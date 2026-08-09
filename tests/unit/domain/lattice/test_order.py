# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The join W6 composes with, over all twenty-five ordered label pairs.

The equation that matters is::

    force(join(a, b)) == max(force(a), force(b))

That is what the ABSTENTION RATCHET (worker W5) and ORIGINDIFF (worker W6) both
rest on: composing verdicts can raise the force the gate reacts with and can
never lower it.  Five labels means twenty-five ordered pairs; there is no reason
to sample them.
"""

from __future__ import annotations

import itertools

import pytest
from mainline_domain.contracts import ControlDelta, force
from mainline_domain.lattice import CHAIN, NEUTRAL, dual, is_weakening, join, rank

_ALL = tuple(ControlDelta)
_PAIRS = tuple(itertools.product(_ALL, repeat=2))


def test_the_chain_is_a_permutation_of_the_sql_enum() -> None:
    """A label that exists in ``mainline.control_delta`` and not in the chain would
    be unrankable, and :func:`join` would raise on it at the worst moment."""
    assert set(CHAIN) == set(_ALL)
    assert len(CHAIN) == len(_ALL)


def test_force_is_monotone_along_the_chain() -> None:
    forces = [force(delta) for delta in CHAIN]
    assert forces == sorted(forces), dict(zip([d.value for d in CHAIN], forces, strict=True))
    assert forces == [0, 0, 0, 2, 3]


@pytest.mark.parametrize(("a", "b"), _PAIRS)
def test_the_join_never_lowers_force(a: ControlDelta, b: ControlDelta) -> None:
    assert force(join((a, b))) == max(force(a), force(b))


@pytest.mark.parametrize(("a", "b"), _PAIRS)
def test_the_join_is_commutative_and_idempotent(a: ControlDelta, b: ControlDelta) -> None:
    assert join((a, b)) is join((b, a))
    assert join((a, a)) is a


@pytest.mark.parametrize(("a", "b", "c"), tuple(itertools.product(_ALL, repeat=3))[:60])
def test_the_join_is_associative(a: ControlDelta, b: ControlDelta, c: ControlDelta) -> None:
    assert join((join((a, b)), c)) is join((a, join((b, c))))


def test_introduce_is_the_identity_of_the_join_and_restate_is_the_empty_verdict() -> None:
    """Two different questions that are easy to conflate.

    ``introduce`` is the bottom of the chain because every other label
    presupposes the control existed at the baseline, so any of them defeats it.
    ``NEUTRAL`` — the verdict of an edit that produced *no findings at all* — is
    ``restate``, because calling that ``introduce`` would assert something about
    the baseline that no rule established.
    """
    for delta in _ALL:
        assert join((ControlDelta.INTRODUCE, delta)) is delta
    assert CHAIN[0] is ControlDelta.INTRODUCE
    assert NEUTRAL is ControlDelta.RESTATE
    assert join(()) is ControlDelta.RESTATE


def test_rank_is_a_strict_total_order() -> None:
    ranks = [rank(delta) for delta in CHAIN]
    assert ranks == list(range(len(CHAIN)))


@pytest.mark.parametrize("delta", _ALL)
def test_dual_is_an_involution(delta: ControlDelta) -> None:
    assert dual(dual(delta)) is delta


def test_dual_does_not_preserve_force_and_that_asymmetry_is_the_product() -> None:
    """Adding a control is safe; deleting one is not.  If ``dual`` preserved force
    the lattice would be symmetric, and a symmetric lattice cannot express a
    ratchet."""
    assert dual(ControlDelta.REMOVE) is ControlDelta.INTRODUCE
    assert force(ControlDelta.REMOVE) == 3
    assert force(ControlDelta.INTRODUCE) == 0
    assert dual(ControlDelta.WEAKEN) is ControlDelta.STRENGTHEN
    assert force(ControlDelta.WEAKEN) == 2
    assert force(ControlDelta.STRENGTHEN) == 0


@pytest.mark.parametrize("delta", _ALL)
def test_is_weakening_is_exactly_the_two_labels_the_gate_reacts_to(delta: ControlDelta) -> None:
    assert is_weakening(delta) == (delta in (ControlDelta.WEAKEN, ControlDelta.REMOVE))


def test_the_origindiff_composition_worker_w6_needs_is_this_join() -> None:
    """Decision D7 in one line: the delta of record is the more forceful of the
    parent delta and the blame-origin delta."""
    parent = ControlDelta.RESTATE
    origin = ControlDelta.WEAKEN
    assert join((parent, origin)) is ControlDelta.WEAKEN
    # Twenty individually-neutral commits whose composition weakens.
    assert join([ControlDelta.RESTATE] * 20 + [ControlDelta.WEAKEN]) is ControlDelta.WEAKEN
