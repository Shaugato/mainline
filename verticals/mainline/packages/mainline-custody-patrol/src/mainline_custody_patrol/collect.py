# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""Custody of the custodian: eight collectors, one Object-Locked object each, one leaf each.

Every other table in the ledger band records what the database was *asked* to do. The
eight attestations assembled here record what was done **to** the database — who held
the keys, which triggers were installed, what the cloud control plane logged, whether
the Object Lock retention was still what we said it was. The classic failure of a
tamper-evident log is that it proves its own contents beautifully and can say nothing
at all about the platform underneath it, so an adversary with cloud-admin rights (tier
T2) simply changes the platform.

THE SHAPE OF ONE ATTESTATION, AND WHY IT IS SPLIT IN TWO
--------------------------------------------------------
The collected JSON — a ``ccloud`` audit page, an IAM snapshot, the KMS key policy,
``pg_get_triggerdef()`` output — goes to **S3 with Object Lock COMPLIANCE in the second
account**, and ``mainline.custodian_attestation`` keeps only ``payload_object_key`` and
``payload_sha256`` (migration 0078). Two reasons, and the second is the real one: an IAM
snapshot is large and unbounded, so storing it in an append-only table would make that
table grow without limit; and *a copy held in the database we are attesting about is a
copy the adversary being attested about can rewrite*. The hash is small enough to sit
inside the Merkle tree, and the object it names is somewhere we cannot delete it from.

ORDER OF OPERATIONS, WHICH IS NOT NEGOTIABLE
---------------------------------------------
``collect → canonicalise → hash → put to Object Lock → verify the store's digest →
row + leaf``. The object leaves our reach **before** the row that names it exists. The
reverse order would produce a row pointing at an object we could still decide not to
write, which is a promise rather than a commitment.

WHAT REFUSES, AND WHAT MERELY REPORTS
--------------------------------------
A collector that cannot run does not silently drop out of the set. It produces a
:class:`Refusal`, the run's :attr:`PatrolRun.complete` is ``False``, and
:meth:`PatrolRun.summary_lines` prints the refusal as loudly as a success — the same
discipline the verifier applies to ``SKIP``. The seven that did run are still attested,
because an outage in one cloud API is not a reason to lose the audit stream. But a run
with a refusal in it is never reportable as a clean run.

WHAT THIS MODULE DOES NOT CLAIM
--------------------------------
Tier T3 — access at the Cockroach Labs or AWS storage layer — is **not defeated** by
anything here, and saying so first is the only version of that sentence that helps
anybody. These attestations raise the cost of T1 and T2 by putting the evidence
somewhere the T1 and T2 principals cannot reach; they say nothing about a principal
inside the storage path itself.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Final, Protocol, runtime_checkable
from uuid import NAMESPACE_URL, UUID, uuid5

from trappoint_jcs import CANON_VERSION, canonicalise, canonicalise_payload
from trappoint_jcs.canon_v1 import canon_src_sha256

from .ccloud import CcloudFold, CcloudShim, PageCursor, audit_list, backup_list, rfc3339
from .fingerprint import (
    DEFAULT_SCHEMA_PREFIXES,
    InspectReport,
    SchemaFingerprint,
    SqlSource,
    TriggerDefinitions,
    inspect_database,
    stable_schema_fingerprint,
    trigger_definitions,
)

__all__ = [
    "ATTESTATION_KINDS",
    "COLLECTOR_ID",
    "COMPLIANCE",
    "DEFAULT_RETENTION_YEARS",
    "INSERT_CUSTODIAN_ATTESTATION_SQL",
    "LEDGER_ENTRY_KIND",
    "Attestation",
    "CloudControlPlane",
    "CollectionRefused",
    "CustodyPatrol",
    "FixtureCloudControlPlane",
    "InMemoryObjectStore",
    "LeafLocator",
    "LedgerSink",
    "ObjectStore",
    "ObjectStoreRefused",
    "PatrolRun",
    "PsycopgLeafLocator",
    "Refusal",
    "StoredObject",
    "k2_migration_attestation",
    "write_k2_migration_attestation",
]

#: The closed vocabulary of ``mainline.custodian_attestation.kind``, transcribed from
#: migration 0078's ``kind_known`` CHECK. It is closed because every value is produced by
#: ONE program — this one — inside this repository: adding a kind means adding a
#: collector, and a collector nobody wrote a migration for is a collector nobody
#: reviewed. ``tests/integration/custody/test_custodian_attestation.py`` reads the
#: migration file and asserts the two lists are equal, so the duplication cannot drift.
ATTESTATION_KINDS: Final[tuple[str, ...]] = (
    "ccloud_audit",
    "ccloud_backup",
    "inspect_database",
    "schema_fingerprint",
    "trigger_definitions",
    "kms_key_policy",
    "s3_object_lock",
    "iam_snapshot",
)

