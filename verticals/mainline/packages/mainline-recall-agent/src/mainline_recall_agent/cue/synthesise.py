# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The two entry points.  One prompt family, one pipeline, two callers.

``synthesise_event_cue`` writes the document side; ``synthesise_exposure_cue`` writes the
query side.  Everything between the two — the facet definitions, the output schema, the
anchor gazetteer, the span arithmetic, the embedding template — is shared code rather than
shared intent, because "we kept the two sides in sync" is a claim that decays and a shared
call graph is a claim that cannot.

The pipeline, in order, and the order is the design:

1. **Render one canonical source document** and record its sha256.  Offsets computed later
   are offsets into these exact bytes.
2. **Extract the source's anchors.**  Deterministic, no model.
3. **Call the judge** under a strict schema, inside the sentinel-tagged user turn.
4. **Anchor-verify each populated facet.**  A facet naming a tag, setpoint, citation or CAS
   number the source does not contain is dropped *before* anything is built from it, and it
   becomes a human-review finding carrying the offending span hash.
5. **Resolve spans** by exact unique ``find()`` over the survivors.  Fabricated, ambiguous
   or partially overlapping quotes fail the step.
6. **Emit rows** — one per surviving facet per archival level, plus the narrative safety net,
   always.

Refusals and dead letters are **not** exceptions to the caller.  They come back as a
``CueOutcome`` with ``status='silenced'`` and the silence-ledger reason the provider itself
named, because the orchestrator has to write that row and then fall back to channels A+B
client-side: *a precursor the model declined to summarise must still block the merge*
(ARCHITECTURE §8.4).
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any, Final, Literal, Protocol, cast, runtime_checkable
from uuid import UUID

from mainline_recall_agent.providers.base import MAX_INPUT_CHARS
from mainline_recall_agent.providers.errors import (
    DeadLetter,
    ModelRefusal,
    ModelTruncated,
    ProviderError,
    ProviderUnavailable,
)
from mainline_recall_agent.providers.system_blocks import SystemPrefix
from mainline_recall_agent.providers.types import JudgeResult, ResolvedModel, ValidatedModelT

from .anchors import anchor_keys, extract_anchors, span_sha256, verify_anchors
from .models import ActivityPath, ClauseDiff, EventInput, IsolationPlan, PermitInput
from .prompts import (
    PROMPT_VERSION,
    build_event_prefix,
    build_exposure_prefix,
    event_payload,
    exposure_payload,
)
from .schema import (
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
)
from .source_text import SourceDocument, event_source_document, exposure_source_document
from .spans import Span, resolve_spans
from .template import EMBED_TEMPLATE_SHA256, embed_text_for

__all__ = [
    "SILENCEABLE_REASONS",
    "VERBATIM_GEN_MODEL",
    "CueJudge",
    "DetailedCueJudge",
    "synthesise_event_cue",
    "synthesise_exposure_cue",
]

log = logging.getLogger(__name__)

#: ``gen_model`` for the narrative row.  ``mainline.event_cue.gen_model`` is NOT NULL and
#: the narrative facet is *raw text, unchanged* — no model produced it.  Writing the judge's
#: identity there would attribute a verbatim copy to a generator, which is a small lie that
#: would later be read as evidence that the model wrote the narrative.
VERBATIM_GEN_MODEL: Final[str] = "verbatim:no-model"

#: The subset of the closed D10 vocabulary a judge call can produce.  Anything else arriving
#: with a ``silence_reason`` is a provider contract change, and it raises rather than being
#: coerced into a reason that happens to validate.
SILENCEABLE_REASONS: Final[frozenset[str]] = frozenset(
    {"model_refusal", "abstained", "truncated", "unreachable"}
)


@runtime_checkable
class CueJudge(Protocol):
    """The narrow structural view of ``providers.types.JudgeProvider`` this module needs.

    Narrower in one respect: ``system_blocks`` is a :class:`SystemPrefix`, not a bare
    sequence.  ``BedrockClaudeJudge`` already refuses a raw list — a list bypasses the
    stability contract that makes the cache breakpoint real — so requiring the built prefix
    in the type is the same rule expressed where a type checker can see it.  Any
    ``JudgeProvider`` implementation whose parameter is at least this wide satisfies it.
    """

    @property
    def resolved_model(self) -> ResolvedModel: ...

    def judge(
        self,
        system_blocks: SystemPrefix,
        user_payload: dict[str, Any],
        schema: type[ValidatedModelT],
    ) -> ValidatedModelT: ...


