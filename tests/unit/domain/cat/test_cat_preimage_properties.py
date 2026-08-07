# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Properties of the ``cat_key`` encoding that the golden vectors cannot pin.

Fifteen vectors prove fifteen points.  What has to hold is a statement about
*every* CAT: the encoding is injective modulo ``Decimal`` value-equality.  Two
CATs that compare equal produce the same key; two that differ produce different
ones.  That is the whole contract of identity axis 2 — a blame edge attaches
through ``cat_key`` equality, so a collision moves blame onto the wrong clause
and a spurious difference detaches it from the right one.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Final

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from mainline_domain.cat import CAT_FIELD_ORDER, canonical_decimal, cat_key, cat_preimage
from mainline_domain.cat.preimage import TYPE_ABSENT, TYPE_LIST, TYPE_QUANTITY, TYPE_TEXT
from mainline_domain.contracts import CAT, Quantity

# Small alphabets on purpose: collisions are found by making fields *similar*,
# not by making them long.  'ab'/'c' vs 'a'/'bc' is the failure mode, and it
# only appears when the generator reuses a handful of tokens.
_TOKENS: Final[tuple[str, ...]] = ("", "a", "b", "c", "ab", "bc", "abc", "á", "中文", " ")
_UNITS: Final[tuple[str, ...]] = ("kPa", "psig", "%", "month", "m/s")
_DIMENSIONS: Final[tuple[str, ...]] = ("pressure", "dimensionless", "time")
_REFERENCES: Final[tuple[str, ...]] = ("absolute", "gauge", "delta", "none")

_text = st.sampled_from(_TOKENS)
_list = st.lists(st.sampled_from(_TOKENS), max_size=3).map(tuple)
_decimal = st.sampled_from(
    [Decimal(raw) for raw in ("0", "1", "-1", "0.5", "50", "50.0", "1750", "19.5", "-0.0", "1E-3")]
)
_quantity = st.one_of(
    st.none(),
    st.builds(
        Quantity,
        value=_decimal,
        unit=st.sampled_from(_UNITS),
        dimension=st.sampled_from(_DIMENSIONS),
        reference=st.sampled_from(_REFERENCES),
    ),
)

_cats = st.builds(
    CAT,
    actor=_text,
    deontic=_text,
    action=_text,
    object_class=_text,
    hazard_energy=_text,
    parameter=_text,
    comparator=_text,
    value=_quantity,
    conditions=_list,
    exceptions=_list,
    verification=_list,
    frequency=_quantity,
    coverage_quantifier=_text,
)

_SETTINGS = settings(
    max_examples=2000,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)


@given(left=_cats, right=_cats)
@_SETTINGS
def test_injective_modulo_value_equality(left: CAT, right: CAT) -> None:
    """Equal CATs share a key; unequal CATs do not.

    Both halves matter and they fail differently.  A collision (unequal CATs,
    one key) silently merges two obligations, so blame written by one incident
    attaches to a clause it never touched.  A spurious difference (equal CATs,
    two keys) detaches a blame edge from the clause it belongs to and shows up
    as an orphaned blood-written obligation — louder, but still wrong.
    """
    if left == right:
        assert cat_key(left) == cat_key(right)
    else:
        assert cat_key(left) != cat_key(right)


@given(cat=_cats)
@_SETTINGS
def test_key_is_a_pure_function_of_the_tuple(cat: CAT) -> None:
    assert cat_key(cat) == cat_key(cat)
    assert cat_preimage(cat) == cat_preimage(cat)


@given(cat=_cats)
@settings(max_examples=400, deadline=None)
def test_key_shape(cat: CAT) -> None:
    key = cat_key(cat)
    assert key.startswith("cat1:")
    assert len(key) == 69
    assert all(character in "0123456789abcdef" for character in key[5:])


@given(cat=_cats)
@settings(max_examples=400, deadline=None)
def test_preimage_is_self_delimiting(cat: CAT) -> None:
    """Walk the preimage as a decoder would and land exactly on the end.

    If any field mis-declared its length the walk would overrun or stop short.
    This is the structural property the golden vectors only sample.
    """
    raw = cat_preimage(cat)
    assert raw.startswith(b"mainline/cat/v1\x1f")
    cursor = len(b"mainline/cat/v1\x1f")
    for _ in CAT_FIELD_ORDER:
        type_byte = raw[cursor]
        assert type_byte in (TYPE_ABSENT, TYPE_TEXT, TYPE_LIST, TYPE_QUANTITY)
        length = int.from_bytes(raw[cursor + 1 : cursor + 5], "big")
        cursor += 5 + length
        assert cursor <= len(raw)
    assert cursor == len(raw)


