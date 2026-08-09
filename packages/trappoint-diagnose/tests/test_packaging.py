# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Claims this distribution makes about itself, asserted so that deleting them shows.

Three of them, and each is load-bearing for something said elsewhere:

* **Zero required runtime dependencies.** The README and ``pyproject.toml`` both say this
  package decides what a refusal means with nothing between it and the standard library.
  Without this test, that becomes true until someone needs a convenience.
* **No blanket-retry helper.** ``.importlinter`` contract 4 forbids ``tenacity``,
  ``backoff`` and ``retrying`` repo-wide, because a refusal is attempted exactly once,
  ever. A diagnoser that retried would write duplicate diagnoses for one attempted
  history.
* **No driver on the import path.** A verifier must be able to import this package to
  check a payload without pulling a binary wheel, so the driver may only be imported
  inside a function.
"""

from __future__ import annotations

import ast
import sys
import tomllib
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
SOURCE = PACKAGE / "src" / "trappoint_diagnose"
FORBIDDEN_RETRY = {"tenacity", "backoff", "retrying"}
DRIVERS = {"psycopg", "psycopg2", "asyncpg", "sqlalchemy"}


def manifest() -> dict:
    with (PACKAGE / "pyproject.toml").open("rb") as handle:
        return tomllib.load(handle)


def test_the_runtime_dependency_list_is_empty():
    assert manifest()["project"]["dependencies"] == []


def test_the_driver_is_an_optional_extra_and_nothing_else_is():
    extras = manifest()["project"]["optional-dependencies"]
    assert set(extras) == {"pg"}
    assert all("psycopg" in requirement for requirement in extras["pg"])


def test_no_module_imports_a_blanket_retry_helper():
    for path in sorted(SOURCE.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = {alias.name.split(".")[0] for alias in node.names}
            elif isinstance(node, ast.ImportFrom):
                names = {(node.module or "").split(".")[0]}
            else:
                continue
            offending = names & FORBIDDEN_RETRY
            assert not offending, f"{path.name} imports {offending}"


def test_a_driver_is_never_imported_at_module_scope():
    for path in sorted(SOURCE.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in tree.body:
            if isinstance(node, ast.Import):
                names = {alias.name.split(".")[0] for alias in node.names}
            elif isinstance(node, ast.ImportFrom):
                names = {(node.module or "").split(".")[0]}
            else:
                continue
            assert not (names & DRIVERS), f"{path.name} imports a driver at module scope"


def test_importing_the_package_pulls_in_no_third_party_module():
    # Everything `trappoint_diagnose` reached for on the way in must be either the
    # standard library or itself. A verifier's machine has nothing else on it.
    before = set(sys.modules)
    import trappoint_diagnose  # noqa: F401

    added = set(sys.modules) - before
    stdlib = set(sys.stdlib_module_names)
    for name in added:
        root = name.split(".")[0]
        assert root in stdlib or root.startswith(("trappoint_diagnose", "_")), (
            f"importing trappoint_diagnose pulled in {root}"
        )


def test_every_source_file_carries_a_reuse_header():
    for path in sorted(SOURCE.rglob("*.py")):
        head = path.read_text(encoding="utf-8")[:200]
        assert "SPDX-FileCopyrightText" in head, path.name
        assert "SPDX-License-Identifier: Apache-2.0" in head, path.name


def test_the_typing_marker_ships_with_its_licence_sidecar():
    assert (SOURCE / "py.typed").is_file()
    assert (SOURCE / "py.typed.license").is_file()
