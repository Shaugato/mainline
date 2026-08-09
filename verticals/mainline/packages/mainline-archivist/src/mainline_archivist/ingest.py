# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The Archivist's run over one document, with the model call in the middle of the posture.

ARCHITECTURE.md §8.4 row 1 gives this agent two model calls — triage, then extraction, both
at ``effort: low`` — and one abstention: **severity comes from a coded field, a regulator
classification, or a signed human.** Everything in this module is arranged around making
that abstention structural rather than intentional.

.. rubric:: The order the layers actually fire

``mainline_quarantine.pipeline.intake`` evaluates a *supplied* proposal: it is the
pessimistic one-shot evaluator the hostile corpus is written against, and it takes the
payload a fully compromised model would return. A live agent cannot use it that way,
because it has to make the call in the middle::

    L5  capability starvation   before a byte is read
    L2  delimit, datamark, screen
        ── the two quarantined_call()s happen HERE ──
    L3  output-schema containment  over what came back
    L4  semantic anchoring         over what came back
    L6  every non-clean verdict becomes a finding

So this module calls the layers directly, in that order, and records the sequence it took
in :attr:`IngestOutcome.layers_fired`. ``tests/unit/archivist/test_ingest.py`` asserts that
sequence against ``mainline_quarantine.FIRING_ORDER`` rather than against a literal, so a
change to the posture's order fails here instead of drifting.

.. rubric:: What the model is allowed to decide

Nothing that reaches a gate-visible column.

* **Route** — triage returns one of four pipelines. The coded ``kind`` wins every time;
  a disagreement is recorded as a :class:`RouteDisagreement` and carried in the
  provenance, because "the machine read this as a procedure and the buyer's system coded
  it as an incident" is worth a reviewer's attention and is not worth a veto.
* **Quantities and anchors** — extraction's output is the *second* reading. It is contained
  (L3) and anchor-checked (L4) before it is looked at, and every quote it returns is
  re-located in the source by exact string search, because we never trust a model-reported
  offset.
* **Severity** — a model reading arrives only if the caller supplies one, is always a
  ``potential``, and is capped at :data:`~mainline_archivist.appraise.MODEL_GATE_CEILING`.
  The cap produces a ``silence_ledger`` row rather than a silence.

.. rubric:: Refusal is silence, and silence is a row

Decision A8. Both calls may be declined — the corpus is cyanide leaching, H₂S and
confined-space chemistry, so false-positive refusals are expected. A refusal here does
**not** stop the ingest: the deterministic channel supplies the route, the event is still
written, and the refusal becomes a ``SilenceRow`` the caller writes through a role that
holds the grant. *A precursor the model declined to summarise must still block the merge.*
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Final

from mainline_agentkit.errors import DeadLettered, ModelRefused
from mainline_agentkit.profiles import EXTRACTION, TRIAGE
from mainline_quarantine import (
    Cue,
    FleetRegister,
    Layer,
    Outcome,
    contain,
    finding_from_anchor_verdict,
    finding_from_capability,
    finding_from_containment,
    finding_from_screen,
    require_capability,
    verify_anchors,
    wrap_untrusted,
)

from .appraise import SeverityClaim, appraise, downgrade_silence_rows
from .emit import EventDraft, insert_event, statements_for_findings
from .errors import DocumentNotAdmitted, EventKindNotCoded
from .source import custody_preamble
from .verbatim import VerbatimSpan

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from datetime import datetime

    from mainline_agentkit.call import UntrustedText, Validated
    from mainline_agentkit.runtime import AgentkitRuntime
    from mainline_quarantine import (
        AnchorExtractor,
        AnchorVerdict,
        CapabilityVerdict,
        ContainmentResult,
        DocumentIntakeFinding,
        PromptAttackScreen,
        ScreenResult,
    )

    from .appraise import SeverityAppraisal
    from .emit import Statement
    from .source import ExtractedText, FetchedObject

__all__ = [
    "ARCHIVIST_AGENT",
    "ROUTE_FOR_KIND",
    "SILENCE_SOURCE",
    "CodedFacts",
    "IngestOutcome",
    "ModelSeverityReading",
    "RouteDisagreement",
    "ingest_document",
    "require_admitted",
]

#: The agent name as the fleet register spells it.
ARCHIVIST_AGENT: Final[str] = "archivist"