def _mutations(cat: CAT) -> list[CAT]:
    """One single-field change per field, each guaranteed to change the value."""
    other_quantity = Quantity(value=Decimal("999"), unit="zzz", dimension="zzz", reference="delta")
    changes: dict[str, Any] = {
        "actor": cat.actor + "x",
        "deontic": cat.deontic + "x",
        "action": cat.action + "x",
        "object_class": cat.object_class + "x",
        "hazard_energy": cat.hazard_energy + "x",
        "parameter": cat.parameter + "x",
        "comparator": cat.comparator + "x",
        "value": None if cat.value is not None else other_quantity,
        "conditions": (*cat.conditions, "zzz"),
        "exceptions": (*cat.exceptions, "zzz"),
        "verification": (*cat.verification, "zzz"),
        "frequency": None if cat.frequency is not None else other_quantity,
        "coverage_quantifier": cat.coverage_quantifier + "x",
    }
    assert set(changes) == set(CAT_FIELD_ORDER)
    out: list[CAT] = []
    for field, new_value in changes.items():
        out.append(CAT(**{**{f: getattr(cat, f) for f in CAT_FIELD_ORDER}, field: new_value}))
    return out


@given(cat=_cats)
@_SETTINGS
def test_any_single_field_change_changes_the_key(cat: CAT) -> None:
    """Every one of the thirteen slots is load-bearing.

    A slot that could change without moving the key would be a slot an editor
    could change without moving identity — which is precisely the dodge the CAT
    exists to close.
    """
    base = cat_key(cat)
    for mutated in _mutations(cat):
        assert mutated != cat
        assert cat_key(mutated) != base


@given(cat=_cats)
@settings(max_examples=500, deadline=None)
def test_list_order_is_significant(cat: CAT) -> None:
    """The encoder does not sort; ordering is the normaliser's job (spec §7.3)."""
    if len(cat.conditions) < 2 or cat.conditions[0] == cat.conditions[-1]:
        return
    reversed_cat = CAT(
        **{
            **{f: getattr(cat, f) for f in CAT_FIELD_ORDER},
            "conditions": tuple(reversed(cat.conditions)),
        }
    )
    assert cat_key(reversed_cat) != cat_key(cat)


# --------------------------------------------------------------------------- #
# Canonical decimals (spec §4)                                                 #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("50", "50"),
        ("50.0", "50"),
        ("50.000", "50"),
        ("5E+1", "50"),
        ("0.500", "0.5"),
        ("-0.0", "0"),
        ("-0", "0"),
        ("0", "0"),
        ("-12.340", "-12.34"),
        ("1E-7", "0.0000001"),
        ("1E+3", "1000"),
        ("0.0", "0"),
    ],
)
def test_canonical_decimal_table(raw: str, expected: str) -> None:
    assert canonical_decimal(Decimal(raw)) == expected


@pytest.mark.parametrize("raw", ["NaN", "sNaN", "Infinity", "-Infinity"])
def test_non_finite_decimal_raises(raw: str) -> None:
    """There is no canonical spelling for a non-finite setpoint, and no safe default."""
    quantity = Quantity(value=Decimal(raw), unit="kPa", dimension="pressure", reference="gauge")
    cat = CAT(
        actor="",
        deontic="MUST",
        action="",
        object_class="",
        hazard_energy="",
        parameter="",
        comparator="<=",
        value=quantity,
        conditions=(),
        exceptions=(),
        verification=(),
        frequency=None,
        coverage_quantifier="all",
    )
    with pytest.raises(ValueError, match="finite"):
        cat_preimage(cat)


def test_decimal_representations_that_compare_equal_share_a_key() -> None:
    """``Decimal('50') == Decimal('50.0')``, so the two CATs are one obligation."""

    def build(raw: str) -> CAT:
        return CAT(
            actor="a",
            deontic="MUST",
            action="b",
            object_class="c",
            hazard_energy="d",
            parameter="e",
            comparator="<=",
            value=Quantity(value=Decimal(raw), unit="kPa", dimension="pressure", reference="gauge"),
            conditions=(),
            exceptions=(),
            verification=(),
            frequency=None,
            coverage_quantifier="all",
        )

    assert build("50") == build("50.0")
    assert cat_key(build("50")) == cat_key(build("50.000")) == cat_key(build("5E+1"))


def test_field_order_matches_the_frozen_contract() -> None:
    """A CAT field added without a decision here must fail loudly, not encode silently."""
    import dataclasses

    assert tuple(f.name for f in dataclasses.fields(CAT)) == CAT_FIELD_ORDER
    assert len(CAT_FIELD_ORDER) == 13


def test_type_bytes_are_the_four_the_spec_declares() -> None:
    assert (TYPE_ABSENT, TYPE_TEXT, TYPE_LIST, TYPE_QUANTITY) == (0x00, 0x01, 0x02, 0x03)
