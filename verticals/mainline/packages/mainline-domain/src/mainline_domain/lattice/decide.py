# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Path A: two CATs, a registry, a commit — one verdict and its irreducible reasons.

This is the function the whole product turns on, and it is deliberately the most
boring one in the repository.  It takes two frozen tuples and a registry object,
runs nine pure predicates, folds their findings with a join, minimises the
result, and returns.  **No model, no network, no I/O, no clock, no randomness.**
Given the same inputs it returns the same verdict on any machine in any year,
which is the only property that makes "the database refused this merge, and here
is why" survive cross-examination.

PATH A MUST BE INDEPENDENTLY RUNNABLE AND INDEPENDENTLY AUDITABLE
------------------------------------------------------------------
Nothing under ``mainline_domain.lattice`` imports the delta oracle, and nothing
imports a resolution layer that could reach one.  Decision D1 puts Path B in a
physically separate distribution (``mainline-delta-oracle``) reachable only
through the :class:`~mainline_domain.contracts.DeltaOracle` ``Protocol``, and
``tests/unit/domain/lattice/test_path_a_is_alone.py`` walks this package's AST to
keep it that way.  Principle P7: no component that can decide a state transition
may reach a model — and this one decides a state transition.

WHY ``as_of`` IS AN ARGUMENT AND IS CHECKED
-------------------------------------------
A DIRECTRIX registry knows the commit it was read at.  Handing this function a
registry read at a *different* commit would silently re-derive last March's
verdict under a registry that has moved since — which is precisely the
retro-tuning attack ``0150_v_safe_direction_current.sql``'s header describes,
rebuilt one layer up.  So ``as_of`` is passed separately and compared, and a
mismatch raises rather than answering.  A verdict issued at commit ``c`` must be
re-derivable under the registry that existed at ``c``, and this is the one line
that makes that checkable rather than merely intended.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from ..contracts import CAT, AnchorSet, ControlDelta, DeltaVerdict, force
from ..registry.model import SafeDirectionRegistry
from .errors import LatticeError
from .order import NEUTRAL
from .rules import RULES, RuleFinding, RuleInput
from .version import LATTICE_VERSION
from .witness import (
    minimal_correction_set,
    minimal_unsatisfiable_subset,
    verdict,
    verdict_of,
    witnesses_of,
)

__all__ = ["LatticeDecision", "decide", "explain"]

#: Path A always writes this basis.  Worker W5's ratchet is the only thing that
#: may change it, and it may only ever change it *upward* in force.
LATTICE_BASIS: Final[str] = "lattice"


@dataclass(frozen=True, slots=True)
class LatticeDecision:
    """A verdict with the whole of its arithmetic kept.

    :func:`decide` returns only the :class:`DeltaVerdict`, because that is what
    the brief specifies and what a caller writing a ``clause_version`` row needs.
    Everything else a refusal message, an audit view or the ORIGINDIFF join wants
    lives here, and :func:`explain` returns it.

    ``minimal`` is the **minimal unsatisfiable subset** — why the answer is no.
    ``repair`` is the **minimal correction set** — what would have to change for
    it to be yes.  ``ARCHITECTURE.md`` §3.1 asks for both and they are not the
    same set; ``witness.py`` explains the difference at length.

    ``anchors_considered`` is ``False`` when the caller supplied no anchor sets,
    in which case rule R8 did not run.  It is recorded rather than assumed
    because a verdict computed without anchors is a verdict with eight rules, and
    a person reading the decision record is entitled to know which.
    """

    verdict: DeltaVerdict
    findings: tuple[RuleFinding, ...]
    minimal: tuple[RuleFinding, ...]
    repair: tuple[RuleFinding, ...]
    anchors_considered: bool
    lattice_version: str
    registry_commit: bytes

    @property
    def delta(self) -> ControlDelta:
        """The verdict's label, for callers that want one attribute rather than two."""
        return self.verdict.delta

    @property
    def refuses(self) -> bool:
        """``True`` when this verdict is one the merge gate reacts to."""
        return force(self.verdict.delta) > 0


