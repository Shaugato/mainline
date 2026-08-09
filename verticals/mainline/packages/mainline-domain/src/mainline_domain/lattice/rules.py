# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The nine deterministic predicates.  No model, no network, no I/O.

Each rule is a pure function ``RuleInput -> tuple[RuleFinding, ...]``.  A rule
that has nothing to say returns ``()``.  A rule that *cannot* say returns a
``WEAKEN`` finding marked ``orderable=False`` — P3 fail-closed — rather than
raising or returning a sentinel, because the failure mode of a safety gate is a
block, not a stack trace and not a silence.

WHY EACH RULE OWNS EXACTLY ONE SLOT
-----------------------------------
The nine rules partition the CAT.  Nothing is judged twice, and the partition is
enforced by construction rather than by comment:

======================  ==================================================
``R1_DEONTIC``          ``deontic``
``R2_SETPOINT``         ``parameter`` + ``value`` (the magnitude)
``R3_COMPARATOR``       ``comparator`` (the *relation class*, never the value)
``R4_EXCEPTION``        ``exceptions``
``R5_QUANTIFIER``       ``coverage_quantifier``
``R6_VERIFICATION``     ``verification``
``R7_FREQUENCY``        ``frequency``
``R8_ANCHOR``           the anchor sets (not a CAT slot at all)
``R9_COVERAGE``         the existence of the CAT
======================  ==================================================

Double-counting is not a cosmetic problem here.  The verdict is a *join*, so a
second witness for one edit cannot make the verdict worse — but it can make the
refusal message claim two independent reasons where there is one, and a refusal
that overstates its own case is the kind of thing that gets a gate switched off
(risk R-A7: a rule that breaches the nuisance ceiling is **rejected, not tuned**).
``mainline_domain.anchors.drop`` makes the same argument in the other direction.

TWO CAT SLOTS ARE DELIBERATELY UNJUDGED
---------------------------------------
``actor``/``action``/``object_class``/``hazard_energy`` and ``conditions`` have
no rule.  For the first four that is because a change in them is a change of
*identity*, which the matcher (workers W7/W8) decides — a clause whose actor
changed from "the operator" to "the supervisor" may or may not be the same
obligation, and the lattice is not the place that question gets answered.

``conditions`` is the harder omission and is stated in ``novelty/deltalattice.yaml``
under ``unverified``: adding a condition can narrow a control's applicability (a
weakening) or state a pre-existing scope explicitly (a restatement), and this
lattice has no way to tell those apart.  Guessing in the fail-closed direction
would fire on a very large fraction of ordinary edits.  Nine rules, no tenth.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

from ..anchors.drop import uncompensated_drops
from ..cat.lexicon import load_lexicons
from ..cat.normalise import normalise_phrase
from ..cat.schema import COMPARATORS, COVERAGE_QUANTIFIERS, DEONTIC_LABELS
from ..contracts import CAT, AnchorSet, ControlDelta, DeltaWitness, Quantity, RuleId
from ..quantity.algebra import compare
from ..quantity.errors import QuantityError
from ..registry.model import SafeDirectionRegistry
from ..registry.resolve import setpoint_delta, tolerance_delta

__all__ = [
    "BOUND_POLARITY_INVERSIONS",
    "COMPARATOR_FAMILY",
    "COVERAGE_RANK",
    "DEONTIC_POLARITY",
    "DEONTIC_RUNG",
    "RULES",
    "WEAKENING_COMPARATOR_MOVES",
    "Rule",
    "RuleFinding",
    "RuleInput",
    "r1_deontic",
    "r2_setpoint",
    "r3_comparator",
    "r4_exception",
    "r5_quantifier",
    "r6_verification",
    "r7_frequency",
    "r8_anchor",
    "r9_coverage",
]


# --------------------------------------------------------------------------- #
# What a rule is handed, and what it hands back                                #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class RuleInput:
    """Everything the nine rules are allowed to see.

    Note what is **absent**: no clause id, no commit id, no site, no severity, no
    blame ancestry, no text.  A rule that could see the severity of the ancestry
    could be written to be quieter on the clauses that matter most, and the whole
    point of Path A is that it is re-derivable by an opposing expert from two
    tuples and a signed registry.

    ``reference_anchors``/``descendant_anchors`` are ``None`` when the caller did
    not supply them, in which case **rule R8 does not run at all**.  That is a
    silent omission by design — see :func:`r8_anchor` — and
    :attr:`~mainline_domain.lattice.decide.LatticeDecision.anchors_considered`
    is how a caller finds out it happened.
    """

    reference: CAT | None
    descendant: CAT | None
    registry: SafeDirectionRegistry
    reference_anchors: AnchorSet | None
    descendant_anchors: AnchorSet | None

    @property
    def both_present(self) -> bool:
        """``True`` when there are two tuples to compare (rules R1 to R8 need this)."""
        return self.reference is not None and self.descendant is not None


