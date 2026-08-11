# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Record the **live** cassette store from Amazon Bedrock.  Sibling of ``make_cassettes.py``.

    AWS_PROFILE=mainline-dev \\
    MAINLINE_AGENT_PROVIDER=bedrock MAINLINE_AGENT_ALLOW_LIVE=1 \\
    MAINLINE_CASSETTE_MODE=record \\
    python packages/mainline-agentkit/tests/make_live_cassettes.py

**These cassettes are LIVE and every one of them says so.**  ``make_cassettes.py`` writes
``packages/mainline-agentkit/tests/cassettes/`` and every interaction there carries
``"provenance": "synthetic"``; its docstring says *"the day the live lane records real ones
they carry ``provenance: 'live'``"*.  This is that day and this is that lane.  It writes a
**separate** store, ``cassettes_live/``, because ``make_cassettes.py`` begins by
``shutil.rmtree``-ing its own directory and would delete anything recorded into it.

The two stores are deliberately **key-compatible**.  A cassette key is
``sha256(profile_id ‖ 0x1f ‖ prompt_version ‖ 0x1f ‖ jcs(input))`` and carries neither the
model id nor the response, so the scenarios shared with ``make_cassettes.py`` land on the
same filenames in both stores.  Pointing ``MAINLINE_CASSETTE_DIR`` at ``cassettes_live``
therefore swaps synthetic evidence for live evidence **without changing a call site**, and
:mod:`test_live_cassettes` asserts that overlap rather than leaving it to be noticed.

Three refusals this program keeps
---------------------------------
**No hand-computed key.**  Every key comes from ``build_request(...).cassette_key`` — the
shipping builder — so a change to the key rule regenerates this store instead of silently
orphaning it.  Nothing here reimplements the hash.

**No sampling parameter.**  Decision A6.  Nothing in this file constructs one, the
projection below re-runs :func:`assert_no_sampling_params` on the exact bytes that go on the
wire, and ``test_no_sampling_params.py`` plus ``mainline-boundary``'s ``GREP-SAMPLING-PARAM``
police the source.  A parameter that cannot exist cannot be blamed for drift.

**No silent body edit.**  ``au.anthropic.claude-haiku-4-5-20251001-v1:0`` **refuses three
fields of the shipping body**, measured on 2026-08-11 from this workstation:

===================================  =========================================================
field                                verbatim ``ValidationException``
===================================  =========================================================
``output_config.effort``             ``output_config.effort: Extra inputs are not permitted``
``output_config.format.name``        ``output_config.format.name: Extra inputs are not permitted``
``thinking: {"type": "adaptive"}``   ``adaptive thinking is not supported on this model``
===================================  =========================================================

The shipping body targets the pinned ``claude-opus-5`` generation, which accepts all three.
:func:`project_for_wire` is the **only** place the difference is applied, it names every
field it touches, the list it applied is written into ``INDEX.json`` per cassette, and
``evidence/aws/agent/live-run.json`` carries the refusals verbatim.  A projection nobody can
see is a body edit; a projection recorded field by field is a finding.

