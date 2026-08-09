# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The literal keyword arguments that go to AWS, and the DER bytes that go to a TSA.

AWS credentials are not valid on the machine this package was written on. Everything in
this file exists so that the first invocation that *does* have credentials fails on a
mismatch instead of writing an object nobody can rely on — S3 Object Lock cannot be
retrofitted onto an object any more than onto a bucket (GT-18), and a checkpoint written
without COMPLIANCE retention is a checkpoint we can quietly delete, which is the one
property the whole design exists to remove.

Every expected value below is a **literal**, not an import from the code under test.
Asserting ``kwargs["ObjectLockMode"] == ports.OBJECT_LOCK_MODE`` would pass after
somebody changed ``OBJECT_LOCK_MODE`` to ``"GOVERNANCE"``, which is precisely the change
that has to fail.

Deliberately not ``moto`` (ruling CU-10): its Object Lock enforcement is incomplete, and
a green test against a mock that does not enforce the control is worse than no test.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fakes import (
    EXPECTED_LEGAL_HOLD,
    EXPECTED_MESSAGE_TYPE,
    EXPECTED_OBJECT_LOCK_MODE,
    EXPECTED_SIGNING_ALGORITHM,
    FakeCallRefused,
    FakeKmsClient,
    FakeS3Client,
    FakeTransport,
)
from mainline_anchor.aws import (
    CHECKPOINT_CONTENT_TYPE,
    S3ObjectLockArchive,
    S3TilePublisher,
    assert_region,
    kms_sign_port,
    plus_years,
)
from mainline_anchor.beacon_client import BeaconUnavailable, HttpBeaconSource
from mainline_anchor.ports import (
    AnchorError,
    AnchorMisconfigured,
    HttpResponse,
    ObjectLockNotEnforced,
    Tile,
    as_metadata,
)
from mainline_anchor.tsa_client import (
    OID_SHA256,
    TSA_CONTENT_TYPE,
    HttpTsaAuthority,
    TsaRejected,
    TsaResponseInvalid,
    build_timestamp_request,
    parse_timestamp_response,
)

NOTE = (
    b"mainline.example/site/BLK-07\n5\nAAAA\n\n\xe2\x80\x94 mainline.example/site/BLK-07 AAAAAAAA\n"
)
DIGEST = bytes(range(32))
FIXED_NOW = datetime(2026, 8, 10, 4, 30, tzinfo=UTC)


def clock() -> datetime:
    return FIXED_NOW


# ── S3 PutObject ──────────────────────────────────────────────────────────────────────


def test_put_object_carries_compliance_a_legal_hold_and_seven_years():
    client = FakeS3Client()
    archive = S3ObjectLockArchive(client, client.bucket, clock=clock)

    archived = archive.put_checkpoint(
        key="checkpoint/mainline.example/site/BLK-07/00000000000000000005-0001.note",
        note=NOTE,
        metadata=as_metadata("mainline.example/site/BLK-07", 5, DIGEST),
    )

    assert len(client.put_calls) == 1
    call = client.put_calls[0]
    assert call["ObjectLockMode"] == "COMPLIANCE"
    assert call["ObjectLockLegalHoldStatus"] == "ON"
    assert call["ObjectLockRetainUntilDate"] == datetime(2033, 8, 10, 4, 30, tzinfo=UTC)
    assert call["Body"] == NOTE
    assert call["ContentType"] == CHECKPOINT_CONTENT_TYPE
    assert call["ChecksumAlgorithm"] == "SHA256"
    assert call["Metadata"]["origin"] == "mainline.example/site/BLK-07"
    assert call["Metadata"]["tree-size"] == "5"

    # And the metadata came BACK from the service, not from our memory of the request.
    assert client.head_calls
    assert archived.object_lock_mode == "COMPLIANCE"
    archived.assert_indelible(floor=FIXED_NOW + timedelta(days=365 * 7 - 3))


def test_a_bucket_created_without_object_lock_is_caught_by_the_read_back():
    # This is the failure the read-back exists for. The real S3 accepts the write against
    # a bucket with no Object Lock configuration, ignores every lock parameter, and
    # returns 200 — so the request succeeding proves nothing at all.
    client = FakeS3Client(object_lock_enabled=False)
    archive = S3ObjectLockArchive(client, client.bucket, clock=clock)

    archived = archive.put_checkpoint(key="checkpoint/x", note=NOTE, metadata={"origin": "x"})

    assert client.put_calls  # the write happened
    assert archived.object_lock_mode is None  # and it is holding nothing
    with pytest.raises(ObjectLockNotEnforced, match="ObjectLockMode"):
        archived.assert_indelible(floor=FIXED_NOW)


