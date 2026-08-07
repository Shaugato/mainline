# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""Layer 4: the anchor gazetteer, and what it does and does not claim.

It claims one thing: a cue naming a **checkable particular** — an equipment tag, a setpoint,
a regulatory citation, a CAS number — that its source does not contain is refused.  It does
not claim to detect a wrong cue, and the tests are written so that nobody reading them comes
away thinking it does.

Two properties get most of the attention here, because both are ways the control could be
worse than useless:

* **False rejections are the expensive failure.**  A control that refuses good cues gets
  switched off.  Hence the SI-normalisation tests: ``3.5 bar`` and ``350 kPa`` are one fact.
* **Under-recognition is safe by construction.**  A surface form the gazetteer does not know
  produces no anchor, so it cannot trip the check.  That is a real limit, and it is tested
  as a limit rather than hidden.
"""

from __future__ import annotations

import pytest

from mainline_recall_agent.cue.anchors import (
    anchor_keys,
    extract_anchors,
    span_sha256,
    verify_anchors,
)


def kinds(text: str) -> list[tuple[str, str]]:
    return [(a.kind, a.normalised) for a in extract_anchors(text)]


def test_equipment_tags_are_extracted_and_normalised() -> None:
    assert ("equipment_tag", "K-401") in kinds("the bypass on K-401 was left in place")
    assert ("equipment_tag", "PT-101A") in kinds("transmitter PT-101A reads high")
    assert ("equipment_tag", "K-401") in kinds("tag written as K - 401 with spaces")


def test_lowercase_prose_is_not_an_equipment_tag() -> None:
    """Case-sensitive on purpose: a case-insensitive pass turns ordinary text into tags."""
    assert kinds("the type-3 barrier and a re-2 review") == []


def test_setpoints_normalise_to_si_so_the_same_fact_is_the_same_anchor() -> None:
    assert kinds("held at 3.5 bar")[0] == ("setpoint", "350 kPa")
    assert kinds("held at 350 kPa")[0] == ("setpoint", "350 kPa")
    assert kinds("3 m of ground") == kinds("3 metres of ground") == [("setpoint", "3 m")]
    assert kinds("20 degC ambient")[0] == ("setpoint", "293.15 K")


def test_percent_lel_is_not_eaten_by_percent() -> None:
    assert kinds("atmosphere at 10 %LEL") == [("setpoint", "10 %LEL")]
    assert kinds("oxygen at 19.5 %") == [("setpoint", "19.5 %")]


def test_citations_are_extracted_and_normalised() -> None:
    found = kinds("30 CFR 56.14105 and AS 2865-2009 and ISO 45001:2018 apply")
    assert {kind for kind, _ in found} == {"citation"}
    values = {normalised for _, normalised in found}
    assert values == {"30 CFR 56.14105", "AS 2865-2009", "ISO 45001:2018"}


def test_section_symbols_and_whs_regulations_are_citations() -> None:
    values = {n for _, n in kinds("see § 75.1725 and WHS Regulation 2011 r 302")}
    assert "§75.1725" in values
    assert "WHS REG 2011 R 302" in values


def test_cas_numbers_are_validated_by_check_digit() -> None:
    """Without the check digit this pattern matches phone numbers and part numbers."""
    assert kinds("hydrogen sulfide, CAS 7783-06-4") == [("cas", "7783-06-4")]
    assert kinds("sodium cyanide 143-33-9 in the circuit") == [("cas", "143-33-9")]
    assert kinds("part number 1234-56-7 was replaced") == []


def test_a_cue_naming_a_tag_absent_from_its_source_is_rejected() -> None:
    """The done_when case, at the level of the pure function."""
    source = "The belt rolled back through the drive when the brake was released."
    verdict = verify_anchors(
        "Release of stored gravitational energy through drive K-401.",
        anchor_keys(extract_anchors(source)),
    )
    assert verdict.ok is False
    assert verdict.missing_keys == (("equipment_tag", "K-401"),)


def test_a_cue_naming_a_tag_present_in_its_source_is_accepted() -> None:
    source = "Drive K-401 rolled back when the brake was released."
    verdict = verify_anchors("Stored energy released through drive K-401.", anchor_keys(
        extract_anchors(source)
    ))
    assert verdict.ok is True
    assert verdict.missing == ()


def test_the_check_is_one_directional() -> None:
    """A cue is a summary and drops particulars; that is not a fault."""
    source = "Tag K-401 at 350 kPa under 30 CFR 56.14105."
    verdict = verify_anchors(
        "Stored pneumatic energy released from a pressurised assembly.",
        anchor_keys(extract_anchors(source)),
    )
    assert verdict.ok is True


def test_a_paraphrased_unit_does_not_cause_a_false_rejection() -> None:
    source = "The assembly had been inflated to 3.5 bar before the rim separated."
    verdict = verify_anchors(
        "A person stands in the trajectory of an assembly pressurised to 350 kPa.",
        anchor_keys(extract_anchors(source)),
    )
    assert verdict.ok is True, "SI normalisation must make these one fact"


def test_an_unrecognised_surface_form_cannot_trip_the_check() -> None:
    """A stated limit, tested as a limit.

    ``TAG/401/A`` is not a form the gazetteer knows, so it yields no anchor and the cue is
    tolerated.  Under-recognition weakens the control; it can never produce a false alarm.
    """
    assert kinds("valve TAG/401/A stuck open") == []
    verdict = verify_anchors("A cue naming valve TAG/401/A.", frozenset())
    assert verdict.ok is True


def test_extraction_is_deterministic_and_positional() -> None:
    text = "Tag K-401 at 350 kPa; tag K-402 downstream."
    once = extract_anchors(text)
    assert once == extract_anchors(text)
    assert [a.start for a in once] == sorted(a.start for a in once)
    for anchor in once:
        assert text[anchor.start : anchor.end] == anchor.raw


@pytest.mark.parametrize("value", ["", "K-401", "a longer offending cue span"])
def test_span_hashes_are_stable_lowercase_sha256(value: str) -> None:
    digest = span_sha256(value)
    assert len(digest) == 64
    assert digest == digest.lower()
    assert digest == span_sha256(value)