What is being claimed, and what is not
--------------------------------------
The documents are the same fabricated MAINLINE-shaped strings ``make_cassettes.py`` uses —
imported from it rather than copied, so the two lanes cannot drift.  They are **not** real
incident data.  These cassettes are evidence that *Bedrock executed for MAINLINE and what it
returned is on disk byte-for-byte*; they are not evidence about any mine, any permit or any
fatality.
"""

from __future__ import annotations

import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_TESTS = Path(__file__).resolve().parent
_SRC = _TESTS.parent / "src"
_REPO = _TESTS.parents[2]
for _entry in (str(_SRC), str(_TESTS), str(_REPO / "scripts")):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

from mainline_agentkit import (  # noqa: E402 - the path shim above must run first
    ADJUDICATION,
    DISPOSITION_ASSISTANT,
    EXTRACTION,
    NARRATION,
    TRIAGE,
    AgentkitSettings,
    CassetteStore,
    SchemaViolation,
    UntrustedText,
    assert_no_sampling_params,
    assert_no_tool_surface,
    build_request,
)
from mainline_agentkit._canon import sha256_hex, stable_json_bytes  # noqa: E402
from mainline_agentkit.cassette import PROVENANCE_LIVE, Interaction  # noqa: E402
from make_cassettes import (  # noqa: E402 - the sentinel/document discipline, not a copy of it
    CTX_SITE,
    DOC_CONFLICT,
    DOC_INCIDENT,
    DOC_POISONED,
    DOC_PROCEDURE,
    SENTINEL,
)

#: Where the live store lives.  A **sibling** of ``cassettes/``, never inside it.
LIVE_DIR = _TESTS / "cassettes_live"
INDEX_PATH = LIVE_DIR / "INDEX.json"

#: The model that actually served these cassettes.  A bare ``au.*`` inference-profile id,
#: which ``assert_australian_profile`` accepts and ``scripts/aws/_common.assert_in_region``
#: agrees is in-region: ``ap-southeast-2``, no ``global.``/``apac.`` routing prefix.
LIVE_MODEL_ID = "au.anthropic.claude-haiku-4-5-20251001-v1:0"

#: Identifies the projection rule, so a cassette recorded under a different rule is
#: distinguishable from one recorded under this one without reading the diff.
WIRE_PROJECTION_ID = "au.claude-haiku-4-5.invoke-model/1"

#: What ``thinking: {"type": "adaptive"}`` becomes on a generation that has no adaptive
#: mode, keyed by the profile's declared effort.  Decision A5 writes thinking explicitly on
#: every call and never disables it; this preserves that intent in the spelling this model
#: accepts.  1024 is the vendor minimum; the high band is held at 2048 to bound the spend.
THINKING_BUDGET: dict[str, int] = {"low": 1024, "high": 2048}

INDEX_SCHEMA = "mainline.agentkit.live-cassette-index/1"

#: The three refusals measured on 2026-08-11, verbatim, so the projection below can be
#: read against the reason for it rather than taken on trust.
MEASURED_REFUSALS: tuple[dict[str, str], ...] = (
    {
        "field": "output_config.effort",
        "error_type": "ValidationException",
        "error_message_verbatim": "output_config.effort: Extra inputs are not permitted",
    },
    {
        "field": "output_config.format.name",
        "error_type": "ValidationException",
        "error_message_verbatim": "output_config.format.name: Extra inputs are not permitted",
    },
    {
        "field": "thinking.type=adaptive",
        "error_type": "ValidationException",
        "error_message_verbatim": "adaptive thinking is not supported on this model",
    },
)


class LiveRecordingRefused(RuntimeError):
    """Recording was attempted without both live opt-ins."""


def assert_live_recording_permitted(settings: AgentkitSettings | None = None) -> None:
    """Recording is opt-in twice over, and this says which switch is missing.

    The same posture ``mainline_recall_agent.providers.cassette.assert_recording_permitted``
    takes for the recall store, spelled in this package's own environment variables so one
    lane cannot unlock the other: ``MAINLINE_AGENT_ALLOW_LIVE=1`` is the transport's live
    lock (``select_transport`` refuses to build ``BedrockTransport`` without it) and
    ``MAINLINE_CASSETTE_MODE=record`` is the store's write lock (``CassetteStore.put``
    refuses to write in ``replay``).  Both are read through the shipping
    :class:`AgentkitSettings`, never re-parsed here.
    """
    resolved = settings or AgentkitSettings.from_env()
    if not resolved.allow_live:
        raise LiveRecordingRefused(
            "recording a live cassette requires MAINLINE_AGENT_ALLOW_LIVE=1; a live call "
            "that happens by accident costs money and non-determinism, so it fails loudly"
        )
    if resolved.cassette_mode != "record":
        raise LiveRecordingRefused(
            "recording a live cassette additionally requires MAINLINE_CASSETTE_MODE=record; "
            f"the store is in {resolved.cassette_mode!r} and refuses to write"
        )


def scenarios() -> list[dict[str, Any]]:
    """``(name, profile, untrusted, trusted_context)`` for every profile in the fleet.

    Six calls over five profiles.  The documents are ``make_cassettes.py``'s, so a live
    cassette and its synthetic twin share a key and can be compared directly.  The poisoned
    document is here on purpose: a live model reading an instruction addressed to *"the
    automated reader"* is the only way to say anything true about layer 2 of the injection
    posture, and a synthetic cassette of that scenario can only ever restate our own belief.
    """
    return [
        {
            "name": "triage.procedure",
            "profile": TRIAGE,
            "untrusted": DOC_PROCEDURE,
            "ctx": CTX_SITE,
            "why": "the clean path: a confined-space SOP routed by the triage rubric",
        },
        {
            "name": "triage.poisoned",
            "profile": TRIAGE,
            "untrusted": DOC_POISONED,
            "ctx": CTX_SITE,
            "why": (
                "layer 2 under a live model: the document carries an instruction addressed "
                "to an automated reader and the recorded answer is what the quarantine did "
                "with it"
            ),
        },
        {
            "name": "extraction.procedure",
            "profile": EXTRACTION,
            "untrusted": DOC_PROCEDURE,
            "ctx": CTX_SITE,
            "why": "quantities with comparators, the schema-constrained path",
        },
        {
            "name": "adjudication.conflict",
            "profile": ADJUDICATION,
            "untrusted": DOC_CONFLICT,
            "ctx": CTX_SITE,
            "why": "three versions of one clause disagreeing about a re-test interval",
        },
        {
            "name": "narration.conflict",
            "profile": NARRATION,
            "untrusted": DOC_CONFLICT,
            "ctx": CTX_SITE,
            "why": "the same conflict, narrated rather than classified",
        },
        {
            "name": "disposition.incident",
            "profile": DISPOSITION_ASSISTANT,
            "untrusted": DOC_INCIDENT,
            "ctx": CTX_SITE,
            "why": "display-only precursor text, the lowest-trust output in the fleet",
        },
    ]


def project_for_wire(body: Any, *, effort: str) -> tuple[dict[str, Any], list[str]]:
    """Return the bytes this model generation accepts, and the list of edits applied.

    The shipping body is built for ``claude-opus-5``.  Three of its fields are refused by
    ``au.anthropic.claude-haiku-4-5-20251001-v1:0`` (see :data:`MEASURED_REFUSALS`).  Every
    edit is named, returned, and written into ``INDEX.json`` beside the cassette it produced.

    Nothing is *added* except the thinking spelling, and nothing that decision A6 bans is
    ever constructed: the projected body is re-checked by the shipping guards before it
    leaves this function, so the assertion runs on the exact object that is serialised.
    """
    projected: dict[str, Any] = json.loads(json.dumps(dict(body), ensure_ascii=False))
    applied: list[str] = []

    config = projected.get("output_config")
    if isinstance(config, dict):
        if "effort" in config:
            del config["effort"]
            applied.append("removed output_config.effort")
        fmt = config.get("format")
        if isinstance(fmt, dict):
            for field in ("name", "strict"):
                if field in fmt:
                    del fmt[field]
                    applied.append(f"removed output_config.format.{field}")

    thinking = projected.get("thinking")
    if isinstance(thinking, dict) and thinking.get("type") == "adaptive":
        budget = THINKING_BUDGET[effort]
        projected["thinking"] = {"type": "enabled", "budget_tokens": budget}
        applied.append(f"thinking adaptive -> enabled, budget {budget}")

    assert_no_sampling_params(projected)
    assert_no_tool_surface(projected)
    return projected, applied


def _client() -> Any:
    """The region-pinned ``bedrock-runtime`` client from the fleet's shared contract.

    Imported inside the function so that importing this module — which
    ``test_live_cassettes.py`` does, with no credentials and no network — never touches
    ``boto3``.
    """
    from aws._common import assert_in_region, bedrock_runtime

    assert_in_region(LIVE_MODEL_ID)
    return bedrock_runtime()


def _invoke(client: Any, model_id: str, projected: dict[str, Any]) -> dict[str, Any]:
    """One ``InvokeModel`` call.  Returns the decoded body plus the call's own metadata."""
    payload = json.dumps(projected, separators=(",", ":"), ensure_ascii=False)
    started = time.perf_counter()
    raw = client.invoke_model(
        modelId=model_id,
        body=payload,
        accept="application/json",
        contentType="application/json",
    )
    latency_ms = round((time.perf_counter() - started) * 1000, 1)
    decoded = json.loads(raw["body"].read())
    metadata = raw.get("ResponseMetadata") or {}
    return {
        "response": decoded,
        "latency_ms": latency_ms,
        "http_status": int(metadata.get("HTTPStatusCode", 0)),
        "request_id": str(metadata.get("RequestId", "")),
        "retry_attempts": int(metadata.get("RetryAttempts", 0)),
    }


