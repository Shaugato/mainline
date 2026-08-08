# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Corpora and DDL for the candidate-cascade integration suite.

Two things live here and they are kept apart on purpose.

**The corpus builder** is pure Python and is used by the offline half of the
suite — the half that runs in CI today, with no cluster and no AWS.  It builds
*distinct* clauses: every one carries a unique reference number, so a corpus of
800 contains 800 genuinely different texts.  That distinctness is load-bearing
for the sublinearity measurement: if the generator silently repeated itself, the
number of band collisions would grow with the corpus for a reason that has
nothing to do with the index, and the test would fail for the wrong reason (or,
worse, pass for one).

**The DDL** is a *minimal mirror* of the two tables this domain reads —
``mainline.clause_band`` and ``mainline.clause_embedding``.  It is not the real
migration: those live in ``verticals/mainline/db/migrations/`` and belong to the
datamodel lead.  Two deliberate differences, both stated rather than hidden:

* the embedding column is ``VECTOR(8)``, not ``VECTOR(1024)``.  What is under
  test is the *statement* and the *index shape* — that a fully-constrained arm
  plans as a prefix-constrained vector search — and neither depends on the
  dimension.  A 1024-d fixture would make the suite slow for no extra proof.
* the tables are created inside a throwaway database whose schema is named
  ``mainline``, so the production-shaped ``mainline.clause_band`` identifiers in
  the statements resolve unchanged.  Nothing here ever writes to a real
  ``mainline`` schema.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from dataclasses import dataclass

from mainline_domain.anchors import extract_anchors
from mainline_domain.canon import canon_digest
from mainline_domain.identity.candidates import ClauseRecord, ClauseRef

SITE = uuid.UUID("aaaaaaaa-0000-4000-8000-000000000001")
ACTIVITY = "maintenance/mechanical-isolation"

SUBJECTS = (
    "the authorised person",
    "the permit issuer",
    "the isolation officer",
    "the area supervisor",
)
VERBS = ("shall isolate", "shall verify", "shall confirm", "shall witness")
OBJECTS = (
    "pump P-101A at ISOL-4471",
    "vessel TK-204 at ISOL-3312",
    "compressor C-330B at ISOL-7781",
    "line 6-PG-1042 at ISOL-2290",
)
TAILS = (
    "before breaking containment",
    "prior to entry into the confined space",
    "before the hot work permit is issued",
)

QUERY_TEXT = (
    "The authorised person shall isolate pump P-101A at ISOL-4471 and verify zero "
    "energy at PIT-1204 before breaking containment."
)

#: Near-duplicates of :data:`QUERY_TEXT` planted into every corpus size.  Their
#: number is FIXED, which is the whole point: if S3's work grew with the corpus
#: it would have to be from something other than the planted pairs.
PLANTED = (
    QUERY_TEXT,
    QUERY_TEXT.replace("shall isolate", "must isolate"),
    QUERY_TEXT.replace("verify zero energy", "confirm zero energy"),
    QUERY_TEXT.replace("The authorised", "the authorised").replace(" and ", " and then "),
)


@dataclass(frozen=True, slots=True)
class Corpus:
    """A built corpus and the query it was built around."""

    records: tuple[ClauseRecord, ...]
    query_text: str
    planted: tuple[ClauseRef, ...]

    def __len__(self) -> int:
        return len(self.records)


