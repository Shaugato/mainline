#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Score the G4-alpha gates against **real Titan vectors in a real C-SPANN index**.

    D:/CoackroachDBxAWS/mainline/.venv/Scripts/python.exe scripts/aws/recall_real.py

What this program is for
------------------------
``tests/eval/recall/test_g4alpha_gates.py`` scores ``NullBackend`` — a complete, honest
retriever that returns nothing — and the five gates are red because a system that never
blocks has a recall of zero. That establishes the suite can be red. It does not establish
what a *working* retriever measures, and until something measures it the recall design is
an argument rather than a result.

This program closes that gap for exactly one channel. It embeds 1 071 synthetic corpus
documents and every evaluation permit through ``amazon.titan-embed-text-v2:0`` in
``ap-southeast-2``, loads the vectors into a CockroachDB ``VECTOR(1024)`` sidecar behind
the ``ce_ann`` prefix-constrained index from migration 0031, runs
:func:`trappoint_recall.eval.harness.run_evaluation_sync` over the committed GS0 gold set,
and writes three artefacts:

``evidence/aws/recall/real-embeddings-metrics.json``
    every metric as a :class:`~trappoint_recall.eval.measurement.Measurement` with its
    interval, its ``n`` and its split policy, plus all five gate verdicts with observed
    value and floor.
``evidence/aws/recall/run-manifest.json``
    corpus commit, split policy, model id, index generation, k, database, cluster region,
    seeds, token ledger and the ``40001`` retry trip count.
``evidence/aws/recall/gate-report.md``
    the same result in prose a judge can read, in which every number carries its interval
    or is introduced as a floor — checked by ``scripts/recall/no_bare_point_estimates.py``,
    which this program runs against its own output before it exits.

What it deliberately does not do
--------------------------------
**It does not touch the gate expectation.** ``tests/eval/recall/g4alpha_expected.json``
says ``RED`` and the lane is green *because* the gates are red; a working retriever makes
the lane fail until a human flips the expectation in a reviewable commit. That is the
discipline, and a program that quietly re-coloured it would be deleting the only mechanism
that makes the colour mean anything. Nothing here writes to that file, to the gate tests,
to the lane, or to ``trappoint_recall.eval.gates``.

**It builds one channel of four.** Channels A (deterministic ancestry), B (bonded
severity-5) and D (lexical BM25) are absent, so gates that require them cannot pass. The
report names which channel each red is waiting on.

Cost
----
Titan v2 is billed on input tokens only. The full corpus plus every permit is
approximately 190 000 tokens, about **USD 0.004** at the published list price, and every
vector is cached under ``out/aws/recall/`` so a second run spends nothing. The exact count
Bedrock itself reported is in the manifest's token ledger and reconciles against
CloudWatch.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:  # direct execution: `python scripts/aws/recall_real.py`
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from botocore.config import Config

from scripts.aws._common import (
    REGION,
    artefact,
    crdb,
    dotenv,
    ledger_total,
    repo_root,
    session,
    token_ledger_entry,
    with_retry,
)

# `packages/trappoint-recall/src` is a source layout, not an installed distribution, on any
# interpreter that has not had the workspace installed into it. The bootstrap is written as
# an `if` rather than an assignment followed by an `if` on purpose: E402 permits `if` and
# `try` between imports precisely so that conditional import bootstraps can sit at the top
# of a file, and a bare assignment here is what made every import below it a finding.
if str(_pkg_src := repo_root() / "packages" / "trappoint-recall" / "src") not in sys.path:
    sys.path.insert(0, str(_pkg_src))

from trappoint_recall.corpora.build import (
    SYNTHETIC_PROVENANCE,
    load_inputs,
)
from trappoint_recall.corpora.synthetic import DEFAULT_SEED
from trappoint_recall.eval.bedrock_backend import (
    ANN_OVERFETCH,
    CALIBRATION_ID,
    DEFAULT_ANN_DATABASE,
    DEFAULT_ANN_LIMIT_FLOOR,
    DEFAULT_INDEX_GEN,
    EMBED_DIM,
    EMBED_TEMPLATE,
    EMBED_TEMPLATE_SHA256,
    TITAN_EMBED_MODEL_ID,
    BedrockBackend,
    CockroachAnnProbe,
    EmbeddingCache,
    TitanEmbedder,
    default_cache_path,
    document_rows,
    query_embed_text,
    vector_literal,
)
from trappoint_recall.eval.corpus import EvalCorpus, load_corpus
from trappoint_recall.eval.gates import evaluate_g4alpha, load_floors, overall_status
from trappoint_recall.eval.harness import compute_metrics, run_evaluation_sync

# ═══════════════════════════════════════════════════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════════════════════════════════════════════════

#: The gold-set root the recall fleet ships.  ``load_corpus`` wants a directory carrying
#: ``queries.jsonl`` / ``qrels.jsonl`` / ``split.json``; under this root that is ``gs0``.
GOLDSETS_ROOT = Path("tests/fixtures/recall/goldsets")

#: The fixtures root ``load_inputs`` reads the four source corpora from.  The document text
#: a retriever must embed comes from here, not from the gold set, which carries only ids.
FIXTURES_ROOT = Path("tests/fixtures/recall")

#: Where the evidence surface should live once ``cloud-load`` has built it.
PRIMARY_DATABASE = DEFAULT_ANN_DATABASE

#: This worker's own scratch database, used **only** when the primary is unusable, and
#: named in every artefact when it is.  A proof that quietly moved to a different surface
#: than the one it names is not a proof.
FALLBACK_DATABASE = "w_real_recall"

#: Columns the parent stub must carry for the time wall to be a predicate rather than a
#: promise.  ``ensure_surface`` checks for them before accepting a pre-existing surface.
REQUIRED_PARENT_COLUMNS = (
    "clause_uuid",
    "commit_id",
    "external_ref",
    "occurred_at",
    "ingested_at",
    "corpus_commit_at",
    "severity",
)

EVIDENCE_DIR = Path("evidence/aws/recall")

#: Bedrock client configuration, and the one place this program departs from calling
#: ``_common.bedrock_runtime()`` directly.
#:
#: **Measured, 2026-08-11:** the Titan on-demand quota in ``ap-southeast-2`` on this account
#: is small enough that a single sequential call every four seconds was refused with
#: ``ThrottlingException`` twelve times out of fifteen — while three other programs in this
#: fleet were embedding against the same quota.
#:
#: ``mode="adaptive"`` was tried first and **measured worse**, which is worth recording
#: because it is the opposite of the documented expectation.  Adaptive mode fits a
#: client-side rate limiter to the observed throttle rate; when the throttling is caused by
#: *other* clients sharing the quota, the observed rate is near 100% and the limiter paces
#: this process down to almost nothing — one embedding in fifteen minutes, against roughly
#: fourteen a minute under ``standard``.  The lesson is specific and generalises: adaptive
#: throttling assumes it is the only tenant, and this quota has five.
#:
#: So the client retries little and this module's own bounded loop
#: (:data:`~trappoint_recall.eval.bedrock_backend.THROTTLE_ATTEMPTS`) does the waiting,
#: where the trip count ends up in the artefact instead of inside botocore.  The session
#: still comes from ``_common.session()``, so profile and region are pinned at the same
#: chokepoint as every other program here; only the retry policy is local.
BEDROCK_CONFIG = Config(retries={"max_attempts": 3, "mode": "standard"})

