# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The refusal taxonomy, made total.

``spec/errors.md`` §1.1 states the property this module enforces:

    Over the gate path, the refusal taxonomy is **total** over
    ``{40001, 23514, 23503, 23505, P0001}``. Any other SQLSTATE fails the
    conformance suite.

"Fails the suite" is the whole point, and it is why :func:`classify` raises rather than
returning an ``UNKNOWN`` member. An enum with a catch-all is a taxonomy that can absorb
anything, and absorbing anything is how a suite comes to pass against a database that
refused for a reason nobody modelled.

``42501`` is excluded by *definition*, not by exception: the writer was refused before
the gate, by the grant graph or by a row-level-security policy, and no gate condition
was ever evaluated. It has its own class.
"""

from __future__ import annotations

from enum import Enum

__all__ = [
    "ADMIT_CODES",
    "DENY_CODES",
    "REFUSE_CODES",
    "RETRY_CODES",
    "SCHEMA_ABSENT_CODES",
    "Outcome",
    "UnmodelledRefusal",
    "classify",
    "describe",
    "is_schema_absent",
]

RETRY_CODES: frozenset[str] = frozenset({"40001"})
REFUSE_CODES: frozenset[str] = frozenset({"23514", "23503", "23505", "P0001"})
DENY_CODES: frozenset[str] = frozenset({"42501"})
ADMIT_CODES: frozenset[str] = frozenset({"00000"})

# Not part of the taxonomy, and deliberately named anyway. These are the codes that mean
# "the schema is not migrated to the version the client expects" (spec/errors.md §1.1),
# and a runner that reports them as an anonymous unmodelled refusal is a runner that
# makes the ordinary red-before-green state look like a mystery. They are still
# failures — they are just failures that get a sentence naming the missing object.
SCHEMA_ABSENT_CODES: frozenset[str] = frozenset(
    {
        "42P01",  # undefined_table
        "42883",  # undefined_function
        "42704",  # undefined_object (a type, a constraint)
        "3F000",  # invalid_schema_name
        "42P02",  # undefined_parameter
        "42703",  # undefined_column
    }
)

_DEFECT_NOTES: dict[str, str] = {
    "23502": (
        "a NOT NULL projected column was left unset by a trigger; project the strictest "
        "legal value instead (spec/errors.md §1.1, spec rule P-4)"
    ),
    "22P02": "a client sent a value the column type cannot hold; the gate never ran",
    "22003": "a client sent a value the column type cannot hold; the gate never ran",
    "42P01": "the schema is not migrated to the version this case expects",
    "42883": "the schema is not migrated: a function or procedure is missing",
    "3F000": "the schema is not migrated: the schema itself does not exist",
    "40003": "statement completion unknown — a client bug in transaction handling",
    "25P02": "a statement was issued after an aborted one — a client bug",
    "53200": "resource exhaustion; the transition is undecided but is NOT a serialization failure",
    "57014": "cancellation; the transition is undecided but is NOT a serialization failure",
    "XXUUU": "an internal error; report it upstream and do not model it",
}


class Outcome(Enum):
    """The four expectation classes of ``spec/errors.md`` §1.

    There is no fifth member and no catch-all. That is a design decision with teeth:
    every place that switches on an ``Outcome`` is exhaustive, and a new code cannot be
    quietly absorbed by an ``UNKNOWN`` branch nobody reads.
    """

    RETRY = "retry"
    REFUSE = "gate"
    DENY = "deny"
    ADMIT = "admit"


class UnmodelledRefusal(Exception):
    """The database refused for a reason nobody modelled.

    Carries the code and, where one exists, the specific note from ``spec/errors.md``
    saying what that code means when it appears here. This is a conformance **failure**,
    not a harness error: the history ran, the database answered, and the answer was
    outside the closed set the specification allows.
    """

    def __init__(self, sqlstate: str, message: str = "") -> None:
        """Record the offending code and attach the specification's note about it."""
        self.sqlstate = sqlstate
        self.message = message
        note = _DEFECT_NOTES.get(sqlstate)
        detail = f"{sqlstate} is outside the modelled taxonomy"
        if note:
            detail += f" — {note}"
        if message:
            detail += f": {message}"
        super().__init__(detail)


def classify(sqlstate: str) -> Outcome:
    """Map a SQLSTATE onto its expectation class.

    Raises:
        UnmodelledRefusal: for every code outside the four classes.
    """
    if sqlstate in RETRY_CODES:
        return Outcome.RETRY
    if sqlstate in REFUSE_CODES:
        return Outcome.REFUSE
    if sqlstate in DENY_CODES:
        return Outcome.DENY
    if sqlstate in ADMIT_CODES:
        return Outcome.ADMIT
    raise UnmodelledRefusal(sqlstate)


def is_schema_absent(sqlstate: str) -> bool:
    """Whether *sqlstate* means the object the case needs has not been created yet."""
    return sqlstate in SCHEMA_ABSENT_CODES


def describe(sqlstate: str) -> str:
    """Return a one-line human reading of *sqlstate*, for a failure report."""
    note = _DEFECT_NOTES.get(sqlstate)
    if note:
        return f"{sqlstate}: {note}"
    try:
        return f"{sqlstate}: {classify(sqlstate).value}-class"
    except UnmodelledRefusal:
        return f"{sqlstate}: outside the modelled taxonomy"
