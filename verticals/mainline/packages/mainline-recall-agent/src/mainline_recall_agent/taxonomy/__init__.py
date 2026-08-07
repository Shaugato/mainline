# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The archival spine that *is* the vector-index prefix.

Four things live here, and they are one thing seen from four sides.

**A frozen level 1** (:mod:`.register`).  The fonds are the buyer's own ICMM Material
Unwanted Event register.  ``activity_node.activity_root`` is denormalised onto every
descendant and reaches the physical index through ``event_cue.scope_id``; C-SPANN keeps one
K-means tree per distinct prefix value, so a level-1 code is a partition and re-inducting
level 1 is a **re-partition, not an update**.  The loader says so, in those words, when
asked.

**Induced levels 2 and 3** (:mod:`.induction`, :mod:`.merge`, :mod:`.classifier`).  TnT-LLM's
two phases through the ``JudgeProvider`` — propose per document, then merge and refine —
under a naming rule that a label must name a **function performed**, never a thing or a
place (:mod:`.labels`).  Then bulk assignment by a cheap deterministic classifier committed
as JSON coefficients rather than a pickle, and confirmation on a held-out sample reported
with Wilson bounds through the eval package (:mod:`.holdout`).

**A version that is a commit** (:mod:`.versioning`).  Every run emits a
:class:`~.versioning.TaxonomyVersion` — parent version, label diff, model, prompt version,
holdout scores, digest — because a re-induction silently changes what the gate would have
recalled and that must be attributable.

**Level-Materialised Bonds** (:mod:`.lmb`, :mod:`.bonds`).  One ``event_cue`` row per
archival level per populated facet, which grades the K-means trees and turns the matching
level into a retrieval feature; and one ``event_bond`` row for the event's node **and every
ancestor**, which is what makes *"a fatality never decays"* a set-membership question rather
than a decay constant somebody can tune.