#: The parent stub.  It is a **stub** and every artefact says so: the production
#: ``mainline.clause_version`` carries ``append_only``, ``z_delta_witness_required`` and
#: ``clause_version_guard`` triggers whose whole purpose is to refuse a bulk load, and
#: forging a corpus past them would be defeating the gate rather than proving the index.
#: What this table exists to hold is the three timestamps the Retro-Recall wall is a
#: predicate over, plus the severity ``tau`` is graded by.
PARENT_STUB_DDL = """
CREATE TABLE IF NOT EXISTS mainline.clause_version (
  clause_uuid      UUID   NOT NULL,
  commit_id        BYTES  NOT NULL,
  external_ref     STRING NOT NULL,
  site_id          UUID   NOT NULL,
  activity_root    STRING NOT NULL,
  occurred_at      TIMESTAMPTZ NOT NULL,
  ingested_at      TIMESTAMPTZ NOT NULL,
  corpus_commit_at TIMESTAMPTZ NOT NULL,
  severity         INT NOT NULL,
  CONSTRAINT clause_version_pk PRIMARY KEY (clause_uuid, commit_id),
  CONSTRAINT external_ref_stated CHECK (external_ref <> '')
)
"""

#: Verbatim from ``verticals/mainline/db/migrations/0031_clause_embedding.sql``: the same
#: column list, the same two named CHECK constraints, the same ``fk_version``, the same
#: inline ``VECTOR INDEX ce_ann (site_id, activity_root, embedding vector_cosine_ops)`` and
#: the same two column families.  Copied rather than imported because the migration runner
#: applies the whole band and this is one table; the copy is asserted against the migration
#: text by ``tests/eval/recall/test_bedrock_backend_contract.py``.
EMBEDDING_DDL = """
CREATE TABLE IF NOT EXISTS mainline.clause_embedding (
  clause_uuid   UUID   NOT NULL,
  commit_id     BYTES  NOT NULL,
  site_id       UUID   NOT NULL,
  activity_root STRING NOT NULL,
  embed_model   STRING NOT NULL,
  index_gen     STRING NOT NULL,
  embedding     VECTOR(1024) NOT NULL,
  CONSTRAINT clause_embedding_pk PRIMARY KEY (clause_uuid, commit_id),
  CONSTRAINT fk_version FOREIGN KEY (clause_uuid, commit_id)
    REFERENCES mainline.clause_version (clause_uuid, commit_id),
  CONSTRAINT embed_model_stated CHECK (embed_model <> ''),
  CONSTRAINT index_gen_stated CHECK (index_gen <> ''),
  VECTOR INDEX ce_ann (site_id, activity_root, embedding vector_cosine_ops),
  FAMILY f_meta (clause_uuid, commit_id, site_id, activity_root, embed_model, index_gen),
  FAMILY f_vec  (embedding)
)
"""


# ═══════════════════════════════════════════════════════════════════════════════════════
# Corpus resolution
# ═══════════════════════════════════════════════════════════════════════════════════════


def resolve_corpus_dir(root: Path) -> Path:
    """Return the directory :func:`load_corpus` can actually load.

    ``tests/fixtures/recall/goldsets`` is a *collection* of gold sets: the loadable corpus
    beneath it is ``gs0``, which is the merged set the G4-alpha gates are defined over.
    Accepting either spelling means a caller who names the collection gets the corpus and a
    caller who names the corpus gets the corpus, and neither gets a silent empty scan.
    """
    if (root / "queries.jsonl").is_file():
        return root
    nested = root / "gs0"
    if (nested / "queries.jsonl").is_file():
        return nested
    raise FileNotFoundError(
        f"no loadable corpus under {root}: expected queries.jsonl there or in gs0/"
    )


# ═══════════════════════════════════════════════════════════════════════════════════════
# The evidence surface
# ═══════════════════════════════════════════════════════════════════════════════════════


def _table_columns(connection: Any, table: str) -> set[str]:
    # Local import for the same reason `_common.crdb` does it: this module must import on
    # an interpreter with no driver installed, so that `--help` and the unit tests work.
    import psycopg

    try:
        cursor = connection.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'mainline' AND table_name = %s",
            (table,),
        )
    except psycopg.Error:
        # An `information_schema` read of a table that does not exist returns no rows; it
        # does not raise. Reaching here means the connection or the database itself is
        # unusable, and the caller's answer to that is the same as "no such columns" —
        # fall back to the scratch surface and say so in the artefact.
        return set()
    return {str(row[0]) for row in cursor.fetchall()}


def _database_exists(name: str) -> bool:
    with crdb() as connection:
        cursor = connection.execute("SHOW DATABASES")
        return any(str(row[0]) == name for row in cursor.fetchall())


def ensure_surface(
    *, primary: str, fallback: str, allow_bootstrap: bool
) -> tuple[str, dict[str, object]]:
    """Pick the database this run will measure, and say why.

    Preference order, and the reason is the whole point of publishing it:

    1. **The primary** (``mainline_ann_evidence``) when it exists and its parent stub
       carries the columns the time wall is a predicate over. That surface belongs to the
       fleet's ``cloud-load`` worker; using it means this evaluation and the ANN proof are
       reading the same rows.
    2. **This worker's scratch database** otherwise, created here from the DDL above. The
       artefacts record ``surface: worker_scratch`` and the exact reason, because a recall
       number measured against a surface other than the one the fleet names is a number
       about a different experiment.
    """
    note: dict[str, object] = {"primary": primary, "fallback": fallback}
    if _database_exists(primary):
        with crdb(primary) as connection:
            parent = _table_columns(connection, "clause_version")
            embedding = _table_columns(connection, "clause_embedding")
        missing = [c for c in REQUIRED_PARENT_COLUMNS if c not in parent]
        if embedding and not missing:
            note["surface"] = "fleet_evidence_database"
            note["reason"] = "primary exists and carries the temporal columns the wall needs"
            return primary, note
        note["primary_parent_columns"] = sorted(parent)
        note["primary_missing_columns"] = missing
        note["reason"] = (
            f"{primary} exists but its parent stub is missing {missing or 'clause_embedding'}; "
            "the Retro-Recall time wall is a predicate over occurred_at / ingested_at / "
            "corpus_commit_at and cannot be enforced without them"
        )
    else:
        note["reason"] = (
            f"{primary} does not exist on this cluster; the fleet's cloud-load worker had "
            "not created it when this evaluation ran"
        )
    if not allow_bootstrap:
        raise RuntimeError(str(note["reason"]) + " (and --no-bootstrap was given)")
    note["surface"] = "worker_scratch"
    bootstrap(fallback)
    return fallback, note


