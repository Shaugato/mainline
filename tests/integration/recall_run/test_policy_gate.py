# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""What a run refuses to start under, and the order in which it refuses.

Two gates fire before a single row is retrieved and before a single token is spent.

**MI18 — a run cites only an anchored policy.** ``recall_policy.anchored_tree_size`` must be
non-NULL, meaning the policy's commitment has landed in a cosigned checkpoint, before a run
may cite the row. ``fn_recall_policy_anchored`` (migration 0112) enforces it on
``recall_run`` INSERT with a ``P0001``; the check here is the same refusal taken earlier. It
never *substitutes* for the trigger — ``tests/integration/recall_schema/test_rc04_policy_
anchored.py`` asserts the database still refuses with this check removed.

**M5 THYMOGATE — a policy that missed a known killer may not run.** If the policy names a
certificate, that certificate must exist and be clean. Bringing into existence a tuned
retriever that would have missed a known killer is the one thing negative selection exists to
prevent, and it does not become acceptable because a permit is waiting. The column is nullable
at K4 and becomes ``NOT NULL`` at K8 (recall lead D14), so *no* certificate is currently a
legal state — but a certificate that is named and unreadable is not, because **the absence of
a verdict is not a pass**.

The ordering assertion is the one that is easy to lose in a refactor: a run that spent twenty
seconds reranking and *then* discovered its policy was never anchored has burned a model
budget to produce a refusal that reads like a bug.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

import pytest
from _run_corpus import POLICY_ROW, THYMOGATE_ROW
from _run_fakes import FixtureReranker, verdicts
from mainline_recall_agent.run.errors import PolicyRefused, RunRefused, ThymogateRefused
from mainline_recall_agent.run.probabilistic import ChannelCOutcome


@dataclass
class SpyArmRunner:
    """An arm runner that records whether the run ever got as far as retrieval."""

    ran: list[bool] = field(default_factory=list)

    def run(self) -> ChannelCOutcome:
        self.ran.append(True)
        raise AssertionError(
            "the ANN arms executed under a policy the gate should have refused: the "
            "policy gate must fire before any retrieval and before any model call"
        )


def _policy(**overrides) -> tuple:
    """One POLICY_SQL row with named columns overridden."""
    columns = [
        "policy_version", "taxonomy_ver", "embed_model", "gen_model", "prompt_version",
        "beam_size", "tau", "arms", "calibrator", "anchored_tree_size",
        "thymogate_certificate_id",
    ]
    row = list(POLICY_ROW)
    for name, value in overrides.items():
        row[columns.index(name)] = value
    return tuple(row)


def _thymogate(**overrides) -> tuple:
    columns = [
        "certificate_id", "config_digest", "panel_digest", "panel_size", "n_missed", "verdict"
    ]
    row = list(THYMOGATE_ROW)
    for name, value in overrides.items():
        row[columns.index(name)] = value
    return tuple(row)


def _gated_harness(build_harness, cluster_kwargs: dict):
    from _run_fakes import FakeCluster  # noqa: PLC0415 - sibling fixture module

    spy = SpyArmRunner()
    judge = FixtureReranker(table=verdicts())
    harness = build_harness(
        cluster=FakeCluster(**cluster_kwargs),
        arm_runner=spy,
        reranker=judge,
    )
    return harness, spy, judge


def test_a_clean_anchored_policy_runs(harness) -> None:
    """Green half: the fixture policy is anchored and its THYMOGATE certificate is clean."""
    outcome = harness.run()
    assert outcome.open_blocking > 0


def test_an_unanchored_policy_refuses_before_retrieval(build_harness) -> None:
    """MI18. A policy whose commitment is not in a checkpoint could be retro-fitted after."""
    harness, spy, judge = _gated_harness(
        build_harness, {"policy_row": _policy(anchored_tree_size=None)}
    )
    with pytest.raises(PolicyRefused, match="anchored_tree_size"):
        harness.run()
    assert spy.ran == [], "retrieval must not have started"
    assert judge.calls == [], "no model budget may be spent behind a refused policy"
    assert harness.cluster.transactions == []


