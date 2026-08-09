# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""One wire for the recall agent: `JudgeTransport` implemented over `mainline-agentkit`.

The recall agent's judge injects its transport (`BedrockClaudeJudge(transport=…)`) so
that *the refusal path, the repair path and the dead-letter path that CI exercises are
the same lines of code that run in production*.  This class is a third implementation of
that seam — beside the recall package's own live and cassette transports — and what it
buys is that the recall agent's model calls stop being a second, parallel model runtime:

* **Residency is asserted at start-up, once, and cannot be declined.**  The `au.*`
  assertion runs in `__init__`, not per call, for the reason
  `mainline_agentkit.runtime` gives: an assertion that lives inside a transport's call
  path runs on the live provider only and can be skipped by a caller who passes a model
  id by hand, and *a control a caller can decline is not a control*.
* **`thinking` and `output_config.effort` reach the wire** (decisions A5 and A4).  See
  `body.py` — the recall judge's own request carries neither.
* **Refusal is classified before content is touched, by the fleet's classifier.**
  `mainline_agentkit.refusal.interpret` also catches a Bedrock **Guardrail
  intervention**, which is reported out of band from `stop_reason` and which the recall
  judge's `_check_stop_reason` therefore cannot see, and it **fails closed on an
  unrecognised stop reason** rather than treating it as a normal completion.  Both
  become a recall `ModelRefusal`, so the orchestrator's existing degraded path fires
  unchanged.
* **Silence is one row built by one implementation.**  :func:`fleet_silence_row` returns
  a `mainline_meas.silence_ledger` row carrying the replayability quad; this package
  holds no driver and no credential, so the caller writes it through its own SQL role.

**What this class refuses to do.**  It does not retry.  Retry policy is the judge's — one
call, one repair, then `DeadLetter` — and a retry helper inside a transport is exactly
the blanket-retry helper ARCHITECTURE §6.5 bans.  It also does not touch the request's
system array, its messages or its schema: the request digest the cassettes and the ledger
are keyed on is computed over those bytes, and a binding that rewrote them would silently
invalidate every recorded interaction.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from mainline_agentkit import (
    CassetteMiss as AgentkitCassetteMiss,
)
from mainline_agentkit import (
    ModelRefused,
    ModelRequest,
    ResidencyRefused,
    SilenceRow,
    Transport,
    TransportUnavailable,
    TruncatedResponse,
    UnknownStopReason,
    assert_australian_profile,
    cassette_key,
    interpret,
    silence_row_for_refusal,
)
from mainline_agentkit.cache import prefix_digest
from mainline_recall_agent.providers.canonical import request_digest, sha256_hex
from mainline_recall_agent.providers.errors import (
    CassetteMiss,
    ModelRefusal,
    ModelTruncated,
    ProviderError,
    ProviderUnavailable,
    ResidencyViolation,
)
from mainline_recall_agent.providers.judge import TransportReply
from mainline_recall_agent.providers.types import Usage

from .body import build_fleet_body
from .errors import FleetContractViolation
from .legs import get_leg

if TYPE_CHECKING:
    from mainline_agentkit import ModelResponse

    from .legs import RecallLeg

__all__ = ["FleetJudgeTransport", "fleet_silence_row"]