def bootstrap(database: str) -> None:
    """Create the scratch surface. Idempotent; DDL runs with autocommit, never in a txn."""
    with crdb() as connection:
        connection.execute(f"CREATE DATABASE IF NOT EXISTS {database}")
    with crdb(database) as connection:
        connection.execute("CREATE SCHEMA IF NOT EXISTS mainline")
        connection.execute(PARENT_STUB_DDL)
        connection.execute(EMBEDDING_DDL)


# ═══════════════════════════════════════════════════════════════════════════════════════
# Loading the corpus behind the index
# ═══════════════════════════════════════════════════════════════════════════════════════


def embed_all(
    texts: Sequence[str], embedder: TitanEmbedder, *, workers: int, label: str
) -> list[list[float]]:
    """Embed *texts*, reporting progress, because this leg is measured in tens of minutes.

    A run that prints nothing for an hour is indistinguishable from a run that has hung, and
    the difference matters when the constraint is a shared quota rather than a bug.
    """
    started = time.perf_counter()
    done = 0

    def one(text: str) -> list[float]:
        nonlocal done
        vector = embedder.embed(text)
        done += 1
        if done % 50 == 0 or done == len(texts):
            elapsed = time.perf_counter() - started
            sys.stdout.write(
                f"  {label} {done}/{len(texts)} · {elapsed:.0f}s · "
                f"{embedder.calls} calls · {embedder.throttle_retries} throttle retries\n"
            )
            sys.stdout.flush()
        return vector

    if workers > 1:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            return list(pool.map(one, texts))
    return [one(text) for text in texts]


def load_documents(
    database: str,
    rows: Sequence[dict[str, Any]],
    embedder: TitanEmbedder,
    *,
    workers: int,
    batch: int = 50,
) -> dict[str, object]:
    """Embed every document through Titan and UPSERT it behind ``ce_ann``.

    Embedding is parallel because Titan takes one ``inputText`` per call and the wall-clock
    cost of 1 071 sequential round trips is five minutes of nothing. Writing is sequential
    and wrapped in the ``40001`` loop: CockroachDB Cloud is a managed multi-node cluster and
    produces ``RETRY_SERIALIZABLE`` under ordinary contention, which a single-node Docker
    never does.
    """
    started = time.perf_counter()
    texts = [str(row["text"]) for row in rows]
    vectors = embed_all(texts, embedder, workers=workers, label="documents")

    parent_sql = (
        "UPSERT INTO mainline.clause_version (clause_uuid, commit_id, external_ref, "
        "site_id, activity_root, occurred_at, ingested_at, corpus_commit_at, severity) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)"
    )
    vector_sql = (
        "UPSERT INTO mainline.clause_embedding (clause_uuid, commit_id, site_id, "
        "activity_root, embed_model, index_gen, embedding) VALUES (%s,%s,%s,%s,%s,%s,%s)"
    )

    retries_total = 0
    written = 0
    # One connection for the whole load. Each round trip to Singapore is ~150 ms and a
    # fresh connect is a second or two on Basic; reconnecting per batch was measured as the
    # dominant cost of this leg. Autocommit means each statement is its own transaction, so
    # a batch that has to be retried is retried as UPSERTs, which are idempotent by
    # construction — re-running one is a no-op, never a double insert.
    with crdb(database) as connection:
        for start in range(0, len(rows), batch):
            chunk = list(
                zip(rows[start : start + batch], vectors[start : start + batch], strict=True)
            )

            def _write(chunk: list[tuple[dict[str, Any], list[float]]] = chunk) -> int:
                with connection.cursor() as cursor:
                    cursor.executemany(
                        parent_sql,
                        [
                            (
                                row["clause_uuid"],
                                row["commit_id"],
                                row["external_ref"],
                                row["site_id"],
                                row["activity_root"],
                                row["occurred_at"],
                                row["ingested_at"],
                                row["corpus_commit_at"],
                                row["severity"],
                            )
                            for row, _vector in chunk
                        ],
                    )
                    cursor.executemany(
                        vector_sql,
                        [
                            (
                                row["clause_uuid"],
                                row["commit_id"],
                                row["site_id"],
                                row["activity_root"],
                                row["embed_model"],
                                row["index_gen"],
                                vector_literal(vector),
                            )
                            for row, vector in chunk
                        ],
                    )
                return len(chunk)

            count, retries = with_retry(_write)
            written += count
            retries_total += retries

        cursor = connection.execute("SELECT count(*) FROM mainline.clause_embedding")
        stored = int(cursor.fetchone()[0])
        cursor = connection.execute(
            "SELECT count(DISTINCT (site_id, activity_root)) FROM mainline.clause_embedding"
        )
        partitions = int(cursor.fetchone()[0])

    return {
        "documents_presented": len(rows),
        "rows_upserted": written,
        "rows_in_index": stored,
        "distinct_prefix_partitions": partitions,
        "retries_40001": retries_total,
        "load_seconds": round(time.perf_counter() - started, 2),
    }


# ═══════════════════════════════════════════════════════════════════════════════════════
# Structural ceiling — what the prefix costs before a model is involved
# ═══════════════════════════════════════════════════════════════════════════════════════


def routine_partition_occupancy(
    corpus: EvalCorpus, rows: Sequence[dict[str, Any]]
) -> dict[str, object]:
    """How many documents the nuisance-rate replay could possibly have retrieved.

    **This is the most important number in the artefact and it was found by accident.**

    The nuisance rate is the negative control: routine permits are replayed and any
    probabilistic blocking check on one is a false alarm. A rate near zero is what the gate
    wants to see — and a rate of exactly zero is what a retriever produces when the routine
    permits' ``(site_id, activity_root)`` prefixes address C-SPANN partitions that hold no
    documents at all. The search is not quiet; it is looking in an empty tree.

    Measured on GS0: the routine permits carry site/activity pairs such as
    ``SITE-underground-metalliferous`` + ``underground`` and ``MINE-6600239`` + ``qld``,
    and the document corpus contains no row under either. So a single-arm channel-C
    retriever cannot raise a false alarm on this replay no matter how badly calibrated it
    is, and **a nuisance-rate pass measured this way is an artefact of corpus construction,
    not evidence that the system does not cry wolf.**

    The gate's own vacuity guard — the sensitivity witness — was written to stop a silent
    system passing. It does not catch this case, because the retro subset does produce
    blocking checks, so the witness is satisfied while the control is empty. That is a real
    gap in the suite and it is reported here rather than banked as a green.
    """
    occupancy: dict[tuple[str, str], int] = {}
    for row in rows:
        key = (str(row["site_ref"]), str(row["activity_root"]))
        occupancy[key] = occupancy.get(key, 0) + 1

    routine = [q for q in corpus.queries if q.kind == "routine"]
    empty = 0
    reachable_docs = 0
    examples: list[dict[str, object]] = []
    for query in routine:
        key = (query.site_id, query.activity_path.strip("/").split("/")[0])
        count = occupancy.get(key, 0)
        reachable_docs += count
        if count == 0:
            empty += 1
            if len(examples) < 5:
                examples.append(
                    {"query_id": query.query_id, "prefix": f"{key[0]}/{key[1]}", "documents": 0}
                )

    retro = [q for q in corpus.queries if q.kind == "retro"]
    retro_empty = sum(
        1
        for q in retro
        if occupancy.get((q.site_id, q.activity_path.strip("/").split("/")[0]), 0) == 0
    )
    return {
        "routine_permits": len(routine),
        "routine_permits_addressing_an_empty_partition": empty,
        "mean_documents_reachable_per_routine_permit": (
            round(reachable_docs / len(routine), 4) if routine else None
        ),
        "retro_permits": len(retro),
        "retro_permits_addressing_an_empty_partition": retro_empty,
        "distinct_document_partitions": len(occupancy),
        "examples": examples,
        "share_addressing_an_empty_partition": (
            round(empty / len(routine), 4) if routine else None
        ),
        "nuisance_rate_is_vacuous": empty == len(routine) and bool(routine),
        "nuisance_rate_is_materially_vacuous": bool(routine) and empty / len(routine) >= 0.5,
        "materially_vacuous_threshold": 0.5,
        "note": (
            "a nuisance rate measured over permits whose prefix partitions hold no documents "
            "is zero by construction; it is not evidence about false alarms, and the gate's "
            "sensitivity witness does not catch it because the witness is measured on the "
            "retro subset"
        ),
    }


