# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Checks on the eleven migrations that need no driver and no cluster.

These are the only assertions about this worker's SQL that run on a machine with
no ``cockroach`` binary, no ``MAINLINE_TEST_DSN`` and no Docker daemon.  They are
worth having for exactly that reason, and they are not a substitute for the
cluster suite: a file can satisfy every rule below and still be refused by
CockroachDB.

WHAT IS CHECKED AND WHY EACH ONE HAS A FAILURE BEHIND IT
--------------------------------------------------------
* the filename convention and the allocation (MR-5, MR-6 rule A/B) — because a
  ``.up.sql`` suffix or a second dot made ``trappoint migrate`` refuse all 121
  files beside it, measured, once;
* one top-level statement per file — because CockroachDB DDL is not
  transactional across statements, so a half-applied file makes the ``dirty``
  marker undiagnosable;
* ``0200`` and above appears in no filename — the ``0200-0219`` annexe these
  files were briefed under is revoked and lint rule B refuses it;
* the four linted header keys and the SPDX header;
* ``(NEW).x`` to READ and ``NEW.x :=`` to WRITE — the two forms are opposite on
  v26.2.5 and getting the read form wrong applies the function and then fails at
  ``CREATE TRIGGER``, one migration downstream of the defect;
* the refusal messages in the SQL are byte-identical to the constants the tests
  pin — three copies, so no copy can drift alone.
