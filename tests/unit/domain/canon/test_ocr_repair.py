# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""OCR confusable repair fires inside numeric literals and nowhere else.

The failure this test exists to prevent is not "a missed repair".  It is a
canonicaliser that rewrites ``Oil`` to ``0i1``, ``SO2`` to ``502`` or ``TK-2O4``
to something that is no longer an anchor — that is a canonicaliser editing a
safety procedure without anyone signing for it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

FIXTURE = (
    Path(__file__).resolve().parents[4]
    / "tests"
    / "fixtures"
    / "domain"
    / "canon"
    / "reflow-triple.json"
)

REPAIRED = [
    ("1O", "10"),
    ("286S", "2865"),
    ("1O0", "100"),
    ("35O", "350"),
    ("1OO0", "1000"),
    ("2.5O", "2.50"),
    ("1O-15", "10-15"),
    ("+1O", "+10"),
]

UNTOUCHED = [
    "Oil",
    "Ill",
    "IO",
    "OO",
    "loss",
    "SOLE",
    "SO2",  # sulfur dioxide, not 502
    "S02",  # genuinely ambiguous: leave it
    "IS0",
    "lO",  # leading-character damage is out of scope, on purpose
    "TK-2O4",  # damage inside an anchor is reported as anchor drop, not guessed
    "1O0kPa",  # a number glued to its unit is not a bare numeric literal
    "isolation",
    "P-101A",
    "LOTO-4471",
]


@pytest.mark.parametrize(("damaged", "expected"), REPAIRED)
def test_numeric_literals_are_repaired(damaged: str, expected: str) -> None:
    from mainline_domain.canon.ocr import repair_numeric_confusables

    text = f"Trip at {damaged} and hold."
    repaired, repairs = repair_numeric_confusables(text)

    assert repaired == f"Trip at {expected} and hold."
    assert len(repairs) == 1
    assert repairs[0].before == damaged
    assert repairs[0].after == expected
    assert repaired[repairs[0].start : repairs[0].end] == expected


@pytest.mark.parametrize("token", UNTOUCHED)
def test_free_prose_is_never_repaired(token: str) -> None:
    from mainline_domain.canon.ocr import repair_numeric_confusables

    text = f"The {token} shall be recorded."
    repaired, repairs = repair_numeric_confusables(text)

    assert repaired == text
    assert repairs == ()


def test_repair_is_length_preserving() -> None:
    """Every offset in the system survives a repair because lengths never move."""
    from mainline_domain.canon.ocr import repair_numeric_confusables

    text = "Values 1O, 35O and 286S apply to P-101A under AS 2865."
    repaired, repairs = repair_numeric_confusables(text)

    assert len(repaired) == len(text)
    assert len(repairs) == 3
    for repair in repairs:
        assert len(repair.before) == len(repair.after) == repair.end - repair.start


def test_edge_punctuation_does_not_block_a_repair() -> None:
    from mainline_domain.canon.ocr import repair_numeric_confusables

    repaired, repairs = repair_numeric_confusables("Hold at (1O%), then 286S.")
    assert repaired == "Hold at (10%), then 2865."
    assert [r.before for r in repairs] == ["1O", "286S"]


def test_fixture_prose_list_is_actually_untouched() -> None:
    from mainline_domain.canon.ocr import repair_numeric_confusables

    document = json.loads(FIXTURE.read_text(encoding="utf-8"))
    for token in document["free_prose_must_not_be_repaired"]:
        repaired, repairs = repair_numeric_confusables(token)
        assert repaired == token
        assert repairs == ()


def test_fixture_damage_map_is_what_the_repairer_produces() -> None:
    from mainline_domain.canon.ocr import repair_numeric_confusables

    document = json.loads(FIXTURE.read_text(encoding="utf-8"))
    for damaged, expected in document["ocr_damage"].items():
        repaired, _ = repair_numeric_confusables(damaged)
        assert repaired == expected