class FleetJudgeTransport:
    """A recall `JudgeTransport` that sends through the fleet's request contract.

    Attributes:
        leg: the registered leg every call through this transport runs as.
        inference_profile_arn: the resolved ``au.*`` ARN, asserted at construction.
    """

    def __init__(
        self,
        *,
        inner: Transport,
        leg: RecallLeg,
        inference_profile_arn: str,
        iam_role_arn: str = "",
    ) -> None:
        """Bind a leg to a provider, asserting residency before anything can be sent.

        Args:
            inner: an agentkit transport — the cassette provider offline, the
                `bedrock-runtime` `InvokeModel` provider live.  Nothing else is
                accepted, because the two guards that make a body legal live inside the
                agentkit transport as well as in `body.py`.
            leg: the registered leg.  Its prompt version and budget are cross-checked
                against every request.
            inference_profile_arn: the ``au.*`` inference profile this transport serves
                against.  An offline replay must declare one too: *a replay that cannot
                name the profile it replays cannot carry its provenance either.*
            iam_role_arn: the execution role, carried into
                :meth:`identity_components` and otherwise unused.

        Raises:
            FleetContractViolation: ``inner`` is not an agentkit transport.
            ResidencyViolation: the identifier is not an Australian inference profile.
                A ``global.*`` profile routes to every commercial Region and a bare
                foundation-model id bypasses the very ARNs the VPC-endpoint policy
                enumerates.
        """
        if not isinstance(inner, Transport):
            raise FleetContractViolation(
                "the inner provider does not implement the agentkit Transport protocol; "
                "the body guards that make a request legal run inside that protocol's "
                "implementations as well as in this package",
                observed=type(inner).__name__,
                decision="A3",
            )
        try:
            profile_id = assert_australian_profile(inference_profile_arn)
        except ResidencyRefused as refusal:
            raise ResidencyViolation(
                str(refusal),
                leg_id=leg.leg_id,
                identifier=inference_profile_arn,
                decision="ARCHITECTURE §10.1 layer 1",
            ) from refusal
        self._inner = inner
        self._leg = leg
        self._arn = inference_profile_arn
        self._profile_id = profile_id
        self._iam_role_arn = iam_role_arn
        self._calls = 0
        self._last_request: ModelRequest | None = None
        self._last_response: ModelResponse | None = None
        self._last_output_sha256: str | None = None

    # -- introspection -----------------------------------------------------------------

    @property
    def leg(self) -> RecallLeg:
        """The leg this transport serves."""
        return self._leg

    @property
    def inference_profile_arn(self) -> str:
        """The ARN asserted at construction and sent as ``modelId`` on every call."""
        return self._arn

    @property
    def inference_profile_id(self) -> str:
        """The profile id — the part of the ARN after the last ``/``."""
        return self._profile_id

    @property
    def call_count(self) -> int:
        """Transport calls made over this transport's lifetime.  Asserted by tests."""
        return self._calls

    # -- the seam ----------------------------------------------------------------------

    def send(self, request: dict[str, Any]) -> TransportReply:
        """Send one recall judge request and return the normalised reply.

        Args:
            request: the canonical request from `BedrockClaudeJudge.build_request`.

        Returns:
            A `TransportReply` the recall judge validates exactly as it validates the
            replies from its own transports.  A response with no text block returns an
            empty ``text``, which the judge turns into its one repair attempt and then a
            `DeadLetter` — the retry rule stays where it belongs.

        Raises:
            ModelRefusal: the model declined, or a Bedrock Guardrail intervened, or the
                stop reason was unrecognised.  The caller writes
                ``silence_ledger(reason='model_refusal')`` and completes on channels
                A+B.  *A precursor the model declined to summarise must still block the
                merge.*
            ModelTruncated: ``max_tokens`` was reached.  A cut-off answer is not an
                answer.
            ProviderUnavailable: the provider could not be reached at all.  Nothing was
                asked and nothing was declined, so the candidate is ``unreachable``
                rather than ``abstained``.
            CassetteMiss: replay mode with no recording for this request.  A defect, not
                silence: replay never falls through to a live call.
            FleetContractViolation, PromptVersionDrift, BudgetDrift: the request breaks
                the model-call contract and never reaches a wire.
        """
        body = build_fleet_body(request, self._leg)
        digest = request_digest(request)
        model_request = ModelRequest(
            body=body,
            model_id=self._arn,
            profile_id=self._leg.leg_id,
            prompt_version=self._leg.prompt_version,
            # Keyed on the digest rather than on the request object: the recall package
            # canonicalises under RFC 8785 with its own float rules, and two
            # canonicalisers disagreeing about one key is a cassette collision nobody
            # would notice until a replay asserted the wrong thing.
            cassette_key=cassette_key(
                self._leg.leg_id,
                self._leg.prompt_version,
                {"recall_request_sha256": digest},
            ),
            prefix_digest=prefix_digest(body["system"]),
            input_sha256=digest,
        )
        self._calls += 1
        self._last_request = model_request
        self._last_response = None
        self._last_output_sha256 = None
        response = self._invoke(model_request)
        self._last_response = response
        # stop_reason BEFORE content, and by the fleet's classifier rather than by a
        # second copy of the rule.  Everything below this line has already been cleared.
        self._interpret(response, digest)
        text = response.last_text_block() or ""
        self._last_output_sha256 = sha256_hex(text.encode("utf-8"))
        return TransportReply(
            stop_reason=str(response.stop_reason or ""),
            text=text,
            usage=_usage(response),
        )

    # -- provenance --------------------------------------------------------------------

    def provenance(self) -> dict[str, Any]:
        """The replayability record for the most recent call.

        ARCHITECTURE §8.2 claims two weaker, true things instead of reproducibility —
        replayability and arithmetic reproducibility — and every field of the first is
        here, so the orchestrator can write ``recall_run`` and
        ``agent_action_provenance`` without reaching back into either package.

        Raises:
            FleetContractViolation: no call has been made through this transport.
        """
        request = self._last_request
        if request is None:
            raise FleetContractViolation(
                "no call has been made through this transport, so there is no provenance "
                "to report; an empty record here would be a claim about a call that never "
                "happened",
                leg_id=self._leg.leg_id,
            )
        usage = _usage(self._last_response) if self._last_response is not None else Usage()
        return {
            "leg_id": self._leg.leg_id,
            "agent_name": self._leg.agent,
            "sql_role": self._leg.sql_role,
            "tier": str(self._leg.tier),
            "effort": str(self._leg.effort),
            "model_id": self._leg.model_key,
            "inference_profile_id": self._profile_id,
            "inference_profile_arn": self._arn,
            "prompt_version": self._leg.prompt_version,
            "prefix_digest": request.prefix_digest,
            "cassette_key": request.cassette_key,
            "input_sha256": request.input_sha256,
            "output_sha256": self._last_output_sha256 or "",
            "stop_reason": (
                str(self._last_response.stop_reason or "") if self._last_response else ""
            ),
            "usage": usage.model_dump(),
            "cache_read_input_tokens": usage.cache_read_input_tokens,
            "cache_creation_input_tokens": usage.cache_creation_input_tokens,
            "transport": type(self._inner).__name__,
        }

    def identity_components(self, *, schema_version: str) -> dict[str, str]:
        """The seven ``agent_identity`` components for this leg, in concatenation order.

        The digest belongs to `mainline-provenance`; this returns the inputs.
        """
        return self._leg.identity_components(
            iam_role_arn=self._iam_role_arn,
            model_id=self._leg.model_key,
            inference_profile_arn=self._arn,
            schema_version=schema_version,
        )

    # -- internals ---------------------------------------------------------------------

    def _invoke(self, request: ModelRequest) -> ModelResponse:
        try:
            return self._inner.invoke(request)
        except AgentkitCassetteMiss as miss:
            raise CassetteMiss(
                str(miss),
                leg_id=self._leg.leg_id,
                cassette_key=request.cassette_key,
            ) from miss
        except TransportUnavailable as unavailable:
            raise ProviderUnavailable(
                str(unavailable),
                leg_id=self._leg.leg_id,
                inference_profile_arn=self._arn,
            ) from unavailable

    def _interpret(self, response: ModelResponse, digest: str) -> None:
        context: dict[str, Any] = {
            "leg_id": self._leg.leg_id,
            "prompt_version": self._leg.prompt_version,
            "model_id": self._leg.model_key,
            "inference_profile_arn": self._arn,
            "input_sha256": digest,
            "request_digest": digest,
            "usage": _usage(response).model_dump(),
        }
        try:
            interpret(response, max_tokens=self._leg.max_tokens)
        except ModelRefused as refusal:
            raise ModelRefusal(
                "the model declined; the precursor it refused to summarise still blocks "
                "the merge, and the refusal is recorded as silence",
                category=refusal.category,
                stop_reason=refusal.stop_reason,
                **context,
            ) from refusal
        except TruncatedResponse as truncated:
            raise ModelTruncated(
                "the response hit its budget; max_tokens caps thinking plus text, so a "
                "cut-off answer is not an answer",
                category="truncated",
                stop_reason=str(response.stop_reason or ""),
                max_tokens=self._leg.max_tokens,
                **context,
            ) from truncated
        except UnknownStopReason as unknown:
            # Fail closed.  The recall judge's own `_check_stop_reason` branches on two
            # known values and treats everything else as a normal completion; a future
            # model generation adding a stop reason we silently accept is precisely how a
            # memory gap opens without anyone noticing.
            raise ModelRefusal(
                "the response carried an unrecognised stop reason; it is treated as a "
                "refusal rather than as a completion, because a stop reason nobody has "
                "classified is not evidence that the model answered",
                category="unknown_stop_reason",
                stop_reason=str(response.stop_reason or ""),
                **context,
            ) from unknown


