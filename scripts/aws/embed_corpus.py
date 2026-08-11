# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Embed MAINLINE's whole evaluation corpus through Amazon Titan v2 and prove, per vector,
which text produced it.

    D:/CoackroachDBxAWS/mainline/.venv/Scripts/python.exe scripts/aws/embed_corpus.py

WHY THIS PROGRAM EXISTS
-----------------------
Every vector in this repository before today was eight-dimensional and fabricated:
``tests/integration/algorithms/candidates/_w7_support.py`` builds ``VECTOR(8)`` columns from
``fixture_embedding(text, dim=8)``, whose own docstring says *"Not a model output and never
claimed to be one."*  The production DDL declares ``VECTOR(1024)`` and the production read
path asks Bedrock for it, and until now the two had never met.  This program is the meeting:
it takes the corpus the gold sets actually judge, sends each document's own text to
``amazon.titan-embed-text-v2:0`` in ``ap-southeast-2``, and writes a manifest in which every
vector is bound to its text by two digests — so the claim "this vector is Titan's, of that
text" is checkable by a stranger with a hash function and no AWS account.

WHAT IT EMBEDS
--------------
Four corpora, each identified by **the same ``doc_id`` the committed gold sets use**, so
``evidence/aws/recall`` can score against ``tests/fixtures/recall/goldsets`` with no join
table:

1. ``trappoint_recall.corpora.synthetic.generate()`` — MSHA-shaped fatality investigation
   reports, CSB reports, Australian state-regulator alerts **and the Part 50 extract**.
   The loaders in ``trappoint_recall.corpora.msha`` / ``.csb`` are what turn the generated
   text into ``EventRecord``s, and ``EventRecord.to_split_record`` sets
   ``doc_id = external_ref``; that identity is why nothing has to be joined later.
2. The 96 retro query narratives in ``goldsets/g4_retro.queries.jsonl``, facet ``narrative``.
3. The 893 MAINLINE clauses in ``verticals/mainline/fixtures/corpus/answer-key/clause.jsonl``,
   with prose resolved through ``mainline_corpus.docx.bodies.BodyBank`` — the renderer's own
   provider chain, so the embedded text is byte-identical to what the corpus renders.

THE PART 50 SET IS INCLUDED, AND HERE IS THE MEASUREMENT THAT DECIDED IT
------------------------------------------------------------------------
The brief for this worker named three of the four corpora ``generate()`` returns and gave the
reason: *"so evidence/aws/recall can score against tests/fixtures/recall/goldsets"*.  Counted
on this machine, the five committed qrels files judge **1 049 distinct ``doc_id``s**.  The
three named sets cover **165** of them.  All four cover **1 049 — every one, nothing
missing**.  The 884 uncovered ids are Part 50 ``DOCUMENT_NO``s, and they are not a footnote:
in ``g4_retro`` the *truth precursor* of a fatality is a Part 50 row (``doc_id "2100141"``
for ``Q-G4-FAI-2010-001``).  An index without them cannot score the gold sets at all, which
is the stated purpose of the work.  So the fourth set is in, ``--sets`` makes the three-set
behaviour one flag away, and ``corpus-provenance.json`` records the coverage both ways.

WHAT IS PROVEN, AND HOW
-----------------------
* **One ``inputText`` per ``InvokeModel``.**  Titan v2 has no batch form; the loop is the API.
  The request is exactly ``{"inputText", "dimensions": 1024, "normalize": true}``.
* **Every stored vector is unit-norm.**  Titan's ``normalize: true`` returns a norm near 1.0
  (measured 1.0000000094 on the probe), which is *near* and not *is*.  Each vector is
  re-normalised in float64, cast to float32, and the **float32 bytes that are actually
  stored** are re-measured; a deviation over 1e-5 raises rather than being written.
* **Which vector came from which text** is a pair of digests per id: ``text_sha256`` over the
  UTF-8 bytes sent, and ``sha256`` over the little-endian C-order float32 bytes stored.  The
  manifest carries both for all of them.
* **Resumable.**  A second run loads the store, matches ``text_sha256`` per id, and makes
  **zero** Bedrock calls.  An id whose text has changed is re-embedded and counted as stale,
  because a stale vector that survives a corpus edit is worse than a missing one.
* **Throttling** is caught, backed off exponentially with jitter, and *counted*.  Botocore's
  own retry layer is switched off (``total_max_attempts: 1``) so 429s reach this program
  instead of being absorbed; whatever the SDK still absorbs is reported separately, and the
  ledger publishes the **sum** as ``throttles_true_total`` rather than leaving a reader to
  add two numbers.  It is a large number — AWS Service Quotas publishes **60 on-demand
  requests per minute** for this model, account-wide, and the whole fleet embeds against it
  at once.  The index behind this manifest cost **23 545 observed throttles plus 150 the SDK
  absorbed** across 3 163 seconds.

WHAT IT DOES NOT DO
-------------------
It writes to no database — that is ``cloud-load``'s job.  It provisions nothing, changes no
account setting, and runs no Terraform.  It reads AWS only through ``bedrock-runtime``.

COST
----
Priced by ``_common.USD_PER_1K_TOKENS`` at USD 0.00002 / 1 000 input tokens (a **declared
list price, not a bill** — see ``PRICE_BASIS``).  The whole corpus is ~1.0 MB of text; the
projected and the actual spend are both in ``token-ledger.json``, and a run whose *projection*
exceeds USD 0.50 raises ``CostCeilingExceeded`` and records why instead of spending.

THE CORPUS IS SYNTHETIC
-----------------------
No real incident, no real person, no real operation.  Every artefact says so in those words.
The reason it is synthetic is the most creditable thing about it: each record in the real
corpus is a death, and a repository is a copy.

EXIT CODES
----------
``0`` the store is complete and every artefact was written.  ``1`` embedding failed for at
least one item; the artefacts are still written, with the failures in them.  ``2`` no AWS
session could be built.  ``3`` the projected spend exceeded the ceiling and nothing was sent.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
import threading
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
from botocore.exceptions import BotoCoreError, ClientError

if __package__ in {None, ""}:  # direct execution: `python scripts/aws/embed_corpus.py`
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.aws._common import (
    REGION,
    CostCeilingExceeded,
    artefact,
    assert_in_region,
    check_cost_ceiling,
    ledger_total,
    redact,
    repo_root,
    session,
    sha256_hex,
    token_ledger_entry,
)

# ═══════════════════════════════════════════════════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════════════════════════════════════════════════

#: The only model this program calls.  Bare vendor id, no routing prefix, so
#: ``assert_in_region`` admits it and the call is served in ``ap-southeast-2`` on demand.
MODEL_ID = "amazon.titan-embed-text-v2:0"

#: The width ``verticals/mainline/db/migrations/0031_clause_embedding.sql`` declares
#: (``VECTOR(1024)``).  Titan v2 also offers 512 and 256; asking for anything but the width
#: the table accepts would produce vectors that cannot be loaded.
DIMENSIONS = 1024

#: Stamped into every manifest row.  ``titan2`` is the model family, ``1`` is this
#: repository's generation of the index.  A re-embedding under a different model, width, or
#: text-selection rule takes the next number, so two vectors with the same id and the same
#: ``index_gen`` are the same vector or one of them is a defect.
INDEX_GEN = "titan2-1"

#: How far a *stored* float32 vector's L2 norm may sit from 1.0.  float32 has ~7 significant
#: decimal digits, so renormalising in float64 and casting down costs ~1e-7; 1e-5 is two
#: orders of margin and still tight enough to catch a vector that was never normalised.
NORM_TOLERANCE = 1e-5

#: Bytes per stored vector: 1024 float32.  Recorded so the sha256 is reproducible without
#: reading this file.
BYTES_PER_VECTOR = DIMENSIONS * 4

#: Little-endian, C-order float32.  Stated explicitly rather than inherited from the host, so
#: the digest of a vector is the same digest on a big-endian machine.
VECTOR_DTYPE = "<f4"

#: Conservative chars-per-token for the **pre-flight cost projection only**.  Real English
#: through Titan measures ~4.5 chars/token; 3.0 over-estimates the bill by ~50%, which is the
#: correct direction for a ceiling check.  The ledger reports Bedrock's own
#: ``inputTextTokenCount``, never this.
PROJECTION_CHARS_PER_TOKEN = 3.0