def test_an_unversioned_bucket_is_caught_before_the_retention_is_even_looked_at():
    client = FakeS3Client(versioned=False)
    archive = S3ObjectLockArchive(client, client.bucket, clock=clock)
    archived = archive.put_checkpoint(key="checkpoint/x", note=NOTE, metadata={"origin": "x"})
    with pytest.raises(ObjectLockNotEnforced, match="VersionId"):
        archived.assert_indelible(floor=FIXED_NOW)


def test_the_fake_refuses_governance_so_the_assertion_is_not_vacuous():
    # Proof that the fake bites: hand it the wrong mode directly and it refuses. Without
    # this, "the fake asserts COMPLIANCE" is itself an untested claim.
    client = FakeS3Client()
    with pytest.raises(FakeCallRefused, match="GOVERNANCE"):
        client.put_object(
            Bucket=client.bucket,
            Key="checkpoint/x",
            Body=NOTE,
            ObjectLockMode="GOVERNANCE",
            ObjectLockLegalHoldStatus=EXPECTED_LEGAL_HOLD,
            ObjectLockRetainUntilDate=FIXED_NOW.replace(year=2033),
        )
    with pytest.raises(FakeCallRefused, match="LegalHoldStatus"):
        client.put_object(
            Bucket=client.bucket,
            Key="checkpoint/x",
            Body=NOTE,
            ObjectLockMode=EXPECTED_OBJECT_LOCK_MODE,
            ObjectLockLegalHoldStatus="OFF",
            ObjectLockRetainUntilDate=FIXED_NOW.replace(year=2033),
        )
    with pytest.raises(FakeCallRefused, match="days out"):
        client.put_object(
            Bucket=client.bucket,
            Key="checkpoint/x",
            Body=NOTE,
            ObjectLockMode=EXPECTED_OBJECT_LOCK_MODE,
            ObjectLockLegalHoldStatus=EXPECTED_LEGAL_HOLD,
            ObjectLockRetainUntilDate=FIXED_NOW.replace(year=2027),
        )


def test_a_retention_below_seven_years_is_refused_at_construction():
    client = FakeS3Client()
    with pytest.raises(AnchorMisconfigured, match="floor"):
        S3ObjectLockArchive(client, client.bucket, retention_years=3, clock=clock)


def test_a_naive_clock_cannot_produce_a_retain_until_date():
    client = FakeS3Client()
    archive = S3ObjectLockArchive(client, client.bucket, clock=lambda: datetime(2026, 8, 10))  # noqa: DTZ001 - the point
    with pytest.raises(AnchorMisconfigured, match="timezone-aware"):
        archive.put_checkpoint(key="checkpoint/x", note=NOTE, metadata={})


def test_plus_years_rounds_a_leap_day_up():
    assert plus_years(datetime(2028, 2, 29, tzinfo=UTC), 7) == datetime(2035, 3, 1, tzinfo=UTC)
    assert plus_years(datetime(2026, 8, 10, tzinfo=UTC), 7) == datetime(2033, 8, 10, tzinfo=UTC)


# ── REGION PIN ────────────────────────────────────────────────────────────────────────


def test_region_pin_refuses_a_client_in_the_wrong_region():
    client = FakeS3Client(region="us-east-1")
    with pytest.raises(AnchorMisconfigured, match="REGION PIN"):
        assert_region(client, "ap-southeast-2")
    assert_region(client, "us-east-1")
    assert_region(client, None)


def test_an_unknowable_region_is_reported_rather_than_assumed_to_match():
    class Opaque:
        pass

    with pytest.raises(AnchorMisconfigured, match="could not be checked"):
        assert_region(Opaque(), "ap-southeast-2")


# ── KMS Sign ──────────────────────────────────────────────────────────────────────────


def test_kms_sign_is_ecdsa_sha_256_over_raw_message_bytes():
    client = FakeKmsClient(region="ap-southeast-2")
    signer = kms_sign_port(client, client.key_id, expected_region="ap-southeast-2")

    signature = signer.sign(NOTE)

    assert signature
    assert len(client.sign_calls) == 1
    call = client.sign_calls[0]
    assert call["SigningAlgorithm"] == "ECDSA_SHA_256"
    assert call["MessageType"] == "RAW"
    assert call["Message"] == NOTE
    assert call["KeyId"] == client.key_id