@runtime_checkable
class DetailedCueJudge(CueJudge, Protocol):
    """A judge that can also return the request digest and the attempt count.

    Optional by design.  The digest is what ties a cue back to the exact call that produced
    it, so it is recorded when the provider offers it and left ``None`` when it does not —
    rather than being fabricated locally from a request we did not send.
    """

    def judge_detailed(
        self,
        system_blocks: SystemPrefix,
        user_payload: dict[str, Any],
        schema: type[ValidatedModelT],
    ) -> JudgeResult: ...


# --------------------------------------------------------------------------------------
# Internals shared by both sides.
# --------------------------------------------------------------------------------------


def _call_judge(
    judge: CueJudge, prefix: SystemPrefix, payload: dict[str, Any]
) -> tuple[FacetSynthesis, str | None, int]:
    """One judge call.  Returns the synthesis, the request digest if offered, and attempts."""
    if isinstance(judge, DetailedCueJudge):
        detailed = judge.judge_detailed(prefix, payload, FacetSynthesis)
        value = detailed.value
        if not isinstance(value, FacetSynthesis):  # pragma: no cover - the judge validates
            raise ProviderError(
                "judge returned a validated model of the wrong type",
                expected="FacetSynthesis",
                got=type(value).__name__,
            )
        return value, detailed.request_digest, detailed.attempts
    return judge.judge(prefix, payload, FacetSynthesis), None, 1


def _silence_from(exc: ProviderError) -> SilenceRecord:
    reason = exc.silence_reason
    if reason not in SILENCEABLE_REASONS:  # pragma: no cover - guarded at the call site
        raise exc
    digest = exc.context.get("request_digest")
    return SilenceRecord(
        # Narrowed by the membership test above; ``cast`` rather than a type-ignore so the
        # assertion is visible to a reader as well as to the checker.
        reason=cast(SilenceReason, reason),
        detail=str(exc),
        request_digest=str(digest) if isinstance(digest, str) else None,
        exception_type=type(exc).__name__,
    )


def _silenced_outcome(
    *,
    subject_kind: Literal["event", "exposure"],
    subject_id: UUID,
    subject_ref: str,
    document: SourceDocument,
    gen_model: str,
    exc: ProviderError,
) -> CueOutcome:
    silence = _silence_from(exc)
    log.warning(
        "cue synthesis silenced: kind=%s ref=%s reason=%s exception=%s",
        subject_kind,
        subject_ref,
        silence.reason,
        silence.exception_type,
    )
    attempts = len(exc.attempts) if isinstance(exc, DeadLetter) else 0
    return CueOutcome(
        subject_kind=subject_kind,
        subject_id=subject_id,
        subject_ref=subject_ref,
        status="silenced",
        source_sha256=document.sha256,
        prompt_version=PROMPT_VERSION,
        gen_model=gen_model,
        embed_template_sha256=EMBED_TEMPLATE_SHA256,
        silence=silence,
        request_digest=silence.request_digest,
        attempts=attempts,
    )


def _anchor_screen(
    synthesis: FacetSynthesis,
    *,
    document: SourceDocument,
    subject_kind: Literal["event", "exposure"],
    subject_id: UUID,
    gen_model: str,
) -> tuple[
    dict[str, FacetAnswer],
    list[FacetSilence],
    list[AnchorRejection],
    list[HumanReviewRoute],
]:
    """Layer 4.  Drop any facet naming a particular the source does not contain.

    Runs before span resolution on purpose: a facet we are going to discard should not be
    able to fail the whole step by also carrying an unresolvable quote.
    """
    source_keys = anchor_keys(extract_anchors(document.text))
    kept: dict[str, FacetAnswer] = {}
    silences: list[FacetSilence] = []
    rejections: list[AnchorRejection] = []
    routes: list[HumanReviewRoute] = []

    for facet, answer in synthesis.as_mapping().items():
        if answer.insufficient:
            reason = (answer.insufficient_reason or "").strip()
            silences.append(
                FacetSilence(facet=facet, cause="insufficient_evidence", reason=reason)
            )
            log.info(
                "facet %s reported insufficient evidence for %s: %s", facet, subject_kind, reason
            )
            kept[facet] = answer
            continue

        cue_text = answer.require_text(facet)
        verdict = verify_anchors(cue_text, source_keys)
        if verdict.ok:
            kept[facet] = answer
            continue

        detail_bits = ", ".join(
            f"{anchor.kind} {anchor.raw!r} (normalised {anchor.normalised!r})"
            for anchor in verdict.missing
        )
        detail = (
            f"cue for facet {facet!r} names {detail_bits}, absent from the source "
            f"document's extracted anchor set"
        )
        log.warning("anchor rejection: %s", detail)
        for anchor in verdict.missing:
            rejections.append(
                AnchorRejection.build(facet=facet, anchor=anchor, cue_text=cue_text)
            )
            routes.append(
                HumanReviewRoute(
                    subject_kind=subject_kind,
                    subject_id=subject_id,
                    facet=facet,
                    anchor_kind=anchor.kind,
                    anchor_raw=anchor.raw,
                    span_sha256=span_sha256(cue_text),
                    source_sha256=document.sha256,
                    gen_model=gen_model,
                    prompt_version=PROMPT_VERSION,
                    detail=detail,
                )
            )
        silences.append(FacetSilence(facet=facet, cause="anchor_absent", reason=detail))
        # The rejected text does not survive into the cue.  A caller reading
        # ``outcome.cue.mechanism`` must not be able to reach a fabricated particular, and
        # the finding already carries the anchor and the span hash a reviewer needs.
        kept[facet] = FacetAnswer(
            cue_text=None,
            evidence_quote=None,
            insufficient=True,
            insufficient_reason=(
                f"rejected by anchor verification: {detail_bits}. Routed to human review."
            ),
        )

    return kept, silences, rejections, routes