#: ``mainline_meas.silence_ledger.source`` for anything this agent declines to record.
#: ``fleet_appraisal`` is the §5.7 vocabulary term for a Cognition-plane reading that did
#: not happen; ``severity_downgrade`` (used by :mod:`mainline_archivist.appraise`) is the
#: term for one that happened and was capped. They are different facts and they get
#: different rows.
SILENCE_SOURCE: Final[str] = "fleet_appraisal"

#: The triage route each coded ``event.kind`` is *expected* to produce. Advisory only:
#: nothing branches on it, and it exists so a disagreement can be named. A regulator notice
#: and a CAPA are both documents about something that happened; an OEM alert is a document
#: about how work is to be done, which is why it maps to ``procedure``.
ROUTE_FOR_KIND: Final[Mapping[str, str]] = {
    "incident": "incident",
    "near_miss": "incident",
    "audit_finding": "incident",
    "capa": "incident",
    "regulator_notice": "incident",
    "oem_alert": "procedure",
}

#: Bounded so one pathological document cannot spend the extraction budget.
_MAX_ANCHOR_TEXT_CHARS: Final[int] = 20_000


@dataclass(frozen=True, slots=True)
class ModelSeverityReading:
    """A severity a model proposed, with the call that produced it.

    The quote is located in the source by exact string search here; the reading carries
    characters, never offsets, for the same reason the extraction profile does.
    """

    value: int
    quote: str
    profile_id: str
    prompt_version: str
    output_sha256: str


@dataclass(frozen=True, slots=True)
class CodedFacts:
    """Everything about this event that did **not** come from a model.

    Every field here is either a coded value out of the buyer's own system, a statutory
    classification, or a span located in the document. There is no field a model writes,
    and that is the whole shape of the type: an ``EventDraft`` cannot be assembled without
    one of these, so there is no path from a model's output to ``mainline.event`` that does
    not pass through a coded fact.

    Attributes:
        kind: the coded ``event.kind``. Required, and not derivable from a triage route.
        title_quote: the document's own title line, located in the extracted text.
        narrative_span: offsets of the passage that *is* the narrative. Offsets rather
            than text, because these come from the deterministic pass, not from a model.
        claims: coded, regulator and signed-human severity claims.
    """

    site_id: str
    kind: str
    occurred_at: datetime
    title_quote: str
    narrative_span: tuple[int, int]
    claims: tuple[SeverityClaim, ...]
    external_ref: str | None = None
    source_doc_id: str | None = None
    cluster_id: str | None = None
    consequence_proxy: Mapping[str, Any] | None = None
    canon_version: int = 1
    #: Allow NFKC/whitespace folding when locating the title. Off by default: a caller who
    #: accepts the widening has written it down.
    fold_title: bool = False

    def __post_init__(self) -> None:
        """Refuse coded facts that could not describe an event.

        Raises:
            EventKindNotCoded: no kind.
            ValueError: no title quote, or an impossible narrative span.
        """
        if not self.kind:
            raise EventKindNotCoded(
                "CodedFacts.kind is empty. A triage route is a pipeline decision and "
                "event.kind is a closed vocabulary; the Archivist records a disagreement "
                "between them and resolves one only in the coded field's favour."
            )
        if not self.title_quote.strip():
            raise ValueError(
                "title_quote is empty; CHECK title_stated refuses an empty title and the "
                "Archivist has no other source for one"
            )
        start, end = self.narrative_span
        if start < 0 or end <= start:
            raise ValueError(f"narrative_span {self.narrative_span} is not a forward range")


@dataclass(frozen=True, slots=True)
class RouteDisagreement:
    """The model routed the document one way and the coded field says another.

    Deliberately **not** a ``document_intake_finding``. That table's vocabulary is the
    injection posture's — layers, attack classes, outcomes — and a routing disagreement is
    not an attack. Recording it there would inflate the attack record with ordinary
    disagreement, which is the fastest way to make an attack record unreadable. It rides
    in the provenance instead, where a reviewer looking at *this ingest* will see it.
    """

    coded_kind: str
    expected_route: str
    model_route: str
    model_abstained: bool
    basis_quote: str

    def to_mapping(self) -> dict[str, Any]:
        """Ledger-shaped form."""
        return {
            "coded_kind": self.coded_kind,
            "expected_route": self.expected_route,
            "model_route": self.model_route,
            "model_abstained": self.model_abstained,
            "basis_quote": self.basis_quote,
            "resolved_by": "coded_field",
        }


