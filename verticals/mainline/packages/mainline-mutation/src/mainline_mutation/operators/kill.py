# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""KILL operators — control mutations the pipeline must react to.

Every operator here writes a clause a real drafter could defend in a review
meeting.  That is the design constraint: a mutation nobody would ever commit
measures nothing, because the failure mode this harness exists to quantify is
the edit that *passes* review.

THE SUBSTITUTION TABLES ARE CHECKED AGAINST THE COMMITTED LEXICON
------------------------------------------------------------------
:func:`_assert_lexicon_coupled` runs at import and raises
:class:`~mainline_mutation.errors.CatalogueError` if a phrase this module
neutralises is not in ``data/lexicon/slots.toml``'s committed cue lists.  Without
that check the harness could drift into deleting phrases the extractor never
recognised, which would produce mutants that are trivially undetectable and a
kill rate that fell for a reason nobody could name.

WHAT THE SALAMI OPERATORS ACTUALLY DO, BECAUSE IT IS THE INTERESTING ONE
------------------------------------------------------------------------
They walk the comparator through the two cells rule R3 is **deliberately
silent** on — ``<=`` ↔ ``=``, documented in ``lattice/rules.py`` as the
commonest restatement in a real library — and move the magnitude on the step
where the comparator FAMILY changes, because R2 stays silent then (comparing a
bound against an exact value is arithmetic on two different assertions).  The
remaining steps are pure reflow, which changes no CAT slot at all.

