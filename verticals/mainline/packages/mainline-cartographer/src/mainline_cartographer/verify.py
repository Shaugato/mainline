# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The verifier — where a model proposal becomes a row, or does not.

Nothing the model emits reaches a table without passing every check in this module, and
the checks are ordered so that the cheapest, most structural one runs first. In order:

1. **The label is one we minted.** ``C4`` either is in the candidate map or it is not.
   An unknown label is a hallucinated clause and it is dropped, not repaired.
2. **The candidate belongs to the incident's site.** Blame does not cross sites without
   a fleet-propagation record, and this package writes none.
3. **The control class was read from the database, not from the model.** The proposal
   must copy one of the ``control_failure.control_class`` values the incident actually
   records. This is layer 4 of the injection posture — semantic anchoring — and it is
   the cheapest high-value control in the whole ingest: an injected instruction can
   change field *values*, but it cannot conjure a failed control the ICAM record does
   not contain.
4. **Both quotes bind, exactly and uniquely.** ``str.find`` into the clause's
   ``canon_text`` and into the event's ``narrative``. *We compute the offsets.* A model
   never reports one, so a model can never misreport one. Not found ⇒ dropped. Found
   twice ⇒ dropped, because a span that could be either of two places is not a span.

**Failures drop the link; they do not fail the call.** A single unbindable quote among
five links must not discard the four that bound — but neither may it vanish. Every drop
is returned in :attr:`VerifiedBlame.dropped` with its reason, and
:meth:`VerifiedBlame.arithmetic` renders the counts for the silence ledger. *The
injection is evidence*: a proposal dropped because its quote was an instruction rather
than a clause is a row in the record, not a gap in it.

The score is ours. The model emits a named confidence band; this module maps the band to
an integer count of thousandths through :data:`CONFIDENCE_P_LINK_MILLI`. The model never
emits a number, so no number it emits can be read as a calibrated probability — and the
integer keeps a float out of a payload that gets hashed (ADR 0042).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .errors import QuoteAmbiguous, QuoteUnbound
from .types import BlameBasis, BlameState, ProvisionalBlameEdge

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from datetime import datetime

    from .profile import BlameLinkProposal, ProposedLink
    from .types import ClauseCandidate, EventRow

__all__ = [
    "CONFIDENCE_P_LINK_MILLI",
    "DROP_REASONS",
    "DroppedLink",
    "VerifiedBlame",
    "attribution_for",
    "bind_quote",
    "verify_links",
]

#: Band → integer thousandths. The model names a band; the number is ours, it is
#: documented, and it is the same for every caller. `p_link` is stored as FLOAT8 by the
#: DDL, so :mod:`mainline_cartographer.emit` renders this integer as an exact decimal at
#: the very last moment — the value that gets hashed into `features` stays an integer.
CONFIDENCE_P_LINK_MILLI: Mapping[str, int] = {"low": 200, "medium": 500, "high": 800}

#: Every reason a proposed link can be discarded. Closed, because a drop reason that is
#: not in this set is a silent drop, and a silent drop in a recall path is the defect
#: this product exists to refuse.
DROP_REASONS: frozenset[str] = frozenset(
    {
        "unknown_candidate",
        "site_mismatch",
        "control_class_not_in_source",
        "evidence_quote_unbound",
        "evidence_quote_ambiguous",
        "narrative_quote_unbound",
        "narrative_quote_ambiguous",
        "duplicate_link",
    }
)


@dataclass(frozen=True, slots=True)
class DroppedLink:
    """One proposal the verifier refused, and why."""

    candidate_label: str
    reason: str
    detail: str

    def __post_init__(self) -> None:
        """Refuse a reason outside the closed vocabulary."""
        if self.reason not in DROP_REASONS:
            raise ValueError(f"drop reason {self.reason!r} is outside {sorted(DROP_REASONS)}")

    def to_mapping(self) -> dict[str, str]:
        """Render for the silence ledger's ``arithmetic`` and the console."""
        return {
            "candidate_label": self.candidate_label,
            "reason": self.reason,
            "detail": self.detail,
        }


