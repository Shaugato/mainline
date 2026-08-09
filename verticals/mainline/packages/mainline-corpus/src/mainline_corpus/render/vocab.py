# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Era vocabulary, control-class wording, and the small phrase tables the renderers share.

The dated substitution schedule ``injector_vocabulary_drift.jsonl`` is the whole reason the
corpus can *measure* the claim "lexical retrieval fails across twenty-two years, semantic
retrieval does not".  ``corpus-blame-key`` emits the schedule; this module is the consumer the
schedule was written for.

A renderer that reached for today's surface form every time would produce a corpus with no
drift in it, ``corpus-embed-lift``'s ``drift_margin`` would come out near zero, and the film's
line about lexical-only search would have to be cut for a reason nobody could name.  So the
lookup is by *date*: a 2005 record says "danger tagging", a 2024 record says "positive
isolation verification", and they are the same duty.

Every literal below comes from the gazetteer.  Nothing here invents a word.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping, Sequence
from functools import cache
from typing import Any, Final

from .. import gazetteer as gaz

__all__ = [
    "CONCEPTS_FOR_KIND",
    "control_label",
    "era_for",
    "failure_phrase",
    "hazard_media",
    "hazard_release",
    "icam_tier_phrase",
    "surfaces_for",
    "title_case",
]

#: The concepts each node kind is allowed to reach for.  Restricted on purpose: the era table
#: has sixteen concepts and putting all of them into every node's facts would add ~2.7 MB of
#: identical vocabulary across the committed cache without changing a word of the output.
CONCEPTS_FOR_KIND: Final[dict[str, tuple[str, ...]]] = {
    "event_narrative": ("critical_control", "investigation", "near_miss", "verification"),
    "clause_text": ("critical_control", "energy_isolation", "verification"),
    "moc_justification": ("critical_control", "management_of_change", "verification"),
    "revision_reason": ("investigation", "management_of_change", "near_miss"),
}

#: How a failed control reads in an ICAM finding.  One phrase per ``failure_mode`` the skeleton
#: emits; the vocabulary is closed and a new mode is a build error rather than a silent default.
_FAILURE_PHRASE: Final[dict[str, str]] = {
    "absent": "was not in place",
    "bypassed": "had been bypassed",
    "degraded": "had degraded below its design intent",
    "ineffective": "was in place but did not perform",
    "not_verified": "was never verified as effective",
}

#: How an ICAM tier reads in a sentence.
_TIER_PHRASE: Final[dict[str, str]] = {
    "absent_or_failed_defence": "an absent or failed defence",
    "individual_or_team_action": "an individual or team action",
    "organisational_factor": "an organisational factor",
    "task_or_environmental_condition": "a task or environmental condition",
}


@cache
def _era_table() -> tuple[tuple[dt.date, dt.date, str, str], ...]:
    """``(from, to, era_key, era_label)`` for each era, from ``phrases.yaml``."""
    phrases = gaz.load("phrases")
    rows = []
    for entry in gaz.as_sequence(phrases, "eras", origin="phrases.yaml"):
        rows.append(
            (
                dt.date(int(entry["from"]), 1, 1),
                dt.date(int(entry["to"]), 12, 31),
                str(entry["key"]),
                str(entry["label"]),
            )
        )
    return tuple(sorted(rows))


@cache
def _concept_table() -> dict[str, dict[str, str]]:
    """``{concept: {era_key: surface}}`` from ``phrases.yaml``."""
    phrases = gaz.load("phrases")
    out: dict[str, dict[str, str]] = {}
    for entry in gaz.as_sequence(phrases, "concepts", origin="phrases.yaml"):
        out[str(entry["key"])] = {
            str(key): str(value) for key, value in entry.items() if key != "key"
        }
    return out


@cache
def _control_table() -> dict[str, Mapping[str, Any]]:
    classes = gaz.load("control_classes")
    return {
        str(entry["key"]): entry
        for entry in gaz.as_sequence(classes, "classes", origin="control_classes.yaml")
    }


