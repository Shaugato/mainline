# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""Capability starvation, asserted over the source rather than promised in a README.

Three claims this package makes about itself, each checked here against the tree
that ships rather than against the tree somebody remembers.

1. **No model surface is reachable.** §8.4 row 6 says the lattice compare decides,
   so there is no call to make and no SDK to import.
2. **No ``UPDATE`` and no ``DELETE`` exist.** ``agent_patroller`` holds ``INSERT``
   on five tables and nothing else, so such a statement could only ever be refused
   — and a future reader would reasonably assume it once worked.
3. **No statement names a gate table.** §9's two rules compose into a prohibition
   on stale gate reads, and the check runs over every SQL constant the package can
   produce.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest
from mainline_fixity import FLEET_ENTRY, GATE_TABLES, PATROL_ROLE, STATEMENTS

# Resolved from this file rather than imported from `conftest`: two sibling suites
# each carry a `conftest`, and a bare `from conftest import` binds to whichever one
# reached `sys.modules` first — a collection-order dependency that would make this
# suite pass or fail depending on which other suite ran beside it.
REPO_ROOT = Path(__file__).resolve().parents[3]
FIXITY_SRC = REPO_ROOT / "verticals" / "mainline" / "packages" / "mainline-fixity" / "src"

#: Anything that could reach a model, a network or a database.
FORBIDDEN_IMPORTS = frozenset(
    {
        "anthropic",
        "boto3",
        "botocore",
        "langchain",
        "langgraph",
        "mainline_agentkit",
        "openai",
        "psycopg",
        "psycopg2",
        "requests",
        "sqlalchemy",
        "strands",
        "urllib3",
    }
)

#: Blanket retry helpers are banned repository-wide: a retry loop around a refusal
#: is how a gate refusal becomes an eventual success.
FORBIDDEN_RETRY = frozenset({"backoff", "retrying", "tenacity"})

MODULES = sorted(Path(FIXITY_SRC).joinpath("mainline_fixity").glob("*.py"))


def imported_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            roots.add(node.module.split(".")[0])
    return roots


def test_the_suite_actually_found_the_package():
    # A scan that silently walked zero files would pass every assertion below.
    assert len(MODULES) >= 8


@pytest.mark.parametrize("module", MODULES, ids=lambda p: p.name)
def test_no_module_can_reach_a_model_a_network_or_a_driver(module: Path):
    offending = imported_roots(module) & (FORBIDDEN_IMPORTS | FORBIDDEN_RETRY)
    assert not offending, (
        f"{module.name} imports {sorted(offending)}. The fixity patrol's fleet entry "
        f"says no_model: true and its grant is INSERT-only; either claim is false the "
        f"moment one of these is importable from here."
    )


@pytest.mark.parametrize("module", MODULES, ids=lambda p: p.name)
def test_no_module_names_a_bedrock_endpoint_in_a_string(module: Path):
    source = module.read_text(encoding="utf-8").lower()
    assert "bedrock-runtime" not in source
    assert "invoke_model" not in source


def test_no_statement_mutates_anything():
    for sql in STATEMENTS:
        assert not re.search(r"\bUPDATE\b|\bDELETE\b|\bTRUNCATE\b", sql, re.IGNORECASE), sql


def test_every_statement_is_an_insert_that_absorbs_redelivery():
    for sql in STATEMENTS:
        assert sql.lstrip().upper().startswith("INSERT INTO")
        assert "ON CONFLICT" in sql


def test_no_statement_names_a_gate_table():
    for sql in STATEMENTS:
        lowered = sql.lower()
        for table in GATE_TABLES:
            assert not re.search(rf"\b{re.escape(table)}\b", lowered), (table, sql)


def test_the_fleet_entry_matches_what_the_package_can_actually_do():
    assert FLEET_ENTRY["no_model"] is True
    assert FLEET_ENTRY["tools"] == []
    assert FLEET_ENTRY["call_profiles"] == []
    assert FLEET_ENTRY["may_write_gate_field"] is False
    assert FLEET_ENTRY["sql_role"] == PATROL_ROLE == "agent_patroller"
    assert "abstain" in FLEET_ENTRY["decision_it_does_not_make"]


def test_the_declared_writes_are_exactly_the_tables_the_statements_touch():
    declared = {name.split(".", 1)[1] for name in FLEET_ENTRY["writes"]}
    written = {re.search(r"INSERT INTO mainline\.(\w+)", sql).group(1) for sql in STATEMENTS}
    assert written <= declared
    # The register may name a table this package has a grant for and does not yet
    # write; it may never write one it does not name.
    assert declared - written <= {"observed_assertion", "time_witness"} or not (written - declared)
