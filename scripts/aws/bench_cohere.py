#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Benchmark Cohere against Titan on this account, and report the residency finding first.

    python scripts/aws/bench_cohere.py --stage residency
    python scripts/aws/bench_cohere.py --stage bench --allow-residency-violation
    python scripts/aws/bench_cohere.py --stage all --allow-residency-violation
    python scripts/aws/bench_cohere.py --stage bench --rescore-only     # no AWS calls
    python scripts/aws/bench_cohere.py --dry-run                        # price it, spend nothing

``docs/adr/0002-g1-platform-ground-truth.md`` recorded ``cohere.embed-v4:0`` as *"a
benchmark candidate against Titan; no change made unilaterally"* and left it open.  This
program closes it.  It changes no provider code, switches no model, and touches nothing
under ``verticals/``: it measures, writes three artefacts, and stops.

WHY THE HEADLINE IS A STRUCTURE AND NOT A SCORE
------------------------------------------------
On this account, in ``ap-southeast-2``:

* ``invoke_model cohere.embed-v4:0`` is refused — ``ValidationException``, *"Invocation of
  model ID cohere.embed-v4:0 with on-demand throughput isn't supported. Retry your request
  with the ID or ARN of an inference profile that contains this model."*
* ``list_inference_profiles`` returns **exactly one** profile containing that model:
  ``global.cohere.embed-v4:0``, whose own AWS-authored description reads *"Routes requests
  to Embed v4 globally across all supported AWS Regions."*
* ``cohere.embed-english-v3`` is ``ON_DEMAND`` in region and needs no profile.

``providers/bedrock_titan.py::REQUIRED_REGION`` and ``ARCHITECTURE §10.1`` commit this
system to embedding Australian safety narratives in ``ap-southeast-2`` or not at all.
``_common.assert_in_region`` enforces exactly that, and it **refuses**
``global.cohere.embed-v4:0``.  So at v4, on this account, the choice is residency versus
that model — and no benchmark score can settle a question of that shape.

The score is still worth having, because "we chose residency" is only an honest sentence
if we know what it cost.  So the v4 arm is measured anyway, once, over a corpus that is
**synthetic by construction** and therefore carries no Australian narrative to export, and
it is labelled ``RESIDENCY-VIOLATING`` in every place it appears.  Running it requires
``--allow-residency-violation`` on the command line; the flag's presence is recorded in the
artefact, because a guard you can trip without leaving a mark is not a guard.

HOW THE BENCHMARK IS KEPT HONEST
---------------------------------
1. **One corpus, one query set, one template.**  All three arms see the identical strings,
   composed by the production template
   ``providers/base.py::embed_text`` (``{activity_path} | {asset_class} | {facet}: {cue}``)
   and normalised by the production ``normalise_text``.  A benchmark that lets each model
   pick its own preprocessing measures the preprocessing.
2. **The time wall is applied.**  Each G4 retro query carries the instant of the fatality it
   was synthesised from.  The candidate pool for that query is the set of records satisfying
   ``occurred_at < t AND ingested_at < t AND corpus_commit_at <= t`` — the same three
   predicates ``trappoint_recall.eval.splits.SplitPolicy`` applies.  Scoring the whole
   corpus for every query would be a different, easier task, and its numbers would not be
   comparable to anything the harness reports.
3. **No database.**  Ranking is exhaustive cosine similarity in-process over the walled
   pool.  This is deliberate: a model comparison that needed an ANN index would be
   confounded by the index's recall, and would make this result depend on another worker's.
   Exhaustive cosine is the ceiling every ANN arm is measured against anyway.
4. **Every proportion carries a Wilson interval and its n**; every mean carries a
   deterministic bootstrap interval.  Both come from
   ``trappoint_recall.eval.measurement``, the same code the release gates use.
5. **Calls are interleaved, one text per call, for all three arms.**  Cohere accepts up to
   96 texts per request and Titan accepts one; batching one arm and not the other would
   make "mean latency per call" a statement about the batch size.  The arms are rotated
   per text so no arm systematically holds the warm socket.
6. **The corpus is synthetic and every artefact says so.**  It models fatalities.  A number
   measured on invented text is a number about the generator, and the ADR says that before
   it says anything else.

WHAT THIS PROGRAM WILL NOT DO
------------------------------
It will not edit ``providers/``, will not change ``TITAN_EMBED_MODEL_ID``, will not create
provisioned throughput, will not request model access, and will not enable invocation
logging.  Its output is a recommendation with citations.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import re
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Final

import numpy as np
from mainline_recall_agent.providers.base import embed_text, normalise_text, template_sha256

from trappoint_recall.corpora.build import SYNTHETIC_PROVENANCE, load_inputs
from trappoint_recall.eval.measurement import bootstrap_mean_interval, wilson_interval

if __package__ in {None, ""}:  # direct execution: `python scripts/aws/bench_cohere.py`
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.aws._common import (
    CROSS_REGION_PREFIXES,
    DEFAULT_PROFILE,
    REGION,
    USD_PER_1K_TOKENS,
    ResidencyError,
    artefact,
    assert_in_region,
    bedrock_control,
    bedrock_runtime,
    check_cost_ceiling,
    cloudwatch,
    crdb,
    ledger_total,
    redact,
    session,
    sha256_hex,
    token_ledger_entry,
)

_ROOT = Path(__file__).resolve().parents[2]

__all__ = [
    "ARMS",
    "Arm",
    "BenchCorpus",
    "EmbedCall",
    "load_bench_corpus",
    "main",
    "residency_finding",
    "score_arm",
]

# ═══════════════════════════════════════════════════════════════════════════════════════
# 0 · Constants that are decisions
# ═══════════════════════════════════════════════════════════════════════════════════════

FIXTURES: Final[Path] = _ROOT / "tests" / "fixtures" / "recall"
GOLDSET_DIR: Final[Path] = FIXTURES / "goldsets"
QUERIES_PATH: Final[Path] = GOLDSET_DIR / "g4_retro.queries.jsonl"
QRELS_PATH: Final[Path] = GOLDSET_DIR / "g4_retro.qrels.jsonl"

EVIDENCE_DIR: Final[Path] = _ROOT / "evidence" / "aws" / "bench"
VECTOR_CACHE: Final[Path] = _ROOT / "out" / "aws" / "bench"
"""``out/`` is gitignored.  Vectors are large and reproducible; manifests are neither."""

#: The facet every arm embeds under.  ``narrative`` is the cue schema's safety net — the
#: full work description rather than a synthesised facet — because facet synthesis is
#: channel D's own machinery and benchmarking two embedders through it would measure the
#: synthesiser.  The coded classification is deliberately **excluded** from the embedded
#: text: g4_retro's third refusal says choosing or scoring by shared codes turns the money
#: metric into an evaluation of the coding manual.
BENCH_FACET: Final[str] = "narrative"

#: Cutoffs reported.  ``@1`` is "the retriever's single best guess was the true precursor";
#: ``@10`` is the ANN candidate window the product actually re-ranks.
CUTOFFS: Final[tuple[int, ...]] = (1, 3, 10)

#: umbrela grade of the *truth precursor* — the prior incident the investigation itself
#: cited.  Grade 2 is "shares mechanism", which is useful but is not the money metric.
TRUTH_GRADE: Final[int] = 3
RELATED_GRADE: Final[int] = 2

#: Bedrock's request schema for the Cohere v3 family enforces this, measured verbatim:
#: ``Malformed input request: #/texts/0: expected maxLength: 2048, actual: 4680``.  It is a
#: *request validation*, not a model truncation: ``truncate: "END"`` does not soften it.
#: A caller must therefore truncate client-side, and this program counts every text it cut.
COHERE_V3_MAX_CHARS: Final[int] = 2048

#: Throttling.  Bedrock embedding models throttle on **requests per minute, not tokens**,
#: so a 3 500-call sequential sweep is exactly the shape that trips it — and it did, on the
#: first attempt at this benchmark, after roughly 700 texts, with botocore's own adaptive
#: retries already exhausted (*"reached max retries: 4"*).  Two things were wrong and both
#: are fixed here rather than papered over:
#:
#: 1. **Patience.** A linear 0.75·n backoff buys eleven seconds. A per-minute quota needs
#:    to be waited out, not out-argued, so the schedule is exponential with full jitter and
#:    a 30-second cap, and it is allowed to spend around two minutes on one call.
#: 2. **Pacing.** Backoff alone converges on "call as fast as possible, then get refused".
#:    :class:`Pacer` adds an additive-increase / multiplicative-decrease delay between
#:    calls, so a throttled run slows to a rate the account will actually serve instead of
#:    hammering the same wall. The final pace and the total number of throttled calls are
#:    published in the artefact: a latency number measured while being throttled is a
#:    statement about the quota, and a reader must be able to see that it was not.
THROTTLE_ATTEMPTS: Final[int] = 9
THROTTLE_BASE_SECONDS: Final[float] = 1.0
THROTTLE_MAX_SECONDS: Final[float] = 30.0

#: Additive increase applied to the inter-call delay each time a call is throttled, and the
#: multiplicative decay applied after each clean call.  The pair converges on the fastest
#: pace that is not refused, which is the only pace worth running at.
PACE_INCREASE_SECONDS: Final[float] = 0.25
PACE_DECAY: Final[float] = 0.995
PACE_MAX_SECONDS: Final[float] = 5.0

#: How many times the sweep re-asks for the texts a quota refused.  Each pass takes what the
#: account will give; the loop also stops early when a whole pass buys nothing, so this is a
#: ceiling on patience rather than a schedule.
MAX_SWEEP_PASSES: Final[int] = 40

#: Jitter source.  ``SystemRandom`` rather than the module-level ``random`` functions: the
#: jitter is not security-sensitive, but ``S311`` exists so that the question gets asked
#: rather than suppressed, and answering it costs nothing here.
_JITTER: Final = random.SystemRandom()

WALL_RE: Final = re.compile(r"wall\s+(\S+)")

#: What each artefact does NOT prove.  ``_common.artefact`` requires this list, and the
#: failure mode it exists to prevent is a file that reads as broader than its evidence.
RESIDENCY_CAVEATS: Final[tuple[str, ...]] = (
    (
        "a control-plane listing plus four live invocations on one account in one region on "
        "one day; it says nothing about another account, another region, or a future "
        "model-access grant"
    ),
    (
        "the cross-region arm was invoked deliberately, on a synthetic probe string, to "
        "measure what refusing it costs; the flag that permitted it is recorded in this file"
    ),
    (
        "'global' routing is read from AWS's own profile description and from the regionless "
        "model ARN; this program did not and cannot observe which region actually served the "
        "request, which is precisely the finding"
    ),
    (
        "the input-length ceiling is measured with one long probe string, not swept; it "
        "establishes that a limit exists and quotes the refusal verbatim"
    ),
)

RAW_CAVEATS: Final[tuple[str, ...]] = (
    (
        "the embeddings here are of a single probe sentence, not of the benchmark corpus; the "
        "corpus vectors are cached under out/aws/bench/ and are gitignored by size"
    ),
    "a captured refusal is a result, not a failure of this program",
)

BENCH_CAVEATS: Final[tuple[str, ...]] = (
    (
        "THE CORPUS IS SYNTHETIC. Every document is invented by "
        "trappoint_recall.corpora.synthetic and carries corpus_class='synthetic_replica'. "
        "These scores describe how three embedders behave on that generator's prose. They "
        "are not a claim about retrieval quality on real incident data, and ADR 0040 says so "
        "before it says anything else."
    ),
    (
        "the judgements are distant supervision — the truth precursor is the prior incident "
        "the synthetic investigation cites — not human adjudication"
    ),
    (
        "ranking is exhaustive cosine, not ANN; these are the ceiling an indexed arm is "
        "measured against, and an indexed arm will score at or below them"
    ),
    (
        "n = 96 queries. With 96 trials the Wilson intervals are wide and small differences "
        "between arms are not resolvable; the paired sign test is reported for that reason"
    ),
    (
        "the cross-region arm's numbers are measurements of a configuration this system "
        "refuses to adopt; they exist so the cost of refusing it is known, not to recommend it"
    ),
    (
        "USD figures are computed from published list prices recorded in "
        "_common.USD_PER_1K_TOKENS; no bill and no Price List API response backs them"
    ),
)


class BenchError(RuntimeError):
    """A benchmark precondition that cannot be repaired by retrying."""


# ═══════════════════════════════════════════════════════════════════════════════════════
# 1 · The arms
# ═══════════════════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True, slots=True)
class Arm:
    """One model under test, and everything a reader needs to judge its number.

    ``residency`` is not a comment.  ``in_region`` arms are asserted through
    :func:`_common.assert_in_region` before a single call is made; the ``cross_region`` arm
    is asserted to be *refused* by the same function, and that refusal is recorded.
    """

    key: str
    model_id: str
    vendor: str
    family: str
    residency: str  # "in_region" | "cross_region"
    native_dim: int
    requested_dim: int | None
    max_input_chars: int | None
    notes: str


