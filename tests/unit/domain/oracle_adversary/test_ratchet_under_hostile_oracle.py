# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The headline claim, stated against an adversary instead of against a mistake.

``tests/unit/domain/resolution/test_ratchet_property.py`` establishes that no
*well-formed* oracle output lowers the Path-A force.  This module establishes the
stronger thing the product is actually sold on: **an attacker in control of Path B
cannot clear a gate.**  The difference matters because the two failure modes have
different shapes — a wrong model returns plausible values, a compromised one
returns whatever the code reads.

Every test here runs the catalogue in :mod:`_adversary`, which is the threat model
written down.  ``test_falsifiable.py`` proves the catalogue can go red.
"""

from __future__ import annotations

import pytest
from _adversary import (
    ATTACKS,
    INJECTION_PAYLOAD,
    PATH_A,
    THETAS,
    Attack,
    assert_ratchet_holds,
    breaches,
    default_resolver,
    path_a_verdict,
)
from mainline_domain.contracts import ControlDelta, force
from mainline_domain.resolution import ResolutionRefused, explain, resolve

_ATTACK_IDS = [item.name for item in ATTACKS]


def test_the_catalogue_is_not_vacuous() -> None:
    """A threat model with one shape of attack in it is a slogan."""
    names = [item.name for item in ATTACKS]
    assert len(names) == len(set(names)), f"duplicate attack names: {names}"
    assert len(ATTACKS) >= 15, "the catalogue has shrunk; attacks are removed by argument"
    dispositions = {item.disposition for item in ATTACKS}
    assert dispositions == {"resolved", "refused"}, (
        "both dispositions must be exercised: a catalogue that only asserts refusals "
        "is satisfied by a resolver that raises on everything"
    )
    assert all(item.intent for item in ATTACKS), "every attack states what it is trying to do"


def test_no_attack_in_the_catalogue_lowers_the_verdict() -> None:
    """The whole cross product, in one assertion, with the count on the record."""
    cases = assert_ratchet_holds(default_resolver)
    assert cases == len(ATTACKS) * len(PATH_A) * len(THETAS)


@pytest.mark.parametrize("item", ATTACKS, ids=_ATTACK_IDS)
def test_each_attack_individually(item: Attack) -> None:
    """One test per attack, so a failure names the attacker rather than the suite."""
    found = breaches(default_resolver, attacks=[item])
    assert not found, "\n  ".join(str(breach) for breach in found)


@pytest.mark.parametrize("theta", THETAS)
@pytest.mark.parametrize("item", ATTACKS, ids=_ATTACK_IDS)
def test_a_lattice_weakening_is_never_cleared(item: Attack, theta: float) -> None:
    """The sentence that would be said under oath, asserted for every attack.

    Path A found a weakening over blood-written ancestry.  Whatever Path B says,
    at whatever confidence, with whatever flag, the delta of record still carries
    force — the merge is still refused.
    """
    weaken = path_a_verdict(ControlDelta.WEAKEN)
    oracle = item.build(weaken.delta, theta)
    if item.disposition == "refused":
        with pytest.raises(ResolutionRefused):
            resolve(weaken, oracle, theta=theta)
        return
    resolved = resolve(weaken, oracle, theta=theta)
    assert force(resolved.delta) >= force(ControlDelta.WEAKEN), (
        f"attack {item.name!r} cleared a lattice weakening at theta={theta}: "
        f"resolved to {resolved.delta.value}"
    )


@pytest.mark.parametrize("theta", THETAS)
def test_an_absent_path_b_is_an_abstention_not_a_no_op(theta: float) -> None:
    """Killing the queue is an attack, and its result is the abstention floor."""
    for delta in ControlDelta:
        verdict_a = path_a_verdict(delta)
        result = explain(verdict_a, None, theta=theta)
        assert result.abstained is True
        assert result.oracle_present is False
        assert force(result.verdict.delta) >= force(verdict_a.delta)
        assert force(result.verdict.delta) >= force(ControlDelta.WEAKEN), (
            "an oracle that never answered must resolve through the floor, not "
            "through 'nothing to add'"
        )
        assert result.verdict.basis == "abstain_to_weaken"


@pytest.mark.parametrize("theta", THETAS)
def test_an_abstention_flag_beats_a_confident_clearing_label(theta: float) -> None:
    """``abstained`` is read before the number, at every theta including 0.0."""
    weaken = path_a_verdict(ControlDelta.WEAKEN)
    oracle = next(a for a in ATTACKS if a.name == "confident_abstention").build(weaken.delta, theta)
    result = explain(weaken, oracle, theta=theta)
    assert result.abstained is True
    assert result.verdict.basis == "abstain_to_weaken"
    assert force(result.verdict.delta) >= force(ControlDelta.WEAKEN)


@pytest.mark.parametrize("theta", THETAS)
def test_injected_prose_never_reaches_the_verdict(theta: float) -> None:
    """The payload is stored as evidence and appears nowhere in the decision.

    ``rationale`` is the field an injection survives into, and it is carried on
    the :class:`Resolution` — deliberately, because suppressing it would be an
    edit to evidence.  What must not happen is any of it appearing in the
    ``DeltaVerdict``, which is what a gate and a renderer read.
    """
    weaken = path_a_verdict(ControlDelta.WEAKEN)
    oracle = next(a for a in ATTACKS if a.name == "injected_rationale").build(weaken.delta, theta)
    result = explain(weaken, oracle, theta=theta)

    assert result.oracle_rationale == INJECTION_PAYLOAD, (
        "the payload must be kept on the record; a silent strip is an edit to evidence"
    )
    rendered = repr(result.verdict)
    for token in ("IGNORE", "R1_DEONTIC is satisfied", "safe_direction", "Approve"):
        assert token not in rendered, (
            f"model prose {token!r} reached the DeltaVerdict, which is what the gate reads"
        )
    assert result.verdict.witnesses == weaken.witnesses
    assert result.verdict.basis in {"lattice", "lattice+model", "abstain_to_weaken"}
    assert result.verdict.basis != "human"


@pytest.mark.parametrize("item", ATTACKS, ids=_ATTACK_IDS)
def test_no_attack_forges_a_witness(item: Attack) -> None:
    """Witnesses are the lattice's, in every cell, for every attack.

    The value of running two paths is that neither can forge the other's output.
    A witness is a ``rule_id`` plus a from/to pair, and the model has no route to
    one: the resolution copies Path A's tuple or copies nothing.
    """
    for verdict_a in PATH_A:
        for theta in THETAS:
            oracle = item.build(verdict_a.delta, theta)
            if item.disposition == "refused":
                continue
            resolved = resolve(verdict_a, oracle, theta=theta)
            assert resolved.witnesses == verdict_a.witnesses, (
                f"attack {item.name!r} changed the witness set at theta={theta}"
            )


@pytest.mark.parametrize("item", ATTACKS, ids=_ATTACK_IDS)
def test_minimality_is_withdrawn_whenever_the_resolution_moves(item: Attack) -> None:
    """A witness set that no longer explains the verdict does not get to claim it is minimal."""
    for verdict_a in PATH_A:
        for theta in THETAS:
            if item.disposition == "refused":
                continue
            oracle = item.build(verdict_a.delta, theta)
            resolved = resolve(verdict_a, oracle, theta=theta)
            if resolved.delta is not verdict_a.delta:
                assert resolved.minimal is False, (
                    f"attack {item.name!r} moved the delta to {resolved.delta.value} "
                    f"and the verdict still claims a minimal witness set"
                )
