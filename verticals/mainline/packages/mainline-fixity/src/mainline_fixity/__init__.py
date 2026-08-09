# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""``mainline-fixity`` — the fixity patrol: as-documented against as-operated.

Agent 6 of the fleet (ARCHITECTURE.md §8.4). Tier T1: it writes proposal rows —
``patrol_run``, ``drift_finding``, ``discordance_warrant``, ``observed_assertion``,
``time_witness`` — and it writes nothing the merge gate reads.

**This agent holds no model, and that is the design, not an omission.** §8.4 row 6
says the decision it does not make is ``weaken``: *the lattice compare decides, and
abstain ⇒ weaken.* Since the comparison is
:func:`mainline_domain.lattice.explain` over two CATs, there is no call to make.
The package's fleet-register entry is therefore ``no_model: true``, its dependency
list contains no ``mainline-agentkit`` and no ``boto3``, and
``tests/unit/fixity/test_starvation.py`` walks the AST of every module here to keep
it that way. A component with no model surface cannot be prompted into anything.

Read these four sentences before using it.

1. *A drift finding is a ``control_delta`` whose author is the plant.* The
   comparison is the same nine-rule lattice the clause pipeline uses, so a
   reality-authored weakening fires the existing merge gate with no new gate logic,
   and the blocking decision reads ``clause_blame_current.max_severity`` rather
   than the clause's current text — diachronic gating, for free.
2. *"No excursion found" is never "no excursion occurred".* A PI archive value is a
   vertex of a compression corridor. A difference smaller than ``ExcDev + CompDev``
   is recorded as a **bounded negative with its arithmetic** and marked
   ``undetermined``.
3. *UNKNOWN is first class.* A bisect that terminates against a skipped region
   returns a **range**, never a culprit. Fabricating a named culprit from an
   unobservable interval is how this product gets a customer sued.
4. *Nothing here holds a driver, a credential or an ``UPDATE``.*
   :mod:`mainline_fixity.emit` returns statements and parameters; the caller holds
   ``agent_patroller``, whose grant is ``INSERT`` on five tables and nothing else.

And one thing this package does **not** claim. An ``undetermined`` finding does not
block, because MI21 forbids it — so an adversary who can make a comparison
undetermined has, by that route alone, avoided the drift gate. That is why an
absence opens an **A6 discordance warrant** instead: a separate obligation, blocking
under MI05, with a different constraint name, closed by a person. The residual is
stated in the README rather than argued away.
"""

from __future__ import annotations

from .bisect import (
    DEFAULT_PENALTY,
    Bracket,
    ProbeResult,
    bisect_culprit,
    bracket_last_regression,
    pelt,
)
from .compare import SETPOINT_ONLY, FixityComparison, Reason, compare_fixity
from .emit import (
    FINDING_NAMESPACE,
    RUN_NAMESPACE,
    STATEMENTS,
    bindings_in_scope,
    finding_uuid,
    insert_drift_finding,
    insert_observed_assertion,
    insert_patrol_run,
    insert_time_witness,
    insert_warrant,
    observations_for,
    projection_placeholder,
    run_uuid,
)
from .errorbar import BoundedNegative, CorridorVerdict, Reading, read_against_corridor
from .errors import (
    BisectBracketEmpty,
    FixityError,
    GateReadFromPatrol,
    MissingErrorBar,
    PatrolAccountUnbalanced,
    ProjectionSuppliedByClient,
    StaleFollowerRead,
    UndeterminedWouldBlock,
    UnstartedPatrol,
)
from .follower import (
    AS_OF_HLC_SQL,
    GATE_TABLES,
    PATROL_READ_PREAMBLE,
    PATROL_ROLE,
    Statement,
    assert_patrol_safe,
    patrol_read,
)
from .patrol import PatrolResult, Subject, run_patrol
from .types import (
    BLOCKING_SEVERITY_FLOOR,
    FIXITY_CLASSES,
    SOURCE_KINDS,
    WARRANT_CLASSES,
    BisectOutcome,
    ClauseBinding,
    DriftFinding,
    ErrorBar,
    ObservedAssertion,
    PatrolAccount,
    PatrolRun,
    PatrolScope,
    TimeWitness,
    cat_json,
)
from .warrant import PATROL_WARRANT_CLASSES, DiscordanceWarrant, propose_warrant

__version__ = "0.1.0"

#: The fleet-register entry for §8.4 row 6, in the shape ``spec/agents/fleet.yaml``
#: consumes. Exported as data so the register and this package are checked against
#: each other rather than maintained in parallel — the same reason
#: ``mainline_agentkit.profiles.describe_fleet`` exists.
FLEET_ENTRY = {
    "agent": "fixity_patrol",
    "tier": "T1",
    "sql_role": PATROL_ROLE,
    "iam_role": "mainline-fixity-patrol",
    "tools": [],
    "no_model": True,
    "may_write_gate_field": False,
    "call_profiles": [],
    "writes": [
        "mainline.observed_assertion",
        "mainline.patrol_run",
        "mainline.drift_finding",
        "mainline.time_witness",
        "mainline.discordance_warrant",
    ],
    "decision_it_does_not_make": ("`weaken` — the lattice compare decides, and abstain ⇒ weaken"),
}

__all__ = [
    "AS_OF_HLC_SQL",
    "BLOCKING_SEVERITY_FLOOR",
    "DEFAULT_PENALTY",
    "FINDING_NAMESPACE",
    "FIXITY_CLASSES",
    "FLEET_ENTRY",
    "GATE_TABLES",
    "PATROL_READ_PREAMBLE",
    "PATROL_ROLE",
    "PATROL_WARRANT_CLASSES",
    "RUN_NAMESPACE",
    "SETPOINT_ONLY",
    "SOURCE_KINDS",
    "STATEMENTS",
    "WARRANT_CLASSES",
    "BisectBracketEmpty",
    "BisectOutcome",
    "BoundedNegative",
    "Bracket",
    "ClauseBinding",
    "CorridorVerdict",
    "DiscordanceWarrant",
    "DriftFinding",
    "ErrorBar",
    "FixityComparison",
    "FixityError",
    "GateReadFromPatrol",
    "MissingErrorBar",
    "ObservedAssertion",
    "PatrolAccount",
    "PatrolAccountUnbalanced",
    "PatrolResult",
    "PatrolRun",
    "PatrolScope",
    "ProbeResult",
    "ProjectionSuppliedByClient",
    "Reading",
    "Reason",
    "StaleFollowerRead",
    "Statement",
    "Subject",
    "TimeWitness",
    "UndeterminedWouldBlock",
    "UnstartedPatrol",
    "__version__",
    "assert_patrol_safe",
    "bindings_in_scope",
    "bisect_culprit",
    "bracket_last_regression",
    "cat_json",
    "compare_fixity",
    "finding_uuid",
    "insert_drift_finding",
    "insert_observed_assertion",
    "insert_patrol_run",
    "insert_time_witness",
    "insert_warrant",
    "observations_for",
    "patrol_read",
    "pelt",
    "projection_placeholder",
    "propose_warrant",
    "read_against_corridor",
    "run_patrol",
    "run_uuid",
]
