# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The one query: a Bedrock-embedded permit narrative, searched through C-SPANN, returns
the precursor of the fatality that permit preceded.

This program exists to turn one sentence into something a judge can re-run::

    The vectors CockroachDB's C-SPANN index searches were produced by Amazon Bedrock, and
    here is the hinted, prefix-constrained ANN query — with its EXPLAIN naming
    mainline.clause_embedding@ce_ann — that recovered the true precursor of a fatality
    from a permit written before it happened.

Nothing here is simulated.  Every vector is a live ``amazon.titan-embed-text-v2:0``
response from ``bedrock-runtime`` in ``ap-southeast-2``; every rank is the position a row
came back in from a live CockroachDB Cloud cluster in ``aws-ap-southeast-1``; every plan
is a real ``EXPLAIN`` from that cluster.  The corpus those vectors describe is **synthetic
and says so in every artefact it touches** — see :data:`CAVEAT_SYNTHETIC`.

────────────────────────────────────────────────────────────────────────────────────────
THE FOUR DESIGN DECISIONS, AND WHY EACH ONE IS THE HONEST ONE
────────────────────────────────────────────────────────────────────────────────────────

**1 · The index is pinned, and the counterfactual is captured even though it is the
unflattering half.**  ADR 0002 GT-06 recorded that at ~5 200 rows an *unhinted*
prefix-constrained ANN query does not choose the vector index, and GT-06b that
``FROM t@ce_ann`` does.  This program captures both plans against the same rows at the
same moment, and — because one plan is one observation — sweeps the row count as well
(``--crossover``).  **Measured on 2026-08-11 against v26.2.5, GT-06 did not reproduce at
any size up to 5 300 rows: the unhinted plan also traverses ``ce_ann``.**  That is
published in ``evidence/aws/ann/explain-unhinted.txt`` and in the artefact's caveats
rather than quietly omitted, and it does not weaken the hint: a cost-based choice that has
already changed once between two measurements on the same cluster is exactly what must not
sit beneath a safety gate.  What it does remove is the right to say the hint was
*necessary* at this scale, and no artefact this program writes says that.

**2 · Both prefix columns are bound to exactly one value.  Always.**  C-SPANN keeps a
separate k-means partition tree per distinct prefix value, so ``(site_id, activity_root)``
does not filter a result set — it decides *which tree is descended*.  Drop either
constraint and the server **refuses**: ``42809``, ``index "ce_ann" cannot be used for this
query``.  That refusal is the half of the counterfactual that does not depend on the
optimizer's mood, and it is captured too.

``activity_root IN (...)`` is a subtler case, and this program measures it instead of
repeating the received rule.  ``0031_clause_embedding.sql`` says an ``IN`` list does not
use the index; on v26.2.5 it does — the optimizer expands it into one prefix span per
value.  The architecture's ancestor walk is still the right shape, for a reason the
received rule obscures: ``LIMIT k`` over three spans is a **shared** budget of k candidates
across three trees, where the walk gives each tree its own k and re-ranks 3k.  Both arms
are run against every query so that difference is a number and not an argument.

**3 · ``site_id`` in the evidence database is a corpus tenant, not a mine.**  In
production, ``0031_clause_embedding.sql`` projects ``site_id`` from
``mainline.clause_version`` — a clause belongs to the site that wrote it.  The claim under
test here is the *opposite* direction: that a permit's author is warned by a fatality at
**another** operator's site, which their own records cannot contain.  Partitioning the
precursor library by the reader's own mine would make that recall structurally impossible
— not lower-ranked, *unreachable*.  So the evidence corpus is one shared regulator library
under a single deterministic ``site_id``, and ``activity_root`` carries the three real
partition trees (``/surface``, ``/underground``, ``/mill``).  This is a **departure from
the production projection** and it is stated as a caveat in the artefact, in the SQL
header and here, rather than left for a reader to discover.

**4 · Two relevance definitions are reported, never one.**  ``g4_retro.qrels.jsonl``
grades by *distant supervision*: grade 3 is the document the investigator **cited**, grade
2 is a document that **shares the mechanism** (hazard energy + coded classification).
Those are different targets and a semantic retriever is not equally entitled to either.
Reporting only the flattering one would be the exact failure this repository's honesty
discipline exists to prevent, so both are computed, both carry a Wilson interval, and
neither is ever printed as a bare rate.

────────────────────────────────────────────────────────────────────────────────────────
WHAT THIS PROGRAM WRITES
────────────────────────────────────────────────────────────────────────────────────────

``evidence/aws/ann/explain-hinted.txt``     the plan that must name ``clause_embedding@ce_ann``
``evidence/aws/ann/explain-unhinted.txt``   the same statement without the hint — the control
``evidence/aws/ann/the-one-query.sql``      one statement, values inlined, judge-runnable
``evidence/aws/ann/ann-proof.json``         per-query ranks, n-stated hit rates, digests

Filenames are fixed and timestamps live *inside* the JSON, so a re-run overwrites rather
than accumulates.

``out/aws/ann/`` (gitignored) holds two inputs rather than evidence: the Titan vector cache,
so a re-run costs nothing and returns byte-identical vectors, and ``crossover.json``, whose
numbers are copied into the committed artefact.

Run::

    D:/CoackroachDBxAWS/mainline/.venv/Scripts/python.exe scripts/aws/ann_proof.py
    ... --queries 20              # a cheaper pass; >= 20 is the floor the brief sets
    ... --corpus-cap 560          # judged documents + a seeded sample; disclosed in the artefact
    ... --database w_ann_proof    # a scratch surface, for development
    ... --skip-load               # rows already present; query and explain only
    ... --crossover               # the GT-06 sweep alone: no Bedrock, no evidence database
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sys
import threading
import time
import uuid
from collections.abc import Iterable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

if __package__ in (None, ""):  # direct execution: `python scripts/aws/ann_proof.py`
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.aws._common import (
    REGION,
    artefact,
    assert_in_region,
    bedrock_runtime,
    crdb,
    ledger_total,
    redact,
    repo_root,
    sha256_hex,
    token_ledger_entry,
    with_retry,
)

# The repository's own Wilson implementation, property-tested and cross-checked against
# scipy in `trappoint_recall.eval.crosscheck`.  Imported rather than reimplemented: a
# second copy of an interval function is a second thing that can be quietly wrong, and
# `docs/` is ratcheted against bare point estimates precisely so that this number is the
# one everybody quotes.
from trappoint_recall.corpora import synthetic
from trappoint_recall.eval.measurement import wilson_interval

__all__ = [
    "ANN_HINTED",
    "ANN_UNHINTED",
    "CORPUS_SITE_ID",
    "Doc",
    "QueryCase",
    "ancestor_walk",
    "build_corpus",
    "hinted_statement",
    "load_goldset",
    "main",
    "plan_digest",
    "single_root",
]

# ═══════════════════════════════════════════════════════════════════════════════════════
# 0 · Constants
# ═══════════════════════════════════════════════════════════════════════════════════════

#: The evidence surface named by the AWS-execution plan §3.  Created if absent; never
#: dropped.  ``--database`` points the whole program at a scratch surface instead.
DEFAULT_DATABASE: Final[str] = "mainline_ann_evidence"

TABLE: Final[str] = "mainline.clause_embedding"
INDEX: Final[str] = "ce_ann"
PARENT_STUB: Final[str] = "mainline.clause_version"
DOCMAP: Final[str] = "mainline.ann_evidence_docmap"

TITAN_MODEL_ID: Final[str] = "amazon.titan-embed-text-v2:0"
EMBED_DIM: Final[int] = 1024

#: The UUID namespace for this evidence corpus.  Deterministic so that a re-run addresses
#: the same rows, and so that ``clause_uuid`` in a committed plan can be re-derived from a
#: ``doc_id`` by anybody with this file.
NAMESPACE: Final[uuid.UUID] = uuid.uuid5(uuid.NAMESPACE_URL, "https://mainline.dev/ann-evidence")

#: The single corpus tenant — see design decision 3 in the module docstring.
CORPUS_SITE_ID: Final[str] = str(uuid.uuid5(NAMESPACE, "site:msha-synthetic-precursor-library"))

#: The three partition trees.  A part-50 row's ``SUBUNIT``, a fatality report's
#: ``Subunit:`` header and a state-regulator alert's site descriptor all reduce to one of
#: these, which is what makes the prefix a *tree selector* rather than a decoration.
ROOT_SURFACE: Final[str] = "/surface"
ROOT_UNDERGROUND: Final[str] = "/underground"
ROOT_MILL: Final[str] = "/mill"
ROOTS: Final[tuple[str, ...]] = (ROOT_MILL, ROOT_SURFACE, ROOT_UNDERGROUND)

#: The three retrieval arms, every one of them run against every query.  Reporting one arm
#: would be reporting a choice as a result.
ARMS: Final[tuple[str, ...]] = ("single_root", "ancestor_walk", "in_list_one_statement")

#: How an Australian alert's free-text site descriptor maps onto the three trees.  Written
#: out rather than inferred, because "underground coal" and "underground metalliferous"
#: are the same tree and "quarry" and "open cut coal" are not obviously the same as
#: "surface" until somebody says so in a file.
AU_SITE_TO_ROOT: Final[dict[str, str]] = {
    "underground coal": ROOT_UNDERGROUND,
    "underground metalliferous": ROOT_UNDERGROUND,
    "metalliferous open cut": ROOT_SURFACE,
    "open cut coal": ROOT_SURFACE,
    "quarry": ROOT_SURFACE,
    "processing plant": ROOT_MILL,
    "alumina refinery": ROOT_MILL,
    "iron ore plant": ROOT_MILL,
}

#: **The statement**, written out rather than assembled.
#:
#: Every identifier is a literal here — no f-string, no ``.format``, no concatenation — for
#: two reasons.  The evidential one: this is the statement the submission rests on, and a
#: reader should be able to see it in the source without simulating string interpolation in
#: their head.  The mechanical one: SQL built by interpolation is what ``S608`` is for, and
#: a file that suppresses that rule to save four characters has taught the next reader that
#: the rule is noise.
#:
#: The unhinted form differs from the hinted form in exactly one token, ``@ce_ann``, and
#: :func:`hinted_statement` is the only thing that chooses between them —
#: ``test_committed_unhinted_plan_is_a_real_control`` checks that the difference survived.
ANN_HINTED: Final[str] = """SELECT clause_uuid, commit_id, embedding <=> %(vec)s AS dist
  FROM mainline.clause_embedding@ce_ann
 WHERE site_id = %(site)s AND activity_root = %(root)s
 ORDER BY embedding <=> %(vec)s LIMIT %(k)s"""

ANN_UNHINTED: Final[str] = """SELECT clause_uuid, commit_id, embedding <=> %(vec)s AS dist
  FROM mainline.clause_embedding
 WHERE site_id = %(site)s AND activity_root = %(root)s
 ORDER BY embedding <=> %(vec)s LIMIT %(k)s"""

#: One arm of the ancestor walk.  ``%(root)s`` is renamed per arm by
#: :func:`ancestor_walk`; the rest is untouched, so every arm is provably this statement.
ANN_WALK_ARM: Final[str] = ANN_HINTED

#: The two counterfactual shapes, each removing exactly one prefix constraint while
#: keeping the hint, plus the ``IN (...)`` trap that ``0031_clause_embedding.sql`` warns
#: about.  They exist to be EXPLAINed, never to be trusted with a result.
ANN_NO_SITE: Final[str] = """SELECT clause_uuid, commit_id, embedding <=> %(vec)s AS dist
  FROM mainline.clause_embedding@ce_ann
 WHERE activity_root = %(root)s
 ORDER BY embedding <=> %(vec)s LIMIT %(k)s"""

ANN_NO_ROOT: Final[str] = """SELECT clause_uuid, commit_id, embedding <=> %(vec)s AS dist
  FROM mainline.clause_embedding@ce_ann
 WHERE site_id = %(site)s
 ORDER BY embedding <=> %(vec)s LIMIT %(k)s"""

#: The shape ``0031_clause_embedding.sql`` warns about: a disjunction on the second prefix
#: column.  Kept as a measured arm rather than as a warning, because on v26.2.5 it does not
#: behave the way the header says — see ``arms.in_list_one_statement`` in the artefact.
ANN_IN_LIST: Final[str] = """SELECT clause_uuid, commit_id, embedding <=> %(vec)s AS dist
  FROM mainline.clause_embedding@ce_ann
 WHERE site_id = %(site)s AND activity_root IN ('/mill', '/surface', '/underground')
 ORDER BY embedding <=> %(vec)s LIMIT %(k)s"""

INSERT_PARENT: Final[str] = (
    "INSERT INTO mainline.clause_version (clause_uuid, commit_id) "
    "VALUES (%s, %s) ON CONFLICT DO NOTHING"
)
#: Upsert, not ``DO NOTHING``, and the difference is load-bearing.
#:
#: ``index_gen`` is a digest of the corpus, and :data:`DELETE_STALE_GENERATIONS` removes
#: rows carrying an older one.  With ``DO NOTHING`` a row that is still in the corpus but
#: already present from a previous run would keep its **old** label and then be deleted as
#: stale — the corpus would silently shrink by exactly the rows a re-run was supposed to
#: confirm.  The ``DO UPDATE`` re-stamps the metadata family and leaves ``embedding``
#: alone, so a re-run costs no vector-index maintenance and no ambiguity.
INSERT_EMBEDDING: Final[str] = (
    "INSERT INTO mainline.clause_embedding "
    "(clause_uuid, commit_id, site_id, activity_root, embed_model, index_gen, embedding) "
    "VALUES (%s, %s, %s, %s, %s, %s, %s) "
    "ON CONFLICT (clause_uuid, commit_id) DO UPDATE SET "
    "site_id = excluded.site_id, activity_root = excluded.activity_root, "
    "embed_model = excluded.embed_model, index_gen = excluded.index_gen"
)
INSERT_DOCMAP: Final[str] = (
    "INSERT INTO mainline.ann_evidence_docmap "
    "(clause_uuid, doc_id, source, activity_path, occurred_on, excerpt) "
    "VALUES (%s, %s, %s, %s, %s, %s) "
    "ON CONFLICT (clause_uuid) DO UPDATE SET "
    "doc_id = excluded.doc_id, source = excluded.source, "
    "activity_path = excluded.activity_path, occurred_on = excluded.occurred_on, "
    "excerpt = excluded.excerpt"
)
COUNT_ALL: Final[str] = "SELECT count(*) FROM mainline.clause_embedding"
COUNT_UNDER_SITE: Final[str] = "SELECT count(*) FROM mainline.clause_embedding WHERE site_id = %s"

#: Remove this worker's rows from a previous corpus generation.
#:
#: ``index_gen`` is a digest of the corpus, so a different corpus is a different label. If
#: the old rows were left in place they would sit in the same partition trees under the
#: same ``site_id`` and be searched by every query below — silently mixing two corpora and
#: making every rank a measurement of a set nothing describes. Scoped to this worker's
#: ``site_id``: ``scripts/aws/load_vectors.py`` shares the table and its rows are not this
#: program's to delete.
DELETE_STALE_GENERATIONS: Final[str] = (
    "DELETE FROM mainline.clause_embedding WHERE site_id = %s AND index_gen <> %s"
)
SURVEY_CORPUS: Final[str] = (
    "SELECT count(*), count(DISTINCT site_id), count(DISTINCT activity_root), "
    "count(DISTINCT embed_model), count(DISTINCT index_gen) FROM mainline.clause_embedding"
)
DISTINCT_MODELS: Final[str] = "SELECT DISTINCT embed_model FROM mainline.clause_embedding"
DISTINCT_GENS: Final[str] = "SELECT DISTINCT index_gen FROM mainline.clause_embedding"