def _build_rows(
    *,
    facets: Mapping[str, FacetAnswer],
    spans: Mapping[str, Span],
    narrative: NarrativeFacet,
    subject_kind: Literal["event", "exposure"],
    subject_id: UUID,
    site_id: UUID,
    taxonomy_ver: int,
    activity_path: ActivityPath,
    asset_class: str,
    document: SourceDocument,
    gen_model: str,
) -> tuple[CueRow, ...]:
    """One row per (surviving facet x archival level), narrative last and always.

    The fan-out across levels is the Level-Materialised Bond shape (ARCHITECTURE §5.4): each
    level is a distinct C-SPANN prefix and therefore a distinct K-means tree, which is what
    makes *one arm per ancestor* a real search rather than the same tree queried three
    times.  The *bond basis* and the taxonomy induction that decides which nodes are on the
    path are not decided here — this function fans out the path it was handed.
    """
    rendered_path = activity_path.rendered()
    rows: list[CueRow] = []

    def emit(facet: str, cue_text: str, span: Span, model_id: str) -> None:
        embedded = embed_text_for(
            activity_path=rendered_path,
            asset_class=asset_class,
            facet=facet,
            cue_text=cue_text,
        )
        over = len(embedded) > MAX_INPUT_CHARS
        reason = (
            f"embedding input is {len(embedded)} characters, over the provider bound of "
            f"{MAX_INPUT_CHARS}; the row is still written and still reachable through the "
            "lexical channel, but it is not handed to an embedder, because truncating it "
            "would silently change what the index holds"
            if over
            else None
        )
        for node in activity_path.nodes:
            rows.append(
                CueRow(
                    subject_kind=subject_kind,
                    subject_id=subject_id,
                    site_id=site_id,
                    scope_id=node.scope_id,
                    scope_level=node.level,
                    facet=facet,
                    taxonomy_ver=taxonomy_ver,
                    cue_text=cue_text,
                    source_span=(span.start, span.end),
                    source_sha256=document.sha256,
                    is_derived=True,
                    gen_model=model_id,
                    prompt_version=PROMPT_VERSION,
                    activity_path=rendered_path,
                    asset_class=asset_class,
                    embed_text=embedded,
                    embeddable=not over,
                    not_embeddable_reason=reason,
                )
            )

    for facet in SYNTHESISED_FACETS:
        answer = facets[facet]
        if answer.insufficient:
            continue
        emit(facet, answer.require_text(facet), spans[facet], gen_model)

    emit("narrative", narrative.text, narrative.span, VERBATIM_GEN_MODEL)
    return tuple(rows)


