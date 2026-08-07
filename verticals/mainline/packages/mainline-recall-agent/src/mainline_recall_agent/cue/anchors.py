# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""Semantic anchoring — prompt-injection posture layer 4, with no model in it.

ARCHITECTURE §8.4: *"a cue whose hard anchors — equipment tags, SI-normalised setpoints,
regulatory citations, CAS numbers — are absent from the source's extracted anchor set is
rejected before insert; pure regex + gazetteer, the cheapest high-value control we have."*

The control is worth stating precisely, because it is easy to over-claim.  It does **not**
detect a wrong cue.  It detects a cue that names a **checkable particular** the source does
not contain: a tag, a setpoint, a regulation, a substance.  Those four classes are chosen
because they are what a confabulation or an injected instruction reaches for when it wants
to sound like plant knowledge, and what a supervisor will act on without re-reading the
source.  ``K-401`` in a cue whose source never mentions ``K-401`` is a fabrication whether
a model or an attacker wrote it, and no model is consulted to say so.

Three commitments, and the third is the one that makes the control safe to switch on:

**Precision over recall.**  The patterns are narrow and **case-sensitive**.  Plant tags,
CFR citations and unit symbols all carry meaning in their casing, and a case-insensitive
pass turns ``3 in the morning`` into a length anchor.

**Setpoints are compared in SI, not as strings.**  ``3.5 bar`` in a cue and ``350 kPa`` in
the source are the same fact, and rejecting that cue would be a false alarm that teaches
people to ignore alarms.  A magnitude+unit anchor normalises through the committed
gazetteer before the set comparison.

**Under-recognition can only weaken the control, never trip it.**  The check asks whether
every anchor *found in the cue* is present in the source.  A surface form the gazetteer
does not know produces no anchor at all, so an unrecognised form in a cue is silently
tolerated rather than falsely rejected.  The residual risk — a fabricated identifier in a
form we do not recognise — is real, is stated in the README, and is not papered over here.
The alternative, loose patterns, spends the whole budget rejecting good cues.