@dataclass(frozen=True, slots=True)
class VerifiedBlame:
    """What survived verification, what did not, and what the model said about itself."""

    edges: tuple[ProvisionalBlameEdge, ...]
    dropped: tuple[DroppedLink, ...]
    abstained: bool
    abstain_reason: str
    injection_noted: bool
    injection_note: str

    def arithmetic(self) -> dict[str, Any]:
        """Render the counts a ``silence_ledger`` row carries when nothing survived."""
        by_reason: dict[str, int] = {}
        for drop in self.dropped:
            by_reason[drop.reason] = by_reason.get(drop.reason, 0) + 1
        return {
            "proposed": len(self.edges) + len(self.dropped),
            "verified": len(self.edges),
            "dropped": len(self.dropped),
            "dropped_by_reason": dict(sorted(by_reason.items())),
            "abstained": self.abstained,
            "abstain_reason": self.abstain_reason,
            "injection_noted": self.injection_noted,
        }


def bind_quote(haystack: str, needle: str, *, where: str) -> tuple[int, int]:
    """Bind a quote to an exact, unique span, or refuse.

    Args:
        haystack: the source text the quote claims to come from.
        needle: the verbatim span the model copied.
        where: a name for the source, used in the refusal message.

    Returns:
        ``(start, end)`` — character offsets **we** computed.

    Raises:
        QuoteUnbound: the quote does not occur in the source.
        QuoteAmbiguous: the quote occurs more than once.
    """
    occurrences = haystack.count(needle)
    if occurrences == 0:
        raise QuoteUnbound(where, needle)
    if occurrences > 1:
        raise QuoteAmbiguous(where, needle, occurrences)
    start = haystack.index(needle)
    return start, start + len(needle)


def attribution_for(event: EventRow, link: ProposedLink, *, prompt_version: str) -> str:
    """Compose the prose a human is shown beside an inferred link.

    The DDL comment on ``blame_edge.attribution`` is explicit — *prose a human is shown;
    never a bare number* — so the confidence band appears as its word and the score does
    not appear at all. The sentence also states its own force: a reader who sees this
    string must not be able to mistake it for something that blocked anything.
    """
    occurred = event.occurred_at.date().isoformat()
    kinds = {
        "control_named": "names the control this incident records as having failed",
        "hazard_energy_match": "governs the same hazardous energy and activity as this incident",
        "procedure_revised": "refers to the revision this incident describes",
    }
    return (
        f"Proposed link, {link.confidence_band} confidence: this clause "
        f"{kinds[link.link_kind]} ({link.control_class}). Incident: {event.title} "
        f"({event.kind}, {occurred}). Inferred by the Cartographer under prompt "
        f"{prompt_version}; PROVISIONAL and not counted in ancestral severity. It blocks "
        f"nothing on its own and awaits a reviewer."
    )


