# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""Recurrence-Condition Cues — the symmetric, write-time genre bridge.

Embedding the narrative is the default and it is wrong.  Narratives are dominated by names,
shift times, weather, injuries and investigator prose style, so cosine similarity retrieves
*documents written the same way* rather than *hazards that can recur* — and a permit is a
form, a different genre entirely.  Query/document asymmetry is the core failure mode of
retrieval in this domain (ARCHITECTURE §6.2, ``research/05-architecture/diachronic-recall.md``
§4).

The fix is symmetric and it happens at write time.  Both sides emit the same four facets —
``mechanism``, ``precondition``, ``control_failure``, ``recurrence_test`` — under one
byte-identical definitions block, plus ``narrative`` as a raw-text safety net.  The event
side derives them from an appraised record; the permit side derives them from the scope of
work, the isolation plan, and the diff of the clauses being waived or weakened.  Query and
document then share a genre, and cosine between them means something.

Four properties this package enforces rather than intends:

**Per-facet insufficiency.**  Each of the four written facets carries its own escape.  An
insufficient facet produces *no cue row* and a logged reason — never a placeholder string,
because a cue that exists and says nothing is still a point in the index and it will still
be retrieved.

**Anchor verification** (§8.4 layer 4).  Equipment tags, SI-normalised setpoints, regulatory
citations and CAS numbers named by a cue must appear in its source.  Pure regex and
gazetteer, no model.  A cue that fails is rejected *before insert* and routed to human review
with the offending span hash.

**Offsets we computed.**  ``source_span`` comes from an exact, unique ``find()`` of a
verbatim quote into the canonical source text.  A model-reported offset is indistinguishable
from a guessed one, so no model-reported offset is ever accepted.

**One template, one digest.**  ``EMBED_TEMPLATE_SHA256`` covers the embedding template and
the facet-definitions block together; callers pin it into ``recall_policy`` and a golden test
makes drift a CI failure.

Entry points: :func:`~.synthesise.synthesise_event_cue` and
:func:`~.synthesise.synthesise_exposure_cue`.  Both take an injected judge from
``..providers``; nothing here calls Bedrock or reads an environment variable.
"""

from __future__ import annotations

from .anchors import (
    ANCHOR_KINDS,
    UNIT_GAZETTEER,
    Anchor,
    AnchorKind,
    AnchorVerdict,
    anchor_keys,
    extract_anchors,
    span_sha256,
    verify_anchors,
)
from .errors import (
    AnchorGazetteerError,
    CueError,
    FacetContract,
    SourceDocumentError,
    SpanAmbiguous,
    SpanOverlap,
    SpanUnresolvable,
)
from .models import (
    ActivityNode,
    ActivityPath,
    ClauseDiff,
    ClauseDiffEntry,
    ControlFailureHint,
    EventInput,
    IsolationPlan,
    IsolationPoint,
    PermitInput,
)
from .prompts import (
    EVENT_EXAMPLES,
    EVENT_RUBRIC,
    EXPOSURE_EXAMPLES,
    EXPOSURE_RUBRIC,
    FACET_DEFINITIONS,
    PROMPT_VERSION,
    build_event_prefix,
    build_exposure_prefix,
    event_payload,
    exposure_payload,
)
from .schema import (
    FACETS,
    MAX_FACET_TOKENS,
    MIN_FACET_CHARS,
    SYNTHESISED_FACETS,
    AnchorRejection,
    CueOutcome,
    CueRow,
    FacetAnswer,
    FacetSilence,
    FacetSynthesis,
    HumanReviewRoute,
    NarrativeFacet,
    RecurrenceConditionCue,
    SilenceReason,
    SilenceRecord,
    approx_token_count,
)
from .source_text import (
    SourceDocument,
    canonicalise,
    event_source_document,
    exposure_source_document,
)
from .spans import MAX_QUOTE_CHARS, MIN_QUOTE_CHARS, Span, locate_quote, resolve_spans
from .synthesise import (
    SILENCEABLE_REASONS,
    VERBATIM_GEN_MODEL,
    CueJudge,
    DetailedCueJudge,
    synthesise_event_cue,
    synthesise_exposure_cue,
)
from .template import (
    EMBED_TEMPLATE,
    EMBED_TEMPLATE_DIGEST_INPUT,
    EMBED_TEMPLATE_SHA256,
    TEMPLATE_DIGEST_VERSION,
    embed_text_for,
    policy_pin,
)

__all__ = [
    "ANCHOR_KINDS",
    "EMBED_TEMPLATE",
    "EMBED_TEMPLATE_DIGEST_INPUT",
    "EMBED_TEMPLATE_SHA256",
    "EVENT_EXAMPLES",
    "EVENT_RUBRIC",
    "EXPOSURE_EXAMPLES",
    "EXPOSURE_RUBRIC",
    "FACETS",
    "FACET_DEFINITIONS",
    "MAX_FACET_TOKENS",
    "MAX_QUOTE_CHARS",
    "MIN_FACET_CHARS",
    "MIN_QUOTE_CHARS",
    "PROMPT_VERSION",
    "SILENCEABLE_REASONS",
    "SYNTHESISED_FACETS",
    "TEMPLATE_DIGEST_VERSION",
    "UNIT_GAZETTEER",
    "VERBATIM_GEN_MODEL",
    "ActivityNode",
    "ActivityPath",
    "Anchor",
    "AnchorGazetteerError",
    "AnchorKind",
    "AnchorRejection",
    "AnchorVerdict",
    "ClauseDiff",
    "ClauseDiffEntry",
    "ControlFailureHint",
    "CueError",
    "CueJudge",
    "CueOutcome",
    "CueRow",
    "DetailedCueJudge",
    "EventInput",
    "FacetAnswer",
    "FacetContract",
    "FacetSilence",
    "FacetSynthesis",
    "HumanReviewRoute",
    "IsolationPlan",
    "IsolationPoint",
    "NarrativeFacet",
    "PermitInput",
    "RecurrenceConditionCue",
    "SilenceReason",
    "SilenceRecord",
    "SourceDocument",
    "SourceDocumentError",
    "Span",
    "SpanAmbiguous",
    "SpanOverlap",
    "SpanUnresolvable",
    "anchor_keys",
    "approx_token_count",
    "build_event_prefix",
    "build_exposure_prefix",
    "canonicalise",
    "embed_text_for",
    "event_payload",
    "event_source_document",
    "exposure_payload",
    "exposure_source_document",
    "extract_anchors",
    "locate_quote",
    "policy_pin",
    "resolve_spans",
    "span_sha256",
    "synthesise_event_cue",
    "synthesise_exposure_cue",
    "verify_anchors",
]
