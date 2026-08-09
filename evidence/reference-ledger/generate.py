#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Generate the committed, byte-deterministic reference evidence bundle.

**CU-6.** A reference fixture a stranger cannot regenerate is a screenshot. This script
is the regeneration, and ``scripts/custody/regen_reference_ledger.py`` asserts in CI that
running it changes nothing — the same zero-diff discipline ``trappoint render`` is held to.

Everything that could vary between two runs is pinned:

============================ ==========================================================
source of variation          how it is removed
============================ ==========================================================
wall clock                   ``ORIGIN_INSTANT``: one fixed UTC instant, all times derived
identity (UUIDs)             ``uuid5`` under ``IDENTITY_NAMESPACE`` over a stable label
key material                 committed PEMs in ``keys/`` — public by design
ECDSA nonce                  **RFC 6979** deterministic ``k`` (see :func:`ecdsa_sign_rfc6979`)
RSA signatures               PKCS#1 v1.5 is deterministic by construction
JSON member order            RFC 8785 (JCS) via ``trappoint_jcs.canon_v1``
line endings                 every text artefact is written with ``\\n`` and hashed LF-first
============================ ==========================================================

**What this bundle proves, and what it does not.** It proves that a verifier implementing
``spec/wire/evidence-bundle.md`` v1.0 works, on a complete, non-trivial input, offline,
with no credential. It proves nothing whatever about MAINLINE's production log: the log
key is published in this repository, the beacon values are synthetic, the RFC 3161 tokens
come from a timestamp authority minted in this file, and the S3 Object Lock metadata is a
recorded *shape* rather than a live response. Each of those is labelled in the bundle
itself and in ``README.md``, because a fixture that implies production custody is exactly
the overclaim this domain exists to refuse.

Run it:

.. code-block:: console

   $ python evidence/reference-ledger/generate.py            # regenerate in place
   $ python evidence/reference-ledger/generate.py --out /tmp/x  # regenerate elsewhere

The generator depends on ``cryptography`` and on two workspace packages
(``trappoint-jcs`` for the canonical bytes and ``trappoint-ledger`` for the RFC 6962 tree
and the link chain). That is deliberate: the *generator* may use our code, because a
generator that reimplemented the tree would be testing itself. The **verifier** may not,
and does not — its dependency floor is asserted separately.
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import hashlib
import hmac
import json
import sys
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

HERE: Final = Path(__file__).resolve().parent
REPO_ROOT: Final = HERE.parents[1]

for _source_root in (
    REPO_ROOT / "packages" / "trappoint-jcs" / "src",
    REPO_ROOT / "packages" / "trappoint-ledger" / "src",
):
    if _source_root.is_dir() and str(_source_root) not in sys.path:
        sys.path.insert(0, str(_source_root))

from cryptography.hazmat.primitives import hashes, serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa  # noqa: E402
from cryptography.hazmat.primitives.asymmetric.utils import (  # noqa: E402
    encode_dss_signature,
)
from cryptography import x509  # noqa: E402
from cryptography.x509.oid import NameOID  # noqa: E402

from trappoint_jcs.canon_v1 import (  # noqa: E402
    CANON_VERSION,
    canon_src_sha256,
    canonicalise_payload,
)
from trappoint_ledger.chain import GENESIS_LINK_HASH, chain_links  # noqa: E402
from trappoint_ledger.merkle import (  # noqa: E402
    EMPTY_ROOT,
    consistency_proof,
    hash_leaf,
    inclusion_proof,
    merkle_tree_hash,
    verify_consistency,
    verify_inclusion,
)

# =======================================================================================
# The pins. Change any of these and the bundle changes; that is the point.
# =======================================================================================

#: One fixed instant. Every timestamp in the bundle is this plus a fixed offset.
ORIGIN_INSTANT: Final = dt.datetime(2026, 8, 7, 2, 0, 0, tzinfo=dt.UTC)

#: uuid5 namespace for every identity in the fixture. Arbitrary, fixed, published.
IDENTITY_NAMESPACE: Final = uuid.UUID("6b2f0f8e-3d1a-5a7c-9f42-0c1d2e3f4a5b")

SITE_CODE: Final = "blk-07"
ORIGIN: Final = f"mainline.example/site/{SITE_CODE}"
GENERATOR: Final = "mainline reference-ledger generator 1.0"
MMD_SECONDS: Final = 60

#: Checkpoint cadence in the fixture, in seconds. Equal to the MMD by design: the honest
#: window of undetectable mutation is one cadence, and the receipt promise is one cadence.
CHECKPOINT_CADENCE_S: Final = 60

#: drand quicknet, from ``spec/wire/checkpoint.md`` §4.2. Round→time is arithmetic.
DRAND_CHAIN_HASH: Final = "52db9ba70e0cc0f6eaf7803dd07447a1f5477735fd3f661792ba94600c84e971"
DRAND_GENESIS: Final = 1692803367
DRAND_PERIOD_S: Final = 3

#: The NIST beacon chain index used by the fixture pulses.
NIST_CHAIN_INDEX: Final = 2

KEYS: Final = HERE / "keys"
LOG_KEY_PEM: Final = KEYS / "reference-log.NOT-SECRET.key.pem"
WITNESS_KEY_PEM: Final = KEYS / "reference-witness.NOT-SECRET.key.pem"
WEBAUTHN_KEY_PEM: Final = KEYS / "reference-webauthn.NOT-SECRET.key.pem"
TSA_ROOT_KEY_PEM: Final = KEYS / "reference-tsa-root.NOT-SECRET.key.pem"
TSA_LEAF_KEY_PEM: Final = KEYS / "reference-tsa.NOT-SECRET.key.pem"

WITNESS_ID: Final = "witness.mainline.example/operator-1"
WEBAUTHN_RP_ID: Final = "console.mainline.example"
WEBAUTHN_ORIGIN: Final = "https://console.mainline.example"

#: Tree sizes at which the fixture log issues a checkpoint. Size 0 is included on purpose:
#: ``spec/wire/checkpoint.md`` §7.6 requires a verifier to accept the empty tree, and a log
#: that cannot prove it was empty when it was empty has a hole at its own beginning.
CHECKPOINT_SIZES: Final = (0, 1, 3, 18, 34, 50, 66, 73)

#: The named subset the README points a first-time reader at. Every leaf gets an inclusion
#: proof (``spec/custody/checks.yaml`` check 16 requires it); these are the interesting ones.
NAMED_SUBSET_LABELS: Final = (
    "schema attestation of the merge gate",
    "the first blocking check opened",
    "the disposition that cleared it",
    "the merge the database permitted afterwards",
)


# =======================================================================================
# Deterministic ECDSA over P-256 — RFC 6979, implemented here rather than delegated
# =======================================================================================
#
# `cryptography` grew `ec.ECDSA(..., deterministic_signing=True)` in 42.0, but only when it
# is linked against OpenSSL 3.2 or newer. A byte-determinism claim that silently depends on
# the OpenSSL build of whoever runs the regeneration is not a determinism claim, so the
# nonce derivation lives here, in ~60 lines a reader can audit. Where the library CAN do it,
# `_assert_matches_library` checks that the two agree — so this code is cross-examined by an
# independent implementation on every run that can afford it, and the run says so if it
# cannot.

