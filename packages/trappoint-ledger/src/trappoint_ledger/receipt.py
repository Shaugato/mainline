# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The Signed Disposition Receipt: issue it, verify it, and audit its coverage.

An SDR is MAINLINE's analogue of Certificate Transparency's Signed Certificate
Timestamp, and it exists because splitting intake from sequencing buys throughput at the
cost of a Maximum Merge Delay. Ours is 60 seconds. Inside that window a disposition has
been recorded and nothing that left our trust boundary yet covers it.

    **An SDR is a signed promise that a specific leaf will appear in a checkpoint within
    the MMD. A receipt whose leaf never appears is not a missing record — it is
    affirmative, portable proof of log misbehaviour, held by the person we gave it to.**

That inversion is the point. A leaf that quietly never gets sequenced is invisible;
a receipt makes the party who signed the disposition the holder of a signed statement
from us that contradicts our own log.

**The signed bytes are JCS, not a concatenation.** ARCHITECTURE.md §7.2 writes the
receipt as ``Sign_KMS(entry_id ‖ leaf_hash ‖ site ‖ issued_at ‖ MMD)``. A bare
concatenation of variable-length fields is ambiguous — two different field tuples can
produce identical bytes — and an ambiguous signature input is a canonicalisation attack
waiting to be written up. ``spec/wire/receipt.md`` §2 fixes the framing as RFC 8785 JCS,
which is injective, is the framing every leaf already uses, and is verifiable with the
canonicaliser the verifier already vendors. The covered fields are unchanged.

