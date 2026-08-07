# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The 2 000-document fixture and the 200 queries the differential runs.

Generated rather than committed, from a fixed seed and a fixed generator, so that the fixture
is a *function of this file* — reviewable in a diff, reproducible on any machine, and
impossible to accidentally tune by editing a data file until the test goes green.

The corpus is built to exercise the arithmetic at its edges rather than to look realistic:

* **document frequency spans the whole range.**  ``%LEL`` is planted in every document so
  ``df = N`` is exercised; every document carries one tag that appears nowhere else so
  ``df = 1`` is exercised; a 120-tag shared pool and a Zipf-drawn prose vocabulary cover
  everything in between.
* **length varies by more than an order of magnitude** — 3 to 16 sentences — because BM25
  without length normalisation is ``ts_rank``, and a fixture of uniform-length documents
  cannot tell the two apart.
* **every token class appears**: identifiers, quantities, citations, CAS numbers and prose,
  because the SQL scores whatever the analyser produced and a fixture of prose alone would
  never exercise a term containing ``:`` or ``/``.

The 200 queries are four kinds in fixed proportion: single-term, multi-term drawn from a real
document, rare-identifier (the ``df = 1`` tags, which is channel D's whole purpose), and edge
queries mixing an unseen term with a seen one and a ``df = N`` term with a rare one.
"""

from __future__ import annotations

import random
import uuid
from dataclasses import dataclass
from typing import Final

from trappoint_recall.lexical.analyser import analyse_query
from trappoint_recall.lexical.postings import DocumentPostings, build_document_postings

CORPUS_SEED: Final[int] = 20260804
N_DOCUMENTS: Final[int] = 2000
N_QUERIES: Final[int] = 200

_PREFIXES: Final[tuple[str, ...]] = (
    "K", "TK", "CC", "PSV", "FT", "LT", "PT", "MV", "XV", "HV", "P", "C", "E", "D",
)
_HEAD_NOUNS: Final[tuple[str, ...]] = (
    "vessel", "pump", "valve", "compressor", "conveyor", "hoist", "winder", "drill",
    "loader", "excavator", "screen", "thickener", "kiln", "flare", "scrubber", "sump",
)
_VERBS: Final[tuple[str, ...]] = (
    "failed", "leaked", "overpressured", "tripped", "stalled", "ruptured", "collapsed",
    "ignited", "overheated", "seized", "vibrated", "corroded", "cracked", "jammed",
)
_MODIFIERS: Final[tuple[str, ...]] = (
    "during maintenance", "under a hot work permit", "on night shift", "after isolation",
    "before the pre-start check", "while the lock-out was in place", "at the shift handover",
    "without a rescue plan", "with the guard removed", "after a bypass was applied",
)
_CONSEQUENCE: Final[tuple[str, ...]] = (
    "The operator was not injured.",
    "One worker sustained a lost time injury.",
    "The area was evacuated and the atmosphere was monitored.",
    "Production was stopped and the equipment was tagged out.",
    "A fatality occurred and the site was placed under a prohibition notice.",
)
_UNITS: Final[tuple[str, ...]] = (
    "10 ppm", "25 %LEL", "100 psi", "689 kPa", "50 °C", "30 min", "1.2e-3 m3/h",
    "40 µg/m3", "5 bar", "1450 rpm", "0.1 %", "-5 °C", "120 degF", "30 psig",
)
_CITATIONS: Final[tuple[str, ...]] = (
    "30 CFR 57.22239", "29 CFR 1910.146", "AS/NZS 3000", "ISO 45001", "ASME B31.3",
    "API RP 754", "NFPA 70E", "WHS Regulation 2011 r 341", "§ 57.22239(a)",
)
_CAS: Final[tuple[str, ...]] = (
    "7783-06-4", "71-43-2", "1333-74-0", "74-82-8", "7664-41-7", "630-08-0",
)
#: Planted in every document so that ``df = N`` is a case the differential actually reaches.
_UBIQUITOUS: Final[str] = "%LEL"
#: A token no generator above can produce, and one that survives the analyser intact: it must
#: be a single prose word, because a hyphenated one such as ``zzzz-nonexistent-tag`` also emits
#: its components and ``tag`` is all over an incident corpus. An "unseen term" that is not
#: unseen makes the test that uses it assert nothing.
_UNSEEN: Final[str] = "qqqqzzzz"


@dataclass(frozen=True, slots=True)
class Fixture:
    site_id: str
    other_site_id: str
    texts: dict[str, str]
    documents: tuple[DocumentPostings, ...]
    queries: tuple[tuple[str, str], ...]  # (kind, query text)
    unique_tags: tuple[str, ...]


def _zipf_choice(rng: random.Random, items: tuple[str, ...]) -> str:
    """Rank-biased choice, so prose document frequencies are not uniform."""
    weights = [1.0 / (i + 1) for i in range(len(items))]
    return rng.choices(items, weights=weights, k=1)[0]


def _sentence(rng: random.Random, tag: str) -> str:
    parts = [
        f"{_zipf_choice(rng, _HEAD_NOUNS).capitalize()} {tag}",
        _zipf_choice(rng, _VERBS),
        _zipf_choice(rng, _MODIFIERS),
    ]
    if rng.random() < 0.55:
        parts.append("at " + rng.choice(_UNITS))
    return " ".join(parts) + "."


def build_fixture(
    *, n_documents: int = N_DOCUMENTS, n_queries: int = N_QUERIES, seed: int = CORPUS_SEED
) -> Fixture:
    rng = random.Random(seed)
    site_id = str(uuid.UUID(int=rng.getrandbits(128), version=4))
    other_site_id = str(uuid.UUID(int=rng.getrandbits(128), version=4))

    # A pool of shared tags (many documents) and one unique tag per document (df = 1).
    shared_tags = tuple(
        f"{rng.choice(_PREFIXES)}-{rng.randint(100, 999)}" for _ in range(120)
    )
    unique_tags: list[str] = []
    texts: dict[str, str] = {}
    event_ids: list[str] = []

    for index in range(n_documents):
        event_id = str(uuid.UUID(int=rng.getrandbits(128), version=4))
        event_ids.append(event_id)
        unique = f"{rng.choice(_PREFIXES)}-{9000 + index}"
        unique_tags.append(unique)

        sentences = [f"Monitoring recorded {_UBIQUITOUS} throughout the task."]
        sentences.append(_sentence(rng, unique))
        for _ in range(rng.randint(0, 11)):
            sentences.append(_sentence(rng, _zipf_choice(rng, shared_tags)))
        if rng.random() < 0.45:
            sentences.append(f"Cited under {rng.choice(_CITATIONS)}.")
        if rng.random() < 0.30:
            sentences.append(f"Substance CAS {rng.choice(_CAS)} was involved.")
        sentences.append(_zipf_choice(rng, _CONSEQUENCE))
        texts[event_id] = " ".join(sentences)

    documents = tuple(
        build_document_postings(event_id, texts[event_id]) for event_id in event_ids
    )

    queries: list[tuple[str, str]] = []
    quarter = n_queries // 4

    # 1. single-term, over the whole df range
    single_pool = [
        *shared_tags[:20],
        _UBIQUITOUS, "valve", "pump", "isolation", "fatality", "hot work",
        *unique_tags[:20],
    ]
    for i in range(quarter):
        queries.append(("single", single_pool[i % len(single_pool)]))

    # 2. multi-term, drawn from real documents so the terms co-occur
    for i in range(quarter):
        source = texts[event_ids[(i * 37) % n_documents]]
        words = source.split()
        start = rng.randrange(0, max(1, len(words) - 8))
        queries.append(("multi", " ".join(words[start : start + rng.randint(2, 8)])))

    # 3. rare identifiers: df = 1. This is what channel D exists for.
    for i in range(quarter):
        queries.append(("rare-identifier", unique_tags[(i * 17) % n_documents]))

    # 4. edges: unseen terms, df = N terms, mixtures, and identifier-vs-near-miss pairs
    edges = [
        _UNSEEN,
        f"{_UNSEEN} {unique_tags[0]}",
        _UBIQUITOUS,
        f"{_UBIQUITOUS} {unique_tags[1]}",
        f"{unique_tags[2]} {unique_tags[3]} {unique_tags[4]}",
        "K-401 K402",
        "7783-06-4",
        "CAS 7783-06-4 and 25 %LEL",
        "30 CFR 57.22239",
        "0.1 % methane",
        "1000 ppm methane",
        "50 °C bearing",
        "122 degF bearing",
        "AS/NZS 3000 wiring",
        "the valve was not closed",
        "the valve was closed",
        "lock-out tag-out",
        "1450 rpm 689 kPa",
        f"{shared_tags[0]} {shared_tags[1]} {shared_tags[2]} {shared_tags[3]}",
        "-5 °C frozen drain",
    ]
    for i in range(n_queries - 3 * quarter):
        queries.append(("edge", edges[i % len(edges)]))

    # A query whose terms all vanish under analysis cannot be issued; drop it here rather
    # than letting the builder raise in the middle of the differential.
    kept = tuple((kind, text) for kind, text in queries if analyse_query(text).terms)
    assert len(kept) >= n_queries - 4, "too many generated queries analysed to nothing"

    return Fixture(
        site_id=site_id,
        other_site_id=other_site_id,
        texts=texts,
        documents=documents,
        queries=kept,
        unique_tags=tuple(unique_tags),
    )
