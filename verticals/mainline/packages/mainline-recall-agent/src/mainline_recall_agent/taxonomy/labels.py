# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The label validator: an activity label must name a FUNCTION PERFORMED.

This is the rule the whole archival argument rests on.  ARCHITECTURE §5.4 states it in the
DDL comment — ``label STRING NOT NULL, -- a FUNCTION PERFORMED, never a thing or a place``
— and ``research/05-architecture/diachronic-recall.md`` §3 gives the reason: asset tags,
contractors, org charts and pit names churn every three years, and *"isolating stored
energy before intrusive work"* does not.  A taxonomy classified by things is a taxonomy
that has to be re-induced whenever the fleet is re-tagged, and re-inducting the taxonomy
re-partitions the vector index (see :mod:`~mainline_recall_agent.taxonomy.register`).

A CHECK constraint cannot express "is this phrase a function", so the rule is enforced
here, at every point where a label enters the system: the level-1 register loader, the
induction merge phase, and :class:`~mainline_recall_agent.taxonomy.models.ActivityNode`
construction itself — which means a node read *back* from the row store is validated too,
and a label that got in some other way is found rather than trusted.

Reading the research note honestly
----------------------------------
The note's own level-2 examples are ``"energy isolation"`` and ``"tyre & rim"``.  Both are
refused here, and that is deliberate rather than an oversight: they are shorthand in a
prose table, and they are precisely the shape — a nominalisation and an equipment pair —
that the DDL comment and this worker's brief forbid.  Their functional renderings are
``"isolating stored energy before intrusive work"`` and ``"inflating and servicing
pressurised assemblies at a distance"``.  The shorthand names the topic; the label has to
name the work.

What this validator is and is not
---------------------------------
It is a **deterministic, auditable, lexicon-driven** check: a leading gerund drawn from a
committed verb lexicon, no equipment or place term from a committed gazetteer, lowercase,
no asset tags.  It is not a parser and it is not a model.  It will accept a grammatical
nonsense phrase that happens to lead with a gerund, and it will reject a legitimate
function whose verb is not yet in the lexicon.  Both failure modes are visible: the first
survives to a human review of the frozen taxonomy, the second raises with the exact token
it did not recognise, and the fix in either case is a reviewed edit to a list in this
file rather than a change of behaviour somewhere in a prompt.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

from .errors import LabelRejected

__all__ = [
    "CHEMICAL_TOKENS",
    "EQUIPMENT_AND_PLACE_BIGRAMS",
    "EQUIPMENT_AND_PLACE_UNIGRAMS",
    "FUNCTION_GERUNDS",
    "MAX_LABEL_CHARS",
    "MAX_LABEL_TOKENS",
    "MIN_LABEL_CHARS",
    "REJECTION_REASONS",
    "LabelVerdict",
    "check_label",
    "normalise_label",
    "validate_label",
]

#: Bounds.  A label is a heading in a business classification scheme, not a sentence:
#: long labels are descriptions, and a description cannot be a stable prefix value.
MIN_LABEL_CHARS: Final[int] = 8
MAX_LABEL_CHARS: Final[int] = 96
MAX_LABEL_TOKENS: Final[int] = 12

#: Stable rejection codes.  Aggregated on the version record, so they are part of the
#: published artefact and may not be renamed casually.
REJECTION_REASONS: Final[tuple[str, ...]] = (
    "empty",
    "too_short",
    "too_long",
    "not_lowercase",
    "illegal_character",
    "too_many_tokens",
    "asset_tag",
    "equipment_or_place_term",
    "no_function_verb",
    "verb_not_leading",
    "unknown_gerund",
)