Known duplication, stated rather than hidden
--------------------------------------------
``mainline_domain.anchors`` (ANCHORLOCK) implements the same four classes — plus
``named_role``, ``instrument_loop`` and ``isolation_point_id`` — over a *versioned,
fingerprinted* gazetteer, for a different job: vetoing a cosine clause match and raising a
weakening signal.  This module does not import it, because ``mainline-recall-agent``
declares no dependency on ``mainline-domain`` and adding one is not this worker's file to
change.  That is a duplication, not a design: two extractors can disagree about what a hard
anchor is, and the day they do, "the tag is in the source" will mean one thing to the clause
gate and another to the cue gate.  The end state is one gazetteer with one fingerprint,
consumed by both, with that fingerprint pinned into ``recall_policy`` beside
``EMBED_TEMPLATE_SHA256``.  Raised as a cross-domain note; until it is resolved, the two
implementations are independent and only this one governs cue rejection.
"""

from __future__ import annotations

import hashlib
import re
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field

from .errors import AnchorGazetteerError

__all__ = [
    "ANCHOR_KINDS",
    "UNIT_GAZETTEER",
    "Anchor",
    "AnchorKind",
    "AnchorVerdict",
    "anchor_keys",
    "extract_anchors",
    "span_sha256",
    "verify_anchors",
]

AnchorKind = Literal["equipment_tag", "setpoint", "citation", "cas"]

ANCHOR_KINDS: Final[tuple[AnchorKind, ...]] = (
    "equipment_tag",
    "setpoint",
    "citation",
    "cas",
)

# --------------------------------------------------------------------------------------
# The unit gazetteer: exact surface form -> (canonical unit, multiplier to canonical).
#
# Keyed by the *exact* casing, because the pattern is case-sensitive.  Spelled-out aliases
# are carried alongside the symbols so that "3 metres" in a source and "3 m" in a cue
# resolve to the same normalised anchor — the asymmetry that would otherwise reject a
# faithful cue for paraphrasing a unit.
#
# Temperature is absent from this table and handled separately: it is affine, not linear,
# and a table of multipliers would silently turn 20 degC into 20 K.
# --------------------------------------------------------------------------------------

_PSI_TO_KPA: Final[float] = 6.894757293168361

UNIT_GAZETTEER: Final[dict[str, tuple[str, float]]] = {
    # pressure -> kPa
    "Pa": ("kPa", 0.001),
    "pascal": ("kPa", 0.001),
    "pascals": ("kPa", 0.001),
    "kPa": ("kPa", 1.0),
    "kpa": ("kPa", 1.0),
    "kilopascal": ("kPa", 1.0),
    "kilopascals": ("kPa", 1.0),
    "MPa": ("kPa", 1000.0),
    "bar": ("kPa", 100.0),
    "barg": ("kPa", 100.0),
    "mbar": ("kPa", 0.1),
    "psi": ("kPa", _PSI_TO_KPA),
    "psig": ("kPa", _PSI_TO_KPA),
    "kg/cm2": ("kPa", 98.0665),
    # length -> m
    "mm": ("m", 0.001),
    "millimetre": ("m", 0.001),
    "millimetres": ("m", 0.001),
    "cm": ("m", 0.01),
    "centimetre": ("m", 0.01),
    "centimetres": ("m", 0.01),
    "m": ("m", 1.0),
    "metre": ("m", 1.0),
    "metres": ("m", 1.0),
    "meter": ("m", 1.0),
    "meters": ("m", 1.0),
    "km": ("m", 1000.0),
    "kilometre": ("m", 1000.0),
    "kilometres": ("m", 1000.0),
    "inch": ("m", 0.0254),
    "inches": ("m", 0.0254),
    "ft": ("m", 0.3048),
    "feet": ("m", 0.3048),
    # mass -> kg
    "g": ("kg", 0.001),
    "gram": ("kg", 0.001),
    "grams": ("kg", 0.001),
    "kg": ("kg", 1.0),
    "kilogram": ("kg", 1.0),
    "kilograms": ("kg", 1.0),
    "t": ("kg", 1000.0),
    "tonne": ("kg", 1000.0),
    "tonnes": ("kg", 1000.0),
    "lb": ("kg", 0.45359237),
    # time -> s
    "ms": ("s", 0.001),
    "s": ("s", 1.0),
    "sec": ("s", 1.0),
    "second": ("s", 1.0),
    "seconds": ("s", 1.0),
    "min": ("s", 60.0),
    "minute": ("s", 60.0),
    "minutes": ("s", 60.0),
    "h": ("s", 3600.0),
    "hr": ("s", 3600.0),
    "hour": ("s", 3600.0),
    "hours": ("s", 3600.0),
    # electrical -> V / A
    "mV": ("V", 0.001),
    "V": ("V", 1.0),
    "volt": ("V", 1.0),
    "volts": ("V", 1.0),
    "kV": ("V", 1000.0),
    "mA": ("A", 0.001),
    "A": ("A", 1.0),
    "amp": ("A", 1.0),
    "amps": ("A", 1.0),
    "ampere": ("A", 1.0),
    "amperes": ("A", 1.0),
    "kA": ("A", 1000.0),
    # energy / power -> J / W
    "J": ("J", 1.0),
    "joule": ("J", 1.0),
    "joules": ("J", 1.0),
    "kJ": ("J", 1000.0),
    "MJ": ("J", 1000000.0),
    "W": ("W", 1.0),
    "watt": ("W", 1.0),
    "watts": ("W", 1.0),
    "kW": ("W", 1000.0),
    "MW": ("W", 1000000.0),
    # force / torque -> N / N.m
    "N": ("N", 1.0),
    "kN": ("N", 1000.0),
    "Nm": ("N.m", 1.0),
    "N.m": ("N.m", 1.0),
    "kNm": ("N.m", 1000.0),
    # concentration
    "ppm": ("ppm", 1.0),
    "ppb": ("ppm", 0.001),
    "%LEL": ("%LEL", 1.0),
    "% LEL": ("%LEL", 1.0),
    "%": ("%", 1.0),
    "percent": ("%", 1.0),
    "mg/m3": ("mg/m3", 1.0),
    # speed / rotation
    "m/s": ("m/s", 1.0),
    "km/h": ("m/s", 0.2777777777777778),
    "rpm": ("rpm", 1.0),
    "RPM": ("rpm", 1.0),
    # volume / flow
    "mL": ("m3", 0.000001),
    "L": ("m3", 0.001),
    "litre": ("m3", 0.001),
    "litres": ("m3", 0.001),
    "m3": ("m3", 1.0),
    "L/s": ("m3/s", 0.001),
    "L/min": ("m3/s", 0.000016666666666666667),
    "m3/h": ("m3/s", 0.0002777777777777778),
}

#: Affine units, handled outside the multiplier table.  ``(scale, offset)`` into kelvin.
_TEMPERATURE: Final[dict[str, tuple[float, float]]] = {
    "degC": (1.0, 273.15),
    "degc": (1.0, 273.15),
    "°C": (1.0, 273.15),
    "degF": (5.0 / 9.0, 255.3722222222222),
    "°F": (5.0 / 9.0, 255.3722222222222),
    "K": (1.0, 0.0),
}


def _unit_alternation() -> str:
    """Longest surface form first, so ``%LEL`` cannot be eaten by ``%`` and ``m/s`` by ``m``."""
    surfaces = sorted([*UNIT_GAZETTEER, *_TEMPERATURE], key=lambda s: (-len(s), s))
    if not surfaces:  # pragma: no cover - both tables are literals
        raise AnchorGazetteerError("the unit gazetteer is empty")
    return "|".join(re.escape(surface) for surface in surfaces)


# One master pattern, one pass.  ``re.finditer`` never returns overlapping matches and the
# alternation is ordered by specificity, so a CAS number can never also be read as a
# setpoint and a citation can never be shredded into a tag plus a number.
_MASTER: Final[re.Pattern[str]] = re.compile(
    r"""
    (?P<cas>\b\d{2,7}-\d{2}-\d\b)
  | (?P<citation>
        \b\d{1,3}\s*C\.?\s?F\.?\s?R\.?\s*(?:§+\s*)?\d+(?:\.\d+)*\b
      | §+\s*\d+(?:\.\d+)*
      | \bAS(?:/NZS)?\s*\d{3,5}(?:\.\d+)*(?:\s*[-:]\s*\d{4})?\b
      | \bISO\s*\d{3,5}(?:[-.]\d+)*(?:\s*:\s*\d{4})?\b
      | \bIEC\s*\d{3,5}(?:[-.]\d+)*\b
      | \bMDG\s*\d{2,4}\b
      | \b(?:WHS|OHS)\s+[Rr]eg(?:ulation)?s?\.?\s*(?:\d{4}\s*)?(?:r\.?\s*)?\d+[A-Z]?\b
    )
  | (?P<setpoint>
        (?P<magnitude>-?\d+(?:\.\d+)?)\s*(?P<unit>UNITS)(?![A-Za-z0-9/])
    )
  | (?P<equipment_tag>\b[A-Z]{1,5}\s?-\s?\d{1,5}(?:-\d{1,4})?[A-Z]{0,2}\b)
    """.replace("UNITS", _unit_alternation()),
    re.VERBOSE,
)

#: Significant figures that survive SI normalisation before two magnitudes are called
#: equal.  Six is far beyond any instrument in the corpus and far short of float noise.
_SIGFIGS: Final[int] = 6


class Anchor(BaseModel):
    """One checkable particular found in a text.

    ``normalised`` is the comparison key; ``raw`` is what a human is shown when the anchor
    is the reason a cue was refused.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: AnchorKind
    raw: str = Field(min_length=1)
    normalised: str = Field(min_length=1)
    start: int = Field(ge=0)
    end: int = Field(ge=0)

    @property
    def key(self) -> tuple[str, str]:
        return (self.kind, self.normalised)