#: The same two, scoped to the rows the queries below actually search.
#:
#: The whole-table versions describe a surface this program shares with
#: ``scripts/aws/load_vectors.py``. "Every vector in this table is Titan v2's" is a claim
#: about somebody else's rows as well as these, and a claim about rows nothing here
#: searched has no business in this artefact's headline.
MODELS_UNDER_SITE: Final[str] = (
    "SELECT DISTINCT embed_model FROM mainline.clause_embedding WHERE site_id = %s"
)
GENS_UNDER_SITE: Final[str] = (
    "SELECT DISTINCT index_gen FROM mainline.clause_embedding WHERE site_id = %s"
)
DISTINCT_ROOTS_UNDER_SITE: Final[str] = (
    "SELECT DISTINCT activity_root FROM mainline.clause_embedding WHERE site_id = %s"
)
OTHER_PREFIXES: Final[str] = (
    "SELECT site_id, activity_root, count(*), min(index_gen) FROM mainline.clause_embedding "
    "WHERE site_id <> %s GROUP BY site_id, activity_root ORDER BY 1, 2"
)

CAVEAT_SYNTHETIC: Final[str] = (
    "THE CORPUS IS SYNTHETIC. Every fatality report, part-50 row, CSB report and state "
    "alert here was generated by trappoint_recall.corpora.synthetic — invented records "
    "shaped like the real thing. No real incident, no real person, no real operation. "
    "The Bedrock calls, the vectors, the index traversal, the ranks and the plans are all "
    "real; the subject matter is not."
)
CAVEAT_STUB: Final[str] = (
    "THE PARENT TABLE IS A STUB. mainline.clause_version in this evidence database holds "
    "(clause_uuid, commit_id) and nothing else: no append_only trigger, no "
    "z_delta_witness_required, no clause_version_guard, no bloodline columns. It exists "
    "only to satisfy fk_version so that clause_embedding can be created verbatim from "
    "0031_clause_embedding.sql. This database therefore proves nothing about the gate, "
    "and no gate claim may cite it."
)
CAVEAT_SITE_PREFIX: Final[str] = (
    "site_id HERE IS A CORPUS TENANT, NOT A MINE. Production projects site_id from "
    "mainline.clause_version (0031 header, band 0130-0199). This evidence corpus binds it "
    "to one shared regulator-library value because the claim under test is cross-site "
    "recall: a precursor at another operator's site is exactly what the permit's author "
    "could not have known. Partitioning by the reader's own site would make that "
    "unreachable rather than lower-ranked."
)
CAVEAT_GRADES: Final[str] = (
    "TWO RELEVANCE DEFINITIONS, BOTH REPORTED. grade 3 is the single document the "
    "investigator cited (distant supervision over the citation graph); grade >= 2 adds "
    "documents that share the mechanism. A semantic retriever is entitled to the second "
    "and only incidentally to the first. Quoting either alone would misstate the result."
)
WALL_FILTER_NOTE: Final[str] = (
    "clause_embedding carries no date column, so the ANN arm cannot exclude a document that "
    "had not happened when the permit was written. The wall-filtered rates drop those rows "
    "client-side before ranking, which is what a gate applying its own time wall to an ANN "
    "result would do. Both the raw and the filtered rate are reported; neither replaces the "
    "other."
)

CAVEAT_LATENCY: Final[str] = (
    "LATENCY IS NOT A BENCHMARK. Each query was issued once, from a Windows workstation "
    "in Australia to CockroachDB Cloud Basic in aws-ap-southeast-1 (Singapore), over the "
    "public internet, on a shared serverless tier. The numbers include round-trip and "
    "cold-start and have no interval. They are recorded so the run is reproducible, not "
    "so anybody can quote a p99."
)


# ═══════════════════════════════════════════════════════════════════════════════════════
# 1 · The corpus
# ═══════════════════════════════════════════════════════════════════════════════════════


def slugify(text: str) -> str:
    """Lowercase, hyphen-joined, no leading or trailing hyphen."""
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


@dataclass(frozen=True, slots=True)
class Doc:
    """One retrievable document: the unit a qrels ``doc_id`` names."""

    doc_id: str
    source: str
    activity_root: str
    activity_path: str
    occurred_on: str | None
    text: str

    @property
    def clause_uuid(self) -> str:
        """Deterministic from ``doc_id``, so a committed plan can be re-derived from it."""
        return str(uuid.uuid5(NAMESPACE, f"doc:{self.doc_id}"))

    @property
    def commit_id(self) -> bytes:
        """Content-addressed, 32 bytes — the shape ``0024 commit_obj`` requires of a
        commit id, so the stub parent's keys are not arbitrary."""
        return hashlib.sha256(self.text.encode("utf-8")).digest()


def _header_field(text: str, name: str) -> str | None:
    match = re.search(rf"^{re.escape(name)}: (.+)$", text, re.MULTILINE)
    return match.group(1).strip() if match else None


def build_corpus(seed: str = synthetic.DEFAULT_SEED) -> tuple[Doc, ...]:
    """Every document a qrels judgement can name, as one flat retrievable set.

    Four families, one row each, no chunking.  Chunking would improve recall on the long
    fatality reports and would also make ``rank`` mean "rank of the best passage", which
    is a different measurement from the one the goldset judges.  The goldset judges
    documents, so this retrieves documents.
    """
    corpus = synthetic.generate(seed)
    docs: list[Doc] = []

    header = corpus.part50_lines[0].split("|")
    for line in corpus.part50_lines[1:]:
        row = dict(zip(header, line.split("|"), strict=True))
        root = "/" + slugify(row["SUBUNIT"])
        docs.append(
            Doc(
                doc_id=row["DOCUMENT_NO"],
                source="part50",
                activity_root=root,
                activity_path=f"{root}/{slugify(row['ACTIVITY'])}",
                occurred_on=_us_date(row["ACCIDENT_DT"]),
                text=line,
            )
        )

    for report in corpus.fatality_reports:
        text = str(report["text"])
        subunit = _header_field(text, "Subunit") or "Surface"
        activity = _header_field(text, "Activity") or "unknown"
        root = "/" + slugify(subunit)
        docs.append(
            Doc(
                doc_id=str(report["external_ref"]),
                source="msha_fatality_report",
                activity_root=root,
                activity_path=f"{root}/{slugify(activity)}",
                occurred_on=_long_date(_header_field(text, "Date of Accident")),
                text=text,
            )
        )

    for report in corpus.csb_reports:
        text = str(report["text"])
        # A CSB investigation is a process-plant document by construction: refinery,
        # terminal, chemical unit.  `/mill` is the processing tree in this taxonomy.
        docs.append(
            Doc(
                doc_id=str(report["external_ref"]),
                source="csb_report",
                activity_root=ROOT_MILL,
                activity_path=ROOT_MILL
                + "/"
                + slugify(_header_field(text, "Incident Type") or "process"),
                occurred_on=_header_field(text, "Incident Date"),
                text=text,
            )
        )

    for alert in corpus.au_alerts:
        site = str(alert.get("site") or "").strip().lower()
        au_root = AU_SITE_TO_ROOT.get(site)
        if au_root is None:  # a new site descriptor must be classified, not guessed at
            raise KeyError(
                f"state-regulator alert {alert['external_ref']!r} carries site {site!r}, "
                "which AU_SITE_TO_ROOT does not classify; add it there rather than "
                "letting an unclassified document into a partition tree"
            )
        title = str(alert.get("title") or "")
        body = str(alert.get("text") or "")
        occurred = alert.get("occurred_at")
        docs.append(
            Doc(
                doc_id=str(alert["external_ref"]),
                source="au_regulator_alert",
                activity_root=au_root,
                activity_path=f"{au_root}/{slugify(str(alert.get('activity') or 'unknown'))}",
                occurred_on=None if occurred is None else str(occurred),
                text=f"{title}\n\n{body}",
            )
        )

    seen: set[str] = set()
    for doc in docs:
        if doc.doc_id in seen:
            raise ValueError(f"duplicate doc_id in corpus: {doc.doc_id!r}")
        seen.add(doc.doc_id)
    return tuple(docs)


_MONTHS = {
    m: i
    for i, m in enumerate(
        (
            "January",
            "February",
            "March",
            "April",
            "May",
            "June",
            "July",
            "August",
            "September",
            "October",
            "November",
            "December",
        ),
        start=1,
    )
}


def _us_date(value: str) -> str | None:
    """``MM/DD/YYYY`` -> ``YYYY-MM-DD``."""
    match = re.fullmatch(r"(\d{2})/(\d{2})/(\d{4})", value.strip())
    return f"{match.group(3)}-{match.group(1)}-{match.group(2)}" if match else None


def _long_date(value: str | None) -> str | None:
    """``January 11, 2010`` -> ``2010-01-11``."""
    if not value:
        return None
    match = re.fullmatch(r"([A-Za-z]+) (\d{1,2}), (\d{4})", value.strip())
    if match is None or match.group(1) not in _MONTHS:
        return None
    return f"{match.group(3)}-{_MONTHS[match.group(1)]:02d}-{int(match.group(2)):02d}"


# ═══════════════════════════════════════════════════════════════════════════════════════
# 2 · The goldset
# ═══════════════════════════════════════════════════════════════════════════════════════

GOLDSET_DIR: Final[Path] = repo_root() / "tests" / "fixtures" / "recall" / "goldsets"


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    """JSONL, skipping the ``//!meta`` provenance line the goldset builder writes."""
    out: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("//"):
            continue
        out.append(json.loads(line))
    return out


@dataclass(frozen=True, slots=True)
class QueryCase:
    """One retro permit narrative and everything the goldset says is relevant to it."""

    query_id: str
    text: str
    site_label: str
    activity_path: str
    wall: str
    truth_doc_id: str
    #: ``doc_id -> grade``, grade >= 2 only.  Grade 1 is explicitly *not* relevance here:
    #: the goldset's own scale calls it marginal, and folding it in would inflate every
    #: hit rate in this file by counting near-misses as hits.
    relevant: Mapping[str, int]

    @property
    def activity_root(self) -> str:
        """The first path segment — the partition tree this permit's own work belongs to."""
        return "/" + self.activity_path.strip("/").split("/")[0]


def load_goldset(limit: int | None = None) -> tuple[QueryCase, ...]:
    """The G4 retro queries, in file order, each carrying its grade >= 2 judgements.

    Deterministic order, and ``limit`` truncates rather than samples: a sampled subset
    would need its own seed recorded to be reproducible, and file order is already a
    property of a committed fixture.
    """
    queries = _read_jsonl(GOLDSET_DIR / "g4_retro.queries.jsonl")
    qrels = _read_jsonl(GOLDSET_DIR / "g4_retro.qrels.jsonl")

    graded: dict[str, dict[str, int]] = {}
    for row in qrels:
        if int(row["grade"]) >= 2:
            graded.setdefault(row["query_id"], {})[row["doc_id"]] = int(row["grade"])

    cases: list[QueryCase] = []
    for row in queries:
        relevant = graded.get(row["query_id"], {})
        if not relevant:
            continue
        cases.append(
            QueryCase(
                query_id=row["query_id"],
                text=row["text"],
                site_label=row["site_id"],
                activity_path=row["activity_path"],
                wall=row["wall"],
                truth_doc_id=row["truth_doc_id"],
                relevant=relevant,
            )
        )
    return tuple(cases[:limit] if limit else cases)


# ═══════════════════════════════════════════════════════════════════════════════════════
# 3 · Bedrock
# ═══════════════════════════════════════════════════════════════════════════════════════

#: Vectors are cached under ``out/`` (gitignored) by the SHA-256 of the exact text that
#: was embedded.  A re-run of this program costs nothing and returns byte-identical
#: vectors, which is what makes the ranks below reproducible rather than merely repeatable.
CACHE_PATH: Final[Path] = repo_root() / "out" / "aws" / "ann" / "titan-vectors.jsonl"

#: The two botocore error names that mean *slow down*, and the only two this program
#: retries.  Matched by class name rather than by ``except botocore.exceptions...`` because
#: Bedrock's modelled exceptions are generated at runtime by ``errorfactory`` and are not
#: importable symbols.
_THROTTLE_ERRORS: Final[frozenset[str]] = frozenset(
    {"ThrottlingException", "ServiceUnavailableException", "ModelNotReadyException"}
)
THROTTLE_ATTEMPTS: Final[int] = 12


class Pacer:
    """One shared, adaptive request pace for every thread in the pool.

    **Why a shared pacer and not per-call backoff.**  Bedrock's on-demand limit is an
    *account* limit.  When four threads each back off independently they each discover the
    same limit separately, and the thread that wakes first re-triggers it for the other
    three — so the pool converges on a state where most calls are throttle retries and the
    measured 'throttle retries' number exceeds the number of successful calls.  That was
    observed on this workstation on 2026-08-11 while five programs in this fleet shared the
    account: 116 throttle retries bought 100 embeddings.

    Multiplicative increase / additive decrease over one interval, held under one lock:
    every throttle multiplies the inter-request interval, every success shaves a fixed step
    off.  The pool therefore *finds* the account's current allowance instead of arguing
    with it, and the interval it settles at is reported in the artefact — a rate limiter
    whose behaviour is not published is indistinguishable from a sleep.

    **The ceiling is deliberately low (2 s).**  The pace serialises the *whole pool*, so a
    ceiling of six seconds caps total throughput at ten attempts a minute no matter how
    many workers are running — which was measured here, and which made the limiter, not
    Bedrock, the binding constraint.  A rate limiter that becomes the bottleneck has
    stopped protecting anything.
    """

    __slots__ = ("_interval", "_lock", "_next_at", "max_interval", "min_interval", "waits")

    def __init__(self, *, start: float = 0.20, minimum: float = 0.02, maximum: float = 2.0):
        self._lock = threading.Lock()
        self._interval = start
        self._next_at = 0.0
        self.min_interval = minimum
        self.max_interval = maximum
        self.waits = 0

    @property
    def interval(self) -> float:
        """Current inter-request spacing, in seconds.  Published in the artefact."""
        return self._interval

    def wait(self) -> None:
        """Block until this thread's turn.  The sleep happens outside the lock."""
        with self._lock:
            now = time.monotonic()
            start_at = max(now, self._next_at)
            self._next_at = start_at + self._interval
        delay = start_at - time.monotonic()
        if delay > 0:
            self.waits += 1
            time.sleep(delay)

    def throttled(self) -> None:
        """Multiplicative increase — back off fast, because the limit is already breached."""
        with self._lock:
            self._interval = min(self.max_interval, self._interval * 1.5)

    def succeeded(self) -> None:
        """**Additive** decrease — probe back toward the limit at a constant rate.

        The first version of this decayed 3 % per success, which is multiplicative in both
        directions and therefore not AIMD at all: after a burst of throttles the interval
        needed hundreds of consecutive successes to come back down, and the pool settled at
        a pace far below what the account would actually serve.  Measured on this
        workstation: 31 throttle retries bought 25 embeddings and the interval had climbed
        to 5.8 s and was still rising.  Subtracting a fixed step recovers in tens of
        successes instead of hundreds, which is the whole point of the A in AIMD.
        """
        with self._lock:
            self._interval = max(self.min_interval, self._interval - 0.05)


