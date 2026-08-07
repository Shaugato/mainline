# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Path-A CAT extraction: a deterministic shallow grammar over ``canon_text``.

**No model call.  No network.  No randomness.  No clock.**  This is the
deterministic half of the classifier/verifier pair in
``research/05-architecture/clause-identity.md`` §6.3, and it is the half that
must remain auditable, because principle P7 forbids any component that can
decide a state transition from reaching a model — and the lattice this feeds
*does* decide one.  Path B lives in the physically separate distribution
``mainline-delta-oracle`` and can only ever raise a verdict's force, never lower
it.  A test in ``tests/unit/domain/cat/`` walks this package's AST and fails if
a network or model import appears.

**A shallow grammar, and the shallowness is the point.**  A dependency parser
would be more accurate on average and far less predictable at the margin.
Everything this module consults is a committed, versioned word list whose
behaviour an opposing expert can enumerate exhaustively — closed-class
subordinators, a controlled deontic lexicon, an action vocabulary, a unit table.
Path A has to be *checkable* before it is clever.

The three design rules worth knowing before reading the code:

1. **Negation lives in the deontic, never in the action.**  ``shall not exceed``
   and ``shall remain below`` both extract as ``(MUST_NOT, exceed)``.  Encoding
   one as ``(MUST, not_exceed)`` would give one control two identities, and an
   identity split detaches a blame edge silently — worse than a missed
   weakening, because nothing anywhere goes red.
2. **A unit is never guessed.**  ``shall not exceed 50`` yields ``value=None``
   and ``confidence='low'``, not ``50 kPa``.  A guessed unit is a fabricated
   setpoint, and a fabricated setpoint is compared against ``safe_direction``
   by rule R2 as though it were evidence.
3. **Opacity is a product state, not a retryable failure.**  A table row, a
   figure standing in for a setpoint, or a bare cross-reference yields
   ``confidence='opaque'``.  Any edit to an opaque clause with severity ≥ 4
   ancestry defaults to ``weaken`` (risk R-A3).  This deliberately over-blocks,
   and that is the correct direction of error.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from functools import lru_cache
from typing import Final, Literal

from ..anchors import extract_anchors
from ..contracts import CAT, Anchor, AnchorClass, AnchorSet, CatConfidence, CATResult, Quantity
from .lexicon import Lexicons, lexicon_fingerprint, load_lexicons
from .normalise import normalise_cat, normalise_phrase
from .quantity_bridge import ConverterSpec, QuantityMatch, iter_quantities
from .schema import DEONTIC_ABSENT, EMPTY_CAT, validate_cat
from .version import CAT_EXTRACTOR_VERSION

__all__ = [
    "OPACITY_REASONS",
    "ClauseHint",
    "LayoutKind",
    "extract_cat",
    "extractor_version",
    "opacity_reason",
]

OPACITY_REASONS: Final[tuple[str, ...]] = (
    "layout_hint_table",
    "layout_hint_figure",
    "pipe_delimited_row",
    "bare_cross_reference",
    "control_delegated_to_figure",
    "row_shaped_fragment",
)
"""Every reason :func:`opacity_reason` can give.

All six map to ``cat_confidence='opaque'`` and thence to
``identity_residue.reason='opaque_control'`` — the fourth of the five legal
residue values.  There is no sixth reason and no sixth residue value.
"""

LayoutKind = Literal[
    "paragraph", "table_cell", "table_row", "figure_caption", "list_item", "heading"
]


@dataclass(frozen=True, slots=True)
class ClauseHint:
    """What the ingest layer knows about a clause that its text does not say.

    ``layout_kind`` comes from a layout model (Textract ``LAYOUT_*`` blocks) and
    is strictly better evidence than any string heuristic: ``canon()`` collapses
    every whitespace run to a single space, so a table's column gutters are gone
    by the time this module sees the text, and the pipe character is the only
    in-band table marker left.  Passing the layout kind is how a caller avoids
    relying on that.
    """

    layout_kind: LayoutKind = "paragraph"


def extractor_version() -> str:
    """``'catseal/1+lex.<16 hex>'`` — the extractor **and** the word lists.

    The lexicon fingerprint is in here because a stored CAT must record which
    word lists decided it.  Without that, a lexicon could be edited with no
    version bump and no trace, and whether a phrase counted as a hedge would
    depend on which checkout ran the extractor — which makes an R4 hedge-entry
    finding unfalsifiable.
    """
    return f"catseal/{CAT_EXTRACTOR_VERSION}+lex.{lexicon_fingerprint().hex()[:16]}"


# --------------------------------------------------------------------------- #
# Phrase matching                                                              #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class _Hit:
    start: int
    end: int
    phrase: str

    @property
    def span(self) -> tuple[int, int]:
        return (self.start, self.end)


