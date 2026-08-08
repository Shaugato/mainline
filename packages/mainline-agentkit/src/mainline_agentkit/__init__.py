# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""``mainline-agentkit`` — the whole of MAINLINE's model surface, in one small package.

There is **no agent framework in the Cognition plane** (decision A1). Every MAINLINE
model call is a single-shot, zero-tool, JSON-Schema-constrained Bedrock call issued from
:func:`mainline_agentkit.call.quarantined_call`. Strands and LangGraph were evaluated
and rejected: a framework whose value is the tool loop is worth nothing to a fleet whose
defining security property is that the components touching untrusted text hold **no
tools**, and LangGraph's checkpointer would be a second, weaker record of a legally
significant process — the same objection that rejected Step Functions.

Read these three sentences before using anything here:

* *We claim replayability and arithmetic reproducibility, never reproducibility of model
  output.* The model proposes; the arithmetic decides; both are on the record.
* *Prompt-injection defence does not fix a plausible-but-false narrative in an otherwise
  clean PDF. Content authenticity is out of scope; provenance is in scope.*
* *Inference runs in Australia (``ap-southeast-2``). On the free demo tier the database
  is in Singapore (``aws-ap-southeast-1``), so end-to-end Australian data residency is
  FALSE for that deployment and is never claimed.*

The two things worth knowing about the API surface:

1. :func:`quarantined_call` has no ``tools`` parameter. That absence is the structural
   quarantine, not a convention about how to use it.
2. Nothing here writes to a database. Refusals come back as
   :class:`~mainline_agentkit.errors.ModelRefused` and are turned into a
   ``silence_ledger`` row by the caller, which holds the SQL role. This package holds
   no driver and no credential.
"""

from __future__ import annotations

from .cache import CacheFacts, WarmRegistry, estimate_tokens, place_cache_breakpoint
from .call import (
    SENTINEL_PREFIX,
    FanoutInput,
    UntrustedText,
    Validated,
    build_request,
    new_sentinel,
    quarantined_call,
    warm_then_fanout,
)
from .cassette import CassetteStore, CassetteTransport, Interaction, cassette_key
from .errors import (
    AgentkitError,
    CachePrefixTooSmall,
    CassetteMiss,
    CassettePrefixDrift,
    ColdFanout,
    ConfigurationRefused,
    DeadLettered,
    ForbiddenRequestField,
    ModelRefused,
    ProfileNotPinned,
    ProfileUnknown,
    ResidencyRefused,
    RuntimeAlreadyBooted,
    RuntimeNotBooted,
    RuntimeRefusing,
    SchemaViolation,
    ToolFormDisabled,
    ToolSurfaceConstructed,
    TransportUnavailable,
    TruncatedResponse,
    UnknownStopReason,
    UnsupportedSchema,
    UntrustedTextInSystemPrompt,
    WarmTimeout,
)
from .profiles import (
    ADJUDICATION,
    DISPOSITION_ASSISTANT,
    EXTRACTION,
    NARRATION,
    PROFILES,
    TRIAGE,
    CallProfile,
    Effort,
    Tier,
    describe_fleet,
    get_profile,
)
from .refusal import (
    KNOWN_STOP_REASONS,
    SILENCE_REASONS,
    SILENCE_SOURCES,
    Outcome,
    SilenceRow,
    classify,
    interpret,
    silence_row_for_refusal,
)
from .runtime import (
    IDENTITY_COMPONENT_ORDER,
    INFERENCE_PROFILE_ARN_ENV,
    RESIDENCY_NOTE,
    RUN_RECORD_VERSION,
    AgentkitRuntime,
    ProfilePin,
    RunRecord,
    boot_runtime,
    current_runtime,
    is_serving,
    shutdown_runtime,
)
from .schema import (
    OPTIONAL_STRIPPED_KEYWORDS,
    STRIPPED_KEYWORDS,
    BedrockSchema,
    StrippedConstraint,
    bedrock_schema,
)
from .transport import (
    ANTHROPIC_VERSION,
    AUSTRALIAN_PREFIX,
    BANNED_SAMPLING_KEYS,
    BANNED_TOOL_KEYS,
    AgentkitSettings,
    BedrockTransport,
    ModelRequest,
    ModelResponse,
    ResolvedProfile,
    Transport,
    Usage,
    assert_australian_profile,
    assert_no_sampling_params,
    assert_no_tool_surface,
    resolve_inference_profile,
    select_transport,
)

__version__ = "0.1.0"

# `fallback_toolform` is deliberately NOT imported or re-exported here. It is the AR-1
# format fallback: written, unused, switched off, and reachable only by importing it by
# name with MAINLINE_AR1_FALLBACK=1 set. Re-exporting it from the package root would
# make a capability change look like an import.

__all__ = [
    "ADJUDICATION",
    "ANTHROPIC_VERSION",
    "AUSTRALIAN_PREFIX",
    "BANNED_SAMPLING_KEYS",
    "BANNED_TOOL_KEYS",
    "DISPOSITION_ASSISTANT",
    "EXTRACTION",
    "IDENTITY_COMPONENT_ORDER",
    "INFERENCE_PROFILE_ARN_ENV",
    "KNOWN_STOP_REASONS",
    "NARRATION",
    "OPTIONAL_STRIPPED_KEYWORDS",
    "PROFILES",
    "RESIDENCY_NOTE",
    "RUN_RECORD_VERSION",
    "SENTINEL_PREFIX",
    "SILENCE_REASONS",
    "SILENCE_SOURCES",
    "STRIPPED_KEYWORDS",
    "TRIAGE",
    "AgentkitError",
    "AgentkitRuntime",
    "AgentkitSettings",
    "BedrockSchema",
    "BedrockTransport",
    "CacheFacts",
    "CachePrefixTooSmall",
    "CallProfile",
    "CassetteMiss",
    "CassettePrefixDrift",
    "CassetteStore",
    "CassetteTransport",
    "ColdFanout",
    "ConfigurationRefused",
    "DeadLettered",
    "Effort",
    "FanoutInput",
    "ForbiddenRequestField",
    "Interaction",
    "ModelRefused",
    "ModelRequest",
    "ModelResponse",
    "Outcome",
    "ProfileNotPinned",
    "ProfilePin",
    "ProfileUnknown",
    "ResidencyRefused",
    "ResolvedProfile",
    "RunRecord",
    "RuntimeAlreadyBooted",
    "RuntimeNotBooted",
    "RuntimeRefusing",
    "SchemaViolation",
    "SilenceRow",
    "StrippedConstraint",
    "Tier",
    "ToolFormDisabled",
    "ToolSurfaceConstructed",
    "Transport",
    "TransportUnavailable",
    "TruncatedResponse",
    "UnknownStopReason",
    "UnsupportedSchema",
    "UntrustedText",
    "UntrustedTextInSystemPrompt",
    "Usage",
    "Validated",
    "WarmRegistry",
    "WarmTimeout",
    "__version__",
    "assert_australian_profile",
    "assert_no_sampling_params",
    "assert_no_tool_surface",
    "bedrock_schema",
    "boot_runtime",
    "build_request",
    "cassette_key",
    "classify",
    "current_runtime",
    "describe_fleet",
    "estimate_tokens",
    "get_profile",
    "interpret",
    "is_serving",
    "new_sentinel",
    "place_cache_breakpoint",
    "quarantined_call",
    "resolve_inference_profile",
    "select_transport",
    "shutdown_runtime",
    "silence_row_for_refusal",
    "warm_then_fanout",
]
