# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""DELTALATTICE — nine deterministic rules over two CATs, with a minimal witness.

Public surface::

    from mainline_domain.lattice import decide, explain

    verdict = decide(reference_cat, descendant_cat, registry, as_of=commit_id)
    verdict.delta        # ControlDelta.WEAKEN
    verdict.basis        # 'lattice'
    verdict.witnesses    # the irreducible reason set — I14
    verdict.minimal      # always True for a lattice verdict

    decision = explain(reference_cat, descendant_cat, registry, as_of=commit_id)
    decision.findings    # every rule finding, R1 → R9
    decision.minimal     # why the answer is no
    decision.repair      # what would have to change for it to be yes

WHAT IS UNCLAIMED HERE, AND WHAT IS NOT
---------------------------------------
Deontic downgrade detection is published work in legal NLP; a per-parameter
direction registry is ordinary safety engineering; minimal unsatisfiable subsets
are decades old in SAT and constraint solving.  None of those is the claim.

The claim is the composition: **a lattice whose verdict carries a minimal
unsatisfiable witness set, and whose absence is a write refusal.**  Decision D8
makes ``mainline.fn_delta_witness_guard`` raise ``P0001`` on any
``clause_version`` insert that declares ``control_delta IN ('weaken','remove')``
with ``delta_basis='lattice'`` and no witness rows written earlier in the same
transaction.  An unexplainable weakening verdict does not get to exist in the
database — not "is flagged", not "is logged": cannot be stored.

``novelty/deltalattice.yaml`` states that position, its prior art and everything
this worker has **not** proven.

PATH A ONLY
-----------
Nothing in this package imports a model SDK, opens a socket, reads an environment
variable or looks at a clock.  ``tests/unit/domain/lattice/test_path_a_is_alone.py``
walks the AST of every module here to keep it that way.  Principle P7: no
component that can decide a state transition may reach a model, and this one
decides a state transition.

Six modules, in the order data flows through them:

===============  ======================================================
``rules``        the nine predicates and what they are allowed to see
``order``        the join W6 composes with, and the duality involution
``witness``      minimality (I14) and the sanctioned verdict constructor
``decide``       the pure entry point
``version``      ``LATTICE_VERSION`` and the decision-table fingerprint
``errors``       the two things this package refuses to paper over
===============  ======================================================
"""

from __future__ import annotations

from .decide import LatticeDecision, decide, explain
from .errors import LatticeError, WitnesslessWeakenError
from .order import CHAIN, NEUTRAL, dual, is_weakening, join, rank
from .rules import (
    BOUND_POLARITY_INVERSIONS,
    COMPARATOR_FAMILY,
    COVERAGE_RANK,
    DEONTIC_POLARITY,
    DEONTIC_RUNG,
    RULES,
    WEAKENING_COMPARATOR_MOVES,
    Rule,
    RuleFinding,
    RuleInput,
    r1_deontic,
    r2_setpoint,
    r3_comparator,
    r4_exception,
    r5_quantifier,
    r6_verification,
    r7_frequency,
    r8_anchor,
    r9_coverage,
)
from .version import LATTICE_VERSION, rule_catalogue_fingerprint
from .witness import (
    WITNESSLESS_WEAKEN_MESSAGE,
    is_irredundant,
    minimal_correction_set,
    minimal_unsatisfiable_subset,
    verdict,
    verdict_of,
    witnesses_of,
)

__all__ = [
    "BOUND_POLARITY_INVERSIONS",
    "CHAIN",
    "COMPARATOR_FAMILY",
    "COVERAGE_RANK",
    "DEONTIC_POLARITY",
    "DEONTIC_RUNG",
    "LATTICE_VERSION",
    "NEUTRAL",
    "RULES",
    "WEAKENING_COMPARATOR_MOVES",
    "WITNESSLESS_WEAKEN_MESSAGE",
    "LatticeDecision",
    "LatticeError",
    "Rule",
    "RuleFinding",
    "RuleInput",
    "WitnesslessWeakenError",
    "decide",
    "dual",
    "explain",
    "is_irredundant",
    "is_weakening",
    "join",
    "minimal_correction_set",
    "minimal_unsatisfiable_subset",
    "r1_deontic",
    "r2_setpoint",
    "r3_comparator",
    "r4_exception",
    "r5_quantifier",
    "r6_verification",
    "r7_frequency",
    "r8_anchor",
    "r9_coverage",
    "rank",
    "rule_catalogue_fingerprint",
    "verdict",
    "verdict_of",
    "witnesses_of",
]