Consumed and not owned: ``mainline.activity_node`` and ``mainline.event``.  Where those
migrations are absent, the fixture DDL under ``tests/fixtures/recall_taxonomy/`` stands in
and the integration lane is skipped with a reason — never faked.
"""

from __future__ import annotations

from .bonds import BondEmission, BondWriter, assert_ancestor_closure, build_bond_rows
from .classifier import ARTEFACT_KIND, Prediction, TaxonomyClassifier, tokenise
from .errors import (
    ArchivalPathError,
    BondClosureError,
    ClassifierArtefactInvalid,
    ClassifierNotFitted,
    CueEmissionError,
    EvalPackageUnavailable,
    HoldoutTooSmall,
    InductionQualityError,
    LabelRejected,
    Level1OffRegister,
    Level1Repartition,
    Level1Unfrozen,
    RegisterMalformed,
    TaxonomyError,
    TaxonomyVersionError,
)
from .holdout import (
    DEFAULT_HOLDOUT_SIZE,
    FILE_LEVEL_FLOOR,
    FONDS_LEVEL_FLOOR,
    HoldoutReport,
    holdout_split,
    score_holdout,
)
from .induction import (
    InductionConfig,
    InductionDocument,
    MergeOutcome,
    Proposal,
    ProposalPool,
    Rejection,
    SnapshotBuild,
    assign_leaves,
    build_snapshot,
    merge_and_refine,
    propose_labels,
)
from .labels import (
    EQUIPMENT_AND_PLACE_BIGRAMS,
    EQUIPMENT_AND_PLACE_UNIGRAMS,
    FUNCTION_GERUNDS,
    REJECTION_REASONS,
    LabelVerdict,
    check_label,
    normalise_label,
    validate_label,
)
from .lmb import LevelMaterialisedBondWriter, LmbEmission, build_cue_rows
from .merge import LabelCandidate, cluster_labels, similarity
from .models import (
    BOND_BASES,
    INDUCED_BY,
    LEVEL_FILE,
    LEVEL_FONDS,
    LEVEL_NAMES,
    LEVEL_SERIES,
    ActivityNode,
    ArchivalPath,
    BondRow,
    CueRow,
    EventRef,
    FacetValue,
    TaxonomySnapshot,
    derive_scope_id,
)
from .offline_judge import OFFLINE_JUDGE_MODEL_ID, InductionRule, RuleBasedInductionJudge
from .pipeline import InductionRun, run_induction
from .prompts import INDUCTION_PROMPT_VERSION, build_induction_prefix
from .register import (
    MAX_LEVEL1_CODES,
    MIN_LEVEL1_CODES,
    REPARTITION_MESSAGE,
    Level1Code,
    Level1Register,
    assert_level1_node,
    load_level1_register,
    refuse_level1_reinduction,
)
from .schemas import DocumentLabel, LabelProposalBatch, MergeDecision, MergeGroup
from .sources import ActivityNodeSource, InMemoryNodeSource, SqlNodeSource, resolve_path
from .sql import (
    INSERT_ACTIVITY_NODE,
    INSERT_EVENT_BOND,
    INSERT_EVENT_CUE,
    activity_node_params,
    bond_batch,
    bond_params,
    cue_batch,
    cue_params,
)
from .versioning import LabelDiff, TaxonomyVersion, diff_snapshots, emit_version

__all__ = [
    "ARTEFACT_KIND",
    "BOND_BASES",
    "DEFAULT_HOLDOUT_SIZE",
    "EQUIPMENT_AND_PLACE_BIGRAMS",
    "EQUIPMENT_AND_PLACE_UNIGRAMS",
    "FILE_LEVEL_FLOOR",
    "FONDS_LEVEL_FLOOR",
    "FUNCTION_GERUNDS",
    "INDUCED_BY",
    "INDUCTION_PROMPT_VERSION",
    "INSERT_ACTIVITY_NODE",
    "INSERT_EVENT_BOND",
    "INSERT_EVENT_CUE",
    "LEVEL_FILE",
    "LEVEL_FONDS",
    "LEVEL_NAMES",
    "LEVEL_SERIES",
    "MAX_LEVEL1_CODES",
    "MIN_LEVEL1_CODES",
    "OFFLINE_JUDGE_MODEL_ID",
    "REJECTION_REASONS",
    "REPARTITION_MESSAGE",
    "ActivityNode",
    "ActivityNodeSource",
    "ArchivalPath",
    "ArchivalPathError",
    "BondClosureError",
    "BondEmission",
    "BondRow",
    "BondWriter",
    "ClassifierArtefactInvalid",
    "ClassifierNotFitted",
    "CueEmissionError",
    "CueRow",
    "DocumentLabel",
    "EvalPackageUnavailable",
    "EventRef",
    "FacetValue",
    "HoldoutReport",
    "HoldoutTooSmall",
    "InMemoryNodeSource",
    "InductionConfig",
    "InductionDocument",
    "InductionQualityError",
    "InductionRule",
    "InductionRun",
    "LabelCandidate",
    "LabelDiff",
    "LabelProposalBatch",
    "LabelRejected",
    "LabelVerdict",
    "Level1Code",
    "Level1OffRegister",
    "Level1Register",
    "Level1Repartition",
    "Level1Unfrozen",
    "LevelMaterialisedBondWriter",
    "LmbEmission",
    "MergeDecision",
    "MergeGroup",
    "MergeOutcome",
    "Prediction",
    "Proposal",
    "ProposalPool",
    "RegisterMalformed",
    "Rejection",
    "RuleBasedInductionJudge",
    "SnapshotBuild",
    "SqlNodeSource",
    "TaxonomyClassifier",
    "TaxonomyError",
    "TaxonomySnapshot",
    "TaxonomyVersion",
    "TaxonomyVersionError",
    "activity_node_params",
    "assert_ancestor_closure",
    "assert_level1_node",
    "assign_leaves",
    "bond_batch",
    "bond_params",
    "build_bond_rows",
    "build_cue_rows",
    "build_induction_prefix",
    "build_snapshot",
    "check_label",
    "cluster_labels",
    "cue_batch",
    "cue_params",
    "derive_scope_id",
    "diff_snapshots",
    "emit_version",
    "holdout_split",
    "load_level1_register",
    "merge_and_refine",
    "normalise_label",
    "propose_labels",
    "refuse_level1_reinduction",
    "resolve_path",
    "run_induction",
    "score_holdout",
    "similarity",
    "tokenise",
    "validate_label",
]
