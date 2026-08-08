# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The integration suites must SKIP without a credential — never pass, never error.

This is the guard on the guard. The two suites in ``tests/integration/mcp`` make claims
about what a stranger's agent can and cannot reach; if either of them could go green on a
machine with no credential, the claim would be "unreachable things were unreachable
because we never tried", which is worse than no claim at all.

The check is structural — a module-level ``pytestmark`` carrying a ``skipif`` with a
non-empty reason — because that is the only form that covers *every* test in the file
including ones added later. A per-test decorator can be forgotten on the next test; a
module-level mark cannot.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_INTEGRATION = _REPO_ROOT / "tests" / "integration" / "mcp"
SUITES = ("test_audit_surface.py", "test_negative_reachability.py")


def _module(name: str) -> ast.Module:
    path = _INTEGRATION / name
    assert path.is_file(), f"{path} is missing"
    return ast.parse(path.read_text(encoding="utf-8"))


def _pytestmark(tree: ast.Module) -> ast.expr | None:
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "pytestmark":
                    return node.value
    return None


@pytest.mark.parametrize("suite", SUITES)
class TestSkipDiscipline:
    def test_the_suite_carries_a_module_level_pytestmark(self, suite):
        assert _pytestmark(_module(suite)) is not None, (
            f"{suite} has no module-level pytestmark, so a test added tomorrow could run "
            "without a credential and pass by never trying"
        )

    def test_the_mark_is_a_skipif_with_a_reason(self, suite):
        source = (_INTEGRATION / suite).read_text(encoding="utf-8")
        assert "pytest.mark.skipif" in source
        assert "reason=" in source
        assert "MAINLINE_MCP_API_KEY" in source

    def test_the_reason_says_it_skips_rather_than_passes(self, suite):
        source = (_INTEGRATION / suite).read_text(encoding="utf-8")
        assert "SKIPS rather than passes" in source, (
            f"{suite}'s skip reason must say out loud that it skips rather than passes; "
            "an operator reading a wall of SKIPs deserves to know it is deliberate"
        )

    def test_every_test_lives_under_the_module_mark(self, suite):
        # Module-level pytestmark applies to everything in the file, so the only way to
        # escape it would be a conditional import or an exec. Assert there is neither.
        source = (_INTEGRATION / suite).read_text(encoding="utf-8")
        assert "exec(" not in source
        assert "importlib" not in source

    def test_the_suite_requires_a_cluster_marker(self, suite):
        source = (_INTEGRATION / suite).read_text(encoding="utf-8")
        assert "pytest.mark.requires_cluster" in source
