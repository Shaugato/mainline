# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""One structured answer to "what state is this cluster's migration bookkeeping in?".

`docs/leads/datamodel.md` **DM-13**: the runner owns a bookkeeping schema created
idempotently on connect, **outside the numbered set** — otherwise migration ``0001`` has
nowhere to record that it ran. :mod:`trappoint_migrate.bootstrap` owns the DDL for that
schema and :mod:`trappoint_migrate.lock` owns the lease; this module owns the *reading*
of them, as one value.

**A naming divergence, recorded rather than silently reconciled.** DM-13 names the schema
``trappoint_migration``. The schema that shipped, and that every attestation row in every
existing cluster already lives in, is ``trappoint`` (kernel ruling D6, which also placed
``trappoint.merge_permit()`` there). This module does not rename it. Renaming a schema
that a tamper-evident chain is stored in would require rewriting the chain, and "we
rewrote the ledger to tidy a name" is not a sentence this repository can afford. The
authoritative name is :data:`trappoint_migrate.bootstrap.SCHEMA`, re-exported here as
:data:`SCHEMA` so exactly one string exists.

**Why an inspection type at all, rather than four calls at each call site.** ``status``,
``verify`` and the schema test-suite's health check all need the same five facts, and
each of them is a *refusal condition* for something:

===================== ==========================================================
``bootstrapped``      ``apply`` refuses without it — a migration with no record
``lock``              a held lease means another migrator is mid-stream
``unresolved``        a ``dirty`` or ``applying`` row refuses forward progress
``chain_head``        what the schema is attested to be
``chain_findings``    a gap means a row was deleted; a mismatch means one was rewritten
===================== ==========================================================

Assembling them once, in one order, means a caller cannot report "chain intact" while
holding a stale head, and cannot report "clean" while a lease is held by somebody else.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import psycopg
from psycopg.rows import dict_row

from . import runner
from .attest import ChainHead, chain_head, verify_chain
from .bootstrap import BOOKKEEPING_TABLES, SCHEMA, bootstrap, is_bootstrapped
from .errors import AttestationDrift
from .lock import LOCK_NAME

__all__ = [
    "BOOKKEEPING_TABLES",
    "SCHEMA",
    "BookkeepingStatus",
    "LockState",
    "ensure",
    "inspect",
    "present_tables",
]


@dataclass(frozen=True, slots=True)
class LockState:
    """Who holds the migration lease, and whether the lease is still alive.

    ``expired`` is computed here rather than left to the reader because a lease row that
    has passed its expiry is *takeable*, and a status line that printed a stale holder
    without saying so would read as "somebody is migrating" when nobody is.
    """

    holder: str
    acquired_at: datetime
    expires_at: datetime
    reason: str

    @property
    def expired(self) -> bool:
        """True when the lease has passed its expiry and may be taken over."""
        return self.expires_at <= datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class BookkeepingStatus:
    """Everything the runner knows about its own state on one cluster, for one tree."""

    schema: str
    tree: str
    bootstrapped: bool
    tables: tuple[str, ...]
    """The bookkeeping tables that exist. Fewer than three is not 'partly bootstrapped',
    it is not bootstrapped — see :func:`trappoint_migrate.bootstrap.is_bootstrapped`."""
    lock: LockState | None
    applied: tuple[runner.AppliedRow, ...]
    unresolved: tuple[runner.AppliedRow, ...]
    chain_head: ChainHead | None
    chain_findings: tuple[str, ...]

    @property
    def missing_tables(self) -> tuple[str, ...]:
        """Bookkeeping tables the schema should carry and does not."""
        return tuple(name for name in BOOKKEEPING_TABLES if name not in self.tables)

    @property
    def applied_count(self) -> int:
        """How many versions are recorded ``applied`` for this tree."""
        return sum(1 for row in self.applied if row.state == "applied")

    @property
    def is_clean(self) -> bool:
        """True when nothing refuses: bootstrapped, no unresolved version, chain intact.

        A held-but-live lease is deliberately **not** part of this. Another migrator
        holding the lease is a normal concurrent state, not a fault in this cluster's
        bookkeeping, and conflating the two would make ``verify`` fail during any
        deployment that happened to overlap it.
        """
        return self.bootstrapped and not self.unresolved and not self.chain_findings

    def render(self) -> list[str]:
        """Human-readable lines, most-refusing first. The CLI prints these verbatim."""
        lines = [f"schema {self.schema} · tree {self.tree}"]
        if not self.bootstrapped:
            lines.append(
                f"  NOT BOOTSTRAPPED — missing {list(self.missing_tables)}; "
                "run `trappoint migrate bootstrap`"
            )
            return lines
        lines.append(f"  applied     {self.applied_count}")
        lines.append(f"  unresolved  {len(self.unresolved)}")
        for row in self.unresolved:
            lines.append(
                f"    ! {row.version} [{row.state}] "
                f"{row.failure_sqlstate or ''} {row.failure or ''}".rstrip()
            )
        if self.lock is None:
            lines.append("  lease       free")
        else:
            state = "EXPIRED" if self.lock.expired else "held"
            lines.append(
                f"  lease       {state} by {self.lock.holder} until "
                f"{self.lock.expires_at.isoformat()} ({self.lock.reason})"
            )
        if self.chain_head is not None:
            lines.append(
                f"  attestation ordinal {self.chain_head.ordinal} kind "
                f"{self.chain_head.kind} grade {self.chain_head.grade} · "
                f"{self.chain_head.fingerprint.hex()}"
            )
        for finding in self.chain_findings:
            lines.append(f"    ! CHAIN {finding}")
        if not self.chain_findings and self.chain_head is not None:
            lines.append("  chain       intact (dense, every prev_fingerprint matches)")
        return lines


