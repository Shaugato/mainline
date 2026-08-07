# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Loader for the committed CATSEAL lexicons.

Five TOML files under ``mainline_domain/data/lexicon/``, loaded once, cached,
never fetched.  Every loader is strict: a malformed or missing file raises at
load rather than degrading to an empty vocabulary, because an empty deontic
lexicon does not fail — it quietly labels every obligation in the corpus
``ABSENT``, which is the weakest rung of rule R1 and therefore turns every
subsequent edit into a non-event.

**Versioned and fingerprinted**, following the discipline W1 set for the
ANCHORLOCK gazetteers.  Each file declares an integer ``version`` and the loader
*reads* it — a declared version nothing reads is decoration.  The five files'
``(name, version, sha256(bytes))`` triples fold into one 32-byte
:func:`lexicon_fingerprint`, which is stamped into
:attr:`~mainline_domain.contracts.CATResult.extractor_version` so a stored CAT
records *which word lists decided it*.  Without that, a lexicon could be edited
with no version bump and no trace, and whether a phrase counted as a hedge would
depend on which checkout ran the extractor — which makes an R4 hedge-entry
finding unfalsifiable.

The fingerprint covers the **bytes of the committed files**, not the parsed
entries, so a comment-only edit moves it.  That is deliberate and matches W1:
the question the fingerprint answers is "which bytes were in the tree", because
those bytes are what an opposing expert would be handed.
"""

from __future__ import annotations

import hashlib
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from functools import lru_cache
from typing import Any, Final

from ..data import data_file

__all__ = [
    "LEXICON_FINGERPRINT_DOMAIN",
    "Deontic",
    "Grammar",
    "Hedges",
    "Lexicons",
    "NamedFrequency",
    "Parameters",
    "Slots",
    "UnitClasses",
    "lexicon_fingerprint",
    "load_lexicons",
]

LEXICON_FINGERPRINT_DOMAIN: Final[bytes] = b"mainline/cat/lexicon/v1"

_DEONTIC: Final[tuple[str, ...]] = ("lexicon", "deontic.toml")
_HEDGE: Final[tuple[str, ...]] = ("lexicon", "hedge.toml")
_SLOTS: Final[tuple[str, ...]] = ("lexicon", "slots.toml")
_GRAMMAR: Final[tuple[str, ...]] = ("lexicon", "grammar.toml")
_UNITS: Final[tuple[str, ...]] = ("lexicon", "unit-class.toml")
_PARAMETERS: Final[tuple[str, ...]] = ("lexicon", "parameter.toml")

_FILES: Final[tuple[tuple[str, ...], ...]] = (
    _DEONTIC,
    _HEDGE,
    _SLOTS,
    _GRAMMAR,
    _UNITS,
    _PARAMETERS,
)

# The version each file must declare.  A bump here without a bump in the file
# (or vice versa) is a hard error, so a lexicon cannot be reshaped in place.
_EXPECTED_VERSION: Final[int] = 1


def _read(parts: tuple[str, ...]) -> dict[str, Any]:
    with data_file(*parts).open("rb") as handle:
        return tomllib.load(handle)


def _table(doc: Mapping[str, Any], key: str, where: str) -> Mapping[str, Any]:
    """Return a required sub-table, raising if it is absent or the wrong shape.

    One helper rather than eighteen inline ``isinstance`` guards, so the shape
    contract of a lexicon file is stated once and every file is held to it
    identically.  A ``TypeError`` is the honest class here: the TOML parsed, and
    the value it produced is not the kind of thing the loader can use.
    """
    value = doc.get(key)
    if not isinstance(value, Mapping):
        raise TypeError(f"{where}: [{key}] must be a table, got {type(value).__name__}")
    return value


def _require_version(doc: Mapping[str, Any], table: str, path: tuple[str, ...]) -> None:
    section = _table(doc, table, "/".join(path))
    declared = section.get("version")
    if declared != _EXPECTED_VERSION:
        raise ValueError(
            f"{'/'.join(path)}: [{table}].version is {declared!r}, expected {_EXPECTED_VERSION}. "
            f"A lexicon version bump is a decision, not a side effect."
        )


def _str_list(value: object, where: str) -> tuple[str, ...]:
    """Return a non-empty list of strings, raising otherwise."""
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise TypeError(f"{where}: expected a list of strings")
    if not value:
        raise ValueError(f"{where}: an empty list would silently disable a rule")
    return tuple(str(item) for item in value)


def _phrase_map(table: object, where: str) -> dict[str, str]:
    """Invert ``key -> [surface phrases]`` into ``surface phrase -> key``.

    Raises on a phrase claimed by two keys: an ambiguous surface form would be
    resolved by dict insertion order, which is a decision made by the order
    somebody happened to type the file in.
    """
    if not isinstance(table, Mapping):
        raise TypeError(f"{where}: expected a table")
    out: dict[str, str] = {}
    for key, phrases in table.items():
        for phrase in _str_list(phrases, f"{where}.{key}"):
            folded = phrase.casefold()
            if folded in out and out[folded] != key:
                raise ValueError(
                    f"{where}: surface phrase {phrase!r} is claimed by both "
                    f"{out[folded]!r} and {key!r}"
                )
            out[folded] = key
    return out


def _longest_first(phrases: Sequence[str]) -> tuple[str, ...]:
    """Order for greedy matching: longest first, then lexicographic for determinism.

    Length-first is what makes ``'shall not'`` beat ``'shall'``.  Getting that
    ordering wrong turns every prohibition in a corpus into an obligation, which
    inverts the control — it is the single worst bug available in this module,
    so the ordering is centralised in one function with one test.
    """
    return tuple(sorted({p.casefold() for p in phrases}, key=lambda p: (-len(p), p)))


@dataclass(frozen=True, slots=True)
class Deontic:
    """The controlled deontic lexicon."""

    cue_order: tuple[str, ...]
    """Every cue phrase, longest first — the greedy-match order."""
    cue_label: Mapping[str, str]
    """Cue phrase (case-folded) → label (``MUST``, ``MUST_NOT``, …)."""
    taxonomy: Mapping[str, str]
    """Label → ``OBLIGATION``/``PROHIBITION``/``PERMISSION``/``RECOMMENDATION``/``NONE``."""
    passive_markers: tuple[str, ...]

    def labels(self) -> frozenset[str]:
        """Return every legal deontic label, including ``ABSENT``."""
        return frozenset(self.taxonomy)


@dataclass(frozen=True, slots=True)
class Hedges:
    """WHS-style hedges.  Every one of these lands in ``CAT.exceptions[]``."""

    phrases: tuple[str, ...]
    """Longest first."""
    force_low: frozenset[str]
    """Hedges that make an extraction ``'low'`` even when every slot filled."""


@dataclass(frozen=True, slots=True)
class Slots:
    """Action / object / hazard / quantifier / verification vocabularies."""

    actor_generic: tuple[str, ...]
    actor_unspecified: str
    action: Mapping[str, str]
    action_order: tuple[str, ...]
    action_negating: Mapping[str, str]
    """Surface → action key for phrases that **flip the deontic's polarity**."""
    action_negating_order: tuple[str, ...]
    action_light: frozenset[str]
    """Action keys that carry no control content and yield to a nominalisation."""
    object_class: Mapping[str, str]
    object_class_order: tuple[str, ...]
    hazard_priority: tuple[str, ...]
    hazard_cues: Mapping[str, tuple[str, ...]]
    quantifier_default: str
    quantifier_precedence: tuple[str, ...]
    quantifier: Mapping[str, str]
    quantifier_order: tuple[str, ...]
    verification: Mapping[str, str]
    verification_order: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class NamedFrequency:
    """A named frequency expressed as the INTERVAL it implies."""

    value: Decimal
    unit: str


