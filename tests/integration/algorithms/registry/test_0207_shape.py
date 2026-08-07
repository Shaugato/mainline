# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Static checks on migration 0207.  No cluster, no driver, runs everywhere.

Two jobs.

The first is band discipline: one statement, a header that cites its invariants
and its sources, forward-only, and nothing outside the 0200-0219 slice this
domain reserved.  Cheap, and it is the check that would catch a second file
claiming 0207 or a migration quietly acquiring a second statement.

The second is the one that earns the file.  The view extracts every field from
the clause text with ``split_part`` on literal labels — ``'Parameter: '``,
``'Direction: '`` — and those labels are defined in
:mod:`mainline_domain.registry.encoding`.  Nothing in SQL knows that.  If the
grammar is ever changed on the Python side, the view keeps applying, keeps
returning rows, and silently reports every ``parameter_key`` as the empty string
with ``answers`` false — which reads exactly like a site that has ratified
nothing.  So the labels are cross-checked here, against the encoder, by encoding
a real entry and confirming that the literals the SQL searches for occur in it.
"""

from __future__ import annotations

import re

from _directrix_support import (
    MIGRATIONS_DIR,
    OWNED_MIGRATION,
    owned_migration_file,
    split_statements,
)
from mainline_domain.registry import (
    RATIFIABLE_DIRECTIONS,
    EntryStatus,
    SafeDirection,
    encode,
)
from mainline_domain.registry.doc import DOC_CODE
from mainline_domain.registry.encoding import PREAMBLE


def migration_text() -> str:
    return owned_migration_file().read_text(encoding="utf-8")


def code_of(statement: str) -> str:
    """A statement with its leading ``--`` comment lines removed.

    The splitter keeps comments attached to the statement that follows them, so
    a file whose header is longer than its SQL — which this one is, deliberately —
    has one statement that begins with eighty lines of prose.
    """
    lines = [line for line in statement.splitlines() if not line.lstrip().startswith("--")]
    return "\n".join(lines).strip()


def test_the_migration_is_exactly_one_statement() -> None:
    """The deployed runner applies one statement per file (§18)."""
    statements = split_statements(migration_text())
    assert len(statements) == 1, (
        f"0207 carries {len(statements)} statements; the header declares 1"
    )
    assert code_of(statements[0]).upper().startswith("CREATE VIEW")


def test_the_header_declares_what_the_band_requires() -> None:
    text = migration_text()
    for field in ("migration:", "domain:", "statements:", "invariants:", "source:"):
        assert field in text, f"0207's header has no `{field}` line"
    assert "MI22" in text and "I06" in text, "0207 does not cite its invariants"
    assert "forward-only" in text


def test_the_algorithms_band_holds_only_this_worker_s_file_at_0207() -> None:
    claims = sorted(MIGRATIONS_DIR.glob(f"{OWNED_MIGRATION:04d}_*"))
    assert len(claims) == 1, f"more than one file claims 0207: {[p.name for p in claims]}"
    assert claims[0].name == "0207_v_safe_direction_current.sql"

    # No .down.sql anywhere in this worker's slice: forward-only below the
    # protected floor.
    assert not list(MIGRATIONS_DIR.glob(f"{OWNED_MIGRATION:04d}_*.down.sql"))


def test_the_view_name_and_schema_are_the_reserved_ones() -> None:
    text = migration_text()
    assert "CREATE VIEW mainline.v_safe_direction_current" in text
    assert f"'{DOC_CODE}'" in text, "0207 does not filter on the registry doc_code"


def test_the_sql_labels_match_the_python_grammar() -> None:
    """The cross-language join that nothing else checks.

    A grammar change on the Python side leaves this view applying cleanly and
    returning empty strings for every field — indistinguishable, in the console,
    from a site that has ratified nothing.
    """
    text = migration_text()
    sample = encode(
        parameter="max_operating_pressure",
        dimension_label="pressure",
        direction=SafeDirection.LOWER_IS_SAFER,
        status=EntryStatus.RATIFIED,
        rationale="a rationale long enough to be worth disagreeing with",
    )

    literals = re.findall(r"split_part\(\s*(?:split_part\(\s*)?cv\.canon_text,\s*'([^']+)'", text)
    assert literals, "0207 does not extract anything from cv.canon_text"
    for literal in literals:
        assert literal in sample, (
            f"0207 searches the clause text for {literal!r}, which the encoder does not "
            "emit. The view would apply cleanly and return empty fields forever."
        )

    for label in ("Parameter: ", "Dimension: ", "Direction: ", "Status: ", "Rationale: "):
        assert label in literals, f"0207 does not extract the {label.strip()} field"

    assert PREAMBLE in text, (
        "0207's `answers` column does not test the clause preamble, so a clause that "
        "is not a registry entry could report as one"
    )


def test_every_ratifiable_direction_is_named_in_the_answers_predicate() -> None:
    """A direction the Python side can ratify and the view does not know reads as false.

    That is fail-closed and therefore not dangerous, but it is a disagreement
    between the operator's view of the live registry and the algorithm's, and the
    two must not drift apart quietly.
    """
    text = migration_text()
    for direction in RATIFIABLE_DIRECTIONS:
        assert f"'{direction.value}'" in text, (
            f"0207 does not recognise {direction.value}; the view would report a "
            "ratified parameter as not answering"
        )
    assert f"'{SafeDirection.ABSTAIN.value}'" not in text, (
        "0207 treats ABSTAIN as a direction a clause may carry; it is what the "
        "registry answers when no clause applies and must never be ratifiable"
    )


def test_the_migration_says_out_loud_that_it_is_not_what_the_gate_reads() -> None:
    """A header that omits this invites somebody to wire rule R2 to the view.

    Which would make every historical verdict re-computable under a registry that
    has since moved — the retro-tuning attack, rebuilt in a different column.
    """
    text = migration_text()
    assert "IT IS NOT WHAT THE GATE READS" in text
    assert "AS OF THE COMMIT UNDER TEST" in text
    assert "load_registry" in text


def test_the_migration_claims_no_refusal_it_does_not_implement() -> None:
    """A view has no CHECK, no trigger and no SQLSTATE, and the header must say so."""
    text = migration_text()
    assert "sqlstate:   none" in text
    statement = code_of(split_statements(text)[0]).upper()
    for forbidden in ("CHECK (", "CREATE TRIGGER", "RAISE "):
        assert forbidden not in statement, (
            f"0207's statement contains {forbidden!r}; this file creates a view and "
            "claims no refusal"
        )
