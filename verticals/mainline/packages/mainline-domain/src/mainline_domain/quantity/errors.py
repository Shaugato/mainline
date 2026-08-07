# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Every way the quantity algebra refuses to answer.

There is no ``None`` return and no default anywhere in this package.  A unit it
does not know, a frame it cannot cross, a dimension that does not line up — all
of them raise, and the caller (the DIRECTRIX resolver, then the lattice) turns
the raise into an abstention, which decision D6 turns into ``weaken``.

The chain matters more than any single exception in it: **a question the unit
algebra cannot answer must end in a merge refusal, never in a number.**  That is
only true if this module never invents one.
"""

from __future__ import annotations

__all__ = [
    "AmbiguousUnitError",
    "DimensionMismatchError",
    "GaugeReferenceError",
    "QuantityError",
    "ReferenceMismatchError",
    "UnitParseError",
    "UnknownUnitError",
    "ValueParseError",
]


class QuantityError(Exception):
    """Base for everything this package refuses."""


class UnitParseError(QuantityError):
    """A unit token could not be turned into exactly one registry unit."""


class UnknownUnitError(UnitParseError):
    """The token is not in the committed vocabulary.

    Deliberately not a fallback to "dimensionless".  An unrecognised unit on a
    setpoint means the comparison the lattice is about to make is undefined, and
    an undefined comparison must reach the gate as an abstention.
    """


class AmbiguousUnitError(UnitParseError):
    """The token names more than one unit and the text does not disambiguate.

    ``C`` is the case that matters: Pint reads it as coulomb, a process
    engineer writes it for Celsius, and a temperature interlock that silently
    became an electric charge compares against nothing.  ``degC`` is accepted;
    a bare ``C`` is refused.
    """


class ValueParseError(QuantityError):
    """A numeric literal could not be read exactly.

    Exactly, meaning as a :class:`~decimal.Decimal` from the printed digits.
    Nothing in this package parses a stored magnitude through ``float``: binary
    floating point cannot represent ``0.1``, and a setpoint comparison that
    turns on the fifteenth decimal place of a value nobody wrote is a coin toss
    dressed as arithmetic.
    """


class DimensionMismatchError(QuantityError):
    """Two quantities do not share a dimensionality.

    Includes the deliberately separated scales: ``%LEL``, ``%vol``, a bare
    ``%``, a count and an ordinal rating each carry their own base dimension in
    the vendored definitions, so ``19.5 %vol`` and ``19.5 %LEL`` mismatch here
    rather than comparing equal.
    """


class ReferenceMismatchError(QuantityError):
    """Two quantities are in different reference frames.

    The frames are ``absolute`` / ``gauge`` / ``delta`` / ``none``, and they do
    not interconvert.  ``none`` is *unstated*, not *absolute*: a clause that
    wrote a bare ``kPa`` did not say which frame it meant, and this package
    refuses to decide that on the author's behalf.
    """


class GaugeReferenceError(ReferenceMismatchError):
    """A gauge↔absolute (or gauge↔unstated) **pressure** crossing (decision D5).

    ``50 psig`` is ``344.7 kPa_g``.  It is **not** ``446 kPa`` absolute, except
    at exactly one standard atmosphere of ambient pressure, which is not a
    condition any procedure guarantees and is not the condition the instrument
    is reading in.

    The failure this prevents is not a rounding error, it is a sign flip.  Take
    a clause whose ancestor reads *"shall not exceed 400 kPa"* and whose
    descendant reads *"shall not exceed 50 psig"*.  Convert the gauge reading to
    absolute and you get 446 kPa: the limit appears to have been **raised**, and
    the lattice reports ``weaken`` on an edit that in fact tightened the ceiling
    to 344.7 kPa_g.  Convert in the other direction on a different pair and the
    same arithmetic hides a real weakening behind an apparent tightening.  Both
    directions are wrong and neither is detectable downstream, which is why the
    conversion raises instead of being flagged.
    """
