# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""SI normalisation for quantities, and the one conflation this table refuses to make.

A lexical channel whose job is ``%LEL``, ``H2S`` and ``100 psi`` has to decide what
``25 %LEL`` and ``25 %`` have in common.  The answer here is **nothing**: ``%LEL`` is a
fraction of the *lower explosive limit* of the particular gas, so 25 %LEL of methane is
1.25 %v/v in air while 25 % is 25 %v/v — a factor of twenty, and the difference between a
routine entry and an explosive atmosphere.  They therefore live in different dimensions and
can never produce the same term.  This is the single most important line in this module and
it is asserted directly in ``tests/unit/recall_lexical/test_quantities.py``.

Gauge and absolute pressure are likewise separate dimensions (``psig``/``barg`` versus
``psi``/``bar``), because converting gauge to absolute requires an ambient pressure this
module does not have and must not invent.

Canonical form.  A recognised quantity becomes exactly two tokens:

* a quantity token ``q:<dimension>:<mantissa>`` where the mantissa is the value converted to
  the dimension's base unit and formatted ``%.6g``.  Six significant figures is chosen so
  that ``1000 ppm`` and ``0.1 %`` — which differ in the last bits of a float64 — produce the
  same string, while ``1000 ppm`` and ``1001 ppm`` do not;
* the dimension's base symbol as an ``identifier`` token, so that "a pressure was mentioned"
  is itself searchable and ``689 kPa`` can be reached from a query written in ``psi``.

Everything in this table is deliberately bounded.  An unbounded unit table is an unbounded
analyser, and an analyser change is a re-index of every posting in the fleet.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

__all__ = [
    "DIMENSION_SYMBOL",
    "UNITS",
    "UNIT_PATTERN",
    "UNIT_TABLE_VERSION",
    "Unit",
    "bare_unit_symbol",
    "canonical_quantity",
    "format_magnitude",
]

UNIT_TABLE_VERSION: Final[str] = "si-units/1"


@dataclass(frozen=True, slots=True)
class Unit:
    """``base = value * factor + offset`` in the dimension's base unit."""

    key: str
    dimension: str
    factor: float
    offset: float = 0.0


#: The identifier token emitted alongside every quantity of that dimension.
DIMENSION_SYMBOL: Final[dict[str, str]] = {
    "ratio": "frac",
    "lel": "lel",
    "uel": "uel",
    "pressure": "pa",
    "pressure_gauge": "pag",
    "temperature": "k",
    "length": "m",
    "mass": "kg",
    "volume": "m3",
    "time": "s",
    "velocity": "m_s",
    "voltage": "v",
    "current": "a",
    "massconc": "kg_m3",
    "volflow": "m3_s",
    "frequency": "hz",
    "rotation": "rpm",
}

_F2K_OFFSET: Final[float] = 273.15 - 32.0 * 5.0 / 9.0

_UNIT_LIST: Final[tuple[Unit, ...]] = (
    # ── dimensionless fractions, and the two that are NOT dimensionless fractions ──────────
    Unit("pct", "ratio", 1e-2),
    Unit("ppm", "ratio", 1e-6),
    Unit("ppb", "ratio", 1e-9),
    Unit("lel", "lel", 1.0),
    Unit("uel", "uel", 1.0),
    # ── pressure (base: pascal absolute) ──────────────────────────────────────────────────
    Unit("pa", "pressure", 1.0),
    Unit("hpa", "pressure", 1e2),
    Unit("kpa", "pressure", 1e3),
    Unit("mpa", "pressure", 1e6),
    Unit("bar", "pressure", 1e5),
    Unit("mbar", "pressure", 1e2),
    Unit("psi", "pressure", 6894.757293168361),
    Unit("psia", "pressure", 6894.757293168361),
    Unit("atm", "pressure", 101325.0),
    Unit("mmhg", "pressure", 133.322387415),
    Unit("inh2o", "pressure", 249.0889),
    Unit("kgcm2", "pressure", 98066.5),
    # gauge pressure: a different dimension, because ambient is unknown here
    Unit("psig", "pressure_gauge", 6894.757293168361),
    Unit("barg", "pressure_gauge", 1e5),
    Unit("kpag", "pressure_gauge", 1e3),
    # ── temperature (base: kelvin) ────────────────────────────────────────────────────────
    Unit("degc", "temperature", 1.0, 273.15),
    Unit("degf", "temperature", 5.0 / 9.0, _F2K_OFFSET),
    Unit("degk", "temperature", 1.0),
    # ── length (base: metre) ──────────────────────────────────────────────────────────────
    Unit("m", "length", 1.0),
    Unit("mm", "length", 1e-3),
    Unit("cm", "length", 1e-2),
    Unit("km", "length", 1e3),
    Unit("in", "length", 0.0254),
    Unit("ft", "length", 0.3048),
    Unit("yd", "length", 0.9144),
    # ── mass (base: kilogram) ─────────────────────────────────────────────────────────────
    Unit("kg", "mass", 1.0),
    Unit("g", "mass", 1e-3),
    Unit("mg", "mass", 1e-6),
    Unit("tonne", "mass", 1e3),
    Unit("lb", "mass", 0.45359237),
    Unit("oz", "mass", 0.028349523125),
    # ── volume (base: cubic metre) ────────────────────────────────────────────────────────
    Unit("m3", "volume", 1.0),
    Unit("l", "volume", 1e-3),
    Unit("ml", "volume", 1e-6),
    Unit("gal", "volume", 0.003785411784),  # US liquid gallon
    Unit("bbl", "volume", 0.158987294928),  # US oil barrel
    # ── time (base: second) ───────────────────────────────────────────────────────────────
    Unit("s", "time", 1.0),
    Unit("ms", "time", 1e-3),
    Unit("min", "time", 60.0),
    Unit("h", "time", 3600.0),
    Unit("day", "time", 86400.0),
    # ── the rest ──────────────────────────────────────────────────────────────────────────
    Unit("m_s", "velocity", 1.0),
    Unit("km_h", "velocity", 1.0 / 3.6),
    Unit("v", "voltage", 1.0),
    Unit("kv", "voltage", 1e3),
    Unit("mv", "voltage", 1e-3),
    Unit("a", "current", 1.0),
    Unit("ka", "current", 1e3),
    Unit("ma", "current", 1e-3),
    Unit("mg_m3", "massconc", 1e-6),
    Unit("ug_m3", "massconc", 1e-9),
    Unit("mg_l", "massconc", 1e-3),
    Unit("m3_h", "volflow", 1.0 / 3600.0),
    Unit("l_min", "volflow", 1e-3 / 60.0),
    Unit("hz", "frequency", 1.0),
    Unit("khz", "frequency", 1e3),
    Unit("rpm", "rotation", 1.0),
)

