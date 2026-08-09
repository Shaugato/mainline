# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""P5 — silence is a record.  Every neutral and every abstention, with its arithmetic.

The plaintiff's question is never *"why did you block?"*.  It is *"your system
looked at this edit and said nothing — why?"*.  Without a row the answer is
silence plus an adverse inference.  With one:

    *it resolved neutral because the lattice found no rule violated and the
    model concurred at confidence 0.90 against a threshold of 0.75, under
    resolution table ``ratchet.v1`` (sha256 4f2a…) and identity policy
    ``identity-policy-v1`` (sha256 9c11…), on model ``au.anthropic.claude-opus-5``
    at prompt version ``adjudication.v1+rubric.v1``.*

This module builds that row.  It **never writes it**: the record is inserted by
the caller, in the same transaction as the decision it accompanies (P5), through
the SQL role that holds ``INSERT`` on ``mainline_meas.silence_ledger``.  This
package holds no driver and no credential.

**The two vocabularies are the database's, not ours.**  ``source`` and
``reason`` are the exact ``CHECK`` lists in ARCHITECTURE.md §5.7, re-stated here
and enforced in ``__post_init__``, so a row that the database would refuse
cannot be constructed in Python either.  ``delta_neutral`` is the only ``source``
value this module ever uses; a resolution is not a recall, a dedup or a patrol
suppression.

**severity is a projection, never an input** (P2).  ``max_ancestral_severity``
is read by the caller from ``clause_blame_closure`` and passed in.  Nothing here
derives it, guesses it, or defaults it — a silence row claiming severity 0 over
blood-written ancestry is worse than no row at all.

**What does not get a row.**  A resolution that ends in ``weaken`` or ``remove``
is not silence: something was said, loudly, and the delta row itself says it.
The one case that reads like an omission and is not — Path A said ``weaken``,
the model said "nothing here", and the ratchet ignored the model — is recorded
where it belongs, in ``mainline_meas.agent_action``, which records every model
call whatever it returned.  Duplicating it here would make the silence ledger a
log of things that were *not* silenced.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Final

from ..contracts import force

if TYPE_CHECKING:
    from collections.abc import Mapping
    from uuid import UUID

    from .resolve import Resolution

__all__ = [
    "ABSTENTION_CODES",
    "REASON_FOR_ABSTENTION_CODE",
    "SILENCE_REASONS",
    "SILENCE_SOURCES",
    "SilenceRecord",
    "abstention_code_of",
    "requires_silence_record",
    "silence_record",
    "stamp_rationale",
]

