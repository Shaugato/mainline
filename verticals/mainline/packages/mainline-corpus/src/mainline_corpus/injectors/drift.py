# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Injector 8 — vocabulary drift, 2004 to 2026, as a dated term-substitution schedule.

**Proves:** why lexical-only retrieval fails across twenty-two years and why the vector index
earns its place.  The claim is *measured*, not asserted: ``corpus-embed-lift`` computes lexical
recall@5 against semantic recall@5 over the pairs this module emits and writes ``drift_margin``
into the lock, and the film only speaks the line if that margin is positive.

Two artefacts, and they have different consumers:

``vocabulary_drift.jsonl``  the **schedule**: one row per (concept, era) with the surface form
                            in force, the form it replaced, and the date from which a document
                            written at this site uses it.  ``corpus-render-cache``'s template
                            tier reads this to write a 2005 document in 2005 language and a 2025
                            document in 2025 language.  A renderer that reached for the current
                            surface form every time would produce a corpus with no drift in it
                            at all, and the measurement below would come out at zero for a
                            reason nobody would notice.

``drift_pairs.jsonl``       the **measurement set**: one row per (concept, early era, late era)
                            carrying the two surface forms, their era dates, and the count of
                            shared content tokens.  ``shared_tokens`` is the honest column.  The
                            era table in ``phrases.yaml`` deliberately keeps "near" across two
                            eras of ``near_miss`` and "change" across all four of
                            ``management_of_change``; a pair set where every pair is lexically
                            disjoint would overstate the margin, and a measurement built on an
                            overstated set is worse than no measurement.

Nothing is invented here.  Every surface form comes from ``phrases.yaml``, which is where the
gazetteer keeps the era-banded vocabulary, and this module only dates it and pairs it up.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from .. import gazetteer as gaz
from ..blame import params
from ..skeleton import clock

__all__ = ["ERA_START", "pair_rows", "schedule_rows", "shared_tokens"]

#: Tokens that carry no topical signal and must not count as lexical overlap.  Kept small and
#: explicit: a long stop list would let a genuinely-shared content word be discarded, which
#: would flatter the drift measurement in the direction we are trying not to flatter it.
_STOP: frozenset[str] = frozenset({"a", "an", "and", "of", "the", "to", "for", "in", "on"})

#: The first day of an era, derived from ``phrases.yaml``'s ``from`` year.  A document effective
#: on or after this date is written in that era's vocabulary.
ERA_START = "era_start"


def _eras() -> tuple[tuple[str, int, int, str], ...]:
    phrases = gaz.load("phrases")
    return tuple(
        (str(entry["key"]), int(entry["from"]), int(entry["to"]), str(entry["label"]))
        for entry in gaz.as_sequence(phrases, "eras", origin="phrases.yaml")
    )


def _concepts() -> tuple[tuple[str, dict[str, str]], ...]:
    phrases = gaz.load("phrases")
    out: list[tuple[str, dict[str, str]]] = []
    for entry in gaz.as_sequence(phrases, "concepts", origin="phrases.yaml"):
        surfaces = {str(key): str(value) for key, value in entry.items() if key != "key"}
        out.append((str(entry["key"]), surfaces))
    return tuple(sorted(out, key=lambda item: item[0]))


def shared_tokens(left: str, right: str) -> tuple[str, ...]:
    """Content tokens two surface forms have in common, lower-cased, stop words removed."""

    def _tokens(text: str) -> set[str]:
        return {word for word in text.lower().split() if word not in _STOP}

    return tuple(sorted(_tokens(left) & _tokens(right)))


def schedule_rows() -> list[dict[str, Any]]:
    """Emit the dated substitution schedule the renderer consumes."""
    eras = _eras()
    rows: list[dict[str, Any]] = []
    for concept, surfaces in _concepts():
        previous: str | None = None
        for index, (era_key, from_year, to_year, label) in enumerate(eras):
            surface = surfaces.get(era_key)
            if surface is None:
                raise gaz.GazetteerError(
                    f"phrases.yaml: concept {concept!r} has no surface form for era {era_key!r}; "
                    "a gap in the era table is a year in which the renderer has no word to use "
                    "and would silently fall back to the current one"
                )
            rows.append(
                {
                    "concept": concept,
                    "effective_from": clock.iso_date(dt.date(from_year, 1, 1)),
                    "effective_to": clock.iso_date(dt.date(to_year, 12, 31)),
                    "era": era_key,
                    "era_index": index + 1,
                    "era_label": label,
                    "replaces": previous,
                    "surface": surface,
                }
            )
            previous = surface
    rows.sort(key=lambda row: (row["concept"], row["era_index"]))
    return rows


def pair_rows() -> list[dict[str, Any]]:
    """Dated drift pairs for the lexical-versus-semantic measurement.

    A pair is emitted for every ordered era gap of at least ``DRIFT_PAIR_ERA_GAP``, so the set
    spans "one generation apart" as well as "the whole window".  Pairs whose two forms are
    identical are not emitted: a concept that did not drift is not evidence about drift.
    """
    eras = _eras()
    index_of = {key: position for position, (key, _from, _to, _label) in enumerate(eras)}
    rows: list[dict[str, Any]] = []
    for concept, surfaces in _concepts():
        for early_key, early_from, _early_to, _early_label in eras:
            for late_key, late_from, _late_to, _late_label in eras:
                gap = index_of[late_key] - index_of[early_key]
                if gap < params.DRIFT_PAIR_ERA_GAP:
                    continue
                early = surfaces[early_key]
                late = surfaces[late_key]
                if early == late:
                    continue
                overlap = shared_tokens(early, late)
                rows.append(
                    {
                        "concept": concept,
                        "early_era": early_key,
                        "early_surface": early,
                        "early_year": early_from,
                        "era_gap": gap,
                        "late_era": late_key,
                        "late_surface": late,
                        "late_year": late_from,
                        "lexically_disjoint": not overlap,
                        "pair_key": f"{concept}:{early_key}->{late_key}",
                        "shared_tokens": list(overlap),
                    }
                )
    rows.sort(key=lambda row: row["pair_key"])
    if not rows:
        raise gaz.GazetteerError(
            "the era table produced no drift pairs. The corpus's claim that lexical retrieval "
            "fails across twenty-two years would then be untestable, and corpus-embed-lift's "
            "drift_margin would be computed over an empty set."
        )
    return rows
