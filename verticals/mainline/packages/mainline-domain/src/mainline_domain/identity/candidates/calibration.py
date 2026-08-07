# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Where the S-curve knee actually sits, measured rather than remembered.

The banding parameters (16 bands x 8 rows) come with an analytic promise:
``P(share ≥ 1 band) = 1 - (1 - J**8)**16``, with the knee at
``(1/16)**(1/8) = 0.7071``.  That promise is about *shingle-set Jaccard*.  What
the product cares about is *edits to procedure text*, and nothing guarantees
that the two line up on real clauses — 5-gram character shingles over a
dense engineering sentence do not distribute like the uniform sets the
derivation assumes.

So this module does three things and claims nothing beyond them:

* :func:`mutate` applies **labelled, deterministic** edits to a clause — the
  reflow-class mutations (whitespace, punctuation, synonym substitution,
  sentence reorder) that a re-templating produces, and which SURVIVE means the
  identity must hold through;
* :func:`labelled_pairs` builds a corpus of such pairs with their **true**
  Jaccard computed exactly, so every measurement is against ground truth rather
  than against another estimate;
* :func:`band_recall_curve` reports observed band recall per Jaccard bucket
  beside the analytic prediction, so a discrepancy is visible as a number
  instead of being discovered as a missed match.

Everything here is seeded and deterministic: the same seed produces the same
corpus in any process, on any platform, forever.  A calibration harness whose
corpus changes between runs measures nothing.

This is calibration tooling, not a stage.  Nothing in the cascade imports it.
"""

from __future__ import annotations

import random
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Final, Literal

from .band import band_hashes
from .minhash import (
    MinHashParams,
    default_params,
    exact_jaccard,
    s_curve_probability,
    signature,
)

__all__ = [
    "MUTATION_CLASSES",
    "BandRecallBucket",
    "LabelledPair",
    "MutationClass",
    "band_recall_curve",
    "labelled_pairs",
    "mutate",
    "synthetic_clause",
]

MutationClass = Literal[
    "whitespace",
    "punctuation",
    "synonym",
    "reorder",
    "insert_hedge",
    "drop_sentence",
    "rewrite",
]

MUTATION_CLASSES: Final[tuple[MutationClass, ...]] = (
    "whitespace",
    "punctuation",
    "synonym",
    "reorder",
    "insert_hedge",
    "drop_sentence",
    "rewrite",
)
"""Ordered from *should not change identity* to *should not preserve it*.

The first four are reflow: a re-typeset document produces them and the matcher
must survive them.  ``insert_hedge`` and ``drop_sentence`` are real edits with
real Jaccard cost.  ``rewrite`` is the far end — deliberately included so the
curve has points below the knee and the low-Jaccard end of the measurement is
not extrapolated.
"""

_SUBJECTS: Final[tuple[str, ...]] = (
    "the authorised person",
    "the permit issuer",
    "the isolation officer",
    "the area supervisor",
    "the authorised gas tester",
)
_VERBS: Final[tuple[str, ...]] = (
    "shall isolate",
    "shall verify",
    "shall confirm",
    "shall record",
    "shall witness",
)
_OBJECTS: Final[tuple[str, ...]] = (
    "pump P-101A at ISOL-4471",
    "vessel TK-204 at ISOL-3312",
    "compressor C-330B at ISOL-7781",
    "line 6-PG-1042 at ISOL-2290",
)
_TAILS: Final[tuple[str, ...]] = (
    "before breaking containment",
    "prior to entry into the confined space",
    "before the hot work permit is issued",
    "before any energy source is restored",
)
_CHECKS: Final[tuple[str, ...]] = (
    "The isolation shall be verified at PIT-1204 and recorded on the permit.",
    "A second signature is required on the isolation certificate.",
    "The gas test result shall be below 5 percent LEL before entry.",
    "The hold point shall not be released without the issuing authority present.",
)

_SYNONYMS: Final[tuple[tuple[str, str], ...]] = (
    ("before", "prior to"),
    ("shall verify", "shall check"),
    ("confirm", "establish"),
    ("record", "log"),
    ("required", "mandatory"),
)

_HEDGES: Final[tuple[str, ...]] = (
    " where practicable",
    " at the supervisor's discretion",
    " so far as is reasonably practicable",
)


def synthetic_clause(rng: random.Random) -> str:
    """One clause-shaped sentence pair, drawn from the committed vocabulary.

    Clause-*shaped* is the point: character 5-grams over "shall isolate pump
    P-101A at ISOL-4471" behave nothing like 5-grams over English prose,
    because the tags and the deontic boilerplate dominate the shingle set.  A
    calibration corpus of Lorem Ipsum would measure the wrong distribution and
    would do it convincingly.
    """
    head = (
        f"{rng.choice(_SUBJECTS)} {rng.choice(_VERBS)} {rng.choice(_OBJECTS)} {rng.choice(_TAILS)}."
    )
    return f"{head} {rng.choice(_CHECKS)}"


def _sentences(text: str) -> list[str]:
    parts = [p.strip() for p in text.split(". ")]
    return [p if p.endswith(".") else p + "." for p in parts if p]


#: A mutation that needs at least this many sentences to be applicable at all;
#: below it the mutation is a no-op and the pair is discarded by
#: :func:`labelled_pairs` rather than being labelled with a mutation that did
#: not happen.
_MIN_SENTENCES: Final[int] = 2

#: A bucket needs a lower and an upper edge.
_MIN_BUCKET_EDGES: Final[int] = 2


def _mutate_whitespace(text: str, _rng: random.Random) -> str:
    return text.replace(" ", "  ", 1).replace(". ", ".  ", 1)


def _mutate_punctuation(text: str, _rng: random.Random) -> str:
    return text.replace(".", ";", 1)


def _mutate_synonym(text: str, _rng: random.Random) -> str:
    for old, new in _SYNONYMS:
        if old in text:
            return text.replace(old, new, 1)
    return text


def _mutate_reorder(text: str, _rng: random.Random) -> str:
    parts = _sentences(text)
    if len(parts) < _MIN_SENTENCES:
        return text
    return " ".join(parts[1:] + parts[:1])


def _mutate_insert_hedge(text: str, rng: random.Random) -> str:
    parts = _sentences(text)
    parts[0] = parts[0][:-1] + rng.choice(_HEDGES) + "."
    return " ".join(parts)


def _mutate_drop_sentence(text: str, _rng: random.Random) -> str:
    parts = _sentences(text)
    if len(parts) < _MIN_SENTENCES:
        return text
    return " ".join(parts[:-1])


def _mutate_rewrite(_text: str, rng: random.Random) -> str:
    """Keep nothing but the shape: the far end of the curve."""
    return (
        f"{rng.choice(_SUBJECTS)} {rng.choice(_VERBS)} {rng.choice(_OBJECTS)} "
        f"{rng.choice(_TAILS)}. {rng.choice(_CHECKS)}"
    )


_MUTATORS: Final[dict[str, Callable[[str, random.Random], str]]] = {
    "whitespace": _mutate_whitespace,
    "punctuation": _mutate_punctuation,
    "synonym": _mutate_synonym,
    "reorder": _mutate_reorder,
    "insert_hedge": _mutate_insert_hedge,
    "drop_sentence": _mutate_drop_sentence,
    "rewrite": _mutate_rewrite,
}


def mutate(text: str, kind: MutationClass, rng: random.Random) -> str:
    """Apply one labelled mutation.  Deterministic given ``rng``'s state."""
    return _MUTATORS[kind](text, rng)