#: ``mainline_meas.silence_ledger.source`` CHECK vocabulary (ARCHITECTURE.md §5.7).
SILENCE_SOURCES: Final[frozenset[str]] = frozenset(
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

#: ``mainline_meas.silence_ledger.reason`` CHECK vocabulary (ARCHITECTURE.md §5.7).
SILENCE_REASONS: Final[frozenset[str]] = frozenset(
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

#: The one source a delta resolution ever writes under.
DELTA_SOURCE: Final[str] = "delta_neutral"

#: Why Path B produced no usable answer.
#:
#: This vocabulary is declared **here**, in the domain, and imported by
#: ``mainline_delta_oracle`` — never the other way round.  The domain may not
#: import the package that reaches a model (decision D1), so the shared word list
#: has to live on this side of the boundary.  Adding a code is a change to the
#: silence ledger's meaning and belongs in a commit that says so.
ABSTENTION_CODES: Final[frozenset[str]] = frozenset(
    {
        "model_abstained",  # the model said "I cannot tell" — the honest case
        "model_refusal",  # stop_reason='refusal' on a cyanide/H2S/explosives corpus
        "guardrail_intervention",  # Bedrock Guardrails blocked the response
        "truncated",  # max_tokens / pause_turn / context window
        "schema_violation",  # invalid JSON, or valid JSON the schema rejects
        "unknown_stop_reason",  # an unmodelled stop reason: fail closed
        "throttled",  # ThrottlingException / TooManyRequests
        "timeout",  # read or connect timeout
        "transport_unavailable",  # no credential, no endpoint, no cassette
        "quote_not_verbatim",  # the supporting quote is not in the descendant text
        "unsupported_numeric_claim",  # 'entails' + numeric disagreement + no number quoted
        "not_run",  # Path B was never invoked for this pair
    }
)

#: Which ``silence_ledger.reason`` each abstention code becomes.
#:
#: Three codes map to ``unreachable`` rather than ``abstained`` on purpose: a
#: throttle, a timeout and a missing transport are statements about *our*
#: deployment, and folding them into ``abstained`` would let an outage present as
#: a model that could not decide.
REASON_FOR_ABSTENTION_CODE: Final[Mapping[str, str]] = {
    "model_abstained": "abstained",
    "model_refusal": "model_refusal",
    "guardrail_intervention": "model_refusal",
    "truncated": "truncated",
    "schema_violation": "abstained",
    "unknown_stop_reason": "abstained",
    "throttled": "unreachable",
    "timeout": "unreachable",
    "transport_unavailable": "unreachable",
    "quote_not_verbatim": "abstained",
    "unsupported_numeric_claim": "abstained",
    "not_run": "unreachable",
}

_RATIONALE_SEPARATOR: Final[str] = ": "

#: The coded severity scale (ARCHITECTURE.md §8.4).  Named so that the bound in
#: the comparison and the bound in the refusal message are one fact.
_MAX_CODED_SEVERITY: Final[int] = 5


def stamp_rationale(code: str, detail: str) -> str:
    """Render an ``OracleVerdict.rationale`` that carries a machine-readable code.

    ``OracleVerdict`` is frozen by worker W1 and has no code field, so the code
    travels in the first token of ``rationale``.  That is a convention, and a
    convention needs one owner: this function and :func:`abstention_code_of` are
    it, and both sides of the boundary use them.

    Raises:
        ValueError: on a code outside :data:`ABSTENTION_CODES`.
    """
    if code not in ABSTENTION_CODES:
        raise ValueError(f"{code!r} is not an abstention code; known: {sorted(ABSTENTION_CODES)}")
    return f"{code}{_RATIONALE_SEPARATOR}{detail}"


def abstention_code_of(rationale: str | None) -> str | None:
    """Recover the abstention code from a stamped rationale, or ``None``.

    Returns ``None`` for an unstamped rationale rather than guessing: an
    unrecognised prefix means the verdict came from a producer this vocabulary
    does not describe, and inventing a code for it would put a word into the
    ledger that nothing in the system means.
    """
    if not rationale:
        return None
    head = rationale.split(_RATIONALE_SEPARATOR, 1)[0].strip()
    return head if head in ABSTENTION_CODES else None


@dataclass(frozen=True, slots=True)
class SilenceRecord:
    """One ``mainline_meas.silence_ledger`` row, built and never written here."""

    site_id: str
    source: str
    reason: str
    subject_kind: str
    subject_id: str
    severity: int
    score: float | None
    threshold: float | None
    arithmetic: Mapping[str, Any]
    policy_version: str | None
    at: datetime

    def __post_init__(self) -> None:
        """Enforce both database CHECK vocabularies and the severity range."""
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
        if not 0 <= self.severity <= _MAX_CODED_SEVERITY:
            raise ValueError(
                f"severity {self.severity} is outside 0..5; it is a projection of "
                f"clause_blame_closure (P2) and this package never derives it"
            )
        if self.at.tzinfo is None:
            raise ValueError(
                "a naive datetime in an evidentiary payload is an unanswerable "
                "question in cross-examination"
            )

    def to_mapping(self) -> dict[str, Any]:
        """Column-name-keyed form for the caller's own parameterised INSERT."""
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


def requires_silence_record(resolution: Resolution) -> bool:
    """Whether this resolution is one of the two P5 obligations.

    ``True`` for every zero-force resolution (the system asserted that nothing
    was weakened) and for every abstention, including the below-theta case and
    the case where Path B never ran.  ``False`` for a ``weaken`` or ``remove``
    that the lattice or the model actually found — that is not silence.
    """
    return force(resolution.verdict.delta) == 0 or resolution.cell.rule in (
        "ABSTENTION_FLOOR",
        "NEUTRAL_UNCONFIRMED",
    )


def _reason_for(resolution: Resolution) -> str:
    if resolution.cell.rule == "NEUTRAL_UNCONFIRMED":
        # The two paths did not agree and the model was not confident enough for
        # the disagreement to be resolved in its favour. That is a threshold
        # comparison, and `below_tau` is the word the ledger has for one.
        return "below_tau"
    if resolution.cell.rule == "ABSTENTION_FLOOR":
        if not resolution.oracle_present:
            return REASON_FOR_ABSTENTION_CODE["not_run"]
        code = abstention_code_of(resolution.oracle_rationale)
        return REASON_FOR_ABSTENTION_CODE[code] if code else "abstained"
    return "bounded_negative"


def silence_record(
    resolution: Resolution,
    *,
    site_id: UUID | str,
    subject_id: UUID | str,
    max_ancestral_severity: int,
    policy_version: str,
    policy_sha256: str | None = None,
    subject_kind: str = "clause_version",
    at: datetime | None = None,
) -> SilenceRecord:
    """Build the ledger row for a neutral or an abstention.

    Args:
        resolution: the result of :func:`mainline_domain.resolution.resolve.explain`.
        site_id: the tenant.
        subject_id: the ``clause_version`` the resolution was about.
        max_ancestral_severity: **projected** from ``clause_blame_closure`` by the
            caller (P2).  Never derived here.
        policy_version: the ``identity_policy`` version theta was read from.
        policy_sha256: the content hash of those exact bytes (decision D11).
            Optional only because a caller may hold theta from a source that has
            no file; when it is known, pass it — it is what makes retro-tuning
            visible.
        subject_kind: defaults to ``clause_version``.
        at: injected by tests; otherwise a timezone-aware now.

    Returns:
        The row, ready for a parameterised INSERT.

    Raises:
        ValueError: when the resolution is not one this ledger records — see
            :func:`requires_silence_record`.  Writing a "silence" row for a
            weakening would corrupt the one artefact whose value is that it lists
            exactly the warnings that were not given.
    """
    if not requires_silence_record(resolution):
        raise ValueError(
            f"resolution {resolution.verdict.delta.value} via {resolution.cell.rule} is "
            f"not silence: the gate was made louder, not quieter. The silence ledger is "
            f"a complete list of the warnings that were NOT given, and a row here for a "
            f"weakening makes that list useless."
        )
    witnesses = [
        {
            "rule_id": witness.rule_id,
            "field": witness.field,
            "from": witness.from_repr,
            "to": witness.to_repr,
            "note": witness.note,
        }
        for witness in resolution.path_a_witnesses
    ]
    arithmetic: dict[str, Any] = {
        "path_a_delta": resolution.path_a_delta.value,
        "oracle_label": (
            resolution.oracle_label.value if resolution.oracle_label is not None else None
        ),
        "oracle_abstained": resolution.abstained,
        "oracle_present": resolution.oracle_present,
        "abstention_code": (
            abstention_code_of(resolution.oracle_rationale)
            if resolution.oracle_present
            else "not_run"
        ),
        "confidence": resolution.oracle_confidence,
        "theta": resolution.theta,
        "confident": resolution.confident,
        "resolved_delta": resolution.verdict.delta.value,
        "delta_basis": resolution.verdict.basis,
        "resolution_rule": resolution.cell.rule,
        "resolution_table_version": resolution.table_version,
        "resolution_table_sha256": resolution.table_sha256,
        "model_id": resolution.oracle_model_id,
        "prompt_version": resolution.oracle_prompt_version,
        "policy_sha256": policy_sha256,
        "witnesses": witnesses,
    }
    return SilenceRecord(
        site_id=str(site_id),
        source=DELTA_SOURCE,
        reason=_reason_for(resolution),
        subject_kind=subject_kind,
        subject_id=str(subject_id),
        severity=max_ancestral_severity,
        score=resolution.oracle_confidence,
        threshold=resolution.theta,
        arithmetic=arithmetic,
        policy_version=policy_version,
        at=at if at is not None else datetime.now(tz=UTC),
    )