#: ``mainline.ledger_intake.entry_kind`` for every leaf this patrol writes
#: (``ARCHITECTURE.md`` §5.6's entry-kind vocabulary).
LEDGER_ENTRY_KIND: Final = "custodian_attestation"

#: The only Object Lock mode an evidentiary object may be written under. GOVERNANCE is
#: bypassable by a principal holding ``s3:BypassGovernanceRetention``, which is exactly
#: the tier-T2 principal these attestations exist to constrain.
COMPLIANCE: Final = "COMPLIANCE"

#: ``ARCHITECTURE.md`` §10: seven-year default retention on the custody bucket.
DEFAULT_RETENTION_YEARS: Final = 7

COLLECTOR_ID: Final = "mainline-custody-patrol/0.1.0"

#: Named columns, no ``*``, and ``collected_at`` passed explicitly rather than left to
#: the column default: the collector's clock is injectable, so a reference run is
#: byte-deterministic and a test does not have to tolerate ``now()``.
INSERT_CUSTODIAN_ATTESTATION_SQL: Final = """
INSERT INTO mainline.custodian_attestation
    (kind, window_from, window_to, payload_object_key, payload_sha256, row_count, collected_at)
VALUES (%s, %s, %s, %s, %s, %s, %s)
RETURNING attestation_id
"""

_LEAF_PREFIX: Final = b"\x00"  # RFC 6962 §2.1 leaf-domain separation.


class CollectionRefused(RuntimeError):
    """A collector could not produce an attestation and said so instead of guessing."""


class ObjectStoreRefused(RuntimeError):
    """The evidence store refused the write, or disagreed about what it stored."""


@dataclass(frozen=True, slots=True)
class StoredObject:
    """What the evidence store says it holds.

    ``sha256`` is the store's *own* computation over the bytes it wrote, not a copy of
    ours. Comparing the two is what turns "we sent the right bytes" into "the store
    holds the right bytes", and it is the only place a truncated or re-encoded upload
    becomes visible before the object is immutable for seven years.
    """

    object_key: str
    sha256: bytes
    version_id: str | None = None
    object_lock_mode: str = COMPLIANCE
    retain_until: datetime | None = None


@runtime_checkable
class ObjectStore(Protocol):
    """The seam to S3 Object Lock COMPLIANCE in the second AWS account.

    Deliberately one method, and deliberately one with ``object_lock_mode`` and
    ``retain_until`` as **required keyword arguments** rather than as bucket defaults.
    A bucket default is a property of infrastructure that a later ``terraform apply``
    can change; an argument is a property of this call that a fake can assert on. AWS
    credentials are invalid on every machine in this build, so the first live run must
    fail loudly rather than succeed wrongly — which only happens if the call shape is
    pinned somewhere that runs today (``docs/leads/custody.md`` §6 risk 3).
    """

    def put_evidence(
        self,
        *,
        key: str,
        body: bytes,
        object_lock_mode: str,
        retain_until: datetime,
    ) -> StoredObject:
        """Write *body* under *key*, retained until *retain_until*, and report it back."""
        ...


@dataclass(slots=True)
class InMemoryObjectStore:
    """A fake evidence store that asserts the exact call shape it will one day make.

    Not a stub that accepts anything. It refuses a non-COMPLIANCE mode, refuses a
    retention date in the past, refuses an empty body, and refuses to *replace* the
    bytes at an existing key — which is the property Object Lock provides and the one a
    permissive fake would quietly not test. Every one of those refusals is a failure the
    first live run would otherwise discover in production, seven years too late to fix.
    """

    clock: Callable[[], datetime] = lambda: datetime.now(tz=UTC)
    objects: dict[str, bytes] = field(default_factory=dict)
    retentions: dict[str, datetime] = field(default_factory=dict)
    calls: list[Mapping[str, Any]] = field(default_factory=list)

    def put_evidence(
        self,
        *,
        key: str,
        body: bytes,
        object_lock_mode: str,
        retain_until: datetime,
    ) -> StoredObject:
        """Record the write after asserting every property Object Lock is bought for."""
        if object_lock_mode != COMPLIANCE:
            raise ObjectStoreRefused(
                f"object_lock_mode={object_lock_mode!r}; evidentiary objects are written "
                f"under {COMPLIANCE!r} only. GOVERNANCE can be bypassed by a principal "
                "holding s3:BypassGovernanceRetention, which is precisely the tier-T2 "
                "principal this attestation exists to constrain"
            )
        if not body:
            raise ObjectStoreRefused(f"refusing to store an empty evidentiary object at {key}")
        if retain_until <= self.clock():
            raise ObjectStoreRefused(
                f"retain_until={retain_until.isoformat()} is not in the future; an object "
                "written with an expired retention is an object anyone can delete today"
            )
        existing = self.objects.get(key)
        if existing is not None and existing != body:
            raise ObjectStoreRefused(
                f"{key} already holds different bytes. Under Object Lock COMPLIANCE this "
                "would create a new version rather than replacing anything, so a collector "
                "that expects to overwrite has a key-derivation bug — and the fake refuses "
                "here rather than letting the bug reach a bucket nobody can clean up"
            )
        self.objects[key] = body
        self.retentions[key] = retain_until
        self.calls.append(
            {
                "key": key,
                "object_lock_mode": object_lock_mode,
                "retain_until": retain_until,
                "length": len(body),
            }
        )
        return StoredObject(
            object_key=key,
            sha256=hashlib.sha256(body).digest(),
            version_id=f"fake-{len(self.calls):08d}",
            object_lock_mode=object_lock_mode,
            retain_until=retain_until,
        )


