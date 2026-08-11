# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The unit registry, the reference-frame table, and the token vocabulary.

Three things live here, and they are separate on purpose:

``unit_registry()``
    A **fresh** :class:`pint.UnitRegistry` loaded from the committed
    ``data/units/mainline_units.txt``, built once per process.  Never
    ``pint.UnitRegistry()`` on its own: the default registry has no gauge units
    at all, so ``psig`` raises there — and, worse, it happily answers questions
    about ``psi`` while doing so, which is how a missing definition file turns
    into a plausible wrong number rather than a crash.

``reference_of()``
    The reference **frame** of a unit — ``absolute`` / ``gauge`` / ``delta`` /
    ``none``.  Pint has no concept of this; it is declared here.  A pressure
    unit that is neither an explicit gauge nor an explicit absolute spelling is
    ``none``, meaning *the author did not say*, which is different from
    *absolute* and is treated as different everywhere.

``resolve_token()``
    Document token → canonical registry unit.  Refuses rather than guesses.

WHY ``none`` COMPARES WITH ``none`` BUT NOTHING ELSE DOES
--------------------------------------------------------
Gauge and absolute pressure differ by an additive constant, and addition of a
constant is **monotone**.  So two readings in the *same* unstated frame order
correctly no matter which frame it was: if a clause said ``300 kPa`` and its
descendant says ``400 kPa``, the limit went up whether both meant gauge or both
meant absolute.  That is why ``none`` ↔ ``none`` is allowed and is sound, and it
is also exactly why ``none`` ↔ ``gauge`` is not: the moment the two sides differ
in frame, the additive constant stops cancelling and the *direction* of the
comparison can flip.  The permitted comparison is not a relaxation of D5; it is
the largest set of comparisons for which D5's failure mode cannot occur.

