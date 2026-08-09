# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The self-refutation harness: five mutations, each of which must turn a named check red.

PL-2, stated for this stage: **a suite that has never been red asserts nothing.**  The audit in
``verify.py`` and the generator it audits live in the same package, written by the same hand, in
the same afternoon.  Fourteen green checks in that situation are not evidence — they are a
coincidence that has not been tested.

So this module breaks the corpus on purpose, five ways, and asserts that the audit notices.  Each
mutation is a *plausible defect*: not noise, but the specific shortcut a tired engineer takes,
or the specific thing that goes wrong when an upstream parameter drifts.

======  ==========================================================  ==================
 id      the defect                                                  must turn red
======  ==========================================================  ==================
 N1      identity is minted from the clause's current printed        R04
         label, so it follows the page instead of the obligation
 N2      the retypeset relabels nothing — the "new scheme" reuses    R05, R06, R10
         the old addresses
 N3      the retypeset reorders nothing — labels change, positions   R07, R08
         do not, so it is a renumbering wearing a reflow's name
 N4      the audit copies the injector's asserted ``identity_held``  R14
         boolean into its own output
 N5      every register is scored against itself, which is the       R10, R11
         bug that makes any matcher look perfect
======  ==========================================================  ==================

A mutation that does **not** turn its checks red is reported as ``SURVIVED``, and the harness
exits non-zero.  A survivor means the audit is measuring something other than what it says, and
that is worse than a failing check because it is invisible.

Nothing here is monkeypatching: each mutation is a pure function from the honest audit's data to
a corrupted copy, and the same :func:`mainline_corpus.reflow.verify.run_checks` is re-run over
it.  The production path cannot reach this module, and this module cannot alter the production
path.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final

from . import matchers, measure, verify
from .model import Collision, ReflowDocument, ReflowPair, RegisterScore

__all__ = ["MUTATIONS", "Mutation", "MutationOutcome", "run_nemesis"]


@dataclass(frozen=True, slots=True)
class Mutation:
    mutation_id: str
    title: str
    defect: str
    must_fail: tuple[str, ...]
    apply: Callable[[Sequence[ReflowPair]], tuple[ReflowPair, ...]]


@dataclass(frozen=True, slots=True)
class MutationOutcome:
    mutation_id: str
    title: str
    defect: str
    must_fail: tuple[str, ...]
    actually_failed: tuple[str, ...]
    verdict: str
    note: str

    def to_payload(self) -> dict[str, Any]:
        return {
            "actually_failed": list(self.actually_failed),
            "defect": self.defect,
            "must_fail": list(self.must_fail),
            "mutation_id": self.mutation_id,
            "note": self.note,
            "title": self.title,
            "verdict": self.verdict,
        }


# ── the mutations ────────────────────────────────────────────────────────────────────────────


def _mutate_label_derived_identity(pairs: Sequence[ReflowPair]) -> tuple[ReflowPair, ...]:
    """N1 — identity follows the page: the clause's id becomes the mint of its new label."""
    return tuple(
        dataclasses.replace(
            pair,
            clause_uuid=pair.g2_label_key_uuid,
            birth_key_uuid=pair.g2_label_key_uuid,
            identity_matches_birth_key=True,
            identity_is_label_free=False,
        )
        for pair in pairs
    )


def _mutate_no_relabel(pairs: Sequence[ReflowPair]) -> tuple[ReflowPair, ...]:
    """N2 — the "retypeset" prints the old addresses under a new heading font."""
    return tuple(
        dataclasses.replace(
            pair,
            g2_printed_label=pair.g1_printed_label,
            g2_shape=measure.label_shape(pair.g1_printed_label),
            label_changed=False,
            identity_is_label_free=pair.identity_matches_birth_key,
        )
        for pair in pairs
    )


def _mutate_no_reorder(pairs: Sequence[ReflowPair]) -> tuple[ReflowPair, ...]:
    """N3 — labels change, positions do not: a renumbering claiming to be a reflow."""
    return tuple(
        dataclasses.replace(
            pair,
            g2_ordinal=pair.g1_ordinal,
            ordinal_changed=False,
            ordinal_displacement=0,
        )
        for pair in pairs
    )


def _mutate_carry_asserted_boolean(pairs: Sequence[ReflowPair]) -> tuple[ReflowPair, ...]:
    """N4 — the audit copies the injector's own ``identity_held`` into its output.

    Applied at the row level rather than the dataclass level, because that is where the defect
    would in fact live: somebody adds one key to ``to_row`` and the tree grows a second home for
    an unchecked claim.  :func:`_rows_with_asserted_boolean` performs the substitution and
    ``run_nemesis`` feeds the result to ``R14``.
    """
    return tuple(pairs)


def _rows_with_asserted_boolean(pair: ReflowPair) -> dict[str, Any]:
    row = pair.to_row()
    row["identity_held"] = True
    return row


