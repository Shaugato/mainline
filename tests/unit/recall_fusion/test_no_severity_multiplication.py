# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""A source-level proof that severity never scales a score anywhere in the admission path.

The behavioural tests in ``test_sga.py`` show that today's code does not inflate a score by
severity. This one shows that no code in the package *could*, by walking the abstract syntax
tree of every module in the fusion package and the rerank package and refusing any
multiplicative expression with an operand that mentions severity.

Why a syntax check rather than more behaviour: score-boosting by severity is the single most
tempting shortcut in this design. It makes every recall metric improve at once, it is one
character of diff, and it is invisible in any output — the number simply gets larger, and the
system starts claiming a resemblance it never measured. A behavioural test catches it only
where a fixture happens to look; a syntax check catches it in a branch nobody exercised, in a
helper somebody added at midnight.

The rule is deliberately blunt: no ``*``, ``/``, ``**`` or ``@`` may have an operand whose
source text mentions severity. Legitimate uses of severity — looking up a threshold, ordering
a queue, recording a value — do not need one, and a future change that genuinely does can
argue for the exception in review rather than acquire it silently.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from fusion_paths import FUSION_PACKAGE, RERANK_PACKAGE

MULTIPLICATIVE = (ast.Mult, ast.Div, ast.FloorDiv, ast.Pow, ast.MatMult)


def _modules() -> list[Path]:
    found = sorted(FUSION_PACKAGE.glob("*.py")) + sorted(RERANK_PACKAGE.glob("*.py"))
    assert found, "no modules found: the scan must not pass by scanning nothing"
    return found


def _mentions_severity(node: ast.AST) -> bool:
    return "severity" in ast.unparse(node).lower()


def _violations(source: str, path: Path) -> list[str]:
    tree = ast.parse(source, filename=str(path))
    out: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.BinOp) and isinstance(node.op, MULTIPLICATIVE):
            operands = (node.left, node.right)
        elif isinstance(node, ast.AugAssign) and isinstance(node.op, MULTIPLICATIVE):
            operands = (node.target, node.value)
        else:
            continue
        if any(_mentions_severity(operand) for operand in operands):
            out.append(f"{path.name}:{node.lineno}: {ast.unparse(node)}")
    return out


@pytest.mark.frozen
def test_no_module_multiplies_or_divides_by_severity() -> None:
    violations: list[str] = []
    for path in _modules():
        violations.extend(_violations(path.read_text(encoding="utf-8"), path))
    assert not violations, (
        "severity appears in a multiplicative expression:\n  "
        + "\n  ".join(violations)
        + "\n\nSeverity LOWERS the evidence bar (it selects tau); it never inflates a score. "
        "A score scaled by severity claims a resemblance the system never measured, and "
        "every downstream number - including the p_relevant a supervisor is shown and a "
        "court is quoted - inherits that claim."
    )


def test_the_scanner_would_actually_catch_it() -> None:
    """PL-2: a check that has never been red asserts nothing. Here is it being red."""
    guilty = "boosted = p_relevant * severity\n"
    assert _violations(guilty, Path("guilty.py"))

    also_guilty = "score **= float(candidate.severity)\n"
    assert _violations(also_guilty, Path("guilty.py"))

    innocent = "threshold = tau_table.tau_for(candidate.severity)\nrank = -weight * 2.0\n"
    assert not _violations(innocent, Path("innocent.py"))


def test_ordering_by_severity_is_not_flagged_because_it_scales_nothing() -> None:
    """``-float(candidate.severity)`` in a sort key is a queue order, not a score change."""
    key = "key = (-float(candidate.severity), -check.p_relevant, float(candidate.rank))\n"
    assert not _violations(key, Path("sort_key.py"))
