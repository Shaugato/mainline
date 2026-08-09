# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""``trappoint-core`` — the client that must never blanket-retry the merge gate.

Four modules and one property between them:

* :mod:`trappoint_core.errors` — the SQLSTATE taxonomy as types, and how the exhibit is
  recovered from a driver that cannot supply it.
* :mod:`trappoint_core.retry` — a hand-written loop that retries ``40001`` and nothing
  else, with a spy so the once-only property is asserted rather than assumed.
* :mod:`trappoint_core.gate` — one explicit SERIALIZABLE transaction and one ``CALL``.
* :mod:`trappoint_core.cas` — the gap-free ledger append, so a gap MEANS tampering.

The property: **a refusal is attempted exactly once, ever** (``spec/errors.md`` §4).
"""

from .cas import GENESIS_LINK, LedgerPosition, append_leaf, leaf_hash, link_hash, next_seq
from .errors import (
    DENIED_SQLSTATE,
    MODELLED_SQLSTATES,
    REFUSAL_SQLSTATES,
    RETRYABLE_SQLSTATE,
    AuthorisationDenied,
    Diagnosis,
    GateRefused,
    RetryBudgetExhausted,
    TrappointError,
    UnmodelledRefusal,
    diagnose,
    gate_refused,
    sqlstate_of,
)
from .gate import ISOLATION_STATEMENT, SUBJECT_KINDS, MergeRequest, execute_gate, procedure_name
from .retry import DEFAULT_POLICY, GateObserver, RecordingObserver, RetryPolicy, run_gate

__all__ = [
    "DEFAULT_POLICY",
    "DENIED_SQLSTATE",
    "GENESIS_LINK",
    "ISOLATION_STATEMENT",
    "MODELLED_SQLSTATES",
    "REFUSAL_SQLSTATES",
    "RETRYABLE_SQLSTATE",
    "SUBJECT_KINDS",
    "AuthorisationDenied",
    "Diagnosis",
    "GateObserver",
    "GateRefused",
    "LedgerPosition",
    "MergeRequest",
    "RecordingObserver",
    "RetryBudgetExhausted",
    "RetryPolicy",
    "TrappointError",
    "UnmodelledRefusal",
    "append_leaf",
    "diagnose",
    "execute_gate",
    "gate_refused",
    "leaf_hash",
    "link_hash",
    "next_seq",
    "procedure_name",
    "run_gate",
    "sqlstate_of",
]