def _boundaried(phrase: str) -> str:
    r"""Escape a phrase, adding word boundaries only where they make sense.

    ``\b`` is wrong for this vocabulary: it would break ``<=``, ``+/-`` and
    ``%``.  Worse, a trailing boundary on ``<=`` would refuse to match ``<=50``,
    which is the commonest way a comparator is written.  So the lookarounds are
    attached per-end, and only when that end is alphanumeric.
    """
    prefix = r"(?<![A-Za-z0-9])" if phrase[:1].isalnum() else ""
    suffix = r"(?![A-Za-z0-9])" if phrase[-1:].isalnum() else ""
    return prefix + re.escape(phrase) + suffix


@lru_cache(maxsize=64)
def _pattern(phrases: tuple[str, ...]) -> re.Pattern[str]:
    """Compile a longest-first alternation.

    Python's ``|`` is ordered — it takes the first alternative that matches at a
    position — so a longest-first list gives longest-match semantics.  That
    ordering is what makes ``'shall not'`` beat ``'shall'``.  Getting it wrong
    turns every prohibition in a corpus into an obligation, which inverts the
    control; it is the single worst bug available in this module.
    """
    return re.compile("|".join(_boundaried(phrase) for phrase in phrases), re.IGNORECASE)


def _find_all(
    text: str, phrases: tuple[str, ...], start: int = 0, end: int | None = None
) -> list[_Hit]:
    """Every non-overlapping longest-first hit within ``text[start:end]``."""
    if not phrases:
        return []
    stop = len(text) if end is None else end
    if start >= stop:
        return []
    return [
        _Hit(start=match.start(), end=match.end(), phrase=match.group(0).casefold())
        for match in _pattern(phrases).finditer(text, start, stop)
    ]


def _first(
    text: str, phrases: tuple[str, ...], start: int = 0, end: int | None = None
) -> _Hit | None:
    hits = _find_all(text, phrases, start, end)
    return hits[0] if hits else None


# --------------------------------------------------------------------------- #
# Carving: matrix vs subordinate                                               #
# --------------------------------------------------------------------------- #

_CHUNK_BREAK: Final[re.Pattern[str]] = re.compile(r"[;,]")


@dataclass(frozen=True, slots=True)
class _Carved:
    matrix: tuple[tuple[int, int], ...]
    conditions: tuple[tuple[int, int], ...]
    exceptions: tuple[tuple[int, int], ...]

    def in_matrix(self, position: int) -> bool:
        return any(start <= position < end for start, end in self.matrix)


def _carve(text: str, lexicons: Lexicons) -> _Carved:
    """Split a clause into matrix, condition and exception spans.

    The rule is deliberately mechanical: break on ``,`` and ``;``; within each
    chunk find the earliest subordinator; everything from it to the chunk's end
    is subordinate, everything before it stays matrix.  A leading ``If X,`` is
    therefore a whole subordinate chunk and a trailing ``unless X`` is a
    subordinate tail, which is how both actually appear in procedures.

    Exceptions are checked before conditions at the same position: ``'unless
    and until'`` is listed as a condition and ``'unless'`` as an exception, and
    without that precedence the longer conditional reading would swallow the
    exception.
    """
    grammar = lexicons.grammar
    matrix: list[tuple[int, int]] = []
    conditions: list[tuple[int, int]] = []
    exceptions: list[tuple[int, int]] = []

    cursor = 0
    boundaries = [match.start() for match in _CHUNK_BREAK.finditer(text)] + [len(text)]
    for boundary in boundaries:
        chunk_start, chunk_end = cursor, boundary
        cursor = boundary + 1
        if chunk_start >= chunk_end:
            continue
        condition_hit = _first(text, grammar.condition_subordinators, chunk_start, chunk_end)
        exception_hit = _first(text, grammar.exception_subordinators, chunk_start, chunk_end)
        # Earliest wins; a tie goes to the exception, which is the stronger claim.
        hit: _Hit | None
        kind: str
        if exception_hit is not None and (
            condition_hit is None or exception_hit.start <= condition_hit.start
        ):
            hit, kind = exception_hit, "exception"
        elif condition_hit is not None:
            hit, kind = condition_hit, "condition"
        else:
            hit, kind = None, ""
        if hit is None:
            matrix.append((chunk_start, chunk_end))
            continue
        if hit.start > chunk_start:
            matrix.append((chunk_start, hit.start))
        target = exceptions if kind == "exception" else conditions
        target.append((hit.end, chunk_end))
    return _Carved(matrix=tuple(matrix), conditions=tuple(conditions), exceptions=tuple(exceptions))


# --------------------------------------------------------------------------- #
# Opacity                                                                      #
# --------------------------------------------------------------------------- #

_WORD: Final[re.Pattern[str]] = re.compile(r"[^\s]+")