The receipt is signed by **the same KMS key that signs checkpoints for that origin**, so
verifying one needs no key material a verifier does not already hold, and a compromise of
the receipt path is a compromise of the log path rather than a second, weaker one.
"""

from __future__ import annotations

import base64
import re
from collections.abc import Container, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any, Final

from trappoint_jcs.canon_v1 import canonicalise_payload
from trappoint_ledger.note.format import SignatureVerifier
from trappoint_ledger.note.keyid import KEY_ID_BYTES, PublicKey, key_id_hex
from trappoint_ledger.signer import Signer, p256_sha256_verify, public_key_for

__all__ = [
    "MMD_SECONDS",
    "RECEIPT_MEMBERS",
    "SDR_TYP",
    "SDR_VERSION",
    "MalformedReceipt",
    "Receipt",
    "ReceiptEnvelope",
    "ReceiptFinding",
    "ReceiptVerdict",
    "ReceiptVerificationFailed",
    "format_issued_at",
    "issue_receipt",
    "receipt_coverage",
    "verify_receipt",
]

#: Domain separation. Without it, a signature over one JCS object of this shape could be
#: replayed as a signature over another.
SDR_TYP: Final = "MAINLINE-SDR-v1"

#: The envelope version. The envelope is NOT signed; only ``receipt`` is.
SDR_VERSION: Final = 1

#: The Maximum Merge Delay, in seconds. ``spec/wire/receipt.md`` §2.1 fixes it at 60 for
#: v1.0 — it is a *promise*, so it is a constant and not a tunable.
MMD_SECONDS: Final = 60

#: Exactly these members, all required, no others permitted.
RECEIPT_MEMBERS: Final = frozenset(
    {
        "typ",
        "entry_id",
        "leaf_hash",
        "site_code",
        "origin",
        "payload_ver",
        "issued_at",
        "mmd_seconds",
    }
)

_UUID_LOWER: Final = re.compile(r"\A[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\Z")
_LEAF_HASH: Final = re.compile(r"\A[0-9a-f]{64}\Z")
_ISSUED_AT: Final = re.compile(r"\A(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})\.(\d{3})Z\Z")
_KEY_ID_HEX_LEN: Final = KEY_ID_BYTES * 2


class MalformedReceipt(ValueError):
    """A receipt or envelope does not conform to ``spec/wire/receipt.md`` v1.0."""


class ReceiptVerificationFailed(ValueError):
    """A well-formed receipt's signature does not verify against the log key.

    Distinct from :class:`MalformedReceipt`, and the distinction is the whole finding:
    "this is not a receipt" is a transport fault, "this receipt does not verify" is an
    accusation that someone forged our signature.
    """


def format_issued_at(when: datetime) -> str:
    """Render an instant as the receipt's ``issued_at``: RFC 3339 UTC, milliseconds, ``Z``.

    Args:
        when: A timezone-aware instant. Converted to UTC and truncated — never rounded —
            to milliseconds, so the value is always at or before the real instant and the
            MMD deadline it implies is never later than the truth.

    Returns:
        e.g. ``2026-08-07T02:11:42.310Z``.

    Raises:
        ValueError: If ``when`` is naive. A naive datetime in an evidentiary payload is
            an unanswerable question in cross-examination.
    """
    if when.tzinfo is None:
        raise ValueError("issued_at must be built from a timezone-aware instant")
    utc = when.astimezone(UTC)
    return f"{utc:%Y-%m-%dT%H:%M:%S}.{utc.microsecond // 1000:03d}Z"


def _parse_issued_at(value: str) -> datetime:
    match = _ISSUED_AT.match(value)
    if match is None:
        raise MalformedReceipt(
            f"issued_at {value!r} is not RFC 3339 UTC with milliseconds and a literal 'Z' "
            "(spec/wire/receipt.md §2.1)"
        )
    year, month, day, hour, minute, second, millis = (int(g) for g in match.groups())
    try:
        return datetime(year, month, day, hour, minute, second, millis * 1000, tzinfo=UTC)
    except ValueError as exc:
        # The regex fixes the SHAPE; only the calendar can refuse 2026-18-07 or a leap
        # day that is not one. A ValueError escaping from here would surface as a crash
        # in a verifier rather than as a refusal of the receipt.
        raise MalformedReceipt(f"issued_at {value!r} is not a real instant: {exc}") from exc


@dataclass(frozen=True, slots=True)
class Receipt:
    """The eight-member signed object of ``spec/wire/receipt.md`` §2.1."""

    entry_id: str
    """The ``ledger_intake.entry_id`` UUID, lowercase."""

    leaf_hash: str
    """64 lowercase hex characters: ``SHA-256(0x00 ‖ canon_bytes)``."""

    site_code: str
    """The site whose log this leaf belongs to."""

    origin: str
    """The log origin — identical to line 1 of the checkpoint note. This is what binds
    the receipt to **which** log must contain it, and it is why a sandbox receipt
    presented against an evidentiary bundle fails on ``origin`` rather than quietly
    passing (attack A12)."""

    payload_ver: int
    """The canonicaliser version used for ``canon_bytes``."""

    issued_at: str
    """Our clock at intake. The receipt makes no claim that it is right: it is the lower
    edge of an interval whose upper edge is a checkpoint's RFC 3161 ``genTime``, and a
    receipt alone brackets nothing."""

    mmd_seconds: int = MMD_SECONDS
    """The Maximum Merge Delay. MUST be 60 for v1.0."""

    typ: str = SDR_TYP
    """Domain separation tag."""

    def __post_init__(self) -> None:
        """Validate every member against §2.1, refusing rather than normalising."""
        if self.typ != SDR_TYP:
            raise MalformedReceipt(f"typ must be {SDR_TYP!r}, got {self.typ!r}")
        if _UUID_LOWER.match(self.entry_id) is None:
            raise MalformedReceipt(
                f"entry_id {self.entry_id!r} is not a lowercase UUID; upper case would "
                "canonicalise to different bytes and so to a different signature"
            )
        if _LEAF_HASH.match(self.leaf_hash) is None:
            raise MalformedReceipt(
                f"leaf_hash {self.leaf_hash!r} is not 64 lowercase hex characters"
            )
        if not self.site_code:
            raise MalformedReceipt("site_code is empty")
        if not self.origin:
            raise MalformedReceipt("origin is empty")
        if not isinstance(self.payload_ver, int) or isinstance(self.payload_ver, bool):
            raise MalformedReceipt("payload_ver must be an integer")
        if self.payload_ver < 1:
            raise MalformedReceipt(f"payload_ver must be >= 1, got {self.payload_ver}")
        if not isinstance(self.mmd_seconds, int) or isinstance(self.mmd_seconds, bool):
            raise MalformedReceipt("mmd_seconds must be an integer")
        if self.mmd_seconds != MMD_SECONDS:
            raise MalformedReceipt(
                f"mmd_seconds must be {MMD_SECONDS} for SDR v1.0, got {self.mmd_seconds}; "
                "the MMD is a promise, and a receipt that quietly widened it would be a "
                "promise nobody agreed to"
            )
        _parse_issued_at(self.issued_at)

    @property
    def issued(self) -> datetime:
        """Return ``issued_at`` as an aware UTC datetime."""
        return _parse_issued_at(self.issued_at)

    @property
    def deadline(self) -> datetime:
        """Return the instant by which this leaf must appear under a checkpoint."""
        return self.issued + timedelta(seconds=self.mmd_seconds)

    def to_object(self) -> dict[str, Any]:
        """Return the receipt as the JSON object §2.1 defines."""
        return {
            "typ": self.typ,
            "entry_id": self.entry_id,
            "leaf_hash": self.leaf_hash,
            "site_code": self.site_code,
            "origin": self.origin,
            "payload_ver": self.payload_ver,
            "issued_at": self.issued_at,
            "mmd_seconds": self.mmd_seconds,
        }

    def canonical_bytes(self) -> bytes:
        """Return the exact bytes that are signed: JCS over :meth:`to_object`.

        ``canonicalise_payload`` — not ``canonicalise`` — because the payload profile
        bans IEEE-754 floats (ruling CU-5, ADR 0042). Both numeric members here are
        exact integers, so the ban costs nothing and closes the one interoperability risk
        that would make a stranger's re-implementation disagree with ours.
        """
        return canonicalise_payload(self.to_object())

    @classmethod
    def from_object(cls, obj: Mapping[str, Any]) -> Receipt:
        """Parse a receipt object, strictly.

        Args:
            obj: The JSON object.

        Returns:
            The receipt.

        Raises:
            MalformedReceipt: If a member is missing, unknown, or malformed. An unknown
                member is refused rather than ignored: it would change the canonical
                bytes, so a verifier that ignored it would verify a signature over bytes
                it never showed anyone.
        """
        if not isinstance(obj, Mapping):
            raise MalformedReceipt("a receipt is a JSON object")
        present = set(obj)
        missing = RECEIPT_MEMBERS - present
        extra = present - RECEIPT_MEMBERS
        if missing or extra:
            raise MalformedReceipt(
                f"a receipt has exactly the members {sorted(RECEIPT_MEMBERS)}; "
                f"missing={sorted(missing)} unexpected={sorted(extra)}"
            )
        return cls(
            entry_id=str(obj["entry_id"]),
            leaf_hash=str(obj["leaf_hash"]),
            site_code=str(obj["site_code"]),
            origin=str(obj["origin"]),
            payload_ver=obj["payload_ver"],
            issued_at=str(obj["issued_at"]),
            mmd_seconds=obj["mmd_seconds"],
            typ=str(obj["typ"]),
        )


@dataclass(frozen=True, slots=True)
class ReceiptEnvelope:
    """What the intake API returns and what a holder keeps.

    The envelope is **not** signed; only :attr:`receipt` is. A verifier re-canonicalises
    the receipt and MUST NOT verify over the envelope bytes as received — otherwise the
    envelope's own spelling (key order, whitespace) would become part of the evidence.
    """

    receipt: Receipt
    key_id: bytes
    """The C2SP type-``0x02`` key ID: ``SHA-256(DER SPKI)[:4]``. Identical to the one in
    the checkpoint signature line, so a holder can tell which key to fetch without
    parsing a certificate."""

    sig: bytes
    """The ASN.1 DER ECDSA signature, exactly as KMS returned it."""

    sdr_version: int = SDR_VERSION

    def __post_init__(self) -> None:
        """Validate the envelope's own fields."""
        if self.sdr_version != SDR_VERSION:
            raise MalformedReceipt(f"sdr_version must be {SDR_VERSION}, got {self.sdr_version}")
        if len(self.key_id) != KEY_ID_BYTES:
            raise MalformedReceipt(f"key_id is {len(self.key_id)} bytes, not {KEY_ID_BYTES}")
        if not self.sig:
            raise MalformedReceipt("sig is empty")

    def to_json_object(self) -> dict[str, Any]:
        """Return the envelope as the JSON object ``spec/wire/receipt.md`` §3 defines."""
        return {
            "sdr_version": self.sdr_version,
            "receipt": self.receipt.to_object(),
            "key_id": key_id_hex(self.key_id),
            "sig": base64.b64encode(self.sig).decode("ascii"),
        }

    @classmethod
    def from_json_object(cls, obj: Mapping[str, Any]) -> ReceiptEnvelope:
        """Parse an SDR envelope.

        Args:
            obj: The JSON object.

        Returns:
            The envelope.

        Raises:
            MalformedReceipt: If a member is missing or malformed.
        """
        try:
            version = obj["sdr_version"]
            receipt_obj = obj["receipt"]
            key_id_field = str(obj["key_id"])
            sig_field = str(obj["sig"])
        except (KeyError, TypeError) as exc:
            raise MalformedReceipt(f"SDR envelope is missing a member: {exc}") from exc
        if len(key_id_field) != _KEY_ID_HEX_LEN:
            raise MalformedReceipt(
                f"key_id {key_id_field!r} is not {_KEY_ID_HEX_LEN} lowercase hex characters"
            )
        try:
            key_id = bytes.fromhex(key_id_field)
            sig = base64.b64decode(sig_field, validate=True)
        except (ValueError, TypeError) as exc:
            raise MalformedReceipt(f"SDR envelope key_id or sig is malformed: {exc}") from exc
        if key_id_field != key_id.hex():
            raise MalformedReceipt(f"key_id {key_id_field!r} is not lowercase hex")
        return cls(
            receipt=Receipt.from_object(receipt_obj),
            key_id=key_id,
            sig=sig,
            sdr_version=version,
        )


