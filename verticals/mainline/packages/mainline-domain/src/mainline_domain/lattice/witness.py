# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Minimality — what turns a refusal message from a dump into a reason.

Invariant **I14**: *every refusal emits an irreducible reason set and, where
computable, the nearest admissible alternative*.  ``ARCHITECTURE.md`` §3.1 spells
out why: a gate that only says "no" gets routed around, and an invariant that is
routed around is not an invariant.

Those are **two different sets** and this module computes both.

THE MINIMAL UNSATISFIABLE SUBSET — *why the answer is no*
---------------------------------------------------------
A subset ``M`` of the findings with ``join(M) == verdict`` such that dropping any
member changes the verdict.  It is computed the way the brief specifies —
:func:`minimal_unsatisfiable_subset` drops each finding in turn and re-runs the
decision — and then **verified**, because a single greedy deletion pass is only
guaranteed irredundant for a monotone decision and this module refuses to assume
that its own decision function will stay monotone forever.  The pass is repeated
to a fixpoint and the post-condition is asserted before the result is returned.

THE MINIMAL CORRECTION SET — *what would have to change for it to be yes*
-------------------------------------------------------------------------
A smallest subset ``C`` of the findings whose **removal** makes the verdict
admissible (``force == 0``).  ``ARCHITECTURE.md`` §3.1 calls this the *nearest
admissible alternative*, and it is not the same as ``M``: when three rules each
independently force ``weaken``, any one of them is an irreducible reason, but
undoing one of them changes nothing — all three have to go.

AN HONEST NOTE ON HOW BIG ``M`` USUALLY IS
------------------------------------------
Because the verdict is a **join** over nine independent rules, ``M`` is a
singleton for every finding combination this lattice can currently produce: the
single most forceful finding attains the maximum on its own.  That is not a
weakness of the minimiser, it is a true fact about the decision, and it is
recorded in ``novelty/deltalattice.yaml`` rather than dressed up.  The general
algorithm is written anyway — it costs nine iterations over at most nine findings
— so that a future rule whose finding is only forcing *in combination* does not
silently break the property that
``tests/unit/domain/lattice/test_minimality.py`` proves over a thousand
Hypothesis cases.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Final

from ..contracts import ControlDelta, DeltaBasis, DeltaVerdict, DeltaWitness, force
from .errors import LatticeError, WitnesslessWeakenError
from .order import join
from .rules import RuleFinding

__all__ = [
    "WITNESSLESS_WEAKEN_MESSAGE",
    "is_irredundant",
    "minimal_correction_set",
    "minimal_unsatisfiable_subset",
    "verdict",
    "verdict_of",
    "witnesses_of",
]

#: The Python-side wording.  Deliberately **not** identical to the SQL guard's
#: message: the two refusals happen in different places for different audiences,
#: and a test that asserts the SQL text must fail when the SQL changes, not when
#: this string does.  The SQL message is
#: ``'MAINLINE: a lattice weakening must carry its minimal witness set'`` and it
#: is pinned by ``tests/integration/algorithms/lattice/test_witness_or_refuse.py``.
WITNESSLESS_WEAKEN_MESSAGE: Final[str] = (
    "a lattice {delta} must carry its minimal witness set (decision D8): "
    "delta_basis='lattice' with no DeltaWitness rows is a verdict nobody can check, "
    "and mainline.fn_delta_witness_guard raises P0001 on it"
)


def verdict_of(findings: Iterable[RuleFinding]) -> ControlDelta:
    """Return the verdict a set of findings produces: the join of their deltas."""
    return join(finding.delta for finding in findings)


def witnesses_of(findings: Iterable[RuleFinding]) -> tuple[DeltaWitness, ...]:
    """Return the witness rows of a finding sequence, in the order given."""
    return tuple(finding.witness for finding in findings)


def is_irredundant(findings: Sequence[RuleFinding], target: ControlDelta) -> bool:
    """Report whether no member can be dropped without changing the verdict.

    The defining property of a minimal unsatisfiable subset, written as a
    predicate so it can be asserted rather than argued.  An empty sequence is
    irredundant iff it already yields the target.
    """
    if verdict_of(findings) != target:
        return False
    return all(
        verdict_of([f for j, f in enumerate(findings) if j != i]) != target
        for i in range(len(findings))
    )