@dataclass(frozen=True, slots=True)
class RuleFinding:
    """One rule's contribution: a delta, its witness row, and whether it inverts.

    ``orderable`` is the flag the duality property turns on.  It is ``True`` when
    the finding sits on a **ladder**, so reading the same edit backwards produces
    the dual verdict (a deontic downgrade reversed is a deontic upgrade).  It is
    ``False`` for the two kinds of finding whose dual is *itself*:

    * a **polarity inversion** — ``MUST`` ↔ ``MUST_NOT``, an upper bound becoming
      a lower bound.  The control was turned around, and neither direction of
      reading makes that a strengthening;
    * a **fail-closed abstention** — the registry declined, the quantities are
      not comparable, a slot became unreadable.  Reversing an "I cannot tell"
      gives another "I cannot tell", and both resolve to ``weaken`` under D6.

    Those are the only two categories, they are enumerated by
    ``tests/unit/domain/lattice/test_duality.py``, and a third one appearing
    without a test is how the duality guarantee would quietly stop being true.
    """

    rule_id: RuleId
    delta: ControlDelta
    orderable: bool
    witness: DeltaWitness


def _finding(
    rule_id: RuleId,
    delta: ControlDelta,
    field: str,
    from_repr: str,
    to_repr: str,
    note: str,
    *,
    orderable: bool = True,
) -> RuleFinding:
    return RuleFinding(
        rule_id=rule_id,
        delta=delta,
        orderable=orderable,
        witness=DeltaWitness(
            rule_id=rule_id,
            field=field,
            from_repr=from_repr,
            to_repr=to_repr,
            note=note,
        ),
    )


def _q(value: Quantity | None) -> str:
    """Render a quantity as it will be printed in a refusal.  ``'—'`` for absent.

    The unit is the *canonical* one, not the document's spelling, because the
    reader of a refusal needs to see the thing that was actually compared.  The
    frame is printed whenever it is not ``none``: ``'50 psi_gauge (gauge)'``
    against ``'50 psi_absolute (absolute)'`` is the one pair of strings that must
    never look identical in a refusal message (decision D5).
    """
    if value is None:
        return "—"
    frame = "" if value.reference == "none" else f" ({value.reference})"
    return f"{value.value} {value.unit}{frame}"


def _seq(elements: tuple[str, ...]) -> str:
    return "[" + ", ".join(repr(e) for e in elements) + "]"


# --------------------------------------------------------------------------- #
# R1 — deontic                                                                 #
# --------------------------------------------------------------------------- #

DEONTIC_RUNG: Final[dict[str, int]] = {
    "MUST": 3,
    "MUST_NOT": 3,
    "SHOULD": 2,
    "SHOULD_NOT": 2,
    "MAY": 1,
    "ABSENT": 0,
}
"""``MUST > SHOULD > MAY > ABSENT``; moving right is the weakening.

``MUST_NOT``/``SHOULD_NOT`` share a rung with their positive twins because a
prohibition has the same *force* as the corresponding obligation — it is the
polarity of the action that differs, and ``cat/schema.py`` says so where the
labels are declared.  Encoding "shall not enter" as ``(MUST, not_enter)`` instead
would put the negation inside ``action``, split the identity of every clause
about entry, and leave R1 comparing two rungs that were never comparable.
"""

DEONTIC_POLARITY: Final[dict[str, str]] = {
    "MUST": "+",
    "MUST_NOT": "-",
    "SHOULD": "+",
    "SHOULD_NOT": "-",
    "MAY": "+",
    "ABSENT": "0",
}


def r1_deontic(inp: RuleInput) -> tuple[RuleFinding, ...]:
    """Deontic downgrade: ``MUST → SHOULD → MAY → ABSENT`` moving right.

    Three outcomes and one refusal:

    * the rung fell — ``weaken``, orderable;
    * the rung rose — ``strengthen``, orderable;
    * the **polarity inverted** at any rung (``MUST`` → ``MUST_NOT``) — ``weaken``,
      *not* orderable.  The control was turned around: an obligation to do a
      thing became a prohibition on doing it, or the reverse.  Neither reading is
      a tightening, both are a change no lattice can rank, and P3 says an
      unrankable change to a safety control is adjudicated rather than assumed
      benign.  This is one of exactly two non-dual cells in the whole lattice;
      the other is the bound inversion in :func:`r3_comparator`.
    * a label outside :data:`~mainline_domain.cat.schema.DEONTIC_LABELS` — the
      extractor is broken, and a broken extractor must not be able to produce a
      quiet ``restate``.  ``weaken``, not orderable.
    """
    if inp.reference is None or inp.descendant is None:  # i.e. not inp.both_present
        return ()
    before, after = inp.reference.deontic, inp.descendant.deontic
    if before == after:
        return ()

    if before not in DEONTIC_LABELS or after not in DEONTIC_LABELS:
        unknown = before if before not in DEONTIC_LABELS else after
        return (
            _finding(
                "R1_DEONTIC",
                ControlDelta.WEAKEN,
                "deontic",
                before,
                after,
                f"{unknown!r} is not one of {DEONTIC_LABELS}; an unknown modality has no "
                "rung on R1's ladder, so this edit is unrankable and fails closed",
                orderable=False,
            ),
        )

    polarity_before, polarity_after = DEONTIC_POLARITY[before], DEONTIC_POLARITY[after]
    if {polarity_before, polarity_after} == {"+", "-"}:
        return (
            _finding(
                "R1_DEONTIC",
                ControlDelta.WEAKEN,
                "deontic",
                before,
                after,
                f"the deontic polarity inverted ({before} → {after}): an obligation became a "
                "prohibition or the reverse. That is not a move along R1's ladder and the "
                "lattice will not rank it",
                orderable=False,
            ),
        )

    rung_before, rung_after = DEONTIC_RUNG[before], DEONTIC_RUNG[after]
    if rung_after < rung_before:
        return (
            _finding(
                "R1_DEONTIC",
                ControlDelta.WEAKEN,
                "deontic",
                before,
                after,
                f"the deontic fell from {before} to {after}; on R1's ladder "
                f"MUST > SHOULD > MAY > ABSENT, and moving right loosens the obligation",
            ),
        )
    return (
        _finding(
            "R1_DEONTIC",
            ControlDelta.STRENGTHEN,
            "deontic",
            before,
            after,
            f"the deontic rose from {before} to {after}",
        ),
    )


