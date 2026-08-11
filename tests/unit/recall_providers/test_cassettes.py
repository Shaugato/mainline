# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""Cassette round-trip determinism, tamper evidence, and the recording opt-in."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from mainline_recall_agent.providers.base import embed_text
from mainline_recall_agent.providers.canonical import request_digest
from mainline_recall_agent.providers.cassette import (
    LIVE_PROVENANCE,
    CassetteStore,
    RecordingEmbeddingProvider,
    ReplayEmbeddingProvider,
    assert_recording_permitted,
    embed_request,
)
from mainline_recall_agent.providers.errors import (
    CassetteMiss,
    CassetteRecordingNotPermitted,
    CassetteTampered,
)
from mainline_recall_agent.providers.projection import load_projection
from mainline_recall_agent.providers.surrogate import SURROGATE_MODEL_ID, SurrogateEmbedder
from mainline_recall_agent.providers.types import EMBED_DIM


def test_committed_cassettes_all_load_and_self_verify(store: CassetteStore) -> None:
    documents = store.iter_documents()
    assert documents, "no cassettes are committed; replay would be vacuous"
    for document in documents:
        assert document["request_digest"] == request_digest(document["request"])


def test_every_cassette_declares_its_provenance(store: CassetteStore) -> None:
    """Handwritten fixtures and real recordings must never be mistaken for one another."""
    for document in store.iter_documents():
        assert document["provenance"] in {"handwritten", "surrogate", *LIVE_PROVENANCE}


def test_judge_cassettes_are_currently_handwritten_and_say_so(store: CassetteStore) -> None:
    """The honest statement, asserted rather than left in a README.

    AWS credentials are not valid on the build machine, so no committed judge cassette can
    be a recording of Claude.  When ``GT-RC-01`` passes and real cassettes are recorded,
    this test is the thing that has to be consciously updated — which is the point.
    """
    judge_documents = store.iter_documents("judge")
    assert judge_documents
    for document in judge_documents:
        assert document["provenance"] == "handwritten", (
            "a judge cassette claims live provenance; if that is now true, update this "
            "test and the README's honesty note together"
        )


def test_a_cassette_edited_by_hand_fails_to_load(tmp_path: Path) -> None:
    store = CassetteStore(tmp_path)
    request = {"kind": "judge", "a": 1}
    path = store.save(
        "judge", request, {"stop_reason": "end_turn", "text": "{}"}, provenance="handwritten"
    )
    document = json.loads(path.read_text(encoding="utf-8"))
    document["request"]["a"] = 2  # "the model was asked something else"
    path.write_text(json.dumps(document), encoding="utf-8")
    # Loaded by the request the filename still claims: the stored request no longer hashes
    # to the digest it is filed under, and the store refuses rather than serving it.
    with pytest.raises(CassetteTampered, match="does not hash"):
        store.load("judge", request)


def test_a_cassette_with_an_unknown_provenance_fails_to_load(tmp_path: Path) -> None:
    store = CassetteStore(tmp_path)
    request = {"kind": "judge", "a": 1}
    path = store.save(
        "judge", request, {"stop_reason": "end_turn", "text": "{}"}, provenance="handwritten"
    )
    document = json.loads(path.read_text(encoding="utf-8"))
    document["provenance"] = "definitely-real"
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(CassetteTampered, match="provenance"):
        store.load("judge", request)