The consequence is exactly the claim decision D7 makes: **every adjacent diff is
`restate` and the diff against the origin is `weaken`.**  The runner records
``chain_adjacent_max_force`` so the artefact states that as a measurement rather
than as an assertion — a salami whose adjacent steps were individually
detectable would prove nothing about ORIGINDIFF, and the number says whether
they were.
"""

from __future__ import annotations

import random
import re
from decimal import Decimal
from typing import Final

from mainline_domain.anchors.extract import extract_anchors
from mainline_domain.cat.lexicon import load_lexicons
from mainline_domain.contracts import IDENTITY_ANCHOR_CLASSES, AnchorClass
from mainline_domain.registry import SafeDirection

from ..directrix import safe_direction
from ..errors import CatalogueError, OperatorInapplicable
from ..model import MutationApplication, Operator, Revision
from ..paraphrase import paraphrase_for
from ._text import decimal_str, insert_before, replace_first_ci

__all__ = ["KILL_OPERATORS"]


# --------------------------------------------------------------------------- #
# Tables — each one reviewable on its own, each one coupled to the lexicon      #
# --------------------------------------------------------------------------- #

#: Longest first.  ``must not`` must be tried before ``must`` or the negation is
#: left behind and the mutant reads ``should not not exceed``.
_DEONTIC_DOWNGRADES: Final[tuple[tuple[str, str], ...]] = (
    ("must not", "should not"),
    ("shall not", "should not"),
    ("must", "should"),
    ("shall", "should"),
)

#: Verification cue → the innocuous phrase that replaces it.  Every left-hand
#: side is a committed surface in ``slots.toml``'s ``[verification.cues]``; the
#: right-hand sides are deliberately *not* cues, so the slot empties.
_VERIFICATION_NEUTRALISERS: Final[tuple[tuple[str, str], ...]] = (
    ("independently verified", "reviewed"),
    ("independent verification", "a review"),
    ("independent check", "a review"),
    ("recorded on the permit", "noted locally"),
    ("second signature", "note"),
    ("countersigned", "filed"),
    ("functional test", "walkaround"),
    ("witnessed by", "seen by"),
    ("isolation certificate", "isolation note"),
)

#: ``all``-class cue → ``selected``-class cue.  Both sides are committed cues in
#: ``[coverage_quantifier.cues]``, so the rank provably falls from 4 to 2.
_QUANTIFIER_NARROWINGS: Final[tuple[tuple[str, str], ...]] = (
    ("every", "nominated"),
    ("all", "selected"),
    ("each", "designated"),
)

#: Non-negating comparator surfaces, which can be loosened to ``approximately``
#: without touching the deontic.  A negating surface (``not exceed``) cannot:
#: replacing it flips MUST_NOT to MUST and rule R1 fires a polarity inversion,
#: which would make this class measure R1 instead of R3.
_COMPARATOR_SURFACES: Final[tuple[str, ...]] = (
    "no more than",
    "not more than",
    "no less than",
    "not less than",
    "at least",
    "at most",
    "a maximum of",
    "a minimum of",
    "maximum of",
    "minimum of",
)

_HEDGE: Final[str] = "so far as is reasonably practicable"
_EXCEPTION: Final[str] = "except where the supervisor determines otherwise"

_NUDGE_PERCENT: Final[dict[str, str]] = {"1%": "0.01", "5%": "0.05", "25%": "0.25"}

#: The comparator surface a salami step uses to reach the exact family.  ``set
#: at`` is the committed ``'='`` surface in ``grammar.toml`` and it is not a
#: negating action, so the deontic is untouched.
_EXACT_SURFACE: Final[str] = "must be set at"

_SALAMI_STEPS: Final[dict[str, int]] = {"salami_5": 5, "salami_10": 10, "salami_20": 20}

#: The composed magnitude of a salami, as a fraction of the origin value. 25 %
#: because that is the setpoint-nudge control case: a salami that composed to
#: something smaller than the loudest single nudge would be measuring the nudge.
_SALAMI_TOTAL: Final[Decimal] = Decimal("0.25")


def _assert_lexicon_coupled() -> None:
    """Refuse a substitution table that has drifted from the committed lexicon."""
    lexicons = load_lexicons()
    verification = {surface.lower() for surface in lexicons.slots.verification}
    for surface, replacement in _VERIFICATION_NEUTRALISERS:
        if surface not in verification:
            raise CatalogueError(
                f"the verification neutraliser {surface!r} is not a committed cue in "
                "slots.toml [verification.cues]. Deleting a phrase the extractor never "
                "recognised produces a mutant that is undetectable by construction and a "
                "kill rate that falls for a reason nobody can name"
            )
        if replacement.lower() in verification:
            raise CatalogueError(
                f"the verification neutraliser replaces {surface!r} with {replacement!r}, "
                "which is ALSO a committed cue; the slot would not empty and the mutation "
                "would be a no-op wearing the name of a deletion"
            )
    quantifier = {surface.lower(): key for surface, key in lexicons.slots.quantifier.items()}
    for surface, replacement in _QUANTIFIER_NARROWINGS:
        if quantifier.get(surface) != "all":
            raise CatalogueError(
                f"{surface!r} is not an 'all'-class coverage cue in slots.toml; narrowing from "
                "it would not lower the coverage rank"
            )
        if quantifier.get(replacement) != "selected":
            raise CatalogueError(
                f"{replacement!r} is not a 'selected'-class coverage cue in slots.toml; the "
                "narrowing would not be a narrowing"
            )
    comparators = {surface.lower() for surface in lexicons.grammar.comparator}
    for surface in (*_COMPARATOR_SURFACES, _EXACT_SURFACE.removeprefix("must be ")):
        if surface not in comparators:
            raise CatalogueError(
                f"{surface!r} is not a committed comparator surface in grammar.toml; a "
                "comparator mutation the extractor cannot read is not a comparator mutation"
            )
    negating = {surface.lower() for surface in lexicons.slots.action_negating}
    for surface in _COMPARATOR_SURFACES:
        if surface in negating:
            raise CatalogueError(
                f"{surface!r} is both a comparator surface and a NEGATING action surface; "
                "loosening it would flip the deontic and this class would measure R1"
            )
    if _HEDGE not in {phrase.lower() for phrase in lexicons.hedges.phrases}:
        raise CatalogueError(
            f"{_HEDGE!r} is not in the committed hedge lexicon; R4's hedge finding would not "
            "fire and the class would be measuring an ordinary exception"
        )


_assert_lexicon_coupled()


# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #


def _tail_insert(body: str, phrase: str) -> str:
    """Append ``, <phrase>`` before the clause's final full stop."""
    stripped = body.rstrip()
    if stripped.endswith("."):
        return f"{stripped[:-1]}, {phrase}."
    return f"{stripped}, {phrase}."


def _tidy(body: str) -> str:
    """Repair the spacing artefacts a deletion leaves behind.

    Not cosmetic.  ``canon()`` collapses whitespace runs, so a double space would
    vanish anyway — but ``' ,'`` and ``' .'`` would not, and a mutant whose only
    difference from its ancestor is a floating comma is a mutant whose detection
    says nothing about the control.
    """
    body = re.sub(r"\s{2,}", " ", body)
    body = re.sub(r"\s+([,.;])", r"\1", body)
    return body.strip()


