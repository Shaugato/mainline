# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Prove, from this machine, that Amazon Bedrock executes for MAINLINE in ``ap-southeast-2``.

    D:/CoackroachDBxAWS/mainline/.venv/Scripts/python.exe scripts/aws/probe_bedrock.py

WHY THIS PROGRAM EXISTS
-----------------------
``docs/STATE-OF-THE-BUILD.md`` §3.3 recorded, correctly at the time, that *no AWS service
had ever executed* for this project: Bedrock answered ``ValidationException: Operation not
allowed`` and every model call in the tree was a handwritten cassette.  That finding is now
false, and the honest way to retire a published finding is not to delete it — it is to
replace it with a re-runnable measurement that anyone can repeat.  This is that
measurement, and it is layer 0 of the AWS fleet: nine later programs are entitled to assume
only what this file has actually observed.

WHAT IT DOES, AND WHY EACH CALL IS HERE
---------------------------------------
1. **Titan embeddings** (``amazon.titan-embed-text-v2:0``, InvokeModel).  The production
   read path (``providers/bedrock_titan.py``) issues exactly this request shape.  We record
   HTTP status, the AWS ``RequestId``, wall-clock latency, the returned width, Bedrock's own
   ``inputTextTokenCount``, and the **L2 norm** of the vector — because the provider asks for
   ``normalize: true`` and then renormalises anyway, and the norm is how you find out whether
   that second step was paranoia or necessity.
2. **Haiku 4.5 via the ``au.`` Australia-only inference profile** (Converse).  ``maxTokens``
   is 32 and **no sampling parameter is sent**: A6 records that they 400 on this generation,
   ``tests/boundary/test_ci_greps.py`` bans them in every request builder under ``scripts/``,
   and the claim MAINLINE makes was always replayability, never reproducibility of model
   output.
3. **Cohere embed v4** (``cohere.embed-v4:0``, InvokeModel), which **fails** — and the
   failure is the point.  Its ``ValidationException`` is captured verbatim, hashed, and
   filed as a *successful observation*, because it is the evidence for a residency finding:
   the only identifier on this account that can serve embed-v4 is
   ``global.cohere.embed-v4:0``, a cross-region routing profile that
   ``scripts/aws/_common.py::assert_in_region`` refuses by design.  At v4, on this account,
   the choice is residency **or** that model.  ADR 0002 left "benchmark Cohere against Titan"
   open; this is the structural half of the answer, and the in-region alternative is
   ``cohere.embed-english-v3``.
4. **The census** (``list_foundation_models`` + ``list_inference_profiles``), so that
   claim 3 is checkable rather than anecdotal, and so a later worker choosing a model can
   read what exists in this region instead of guessing.

WHAT IT DOES NOT DO
-------------------
No IAM object is created.  Model-invocation logging is **not** enabled — that is an
account-settings change and is out of scope for this fleet.  No Terraform runs.  Nothing is
provisioned; every call above is on-demand and read-only apart from the three inferences,
which are priced at **USD 0.0000006** in total by ``USD_PER_1K_TOKENS`` (declared list
price, not a bill — see ``PRICE_BASIS``).