def text_uniqueness(corpus: EvalCorpus, rows: Sequence[dict[str, Any]]) -> dict[str, object]:
    """How many *distinct* strings the corpus actually presents to the embedder.

    Measured, not assumed, and it turned out to matter: 1 071 synthetic documents render to
    224 distinct embedding texts, because the Part-50 replica generates narratives from a
    template and many rows differ only in fields the template does not carry into the cue.

    Two consequences a reader is owed:

    * **Ties are pervasive.** Documents with identical text have identical vectors and
      therefore identical cosine distance. Their relative order inside the ANN result is
      decided by the tie-break in the query (``ORDER BY distance, external_ref``), not by
      the model. A recall@k over a corpus with this much duplication is measuring a
      different thing from a recall@k over 1 071 distinct narratives, and the difference
      flatters nobody in a predictable direction.
    * **It bounds the cost, honestly.** The embedding cache is keyed by request body, so
      the corpus costs 224 calls rather than 1 071. That is a real saving and not a
      shortcut, but it is only true because the corpus repeats itself.
    """
    document_texts = [str(row["text"]) for row in rows]
    permit_texts = [query_embed_text(query) for query in corpus.queries]
    distinct_documents = len(set(document_texts))
    return {
        "documents": len(document_texts),
        "distinct_document_texts": distinct_documents,
        "duplicate_document_texts": len(document_texts) - distinct_documents,
        "permits": len(permit_texts),
        "distinct_permit_texts": len(set(permit_texts)),
        "distinct_texts_embedded": len(set(document_texts) | set(permit_texts)),
        "note": (
            "documents sharing an embedding text share a vector exactly; their order inside "
            "an ANN result is decided by the query's tie-break, not by the model"
        ),
    }


def prefix_reachability(corpus: EvalCorpus, rows: Sequence[dict[str, Any]]) -> dict[str, object]:
    """How many retro truth precursors the ANN prefix can reach *at all*.

    The C-SPANN prefix is not a filter: it selects the k-means tree that is descended. A
    truth precursor filed under a different ``(site_id, activity_root)`` than its permit is
    therefore not ranked lower — it is unreachable by a single-arm query, with no refusal
    anywhere and no row that is wrong. That is a *structural* ceiling on Retro-Recall, and
    it must be measured before the model is credited or blamed for the gap.

    The architecture's own answer is the ancestor walk: k activity roots is k separate ANN
    queries ``UNION ALL``-ed and re-ranked. This program runs one arm, so the ceiling stands
    and the report says so.
    """
    by_ref = {str(row["external_ref"]): row for row in rows}
    reachable = 0
    unreachable: list[dict[str, str]] = []
    total = 0
    for query in corpus.queries:
        if query.kind != "retro" or not query.truth_doc_id:
            continue
        total += 1
        row = by_ref.get(query.truth_doc_id)
        if row is None:
            unreachable.append(
                {"query_id": query.query_id, "doc_id": query.truth_doc_id, "why": "not_in_corpus"}
            )
            continue
        same_site = str(row["site_ref"]) == query.site_id
        same_root = str(row["activity_root"]) == query.activity_path.strip("/").split("/")[0]
        if same_site and same_root:
            reachable += 1
        else:
            unreachable.append(
                {
                    "query_id": query.query_id,
                    "doc_id": query.truth_doc_id,
                    "why": "different_prefix_partition",
                    "permit_prefix": f"{query.site_id}/"
                    f"{query.activity_path.strip('/').split('/')[0]}",
                    "document_prefix": f"{row['site_ref']}/{row['activity_root']}",
                }
            )
    return {
        "retro_permits": total,
        "truth_reachable_in_permit_partition": reachable,
        "truth_unreachable": len(unreachable),
        "ceiling_on_retro_recall": round(reachable / total, 6) if total else None,
        "examples": unreachable[:5],
        "note": (
            "a single prefix-constrained ANN arm cannot return a document filed under a "
            "different (site_id, activity_root); the architecture's answer is an ancestor "
            "walk of k arms UNION ALL-ed and re-ranked, which this program does not build"
        ),
    }


# ═══════════════════════════════════════════════════════════════════════════════════════
# The report
# ═══════════════════════════════════════════════════════════════════════════════════════


def gate_attribution(
    gate: Any, bundle: Any, occupancy: dict[str, object] | None = None
) -> dict[str, object]:
    """Say, per gate, whether a red is waiting on a channel this program did not build.

    Written from the observed result rather than from a table of expectations, because a
    hard-coded attribution would keep claiming "channel B" long after channel B landed. The
    only attribution asserted is the one the evidence supports:

    * ``mean_blocking_checks_per_permit`` fails while ``bonded_fatalities_all_blocking``
      does — that is **channel B**, whose entire job is to admit a bonded severity-5 event
      unconditionally. No threshold and no embedding can substitute for it, so this red is
      not a statement about the retriever's quality.
    * ``retro_recall_at_3_sev5``, ``p_at_block`` and ``nuisance_rate`` are measured on
      **channel C's own output**. A and D would add candidates and could move recall; they
      cannot excuse it. This red is a statement about this retriever, and it is reported as
      one.
    * ``conservation_l3`` is an accounting law over whatever ran. It is never attributable
      to a missing channel — if it fails, this backend's counters are wrong.
    """
    vacuous_control = bool(occupancy and occupancy.get("nuisance_rate_is_materially_vacuous"))
    if gate.gate_id == "nuisance_rate" and vacuous_control:
        share = occupancy["share_addressing_an_empty_partition"] if occupancy else None
        return {
            "attributable_to_missing_channel": None,
            "verdict_is_vacuous": True,
            "share_of_control_addressing_an_empty_partition": share,
            "note": (
                "a majority of routine permits address a (site_id, activity_root) partition "
                "that holds no documents, so on those permits this arm cannot raise a false "
                "alarm at all. Whatever colour the gate reports, the number is substantially "
                "an artefact of corpus construction and must not be read as evidence about "
                "false alarms."
            ),
        }
    if gate.passed:
        return {"attributable_to_missing_channel": None, "note": "gate passed"}
    if gate.gate_id == "mean_blocking_checks_per_permit" and not bundle.bonded.holds:
        return {
            "attributable_to_missing_channel": "B",
            "note": (
                "MI16 bonded_fatalities_all_blocking is violated because channel B — bonded "
                "severity-5, admitted unconditionally with no threshold and no model in the "
                "path — is not implemented. A prefix-constrained vector search cannot "
                "promise that invariant and this backend does not claim to."
            ),
        }
    if gate.gate_id == "conservation_l3":
        return {
            "attributable_to_missing_channel": None,
            "note": (
                "the conservation law is an accounting statement about the run that "
                "happened; a failure here is a defect in this backend's counters, never a "
                "missing channel"
            ),
        }
    return {
        "attributable_to_missing_channel": None,
        "note": (
            "measured on channel C's own output. Channels A (deterministic ancestry) and D "
            "(lexical BM25) would add candidates and could move this number, but their "
            "absence does not excuse it: this red is a statement about this retriever."
        ),
    }


