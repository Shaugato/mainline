# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The fixtures still say what the TOML claims they say.

The declared ``parameter`` and ``directrix_ratified`` on each fixture are
EXPECTATIONS, not inputs.  If a fixture's text drifted and its parameter stopped
resolving, every setpoint mutant against it would move into the *inapplicable*
bucket — and inapplicable mutants are not in the denominator, so the published
kill rate would RISE because its hardest trials quietly left.  Nothing would look
wrong anywhere.

That is the single most dangerous silent failure this harness has, and it is the
reason these assertions exist.
"""

from __future__ import annotations

import pytest
from mainline_mutation import load_fixtures
from mainline_mutation.directrix import ratified_overlap, registry, safe_direction
from mainline_mutation.paraphrase import paraphrase_for
from mainline_mutation.pipeline import view_of

FIXTURES = load_fixtures()


@pytest.mark.parametrize("revision", FIXTURES, ids=lambda r: r.fixture_id)
def test_the_declared_parameter_is_what_the_extractor_produces(revision):
    view = view_of(revision.document())
    extracted = "" if view.cat is None else view.cat.parameter
    assert extracted == revision.parameter, (
        f"{revision.fixture_id} declares parameter {revision.parameter!r} and the CAT "
        f"extractor produced {extracted!r}. Every setpoint mutant against this fixture is "
        "now silently inapplicable, which raises the published kill rate by removing its "
        "hardest trials"
    )


@pytest.mark.parametrize("revision", FIXTURES, ids=lambda r: r.fixture_id)
def test_the_declared_ratification_matches_directrix(revision):
    answers = revision.parameter in registry().parameters()
    assert answers == revision.directrix_ratified, (
        f"{revision.fixture_id} declares directrix_ratified={revision.directrix_ratified} and "
        f"the registry {'answers' if answers else 'abstains'} on {revision.parameter!r}"
    )


@pytest.mark.parametrize("revision", FIXTURES, ids=lambda r: r.fixture_id)
def test_the_declared_setpoint_token_is_in_the_text(revision):
    if not revision.setpoint_token:
        return
    assert revision.setpoint_token in revision.raw_text


@pytest.mark.parametrize("revision", FIXTURES, ids=lambda r: r.fixture_id)
def test_the_furniture_is_stripped_by_the_canonicaliser(revision):
    """The page furniture must not survive into ``canon_text``.

    Half the SURVIVE catalogue changes nothing but the furniture, so a furniture
    line the canonicaliser does not recognise would make those classes measure a
    text change while reporting the canonicaliser's name.
    """
    view = view_of(revision.document())
    for line in revision.furniture_lines:
        assert line not in view.canon_text, (
            f"{revision.fixture_id}'s furniture line {line!r} survived canonicalisation"
        )


@pytest.mark.parametrize("revision", FIXTURES, ids=lambda r: r.fixture_id)
def test_the_numbering_prefix_is_excised(revision):
    if not revision.numbering_prefix:
        return
    view = view_of(revision.document())
    assert not view.canon_text.startswith(revision.numbering_prefix), (
        "CANONHOLD excises the numbering prefix into its own field; a prefix left in "
        "canon_text would make `renumber` a real text change"
    )


@pytest.mark.parametrize("revision", FIXTURES, ids=lambda r: r.fixture_id)
def test_every_fixture_has_a_committed_paraphrase(revision):
    entry = paraphrase_for(revision)
    assert entry.paraphrase.strip()
    assert entry.provenance == "hand-authored", (
        "the cassettes are hand-authored and every artefact says so. A cassette claiming "
        "another provenance would need a model_id and a recorded_at that mean something"
    )
    assert entry.model_id is None, "PL-3: no model was called to produce these"


def test_directrix_coverage_is_reported_not_assumed():
    """The measured coverage gap between two committed tables.

    Only a handful of the parameter keys the CAT extractor can produce are
    ratified in the DIRECTRIX seed.  Under decision D6 every other one ABSTAINS
    and fails closed to ``weaken`` — R-A4 working as designed, and also the
    reason the setpoint classes decline unratified fixtures.  The number is
    recomputed here so that a comment cannot rot into a false statement.
    """
    overlap = ratified_overlap()
    assert overlap, "no extractable parameter is ratified; every setpoint clause would abstain"
    for key in overlap:
        assert safe_direction(key).value != "ABSTAIN"


def test_at_least_one_fixture_per_family_is_ratified():
    ratified = {r.family for r in FIXTURES if r.directrix_ratified}
    assert len(ratified) >= 2, (
        "the setpoint classes would be confined to one document family, and the per-family "
        "breakdown of the loudest mutation in the catalogue would be a single column"
    )