@dataclass(frozen=True, slots=True)
class Grammar:
    """The shallow closed-class grammar."""

    condition_subordinators: tuple[str, ...]
    exception_subordinators: tuple[str, ...]
    comparator: Mapping[str, str]
    comparator_order: tuple[str, ...]
    range_joiners: tuple[str, ...]
    reference_markers: Mapping[str, str]
    reference_marker_order: tuple[str, ...]
    named_frequency: Mapping[str, NamedFrequency]
    named_frequency_order: tuple[str, ...]
    frequency_introducers: tuple[str, ...]
    event_anchored: tuple[str, ...]
    figure_cues: tuple[str, ...]
    cross_reference_openers: tuple[str, ...]
    cell_delimiter: str
    min_cells: int
    row_max_words: int
    row_min_quantities: int


@dataclass(frozen=True, slots=True)
class UnitClasses:
    """Unit token → dimension, and → declared pressure reference.

    Contains **no conversion factors** and must never contain any; see the
    header of ``data/lexicon/unit-class.toml`` for why (decision D5).
    """

    dimension: Mapping[str, str]
    reference: Mapping[str, str]
    default_reference: str
    referenced_dimensions: frozenset[str]
    token_order: tuple[str, ...]
    """Canonical tokens longest-first, matched **case-sensitively**."""
    alias: Mapping[str, str]
    """Case-folded alias → canonical token (``'metres'`` → ``'m'``, ``'months'`` → ``'month'``)."""
    alias_order: tuple[str, ...]
    """Aliases longest-first, matched **case-insensitively**."""

    def canonical(self, token: str) -> str | None:
        """Resolve any surface unit token to its canonical form, or ``None``.

        Aliases are consulted **first**.  ``'months'`` must resolve to
        ``'month'`` even though a naive canonical-first lookup would find
        nothing and fall through — and if the two ever both counted as
        canonical, one control written two ways would carry two ``cat_key``s.
        """
        resolved = self.alias.get(token.casefold())
        if resolved is not None:
            return resolved
        return token if token in self.dimension else None