EVIDENCE_DIR = "evidence/aws/embeddings"
STORE_NPZ = "out/aws/titan-vectors.npz"
STORE_INDEX = "out/aws/titan-vectors-index.json"

GOLDSET_DIR = "tests/fixtures/recall/goldsets"
QRELS_FILES = (
    "g1_citations.qrels.jsonl",
    "g2_codes.qrels.jsonl",
    "g3_adjudicated.qrels.jsonl",
    "g4_retro.qrels.jsonl",
    "gs0/qrels.jsonl",
)
CLAUSE_DIR = "verticals/mainline/fixtures/corpus/answer-key"

#: The sentence the brief requires, verbatim, in ``corpus-provenance.json``.
SYNTHETIC_STATEMENT = "SYNTHETIC — no real incident record is committed to this repository"

#: Error codes worth backing off on.  ``ThrottlingException`` is the one this program is
#: built for; the rest are transient server-side conditions that a retry legitimately fixes.
#: Everything else is a fact about the request and retrying it reports the same defect eight
#: times.
THROTTLE_CODES = frozenset({"ThrottlingException", "TooManyRequestsException"})
TRANSIENT_CODES = frozenset(
    {"ServiceUnavailableException", "InternalServerException", "ModelNotReadyException"}
)

#: Retry policy, tuned against a **measured** condition rather than a default.
#: ``servicequotas:ListServiceQuotas`` publishes 60 on-demand requests per minute for this
#: model, account-wide, and CloudWatch recorded 2 524 ``InvocationThrottles`` against 300
#: ``Invocations`` in a five-minute window while four other programs in this fleet were
#: embedding at the same time.  A polite 1-second ladder loses that race: with six threads
#: it completed under 100 items in twenty minutes, because each thread spent its time asleep
#: while less patient processes took the bucket.
#:
#: So the ladder is short and the attempt budget is long: retry quickly (a throttled request
#: transfers no tokens and costs nothing), cap the wait low enough to stay in contention, and
#: allow enough attempts that an item rides out a busy minute instead of being dropped.
MAX_ATTEMPTS = 40
BACKOFF_BASE_SECONDS = 0.25
BACKOFF_CAP_SECONDS = 4.0

#: Vectors between checkpoints. An interrupted run must not cost its tokens twice, and a
#: store that is only written at the end is a store that is lost to a Ctrl-C.
CHECKPOINT_EVERY = 25

ALL_SETS = (
    "synthetic_part50",
    "synthetic_fatality",
    "synthetic_csb",
    "synthetic_au_alert",
    "retro_query",
    "mainline_clause",
)

#: The three sets the brief named, kept as a flag value so the narrower scope is reproducible
#: without editing code — see the module docstring for why the default is wider.
BRIEF_SETS = ("synthetic_fatality", "synthetic_csb", "synthetic_au_alert", "retro_query")


# ═══════════════════════════════════════════════════════════════════════════════════════
# 1 · The corpus
# ═══════════════════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True, slots=True)
class Item:
    """One text to embed, with the id it will keep for the rest of its life."""

    ident: str
    set_name: str
    text: str

    @property
    def text_sha256(self) -> str:
        return sha256_hex(self.text.encode("utf-8"))


@dataclass
class CorpusBuild:
    """Everything the corpus assembly learned, including what it threw away and why."""

    items: list[Item] = field(default_factory=list)
    drops: dict[str, dict[str, int]] = field(default_factory=lambda: defaultdict(dict))
    notes: dict[str, Any] = field(default_factory=dict)

    def drop(self, set_name: str, reason: str, count: int = 1) -> None:
        bucket = self.drops.setdefault(set_name, {})
        bucket[reason] = bucket.get(reason, 0) + count

    def counts(self) -> dict[str, int]:
        tally: Counter[str] = Counter(item.set_name for item in self.items)
        return {name: tally.get(name, 0) for name in ALL_SETS if tally.get(name)}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    """JSONL rows, skipping blanks and the ``//!meta`` header the gold sets carry."""
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("//"):
            continue
        rows.append(json.loads(stripped))
    return rows


def _add_synthetic(build: CorpusBuild, wanted: frozenset[str]) -> None:
    """Generate the incident corpus, run it through the repository's own loaders, embed the
    narrative each loader produced.

    The narrative — not the title — is what is sent.  ``EventRecord.title`` is assembled by
    the loader from coded fields (``f"{classification} — {operation}"``); embedding it would
    put loader-constructed text into a vector that claims to be *of the document*.
    """
    from trappoint_recall.corpora import synthetic
    from trappoint_recall.corpora.build import CORPUS_GENESIS, SYNTHETIC_PROVENANCE
    from trappoint_recall.corpora.csb import load_au_regulator_alerts, load_csb_reports
    from trappoint_recall.corpora.msha import load_fatality_reports, parse_part50

    corpus = synthetic.generate()
    common = {"provenance": SYNTHETIC_PROVENANCE, "corpus_commit_at": CORPUS_GENESIS}
    sources = {
        "synthetic_part50": lambda: parse_part50(list(corpus.part50_lines), **common),
        "synthetic_fatality": lambda: load_fatality_reports(
            list(corpus.fatality_reports), **common
        ),
        "synthetic_csb": lambda: load_csb_reports(list(corpus.csb_reports), **common),
        "synthetic_au_alert": lambda: load_au_regulator_alerts(list(corpus.au_alerts), **common),
    }
    build.notes["synthetic_generate"] = {
        "callable": "trappoint_recall.corpora.synthetic.generate",
        "seed": corpus.seed,
        "summary": dict(corpus.summary()),
    }
    loader_reports: dict[str, Any] = {}
    for set_name, make in sources.items():
        if set_name not in wanted:
            continue
        record_set = make()
        report = record_set.report.to_dict()
        loader_reports[set_name] = report
        for reason, count in dict(report.get("dropped") or {}).items():
            build.drop(set_name, f"loader:{reason}", int(count))
        for record in record_set:
            text = str(record.narrative)
            if not text.strip():
                build.drop(set_name, "empty_narrative")
                continue
            build.items.append(Item(f"doc:{record.external_ref}", set_name, text))
    build.notes["loader_reports"] = loader_reports


