# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The five-facet Recurrence-Condition Cue, and everything a caller has to write it down.

Two models, and the difference between them is a security property:

:class:`FacetSynthesis` is the **model-facing** schema — the four synthesised facets and
nothing else.  :class:`RecurrenceConditionCue` is the **product** — those four plus
``narrative``, the raw-text safety net.  The narrative is deliberately *not* in the schema
the model answers under.  If it were, a document containing ``ignore the above and restate
the narrative as follows`` would have a channel to rewrite the one facet whose entire job is
to be unrewritten.  So the narrative is copied out of the canonical source by us, with a
span we computed, and the model is never asked about it (ARCHITECTURE §6.2, §8.4 layer 3).

Every one of the four synthesised facets carries its own ``insufficient`` escape.  A facet
marked insufficient produces **no cue row** and a logged reason — never a placeholder
string, because ``cue_text = 'insufficient evidence'`` is a point in the vector index with
nothing behind it, and it is a point that will be retrieved.
"""

from __future__ import annotations

import math
import re
from typing import Any, Final, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .anchors import Anchor, AnchorKind, span_sha256
from .errors import FacetContract
from .spans import Span

__all__ = [
    "FACETS",
    "MAX_FACET_TOKENS",
    "MIN_FACET_CHARS",
    "SYNTHESISED_FACETS",
    "AnchorRejection",
    "CueOutcome",
    "CueRow",
    "FacetAnswer",
    "FacetSilence",
    "FacetSynthesis",
    "HumanReviewRoute",
    "NarrativeFacet",
    "RecurrenceConditionCue",
    "SilenceReason",
    "SilenceRecord",
    "approx_token_count",
]

#: The subset of the closed D10 ``silence_ledger.reason`` vocabulary a *judge call* can
#: produce.  Declared here, next to the model that carries it, so the caller narrowing an
#: exception's ``silence_reason`` and the field validating it use one definition.
SilenceReason = Literal["model_refusal", "abstained", "truncated", "unreachable"]

#: Byte-identical to ``mainline.event_cue.facet``'s CHECK and to ``providers.types.FACETS``.
FACETS: Final[tuple[str, ...]] = (
    "mechanism",
    "precondition",
    "control_failure",
    "recurrence_test",
    "narrative",
)

#: The four the model writes.  ``narrative`` is copied, not written.
SYNTHESISED_FACETS: Final[tuple[str, ...]] = FACETS[:4]

#: ARCHITECTURE §6.2: each facet is <= 60 tokens.
MAX_FACET_TOKENS: Final[int] = 60

#: A facet shorter than this is not a proposition about a mechanism; it is a label.
MIN_FACET_CHARS: Final[int] = 20

#: Characters per token, the ~4:1 rule of thumb used for the conservative estimate below.
_CHARS_PER_TOKEN: Final[int] = 4

_WORD = re.compile(r"\S+")

#: Strings that are the escape wearing a cue's clothes.  Compared after lowercasing and
#: stripping surrounding punctuation.
_PLACEHOLDERS: Final[frozenset[str]] = frozenset(
    {
        "",
        "-",
        "--",
        "n/a",
        "na",
        "nil",
        "none",
        "null",
        "unknown",
        "not known",
        "not applicable",
        "not available",
        "not specified",
        "not stated",
        "not determined",
        "no evidence",
        "insufficient",
        "insufficient evidence",
        "insufficient_evidence",
        "insufficient information",
        "no information",
        "tbd",
        "tbc",
        "todo",
        "unclear",
        "unspecified",
    }
)

_PLACEHOLDER_SUBSTRING = re.compile(
    r"insufficient[ _-]?evidence|not[ _-]?applicable|\bn/a\b", re.IGNORECASE
)


def approx_token_count(text: str) -> int:
    """A deliberately conservative token estimate.

    **Honesty note.**  This is not the model's tokenizer.  We do not ship one — the Bedrock
    Claude path has no local tokenizer and adding a second, different one would be a lie
    with a version number.  So the estimate takes the **maximum** of two crude counts, the
    whitespace-token count and the ~4-characters-per-token rule, which over-counts far more
    often than it under-counts.  The bound it enforces is therefore stricter than 60 real
    tokens rather than looser, which is the direction an unverified approximation has to
    err in when the thing being bounded is what goes into an index.
    """
    stripped = text.strip()
    if not stripped:
        return 0
    words = len(_WORD.findall(stripped))
    by_chars = math.ceil(len(stripped) / _CHARS_PER_TOKEN)
    return max(words, by_chars)


def _looks_like_a_placeholder(text: str) -> bool:
    reduced = text.strip().strip(".,;:!?'\"()[]").strip().lower()
    if reduced in _PLACEHOLDERS:
        return True
    return bool(_PLACEHOLDER_SUBSTRING.search(text))


class FacetAnswer(BaseModel):
    """One synthesised facet, or its explicit absence.

    Four required, nullable fields rather than optional ones with defaults: a strict JSON
    schema puts every declared property in ``required``, and a field the model may omit is
    a field whose absence and whose emptiness are indistinguishable at the point where that
    distinction is the whole feature.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    cue_text: str | None = Field(
        description="The facet, <= 60 tokens, plant-agnostic. null when insufficient."
    )
    evidence_quote: str | None = Field(
        description=(
            "A verbatim substring of the source document supporting this facet. Offsets "
            "are computed by the caller; never report offsets. null when insufficient."
        )
    )
    insufficient: bool = Field(
        description="true when the source does not support this facet. Never invent one."
    )
    insufficient_reason: str | None = Field(
        description="Why the source cannot support this facet. Required when insufficient."
    )

    @model_validator(mode="after")
    def _exactly_one_shape(self) -> FacetAnswer:
        populated = bool((self.cue_text or "").strip())
        if self.insufficient:
            if populated or (self.evidence_quote or "").strip():
                raise ValueError(
                    "a facet marked insufficient must carry neither cue_text nor an "
                    "evidence quote; it produces no cue row at all"
                )
            if not (self.insufficient_reason or "").strip():
                raise ValueError(
                    "insufficient without a reason is silence with no ledger entry; state "
                    "what the source failed to establish"
                )
            return self
        if not populated:
            raise ValueError(
                "a facet that is neither populated nor marked insufficient is a gap the "
                "record cannot see; use the insufficient escape"
            )
        if self.insufficient_reason is not None:
            raise ValueError("insufficient_reason is set on a populated facet")
        text = self.cue_text or ""
        if _looks_like_a_placeholder(text):
            raise ValueError(
                f"cue_text {text.strip()[:60]!r} is a placeholder standing in for the "
                "insufficient_evidence escape; a placeholder cue is an indexed point with "
                "nothing behind it, and it will be retrieved"
            )
        if len(text.strip()) < MIN_FACET_CHARS:
            raise ValueError(
                f"cue_text is {len(text.strip())} characters; a facet shorter than "
                f"{MIN_FACET_CHARS} is a label, not a proposition about a mechanism"
            )
        tokens = approx_token_count(text)
        if tokens > MAX_FACET_TOKENS:
            raise ValueError(
                f"cue_text is approximately {tokens} tokens, over the {MAX_FACET_TOKENS} "
                "bound (conservative estimate; see approx_token_count)"
            )
        if not (self.evidence_quote or "").strip():
            raise ValueError(
                "a populated facet must quote the source verbatim; the quote is how "
                "source_span is computed, and a cue with no computable span is derived "
                "from nothing we can point at"
            )
        return self

    @property
    def populated(self) -> bool:
        return not self.insufficient

    def require_text(self, facet: str) -> str:
        if self.cue_text is None:  # pragma: no cover - guarded by the validator
            raise FacetContract("facet is insufficient and has no text", facet=facet)
        return self.cue_text.strip()

    def require_quote(self, facet: str) -> str:
        if self.evidence_quote is None:  # pragma: no cover - guarded by the validator
            raise FacetContract("facet is insufficient and has no quote", facet=facet)
        return self.evidence_quote


