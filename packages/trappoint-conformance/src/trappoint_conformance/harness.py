# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Running a history and asserting exactly what the database said.

The assertion contract, from ``spec/errors.md`` §3.1 and
``spec/conformance/README.md`` §1:

    A test asserting only a SQLSTATE is **not conformant**. *"An exception was raised"*
    is worthless in a product whose deliverable is the diagnosis.

So every assertion names two things: the code, and the **exhibit**. For
``23514``/``23503``/``23505`` the exhibit is ``diag.constraint_name`` verbatim. For
``P0001`` ``diag.constraint_name`` is empty by construction, and the exhibit is the
fully-qualified name of the raising object — which the message convention makes
recoverable, and which this module marks as **weakened** when it had to be inferred. A
run whose exhibits were inferred is never indistinguishable from a run whose exhibits
were reported.

The retry discipline lives here too, and it is deliberately tiny: ``40001`` is retried
with capped backoff and full jitter; the four refusal codes are attempted **exactly
once, ever**. That is not a performance decision. If a client retries a ``23514``, the
refusal ledger holds five identical refusals for one attempted history and the count of
refusals stops being a count of anything.
"""

from __future__ import annotations

import random
import time
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

import psycopg
from psycopg import sql as pgsql

from .sqlstate import Outcome, UnmodelledRefusal, classify, describe, is_schema_absent

__all__ = [
    "ConformanceFailure",
    "Harness",
    "HistoryOutcome",
    "Step",
    "assert_admitted",
    "assert_refusal",
]

_MAX_RETRY_ATTEMPTS = 6
_BASE_DELAY_S = 0.02
_CAP_DELAY_S = 1.0

# The message-prefix convention of spec/errors.md §3.2: `<PREFIX>: <one sentence>`.
_KNOWN_PREFIXES = ("TRAPPOINT", "MAINLINE")


class ConformanceFailure(AssertionError):
    """A case did not observe what the manifest says it must."""


@dataclass(frozen=True, slots=True)
class Step:
    """One statement in a history, with a label that appears in the failure report.

    ``sql`` is a ``str`` or a ``psycopg.sql.Composable``. The second form is how a schema
    name reaches a statement: it is a quoted IDENTIFIER, never interpolated text, because
    the profile-to-schema mapping can be overridden from the command line and a
    conformance runner that could be made to execute arbitrary SQL by a ``--schema`` flag
    would be a poor advertisement for a product about refusing bad writes.
    """

    label: str
    sql: str | pgsql.SQL | pgsql.Composed
    params: tuple[Any, ...] = ()


@dataclass(slots=True)
class HistoryOutcome:
    """What the database did with a history.

    ``completed`` is True when every step succeeded — the expectation for an ``admit``
    case, and a failure for every other class.
    """

    case_id: str
    completed: bool
    sqlstate: str
    constraint: str
    message: str
    failing_step: str = ""
    exhibit_weakened: bool = False
    """True when the exhibit was inferred from the message rather than reported by the
    driver. Recorded, printed, and never silently equivalent to a reported exhibit."""
    retries: int = 0
    stored: dict[str, Any] = field(default_factory=dict)
    """Rows read back after the history, for cases carrying ``asserts_stored_row``. The
    rewrite is the claim; the refusal is the consequence."""

    @property
    def outcome(self) -> Outcome:
        """The expectation class of the observed SQLSTATE.

        Raises:
            UnmodelledRefusal: the taxonomy is total, so this is a suite failure.
        """
        return classify(self.sqlstate)

    def summary(self) -> str:
        """One line, for a report."""
        if self.completed:
            return f"{self.case_id}: completed (00000)"
        weak = " (exhibit inferred)" if self.exhibit_weakened else ""
        return (
            f"{self.case_id}: {self.sqlstate} on {self.constraint or '<no exhibit>'}{weak}"
            f" at step {self.failing_step!r}"
        )


def _full_jitter(attempt: int, rng: random.Random) -> float:
    return rng.uniform(0.0, min(_CAP_DELAY_S, _BASE_DELAY_S * (2**attempt)))


def _infer_exhibit(message: str) -> str:
    """Recover a ``P0001`` exhibit from the message prefix.

    The driver reports no constraint name for a deliberate ``RAISE``, so the exhibit has
    to come from somewhere. The convention gives a prefix; the prefix gives the vertical
    whose trigger raised. This is strictly weaker than a reported name and the caller
    records that it was inferred.
    """
    head = message.strip().split(":", 1)[0].strip()
    if head in _KNOWN_PREFIXES:
        return f"{head.lower()}:<raising object not reported by the driver>"
    return ""


class Harness:
    """A connection plus the discipline every case runs under."""

    def __init__(
        self,
        conn: psycopg.Connection[Any],
        *,
        rng: random.Random | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        """Bind a connection, seed the jitter source, and set the isolation level."""
        self.conn = conn
        self._rng = rng or random.SystemRandom()
        self._sleep = sleep
        # Explicit, never inherited from a pool default (spec/errors.md §2.1).
        self.conn.isolation_level = psycopg.IsolationLevel.SERIALIZABLE

    @contextmanager
    def savepoint(self, name: str) -> Iterator[None]:
        """Open a nested savepoint, so a probe that fails does not abort the history.

        CockroachDB supports general-purpose nested savepoints, which is what makes the
        QUICKREFUSE probe loop legal. It is exposed here because a case that attempts a
        step it expects to fail and then continues needs the same mechanism.
        """
        with self.conn.transaction(savepoint_name=name):
            yield

    def read(self, sql: str, params: Sequence[Any] = ()) -> list[tuple[Any, ...]]:
        """Run a read. Used only by ``asserts_stored_row`` checks."""
        with self.conn.cursor() as cur:
            cur.execute(sql, params)
            return list(cur.fetchall())

    def run_history(self, case_id: str, steps: Sequence[Step]) -> HistoryOutcome:
        """Execute *steps* in one transaction and report what the database said.

        The whole transaction is retried on ``40001`` and on nothing else. The first
        step to fail with any other code ends the history and becomes the observation.
        """
        for attempt in range(_MAX_RETRY_ATTEMPTS):
            try:
                with self.conn.transaction():
                    for step in steps:
                        with self.conn.cursor() as cur:
                            cur.execute(step.sql, step.params)
                return HistoryOutcome(
                    case_id=case_id,
                    completed=True,
                    sqlstate="00000",
                    constraint="",
                    message="",
                    retries=attempt,
                )
            except psycopg.errors.SerializationFailure as exc:
                if attempt + 1 >= _MAX_RETRY_ATTEMPTS:
                    return HistoryOutcome(
                        case_id=case_id,
                        completed=False,
                        sqlstate="40001",
                        constraint="",
                        message=str(exc).strip(),
                        retries=attempt + 1,
                    )
                self._sleep(_full_jitter(attempt, self._rng))
            except psycopg.Error as exc:
                return self._observe(case_id, exc, steps, retries=attempt)

        raise AssertionError("unreachable: the retry loop always returns")  # pragma: no cover

    def _observe(
        self,
        case_id: str,
        exc: psycopg.Error,
        steps: Sequence[Step],
        *,
        retries: int,
    ) -> HistoryOutcome:
        diag = exc.diag
        sqlstate = (diag.sqlstate if diag is not None else None) or "XXUUU"
        constraint = (diag.constraint_name if diag is not None else None) or ""
        message = (diag.message_primary if diag is not None else None) or str(exc).strip()

        weakened = False
        if not constraint and sqlstate == "P0001":
            constraint = _infer_exhibit(message)
            weakened = bool(constraint)

        # Which step failed. psycopg does not report it, so the label is recovered by
        # matching the statement text the driver echoes where it does; otherwise the
        # history is short enough that naming the last-attempted step is honest.
        failing = ""
        for step in steps:
            text = step.sql if isinstance(step.sql, str) else step.sql.as_string(self.conn)
            probe = text.strip()[:40]
            if probe and probe in str(exc):
                failing = step.label
                break

        return HistoryOutcome(
            case_id=case_id,
            completed=False,
            sqlstate=sqlstate,
            constraint=constraint,
            message=message,
            failing_step=failing,
            exhibit_weakened=weakened,
            retries=retries,
        )


def assert_refusal(history: HistoryOutcome, sqlstate: str, constraint: str) -> None:
    """Assert that *history* was refused with exactly *sqlstate* on exactly *constraint*.

    Three distinct failures, reported distinctly because they mean different things:

    * the history **completed** — the gate admitted a write it must refuse;
    * the code is outside the modelled taxonomy — the database refused for a reason
      nobody modelled, which is a defect rather than an edge case;
    * the code matches but the exhibit does not — the right refusal from the wrong
      mechanism, which reads as a pass to anyone not looking closely and is exactly what
      naming the exhibit exists to catch.

    Raises:
        ConformanceFailure: on any of the three.
    """
    if history.completed:
        raise ConformanceFailure(
            f"{history.case_id}: the history COMPLETED. Expected {sqlstate} on "
            f"{constraint!r}. A gate that admits this write is not a gate."
        )

    if history.sqlstate != sqlstate:
        try:
            classify(history.sqlstate)
        except UnmodelledRefusal as unmodelled:
            hint = ""
            if is_schema_absent(history.sqlstate):
                hint = (
                    " The object this case needs has not been created yet: this is the "
                    "expected RED state before the migration that owns the case lands."
                )
            raise ConformanceFailure(
                f"{history.case_id}: expected {sqlstate} on {constraint!r}; observed "
                f"{unmodelled}.{hint} Message: {history.message}"
            ) from unmodelled
        raise ConformanceFailure(
            f"{history.case_id}: expected {sqlstate} on {constraint!r}; observed "
            f"{describe(history.sqlstate)} on {history.constraint or '<no exhibit>'}. "
            f"Message: {history.message}"
        )

    if history.constraint != constraint:
        raise ConformanceFailure(
            f"{history.case_id}: {sqlstate} was raised, but by "
            f"{history.constraint or '<no exhibit>'}, not by {constraint!r}. The "
            "constraint name is the exhibit; the right code from the wrong mechanism is "
            "not a pass."
        )


def assert_admitted(history: HistoryOutcome) -> None:
    """Assert an ``admit``-class history completed.

    A gate that refuses everything is not a gate, and three cases in the manifest exist
    only to say so.
    """
    if not history.completed:
        raise ConformanceFailure(
            f"{history.case_id}: the history must COMPLETE, but was refused with "
            f"{describe(history.sqlstate)} on {history.constraint or '<no exhibit>'}. "
            f"Message: {history.message}"
        )