def issue_receipt(
    signer: Signer,
    *,
    entry_id: str,
    leaf_hash: str,
    site_code: str,
    origin: str,
    payload_ver: int,
    issued_at: datetime | str,
    mmd_seconds: int = MMD_SECONDS,
) -> ReceiptEnvelope:
    """Sign a Signed Disposition Receipt.

    Issued **at intake, before sequencing**. Issuing one after the leaf is already
    sequenced is permitted but pointless; issuing one for a leaf that was never inserted
    is attack A14 and is exactly what :func:`receipt_coverage` detects.

    Args:
        signer: The log key for ``origin`` — the same key that signs its checkpoints.
        entry_id: The intake UUID, lowercase.
        leaf_hash: 64 lowercase hex characters.
        site_code: The site.
        origin: The log origin.
        payload_ver: The canonicaliser version.
        issued_at: An aware datetime, or an already-formatted ``issued_at`` string.
        mmd_seconds: The MMD; must be :data:`MMD_SECONDS` for v1.0.

    Returns:
        The envelope to hand to the signing party.

    Raises:
        MalformedReceipt: If any field violates §2.1.
    """
    receipt = Receipt(
        entry_id=entry_id,
        leaf_hash=leaf_hash,
        site_code=site_code,
        origin=origin,
        payload_ver=payload_ver,
        issued_at=issued_at if isinstance(issued_at, str) else format_issued_at(issued_at),
        mmd_seconds=mmd_seconds,
    )
    key = public_key_for(signer, origin)
    return ReceiptEnvelope(
        receipt=receipt,
        key_id=key.key_id,
        sig=signer.sign(receipt.canonical_bytes()),
    )