def verify_links(
    proposal: BlameLinkProposal,
    *,
    event: EventRow,
    candidates: Sequence[ClauseCandidate],
    commit_id: str,
    model_id: str,
    prompt_version: str,
    provisional_until: datetime,
    provenance: Mapping[str, Any] | None = None,
    evidence_doc_id: str | None = None,
) -> VerifiedBlame:
    """Turn a model proposal into rows that could be inserted, and a record of the rest.

    Args:
        proposal: what the model emitted, already schema-valid.
        event: the incident the proposal is about, with its deterministic
            ``control_failure`` classes.
        candidates: the clauses that were offered, keyed by the labels we minted.
        commit_id: hex commit the edge is pinned to.
        model_id: the resolved ``au.*`` inference-profile ARN, for the row and the record.
        prompt_version: the profile's prompt version.
        provisional_until: when the provisional edge lapses without review.
        provenance: the replayability quad from
            :meth:`mainline_agentkit.call.Validated.provenance`, folded into ``features``.
        evidence_doc_id: the clause's source document, when the caller knows it.

    Returns:
        The surviving edges and every drop, with its reason.
    """
    by_label = {candidate.label: candidate for candidate in candidates}
    allowed_classes = frozenset(event.control_classes)
    edges: list[ProvisionalBlameEdge] = []
    dropped: list[DroppedLink] = []
    seen: set[str] = set()

    for link in proposal.links:
        candidate = by_label.get(link.candidate_label)
        if candidate is None:
            dropped.append(
                DroppedLink(
                    link.candidate_label,
                    "unknown_candidate",
                    f"no candidate was offered under label {link.candidate_label!r}; "
                    f"offered: {sorted(by_label)}",
                )
            )
            continue
        if candidate.site_id != event.site_id:
            dropped.append(
                DroppedLink(
                    link.candidate_label,
                    "site_mismatch",
                    f"candidate site {candidate.site_id} is not the incident's site "
                    f"{event.site_id}; blame crosses sites only through fleet propagation",
                )
            )
            continue
        if link.control_class not in allowed_classes:
            dropped.append(
                DroppedLink(
                    link.candidate_label,
                    "control_class_not_in_source",
                    f"control_class {link.control_class!r} is not among the failed control "
                    f"classes recorded for this incident: {sorted(allowed_classes)}",
                )
            )
            continue
        if candidate.clause_uuid in seen:
            dropped.append(
                DroppedLink(
                    link.candidate_label,
                    "duplicate_link",
                    f"clause {candidate.clause_uuid} was already linked by an earlier proposal; "
                    f"blame_edge's primary key is (clause_uuid, event_id, basis)",
                )
            )
            continue

        bound = _bind_both(link, candidate, event)
        if isinstance(bound, DroppedLink):
            dropped.append(bound)
            continue
        evidence_span, narrative_span = bound

        seen.add(candidate.clause_uuid)
        edges.append(
            ProvisionalBlameEdge(
                event_id=event.event_id,
                clause_uuid=candidate.clause_uuid,
                site_id=event.site_id,
                commit_id=commit_id,
                p_link_milli=CONFIDENCE_P_LINK_MILLI[link.confidence_band],
                features=_features(
                    link,
                    event=event,
                    evidence_span=evidence_span,
                    narrative_span=narrative_span,
                    provenance=provenance,
                ),
                attribution=attribution_for(event, link, prompt_version=prompt_version),
                evidence_span=evidence_span,
                evidence_quote_sha256=_sha256_hex(link.evidence_quote),
                provisional_until=provisional_until,
                model_id=model_id,
                prompt_version=prompt_version,
                evidence_doc_id=evidence_doc_id,
                basis=BlameBasis.INFERRED_SEMANTIC,
                state=BlameState.PROVISIONAL,
            )
        )

    return VerifiedBlame(
        edges=tuple(edges),
        dropped=tuple(dropped),
        abstained=proposal.abstained,
        abstain_reason=proposal.abstain_reason,
        injection_noted=proposal.injection_noted,
        injection_note=proposal.injection_note,
    )


def _bind_both(
    link: ProposedLink, candidate: ClauseCandidate, event: EventRow
) -> tuple[tuple[int, int], tuple[int, int]] | DroppedLink:
    """Bind both quotes, returning the spans or the drop that stopped them."""
    try:
        evidence_span = bind_quote(
            candidate.canon_text, link.evidence_quote, where=f"clause {candidate.label} canon_text"
        )
    except QuoteUnbound as exc:
        return DroppedLink(link.candidate_label, "evidence_quote_unbound", str(exc))
    except QuoteAmbiguous as exc:
        return DroppedLink(link.candidate_label, "evidence_quote_ambiguous", str(exc))
    try:
        narrative_span = bind_quote(
            event.narrative, link.narrative_quote, where=f"event {event.event_id} narrative"
        )
    except QuoteUnbound as exc:
        return DroppedLink(link.candidate_label, "narrative_quote_unbound", str(exc))
    except QuoteAmbiguous as exc:
        return DroppedLink(link.candidate_label, "narrative_quote_ambiguous", str(exc))
    return evidence_span, narrative_span


def _features(
    link: ProposedLink,
    *,
    event: EventRow,
    evidence_span: tuple[int, int],
    narrative_span: tuple[int, int],
    provenance: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Build ``blame_edge.features``: everything a reviewer needs to re-derive the drop.

    ``CHECK scored_needs_features`` makes this column non-null on an inferred basis, and
    what it should hold is not a feature vector — it is the *reason this row exists*, in
    a form a human can check against the two source texts without running our code.
    """
    payload: dict[str, Any] = {
        "basis_law": "inferred_semantic edges never reach active and never raise max_severity",
        "link_kind": link.link_kind,
        "confidence_band": link.confidence_band,
        "p_link_milli": CONFIDENCE_P_LINK_MILLI[link.confidence_band],
        "control_class": link.control_class,
        "control_class_source": "mainline.control_failure",
        "candidate_label": link.candidate_label,
        "evidence_span": [evidence_span[0], evidence_span[1]],
        "narrative_span": [narrative_span[0], narrative_span[1]],
        "narrative_quote_sha256": _sha256_hex(link.narrative_quote),
        "event_source_sha256": event.source_sha256,
        "offsets_computed_by": "mainline_cartographer.verify.bind_quote",
    }
    if provenance is not None:
        payload["provenance"] = dict(provenance)
    return payload


def _sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