"""

from __future__ import annotations

import re

import pytest
from _cbm_sql_support import (
    ABSENT_ACCOUNT_MESSAGE,
    CLOSURE_ABSENT_MESSAGE,
    GENERATION_MESSAGE,
    NO_FIRST_PARENT_MESSAGE,
    OWNED_MIGRATIONS,
    RESIDUE_CLOSURE_MESSAGE,
    STALE_ACCOUNT_MESSAGE,
    UNKNOWN_COMMIT_MESSAGE,
    code_of,
    migration,
    split_statements,
)

FILENAME_RE = re.compile(r"^\d{4}[a-z]?_[a-z0-9_]+\.sql$")

#: (filename, first + last allocation key of the band it must fall in, owner).
#: Taken from ``verticals/mainline/db/migrations.allocation.toml``, which is the
#: authority; the prose tables in the lead plans are its rendering.
BAND_OF = {
    "0049c_cbm_account.sql": ("0049a", "0049z"),
    "0140a_fn_cbm_account_guard.sql": ("0140", "0144z"),
    "0140b_fn_residue_project.sql": ("0140", "0144z"),
    "0140c_fn_cbm_gate_permit.sql": ("0140", "0144z"),
    "0140d_fn_cbm_gate_cr.sql": ("0140", "0144z"),
    "0145a_trg_cbm_account_guard.sql": ("0145", "0149z"),
    "0145b_trg_residue_project.sql": ("0145", "0149z"),
    "0145c_trg_cbm_gate_permit.sql": ("0145", "0149z"),
    "0145d_trg_cbm_gate_cr.sql": ("0145", "0149z"),
    "0145e_trg_cbm_account_append_only.sql": ("0145", "0149z"),
    "0151_v_cbm_ledger.sql": ("0150", "0154z"),
}


def _key(stem_prefix: str) -> tuple[int, str]:
    return int(stem_prefix[:4]), stem_prefix[4:]


@pytest.mark.parametrize("name", OWNED_MIGRATIONS)
def test_the_filename_matches_the_one_convention(name: str) -> None:
    assert FILENAME_RE.match(name), (
        f"{name} does not match MR-5's ^\\d{{4}}[a-z]?_[a-z0-9_]+\\.sql$. A second dot or an "
        "`.up.sql` suffix makes the whole directory undiscoverable, measured once, on 121 files"
    )
    assert ".up.sql" not in name


@pytest.mark.parametrize("name", OWNED_MIGRATIONS)
def test_the_number_falls_in_a_band_this_domain_owns(name: str) -> None:
    first, last = BAND_OF[name]
    stem = name.split("_", 1)[0]
    assert _key(first) <= _key(stem) <= _key(last), (
        f"{name} is outside {first}-{last}. Numbers are granted by "
        "migrations.allocation.toml and enforced by `trappoint migrate lint` rule B"
    )
    assert int(stem[:4]) < 200, (
        f"{name} claims 0200 or above. That range is UNALLOCATED (MRR-7) and the "
        "0200-0219 annexe these files were briefed under is revoked in whole"
    )


@pytest.mark.parametrize("name", OWNED_MIGRATIONS)
def test_exactly_one_top_level_statement(name: str) -> None:
    statements = split_statements(migration(name).read_text(encoding="utf-8"))
    assert len(statements) == 1, (
        f"{name} carries {len(statements)} top-level statements. CockroachDB DDL is not "
        "transactional across statements, so a half-applied file leaves an operator unable to "
        "tell which half is on the cluster"
    )


@pytest.mark.parametrize("name", OWNED_MIGRATIONS)
def test_the_linted_header_keys_are_present(name: str) -> None:
    text = migration(name).read_text(encoding="utf-8")
    assert text.startswith("-- SPDX-FileCopyrightText: 2026 MAINLINE contributors")
    assert "-- SPDX-License-Identifier: FSL-1.1-ALv2" in text
    for key in ("-- MI:", "-- I:", "-- COUNSEL-GATED:", "-- RATIONALE:"):
        assert key in text, f"{name} is missing the linted header key {key!r}"


@pytest.mark.parametrize("name", OWNED_MIGRATIONS)
def test_no_rendered_banner_in_an_authored_band(name: str) -> None:
    """Rule B compares a FILE against the declaration, which is what the string
    comparison that reported zero collisions could not do."""
    assert "@rendered-by" not in migration(name).read_text(encoding="utf-8"), (
        f"{name} carries the rendered banner in an `authored` band, which lint rule B refuses"
    )


_TRIGGER_FUNCTIONS = (
    "0140a_fn_cbm_account_guard.sql",
    "0140b_fn_residue_project.sql",
    "0140c_fn_cbm_gate_permit.sql",
    "0140d_fn_cbm_gate_cr.sql",
)


@pytest.mark.parametrize("name", _TRIGGER_FUNCTIONS)
def test_new_is_parenthesised_to_read_and_bare_to_write(name: str) -> None:
    """The two forms are opposite on v26.2.5 and both are load-bearing.

    ``NEW.col`` in a READ position parses at ``CREATE FUNCTION`` and then fails at
    ``CREATE TRIGGER`` with ``42P01 no data source matches prefix: new`` — the
    function applies, the attachment does not, and the diagnosis is one migration
    downstream of the defect.  ``(NEW).col := …`` in a WRITE position is a plain
    ``42601``.  Measured, both.
    """
    body = code_of(split_statements(migration(name).read_text(encoding="utf-8"))[0])

    bad_reads = sorted(
        {
            match.group(0)
            for match in re.finditer(r"(?<![(.\w])(?:NEW|OLD)\.\w+", body)
            if not body[match.end() :].lstrip().startswith(":=")
        }
    )
    assert not bad_reads, (
        f"{name} reads {bad_reads} without parentheses; CockroachDB v26.2 needs (NEW).col to read"
    )
    bad_writes = re.findall(r"\((?:NEW|OLD)\)\.\w+\s*:=", body)
    assert not bad_writes, (
        f"{name} writes {sorted(set(bad_writes))} with parentheses; CockroachDB v26.2 needs "
        "NEW.col := to write"
    )


@pytest.mark.parametrize(
    ("name", "message"),
    [
        ("0140a_fn_cbm_account_guard.sql", UNKNOWN_COMMIT_MESSAGE),
        ("0140a_fn_cbm_account_guard.sql", CLOSURE_ABSENT_MESSAGE),
        ("0140a_fn_cbm_account_guard.sql", GENERATION_MESSAGE),
        ("0140b_fn_residue_project.sql", NO_FIRST_PARENT_MESSAGE),
        ("0140b_fn_residue_project.sql", RESIDUE_CLOSURE_MESSAGE),
        ("0140c_fn_cbm_gate_permit.sql", ABSENT_ACCOUNT_MESSAGE),
        ("0140c_fn_cbm_gate_permit.sql", STALE_ACCOUNT_MESSAGE),
        ("0140d_fn_cbm_gate_cr.sql", ABSENT_ACCOUNT_MESSAGE),
        ("0140d_fn_cbm_gate_cr.sql", STALE_ACCOUNT_MESSAGE),
    ],
)
def test_the_refusal_message_in_the_sql_is_the_one_the_tests_pin(name: str, message: str) -> None:
    body = code_of(split_statements(migration(name).read_text(encoding="utf-8"))[0])
    assert f"MESSAGE='{message}'" in body, (
        f"{name} does not raise the exact message the suite pins:\n  {message}"
    )


def test_the_two_gates_refuse_with_identical_words() -> None:
    """A database that says something slightly different depending on which
    branch you merged is an exhibit that ends a cross-examination badly."""
    permit = code_of(
        split_statements(migration("0140c_fn_cbm_gate_permit.sql").read_text(encoding="utf-8"))[0]
    )
    cr = code_of(
        split_statements(migration("0140d_fn_cbm_gate_cr.sql").read_text(encoding="utf-8"))[0]
    )
    assert re.findall(r"MESSAGE='([^']+)'", permit) == re.findall(r"MESSAGE='([^']+)'", cr)


def test_the_account_table_declares_the_stored_column_and_the_named_check() -> None:
    body = code_of(
        split_statements(migration("0049c_cbm_account.sql").read_text(encoding="utf-8"))[0]
    )
    assert "CONSTRAINT cbm_balances CHECK (balanced)" in body
    assert "STORED" in body
    for column in (
        "inherited",
        "carried",
        "split_carried",
        "merge_carried",
        "residue_open",
        "residue_disposed",
    ):
        assert column in body
    assert "CASCADE" not in body, (
        "a cascade would let deleting a commit erase the arithmetic that proves an obligation "
        "went missing from it"
    )


def test_the_guard_applies_the_blood_threshold_the_python_uses() -> None:
    """One literal, two places, and a differential test that cannot see a
    disagreement about it unless this assertion holds them together."""
    from mainline_domain.cbm import BLOOD_SEVERITY_THRESHOLD

    body = code_of(
        split_statements(migration("0140a_fn_cbm_account_guard.sql").read_text(encoding="utf-8"))[0]
    )
    assert f"c.max_severity >= {BLOOD_SEVERITY_THRESHOLD}" in body


def test_the_view_is_capped_at_the_mcp_row_limit() -> None:
    from mainline_domain.cbm import LEDGER_ROW_CAP

    body = code_of(
        split_statements(migration("0151_v_cbm_ledger.sql").read_text(encoding="utf-8"))[0]
    )
    assert f"LIMIT {LEDGER_ROW_CAP}" in body
    assert "ledger_truncated" in body
