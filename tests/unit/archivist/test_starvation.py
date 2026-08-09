# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""What the Archivist does not hold, asserted over its own AST.

The package's claim about itself is three absences — no tool, no driver, no credential —
and an absence is only a claim if something checks for it. These tests walk every module
in ``mainline_archivist`` rather than reading its dependency list, because a dependency
list records what was declared and an AST records what was written.

``scripts/agents/assert_no_tool_construction.py`` (injection-defence's) runs the same
shape over the whole ingest tree. This file is the package-local half: it fails on this
package alone, in this package's own suite, so the failure names the file that broke it.
"""

from __future__ import annotations

import ast
import re
import sys
import tomllib
from pathlib import Path

import mainline_archivist
import pytest

PACKAGE_ROOT = Path(mainline_archivist.__file__).resolve().parent
MODULES = sorted(PACKAGE_ROOT.glob("*.py"))

#: Anything that could reach a model, a database or a cloud API. A component that reads
#: the attacker's bytes must hold none of them at import time.
FORBIDDEN_TOP_LEVEL = frozenset(
    {
        "anthropic",
        "asyncpg",
        "boto3",
        "botocore",
        "langchain",
        "langgraph",
        "psycopg",
        "psycopg2",
        "requests",
        "sqlalchemy",
        "strands",
        "urllib3",
    }
)

#: The one module permitted to name ``boto3`` at all, and only inside a function body.
CLOUD_MODULES = frozenset({"source.py"})

#: A string literal that *is* a statement, as opposed to prose about one.
_SQL_STATEMENT = re.compile(
    r"^\s*(WITH|SELECT|INSERT|UPSERT|UPDATE|DELETE|TRUNCATE|DROP|ALTER|GRANT|REVOKE|CREATE)\b",
    re.IGNORECASE,
)


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _top_level_imports(tree: ast.Module) -> set[str]:
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module.split(".")[0])
        elif isinstance(node, ast.If):
            # `if TYPE_CHECKING:` blocks are not runtime imports; they cost nothing and
            # hold nothing.
            continue
    return names


def test_the_package_has_modules_to_walk():
    # A scan over an empty list passes vacuously, which is the failure mode of every
    # test like this one.
    assert len(MODULES) >= 6
    assert {path.name for path in MODULES} >= {
        "__init__.py",
        "appraise.py",
        "emit.py",
        "errors.py",
        "ingest.py",
        "source.py",
        "verbatim.py",
    }


@pytest.mark.parametrize("path", MODULES, ids=lambda path: path.name)
def test_no_module_imports_a_driver_or_a_cloud_sdk_at_import_time(path):
    imported = _top_level_imports(_tree(path))

    assert not (imported & FORBIDDEN_TOP_LEVEL), (
        f"{path.name} imports {sorted(imported & FORBIDDEN_TOP_LEVEL)} at module scope. "
        f"A process that ingests a document off local disk must not load a cloud SDK, "
        f"and this package holds no driver at all."
    )


@pytest.mark.parametrize("path", MODULES, ids=lambda path: path.name)
def test_boto3_appears_only_inside_a_function_in_the_cloud_module(path):
    source = path.read_text(encoding="utf-8")
    if "import boto3" not in source:
        return
    assert path.name in CLOUD_MODULES, (
        f"{path.name} names boto3; only {sorted(CLOUD_MODULES)} may, and only inside a "
        f"function body"
    )
    tree = _tree(path)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import) and any(a.name == "boto3" for a in node.names):
            enclosing = _enclosing_function(tree, node)
            assert enclosing is not None, (
                "boto3 is imported outside a function body; the import must be inside "
                "the method that uses it so the offline path never loads it"
            )


def _enclosing_function(tree: ast.Module, target: ast.AST) -> ast.AST | None:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for child in ast.walk(node):
                if child is target:
                    return node
    return None


def test_this_package_constructs_no_tool_surface():
    """Run the repo-wide layer-1 control against this package, rather than a copy of it.

    ``scripts/agents/assert_no_tool_construction.py`` already encodes what counts as a
    tool surface and, importantly, the two narrow exceptions — a literal empty value is a
    *declared absence*, and a value derived from something already called ``tools`` is a
    read of a declared list rather than the construction of a new one. This package
    contains exactly that second shape: ``ingest_document`` passes the tools the process
    holds to ``require_capability`` so layer 5 can refuse them.

    A stricter local reimplementation would fail on the code that enforces the property,
    which is the classic way a control gets deleted. So the control itself is invoked.
    """
    import importlib.util

    repo_root = PACKAGE_ROOT.parents[5]
    script = repo_root / "scripts" / "agents" / "assert_no_tool_construction.py"
    assert script.exists(), script

    spec = importlib.util.spec_from_file_location("_assert_no_tool_construction", script)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Registered before exec: `@dataclass(slots=True)` rebuilds the class and looks its
    # module up in `sys.modules`, so a module executed outside it fails on import.
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)

    findings, files = module.run(repo_root, [PACKAGE_ROOT.parent], check_exempt=False)

    assert files, "the scan found no files, which would pass vacuously"
    assert findings == [], [str(finding) for finding in findings]


@pytest.mark.parametrize("path", MODULES, ids=lambda path: path.name)
def test_no_mutating_sql_appears_anywhere_in_the_package(path):
    # Only literals that *are* statements are scanned — a string beginning with a SQL
    # verb. That exclusion is what lets emit.py both refuse mutating SQL and explain the
    # refusal: its module docstring quotes the `UPDATE mainline.event SET severity_gate =
    # 5` it will not build, and its guard regex names the verbs it rejects. Neither is a
    # statement, and a scan that could not tell them apart would push the explanation out
    # of the code.
    statements = [
        literal for literal in _non_docstring_strings(_tree(path)) if _SQL_STATEMENT.match(literal)
    ]
    for literal in statements:
        verb = _SQL_STATEMENT.match(literal).group(1).upper()  # type: ignore[union-attr]
        assert verb == "INSERT", (
            f"{path.name} builds a {verb} statement: {literal[:80]!r}. agent_ingestor "
            f"holds INSERT on eleven tables and nothing else."
        )


def _non_docstring_strings(tree: ast.Module) -> list[str]:
    docstrings: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", [])
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                docstrings.add(id(body[0].value))
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
    ]


def test_every_rendered_statement_is_an_insert_into_a_granted_table():
    # The AST scan above reads the *source*, where the statements are assembled from
    # fragments. This one reads what is actually built, which is what the database sees.
    from mainline_archivist.emit import (
        INGEST_INSERTABLE_TABLES,
        INSERT_CONTROL_FAILURE_SQL,
        INSERT_EVENT_SQL,
        insert_intake_finding,
    )

    rendered = [
        INSERT_EVENT_SQL,
        INSERT_CONTROL_FAILURE_SQL,
        insert_intake_finding({"document_sha256": "a" * 64, "route": "human_review"}).sql,
    ]

    assert len(rendered) == 3
    for sql in rendered:
        assert sql.startswith("INSERT INTO mainline.")
        target = sql.split()[2]
        assert target in INGEST_INSERTABLE_TABLES, target
        assert "DO UPDATE" not in sql
        assert re.search(r"\b(UPDATE|DELETE|TRUNCATE|DROP|ALTER|GRANT|REVOKE)\b", sql) is None


def test_quarantined_call_has_no_tools_parameter():
    import inspect

    from mainline_agentkit.call import quarantined_call

    parameters = set(inspect.signature(quarantined_call).parameters)
    assert "tools" not in parameters
    assert "tool_choice" not in parameters
    # Asserted from *this* package's suite as well as agentkit's, because the Archivist is
    # the agent whose safety argument rests on it.


def test_the_declared_version_matches_the_distribution():
    pyproject = PACKAGE_ROOT.parents[1] / "pyproject.toml"
    declared = tomllib.loads(pyproject.read_text(encoding="utf-8"))["project"]["version"]

    assert mainline_archivist.__version__ == declared


def test_the_distribution_declares_no_runtime_cloud_dependency():
    pyproject = PACKAGE_ROOT.parents[1] / "pyproject.toml"
    project = tomllib.loads(pyproject.read_text(encoding="utf-8"))["project"]

    assert project["dependencies"] == ["mainline-agentkit", "mainline-quarantine"]
    # boto3 is an extra. Nothing on a dated path may require an AWS credential (PL-3).
    assert "boto3>=1.35" in project["optional-dependencies"]["aws"]


def test_the_public_surface_is_explicit():
    # A star-import surface is a surface nobody reviewed. `__all__` ordering itself is
    # ruff's RUF022 to enforce (SCREAMING_CASE, then CamelCase, then snake_case); what is
    # asserted here is that every name in it resolves and that none is listed twice.
    exported = mainline_archivist.__all__
    assert len(set(exported)) == len(exported)
    for name in exported:
        assert hasattr(mainline_archivist, name), name