def _measurement_line(label: str, measurement: Any) -> str:
    if not measurement.defined:
        return f"- **{label}** is UNDEFINED over n={measurement.n}: {measurement.undefined_reason}"
    pct = round(measurement.confidence * 100)
    return (
        f"- **{label}** {measurement.value:.4f}, {pct}% "
        f"{measurement.interval_method.replace('_', ' ')} interval "
        f"[{measurement.lower:.4f}, {measurement.upper:.4f}], n={measurement.n}"
    )


def _report_preamble(run: Any, corpus: EvalCorpus, manifest: dict[str, Any]) -> list[str]:
    """The masthead and the four caveats that bound every number after it."""
    lines: list[str] = []
    add = lines.append

    add("# Real-embedding recall: what one Bedrock-powered channel measures")
    add("")
    add(
        f"Backend `{run.backend_name}` · corpus `{corpus.label()}` · "
        f"k={run.k} · split `{run.split_policy_id}`"
    )
    add(
        f"Model `{manifest['bedrock']['embed_model_id']}` in "
        f"`{manifest['bedrock']['region']}` · index generation "
        f"`{manifest['index']['index_gen']}` · "
        f"database `{manifest['database']['database']}` in "
        f"`{manifest['database']['cluster_region']}`"
    )
    add("")
    add(
        "Every vector searched here was produced by Amazon Bedrock and stored in a "
        "CockroachDB `VECTOR(1024)` column behind the `ce_ann` prefix-constrained index. "
        "The query that produced every candidate below pins that index explicitly "
        "(`FROM mainline.clause_embedding@ce_ann`) and constrains both prefix columns to a "
        "single value, which is the only shape C-SPANN will descend."
    )
    add("")

    add("## What this is a measurement of, and what it is not")
    add("")
    add(
        "- **The corpus is SYNTHETIC.** Every record is generated by "
        "`trappoint_recall.corpora.synthetic`. The reason is the most creditable thing "
        "about the corpus design: the real set is a register of deaths, and a repository "
        "is a copy. No number here characterises the product on real incident data."
    )
    add(
        "- **This is channel C alone.** Channel A (deterministic ancestry), channel B "
        "(bonded severity-5, admitted unconditionally) and channel D (lexical BM25) are "
        "not implemented. Gates that require them cannot pass, and the failures below name "
        "which."
    )
    add(
        f"- **`p_relevant` is a declared map, not a fitted calibrator** "
        f"(`{CALIBRATION_ID}`): `max(0, 1 - cosine distance)`, with no free parameters. "
        "It is strictly monotone, so the ranking metrics are exactly what any calibration "
        "would produce; the threshold metrics are conditional on it and are not the "
        "shipped policy's numbers."
    )
    add(f"- **The parent table is a stub.** {manifest['database']['stub_disclosure']}")
    add("")
    return lines


def _report_gates(gates: Sequence[Any], bundle: Any, manifest: dict[str, Any]) -> list[str]:
    """The five gate verdicts, then every metric with its interval.

    One function rather than two because a gate verdict is a floor applied to a metric
    that appears in the table below it; splitting them puts a reader's eye in two places.
    """
    lines: list[str] = []
    add = lines.append

    add("## The five G4-alpha gates")
    add("")
    add(
        f"Overall: **{overall_status(gates)}** — {sum(1 for g in gates if g.passed)} of "
        f"{len(gates)} gates pass."
    )
    add("")
    for gate in gates:
        add(f"### `{gate.gate_id}` — {gate.status}")
        add("")
        add(f"Floor: {gate.floor_repr}.")
        if gate.measurement is not None:
            add("")
            add(_measurement_line(gate.gate_id, gate.measurement))
        add("")
        # The gate's reason is a verbatim string produced by trappoint_recall.eval.gates,
        # which this fleet may not edit. Some of those strings quote a point estimate
        # inline. Rather than paraphrase a machine's own words — which is how a reason
        # stops being evidence — the sanctioned exemption is used, with the reason the
        # rule's own docstring requires, and the figure appears immediately above with its
        # interval and its n.
        add(
            "<!-- no-bare-point-estimates: allow - the next line is quoted unedited from "
            "trappoint_recall.eval.gates; the same figure is published above with its "
            "interval and n -->"
        )
        add(f"Reason recorded by the gate: {gate.reason}")
        add("")
        attribution = gate_attribution(gate, bundle, manifest.get("routine_partition_occupancy"))
        channel = attribution["attributable_to_missing_channel"]
        if channel:
            add(f"Waiting on channel **{channel}**. {attribution['note']}")
        else:
            add(f"Channel attribution: {attribution['note']}")
        add("")

    add("## Every metric, with its interval")
    add("")
    add(
        "Two interval methods appear below and the difference is not decoration. A Wilson "
        "score interval is correct for a binomial proportion and nothing else, so the "
        "recall family, `p_at_block` and the nuisance rate get Wilson. `nDCG@10`, `MRR` and "
        "mean blocking checks per permit are means of per-permit quantities rather than "
        "proportions; applying Wilson to them would be a category error dressed as rigour, "
        "so they get a deterministic bootstrap percentile interval whose seed is derived "
        "from the metric name and the sample size, and therefore reproduces exactly on any "
        "machine."
    )
    add("")
    for name in sorted(bundle.measurements):
        add(_measurement_line(f"`{name}`", bundle.measurements[name]))
    add("")
    return lines