def test_the_kms_fake_refuses_the_wrong_algorithm_so_the_assertion_is_not_vacuous():
    client = FakeKmsClient()
    with pytest.raises(FakeCallRefused, match="SigningAlgorithm"):
        client.sign(
            KeyId=client.key_id,
            Message=NOTE,
            MessageType=EXPECTED_MESSAGE_TYPE,
            SigningAlgorithm="ECDSA_SHA_384",
        )
    with pytest.raises(FakeCallRefused, match="MessageType"):
        client.sign(
            KeyId=client.key_id,
            Message=NOTE,
            MessageType="DIGEST",
            SigningAlgorithm=EXPECTED_SIGNING_ALGORITHM,
        )


def test_the_kms_public_key_is_checked_for_key_spec_and_usage():
    client = FakeKmsClient()
    signer = kms_sign_port(client, client.key_id)
    assert signer.public_key_spki_der() == client.spki
    assert client.get_public_key_calls[0]["KeyId"] == client.key_id


def test_kms_region_pin_is_enforced_before_the_signer_is_built():
    client = FakeKmsClient(region="us-east-1")
    with pytest.raises(AnchorMisconfigured, match="REGION PIN"):
        kms_sign_port(client, client.key_id, expected_region="ap-southeast-2")
    assert client.get_public_key_calls == []


# ── Tiles ─────────────────────────────────────────────────────────────────────────────


def test_tiles_are_published_without_object_lock_and_with_an_immutable_cache_header():
    client = FakeS3Client(bucket="mainline-tiles")
    publisher = S3TilePublisher(client, "mainline-tiles")
    published = publisher.publish(
        [Tile(path="0/000", data=b"aaa"), Tile(path="0/001", data=b"bbb")]
    )

    assert [p.path for p in published] == ["0/000", "0/001"]
    for call in client.put_calls:
        assert "ObjectLockMode" not in call
        assert call["CacheControl"] == "public, max-age=31536000, immutable"
        assert call["Key"].startswith("tile/")


# ── RFC 3161 ──────────────────────────────────────────────────────────────────────────


def test_the_timestamp_request_is_the_der_an_opposing_implementation_must_reproduce():
    # A frozen wire vector. The bytes below were produced by this encoder and then read
    # back field by field in the assertions that follow, so the constant is anchored to a
    # decoded structure rather than to itself.
    request = build_timestamp_request(DIGEST, nonce=0x0123456789ABCDEF, cert_req=True)
    assert request.hex() == (
        "3043"  # SEQUENCE TimeStampReq, 67 content bytes
        "020101"  # version   INTEGER 1
        "3031"  # messageImprint SEQUENCE
        "300d"  # ..hashAlgorithm AlgorithmIdentifier
        "0609608648016503040201"  # ....OID 2.16.840.1.101.3.4.2.1 (sha-256)
        "0500"  # ....parameters NULL, present and empty, as RFC 5754 §2 permits
        "0420"
        + DIGEST.hex()  # ..hashedMessage OCTET STRING (32 bytes)
        + "02080123456789abcdef"  # nonce  INTEGER, minimal-width, positive
        + "0101ff"  # certReq  BOOLEAN TRUE (DER: 0xFF, never 0x01)
    )
    # reqPolicy is absent, which is a request for the authority's default policy.
    assert request[0] == 0x30


def test_the_timestamp_request_encodes_sha256_the_digest_and_a_positive_nonce():
    request = build_timestamp_request(DIGEST, nonce=1, cert_req=False)
    assert DIGEST in request
    # The SHA-256 OID, DER-encoded, is 06 09 60 86 48 01 65 03 04 02 01.
    assert bytes.fromhex("0609608648016503040201") in request
    assert bytes.fromhex("0101ff") not in request  # certReq omitted at its DEFAULT


def test_a_digest_that_is_not_sha256_is_refused_before_it_reaches_the_wire():
    with pytest.raises(ValueError, match="SHA-256 digest"):
        build_timestamp_request(b"\x00" * 20, nonce=1)
    with pytest.raises(ValueError, match="positive"):
        build_timestamp_request(DIGEST, nonce=0)


def test_a_rejected_pki_status_is_a_named_refusal_and_not_a_token():
    # TimeStampResp with PKIStatus = 2 (rejection) and no token.
    response = bytes.fromhex("30053003020102")
    with pytest.raises(TsaRejected) as caught:
        parse_timestamp_response(response)
    assert caught.value.status == 2


