# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""One incident document, one fleet register, and a transport that answers from a script.

The document is deliberately ordinary: a confined-space entry with an oxygen reading, an
equipment tag and a coded consequence. Everything the suite asserts about severity,
spans, routes and anchors is asserted against these bytes, so a reader can check a claim
by reading one paragraph rather than by trusting a fixture factory.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from datetime import UTC, datetime
from typing import Any

from mainline_agentkit.runtime import AgentkitRuntime
from mainline_agentkit.transport import AgentkitSettings, ModelResponse, Usage
from mainline_archivist import (
    CodedFacts,
    ExtractedText,
    FetchedObject,
    ObjectRef,
    SeverityClaim,
    VerbatimSpan,
)
from mainline_quarantine import FleetRegister, LocalPromptAttackScreen

#: An `au.*` inference profile ARN of the shape `assert_australian_profile` accepts. The
#: account number is a placeholder: nothing in this suite reaches AWS.
PROFILE_ARN = (
    "arn:aws:bedrock:ap-southeast-2:000000000000:inference-profile/au.anthropic.claude-opus-5"
)

OCCURRED_AT = datetime(2019, 3, 14, 6, 20, tzinfo=UTC)
OBSERVED_AT = datetime(2026, 8, 9, 1, 0, tzinfo=UTC)

DOCUMENT_TEXT = """\
INCIDENT INVESTIGATION REPORT IR-2019-0117
Site: Kalgoorlie Concentrator
Date of occurrence: 14 March 2019

Summary
At 06:20 a maintenance fitter entered thickener access chamber TK-4021 to clear a \
blocked underflow line. The atmosphere had not been re-tested after the isolation was \
broken. Oxygen was subsequently measured at 17.4 % by volume, below the entry minimum \
of at least 19.5 % required by the confined space entry permit. The fitter was \
withdrawn by a standby observer after approximately four minutes and treated on site.

Consequence coding
Actual consequence class: 3 (medical treatment injury)
Potential consequence class: 5 (single fatality)

Barrier analysis
The atmospheric re-test after isolation break was ABSENT. Gas detector GD-119A had a \
current calibration record. The standby observer role was staffed and effective.
"""

TITLE_QUOTE = "INCIDENT INVESTIGATION REPORT IR-2019-0117"
OXYGEN_QUOTE = "at least 19.5 %"
ACTUAL_CODE_QUOTE = "Actual consequence class: 3 (medical treatment injury)"
POTENTIAL_CODE_QUOTE = "Potential consequence class: 5 (single fatality)"
NARRATIVE_QUOTE = (
    "At 06:20 a maintenance fitter entered thickener access chamber TK-4021 to clear a "
    "blocked underflow line."
)

SITE_ID = "3f6f4a52-0d21-4a1a-8a3f-2f6d1c9b7a01"

#: A register with the Archivist's real entry: T1, one SQL role, and no tools at all.
REGISTER_DOCUMENT: dict[str, Any] = {
    "version": 1,
    "agents": {
        "archivist": {
            "tier": "T1",
            "sql_role": ["agent_ingestor"],
            "tools": [],
            "may_write_gate_field": False,
        }
    },
}


def register() -> FleetRegister:
    """The fleet register the capability layer checks against."""
    return FleetRegister.from_mapping(REGISTER_DOCUMENT, source="<archivist corpus>")


def screen() -> LocalPromptAttackScreen:
    """The offline layer-2 screen."""
    return LocalPromptAttackScreen()


def fetched(text: str = DOCUMENT_TEXT) -> FetchedObject:
    """A fetched object whose digest is computed from the bytes, as the store computes it."""
    import hashlib

    body = text.encode("utf-8")
    return FetchedObject(
        ref=ObjectRef(object_key="incidents/IR-2019-0117.txt", version_id="v-000000001"),
        body=body,
        sha256=hashlib.sha256(body).hexdigest(),
        media_type="text/plain",
    )


def extracted(text: str = DOCUMENT_TEXT) -> ExtractedText:
    """The extracted text, from the offline extractor."""
    return ExtractedText(text=text, extractor="utf8", media_type="text/plain", page_count=1)


