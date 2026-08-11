# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""A channel-C retriever whose vectors are Amazon Bedrock's and whose index is C-SPANN.

This module implements :class:`~trappoint_recall.eval.backend.ConservingBackend` against
real infrastructure: every query narrative is embedded by **Titan Text Embeddings v2** in
``ap-southeast-2``, and every candidate comes back from a **hinted, prefix-constrained
ANN query** against a CockroachDB ``VECTOR(1024)`` sidecar carrying the ``ce_ann`` index
declared in ``verticals/mainline/db/migrations/0031_clause_embedding.sql``.

It is one channel of four, and saying which one is half the value of the file
-----------------------------------------------------------------------------
ARCHITECTURE 6.4 defines four channels. This is **C** and only C:

* **A — deterministic ancestry** (GIN containment on the blame graph) is not here.
* **B — bonded severity-5** is not here. Every bonded fatality must come back blocking
  unconditionally (MI16); a vector search cannot promise that, and a backend that
  *declared* bonded counters it did not produce would be lying to the invariant that
  exists to stop a fatality decaying. :meth:`BedrockBackend.declared_tally` therefore
  declares ``n_bonded_sev5 = 0``, which is true of this channel and which
  :func:`~trappoint_recall.eval.metrics.bonded_fatalities_all_blocking` will correctly
  read as an MI16 failure on any corpus that bonds a fatality. **That failure is the
  measurement, not a defect in it.**
* **D — lexical BM25** is not here.

So the gates that depend on A, B or D stay red, and the report this backend feeds says
which channel is missing rather than which threshold was inconvenient.

Why the counters are computed twice, on purpose
-----------------------------------------------
The silence conservation law L3 compares the counters a run *declares* against the
counters *enumerated* from the candidate list. That is only a check if the two are
derived independently — a backend that returns ``RunTally.enumerate_from(candidates)``
makes the law tautologically true, and an unverifiable law is a failure dressed as a
pass. Here:

* :meth:`BedrockBackend.retrieve` builds candidates by calling
  :func:`trappoint_recall.fusion.sga.admit`, the project's own admission function;
* :meth:`BedrockBackend.declared_tally` counts by re-deriving each row's outcome from the
  tau table and the cap directly, in :func:`_declare_partition`, which never looks at a
  :class:`~trappoint_recall.eval.backend.ScoredCandidate`.

Both read the same probe rows — they must, because they describe the same run — but
neither reads the other's output, so a disagreement between the admission function and
the policy arithmetic surfaces as a conservation violation instead of as nothing.

What ``p_relevant`` is here, stated plainly because it changes three gates
--------------------------------------------------------------------------
There is no fitted calibrator in this tree. :mod:`trappoint_recall.fusion.calibration`
refuses to score a calibrator on its own fold, and fitting one on this corpus to evaluate
it on this corpus would be the most flattering number available. So this backend applies
:data:`CALIBRATION_ID` — a **declared, unfitted, parameter-free** map
``p_relevant = max(0, 1 - cosine_distance)`` — and says so in every artefact it feeds.

The consequence is exact and asymmetric, and belongs in the reader's hands:

* **Rank-only metrics are unaffected.** ``Retro-Recall@k``, ``Recall@k``, ``nDCG@10``,
  ``MRR`` and the rank distribution depend on the *ordering*, and the map is strictly
  monotone in cosine similarity, so it cannot move them by one place.
* **Threshold metrics are conditional on it.** ``P@block``, the nuisance rate and mean
  blocking checks per permit compare this number against ``tau``. They are measurements
  of *this declared map* under the published tau table, not of a calibrated policy.

The one thing this file will not do is choose the map to make a gate pass. It has no free
parameters to choose.

Residency
---------
:func:`assert_in_region` refuses ``global.`` / ``us.`` / ``eu.`` / ``apac.`` routing
prefixes, and permits ``au.`` and bare in-region model ids. The rule is restated here
rather than imported from ``scripts/aws/_common.py`` deliberately: this package is
Apache-2.0 substrate that must run against a corpus that has never seen MAINLINE, and it
may not depend on a program in ``scripts/``. The duplication is asserted against the
fleet's own copy by ``tests/eval/recall/test_bedrock_backend_contract.py``.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import random
import threading
import time
import uuid
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final, Protocol, runtime_checkable

from trappoint_recall.eval.backend import (
    BLOCKING_CAP_PROBABILISTIC,
    RunTally,
    ScoredCandidate,
)
from trappoint_recall.eval.corpus import EvalQuery
from trappoint_recall.fusion.sga import (
    DEFAULT_TAU,
    AdmissionCandidate,
    TauTable,
    admit,
)

__all__ = [
    "ANN_OVERFETCH",
    "ANN_SQL",
    "CALIBRATION_ID",
    "DEFAULT_ANN_DATABASE",
    "DEFAULT_ANN_LIMIT_FLOOR",
    "DEFAULT_INDEX_GEN",
    "EMBED_DIM",
    "EMBED_TEMPLATE",
    "EMBED_TEMPLATE_SHA256",
    "REQUIRED_REGION",
    "THROTTLE_ERROR_CODES",
    "TITAN_EMBED_MODEL_ID",
    "AnnProbe",
    "AnnRow",
    "BedrockBackend",
    "CockroachAnnProbe",
    "EmbeddingCache",
    "ProbeResult",
    "ResidencyRefused",
    "TitanEmbedder",
    "activity_root_of",
    "assert_in_region",
    "calibrate",
    "commit_id_of",
    "doc_uuid_of",
    "embed_text",
    "site_uuid_of",
    "vector_literal",
]

# ═══════════════════════════════════════════════════════════════════════════════════════
# 0 · Constants that other programs pin
# ═══════════════════════════════════════════════════════════════════════════════════════

REQUIRED_REGION: Final[str] = "ap-southeast-2"
"""Residency. ARCHITECTURE 10.1: Australian safety narratives are embedded here or nowhere."""