def _validates(profile: Any, response: dict[str, Any]) -> tuple[bool, str]:
    """Whether the recorded answer survives the profile's own client-side validator."""
    text: str | None = None
    for block in reversed(response.get("content") or []):
        if isinstance(block, dict) and block.get("type") == "text":
            text = str(block.get("text", ""))
            break
    if text is None:
        return False, "response carried no text block"
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        return False, f"response text is not JSON: {exc.msg} at position {exc.pos}"
    if not isinstance(payload, dict):
        return False, f"response JSON is a {type(payload).__name__}, not an object"
    try:
        profile.schema.validate_payload(payload, profile_id=profile.profile_id)
    except SchemaViolation as violation:
        return False, violation.detail
    return True, ""


def call_input_of(
    untrusted: UntrustedText, ctx: Any, validator_error: str | None
) -> dict[str, Any]:
    """The canonical identity of one call, in the shape the key is computed over.

    Re-derived here — not copied out of :mod:`mainline_agentkit.call` — for the index only.
    The **key** is always ``build_request(...).cassette_key``; this exists so that
    ``test_live_cassettes.py`` can re-run the shipping :func:`cassette_key` over the
    recorded identity and prove the filename is what the rule produces.
    """
    return {
        "trusted_context": dict(ctx),
        "untrusted_sha256": untrusted.sha256,
        "source_sha256": untrusted.source_sha256,
        "media_type": untrusted.media_type,
        "validator_error": validator_error or "",
    }