def test_regenerating_an_unchanged_constructed_cassette_produces_no_diff(
    tmp_path: Path,
) -> None:
    """The fixture set must regenerate to the same bytes, or review stops working.

    If every regeneration re-stamped ``recorded_at``, a real change to a fixture — the kind
    a gate test depends on — would arrive in a diff of 32 files that all look changed, and
    nobody would find it.  A constructed cassette is not an observation, so its timestamp
    is stable while its content is.
    """
    store = CassetteStore(tmp_path)
    request = {"kind": "judge", "scenario": "clean"}
    response = {"stop_reason": "end_turn", "text": "{}"}
    path = store.save("judge", request, response, provenance="handwritten", note="n")

    # Age the artefact deliberately.  Two saves inside one second would agree by accident
    # and prove nothing, so the committed timestamp is moved far enough that "kept" and
    # "re-stamped" cannot be confused.
    aged = json.loads(path.read_text(encoding="utf-8"))
    aged["recorded_at"] = "2020-01-01T00:00:00+00:00"
    path.write_text(json.dumps(aged, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    before = path.read_bytes()

    store.save("judge", request, response, provenance="handwritten", note="n")
    assert path.read_bytes() == before
    assert json.loads(path.read_text(encoding="utf-8"))["recorded_at"] == aged["recorded_at"]


def test_a_changed_constructed_cassette_does_get_a_fresh_timestamp(tmp_path: Path) -> None:
    """Stability must not shade into staleness: changed content is newly constructed."""
    store = CassetteStore(tmp_path)
    request = {"kind": "judge", "scenario": "clean"}
    path = store.save(
        "judge", request, {"stop_reason": "end_turn", "text": "{}"}, provenance="handwritten"
    )
    stale = json.loads(path.read_text(encoding="utf-8"))
    stale["recorded_at"] = "2020-01-01T00:00:00+00:00"
    path.write_text(json.dumps(stale, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    store.save(
        "judge",
        request,
        {"stop_reason": "end_turn", "text": '{"changed": true}'},
        provenance="handwritten",
    )
    assert json.loads(path.read_text(encoding="utf-8"))["recorded_at"] != stale["recorded_at"]


def test_a_live_cassette_always_restamps_because_its_timestamp_is_evidence(
    tmp_path: Path,
) -> None:
    """A live recording's ``recorded_at`` says when the call was observed. Never reused."""
    store = CassetteStore(tmp_path)
    request = {"kind": "judge", "scenario": "clean"}
    response = {"stop_reason": "end_turn", "text": "{}"}
    path = store.save("judge", request, response, provenance="bedrock-live")
    forged = json.loads(path.read_text(encoding="utf-8"))
    forged["recorded_at"] = "2020-01-01T00:00:00+00:00"
    path.write_text(json.dumps(forged, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    store.save("judge", request, response, provenance="bedrock-live")
    assert json.loads(path.read_text(encoding="utf-8"))["recorded_at"] != forged["recorded_at"]


def test_a_miss_names_the_digest_and_how_to_record_it(store: CassetteStore) -> None:
    with pytest.raises(CassetteMiss) as excinfo:
        store.load("embed", embed_request(embed_model="nope", facet="mechanism", text="unseen"))
    message = str(excinfo.value)
    assert "MAINLINE_RECALL_CASSETTE_MODE=record" in message
    assert len(excinfo.value.context["digest"]) == 64


def test_recording_requires_both_opt_ins(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(CassetteRecordingNotPermitted, match="CASSETTE_MODE=record"):
        assert_recording_permitted()
    monkeypatch.setenv("MAINLINE_RECALL_CASSETTE_MODE", "record")
    with pytest.raises(CassetteRecordingNotPermitted, match="ALLOW_NETWORK"):
        assert_recording_permitted()
    monkeypatch.setenv("MAINLINE_RECALL_ALLOW_NETWORK", "1")
    assert_recording_permitted()


def test_a_recording_provider_cannot_be_constructed_by_default() -> None:
    with pytest.raises(CassetteRecordingNotPermitted):
        RecordingEmbeddingProvider(SurrogateEmbedder(), provenance="surrogate")


def _replay_provider(store: CassetteStore) -> ReplayEmbeddingProvider:
    projection = load_projection()
    return ReplayEmbeddingProvider(
        model_id=SURROGATE_MODEL_ID,
        index_gen=f"surrogate-1+{projection.projection_id}",
        is_semantic=False,
        coarse_impl=projection.project,
        store=store,
    )


def test_replay_reproduces_the_recorded_vectors_bit_for_bit(
    store: CassetteStore, fixture_corpus: list[dict[str, Any]]
) -> None:
    facet = "mechanism"
    texts = [
        embed_text(
            activity_path=entry["activity_path"],
            asset_class=entry["asset_class"],
            facet=facet,
            cue_text=entry["facets"][facet],
        )
        for entry in fixture_corpus
    ]
    replayed = _replay_provider(store).embed(texts, facet)
    computed = SurrogateEmbedder().embed(texts, facet)
    assert len(replayed) == len(fixture_corpus)
    assert replayed == computed


def test_replay_is_stable_across_two_reads(
    store: CassetteStore, fixture_corpus: list[dict[str, Any]]
) -> None:
    facet = "recurrence_test"
    text = embed_text(
        activity_path=fixture_corpus[0]["activity_path"],
        asset_class=fixture_corpus[0]["asset_class"],
        facet=facet,
        cue_text=fixture_corpus[0]["facets"][facet],
    )
    provider = _replay_provider(store)
    assert provider.embed([text], facet) == provider.embed([text], facet)


def test_replay_coarse_is_computed_not_replayed(store: CassetteStore) -> None:
    """Coarse is client-side arithmetic; replaying it would hide our own regressions."""
    provider = _replay_provider(store)
    vector = SurrogateEmbedder().embed(["a cue about stored energy release"], "mechanism")[0]
    assert provider.coarse([vector]) == SurrogateEmbedder().coarse([vector])


def test_batching_does_not_change_the_key(
    store: CassetteStore, fixture_corpus: list[dict[str, Any]]
) -> None:
    """One cassette per text: a caller changing its chunking must not miss."""
    facet = "mechanism"
    texts = [
        embed_text(
            activity_path=entry["activity_path"],
            asset_class=entry["asset_class"],
            facet=facet,
            cue_text=entry["facets"][facet],
        )
        for entry in fixture_corpus[:4]
    ]
    provider = _replay_provider(store)
    whole = provider.embed(texts, facet)
    split = provider.embed(texts[:1], facet) + provider.embed(texts[1:], facet)
    assert whole == split


def test_the_store_refuses_an_unknown_kind_or_a_malformed_digest(tmp_path: Path) -> None:
    from mainline_recall_agent.providers.errors import ProviderError

    store = CassetteStore(tmp_path)
    with pytest.raises(ProviderError):
        store.path_for("transcript", "0" * 64)
    with pytest.raises(ProviderError):
        store.path_for("judge", "NOTHEX")


def test_embed_request_shape_is_stable() -> None:
    request = embed_request(embed_model="m", facet="mechanism", text="t")
    assert request == {
        "kind": "embed",
        "embed_model": "m",
        "facet": "mechanism",
        "dim": EMBED_DIM,
        "side": "document",
        "text": "t",
    }
