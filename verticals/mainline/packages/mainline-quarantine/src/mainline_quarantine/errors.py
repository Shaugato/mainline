# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The refusal vocabulary of the quarantine.

Same two rules as ``mainline_agentkit.errors``, and for the same reason.

* **Nothing is absorbed.** No code path in this package catches one of these and turns
  it into a default. A blocked document is a *finding*, never an empty result: layer 6
  of ARCHITECTURE.md 8.4 is "the injection is evidence", and an exception swallowed on
  the way to a `document_intake_finding` row deletes the evidence.
* **Unknown means refused.** An anchor class this package cannot classify, a guardrail
  response shape it has never seen, an SQL role absent from the fleet register — all
  refuse rather than pass.

Naming: these do not end in ``Error`` (``N818`` is disabled repository-wide). The words
below are the words an operator sees.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__ = [
    "AnchorExtractorUnavailable",
    "CapabilityRefused",
    "GateFieldInSchema",
    "GuardrailConfigInvalid",
    "GuardrailResidencyRefused",
    "GuardrailUnavailable",
    "QuarantineError",
    "SentinelCollision",
    "UnknownAgent",
    "UntrustedSpanNotTagged",
]


class QuarantineError(Exception):
    """Base class for every refusal this package can raise."""


class SentinelCollision(QuarantineError):
    """The untrusted text already contains the sentinel minted for this request.

    Layer 2 delimits an untrusted span with a per-request random sentinel. If the
    document already contains that exact byte string, the attacker can close the block
    early and write outside it, so the request is refused and re-minted rather than
    sent. With 8 random bytes a collision by chance is ~2**-64 per request; a collision
    observed in practice means the sentinel leaked, which is a security event and not a
    retry.
    """

    def __init__(self, sentinel: str) -> None:
        """Record the sentinel that was found inside the untrusted text."""
        super().__init__(
            f"untrusted text contains its own delimiter {sentinel!r}: refusing to send. "
            f"A document that can close the block can write outside it "
            f"(ARCHITECTURE.md 8.4 layer 2)."
        )
        self.sentinel = sentinel


class UntrustedSpanNotTagged(QuarantineError):
    """A request carried untrusted text outside a Guardrails ``guardContent`` tag.

    This is the failure mode the posture exists to make impossible. Bedrock's
    ``PROMPT_ATTACK`` filter applies **only to tagged spans**; untagged untrusted text
    is passed to the model with the prompt-attack filter never having looked at it, and
    the response is a normal 200. A guardrail that is configured, billed and silently
    not applied is worse than none, because the architecture diagram claims it.
    """

    def __init__(self, detail: str) -> None:
        """Record which span was found untagged."""
        super().__init__(
            f"untrusted span is not inside a guardContent tag ({detail}): the "
            f"PROMPT_ATTACK filter applies only to tagged spans, so this request would "
            f"be unfiltered and look identical to a filtered one."
        )
        self.detail = detail


class GuardrailConfigInvalid(QuarantineError):
    """``config/guardrail.json`` does not express the posture 8.4 requires."""

    def __init__(self, reason: str) -> None:
        """Record exactly which clause of the posture the document fails."""
        super().__init__(f"guardrail.json is not a MAINLINE guardrail: {reason}")
        self.reason = reason


class GuardrailResidencyRefused(GuardrailConfigInvalid):
    """The guardrail document carries ``crossRegionConfig``.

    A guardrail profile routes guardrail inference to a *set* of destination Regions
    chosen by AWS, not by us. Attaching one to a MAINLINE guardrail would move the
    evaluation of Australian incident text out of the Region the endpoint policy pins,
    silently, with no error and no change in the response shape — and the residency
    argument in the submission would become false without a single line of our code
    changing. The key must be ABSENT: an empty object is not the same as absent, and
    this refuses both.
    """

    def __init__(self, value: object) -> None:
        """Record what the key held, so a reviewer sees it was not merely empty."""
        super().__init__(
            f"crossRegionConfig is present ({value!r}). It must be ABSENT: a guardrail "
            f"profile can route inference out of Australia and break the residency "
            f"argument with no error and no visible change."
        )
        self.value = value


class GuardrailUnavailable(QuarantineError):
    """The live Bedrock Guardrails screen was requested but cannot be constructed.

    Raised when ``boto3`` is absent, when no guardrail identifier is configured, or when
    the live path is selected without an explicit opt-in. AWS credentials are not valid
    on the build machine (PL-3), so this must fail loudly rather than degrade to the
    local screen: silently substituting a regex for ``PROMPT_ATTACK`` would be exactly
    the "unverified capability claimed as verified" defect the honesty rule forbids.
    """


class AnchorExtractorUnavailable(QuarantineError):
    """No anchor extractor could be constructed for layer 4.

    Layer 4 has two real implementations — the algorithms domain's ANCHORLOCK extractor,
    and the committed-gazetteer fallback in this package. It has no third mode in which
    it returns "no anchors" and lets the cue through: an extractor that finds nothing
    turns every anchor-based refusal into a pass.
    """


class CapabilityRefused(QuarantineError):
    """The caller holds an SQL role the fleet register does not grant this agent.

    Layer 5. The register is the authority; the caller's claim about itself is not. A
    process that has somehow acquired ``agent_gate`` while running the archivist is a
    process that can write a field the gate reads, and it stops here rather than at the
    first INSERT.
    """

    def __init__(self, agent: str, role: str, granted: Sequence[str]) -> None:
        """Name the agent, the role it presented, and what the register grants."""
        super().__init__(
            f"agent {agent!r} presented SQL role {role!r}, which spec/agents/fleet.yaml "
            f"does not grant it (granted: {sorted(granted)}). ARCHITECTURE.md 8.4 layer "
            f"5: the component that reads hostile text holds no capability to act on it."
        )
        self.agent = agent
        self.role = role
        self.granted = tuple(granted)


class UnknownAgent(QuarantineError):
    """The capability guard was asked about an agent the register does not contain.

    Fails closed. An agent absent from the register has no grant, so it has no
    permission; treating "not listed" as "unconstrained" is how a register stops being
    a control.
    """

    def __init__(self, agent: str, known: Sequence[str]) -> None:
        """Name the missing agent and list the register's agents."""
        super().__init__(
            f"agent {agent!r} is not in the fleet register (known: {sorted(known)}); "
            f"an unlisted agent holds no grant, so this is a refusal, not a default."
        )
        self.agent = agent
        self.known = tuple(known)


class GateFieldInSchema(QuarantineError):
    """A structured-output schema declared a field that arms the gate.

    Layer 3's static half. An extraction schema containing ``severity`` would give a
    model a legitimate, schema-valid channel into a field ARCHITECTURE.md 8.4 says only
    a coded field, a regulator classification or a signed human may set. The control is
    that the field is not *expressible*, and this is the assertion that keeps it so.
    """

    def __init__(self, schema_name: str, field: str, pointer: str) -> None:
        """Name the schema, the field, and the JSON pointer it appeared at."""
        super().__init__(
            f"schema {schema_name!r} declares gate-arming field {field!r} at {pointer}: "
            f"a model must not be able to express it at all (ARCHITECTURE.md 8.4)."
        )
        self.schema_name = schema_name
        self.field = field
        self.pointer = pointer