# --------------------------------------------------------------------------- #
# R3 — comparator (declared before R2 because R2 consults the families)        #
# --------------------------------------------------------------------------- #

COMPARATOR_FAMILY: Final[dict[str, str]] = {
    "": "none",
    "~": "approx",
    "+/-": "tolerance",
    "range": "range",
    "<": "upper",
    "<=": "upper",
    ">": "lower",
    ">=": "lower",
    "=": "exact",
}
"""Which *kind* of relation each comparator token asserts.

R2 compares magnitudes only **within** a family: ``50 kPa`` under ``<=`` and
``50 kPa`` under ``+/-`` are not two readings of one number, and subtracting them
would be arithmetic on two different assertions.  When the family moves, R3 owns
the edit and R2 stays silent, so one change produces one witness.
"""

_WEAKENING_MOVES: Final[tuple[tuple[str, str, str], ...]] = (
    # (from, to, why) — every non-empty comparator losing its bound entirely.
    ("<=", "", "the upper bound was removed"),
    ("<", "", "the upper bound was removed"),
    (">=", "", "the lower bound was removed"),
    (">", "", "the lower bound was removed"),
    ("=", "", "the stated value was removed"),
    ("~", "", "the approximate value was removed"),
    ("+/-", "", "the tolerance was removed"),
    ("range", "", "the range was removed"),
    # An exact value becoming anything less exact.
    ("=", "~", "an exact value became approximate"),
    ("=", "+/-", "an exact value acquired a tolerance band"),
    ("=", "range", "an exact value became a range"),
    # A bound becoming a band or an approximation.
    ("<=", "~", "a bound became an approximation"),
    ("<=", "+/-", "a bound became a tolerance band"),
    ("<=", "range", "a bound became a range"),
    ("<", "~", "a bound became an approximation"),
    ("<", "+/-", "a bound became a tolerance band"),
    ("<", "range", "a bound became a range"),
    (">=", "~", "a bound became an approximation"),
    (">=", "+/-", "a bound became a tolerance band"),
    (">=", "range", "a bound became a range"),
    (">", "~", "a bound became an approximation"),
    (">", "+/-", "a bound became a tolerance band"),
    (">", "range", "a bound became a range"),
    # A stated band becoming a hand-wave.
    ("+/-", "~", "a stated tolerance became an approximation"),
    ("range", "~", "a stated range became an approximation"),
    # The two cells the brief and research §6.2 name explicitly.  See the note
    # in WEAKENING_COMPARATOR_MOVES below: these are the arguable ones.
    ("<=", "<", "a closed bound became an open one"),
    (">=", ">", "a closed bound became an open one"),
)

WEAKENING_COMPARATOR_MOVES: Final[dict[tuple[str, str], str]] = {
    (before, after): why for before, after, why in _WEAKENING_MOVES
}
"""The explicit, reviewable transition table.  Every cell is a decision.

The **strengthening** table is not written down: it is exactly this one reversed
(:func:`r3_comparator` looks the reversed pair up), which is what makes "a
strengthen is the exact dual of a weaken" a property of the data rather than a
claim about two hand-maintained lists that could drift apart.

CELLS THAT ARE DELIBERATELY SILENT.  ``=`` ↔ ``<=`` and ``=`` ↔ ``>=`` produce no
finding in either direction.  "exactly 50 kPa" becoming "at most 50 kPa" enlarges
the admissible set and tightens nothing, but it is also the single commonest
*restatement* in a real procedure library — a drafter writing the same cap two
ways — and firing on it would breach the nuisance ceiling that risk R-A7 says
gets a rule rejected rather than tuned.  Silence in both directions keeps the
table symmetric, so the duality property still holds over these cells.

THE ARGUABLE CELLS, STATED PLAINLY.  ``<=`` → ``<`` is listed as a weakening
because the brief, ``docs/leads/algorithms.md`` §2, and
``research/05-architecture/clause-identity.md`` §6.2 all name it as one.  On the
arithmetic alone that is **backwards**: ``< 50`` excludes 50 and is the tighter
bound.  What the rule actually catches is a drafter changing the *relation class*
of a limit, which in the corpus is nearly always accompanied by a change to the
number — and the direction of the error here is over-blocking (a genuine
tightening reported as a weakening), which costs an adjudication and never a
silent pass.  That is the correct direction of failure for this product and it is
recorded in ``novelty/deltalattice.yaml`` under ``unverified`` rather than
defended as correct.  If the mutation ratchet (worker W10) measures the nuisance
cost as unacceptable, the two cells are **removed**, not re-weighted.
"""

