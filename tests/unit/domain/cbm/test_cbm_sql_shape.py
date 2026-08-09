# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The Python and the SQL must be talking about the same three relations.

The differential in ``tests/integration/algorithms/cbm/test_differential_200.py``
proves the two derivations AGREE; it needs a cluster.  This file checks the much
cheaper property that they are reading the same columns of the same tables, and
it runs anywhere.

WHY THE THRESHOLD IS CHECKED HERE AND NOT ONLY THERE
----------------------------------------------------
``BLOOD_SEVERITY_THRESHOLD`` is a literal in two places by design: the SQL applies
it in ``0140a``'s ``anc`` CTE, and the Python applies it in
:meth:`AncestorFacts.is_blood_bearing` over rows whose fetch query deliberately
does NOT filter (:data:`ANCESTOR_SQL`).  That separation is what lets the
differential see a disagreement about the threshold at all — and this assertion
is what stops the two from being edited apart between differential runs.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from mainline_domain.cbm import (
    ANCESTOR_SQL,
    BLOOD_SEVERITY_THRESHOLD,
    CLOSURE_MISSING_SQL,
    COMMIT_SQL,
    LEDGER_ROW_CAP,
    PROJECTOR_VERSION,
)

_REPO_ROOT = Path(__file__).resolve().parents[4]
_MIGRATIONS = _REPO_ROOT / "verticals" / "mainline" / "db" / "migrations"

GUARD = _MIGRATIONS / "0140a_fn_cbm_account_guard.sql"
TABLE = _MIGRATIONS / "0049c_cbm_account.sql"
VIEW = _MIGRATIONS / "0151_v_cbm_ledger.sql"


def _sql(path: Path) -> str:
    if not path.is_file():
        pytest.skip(f"{path.name} is not in the tree; the SQL half of this check cannot run")
    return path.read_text(encoding="utf-8")


def test_the_guard_applies_the_same_blood_threshold_the_python_does() -> None:
    assert BLOOD_SEVERITY_THRESHOLD == 4
    assert f"c.max_severity >= {BLOOD_SEVERITY_THRESHOLD}" in _sql(GUARD)


def test_the_client_query_deliberately_does_not_apply_the_threshold() -> None:
    """If it did, the differential could not see a disagreement about it.

    This is the one place in the package where a MISSING filter is the correct
    code, so it gets an assertion of its own rather than a comment somebody will
    delete as dead weight.
    """
    assert "max_severity" in ANCESTOR_SQL
    assert ">= 4" not in ANCESTOR_SQL
    assert "a.sev" in ANCESTOR_SQL, "the severity must be RETURNED so Python can apply it"


@pytest.mark.parametrize(
    "relation",
    [
        "mainline.clause_version",
        "mainline.clause_blame_current",
        "mainline.identity_residue",
        "mainline.identity_assignment",
    ],
)
def test_both_derivations_read_the_same_relations(relation: str) -> None:
    combined = COMMIT_SQL + CLOSURE_MISSING_SQL + ANCESTOR_SQL
    assert relation in combined, f"the client projector never reads {relation}"
    assert relation in _sql(GUARD), f"the trigger never reads {relation}"


def test_neither_derivation_reads_the_closure_table_directly() -> None:
    """DM-9: ``mainline.clause_blame_current`` is the sole read path.

    ``max(closure_gen)`` discipline has to be structural.  One forgotten call site
    reads a superseded generation, a superseded generation is a LOWER severity,
    and a lower severity is a gate that opens.  The repository-wide grep
    (``scripts/grep_closure_readpath.py``, owned by dm-blame) enforces the same
    rule across every file; this is the local half, so the package fails its own
    tests before it fails somebody else's lint.
    """
    combined = COMMIT_SQL + CLOSURE_MISSING_SQL + ANCESTOR_SQL
    assert "clause_blame_closure" not in combined
    body = "\n".join(
        line for line in _sql(GUARD).splitlines() if not line.lstrip().startswith("--")
    )
    assert "clause_blame_closure" not in body


def test_the_group_by_that_makes_the_law_a_law_is_in_both() -> None:
    """Counting ANCESTORS and not ROWS, on both sides.

    ``identity_residue``'s unique key includes ``reason`` and a split writes one
    ``identity_assignment`` row per child, so a ``count(*)`` over either would
    make the right-hand side exceed the left on ordinary matcher output.
    """
    for text in (ANCESTOR_SQL, _sql(GUARD)):
        assert text.count("GROUP BY r.ancestor_clause_uuid") == 1
        assert text.count("GROUP BY g.ancestor_clause_uuid") == 1
        assert "bool_or(r.disposition_id IS NULL)" in text


def test_the_first_parent_is_the_baseline_on_both_sides() -> None:
    """Reading the severity from the commit itself would let the commit that
    dropped a control decide how serious dropping it was."""
    for text in (COMMIT_SQL, _sql(GUARD)):
        assert "parent_ord = 0" in text


def test_the_six_counters_are_exactly_the_columns_the_table_declares() -> None:
    table = _sql(TABLE)
    for column in (
        "inherited",
        "carried",
        "split_carried",
        "merge_carried",
        "residue_open",
        "residue_disposed",
    ):
        assert re.search(rf"^\s+{column}\s+INT8\s+NOT NULL", table, re.MULTILINE), (
            f"{column} is not declared as `INT8 NOT NULL` on mainline.cbm_account"
        )
    assert "CONSTRAINT cbm_balances CHECK (balanced)" in table


def test_the_projector_version_is_a_stamped_string_and_not_a_number() -> None:
    """It is written to a ``STRING NOT NULL`` column with a ``<> ''`` check, and it
    is what tells a versioning story apart from a tampering story."""
    assert isinstance(PROJECTOR_VERSION, str)
    assert PROJECTOR_VERSION.strip() == PROJECTOR_VERSION != ""
    assert len(PROJECTOR_VERSION) <= 32, (
        "0151 clips projector_ver to 32 characters to stay inside the 10 KiB MCP response cap"
    )


def test_the_view_cap_matches_the_constant_the_tests_use() -> None:
    assert LEDGER_ROW_CAP == 25
    assert f"LIMIT {LEDGER_ROW_CAP}" in _sql(VIEW)
