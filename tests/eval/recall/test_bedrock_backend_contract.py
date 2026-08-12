# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The Bedrock channel-C backend, proved against a fake client and no credentials at all.

Every test here runs with no AWS session, no CockroachDB connection and no network. That
is not a convenience: the properties under test are properties of the *contract*, and a
suite that could only check them against a live account would check them once, on one
machine, on the day someone remembered.

Four claims, and the second is the one worth the file:

1. :class:`~trappoint_recall.eval.bedrock_backend.BedrockBackend` satisfies
   :class:`~trappoint_recall.eval.backend.ConservingBackend`.
2. **Its declared counters are computed independently of the candidate list it returns.**
   Proved destructively: a candidate is removed from the returned list after the fact and
   the conservation law *notices*. A backend that derived its counters from its candidates
   would stay silently consistent, and the law it satisfied would be a tautology.
3. It refuses a cross-region model identifier — ``global.``, ``us.``, ``eu.``, ``apac.`` —
   and accepts an ``au.`` profile or a bare in-region id.
4. The embedding template is applied identically to documents and to permits, and the
   evidence DDL is the migration's table rather than a paraphrase of it.
"""

from __future__ import annotations

# Every import in this module sits at the top of the file, which it can because
# ``tests/eval/recall/conftest.py`` performs the whole sys.path bootstrap — this
# directory, then ``ensure_import_paths()`` for the package source — and pytest imports a
# directory's conftest before any test module in it. This file used to repeat that
# bootstrap inline and pay six E402s for the privilege; its three sibling modules
# (``test_g4alpha_gates``, ``test_harness_contracts``, ``test_metrics_properties``)
# already rely on conftest alone, so the repetition was the anomaly, not the rule.
import asyncio
import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from corpus_resolution import REPO_ROOT

from trappoint_recall.eval.backend import (
    BLOCKING_CAP_PROBABILISTIC,
    ConservingBackend,
    QueryResult,
    RetrievalBackend,
    RunTally,
)
from trappoint_recall.eval.bedrock_backend import (
    CALIBRATION_ID,
    EMBED_DIM,
    EMBED_TEMPLATE,
    EMBED_TEMPLATE_SHA256,
    TITAN_EMBED_MODEL_ID,
    AnnRow,
    BedrockBackend,
    EmbeddingCache,
    ProbeResult,
    ResidencyRefused,
    TitanEmbedder,
    activity_root_of,
    assert_in_region,
    calibrate,
    document_rows,
    embed_text,
    query_embed_text,
    site_uuid_of,
    vector_literal,
)
from trappoint_recall.eval.corpus import EvalQuery
from trappoint_recall.eval.metrics import conservation
from trappoint_recall.fusion.sga import DEFAULT_TAU

CORPUS_HEAD = datetime(2017, 12, 28, tzinfo=UTC)


# ═══════════════════════════════════════════════════════════════════════════════════════
# Fakes — three of them, none of which reach a network
# ═══════════════════════════════════════════════════════════════════════════════════════


class FakeInvokeClient:
    """A Bedrock client that answers InvokeModel from arithmetic.

    The vector is a deterministic function of the text so a test can assert *which* text
    was embedded, and the response carries ``inputTextTokenCount`` because the token ledger
    is evidence and a fake that omitted it would let the ledger silently read zero.
    """

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    # N803 is suppressed twice below because this fake exists to satisfy
    # ``InvokeModelClient``, whose parameter names are botocore's, not ours:
    # ``TitanEmbedder`` calls ``invoke_model(modelId=..., contentType=..., accept=...)``
    # by keyword. Renaming them to snake_case here would make the fake un-callable by the
    # code under test, and the suite would be proving a signature Bedrock never sees.
    def invoke_model(
        self,
        *,
        modelId: str,  # noqa: N803  # boto3 InvokeModel parameter name
        body: str,
        contentType: str,  # noqa: N803  # boto3 InvokeModel parameter name
        accept: str,
    ) -> dict[str, Any]:
        payload = json.loads(body)
        # All four wire fields are recorded, not only the two the arithmetic needs. A fake
        # that discarded ``contentType`` and ``accept`` could not catch a caller that sent
        # the wrong ones, and the InvokeModel contract is exactly what this suite pins.
        self.calls.append(
            {
                "modelId": modelId,
                "body": payload,
                "contentType": contentType,
                "accept": accept,
            }
        )
        seed = sum(ord(char) for char in payload["inputText"]) or 1
        vector = [((seed * (index + 1)) % 97) / 97.0 for index in range(payload["dimensions"])]
        norm = sum(value * value for value in vector) ** 0.5
        unit = [value / norm for value in vector]
        return {
            "body": json.dumps(
                {"embedding": unit, "inputTextTokenCount": len(payload["inputText"]) // 4 or 1}
            ).encode("utf-8")
        }


class ScriptedProbe:
    """An ANN probe that replays a fixed row list. No database, no index, no vectors."""

    def __init__(self, rows: list[AnnRow], *, n_probed: int | None = None) -> None:
        self.rows = rows
        self.n_probed = n_probed if n_probed is not None else len(rows)
        self.seen: list[dict[str, Any]] = []

    def probe(
        self,
        *,
        site_id: str,
        activity_root: str,
        vector: Any,
        ann_limit: int,
        wall: datetime,
    ) -> ProbeResult:
        self.seen.append(
            {
                "site_id": site_id,
                "activity_root": activity_root,
                "ann_limit": ann_limit,
                "wall": wall,
                "dim": len(vector),
            }
        )
        return ProbeResult(
            rows=tuple(self.rows),
            n_probed=self.n_probed,
            n_wall_excluded=max(0, self.n_probed - len(self.rows)),
            retries_40001=0,
            latency_ms=1.0,
        )


def make_query(query_id: str = "Q-1", **overrides: Any) -> EvalQuery:
    payload: dict[str, Any] = {
        "query_id": query_id,
        "kind": "retro",
        "text": "permit to work: ground support installation",
        "site_id": "MINE-4601731",
        "activity_path": "/underground/ground-support-installation",
        "asset_class": "roof-bolter",
        "severity": 5,
        "wall": datetime(2010, 1, 11, tzinfo=UTC),
        "truth_doc_id": "D1",
        "facets": {"narrative": "secondary ground support under unsupported back"},
    }
    payload.update(overrides)
    return EvalQuery(**payload)


def make_backend(rows: list[AnnRow], **kwargs: Any) -> tuple[BedrockBackend, ScriptedProbe]:
    probe = ScriptedProbe(rows)
    backend = BedrockBackend(
        embedder=TitanEmbedder(client=FakeInvokeClient(), cache=EmbeddingCache()),
        probe=probe,
        corpus_head_wall=CORPUS_HEAD,
        **kwargs,
    )
    return backend, probe


def rows_at(*distances: float, severity: int = 3) -> list[AnnRow]:
    return [
        AnnRow(
            doc_id=f"D{index + 1}",
            distance=distance,
            severity=severity,
            within_wall=True,
            ann_rank=index + 1,
        )
        for index, distance in enumerate(distances)
    ]


# ═══════════════════════════════════════════════════════════════════════════════════════
# 1 · The protocol
# ═══════════════════════════════════════════════════════════════════════════════════════


def test_backend_satisfies_both_protocols() -> None:
    backend, _ = make_backend(rows_at(0.10))
    assert isinstance(backend, RetrievalBackend)
    assert isinstance(backend, ConservingBackend)
    assert backend.name


def test_retrieve_returns_scored_candidates_on_channel_c() -> None:
    backend, probe = make_backend(rows_at(0.10, 0.20, 0.90))
    query = make_query()
    candidates = asyncio.run(backend.retrieve(query, 10))

    assert [c.doc_id for c in candidates] == ["D1", "D2", "D3"]
    assert [c.rank for c in candidates] == [1, 2, 3]
    assert {c.channel for c in candidates} == {"C"}
    assert {c.origin for c in candidates} == {"recall_probabilistic"}
    # The permit's own prefix was used, and the wall passed to the probe is the permit's t.
    assert probe.seen[0]["site_id"] == site_uuid_of("MINE-4601731")
    assert probe.seen[0]["activity_root"] == "underground"
    assert probe.seen[0]["wall"] == query.wall
    assert probe.seen[0]["dim"] == EMBED_DIM


def test_routine_permit_is_walled_at_corpus_head() -> None:
    backend, probe = make_backend(rows_at(0.10))
    routine = make_query("Q-NC-1", kind="routine", severity=None, wall=None, truth_doc_id=None)
    asyncio.run(backend.retrieve(routine, 10))
    assert probe.seen[0]["wall"] == CORPUS_HEAD


def test_ann_limit_over_fetches_because_the_wall_is_applied_after_the_index() -> None:
    backend, probe = make_backend(rows_at(0.10))
    asyncio.run(backend.retrieve(make_query(), 10))
    assert probe.seen[0]["ann_limit"] >= 40
    assert probe.seen[0]["ann_limit"] >= 10


# ═══════════════════════════════════════════════════════════════════════════════════════
# 2 · The counters are independent of the candidate list
# ═══════════════════════════════════════════════════════════════════════════════════════


def test_declared_tally_matches_the_enumerated_tally_on_an_honest_run() -> None:
    backend, _ = make_backend(rows_at(0.10, 0.20, 0.30, 0.80))
    query = make_query()
    candidates = asyncio.run(backend.retrieve(query, 10))
    declared = asyncio.run(backend.declared_tally(query))
    enumerated = RunTally.enumerate_from(candidates)

    assert declared.conserved
    assert declared.n_candidates == enumerated.n_candidates
    for field in ("n_blocking", "n_advisory", "n_silenced", "n_deduped"):
        assert getattr(declared, field) == getattr(enumerated, field), field


def test_the_conservation_law_notices_a_candidate_removed_after_the_fact() -> None:
    """The destructive proof that the counters are not derived from the candidate list.

    If ``declared_tally`` returned ``RunTally.enumerate_from(candidates)``, deleting a
    candidate would delete it from both sides and the law would still close. It does not,
    because the declared side is re-derived from the probe rows and the published policy
    constants — so the deletion shows up exactly where an unaccounted candidate should.
    """
    backend, _ = make_backend(rows_at(0.10, 0.20, 0.30, 0.80))
    query = make_query()
    candidates = asyncio.run(backend.retrieve(query, 10))
    declared = asyncio.run(backend.declared_tally(query))

    tampered = QueryResult(
        query=query,
        candidates=tuple(candidates[:-1]),
        declared_tally=declared,
        latency_ms=1.0,
        backend_name=backend.name,
    )
    report = conservation([tampered], split_policy_id="test", expected_runs=1)
    assert not report.holds
    assert any("enumerated" in violation.detail for violation in report.violations)


def test_declared_tally_refuses_a_run_that_never_happened() -> None:
    backend, _ = make_backend(rows_at(0.10))
    with pytest.raises(RuntimeError, match="never"):
        asyncio.run(backend.declared_tally(make_query("Q-unseen")))


def test_declared_bonded_counters_are_zero_because_channel_b_is_absent() -> None:
    backend, _ = make_backend(
        [AnnRow(doc_id="F1", distance=0.05, severity=5, within_wall=True, ann_rank=1)]
    )
    query = make_query()
    asyncio.run(backend.retrieve(query, 10))
    declared = asyncio.run(backend.declared_tally(query))
    assert declared.n_bonded_sev5 == 0
    assert declared.n_bonded_sev5_blocking == 0


# ═══════════════════════════════════════════════════════════════════════════════════════
# 3 · The cap, the thresholds and the arithmetic
# ═══════════════════════════════════════════════════════════════════════════════════════


def test_the_probabilistic_cap_is_respected() -> None:
    # Six severity-5 rows at distance 0.05 all clear tau(5) = 0.35 comfortably.
    rows = [
        AnnRow(doc_id=f"D{i}", distance=0.05, severity=5, within_wall=True, ann_rank=i)
        for i in range(1, 7)
    ]
    backend, _ = make_backend(rows)
    query = make_query()
    candidates = asyncio.run(backend.retrieve(query, 10))
    blocking = [c for c in candidates if c.outcome == "blocking"]
    assert len(blocking) == BLOCKING_CAP_PROBABILISTIC
    assert len([c for c in candidates if c.outcome == "advisory"]) == 3

    declared = asyncio.run(backend.declared_tally(query))
    assert declared.n_blocking == BLOCKING_CAP_PROBABILISTIC


def test_below_tau_is_silence_and_carries_the_threshold_it_was_tested_against() -> None:
    # tau(1) = 0.85; a distance of 0.5 calibrates to 0.5 and is silenced.
    rows = [AnnRow(doc_id="D1", distance=0.5, severity=1, within_wall=True, ann_rank=1)]
    backend, _ = make_backend(rows)
    query = make_query()
    candidates = asyncio.run(backend.retrieve(query, 10))
    assert candidates[0].outcome == "silenced"
    assert candidates[0].tau_applied == pytest.approx(DEFAULT_TAU[1])


def test_severity_zero_is_admitted_at_the_strictest_threshold() -> None:
    rows = [AnnRow(doc_id="D1", distance=0.05, severity=0, within_wall=True, ann_rank=1)]
    backend, _ = make_backend(rows)
    query = make_query()
    candidates = asyncio.run(backend.retrieve(query, 10))
    assert candidates[0].severity == 1
    assert candidates[0].tau_applied == pytest.approx(DEFAULT_TAU[1])
    assert candidates[0].features["corpus_severity"] == pytest.approx(0.0)


def test_calibration_is_monotone_and_bounded() -> None:
    assert calibrate(0.0) == 1.0
    assert calibrate(1.0) == 0.0
    assert calibrate(2.0) == 0.0
    assert calibrate(0.25) > calibrate(0.75)
    assert 0.0 <= calibrate(0.4) <= 1.0
    assert CALIBRATION_ID == "declared_identity_v1"


def test_only_the_top_k_are_candidates() -> None:
    backend, _ = make_backend(rows_at(*[0.1 + i / 100 for i in range(20)]))
    candidates = asyncio.run(backend.retrieve(make_query(), 5))
    assert len(candidates) == 5
    assert [c.doc_id for c in candidates] == ["D1", "D2", "D3", "D4", "D5"]


# ═══════════════════════════════════════════════════════════════════════════════════════
# 4 · Residency
# ═══════════════════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    "model_id",
    [
        "global.cohere.embed-v4:0",
        "us.anthropic.claude-haiku-4-5-20251001-v1:0",
        "eu.amazon.titan-embed-text-v2:0",
        "apac.anthropic.claude-haiku-4-5-20251001-v1:0",
    ],
)
def test_cross_region_model_ids_are_refused(model_id: str) -> None:
    with pytest.raises(ResidencyRefused):
        assert_in_region(model_id)
    with pytest.raises(ResidencyRefused):
        TitanEmbedder(client=FakeInvokeClient(), model_id=model_id)


@pytest.mark.parametrize(
    "model_id",
    ["amazon.titan-embed-text-v2:0", "cohere.embed-english-v3", "au.anthropic.claude-x"],
)
def test_in_region_and_australian_profile_ids_are_accepted(model_id: str) -> None:
    assert assert_in_region(model_id) == model_id


def test_a_foreign_region_is_refused_even_with_a_legal_model_id() -> None:
    with pytest.raises(ResidencyRefused):
        TitanEmbedder(client=FakeInvokeClient(), region="us-east-1")


def test_the_package_rule_and_the_fleet_rule_refuse_the_same_prefixes() -> None:
    """The duplicated residency rule is asserted equal to the fleet's, not assumed equal.

    ``trappoint-recall`` is Apache-2.0 substrate and may not import a program from
    ``scripts/``; the copy is therefore deliberate, and this is the test that stops the two
    from drifting into disagreeing about what leaves the country.
    """
    from scripts.aws._common import CROSS_REGION_PREFIXES
    from trappoint_recall.eval import bedrock_backend

    assert bedrock_backend._CROSS_REGION_PREFIXES == CROSS_REGION_PREFIXES


# ═══════════════════════════════════════════════════════════════════════════════════════
# 5 · Template symmetry and the DDL copy
# ═══════════════════════════════════════════════════════════════════════════════════════


class _Record:
    external_ref = "2100141"
    site_ref = "MINE-4601731"
    activity_path = "/underground/ground-support-installation"
    asset_class = "roof-bolter"
    title = "Fall of roof"
    narrative = "the immediate roof failed over the working place"
    work_description = ""
    occurred_at = datetime(2009, 5, 1, tzinfo=UTC)
    ingested_at = datetime(2009, 6, 1, tzinfo=UTC)
    corpus_commit_at = datetime(2009, 6, 1, tzinfo=UTC)
    severity_actual = 4


def test_both_sides_of_the_index_are_embedded_through_one_template() -> None:
    prefix = "/underground/ground-support-installation | roof-bolter | narrative: "
    document = document_rows([_Record()], corpus_commit="sha256:deadbeef")[0]
    permit = query_embed_text(make_query())
    assert document["text"].startswith(prefix)
    assert permit.startswith(prefix)
    assert EMBED_TEMPLATE.count("{") == 4
    assert hashlib.sha256(EMBED_TEMPLATE.encode()).hexdigest() == EMBED_TEMPLATE_SHA256


def test_document_rows_carry_the_prefix_and_the_three_wall_timestamps() -> None:
    row = document_rows([_Record()], corpus_commit="sha256:deadbeef")[0]
    assert row["site_id"] == site_uuid_of("MINE-4601731")
    assert row["activity_root"] == activity_root_of("/underground/ground-support-installation")
    assert row["embed_model"] == TITAN_EMBED_MODEL_ID
    assert isinstance(row["commit_id"], bytes)
    for column in ("occurred_at", "ingested_at", "corpus_commit_at"):
        assert isinstance(row[column], datetime)


def test_a_lossy_vector_literal_is_impossible() -> None:
    values = [1 / 3] * EMBED_DIM
    literal = vector_literal(values)
    parsed = [float(x) for x in literal.strip("[]").split(",")]
    assert parsed == values
    with pytest.raises(ValueError, match="1024-d vector"):
        vector_literal([0.0, 1.0])


def _normalise_sql(text: str) -> str:
    """Strip line comments and collapse whitespace. Comments are prose, columns are the claim."""
    stripped = "\n".join(line.split("--", 1)[0] for line in text.splitlines())
    return re.sub(r"\s+", " ", stripped).strip().lower()


def test_the_evidence_ddl_is_the_migration_table_and_not_a_paraphrase() -> None:
    """The evidence surface is migration 0031's table, checked character by character.

    A recall number measured against a table that merely resembles the production sidecar
    is a number about a different index. The only permitted difference is
    ``IF NOT EXISTS``, because the loader is idempotent and the migration is not.
    """
    from scripts.aws.recall_real import EMBEDDING_DDL

    migration = (
        REPO_ROOT / "verticals/mainline/db/migrations/0031_clause_embedding.sql"
    ).read_text(encoding="utf-8")
    match = re.search(
        r"^CREATE TABLE mainline\.clause_embedding \(.*?^\);",
        migration,
        re.MULTILINE | re.DOTALL,
    )
    assert match is not None, "migration 0031 no longer declares the table at column 0"
    body = match.group(0).rstrip(";")
    assert _normalise_sql(EMBEDDING_DDL).replace("if not exists ", "") == _normalise_sql(body)


def test_the_ann_query_pins_the_index_and_constrains_both_prefix_columns() -> None:
    from trappoint_recall.eval.bedrock_backend import ANN_SQL

    assert "clause_embedding@ce_ann" in ANN_SQL
    assert "site_id = %(site_id)s" in ANN_SQL
    assert "activity_root = %(activity_root)s" in ANN_SQL
    assert "<=>" in ANN_SQL
    # The time wall is a predicate over all three timestamps, never AS OF SYSTEM TIME.
    for column in ("occurred_at", "ingested_at", "corpus_commit_at"):
        assert column in ANN_SQL
    assert "AS OF SYSTEM TIME" not in ANN_SQL.upper()


# ═══════════════════════════════════════════════════════════════════════════════════════
# 6 · The cache
# ═══════════════════════════════════════════════════════════════════════════════════════


def test_the_cache_makes_a_repeated_embedding_free(tmp_path: Path) -> None:
    client = FakeInvokeClient()
    cache = EmbeddingCache(path=tmp_path / "vectors.jsonl")
    embedder = TitanEmbedder(client=client, cache=cache)
    first = embedder.embed("isolate and prove zero energy")
    second = embedder.embed("isolate and prove zero energy")
    assert first == second
    assert len(client.calls) == 1
    assert embedder.calls == 1
    assert embedder.input_tokens > 0
    cache.close()

    reloaded = EmbeddingCache(path=tmp_path / "vectors.jsonl")
    warm = TitanEmbedder(client=FakeInvokeClient(), cache=reloaded)
    assert warm.embed("isolate and prove zero energy") == first
    assert warm.calls == 0


def test_the_cache_key_separates_two_embedding_spaces() -> None:
    a = EmbeddingCache.key_for("amazon.titan-embed-text-v2:0", 1024, True, "x")
    b = EmbeddingCache.key_for("amazon.titan-embed-text-v2:0", 256, True, "x")
    c = EmbeddingCache.key_for("cohere.embed-english-v3", 1024, True, "x")
    d = EmbeddingCache.key_for("amazon.titan-embed-text-v2:0", 1024, False, "x")
    assert len({a, b, c, d}) == 4


def test_no_aws_call_is_made_without_a_client_when_the_cache_is_warm(tmp_path: Path) -> None:
    """The whole suite's premise: nothing here needs credentials."""
    cache = EmbeddingCache(path=tmp_path / "vectors.jsonl")
    seeded = TitanEmbedder(client=FakeInvokeClient(), cache=cache)
    seeded.embed("permit text")
    cache.close()

    offline = TitanEmbedder(client=None, cache=EmbeddingCache(path=tmp_path / "vectors.jsonl"))
    assert len(offline.embed("permit text")) == EMBED_DIM
    assert offline.client is None


