# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""``up``, ``status`` and ``force``: applying the stream and refusing to guess.

The apply loop is deliberately boring, and every step of it exists because of a
specific way migrations go wrong on CockroachDB:

1. **Refuse unless bootstrapped.** A migration applied against a database with no
   bookkeeping tables is a migration with no record.
2. **Hold a real lease** (there are no advisory locks).
3. **Reconcile disk against the database before touching anything.** Three
   reconciliation failures are fatal and all three are the same underlying fact — the
   stream on disk is not the stream that produced this schema: a file whose SHA-256
   changed after it was applied; a new file that sorts *before* the last applied one;
   an applied version with no file.
4. **Refuse while anything is ``applying`` or ``dirty``.** Forward progress past an
   unresolved failure is how a half-applied schema becomes permanent.
5. **Per file: record intent, issue exactly one statement, wait for the JOB, record
   outcome, attest.** The statement is never retried — not even on ``40001`` — because
   a DDL statement starts a background job and "did it happen" is answered by
   ``SHOW JOBS``.

On failure the version is marked ``dirty`` with the SQLSTATE and the database's own
message, and the run stops. Resolution is a human with an incident id.
"""

from __future__ import annotations

import getpass
import socket
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psycopg

from . import attest as attestation
from . import lock
from .bootstrap import is_bootstrapped
from .db import execute_ddl, fetch_all, in_txn, wait_for_schema_jobs
from .discovery import MigrationFile, discover
from .errors import (
    BootstrapMissing,
    DirtyMigration,
    MigrationTreeInvalid,
    StatementFailed,
)

__all__ = [
    "AppliedRow",
    "MigrationPlan",
    "UpResult",
    "actor",
    "apply",
    "force",
    "plan",
    "read_applied",
]

# Which schemas' routines the fingerprint covers. `trappoint` is included because the
# kernel's own procedures (`trappoint.merge_permit()`, ruling D6) live there, and a
# fingerprint that omitted them would let the merge procedure be replaced without
# changing the attestation — which is precisely the self-attesting-gate claim.
DEFAULT_SCHEMA_PREFIXES: tuple[str, ...] = ("mainline%", "trappoint%")


def actor() -> str:
    """Who is applying this, for ``applied_by``.

    A username and a host. Not a claim of identity — this is an operational breadcrumb,
    not an attestation of authorship, and the difference matters enough to say here so
    nobody later cites this column as evidence of who signed anything.
    """
    try:
        user = getpass.getuser()
    except (OSError, KeyError):  # pragma: no cover - depends on the host
        user = "unknown"
    return f"{user}@{socket.gethostname()}"


@dataclass(frozen=True, slots=True)
class AppliedRow:
    """One row of ``trappoint.schema_migration``."""

    version: str
    filename: str
    sha256: bytes
    state: str
    failure: str | None
    failure_sqlstate: str | None


@dataclass(frozen=True, slots=True)
class MigrationPlan:
    """What ``up`` would do, computed before anything is applied."""

    tree: str
    root: Path
    applied: tuple[AppliedRow, ...]
    pending: tuple[MigrationFile, ...]
    unresolved: tuple[AppliedRow, ...]
    """Rows in ``applying`` or ``dirty`` state. Non-empty means ``up`` refuses."""

    @property
    def is_noop(self) -> bool:
        """True when there is nothing to apply."""
        return not self.pending


@dataclass(slots=True)
class UpResult:
    """The outcome of an apply run."""

    tree: str
    applied: list[str] = field(default_factory=list)
    attestation_ordinals: list[int] = field(default_factory=list)
    final_fingerprint: bytes | None = None
    grade: str | None = None


def read_applied(conn: psycopg.Connection[Any], tree: str) -> list[AppliedRow]:
    """Read every recorded version for *tree*, ordered."""
    rows = fetch_all(
        conn,
        """
        SELECT version, filename, sha256, state, failure, failure_sqlstate
        FROM trappoint.schema_migration
        WHERE tree = %s
        ORDER BY version ASC
        """,
        (tree,),
    )
    return [
        AppliedRow(
            version=str(r["version"]),
            filename=str(r["filename"]),
            sha256=bytes(r["sha256"]),
            state=str(r["state"]),
            failure=None if r["failure"] is None else str(r["failure"]),
            failure_sqlstate=(
                None if r["failure_sqlstate"] is None else str(r["failure_sqlstate"])
            ),
        )
        for r in rows
    ]


def plan(conn: psycopg.Connection[Any], *, tree: str, root: Path) -> MigrationPlan:
    """Reconcile the files under *root* against what the database recorded.

    Raises:
        MigrationTreeInvalid: on a checksum change, an out-of-order insertion, or an
            applied version whose file has vanished. None of the three is recoverable by
            the runner, and all three mean the same thing: the stream on disk is not the
            stream that produced this schema.
    """
    files = discover(root)
    by_version = {f.version: f for f in files}
    recorded = read_applied(conn, tree)
    recorded_by_version = {r.version: r for r in recorded}

    for row in recorded:
        candidate = by_version.get(row.version)
        if candidate is None:
            raise MigrationTreeInvalid(
                f"{tree}: version {row.version!r} is recorded as {row.state} but no file "
                f"for it exists under {root}. A migration that was applied and then "
                "deleted from the tree leaves a schema nobody can rebuild."
            )
        if row.state == "applied" and candidate.sha256 != row.sha256:
            raise MigrationTreeInvalid(
                f"{tree}: {candidate.path.name} changed after it was applied "
                f"(recorded {row.sha256.hex()[:16]}…, on disk "
                f"{candidate.sha256.hex()[:16]}…). Forward-only means the applied file "
                "is history; write a new migration."
            )

    applied_versions = sorted(r.version for r in recorded if r.state == "applied")
    highest_applied = applied_versions[-1] if applied_versions else None

    pending: list[MigrationFile] = []
    for migration in files:
        if migration.version in recorded_by_version:
            continue
        if highest_applied is not None and migration.version < highest_applied:
            raise MigrationTreeInvalid(
                f"{tree}: {migration.path.name} sorts before the last applied version "
                f"{highest_applied!r}. Inserting a statement into applied history would "
                "make the stream unreplayable; renumber it above the head."
            )
        pending.append(migration)

    unresolved = tuple(r for r in recorded if r.state in {"applying", "dirty"})
    return MigrationPlan(
        tree=tree,
        root=root,
        applied=tuple(recorded),
        pending=tuple(pending),
        unresolved=unresolved,
    )


def _record_intent(
    conn: psycopg.Connection[Any], *, tree: str, migration: MigrationFile, who: str
) -> None:
    def body(c: psycopg.Connection[Any]) -> None:
        c.execute(
            """
            INSERT INTO trappoint.schema_migration
                (tree, version, filename, sha256, state, applied_by)
            VALUES (%s, %s, %s, %s, 'applying', %s)
            """,
            (tree, migration.version, migration.path.name, migration.sha256, who),
        )

    in_txn(conn, body)


def _record_success(
    conn: psycopg.Connection[Any], *, tree: str, version: str, job_ids: tuple[str, ...]
) -> None:
    def body(c: psycopg.Connection[Any]) -> None:
        c.execute(
            """
            UPDATE trappoint.schema_migration
               SET state = 'applied', finished_at = now(), job_ids = %s
             WHERE tree = %s AND version = %s AND state = 'applying'
            """,
            (list(job_ids), tree, version),
        )

    in_txn(conn, body)


def _record_dirty(
    conn: psycopg.Connection[Any],
    *,
    tree: str,
    version: str,
    failure: str,
    sqlstate: str | None,
) -> None:
    """Mark the version dirty.

    Best-effort by construction: if this write also fails, the ORIGINAL failure is what
    the operator needs, so this one is never allowed to mask it.
    """

    def body(c: psycopg.Connection[Any]) -> None:
        c.execute(
            """
            UPDATE trappoint.schema_migration
               SET state = 'dirty', failure = %s, failure_sqlstate = %s
             WHERE tree = %s AND version = %s
            """,
            (failure[:4000], sqlstate, tree, version),
        )

    in_txn(conn, body)


def apply(
    conn: psycopg.Connection[Any],
    *,
    tree: str,
    root: Path,
    schema_prefixes: tuple[str, ...] = DEFAULT_SCHEMA_PREFIXES,
    attest_each: bool = True,
    holder: str | None = None,
) -> UpResult:
    """Apply every pending migration under *root*, forward only.

    Raises:
        BootstrapMissing: the ``trappoint`` schema is absent.
        DirtyMigration: an earlier run left an unresolved version.
        MigrationTreeInvalid: disk and database disagree (see :func:`plan`).
        StatementFailed / SchemaJobFailed: a migration was refused; the version is
            marked dirty before the exception leaves this function.
    """
    if not is_bootstrapped(conn):
        raise BootstrapMissing(
            "the `trappoint` schema is absent. Run `trappoint migrate bootstrap` first: "
            "this runner records an attempt before it makes one, and there is nowhere "
            "to record it yet."
        )

    who = holder or actor()
    result = UpResult(tree=tree)

    with lock.hold(conn, holder=who, reason=f"migrate up {tree}") as lease:
        current = plan(conn, tree=tree, root=root)
        if current.unresolved:
            first = current.unresolved[0]
            raise DirtyMigration(
                f"{tree}: version {first.version!r} is {first.state}"
                + (f" — {first.failure}" if first.failure else "")
                + ". Forward progress is refused until a human resolves it: "
                f"`trappoint migrate force {first.version} --incident <id>`. "
                "A dirty schema is a custody event, not a retry."
            )

        held = lease
        for migration in current.pending:
            held = lock.renew(conn, held)
            _record_intent(conn, tree=tree, migration=migration, who=who)
            watermark = datetime.now(UTC)
            try:
                execute_ddl(conn, migration.version, migration.sql)
                job_ids = wait_for_schema_jobs(conn, since=watermark)
            except Exception as exc:
                sqlstate = exc.sqlstate if isinstance(exc, StatementFailed) else None
                _record_dirty(
                    conn,
                    tree=tree,
                    version=migration.version,
                    failure=str(exc),
                    sqlstate=sqlstate,
                )
                raise

            _record_success(conn, tree=tree, version=migration.version, job_ids=job_ids)
            result.applied.append(migration.version)

            if attest_each:
                computed = attestation.stable_fingerprint(conn, schema_prefixes=schema_prefixes)
                ordinal = attestation.append(
                    conn,
                    kind="apply",
                    tree=tree,
                    version=migration.version,
                    attestation=computed,
                    applied_by=who,
                    file_sha256=migration.sha256,
                    job_ids=job_ids,
                )
                result.attestation_ordinals.append(ordinal)
                result.final_fingerprint = computed.digest
                result.grade = computed.grade

        if result.applied and not attest_each:
            computed = attestation.stable_fingerprint(conn, schema_prefixes=schema_prefixes)
            ordinal = attestation.append(
                conn,
                kind="apply",
                tree=tree,
                version=result.applied[-1],
                attestation=computed,
                applied_by=who,
            )
            result.attestation_ordinals.append(ordinal)
            result.final_fingerprint = computed.digest
            result.grade = computed.grade

    return result


def force(
    conn: psycopg.Connection[Any],
    *,
    tree: str,
    version: str,
    incident_id: str,
    resolve_to: str,
    schema_prefixes: tuple[str, ...] = DEFAULT_SCHEMA_PREFIXES,
    holder: str | None = None,
) -> int:
    """Clear a dirty version under a named incident, and record that it happened.

    ``resolve_to`` is ``applied`` (a human verified the statement did take effect) or
    ``pending`` (it did not; delete the row so ``up`` retries it). There is no default:
    the two answers produce different schemas and a runner that guessed would be
    guessing about production.

    A ``force`` writes an attestation row of kind ``force`` carrying the incident id.
    The row's ``force_cites_an_incident`` CHECK makes an unattributed force physically
    impossible to store, which is the point — a dirty schema is a custody event, and the
    ledger has to say who decided it was fine.

    Returns:
        The attestation ordinal written.
    """
    who = holder or actor()
    with lock.hold(conn, holder=who, reason=f"migrate force {tree}/{version}"):
        rows = read_applied(conn, tree)
        match = next((r for r in rows if r.version == version), None)
        if match is None:
            raise MigrationTreeInvalid(
                f"{tree}: no recorded version {version!r} to force. `force` resolves a "
                "recorded failure; it does not invent one."
            )
        if match.state == "applied":
            raise MigrationTreeInvalid(
                f"{tree}: version {version!r} is already `applied`; there is nothing to "
                "force, and forcing an applied version would rewrite history."
            )

        def body(c: psycopg.Connection[Any]) -> None:
            if resolve_to == "pending":
                c.execute(
                    "DELETE FROM trappoint.schema_migration WHERE tree = %s AND version = %s",
                    (tree, version),
                )
            else:
                c.execute(
                    """
                    UPDATE trappoint.schema_migration
                       SET state = 'applied', finished_at = now(),
                           failure = NULL, failure_sqlstate = NULL,
                           forced_incident = %s
                     WHERE tree = %s AND version = %s
                    """,
                    (incident_id, tree, version),
                )

        in_txn(conn, body)

        computed = attestation.stable_fingerprint(conn, schema_prefixes=schema_prefixes)
        return attestation.append(
            conn,
            kind="force",
            tree=tree,
            version=version,
            attestation=computed,
            applied_by=who,
            incident_id=incident_id,
        )