_P: Final = 2**256 - 2**224 + 2**192 + 2**96 - 1
_A: Final = _P - 3
_B: Final = 0x5AC635D8AA3A93E7B3EBBD55769886BC651D06B0CC53B0F63BCE3C3E27D2604B
_GX: Final = 0x6B17D1F2E12C4247F8BCE6E563A440F277037D812DEB33A0F4A13945D898C296
_GY: Final = 0x4FE342E2FE1A7F9B8EE7EB4A7C0F9E162BCE33576B315ECECBB6406837BF51F5
_N: Final = 0xFFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551
_QLEN: Final = 256


def _point_add(
    p: tuple[int, int] | None, q: tuple[int, int] | None
) -> tuple[int, int] | None:
    """Affine point addition on P-256. ``None`` is the point at infinity."""
    if p is None:
        return q
    if q is None:
        return p
    x1, y1 = p
    x2, y2 = q
    if x1 == x2 and (y1 + y2) % _P == 0:
        return None
    if p == q:
        lam = (3 * x1 * x1 + _A) * pow(2 * y1, -1, _P) % _P
    else:
        lam = (y2 - y1) * pow(x2 - x1, -1, _P) % _P
    x3 = (lam * lam - x1 - x2) % _P
    return (x3, (lam * (x1 - x3) - y1) % _P)


def _scalar_mul(k: int, point: tuple[int, int]) -> tuple[int, int]:
    """Double-and-add. Not constant time — this key is published on purpose."""
    result: tuple[int, int] | None = None
    addend: tuple[int, int] | None = point
    while k:
        if k & 1:
            result = _point_add(result, addend)
        addend = _point_add(addend, addend)
        k >>= 1
    if result is None:  # pragma: no cover — k is always in [1, n)
        raise ValueError("scalar multiplication produced the point at infinity")
    return result


def _bits2int(data: bytes) -> int:
    value = int.from_bytes(data, "big")
    excess = len(data) * 8 - _QLEN
    return value >> excess if excess > 0 else value


def _int2octets(value: int) -> bytes:
    return value.to_bytes(32, "big")


def _bits2octets(data: bytes) -> bytes:
    z1 = _bits2int(data)
    z2 = z1 - _N
    return _int2octets(z2 if z2 >= 0 else z1)


def _hmac(key: bytes, *parts: bytes) -> bytes:
    mac = hmac.new(key, digestmod=hashlib.sha256)
    for part in parts:
        mac.update(part)
    return mac.digest()


def _rfc6979_nonces(private_value: int, digest: bytes) -> Iterable[int]:
    """Yield candidate ``k`` values exactly as RFC 6979 §3.2 specifies, HMAC-SHA-256."""
    v = b"\x01" * 32
    k = b"\x00" * 32
    x_octets = _int2octets(private_value)
    h_octets = _bits2octets(digest)
    k = _hmac(k, v, b"\x00", x_octets, h_octets)
    v = _hmac(k, v)
    k = _hmac(k, v, b"\x01", x_octets, h_octets)
    v = _hmac(k, v)
    while True:
        t = b""
        while len(t) * 8 < _QLEN:
            v = _hmac(k, v)
            t += v
        yield _bits2int(t)
        k = _hmac(k, v, b"\x00")
        v = _hmac(k, v)


def ecdsa_sign_rfc6979(private_key: ec.EllipticCurvePrivateKey, message: bytes) -> bytes:
    """Return the ASN.1 DER ECDSA-P-256-SHA-256 signature with an RFC 6979 nonce.

    DER, not fixed-width ``r‖s``: ``spec/wire/checkpoint.md`` §5.1 rules on that
    normatively, because C2SP leaves it unspecified for signature type ``0x02`` and an
    opposing expert's verifier must not have to guess.
    """
    private_value = private_key.private_numbers().private_value
    digest = hashlib.sha256(message).digest()
    h = _bits2int(digest)
    for candidate in _rfc6979_nonces(private_value, digest):
        if not 1 <= candidate < _N:
            continue
        r = _scalar_mul(candidate, (_GX, _GY))[0] % _N
        if r == 0:
            continue
        s = pow(candidate, -1, _N) * (h + r * private_value) % _N
        if s == 0:
            continue
        signature = encode_dss_signature(r, s)
        # Never emit a signature we have not verified with an independent implementation.
        private_key.public_key().verify(signature, message, ec.ECDSA(hashes.SHA256()))
        return signature
    raise AssertionError("unreachable: RFC 6979 always terminates")  # pragma: no cover


def _assert_matches_library(private_key: ec.EllipticCurvePrivateKey) -> str:
    """Cross-examine the local RFC 6979 against ``cryptography``'s, when it has one."""
    probe = b"trappoint reference-ledger RFC 6979 cross-check"
    mine = ecdsa_sign_rfc6979(private_key, probe)
    try:
        theirs = private_key.sign(
            probe, ec.ECDSA(hashes.SHA256(), deterministic_signing=True)
        )
    except Exception as exc:  # noqa: BLE001 — any failure means "not available here"
        return f"unavailable ({type(exc).__name__}); local RFC 6979 unconfirmed this run"
    if mine != theirs:
        raise SystemExit(
            "RFC 6979 disagreement: the local deterministic nonce and OpenSSL's differ. "
            "Refusing to emit a bundle whose signatures two conforming implementations "
            "would not both produce."
        )
    return "confirmed against OpenSSL deterministic ECDSA"


# =======================================================================================
# A minimal DER writer — enough for RFC 3161, and no more
# =======================================================================================
#
# CU-8 rules that RFC 3161 verification is hand-rolled inside `trappoint-verify` because
# `cryptography` has no CMS SignedData verification API and `asn1crypto` would break the
# dependency floor. The MINTING side inherits the same constraint for the same reason, and
# it is a smaller problem: writing DER is decidable, reading attacker-controlled DER is not.


