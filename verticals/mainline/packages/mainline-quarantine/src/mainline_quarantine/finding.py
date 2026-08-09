# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Layer 6: the injection is evidence.

Every other layer produces a refusal. This one produces a **row**, and the difference
matters more than it looks: a blocked document that is dropped teaches nobody anything,
and the customer who is being probed - by a contractor, by a vendor's document template,
by whoever authored the incident PDF - never finds out. SEC-0, the Record Honesty Rule:
*MAINLINE never chooses not to record a fact.*

So:

* every non-clean verdict from layers 2, 3, 4 and 5 becomes a
  :class:`DocumentIntakeFinding`;
* every finding routes to ``human_review``. There is no ``drop`` route, no severity below
  which a finding is discarded, and :func:`assert_never_dropped` is the test hook that
  keeps it that way;
* the finding records the **digest** of the offending span, not the span. An operator
  triaging a queue of these should not have to re-read the attack to act on it, and a
  span reproduced into a second table is a second place the attack text lives. The
  document itself is already in S3 under Object Lock from the custody preamble (8.6), so
  the bytes are recoverable by anyone who needs them, with the access recorded.

**Ownership note.** The DDL for ``mainline.document_intake_finding`` belongs to the data
model domain (11.2 grants ``agent_ingestor`` INSERT on it). :meth:`to_row` is this
package's statement of the payload that table must accept; if the two disagree, the
column list is the one to change and this docstring is the reason why.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Final

from .classes import Layer, Outcome

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from .anchoring import AnchorVerdict
    from .capability import CapabilityVerdict
    from .containment import ContainmentResult
    from .screen import ScreenResult

__all__ = [
    "ROUTE_HUMAN_REVIEW",
    "DocumentIntakeFinding",
    "assert_never_dropped",
    "finding_from_anchor_verdict",
    "finding_from_capability",
    "finding_from_containment",
    "finding_from_screen",
    "utc_now",
]

#: The only route a finding has. Written as a constant so that a future second route is
#: a diff a reviewer sees rather than a string somebody typed at a call site.
ROUTE_HUMAN_REVIEW: Final[str] = "human_review"


def utc_now() -> datetime:
    """Timezone-aware now. A naive datetime in an evidentiary payload is unanswerable."""
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class DocumentIntakeFinding:
    """One recorded refusal, shaped for ``mainline.document_intake_finding``.

    Attributes:
        document_sha256: digest of the source bytes, from the custody preamble (8.6).
            This is the join back to the Object-Locked object, and it is what makes the
            finding evidence rather than an anecdote.
        span_sha256: domain-separated digest of the offending span.
        span_start / span_end: half-open offsets into the extracted text, so a reviewer
            can find the span in the document without it being copied here.
        layer / outcome: which control fired and what it decided, from the shared
            vocabulary in :mod:`mainline_quarantine.classes`.
        detector: the named rule that fired, or the extractor that rejected the anchor.
        attack_class: the corpus class this resembles, when a control could name one.
            ``None`` when it could not - Bedrock reports that it intervened, not which
            shape it saw, and inventing a class there would be inventing evidence.
        detail: one line an operator can act on.
        route: always :data:`ROUTE_HUMAN_REVIEW`.
    """

    document_sha256: str
    observed_at: datetime
    layer: Layer
    outcome: Outcome
    detector: str
    detail: str
    span_sha256: str = ""
    span_start: int = 0
    span_end: int = 0
    attack_class: str | None = None
    cue_id: str = ""
    agent: str = ""
    route: str = ROUTE_HUMAN_REVIEW
    evidence: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        """Refuse a finding that is not evidence: no naive timestamp, no other route."""
        if self.observed_at.tzinfo is None:
            raise ValueError(
                "observed_at must be timezone-aware; a naive datetime in an evidentiary "
                "payload is an unanswerable question in cross-examination"
            )
        if self.route != ROUTE_HUMAN_REVIEW:
            raise ValueError(
                f"route must be {ROUTE_HUMAN_REVIEW!r}; layer 6 has no drop path "
                f"(ARCHITECTURE.md 8.4: the injection is evidence)"
            )

    def to_row(self) -> dict[str, Any]:
        """Return the INSERT payload for ``mainline.document_intake_finding``."""
        return {
            "document_sha256": self.document_sha256,
            "observed_at": self.observed_at.isoformat(),
            "layer": str(self.layer),
            "outcome": str(self.outcome),
            "detector": self.detector,
            "detail": self.detail,
            "span_sha256": self.span_sha256,
            "span_start": self.span_start,
            "span_end": self.span_end,
            "attack_class": self.attack_class,
            "cue_id": self.cue_id,
            "agent": self.agent,
            "route": self.route,
            "evidence": list(self.evidence),
        }


