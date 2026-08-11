# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""``blocking_check.evidence_summary`` — the sentence the rerank was paid for.

This is where the token spend is justified. The listwise judge is the most expensive stage in
the whole recall budget (4 s p50, 20 s p95, ARCHITECTURE 6.6), and it is worth that only
because its output is not a score: it is the *evidence text* the check row needs anyway, in
the operator's own vocabulary, naming the mechanism and the precondition. Bedrock Rerank
would have returned a float; a float would still have left somebody to write this sentence.

The one rule this module enforces is that the sentence **cannot exist without the citation**.
:func:`evidence_summary` refuses to render a verdict that does not name both a mechanism and
a precondition. There is no fallback string, no "related incident" template, and no path by
which a blocking check acquires a plausible-sounding summary that no model actually stood
behind. If the citation is absent the candidate is not relevant, and a candidate that is not
relevant has no blocking check to summarise.

Suppressed siblings are named in the summary rather than hidden by it. MMR collapsed them
into this representative; the supervisor is told how many there were and which, because *one
of six* and *one alone* are different facts about a plant.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

from mainline_recall_agent.providers.errors import ProviderError
from mainline_recall_agent.rerank.schema import RerankedCandidate

__all__ = [
    "MAX_EVIDENCE_CHARS",
    "MAX_SIBLINGS_NAMED",
    "EvidenceRefused",
    "evidence_summary",
]

MAX_EVIDENCE_CHARS: Final[int] = 1200
"""Bound on the rendered summary. Long enough for two citations, a justification and a
sibling list; short enough that a supervisor reads it rather than scrolls past it."""

MAX_SIBLINGS_NAMED: Final[int] = 5
"""Siblings named inline. The count is always exact; beyond this the remainder is reported
as a number, and the full list is on the check's ``also_matched`` and in the ledger."""


class EvidenceRefused(ProviderError):
    """A blocking check was about to be summarised from a verdict that cites nothing.

    A defect, not silence: reaching here means an admission decision was made on a verdict
    the citation rule should already have demoted.
    """


def evidence_summary(verdict: RerankedCandidate, *, also_matched: Sequence[str] = ()) -> str:
    """Render the evidence text for one blocking check.

    Args:
        verdict: A reranked candidate that survived the citation rule.
        also_matched: Event identities MMR collapsed into this representative.

    Raises:
        EvidenceRefused: if the verdict is not relevant, was demoted, or does not name both
            a shared mechanism and a shared precondition.
    """
    if verdict.relevance != "relevant":
        raise EvidenceRefused(
            "refusing to write evidence for a candidate the judge did not find relevant; a "
            "blocking check needs a claim behind it",
            doc_id=verdict.doc_id,
            relevance=verdict.relevance,
        )
    if verdict.demoted:
        raise EvidenceRefused(
            "refusing to write evidence for a demoted verdict",
            doc_id=verdict.doc_id,
            demotion_reason=verdict.demotion_reason,
        )
    if not verdict.cites_mechanism_and_precondition:
        raise EvidenceRefused(
            "the verdict does not name both a shared mechanism and a shared precondition. "
            "There is no fallback summary: a blocking check whose evidence text nobody stood "
            "behind is worse than no check at all.",
            doc_id=verdict.doc_id,
        )

    parts = [
        f"Shared mechanism: {verdict.shared_mechanism.strip().rstrip('.')}.",
        f"Shared precondition: {verdict.shared_precondition.strip().rstrip('.')}.",
        verdict.justification.strip(),
    ]
    siblings = tuple(also_matched)
    if siblings:
        named = ", ".join(siblings[:MAX_SIBLINGS_NAMED])
        remainder = len(siblings) - min(len(siblings), MAX_SIBLINGS_NAMED)
        tail = f" and {remainder} more" if remainder else ""
        plural = "record" if len(siblings) == 1 else "records"
        parts.append(
            f"Also matched {len(siblings)} materially similar {plural} "
            f"({named}{tail}), collapsed into this one for review."
        )
    rendered = " ".join(part for part in parts if part)
    if len(rendered) > MAX_EVIDENCE_CHARS:
        # Trimmed at a word boundary and marked, never silently cut mid-clause: a summary
        # that stops halfway through a precondition reads as a different precondition.
        cut = rendered[: MAX_EVIDENCE_CHARS - 12].rsplit(" ", 1)[0]
        return f"{cut} [truncated]"
    return rendered