BOUND_POLARITY_INVERSIONS: Final[frozenset[tuple[str, str]]] = frozenset(
    (a, b) for a in ("<", "<=") for b in (">", ">=")
) | frozenset((b, a) for a in ("<", "<=") for b in (">", ">="))
"""Upper bound ↔ lower bound.  ``weaken`` in **both** directions, and not orderable.

The second of exactly two non-dual cells in the lattice (the first is the deontic
polarity inversion in :func:`r1_deontic`).  A cap on a parameter becoming a floor
on the same parameter is the control turned around; there is no reading of that
edit in which one of the two directions is a tightening.
"""


# PLR0911: the return count IS the transition table made visible. Each `return` is one
# reviewable cell — unknown token, polarity inversion, listed loosening, its reverse,
# silence — and folding them into an accumulator would hide which cell decided.
def r3_comparator(inp: RuleInput) -> tuple[RuleFinding, ...]:  # noqa: PLR0911
    """Judge comparator loosening: ``<=`` to ``<``, ``=`` to ``~``, bound removed.

    R3 judges the **relation class only**.  The magnitude belongs to R2, and the
    two never both fire on one edit: when the family changes R2 falls silent, and
    when it does not, this table's cells are all within-family or empty.
    """
    if inp.reference is None or inp.descendant is None:  # i.e. not inp.both_present
        return ()
    before, after = inp.reference.comparator, inp.descendant.comparator
    if before == after:
        return ()

    if before not in COMPARATORS or after not in COMPARATORS:
        unknown = before if before not in COMPARATORS else after
        return (
            _finding(
                "R3_COMPARATOR",
                ControlDelta.WEAKEN,
                "comparator",
                before,
                after,
                f"{unknown!r} is not in the comparator alphabet {sorted(COMPARATORS)}; "
                "an unknown relation cannot be ordered and fails closed",
                orderable=False,
            ),
        )

    if (before, after) in BOUND_POLARITY_INVERSIONS:
        return (
            _finding(
                "R3_COMPARATOR",
                ControlDelta.WEAKEN,
                "comparator",
                before,
                after,
                f"the bound inverted ({before} → {after}): a cap on this parameter became a "
                "floor, or the reverse. The control was turned around and the lattice will "
                "not rank it",
                orderable=False,
            ),
        )

    why = WEAKENING_COMPARATOR_MOVES.get((before, after))
    if why is not None:
        return (
            _finding(
                "R3_COMPARATOR",
                ControlDelta.WEAKEN,
                "comparator",
                before,
                after,
                f"{why} ({before or 'no relation'} → {after or 'no relation'})",
            ),
        )

    inverse = WEAKENING_COMPARATOR_MOVES.get((after, before))
    if inverse is not None:
        return (
            _finding(
                "R3_COMPARATOR",
                ControlDelta.STRENGTHEN,
                "comparator",
                before,
                after,
                f"the exact reverse of a loosening ({inverse}), read forwards: "
                f"{before or 'no relation'} → {after or 'no relation'}",
            ),
        )
    return ()


# --------------------------------------------------------------------------- #
# R2 — setpoint                                                                #
# --------------------------------------------------------------------------- #


def _nothing_moved(reference: CAT, descendant: CAT) -> bool:
    """Report whether parameter, comparator family and value are all identical.

    This short-circuit is what keeps decision D6 pointed at the thing it is for.
    D6 says an *unratified parameter abstains and an abstention is a weakening* —
    it is about a **move** the registry cannot rank, not about the mere existence
    of a parameter nobody has ratified.  Without this guard, re-typesetting a
    clause whose parameter is not yet in DIRECTRIX would report ``weaken`` on an
    edit in which the setpoint did not move at all, and every unratified clause
    in the corpus would block on its own reformatting.  That is the nuisance-
    ceiling failure mode, and it would be a bug in this module rather than a
    property of D6.
    """
    return (
        reference.parameter == descendant.parameter
        and COMPARATOR_FAMILY.get(reference.comparator)
        == COMPARATOR_FAMILY.get(descendant.comparator)
        and reference.value == descendant.value
    )


