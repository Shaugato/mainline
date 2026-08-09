# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""``mainline-cherrypick`` — the cherry-pick worker: a lesson offered to the fleet.

Agent 7 of the fleet (ARCHITECTURE.md §8.4, §5.9). Tier **T1**. SQL role
``agent_fleet``. One model call, and it is a **T2 narration** that cannot resolve
anything.

Read these four sentences before using it.

1. *Sites are downstream distributions, not replicas.* §5.9 borrows Debian's DEP-3
   model, whose machine-readable ``Forwarded: not-needed`` declination has been in
   production since 2009: **a mandated response beats mandated conformity**, because
   a setpoint that is right at one plant can be an unrevealed hazard at another.
   A site that says no says it in a falsifiable shape, and that no is citable the
   next time the same lesson arrives.
2. *Only tightenings travel, and it is a `CHECK`.* Weakenings are site-local
   trade-offs and must be re-earned locally. MI23 enforces it in the database;
   :class:`~mainline_cherrypick.types.Lesson` refuses to construct one, so the
   refusal names the lesson rather than the constraint.
3. *A recorded resolution is proposed, never auto-applied.* Auto-applying a
   safety-text resolution is precisely the rubber-stamp accelerant this product
   exists not to build. Four independent barriers enforce it — see
   :mod:`mainline_cherrypick.narrate`.
4. *Claude explains a conflict, never resolves one.* The three-way merge in
   :mod:`mainline_cherrypick.merge3` is deterministic and model-free; the model
   writes prose for a human and its schema's ``resolution_proposed`` field accepts
   exactly one value.

And the thing that makes ``resolution_memory`` more than a cache: git's ``rerere``
remembers **how** a conflict was resolved and not **where the resolution came
from**, so when a resolution is later found wrong git cannot tell you which trees
inherited it. ``origin_conflict`` costs one column and
:data:`~mainline_cherrypick.rerere.INHERITED_SITES_SQL` is the query it buys.

**:mod:`mainline_cherrypick.narrate` is deliberately not re-exported here.** Every
name in this module's ``__all__`` is reachable without importing a model surface,
so the deterministic half of the package — the merge, the patch digest, the
envelope, the state machine, the statements — can be imported, tested and audited
with ``mainline-agentkit`` absent from the environment entirely.
``tests/unit/cherrypick/test_starvation.py`` asserts exactly that by walking the
import graph. Reaching the model means naming the module, and naming the module is
a line in a diff.

