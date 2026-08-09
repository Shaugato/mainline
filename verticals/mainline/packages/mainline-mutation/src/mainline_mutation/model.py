# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The types the harness measures with.  Frozen, slotted, and deliberately dull.

THE TWO CATALOGUES ARE TWO DIFFERENT PRODUCTS (decision D13)
-------------------------------------------------------------
A single "accuracy" number over one mixed corpus hides both failure directions
at once, and they are not the same failure:

``KILL``
    A control mutation.  The pipeline **must** react — either the delta lattice
    returns ``weaken``/``remove``, or the identity machinery raises a residue
    row.  A KILL mutant that produces neither is a **missed weakening**, which
    in this product is a fatality that the gate let through.  It is the risk
    ``docs/leads/algorithms.md`` §8 R-A1 declines to argue away and elects to
    measure instead.

``SURVIVE``
    An identity-preserving reformat.  The pipeline **must not** react: the
    clause must still be recognised as the same clause and no ``weaken`` may be
    raised.  A SURVIVE mutant that changes identity is a **manufactured false
    positive**, which costs an adjudication, and enough of them breach the
    nuisance ceiling that R-A7 says gets a rule *rejected, not tuned*.

Reporting them separately is the whole of decision D13.  There is no combined
"accuracy" figure anywhere in this package, and adding one would be a
regression.

THE OUTCOME VOCABULARY IS CLOSED
---------------------------------
:data:`Outcome` has exactly six members and every one of them is a different
sentence in the published artefact.  ``killed``/``survived`` belong to KILL;
``preserved``/``identity_changed``/``false_weaken``/``identity_changed_and_false_weaken``
belong to SURVIVE.  :meth:`MutationResult.success` is the one place the two
vocabularies collapse into a boolean, and it is the only input the Wilson
arithmetic takes.
"""

from __future__ import annotations

import hashlib
import random
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Final, Literal

__all__ = [
    "KILL",
    "MUTANT_ID_DOMAIN",
    "OUTCOMES",
    "SURVIVE",
    "ClassMetric",
    "MutationApplication",
    "MutationClass",
    "MutationKind",
    "MutationResult",
    "Operator",
    "Outcome",
    "PipelineOutcome",
    "Revision",
    "mutant_id",
]

MutationKind = Literal["KILL", "SURVIVE"]

KILL: Final[MutationKind] = "KILL"
SURVIVE: Final[MutationKind] = "SURVIVE"

Outcome = Literal[
    "killed",
    "survived",
    "preserved",
    "identity_changed",
    "false_weaken",
    "identity_changed_and_false_weaken",
]

OUTCOMES: Final[tuple[Outcome, ...]] = (
    "killed",
    "survived",
    "preserved",
    "identity_changed",
    "false_weaken",
    "identity_changed_and_false_weaken",
)

#: Domain separator for :func:`mutant_id`.  A bare digest over three strings
#: collides with every other bare digest over three strings in the repository.
MUTANT_ID_DOMAIN: Final[bytes] = b"mainline/mutation/mutant-id/v1\n"


def mutant_id(*, seed: int, class_id: str, fixture_id: str, ordinal: int = 0) -> str:
    """Return the deterministic identifier of one mutant.

    A mutant's identity is a pure function of the master seed, the mutation
    class, the fixture and an ordinal within the pairing — never of a clock, a
    UUID, or the order in which the runner happened to enumerate the catalogue.
    Two runs of the same seed therefore produce the same set of ``mutant_id``
    values, which is what makes a diff of two artefacts a diff of *outcomes*
    rather than of identifiers.
    """
    preimage = b"".join(
        (
            MUTANT_ID_DOMAIN,
            f"seed={seed}\n".encode(),
            f"class={class_id}\n".encode(),
            f"fixture={fixture_id}\n".encode(),
            f"ordinal={ordinal}\n".encode(),
        )
    )
    return hashlib.sha256(preimage).hexdigest()[:32]


@dataclass(frozen=True, slots=True)
class MutationClass:
    """One declared row of a catalogue.  Data, loaded from ``catalogue-v1.toml``.

    ``expected`` is prose and is not executed; the executable form of the same
    sentence is :func:`mainline_mutation.judge.judge`.  Both exist because a
    reader of the artefact needs the sentence and the runner needs the
    predicate, and keeping them in one place would mean the artefact carried
    whatever the code happened to do.
    """

    class_id: str
    kind: MutationKind
    title: str
    rationale: str
    expected: str
    #: The mutation classes the brief names in groups (``1%``/``5%``/``25%``
    #: setpoint nudges, ``5``/``10``/``20``-step salami) are separate classes,
    #: because a kill rate that averaged them would hide the interesting end.
    magnitude: str | None = None
    #: When ``True`` the class declines fixtures whose parameter DIRECTRIX does
    #: not ratify.  Declared per class rather than decided in code so that the
    #: reason a trial is absent from a denominator is legible in the data file.
    applies_when_ratified: bool = False


@dataclass(frozen=True, slots=True)
class Revision:
    """One historical fixture revision — the ancestor a mutation is applied to.

    ``family`` is the document family the metric is broken down by: a kill rate
    that is high on permits and low on ventilation standards is two different
    facts, and the aggregate would report neither.

    ``furniture_lines`` and ``numbering_prefix`` are carried separately from
    ``raw_text`` because half the SURVIVE catalogue is about changing exactly
    those and nothing else.  :meth:`document` reassembles the page as the
    canonicaliser will see it.

    ``directrix_ratified`` records whether ``parameter`` resolves in the
    DIRECTRIX seed.  It is an input to operator applicability and never to a
    verdict: the harness declines to run a setpoint nudge against an unratified
    parameter because the resulting kill would measure D6's fail-closed
    abstention rather than R2's direction arithmetic.
    """

    fixture_id: str
    family: str
    title: str
    raw_text: str
    numbering_prefix: str
    furniture_lines: tuple[str, ...]
    parameter: str
    directrix_ratified: bool
    setpoint_token: str
    setpoint_value: str
    setpoint_unit: str

    def document(self, *, text: str | None = None, prefix: str | None = None) -> str:
        """Reassemble the page: furniture lines, then the numbered clause.

        ``text`` and ``prefix`` override the stored ones so an operator can
        change one layer without rebuilding the others — which is what makes
        ``renumber`` a one-line operator that provably touches nothing else.
        """
        body = self.raw_text if text is None else text
        number = self.numbering_prefix if prefix is None else prefix
        head = f"{number} " if number else ""
        return "\n".join([*self.furniture_lines, head + body])


@dataclass(frozen=True, slots=True)
class MutationApplication:
    """What an operator produced: the descendant document and how it got there.

    ``descendant_document`` is the **whole page** — furniture lines, numbering
    prefix and clause body — exactly as
    :func:`mainline_domain.canon.canonicalise` will see it.  Operators return a
    document rather than a clause body because half the SURVIVE catalogue
    changes nothing *but* the furniture, and an operator that could only return
    a body could not express those mutations at all.

    ``chain`` is the intermediate documents of a multi-step mutation, ancestor
    excluded and descendant included, so ``chain[-1] == descendant_document``
    always and ``len(chain) == 1`` for every single-step operator.  It exists
    for the N-step salami classes, where the *point* is that no adjacent pair in
    the chain is detectable and the composition is.
    """

    descendant_document: str
    note: str
    chain: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Hold ``chain[-1] == descendant_document``, defaulting a single-step chain."""
        if not self.chain:
            object.__setattr__(self, "chain", (self.descendant_document,))
        elif self.chain[-1] != self.descendant_document:
            raise ValueError(
                "a mutation chain must end at the descendant document it claims; the last "
                "chain element and `descendant_document` disagree, which would make the salami "
                "classes measure a composition nobody applied"
            )