#: Gerunds that name work a person or a crew performs.  Alphabetical, and deliberately a
#: closed list: an open morphological rule ("any token ending in -ing") admits `casing`,
#: `housing`, `bearing`, `tailing` and `ring`, every one of which is a thing.
FUNCTION_GERUNDS: Final[frozenset[str]] = frozenset(
    {
        "accessing",
        "anchoring",
        "applying",
        "ascending",
        "assaying",
        "authorising",
        "authorizing",
        "backfilling",
        "barricading",
        "blasting",
        "bleeding",
        "bolting",
        "boring",
        "breaking",
        "charging",
        "cleaning",
        "clearing",
        "climbing",
        "commissioning",
        "communicating",
        "confining",
        "connecting",
        "containing",
        "controlling",
        "coordinating",
        "covering",
        "crossing",
        "cutting",
        "de-energising",
        "de-energizing",
        "decanting",
        "decommissioning",
        "decontaminating",
        "deflating",
        "descending",
        "dewatering",
        "digging",
        "disconnecting",
        "dispatching",
        "disposing",
        "dosing",
        "drilling",
        "driving",
        "dumping",
        "energising",
        "energizing",
        "entering",
        "erecting",
        "establishing",
        "evacuating",
        "excavating",
        "excluding",
        "exiting",
        "extinguishing",
        "filling",
        "firing",
        "fitting",
        "guarding",
        "handling",
        "hauling",
        "immobilising",
        "immobilizing",
        "impounding",
        "inflating",
        "inspecting",
        "isolating",
        "jacking",
        "landing",
        "lifting",
        "loading",
        "locking",
        "lowering",
        "maintaining",
        "managing",
        "measuring",
        "meshing",
        "mixing",
        "monitoring",
        "mucking",
        "moving",
        "operating",
        "parking",
        "permitting",
        "planning",
        "positioning",
        "preventing",
        "propping",
        "protecting",
        "proving",
        "pumping",
        "recharging",
        "reclaiming",
        "recovering",
        "refuelling",
        "releasing",
        "rescuing",
        "restraining",
        "reversing",
        "rigging",
        "sampling",
        "scaling",
        "securing",
        "selecting",
        "separating",
        "servicing",
        "shotcreting",
        "slinging",
        "spraying",
        "stabilising",
        "stabilizing",
        "storing",
        "supervising",
        "supporting",
        "surveying",
        "suspending",
        "testing",
        "tipping",
        "towing",
        "transferring",
        "transporting",
        "traversing",
        "treating",
        "unloading",
        "venting",
        "ventilating",
        "verifying",
        "washing",
        "welding",
        "working",
    }
)

#: Equipment and place nouns.  Concrete instances only — the words that get re-tagged,
#: renamed, sold, decommissioned or re-surveyed.  Abstractions a functional label legitimately
#: needs ("energy", "equipment", "machinery", "people", "atmosphere", "load") are absent by
#: design: banning them would ban the vocabulary of function itself.
EQUIPMENT_AND_PLACE_UNIGRAMS: Final[frozenset[str]] = frozenset(
    {
        # equipment
        "agitator",
        "boiler",
        "bogger",
        "borer",
        "busbar",
        "cable",
        "compressor",
        "conveyor",
        "crane",
        "crusher",
        "cyclone",
        "dozer",
        "bulldozer",
        "dragline",
        "drill",
        "excavator",
        "feeder",
        "flange",
        "forklift",
        "furnace",
        "gearbox",
        "generator",
        "grader",
        "hoist",
        "hose",
        "jumbo",
        "kiln",
        "ladder",
        "lhd",
        "loader",
        "locomotive",
        "mill",
        "pipeline",
        "pump",
        "reclaimer",
        "rig",
        "rim",
        "scaffold",
        "scraper",
        "shovel",
        "silo",
        "sprocket",
        "stacker",
        "substation",
        "switchboard",
        "switchgear",
        "tank",
        "telehandler",
        "thickener",
        "transformer",
        "truck",
        "tyre",
        "tire",
        "vessel",
        "wagon",
        "winder",
        # places
        "adit",
        "berm",
        "crosscut",
        "dam",
        "decline",
        "laydown",
        "magazine",
        "pit",
        "plant",
        "pond",
        "portal",
        "quarry",
        "shaft",
        "shed",
        "stockpile",
        "stope",
        "tsf",
        "warehouse",
        "workshop",
    }
)

