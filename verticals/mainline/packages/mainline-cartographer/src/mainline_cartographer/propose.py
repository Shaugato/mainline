# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""Issuing the blame-link call, and composing what the model is allowed to see.

This module is the only place in the package that touches a model, and it touches it
through :func:`mainline_agentkit.call.quarantined_call`, which has no ``tools``
parameter. The Cartographer reads incident narratives and clause text — both of them
customer documents, both of them possibly hostile — and holds no capability to act on
what it reads. That is a property of the call shape, not of the prompt, and it survives
a prompt the attacker wrote.

**What is trusted and what is not.** The incident narrative and the clause text are
untrusted and go inside the sentinel. The trusted context carries only things the
database told us: the site, the event id, the failed control classes from
``control_failure``, and the label list. The model answers in labels; the caller maps
labels back to UUIDs. No identifier the model emits is ever used as an identifier.

**A refusal is not an empty result.** ``ModelRefused`` propagates out of this module
untouched, because §8.4's sentence is the whole point: *a precursor the model declined
to summarise must still block the merge.* :func:`blame_silence_row` builds the
``silence_ledger`` row the caller writes — ``source='blame_lapse'``,
``reason='model_refusal'`` — and the deterministic channels continue without us. There
is no code path here that turns a refusal into "no links found".
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from mainline_agentkit import UntrustedText, quarantined_call, silence_row_for_refusal

from .profile import BLAME_LINK
from .types import ClauseCandidate
from .verify import verify_links

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from datetime import datetime

    from mainline_agentkit import (
        AgentkitSettings,
        ModelRefused,
        SilenceRow,
        Transport,
        Validated,
    )

    from .profile import BlameLinkProposal
    from .types import EventRow
    from .verify import VerifiedBlame

__all__ = [
    "BLAME_SILENCE_SOURCE",
    "blame_silence_row",
    "compose_untrusted",
    "mint_candidates",
    "propose_and_verify",
    "propose_blame_links",
    "trusted_context_for",
    "verified_silence_arithmetic",
]

#: ``mainline_meas.silence_ledger.source`` for everything this package declines to link.
BLAME_SILENCE_SOURCE = "blame_lapse"


def mint_candidates(
    clauses: Sequence[tuple[str, str, str]],
) -> tuple[ClauseCandidate, ...]:
    """Label a list of ``(clause_uuid, site_id, canon_text)`` triples ``C1``, ``C2``, ….

    Labels are positional and minted here so that the mapping from label to UUID exists
    only on our side of the call. The model is never shown a UUID and can therefore
    never return one.
    """
    return tuple(
        ClauseCandidate(
            label=f"C{index}",
            clause_uuid=clause_uuid,
            site_id=site_id,
            canon_text=canon_text,
        )
        for index, (clause_uuid, site_id, canon_text) in enumerate(clauses, start=1)
    )


def compose_untrusted(event: EventRow, candidates: Sequence[ClauseCandidate]) -> UntrustedText:
    """Compose the one untrusted block: the incident, then the labelled candidates.

    The event's ``source_sha256`` travels with the block, so a claim made about this
    call can be tied back to an Object-Locked object in S3 without asking us.
    """
    parts = [
        "[INCIDENT]",
        f"kind: {event.kind}",
        f"occurred: {event.occurred_at.date().isoformat()}",
        f"title: {event.title}",
        "narrative:",
        event.narrative,
        "",
        "[CANDIDATE CLAUSES]",
    ]
    for candidate in candidates:
        parts.extend([f"<{candidate.label}>", candidate.canon_text, f"</{candidate.label}>", ""])
    return UntrustedText(
        text="\n".join(parts),
        source_sha256=event.source_sha256,
        media_type="text/plain",
    )


