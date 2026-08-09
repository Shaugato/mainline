# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The Signed Disposition Receipt, against the vector in ``spec/wire/receipt.md`` §5.

The negative test at the bottom is the one the format exists for. A receipt whose leaf
never appears under a checkpoint is not a missing record: it is affirmative, portable
proof of log misbehaviour, held by the person we handed it to. If
:func:`~trappoint_ledger.receipt.receipt_coverage` could not tell that case from "not
merged yet", the receipt would be an acknowledgement rather than evidence — so both the
``SKIP(within-mmd)`` boundary and the ``FAIL`` beyond it are asserted, on either side of
the same second.

The five conformance points of §7 are covered here: the vector verifies (1), any
single-byte mutation of any member value is rejected (2), an unknown member, a missing
member and a wrong ``typ`` are rejected (3), the 287 canonical bytes reproduce exactly
(4), and the MMD boundary reports SKIP inside and FAIL outside (5).
"""

from __future__ import annotations

import base64
import copy
import hashlib
import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from trappoint_ledger.note import parse_vkey
from trappoint_ledger.receipt import (
    MMD_SECONDS,
    RECEIPT_MEMBERS,
    SDR_TYP,
    MalformedReceipt,
    Receipt,
    ReceiptEnvelope,
    ReceiptVerdict,
    ReceiptVerificationFailed,
    format_issued_at,
    issue_receipt,
    receipt_coverage,
    verify_receipt,
)

pytest.importorskip(
    "trappoint_jcs",
    reason="trappoint_jcs is not importable, so the receipt's canonical bytes — which "
    "ARE the signed bytes — cannot be produced",
)


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "spec" / "wire" / "receipt.md").is_file():
            return parent
    pytest.skip(f"spec/wire/receipt.md was not found above {here}")


ROOT = _repo_root()
RECEIPT_SPEC = (ROOT / "spec" / "wire" / "receipt.md").read_text(encoding="utf-8")
CHECKPOINT_SPEC = (ROOT / "spec" / "wire" / "checkpoint.md").read_text(encoding="utf-8")


def _fenced(text: str, lang: str) -> list[str]:
    """Return the content of every fenced block written in ``lang``."""
    blocks: list[tuple[str, str]] = []
    current: list[str] | None = None
    language = ""
    for line in text.splitlines():
        if line.startswith("```"):
            if current is None:
                language, current = line[3:].strip(), []
            else:
                blocks.append((language, "\n".join(current)))
                current = None
        elif current is not None:
            current.append(line)
    return [content for block_lang, content in blocks if block_lang == lang]


def _section(text: str, heading_prefix: str) -> str:
    marker = f"## {heading_prefix}"
    body = text.split(marker, 1)[1]
    return body.split("\n## ", 1)[0]


VECTOR = _section(RECEIPT_SPEC, "5. Worked test vector")
JSON_BLOCKS = [json.loads(block) for block in _fenced(VECTOR, "json")]
RECEIPT_OBJECT = JSON_BLOCKS[0]
ENVELOPE_OBJECT = JSON_BLOCKS[1]
CANONICAL_TEXT = _fenced(VECTOR, "text")[0]
CANONICAL_BYTES = CANONICAL_TEXT.encode("utf-8")
LOG_KEY = parse_vkey(
    next(
        line.strip()
        for line in CHECKPOINT_SPEC.splitlines()
        if line.startswith("mainline.example/site/BLK-07+")
    )
)


@pytest.fixture
def verify():
    """Return the P-256 verify primitive, skipping loudly if the backend is absent."""
    pytest.importorskip(
        "cryptography",
        reason="'cryptography' is not installed, so no P-256 signature can be verified; "
        "the canonicalisation and MMD assertions in this module still run without it",
    )
    from trappoint_ledger.signer import p256_sha256_verify

    return p256_sha256_verify


@pytest.fixture
def local_signer():
    """The deliberately public §7.1 key, which also signs the receipt vector."""
    pytest.importorskip("cryptography", reason="'cryptography' is not installed")
    from trappoint_ledger.signer import LocalP256Signer

    start = CHECKPOINT_SPEC.index("-----BEGIN PRIVATE KEY-----")
    end = CHECKPOINT_SPEC.index("-----END PRIVATE KEY-----") + len("-----END PRIVATE KEY-----")
    return LocalP256Signer.from_pem((CHECKPOINT_SPEC[start:end] + "\n").encode("ascii"))


# ── §7.4: the canonical bytes reproduce exactly ────────────────────────────────────────


def test_the_receipt_object_canonicalises_to_the_287_bytes_in_the_spec():
    receipt = Receipt.from_object(RECEIPT_OBJECT)
    assert receipt.canonical_bytes() == CANONICAL_BYTES
    assert len(CANONICAL_BYTES) == 287
    digest = hashlib.sha256(CANONICAL_BYTES).hexdigest()
    assert digest in VECTOR, "the SHA-256 stated in §5 does not match the bytes in §5"


def test_the_members_are_sorted_by_utf16_code_unit_and_typ_comes_last():
    """JCS ordering is a property of the canonicaliser; this pins what it produced."""
    assert CANONICAL_TEXT.startswith('{"entry_id":')
    assert CANONICAL_TEXT.endswith('"typ":"MAINLINE-SDR-v1"}')
    assert set(json.loads(CANONICAL_TEXT)) == RECEIPT_MEMBERS


def test_the_object_round_trips_through_the_dataclass():
    receipt = Receipt.from_object(RECEIPT_OBJECT)
    assert receipt.to_object() == RECEIPT_OBJECT
    assert Receipt.from_object(receipt.to_object()) == receipt
    assert receipt.typ == SDR_TYP
    assert receipt.mmd_seconds == MMD_SECONDS


# ── §7.1: the vector verifies ──────────────────────────────────────────────────────────


def test_the_spec_envelope_verifies_against_the_checkpoint_key(verify):
    envelope = ReceiptEnvelope.from_json_object(ENVELOPE_OBJECT)
    assert envelope.key_id == LOG_KEY.key_id
    receipt = verify_receipt(envelope, LOG_KEY, verify)
    assert receipt.entry_id == RECEIPT_OBJECT["entry_id"]
    assert envelope.to_json_object() == ENVELOPE_OBJECT


def test_the_receipt_leaf_is_the_seq_3_leaf_of_the_checkpoint_vector():
    """The two documents describe one tree; if they drift, this fails."""
    assert RECEIPT_OBJECT["leaf_hash"] in CHECKPOINT_SPEC
    assert RECEIPT_OBJECT["origin"] in CHECKPOINT_SPEC


# ── §7.2: any single-byte mutation of any member value is rejected ─────────────────────


def test_every_single_character_mutation_of_every_member_is_rejected(verify):
    envelope = ReceiptEnvelope.from_json_object(ENVELOPE_OBJECT)
    checked = 0
    for member, value in RECEIPT_OBJECT.items():
        if not isinstance(value, str):
            continue
        for index in range(len(value)):
            mutated = dict(RECEIPT_OBJECT)
            original = value[index]
            mutated[member] = value[:index] + ("0" if original != "0" else "1") + value[index + 1 :]
            try:
                candidate = ReceiptEnvelope(
                    receipt=Receipt.from_object(mutated),
                    key_id=envelope.key_id,
                    sig=envelope.sig,
                )
            except MalformedReceipt:
                checked += 1  # refused before it ever reached the signature
                continue
            with pytest.raises(ReceiptVerificationFailed):
                verify_receipt(candidate, LOG_KEY, verify)
            checked += 1
    assert checked > 100


def test_a_mutated_integer_member_is_rejected(verify):
    envelope = ReceiptEnvelope.from_json_object(ENVELOPE_OBJECT)
    mutated = dict(RECEIPT_OBJECT)
    mutated["payload_ver"] = 2
    candidate = ReceiptEnvelope(
        receipt=Receipt.from_object(mutated), key_id=envelope.key_id, sig=envelope.sig
    )
    with pytest.raises(ReceiptVerificationFailed, match="does not verify"):
        verify_receipt(candidate, LOG_KEY, verify)


def test_a_tampered_signature_is_rejected(verify):
    envelope = ReceiptEnvelope.from_json_object(ENVELOPE_OBJECT)
    tampered = bytearray(envelope.sig)
    tampered[-1] ^= 0x01
    with pytest.raises(ReceiptVerificationFailed, match="does not verify"):
        verify_receipt(
            ReceiptEnvelope(receipt=envelope.receipt, key_id=envelope.key_id, sig=bytes(tampered)),
            LOG_KEY,
            verify,
        )


# ── §7.3: structural refusals ──────────────────────────────────────────────────────────


def test_an_unknown_member_is_refused():
    obj = dict(RECEIPT_OBJECT)
    obj["extra"] = "surplus"
    with pytest.raises(MalformedReceipt, match="unexpected"):
        Receipt.from_object(obj)


@pytest.mark.parametrize("member", sorted(RECEIPT_MEMBERS))
def test_a_missing_member_is_refused(member):
    obj = {k: v for k, v in RECEIPT_OBJECT.items() if k != member}
    with pytest.raises(MalformedReceipt, match="missing"):
        Receipt.from_object(obj)


def test_a_wrong_typ_is_refused():
    obj = dict(RECEIPT_OBJECT)
    obj["typ"] = "MAINLINE-SDR-v2"
    with pytest.raises(MalformedReceipt, match="typ"):
        Receipt.from_object(obj)


def test_an_mmd_that_is_not_sixty_is_refused():
    obj = dict(RECEIPT_OBJECT)
    obj["mmd_seconds"] = 600
    with pytest.raises(MalformedReceipt, match="promise"):
        Receipt.from_object(obj)


@pytest.mark.parametrize(
    ("member", "value"),
    [
        ("entry_id", "018F3A2F-9A01-7E42-8B0D-51F6B2C30D44"),
        ("entry_id", "not-a-uuid"),
        ("leaf_hash", "7210ABAAA02DA99E69515827E6B73629F0EBB503FA248214980DE321D9D7A103"),
        ("leaf_hash", "abc"),
        ("issued_at", "2026-08-07T02:11:42Z"),
        ("issued_at", "2026-08-07T02:11:42.310+00:00"),
        ("issued_at", "2026-08-07 02:11:42.310Z"),
        ("site_code", ""),
        ("origin", ""),
    ],
)
def test_a_malformed_member_value_is_refused(member, value):
    obj = dict(RECEIPT_OBJECT)
    obj[member] = value
    with pytest.raises(MalformedReceipt):
        Receipt.from_object(obj)


def test_a_boolean_is_not_an_integer_member():
    obj = dict(RECEIPT_OBJECT)
    obj["payload_ver"] = True
    with pytest.raises(MalformedReceipt, match="integer"):
        Receipt.from_object(obj)


def test_an_envelope_with_a_lying_key_id_is_refused(verify):
    envelope = ReceiptEnvelope.from_json_object(ENVELOPE_OBJECT)
    other = ReceiptEnvelope(
        receipt=envelope.receipt, key_id=bytes.fromhex("00000000"), sig=envelope.sig
    )
    with pytest.raises(ReceiptVerificationFailed, match="names key"):
        verify_receipt(other, LOG_KEY, verify)


def test_a_receipt_for_another_origin_is_refused(verify):
    """A sandbox receipt presented against an evidentiary bundle fails here (A12)."""
    obj = copy.deepcopy(ENVELOPE_OBJECT)
    obj["receipt"]["origin"] = "mainline.sandbox/site/BLK-07"
    with pytest.raises(ReceiptVerificationFailed, match="origin"):
        verify_receipt(obj, LOG_KEY, verify)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda o: o.pop("sig"),
        lambda o: o.__setitem__("key_id", "E74111D1"),
        lambda o: o.__setitem__("key_id", "e74111"),
        lambda o: o.__setitem__("sig", "not base64!"),
    ],
)
def test_a_malformed_envelope_is_refused(mutate):
    obj = copy.deepcopy(ENVELOPE_OBJECT)
    mutate(obj)
    with pytest.raises(MalformedReceipt):
        ReceiptEnvelope.from_json_object(obj)


def test_an_envelope_carries_a_four_byte_key_id_and_a_signature():
    envelope = ReceiptEnvelope.from_json_object(ENVELOPE_OBJECT)
    with pytest.raises(MalformedReceipt, match="key_id is"):
        ReceiptEnvelope(receipt=envelope.receipt, key_id=b"\x01", sig=envelope.sig)
    with pytest.raises(MalformedReceipt, match="sig is empty"):
        ReceiptEnvelope(receipt=envelope.receipt, key_id=envelope.key_id, sig=b"")
    with pytest.raises(MalformedReceipt, match="sdr_version"):
        ReceiptEnvelope(
            receipt=envelope.receipt, key_id=envelope.key_id, sig=envelope.sig, sdr_version=2
        )


# ── Issuing ────────────────────────────────────────────────────────────────────────────


def test_issue_and_verify_round_trip(local_signer, verify):
    from trappoint_ledger.signer import public_key_for

    origin = "mainline.example/site/BLK-07"
    issued = datetime(2026, 8, 7, 2, 11, 42, 310_777, tzinfo=UTC)
    envelope = issue_receipt(
        local_signer,
        entry_id=RECEIPT_OBJECT["entry_id"],
        leaf_hash=RECEIPT_OBJECT["leaf_hash"],
        site_code="BLK-07",
        origin=origin,
        payload_ver=1,
        issued_at=issued,
    )
    # Truncated, never rounded: the deadline it implies is never later than the truth.
    assert envelope.receipt.issued_at == "2026-08-07T02:11:42.310Z"
    assert envelope.receipt.canonical_bytes() == CANONICAL_BYTES
    key = public_key_for(local_signer, origin)
    assert verify_receipt(envelope, key, verify) == envelope.receipt
    assert json.loads(json.dumps(envelope.to_json_object()))["key_id"] == LOG_KEY.key_id_hex


def test_a_receipt_tampered_after_issue_fails(local_signer, verify):
    from trappoint_ledger.signer import public_key_for

    origin = "mainline.example/site/BLK-07"
    envelope = issue_receipt(
        local_signer,
        entry_id=RECEIPT_OBJECT["entry_id"],
        leaf_hash=RECEIPT_OBJECT["leaf_hash"],
        site_code="BLK-07",
        origin=origin,
        payload_ver=1,
        issued_at=datetime.now(tz=UTC),
    )
    forged = ReceiptEnvelope(
        receipt=Receipt.from_object({**envelope.receipt.to_object(), "site_code": "BLK-08"}),
        key_id=envelope.key_id,
        sig=envelope.sig,
    )
    with pytest.raises(ReceiptVerificationFailed, match="does not verify"):
        verify_receipt(forged, public_key_for(local_signer, origin), verify)


def test_format_issued_at_refuses_a_naive_datetime():
    with pytest.raises(ValueError, match="timezone-aware"):
        format_issued_at(datetime(2026, 8, 7, 2, 11, 42))  # noqa: DTZ001 - the point


def test_format_issued_at_normalises_to_utc():
    from datetime import timezone

    aware = datetime(2026, 8, 7, 12, 11, 42, 310_000, tzinfo=timezone(timedelta(hours=10)))
    assert format_issued_at(aware) == "2026-08-07T02:11:42.310Z"
    assert re.match(r"\A\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z\Z", format_issued_at(aware))


# ── §7.5: the MMD boundary, which is why the receipt exists ────────────────────────────


def _receipt() -> Receipt:
    return Receipt.from_object(RECEIPT_OBJECT)


def test_coverage_passes_when_the_leaf_is_in_the_bundle():
    receipt = _receipt()
    finding = receipt_coverage(
        receipt,
        leaf_hashes_in_bundle={receipt.leaf_hash},
        newest_checkpoint_at=receipt.issued + timedelta(days=400),
    )
    assert finding.verdict is ReceiptVerdict.PASS
    assert not finding.is_accusation
    assert receipt.leaf_hash in finding.detail


def test_coverage_skips_inside_the_mmd_and_prints_the_deadline():
    receipt = _receipt()
    finding = receipt_coverage(
        receipt,
        leaf_hashes_in_bundle=set(),
        newest_checkpoint_at=receipt.deadline,
    )
    assert finding.verdict is ReceiptVerdict.SKIP_WITHIN_MMD
    assert not finding.is_accusation
    assert format_issued_at(receipt.deadline) in finding.detail


def test_coverage_fails_one_millisecond_past_the_deadline():
    """The whole product of the format: a signed promise the log did not keep."""
    receipt = _receipt()
    finding = receipt_coverage(
        receipt,
        leaf_hashes_in_bundle=set(),
        newest_checkpoint_at=receipt.deadline + timedelta(milliseconds=1),
    )
    assert finding.verdict is ReceiptVerdict.FAIL_LOG_MISBEHAVIOUR
    assert finding.is_accusation
    assert "LOG MISBEHAVIOUR" in finding.detail
    assert receipt.entry_id in finding.detail


def test_the_mmd_boundary_is_exactly_sixty_seconds():
    receipt = _receipt()
    assert receipt.deadline - receipt.issued == timedelta(seconds=MMD_SECONDS)


def test_coverage_skips_rather_than_accuses_when_the_bundle_has_no_checkpoint():
    """Gap G6 in ADR 0043: §4 compares against a quantity that may not exist."""
    finding = receipt_coverage(_receipt(), leaf_hashes_in_bundle=set(), newest_checkpoint_at=None)
    assert finding.verdict is ReceiptVerdict.SKIP_NO_CHECKPOINT
    assert not finding.is_accusation
    assert str(finding.verdict).startswith("SKIP")


def test_the_verdicts_are_the_words_the_report_prints():
    assert str(ReceiptVerdict.PASS) == "PASS"
    assert str(ReceiptVerdict.SKIP_WITHIN_MMD) == "SKIP(within-mmd)"
    assert str(ReceiptVerdict.FAIL_LOG_MISBEHAVIOUR) == "FAIL"


def test_the_envelope_is_not_what_is_signed():
    """§3: a verifier re-canonicalises the receipt and never verifies over the envelope."""
    envelope = ReceiptEnvelope.from_json_object(ENVELOPE_OBJECT)
    as_sent = json.dumps(ENVELOPE_OBJECT, indent=2).encode("utf-8")
    assert envelope.receipt.canonical_bytes() != as_sent
    assert base64.b64decode(ENVELOPE_OBJECT["sig"]) == envelope.sig
