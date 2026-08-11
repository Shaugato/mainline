# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The live store, checked with no credential, no network and no AWS SDK.

``cassettes_live/`` holds interactions recorded from
``au.anthropic.claude-haiku-4-5-20251001-v1:0`` in ``ap-southeast-2``. Everything asserted
here is a property of the committed bytes, so this file runs on a stranger's laptop and in
CI — the same rule ``conftest.py`` states for the rest of the package, and the reason the
live lane is worth having at all: *evidence that needs the endpoint back to be checked is
not evidence.*

Four claims, in the order a sceptic would test them:

1. **The store says what it is.** Every interaction and every index row declares
   ``provenance: "live"`` and the model that served it. Nothing here infers liveness from
   the absence of a synthetic marker.
2. **The digests recompute.** The filename is re-derived from the recorded call identity by
   the *shipping* :func:`cassette_key`, and the recorded response and cassette hashes are
   recomputed from the bytes. A cassette whose name was chosen by hand fails here.
3. **Replay is deterministic.** ``quarantined_call`` runs twice over the store and the two
   replayability records are identical, field for field.
4. **A tampered cassette fails to load.** Prefix drift, a renamed key and a replay-mode
   write all raise. The point of the cassette is that a fixture cannot be edited into
   agreeing with the code that reads it.