UNITS: Final[dict[str, Unit]] = {u.key: u for u in _UNIT_LIST}

#: ``(regex fragment, unit key)``.  The fragment is matched against case-folded, ``³``/``²``
#: -flattened, ``µ``→``u`` text.  Ordering is derived, not hand-maintained: see below.
_SURFACES: Final[tuple[tuple[str, str], ...]] = (
    (r"%\s*lel", "lel"),
    (r"%\s*uel", "uel"),
    (r"%\s*v\s*/\s*v", "pct"),
    (r"%\s*vol", "pct"),
    (r"vol\s*%", "pct"),
    (r"%", "pct"),
    (r"percent", "pct"),
    (r"ppm", "ppm"),
    (r"ppb", "ppb"),
    (r"mg\s*/\s*m3", "mg_m3"),
    (r"ug\s*/\s*m3", "ug_m3"),
    (r"mg\s*/\s*l", "mg_l"),
    (r"m3\s*/\s*h", "m3_h"),
    (r"l\s*/\s*min", "l_min"),
    (r"lpm", "l_min"),
    (r"m\s*/\s*s", "m_s"),
    (r"km\s*/\s*h", "km_h"),
    (r"kph", "km_h"),
    (r"kg\s*/\s*cm2", "kgcm2"),
    (r"in\s*h2o", "inh2o"),
    (r"mmhg", "mmhg"),
    (r"kpag", "kpag"),
    (r"kpa", "kpa"),
    (r"mpa", "mpa"),
    (r"hpa", "hpa"),
    (r"pa", "pa"),
    (r"mbar", "mbar"),
    (r"barg", "barg"),
    (r"bar", "bar"),
    (r"psig", "psig"),
    (r"psia", "psia"),
    (r"psi", "psi"),
    (r"atm", "atm"),
    (r"°\s*c", "degc"),
    (r"deg\s*c", "degc"),
    (r"°\s*f", "degf"),
    (r"deg\s*f", "degf"),
    (r"°\s*k", "degk"),
    (r"kelvin", "degk"),
    (r"celsius", "degc"),
    (r"fahrenheit", "degf"),
    (r"mm", "mm"),
    (r"cm", "cm"),
    (r"km", "km"),
    (r"metres?", "m"),
    (r"meters?", "m"),
    (r"m", "m"),
    (r"inch(?:es)?", "in"),
    (r"in", "in"),
    (r"ft", "ft"),
    (r"feet", "ft"),
    (r"foot", "ft"),
    (r"yd", "yd"),
    (r"kg", "kg"),
    (r"mg", "mg"),
    (r"tonnes?", "tonne"),
    (r"lbs?", "lb"),
    (r"oz", "oz"),
    (r"g", "g"),
    (r"m3", "m3"),
    (r"ml", "ml"),
    (r"litres?", "l"),
    (r"liters?", "l"),
    (r"gal(?:lons?)?", "gal"),
    (r"bbl", "bbl"),
    (r"l", "l"),
    (r"ms", "ms"),
    (r"min(?:ute)?s?", "min"),
    (r"h(?:ou)?rs?", "h"),
    (r"h", "h"),
    (r"sec(?:ond)?s?", "s"),
    (r"s", "s"),
    (r"days?", "day"),
    (r"kv", "kv"),
    (r"mv", "mv"),
    (r"v(?:olts?)?", "v"),
    (r"ka", "ka"),
    (r"ma", "ma"),
    (r"a(?:mps?)?", "a"),
    (r"khz", "khz"),
    (r"hz", "hz"),
    (r"rpm", "rpm"),
)