@dataclass(frozen=True, slots=True)
class IngestOutcome:
    """Everything one document produced: what was written, what was refused, what was silent.

    Attributes:
        admitted: whether the posture allowed an extraction to be inserted at all.
        outcome: the quarantine outcome that decided it.
        layers_fired: the layers that actually ran, in the order they ran.
        statements: the INSERTs, in the order they must run — the event first, then the
            findings, because a finding about an event that is not there is harder to read.
        findings: every ``DocumentIntakeFinding`` the layers produced.
        silences: ``SilenceRow`` objects for every model refusal and every capped rating.
            **This package cannot write them**; ``agent_ingestor`` holds no INSERT on
            ``mainline_meas.silence_ledger``.
        provenance: the §8.2 replayability record for each model call, plus the custody
            preamble and the routing disagreement.
    """

    admitted: bool
    outcome: Outcome
    layers_fired: tuple[Layer, ...]
    statements: tuple[Statement, ...]
    findings: tuple[DocumentIntakeFinding, ...]
    silences: tuple[Any, ...]
    provenance: dict[str, Any]
    appraisal: SeverityAppraisal | None = None
    triage: Validated[Any] | None = None
    extraction: Validated[Any] | None = None
    disagreement: RouteDisagreement | None = None
    capability: CapabilityVerdict | None = None
    screen: ScreenResult | None = None
    containment: ContainmentResult | None = None
    anchors: AnchorVerdict | None = None
    refusals: tuple[str, ...] = field(default_factory=tuple)

    @property
    def wrote_event(self) -> bool:
        """Whether an ``INSERT INTO mainline.event`` is among the statements."""
        return any(statement.table == "mainline.event" for statement in self.statements)