TITAN_EMBED_MODEL_ID: Final[str] = "amazon.titan-embed-text-v2:0"
"""Verified HTTP 200 with a 1024-float embedding in ``evidence/aws/probe/raw-titan-invoke.json``."""

EMBED_DIM: Final[int] = 1024
"""Titan v2's default width, and the width ``VECTOR(1024)`` in migration 0031 declares."""

DEFAULT_INDEX_GEN: Final[str] = "titan2-1"
"""Generation label written into ``clause_embedding.index_gen``; feeds M4's index fingerprint."""

DEFAULT_ANN_DATABASE: Final[str] = "mainline_ann_evidence"
"""The evidence database the AWS-execution plan 3 allocates to the corpus-scale ANN surface."""

ANN_OVERFETCH: Final[int] = 4
"""Rows probed from the index per requested candidate, before the time wall is applied.

The wall is a predicate on the *parent* row and cannot be pushed into the vector search
without breaking the index hint (measured: a join in the same SELECT as ``@ce_ann`` is
refused outright with ``index "ce_ann" cannot be used for this query``). Over-fetching and
then filtering is therefore the only shape available, and the factor is published because
it bounds what the wall can remove before the top-k is short."""

DEFAULT_ANN_LIMIT_FLOOR: Final[int] = 40
"""Minimum rows probed regardless of k, matching the top-40 the rerank rubric expects."""

CALIBRATION_ID: Final[str] = "declared_identity_v1"
"""``p_relevant = max(0, 1 - cosine_distance)``. Unfitted, parameter-free, and monotone.

Named so no downstream document can quote a threshold metric from this backend without
naming the map it was measured under. See the module docstring for what it does and does
not move."""

CHANNEL: Final[str] = "C"
ORIGIN: Final[str] = "recall_probabilistic"

EMBED_TEMPLATE: Final[str] = "{activity_path} | {asset_class} | {facet}: {cue_text}"
"""The frozen embedding template, applied identically to documents and to queries.

Genre symmetry is the entire reason cue embeddings exist: a permit written in the future
tense and an investigation written in the past tense are not neighbours in a space that
was never told they describe the same work. Template drift between the two sides is
therefore a defect that would show up as a recall number rather than as an error, which is
why one function produces both sides and :data:`EMBED_TEMPLATE_SHA256` is written into
every artefact."""

EMBED_TEMPLATE_SHA256: Final[str] = hashlib.sha256(EMBED_TEMPLATE.encode("utf-8")).hexdigest()

_SITE_NAMESPACE: Final[uuid.UUID] = uuid.uuid5(uuid.NAMESPACE_URL, "urn:mainline:site")
_DOC_NAMESPACE: Final[uuid.UUID] = uuid.uuid5(uuid.NAMESPACE_URL, "urn:mainline:document")

_CROSS_REGION_PREFIXES: Final[frozenset[str]] = frozenset({"global", "us", "eu", "apac"})

_RETRYABLE_SQLSTATE: Final[str] = "40001"
_BACKOFF_BASE: Final[float] = 0.05
_BACKOFF_MAX: Final[float] = 2.0

THROTTLE_ERROR_CODES: Final[frozenset[str]] = frozenset(
    {
        "ThrottlingException",
        "TooManyRequestsException",
        "ServiceQuotaExceededException",
        "ModelNotReadyException",
        "ServiceUnavailableException",
    }
)
"""Bedrock refusals that mean *later*, and nothing else.

Measured on this account: eight concurrent ``InvokeModel`` calls to Titan v2 exhaust
botocore's own four internal retries and surface ``ThrottlingException``. A throttle is a
statement about rate, not about the request, so it is the one Bedrock error this module
retries — a ``ValidationException`` or an ``AccessDeniedException`` is a fact about the
call and asking it again is a way of reporting the same defect five times."""

THROTTLE_BACKOFF_BASE: Final[float] = 0.1
THROTTLE_BACKOFF_MAX: Final[float] = 1.0
THROTTLE_ATTEMPTS: Final[int] = 900
"""Many short waits rather than a few long ones, because of what the quota turned out to be.

**Measured on this account from AWS's own metrics, 2026-08-11.**
``cloudwatch get_metric_statistics(AWS/Bedrock, ModelId=amazon.titan-embed-text-v2:0,
Period=300, Sum)`` over a two-hour window returned ``Invocations`` of **exactly 300 in
every five-minute bucket** — 60 successful calls a minute, account-wide — against
``InvocationThrottles`` of **2 100 to 4 100 per bucket**. So the limiter is a hard requests
-per-minute bucket, not a token budget: ``InputTokenCount`` in the same buckets ranged from
20 000 to 89 000 without changing the invocation ceiling at all.

Two consequences, and the second is why these constants are what they are.

* **This is a design input, not an incident.** A per-permit embedding at merge time would
  be competing for 60 calls a minute across the whole account. It is one more reason cue
  vectors are computed once at ingest and stored, and the reason :class:`EmbeddingCache`
  is load-bearing rather than an optimisation.
* **Under a shared bucket, exponential backoff cedes the quota.** A refused call costs a
  round trip and is not billed; whichever client waits least collects the tokens as they
  refill. With a 0.75-to-8-second exponential schedule this module was observed taking well
  under 1% of the successful calls while other programs on the same account ran flat out.
  The schedule is therefore short and nearly flat, and the attempt count is deep enough
  (900 × up to 1 s ≈ ten minutes) that one call can sit out a long dry spell rather than
  failing a corpus pass at document nine hundred. Every trip is counted and published.
"""


def _error_code(exc: BaseException) -> str:
    """Bedrock's error code, from a botocore ``ClientError`` or from the class name.

    Read structurally rather than by importing ``botocore``: this package is Apache-2.0
    substrate whose declared dependencies do not include an AWS SDK, and a fake client in
    a credential-free test must be able to raise a throttle the same way.
    """
    response = getattr(exc, "response", None)
    if isinstance(response, Mapping):
        error = response.get("Error")
        if isinstance(error, Mapping):
            code = error.get("Code")
            if isinstance(code, str):
                return code
    return type(exc).__name__


