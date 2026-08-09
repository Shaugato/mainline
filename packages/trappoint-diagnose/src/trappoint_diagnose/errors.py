# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The refusal vocabulary of the diagnoser.

Every exception here is a REFUSAL of this package to produce something, and each one
exists because the alternative — producing it anyway — would be worse than failing.
There is deliberately no generic ``DiagnoseError``: a caller that cannot tell "the probe
budget ran out" from "the payload does not validate" will handle both the same way, and
one of those is honest incompleteness while the other is a defect.
"""

from __future__ import annotations

__all__ = [
    "DiagnoseRefused",
    "NotDiagnosable",
    "OracleUnavailable",
    "PayloadInvalid",
    "ProbeBudgetExhausted",
    "ProbeUnsafe",
]


class DiagnoseRefused(Exception):
    """Base of the refusal vocabulary. Never raised directly."""


class PayloadInvalid(DiagnoseRefused):
    """The assembled payload does not validate against the shipped wire schema.

    Raised rather than returned, and never suppressed. A payload that does not validate
    is a payload no consumer contracted to parse, and emitting one would make the wire
    contract advisory — which is the same as not having one.
    """


class ProbeBudgetExhausted(DiagnoseRefused):
    """The oracle budget ran out before minimality was established.

    This is not an error condition in the product sense: the emitter catches it and
    degrades to ``diagnosis="none"`` with ``naa_reason="probe_budget_exhausted"``, which
    is the honest answer. It is an exception rather than a sentinel because the
    recursion has to unwind from wherever it happened to be.
    """


class ProbeUnsafe(DiagnoseRefused):
    """The probe was asked to run somewhere it must never run.

    The savepoint oracle refuses a connection that is already inside a transaction. A
    diagnosis that shared the gate's transaction could mutate the gate — and row locks
    survive ``ROLLBACK TO SAVEPOINT`` in CockroachDB, so even a rolled-back probe on the
    gate's connection would hold locks the gate then waits on. Both are I14 violations
    and both are silent, so the refusal happens at construction time.
    """


class OracleUnavailable(DiagnoseRefused):
    """No oracle was supplied for a refusal the declarative decomposition cannot cover.

    Distinguished from ``ProbeBudgetExhausted`` because the resulting payload differs:
    an unavailable oracle is ``not_computable``, an exhausted budget is
    ``probe_budget_exhausted``, and conflating them would let a deployment that never
    configured probing look like one whose refusal was genuinely hard.
    """


class NotDiagnosable(DiagnoseRefused):
    """The database refused to diagnose the refusal, and said why.

    The UDF raises ``P0001`` when the projected counter disagrees with its re-derived
    witness set, or when the refusal is no longer reproducible against the current row.
    Both are facts about the world and neither licences a fabricated reason set.
    """
