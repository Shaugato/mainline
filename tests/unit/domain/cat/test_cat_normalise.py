# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Canonical form (spec §7), and the seam to worker W2's quantity algebra.

The encoder is dumb on purpose, so every claim about ``cat_key`` reproducibility
is really a claim about this module.  The seam tests are the important ones: they
pin the error contract W2 has to honour, and they pin it in the direction that
matters — a gauge↔absolute crossing must **escape**, never be absorbed.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from mainline_domain.cat import UnconvertibleUnitError, cat_key, normalise_cat, normalise_list
from mainline_domain.cat.normalise import normalise_phrase, sort_key
from mainline_domain.cat.quantity_bridge import resolve_converter, si_normalise
from mainline_domain.contracts import CAT, Quantity


def build(**overrides: object) -> CAT:
    base: dict[str, object] = {
        "actor": "supervisor",
        "deontic": "MUST",
        "action": "isolate",
        "object_class": "valve",
        "hazard_energy": "pressure",
        "parameter": "max_operating_pressure",
        "comparator": "<=",
        "value": Quantity(
            value=Decimal("1750"), unit="kPa", dimension="pressure", reference="gauge"
        ),
        "conditions": (),
        "exceptions": (),
        "verification": (),
        "frequency": None,
        "coverage_quantifier": "all",
    }
    base.update(overrides)
    return CAT(**base)  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# §7.1, §7.2 slot and phrase normalisation                                     #
# --------------------------------------------------------------------------- #


def test_closed_slots_are_folded_and_deontic_is_not() -> None:
    cat = normalise_cat(build(actor="  The   SUPERVISOR ", deontic="must"))
    assert cat.actor == "the supervisor"
    assert cat.deontic == "MUST", "R1's ladder is written in upper case"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("  Where   Practicable.  ", "where practicable"),
        ("the space is purged;", "the space is purged"),
        ("a trailing comma,", "a trailing comma"),
        ("a double stop..", "a double stop"),
        # Stripping these would empty them, so they are left alone and survive
        # into the tuple rather than being silently deleted.
        ("...", "..."),
        (" ; ", ";"),
        ("", ""),
    ],
)
def test_normalise_phrase(raw: str, expected: str) -> None:
    assert normalise_phrase(raw) == expected


@pytest.mark.parametrize("raw", ["a..", "...", "the space is purged;;", "", " ,, "])
def test_normalise_phrase_is_idempotent(raw: str) -> None:
    """A non-idempotent normaliser gives one CAT two canonical forms — and two keys."""
    once = normalise_phrase(raw)
    assert normalise_phrase(once) == once


def test_list_is_deduplicated_emptied_and_byte_ordered() -> None:
    result = normalise_list(["  B ", "a", "", "A", "b.", "á"])
    assert result == ("a", "b", "á")
    assert list(result) == sorted(result, key=sort_key)


def test_ordering_is_by_utf8_bytes_not_by_locale() -> None:
    """Identity may not depend on the machine's collation settings."""
    elements = ["zebra", "álvaro", "apple"]
    result = normalise_list(elements)
    assert result == tuple(sorted({normalise_phrase(e) for e in elements}, key=sort_key))
    assert result[-1] == "álvaro", "U+00E1 encodes to 0xC3 0xA1, above every ASCII letter"


def test_duplicate_exception_is_one_exception() -> None:
    """A clause that hedges twice has not added a hedge; R4 must not see growth."""
    cat = normalise_cat(
        build(exceptions=("where practicable", "Where practicable.", "where practicable"))
    )
    assert cat.exceptions == ("where practicable",)


def test_list_order_in_the_input_does_not_change_the_key() -> None:
    forward = normalise_cat(build(verification=("second signature", "hold point")))
    backward = normalise_cat(build(verification=("hold point", "second signature")))
    assert forward == backward
    assert cat_key(forward) == cat_key(backward)


_slot = st.text(alphabet="abAB á.;, ", max_size=12)
_list_strategy = st.lists(_slot, max_size=4).map(tuple)


