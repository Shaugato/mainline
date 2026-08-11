# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Gauge-safe quantity algebra — worker W2, decision D5.

Public surface::

    from mainline_domain.quantity import quantity, compare, convert, to_si

    p = quantity("50", "psig")  # Quantity(50, 'psi_gauge', …, 'gauge')
    convert(p, "bar_g")  # 3.4473786… bar_gauge
    convert(p, "kPa")  # raises GaugeReferenceError

One claim, and it is a refusal: **this package will not tell you how a gauge
reading compares to an absolute one.**  Pint will — ``50 psig`` becomes
``446.06 kPa`` with no complaint, because the two are dimensionally identical
and Pint has no notion of a reference frame.  That number is right only at one
standard atmosphere of ambient pressure, and the direction of the error is not
constant, so a setpoint comparison built on it can report a weakening as a
tightening.  Rule R2 of the delta lattice is exactly such a comparison, and it
decides whether a merge is refused.

The refusal is worth more than a warning would be because of what happens
downstream: an exception here becomes an abstention in the DIRECTRIX resolver,
and decision D6 resolves an abstention to ``weaken``.  So the failure mode of
this package is a permit that will not merge until somebody writes the frame
down — which is a nuisance, and is the correct nuisance.
"""

from __future__ import annotations

from .algebra import as_decimal, compare, convert, quantity, same_frame, to_si
from .errors import (
    AmbiguousUnitError,
    DimensionMismatchError,
    GaugeReferenceError,
    QuantityError,
    ReferenceMismatchError,
    UnitParseError,
    UnknownUnitError,
    ValueParseError,
)
from .parse import Comparator, Measurement, parse_measurements, parse_one
from .units import (
    ABSOLUTE_PRESSURE_UNITS,
    AMBIGUOUS_TOKENS,
    DIMENSION_LABELS,
    GAUGE_PRESSURE_UNITS,
    UNIT_TOKENS,
    canonical_unit,
    dimension_of,
    dimensionality_for_label,
    reference_of,
    resolve_token,
    unit_registry,
)
from .version import PARSE_VERSION, UNITS_VERSION

__all__ = [
    "ABSOLUTE_PRESSURE_UNITS",
    "AMBIGUOUS_TOKENS",
    "DIMENSION_LABELS",
    "GAUGE_PRESSURE_UNITS",
    "PARSE_VERSION",
    "UNITS_VERSION",
    "UNIT_TOKENS",
    "AmbiguousUnitError",
    "Comparator",
    "DimensionMismatchError",
    "GaugeReferenceError",
    "Measurement",
    "QuantityError",
    "ReferenceMismatchError",
    "UnitParseError",
    "UnknownUnitError",
    "ValueParseError",
    "as_decimal",
    "canonical_unit",
    "compare",
    "convert",
    "dimension_of",
    "dimensionality_for_label",
    "parse_measurements",
    "parse_one",
    "quantity",
    "reference_of",
    "resolve_token",
    "same_frame",
    "to_si",
    "unit_registry",
]
