# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""A real lock table, because CockroachDB has no advisory locks.

``pg_advisory_lock`` does not exist in CockroachDB. Every PostgreSQL migration tool
that "just works" is relying on a session-scoped mutex that is not there, so the lease
has to be a row — and a row-based lease has properties a session lock does not, all of
which are visible here rather than hidden:

* **it outlives the process**, so a killed migrator leaves the lease held and the next
  run must decide what to do about it. It waits for expiry; it never steals.
* **it has to be renewed**, because a long schema change can outlast any lease short
  enough to be useful after a crash.
* **taking it over is a conditional UPDATE**, not a delete-then-insert. The condition
  ``expires_at < now()`` is evaluated by the database, so two migrators racing to
  reclaim one expired lease cannot both win.

The acquisition is written as INSERT-then-conditional-UPDATE rather than as
``INSERT … ON CONFLICT … DO UPDATE … WHERE``. Both are legal; the two-step form is
unambiguously legal on every version, and a migration runner is the wrong place to be
clever about upsert semantics.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import psycopg
from psycopg.rows import dict_row

from .db import in_txn
from .errors import LockUnavailable

__all__ = ["DEFAULT_LEASE", "LOCK_NAME", "LockLease", "hold", "release", "renew"]

DEFAULT_LEASE = timedelta(minutes=10)
LOCK_NAME = "migrate"


@dataclass(frozen=True, slots=True)
class LockLease:
    """A held lease. ``holder`` is what another migrator will be told is in the way."""

    lock_name: str
    holder: str
    expires_at: datetime


def _try_acquire(
    conn: psycopg.Connection[Any], *, holder: str, reason: str, lease: timedelta
) -> LockLease | None:
    expires_at = datetime.now(UTC) + lease

    def insert(c: psycopg.Connection[Any]) -> LockLease | None:
        try:
            c.execute(
                """
                INSERT INTO trappoint.schema_lock (lock_name, holder, expires_at, reason)
                VALUES (%s, %s, %s, %s)
                """,
                (LOCK_NAME, holder, expires_at, reason),
            )
        except psycopg.errors.UniqueViolation:
            return None
        return LockLease(LOCK_NAME, holder, expires_at)

    acquired = in_txn(conn, insert)
    if acquired is not None:
        return acquired

    def take_over(c: psycopg.Connection[Any]) -> LockLease | None:
        with c.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                UPDATE trappoint.schema_lock
                   SET holder = %s, acquired_at = now(), expires_at = %s, reason = %s
                 WHERE lock_name = %s
                   AND expires_at < now()
                RETURNING holder, expires_at
                """,
                (holder, expires_at, reason, LOCK_NAME),
            )
            row = cur.fetchone()
        if row is None:
            return None
        return LockLease(LOCK_NAME, str(row["holder"]), row["expires_at"])

    return in_txn(conn, take_over)


def _current_holder(conn: psycopg.Connection[Any]) -> tuple[str, datetime] | None:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "SELECT holder, expires_at FROM trappoint.schema_lock WHERE lock_name = %s",
            (LOCK_NAME,),
        )
        row = cur.fetchone()
    if row is None:
        return None
    return str(row["holder"]), row["expires_at"]


def renew(
    conn: psycopg.Connection[Any], lease: LockLease, *, extend: timedelta = DEFAULT_LEASE
) -> LockLease:
    """Extend *lease*, refusing if it is no longer ours.

    Renewal is conditional on the holder still being us. A migrator whose lease expired
    while a schema change was running has already lost it, and continuing to apply
    migrations under a lease someone else now holds is exactly the concurrent stream the
    lock exists to prevent.
    """
    expires_at = datetime.now(UTC) + extend

    def body(c: psycopg.Connection[Any]) -> int:
        cur = c.execute(
            """
            UPDATE trappoint.schema_lock
               SET expires_at = %s
             WHERE lock_name = %s AND holder = %s
            """,
            (expires_at, lease.lock_name, lease.holder),
        )
        return cur.rowcount

    if in_txn(conn, body) != 1:
        held = _current_holder(conn)
        who = held[0] if held else "nobody"
        raise LockUnavailable(
            f"the migration lease is no longer held by {lease.holder!r} (now {who!r}); "
            "refusing to continue applying migrations under a lease we do not hold"
        )
    return LockLease(lease.lock_name, lease.holder, expires_at)


def release(conn: psycopg.Connection[Any], lease: LockLease) -> None:
    """Release *lease* if we still hold it.

    Silent when we do not: the lease expired and somebody else took it over, which they
    report themselves. Complaining here would produce two messages about one fact.
    """

    def body(c: psycopg.Connection[Any]) -> None:
        c.execute(
            "DELETE FROM trappoint.schema_lock WHERE lock_name = %s AND holder = %s",
            (lease.lock_name, lease.holder),
        )

    in_txn(conn, body)


@contextmanager
def hold(
    conn: psycopg.Connection[Any],
    *,
    holder: str,
    reason: str,
    lease: timedelta = DEFAULT_LEASE,
) -> Iterator[LockLease]:
    """Hold the migration lease for the duration of the block.

    Raises:
        LockUnavailable: immediately, naming the current holder and when their lease
            expires. It does not wait: two migration streams against one cluster is an
            operational mistake, and a runner that queues behind one makes it slower to
            notice rather than impossible to make.
    """
    acquired = _try_acquire(conn, holder=holder, reason=reason, lease=lease)
    if acquired is None:
        held = _current_holder(conn)
        if held is None:
            raise LockUnavailable(
                "could not acquire the migration lease and no holder is recorded; "
                "another migrator released it between the two statements — retry once"
            )
        who, until = held
        raise LockUnavailable(
            f"the migration lease is held by {who!r} until {until.isoformat()}. "
            "This runner refuses rather than waits: two concurrent migration streams "
            "against one cluster is not a queueing problem."
        )
    try:
        yield acquired
    finally:
        release(conn, acquired)