@dataclass(frozen=True, slots=True)
class PipelineOutcome:
    """Everything the pipeline said about one ancestor/descendant pair.

    Every field is a fact the artefact prints or the SQL row stores.  Nothing
    here is a judgement: :func:`mainline_mutation.judge.judge` turns this into an
    :data:`Outcome`, and keeping the two apart is what lets a reader re-derive
    the verdict from the recorded facts.
    """

    ancestor_canon_sha256: str
    descendant_canon_sha256: str
    ancestor_cat_key: str | None
    descendant_cat_key: str | None
    ancestor_cat_confidence: str
    descendant_cat_confidence: str
    delta: str
    delta_basis: str
    delta_force: int
    #: What the ABSTENTION RATCHET returns for this pair when Path B did NOT
    #: run.  Recorded, never judged on.  ``resolution.resolve(path_a, None,
    #: theta)`` treats an absent oracle as an abstention and decision D6 resolves
    #: an abstention to ``weaken``, so this column is ``weaken`` on every row —
    #: which is the ratchet failing closed exactly as specified and is precisely
    #: why the harness judges Path A instead.  See
    #: :mod:`mainline_mutation.pipeline`.
    ratchet_delta_without_oracle: str
    witness_rule_ids: tuple[str, ...]
    residue_reasons: tuple[str, ...]
    identity_recovered: bool
    match_stage: str | None
    match_score: float | None
    anchors_considered: bool
    disabled_rules: tuple[str, ...]
    residue_source: str


@dataclass(frozen=True, slots=True)
class MutationResult:
    """One row of the run: one mutant, one outcome, and the arithmetic behind it."""

    mutant_id: str
    class_id: str
    kind: MutationKind
    fixture_id: str
    family: str
    outcome: Outcome
    outcome_reason: str
    pipeline: PipelineOutcome
    chain_length: int

    @property
    def success(self) -> bool:
        """``True`` when the pipeline did what the catalogue says it must.

        The single collapse point from the six-member outcome vocabulary into the
        boolean the Wilson arithmetic consumes.  For KILL that is ``killed``; for
        SURVIVE it is ``preserved``.  Nothing else counts, in either catalogue.
        """
        return self.outcome in ("killed", "preserved")


Operator = Callable[[Revision, random.Random], MutationApplication]
"""What every operator is.

The ``Random`` is supplied by the runner and seeded from ``(master seed, class,
fixture)``, so an operator that wants randomness has it and an operator that
reaches for the module-level ``random`` has broken reproducibility for the whole
artefact.
"""


@dataclass(frozen=True, slots=True)
class ClassMetric:
    """The published figure for one catalogue class, in one document family or overall."""

    kind: MutationKind
    class_id: str
    family: str
    successes: int
    trials: int
    wilson_lower: float
    point_estimate: float
    wilson_upper: float
    confidence: str
    outcome_counts: Mapping[str, int] = field(default_factory=dict)
