# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The canonical source document — the one text both the model and ``find()`` see.

There is exactly one rule in this module and everything else follows from it:

    **The bytes shown to the model are the bytes offsets are computed against.**

``event_cue.source_span`` is a pair of integers a human will later use to find the words a
cue came from.  If the model is shown a prettified rendering and offsets are computed
against the raw column, every span in the corpus is wrong by an amount nobody can see.  So
the document is canonicalised **once**, its sha256 is recorded, and both the quarantined
user turn and :func:`~.spans.resolve_spans` use that exact string.

Canonicalisation here is deliberately *weaker* than
``providers.base.normalise_text``.  That function collapses every run of whitespace,
newlines included, which is right for an embedding input — line structure is noise in a
vector — and wrong for an offset-bearing document, because the span a supervisor is shown
should still look like the paragraph it came from.  So: NFKC, CRLF/CR to LF, runs of spaces
collapsed, leading and trailing whitespace stripped per line, runs of blank lines collapsed
to one, and nothing else.  Line *structure* survives; ragged indentation from a PDF
extraction does not, because otherwise every offset in the corpus would depend on how the
extractor felt about margins.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .errors import SourceDocumentError
from .models import ClauseDiff, EventInput, IsolationPlan, PermitInput

__all__ = [
    "SourceDocument",
    "canonicalise",
    "event_source_document",
    "exposure_source_document",
]

_LEADING_WS = re.compile(r"^[ \t\f\v]+", re.MULTILINE)
_TRAILING_WS = re.compile(r"[ \t\f\v]+$", re.MULTILINE)
_INLINE_WS = re.compile(r"[ \t\f\v]{2,}")
_BLANK_RUN = re.compile(r"\n{3,}")

#: Guard against a whole PDF arriving where a narrative was expected.  Refused rather than
#: truncated: a document we silently shortened is a document whose spans point at text the
#: reader cannot see.
MAX_SOURCE_CHARS: Final[int] = 200_000


def canonicalise(text: str) -> str:
    """NFKC, LF line endings, no trailing whitespace, at most one blank line.

    Idempotent by construction — ``canonicalise(canonicalise(x)) == canonicalise(x)`` — and
    a test asserts it, because a non-idempotent canonicaliser makes ``source_sha256``
    depend on how many times the pipeline ran.
    """
    if not isinstance(text, str):  # pragma: no cover - defended by the models
        raise SourceDocumentError("source text must be str", python_type=type(text).__name__)
    normalised = unicodedata.normalize("NFKC", text)
    normalised = normalised.replace("\r\n", "\n").replace("\r", "\n")
    normalised = _INLINE_WS.sub(" ", normalised)
    normalised = _LEADING_WS.sub("", normalised)
    normalised = _TRAILING_WS.sub("", normalised)
    normalised = _BLANK_RUN.sub("\n\n", normalised)
    return normalised.strip()