def _require_change(revision: Revision, body: str, what: str) -> str:
    if body.strip() == revision.raw_text.strip():
        raise OperatorInapplicable(
            f"{what} left {revision.fixture_id} unchanged; an operator whose output equals its "
            "input has produced no trial, and a kill rate over no-op mutants is a number "
            "about nothing"
        )
    return body


def _nudged_token(revision: Revision, fraction: Decimal) -> str:
    """The setpoint token moved ``fraction`` **against** ``safe_direction``."""
    direction = safe_direction(revision.parameter)
    if direction is SafeDirection.LOWER_IS_SAFER:
        moved = Decimal(revision.setpoint_value) * (Decimal(1) + fraction)
    elif direction is SafeDirection.HIGHER_IS_SAFER:
        moved = Decimal(revision.setpoint_value) * (Decimal(1) - fraction)
    else:
        raise OperatorInapplicable(
            f"DIRECTRIX answers {direction.value} for {revision.parameter!r}; a nudge whose "
            "dangerous direction is unknown would be measuring D6's fail-closed abstention "
            "rather than R2's direction arithmetic"
        )
    return f"{decimal_str(moved)} {revision.setpoint_unit}"


# --------------------------------------------------------------------------- #
# The operators                                                                #
# --------------------------------------------------------------------------- #


def deontic_downgrade(revision: Revision, rng: random.Random) -> MutationApplication:
    """MUST becomes SHOULD.  The obligation stays; its force does not."""
    del rng
    for surface, replacement in _DEONTIC_DOWNGRADES:
        body = replace_first_ci(revision.raw_text, surface, replacement)
        if body is not None:
            return MutationApplication(
                descendant_document=revision.document(text=_require_change(
                    revision, body, "deontic_downgrade"
                )),
                note=f"{surface!r} -> {replacement!r}",
            )
    raise OperatorInapplicable(
        f"{revision.fixture_id} states no MUST or SHALL to downgrade"
    )


def _setpoint_nudge(revision: Revision, magnitude: str) -> MutationApplication:
    if not revision.directrix_ratified or not revision.setpoint_token:
        raise OperatorInapplicable(
            f"{revision.fixture_id} carries no DIRECTRIX-ratified setpoint; the class declares "
            "applies_when_ratified so this pairing is not a trial"
        )
    token = _nudged_token(revision, Decimal(_NUDGE_PERCENT[magnitude]))
    body = replace_first_ci(revision.raw_text, revision.setpoint_token, token)
    if body is None:
        raise OperatorInapplicable(
            f"the declared setpoint token {revision.setpoint_token!r} is not in "
            f"{revision.fixture_id}'s text"
        )
    return MutationApplication(
        descendant_document=revision.document(
            text=_require_change(revision, body, f"setpoint_nudge_{magnitude}")
        ),
        note=(
            f"{revision.setpoint_token!r} -> {token!r}, {magnitude} against "
            f"{safe_direction(revision.parameter).value}"
        ),
    )


def setpoint_nudge_1pct(revision: Revision, rng: random.Random) -> MutationApplication:
    """One percent against ``safe_direction``: inside the noise of a human review."""
    del rng
    return _setpoint_nudge(revision, "1%")


def setpoint_nudge_5pct(revision: Revision, rng: random.Random) -> MutationApplication:
    """Five percent: the magnitude a drafter defends as a rounding tidy-up."""
    del rng
    return _setpoint_nudge(revision, "5%")


def setpoint_nudge_25pct(revision: Revision, rng: random.Random) -> MutationApplication:
    """Twenty-five percent: the control case.  A harness that misses it measures nothing."""
    del rng
    return _setpoint_nudge(revision, "25%")