def _mutate_self_scored(pairs: Sequence[ReflowPair]) -> tuple[ReflowPair, ...]:
    """N5 — every register reads the same side twice, so every register looks perfect.

    This is the single most dangerous bug an evaluation harness can have and it is invisible in
    the output: the numbers are plausible, the code is short, and the whole scoreboard is a
    tautology.  Modelled by collapsing both sides of every key onto the pre-2016 values.
    """
    return tuple(
        dataclasses.replace(
            pair,
            g2_printed_label=pair.g1_printed_label,
            g2_shape=measure.label_shape(pair.g1_printed_label),
            g2_ordinal=pair.g1_ordinal,
            label_changed=False,
            ordinal_changed=False,
            ordinal_displacement=0,
        )
        for pair in pairs
    )


MUTATIONS: Final[tuple[Mutation, ...]] = (
    Mutation(
        mutation_id="N1",
        title="identity minted from the printed label",
        defect=(
            "every clause's identity becomes uuid5 of the address it prints under after the "
            "reflow, so identity follows the page rather than the obligation"
        ),
        must_fail=("R04",),
        apply=_mutate_label_derived_identity,
    ),
    Mutation(
        mutation_id="N2",
        title="a retypeset that relabels nothing",
        defect=(
            "the generation-2 template reuses the generation-1 addresses, so the 'new scheme' is "
            "a new font"
        ),
        must_fail=("R05", "R06", "R10"),
        apply=_mutate_no_relabel,
    ),
    Mutation(
        mutation_id="N3",
        title="a renumbering wearing a reflow's name",
        defect=(
            "labels change but every clause keeps its position, so the organising principle did "
            "not change and decision D6's claim is false"
        ),
        must_fail=("R07", "R08"),
        apply=_mutate_no_reorder,
    ),
    Mutation(
        mutation_id="N4",
        title="the injector's asserted boolean carried into the audit",
        defect=(
            "reflow_pair.jsonl grows an identity_held field copied from the schedule, giving an "
            "unchecked claim a second home in the tree that was built to check it"
        ),
        must_fail=("R14",),
        apply=_mutate_carry_asserted_boolean,
    ),
    Mutation(
        mutation_id="N5",
        title="every register scored against itself",
        defect=(
            "both sides of every register key read the pre-2016 value, so every register scores "
            "perfectly and the scoreboard measures nothing"
        ),
        must_fail=("R10", "R11"),
        apply=_mutate_self_scored,
    ),
)


# ── the harness ──────────────────────────────────────────────────────────────────────────────


def _rebuild_documents(pairs: Sequence[ReflowPair]) -> tuple[ReflowDocument, ...]:
    """Recompute the per-document measurements over mutated pairs.

    Imported lazily from ``build`` to keep the production module free of any import of this one:
    the harness knows about the build, the build does not know about the harness.
    """
    from .build import _build_documents

    return _build_documents(pairs)


def _mutated_spine(spine: Mapping[str, Any], pairs: Sequence[ReflowPair]) -> dict[str, Any]:
    """Keep the spine exhibit consistent with the mutated pairs so R13 is not collateral."""
    body = dict(spine)
    for pair in pairs:
        if pair.clause_key == spine.get("clause_key"):
            body["measured_label_2011"] = pair.g1_printed_label
            body["measured_label_2016"] = pair.g2_printed_label
            body["agrees_with_anchors"] = pair.g1_printed_label == spine.get(
                "declared_label_2011"
            ) and pair.g2_printed_label == spine.get("declared_label_2016")
            break
    return body


def _run_one(
    mutation: Mutation, pairs: Sequence[ReflowPair], spine: Mapping[str, Any]
) -> MutationOutcome:
    mutated = mutation.apply(pairs)
    documents = _rebuild_documents(mutated)
    scores: tuple[RegisterScore, ...]
    collisions: tuple[Collision, ...]
    scores, collisions = matchers.score_registers(mutated)
    report = verify.run_checks(
        pairs=mutated,
        documents=documents,
        scores=scores,
        collisions=collisions,
        spine=_mutated_spine(spine, mutated),
    )
    failed = set(report.failed_ids())

    if mutation.mutation_id == "N4":
        # R14 reads the emitted row shape, which no dataclass mutation can reach. Evaluate the
        # same predicate the check evaluates, against the row this defect would produce.
        row_fields = set(_rows_with_asserted_boolean(mutated[0]))
        if row_fields & verify.FORBIDDEN_ROW_FIELDS:
            failed.add("R14")

    missing = tuple(sorted(set(mutation.must_fail) - failed))
    verdict = "KILLED" if not missing else "SURVIVED"
    note = (
        f"the audit refused it on {sorted(set(mutation.must_fail) & failed)}"
        if verdict == "KILLED"
        else (
            f"checks {list(missing)} stayed green under a defect they exist to catch; the audit "
            "is measuring something other than what it says"
        )
    )
    return MutationOutcome(
        mutation_id=mutation.mutation_id,
        title=mutation.title,
        defect=mutation.defect,
        must_fail=mutation.must_fail,
        actually_failed=tuple(sorted(failed)),
        verdict=verdict,
        note=note,
    )


def run_nemesis(
    pairs: Sequence[ReflowPair], spine: Mapping[str, Any]
) -> tuple[MutationOutcome, ...]:
    """Apply every mutation to the honest audit and report which the checks killed."""
    return tuple(_run_one(mutation, pairs, spine) for mutation in MUTATIONS)