def _synthesise(
    *,
    subject_kind: Literal["event", "exposure"],
    subject_id: UUID,
    subject_ref: str,
    site_id: UUID,
    taxonomy_ver: int,
    document: SourceDocument,
    prefix: SystemPrefix,
    payload: dict[str, Any],
    activity_path: ActivityPath,
    asset_class: str,
    judge: CueJudge,
) -> CueOutcome:
    """The shared pipeline.  Both entry points differ only in what they hand it."""
    gen_model = judge.resolved_model.profile_id

    try:
        synthesis, request_digest, attempts = _call_judge(judge, prefix, payload)
    except (ModelRefusal, ModelTruncated, DeadLetter, ProviderUnavailable) as exc:
        return _silenced_outcome(
            subject_kind=subject_kind,
            subject_id=subject_id,
            subject_ref=subject_ref,
            document=document,
            gen_model=gen_model,
            exc=exc,
        )
    except ProviderError as exc:
        # A provider failure with no silence reason is a defect in our code or our fixtures,
        # not a fact about the corpus, and it must crash rather than become a ledger row
        # that says the corpus was quiet.
        if exc.silence_reason is None:
            raise
        return _silenced_outcome(  # pragma: no cover - reached only if providers add a reason
            subject_kind=subject_kind,
            subject_id=subject_id,
            subject_ref=subject_ref,
            document=document,
            gen_model=gen_model,
            exc=exc,
        )

    facets, silences, rejections, routes = _anchor_screen(
        synthesis,
        document=document,
        subject_kind=subject_kind,
        subject_id=subject_id,
        gen_model=gen_model,
    )

    quotes = {
        facet: answer.require_quote(facet)
        for facet, answer in facets.items()
        if not answer.insufficient
    }
    spans = resolve_spans(document.text, quotes)

    narrative = NarrativeFacet(
        text=document.narrative,
        span=Span(start=document.narrative_start, end=document.narrative_end),
    )
    cue = RecurrenceConditionCue(
        mechanism=facets["mechanism"],
        precondition=facets["precondition"],
        control_failure=facets["control_failure"],
        recurrence_test=facets["recurrence_test"],
        narrative=narrative,
    )
    rows = _build_rows(
        facets=facets,
        spans=spans,
        narrative=narrative,
        subject_kind=subject_kind,
        subject_id=subject_id,
        site_id=site_id,
        taxonomy_ver=taxonomy_ver,
        activity_path=activity_path,
        asset_class=asset_class,
        document=document,
        gen_model=gen_model,
    )
    return CueOutcome(
        subject_kind=subject_kind,
        subject_id=subject_id,
        subject_ref=subject_ref,
        status="synthesised",
        source_sha256=document.sha256,
        prompt_version=PROMPT_VERSION,
        gen_model=gen_model,
        embed_template_sha256=EMBED_TEMPLATE_SHA256,
        cue=cue,
        rows=rows,
        facet_silences=tuple(silences),
        rejections=tuple(rejections),
        review_routes=tuple(routes),
        request_digest=request_digest,
        attempts=attempts,
    )


# --------------------------------------------------------------------------------------
# The two entry points.
# --------------------------------------------------------------------------------------


def synthesise_event_cue(
    event: EventInput,
    activity_path: ActivityPath,
    asset_class: str,
    *,
    judge: CueJudge,
) -> CueOutcome:
    """The document side: one appraised record becomes up to five facets.

    ``judge`` is injected rather than constructed.  This module never touches Bedrock, never
    reads an environment variable and never resolves an inference profile — the provider
    layer owns all three, which is what lets the whole cue pipeline run on cassettes with no
    AWS account (recall.md D5).
    """
    document = event_source_document(event)
    return _synthesise(
        subject_kind="event",
        subject_id=event.event_id,
        subject_ref=event.subject_ref,
        site_id=event.site_id,
        taxonomy_ver=event.taxonomy_ver,
        document=document,
        prefix=build_event_prefix(),
        payload=event_payload(
            document, activity_path=activity_path.rendered(), asset_class=asset_class
        ),
        activity_path=activity_path,
        asset_class=asset_class,
        judge=judge,
    )


def synthesise_exposure_cue(
    permit: PermitInput,
    isolation_plan: IsolationPlan,
    clause_diff: ClauseDiff,
    *,
    judge: CueJudge,
) -> CueOutcome:
    """The query side: one permit becomes the same five facets, from three inputs.

    Structurally identical output to :func:`synthesise_event_cue` — same schema, same
    template, same anchor screen, same span arithmetic — because a query that is not the
    same kind of object as the documents is a query that retrieves by genre.
    """
    document = exposure_source_document(permit, isolation_plan, clause_diff)
    return _synthesise(
        subject_kind="exposure",
        subject_id=permit.permit_id,
        subject_ref=permit.subject_ref,
        site_id=permit.site_id,
        taxonomy_ver=permit.taxonomy_ver,
        document=document,
        prefix=build_exposure_prefix(),
        payload=exposure_payload(
            document,
            activity_path=permit.activity_path.rendered(),
            asset_class=permit.asset_class,
        ),
        activity_path=permit.activity_path,
        asset_class=permit.asset_class,
        judge=judge,
    )