class ResidencyRefused(RuntimeError):
    """A model identifier would route the call outside :data:`REQUIRED_REGION`."""


def assert_in_region(model_id: str) -> str:
    """Return *model_id*, or raise :class:`ResidencyRefused` if it leaves the region.

    The rule is the first dot-separated segment, because that is what Bedrock's
    inference-profile naming encodes. ``apac.`` is refused with the rest even though
    ``ap-southeast-2`` is inside APAC: an APAC profile may serve from Tokyo or Mumbai, and
    "somewhere in Asia-Pacific" is not the promise ARCHITECTURE 10.1 makes.
    """
    if not isinstance(model_id, str) or not model_id:
        raise ResidencyRefused(f"not a model identifier: {model_id!r}")
    prefix = model_id.split(".", 1)[0].lower()
    if prefix in _CROSS_REGION_PREFIXES:
        raise ResidencyRefused(
            f"{model_id!r} routes through the {prefix!r} cross-region inference profile; "
            f"MAINLINE embeds Australian safety narratives in {REQUIRED_REGION} or not at "
            "all (ARCHITECTURE 10.1). Use an 'au.' profile or a bare in-region model id."
        )
    return model_id


# ═══════════════════════════════════════════════════════════════════════════════════════
# 1 · Identity and text, shared by the loader and the retriever
# ═══════════════════════════════════════════════════════════════════════════════════════


def activity_root_of(activity_path: str) -> str:
    """First segment of a functional-taxonomy path, which is the ANN prefix's second column.

    ``/underground/ground-support-installation`` -> ``underground``. The prefix is not a
    filter: it selects the C-SPANN partition tree that is descended, so this function
    decides *reachability*, not ranking.
    """
    stripped = activity_path.strip("/")
    if not stripped:
        raise ValueError("activity_path is empty; the ANN prefix would be unresolvable")
    return stripped.split("/", 1)[0]


def site_uuid_of(site_ref: str) -> str:
    """Deterministic UUIDv5 for a site reference, because the prefix column is ``UUID``.

    The corpus names sites ``MINE-4601731`` / ``SITE-quarry``; migration 0031 declares
    ``site_id UUID``. A v5 name-based UUID keeps the mapping reproducible by anyone with
    the site reference and no access to this run.
    """
    if not site_ref:
        raise ValueError("site_ref is empty; a prefix column may not be defaulted")
    return str(uuid.uuid5(_SITE_NAMESPACE, site_ref))


def doc_uuid_of(external_ref: str) -> str:
    """Deterministic UUIDv5 for a document's external reference."""
    if not external_ref:
        raise ValueError("external_ref is empty")
    return str(uuid.uuid5(_DOC_NAMESPACE, external_ref))


def commit_id_of(external_ref: str, corpus_commit: str) -> bytes:
    """The ``BYTES`` half of the primary key: this document at this corpus state.

    Two corpus states produce two rows for the same document, which is what makes the
    sidecar's primary key ``(clause_uuid, commit_id)`` rather than the document alone.
    """
    return hashlib.sha256(f"{corpus_commit}\x00{external_ref}".encode()).digest()[:16]


def embed_text(*, activity_path: str, asset_class: str, facet: str, cue_text: str) -> str:
    """Render :data:`EMBED_TEMPLATE`. The **only** place either side's text is built."""
    return EMBED_TEMPLATE.format(
        activity_path=activity_path,
        asset_class=asset_class or "unspecified",
        facet=facet,
        cue_text=cue_text,
    )


def query_embed_text(query: EvalQuery, *, facet: str = "narrative") -> str:
    """The text a permit is embedded as: its narrative cue facet, or its work description.

    ``facets['narrative']`` is the safety net the corpus ships (ARCHITECTURE 6.2). When a
    corpus carries no facets the permit text itself is used, and the facet label still says
    ``narrative`` so both sides of the template agree.
    """
    cue = query.facets.get(facet) or query.text
    return embed_text(
        activity_path=query.activity_path,
        asset_class=query.asset_class,
        facet=facet,
        cue_text=cue,
    )


def vector_literal(vector: Sequence[float]) -> str:
    """CockroachDB ``VECTOR`` literal.

    ``repr``-grade floats: a lossy render is a different vector, and the index would
    faithfully search the one that was written rather than the one that was meant.
    """
    if len(vector) != EMBED_DIM:
        raise ValueError(f"expected a {EMBED_DIM}-d vector, got {len(vector)}")
    return "[" + ",".join(repr(float(x)) for x in vector) + "]"


def calibrate(cosine_distance: float) -> float:
    """:data:`CALIBRATION_ID`: ``max(0, 1 - distance)``, clamped into ``[0, 1]``.

    Cosine distance over unit vectors lies in ``[0, 2]``, so an orthogonal or opposed
    document maps to exactly zero rather than to a negative probability. Strictly monotone
    decreasing in distance on ``[0, 1]`` and flat beyond it, which is why it cannot reorder
    a candidate set — and why the rank metrics computed over this backend are the same
    numbers any monotone calibration would produce.
    """
    if not math.isfinite(cosine_distance):
        raise ValueError(f"cosine distance is not finite: {cosine_distance!r}")
    return max(0.0, min(1.0, 1.0 - cosine_distance))


MAX_SEVERITY: Final[int] = 5
MIN_SEVERITY: Final[int] = 1


def _admission_severity(severity: int) -> int:
    """Map a corpus severity onto the 1..5 admission scale.

    Severity 0 — "no injury recorded" in the Part-50 vocabulary — is presented as 1, which
    carries the *highest* tau in the table. Rounding an unknown up towards blocking would
    manufacture recall out of a missing label; rounding it towards silence costs recall and
    is the honest direction to be wrong in.
    """
    if severity < MIN_SEVERITY:
        return MIN_SEVERITY
    if severity > MAX_SEVERITY:
        return MAX_SEVERITY
    return severity