@runtime_checkable
class CloudControlPlane(Protocol):
    """KMS, S3 and IAM reads, behind one Protocol with no SDK on the import path.

    Three of the eight kinds — ``kms_key_policy``, ``s3_object_lock``, ``iam_snapshot``
    — are answers to *"and who could have changed any of this?"*. They are read through
    this Protocol so the patrol is testable and importable with no AWS credentials,
    which is the state of every machine in this build.
    """

    def kms_key_policy(self, key_id: str) -> Mapping[str, Any]:
        """Who may use, disable or schedule deletion of the log signing key."""
        ...

    def s3_object_lock(self, bucket: str) -> Mapping[str, Any]:
        """Report the retention mode and period actually configured on the bucket."""
        ...

    def iam_snapshot(self) -> Mapping[str, Any]:
        """Who could have done any of the above."""
        ...


@dataclass(slots=True)
class FixtureCloudControlPlane:
    """A control plane that answers from committed JSON.

    The fixtures are recorded response shapes. Their job is to exercise the folding,
    hashing and refusal paths on a machine with no AWS account — and to make the shape
    of the eventual live call visible in a file a reviewer can read, rather than only in
    a boto3 call nobody can run.
    """

    directory: Path

    def _read(self, name: str) -> Mapping[str, Any]:
        path = self.directory / name
        if not path.is_file():
            raise CollectionRefused(
                f"no cloud fixture at {path}. A fixture-backed control plane that "
                "invented an empty response would make an uncollected attestation "
                "indistinguishable from a clean one"
            )
        loaded = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(loaded, Mapping):
            raise CollectionRefused(f"{path} is not a JSON object")
        return loaded

    def kms_key_policy(self, key_id: str) -> Mapping[str, Any]:
        """Return the recorded key policy, tagged with the key it is claimed to describe."""
        return {"key_id": key_id, **self._read("kms-key-policy.json")}

    def s3_object_lock(self, bucket: str) -> Mapping[str, Any]:
        """Return the recorded Object Lock configuration for *bucket*."""
        return {"bucket": bucket, **self._read("s3-object-lock.json")}

    def iam_snapshot(self) -> Mapping[str, Any]:
        """Return the recorded IAM snapshot."""
        return dict(self._read("iam-snapshot.json"))


@runtime_checkable
class LedgerSink(Protocol):
    """Structural mirror of ``trappoint_migrate.attest.LedgerSink``.

    ``emit(kind, subject_id, payload)`` is the shape the migration runner, the gate
    service and ``mainline_sequencer.sink.MainlineLedgerSink`` all speak. It is declared
    structurally rather than imported so this package does not depend on the sequencer
    in order to feed it — and so a test can assert what was emitted without a database.

    The return type is ``object`` on purpose: the datamodel lead's Protocol says
    ``-> None`` and the custody implementation returns a Signed Disposition Receipt.
    Widening to ``object`` accepts both without asking either to change.
    """

    def emit(self, kind: str, subject_id: UUID, payload: Mapping[str, Any]) -> object:
        """Record *payload* under *kind* as one ledger intake row."""
        ...


@runtime_checkable
class LeafLocator(Protocol):
    """Finds the sequenced position of a leaf, or reports that there is not one yet."""

    def seq_for_leaf_hash(self, site_code: str, leaf_hash: bytes) -> int | None:
        """Return ``ledger_leaf.seq`` for *leaf_hash*, or ``None`` if unsequenced."""
        ...


#: The one statement the locator runs. Named so a reviewer can see that it reads
#: ``mainline.ledger_leaf`` — the SEQUENCED table — and not ``ledger_intake``. An intake
#: row proves we accepted the fact; only a leaf proves the log committed to it, and the
#: difference between those two is exactly attack A14 (``receipt_orphan``).
SELECT_LEAF_SEQ_SQL: Final = """
SELECT seq FROM mainline.ledger_leaf WHERE site_code = %s AND leaf_hash = %s
"""