def ingest_document(  # noqa: PLR0912, PLR0915 - the posture is a sequence; splitting it hides the order
    *,
    runtime: AgentkitRuntime,
    obj: FetchedObject,
    extracted: ExtractedText,
    coded: CodedFacts,
    screen: PromptAttackScreen,
    register: FleetRegister,
    sql_roles: Sequence[str] = ("agent_ingestor",),
    tools: Sequence[str] = (),
    iam_role_arn: str = "",
    anchor_extractor: AnchorExtractor | None = None,
    model_severity: ModelSeverityReading | None = None,
    observed_at: datetime | None = None,
) -> IngestOutcome:
    """Run the Archivist over one fetched document and return everything it produced.

    Args:
        runtime: a booted agentkit runtime. Supplies the pinned inference-profile ARN and
            the replayability record; the Archivist never chooses a model id.
        obj: the fetched bytes, with the digest computed from them.
        extracted: the text, and which extractor produced it.
        coded: every fact that did not come from a model.
        screen: the layer-2 screen — the offline heuristic or the live Guardrails screen.
        register: the fleet register, for layer 5.
        sql_roles: the roles this process actually holds.
        tools: the tools this process actually holds. The register declares an empty list
            for the Archivist, so anything here is a refusal.
        iam_role_arn: the execution role, for the ``agent_identity`` components.
        anchor_extractor: ANCHORLOCK or the committed-gazetteer fallback. ``None`` skips
            layer 4, which is appropriate only when the caller ran it itself.
        model_severity: a severity some model proposed. Capped, never admitted.
        observed_at: fixed instant, so a test's findings are byte-stable.

    Returns:
        The outcome. A refused document returns with ``admitted=False``, no event
        statement, and every finding the layers produced — never an exception, because a
        refused document is an ordinary Tuesday and its findings are the product.

    Raises:
        SpanNotVerbatim: a coded span does not index the extracted text. This is a caller
            error about *trusted* input, not a document refusal, so it is not swallowed.
    """
    text = extracted.text
    findings: list[DocumentIntakeFinding] = []
    layers: list[Layer] = []
    silences: list[Any] = []
    refusals: list[str] = []
    provenance: dict[str, Any] = {
        "agent": ARCHIVIST_AGENT,
        "custody_preamble": custody_preamble(obj, extracted),
        "calls": {},
    }

    # ── L5, before a byte of the document is read ───────────────────────────────────
    layers.append(Layer.L5_CAPABILITY_STARVATION)
    capability = require_capability(
        ARCHIVIST_AGENT, register, sql_roles=sql_roles, tools=tools, raising=False
    )
    capability_finding = finding_from_capability(
        capability, document_sha256=obj.sha256, observed_at=observed_at
    )
    if capability_finding is not None:
        findings.append(capability_finding)
        return IngestOutcome(
            admitted=False,
            outcome=capability.outcome,
            layers_fired=tuple(layers),
            statements=statements_for_findings([f.to_row() for f in findings]),
            findings=tuple(findings),
            silences=(),
            provenance=provenance,
            capability=capability,
            refusals=tuple(capability.refusals),
        )

    # ── L2, delimiting and the screen ───────────────────────────────────────────────
    layers.append(Layer.L2_DELIMIT_AND_DATAMARK)
    # Not caught and converted: a document carrying our own delimiters is refused before it
    # is screened, and a SentinelCollision propagates to the caller.
    wrap_untrusted(text)
    screen_result = screen.screen(text)
    screen_finding = finding_from_screen(
        screen_result, document_sha256=obj.sha256, observed_at=observed_at
    )
    if screen_finding is not None:
        findings.append(screen_finding)
    if screen_result.blocked:
        return IngestOutcome(
            admitted=False,
            outcome=screen_result.outcome,
            layers_fired=tuple(layers),
            statements=statements_for_findings([f.to_row() for f in findings]),
            findings=tuple(findings),
            silences=(),
            provenance=provenance,
            capability=capability,
            screen=screen_result,
            refusals=(f"layer 2 blocked: {screen_result.detector}",),
        )

    untrusted = _untrusted_text(text, obj)

    # ── the two calls ───────────────────────────────────────────────────────────────
    triage_result: Validated[Any] | None = None
    try:
        triage_result = runtime.call(TRIAGE, untrusted, _trusted_context(coded, obj, extracted))
    except ModelRefused as refusal:
        refusals.append(f"triage refused: {refusal.category}")
        silences.append(
            _silence(runtime, refusal, profile_id=TRIAGE.profile_id, coded=coded, obj=obj)
        )
    except DeadLettered as dead:
        refusals.append(f"triage dead-lettered after {dead.attempts} attempts")
    else:
        provenance["calls"]["triage"] = _call_provenance(
            runtime, triage_result, profile_id=TRIAGE.profile_id, iam_role_arn=iam_role_arn
        )

    disagreement = _route_disagreement(coded, triage_result)
    if disagreement is not None:
        provenance["route_disagreement"] = disagreement.to_mapping()

    extraction_result: Validated[Any] | None = None
    containment: ContainmentResult | None = None
    anchors: AnchorVerdict | None = None
    try:
        extraction_result = runtime.call(
            EXTRACTION, untrusted, _trusted_context(coded, obj, extracted)
        )
    except ModelRefused as refusal:
        refusals.append(f"extraction refused: {refusal.category}")
        silences.append(
            _silence(runtime, refusal, profile_id=EXTRACTION.profile_id, coded=coded, obj=obj)
        )
    except DeadLettered as dead:
        refusals.append(f"extraction dead-lettered after {dead.attempts} attempts")
    else:
        provenance["calls"]["extraction"] = _call_provenance(
            runtime,
            extraction_result,
            profile_id=EXTRACTION.profile_id,
            iam_role_arn=iam_role_arn,
        )

    admitted = True
    outcome = Outcome.CLEAN if not screen_finding else screen_result.outcome

    if extraction_result is not None:
        # ── L3, over what came back ─────────────────────────────────────────────────
        layers.append(Layer.L3_OUTPUT_SCHEMA_CONTAINMENT)
        payload = extraction_result.value.model_dump()
        containment = contain(payload, dict(EXTRACTION.schema.schema))
        containment_finding = finding_from_containment(
            containment,
            document_sha256=obj.sha256,
            cue_id=extraction_result.output_sha256,
            observed_at=observed_at,
        )
        if containment_finding is not None:
            findings.append(containment_finding)
        if containment.contained:
            admitted = False
            outcome = containment.outcome
            refusals.append(f"layer 3 contained: {containment.outcome}")
        elif containment.outcome is not Outcome.CLEAN:
            outcome = containment.outcome

        # ── L4, over what came back ─────────────────────────────────────────────────
        if admitted and anchor_extractor is not None:
            layers.append(Layer.L4_SEMANTIC_ANCHORING)
            cue = _cue_from_extraction(payload, extraction_result.output_sha256)
            anchors = verify_anchors(cue, text[:_MAX_ANCHOR_TEXT_CHARS], anchor_extractor)
            anchor_finding = finding_from_anchor_verdict(
                anchors,
                document_sha256=obj.sha256,
                cue_id=cue.cue_id,
                observed_at=observed_at,
            )
            if anchor_finding is not None:
                findings.append(anchor_finding)
            if anchors.rejected:
                admitted = False
                outcome = anchors.outcome
                refusals.append("layer 4 rejected an anchor absent from the source")

    # ── the appraisal, which no model participates in beyond a capped potential ─────
    claims = list(coded.claims)
    if model_severity is not None:
        claims.append(_model_claim(model_severity, text))
    appraisal = appraise(claims)
    silences.extend(
        downgrade_silence_rows(
            appraisal,
            site_id=coded.site_id,
            subject_kind="event",
            subject_id=coded.external_ref or obj.sha256,
        )
    )
    provenance["appraisal"] = appraisal.to_mapping()

    statements: list[Statement] = []
    if admitted:
        statements.append(_event_statement(coded, obj, extracted, appraisal))
    else:
        refusals.append("no event written: the posture refused this document")

    layers.append(Layer.L6_INJECTION_IS_EVIDENCE)
    statements.extend(statements_for_findings([finding.to_row() for finding in findings]))

    return IngestOutcome(
        admitted=admitted,
        outcome=outcome,
        layers_fired=tuple(layers),
        statements=tuple(statements),
        findings=tuple(findings),
        silences=tuple(silences),
        provenance=provenance,
        appraisal=appraisal,
        triage=triage_result,
        extraction=extraction_result,
        disagreement=disagreement,
        capability=capability,
        screen=screen_result,
        containment=containment,
        anchors=anchors,
        refusals=tuple(refusals),
    )


