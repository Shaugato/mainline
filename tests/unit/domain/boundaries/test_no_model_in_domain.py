# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""E3, for the algorithms domain: no model code path inside ``mainline_domain``.

ARCHITECTURE.md §8.2 draws the deterministic/LLM boundary with four independent
enforcements — no IAM, no network route, no code path, no prompt path.  This file
is the **code path** half, scoped to the one distribution that contains the delta
lattice, and it is a test rather than a line in ``.importlinter`` for two
reasons: ``root_packages`` can only name packages that are importable at lint
time, and the check here is over *files on disk*, so it covers a module that was
added but not yet installed, one that fails to import, and one that only imports
its SDK inside a function.

The claim is exact, and worth stating in the form it would be put under
cross-examination:

    *No module of the distribution that decides whether a clause edit is a
    weakening imports a model client, in any form, at any depth, lazily or
    otherwise.*

The model path lives in ``mainline-delta-oracle``, a different distribution, and
the final test in this file asserts the arrow points that way — that the oracle
really does reach agentkit — so that "the domain imports no model SDK" cannot be
satisfied by there being no model anywhere.

**This file imports nothing from the packages it checks.**  It reads their source
off disk and parses it, so it runs identically whether or not either
distribution is installed, and it cannot be defeated by an import-time guard.
"""

from __future__ import annotations

import ast
import tomllib
from pathlib import Path
from typing import Final

import pytest

_REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[4]
_DOMAIN_DIST: Final[Path] = _REPO_ROOT / "verticals" / "mainline" / "packages" / "mainline-domain"
_DOMAIN_SRC: Final[Path] = _DOMAIN_DIST / "src" / "mainline_domain"
_ORACLE_SRC: Final[Path] = (
    _REPO_ROOT
    / "verticals"
    / "mainline"
    / "packages"
    / "mainline-delta-oracle"
    / "src"
    / "mainline_delta_oracle"
)

#: Import roots that mean "this module can reach a model".
_FORBIDDEN_ROOTS: Final[frozenset[str]] = frozenset(
    {
        "boto3",
        "botocore",
        "anthropic",
        "strands",
        "strands_agents",
        "strands_tools",
        "openai",
        "langchain",
        "langchain_core",
        "langgraph",
        "llama_index",
        "cohere",
        "transformers",
        "sentence_transformers",
        "torch",
        # The one distribution in this repository that CAN reach a model. It is
        # not a model SDK, and it is forbidden here for exactly the same reason:
        # an indirect reach is the shape this actually takes in practice.
        "mainline_agentkit",
        "mainline_delta_oracle",
    }
)

#: Any imported module whose dotted name contains one of these substrings is a
#: model path whatever it is called. Catches a vendored client, a private wrapper
#: and a plugin package the list above has never heard of.
_FORBIDDEN_SUBSTRINGS: Final[tuple[str, ...]] = ("bedrock", "sagemaker", "invoke_model")


def _domain_modules() -> list[Path]:
    found = sorted(_DOMAIN_SRC.rglob("*.py"))
    assert found, (
        f"no modules found under {_DOMAIN_SRC}; this test asserts a property of a "
        f"package that must exist, so an empty walk is a failure, not a pass"
    )
    return found


def _imported_names(tree: ast.AST) -> set[str]:
    """Every absolute module name imported anywhere in the tree, at any depth.

    Function-level imports are included deliberately: ``PLC0415`` is disabled
    repo-wide for optional heavy dependencies, so "the SDK is only imported
    inside the one function that needs it" is a shape that exists in this
    codebase and would otherwise slip past.
    """
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # relative: inside the package being checked
                continue
            if node.module:
                names.add(node.module)
    return names


def violations(source: str, filename: str = "<test>") -> list[str]:
    """Every forbidden import in one module's source, sorted.

    Exposed rather than inlined so that
    :func:`test_the_detector_rejects_what_it_claims_to_reject` can run it against
    synthetic sources: a guard that has never rejected anything is not a guard.
    """
    tree = ast.parse(source, filename=filename)
    found: set[str] = set()
    for name in _imported_names(tree):
        root = name.split(".", 1)[0]
        lowered = name.lower()
        if root in _FORBIDDEN_ROOTS or any(part in lowered for part in _FORBIDDEN_SUBSTRINGS):
            found.add(name)
    return sorted(found)


@pytest.mark.parametrize("path", _domain_modules(), ids=lambda p: p.name)
def test_no_domain_module_imports_a_model_client(path: Path) -> None:
    """The whole of E3 for this distribution, one module at a time."""
    offending = violations(path.read_text(encoding="utf-8"), filename=str(path))
    assert offending == [], (
        f"{path.relative_to(_REPO_ROOT)} imports {offending}. mainline_domain contains "
        f"the delta lattice, which decides a state transition, and principle P7 forbids "
        f"any component that decides a state transition from reaching a model. Path B "
        f"lives in mainline-delta-oracle and enters through the OracleVerdict dataclass."
    )


def test_the_detector_rejects_what_it_claims_to_reject() -> None:
    """PL-2 applied to the guard itself, in every evasion it is meant to catch."""
    assert violations("import boto3") == ["boto3"]
    assert violations("from botocore.exceptions import ClientError") == ["botocore.exceptions"]
    assert violations("def f():\n    import boto3\n    return boto3") == ["boto3"]
    assert violations("import acme.bedrock_helper as helper") == ["acme.bedrock_helper"]
    assert violations("from mainline_agentkit import quarantined_call") == ["mainline_agentkit"]
    assert violations("if TYPE_CHECKING:\n    import anthropic") == ["anthropic"]


def test_the_detector_passes_what_it_must_not_reject() -> None:
    """The converse: it must not fire on the domain's real imports, or it gets deleted."""
    clean = (
        "from __future__ import annotations\n"
        "import hashlib\n"
        "from decimal import Decimal\n"
        "import numpy as np\n"
        "from ..contracts import ControlDelta\n"
        "from .table import RESOLUTION\n"
        '"""A docstring mentioning boto3 and bedrock, which are words, not imports."""\n'
    )
    assert violations(clean) == []


