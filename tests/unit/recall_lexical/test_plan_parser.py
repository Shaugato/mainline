# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The plan assertion, tested against specimens of the ``EXPLAIN`` grammar.

Provenance, stated plainly: the files under ``fixtures/`` are **hand-written examples of
CockroachDB's ``EXPLAIN`` text format, not captures from a live cluster** — no CockroachDB was
reachable from the machine this band was written on.  They make the parser and the assertion
testable with no cluster.  They do not prove what a real optimiser does; that is
``tests/integration/recall_lexical/test_plan_assertion_live.py``, which runs ``EXPLAIN`` against a
real cluster and skips with a reason when there is none.  A skipped run verifies nothing.

Four specimens, four distinct ways the check has to behave:

``explain_constrained``
    what the shipped statement should produce — ``lex_posting`` on its primary key with
    ``spans: 3 spans``.  Note that ``lex_doclen`` is scanned in full in the same plan and the
    assertion does not care: the claim is about the posting list, whose size is the product of
    the corpus and the vocabulary, not about a table with one row per document.
``explain_full_scan``
    the defect this module exists for.  The ranking is still correct; only the plan is wrong.
``explain_wrong_index``
    constrained, but on the wrong key.  A naive "no FULL SCAN" check passes here.
``explain_no_posting_access``
    the vacuous pass: no access at all.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from trappoint_recall.lexical.plan import (
    PlanAssertionError,
    assert_constrained_lex_scan,
    parse_plan,
    plan_digest,
    plan_text_from_rows,
)


def load(fixtures_dir: Path, name: str) -> str:
    return (fixtures_dir / f"explain_{name}.txt").read_text(encoding="utf-8")


def test_the_shipped_shape_is_accepted(fixtures_dir: Path) -> None:
    approved = assert_constrained_lex_scan(load(fixtures_dir, "constrained"))
    assert len(approved) == 1
    node = approved[0]
    assert node.bare_table == "lex_posting"
    assert node.index == "lex_posting_pk"
    assert node.spans == "3 spans"
    assert not node.is_full_scan


def test_a_full_scan_of_the_posting_list_is_refused(fixtures_dir: Path) -> None:
    with pytest.raises(PlanAssertionError, match="scanned WITHOUT a constrained span"):
        assert_constrained_lex_scan(load(fixtures_dir, "full_scan"))


def test_a_constrained_scan_on_the_wrong_index_is_refused(fixtures_dir: Path) -> None:
    """The failure a bare "no FULL SCAN" check would miss."""
    plan = load(fixtures_dir, "wrong_index")
    assert "FULL SCAN" not in plan, "premise: this plan contains no full scan"
    with pytest.raises(PlanAssertionError, match="rather than lex_posting_pk"):
        assert_constrained_lex_scan(plan)


def test_a_plan_that_never_touches_the_posting_list_is_refused(fixtures_dir: Path) -> None:
    """A vacuous pass is a failure: "no full scan" is trivially true of no scan."""
    with pytest.raises(PlanAssertionError, match="never accesses lex_posting"):
        assert_constrained_lex_scan(load(fixtures_dir, "no_posting_access"))


def test_a_lookup_join_onto_the_primary_key_is_accepted(fixtures_dir: Path) -> None:
    approved = assert_constrained_lex_scan(load(fixtures_dir, "lookup_join"))
    assert approved[0].spans is None
    assert approved[0].equality == "(site_id, term) = (site_id, term)"
    assert approved[0].is_constrained


# ── the parser ───────────────────────────────────────────────────────────────────────────────


def test_every_table_access_is_found(fixtures_dir: Path) -> None:
    nodes = parse_plan(load(fixtures_dir, "constrained"))
    assert [(n.bare_table, n.index, n.spans) for n in nodes] == [
        ("lex_stats", "lex_stats_pk", None),
        ("lex_posting", "lex_posting_pk", "3 spans"),
        ("lex_doclen", "lex_doclen_pk", "FULL SCAN"),
    ]


def test_node_kinds_are_carried_through(fixtures_dir: Path) -> None:
    nodes = parse_plan(load(fixtures_dir, "constrained"))
    assert [n.node for n in nodes] == ["lookup join", "scan", "scan"]


def test_row_count_estimates_are_not_mistaken_for_spans(fixtures_dir: Path) -> None:
    posting = next(
        n for n in parse_plan(load(fixtures_dir, "constrained")) if n.bare_table == "lex_posting"
    )
    assert posting.spans == "3 spans"


def test_a_schema_qualified_table_name_is_the_same_table() -> None:
    plan = "  • scan\n        table: mainline.lex_posting@lex_posting_pk\n        spans: 2 spans"
    assert assert_constrained_lex_scan(plan)[0].bare_table == "lex_posting"


def test_an_empty_plan_is_refused_rather_than_silently_passing() -> None:
    with pytest.raises(PlanAssertionError, match="never accesses lex_posting"):
        assert_constrained_lex_scan("")


def test_driver_rows_are_joined_into_one_text() -> None:
    rows = [
        ("  • scan",),
        ("        table: lex_posting@lex_posting_pk",),
        ("        spans: 1 span",),
    ]
    assert assert_constrained_lex_scan(plan_text_from_rows(rows))[0].spans == "1 span"
    assert plan_text_from_rows("already text") == "already text"


# ── the digest ───────────────────────────────────────────────────────────────────────────────


def test_the_digest_ignores_row_counts_but_not_shape(fixtures_dir: Path) -> None:
    plan = load(fixtures_dir, "constrained")
    grown = plan.replace("2,000 (100%", "9,000,000 (100%").replace(
        "41 (0.02%", "918 (0.02%"
    )
    assert plan_digest(grown) == plan_digest(plan)
    assert plan_digest(load(fixtures_dir, "full_scan")) != plan_digest(plan)