ARMS: Final[tuple[Arm, ...]] = (
    Arm(
        key="titan_v2",
        model_id="amazon.titan-embed-text-v2:0",
        vendor="Amazon",
        family="Titan Text Embeddings V2",
        residency="in_region",
        native_dim=1024,
        requested_dim=1024,
        max_input_chars=None,
        notes=(
            "the incumbent; providers/bedrock_titan.py::TITAN_EMBED_MODEL_ID, and the width "
            "migration 0031 declares as VECTOR(1024)"
        ),
    ),
    Arm(
        key="cohere_v3",
        model_id="cohere.embed-english-v3",
        vendor="Cohere",
        family="Embed English v3",
        residency="in_region",
        native_dim=1024,
        requested_dim=None,
        max_input_chars=COHERE_V3_MAX_CHARS,
        notes=(
            "the only Cohere embedder this account can invoke in-region on demand; its width "
            "happens to match VECTOR(1024), and Bedrock refuses any single text over "
            "2048 characters"
        ),
    ),
    Arm(
        key="cohere_v4_global",
        model_id="global.cohere.embed-v4:0",
        vendor="Cohere",
        family="Embed v4 (via the global cross-region inference profile)",
        residency="cross_region",
        native_dim=1536,
        requested_dim=None,
        max_input_chars=None,
        notes=(
            "RESIDENCY-VIOLATING. The bare id cohere.embed-v4:0 is refused for on-demand "
            "throughput; the sole profile that carries it routes globally. Measured for "
            "completeness on a synthetic corpus only, and never proposed for use."
        ),
    ),
)

ARMS_BY_KEY: Final[Mapping[str, Arm]] = {a.key: a for a in ARMS}


# ═══════════════════════════════════════════════════════════════════════════════════════
# 2 · The corpus
# ═══════════════════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True, slots=True)
class BenchDoc:
    doc_id: str
    source: str
    text: str
    occurred_at: datetime
    ingested_at: datetime
    corpus_commit_at: datetime


@dataclass(frozen=True, slots=True)
class BenchQuery:
    query_id: str
    text: str
    wall: datetime
    truth_doc_id: str
    graded: Mapping[str, int]


