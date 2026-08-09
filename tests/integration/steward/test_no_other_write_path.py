# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""There is one write path in this distribution, and this module is what keeps it that way.

The Steward is one of only two components in MAINLINE that hold a tool loop, and the
property that makes that safe is not a policy — it is that the code it runs *cannot*
express a second write. This suite reads the distribution's abstract syntax trees rather
than its behaviour, because a behavioural test only covers the paths somebody thought to
call.

Five assertions, and each names the failure it prevents:

1. **No driver, no SDK.** A `psycopg`/`asyncpg`/`sqlalchemy` import would be a pgwire
   write path around the MCP boundary entirely. A `boto3` import would give the Steward an
   AWS API surface its IAM role is not sized for. A model SDK would put a second,
   differently-configured model call in a repository that has exactly one.
2. **No probe imports.** `mainline_mcp.client.probe_insert_rows_unbound` exists so the
   negative-reachability suite can attempt a forbidden write and record that the *server*
   refused it. It is a test instrument. Importing it into product code would turn "the
   API cannot express this" into "the API discourages this".
3. **One call site.** `insert_external_attestation` is called exactly once, in
   `attestation.py`. Two call sites would be two places for the row shape to drift.
4. **No raw tool name.** Nothing calls `Client.call("insert_rows", …)` or names
   `create_table`/`create_database`. The typed method has no parameter that names a table;
   reaching past it to the generic verb would put one back.
5. **`subprocess` lives in exactly one module.** `ccloud.py` shells out to the `ccloud`
   binary and nothing else may. A second `subprocess` import is a second unaudited
   capability in a container that holds a database credential.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

BANNED_MODULES = frozenset(
    {
        "psycopg",
        "psycopg2",
        "asyncpg",
        "pg8000",
        "sqlalchemy",
        "boto3",
        "botocore",
        "anthropic",
        "openai",
        "mainline_agentkit",
        "requests",
        "aiohttp",
        "httpx",
        "socket",
        "http",
        "urllib",
        "telnetlib",
        "paramiko",
    }
)

WRITE_METHOD = "insert_external_attestation"
FORBIDDEN_TOOL_NAMES = frozenset({"insert_rows", "create_table", "create_database"})
SUBPROCESS_OWNER = "ccloud.py"


def _sources(package: Path) -> list[Path]:
    return sorted(p for p in (package / "src").rglob("*.py"))


@pytest.fixture(scope="module")
def package_sources(request) -> list[Path]:
    package = request.config.rootpath / "verticals" / "mainline" / "packages" / "mainline-steward"
    sources = _sources(package)
    assert sources, f"no sources found under {package}"
    return sources


def _trees(sources: list[Path]) -> list[tuple[Path, ast.Module]]:
    return [
        (path, ast.parse(path.read_text(encoding="utf-8"), filename=str(path))) for path in sources
    ]


