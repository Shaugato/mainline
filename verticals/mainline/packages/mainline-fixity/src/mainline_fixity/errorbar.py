# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The compression corridor, and why *"no excursion found"* is not *"no excursion occurred"*.

A PI historian applies **exception reporting** at the collector and **swinging-door
compression** at the archive. What lands in the archive is therefore a *vertex of a
compression corridor*, not a measurement: the true signal is guaranteed only to have
stayed within ``ExcDev + CompDev`` of the line between two stored vertices. An
excursion narrower than that corridor can be entirely legitimate and entirely
invisible, and no amount of querying will surface it.

Two consequences, and both are load-bearing.

**A difference inside the corridor is not a finding of compliance.** It is a
finding that the archive cannot settle the question. :class:`Reading` calls that
``INDISTINGUISHABLE`` and carries a :class:`BoundedNegative` — the arithmetic that
bounds what was *not* seen. §5.8: recorded as a bounded negative with its
arithmetic, **never** as "no excursion occurred".

**The corridor composes in series, so it sums.** ExcDev is applied when the value
leaves the collector and CompDev when it enters the archive; the second operates on
the output of the first. Root-sum-squaring them would treat them as independent
measurement errors, produce a narrower corridor, and make every finding more
confident than the data supports. We sum. Being wrong in the conservative direction
is the only kind of wrong this component is allowed to be.

Nothing here converts between reference frames. ``50 psig`` is ``344.7 kPa_g`` and is
**not** ``446 kPa(a)``; :func:`mainline_domain.quantity.algebra.convert` raises on a
crossing and this module lets it.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING

from mainline_domain.cat.preimage import canonical_decimal
from mainline_domain.quantity.algebra import convert
from mainline_domain.registry.model import SafeDirection

if TYPE_CHECKING:
    from mainline_domain.contracts import Quantity

    from .types import ErrorBar

__all__ = [
    "BoundedNegative",
    "CorridorVerdict",
    "Reading",
    "read_against_corridor",
]


class CorridorVerdict(StrEnum):
    """What an archived value can and cannot establish about a documented setpoint."""

    #: The observed value is outside the corridor **in the unsafe direction**.
    EXCEEDS = "exceeds"
    #: The observed value is outside the corridor in the safe direction.
    WITHIN_SAFE = "within_safe"
    #: The difference is smaller than the corridor. The archive cannot settle it.
    INDISTINGUISHABLE = "indistinguishable"
    #: The registry declines to say which way is dangerous for this parameter.
    #: The caller applies ``abstain ⇒ weaken``; this module does not decide it.
    DIRECTION_UNKNOWN = "direction_unknown"
    #: The control is a *band*, and one archived vertex cannot show a band's width.
    BAND_NOT_OBSERVABLE = "band_not_observable"


@dataclass(frozen=True, slots=True)
class BoundedNegative:
    """The arithmetic behind *"we looked and could not tell"*.

    Every field is here so that the sentence :meth:`statement` produces can be
    re-derived by a stranger from the row alone. A bounded negative with no
    arithmetic is just a claim, and a claim is what this record exists to avoid
    making.
    """

    parameter: str
    unit: str
    documented: Decimal
    observed: Decimal
    difference: Decimal
    corridor: Decimal

    def statement(self) -> str:
        """Render the sentence that goes in front of a reviewer, with its bound."""
        return (
            f"no excursion in {self.parameter} was distinguishable from archival "
            f"compression: |observed - documented| = {canonical_decimal(abs(self.difference))} "
            f"{self.unit}, corridor = {canonical_decimal(self.corridor)} {self.unit} "
            f"(ExcDev + CompDev). An excursion narrower than the corridor is not "
            f"observable in this archive. This is a bounded negative: it does not say "
            f"that no excursion occurred."
        )

    def to_json(self) -> dict[str, str]:
        """Render the arithmetic for a JSONB detail column, float-free."""
        return {
            "parameter": self.parameter,
            "unit": self.unit,
            "documented": canonical_decimal(self.documented),
            "observed": canonical_decimal(self.observed),
            "difference": canonical_decimal(self.difference),
            "corridor": canonical_decimal(self.corridor),
            "claim": "bounded_negative",
        }


