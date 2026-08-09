# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The committed scenarios, and the generator that records them.

Eleven scenarios, one per behaviour Path B can exhibit, each recorded as an
agentkit interaction under ``tests/fixtures/domain/oracle/cassettes/``.  Nine of
them end in an abstention; that ratio is the product, not an accident of test
authorship.

**Provenance is stated, never implied.**  Every recording here is written with
``provenance: "synthetic"`` — hand-built response bodies that exercise the code
paths — because AWS credentials are not valid on the build machine as of 2026-08.
Nothing in this file has ever been near Bedrock, and the field in each file is
what says so.  When the live lane records real interactions they carry
``provenance: "live"`` and the two can be told apart without asking anyone.

**Why the generator ships inside the package.**  Two reasons.  The retry path
records *two* interactions whose second key depends on the exact text of the
validator's own complaint, so the keys cannot be written by hand; and
``tests/unit/domain/resolution/test_oracle_cassettes.py`` re-runs this generator
and compares it against the committed files, which turns "the fixtures are stale"
from a discovery into a failing build.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Final

from mainline_agentkit import CassetteStore, ModelRequest, ModelResponse
from mainline_agentkit.cassette import PROVENANCE_SYNTHETIC
from mainline_domain.contracts import CAT, Quantity

from .oracle import PROMPT_VERSION, AdjudicationOracle
from .request import DeltaOracleRequest, OriginContext

if TYPE_CHECKING:
    import threading
    from collections.abc import Mapping, Sequence
    from pathlib import Path

__all__ = [
    "SCENARIOS",
    "STORE_README",
    "RecordedCall",
    "Scenario",
    "ScriptedTransport",
    "record_scenarios",
    "recorded_calls",
    "scenario",
]


# ── the clause pair every scenario varies ───────────────────────────────────────

_ANCESTOR = (
    "The Supervisor shall verify that pump P-101A is isolated and proved dead "
    "before any person enters the pump housing. The atmosphere shall be gas "
    "tested at intervals not exceeding 30 minutes while the space is occupied."
)

_ORIGIN = OriginContext(
    event_summary=(
        "A fitter entered the P-101A housing during a shutdown while the discharge "
        "line remained pressurised. The atmosphere was not retested after the first "
        "hour. The fitter was overcome and did not recover. The investigation found "
        "the isolation had been proved once, at the start of the shift, and not "
        "again."
    ),
    severity=5,
    occurred_on="2019-07-14",
)


def _quantity(value: str, unit: str, dimension: str) -> Quantity:
    return Quantity(value=Decimal(value), unit=unit, dimension=dimension, reference="none")


def _cat(deontic: str, interval_minutes: str, *, exceptions: tuple[str, ...] = ()) -> CAT:
    return CAT(
        actor="supervisor",
        deontic=deontic,
        action="verify_isolation",
        object_class="pump_housing",
        hazard_energy="atmospheric",
        parameter="gas_test_interval",
        comparator="<=",
        value=None,
        conditions=("space_occupied",),
        exceptions=exceptions,
        verification=("proved_dead",),
        frequency=_quantity(interval_minutes, "min", "time"),
        coverage_quantifier="all",
    )


def _request(descendant: str, cat_deontic: str, interval: str, **kwargs: Any) -> DeltaOracleRequest:
    return DeltaOracleRequest(
        ancestor_text=_ANCESTOR,
        descendant_text=descendant,
        ancestor_cat=_cat("MUST", "30"),
        descendant_cat=_cat(cat_deontic, interval, **kwargs),
        parameter_hint="gas_test_interval",
        prompt_version=PROMPT_VERSION,
        origin=_ORIGIN,
        source_sha256="",
    )


# ── response bodies ─────────────────────────────────────────────────────────────


def _proposal(
    relation: str,
    band: str,
    quote: str,
    *,
    numeric_disagreement: bool = False,
    notes: str = "",
) -> dict[str, Any]:
    return {
        "relation": relation,
        "confidence_band": band,
        "numeric_disagreement": numeric_disagreement,
        "supporting_quote": quote,
        "notes": notes,
    }


def _body(
    payload: Mapping[str, Any] | str | None,
    *,
    stop_reason: str = "end_turn",
    guardrail: bool = False,
) -> dict[str, Any]:
    """One Anthropic native response body, as Bedrock would return it."""
    content: list[dict[str, Any]] = []
    if payload is not None:
        text = payload if isinstance(payload, str) else json.dumps(payload)
        content = [{"type": "text", "text": text}]
    body: dict[str, Any] = {
        "id": "msg_synthetic",
        "model": "claude-opus-5",
        "stop_reason": stop_reason,
        "content": content,
        "usage": {"input_tokens": 1800, "output_tokens": 180},
    }
    if guardrail:
        body["amazon-bedrock-guardrailAction"] = "INTERVENED"
    return body


@dataclass(frozen=True, slots=True)
class Scenario:
    """One recorded behaviour, with the outcome it is committed to demonstrate."""

    name: str
    request: DeltaOracleRequest
    responses: tuple[Mapping[str, Any], ...]
    expects: str