def comparator_loosening(revision: Revision, rng: random.Random) -> MutationApplication:
    """A stated bound becomes an approximation, with the number untouched.

    Two shapes, in preference order, and the second one is *expected to be
    harder*:

    1. a non-negating comparator surface becomes ``approximately`` — a clean R3
       loosening with the deontic untouched;
    2. otherwise ``approximately`` is inserted before the magnitude, leaving the
       negating surface (``must not exceed``) in place.  The extractor resolves
       the comparator longest-first and keeps ``<=``, so **this mutant survives**
       — and that survival is a finding about the extractor's precedence, not a
       defect in the harness.  It is left in the catalogue rather than tuned out,
       because removing the mutants a system fails on is how a mutation score
       becomes a marketing number.
    """
    del rng
    for surface in _COMPARATOR_SURFACES:
        body = replace_first_ci(revision.raw_text, surface, "approximately")
        if body is not None:
            return MutationApplication(
                descendant_document=revision.document(
                    text=_require_change(revision, body, "comparator_loosening")
                ),
                note=f"{surface!r} -> 'approximately' (relation class loosened, deontic held)",
            )
    if revision.setpoint_token:
        body = insert_before(revision.raw_text, revision.setpoint_token, "approximately ")
        if body is not None:
            return MutationApplication(
                descendant_document=revision.document(
                    text=_require_change(revision, body, "comparator_loosening")
                ),
                note=(
                    "'approximately' inserted before the magnitude, leaving the negating "
                    "comparator surface in place"
                ),
            )
    raise OperatorInapplicable(f"{revision.fixture_id} states no comparator to loosen")


def hedge_insertion(revision: Revision, rng: random.Random) -> MutationApplication:
    """A committed hedge enters: formally intact, practically optional."""
    del rng
    return MutationApplication(
        descendant_document=revision.document(text=_tail_insert(revision.raw_text, _HEDGE)),
        note=f"hedge {_HEDGE!r} appended to the matrix clause",
    )


def exception_insertion(revision: Revision, rng: random.Random) -> MutationApplication:
    """An exception narrows when the obligation applies, without changing what it requires."""
    del rng
    return MutationApplication(
        descendant_document=revision.document(text=_tail_insert(revision.raw_text, _EXCEPTION)),
        note=f"exception {_EXCEPTION!r} appended to the matrix clause",
    )


def quantifier_narrowing(revision: Revision, rng: random.Random) -> MutationApplication:
    """``all`` becomes ``selected``: one word, most of the population."""
    del rng
    for surface, replacement in _QUANTIFIER_NARROWINGS:
        pattern = re.compile(rf"\b{re.escape(surface)}\b", re.IGNORECASE)
        body, count = pattern.subn(replacement, revision.raw_text, count=1)
        if count:
            return MutationApplication(
                descendant_document=revision.document(
                    text=_require_change(revision, body, "quantifier_narrowing")
                ),
                note=f"coverage cue {surface!r} -> {replacement!r} (rank all=4 -> selected=2)",
            )
    raise OperatorInapplicable(f"{revision.fixture_id} states no universal coverage cue")


def verification_step_deletion(revision: Revision, rng: random.Random) -> MutationApplication:
    """The independent check, second signature or hold point stops being one.

    The cue phrase is replaced by an innocuous one rather than the whole conjunct
    being deleted.  Deleting the conjunct would also take the clause's conditions
    and coverage cue with it, and three rules firing on a mutation whose class
    claims one makes the per-class kill rate a statement about the operator
    rather than about R6.
    """
    del rng
    for surface, replacement in _VERIFICATION_NEUTRALISERS:
        body = replace_first_ci(revision.raw_text, surface, replacement)
        if body is not None:
            return MutationApplication(
                descendant_document=revision.document(
                    text=_require_change(revision, body, "verification_step_deletion")
                ),
                note=f"verification cue {surface!r} -> {replacement!r}",
            )
    raise OperatorInapplicable(f"{revision.fixture_id} states no verification step to delete")


_INTERVAL_MARKERS: Final[tuple[str, ...]] = ("interval", "intervals of", "every")
_LENGTHEN_FACTOR: Final[int] = 8


def frequency_lengthening(revision: Revision, rng: random.Random) -> MutationApplication:
    """The interval between checks lengthens; the control is exercised less often.

    Applies only where the fixture's magnitude is a *time* and the clause names
    an interval, because ``CAT.frequency`` is populated by the extractor and not
    by this operator: multiplying the magnitude of a clause whose time quantity
    landed in ``value`` would fire R2 (or D6's abstention) and the class would be
    measuring the wrong rule.
    """
    del rng
    lowered = revision.raw_text.lower()
    if not any(marker in lowered for marker in _INTERVAL_MARKERS):
        raise OperatorInapplicable(f"{revision.fixture_id} names no interval")
    if revision.setpoint_unit.lower() not in ("minutes", "minute", "hours", "hour", "min", "h"):
        raise OperatorInapplicable(
            f"{revision.fixture_id}'s magnitude is {revision.setpoint_unit!r}, not a stated "
            "interval in minutes or hours"
        )
    lengthened = Decimal(revision.setpoint_value) * _LENGTHEN_FACTOR
    token = f"{decimal_str(lengthened)} {revision.setpoint_unit}"
    body = replace_first_ci(revision.raw_text, revision.setpoint_token, token)
    if body is None:
        raise OperatorInapplicable(
            f"the declared interval token {revision.setpoint_token!r} is not in "
            f"{revision.fixture_id}'s text"
        )
    return MutationApplication(
        descendant_document=revision.document(
            text=_require_change(revision, body, "frequency_lengthening")
        ),
        note=f"interval {revision.setpoint_token!r} -> {token!r} (x{_LENGTHEN_FACTOR})",
    )


