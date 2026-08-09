# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""PL-2, discharged permanently rather than once.

A suite whose deliverable is a refusal proves nothing until it has been observed
red **for the right reason**.  The usual discharge of that obligation is a commit
in the history where the test failed, which is evidence only to someone willing to
walk the log and re-run an old tree.

This module discharges it differently and, we think, better: it keeps three
deliberately compromised resolutions in the repository forever and asserts that
the adversary property **fails against each of them**, naming the attack that won.
The red is reproducible on any checkout, by anyone, in a second — and it stays
reproducible, because a future edit that weakens
:func:`_adversary.breaches` turns these tests green and this file red.

The three compromises are not strawmen.  Each is a shape that a competent engineer
produces while trying to do the right thing:

``_trusting``
    "the model is confident and it disagrees; take its word."  This is the natural
    implementation of *ensemble* and it is exactly the bug.
``_coercing``
    "a confidence of NaN can't be compared, so treat it as zero — that's the safe
    direction."  Safe for this decision, and it converts a broken producer into a
    permanent stream of nuisance blocks that nobody investigates.
``_paranoid``
    "when in doubt, refuse."  Over-blocking is the failure mode this product is
    most likely to die of, and a catalogue that did not test for it would be
    satisfied by a resolver that raised on every input.
"""

from __future__ import annotations

from dataclasses import replace

import pytest
from _adversary import (
    ATTACKS,
    PATH_A,
    THETAS,
    assert_ratchet_holds,
    breaches,
    default_resolver,
)
from mainline_domain.contracts import ControlDelta, DeltaVerdict, OracleVerdict
from mainline_domain.resolution import ResolutionRefused, resolve


class _Sabotage(ResolutionRefused):
    """Raised by :func:`_paranoid`, which refuses everything on principle."""


def _trusting(path_a: DeltaVerdict, oracle: OracleVerdict | None, theta: float) -> DeltaVerdict:
    """Take a confident model's label as the answer.  The ensemble bug."""
    if oracle is not None and not oracle.abstained and oracle.confidence >= theta:
        return DeltaVerdict(
            delta=oracle.label,
            basis="lattice+model",
            witnesses=path_a.witnesses,
            minimal=False,
        )
    return resolve(path_a, oracle, theta=theta)


def _coercing(path_a: DeltaVerdict, oracle: OracleVerdict | None, theta: float) -> DeltaVerdict:
    """Clamp an out-of-contract confidence instead of refusing it."""
    if oracle is not None and not 0.0 <= oracle.confidence <= 1.0:
        oracle = replace(oracle, confidence=0.0)
    if oracle is not None and oracle.confidence != oracle.confidence:  # NaN
        oracle = replace(oracle, confidence=0.0)
    return resolve(path_a, oracle, theta=theta)


def _paranoid(
    path_a: DeltaVerdict,  # noqa: ARG001 — the point is that it reads nothing
    oracle: OracleVerdict | None,  # noqa: ARG001
    theta: float,  # noqa: ARG001
) -> DeltaVerdict:
    """Refuse every input.  Maximally safe, completely useless."""
    raise _Sabotage("refusing on principle")


# ── the shipped resolution passes ───────────────────────────────────────────────


def test_the_shipped_resolution_survives_the_catalogue() -> None:
    """The green half.  Without the red half below it means nothing."""
    cases = assert_ratchet_holds(default_resolver)
    assert cases == len(ATTACKS) * len(PATH_A) * len(THETAS)


# ── and three compromised ones do not ───────────────────────────────────────────


def test_the_property_catches_a_resolver_that_trusts_a_confident_model() -> None:
    """The ensemble bug is caught, and the failure names the attack that won."""
    found = breaches(_trusting)
    assert found, "a resolver that takes a confident model's label must breach the ratchet"

    kinds = {breach.kind for breach in found}
    assert "lowered" in kinds
    assert "cleared" in kinds, (
        "the compromised resolver must be shown clearing a lattice weakening, which "
        "is the sentence the product exists to make impossible"
    )
    assert {"total_clearance", "confident_restate"} <= {breach.attack for breach in found}

    with pytest.raises(AssertionError, match="the abstention ratchet was breached"):
        assert_ratchet_holds(_trusting)


def test_the_property_catches_a_resolver_that_coerces_a_malformed_confidence() -> None:
    """Clamping is not refusing, and the difference is a false record in a ledger."""
    found = breaches(_coercing)
    assert found, "coercing an out-of-contract confidence must be reported"
    assert {breach.kind for breach in found} == {"not_refused"}
    assert {breach.attack for breach in found} == {
        item.name for item in ATTACKS if item.disposition == "refused"
    }

    with pytest.raises(AssertionError, match="the abstention ratchet was breached"):
        assert_ratchet_holds(_coercing)


def test_the_property_catches_a_resolver_that_refuses_everything() -> None:
    """Over-blocking is a failure, not a conservative success."""
    found = breaches(_paranoid)
    assert found, "a resolver that refuses well-formed input must be reported"
    assert {breach.kind for breach in found} == {"over_refused"}
    assert {breach.attack for breach in found} == {
        item.name for item in ATTACKS if item.disposition == "resolved"
    }

    with pytest.raises(AssertionError, match="the abstention ratchet was breached"):
        assert_ratchet_holds(_paranoid)


def test_the_failure_message_is_a_diagnosis_and_not_a_verdict() -> None:
    """A message that says only 'the property failed' makes the reader re-derive it."""
    with pytest.raises(AssertionError) as raised:
        assert_ratchet_holds(_trusting)
    message = str(raised.value)
    assert "attack=" in message
    assert "path_a=" in message
    assert "theta=" in message
    assert "total_clearance" in message


def test_a_single_attack_can_be_run_in_isolation() -> None:
    """The catalogue is addressable, so a breach can be reproduced without the rest."""
    only = [item for item in ATTACKS if item.name == "total_clearance"]
    found = breaches(_trusting, attacks=only, path_a=[PATH_A[0]], thetas=[0.5])
    assert all(breach.attack == "total_clearance" for breach in found)
    assert breaches(default_resolver, attacks=only) == []


def test_the_catalogue_covers_every_member_of_the_delta_enum() -> None:
    """An attack that is only ever run against one Path-A verdict is not run at all."""
    assert {verdict.delta for verdict in PATH_A} == set(ControlDelta)
