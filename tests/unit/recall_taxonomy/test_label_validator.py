# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""A label names a function performed — proven against things, places and asset tags.

The rule is stated in the DDL comment on ``mainline.activity_node.label`` and no CHECK can
enforce it, so this suite is where it is enforced.  The rejection table below is the
interesting part: it includes the research note's own shorthand (``"energy isolation"``,
``"tyre & rim"``) because that shorthand is exactly the shape the rule forbids, and a
validator that quietly accepted the documentation's examples would be enforcing nothing.
"""

from __future__ import annotations

import pytest
from mainline_recall_agent.taxonomy import (
    LEVEL_FILE,
    ActivityNode,
    LabelRejected,
    Level1Register,
    check_label,
    validate_label,
)
from mainline_recall_agent.taxonomy.labels import REJECTION_REASONS, normalise_label

ACCEPTED = [
    "isolating stored energy before intrusive work",
    "proving zero energy before opening a system",
    "restraining people working at height",
    "verifying atmosphere before and during entry",
    "separating people from powered mobile equipment",
    "de-energising and proving electrical circuits before contact",
    "testing for oxygen deficiency and h2s",
    "climbing fixed access with three points of contact",
]

#: (label, expected reason).  Every entry names a real way a taxonomy stops being functional.
REJECTED = [
    # things
    ("haul truck", "equipment_or_place_term"),
    ("conveyor", "equipment_or_place_term"),
    ("tyre and rim", "equipment_or_place_term"),
    ("inspecting the ball mill liners", "equipment_or_place_term"),
    # places
    ("north pit", "equipment_or_place_term"),
    ("workshop", "equipment_or_place_term"),
    ("entering the tailings dam area", "equipment_or_place_term"),
    # nominalisations: a topic, not work
    ("energy isolation", "no_function_verb"),
    ("confined space entry", "no_function_verb"),
    ("fall from height", "no_function_verb"),
    # the work is named, but the phrase is headed by the object
    ("personal lock application procedure", "no_function_verb"),
    ("scaffold erecting and handover", "equipment_or_place_term"),
    # asset tags and proper nouns
    ("isolating k-401 before entry", "asset_tag"),
    ("isolating K-401 before entry", "not_lowercase"),
    ("isolating circuit 401 before entry", "asset_tag"),
    ("isolating the pump before entry", "equipment_or_place_term"),
    ("Isolating stored energy before intrusive work", "not_lowercase"),
    ("isolating stored energy at Kalgoorlie", "not_lowercase"),
    # shape
    ("", "empty"),
    ("locking", "too_short"),
    ("isolating & proving", "illegal_character"),
    ("wobbling stored energy before intrusive work", "unknown_gerund"),
]


@pytest.mark.parametrize("label", ACCEPTED)
def test_functional_labels_are_accepted(label: str) -> None:
    verdict = check_label(label)
    assert verdict.ok, verdict.render()
    assert validate_label(label) == normalise_label(label)


@pytest.mark.parametrize(("label", "reason"), REJECTED)
def test_thing_and_place_labels_are_rejected(label: str, reason: str) -> None:
    verdict = check_label(label)
    assert not verdict.ok, f"{label!r} was accepted and should not have been"
    assert verdict.reason == reason, verdict.render()
    assert verdict.detail, "a rejection must name the offending token"


def test_every_reason_code_is_declared() -> None:
    """A reason that is not in ``REJECTION_REASONS`` cannot be aggregated on a version."""
    for label, _ in REJECTED:
        verdict = check_label(label)
        assert verdict.reason in REJECTION_REASONS


def test_validate_label_raises_with_the_reason_in_context() -> None:
    with pytest.raises(LabelRejected) as excinfo:
        validate_label("haul truck", where="series label")
    assert excinfo.value.context["reason"] == "equipment_or_place_term"
    assert "haul truck" in str(excinfo.value)


def test_a_node_cannot_be_constructed_with_a_thing_label() -> None:
    """The refusal is at construction, so a node read back from the row store is checked."""
    with pytest.raises(LabelRejected):
        ActivityNode(
            scope_id="00000000-0000-4000-8000-000000000001",
            site_id="00000000-0000-4000-8000-0000000000ff",
            level=LEVEL_FILE,
            parent_scope="00000000-0000-4000-8000-000000000002",
            label="haul truck",
            activity_root="MUE-03",
            taxonomy_ver=1,
            induced_by="llm_induced",
            frozen=False,
        )


def test_the_shipped_register_labels_all_pass(register: Level1Register) -> None:
    for code in register.codes:
        assert check_label(code.label).ok, code.label


def test_whitespace_is_collapsed_but_case_is_not_folded() -> None:
    assert normalise_label("  isolating   stored  energy before work ") == (
        "isolating stored energy before work"
    )
    # Folding case here would silently accept a place name, which is the whole point.
    assert not check_label("North Pit isolating work").ok
