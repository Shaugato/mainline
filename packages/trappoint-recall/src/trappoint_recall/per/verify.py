# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The standalone PER verifier.

Two modes, because two different people check this artefact.

**Boundary mode** — the receipt alone. This is what an opposing expert, a regulator or an
insurer gets: ``(candidate_root, theta, s, n)`` and the two boundary leaves with their audit
paths. It establishes that the cut is where the receipt says it is, against a root that was
committed before the dispute existed, and it discloses nothing about the suppressed set.

**Full mode** — the receipt plus the disclosed candidate rows (``mainline_meas.
recall_candidate``, which is what a discovery order produces). This recomputes the root from
scratch, so removing, adding or editing a single candidate is caught, and re-derives ``s``
from the scores rather than believing the receipt's arithmetic.

Every check reports rather than raises. A verifier that crashed on a hostile bundle would be
telling the person holding it nothing, and "the receipt is malformed" is itself a finding.
The single exception is a receipt so broken it cannot be parsed into a shape with fields —
that is reported as the first failed check and verification stops.

Dependencies: the standard library. No ``pydantic``, no ``cryptography``, no package outside
this subpackage. See :mod:`trappoint_recall.per.canon` for why that is a requirement rather
than a preference.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from trappoint_recall.per.errors import PerRefused
from trappoint_recall.per.leaf import (
    RAISED_OUTCOMES,
    CandidateScore,
    Leaf,
    leaf_hash,
    leaves_from_candidates,
)
from trappoint_recall.per.merkle import merkle_root, verify_audit_path
from trappoint_recall.per.receipt import (
    PER_BOUND_SENTENCE,
    BoundaryLeaf,
    SilenceReceipt,
    derive_theta_q,
)

__all__ = [
    "Check",
    "VerificationReport",
    "leaves_from_disclosure",
    "verify_receipt",
]


@dataclass(frozen=True, slots=True)
class Check:
    """One named verification step and what it found."""

    name: str
    ok: bool
    detail: str

    def to_json(self) -> dict[str, Any]:
        """Wire form."""
        return {"name": self.name, "ok": self.ok, "detail": self.detail}


@dataclass(frozen=True, slots=True)
class VerificationReport:
    """The outcome of a verification run. ``ok`` is the conjunction of every check."""

    mode: str
    checks: tuple[Check, ...]

    @property
    def ok(self) -> bool:
        """True when every check passed and at least one check ran."""
        return bool(self.checks) and all(check.ok for check in self.checks)

    @property
    def failures(self) -> tuple[Check, ...]:
        """The checks that failed, in the order they ran."""
        return tuple(check for check in self.checks if not check.ok)

    def to_json(self) -> dict[str, Any]:
        """Wire form, suitable for an attestation payload."""
        return {
            "mode": self.mode,
            "ok": self.ok,
            "checks": [check.to_json() for check in self.checks],
            "claim_bound": PER_BOUND_SENTENCE,
        }

    def to_text(self) -> str:
        """Human-readable report. Failures are prefixed ``FAIL`` so a grep finds them."""
        lines = [f"Proof of Exhausted Recall — {self.mode} verification"]
        for check in self.checks:
            lines.append(f"  {'ok  ' if check.ok else 'FAIL'}  {check.name}: {check.detail}")
        lines.append(f"  result: {'PASS' if self.ok else 'FAIL'}")
        lines.append(f"  bound:  {PER_BOUND_SENTENCE}")
        return "\n".join(lines)


def leaves_from_disclosure(entries: Sequence[Mapping[str, Any]]) -> tuple[Leaf, ...]:
    """Turn a disclosed candidate set into a leaf sequence.

    Accepts either shape a discovery order actually produces:

    * **leaf form** — ``{ord, event_id, score_q, tau_applied, outcome}``, taken as given and
      ordered by ``ord`` so that contiguity and sortedness remain *checks* rather than
      something this function quietly repairs; or
    * **row form** — ``{event_id, p_relevant, tau_applied, outcome}``, exactly the columns of
      ``mainline_meas.recall_candidate``, which are sorted and quantised here.

    Raises:
        PerRefused: on a mixed or unrecognised shape, or an unusable field.
    """
    if not entries:
        return ()
    leaf_form = [("score_q" in entry) for entry in entries]
    if all(leaf_form):
        leaves = [Leaf.from_json(entry) for entry in entries]
        return tuple(sorted(leaves, key=lambda leaf: leaf.ord))
    if any(leaf_form):
        raise PerRefused(
            "the disclosed set mixes leaf form (score_q) and row form (p_relevant); a "
            "verifier cannot know which rows were quantised by whom"
        )
    scores = [
        CandidateScore(
            event_id=str(entry["event_id"]),
            p_relevant=float(entry["p_relevant"]),
            tau_applied=float(entry["tau_applied"]),
            outcome=str(entry["outcome"]),
        )
        for entry in entries
    ]
    return leaves_from_candidates(scores)


