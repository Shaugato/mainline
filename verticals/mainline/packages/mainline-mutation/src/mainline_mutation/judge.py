# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Turn recorded facts into one of six outcomes.  The whole judgement, in one file.

Separating this from :mod:`mainline_mutation.pipeline` is not tidiness.  The
artefact records the facts *and* the outcome, so a reader who disagrees with a
judgement can re-derive their own from the same row — and a judgement that lived
inside the code that produced the facts could be changed without the facts
moving.

KILL — the pipeline must react
------------------------------
``killed``
    ``force(delta) > 0`` (a ``weaken`` or a ``remove``) **or** a residue row.
``survived``
    Neither.  This is a MISSED WEAKENING and it is the number this whole
    package exists to publish.

Why residue counts: ``docs/leads/algorithms.md`` §0's asymmetry is that evading
the matcher produces an orphaned blood-written obligation, which is a *louder*
gate than the weakening it was hiding.  A KILL mutant that makes its clause
unrecognisable has not escaped; it has traded a weaken verdict for a blocking
row.  Counting only the verdict would score that as a miss and would understate
a mechanism the design deliberately relies on.

SURVIVE — the pipeline must not react
-------------------------------------
``preserved``
    Recognised as the ancestor, no weakening, no matcher-manufactured residue.
``identity_changed``
    The cascade did not recover the ancestor at or above a stage accept band,
    or an anchor-shaped residue was raised on a pure reformat.
``false_weaken``
    A weakening verdict on an edit that changed no control.
``identity_changed_and_false_weaken``
    Both.  A separate member rather than a precedence rule, because the two
    failures have different causes and collapsing them would hide one.

``opaque_control`` residue does NOT fail a SURVIVE mutant, and that is a
judgement call recorded here rather than buried.  R-A3 declares over-blocking on
opaque clauses a product characteristic: an edit to a clause the extractor
cannot read defaults to ``weaken`` deliberately.  A harness that scored that
deliberate over-block as a false positive would be measuring the design's stated
position rather than a defect in it.  It is still recorded on the row, so a
reader who takes the other view can recount.
"""

from __future__ import annotations

from typing import Final

from .model import KILL, MutationKind, Outcome, PipelineOutcome

__all__ = ["MATCHER_RESIDUE", "judge"]

#: Residue reasons that mean *the matcher manufactured a blocking row*.  These
#: fail a SURVIVE mutant.  ``opaque_control`` is deliberately absent; see the
#: module docstring.
MATCHER_RESIDUE: Final[frozenset[str]] = frozenset(
    {"unmatched", "ambiguous", "anchor_drop", "citation_unresolved"}
)


# PLR0911: the seven returns ARE the outcome vocabulary made visible. Each one is
# one reviewable cell of the judgement and produces a different sentence in the
# published artefact; folding them into an accumulator would hide which cell
# decided, which is the whole thing a reader recounts from.
def judge(kind: MutationKind, outcome: PipelineOutcome) -> tuple[Outcome, str]:  # noqa: PLR0911
    """Return ``(outcome, reason)`` for one mutant.  The reason is printed verbatim."""
    reacted_delta = outcome.delta_force > 0
    residue = tuple(outcome.residue_reasons)
    matcher_residue = tuple(r for r in residue if r in MATCHER_RESIDUE)

    if kind == KILL:
        if reacted_delta:
            witnesses = ", ".join(outcome.witness_rule_ids) or "(none recorded)"
            return "killed", (f"the lattice returned {outcome.delta} on witnesses [{witnesses}]")
        if residue:
            return "killed", (
                f"the lattice returned {outcome.delta}, and the identity machinery raised "
                f"{list(residue)}"
            )
        return "survived", (
            f"the lattice returned {outcome.delta} and no residue was raised: this control "
            "mutation reached the gate undetected"
        )

    if reacted_delta and matcher_residue:
        return "identity_changed_and_false_weaken", (
            f"a reformat produced {outcome.delta} on [{', '.join(outcome.witness_rule_ids)}] "
            f"AND matcher residue {list(matcher_residue)}"
        )
    if reacted_delta:
        return "false_weaken", (
            f"a reformat produced {outcome.delta} on "
            f"[{', '.join(outcome.witness_rule_ids)}]: a manufactured blocking row"
        )
    if matcher_residue:
        return "identity_changed", (
            f"a reformat was not recognised as its own ancestor: {list(matcher_residue)}"
        )
    note = f" (opaque_control recorded and not counted: {list(residue)})" if residue else ""
    stage = outcome.match_stage or "no stage"
    return "preserved", (
        f"recognised as the ancestor at {stage} and the verdict was {outcome.delta}{note}"
    )