#: Two-token equipment and place names.  Checked over adjacent token pairs, because the
#: individual words ("light", "control", "haul", "room") must stay legal on their own.
EQUIPMENT_AND_PLACE_BIGRAMS: Final[frozenset[str]] = frozenset(
    {
        "apron feeder",
        "ball mill",
        "boom lift",
        "control room",
        "conveyor belt",
        "crib room",
        "drill rig",
        "dump truck",
        "go line",
        "haul road",
        "haul truck",
        "light vehicle",
        "man cage",
        "mobile plant",
        "north pit",
        "open pit",
        "processing plant",
        "rom pad",
        "sag mill",
        "scissor lift",
        "service truck",
        "ship loader",
        "south pit",
        "tailings dam",
        "tailings storage",
        "ventilation fan",
        "wash bay",
        "water cart",
        "work platform",
    }
)

#: The only tokens that may contain a digit.  Everything else with a digit in it is an
#: asset tag or a level number, and both are exactly what the functional scheme exists to
#: avoid depending on.
CHEMICAL_TOKENS: Final[frozenset[str]] = frozenset(
    {"ch4", "co2", "h2s", "hcn", "nox", "no2", "o2", "pm10", "so2", "sox"}
)

_TOKEN_RE: Final[re.Pattern[str]] = re.compile(r"[a-z][a-z0-9'\-]*|[0-9]+")
_ALLOWED_RE: Final[re.Pattern[str]] = re.compile(r"^[a-z][a-z0-9 '\-]*[a-z0-9]$")
_DIGIT_RE: Final[re.Pattern[str]] = re.compile(r"[0-9]")
_GERUND_SUFFIX: Final[str] = "ing"


@dataclass(frozen=True, slots=True)
class LabelVerdict:
    """The result of checking one label.

    ``ok`` and ``reason`` are the whole interface; ``detail`` names the offending token so
    a rejection is actionable without re-running the checker by hand.
    """

    label: str
    ok: bool
    reason: str | None = None
    detail: str | None = None

    def render(self) -> str:
        if self.ok:
            return f"{self.label!r}: accepted"
        because = f": {self.detail}" if self.detail else ""
        return f"{self.label!r}: rejected ({self.reason}{because})"


def normalise_label(label: str) -> str:
    """Collapse whitespace.  Case is **not** folded — see ``not_lowercase`` below.

    Folding case here would silently accept ``North Pit``.  A capital letter inside an
    archival label is almost always a proper noun (a place, an asset, a contractor), which
    is the churn the functional scheme exists to survive, so the case is evidence and is
    kept.
    """
    return " ".join(label.split())


#: Shortest token a suffix rule may strip from and still leave a real word.  ``ies`` needs
#: one more character than ``es``/``s`` because it removes three and appends one.
_MIN_STEM_CHARS: Final[int] = 3
_MIN_IES_CHARS: Final[int] = 4


def _plural_forms(token: str) -> tuple[str, ...]:
    """Candidate singular forms.  Crude on purpose: a stemmer here would be a dependency
    and a source of surprises, and the gazetteer is a hand-maintained list either way."""
    forms = [token]
    if token.endswith("ies") and len(token) > _MIN_IES_CHARS:
        forms.append(token[:-3] + "y")
    if token.endswith("es") and len(token) > _MIN_STEM_CHARS:
        forms.append(token[:-2])
    if token.endswith("s") and len(token) > _MIN_STEM_CHARS:
        forms.append(token[:-1])
    return tuple(forms)


def _gazetteer_hit(tokens: list[str]) -> str | None:
    for index, token in enumerate(tokens):
        for form in _plural_forms(token):
            if form in EQUIPMENT_AND_PLACE_UNIGRAMS:
                return token
        if index + 1 < len(tokens):
            pair = f"{token} {tokens[index + 1]}"
            for form in _plural_forms(pair):
                if form in EQUIPMENT_AND_PLACE_BIGRAMS:
                    return pair
    return None