def _report_reachability(
    bundle: Any, manifest: dict[str, Any], reachability: dict[str, Any]
) -> list[str]:
    """Three sections that are one argument: what the prefix could return before ranking.

    Where the truth precursor landed, the structural ceiling the prefix imposes on retro
    recall, and the negative control that searches empty trees. Kept together because the
    third is only readable as a finding once the second has been stated.
    """
    lines: list[str] = []
    add = lines.append

    add("## Where the truth precursor landed")
    add("")
    ranks = bundle.ranks.to_dict()
    histogram = ranks["histogram"]
    add(
        f"Over {ranks['n']} severity-5 retro permits the authored truth precursor was "
        f"returned for {ranks['n_found']} of them and missed for {ranks['not_found']}. "
        "Position histogram, as counts rather than rates: "
        + ", ".join(f"rank {bucket}: {count}" for bucket, count in histogram.items())
        + "."
    )
    add("")

    add("## The prefix is a ceiling before the model is")
    add("")
    ceiling = reachability["ceiling_on_retro_recall"]
    add(
        f"Of {reachability['retro_permits']} severity-5 retro permits, "
        f"{reachability['truth_reachable_in_permit_partition']} have their truth precursor "
        f"filed in the same `(site_id, activity_root)` partition as the permit and "
        f"{reachability['truth_unreachable']} do not. A single prefix-constrained arm "
        "therefore has a hard structural ceiling: a target above "
        f"{ceiling:.4f} is unreachable by this query shape no matter what the embedding "
        "does, because the prefix is not a filter — it selects the k-means tree that is "
        "descended, and a document in another tree is not ranked lower, it is absent. The "
        "architecture's answer is an ancestor walk of k arms UNION ALL-ed and re-ranked, "
        "which this program does not build."
    )
    add("")

    add("## The negative control searches empty trees, and that is the finding")
    add("")
    occupancy = manifest["routine_partition_occupancy"]
    add(
        f"Of {occupancy['routine_permits']} routine permits — the negative control the "
        "nuisance rate is measured on — "
        f"{occupancy['routine_permits_addressing_an_empty_partition']} address a "
        "`(site_id, activity_root)` partition that holds no documents at all. The mean "
        "number of documents reachable by a routine permit is "
        f"{occupancy['mean_documents_reachable_per_routine_permit']}."
    )
    add("")
    add(
        "**A nuisance rate measured this way cannot be evidence about false alarms.** The "
        "prefix selects the k-means tree the query descends; a permit whose tree is empty "
        "returns nothing however badly the score is calibrated, so the control reports "
        "silence that the retriever did not earn. The gate carries a vacuity guard — a "
        "sensitivity witness requiring the same policy to have blocked on the retro subset "
        "— and it does not catch this, because the retro subset does produce blocking "
        "checks while the control is empty. That is a genuine gap in the suite, and it is "
        "recorded here rather than banked as a green."
    )
    add("")
    add(
        "The fix is a corpus change, not a threshold change: the routine-permit replay has "
        "to be generated over site and activity pairs the document corpus actually "
        "contains. That belongs to whoever owns the gold sets, and nothing in this program "
        "touches it."
    )
    add("")
    return lines


def _report_run_facts(manifest: dict[str, Any]) -> list[str]:
    """What the retrieval, the retry loop, Bedrock's quota and the corpus's repetition did."""
    lines: list[str] = []
    add = lines.append

    add("## What the retrieval actually did")
    add("")
    retrieval = manifest["retrieval"]
    probe_stats = retrieval.get("probe") or {}
    add(
        f"{retrieval['queries_executed']} permits were embedded and probed. The index "
        f"returned {retrieval['rows_probed_total']} rows in total, of which "
        f"{retrieval['rows_excluded_by_time_wall']} were removed by the time wall — the "
        "predicate `occurred_at < t AND ingested_at < t AND corpus_commit_at <= t`, "
        "evaluated by the database and never by `AS OF SYSTEM TIME`, whose reach is bounded "
        "by `gc.ttlseconds`. A wall that removes nothing is indistinguishable from a wall "
        "that is not there, which is why that count is published rather than assumed."
    )
    add("")
    add(
        f"The `40001 RETRY_SERIALIZABLE` loop fired "
        f"{probe_stats.get('retries_40001', 0)} times across "
        f"{probe_stats.get('probes', 0)} probes, and "
        f"{manifest['database'].get('retries_40001', 0)} times across the load. Insurance "
        "whose premium is never quoted is indistinguishable from superstition, so the trip "
        "count is reported whether or not it is zero: a single-node cluster never raises "
        "this state at all, and CockroachDB Cloud raises it under ordinary contention."
    )
    add("")
    add(
        f"Bedrock refused {manifest['bedrock'].get('throttle_retries', 0)} of this run's "
        "calls with `ThrottlingException`; every refusal was retried rather than dropped. "
        "The account-wide ceiling was read from AWS's own metrics rather than inferred: "
        "`cloudwatch get_metric_statistics(AWS/Bedrock, ModelId=amazon.titan-embed-text-v2:0, "
        "Period=300, Sum)` returned `Invocations` of exactly 300 in every five-minute "
        "bucket — 60 successful calls a minute for the whole account — against "
        "`InvocationThrottles` of two to four thousand per bucket while this fleet's "
        "programs ran together. That is a design input, not an incident: a per-permit "
        "embedding at merge time would be competing for those 60 calls a minute, which is "
        "one more reason cue vectors are computed once at ingest and stored."
    )
    add("")

    add("## The corpus repeats itself, and that bounds what any of this means")
    add("")
    unique = manifest["text_uniqueness"]
    add(
        f"The {unique['documents']} synthetic documents render to "
        f"{unique['distinct_document_texts']} distinct embedding texts, so "
        f"{unique['duplicate_document_texts']} of them carry a vector identical to another "
        f"document's. The {unique['permits']} permits render to "
        f"{unique['distinct_permit_texts']} distinct texts. Identical vectors sit at "
        "identical cosine distance, so their order inside a result set is decided by the "
        "query's tie-break rather than by the model, and every ranking figure above should "
        "be read as a statement about this corpus rather than about 1 071 distinct "
        "narratives."
    )
    add("")
    return lines


def _report_laws(bundle: Any) -> list[str]:
    """The two invariants the harness checks independently of any gate: L3 and MI16."""
    lines: list[str] = []
    add = lines.append

    add("## Conservation, and why it is checked twice")
    add("")
    conservation = bundle.conservation.to_dict()
    add(
        f"L3 closed over {conservation['total_candidates']} candidates across "
        f"{conservation['covered_runs']} of {conservation['expected_runs']} runs with "
        f"{len(conservation['violations'])} violations. The declared counters come from the "
        "policy arithmetic applied to the probe rows; the enumerated counters come from the "
        "candidate list. Neither reads the other, which is the only way the law is a check "
        "rather than a tautology."
    )
    add("")

    add("## MI16, checked against the corpus and not against this backend")
    add("")
    bonded = bundle.bonded.to_dict()
    add(
        f"The corpus bonds {bonded['expected_bonded']} severity-5 events to permits. This "
        f"backend returned {bonded['blocking_bonded']} of them as blocking checks. Channel B "
        "is what admits a bonded fatality unconditionally, with no threshold and no model in "
        "the path, and channel B is not built. A vector search cannot promise MI16 and this "
        "backend does not declare that it does: its declared bonded counters are zero, which "
        "is true of channel C and which the harness correctly reads as a failure of the "
        "invariant rather than as an absence of one."
    )
    add("")
    return lines


