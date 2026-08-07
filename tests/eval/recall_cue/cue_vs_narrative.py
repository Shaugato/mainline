# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""Cue vs narrative — the genuinely open question, made callable by the ablation runner.

recall.md risk 2 states it plainly: *cues may not beat contextualised narratives in this
domain*.  The mitigation is to build both and let the ablation decide, which requires the
``V-narrative`` arm of ``trappoint_recall.eval.ablation.DEFAULT_MATRIX`` to be able to ask
one question — *what text would this subject contribute under genre X?* — without
reimplementing the cue pipeline or knowing anything about it.

This module answers exactly that question, and deliberately does not answer any other.

**Report only.  No threshold.  No verdict.**  Every number below is a *description of the
texts*, computed with no model, no vectors and no retrieval: coverage, length, anchor
density, and a token-overlap proxy for genre symmetry between the query side and the
document side.  None of them is evidence that one genre retrieves better — that claim needs
the harness, the gold sets and a Wilson interval, and it belongs to ``recall-eval-harness``.
A stub that shipped a threshold would be a retrieval claim made by the component under test,
which is the exact self-certification the domain plan bans elsewhere.

The overlap proxy in particular is worth naming honestly: **lexical overlap is not cosine
similarity.**  It is a cheap, deterministic, offline statistic that shows whether the two
sides are speaking the same *kind* of sentence.  It cannot show that they are close in an
embedding space, and nothing here says it can.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from typing import Any, Final, Literal, Protocol

from mainline_recall_agent.cue.anchors import extract_anchors
from mainline_recall_agent.cue.schema import SYNTHESISED_FACETS, CueOutcome

__all__ = [
    "GENRES",
    "CueVsNarrativeReport",
    "GenreSample",
    "GenreStats",
    "PairOverlap",
    "compare_genres",
    "genre_probe",
    "genre_texts",
    "subject_tokens",
]

Genre = Literal["cue", "narrative"]

GENRES: Final[tuple[Genre, ...]] = ("cue", "narrative")

#: Identifier-preserving tokenisation: ``K-401`` and ``H2S`` stay whole.  The same choice
#: channel D makes, and for the same reason — the identifiers are the job.
_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9%/.\-]*")

#: Function words carry no genre information and would inflate every overlap figure toward
#: each other, which is the one thing this comparison must not do.
_STOPWORDS: Final[frozenset[str]] = frozenset(
    """a an and are as at be been before being between by during for from had has have if in
    into is it its no not of on or over per shall should so than that the their then there
    these this to under until up upon was were when where which while who whom will with
    within without would""".split()
)


class ArmLike(Protocol):
    """The one field of ``AblationArm`` this module reads.

    Structural rather than a hard import so the stub is usable from a bare checkout where
    ``trappoint-recall`` has not been installed — and so that the ablation runner, not this
    module, stays the owner of what an arm is.
    """

    @property
    def embedding_genre(self) -> str: ...


def genre_texts(outcome: CueOutcome, *, genre: Genre) -> tuple[str, ...]:
    """The texts this subject would contribute to the index under ``genre``.

    ``cue``
        the four synthesised facets, in the fixed facet order, already wrapped in the D3
        embedding template.
    ``narrative``
        the raw-text safety net alone, wrapped in the *same* template — the contextual
        prefix stays on, because the ablation's question is "cue or narrative", not "cue or
        no contextual retrieval".  Conflating the two would attribute the contextual-prefix
        win to the cue design.

    Rows are de-duplicated across archival levels: the Level-Materialised Bond writes the
    same text into several trees, and counting it several times would make cue coverage look
    like a function of taxonomy depth.
    """
    if genre not in GENRES:
        raise ValueError(f"unknown embedding genre {genre!r}; known: {list(GENRES)}")
    wanted = SYNTHESISED_FACETS if genre == "cue" else ("narrative",)
    seen: list[str] = []
    for facet in wanted:
        for row in outcome.rows_for(facet):
            if row.embed_text not in seen:
                seen.append(row.embed_text)
    return tuple(seen)


