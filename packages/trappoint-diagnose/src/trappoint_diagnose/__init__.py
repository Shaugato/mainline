# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""QUICKREFUSE — the minimal unsatisfiable subset and nearest admissible alternative.

Invariant `I14`: *every refusal emits an irreducible reason set and, where computable, the
nearest admissible alternative.* A gate that only says "no" gets routed around, and an
invariant that is routed around is not an invariant.

Two algorithms, in this order:

1. **Declarative decomposition** (``decompose``, and ``trappoint.explain_refusal()`` in
   SQL). The refused constraint maps to the projected counter behind it, and that
   counter's witness rows ARE the minimal unsatisfiable subset. Deterministic, no probe.
2. **QuickXplain over savepoint probes** (``quickxplain`` + ``SavepointOracle``). The
   general algorithm, with the DATABASE as the oracle — so the explanation is produced by
   the same constraint engine that produced the refusal and cannot disagree with it.

Where neither answers, the payload says so: ``diagnosis="none"``, ``naa=null``, and a
reason from a closed set. That is a first-class outcome. A superset labelled as a minimal
unsatisfiable subset is the one failure mode this invariant exists to prevent.

Typical use::

    from trappoint_diagnose import Diagnoser, UdfSource, context_from_exception
    from trappoint_diagnose import load_gate_binding

    binding = load_gate_binding("verticals/mainline/vertical.toml")
    diagnoser = Diagnoser(binding)
    context = context_from_exception(
        refused, subject_kind="permit", subject_id=str(permit_id), gate_epoch=epoch
    )
    payload = diagnoser.explain(context, source=UdfSource(connect))
"""

from __future__ import annotations

from .binding import CounterBinding, GateBinding, SubjectBinding, load_gate_binding
from .decompose import Decomposition, OpenObligation, Witnesses, decompose
from .diagnose import Diagnoser, ProbeRequest, context_from_exception
from .errors import (
    DiagnoseRefused,
    NotDiagnosable,
    OracleUnavailable,
    PayloadInvalid,
    ProbeBudgetExhausted,
    ProbeUnsafe,
)
from .ledger import ledger_row, record_refusal
from .model import (
    AuthorityGap,
    CapabilityGap,
    ClauseAtom,
    DisposeObligations,
    EventAtom,
    EvidenceItem,
    ForkSubject,
    MaterialiseAuthority,
    MusAtom,
    Naa,
    Obligation,
    RefusalContext,
    RefusalPayload,
    SubstituteKind,
    SupplyEvidence,
)
from .oracle import ProbePlan, SavepointOracle, probe_transaction
from .quickxplain import BudgetedOracle, Oracle, is_minimal_conflict, quickxplain
from .udf import UdfSource, atoms_from_wire, naa_from_wire
from .wire import build_payload, load_refusal_schema, now_rfc3339, validate_payload

__version__ = "0.1.0"

__all__ = [
    "AuthorityGap",
    "BudgetedOracle",
    "CapabilityGap",
    "ClauseAtom",
    "CounterBinding",
    "Decomposition",
    "DiagnoseRefused",
    "Diagnoser",
    "DisposeObligations",
    "EventAtom",
    "EvidenceItem",
    "ForkSubject",
    "GateBinding",
    "MaterialiseAuthority",
    "MusAtom",
    "Naa",
    "NotDiagnosable",
    "Obligation",
    "OpenObligation",
    "Oracle",
    "OracleUnavailable",
    "PayloadInvalid",
    "ProbeBudgetExhausted",
    "ProbePlan",
    "ProbeRequest",
    "ProbeUnsafe",
    "RefusalContext",
    "RefusalPayload",
    "SavepointOracle",
    "SubjectBinding",
    "SubstituteKind",
    "SupplyEvidence",
    "UdfSource",
    "Witnesses",
    "__version__",
    "atoms_from_wire",
    "build_payload",
    "context_from_exception",
    "decompose",
    "is_minimal_conflict",
    "ledger_row",
    "load_gate_binding",
    "load_refusal_schema",
    "naa_from_wire",
    "now_rfc3339",
    "probe_transaction",
    "quickxplain",
    "record_refusal",
    "validate_payload",
]
