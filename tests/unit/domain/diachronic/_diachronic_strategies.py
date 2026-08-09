# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Hypothesis strategies over legal CAT triples.  Asserts nothing itself.

Deliberately **not** an import of ``tests/unit/domain/lattice/_lattice_strategies``.
Those pools are tuned for the interaction between the nine rules; these are tuned
for the interaction between two *baselines*, which needs three tuples at a time
and needs the origin and the parent to differ from each other often enough that
the join has something to do.  Sharing the module would couple two suites'
shrinking behaviour for no benefit, and the two files' own docstrings warn that
pytest's prepend import mode makes a shared name a hazard in the first place.

Small, adversarial pools rather than large uniform ones, for the same reason the
lattice suite gives: what these properties are exposed to is the interaction
between a parent verdict and an origin verdict, and interactions are reached by
drawing repeatedly from a handful of values.
"""

from __future__ import annotations

from _diachronic_fixtures import PRESSURE_PARAMETER, anchors, cat, qty
from hypothesis import strategies as st
from mainline_domain.cat.schema import COVERAGE_QUANTIFIERS, DEONTIC_LABELS
from mainline_domain.contracts import CAT, AnchorClass, AnchorSet

__all__ = ["anchor_sets", "cats"]

_PARAMETERS: tuple[str, ...] = ("", PRESSURE_PARAMETER, "vent_line_backpressure")
_COMPARATORS: tuple[str, ...] = ("", "<=", "<", ">=", "=", "~")
_VALUES: tuple[tuple[str, str] | None, ...] = (None, ("10", "kPa"), ("50", "kPa"), ("50", "psig"))
_EXCEPTIONS: tuple[str, ...] = ("where practicable", "unless the vessel is inerted")
_VERIFICATION: tuple[str, ...] = ("hold_point", "second_signature")
_FREQUENCIES: tuple[tuple[str, str] | None, ...] = (None, ("7", "day"), ("30", "day"))

_ANCHORS: tuple[tuple[AnchorClass, str], ...] = (
    (AnchorClass.EQUIPMENT_TAG, "P-101A"),
    (AnchorClass.ISOLATION_POINT_ID, "ISO-44"),
)


def _sublists(pool: tuple[str, ...]) -> st.SearchStrategy[tuple[str, ...]]:
    return st.lists(st.sampled_from(pool), unique=True, max_size=len(pool)).map(tuple)


@st.composite
def cats(draw: st.DrawFn) -> CAT:
    """Draw a legal CAT from the adversarial pools above."""
    comparator = draw(st.sampled_from(_COMPARATORS))
    raw_value = draw(st.sampled_from(_VALUES))
    value = None if comparator == "" or raw_value is None else qty(*raw_value)
    raw_frequency = draw(st.sampled_from(_FREQUENCIES))
    return cat(
        actor="the authorised person",
        deontic=draw(st.sampled_from(DEONTIC_LABELS)),
        action="operate",
        object_class="pressure vessel",
        hazard_energy="pressure",
        parameter=draw(st.sampled_from(_PARAMETERS)),
        comparator=comparator,
        value=value,
        exceptions=draw(_sublists(_EXCEPTIONS)),
        verification=draw(_sublists(_VERIFICATION)),
        frequency=None if raw_frequency is None else qty(*raw_frequency),
        coverage_quantifier=draw(st.sampled_from(tuple(sorted(COVERAGE_QUANTIFIERS)))),
    )


@st.composite
def anchor_sets(draw: st.DrawFn) -> AnchorSet:
    """Draw a subset of the two identity anchors the pools carry."""
    chosen = draw(st.lists(st.sampled_from(_ANCHORS), unique=True, max_size=len(_ANCHORS)))
    return anchors(*chosen)