def test_embed_text_defaults_an_absent_asset_class_rather_than_dropping_the_field() -> None:
    rendered = embed_text(
        activity_path="/surface/haul-road-operations",
        asset_class="",
        facet="narrative",
        cue_text="grader on the ramp",
    )
    assert "| unspecified |" in rendered


# ═══════════════════════════════════════════════════════════════════════════════════════
# 7 · Throttling — the one Bedrock refusal that means "later"
# ═══════════════════════════════════════════════════════════════════════════════════════


class _ThrottleThenAnswer:
    """Refuses ``n`` times with a botocore-shaped ThrottlingException, then answers."""

    def __init__(self, refusals: int) -> None:
        self.refusals = refusals
        self.inner = FakeInvokeClient()

    def invoke_model(self, **kwargs: Any) -> dict[str, Any]:
        if self.refusals > 0:
            self.refusals -= 1
            error = RuntimeError("Too many requests")
            error.response = {"Error": {"Code": "ThrottlingException"}}  # type: ignore[attr-defined]
            raise error
        return self.inner.invoke_model(**kwargs)


class _RefuseWithValidationError:
    # The request never reaches arithmetic here, so the wire kwargs are deliberately
    # unread; the leading underscore says so rather than a suppression saying it.
    def invoke_model(self, **_kwargs: Any) -> dict[str, Any]:
        error = RuntimeError("bad body")
        error.response = {"Error": {"Code": "ValidationException"}}  # type: ignore[attr-defined]
        raise error