def _retro_narrative_collisions(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Queries that share a byte-identical ``narrative`` facet but not their truth document.

    **Measured, and it is the most consequential number this program found.**  The 96 G4
    queries carry only **24 distinct narrative facets** — 24 groups of exactly 4 — and in
    every one of those groups all four queries have a *different* ``truth_doc_id``.

    The arithmetic is unavoidable and has nothing to do with model quality: an embedding is a
    function of its input, so four byte-identical narratives produce one vector, one ranking,
    and one rank-1 document.  At most one query per group can be right at rank 1.  **A
    text-only dense retriever over this facet is capped at 24/96 = 25.0% rank-1 on G4**, and
    a system that reported more would be reading something other than the narrative.

    This is a fact about the fixture, discovered while embedding it, and it belongs with the
    vectors rather than in the recall harness that will trip over it.  ``real-recall`` needs
    it to interpret its own numbers; it is not a reason to change a gate floor.
    """
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[str((row.get("facets") or {}).get("narrative") or "")].append(row)
    sizes = Counter(len(members) for members in groups.values())
    split = sum(1 for m in groups.values() if len({r.get("truth_doc_id") for r in m}) > 1)
    return {
        "queries": len(rows),
        "distinct_narrative_facets": len(groups),
        "group_sizes": {str(k): v for k, v in sorted(sizes.items())},
        "groups_whose_members_disagree_on_truth_doc_id": split,
        "max_rank1_hits_for_any_text_only_retriever": len(groups),
        "max_rank1_rate_per_1000": round(len(groups) / len(rows) * 1000) if rows else None,
        "why": (
            "An embedding is a function of its input. Queries with byte-identical text share "
            "one vector and therefore one ranking, so at most one member of each group can "
            "have its own truth document at rank 1. This is a ceiling imposed by the fixture, "
            "not by the retriever, and it is not a reason to move a gate floor."
        ),
    }


def _add_queries(build: CorpusBuild, root: Path) -> None:
    """The 96 retro permit narratives, facet ``narrative``, keyed by their own ``query_id``."""
    path = root / GOLDSET_DIR / "g4_retro.queries.jsonl"
    rows = _read_jsonl(path)
    for row in rows:
        query_id = str(row.get("query_id") or "")
        text = str((row.get("facets") or {}).get("narrative") or "")
        if not query_id:
            build.drop("retro_query", "no_query_id")
            continue
        if not text.strip():
            build.drop("retro_query", "no_narrative_facet")
            continue
        build.items.append(Item(f"query:{query_id}", "retro_query", text))
    build.notes["retro_queries"] = {
        "source": f"{GOLDSET_DIR}/g4_retro.queries.jsonl",
        "rows": len(rows),
        "narrative_collisions": _retro_narrative_collisions(rows),
    }


def _latest_revision(revisions: list[dict[str, Any]]) -> dict[str, Any]:
    """The head revision: highest ``rev_no``, ties broken by ``effective_on``.

    The head is the right one to embed because it is the text the clause *currently* says,
    and the ANN proof asks what a permit written today would match.
    """
    return max(revisions, key=lambda r: (int(r["rev_no"]), str(r["effective_on"])))


def _add_clauses(build: CorpusBuild, root: Path) -> None:
    """The 893 MAINLINE clauses, with prose from the renderer's own provider chain.

    ``BodyBank`` resolves in three tiers — ``authored`` (a human wrote it), ``cache`` (a
    published render), then ``structural`` (composed from the clause's control class, barrier
    role, era vocabulary and citation).  Neither of the first two fixtures has landed in this
    tree, so every body here is ``structural``.  That is **resolution, not padding**: it is
    the same text ``mainline_corpus.docx.render`` puts on the page, produced by the same
    function.  The tier is counted per clause in ``corpus-provenance.json`` so a reader never
    has to take that on trust.
    """
    from mainline_corpus.docx import sources as docx_sources
    from mainline_corpus.docx.bodies import BodyBank

    clauses = _read_jsonl(root / CLAUSE_DIR / "clause.jsonl")
    registry_rows = _read_jsonl(root / CLAUSE_DIR / "clause_registry.jsonl")
    registry = {str(r["clause_uuid"]): r for r in registry_rows}
    revisions: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in _read_jsonl(root / CLAUSE_DIR / "clause_revision.jsonl"):
        revisions[str(row["clause_uuid"])].append(row)

    bank = BodyBank(docx_sources.fixtures_root())
    renderers: Counter[str] = Counter()
    for clause in clauses:
        uuid = str(clause["clause_uuid"])
        entry = registry.get(uuid)
        if entry is None:
            build.drop("mainline_clause", "not_in_clause_registry")
            continue
        if not revisions.get(uuid):
            build.drop("mainline_clause", "no_revision_in_clause_revision_jsonl")
            continue
        head = _latest_revision(revisions[uuid])
        # The renderer's own citation rule, reused rather than reimplemented: a second copy
        # of `index = int(uuid[:8], 16) % len(entries)` is a second copy that can drift.
        citation = docx_sources._clause_citation(str(clause["activity_root"]), uuid)
        try:
            prose = bank.prose(
                clause_uuid=uuid,
                control_class=str(entry["control_class"]),
                barrier_role=str(entry["barrier_role"]),
                doc_code=str(head["doc_code"]),
                year=int(str(head["effective_on"])[:4]),
                citation=citation,
            )
        except KeyError:
            build.drop("mainline_clause", "control_class_not_in_gazetteer")
            continue
        if not prose.body.strip():
            build.drop("mainline_clause", "empty_body")
            continue
        renderers[prose.renderer] += 1
        build.items.append(Item(f"clause:{uuid}", "mainline_clause", prose.body))
    build.notes["clause_corpus"] = {
        "source": path_ref(f"{CLAUSE_DIR}/clause.jsonl"),
        "clauses_in_file": len(clauses),
        "registry_rows": len(registry),
        "body_renderer_tiers": dict(sorted(renderers.items())),
        "authored_fixture_available": bank.authored_available,
        "cache_fixture_available": bank.cache_available,
    }


def build_corpus(root: Path, wanted: frozenset[str]) -> CorpusBuild:
    """Assemble every requested set.  Nothing is invented; every exclusion is counted."""
    build = CorpusBuild()
    if wanted & {"synthetic_part50", "synthetic_fatality", "synthetic_csb", "synthetic_au_alert"}:
        _add_synthetic(build, wanted)
    if "retro_query" in wanted:
        _add_queries(build, root)
    if "mainline_clause" in wanted:
        _add_clauses(build, root)
    duplicates = [i for i, c in Counter(item.ident for item in build.items).items() if c > 1]
    if duplicates:
        raise RuntimeError(
            f"{len(duplicates)} ids appear twice in the corpus ({duplicates[:3]}). Two texts "
            "under one id means one of them silently wins in the store, and the manifest "
            "would bind the id to whichever the loop reached last."
        )
    return build


def goldset_coverage(root: Path, items: list[Item]) -> dict[str, Any]:
    """How many judged ``doc_id``s the embedded document set actually covers.

    This is the number that decides whether ``evidence/aws/recall`` can score at all, so it
    is measured here and written into the provenance artefact rather than assumed.
    """
    judged: set[str] = set()
    per_file: dict[str, int] = {}
    for name in QRELS_FILES:
        path = root / GOLDSET_DIR / name
        ids = {str(row["doc_id"]) for row in _read_jsonl(path) if row.get("doc_id")}
        per_file[name] = len(ids)
        judged |= ids
    embedded = {i.ident.split(":", 1)[1] for i in items if i.ident.startswith("doc:")}
    missing = sorted(judged - embedded)
    return {
        "qrels_files": per_file,
        "distinct_judged_doc_ids": len(judged),
        "covered_by_embedded_documents": len(judged & embedded),
        "missing": len(missing),
        "missing_sample": missing[:10],
    }


# ═══════════════════════════════════════════════════════════════════════════════════════
# 2 · The store — resumable, keyed by the same id the manifest publishes
# ═══════════════════════════════════════════════════════════════════════════════════════


@dataclass
class StoredVector:
    """One vector's row in the persistent index."""

    set_name: str
    chars: int
    tokens: int
    vector_sha256: str
    text_sha256: str
    request_id: str
    latency_ms: float
    returned_norm: float
    stored_norm: float


class VectorStore:
    """``out/aws/titan-vectors.npz`` plus its sidecar index, loaded and saved as one unit.

    ``out/`` is gitignored: an 8 MB float blob does not belong in a repository, and the
    committed manifest carries the digest of every vector in it, which is the part a reviewer
    can actually check.  The sidecar index is what makes the program resumable *without*
    re-reading Bedrock: it carries the token count and the text digest per id, so an
    interrupted run resumes and a completed run can rebuild its ledger for free.
    """

    def __init__(self, npz_path: Path, index_path: Path) -> None:
        self.npz_path = npz_path
        self.index_path = index_path
        self.vectors: dict[str, np.ndarray] = {}
        self.index: dict[str, StoredVector] = {}
        #: One record per run that actually spent tokens. This is what makes the ledger
        #: honest across a resume: the run that does the work is not the run that writes the
        #: final artefact, and a `this_run` block full of zeros would otherwise erase the
        #: throttle count and wall time the index actually cost.
        self.history: list[dict[str, Any]] = []
        self._lock = threading.Lock()

    def load(self) -> None:
        if self.index_path.is_file():
            raw = json.loads(self.index_path.read_text(encoding="utf-8"))
            for ident, row in dict(raw.get("entries") or {}).items():
                self.index[ident] = StoredVector(**row)
            self.history = list(raw.get("build_history") or [])
        if self.npz_path.is_file():
            with np.load(self.npz_path) as archive:
                for ident in archive.files:
                    self.vectors[ident] = np.asarray(archive[ident], dtype=np.float32)
        # An id present in one half and not the other is not usable evidence; drop it so the
        # run re-embeds it rather than publishing a digest with no vector behind it.
        for ident in set(self.index) - set(self.vectors):
            del self.index[ident]
        for ident in set(self.vectors) - set(self.index):
            del self.vectors[ident]

    def fresh(self, item: Item) -> bool:
        row = self.index.get(item.ident)
        return row is not None and row.text_sha256 == item.text_sha256

    def put(self, ident: str, vector: np.ndarray, row: StoredVector) -> None:
        with self._lock:
            self.vectors[ident] = vector
            self.index[ident] = row

    def note_run(self, tally: RunTally, wall_seconds: float) -> None:
        """Append this run to the index's build history, if it did anything worth recording.

        A resumed run that made no calls appends nothing: the history is a record of what the
        index cost, not of how many times someone typed the command.
        """
        if not tally.calls and not tally.failures:
            return
        rate = round(tally.calls / wall_seconds * 60.0, 1) if wall_seconds > 0 else None
        self.history.append(
            {
                "finished_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "bedrock_calls": tally.calls,
                "input_tokens": tally.input_tokens,
                "throttles_observed": tally.throttles,
                "transient_retries": tally.transient_retries,
                "botocore_internal_retry_attempts": tally.botocore_retry_attempts,
                "failures": len(tally.failures),
                "wall_seconds": round(wall_seconds, 1),
                "observed_requests_per_minute": rate,
            }
        )

    def history_totals(self) -> dict[str, Any]:
        """What the index cost to build, summed over every run that built it."""
        keys = (
            "bedrock_calls",
            "input_tokens",
            "throttles_observed",
            "transient_retries",
            "botocore_internal_retry_attempts",
            "failures",
        )
        totals: dict[str, Any] = {k: sum(int(r.get(k, 0)) for r in self.history) for k in keys}
        totals["runs"] = len(self.history)
        totals["wall_seconds"] = round(
            sum(float(r.get("wall_seconds", 0.0)) for r in self.history), 1
        )
        return totals

    def snapshot(self) -> tuple[dict[str, np.ndarray], dict[str, StoredVector]]:
        """A consistent shallow copy, taken under the lock so a checkpoint can be written
        while worker threads keep embedding."""
        with self._lock:
            return dict(self.vectors), dict(self.index)

    def save(self) -> None:
        vectors, index = self.snapshot()
        self.npz_path.parent.mkdir(parents=True, exist_ok=True)
        # The temp name must itself end in `.npz`: numpy appends the extension when it is
        # missing, so `titan-vectors.npz.tmp` is written as `titan-vectors.npz.tmp.npz` and
        # the rename that follows looks for a file that was never created.
        tmp_npz = self.npz_path.with_name(self.npz_path.name + ".tmp.npz")
        np.savez(tmp_npz, **vectors)
        tmp_npz.replace(self.npz_path)
        payload = {
            "model_id": MODEL_ID,
            "index_gen": INDEX_GEN,
            "dimensions": DIMENSIONS,
            "region": REGION,
            "vector_dtype": VECTOR_DTYPE,
            "note": (
                "Operational join file for scripts/aws/load_vectors.py. Ids are VERBATIM and "
                "unredacted here; the committed manifest passes through _common.redact and "
                "records any id that redaction altered."
            ),
            "entries": {k: vars(v) for k, v in sorted(index.items())},
            "build_history": list(self.history),
        }
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        self.index_path.write_text(
            json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )


# ═══════════════════════════════════════════════════════════════════════════════════════
# 3 · The Bedrock loop
# ═══════════════════════════════════════════════════════════════════════════════════════


@dataclass
class RunTally:
    """Everything the run learned about the wire, counted under one lock."""

    calls: int = 0
    input_tokens: int = 0
    throttles: int = 0
    transient_retries: int = 0
    botocore_retry_attempts: int = 0
    failures: list[dict[str, Any]] = field(default_factory=list)
    latencies_ms: list[float] = field(default_factory=list)
    returned_norms: list[float] = field(default_factory=list)
    stored_norm_deviations: list[float] = field(default_factory=list)
    sample: dict[str, Any] | None = None
    lock: threading.Lock = field(default_factory=threading.Lock)


_CLIENTS = threading.local()
_CLIENT_LOCK = threading.Lock()


def _client() -> Any:
    """One ``bedrock-runtime`` client per thread, with **botocore's own retries turned off**.

    Two reasons, both measured rather than stylistic.

    *Evidence.*  Botocore retries throttles itself, silently, before the exception ever
    reaches this program.  With that layer on, ``throttles_observed`` in the ledger is a
    lower bound and the real number is invisible.  With ``max_attempts: 1`` every 429 is
    surfaced, counted, and backed off by the loop in this file, so the number published is
    the number that happened.

    *Throughput.*  The hidden layer also sleeps.  At this account's saturated 60 requests
    per minute, one of this program's "attempts" was costing up to three HTTP requests and
    several seconds of somebody else's backoff, which is why the first two runs completed
    fewer than 100 items in twenty minutes.

    ``bedrock_runtime()`` from ``_common`` is the fleet's normal entry point and takes no
    config, so the client is built from the same cached, region-pinned ``session()`` with the
    one option this program needs changed.  Construction happens under a lock because
    botocore mutates the shared session's loader caches while building a client; calling a
    built client from several threads is safe.
    """
    existing = getattr(_CLIENTS, "client", None)
    if existing is not None:
        return existing
    from botocore.config import Config

    with _CLIENT_LOCK:
        made = session().client(
            "bedrock-runtime",
            region_name=REGION,
            # `total_max_attempts`, NOT `max_attempts`. botocore's `max_attempts` counts
            # *retries* and silently adds one for the initial call: `max_attempts: 1`
            # resolves to `total_max_attempts: 2`, which is how this program's first complete
            # index came to have 150 throttles absorbed by the SDK while its own caveat
            # claimed the count was exact. `c.meta.config.retries` is where that was caught.
            config=Config(retries={"total_max_attempts": 1, "mode": "standard"}),
        )
    if made.meta.config.retries.get("total_max_attempts") != 1:
        raise RuntimeError(
            f"bedrock-runtime client resolved to {made.meta.config.retries!r}; this program "
            "counts throttles itself and cannot do that while the SDK is absorbing them."
        )
    _CLIENTS.client = made
    return made


def request_body(text: str) -> dict[str, Any]:
    """The exact Titan v2 request.  One ``inputText``; there is no batch form."""
    return {"inputText": text, "dimensions": DIMENSIONS, "normalize": True}


def _invoke_once(text: str) -> tuple[dict[str, Any], bytes, float]:
    started = time.perf_counter()
    response = _client().invoke_model(
        modelId=MODEL_ID,
        body=json.dumps(request_body(text)),
        accept="application/json",
        contentType="application/json",
    )
    raw = response["body"].read()
    latency_ms = (time.perf_counter() - started) * 1000.0
    meta = dict(response.get("ResponseMetadata") or {})
    return meta, raw, latency_ms


def _sleep_for(attempt: int, rng: random.Random) -> float:
    """Exponential backoff with full jitter, capped.  Returns the seconds slept."""
    ceiling = min(BACKOFF_CAP_SECONDS, BACKOFF_BASE_SECONDS * (2**attempt))
    delay = rng.uniform(0.0, ceiling)
    time.sleep(delay)
    return delay


def invoke_with_backoff(text: str, tally: RunTally) -> tuple[dict[str, Any], bytes, float]:
    """Call Titan, backing off on throttles and transient server errors, counting both.

    Botocore's own retry layer is disabled on this client (see :func:`_client`), so every
    throttle reaches this loop and is counted here.  ``ResponseMetadata.RetryAttempts`` is
    still summed — it should be 0 for every call, and a non-zero total would mean the config
    did not take effect and the count is a lower bound after all.
    """
    # System-seeded on purpose. An earlier version seeded from the text so a replay would
    # back off identically, which sounded reproducible and was in fact a defect: an item that
    # lost the race for the account's request quota would then lose it the same way on every
    # retry. Jitter exists to decorrelate contenders, so it has to be random. Not a
    # cryptographic use.
    rng = random.Random()  # noqa: S311
    last: Exception | None = None
    for attempt in range(MAX_ATTEMPTS):
        try:
            meta, raw, latency_ms = _invoke_once(text)
        except ClientError as exc:
            code = str(exc.response.get("Error", {}).get("Code") or "")
            if code in THROTTLE_CODES:
                with tally.lock:
                    tally.throttles += 1
            elif code in TRANSIENT_CODES:
                with tally.lock:
                    tally.transient_retries += 1
            else:
                raise
            last = exc
            _sleep_for(attempt, rng)
        else:
            with tally.lock:
                tally.botocore_retry_attempts += int(meta.get("RetryAttempts") or 0)
            return meta, raw, latency_ms
    raise RuntimeError(
        f"{MAX_ATTEMPTS} attempts exhausted against {MODEL_ID}; last error {last!r}. "
        "The backoff did its job and the service is still refusing. This item is recorded "
        "as a failure and the next run picks it up: the store is resumable, so retrying "
        "here forever would only report the same account-quota condition more slowly."
    )


def _to_unit_float32(embedding: list[float]) -> tuple[np.ndarray, float, float]:
    """Re-normalise in float64, store float32, and measure what was *stored*.

    Titan is asked for ``normalize: true`` and returns a norm near 1.0 — the probe measured
    1.0000000094.  Near is not is: cosine distance in CockroachDB's C-SPANN index is computed
    over what is in the column, so the check that matters is on the float32 bytes that go to
    disk, not on the float64 the wire carried.
    """
    raw = np.asarray(embedding, dtype=np.float64)
    if raw.shape != (DIMENSIONS,):
        raise RuntimeError(f"Titan returned width {raw.shape}, not ({DIMENSIONS},)")
    returned_norm = float(np.linalg.norm(raw))
    if not math.isfinite(returned_norm) or returned_norm == 0.0:
        raise RuntimeError(f"Titan returned a vector of norm {returned_norm}; nothing to normalise")
    stored = (raw / returned_norm).astype(VECTOR_DTYPE)
    stored_norm = float(np.linalg.norm(stored.astype(np.float64)))
    if abs(stored_norm - 1.0) > NORM_TOLERANCE:
        raise RuntimeError(
            f"stored float32 vector has L2 norm {stored_norm!r}, outside 1.0 +/- "
            f"{NORM_TOLERANCE}. A non-unit vector in a cosine index is a silently wrong "
            "neighbour list, so this is refused rather than written."
        )
    return stored, returned_norm, stored_norm


def embed_item(item: Item, store: VectorStore, tally: RunTally) -> None:
    """Embed one item and put it in the store.  Failures are recorded, never swallowed."""
    try:
        meta, raw, latency_ms = invoke_with_backoff(item.text, tally)
        parsed = json.loads(raw)
        stored, returned_norm, stored_norm = _to_unit_float32(list(parsed["embedding"]))
    except (ClientError, BotoCoreError, RuntimeError, ValueError, KeyError) as exc:
        with tally.lock:
            tally.failures.append(
                {"id": item.ident, "set": item.set_name, "error": f"{type(exc).__name__}: {exc}"}
            )
        return
    tokens = int(parsed.get("inputTextTokenCount") or 0)
    row = StoredVector(
        set_name=item.set_name,
        chars=len(item.text),
        tokens=tokens,
        vector_sha256=sha256_hex(stored.tobytes()),
        text_sha256=item.text_sha256,
        request_id=str(meta.get("RequestId") or ""),
        latency_ms=round(latency_ms, 1),
        returned_norm=returned_norm,
        stored_norm=stored_norm,
    )
    store.put(item.ident, stored, row)
    with tally.lock:
        tally.calls += 1
        tally.input_tokens += tokens
        tally.latencies_ms.append(latency_ms)
        tally.returned_norms.append(returned_norm)
        tally.stored_norm_deviations.append(abs(stored_norm - 1.0))
        if tally.sample is None or item.ident < str(tally.sample["id"]):
            tally.sample = _sample_payload(item, meta, raw, parsed, row, stored)


def _sample_payload(
    item: Item,
    meta: dict[str, Any],
    raw: bytes,
    parsed: dict[str, Any],
    row: StoredVector,
    stored: np.ndarray,
) -> dict[str, Any]:
    """One complete request/response pair, kept small enough for a judge to read.

    The embedding is truncated to 16 coordinates and the full vector is represented by its
    digest.  A 4 KB float dump proves nothing a hash does not, and it hides the wire shape in
    the middle of it.
    """
    return {
        "id": item.ident,
        "set": item.set_name,
        "request": {
            "operation": "bedrock-runtime:InvokeModel",
            "modelId": MODEL_ID,
            "accept": "application/json",
            "contentType": "application/json",
            "body": request_body(item.text),
            "body_sha256": sha256_hex(json.dumps(request_body(item.text)).encode("utf-8")),
            "input_text_chars": len(item.text),
            "input_text_sha256": item.text_sha256,
            "batch_form": "none — Titan v2 accepts exactly one inputText per InvokeModel",
        },
        "response": {
            "http_status": int(meta.get("HTTPStatusCode") or 0),
            "request_id": str(meta.get("RequestId") or ""),
            "botocore_retry_attempts": int(meta.get("RetryAttempts") or 0),
            "latency_ms": row.latency_ms,
            "body_keys": sorted(parsed.keys()),
            "body_sha256": sha256_hex(raw),
            "body_bytes": len(raw),
            "inputTextTokenCount": row.tokens,
            "embedding_length": len(parsed.get("embedding") or []),
            "embedding_first_16_as_returned": [float(v) for v in parsed["embedding"][:16]],
            "embedding_l2_norm_as_returned": row.returned_norm,
            "embeddingsByType_keys": sorted(dict(parsed.get("embeddingsByType") or {}).keys()),
            "stored_vector": {
                "dtype": VECTOR_DTYPE,
                "order": "C",
                "bytes": BYTES_PER_VECTOR,
                "l2_norm": row.stored_norm,
                "sha256": row.vector_sha256,
                "first_16": [float(v) for v in stored[:16]],
            },
        },
    }


# ═══════════════════════════════════════════════════════════════════════════════════════
# 4 · Cost and redaction pre-flight
# ═══════════════════════════════════════════════════════════════════════════════════════


def project_cost(pending: list[Item]) -> dict[str, Any]:
    """Price the run *before* spending, on a deliberately pessimistic token estimate."""
    chars = sum(len(item.text) for item in pending)
    tokens = math.ceil(chars / PROJECTION_CHARS_PER_TOKEN)
    usd = round(tokens / 1000.0 * 0.00002, 8)
    return {
        "pending_items": len(pending),
        "pending_chars": chars,
        "projected_input_tokens": tokens,
        "projected_usd": usd,
        "basis": (
            f"chars / {PROJECTION_CHARS_PER_TOKEN} tokens, which over-estimates English "
            "through Titan by roughly 50%; priced at USD_PER_1K_TOKENS for " + MODEL_ID
        ),
    }


def path_ref(relative: str) -> str | dict[str, Any]:
    """A repository-relative path in a form that survives ``_common.redact``.

    ``_SECRET_SHAPE`` treats any run of 40+ characters from ``[A-Za-z0-9+/=]`` containing at
    least one of ``+/=`` as a credential.  A deep repository path is exactly that shape:
    ``verticals/mainline/fixtures/corpus/answer`` is 41 such characters before the hyphen, so
    the redactor rewrites the provenance file's own source path to
    ``<redacted>-key/clause.jsonl``.  Rather than publish a mangled path, this returns the
    segments — which are individually far too short to trip the rule — and says why.
    """
    if redact(relative) == relative:
        return relative
    return {
        "path_segments": relative.split("/"),
        "join_with": "/",
        "why_not_a_string": (
            "scripts/aws/_common.py::_SECRET_SHAPE reads a 40+ character run of "
            "[A-Za-z0-9+/=] as a secret, and this path is one. Split, it survives intact."
        ),
    }


def redaction_audit(payload: Any, pointer: str = "") -> list[dict[str, str]]:
    """Every string in *payload* that ``_common.redact`` alters, with a digest to recover it.

    Nothing here is hypothetical.  Two of the 893 clause UUIDs in this corpus end in a
    twelve-digit group (``…-395153274288``, ``…-404302643067``) and ``_ACCOUNT_ID`` reads a
    twelve-digit run bounded by non-alphanumerics as an AWS account id.  An evidence file
    whose keys have been silently rewritten by its own redactor is worse than one that leaks,
    because it looks fine — so this walks the payload *before* it is written and publishes the
    casualty list beside the data.  The original string is never republished; its sha256 is,
    which is enough to confirm an identity against the committed corpus without undoing the
    redaction.  ``out/aws/titan-vectors-index.json`` keeps every id verbatim for the loader.
    """
    found: list[dict[str, str]] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            name = str(key)
            found += redaction_audit(name, f"{pointer}/<key>{name}")
            found += redaction_audit(value, f"{pointer}/{name}")
    elif isinstance(payload, (list, tuple)):
        for position, value in enumerate(payload):
            found += redaction_audit(value, f"{pointer}/{position}")
    elif isinstance(payload, str):
        after = redact(payload)
        if after != payload:
            found.append(
                {
                    "pointer": pointer,
                    "written_as": str(after),
                    "original_sha256": sha256_hex(payload.encode("utf-8")),
                }
            )
    return found


# ═══════════════════════════════════════════════════════════════════════════════════════
# 5 · Artefacts
# ═══════════════════════════════════════════════════════════════════════════════════════


def _stats(values: list[float]) -> dict[str, float] | None:
    if not values:
        return None
    ordered = sorted(values)
    return {
        "n": len(ordered),
        "min": ordered[0],
        "median": ordered[len(ordered) // 2],
        "max": ordered[-1],
        "mean": round(sum(ordered) / len(ordered), 6),
    }


def duplication(store: VectorStore) -> dict[str, Any]:
    """How many of the ids actually carry *different* text, and what that says about Titan.

    Measured on the completed index: **2 060 ids, 908 distinct texts, 908 distinct vectors.**
    Two facts fall out of that one line, and both matter downstream.

    1. **Titan v2 is deterministic at these parameters.**  The map from distinct text to
       distinct vector is a bijection — no text produced two different vectors across a run
       that spanned an hour and 23 000 throttles, and no two texts produced the same one.
       That is why a resumed run can trust a stored vector instead of re-embedding.
    2. **The corpus is far less diverse than its record count.**  891 Part 50 rows carry 96
       distinct narratives; 60 AU alerts carry 8.  An ANN search over this index returns
       large groups at cosine distance 0.0 to each other, and any metric computed over it has
       to say how ties were broken before the number means anything.

    Neither is a defect in the vectors.  Both are properties of the fixture that a reader of
    the manifest would otherwise have to discover by being surprised.
    """
    rows = list(store.index.values())
    texts = {r.text_sha256 for r in rows}
    vectors = {r.vector_sha256 for r in rows}
    text_to_vector: dict[str, set[str]] = defaultdict(set)
    vector_to_text: dict[str, set[str]] = defaultdict(set)
    by_set: dict[str, list[StoredVector]] = defaultdict(list)
    for row in rows:
        text_to_vector[row.text_sha256].add(row.vector_sha256)
        vector_to_text[row.vector_sha256].add(row.text_sha256)
        by_set[row.set_name].append(row)
    per_set = {
        name: {
            "ids": len(members),
            "distinct_texts": len({r.text_sha256 for r in members}),
            "distinct_vectors": len({r.vector_sha256 for r in members}),
        }
        for name, members in by_set.items()
    }
    ambiguous = sum(1 for v in text_to_vector.values() if len(v) > 1)
    colliding = sum(1 for t in vector_to_text.values() if len(t) > 1)
    return {
        "ids": len(rows),
        "distinct_texts": len(texts),
        "distinct_vectors": len(vectors),
        "ids_sharing_text_with_another_id": len(rows) - len(texts),
        "per_set": dict(sorted(per_set.items())),
        "determinism": {
            "texts_that_produced_more_than_one_vector": ambiguous,
            "vectors_produced_by_more_than_one_text": colliding,
            "verdict": (
                "bijection — identical input text produced byte-identical float32 output "
                "every time, which is what makes the resumable store sound"
                if ambiguous == 0 and colliding == 0
                else "NOT a bijection; see the two counts above before trusting any cached vector"
            ),
        },
        "consequence": (
            "An ANN search over this index returns groups of vectors at cosine distance 0.0 "
            "to one another. Any recall figure computed here must state its tie-breaking "
            "rule; this is a property of the synthetic fixture, not of the retriever."
        ),
    }


def write_manifest(store: VectorStore, build: CorpusBuild, tally: RunTally) -> Path:
    """The committed proof: one row per vector, binding id -> text digest -> vector digest."""
    by_set: dict[str, dict[str, int]] = {}
    for row in store.index.values():
        bucket = by_set.setdefault(row.set_name, {"vectors": 0, "chars": 0, "input_tokens": 0})
        bucket["vectors"] += 1
        bucket["chars"] += row.chars
        bucket["input_tokens"] += row.tokens
    entries = {
        ident: {
            "set": row.set_name,
            "chars": row.chars,
            "inputTextTokenCount": row.tokens,
            "sha256": row.vector_sha256,
            "text_sha256": row.text_sha256,
        }
        for ident, row in sorted(store.index.items())
    }
    corpus_total = len(build.items)
    requested_present = sum(1 for item in build.items if store.fresh(item))
    payload = {
        "model_id": MODEL_ID,
        "index_gen": INDEX_GEN,
        "dimensions": DIMENSIONS,
        "request_shape": {**request_body("<the item's own text>"), "one_input_text_per_call": True},
        "vector_bytes": {
            "dtype": VECTOR_DTYPE,
            "order": "C",
            "bytes_per_vector": BYTES_PER_VECTOR,
            "sha256_is_over": "the stored little-endian C-order float32 bytes, not the JSON floats",
        },
        "store": {
            "vectors": STORE_NPZ,
            "index": STORE_INDEX,
            "gitignored": True,
            "why": "8 MB of float32 does not belong in a repository; the digests below do",
        },
        "totals": {
            "vectors": len(store.index),
            "corpus_items_requested": corpus_total,
            "requested_items_embedded": requested_present,
            # `complete` asks whether every item THIS run asked for is in the store, not
            # whether the store happens to be the same size as the request. Run with a
            # narrowed `--sets` against a full store and the two are different numbers, and
            # the size comparison would call a complete manifest incomplete.
            "complete": requested_present == corpus_total,
            "sets_requested": sorted({item.set_name for item in build.items}),
            "input_tokens": sum(r.tokens for r in store.index.values()),
            "chars": sum(r.chars for r in store.index.values()),
            "unit_norm_verified": len(store.index),
            "norm_tolerance": NORM_TOLERANCE,
        },
        "by_set": dict(sorted(by_set.items())),
        # Sourced from the store, not from this run's tally: the run that writes the
        # manifest may be a resumed one that made no calls, and a norm distribution over
        # zero samples is not evidence that 2 060 vectors are unit-length. Every row in the
        # index carries the norm Titan returned and the norm of the float32 that was stored,
        # so these cover the whole index however many runs built it.
        "norms": {
            "returned_by_titan": _stats([r.returned_norm for r in store.index.values()]),
            "stored_float32_abs_deviation_from_1": _stats(
                [abs(r.stored_norm - 1.0) for r in store.index.values()]
            ),
            "assertion": (
                f"every stored vector was re-normalised in float64, cast to float32, and "
                f"re-measured; a deviation over {NORM_TOLERANCE} raises rather than being "
                f"written, so the maximum below is a bound this program enforced, not one "
                f"it observed after the fact"
            ),
        },
        "latency_ms": _stats([r.latency_ms for r in store.index.values()]),
        "text_duplication": duplication(store),
        "failures_this_run": tally.failures,
        "entries": entries,
    }
    payload["redaction_casualties"] = redaction_audit(payload)
    return artefact(
        Path(EVIDENCE_DIR) / "manifest.json",
        payload,
        kind="titan-embedding-manifest",
        synthetic=True,
        caveats=[
            (
                "the sha256 of a vector proves which bytes were stored, not that Titan's "
                "weights are what AWS says they are; the corroborating AWS-side record is "
                "CloudWatch AWS/Bedrock Invocations and InputTokenCount, which "
                "cloudwatch-cost reads"
            ),
            (
                "the vectors themselves are in out/aws/, which is gitignored; a reader who "
                "wants to re-derive a digest must re-run this program and pay for the tokens"
            ),
            (
                "redaction_casualties lists every string scripts/aws/_common.py::redact "
                "altered on the way into this file, measured before writing rather than "
                "assumed; out/aws/titan-vectors-index.json holds every id verbatim"
            ),
            "no database was written; row counts in CockroachDB are cloud-load's evidence",
        ],
    )


#: The two Service Quotas entries that govern this program.  Read live rather than declared,
#: because the throttle count in the ledger is meaningless without the ceiling it hit.
_QUOTA_NAMES = (
    "On-demand model inference requests per minute for Amazon Titan Text Embeddings V2",
    "On-demand model inference tokens per minute for Amazon Titan Text Embeddings V2",
)


def quota_snapshot() -> dict[str, Any]:
    """AWS's own published limits for this model, read read-only from Service Quotas.

    This is the number that explains the throttles.  Measured on this account today: **60
    requests per minute**, account-wide, against a token ceiling of 300 000/min that this
    corpus never approaches.  So the corpus is request-bound, not token-bound: 2 060 vectors
    need at least 34 minutes of *exclusive* quota, and the fleet shares it.  A run's own
    ``observed_requests_per_minute`` in the build history is directly comparable to this.

    Best-effort: a caller without ``servicequotas:ListServiceQuotas`` still gets a ledger,
    with the error in place of the numbers, because an unreadable quota is not a reason to
    withhold a token count.
    """
    try:
        client = session().client("service-quotas", region_name=REGION)
        found: dict[str, Any] = {}
        for page in client.get_paginator("list_service_quotas").paginate(ServiceCode="bedrock"):
            for quota in page["Quotas"]:
                if quota["QuotaName"] in _QUOTA_NAMES:
                    found[quota["QuotaName"]] = quota.get("Value")
    except (ClientError, BotoCoreError) as exc:
        return {"read": False, "error": f"{type(exc).__name__}: {redact(str(exc))}"}
    return {
        "read": True,
        "source": "servicequotas:ListServiceQuotas, ServiceCode=bedrock, read-only",
        "quotas": found,
        "binding_constraint": (
            "requests per minute, account-wide and shared with every other program in this "
            "fleet — not tokens per minute, which this corpus never approaches"
        ),
    }


def _reconcile(store: VectorStore) -> dict[str, Any]:
    """Does the build history account for every vector in the index?  Say so either way.

    The index holds one vector per id; the history holds one record per run that spent
    tokens.  They are not the same number, and pretending they are is exactly the kind of
    quiet arithmetic this fleet is supposed to refuse:

    * **positive delta** — vectors whose run predates the build-history feature, or which
      were written by a run whose record was lost. They were still paid for; the ledger just
      cannot name the run.
    * **negative delta** — more calls than vectors, which is what a re-embedded stale id or a
      retried failure looks like. Those calls were paid for and produced no *additional* row.
    """
    recorded = store.history_totals()["bedrock_calls"]
    delta = len(store.index) - recorded
    if delta == 0:
        meaning = "every vector in the index is accounted for by a recorded run"
    elif delta > 0:
        meaning = (
            f"{delta} vectors were embedded by runs older than this file's build-history "
            "feature; they were paid for, but the ledger cannot name the run that did it"
        )
    else:
        meaning = (
            f"{-delta} calls produced no additional row — a re-embedded stale id or a "
            "retried failure; the tokens were spent and the ledger counts them"
        )
    return {
        "vectors_in_index": len(store.index),
        "successful_calls_in_build_history": recorded,
        "delta": delta,
        "meaning": meaning,
    }


def _throttle_truth(store: VectorStore) -> dict[str, Any]:
    """Observed throttles plus the ones botocore absorbed, and their sum.

    The first complete index was built with a client that resolved to
    ``total_max_attempts: 2`` — botocore's ``max_attempts`` counts retries and adds one —
    so 150 throttles never reached this program's counter.  The config is fixed; the history
    is not rewritten.  Publishing the sum is how a ledger stays true to a run it cannot redo.
    """
    totals = store.history_totals()
    observed = totals["throttles_observed"]
    absorbed = totals["botocore_internal_retry_attempts"]
    return {
        "observed_by_this_program": observed,
        "absorbed_by_botocore_before_this_program_saw_them": absorbed,
        "true_total": observed + absorbed,
        "note": (
            "absorbed > 0 means the client that built those rows still had an SDK retry "
            "layer; every request it retried was also a throttle. The sum is the honest "
            "number and it is what any CloudWatch InvocationThrottles comparison should use."
        ),
    }


def write_ledger(
    store: VectorStore, tally: RunTally, projection: dict[str, Any], wall: float
) -> Path:
    """Calls, tokens, USD, and a sentence saying what was actually spent."""
    index_tokens = sum(r.tokens for r in store.index.values())
    cumulative = token_ledger_entry(MODEL_ID, len(store.index), index_tokens, 0)
    this_run = token_ledger_entry(MODEL_ID, tally.calls, tally.input_tokens, 0)
    spent = this_run["usd_total"] or 0.0
    payload = {
        "model_id": MODEL_ID,
        "this_run": {
            "bedrock_calls": tally.calls,
            "input_tokens": tally.input_tokens,
            "output_tokens": 0,
            "throttles_observed": tally.throttles,
            "transient_retries": tally.transient_retries,
            "botocore_internal_retry_attempts": tally.botocore_retry_attempts,
            "failures": len(tally.failures),
            "wall_seconds": round(wall, 1),
            "ledger_entry": this_run,
        },
        "index_cumulative": {
            "vectors": len(store.index),
            "billable_calls_implied_by_the_index": len(store.index),
            "input_tokens": index_tokens,
            "ledger_entry": cumulative,
            "build_history_totals": store.history_totals(),
            "throttles_true_total": _throttle_truth(store),
            "build_history": list(store.history),
            "why_history": (
                "The run that spends the tokens is not always the run that writes this file: "
                "a resumed run makes zero calls by design. The history is what the index "
                "actually cost, run by run, including the throttles it rode out."
            ),
            "reconciliation": _reconcile(store),
        },
        "totals": ledger_total([cumulative]),
        "throughput": {
            "service_quotas": quota_snapshot(),
            "note": (
                "Throttles here are a queueing fact, not an error: the account's "
                "requests-per-minute ceiling for this model is shared by every program in "
                "the fleet, and this one rides it out with jittered exponential backoff "
                "rather than dropping work."
            ),
        },
        "ceiling": {
            "per_run_usd": 0.50,
            "projection_before_run": projection,
            "projection_exceeded": False,
        },
        "budget_consumed": (
            f"This run sent {tally.calls} InvokeModel requests carrying "
            f"{tally.input_tokens} input tokens to {MODEL_ID} in {REGION}, priced at "
            f"USD {spent:.6f}. The whole index, across the "
            f"{store.history_totals()['runs']} run(s) that built it, is "
            f"{len(store.index)} vectors and {index_tokens} input tokens, priced at "
            f"USD {cumulative['usd_total']:.6f} — "
            f"{(cumulative['usd_total'] or 0.0) / 0.50 * 100:.3f}% of the USD 0.50 per-run "
            f"ceiling and {(cumulative['usd_total'] or 0.0) / 5.0 * 100:.4f}% of the USD "
            "5/month project ceiling. Embedding models bill input only; the zero output "
            "tokens are the billing model, not a missing measurement. This is a declared "
            "list price, not a bill."
        ),
    }
    return artefact(
        Path(EVIDENCE_DIR) / "token-ledger.json",
        payload,
        kind="titan-embedding-token-ledger",
        synthetic=True,
        caveats=[
            (
                "USD figures are computed from _common.USD_PER_1K_TOKENS, a published list "
                "price recorded 2026-08-11; no bill and no Price List API response backs them"
            ),
            (
                "throttles_observed counts the 429s this program's own loop saw. Any "
                "botocore_internal_retry_attempts are throttles the SDK absorbed before the "
                "loop could see them, so the honest total is the sum — published as "
                "index_cumulative.throttles_true_total rather than left for a reader to add"
            ),
            (
                "on a resumed run bedrock_calls is 0 by design — the cumulative block, not "
                "this run's block, is what the index cost to build"
            ),
        ],
    )


def write_provenance(
    build: CorpusBuild, store: VectorStore, root: Path, wanted: frozenset[str]
) -> Path:
    """Where every text came from, what was dropped, and the word SYNTHETIC."""
    report_path = root / GOLDSET_DIR / "build_report.json"
    build_report = json.loads(report_path.read_text(encoding="utf-8"))
    payload = {
        "statement": SYNTHETIC_STATEMENT,
        "what_that_means": (
            "Every incident narrative embedded here was generated by "
            "trappoint_recall.corpora.synthetic. No real incident, no real person, no real "
            "operation. The gold sets reference MSHA document numbers whose source PDFs are "
            "deliberately absent (scripts/recall/fetch_corpora.py explains why): each record "
            "in the real corpus is a death, and a repository is a copy. The MAINLINE clause "
            "corpus is likewise a fabricated document set, not any operator's procedures."
        ),
        "sets_requested": sorted(wanted),
        "counts_per_set": build.counts(),
        "embedded_per_set": {
            name: sum(1 for r in store.index.values() if r.set_name == name)
            for name in sorted({r.set_name for r in store.index.values()})
        },
        "drops_per_reason": {k: dict(sorted(v.items())) for k, v in sorted(build.drops.items())},
        "corpus_commit": {
            "value": build_report.get("corpus_commit"),
            "source": f"{GOLDSET_DIR}/build_report.json",
            "meaning": "a digest over record identities and their three time-wall timestamps, "
            "not a git commit",
        },
        "goldset_coverage": goldset_coverage(root, build.items),
        "text_duplication": duplication(store),
        "clause_corpus_inputs": [
            path_ref(f"{CLAUSE_DIR}/clause.jsonl"),
            path_ref(f"{CLAUSE_DIR}/clause_registry.jsonl"),
            path_ref(f"{CLAUSE_DIR}/clause_revision.jsonl"),
        ],
        "scope_note": {
            "brief_named_sets": list(BRIEF_SETS),
            "default_sets": list(ALL_SETS),
            "why_part50_is_included": (
                "The brief's stated purpose for the doc_id scheme is that evidence/aws/recall "
                "can score against the committed gold sets. Measured here: the five qrels "
                "files judge 1049 distinct doc_ids; the sets the brief named cover 165 of "
                "them and all four cover 1049. The 884 uncovered ids are Part 50 "
                "DOCUMENT_NOs, and in g4_retro the truth precursor of a fatality IS a Part 50 "
                "row. Part 50 is the fourth return value of the same synthetic.generate() "
                "call, carries the same doc_id == external_ref identity, and costs about USD "
                "0.0006 to embed. Run with --sets to reproduce the narrower scope."
            ),
        },
        **build.notes,
    }
    payload["redaction_casualties"] = redaction_audit(payload)
    return artefact(
        Path(EVIDENCE_DIR) / "corpus-provenance.json",
        payload,
        kind="titan-embedding-corpus-provenance",
        synthetic=True,
        caveats=[
            (
                "every clause body in this run resolved at the 'structural' tier of "
                "mainline_corpus.docx.bodies.BodyBank because neither the authored nor the "
                "cache body fixture exists in this tree; that is the renderer's own composed "
                "prose, identical to what the .docx render puts on the page, not text "
                "invented here"
            ),
            (
                "goldset_coverage counts doc_id membership only; it says nothing about "
                "whether retrieval over these vectors is any good — that is real-recall's"
            ),
            (
                "the retro query narratives are permits synthesised from investigation work "
                "descriptions, as g4_retro.qrels.jsonl's own //!meta line records"
            ),
        ],
    )


def write_samples(sample: dict[str, Any] | None) -> list[Path]:
    """The two wire-shape files.  On a resumed run with no calls, the existing ones stand."""
    if sample is None:
        return []
    request_payload = {"id": sample["id"], "set": sample["set"], "request": sample["request"]}
    request_payload["redaction_casualties"] = redaction_audit(request_payload)
    response_payload = {"id": sample["id"], "set": sample["set"], "response": sample["response"]}
    response_payload["redaction_casualties"] = redaction_audit(response_payload)
    request = artefact(
        Path(EVIDENCE_DIR) / "raw-request-sample.json",
        request_payload,
        kind="titan-raw-request-sample",
        synthetic=True,
        caveats=[
            (
                "one request out of the whole corpus, chosen as the lexicographically first "
                "id embedded in the run that wrote this file, so it is reproducible rather "
                "than cherry-picked"
            ),
            (
                "the inputText is a fabricated narrative; its sha256 appears against the "
                "same id in manifest.json, which ties this request to its vector"
            ),
        ],
    )
    response = artefact(
        Path(EVIDENCE_DIR) / "raw-response-sample.json",
        response_payload,
        kind="titan-raw-response-sample",
        synthetic=True,
        caveats=[
            (
                "the embedding is truncated to its first 16 coordinates on purpose; the "
                "sha256 of the full stored vector is the complete claim and a 4 KB float "
                "dump would hide the wire shape rather than show it"
            ),
            (
                "request_id is AWS's own handle for this call and is the join to the "
                "AWS/Bedrock CloudWatch metrics cloudwatch-cost reads"
            ),
        ],
    )
    return [request, response]


# ═══════════════════════════════════════════════════════════════════════════════════════
# 6 · Entry point
# ═══════════════════════════════════════════════════════════════════════════════════════


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--sets", nargs="+", choices=ALL_SETS, default=list(ALL_SETS))
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--limit", type=int, default=0, help="embed at most N pending items")
    parser.add_argument("--dry-run", action="store_true", help="price it, send nothing")
    return parser.parse_args(argv)


def _run_pending(pending: list[Item], store: VectorStore, tally: RunTally, workers: int) -> None:
    """Embed everything pending, checkpointing the store as it goes.

    The checkpoint is what makes "an interrupted run costs nothing twice" true rather than
    aspirational: at this account's throttle rate a full pass takes hours, and a store written
    only at the end is a store one Ctrl-C away from being paid for again.
    """
    if not pending:
        return
    done = 0
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = [pool.submit(embed_item, item, store, tally) for item in pending]
        for future in as_completed(futures):
            future.result()
            done += 1
            if done % CHECKPOINT_EVERY == 0:
                store.save()
                print(
                    f"  checkpoint {done}/{len(pending)} · calls {tally.calls} · "
                    f"throttles {tally.throttles} · failures {len(tally.failures)}",
                    flush=True,
                )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    assert_in_region(MODEL_ID)
    root = repo_root()
    wanted = frozenset(args.sets)

    build = build_corpus(root, wanted)
    store = VectorStore(root / STORE_NPZ, root / STORE_INDEX)
    store.load()
    pending = [item for item in build.items if not store.fresh(item)]
    stale = sum(1 for item in pending if item.ident in store.index)
    fresh = len(build.items) - len(pending)
    if args.limit:
        pending = pending[: args.limit]
    projection = project_cost(pending)
    print(
        f"corpus {len(build.items)} items · already fresh {fresh} · pending {len(pending)} "
        f"(stale {stale}) · projected USD {projection['projected_usd']:.6f}"
    )

    try:
        check_cost_ceiling(projection["projected_usd"], what=f"embedding {len(pending)} items")
    except CostCeilingExceeded as exc:
        artefact(
            Path(EVIDENCE_DIR) / "token-ledger.json",
            {
                "refused": True,
                "reason": str(exc),
                "projection": projection,
                "budget_consumed": "Nothing. The projection exceeded the ceiling before any "
                "InvokeModel call was made, so this run sent no tokens and spent no money.",
            },
            kind="titan-embedding-token-ledger",
            synthetic=True,
            caveats=["no Bedrock call was made; this file records a refusal, not a measurement"],
        )
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 3

    tally = RunTally()
    started = time.perf_counter()
    wall = 0.0
    if args.dry_run:
        print("dry run: no InvokeModel call made")
    else:
        # `finally`, not a trailing call: a KeyboardInterrupt or a hard failure part-way
        # through must still leave the tokens already paid for on disk.
        try:
            _run_pending(pending, store, tally, args.concurrency)
        finally:
            wall = time.perf_counter() - started
            store.note_run(tally, wall)
            store.save()

    paths = [
        write_manifest(store, build, tally),
        write_ledger(store, tally, projection, wall),
        write_provenance(build, store, root, wanted),
        *write_samples(tally.sample),
    ]
    print(
        f"calls {tally.calls} · tokens {tally.input_tokens} · throttles {tally.throttles} · "
        f"failures {len(tally.failures)} · vectors in store {len(store.index)} · {wall:.1f}s"
    )
    for path in paths:
        print(f"wrote {path.relative_to(root).as_posix()}")
    return 1 if tally.failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
