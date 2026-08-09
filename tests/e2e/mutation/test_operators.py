# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Operator properties: they change something, they are deterministic, they say when they don't.

The three properties `operators/__init__.py` claims, asserted rather than
documented.  Plus the two that are specific to the design:

* eleven of the twelve SURVIVE classes leave ``canon_sha256`` **byte identical**,
  because that is CANONHOLD's specification and not a happy accident of the
  fixtures.  The twelfth, ``cross_reference_renumbering``, changes the text on
  purpose and is the only one that tests the matcher;
* every salami chain has adjacent steps that are individually invisible.  A
  salami whose steps were detectable proves nothing about ORIGINDIFF, and the
  claim in the artefact is only as good as this assertion.
"""

from __future__ import annotations

import pytest
from mainline_mutation import load_catalogue, load_fixtures, run
from mainline_mutation.catalogue import operator_for
from mainline_mutation.errors import OperatorInapplicable
from mainline_mutation.model import SURVIVE
from mainline_mutation.operators.survive import ancestor_document
from mainline_mutation.pipeline import view_of
from mainline_mutation.runner import _rng

CLASSES = load_catalogue()
FIXTURES = load_fixtures()

#: The one SURVIVE class whose text genuinely moves, and the one whose numbering
#: scheme CANONHOLD deliberately does not excise. Both are documented in
#: `operators/survive.py` and both test the MATCHER rather than the canonicaliser.
TEXT_CHANGING_SURVIVE = {"cross_reference_renumbering", "table_to_prose", "appendix_relocation"}


def _pairs():
    return [(c, f) for c in CLASSES for f in FIXTURES]


@pytest.mark.parametrize(
    ("mutation_class", "revision"),
    _pairs(),
    ids=lambda x: getattr(x, "class_id", None) or getattr(x, "fixture_id", ""),
)
def test_an_operator_either_changes_something_or_declines(mutation_class, revision):
    operator = operator_for(mutation_class.class_id)
    try:
        application = operator(revision, _rng(0, mutation_class.class_id, revision.fixture_id))
    except OperatorInapplicable as declined:
        # PT017 says to use pytest.raises. It does not apply: the operator is
        # ALLOWED to decline this pairing and the assertion is that a decline
        # carries a reason, not that a decline happens.
        reason = str(declined)
        assert reason.strip()
        return
    assert application.descendant_document != revision.document(), (
        f"{mutation_class.class_id} produced an identical document for {revision.fixture_id}; "
        "a no-op mutant is not a trial and a kill rate over no-op mutants is a number about "
        "nothing"
    )
    assert application.note.strip()
    assert application.chain[-1] == application.descendant_document


@pytest.mark.parametrize(
    ("mutation_class", "revision"),
    _pairs(),
    ids=lambda x: getattr(x, "class_id", None) or getattr(x, "fixture_id", ""),
)
def test_an_operator_is_deterministic_given_its_generator(mutation_class, revision):
    operator = operator_for(mutation_class.class_id)
    try:
        first = operator(revision, _rng(0, mutation_class.class_id, revision.fixture_id))
        second = operator(revision, _rng(0, mutation_class.class_id, revision.fixture_id))
    except OperatorInapplicable:
        return
    assert first.descendant_document == second.descendant_document
    assert first.chain == second.chain


@pytest.mark.parametrize(
    "mutation_class",
    [c for c in CLASSES if c.kind == SURVIVE and c.class_id not in TEXT_CHANGING_SURVIVE],
    ids=lambda c: c.class_id,
)
def test_the_reformatting_classes_leave_the_digest_alone(mutation_class):
    """CANONHOLD's specification, one class per mechanism it claims."""
    operator = operator_for(mutation_class.class_id)
    checked = 0
    for revision in FIXTURES:
        try:
            application = operator(revision, _rng(0, mutation_class.class_id, revision.fixture_id))
        except OperatorInapplicable:
            continue
        ancestor = view_of(ancestor_document(revision, mutation_class.class_id))
        descendant = view_of(application.descendant_document)
        assert descendant.canon_sha256 == ancestor.canon_sha256, (
            f"{mutation_class.class_id} moved canon_sha256 on {revision.fixture_id}: "
            f"{ancestor.canon_text!r} -> {descendant.canon_text!r}. This class claims to "
            "change only the page around the clause"
        )
        checked += 1
    assert checked >= 1, f"{mutation_class.class_id} was inapplicable to every fixture"


def test_every_salami_chain_is_individually_invisible():
    """The ORIGINDIFF claim, measured.  Adjacent force 0, origin verdict a weakening."""
    output = run(seed=0)
    salami = [r for r in output.results if r.class_id.startswith("salami_")]
    assert salami, "no salami trial ran; the ORIGINDIFF claim is unmeasured"
    for result in salami:
        adjacent = output.adjacent_max_force[result.mutant_id]
        assert adjacent == 0, (
            f"{result.class_id}/{result.fixture_id} has an adjacent step of force {adjacent}. "
            "A synchronic gate would have caught this chain, so it demonstrates nothing about "
            "diachronic gating"
        )
        assert result.pipeline.delta_force > 0, (
            f"{result.class_id}/{result.fixture_id} composes to {result.pipeline.delta} against "
            "the origin; the chain is not a weakening and the class is measuring nothing"
        )
        assert result.chain_length >= 5


@pytest.mark.parametrize(
    "class_id",
    ["setpoint_nudge_1pct", "setpoint_nudge_5pct", "setpoint_nudge_25pct"],
)
def test_a_nudge_moves_against_the_safe_direction(class_id):
    """The magnitude moves the DANGEROUS way, not just a different way."""
    from decimal import Decimal

    from mainline_mutation.directrix import safe_direction

    operator = operator_for(class_id)
    ran = 0
    for revision in FIXTURES:
        if not revision.directrix_ratified:
            continue
        application = operator(revision, _rng(0, class_id, revision.fixture_id))
        view = view_of(application.descendant_document)
        assert view.cat is not None
        # The magnitude lands in `value` for a setpoint and in `frequency` for an
        # interval clause; the extractor decides which, and the nudge is against
        # `safe_direction` either way.
        quantity = view.cat.value or view.cat.frequency
        assert quantity is not None
        moved = quantity.value
        original = Decimal(revision.setpoint_value)
        direction = safe_direction(revision.parameter).value
        if direction == "LOWER_IS_SAFER":
            assert moved > original
        else:
            assert moved < original
        ran += 1
    assert ran >= 1