_LONGER_INTERVAL = (
    "The Supervisor should verify that pump P-101A is isolated and proved dead "
    "before any person enters the pump housing, where practicable. The atmosphere "
    "shall be gas tested at intervals not exceeding 120 minutes while the space is "
    "occupied."
)
_SHORTER_INTERVAL = (
    "The Supervisor shall verify that pump P-101A is isolated and proved dead "
    "before any person enters the pump housing. The atmosphere shall be gas tested "
    "at intervals not exceeding 15 minutes while the space is occupied, and the "
    "result recorded."
)
_REWORDED = (
    "Before any person enters the housing of pump P-101A, the Supervisor shall "
    "confirm the pump is isolated and proved dead. While the space is occupied the "
    "atmosphere shall be gas tested every 30 minutes."
)
_REWORDED_TERSE = (
    "Prior to entry into the P-101A pump housing, the Supervisor shall establish "
    "that the pump is isolated and proved dead. Gas testing of the occupied space "
    "shall occur at 30 minute intervals."
)
_AMBIGUOUS = (
    "The Supervisor shall verify isolation of P-101A in accordance with the site "
    "isolation standard before entry. Gas testing shall be carried out as required "
    "by that standard."
)
_RESTRUCTURED = (
    "Entry to the P-101A pump housing requires the Supervisor to have proved the "
    "pump dead. The occupied space shall be gas tested at intervals not exceeding "
    "30 minutes."
)
_HOUSEKEEPING = (
    "The Supervisor shall verify that pump P-101A is isolated and proved dead "
    "before any person enters the pump housing. The atmosphere shall be gas tested "
    "at intervals not exceeding 30 minutes while the space is occupied. Records "
    "shall be retained for seven years."
)
_TABLE_FRAGMENT = (
    "The Supervisor shall verify that pump P-101A is isolated and proved dead "
    "before entry. Gas test interval: refer to Table 7.3-2 of this procedure."
)
_TRUNCATION_CASE = (
    "The Supervisor shall verify that pump P-101A is isolated and proved dead "
    "before any person enters the pump housing. The atmosphere shall be gas tested "
    "at intervals not exceeding 45 minutes while the space is occupied."
)
_GUARDRAIL_CASE = (
    "The Supervisor shall verify that pump P-101A is isolated and proved dead "
    "before any person enters the pump housing. Where hydrogen cyanide may be "
    "present the atmosphere shall be gas tested at intervals not exceeding 60 "
    "minutes while the space is occupied."
)
_REFUSAL_CASE = (
    "The Supervisor shall verify that pump P-101A is isolated and proved dead "
    "before any person enters the pump housing. Sodium cyanide residue shall be "
    "flushed before the atmosphere is gas tested at intervals not exceeding 90 "
    "minutes."
)

#: Every committed scenario.  The order is the file order of the README table.
SCENARIOS: Final[tuple[Scenario, ...]] = (
    Scenario(
        name="contradicts_high",
        request=_request(_LONGER_INTERVAL, "SHOULD", "120", exceptions=("where practicable",)),
        responses=(
            _body(
                _proposal(
                    "contradicts",
                    "high",
                    "at intervals not exceeding 120 minutes",
                    numeric_disagreement=True,
                    notes="The interval is four times longer and the modality is softened.",
                )
            ),
        ),
        expects="weaken at band high — the money path",
    ),
    Scenario(
        name="entails_high",
        request=_request(_SHORTER_INTERVAL, "MUST", "15"),
        responses=(
            _body(
                _proposal(
                    "entails",
                    "high",
                    "at intervals not exceeding 15 minutes",
                    numeric_disagreement=True,
                    notes="Shorter interval and an added recording step.",
                )
            ),
        ),
        expects="strengthen — a numeric claim supported by a quoted number",
    ),
    Scenario(
        name="neutral_high",
        request=_request(_REWORDED, "MUST", "30"),
        responses=(
            _body(
                _proposal(
                    "neutral",
                    "high",
                    "the atmosphere shall be gas tested every 30 minutes",
                    notes="Reordered and re-typeset; the obligation is unchanged.",
                )
            ),
        ),
        expects="restate accepted above theta",
    ),
    Scenario(
        name="neutral_low",
        request=_request(_REWORDED_TERSE, "MUST", "30"),
        responses=(
            _body(
                _proposal(
                    "neutral",
                    "low",
                    "Gas testing of the occupied space shall occur at 30 minute intervals",
                    notes="Nominalised; the actor is implied rather than stated.",
                )
            ),
        ),
        expects="below theta — resolves to weaken when the paths disagree",
    ),
    Scenario(
        name="model_abstains",
        request=_request(_AMBIGUOUS, "MUST", "30"),
        responses=(
            _body(
                _proposal(
                    "abstain",
                    "low",
                    "as required by that standard",
                    notes="B defers to a document that was not supplied.",
                )
            ),
        ),
        expects="abstained — the honest case",
    ),
    Scenario(
        name="quote_not_verbatim",
        request=_request(_RESTRUCTURED, "MUST", "30"),
        responses=(
            _body(
                _proposal(
                    "neutral",
                    "high",
                    "the Supervisor shall personally supervise every entry",
                    notes="",
                )
            ),
        ),
        expects="abstained — fabricated evidence, rejected by the verifier",
    ),
    Scenario(
        name="unsupported_numeric_claim",
        request=_request(_HOUSEKEEPING, "MUST", "30"),
        responses=(
            _body(
                _proposal(
                    "entails",
                    "high",
                    "Records shall be retained for seven years",
                    numeric_disagreement=True,
                    notes="",
                )
            ),
        ),
        expects="abstained — 'entails' with a numeric disagreement and no number quoted",
    ),
    Scenario(
        name="schema_violation",
        request=_request(_TABLE_FRAGMENT, "MUST", "30"),
        responses=(
            _body({"relation": "neutral", "confidence_band": "high"}),
            _body("I could not produce JSON for this one."),
        ),
        expects="abstained — invalid twice, then dead-lettered",
    ),
    Scenario(
        name="truncated",
        request=_request(_TRUNCATION_CASE, "MUST", "45"),
        responses=(_body(None, stop_reason="max_tokens"),),
        expects="abstained — a truncated structured output is fatal by decision A5",
    ),
    Scenario(
        name="guardrail_intervention",
        request=_request(_GUARDRAIL_CASE, "MUST", "60"),
        responses=(_body(None, stop_reason="end_turn", guardrail=True),),
        expects="abstained — Guardrails blocked the response",
    ),
    Scenario(
        name="model_refusal",
        request=_request(_REFUSAL_CASE, "MUST", "90"),
        responses=(_body(None, stop_reason="refusal"),),
        expects="abstained — a refusal on a cyanide corpus is plausible and is silence",
    ),
)