# ═══════════════════════════════════════════════════════════════════════════════════════
# 2 · The embedding cache
# ═══════════════════════════════════════════════════════════════════════════════════════


@dataclass(slots=True)
class EmbeddingCache:
    """A content-addressed JSONL cache so a re-run of this evaluation costs nothing.

    The key is a digest over *the exact request body* — model id, dimension, normalisation
    flag and text — not over the text alone. Two runs that differ in any of those are two
    different vectors, and a cache that conflated them would silently mix embedding spaces
    inside one index generation.

    Writes are append-only and flushed per entry: a run interrupted after 900 of 1 071
    embeddings must not have to buy those 900 again.
    """

    path: Path | None = None
    _entries: dict[str, list[float]] = field(default_factory=dict, init=False)
    _handle: Any = field(default=None, init=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False)
    hits: int = field(default=0, init=False)
    misses: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.is_file():
            with self.path.open("r", encoding="utf-8") as handle:
                for raw in handle:
                    line = raw.strip()
                    if not line:
                        continue
                    try:
                        payload = json.loads(line)
                    except json.JSONDecodeError:
                        # A truncated final line from an interrupted run is recoverable by
                        # dropping it; refusing the whole cache would buy the corpus again.
                        continue
                    key = payload.get("key")
                    vector = payload.get("vector")
                    if isinstance(key, str) and isinstance(vector, list):
                        self._entries[key] = [float(x) for x in vector]

    @staticmethod
    def key_for(model_id: str, dimensions: int, normalize: bool, text: str) -> str:
        material = json.dumps(
            {"model": model_id, "dimensions": dimensions, "normalize": normalize, "text": text},
            sort_keys=True,
            ensure_ascii=False,
        )
        return hashlib.sha256(material.encode("utf-8")).hexdigest()

    def get(self, key: str) -> list[float] | None:
        with self._lock:
            vector = self._entries.get(key)
            if vector is None:
                self.misses += 1
                return None
            self.hits += 1
            return vector

    def put(self, key: str, vector: Sequence[float]) -> None:
        values = [float(x) for x in vector]
        with self._lock:
            self._entries[key] = values
            if self.path is None:
                return
            if self._handle is None:
                self._handle = self.path.open("a", encoding="utf-8")
            self._handle.write(json.dumps({"key": key, "vector": values}) + "\n")
            self._handle.flush()

    def close(self) -> None:
        with self._lock:
            if self._handle is not None:
                self._handle.close()
                self._handle = None

    def to_dict(self) -> dict[str, object]:
        return {
            "path": str(self.path) if self.path else None,
            "entries": len(self._entries),
            "hits": self.hits,
            "misses": self.misses,
        }


# ═══════════════════════════════════════════════════════════════════════════════════════
# 3 · Titan
# ═══════════════════════════════════════════════════════════════════════════════════════


@runtime_checkable
class InvokeModelClient(Protocol):
    """The one Bedrock operation this module uses. Narrow on purpose: a fake is three lines."""

    def invoke_model(
        self, *, modelId: str, body: str, contentType: str, accept: str
    ) -> Mapping[str, Any]: ...


@dataclass(slots=True)
class TitanEmbedder:
    """Titan Text Embeddings v2, one ``inputText`` per call, cached, with a token ledger.

    Titan has no batch form: the InvokeModel contract takes a single ``inputText``, so the
    only lever on cost is the cache, and the only honest report of cost is Bedrock's own
    ``inputTextTokenCount`` accumulated here and reconciled against CloudWatch by the
    fleet's cost worker.
    """

    client: InvokeModelClient | None = None
    model_id: str = TITAN_EMBED_MODEL_ID
    region: str = REQUIRED_REGION
    cache: EmbeddingCache = field(default_factory=EmbeddingCache)
    normalize: bool = True
    dimensions: int = EMBED_DIM
    throttle_attempts: int = THROTTLE_ATTEMPTS
    sleep: Callable[[float], None] = time.sleep
    rand: Callable[[], float] = random.random
    calls: int = field(default=0, init=False)
    input_tokens: int = field(default=0, init=False)
    latency_ms_total: float = field(default=0.0, init=False)
    throttle_retries: int = field(default=0, init=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False)

    def __post_init__(self) -> None:
        assert_in_region(self.model_id)
        if self.region != REQUIRED_REGION:
            raise ResidencyRefused(
                f"refusing to embed in {self.region!r}; cognition stays in "
                f"{REQUIRED_REGION} (ARCHITECTURE 10.1)"
            )
        if self.dimensions != EMBED_DIM:
            raise ValueError(
                f"the sidecar declares VECTOR({EMBED_DIM}); a {self.dimensions}-d request "
                "would produce a vector the index cannot store"
            )

    def request_body(self, text: str) -> dict[str, Any]:
        """The InvokeModel body, exposed so a cassette or a probe can key the exact request."""
        return {"inputText": text, "dimensions": self.dimensions, "normalize": self.normalize}

    def _client(self) -> InvokeModelClient:
        if self.client is not None:
            return self.client
        try:
            import boto3
        except ImportError as exc:  # pragma: no cover - boto3 is a declared dependency
            raise RuntimeError("boto3 is not installed; cannot reach Bedrock") from exc
        self.client = boto3.client("bedrock-runtime", region_name=self.region)
        return self.client

    def _invoke(self, body: str) -> Mapping[str, Any]:
        """One InvokeModel call, retrying **throttles only**, with full-jitter backoff.

        The trip count is kept and published: a throttle that was absorbed silently is a
        latency figure that means something different from the one it appears to mean.
        """
        attempt = 0
        while True:
            try:
                return _read_body(
                    self._client().invoke_model(
                        modelId=self.model_id,
                        body=body,
                        contentType="application/json",
                        accept="application/json",
                    )
                )
            except Exception as exc:
                if _error_code(exc) not in THROTTLE_ERROR_CODES:
                    raise
                attempt += 1
                with self._lock:
                    self.throttle_retries += 1
                if attempt >= self.throttle_attempts:
                    raise
                delay = min(THROTTLE_BACKOFF_MAX, THROTTLE_BACKOFF_BASE * attempt)
                self.sleep(delay * (0.5 + self.rand()))

    def embed(self, text: str) -> list[float]:
        """Return the 1024-d unit vector for *text*, from cache when possible."""
        key = EmbeddingCache.key_for(self.model_id, self.dimensions, self.normalize, text)
        cached = self.cache.get(key)
        if cached is not None:
            return cached
        body = json.dumps(self.request_body(text))
        started = time.perf_counter()
        payload = self._invoke(body)
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        vector = payload.get("embedding")
        if not isinstance(vector, list) or len(vector) != self.dimensions:
            raise RuntimeError(
                f"Titan returned {type(vector).__name__} of length "
                f"{len(vector) if isinstance(vector, list) else 'n/a'}; expected "
                f"{self.dimensions} floats"
            )
        tokens = payload.get("inputTextTokenCount")
        with self._lock:
            self.latency_ms_total += elapsed_ms
            self.calls += 1
            if isinstance(tokens, int):
                self.input_tokens += tokens
        values = [float(x) for x in vector]
        self.cache.put(key, values)
        return values

    def ledger(self) -> dict[str, object]:
        return {
            "model_id": self.model_id,
            "region": self.region,
            "dimensions": self.dimensions,
            "normalize": self.normalize,
            "calls": self.calls,
            "input_tokens": self.input_tokens,
            "output_tokens": 0,
            "throttle_retries": self.throttle_retries,
            "mean_latency_ms": (
                round(self.latency_ms_total / self.calls, 2) if self.calls else None
            ),
            "cache": self.cache.to_dict(),
        }