# ── internals ───────────────────────────────────────────────────────────────────────


def _untrusted_text(text: str, obj: FetchedObject) -> UntrustedText:
    """Wrap the extracted text in the type agentkit accepts in exactly one position."""
    from mainline_agentkit.call import UntrustedText as _UntrustedText

    return _UntrustedText(text=text, source_sha256=obj.sha256, media_type=obj.media_type)


def _trusted_context(
    coded: CodedFacts, obj: FetchedObject, extracted: ExtractedText
) -> dict[str, Any]:
    """Build the operator's framing, rendered before the untrusted block.

    Deliberately thin. It carries what the document *is* — where it came from, how it was
    extracted, which site it belongs to — and **not** the coded severity or the coded kind.
    A model that has been told the answer is not a second reading, and the extraction call
    exists to be a second reading.
    """
    return {
        "site_id": coded.site_id,
        "object_key": obj.ref.object_key,
        "version_id": obj.ref.version_id,
        "source_sha256": obj.sha256,
        "media_type": obj.media_type,
        "extractor": extracted.extractor,
        "extracted_chars": len(extracted.text),
        "page_count": extracted.page_count,
    }


def _call_provenance(
    runtime: AgentkitRuntime,
    validated: Validated[Any],
    *,
    profile_id: str,
    iam_role_arn: str,
) -> dict[str, Any]:
    """Merge the call's replayability record with the seven ``agent_identity`` components.

    The digest itself is ``mainline-provenance``'s to compute; §8.2 admits exactly one
    implementation of that formula and this is not it. What travels here are the
    components, in concatenation order.
    """
    record = dict(runtime.provenance(validated))
    record["identity_components"] = runtime.run_record.identity_components(
        agent_name=ARCHIVIST_AGENT,
        sql_role="agent_ingestor",
        iam_role_arn=iam_role_arn,
        profile_id=profile_id,
    )
    return record


def _silence(
    runtime: AgentkitRuntime,
    refusal: ModelRefused,
    *,
    profile_id: str,
    coded: CodedFacts,
    obj: FetchedObject,
) -> Any:
    """Build the ``silence_ledger`` row for a refusal. Decision A8.

    ``severity=0`` because a refusal carries no severity of its own: what the row records
    is that a reading did not happen, and inventing a severity for it would be inventing
    the very thing the model declined to give.
    """
    return runtime.silence_row(
        refusal,
        profile_id=profile_id,
        site_id=coded.site_id,
        source=SILENCE_SOURCE,
        subject_kind="event",
        subject_id=coded.external_ref or obj.sha256,
        severity=0,
        input_sha256=obj.sha256,
    )