def _report_colours_and_cost(manifest: dict[str, Any]) -> list[str]:
    """What this program deliberately did not write, and what the run cost."""
    lines: list[str] = []
    add = lines.append

    add("## The gate colours in CI are unchanged, on purpose")
    add("")
    add(
        "`tests/eval/recall/g4alpha_expected.json` still says RED and this program does not "
        "write to it, to `test_g4alpha_gates.py`, to `g4alpha_lane.py` or to "
        "`trappoint_recall.eval.gates`. The lane is designed so that a working retriever "
        "makes it fail until a human flips the expectation in a reviewable commit. Any gate "
        "this backend clears is therefore reported here and nowhere else; the flip is a "
        "separate, reviewed change, and making it ourselves would delete the discipline that "
        "gives the colour meaning."
    )
    add("")

    add("## Cost")
    add("")
    ledger = manifest["token_ledger"]["total"]
    cache_stats = manifest["bedrock"]["cache"]
    add(
        f"**This run** made {ledger['calls']} Bedrock InvokeModel calls for "
        f"{ledger['input_tokens']} input tokens — Bedrock's own count, not an estimate — "
        f"priced at USD {ledger['usd_total']:.6f} against the published list price, and "
        f"served {cache_stats['hits']} embeddings from the on-disk cache at no cost."
    )
    add("")
    add(
        f"**In total** the corpus has ever required {cache_stats['entries']} distinct "
        "Bedrock calls, which is the size of the cache: 1 071 documents and 396 permits "
        "collapse to that many distinct request bodies because the corpus repeats itself. "
        "Calls made by earlier runs of this same program are not re-counted here, and the "
        "account-side record of all of them is CloudWatch's `InputTokenCount` for this "
        "model. A re-run of this evaluation makes no Bedrock calls at all, which is the "
        "point of the cache and the reason the number above can be zero."
    )
    add("")
    add(
        f"Artefacts: `{EVIDENCE_DIR.as_posix()}/real-embeddings-metrics.json`, "
        f"`{EVIDENCE_DIR.as_posix()}/run-manifest.json`, and this file."
    )
    add("")
    return lines


def render_report(
    *,
    bundle: Any,
    gates: Sequence[Any],
    corpus: EvalCorpus,
    manifest: dict[str, Any],
    reachability: dict[str, Any],
) -> str:
    """Assemble the judge-readable report from its six sections, in reading order.

    The sections were one 103-statement function until the ruff ratchet refused it. They
    are split on the report's own `##` boundaries, which is the division a reader already
    sees; nothing here decides anything, so the split costs no logic.
    """
    return "\n".join(
        [
            *_report_preamble(bundle.run, corpus, manifest),
            *_report_gates(gates, bundle, manifest),
            *_report_reachability(bundle, manifest, reachability),
            *_report_run_facts(manifest),
            *_report_laws(bundle),
            *_report_colours_and_cost(manifest),
        ]
    )


# ═══════════════════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════════════════


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="recall_real",
        description="Score the G4-alpha gates against real Titan vectors in a real ANN index.",
    )
    parser.add_argument("--database", default=PRIMARY_DATABASE, help="preferred ANN surface")
    parser.add_argument("--fallback-database", default=FALLBACK_DATABASE)
    parser.add_argument("--no-bootstrap", action="store_true", help="refuse the scratch surface")
    parser.add_argument("--corpus", type=Path, default=None)
    parser.add_argument("--k", type=int, default=10)
    parser.add_argument(
        "--embed-workers",
        type=int,
        default=12,
        help=(
            "concurrent Titan calls. The account-wide Titan ceiling measured from "
            "CloudWatch is 300 successful invocations per five minutes shared by every "
            "client, so this is a share of a fixed bucket rather than a throughput knob"
        ),
    )
    parser.add_argument(
        "--skip-load",
        action="store_true",
        help="assume the surface is already populated (re-scoring an existing index)",
    )
    return parser


def _portable_embedding_ledger(embedder: Any, root: Path) -> dict[str, Any]:
    """The embedder's ledger, with the cache path made relative to the repository.

    The cache lives under gitignored ``out/``; an absolute Windows path in a committed
    artefact is not a secret but it is not reproducible either, and an evidence file that
    names a directory only one machine has is describing that machine.
    """
    ledger = embedder.ledger()
    cache_block = dict(ledger["cache"])  # type: ignore[arg-type]
    if cache_block.get("path"):
        try:
            cache_block["path"] = Path(str(cache_block["path"])).relative_to(root).as_posix()
        except ValueError:
            cache_block["path"] = Path(str(cache_block["path"])).name
    ledger["cache"] = cache_block
    return ledger