def fleet_silence_row(
    error: ProviderError,
    *,
    site_id: str,
    subject_kind: str,
    subject_id: str,
    severity: int,
    policy_version: str | None = None,
) -> SilenceRow:
    """Turn a silence-bearing recall error into its `silence_ledger` row.

    Decision A8: *refusal is silence, and silence is a row.*  The row's ``arithmetic``
    carries the replayability quad rather than a score, because for a refusal there is no
    score — the honest content of the field is *which model, under which prompt version,
    on which profile, over which input* declined.

    Args:
        error: a recall provider error raised through :class:`FleetJudgeTransport`.  It
            must carry a ``silence_reason``; a defect must crash the run instead.
        site_id: the site the subject belongs to.
        subject_kind: what the silence is about (``'event'``, ``'permit'``, …).
        subject_id: the subject's identifier.
        severity: the subject's severity, so a suppressed fatality is visible as one.
        policy_version: the recall policy in force, when there is one.

    Raises:
        FleetContractViolation: the error carries no silence reason (a defect in our own
            code, which must never be recorded as a fact about the corpus), or it was not
            raised through this transport and therefore carries no leg.
    """
    reason = getattr(error, "silence_reason", None)
    if reason is None:
        raise FleetContractViolation(
            "this error is a defect, not silence; a ProviderError with no silence_reason "
            "is a bug in our code rather than a fact about the corpus, and recording it "
            "as silence would put a false absence into the ledger",
            error_type=type(error).__name__,
        )
    context = dict(error.context)
    leg_id = str(context.get("leg_id", ""))
    if not leg_id:
        raise FleetContractViolation(
            "the error carries no leg; a silence row whose source cannot be attributed to "
            "a declared capability is a row nobody can check",
            error_type=type(error).__name__,
        )
    leg = get_leg(leg_id)
    if reason not in leg.silence_reasons:
        raise FleetContractViolation(
            "the leg does not declare this silence reason; the register is the complete "
            "statement of what this capability can fail as",
            leg_id=leg_id,
            reason=reason,
            declared=sorted(leg.silence_reasons),
        )
    arithmetic: dict[str, Any] = {
        "category": context.get("category", reason),
        "stop_reason": context.get("stop_reason"),
        "leg_id": leg_id,
        "profile_id": leg_id,
        "prompt_version": context.get("prompt_version", leg.prompt_version),
        "model_id": context.get("model_id", leg.model_key),
        "inference_profile_arn": context.get("inference_profile_arn", ""),
        "input_sha256": context.get("input_sha256", ""),
        "usage": context.get("usage", {}),
        "fallback": leg.degrades_to,
    }
    if reason == "model_refusal":
        # One implementation of the refusal row, and it is agentkit's.
        return silence_row_for_refusal(
            ModelRefused(
                category=str(arithmetic["category"]),
                stop_reason=(
                    None if arithmetic["stop_reason"] is None else str(arithmetic["stop_reason"])
                ),
            ),
            site_id=site_id,
            source=leg.silence_source,
            subject_kind=subject_kind,
            subject_id=subject_id,
            severity=severity,
            profile_id=leg_id,
            prompt_version=str(arithmetic["prompt_version"]),
            model_id=str(arithmetic["model_id"]),
            inference_profile_arn=str(arithmetic["inference_profile_arn"]),
            input_sha256=str(arithmetic["input_sha256"]),
            policy_version=policy_version,
        )
    return SilenceRow(
        site_id=site_id,
        source=leg.silence_source,
        reason=reason,
        subject_kind=subject_kind,
        subject_id=subject_id,
        severity=severity,
        arithmetic=arithmetic,
        policy_version=policy_version,
    )


def _usage(response: ModelResponse | None) -> Usage:
    """Translate an agentkit usage block into the recall package's own."""
    if response is None:
        return Usage()
    usage = response.usage
    return Usage(
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        cache_creation_input_tokens=usage.cache_creation_input_tokens,
        cache_read_input_tokens=usage.cache_read_input_tokens,
    )