@given(
    actor=_slot,
    deontic=_slot,
    conditions=_list_strategy,
    exceptions=_list_strategy,
    verification=_list_strategy,
)
@settings(max_examples=600, deadline=None)
def test_normalisation_is_idempotent(
    actor: str,
    deontic: str,
    conditions: tuple[str, ...],
    exceptions: tuple[str, ...],
    verification: tuple[str, ...],
) -> None:
    """``normalise(normalise(x)) == normalise(x)``, and therefore one key per CAT.

    Each step is idempotent on its own; the composition is what the encoder
    depends on, and the composition is what is tested.
    """
    once = normalise_cat(
        build(
            actor=actor,
            deontic=deontic,
            conditions=conditions,
            exceptions=exceptions,
            verification=verification,
        )
    )
    assert normalise_cat(once) == once
    assert cat_key(normalise_cat(once)) == cat_key(once)


# --------------------------------------------------------------------------- #
# §7.4 — the W2 seam                                                           #
# --------------------------------------------------------------------------- #


class _KnowsNothing:
    """A converter that knows no units at all."""

    def to_si(self, quantity: Quantity) -> Quantity:
        raise UnconvertibleUnitError(quantity.unit)


class _CrossesReferences:
    """The bug decision D5 exists to make unrepresentable: gauge read as absolute."""

    def to_si(self, quantity: Quantity) -> Quantity:
        return Quantity(
            value=quantity.value + Decimal("101.325"),
            unit="kPa",
            dimension=quantity.dimension,
            reference="absolute",
        )


class _RefusesToCross(Exception):
    pass


class _RaisesOnCrossing:
    """What W2 must actually do: raise, and not with a ``LookupError``."""

    def to_si(self, quantity: Quantity) -> Quantity:
        if quantity.reference == "gauge":
            raise _RefusesToCross("50 psig is not 446 kPa absolute")
        return Quantity(
            value=quantity.value * 1000,
            unit="Pa",
            dimension=quantity.dimension,
            reference=quantity.reference,
        )


def test_no_converter_leaves_units_exactly_as_written() -> None:
    cat = normalise_cat(build(), converter=None)
    assert cat.value is not None
    assert (cat.value.unit, cat.value.value) == ("kPa", Decimal("1750"))


def test_unknown_unit_is_kept_verbatim_by_default() -> None:
    """Spec §10: ``1 shift`` normalises to itself, and says so rather than guessing."""
    cat = normalise_cat(build(), converter=_KnowsNothing())
    assert cat.value is not None
    assert cat.value.unit == "kPa"


def test_unknown_unit_can_be_made_fatal() -> None:
    quantity = Quantity(value=Decimal("1"), unit="shift", dimension="time", reference="none")
    with pytest.raises(UnconvertibleUnitError):
        si_normalise(quantity, _KnowsNothing(), keep_unconvertible=False)


def test_a_converter_that_crosses_references_is_caught() -> None:
    """If W2 ever silently returned an absolute reading for a gauge one, this fires.

    ``50 psig -> 446 kPa(a)`` flips a ``safe_direction`` comparison, so a
    weakening reads as a strengthening on the way past the gate.  The check is
    here, on our side of the seam, because a guarantee that lives only in
    another package is a guarantee we cannot testify to.
    """
    with pytest.raises(ValueError, match="reference class"):
        normalise_cat(build(), converter=_CrossesReferences())


def test_a_reference_crossing_error_propagates_and_is_never_absorbed() -> None:
    """Only ``LookupError`` is absorbed.  A refusal to cross must escape."""
    with pytest.raises(_RefusesToCross):
        normalise_cat(build(), converter=_RaisesOnCrossing())


def test_converter_preserving_reference_is_applied() -> None:
    cat = normalise_cat(
        build(
            value=Quantity(value=Decimal("2"), unit="kPa", dimension="pressure", reference="none")
        ),
        converter=_RaisesOnCrossing(),
    )
    assert cat.value is not None
    assert (cat.value.value, cat.value.unit, cat.value.reference) == (Decimal("2000"), "Pa", "none")


def test_resolve_converter_rejects_a_non_converter() -> None:
    with pytest.raises(TypeError, match="to_si"):
        resolve_converter(object())  # type: ignore[arg-type]


def test_auto_resolves_to_none_until_w2_lands() -> None:
    """``'auto'`` is environment-dependent and is documented as unsafe for storage.

    Whether the conversion ran would otherwise depend on which distributions
    happened to be installed, and identity may not depend on that.
    """
    resolved = resolve_converter("auto")
    assert resolved is None or hasattr(resolved, "to_si")
