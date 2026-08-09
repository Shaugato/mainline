# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The mandatory header block — tier 0, no cluster.

`docs/leads/datamodel.md` §5 tier 0: runner semantics with no database. Everything here
is a statement about text, and the last three cases are statements about the *repository*
— that every migration on disk actually satisfies the rule, which is the only thing that
makes the rule more than a well-written function.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from trappoint_migrate.header import (
    HEADER_KEYS,
    catalogue_ids,
    find_catalogue,
    header_findings,
    parse_header,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
MAINLINE_TREE = REPO_ROOT / "verticals" / "mainline" / "db" / "migrations"

GOOD = """\
-- SPDX-FileCopyrightText: 2026 MAINLINE contributors
-- SPDX-License-Identifier: FSL-1.1-ALv2
--
-- MI: MI01, MI17
-- I: I01
-- COUNSEL-GATED: no
-- RATIONALE: The schema is the unit that grants and policies are scoped to, so it
--            exists before anything it will contain.
--
CREATE SCHEMA mainline;
"""


def rules(findings: list[object]) -> set[str]:
    return {getattr(f, "rule") for f in findings}  # noqa: B009 - Finding is frozen+slots


def test_a_complete_header_produces_no_findings() -> None:
    assert header_findings(Path("0001_x.sql"), GOOD) == []


def test_every_missing_key_is_named_individually() -> None:
    findings = header_findings(Path("0001_x.sql"), "CREATE SCHEMA mainline;\n")
    assert rules(findings) == {"header-missing-key"}
    # One finding per key, so a file with no header at all tells the author all four
    # things to write rather than one thing four times.
    assert len(findings) == len(HEADER_KEYS)


def test_an_empty_mi_line_is_refused_even_though_the_key_is_present() -> None:
    """A presence check alone would pass a placeholder. This is what makes it not one."""
    text = GOOD.replace("-- MI: MI01, MI17", "-- MI:")
    assert "header-no-invariant" in rules(header_findings(Path("0001_x.sql"), text))


def test_an_mi_id_outside_the_catalogue_is_refused() -> None:
    text = GOOD.replace("-- MI: MI01, MI17", "-- MI: MI31")
    findings = header_findings(Path("0001_x.sql"), text, known_mi_ids=frozenset({"MI01", "MI17"}))
    assert "header-unknown-invariant" in rules(findings)
    assert "MI31" in findings[0].detail


def test_membership_is_silent_when_the_tree_declares_no_catalogue() -> None:
    """Rule-B discipline: no registry means no membership check, never an invented one."""
    text = GOOD.replace("-- MI: MI01, MI17", "-- MI: MI31")
    assert header_findings(Path("0001_x.sql"), text, known_mi_ids=None) == []


def test_a_repeated_citation_key_is_refused_because_its_consumer_reads_one() -> None:
    text = GOOD.replace("-- I: I01", "-- I: I01\n-- MI: MI02")
    assert "header-duplicate-key" in rules(header_findings(Path("0001_x.sql"), text))


def test_a_repeated_counsel_gated_key_that_agrees_is_allowed() -> None:
    """DM-17 mandates the long form; several files also carry the short summary line.

    Two lines that give the same answer are redundancy, not ambiguity. Refusing them
    would be refusing the shape the ruling asked for.
    """
    text = GOOD.replace(
        "-- COUNSEL-GATED: no",
        "-- COUNSEL-GATED: yes\n"
        "-- COUNSEL-GATED: yes (G0) · DEFAULT: conservative · ADR: docs/adr/0001-g0-counsel.md",
    )
    assert header_findings(Path("0066_disposition.sql"), text) == []
    assert parse_header(text).counsel_gated is True


def test_a_repeated_counsel_gated_key_that_disagrees_is_refused() -> None:
    text = GOOD.replace("-- COUNSEL-GATED: no", "-- COUNSEL-GATED: no\n-- COUNSEL-GATED: yes")
    findings = header_findings(Path("0066_disposition.sql"), text)
    assert "header-conflicting-key" in rules(findings)
    # And the ambiguity propagates: `counsel_gated` is None rather than one of the two
    # answers, so the manifest records `null` instead of picking a side.
    assert parse_header(text).counsel_gated is None


@pytest.mark.parametrize("value", ["maybe", "TBD", "see ADR"])
def test_a_counsel_gated_value_outside_yes_no_is_refused(value: str) -> None:
    text = GOOD.replace("-- COUNSEL-GATED: no", f"-- COUNSEL-GATED: {value}")
    assert "header-counsel-gated-value" in rules(header_findings(Path("0001_x.sql"), text))


def test_an_empty_rationale_is_refused() -> None:
    text = GOOD.replace(
        "-- RATIONALE: The schema is the unit that grants and policies are scoped to, so it\n"
        "--            exists before anything it will contain.",
        "-- RATIONALE:",
    )
    assert "header-empty-rationale" in rules(header_findings(Path("0001_x.sql"), text))


def test_the_rationale_joins_its_continuation_lines() -> None:
    rationale = parse_header(GOOD).rationale
    assert rationale.startswith("The schema is the unit")
    assert rationale.endswith("exists before anything it will contain.")
    assert "\n" not in rationale


def test_a_key_after_the_first_statement_is_not_a_header() -> None:
    """The window is the LEADING comment block, not 'the first N characters'.

    A rule whose window can be widened by adding SQL is a rule that erodes.
    """
    text = (
        "CREATE SCHEMA mainline;\n-- MI: MI01\n-- I: I01\n-- COUNSEL-GATED: no\n-- RATIONALE: x\n"
    )
    assert rules(header_findings(Path("0001_x.sql"), text)) == {"header-missing-key"}


def test_the_i_key_does_not_match_the_mi_line() -> None:
    """`-- MI:` must not satisfy `-- I:`; the two citations are different registries."""
    text = "-- MI: MI01\n-- COUNSEL-GATED: no\n-- RATIONALE: because\nCREATE SCHEMA mainline;\n"
    findings = header_findings(Path("0001_x.sql"), text)
    assert [f.detail for f in findings if f.rule == "header-missing-key"], findings
    assert "'-- I:'" in findings[0].detail


def test_the_i17_citation_is_only_refused_when_strictness_is_asked_for() -> None:
    text = GOOD.replace("-- I: I01", "-- I: I17")
    assert header_findings(Path("0049y_x.sql"), text) == []
    strict = header_findings(Path("0049y_x.sql"), text, strict_trappoint_ids=True)
    assert "header-unknown-trappoint-invariant" in rules(strict)


# ── The repository itself ─────────────────────────────────────────────────────────────
# A rule nobody's tree satisfies is a rule that will be turned off. These three assert
# the tree, so the rule and the repository fail together or not at all.


@pytest.mark.skipif(not MAINLINE_TREE.is_dir(), reason="the MAINLINE migration tree is absent")
def test_the_mainline_catalogue_is_discoverable_and_holds_thirty_invariants() -> None:
    catalogue = find_catalogue(MAINLINE_TREE)
    assert catalogue is not None, "verticals/mainline/db/invariants/mi_catalogue.yaml"
    ids = catalogue_ids(catalogue)
    assert ids == frozenset(f"MI{n:02d}" for n in range(1, 31))


@pytest.mark.skipif(not MAINLINE_TREE.is_dir(), reason="the MAINLINE migration tree is absent")
def test_a_proposed_invariant_is_not_an_adopted_one() -> None:
    """The catalogue's `proposed:` block carries `id:` lines and none of them is a registry entry.

    Migration 0041 proposes MI31 in a `-- proposes:` line. If `catalogue_ids` counted it,
    this linter would certify exactly the citation `scripts/mi_ratchet.py` refuses:
    §16 is amended by an ADR, not by a header comment.
    """
    catalogue = find_catalogue(MAINLINE_TREE)
    assert catalogue is not None
    raw = catalogue.read_text(encoding="utf-8")
    assert "MI31" in raw, "this test is meaningless if the proposal was withdrawn"
    assert "MI31" not in catalogue_ids(catalogue)


@pytest.mark.skipif(not MAINLINE_TREE.is_dir(), reason="the MAINLINE migration tree is absent")
def test_every_committed_migration_satisfies_the_header_rule() -> None:
    known = catalogue_ids(find_catalogue(MAINLINE_TREE) or MAINLINE_TREE)
    offences: list[str] = []
    for path in sorted(MAINLINE_TREE.glob("*.sql")):
        for finding in header_findings(path, path.read_text(encoding="utf-8"), known_mi_ids=known):
            offences.append(finding.render())
    assert offences == []


@pytest.mark.skipif(not MAINLINE_TREE.is_dir(), reason="the MAINLINE migration tree is absent")
def test_the_counsel_gated_set_is_non_empty_and_every_file_answers_the_question() -> None:
    """DM-17's set must be addressable by query, and nobody may leave the key blank."""
    gated: list[str] = []
    silent: list[str] = []
    for path in sorted(MAINLINE_TREE.glob("*.sql")):
        answer = parse_header(path.read_text(encoding="utf-8")).counsel_gated
        if answer is None:
            silent.append(path.name)
        elif answer:
            gated.append(path.name)
    assert silent == [], "every migration must answer COUNSEL-GATED, one way or the other"
    assert gated, "the counsel-gated set is empty; DM-17 names five anchors at minimum"