# NO leading `^`.  `Pattern.match(string, pos)` already anchors at `pos`, and in
# Python `^` does *not* match at a non-zero `pos` — it only matches at the real
# start of the string (or after a newline under MULTILINE).  A `^` here silently
# disables passive detection for every clause, which reads as every passive
# obligation acquiring its own grammatical subject as its actor.
_PASSIVE_BE: Final[re.Pattern[str]] = re.compile(
    r"\s*(?:not\s+)?(?:be|been|being)\b", re.IGNORECASE
)
_BY_AGENT: Final[re.Pattern[str]] = re.compile(r"\bby\b", re.IGNORECASE)


def _layout_opacity(hint: ClauseHint) -> str | None:
    """Opacity the ingest layer already knows about, before any string is read."""
    if hint.layout_kind in ("table_cell", "table_row"):
        return "layout_hint_table"
    if hint.layout_kind == "figure_caption":
        return "layout_hint_figure"
    return None


def _delegated_to_figure(text: str, lexicons: Lexicons) -> bool:
    """Report whether a drawing stands in for the control itself.

    Requires a *delegation phrase* immediately before the figure cue.  Without
    that, "recorded in Table 4" would make every clause mentioning a table
    opaque, and over-blocking that broad breaches the nuisance ceiling in risk
    R-A7 — at which point the rule gets switched off, which is worse than a
    narrower one.
    """
    grammar = lexicons.grammar
    for figure in _find_all(text, grammar.figure_cues):
        window_start = max(0, figure.start - 24)
        delegators = _find_all(text, grammar.cross_reference_openers, window_start, figure.start)
        if delegators and text[delegators[-1].end : figure.start].strip(" ") == "":
            return True
    return False


def _opacity(
    text: str,
    hint: ClauseHint,
    lexicons: Lexicons,
    deontic_hits: Sequence[_Hit],
    quantities: Sequence[QuantityMatch],
) -> str | None:
    """Return the opacity reason, or ``None``.  Checked before anything else."""
    layout = _layout_opacity(hint)
    if layout is not None:
        return layout

    grammar = lexicons.grammar
    cells = [cell for cell in text.split(grammar.cell_delimiter) if cell.strip()]
    if grammar.cell_delimiter in text and len(cells) >= grammar.min_cells:
        return "pipe_delimited_row"

    # A clause whose whole content is a pointer elsewhere.
    opener = _first(text, grammar.cross_reference_openers)
    if opener is not None and opener.start == 0 and not deontic_hits:
        return "bare_cross_reference"

    if not quantities and _delegated_to_figure(text, lexicons):
        return "control_delegated_to_figure"

    # A row-shaped fragment that survived as prose: no modality anywhere, several
    # quantities, very few words.
    row_shaped = (
        not deontic_hits
        and len(quantities) >= grammar.row_min_quantities
        and len(_WORD.findall(text)) <= grammar.row_max_words
    )
    return "row_shaped_fragment" if row_shaped else None


def opacity_reason(canon_text: str, hint: ClauseHint | None = None) -> str | None:
    """Why this clause is ``'opaque'``, or ``None`` if it is readable.

    Public because "the extractor could not read it" is a fact an adjudicator is
    entitled to see the reason for.  A residue row saying ``opaque_control`` and
    nothing else asks a human to guess what the machine choked on; one that can
    be joined to ``control_delegated_to_figure`` tells them to go and look at
    the drawing.
    """
    lexicons = load_lexicons()
    hint = hint or ClauseHint()
    if not canon_text.strip():
        return "row_shaped_fragment"
    return _opacity(
        canon_text,
        hint,
        lexicons,
        _find_all(canon_text, lexicons.deontic.cue_order),
        list(iter_quantities(canon_text)),
    )


# --------------------------------------------------------------------------- #
# Slot resolution                                                              #
# --------------------------------------------------------------------------- #

_POLARITY_FLIP: Final[Mapping[str, str]] = {
    "MUST": "MUST_NOT",
    "MUST_NOT": "MUST",
    "SHOULD": "SHOULD_NOT",
    "SHOULD_NOT": "SHOULD",
    # A negated permission is a prohibition; a negated absence is still absence.
    "MAY": "MUST_NOT",
    DEONTIC_ABSENT: DEONTIC_ABSENT,
}

_ANCHOR_OBJECT_CLASS: Final[Mapping[AnchorClass, str]] = {
    AnchorClass.EQUIPMENT_TAG: "plant",
    AnchorClass.ISOLATION_POINT_ID: "isolation_point",
    AnchorClass.INSTRUMENT_LOOP: "instrument_loop",
}


def _anchors_in(anchor_set: AnchorSet, start: int, end: int) -> list[Anchor]:
    inside = [a for a in anchor_set.items if start <= a.span[0] and a.span[1] <= end]
    return sorted(inside, key=lambda a: (a.span[0], a.span[1], a.norm))


