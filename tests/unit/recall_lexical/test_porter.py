# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The vendored Porter stemmer, against the algorithm's own published vocabulary.

The stemmer is vendored rather than depended on because a third-party stemmer that improves
its rules in a patch release changes every prose posting in ``mainline.lex_posting`` without
moving :func:`rule_fingerprint`.  Vendoring makes the behaviour a property of this
repository's bytes — which only helps if the bytes are correct, hence this file.

The vocabulary below is Porter's own worked examples plus the words the rule interactions get
wrong when a step's suffix table is over-populated.  ``rational`` is in the list because it
was: ``ational`` had been placed in the step-4 table, where it shadowed ``al``, and
``rational`` stemmed to itself while ``rationally`` stemmed to ``ration`` — two forms of one
word that would never have met in a posting list, with nothing failing anywhere.
"""

from __future__ import annotations

import pytest

from trappoint_recall.lexical.porter import stem

# fmt: off
VOCABULARY: dict[str, str] = {
    # step 1a
    "caresses": "caress", "ponies": "poni", "ties": "ti", "caress": "caress", "cats": "cat",
    # step 1b
    "feed": "feed", "agreed": "agre", "plastered": "plaster", "bled": "bled",
    "motoring": "motor", "sing": "sing",
    # step 1b continuation
    "conflated": "conflat", "troubled": "troubl", "sized": "size", "hopping": "hop",
    "tanned": "tan", "falling": "fall", "hissing": "hiss", "fizzed": "fizz",
    "failing": "fail", "filing": "file",
    # step 1c
    "happy": "happi", "sky": "sky",
    # step 2
    "relational": "relat", "conditional": "condit", "rational": "ration",
    "digitizer": "digit", "conformably": "conform", "radically": "radic",
    "differently": "differ", "vilely": "vile", "analogously": "analog",
    "vietnamization": "vietnam", "predication": "predic", "operator": "oper",
    "feudalism": "feudal", "decisiveness": "decis", "hopefulness": "hope",
    "callousness": "callous", "formality": "formal", "sensitivity": "sensit",
    "sensibility": "sensibl",
    # step 3
    "triplicate": "triplic", "formative": "form", "formalize": "formal",
    "electricity": "electr", "electrical": "electr", "hopeful": "hope", "goodness": "good",
    # step 4
    "revival": "reviv", "allowance": "allow", "inference": "infer", "airliner": "airlin",
    "gyroscopic": "gyroscop", "adjustable": "adjust", "defensible": "defens",
    "irritant": "irrit", "replacement": "replac", "adjustment": "adjust",
    "dependent": "depend", "adoption": "adopt", "communism": "commun",
    "activate": "activ", "angularity": "angular", "homologous": "homolog",
    "effective": "effect", "bowdlerize": "bowdler",
    # step 5
    "probate": "probat", "rate": "rate", "cease": "ceas",
    "controlling": "control", "rolling": "roll",
}
# fmt: on


@pytest.mark.parametrize(("word", "expected"), sorted(VOCABULARY.items()))
def test_published_vocabulary(word: str, expected: str) -> None:
    assert stem(word) == expected


def test_inflected_forms_of_one_word_converge() -> None:
    """The only property the index actually needs from a stemmer."""
    for forms in (
        ("operate", "operates", "operated", "operating", "operator", "operation"),
        ("isolate", "isolated", "isolating", "isolation"),
        ("fail", "fails", "failed", "failing"),
    ):
        stems = {stem(form) for form in forms}
        assert len(stems) == 1, f"{forms} produced {sorted(stems)}"


def test_porter_1980_does_not_conflate_every_derivation() -> None:
    """Stated because it is a real limit, not a defect to be quietly patched.

    ``failure`` stems to ``failur``, not ``fail``: the 1980 algorithm has no ``ure`` rule.
    Widening the tables to fix it would change every prose posting in the fleet, and the
    identifier channel — which is why channel D exists — is unaffected either way.
    """
    assert stem("failure") == "failur" != stem("failed")


def test_rational_and_rationally_converge() -> None:
    """The regression the step-4 table bug produced, named so it cannot come back."""
    assert stem("rational") == stem("rationally") == "ration"


def test_short_words_are_returned_unchanged() -> None:
    for word in ("a", "at", "is", "no", "on"):
        assert stem(word) == word


def test_the_stemmer_is_deterministic_and_total() -> None:
    for word in ("", "x", "aaaaa", "bbbbb", "yyyyy", "sssss"):
        assert stem(word) == stem(word)