def _cas_check_digit_ok(raw: str) -> bool:
    r"""CAS check digit: digits weighted right-to-left, modulo 10.

    Without it, ``\d{2,7}-\d{2}-\d`` matches phone numbers, OEM part numbers and date
    ranges, and a control that fires on those is a control nobody keeps switched on.
    """
    digits = raw.replace("-", "")
    body, check = digits[:-1], digits[-1]
    total = sum(int(d) * (i + 1) for i, d in enumerate(reversed(body)))
    return total % 10 == int(check)


def _normalise_tag(raw: str) -> str:
    return "".join(raw.split()).upper()


def _normalise_citation(raw: str) -> str:
    collapsed = " ".join(raw.split()).upper()
    collapsed = re.sub(r"C\.?\s?F\.?\s?R\.?", "CFR", collapsed)
    collapsed = re.sub(r"§+\s*", "§", collapsed)
    collapsed = re.sub(r"\s*([-:])\s*", r"\1", collapsed)
    collapsed = re.sub(r"\bREGULATIONS?\b|\bREGS?\b", "REG", collapsed)
    collapsed = collapsed.replace("REG.", "REG")
    return re.sub(r"\s+", " ", collapsed).strip()


def _format_magnitude(value: float) -> str:
    """Fixed significant figures — deterministic, and immune to float printing drift."""
    return f"{value:.{_SIGFIGS}g}"