def test_a_throttle_is_retried_and_the_trip_count_is_published() -> None:
    slept: list[float] = []
    embedder = TitanEmbedder(
        client=_ThrottleThenAnswer(3),
        cache=EmbeddingCache(),
        sleep=slept.append,
        rand=lambda: 0.5,
    )
    assert len(embedder.embed("permit")) == EMBED_DIM
    assert embedder.throttle_retries == 3
    assert len(slept) == 3
    assert slept == sorted(slept), "backoff must not shrink between attempts"
    assert embedder.ledger()["throttle_retries"] == 3


def test_a_validation_error_is_not_retried_because_it_is_a_fact_about_the_request() -> None:
    slept: list[float] = []
    embedder = TitanEmbedder(
        client=_RefuseWithValidationError(), cache=EmbeddingCache(), sleep=slept.append
    )
    with pytest.raises(RuntimeError, match="bad body"):
        embedder.embed("permit")
    assert embedder.throttle_retries == 0
    assert slept == []


def test_a_throttle_that_never_clears_fails_the_run_rather_than_returning_a_vector() -> None:
    embedder = TitanEmbedder(
        client=_ThrottleThenAnswer(10_000),
        cache=EmbeddingCache(),
        throttle_attempts=4,
        sleep=lambda _seconds: None,
        rand=lambda: 0.5,
    )
    with pytest.raises(RuntimeError):
        embedder.embed("permit")
    assert embedder.throttle_retries == 4