def _read_body(response: Mapping[str, Any]) -> Mapping[str, Any]:
    """Decode an InvokeModel response body, whether it is a stream or already bytes."""
    raw = response.get("body")
    if raw is None:
        raise RuntimeError("InvokeModel response carries no body")
    if hasattr(raw, "read"):
        raw = raw.read()
    if isinstance(raw, (bytes, bytearray)):
        raw = bytes(raw).decode("utf-8")
    parsed = json.loads(raw) if isinstance(raw, str) else raw
    if not isinstance(parsed, Mapping):
        raise TypeError("InvokeModel response body is not a JSON object")
    return parsed


# ═══════════════════════════════════════════════════════════════════════════════════════
# 4 · The ANN probe
# ═══════════════════════════════════════════════════════════════════════════════════════

ANN_SQL: Final[str] = """
WITH ann AS (
  SELECT clause_uuid, commit_id, embedding <=> %(qvec)s AS distance
    FROM mainline.clause_embedding@ce_ann
   WHERE site_id = %(site_id)s AND activity_root = %(activity_root)s
   ORDER BY embedding <=> %(qvec)s
   LIMIT %(ann_limit)s
)
SELECT v.external_ref,
       a.distance,
       v.severity,
       (v.occurred_at < %(wall)s
        AND v.ingested_at < %(wall)s
        AND v.corpus_commit_at <= %(wall)s) AS within_wall
  FROM ann AS a
  JOIN mainline.clause_version AS v
    ON v.clause_uuid = a.clause_uuid AND v.commit_id = a.commit_id
 ORDER BY a.distance ASC, v.external_ref ASC
"""
"""The deliverable query, in the shape GT-06b measured.

Two things about its shape are load-bearing and were both established by execution, not by
reading:

1. ``@ce_ann`` pins the index. GT-06 measured that at corpus scale the *unhinted* form
   plans a scan; a plan that flips on table statistics must not sit beneath a safety gate.
2. The vector search is its own CTE. A ``JOIN`` in the same ``SELECT`` as the hint is
   refused outright — ``index "ce_ann" cannot be used for this query`` — so the parent row
   is joined *after* the index has produced its target count.

The time wall is a predicate the database evaluates (recall lead D12: ``occurred_at < t AND
ingested_at < t AND corpus_commit <= t``, never ``AS OF SYSTEM TIME``, whose reach is
bounded by ``gc.ttlseconds``). It is returned as a column rather than applied as a filter so
the run can report how many probed rows the wall removed; a wall that silently removes
nothing is indistinguishable from a wall that is not there.
"""


@dataclass(frozen=True, slots=True)
class AnnRow:
    """One row the index returned, before any admission decision has been made."""

    doc_id: str
    distance: float
    severity: int
    within_wall: bool
    ann_rank: int


@dataclass(frozen=True, slots=True)
class ProbeResult:
    """What one ANN probe saw, including what it discarded and why."""

    rows: tuple[AnnRow, ...]
    n_probed: int
    n_wall_excluded: int
    retries_40001: int
    latency_ms: float

    def to_dict(self) -> dict[str, object]:
        return {
            "n_probed": self.n_probed,
            "n_within_wall": len(self.rows),
            "n_wall_excluded": self.n_wall_excluded,
            "retries_40001": self.retries_40001,
            "latency_ms": round(self.latency_ms, 2),
        }


@runtime_checkable
class AnnProbe(Protocol):
    """The retrieval substrate, narrowed to one call so a fake needs no database."""

    def probe(
        self,
        *,
        site_id: str,
        activity_root: str,
        vector: Sequence[float],
        ann_limit: int,
        wall: datetime,
    ) -> ProbeResult: ...