def scenario(name: str) -> Scenario:
    """Look one scenario up by name."""
    for item in SCENARIOS:
        if item.name == name:
            return item
    raise KeyError(f"unknown scenario {name!r}; known: {[item.name for item in SCENARIOS]}")


# ── the recording transport ─────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class RecordedCall:
    """One request the oracle actually issued, with the body it was served."""

    request: ModelRequest
    body: Mapping[str, Any]


class ScriptedTransport:
    """Serves a fixed list of bodies in order and remembers every request.

    Satisfies agentkit's ``Transport`` protocol.  It exists so the *retry* path
    can be recorded: the second attempt's cassette key depends on the validator's
    own complaint about the first, so the two keys can only be obtained by running
    the real call path.
    """

    def __init__(self, bodies: Sequence[Mapping[str, Any]]) -> None:
        """Bind the scripted bodies."""
        self._bodies = list(bodies)
        self.calls: list[RecordedCall] = []

    def _next(self, request: ModelRequest) -> ModelResponse:
        if not self._bodies:
            raise AssertionError(
                f"the scripted transport ran out of bodies at call {len(self.calls) + 1}; "
                f"a scenario must script one body per attempt the call path makes"
            )
        body = self._bodies.pop(0)
        self.calls.append(RecordedCall(request=request, body=body))
        return ModelResponse.from_body(body)

    def invoke(self, request: ModelRequest) -> ModelResponse:
        """Serve the next scripted body."""
        return self._next(request)

    def warm(self, request: ModelRequest, *, first_token: threading.Event) -> ModelResponse:
        """Serve the next scripted body, releasing the fan-out immediately."""
        try:
            return self._next(request)
        finally:
            first_token.set()


def recorded_calls(item: Scenario) -> list[RecordedCall]:
    """Run one scenario through the real call path and return what it put on the wire.

    Model-behaviour failures are absorbed by the oracle, which is the property
    under test; a configuration refusal would propagate and fail the generator,
    which is what it is for.
    """
    transport = ScriptedTransport(item.responses)
    oracle = AdjudicationOracle(transport=transport)
    oracle.classify(item.request)
    return transport.calls


def record_scenarios(root: Path) -> dict[str, list[str]]:
    """Record every scenario into ``root`` and return the keys, by scenario name."""
    store = CassetteStore(root, mode="record")
    written: dict[str, list[str]] = {}
    for item in SCENARIOS:
        keys: list[str] = []
        for call in recorded_calls(item):
            store.record(call.request, call.body, provenance=PROVENANCE_SYNTHETIC)
            keys.append(call.request.cassette_key)
        written[item.name] = keys
    return written


#: Header for the human-readable index written beside the recordings.
STORE_README: Final[str] = """\
<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
-->

# Path B cassettes

Committed recordings for `mainline-delta-oracle`, worker W5. Every file is keyed
`sha256(profile_id || prompt_version || jcs(call_input))` and every one carries
`"provenance": "synthetic"`: AWS credentials were not valid on the build machine
as of 2026-08, so **none of these responses has been near Bedrock**. That field is
what tells a synthetic recording from a live one, and nothing else does.

Regenerate with `mainline_delta_oracle.cassettes.record_scenarios(root)`. The
committed files are compared against a fresh generation by
`tests/unit/domain/resolution/test_oracle_cassettes.py`, so a stale fixture is a
failing build rather than a discovery.

| scenario | expects | keys |
|---|---|---|
"""
