# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""RED FIRST (PL-2): an unratified parameter abstains, and abstention is ``weaken``.

Decision D6, in one file.  This was the second artefact worker W2 wrote and it
was red before :mod:`mainline_domain.registry` existed.

WHY "NEUTRAL" IS THE WRONG ANSWER, RESTATED AS A TEST
-----------------------------------------------------
The intuitive reading is that if the registry knows nothing about a parameter,
rule R2 has learned nothing, so the edit should be classified as it would have
been without R2 at all — ``restate``.  That reading is wrong here for a
structural reason, and it is the reason this file exists rather than a comment.

**The registry's coverage is under the author's influence.**  If absent meant
neutral, then a parameter that is absent from DIRECTRIX is a parameter whose
setpoint can be moved invisibly — and *removing* an entry, or simply never
adding one, becomes a way to move a setpoint without the lattice firing.  Under
D6 the incentive inverts: the way to stop the gate blocking on a parameter is to
ratify it, in a signed commit, which binds the direction publicly *before* the
edit anyone cares about is proposed.

That is the adoption ratchet, and the tests below are what stops somebody
"fixing" the nuisance blocks by flipping the default.
"""

from __future__ import annotations

import hashlib
import uuid

import pytest
from mainline_domain.contracts import ControlDelta
from mainline_domain.quantity import quantity
from mainline_domain.registry import (
    AbstentionReason,
    EntryStatus,
    SafeDirection,
    SafeDirectionRegistry,
    delta_for_abstention,
    load_registry,
    load_seed,
    seed_source,
    setpoint_delta,
)

_SITE = uuid.UUID("9f1c2d3e-4a5b-6c7d-8e9f-0a1b2c3d4e5f")


def _commit(label: str) -> bytes:
    return hashlib.sha256(f"mainline-directrix-test/{label}".encode()).digest()


def _registry(
    status: EntryStatus = EntryStatus.RATIFIED, *, signed: bool = True
) -> SafeDirectionRegistry:
    head = _commit(f"seed/{status.value}/{signed}")
    source = seed_source(site_id=_SITE, commit_id=head, signed=signed, status=status)
    return load_registry(source, site_id=_SITE, as_of_commit=head)


def test_a_parameter_absent_from_the_registry_abstains() -> None:
    registry = _registry()
    assert registry.safe_direction("torque_of_the_left_handed_widget") is SafeDirection.ABSTAIN
    resolution = registry.resolve("torque_of_the_left_handed_widget")
    assert resolution.reason is AbstentionReason.NOT_IN_REGISTRY
    assert resolution.entry is None


def test_the_helper_maps_abstain_to_weaken_and_not_to_neutral() -> None:
    """The headline of decision D6."""
    registry = _registry()
    resolution = registry.resolve("torque_of_the_left_handed_widget")
    assert delta_for_abstention(resolution) is ControlDelta.WEAKEN

    ruling = setpoint_delta(
        registry,
        "torque_of_the_left_handed_widget",
        ancestor=quantity("400", "kPa"),
        descendant=quantity("600", "kPa"),
    )
    assert ruling.delta is ControlDelta.WEAKEN
    assert ruling.direction is SafeDirection.ABSTAIN
    assert ruling.abstained
    assert ruling.delta is not ControlDelta.RESTATE


def test_delta_for_abstention_refuses_a_resolution_that_did_not_abstain() -> None:
    """A caller reaching for the abstention path with an answer in hand has a bug.

    Returning ``weaken`` anyway would hide it behind a verdict that looks
    conservative, which is exactly how a fail-closed default becomes a mask.
    """
    registry = _registry()
    answered = registry.resolve("max_operating_pressure")
    assert not answered.abstained
    with pytest.raises(ValueError):
        delta_for_abstention(answered)


def test_a_proposed_entry_is_not_ratified_and_therefore_abstains() -> None:
    """The clause exists, is well-formed, names a direction — and does not answer."""
    registry = _registry(status=EntryStatus.PROPOSED)
    assert registry.entries == {}
    resolution = registry.resolve("max_operating_pressure")
    assert resolution.direction is SafeDirection.ABSTAIN
    assert resolution.reason is AbstentionReason.NOT_RATIFIED
    # The entry is still carried, so the refusal can say what to do about it.
    assert resolution.entry is not None
    assert resolution.entry.direction is SafeDirection.LOWER_IS_SAFER

    ruling = setpoint_delta(
        registry,
        "max_operating_pressure",
        ancestor=quantity("400", "kPa"),
        descendant=quantity("300", "kPa"),  # a TIGHTENING
    )
    assert ruling.delta is ControlDelta.WEAKEN, (
        "an unratified parameter blocks even on an edit that tightens it; the system "
        "does not know which way is safer, so it does not get to call this an "
        "improvement"
    )


def test_a_ratified_entry_on_an_unsigned_commit_abstains() -> None:
    """Status and signature are two conditions and they fail independently.

    A clause saying RATIFIED on a commit nobody signed is a direction that
    asserts a decision without producing the person who made it.  The clause is
    written by whoever edited the document; the signature is not.
    """
    registry = _registry(status=EntryStatus.RATIFIED, signed=False)
    assert registry.entries == {}
    resolution = registry.resolve("max_operating_pressure")
    assert resolution.reason is AbstentionReason.UNSIGNED_RATIFICATION
    assert delta_for_abstention(resolution) is ControlDelta.WEAKEN


def test_a_withdrawn_entry_abstains_and_says_so() -> None:
    registry = _registry(status=EntryStatus.WITHDRAWN)
    resolution = registry.resolve("min_ppe_level")
    assert resolution.reason is AbstentionReason.WITHDRAWN


def test_a_ratified_signed_entry_answers() -> None:
    """The green half.  Without it the file only proves the system says no to everything."""
    registry = _registry()
    assert len(registry.entries) == len(load_seed())
    assert registry.safe_direction("max_operating_pressure") is SafeDirection.LOWER_IS_SAFER
    assert registry.safe_direction("min_ppe_level") is SafeDirection.HIGHER_IS_SAFER
    assert (
        registry.safe_direction("bolt_torque_specification")
        is SafeDirection.TIGHTER_TOLERANCE_IS_SAFER
    )


def test_every_abstention_reason_resolves_to_weaken() -> None:
    """No reason is a soft one.  Enumerated so a new reason cannot be added quietly.

    Adding an ``AbstentionReason`` without deciding what it resolves to is how a
    fail-closed system acquires a fail-open branch, so the enum is walked here
    and every member is required to be reachable through
    :func:`delta_for_abstention`.
    """
    from mainline_domain.registry.model import Resolution

    for reason in AbstentionReason:
        resolution = Resolution(
            parameter="whatever",
            direction=SafeDirection.ABSTAIN,
            reason=reason,
            entry=None,
            detail=f"synthetic {reason.value}",
        )
        assert delta_for_abstention(resolution) is ControlDelta.WEAKEN


def test_a_resolution_cannot_claim_a_direction_and_a_reason_at_once() -> None:
    """The invariant that keeps 'abstained' from drifting away from 'has a reason'."""
    from mainline_domain.registry.model import Resolution

    with pytest.raises(ValueError):
        Resolution(
            parameter="p",
            direction=SafeDirection.LOWER_IS_SAFER,
            reason=AbstentionReason.NOT_IN_REGISTRY,
            entry=None,
            detail="",
        )
    with pytest.raises(ValueError):
        Resolution(
            parameter="p",
            direction=SafeDirection.ABSTAIN,
            reason=None,
            entry=None,
            detail="",
        )