def _clause(i: int) -> str:
    """One distinct clause.  The reference number guarantees distinctness."""
    subject = SUBJECTS[i % len(SUBJECTS)]
    verb = VERBS[(i // 4) % len(VERBS)]
    obj = OBJECTS[(i // 16) % len(OBJECTS)]
    tail = TAILS[(i // 64) % len(TAILS)]
    return (
        f"{subject.capitalize()} {verb} {obj} {tail}. "
        f"Work order reference WO-{i:07d}-{(i * 37) % 97:02d} applies to this step."
    )


def record_for(text: str, index: int) -> ClauseRecord:
    """Wrap a clause text as a :class:`ClauseRecord` with a deterministic identity."""
    return ClauseRecord(
        ref=ClauseRef(
            clause_uuid=uuid.uuid5(uuid.NAMESPACE_URL, f"mainline/w7/clause/{index}"),
            commit_id=index.to_bytes(32, "big"),
        ),
        site_id=SITE,
        activity_root=ACTIVITY,
        canon_text=text,
        canon_sha256=canon_digest(text),
        anchors=extract_anchors(text),
    )


def build_corpus(size: int) -> Corpus:
    """``size`` distinct clauses, with the fixed planted near-duplicates included.

    Planted records occupy the *first* indices so that a prefix of a larger
    corpus is a valid smaller corpus — which is what lets the doubling test
    index once and measure at several sizes without rebuilding.
    """
    if size < len(PLANTED):
        raise ValueError(f"corpus size must be at least {len(PLANTED)}")
    texts = [*PLANTED, *(_clause(i) for i in range(size - len(PLANTED)))]
    records = tuple(record_for(text, i) for i, text in enumerate(texts))
    if len({r.canon_text for r in records}) != size:
        raise ValueError(
            "the generator produced duplicate clause texts; the sublinearity "
            "measurement would be meaningless"
        )
    return Corpus(
        records=records,
        query_text=QUERY_TEXT,
        planted=tuple(r.ref for r in records[: len(PLANTED)]),
    )


def prefixes(corpus: Corpus, sizes: tuple[int, ...]) -> Iterator[tuple[int, Corpus]]:
    """Successive prefixes of one corpus, so signatures are computed once."""
    for size in sizes:
        if size > len(corpus):
            raise ValueError(f"prefix {size} exceeds corpus size {len(corpus)}")
        yield (
            size,
            Corpus(
                records=corpus.records[:size],
                query_text=corpus.query_text,
                planted=corpus.planted,
            ),
        )


# --------------------------------------------------------------------------- #
# DDL — a minimal mirror, in a throwaway database.  See the module docstring.  #
# --------------------------------------------------------------------------- #

CREATE_SCHEMA = "CREATE SCHEMA IF NOT EXISTS mainline"

CREATE_CLAUSE_BAND = """
CREATE TABLE IF NOT EXISTS mainline.clause_band (
  site_id     UUID  NOT NULL,
  band_no     INT2  NOT NULL,
  band_hash   INT8  NOT NULL,
  clause_uuid UUID  NOT NULL,
  commit_id   BYTES NOT NULL,
  PRIMARY KEY (site_id, band_no, band_hash, clause_uuid, commit_id)
)
""".strip()

CREATE_CLAUSE_EMBEDDING = """
CREATE TABLE IF NOT EXISTS mainline.clause_embedding (
  clause_uuid   UUID   NOT NULL,
  commit_id     BYTES  NOT NULL,
  site_id       UUID   NOT NULL,
  activity_root STRING NOT NULL,
  embed_model   STRING NOT NULL,
  index_gen     STRING NOT NULL,
  embedding     VECTOR(8) NOT NULL,
  PRIMARY KEY (clause_uuid, commit_id),
  VECTOR INDEX ce_ann (site_id, activity_root, embedding vector_cosine_ops)
)
""".strip()

CREATE_CLAUSE_VERSION = """
CREATE TABLE IF NOT EXISTS mainline.clause_version (
  clause_uuid   UUID   NOT NULL,
  commit_id     BYTES  NOT NULL,
  site_id       UUID   NOT NULL,
  canon_text    STRING NOT NULL,
  canon_sha256  BYTES  NOT NULL,
  anchor_set    STRING[] NOT NULL,
  PRIMARY KEY (clause_uuid, commit_id),
  INDEX by_digest (site_id, canon_sha256)
)
""".strip()

INSERT_CLAUSE_VERSION = """
INSERT INTO mainline.clause_version
  (clause_uuid, commit_id, site_id, canon_text, canon_sha256, anchor_set)
VALUES (%(clause_uuid)s, %(commit_id)s, %(site_id)s, %(canon_text)s,
        %(canon_sha256)s, %(anchor_set)s)
ON CONFLICT DO NOTHING
""".strip()

INSERT_CLAUSE_EMBEDDING = """
INSERT INTO mainline.clause_embedding
  (clause_uuid, commit_id, site_id, activity_root, embed_model, index_gen, embedding)
VALUES (%(clause_uuid)s, %(commit_id)s, %(site_id)s, %(activity_root)s,
        'fixture', 'w7-test', %(embedding)s)
ON CONFLICT DO NOTHING
""".strip()


def fixture_embedding(text: str, dim: int = 8) -> list[float]:
    """A deterministic 8-d pseudo-embedding derived from the text's own digest.

    **Not a model output and never claimed to be one.**  The ANN assertions in
    this suite are about the *plan* and about *latency growth*; neither needs
    semantically meaningful vectors, and manufacturing some would invite the
    reading that this package calls a model.  It does not, and cannot: no SDK
    is installed in this distribution (decision D1 / principle P7).
    """
    digest = canon_digest(text)
    values = [digest[i] / 255.0 for i in range(dim)]
    norm = sum(v * v for v in values) ** 0.5 or 1.0
    return [v / norm for v in values]
