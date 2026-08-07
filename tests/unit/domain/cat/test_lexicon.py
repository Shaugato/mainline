# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The committed lexicons: their invariants, and their seams to other workers.

A lexicon that can drift between runs makes every downstream finding
unfalsifiable — whether a phrase counted as a hedge would depend on which
checkout ran the extractor.  These tests pin the properties the loader promises
and, more importantly, the two cross-worker seams: W1's setpoint gazetteer must
stay classifiable here, and W2's ``safe_direction`` key space must stay the same
key space this file resolves names into.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Final

import pytest
from mainline_domain.cat.lexicon import lexicon_fingerprint, load_lexicons
from mainline_domain.cat.schema import COMPARATORS, COVERAGE_QUANTIFIERS, DEONTIC_LABELS
from mainline_domain.data import data_file

LEX = load_lexicons()

_GAZETTEER_SETPOINTS: Final[Path] = data_file("gazetteer", "setpoint-units.toml")


def test_every_lexicon_declares_the_version_the_loader_expects() -> None:
    for name, table in (
        ("deontic.toml", "deontic"),
        ("hedge.toml", "hedge"),
        ("slots.toml", "slots"),
        ("grammar.toml", "grammar"),
        ("unit-class.toml", "units"),
        ("parameter.toml", "parameters"),
    ):
        with data_file("lexicon", name).open("rb") as handle:
            doc = tomllib.load(handle)
        assert doc[table]["version"] == 1, f"{name} must declare a version the loader reads"


def test_fingerprint_is_32_bytes_and_stable_within_a_process() -> None:
    assert len(lexicon_fingerprint()) == 32
    assert lexicon_fingerprint() == lexicon_fingerprint()


# --------------------------------------------------------------------------- #
# Longest-first ordering — the ordering that keeps prohibitions prohibitions    #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "order",
    [
        LEX.deontic.cue_order,
        LEX.hedges.phrases,
        LEX.slots.action_order,
        LEX.slots.action_negating_order,
        LEX.slots.object_class_order,
        LEX.slots.verification_order,
        LEX.grammar.comparator_order,
        LEX.grammar.condition_subordinators,
        LEX.grammar.exception_subordinators,
        LEX.parameters.synonym_order,
        LEX.units.alias_order,
    ],
    ids=lambda o: f"n={len(o)}",
)
def test_vocabularies_are_ordered_longest_first(order: tuple[str, ...]) -> None:
    """``'shall not'`` must precede ``'shall'`` in every alternation.

    Python's ``|`` takes the first alternative that matches, so a list that is
    not longest-first gives shortest-match semantics — which turns every
    prohibition in the corpus into an obligation while leaving the CAT looking
    perfectly well-formed.
    """
    assert list(order) == sorted(order, key=lambda phrase: (-len(phrase), phrase))


def test_negation_beats_the_bare_modality_in_the_deontic_order() -> None:
    order = list(LEX.deontic.cue_order)
    assert order.index("shall not") < order.index("shall")
    assert order.index("must not") < order.index("must")
    assert order.index("should not") < order.index("should")
    assert order.index("may not") < order.index("may")


# --------------------------------------------------------------------------- #
# Vocabularies agree with the schema constants and with the SQL                 #
# --------------------------------------------------------------------------- #


def test_deontic_labels_match_the_schema_constant() -> None:
    assert set(LEX.deontic.cue_label.values()) | {"ABSENT"} == set(DEONTIC_LABELS)
    assert set(LEX.deontic.taxonomy) == set(DEONTIC_LABELS)


def test_comparator_tokens_are_the_spec_alphabet() -> None:
    assert set(LEX.grammar.comparator.values()) <= COMPARATORS


def test_quantifier_classes_are_the_schema_vocabulary() -> None:
    produced = set(LEX.slots.quantifier.values()) | {LEX.slots.quantifier_default}
    assert produced <= COVERAGE_QUANTIFIERS
    assert set(LEX.slots.quantifier_precedence) <= COVERAGE_QUANTIFIERS


def test_hedges_do_not_start_with_an_exception_subordinator() -> None:
    """A phrase captured twice under two spellings makes R4 fire on a rewording."""
    for phrase in LEX.hedges.phrases:
        first_word = phrase.split(" ", 1)[0]
        assert first_word not in LEX.grammar.exception_subordinators, phrase


def test_no_phrase_is_both_a_deontic_cue_and_a_hedge() -> None:
    """A hedge qualifies an obligation; it does not establish one."""
    assert not set(LEX.hedges.phrases) & set(LEX.deontic.cue_label)


# --------------------------------------------------------------------------- #
# Seam with W1 (ANCHORLOCK): every setpoint unit must be classifiable           #
# --------------------------------------------------------------------------- #


