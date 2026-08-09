# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Render a run as the dated JSON artefact that lands in ``evidence/mutation/``.

THIS IS THE PUBLISHED SURFACE, SO IT CARRIES THE CAVEATS
---------------------------------------------------------
Every artefact states, in the artefact and not in a README somebody may not
read:

* that the number is a **standing measurement and never a gate** — nothing in
  this package blocks a merge, and a low figure fails no build;
* that the adversarial-paraphrase cassettes are **hand-authored** and no model
  was called (PL-3, decision D12), verbatim from the cassette file;
* that Path B was **not consulted**, so the figure is a lower bound on the whole
  system's detection rather than an estimate of it;
* that residue was derived by a **stand-in** for worker W8, named on every row;
* that CBM accounting (worker W9) was **not exercised**;
* which lattice rules were **disabled**, if any.

Nothing in the schema lets a producer omit those.  A caveat that is optional is
a caveat that is absent from the run somebody quotes.

DETERMINISM OF THE DOCUMENT ITSELF
-----------------------------------
``generated_at`` is the only field that moves between two runs of one seed, and
:func:`stable_document` returns the artefact without it so a determinism test
can compare two runs byte for byte.  A test that had to know which keys to strip
would stop working the moment a field was added.
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from mainline_domain.canon.version import CANON_VERSION
from mainline_domain.cat.extract import extractor_version
from mainline_domain.identity.candidates import DEFAULT_BANDS, RESCORE_VERSION
from mainline_domain.identity.candidates.minhash import default_params
from mainline_domain.lattice.version import LATTICE_VERSION, rule_catalogue_fingerprint
from mainline_domain.registry import ENCODING_VERSION

from .catalogue import confidence, load_catalogue, operator_fingerprint
from .directrix import ratified_overlap
from .fixtures import load_fixtures
from .metrics import (
    false_identity_change_rate,
    false_weaken_rate,
    per_class,
    per_class_family,
    per_family,
    summarise,
    surviving_classes,
)
from .model import KILL, SURVIVE
from .paraphrase import provenance_statement
from .pipeline import RESOLUTION_THETA
from .residue import RESIDUE_SOURCE
from .resources import catalogue_sha256
from .runner import RunOutput
from .version import HARNESS_VERSION, PARAPHRASE_PROFILE, REPORT_SCHEMA

__all__ = ["artefact_name", "build_report", "stable_document", "write_report"]

_STANDING: str = (
    "THIS IS A STANDING MEASUREMENT AND NEVER A GATE. Nothing in mainline-mutation blocks a "
    "merge, materialises a blocking check, or fails a build on a low figure. It measures the "
    "residual risk this domain declines to argue away (docs/leads/algorithms.md R-A1) and "
    "publishes it. A number that could stop a merge would acquire an incentive to be high, "
    "and the whole value of this one is that it is allowed to be bad."
)

_LOWER_BOUND_ONLY: str = (
    "EVERY PUBLISHED PROPORTION IS A WILSON LOWER BOUND. Three of three killed is a point "
    "estimate of 1.0 and a 95 % lower bound of 0.44; publishing 1.0 there would be a false "
    "statement about how much evidence exists. Point estimates appear beside the bounds, "
    "labelled, and are never the claim."
)

_PATH_B_ABSENT: str = (
    "PATH B WAS NOT CONSULTED. resolve() was called with oracle=None and theta=1.0, so the "
    "verdict is the model-free floor. The ABSTENTION RATCHET can only ever RAISE a verdict's "
    "force, so consulting an oracle could only improve these numbers — which means this figure "
    "is a LOWER BOUND on the whole system's detection and not an estimate of it."
)


def _component_versions(disabled: tuple[str, ...] = ()) -> dict[str, Any]:
    # A crippled run must NOT be publishable under the production lattice
    # version. The version string is what a reader keys on when they compare two
    # artefacts, and a crippled number wearing `lat1` is the one mislabelling
    # that would make the red-before-green pair unreadable.
    lattice = LATTICE_VERSION
    if disabled:
        lattice = f"{LATTICE_VERSION}+crippled({','.join(disabled)})"
    return {
        "harness_version": HARNESS_VERSION,
        "canon_version": CANON_VERSION,
        "cat_extractor_version": extractor_version(),
        "lattice_version": lattice,
        "lattice_rule_catalogue_fingerprint": rule_catalogue_fingerprint().hex(),
        "registry_encoding_version": ENCODING_VERSION,
        "minhash_version": default_params().minhash_version,
        "rescore_version": RESCORE_VERSION,
        "identity_policy_sha256": DEFAULT_BANDS.fingerprint().hex(),
        "catalogue_sha256": catalogue_sha256(),
        "operator_fingerprint": operator_fingerprint(),
        "residue_source": RESIDUE_SOURCE,
        "resolution_theta": RESOLUTION_THETA,
    }


def _metric_rows(metrics: tuple[Any, ...]) -> list[dict[str, Any]]:
    return [
        {
            "kind": m.kind,
            "class_id": m.class_id,
            "family": m.family,
            "successes": m.successes,
            "trials": m.trials,
            # Lower bound FIRST, everywhere, so a reader skimming a column of
            # numbers reads the claim before the flattering version of it.
            "wilson_lower": m.wilson_lower,
            "point_estimate": m.point_estimate,
            "wilson_upper": m.wilson_upper,
            "confidence": m.confidence,
            "outcome_counts": dict(sorted(m.outcome_counts.items())),
        }
        for m in metrics
    ]