def record_scenario(
    client: Any,
    store: CassetteStore,
    scenario: dict[str, Any],
    *,
    model_id: str,
) -> list[dict[str, Any]]:
    """Record one scenario, plus its repair turn when the first answer does not validate.

    The repair turn is not an extra feature: ``quarantined_call`` retries **once**, carrying
    the validator's own error text, and a live store that held only attempt 1 would make
    that path a cassette miss on replay.  So the recorder walks the same two attempts the
    shipping caller walks, and stops where it stops.
    """
    entries: list[dict[str, Any]] = []
    profile = scenario["profile"]
    validator_error: str | None = None
    for attempt in (1, 2):
        request = build_request(
            profile,
            scenario["untrusted"],
            scenario["ctx"],
            model_id=model_id,
            sentinel=SENTINEL,
            validator_error=validator_error,
        )
        projected, applied = project_for_wire(request.body, effort=str(profile.effort))
        call = _invoke(client, model_id, projected)
        response = call["response"]
        recorded_at = datetime.now(tz=UTC).isoformat()
        path = store.put(
            Interaction(
                key=request.cassette_key,
                profile_id=request.profile_id,
                prompt_version=request.prompt_version,
                prefix_digest=request.prefix_digest,
                model_id=request.model_id,
                provenance=PROVENANCE_LIVE,
                response=response,
                recorded_at=recorded_at,
            )
        )
        ok, detail = _validates(profile, response)
        usage = dict(response.get("usage") or {})
        entries.append(
            {
                "digest": request.cassette_key,
                "file": path.name,
                "scenario": scenario["name"],
                "why": scenario["why"],
                "attempt": attempt,
                "profile": request.profile_id,
                "prompt_version": request.prompt_version,
                "prefix_digest": request.prefix_digest,
                "model_id": request.model_id,
                "provenance": PROVENANCE_LIVE,
                "recorded_at": recorded_at,
                "call_input": call_input_of(
                    scenario["untrusted"], scenario["ctx"], validator_error
                ),
                "input_sha256": request.input_sha256,
                "stop_reason": response.get("stop_reason"),
                "usage": {
                    "input_tokens": int(usage.get("input_tokens") or 0),
                    "output_tokens": int(usage.get("output_tokens") or 0),
                    "cache_creation_input_tokens": int(
                        usage.get("cache_creation_input_tokens") or 0
                    ),
                    "cache_read_input_tokens": int(usage.get("cache_read_input_tokens") or 0),
                },
                "http_status": call["http_status"],
                "request_id": call["request_id"],
                "retry_attempts": call["retry_attempts"],
                "latency_ms": call["latency_ms"],
                "validates": ok,
                "validator_error": detail,
                "wire_projection": WIRE_PROJECTION_ID,
                "wire_projection_applied": applied,
                # `stable_json_bytes`, not `canonical_json_bytes`: a model response is a
                # payload this system did not author and may legally carry a float, which
                # the RFC 8785 canonicaliser refuses by design.
                "response_sha256": sha256_hex(stable_json_bytes(response)),
                "cassette_sha256": sha256_hex(path.read_bytes()),
            }
        )
        if ok:
            return entries
        validator_error = detail
    return entries