def _der(tag: int, content: bytes) -> bytes:
    length = len(content)
    if length < 0x80:
        header = bytes((tag, length))
    else:
        encoded = length.to_bytes((length.bit_length() + 7) // 8, "big")
        header = bytes((tag, 0x80 | len(encoded))) + encoded
    return header + content


def der_int(value: int) -> bytes:
    if value < 0:
        raise ValueError("the fixture emits no negative INTEGERs")
    raw = value.to_bytes(max(1, (value.bit_length() + 7) // 8), "big")
    if raw[0] & 0x80:
        raw = b"\x00" + raw
    return _der(0x02, raw)


def der_oid(dotted: str) -> bytes:
    parts = [int(p) for p in dotted.split(".")]
    body = bytearray([parts[0] * 40 + parts[1]])
    for part in parts[2:]:
        chunk = [part & 0x7F]
        part >>= 7
        while part:
            chunk.append((part & 0x7F) | 0x80)
            part >>= 7
        body.extend(reversed(chunk))
    return _der(0x06, bytes(body))


def der_octet(data: bytes) -> bytes:
    return _der(0x04, data)


def der_null() -> bytes:
    return b"\x05\x00"


def der_seq(*items: bytes) -> bytes:
    return _der(0x30, b"".join(items))


def der_set(*items: bytes) -> bytes:
    """DER SET OF: members sorted by their own encoding (X.690 §11.6)."""
    return _der(0x31, b"".join(sorted(items)))


def der_explicit(tag_number: int, content: bytes) -> bytes:
    return _der(0xA0 | tag_number, content)


def der_implicit_set(tag_number: int, items: Sequence[bytes]) -> bytes:
    return _der(0xA0 | tag_number, b"".join(sorted(items)))


def der_gentime(when: dt.datetime) -> bytes:
    return _der(0x18, when.strftime("%Y%m%d%H%M%SZ").encode("ascii"))


def der_utctime(when: dt.datetime) -> bytes:
    return _der(0x17, when.strftime("%y%m%d%H%M%SZ").encode("ascii"))


OID_SHA256: Final = "2.16.840.1.101.3.4.2.1"
OID_RSA_ENCRYPTION: Final = "1.2.840.113549.1.1.1"
OID_SIGNED_DATA: Final = "1.2.840.113549.1.7.2"
OID_CT_TST_INFO: Final = "1.2.840.113549.1.9.16.1.4"
OID_ATTR_CONTENT_TYPE: Final = "1.2.840.113549.1.9.3"
OID_ATTR_MESSAGE_DIGEST: Final = "1.2.840.113549.1.9.4"
OID_ATTR_SIGNING_TIME: Final = "1.2.840.113549.1.9.5"

#: A private-arc policy OID. It names a timestamp policy that exists only in this fixture;
#: a real deployment carries the policy OID of the authority that actually issued the token.
OID_FIXTURE_TSA_POLICY: Final = "1.3.6.1.4.1.57264.999.1"

_ALG_SHA256: Final = der_seq(der_oid(OID_SHA256), der_null())
_ALG_RSA: Final = der_seq(der_oid(OID_RSA_ENCRYPTION), der_null())


# =======================================================================================
# The locally-minted timestamp authority
# =======================================================================================


@dataclass(frozen=True)
class TimestampAuthority:
    """A two-certificate RFC 3161 authority whose whole existence is this fixture."""

    name: str
    root: x509.Certificate
    leaf: x509.Certificate
    leaf_key: rsa.RSAPrivateKey
    _serial: list[int] = field(default_factory=lambda: [0x5A11_0001])

    def next_serial(self) -> int:
        self._serial[0] += 1
        return self._serial[0]

    def token(self, message: bytes, gen_time: dt.datetime) -> bytes:
        """Return a DER ``TimeStampToken`` (CMS ``SignedData``) over ``message``."""
        imprint = hashlib.sha256(message).digest()
        tst_info = der_seq(
            der_int(1),
            der_oid(OID_FIXTURE_TSA_POLICY),
            der_seq(_ALG_SHA256, der_octet(imprint)),
            der_int(self.next_serial()),
            der_gentime(gen_time),
        )
        signed_attrs = [
            der_seq(der_oid(OID_ATTR_CONTENT_TYPE), der_set(der_oid(OID_CT_TST_INFO))),
            der_seq(
                der_oid(OID_ATTR_MESSAGE_DIGEST),
                der_set(der_octet(hashlib.sha256(tst_info).digest())),
            ),
            der_seq(der_oid(OID_ATTR_SIGNING_TIME), der_set(der_utctime(gen_time))),
        ]
        # RFC 5652 §5.4: the signature covers the attributes DER-encoded as a SET OF,
        # never as the [0] IMPLICIT tag under which they travel.
        signature = self.leaf_key.sign(
            der_set(*signed_attrs), padding.PKCS1v15(), hashes.SHA256()
        )
        signer_info = der_seq(
            der_int(1),
            der_seq(
                self.leaf.issuer.public_bytes(), der_int(self.leaf.serial_number)
            ),
            _ALG_SHA256,
            der_implicit_set(0, signed_attrs),
            _ALG_RSA,
            der_octet(signature),
        )
        signed_data = der_seq(
            der_int(3),
            der_set(_ALG_SHA256),
            der_seq(der_oid(OID_CT_TST_INFO), der_explicit(0, der_octet(tst_info))),
            der_explicit(
                0,
                self.leaf.public_bytes(serialization.Encoding.DER)
                + self.root.public_bytes(serialization.Encoding.DER),
            ),
            der_set(signer_info),
        )
        token = der_seq(der_oid(OID_SIGNED_DATA), der_explicit(0, signed_data))
        _assert_token_reads_back(token, imprint, gen_time, self.leaf)
        return token


def _assert_token_reads_back(
    token: bytes, imprint: bytes, gen_time: dt.datetime, leaf: x509.Certificate
) -> None:
    """Refuse to emit a token whose two load-bearing fields cannot be read back out.

    A minted token nobody has parsed is a blob. This walks the DER for the SHA-256
    ``messageImprint`` and the ``genTime`` string and checks both, so a mistake in the
    writer above fails here rather than in somebody else's verifier six weeks from now.
    """
    if imprint not in token:
        raise SystemExit("minted TSA token does not carry its own messageImprint")
    stamp = gen_time.strftime("%Y%m%d%H%M%SZ").encode("ascii")
    if stamp not in token:
        raise SystemExit("minted TSA token does not carry its own genTime")
    if leaf.public_bytes(serialization.Encoding.DER) not in token:
        raise SystemExit("minted TSA token does not carry the signing certificate")


def build_timestamp_authority(
    root_key: rsa.RSAPrivateKey, leaf_key: rsa.RSAPrivateKey
) -> TimestampAuthority:
    """Mint the fixture's root CA and timestamping certificate, deterministically.

    RSASSA-PKCS#1 v1.5 is deterministic, the serial numbers are fixed and the validity
    window is fixed, so ``CertificateBuilder.sign`` produces the same DER on every run.
    """
    not_before = dt.datetime(2026, 1, 1, tzinfo=dt.UTC)
    not_after = dt.datetime(2036, 1, 1, tzinfo=dt.UTC)

    root_name = x509.Name(
        [
            x509.NameAttribute(NameOID.COUNTRY_NAME, "AU"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "MAINLINE reference fixtures"),
            x509.NameAttribute(NameOID.COMMON_NAME, "MAINLINE Reference TSA Root"),
        ]
    )
    leaf_name = x509.Name(
        [
            x509.NameAttribute(NameOID.COUNTRY_NAME, "AU"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "MAINLINE reference fixtures"),
            x509.NameAttribute(NameOID.COMMON_NAME, "MAINLINE Reference TSA"),
        ]
    )

    root = (
        x509.CertificateBuilder()
        .subject_name(root_name)
        .issuer_name(root_name)
        .public_key(root_key.public_key())
        .serial_number(0x5A11_0100)
        .not_valid_before(not_before)
        .not_valid_after(not_after)
        .add_extension(x509.BasicConstraints(ca=True, path_length=1), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=True,
                crl_sign=True,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .sign(root_key, hashes.SHA256())
    )
    leaf = (
        x509.CertificateBuilder()
        .subject_name(leaf_name)
        .issuer_name(root_name)
        .public_key(leaf_key.public_key())
        .serial_number(0x5A11_0101)
        .not_valid_before(not_before)
        .not_valid_after(not_after)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=True,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        # RFC 3161 §2.3: the timestamping EKU MUST be present and MUST be critical, and it
        # MUST be the only EKU. A verifier that does not enforce that will accept a TLS
        # certificate as a timestamp, which is how a "trusted" chain becomes worthless.
        .add_extension(
            x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.TIME_STAMPING]),
            critical=True,
        )
        .sign(root_key, hashes.SHA256())
    )
    return TimestampAuthority(
        name="reference-tsa.mainline.example", root=root, leaf=leaf, leaf_key=leaf_key
    )


# =======================================================================================
# C2SP signed notes
# =======================================================================================


def key_id(public_key: ec.EllipticCurvePublicKey) -> bytes:
    """``SHA-256(DER SPKI)[:4]`` — the ``0x02`` rule, which is NOT the Ed25519 rule.

    ``spec/wire/checkpoint.md`` §5.1: for type ``0x01`` the key ID is
    ``SHA-256(name ‖ 0x0A ‖ 0x01 ‖ pubkey)[:4]``; for ``0x02`` it is the truncated
    SHA-256 of the DER SPKI alone. Deriving it the Ed25519 way produces a note that
    "verifies" against nothing.
    """
    spki = public_key.public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    return hashlib.sha256(spki).digest()[:4]


def vkey(name: str, public_key: ec.EllipticCurvePublicKey) -> str:
    """The C2SP verifier-key form: ``<name>+<8 hex key id>+<base64(0x02 ‖ DER SPKI)>``."""
    spki = public_key.public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    return f"{name}+{key_id(public_key).hex()}+{base64.b64encode(bytes([0x02]) + spki).decode()}"


def note_text(tree_size: int, root: bytes, extensions: Sequence[tuple[str, str]]) -> str:
    """Assemble the signed bytes: origin, size, root, then extension lines, then ``\\n``."""
    lines = [ORIGIN, str(tree_size), base64.b64encode(root).decode("ascii")]
    lines.extend(f"{name}: {value}" for name, value in extensions)
    return "\n".join(lines) + "\n"


def signature_line(name: str, public_key: ec.EllipticCurvePublicKey, sig: bytes) -> str:
    """``U+2014 U+0020 <name> U+0020 base64(key id ‖ signature)``.

    The em dash is U+2014. A hyphen or U+2013 produces a note that parses as one long text
    with no signatures, which then fails verification for the wrong reason — the single
    most common implementation error in the format.
    """
    return f"— {name} {base64.b64encode(key_id(public_key) + sig).decode('ascii')}"


# =======================================================================================
# The fixture log's content
# =======================================================================================


def ident(label: str) -> str:
    """A stable UUID for a stable label. Not random, and not a hash of the clock."""
    return str(uuid.uuid5(IDENTITY_NAMESPACE, label))


def stamp(offset_seconds: int, millis: int = 0) -> str:
    """RFC 3339 UTC with milliseconds and a literal ``Z``, as every wire format requires."""
    moment = ORIGIN_INSTANT + dt.timedelta(seconds=offset_seconds, milliseconds=millis)
    return moment.strftime("%Y-%m-%dT%H:%M:%S.") + f"{moment.microsecond // 1000:03d}Z"


def commit_hex(label: str) -> str:
    """A 32-byte commit identifier for a clause version, derived from a stable label."""
    return hashlib.sha256(f"commit/{label}".encode()).hexdigest()


#: The gate's own source, as ``pg_get_triggerdef()`` renders it on CockroachDB v26.2.5.
#:
#: GT-05 IS ANSWERED, and the answer is yes. Probed against CockroachDB CCL v26.2.5 on
#: 2026-08-10: ``SELECT pg_get_triggerdef(oid) FROM pg_trigger WHERE NOT tgisinternal``
#: returns a fully-qualified, type-annotated ``CREATE TRIGGER`` statement. Check 11 does
#: NOT need the ``SHOW CREATE TABLE`` fallback and does not report ``PASS(coarse)``.
#:
#: Two properties of the returned text a verifier must not be surprised by, both visible
#: below: the object names are qualified with the DATABASE as well as the schema, and
#: literals carry CockroachDB's ``:::TYPE`` annotations. Both mean the attestation text is
#: a property of the cluster the migration ran on, so an attestation is compared against
#: the text captured at migration time — never against the migration file.
GATE_TRIGGERDEF: Final = (
    "CREATE TRIGGER permit_merge_gate BEFORE UPDATE ON mainline_ref.mainline.permit "
    "FOR EACH ROW WHEN ((new).state = 'merged':::mainline.subject_state) AND "
    "((old).state != 'merged':::mainline.subject_state) "
    "EXECUTE FUNCTION mainline_ref.mainline.fn_permit_merge_gate()"
)

CLOSURE_TRIGGERDEF: Final = (
    "CREATE TRIGGER append_only BEFORE UPDATE OR DELETE ON "
    "mainline_ref.mainline.clause_blame_closure FOR EACH ROW "
    "EXECUTE FUNCTION mainline_ref.mainline.fn_refuse_mutation()"
)

#: S9's defence, attested for the same reason as the gate: ``chain_digest`` is computed
#: server-side but its INPUT is supplied by the inserter, so the chain is only a chain while
#: this trigger is running. Attesting it is what lets check 11 notice that it stopped.
CHAIN_TRIGGERDEF: Final = (
    "CREATE TRIGGER permit_event_chain BEFORE INSERT ON "
    "mainline_ref.mainline.permit_event FOR EACH ROW "
    "EXECUTE FUNCTION mainline_ref.mainline.fn_permit_event_chain()"
)

#: (migration, object, kind, definition) for every mechanism the ledger attests to itself.
ATTESTED_MECHANISMS: Final = (
    (
        "0130_trg_permit_merge_gate",
        "mainline.permit_merge_gate",
        "trigger",
        GATE_TRIGGERDEF,
    ),
    (
        "0128j_trg_refuse_mutation_clause_blame_closure",
        "mainline.clause_blame_closure.append_only",
        "trigger",
        CLOSURE_TRIGGERDEF,
    ),
    (
        "0125_trg_permit_event_chain",
        "mainline.permit_event.permit_event_chain",
        "trigger",
        CHAIN_TRIGGERDEF,
    ),
)

PERMIT_COUNT: Final = 8


@dataclass
class Leaf:
    seq: int
    entry_id: str
    entry_kind: str
    subject_id: str
    payload: dict[str, Any]
    canon_bytes: bytes
    leaf_hash: bytes
    actor: str
    actor_kind: str
    recorded_at: str
    batch_id: str
    prev_link_hash: bytes = b""
    link_hash: bytes = b""


def _entry(
    seq: int,
    entry_kind: str,
    subject_label: str,
    payload: dict[str, Any],
    actor: str,
    actor_kind: str,
    offset: int,
) -> Leaf:
    canon = canonicalise_payload(payload)
    return Leaf(
        seq=seq,
        entry_id=ident(f"entry/{seq}"),
        entry_kind=entry_kind,
        subject_id=ident(subject_label),
        payload=payload,
        canon_bytes=canon,
        leaf_hash=hash_leaf(canon),
        actor=actor,
        actor_kind=actor_kind,
        recorded_at=stamp(offset, millis=(seq * 37) % 1000),
        batch_id=ident(f"batch/{seq // 12}"),
    )


def build_leaves() -> list[Leaf]:
    """Seventy-two leaves across eight entry kinds — one shift on one site.

    The narrative is deliberately ordinary: the schema attests itself, then eight permits
    each run recall → two blocking checks → two closure generations → two dispositions →
    merge, with the custodian patrol and the silence ledger interleaved. Ordinary is the
    point. Evidence Act 1995 (Cth) s.69 turns on a record made in the ordinary course of
    business, and a fixture that shows only incidents is a fixture of the wrong thing.
    """
    leaves: list[Leaf] = []
    seq = 0
    offset = 0

    for migration, obj, kind, definition in ATTESTED_MECHANISMS:
        leaves.append(
            _entry(
                seq,
                "schema",
                f"migration/{migration}",
                {
                    "applied_at": stamp(offset),
                    "definition_sha256": hashlib.sha256(
                        definition.encode("utf-8")
                    ).hexdigest(),
                    "entry_kind": "schema",
                    "kind": kind,
                    "migration": migration,
                    "object": obj,
                    "site_code": SITE_CODE,
                    "source": "pg_get_triggerdef",
                },
                actor="svc_migrator",
                actor_kind="service",
                offset=offset,
            )
        )
        seq += 1
        offset += 11

    for permit_index in range(PERMIT_COUNT):
        permit_id = ident(f"permit/{permit_index}")
        clause_uuid = ident(f"clause/{permit_index}")
        as_of = commit_hex(f"clause/{permit_index}")
        signer = f"auth0|{permit_index:04x}"

        offset += 47
        leaves.append(
            _entry(
                seq,
                "recall",
                f"permit/{permit_index}",
                {
                    "advisory": 9 + permit_index,
                    "blocking": 2,
                    "candidates": 30 + permit_index * 3,
                    "entry_kind": "recall",
                    "permit_id": permit_id,
                    "silenced": 19 + permit_index * 2,
                    "site_code": SITE_CODE,
                },
                actor="agent_recaller",
                actor_kind="agent",
                offset=offset,
            )
        )
        seq += 1

        for check_index in range(2):
            offset += 13
            severity = 4 + check_index
            leaves.append(
                _entry(
                    seq,
                    "check_open",
                    f"check/{permit_index}/{check_index}",
                    {
                        "check_id": ident(f"check/{permit_index}/{check_index}"),
                        "clause_uuid": clause_uuid,
                        "entry_kind": "check_open",
                        "severity": severity,
                        "site_code": SITE_CODE,
                        "virulence": "blood_major" if severity == 4 else "blood_fatal",
                    },
                    actor="agent_projector",
                    actor_kind="agent",
                    offset=offset,
                )
            )
            seq += 1

        for generation in (1, 2):
            offset += 7
            leaves.append(
                _entry(
                    seq,
                    "closure",
                    f"clause/{permit_index}",
                    {
                        "ancestor_count": 17 + permit_index + generation * 5,
                        "as_of_commit": as_of,
                        "clause_uuid": clause_uuid,
                        "closure_gen": generation,
                        "entry_kind": "closure",
                        "max_severity": 3 + generation,
                        "site_code": SITE_CODE,
                        "truncated": False,
                    },
                    actor="agent_projector",
                    actor_kind="agent",
                    offset=offset,
                )
            )
            seq += 1

        for check_index in range(2):
            offset += 29
            leaves.append(
                _entry(
                    seq,
                    "disposition",
                    f"check/{permit_index}/{check_index}",
                    {
                        "check_id": ident(f"check/{permit_index}/{check_index}"),
                        "disposition_kind": "controlled" if check_index == 0 else "carried",
                        "entry_kind": "disposition",
                        "issued_at": stamp(offset),
                        "signer_rank": 4,
                        "signer_sub": signer,
                        "site_code": SITE_CODE,
                    },
                    actor=signer,
                    actor_kind="human",
                    offset=offset,
                )
            )
            seq += 1

        offset += 19
        leaves.append(
            _entry(
                seq,
                "merge",
                f"permit/{permit_index}",
                {
                    "entry_kind": "merge",
                    "merged_at": stamp(offset),
                    "open_blocking": 0,
                    "permit_id": permit_id,
                    "site_code": SITE_CODE,
                },
                actor="svc_gate",
                actor_kind="service",
                offset=offset,
            )
        )
        seq += 1

        if permit_index % 2 == 1:
            offset += 5
            leaves.append(
                _entry(
                    seq,
                    "custodian_attestation",
                    f"patrol/{permit_index}",
                    {
                        "entry_kind": "custodian_attestation",
                        "finding_count": 0,
                        "observed_at": stamp(offset),
                        "site_code": SITE_CODE,
                        "subject": "schema_fingerprint",
                    },
                    actor="agent_patroller",
                    actor_kind="agent",
                    offset=offset,
                )
            )
            seq += 1

        if permit_index in (3, 6):
            offset += 3
            leaves.append(
                _entry(
                    seq,
                    "silence",
                    f"permit/{permit_index}",
                    {
                        "entry_kind": "silence",
                        "logged_at": stamp(offset),
                        "permit_id": permit_id,
                        "reason": "below_admission_threshold",
                        "site_code": SITE_CODE,
                        "suppressed": 4,
                    },
                    actor="agent_recaller",
                    actor_kind="agent",
                    offset=offset,
                )
            )
            seq += 1

    if CHECKPOINT_SIZES[-1] != len(leaves):
        raise SystemExit(
            f"the last checkpoint must commit to the whole log: CHECKPOINT_SIZES ends at "
            f"{CHECKPOINT_SIZES[-1]} and the log holds {len(leaves)} leaves. A bundle whose "
            "newest checkpoint predates its own newest leaf is a bundle with an unproved "
            "tail, and check 16 would say so."
        )
    links = chain_links([leaf.leaf_hash for leaf in leaves], head=GENESIS_LINK_HASH)
    for leaf, (previous, current) in zip(leaves, links, strict=True):
        leaf.prev_link_hash = previous
        leaf.link_hash = current
    return leaves


# =======================================================================================
# Assembling the bundle
# =======================================================================================


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def build_checkpoints(
    leaf_hashes: Sequence[bytes],
    log_key: ec.EllipticCurvePrivateKey,
    witness_key: ec.EllipticCurvePrivateKey,
    tsa: TimestampAuthority,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Sign one checkpoint per size in :data:`CHECKPOINT_SIZES`; cosign the last two."""
    canon_hex = canon_src_sha256().hex()
    checkpoints: list[dict[str, Any]] = []
    cosignatures: list[dict[str, Any]] = []

    for index, size in enumerate(CHECKPOINT_SIZES):
        issue_offset = 90 + index * CHECKPOINT_CADENCE_S
        issued = ORIGIN_INSTANT + dt.timedelta(seconds=issue_offset)
        issued_epoch = int(issued.timestamp())

        # The drand round is chosen so that its arithmetic round time is <= the moment the
        # checkpoint was issued and therefore <= the TSA genTime. A checkpoint quoting a
        # round whose time falls AFTER its timestamp is attack A9, and check 6 recomputes
        # exactly this expression: 1692803367 + (round - 1) * 3.
        drand_round = (issued_epoch - DRAND_GENESIS) // DRAND_PERIOD_S + 1
        drand_value = hashlib.sha256(f"drand/{drand_round}".encode()).hexdigest()
        nist_pulse = 29255654 + index
        nist_value = (
            hashlib.sha512(f"nist/{nist_pulse}".encode()).hexdigest()
        )

        root = merkle_tree_hash(list(leaf_hashes[:size])) if size else EMPTY_ROOT
        text = note_text(
            size,
            root,
            (
                ("canon", f"{CANON_VERSION} {canon_hex}"),
                (
                    "drand",
                    f"{DRAND_CHAIN_HASH} {drand_round} {drand_value}",
                ),
                ("nist", f"2.0 {NIST_CHAIN_INDEX}.{nist_pulse} {nist_value}"),
            ),
        )
        raw = text.encode("utf-8")
        lines = [signature_line(ORIGIN, log_key.public_key(), ecdsa_sign_rfc6979(log_key, raw))]

        # The last two checkpoints carry a witness line. Earlier ones deliberately do not:
        # a bundle in which every checkpoint is cosigned never exercises `unwitnessed debt`,
        # and a verifier that has only ever seen the happy case has not been tested.
        if index >= len(CHECKPOINT_SIZES) - 2:
            witness_sig = ecdsa_sign_rfc6979(witness_key, raw)
            line = signature_line(WITNESS_ID, witness_key.public_key(), witness_sig)
            lines.append(line)
            cosignatures.append(
                {
                    "adverse": False,
                    "received_at": stamp(issue_offset + 4),
                    "sig_line": line,
                    "tree_size": size,
                    "trust_domain": "operator",
                    "witness_id": WITNESS_ID,
                    "witness_key": vkey(WITNESS_ID, witness_key.public_key()),
                }
            )

        note = text + "\n" + "\n".join(lines) + "\n"
        gen_time = (issued + dt.timedelta(seconds=2)).replace(microsecond=0)
        token = tsa.token(raw, gen_time)

        checkpoints.append(
            {
                "log_key": vkey(ORIGIN, log_key.public_key()),
                "note": note,
                "observed_at": stamp(issue_offset + 2),
                "root_hex": root.hex(),
                "tree_size": size,
                "tsa_tokens": [{"issuer": tsa.name, "token_b64": _b64(token)}],
            }
        )
    return checkpoints, cosignatures


def build_receipts(
    leaves: Sequence[Leaf], log_key: ec.EllipticCurvePrivateKey
) -> list[dict[str, Any]]:
    """One Signed Disposition Receipt per ``disposition`` leaf, all of them covered.

    The reference bundle contains no orphan receipt on purpose: it is the *conforming*
    input, and a conforming input must verify with zero findings. ``A14`` — the orphan —
    is executed by the nemesis harness against a working copy, which is where an attack
    belongs.
    """
    receipts: list[dict[str, Any]] = []
    for leaf in leaves:
        if leaf.entry_kind != "disposition":
            continue
        receipt = {
            "entry_id": leaf.entry_id,
            "issued_at": leaf.recorded_at,
            "leaf_hash": leaf.leaf_hash.hex(),
            "mmd_seconds": MMD_SECONDS,
            "origin": ORIGIN,
            "payload_ver": CANON_VERSION,
            "site_code": SITE_CODE,
            "typ": "MAINLINE-SDR-v1",
        }
        signed = canonicalise_payload(receipt)
        receipts.append(
            {
                "key_id": key_id(log_key.public_key()).hex(),
                "receipt": receipt,
                "sdr_version": 1,
                "sig": _b64(ecdsa_sign_rfc6979(log_key, signed)),
            }
        )
    return receipts


def build_webauthn(
    leaves: Sequence[Leaf], credential_key: ec.EllipticCurvePrivateKey
) -> list[dict[str, Any]]:
    """One re-verifiable WebAuthn assertion over a reconstructible challenge.

    Property 2 of check 12 is the one that matters: the challenge **reconstructs** from
    ``challenge_inputs``, so *"he signed a summary, not the warning"* is refuted by
    arithmetic rather than by our word. ``receipt_digest`` here is the RFC 6962 Merkle Tree
    Hash over the leaf hashes of the exact entries that were rendered to the signer — the
    two blocking checks the console put in front of them — so the digest names the content,
    not a page.

    The concatenation is framed explicitly in ``challenge_framing`` inside the bundle.
    ``spec/wire/evidence-bundle.md`` §11 writes the challenge as a bare ``‖`` of mixed
    types, which is ambiguous for exactly the reason ``receipt.md`` §2 rejects a bare
    concatenation; naming the framing in a member a v1.0 verifier is required to ignore
    costs nothing and removes the guess.
    """
    rendered = [leaf for leaf in leaves if leaf.entry_kind == "check_open"][:2]
    disposition = next(leaf for leaf in leaves if leaf.entry_kind == "disposition")
    receipt_digest = merkle_tree_hash([leaf.leaf_hash for leaf in rendered])

    check_id = str(disposition.payload["check_id"])
    defeater_code = "D-114"
    rationale = (
        "Isolation is not available on the live main; the carried disposition names the "
        "same defeater and the same predicate, and the predicate is still true."
    )
    rationale_sha256 = hashlib.sha256(rationale.encode("utf-8")).digest()
    disposition_kind = str(disposition.payload["disposition_kind"])
    gate_epoch = 7

    challenge = hashlib.sha256(
        receipt_digest
        + check_id.encode("utf-8")
        + defeater_code.encode("utf-8")
        + rationale_sha256
        + disposition_kind.encode("utf-8")
        + str(gate_epoch).encode("ascii")
    ).digest()

    client_data = json.dumps(
        {
            "type": "webauthn.get",
            "challenge": _b64url(challenge),
            "origin": WEBAUTHN_ORIGIN,
            "crossOrigin": False,
        },
        separators=(",", ":"),
    ).encode("utf-8")

    sign_count = 42
    authenticator_data = (
        hashlib.sha256(WEBAUTHN_RP_ID.encode("utf-8")).digest()
        + bytes([0x05])  # UP | UV — a person authenticated, not merely a token present
        + sign_count.to_bytes(4, "big")
    )
    signature = ecdsa_sign_rfc6979(
        credential_key, authenticator_data + hashlib.sha256(client_data).digest()
    )

    numbers = credential_key.public_key().public_numbers()
    cose_key = (
        b"\xa5"
        b"\x01\x02"  # kty: EC2
        b"\x03\x26"  # alg: ES256 (-7)
        b"\x20\x01"  # crv: P-256
        b"\x21\x58\x20" + numbers.x.to_bytes(32, "big") + b"\x22\x58\x20"
        + numbers.y.to_bytes(32, "big")
    )

    return [
        {
            "authenticator_data_b64": _b64(authenticator_data),
            "challenge_inputs": {
                "challenge_framing": (
                    "sha256(receipt_digest_bytes || utf8(check_id) || utf8(defeater_code) "
                    "|| rationale_sha256_bytes || utf8(disposition_kind) || "
                    "ascii(decimal gate_epoch))"
                ),
                "check_id": check_id,
                "defeater_code": defeater_code,
                "disposition_kind": disposition_kind,
                "gate_epoch": gate_epoch,
                "rationale_sha256_hex": rationale_sha256.hex(),
                "receipt_digest_hex": receipt_digest.hex(),
            },
            "client_data_json_b64": _b64(client_data),
            "cose_public_key_b64": _b64(cose_key),
            "credential_id_b64": _b64(hashlib.sha256(b"reference-credential").digest()),
            "disposition_id": disposition.subject_id,
            "signature_b64": _b64(signature),
            "sign_count": sign_count,
            "uv_required": True,
        }
    ]


def build_bundle(
    log_key: ec.EllipticCurvePrivateKey,
    witness_key: ec.EllipticCurvePrivateKey,
    webauthn_key: ec.EllipticCurvePrivateKey,
    tsa: TimestampAuthority,
) -> dict[str, Any]:
    leaves = build_leaves()
    leaf_hashes = [leaf.leaf_hash for leaf in leaves]
    size = len(leaves)
    root = merkle_tree_hash(leaf_hashes)

    checkpoints, cosignatures = build_checkpoints(leaf_hashes, log_key, witness_key, tsa)

    consistency: list[dict[str, Any]] = []
    for earlier, later in zip(CHECKPOINT_SIZES, CHECKPOINT_SIZES[1:], strict=False):
        # RFC 6962 §2.1.4: the empty tree is a prefix of every tree, so the 0 -> n proof is
        # the empty path. `consistency_proof_ranges` refuses first_size = 0 rather than
        # returning [], which is the right refusal for a caller that did not mean it — so
        # the one legitimate case is spelled out here instead of hidden in the library.
        path = [] if earlier == 0 else consistency_proof(leaf_hashes[:later], earlier, later)
        earlier_root = merkle_tree_hash(leaf_hashes[:earlier]) if earlier else EMPTY_ROOT
        later_root = merkle_tree_hash(leaf_hashes[:later]) if later else EMPTY_ROOT
        if not verify_consistency(earlier, earlier_root, later, later_root, path):
            raise SystemExit(f"consistency proof {earlier}->{later} does not verify")
        consistency.append(
            {"from_size": earlier, "path_hex": [h.hex() for h in path], "to_size": later}
        )

    inclusion: list[dict[str, Any]] = []
    for leaf in leaves:
        path = inclusion_proof(leaf_hashes, leaf.seq, size)
        if not verify_inclusion(leaf.leaf_hash, leaf.seq, size, path, root):
            raise SystemExit(f"inclusion proof for seq {leaf.seq} does not verify")
        inclusion.append(
            {"path_hex": [h.hex() for h in path], "seq": leaf.seq, "tree_size": size}
        )

    by_object = {obj: definition for _, obj, _, definition in ATTESTED_MECHANISMS}
    schema_attestations = []
    for leaf in leaves:
        if leaf.entry_kind != "schema":
            continue
        definition = by_object[str(leaf.payload["object"])]
        schema_attestations.append(
            {
                "captured_at": leaf.payload["applied_at"],
                "definition": definition,
                "definition_sha256_hex": hashlib.sha256(
                    definition.encode("utf-8")
                ).hexdigest(),
                "kind": leaf.payload["kind"],
                "leaf_seq": leaf.seq,
                "migration": leaf.payload["migration"],
                "object": leaf.payload["object"],
                "source": "pg_get_triggerdef",
            }
        )

    closure_generations = [
        {
            "ancestor_count": leaf.payload["ancestor_count"],
            "as_of_commit": leaf.payload["as_of_commit"],
            "clause_uuid": leaf.payload["clause_uuid"],
            "closure_gen": leaf.payload["closure_gen"],
            "leaf_seq": leaf.seq,
            "max_severity": leaf.payload["max_severity"],
            "truncated": leaf.payload["truncated"],
        }
        for leaf in leaves
        if leaf.entry_kind == "closure"
    ]

    archive_objects = []
    for entry in checkpoints:
        tree_size = int(entry["tree_size"])
        key = f"checkpoints/{SITE_CODE}/{tree_size:06d}.note"
        version_id = _b64(hashlib.sha256(f"s3-version/{key}".encode()).digest()[:24])
        archive_objects.append(
            {
                "etag_hex": hashlib.md5(  # noqa: S324 — S3 ETag is MD5 by definition
                    entry["note"].encode("utf-8"), usedforsecurity=False
                ).hexdigest(),
                "key": key,
                "last_modified": entry["observed_at"],
                "object_lock_mode": "COMPLIANCE",
                "retain_until": "2033-08-07T02:14:07.000Z",
                "tree_size": tree_size,
                "version_id": version_id,
            }
        )

    return {
        "archive": {
            "bucket": "mainline-evidence-reference",
            "objects": archive_objects,
            "provenance": (
                "FIXTURE. These are recorded object-lock SHAPES, never a live S3 response. "
                "Check 8 requires --s3 and reports SKIP(offline) without it; offline this "
                "section is a claim by us about our own archive and the report says so."
            ),
        },
        "bundle_version": 1,
        "canon": {"canon_src_sha256": canon_src_sha256().hex(), "payload_ver": CANON_VERSION},
        "checkpoints": checkpoints,
        "closure_generations": closure_generations,
        "consistency_proofs": consistency,
        "generated_at": stamp(90 + (len(CHECKPOINT_SIZES) - 1) * CHECKPOINT_CADENCE_S + 30),
        "generator": GENERATOR,
        "inclusion_proofs": inclusion,
        "leaves": [
            {
                "actor": leaf.actor,
                "actor_kind": leaf.actor_kind,
                "batch_id": leaf.batch_id,
                "canon_bytes_b64": _b64(leaf.canon_bytes),
                "entry_id": leaf.entry_id,
                "entry_kind": leaf.entry_kind,
                "is_sandbox": False,
                "leaf_hash_hex": leaf.leaf_hash.hex(),
                "link_hash_hex": leaf.link_hash.hex(),
                "payload": leaf.payload,
                "payload_ver": CANON_VERSION,
                "prev_link_hash_hex": leaf.prev_link_hash.hex(),
                "recorded_at": leaf.recorded_at,
                "seq": leaf.seq,
                "subject_id": leaf.subject_id,
            }
            for leaf in leaves
        ],
        "notes": (
            "Reference fixture. The log key in evidence/reference-ledger/keys/ is public by "
            "design: this bundle proves the verifier works, not that MAINLINE's production "
            "log is honest. The beacon values are synthetic and arithmetically consistent; "
            "the RFC 3161 tokens come from a timestamp authority minted by generate.py; the "
            "archive metadata is a recorded shape. A record of the preconditions the "
            "database enforced before work was permitted to start."
        ),
        "origin": ORIGIN,
        "receipts": build_receipts(leaves, log_key),
        "schema_attestations": schema_attestations,
        "site_code": SITE_CODE,
        "webauthn_assertions": build_webauthn(leaves, webauthn_key),
        "witness_cosignatures": cosignatures,
    }


# =======================================================================================
# Self-check, manifest, entry point
# =======================================================================================


def self_check(bundle: dict[str, Any]) -> list[str]:
    """Re-derive the bundle's own claims from its own bytes. Emitting an unverified
    fixture would make every downstream green meaningless.

    This is deliberately NOT ``trappoint-verify``: the verifier is a separate artefact
    with a dependency floor to keep, and the reference bundle must be checkable before it
    exists. What runs here is the arithmetic — leaf hashes from carried bytes, the link
    chain, density, sandbox containment, the tree, every proof, and the closure lattice.
    """
    findings: list[str] = []
    leaves = bundle["leaves"]

    previous = GENESIS_LINK_HASH
    for index, leaf in enumerate(leaves):
        canon = base64.b64decode(leaf["canon_bytes_b64"])
        if hash_leaf(canon).hex() != leaf["leaf_hash_hex"]:
            findings.append(f"check 1: leaf {leaf['seq']} hash does not match its bytes")
        if canonicalise_payload(leaf["payload"]) != canon:
            findings.append(f"check 1: leaf {leaf['seq']} payload disagrees with canon_bytes")
        if leaf["seq"] != index:
            findings.append(f"check 9: seq is not dense at position {index}")
        if bytes.fromhex(leaf["prev_link_hash_hex"]) != previous:
            findings.append(f"check 9: link chain breaks at seq {leaf['seq']}")
        previous = hashlib.sha256(previous + bytes.fromhex(leaf["leaf_hash_hex"])).digest()
        if previous.hex() != leaf["link_hash_hex"]:
            findings.append(f"check 9: link_hash is wrong at seq {leaf['seq']}")
        if leaf["is_sandbox"]:
            findings.append(f"check 13: leaf {leaf['seq']} is a sandbox leaf")

    leaf_hashes = [bytes.fromhex(leaf["leaf_hash_hex"]) for leaf in leaves]
    roots = {
        entry["tree_size"]: bytes.fromhex(entry["root_hex"]) for entry in bundle["checkpoints"]
    }
    for size, root in roots.items():
        expected = merkle_tree_hash(leaf_hashes[:size]) if size else EMPTY_ROOT
        if expected != root:
            findings.append(f"check 16: checkpoint at size {size} names the wrong root")

    for proof in bundle["inclusion_proofs"]:
        path = [bytes.fromhex(h) for h in proof["path_hex"]]
        if not verify_inclusion(
            leaf_hashes[proof["seq"]], proof["seq"], proof["tree_size"], path, roots[proof["tree_size"]]
        ):
            findings.append(f"check 2: inclusion proof for seq {proof['seq']} fails")

    for proof in bundle["consistency_proofs"]:
        path = [bytes.fromhex(h) for h in proof["path_hex"]]
        if not verify_consistency(
            proof["from_size"],
            roots[proof["from_size"]],
            proof["to_size"],
            roots[proof["to_size"]],
            path,
        ):
            findings.append(
                f"check 3: consistency {proof['from_size']}->{proof['to_size']} fails"
            )

    seen: dict[tuple[str, str], list[tuple[int, int]]] = {}
    for row in bundle["closure_generations"]:
        seen.setdefault((row["clause_uuid"], row["as_of_commit"]), []).append(
            (row["closure_gen"], row["max_severity"])
        )
    for (clause, commit), rows in seen.items():
        rows.sort()
        if [gen for gen, _ in rows] != list(range(1, len(rows) + 1)):
            findings.append(f"check 14: generations not dense for {clause}@{commit[:8]}")
        severities = [sev for _, sev in rows]
        if any(b < a for a, b in zip(severities, severities[1:], strict=False)):
            findings.append(f"check 14: max_severity decreases for {clause}@{commit[:8]}")

    covered = {leaf["leaf_hash_hex"] for leaf in leaves}
    for envelope in bundle["receipts"]:
        if envelope["receipt"]["leaf_hash"] not in covered:
            findings.append(f"check 15: receipt {envelope['receipt']['entry_id']} is orphaned")

    return findings


def verify_notes(bundle: dict[str, Any]) -> list[str]:
    """Verify every signature line in every checkpoint note against its own vkey."""
    findings: list[str] = []
    for entry in bundle["checkpoints"]:
        note = entry["note"]
        text, _, signatures = note.rpartition("\n\n")
        signed = (text + "\n").encode("utf-8")
        known: dict[str, ec.EllipticCurvePublicKey] = {}
        for candidate in [entry["log_key"], *[c["witness_key"] for c in bundle["witness_cosignatures"]]]:
            name, key_hex, encoded = candidate.split("+", 2)
            blob = base64.b64decode(encoded)
            if blob[0] != 0x02:
                findings.append(f"check 4: {name} is not a type 0x02 key")
                continue
            public = serialization.load_der_public_key(blob[1:])
            if key_id(public).hex() != key_hex:
                findings.append(f"check 4: {name} key id {key_hex} is not SHA-256(SPKI)[:4]")
            known[name] = public
        verified = 0
        for line in signatures.splitlines():
            if not line:
                continue
            if not line.startswith("— "):
                findings.append("check 4: a signature line does not begin with U+2014 U+0020")
                continue
            name, _, encoded = line[2:].rpartition(" ")
            if name not in known:
                continue  # a verifier MUST ignore signature lines whose key it does not know
            blob = base64.b64decode(encoded)
            try:
                known[name].verify(blob[4:], signed, ec.ECDSA(hashes.SHA256()))
            except Exception:  # noqa: BLE001 — any failure is the same finding
                findings.append(f"check 4: signature from {name} does not verify")
            else:
                verified += 1
        if verified == 0:
            findings.append(f"check 4: no known key verified the size-{entry['tree_size']} note")
    return findings


MANIFEST_FILES: Final = (
    "README.md",
    "bundle.json",
    "generate.py",
    "keys/README.md",
    "keys/reference-log.NOT-SECRET.key.pem",
    "keys/reference-tsa-root.NOT-SECRET.key.pem",
    "keys/reference-tsa.NOT-SECRET.key.pem",
    "keys/reference-webauthn.NOT-SECRET.key.pem",
    "keys/reference-witness.NOT-SECRET.key.pem",
)


def write_manifest(directory: Path) -> str:
    """Emit ``MANIFEST.sha256`` in ``sha256sum`` format, over LF-normalised bytes.

    Normalising CRLF to LF before hashing is the same rule ``canon_src_sha256`` obeys and
    for the same reason: without it the manifest fingerprints whether the checkout ran on
    Windows rather than fingerprinting the content, and two honest verifiers disagree.
    """
    lines = []
    for relative in MANIFEST_FILES:
        raw = (directory / relative).read_bytes().replace(b"\r\n", b"\n")
        lines.append(f"{hashlib.sha256(raw).hexdigest()}  {relative}")
    return "\n".join(lines) + "\n"


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))


def load_ec(path: Path) -> ec.EllipticCurvePrivateKey:
    key = serialization.load_pem_private_key(path.read_bytes(), password=None)
    if not isinstance(key, ec.EllipticCurvePrivateKey):  # pragma: no cover
        raise SystemExit(f"{path} is not an EC private key")
    return key


def load_rsa(path: Path) -> rsa.RSAPrivateKey:
    key = serialization.load_pem_private_key(path.read_bytes(), password=None)
    if not isinstance(key, rsa.RSAPrivateKey):  # pragma: no cover
        raise SystemExit(f"{path} is not an RSA private key")
    return key


def generate(out: Path) -> dict[str, Any]:
    log_key = load_ec(LOG_KEY_PEM)
    witness_key = load_ec(WITNESS_KEY_PEM)
    webauthn_key = load_ec(WEBAUTHN_KEY_PEM)
    tsa = build_timestamp_authority(load_rsa(TSA_ROOT_KEY_PEM), load_rsa(TSA_LEAF_KEY_PEM))

    cross_check = _assert_matches_library(log_key)
    print(f"[reference-ledger] RFC 6979 nonce: {cross_check}")

    bundle = build_bundle(log_key, witness_key, webauthn_key, tsa)

    findings = self_check(bundle) + verify_notes(bundle)
    if findings:
        raise SystemExit(
            "the generated bundle does not verify against its own arithmetic:\n  "
            + "\n  ".join(findings)
        )

    out.mkdir(parents=True, exist_ok=True)
    (out / "bundle.json").write_bytes(canonicalise_payload(bundle))
    if out.resolve() != HERE:
        # A bundle regenerated elsewhere still needs the files the manifest names, so a
        # zero-diff comparison compares like with like.
        for relative in MANIFEST_FILES:
            if relative == "bundle.json":
                continue
            target = out / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((HERE / relative).read_bytes())
    write_text(out / "MANIFEST.sha256", write_manifest(out))
    return bundle


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=HERE, help="output directory")
    args = parser.parse_args(argv)

    bundle = generate(args.out)
    leaves = len(bundle["leaves"])
    kinds = sorted({leaf["entry_kind"] for leaf in bundle["leaves"]})
    print(
        f"[reference-ledger] {leaves} leaves across {len(kinds)} entry kinds "
        f"({', '.join(kinds)})"
    )
    print(
        f"[reference-ledger] {len(bundle['checkpoints'])} checkpoints, "
        f"{len(bundle['consistency_proofs'])} consecutive consistency proofs, "
        f"{len(bundle['inclusion_proofs'])} inclusion proofs, "
        f"{len(bundle['receipts'])} receipts"
    )
    print(f"[reference-ledger] wrote {args.out / 'bundle.json'} and MANIFEST.sha256")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
