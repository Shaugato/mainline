# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The conditions this package refuses to paper over.

Every exception here names a way a fixity patrol could quietly become wrong, and
each one is raised in exactly one place. There is no generic ``FixityFailed``,
because a patrol that reports "something went wrong" has told a reviewer nothing
they can act on — and the diagnosis is the deliverable.

``N818`` (exception names must end in ``Error``) is disabled repository-wide on
purpose: the refusal vocabulary is a product surface, and these words appear in
operator-facing messages.
"""

from __future__ import annotations

__all__ = [
    "BisectBracketEmpty",
    "FixityError",
    "GateReadFromPatrol",
    "MissingErrorBar",
    "PatrolAccountUnbalanced",
    "ProjectionSuppliedByClient",
    "StaleFollowerRead",
    "UndeterminedWouldBlock",
    "UnstartedPatrol",
]


class FixityError(Exception):
    """Base for every refusal this package makes."""


class PatrolAccountUnbalanced(FixityError):
    """``n_in_scope`` did not equal ``n_checked + n_not_checked``.

    The patrol's own conservation law, and the reason it exists: a scan that
    reports twelve findings out of an unstated denominator is an anecdote. The
    denominator is what turns "we found no drift" into a bounded claim, so a
    patrol whose arithmetic does not close does not get to write a run row.
    """

    def __init__(self, in_scope: int, checked: int, not_checked: int) -> None:
        """Name the three numbers, because their difference is the diagnosis."""
        self.in_scope = in_scope
        self.checked = checked
        self.not_checked = not_checked
        super().__init__(
            f"patrol accounting does not close: n_in_scope={in_scope} but "
            f"n_checked={checked} + n_not_checked={not_checked} = {checked + not_checked}. "
            f"A coverage claim with an unstated denominator is not a coverage claim"
        )


class GateReadFromPatrol(FixityError):
    """A patrol statement touched a table the merge gate reads.

    §9 is explicit: patrol reads use ``AS OF SYSTEM TIME follower_read_timestamp()``
    so they never contend with permit merges, and **gate reads never use follower
    or bounded-staleness reads**. A statement that is both — a stale read of a gate
    table — is the one combination that could let a patrol answer a gate question
    with data that is 4.2 seconds old. It is refused at statement-construction
    time rather than reviewed.
    """

    def __init__(self, statement: str, table: str) -> None:
        """Quote the offending table and the statement that named it."""
        self.statement = statement
        self.table = table
        super().__init__(
            f"a patrol statement names {table!r}, which the merge gate reads. Patrol "
            f"statements run at a follower-read timestamp and must never be the source "
            f"of a gate decision (ARCHITECTURE.md §9.1). Statement: {statement!r}"
        )


class StaleFollowerRead(FixityError):
    """A patrol read was built without its ``AS OF SYSTEM TIME`` preamble.

    The preamble is not an optimisation. Without it the scan takes locks on rows a
    permit merge is trying to write, and the first symptom is a `40001` on the
    *merge*, not on the patrol — a failure whose cause is in a different process.
    """

    def __init__(self, statement: str) -> None:
        """Quote the statement that would have run at the current timestamp."""
        self.statement = statement
        super().__init__(
            "a patrol read must carry the follower-read preamble; without it the scan "
            "contends with permit merges and the symptom appears in the merge, not here. "
            f"Statement: {statement!r}"
        )


class MissingErrorBar(FixityError):
    """A historian-derived observation arrived with no ExcDev/CompDev.

    PI applies exception reporting and swinging-door compression, so an archived
    value is a **vertex of a compression corridor**, not a measurement. Comparing
    one to a setpoint without its corridor produces a confident answer to a
    question the data cannot settle, which is how this product gets a customer
    sued. ``source_kind='historian'`` without ``err_bar`` therefore raises.
    """

    def __init__(self, asset_tag: str, source_ref: str) -> None:
        """Name the tag and the immutable source reference of the export."""
        self.asset_tag = asset_tag
        self.source_ref = source_ref
        super().__init__(
            f"historian observation for {asset_tag!r} (source_ref={source_ref!r}) carries no "
            f"error bar. An archived PI value is a vertex of a compression corridor, not a "
            f"measurement; comparing it to a setpoint without ExcDev/CompDev fabricates "
            f"precision the export does not have"
        )


class UndeterminedWouldBlock(FixityError):
    """A finding was built ``undetermined`` and ``blocking`` at once.

    The Python mirror of MI21 (``CHECK undetermined_never_blocks``, `23514`). The
    database would refuse it; refusing it here means the operator sees which of
    their inputs produced the contradiction instead of a constraint name.
    """

    def __init__(self, clause_uuid: str) -> None:
        """Name the clause whose finding was contradictory."""
        self.clause_uuid = clause_uuid
        super().__init__(
            f"finding for clause {clause_uuid} is undetermined and blocking at once. "
            f"MI21: an UNDETERMINED fixity result never blocks "
            f"(CHECK undetermined_never_blocks, SQLSTATE 23514)"
        )


class ProjectionSuppliedByClient(FixityError):
    """Someone tried to derive a projected column from data the inserter holds.

    ``drift_finding.severity_inherited`` is projected from ``clause_blame_current``
    and ``gate_class`` is derived from it; principle P2 says a column a gate reads
    is written by a trigger from an authoritative source and **never** from the
    inserter. This package supplies a constant placeholder that depends only on
    ``(direction, undetermined)`` — both of which are the lattice's determination,
    not a severity — and raises if a caller tries to influence it.
    """

    def __init__(self, column: str) -> None:
        """Name the projected column the caller attempted to decide."""
        self.column = column
        super().__init__(
            f"{column!r} is a projection. The fixity patrol proposes a finding; the "
            f"database decides what it is worth. Supplying this column from anything the "
            f"inserter knows would make the gate read a number the inserter chose (P2)"
        )


class BisectBracketEmpty(FixityError):
    """A bisect was asked to search an interval containing no candidate element."""

    def __init__(self, lo: str, hi: str) -> None:
        """Name the empty interval's endpoints."""
        self.lo = lo
        self.hi = hi
        super().__init__(
            f"bisect bracket ({lo}, {hi}) contains no candidate element. An empty bracket "
            f"is a caller bug: there is no culprit to find and no range to report"
        )


class UnstartedPatrol(FixityError):
    """A patrol result was assembled with ``finished_at`` before ``started_at``."""

    def __init__(self, started: str, finished: str) -> None:
        """Name both timestamps so the clock skew is visible."""
        self.started = started
        self.finished = finished
        super().__init__(
            f"patrol run finished at {finished} before it started at {started}. A run whose "
            f"own clock disagrees with itself cannot witness anything about another clock"
        )
