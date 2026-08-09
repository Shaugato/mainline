# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Static checks on ``0049b_commutation_edge.sql``.  No cluster, no driver, runs everywhere.

The three CHECKs on this table are the whole of its claim, and each of them has a
Python counterpart that has to agree with it.  These tests hold the two halves
together without a database:

===========================  =======================================================
``canonical_direction``      ``mainline_domain.diachronic.commutation.canonical``
``overlap_nonempty``         ``CommutationEdge.footprint_overlap`` is never empty
``computed_by_stated``       ``version.computed_by()`` is never the empty string
===========================  =======================================================
"""

from __future__ import annotations

import re

from _diachronic_sql_support import code_of, migration, split_statements
from mainline_domain.diachronic.commutation import COMMUTATION_EDGE_INSERT_SQL

TABLE_FILE = "0049b_commutation_edge.sql"


def sql_text() -> str:
    return migration(TABLE_FILE).read_text(encoding="utf-8")


def sql_body() -> str:
    statements = split_statements(sql_text())
    assert len(statements) == 1, (
        f"{TABLE_FILE} must contain exactly one top-level statement (MR-5); "
        f"found {len(statements)}"
    )
    return code_of(statements[0])


def test_the_file_is_one_statement_and_it_is_the_table():
    assert sql_body().startswith("CREATE TABLE mainline.commutation_edge (")


def test_the_primary_key_is_the_four_identity_columns_and_not_the_site():
    """``site_id`` out of the key on purpose: a commit is already site-scoped through
    ``commit_obj``, and putting the site in the key would let two rows for one pair
    exist under two site values — a disagreement the CHECKs could not see."""
    body = sql_body()
    found = re.search(
        r"CONSTRAINT commutation_edge_pk PRIMARY KEY\s*\(([^)]*)\)", body, re.S
    )
    assert found is not None
    columns = [c.strip() for c in found.group(1).split(",")]
    assert columns == ["from_commit", "from_clause_uuid", "to_commit", "to_clause_uuid"]


def test_the_canonical_direction_check_is_a_strict_lexicographic_ordering():
    """Strict ``<`` is what makes the reverse row AND the self row unstorable.

    Written longhand rather than as a row-value comparison: a CHECK is the wrong
    place to depend on a parse the whole table's storability turns on, and the
    longhand form is what a reader verifying the Python canonicaliser has to read
    anyway.
    """
    body = sql_body()
    assert "from_commit < to_commit" in body
    assert "from_commit = to_commit AND from_clause_uuid < to_clause_uuid" in body
    assert "<=" not in body.split("CONSTRAINT canonical_direction")[1].split("CONSTRAINT")[0]


def test_the_overlap_check_coalesces_because_array_length_answers_null_on_an_empty_array():
    """The platform trap this constraint would otherwise walk straight into.

    ``array_length(x, 1)`` returns NULL — not 0 — for an empty array, and a CHECK
    whose expression evaluates to NULL **passes**.  Written the naive way this
    constraint would admit precisely the rows it exists to refuse, which is an empty
    ``footprint_overlap``: a dependency assertion with no evidence behind it.
    """
    body = sql_body()
    assert "COALESCE(array_length(footprint_overlap, 1), 0) >= 1" in body


def test_both_foreign_keys_are_composite_and_point_at_a_version_not_a_clause():
    """A derived edge names two VERSIONS. A pointer that resolves to a clause but not
    to the version of it that was edited points at the wrong fact."""
    body = sql_body()
    for side in ("from", "to"):
        assert (
            f"FOREIGN KEY ({side}_clause_uuid, {side}_commit)\n"
            "    REFERENCES mainline.clause_version (clause_uuid, commit_id)" in body
        )


def test_nothing_cascades():
    """A CASCADE on a table of derived safety dependencies would let a delete
    somewhere else silently retract an antecedent a gate had already read."""
    assert "CASCADE" not in sql_body().upper()


def test_the_provenance_columns_are_not_nullable_and_are_check_constrained():
    body = sql_body()
    assert "computed_by       STRING      NOT NULL" in body
    assert "footprint_ver     STRING      NOT NULL" in body
    assert "CONSTRAINT computed_by_stated CHECK (computed_by <> '')" in body
    assert "CONSTRAINT footprint_ver_stated CHECK (footprint_ver <> '')" in body


def test_the_reverse_lookup_index_exists_because_rows_are_stored_one_way_only():
    assert "INDEX by_to (to_commit, to_clause_uuid)" in sql_body()


def test_every_column_the_insert_binds_exists_in_the_table():
    """A column named in the INSERT and absent from the DDL is a runtime 42703."""
    body = sql_body()
    column_re = r"^\s{2}(\w+)\s+(?:UUID|BYTES|STRING\[\]|STRING|TIMESTAMPTZ)"
    columns = set(re.findall(column_re, body, re.M))
    named = re.search(
        r"INSERT INTO mainline\.commutation_edge\s*\(([^)]*)\)",
        COMMUTATION_EDGE_INSERT_SQL,
        re.S,
    )
    assert named is not None
    bound = {c.strip() for c in named.group(1).replace("\n", " ").split(",")}
    assert bound <= columns, f"the INSERT names columns the table does not have: {bound - columns}"


def test_the_insert_conflict_target_is_the_primary_key():
    """``ON CONFLICT`` on anything other than the PK would silently not fire."""
    found = re.search(r"ON CONFLICT \(([^)]*)\)", COMMUTATION_EDGE_INSERT_SQL, re.S)
    assert found is not None
    target = [c.strip() for c in found.group(1).replace("\n", " ").split(",")]
    assert target == ["from_commit", "from_clause_uuid", "to_commit", "to_clause_uuid"]


def test_the_header_carries_the_four_linted_keys_and_names_its_band():
    text = sql_text()
    for key in ("MI:", "I:", "COUNSEL-GATED:", "RATIONALE:"):
        assert f"-- {key}" in text, f"the header is missing the {key!r} key"
    assert "0049a-0049z" in text
    assert "migrations.allocation.toml" in text


def test_the_header_admits_that_append_only_is_not_yet_enforced():
    """MI01 is cited and its trigger is owed. A header that overclaimed would be
    worse than one that never mentioned the invariant."""
    text = sql_text()
    assert "APPEND-ONLY IS NOT YET ENFORCED" in text
    assert "fn_refuse_mutation" in text