def minimal_unsatisfiable_subset(
    findings: Sequence[RuleFinding],
    target: ControlDelta | None = None,
) -> tuple[RuleFinding, ...]:
    """Return the irreducible reason set behind ``target`` (default: the findings' verdict).

    Deletion-based, repeated to a fixpoint, then verified.  Candidates are tried
    for removal in **reverse declaration order**, so when several rules force the
    same verdict the survivor is the lowest-numbered one — see
    :data:`~mainline_domain.lattice.rules.RULES` on why the citation has to be
    stable across two runs of the same comparison.

    :raises LatticeError: if the result fails :func:`is_irredundant`.  That is an
        internal contradiction — the minimiser disagreeing with its own
        post-condition — and returning a set that has not been checked would put
        an unchecked "irreducible reason set" in front of a person deciding
        whether to sign a permit.
    """
    goal = verdict_of(findings) if target is None else target
    kept = list(findings)
    if verdict_of(kept) != goal:
        raise LatticeError(
            f"the finding set yields {verdict_of(kept).value!r}, not the requested "
            f"{goal.value!r}; there is no subset of it that yields the latter"
        )

    changed = True
    while changed:
        changed = False
        for candidate in reversed(list(kept)):
            trial = [f for f in kept if f is not candidate]
            if verdict_of(trial) == goal:
                kept = trial
                changed = True
                break

    result = tuple(kept)
    if not is_irredundant(result, goal):  # pragma: no cover - a contradiction, not a state
        raise LatticeError(
            "the minimiser produced a redundant witness set; this is a bug in "
            "minimal_unsatisfiable_subset, not a property of the edit"
        )
    return result


def minimal_correction_set(findings: Sequence[RuleFinding]) -> tuple[RuleFinding, ...]:
    """Return the nearest admissible alternative: the smallest set whose removal admits.

    "Admits" means ``force(join(rest)) == 0`` — the gate stops reacting.  Returns
    ``()`` when the findings are already admissible.

    Computed the same way round as the MUS, but on the complement: start from
    every forcing finding, then try putting each one back and keep it out only if
    it was needed.  The result is preserved in declaration order so the repair
    list a person reads runs R1 → R9.
    """
    if force(verdict_of(findings)) == 0:
        return ()

    def _without(removed: Sequence[RuleFinding]) -> list[RuleFinding]:
        # Identity, never equality: two rules can emit byte-identical witnesses
        # for one edit (an exception added and the same string removed elsewhere),
        # and `in` would drop both when only one was chosen.
        gone = {id(f) for f in removed}
        return [f for f in findings if id(f) not in gone]

    correction = [f for f in findings if force(f.delta) > 0]
    for candidate in list(correction):
        trial = [f for f in correction if f is not candidate]
        if force(verdict_of(_without(trial))) == 0:
            correction = trial
    order = {id(f): i for i, f in enumerate(findings)}
    return tuple(sorted(correction, key=lambda f: order[id(f)]))


def verdict(
    delta: ControlDelta,
    basis: DeltaBasis,
    witnesses: tuple[DeltaWitness, ...],
    *,
    minimal: bool,
) -> DeltaVerdict:
    """Build a :class:`DeltaVerdict` — the **only** sanctioned way to do so in this domain.

    Enforces decision D8 at the point the mistake is made: a ``weaken`` or
    ``remove`` on ``delta_basis='lattice'`` with an empty witness tuple raises
    :class:`~mainline_domain.lattice.errors.WitnesslessWeakenError`.

    ``basis='abstain_to_weaken'`` and ``basis='human'`` are exempt, and the
    exemption is not a loophole — it is the same scoping
    ``mainline.fn_delta_witness_guard`` uses.  The ratchet fires precisely when
    Path A could **not** decide, so demanding a lattice witness for it would
    demand an explanation that does not exist; a human override's explanation is
    the commit message and the signature on it.

    ``basis='lattice+model'`` is **not** exempt.  If the model raised the force of
    a verdict the lattice had already formed, the lattice's own reasons are still
    the ones the database can check, and a ``lattice+model`` weaken with no
    lattice witness is a verdict resting entirely on a model — which principle P7
    does not allow to decide a state transition on its own.
    """
    if force(delta) > 0 and basis in ("lattice", "lattice+model") and not witnesses:
        raise WitnesslessWeakenError(WITNESSLESS_WEAKEN_MESSAGE.format(delta=delta.value))
    return DeltaVerdict(delta=delta, basis=basis, witnesses=witnesses, minimal=minimal)
