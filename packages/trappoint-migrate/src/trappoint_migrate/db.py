# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Connection discipline: isolation, the one retryable code, and job waiting.

Three rules, each of which is a claim made elsewhere in the repository:

1. **Isolation is set explicitly, never inherited from a pool default.**
   ``spec/errors.md`` §2.1 makes this normative. psycopg emits
   ``BEGIN ISOLATION LEVEL SERIALIZABLE`` when the connection carries the level, so
   the level is visible in the wire log rather than assumed from a server default.

2. **``40001`` is the only code that is ever retried, and only for bookkeeping
   transactions.** The retry loop is hand-written here — capped exponential backoff
   with full jitter, bounded attempts — because a decorator that retries "on
   exception" cannot tell an undecided transaction from a decided refusal.
   ``.importlinter`` contract 4 forbids ``tenacity``/``backoff``/``retrying``
   repository-wide so this stays the only loop.

3. **A DDL statement is attempted exactly once, ever.** It is *not* retried, not even
   on ``40001``. A CockroachDB DDL statement starts a background job; "did it happen"
   is answered by ``SHOW JOBS``, not by issuing it again and hoping.
"""

from __future__ import annotations

import random
import time
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, TypeVar

import psycopg
from psycopg import sql as pgsql
from psycopg.rows import dict_row

from .crdb import (
    SCHEMA_CHANGE_JOB_TYPES,
    TERMINAL_FAILURE_STATUSES,
    TERMINAL_SUCCESS_STATUSES,
)
from .errors import ClusterUnreachable, SchemaJobFailed, StatementFailed, UsageError

if TYPE_CHECKING:  # pragma: no cover - typing only
    from datetime import datetime

__all__ = [
    "APPLICATION_NAME",
    "JobRecord",
    "connect",
    "execute_ddl",
    "fetch_all",
    "in_txn",
    "wait_for_schema_jobs",
]

T = TypeVar("T")

APPLICATION_NAME = "trappoint-migrate"

# Bounded, and the bound is small on purpose. Eight attempts of capped-and-jittered
# backoff is about six seconds of contention tolerance; past that, something is holding
# a conflicting transaction and the honest thing is to say so rather than to keep
# trying under a lock lease that is also expiring.
_MAX_ATTEMPTS = 8
_BASE_DELAY_S = 0.05
_CAP_DELAY_S = 2.0

_UNDEFINED_COLUMN = "42703"


def _full_jitter(attempt: int, rng: random.Random) -> float:
    """Capped exponential backoff with FULL jitter: ``U(0, min(cap, base·2^n))``.

    Full jitter rather than equal jitter because the failure mode being defended
    against is N migrators (or N conformance workers) retrying in lockstep, and only
    full jitter spreads a synchronised herd on the first retry.
    """
    ceiling = min(_CAP_DELAY_S, _BASE_DELAY_S * (2**attempt))
    return rng.uniform(0.0, ceiling)


@dataclass(frozen=True, slots=True)
class JobRecord:
    """One row of ``SHOW JOBS``, reduced to what the runner decides on."""

    job_id: str
    job_type: str
    status: str
    description: str
    error: str


@contextmanager
def connect(dsn: str, *, autocommit: bool = True) -> Iterator[psycopg.Connection[Any]]:
    """Open a connection with the migrator's discipline applied.

    Autocommit is the default because DDL is issued outside an explicit transaction;
    :func:`in_txn` opens one explicitly for bookkeeping writes.
    """
    try:
        conn = psycopg.connect(dsn, autocommit=autocommit, application_name=APPLICATION_NAME)
    except psycopg.OperationalError as exc:
        raise ClusterUnreachable(f"cannot connect: {str(exc).strip()}") from exc
    try:
        # Explicit, per spec/errors.md §2.1. CockroachDB's default is SERIALIZABLE, and
        # this line exists precisely so that the claim does not rest on that default.
        conn.isolation_level = psycopg.IsolationLevel.SERIALIZABLE
        yield conn
    finally:
        conn.close()


def in_txn[T](
    conn: psycopg.Connection[Any],
    body: Callable[[psycopg.Connection[Any]], T],
    *,
    attempts: int = _MAX_ATTEMPTS,
    rng: random.Random | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    """Run *body* in one SERIALIZABLE transaction, retrying only ``40001``.

    The whole transaction is retried from ``BEGIN``, never a statement, and *body* must
    therefore be free of side effects outside the database.

    Every other SQLSTATE propagates on the first attempt. That is the point: a ``23505``
    from the attestation chain's ``UNIQUE (prev_ordinal)`` means another migrator
    already appended, and retrying it would turn a detected race into a silent one.
    """
    if attempts < 1:
        raise UsageError("in_txn needs at least one attempt")
    jitter = rng if rng is not None else random.SystemRandom()
    last: psycopg.errors.SerializationFailure | None = None
    for attempt in range(attempts):
        try:
            with conn.transaction():
                return body(conn)
        except psycopg.errors.SerializationFailure as exc:  # 40001, and only 40001
            last = exc
            if attempt + 1 < attempts:
                sleep(_full_jitter(attempt, jitter))
    raise last  # type: ignore[misc]


def execute_ddl(conn: psycopg.Connection[Any], version: str, statement: str) -> None:
    """Issue one DDL statement in autocommit, exactly once.

    Raises:
        StatementFailed: carrying the SQLSTATE and the database's own message. The
            caller marks the version dirty; it does not try again.
    """
    try:
        conn.execute(statement)
    except psycopg.Error as exc:
        sqlstate = exc.diag.sqlstate if exc.diag is not None else None
        raise StatementFailed(version, sqlstate, str(exc).strip()) from exc


def _show_jobs(conn: psycopg.Connection[Any], since: datetime | None) -> list[dict[str, Any]]:
    """Read schema-change jobs, tolerating column-name drift across versions.

    ``SHOW JOBS`` is an observability surface, not a stable API, and its column set has
    moved between releases. Rather than assert a shape, the runner asks for everything
    and reads the columns it needs by name — falling back to an unfiltered read if the
    ``created`` column is not present under that name.
    """
    types = pgsql.SQL(", ").join(pgsql.Literal(t) for t in SCHEMA_CHANGE_JOB_TYPES)
    filtered = pgsql.SQL(
        "SELECT * FROM [SHOW JOBS] WHERE job_type IN ({types}) AND created >= %s"
    ).format(types=types)
    unfiltered = pgsql.SQL("SELECT * FROM [SHOW JOBS] WHERE job_type IN ({types})").format(
        types=types
    )
    with conn.cursor(row_factory=dict_row) as cur:
        if since is not None:
            try:
                cur.execute(filtered, (since,))
                return list(cur.fetchall())
            except psycopg.Error as exc:
                state = exc.diag.sqlstate if exc.diag is not None else None
                if state != _UNDEFINED_COLUMN:
                    raise
        cur.execute(unfiltered)
        return list(cur.fetchall())


def _status_of(row: dict[str, Any]) -> str:
    for key in ("status", "job_status", "state"):
        value = row.get(key)
        if isinstance(value, str):
            return value.lower()
    return "unknown"


def wait_for_schema_jobs(
    conn: psycopg.Connection[Any],
    *,
    since: datetime | None,
    timeout_s: float = 900.0,
    poll_s: float = 0.5,
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], float] = time.monotonic,
) -> tuple[str, ...]:
    """Block until every schema-change job created since *since* is terminal.

    The statement returning is not the schema change finishing
    (research/06-build/schema-migrations.md §2.2). The version must not advance until
    the job does, because a recorded migration whose job is still reverting is a record
    of something that did not happen.

    ``SHOW JOBS WHEN COMPLETE`` exists and blocks for up to 24 hours; polling is used
    here so the runner keeps its lock lease renewed and can report progress.

    Returns:
        The job ids observed, for ``schema_migration.job_ids``.

    Raises:
        SchemaJobFailed: on a terminal non-success status, or on timeout.
    """
    deadline = now() + timeout_s
    seen: dict[str, JobRecord] = {}
    while True:
        rows = _show_jobs(conn, since)
        pending: list[JobRecord] = []
        for row in rows:
            record = JobRecord(
                job_id=str(row.get("job_id", "")),
                job_type=str(row.get("job_type", "")),
                status=_status_of(row),
                description=str(row.get("description", ""))[:400],
                error=str(row.get("error", "") or ""),
            )
            seen[record.job_id] = record
            if record.status in TERMINAL_FAILURE_STATUSES:
                raise SchemaJobFailed(
                    f"schema-change job {record.job_id} is {record.status}: "
                    f"{record.error or record.description}"
                )
            if record.status not in TERMINAL_SUCCESS_STATUSES:
                pending.append(record)

        if not pending:
            return tuple(sorted(seen))

        if now() >= deadline:
            names = ", ".join(f"{j.job_id}({j.status})" for j in pending)
            raise SchemaJobFailed(
                f"schema-change jobs did not reach a terminal state within {timeout_s:.0f}s: "
                f"{names}. The version is NOT advanced; inspect SHOW JOBS before retrying."
            )
        sleep(poll_s)


def fetch_all(
    conn: psycopg.Connection[Any], statement: str, params: Sequence[Any] | None = None
) -> list[dict[str, Any]]:
    """Run a read and return dict rows. A thin helper, used by ``attest`` and ``status``."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(statement, params)
        return list(cur.fetchall())