def test_every_anchorlock_setpoint_unit_resolves_to_a_dimension() -> None:
    """A unit W1 can emit as a setpoint anchor but W3 cannot classify is a hole.

    The extractor would see a setpoint, fail to build a ``Quantity`` for it, and
    return ``value=None`` — so the clause would read as carrying no setpoint at
    all, which is the quietest way to lose a control.  This test is the seam.
    """
    with _GAZETTEER_SETPOINTS.open("rb") as handle:
        gazetteer = tomllib.load(handle)
    units: list[str] = gazetteer["setpoints"]["units"]
    unresolved = [token for token in units if LEX.units.canonical(token) is None]
    assert unresolved == [], (
        f"ANCHORLOCK can emit setpoint units this lexicon cannot classify: {unresolved}. "
        f"Add them to data/lexicon/unit-class.toml — as ALIASES if they are variants "
        f"of a token already there, never as new canonical tokens."
    )


def test_unit_aliases_never_shadow_a_canonical_token() -> None:
    """One canonical token per unit, or ``12 months`` and ``12 month`` split identity."""
    canonical_folded = {token.casefold() for token in LEX.units.dimension}
    for alias, target in LEX.units.alias.items():
        if alias in canonical_folded:
            assert target.casefold() == alias, (
                f"{alias!r} is canonical and also aliased to {target!r}"
            )


def test_every_alias_resolves_to_a_classified_token() -> None:
    for alias, target in LEX.units.alias.items():
        assert target in LEX.units.dimension, f"{alias!r} -> {target!r} which has no dimension"


def test_declared_references_are_only_on_pressure_units() -> None:
    for token, reference in LEX.units.reference.items():
        assert LEX.units.dimension[token] in LEX.units.referenced_dimensions
        assert reference in ("gauge", "absolute", "delta", "none")


def test_bare_pressure_units_declare_no_reference() -> None:
    """Decision D5: unstated is ``'none'``, never ``'absolute'``."""
    for token in ("kPa", "bar", "psi", "Pa", "MPa"):
        assert token not in LEX.units.reference
    assert LEX.units.default_reference == "none"


# --------------------------------------------------------------------------- #
# Seam with W2 (DIRECTRIX): the parameter key space                            #
# --------------------------------------------------------------------------- #


def test_parameter_keys_are_snake_case_identifiers() -> None:
    """These keys are shared with DIRECTRIX's registry; a stray spelling is a miss."""
    for key in LEX.parameters.keys:
        assert key.islower()
        assert key.replace("_", "").isalnum(), key
        assert not key.startswith("_") and not key.endswith("_")


def test_parameter_lexicon_carries_no_direction() -> None:
    """Which way a setpoint move is dangerous is DIRECTRIX's judgement, not this file's.

    A direction column here would escape the gate that governs
    ``REG-SAFE-DIRECTION`` — the registry is stored as clauses in the gated
    commit DAG precisely so that editing it is itself a gated change.
    """
    with data_file("lexicon", "parameter.toml").open("rb") as handle:
        doc = tomllib.load(handle)
    assert set(doc["parameters"]) == {"version", "synonyms", "deliberately_unmapped"}
    for entry in doc["parameters"]["synonyms"].values():
        assert isinstance(entry, list)
        assert all(isinstance(phrase, str) for phrase in entry)


def test_direction_ambiguous_phrases_stay_unmapped() -> None:
    """ "operating pressure" says nothing about which way is safe, so it maps to nothing."""
    for phrase in ("pressure", "operating pressure", "temperature", "frequency"):
        assert phrase in LEX.parameters.deliberately_unmapped
        assert phrase not in LEX.parameters.synonym


def test_parameter_key_count_is_substantial() -> None:
    """Under-coverage fails closed (D6) but still costs adjudication; keep it real."""
    assert len(LEX.parameters.keys) >= 40


# --------------------------------------------------------------------------- #
# Loader strictness                                                            #
# --------------------------------------------------------------------------- #


def test_a_phrase_claimed_by_two_keys_is_a_load_error() -> None:
    """Ambiguity resolved by dict insertion order is ambiguity resolved by typing order."""
    from mainline_domain.cat.lexicon import _phrase_map

    with pytest.raises(ValueError, match="claimed by both"):
        _phrase_map({"a": ["shared"], "b": ["shared"]}, "test")


def test_an_empty_vocabulary_is_a_load_error() -> None:
    """An empty deontic lexicon does not fail: it labels the whole corpus ABSENT."""
    from mainline_domain.cat.lexicon import _str_list

    with pytest.raises(ValueError, match="empty list"):
        _str_list([], "test")