def test_a_granted_status_with_no_token_is_refused_rather_than_returning_empty_bytes():
    response = bytes.fromhex("30053003020100")
    with pytest.raises(TsaResponseInvalid, match="carries no timeStampToken"):
        parse_timestamp_response(response)


def test_indefinite_length_is_ber_and_is_refused():
    with pytest.raises(TsaResponseInvalid, match="indefinite-length"):
        parse_timestamp_response(bytes.fromhex("3080") + b"\x00\x00")


def test_a_truncated_der_element_is_refused_with_the_byte_counts():
    with pytest.raises(TsaResponseInvalid, match="claims 5 bytes and 2 remain"):
        parse_timestamp_response(bytes.fromhex("30050000"))
    with pytest.raises(TsaResponseInvalid, match="long-form length is truncated"):
        parse_timestamp_response(bytes.fromhex("30ff00"))


def test_the_authority_refuses_a_token_over_someone_elses_digest():
    token = _minimal_token(imprint=b"\xff" * 32, nonce=7)
    transport = FakeTransport({"https://tsa.test/": HttpResponse(200, _wrap(token))})
    authority = HttpTsaAuthority("tsa-test", "https://tsa.test/", transport, nonce_source=lambda: 7)
    with pytest.raises(TsaResponseInvalid, match="not over our digest"):
        authority.timestamp(DIGEST)


def test_the_authority_refuses_a_token_that_does_not_echo_the_nonce():
    token = _minimal_token(imprint=DIGEST, nonce=None)
    transport = FakeTransport({"https://tsa.test/": HttpResponse(200, _wrap(token))})
    authority = HttpTsaAuthority("tsa-test", "https://tsa.test/", transport, nonce_source=lambda: 7)
    with pytest.raises(TsaResponseInvalid, match="omitted the nonce"):
        authority.timestamp(DIGEST)

    token = _minimal_token(imprint=DIGEST, nonce=9)
    transport = FakeTransport({"https://tsa.test/": HttpResponse(200, _wrap(token))})
    authority = HttpTsaAuthority("tsa-test", "https://tsa.test/", transport, nonce_source=lambda: 7)
    with pytest.raises(TsaResponseInvalid, match="echoed nonce 9"):
        authority.timestamp(DIGEST)


def test_a_good_token_yields_gen_time_and_the_echoed_imprint():
    token = _minimal_token(imprint=DIGEST, nonce=7)
    transport = FakeTransport({"https://tsa.test/": HttpResponse(200, _wrap(token))})
    authority = HttpTsaAuthority("tsa-test", "https://tsa.test/", transport, nonce_source=lambda: 7)

    result = authority.timestamp(DIGEST)

    assert result.authority == "tsa-test"
    assert result.message_imprint == DIGEST
    assert result.gen_time == datetime(2026, 8, 10, 4, 30, 5, tzinfo=UTC)
    assert result.token_der == token
    method, url, body = transport.calls[0]
    assert (method, url) == ("POST", "https://tsa.test/")
    assert body == build_timestamp_request(DIGEST, nonce=7)
    assert transport.last_headers["Content-Type"] == TSA_CONTENT_TYPE


def test_a_non_200_from_an_authority_is_a_refusal_naming_the_status():
    transport = FakeTransport({"https://tsa.test/": HttpResponse(503, b"busy")})
    authority = HttpTsaAuthority("tsa-test", "https://tsa.test/", transport, nonce_source=lambda: 7)
    with pytest.raises(TsaResponseInvalid, match="HTTP 503"):
        authority.timestamp(DIGEST)


# ── Beacons ───────────────────────────────────────────────────────────────────────────

_DRAND_URL = "https://api.drand.sh/52db9ba70e0cc0f6eaf7803dd07447a1f5477735fd3f661792ba94600c84e971/public/latest"
_NIST_URL = "https://beacon.nist.gov/beacon/2.0/pulse/last"
_SIGNATURE = "ab" * 48


def _drand_body() -> bytes:
    import hashlib
    import json

    randomness = hashlib.sha256(bytes.fromhex(_SIGNATURE)).hexdigest()
    return json.dumps(
        {"round": 31088494, "randomness": randomness, "signature": _SIGNATURE}
    ).encode()


def _nist_body() -> bytes:
    import json

    return json.dumps(
        {
            "pulse": {
                "version": "Version 2.0",
                "chainIndex": 2,
                "pulseIndex": 29255654,
                "outputValue": ("D7" * 64),
                "timeStamp": "2026-08-10T04:00:00.000Z",
            }
        }
    ).encode()