@dataclass(frozen=True, slots=True)
class Reading:
    """One documented setpoint read against one archived value and its corridor."""

    verdict: CorridorVerdict
    difference: Decimal
    corridor: Decimal
    unit: str
    bounded_negative: BoundedNegative | None

    @property
    def settles(self) -> bool:
        """True when the archive can settle the question at all.

        ``INDISTINGUISHABLE``, ``DIRECTION_UNKNOWN`` and ``BAND_NOT_OBSERVABLE``
        all mean *the data does not answer*, and each becomes an
        ``undetermined`` finding rather than a silent pass — for three different
        reasons, which is why they are three values and not one.
        """
        return self.verdict in (CorridorVerdict.EXCEEDS, CorridorVerdict.WITHIN_SAFE)


def read_against_corridor(
    documented: Quantity,
    observed: Quantity,
    direction: SafeDirection,
    *,
    parameter: str,
    err_bar: ErrorBar | None = None,
) -> Reading:
    """Read an archived value against a documented setpoint, honestly.

    Both quantities are brought into the documented value's unit, which raises
    rather than converting across a reference frame. The corridor must be
    expressed in a unit of the same dimension and frame; a corridor in another
    frame is refused for exactly the same reason a setpoint in another frame is.

    ``err_bar`` of ``None`` means a corridor of zero, which is correct for a
    discrete assertion by a person (an inspection record, an isolation register).
    :class:`~mainline_fixity.errors.MissingErrorBar` is raised by
    :mod:`mainline_fixity.compare` for the source kinds where a zero corridor
    would be a fabrication, not here — this function has no way to know where the
    number came from and does not pretend to.

    Returns:
        A :class:`Reading` whose ``verdict`` says what the archive can establish,
        carrying a :class:`BoundedNegative` when the answer is that it cannot.
    """
    aligned = convert(observed, documented.unit)
    difference = aligned.value - documented.value

    corridor = Decimal(0)
    if err_bar is not None:
        corridor_quantity = convert(
            _corridor_quantity(err_bar.corridor(), err_bar.unit, documented),
            documented.unit,
        )
        corridor = corridor_quantity.value

    if direction is SafeDirection.TIGHTER_TOLERANCE_IS_SAFER:
        # The value is a target and the *band* is the control. One archived
        # vertex says nothing about the band's width, and treating a re-centring
        # as a weakening would report every legitimate calibration as drift.
        return Reading(
            verdict=CorridorVerdict.BAND_NOT_OBSERVABLE,
            difference=difference,
            corridor=corridor,
            unit=documented.unit,
            bounded_negative=None,
        )

    if abs(difference) <= corridor:
        return Reading(
            verdict=CorridorVerdict.INDISTINGUISHABLE,
            difference=difference,
            corridor=corridor,
            unit=documented.unit,
            bounded_negative=BoundedNegative(
                parameter=parameter,
                unit=documented.unit,
                documented=documented.value,
                observed=aligned.value,
                difference=difference,
                corridor=corridor,
            ),
        )

    if direction is SafeDirection.ABSTAIN:
        return Reading(
            verdict=CorridorVerdict.DIRECTION_UNKNOWN,
            difference=difference,
            corridor=corridor,
            unit=documented.unit,
            bounded_negative=None,
        )

    unsafe = (direction is SafeDirection.LOWER_IS_SAFER and difference > 0) or (
        direction is SafeDirection.HIGHER_IS_SAFER and difference < 0
    )
    return Reading(
        verdict=CorridorVerdict.EXCEEDS if unsafe else CorridorVerdict.WITHIN_SAFE,
        difference=difference,
        corridor=corridor,
        unit=documented.unit,
        bounded_negative=None,
    )


def _corridor_quantity(width: Decimal, unit: str, like: Quantity) -> Quantity:
    """Build the corridor as a :class:`Quantity` in its declared unit.

    The corridor inherits the documented quantity's *dimension and frame labels*
    only when its own unit string matches; otherwise it is constructed with its
    own labels and :func:`convert` refuses the crossing. The refusal is the point:
    a corridor quoted in ``psi`` against a setpoint in ``kPa_g`` is a unit error
    somebody has to fix, not a conversion this module should perform silently.
    """
    from mainline_domain.quantity.algebra import quantity as build_quantity

    if unit == like.unit:
        return type(like)(
            value=width,
            unit=like.unit,
            dimension=like.dimension,
            reference=like.reference,
        )
    return build_quantity(width, unit)
