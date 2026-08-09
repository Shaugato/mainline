# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The run: every class against every fixture, one row per mutant.

DETERMINISM IS THE PRODUCT PROPERTY HERE
-----------------------------------------
Given one master seed the whole run is a pure function of committed bytes.  The
per-mutant ``Random`` is seeded from ``blake2b(seed || class || fixture)``, so
adding a class does not move any other class's mutants and re-ordering the
catalogue does not move any of them.  A residual-risk figure that changed
between two runs of the same code would be a figure nobody could act on, and
``tests/e2e/mutation/test_determinism.py`` asserts the property rather than the
comment claiming it.

THE SALAMI ARM IS DIFFERENT AND THE DIFFERENCE IS THE POINT
------------------------------------------------------------
For a multi-step mutant the runner computes TWO things:

* the **origin** comparison — fixture against the last document in the chain.
  That is decision D7's baseline and it is what the outcome is judged on;
* ``chain_adjacent_max_force`` — the maximum ``force`` over every adjacent pair
  in the chain, which is what a synchronic system would have seen.

A salami whose adjacent max force is 0 and whose origin verdict is ``weaken`` is
the ORIGINDIFF claim demonstrated on data.  A salami whose adjacent steps were
individually detectable proves nothing about it, and the recorded number is what
distinguishes the two.
"""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass, field
from typing import Final

from .catalogue import load_catalogue, operator_for
from .errors import OperatorInapplicable, UnpopulatedClass
from .fixtures import load_fixtures
from .judge import judge
from .lattice_injection import ALL_RULE_IDS
from .model import (
    KILL,
    MutationClass,
    MutationResult,
    Revision,
    mutant_id,
)
from .operators.survive import ancestor_document
from .pipeline import ClauseView, run_pair, view_of

__all__ = ["RunOutput", "Skip", "killed", "run", "survivors"]

_SEED_DOMAIN: Final[bytes] = b"mainline/mutation/rng/v1\n"
_SEED_BYTES: Final[int] = 8


@dataclass(frozen=True, slots=True)
class Skip:
    """A class/fixture pairing that produced no trial, and why.

    Recorded and published.  A denominator that shrank silently is how a kill
    rate improves without anything improving, so every absent trial is in the
    artefact with the operator's own sentence attached.
    """

    class_id: str
    fixture_id: str
    reason: str


@dataclass(frozen=True, slots=True)
class RunOutput:
    """Everything one run produced."""

    seed: int
    disabled_rules: tuple[str, ...]
    results: tuple[MutationResult, ...]
    skips: tuple[Skip, ...]
    adjacent_max_force: dict[str, int] = field(default_factory=dict)


def _rng(seed: int, class_id: str, fixture_id: str) -> random.Random:
    digest = hashlib.blake2b(
        _SEED_DOMAIN
        + f"seed={seed}\n".encode()
        + f"class={class_id}\n".encode()
        + f"fixture={fixture_id}\n".encode(),
        digest_size=_SEED_BYTES,
    ).digest()
    return random.Random(int.from_bytes(digest, "big"))  # noqa: S311 - a SEEDED generator is
    # the requirement, not a hazard: the run must be byte-reproducible from committed inputs,
    # which a cryptographic source would make impossible.


def _adjacent_max_force(chain: tuple[str, ...], disabled: frozenset[str]) -> int:
    """The loudest verdict a SYNCHRONIC gate would have seen, walking the chain.

    Zero means every individual commit looked like a restatement.  That is the
    salami property, measured rather than asserted.
    """
    loudest = 0
    previous: ClauseView | None = None
    for document in chain:
        current = view_of(document)
        if previous is not None:
            step = run_pair(previous, current, disabled_rules=disabled)
            loudest = max(loudest, step.delta_force)
        previous = current
    return loudest


def _trial(
    mutation_class: MutationClass,
    revision: Revision,
    *,
    seed: int,
    disabled: frozenset[str],
) -> tuple[MutationResult, int | None]:
    operator = operator_for(mutation_class.class_id)
    application = operator(revision, _rng(seed, mutation_class.class_id, revision.fixture_id))

    ancestor_doc = (
        revision.document()
        if mutation_class.kind == KILL
        else ancestor_document(revision, mutation_class.class_id)
    )
    ancestor = view_of(ancestor_doc)
    descendant = view_of(application.descendant_document)
    outcome = run_pair(ancestor, descendant, disabled_rules=disabled)
    label, reason = judge(mutation_class.kind, outcome)

    chain = application.chain
    adjacent = None
    if len(chain) > 1:
        adjacent = _adjacent_max_force((ancestor_doc, *chain), disabled)

    result = MutationResult(
        mutant_id=mutant_id(
            seed=seed, class_id=mutation_class.class_id, fixture_id=revision.fixture_id
        ),
        class_id=mutation_class.class_id,
        kind=mutation_class.kind,
        fixture_id=revision.fixture_id,
        family=revision.family,
        outcome=label,
        outcome_reason=f"{reason}. Operator: {application.note}",
        pipeline=outcome,
        chain_length=len(chain),
    )
    return result, adjacent


def run(
    *,
    seed: int = 0,
    disabled_rules: frozenset[str] = frozenset(),
    require_every_class: bool = True,
) -> RunOutput:
    """Run every declared class against every fixture.

    :param seed: the master seed.  Recorded in the artefact and in every SQL row.
    :param disabled_rules: lattice rules to switch off — the crippled arm.  Empty
        means the production code path (:func:`mainline_domain.lattice.explain`)
        and nothing else.
    :param require_every_class: raise
        :class:`~mainline_mutation.errors.UnpopulatedClass` when a declared class
        produced no trial at all.  Defaults to ``True`` because that is the
        ``done_when`` this worker is held to; a caller exploring a single class
        can turn it off, and the artefact records that it did.

    :raises ValueError: when ``disabled_rules`` names something that is not a
        rule id.
    """
    unknown = sorted(disabled_rules - set(ALL_RULE_IDS))
    if unknown:
        raise ValueError(f"{unknown} are not lattice rule ids; the nine are {list(ALL_RULE_IDS)}")

    results: list[MutationResult] = []
    skips: list[Skip] = []
    adjacent: dict[str, int] = {}

    for mutation_class in load_catalogue():
        produced = 0
        for revision in load_fixtures():
            try:
                result, chain_force = _trial(
                    mutation_class, revision, seed=seed, disabled=disabled_rules
                )
            except OperatorInapplicable as inapplicable:
                skips.append(
                    Skip(
                        class_id=mutation_class.class_id,
                        fixture_id=revision.fixture_id,
                        reason=str(inapplicable),
                    )
                )
                continue
            results.append(result)
            if chain_force is not None:
                adjacent[result.mutant_id] = chain_force
            produced += 1
        if produced == 0 and require_every_class:
            reasons = [s.reason for s in skips if s.class_id == mutation_class.class_id]
            raise UnpopulatedClass(
                f"class {mutation_class.class_id!r} produced no trial against any of the "
                f"{len(load_fixtures())} fixtures. A class that contributes nothing makes the "
                "published aggregate a statement about a smaller catalogue than the artefact "
                f"claims. Operator reasons: {reasons[:3]}"
            )

    return RunOutput(
        seed=seed,
        disabled_rules=tuple(sorted(disabled_rules)),
        results=tuple(results),
        skips=tuple(skips),
        adjacent_max_force=adjacent,
    )


def killed(output: RunOutput) -> tuple[MutationResult, ...]:
    """KILL results the pipeline caught."""
    return tuple(r for r in output.results if r.kind == KILL and r.success)


def survivors(output: RunOutput) -> tuple[MutationResult, ...]:
    """KILL results that reached the gate undetected — the residual risk, named."""
    return tuple(r for r in output.results if r.kind == KILL and not r.success)