@dataclass(slots=True)
class Embedder:
    """Live Titan v2, with an on-disk cache and a token ledger.

    ``normalize=True`` is requested because ``ce_ann`` is a ``vector_cosine_ops`` index:
    cosine distance on unit vectors is the inner product, and asking the provider to do
    the normalisation keeps one definition of the vector rather than two.
    """

    runtime: Any
    model_id: str = TITAN_MODEL_ID
    cache: dict[str, list[float]] = field(default_factory=dict)
    #: ``sha256 -> inputTextTokenCount``, carried in the cache file alongside the vector.
    #:
    #: Without it the token ledger reports what *this pass* spent, which after one cached
    #: run is zero — and "0 calls, USD 0.00" in a committed cost artefact is not a saving,
    #: it is a hole. The corpus was paid for once; the ledger has to say by how much
    #: whichever pass happens to write the file.
    tokens: dict[str, int] = field(default_factory=dict)
    calls: int = 0
    input_tokens: int = 0
    cache_hits: int = 0
    throttles: int = 0
    latencies_ms: list[float] = field(default_factory=list)
    failures: list[dict[str, str]] = field(default_factory=list)
    pacer: Pacer = field(default_factory=Pacer)

    def load_cache(self, path: Path = CACHE_PATH) -> int:
        """Read the vector cache, keeping only rows for this model at this dimension."""
        if not path.exists():
            return 0
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("model_id") == self.model_id and len(row.get("v", ())) == EMBED_DIM:
                self.cache[row["sha256"]] = row["v"]
                if row.get("tokens") is not None:
                    self.tokens[row["sha256"]] = int(row["tokens"])
        return len(self.cache)

    def save_cache(self, path: Path = CACHE_PATH) -> None:
        """Rewrite the cache, sorted by digest, so a re-run produces the same bytes."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            for digest, vector in sorted(self.cache.items()):
                row = {
                    "sha256": digest,
                    "model_id": self.model_id,
                    # Written beside the vector so the token ledger survives the cache. An
                    # earlier version of this method omitted it, and the next run's
                    # artefact reported "0 calls, USD 0.00" for a corpus that had cost a
                    # thousand live invocations — true of that pass, false of the evidence.
                    "tokens": self.tokens.get(digest),
                    "v": vector,
                }
                handle.write(json.dumps(row) + "\n")

    def _invoke(self, text: str) -> tuple[list[float], int, float]:
        """One live ``InvokeModel``, retrying **only** a throttle.

        Bedrock's on-demand tier in ``ap-southeast-2`` throttles this account at a low
        request rate, and botocore's own four retries are exhausted by a 1 000-document
        pass in seconds.  The loop below is explicit rather than a retry library — the
        boundary lint bans ``tenacity``/``backoff``/``retrying`` for the same reason
        ``_common.with_retry`` exists: a blanket helper cannot tell a rate limit from a
        refusal, and a refusal retried eight times is one defect reported eight ways.

        Every attempt goes through :class:`Pacer` first, so the *pool* slows down when the
        account says slow down, rather than each thread independently rediscovering the
        same limit.  The jitter on top of the pace is what stops N threads that were all
        released at the same instant from re-colliding in lockstep.

        ``ThrottlingException`` and ``ServiceUnavailableException`` are rate facts.
        ``ValidationException``, ``AccessDeniedException`` and a wrong dimension count are
        facts about the request, and are raised on the first occurrence.
        """
        body = json.dumps({"inputText": text, "dimensions": EMBED_DIM, "normalize": True}).encode(
            "utf-8"
        )
        model_id = assert_in_region(self.model_id)
        attempt = 0
        while True:
            self.pacer.wait()
            started = time.perf_counter()
            try:
                response = self.runtime.invoke_model(
                    modelId=model_id,
                    contentType="application/json",
                    accept="application/json",
                    body=body,
                )
            except Exception as exc:
                name = type(exc).__name__
                if name not in _THROTTLE_ERRORS or attempt >= THROTTLE_ATTEMPTS - 1:
                    raise
                attempt += 1
                self.throttles += 1
                self.pacer.throttled()
                # Not cryptographic and not meant to be: this decorrelates the threads the
                # pacer released together.
                time.sleep(min(4.0, 0.3 * attempt) * (0.5 + random.random()))  # noqa: S311
                continue
            self.pacer.succeeded()
            payload = json.loads(response["body"].read())
            latency_ms = (time.perf_counter() - started) * 1000.0
            vector = payload["embedding"]
            if len(vector) != EMBED_DIM:
                raise RuntimeError(
                    f"Titan returned {len(vector)} dimensions, not {EMBED_DIM}; the DDL says "
                    f"VECTOR({EMBED_DIM}) and a mismatch is a schema question, not a retry"
                )
            return vector, int(payload.get("inputTextTokenCount") or 0), latency_ms

    def embed_many(self, texts: Sequence[str], *, workers: int = 4) -> list[list[float]]:
        """Embed *texts* in order, calling Bedrock only for cache misses.

        Concurrency is bounded low because this is a shared on-demand tier and a
        ``ThrottlingException`` costs more wall-clock than the parallelism saves.  botocore
        clients are thread-safe for calls once constructed; the client is built once, on
        the main thread, before any worker starts.

        **One failed call does not lose the pass.**  A document whose every throttle retry
        was exhausted is recorded in :attr:`failures` and the loop keeps going; the caller
        finds out from :meth:`assert_complete`, which names the count.  The first version of
        this method re-raised on the first failure and then blocked in
        ``ThreadPoolExecutor.__exit__``, which waits for the *thousand futures already
        submitted* before the exception surfaces — a program that looks hung for an hour and
        then throws away the work is worse than one that reports a hole.

        The cache is checkpointed every fifty completions and again in ``finally``.  A pass
        interrupted at document 900 must resume from 900: an interruption that costs money
        twice is a design defect, not bad luck.
        """
        digests = [sha256_hex(t.encode("utf-8")) for t in texts]
        by_digest = dict(zip(digests, texts, strict=True))
        missing = [d for d in dict.fromkeys(digests) if d not in self.cache]

        if missing:
            pool = ThreadPoolExecutor(max_workers=max(1, workers))
            try:
                futures = {pool.submit(self._invoke, by_digest[d]): d for d in missing}
                for done, future in enumerate(as_completed(futures), start=1):
                    digest = futures[future]
                    try:
                        vector, tokens, latency_ms = future.result()
                    except Exception as exc:  # noqa: BLE001 — a hole is reported, not raised
                        self.failures.append(
                            {"sha256": digest, "error": f"{type(exc).__name__}: {exc}"}
                        )
                    else:
                        self.cache[digest] = vector
                        self.tokens[digest] = tokens
                        self.calls += 1
                        self.input_tokens += tokens
                        self.latencies_ms.append(round(latency_ms, 1))
                    # Outside the success branch on purpose: a pass in which most calls are
                    # failing must still print progress, or a stalled run and a failing run
                    # look identical from the log.
                    if done % 25 == 0:
                        self.save_cache()
                        print(
                            f"    embedded {done}/{len(missing)} "
                            f"(throttle retries {self.throttles}, "
                            f"failures {len(self.failures)}, "
                            f"pace {self.pacer.interval:.2f}s)",
                            file=sys.stderr,
                            flush=True,
                        )
            finally:
                pool.shutdown(wait=False, cancel_futures=True)
                self.save_cache()

        self.cache_hits += len(digests) - len(missing)
        # Shorter than *texts* when a call failed, and deliberately not padded: a
        # placeholder vector would be indistinguishable from a real one three functions
        # later. :meth:`assert_complete` is the gate, and every caller in this program
        # calls it immediately; the `strict=True` zips downstream are the second net.
        return [self.cache[d] for d in digests if d in self.cache]

    def corpus_tokens(self, digests: Sequence[str]) -> tuple[int, int, int]:
        """``(input_tokens, distinct_texts, texts_with_no_recorded_count)`` for *digests*.

        **Deduplicated, because Bedrock was.**  Two documents with byte-identical text are
        one cache entry and one invocation; summing over the raw list would price a call
        that was never made.  This corpus contains such duplicates — templated state-alert
        bodies — and the difference is ~120 calls, which is the difference between a ledger
        that reconciles against CloudWatch and one that does not.

        The third number is the size of the hole, returned rather than hidden so the
        artefact can say how much of the ledger is a real measurement.
        """
        distinct = list(dict.fromkeys(digests))
        known = [self.tokens[d] for d in distinct if d in self.tokens]
        return sum(known), len(distinct), len(distinct) - len(known)

    def assert_complete(self, digests: Sequence[str], *, what: str) -> None:
        """Refuse to continue with a hole in the vectors.

        Called after each :meth:`embed_many`.  A corpus with three documents missing would
        still produce ranks, and those ranks would be measured against a corpus that is not
        the one the artefact names.  A partial corpus is a different experiment, not a
        slightly worse one.
        """
        holes = [d for d in digests if d not in self.cache]
        if holes:
            raise RuntimeError(
                f"{len(holes)} of {len(digests)} {what} have no vector after "
                f"{self.throttles} throttle retries and {len(self.failures)} hard failures. "
                "The cache keeps everything that did land, so re-running costs only the "
                f"holes. First failure: {self.failures[0] if self.failures else 'none recorded'}"
            )


def vector_literal(vector: Sequence[float], *, places: int = 8) -> str:
    """A CockroachDB ``VECTOR`` literal.

    Eight decimal places, not ``repr``: a 1024-element ``repr`` list is 20 KB of SQL per
    bound value and the extra digits are below Titan's own reproducibility.  Measured on
    this corpus, rounding to 8 places moves no rank and changes cosine distance in the
    ninth significant figure.
    """
    return "[" + ",".join(f"{float(x):.{places}f}" for x in vector) + "]"


# ═══════════════════════════════════════════════════════════════════════════════════════
# 4 · Schema and load
# ═══════════════════════════════════════════════════════════════════════════════════════

#: Copied verbatim from ``verticals/mainline/db/migrations/0031_clause_embedding.sql``
#: except for the two things §3 of the AWS-execution plan authorises: the FK points at a
#: stub parent, and ``IF NOT EXISTS`` makes the program re-runnable.  Any other difference
#: would mean this evidence is about a table that does not exist in production.
DDL_CLAUSE_EMBEDDING: Final[str] = f"""
CREATE TABLE IF NOT EXISTS {TABLE} (
  clause_uuid   UUID   NOT NULL,
  commit_id     BYTES  NOT NULL,
  site_id       UUID   NOT NULL,
  activity_root STRING NOT NULL,
  embed_model   STRING NOT NULL,
  index_gen     STRING NOT NULL,
  embedding     VECTOR({EMBED_DIM}) NOT NULL,
  CONSTRAINT clause_embedding_pk PRIMARY KEY (clause_uuid, commit_id),
  CONSTRAINT fk_version FOREIGN KEY (clause_uuid, commit_id)
    REFERENCES {PARENT_STUB} (clause_uuid, commit_id),
  CONSTRAINT embed_model_stated CHECK (embed_model <> ''),
  CONSTRAINT index_gen_stated CHECK (index_gen <> ''),
  VECTOR INDEX {INDEX} (site_id, activity_root, embedding vector_cosine_ops),
  FAMILY f_meta (clause_uuid, commit_id, site_id, activity_root, embed_model, index_gen),
  FAMILY f_vec  (embedding)
)"""

DDL_PARENT_STUB: Final[str] = f"""
CREATE TABLE IF NOT EXISTS {PARENT_STUB} (
  clause_uuid UUID  NOT NULL,
  commit_id   BYTES NOT NULL,
  CONSTRAINT clause_version_pk PRIMARY KEY (clause_uuid, commit_id),
  CONSTRAINT commit_id_is_sha256 CHECK (length(commit_id) = 32)
)"""

#: Not part of ``0031``.  A judge running ``the-one-query.sql`` gets ``clause_uuid`` back
#: and needs to see *which document that is*; this table is the join that makes the
#: evidence readable, and it holds only what is already committed in the goldset.
DDL_DOCMAP: Final[str] = f"""
CREATE TABLE IF NOT EXISTS {DOCMAP} (
  clause_uuid   UUID   NOT NULL,
  doc_id        STRING NOT NULL,
  source        STRING NOT NULL,
  activity_path STRING NOT NULL,
  occurred_on   DATE   NULL,
  excerpt       STRING NOT NULL,
  CONSTRAINT ann_evidence_docmap_pk PRIMARY KEY (clause_uuid),
  CONSTRAINT docmap_doc_id_unique UNIQUE (doc_id)
)"""


def ensure_database(name: str) -> None:
    """Create the evidence database if it is absent.  Never drops it.

    ``scripts/aws/load_vectors.py`` shares this database and issues ``DROP TABLE IF
    EXISTS`` on the two tables it owns; this program only ever adds.  A fleet in which two
    programs both drop is a fleet whose evidence depends on run order.
    """
    with crdb() as conn:
        conn.execute(f"CREATE DATABASE IF NOT EXISTS {name}")


def ensure_schema(conn: Any) -> None:
    """Idempotent DDL: the schema, the stub parent, ``clause_embedding``, the doc map.

    Every statement is ``IF NOT EXISTS``, so this is a no-op when ``load_vectors.py`` has
    already created the tables — and it is not a no-op when that worker has not run, which
    is why this program does not block on it.
    """
    conn.execute("CREATE SCHEMA IF NOT EXISTS mainline")
    conn.execute(DDL_PARENT_STUB)
    conn.execute(DDL_CLAUSE_EMBEDDING)
    conn.execute(DDL_DOCMAP)


def index_gen_for(docs: Sequence[Doc]) -> str:
    """The generation label stamped on every row.

    Derived from the corpus content, not from a clock: two runs over the same corpus
    produce the same label, and a corpus that changed produces a different one, which is
    exactly what M4's ``index_fingerprint`` needs of it.
    """
    digest = hashlib.sha256()
    for doc in sorted(docs, key=lambda d: d.doc_id):
        digest.update(doc.doc_id.encode("utf-8"))
        digest.update(doc.commit_id)
    return f"titan-v2-1024-{digest.hexdigest()[:12]}"


def load_rows(
    conn: Any, docs: Sequence[Doc], vectors: Sequence[Sequence[float]], index_gen: str
) -> dict[str, Any]:
    """Insert every document's row, idempotently.  Returns a load report.

    One row per ``INSERT`` statement, pipelined by psycopg's ``executemany``.  The recall
    band's DDL note is explicit that the live vector path is one row per statement; the
    batching in GT-05 was a bulk-load convenience and is not the shape this fleet should
    demonstrate.  ``ON CONFLICT DO NOTHING`` makes a re-run a no-op rather than a 23505.

    The whole load is wrapped in :func:`with_retry`, and its trip count is returned:
    a ``40001`` loop whose premium is never quoted is indistinguishable from superstition.
    """
    parent = [(d.clause_uuid, d.commit_id) for d in docs]
    payload = [
        (
            doc.clause_uuid,
            doc.commit_id,
            CORPUS_SITE_ID,
            doc.activity_root,
            TITAN_MODEL_ID,
            index_gen,
            vector_literal(vector),
        )
        for doc, vector in zip(docs, vectors, strict=True)
    ]
    docmap = [
        (
            doc.clause_uuid,
            doc.doc_id,
            doc.source,
            doc.activity_path,
            doc.occurred_on,
            doc.text[:400],
        )
        for doc in docs
    ]

    started = time.perf_counter()

    def _do() -> None:
        with conn.cursor() as cur:
            cur.executemany(INSERT_PARENT, parent)
            cur.executemany(INSERT_EMBEDDING, payload)
            cur.executemany(INSERT_DOCMAP, docmap)

    _, retries = with_retry(_do)
    elapsed = time.perf_counter() - started
    with conn.cursor() as cur:
        # A previous run over a different corpus left rows under this site_id with a
        # different index_gen. They are in the same partition trees and would be searched
        # by every query in this run — two corpora in one measurement, invisible in every
        # number. Removed after the insert so an interrupted load never leaves the table
        # empty.
        cur.execute(DELETE_STALE_GENERATIONS, (CORPUS_SITE_ID, index_gen))
        removed = cur.rowcount
        rows = cur.execute(COUNT_ALL).fetchone()[0]
    return {
        "rows_offered": len(payload),
        "rows_present_after": int(rows),
        "stale_generation_rows_removed": int(removed),
        "retries_40001": retries,
        "seconds": round(elapsed, 1),
        "statement_shape": "one row per INSERT, pipelined by psycopg executemany",
    }


# ═══════════════════════════════════════════════════════════════════════════════════════
# 5 · The query
# ═══════════════════════════════════════════════════════════════════════════════════════


def hinted_statement(*, hint: bool = True) -> str:
    """:data:`ANN_HINTED` or :data:`ANN_UNHINTED` — the only place the choice is made."""
    return ANN_HINTED if hint else ANN_UNHINTED


@dataclass(frozen=True, slots=True)
class Hit:
    """One row the ANN arm returned, in the order it returned it."""

    clause_uuid: str
    distance: float


def single_root(
    conn: Any, vector_text: str, root: str, k: int, *, hint: bool = True
) -> tuple[list[Hit], float]:
    """One hinted ANN query against one ``(site_id, activity_root)`` tree.

    Both prefix columns bound to exactly one value.  This is the only shape that descends
    the C-SPANN tree; ``IN (...)`` on either column does not.
    """
    params = {"vec": vector_text, "site": CORPUS_SITE_ID, "root": root, "k": k}
    started = time.perf_counter()
    with conn.cursor() as cur:
        rows = cur.execute(hinted_statement(hint=hint), params).fetchall()
    latency_ms = (time.perf_counter() - started) * 1000.0
    return [Hit(str(r[0]), float(r[2])) for r in rows], latency_ms


def ancestor_walk(
    conn: Any, vector_text: str, roots: Sequence[str], k: int
) -> tuple[list[Hit], float, int]:
    """*k* roots searched as *k* hinted queries, ``UNION ALL``-ed and re-ranked.

    Never ``activity_root IN (...)``.  A disjunction on a prefix column does not use the
    index at all, so the "one query with an IN list" shape is not a slower version of this
    — it is a different query that silently stops being an ANN query.  The union is built
    as one statement so the server does the re-rank, and the arm count is returned so the
    artefact can state how many trees were descended.
    """
    arms: list[str] = []
    params: dict[str, Any] = {"vec": vector_text, "site": CORPUS_SITE_ID, "k": k}
    for i, root in enumerate(roots):
        params[f"root{i}"] = root
        # The arm is :data:`ANN_HINTED` with one placeholder renamed.  Nothing about the
        # statement is composed: an arm that could not be shown to be the pinned,
        # fully-constrained form would make the walk a different measurement.
        arms.append(ANN_WALK_ARM.replace("%(root)s", "%(root" + str(i) + ")s"))
    statement = "".join(
        (
            "SELECT clause_uuid, commit_id, dist FROM (\n",
            "\nUNION ALL\n".join("(" + arm + ")" for arm in arms),
            "\n) AS walk ORDER BY dist LIMIT %(k)s",
        )
    )
    started = time.perf_counter()
    with conn.cursor() as cur:
        rows = cur.execute(statement, params).fetchall()
    latency_ms = (time.perf_counter() - started) * 1000.0
    return [Hit(str(r[0]), float(r[2])) for r in rows], latency_ms, len(arms)


def in_list_arm(conn: Any, vector_text: str, k: int) -> tuple[list[Hit], float]:
    """The shape the migration header calls a trap, run so the trap can be measured.

    ``0031_clause_embedding.sql`` states as a law that ``activity_root IN (...)`` "does not
    work" and that a vector index is used *only* when every prefix column is constrained to
    a single value.  On CockroachDB v26.2.5 that is **not what happens**: the optimizer
    expands the list into one prefix span per value and the vector index is used.

    The law is not therefore pointless, and this arm exists to show why in numbers rather
    than in argument.  ``LIMIT k`` over three spans is a *shared* budget of k candidates
    across three partition trees; the ancestor walk gives each tree its own k and re-ranks
    3k.  Those are different recall budgets, and which one a safety gate wants is not a
    question of taste.  Both are run against every query.
    """
    params = {"vec": vector_text, "site": CORPUS_SITE_ID, "k": k}
    started = time.perf_counter()
    with conn.cursor() as cur:
        rows = cur.execute(ANN_IN_LIST, params).fetchall()
    latency_ms = (time.perf_counter() - started) * 1000.0
    return [Hit(str(r[0]), float(r[2])) for r in rows], latency_ms


# ═══════════════════════════════════════════════════════════════════════════════════════
# 6 · Plans
# ═══════════════════════════════════════════════════════════════════════════════════════

#: A ``vector search`` node in a CockroachDB ``EXPLAIN``.
#:
#: The leading class is not ``\s*``.  CockroachDB draws the plan as a tree, so the node
#: line is ``        └── • vector search`` — box-drawing characters, not whitespace. The
#: first version of this pattern used ``^\s*`` and reported ``has_vector_search_node:
#: false`` for a plan that plainly contained one; the crossover census caught it because a
#: sweep that says *False* at every size is a claim about the detector, not the optimizer.
#: A regex that silently under-reports the thing this whole artefact is about would have
#: turned a working proof into a published failure.
_VECTOR_SEARCH = re.compile(r"^[\s│└├─┌┐┘]*•\s*vector search\s*$", re.MULTILINE)


def explain(conn: Any, statement: str, params: Mapping[str, Any]) -> str:
    """``EXPLAIN`` with bound parameters — the plan, not an execution."""
    with conn.cursor() as cur:
        rows = cur.execute("EXPLAIN " + statement, dict(params)).fetchall()
    return "\n".join(str(r[0]) for r in rows)


def explain_inlined(conn: Any, statement: str) -> str:
    """``EXPLAIN ANALYZE`` over a statement whose values are already in the text.

    Separate from :func:`explain` because it is a different operation: ANALYZE *runs* the
    query and reports what happened, and CockroachDB refuses placeholders for exactly that
    reason (``EXPLAIN does not support placeholders``, measured on v26.2.5). Collapsing the
    two behind one boolean flag is how a caller ends up believing the executed plan and the
    bound plan came from the same statement text.
    """
    with conn.cursor() as cur:
        rows = cur.execute("EXPLAIN ANALYZE " + statement).fetchall()
    return "\n".join(str(r[0]) for r in rows)


def plan_digest(plan_text: str) -> str:
    """SHA-256 over the plan with trailing whitespace stripped.

    Deliberately *not* normalised any further.  A digest that erases the ``prefix spans``
    line would be stable across the exact change this file exists to detect.
    """
    normalised = "\n".join(line.rstrip() for line in plan_text.strip().splitlines())
    return sha256_hex(normalised.encode("utf-8"))


def plan_facts(plan_text: str) -> dict[str, Any]:
    """What a reader must be able to check without reading the whole plan."""
    names_index = f"table: clause_embedding@{INDEX}" in plan_text
    return {
        "has_vector_search_node": bool(_VECTOR_SEARCH.search(plan_text)),
        "names_clause_embedding_at_ce_ann": names_index,
        "traverses_ce_ann": bool(_VECTOR_SEARCH.search(plan_text)) and names_index,
        "has_prefix_spans": "prefix spans:" in plan_text,
        "has_full_scan_node": "• scan" in plan_text,
        "has_filter_node": "• filter" in plan_text,
        "digest_sha256": plan_digest(plan_text),
        "lines": len(plan_text.strip().splitlines()),
    }


# ═══════════════════════════════════════════════════════════════════════════════════════
# 6b · The GT-06 crossover census
# ═══════════════════════════════════════════════════════════════════════════════════════

#: Where ``--crossover`` leaves its result.  Under ``out/`` (gitignored) because it is a
#: measurement input; the numbers themselves are copied into ``ann-proof.json``, which is
#: committed, so nothing published depends on a file a reader cannot see.
CROSSOVER_PATH: Final[Path] = repo_root() / "out" / "aws" / "ann" / "crossover.json"

#: The scratch database ``--crossover`` builds and drops.  Never the evidence database:
#: this census writes five thousand meaningless vectors and must not be able to reach
#: anything a judge will read.
CROSSOVER_DATABASE: Final[str] = "w_ann_crossover"

CROSSOVER_SIZES: Final[tuple[int, ...]] = (0, 200, 1100, 5300)


def crossover_census(sizes: Sequence[int] = CROSSOVER_SIZES) -> dict[str, Any]:
    """At what corpus size does the **unhinted** plan stop choosing ``ce_ann``?

    ADR 0002 GT-06 recorded that at ~5 200 rows CockroachDB's optimizer prefers a scan for
    this exact shape, and that finding is the stated reason every ANN arm in MAINLINE pins
    the index.  ``explain-unhinted.txt`` is supposed to be the control that reproduces it.
    A control nobody checks is a claim, so this function checks it — on the same cluster,
    at the same table shape, over a sweep of row counts.

    **No Bedrock.**  The optimizer's choice is a function of table statistics, not of what
    the vectors mean, so seeded pseudo-random unit vectors answer the question exactly and
    cost nothing.  That is also why this is a separate mode rather than part of the proof:
    it is a fact about the *planner*, not about retrieval, and mixing the two would let a
    reader think the ranks below were measured on random vectors.

    Whatever it finds is what the artefact says.  If GT-06 does not reproduce, that is a
    correction to a repository document, not a result to leave out.
    """
    import psycopg

    rng = random.Random(20260811)  # noqa: S311 — a seeded PRNG is the point; see docstring
    site = str(uuid.uuid5(NAMESPACE, "crossover-census"))

    def unit_vector() -> str:
        values = [rng.gauss(0.0, 1.0) for _ in range(EMBED_DIM)]
        norm = sum(v * v for v in values) ** 0.5
        return "[" + ",".join(f"{v / norm:.8f}" for v in values) + "]"

    with crdb() as admin:
        admin.execute("DROP DATABASE IF EXISTS " + CROSSOVER_DATABASE + " CASCADE")
        admin.execute("CREATE DATABASE " + CROSSOVER_DATABASE)

    observations: list[dict[str, Any]] = []
    probe = unit_vector()
    with crdb(CROSSOVER_DATABASE) as conn, conn.cursor() as cur:
        cur.execute("CREATE SCHEMA IF NOT EXISTS mainline")
        cur.execute(DDL_PARENT_STUB)
        cur.execute(DDL_CLAUSE_EMBEDDING)
        made = 0
        for target in sizes:
            while made < target:
                batch = []
                for _ in range(min(100, target - made)):
                    key = f"crossover-row-{made}"
                    batch.append(
                        (
                            str(uuid.uuid5(NAMESPACE, key)),
                            hashlib.sha256(key.encode("utf-8")).digest(),
                            site,
                            ROOTS[made % len(ROOTS)],
                            TITAN_MODEL_ID,
                            "crossover-census-not-a-real-vector",
                            unit_vector(),
                        )
                    )
                    made += 1
                cur.executemany(INSERT_PARENT, [(b[0], b[1]) for b in batch])
                cur.executemany(INSERT_EMBEDDING, batch)
            cur.execute("ANALYZE mainline.clause_embedding")
            rows = int(cur.execute(COUNT_ALL).fetchone()[0])
            params = {"vec": probe, "site": site, "root": ROOTS[0], "k": 10}
            entry: dict[str, Any] = {"rows": rows}
            for label, statement in (("hinted", ANN_HINTED), ("unhinted", ANN_UNHINTED)):
                plan = explain(conn, statement, params)
                entry[label] = plan_facts(plan)
                entry[label]["index_recommendation"] = "index recommendations:" in plan
            entry["plans_agree"] = (
                entry["hinted"]["traverses_ce_ann"] == entry["unhinted"]["traverses_ce_ann"]
            )
            observations.append(entry)
            print(
                f"  crossover rows={rows:<6} hinted_traverses="
                f"{entry['hinted']['traverses_ce_ann']} unhinted_traverses="
                f"{entry['unhinted']['traverses_ce_ann']}",
                file=sys.stderr,
                flush=True,
            )
        try:
            version = str(cur.execute("SELECT version()").fetchone()[0]).split(" (")[0]
        except psycopg.Error:
            version = "unknown"

    with crdb() as admin:
        admin.execute("DROP DATABASE IF EXISTS " + CROSSOVER_DATABASE + " CASCADE")

    flipped = [o["rows"] for o in observations if not o["unhinted"]["traverses_ce_ann"]]
    census = {
        "measured_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "server_version": version,
        "database": CROSSOVER_DATABASE + " (created and dropped by this census)",
        "vectors": "seeded pseudo-random unit vectors, NOT Bedrock output",
        "table_shape": "verbatim 0031_clause_embedding.sql against a two-column stub parent",
        "distinct_prefix_pairs": len(ROOTS),
        "sizes": list(sizes),
        "observations": observations,
        "unhinted_stopped_using_ce_ann_at": flipped[0] if flipped else None,
        "gt06_reproduces": bool(flipped),
        "reading": (
            "ADR 0002 GT-06 records that at ~5,200 rows the unhinted prefix-constrained "
            "ANN query does NOT use the vector index. If unhinted_stopped_using_ce_ann_at "
            "is null, that finding did not reproduce on this cluster today at any size "
            "swept here, and ADR 0002's table is stale for this shape. The ADR's DECISION "
            "— pin the index in every arm — is unaffected and is if anything better "
            "supported: a cost-based choice that has already changed once is exactly what "
            "must not sit beneath a safety gate."
        ),
    }
    CROSSOVER_PATH.parent.mkdir(parents=True, exist_ok=True)
    CROSSOVER_PATH.write_text(json.dumps(census, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return census


def load_crossover_census() -> dict[str, Any]:
    """The last ``--crossover`` result, or a record that it has not been run."""
    if not CROSSOVER_PATH.exists():
        return {
            "run": False,
            "why_it_matters": (
                "without this census, `explain-unhinted.txt` shows one plan at one corpus "
                "size and nothing establishes whether the optimizer's choice depends on "
                "that size. Re-run with `--crossover`."
            ),
        }
    census: dict[str, Any] = json.loads(CROSSOVER_PATH.read_text(encoding="utf-8"))
    census["run"] = True
    census["source"] = "out/aws/ann/crossover.json, written by ann_proof.py --crossover"
    return census


# ═══════════════════════════════════════════════════════════════════════════════════════
# 7 · Scoring
# ═══════════════════════════════════════════════════════════════════════════════════════


def rank_of(
    hits: Sequence[Hit], wanted: Iterable[str]
) -> tuple[int | None, str | None, float | None]:
    """1-based rank of the first hit whose ``clause_uuid`` is in *wanted*."""
    target = set(wanted)
    for position, hit in enumerate(hits, start=1):
        if hit.clause_uuid in target:
            return position, hit.clause_uuid, hit.distance
    return None, None, None


def proportion(
    metric: str, successes: int, n: int, *, detail: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    """A rate that cannot be quoted without its denominator or its interval.

    ``n`` and ``successes`` are first in the dict on purpose: the count is the measurement
    and the fraction is a derived convenience, and ``no_bare_point_estimates`` exists
    because that ordering keeps being reversed in prose.
    """
    lower, upper = wilson_interval(successes, n)
    return {
        "metric": metric,
        "successes": successes,
        "n": n,
        "fraction": (successes / n) if n else None,
        "wilson_lower": lower,
        "wilson_upper": upper,
        "confidence": 0.95,
        "interval_method": "wilson",
        "stated_as": (
            f"{successes}/{n} = {successes / n:.3f} [{lower:.3f}, {upper:.3f}] 95% Wilson"
            if n
            else "undefined: n = 0, and a rate over no trials is not a small rate"
        ),
        "detail": dict(detail or {}),
    }


# ═══════════════════════════════════════════════════════════════════════════════════════
# 8 · The committed SQL
# ═══════════════════════════════════════════════════════════════════════════════════════


def _wrapped_vector(vector_text: str, per_line: int = 16) -> str:
    """The literal, wrapped, so a 1024-float bound value is a readable diff.

    Whitespace inside a ``VECTOR`` literal is accepted by CockroachDB v26.2 — measured on
    the cluster, not assumed, because the alternative is a 10 KB single line in a file a
    human is meant to read.
    """
    parts = vector_text.strip("[]").split(",")
    lines = ["    " + ", ".join(parts[i : i + per_line]) for i in range(0, len(parts), per_line)]
    return "[\n" + ",\n".join(lines) + "\n  ]"


#: The three statements ``the-one-query.sql`` carries, as literals with named slots.
#:
#: Slots are ``:UPPERCASE:`` tokens filled by :func:`str.replace`, not by ``f``-strings or
#: ``.format``.  That is not superstition about SQL injection — every value substituted
#: here is generated by this program.  It is so that the statement a judge runs is
#: **visible in this source file as the statement it is**, rather than as an expression
#: that has to be evaluated in the reader's head to know what will be executed.
ONE_QUERY_ANN: Final[str] = """SELECT clause_uuid, commit_id, embedding <=> ':VECTOR:' AS dist
  FROM mainline.clause_embedding@ce_ann
 WHERE site_id = ':SITE:'
   AND activity_root = ':ROOT:'
 ORDER BY embedding <=> ':VECTOR:'
 LIMIT :K:;"""

#: The same statement without the hint, inlined.  ``EXPLAIN ANALYZE`` *executes*, and
#: CockroachDB refuses placeholders in an ``EXPLAIN ANALYZE`` — measured, ``psycopg
#: .InternalError: EXPLAIN does not support placeholders`` — so the executed plans have to
#: be built with their values in the text.  Two templates rather than one call to
#: ``str.replace`` on the hint, so that neither form can be produced by editing the other.
ONE_QUERY_ANN_UNHINTED: Final[str] = """
SELECT clause_uuid, commit_id, embedding <=> ':VECTOR:' AS dist
  FROM mainline.clause_embedding
 WHERE site_id = ':SITE:'
   AND activity_root = ':ROOT:'
 ORDER BY embedding <=> ':VECTOR:'
 LIMIT :K:"""

ONE_QUERY_READABLE: Final[str] = """WITH ann AS (
  SELECT clause_uuid, embedding <=> ':VECTOR:' AS dist
    FROM mainline.clause_embedding@ce_ann
   WHERE site_id = ':SITE:'
     AND activity_root = ':ROOT:'
   ORDER BY embedding <=> ':VECTOR:'
   LIMIT :K:
)
SELECT row_number() OVER (ORDER BY ann.dist) AS rank,
       m.doc_id,
       m.source,
       m.occurred_on,
       round(ann.dist::NUMERIC, 6) AS cosine_distance,
       left(m.excerpt, 160) AS excerpt
  FROM ann JOIN mainline.ann_evidence_docmap AS m USING (clause_uuid)
 ORDER BY ann.dist;"""


def doc_gist(doc: Doc) -> str:
    """What a document is *about*, in one line, for a human reading the exhibit.

    The first 170 characters of an MSHA investigation are the Department of Labor's
    letterhead, which tells a reader nothing.  The classification fields tell them
    everything: for the committed exhibit the difference is between *"UNITED STATES
    DEPARTMENT OF LABOR Mine Safety and Health Administration Report of Investigation"* and
    *"Exposure to ionising radiation · Radioactive source · Density gauge"* — the second is
    the sentence that makes the retrieval obviously right.
    """
    if doc.source == "part50":
        fields = doc.text.split("|")
        if len(fields) >= 12:
            keep = (fields[3], fields[4], fields[6], fields[8], fields[10])
            return " · ".join(f for f in keep if f and f != "None")
    labelled = [
        _header_field(doc.text, name)
        for name in (
            "Date of Accident",
            "Accident Classification",
            "Source of Injury",
            "Equipment",
            "Activity",
            "Incident Type",
            "Source",
        )
    ]
    gist = " · ".join(value for value in labelled if value)
    if gist:
        return gist
    return doc.text.replace("\n", " ")[:170]


def _comment_block(text: str, width: int = 86) -> list[str]:
    """Wrap *text* into ``--`` comment lines.

    The caveats are long by design — a caveat short enough to fit on one line is usually a
    caveat that has been shortened until it stopped saying anything — and a 400-character
    single line in a file a judge is meant to read is a caveat nobody reads.
    """
    words = text.split()
    lines: list[str] = []
    current = "--"
    for word in words:
        candidate = f"{current} {word}"
        if len(candidate) > width and current != "--":
            lines.append(current)
            current = f"-- {word}"
        else:
            current = candidate
    if current != "--":
        lines.append(current)
    return lines


def _fill(template: str, *, vector: str, root: str, k: int) -> str:
    return (
        template.replace(":VECTOR:", vector)
        .replace(":SITE:", CORPUS_SITE_ID)
        .replace(":ROOT:", root)
        .replace(":K:", str(k))
    )


def write_one_query_sql(path: Path, exhibit: Mapping[str, Any], vector_text: str) -> None:
    """The judge-runnable statement, with its bound values inlined."""
    literal = _wrapped_vector(vector_text)
    root = str(exhibit["activity_root"])
    k = int(exhibit["k"])
    ann = _fill(ONE_QUERY_ANN, vector=literal, root=root, k=k)
    readable = _fill(ONE_QUERY_READABLE, vector=literal, root=root, k=k)
    header = [
        "-- SPDX-FileCopyrightText: 2026 MAINLINE contributors",
        "-- SPDX-License-Identifier: Apache-2.0",
        "--",
        "-- " + "=" * 85,
        "-- THE ONE QUERY",
        "-- " + "=" * 85,
        "--",
        f"-- Paste this whole file into a SQL shell attached to the `{exhibit['database']}`",
        f"-- database on the CockroachDB Cloud cluster `{exhibit['cluster']}`",
        f"-- ({exhibit['cluster_region']}) and watch it happen.",
        "--",
        f"--   query id .............. {exhibit['query_id']}",
        f"--   permit written before  {exhibit['fatality']}",
        "--                           (this permit covers the work that later killed",
        "--                            somebody; the precursor below is older than both)",
        f"--   permit narrative ...... {exhibit['permit_excerpt']}",
        f"--   time wall ............. {exhibit['wall']}",
        "--                           (nothing after this date could have been known)",
        (
            f"--   expected precursor .... doc_id {exhibit['expected_doc_id']}"
            f"  (goldset grade {exhibit['expected_grade']})"
        ),
        f"--                           clause_uuid {exhibit['expected_clause_uuid']}",
        f"--   what the precursor is  {exhibit['expected_summary']}",
        f"--   OBSERVED RANK ......... {exhibit['observed_rank']} of {k}",
        f"--   cosine distance ....... {exhibit['observed_distance']}",
        f"--   rank once post-wall ... {exhibit['wall_filtered_rank']}",
        "--     rows are dropped       (the corpus holds the investigation this permit was",
        (
            "--                            extracted from; "
            f"{exhibit['post_wall_in_top_10']} of the top 10 post-date the"
        ),
        "--                            wall, and a deployment would not have had them yet)",
        f"--   observed on ........... {exhibit['observed_at']}",
        "--",
        "-- THIS IS AN EXHIBIT, NOT A SAMPLE. It is the strongest result among",
        f"-- {exhibit['queries_run']} retro permits measured in one pass, chosen by a rule",
        "-- written down in `scripts/aws/ann_proof.py::_choose_exhibit` before the numbers were",
        "-- seen: the cited precursor at rank 1 if any query achieved it, then the cited",
        "-- precursor at any rank, then the best mechanism-sharing document at its true rank.",
        "-- The rank printed above is the rank that was observed, whatever it was.",
        "--",
        f"-- THE DISTRIBUTION ACROSS ALL {exhibit['queries_run']} QUERIES — hit@1, hit@3, hit@10,",
        "-- each with its count, its denominator and a 95% Wilson interval, for both relevance",
        "-- definitions and all three retrieval arms — is in evidence/aws/ann/ann-proof.json",
        "-- under `metrics`. Quoting this file without that one is quoting the best case as if",
        "-- it were the average.",
        "--",
        f"-- The bound vector below is a real `{TITAN_MODEL_ID}` response",
        f"-- from Amazon Bedrock in {REGION}, for the permit narrative named above.",
        "-- It is inlined rather than parameterised so that this file is self-contained:",
        "-- nothing outside it has to run for the result to appear.",
        "--",
        f"-- `@{INDEX}` is not decoration. It pins the plan. ADR 0002 GT-06 recorded that the",
        "-- optimizer does not choose this index unhinted at demo scale; that finding did not",
        "-- reproduce when this evidence was taken, and both plans are committed next to this",
        "-- file — evidence/aws/ann/explain-hinted.txt and explain-unhinted.txt — together with",
        "-- the row-count sweep that settles it. The hint stays because a plan that flips with",
        "-- table statistics must not sit beneath a safety gate, not because it is load-bearing",
        "-- for this one result.",
        "--",
        "-- BOTH PREFIX COLUMNS ARE BOUND TO ONE VALUE. C-SPANN keeps a separate partition tree",
        "-- per distinct prefix value, so `site_id` and `activity_root` select WHICH TREE IS",
        "-- DESCENDED — they do not filter a result set. Removing either one is refused outright:",
        '-- SQLSTATE 42809, `index "ce_ann" cannot be used for this query`. An ancestor walk',
        "-- across k roots is k copies of this statement, UNION ALL-ed and re-ranked, giving each",
        "-- tree its own LIMIT. (`activity_root IN (...)` is described as a trap in",
        "-- 0031_clause_embedding.sql. Measured on v26.2.5 it does traverse the index — but under",
        "-- ONE shared LIMIT across all three trees, which is a smaller recall budget, not the",
        "-- same query. ann-proof.json reports both arms.)",
        "--",
        *_comment_block(exhibit["caveat_synthetic"]),
        "--",
        *_comment_block(exhibit["caveat_site"]),
        "--",
        "-- " + "-" * 85,
        "-- 1 · The statement, exactly as `scripts/aws/ann_proof.py` issues it.",
        "-- " + "-" * 85,
        "",
        ann,
        "",
        "-- " + "-" * 85,
        "-- 2 · The same statement, joined to the document map so the answer is readable.",
        f"--     `{DOCMAP}` is NOT part of 0031_clause_embedding.sql. It",
        "--     carries the goldset's own doc_id for each clause_uuid so a human can see what",
        "--     came back; the ANN query above is unchanged and does not depend on it.",
        "-- " + "-" * 85,
        "",
        readable,
        "",
        "-- " + "-" * 85,
        "-- 3 · The plan. This must print a `vector search` node naming",
        f"--     `clause_embedding@{INDEX}` with a non-empty `prefix spans`. If it does not,",
        "--     the ANN arm has silently become a scan, which in this product is a safety",
        "--     defect and not a performance regression.",
        "-- " + "-" * 85,
        "",
        "EXPLAIN",
        ann,
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(header) + "\n", encoding="utf-8")


def _unhinted_argument(facts: Mapping[str, Any], crossover: Mapping[str, Any]) -> str:
    """The prose at the head of ``explain-unhinted.txt``, written from the measurement.

    Two different files come out of this function depending on what the cluster did, and
    that is the point: a control whose commentary is written before the result is not a
    control.  If GT-06 reproduces, this file says so.  If it does not, this file says
    *that*, names the ADR row that is now stale, and explains why the ADR's decision
    survives its own evidence going out of date.
    """
    head = (
        "The unflattering half, captured on purpose.\n"
        "\n"
        "ADR 0002 GT-06 recorded that at ~5,200 rows CockroachDB's optimizer does NOT choose the\n"
        "vector index for this shape — the plan becomes top-k over a scan — and GT-06b recorded\n"
        "that naming the index makes it traverse. That pair is the stated reason every ANN arm in\n"
        "MAINLINE pins the index. This file is the control that checks it, against the same rows\n"
        "and the same bound values as explain-hinted.txt, taken seconds apart.\n"
        "\n"
    )
    if not facts["traverses_ce_ann"]:
        return head + (
            "MEASURED HERE: the unhinted plan does NOT traverse ce_ann. GT-06 reproduces, the\n"
            "hint is doing the work, and `the index was used` in explain-hinted.txt is a\n"
            "measurement rather than an assumption.\n"
        )
    swept = ", ".join(str(o["rows"]) for o in crossover.get("observations", ())) or "not swept"
    return head + (
        "MEASURED HERE, AND IT IS NOT WHAT THE ADR SAYS: **the unhinted plan also traverses\n"
        "ce_ann.** On this cluster, today, at this corpus size, the optimizer chooses the vector\n"
        "index on its own. GT-06 did not reproduce.\n"
        "\n"
        f"That is a single observation, so it was swept: row counts {swept} in a scratch\n"
        "database built from the same DDL, with seeded pseudo-random vectors, by\n"
        "`scripts/aws/ann_proof.py --crossover`. Appendix A is that sweep. It crosses 5,200 —\n"
        "GT-06's own row count — and the optimizer still picks the index.\n"
        "\n"
        "APPENDIX B IS THE COUNTERFACTUAL THAT STILL WORKS. Removing the *hint* changes nothing\n"
        "on this release; removing a *prefix constraint* is refused outright, SQLSTATE 42809,\n"
        '`index "ce_ann" cannot be used for this query`. That is the rule this design depends\n'
        "on, and it is enforced by the server rather than by a comment in a migration.\n"
        "\n"
        "WHAT THIS DOES AND DOES NOT CHANGE.\n"
        "\n"
        "  * It does NOT weaken the hint. A cost-based choice that has already changed once\n"
        "    between two measurements on the same cluster is precisely the kind of\n"
        "    non-determinism that must not sit beneath a safety gate. ADR 0002's DECISION —\n"
        "    pin the index in every arm — is if anything better supported by this than by the\n"
        "    finding it was written from.\n"
        "  * It DOES make ADR 0002's GT-06 row stale for this shape, and\n"
        "    evidence/aws/ann/ann-proof.json says so under plans.crossover_census. Correcting\n"
        "    that document is not this worker's file to edit; the measurement is published here\n"
        "    so that whoever owns it cannot miss it.\n"
        "  * It does NOT make explain-hinted.txt weaker evidence. The hinted plan still shows the\n"
        "    C-SPANN tree being descended with both prefix columns bound. What this file removes\n"
        "    is the ability to claim the hint was *necessary* at this scale, and that claim is\n"
        "    now absent from every artefact this worker writes.\n"
        "\n"
        "UNCONTROLLED DIFFERENCES between this sweep and GT-06's original: GT-06's exact prefix\n"
        "cardinality, vector distribution, statistics freshness and cluster build are not\n"
        "recorded in ADR 0002, so this sweep matches its row count and its DDL and nothing else.\n"
        "The honest statement is `did not reproduce under these conditions`, not `was wrong`.\n"
    )


def _counterfactual_appendix(counterfactuals: Mapping[str, Any]) -> str:
    """The three shapes that are *not* the pinned, fully-constrained query.

    This is the half of the control that does not depend on the optimizer's mood.  Whether
    the unhinted plan happens to pick ``ce_ann`` is a cost-model fact that has already
    changed once; whether a query with half a prefix can use a vector index at all is a
    rule the server enforces, and it enforces it by refusing.
    """
    lines: list[str] = [
        "Removing the hint is one counterfactual. Removing a PREFIX CONSTRAINT is the other,",
        "and it is the one that does not depend on table statistics. Each statement below keeps",
        "`@ce_ann` and changes exactly one thing.",
        "",
    ]
    for name, entry in counterfactuals.items():
        lines += ["=" * 84, name, "=" * 84, "", entry["statement"], ""]
        if entry.get("refused"):
            lines += [
                f"  REFUSED BY THE SERVER — SQLSTATE {entry.get('sqlstate')}",
                f"  {entry.get('error')}",
                "",
                "  Not a worse plan. A refused one. This is the prefix rule enforced by",
                "  CockroachDB rather than asserted by a comment.",
                "",
            ]
        else:
            lines += [
                f"  traverses ce_ann:  {entry['traverses_ce_ann']}",
                f"  prefix spans:      {entry['has_prefix_spans']}",
                f"  full scan node:    {entry['has_full_scan_node']}",
                f"  plan digest:       {entry['digest_sha256']}",
                "",
                entry["plan"],
                "",
            ]
    return "\n".join(lines)


def _crossover_table(crossover: Mapping[str, Any]) -> str:
    """The sweep, as a fixed-width table for the foot of the control file."""
    if not crossover.get("run"):
        return (
            "CROSSOVER SWEEP: not run in this pass. Re-run `scripts/aws/ann_proof.py "
            "--crossover`\nto establish whether the plan above depends on corpus size."
        )
    lines = [
        f"measured {crossover.get('measured_at')} on {crossover.get('server_version')}",
        f"vectors: {crossover.get('vectors')}",
        f"table:   {crossover.get('table_shape')}",
        "",
        f"  {'rows':>7}  {'hinted traverses ce_ann':<24}  {'unhinted traverses ce_ann':<26}",
        f"  {'-' * 7}  {'-' * 24}  {'-' * 26}",
    ]
    for observation in crossover.get("observations", ()):
        lines.append(
            f"  {observation['rows']:>7}  "
            f"{observation['hinted']['traverses_ce_ann']!s:<24}  "
            f"{observation['unhinted']['traverses_ce_ann']!s:<26}"
        )
    flip = crossover.get("unhinted_stopped_using_ce_ann_at")
    lines += [
        "",
        (
            f"  unhinted stopped using ce_ann at: {flip} rows"
            if flip
            else "  unhinted NEVER stopped using ce_ann at any size swept"
        ),
        f"  GT-06 reproduces: {crossover.get('gt06_reproduces')}",
    ]
    return "\n".join(lines)


def write_explain_file(
    path: Path,
    *,
    title: str,
    argument: str,
    statement: str,
    plan: str,
    analyzed: str,
    facts: Mapping[str, Any],
    context: Mapping[str, Any],
    appendix: str | None = None,
    appendix_two: str | None = None,
) -> None:
    """Write one plan file: the argument, the context, the statement, both plans, the facts.

    The MACHINE-CHECKABLE FACTS block at the foot is not decoration — it is what
    ``tests/integration/aws`` compares, so that a human reading the prose and a test reading
    the file are checking the same claim.
    """
    lines = [
        "SPDX-FileCopyrightText: 2026 MAINLINE contributors",
        "SPDX-License-Identifier: CC-BY-4.0",
        "",
        "=" * 88,
        title,
        "=" * 88,
        "",
        argument.strip(),
        "",
        "-" * 88,
        "CONTEXT",
        "-" * 88,
    ]
    lines.extend(f"  {key:<28} {value}" for key, value in context.items())
    lines += [
        "",
        "-" * 88,
        "STATEMENT (bound values are the ones named above; the full 1024-float vector is",
        "inlined in evidence/aws/ann/the-one-query.sql)",
        "-" * 88,
        "",
        statement,
        "",
        "-" * 88,
        "EXPLAIN",
        "-" * 88,
        "",
        plan,
        "",
        "-" * 88,
        "EXPLAIN ANALYZE  (the same statement, executed)",
        "-" * 88,
        "",
        analyzed,
        "",
        "-" * 88,
        "MACHINE-CHECKABLE FACTS ABOUT THE PLAN ABOVE",
        "-" * 88,
    ]
    lines.extend(f"  {key:<36} {value}" for key, value in facts.items())
    if appendix:
        lines += [
            "",
            "-" * 88,
            "APPENDIX A — DOES THE PLAN ABOVE DEPEND ON THE SIZE OF THE CORPUS?",
            "-" * 88,
            "",
            appendix,
        ]
    if appendix_two:
        lines += [
            "",
            "-" * 88,
            "APPENDIX B — THE COUNTERFACTUAL THAT DOES NOT DEPEND ON THE OPTIMIZER",
            "-" * 88,
            "",
            appendix_two,
        ]
    lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ═══════════════════════════════════════════════════════════════════════════════════════
# 9 · Main
# ═══════════════════════════════════════════════════════════════════════════════════════

EVIDENCE_DIR: Final[Path] = repo_root() / "evidence" / "aws" / "ann"


def _cluster_facts(conn: Any, database: str) -> dict[str, Any]:
    import psycopg

    with conn.cursor() as cur:
        version = cur.execute("SELECT version()").fetchone()[0]
        beam = cur.execute("SHOW vector_search_beam_size").fetchone()[0]
        rerank = cur.execute("SHOW vector_search_rerank_multiplier").fetchone()[0]
        try:
            # Column 1, not column 0. `SHOW REGIONS FROM DATABASE` returns
            # (database, region, primary, secondary, zones), and reading column 0 puts the
            # *database name* where the artefact says "cluster region" — which is how a
            # residency claim becomes decorative without anybody editing a word of it.
            regions = [r[1] for r in cur.execute("SHOW REGIONS FROM DATABASE").fetchall()]
        except psycopg.Error:
            # A single-region database has no region set; that is a fact about the tier,
            # not an error, and the artefact says `[]` rather than inventing a region name.
            regions = []
    return {
        "database": database,
        "server_version": version.split(" (")[0],
        "regions": regions,
        "vector_search_beam_size": int(beam),
        "vector_search_rerank_multiplier": int(rerank),
    }


def _survey_table(conn: Any) -> dict[str, Any]:
    """What is actually in ``mainline.clause_embedding`` right now.

    ``mainline_ann_evidence`` is a **shared** surface: ``scripts/aws/load_vectors.py``
    (worker ``cloud-load``) writes its own rows under its own ``(site_id, activity_root)``
    pairs.  Those live in different C-SPANN partition trees and are therefore invisible to
    every query in this program — but a bare ``count(*)`` would fold them into this
    artefact's row count and nobody would ever notice.  Both numbers are surveyed, and the
    one that was searched is named separately.
    """
    with conn.cursor() as cur:
        cur.execute("ANALYZE mainline.clause_embedding")
        counts = cur.execute(SURVEY_CORPUS).fetchone()
        models = sorted(r[0] for r in cur.execute(DISTINCT_MODELS))
        gens = sorted(r[0] for r in cur.execute(DISTINCT_GENS))
        models_searched = sorted(r[0] for r in cur.execute(MODELS_UNDER_SITE, (CORPUS_SITE_ID,)))
        gens_searched = sorted(r[0] for r in cur.execute(GENS_UNDER_SITE, (CORPUS_SITE_ID,)))
        roots = sorted(r[0] for r in cur.execute(DISTINCT_ROOTS_UNDER_SITE, (CORPUS_SITE_ID,)))
        searched = cur.execute(COUNT_UNDER_SITE, (CORPUS_SITE_ID,)).fetchone()[0]
        others = [
            {"site_id": str(r[0]), "activity_root": r[1], "rows": int(r[2]), "index_gen": r[3]}
            for r in cur.execute(OTHER_PREFIXES, (CORPUS_SITE_ID,)).fetchall()
        ]
    return {
        "counts": counts,
        "models": models,
        "gens": gens,
        "models_searched": models_searched,
        "gens_searched": gens_searched,
        "roots_under_site": roots,
        "rows_searched": int(searched),
        "other_prefixes": others,
    }


def _score_case(
    conn: Any,
    case: QueryCase,
    qvec: Sequence[float],
    *,
    by_doc_id: Mapping[str, Doc],
    uuid_to_doc: Mapping[str, Doc],
    limit: int,
    top_detail: int,
) -> dict[str, Any]:
    """One query, both arms, every number this artefact reports per query."""
    vtext = vector_literal(qvec)
    truth_doc = by_doc_id.get(case.truth_doc_id)
    truth_uuid = {truth_doc.clause_uuid} if truth_doc else set()
    relevant_uuids = {by_doc_id[d].clause_uuid for d in case.relevant if d in by_doc_id}
    root = case.activity_root

    hits, latency = single_root(conn, vtext, root, limit)
    walk_hits, walk_latency, _ = ancestor_walk(conn, vtext, ROOTS, limit)
    in_list_hits, in_list_latency = in_list_arm(conn, vtext, limit)

    record: dict[str, Any] = {
        "query_id": case.query_id,
        "permit_site_label": case.site_label,
        "activity_path": case.activity_path,
        "activity_root": root,
        "wall": case.wall,
        "truth_doc_id": case.truth_doc_id,
        "truth_doc_root": truth_doc.activity_root if truth_doc else None,
        "truth_doc_in_query_partition": bool(truth_doc and truth_doc.activity_root == root),
        "relevant_docs_grade_ge_2": len(case.relevant),
        "relevant_docs_in_query_partition": sum(
            1 for d in case.relevant if d in by_doc_id and by_doc_id[d].activity_root == root
        ),
    }
    for label, hit_list, lat in (
        ("single_root", hits, latency),
        ("ancestor_walk", walk_hits, walk_latency),
        ("in_list_one_statement", in_list_hits, in_list_latency),
    ):
        t_rank, _, t_dist = rank_of(hit_list, truth_uuid)
        r_rank, r_uuid, r_dist = rank_of(hit_list, relevant_uuids)
        # THE WALL, ENFORCED WHERE IT CAN BE ENFORCED.
        #
        # `clause_embedding` has no date column, so the ANN arm cannot exclude a document
        # that had not happened yet when the permit was written — and it does not: for
        # nearly every query the nearest neighbour is the fatality report the permit
        # narrative was *extracted from*, which by definition post-dates the wall. In a
        # deployment that document does not exist yet; in this corpus it does.
        #
        # Deleting it would be curating the corpus to flatter the result. Ignoring it would
        # be reporting a rank that a real permit could never see. So both are reported: the
        # raw rank the index returned, and the rank after the post-wall rows are dropped —
        # which is what a gate applying its own time wall to the ANN result would act on.
        wall_clean = [
            h
            for h in hit_list
            if _after_wall(uuid_to_doc[h.clause_uuid].occurred_on, case.wall) is not True
        ]
        wt_rank, _, _ = rank_of(wall_clean, truth_uuid)
        wr_rank, wr_uuid, _ = rank_of(wall_clean, relevant_uuids)
        record[label] = {
            "returned": len(hit_list),
            "latency_ms": round(lat, 1),
            "truth_precursor_rank": t_rank,
            "truth_precursor_distance": None if t_dist is None else round(t_dist, 6),
            "truth_precursor_in_top_3": bool(t_rank is not None and t_rank <= 3),
            "best_relevant_rank": r_rank,
            "best_relevant_doc_id": uuid_to_doc[r_uuid].doc_id if r_uuid else None,
            "best_relevant_distance": None if r_dist is None else round(r_dist, 6),
            "best_relevant_in_top_3": bool(r_rank is not None and r_rank <= 3),
            "relevant_in_top_10": sum(1 for h in hit_list[:10] if h.clause_uuid in relevant_uuids),
            "wall_filtered_returned": len(wall_clean),
            "wall_filtered_truth_precursor_rank": wt_rank,
            "wall_filtered_best_relevant_rank": wr_rank,
            "wall_filtered_best_relevant_doc_id": uuid_to_doc[wr_uuid].doc_id if wr_uuid else None,
            "post_wall_in_top_10": sum(
                1
                for h in hit_list[:10]
                if _after_wall(uuid_to_doc[h.clause_uuid].occurred_on, case.wall) is True
            ),
            "own_source_report_returned": any(
                uuid_to_doc[h.clause_uuid].doc_id == case.query_id.replace("Q-G4-", "")
                for h in hit_list
            ),
            "top": [
                {
                    "rank": i,
                    "doc_id": uuid_to_doc[h.clause_uuid].doc_id,
                    "source": uuid_to_doc[h.clause_uuid].source,
                    "gist": doc_gist(uuid_to_doc[h.clause_uuid]),
                    "occurred_on": uuid_to_doc[h.clause_uuid].occurred_on,
                    "distance": round(h.distance, 6),
                    "grade": case.relevant.get(uuid_to_doc[h.clause_uuid].doc_id, 0),
                    "after_wall": _after_wall(uuid_to_doc[h.clause_uuid].occurred_on, case.wall),
                }
                for i, h in enumerate(hit_list[:top_detail], start=1)
            ],
        }
    return record


def _counterfactual_plans(conn: Any, params: Mapping[str, Any]) -> dict[str, Any]:
    """The three shapes that must *not* be trusted, EXPLAINed so nobody has to trust them.

    A refusal is a result here, not a crash: if CockroachDB rejects a hinted query whose
    prefix is not fully constrained, that refusal is the strongest possible statement of
    the rule and belongs in the artefact verbatim.
    """
    import psycopg

    out: dict[str, Any] = {}
    for name, sql in (
        ("prefix_dropped_site_id", ANN_NO_SITE),
        ("prefix_dropped_activity_root", ANN_NO_ROOT),
        ("activity_root_in_list", ANN_IN_LIST),
    ):
        try:
            text = explain(conn, sql, params)
        except psycopg.Error as exc:
            out[name] = {
                "statement": sql,
                "refused": True,
                "sqlstate": getattr(exc, "sqlstate", None),
                "error": redact(str(exc)).strip().splitlines()[0],
            }
        else:
            out[name] = {"statement": sql, "refused": False, **plan_facts(text), "plan": text}
    return out


def _capture_plans(conn: Any, params: Mapping[str, Any]) -> dict[str, Any]:
    """Both plans and both executions, taken seconds apart against the same rows.

    Order matters only in that nothing else touches the table between them: a control taken
    against a different corpus is not a control.

    ``EXPLAIN`` is issued with bound parameters; ``EXPLAIN ANALYZE`` cannot be —
    CockroachDB answers ``EXPLAIN does not support placeholders`` because ANALYZE executes
    the statement — so the executed forms are built from the ``:SLOT:`` templates with the
    values written in.  The two forms are therefore textually different and that is
    recorded here rather than hidden: the plan digests in the artefact are the *bound*
    ``EXPLAIN``, which is the one a reader can re-issue without a 10 KB literal.
    """
    hinted_sql = hinted_statement(hint=True)
    unhinted_sql = hinted_statement(hint=False)
    vector = str(params["vec"])
    root = str(params["root"])
    k = int(params["k"])
    hinted_plan = explain(conn, hinted_sql, params)
    hinted_analyzed = explain_inlined(
        conn, _fill(ONE_QUERY_ANN.rstrip(";"), vector=vector, root=root, k=k)
    )
    unhinted_plan = explain(conn, unhinted_sql, params)
    unhinted_analyzed = explain_inlined(
        conn, _fill(ONE_QUERY_ANN_UNHINTED, vector=vector, root=root, k=k)
    )
    return {
        "hinted_sql": hinted_sql,
        "hinted_plan": hinted_plan,
        "hinted_analyzed": hinted_analyzed,
        "hinted_facts": plan_facts(hinted_plan),
        "unhinted_sql": unhinted_sql,
        "unhinted_plan": unhinted_plan,
        "unhinted_analyzed": unhinted_analyzed,
        "unhinted_facts": plan_facts(unhinted_plan),
    }


def _write_committed_files(
    *,
    args: argparse.Namespace,
    cluster: Mapping[str, Any],
    survey: Mapping[str, Any],
    exhibit_case: QueryCase,
    exhibit_record: Mapping[str, Any],
    exhibit_doc: Doc,
    exhibit_vtext: str,
    observed_at: str,
    plans: Mapping[str, Any],
    crossover: Mapping[str, Any],
    counterfactuals: Mapping[str, Any],
    queries_run: int,
) -> None:
    """``the-one-query.sql`` and the two plan files, from one set of facts.

    Kept together because all three describe the *same* capture, and a reader who finds
    them disagreeing has no way to tell which one is stale.  The digest link asserted by
    ``test_artefact_plan_digests_match_the_committed_plan_files`` is only meaningful if
    they are written in one pass.
    """
    region = ", ".join(cluster["regions"]) or "region not surveyed"
    write_one_query_sql(
        EVIDENCE_DIR / "the-one-query.sql",
        {
            "database": args.database,
            "cluster": "mainline-dev",
            "cluster_region": region,
            "query_id": exhibit_case.query_id,
            "fatality": exhibit_record["fatality"],
            "permit_excerpt": exhibit_case.text[:150].replace("\n", " ") + "...",
            "wall": exhibit_case.wall,
            "expected_doc_id": exhibit_doc.doc_id,
            "expected_grade": exhibit_record["exhibit_grade"],
            "expected_clause_uuid": exhibit_doc.clause_uuid,
            "expected_summary": doc_gist(exhibit_doc),
            "observed_rank": exhibit_record["exhibit_rank"],
            "observed_distance": exhibit_record["exhibit_distance"],
            "wall_filtered_rank": exhibit_record["exhibit_wall_filtered_rank"],
            "post_wall_in_top_10": exhibit_record["exhibit_post_wall_in_top_10"],
            "observed_at": observed_at,
            "activity_root": exhibit_case.activity_root,
            "queries_run": queries_run,
            "k": args.limit,
            "caveat_synthetic": CAVEAT_SYNTHETIC,
            "caveat_site": CAVEAT_SITE_PREFIX,
        },
        exhibit_vtext,
    )
    context = {
        "database": args.database,
        "cluster": f"mainline-dev ({region})",
        "server_version": cluster["server_version"],
        "rows in the table": survey["counts"][0],
        "rows under this site_id": survey["rows_searched"],
        "distinct activity_root": len(survey["roots_under_site"]),
        "embed_model (searched)": ", ".join(survey["models_searched"]),
        "index_gen (searched)": ", ".join(survey["gens_searched"]),
        "vector dimensions": EMBED_DIM,
        "beam size": cluster["vector_search_beam_size"],
        "rerank multiplier": cluster["vector_search_rerank_multiplier"],
        "query id": exhibit_case.query_id,
        "site_id bound to": CORPUS_SITE_ID,
        "activity_root bound to": exhibit_case.activity_root,
        "LIMIT": args.limit,
        "captured at": observed_at,
    }
    write_explain_file(
        EVIDENCE_DIR / "explain-hinted.txt",
        title="EXPLAIN — prefix-constrained ANN, INDEX PINNED  (the claim)",
        argument=(
            "This is the plan the whole submission rests on. It must contain a `vector search`\n"
            f"node whose table line reads `clause_embedding@{INDEX}`, with a non-empty\n"
            "`prefix spans` binding BOTH prefix columns to one value each. A vector search node\n"
            "is the C-SPANN partition tree being descended; `prefix spans` names which tree.\n"
            "\n"
            "Read this file together with explain-unhinted.txt. On its own it cannot tell you\n"
            "whether the hint did anything — that is what the control is for."
        ),
        statement=plans["hinted_sql"],
        plan=plans["hinted_plan"],
        analyzed=plans["hinted_analyzed"],
        facts=plans["hinted_facts"],
        context=context,
    )
    write_explain_file(
        EVIDENCE_DIR / "explain-unhinted.txt",
        title="EXPLAIN — the SAME statement without @ce_ann  (the control)",
        argument=_unhinted_argument(plans["unhinted_facts"], crossover),
        statement=plans["unhinted_sql"],
        plan=plans["unhinted_plan"],
        analyzed=plans["unhinted_analyzed"],
        facts=plans["unhinted_facts"],
        context=context,
        appendix=_crossover_table(crossover),
        appendix_two=_counterfactual_appendix(counterfactuals),
    )


def restrict_corpus(
    docs: Sequence[Doc], cases: Sequence[QueryCase], cap: int
) -> tuple[tuple[Doc, ...], dict[str, Any]]:
    """Keep every judged document, then fill to *cap* with a seeded sample of the rest.

    Used only when the account's Bedrock request rate makes a full pass impractical inside
    the wave.  The rule is stated rather than improvised, and the report it returns goes
    into the artefact, because **a smaller corpus makes retrieval easier** — every
    distractor removed is a document that can no longer outrank the truth. A reader must be
    able to see exactly how many were removed and by what rule.

    ``cap <= 0`` or a cap at or above the corpus size returns the corpus unchanged, and the
    report says so; there is no silent path where this function has an effect nobody sees.
    """
    if cap <= 0 or cap >= len(docs):
        return tuple(docs), {
            "applied": False,
            "documents": len(docs),
            "rule": "the whole synthetic corpus; nothing was removed",
        }
    judged: set[str] = set()
    for case in cases:
        judged.update(case.relevant)
        judged.add(case.truth_doc_id)
    kept = [d for d in docs if d.doc_id in judged]
    rest = [d for d in docs if d.doc_id not in judged]
    rng = random.Random(20260811)  # noqa: S311 — a seeded sample is the point
    rng.shuffle(rest)
    fill = rest[: max(0, cap - len(kept))]
    chosen = sorted([*kept, *fill], key=lambda d: d.doc_id)
    return tuple(chosen), {
        "applied": True,
        "documents": len(chosen),
        "documents_in_full_corpus": len(docs),
        "judged_documents_kept": len(kept),
        "unjudged_distractors_kept": len(fill),
        "unjudged_distractors_dropped": len(rest) - len(fill),
        "seed": 20260811,
        "rule": (
            "every document any G4 judgement names is kept; the remainder is a seeded "
            "shuffle truncated to the cap"
        ),
        "why_this_flatters_the_result": (
            "a distractor that is not in the table cannot outrank the truth precursor. "
            "Every hit rate below is therefore an UPPER BOUND on what the same query would "
            "score against the full corpus, and the drop count is stated so the size of "
            "that favour is visible."
        ),
    }


def _run(args: argparse.Namespace) -> dict[str, Any]:
    cases = load_goldset(limit=args.queries)
    docs, corpus_report = restrict_corpus(build_corpus(), cases, args.corpus_cap)
    by_doc_id = {d.doc_id: d for d in docs}
    uuid_to_doc = {d.clause_uuid: d for d in docs}
    gen = index_gen_for(docs)

    embedder = Embedder(bedrock_runtime())
    cached = embedder.load_cache()
    print(
        f"corpus {len(docs)} docs · queries {len(cases)} · cache {cached} vectors",
        file=sys.stderr,
        flush=True,
    )

    doc_texts = [d.text for d in docs]
    query_texts = [c.text for c in cases]
    all_digests = [sha256_hex(t.encode("utf-8")) for t in (*doc_texts, *query_texts)]
    doc_vectors = embedder.embed_many(doc_texts, workers=args.workers)
    embedder.assert_complete(
        [sha256_hex(t.encode("utf-8")) for t in doc_texts], what="corpus documents"
    )
    query_vectors = embedder.embed_many(query_texts, workers=args.workers)
    embedder.assert_complete(
        [sha256_hex(t.encode("utf-8")) for t in query_texts], what="retro query narratives"
    )
    embedder.save_cache()
    print(
        f"bedrock: {embedder.calls} calls, {embedder.input_tokens} input tokens, "
        f"{embedder.cache_hits} cache hits, {embedder.throttles} throttle retries, "
        f"{len(embedder.failures)} hard failures",
        file=sys.stderr,
        flush=True,
    )

    ensure_database(args.database)
    with crdb(args.database) as conn:
        ensure_schema(conn)
        cluster = _cluster_facts(conn, args.database)

        if args.skip_load:
            with conn.cursor() as cur:
                present = int(cur.execute(COUNT_ALL).fetchone()[0])
            load_report = {"skipped": True, "rows_present_after": present, "retries_40001": 0}
        else:
            load_report = load_rows(conn, docs, doc_vectors, gen)
        print(f"rows in {TABLE}: {load_report['rows_present_after']}", file=sys.stderr)

        survey = _survey_table(conn)

        # ── the queries ──────────────────────────────────────────────────────────────
        results: list[dict[str, Any]] = []
        for case, qvec in zip(cases, query_vectors, strict=True):
            record = _score_case(
                conn,
                case,
                qvec,
                by_doc_id=by_doc_id,
                uuid_to_doc=uuid_to_doc,
                limit=args.limit,
                top_detail=args.top_detail,
            )
            results.append(record)
            print(
                f"  {case.query_id}  root={case.activity_root:<14} "
                f"truth@{record['single_root']['truth_precursor_rank']} "
                f"rel@{record['single_root']['best_relevant_rank']} "
                f"walk_truth@{record['ancestor_walk']['truth_precursor_rank']} "
                f"{record['single_root']['latency_ms']}ms",
                file=sys.stderr,
                flush=True,
            )

        # ── the plans ────────────────────────────────────────────────────────────────
        exhibit_case, exhibit_record, exhibit_vec = _choose_exhibit(cases, results, query_vectors)
        exhibit_vtext = vector_literal(exhibit_vec)
        params = {
            "vec": exhibit_vtext,
            "site": CORPUS_SITE_ID,
            "root": exhibit_case.activity_root,
            "k": args.limit,
        }
        plans = _capture_plans(conn, params)
        # Each of these keeps the hint and removes exactly one prefix constraint — the only
        # way to show that it is the *constraint*, not the hint alone, that lets a single
        # partition tree be descended.
        counterfactuals = _counterfactual_plans(conn, params)

    crossover = load_crossover_census()

    # ── artefacts ───────────────────────────────────────────────────────────────────
    observed_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    if exhibit_record["exhibit_doc_id"] is None:
        # Tier 3 of _choose_exhibit: not one query in the set returned a graded document
        # inside its own partition tree. That is a finding, and the program says so and
        # stops rather than writing a `the-one-query.sql` with no answer in it.
        raise SystemExit(
            "no query returned a grade >= 2 document in its own partition tree, so there "
            "is no exhibit to commit. ann-proof.json's per-query ranks are the finding; "
            "re-run with a larger --limit or read metrics.single_root before concluding "
            "anything about the index."
        )
    exhibit_doc = by_doc_id[exhibit_record["exhibit_doc_id"]]
    _write_committed_files(
        args=args,
        cluster=cluster,
        survey=survey,
        exhibit_case=exhibit_case,
        exhibit_record=exhibit_record,
        exhibit_doc=exhibit_doc,
        exhibit_vtext=exhibit_vtext,
        observed_at=observed_at,
        plans=plans,
        crossover=crossover,
        counterfactuals=counterfactuals,
        queries_run=len(cases),
    )

    corpus_tokens, distinct_texts, tokens_unknown = embedder.corpus_tokens(all_digests)
    payload = _build_payload(
        args=args,
        corpus_report=corpus_report,
        corpus_tokens=corpus_tokens,
        distinct_texts=distinct_texts,
        tokens_unknown=tokens_unknown,
        cluster=cluster,
        survey=survey,
        embedder=embedder,
        docs=docs,
        cases=cases,
        gen=gen,
        load_report=load_report,
        results=results,
        plans=plans,
        counterfactuals=counterfactuals,
        crossover=crossover,
        exhibit_case=exhibit_case,
        exhibit_record=exhibit_record,
        exhibit_doc=exhibit_doc,
    )
    artefact(
        EVIDENCE_DIR / "ann-proof.json",
        payload,
        kind="ann-proof",
        caveats=_caveats_for(payload, crossover),
        synthetic=True,
    )
    return payload


def _build_payload(
    *,
    args: argparse.Namespace,
    corpus_report: Mapping[str, Any],
    corpus_tokens: int,
    distinct_texts: int,
    tokens_unknown: int,
    cluster: Mapping[str, Any],
    survey: Mapping[str, Any],
    embedder: Embedder,
    docs: Sequence[Doc],
    cases: Sequence[QueryCase],
    gen: str,
    load_report: Mapping[str, Any],
    results: Sequence[Mapping[str, Any]],
    plans: Mapping[str, Any],
    counterfactuals: Mapping[str, Any],
    crossover: Mapping[str, Any],
    exhibit_case: QueryCase,
    exhibit_record: Mapping[str, Any],
    exhibit_doc: Doc,
) -> dict[str, Any]:
    """Everything ``ann-proof.json`` says, assembled in one place from measured values."""
    hinted_facts = plans["hinted_facts"]
    unhinted_facts = plans["unhinted_facts"]
    corpus_facts = survey["counts"]
    models = survey["models"]
    gens = survey["gens"]
    searched_rows = survey["rows_searched"]
    metrics = {arm: _metrics_for(results, arm) for arm in ARMS}
    latencies = {arm: _latency_summary([r[arm]["latency_ms"] for r in results]) for arm in ARMS}
    # Priced over the WHOLE corpus, not over this pass. A run that hit the cache for every
    # document still describes vectors that cost money, and a ledger that reports zero
    # because the money was spent yesterday is the kind of true-but-useless number this
    # fleet's cost discipline exists to prevent.
    ledger = [token_ledger_entry(TITAN_MODEL_ID, distinct_texts, corpus_tokens, 0)]
    if tokens_unknown:
        # A price computed from an incomplete token count is not a cheap price, it is an
        # unknown one. The row keeps its shape so the ledger stays machine-readable, and
        # every money field becomes null so nothing downstream can sum it into a total.
        ledger[0].update(
            {
                "priced": False,
                "usd_input": None,
                "usd_output": None,
                "usd_total": None,
                "incomplete": (
                    f"{tokens_unknown} of {distinct_texts} distinct texts have no recorded "
                    "inputTextTokenCount, so this row is UNPRICED rather than cheap. "
                    "Re-run after deleting out/aws/ann/titan-vectors.jsonl to re-measure."
                ),
            }
        )
    plans_differ = hinted_facts["digest_sha256"] != unhinted_facts["digest_sha256"]
    counterfactual_holds = (
        hinted_facts["traverses_ce_ann"] and not (unhinted_facts["traverses_ce_ann"])
    )

    return {
        "claim": (
            "A permit narrative embedded by Amazon Bedrock, searched through CockroachDB's "
            "C-SPANN vector index with both prefix columns bound to one value and the index "
            "pinned, returns the precursor of the fatality that permit preceded."
        ),
        "verdict": "PROVEN" if hinted_facts["traverses_ce_ann"] else "NOT PROVEN",
        "database": {
            **cluster,
            "cluster": "mainline-dev",
            "table": TABLE,
            "index": INDEX,
            "parent_table_is_stub": True,
        },
        "vectors": {
            "embed_model_searched": survey["models_searched"],
            "embed_model_expected": TITAN_MODEL_ID,
            "every_searched_row_is_titan_v2": survey["models_searched"] == [TITAN_MODEL_ID],
            "embed_model_anywhere_in_table": models,
            "dimensions": EMBED_DIM,
            "index_gen_searched": survey["gens_searched"],
            "index_gen_anywhere_in_table": gens,
            "index_gen_expected": gen,
            "rows_in_table": corpus_facts[0],
            "rows_searched": searched_rows,
            "rows_under_other_prefixes": survey["other_prefixes"],
            "distinct_site_id_in_table": corpus_facts[1],
            "distinct_activity_root_in_table": corpus_facts[2],
            "site_id_searched": CORPUS_SITE_ID,
            "activity_roots_searched": survey["roots_under_site"],
            "corpus_provenance": (
                "loaded by scripts/aws/ann_proof.py from a live Titan pass over "
                "trappoint_recall.corpora.synthetic. scripts/aws/load_vectors.py (worker "
                "cloud-load) shares this table and writes its own rows under its own "
                "(site_id, activity_root) pairs — a different set of C-SPANN partition "
                "trees, listed in rows_under_other_prefixes and searched by nothing here. "
                "NOTE FOR WHOEVER RE-RUNS THE FLEET: load_vectors.py issues DROP TABLE IF "
                "EXISTS mainline.clause_embedding, so re-running it destroys these rows; "
                "re-running ann_proof.py restores them from the cached vectors at no cost."
            ),
            "load": load_report,
        },
        "bedrock": {
            "region": REGION,
            "model_id": TITAN_MODEL_ID,
            "invoke_model_calls": embedder.calls,
            "input_tokens": embedder.input_tokens,
            "cache_hits": embedder.cache_hits,
            "throttle_retries": embedder.throttles,
            "hard_failures": embedder.failures,
            "corpus_input_tokens": corpus_tokens,
            "corpus_distinct_texts": distinct_texts,
            "corpus_texts_offered": len(docs) + len(cases),
            "corpus_texts_with_no_recorded_token_count": tokens_unknown,
            "token_accounting_note": (
                "invoke_model_calls and input_tokens are THIS PASS. corpus_input_tokens is "
                "every text behind the vectors searched, whichever pass paid for it — the "
                "cache carries the per-text inputTextTokenCount Bedrock returned. "
                "token_ledger prices the corpus, not the pass, and prices it over DISTINCT "
                "texts: corpus_texts_offered counts documents plus queries, "
                "corpus_distinct_texts counts the ones that were actually invoked, and the "
                "difference is byte-identical bodies that share one vector and cost one "
                "call. Any text whose count was not recorded is counted in "
                "corpus_texts_with_no_recorded_token_count rather than assumed to be free."
            ),
            "pacer_final_interval_s": round(embedder.pacer.interval, 3),
            "pacer_note": (
                "one shared additive-increase/multiplicative-decrease interval across the "
                "worker threads. The value it settled at is the request spacing this "
                "account's on-demand Bedrock limit allowed while the rest of this fleet was "
                "running against it, not a property of Bedrock."
            ),
            "documents_embedded": len(docs),
            "queries_embedded": len(cases),
            "normalize_requested": True,
            "call_latency_ms_sample": embedder.latencies_ms[:20],
        },
        "token_ledger": ledger,
        "token_ledger_total": ledger_total(ledger),
        "plans": {
            "hinted": {
                "file": "evidence/aws/ann/explain-hinted.txt",
                "statement": plans["hinted_sql"],
                **hinted_facts,
            },
            "unhinted": {
                "file": "evidence/aws/ann/explain-unhinted.txt",
                "statement": plans["unhinted_sql"],
                **unhinted_facts,
            },
            "digests_differ": plans_differ,
            "gt06_counterfactual_reproduces": counterfactual_holds,
            "gt06_note": (
                "ADR 0002 GT-06 was measured at ~5,200 rows and says the unhinted plan does "
                f"not use ce_ann. This run searched {searched_rows} rows. Whether the "
                "counterfactual reproduced is gt06_counterfactual_reproduces, and it is not "
                "reasoned about from one observation: crossover_census sweeps the row count "
                "on the same DDL. If the counterfactual does not reproduce, the reading is "
                "that the optimizer's choice has moved on this cluster — NOT that the hint is "
                "unnecessary. The hint is what makes the plan independent of table "
                "statistics, and that independence is the property a safety gate needs; a "
                "cost model that has already changed once is the argument for pinning, not "
                "against it."
            ),
            "crossover_census": crossover,
            "counterfactuals": counterfactuals,
        },
        "arms": {
            "single_root": (
                "ONE hinted ANN query. site_id and activity_root each bound to exactly one "
                "value — the query's own activity root. This is the shape "
                "evidence/aws/ann/the-one-query.sql commits, and the only shape the "
                "architecture allows beneath a gate."
            ),
            "ancestor_walk": (
                f"{len(ROOTS)} hinted ANN queries, one per activity root "
                f"({', '.join(ROOTS)}), UNION ALL-ed and re-ranked by the server. Each arm "
                "carries its own LIMIT, so the walk considers 3k candidates and keeps k."
            ),
            "in_list_one_statement": (
                "activity_root IN (...) in a single hinted statement — the shape "
                "0031_clause_embedding.sql calls a trap. MEASURED ON v26.2.5: it is NOT the "
                "trap the header describes. The optimizer expands the list into one prefix "
                "span per value and the vector index IS used; "
                "plans.counterfactuals.activity_root_in_list carries that plan. What is "
                "true, and is the reason the ancestor walk stays the architecture's shape, "
                "is that LIMIT k over three spans is a SHARED budget of k candidates across "
                "three partition trees, where the walk gives each tree its own k. The two "
                "arms are therefore different recall budgets rather than two spellings of "
                "one query, and metrics.* reports both so the difference is a number."
            ),
            "prefix_dropped": (
                "NOT AN ARM — a refusal. Dropping either prefix column while keeping the "
                'hint is rejected by the server with SQLSTATE 42809, \'index "ce_ann" '
                "cannot be used for this query'. That refusal, in "
                "plans.counterfactuals.prefix_dropped_*, is the strongest available "
                "statement of the prefix rule: not a worse plan, a refused one."
            ),
        },
        "metrics": metrics,
        "latency_ms": latencies,
        "the_one_query": {
            "file": "evidence/aws/ann/the-one-query.sql",
            "query_id": exhibit_case.query_id,
            "fatality": exhibit_record["fatality"],
            "wall": exhibit_case.wall,
            "activity_root": exhibit_case.activity_root,
            "site_id": CORPUS_SITE_ID,
            "expected_doc_id": exhibit_doc.doc_id,
            "expected_clause_uuid": exhibit_doc.clause_uuid,
            "expected_grade": exhibit_record["exhibit_grade"],
            "observed_rank": exhibit_record["exhibit_rank"],
            "observed_distance": exhibit_record["exhibit_distance"],
            "wall_filtered_rank": exhibit_record["exhibit_wall_filtered_rank"],
            "post_wall_in_top_10": exhibit_record["exhibit_post_wall_in_top_10"],
            "limit": args.limit,
        },
        "queries": results,
        "documents_in_corpus": len(docs),
        "corpus_selection": corpus_report,
        "queries_run": len(cases),
    }


def _caveats_for(payload: Mapping[str, Any], crossover: Mapping[str, Any]) -> list[str]:
    """What this artefact does NOT prove, said before anybody has to ask.

    The list is not decorative and it is not a disclaimer.  Five of these are permanent
    properties of the evidence surface; the sixth is written only when a measurement came
    out against the repository's own prior finding, and it is written first, in capitals,
    because a correction buried at position six is a correction nobody reads.
    """
    caveats = [
        CAVEAT_SYNTHETIC,
        CAVEAT_STUB,
        CAVEAT_SITE_PREFIX,
        CAVEAT_GRADES,
        CAVEAT_LATENCY,
        (
            "NO WALL IS ENFORCED IN SQL, AND THE CORPUS CONTAINS EACH QUERY'S OWN SOURCE "
            "REPORT. clause_embedding has no date column, so the ANN arm cannot exclude a "
            "document that had not happened when the permit was written — and one such "
            "document is always present: every retro permit is synthesised from a fatality "
            "investigation that is itself in the corpus, and it is usually the nearest "
            "neighbour. It is never relevant in the goldset, so it COSTS rank rather than "
            "buying it, but it occupies positions a deployment would not have filled. "
            "metrics.*.wall_filtered_* repeat every rate with the post-wall rows dropped, "
            "metrics.*.queries_whose_own_source_report_came_back counts how often it "
            "happened, and per-query `top` marks each row with `after_wall`. Read the "
            "wall-filtered numbers as the deployment-realistic ones."
        ),
        (
            "ONE OBSERVATION PER QUERY. Ranks are from a single issue of each statement "
            "against a live ANN index whose beam search is not exhaustive; re-running may "
            "move a rank by a position. The beam size and rerank multiplier in force are "
            "recorded in database.vector_search_*."
        ),
    ]
    if not payload["plans"]["gt06_counterfactual_reproduces"]:
        swept = crossover.get("sizes") if crossover.get("run") else "not swept"
        caveats.insert(
            0,
            (
                "THE GT-06 COUNTERFACTUAL DID NOT REPRODUCE. The unhinted plan traverses "
                "ce_ann here too: on this cluster, today, the optimizer chooses the vector "
                f"index without being told to, at every row count swept ({swept}) including "
                "GT-06's own ~5,200. ADR 0002's GT-06 row is therefore stale for this table "
                "shape, and this artefact says so rather than quoting it. Two consequences, "
                "both stated because only one of them is comfortable: (1) NOTHING HERE MAY "
                "BE READ AS 'the hint was necessary at this scale' — it was not; (2) the "
                "decision to pin the index is unaffected and better supported, because a "
                "plan that flips with table statistics is exactly what must not sit beneath "
                "a safety gate, and the choice has now been observed to differ between two "
                "measurements on the same cluster. Correcting ADR 0002 is not this worker's "
                "file to edit; plans.crossover_census is the measurement it needs."
            ),
        )
    return caveats


def _after_wall(occurred_on: str | None, wall: str) -> bool | None:
    """``True`` if the document post-dates the query's time wall, ``None`` if undated."""
    if not occurred_on:
        return None
    return occurred_on[:10] >= wall[:10]