@dataclass(slots=True)
class PsycopgLeafLocator:
    """A :class:`LeafLocator` over any DB-API connection. No driver import required.

    Takes the connection rather than a DSN because the caller owns the transaction: the
    lookup must see the sequencer's committed work, so it runs on the caller's session
    under the caller's isolation, not on a connection this module opened behind them.
    """

    connection: Any

    def seq_for_leaf_hash(self, site_code: str, leaf_hash: bytes) -> int | None:
        """Return the leaf's sequenced position, or ``None`` when it has none yet."""
        with self.connection.cursor() as cur:
            cur.execute(SELECT_LEAF_SEQ_SQL, (site_code, leaf_hash))
            row = cur.fetchone()
        if row is None:
            return None
        return int(row[0] if isinstance(row, (list, tuple)) else row["seq"])


@dataclass(frozen=True, slots=True)
class Attestation:
    """One collected fact about the platform, committed to and named.

    Attributes:
        kind: one of :data:`ATTESTATION_KINDS`.
        window_from / window_to: the closed interval the fact covers. Equal for
            snapshot-shaped kinds — migration 0078's ``window_ordered`` admits a point
            deliberately, because inventing an end time for a statement about an instant
            is exactly the invented value that band refuses everywhere else.
        payload_object_key: the Object-Locked key. The JSON lives there.
        payload_sha256: … and only its digest lives in the row.
        row_count: a count for stream-shaped kinds, ``None`` for snapshots.
        canon_bytes: the RFC 8785 bytes that were stored and hashed. Carried so a caller
            can re-derive the digest without fetching the object; never written to the
            database.
        leaf_hash: SHA-256(0x00 ‖ canonical leaf payload), RFC 6962 §2.1.
    """

    kind: str
    window_from: datetime
    window_to: datetime
    payload_object_key: str
    payload_sha256: bytes
    row_count: int | None
    collected_at: datetime
    canon_bytes: bytes
    leaf_payload: Mapping[str, Any]
    leaf_hash: bytes
    subject_id: UUID
    object_version_id: str | None
    source: str

    @property
    def row_params(self) -> tuple[Any, ...]:
        """Parameters for :data:`INSERT_CUSTODIAN_ATTESTATION_SQL`, in column order."""
        return (
            self.kind,
            self.window_from,
            self.window_to,
            self.payload_object_key,
            self.payload_sha256,
            self.row_count,
            self.collected_at,
        )


@dataclass(frozen=True, slots=True)
class Refusal:
    """A collector that could not run, and why. Never silently absent."""

    kind: str
    reason: str

    def __str__(self) -> str:
        """Render as the loud one-liner the run summary prints."""
        return f"REFUSED {self.kind}: {self.reason}"


@dataclass(frozen=True, slots=True)
class PatrolRun:
    """One pass of the patrol: what was attested, and what was not."""

    started_at: datetime
    finished_at: datetime
    attestations: tuple[Attestation, ...]
    refusals: tuple[Refusal, ...]

    @property
    def complete(self) -> bool:
        """True only when all eight kinds produced an attestation."""
        return not self.refusals and {a.kind for a in self.attestations} == set(ATTESTATION_KINDS)

    def summary_lines(self) -> list[str]:
        """Render the run. A refusal is printed as loudly as a success, by construction."""
        lines = [
            f"custodian patrol {rfc3339(self.started_at)} → {rfc3339(self.finished_at)}",
            f"  attested: {len(self.attestations)}/{len(ATTESTATION_KINDS)}",
        ]
        lines.extend(
            f"  OK       {a.kind:<20} rows={a.row_count if a.row_count is not None else '-'} "
            f"sha256={a.payload_sha256.hex()[:16]}… key={a.payload_object_key}"
            for a in self.attestations
        )
        lines.extend(f"  {refusal}" for refusal in self.refusals)
        if not self.complete:
            lines.append(
                "  INCOMPLETE — this run is NOT reportable as a clean patrol. A kind that "
                "did not run is not a kind that found nothing."
            )
        return lines


def _subject_id(kind: str, digest: bytes) -> UUID:
    """Derive the leaf's subject id from the kind and the payload digest.

    ``uuid5`` rather than ``uuid4`` so a reference run regenerates byte-identically
    (CU-6) and so two collectors that somehow produced the same bytes for the same kind
    cannot present as two independent facts.
    """
    return uuid5(NAMESPACE_URL, f"urn:mainline:custodian_attestation:{kind}:{digest.hex()}")