def _resolve_actor(
    text: str, regions: Sequence[tuple[int, int]], anchor_set: AnchorSet, lexicons: Lexicons
) -> tuple[str, tuple[int, int] | None]:
    """Resolve the actor, which is a **role** or else ``unspecified``.

    Resolution is closed: a ``named_role`` anchor from the committed ANCHORLOCK
    gazetteer, or a phrase from the small generic-actor list.  There is
    deliberately **no** fall-back to "whatever noun phrase preceded the
    modality", and that omission is doing real work.

    Two reasons.  First, most safety clauses are stative or passive — "the
    operating pressure shall not exceed 1750 kPa", "the vessel shall be
    isolated" — and in both the pre-modality noun phrase is the thing being
    controlled, not the person bound.  A noun-phrase fallback would file the
    controlled object under ``actor`` and leave ``object_class`` empty, which
    scrambles two slots at once.  Second, ``actor`` is a *closed* slot whose
    value enters the ``cat_key``: letting arbitrary prose into it means a
    reworded subject re-keys the obligation, and identity axis 2 exists
    precisely to survive rewording.

    ``unspecified`` is the honest answer to "this clause does not say who", and
    it is a value the lattice can compare.
    """
    for start, end in regions:
        if start >= end:
            continue
        roles = [a for a in _anchors_in(anchor_set, start, end) if a.cls is AnchorClass.NAMED_ROLE]
        if roles:
            # Nearest role to the modality: "the supervisor and the operator
            # shall" binds the one the verb agrees with.
            return roles[-1].norm, roles[-1].span
        generic = _find_all(text, lexicons.slots.actor_generic, start, end)
        if generic:
            return generic[-1].phrase, generic[-1].span
    return lexicons.slots.actor_unspecified, None


def _by_agent_region(text: str, start: int, end: int) -> tuple[int, int] | None:
    """Return the span after a passive ``by``, where a named agent hides.

    "The relief valve shall be inspected **by a competent person**" names its
    actor; without this the clause reads as having none, and "nobody in
    particular must inspect it" is a materially different obligation from
    "a competent person must".
    """
    match = _BY_AGENT.search(text, start, end)
    return (match.end(), end) if match is not None else None


def _resolve_object(
    text: str, regions: Sequence[tuple[int, int]], anchor_set: AnchorSet, lexicons: Lexicons
) -> tuple[str, tuple[int, int] | None]:
    for start, end in regions:
        if start >= end:
            continue
        hits = _find_all(text, lexicons.slots.object_class_order, start, end)
        if hits:
            return lexicons.slots.object_class[hits[0].phrase], hits[0].span
    for start, end in regions:
        for anchor in _anchors_in(anchor_set, start, end):
            mapped = _ANCHOR_OBJECT_CLASS.get(anchor.cls)
            if mapped is not None:
                return mapped, anchor.span
    return "", None


def _resolve_hazard(text: str, lexicons: Lexicons) -> tuple[str, tuple[int, int] | None]:
    """First class in the declared priority order whose cues appear."""
    for hazard_class in lexicons.slots.hazard_priority:
        hit = _first(text, lexicons.slots.hazard_cues[hazard_class])
        if hit is not None:
            return hazard_class, hit.span
    return "", None


def _resolve_quantifier(text: str, lexicons: Lexicons) -> tuple[str, tuple[int, int] | None]:
    slots = lexicons.slots
    by_class: dict[str, _Hit] = {}
    for hit in _find_all(text, slots.quantifier_order):
        cls = slots.quantifier[hit.phrase]
        by_class.setdefault(cls, hit)
    for cls in slots.quantifier_precedence:
        if cls in by_class:
            return cls, by_class[cls].span
    return slots.quantifier_default, None


def _resolve_verification(
    text: str, lexicons: Lexicons
) -> tuple[tuple[str, ...], tuple[tuple[int, int], ...]]:
    """Verification cues collapse to their KEY, not their surface form.

    Rule R6 fires on a *deleted* independent check.  If the slot held surface
    text, renaming a "hold point" to a "witness point" would look like one
    verification removed and another added, and R6 would fire on a rewording.
    The key is what survives a rewrite, which is exactly what identity axis 2 is
    supposed to hold.
    """
    keys: list[str] = []
    spans: list[tuple[int, int]] = []
    for hit in _find_all(text, lexicons.slots.verification_order):
        keys.append(lexicons.slots.verification[hit.phrase])
        spans.append(hit.span)
    return tuple(keys), tuple(spans)


# --------------------------------------------------------------------------- #
# Setpoint and frequency                                                       #
# --------------------------------------------------------------------------- #

_COMPARATOR_WINDOW: Final[int] = 48
_FREQUENCY_WINDOW: Final[int] = 40