SCALE-ONLY CONVERSION WITHIN A FRAME
------------------------------------
``kPa → bar`` at ``reference='none'`` is a pure scale change and is allowed for
the same reason.  Every unit tagged ``none`` or ``absolute`` in :data:`UNIT_REFERENCE`
is a scale unit (no Pint offset), so a conversion inside those frames can never
add or remove an atmosphere.  Gauge units *do* carry an offset, and the offsets
cancel exactly when both sides are gauge — which the committed unit tests check
by converting one standard atmosphere to zero in every gauge unit in the file.
"""

from __future__ import annotations

import threading
from collections.abc import Mapping
from decimal import Decimal
from typing import Any, Final

from ..contracts import Reference
from ..data import data_file
from .errors import AmbiguousUnitError, QuantityError, UnknownUnitError
from .version import UNITS_VERSION

#: Pint's ``UnitRegistry`` is generic, and its type parameters have changed shape
#: between minor releases.  Pinning them here would make ``mypy --strict`` pass
#: against exactly one Pint version and fail on the next patch bump, which is a
#: type annotation that costs more than it buys.  The boundary is ``Any`` and the
#: guarantees are enforced by the runtime checks in this module — the version
#: constant read back out of the definition file, and the reference/dimension
#: tables — which are the ones that actually decide anything.
type UnitRegistryT = Any

__all__ = [
    "ABSOLUTE_PRESSURE_UNITS",
    "AMBIGUOUS_TOKENS",
    "DIMENSION_LABELS",
    "GAUGE_PRESSURE_UNITS",
    "PRESSURE_DIMENSIONALITY",
    "UNIT_TOKENS",
    "UnitRegistryT",
    "canonical_unit",
    "dimension_of",
    "dimensionality_for_label",
    "label_for_dimensionality",
    "reference_of",
    "resolve_token",
    "unit_registry",
]


# --------------------------------------------------------------------------- #
# the registry                                                                 #
# --------------------------------------------------------------------------- #

_LOCK: Final[threading.Lock] = threading.Lock()
_REGISTRY: UnitRegistryT | None = None

#: The dimensionless constant declared at the bottom of the definition file.
_VERSION_UNIT: Final[str] = "mainline_units_version"


def _build_registry() -> UnitRegistryT:
    import pint  # imported here so `contracts` stays importable without pint

    registry: UnitRegistryT = pint.UnitRegistry(
        # Every stored magnitude in this system is a Decimal.  A float registry
        # would re-introduce binary rounding on the exact path that decides
        # whether a setpoint moved, and "the limit changed by 1e-16" is not a
        # thing a procedure can mean.
        non_int_type=Decimal,
        # A redefinition is a silent semantic change to a committed artefact.
        # Pint's default is to warn; a warning in a library nobody is watching
        # is a defect that ships.
        on_redefinition="raise",
        # Refuse to auto-convert an offset unit into its base on multiplication.
        # `50 psig * 2` has no meaning — doubling a gauge reading is not
        # doubling a pressure — and pint's convenience mode would silently make
        # it mean something.
        autoconvert_offset_to_baseunit=False,
    )
    registry.load_definitions(str(data_file("units", "mainline_units.txt")))

    declared = registry.Quantity(Decimal(1), _VERSION_UNIT).to("dimensionless").magnitude
    if int(declared) != UNITS_VERSION:
        raise QuantityError(
            f"unit definition file declares version {declared} but "
            f"mainline_domain.quantity.version.UNITS_VERSION is {UNITS_VERSION}; "
            "one of the two was changed without the other"
        )
    return registry


def unit_registry() -> UnitRegistryT:
    """The process-wide registry built from the committed definition file.

    Built once and shared: a Pint registry is expensive and, more importantly,
    quantities from two different registries do not interoperate — a mistake
    that surfaces as a confusing ``ValueError`` deep inside a comparison rather
    than as anything a caller could diagnose.
    """
    global _REGISTRY
    if _REGISTRY is None:
        with _LOCK:
            if _REGISTRY is None:
                _REGISTRY = _build_registry()
    return _REGISTRY


def canonical_unit(name: str) -> str:
    """The canonical registry name of a unit (``'psig'`` → ``'psi_gauge'``).

    This — not the token the document used — is what goes into
    :attr:`mainline_domain.contracts.Quantity.unit`, so that two clauses writing
    ``barg`` and ``bar_g`` produce the same stored unit.
    """
    registry = unit_registry()
    try:
        return str(registry.Unit(name))
    except Exception as exc:  # pint raises several unrelated types here
        raise UnknownUnitError(f"{name!r} is not a unit in the committed registry") from exc


def dimension_of(unit: str) -> str:
    """The canonical dimensionality string, e.g. ``'[mass] / [length] / [time] ** 2'``.

    The dimensionality string, not a friendly label, is what
    :attr:`Quantity.dimension` carries and what comparison keys on.  Friendly
    labels are many-to-one (energy and torque genuinely share a dimensionality,
    and pretending otherwise would be physics fan-fiction), so a label is a
    presentation choice and a dimensionality is a fact.
    """
    return str(unit_registry().Unit(canonical_unit(unit)).dimensionality)


PRESSURE_DIMENSIONALITY: Final[str] = "[mass] / [length] / [time] ** 2"
TEMPERATURE_DIMENSIONALITY: Final[str] = "[temperature]"


# --------------------------------------------------------------------------- #
# reference frames                                                             #
# --------------------------------------------------------------------------- #

GAUGE_PRESSURE_UNITS: Final[frozenset[str]] = frozenset(
    {
        "pascal_gauge",
        "kilopascal_gauge",
        "megapascal_gauge",
        "bar_gauge",
        "millibar_gauge",
        "psi_gauge",
        "kilopond_per_square_centimetre_gauge",
        "inch_water_gauge",
        "millimetre_water_gauge",
    }
)
"""Every unit in the committed file that carries the 101325 Pa offset.

Held as an explicit list rather than derived from "has an offset", because
``degree_Celsius`` also has an offset and is not gauge pressure.  A gauge unit
added to the definition file and not added here would silently become
``reference='none'`` and start comparing against unstated-frame readings, so the
committed test cross-checks the two directions: every offset-carrying pressure
unit in the file is in this set, and every member of this set is in the file.
"""

ABSOLUTE_PRESSURE_UNITS: Final[frozenset[str]] = frozenset(
    {
        "pascal_absolute",
        "kilopascal_absolute",
        "megapascal_absolute",
        "bar_absolute",
        "psi_absolute",
        "inch_water_absolute",
        "standard_atmosphere",
    }
)
"""Pressure units whose author *said* absolute.