EXIT CODES
----------
``0`` all three probes returned what they were expected to return, including Cohere's
refusal.  ``1`` at least one probe did not; the artefacts are still written, with the
failure in them, because an unwritten failure is an unexplained gap.  ``2`` no AWS session
could be built at all.
"""

from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path
from typing import Any

from botocore.exceptions import BotoCoreError, ClientError

if __package__ in {None, ""}:  # direct execution: `python scripts/aws/probe_bedrock.py`
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.aws._common import (
    REGION,
    artefact,
    assert_in_region,
    bedrock_control,
    bedrock_runtime,
    ledger_total,
    redact,
    sha256_hex,
    token_ledger_entry,
)

# ═══════════════════════════════════════════════════════════════════════════════════════
# Constants — every one of them a deliberate choice
# ═══════════════════════════════════════════════════════════════════════════════════════

TITAN_MODEL_ID = "amazon.titan-embed-text-v2:0"
HAIKU_MODEL_ID = "au.anthropic.claude-haiku-4-5-20251001-v1:0"
COHERE_MODEL_ID = "cohere.embed-v4:0"

#: The embedded text.  Fixed, so two runs are comparable, and drawn from MAINLINE's own
#: domain so the probe exercises the vocabulary the real corpus uses.  It describes no real
#: incident: this is a fabricated clause, and every artefact this program writes says so.
PROBE_TEXT = (
    "MAINLINE probe clause: isolate and de-pressurise the line, prove zero energy at the "
    "break point, and hold the permit open until the isolation is independently verified."
)

#: The prompt.  Short and closed on purpose — this measures that Converse works through the
#: ``au.`` profile, not that the model is clever.
PROBE_PROMPT = "Reply with exactly these three words and nothing else: MAINLINE gate online"

MAX_TOKENS = 32

EVIDENCE_DIR = Path("evidence/aws/probe")

#: The width the DDL declares (``VECTOR(1024)`` in ``0031_clause_embedding.sql``) and the
#: width the provider requests.  A probe that accepted any width would not be a probe.
EXPECTED_DIM = 1024

#: The two exception roots ``botocore`` raises: ``ClientError`` for anything the service
#: answered (a ``ValidationException`` is one), ``BotoCoreError`` for anything that stopped
#: the request reaching it.  Named rather than caught blind on purpose — ``ruff``'s ``BLE``
#: family is load-bearing in this repository, and rightly: in a product whose deliverable
#: is a refusal, swallowing an unexpected exception is the defect class, not a style nit.
#: A ``JSONDecodeError`` or a ``KeyError`` below would be a bug in *this* program, and it
#: must reach the operator instead of being filed as a Bedrock failure.
AWS_ERRORS = (BotoCoreError, ClientError)

SYNTHETIC_CAVEAT = (
    "the embedded text and the prompt are fabricated MAINLINE-shaped strings, not real "
    "incident or permit data; this file proves the AWS call path, not any domain result"
)


# ═══════════════════════════════════════════════════════════════════════════════════════
# Small helpers
# ═══════════════════════════════════════════════════════════════════════════════════════


def _meta(response_or_error: Any) -> dict[str, Any]:
    """The bits of ``ResponseMetadata`` that are evidence, from a response or an error.

    ``RequestId`` is the load-bearing field: it is the identifier AWS itself would use to
    find this call in its own records, which is what turns "we say we called Bedrock" into
    something a third party could check.
    """
    meta = (response_or_error or {}).get("ResponseMetadata", {}) or {}
    return {
        "http_status": meta.get("HTTPStatusCode"),
        "request_id": meta.get("RequestId"),
        "retry_attempts": meta.get("RetryAttempts"),
        "date_header": (meta.get("HTTPHeaders") or {}).get("date"),
    }


def _read_body(body: Any) -> bytes:
    if isinstance(body, (bytes, bytearray)):
        return bytes(body)
    data = body.read()
    return data if isinstance(data, bytes) else str(data).encode("utf-8")


def _l2_norm(values: list[float]) -> float:
    return math.sqrt(math.fsum(float(v) * float(v) for v in values))


# ═══════════════════════════════════════════════════════════════════════════════════════
# Probe 1 — Titan embeddings
# ═══════════════════════════════════════════════════════════════════════════════════════


def probe_titan(runtime: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    """InvokeModel against Titan v2.  Returns ``(summary, raw)``."""
    model_id = assert_in_region(TITAN_MODEL_ID)
    request_body = {"inputText": PROBE_TEXT, "dimensions": EXPECTED_DIM, "normalize": True}
    encoded = json.dumps(request_body).encode("utf-8")

    started = time.perf_counter()
    try:
        response = runtime.invoke_model(
            modelId=model_id,
            contentType="application/json",
            accept="application/json",
            body=encoded,
        )
    except AWS_ERRORS as exc:  # a failed probe is still a measurement
        latency_ms = round((time.perf_counter() - started) * 1000, 1)
        error = getattr(exc, "response", None) or {}
        summary = {
            "model_id": model_id,
            "call": "invoke_model",
            "ok": False,
            "latency_ms": latency_ms,
            "error_type": type(exc).__name__,
            "error_code": (error.get("Error") or {}).get("Code"),
            "error_message": (error.get("Error") or {}).get("Message") or str(exc),
            **_meta(error),
        }
        return summary, {"request": request_body, "response": None, "error": summary}

    payload_bytes = _read_body(response["body"])
    latency_ms = round((time.perf_counter() - started) * 1000, 1)
    payload = json.loads(payload_bytes)
    embedding = payload.get("embedding") or []
    norm = _l2_norm(embedding)

    summary = {
        "model_id": model_id,
        "call": "invoke_model",
        "ok": True,
        "latency_ms": latency_ms,
        "embedding_length": len(embedding),
        "embedding_length_matches_ddl": len(embedding) == EXPECTED_DIM,
        "input_text_token_count": payload.get("inputTextTokenCount"),
        # `normalize: true` was requested. This is whether Bedrock honoured it, measured
        # rather than assumed, which is the whole reason the provider renormalises anyway.
        # Nine decimals, not the full float. The deviation from unity this is here to
        # expose is ~6e-8, so nine places says everything twelve would; and twelve places
        # writes a twelve-digit run into an evidence file that an auditor's account-id
        # grep would flag. Precision that only feeds a false positive is not precision.
        "l2_norm": round(norm, 9),
        "l2_norm_is_unit_to_1e_6": abs(norm - 1.0) < 1e-6,
        "embedding_sha256": sha256_hex(
            json.dumps([float(v) for v in embedding], separators=(",", ":")).encode("utf-8")
        ),
        "response_body_sha256": sha256_hex(payload_bytes),
        "content_type": response.get("contentType"),
        **_meta(response),
    }
    raw = {
        "request": {
            "operation": "bedrock-runtime:InvokeModel",
            "modelId": model_id,
            "contentType": "application/json",
            "accept": "application/json",
            "body": request_body,
            "body_bytes": len(encoded),
            "body_sha256": sha256_hex(encoded),
        },
        "response": {
            "metadata": _meta(response),
            "contentType": response.get("contentType"),
            # The full body, embedding and all. It is 1024 floats and it is the evidence;
            # a truncated response is a claim about a response, not a response.
            "body": payload,
        },
        "derived": {
            "latency_ms": latency_ms,
            "embedding_length": len(embedding),
            "l2_norm": summary["l2_norm"],
            "embedding_sha256": summary["embedding_sha256"],
            "response_body_sha256": summary["response_body_sha256"],
        },
    }
    return summary, raw


# ═══════════════════════════════════════════════════════════════════════════════════════
# Probe 2 — Haiku 4.5 through the au. profile
# ═══════════════════════════════════════════════════════════════════════════════════════


def probe_haiku(runtime: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    """Converse against the Australia-only Haiku profile.  Returns ``(summary, raw)``.

    ``inferenceConfig`` carries ``maxTokens`` and nothing else.  That absence is enforced
    by ``scan_sampling_params`` over ``scripts/``, and it is a design position, not an
    oversight: see the module docstring.
    """
    model_id = assert_in_region(HAIKU_MODEL_ID)
    messages = [{"role": "user", "content": [{"text": PROBE_PROMPT}]}]
    inference_config = {"maxTokens": MAX_TOKENS}

    started = time.perf_counter()
    try:
        response = runtime.converse(
            modelId=model_id,
            messages=messages,
            inferenceConfig=inference_config,
        )
    except AWS_ERRORS as exc:
        latency_ms = round((time.perf_counter() - started) * 1000, 1)
        error = getattr(exc, "response", None) or {}
        summary = {
            "model_id": model_id,
            "call": "converse",
            "ok": False,
            "latency_ms": latency_ms,
            "error_type": type(exc).__name__,
            "error_code": (error.get("Error") or {}).get("Code"),
            "error_message": (error.get("Error") or {}).get("Message") or str(exc),
            **_meta(error),
        }
        return summary, {
            "request": {
                "modelId": model_id,
                "messages": messages,
                "inferenceConfig": inference_config,
            },
            "response": None,
            "error": summary,
        }

    latency_ms = round((time.perf_counter() - started) * 1000, 1)
    blocks = ((response.get("output") or {}).get("message") or {}).get("content") or []
    reply = "".join(block.get("text", "") for block in blocks)
    usage = response.get("usage") or {}

    summary = {
        "model_id": model_id,
        "call": "converse",
        "ok": True,
        "latency_ms": latency_ms,
        "server_latency_ms": (response.get("metrics") or {}).get("latencyMs"),
        "stop_reason": response.get("stopReason"),
        "usage": dict(usage),
        "reply_text": reply,
        "reply_sha256": sha256_hex(reply.encode("utf-8")),
        "sampling_parameters_sent": [],
        **_meta(response),
    }
    raw = {
        "request": {
            "operation": "bedrock-runtime:Converse",
            "modelId": model_id,
            "messages": messages,
            "inferenceConfig": inference_config,
            "sampling_parameters_sent": [],
            "sampling_note": (
                "A6: no sampling parameter is sent on any Claude generation used here; "
                "tests/boundary/test_ci_greps.py enforces the absence across scripts/"
            ),
        },
        "response": {
            "metadata": _meta(response),
            "output": response.get("output"),
            "stopReason": response.get("stopReason"),
            "usage": dict(usage),
            "metrics": response.get("metrics"),
        },
        "derived": {
            "latency_ms": latency_ms,
            "reply_text": reply,
            "reply_sha256": summary["reply_sha256"],
        },
    }
    return summary, raw


# ═══════════════════════════════════════════════════════════════════════════════════════
# Probe 3 — Cohere embed v4, whose refusal is the finding
# ═══════════════════════════════════════════════════════════════════════════════════════


def probe_cohere(runtime: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    """InvokeModel against ``cohere.embed-v4:0``.  A ``ValidationException`` is the
    expected, successful outcome and is recorded verbatim.

    ``observed_as_expected`` is true when Bedrock refuses.  If Bedrock ever *succeeds*
    here, that is a change in the account's entitlements and the residency finding this
    fleet publishes would have to be rewritten — so the probe reports that case loudly
    rather than treating any 200 as good news.
    """
    model_id = assert_in_region(COHERE_MODEL_ID)  # bare vendor id: legal to attempt
    request_body = {
        "texts": [PROBE_TEXT],
        "input_type": "search_document",
        "output_dimension": EXPECTED_DIM,
        "embedding_types": ["float"],
    }
    encoded = json.dumps(request_body).encode("utf-8")

    started = time.perf_counter()
    try:
        response = runtime.invoke_model(
            modelId=model_id,
            contentType="application/json",
            accept="application/json",
            body=encoded,
        )
    except AWS_ERRORS as exc:
        latency_ms = round((time.perf_counter() - started) * 1000, 1)
        error = getattr(exc, "response", None) or {}
        code = (error.get("Error") or {}).get("Code") or type(exc).__name__
        message = (error.get("Error") or {}).get("Message") or str(exc)
        summary = {
            "model_id": model_id,
            "call": "invoke_model",
            "outcome": "refused",
            "observed_as_expected": code == "ValidationException",
            "latency_ms": latency_ms,
            "error_type": type(exc).__name__,
            "error_code": code,
            # VERBATIM. `redaction_altered_message` below is how you know it stayed that way.
            "error_message_verbatim": message,
            "error_message_sha256": sha256_hex(message.encode("utf-8")),
            "redaction_altered_message": redact(message) != message,
            "residency_finding": (
                "the only identifier on this account that serves cohere embed-v4 is "
                "global.cohere.embed-v4:0, a cross-region routing profile that "
                "scripts/aws/_common.py::assert_in_region refuses; the in-region "
                "alternative at v3 is cohere.embed-english-v3 (ON_DEMAND, ap-southeast-2)"
            ),
            **_meta(error),
        }
        raw = {
            "request": {
                "operation": "bedrock-runtime:InvokeModel",
                "modelId": model_id,
                "contentType": "application/json",
                "accept": "application/json",
                "body": request_body,
                "body_sha256": sha256_hex(encoded),
            },
            "response": None,
            "error": {
                "type": type(exc).__name__,
                "code": code,
                "message_verbatim": message,
                "message_sha256": sha256_hex(message.encode("utf-8")),
                "metadata": _meta(error),
            },
        }
        return summary, raw

    # Unexpected success: record it as such rather than quietly banking a 200.
    payload_bytes = _read_body(response["body"])
    latency_ms = round((time.perf_counter() - started) * 1000, 1)
    payload = json.loads(payload_bytes)
    summary = {
        "model_id": model_id,
        "call": "invoke_model",
        "outcome": "succeeded",
        "observed_as_expected": False,
        "latency_ms": latency_ms,
        "note": (
            "cohere.embed-v4:0 served an on-demand request, which contradicts the "
            "measurement of 2026-08-11 and the residency finding built on it; the finding "
            "must be re-derived before it is quoted again"
        ),
        **_meta(response),
    }
    raw = {
        "request": {
            "operation": "bedrock-runtime:InvokeModel",
            "modelId": model_id,
            "body": request_body,
            "body_sha256": sha256_hex(encoded),
        },
        "response": {
            "metadata": _meta(response),
            "body_sha256": sha256_hex(payload_bytes),
            "body_keys": sorted(payload),
        },
        "error": None,
    }
    return summary, raw


# ═══════════════════════════════════════════════════════════════════════════════════════
# Probe 4 — the census
# ═══════════════════════════════════════════════════════════════════════════════════════


def census(control: Any) -> dict[str, Any]:
    """What ``ap-southeast-2`` actually offers this account, read from the control plane.

    Two lists, because they answer different questions.  ``list_foundation_models`` says
    which *models* exist and how they may be invoked (``inferenceTypesSupported``);
    ``list_inference_profiles`` says which *routing profiles* exist, and it is the only
    place the ``global.``/``au.``/``apac.`` distinction is visible.  A model that is
    ``INFERENCE_PROFILE``-only and has no ``au.`` profile is unreachable in-region, which
    is exactly the shape of the Cohere finding.
    """
    models = control.list_foundation_models().get("modelSummaries", []) or []
    profiles = control.list_inference_profiles().get("inferenceProfileSummaries", []) or []

    def row(model: dict[str, Any]) -> dict[str, Any]:
        return {
            "model_id": model.get("modelId"),
            "model_name": model.get("modelName"),
            "provider": model.get("providerName"),
            "input_modalities": model.get("inputModalities"),
            "output_modalities": model.get("outputModalities"),
            "inference_types_supported": model.get("inferenceTypesSupported"),
            "lifecycle": (model.get("modelLifecycle") or {}).get("status"),
            "streaming": model.get("responseStreamingSupported"),
        }

    embedding_models = [row(m) for m in models if "EMBEDDING" in (m.get("outputModalities") or [])]
    embedding_models.sort(key=lambda r: r["model_id"] or "")

    def prefix(profile_id: str) -> str:
        return (profile_id or "").split(".", 1)[0].lower()

    profile_rows = [
        {
            "inference_profile_id": p.get("inferenceProfileId"),
            "name": p.get("inferenceProfileName"),
            "type": p.get("type"),
            "status": p.get("status"),
            "routing_prefix": prefix(p.get("inferenceProfileId", "")),
            "models": [m.get("modelArn") for m in (p.get("models") or [])],
        }
        for p in profiles
    ]
    profile_rows.sort(key=lambda r: r["inference_profile_id"] or "")

    by_prefix: dict[str, int] = {}
    for entry in profile_rows:
        by_prefix[entry["routing_prefix"]] = by_prefix.get(entry["routing_prefix"], 0) + 1

    au_profiles = [p for p in profile_rows if p["routing_prefix"] == "au"]
    on_demand_embedding = [
        r["model_id"]
        for r in embedding_models
        if "ON_DEMAND" in (r["inference_types_supported"] or [])
    ]
    profile_only_embedding = [
        r["model_id"]
        for r in embedding_models
        if (r["inference_types_supported"] or []) == ["INFERENCE_PROFILE"]
    ]

    return {
        "region": REGION,
        "foundation_models_total": len(models),
        "inference_profiles_total": len(profiles),
        "inference_profiles_by_routing_prefix": dict(sorted(by_prefix.items())),
        "embedding_models": embedding_models,
        "embedding_models_on_demand_in_region": sorted(on_demand_embedding),
        "embedding_models_inference_profile_only": sorted(profile_only_embedding),
        "au_inference_profiles": au_profiles,
        "au_inference_profile_ids": sorted(p["inference_profile_id"] for p in au_profiles),
        "reading": (
            "an embedding model listed only as INFERENCE_PROFILE cannot be invoked by its "
            "bare id; if no au.* profile exists for it, it cannot be invoked in-region at "
            "all, and that is a residency constraint rather than a benchmark footnote"
        ),
    }


# ═══════════════════════════════════════════════════════════════════════════════════════
# main
# ═══════════════════════════════════════════════════════════════════════════════════════


def main() -> int:
    try:
        runtime = bedrock_runtime()
        control = bedrock_control()
    except AWS_ERRORS as exc:
        print(f"no AWS session: {type(exc).__name__}: {redact(str(exc))}", file=sys.stderr)
        return 2

    titan_summary, titan_raw = probe_titan(runtime)
    haiku_summary, haiku_raw = probe_haiku(runtime)
    cohere_summary, cohere_raw = probe_cohere(runtime)

    try:
        availability = census(control)
        census_error = None
    except AWS_ERRORS as exc:
        availability = {"region": REGION}
        census_error = {"type": type(exc).__name__, "message": redact(str(exc))}

    titan_ok = bool(titan_summary.get("ok")) and titan_summary.get("http_status") == 200
    haiku_ok = bool(haiku_summary.get("ok")) and haiku_summary.get("http_status") == 200
    cohere_ok = bool(cohere_summary.get("observed_as_expected"))

    ledger = [
        token_ledger_entry(
            TITAN_MODEL_ID, 1, int(titan_summary.get("input_text_token_count") or 0), 0
        ),
        token_ledger_entry(
            HAIKU_MODEL_ID,
            1,
            int((haiku_summary.get("usage") or {}).get("inputTokens") or 0),
            int((haiku_summary.get("usage") or {}).get("outputTokens") or 0),
        ),
        token_ledger_entry(COHERE_MODEL_ID, 1, 0, 0),
    ]
    ledger_summary = ledger_total(ledger)

    caveats = [
        SYNTHETIC_CAVEAT,
        (
            "one call per model: latency here is a single observation with no interval "
            "and must not be quoted as a performance figure"
        ),
        "costs are priced from a declared list-price table, not from a bill",
        (
            "this file proves Bedrock executes; it proves nothing about any vector "
            "reaching CockroachDB, which is a later worker's artefact"
        ),
    ]
    if not (titan_ok and haiku_ok and cohere_ok):
        caveats.insert(0, "AT LEAST ONE PROBE DID NOT RETURN WHAT WAS EXPECTED — see verdict")
    if census_error is not None:
        caveats.append(f"the model census failed: {census_error['type']}")

    rollup = {
        "verdict": "PROVEN" if (titan_ok and haiku_ok and cohere_ok) else "INCOMPLETE",
        "claim": (
            "Amazon Bedrock executed for MAINLINE in ap-southeast-2 from this workstation: "
            "Titan v2 returned a 1024-d embedding, Claude Haiku 4.5 answered through the "
            "Australia-only au. inference profile, and Cohere embed-v4 refused on-demand "
            "invocation for a reason that is itself a residency finding"
        ),
        "supersedes": (
            "docs/STATE-OF-THE-BUILD.md §3.3, which recorded 'no AWS service has ever "
            "executed' and a ValidationException: Operation not allowed. That finding was "
            "true when written and does not reproduce; this artefact is its replacement."
        ),
        "checks": {
            "titan_http_200_with_request_id": titan_ok and bool(titan_summary.get("request_id")),
            "titan_width_1024": titan_summary.get("embedding_length") == EXPECTED_DIM,
            "haiku_http_200_with_request_id": haiku_ok and bool(haiku_summary.get("request_id")),
            "haiku_no_sampling_parameters_sent": haiku_summary.get("sampling_parameters_sent")
            == [],
            "cohere_validation_exception_captured_verbatim": cohere_ok
            and cohere_summary.get("redaction_altered_message") is False,
        },
        "titan": titan_summary,
        "haiku": haiku_summary,
        "cohere": cohere_summary,
        "token_ledger": ledger,
        "token_ledger_total": ledger_summary,
        "census_summary": {
            "foundation_models_total": availability.get("foundation_models_total"),
            "inference_profiles_total": availability.get("inference_profiles_total"),
            "inference_profiles_by_routing_prefix": availability.get(
                "inference_profiles_by_routing_prefix"
            ),
            "embedding_models_on_demand_in_region": availability.get(
                "embedding_models_on_demand_in_region"
            ),
        },
        "census_error": census_error,
        "raw_artefacts": [
            "evidence/aws/probe/raw-titan-invoke.json",
            "evidence/aws/probe/raw-haiku-converse.json",
            "evidence/aws/probe/raw-cohere-refusal.json",
            "evidence/aws/probe/model-availability.json",
        ],
        "reproduce": (
            "AWS_PROFILE=mainline-dev "
            "D:/CoackroachDBxAWS/mainline/.venv/Scripts/python.exe scripts/aws/probe_bedrock.py"
        ),
    }

    written = [
        artefact(
            EVIDENCE_DIR / "bedrock-probe.json",
            rollup,
            kind="bedrock-probe",
            caveats=caveats,
            synthetic=True,
        ),
        artefact(
            EVIDENCE_DIR / "model-availability.json",
            availability if census_error is None else {**availability, "error": census_error},
            kind="bedrock-model-census",
            caveats=[
                (
                    "a control-plane listing, read-only; it says what this account may "
                    "invoke, not what it has invoked"
                ),
                (
                    "inferenceTypesSupported is AWS's declaration; only bedrock-probe.json "
                    "records what an actual invocation did"
                ),
            ],
            synthetic=False,
        ),
        artefact(
            EVIDENCE_DIR / "raw-titan-invoke.json",
            titan_raw,
            kind="bedrock-raw-invoke",
            caveats=[
                SYNTHETIC_CAVEAT,
                (
                    "the response body is recorded in full, including all 1024 floats; a "
                    "truncated response would be a claim about a response, not a response"
                ),
            ],
            synthetic=True,
        ),
        artefact(
            EVIDENCE_DIR / "raw-haiku-converse.json",
            haiku_raw,
            kind="bedrock-raw-converse",
            caveats=[
                SYNTHETIC_CAVEAT,
                (
                    "model output is not reproducible; MAINLINE claims replayability of "
                    "recorded calls, never reproducibility of generation (A6)"
                ),
            ],
            synthetic=True,
        ),
        artefact(
            EVIDENCE_DIR / "raw-cohere-refusal.json",
            cohere_raw,
            kind="bedrock-raw-refusal",
            caveats=[
                (
                    "this is a captured refusal, not a failure of the probe; the refusal "
                    "is the evidence"
                ),
                (
                    "the message is recorded verbatim and hashed; bedrock-probe.json "
                    "records whether redaction altered it (it must be false)"
                ),
            ],
            synthetic=False,
        ),
    ]

    for path in written:
        print(f"wrote {path.relative_to(Path(__file__).resolve().parents[2]).as_posix()}")
    print(
        f"titan={'200' if titan_ok else 'FAILED'} "
        f"haiku={'200' if haiku_ok else 'FAILED'} "
        f"cohere={'refused-as-expected' if cohere_ok else 'UNEXPECTED'} "
        f"verdict={rollup['verdict']} "
        f"usd={ledger_summary['usd_total']}"
    )
    return 0 if rollup["verdict"] == "PROVEN" else 1


if __name__ == "__main__":
    raise SystemExit(main())