def r2_setpoint(inp: RuleInput) -> tuple[RuleFinding, ...]:
    """Setpoint direction — whether the value moved against ``safe_direction``.

    After SI normalisation, and only after it: a magnitude compared in the
    document's own units is a comparison between two different questions.

    The direction comes from DIRECTRIX (worker W2), read **as of the commit under
    test**, and an unknown, proposed, withdrawn, retired, duplicated, ambiguous or
    dimension-mismatched parameter yields ``SafeDirection.ABSTAIN``, which
    decision D6 resolves to ``weaken`` — never to neutral.  The whole of that
    ruling, with its arithmetic, is
    :func:`mainline_domain.registry.resolve.setpoint_delta`; this rule's job is to
    decide *whether the two values are two readings of one assertion* and then to
    turn the ruling into a witness.

    Three ways this rule declines to run, each for a reason that is not "nothing
    happened":

    * nothing was asserted on either side (no parameter, no comparator, no value)
      — there is no setpoint here for anything to have moved;
    * nothing moved (:func:`_nothing_moved`);
    * the comparator **family** changed, so R3 owns the edit and R2 would be
      double-counting it.
    """
    if inp.reference is None or inp.descendant is None:  # i.e. not inp.both_present
        return ()
    reference, descendant = inp.reference, inp.descendant

    asserted = any(
        (
            reference.parameter,
            descendant.parameter,
            reference.comparator,
            descendant.comparator,
            reference.value is not None,
            descendant.value is not None,
        )
    )
    if not asserted or _nothing_moved(reference, descendant):
        return ()

    if reference.parameter != descendant.parameter:
        return (_parameter_changed(reference, descendant),)

    if COMPARATOR_FAMILY.get(reference.comparator) != COMPARATOR_FAMILY.get(descendant.comparator):
        return ()  # R3's edit, not this one

    parameter = reference.parameter
    if COMPARATOR_FAMILY.get(reference.comparator) == "tolerance":
        ruling = tolerance_delta(
            inp.registry,
            parameter,
            ancestor_band=reference.value,
            descendant_band=descendant.value,
        )
        field = "value(tolerance)"
    else:
        ruling = setpoint_delta(
            inp.registry,
            parameter,
            ancestor=reference.value,
            descendant=descendant.value,
        )
        field = "value"

    if ruling.delta is ControlDelta.RESTATE:
        return ()

    # A finding is on a ladder only if TWO magnitudes were actually compared.
    # `ruling.abstained` alone is not enough: `tolerance_delta` answers a removed
    # band decisively ("a specification with no stated band has an unbounded one")
    # but *abstains* on an added one, so trusting that flag would make the removal
    # orderable and the addition not — an asymmetry that is real in W2's helper and
    # must not become an asymmetry in this lattice's duality guarantee.  Requiring
    # both sides present makes the two directions agree; it is a no-op on the
    # setpoint path, where a missing side already abstains.
    both_sides = ruling.ancestor is not None and ruling.descendant is not None
    return (
        _finding(
            "R2_SETPOINT",
            ruling.delta,
            field,
            _q(ruling.ancestor),
            _q(ruling.descendant),
            f"{parameter or '(no parameter named)'}: {ruling.reason}",
            orderable=not ruling.abstained and both_sides,
        ),
    )


def _parameter_changed(reference: CAT, descendant: CAT) -> RuleFinding:
    """Rule on an edit in which the parameter under control is not the one it was.

    Two shapes, and only one of them is rankable.  A parameter *appearing* where
    none was named fills a slot, and ``cat/schema.py``'s ``EMPTY_CAT`` doctrine
    reads an edge toward a filled slot as a strengthening; a parameter *vanishing*
    is the same edge backwards.  A parameter **replaced** by a different one is
    not on any ladder: the registry ratifies a direction per parameter and has no
    ordering across two of them, so the comparison the rule would need does not
    exist.  Fails closed, not orderable.
    """
    before, after = reference.parameter, descendant.parameter
    if before and after:
        return _finding(
            "R2_SETPOINT",
            ControlDelta.WEAKEN,
            "parameter",
            before,
            after,
            f"the parameter under control changed from {before!r} to {after!r}; DIRECTRIX "
            "ratifies a direction per parameter and has no ordering across two of them",
            orderable=False,
        )
    if before and not after:
        return _finding(
            "R2_SETPOINT",
            ControlDelta.WEAKEN,
            "parameter",
            before,
            "—",
            f"the clause stopped naming a controlled parameter ({before!r}); a control "
            "whose subject became unreadable is not a control that stayed put",
        )
    return _finding(
        "R2_SETPOINT",
        ControlDelta.STRENGTHEN,
        "parameter",
        "—",
        after,
        f"the clause now names a controlled parameter ({after!r}) where it named none",
    )


# --------------------------------------------------------------------------- #
# R4 — exceptions and hedges                                                   #
# --------------------------------------------------------------------------- #


def _hedge_phrases() -> frozenset[str]:
    """Return the committed hedge lexicon, normalised the way a CAT slot is.

    Loaded through :func:`mainline_domain.cat.lexicon.load_lexicons`, which is
    ``lru_cache``d and reads only committed files — no network, no environment.
    The fingerprint of those files is stamped into ``extractor_version``, so a
    stored verdict records *which word list decided that a phrase was a hedge*.
    """
    return frozenset(normalise_phrase(p) for p in load_lexicons().hedges.phrases)