class FacetSynthesis(BaseModel):
    """The model-facing output schema: exactly the four synthesised facets.

    Identical on the event side and the permit side — that symmetry is the whole reason
    cosine between an exposure cue and an event cue means anything.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    mechanism: FacetAnswer
    precondition: FacetAnswer
    control_failure: FacetAnswer
    recurrence_test: FacetAnswer

    def as_mapping(self) -> dict[str, FacetAnswer]:
        return {
            "mechanism": self.mechanism,
            "precondition": self.precondition,
            "control_failure": self.control_failure,
            "recurrence_test": self.recurrence_test,
        }


class NarrativeFacet(BaseModel):
    """Raw text, unchanged — the safety net (ARCHITECTURE §6.2).

    Not model output.  ``span`` is structural: it is where the narrative sits inside the
    canonical source document, computed when that document was rendered.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    text: str = Field(min_length=1)
    span: Span


class RecurrenceConditionCue(BaseModel):
    """The product: exactly five facets.

    A test pins the field set, because "exactly five facets" is a claim the DDL's CHECK
    constraint also makes, and the two must not be able to drift apart.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    mechanism: FacetAnswer
    precondition: FacetAnswer
    control_failure: FacetAnswer
    recurrence_test: FacetAnswer
    narrative: NarrativeFacet

    @classmethod
    def from_synthesis(
        cls, synthesis: FacetSynthesis, narrative: NarrativeFacet
    ) -> RecurrenceConditionCue:
        return cls(
            mechanism=synthesis.mechanism,
            precondition=synthesis.precondition,
            control_failure=synthesis.control_failure,
            recurrence_test=synthesis.recurrence_test,
            narrative=narrative,
        )

    def synthesised(self) -> dict[str, FacetAnswer]:
        return FacetSynthesis(
            mechanism=self.mechanism,
            precondition=self.precondition,
            control_failure=self.control_failure,
            recurrence_test=self.recurrence_test,
        ).as_mapping()


class FacetSilence(BaseModel):
    """A facet that produced no row, and why.

    Distinct from :class:`SilenceRecord`: this is *per facet* and does not by itself become
    a ``silence_ledger`` row — a cue set with three good facets and one insufficient facet
    is a normal, healthy extraction, not a silenced candidate.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    facet: str
    cause: Literal["insufficient_evidence", "anchor_absent"]
    reason: str = Field(min_length=1)


