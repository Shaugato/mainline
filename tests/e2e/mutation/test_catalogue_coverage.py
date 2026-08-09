# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Every declared class has at least one fixture and one recorded result.

This is the ``done_when`` clause that a mutation harness fails most quietly.  A
class that produces no trial contributes nothing to the aggregate and looks
identical, in the artefact, to a class that produced trials and passed them all.
The Wilson interval already refuses to flatter an empty class — zero of zero has
a lower bound of 0.0 — but a class that silently stopped applying would still be
a claim the catalogue makes and the number does not support.
"""

from __future__ import annotations

from collections import Counter

import pytest
from mainline_mutation import KILL, SURVIVE, build_report, load_catalogue, load_fixtures, run
from mainline_mutation.catalogue import operators


@pytest.fixture(scope="module")
def output():
    return run(seed=0)


@pytest.fixture(scope="module")
def by_class(output):
    return Counter(r.class_id for r in output.results)


def test_the_catalogue_declares_both_kinds():
    kinds = {c.kind for c in load_catalogue()}
    assert kinds == {KILL, SURVIVE}, (
        "decision D13 is two catalogues, not one. A build with only one kind is measuring "
        "one failure direction and calling it accuracy"
    )


def test_every_declared_class_has_an_operator():
    declared = {c.class_id for c in load_catalogue()}
    assert declared == set(operators()), (
        "load_catalogue() is supposed to refuse this pairing mismatch at import; if this "
        "assertion is the thing that caught it, that check has regressed"
    )


@pytest.mark.parametrize("class_id", [c.class_id for c in load_catalogue()])
def test_every_class_produced_at_least_one_result(by_class, class_id):
    assert by_class[class_id] >= 1, (
        f"{class_id} produced no trial against any of the {len(load_fixtures())} fixtures. "
        "A class that contributes nothing makes the published aggregate a statement about a "
        "smaller catalogue than the artefact claims"
    )


def test_the_brief_s_named_classes_are_all_present():
    """Every class the worker brief enumerates, by name, present in the declaration."""
    declared = {c.class_id for c in load_catalogue()}
    kill_required = {
        "deontic_downgrade",
        "setpoint_nudge_1pct",
        "setpoint_nudge_5pct",
        "setpoint_nudge_25pct",
        "comparator_loosening",
        "hedge_insertion",
        "exception_insertion",
        "quantifier_narrowing",
        "verification_step_deletion",
        "frequency_lengthening",
        "uncompensated_anchor_drop",
        "clause_split_and_dilute",
        "salami_5",
        "salami_10",
        "salami_20",
        "adversarial_paraphrase",
    }
    survive_required = {
        "retypeset",
        "renumber",
        "reflow_rewrap",
        "document_split",
        "document_merge",
        "ocr_noise",
        "table_to_prose",
        "heading_level_change",
        "whitespace_punctuation_churn",
        "template_migration",
        "appendix_relocation",
        "cross_reference_renumbering",
    }
    assert kill_required <= declared
    assert survive_required <= declared


def test_every_family_is_exercised(output):
    families = {f.family for f in load_fixtures()}
    exercised = {r.family for r in output.results}
    assert families == exercised, (
        "a document family with no results is a breakdown axis with an empty column, and a "
        "reader comparing families would draw a conclusion from its absence"
    )


def test_every_skip_carries_a_reason(output):
    for skip in output.skips:
        assert skip.reason.strip(), (
            f"{skip.class_id}/{skip.fixture_id} was skipped with no reason. A denominator "
            "that shrank silently is how a kill rate improves without anything improving"
        )


def test_the_artefact_publishes_the_skips(output):
    report = build_report(output)
    assert len(report["skipped"]) == len(output.skips)
    assert all(row["reason"] for row in report["skipped"])


def test_every_published_metric_row_carries_its_denominator(output):
    report = build_report(output)
    for section in ("per_class", "per_family", "per_class_family"):
        for row in report[section]:
            assert row["trials"] >= 1
            assert row["successes"] <= row["trials"]
            assert row["wilson_lower"] <= row["point_estimate"] <= row["wilson_upper"]
            assert row["confidence"] == report["confidence"]