def test_a_live_snapshot_carries_both_beacons_and_the_extension_lines_are_ordered():
    transport = FakeTransport(
        {_DRAND_URL: HttpResponse(200, _drand_body()), _NIST_URL: HttpResponse(200, _nist_body())}
    )
    snapshot = HttpBeaconSource(transport).snapshot()

    assert [name for name, _ in snapshot.extensions()] == ["drand", "nist"]
    assert snapshot.drand.round_number == 31088494
    assert snapshot.nist.pulse_index == 29255654
    assert snapshot.nist.output_value == "d7" * 64  # normalised to lowercase


def test_a_drand_round_whose_randomness_does_not_bind_its_signature_is_refused():
    import json

    body = json.dumps({"round": 5, "randomness": "00" * 32, "signature": _SIGNATURE}).encode()
    transport = FakeTransport({_DRAND_URL: HttpResponse(200, body)})
    with pytest.raises(BeaconUnavailable, match="internally"):
        HttpBeaconSource(transport).drand_round()


def test_a_beacon_that_answers_non_200_is_unavailable_rather_than_defaulted():
    transport = FakeTransport({_DRAND_URL: HttpResponse(502, b"")})
    with pytest.raises(BeaconUnavailable, match="HTTP 502"):
        HttpBeaconSource(transport).drand_round()


def test_a_beacon_that_answers_non_json_is_unavailable():
    transport = FakeTransport({_NIST_URL: HttpResponse(200, b"<html>maintenance</html>")})
    with pytest.raises(BeaconUnavailable, match="non-JSON"):
        HttpBeaconSource(transport).nist_pulse()


def test_the_transport_refuses_a_plaintext_url():
    from mainline_anchor.tsa_client import UrllibTransport

    with pytest.raises(AnchorError, match="refusing to fetch"):
        UrllibTransport().request("GET", "http://tsa.example/")


# ── helpers: a minimal, structurally-valid TimeStampToken ─────────────────────────────
#
# Hand-built rather than fetched. A real token from FreeTSA or Sigstore is a fixture
# `scripts/custody/fetch_tsa_fixtures.py` collects for `trappoint-verify`'s check 5, where
# the signature is actually verified. What is needed HERE is only that the walk from
# ContentInfo down to TSTInfo lands on the right fields, so the SignedData carries no
# certificates and no signerInfos and the token verifies nothing.


def _tlv(tag: int, content: bytes) -> bytes:
    if len(content) < 0x80:
        return bytes([tag, len(content)]) + content
    body = len(content).to_bytes((len(content).bit_length() + 7) // 8, "big")
    return bytes([tag, 0x80 | len(body)]) + body + content


def _int(value: int) -> bytes:
    width = (value.bit_length() + 8) // 8 if value else 1
    return _tlv(0x02, value.to_bytes(width, "big"))


def _oid(dotted: str) -> bytes:
    arcs = [int(a) for a in dotted.split(".")]
    out = bytearray()
    first = 40 * arcs[0] + arcs[1]
    for arc in [first, *arcs[2:]]:
        chunks = []
        value = arc
        while True:
            chunks.append(value & 0x7F)
            value >>= 7
            if not value:
                break
        chunks.reverse()
        out += bytes(c | 0x80 for c in chunks[:-1]) + bytes([chunks[-1]])
    return _tlv(0x06, bytes(out))


def _minimal_token(*, imprint: bytes, nonce: int | None) -> bytes:
    algorithm = _tlv(0x30, _oid(OID_SHA256) + _tlv(0x05, b""))
    message_imprint = _tlv(0x30, algorithm + _tlv(0x04, imprint))
    tst_fields = (
        _int(1) + _oid("1.2.3.4.1") + message_imprint + _int(42) + _tlv(0x18, b"20260810043005Z")
    )
    if nonce is not None:
        tst_fields += _int(nonce)
    tst_info = _tlv(0x30, tst_fields)
    encap = _tlv(0x30, _oid("1.2.840.113549.1.9.16.1.4") + _tlv(0xA0, _tlv(0x04, tst_info)))
    signed_data = _tlv(0x30, _int(3) + _tlv(0x31, b"") + encap + _tlv(0x31, b""))
    return _tlv(0x30, _oid("1.2.840.113549.1.7.2") + _tlv(0xA0, signed_data))


def _wrap(token: bytes) -> bytes:
    """Wrap a token in a granted TimeStampResp."""
    return _tlv(0x30, _tlv(0x30, _int(0)) + token)