@dataclass(frozen=True, slots=True)
class _Setpoint:
    parameter: str
    comparator: str
    value: Quantity | None
    spans: tuple[tuple[int, int], ...]
    asserted: bool
    """True when the clause asserts a setpoint at all — a parameter phrase, a
    comparator, or a quantity was found.  Used to decide ``'low'``."""
    lossy_range: bool
    comparator_inferred: bool
    """A value was found with no comparator phrase, so ``'='`` was assumed."""


def _pick_comparator(text: str, value_start: int, lexicons: Lexicons) -> _Hit | None:
    """Longest comparator phrase fully inside the window before the value.

    Longest-wins rather than nearest-wins, because ``'a maximum of 50 kPa'``
    contains both ``'maximum of'`` (``<=``) and ``'of'`` (``=``) and the nearer
    one is the wrong one.  Ties break to the later match, which is the nearer.
    """
    window_start = max(0, value_start - _COMPARATOR_WINDOW)
    hits = _find_all(text, lexicons.grammar.comparator_order, window_start, value_start)
    if not hits:
        return None
    return max(hits, key=lambda hit: (len(hit.phrase), hit.start))


def _is_frequency(text: str, match: QuantityMatch, lexicons: Lexicons) -> bool:
    """Report whether a time quantity is an interval rather than a setpoint.

    A time quantity introduced by a frequency phrase is an interval; one that is
    not — "the permit shall be valid for no more than 12 hours" — is a setpoint.
    """
    if match.quantity.dimension not in ("time", "event"):
        return False
    window_start = max(0, match.span[0] - _FREQUENCY_WINDOW)
    return bool(
        _find_all(text, lexicons.grammar.frequency_introducers, window_start, match.span[0])
    )


def _named_frequency(
    text: str, lexicons: Lexicons
) -> tuple[Quantity | None, tuple[int, int] | None]:
    grammar = lexicons.grammar
    units = lexicons.units
    hit = _first(text, grammar.named_frequency_order)
    if hit is None:
        event = _first(text, grammar.event_anchored)
        if event is None:
            return None, None
        # "prior to each use" is not a duration at all.  It becomes the unit
        # `use`, which no converter knows, so identity stays exact while the
        # lattice is required to treat the comparison as unknown (spec §10).
        return (
            Quantity(value=Decimal("1"), unit="use", dimension="event", reference="none"),
            event.span,
        )
    named = grammar.named_frequency[hit.phrase]
    dimension = units.dimension.get(named.unit)
    if dimension is None:  # pragma: no cover - the loader validates this
        return None, None
    return (
        Quantity(value=named.value, unit=named.unit, dimension=dimension, reference="none"),
        hit.span,
    )


def _resolve_setpoint(
    text: str, quantities: Sequence[QuantityMatch], lexicons: Lexicons
) -> _Setpoint:
    parameter_hits = _find_all(text, lexicons.parameters.synonym_order)
    setpoint_candidates = [q for q in quantities if not _is_frequency(text, q, lexicons)]

    chosen: QuantityMatch | None = setpoint_candidates[0] if setpoint_candidates else None
    if chosen is not None and parameter_hits and len(setpoint_candidates) > 1:
        # Several quantities: take the one nearest a named parameter, because
        # "the pressure shall not exceed 1750 kPa for more than 30 minutes"
        # has two and only one of them is the setpoint.
        chosen = min(
            setpoint_candidates,
            key=lambda q: min(abs(q.span[0] - hit.start) for hit in parameter_hits),
        )

    spans: list[tuple[int, int]] = []
    parameter = ""
    if parameter_hits:
        best = parameter_hits[0]
        if chosen is not None:
            best = min(parameter_hits, key=lambda hit: abs(hit.start - chosen.span[0]))
        parameter = lexicons.parameters.synonym[best.phrase]
        spans.append(best.span)

    comparator = ""
    lossy_range = False
    comparator_inferred = False
    if chosen is not None:
        comparator_hit = _pick_comparator(text, chosen.span[0], lexicons)
        if comparator_hit is not None:
            comparator = lexicons.grammar.comparator[comparator_hit.phrase]
            spans.append(comparator_hit.span)
        else:
            # A stated value with no stated relation.  '=' is the only reading
            # available, and the extraction is 'low' because it was inferred
            # rather than read off a span — a comparator is exactly the slot
            # rule R3 orders, so an inferred one must never look like evidence.
            comparator = "="
            comparator_inferred = True
        if comparator == "range":
            lossy_range = True
        spans.append(chosen.span)
        if chosen.reference_span is not None:
            spans.append(chosen.reference_span)
    else:
        comparator_hit = _first(text, lexicons.grammar.comparator_order)
        if comparator_hit is not None and parameter:
            comparator = lexicons.grammar.comparator[comparator_hit.phrase]
            spans.append(comparator_hit.span)

    asserted = bool(parameter_hits) or chosen is not None or bool(comparator)
    return _Setpoint(
        parameter=parameter,
        comparator=comparator,
        value=chosen.quantity if chosen is not None else None,
        spans=tuple(spans),
        asserted=asserted,
        lossy_range=lossy_range,
        comparator_inferred=comparator_inferred,
    )