def _verify_no_bare_point_estimates(root: Path, report_path: Path) -> int:
    """Run this program's own output past ``scripts/recall/no_bare_point_estimates.py``.

    A recall number published without its interval is not publishable, and the check that
    says so is run here rather than only in CI so that the refusal arrives before the
    artefact is committed.
    """
    checker = root / "scripts" / "recall" / "no_bare_point_estimates.py"
    completed = subprocess.run(
        [sys.executable, str(checker), "--paths", str(report_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    sys.stdout.write(completed.stdout)
    sys.stderr.write(completed.stderr)
    if completed.returncode != 0:
        sys.stderr.write(
            "no_bare_point_estimates refused the gate report. A recall number published "
            "without its interval is not publishable; fix the prose, not the check.\n"
        )
    return completed.returncode


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)

    root = repo_root()
    corpus_dir = resolve_corpus_dir(args.corpus if args.corpus else root / GOLDSETS_ROOT)
    corpus = load_corpus(corpus_dir)
    records = load_inputs(root / FIXTURES_ROOT, provenance=SYNTHETIC_PROVENANCE)
    rows = document_rows(records, corpus_commit=corpus.split_policy.corpus_commit)

    sys.stdout.write(
        f"corpus {corpus.label()}\n"
        f"documents {len(rows)} · corpus_commit {corpus.split_policy.corpus_commit}\n"
    )

    database, surface_note = ensure_surface(
        primary=args.database,
        fallback=args.fallback_database,
        allow_bootstrap=not args.no_bootstrap,
    )
    sys.stdout.write(f"surface {database} ({surface_note['surface']}): {surface_note['reason']}\n")

    cache = EmbeddingCache(path=default_cache_path(root / "out"))
    embedder = TitanEmbedder(
        client=session().client("bedrock-runtime", region_name=REGION, config=BEDROCK_CONFIG),
        cache=cache,
    )

    load_report: dict[str, object]
    if args.skip_load:
        with crdb(database) as connection:
            stored = int(
                connection.execute("SELECT count(*) FROM mainline.clause_embedding").fetchone()[0]
            )
        load_report = {"skipped": True, "rows_in_index": stored}
    else:
        load_report = load_documents(database, rows, embedder, workers=max(1, args.embed_workers))
    sys.stdout.write(f"load {json.dumps(load_report)}\n")

    # Warm the permit side of the cache in parallel before the harness runs. The harness
    # evaluates one permit at a time by design — results come back in corpus order so two
    # runs produce byte-identical reports — and 396 sequential Bedrock calls against a quota
    # this small is an hour of waiting for no measurement benefit. Warming changes nothing
    # about which vector each permit gets: the cache key is the request body.
    embed_all(
        [query_embed_text(query) for query in corpus.queries],
        embedder,
        workers=max(1, args.embed_workers),
        label="permits",
    )

    probe = CockroachAnnProbe(connect=lambda: crdb(database))
    backend = BedrockBackend(
        embedder=embedder,
        probe=probe,
        corpus_head_wall=corpus.split_policy.wall,
    )

    started = datetime.now(tz=UTC)
    run = run_evaluation_sync(backend, corpus, k=args.k, concurrency=1)
    bundle = compute_metrics(run, corpus)
    gates = evaluate_g4alpha(bundle)
    probe.close()
    cache.close()

    reachability = prefix_reachability(corpus, rows)
    uniqueness = text_uniqueness(corpus, rows)
    occupancy = routine_partition_occupancy(corpus, rows)
    ledger_rows = [token_ledger_entry(embedder.model_id, embedder.calls, embedder.input_tokens, 0)]
    env = dotenv()
    embedding_ledger = _portable_embedding_ledger(embedder, root)

    manifest: dict[str, Any] = {
        "run": {
            "started_at": started.isoformat(),
            "k": args.k,
            "backend_name": run.backend_name,
            "concurrency": 1,
            "wall_seconds": round(run.wall_seconds, 2),
        },
        "corpus": {
            "directory": corpus_dir.relative_to(root).as_posix(),
            "label": corpus.label(),
            "corpus_commit": corpus.split_policy.corpus_commit,
            "split_policy_id": corpus.split_policy_id,
            "split_wall": corpus.split_policy.wall.isoformat(),
            "synthetic": corpus.synthetic,
            "preliminary": corpus.preliminary,
            "seed": DEFAULT_SEED,
            "n_queries": len(corpus.queries),
            "n_documents": len(rows),
            **corpus.to_dict(),
        },
        "bedrock": {
            "embed_model_id": TITAN_EMBED_MODEL_ID,
            "region": REGION,
            "dimensions": EMBED_DIM,
            "embed_template": EMBED_TEMPLATE,
            "embed_template_sha256": EMBED_TEMPLATE_SHA256,
            **embedding_ledger,
        },
        "index": {
            "index_gen": DEFAULT_INDEX_GEN,
            "index_name": "ce_ann",
            "prefix_columns": ["site_id", "activity_root"],
            "opclass": "vector_cosine_ops",
            "ann_overfetch": ANN_OVERFETCH,
            "ann_limit_floor": DEFAULT_ANN_LIMIT_FLOOR,
            "hinted": True,
        },
        "database": {
            "database": database,
            "cluster": env.get("CRDB_CLUSTER", "mainline-dev"),
            "cluster_region": env.get("CRDB_REGION", "aws-ap-southeast-1"),
            "surface": surface_note["surface"],
            "surface_reason": surface_note["reason"],
            "stub_disclosure": (
                "mainline.clause_version here is a minimal stub carrying only the identity, "
                "the ANN prefix and the three timestamps the Retro-Recall wall is a predicate "
                "over. The production table carries append_only, z_delta_witness_required and "
                "clause_version_guard triggers that would refuse this bulk load, which is the "
                "gate working correctly rather than an obstacle to route around."
            ),
            **load_report,
        },
        "policy": backend.config(),
        "retrieval": {**backend.run_report(), "embedding": embedding_ledger},
        "prefix_reachability": reachability,
        "text_uniqueness": uniqueness,
        "routine_partition_occupancy": occupancy,
        "token_ledger": {"entries": ledger_rows, "total": ledger_total(ledger_rows)},
        "floors": load_floors(),
    }

    metrics_payload = {
        "verdict": overall_status(gates),
        "run": run.to_dict(),
        "corpus": corpus.to_dict(),
        "measurements": {k: v.to_dict() for k, v in sorted(bundle.measurements.items())},
        "gates": [
            {
                **gate.to_dict(),
                "observed": (
                    None
                    if gate.measurement is None
                    else {
                        "value": gate.measurement.value,
                        "lower": gate.measurement.lower,
                        "upper": gate.measurement.upper,
                        "n": gate.measurement.n,
                        "defined": gate.measurement.defined,
                        "interval_method": gate.measurement.interval_method,
                    }
                ),
                "attribution": gate_attribution(gate, bundle, occupancy),
            }
            for gate in gates
        ],
        "conservation": bundle.conservation.to_dict(),
        "bonded_fatalities": bundle.bonded.to_dict(),
        "rank_distribution": bundle.ranks.to_dict(),
        "notes": list(bundle.notes),
        "prefix_reachability": reachability,
        "text_uniqueness": uniqueness,
        "routine_partition_occupancy": occupancy,
        "channels_present": ["C"],
        "channels_absent": ["A", "B", "C_sweep", "D"],
    }

    caveats = [
        (
            "the corpus is SYNTHETIC: every record is generated by "
            "trappoint_recall.corpora.synthetic and no number here characterises real "
            "incident data"
        ),
        (
            "this is retrieval channel C only; channels A (deterministic ancestry), B "
            "(bonded severity-5) and D (lexical BM25) are not implemented, so gates "
            "requiring them cannot pass"
        ),
        (
            f"p_relevant is the declared unfitted map {CALIBRATION_ID}, so P@block, the "
            "nuisance rate and mean blocking checks per permit are conditional on it; the "
            "rank metrics are invariant to any monotone calibration and are not"
        ),
        (
            "mainline.clause_version on this surface is a minimal stub, not the production "
            "table with its append-only and delta-witness triggers"
        ),
        (
            "the retro permit narratives are synthesised from the investigations that name "
            "their own precursors, so a semantic match between a permit and its source "
            "document is partly paraphrase overlap and not only precursor prediction"
        ),
        (
            f"{uniqueness['documents']} documents render to "
            f"{uniqueness['distinct_document_texts']} distinct embedding texts, so many "
            "documents carry identical vectors and their order inside a result set is "
            "decided by the query's tie-break rather than by the model"
        ),
    ]

    metrics_path = artefact(
        EVIDENCE_DIR / "real-embeddings-metrics.json",
        metrics_payload,
        kind="recall-real-embeddings-metrics",
        caveats=caveats,
        synthetic=True,
    )
    manifest_path = artefact(
        EVIDENCE_DIR / "run-manifest.json",
        manifest,
        kind="recall-real-embeddings-manifest",
        caveats=caveats,
        synthetic=True,
    )

    report_path = root / EVIDENCE_DIR / "gate-report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        render_report(
            bundle=bundle,
            gates=gates,
            corpus=corpus,
            manifest=manifest,
            reachability=reachability,
        ),
        encoding="utf-8",
    )

    sys.stdout.write(f"wrote {metrics_path}\n{manifest_path}\n{report_path}\n")
    for gate in gates:
        sys.stdout.write(f"[{gate.status}] {gate.gate_id}\n")

    return _verify_no_bare_point_estimates(root, report_path)


if __name__ == "__main__":
    raise SystemExit(main())
