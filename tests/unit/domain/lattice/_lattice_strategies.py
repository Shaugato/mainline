# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Hypothesis strategies over *legal* CAT pairs.  Asserts nothing itself.

Every tuple these strategies build passes
:func:`~mainline_domain.cat.schema.validate_cat`, so a property proven over them
is a property over inputs the extractor can actually produce.  Generating
illegal tuples would prove the lattice behaves well on documents that cannot
exist, which is not a claim anybody needs.

The pools are small and adversarial rather than large and uniform.  What the
minimality and duality properties are exposed to is the *interaction* between
rules — two rules forcing the same verdict, a rule firing while another abstains,
one rule's silence keeping another's witness minimal — and interactions are
reached by drawing repeatedly from a handful of values, not by drawing once from
thousands.
"""

from __future__ import annotations

from _lattice_fixtures import anchors, cat, qty, registry
from hypothesis import strategies as st
from mainline_domain.cat.schema import COVERAGE_QUANTIFIERS, DEONTIC_LABELS
from mainline_domain.contracts import CAT, AnchorClass, AnchorSet
from mainline_domain.registry.model import SafeDirection, SafeDirectionRegistry

__all__ = ["anchor_sets", "cats", "registries"]

#: One ratified parameter, one unratified.  The unratified one is what drives
#: rule R2 into decision D6's abstention, and the property tests need both paths
#: because the abstention branch is where the duality guarantee is easiest to
#: break.
_PARAMETERS: tuple[str, ...] = ("", "max_operating_pressure", "vent_line_backpressure")

_COMPARATORS: tuple[str, ...] = ("", "<=", "<", ">=", "=", "~", "+/-", "range")

_VALUES = (None, ("10", "kPa"), ("50", "kPa"), ("50", "psig"))

_EXCEPTIONS: tuple[str, ...] = ("where practicable", "unless the vessel is inerted")
_VERIFICATION: tuple[str, ...] = ("hold_point", "second_signature")
_FREQUENCIES = (None, ("7", "day"), ("30", "day"))

_ANCHORS: tuple[tuple[AnchorClass, str], ...] = (
    (AnchorClass.EQUIPMENT_TAG, "P-101A"),
    (AnchorClass.ISOLATION_POINT_ID, "ISO-44"),
)


def _sublists(pool: tuple[str, ...]) -> st.SearchStrategy[tuple[str, ...]]:
    return st.lists(st.sampled_from(pool), unique=True, max_size=len(pool)).map(tuple)


@st.composite
def cats(draw: st.DrawFn) -> CAT:
    """A legal CAT drawn from the adversarial pools above.

    The one constraint that has to be enforced rather than sampled is the
    schema's: a value with no comparator asserts no relation and is refused by
    ``validate_cat``.  Sampling around it rather than filtering keeps the
    strategy from shrinking into a corner.
    """
    comparator = draw(st.sampled_from(_COMPARATORS))
    raw_value = draw(st.sampled_from(_VALUES))
    value = None if comparator == "" or raw_value is None else qty(*raw_value)
    raw_frequency = draw(st.sampled_from(_FREQUENCIES))
    return cat(
        deontic=draw(st.sampled_from(DEONTIC_LABELS)),
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
    """A subset of the two identity anchors the pools carry."""
    chosen = draw(st.lists(st.sampled_from(_ANCHORS), unique_by=lambda a: a, max_size=2))
    return anchors(*chosen)


def registries() -> st.SearchStrategy[SafeDirectionRegistry]:
    """Two registries: one that answers about the pressure parameter, one that does not.

    Both are read at the suite's single ``AS_OF`` commit, because
    :func:`~mainline_domain.lattice.decide.decide` refuses a registry read
    anywhere else and the properties under test are about the lattice, not about
    that guard (which has its own test).
    """
    return st.sampled_from(
        (
            registry(("max_operating_pressure", SafeDirection.LOWER_IS_SAFER, "kPa")),
            registry(),
        )
    )