_CITATION_PREAMBLES: Final[tuple[str, ...]] = (
    " in accordance with ",
    " as required by ",
    " under ",
)


def uncompensated_anchor_drop(revision: Revision, rng: random.Random) -> MutationApplication:
    """An identity anchor disappears and nothing of its class arrives.

    ANCHORLOCK is used to LOCATE the anchor; what is being measured is whether
    the pipeline REACTS to its removal.  Those are different questions, and using
    the extractor to find the tag is not circular — an operator that guessed
    where the tag was would drop text that is not an anchor and measure nothing.
    """
    del rng
    anchors = sorted(
        (a for a in extract_anchors(revision.raw_text).items if a.cls in IDENTITY_ANCHOR_CLASSES),
        key=lambda a: (a.span[0], a.cls.value),
    )
    if not anchors:
        raise OperatorInapplicable(f"{revision.fixture_id} carries no identity anchor to drop")
    target = anchors[0]
    body = revision.raw_text
    if target.cls is AnchorClass.REGULATORY_CITATION:
        for preamble in _CITATION_PREAMBLES:
            joined = f"{preamble}{target.raw}"
            trimmed = replace_first_ci(body, joined, "")
            if trimmed is not None:
                return MutationApplication(
                    descendant_document=revision.document(
                        text=_require_change(
                            revision, _tidy(trimmed), "uncompensated_anchor_drop"
                        )
                    ),
                    note=f"citation {target.norm!r} and its preamble removed",
                )
    dropped = replace_first_ci(body, target.raw, "")
    if dropped is None:  # pragma: no cover - the anchor came from this text
        raise OperatorInapplicable(
            f"anchor {target.raw!r} was located in {revision.fixture_id} and then not found"
        )
    return MutationApplication(
        descendant_document=revision.document(
            text=_require_change(revision, _tidy(dropped), "uncompensated_anchor_drop")
        ),
        note=f"{target.cls.value} anchor {target.norm!r} removed with no replacement",
    )


_SPLIT_SEPARATORS: Final[tuple[str, ...]] = (", and ", " and ", ", ")


def clause_split_and_dilute(revision: Revision, rng: random.Random) -> MutationApplication:
    """One clause becomes two; the half a reader sees keeps the subject and loses the force.

    The descendant under test is the FIRST conjunct — the half that keeps the
    equipment tag and the parameter, and therefore the half the matcher will
    recognise as the ancestor.  The obligation-carrying tail is notionally moved
    to a new clause elsewhere in the document, which is why the mutation is not
    an outright deletion and why a reviewer reading the diff sees a tidy-up.
    """
    del rng
    for separator in _SPLIT_SEPARATORS:
        head, sep, tail = revision.raw_text.partition(separator)
        if not sep or not tail.strip():
            continue
        body = _tidy(head) + "."
        if body.strip() == revision.raw_text.strip():
            continue
        return MutationApplication(
            descendant_document=revision.document(text=body),
            note=(
                f"split at {separator!r}; the tail {tail.strip()[:60]!r} was relocated to a "
                "new clause and the head is the version under test"
            ),
        )
    raise OperatorInapplicable(f"{revision.fixture_id} has no conjunct to split at")


_REFLOW_PAD: Final[str] = "  "


def _neutral_step(document: str, step: int) -> str:
    """A reflow-only edit: whitespace the canonicaliser collapses back to nothing.

    Used to pad a salami to its declared length.  It changes the bytes of every
    intermediate revision and no CAT slot at all, which is what makes the
    padding honest: a chain padded with edits that themselves weakened would
    make the composed verdict unattributable to the two comparator moves.
    """
    return document.replace(" and ", f"{_REFLOW_PAD}and{' ' * (1 + step)}", 1)