def span(quote: str, text: str = DOCUMENT_TEXT) -> VerbatimSpan:
    """Locate a quote in the corpus document."""
    return VerbatimSpan.locate(text, quote)


def coded_claims() -> tuple[SeverityClaim, ...]:
    """The two coded severity claims the document states in its own consequence coding."""
    return (
        SeverityClaim.coded(
            3,
            field_name="consequence_class_actual",
            dimension="actual",
            span=span(ACTUAL_CODE_QUOTE),
        ),
        SeverityClaim.coded(
            5,
            field_name="consequence_class_potential",
            dimension="potential",
            span=span(POTENTIAL_CODE_QUOTE),
        ),
    )


def coded_facts(
    *,
    kind: str = "incident",
    claims: tuple[SeverityClaim, ...] | None = None,
    text: str = DOCUMENT_TEXT,
) -> CodedFacts:
    """Everything about this event that did not come from a model."""
    start = text.index(NARRATIVE_QUOTE)
    return CodedFacts(
        site_id=SITE_ID,
        kind=kind,
        occurred_at=OCCURRED_AT,
        title_quote=TITLE_QUOTE,
        narrative_span=(start, start + len(NARRATIVE_QUOTE)),
        claims=coded_claims() if claims is None else claims,
        external_ref="IR-2019-0117",
    )


TRIAGE_PAYLOAD: dict[str, Any] = {
    "route": "incident",
    "hazard_classes": ["confined_space"],
    "abstained": False,
    "basis_quote": TITLE_QUOTE,
}

EXTRACTION_PAYLOAD: dict[str, Any] = {
    "abstained": False,
    "abstain_reason": "none",
    "anchors": ["TK-4021", "GD-119A"],
    "quantities": [
        {
            "quantity_kind": "oxygen_concentration",
            "value_milli": 19500,
            "unit": "%",
            "comparator": "gte",
            "quote": OXYGEN_QUOTE,
        }
    ],
}


@dataclass
class ScriptedTransport:
    """A transport that answers each profile from a script. No socket, no cassette.

    ``responses`` maps a ``profile_id`` to either a payload mapping (returned as the last
    text block, which is where a structured output arrives) or a ``stop_reason`` string,
    which is how a refusal or a truncation is scripted.
    """

    responses: dict[str, Any]
    calls: list[str] = dataclass_field(default_factory=list)

    def invoke(self, request: Any) -> ModelResponse:
        """Return the scripted response for ``request.profile_id``."""
        self.calls.append(request.profile_id)
        scripted = self.responses[request.profile_id]
        if isinstance(scripted, str):
            return ModelResponse(
                stop_reason=scripted,
                content=(),
                usage=Usage(input_tokens=1200, output_tokens=0),
                model=request.model_id,
                raw={"stop_reason": scripted},
            )
        body = {
            "stop_reason": "end_turn",
            "content": [
                {"type": "thinking", "thinking": "…"},
                {"type": "text", "text": json.dumps(scripted)},
            ],
            "usage": {
                "input_tokens": 1200,
                "output_tokens": 180,
                "cache_read_input_tokens": 512,
            },
            "model": request.model_id,
        }
        return ModelResponse.from_body(body)

    def warm(self, request: Any, *, first_token: Any) -> ModelResponse:
        """Set the first-token event, then answer as :meth:`invoke` would."""
        response = self.invoke(request)
        first_token.set()
        return response


def runtime(transport: ScriptedTransport | None = None) -> AgentkitRuntime:
    """Boot an agentkit runtime over a scripted transport, pinned to an ``au.*`` profile."""
    wire = transport or ScriptedTransport(
        responses={"triage": TRIAGE_PAYLOAD, "extraction": EXTRACTION_PAYLOAD}
    )
    return AgentkitRuntime.boot(
        settings=AgentkitSettings(provider="cassette"),
        transport=wire,
        inference_profile_arn=PROFILE_ARN,
        run_id="archivist-corpus-run",
    )