def build_index(entries: list[dict[str, Any]], *, model_id: str) -> dict[str, Any]:
    """The store's manifest.  Every field a reader needs to re-derive a filename."""
    return {
        "schema": INDEX_SCHEMA,
        "store": "packages/mainline-agentkit/tests/cassettes_live",
        "generated_by": "packages/mainline-agentkit/tests/make_live_cassettes.py",
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "region": "ap-southeast-2",
        "model_id": model_id,
        "provenance": PROVENANCE_LIVE,
        "sentinel": SENTINEL,
        "key_rule": (
            "sha256(profile_id 0x1f prompt_version 0x1f jcs(call_input)); computed by "
            "mainline_agentkit.cassette.cassette_key via build_request, never by hand"
        ),
        "sibling_store": {
            "path": "packages/mainline-agentkit/tests/cassettes",
            "provenance": "synthetic",
            "relationship": (
                "key-compatible and byte-untouched by this program. The key carries neither "
                "the model id nor the response, so a scenario shared with make_cassettes.py "
                "lands on the same filename in both stores and MAINLINE_CASSETTE_DIR is the "
                "whole of the switch between synthetic and live evidence."
            ),
        },
        "wire_projection": {
            "id": WIRE_PROJECTION_ID,
            "why": (
                "the shipping body is built for the pinned claude-opus-5 generation; this "
                "model refuses three of its fields. Every edit is named per entry in "
                "wire_projection_applied and the refusals are verbatim below."
            ),
            "measured_refusals": [dict(item) for item in MEASURED_REFUSALS],
            "measured_on": "2026-08-11",
            "unchanged": [
                "system blocks and their cache breakpoint",
                "the user turn, its sentinel and the untrusted span",
                "max_tokens",
                "output_config.format.schema",
                "anthropic_version",
            ],
            "sampling_parameters_sent": [],
        },
        "count": len(entries),
        "entries": entries,
    }


def main() -> int:
    """Record the live store and write its index.  Returns a process exit code."""
    assert_live_recording_permitted()
    store = CassetteStore(LIVE_DIR, mode="record")
    client = _client()
    entries: list[dict[str, Any]] = []
    for scenario in scenarios():
        entries.extend(record_scenario(client, store, scenario, model_id=LIVE_MODEL_ID))
        print(f"  recorded {scenario['name']}")
    entries.sort(key=lambda item: (item["scenario"], item["attempt"]))
    INDEX_PATH.write_text(
        json.dumps(build_index(entries, model_id=LIVE_MODEL_ID), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    unvalidated = [item["scenario"] for item in entries if not item["validates"]]
    print(f"wrote {len(entries)} live cassettes to {LIVE_DIR}")
    print(f"index: {INDEX_PATH}")
    if unvalidated:
        print(f"attempts that did not validate (recorded anyway): {sorted(set(unvalidated))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