@dataclass(slots=True)
class CustodyPatrol:
    """The eight collectors, their evidence store, and the ledger they fold into.

    Every external capability is an injected Protocol. That is not testing hygiene: it
    is what makes the package importable, and seven of its eight collectors runnable,
    on a machine with no AWS credentials, no CockroachDB Cloud organisation and no
    database driver.

    Attributes:
        object_store: where the collected JSON goes and cannot be deleted from.
        key_prefix: the S3 key prefix inside the evidence bucket.
        clock: injected so a reference run is byte-deterministic.
        sink: the ledger. Optional — a dry run collects and stores without emitting, and
            says so; it does not pretend the leaf was written.
        sql / ccloud / cloud: the three read capabilities. A missing one produces a
            :class:`Refusal` for the kinds that need it, never a skipped set member.
    """

    object_store: ObjectStore
    key_prefix: str = "custodian"
    retention_years: int = DEFAULT_RETENTION_YEARS
    clock: Callable[[], datetime] = lambda: datetime.now(tz=UTC)
    site_code: str = "unknown"
    sink: LedgerSink | None = None
    sql: SqlSource | None = None
    ccloud: CcloudShim | None = None
    ccloud_source: str = "unresolved"
    ccloud_cursor: PageCursor | None = None
    cloud: CloudControlPlane | None = None
    cluster_id: str = ""
    database: str = "mainline"
    kms_key_id: str = ""
    evidence_bucket: str = ""
    schema_prefixes: Sequence[str] = DEFAULT_SCHEMA_PREFIXES

    # ----------------------------------------------------------------- internals

    def _retain_until(self, now: datetime) -> datetime:
        # 365-day years, deliberately: a leap-aware "seven calendar years" would put a
        # retention boundary on a date arithmetic disagreement, and a retention that is
        # a day LONGER than promised is harmless while a day shorter is a deleted
        # object. `timedelta` has no `years`, and inventing one here would be a second
        # calendar implementation in a file that has no business owning one.
        return now + timedelta(days=365 * self.retention_years)

    def _attest(
        self,
        *,
        kind: str,
        document: Mapping[str, Any],
        row_count: int | None,
        window_from: datetime,
        window_to: datetime,
        source: str,
    ) -> Attestation:
        """Canonicalise, store, verify the store, then build the row and the leaf."""
        if kind not in ATTESTATION_KINDS:
            raise CollectionRefused(
                f"{kind!r} is not in mainline.custodian_attestation's kind vocabulary "
                f"{ATTESTATION_KINDS}. Adding a kind is a migration, because adding a kind "
                "means adding a collector, and a collector nobody wrote a migration for is "
                "a collector nobody reviewed"
            )
        if window_to < window_from:
            raise CollectionRefused(
                f"{kind}: window_to {rfc3339(window_to)} precedes window_from "
                f"{rfc3339(window_from)}; `window_ordered` would refuse the row"
            )

        now = self.clock()
        # RFC 8785 IN FULL over the foreign document — floats included. CockroachDB
        # Cloud and AWS authored these bytes and we do not get to impose an evidentiary
        # number profile on them. CU-5's float ban applies to the LEAF payload below,
        # which we author, and which never carries one.
        canon = canonicalise(dict(document))
        digest = hashlib.sha256(canon).digest()
        key = f"{self.key_prefix}/{kind}/{window_to:%Y/%m/%d}/{digest.hex()}.json"

        stored = self.object_store.put_evidence(
            key=key,
            body=canon,
            object_lock_mode=COMPLIANCE,
            retain_until=self._retain_until(now),
        )
        if stored.sha256 != digest:
            raise ObjectStoreRefused(
                f"{kind}: the evidence store reports sha256={stored.sha256.hex()} for "
                f"{key} but the canonical bytes hash to {digest.hex()}. The row must never "
                "name an object whose contents we cannot vouch for — that is a citation to "
                "evidence rather than evidence"
            )

        leaf_payload: dict[str, Any] = {
            "attestation": "custodian",
            "collector": COLLECTOR_ID,
            "kind": kind,
            "site_code": self.site_code,
            "source": source,
            "window_from": rfc3339(window_from),
            "window_to": rfc3339(window_to),
            "collected_at": rfc3339(now),
            "payload_object_key": stored.object_key,
            "payload_object_version": stored.version_id,
            "payload_object_lock_mode": stored.object_lock_mode,
            "payload_sha256": digest.hex(),
            "payload_ver": CANON_VERSION,
            "canon_src_sha256": canon_src_sha256().hex(),
            "row_count": row_count,
        }
        # CU-5: `canonicalise_payload` refuses any IEEE-754 float. Every member above is
        # a string, an int or null, so this call is a proof rather than a hope — and it
        # is the call whose bytes the Merkle leaf is taken over.
        leaf_bytes = canonicalise_payload(leaf_payload)
        leaf_hash = hashlib.sha256(_LEAF_PREFIX + leaf_bytes).digest()
        subject = _subject_id(kind, digest)

        if self.sink is not None:
            self.sink.emit(LEDGER_ENTRY_KIND, subject, leaf_payload)

        return Attestation(
            kind=kind,
            window_from=window_from,
            window_to=window_to,
            payload_object_key=stored.object_key,
            payload_sha256=digest,
            row_count=row_count,
            collected_at=now,
            canon_bytes=canon,
            leaf_payload=leaf_payload,
            leaf_hash=leaf_hash,
            subject_id=subject,
            object_version_id=stored.version_id,
            source=source,
        )

    def _require_sql(self, kind: str) -> SqlSource:
        if self.sql is None:
            raise CollectionRefused(
                f"{kind} needs a SqlSource and none was supplied. The patrol does not "
                "open its own connection: a custodian attestation and its ledger leaf "
                "commit together or not at all, so the caller's transaction is the unit "
                "of atomicity"
            )
        return self.sql

    def _require_cloud(self, kind: str) -> CloudControlPlane:
        if self.cloud is None:
            raise CollectionRefused(
                f"{kind} needs a CloudControlPlane and none was supplied. AWS credentials "
                "are not valid on any machine in this build, so this refusal is the "
                "expected state today — and it is a refusal rather than an omission"
            )
        return self.cloud

    def _require_ccloud(self, kind: str) -> CcloudShim:
        if self.ccloud is None:
            raise CollectionRefused(
                f"{kind} needs a ccloud shim and none was resolved. See "
                "mainline_custody_patrol.ccloud.resolve_shim: there is deliberately no "
                "silent default"
            )
        return self.ccloud

    # ------------------------------------------------------------ the collectors

    def collect_ccloud_audit(self, *, window_from: datetime, window_to: datetime) -> Attestation:
        """Fold the CockroachDB Cloud audit stream — the record an admin does not author."""
        fold = audit_list(
            self._require_ccloud("ccloud_audit"),
            starting_from=window_from,
            window_to=window_to,
            source=self.ccloud_source,
            cursor=self.ccloud_cursor,
        )
        return self._attest_fold(fold)

    def collect_ccloud_backup(self, *, at: datetime) -> Attestation:
        """Fold the backup inventory. A restore nobody can point at is not a backup."""
        if not self.cluster_id:
            raise CollectionRefused(
                "ccloud_backup needs the cluster id whose backups are being attested; "
                "an unqualified backup list is a claim about no particular cluster"
            )
        fold = backup_list(
            self._require_ccloud("ccloud_backup"),
            cluster_id=self.cluster_id,
            at=at,
            source=self.ccloud_source,
            cursor=self.ccloud_cursor,
        )
        return self._attest_fold(fold)

    def _attest_fold(self, fold: CcloudFold) -> Attestation:
        return self._attest(
            kind=fold.kind,
            document=fold.document,
            row_count=fold.row_count,
            window_from=fold.window_from,
            window_to=fold.window_to,
            source=fold.command,
        )

    def collect_inspect_database(self, *, at: datetime) -> Attestation:
        """Attest the cluster's own consistency reporting, including its unavailability."""
        report: InspectReport = inspect_database(
            self._require_sql("inspect_database"), database=self.database
        )
        document = {
            "attestation_kind": "inspect_database",
            "collector": COLLECTOR_ID,
            "database": report.database,
            "statement": report.statement,
            "available": report.available,
            "enable_sqlstate": report.enable_sqlstate,
            "unavailable_reason": report.unavailable_reason,
            "error_count": report.row_count,
            "errors": [dict(row) for row in report.errors],
        }
        return self._attest(
            kind="inspect_database",
            document=document,
            row_count=report.row_count if report.available else None,
            window_from=at,
            window_to=at,
            source=report.statement,
        )

    def collect_schema_fingerprint(self, *, at: datetime) -> Attestation:
        """Attest the normalised, order-stable digest of the whole schema.

        Stability is *observed* here, not assumed: both computations are attested, so a
        reader can see that the run computed the digest twice and got the same answer.
        """
        first, second = stable_schema_fingerprint(
            self._require_sql("schema_fingerprint"), schema_prefixes=self.schema_prefixes
        )
        document = _fingerprint_document(first, second, self.schema_prefixes)
        return self._attest(
            kind="schema_fingerprint",
            document=document,
            row_count=sum(first.row_counts.values()),
            window_from=at,
            window_to=at,
            source=f"SHOW CREATE ALL … + pg_catalog ({first.grade})",
        )

    def collect_trigger_definitions(self, *, at: datetime) -> Attestation:
        """Attest what the triggers ACTUALLY are — the self-attesting gate (check 11)."""
        definitions: TriggerDefinitions = trigger_definitions(
            self._require_sql("trigger_definitions")
        )
        document = {
            "attestation_kind": "trigger_definitions",
            "collector": COLLECTOR_ID,
            "granularity": definitions.granularity,
            "source": definitions.source,
            "trigger_count": definitions.row_count,
            "triggers": [dict(row) for row in definitions.triggers],
            "platform_note": (
                "pg_get_triggerdef() confirmed on CockroachDB CCL v26.2.5 (2026-08-07); "
                "behaviour on CockroachDB Cloud Standard is not verified. granularity="
                "'coarse' means the SHOW CREATE fallback was taken and verifier check 11 "
                "reports PASS(coarse)."
            ),
        }
        return self._attest(
            kind="trigger_definitions",
            document=document,
            row_count=definitions.row_count,
            window_from=at,
            window_to=at,
            source=definitions.source,
        )

    def collect_kms_key_policy(self, *, at: datetime) -> Attestation:
        """Attest who may use, disable or schedule deletion of the log signing key."""
        if not self.kms_key_id:
            raise CollectionRefused(
                "kms_key_policy needs the key id of the log signing key. A key policy "
                "attested without naming its key describes no key"
            )
        policy = self._require_cloud("kms_key_policy").kms_key_policy(self.kms_key_id)
        document = {
            "attestation_kind": "kms_key_policy",
            "collector": COLLECTOR_ID,
            "key_id": self.kms_key_id,
            "policy": dict(policy),
        }
        return self._attest(
            kind="kms_key_policy",
            document=document,
            row_count=None,
            window_from=at,
            window_to=at,
            source=f"kms:GetKeyPolicy {self.kms_key_id}",
        )

    def collect_s3_object_lock(self, *, at: datetime) -> Attestation:
        """Attest the retention mode and period actually configured on the bucket.

        ``GT-18``: Object Lock and versioning cannot be retrofitted and backup retention
        is set once at provisioning. This attestation is how a later *weakening* becomes
        visible — the configuration is read back on every patrol, not trusted from the
        plan that created it.
        """
        if not self.evidence_bucket:
            raise CollectionRefused(
                "s3_object_lock needs the evidence bucket name; a retention configuration "
                "attested without naming its bucket describes no bucket"
            )
        configuration = self._require_cloud("s3_object_lock").s3_object_lock(self.evidence_bucket)
        document = {
            "attestation_kind": "s3_object_lock",
            "collector": COLLECTOR_ID,
            "bucket": self.evidence_bucket,
            "configuration": dict(configuration),
        }
        return self._attest(
            kind="s3_object_lock",
            document=document,
            row_count=None,
            window_from=at,
            window_to=at,
            source=f"s3:GetObjectLockConfiguration {self.evidence_bucket}",
        )

    def collect_iam_snapshot(self, *, at: datetime) -> Attestation:
        """Attest who could have done any of the above."""
        snapshot = self._require_cloud("iam_snapshot").iam_snapshot()
        document = {
            "attestation_kind": "iam_snapshot",
            "collector": COLLECTOR_ID,
            "snapshot": dict(snapshot),
        }
        principals = snapshot.get("principals")
        return self._attest(
            kind="iam_snapshot",
            document=document,
            row_count=len(principals) if isinstance(principals, list) else None,
            window_from=at,
            window_to=at,
            source="iam:ListRoles+ListUsers+ListPolicies",
        )

    # ------------------------------------------------------------------- the run

    def run(self, *, window_from: datetime, window_to: datetime | None = None) -> PatrolRun:
        """Run all eight collectors. A failure in one never removes the other seven.

        Every collector is attempted; the ones that cannot run produce a
        :class:`Refusal`. The run is *complete* only when all eight attested, and an
        incomplete run says so in its own summary — because "seven of eight" and "eight
        of eight" must never render the same way.
        """
        started = self.clock()
        at = window_to if window_to is not None else started
        attestations: list[Attestation] = []
        refusals: list[Refusal] = []

        plan: tuple[tuple[str, Callable[[], Attestation]], ...] = (
            (
                "ccloud_audit",
                lambda: self.collect_ccloud_audit(window_from=window_from, window_to=at),
            ),
            ("ccloud_backup", lambda: self.collect_ccloud_backup(at=at)),
            ("inspect_database", lambda: self.collect_inspect_database(at=at)),
            ("schema_fingerprint", lambda: self.collect_schema_fingerprint(at=at)),
            ("trigger_definitions", lambda: self.collect_trigger_definitions(at=at)),
            ("kms_key_policy", lambda: self.collect_kms_key_policy(at=at)),
            ("s3_object_lock", lambda: self.collect_s3_object_lock(at=at)),
            ("iam_snapshot", lambda: self.collect_iam_snapshot(at=at)),
        )

        for kind, collector in plan:
            try:
                attestations.append(collector())
            except (RuntimeError, ValueError) as exc:
                # Bounded by TYPE, never by `except Exception`. `RuntimeError` is the base
                # of every refusal this package raises — CollectionRefused,
                # ObjectStoreRefused, CcloudUnavailable, CcloudFieldMissing,
                # CcloudPaginationUnresolved, FingerprintUnstable — and `ValueError` is
                # what a caller-supplied naive datetime or reversed window produces. A
                # TypeError, an AttributeError or a KeyError is a bug in THIS module and
                # must not be laundered into a tidy summary line: it propagates and fails
                # the run, which is the only way anybody finds out.
                refusals.append(Refusal(kind=kind, reason=f"{type(exc).__name__}: {exc}"))

        return PatrolRun(
            started_at=started,
            finished_at=self.clock(),
            attestations=tuple(attestations),
            refusals=tuple(refusals),
        )


