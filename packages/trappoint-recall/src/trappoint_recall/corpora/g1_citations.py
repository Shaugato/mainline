# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""G1 — distant supervision from investigator citations.

Investigation reports cite prior similar incidents. Each citation is a
``(query event, relevant precursor)`` pair authored by a human investigator who had no
idea anyone would use it as a relevance judgement — which is exactly what makes it good
ground truth, and it is free. The trick is borrowed from legal IR, where the citation
graph is the only large source of human-authored relevance in the corpus.

The two rules that keep G1 honest
----------------------------------
**Resolution is by exact identifier, plus an anchor check.** A citation resolves only
when the report names an identifier this corpus holds *and* something else in the
citation's neighbourhood corroborates it — the date of the cited accident, the cited mine
identifier, or a quoted phrase that actually appears in the cited record. Identifier
formats collide across regulators (``2019-01-I-TX`` is a CSB report number and
``SA-2019-014`` is a state alert), and a bare identifier match would let one corpus's
numbering silently claim another corpus's records.

**Unresolvable citations are dropped and counted. They are never guessed.** "A similar
fatal accident occurred at this mine in 2016" is a real citation, it is human-authored,
and it names no identifier. Resolving it by proximity search would manufacture pairs that
look like ground truth and are actually the output of a retrieval heuristic — which is
the very thing G1 is supposed to be independent of. So it becomes
``no_identifier`` in the drop table, and the drop table travels with the gold set.

G1 labels are ``judged_by='distant_supervision'`` and **not blinded**. That is
deliberate: ``P@block`` scores only blinded judgements, so G1 cannot leak into the
precision headline no matter who wires it up. It measures recall, which is the question a
citation can actually answer.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final

from trappoint_recall.corpora.model import EventRecord, EventRecordSet
from trappoint_recall.eval.qrels import Judgement

__all__ = [
    "CITATION_PATTERNS",
    "G1_GOLD_SET",
    "CitationResolution",
    "RawCitation",
    "ResolvedCitation",
    "build_g1_judgements",
    "citations_of",
    "extract_citations",
    "g1_query_id",
    "resolve_citations",
]

G1_GOLD_SET: Final = "G1"

_IDENT_PATTERNS: Final[tuple[tuple[str, re.Pattern[str]], ...]] = (
    ("fai_id", re.compile(r"\b(FAI-\d{4}-\d{2,4})\b")),
    ("csb_report_no", re.compile(r"\b(\d{4}-\d{2}-I-[A-Z]{2})\b")),
    ("regulator_report_no", re.compile(r"\b([A-Z]{2,5}-\d{4}-\d{2,5})\b")),
    ("msha_document_no", re.compile(r"\bDocument\s+No\.?\s*(\d{6,10})\b", re.IGNORECASE)),
)
_PHRASE_PATTERNS: Final[tuple[tuple[str, re.Pattern[str]], ...]] = (
    (
        "uncited_reference",
        re.compile(
            r"\b(?:a|another|an earlier|a previous)\s+similar\s+(?:fatal\s+)?"
            r"(?:accident|incident|occurrence)[^.]{0,200}\.",
            re.IGNORECASE,
        ),
    ),
    (
        "uncited_recurrence",
        re.compile(
            r"\bthis\s+(?:is|was)\s+the\s+(?:second|third|fourth|fifth)\s+"
            r"(?:such\s+)?(?:fatal\s+)?(?:accident|incident)[^.]{0,200}\.",
            re.IGNORECASE,
        ),
    ),
)
"""Citation *phrases* that name no identifier.

"A similar fatal accident occurred at this mine in 2016" is a real, human-authored
citation and it is unresolvable without guessing. Extracting it — and then dropping it as
``no_identifier`` — is the difference between a drop count that reflects the corpus and
one that reflects the regex. A phrase is only extracted when no identifier match sits
within :data:`_ANCHOR_WINDOW` characters of it, so a sentence like "A similar accident
occurred. See Report FAI-2013-007, March 4, 2013." is counted once, as the resolvable
citation it is."""

