# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The six layers, in the order they actually run, over one document.

:func:`intake` is the whole posture in one function, and reading it top to bottom is the
shortest honest description of what MAINLINE does with an untrusted document::

    L5  capability starvation   - before a byte is read
    L1  structural quarantine   - not a step; the call shape, proved by the AST scan
    L2  delimit, datamark, screen
    L3  output-schema containment
    L4  semantic anchoring
    L6  every non-clean verdict becomes a finding

**Short-circuiting is the design, and it is why every corpus case names a layer.** When
layer 2 blocks a document, layers 3 and 4 never run - there is no model call to contain
and no cue to anchor, because the extraction never happened. A case whose expected
outcome is ``CONTAINED_UNKNOWN_FIELD`` is therefore also a case asserting that layer 2
did *not* fire on it, which is a stronger statement than it looks: it is the statement
that the corpus is not passing because one over-eager regex catches everything.

**The proposal is supplied, not generated.** ``intake`` takes the payload a *fully
compromised* model would return - one that did exactly what the injected text asked - and
reports what the deterministic layers do with it. That is deliberately the pessimistic
assumption, and it is the only one that can be tested without a model in the loop: we do
not claim the model resists injection, we claim that if it does not, the layers after it
still refuse.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .anchoring import verify_anchors
from .capability import require_capability
from .classes import OUTCOME_LAYER, Layer, Outcome
from .containment import contain
from .finding import (
    DocumentIntakeFinding,
    finding_from_anchor_verdict,
    finding_from_capability,
    finding_from_containment,
    finding_from_screen,
)
from .sentinel import wrap_untrusted

if TYPE_CHECKING:
    from collections.abc import Mapping
    from datetime import datetime

    from .anchoring import AnchorExtractor, AnchorVerdict, Cue
    from .capability import CapabilityVerdict, FleetRegister
    from .containment import ContainmentResult
    from .screen import PromptAttackScreen, ScreenResult

__all__ = ["IntakeVerdict", "ProcessCapability", "UntrustedDocument", "intake"]


@dataclass(frozen=True, slots=True)
class UntrustedDocument:
    """Text extracted from a customer document, and the digest of the bytes it came from.

    ``source_sha256`` is not decorative. It is the custody preamble's digest (8.6), and
    it is what ties a finding to an Object-Locked object, which is what makes the finding
    worth writing down.
    """

    doc_id: str
    text: str
    source_sha256: str
    media_type: str = "text/plain"


@dataclass(frozen=True, slots=True)
class ProcessCapability:
    """What the running process actually holds, for layer 5 to compare with the register."""

    agent: str
    register: FleetRegister
    sql_roles: tuple[str, ...] = ()
    tools: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class IntakeVerdict:
    """The verdict of the whole posture on one document."""

    outcome: Outcome
    layer: Layer | None
    findings: tuple[DocumentIntakeFinding, ...]
    capability: CapabilityVerdict | None
    screen: ScreenResult | None
    containment: ContainmentResult | None
    anchors: AnchorVerdict | None
    sentinel: str = ""
    tag_suffix: str = ""

    @property
    def admitted(self) -> bool:
        """Whether the extraction may be inserted at all.

        ``VALUE_ONLY_DISTORTION`` is **admitted and flagged**: the payload is schema-valid
        and the record now carries a value an attacker moved. Refusing it here would be a
        lie about what the posture achieved, and hiding it would be worse.
        """
        return self.outcome in {Outcome.CLEAN, Outcome.VALUE_ONLY_DISTORTION}