def _fingerprint_document(
    first: SchemaFingerprint,
    second: SchemaFingerprint,
    schema_prefixes: Sequence[str],
) -> dict[str, Any]:
    return {
        "attestation_kind": "schema_fingerprint",
        "collector": COLLECTOR_ID,
        "grade": first.grade,
        "parts": list(first.parts),
        "schema_prefixes": list(schema_prefixes),
        "fingerprint_run_1": first.hex,
        "fingerprint_run_2": second.hex,
        "stable": first.digest == second.digest,
        "part_digests": dict(first.part_digests),
        "row_counts": dict(first.row_counts),
    }


def k2_migration_attestation(
    patrol: CustodyPatrol,
    *,
    at: datetime | None = None,
    locator: LeafLocator | None = None,
) -> dict[str, Any]:
    """Build the K2 exit-criterion-6 artefact: two fingerprints and the leaf they entered.

    ``tests/integration/custody/test_k2_exit.py::
    test_k2_6_migration_attestation_chained_with_a_stable_fingerprint`` requires three
    things of this document and each one is a separate claim: that the fingerprint was
    computed **twice** (``fingerprint_run_1``, ``fingerprint_run_2``), that the two runs
    **agreed**, and that the result was **chained into the ledger**
    (``chained_leaf_seq``).

    The third is the one that is easy to fake and this function refuses to. A fingerprint
    that lives outside the tree is a file we could edit, so the leaf's sequenced position
    is looked up rather than asserted, and a leaf that never appears raises rather than
    writing ``null`` — an unsequenced leaf is attack A14 (``receipt_orphan``), not a
    formatting inconvenience.

    Raises:
        CollectionRefused: no locator was supplied, or the leaf is not yet sequenced.
    """
    moment = at if at is not None else patrol.clock()
    attestation = patrol.collect_schema_fingerprint(at=moment)
    document = json.loads(attestation.canon_bytes.decode("utf-8"))

    if locator is None:
        raise CollectionRefused(
            "k2_migration_attestation needs a LeafLocator. The criterion is that the "
            "attestation is CHAINED, and 'chained' is a fact about mainline.ledger_leaf "
            "that only the database can answer. Emitting the artefact with a null "
            "chained_leaf_seq would satisfy the file format and none of the criterion."
        )
    seq = locator.seq_for_leaf_hash(patrol.site_code, attestation.leaf_hash)
    if seq is None:
        raise CollectionRefused(
            f"leaf {attestation.leaf_hash.hex()[:16]}… has no row in mainline.ledger_leaf. "
            "The intake row exists and the sequencer has not yet merged it, or it never "
            "will: an intake row that is never sequenced is attack A14 (receipt_orphan). "
            "Re-run after the next sequencer pass, or investigate — but do not record the "
            "attestation as chained, because it is not."
        )

    return {
        "artefact": "k2-migration-attestation",
        "criterion": "K2.6 — migration attestation chained, fingerprint stable",
        "collector": COLLECTOR_ID,
        "computed_at": rfc3339(attestation.collected_at),
        "site_code": patrol.site_code,
        "schema_prefixes": list(patrol.schema_prefixes),
        "fingerprint_run_1": document["fingerprint_run_1"],
        "fingerprint_run_2": document["fingerprint_run_2"],
        "grade": document["grade"],
        "parts": document["parts"],
        "part_digests": document["part_digests"],
        "payload_object_key": attestation.payload_object_key,
        "payload_sha256": attestation.payload_sha256.hex(),
        "leaf_hash": attestation.leaf_hash.hex(),
        "chained_leaf_seq": seq,
        "canon_src_sha256": canon_src_sha256().hex(),
    }


def write_k2_migration_attestation(
    path: Path,
    patrol: CustodyPatrol,
    *,
    at: datetime | None = None,
    locator: LeafLocator | None = None,
) -> dict[str, Any]:
    r"""Write the K2.6 artefact to *path* with two-space indent and a trailing newline.

    Deterministic on purpose — sorted keys, fixed indent, ``\n`` line endings — so that
    regenerating it on an unchanged cluster produces a zero diff, exactly as
    ``just evidence-regen`` demands of the reference bundle (CU-6).
    """
    document = k2_migration_attestation(patrol, at=at, locator=locator)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return document