The store is **key-compatible** with the synthetic store, and
:func:`test_live_and_synthetic_stores_share_keys` is the assertion that makes
``MAINLINE_CASSETTE_DIR`` the whole of the switch between them.
"""

from __future__ import annotations

import json
from pathlib import Path

import make_live_cassettes as live
import pytest
from mainline_agentkit import (
    CassetteMiss,
    CassettePrefixDrift,
    CassetteStore,
    CassetteTransport,
    Interaction,
    ModelRequest,
    TransportUnavailable,
    assert_no_sampling_params,
    assert_no_tool_surface,
    build_request,
    cassette_key,
    quarantined_call,
)
from mainline_agentkit._canon import canonical_json_bytes, sha256_hex, stable_json_bytes
from mainline_agentkit.cassette import PROVENANCE_LIVE, PROVENANCE_SYNTHETIC

LIVE_DIR = live.LIVE_DIR
SYNTHETIC_DIR = Path(__file__).resolve().parent / "cassettes"


def _index() -> dict:
    return json.loads(live.INDEX_PATH.read_text(encoding="utf-8"))


def _cassette_paths() -> list[Path]:
    return sorted(path for path in LIVE_DIR.glob("*.json") if path.name != "INDEX.json")


def _document(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture
def index() -> dict:
    return _index()


@pytest.fixture
def live_store() -> CassetteStore:
    return CassetteStore(LIVE_DIR, mode="replay")


# ── 1. the store says what it is ────────────────────────────────────────────────


def test_the_live_store_exists_and_is_indexed(index):
    assert LIVE_DIR.is_dir(), f"{LIVE_DIR} is missing; record it with make_live_cassettes.py"
    assert index["schema"] == live.INDEX_SCHEMA
    assert index["count"] == len(index["entries"]) == len(_cassette_paths())
    assert index["region"] == "ap-southeast-2"
    assert index["model_id"] == live.LIVE_MODEL_ID


def test_every_index_row_declares_live_provenance(index):
    assert index["provenance"] == PROVENANCE_LIVE
    assert [row["provenance"] for row in index["entries"]] == [PROVENANCE_LIVE] * index["count"]


def test_every_cassette_declares_live_provenance_and_the_live_model():
    paths = _cassette_paths()
    assert paths, "the live store is empty"
    for path in paths:
        interaction = Interaction.from_json(_document(path))
        assert interaction.provenance == PROVENANCE_LIVE, path.name
        assert interaction.model_id == live.LIVE_MODEL_ID, path.name
        assert interaction.recorded_at, f"{path.name} has no recording timestamp"


def test_the_index_covers_every_profile_in_the_fleet(index):
    """Five profiles, and the index proves each one was actually exercised live."""
    recorded = {row["profile"] for row in index["entries"]}
    assert recorded == {
        "adjudication",
        "disposition_assistant",
        "extraction",
        "narration",
        "triage",
    }


def test_the_wire_projection_is_declared_field_by_field(index):
    """A projection nobody can see is a body edit; this is the record of what was touched."""
    projection = index["wire_projection"]
    assert projection["id"] == live.WIRE_PROJECTION_ID
    assert projection["sampling_parameters_sent"] == []
    refused = {item["field"] for item in projection["measured_refusals"]}
    assert refused == {
        "output_config.effort",
        "output_config.format.name",
        "thinking.type=adaptive",
    }
    for row in index["entries"]:
        assert row["wire_projection"] == live.WIRE_PROJECTION_ID
        assert row["wire_projection_applied"], f"{row['scenario']} claims no projection at all"


# ── 2. the digests recompute ────────────────────────────────────────────────────


def test_every_filename_is_what_the_shipping_key_rule_produces(index):
    """The name is re-derived, not trusted.

    ``cassette_key`` is the function the transport uses to *look a cassette up*. Running it
    over the recorded call identity and getting the filename back is the only check that
    rules out a store whose names were chosen rather than computed.
    """
    for row in index["entries"]:
        recomputed = cassette_key(row["profile"], row["prompt_version"], row["call_input"])
        assert recomputed == row["digest"], row["scenario"]
        assert (LIVE_DIR / f"{recomputed}.json").is_file()
        assert sha256_hex(canonical_json_bytes(row["call_input"])) == row["input_sha256"]


def test_every_recorded_body_hashes_to_its_index_row(index):
    for row in index["entries"]:
        path = LIVE_DIR / row["file"]
        document = _document(path)
        assert document["key"] == row["digest"] == path.stem
        assert sha256_hex(stable_json_bytes(document["response"])) == row["response_sha256"]
        assert sha256_hex(path.read_bytes()) == row["cassette_sha256"]


def test_an_edited_response_no_longer_hashes_to_its_row(index):
    """The counter-test. Without it the previous assertion could be hashing nothing."""
    row = index["entries"][0]
    document = _document(LIVE_DIR / row["file"])
    tampered = dict(document["response"])
    tampered["stop_reason"] = "refusal"
    assert sha256_hex(stable_json_bytes(tampered)) != row["response_sha256"]


def test_the_shipping_builder_lands_on_the_recorded_keys(index):
    """Rebuild every scenario with ``build_request`` and find it in the store.

    This is the assertion that ties the store to the code rather than to the index: if a
    prompt is edited, ``prompt_version`` moves, the key moves, and this fails as a miss —
    which is decision A13 working, not a flaky test.
    """
    rows = {row["scenario"]: row for row in index["entries"] if row["attempt"] == 1}
    for scenario in live.scenarios():
        request = build_request(
            scenario["profile"],
            scenario["untrusted"],
            scenario["ctx"],
            model_id=live.LIVE_MODEL_ID,
            sentinel=live.SENTINEL,
        )
        row = rows[scenario["name"]]
        assert request.cassette_key == row["digest"]
        assert request.prefix_digest == row["prefix_digest"]
        assert request.input_sha256 == row["input_sha256"]


# ── 3. replay is deterministic ──────────────────────────────────────────────────


def _replay_once(scenario: dict, store: CassetteStore) -> dict:
    """One full ``quarantined_call`` against the live store, reduced to its record."""
    validated = quarantined_call(
        scenario["profile"],
        scenario["untrusted"],
        scenario["ctx"],
        transport=CassetteTransport(store),
        model_id=live.LIVE_MODEL_ID,
        sentinel=live.SENTINEL,
    )
    return {
        "provenance": validated.provenance(),
        "value": json.loads(validated.value.model_dump_json()),
    }


@pytest.mark.parametrize("scenario", live.scenarios(), ids=lambda item: item["name"])
def test_replaying_the_live_store_twice_gives_the_same_record(scenario, live_store):
    first = _replay_once(scenario, live_store)
    second = _replay_once(scenario, live_store)
    assert first == second
    assert sha256_hex(stable_json_bytes(first)) == sha256_hex(stable_json_bytes(second))
    # Not vacuous: the record has to carry the identity of the live call it replayed.
    assert first["provenance"]["model_id"] == live.LIVE_MODEL_ID
    assert first["provenance"]["stop_reason"] == "end_turn"


def test_replay_reaches_the_live_model_output_not_the_synthetic_one():
    """The two stores answer the same key differently, and that difference is the evidence.

    ``triage.poisoned`` is the sharpest case: the synthetic cassette encodes what we
    *believed* a working quarantine looks like (``abstained: true``), and the live model
    read the injected instruction as data and routed the document anyway. Both are correct
    behaviour under the rubric; only one of them is an observation.
    """
    scenario = next(item for item in live.scenarios() if item["name"] == "triage.poisoned")
    request = build_request(
        scenario["profile"],
        scenario["untrusted"],
        scenario["ctx"],
        model_id=live.LIVE_MODEL_ID,
        sentinel=live.SENTINEL,
    )
    synthetic = CassetteStore(SYNTHETIC_DIR, mode="replay").get(request.cassette_key)
    recorded = CassetteStore(LIVE_DIR, mode="replay").get(request.cassette_key)
    assert synthetic.provenance == PROVENANCE_SYNTHETIC
    assert recorded.provenance == PROVENANCE_LIVE
    assert dict(synthetic.response) != dict(recorded.response)
    # The live answer names no defeater code and carries no field the injection asked for.
    text = str(recorded.response["content"][-1]["text"])
    assert "SUPERSEDED" not in text
    assert json.loads(text)["basis_quote"] == "SOP-207 ISOLATION VERIFICATION"


def test_live_and_synthetic_stores_share_keys():
    """Key-compatibility, asserted rather than assumed.

    The key carries neither the model id nor the response, so a scenario recorded in both
    lanes lands on the same filename in both stores. That is what makes
    ``MAINLINE_CASSETTE_DIR`` the entire switch between synthetic and live evidence, with
    no call site aware of which one it got.
    """
    live_keys = {path.stem for path in _cassette_paths()}
    synthetic_keys = {path.stem for path in SYNTHETIC_DIR.glob("*.json")}
    assert live_keys <= synthetic_keys, sorted(live_keys - synthetic_keys)
    assert len(synthetic_keys) == 20, "the 20 committed synthetic cassettes must not move"


def test_the_synthetic_store_is_still_synthetic():
    """The live lane writes a sibling directory and never the committed one."""
    for path in sorted(SYNTHETIC_DIR.glob("*.json")):
        assert Interaction.from_json(_document(path)).provenance == PROVENANCE_SYNTHETIC


# ── 4. a tampered cassette fails to load ────────────────────────────────────────


def test_prefix_drift_refuses_the_replay(tmp_path, index):
    """A cassette recorded against a rubric that has since been edited does not replay."""
    row = index["entries"][0]
    document = _document(LIVE_DIR / row["file"])
    document["prefix_digest"] = "f" * 64
    (tmp_path / row["file"]).write_text(json.dumps(document), encoding="utf-8")
    transport = CassetteTransport(CassetteStore(tmp_path, mode="replay"))
    request = ModelRequest(
        body={},
        model_id=live.LIVE_MODEL_ID,
        profile_id=row["profile"],
        prompt_version=row["prompt_version"],
        cassette_key=row["digest"],
        prefix_digest=row["prefix_digest"],
        input_sha256=row["input_sha256"],
    )
    with pytest.raises(CassettePrefixDrift):
        transport.invoke(request)


def test_a_renamed_cassette_is_a_miss_not_a_silent_substitution(tmp_path, index):
    row = index["entries"][0]
    (tmp_path / f"{'a' * 64}.json").write_text(
        json.dumps(_document(LIVE_DIR / row["file"])), encoding="utf-8"
    )
    store = CassetteStore(tmp_path, mode="replay")
    with pytest.raises(CassetteMiss):
        store.get(row["digest"])


def test_a_replay_mode_store_refuses_to_write(live_store, index):
    """*Fails to load* is only half of it: replay must also refuse to rewrite a fixture."""
    row = index["entries"][0]
    interaction = Interaction.from_json(_document(LIVE_DIR / row["file"]))
    with pytest.raises(TransportUnavailable, match="replay mode"):
        live_store.put(interaction)


def test_recording_needs_both_live_opt_ins(monkeypatch):
    """Neither switch alone opens the live lane; the message names the missing one."""
    with pytest.raises(live.LiveRecordingRefused, match="MAINLINE_AGENT_ALLOW_LIVE"):
        live.assert_live_recording_permitted()
    monkeypatch.setenv("MAINLINE_AGENT_ALLOW_LIVE", "1")
    with pytest.raises(live.LiveRecordingRefused, match="MAINLINE_CASSETTE_MODE"):
        live.assert_live_recording_permitted()
    monkeypatch.setenv("MAINLINE_CASSETTE_MODE", "record")
    live.assert_live_recording_permitted()


# ── decision A6, on the bytes that actually went on the wire ────────────────────


@pytest.mark.parametrize("scenario", live.scenarios(), ids=lambda item: item["name"])
def test_the_projected_body_carries_no_sampling_parameter(scenario):
    """The recorder projects the body for this model generation; A6 survives the projection."""
    request = build_request(
        scenario["profile"],
        scenario["untrusted"],
        scenario["ctx"],
        model_id=live.LIVE_MODEL_ID,
        sentinel=live.SENTINEL,
    )
    projected, applied = live.project_for_wire(request.body, effort=str(scenario["profile"].effort))
    assert_no_sampling_params(projected)
    assert_no_tool_surface(projected)
    assert "effort" not in projected["output_config"]
    assert "name" not in projected["output_config"]["format"]
    assert projected["thinking"]["type"] == "enabled"
    # Everything the projection is *not* allowed to touch.
    assert projected["system"] == request.body["system"]
    assert projected["messages"] == request.body["messages"]
    assert projected["max_tokens"] == request.body["max_tokens"]
    assert (
        projected["output_config"]["format"]["schema"]
        == request.body["output_config"]["format"]["schema"]
    )
    assert len(applied) == 3