def _check_boundary_half(
    half: BoundaryLeaf | None,
    *,
    label: str,
    expected_ordinal: int,
    receipt: SilenceReceipt,
    theta_rule: str,
) -> list[Check]:
    """Verify presence, positioning, the theta relation and the inclusion path for one half."""
    exists = 1 <= expected_ordinal <= receipt.n
    if half is None:
        return [
            Check(
                f"boundary_present[{label}]",
                ok=not exists,
                detail=(
                    f"ordinal {expected_ordinal} is outside 1..{receipt.n}, so its absence is "
                    "correct"
                    if not exists
                    else f"ordinal {expected_ordinal} exists in the tree but was not disclosed"
                ),
            )
        ]
    if not exists:
        return [
            Check(
                f"boundary_present[{label}]",
                ok=False,
                detail=(
                    f"a leaf was disclosed for ordinal {expected_ordinal}, which is outside "
                    f"1..{receipt.n}"
                ),
            )
        ]

    checks = [
        Check(
            f"boundary_present[{label}]",
            ok=True,
            detail=f"ordinal {expected_ordinal} disclosed",
        )
    ]
    positioned = half.leaf.ord == expected_ordinal and half.index == expected_ordinal - 1
    checks.append(
        Check(
            f"boundary_position[{label}]",
            ok=positioned,
            detail=(
                f"leaf.ord={half.leaf.ord}, index={half.index}; expected ord="
                f"{expected_ordinal}, index={expected_ordinal - 1}"
            ),
        )
    )

    if theta_rule == "at_or_above":
        holds = half.leaf.score_q >= receipt.theta_q
        detail = f"score_q={half.leaf.score_q} >= theta_q={receipt.theta_q} is {holds}"
    else:
        holds = half.leaf.score_q < receipt.theta_q
        detail = f"score_q={half.leaf.score_q} < theta_q={receipt.theta_q} is {holds}"
    checks.append(Check(f"boundary_theta[{label}]", ok=holds, detail=detail))

    try:
        included = verify_audit_path(
            leaf_hash(half.leaf),
            half.index,
            receipt.n,
            half.path,
            receipt.candidate_root,
        )
        include_detail = (
            f"audit path of {len(half.path)} sibling(s) at index {half.index} in a tree of "
            f"{receipt.n} {'reproduces' if included else 'does not reproduce'} candidate_root"
        )
    except PerRefused as exc:
        included = False
        include_detail = str(exc)
    checks.append(Check(f"inclusion[{label}]", ok=included, detail=include_detail))
    return checks


def _boundary_checks(receipt: SilenceReceipt) -> list[Check]:
    """Everything provable from the receipt alone."""
    checks = [
        Check(
            "boundary_sane",
            ok=0 <= receipt.s <= receipt.n,
            detail=f"s={receipt.s}, n={receipt.n}",
        ),
        Check(
            "theta_consistent",
            ok=abs(receipt.theta - receipt.theta_q / 1_000_000) < 1e-9,
            detail=(
                f"theta={receipt.theta!r} agrees with theta_q={receipt.theta_q} to within "
                "1e-9; theta_q is the authoritative integer"
            ),
        ),
    ]
    checks.extend(
        _check_boundary_half(
            receipt.boundary.at_s,
            label="s",
            expected_ordinal=receipt.s,
            receipt=receipt,
            theta_rule="at_or_above",
        )
    )
    checks.extend(
        _check_boundary_half(
            receipt.boundary.at_s_plus_1,
            label="s+1",
            expected_ordinal=receipt.s + 1,
            receipt=receipt,
            theta_rule="below",
        )
    )
    claim_ok = receipt.certificate_verdict != "UNDETERMINED" or receipt.not_exhaustive
    checks.append(
        Check(
            "exhaustion_claim_bounded",
            ok=claim_ok,
            detail=(
                f"coverage verdict {receipt.certificate_verdict!r}, "
                f"not_exhaustive={receipt.not_exhaustive}. "
                + PER_BOUND_SENTENCE
            ),
        )
    )
    return checks