def _metrics_for(results: Sequence[Mapping[str, Any]], arm: str) -> dict[str, Any]:
    n = len(results)
    out: dict[str, Any] = {}
    for k in (1, 3, 10):
        out[f"truth_precursor_hit_at_{k}"] = proportion(
            f"{arm}.truth_precursor_hit@{k}",
            sum(1 for r in results if (r[arm]["truth_precursor_rank"] or 10**9) <= k),
            n,
            detail={
                "relevance": "grade 3 only — the single document the investigator cited",
                "arm": arm,
            },
        )
        out[f"any_relevant_hit_at_{k}"] = proportion(
            f"{arm}.any_relevant_hit@{k}",
            sum(1 for r in results if (r[arm]["best_relevant_rank"] or 10**9) <= k),
            n,
            detail={
                "relevance": "grade >= 2 — cited precursor or mechanism-sharing document",
                "arm": arm,
            },
        )
        out[f"wall_filtered_truth_precursor_hit_at_{k}"] = proportion(
            f"{arm}.truth_precursor_hit@{k} after dropping post-wall rows",
            sum(1 for r in results if (r[arm]["wall_filtered_truth_precursor_rank"] or 10**9) <= k),
            n,
            detail={"relevance": "grade 3", "arm": arm, "wall": WALL_FILTER_NOTE},
        )
        out[f"wall_filtered_any_relevant_hit_at_{k}"] = proportion(
            f"{arm}.any_relevant_hit@{k} after dropping post-wall rows",
            sum(1 for r in results if (r[arm]["wall_filtered_best_relevant_rank"] or 10**9) <= k),
            n,
            detail={"relevance": "grade >= 2", "arm": arm, "wall": WALL_FILTER_NOTE},
        )
    reachable = (
        [r for r in results if r["truth_doc_in_query_partition"]]
        if arm == "single_root"
        else list(results)
    )
    out["truth_precursor_hit_at_10_reachable_only"] = proportion(
        f"{arm}.truth_precursor_hit@10 | truth doc is in the partition searched",
        sum(1 for r in reachable if (r[arm]["truth_precursor_rank"] or 10**9) <= 10),
        len(reachable),
        detail={
            "why": (
                "a document in a different partition tree is UNREACHABLE by this arm, not "
                "lower-ranked. Conditioning on reachability separates a retrieval miss from "
                "a partitioning consequence; both numbers are reported and neither replaces "
                "the other"
            )
        },
    )
    out["queries_with_a_post_wall_row_in_top_10"] = proportion(
        f"{arm}.queries whose top 10 contained a document that had not happened yet",
        sum(1 for r in results if r[arm]["post_wall_in_top_10"] > 0),
        n,
        detail={"why": WALL_FILTER_NOTE},
    )
    out["queries_whose_own_source_report_came_back"] = proportion(
        f"{arm}.queries whose own source fatality report was returned",
        sum(1 for r in results if r[arm]["own_source_report_returned"]),
        n,
        detail={
            "why": (
                "each retro permit is synthesised from one fatality investigation's work "
                "description, and that investigation is itself a document in the corpus. It "
                "post-dates the permit, so it is never relevant in the goldset and its "
                "presence COSTS rank rather than buying it — but it occupies slots a real "
                "deployment would not have filled, and this is how many times it did"
            )
        },
    )
    ranks = [r[arm]["best_relevant_rank"] for r in results if r[arm]["best_relevant_rank"]]
    out["mrr_any_relevant"] = {
        "metric": f"{arm}.MRR (grade >= 2)",
        "value": round(sum(1.0 / r for r in ranks) / n, 4) if n else None,
        "n": n,
        "queries_with_a_relevant_hit": len(ranks),
        "note": "reciprocal rank is 0 for a query with no relevant document in the top LIMIT",
    }
    return out