def verify_receipt(
    envelope: ReceiptEnvelope | Mapping[str, Any],
    key: PublicKey,
    verify: SignatureVerifier = p256_sha256_verify,
) -> Receipt:
    """Verify an SDR's signature against the log key for its origin.

    Re-canonicalises the receipt object; never verifies over the envelope bytes as
    received.

    Args:
        envelope: The envelope, or its JSON object.
        key: The log key. Its name must equal the receipt's ``origin`` — that check is
            what makes a sandbox receipt fail against an evidentiary bundle instead of
            verifying against a key it was never issued under.
        verify: The signature primitive; defaults to
            :func:`trappoint_ledger.signer.p256_sha256_verify`.

    Returns:
        The verified receipt.

    Raises:
        MalformedReceipt: If the envelope does not parse.
        ReceiptVerificationFailed: If the key ID does not match, the origin does not
            match, or the signature does not verify.
    """
    parsed = (
        envelope
        if isinstance(envelope, ReceiptEnvelope)
        else ReceiptEnvelope.from_json_object(envelope)
    )
    if key.key_id != parsed.key_id:
        raise ReceiptVerificationFailed(
            f"the receipt names key {parsed.key_id.hex()} and the key supplied is {key.key_id_hex}"
        )
    if key.name != parsed.receipt.origin:
        raise ReceiptVerificationFailed(
            f"the receipt was issued for origin {parsed.receipt.origin!r} and the key "
            f"supplied is named {key.name!r}; a receipt is bound to which log must "
            "contain it (spec/wire/receipt.md §2.1)"
        )
    if not verify(key, parsed.receipt.canonical_bytes(), parsed.sig):
        raise ReceiptVerificationFailed(
            f"the signature over receipt {parsed.receipt.entry_id} does not verify "
            f"against key {key.key_id_hex}"
        )
    return parsed.receipt


