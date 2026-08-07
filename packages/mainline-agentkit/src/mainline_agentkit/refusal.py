# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Refusal is silence, and silence is a row.

Decision A8, and the sentence underneath it: **a precursor the model declined to
summarise must still block the merge.** Our corpus is cyanide leaching, hydrogen
sulfide, explosives and confined-space chemistry, so ``stop_reason: "refusal"`` on a
perfectly clean document is expected traffic, not an incident.

Three rules, all of them structural rather than procedural:

1. **``stop_reason`` is checked before ``content`` is touched.** :func:`interpret` is
   the only function in this package that reads a response, and the caller cannot
   reach content without going through it. A refusal whose content block was parsed
   first is a refusal that has already leaked into a candidate set.
2. **Branch on ``stop_reason`` only.** ``stop_details`` may be ``null``, so a code path
   that reaches into it to decide the category is a code path that raises
   ``AttributeError`` on the day the model refuses.
3. **An unrecognised stop reason is a refusal.** :class:`UnknownStopReason` is raised
   rather than defaulting to success. A future model generation adding a stop reason
   we silently treat as "fine" is precisely how a memory gap opens without anyone
   noticing.

The output is a :class:`SilenceRow`, whose fields are the columns of
``mainline_meas.silence_ledger`` (ARCHITECTURE.md §5.7) with its two ``CHECK``
vocabularies enforced here as well, so a row that would be rejected by the database is
rejected before it is built. This package holds **no database credential and no
driver** — it builds the row and hands it to the caller, which is what keeps the
Cognition plane unable to write anything the gate reads.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from .errors import ModelRefused, TruncatedResponse, UnknownStopReason

if TYPE_CHECKING:
    from collections.abc import Mapping

    from .transport import ModelResponse

__all__ = [
    "KNOWN_STOP_REASONS",
    "SILENCE_REASONS",
    "SILENCE_SOURCES",
    "Outcome",
    "SilenceRow",
    "classify",
    "guardrail_intervened",
    "interpret",
    "silence_row_for_refusal",
]


class Outcome(StrEnum):
    """What a ``stop_reason`` means for the call that produced it."""

    OK = "ok"
    TRUNCATED = "truncated"
    REFUSED = "refused"


#: Every ``stop_reason`` this package recognises on the Anthropic native body.
#: Anything outside this set raises :class:`UnknownStopReason` — see rule 3 above.
KNOWN_STOP_REASONS: Mapping[str, Outcome] = {
    "end_turn": Outcome.OK,
    "stop_sequence": Outcome.OK,
    "tool_use": Outcome.OK,
    "pause_turn": Outcome.TRUNCATED,
    "max_tokens": Outcome.TRUNCATED,
    "model_context_window_exceeded": Outcome.TRUNCATED,
    "refusal": Outcome.REFUSED,
}

#: ``mainline_meas.silence_ledger.source`` CHECK vocabulary, ARCHITECTURE.md §5.7.
SILENCE_SOURCES: frozenset[str] = frozenset(
    {
        "recall",
        "fleet_appraisal",
        "severity_downgrade",
        "closure_truncation",
        "dedup",
        "delta_neutral",
        "blame_lapse",
        "patrol_suppression",
        "ring_exclusion",
        "boundary_unmodelled",
    }
)

#: ``mainline_meas.silence_ledger.reason`` CHECK vocabulary, ARCHITECTURE.md §5.7.
SILENCE_REASONS: frozenset[str] = frozenset(
    {
        "below_tau",
        "model_refusal",
        "dedup_sibling",
        "cap_exceeded",
        "truncated",
        "abstained",
        "bounded_negative",
        "unreachable",
    }
)

#: Bedrock reports a Guardrail intervention out of band from ``stop_reason``.
#: **Unverified on this account** as of 2026-08-07 (no valid AWS credentials): the key
#: name is taken from the Bedrock InvokeModel response contract, and the behaviour is
#: covered by a cassette rather than a live observation. Treated as a refusal either
#: way, because a guardrail that fires and is then ignored is not a guardrail.
GUARDRAIL_ACTION_KEY = "amazon-bedrock-guardrailAction"
GUARDRAIL_INTERVENED = "INTERVENED"


def classify(stop_reason: str | None) -> Outcome:
    """Map a ``stop_reason`` to an :class:`Outcome`.

    Raises:
        UnknownStopReason: for ``None`` or any value outside
            :data:`KNOWN_STOP_REASONS`.
    """
    if stop_reason is None or stop_reason not in KNOWN_STOP_REASONS:
        raise UnknownStopReason(stop_reason, tuple(KNOWN_STOP_REASONS))
    return KNOWN_STOP_REASONS[stop_reason]


