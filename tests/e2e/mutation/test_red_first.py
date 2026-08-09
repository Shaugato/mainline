# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""PL-2. The harness must be able to report a SURVIVING mutant, and here it does.

`docs/leads/algorithms.md` §3, worker 10: *"the harness must first report a
surviving mutant (kill rate < 1.0) on a deliberately weakened lattice — a
harness that has only ever reported 100 % is not a harness."*

This file is that proof, and it is written so that it FAILS for the right reason
in every direction it could be wrong:

* if the injection point does nothing, the crippled arm equals the intact arm and
  `test_crippling_r1_lowers_the_kill_rate` fails;
* if the harness cannot express a deontic downgrade at all, the surviving class
  is not `deontic_downgrade` and `test_the_surviving_class_is_named` fails;
* if the intact arm is not strictly better, `test_the_intact_arm_kills_more`
  fails — which is the case where the harness is measuring noise;
* if the published number is a point estimate rather than a bound,
  `test_the_published_number_is_a_lower_bound` fails.

Every one of these was observed red before the operators existed.  A suite that
has never been red asserts nothing, and for a product whose deliverable is a
refusal, that is not a slogan.
"""

from __future__ import annotations

import pytest
from mainline_mutation import (
    KILL,
    build_report,
    run,
    summarise,
    surviving_classes,
)

R1 = frozenset({"R1_DEONTIC"})


@pytest.fixture(scope="module")
def intact():
    return run(seed=0)


@pytest.fixture(scope="module")
def crippled():
    return run(seed=0, disabled_rules=R1)


def test_crippling_r1_lowers_the_kill_rate(intact, crippled):
    hurt = summarise(crippled.results, kind=KILL, confidence="0.95")
    whole = summarise(intact.results, kind=KILL, confidence="0.95")

    assert hurt.trials == whole.trials, (
        "the two arms must run the same mutants; a crippled arm with a different "
        "denominator is measuring a different catalogue"
    )
    assert hurt.interval.point < 1.0, (
        "the crippled arm reported a perfect kill rate. Either the injection point "
        "does nothing or the catalogue contains no mutation R1_DEONTIC is the only "
        "detector of. Both mean this harness has not been observed to assert anything"
    )
    assert hurt.successes < whole.successes


def test_the_surviving_class_is_named(crippled):
    named = surviving_classes(crippled.results)
    assert named, "a kill rate below 1.0 with no named surviving class is unactionable"
    assert "deontic_downgrade" in named, (
        f"R1_DEONTIC was disabled and the deontic downgrades were still caught: {named}. "
        "Either another rule is double-counting R1's slot — which rules.py's partition "
        "forbids — or the mutants are not producing a deontic downgrade at all"
    )


def test_the_intact_arm_kills_more(intact, crippled):
    whole = summarise(intact.results, kind=KILL, confidence="0.95")
    hurt = summarise(crippled.results, kind=KILL, confidence="0.95")
    assert whole.interval.lower > hurt.interval.lower, (
        "the intact arm must report a strictly higher LOWER BOUND than the crippled one. "
        "If it does not, the difference between the arms is inside the noise of the "
        "fixture set and no comparison between them means anything"
    )


def test_the_published_number_is_a_lower_bound(intact):
    report = build_report(intact)
    headline = report["headline"]["kill"]
    assert "wilson_lower" in headline
    assert headline["wilson_lower"] <= headline["point_estimate"]
    assert headline["point_estimate"] <= headline["wilson_upper"]
    assert report["component_versions"]["catalogue_sha256"]
    assert len(report["component_versions"]["catalogue_sha256"]) == 64


def test_the_crippled_arm_says_so_in_the_artefact(crippled):
    report = build_report(crippled)
    assert report["arm"] == "crippled"
    assert report["disabled_lattice_rules"] == ["R1_DEONTIC"]
    assert "R1_DEONTIC" in report["component_versions"]["lattice_version"], (
        "a crippled run must not be publishable under the production lattice version; "
        "the version string is what a reader keys on"
    )


def test_intact_is_the_production_code_path(intact):
    report = build_report(intact)
    assert report["arm"] == "intact"
    assert report["disabled_lattice_rules"] == []
    assert "crippled" not in report["component_versions"]["lattice_version"]


def test_some_mutant_survives_even_intact(intact):
    """The honest one.  A perfect intact score would be the number to distrust.

    Not an assertion that the system is bad — an assertion that the catalogue
    contains at least one mutation this pipeline does not catch, which is what
    makes the published figure a measurement rather than a formality.  If this
    ever goes green the correct response is to add harder mutants, never to
    delete the test.
    """
    named = surviving_classes(intact.results)
    assert named, (
        "the intact arm killed every mutant in the catalogue. That is not a result, it is "
        "a catalogue that has stopped being adversarial. Add mutations; do not celebrate"
    )