class ReceiptVerdict(StrEnum):
    """The outcome of a receipt-coverage audit — verifier check 15."""

    PASS = "PASS"  # noqa: S105 - a verdict word, not a credential
    """The leaf is in the bundle and is included under a checkpoint."""

    SKIP_WITHIN_MMD = "SKIP(within-mmd)"
    """The leaf is absent but the MMD has not expired. Not yet a finding."""

    SKIP_NO_CHECKPOINT = "SKIP(no-checkpoint)"
    """The leaf is absent and the bundle carries no checkpoint at all, so "the newest
    checkpoint's timestamp" — the quantity §4 compares against — does not exist.

    Not a verdict ``spec/wire/receipt.md`` v1.0 names; filed as gap G6 in ADR 0043.
    Inventing a FAIL here would accuse the log operator on the strength of a bundle that
    was never assembled, and silently returning PASS would be worse."""

    FAIL_LOG_MISBEHAVIOUR = "FAIL"
    """The MMD expired and the leaf never appeared. **This is the only verifier finding
    that accuses the log operator of an act** rather than reporting a mismatch."""


@dataclass(frozen=True, slots=True)
class ReceiptFinding:
    """A receipt-coverage verdict with the arithmetic that produced it."""

    verdict: ReceiptVerdict
    receipt: Receipt
    deadline: datetime
    """``issued_at + mmd_seconds``. Printed in every verdict, including the passing one,
    so a reader can check the arithmetic rather than take it."""

    detail: str
    """One sentence, in the words the report prints."""

    @property
    def is_accusation(self) -> bool:
        """Return whether this finding accuses the log operator of an act."""
        return self.verdict is ReceiptVerdict.FAIL_LOG_MISBEHAVIOUR


def receipt_coverage(
    receipt: Receipt,
    *,
    leaf_hashes_in_bundle: Container[str],
    newest_checkpoint_at: datetime | None,
) -> ReceiptFinding:
    """Decide whether an SDR's promise was kept — ``spec/wire/receipt.md`` §4 steps 3 to 5.

    The signature is **not** checked here; :func:`verify_receipt` does that, and check 4
    covers it in the verifier because a receipt is signed by the same key as the
    checkpoints. This function is set membership and MMD arithmetic, which is exactly
    what makes it runnable against a bundle with no key material at all.

    Args:
        receipt: The verified receipt.
        leaf_hashes_in_bundle: The leaf hashes the bundle carries, as lowercase hex. The
            caller is responsible for having verified their inclusion proofs — presence
            in this container means "present and proven", not "present".
        newest_checkpoint_at: The timestamp of the newest checkpoint in the bundle, or
            ``None`` if it carries none.

    Returns:
        The finding.
    """
    deadline = receipt.deadline
    if receipt.leaf_hash in leaf_hashes_in_bundle:
        return ReceiptFinding(
            verdict=ReceiptVerdict.PASS,
            receipt=receipt,
            deadline=deadline,
            detail=(
                f"leaf {receipt.leaf_hash} is present in the bundle for origin "
                f"{receipt.origin}; the promise made at {receipt.issued_at} was kept"
            ),
        )
    if newest_checkpoint_at is None:
        return ReceiptFinding(
            verdict=ReceiptVerdict.SKIP_NO_CHECKPOINT,
            receipt=receipt,
            deadline=deadline,
            detail=(
                f"leaf {receipt.leaf_hash} is absent and the bundle carries no checkpoint, "
                f"so whether the {receipt.mmd_seconds}s merge delay expired cannot be "
                f"decided from this bundle. Deadline was {format_issued_at(deadline)}"
            ),
        )
    if newest_checkpoint_at <= deadline:
        return ReceiptFinding(
            verdict=ReceiptVerdict.SKIP_WITHIN_MMD,
            receipt=receipt,
            deadline=deadline,
            detail=(
                f"leaf {receipt.leaf_hash} is not yet under a checkpoint, and the "
                f"{receipt.mmd_seconds}s merge delay has not expired: the newest "
                f"checkpoint is {format_issued_at(newest_checkpoint_at)} and the deadline "
                f"is {format_issued_at(deadline)}"
            ),
        )
    return ReceiptFinding(
        verdict=ReceiptVerdict.FAIL_LOG_MISBEHAVIOUR,
        receipt=receipt,
        deadline=deadline,
        detail=(
            f"LOG MISBEHAVIOUR: the log signed a receipt promising that leaf "
            f"{receipt.leaf_hash} (entry {receipt.entry_id}) would appear under a "
            f"checkpoint of {receipt.origin} by {format_issued_at(deadline)}. The newest "
            f"checkpoint in this bundle is {format_issued_at(newest_checkpoint_at)} and "
            "the leaf is not in it. The receipt is signed by the log's own key"
        ),
    )