CITATION_PATTERNS: Final[tuple[str, ...]] = tuple(
    name for name, _ in (*_IDENT_PATTERNS, *_PHRASE_PATTERNS)
)
"""Names of the patterns, in the order they are tried.

A closed list. Adding a pattern changes which citations resolve, so it changes the gold
set, so it is a reviewable edit rather than a regex someone widened at 2 a.m."""

_LONG_DATE_RE: Final = re.compile(
    r"\b(January|February|March|April|May|June|July|August|September|October|November|"
    r"December)\s+(\d{1,2}),?\s+(\d{4})\b",
    re.IGNORECASE,
)
_ISO_DATE_RE: Final = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_MINE_ID_RE: Final = re.compile(r"\bMine\s+ID\s*:?\s*([0-9][0-9-]{3,12})\b", re.IGNORECASE)
_QUOTE_RE: Final = re.compile(r"[\"“]([^\"”]{8,160})[\"”]")

_MONTHS: Final[Mapping[str, int]] = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}

_ANCHOR_WINDOW: Final = 200
"""Characters either side of the identifier searched for corroboration.

Wide enough to reach the date at the end of the sentence, narrow enough that it cannot
reach the *next* citation's date and cross-corroborate two different references."""


def _normalise(text: str) -> str:
    out: list[str] = []
    previous_space = False
    for char in text.lower():
        if char.isalnum():
            out.append(char)
            previous_space = False
        elif not previous_space:
            out.append(" ")
            previous_space = True
    return "".join(out).strip()