What this package does **not** claim: the applicability score does not decide
anything. It orders a superintendent's queue, it is produced by a deterministic
function with published weights, and no model reads or writes it — the DDL column
beside it is called ``model_version`` and this package fills it with
:data:`~mainline_cherrypick.travel.SCORER_VERSION`.
"""

from __future__ import annotations

from .adopt import (
    TERMINAL_STATES,
    TRANSITIONS,
    advance,
    conflicts_from_merge,
    decline,
    reopen_expired_waiver,
)
from .emit import (
    FLEET_ROLE,
    FORBIDDEN_TARGETS,
    INSERT_LESSON_SQL,
    INSERT_MERGE_CONFLICT_SQL,
    INSERT_PROPAGATION_SQL,
    INSERT_RESOLUTION_MEMORY_SQL,
    STATEMENTS,
    UPDATE_PROPAGATION_STATE_SQL,
    Statement,
    assert_fleet_safe,
    insert_lesson,
    insert_merge_conflict,
    insert_propagation,
    insert_resolution_memory,
    statements_for_offer,
    update_propagation_state,
)
from .errors import (
    AdoptionNotClean,
    AgentWouldResolve,
    CherryPickError,
    DeclinationNotFalsifiable,
    ForbiddenWriteTarget,
    IllegalPropagationTransition,
    RecalledResolutionOffered,
    WeakeningWouldTravel,
)
from .merge3 import (
    CLAUSE_DIGEST_DOMAIN,
    ConflictRegion,
    Merge3Result,
    digest_lines,
    merge3,
)
from .patchid import (
    PATCH_DIGEST_DOMAIN,
    PATCH_DIGEST_VERSION,
    normalise_delta_set,
    patch_digest,
)
from .rerere import INHERITED_SITES_SQL, RecalledResolution, recall, remember
from .travel import (
    DEFAULT_SLA_DAYS,
    SCORE_WEIGHTS,
    SCORER_VERSION,
    TravelVerdict,
    applicability_score,
    assert_may_travel,
    due_by,
    evaluate_envelope,
    may_travel,
)
from .types import (
    AGENT_SUBJECT_PREFIXES,
    DECLINATION_KINDS,
    TRAVELLING_DELTAS,
    ClauseDelta,
    Declination,
    HumanResolution,
    Lesson,
    MergeConflict,
    Propagation,
    PropState,
    ResolutionMemoryRow,
)

__version__ = "0.1.0"

#: The fleet-register entry for §8.4 row 7, in the shape ``spec/agents/fleet.yaml``
#: consumes. Exported as data so the register and this package are checked against
#: each other rather than maintained in parallel.
FLEET_ENTRY = {
    "agent": "cherry_pick",
    "tier": "T1",
    "sql_role": FLEET_ROLE,
    "iam_role": "mainline-site-adopter",
    "tools": [],
    "no_model": False,
    "may_write_gate_field": False,
    "call_profiles": ["narration"],
    "writes": [
        "mainline.lesson",
        "mainline.propagation",
        "mainline.merge_conflict",
        "mainline.resolution_memory",
        "mainline_ops.outbox",
    ],
    "decision_it_does_not_make": (
        "Applicability. Recorded resolutions are proposed, never auto-applied"
    ),
}

__all__ = [
    "AGENT_SUBJECT_PREFIXES",
    "CLAUSE_DIGEST_DOMAIN",
    "DECLINATION_KINDS",
    "DEFAULT_SLA_DAYS",
    "FLEET_ENTRY",
    "FLEET_ROLE",
    "FORBIDDEN_TARGETS",
    "INHERITED_SITES_SQL",
    "INSERT_LESSON_SQL",
    "INSERT_MERGE_CONFLICT_SQL",
    "INSERT_PROPAGATION_SQL",
    "INSERT_RESOLUTION_MEMORY_SQL",
    "PATCH_DIGEST_DOMAIN",
    "PATCH_DIGEST_VERSION",
    "SCORER_VERSION",
    "SCORE_WEIGHTS",
    "STATEMENTS",
    "TERMINAL_STATES",
    "TRANSITIONS",
    "TRAVELLING_DELTAS",
    "UPDATE_PROPAGATION_STATE_SQL",
    "AdoptionNotClean",
    "AgentWouldResolve",
    "CherryPickError",
    "ClauseDelta",
    "ConflictRegion",
    "Declination",
    "DeclinationNotFalsifiable",
    "ForbiddenWriteTarget",
    "HumanResolution",
    "IllegalPropagationTransition",
    "Lesson",
    "Merge3Result",
    "MergeConflict",
    "PropState",
    "Propagation",
    "RecalledResolution",
    "RecalledResolutionOffered",
    "ResolutionMemoryRow",
    "Statement",
    "TravelVerdict",
    "WeakeningWouldTravel",
    "__version__",
    "advance",
    "applicability_score",
    "assert_fleet_safe",
    "assert_may_travel",
    "conflicts_from_merge",
    "decline",
    "digest_lines",
    "due_by",
    "evaluate_envelope",
    "insert_lesson",
    "insert_merge_conflict",
    "insert_propagation",
    "insert_resolution_memory",
    "may_travel",
    "merge3",
    "normalise_delta_set",
    "patch_digest",
    "recall",
    "remember",
    "reopen_expired_waiver",
    "statements_for_offer",
    "update_propagation_state",
]