def _hedge_in(element: str) -> str | None:
    """Return the lexicon hedge this exception is, or contains.  ``None`` otherwise."""
    normalised = normalise_phrase(element)
    phrases = _hedge_phrases()
    if normalised in phrases:
        return normalised
    # Containment, longest first, so "so far as is reasonably practicable" is
    # reported rather than the "practicable"-shaped fragment inside it.  The
    # extractor writes a hedge into `exceptions[]` on its own, but an exception
    # span captured by a subordinator can carry one along with it.
    for phrase in sorted(phrases, key=len, reverse=True):
        if phrase in normalised:
            return phrase
    return None


def r4_exception(inp: RuleInput) -> tuple[RuleFinding, ...]:
    """``exceptions[]`` grows, or a hedge from the committed lexicon enters.

    One finding per element, not one per edit.  The list is what a person has to
    read to understand the refusal, and "two exceptions were added" is a summary
    where "``so far as is reasonably practicable`` and ``at the supervisor's
    discretion`` were added" is evidence.

    Removals produce ``strengthen`` findings for the same reason: the duality
    property is a property of this rule, and a rule that only ever fired one way
    could not be checked against its own inverse.
    """
    if inp.reference is None or inp.descendant is None:  # i.e. not inp.both_present
        return ()
    before = inp.reference.exceptions
    after = inp.descendant.exceptions
    before_set, after_set = set(before), set(after)

    findings: list[RuleFinding] = []
    for element in after:
        if element in before_set:
            continue
        hedge = _hedge_in(element)
        detail = (
            f"and it is the committed hedge {hedge!r}, which leaves the obligation formally "
            "intact and practically optional"
            if hedge is not None
            else "which narrows when the obligation applies"
        )
        findings.append(
            _finding(
                "R4_EXCEPTION",
                ControlDelta.WEAKEN,
                "exceptions",
                _seq(before),
                _seq(after),
                f"the exception {element!r} entered the clause, {detail}",
            )
        )
    for element in before:
        if element in after_set:
            continue
        findings.append(
            _finding(
                "R4_EXCEPTION",
                ControlDelta.STRENGTHEN,
                "exceptions",
                _seq(before),
                _seq(after),
                f"the exception {element!r} was removed, so the obligation now applies "
                "where it previously did not",
            )
        )
    return tuple(findings)


# --------------------------------------------------------------------------- #
# R5 — coverage quantifier                                                     #
# --------------------------------------------------------------------------- #

COVERAGE_RANK: Final[dict[str, int]] = {
    "unspecified": 0,
    "typical": 1,
    "selected": 2,
    "any": 3,
    "all": 4,
}
"""How much of the population the clause covers.  Falling is the weakening.

``unspecified`` is the **bottom** and not a neutral middle, which is the same
choice ``EMPTY_CAT`` makes for every other slot: a clause that stopped saying
"all" is a clause that stopped asserting coverage, and reading that as "no change"
would make deleting the word ``all`` the cheapest weakening in the product.

``typical``/``representative`` names a sample; ``selected``/``nominated`` names an
enumerated subset, which is broader than a sample; ``any`` is universal but leaves
the selection to the reader; ``all`` is explicit universal coverage.  The keys are
exactly ``cat/schema.py``'s ``COVERAGE_QUANTIFIERS`` and a test holds them equal,
so a sixth quantifier cannot appear in the lexicon without appearing here.
"""


def r5_quantifier(inp: RuleInput) -> tuple[RuleFinding, ...]:
    """Quantifier narrowing: ``all → selected``, ``every → typical``, scope shrinks."""
    if inp.reference is None or inp.descendant is None:  # i.e. not inp.both_present
        return ()
    before = inp.reference.coverage_quantifier
    after = inp.descendant.coverage_quantifier
    if before == after:
        return ()

    if before not in COVERAGE_RANK or after not in COVERAGE_RANK:
        unknown = before if before not in COVERAGE_RANK else after
        return (
            _finding(
                "R5_QUANTIFIER",
                ControlDelta.WEAKEN,
                "coverage_quantifier",
                before,
                after,
                f"{unknown!r} is not one of {sorted(COVERAGE_QUANTIFIERS)}; an unranked "
                "quantifier cannot be ordered and fails closed",
                orderable=False,
            ),
        )

    if COVERAGE_RANK[after] < COVERAGE_RANK[before]:
        return (
            _finding(
                "R5_QUANTIFIER",
                ControlDelta.WEAKEN,
                "coverage_quantifier",
                before,
                after,
                f"coverage narrowed from {before!r} to {after!r}; the control now reaches "
                "less of the population it reached before",
            ),
        )
    return (
        _finding(
            "R5_QUANTIFIER",
            ControlDelta.STRENGTHEN,
            "coverage_quantifier",
            before,
            after,
            f"coverage widened from {before!r} to {after!r}",
        ),
    )