def _full_checks(receipt: SilenceReceipt, leaves: Sequence[Leaf]) -> list[Check]:
    """Everything that additionally needs the disclosed candidate set."""
    checks = [
        Check(
            "leaf_count",
            ok=len(leaves) == receipt.n,
            detail=f"disclosed {len(leaves)} candidate(s); receipt commits to n={receipt.n}",
        )
    ]

    ordinals_ok = all(leaf.ord == position for position, leaf in enumerate(leaves, start=1))
    checks.append(
        Check(
            "ordinals_contiguous",
            ok=ordinals_ok,
            detail=(
                "ordinals are 1..n contiguous"
                if ordinals_ok
                else "ordinals are not 1..n contiguous — a candidate was removed or reordered"
            ),
        )
    )

    sorted_ok = all(
        (-left.score_q, left.event_id) <= (-right.score_q, right.event_id)
        for left, right in zip(leaves, leaves[1:], strict=False)
    )
    checks.append(
        Check(
            "commitment_order",
            ok=sorted_ok,
            detail=(
                "score descending, event_id ascending"
                if sorted_ok
                else "the disclosed set is not score-sorted, so the boundary proves nothing"
            ),
        )
    )

    unique_ok = len({leaf.event_id for leaf in leaves}) == len(leaves)
    checks.append(
        Check(
            "candidates_distinct",
            ok=unique_ok,
            detail=(
                "every event_id appears once"
                if unique_ok
                else "an event_id appears twice; recall_candidate is keyed (run_id, event_id)"
            ),
        )
    )

    recomputed = merkle_root([leaf_hash(leaf) for leaf in leaves])
    checks.append(
        Check(
            "root_matches",
            ok=recomputed == receipt.candidate_root,
            detail=(
                f"recomputed {recomputed.hex()}; committed {receipt.candidate_root.hex()}"
            ),
        )
    )

    derived_s = sum(1 for leaf in leaves if leaf.score_q >= receipt.theta_q)
    checks.append(
        Check(
            "cut_position",
            ok=derived_s == receipt.s,
            detail=(
                f"{derived_s} leaf/leaves score at or above theta_q={receipt.theta_q}; "
                f"receipt claims s={receipt.s}"
            ),
        )
    )

    beyond = [
        leaf.ord for leaf in leaves if leaf.outcome in RAISED_OUTCOMES and leaf.ord > receipt.s
    ]
    checks.append(
        Check(
            "nothing_raised_beyond_s",
            ok=not beyond,
            detail=(
                "no blocking or advisory candidate lies past the cut"
                if not beyond
                else f"raised candidates at ordinals {beyond} lie past s={receipt.s}"
            ),
        )
    )

    implied = derive_theta_q(leaves)
    checks.append(
        Check(
            "theta_is_lowest_raised",
            ok=implied == receipt.theta_q,
            detail=(
                f"the lowest score actually shown to a human is {implied}; receipt "
                f"declares theta_q={receipt.theta_q}"
            ),
        )
    )

    disclosed_ok = True
    disclosed_detail = "boundary leaves agree with the disclosed set"
    for half, ordinal in (
        (receipt.boundary.at_s, receipt.s),
        (receipt.boundary.at_s_plus_1, receipt.s + 1),
    ):
        if half is None:
            continue
        if not 1 <= ordinal <= len(leaves) or leaves[ordinal - 1] != half.leaf:
            disclosed_ok = False
            disclosed_detail = (
                f"the leaf disclosed at ordinal {ordinal} is not the one in the disclosed set"
            )
            break
    checks.append(Check("boundary_matches_set", ok=disclosed_ok, detail=disclosed_detail))
    return checks


def verify_receipt(
    document: Mapping[str, Any],
    candidates: Sequence[Mapping[str, Any]] | None = None,
) -> VerificationReport:
    """Verify a silence receipt, optionally against the disclosed candidate set.

    Args:
        document: the receipt's wire form (``SilenceReceipt.to_json()``).
        candidates: the disclosed candidate rows or leaves. When ``None``, boundary mode.

    Returns:
        A report whose ``ok`` is the conjunction of every check. Never raises for a bad
        receipt: a malformed bundle is a finding, not a crash.
    """
    try:
        receipt = SilenceReceipt.from_json(document)
    except PerRefused as exc:
        return VerificationReport(
            mode="boundary" if candidates is None else "full",
            checks=(Check("receipt_parses", ok=False, detail=str(exc)),),
        )

    checks = [Check("receipt_parses", ok=True, detail=f"per_version={receipt.per_version}")]
    checks.extend(_boundary_checks(receipt))
    if candidates is None:
        return VerificationReport(mode="boundary", checks=tuple(checks))

    try:
        leaves = leaves_from_disclosure(candidates)
    except PerRefused as exc:
        checks.append(Check("disclosure_parses", ok=False, detail=str(exc)))
        return VerificationReport(mode="full", checks=tuple(checks))
    checks.append(
        Check("disclosure_parses", ok=True, detail=f"{len(leaves)} candidate(s) disclosed")
    )
    checks.extend(_full_checks(receipt, leaves))
    return VerificationReport(mode="full", checks=tuple(checks))