``standard_atmosphere`` (``atm``) is here because an atmosphere is an absolute
pressure by definition — nobody writes "3 atm gauge" — and because it is the one
absolute pressure unit that appears in real procedure text without an ``a``
suffix.
"""


def reference_of(unit: str) -> Reference:
    """The reference frame of a canonical unit.  Total, deterministic, no guessing.

    The rules, in order:

    1. an explicit gauge spelling → ``'gauge'``;
    2. an explicit absolute spelling (or ``atm``) → ``'absolute'``;
    3. any other pressure unit → ``'none'`` — *the author did not say*.  This is
       the rule that matters, and it is deliberately not ``'absolute'``: SI says
       a pascal is an absolute pressure, but a P&ID that prints ``kPa`` next to a
       transmitter overwhelmingly means gauge, and neither reading is safe to
       assume.  ``none`` compares only with ``none``;
    4. a ``delta_*`` unit (Pint's difference form of an offset unit) →
       ``'delta'``;
    5. any other temperature unit → ``'absolute'``.  Unlike gauge pressure, the
       Celsius↔Kelvin offset is exact and universal — it does not depend on
       where the instrument is standing — so temperature conversions are allowed
       and are not the failure D5 describes;
    6. everything else → ``'none'``.  Reference class does not apply to a length
       or a count, and ``'none'`` is its own frame, so lengths still compare with
       lengths.
    """
    canonical = canonical_unit(unit)
    if canonical in GAUGE_PRESSURE_UNITS:
        return "gauge"
    if canonical in ABSOLUTE_PRESSURE_UNITS:
        return "absolute"
    dimensionality = dimension_of(canonical)
    if dimensionality == PRESSURE_DIMENSIONALITY:
        return "none"
    if dimensionality == TEMPERATURE_DIMENSIONALITY:
        return "delta" if canonical.startswith("delta_") else "absolute"
    return "none"


# --------------------------------------------------------------------------- #
# friendly dimension labels — used by the DIRECTRIX registry clauses           #
# --------------------------------------------------------------------------- #

_LABEL_REPRESENTATIVES: Final[Mapping[str, str]] = {
    "pressure": "pascal",
    "temperature": "kelvin",
    "time": "second",
    "frequency": "hertz",
    "length": "meter",
    "area": "meter ** 2",
    "volume": "meter ** 3",
    "mass": "kilogram",
    "force": "newton",
    "energy": "joule",
    "power": "watt",
    "velocity": "meter / second",
    "acceleration": "meter / second ** 2",
    "torque": "newton * meter",
    "volumetric_flow": "meter ** 3 / second",
    "mass_flow": "kilogram / second",
    "mass_concentration": "kilogram / meter ** 3",
    "voltage": "volt",
    "current": "ampere",
    "illuminance": "lux",
    "radiation_dose": "sievert",
    "radioactivity": "becquerel",
    "angle": "radian",
    "ratio": "dimensionless",
    "lel_fraction": "percent_lel",
    "uel_fraction": "percent_uel",
    "volume_fraction": "percent_volume",
    "count": "tally",
    "ordinal": "rating",
    "sound_level": "decibel_a_weighted",
}
"""Label → a unit that *has* that dimensionality.

The DIRECTRIX seed and the registry clauses name a dimension by label, because
``Dimension: pressure`` is a sentence an inspector can read and
``Dimension: [mass] / [length] / [time] ** 2`` is not.  The mapping is
many-to-one in one direction only: several labels may share a dimensionality
(``energy``/``force``·``length`` do), and that is fine, because a label is only
ever resolved *to* a dimensionality and never back.
"""


def dimensionality_for_label(label: str) -> str:
    """``'pressure'`` → ``'[mass] / [length] / [time] ** 2'``.  Raises on an unknown label."""
    try:
        representative = _LABEL_REPRESENTATIVES[label]
    except KeyError:
        raise UnknownUnitError(
            f"{label!r} is not a declared dimension label; declared labels are "
            + ", ".join(sorted(_LABEL_REPRESENTATIVES))
        ) from None
    return str(unit_registry().Unit(representative).dimensionality)


DIMENSION_LABELS: Final[tuple[str, ...]] = tuple(sorted(_LABEL_REPRESENTATIVES))


def label_for_dimensionality(dimensionality: str) -> str | None:
    """Best-effort inverse, for messages only.  Never used to decide anything."""
    for label in DIMENSION_LABELS:
        if dimensionality_for_label(label) == dimensionality:
            return label
    return None


# --------------------------------------------------------------------------- #
# the token vocabulary                                                         #
# --------------------------------------------------------------------------- #

UNIT_TOKENS: Final[Mapping[str, str]] = {
    # pressure — gauge
    "psig": "psi_gauge",
    "psi_g": "psi_gauge",
    "barg": "bar_gauge",
    "bar_g": "bar_gauge",
    "kPag": "kilopascal_gauge",
    "kPa_g": "kilopascal_gauge",
    "kpag": "kilopascal_gauge",
    "KPAG": "kilopascal_gauge",
    "MPag": "megapascal_gauge",
    "MPa_g": "megapascal_gauge",
    "Pag": "pascal_gauge",
    "Pa_g": "pascal_gauge",
    "mbarg": "millibar_gauge",
    "mbar_g": "millibar_gauge",
    "kgf/cm2g": "kilopond_per_square_centimetre_gauge",
    "inWG": "inch_water_gauge",
    "inH2Og": "inch_water_gauge",
    "mmH2Og": "millimetre_water_gauge",
    # pressure — explicitly absolute
    "psia": "psi_absolute",
    "bara": "bar_absolute",
    "kPaa": "kilopascal_absolute",
    "kPa_a": "kilopascal_absolute",
    "MPaa": "megapascal_absolute",
    "Paa": "pascal_absolute",
    "Pa_a": "pascal_absolute",
    "atm": "standard_atmosphere",
    "inH2Oa": "inch_water_absolute",
    # pressure — frame unstated
    "Pa": "pascal",
    "kPa": "kilopascal",
    "KPA": "kilopascal",
    "kpa": "kilopascal",
    "MPa": "megapascal",
    "bar": "bar",
    "mbar": "millibar",
    "psi": "pound_force_per_square_inch",
    "mmHg": "millimeter_Hg",
    "torr": "torr",
    "inH2O": "inch_H2O",
    "mmH2O": "millimeter_H2O",
    # temperature
    "degC": "degree_Celsius",
    "degc": "degree_Celsius",
    "°C": "degree_Celsius",
    "degF": "degree_Fahrenheit",
    "°F": "degree_Fahrenheit",
    "K": "kelvin",
    "delta_degC": "delta_degree_Celsius",
    # concentration and ratio
    "%": "percent",
    "pct": "percent",
    "%LEL": "percent_lel",
    "%lel": "percent_lel",
    "pctLEL": "percent_lel",
    "%UEL": "percent_uel",
    "%vol": "percent_volume",
    "vol%": "percent_volume",
    "ppm": "ppm",
    "ppb": "parts_per_billion",
    "pphm": "parts_per_hundred_million",
    # length, area, volume
    "mm": "millimeter",
    "cm": "centimeter",
    "m": "meter",
    "km": "kilometer",
    "ft": "foot",
    "inch": "inch",
    "inches": "inch",
    "mm2": "millimeter ** 2",
    "m2": "meter ** 2",
    "m3": "meter ** 3",
    "L": "liter",
    "l": "liter",
    "mL": "milliliter",
    "kL": "kiloliter",
    # mass
    "kg": "kilogram",
    "g": "gram",
    "t": "metric_ton",
    "tonne": "metric_ton",
    "tonnes": "metric_ton",
    "lb": "pound",
    "lbs": "pound",
    # time
    "s": "second",
    "sec": "second",
    "secs": "second",
    "min": "minute",
    "mins": "minute",
    "h": "hour",
    "hr": "hour",
    "hrs": "hour",
    "hour": "hour",
    "hours": "hour",
    "day": "day",
    "days": "day",
    "week": "week",
    "weeks": "week",
    "month": "month",
    "months": "month",
    "year": "year",
    "years": "year",
    # electrical, mechanical, environmental
    "V": "volt",
    "kV": "kilovolt",
    "mV": "millivolt",
    "A": "ampere",
    "mA": "milliampere",
    "kA": "kiloampere",
    "W": "watt",
    "kW": "kilowatt",
    "MW": "megawatt",
    "kWh": "kilowatt_hour",
    "Hz": "hertz",
    "rpm": "revolutions_per_minute",
    "N": "newton",
    "kN": "kilonewton",
    "Nm": "newton * meter",
    "kNm": "kilonewton * meter",
    "m/s": "meter / second",
    "km/h": "kilometer / hour",
    "L/s": "liter / second",
    "L/min": "liter / minute",
    "m3/h": "meter ** 3 / hour",
    "m3/s": "meter ** 3 / second",
    "kg/h": "kilogram / hour",
    "mg/m3": "milligram / meter ** 3",
    "ug/m3": "microgram / meter ** 3",
    "deg": "degree",
    "degrees": "degree",
    "dBA": "decibel_a_weighted",
    "dB_A": "decibel_a_weighted",
    "lux": "lux",
    "Sv": "sievert",
    "mSv": "millisievert",
    "uSv": "microsievert",
    "Bq": "becquerel",
    "Gy": "gray",
    # the MAINLINE scales
    "point": "tally",
    "points": "tally",
    "count": "tally",
    "level": "rating",
    "levels": "rating",
}
"""Document token → canonical registry unit.

Case-sensitive, because ``mm`` and ``mM`` and ``Mm`` are three different things
and a case-insensitive unit table is a bug generator.  Where a real document
convention is genuinely case-sloppy for a unit whose sloppy spelling is
unambiguous (``kPa``/``KPA``/``kpa``), the variants are listed explicitly rather
than folded — listing is auditable, folding is a rule that will one day fold
something it should not.
"""

AMBIGUOUS_TOKENS: Final[Mapping[str, str]] = {
    "C": (
        "'C' is coulomb in the unit registry and Celsius in a procedure. A "
        "temperature interlock silently read as an electric charge compares "
        "against nothing. Write 'degC'."
    ),
    "F": ("'F' is farad in the unit registry and Fahrenheit in a procedure. Write 'degF'."),
    "in": (
        "'in' is both the inch and the commonest English preposition, so "
        "'reduced to 50 in 2019' would parse as fifty inches. Write 'inch'."
    ),
    "mil": (
        "'mil' is a thousandth of an inch, a millilitre and a million in "
        "different trades. No reading is safe."
    ),
    "gal": (
        "'gal' is the US liquid gallon (3.785 L) or the imperial gallon "
        "(4.546 L) depending on who printed the document — a 20 % difference. "
        "Write litres."
    ),
    "dB": (
        "a bare decibel is a ratio against an unstated reference. An "
        "occupational-noise limit is an A-weighted sound pressure level; write "
        "'dBA'."
    ),
    "M": "'M' is mega- as a prefix and molar as a unit; neither reading is safe alone.",
}
"""Tokens that are refused *by name*, each with the reason it is refused.

Refusing with a reason is the point.  ``UnknownUnitError`` on a token nobody has
heard of is a coverage gap; :class:`AmbiguousUnitError` on ``C`` is a decision,
and the message is what tells an author how to write the clause so that the
system can read it.  Both end the same way for the gate — no comparison, so
abstain, so ``weaken`` — but only one of them tells anybody what to do about it.
"""


def resolve_token(token: str) -> str:
    """Document token → canonical registry unit name.  Never returns a fallback.

    :raises AmbiguousUnitError: the token is in :data:`AMBIGUOUS_TOKENS`.
    :raises UnknownUnitError: the token is in neither table.
    """
    if token in UNIT_TOKENS:
        return canonical_unit(UNIT_TOKENS[token])
    if token in AMBIGUOUS_TOKENS:
        raise AmbiguousUnitError(f"{token!r} is ambiguous: {AMBIGUOUS_TOKENS[token]}")
    raise UnknownUnitError(
        f"{token!r} is not in the committed unit vocabulary. It is not guessed at: "
        "an unreadable unit on a setpoint must reach the gate as an abstention, "
        "which decision D6 resolves to `weaken`."
    )