def _verb_verdict(label: str, tokens: list[str]) -> LabelVerdict:
    head = tokens[0]
    if head in FUNCTION_GERUNDS:
        return LabelVerdict(label=label, ok=True)
    later = [t for t in tokens[1:] if t in FUNCTION_GERUNDS]
    if later:
        return LabelVerdict(
            label=label,
            ok=False,
            reason="verb_not_leading",
            detail=(
                f"the label leads with {head!r}; a functional label leads with the work "
                f"({later[0]!r} appears later, so the phrase names a thing that is being "
                "worked on rather than the work)"
            ),
        )
    if head.endswith(_GERUND_SUFFIX):
        return LabelVerdict(
            label=label,
            ok=False,
            reason="unknown_gerund",
            detail=(
                f"{head!r} is not in FUNCTION_GERUNDS; add it in a reviewed edit if it "
                "genuinely names work performed, and note that 'bearing', 'casing', "
                "'housing' and 'tailing' end in -ing and are things"
            ),
        )
    return LabelVerdict(
        label=label,
        ok=False,
        reason="no_function_verb",
        detail=f"no gerund from the committed verb lexicon appears in {label!r}",
    )


def check_label(label: str) -> LabelVerdict:  # noqa: PLR0911 - one branch per rule
    """Check ``label`` and return a verdict.  Never raises for a bad label.

    The checks run in a fixed order and the *first* failure is reported, so a rejection
    always names one cause.  Gazetteer before verb: for a thing-or-place label
    (``"haul truck"``, ``"north pit"``) the informative answer is *"that is a piece of
    equipment"*, not *"that has no verb in it"*.
    """
    text = normalise_label(label)
    if not text:
        return LabelVerdict(label=label, ok=False, reason="empty", detail="blank label")
    if len(text) < MIN_LABEL_CHARS:
        return LabelVerdict(
            label=label,
            ok=False,
            reason="too_short",
            detail=f"{len(text)} chars, minimum {MIN_LABEL_CHARS}",
        )
    if len(text) > MAX_LABEL_CHARS:
        return LabelVerdict(
            label=label,
            ok=False,
            reason="too_long",
            detail=f"{len(text)} chars, maximum {MAX_LABEL_CHARS}",
        )
    if text != text.lower():
        offending = next((t for t in text.split() if t != t.lower()), text)
        return LabelVerdict(
            label=label,
            ok=False,
            reason="not_lowercase",
            detail=(
                f"{offending!r} is capitalised; archival labels are lowercase because a "
                "capital is nearly always a proper noun, and proper nouns churn"
            ),
        )
    if not _ALLOWED_RE.match(text):
        return LabelVerdict(
            label=label,
            ok=False,
            reason="illegal_character",
            detail="labels use lowercase letters, spaces, hyphens and apostrophes only",
        )
    tokens = _TOKEN_RE.findall(text)
    if not tokens:
        return LabelVerdict(label=label, ok=False, reason="empty", detail="no tokens")
    if len(tokens) > MAX_LABEL_TOKENS:
        return LabelVerdict(
            label=label,
            ok=False,
            reason="too_many_tokens",
            detail=f"{len(tokens)} tokens, maximum {MAX_LABEL_TOKENS}",
        )
    for token in tokens:
        if _DIGIT_RE.search(token) and token not in CHEMICAL_TOKENS:
            return LabelVerdict(
                label=label,
                ok=False,
                reason="asset_tag",
                detail=(
                    f"{token!r} carries a digit; asset tags and level numbers are the "
                    "churn a functional scheme exists to outlive"
                ),
            )
    hit = _gazetteer_hit(tokens)
    if hit is not None:
        return LabelVerdict(
            label=label,
            ok=False,
            reason="equipment_or_place_term",
            detail=f"{hit!r} names a thing or a place, not work performed",
        )
    return _verb_verdict(label, tokens)


def validate_label(label: str, *, where: str = "activity label") -> str:
    """Return the normalised label, or raise :class:`LabelRejected`.

    The strict entry point.  Used where a bad label must stop the process — the level-1
    register loader and node construction — as opposed to induction, which collects
    verdicts so the rejection *rate* becomes part of the version record.
    """
    verdict = check_label(label)
    if not verdict.ok:
        raise LabelRejected(
            f"{where} does not name a function performed",
            label=label,
            reason=verdict.reason,
            detail=verdict.detail,
        )
    return normalise_label(label)