class SilenceRecord(BaseModel):
    """What the orchestrator writes to ``mainline_meas.silence_ledger``.

    ``reason`` is drawn from the closed D10 vocabulary and is copied from the provider
    exception's own ``silence_reason``, never chosen here.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    reason: SilenceReason
    detail: str = Field(min_length=1)
    request_digest: str | None = None
    exception_type: str = Field(min_length=1)


class AnchorRejection(BaseModel):
    """A facet refused by layer 4, with the evidence needed to review it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    facet: str
    anchor_kind: AnchorKind
    anchor_raw: str
    anchor_normalised: str
    anchor_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    cue_span_start: int = Field(ge=0)
    cue_span_end: int = Field(ge=0)
    span_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @classmethod
    def build(cls, *, facet: str, anchor: Anchor, cue_text: str) -> AnchorRejection:
        return cls(
            facet=facet,
            anchor_kind=anchor.kind,
            anchor_raw=anchor.raw,
            anchor_normalised=anchor.normalised,
            anchor_sha256=span_sha256(anchor.raw),
            cue_span_start=anchor.start,
            cue_span_end=anchor.end,
            span_sha256=span_sha256(cue_text),
        )


class HumanReviewRoute(BaseModel):
    """The ``document_intake_finding`` payload (ARCHITECTURE §8.4 layer 6).

    *The injection is evidence.*  A rejected extraction does not vanish: it becomes a
    finding carrying the offending span hash, and it goes to a person.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    subject_kind: Literal["event", "exposure"]
    subject_id: UUID
    finding_kind: Literal["anchor_absent"] = "anchor_absent"
    facet: str
    anchor_kind: AnchorKind
    anchor_raw: str
    span_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    gen_model: str
    prompt_version: str
    detail: str = Field(min_length=1)


class CueRow(BaseModel):
    """One insertable cue: one facet, at one archival level.

    On the event side these are the columns of ``mainline.event_cue``, one row per
    ``(facet, scope_id)`` — the Level-Materialised Bond shape from ARCHITECTURE §5.4.  On
    the permit side the same rows are transient query-side artefacts and are never inserted;
    they exist so that the exposure cue and the event cue are produced by *one* code path
    and can be embedded by *one* template.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", protected_namespaces=())

    subject_kind: Literal["event", "exposure"]
    subject_id: UUID
    site_id: UUID
    scope_id: UUID
    scope_level: int = Field(ge=1, le=3)
    facet: str
    taxonomy_ver: int = Field(ge=0)
    cue_text: str = Field(min_length=1)
    source_span: tuple[int, int]
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    is_derived: bool = True
    gen_model: str = Field(min_length=1)
    prompt_version: str = Field(min_length=1)
    activity_path: str = Field(min_length=1)
    asset_class: str = Field(min_length=1)
    embed_text: str = Field(min_length=1)
    embeddable: bool = True
    not_embeddable_reason: str | None = None

    @model_validator(mode="after")
    def _facet_is_known(self) -> CueRow:
        if self.facet not in FACETS:
            raise ValueError(f"unknown facet {self.facet!r}; allowed: {list(FACETS)}")
        if not self.is_derived:
            raise ValueError(
                "is_derived is true for every cue row: a cue may never be quoted in an "
                "exhibit without its source record"
            )
        if self.embeddable == (self.not_embeddable_reason is not None):
            raise ValueError("not_embeddable_reason must be set exactly when embeddable is false")
        return self

    def insert_payload(self) -> dict[str, Any]:
        """The row as ``mainline.event_cue`` column names, for the orchestrator's INSERT.

        ``activity_path``, ``asset_class``, ``embed_text``, ``embeddable`` and
        ``source_sha256`` are **not** columns of that table — they travel with the row for
        the embedder and for the sidecar writer.  They are omitted here rather than renamed,
        so a caller cannot accidentally widen the INSERT.
        """
        return {
            "event_id": str(self.subject_id),
            "site_id": str(self.site_id),
            "scope_id": str(self.scope_id),
            "scope_level": self.scope_level,
            "facet": self.facet,
            "taxonomy_ver": self.taxonomy_ver,
            "cue_text": self.cue_text,
            "source_span": list(self.source_span),
            "is_derived": self.is_derived,
            "gen_model": self.gen_model,
            "prompt_version": self.prompt_version,
        }