# --------------------------------------------------------------------------- #
# The extractor                                                                #
# --------------------------------------------------------------------------- #


def _subordinate_texts(
    text: str, spans: Iterable[tuple[int, int]], hedges: Iterable[str] = ()
) -> list[str]:
    """Normalised text of subordinate spans, subordinator already stripped.

    The subordinator is dropped by :func:`_carve` (the span starts after it), so
    ``'unless the space is purged'`` and ``'except where the space is purged'``
    both yield ``'the space is purged'``.  Without that, rule R4 would fire on a
    rewording — one exception removed, one added — and a rule that fires on
    rewordings gets switched off.

    A span whose whole normalised text sits inside a matched hedge is dropped.
    ``'where practicable'`` is both a subordinator and a hedge, so without this
    the clause emits a condition ``'practicable'`` *and* an exception
    ``'where practicable'`` for one phrase.  The hedge is the better record: it
    is the closed-vocabulary form R4 was built to see.
    """
    hedge_texts = tuple(hedges)
    out: list[str] = []
    for start, end in spans:
        phrase = normalise_phrase(text[start:end])
        if not phrase:
            continue
        if any(phrase in hedge for hedge in hedge_texts):
            continue
        out.append(phrase)
    return out


def _confidence_reasons(setpoint: _Setpoint, deontic: str, action: str) -> list[str]:
    """List the reasons this extraction is ``'low'`` rather than ``'ok'``.

    The governing rule is the brief's: where the extractor cannot fill
    ``parameter``, ``comparator`` or ``value`` from a verifiable evidence span,
    the result is ``'low'``.  "Asserted but incomplete" is the honest reading of
    a clause that plainly states a setpoint the extractor could only half read —
    the alternative is an ``'ok'`` CAT with a hole in it, which rule R2 would
    then diff as though the hole were a fact.
    """
    reasons: list[str] = []
    if setpoint.asserted and not (setpoint.parameter and setpoint.comparator and setpoint.value):
        reasons.append("incomplete_setpoint")
    if setpoint.lossy_range:
        reasons.append("range_lower_bound_only")
    if setpoint.comparator_inferred:
        reasons.append("comparator_inferred")
    if deontic == DEONTIC_ABSENT and not action:
        reasons.append("no_modality_and_no_action")
    return reasons


@dataclass(frozen=True, slots=True)
class _Participants:
    """Who is bound, and what the action is performed on."""

    actor: str
    object_class: str
    spans: tuple[tuple[int, int], ...]


def _resolve_participants(
    text: str,
    modality: _Modality,
    predicate: _Predicate,
    anchor_set: AnchorSet,
    lexicons: Lexicons,
) -> _Participants:
    """Resolve actor and object, keeping the two from claiming the same phrase."""
    # Actor regions, in preference order.  A passive clause names its agent
    # after `by`, if it names one at all; otherwise the pre-modality region is
    # the only place a role can be.
    actor_regions: list[tuple[int, int]] = []
    if modality.passive:
        by_region = _by_agent_region(text, predicate.action_end, modality.post_end)
        if by_region is not None:
            actor_regions.append(by_region)
    actor_regions.append((modality.pre_start, modality.pre_end))
    actor, actor_span = _resolve_actor(text, actor_regions, anchor_set, lexicons)

    # The pre-modality region is an object candidate whenever it did not supply
    # the actor: in "the vessel shall be isolated" and in "the operating pressure
    # shall not exceed 1750 kPa" alike, that noun phrase is the thing being
    # controlled, and letting both slots claim it scrambles two at once.
    object_regions: list[tuple[int, int]] = [(predicate.action_end, modality.post_end)]
    if actor_span is None or not (modality.pre_start <= actor_span[0] < modality.pre_end):
        object_regions.insert(0, (modality.pre_start, modality.pre_end))
    object_class, object_span = _resolve_object(text, object_regions, anchor_set, lexicons)

    spans = tuple(span for span in (actor_span, object_span) if span is not None)
    return _Participants(actor=actor, object_class=object_class, spans=spans)


def _resolve_frequency(
    text: str, quantities: Sequence[QuantityMatch], lexicons: Lexicons
) -> tuple[Quantity | None, tuple[tuple[int, int], ...]]:
    """Find the clause's interval: an explicit one first, then a named one."""
    for match in quantities:
        if _is_frequency(text, match, lexicons):
            return match.quantity, (match.span,)
    frequency, span = _named_frequency(text, lexicons)
    return frequency, () if span is None else (span,)


@dataclass(frozen=True, slots=True)
class _Qualifiers:
    """Conditions and exceptions, with the hedges folded into the exceptions."""

    conditions: tuple[str, ...]
    exceptions: tuple[str, ...]
    spans: tuple[tuple[int, int], ...]
    reasons: tuple[str, ...]


