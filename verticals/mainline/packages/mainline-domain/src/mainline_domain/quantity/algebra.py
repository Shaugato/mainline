# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Construction, conversion and comparison of :class:`~mainline_domain.contracts.Quantity`.

The whole package exists to make exactly one operation trustworthy:
:func:`compare`, which returns ``-1``/``0``/``+1`` for *"the descendant's value
is below / equal to / above the ancestor's"*.  Rule R2 of the delta lattice
multiplies that sign by the ``safe_direction`` of the parameter and gets
``weaken`` or ``strengthen``.  So a wrong sign here is a weakening reported as a
tightening, which is worse than no system at all.

Everything below is arranged around not producing a wrong sign:

* every magnitude is a :class:`~decimal.Decimal`, start to finish;
* a comparison across reference frames raises instead of answering;
* a comparison across dimensionalities raises instead of answering;
* ``to_si`` never routes a gauge reading through absolute pascals.

WHAT THIS MODULE DELIBERATELY DOES NOT DO
-----------------------------------------
No addition, no multiplication, no unit arithmetic of any kind on ``Quantity``.
Not because it would be hard, but because there is no operation in the delta
lattice that needs it, and an arithmetic surface on a gauge quantity is a
loaded weapon: ``50 psig * 2`` is not ``100 psig``-worth of anything, and any
API that lets a caller write it will eventually have a caller who writes it.
Pint's ``autoconvert_offset_to_baseunit`` is off for the same reason.
"""

from __future__ import annotations

from decimal import Decimal, DecimalException, localcontext
from typing import Final

from ..contracts import Quantity, Reference
from .errors import (
    DimensionMismatchError,
    GaugeReferenceError,
    ReferenceMismatchError,
    ValueParseError,
)
from .units import (
    AMBIGUOUS_TOKENS,
    PRESSURE_DIMENSIONALITY,
    UNIT_TOKENS,
    canonical_unit,
    dimension_of,
    label_for_dimensionality,
    reference_of,
    resolve_token,
    unit_registry,
)

__all__ = [
    "COMPARISON_PRECISION",
    "as_decimal",
    "compare",
    "convert",
    "quantity",
    "same_frame",
    "to_si",
]

#: Working precision for conversions.  Generous on purpose: the inputs are
#: printed setpoints with three or four significant figures, and 50 digits of
#: working precision means the conversion contributes nothing to the comparison
#: at any magnitude a procedure will ever contain.  It is *precision*, not
#: tolerance — nothing here rounds a comparison to make two values equal.
COMPARISON_PRECISION: Final[int] = 50

#: The canonical unit each frame normalises to.  Only pressure needs an entry:
#: for every other dimension Pint's own base units are in the same frame as the
#: input, so ``to_base_units`` is safe.  For gauge pressure it is not — Pint's
#: base for a gauge unit is *absolute* pascals, which is precisely the crossing
#: this package refuses — so the target is named explicitly instead.
_FRAME_TARGET: Final[dict[tuple[str, Reference], str]] = {
    (PRESSURE_DIMENSIONALITY, "gauge"): "pascal_gauge",
    (PRESSURE_DIMENSIONALITY, "absolute"): "pascal_absolute",
}


def as_decimal(value: Decimal | int | str) -> Decimal:
    """Coerce a printed magnitude to :class:`Decimal`, refusing ``float``.

    ``float`` is rejected by type, not converted: ``Decimal(0.1)`` is
    ``0.1000000000000000055511151231257827021181583404541015625``, and once that
    is in a Quantity there is no way to tell it from a value somebody meant.
    """
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):  # bool is an int; a boolean setpoint is a bug
        raise ValueParseError("a boolean is not a magnitude")
    if isinstance(value, int):
        return Decimal(value)
    try:
        return Decimal(value.strip().replace(",", ""))
    except (DecimalException, AttributeError) as exc:
        raise ValueParseError(f"{value!r} is not an exact decimal magnitude") from exc


def quantity(value: Decimal | int | str, unit_token: str) -> Quantity:
    """Build a :class:`Quantity` from a printed magnitude and a document token.

    ``quantity('50', 'psig')`` → ``Quantity(Decimal('50'), 'psi_gauge',
    '[mass] / [length] / [time] ** 2', 'gauge')``.

    The reference frame is **derived** from the unit, never supplied by the
    caller.  A caller-supplied frame is a caller-supplied opinion about what a
    document meant, and P2's rule — a value a gate reads is derived from an
    authoritative source, never from the writer — applies to this package as
    much as to a trigger.  The authoritative source here is the committed
    definition file plus :data:`~mainline_domain.quantity.units.GAUGE_PRESSURE_UNITS`.
    """
    canonical = _canonicalise(unit_token)
    return Quantity(
        value=as_decimal(value),
        unit=canonical,
        dimension=dimension_of(canonical),
        reference=reference_of(canonical),
    )


def _canonicalise(unit_token: str) -> str:
    """Accept either a document token (``'psig'``, ``'%LEL'``) or a registry name.

    The token vocabulary is consulted **first**, and that order is the point: it
    is the only place where an ambiguous spelling is refused, so a caller passing
    ``'C'`` must get :class:`AmbiguousUnitError` and not Pint's coulomb.  A name
    that is not a token at all (``'psi_gauge'``, ``'meter ** 3 / hour'``) falls
    through to the registry, which is what the registry loader and the seed use.
    """
    if unit_token in UNIT_TOKENS or unit_token in AMBIGUOUS_TOKENS:
        return resolve_token(unit_token)
    return canonical_unit(unit_token)


def same_frame(left: Quantity, right: Quantity) -> bool:
    """``True`` when the two can be compared at all: same dimensionality, same frame."""
    return left.dimension == right.dimension and left.reference == right.reference


def _refuse_frame(left: Quantity, right: Quantity) -> None:
    """Raise the frame error appropriate to the dimension, with the whole story."""
    detail = (
        f"{left.value} {left.unit} is {left.reference}; "
        f"{right.value} {right.unit} is {right.reference}"
    )
    if left.dimension == PRESSURE_DIMENSIONALITY:
        raise GaugeReferenceError(
            "refusing to relate two pressures in different reference frames: "
            f"{detail}. A gauge reading and an absolute reading differ by the "
            "ambient pressure, which no procedure guarantees; converting one to "
            "the other can invert the direction of a setpoint change. "
            "'none' means the clause did not state a frame, and is not 'absolute'."
        )
    raise ReferenceMismatchError(
        f"refusing to relate quantities in different reference frames: {detail}"
    )


def _refuse_dimension(left: Quantity, right: Quantity) -> None:
    left_label = label_for_dimensionality(left.dimension) or left.dimension
    right_label = label_for_dimensionality(right.dimension) or right.dimension
    raise DimensionMismatchError(
        f"refusing to relate {left.value} {left.unit} ({left_label}) to "
        f"{right.value} {right.unit} ({right_label}): different dimensionality"
    )


def convert(q: Quantity, unit_token: str) -> Quantity:
    """Convert within one reference frame.  Raises on any crossing.

    ``convert(quantity('50', 'psig'), 'bar_g')`` → ``3.4473786…  bar_gauge``.
    ``convert(quantity('50', 'psig'), 'kPa')`` → :class:`GaugeReferenceError`,
    even though Pint would cheerfully return ``446.06 kPa`` (decision D5).
    """
    target = _canonicalise(unit_token)
    target_reference = reference_of(target)
    target_dimension = dimension_of(target)

    if target_dimension != q.dimension:
        _refuse_dimension(q, Quantity(Decimal(0), target, target_dimension, target_reference))
    if target_reference != q.reference:
        _refuse_frame(q, Quantity(Decimal(0), target, target_dimension, target_reference))

    if target == q.unit:
        return q

    registry = unit_registry()
    with localcontext() as context:
        context.prec = COMPARISON_PRECISION
        converted = registry.Quantity(q.value, q.unit).to(target)
        magnitude = as_decimal(converted.magnitude)

    return Quantity(
        value=magnitude,
        unit=target,
        dimension=target_dimension,
        reference=target_reference,
    )


def to_si(q: Quantity) -> Quantity:
    """Normalise to the canonical unit of the quantity's own frame.

    Gauge pressure goes to ``pascal_gauge``, explicit absolute pressure to
    ``pascal_absolute``, and everything else to Pint's base units — which, for
    every non-pressure frame, is a unit in the same frame the input was in
    (Celsius and Kelvin are both absolute; ``delta_degC`` and ``kelvin`` are both
    differences).

    The pressure special-case is the whole point.  ``to_base_units()`` on
    ``50 psig`` returns ``446062.86 pascal`` — the absolute reading — and a
    normaliser that returned that would hand every downstream comparison the
    exact number D5 exists to prevent, with the frame tag stripped off.
    """
    target = _FRAME_TARGET.get((q.dimension, q.reference))
    if target is not None:
        return convert(q, target)

    registry = unit_registry()
    with localcontext() as context:
        context.prec = COMPARISON_PRECISION
        based = registry.Quantity(q.value, q.unit).to_base_units()
        magnitude = as_decimal(based.magnitude)
    unit = str(based.units)

    return Quantity(
        value=magnitude,
        unit=unit,
        dimension=q.dimension,
        reference=q.reference,
    )


def compare(left: Quantity, right: Quantity) -> int:
    """``-1`` if ``left < right``, ``0`` if equal, ``+1`` if ``left > right``.

    Raises :class:`DimensionMismatchError` or :class:`ReferenceMismatchError`
    rather than answering when the two are not comparable.  There is no third
    return value for "cannot tell": a caller that gets an integer back has an
    answer it can act on, and a caller that does not gets an exception it must
    handle.  A sentinel would eventually be compared against zero by somebody.

    Equality is exact decimal equality after conversion, not equality within a
    tolerance.  A tolerance here would be a policy about how much a setpoint may
    move before anyone is told, and that policy belongs in a clause somebody
    signed, not in an arithmetic helper.
    """
    if left.dimension != right.dimension:
        _refuse_dimension(left, right)
    if left.reference != right.reference:
        _refuse_frame(left, right)

    if left.unit == right.unit:
        return _sign(left.value - right.value)

    normalised_right = convert(right, left.unit)
    return _sign(left.value - normalised_right.value)


def _sign(delta: Decimal) -> int:
    if delta < 0:
        return -1
    if delta > 0:
        return 1
    return 0