def explain(
    reference: CAT | None,
    descendant: CAT | None,
    registry: SafeDirectionRegistry,
    as_of: bytes,
    *,
    reference_anchors: AnchorSet | None = None,
    descendant_anchors: AnchorSet | None = None,
) -> LatticeDecision:
    """Run the nine rules and return the verdict together with all of its arithmetic.

    ``reference`` is whichever version the caller is diffing *against* — the
    parent for an ordinary edit, the **blame-origin version** for ORIGINDIFF
    (decision D7, worker W6).  This function does not care which and must not:
    the choice of baseline is what makes the gate diachronic, and it belongs to
    the caller.

    Either side may be ``None``, which is how R9 expresses coverage: a reference
    with no descendant is ``remove``, a descendant with no reference is
    ``introduce``.  Both ``None`` is a caller bug and raises — there is no edit
    there to have a verdict about.

    :raises LatticeError: on two ``None`` sides, or when ``registry.as_of_commit``
        is not ``as_of``.
    """
    if reference is None and descendant is None:
        raise LatticeError(
            "decide() was handed no reference and no descendant; there is no edit to judge. "
            "A clause that exists in neither version is not a control_delta, it is nothing"
        )
    if registry.as_of_commit != as_of:
        raise LatticeError(
            "the registry was read at commit "
            f"{registry.as_of_commit.hex()[:12]} but the edit under test is at "
            f"{as_of.hex()[:12]}. A verdict must be derivable under the registry that "
            "existed at its own commit; deriving it under a later one is the retro-tuning "
            "hazard DIRECTRIX exists to prevent"
        )

    inp = RuleInput(
        reference=reference,
        descendant=descendant,
        registry=registry,
        reference_anchors=reference_anchors,
        descendant_anchors=descendant_anchors,
    )

    findings: list[RuleFinding] = []
    for rule_id, predicate in RULES:
        produced = predicate(inp)
        wrong = [f.rule_id for f in produced if f.rule_id != rule_id]
        if wrong:  # pragma: no cover - a wiring bug, not a document state
            raise LatticeError(
                f"the predicate registered as {rule_id} emitted findings labelled {wrong}; "
                "a witness whose rule_id does not name the rule that produced it makes the "
                "delta_witness table unauditable"
            )
        findings.extend(produced)

    decided = verdict_of(findings) if findings else NEUTRAL
    minimal = minimal_unsatisfiable_subset(findings, decided)
    repair = minimal_correction_set(findings)

    return LatticeDecision(
        verdict=verdict(
            decided,
            "lattice",
            witnesses_of(minimal),
            minimal=True,
        ),
        findings=tuple(findings),
        minimal=minimal,
        repair=repair,
        anchors_considered=reference_anchors is not None and descendant_anchors is not None,
        lattice_version=LATTICE_VERSION,
        registry_commit=registry.as_of_commit,
    )


def decide(
    reference: CAT | None,
    descendant: CAT | None,
    registry: SafeDirectionRegistry,
    as_of: bytes,
    *,
    reference_anchors: AnchorSet | None = None,
    descendant_anchors: AnchorSet | None = None,
) -> DeltaVerdict:
    """The pure entry point: two CATs in, one :class:`DeltaVerdict` out.

    ``verdict.witnesses`` is the **minimal** set and ``verdict.minimal`` is
    therefore always ``True``.  Callers that need the residual findings — the
    repair set a person has to act on, or the full arithmetic for an audit view —
    call :func:`explain` instead and get the same verdict inside a
    :class:`LatticeDecision`.

    Every witness in the returned verdict must be written to
    ``mainline.delta_witness`` **before** the ``clause_version`` row, in the same
    transaction; ``mainline.fn_delta_witness_guard`` (migration ``0140``, attached
    to ``clause_version`` by ``0145``) refuses the version row otherwise.
    ``0049a_delta_witness.sql``'s header states that ordering contract normatively,
    and ``tests/integration/algorithms/lattice/test_verdict_round_trip.py`` writes
    a real verdict through it against a real cluster.
    """
    return explain(
        reference,
        descendant,
        registry,
        as_of,
        reference_anchors=reference_anchors,
        descendant_anchors=descendant_anchors,
    ).verdict