def test_the_domain_distribution_declares_no_model_dependency() -> None:
    """The second surface: what the wheel would install, not what the source imports.

    An import graph is clean until someone adds a dependency and a helper that
    uses it in the same commit. This reads the declared dependency list, which is
    the thing a reviewer skims and an SBOM diff sees.
    """
    manifest = tomllib.loads((_DOMAIN_DIST / "pyproject.toml").read_text(encoding="utf-8"))
    project = manifest["project"]
    declared = list(project.get("dependencies", []))
    for extra in project.get("optional-dependencies", {}).values():
        declared.extend(extra)
    offending = sorted(
        requirement
        for requirement in declared
        if any(root.replace("_", "-") in requirement.lower() for root in _FORBIDDEN_ROOTS)
    )
    assert offending == [], (
        f"mainline-domain declares {offending}. The separation of Path A and Path B is a "
        f"DISTRIBUTION boundary; a dependency edge here makes it a convention."
    )


def test_path_b_really_does_reach_the_model_surface() -> None:
    """The arrow points somewhere, or this whole file proves nothing.

    "The domain imports no model SDK" is trivially true of a repository with no
    model in it. This asserts the other half: ``mainline-delta-oracle`` exists, it
    imports agentkit, and it imports the domain — so the separation being tested
    is a real one between two things that both exist.
    """
    assert _ORACLE_SRC.is_dir(), f"Path B is missing at {_ORACLE_SRC}"
    imports: set[str] = set()
    for path in sorted(_ORACLE_SRC.rglob("*.py")):
        imports |= _imported_names(ast.parse(path.read_text(encoding="utf-8"), filename=str(path)))
    roots = {name.split(".", 1)[0] for name in imports}
    assert "mainline_agentkit" in roots, "Path B does not reach the model surface at all"
    assert "mainline_domain" in roots, "Path B does not speak the domain's contracts"