# --------------------------------------------------------------------------- #
# R6 — verification                                                            #
# --------------------------------------------------------------------------- #


def r6_verification(inp: RuleInput) -> tuple[RuleFinding, ...]:
    """Detect an independent check, second signature or hold point being deleted.

    The cues are ``data/lexicon/slots.toml``'s ``[verification.cues]`` — the
    things quietly removed when a procedure is "streamlined".  One finding per
    deleted check, because which one went is the whole content of the refusal.
    """
    if inp.reference is None or inp.descendant is None:  # i.e. not inp.both_present
        return ()
    before = inp.reference.verification
    after = inp.descendant.verification
    before_set, after_set = set(before), set(after)

    findings: list[RuleFinding] = []
    for element in before:
        if element in after_set:
            continue
        findings.append(
            _finding(
                "R6_VERIFICATION",
                ControlDelta.WEAKEN,
                "verification",
                _seq(before),
                _seq(after),
                f"the verification step {element!r} was deleted; an independent check, a "
                "second signature or a hold point no longer stands between the hazard and "
                "the work",
            )
        )
    for element in after:
        if element in before_set:
            continue
        findings.append(
            _finding(
                "R6_VERIFICATION",
                ControlDelta.STRENGTHEN,
                "verification",
                _seq(before),
                _seq(after),
                f"the verification step {element!r} was added",
            )
        )
    return tuple(findings)


# --------------------------------------------------------------------------- #
# R7 — frequency                                                               #
# --------------------------------------------------------------------------- #


# PLR0911: ten returns because there are ten distinct outcomes, and every one of them is
# a different sentence in a refusal — removed, stated, uncomparable, longer, shorter,
# unchanged. Collapsing them into a shared exit would make the ten sentences one, which
# is exactly the "a refusal that tells the writer the wrong thing costs an hour" failure.
def r7_frequency(inp: RuleInput) -> tuple[RuleFinding, ...]:  # noqa: PLR0911
    """Detect the test or inspection **interval** lengthening.

    ``CAT.frequency`` is always an interval, never a rate: ``grammar.toml``
    inverts "twice per shift" into ``0.5 shift`` at extraction time precisely so
    that this rule never has to know whether a number counts events or time.  So
    the arithmetic is one comparison and the direction is fixed — longer is looser
    — with no registry lookup, because "a longer interval between gas tests is
    worse" is not a per-parameter judgement anybody needs to ratify.

    Event-anchored frequencies ("before each use") carry the unit ``use`` in the
    dimension ``event``.  Two of those compare fine against each other; one
    against a duration raises :class:`QuantityError`, and an uncomparable pair
    fails closed rather than being quietly skipped.
    """
    if inp.reference is None or inp.descendant is None:  # i.e. not inp.both_present
        return ()
    before, after = inp.reference.frequency, inp.descendant.frequency
    if before is None and after is None:
        return ()

    if before is not None and after is None:
        return (
            _finding(
                "R7_FREQUENCY",
                ControlDelta.WEAKEN,
                "frequency",
                _q(before),
                "—",
                "the stated interval was removed; a test with no stated frequency has an "
                "unbounded one",
            ),
        )
    if before is None and after is not None:
        return (
            _finding(
                "R7_FREQUENCY",
                ControlDelta.STRENGTHEN,
                "frequency",
                "—",
                _q(after),
                "an interval was stated where none was",
            ),
        )

    if before is None or after is None:  # pragma: no cover - the three branches above cover it
        # (None, None), (x, None) and (None, y) have all returned, so this is
        # unreachable today.  It is written FAIL-CLOSED rather than `return ()`
        # because P3 says the failure mode of a safety gate is a block, and an
        # unreachable branch that would fail OPEN is one refactor away from being
        # reachable.
        return (
            _finding(
                "R7_FREQUENCY",
                ControlDelta.WEAKEN,
                "frequency",
                _q(before),
                _q(after),
                "the two frequencies could not both be read; an interval comparison "
                "this rule cannot perform is treated as a loosening (P3)",
                orderable=False,
            ),
        )
    if before == after:
        return ()
    try:
        moved = compare(after, before)
    except QuantityError as exc:
        return (
            _finding(
                "R7_FREQUENCY",
                ControlDelta.WEAKEN,
                "frequency",
                _q(before),
                _q(after),
                f"the two intervals are not comparable: {exc}",
                orderable=False,
            ),
        )
    if moved == 0:
        return ()
    if moved > 0:
        return (
            _finding(
                "R7_FREQUENCY",
                ControlDelta.WEAKEN,
                "frequency",
                _q(before),
                _q(after),
                "the interval between checks lengthened, so the control is exercised less "
                "often than the version that carries the blame",
            ),
        )
    return (
        _finding(
            "R7_FREQUENCY",
            ControlDelta.STRENGTHEN,
            "frequency",
            _q(before),
            _q(after),
            "the interval between checks shortened",
        ),
    )