def guardrail_intervened(raw: Mapping[str, Any]) -> bool:
    """Whether a Bedrock Guardrail blocked this response."""
    return raw.get(GUARDRAIL_ACTION_KEY) == GUARDRAIL_INTERVENED


def interpret(response: ModelResponse, *, max_tokens: int) -> Outcome:
    """Decide what a response is **before** any caller touches its content.

    Args:
        response: the parsed response.
        max_tokens: the profile's committed budget, reported in the truncation
            refusal so the operator sees the number that was breached.

    Returns:
        :attr:`Outcome.OK` — the only value a caller may proceed on.

    Raises:
        ModelRefused: on ``stop_reason == "refusal"`` or a Guardrail intervention.
        TruncatedResponse: on ``max_tokens``, ``pause_turn`` or a context-window
            overflow. Decision A5 makes this fatal: ``max_tokens`` caps thinking plus
            text, so a truncated structured output is either invalid JSON or — worse —
            valid and short.
        UnknownStopReason: on anything unrecognised.
    """
    if guardrail_intervened(response.raw):
        raise ModelRefused(
            category="guardrail_intervention",
            stop_reason=response.stop_reason,
            detail="Bedrock Guardrails blocked the response",
        )
    outcome = classify(response.stop_reason)
    if outcome is Outcome.REFUSED:
        raise ModelRefused(category="model_refusal", stop_reason=response.stop_reason)
    if outcome is Outcome.TRUNCATED:
        raise TruncatedResponse(
            stop_reason=str(response.stop_reason),
            max_tokens=max_tokens,
            output_tokens=response.usage.output_tokens,
        )
    return outcome


@dataclass(frozen=True, slots=True)
class SilenceRow:
    """One ``mainline_meas.silence_ledger`` row, built but never written by this package.

    The Cognition plane holds ``INSERT`` on ``silence_*`` through its own SQL role.
    Agentkit constructs the row and returns it; it holds no driver and no credential,
    which is the property ``mainline-boundary``'s E3 scan asserts by SBOM.
    """

    site_id: str
    source: str
    reason: str
    subject_kind: str
    subject_id: str
    severity: int
    arithmetic: Mapping[str, Any]
    score: float | None = None
    threshold: float | None = None
    policy_version: str | None = None
    #: Left ``None`` by callers; :meth:`__post_init__` stamps a timezone-aware now.
    #: A naive datetime in an evidentiary payload is an unanswerable question in
    #: cross-examination, so there is no code path here that produces one.
    at: datetime | None = None

    def __post_init__(self) -> None:
        """Enforce the two database CHECK vocabularies before the row is ever built."""
        if self.source not in SILENCE_SOURCES:
            raise ValueError(
                f"silence source {self.source!r} is outside the CHECK vocabulary "
                f"{sorted(SILENCE_SOURCES)} (ARCHITECTURE.md §5.7)"
            )
        if self.reason not in SILENCE_REASONS:
            raise ValueError(
                f"silence reason {self.reason!r} is outside the CHECK vocabulary "
                f"{sorted(SILENCE_REASONS)} (ARCHITECTURE.md §5.7)"
            )
        if self.at is None:
            object.__setattr__(self, "at", datetime.now(tz=UTC))

    def to_mapping(self) -> dict[str, Any]:
        """Column-name-keyed form, ready for the caller's own parameterised INSERT."""
        return {
            "site_id": self.site_id,
            "source": self.source,
            "reason": self.reason,
            "subject_kind": self.subject_kind,
            "subject_id": self.subject_id,
            "severity": self.severity,
            "score": self.score,
            "threshold": self.threshold,
            "arithmetic": dict(self.arithmetic),
            "policy_version": self.policy_version,
            "at": self.at,
        }


def silence_row_for_refusal(
    refusal: ModelRefused,
    *,
    site_id: str,
    source: str,
    subject_kind: str,
    subject_id: str,
    severity: int,
    profile_id: str,
    prompt_version: str,
    model_id: str,
    inference_profile_arn: str,
    input_sha256: str,
    policy_version: str | None = None,
) -> SilenceRow:
    """Turn a :class:`ModelRefused` into the ledger row decision A8 requires.

    ``arithmetic`` carries the replayability quad (§8.2) rather than a score, because
    for a refusal there is no score: the honest content of the field is *which model,
    under which prompt version, on which profile, over which input* declined.
    """
    return SilenceRow(
        site_id=site_id,
        source=source,
        reason="model_refusal",
        subject_kind=subject_kind,
        subject_id=subject_id,
        severity=severity,
        arithmetic={
            "category": refusal.category,
            "stop_reason": refusal.stop_reason,
            "profile_id": profile_id,
            "prompt_version": prompt_version,
            "model_id": model_id,
            "inference_profile_arn": inference_profile_arn,
            "input_sha256": input_sha256,
            "fallback": "deterministic_channel",
        },
        policy_version=policy_version,
    )