@dataclass(frozen=True, slots=True)
class LabelledPair:
    """One near-duplicate pair with its mutation class and its true Jaccard."""

    left: str
    right: str
    mutation: MutationClass
    true_jaccard: float
    shares_band: bool
    shared_bands: int


def labelled_pairs(
    *,
    seed: int,
    count: int,
    params: MinHashParams | None = None,
    mutations: Sequence[MutationClass] = MUTATION_CLASSES,
) -> tuple[LabelledPair, ...]:
    """Build ``count`` pairs per mutation class, each labelled with true Jaccard.

    Ground truth is :func:`~.minhash.exact_jaccard` — the real set similarity,
    computed exhaustively.  Every claim about band recall in this package is
    measured against that, never against the MinHash estimate, because
    measuring an estimator against itself is how a calibration harness reports
    100 % and means nothing.
    """
    p = params if params is not None else default_params()
    rng = random.Random(seed)  # noqa: S311  (corpus generation, not cryptography)
    out: list[LabelledPair] = []
    for kind in mutations:
        for _ in range(count):
            left = synthetic_clause(rng)
            right = mutate(left, kind, rng)
            if left == right:
                continue
            left_bands = band_hashes(signature(left, p), p)
            right_bands = band_hashes(signature(right, p), p)
            shared = sum(1 for a, b in zip(left_bands, right_bands, strict=True) if a == b)
            out.append(
                LabelledPair(
                    left=left,
                    right=right,
                    mutation=kind,
                    true_jaccard=exact_jaccard(left, right, p.shingle_size),
                    shares_band=shared > 0,
                    shared_bands=shared,
                )
            )
    return tuple(out)


@dataclass(frozen=True, slots=True)
class BandRecallBucket:
    """Observed band recall in one Jaccard bucket, beside the analytic prediction."""

    lower: float
    upper: float
    pairs: int
    recalled: int

    @property
    def observed(self) -> float:
        """Fraction of pairs in this bucket that shared at least one band."""
        return self.recalled / self.pairs if self.pairs else 0.0

    def predicted(self, bands: int, rows_per_band: int) -> float:
        """Return the S-curve value at the bucket midpoint."""
        return s_curve_probability((self.lower + self.upper) / 2, bands, rows_per_band)


def band_recall_curve(
    pairs: Sequence[LabelledPair],
    *,
    edges: Sequence[float] = (0.0, 0.3, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0),
) -> tuple[BandRecallBucket, ...]:
    """Bucket labelled pairs by true Jaccard and report band recall in each.

    Buckets are half-open ``[lower, upper)`` except the last, which is closed so
    that an exact 1.0 (identical shingle sets under different text) lands
    somewhere rather than vanishing.  Empty buckets are returned with
    ``pairs=0`` rather than omitted: a bucket with no data is a fact about the
    corpus and hiding it would let a thin corpus look like a complete curve.
    """
    if len(edges) < _MIN_BUCKET_EDGES:
        raise ValueError("need at least two bucket edges")
    buckets: list[BandRecallBucket] = []
    for i in range(len(edges) - 1):
        lower, upper = edges[i], edges[i + 1]
        last = i == len(edges) - _MIN_SENTENCES

        def _inside(
            value: float,
            lo: float = lower,
            hi: float = upper,
            closed: bool = last,
        ) -> bool:
            return lo <= value <= hi if closed else lo <= value < hi

        members = [p for p in pairs if _inside(p.true_jaccard)]
        buckets.append(
            BandRecallBucket(
                lower=lower,
                upper=upper,
                pairs=len(members),
                recalled=sum(1 for p in members if p.shares_band),
            )
        )
    return tuple(buckets)