def trusted_context_for(event: EventRow, candidates: Sequence[ClauseCandidate]) -> dict[str, Any]:
    """Build the operator framing: only facts the database gave us.

    ``failed_control_classes`` is the join key and the anchor gazetteer at once. The
    verifier refuses any ``control_class`` outside this list, so an injected instruction
    inside the untrusted block cannot invent a barrier the ICAM record does not contain.
    """
    return {
        "task": "blame_link",
        "site_id": event.site_id,
        "event_id": event.event_id,
        "event_kind": event.kind,
        "failed_control_classes": sorted(set(event.control_classes)),
        "candidate_labels": [candidate.label for candidate in candidates],
        "storage_law": (
            "every link you propose is stored with basis=inferred_semantic and "
            "state=provisional; it cannot block a permit and cannot raise a severity"
        ),
    }


def propose_blame_links(
    event: EventRow,
    candidates: Sequence[ClauseCandidate],
    *,
    transport: Transport | None = None,
    model_id: str | None = None,
    settings: AgentkitSettings | None = None,
) -> Validated[BlameLinkProposal]:
    """Issue one zero-tool blame-link call and return the schema-valid proposal.

    Raises:
        ValueError: no candidates were offered, so there is nothing to propose about.
        ModelRefused: the model declined. Build a silence row with
            :func:`blame_silence_row`; do not treat it as "no links".
        TruncatedResponse: ``max_tokens`` was hit — a silently short list of precursors.
        DeadLettered: the schema violation survived its one retry.
    """
    if not candidates:
        raise ValueError(
            "propose_blame_links was given no candidate clauses. An empty candidate set is a "
            "recall failure upstream, not an abstention here."
        )
    return quarantined_call(
        BLAME_LINK,
        compose_untrusted(event, candidates),
        trusted_context_for(event, candidates),
        transport=transport,
        model_id=model_id,
        settings=settings,
    )


def propose_and_verify(
    event: EventRow,
    candidates: Sequence[ClauseCandidate],
    *,
    commit_id: str,
    provisional_until: datetime,
    transport: Transport | None = None,
    model_id: str | None = None,
    settings: AgentkitSettings | None = None,
    evidence_doc_id: str | None = None,
) -> tuple[VerifiedBlame, Validated[BlameLinkProposal]]:
    """Propose, then verify. The pair is returned so the caller can ledger both halves.

    The second element carries the replayability quad (§8.2) that
    ``agent_action_provenance`` needs; the first carries the rows and the drops. A caller
    that writes one without the other has recorded either an unexplained row or an
    unattributed refusal.
    """
    validated = propose_blame_links(
        event,
        candidates,
        transport=transport,
        model_id=model_id,
        settings=settings,
    )
    verified = verify_links(
        validated.value,
        event=event,
        candidates=candidates,
        commit_id=commit_id,
        model_id=validated.model_id,
        prompt_version=validated.prompt_version,
        provisional_until=provisional_until,
        provenance=validated.provenance(),
        evidence_doc_id=evidence_doc_id,
    )
    return verified, validated


def blame_silence_row(
    refusal: ModelRefused,
    *,
    event: EventRow,
    input_sha256: str,
    model_id: str,
    inference_profile_arn: str,
) -> SilenceRow:
    """Build the ``silence_ledger`` row for a refused blame-link call.

    ``severity`` is the event's own ``severity_gate`` — the severity of *what we failed
    to reason about*, not a severity we assigned. That is what makes the ledger legible:
    a refusal over a fatality and a refusal over a near-miss must not sort together.
    """
    return silence_row_for_refusal(
        refusal,
        site_id=event.site_id,
        source=BLAME_SILENCE_SOURCE,
        subject_kind="event",
        subject_id=event.event_id,
        severity=event.severity_gate,
        profile_id=BLAME_LINK.profile_id,
        prompt_version=BLAME_LINK.prompt_version,
        model_id=model_id,
        inference_profile_arn=inference_profile_arn,
        input_sha256=input_sha256,
    )


def verified_silence_arithmetic(verified: VerifiedBlame) -> Mapping[str, Any]:
    """Expose the verifier's counts for a caller writing an ``abstained`` silence row.

    A call that returned five proposals of which five were dropped is *not* the same
    event as a call that abstained, and neither is the same as a refusal. Three
    distinguishable rows, three distinguishable causes.
    """
    return verified.arithmetic()