@dataclass(frozen=True, slots=True)
class Parameters:
    """Surface phrase → ``safe_direction`` registry key.

    Carries no direction: which way a setpoint move is dangerous is DIRECTRIX's
    judgement (W2), stored as clauses inside the gated commit DAG so that editing
    it is itself a gated change.  A direction column here would escape that gate.
    """

    synonym: Mapping[str, str]
    synonym_order: tuple[str, ...]
    keys: frozenset[str]
    deliberately_unmapped: frozenset[str]


@dataclass(frozen=True, slots=True)
class Lexicons:
    """Everything the extractor reads, loaded once."""

    deontic: Deontic
    hedges: Hedges
    slots: Slots
    grammar: Grammar
    units: UnitClasses
    parameters: Parameters


def _load_deontic() -> Deontic:
    doc = _read(_DEONTIC)
    _require_version(doc, "deontic", _DEONTIC)
    section = _table(doc, "deontic", "deontic.toml")
    label_by_phrase = _phrase_map(section.get("cues"), "deontic.cues")
    taxonomy_raw = _table(section, "taxonomy", "deontic.toml")
    taxonomy = {str(k): str(v) for k, v in taxonomy_raw.items()}
    unknown = set(label_by_phrase.values()) - set(taxonomy)
    if unknown:
        raise ValueError(f"deontic.toml: cue labels with no taxonomy entry: {sorted(unknown)}")
    if "ABSENT" not in taxonomy:
        raise ValueError("deontic.toml: taxonomy must define ABSENT, the fifth state")
    passive = _table(section, "passive", "deontic.toml")
    return Deontic(
        cue_order=_longest_first(tuple(label_by_phrase)),
        cue_label=label_by_phrase,
        taxonomy=taxonomy,
        passive_markers=_longest_first(
            _str_list(passive.get("markers"), "deontic.passive.markers")
        ),
    )


def _load_hedges() -> Hedges:
    doc = _read(_HEDGE)
    _require_version(doc, "hedge", _HEDGE)
    section = _table(doc, "hedge", "hedge.toml")
    phrases = _str_list(section.get("phrases"), "hedge.phrases")
    confidence = _table(section, "confidence", "hedge.toml")
    force_low = _str_list(confidence.get("force_low"), "hedge.confidence.force_low")
    known = {p.casefold() for p in phrases}
    missing = {p.casefold() for p in force_low} - known
    if missing:
        raise ValueError(f"hedge.toml: force_low entries absent from phrases: {sorted(missing)}")
    return Hedges(
        phrases=_longest_first(phrases),
        force_low=frozenset(p.casefold() for p in force_low),
    )