def _sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class SourceDocument(BaseModel):
    """One canonical document, plus the location of its safety-net narrative inside it.

    ``narrative_span`` is not decoration.  The ``narrative`` facet is *raw text, unchanged*
    (ARCHITECTURE §6.2) and it still needs a ``source_span`` like every other cue row, so
    the span is computed here — structurally, from the rendering — rather than searched for
    later.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["event", "exposure"]
    subject_ref: str = Field(min_length=1)
    text: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    narrative_start: int = Field(ge=0)
    narrative_end: int = Field(ge=0)

    @model_validator(mode="after")
    def _consistent(self) -> SourceDocument:
        if len(self.text) > MAX_SOURCE_CHARS:
            raise ValueError(
                f"source document is {len(self.text)} chars, over the {MAX_SOURCE_CHARS} "
                "bound; refused rather than truncated"
            )
        if self.text != canonicalise(self.text):
            raise ValueError("source document text is not canonical")
        if _sha256_hex(self.text) != self.sha256:
            raise ValueError("source document sha256 does not match its text")
        if not 0 <= self.narrative_start < self.narrative_end <= len(self.text):
            raise ValueError(
                f"narrative span [{self.narrative_start}, {self.narrative_end}) is not a "
                f"non-empty range inside a {len(self.text)}-char document"
            )
        return self

    @property
    def narrative(self) -> str:
        """The safety-net narrative, verbatim, as it sits inside the canonical text."""
        return self.text[self.narrative_start : self.narrative_end]

    @property
    def narrative_span(self) -> tuple[int, int]:
        return (self.narrative_start, self.narrative_end)


def _assemble(
    kind: Literal["event", "exposure"],
    subject_ref: str,
    sections: list[tuple[str, str]],
    narrative_heading: str,
) -> SourceDocument:
    """Join ``(heading, body)`` sections and locate the narrative section's body exactly.

    The narrative offsets are computed from the lengths of the parts as they are joined, so
    they cannot disagree with the rendering.  Searching for the narrative afterwards would
    reintroduce precisely the ambiguity :mod:`.spans` refuses.
    """
    parts: list[str] = []
    cursor = 0
    narrative_start = -1
    narrative_end = -1
    for index, (heading, body) in enumerate(sections):
        clean_body = canonicalise(body)
        if not clean_body:
            continue
        block = f"{heading}\n{clean_body}"
        if index and parts:
            parts.append("\n\n")
            cursor += 2
        body_start = cursor + len(heading) + 1
        parts.append(block)
        cursor += len(block)
        if heading == narrative_heading:
            narrative_start = body_start
            narrative_end = body_start + len(clean_body)
    text = "".join(parts)
    if narrative_start < 0:
        raise SourceDocumentError(
            "the safety-net narrative section is empty; a cue set with no narrative has no "
            "fallback when every synthesised facet is insufficient",
            kind=kind,
            subject_ref=subject_ref,
        )
    if text[narrative_start:narrative_end] != canonicalise(
        dict(sections)[narrative_heading]
    ):  # pragma: no cover - arithmetic guard
        raise SourceDocumentError(
            "narrative span arithmetic disagrees with the rendered document",
            kind=kind,
            subject_ref=subject_ref,
        )
    return SourceDocument(
        kind=kind,
        subject_ref=subject_ref,
        text=text,
        sha256=_sha256_hex(text),
        narrative_start=narrative_start,
        narrative_end=narrative_end,
    )


EVENT_NARRATIVE_HEADING: Final[str] = "NARRATIVE"
EXPOSURE_NARRATIVE_HEADING: Final[str] = "SCOPE OF WORK"


def event_source_document(event: EventInput) -> SourceDocument:
    """Render the event side's canonical document.

    Title and normalised control failures are included because they are source material an
    appraiser would read, and a facet may legitimately quote either.  Nothing derived and
    nothing rated is included — see :mod:`.models` for why severity is absent.
    """
    failures = "\n".join(
        f"- {hint.control_class} | {hint.barrier_role} | {hint.failure_mode} | {hint.hazard_energy}"
        for hint in event.control_failures
    )
    sections = [
        ("RECORD", f"kind: {event.kind}\nreference: {event.subject_ref}"),
        ("TITLE", event.title),
        (EVENT_NARRATIVE_HEADING, event.narrative),
        ("RECORDED CONTROL FAILURES", failures),
    ]
    return _assemble("event", event.subject_ref, sections, EVENT_NARRATIVE_HEADING)


def exposure_source_document(
    permit: PermitInput, isolation_plan: IsolationPlan, clause_diff: ClauseDiff
) -> SourceDocument:
    """Render the permit side's canonical document.

    Three inputs, one document, because the exposure a permit creates is not visible in any
    of them alone: the scope says what will be done, the isolation plan says what stored
    energy is being relied on to stay put, and the clause diff says which written control
    is being stood down while that happens.

    Only ``weaken`` and ``remove`` entries reach the document.  A strengthened clause is not
    an exposure, and putting it in front of the synthesiser invites a cue about a control
    that is being *added* — a cue that would then retrieve precursors for a hazard this
    permit reduces.
    """
    isolation_lines: list[str] = []
    for point in isolation_plan.points:
        verified = f" | verified by {point.verified_by}" if point.verified_by else ""
        isolation_lines.append(f"- {point.tag} | {point.energy} | {point.method}{verified}")
    if isolation_plan.residual_energy_notes.strip():
        isolation_lines.append(f"residual energy: {isolation_plan.residual_energy_notes.strip()}")
    isolation_body = "\n".join([f"plan reference: {isolation_plan.plan_ref}", *isolation_lines])

    diff_blocks: list[str] = []
    for entry in clause_diff.waived_or_weakened():
        lines = [f"[{entry.control_delta}] {entry.clause_ref}"]
        if entry.before_text.strip():
            lines.append(f"before: {entry.before_text.strip()}")
        if entry.after_text.strip():
            lines.append(f"after: {entry.after_text.strip()}")
        if entry.rationale.strip():
            lines.append(f"stated rationale: {entry.rationale.strip()}")
        diff_blocks.append("\n".join(lines))

    sections = [
        (
            "PERMIT",
            f"work type: {permit.work_type}\nasset class: {permit.asset_class}\n"
            f"reference: {permit.subject_ref}",
        ),
        (EXPOSURE_NARRATIVE_HEADING, permit.scope_of_work),
        ("ISOLATION PLAN", isolation_body),
        ("CLAUSES BEING WAIVED OR WEAKENED", "\n\n".join(diff_blocks)),
    ]
    return _assemble("exposure", permit.subject_ref, sections, EXPOSURE_NARRATIVE_HEADING)
