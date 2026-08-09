# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""PL-3 and decision D12: no module in this package can reach a model or a network.

Walked as an AST rather than asserted in a docstring.  The adversarial-paraphrase
class is the one place a harness like this would naturally reach for a model, and
the whole point of the committed cassettes is that it does not.  An import added
in six months would otherwise be caught by an AWS bill.

Also asserted: the run itself opens no socket and reads no environment variable.
A measurement whose value depended on ``AWS_REGION`` being set would be a
measurement nobody else could reproduce.
"""

from __future__ import annotations

import ast
import pathlib

import mainline_mutation
import pytest

PACKAGE = pathlib.Path(mainline_mutation.__file__).parent
MODULES = sorted(PACKAGE.rglob("*.py"))

FORBIDDEN_ROOTS = frozenset(
    {
        "boto3",
        "botocore",
        "anthropic",
        "strands",
        "langchain",
        "openai",
        "requests",
        "httpx",
        "urllib",
        "socket",
        "http",
        "aiohttp",
    }
)

#: `statsmodels` and `scipy` are forbidden for a different reason: the Wilson
#: interval is published, and a bound whose derivation nobody in the room can
#: check by hand does not survive cross-examination.
FORBIDDEN_STATS = frozenset({"statsmodels", "scipy", "sklearn"})


def _imports(path: pathlib.Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".")[0])
    return roots


@pytest.mark.parametrize("path", MODULES, ids=lambda p: p.name)
def test_no_module_imports_a_model_sdk_or_a_network_client(path):
    reached = _imports(path) & FORBIDDEN_ROOTS
    assert not reached, (
        f"{path.name} imports {sorted(reached)}. PL-3: AWS credentials are not valid and "
        "decision D12 keeps the live model path out of CI. The adversarial paraphrases come "
        "from committed cassettes and nothing here calls a model"
    )


@pytest.mark.parametrize("path", MODULES, ids=lambda p: p.name)
def test_no_module_imports_a_statistics_package(path):
    reached = _imports(path) & FORBIDDEN_STATS
    assert not reached, (
        f"{path.name} imports {sorted(reached)}. The Wilson interval is implemented directly, "
        "in six lines, so that an opposing expert can check the published bound with a "
        "calculator"
    )


@pytest.mark.parametrize("path", MODULES, ids=lambda p: p.name)
def test_no_module_reads_an_environment_variable(path):
    """A figure that depended on an env var would not be reproducible by a stranger."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in ("getenv", "environ"):
            value = node.value
            if isinstance(value, ast.Name) and value.id == "os":
                pytest.fail(f"{path.name} reads the environment via os.{node.attr}")


def test_the_cassettes_declare_no_model():
    from mainline_mutation.paraphrase import provenance_label, provenance_statement

    assert provenance_label() == "hand-authored"
    statement = provenance_statement()
    assert "HAND-AUTHORED" in statement
    assert "No model was called" in statement


def test_the_artefact_carries_the_provenance_statement():
    from mainline_mutation import build_report, run

    report = build_report(run(seed=0))
    assert "HAND-AUTHORED" in report["statements"]["paraphrase_provenance"]
    assert report["statements"]["path_b_absent"].startswith("PATH B WAS NOT CONSULTED")
    assert "NEVER A GATE" in report["statements"]["standing_metric_never_a_gate"]