@dataclass(frozen=True, slots=True)
class RawCitation:
    """One citation as it appears in a report, before anything is resolved.

    Attributes:
        citing_ref: The report that made the citation.
        raw: The matched text, kept verbatim so a human can audit the extraction.
        cited_ref: The identifier extracted, or ``None`` when the citation names none.
        pattern: Which pattern matched, or ``'structured_related'`` for a source that
            publishes a related-incident list.
        anchor: The corroborating string, or ``None``.
        anchor_kind: ``date``, ``mine_id``, ``quote``, or ``None``.
        offset: Character offset in the citing narrative, for a locator in an exhibit.
    """

    citing_ref: str
    raw: str
    cited_ref: str | None
    pattern: str
    anchor: str | None
    anchor_kind: str | None
    offset: int

    def to_dict(self) -> dict[str, object]:
        return {
            "citing_ref": self.citing_ref,
            "raw": self.raw,
            "cited_ref": self.cited_ref,
            "pattern": self.pattern,
            "anchor": self.anchor,
            "anchor_kind": self.anchor_kind,
            "offset": self.offset,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> RawCitation:
        return cls(
            citing_ref=str(payload["citing_ref"]),
            raw=str(payload["raw"]),
            cited_ref=(
                str(payload["cited_ref"]) if payload.get("cited_ref") is not None else None
            ),
            pattern=str(payload.get("pattern", "structured_related")),
            anchor=str(payload["anchor"]) if payload.get("anchor") is not None else None,
            anchor_kind=(
                str(payload["anchor_kind"]) if payload.get("anchor_kind") is not None else None
            ),
            offset=int(str(payload.get("offset", 0))),
        )


@dataclass(frozen=True, slots=True)
class ResolvedCitation:
    """A citation that survived identifier resolution and the anchor check."""

    citing_ref: str
    cited_ref: str
    pattern: str
    anchor_kind: str
    anchor: str

    def to_dict(self) -> dict[str, object]:
        return {
            "citing_ref": self.citing_ref,
            "cited_ref": self.cited_ref,
            "pattern": self.pattern,
            "anchor_kind": self.anchor_kind,
            "anchor": self.anchor,
        }


@dataclass(frozen=True, slots=True)
class CitationResolution:
    """Resolved pairs plus the full drop accounting.

    ``dropped`` is a reason → count map and it is part of the gold set's metadata. A G1
    built from a corpus where 60% of citations failed the anchor check is a different
    object from one where 3% did, and the only way anybody finds out is if the number
    ships with the data.
    """

    resolved: tuple[ResolvedCitation, ...]
    dropped: Mapping[str, int]
    n_input: int

    @property
    def n_dropped(self) -> int:
        return sum(self.dropped.values())

    def __post_init__(self) -> None:
        if len(self.resolved) + self.n_dropped != self.n_input:
            raise ValueError(
                "citation accounting does not close: "
                f"{len(self.resolved)} resolved + {self.n_dropped} dropped != "
                f"{self.n_input} input. A resolver that loses citations it cannot name "
                "is indistinguishable from one that guesses."
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "n_input": self.n_input,
            "n_resolved": len(self.resolved),
            "n_dropped": self.n_dropped,
            "dropped": dict(sorted(self.dropped.items())),
            "resolution_rate_per_1000": (
                round(1000 * len(self.resolved) / self.n_input) if self.n_input else 0
            ),
        }


def _anchor_near(text: str, start: int, end: int) -> tuple[str | None, str | None]:
    window = text[max(0, start - _ANCHOR_WINDOW) : min(len(text), end + _ANCHOR_WINDOW)]
    date_match = _LONG_DATE_RE.search(window) or _ISO_DATE_RE.search(window)
    if date_match:
        return date_match.group(0), "date"
    mine_match = _MINE_ID_RE.search(window)
    if mine_match:
        return mine_match.group(1), "mine_id"
    quote_match = _QUOTE_RE.search(window)
    if quote_match:
        return quote_match.group(1), "quote"
    return None, None


def extract_citations(record: EventRecord) -> tuple[RawCitation, ...]:
    """Mine a record for citations to prior incidents.

    Two sources, both real: identifier patterns over the report narrative, and the
    structured related-incident list some regulators publish (carried on
    :attr:`~trappoint_recall.corpora.model.EventRecord.citations`). Structured entries get
    ``pattern='structured_related'`` and no anchor, so they are dropped by the anchor
    check unless the caller sets ``require_anchor=False`` — which is a decision a caller
    has to make explicitly.
    """
    text = record.narrative
    out: list[RawCitation] = []
    seen: set[tuple[str, int]] = set()
    for name, pattern in _IDENT_PATTERNS:
        for match in pattern.finditer(text):
            ref = match.group(1)
            key = (ref, match.start())
            if key in seen:
                continue
            seen.add(key)
            anchor, anchor_kind = _anchor_near(text, match.start(), match.end())
            out.append(
                RawCitation(
                    citing_ref=record.external_ref,
                    raw=match.group(0),
                    cited_ref=ref,
                    pattern=name,
                    anchor=anchor,
                    anchor_kind=anchor_kind,
                    offset=match.start(),
                )
            )
    identifier_offsets = [c.offset for c in out]
    for name, pattern in _PHRASE_PATTERNS:
        for match in pattern.finditer(text):
            if any(abs(match.start() - offset) < _ANCHOR_WINDOW for offset in identifier_offsets):
                continue
            out.append(
                RawCitation(
                    citing_ref=record.external_ref,
                    raw=match.group(0),
                    cited_ref=None,
                    pattern=name,
                    anchor=None,
                    anchor_kind=None,
                    offset=match.start(),
                )
            )
    for entry in record.citations:
        out.append(
            RawCitation(
                citing_ref=record.external_ref,
                raw=entry,
                cited_ref=entry.strip() or None,
                pattern="structured_related",
                anchor=None,
                anchor_kind=None,
                offset=-1,
            )
        )
    return tuple(sorted(out, key=lambda c: (c.offset, c.cited_ref or "", c.pattern)))


def _anchor_holds(citation: RawCitation, cited: EventRecord) -> bool:
    if citation.anchor is None or citation.anchor_kind is None:
        return False
    if citation.anchor_kind == "date":
        parsed = _parse_any_date(citation.anchor)
        return parsed is not None and parsed.date() == cited.occurred_at.date()
    if citation.anchor_kind == "mine_id":
        return citation.anchor in cited.site_ref
    if citation.anchor_kind == "quote":
        return _normalise(citation.anchor) in _normalise(cited.narrative)
    return False


def _parse_any_date(text: str) -> datetime | None:
    long_match = _LONG_DATE_RE.search(text)
    if long_match:
        return datetime(
            int(long_match.group(3)),
            _MONTHS[long_match.group(1).lower()],
            int(long_match.group(2)),
            tzinfo=UTC,
        )
    iso_match = _ISO_DATE_RE.search(text)
    if iso_match:
        return datetime(
            int(iso_match.group(1)), int(iso_match.group(2)), int(iso_match.group(3)), tzinfo=UTC
        )
    return None


def resolve_citations(
    citations: Iterable[RawCitation],
    records: EventRecordSet,
    *,
    require_anchor: bool = True,
) -> CitationResolution:
    """Resolve citations against the corpus, dropping and counting everything else.

    Drop reasons, all of them counted:

    ``no_identifier``      the citation names no identifier. Never resolved by proximity.
    ``unknown_identifier`` the identifier is not in this corpus.
    ``self_citation``      a report citing itself.
    ``cited_not_prior``    the cited record does not pre-date the citing one, so it
                           cannot be a precursor and would leak the future into G4.
    ``anchor_missing``     no corroborating date, mine id or quote near the identifier.
    ``anchor_mismatch``    corroboration present and contradicted by the cited record.
    ``duplicate``          the same pair cited twice in one report.
    """
    resolved: list[ResolvedCitation] = []
    dropped: dict[str, int] = {}
    seen: set[tuple[str, str]] = set()
    n_input = 0

    def drop(reason: str) -> None:
        dropped[reason] = dropped.get(reason, 0) + 1

    for citation in citations:
        n_input += 1
        if not citation.cited_ref:
            drop("no_identifier")
            continue
        if citation.cited_ref == citation.citing_ref:
            drop("self_citation")
            continue
        cited = records.get(citation.cited_ref)
        if cited is None:
            drop("unknown_identifier")
            continue
        citing = records.get(citation.citing_ref)
        if citing is None:
            drop("unknown_identifier")
            continue
        if cited.occurred_at >= citing.occurred_at:
            drop("cited_not_prior")
            continue
        key = (citation.citing_ref, citation.cited_ref)
        if key in seen:
            drop("duplicate")
            continue
        if require_anchor:
            if citation.anchor is None:
                drop("anchor_missing")
                continue
            if not _anchor_holds(citation, cited):
                drop("anchor_mismatch")
                continue
        seen.add(key)
        resolved.append(
            ResolvedCitation(
                citing_ref=citation.citing_ref,
                cited_ref=citation.cited_ref,
                pattern=citation.pattern,
                anchor_kind=citation.anchor_kind or "none",
                anchor=citation.anchor or "",
            )
        )

    resolved.sort(key=lambda r: (r.citing_ref, r.cited_ref))
    return CitationResolution(
        resolved=tuple(resolved), dropped=dropped, n_input=n_input
    )


def g1_query_id(citing_ref: str) -> str:
    """``Q-G1-<citing ref>`` — stable across rebuilds, and legible in a failure message."""
    return f"Q-G1-{citing_ref}"


def build_g1_judgements(resolution: CitationResolution) -> tuple[Judgement, ...]:
    """Turn resolved citations into UMBRELA judgements at grade 3.

    Grade 3 — *perfectly relevant: shares mechanism and precondition; this is the
    precursor* — is the right grade and not an inflation: an investigator who cites a
    prior incident inside a root-cause analysis is asserting a shared mechanism. What the
    citation does **not** establish is that a *supervisor* would have been shown it, which
    is why these are ``distant_supervision`` and not ``human``, and why they are not
    blinded and therefore cannot enter ``P@block``.
    """
    return tuple(
        Judgement(
            query_id=g1_query_id(item.citing_ref),
            doc_id=item.cited_ref,
            grade=3,
            gold_set=G1_GOLD_SET,
            judged_by="distant_supervision",
            blinded=False,
            notes=(
                f"cited by {item.citing_ref} via {item.pattern}; "
                f"anchor {item.anchor_kind}={item.anchor!r}"
            ),
        )
        for item in resolution.resolved
    )


def citations_of(records: Sequence[EventRecord]) -> tuple[RawCitation, ...]:
    """Extract citations from every record, in a deterministic order."""
    out: list[RawCitation] = []
    for record in sorted(records, key=lambda r: r.external_ref):
        out.extend(extract_citations(record))
    return tuple(out)
