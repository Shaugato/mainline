# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""ORIGINDIFF — the delta of record, and the salami-slicing defence.

Decision D7, in one line::

    delta_of_record = join( decide(parent  -> new),
                            decide(origin  -> new) )

where ``origin`` is the blame-origin version resolved by
:mod:`mainline_domain.diachronic.origin` and ``join`` is
:func:`mainline_domain.lattice.order.join` — the maximum along
``introduce ≺ restate ≺ strengthen ≺ weaken ≺ remove``.  Because ``force`` is
monotone along that chain, the delta of record can only ever be *at least as
forceful* as the ordinary parent diff.  Adding the second comparison cannot
quieten a verdict; it can only make one louder.

WHY THIS IS NOT AN ALGEBRA OVER LABELS
--------------------------------------
The tempting implementation is to compose the twenty per-step *labels* — twenty
``restate``s compose to a ``restate``, so define a composition operator that says
otherwise.  That is wrong twice.  It requires inventing an algebra nobody can
audit, and it is unnecessary: the two Control Assertion Tuples are still there.
This module compares ``origin`` and ``new`` **directly**, with the same nine
rules, the same registry and the same minimiser.  There is no new decision
procedure to trust — only a different baseline handed to the one that already
exists, which is exactly the argument ``lattice/decide.py`` makes when it says the
choice of baseline belongs to the caller.

THE ATTACK THIS CLOSES, CONCRETELY
----------------------------------
The lattice has two deliberately silent cells that meet:

* ``r3_comparator`` says nothing about ``=`` ↔ ``<=`` in either direction, because
  "exactly 50 kPa" and "at most 50 kPa" is the commonest *restatement* in a real
  procedure library and firing on it would breach the nuisance ceiling (risk
  R-A7, under which a rule is rejected rather than tuned);
* ``r2_setpoint`` falls silent whenever the comparator **family** changes, because
  a magnitude under ``<=`` and a magnitude under ``=`` are two readings of two
  different assertions and subtracting them would be arithmetic on two questions.

Both are correct in isolation.  Together they leave a corridor: alternate the
comparator between ``= 350 kPa`` and ``<= 357 kPa`` and back, nudging the number
each time, and **every single step is a restatement to the parent diff**.  Twenty
steps later the cap has doubled and no commit was ever a weakening.

Against the blame origin the corridor is not there.  Generation 0 said ``<= 350
kPa`` and generation 20 says ``<= 700 kPa``: same comparator, same family, R2
compares two magnitudes, and the registry has ``max_operating_pressure`` ratified
``lower_is_safer``.  One witness, ``R2_SETPOINT``, and the merge gate has
something to refuse.  ``tests/unit/domain/diachronic/test_red_first_salami.py``
builds exactly that chain and is the test that was red before this module existed.

This is not a hypothetical hole invented to be filled.  It is a *consequence* of
two nuisance-ceiling decisions the lattice worker made on purpose and documented,
and it is the reason the salami defence has to be structural rather than another
rule.  A twenty-first rule closing this particular corridor would leave the
twenty-second corridor open; a different baseline closes all of them at once.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ..contracts import CAT, AnchorSet, ControlDelta, DeltaVerdict, DeltaWitness, force
from ..lattice.decide import LatticeDecision, explain
from ..lattice.order import join, rank
from ..lattice.witness import verdict as build_verdict
from ..registry.model import SafeDirectionRegistry
from .errors import OriginUnresolvedError
from .origin import BlameOrigin

__all__ = [
    "AncestralDelta",
    "Baseline",
    "WitnessRow",
    "delta_of_record",
]

Baseline = Literal["parent", "blame_origin"]
"""Which comparison produced the delta of record.

``parent`` is the incumbent and wins ties.  A tie means both baselines reached the
same rung, and citing the parent then is the honest report: nothing about the
ancestry added to what the ordinary diff already said.
"""


@dataclass(frozen=True, slots=True)
class WitnessRow:
    """One ``mainline.delta_witness`` row, ready to insert, with its ordinal.

    ``minimal`` mirrors the column of the same name in ``0049a_delta_witness.sql``:
    ``True`` for the irreducible reason set behind the delta of record (I14's
    minimal unsatisfiable subset), ``False`` for the witnesses of the comparison
    that *lost*.  The losing set is kept because it is the difference between "the
    parent diff also saw this" and "only the ancestry saw this", and that
    difference is the whole exhibit.
    """

    witness_ord: int
    witness: DeltaWitness
    minimal: bool
    baseline: Baseline


