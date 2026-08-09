# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""Intake: canonical bytes in, a signed promise out.

This is L0 of the custody ledger and the implementation of the ``LedgerSink`` interface
the datamodel lead's migration runner and the gate service both write through.

**Canonicalisation is client-side and there is no version of this that runs in SQL.**
CockroachDB's ``sha256()`` returns a hex STRING rather than ``BYTES``
(cockroach#73896), and ``JSONB`` normalises and reorders keys — so
``sha256(payload::STRING)`` is a value no third party can reproduce, which is the one
property an evidentiary hash must have. ``canon_bytes`` is produced here by
``trappoint_jcs.canon_v1`` under RFC 8785 and stored verbatim beside the parsed
``payload``; the two may be compared and may never be conflated. A verifier hashes
``canon_bytes`` and reports a DISCREPANCY when ``payload`` disagrees, which is how attack
A3 (``payload_substitute``) surfaces as a legible finding instead of as nothing at all.

**Floats are refused at the door (CU-5).** ``canonicalise_payload`` raises
``NonEvidentiaryNumber`` on any IEEE-754 float. No evidentiary quantity is a binary
float, and the ES6 number-serialisation path — exponent thresholds at -7/21 where
Python's are -5/16 — is the single largest interoperability risk in a scheme whose whole
value is that a stranger reproduces our bytes.

**``hlc`` is written and never read back.** ``crdb_internal.cluster_logical_timestamp()``
returns the transaction's *provisional* commit timestamp, which the KV layer may push
before the transaction commits (cockroach#79591). It is an ordering hint for batch
selection and nothing else: the authoritative order is the sequencer's ``seq``, and the
authoritative *time* bracket is the beacon (lower bound) and the RFC 3161 token (upper
bound) on the checkpoint.

**Why a receipt at all.** Splitting intake from sequencing buys ``B / L_batch``
throughput and inherits Certificate Transparency's Maximum Merge Delay: ours is 60
seconds, and for those 60 seconds the record exists but nothing that left our trust
boundary covers it. The Signed Disposition Receipt inverts that gap. A receipt whose leaf
never appears in a checkpoint is not a missing record — it is affirmative, portable proof
of log misbehaviour, **held by the person we gave it to** (``spec/wire/receipt.md`` §1,
attack A14, verifier check 15).
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Protocol
from uuid import UUID, uuid4

import psycopg
from psycopg.types.json import Jsonb

from trappoint_jcs import CANON_VERSION, canonicalise_payload

from .append import optional_symbol

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .append import Signer

__all__ = [
    "INSERT_INTAKE_SQL",
    "MMD_SECONDS",
    "RECEIPT_TYP",
    "IntakeRecord",
    "LedgerSink",
    "MainlineLedgerSink",
    "Receipt",
    "ReceiptIssuer",
    "ReceiptIssuerUnavailable",
    "default_receipt_issuer",
    "record_intake",
    "rfc3339_millis",
]

#: ``spec/wire/receipt.md`` §2.1: MUST be 60 for v1.0. It is the honest number and it is
#: measured (``evidence/k2-checkpoint-cadence.json``), not asserted. A ledger that claims
#: a zero window of undetectable mutation is lying.
MMD_SECONDS = 60

#: Domain separation. Without it a signature over one JCS object could be replayed as a
#: signature over another with the same shape.
RECEIPT_TYP = "MAINLINE-SDR-v1"

_LEAF_PREFIX = b"\x00"  # RFC 6962 §2.1 leaf-domain separation.

# MEASURED PLATFORM FACT, 2026-08-04, CockroachDB CCL v26.2.5 (single node, insecure):
# the builtin is `cluster_logical_timestamp()` UNQUALIFIED. The schema-qualified spelling
# `crdb_internal.cluster_logical_timestamp()` — which ARCHITECTURE.md §5.6 and migration
# 0072a's rationale both use in prose — is `UndefinedFunction: unknown function`. The
# qualified form is how the function is *documented* and it is not how it *resolves*, so
# the statement below uses the spelling that was observed to work and this comment
# records why the two differ. Verified alongside `SELECT version()` in the same session.
INSERT_INTAKE_SQL = """
INSERT INTO mainline.ledger_intake
    (entry_id, site_code, entry_kind, subject_id, actor, actor_kind,
     payload, canon_bytes, payload_ver, leaf_hash, is_sandbox, hlc)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
        cluster_logical_timestamp())
RETURNING entry_id, recorded_at
"""


class ReceiptIssuerUnavailable(RuntimeError):
    """``trappoint_ledger.receipt`` is absent or does not expose ``issue_receipt``."""


@dataclass(frozen=True, slots=True)
class IntakeRecord:
    """One row that entered the evidentiary record."""

    entry_id: UUID
    site_code: str
    entry_kind: str
    leaf_hash: bytes
    canon_bytes: bytes
    payload_ver: int
    is_sandbox: bool
    recorded_at: datetime
    """The serving node's wall clock. Useful for operations and **worthless as evidence
    of when anything happened**: the only defensible statements about time are the
    bracketed ones on the checkpoint. Named here so no exhibit ever cites it as a time."""


@dataclass(frozen=True, slots=True)
class Receipt:
    """A Signed Disposition Receipt and the intake row it promises."""

    record: IntakeRecord
    envelope: Mapping[str, Any]
    """The ``spec/wire/receipt.md`` §3 envelope: ``sdr_version``, ``receipt``, ``key_id``,
    ``sig``. The envelope itself is NOT signed; only ``receipt`` is, and a verifier
    re-canonicalises it rather than verifying over the bytes as received."""


class ReceiptIssuer(Protocol):
    """Signs a receipt object and returns the envelope.

    Required of ``packages/trappoint-ledger``:
    ``receipt.issue_receipt(receipt: Mapping[str, Any], signer: Signer) -> Mapping[str, Any]``.

    The receipt *object* is assembled here because ``spec/wire/receipt.md`` §2.1 fixes it
    at eight named members — that is data assembly, not an algorithm. The
    canonicalisation, the signature and the key-ID derivation are evidentiary logic and
    live in one place, with one implementation, in the substrate package the verifier
    also reads.
    """

    def __call__(
        self, receipt: Mapping[str, Any], signer: Signer
    ) -> Mapping[str, Any]:  # pragma: no cover - a call signature
        """Return the signed envelope for *receipt*."""
        ...


class LedgerSink(Protocol):
    """Structural mirror of ``trappoint_migrate.attest.LedgerSink``.

    ``emit(kind, subject_id, payload)`` is the shape the datamodel lead's runner writes
    through. It is declared structurally rather than imported so that this package does
    not take a dependency on the migration runner in order to feed it.

    Note the one difference, recorded rather than papered over: ``docs/leads/datamodel.md``
    writes the Protocol as ``-> None`` and ``docs/leads/custody.md`` writes the
    implementation as returning a Signed Disposition Receipt. Returning the receipt is the
    load-bearing behaviour — a sink that emits no receipt cannot make the promise attack
    A14 exists to falsify — so this implementation returns one. A caller typed against a
    ``-> None`` Protocol should widen it to ``-> object``; the runtime behaviour is
    identical either way because the value may simply be discarded.
    """

    def emit(
        self, kind: str, subject_id: UUID, payload: Mapping[str, Any]
    ) -> Receipt:  # pragma: no cover - a call signature
        """Record *payload* as an intake row and return its receipt."""
        ...


def rfc3339_millis(moment: datetime) -> str:
    """Format *moment* as RFC 3339 UTC with milliseconds and a literal ``Z``.

    ``spec/wire/receipt.md`` §2.1 fixes this shape. ``datetime.isoformat()`` emits either
    six fractional digits or none, and a receipt whose ``issued_at`` renders differently
    on two machines canonicalises to different bytes and verifies against neither
    signature.
    """
    utc = moment.astimezone(UTC)
    return f"{utc:%Y-%m-%dT%H:%M:%S}.{utc.microsecond // 1000:03d}Z"


def default_receipt_issuer() -> ReceiptIssuer:
    """Bind ``trappoint_ledger.receipt.issue_receipt``.

    Resolved dynamically and inside the function so this module stays importable — and
    ``record_intake`` stays usable — on a checkout where ``packages/trappoint-ledger`` has
    not landed. See the note in ``append.default_algebra`` on why a late binding is
    resolved with ``importlib`` rather than a static import plus a suppression.

    Raises:
        ReceiptIssuerUnavailable: if the package or the symbol is absent.
    """
    issuer = optional_symbol("trappoint_ledger.receipt", "issue_receipt")
    if issuer is None:
        raise ReceiptIssuerUnavailable(
            "trappoint_ledger.receipt.issue_receipt is not importable, so no Signed "
            "Disposition Receipt can be signed. It is NOT re-implemented here: the "
            "receipt's canonicalisation and key-ID derivation are the same evidentiary "
            "logic the verifier runs, and two implementations of that is one too many. "
            "mainline_sequencer.sink.ReceiptIssuer documents the required shape: "
            "issue_receipt(receipt: Mapping[str, Any], signer: Signer) -> Mapping[str, Any]."
        )
    bound: ReceiptIssuer = issuer
    return bound


def record_intake(
    conn: psycopg.Connection[Any],
    *,
    site_code: str,
    entry_kind: str,
    subject_id: UUID,
    actor: str,
    actor_kind: str,
    payload: Mapping[str, Any],
    is_sandbox: bool = False,
    entry_id: UUID | None = None,
) -> IntakeRecord:
    """Canonicalise *payload*, hash it, and insert one ``ledger_intake`` row.

    Usable without a signer: the migration runner's attestation path has no ``kms:Sign``
    capability and must still be able to enter a fact into the record. An unsigned intake
    row is a weaker artefact than a receipted one and it is not a missing one.

    ``entry_id`` is generated client-side rather than left to the column's
    ``gen_random_uuid()`` default, so the receipt can be built over an identifier that is
    known before the insert returns. A UUID4 spreads across ranges exactly as
    ``gen_random_uuid()`` does, so the anti-hot-row property the random primary key exists
    for is unaffected.

    Raises:
        trappoint_jcs.NonEvidentiaryNumber: if the payload contains a float (CU-5).
        psycopg.Error: for every database refusal, unretried. ``23503`` on ``fk_site``
            means a ledger entry for a site nobody provisioned; ``42501`` at INSERT means
            the writing role lacks ``SELECT`` on ``mainline.site``, which foreign-key
            validation requires on this platform (measured, migration 0072).
    """
    canon_bytes = canonicalise_payload(dict(payload))
    leaf_hash = hashlib.sha256(_LEAF_PREFIX + canon_bytes).digest()
    identifier = entry_id if entry_id is not None else uuid4()

    with conn.cursor() as cur:
        cur.execute(
            INSERT_INTAKE_SQL,
            (
                identifier,
                site_code,
                entry_kind,
                subject_id,
                actor,
                actor_kind,
                Jsonb(dict(payload)),
                canon_bytes,
                CANON_VERSION,
                leaf_hash,
                is_sandbox,
            ),
        )
        row = cur.fetchone()
    if row is None:  # pragma: no cover - an INSERT ... RETURNING always returns a row
        raise psycopg.ProgrammingError(
            "INSERT ... RETURNING into mainline.ledger_intake produced no row"
        )
    written_id, recorded_at = row
    return IntakeRecord(
        entry_id=written_id,
        site_code=site_code,
        entry_kind=entry_kind,
        leaf_hash=leaf_hash,
        canon_bytes=canon_bytes,
        payload_ver=CANON_VERSION,
        is_sandbox=is_sandbox,
        recorded_at=recorded_at,
    )


@dataclass(frozen=True, slots=True)
class MainlineLedgerSink:
    """The real ``LedgerSink``: an intake row plus a signed promise about it.

    Attributes:
        conn: an open connection. The sink does not open a transaction: a disposition
            and its ledger row must commit together or not at all, so the *caller's*
            transaction is the unit of atomicity. ``spec/custody/ledger-schema.md`` §7
            makes the same demand of the closure projector.
        site_code: the log partition.
        origin: the log identity, identical to line 1 of the checkpoint note. It binds
            the receipt to WHICH log must contain the leaf — which is why a sandbox
            receipt presented against an evidentiary bundle fails on ``origin`` rather
            than being discovered later (attack A12).
        actor / actor_kind: ISO/IEC 27037 chain of custody — every leaf names who, and of
            what kind.
        signer: the log key. The SAME key that signs checkpoints for this origin, so
            verifying a receipt needs no key material a verifier does not already hold,
            and a compromise of the receipt path is a compromise of the log path rather
            than a second, weaker one.
        is_sandbox: guest-sandbox containment (verifier check 13).
        issue: the receipt issuer, defaulting to ``trappoint_ledger``.
        clock: injected so a reference bundle can be regenerated byte-deterministically.
    """

    conn: psycopg.Connection[Any]
    site_code: str
    origin: str
    actor: str
    actor_kind: str
    signer: Signer
    is_sandbox: bool = False
    issue: ReceiptIssuer | None = None
    clock: Callable[[], datetime] = lambda: datetime.now(tz=UTC)

    def emit(self, kind: str, subject_id: UUID, payload: Mapping[str, Any]) -> Receipt:
        """Record *payload* under *kind* and return its Signed Disposition Receipt."""
        record = record_intake(
            self.conn,
            site_code=self.site_code,
            entry_kind=kind,
            subject_id=subject_id,
            actor=self.actor,
            actor_kind=self.actor_kind,
            payload=payload,
            is_sandbox=self.is_sandbox,
        )
        return self.issue_for(record)

    def issue_for(self, record: IntakeRecord) -> Receipt:
        """Build and sign the receipt for an intake row already written.

        Split out so the reference-bundle generator can receipt a row it inserted by
        another path, and so the eight-member object below is assembled in exactly one
        place.
        """
        issuer = self.issue if self.issue is not None else default_receipt_issuer()
        obj: dict[str, Any] = {
            "typ": RECEIPT_TYP,
            "entry_id": str(record.entry_id),
            "leaf_hash": record.leaf_hash.hex(),
            "site_code": record.site_code,
            "origin": self.origin,
            "payload_ver": record.payload_ver,
            "issued_at": rfc3339_millis(self.clock()),
            "mmd_seconds": MMD_SECONDS,
        }
        return Receipt(record=record, envelope=issuer(obj, self.signer))
