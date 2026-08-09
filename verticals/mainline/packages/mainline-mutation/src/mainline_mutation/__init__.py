# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""MUTATION RATCHET — the residual risk this domain declines to argue away, measured.

    from mainline_mutation import run, build_report

    intact = run(seed=0)
    crippled = run(seed=0, disabled_rules=frozenset({"R1_DEONTIC"}))
    build_report(intact)["headline"]["kill"]["wilson_lower"]

WHAT IT IS
----------
Two catalogues and one harness (decision D13).  **KILL** mutations are control
weakenings the pipeline must react to; **SURVIVE** mutations are
identity-preserving reformats it must ignore.  They are reported separately and
there is no combined "accuracy" figure, because the two failure directions are
different products: one is a missed weakening, one is a manufactured false
positive, and a single number hides both.

Every published proportion is a **Wilson lower bound**.  Point estimates travel
beside the bounds, labelled, and are never the claim.

IT MEASURES; IT DOES NOT GATE
------------------------------
Nothing here blocks a merge, materialises a blocking check or fails a build on a
low figure.  ``docs/leads/algorithms.md`` §8 R-A1 declines to argue delta false
negatives away and elects to publish them instead: this package is that
publication.  A number that could stop a merge would acquire an incentive to be
high, and the whole value of this one is that it is allowed to be bad.

THE HARNESS HAS BEEN RED (PL-2)
--------------------------------
``tests/e2e/mutation/test_red_first.py`` runs the harness against a lattice with
rule ``R1_DEONTIC`` switched off and asserts that the kill rate falls below 1.0
with ``deontic_downgrade`` named as a surviving class.  A harness that has only
ever reported 100 % has not been observed to assert anything.
"""

from __future__ import annotations

from .catalogue import load_catalogue, operator_fingerprint
from .errors import (
    CatalogueError,
    FixtureError,
    MutationError,
    OperatorInapplicable,
    UnpopulatedClass,
)
from .fixtures import load_fixtures
from .judge import judge
from .lattice_injection import ALL_RULE_IDS, decide_with, explain_with
from .metrics import (
    false_identity_change_rate,
    false_weaken_rate,
    per_class,
    per_class_family,
    per_family,
    summarise,
    surviving_classes,
)
from .model import KILL, SURVIVE, MutationClass, MutationResult, PipelineOutcome, Revision
from .report import artefact_name, build_report, stable_document, write_report
from .resources import catalogue_sha256
from .runner import RunOutput, Skip, killed, run, survivors
from .version import HARNESS_VERSION, PARAPHRASE_PROFILE, REPORT_SCHEMA
from .wilson import WilsonInterval, wilson_interval, wilson_lower

__all__ = [
    "ALL_RULE_IDS",
    "HARNESS_VERSION",
    "KILL",
    "PARAPHRASE_PROFILE",
    "REPORT_SCHEMA",
    "SURVIVE",
    "CatalogueError",
    "FixtureError",
    "MutationClass",
    "MutationError",
    "MutationResult",
    "OperatorInapplicable",
    "PipelineOutcome",
    "Revision",
    "RunOutput",
    "Skip",
    "UnpopulatedClass",
    "WilsonInterval",
    "artefact_name",
    "build_report",
    "catalogue_sha256",
    "decide_with",
    "explain_with",
    "false_identity_change_rate",
    "false_weaken_rate",
    "judge",
    "killed",
    "load_catalogue",
    "load_fixtures",
    "operator_fingerprint",
    "per_class",
    "per_class_family",
    "per_family",
    "run",
    "stable_document",
    "summarise",
    "surviving_classes",
    "survivors",
    "wilson_interval",
    "wilson_lower",
    "write_report",
]