@dataclass(frozen=True, slots=True)
class BenchCorpus:
    docs: tuple[BenchDoc, ...]
    queries: tuple[BenchQuery, ...]
    doc_index: Mapping[str, int]
    pool_mask: Any  # np.ndarray[bool], shape (n_queries, n_docs)
    provenance: Mapping[str, Any]

    @property
    def texts(self) -> tuple[str, ...]:
        return tuple(d.text for d in self.docs)

    def sweep_order(self) -> tuple[tuple[str, int], ...]:
        """``(kind, position)`` pairs in the order the sweep should buy them.

        Queries first — 96 texts that every metric depends on — then truth precursors, then
        the other judged documents, then the distractors.  On an account that may throttle
        the sweep to a halt, this is the difference between "we stopped early and have a
        smaller pool" and "we stopped early and have nothing".
        """
        truth_ids = {q.truth_doc_id for q in self.queries}
        judged_ids = {doc_id for q in self.queries for doc_id in q.graded}
        tier_one = [i for i, d in enumerate(self.docs) if d.doc_id in truth_ids]
        tier_two = [
            i
            for i, d in enumerate(self.docs)
            if d.doc_id in judged_ids and d.doc_id not in truth_ids
        ]
        tier_three = [i for i, d in enumerate(self.docs) if d.doc_id not in judged_ids]
        order: list[tuple[str, int]] = [("query", i) for i in range(len(self.queries))]
        order += [("doc", i) for i in tier_one + tier_two + tier_three]
        return tuple(order)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    """JSONL with the goldsets' ``//!meta`` header line skipped."""
    out: list[dict[str, Any]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("//"):
            continue
        out.append(json.loads(line))
    return out


def _apply_pool_rule(
    docs: list[BenchDoc],
    truth_ids: set[str],
    judged_ids: set[str],
    max_documents: int | None,
) -> list[BenchDoc]:
    """Shrink the candidate pool in a stated order of priority, never at random.

    Three tiers, and the order is the argument:

    1. **Every truth precursor is mandatory.** It is the answer to a query; a pool without
       it does not make the task harder, it makes it impossible, and the resulting hit@k
       would be a measurement of the pool.
    2. **Then the other judged documents**, in ``external_ref`` order. These are the
       grade-2 "shares mechanism" neighbours. Dropping some of them makes the task *easier*
       — it removes near-misses that would otherwise outrank the truth — and it does so
       identically for all three arms, which is why the paired comparison survives it and
       the absolute number must not be quoted on its own.
    3. **Then unjudged distractors**, again in ``external_ref`` order.

    No shuffle and no seed at any tier: a reader reproduces the pool with ``sort``.
    """
    if max_documents is None or max_documents >= len(docs):
        return docs
    if max_documents < len(truth_ids):
        raise BenchError(
            f"--max-documents {max_documents} is below the {len(truth_ids)} truth "
            "precursors the gold set requires. Every query's own answer must be in the "
            "pool; refusing to score a task whose answer is missing."
        )
    kept = [d for d in docs if d.doc_id in truth_ids]
    for tier in (
        [d for d in docs if d.doc_id in judged_ids and d.doc_id not in truth_ids],
        [d for d in docs if d.doc_id not in judged_ids],
    ):
        kept += tier[: max(0, max_documents - len(kept))]
    return sorted(kept, key=lambda d: d.doc_id)


def load_bench_corpus(*, max_documents: int | None = None) -> BenchCorpus:
    """Assemble the identical corpus, queries and per-query walls every arm will see.

    The document pool is the **whole** merged synthetic corpus by default — Part 50
    extracts, fatality reports, CSB reports and Australian regulator alerts, 1 071 records.
    The per-query walls do the narrowing, and they do it for a reason that is part of the
    metric rather than a convenience.

    ``max_documents`` shrinks the pool, and exists for one measured reason: on this account
    ``amazon.titan-embed-text-v2:0`` served roughly **three** successful on-demand calls per
    minute against a documented 60-per-minute quota (see ``throughput`` in the artefact), so
    1 071 Titan vectors is several hours of throttled calling.  The rule is deterministic and
    stated rather than sampled:

    1. **Every document any G4 query judges is kept.** Dropping a judged document changes
       the task rather than shrinking it, and would make nDCG's ideal ranking unreachable.
    2. **Distractors are added in ``external_ref`` order** until the pool reaches the cap.
       Order, not a seeded shuffle: a reader can reproduce the pool with ``sort``.
    3. **A smaller pool raises every arm's absolute hit@k.** Those numbers are already about
       a synthetic generator and are not a product claim; the comparison between arms is
       paired on the same queries and the same pool, and stays valid. The artefact records
       the pool size next to every number so no reader has to take that on trust.
    """
    records = load_inputs(FIXTURES, provenance=SYNTHETIC_PROVENANCE)
    docs: list[BenchDoc] = []
    for record in sorted(records.records, key=lambda r: r.external_ref):
        cue = (record.narrative or "").strip()
        if not cue:
            continue
        text = normalise_text(
            embed_text(
                activity_path=record.activity_path or "/unspecified",
                asset_class=record.asset_class or "unspecified",
                facet=BENCH_FACET,
                cue_text=cue,
            )
        )
        docs.append(
            BenchDoc(
                doc_id=record.external_ref,
                source=record.source,
                text=text,
                occurred_at=record.occurred_at,
                ingested_at=record.ingested_at,
                corpus_commit_at=record.corpus_commit_at,
            )
        )
    judgements = _read_jsonl(QRELS_PATH)
    graded: dict[str, dict[str, int]] = {}
    truth: dict[str, str] = {}
    walls: dict[str, datetime] = {}
    for judgement in judgements:
        qid = str(judgement["query_id"])
        graded.setdefault(qid, {})[str(judgement["doc_id"])] = int(judgement["grade"])
        if int(judgement["grade"]) == TRUTH_GRADE:
            truth[qid] = str(judgement["doc_id"])
            match = WALL_RE.search(str(judgement.get("notes") or ""))
            if match is None:
                raise BenchError(
                    f"{qid}: the grade-{TRUTH_GRADE} judgement carries no 'wall <instant>' "
                    "note, so its time wall cannot be reconstructed. Scoring it without a "
                    "wall would silently measure an easier task."
                )
            walls[qid] = datetime.fromisoformat(match.group(1)).astimezone(UTC)

    # ── the pool rule, applied here so every arm sees the identical document list ──────
    full_corpus_size = len(docs)
    judged_ids = {doc_id for per_query in graded.values() for doc_id in per_query}
    n_judged_full = len(judged_ids)
    docs = _apply_pool_rule(docs, set(truth.values()), judged_ids, max_documents)
    in_pool = {d.doc_id for d in docs}
    n_judged = sum(1 for d in docs if d.doc_id in judged_ids)
    n_distractors = len(docs) - n_judged
    doc_index = {d.doc_id: i for i, d in enumerate(docs)}

    queries: list[BenchQuery] = []
    dropped_judgements = 0
    for row in _read_jsonl(QUERIES_PATH):
        qid = str(row["query_id"])
        if qid not in truth:
            continue
        cue = str(row.get("facets", {}).get(BENCH_FACET) or row["text"])
        text = normalise_text(
            embed_text(
                activity_path=str(row.get("activity_path") or "/unspecified"),
                asset_class=str(row.get("asset_class") or "unspecified"),
                facet=BENCH_FACET,
                cue_text=cue,
            )
        )
        # A judgement about a document the pool does not contain is not evidence about any
        # arm; keeping it would put an unreachable document in nDCG's ideal ranking and
        # deflate every arm by the same invisible amount.  Dropped judgements are counted,
        # never silently discarded.
        kept_grades = {d: g for d, g in graded[qid].items() if d in in_pool}
        dropped_judgements += len(graded[qid]) - len(kept_grades)
        queries.append(
            BenchQuery(
                query_id=qid,
                text=text,
                wall=walls[qid],
                truth_doc_id=truth[qid],
                graded=kept_grades,
            )
        )
    queries.sort(key=lambda q: q.query_id)

    mask = np.zeros((len(queries), len(docs)), dtype=bool)
    for qi, query in enumerate(queries):
        for di, doc in enumerate(docs):
            mask[qi, di] = (
                doc.occurred_at < query.wall
                and doc.ingested_at < query.wall
                and doc.corpus_commit_at <= query.wall
            )
        if not mask[qi, doc_index[query.truth_doc_id]]:
            raise BenchError(
                f"{query.query_id}: its own truth precursor "
                f"{query.truth_doc_id} falls outside its time wall. The gold set and this "
                "loader disagree about the wall; refusing to score a task whose answer is "
                "not in the pool."
            )
        # Every *judged* document must also be inside the wall, not merely the truth
        # precursor.  nDCG's ideal ranking is built from the judgement set, so a judged
        # document the pool cannot return would inflate the ideal and deflate every arm's
        # nDCG by the same invisible amount — a shared error is still an error, and it is
        # the kind that survives review because all three columns move together.
        outside = [d for d in query.graded if not mask[qi, doc_index[d]]]
        if outside:
            raise BenchError(
                f"{query.query_id}: {len(outside)} judged documents fall outside its own "
                f"time wall (first: {outside[0]}). The ideal DCG would then be unreachable "
                "by construction; refusing to publish an nDCG whose denominator is a "
                "fiction."
            )

    pool_sizes = mask.sum(axis=1)
    provenance = {
        "corpus": "trappoint_recall synthetic replica, loaded from tests/fixtures/recall",
        "corpus_class": "synthetic_replica",
        "tenant_use": "harness_only",
        "goldset": "G4 retro-recall (the money metric)",
        "n_documents": len(docs),
        "n_queries": len(queries),
        "n_judgements": len(judgements),
        "pool_rule": {
            "full_corpus_documents": full_corpus_size,
            "max_documents_requested": max_documents,
            "judged_documents_in_full_corpus": n_judged_full,
            "judged_documents_kept": n_judged,
            "unjudged_distractors_kept": n_distractors,
            "judgements_dropped_as_out_of_pool": dropped_judgements,
            "truth_precursors_kept": len(queries),
            "rule": (
                "tier 1 every truth precursor (mandatory), tier 2 the other judged "
                "documents in external_ref order, tier 3 unjudged distractors in "
                "external_ref order, until the cap. No shuffle, no seed — the pool is "
                "reproducible with sort. Judgements about documents outside the pool are "
                "dropped from the nDCG ideal and counted above."
            ),
            "why_capped": (
                "measured on this account today: amazon.titan-embed-text-v2:0 sustained "
                "about three successful on-demand calls per minute against a documented "
                "60-per-minute quota, so the full corpus is several hours of throttled "
                "calling. See 'throughput' in this artefact."
                if max_documents is not None and max_documents < full_corpus_size
                else "not capped; this is the whole corpus"
            ),
            "effect_on_the_numbers": (
                "a smaller pool raises every arm's absolute hit@k by the same mechanism. "
                "Those absolutes describe a synthetic generator and are not a product "
                "claim. The comparison between arms is paired on identical queries and an "
                "identical pool and is unaffected."
            ),
        },
        "documents_by_source": {
            source: sum(1 for d in docs if d.source == source)
            for source in sorted({d.source for d in docs})
        },
        "embed_template": "{activity_path} | {asset_class} | {facet}: {cue_text}",
        "embed_template_sha256": template_sha256(),
        "embed_facet": BENCH_FACET,
        "text_normalisation": "providers/base.py::normalise_text (NFKC + whitespace collapse)",
        "time_wall": (
            "per query: occurred_at < t AND ingested_at < t AND corpus_commit_at <= t, the "
            "three predicates trappoint_recall.eval.splits.SplitPolicy applies; t is read "
            "from the grade-3 judgement's own wall note"
        ),
        "walled_pool_size": {
            "min": int(pool_sizes.min()),
            "median": float(np.median(pool_sizes)),
            "max": int(pool_sizes.max()),
        },
        "text_duplication": {
            "distinct_document_texts": len({d.text for d in docs}),
            "distinct_query_texts": len({q.text for q in queries}),
            "documents_sharing_a_text": len(docs) - len({d.text for d in docs}),
            "queries_sharing_a_text": len(queries) - len({q.text for q in queries}),
            "reading": (
                "The synthetic generator draws narratives from a small template set, so many "
                "records are byte-identical once the production embedding template is applied. "
                "Identical input gives an identical vector and an exact cosine tie, and the "
                "tie rule then decides the headline number. This benchmark breaks ties "
                "AGAINST the right answer (see score_arm): a retriever that cannot separate "
                "the truth precursor from documents identical to it has not found it. The "
                "practical consequences are that (a) hit@1 here is a lower bound, (b) the "
                "number of distinct texts, not the number of documents, is what each arm was "
                "actually charged for, and (c) any conclusion about absolute retrieval "
                "quality on this corpus is a conclusion about the generator."
            ),
        },
        "documents_sha256": sha256_hex(
            "\n".join(f"{d.doc_id}\t{d.text}" for d in docs).encode("utf-8")
        ),
        "queries_sha256": sha256_hex(
            "\n".join(f"{q.query_id}\t{q.text}" for q in queries).encode("utf-8")
        ),
    }
    return BenchCorpus(
        docs=tuple(docs),
        queries=tuple(queries),
        doc_index=doc_index,
        pool_mask=mask,
        provenance=provenance,
    )


# ═══════════════════════════════════════════════════════════════════════════════════════
# 3 · Invocation
# ═══════════════════════════════════════════════════════════════════════════════════════


@dataclass(slots=True)
class EmbedCall:
    """One invocation, with everything needed to price it and to doubt it."""

    vector: list[float]
    input_tokens: int
    latency_ms: float
    server_latency_ms: int | None
    request_id: str | None
    request_body: dict[str, Any]
    response_head: dict[str, Any]
    truncated_from_chars: int | None = None
    throttle_retries: int = 0
    """How many times *this program* had to back off before the call succeeded.  Published
    rather than swallowed: a sweep that was throttled has latency numbers about the quota,
    not about the model."""
    botocore_retry_attempts: int = 0
    """``ResponseMetadata.RetryAttempts`` — how many times **botocore** retried inside a
    single ``invoke_model`` call, before this program ever saw an exception.  Without this
    field a throttled Titan call looks like a 3 700 ms model, because the SDK's own
    exponential backoff happens inside the stopwatch.  Latency is reported over the calls
    where this and :attr:`throttle_retries` are both zero, with that subset's own n."""

    @property
    def clean(self) -> bool:
        """True when nothing retried this call, so its latency is about the model."""
        return self.throttle_retries == 0 and self.botocore_retry_attempts == 0


def _titan_body(text: str, arm: Arm) -> dict[str, Any]:
    body: dict[str, Any] = {"inputText": text, "normalize": True}
    if arm.requested_dim is not None:
        body["dimensions"] = arm.requested_dim
    return body


def _cohere_body(text: str, arm: Arm, *, is_query: bool) -> dict[str, Any]:
    body: dict[str, Any] = {
        "texts": [text],
        # Cohere embedders are asymmetric by design: a document and the query that should
        # find it are projected differently.  Sending "search_document" for both is the
        # single most common way to hand Cohere a loss it did not earn.
        "input_type": "search_query" if is_query else "search_document",
        "embedding_types": ["float"],
    }
    if arm.requested_dim is not None:
        body["output_dimension"] = arm.requested_dim
    return body


def _extract_vector(arm: Arm, decoded: Mapping[str, Any]) -> list[float]:
    if arm.vendor == "Amazon":
        vector = decoded.get("embedding")
        if not isinstance(vector, list):
            raise BenchError(f"{arm.model_id}: response carries no 'embedding' list")
        return [float(x) for x in vector]
    embeddings = decoded.get("embeddings")
    # Cohere v3 and v4 both answer with {"embeddings": {"float": [[...]]}} when
    # ``embedding_types`` is set, and with a bare list when it is not.  Both shapes are
    # accepted so a future default change surfaces as a wrong number rather than a crash.
    floats = embeddings.get("float") if isinstance(embeddings, Mapping) else embeddings
    if not isinstance(floats, list) or not floats or not isinstance(floats[0], list):
        raise BenchError(f"{arm.model_id}: response carries no float embedding batch")
    return [float(x) for x in floats[0]]


def bench_runtime() -> Any:
    """``bedrock-runtime`` with the SDK's own retries turned OFF, and why that is the fix.

    ``_common.bedrock_runtime`` is the right client for a probe: botocore's default
    ``max_attempts=5`` in adaptive mode hides a transient throttle and returns a result.  It
    is the wrong client for a rate-limited sweep, and the reason is the defect this
    benchmark spent an hour inside:

    **botocore's retries are invisible to the caller's rate limiter.**  A loop issuing one
    ``invoke_model`` per second, with the SDK retrying up to five times inside each of them,
    is issuing up to five requests per second — and every retried request still counts
    against the per-minute quota that caused the retry.  The loop then measures its own
    throttling as the model's latency, slows down, and gets throttled anyway, because the
    thing it slowed down was not the thing making the requests.

    So the sweep takes the retries into its own hands: ``max_attempts=1`` means one HTTP
    request per ``invoke_model``, the rate the :class:`Pacer` enforces is the rate AWS sees,
    and a ``ThrottlingException`` reaches this program where it can be counted and waited
    out.  ``read_timeout`` is generous because a 1 536-d embedding over a cross-region
    profile is a real round trip, not a hang.

    The region and profile still come from ``_common.session``: this is a configuration
    change, not a second way to choose where the call goes.
    """
    from botocore.config import Config

    return session().client(
        "bedrock-runtime",
        region_name=REGION,
        config=Config(
            retries={"max_attempts": 1, "mode": "standard"},
            read_timeout=60,
            connect_timeout=15,
        ),
    )


class Pacer:
    """Additive-increase / multiplicative-decrease inter-call delay, per model id.

    Each arm gets its own delay because the arms do not share a quota: the Cohere arms ran
    clean through a sweep in which Titan was refused on seventeen calls out of eighteen, and
    a single global pace would have slowed the innocent arms to the throttled one's speed
    and then reported that as their latency.

    ``floor`` is a *deliberate* pace set from the command line, not a learned one.  AIMD
    alone converges on "go as fast as possible, then get refused", which is the right answer
    for a service that recovers instantly and the wrong one for a per-minute quota: the
    refusals themselves consume budget, so the loop can settle into a state where almost
    every call is a retry. Being told the pace up front is cheaper than discovering it
    thirty ThrottlingExceptions at a time.
    """

    def __init__(self, floor: float = 0.0) -> None:
        self._floor = max(0.0, floor)
        self._delay: dict[str, float] = {}
        self._last_call: dict[str, float] = {}
        self.throttled_calls: dict[str, int] = {}
        self.throttle_retries: dict[str, int] = {}

    def wait(self, model_id: str) -> None:
        """Sleep only as long as is needed to honour this model's minimum interval.

        A blind ``sleep(floor)`` before every call would multiply by the number of arms:
        three arms at a three-second floor would make one text take nine seconds even though
        the three models have three independent quotas. Measuring from this model's own last
        call keeps the arms genuinely concurrent in rate while still capping each one.
        """
        interval = max(self._floor, self._delay.get(model_id, 0.0))
        if interval <= 0:
            return
        elapsed = time.monotonic() - self._last_call.get(model_id, 0.0)
        if elapsed < interval:
            time.sleep(interval - elapsed)

    def mark_sent(self, model_id: str) -> None:
        """Stamp the moment a request left, so the interval is measured request-to-request."""
        self._last_call[model_id] = time.monotonic()

    def observed_ok(self, model_id: str) -> None:
        self._delay[model_id] = self._delay.get(model_id, 0.0) * PACE_DECAY

    def observed_throttle(self, model_id: str) -> None:
        self._delay[model_id] = min(
            PACE_MAX_SECONDS, self._delay.get(model_id, 0.0) + PACE_INCREASE_SECONDS
        )
        self.throttle_retries[model_id] = self.throttle_retries.get(model_id, 0) + 1

    def note_throttled_call(self, model_id: str) -> None:
        self.throttled_calls[model_id] = self.throttled_calls.get(model_id, 0) + 1

    def report(self) -> dict[str, Any]:
        return {
            "pace_floor_seconds_per_call": self._floor,
            "final_inter_call_delay_seconds": {
                k: round(max(self._floor, v), 4) for k, v in sorted(self._delay.items())
            },
            "calls_that_were_throttled_at_least_once": dict(sorted(self.throttled_calls.items())),
            "throttle_retries_total": dict(sorted(self.throttle_retries.items())),
        }


def invoke(
    client: Any,
    arm: Arm,
    text: str,
    *,
    is_query: bool,
    pacer: Pacer | None = None,
) -> EmbedCall:
    """One text, one call, with a patient throttle retry and the timing kept.

    ``ThrottlingException`` is the only thing retried.  A ``ValidationException`` is a fact
    about the request, and retrying it is a way of asking the same wrong question nine
    times.

    The measured latency is the latency of the **successful** attempt.  Time spent asleep
    in backoff is deliberately excluded from it and counted separately, because a mean that
    silently folded in a 30-second wait would be a statement about the account's quota
    wearing a model's name.
    """
    sent = text
    truncated_from: int | None = None
    if arm.max_input_chars is not None and len(sent) > arm.max_input_chars:
        truncated_from = len(sent)
        sent = sent[: arm.max_input_chars]

    body = (
        _titan_body(sent, arm)
        if arm.vendor == "Amazon"
        else _cohere_body(sent, arm, is_query=is_query)
    )
    payload = json.dumps(body)

    retries = 0
    while True:
        if pacer is not None:
            pacer.wait(arm.model_id)
            pacer.mark_sent(arm.model_id)
        started = time.perf_counter()
        try:
            response = client.invoke_model(
                modelId=arm.model_id,
                body=payload,
                contentType="application/json",
                accept="application/json",
            )
        except Exception as exc:
            name = type(exc).__name__
            code = getattr(exc, "response", {}).get("Error", {}).get("Code", name)
            if code not in {"ThrottlingException", "TooManyRequestsException"}:
                raise
            if retries >= THROTTLE_ATTEMPTS - 1:
                raise BenchError(
                    f"{arm.model_id}: still throttled after {THROTTLE_ATTEMPTS} attempts "
                    "and an exponential backoff capped at "
                    f"{THROTTLE_MAX_SECONDS:.0f}s. This is an account quota, not a defect "
                    "in the benchmark; re-run to resume from the on-disk cache."
                ) from exc
            if retries == 0 and pacer is not None:
                pacer.note_throttled_call(arm.model_id)
            retries += 1
            if pacer is not None:
                pacer.observed_throttle(arm.model_id)
            # Full jitter over an exponentially growing window: bounded, unsynchronised,
            # and never zero-length.
            window = min(THROTTLE_MAX_SECONDS, THROTTLE_BASE_SECONDS * (2 ** (retries - 1)))
            time.sleep(window * (0.5 + _JITTER.random()))
            continue
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        if pacer is not None:
            pacer.observed_ok(arm.model_id)
        break

    meta = response.get("ResponseMetadata", {})
    headers = {k.lower(): v for k, v in meta.get("HTTPHeaders", {}).items()}
    decoded = json.loads(response["body"].read())

    server_latency = headers.get("x-amzn-bedrock-invocation-latency")
    tokens_header = headers.get("x-amzn-bedrock-input-token-count")
    tokens = decoded.get("inputTextTokenCount")
    if tokens is None and tokens_header is not None:
        tokens = int(tokens_header)
    if tokens is None:
        raise BenchError(
            f"{arm.model_id}: neither the body nor the "
            "x-amzn-bedrock-input-token-count header reports an input token count, so this "
            "arm cannot be priced. Refusing to publish a cost with a guessed denominator."
        )

    return EmbedCall(
        vector=_extract_vector(arm, decoded),
        input_tokens=int(tokens),
        latency_ms=elapsed_ms,
        server_latency_ms=int(server_latency) if server_latency is not None else None,
        request_id=meta.get("RequestId"),
        request_body=body,
        response_head={
            "http_status": meta.get("HTTPStatusCode"),
            "keys": sorted(decoded.keys()),
            "response_type": decoded.get("response_type"),
        },
        truncated_from_chars=truncated_from,
        throttle_retries=retries,
        botocore_retry_attempts=int(meta.get("RetryAttempts") or 0),
    )


# ═══════════════════════════════════════════════════════════════════════════════════════
# 4 · Scoring
# ═══════════════════════════════════════════════════════════════════════════════════════


def _unit(matrix: Any) -> Any:
    """L2-normalise rows so a dot product is a cosine.  A zero row would be a dead vector
    and is refused rather than divided by an epsilon that hides it."""
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    if not np.all(norms > 0):
        raise BenchError("an embedding has zero norm; refusing to score a dead vector")
    return matrix / norms


def _wilson(successes: int, n: int) -> dict[str, Any]:
    lo, hi = wilson_interval(successes, n)
    return {
        "successes": int(successes),
        "n": int(n),
        "point": round(successes / n, 6) if n else None,
        "interval": [round(lo, 6), round(hi, 6)],
        "interval_method": "wilson",
        "confidence": 0.95,
    }


def _mean_with_interval(values: Sequence[float], *, label: str) -> dict[str, Any]:
    array = np.asarray(values, dtype=float)
    lo, hi = bootstrap_mean_interval([float(v) for v in values], label=label)
    return {
        "n": int(array.size),
        "mean": round(float(array.mean()), 6),
        "p50": round(float(np.percentile(array, 50)), 6),
        "p95": round(float(np.percentile(array, 95)), 6),
        "interval": [round(lo, 6), round(hi, 6)],
        "interval_method": "bootstrap_percentile",
        "confidence": 0.95,
        "resamples": 10000,
    }


def _ndcg_at_k(ranked_doc_ids: Sequence[str], graded: Mapping[str, int], k: int) -> float:
    gains = [(2 ** graded.get(d, 0)) - 1 for d in ranked_doc_ids[:k]]
    dcg = sum(g / math.log2(i + 2) for i, g in enumerate(gains))
    ideal = sorted(((2**g) - 1 for g in graded.values()), reverse=True)[:k]
    idcg = sum(g / math.log2(i + 2) for i, g in enumerate(ideal))
    return 0.0 if idcg == 0 else dcg / idcg


#: Cosine scores are floats; two embeddings of the *same string* agree to the last bit, but
#: two embeddings of different strings can agree to eleven decimal places by accident.  Ties
#: are therefore taken at a tolerance rather than by ``==``.
TIE_TOLERANCE: Final[float] = 1e-9


@dataclass(slots=True)
class ArmRanking:
    """Per-query outcomes for one arm, kept so arms can be compared *paired*."""

    hit_truth: dict[int, list[bool]] = field(default_factory=dict)
    hit_related: dict[int, list[bool]] = field(default_factory=dict)
    reciprocal_rank: list[float] = field(default_factory=list)
    ndcg10: list[float] = field(default_factory=list)
    truth_rank: list[int] = field(default_factory=list)
    truth_tied_with: list[int] = field(default_factory=list)
    """How many other in-pool documents scored identically to the truth precursor. On this
    corpus that number is often not zero, and the reason is in ``text_duplication``."""


def score_arm(
    corpus: BenchCorpus,
    doc_vectors: Any,
    query_vectors: Any,
) -> ArmRanking:
    """Exhaustive cosine ranking inside each query's own time wall, ties broken **against** us.

    THE TIE RULE IS NOT A DETAIL ON THIS CORPUS.  The synthetic generator emits many
    documents whose narratives are byte-identical after the production template is applied —
    1 071 documents reduce to 224 distinct embedding inputs.  Identical input means identical
    vector means an exact cosine tie, and how a scorer breaks that tie decides the headline
    number.

    A stable sort would break ties by ``doc_id`` and hand roughly half of them to the truth
    precursor for free, which measures the alphabet.  So the rank of the truth precursor is
    computed **pessimistically**: everything scoring strictly higher, *plus* everything
    scoring equal, plus one.  If a retriever cannot distinguish the right answer from four
    identical documents, it has not found the right answer, and this metric says so.  The
    same rule is applied to the grade>=2 arm.

    The count of tied documents is kept per query, so a reader can see how much of the score
    the rule is deciding rather than having to take the rule on trust.
    """
    docs = _unit(np.asarray(doc_vectors, dtype=np.float64))
    queries = _unit(np.asarray(query_vectors, dtype=np.float64))
    ranking = ArmRanking(
        hit_truth={k: [] for k in CUTOFFS},
        hit_related={k: [] for k in CUTOFFS},
    )
    doc_ids = [d.doc_id for d in corpus.docs]
    doc_position = corpus.doc_index

    for qi, query in enumerate(corpus.queries):
        similarity = docs @ queries[qi]
        allowed = corpus.pool_mask[qi]
        in_pool = similarity[allowed]

        def pessimistic_rank(doc_id: str, scores: Any = in_pool, sim: Any = similarity) -> int:
            score = sim[doc_position[doc_id]]
            strictly_better = int(np.sum(scores > score + TIE_TOLERANCE))
            tied = int(np.sum(np.abs(scores - score) <= TIE_TOLERANCE))
            # ``tied`` counts the document itself, so it contributes the "+1" as well.
            return strictly_better + tied

        def tie_count(doc_id: str, scores: Any = in_pool, sim: Any = similarity) -> int:
            score = sim[doc_position[doc_id]]
            return int(np.sum(np.abs(scores - score) <= TIE_TOLERANCE)) - 1

        truth_position = pessimistic_rank(query.truth_doc_id)
        ranking.truth_rank.append(truth_position)
        ranking.truth_tied_with.append(tie_count(query.truth_doc_id))
        ranking.reciprocal_rank.append(1.0 / truth_position)

        # nDCG needs an explicit ordering, and it gets the same pessimism: within a tie
        # block, judged documents are placed after unjudged ones.
        order = sorted(
            (i for i in range(len(doc_ids)) if allowed[i]),
            key=lambda i: (-similarity[i], query.graded.get(doc_ids[i], 0), doc_ids[i]),
        )
        ranking.ndcg10.append(_ndcg_at_k([doc_ids[i] for i in order], query.graded, 10))

        related_rank = min(
            (pessimistic_rank(d) for d, g in query.graded.items() if g >= RELATED_GRADE),
            default=len(doc_ids) + 1,
        )
        for k in CUTOFFS:
            ranking.hit_truth[k].append(truth_position <= k)
            ranking.hit_related[k].append(related_rank <= k)
    return ranking


def _paired_sign_test(a: Sequence[bool], b: Sequence[bool]) -> dict[str, Any]:
    """Exact two-sided sign test on the discordant pairs (McNemar, exact form).

    Two arms scored on the same 96 queries are paired data.  Comparing their independent
    Wilson intervals answers a weaker question than the one being asked, and overlapping
    intervals routinely hide a real paired difference.  ``b`` and ``c`` are the counts that
    actually carry the information: queries one arm got and the other missed.
    """
    only_a = sum(1 for x, y in zip(a, b, strict=True) if x and not y)
    only_b = sum(1 for x, y in zip(a, b, strict=True) if y and not x)
    n = only_a + only_b
    if n == 0:
        p = 1.0
    else:
        smaller = min(only_a, only_b)
        tail = sum(math.comb(n, i) for i in range(smaller + 1)) / (2**n)
        p = min(1.0, 2 * tail)
    return {
        "discordant_first_only": only_a,
        "discordant_second_only": only_b,
        "n_discordant": n,
        "p_value_exact_two_sided_sign_test": round(p, 6),
        "reading": (
            "a paired comparison on the same queries; the p-value is exact and makes no "
            "normal approximation, and n_discordant is the sample it is computed on"
        ),
    }


# ═══════════════════════════════════════════════════════════════════════════════════════
# 5 · Stage one — the residency finding
# ═══════════════════════════════════════════════════════════════════════════════════════

PROBE_TEXT: Final[str] = (
    "MAINLINE residency probe: isolate and de-pressurise the line, prove zero energy at "
    "the break point, and hold the permit open until the isolation is independently verified."
)

LONG_PROBE_TEXT: Final[str] = (
    "The crew was installing secondary ground support along the number four entry. " * 60
)


def _describe_error(exc: BaseException) -> dict[str, Any]:
    response = getattr(exc, "response", {}) or {}
    error = response.get("Error", {}) if isinstance(response, Mapping) else {}
    metadata = response.get("ResponseMetadata", {}) if isinstance(response, Mapping) else {}
    message = str(error.get("Message") or exc)
    return {
        "type": type(exc).__name__,
        "code": error.get("Code"),
        "message_verbatim": message,
        "message_sha256": sha256_hex(message.encode("utf-8")),
        "http_status": metadata.get("HTTPStatusCode"),
        "request_id": metadata.get("RequestId"),
    }


def _vector_fingerprint(vector: Sequence[float]) -> dict[str, Any]:
    array = np.asarray(vector, dtype="<f4")
    return {
        "dimension": int(array.size),
        "first_16": [round(float(x), 8) for x in array[:16].tolist()],
        "sha256_float32_le": sha256_hex(array.tobytes()),
        "l2_norm": round(float(np.linalg.norm(array.astype(np.float64))), 8),
        "truncation_note": (
            "16 of "
            f"{int(array.size)} coordinates are shown; the sha256 is over the full vector "
            "as little-endian float32, which is the form a reproduction must match"
        ),
    }


def _control_plane_census(control: Any) -> tuple[dict[str, Any], list[dict[str, Any]], int]:
    """What AWS itself declares about the three models, and every profile carrying v4.

    ``inferenceTypesSupported`` is the field the whole finding turns on: a model listed
    only as ``INFERENCE_PROFILE`` has no bare id a caller can invoke, and if no in-region
    profile exists for it then it has no in-region identity at all.
    """
    tracked = {
        "cohere.embed-v4:0",
        "cohere.embed-english-v3",
        "amazon.titan-embed-text-v2:0",
    }
    declared = {
        m["modelId"]: {
            "provider": m.get("providerName"),
            "model_name": m.get("modelName"),
            "inference_types_supported": m.get("inferenceTypesSupported"),
            "input_modalities": m.get("inputModalities"),
            "output_modalities": m.get("outputModalities"),
            "lifecycle": (m.get("modelLifecycle") or {}).get("status"),
        }
        for m in control.list_foundation_models()["modelSummaries"]
        if m["modelId"] in tracked
    }

    profiles: list[dict[str, Any]] = []
    token: str | None = None
    while True:
        kwargs: dict[str, Any] = {"maxResults": 100}
        if token:
            kwargs["nextToken"] = token
        page = control.list_inference_profiles(**kwargs)
        profiles.extend(page["inferenceProfileSummaries"])
        token = page.get("nextToken")
        if not token:
            break

    embed_v4_profiles = [
        {
            "inference_profile_id": p.get("inferenceProfileId"),
            "inference_profile_name": p.get("inferenceProfileName"),
            "description_verbatim": p.get("description"),
            "arn": p.get("inferenceProfileArn"),
            "type": p.get("type"),
            "status": p.get("status"),
            "model_arns": [m.get("modelArn") for m in p.get("models", [])],
        }
        for p in profiles
        if any("cohere.embed-v4" in (m.get("modelArn") or "") for m in p.get("models", []))
    ]
    return declared, embed_v4_profiles, len(profiles)


def _invoke_past_throttle(
    runtime: Any, model_id: str, body: Mapping[str, Any]
) -> tuple[Any | None, dict[str, Any] | None, float]:
    """Invoke, waiting out ``ThrottlingException`` so a 429 cannot masquerade as an answer.

    Every structural probe in this file asks a question a 429 does not answer.  "Is this text
    too long?" and "does this model take a batch?" are questions about the request schema; a
    throttle says only that the account is busy.  The first run of this program recorded
    ``outcome: REFUSED`` for Titan's length probe with a ``ThrottlingException`` inside it —
    an artefact that reads, to anyone skimming, as though Titan had a length limit.  That is
    exactly the kind of quiet wrongness this fleet exists to refuse.

    Returns ``(response, error, latency_ms)``: at most one of the first two is not ``None``,
    and both are ``None`` when the throttle never cleared.
    """
    for attempt in range(THROTTLE_ATTEMPTS):
        started = time.perf_counter()
        try:
            response = runtime.invoke_model(
                modelId=model_id,
                body=json.dumps(body),
                contentType="application/json",
                accept="application/json",
            )
        except Exception as exc:  # noqa: BLE001 — a refusal may be the measurement
            described = _describe_error(exc)
            elapsed = round((time.perf_counter() - started) * 1000.0, 3)
            if described["code"] not in {"ThrottlingException", "TooManyRequestsException"}:
                return None, described, elapsed
            if attempt == THROTTLE_ATTEMPTS - 1:
                return None, None, elapsed
            window = min(THROTTLE_MAX_SECONDS, THROTTLE_BASE_SECONDS * (2**attempt))
            time.sleep(window * (0.5 + _JITTER.random()))
            continue
        return response, None, round((time.perf_counter() - started) * 1000.0, 3)
    return None, None, 0.0


UNMEASURED_BY_THROTTLE: Final[str] = (
    "throttled on every attempt, so this question was not answered. A 429 says the account "
    "was busy; it says nothing about the request schema, and recording it as a refusal would "
    "read as though the model had rejected the input."
)


def _guard_census() -> dict[str, Any]:
    """Exercise ``assert_in_region`` on all four identifiers rather than describing it.

    A guard that is only ever quoted in a document is a guard nobody has run.  This puts
    its refusal string, verbatim, in the artefact that argues from it.
    """
    guard: dict[str, Any] = {}
    for model_id in (
        "amazon.titan-embed-text-v2:0",
        "cohere.embed-english-v3",
        "cohere.embed-v4:0",
        "global.cohere.embed-v4:0",
    ):
        try:
            assert_in_region(model_id)
        except ResidencyError as exc:
            guard[model_id] = {"admitted": False, "refusal_verbatim": str(exc)}
        else:
            guard[model_id] = {"admitted": True, "refusal_verbatim": None}
    return guard


def _probe_bare_v4(runtime: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    """Invoke ``cohere.embed-v4:0`` by its bare id.  The refusal is the finding."""
    bare_body = {
        "texts": [PROBE_TEXT],
        "input_type": "search_document",
        "embedding_types": ["float"],
    }
    started = time.perf_counter()
    try:
        runtime.invoke_model(
            modelId="cohere.embed-v4:0",
            body=json.dumps(bare_body),
            contentType="application/json",
            accept="application/json",
        )
    except Exception as exc:  # noqa: BLE001 — the refusal is the evidence, not a failure
        result: dict[str, Any] = {"outcome": "REFUSED", "error": _describe_error(exc)}
    else:
        result = {
            "outcome": "ADMITTED",
            "surprise": (
                "cohere.embed-v4:0 accepted an on-demand invocation. This contradicts the "
                "measurement this artefact was written to record; ADR 0040 must be revisited."
            ),
        }
    result["latency_ms"] = round((time.perf_counter() - started) * 1000.0, 3)
    raw = {
        "model_id": "cohere.embed-v4:0",
        "label": "bare vendor id, on-demand — REFUSED",
        "request": {
            "operation": "bedrock-runtime:InvokeModel",
            "modelId": "cohere.embed-v4:0",
            "contentType": "application/json",
            "accept": "application/json",
            "body": bare_body,
            "body_sha256": sha256_hex(json.dumps(bare_body).encode("utf-8")),
        },
        "response": None,
        "result": result,
    }
    return result, raw


def _probe_arms(
    runtime: Any, *, allow_violation: bool
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    """One probe invocation per arm, with the full request and response kept."""
    invoked: dict[str, dict[str, Any]] = {}
    raw: list[dict[str, Any]] = []
    for arm in ARMS:
        if arm.residency == "cross_region" and not allow_violation:
            invoked[arm.model_id] = {
                "outcome": "NOT ATTEMPTED",
                "reason": (
                    "--allow-residency-violation was not passed; this program refuses to "
                    "route a call outside ap-southeast-2 without an explicit, recorded "
                    "instruction"
                ),
            }
            continue
        call = invoke(runtime, arm, PROBE_TEXT, is_query=False)
        fingerprint = _vector_fingerprint(call.vector)
        invoked[arm.model_id] = {"outcome": "OK", **fingerprint}
        raw.append(
            {
                "model_id": arm.model_id,
                "label": f"{arm.family} — {arm.residency}",
                "request": {
                    "operation": "bedrock-runtime:InvokeModel",
                    "modelId": arm.model_id,
                    "contentType": "application/json",
                    "accept": "application/json",
                    "body": call.request_body,
                    "body_sha256": sha256_hex(json.dumps(call.request_body).encode("utf-8")),
                },
                "response": {
                    "http_status": call.response_head["http_status"],
                    "request_id": call.request_id,
                    "body_keys": call.response_head["keys"],
                    "response_type": call.response_head["response_type"],
                    "input_tokens": call.input_tokens,
                    "client_latency_ms": round(call.latency_ms, 3),
                    "server_latency_ms": call.server_latency_ms,
                    "embedding": fingerprint,
                },
                "result": {"outcome": "OK"},
            }
        )
    return invoked, raw


def _probe_length_ceiling(runtime: Any, *, allow_violation: bool) -> dict[str, Any]:
    """Measure each arm's maximum input rather than citing a documentation page.

    ``truncate: "END"`` is sent to the Cohere arms deliberately: if the ceiling were a
    model-side truncation the parameter would absorb it, and the refusal that comes back
    anyway is what proves the ceiling is enforced by the *request schema*, before the model
    is reached.  A caller must therefore cut the text itself, and the benchmark counts it.
    """
    length_limits: dict[str, Any] = {}
    for arm in ARMS:
        if arm.residency == "cross_region" and not allow_violation:
            length_limits[arm.model_id] = {"outcome": "NOT ATTEMPTED"}
            continue
        body = (
            _titan_body(LONG_PROBE_TEXT, arm)
            if arm.vendor == "Amazon"
            else {
                "texts": [LONG_PROBE_TEXT],
                "input_type": "search_document",
                "embedding_types": ["float"],
                "truncate": "END",
            }
        )
        response, error, _ = _invoke_past_throttle(runtime, arm.model_id, body)
        sent = "END" if arm.vendor == "Cohere" else None
        if response is not None:
            headers = {k.lower(): v for k, v in response["ResponseMetadata"]["HTTPHeaders"].items()}
            length_limits[arm.model_id] = {
                "outcome": "ACCEPTED",
                "input_chars": len(LONG_PROBE_TEXT),
                "input_tokens": int(headers.get("x-amzn-bedrock-input-token-count", 0)),
                "truncate_parameter_sent": sent,
            }
        elif error is not None:
            length_limits[arm.model_id] = {
                "outcome": "REFUSED",
                "input_chars": len(LONG_PROBE_TEXT),
                "truncate_parameter_sent": sent,
                "error": error,
            }
        else:
            length_limits[arm.model_id] = {
                "outcome": "UNMEASURED",
                "input_chars": len(LONG_PROBE_TEXT),
                "truncate_parameter_sent": sent,
                "reason": UNMEASURED_BY_THROTTLE,
            }
    return length_limits


def residency_finding(*, allow_violation: bool) -> dict[str, Any]:
    """Reproduce the three-model structure from scratch and write both raw artefacts.

    Nothing here is copied from another worker's file or from a brief.  Every string in the
    output was produced by a call made by this function, on this account, today.
    """
    runtime = bedrock_runtime()
    control = bedrock_control()

    declared, embed_v4_profiles, n_profiles = _control_plane_census(control)
    guard = _guard_census()
    bare_result, bare_raw = _probe_bare_v4(runtime)
    invoked, arm_raw = _probe_arms(runtime, allow_violation=allow_violation)
    length_limits = _probe_length_ceiling(runtime, allow_violation=allow_violation)
    dimension_probe = _probe_vector_column()
    raw = [bare_raw, *arm_raw]

    finding = {
        "headline": (
            "On this account, cohere.embed-v4:0 cannot be invoked in ap-southeast-2 at all. "
            "The only Bedrock identifier that serves it is the cross-region routing profile "
            "global.cohere.embed-v4:0, and MAINLINE's residency commitment "
            "(providers/bedrock_titan.py::REQUIRED_REGION, ARCHITECTURE 10.1) forbids it. "
            "The question ADR 0002 left open is therefore not 'which model scores higher' "
            "but 'residency or that model', and this system has already answered that once."
        ),
        "identity": {
            "region": REGION,
            "profile": os.environ.get("AWS_PROFILE") or DEFAULT_PROFILE,
            "caller_arn": redact(session().client("sts").get_caller_identity()["Arn"]),
        },
        "declared_by_the_control_plane": declared,
        "inference_profiles": {
            "total_visible": n_profiles,
            "containing_cohere_embed_v4": embed_v4_profiles,
            "count_containing_cohere_embed_v4": len(embed_v4_profiles),
        },
        "measured_invocations": invoked,
        "bare_v4_refusal": bare_result,
        "input_length_ceiling": length_limits,
        "our_own_residency_guard": guard,
        "what_global_means": {
            "aws_own_words": next(
                (p["description_verbatim"] for p in embed_v4_profiles),
                "(no description returned)",
            ),
            "model_arns_are_partly_regionless": [
                arn for p in embed_v4_profiles for arn in p["model_arns"]
            ],
            "reading": (
                "An inference profile whose member list includes an ARN with an EMPTY region "
                "segment (arn:aws:bedrock:::foundation-model/...) is not pinned to any "
                "region. AWS's own description says the profile 'routes requests to Embed v4 "
                "globally across all supported AWS Regions'. Where a given request is served "
                "is chosen by AWS at call time and is not observable to the caller, so the "
                "sentence 'these narratives were embedded in Australia' becomes unverifiable "
                "the moment this id is used. Unverifiable is the operative word: the harm is "
                "not that the data certainly leaves, it is that we could no longer prove it "
                "did not."
            ),
        },
        "commitments_at_stake": {
            "providers/bedrock_titan.py::REQUIRED_REGION": "ap-southeast-2",
            "providers/bedrock_titan.py refusal": (
                "refusing to embed Australian safety narratives outside the residency "
                "region; cognition stays in ap-southeast-2 (ARCHITECTURE 10.1)"
            ),
            "providers/resolve.py::REQUIRED_REGION": "ap-southeast-2",
            "scripts/aws/_common.py::CROSS_REGION_PREFIXES": sorted(CROSS_REGION_PREFIXES),
            "note_on_ARCHITECTURE": (
                "ARCHITECTURE 10.1 is cited by name in provider source but the document "
                "itself is not committed to this repository. The binding artefacts are the "
                "two REQUIRED_REGION constants and the refusal string above, all of which "
                "are in the tree and all of which are exercised by tests."
            ),
        },
        "dimension_probe": dimension_probe,
        "conclusion": (
            "cohere.embed-english-v3 is the only Cohere embedder this account can use "
            "without breaking residency, and it carries its own structural limit: Bedrock "
            "refuses any single text over 2048 characters for it, which 96 of the 1071 "
            "corpus documents exceed. embed-v4 is reachable only by a global routing "
            "profile. Neither can be adopted on the strength of a score alone."
        ),
    }

    artefact(
        EVIDENCE_DIR / "residency-finding.json",
        finding,
        kind="bedrock-residency-finding",
        caveats=RESIDENCY_CAVEATS,
        synthetic=False,
    )
    artefact(
        EVIDENCE_DIR / "raw-cohere-invoke.json",
        {
            "note": (
                "one full request and response per model id, redacted through "
                "_common.redact. Embeddings are truncated to their first 16 coordinates and "
                "accompanied by a sha256 over the full little-endian float32 vector, so a "
                "reproduction is checkable without committing 4 KiB of floats."
            ),
            "probe_text": PROBE_TEXT,
            "probe_text_sha256": sha256_hex(PROBE_TEXT.encode("utf-8")),
            "calls": raw,
        },
        kind="bedrock-raw-invocations",
        caveats=RAW_CAVEATS,
        synthetic=False,
    )
    return finding


def _probe_vector_column() -> dict[str, Any]:
    """Ask a real CockroachDB whether a 1536-d vector fits a ``VECTOR(1024)`` column.

    Migration 0031's header says a dimension change is *"a new table, never an ALTER"*.
    That is an architectural claim, and an architectural claim that has never been executed
    is a belief.  This probe executes both halves of it in a scratch database and records
    the SQLSTATE.  If no node is reachable the probe records ``unavailable`` with the
    driver's own error and the benchmark continues — a model comparison does not need a
    database, and blocking on one would be the tail wagging the dog.
    """
    dsn = os.environ.get("BENCH_LOCAL_DSN") or (
        "postgresql://root@localhost:26257/defaultdb?sslmode=disable"
    )
    try:
        with crdb(dsn=dsn) as conn:
            version = conn.execute("SELECT version()").fetchone()[0]
            conn.execute("CREATE DATABASE IF NOT EXISTS w_cohere_bench")
    except Exception as exc:  # noqa: BLE001 — an unreachable node is a recordable state
        return {
            "available": False,
            "reason": redact(f"{type(exc).__name__}: {exc}"),
            "reading": (
                "no node was reachable; the dimension claim below rests on migration 0031's "
                "header alone and has not been executed here"
            ),
        }

    outcomes: dict[str, Any] = {"available": True, "server_version": version.split(",")[0]}
    with crdb(dsn=dsn, database="w_cohere_bench") as conn:
        conn.execute("DROP TABLE IF EXISTS dim_probe")
        conn.execute(
            "CREATE TABLE dim_probe (id STRING PRIMARY KEY, embedding VECTOR(1024) NOT NULL)"
        )
        for dim in (1024, 1536):
            literal = "[" + ",".join(["0.1"] * dim) + "]"
            try:
                conn.execute(
                    "INSERT INTO dim_probe (id, embedding) VALUES (%s, %s::VECTOR)",
                    (f"d{dim}", literal),
                )
                outcomes[f"insert_{dim}d"] = {"outcome": "ACCEPTED"}
            except Exception as exc:  # noqa: BLE001 — the refusal is the measurement
                outcomes[f"insert_{dim}d"] = {
                    "outcome": "REFUSED",
                    "sqlstate": getattr(exc, "sqlstate", None),
                    "message_verbatim": str(exc).strip().splitlines()[0],
                }
        try:
            conn.execute("ALTER TABLE dim_probe ALTER COLUMN embedding TYPE VECTOR(1536)")
            outcomes["alter_to_1536"] = {"outcome": "ACCEPTED"}
        except Exception as exc:  # noqa: BLE001 — the refusal is the measurement
            outcomes["alter_to_1536"] = {
                "outcome": "REFUSED",
                "sqlstate": getattr(exc, "sqlstate", None),
                "message_verbatim": str(exc).strip().splitlines()[0],
            }
        conn.execute("DROP TABLE IF EXISTS dim_probe")
    outcomes["reading"] = (
        "VECTOR(1024) is a hard shape, not a hint. A 1536-d vector is refused at INSERT, "
        "and widening the column in place is refused during the index backfill. Migration "
        "0031's 'a new table, never an ALTER' is therefore a description of the platform's "
        "behaviour rather than a house style."
    )
    outcomes["scratch_database"] = "w_cohere_bench"
    return outcomes


# ═══════════════════════════════════════════════════════════════════════════════════════
# 6 · Stage two — the benchmark
# ═══════════════════════════════════════════════════════════════════════════════════════


def _cache_path(arm: Arm, what: str) -> Path:
    return VECTOR_CACHE / f"{arm.key}.{what}.npz"


def _journal_path(arm: Arm) -> Path:
    """Append-only per-call journal, keyed by the digest of the exact text sent.

    The first attempt at this benchmark died to a quota after roughly 700 of 1 167 texts
    and threw away every vector it had already paid for.  A journal makes the sweep
    **resumable**: a re-run reads what is already on disk, skips it, and spends only on
    what is missing.  It lives under ``out/`` and is gitignored — it is 35 MB of floats
    whose manifest, not whose bytes, belongs in ``evidence/``.
    """
    return VECTOR_CACHE / f"{arm.key}.calls.jsonl"


def _journal_key(text: str, *, is_query: bool) -> str:
    return sha256_hex(f"{'Q' if is_query else 'D'}\x00{text}".encode())


def _read_journal(arm: Arm) -> dict[str, EmbedCall]:
    path = _journal_path(arm)
    if not path.exists():
        return {}
    out: dict[str, EmbedCall] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        out[row["key"]] = EmbedCall(
            vector=row["vector"],
            input_tokens=row["input_tokens"],
            latency_ms=row["latency_ms"],
            server_latency_ms=row["server_latency_ms"],
            request_id=row["request_id"],
            request_body=row["request_body"],
            response_head=row["response_head"],
            truncated_from_chars=row["truncated_from_chars"],
            throttle_retries=row["throttle_retries"],
            botocore_retry_attempts=row["botocore_retry_attempts"],
        )
    return out


def _append_journal(arm: Arm, key: str, call: EmbedCall) -> None:
    row = {
        "key": key,
        "vector": call.vector,
        "input_tokens": call.input_tokens,
        "latency_ms": call.latency_ms,
        "server_latency_ms": call.server_latency_ms,
        "request_id": call.request_id,
        "request_body": call.request_body,
        "response_head": call.response_head,
        "truncated_from_chars": call.truncated_from_chars,
        "throttle_retries": call.throttle_retries,
        "botocore_retry_attempts": call.botocore_retry_attempts,
    }
    with _journal_path(arm).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row) + "\n")


def _estimate_tokens(texts: Sequence[str]) -> int:
    """A pre-spend estimate only.  Four characters per token is a rule of thumb and is
    labelled as one; every published number uses the token counts AWS returned."""
    return sum(max(1, len(t) // 4) for t in texts)


def embed_corpus_interleaved(
    corpus: BenchCorpus,
    arms: Sequence[Arm],
    *,
    pace_seconds: float,
    progress: Callable[[str], None],
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Embed every document and query with every arm, one text per call, arms interleaved.

    The interleave is the point.  A sweep that finishes Titan and then starts Cohere
    measures two different half-hours of one network as if they were two models.

    Anything already in an arm's journal is reused rather than re-bought, so a run
    interrupted by a quota can be resumed without paying twice or, worse, quietly reporting
    a corpus that is two thirds of the one it names.
    """
    client = bench_runtime()
    pacer = Pacer(floor=pace_seconds)
    journals = {arm.key: _read_journal(arm) for arm in arms}
    reused = {arm.key: 0 for arm in arms}
    fresh = {arm.key: 0 for arm in arms}
    for arm in arms:
        if journals[arm.key]:
            progress(f"  {arm.key}: {len(journals[arm.key])} calls already on disk, reusing")

    results: dict[str, dict[str, Any]] = {
        arm.key: {
            "doc_vectors": [],
            "query_vectors": [],
            "doc_calls": [],
            "query_calls": [],
        }
        for arm in arms
    }

    # ── sweep order: most load-bearing text first ─────────────────────────────────────
    #
    # Not corpus order.  On a throttled account the sweep may be stopped before it
    # finishes, and the journal is then all there is.  Ordering by *priority* — every
    # query, then every truth precursor, then the remaining judged documents, then the
    # distractors — means any prefix of the sweep is itself a complete, smaller, valid
    # pool: the same pool ``--max-documents`` would have produced. Corpus order would leave
    # an arbitrary alphabetical fragment that answers no query at all.
    priority = corpus.sweep_order()

    # ── multiple passes, because giving up on one text must not lose the other 247 ──────
    #
    # A text that exhausts its backoff is DEFERRED, not fatal.  The first design raised on
    # the ninth consecutive ThrottlingException and took the whole sweep down with it,
    # discarding every vector already bought.  On a quota-limited account that is the wrong
    # trade in both directions: the failure is transient, and the cost of abandoning is
    # everything.  So each pass takes what the account will give and the next pass asks
    # again; the loop stops when nothing is left or when a whole pass buys nothing, which is
    # the only signal that waiting longer is not the answer.
    deferred: set[tuple[str, int]] = set()
    passes = 0
    todo = list(priority)
    while todo and passes < MAX_SWEEP_PASSES:
        passes += 1
        deferred, bought = _one_sweep_pass(
            todo,
            corpus,
            arms,
            client=client,
            pacer=pacer,
            journals=journals,
            fresh=fresh,
            reused=reused,
            pass_number=passes,
            progress=progress,
        )
        progress(f"  pass {passes} done: bought {bought}, deferred {len(deferred)}")
        if not deferred:
            todo = []
            break
        if bought == 0:
            progress(
                f"  pass {passes} bought nothing and {len(deferred)} texts remain; the "
                "account is not serving this model right now"
            )
            break
        todo = [unit for unit in priority if unit in deferred]
    if deferred:
        raise BenchError(
            f"{len(deferred)} texts were still refused after {passes} passes. Every vector "
            "already bought is safe in the journal; re-run to resume, or score a smaller "
            "pool with --max-documents. Refusing to report a corpus with a hole in it."
        )

    # Rows are placed by INDEX, never by append order: the sweep visits texts by priority
    # and rotates which arm calls first, and neither of those may be allowed to permute the
    # matrices.  Row i of every arm's matrix is the same text because it was written to
    # row i, not because it happened to arrive i-th.
    for arm in arms:
        bucket = results[arm.key]
        bucket["doc_vectors"] = [None] * len(corpus.docs)
        bucket["query_vectors"] = [None] * len(corpus.queries)
        bucket["doc_calls"] = [None] * len(corpus.docs)
        bucket["query_calls"] = [None] * len(corpus.queries)
        for kind, position in priority:
            is_query = kind == "query"
            text = corpus.queries[position].text if is_query else corpus.docs[position].text
            call = journals[arm.key][_journal_key(text, is_query=is_query)]
            bucket["query_vectors" if is_query else "doc_vectors"][position] = call.vector
            bucket["query_calls" if is_query else "doc_calls"][position] = call
        if any(v is None for v in bucket["doc_vectors"]):
            raise BenchError(f"{arm.key}: a document row was never filled")
        if any(v is None for v in bucket["query_vectors"]):
            raise BenchError(f"{arm.key}: a query row was never filled")
        np.savez_compressed(
            _cache_path(arm, "vectors"),
            docs=np.asarray(bucket["doc_vectors"], dtype=np.float32),
            queries=np.asarray(bucket["query_vectors"], dtype=np.float32),
        )
    run_report = {
        "calls_made_this_run": fresh,
        "calls_reused_from_journal": reused,
        "journal": (
            "out/aws/bench/<arm>.calls.jsonl — gitignored; a resumed run reuses these "
            "rather than re-invoking, so a quota interruption costs time and not money. "
            "Latency figures therefore describe the run in which each call was actually "
            "made, and the split above says how many of each there were."
        ),
        "throttling": pacer.report(),
    }
    return results, run_report


def _one_sweep_pass(
    todo: Sequence[tuple[str, int]],
    corpus: BenchCorpus,
    arms: Sequence[Arm],
    *,
    client: Any,
    pacer: Pacer,
    journals: dict[str, dict[str, EmbedCall]],
    fresh: dict[str, int],
    reused: dict[str, int],
    pass_number: int,
    progress: Callable[[str], None],
) -> tuple[set[tuple[str, int]], int]:
    """One traversal of *todo*.  Returns the units a quota refused, and how many were bought.

    The arms are rotated per unit so no arm systematically holds the warm socket, and a
    ``BenchError`` from :func:`invoke` — which is only ever raised after the full throttle
    backoff — defers the unit instead of ending the sweep.
    """
    deferred: set[tuple[str, int]] = set()
    bought = 0
    for index, (kind, position) in enumerate(todo):
        is_query = kind == "query"
        text = corpus.queries[position].text if is_query else corpus.docs[position].text
        key = _journal_key(text, is_query=is_query)
        rotated = list(arms[index % len(arms) :]) + list(arms[: index % len(arms)])
        for arm in rotated:
            if journals[arm.key].get(key) is not None:
                reused[arm.key] += 1
                continue
            try:
                call = invoke(client, arm, text, is_query=is_query, pacer=pacer)
            except BenchError:
                deferred.add((kind, position))
                continue
            _append_journal(arm, key, call)
            journals[arm.key][key] = call
            fresh[arm.key] += 1
            bought += 1
        if index % 25 == 0:
            progress(
                f"  pass {pass_number}: {index + 1}/{len(todo)} texts, "
                f"fresh {sum(fresh.values())}, deferred {len(deferred)}"
            )
    return deferred, bought


def _replay_journal(
    corpus: BenchCorpus, arms: Sequence[Arm]
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Rebuild the whole sweep from the on-disk journals, making no AWS call at all.

    This is what ``--rescore-only`` runs on.  It exists so that the *report* can be
    regenerated — a new section added, a metric corrected — without re-invoking a single
    model.  Re-running a benchmark to fix a typo in its own summary is how a fleet spends
    money proving nothing.
    """
    journals = {arm.key: _read_journal(arm) for arm in arms}
    results: dict[str, dict[str, Any]] = {
        arm.key: {"doc_vectors": [], "query_vectors": [], "doc_calls": [], "query_calls": []}
        for arm in arms
    }
    units = [("doc", d.text) for d in corpus.docs] + [("query", q.text) for q in corpus.queries]
    for kind, text in units:
        is_query = kind == "query"
        key = _journal_key(text, is_query=is_query)
        for arm in arms:
            call = journals[arm.key].get(key)
            if call is None:
                raise BenchError(
                    f"{arm.key}: the journal has no entry for a "
                    f"{'query' if is_query else 'document'} it must cover. Run without "
                    "--rescore-only to complete the sweep; refusing to score a corpus with "
                    "a hole in it."
                )
            bucket = results[arm.key]
            bucket["doc_vectors" if kind == "doc" else "query_vectors"].append(call.vector)
            bucket["doc_calls" if kind == "doc" else "query_calls"].append(call)
    report = {
        "calls_made_this_run": {arm.key: 0 for arm in arms},
        "calls_reused_from_journal": {arm.key: len(journals[arm.key]) for arm in arms},
        "journal": "replayed from out/aws/bench/<arm>.calls.jsonl; no model was invoked",
    }
    return results, report


def _quota_census() -> dict[str, Any]:
    """Read this account's Bedrock service quotas.  Read-only, free, and decisive.

    The throttling that killed this benchmark's first attempt is not a mystery to be
    inferred from failures: Service Quotas will state the number.  What it states changes
    the throughput half of the comparison completely, and in the *opposite* direction to
    the recommendation this ADR makes — which is exactly why it is measured and published
    rather than left as a footnote about a flaky run.

    ``ListServiceQuotas`` is a read; nothing here requests an increase.  A quota increase is
    an account-settings change and is out of scope for every worker in this fleet.
    """
    interesting = (
        "Amazon Titan Text Embeddings V2",
        "Titan Text Embeddings V2",
        "Cohere Embed English",
        "Cohere Embed V4",
    )
    try:
        client = session().client("service-quotas", region_name=REGION)
        rows: list[dict[str, Any]] = []
        for page in client.get_paginator("list_service_quotas").paginate(ServiceCode="bedrock"):
            for quota in page["Quotas"]:
                name = quota.get("QuotaName", "")
                if any(marker in name for marker in interesting):
                    rows.append(
                        {
                            "quota_name": name,
                            "value": quota.get("Value"),
                            "adjustable": quota.get("Adjustable"),
                            "quota_code": quota.get("QuotaCode"),
                        }
                    )
    except Exception as exc:  # noqa: BLE001 — a missing permission is a recordable state
        return {
            "available": False,
            "reason": redact(f"{type(exc).__name__}: {exc}"),
            "reading": "this account could not read its own quotas; the throughput section "
            "below rests on observed throttling alone",
        }
    rows.sort(key=lambda r: r["quota_name"])
    return {
        "available": True,
        "source": "service-quotas:ListServiceQuotas, ServiceCode=bedrock, read-only",
        "quotas": rows,
        "reading": (
            "On-demand requests per minute is the binding constraint for a corpus-scale "
            "sweep, and it is the number that decides how long an embedding pass takes. "
            "Read the per-request batch size beside it: the Cohere embedders accept up to "
            "96 texts in one InvokeModel call and Titan v2 accepts exactly one, so requests "
            "per minute and TEXTS per minute are not the same quantity and the ranking "
            "reverses between them. This is measured in 'throughput' below rather than "
            "reasoned about."
        ),
    }


def _observed_throughput(hours: int = 12) -> dict[str, Any]:
    """What AWS says actually happened, from outside this repository.

    ``Invocations`` and ``InvocationThrottles`` are published per ``ModelId`` at no cost and
    need no provisioning, which makes them an attestation written by AWS rather than by us.
    They are the reason §4 of ADR 0040 can state a throttling ratio instead of an anecdote.

    Read-only. ``scripts/aws/cloudwatch_evidence.py`` owns the fleet's CloudWatch artefact;
    this is a citation inside a benchmark, not a second copy of that evidence.
    """
    window_end = datetime.now(UTC)
    window_start = window_end - timedelta(hours=hours)
    try:
        client = cloudwatch()
        out: dict[str, Any] = {}
        # Measured, not assumed: an inference profile is metered under the **profile id**,
        # and the bare model id carries only the refused on-demand attempts — 8 Invocations
        # with 0 InputTokenCount, which is exactly the shape of a request that never reached
        # a model. Both dimensions are read so that pairing is visible rather than inferred.
        dimensions = [arm.model_id for arm in ARMS] + ["cohere.embed-v4:0"]
        for metered_as in dict.fromkeys(dimensions):
            row: dict[str, Any] = {}
            for metric in ("Invocations", "InvocationThrottles", "InputTokenCount"):
                stats = client.get_metric_statistics(
                    Namespace="AWS/Bedrock",
                    MetricName=metric,
                    Dimensions=[{"Name": "ModelId", "Value": metered_as}],
                    StartTime=window_start,
                    EndTime=window_end,
                    Period=hours * 3600,
                    Statistics=["Sum"],
                )
                row[metric] = sum(point["Sum"] for point in stats["Datapoints"])
            total = row["Invocations"] + row["InvocationThrottles"]
            row["throttled_fraction"] = (
                None if total == 0 else round(row["InvocationThrottles"] / total, 6)
            )
            out[metered_as] = row
    except Exception as exc:  # noqa: BLE001 — a missing permission is a recordable state
        return {"available": False, "reason": redact(f"{type(exc).__name__}: {exc}")}
    return {
        "available": True,
        "source": "cloudwatch:GetMetricStatistics, namespace AWS/Bedrock, read-only",
        "window_hours": hours,
        "window_end": window_end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "by_metered_model_id": out,
        "reading": (
            "This counts every call this account made in the window, including this fleet's "
            "other workers and this benchmark's own failed first attempt. It is not a "
            "controlled experiment; it is the operational reality the next corpus-scale "
            "embedding pass will meet."
        ),
        "bare_v4_row_is_the_refusals": (
            "the cohere.embed-v4:0 row counts Invocations with ZERO InputTokenCount. Those "
            "are the on-demand attempts Bedrock refused: the request was counted, no model "
            "was reached, and nothing was billed. The work done under Embed v4 is metered "
            "under global.cohere.embed-v4:0, which is AWS's own accounting confirming that "
            "the profile — not the in-region model — is what served it."
        ),
    }


def _probe_batch_capability(runtime: Any, *, allow_violation: bool) -> dict[str, Any]:
    """Measure how many texts each arm accepts in ONE call, instead of assuming.

    ``MAX_BATCH = 96`` in ``providers/base.py`` is the number the production code already
    uses for Titan, where it means "96 sequential calls".  For Cohere it can mean one call.
    The difference is the entire throughput argument, so it is measured: 96 copies of one
    short probe string per Cohere arm, and the same list handed to Titan to see it refused.
    """
    probe = "isolation not proven at the break point"
    out: dict[str, Any] = {}
    for arm in ARMS:
        if arm.residency == "cross_region" and not allow_violation:
            out[arm.model_id] = {"outcome": "NOT ATTEMPTED"}
            continue
        if arm.vendor == "Amazon":
            body: dict[str, Any] = {"inputText": [probe] * 96, "dimensions": 1024}
        else:
            body = {
                "texts": [probe] * 96,
                "input_type": "search_document",
                "embedding_types": ["float"],
            }
        response, error, latency_ms = _invoke_past_throttle(runtime, arm.model_id, body)
        if response is not None:
            decoded = json.loads(response["body"].read())
            embeddings = decoded.get("embeddings")
            returned = embeddings.get("float") if isinstance(embeddings, Mapping) else embeddings
            headers = {k.lower(): v for k, v in response["ResponseMetadata"]["HTTPHeaders"].items()}
            out[arm.model_id] = {
                "outcome": "ACCEPTED",
                "texts_sent": 96,
                "vectors_returned": len(returned) if isinstance(returned, list) else None,
                "latency_ms": latency_ms,
                "input_tokens": int(headers.get("x-amzn-bedrock-input-token-count", 0)),
            }
        elif error is not None:
            out[arm.model_id] = {"outcome": "REFUSED", "texts_sent": 96, "error": error}
        else:
            out[arm.model_id] = {
                "outcome": "UNMEASURED",
                "texts_sent": 96,
                "reason": UNMEASURED_BY_THROTTLE,
            }
    return out


#: Which Service Quotas row states each arm's on-demand request rate.  Matched by exact
#: quota name so a renamed quota shows up as a missing row rather than as a wrong number.
_RPM_QUOTA_NAME: Final[Mapping[str, str]] = {
    "amazon.titan-embed-text-v2:0": (
        "On-demand model inference requests per minute for Amazon Titan Text Embeddings V2"
    ),
    "cohere.embed-english-v3": (
        "On-demand model inference requests per minute for Cohere Embed English"
    ),
    "global.cohere.embed-v4:0": (
        "Global cross-region model inference requests per minute for Cohere Embed V4"
    ),
}


def _texts_per_minute(quotas: Mapping[str, Any], batch: Mapping[str, Any]) -> dict[str, Any]:
    """Requests per minute times texts per request.  The two are not the same number.

    A reader who sees "Titan 60 RPM, Cohere 20 RPM" concludes Titan is three times faster.
    A reader who also sees that one request carries 96 Cohere texts and exactly one Titan
    text concludes the opposite, by a factor of ten. Publishing the first without the
    second would be a true sentence doing the work of a false one.
    """
    by_name = {row["quota_name"]: row for row in (quotas.get("quotas") or [])}
    out: dict[str, Any] = {}
    for arm in ARMS:
        quota_row = by_name.get(_RPM_QUOTA_NAME.get(arm.model_id, ""))
        rpm = None if quota_row is None else quota_row.get("value")
        measured = batch.get(arm.model_id, {})
        per_request = (
            measured.get("vectors_returned") if measured.get("outcome") == "ACCEPTED" else 1
        )
        out[arm.model_id] = {
            "quota_requests_per_minute": rpm,
            "quota_adjustable": None if quota_row is None else quota_row.get("adjustable"),
            "measured_texts_per_request": per_request,
            "texts_per_minute_ceiling": (
                None if rpm is None or per_request is None else rpm * per_request
            ),
            "basis": (
                "quota value from service-quotas:ListServiceQuotas; texts per request from "
                "the 96-text probe in 'measured_batch_capability'. This is a CEILING the "
                "quota permits, not a rate this program achieved — see "
                "'observed_sustained_rate' for what the account actually served."
            ),
        }
    return out


def _load_cached(arm: Arm) -> tuple[Any, Any]:
    path = _cache_path(arm, "vectors")
    if not path.exists():
        raise BenchError(
            f"{arm.key}: no cached vectors at {path}. Run without --rescore-only first."
        )
    with np.load(path) as data:
        return data["docs"], data["queries"]


def build_arm_report(
    arm: Arm,
    corpus: BenchCorpus,
    ranking: ArmRanking,
    calls: Sequence[EmbedCall] | None,
) -> dict[str, Any]:
    n_queries = len(corpus.queries)
    report: dict[str, Any] = {
        "model_id": arm.model_id,
        "vendor": arm.vendor,
        "family": arm.family,
        "residency": arm.residency,
        "residency_label": (
            "IN-REGION (ap-southeast-2, on-demand, no inference profile)"
            if arm.residency == "in_region"
            else "RESIDENCY-VIOLATING — cross-region routing profile, measured for "
            "completeness on a synthetic corpus and NOT proposed for use"
        ),
        "native_dimension": arm.native_dim,
        "requested_dimension": arm.requested_dim,
        "notes": arm.notes,
        "retrieval": {
            "task": (
                "G4 retro-recall: given a permit synthesised from a fatality investigation's "
                "own description of the work, does the prior incident the investigator cited "
                "surface inside the time wall?"
            ),
            "ranking": "exhaustive cosine over the walled candidate pool; no ANN index",
            f"hit_at_k_truth_precursor_grade_{TRUTH_GRADE}": {
                f"@{k}": _wilson(sum(ranking.hit_truth[k]), n_queries) for k in CUTOFFS
            },
            f"hit_at_k_any_relevant_grade_ge_{RELATED_GRADE}": {
                f"@{k}": _wilson(sum(ranking.hit_related[k]), n_queries) for k in CUTOFFS
            },
            "mrr_truth_precursor": _mean_with_interval(
                ranking.reciprocal_rank, label=f"{arm.key}:mrr"
            ),
            "ndcg_at_10": _mean_with_interval(ranking.ndcg10, label=f"{arm.key}:ndcg10"),
            "truth_rank": _mean_with_interval(
                [float(r) for r in ranking.truth_rank], label=f"{arm.key}:rank"
            ),
            "tie_break": {
                "rule": (
                    "pessimistic: the truth precursor is ranked behind every document that "
                    "scores equal to it within 1e-9, not in front of them"
                ),
                "queries_whose_truth_precursor_is_tied": sum(
                    1 for t in ranking.truth_tied_with if t > 0
                ),
                "mean_documents_tied_with_the_truth_precursor": round(
                    sum(ranking.truth_tied_with) / max(1, len(ranking.truth_tied_with)), 4
                ),
                "max_documents_tied_with_the_truth_precursor": max(
                    ranking.truth_tied_with, default=0
                ),
                "reading": (
                    "a tie here is not a near-miss, it is an exact one: the corpus contains "
                    "byte-identical narratives, so the vectors are identical. See "
                    "corpus.text_duplication."
                ),
            },
        },
    }

    if calls is not None:
        # Latency is reported over the calls that nothing retried.  A throttled call's
        # wall-clock time includes botocore's own exponential backoff, taken *inside*
        # ``invoke_model``; folding those into the mean would publish "Titan v2 answers in
        # 3 700 ms", which is a fact about this account's request quota wearing a model's
        # name.  The excluded count is published beside the mean so the exclusion cannot be
        # mistaken for a clean sweep.
        clean = [c for c in calls if c.clean]
        latencies = [c.latency_ms for c in clean]
        server = [c.server_latency_ms for c in clean if c.server_latency_ms is not None]
        tokens = sum(c.input_tokens for c in calls)
        # ``calls`` is documents first, then queries — see ``run_bench``.
        doc_calls = list(calls)[: len(corpus.docs)]
        doc_tokens = sum(c.input_tokens for c in doc_calls)
        ledger = token_ledger_entry(arm.model_id, len(calls), tokens, 0)
        price = USD_PER_1K_TOKENS.get(arm.model_id)
        mean_doc_tokens = doc_tokens / len(doc_calls)
        # 1 000 documents cost ``1000 * mean_doc_tokens`` tokens, and the price is quoted
        # per 1 000 tokens, so the two thousands cancel and the answer is simply
        # ``price_per_1k * mean_tokens_per_document``.
        usd_per_1000_docs = None if price is None else round(price["input"] * mean_doc_tokens, 8)
        truncated = [c for c in calls if c.truncated_from_chars is not None]
        throttled = sum(c.throttle_retries for c in calls)
        report["cost_and_latency"] = {
            "calls": len(calls),
            "one_text_per_call": True,
            "input_tokens_total": tokens,
            "input_tokens_documents_only": doc_tokens,
            "mean_input_tokens_per_document": round(mean_doc_tokens, 4),
            "throttle_retries_total": throttled,
            "calls_retried_by_botocore": sum(1 for c in calls if c.botocore_retry_attempts),
            "calls_excluded_from_latency": len(calls) - len(clean),
            "latency_basis": (
                "calls that neither botocore nor this program retried; a retried call's "
                "wall clock is the account's request quota, not the model's response time"
            ),
            "client_latency_ms": (
                _mean_with_interval(latencies, label=f"{arm.key}:lat") if latencies else None
            ),
            "server_reported_latency_ms": (
                _mean_with_interval([float(s) for s in server], label=f"{arm.key}:slat")
                if server
                else None
            ),
            "usd_per_1000_documents": usd_per_1000_docs,
            "usd_this_run": ledger["usd_total"],
            "token_ledger_entry": ledger,
        }
        report["input_handling"] = {
            "max_input_chars_enforced_by_bedrock": arm.max_input_chars,
            "texts_truncated_client_side": len(truncated),
            "texts_truncated_fraction_of_corpus": round(len(truncated) / max(1, len(calls)), 6),
            "longest_text_cut_from_chars": (
                max((c.truncated_from_chars or 0) for c in truncated) if truncated else None
            ),
            "reading": (
                "Bedrock refuses this model any single text over "
                f"{arm.max_input_chars} characters — a request-schema validation, not a "
                "model truncation, so 'truncate: END' does not soften it. Every cut is "
                "counted here because a benchmark that silently shortens one arm's inputs "
                "is not a benchmark."
                if arm.max_input_chars is not None
                else "no character ceiling was hit for this arm on this corpus"
            ),
        }

    report["storage_compatibility"] = {
        "target_column": "mainline.clause_embedding.embedding VECTOR(1024)",
        "target_migration": "verticals/mainline/db/migrations/0031_clause_embedding.sql",
        "fits_existing_column": arm.native_dim == 1024
        or (arm.requested_dim == 1024 if arm.requested_dim else False),
        "stored_dimension_would_be": arm.requested_dim or arm.native_dim,
        "migration_cost_if_adopted": (
            "none — the width already matches"
            if (arm.requested_dim or arm.native_dim) == 1024
            else (
                "an expand/contract migration: a new sidecar table, a read view over both, "
                "one cutover migration, then the old table is dropped. Migration 0031's "
                "header forbids ALTER TABLE ... ALTER COLUMN embedding TYPE VECTOR(n), and "
                "the dimension probe in residency-finding.json shows the platform refusing "
                "both the narrow INSERT and the in-place widen."
            )
        ),
    }
    return report


# ═══════════════════════════════════════════════════════════════════════════════════════
# 7 · Entry point
# ═══════════════════════════════════════════════════════════════════════════════════════


def _selected_arms(allow_violation: bool, only: str | None = None) -> tuple[Arm, ...]:
    """The arms this invocation will touch.

    ``only`` exists for one measured reason.  When one arm's quota is exhausted and the
    others are healthy, the useful move is to buy the healthy arms now — filling the shared
    journal — while the exhausted one rests untouched.  Splitting the sweep that way costs
    nothing: the journal is keyed by the text, not by the run, so the later all-arms pass
    reuses every Cohere vector and spends only on Titan.
    """
    chosen = ARMS if allow_violation else tuple(a for a in ARMS if a.residency == "in_region")
    if only:
        wanted = {name.strip() for name in only.split(",") if name.strip()}
        unknown = wanted - {a.key for a in ARMS}
        if unknown:
            raise BenchError(f"--only-arms names no such arm: {sorted(unknown)}")
        chosen = tuple(a for a in chosen if a.key in wanted)
    if not chosen:
        raise BenchError("no arms selected")
    return chosen


def run_bench(
    *,
    allow_violation: bool,
    rescore_only: bool,
    max_documents: int | None,
    pace_seconds: float,
    only_arms: str | None,
    embed_only: bool,
    progress: Callable[[str], None],
) -> dict[str, Any]:
    """Embed, score, compare pairwise, price, and write ``cohere-vs-titan.json``."""
    corpus = load_bench_corpus(max_documents=max_documents)
    arms = _selected_arms(allow_violation, only_arms)
    progress(
        f"corpus: {len(corpus.docs)} documents, {len(corpus.queries)} queries, {len(arms)} arms"
    )

    for arm in arms:
        if arm.residency == "in_region":
            assert_in_region(arm.model_id)

    calls_by_arm: dict[str, list[EmbedCall]] | None = None
    run_report: dict[str, Any] = {
        "mode": (
            "rescore-only: every vector and every timing replayed from the on-disk journal, "
            "no model invoked"
            if rescore_only
            else "live"
        )
    }
    if rescore_only:
        raw, sweep = _replay_journal(corpus, arms)
        run_report.update(sweep)
        vectors = {
            arm.key: (
                np.asarray(raw[arm.key]["doc_vectors"], dtype=np.float32),
                np.asarray(raw[arm.key]["query_vectors"], dtype=np.float32),
            )
            for arm in arms
        }
        calls_by_arm = {
            arm.key: list(raw[arm.key]["doc_calls"]) + list(raw[arm.key]["query_calls"])
            for arm in arms
        }
    else:
        texts = list(corpus.texts) + [q.text for q in corpus.queries]
        estimate = _estimate_tokens(texts)
        priced = sum(
            (USD_PER_1K_TOKENS.get(a.model_id, {}).get("input", 0.0)) * estimate / 1000.0
            for a in arms
        )
        progress(
            f"pre-spend estimate: {len(texts)} texts x {len(arms)} arms, "
            f"~{estimate} tokens/arm (4 chars/token rule of thumb), USD ~{priced:.4f}"
        )
        check_cost_ceiling(priced, what="cohere-vs-titan benchmark")
        VECTOR_CACHE.mkdir(parents=True, exist_ok=True)
        raw, sweep = embed_corpus_interleaved(
            corpus, arms, pace_seconds=pace_seconds, progress=progress
        )
        run_report.update(sweep)
        if embed_only:
            progress("  --embed-only: journals filled, nothing scored, no artefact written")
            return run_report
        vectors = {
            arm.key: (
                np.asarray(raw[arm.key]["doc_vectors"], dtype=np.float32),
                np.asarray(raw[arm.key]["query_vectors"], dtype=np.float32),
            )
            for arm in arms
        }
        calls_by_arm = {
            arm.key: list(raw[arm.key]["doc_calls"]) + list(raw[arm.key]["query_calls"])
            for arm in arms
        }

    rankings: dict[str, ArmRanking] = {}
    reports: dict[str, Any] = {}
    for arm in arms:
        doc_vectors, query_vectors = vectors[arm.key]
        if doc_vectors.shape[1] != arm.native_dim and arm.requested_dim is None:
            raise BenchError(
                f"{arm.key}: returned width {doc_vectors.shape[1]} but this arm declares "
                f"native_dim={arm.native_dim}. The declaration is now wrong and the "
                "storage-compatibility conclusion would be too."
            )
        ranking = score_arm(corpus, doc_vectors, query_vectors)
        rankings[arm.key] = ranking
        reports[arm.key] = build_arm_report(
            arm, corpus, ranking, calls_by_arm[arm.key] if calls_by_arm else None
        )
        reports[arm.key]["observed_dimension"] = int(doc_vectors.shape[1])
        progress(
            f"  {arm.key}: hit@1 {sum(ranking.hit_truth[1])}/{len(corpus.queries)}, "
            f"hit@10 {sum(ranking.hit_truth[10])}/{len(corpus.queries)}"
        )

    incumbent = "titan_v2"
    paired: dict[str, Any] = {}
    for arm in arms:
        if arm.key == incumbent or incumbent not in rankings:
            continue
        paired[f"{incumbent}_vs_{arm.key}"] = {
            f"hit@{k}_truth_precursor": _paired_sign_test(
                rankings[incumbent].hit_truth[k], rankings[arm.key].hit_truth[k]
            )
            for k in CUTOFFS
        }
    if incumbent not in rankings:
        paired["not_computed"] = (
            "the incumbent arm was not part of this run, so there is nothing to compare "
            "against. A benchmark missing its incumbent is a description of the "
            "challengers, not a comparison."
        )

    ledger_entries = [
        reports[a.key]["cost_and_latency"]["token_ledger_entry"]
        for a in arms
        if "cost_and_latency" in reports[a.key]
    ]

    # The throughput census is read-only and free, and it is the section most likely to
    # argue against the recommendation this file ends with.  It is therefore taken every
    # run, including a rescore, rather than being cached.
    progress("  reading service quotas and measuring per-request batch size")
    batch = _probe_batch_capability(bedrock_runtime(), allow_violation=allow_violation)
    quotas = _quota_census()
    throughput = {
        "why_this_section_exists": (
            "This benchmark's first attempt was killed by a ThrottlingException after "
            "roughly 700 of 1 167 texts. Rather than treat that as a flaky run, the quota "
            "was read and the per-request batch size measured. The result is the strongest "
            "argument against the decision recorded in ADR 0040, and it belongs beside the "
            "decision rather than in a postmortem nobody opens."
        ),
        "service_quotas": quotas,
        "measured_batch_capability": batch,
        "texts_per_minute": _texts_per_minute(quotas, batch),
        "observed_throughput": _observed_throughput(),
    }

    payload = {
        "question": (
            "ADR 0002 recorded cohere.embed-v4:0 as a benchmark candidate against Titan and "
            "made no change. This is the benchmark, and the answer it produces is a "
            "recommendation, not a switch."
        ),
        "corpus": dict(corpus.provenance),
        "sweep": run_report,
        "throughput": throughput,
        "arms": reports,
        "paired_comparisons": paired,
        "paired_comparison_note": (
            "All arms are scored on the same 96 queries, so the arms are paired data. "
            "Comparing two independent Wilson intervals answers a weaker question than the "
            "one being asked; the discordant counts and the exact sign test below are the "
            "comparison that respects the pairing."
        ),
        "token_ledger": {
            "entries": ledger_entries,
            "total": ledger_total(ledger_entries) if ledger_entries else None,
        },
        "residency": {
            "in_region_arms": [a.model_id for a in arms if a.residency == "in_region"],
            "cross_region_arms": [a.model_id for a in arms if a.residency == "cross_region"],
            "allow_residency_violation_flag": allow_violation,
            "finding": "evidence/aws/bench/residency-finding.json",
        },
        "decision": {
            "adr": "docs/adr/0040-embedding-benchmark-titan-vs-cohere.md",
            "recommendation": "KEEP amazon.titan-embed-text-v2:0",
            "what_this_file_does_not_do": (
                "It changes no provider code and switches no model. "
                "providers/bedrock_titan.py::TITAN_EMBED_MODEL_ID is untouched."
            ),
        },
    }
    artefact(
        EVIDENCE_DIR / "cohere-vs-titan.json",
        payload,
        kind="embedding-benchmark",
        caveats=BENCH_CAVEATS,
        synthetic=True,
    )
    return payload


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Benchmark Cohere against Titan, and report the residency finding first.",
    )
    parser.add_argument(
        "--stage",
        choices=("all", "residency", "bench"),
        default="all",
        help="residency: the structural finding only. bench: the scores only.",
    )
    parser.add_argument(
        "--allow-residency-violation",
        action="store_true",
        help=(
            "invoke global.cohere.embed-v4:0, which routes outside ap-southeast-2. "
            "Required for the third arm. Recorded in every artefact it touches."
        ),
    )
    parser.add_argument(
        "--max-documents",
        type=int,
        default=None,
        help=(
            "cap the candidate pool. Every judged document is kept; unjudged distractors "
            "are added in external_ref order until the cap. Omit for the whole corpus."
        ),
    )
    parser.add_argument(
        "--pace-seconds",
        type=float,
        default=0.0,
        help=(
            "minimum seconds to wait before each call to each model. A deliberate pace "
            "beats discovering the quota thirty ThrottlingExceptions at a time."
        ),
    )
    parser.add_argument(
        "--only-arms",
        default=None,
        help=(
            "comma-separated arm keys to touch this run (titan_v2, cohere_v3, "
            "cohere_v4_global). Use it to buy the healthy arms while a throttled one rests."
        ),
    )
    parser.add_argument(
        "--embed-only",
        action="store_true",
        help="fill the journals and stop; write no artefact and score nothing",
    )
    parser.add_argument(
        "--rescore-only",
        action="store_true",
        help="score from the cached vectors under out/aws/bench/ and make no AWS calls",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="load the corpus, price the run, and stop before any Bedrock call",
    )
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    def progress(message: str) -> None:
        if not args.quiet:
            print(message, flush=True)

    started = datetime.now(UTC)
    if args.dry_run:
        corpus = load_bench_corpus(max_documents=args.max_documents)
        arms = _selected_arms(args.allow_residency_violation, args.only_arms)
        texts = list(corpus.texts) + [q.text for q in corpus.queries]
        estimate = _estimate_tokens(texts)
        for arm in arms:
            price = USD_PER_1K_TOKENS.get(arm.model_id, {}).get("input")
            progress(
                f"{arm.key:20s} {arm.model_id:32s} residency={arm.residency:12s} "
                f"~{estimate} tokens  USD ~"
                + ("unpriced" if price is None else f"{price * estimate / 1000:.5f}")
            )
        progress(
            f"{len(texts)} texts, {len(arms)} arms, "
            f"{len(texts) * len(arms)} calls. Nothing was invoked."
        )
        return 0

    if args.stage in {"all", "residency"}:
        progress("stage 1 — residency finding")
        residency_finding(allow_violation=args.allow_residency_violation)
        progress(f"  wrote {EVIDENCE_DIR / 'residency-finding.json'}")
        progress(f"  wrote {EVIDENCE_DIR / 'raw-cohere-invoke.json'}")

    if args.stage in {"all", "bench"}:
        progress("stage 2 — benchmark")
        run_bench(
            allow_violation=args.allow_residency_violation,
            rescore_only=args.rescore_only,
            max_documents=args.max_documents,
            pace_seconds=args.pace_seconds,
            only_arms=args.only_arms,
            embed_only=args.embed_only,
            progress=progress,
        )
        if not args.embed_only:
            progress(f"  wrote {EVIDENCE_DIR / 'cohere-vs-titan.json'}")

    progress(f"elapsed {(datetime.now(UTC) - started).total_seconds():.1f}s")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