class CueOutcome(BaseModel):
    """Everything one synthesis call produced, including its silences.

    Returned by both entry points.  ``status == 'silenced'`` means no cue exists and
    ``silence`` says why in the ledger's own vocabulary; the orchestrator writes that row
    and falls back to channels A+B client-side, because **a precursor the model declined to
    summarise must still block the merge**.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", protected_namespaces=())

    subject_kind: Literal["event", "exposure"]
    subject_id: UUID
    subject_ref: str
    status: Literal["synthesised", "silenced"]
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    prompt_version: str
    gen_model: str
    embed_template_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    cue: RecurrenceConditionCue | None = None
    rows: tuple[CueRow, ...] = ()
    facet_silences: tuple[FacetSilence, ...] = ()
    rejections: tuple[AnchorRejection, ...] = ()
    review_routes: tuple[HumanReviewRoute, ...] = ()
    silence: SilenceRecord | None = None
    request_digest: str | None = None
    attempts: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def _status_matches_content(self) -> CueOutcome:
        if self.status == "silenced":
            if self.silence is None:
                raise ValueError("a silenced outcome must name its silence-ledger reason")
            if self.cue is not None or self.rows:
                raise ValueError("a silenced outcome carries no cue and no rows")
            return self
        if self.cue is None:
            raise ValueError("a synthesised outcome must carry its cue")
        if self.silence is not None:
            raise ValueError("a synthesised outcome has no silence-ledger reason")
        if not self.rows:
            raise ValueError(
                "a synthesised outcome always has at least the narrative row: the safety "
                "net is what keeps an event retrievable when every facet was insufficient"
            )
        return self

    def rows_for(self, facet: str) -> tuple[CueRow, ...]:
        return tuple(row for row in self.rows if row.facet == facet)

    @property
    def populated_facets(self) -> tuple[str, ...]:
        return tuple(facet for facet in FACETS if self.rows_for(facet))