def _resolve_qualifiers(text: str, carved: _Carved, lexicons: Lexicons) -> _Qualifiers:
    """Collect conditions and exceptions, adding every hedge to the exceptions.

    Hedges belong in ``exceptions[]`` because that is the slot rule R4 diffs for
    *growth*, and a hedge entering a clause is one of the commonest real
    weakenings in a mining corpus — precisely because it does not look like one.
    """
    hedge_hits = _find_all(text, lexicons.hedges.phrases)
    hedge_texts = [normalise_phrase(hit.phrase) for hit in hedge_hits]
    conditions = _subordinate_texts(text, carved.conditions, hedge_texts)
    exceptions = _subordinate_texts(text, carved.exceptions, hedge_texts)
    spans: list[tuple[int, int]] = list(carved.conditions) + list(carved.exceptions)
    reasons: list[str] = []
    for hit, hedge_text in zip(hedge_hits, hedge_texts, strict=True):
        exceptions.append(hedge_text)
        spans.append(hit.span)
        if hit.phrase in lexicons.hedges.force_low:
            reasons.append("discretionary_hedge")
    return _Qualifiers(
        conditions=tuple(conditions),
        exceptions=tuple(exceptions),
        spans=tuple(spans),
        reasons=tuple(reasons),
    )


@dataclass(frozen=True, slots=True)
class _Modality:
    """Where the clause's modality is, and how it splits the matrix around it."""

    deontic: str
    passive: bool
    pre_start: int
    pre_end: int
    post_start: int
    post_end: int
    spans: tuple[tuple[int, int], ...]
    reasons: tuple[str, ...]


def _resolve_modality(
    text: str, carved: _Carved, deontic_hits: Sequence[_Hit], lexicons: Lexicons
) -> _Modality:
    """Pick the clause's deontic and split the matrix chunk around it.

    The deontic of record comes from the MATRIX span.  A cue occurring only
    inside a condition or an exception is not the clause's modality — "the
    permit may be extended, unless a gas test **must** be repeated" is a
    permission, not an obligation — so falling back to such a cue lowers the
    confidence rather than passing silently.
    """
    matrix_hits = [hit for hit in deontic_hits if carved.in_matrix(hit.start)]
    hit = matrix_hits[0] if matrix_hits else (deontic_hits[0] if deontic_hits else None)
    spans: list[tuple[int, int]] = []
    reasons: list[str] = []
    if hit is None:
        deontic = DEONTIC_ABSENT
    else:
        deontic = lexicons.deontic.cue_label[hit.phrase]
        spans.append(hit.span)
        if not matrix_hits:
            reasons.append("deontic_outside_matrix")

    default_chunk = carved.matrix[0] if carved.matrix else (0, len(text))
    chunk = next(
        (
            (start, end)
            for start, end in carved.matrix
            if hit is not None and start <= hit.start < end
        ),
        default_chunk,
    )
    pre_start = chunk[0]
    pre_end = hit.start if hit is not None else chunk[0]
    post_start = hit.end if hit is not None else chunk[0]
    post_end = chunk[1]

    skip = _PASSIVE_BE.match(text, post_start, post_end)
    if skip is not None:
        post_start = skip.end()
    return _Modality(
        deontic=deontic,
        passive=skip is not None,
        pre_start=pre_start,
        pre_end=pre_end,
        post_start=post_start,
        post_end=post_end,
        spans=tuple(spans),
        reasons=tuple(reasons),
    )


@dataclass(frozen=True, slots=True)
class _Predicate:
    """The action, and whether reading it flipped the clause's polarity."""

    action: str
    flips_polarity: bool
    action_end: int
    spans: tuple[tuple[int, int], ...]


def _resolve_predicate(text: str, modality: _Modality, lexicons: Lexicons) -> _Predicate:
    """Resolve the action, folding any negation into the deontic's polarity."""
    slots = lexicons.slots
    action = ""
    flips = False
    action_end = modality.post_start
    spans: list[tuple[int, int]] = []

    negating = _first(text, slots.action_negating_order, modality.post_start, modality.post_end)
    positive = _first(text, slots.action_order, modality.post_start, modality.post_end)
    if negating is not None and (positive is None or negating.start <= positive.start):
        action = slots.action_negating[negating.phrase]
        flips = True
        spans.append(negating.span)
        action_end = negating.end
    elif positive is not None:
        action = slots.action[positive.phrase]
        spans.append(positive.span)
        action_end = positive.end

    if action == "" or action in slots.action_light:
        # Nominalised predicate: "gas testing shall be carried out", "ventilation
        # shall be provided".  The verb the obligation binds is in the SUBJECT and
        # the post-modality verb is a light one carrying no control content.  Left
        # alone, half the corpus extracts action='perform' and two clauses about
        # entirely different controls collide on identity axis 2 — which is worse
        # than an empty slot, because a collision moves a blame edge.
        nominal = _first(text, slots.action_order, modality.pre_start, modality.pre_end)
        if nominal is not None and slots.action[nominal.phrase] not in slots.action_light:
            action = slots.action[nominal.phrase]
            spans.append(nominal.span)
    return _Predicate(
        action=action, flips_polarity=flips, action_end=action_end, spans=tuple(spans)
    )


