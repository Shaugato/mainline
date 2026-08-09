# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Static checks on ``0152_v_blame_origin.sql``.  No cluster, no driver, runs everywhere.

These are the assertions that still hold on a machine with no ``cockroach`` binary
and no Docker daemon, and they are not consolation prizes.  Each one pins a
decision that is invisible at runtime until it is wrong in production:

* the depth bound in the SQL and the depth bound in Python are **one** bound;
* the view reads ``clause_blame_current`` and never the closure table (DM-9);
* the join structure — INNER to the closure, LEFT to the blame edge — is what
  makes an *absent* projection distinguishable from a *clean* one (MI22);
* the tie-break is deterministic and NULL-ordering-independent.
"""

from __future__ import annotations

import re

from _diachronic_sql_support import code_of, migration, split_statements
from mainline_domain.diachronic.origin import V_BLAME_ORIGIN_SQL
from mainline_domain.diachronic.version import ORIGIN_DEPTH_BOUND

VIEW_FILE = "0152_v_blame_origin.sql"


def sql_text() -> str:
    return migration(VIEW_FILE).read_text(encoding="utf-8")


def sql_body() -> str:
    statements = split_statements(sql_text())
    assert len(statements) == 1, (
        f"{VIEW_FILE} must contain exactly one top-level statement (MR-5); "
        f"found {len(statements)}"
    )
    return code_of(statements[0])


def test_the_file_is_one_statement_and_it_is_the_view():
    body = sql_body()
    assert body.startswith("CREATE VIEW mainline.v_blame_origin AS")


def test_the_depth_bound_in_the_sql_is_the_depth_bound_in_python():
    """Two copies of a bound that can drift is a bound nobody can rely on.

    ``ORIGIN_DEPTH_BOUND`` appears as a literal in the view because a view takes no
    parameters.  This test is the only thing standing between that and two
    different bounds — one governing the candidate query and one governing the
    first-parent walk — which would produce an origin the walk could never verify.
    """
    body = sql_body()
    found = re.search(r"s\.gen\s*-\s*o\.gen\s*<=\s*(\d+)", body)
    assert found is not None, (
        "the view must carry an explicit generation-distance bound; without one the "
        "join's cost is inferred rather than stated"
    )
    assert int(found.group(1)) == ORIGIN_DEPTH_BOUND


def test_the_view_reads_the_current_view_and_never_the_closure_table():
    """DM-9: ``clause_blame_current`` is the sole read path, so max(closure_gen) is
    taken in exactly one place."""
    body = sql_body()
    assert "mainline.clause_blame_current" in body
    assert "mainline.clause_blame_closure" not in body


def test_the_closure_join_is_inner_and_the_blame_join_is_left():
    """The whole of MI22's distinguishability, expressed as two join keywords.

    INNER to the closure: a subject with no projected closure vanishes from the
    view, which is the signal ``resolve_origin`` raises ``BlameClosureAbsent`` on.
    LEFT to the blame edge: a projected-and-clean closure appears with empty origin
    columns, which is the inert case.  Swap either one and a *missing projection*
    becomes indistinguishable from *no blood*, which makes deleting the projection
    the cheapest attack in the product.
    """
    body = sql_body()
    closure_join = re.search(r"(LEFT\s+)?JOIN\s+mainline\.clause_blame_current", body)
    assert closure_join is not None
    assert closure_join.group(1) is None, "the closure join must be INNER"

    blame_join = re.search(r"(LEFT\s+)?JOIN\s+mainline\.blame_edge", body)
    assert blame_join is not None
    assert blame_join.group(1) is not None, "the blame-edge join must be LEFT"


def test_only_active_blame_edges_can_define_an_origin():
    """MI13 rides in on this predicate: an inferred edge never reaches ``active``."""
    body = sql_body()
    assert "be.state       = 'active'::mainline.blame_state" in body


def test_the_severity_matched_is_the_events_gate_severity_and_the_closures_maximum():
    body = sql_body()
    assert "ev.severity_gate  = cbc.max_severity" in body


def test_the_tie_break_is_deterministic_and_survives_either_null_ordering():
    """CockroachDB sorts NULLs first ascending; PostgreSQL sorts them last.

    Ordering on ``o.gen`` alone would make ``DISTINCT ON`` pick the LEFT-JOIN misses
    on one engine and the real candidates on the other.  The boolean expression
    makes the intent explicit; ``o.commit_id`` last makes a same-generation fork
    resolve the same way twice.
    """
    body = sql_body()
    order = body[body.index(" ORDER BY ") + len(" ORDER BY ") :]
    # Strip trailing comments LINE BY LINE before splitting: the comments here
    # contain commas, and splitting first would shred them into phantom terms.
    uncommented = " ".join(
        re.sub(r"--.*$", "", line).strip() for line in order.splitlines()
    )
    terms = [term.strip().rstrip(";").strip() for term in uncommented.split(",")]
    assert terms == [
        "s.clause_uuid",
        "s.commit_id",
        "(o.commit_id IS NULL)",
        "o.gen",
        "o.commit_id",
    ], f"the DISTINCT ON tie-break is not the one the header documents: {terms}"


def test_there_is_no_recursion_in_the_view():
    """A recursive CTE in a view has no seed to be parameterised by, so it would
    enumerate the transitive closure of every commit and then filter."""
    body = sql_body().upper()
    assert "RECURSIVE" not in body
    assert "AS OF SYSTEM TIME" not in body


def test_the_python_read_selects_only_columns_the_view_projects():
    """A column named in the read and absent from the view is a runtime 42703.

    Cheap to check statically and expensive to discover at 3 a.m., which is the
    whole argument for a shape suite.
    """
    body = sql_body()
    projected = set(re.findall(r"AS\s+(\w+)\s*(?:,|\n)", body))
    selected = re.search(r"SELECT(.*?)FROM mainline\.v_blame_origin", V_BLAME_ORIGIN_SQL, re.S)
    assert selected is not None
    read = {name.strip() for name in selected.group(1).split(",") if name.strip()}
    assert read <= projected, (
        f"the read names columns the view does not project: {read - projected}"
    )


def test_the_header_carries_the_four_linted_keys_and_names_its_band():
    text = sql_text()
    for key in ("MI:", "I:", "COUNSEL-GATED:", "RATIONALE:"):
        assert f"-- {key}" in text, f"the header is missing the {key!r} key"
    assert "0150-0154" in text
    assert "migrations.allocation.toml" in text


def test_the_header_states_the_dependency_that_is_not_yet_on_disk():
    """Honesty, asserted.

    ``dm-blame``'s three objects had not landed when this file was written, so the
    view cannot be applied against the tree as it stands.  A header that did not say
    so would be a header that let somebody discover it from a failed deploy.
    """
    text = sql_text()
    assert "dm-blame" in text
    assert "HAD NOT LANDED" in text