@dataclass(slots=True)
class CockroachAnnProbe:
    """:data:`ANN_SQL` against CockroachDB, with the ``40001`` retry loop the Cloud needs.

    ``connect`` is injected rather than a DSN: this package must not learn how MAINLINE
    stores a connection string, and the fleet's ``scripts/aws/_common.crdb`` already refuses
    to return one. The retry loop is written here rather than imported because
    ``tests/boundary/test_ci_greps.py`` bans ``tenacity``/``backoff``/``retrying`` — a
    blanket retry helper cannot tell a serialization restart from a gate refusal, and this
    system's refusals are results.

    **The trip count is published**, per probe and in aggregate. A single-node Docker never
    raises ``RETRY_SERIALIZABLE``; a loop whose premium is never quoted is superstition.
    """

    connect: Callable[[], Any]
    attempts: int = 8
    sleep: Callable[[float], None] = time.sleep
    rand: Callable[[], float] = random.random
    _conn: Any = field(default=None, init=False)
    retries_40001: int = field(default=0, init=False)
    reconnects: int = field(default=0, init=False)
    probes: int = field(default=0, init=False)
    rows_probed: int = field(default=0, init=False)

    def _connection(self) -> Any:
        if self._conn is None:
            self._conn = self.connect()
        return self._conn

    def probe(
        self,
        *,
        site_id: str,
        activity_root: str,
        vector: Sequence[float],
        ann_limit: int,
        wall: datetime,
    ) -> ProbeResult:
        params = {
            "qvec": vector_literal(vector),
            "site_id": site_id,
            "activity_root": activity_root,
            "ann_limit": int(ann_limit),
            "wall": wall,
        }
        started = time.perf_counter()
        retries = 0
        while True:
            try:
                cursor = self._connection().execute(ANN_SQL, params)
                fetched = cursor.fetchall()
                break
            except Exception as exc:
                # A connection that the server has closed is not a result. Reconnecting once
                # and re-asking is honest — the question was never answered — and it stops a
                # 396-permit pass over a managed cluster from being lost to one idle
                # timeout. The reconnect is counted, because a run that silently rebuilt its
                # connection twenty times is describing a different cluster than it appears.
                if getattr(self._conn, "closed", False) and self.reconnects < self.attempts:
                    self.reconnects += 1
                    self._conn = None
                    continue
                if getattr(exc, "sqlstate", None) != _RETRYABLE_SQLSTATE:
                    raise
                retries += 1
                self.retries_40001 += 1
                if retries >= self.attempts:
                    raise
                self.sleep(min(_BACKOFF_MAX, _BACKOFF_BASE * retries) * (0.5 + self.rand()))
        latency_ms = (time.perf_counter() - started) * 1000.0

        rows: list[AnnRow] = []
        excluded = 0
        for index, record in enumerate(fetched, start=1):
            doc_id, distance, severity, within_wall = (
                str(record[0]),
                float(record[1]),
                int(record[2]),
                bool(record[3]),
            )
            if not within_wall:
                excluded += 1
                continue
            rows.append(
                AnnRow(
                    doc_id=doc_id,
                    distance=distance,
                    severity=severity,
                    within_wall=True,
                    ann_rank=index,
                )
            )
        self.probes += 1
        self.rows_probed += len(fetched)
        return ProbeResult(
            rows=tuple(rows),
            n_probed=len(fetched),
            n_wall_excluded=excluded,
            retries_40001=retries,
            latency_ms=latency_ms,
        )

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def to_dict(self) -> dict[str, object]:
        return {
            "probes": self.probes,
            "rows_probed": self.rows_probed,
            "retries_40001": self.retries_40001,
            "reconnects": self.reconnects,
            "retry_attempts_configured": self.attempts,
        }


# ═══════════════════════════════════════════════════════════════════════════════════════
# 5 · The declared partition — the independent side of L3
# ═══════════════════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True, slots=True)
class _RunInput:
    """Everything one run saw, kept so both derivations can start from the same evidence."""

    query_id: str
    probe: ProbeResult
    k: int
    ann_limit: int


def _dedupe(rows: Sequence[AnnRow]) -> tuple[list[AnnRow], list[AnnRow]]:
    """Split rows into first-seen and repeat-of-a-doc-already-seen, preserving order."""
    seen: set[str] = set()
    kept: list[AnnRow] = []
    duplicates: list[AnnRow] = []
    for row in rows:
        if row.doc_id in seen:
            duplicates.append(row)
            continue
        seen.add(row.doc_id)
        kept.append(row)
    return kept, duplicates


def _admitted_rows(run: _RunInput) -> tuple[list[AnnRow], list[AnnRow], list[AnnRow]]:
    """``(candidates, duplicates, beyond_k)`` — the three fates of a probed row.

    The candidate set of a run is the top ``k`` distinct documents that survived the time
    wall. Rows the probe returned beyond that are index traffic, not candidates: they were
    never presented for admission and counting them would make the conservation law close
    over a set no decision was made about.

    A duplicate counts only when the document it repeats is itself in the candidate set.
    A second copy of a document that never made the cut was discarded by the cut-off, not by
    deduplication, and filing it under ``deduped`` would let one row be silenced twice.
    """
    kept, duplicates = _dedupe(run.probe.rows)
    candidates = kept[: run.k]
    admitted_ids = {row.doc_id for row in candidates}
    scoped_duplicates = [row for row in duplicates if row.doc_id in admitted_ids]
    return candidates, scoped_duplicates, kept[run.k :]


def _declare_partition(
    run: _RunInput, tau_table: TauTable, cap: int
) -> tuple[int, int, int, int]:
    """``(blocking, advisory, silenced, deduped)`` from the policy arithmetic alone.

    This is the *declared* side of conservation law L3 and it is deliberately a second
    implementation of the admission rules — tau lookup, the ``p < tau`` silence, the
    ``severity_then_score`` queue and the probabilistic cap — reading only
    :class:`AnnRow` values. It never touches a :class:`ScoredCandidate`, so if
    :func:`trappoint_recall.fusion.sga.admit` and these rules ever disagree, the harness
    reports a conservation violation rather than agreeing with itself.
    """
    candidates, duplicates, _beyond = _admitted_rows(run)
    silenced = 0
    queued: list[tuple[float, float, float]] = []
    for row in candidates:
        severity = _admission_severity(row.severity)
        tau = tau_table.tau_for(severity)
        p = calibrate(row.distance)
        if p < tau:
            silenced += 1
            continue
        queued.append((-float(severity), -p, float(row.ann_rank)))
    queued.sort()
    blocking = min(len(queued), cap)
    advisory = len(queued) - blocking
    return blocking, advisory, silenced, len(duplicates)