_META = re.compile(r"\\s\*|\(\?:|\)\?|[()?\\]")


def _specificity(fragment: str) -> int:
    """How many literal characters a fragment can consume — its matching priority.

    Ordering the alternation by hand is how ``psi`` shadows ``psig`` and ``m`` shadows
    ``min``.  Deriving it means adding a unit cannot silently break an existing one.
    """
    return len(_META.sub("", fragment))


_ORDERED: Final[tuple[tuple[str, str], ...]] = tuple(
    sorted(_SURFACES, key=lambda item: (-_specificity(item[0]), item[0]))
)

#: One alternation, anchored by the caller with ``.match(text, pos)``.  The trailing
#: negative lookahead is what stops ``m`` from matching the first letter of ``metres`` and
#: ``2s`` from being read out of the asset tag ``2S1``.
UNIT_PATTERN: Final[re.Pattern[str]] = re.compile(
    "(?:" + "|".join(f"(?P<u{i}>{frag})" for i, (frag, _) in enumerate(_ORDERED)) + r")(?![a-z0-9])"
)

_GROUP_TO_KEY: Final[dict[str, str]] = {f"u{i}": key for i, (_, key) in enumerate(_ORDERED)}

#: Unit surfaces that are meaningful with no number in front of them, e.g. a permit that says
#: "monitor for %LEL" or an SDS that says "TWA in ppm".
#:
#: Membership is decided by one test: **is this string ever an ordinary English word?**  A
#: bare ``m`` is not a statement about length, ``bar`` is a crow bar as often as it is 100 kPa,
#: and ``in`` is a preposition — so none of them are here.  ``psig``, ``%LEL`` and ``mg/m3``
#: are never anything else.  Getting this wrong does not lose a recall, it invents one, which
#: under this design is the more expensive error.
_BARE_SURFACES: Final[dict[str, str]] = {
    "%lel": "lel",
    "%uel": "uel",
    "lel": "lel",
    "uel": "uel",
    "ppm": "ppm",
    "ppb": "ppb",
    "psig": "psig",
    "psia": "psia",
    "psi": "psi",
    "kpa": "kpa",
    "mpa": "mpa",
    "barg": "barg",
    "rpm": "rpm",
    "mg/m3": "mg_m3",
    "ug/m3": "ug_m3",
    "mg/l": "mg_l",
}


def bare_unit_symbol(token: str) -> str | None:
    """Dimension symbol for a unit written without a number, or ``None``."""
    key = _BARE_SURFACES.get(token)
    if key is None:
        return None
    return DIMENSION_SYMBOL[UNITS[key].dimension]


def format_magnitude(value: float) -> str:
    """Deterministic 6-significant-figure rendering.

    ``%.6g`` and not ``repr``: ``1000 * 1e-6`` and ``0.1 * 1e-2`` are different float64
    values and identical quantities, and a term that depends on the last two bits of a
    conversion is a term that never matches.
    """
    text = f"{value:.6g}"
    # `-0` is a distinct float and an identical quantity.
    return "0" if text in {"-0", "-0.0"} else text


def canonical_quantity(value: float, unit_key: str) -> tuple[str, str]:
    """Return ``(quantity_token, dimension_symbol)`` for a recognised unit key."""
    unit = UNITS[unit_key]
    base = value * unit.factor + unit.offset
    symbol = DIMENSION_SYMBOL[unit.dimension]
    return f"q:{unit.dimension}:{format_magnitude(base)}", symbol


def unit_key_for_match(match: re.Match[str]) -> str:
    """Which unit key an :data:`UNIT_PATTERN` match corresponds to."""
    for group, key in _GROUP_TO_KEY.items():
        if match.group(group) is not None:
            return key
    raise AssertionError("UNIT_PATTERN matched with no capturing group set")  # pragma: no cover


def unit_table_digest_material() -> list[str]:
    """Everything a fingerprint must cover so that a table edit cannot go unnoticed."""
    material = [UNIT_TABLE_VERSION]
    material.extend(f"{u.key}|{u.dimension}|{u.factor!r}|{u.offset!r}" for u in _UNIT_LIST)
    material.extend(f"{frag}->{key}" for frag, key in _ORDERED)
    material.extend(f"bare:{surface}->{key}" for surface, key in sorted(_BARE_SURFACES.items()))
    material.extend(f"dim:{d}->{s}" for d, s in sorted(DIMENSION_SYMBOL.items()))
    return material