_ACTION_SUBTABLES: Final[frozenset[str]] = frozenset({"negating", "nominal", "light"})


def _load_actions(doc: Mapping[str, Any]) -> tuple[dict[str, str], dict[str, str], frozenset[str]]:
    """Return ``(action, action_negating, action_light)`` from ``[action]``."""
    action_table = _table(doc, "action", "slots.toml")
    positive_raw = {
        key: value for key, value in action_table.items() if key not in _ACTION_SUBTABLES
    }
    # Nominalisations resolve to the same keys as the verbs, so they merge into
    # the positive map rather than forming a third vocabulary.
    action = _phrase_map(positive_raw, "action")
    nominal = _phrase_map(action_table.get("nominal", {}), "action.nominal")
    nominal_orphan = set(nominal.values()) - set(action.values())
    if nominal_orphan:
        raise ValueError(
            f"slots.toml: [action.nominal] names keys with no verb surfaces: "
            f"{sorted(nominal_orphan)}"
        )
    clash = set(action) & set(nominal)
    if clash:
        raise ValueError(f"slots.toml: surfaces are both verbal and nominal: {sorted(clash)}")
    action = {**action, **nominal}

    light_raw = _table(action_table, "light", "slots.toml")
    action_light = frozenset(_str_list(light_raw.get("keys"), "action.light.keys"))
    unknown_light = action_light - set(action.values())
    if unknown_light:
        raise ValueError(
            f"slots.toml: [action.light] names unknown action keys: {sorted(unknown_light)}"
        )

    negating = _phrase_map(action_table.get("negating", {}), "action.negating")
    orphan = set(negating.values()) - set(action.values())
    if orphan:
        raise ValueError(
            f"slots.toml: [action.negating] names keys with no positive surfaces: "
            f"{sorted(orphan)}. "
            f"A negating-only action would make the flipped and unflipped forms of one control "
            f"un-unifiable, which is the identity split the polarity rule exists to prevent."
        )
    both = set(action) & set(negating)
    if both:
        raise ValueError(f"slots.toml: surfaces are both positive and negating: {sorted(both)}")
    return action, negating, action_light


def _load_hazards(doc: Mapping[str, Any]) -> tuple[tuple[str, ...], dict[str, tuple[str, ...]]]:
    """Return ``(priority, cues)`` from ``[hazard_energy]``."""
    hazard = _table(doc, "hazard_energy", "slots.toml")
    priority = _str_list(hazard.get("priority"), "hazard_energy.priority")
    cues_raw = _table(hazard, "cues", "slots.toml")
    cues = {
        str(key): _longest_first(_str_list(value, f"hazard_energy.cues.{key}"))
        for key, value in cues_raw.items()
    }
    missing = set(priority) - set(cues)
    if missing:
        raise ValueError(
            f"slots.toml: hazard priority names classes with no cues: {sorted(missing)}"
        )
    unprioritised = set(cues) - set(priority)
    if unprioritised:
        raise ValueError(
            f"slots.toml: hazard cue classes absent from priority: {sorted(unprioritised)}. "
            f"Resolution order must be declared, never left to table order."
        )
    return priority, cues


def _load_quantifiers(doc: Mapping[str, Any]) -> tuple[str, tuple[str, ...], dict[str, str]]:
    """Return ``(default, precedence, cues)`` from ``[coverage_quantifier]``."""
    section = _table(doc, "coverage_quantifier", "slots.toml")
    cues = _phrase_map(section.get("cues"), "coverage_quantifier.cues")
    precedence = _str_list(section.get("precedence"), "coverage_quantifier.precedence")
    undeclared = set(cues.values()) - set(precedence)
    if undeclared:
        raise ValueError(
            f"slots.toml: quantifier classes absent from precedence: {sorted(undeclared)}. "
            f"Resolution order must be declared, never left to position in the clause."
        )
    return str(section.get("default", "unspecified")), precedence, cues


