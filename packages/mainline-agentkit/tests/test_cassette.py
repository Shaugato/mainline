# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The offline provider: keys, misses, drift, and the honesty of the recordings.

Two of these are about *this repository's* claims rather than about caching:

* every committed cassette declares ``provenance: "synthetic"``, because AWS
  credentials are not valid on the build machine and a fixture that looked like a
  recording of a real model would be a claim we cannot support;
* the local canonicaliser agrees with ``trappoint_jcs``, so the small copy in
  ``_canon`` is asserted against the authority rather than assumed equal to it.
"""

from __future__ import annotations

import json

import make_cassettes as recipes
import pytest
from mainline_agentkit import (
    TRIAGE,
    CassetteMiss,
    CassettePrefixDrift,
    CassetteStore,
    CassetteTransport,
    TransportUnavailable,
    UntrustedText,
    build_request,
    cassette_key,
)
from mainline_agentkit._canon import CanonError, canonical_json_bytes
from mainline_agentkit.cassette import PROVENANCE_SYNTHETIC, Interaction


def test_the_key_is_stable_and_domain_separated():
    first = cassette_key("triage", "v1", {"a": 1})
    assert first == cassette_key("triage", "v1", {"a": 1})
    # Without a separator, ("triage","v1") and ("triagev","1") would collide.
    assert cassette_key("triage", "v1", {"a": 1}) != cassette_key("triagev", "1", {"a": 1})
    assert cassette_key("triage", "v1", {"a": 1}) != cassette_key("triage", "v2", {"a": 1})
    # Member order in the input must not matter; JCS sorts.
    assert cassette_key("t", "v", {"a": 1, "b": 2}) == cassette_key("t", "v", {"b": 2, "a": 1})


def test_a_float_in_the_key_input_is_refused():
    with pytest.raises(CanonError, match="float refused"):
        cassette_key("triage", "v1", {"score": 0.1})


def test_the_key_ignores_the_per_request_sentinel(model_id, ctx_site):
    document = UntrustedText(text="anything at all", source_sha256="0" * 64)
    first = build_request(TRIAGE, document, ctx_site, model_id=model_id, sentinel="S-AAA")
    second = build_request(TRIAGE, document, ctx_site, model_id=model_id, sentinel="S-BBB")
    assert first.cassette_key == second.cassette_key
    assert first.body != second.body


def test_a_miss_is_fatal_and_never_falls_through(store, model_id, sentinel, ctx_site):
    unseen = UntrustedText(text="a document nobody recorded", source_sha256="9" * 64)
    request = build_request(TRIAGE, unseen, ctx_site, model_id=model_id, sentinel=sentinel)
    with pytest.raises(CassetteMiss) as excinfo:
        CassetteTransport(store).invoke(request)
    assert excinfo.value.key == request.cassette_key
    assert "never falls through" in str(excinfo.value)


def test_prefix_drift_is_fatal(transport, model_id, sentinel):
    # This cassette was recorded with a deliberately wrong prefix digest, standing in
    # for a rubric that was edited after the recording (decision A13).
    request = build_request(
        TRIAGE,
        recipes.DOC_PROCEDURE,
        {"site_code": "KAL-01", "corpus_commit": "5" * 64},
        model_id=model_id,
        sentinel=sentinel,
    )
    with pytest.raises(CassettePrefixDrift) as excinfo:
        transport.invoke(request)
    assert excinfo.value.recorded == "f" * 64
    assert excinfo.value.observed == request.prefix_digest


def test_a_replay_store_refuses_to_write(store):
    with pytest.raises(TransportUnavailable, match="refusing to write"):
        store.put(
            Interaction(
                key="0" * 64,
                profile_id="triage",
                prompt_version="v1",
                prefix_digest="0" * 64,
                model_id="au.anthropic.claude-opus-5",
                provenance=PROVENANCE_SYNTHETIC,
                response={},
                recorded_at="2026-08-07T00:00:00+00:00",
            )
        )


def test_an_unknown_mode_is_refused(tmp_path):
    with pytest.raises(TransportUnavailable, match="unknown cassette mode"):
        CassetteStore(tmp_path, mode="passthrough")


def test_a_malformed_cassette_names_its_missing_fields(tmp_path):
    (tmp_path / "abc.json").write_text(json.dumps({"key": "abc"}), encoding="utf-8")
    store = CassetteStore(tmp_path, mode="replay")
    with pytest.raises(TransportUnavailable, match="missing required fields"):
        store.get("abc")


def test_every_committed_cassette_is_declared_synthetic(store, cassette_dir):
    keys = store.keys()
    assert keys, "the committed cassette store is empty"
    for key in keys:
        interaction = store.get(key)
        assert interaction.provenance == PROVENANCE_SYNTHETIC, (
            f"{key} claims provenance {interaction.provenance!r}. AWS credentials are "
            f"not valid on the build machine, so no cassette here was recorded live."
        )
        assert interaction.key == key
    assert len(keys) == len(list(cassette_dir.glob("*.json")))


def test_round_trip_record_then_replay(tmp_path, model_id, sentinel, ctx_site):
    document = UntrustedText(text="a fresh document", source_sha256="7" * 64)
    request = build_request(TRIAGE, document, ctx_site, model_id=model_id, sentinel=sentinel)
    recorder = CassetteStore(tmp_path, mode="record")
    recorder.record(
        request,
        {
            "content": [{"type": "text", "text": json.dumps(recipes.GOOD_TRIAGE)}],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 10, "output_tokens": 20},
            "model": "au.anthropic.claude-opus-5",
        },
    )
    replayed = CassetteTransport(CassetteStore(tmp_path, mode="replay")).invoke(request)
    assert replayed.stop_reason == "end_turn"
    assert json.loads(replayed.last_text_block() or "") == recipes.GOOD_TRIAGE


def test_agrees_with_trappoint_jcs():
    jcs = pytest.importorskip(
        "trappoint_jcs",
        reason="trappoint-jcs is a sibling workspace member; not installed in a bare "
        "checkout of mainline-agentkit alone",
    )
    vectors = [
        {},
        {"a": 1, "b": [1, 2, 3]},
        {"b": True, "a": None},
        {"é": "café", "z": '\n"\\'},
        {"nested": {"z": [{"k": 1}, {"j": 2}]}},
        {"😀": "emoji key sorts by UTF-16 code unit"},
        [1, "two", None, True],
    ]
    for vector in vectors:
        assert canonical_json_bytes(vector) == jcs.canonicalise(vector), vector