def _route_disagreement(
    coded: CodedFacts, triage: Validated[Any] | None
) -> RouteDisagreement | None:
    """Name a disagreement between the coded kind and the model's route, or return None."""
    if triage is None:
        return None
    expected = ROUTE_FOR_KIND.get(coded.kind, "")
    verdict = triage.value
    model_route = str(getattr(verdict, "route", ""))
    abstained = bool(getattr(verdict, "abstained", False))
    if model_route == expected and not abstained:
        return None
    return RouteDisagreement(
        coded_kind=coded.kind,
        expected_route=expected,
        model_route=model_route,
        model_abstained=abstained,
        basis_quote=str(getattr(verdict, "basis_quote", "")),
    )


def _cue_from_extraction(payload: Mapping[str, Any], cue_id: str) -> Cue:
    """Fold the extraction into the two forms layer 4 reads.

    Every free-text field is concatenated, not just ``anchors``: an equipment tag smuggled
    into a ``quote`` is exactly as dangerous as one in the anchor list, and layer 4 exists
    because the model has no way to know which of the two it was told to use.
    """
    declared = tuple(str(item) for item in payload.get("anchors", ()))
    quotes = [str(item.get("quote", "")) for item in payload.get("quantities", ())]
    kinds = [str(item.get("quantity_kind", "")) for item in payload.get("quantities", ())]
    text = "\n".join([*declared, *quotes, *kinds])
    return Cue(cue_id=cue_id, text=text, declared_anchors=declared)


def _model_claim(reading: ModelSeverityReading, text: str) -> SeverityClaim:
    """Turn a model's severity reading into a capped claim, with the quote re-located.

    The offsets are computed here by exact string search. A reading whose quote is not in
    the document is a refusal, not a claim — which is the same rule layer 4 applies to an
    anchor, applied to the only number the model is allowed anywhere near.
    """
    span = VerbatimSpan.locate(text, reading.quote)
    return SeverityClaim.model(
        reading.value,
        profile_id=reading.profile_id,
        prompt_version=reading.prompt_version,
        output_sha256=reading.output_sha256,
        span=span,
    )


def _event_statement(
    coded: CodedFacts,
    obj: FetchedObject,
    extracted: ExtractedText,
    appraisal: SeverityAppraisal,
) -> Statement:
    """Locate the coded spans in the extracted text and build the event INSERT.

    Raises:
        SpanNotVerbatim: the coded title is not in the document, or the narrative span
            falls outside it. Both are caller errors about trusted input.
    """
    text = extracted.text
    locate = VerbatimSpan.locate_normalised if coded.fold_title else VerbatimSpan.locate
    title = locate(text, coded.title_quote)
    narrative = VerbatimSpan.read(text, *coded.narrative_span)
    draft = EventDraft(
        site_id=coded.site_id,
        occurred_at=coded.occurred_at,
        kind=coded.kind,
        title=title,
        narrative=narrative,
        source_object_key=obj.ref.object_key,
        source_sha256=obj.sha256_bytes,
        severity=appraisal,
        canon_version=coded.canon_version,
        external_ref=coded.external_ref,
        source_doc_id=coded.source_doc_id,
        consequence_proxy=coded.consequence_proxy,
        cluster_id=coded.cluster_id,
    )
    return insert_event(draft, source_text=text)


def require_admitted(outcome: IngestOutcome) -> IngestOutcome:
    """Refuse to proceed past a refused document.

    For a caller that wants the refusal to be an exception at its own boundary — a Lambda
    that should dead-letter, say — rather than a branch it might forget to take. The
    findings are still on the outcome the exception names, because a refused document's
    findings are the product.

    Raises:
        DocumentNotAdmitted: the posture refused the document.
    """
    if not outcome.admitted:
        raise DocumentNotAdmitted(
            f"the posture refused this document ({outcome.outcome}) at "
            f"{outcome.layers_fired[-1] if outcome.layers_fired else 'no layer'}; there "
            f"is no event to write, and {len(outcome.findings)} finding(s) are waiting to "
            f"be inserted"
        )
    return outcome
