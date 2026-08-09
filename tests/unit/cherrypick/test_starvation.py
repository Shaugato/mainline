# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The model surface is one named module, and the deterministic half never touches it.

The package's structural claim is that everything except conflict *narration* is
model-free: the three-way merge, the patch digest, the envelope, the propagation
state machine and every statement. Reaching a model means naming
``mainline_cherrypick.narrate``, and naming it is a line in a diff.

This suite asserts that over the source tree that ships rather than over the tree
somebody remembers.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest
from mainline_cherrypick import FLEET_ENTRY, FLEET_ROLE, FORBIDDEN_TARGETS, STATEMENTS

# Resolved from this file rather than imported from `conftest`: two sibling suites
# each carry a `conftest`, and a bare `from conftest import` binds to whichever one
# reached `sys.modules` first — a collection-order dependency that would make this
# suite pass or fail depending on which other suite ran beside it.
REPO_ROOT = Path(__file__).resolve().parents[3]
CHERRYPICK_SRC = REPO_ROOT / "verticals" / "mainline" / "packages" / "mainline-cherrypick" / "src"

#: Anything that reaches a model, a network or a database directly. `narrate` is
#: allowed `mainline_agentkit` and nothing else; every other module is allowed none
#: of them.
MODEL_SURFACE = frozenset({"mainline_agentkit"})
FORBIDDEN_EVERYWHERE = frozenset(
    {
        "anthropic",
        "backoff",
        "boto3",
        "botocore",
        "langchain",
        "langgraph",
        "openai",
        "psycopg",
        "psycopg2",
        "requests",
        "retrying",
        "sqlalchemy",
        "strands",
        "tenacity",
        "urllib3",
    }
)

PACKAGE = Path(CHERRYPICK_SRC) / "mainline_cherrypick"
MODULES = sorted(PACKAGE.glob("*.py"))
DETERMINISTIC = [module for module in MODULES if module.name != "narrate.py"]


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
    assert len(MODULES) >= 9
    assert (PACKAGE / "narrate.py").exists()


@pytest.mark.parametrize("module", MODULES, ids=lambda p: p.name)
def test_no_module_imports_a_driver_a_retry_helper_or_a_second_model_client(module: Path):
    offending = imported_roots(module) & FORBIDDEN_EVERYWHERE
    assert not offending, (
        f"{module.name} imports {sorted(offending)}. There is exactly one model surface "
        f"in this repository and this package holds no driver."
    )


@pytest.mark.parametrize("module", DETERMINISTIC, ids=lambda p: p.name)
def test_the_deterministic_half_reaches_no_model_surface(module: Path):
    offending = imported_roots(module) & MODEL_SURFACE
    assert not offending, (
        f"{module.name} imports {sorted(offending)}. Everything except narrate.py must "
        f"be importable, testable and auditable with mainline-agentkit absent."
    )


def test_the_package_root_does_not_re_export_the_model_surface():
    root = (PACKAGE / "__init__.py").read_text(encoding="utf-8")
    assert "from .narrate import" not in root
    assert "narrate" not in {name.strip('"') for name in re.findall(r'"(\w+)"', root)}


def test_no_statement_reaches_a_forbidden_object():
    for sql in STATEMENTS:
        lowered = sql.lower()
        for target in FORBIDDEN_TARGETS:
            assert not re.search(rf"\b{re.escape(target)}\b", lowered), (target, sql)


def test_there_is_exactly_one_update_and_it_touches_prop_state():
    updates = [sql for sql in STATEMENTS if sql.lstrip().upper().startswith("UPDATE")]
    assert len(updates) == 1
    assert "mainline.propagation" in updates[0]
    assert "SET state" in updates[0]


def test_no_statement_deletes_anything():
    for sql in STATEMENTS:
        assert not re.search(r"\bDELETE\b|\bTRUNCATE\b|\bDROP\b", sql, re.IGNORECASE), sql


def test_every_insert_absorbs_redelivery():
    for sql in STATEMENTS:
        if sql.lstrip().upper().startswith("INSERT"):
            assert "ON CONFLICT" in sql, sql


def test_the_fleet_entry_matches_what_the_package_can_actually_do():
    assert FLEET_ENTRY["tools"] == []
    assert FLEET_ENTRY["call_profiles"] == ["narration"]
    assert FLEET_ENTRY["may_write_gate_field"] is False
    assert FLEET_ENTRY["sql_role"] == FLEET_ROLE == "agent_fleet"
    assert "never auto-applied" in FLEET_ENTRY["decision_it_does_not_make"]


def test_the_only_declared_profile_is_a_tier_two_narrator():
    from mainline_agentkit import NARRATION, Tier

    assert NARRATION.profile_id in FLEET_ENTRY["call_profiles"]
    assert NARRATION.tier is Tier.T2
    assert NARRATION.may_write_gate_field is False
    assert NARRATION.describe()["tools"] == []