@cache
def _energy_table() -> dict[str, Mapping[str, Any]]:
    energies = gaz.load("hazard_energies")
    return {
        str(entry["key"]): entry
        for entry in gaz.as_sequence(energies, "energies", origin="hazard_energies.yaml")
    }


def era_for(on: dt.date | str) -> tuple[str, str]:
    """``(era_key, era_label)`` in force on ``on``.

    A date outside the era table is a refusal rather than a clamp: the corpus spans 2004-2026
    by construction, and a 2031 document would mean an upstream generator broke its own bounds.
    """
    day = dt.date.fromisoformat(on) if isinstance(on, str) else on
    for start, end, key, label in _era_table():
        if start <= day <= end:
            return key, label
    raise ValueError(
        f"{day.isoformat()} falls outside the era table {_era_table()[0][0].year}-"
        f"{_era_table()[-1][1].year}; phrases.yaml has no vocabulary for it"
    )


def surfaces_for(node_kind: str, on: dt.date | str) -> dict[str, str]:
    """Return the surface forms in force on ``on`` for the concepts ``node_kind`` may use."""
    era_key, _label = era_for(on)
    table = _concept_table()
    concepts = CONCEPTS_FOR_KIND.get(node_kind)
    if concepts is None:
        raise ValueError(f"unknown node kind {node_kind!r}")
    out: dict[str, str] = {}
    for concept in concepts:
        surfaces = table.get(concept)
        if surfaces is None or era_key not in surfaces:
            raise ValueError(
                f"phrases.yaml: concept {concept!r} has no surface for era {era_key!r}; the "
                "renderer would silently fall back to the current word and erase the drift"
            )
        out[concept] = surfaces[era_key]
    return out


def control_label(control_class: str) -> str:
    """Return the human wording of a control class, from ``control_classes.yaml``."""
    entry = _control_table().get(control_class)
    if entry is None:
        raise ValueError(
            f"control class {control_class!r} is not in control_classes.yaml. The gazetteer is "
            "the only source of control wording; inventing one here would put a phrase in the "
            "corpus that the anchor extractor cannot match."
        )
    return str(entry["label"])


def hazard_media(energy: str) -> tuple[str, ...]:
    """Return the media through which an energy is stored or released."""
    entry = _energy_table().get(energy)
    if entry is None:
        raise ValueError(f"hazard energy {energy!r} is not in hazard_energies.yaml")
    return tuple(str(item) for item in entry["media"])


def hazard_release(energy: str) -> str:
    """Return how this energy typically presents when released."""
    entry = _energy_table().get(energy)
    if entry is None:
        raise ValueError(f"hazard energy {energy!r} is not in hazard_energies.yaml")
    return str(entry["typical_release"])


def failure_phrase(failure_mode: str) -> str:
    """Return how a failed control reads in a finding sentence."""
    try:
        return _FAILURE_PHRASE[failure_mode]
    except KeyError:
        raise ValueError(
            f"failure mode {failure_mode!r} has no wording. Add it here deliberately rather "
            "than defaulting: a default would render every unknown mode identically and make "
            "two findings collide, which breaks the evidence binding."
        ) from None


def icam_tier_phrase(tier: str) -> str:
    """Return how an ICAM tier reads in a finding sentence."""
    try:
        return _TIER_PHRASE[tier]
    except KeyError:
        raise ValueError(
            f"ICAM tier {tier!r} has no wording in the renderer's phrase table"
        ) from None


def title_case(text: str) -> str:
    """Sentence-case a lower-case generated title without touching asset tags.

    ``str.title()`` would turn ``P-4102`` into ``P-4102`` but also ``OEM`` into ``Oem``; the
    corpus is full of upper-case tags and acronyms, so only the first character moves.
    """
    stripped = text.strip()
    if not stripped:
        return stripped
    return stripped[0].upper() + stripped[1:]


def join_clauses(parts: Sequence[str]) -> str:
    """Join parts as ``"a, b and c"`` — Australian English, no serial comma."""
    items = [part for part in parts if part]
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return f"{', '.join(items[:-1])} and {items[-1]}"
