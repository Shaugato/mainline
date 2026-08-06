# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""All seven anchor classes, plus the precedence that keeps them apart.

The classes share surface shapes on purpose — ``ISO 45001`` and ``ISOL-4471``
and ``PIT-1204`` and ``P-101A`` all look alike to a naive regex — so the tests
here are as much about what each pattern *refuses* to claim as about what it
matches.
"""

from __future__ import annotations

import pytest

CASES: list[tuple[str, str, str, str]] = [
    # (text, class value, raw, norm)
    ("Isolate P-101A first.", "equipment_tag", "P-101A", "P-101A"),
    ("Drain TK-204 fully.", "equipment_tag", "TK-204", "TK-204"),
    ("Close PSV-1234B.", "equipment_tag", "PSV-1234B", "PSV-1234B"),
    ("Unit 21-P-101A is offline.", "equipment_tag", "21-P-101A", "21-P-101A"),
    ("Check PIT-1204 output.", "instrument_loop", "PIT-1204", "PIT-1204"),
    ("LSHH-2301 must trip.", "instrument_loop", "LSHH-2301", "LSHH-2301"),
    ("Lock LOTO-4471 open.", "isolation_point_id", "LOTO-4471", "LOTO-4471"),
    ("Fit blind ISOL-77.", "isolation_point_id", "ISOL-77", "ISOL-77"),
    ("Comply with AS 2865.", "regulatory_citation", "AS 2865", "AS 2865"),
    ("Wire to AS/NZS 3000.", "regulatory_citation", "AS/NZS 3000", "AS/NZS 3000"),
    ("Apply IEC 61511-1.", "regulatory_citation", "IEC 61511-1", "IEC 61511-1"),
    ("See WHS Reg r.62.", "regulatory_citation", "WHS Reg r.62", "WHS REG 62"),
    ("See WHS Regulation 62.", "regulatory_citation", "WHS Regulation 62", "WHS REG 62"),
    ("Benzene 71-43-2 is present.", "cas", "71-43-2", "71-43-2"),
    ("Cadmium 7440-43-9 dust.", "cas", "7440-43-9", "7440-43-9"),
    ("The Authorised Gas Tester signs.", "named_role", "Authorised Gas Tester", "AUTHORISED GAS TESTER"),
    ("An authorized gas tester signs.", "named_role", "authorized gas tester", "AUTHORISED GAS TESTER"),
    ("The hole watch stays.", "named_role", "hole watch", "CONFINED SPACE ATTENDANT"),
    ("Hold below 10 % LEL.", "setpoint", "10 % LEL", "10%LEL"),
    ("Trip at >= 350 kPa.", "setpoint", ">= 350 kPa", ">=350kPa"),
    ("Test every 12 months.", "setpoint", "12 months", "12months"),
    ("Rated 50 psig max.", "setpoint", "50 psig", "50psig"),
]


@pytest.mark.parametrize(("text", "cls", "raw", "norm"), CASES, ids=[c[2] for c in CASES])
def test_class_extraction(text: str, cls: str, raw: str, norm: str) -> None:
    from mainline_domain.anchors import extract_anchors

    anchors = [a for a in extract_anchors(text).items if a.cls.value == cls]
    assert len(anchors) == 1, f"expected exactly one {cls} anchor in {text!r}"
    anchor = anchors[0]
    assert anchor.raw == raw
    assert anchor.norm == norm
    assert text[anchor.span[0] : anchor.span[1]] == raw


def test_all_seven_classes_are_reachable() -> None:
    from mainline_domain.anchors import extract_anchors
    from mainline_domain.contracts import AnchorClass

    text = (
        "The Authorised Gas Tester shall verify P-101A and PIT-1204 are below "
        "10 % LEL, benzene 71-43-2 is absent, LOTO-4471 is locked, per AS 2865."
    )
    found = {anchor.cls for anchor in extract_anchors(text).items}
    assert found == set(AnchorClass), f"unreached classes: {set(AnchorClass) - found}"


NON_ANCHORS = [
    ("A date 2019-05-1 is not a CAS number.", "cas"),
    ("An IP66 enclosure is not an isolation point.", "isolation_point_id"),
    ("Send e-mail to the supervisor.", "equipment_tag"),
    ("COVID-19 controls remain.", "equipment_tag"),
    ("Record 12 people on the permit.", "setpoint"),
    ("AS2865x is not a citation.", "regulatory_citation"),
]


@pytest.mark.parametrize(("text", "cls"), NON_ANCHORS)
def test_shapes_that_must_not_become_anchors(text: str, cls: str) -> None:
    from mainline_domain.anchors import extract_anchors

    assert [a for a in extract_anchors(text).items if a.cls.value == cls] == []


def test_cas_checksum_is_enforced() -> None:
    from mainline_domain.anchors import cas_check_digit, extract_anchors, is_valid_cas

    assert cas_check_digit("744043") == 9
    assert is_valid_cas("7440", "43", "9")
    assert not is_valid_cas("7440", "43", "8")
    assert not is_valid_cas("0740", "43", "9")  # zero-padded => a date, not a CAS

    good = extract_anchors("Cadmium 7440-43-9.")
    bad = extract_anchors("Not a CAS 7440-43-8.")
    assert {a.norm for a in good.items if a.cls.value == "cas"} == {"7440-43-9"}
    assert [a for a in bad.items if a.cls.value == "cas"] == []


def test_precedence_isolation_beats_equipment() -> None:
    """``LOTO-4471`` fits the LETTERS-DIGITS shape; the isolation class claims it."""
    from mainline_domain.anchors import extract_anchors

    classes = {a.raw: a.cls.value for a in extract_anchors("Lock LOTO-4471 now.").items}
    assert classes == {"LOTO-4471": "isolation_point_id"}


def test_precedence_instrument_beats_equipment() -> None:
    from mainline_domain.anchors import extract_anchors

    classes = {a.raw: a.cls.value for a in extract_anchors("Check PIT-1204 now.").items}
    assert classes == {"PIT-1204": "instrument_loop"}


def test_precedence_citation_beats_equipment() -> None:
    from mainline_domain.anchors import extract_anchors

    classes = {a.raw: a.cls.value for a in extract_anchors("Apply AS2865 fully.").items}
    assert classes == {"AS2865": "regulatory_citation"}


def test_a_tag_is_not_re_read_as_a_setpoint() -> None:
    """Without span suppression, ``P-101A`` reads as ``101 A`` (101 amperes)."""
    from mainline_domain.anchors import extract_anchors

    assert [a for a in extract_anchors("Isolate P-101A.").items if a.cls.value == "setpoint"] == []


def test_unknown_prefix_fails_closed_to_equipment_tag() -> None:
    """More anchors means more identity constraints -- never fewer."""
    from mainline_domain.anchors import extract_anchors

    anchors = list(extract_anchors("Isolate QQQ-9182 before entry.").items)
    assert [(a.cls.value, a.norm) for a in anchors] == [("equipment_tag", "QQQ-9182")]


def test_a_bare_code_without_a_separator_needs_a_known_prefix() -> None:
    from mainline_domain.anchors import extract_anchors

    assert {a.norm for a in extract_anchors("Isolate P101A now.").items} == {"P-101A"}
    assert [a for a in extract_anchors("Read ZZZZ9182 now.").items] == []


def test_citation_norm_ignores_the_edition_year() -> None:
    """Documented decision: the edition is the lattice's business, not the matcher's."""
    from mainline_domain.anchors import extract_anchors

    with_year = extract_anchors("Comply with AS 2865:2009.")
    without_year = extract_anchors("Comply with AS 2865.")
    assert with_year.identity_norms() == without_year.identity_norms()
    assert with_year.compatible_with(without_year)


def test_spans_are_offsets_into_the_text_given() -> None:
    from mainline_domain.anchors import extract_anchors

    text = "Isolate P-101A and lock LOTO-4471 per AS 2865 below 10 % LEL."
    for anchor in extract_anchors(text).items:
        assert text[anchor.span[0] : anchor.span[1]] == anchor.raw


def test_extraction_is_deterministic() -> None:
    from mainline_domain.anchors import extract_anchors

    text = "Isolate P-101A and lock LOTO-4471 per AS 2865 below 10 % LEL."
    first = extract_anchors(text)
    second = extract_anchors(text)
    assert first == second
    assert first.items == second.items
