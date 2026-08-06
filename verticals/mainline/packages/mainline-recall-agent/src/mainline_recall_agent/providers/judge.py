# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""``BedrockClaudeJudge`` — the listwise judge, with exactly one repair attempt.

The shape of this module is the whole point:

* ``stop_reason`` is read **before** ``content``.  ``"refusal"`` raises ``ModelRefusal``
  so the caller writes ``silence_ledger(reason='model_refusal')`` and falls back to
  channels A+B client-side.  *A precursor the model declined to summarise must still block
  the merge* (ARCHITECTURE §8.4).  Reading content first — the natural way to write this —
  would turn a refusal into an empty candidate list and a merge that proceeds.
* Schema violation gets **one** repair call carrying the validator error, then
  ``DeadLetter``.  Two calls, never three, and the count is asserted by a test.  The loop
  is written out longhand: a blanket-retry helper is banned from this codebase
  (ARCHITECTURE §6.5), because a retry loop against an ill-posed prompt is how a silent
  extraction failure becomes a silent memory gap.
* Transport is injected.  Live Bedrock and cassette replay differ *only* in the transport,
  so the refusal path, the repair path and the dead-letter path that CI exercises are the
  same lines of code that run in production.

Nothing here hard-codes a model identifier; the judge is constructed with a
``ResolvedModel`` produced by ``resolve.py`` at start-up (recall.md D5).
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any, Final, Protocol, cast

from pydantic import BaseModel, ValidationError

from .canonical import request_digest
from .errors import DeadLetter, ModelRefusal, ModelTruncated, ProviderError, ProviderUnavailable
from .schema import output_config
from .system_blocks import SystemPrefix, build_user_turn
from .types import JudgeResult, ResolvedModel, Usage, ValidatedModelT

__all__ = ["ANTHROPIC_API_VERSION", "BedrockClaudeJudge", "JudgeTransport", "TransportReply"]

ANTHROPIC_API_VERSION: Final[str] = "anthropic.messages/2023-06-01"

#: Bedrock/Anthropic stop reasons this code branches on.  Anything else is treated as a
#: normal completion and validated; an unknown stop reason with unparseable content
#: therefore dead-letters rather than being silently accepted.
STOP_REFUSAL: Final[str] = "refusal"
STOP_MAX_TOKENS: Final[str] = "max_tokens"


class TransportReply(BaseModel):
    """The normalised reply every transport returns."""

    model_config = {"frozen": True, "extra": "forbid"}

    stop_reason: str
    text: str
    usage: Usage = Usage()


class JudgeTransport(Protocol):
    """One call, one reply.  No retries live here — retry policy is the judge's."""

    def send(self, request: dict[str, Any]) -> TransportReply: ...