def genre_probe(arm: ArmLike) -> Callable[[CueOutcome], tuple[str, ...]]:
    """The hook a ``BackendFactory`` calls: arm in, text selector out.

    ``run_ablation`` hands each :class:`ArmLike` to a factory owned by whoever built the
    retrieval stack.  That factory calls this to decide *what text this arm indexes*, so the
    cue-vs-narrative knob has one implementation instead of one per backend.
    """
    genre = arm.embedding_genre
    if genre not in GENRES:
        raise ValueError(
            f"arm declares embedding_genre {genre!r}, which this probe does not implement; "
            f"known genres: {list(GENRES)}"
        )
    resolved: Genre = "cue" if genre == "cue" else "narrative"
    return lambda outcome: genre_texts(outcome, genre=resolved)


def subject_tokens(texts: Iterable[str]) -> frozenset[str]:
    """Content tokens of a subject's texts, lowercased, stopwords removed."""
    tokens = {
        token.lower()
        for text in texts
        for token in _TOKEN.findall(text)
        if token.lower() not in _STOPWORDS and len(token) > 1
    }
    return frozenset(tokens)


@dataclass(frozen=True, slots=True)
class GenreSample:
    """One subject under one genre."""

    subject_ref: str
    subject_kind: str
    genre: Genre
    texts: tuple[str, ...]

    @property
    def chars(self) -> int:
        return sum(len(text) for text in self.texts)

    @property
    def anchor_count(self) -> int:
        return sum(len(extract_anchors(text)) for text in self.texts)

    @property
    def tokens(self) -> frozenset[str]:
        return subject_tokens(self.texts)


@dataclass(frozen=True, slots=True)
class GenreStats:
    """Descriptive statistics for one genre over a sample. No verdict attached."""

    genre: Genre
    subjects: int
    texts_per_subject_mean: float
    chars_per_text_mean: float
    anchors_per_subject_mean: float
    subjects_with_no_text: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "genre": self.genre,
            "subjects": self.subjects,
            "texts_per_subject_mean": self.texts_per_subject_mean,
            "chars_per_text_mean": self.chars_per_text_mean,
            "anchors_per_subject_mean": self.anchors_per_subject_mean,
            "subjects_with_no_text": self.subjects_with_no_text,
        }


@dataclass(frozen=True, slots=True)
class PairOverlap:
    """Token overlap between one exposure subject and one event subject, per genre.

    Jaccard over identifier-preserving content tokens.  A *proxy* for genre symmetry, not a
    similarity: see the module docstring.
    """

    exposure_ref: str
    event_ref: str
    cue_jaccard: float
    narrative_jaccard: float

    @property
    def delta(self) -> float:
        return self.cue_jaccard - self.narrative_jaccard

    def to_dict(self) -> dict[str, Any]:
        return {
            "exposure_ref": self.exposure_ref,
            "event_ref": self.event_ref,
            "cue_jaccard": self.cue_jaccard,
            "narrative_jaccard": self.narrative_jaccard,
            "delta": self.delta,
        }


def _jaccard(left: frozenset[str], right: frozenset[str]) -> float:
    if not left and not right:
        return 0.0
    union = len(left | right)
    return len(left & right) / union if union else 0.0


def _mean(values: Sequence[float]) -> float:
    return math.fsum(values) / len(values) if values else 0.0


def _stats(genre: Genre, samples: Sequence[GenreSample]) -> GenreStats:
    per_text_chars = [float(len(text)) for sample in samples for text in sample.texts]
    return GenreStats(
        genre=genre,
        subjects=len(samples),
        texts_per_subject_mean=_mean([float(len(s.texts)) for s in samples]),
        chars_per_text_mean=_mean(per_text_chars),
        anchors_per_subject_mean=_mean([float(s.anchor_count) for s in samples]),
        subjects_with_no_text=sum(1 for s in samples if not s.texts),
    )


