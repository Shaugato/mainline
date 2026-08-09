# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""MAINLINE quarantine — the six-layer prompt-injection posture as executable controls.

ARCHITECTURE.md 8.4 states the posture as six layers in firing order. This package is
those layers, in code, with a hostile corpus under ``tests/security/injection/`` that
asserts a **named** outcome for each of forty-plus documents rather than "an exception
was raised".

===== ==================================== ==============================================
Layer Control                              Where it lives
===== ==================================== ==============================================
1     structural quarantine                the call shape in ``mainline_agentkit.call``,
                                           proved by the repo-wide AST scan
2     delimiting, datamarking, guardrail   :mod:`~mainline_quarantine.sentinel`,
                                           :mod:`~mainline_quarantine.guardrail`,
                                           :mod:`~mainline_quarantine.screen`
3     output-schema containment            :mod:`~mainline_quarantine.containment`
4     semantic anchoring                   :mod:`~mainline_quarantine.anchoring`
5     capability starvation                :mod:`~mainline_quarantine.capability`
6     the injection is evidence            :mod:`~mainline_quarantine.finding`
===== ==================================== ==============================================

:func:`~mainline_quarantine.pipeline.intake` runs them in the order they fire.

**What none of this fixes: a plausible-but-false narrative in an otherwise clean PDF.
Content authenticity is out of scope; provenance is in scope.** That sentence is in
ARCHITECTURE.md 8.4, in the domain plan's "what this domain does not claim", in the
corpus README, and here, because it is the one limitation a reader will otherwise assume
we have not thought about.

**No dependency, on purpose.** The import graph of this package is standard library only.
The three third-party imports that exist - ``boto3`` for the live guardrail, ``yaml`` for
the fleet register, ``mainline_domain`` for ANCHORLOCK - are all inside functions and all
optional. The component that reads the attacker's bytes holds nothing.
"""

from __future__ import annotations

from .anchoring import (
    CHECKED_CLASSES,
    Anchor,
    AnchorExtractor,
    AnchorRejection,
    AnchorVerdict,
    Cue,
    DomainAnchorExtractor,
    domain_extractor,
    verify_anchors,
)
from .capability import (
    GATE_WRITING_ROLES,
    AgentGrant,
    CapabilityVerdict,
    FleetRegister,
    require_capability,
)
from .classes import FIRING_ORDER, OUTCOME_LAYER, AttackClass, Layer, Outcome
from .containment import (
    GATE_ARMING_FIELDS,
    ContainmentResult,
    Violation,
    assert_contained_schema,
    contain,
)
from .errors import (
    AnchorExtractorUnavailable,
    CapabilityRefused,
    GateFieldInSchema,
    GuardrailConfigInvalid,
    GuardrailResidencyRefused,
    GuardrailUnavailable,
    QuarantineError,
    SentinelCollision,
    UnknownAgent,
    UntrustedSpanNotTagged,
)
from .finding import (
    ROUTE_HUMAN_REVIEW,
    DocumentIntakeFinding,
    assert_never_dropped,
    finding_from_anchor_verdict,
    finding_from_capability,
    finding_from_containment,
    finding_from_screen,
)
from .gazetteer import GazetteerAnchorExtractor
from .guardrail import (
    BedrockGuardrailScreen,
    GuardrailDocument,
    default_guardrail_path,
    guardrail_intervened,
    load_guardrail_document,
    validate_guardrail_document,
)
from .normalise import Unmasked, span_sha256, unmask
from .pipeline import IntakeVerdict, ProcessCapability, UntrustedDocument, intake
from .screen import DETECTORS, Detector, LocalPromptAttackScreen, PromptAttackScreen, ScreenResult
from .sentinel import GUARD_TAG_PREFIX, SENTINEL_PREFIX, TaggedSpan, wrap_untrusted

__all__ = [
    "CHECKED_CLASSES",
    "DETECTORS",
    "FIRING_ORDER",
    "GATE_ARMING_FIELDS",
    "GATE_WRITING_ROLES",
    "GUARD_TAG_PREFIX",
    "OUTCOME_LAYER",
    "ROUTE_HUMAN_REVIEW",
    "SENTINEL_PREFIX",
    "AgentGrant",
    "Anchor",
    "AnchorExtractor",
    "AnchorExtractorUnavailable",
    "AnchorRejection",
    "AnchorVerdict",
    "AttackClass",
    "BedrockGuardrailScreen",
    "CapabilityRefused",
    "CapabilityVerdict",
    "ContainmentResult",
    "Cue",
    "Detector",
    "DocumentIntakeFinding",
    "DomainAnchorExtractor",
    "FleetRegister",
    "GateFieldInSchema",
    "GazetteerAnchorExtractor",
    "GuardrailConfigInvalid",
    "GuardrailDocument",
    "GuardrailResidencyRefused",
    "GuardrailUnavailable",
    "IntakeVerdict",
    "Layer",
    "LocalPromptAttackScreen",
    "Outcome",
    "ProcessCapability",
    "PromptAttackScreen",
    "QuarantineError",
    "ScreenResult",
    "SentinelCollision",
    "TaggedSpan",
    "UnknownAgent",
    "Unmasked",
    "UntrustedDocument",
    "UntrustedSpanNotTagged",
    "Violation",
    "assert_contained_schema",
    "assert_never_dropped",
    "contain",
    "default_guardrail_path",
    "domain_extractor",
    "finding_from_anchor_verdict",
    "finding_from_capability",
    "finding_from_containment",
    "finding_from_screen",
    "guardrail_intervened",
    "intake",
    "load_guardrail_document",
    "require_capability",
    "span_sha256",
    "unmask",
    "validate_guardrail_document",
    "verify_anchors",
    "wrap_untrusted",
]