def extract_cat(
    canon_text: str,
    *,
    anchors: AnchorSet | None = None,
    hint: ClauseHint | None = None,
    converter: ConverterSpec = None,
) -> CATResult:
    """Extract a Control Assertion Tuple from one canonicalised clause.

    :param canon_text: the clause's ``canon_text``.  Every span this function
        reports is a half-open offset into *this* string.
    :param anchors: the clause's ANCHORLOCK anchor set.  Extracted here if not
        supplied; pass the one already computed to avoid doing it twice.
    :param hint: what the ingest layer knows that the text does not say.
    :param converter: W2's SI converter, or ``None`` to leave units as written.
        See :func:`mainline_domain.cat.normalise.normalise_cat` — never pass
        ``'auto'`` where the resulting ``cat_key`` will be stored.

    Returns a :class:`~mainline_domain.contracts.CATResult`.  ``cat`` is ``None``
    only when the text carries no clause at all; an unreadable clause returns a
    CAT with ``confidence='opaque'``, because "we looked and could not read it"
    is a different, louder fact than "there was nothing to look at".
    """
    lexicons = load_lexicons()
    hint = hint or ClauseHint()
    version = extractor_version()
    text = canon_text

    if not text.strip():
        return CATResult(
            cat=None, confidence="opaque", evidence_spans=(), extractor_version=version
        )

    anchor_set = anchors if anchors is not None else extract_anchors(text)
    quantities = list(iter_quantities(text))
    deontic_hits = _find_all(text, lexicons.deontic.cue_order)

    if _opacity(text, hint, lexicons, deontic_hits, quantities) is not None:
        # The zero CAT, not None: "we looked and could not read it" is a
        # different and louder fact than "there was nothing to look at", and
        # only the first one carries a cat_key that an opaque-clause edit can
        # be pinned to.  Ask opacity_reason() for the why.
        return CATResult(
            cat=EMPTY_CAT,
            confidence="opaque",
            evidence_spans=(),
            extractor_version=version,
        )

    carved = _carve(text, lexicons)
    spans: list[tuple[int, int]] = []
    reasons: list[str] = []

    modality = _resolve_modality(text, carved, deontic_hits, lexicons)
    deontic = modality.deontic
    spans.extend(modality.spans)
    reasons.extend(modality.reasons)

    predicate = _resolve_predicate(text, modality, lexicons)
    action = predicate.action
    if predicate.flips_polarity:
        deontic = _POLARITY_FLIP[deontic]
    spans.extend(predicate.spans)

    participants = _resolve_participants(text, modality, predicate, anchor_set, lexicons)
    actor, object_class = participants.actor, participants.object_class
    spans.extend(participants.spans)

    hazard_energy, hazard_span = _resolve_hazard(text, lexicons)
    if hazard_span is not None:
        spans.append(hazard_span)

    coverage_quantifier, quantifier_span = _resolve_quantifier(text, lexicons)
    if quantifier_span is not None:
        spans.append(quantifier_span)

    # --- setpoint --------------------------------------------------------- #
    setpoint = _resolve_setpoint(text, quantities, lexicons)
    spans.extend(setpoint.spans)

    frequency, frequency_spans = _resolve_frequency(text, quantities, lexicons)
    spans.extend(frequency_spans)

    qualifiers = _resolve_qualifiers(text, carved, lexicons)
    conditions, exceptions = qualifiers.conditions, qualifiers.exceptions
    spans.extend(qualifiers.spans)
    reasons.extend(qualifiers.reasons)

    verification, verification_spans = _resolve_verification(text, lexicons)
    spans.extend(verification_spans)

    reasons.extend(_confidence_reasons(setpoint, deontic, action))
    confidence: CatConfidence = "low" if reasons else "ok"

    cat = CAT(
        actor=actor,
        deontic=deontic,
        action=action,
        object_class=object_class,
        hazard_energy=hazard_energy,
        parameter=setpoint.parameter,
        comparator=setpoint.comparator,
        value=setpoint.value,
        conditions=tuple(conditions),
        exceptions=tuple(exceptions),
        verification=verification,
        frequency=frequency,
        coverage_quantifier=coverage_quantifier,
    )
    normalised = normalise_cat(cat, converter)
    validate_cat(normalised)
    return CATResult(
        cat=normalised,
        confidence=confidence,
        evidence_spans=tuple(sorted({span for span in spans if span[0] < span[1]})),
        extractor_version=version,
    )