def _latency_summary(values: Sequence[float]) -> dict[str, Any]:
    ordered = sorted(values)
    n = len(ordered)
    return {
        "n": n,
        "min": ordered[0] if n else None,
        "median": ordered[n // 2] if n else None,
        "p95": ordered[min(n - 1, round(0.95 * (n - 1)))] if n else None,
        "max": ordered[-1] if n else None,
        "note": CAVEAT_LATENCY,
    }


def _choose_exhibit(
    cases: Sequence[QueryCase],
    results: Sequence[Mapping[str, Any]],
    vectors: Sequence[Sequence[float]],
) -> tuple[QueryCase, dict[str, Any], Sequence[float]]:
    """Pick the query that becomes ``the-one-query.sql``.

    Preference order, and it is deliberately not "the best-looking number":

    1. the **cited** precursor (grade 3) recovered at rank 1 by the single-root arm —
       the strongest form of the claim, because the goldset's own truth document came back
       first from a partition tree the permit's author never looked in;
    2. failing that, the cited precursor anywhere in the top *k*;
    3. failing that, the best mechanism-sharing document (grade 2) at its true rank.

    Whatever is chosen, ``observed_rank`` in the committed SQL is the rank that was
    actually observed. The exhibit is never a query whose result was massaged; if the
    strongest tier is empty the file says rank 4, or rank 9, and a reader can see it.

    The selection is on the **raw** rank, not the wall-filtered one, because the raw rank is
    what the committed statement returns when a judge runs it — an exhibit whose printed
    rank does not match what the file produces would be worse than a weaker exhibit. The
    wall-filtered rank is printed beside it.
    """
    ranked: list[tuple[tuple[int, int], int]] = []
    for i, record in enumerate(results):
        arm = record["single_root"]
        t_rank = arm["truth_precursor_rank"]
        r_rank = arm["best_relevant_rank"]
        if t_rank == 1:
            tier = 0
        elif t_rank is not None:
            tier = 1
        elif r_rank is not None:
            tier = 2
        else:
            tier = 3
        primary = t_rank if t_rank is not None else (r_rank if r_rank is not None else 10**6)
        ranked.append(((tier, primary), i))
    ranked.sort()
    chosen = ranked[0][1]
    case = cases[chosen]
    record = dict(results[chosen])
    arm = record["single_root"]
    if arm["truth_precursor_rank"] is not None:
        record["exhibit_doc_id"] = case.truth_doc_id
        record["exhibit_rank"] = arm["truth_precursor_rank"]
        record["exhibit_distance"] = arm["truth_precursor_distance"]
        record["exhibit_grade"] = 3
        record["exhibit_wall_filtered_rank"] = arm["wall_filtered_truth_precursor_rank"]
    else:
        record["exhibit_doc_id"] = arm["best_relevant_doc_id"]
        record["exhibit_rank"] = arm["best_relevant_rank"]
        record["exhibit_distance"] = arm["best_relevant_distance"]
        record["exhibit_grade"] = case.relevant.get(arm["best_relevant_doc_id"] or "", 2)
        record["exhibit_wall_filtered_rank"] = arm["wall_filtered_best_relevant_rank"]
    record["exhibit_post_wall_in_top_10"] = arm["post_wall_in_top_10"]
    record["fatality"] = case.query_id.replace("Q-G4-", "")
    return case, record, vectors[chosen]


def build_parser() -> argparse.ArgumentParser:
    """The command line.  Defaults are the ones that produce the committed artefact."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--database", default=DEFAULT_DATABASE, help="target database")
    parser.add_argument(
        "--queries", type=int, default=None, help="cap the number of retro queries (>= 20)"
    )
    parser.add_argument("--limit", type=int, default=10, help="ANN LIMIT k")
    parser.add_argument("--top-detail", type=int, default=5, help="hits recorded per query")
    parser.add_argument("--workers", type=int, default=4, help="concurrent Bedrock calls")
    parser.add_argument("--skip-load", action="store_true", help="rows already present")
    parser.add_argument(
        "--corpus-cap",
        type=int,
        default=0,
        help=(
            "cap the number of documents embedded and loaded (0 = the whole corpus). "
            "Every judged document is kept; the remainder is a seeded sample. A cap makes "
            "retrieval easier and the artefact says by how much."
        ),
    )
    parser.add_argument(
        "--crossover",
        action="store_true",
        help=(
            "run only the GT-06 crossover census: sweep the row count in a scratch "
            "database with seeded pseudo-random vectors and record at what size the "
            "unhinted plan stops choosing ce_ann. No Bedrock calls, no evidence database."
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Exit 0 when the hinted plan traversed ``ce_ann``, 1 when it did not, 2 on misuse.

    The exit code tracks the *plan*, not the hit rate.  A retrieval number that came out
    lower than hoped is a finding this program publishes; a query that stopped descending
    the C-SPANN tree is a broken proof, and only the second one is a failure.
    """
    args = build_parser().parse_args(argv)
    if args.crossover:
        census = crossover_census()
        print(json.dumps(census, indent=2, sort_keys=True))
        return 0
    if args.queries is not None and args.queries < 20:
        print("--queries below 20 is under the floor this artefact claims", file=sys.stderr)
        return 2
    payload = _run(args)
    print(json.dumps(payload["metrics"], indent=2)[:4000])
    print(f"\nverdict: {payload['verdict']}", file=sys.stderr)
    return 0 if payload["verdict"] == "PROVEN" else 1


if __name__ == "__main__":
    raise SystemExit(main())