def finding_from_screen(
    result: ScreenResult,
    *,
    document_sha256: str,
    observed_at: datetime | None = None,
) -> DocumentIntakeFinding | None:
    """Build the finding for a layer-2 verdict, or ``None`` when the span was clean."""
    if result.outcome is Outcome.CLEAN:
        return None
    return DocumentIntakeFinding(
        document_sha256=document_sha256,
        observed_at=observed_at or utc_now(),
        layer=result.layer,
        outcome=result.outcome,
        detector=result.detector,
        detail=result.evidence,
        span_sha256=result.span_sha256,
        span_start=result.span[0],
        span_end=result.span[1],
        attack_class=str(result.attack_class) if result.attack_class else None,
        evidence=(f"screen={result.screen}",),
    )


def finding_from_containment(
    result: ContainmentResult,
    *,
    document_sha256: str,
    cue_id: str = "",
    observed_at: datetime | None = None,
) -> DocumentIntakeFinding | None:
    """Build the finding for a layer-3 verdict, or ``None`` when the payload was clean.

    A ``VALUE_ONLY_DISTORTION`` produces a finding too. It is the residual of the whole
    posture, not a pass: the record now contains a value an attacker moved, and the
    person who has to decide whether that matters is a person, not this function.
    """
    if result.outcome is Outcome.CLEAN:
        return None
    detail = (
        f"schema-valid payload differs from the honest reading at "
        f"{len(result.distorted_fields)} field(s)"
        if result.outcome is Outcome.VALUE_ONLY_DISTORTION
        else f"{len(result.violations)} schema violation(s)"
    )
    evidence = tuple(
        f"{violation.kind}:{violation.pointer}: {violation.detail}"
        for violation in result.violations
    ) or tuple(f"distorted:{path}" for path in result.distorted_fields)
    return DocumentIntakeFinding(
        document_sha256=document_sha256,
        observed_at=observed_at or utc_now(),
        layer=result.layer,
        outcome=result.outcome,
        detector="schema.containment",
        detail=detail,
        cue_id=cue_id,
        evidence=evidence,
    )


def finding_from_anchor_verdict(
    verdict: AnchorVerdict,
    *,
    document_sha256: str,
    cue_id: str = "",
    observed_at: datetime | None = None,
) -> DocumentIntakeFinding | None:
    """Build the layer-4 finding, or ``None`` when every anchor was in the source."""
    if verdict.outcome is Outcome.CLEAN:
        return None
    return DocumentIntakeFinding(
        document_sha256=document_sha256,
        observed_at=observed_at or utc_now(),
        layer=verdict.layer,
        outcome=verdict.outcome,
        detector=f"anchors.{verdict.extractor}",
        detail=(
            f"{len(verdict.rejections)} anchor(s) named by the cue are absent from the "
            f"source document"
        ),
        cue_id=cue_id,
        evidence=tuple(rejection.describe() for rejection in verdict.rejections),
    )


def finding_from_capability(
    verdict: CapabilityVerdict,
    *,
    document_sha256: str,
    observed_at: datetime | None = None,
) -> DocumentIntakeFinding | None:
    """Build the layer-5 finding, or ``None`` when the process was starved."""
    if verdict.outcome is Outcome.CLEAN:
        return None
    return DocumentIntakeFinding(
        document_sha256=document_sha256,
        observed_at=observed_at or utc_now(),
        layer=verdict.layer,
        outcome=verdict.outcome,
        detector="capability.starvation",
        detail=f"{verdict.agent} holds capabilities the fleet register does not grant",
        agent=verdict.agent,
        evidence=tuple(verdict.refusals),
    )


def assert_never_dropped(
    findings: Iterable[DocumentIntakeFinding],
    outcomes: Sequence[Outcome],
) -> None:
    """Refuse a run in which a non-clean outcome produced no finding.

    The test hook for layer 6. Its failure message is the sentence it protects: a control
    that refuses a document and writes nothing has turned an attack into silence, and
    silence is the one thing this product is built not to produce.
    """
    recorded = {finding.outcome for finding in findings}
    missing = [
        outcome for outcome in outcomes if outcome is not Outcome.CLEAN and outcome not in recorded
    ]
    if missing:
        raise AssertionError(
            f"outcomes {[str(outcome) for outcome in missing]} produced no "
            f"document_intake_finding. A refusal that writes nothing turns an attack "
            f"into silence (ARCHITECTURE.md 8.4 layer 6)."
        )
