# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""Path B — the independent semantic opinion, in its own distribution.

This package exists because of a line in ``mainline-domain``'s ``pyproject.toml``
listing what must never appear there: ``boto3``, ``botocore``, ``anthropic``,
``strands``.  The delta lattice decides a state transition, principle P7 forbids
any component that decides a state transition from reaching a model, and the
cheapest way to make that structural rather than aspirational is for the model
path to be a **different distribution** that the deciding one does not depend on.

So the dependency arrow points one way only:

    mainline-delta-oracle  ──imports──▶  mainline-domain
    mainline-delta-oracle  ──imports──▶  mainline-agentkit  ──▶  bedrock (opt-in)
    mainline-domain        ──imports──▶  (nothing that can reach a model, ever)

asserted by an AST walk over every module in ``mainline_domain``
(``tests/unit/domain/boundaries/test_no_model_in_domain.py``) and by
``.importlinter``'s licence-boundary contract.

What this package returns is a ``mainline_domain.contracts.OracleVerdict`` and
nothing else: a label, a confidence, a rationale, evidence spans, and an
abstention flag.  It cannot return a ``rule_id``, it never sees the
``safe_direction`` registry, and every one of its failure modes — refusal,
Guardrail block, truncation, schema violation, throttle, timeout, fabricated
evidence — comes back as ``abstained=True``.  The abstention ratchet in
``mainline_domain.resolution`` then resolves that to ``weaken``.

**The model can make a merge refuse.  It cannot make one pass.**
"""

from __future__ import annotations

from .cassettes import SCENARIOS, Scenario, ScriptedTransport, record_scenarios, scenario
from .catdiff import CAT_FIELD_ORDER, render_cat_diff, render_quantity
from .errors import (
    CassetteModelDrift,
    CassetteRootUnknown,
    DeltaOracleError,
    OracleConfigurationRefused,
    PromptVersionMismatch,
    abstention_code_for,
)
from .mapping import BAND_CONFIDENCE, BAND_MAP_VERSION, RELATION_TO_DELTA, locate_quote, to_verdict
from .oracle import PROFILE_ID, PROMPT_VERSION, AdjudicationOracle, OracleOutcome
from .prompt import FORBIDDEN_TOKENS, TRUSTED_CONTEXT, PathALeakage, assert_no_path_a_leakage
from .request import DeltaOracleRequest, OriginContext, text_pair_digest
from .transport import build_transport, default_cassette_root, verify_cassette_store

__version__ = "0.1.0"

__all__ = [
    "BAND_CONFIDENCE",
    "BAND_MAP_VERSION",
    "CAT_FIELD_ORDER",
    "FORBIDDEN_TOKENS",
    "PROFILE_ID",
    "PROMPT_VERSION",
    "RELATION_TO_DELTA",
    "SCENARIOS",
    "TRUSTED_CONTEXT",
    "AdjudicationOracle",
    "CassetteModelDrift",
    "CassetteRootUnknown",
    "DeltaOracleError",
    "DeltaOracleRequest",
    "OracleConfigurationRefused",
    "OracleOutcome",
    "OriginContext",
    "PathALeakage",
    "PromptVersionMismatch",
    "Scenario",
    "ScriptedTransport",
    "__version__",
    "abstention_code_for",
    "assert_no_path_a_leakage",
    "build_transport",
    "default_cassette_root",
    "locate_quote",
    "record_scenarios",
    "render_cat_diff",
    "render_quantity",
    "scenario",
    "text_pair_digest",
    "to_verdict",
    "verify_cassette_store",
]