def test_an_empty_partition_conserves_over_nothing_and_says_so() -> None:
    """A permit whose prefix partition is empty must still publish counters.

    Returning no candidates is a legitimate answer; publishing no counters is not. The
    conservation law would then be unverifiable for that permit, and the gate reads an
    unverifiable law as a failure rather than as a pass — so the backend has to declare
    zeros rather than decline to declare.
    """
    backend, _ = make_backend([])
    query = make_query()
    candidates = asyncio.run(backend.retrieve(query, 10))
    declared = asyncio.run(backend.declared_tally(query))
    assert candidates == []
    assert declared.n_candidates == 0
    assert declared.conserved
    assert RunTally.enumerate_from(candidates).n_candidates == declared.n_candidates


def test_the_backend_reports_what_the_wall_removed() -> None:
    probe = ScriptedProbe(rows_at(0.10, 0.20), n_probed=40)
    backend = BedrockBackend(
        embedder=TitanEmbedder(client=FakeInvokeClient(), cache=EmbeddingCache()),
        probe=probe,
        corpus_head_wall=CORPUS_HEAD,
    )
    asyncio.run(backend.retrieve(make_query(), 10))
    report = backend.run_report()
    assert report["rows_probed_total"] == 40
    assert report["rows_excluded_by_time_wall"] == 38
    assert report["queries_executed"] == 1
    assert report["embedding"]["model_id"] == TITAN_EMBED_MODEL_ID


def test_the_config_names_every_absent_channel() -> None:
    backend, _ = make_backend(rows_at(0.10))
    config = backend.config()
    assert config["channel"] == "C"
    assert config["origin"] == "recall_probabilistic"
    assert config["calibration"] == CALIBRATION_ID
    assert set(config["channels_absent"]) == {"A", "B", "C_sweep", "D"}
    assert config["blocking_cap_probabilistic"] == BLOCKING_CAP_PROBABILISTIC
    assert config["tau_table"] == dict(DEFAULT_TAU)