# ═══════════════════════════════════════════════════════════════════════════════════════
# 6 · The backend
# ═══════════════════════════════════════════════════════════════════════════════════════


class BedrockBackend:
    """Channel C: Titan v2 vectors, hinted prefix-constrained C-SPANN, published counters.

    Satisfies :class:`~trappoint_recall.eval.backend.ConservingBackend`. Every candidate it
    returns carries ``channel='C'`` and ``origin='recall_probabilistic'``, which is what
    subjects it to the cap of :data:`~trappoint_recall.eval.backend.BLOCKING_CAP_PROBABILISTIC`
    and to ``P@block``; channels A and B are uncapped precisely because a cap that could
    suppress a bonded fatality would contradict MI16, and this backend produces neither.
    """

    name: str = "bedrock-titan-ann-c"

    def __init__(
        self,
        *,
        embedder: TitanEmbedder | None = None,
        probe: AnnProbe | None = None,
        corpus_head_wall: datetime,
        tau_table: TauTable | None = None,
        cap: int = BLOCKING_CAP_PROBABILISTIC,
        ann_overfetch: int = ANN_OVERFETCH,
        ann_limit_floor: int = DEFAULT_ANN_LIMIT_FLOOR,
        facet: str = "narrative",
        name: str | None = None,
        policy_version: str = "",
    ) -> None:
        if probe is None:
            raise ValueError(
                "BedrockBackend needs an AnnProbe: a retriever with no index is a "
                "NullBackend wearing a model's name"
            )
        if corpus_head_wall.tzinfo is None:
            raise ValueError("corpus_head_wall must be timezone-aware")
        self._embedder = embedder if embedder is not None else TitanEmbedder()
        self._probe = probe
        self._corpus_head_wall = corpus_head_wall
        self._tau = tau_table if tau_table is not None else TauTable(
            thresholds=dict(DEFAULT_TAU),
            policy_version=policy_version or "architecture-6.4-defaults",
            provenance={
                "source": "ARCHITECTURE 6.4 initial calibrated defaults",
                "note": (
                    "not fitted on this corpus; severity selects the threshold and never "
                    "alters the score"
                ),
            },
        )
        self._cap = cap
        self._ann_overfetch = max(1, ann_overfetch)
        self._ann_limit_floor = max(1, ann_limit_floor)
        self._facet = facet
        self._policy_version = policy_version or "architecture-6.4-defaults"
        if name:
            self.name = name
        self._runs: dict[str, _RunInput] = {}
        self._wall_excluded_total = 0
        self._probed_total = 0

    # -- configuration reported into every artefact -------------------------------------

    def config(self) -> dict[str, object]:
        """Everything a reader needs to re-derive this backend's decisions."""
        return {
            "backend_name": self.name,
            "channel": CHANNEL,
            "origin": ORIGIN,
            "embed_model_id": self._embedder.model_id,
            "embed_dimensions": self._embedder.dimensions,
            "embed_normalize": self._embedder.normalize,
            "embed_region": self._embedder.region,
            "embed_template": EMBED_TEMPLATE,
            "embed_template_sha256": EMBED_TEMPLATE_SHA256,
            "facet": self._facet,
            "calibration": CALIBRATION_ID,
            "calibration_note": (
                "declared, unfitted, parameter-free monotone map p = max(0, 1 - cosine "
                "distance); rank metrics are invariant to it, threshold metrics are "
                "conditional on it"
            ),
            "tau_table": dict(self._tau.thresholds),
            "tau_policy_version": self._policy_version,
            "blocking_cap_probabilistic": self._cap,
            "ann_overfetch": self._ann_overfetch,
            "ann_limit_floor": self._ann_limit_floor,
            "corpus_head_wall": self._corpus_head_wall.astimezone(UTC).isoformat(),
            "channels_absent": {
                "A": "deterministic ancestry (GIN containment on the blame graph)",
                "B": "bonded severity-5, admitted unconditionally (MI16)",
                "C_sweep": "256-d unpartitioned coarse sweep",
                "D": "lexical BM25",
            },
        }

    def ann_limit_for(self, k: int) -> int:
        return max(self._ann_limit_floor, k * self._ann_overfetch)

    def wall_for(self, query: EvalQuery) -> datetime:
        """A retro permit is walled at its own *t*; a routine permit replays at corpus head."""
        return query.wall if query.wall is not None else self._corpus_head_wall

    # -- the contract -------------------------------------------------------------------

    async def retrieve(self, query: EvalQuery, k: int) -> list[ScoredCandidate]:
        """Embed the permit, probe the index, admit what survives the wall."""
        if k < 1:
            raise ValueError(f"k must be >= 1, got {k}")
        vector = self._embedder.embed(query_embed_text(query, facet=self._facet))
        ann_limit = self.ann_limit_for(k)
        probe = self._probe.probe(
            site_id=site_uuid_of(query.site_id),
            activity_root=activity_root_of(query.activity_path),
            vector=vector,
            ann_limit=ann_limit,
            wall=self.wall_for(query),
        )
        run = _RunInput(query_id=query.query_id, probe=probe, k=k, ann_limit=ann_limit)
        self._runs[query.query_id] = run
        self._wall_excluded_total += probe.n_wall_excluded
        self._probed_total += probe.n_probed
        return self._build_candidates(run)

    async def declared_tally(self, query: EvalQuery) -> RunTally:
        """The counters this run would write to ``mainline_meas.recall_run``.

        Derived by :func:`_declare_partition` from the probe rows and the published policy
        constants — never from the candidate list :meth:`retrieve` returned. See the module
        docstring for why that separation is the whole point of the law.

        ``n_bonded_sev5`` is **0** and that is a statement about this channel, not about the
        corpus: bonded severity-5 events are channel B's to produce and the corpus's to
        know. A channel-C retriever that declared a bonded count would be asserting an
        invariant it cannot enforce, and MI16 is checked against corpus truth for exactly
        that reason.
        """
        run = self._runs.get(query.query_id)
        if run is None:
            raise RuntimeError(
                f"{query.query_id}: declared_tally was asked for a run that never "
                "happened. Counters for an unexecuted retrieval would be a fabrication."
            )
        blocking, advisory, silenced, deduped = _declare_partition(run, self._tau, self._cap)
        return RunTally(
            n_candidates=blocking + advisory + silenced + deduped,
            n_blocking=blocking,
            n_advisory=advisory,
            n_silenced=silenced,
            n_deduped=deduped,
            n_bonded_sev5=0,
            n_bonded_sev5_blocking=0,
            arms_degraded=False,
        )

    # -- internals ----------------------------------------------------------------------

    def _build_candidates(self, run: _RunInput) -> list[ScoredCandidate]:
        """Score and admit, through the project's own admission function."""
        candidates, duplicates, _beyond = _admitted_rows(run)
        presented: list[AdmissionCandidate] = [
            AdmissionCandidate(
                doc_id=row.doc_id,
                p_relevant=calibrate(row.distance),
                severity=_admission_severity(row.severity),
                origin=ORIGIN,
                channel=CHANNEL,
                rank=rank,
            )
            for rank, row in enumerate(candidates, start=1)
        ]
        result = admit(
            presented,
            tau_table=self._tau,
            cap=self._cap,
            policy_version=self._policy_version,
        )
        outcome_of: dict[str, tuple[str, float]] = {}
        for check in (*result.blocking, *result.advisory, *result.silenced):
            outcome_of[check.doc_id] = (check.outcome, check.tau_applied)

        scored: list[ScoredCandidate] = []
        for rank, row in enumerate(candidates, start=1):
            outcome, tau_applied = outcome_of[row.doc_id]
            scored.append(
                ScoredCandidate(
                    doc_id=row.doc_id,
                    rank=rank,
                    p_relevant=calibrate(row.distance),
                    tau_applied=tau_applied,
                    outcome=outcome,  # type: ignore[arg-type]
                    severity=_admission_severity(row.severity),
                    channel=CHANNEL,
                    origin=ORIGIN,
                    features={
                        "cosine_distance": row.distance,
                        "cosine_similarity": 1.0 - row.distance,
                        "ann_rank": float(row.ann_rank),
                        "corpus_severity": float(row.severity),
                    },
                )
            )
        for offset, row in enumerate(duplicates, start=1):
            scored.append(
                ScoredCandidate(
                    doc_id=row.doc_id,
                    rank=len(candidates) + offset,
                    p_relevant=calibrate(row.distance),
                    tau_applied=self._tau.tau_for(_admission_severity(row.severity)),
                    outcome="deduped",
                    severity=_admission_severity(row.severity),
                    channel=CHANNEL,
                    origin=ORIGIN,
                    features={
                        "cosine_distance": row.distance,
                        "cosine_similarity": 1.0 - row.distance,
                        "ann_rank": float(row.ann_rank),
                        "corpus_severity": float(row.severity),
                    },
                )
            )
        return scored

    # -- run-level reporting ------------------------------------------------------------

    def run_report(self) -> dict[str, object]:
        """Aggregate evidence about the retrieval itself, for the run manifest."""
        probe_stats: dict[str, object] = {}
        if isinstance(self._probe, CockroachAnnProbe):
            probe_stats = self._probe.to_dict()
        return {
            "queries_executed": len(self._runs),
            "rows_probed_total": self._probed_total,
            "rows_excluded_by_time_wall": self._wall_excluded_total,
            "embedding": self._embedder.ledger(),
            "probe": probe_stats,
        }