def _salami(revision: Revision, steps: int) -> MutationApplication:
    if not revision.directrix_ratified or not revision.setpoint_token:
        raise OperatorInapplicable(
            f"{revision.fixture_id} carries no DIRECTRIX-ratified setpoint to compose a salami on"
        )
    surface = next(
        (s for s in _COMPARATOR_SURFACES if s in revision.raw_text.lower()),
        None,
    )
    if surface is None:
        raise OperatorInapplicable(
            f"{revision.fixture_id} states its bound with a negating surface; walking it "
            "through R3's silent cells would flip the deontic and be detected on step one"
        )
    target = _nudged_token(revision, _SALAMI_TOTAL)

    # Step A: comparator family upper -> exact, magnitude moved. R3 is silent on
    # this cell by design; R2 is silent because the family changed.
    exact = replace_first_ci(revision.raw_text, f"must be {surface}", _EXACT_SURFACE)
    if exact is None:
        exact = replace_first_ci(revision.raw_text, surface, "set at")
    if exact is None:  # pragma: no cover - `surface` came from this text
        raise OperatorInapplicable(f"{surface!r} vanished from {revision.fixture_id}")
    step_a = replace_first_ci(exact, revision.setpoint_token, target)
    if step_a is None:
        raise OperatorInapplicable(
            f"the declared setpoint token {revision.setpoint_token!r} is not in "
            f"{revision.fixture_id}'s text"
        )
    # Step B: comparator family exact -> upper, magnitude held. Silent again.
    step_b = replace_first_ci(step_a, _EXACT_SURFACE, f"must be {surface}")
    if step_b is None:  # pragma: no cover - written by step A
        raise OperatorInapplicable("the exact-comparator surface vanished between steps")

    documents = [revision.document(text=step_a), revision.document(text=step_b)]
    while len(documents) < steps:
        documents.insert(0, _neutral_step(revision.document(), len(documents)))
    chain = tuple(documents[:steps]) if len(documents) > steps else tuple(documents)
    return MutationApplication(
        descendant_document=chain[-1],
        chain=chain,
        note=(
            f"{len(chain)}-step chain: {steps - 2} reflow-only revisions, then "
            f"{surface!r} -> 'set at' with {revision.setpoint_token!r} -> {target!r} "
            f"(R3 silent cell, R2 silent on a family change), then 'set at' -> {surface!r}"
        ),
    )


def salami_5(revision: Revision, rng: random.Random) -> MutationApplication:
    """Five steps, every adjacent diff `restate`, the origin diff `weaken`."""
    del rng
    return _salami(revision, _SALAMI_STEPS["salami_5"])


def salami_10(revision: Revision, rng: random.Random) -> MutationApplication:
    """Ten steps.  Same construction, each nudge a tenth of the composition."""
    del rng
    return _salami(revision, _SALAMI_STEPS["salami_10"])


def salami_20(revision: Revision, rng: random.Random) -> MutationApplication:
    """Twenty steps — the case docs/leads/algorithms.md §3 names for ORIGINDIFF."""
    del rng
    return _salami(revision, _SALAMI_STEPS["salami_20"])


def adversarial_paraphrase(revision: Revision, rng: random.Random) -> MutationApplication:
    """A committed cassette's rewrite.  No model is called, here or anywhere."""
    del rng
    entry = paraphrase_for(revision)
    return MutationApplication(
        descendant_document=revision.document(text=entry.paraphrase),
        note=f"cassette {entry.key[:16]} ({entry.provenance}): {entry.adversary_note}",
    )


KILL_OPERATORS: Final[dict[str, Operator]] = {
    "deontic_downgrade": deontic_downgrade,
    "setpoint_nudge_1pct": setpoint_nudge_1pct,
    "setpoint_nudge_5pct": setpoint_nudge_5pct,
    "setpoint_nudge_25pct": setpoint_nudge_25pct,
    "comparator_loosening": comparator_loosening,
    "hedge_insertion": hedge_insertion,
    "exception_insertion": exception_insertion,
    "quantifier_narrowing": quantifier_narrowing,
    "verification_step_deletion": verification_step_deletion,
    "frequency_lengthening": frequency_lengthening,
    "uncompensated_anchor_drop": uncompensated_anchor_drop,
    "clause_split_and_dilute": clause_split_and_dilute,
    "salami_5": salami_5,
    "salami_10": salami_10,
    "salami_20": salami_20,
    "adversarial_paraphrase": adversarial_paraphrase,
}