def _load_slots() -> Slots:
    doc = _read(_SLOTS)
    _require_version(doc, "slots", _SLOTS)
    actor = _table(doc, "actor", "slots.toml")
    action, action_negating, action_light = _load_actions(doc)
    object_class = _phrase_map(doc.get("object_class"), "object_class")
    hazard_priority, hazard_cues = _load_hazards(doc)
    quantifier_default, quantifier_precedence, quantifier = _load_quantifiers(doc)
    verification = _phrase_map(
        _table(doc, "verification", "slots.toml").get("cues"), "verification.cues"
    )
    return Slots(
        actor_generic=_longest_first(_str_list(actor.get("generic"), "actor.generic")),
        actor_unspecified=str(actor.get("unspecified", "unspecified")),
        action=action,
        action_order=_longest_first(tuple(action)),
        action_negating=action_negating,
        action_negating_order=_longest_first(tuple(action_negating)),
        action_light=action_light,
        object_class=object_class,
        object_class_order=_longest_first(tuple(object_class)),
        hazard_priority=hazard_priority,
        hazard_cues=hazard_cues,
        quantifier_default=quantifier_default,
        quantifier_precedence=quantifier_precedence,
        quantifier=quantifier,
        quantifier_order=_longest_first(tuple(quantifier)),
        verification=verification,
        verification_order=_longest_first(tuple(verification)),
    )


def _load_named_frequencies(frequency: Mapping[str, Any]) -> dict[str, NamedFrequency]:
    """Parse ``[grammar.frequency.named]`` into interval quantities."""
    named_raw = _table(frequency, "named", "grammar.toml")
    named: dict[str, NamedFrequency] = {}
    for phrase, spec in named_raw.items():
        if not isinstance(spec, Mapping) or "value" not in spec or "unit" not in spec:
            raise TypeError(f"grammar.frequency.named.{phrase}: expected {{value, unit}}")
        named[str(phrase).casefold()] = NamedFrequency(
            value=Decimal(str(spec["value"])), unit=str(spec["unit"])
        )
    return named


def _load_grammar() -> Grammar:
    doc = _read(_GRAMMAR)
    _require_version(doc, "grammar", _GRAMMAR)
    grammar = _table(doc, "grammar", "grammar.toml")
    subordinator = _table(grammar, "subordinator", "grammar.toml")
    comparator = _phrase_map(grammar.get("comparator"), "grammar.comparator")
    reference = _phrase_map(_table(grammar, "reference", "grammar.toml"), "grammar.reference")
    frequency = _table(grammar, "frequency", "grammar.toml")
    named = _load_named_frequencies(frequency)
    opacity = _table(grammar, "opacity", "grammar.toml")

    return Grammar(
        condition_subordinators=_longest_first(
            _str_list(subordinator.get("condition"), "grammar.subordinator.condition")
        ),
        exception_subordinators=_longest_first(
            _str_list(subordinator.get("exception"), "grammar.subordinator.exception")
        ),
        comparator=comparator,
        comparator_order=_longest_first(tuple(comparator)),
        range_joiners=_longest_first(
            _str_list(
                _table(grammar, "range", "grammar.toml").get("joiners"), "grammar.range.joiners"
            )
        ),
        reference_markers=reference,
        reference_marker_order=_longest_first(tuple(reference)),
        named_frequency=named,
        named_frequency_order=_longest_first(tuple(named)),
        frequency_introducers=_longest_first(
            _str_list(frequency.get("introducers"), "grammar.frequency.introducers")
        ),
        event_anchored=_longest_first(
            _str_list(frequency.get("event_anchored"), "grammar.frequency.event_anchored")
        ),
        figure_cues=_longest_first(
            _str_list(opacity.get("figure_cues"), "grammar.opacity.figure_cues")
        ),
        cross_reference_openers=_longest_first(
            _str_list(
                opacity.get("cross_reference_openers"), "grammar.opacity.cross_reference_openers"
            )
        ),
        cell_delimiter=str(opacity.get("cell_delimiter", "|")),
        min_cells=int(opacity.get("min_cells", 2)),
        row_max_words=int(opacity.get("row_max_words", 14)),
        row_min_quantities=int(opacity.get("row_min_quantities", 2)),
    )