def _normalise_setpoint(magnitude: str, unit: str) -> str:
    value = float(magnitude)
    affine = _TEMPERATURE.get(unit)
    if affine is not None:
        scale, offset = affine
        return f"{_format_magnitude(value * scale + offset)} K"
    entry = UNIT_GAZETTEER.get(unit)
    if entry is None:  # pragma: no cover - the pattern is built from the gazetteer
        raise AnchorGazetteerError(
            "the setpoint pattern matched a unit the gazetteer does not carry", unit=unit
        )
    canonical, multiplier = entry
    return f"{_format_magnitude(value * multiplier)} {canonical}"


def extract_anchors(text: str) -> tuple[Anchor, ...]:
    """Every checkable particular in ``text``, in document order.

    Deterministic and total: the same string always yields the same anchors, and no model,
    no network and no clock is consulted.
    """
    found: list[Anchor] = []
    for match in _MASTER.finditer(text):
        raw = match.group(0)
        cas = match.group("cas")
        citation = match.group("citation")
        setpoint = match.group("setpoint")
        tag = match.group("equipment_tag")
        kind: AnchorKind
        if cas is not None:
            if not _cas_check_digit_ok(cas):
                continue
            kind, normalised = "cas", cas
        elif citation is not None:
            kind, normalised = "citation", _normalise_citation(citation)
        elif setpoint is not None:
            kind = "setpoint"
            normalised = _normalise_setpoint(match.group("magnitude"), match.group("unit"))
        elif tag is not None:
            kind, normalised = "equipment_tag", _normalise_tag(tag)
        else:  # pragma: no cover - the alternation is exhaustive
            raise AnchorGazetteerError("anchor pattern matched no named group", raw=raw)
        found.append(
            Anchor(
                kind=kind,
                raw=raw,
                normalised=normalised,
                start=match.start(),
                end=match.end(),
            )
        )
    return tuple(found)


def anchor_keys(anchors: tuple[Anchor, ...]) -> frozenset[tuple[str, str]]:
    """The comparison set: ``(kind, normalised)`` pairs, positions discarded."""
    return frozenset(anchor.key for anchor in anchors)


class AnchorVerdict(BaseModel):
    """The result of checking one cue's anchors against its source's anchor set."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    ok: bool
    cue_anchors: tuple[Anchor, ...]
    missing: tuple[Anchor, ...]

    @property
    def missing_keys(self) -> tuple[tuple[str, str], ...]:
        return tuple(anchor.key for anchor in self.missing)


def verify_anchors(cue_text: str, source_keys: frozenset[tuple[str, str]]) -> AnchorVerdict:
    """Refuse a cue that names a particular its source does not contain.

    The comparison is one-directional on purpose.  A source anchor absent from the cue is
    normal — a cue is a summary and drops most particulars.  A *cue* anchor absent from the
    source has no innocent explanation: the same extractor ran over both texts, so either
    the model invented the particular or something inside the document told it to.
    """
    cue_anchors = extract_anchors(cue_text)
    missing = tuple(anchor for anchor in cue_anchors if anchor.key not in source_keys)
    return AnchorVerdict(ok=not missing, cue_anchors=cue_anchors, missing=missing)


def span_sha256(text: str) -> str:
    """The span hash carried to human review (ARCHITECTURE §8.4 layer 6).

    The *hash*, not the text: ``document_intake_finding`` is read by people who may not hold
    the source document's classification, and the offending span may itself be an injected
    instruction.  A digest identifies it without republishing it.
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