# ═══════════════════════════════════════════════════════════════════════════════════════
# 7 · Convenience for the loader
# ═══════════════════════════════════════════════════════════════════════════════════════


def document_rows(
    records: Iterable[Any],
    *,
    corpus_commit: str,
    embed_model: str = TITAN_EMBED_MODEL_ID,
    index_gen: str = DEFAULT_INDEX_GEN,
) -> list[dict[str, object]]:
    """Project canonical event records onto the sidecar's columns.

    Accepts anything exposing ``external_ref``, ``site_ref``, ``activity_path``,
    ``asset_class``, ``narrative``, ``work_description``, ``occurred_at``, ``ingested_at``,
    ``corpus_commit_at`` and ``severity_actual`` — the shape
    :class:`trappoint_recall.corpora.model.EventRecord` already has — so the loader in
    ``scripts/aws/recall_real.py`` and this retriever cannot disagree about what was
    embedded. That symmetry is the reason this function lives beside the template rather
    than beside the loader.
    """
    rows: list[dict[str, object]] = []
    for record in records:
        cue = (getattr(record, "narrative", "") or "").strip()
        work = (getattr(record, "work_description", "") or "").strip()
        title = (getattr(record, "title", "") or "").strip()
        parts = [part for part in (title, cue, work) if part]
        rows.append(
            {
                "external_ref": record.external_ref,
                "clause_uuid": doc_uuid_of(record.external_ref),
                "commit_id": commit_id_of(record.external_ref, corpus_commit),
                "site_id": site_uuid_of(record.site_ref),
                "site_ref": record.site_ref,
                "activity_root": activity_root_of(record.activity_path),
                "activity_path": record.activity_path,
                "asset_class": record.asset_class,
                "embed_model": embed_model,
                "index_gen": index_gen,
                "occurred_at": record.occurred_at,
                "ingested_at": record.ingested_at,
                "corpus_commit_at": record.corpus_commit_at,
                "severity": int(record.severity_actual),
                "text": embed_text(
                    activity_path=record.activity_path,
                    asset_class=record.asset_class,
                    facet="narrative",
                    cue_text=". ".join(parts),
                ),
            }
        )
    return rows


def default_cache_path(root: Path | str | None = None) -> Path:
    """``out/aws/recall/titan-embeddings.jsonl`` — gitignored, and re-runs are free."""
    base = Path(root) if root is not None else Path(os.environ.get("MAINLINE_OUT_DIR", "out"))
    return base / "aws" / "recall" / "titan-embeddings.jsonl"