def present_tables(conn: psycopg.Connection[Any]) -> tuple[str, ...]:
    """Which of the three bookkeeping tables currently exist, in declaration order."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = %s AND table_name = ANY(%s)
            """,
            (SCHEMA, list(BOOKKEEPING_TABLES)),
        )
        found = {str(row["table_name"]) for row in cur.fetchall()}
    return tuple(name for name in BOOKKEEPING_TABLES if name in found)


def _lock_state(conn: psycopg.Connection[Any]) -> LockState | None:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT holder, acquired_at, expires_at, reason
            FROM trappoint.schema_lock WHERE lock_name = %s
            """,
            (LOCK_NAME,),
        )
        row = cur.fetchone()
    if row is None:
        return None
    return LockState(
        holder=str(row["holder"]),
        acquired_at=row["acquired_at"],
        expires_at=row["expires_at"],
        reason=str(row["reason"]),
    )


def ensure(conn: psycopg.Connection[Any], *, applied_by: str | None = None) -> list[str]:
    """Create the bookkeeping schema if it is absent. Idempotent (DM-13).

    Thin on purpose: the DDL belongs to :mod:`trappoint_migrate.bootstrap` and there is
    no second copy of it here. What this adds is a name a caller can reach for without
    having to know that "bootstrap" is where a *schema* comes from.

    Returns:
        The names of the objects the call ensured, in order.
    """
    return bootstrap(
        conn,
        applied_by=applied_by or runner.actor(),
        schema_prefixes=runner.DEFAULT_SCHEMA_PREFIXES,
    )


def inspect(conn: psycopg.Connection[Any], *, tree: str) -> BookkeepingStatus:
    """Read every bookkeeping fact about *tree* on this cluster, in one pass.

    Reads only. An un-bootstrapped cluster produces a status saying so rather than an
    exception, because "there is nothing here yet" is a legitimate answer to a status
    question and the caller that must refuse on it (``apply``) refuses on the field.
    """
    if not is_bootstrapped(conn):
        return BookkeepingStatus(
            schema=SCHEMA,
            tree=tree,
            bootstrapped=False,
            tables=present_tables(conn),
            lock=None,
            applied=(),
            unresolved=(),
            chain_head=None,
            chain_findings=(),
        )

    applied = tuple(runner.read_applied(conn, tree))
    findings = tuple(verify_chain(conn))
    try:
        head: ChainHead | None = chain_head(conn)
    except AttestationDrift:
        # An empty chain is already reported by `verify_chain` as a finding, and it is
        # the more precise sentence of the two. Raising here as well would turn a
        # complete report into a stack trace.
        head = None

    return BookkeepingStatus(
        schema=SCHEMA,
        tree=tree,
        bootstrapped=True,
        tables=present_tables(conn),
        lock=_lock_state(conn),
        applied=applied,
        unresolved=tuple(row for row in applied if row.state in {"applying", "dirty"}),
        chain_head=head,
        chain_findings=findings,
    )