@dataclass(frozen=True, slots=True)
class AncestralDelta:
    """The delta of record for one edit, with both comparisons kept.

    ``verdict`` is what goes on the ``clause_version`` row.  Its witnesses are the
    **winning** comparison's minimal set, because those are the reasons that
    justify the label being stored; :meth:`witness_rows` is what goes into
    ``mainline.delta_witness`` and carries both sets.
    """

    verdict: DeltaVerdict
    baseline: Baseline
    parent_decision: LatticeDecision
    origin_decision: LatticeDecision | None
    blame_origin: BlameOrigin

    @property
    def delta(self) -> ControlDelta:
        """The label of record."""
        return self.verdict.delta

    @property
    def refuses(self) -> bool:
        """``True`` when the merge gate reacts to this label."""
        return force(self.verdict.delta) > 0

    @property
    def salami(self) -> bool:
        """``True`` when the ancestry saw a weakening the parent diff did not.

        The named property of this mechanism, and the thing a demo points at: the
        origin comparison is **strictly** more forceful than the parent one.  A
        chain of individually-neutral edits whose composition weakens sets this
        flag at the step where the composition crosses the line, and at no earlier
        step.
        """
        if self.origin_decision is None:
            return False
        return force(self.origin_decision.verdict.delta) > force(self.parent_decision.verdict.delta)

    def witness_rows(self) -> tuple[WitnessRow, ...]:
        """Both witness sets, ordinalled, ready for ``mainline.delta_witness``.

        The winning set comes first and carries ``minimal=True``; the losing set
        follows with ``minimal=False``.  Order is stable across two runs of the
        same comparison because both underlying sets are, which is what makes
        ``witness_ord`` a reproducible citation rather than an insertion artefact.

        ``mainline.fn_delta_witness_guard`` (migration ``0140``) refuses a
        ``clause_version`` whose witness rows contain none flagged ``minimal``, so
        emitting the losing set alone would be refused — correctly.
        """
        winner = self.origin_decision if self.baseline == "blame_origin" else self.parent_decision
        loser = self.parent_decision if self.baseline == "blame_origin" else self.origin_decision
        loser_baseline: Baseline = "parent" if self.baseline == "blame_origin" else "blame_origin"

        rows: list[WitnessRow] = []
        if winner is not None:
            for finding in winner.minimal:
                rows.append(
                    WitnessRow(
                        witness_ord=len(rows),
                        witness=finding.witness,
                        minimal=True,
                        baseline=self.baseline,
                    )
                )
        if loser is not None:
            minimal_ids = {id(f) for f in (winner.minimal if winner is not None else ())}
            for finding in loser.minimal:
                if id(finding) in minimal_ids:
                    continue
                rows.append(
                    WitnessRow(
                        witness_ord=len(rows),
                        witness=finding.witness,
                        minimal=False,
                        baseline=loser_baseline,
                    )
                )
        return tuple(rows)

    def exhibit(self) -> str:
        """Return the sentence this mechanism exists to make sayable under oath."""
        if self.origin_decision is None:
            return (
                f"the delta of record is {self.delta.value!r}, measured against the parent "
                "version: this clause carries no blood-written ancestry, so ORIGINDIFF is "
                "inert and adds nothing to the ordinary diff"
            )
        origin = self.blame_origin
        where = (
            f"generation {origin.origin_gen}, {origin.origin_depth} generations back"
            if origin.origin_gen is not None
            else "the blame-origin version"
        )
        if self.baseline == "parent":
            return (
                f"the delta of record is {self.delta.value!r}. It was measured against BOTH the "
                f"parent version and the blame-origin version at {where}, and the two agreed"
            )
        return (
            f"the delta of record is {self.delta.value!r}, and it is measured against the "
            f"version the incident wrote — {where}, where severity "
            f"{origin.origin_severity} blame attached — not against last week. The parent diff "
            f"said {self.parent_decision.verdict.delta.value!r}"
        )


