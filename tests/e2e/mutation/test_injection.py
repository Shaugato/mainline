# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The injection point agrees with the real lattice exactly when nothing is disabled.

`lattice_injection.explain_with` exists so the harness can run against a
deliberately crippled lattice (PL-2).  Its correctness claim is narrow and this
file is the whole of it:

* with ``disabled`` empty it **delegates** to `mainline_domain.lattice.explain`
  and is therefore the production code path, not a copy of it;
* with a rule disabled, that rule's findings are absent and no other rule's are;
* a typo in a rule id **raises** rather than silently disabling nothing — which
  would publish the intact number under a crippled label, the worst possible
  failure for a red-before-green artefact.

Nothing in `mainline_domain.lattice` knows this module exists.  A
``disabled_rules`` argument threaded into the real lattice would be a switch
reachable from a gate path, and a gate whose rules can be turned off by an
argument is not a gate.
"""

from __future__ import annotations

import pytest
from mainline_domain.lattice import explain
from mainline_mutation import load_fixtures
from mainline_mutation.directrix import HARNESS_COMMIT, registry
from mainline_mutation.lattice_injection import ALL_RULE_IDS, decide_with, explain_with
from mainline_mutation.pipeline import view_of


def _pairs():
    fixtures = load_fixtures()
    return [(a, b) for a in fixtures for b in fixtures if a.fixture_id != b.fixture_id]


@pytest.mark.parametrize(
    "pair", _pairs()[:40], ids=lambda p: f"{p[0].fixture_id}->{p[1].fixture_id}"
)
def test_empty_disabled_is_the_production_path(pair):
    ancestor, descendant = (view_of(r.document()) for r in pair)
    mine = explain_with(
        ancestor.cat,
        descendant.cat,
        registry(),
        HARNESS_COMMIT,
        reference_anchors=ancestor.anchors,
        descendant_anchors=descendant.anchors,
    )
    theirs = explain(
        ancestor.cat,
        descendant.cat,
        registry(),
        HARNESS_COMMIT,
        reference_anchors=ancestor.anchors,
        descendant_anchors=descendant.anchors,
    )
    assert mine == theirs


def test_a_disabled_rule_produces_no_findings():
    ancestor = view_of(load_fixtures()[0].document())
    weakened = load_fixtures()[0].raw_text.replace("must not", "should not")
    descendant = view_of(load_fixtures()[0].document(text=weakened))

    whole = explain_with(ancestor.cat, descendant.cat, registry(), HARNESS_COMMIT)
    assert "R1_DEONTIC" in {f.rule_id for f in whole.findings}

    hurt = explain_with(
        ancestor.cat,
        descendant.cat,
        registry(),
        HARNESS_COMMIT,
        disabled=frozenset({"R1_DEONTIC"}),
    )
    assert "R1_DEONTIC" not in {f.rule_id for f in hurt.findings}
    assert {f.rule_id for f in hurt.findings} == {f.rule_id for f in whole.findings} - {
        "R1_DEONTIC"
    }, "disabling one rule must not silence another"


def test_the_crippled_lattice_version_says_so():
    ancestor = view_of(load_fixtures()[0].document())
    descendant = view_of(load_fixtures()[1].document())
    hurt = explain_with(
        ancestor.cat,
        descendant.cat,
        registry(),
        HARNESS_COMMIT,
        disabled=frozenset({"R4_EXCEPTION"}),
    )
    assert "crippled(R4_EXCEPTION)" in hurt.lattice_version


def test_a_typo_raises_rather_than_disabling_nothing():
    ancestor = view_of(load_fixtures()[0].document())
    descendant = view_of(load_fixtures()[1].document())
    with pytest.raises(ValueError, match="are not rule ids"):
        explain_with(
            ancestor.cat,
            descendant.cat,
            registry(),
            HARNESS_COMMIT,
            disabled=frozenset({"R1-DEONTIC"}),
        )


def test_disabling_every_rule_gives_the_neutral_verdict():
    ancestor = view_of(load_fixtures()[0].document())
    weakened = load_fixtures()[0].raw_text.replace("must not", "should not")
    descendant = view_of(load_fixtures()[0].document(text=weakened))
    verdict = decide_with(
        ancestor.cat,
        descendant.cat,
        registry(),
        HARNESS_COMMIT,
        disabled=frozenset(ALL_RULE_IDS),
    )
    assert verdict.delta.value == "restate"
    assert verdict.witnesses == ()