def intake(
    document: UntrustedDocument,
    *,
    screen: PromptAttackScreen,
    capability: ProcessCapability | None = None,
    proposal: Mapping[str, Any] | None = None,
    schema: Mapping[str, Any] | None = None,
    baseline: Mapping[str, Any] | None = None,
    cue: Cue | None = None,
    extractor: AnchorExtractor | None = None,
    observed_at: datetime | None = None,
    sentinel: str | None = None,
    tag_suffix: str | None = None,
) -> IntakeVerdict:
    """Run the posture over one document and return the first refusal, with its finding.

    Args:
        document: the extracted text and its custody digest.
        screen: the layer-2 screen. The offline heuristic screen or the live Guardrails
            screen; the pipeline does not know which and must not.
        capability: what the process holds, for layer 5. ``None`` skips the check and is
            appropriate only for a caller that has already run it at start-up - which is
            where it belongs, since checking it after reading hostile text is late.
        proposal: the payload a fully compromised model would return, for layer 3.
        schema: the wire schema that call was constrained by.
        baseline: the honest reading, so a value-only distortion can be named exactly.
        cue: the model proposal in the form layer 4 reads.
        extractor: ANCHORLOCK or the gazetteer fallback.
        observed_at: fixed instant, so a test's findings are byte-stable.
        sentinel: injected only by tests that need a deterministic wrapping.
        tag_suffix: injected only by tests that need a deterministic wrapping.

    Returns:
        The verdict, carrying every finding produced on the way.
    """
    findings: list[DocumentIntakeFinding] = []
    digest = document.source_sha256

    capability_verdict: CapabilityVerdict | None = None
    if capability is not None:
        capability_verdict = require_capability(
            capability.agent,
            capability.register,
            sql_roles=capability.sql_roles,
            tools=capability.tools,
            raising=False,
        )
        finding = finding_from_capability(
            capability_verdict, document_sha256=digest, observed_at=observed_at
        )
        if finding is not None:
            findings.append(finding)
            return IntakeVerdict(
                outcome=capability_verdict.outcome,
                layer=Layer.L5_CAPABILITY_STARVATION,
                findings=tuple(findings),
                capability=capability_verdict,
                screen=None,
                containment=None,
                anchors=None,
            )

    # Layer 2, first half. The wrapping is done here rather than at the call site so that
    # a document which contains our own delimiters is refused before it is screened - a
    # SentinelCollision is not caught and converted, it propagates.
    tagged = wrap_untrusted(document.text, sentinel=sentinel, tag_suffix=tag_suffix)

    screen_result = screen.screen(document.text)
    screen_finding = finding_from_screen(
        screen_result, document_sha256=digest, observed_at=observed_at
    )
    if screen_finding is not None:
        findings.append(screen_finding)
    if screen_result.blocked:
        return IntakeVerdict(
            outcome=screen_result.outcome,
            layer=screen_result.layer,
            findings=tuple(findings),
            capability=capability_verdict,
            screen=screen_result,
            containment=None,
            anchors=None,
            sentinel=tagged.sentinel,
            tag_suffix=tagged.tag_suffix,
        )

    containment_result: ContainmentResult | None = None
    if proposal is not None and schema is not None:
        containment_result = contain(proposal, schema, baseline=baseline)
        containment_finding = finding_from_containment(
            containment_result,
            document_sha256=digest,
            cue_id=cue.cue_id if cue else "",
            observed_at=observed_at,
        )
        if containment_finding is not None:
            findings.append(containment_finding)
        if containment_result.contained:
            return IntakeVerdict(
                outcome=containment_result.outcome,
                layer=containment_result.layer,
                findings=tuple(findings),
                capability=capability_verdict,
                screen=screen_result,
                containment=containment_result,
                anchors=None,
                sentinel=tagged.sentinel,
                tag_suffix=tagged.tag_suffix,
            )

    anchor_verdict: AnchorVerdict | None = None
    if cue is not None and extractor is not None:
        anchor_verdict = verify_anchors(cue, document.text, extractor)
        anchor_finding = finding_from_anchor_verdict(
            anchor_verdict,
            document_sha256=digest,
            cue_id=cue.cue_id,
            observed_at=observed_at,
        )
        if anchor_finding is not None:
            findings.append(anchor_finding)
        if anchor_verdict.rejected:
            return IntakeVerdict(
                outcome=anchor_verdict.outcome,
                layer=anchor_verdict.layer,
                findings=tuple(findings),
                capability=capability_verdict,
                screen=screen_result,
                containment=containment_result,
                anchors=anchor_verdict,
                sentinel=tagged.sentinel,
                tag_suffix=tagged.tag_suffix,
            )

    outcome = (
        containment_result.outcome
        if containment_result is not None and containment_result.outcome is not Outcome.CLEAN
        else screen_result.outcome
    )
    return IntakeVerdict(
        # The layer is looked up from the outcome rather than hard-coded, so a
        # FLAGGED_OBFUSCATION that survived a clean containment is still attributed to
        # layer 2, which is where it was actually decided.
        outcome=outcome,
        layer=OUTCOME_LAYER[outcome],
        findings=tuple(findings),
        capability=capability_verdict,
        screen=screen_result,
        containment=containment_result,
        anchors=anchor_verdict,
        sentinel=tagged.sentinel,
        tag_suffix=tagged.tag_suffix,
    )