def _load_units() -> UnitClasses:
    doc = _read(_UNITS)
    _require_version(doc, "units", _UNITS)
    units = _table(doc, "units", "unit-class.toml")
    dimension = {str(k): str(v) for k, v in _table(units, "dimension", "unit-class.toml").items()}
    reference = {str(k): str(v) for k, v in _table(units, "reference", "unit-class.toml").items()}
    unknown = set(reference) - set(dimension)
    if unknown:
        raise ValueError(
            f"unit-class.toml: reference declared for unclassified units: {sorted(unknown)}"
        )
    legal_references = {"absolute", "gauge", "delta", "none"}
    bad = set(reference.values()) - legal_references
    if bad:
        raise ValueError(f"unit-class.toml: illegal reference values {sorted(bad)}")
    default_reference = str(units.get("default_reference", "none"))
    if default_reference not in legal_references:
        raise ValueError(f"unit-class.toml: illegal default_reference {default_reference!r}")
    referenced = _table(units, "referenced_dimensions", "unit-class.toml")
    alias = {
        str(k).casefold(): str(v) for k, v in _table(units, "alias", "unit-class.toml").items()
    }
    dangling = {target for target in alias.values() if target not in dimension}
    if dangling:
        raise ValueError(
            f"unit-class.toml: aliases resolve to unclassified tokens: {sorted(dangling)}"
        )
    # An alias that is ALSO canonical is an identity split waiting to happen:
    # the same unit would reach a cat_key under two spellings.
    canonical_folded = {token.casefold() for token in dimension}
    self_referential = {a for a in alias if a in canonical_folded and alias[a].casefold() != a}
    if self_referential:
        raise ValueError(
            f"unit-class.toml: aliases shadow canonical tokens: {sorted(self_referential)}"
        )
    return UnitClasses(
        dimension=dimension,
        reference=reference,
        default_reference=default_reference,
        referenced_dimensions=frozenset(
            _str_list(referenced.get("dimensions"), "units.referenced_dimensions.dimensions")
        ),
        # Case-SENSITIVE ordering here: `m` (metre) and `M` are different units
        # and folding them would be a unit error, not a spelling one.
        token_order=tuple(sorted(dimension, key=lambda token: (-len(token), token))),
        alias=alias,
        alias_order=_longest_first(tuple(alias)),
    )


def _load_parameters() -> Parameters:
    doc = _read(_PARAMETERS)
    _require_version(doc, "parameters", _PARAMETERS)
    section = _table(doc, "parameters", "parameter.toml")
    synonyms = _phrase_map(section.get("synonyms"), "parameters.synonyms")
    unmapped_table = _table(section, "deliberately_unmapped", "parameter.toml")
    unmapped = frozenset(
        p.casefold()
        for p in _str_list(
            unmapped_table.get("phrases"), "parameters.deliberately_unmapped.phrases"
        )
    )
    overlap = unmapped & set(synonyms)
    if overlap:
        raise ValueError(
            f"parameter.toml: phrases both mapped and deliberately unmapped: {sorted(overlap)}"
        )
    return Parameters(
        synonym=synonyms,
        synonym_order=_longest_first(tuple(synonyms)),
        keys=frozenset(synonyms.values()),
        deliberately_unmapped=unmapped,
    )


@lru_cache(maxsize=1)
def load_lexicons() -> Lexicons:
    """Load and validate every CATSEAL lexicon.  Cached for the process lifetime."""
    return Lexicons(
        deontic=_load_deontic(),
        hedges=_load_hedges(),
        slots=_load_slots(),
        grammar=_load_grammar(),
        units=_load_units(),
        parameters=_load_parameters(),
    )


@lru_cache(maxsize=1)
def lexicon_fingerprint() -> bytes:
    """32 bytes over ``(name, version, sha256(bytes))`` of all six lexicon files.

    Order is the fixed :data:`_FILES` order, not directory order, so the
    fingerprint does not depend on a filesystem's sort.
    """
    hasher = hashlib.sha256()
    hasher.update(LEXICON_FINGERPRINT_DOMAIN)
    for parts in _FILES:
        path = data_file(*parts)
        raw = path.read_bytes()
        hasher.update(b"\x1f")
        hasher.update(path.name.encode("utf-8"))
        hasher.update(b"\x1f")
        hasher.update(str(_EXPECTED_VERSION).encode("ascii"))
        hasher.update(b"\x1f")
        hasher.update(hashlib.sha256(raw).digest())
    return hasher.digest()