def test_an_absent_policy_refuses(build_harness) -> None:
    """tau is a calibration artefact with its own commit and author; a run cannot invent one."""
    harness, spy, _judge = _gated_harness(build_harness, {"policy_row": None})
    with pytest.raises(PolicyRefused, match="no recall_policy row"):
        harness.run()
    assert spy.ran == []


def test_a_malformed_tau_refuses(build_harness) -> None:
    """A threshold outside [0, 1] is not a default to fall back from."""
    harness, spy, _judge = _gated_harness(
        build_harness,
        {"policy_row": _policy(tau=json.dumps({"1": 0.85, "2": 0.75, "3": 1.6}))},
    )
    with pytest.raises(PolicyRefused, match="outside"):
        harness.run()
    assert spy.ran == []


def test_a_named_but_missing_thymogate_certificate_refuses(build_harness) -> None:
    """The absence of a verdict is not a pass."""
    harness, spy, judge = _gated_harness(build_harness, {"thymogate_row": None})
    with pytest.raises(ThymogateRefused, match="no such row exists"):
        harness.run()
    assert spy.ran == []
    assert judge.calls == []


def test_a_failed_thymogate_certificate_refuses(build_harness) -> None:
    """A retriever measured against the panel of the fleet's known killers, and missing one."""
    harness, spy, _judge = _gated_harness(
        build_harness, {"thymogate_row": _thymogate(verdict="fail", n_missed=2)}
    )
    with pytest.raises(ThymogateRefused, match="missed"):
        harness.run()
    assert spy.ran == []


def test_a_self_contradictory_thymogate_certificate_refuses(build_harness) -> None:
    """``verdict='pass'`` with a non-zero miss count is a finding, not a pass."""
    harness, spy, _judge = _gated_harness(
        build_harness, {"thymogate_row": _thymogate(verdict="pass", n_missed=1)}
    )
    with pytest.raises(ThymogateRefused):
        harness.run()
    assert spy.ran == []


def test_no_certificate_at_all_is_legal_at_k4(build_harness) -> None:
    """Recall lead D14: the column is nullable at K4 and becomes NOT NULL at K8.

    Legal is not the same as good, and this test exists to record which of the two is being
    asserted. Naming a certificate that cannot be read is a refusal; naming none is a gap that
    a later milestone closes with a ``NOT NULL``, not with an exception today.
    """
    from _run_fakes import FakeCluster  # noqa: PLC0415 - sibling fixture module

    harness = build_harness(
        cluster=FakeCluster(policy_row=_policy(thymogate_certificate_id=None))
    )
    outcome = harness.run()
    assert outcome.open_blocking > 0


def test_an_unloadable_calibrator_refuses(build_harness) -> None:
    """``p_relevant`` is an exhibit: a run may not fall back to an uncalibrated score."""
    harness, spy, _judge = _gated_harness(
        build_harness,
        {"policy_row": _policy(calibrator=json.dumps({"schema": "something-else"}))},
    )
    with pytest.raises(RunRefused, match="calibrator"):
        harness.run()
    assert spy.ran == []


def test_a_permit_citing_no_clause_refuses(build_harness) -> None:
    """A receipt asserting that nothing was relevant to nothing is not evidence."""
    from _run_fakes import FakeCluster  # noqa: PLC0415 - sibling fixture module

    cluster = FakeCluster()
    harness = build_harness(cluster=cluster)
    # Empty the citation set the way an unscoped permit would.
    original = harness.orchestrator._session.query

    def _empty(sql, params=()):
        from mainline_recall_agent.run.channels import (  # noqa: PLC0415
            CITED_CLAUSES_SQL,
        )

        if sql == CITED_CLAUSES_SQL:
            return []
        return original(sql, params)

    harness.orchestrator._session.query = _empty  # type: ignore[method-assign]
    with pytest.raises(RunRefused, match="cites no clause"):
        harness.run()
    assert cluster.transactions == []