def _result_rows(output: RunOutput) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for result in output.results:
        row: dict[str, Any] = {
            "mutant_id": result.mutant_id,
            "kind": result.kind,
            "class_id": result.class_id,
            "fixture_id": result.fixture_id,
            "family": result.family,
            "outcome": result.outcome,
            "success": result.success,
            "outcome_reason": result.outcome_reason,
            "chain_length": result.chain_length,
            "pipeline": asdict(result.pipeline),
        }
        if result.mutant_id in output.adjacent_max_force:
            row["chain_adjacent_max_force"] = output.adjacent_max_force[result.mutant_id]
        rows.append(row)
    return rows


def build_report(output: RunOutput) -> dict[str, Any]:
    """Assemble the artefact.  ``generated_at`` is added by :func:`write_report`."""
    level = confidence()
    kill = summarise(output.results, kind=KILL, confidence=level)
    survive = summarise(output.results, kind=SURVIVE, confidence=level)

    return {
        "schema": REPORT_SCHEMA,
        "seed": output.seed,
        "disabled_lattice_rules": list(output.disabled_rules),
        "arm": "crippled" if output.disabled_rules else "intact",
        "confidence": level,
        "component_versions": _component_versions(output.disabled_rules),
        "statements": {
            "standing_metric_never_a_gate": _STANDING,
            "lower_bound_only": _LOWER_BOUND_ONLY,
            "path_b_absent": _PATH_B_ABSENT,
            "paraphrase_provenance": provenance_statement(),
            "residue_is_a_stand_in": (
                "Residue was derived by mainline_mutation.residue, a STAND-IN for worker W8 "
                "(margin-assignment), which had not landed when this harness was written. "
                f"Every row records residue_source={RESIDUE_SOURCE!r}. No number here is a "
                "measurement of W8's implementation."
            ),
            "cbm_not_exercised": (
                "The CONSERVATION OF BLAME MASS ledger (worker W9) is not exercised by this "
                "harness: it needs a cluster, a commit DAG and blame closure rows, none of "
                "which a fixture corpus has. The KILL catalogue's success condition is "
                "therefore 'a weakening verdict OR a residue row', not 'or a refused merge'."
            ),
            "cascade_s4_absent": (
                "Cascade stage S4 (anchor-gated ANN over clause_embedding) is not driven: it "
                "needs embeddings and a cluster, and PL-3 forbids a dated path on either. "
                "Identity recovery is measured over S1/S2/S3 only."
            ),
        },
        "corpus": {
            "fixtures": len(load_fixtures()),
            "families": sorted({f.family for f in load_fixtures()}),
            "classes": len(load_catalogue()),
            "paraphrase_profile": PARAPHRASE_PROFILE,
            "directrix_ratified_and_extractable": list(ratified_overlap()),
        },
        "headline": {
            "kill": {
                "wilson_lower": kill.interval.lower,
                "point_estimate": kill.interval.point,
                "wilson_upper": kill.interval.upper,
                "killed": kill.successes,
                "trials": kill.trials,
                "outcome_counts": dict(sorted(kill.outcome_counts.items())),
                "surviving_classes": list(surviving_classes(output.results)),
            },
            "survive": {
                "wilson_lower": survive.interval.lower,
                "point_estimate": survive.interval.point,
                "wilson_upper": survive.interval.upper,
                "preserved": survive.successes,
                "trials": survive.trials,
                "outcome_counts": dict(sorted(survive.outcome_counts.items())),
                "false_identity_change_rate_point_estimate": false_identity_change_rate(
                    output.results
                ),
                "false_weaken_rate_point_estimate": false_weaken_rate(output.results),
            },
        },
        "per_class": _metric_rows(per_class(output.results, confidence=level)),
        "per_family": _metric_rows(per_family(output.results, confidence=level)),
        "per_class_family": _metric_rows(per_class_family(output.results, confidence=level)),
        "results": _result_rows(output),
        "skipped": [
            {"class_id": s.class_id, "fixture_id": s.fixture_id, "reason": s.reason}
            for s in output.skips
        ],
    }


def stable_document(output: RunOutput) -> str:
    """The artefact as canonical JSON, with no timestamp.  What determinism compares."""
    return json.dumps(build_report(output), indent=2, sort_keys=True, ensure_ascii=False)


def artefact_name(output: RunOutput, *, when: dt.datetime) -> str:
    """``mutation-<YYYY-MM-DD>-<arm>-seed<N>.json``.

    Dated because the brief asks for a dated artefact, and armed and seeded
    because two runs on one day that differ in either are two different
    measurements and must not overwrite each other.
    """
    arm = "crippled" if output.disabled_rules else "intact"
    return f"mutation-{when.date().isoformat()}-{arm}-seed{output.seed}.json"


def write_report(output: RunOutput, directory: Path, *, when: dt.datetime | None = None) -> Path:
    """Write the dated artefact and return its path.  Creates ``directory`` if absent."""
    moment = when or dt.datetime.now(tz=dt.UTC)
    document = build_report(output)
    document["generated_at"] = moment.isoformat()
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / artefact_name(output, when=moment)
    target.write_text(
        json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return target