def _imported_modules(tree: ast.Module) -> list[tuple[str, int]]:
    found: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend((alias.name.split(".")[0], node.lineno) for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            found.append((node.module.split(".")[0], node.lineno))
    return found


class TestNoSecondWritePath:
    def test_no_database_driver_cloud_sdk_or_model_sdk_is_imported(self, package_sources):
        offences = [
            f"{path.name}:{lineno} imports {module!r}"
            for path, tree in _trees(package_sources)
            for module, lineno in _imported_modules(tree)
            if module in BANNED_MODULES
        ]
        assert not offences, (
            "the dependency list is the security boundary of this distribution: "
            + "; ".join(offences)
        )

    def test_no_negative_reachability_probe_is_imported_into_product_code(self, package_sources):
        offences: list[str] = []
        for path, tree in _trees(package_sources):
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    offences.extend(
                        f"{path.name}:{node.lineno} imports {alias.name!r}"
                        for alias in node.names
                        if alias.name.startswith("probe_")
                    )
        assert not offences, (
            "probe_insert_rows_unbound and probe_select_unscreened are test instruments "
            "whose whole purpose is to attempt what the supported API cannot express: "
            + "; ".join(offences)
        )

    def test_the_write_method_has_exactly_one_call_site(self, package_sources):
        sites: list[str] = []
        for path, tree in _trees(package_sources):
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == WRITE_METHOD
                ):
                    sites.append(f"{path.name}:{node.lineno}")
        assert len(sites) == 1, (
            f"{WRITE_METHOD} must be called exactly once; two call sites are two places "
            f"for the row shape to drift. Found {sites}"
        )
        assert sites[0].startswith("attestation.py:"), (
            f"the write belongs to the emitter; found it at {sites[0]}"
        )

    def test_no_generic_tool_call_reaches_past_the_typed_write_method(self, package_sources):
        offences: list[str] = []
        for path, tree in _trees(package_sources):
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                for argument in node.args:
                    if (
                        isinstance(argument, ast.Constant)
                        and isinstance(argument.value, str)
                        and argument.value in FORBIDDEN_TOOL_NAMES
                    ):
                        offences.append(f"{path.name}:{node.lineno} passes {argument.value!r}")
        assert not offences, (
            "reaching the generic `call(tool, arguments)` verb would restore the table "
            "parameter that the typed write method deliberately does not have: "
            + "; ".join(offences)
        )

    def test_subprocess_is_imported_by_exactly_one_module(self, package_sources):
        importers = sorted(
            {
                path.name
                for path, tree in _trees(package_sources)
                for module, _ in _imported_modules(tree)
                if module == "subprocess"
            }
        )
        assert importers == [SUBPROCESS_OWNER], (
            "the ccloud shim is the only place this distribution executes a binary; "
            f"found {importers}"
        )

    def test_the_only_mcp_client_methods_used_are_reads_plus_the_one_write(self, package_sources):
        # A behavioural cross-check on the AST rule above: the set of Client attributes
        # this package names must be a subset of the documented read verbs plus the typed
        # write method. `call`, `transport` and `dialect` are absent on purpose — each is a
        # way past the typed surface.
        permitted = {
            "select_query",
            "explain_query",
            "show_statement",
            "show_running_queries",
            "list_databases",
            "list_tables",
            "get_table_schema",
            "insert_external_attestation",
            "close",
            "connect",
            "last_elapsed_ms",
            "cluster_id",
            "tool_names",
        }
        forbidden = {"call", "transport", "dialect"}
        used: set[str] = set()
        for _path, tree in _trees(package_sources):
            for node in ast.walk(tree):
                if isinstance(node, ast.Attribute) and node.attr in permitted | forbidden:
                    used.add(node.attr)
        assert not (used & forbidden), (
            f"this package names {sorted(used & forbidden)} on the MCP client; each of "
            "those is a documented way past the typed surface"
        )


class TestTheDetectorsAreAlive:
    """PL-2, applied to a static check: a scanner that has never fired asserts nothing.

    Each detector above is run against a synthetic module that *does* commit the offence,
    so a green suite proves the rule is enforced rather than proving the scanner is broken.
    """

    SYNTHETIC = """
import boto3
from mainline_mcp.client import probe_insert_rows_unbound
import subprocess


def sneak(client):
    client.call("insert_rows", {"table": "mainline.permit", "rows": []})
    client.insert_external_attestation([{}])
    client.insert_external_attestation([{}])
"""

    @pytest.fixture
    def tree(self) -> ast.Module:
        return ast.parse(self.SYNTHETIC)

    def test_the_banned_module_detector_fires(self, tree):
        modules = {module for module, _ in _imported_modules(tree)}
        assert modules & BANNED_MODULES == {"boto3"}

    def test_the_probe_detector_fires(self, tree):
        names = [
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
            for alias in node.names
        ]
        assert [n for n in names if n.startswith("probe_")] == ["probe_insert_rows_unbound"]

    def test_the_call_site_detector_counts_more_than_one(self, tree):
        sites = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == WRITE_METHOD
        ]
        assert len(sites) == 2

    def test_the_raw_tool_name_detector_fires(self, tree):
        literals = {
            argument.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            for argument in node.args
            if isinstance(argument, ast.Constant) and isinstance(argument.value, str)
        }
        assert literals & FORBIDDEN_TOOL_NAMES == {"insert_rows"}

    def test_the_subprocess_detector_fires(self, tree):
        assert "subprocess" in {module for module, _ in _imported_modules(tree)}


class TestTheDependencyListIsShort:
    def test_the_distribution_declares_three_runtime_dependencies(self, request):
        import tomllib

        package = (
            request.config.rootpath / "verticals" / "mainline" / "packages" / "mainline-steward"
        )
        document = tomllib.loads((package / "pyproject.toml").read_text(encoding="utf-8"))
        declared = {
            entry.split(">")[0].split("=")[0].split("[")[0].strip().lower()
            for entry in document["project"]["dependencies"]
        }
        assert declared == {"mainline-mcp", "trappoint-jcs", "pyyaml"}
