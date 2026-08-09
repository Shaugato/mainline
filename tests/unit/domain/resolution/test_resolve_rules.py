# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The four refusals on the way in, and the four rules on the way through.

The ratchet property lives in ``test_ratchet_property.py``.  This file asserts
the things a property test cannot: that specific, nameable inputs are refused
with specific, nameable exceptions, and that the witness set and the ``minimal``
flag are carried honestly.
"""

from __future__ import annotations

import pytest
from mainline_domain.contracts import ControlDelta, DeltaVerdict, DeltaWitness, OracleVerdict
from mainline_domain.resolution import (
    AlreadyResolved,
    HumanVerdictNotResolvable,
    MalformedOracleVerdict,
    ThetaOutOfRange,
    WitnesslessWeakening,
    explain,
    resolve,
)

_WITNESS = DeltaWitness(
    rule_id="R1_DEONTIC",
    field="deontic",
    from_repr="MUST",
    to_repr="SHOULD",
    note="shall -> should",
)
_THETA = 0.75


def _a(
    delta: ControlDelta,
    *,
    basis: str = "lattice",
    witnesses: tuple = (),
    minimal: bool = False,
):
    return DeltaVerdict(delta=delta, basis=basis, witnesses=witnesses, minimal=minimal)  # type: ignore[arg-type]


def _b(label: ControlDelta, confidence: float, *, abstained: bool = False) -> OracleVerdict:
    return OracleVerdict(
        label=label,
        confidence=confidence,
        rationale="relation=x band=y",
        cited_spans=((0, 4),),
        model_id="au.anthropic.claude-opus-5",
        prompt_version="adjudication.v1+rubric.v1",
        abstained=abstained,
    )


# ── the four refusals ───────────────────────────────────────────────────────────


def test_a_human_verdict_is_never_re_resolved() -> None:
    with pytest.raises(HumanVerdictNotResolvable, match="basis='human'"):
        resolve(_a(ControlDelta.RESTATE, basis="human"), _b(ControlDelta.WEAKEN, 0.9), theta=_THETA)


@pytest.mark.parametrize("basis", ["lattice+model", "abstain_to_weaken"])
def test_resolution_is_not_composable(basis: str) -> None:
    with pytest.raises(AlreadyResolved, match="not composable"):
        resolve(
            _a(ControlDelta.WEAKEN, basis=basis, witnesses=(_WITNESS,)),
            _b(ControlDelta.RESTATE, 0.9),
            theta=_THETA,
        )


@pytest.mark.parametrize("delta", [ControlDelta.WEAKEN, ControlDelta.REMOVE])
def test_a_witnessless_lattice_weakening_is_refused(delta: ControlDelta) -> None:
    """Decision D8, one layer above the database that also refuses it."""
    with pytest.raises(WitnesslessWeakening, match="empty witness set"):
        resolve(_a(delta), _b(ControlDelta.WEAKEN, 0.9), theta=_THETA)


@pytest.mark.parametrize("confidence", [-0.1, 1.1, float("nan")])
def test_a_confidence_outside_the_interval_is_refused(confidence: float) -> None:
    with pytest.raises(MalformedOracleVerdict):
        resolve(_a(ControlDelta.RESTATE), _b(ControlDelta.RESTATE, confidence), theta=_THETA)


@pytest.mark.parametrize("theta", [-0.01, 1.01, float("nan")])
def test_a_theta_outside_the_interval_is_refused(theta: float) -> None:
    with pytest.raises(ThetaOutOfRange):
        resolve(_a(ControlDelta.RESTATE), _b(ControlDelta.RESTATE, 0.9), theta=theta)


# ── the four rules, by example ──────────────────────────────────────────────────


def test_rule_1_identical_verdicts_are_accepted_even_below_theta() -> None:
    """``A == B`` fires before the confidence gate — the brief's own ordering.

    This is the one place ordering is load-bearing. If the gate came first, a
    low-confidence model would manufacture a refusal out of two paths that
    already agreed exactly, and the model would become the reason for a block
    without having found anything.
    """
    result = explain(_a(ControlDelta.RESTATE), _b(ControlDelta.RESTATE, 0.1), theta=_THETA)
    assert result.verdict.delta is ControlDelta.RESTATE
    assert result.cell.rule == "CONCUR"
    assert result.verdict.basis == "lattice"


def test_rule_2_either_path_finding_a_weakening_weakens() -> None:
    result = explain(_a(ControlDelta.RESTATE), _b(ControlDelta.WEAKEN, 0.85), theta=_THETA)
    assert result.verdict.delta is ControlDelta.WEAKEN
    assert result.verdict.basis == "lattice+model"
    assert result.raised_by_model


def test_rule_2_does_not_flatten_a_removal_down_to_a_weakening() -> None:
    """The extension the five-member codomain forces, asserted directly."""
    result = explain(
        _a(ControlDelta.REMOVE, witnesses=(_WITNESS,), minimal=True),
        _b(ControlDelta.WEAKEN, 0.85),
        theta=_THETA,
    )
    assert result.verdict.delta is ControlDelta.REMOVE
    assert result.verdict.basis == "lattice"


def test_rule_3_a_confident_neutral_disagreement_takes_the_lattice_member() -> None:
    result = explain(_a(ControlDelta.RESTATE), _b(ControlDelta.STRENGTHEN, 0.85), theta=_THETA)
    assert result.verdict.delta is ControlDelta.RESTATE
    assert result.cell.rule == "NEUTRAL_ACCEPTED"


def test_rule_4_an_unconfident_neutral_disagreement_weakens() -> None:
    result = explain(_a(ControlDelta.RESTATE), _b(ControlDelta.STRENGTHEN, 0.5), theta=_THETA)
    assert result.verdict.delta is ControlDelta.WEAKEN
    assert result.cell.rule == "NEUTRAL_UNCONFIRMED"
    assert result.verdict.basis == "abstain_to_weaken"


def test_theta_is_inclusive_at_the_boundary() -> None:
    """``confidence >= theta``. Stated once, tested once, never guessed at again."""
    at = explain(_a(ControlDelta.RESTATE), _b(ControlDelta.STRENGTHEN, _THETA), theta=_THETA)
    just_below = explain(
        _a(ControlDelta.RESTATE), _b(ControlDelta.STRENGTHEN, _THETA - 1e-9), theta=_THETA
    )
    assert at.confident is True
    assert at.cell.rule == "NEUTRAL_ACCEPTED"
    assert just_below.confident is False
    assert just_below.cell.rule == "NEUTRAL_UNCONFIRMED"


def test_a_model_that_disagrees_downward_is_ignored_and_says_so() -> None:
    result = explain(
        _a(ControlDelta.WEAKEN, witnesses=(_WITNESS,), minimal=True),
        _b(ControlDelta.STRENGTHEN, 1.0),
        theta=_THETA,
    )
    assert result.verdict.delta is ControlDelta.WEAKEN
    assert result.cell.rule == "MODEL_LOWER_IGNORED"
    assert result.verdict.basis == "lattice"


# ── witnesses and minimality ────────────────────────────────────────────────────


def test_the_model_never_contributes_a_witness() -> None:
    result = explain(_a(ControlDelta.RESTATE), _b(ControlDelta.WEAKEN, 0.85), theta=_THETA)
    assert result.verdict.witnesses == ()
    assert result.verdict.basis == "lattice+model"


def test_witnesses_are_carried_when_the_lattice_verdict_stands() -> None:
    result = explain(
        _a(ControlDelta.WEAKEN, witnesses=(_WITNESS,), minimal=True),
        _b(ControlDelta.WEAKEN, 0.85),
        theta=_THETA,
    )
    assert result.verdict.witnesses == (_WITNESS,)
    assert result.verdict.minimal is True


def test_minimality_is_withdrawn_once_the_resolution_moves_the_delta() -> None:
    """A witness set that explained ``restate`` does not explain ``weaken``."""
    result = explain(
        _a(ControlDelta.RESTATE, witnesses=(_WITNESS,), minimal=True),
        _b(ControlDelta.WEAKEN, 0.85),
        theta=_THETA,
    )
    assert result.verdict.minimal is False


def test_minimality_is_withdrawn_under_the_abstention_floor() -> None:
    result = explain(
        _a(ControlDelta.WEAKEN, witnesses=(_WITNESS,), minimal=True),
        _b(ControlDelta.WEAKEN, 0.0, abstained=True),
        theta=_THETA,
    )
    assert result.verdict.delta is ControlDelta.WEAKEN
    assert result.verdict.basis == "abstain_to_weaken"
    assert result.verdict.minimal is False


# ── an absent Path B ────────────────────────────────────────────────────────────


def test_an_absent_oracle_records_that_nothing_ran() -> None:
    result = explain(_a(ControlDelta.RESTATE), None, theta=_THETA)
    assert result.oracle_present is False
    assert result.oracle_label is None
    assert result.oracle_confidence is None
    assert result.abstained is True
    assert result.verdict.delta is ControlDelta.WEAKEN


def test_resolve_is_a_projection_of_explain() -> None:
    a, b = _a(ControlDelta.RESTATE), _b(ControlDelta.WEAKEN, 0.85)
    assert resolve(a, b, theta=_THETA) == explain(a, b, theta=_THETA).verdict


def test_the_table_identity_travels_with_every_resolution() -> None:
    result = explain(_a(ControlDelta.RESTATE), _b(ControlDelta.RESTATE, 0.9), theta=_THETA)
    assert result.table_version == "ratchet.v1"
    assert len(result.table_sha256) == 64