# --------------------------------------------------------------------------- #
# R8 — anchor drop                                                             #
# --------------------------------------------------------------------------- #


def r8_anchor(inp: RuleInput) -> tuple[RuleFinding, ...]:
    """Uncompensated identity-anchor drop — worker W1's detector, as a lattice rule.

    "Uncompensated" means *no anchor of the same class arrived in its place*.
    ``P-101A`` → nothing is a weakening; ``P-101A`` → ``P-101B`` is not this
    rule's business, because ``AnchorSet.compatible_with`` already refuses to call
    those the same clause, which is a louder outcome than a drop.

    **R8 does not run when the caller supplies no anchors**, and it does not fail
    closed on their absence.  Failing closed there would make every CAT-only
    comparison a weakening — including the two-tuple comparison that is this
    lattice's entire specification — so the absence is reported instead, on
    :attr:`~mainline_domain.lattice.decide.LatticeDecision.anchors_considered`.
    A caller that decides a merge on a verdict computed without anchors has
    skipped a rule and the decision record says so.

    Only the five :data:`~mainline_domain.contracts.IDENTITY_ANCHOR_CLASSES` are
    considered: a dropped ``setpoint`` is R2's business and a dropped
    ``named_role`` is R1's.
    """
    reference, descendant = inp.reference_anchors, inp.descendant_anchors
    if reference is None or descendant is None:
        return ()

    findings: list[RuleFinding] = []
    for drop in uncompensated_drops(reference, descendant):
        findings.append(
            _finding(
                "R8_ANCHOR",
                ControlDelta.WEAKEN,
                f"anchor:{drop.cls.value}",
                drop.norm,
                "—",
                f"the {drop.cls.value} anchor {drop.norm!r} was dropped and nothing of its "
                "class arrived in its place",
            )
        )
    for added in uncompensated_drops(descendant, reference):
        findings.append(
            _finding(
                "R8_ANCHOR",
                ControlDelta.STRENGTHEN,
                f"anchor:{added.cls.value}",
                "—",
                added.norm,
                f"the {added.cls.value} anchor {added.norm!r} was added and nothing of its "
                "class was dropped, so the control reaches something it did not reach before",
            )
        )
    return tuple(findings)


# --------------------------------------------------------------------------- #
# R9 — coverage loss                                                           #
# --------------------------------------------------------------------------- #


def r9_coverage(inp: RuleInput) -> tuple[RuleFinding, ...]:
    """Detect a CAT present in the reference version and absent in the descendant.

    ``remove`` is force 3 — the loudest label there is — and it is the one verdict
    that needs no other rule to agree with it.  The dual is ``introduce``, which
    is force 0: adding a control is safe, deleting one is not, and that asymmetry
    is why :func:`~mainline_domain.lattice.order.dual` is not an order
    automorphism.

    **The reference matters more than the parent here.**  ORIGINDIFF (worker W6)
    runs this comparison against the *blame-origin* version, so a control that
    twenty commits removed one qualifier at a time is absent against the version
    that the fatality wrote even though it is present against yesterday's.  This
    rule takes whatever reference it is handed; the caller chooses, and the
    caller is diachronic.
    """
    if inp.reference is not None and inp.descendant is None:
        return (
            _finding(
                "R9_COVERAGE",
                ControlDelta.REMOVE,
                "cat",
                "present",
                "absent",
                "the control assertion present in the reference version is absent from the "
                "descendant: the obligation was not weakened, it was deleted",
            ),
        )
    if inp.reference is None and inp.descendant is not None:
        return (
            _finding(
                "R9_COVERAGE",
                ControlDelta.INTRODUCE,
                "cat",
                "absent",
                "present",
                "the descendant asserts a control the reference version did not; there is no "
                "ancestry for this assertion to have weakened",
            ),
        )
    return ()


# --------------------------------------------------------------------------- #
# The catalogue                                                                #
# --------------------------------------------------------------------------- #

Rule = Callable[[RuleInput], "tuple[RuleFinding, ...]"]

RULES: Final[tuple[tuple[RuleId, Rule], ...]] = (
    ("R1_DEONTIC", r1_deontic),
    ("R2_SETPOINT", r2_setpoint),
    ("R3_COMPARATOR", r3_comparator),
    ("R4_EXCEPTION", r4_exception),
    ("R5_QUANTIFIER", r5_quantifier),
    ("R6_VERIFICATION", r6_verification),
    ("R7_FREQUENCY", r7_frequency),
    ("R8_ANCHOR", r8_anchor),
    ("R9_COVERAGE", r9_coverage),
)
"""``(rule_id, predicate)`` in declaration order.

The order is not cosmetic: it is the **citation order** the minimiser uses to
break ties.  When two rules independently force the same verdict, either one is
an irreducible reason on its own, and the refusal cites the lower-numbered one
so that two runs of the same comparison never blame different rules.  The others
are still written to ``mainline.delta_witness`` as the repair set — the minimal
unsatisfiable subset says *why the answer is no*, the repair set says *what would
have to change for it to be yes*, and I14 asks for both.
"""