def delta_of_record(
    *,
    descendant: CAT | None,
    parent: CAT | None,
    origin: CAT | None,
    registry: SafeDirectionRegistry,
    as_of: bytes,
    blame_origin: BlameOrigin,
    descendant_anchors: AnchorSet | None = None,
    parent_anchors: AnchorSet | None = None,
    origin_anchors: AnchorSet | None = None,
) -> AncestralDelta:
    """Compute decision D7: the more forceful of the parent diff and the origin diff.

    ``origin`` is the Control Assertion Tuple of the version named by
    ``blame_origin``.  It is required whenever ``blame_origin.state`` is
    ``'resolved'`` and must be ``None`` when the mechanism is inert, so that a
    caller cannot pass a tuple from the wrong version by accident.

    Anchors are optional and are handled the way the lattice handles them: rule R8
    runs only for a comparison whose two anchor sets were both supplied, and
    ``LatticeDecision.anchors_considered`` records which comparisons ran with nine
    rules and which with eight.  Supplying ``descendant_anchors`` and
    ``origin_anchors`` is what makes the *uncompensated anchor drop across twenty
    commits* visible — a drop compensated at every individual step (``P-101A`` →
    ``P-101B`` → ``P-101C``) is still a drop against the origin only if the classes
    do not compensate there either, which is the matcher's business as much as the
    lattice's.

    :raises OriginUnresolvedError: when ``blame_origin`` resolved an origin version
        but no ``origin`` tuple was supplied.  Falling back to the parent diff
        would answer with a quieter verdict produced by an extraction failure, and
        that is the outcome an adversary is buying.  The two legitimate handlings
        are to supply the tuple, or to record the clause as
        ``identity_residue.reason='opaque_control'`` and let the residue block.
    """
    if blame_origin.state == "resolved" and origin is None:
        raise OriginUnresolvedError(
            "the blame origin resolved to version "
            f"{(blame_origin.origin_commit or b'').hex()[:12]} but no Control Assertion Tuple "
            "was supplied for it. ORIGINDIFF will not fall back to the parent diff: a "
            "quieter verdict produced by an unreadable origin is exactly what a "
            "salami-sliced weakening is buying. Supply the tuple, or record the clause as "
            "identity_residue.reason='opaque_control' and let the residue block the merge"
        )
    if blame_origin.state != "resolved" and origin is not None:
        raise OriginUnresolvedError(
            "an origin Control Assertion Tuple was supplied for a clause whose blame origin "
            f"is {blame_origin.state!r}. There is no version for that tuple to have come "
            "from, so the comparison would be against a baseline this resolution did not "
            "name — which is the one thing a diachronic gate may not do"
        )

    parent_decision = explain(
        parent,
        descendant,
        registry,
        as_of,
        reference_anchors=parent_anchors,
        descendant_anchors=descendant_anchors,
    )

    if origin is None:
        return AncestralDelta(
            verdict=build_verdict(
                parent_decision.verdict.delta,
                "lattice",
                parent_decision.verdict.witnesses,
                minimal=True,
            ),
            baseline="parent",
            parent_decision=parent_decision,
            origin_decision=None,
            blame_origin=blame_origin,
        )

    origin_decision = explain(
        origin,
        descendant,
        registry,
        as_of,
        reference_anchors=origin_anchors,
        descendant_anchors=descendant_anchors,
    )

    of_record = join((parent_decision.verdict.delta, origin_decision.verdict.delta))
    # Ties go to the parent: it is the incumbent baseline, and reporting the
    # ancestry as the source of a verdict the ordinary diff already reached would
    # overstate what this mechanism contributed.  `rank`, not `force`, because the
    # three force-0 labels are ordered too and the join distinguishes them.
    baseline: Baseline = (
        "blame_origin"
        if rank(origin_decision.verdict.delta) > rank(parent_decision.verdict.delta)
        else "parent"
    )
    winner = origin_decision if baseline == "blame_origin" else parent_decision

    return AncestralDelta(
        verdict=build_verdict(of_record, "lattice", winner.verdict.witnesses, minimal=True),
        baseline=baseline,
        parent_decision=parent_decision,
        origin_decision=origin_decision,
        blame_origin=blame_origin,
    )