@dataclass(frozen=True, slots=True)
class CueVsNarrativeReport:
    """The artefact.  Descriptive, unthresholded, and honest about what it is not."""

    label: str
    stats: tuple[GenreStats, ...]
    pairs: tuple[PairOverlap, ...]
    notes: tuple[str, ...]

    def stats_for(self, genre: Genre) -> GenreStats:
        for entry in self.stats:
            if entry.genre == genre:
                return entry
        raise KeyError(genre)

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "stats": [s.to_dict() for s in self.stats],
            "pairs": [p.to_dict() for p in self.pairs],
            "notes": list(self.notes),
        }

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True) + "\n"

    def to_markdown(self) -> str:
        lines = [
            f"# Cue vs narrative — descriptive comparison ({self.label})",
            "",
            "Report only. No threshold, no verdict, no retrieval claim. Every figure below "
            "describes the *texts*; whether one genre retrieves better is measured by the "
            "recall harness against the gold sets, with intervals.",
            "",
            "| genre | subjects | texts/subject | chars/text | anchors/subject | empty |",
            "|---|---|---|---|---|---|",
        ]
        for entry in self.stats:
            lines.append(
                f"| {entry.genre} | {entry.subjects} | {entry.texts_per_subject_mean:.2f} | "
                f"{entry.chars_per_text_mean:.1f} | {entry.anchors_per_subject_mean:.2f} | "
                f"{entry.subjects_with_no_text} |"
            )
        if self.pairs:
            lines += [
                "",
                "## Query/document token overlap (Jaccard, identifier-preserving)",
                "",
                "A proxy for genre symmetry, not a similarity. Lexical overlap is not cosine.",
                "",
                "| exposure | event | cue | narrative | delta |",
                "|---|---|---|---|---|",
            ]
            for pair in self.pairs:
                lines.append(
                    f"| {pair.exposure_ref} | {pair.event_ref} | {pair.cue_jaccard:.4f} | "
                    f"{pair.narrative_jaccard:.4f} | {pair.delta:+.4f} |"
                )
        if self.notes:
            lines += ["", "## Notes", ""]
            lines += [f"- {note}" for note in self.notes]
        lines.append("")
        return "\n".join(lines)


def compare_genres(
    outcomes: Sequence[CueOutcome],
    *,
    pairs: Sequence[tuple[str, str]] = (),
    label: str = "unlabelled",
) -> CueVsNarrativeReport:
    """Describe a set of cue outcomes under both genres.

    ``pairs`` names ``(exposure_ref, event_ref)`` couples to compute the overlap proxy over.
    It is supplied by the caller rather than inferred, because "which event is a precursor
    of which permit" is gold-set knowledge and this module has no business guessing it.
    """
    by_ref = {outcome.subject_ref: outcome for outcome in outcomes}
    samples: dict[Genre, list[GenreSample]] = {genre: [] for genre in GENRES}
    for outcome in outcomes:
        for genre in GENRES:
            samples[genre].append(
                GenreSample(
                    subject_ref=outcome.subject_ref,
                    subject_kind=outcome.subject_kind,
                    genre=genre,
                    texts=genre_texts(outcome, genre=genre),
                )
            )

    overlaps: list[PairOverlap] = []
    for exposure_ref, event_ref in pairs:
        missing = [ref for ref in (exposure_ref, event_ref) if ref not in by_ref]
        if missing:
            raise KeyError(f"pair names subjects absent from the sample: {missing}")
        exposure, event = by_ref[exposure_ref], by_ref[event_ref]
        overlaps.append(
            PairOverlap(
                exposure_ref=exposure_ref,
                event_ref=event_ref,
                cue_jaccard=_jaccard(
                    subject_tokens(genre_texts(exposure, genre="cue")),
                    subject_tokens(genre_texts(event, genre="cue")),
                ),
                narrative_jaccard=_jaccard(
                    subject_tokens(genre_texts(exposure, genre="narrative")),
                    subject_tokens(genre_texts(event, genre="narrative")),
                ),
            )
        )

    notes = [
        "Report only: no threshold and no verdict. Whether cues beat contextualised "
        "narratives in this domain is an open question, and it is answered by the recall "
        "harness against the gold sets, not here.",
        "Token overlap is a deterministic proxy for genre symmetry. It is not cosine "
        "similarity and it is not evidence of retrieval quality.",
        "Both genres are wrapped in the same D3 embedding template, so the contextual "
        "prefix is held constant and its effect is not attributed to the cue design.",
        "Anchor counts come from the same gazetteer that rejects fabricated particulars, "
        "so a genre with more anchors is a genre with more checkable claims - which cuts "
        "both ways and is reported rather than scored.",
    ]
    silenced = [o.subject_ref for o in outcomes if o.status == "silenced"]
    if silenced:
        notes.append(
            "Silenced subjects contribute no text under either genre and are counted in "
            f"'empty': {sorted(silenced)}."
        )
    return CueVsNarrativeReport(
        label=label,
        stats=tuple(_stats(genre, samples[genre]) for genre in GENRES),
        pairs=tuple(overlaps),
        notes=tuple(notes),
    )
