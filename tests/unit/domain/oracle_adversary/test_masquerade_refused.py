# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The attacks that do not go through the oracle at all — they go through the caller.

An adversary who cannot make the model lie usefully has a second target: the
*call site*.  If a compromised or careless caller can hand the resolution a
verdict that is already signed, or run it twice, or supply a theta of its own
choosing, then the ratchet is a formality.  Each of those is refused, and this
module is where the refusals are pinned.

The distinction that makes this suite different from a validation test: none of
these inputs is a typo.  Every one is the shape of a bypass.
"""

from __future__ import annotations

import math

import pytest
from _adversary import INJECTION_PAYLOAD, THETAS, path_a_verdict
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

_MODEL_ID = "au.anthropic.claude-opus-5"
_PROMPT_VERSION = "adjudication.v1+rubric.v1"


def _oracle(
    label: ControlDelta = ControlDelta.STRENGTHEN,
    confidence: float = 1.0,
    *,
    abstained: bool = False,
) -> OracleVerdict:
    return OracleVerdict(
        label=label,
        confidence=confidence,
        rationale="adversary",
        cited_spans=((0, 1),),
        model_id=_MODEL_ID,
        prompt_version=_PROMPT_VERSION,
        abstained=abstained,
    )


# ── laundering a verdict through a basis it did not earn ────────────────────────


def test_a_signed_human_verdict_is_not_re_decidable() -> None:
    """The oldest bypass: get the model a second bite at a disposition a person signed."""
    signed = DeltaVerdict(
        delta=ControlDelta.WEAKEN,
        basis="human",
        witnesses=(
            DeltaWitness(
                rule_id="R1_DEONTIC",
                field="deontic",
                from_repr="MUST",
                to_repr="SHOULD",
                note="signed by the authorised person",
            ),
        ),
        minimal=True,
    )
    with pytest.raises(HumanVerdictNotResolvable, match="basis='human'"):
        resolve(signed, _oracle(), theta=0.5)


@pytest.mark.parametrize("basis", ["lattice+model", "abstain_to_weaken"])
def test_resolution_is_not_composable(basis: str) -> None:
    """Running the ratchet twice would let a second call ratchet what a first raised.

    The attack is arithmetic rather than semantic: the codomain is monotone
    *upward*, so no single call can lower a verdict — but a caller that resolves an
    already-resolved verdict has smuggled a second model opinion into a slot the
    stored ``delta_basis`` claims held one.
    """
    already = DeltaVerdict(
        delta=ControlDelta.WEAKEN,
        basis=basis,  # type: ignore[arg-type]
        witnesses=(),
        minimal=False,
    )
    with pytest.raises(AlreadyResolved, match="not composable"):
        resolve(already, _oracle(), theta=0.5)


@pytest.mark.parametrize(
    ("first_oracle", "expected_basis"),
    [
        (_oracle(ControlDelta.WEAKEN, 1.0), "lattice+model"),
        (_oracle(ControlDelta.WEAKEN, 1.0, abstained=True), "abstain_to_weaken"),
    ],
)
def test_a_resolved_verdict_fed_straight_back_is_refused(
    first_oracle: OracleVerdict, expected_basis: str
) -> None:
    """The same attack, expressed the way a real caller would accidentally write it.

    Both routes out of ``basis='lattice'`` are covered: the model raising the
    verdict, and the abstention floor raising it.  A second call on either would
    be a second model opinion occupying a slot the stored basis claims held one.
    """
    restate = path_a_verdict(ControlDelta.RESTATE)
    once = resolve(restate, first_oracle, theta=0.5)
    assert once.basis == expected_basis, "the sabotage precondition no longer holds"
    with pytest.raises(AlreadyResolved, match="not composable"):
        resolve(once, _oracle(), theta=0.5)


def test_an_unexplainable_weakening_cannot_be_resolved() -> None:
    """D8, one layer earlier than the database.

    A weaken with no minimal unsatisfiable subset is refused by
    ``fn_delta_witness_guard`` with ``P0001``.  Refusing it here as well means a
    caller cannot manufacture a weaken-shaped verdict that carries no explanation
    and then point at the resolution as the thing that produced it.
    """
    naked = DeltaVerdict(delta=ControlDelta.WEAKEN, basis="lattice", witnesses=(), minimal=False)
    with pytest.raises(WitnesslessWeakening, match="empty witness set"):
        resolve(naked, _oracle(), theta=0.5)


# ── theta, which is the one number an attacker would most like to choose ────────


@pytest.mark.parametrize("theta", [-0.0001, -1.0, 1.0001, 2.0, math.inf, -math.inf, math.nan])
def test_theta_outside_the_unit_interval_is_refused(theta: float) -> None:
    """A theta of -1 makes every confidence confident; a theta of NaN makes none.

    Both are calibration attacks and both are refused rather than clamped, because
    a clamped theta is a policy change nobody committed.
    """
    with pytest.raises(ThetaOutOfRange):
        resolve(path_a_verdict(ControlDelta.WEAKEN), _oracle(), theta=theta)


@pytest.mark.parametrize("confidence", [math.nan, math.inf, -math.inf, -0.0001, 1.0001, 2.0])
def test_out_of_contract_confidence_is_refused_not_coerced(confidence: float) -> None:
    """Reading a broken producer as ``0.0`` would be safe for this decision and wrong.

    It converts "our confidence pipeline is broken" into "the model was unsure",
    written into an evidentiary ledger, forever.  A false record is worse than a
    crash on a path that never touches the gate.
    """
    with pytest.raises(MalformedOracleVerdict, match=r"\[0, 1\]"):
        resolve(path_a_verdict(ControlDelta.RESTATE), _oracle(confidence=confidence), theta=0.5)


def test_theta_zero_makes_everything_confident_and_still_clears_nothing() -> None:
    """The maximally permissive legal calibration is still not a bypass."""
    weaken = path_a_verdict(ControlDelta.WEAKEN)
    for label in ControlDelta:
        resolved = resolve(weaken, _oracle(label, 0.0), theta=0.0)
        assert resolved.delta in {ControlDelta.WEAKEN, ControlDelta.REMOVE}


# ── the basis is a claim about who decided, and it has to be true ───────────────


def test_the_model_appears_in_the_basis_only_when_it_raised_the_verdict() -> None:
    """``delta_basis`` is read as "was a model load-bearing for this refusal"."""
    restate = path_a_verdict(ControlDelta.RESTATE)
    concurring = explain(restate, _oracle(ControlDelta.RESTATE, 1.0), theta=0.5)
    assert concurring.verdict.basis == "lattice", (
        "a model that merely agreed does not get to appear in the basis"
    )
    assert concurring.raised_by_model is False

    raising = explain(restate, _oracle(ControlDelta.WEAKEN, 1.0), theta=0.5)
    assert raising.verdict.basis == "lattice+model"
    assert raising.raised_by_model is True


def test_the_arithmetic_of_every_resolution_is_recoverable() -> None:
    """An attack that leaves no arithmetic behind is an attack nobody can audit.

    Every field a reviewer would need to re-run the comparison by hand is on the
    :class:`Resolution`, including the table digest, so a retro-edited resolution
    table is visible the same way a retro-tuned threshold is.
    """
    weaken = path_a_verdict(ControlDelta.WEAKEN)
    oracle = _oracle(ControlDelta.STRENGTHEN, 0.85)
    result = explain(weaken, oracle, theta=0.75)
    assert result.path_a_delta is ControlDelta.WEAKEN
    assert result.oracle_label is ControlDelta.STRENGTHEN
    assert result.oracle_confidence == pytest.approx(0.85)
    assert result.oracle_model_id == _MODEL_ID
    assert result.oracle_prompt_version == _PROMPT_VERSION
    assert result.theta == pytest.approx(0.75)
    assert result.confident is True
    assert len(result.table_sha256) == 64
    assert result.table_version


@pytest.mark.parametrize("theta", THETAS)
def test_a_spoofed_model_identity_changes_nothing_but_the_record(theta: float) -> None:
    """A model claiming to be the lattice is recorded as having claimed it, and ignored."""
    weaken = path_a_verdict(ControlDelta.WEAKEN)
    spoof = OracleVerdict(
        label=ControlDelta.STRENGTHEN,
        confidence=1.0,
        rationale=INJECTION_PAYLOAD,
        cited_spans=(),
        model_id="mainline_domain.lattice",
        prompt_version="human",
        abstained=False,
    )
    result = explain(weaken, spoof, theta=theta)
    assert result.oracle_model_id == "mainline_domain.lattice"
    assert result.verdict.basis != "human"
    assert result.verdict.delta in {ControlDelta.WEAKEN, ControlDelta.REMOVE}