class BedrockTransport:
    """Live transport over the Anthropic Bedrock SDK, pinned to the resolved ``au.*`` id.

    Unverified on this machine: no AWS credentials, so this path has never executed here.
    The cassette transport is the CI and demo default and the shapes below are what
    ``GT-RC-01`` exists to confirm.
    """

    def __init__(self, *, resolved_model: ResolvedModel, client: Any | None = None) -> None:
        self._model = resolved_model
        self._client = client

    def _anthropic(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            from anthropic import AnthropicBedrock
        except ImportError as exc:  # pragma: no cover - anthropic is a declared dependency
            raise ProviderUnavailable("the anthropic SDK is not installed") from exc
        try:
            self._client = AnthropicBedrock(aws_region=self._model.region)
        except Exception as exc:  # pragma: no cover - requires a live AWS session
            raise ProviderUnavailable(
                "cannot construct an AnthropicBedrock client (no credentials or no route)",
                region=self._model.region,
            ) from exc
        return self._client

    def send(self, request: dict[str, Any]) -> TransportReply:
        client = self._anthropic()
        try:
            response = client.messages.create(
                model=self._model.profile_id,
                max_tokens=request["max_tokens"],
                system=request["system"],
                messages=request["messages"],
                output_config=request["output_config"],
            )
        except Exception as exc:  # pragma: no cover - requires a live endpoint
            raise ProviderUnavailable(
                "Bedrock InvokeModel failed on the judge leg; recall degrades to A+B and "
                "records arms_degraded",
                profile_id=self._model.profile_id,
                error=type(exc).__name__,
            ) from exc
        return normalise_sdk_response(response)


def normalise_sdk_response(response: Any) -> TransportReply:
    """Flatten an SDK message object into ``TransportReply``.

    ``stop_reason`` is copied verbatim, before any content is touched, so the caller's
    ordering guarantee cannot be lost in this function either.
    """
    stop_reason = str(getattr(response, "stop_reason", "") or "")
    usage_obj = getattr(response, "usage", None)
    usage = Usage(
        input_tokens=int(getattr(usage_obj, "input_tokens", 0) or 0),
        output_tokens=int(getattr(usage_obj, "output_tokens", 0) or 0),
        cache_creation_input_tokens=int(
            getattr(usage_obj, "cache_creation_input_tokens", 0) or 0
        ),
        cache_read_input_tokens=int(getattr(usage_obj, "cache_read_input_tokens", 0) or 0),
    )
    chunks: list[str] = []
    for block in getattr(response, "content", []) or []:
        if getattr(block, "type", None) == "text":
            chunks.append(str(getattr(block, "text", "")))
    return TransportReply(stop_reason=stop_reason, text="".join(chunks), usage=usage)


class BedrockClaudeJudge:
    """The listwise judge.  Implements ``JudgeProvider``."""

    #: One initial call plus at most one repair call.  Not a tunable.
    MAX_ATTEMPTS: Final[int] = 2

    def __init__(
        self,
        *,
        resolved_model: ResolvedModel,
        transport: JudgeTransport | None = None,
        max_tokens: int = 4096,
        prompt_version: str = "recall-judge-1",
    ) -> None:
        self._model = resolved_model
        self._transport: JudgeTransport = transport or BedrockTransport(
            resolved_model=resolved_model
        )
        self._max_tokens = max_tokens
        self._prompt_version = prompt_version
        self._last_usage: Usage | None = None
        self._call_count = 0

    @property
    def resolved_model(self) -> ResolvedModel:
        return self._model

    @property
    def last_usage(self) -> Usage | None:
        """Usage from the most recent transport call, refusals and failures included."""
        return self._last_usage

    @property
    def call_count(self) -> int:
        """Transport calls made over this judge's lifetime.  Asserted by tests."""
        return self._call_count

    # -- request construction ----------------------------------------------------------

    def build_request(
        self,
        *,
        system: SystemPrefix,
        messages: list[dict[str, Any]],
        schema: type[BaseModel],
    ) -> dict[str, Any]:
        """The canonical request.

        The profile id and ARN are deliberately **absent**: they are deployment metadata,
        recorded in ``recall_run`` and in the cassette's response envelope, but not part of
        what identifies the request.  Keying on them would make every cassette account- and
        region-specific for no evidentiary gain.
        """
        return {
            "api": ANTHROPIC_API_VERSION,
            "kind": "judge",
            "model": {
                "family": "anthropic-claude",
                "requested_tier": self._model.requested_tier,
                "resolved_tier": self._model.resolved_tier,
            },
            "prompt_version": self._prompt_version,
            "max_tokens": self._max_tokens,
            "system": system.wire(),
            "messages": messages,
            "output_config": output_config(schema),
        }

    @staticmethod
    def _coerce_prefix(system_blocks: Sequence[Any] | SystemPrefix) -> SystemPrefix:
        if isinstance(system_blocks, SystemPrefix):
            return system_blocks
        raise ProviderError(
            "system_blocks must be a SystemPrefix built by build_system_blocks(); a raw "
            "list bypasses the stability contract that makes the cache breakpoint real"
        )

    # -- the call ----------------------------------------------------------------------

    def judge(
        self,
        system_blocks: Sequence[Any] | SystemPrefix,
        user_payload: dict[str, Any],
        schema: type[ValidatedModelT],
    ) -> ValidatedModelT:
        """Validated answer, or an exception that names its silence-ledger reason."""
        result = self.judge_detailed(system_blocks, user_payload, schema)
        return cast(ValidatedModelT, result.value)

    def judge_detailed(
        self,
        system_blocks: Sequence[Any] | SystemPrefix,
        user_payload: dict[str, Any],
        schema: type[ValidatedModelT],
    ) -> JudgeResult:
        prefix = self._coerce_prefix(system_blocks)
        messages: list[dict[str, Any]] = [build_user_turn(user_payload)]
        first_request = self.build_request(system=prefix, messages=messages, schema=schema)
        digest = request_digest(first_request)
        attempts: list[dict[str, Any]] = []

        # ------------------------------------------------------------------------------
        # ATTEMPT 1.  Written out rather than looped through a helper: ARCHITECTURE §6.5
        # bans a blanket-retry helper, and the ban is only real if the code has no place
        # to hide one.
        # ------------------------------------------------------------------------------
        reply = self._send(first_request)
        self._check_stop_reason(reply, digest)
        parsed, error = self._validate(reply.text, schema)
        if parsed is not None:
            return JudgeResult(
                value=parsed,
                request_digest=digest,
                usage=reply.usage,
                model=self._model,
                stop_reason=reply.stop_reason,
                attempts=1,
            )
        attempts.append({"attempt": 1, "raw": reply.text[:4000], "error": error})

        # ------------------------------------------------------------------------------
        # ATTEMPT 2 — the ONE repair.  The validator's own message goes back verbatim;
        # nothing about the task is restated, because restating it is how a repair turn
        # becomes a second, unversioned prompt.
        # ------------------------------------------------------------------------------
        repair_messages: list[dict[str, Any]] = [
            *messages,
            {"role": "assistant", "content": [{"type": "text", "text": reply.text}]},
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "The previous response failed schema validation with the "
                            f"following error:\n{error}\n"
                            "Return the corrected object only, in the declared schema."
                        ),
                    }
                ],
            },
        ]
        repair_request = self.build_request(
            system=prefix, messages=repair_messages, schema=schema
        )
        repair_reply = self._send(repair_request)
        self._check_stop_reason(repair_reply, digest)
        parsed, error = self._validate(repair_reply.text, schema)
        if parsed is not None:
            return JudgeResult(
                value=parsed,
                request_digest=digest,
                usage=repair_reply.usage,
                model=self._model,
                stop_reason=repair_reply.stop_reason,
                attempts=2,
            )
        attempts.append({"attempt": 2, "raw": repair_reply.text[:4000], "error": error})

        raise DeadLetter(
            "listwise judge produced schema-invalid output twice; the caller must write "
            "silence_ledger(reason='abstained') rather than treat this as 'no candidates'",
            request_digest=digest,
            attempts=attempts,
            model=self._model.model_dump(mode="json"),
            schema_name=schema.__name__,
        )

    # -- internals ---------------------------------------------------------------------

    def _send(self, request: dict[str, Any]) -> TransportReply:
        self._call_count += 1
        reply = self._transport.send(request)
        self._last_usage = reply.usage
        return reply

    def _check_stop_reason(self, reply: TransportReply, digest: str) -> None:
        """Read stop_reason BEFORE content.  Order is the contract (ARCHITECTURE §8.4)."""
        if reply.stop_reason == STOP_REFUSAL:
            raise ModelRefusal(
                "the model refused; the precursor it declined to summarise still blocks "
                "the merge, and the refusal is recorded as silence",
                request_digest=digest,
                profile_id=self._model.profile_id,
                resolved_tier=self._model.resolved_tier,
            )
        if reply.stop_reason == STOP_MAX_TOKENS:
            raise ModelTruncated(
                "the judge response hit max_tokens; a cut-off answer is not an answer",
                request_digest=digest,
                max_tokens=self._max_tokens,
            )

    @staticmethod
    def _validate(
        text: str, schema: type[ValidatedModelT]
    ) -> tuple[ValidatedModelT | None, str]:
        stripped = text.strip()
        if not stripped:
            return None, "empty response body"
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError as exc:
            return None, f"response was not valid JSON: {exc}"
        try:
            return schema.model_validate(payload), ""
        except ValidationError as exc:
            return None, exc.json(include_url=False)
