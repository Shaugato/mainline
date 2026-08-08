# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The SQL boundary: two protocols and one thin psycopg adapter.

Everything in this subpackage talks to CockroachDB through :class:`SqlSession`, which is a
callable-shaped protocol rather than a driver. Three things follow, and all three are the
reason the boundary exists:

* the orchestrator's tests run the whole run loop — channels, fusion, conservation,
  persistence, the kernel POST — with no cluster, against a recorded session, and the code
  under test is the shipped code rather than a second implementation;
* the same statements can be executed over the Managed MCP `select_query` path, which is how
  a claim about our SQL becomes a claim proven on CockroachDB's own endpoint;
* the driver stays a leaf dependency, so `import mainline_recall_agent.run` works on a
  machine with no `psycopg` and no cluster — the CI and demo default.

SQLSTATE handling is here rather than at each call site because the classification is a
product rule, not a detail: `40001` is the only retryable code, `23514` / `23503` / `23505` /
`P0001` are refusals attempted exactly once, and anything else is a defect. **A blanket-retry
helper is banned repository-wide** (ARCHITECTURE 6.5), so what this module offers instead is
:func:`classify_sqlstate` — a function that tells a caller which of the three a failure is and
makes the caller decide, in code a reader can see.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from typing import Any, Literal, Protocol, runtime_checkable

from mainline_recall_agent.run.errors import (
    GATE_REFUSAL_SQLSTATES,
    RETRYABLE_SQLSTATES,
)

__all__ = [
    "Failure",
    "SqlSession",
    "Transactional",
    "classify_sqlstate",
    "psycopg_session",
    "sqlstate_of",
]

Failure = Literal["retryable", "refusal", "unmodelled"]


@runtime_checkable
class SqlSession(Protocol):
    """The minimum a recall run needs from a database connection."""

    def query(self, sql: str, params: Sequence[object] = ()) -> Sequence[Sequence[Any]]:
        """Execute ``sql`` and return every row."""
        ...

    def execute(self, sql: str, params: Sequence[object] = ()) -> None:
        """Execute ``sql`` for effect."""
        ...


@runtime_checkable
class Transactional(Protocol):
    """Something that can open a SERIALIZABLE transaction and hand back a session."""

    def transaction(self) -> Any:
        """A context manager yielding an :class:`SqlSession` bound to one transaction."""
        ...


def sqlstate_of(exc: BaseException) -> str | None:
    """Extract a SQLSTATE from a driver exception without importing the driver.

    ``psycopg`` exposes it as ``.sqlstate``; several wrappers expose ``.pgcode``. Both are
    read by name so this module keeps no driver import at all.
    """
    for attribute in ("sqlstate", "pgcode"):
        value = getattr(exc, attribute, None)
        if isinstance(value, str) and value:
            return value
    return None


def classify_sqlstate(sqlstate: str | None) -> Failure:
    """Classify a SQLSTATE into the three categories ARCHITECTURE 16 defines.

    Returns:
        ``"retryable"`` for ``40001``; ``"refusal"`` for ``23514`` / ``23503`` / ``23505`` /
        ``P0001``; ``"unmodelled"`` for everything else, including ``None``.

    An unknown code is deliberately *not* treated as retryable. Retrying a refusal nobody
    modelled is how a gate quietly stops being a gate.
    """
    if sqlstate in RETRYABLE_SQLSTATES:
        return "retryable"
    if sqlstate in GATE_REFUSAL_SQLSTATES:
        return "refusal"
    return "unmodelled"


class _PsycopgSession:
    """An :class:`SqlSession` over one psycopg connection or transaction."""

    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def query(self, sql: str, params: Sequence[object] = ()) -> Sequence[Sequence[Any]]:
        """Execute and fetch. ``params`` is positional, matching ``$1``-style placeholders."""
        with self._connection.cursor() as cursor:
            cursor.execute(sql, tuple(params))
            rows = cursor.fetchall()
        return [tuple(row) for row in rows]

    def execute(self, sql: str, params: Sequence[object] = ()) -> None:
        """Execute for effect."""
        with self._connection.cursor() as cursor:
            cursor.execute(sql, tuple(params))


class PsycopgTransactional:
    """Opens SERIALIZABLE transactions on a psycopg connection.

    The isolation level is **asserted, never inherited** (ARCHITECTURE 6.5). CockroachDB's
    default is SERIALIZABLE, and that is exactly why the statement is issued anyway: a cluster
    setting, a connection-string parameter or a pooler that changed it would otherwise
    downgrade the guarantee with nothing in the code to read.
    """

    def __init__(self, connection: Any) -> None:
        """Wrap an already-open psycopg connection. Connection lifetime is the caller's."""
        self._connection = connection

    @contextmanager
    def transaction(self) -> Iterator[SqlSession]:
        """Yield a session bound to one SERIALIZABLE transaction."""
        with self._connection.transaction():
            session = _PsycopgSession(self._connection)
            session.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
            yield session


@contextmanager
def psycopg_session(dsn: str) -> Iterator[PsycopgTransactional]:
    """Open a connection and yield something that can start SERIALIZABLE transactions.

    ``psycopg`` is imported here rather than at module scope on purpose: the cassette and
    fixture paths — the CI and demo default — must work on a machine where no driver is
    installed. That deferred import is the documented exception PLC0415 is disabled for.
    """
    import psycopg  # noqa: PLC0415 - see the docstring; the driver must stay optional

    with psycopg.connect(dsn) as connection:
        yield PsycopgTransactional(connection)
