# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Path A must be independently runnable and independently auditable.

Decision D1 and principle P7: no component that can decide a state transition may
reach a model, and the lattice decides one.  A grep would be a convention; an AST
walk is a check, so this module parses every source file under
``mainline_domain/lattice/`` and reads its import statements.

The forbidden set is deliberately broader than "a model SDK".  It also excludes
the *resolution* layer and the oracle package, because a lattice that imported
either would stop being separately auditable: an expert asked to re-derive a
verdict from two tuples and a signed registry would have to reason about what a
model returned, which is the whole thing this design refuses.
"""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

import mainline_domain.lattice as lattice_pkg
import pytest

_PACKAGE = Path(lattice_pkg.__file__).resolve().parent
_MODULES = sorted(_PACKAGE.glob("*.py"))

#: Distributions and modules that would let a model, a network or a clock into
#: the decision.  ``resolution``/``oracle`` are the domain-internal half.
_FORBIDDEN_ROOTS = frozenset(
    {
        "boto3",
        "botocore",
        "anthropic",
        "strands",
        "langchain",
        "openai",
        "httpx",
        "requests",
        "urllib",
        "socket",
        "http",
        "asyncio",
        "random",
        "time",
        "datetime",
        "os",
        "subprocess",
        "mainline_delta_oracle",
    }
)

#: Sibling subpackages of ``mainline_domain`` this one may not reach into.
#: ``mainline_domain.resolution`` does not exist yet — it is worker W5's — and the
#: assertion is written now, before it lands, precisely so that the coupling can
#: never be introduced by accident later.
_FORBIDDEN_SIBLINGS = frozenset({"resolution", "oracle", "delta_oracle"})


def test_there_is_something_to_check() -> None:
    assert _MODULES, f"no modules found under {_PACKAGE}"
    assert {p.name for p in _MODULES} >= {
        "__init__.py",
        "decide.py",
        "errors.py",
        "order.py",
        "rules.py",
        "version.py",
        "witness.py",
    }


def _imported_roots(tree: ast.AST) -> set[str]:
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # a relative import — recorded separately below
                continue
            if node.module:
                roots.add(node.module.split(".")[0])
    return roots


def _relative_targets(tree: ast.AST) -> set[str]:
    targets: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level:
            if node.module:
                targets.add(node.module.split(".")[0])
            targets.update(alias.name.split(".")[0] for alias in node.names)
    return targets


@pytest.mark.parametrize("module", _MODULES, ids=lambda p: p.name)
def test_no_module_imports_anything_that_could_reach_a_model(module: Path) -> None:
    tree = ast.parse(module.read_text(encoding="utf-8"), filename=str(module))
    offending = _imported_roots(tree) & _FORBIDDEN_ROOTS
    assert not offending, (
        f"{module.name} imports {sorted(offending)}. Path A decides a state transition "
        f"(P7) and must be re-derivable from two tuples and a signed registry"
    )


@pytest.mark.parametrize("module", _MODULES, ids=lambda p: p.name)
def test_no_module_reaches_into_the_resolution_or_oracle_packages(module: Path) -> None:
    tree = ast.parse(module.read_text(encoding="utf-8"), filename=str(module))
    offending = _relative_targets(tree) & _FORBIDDEN_SIBLINGS
    assert not offending, (
        f"{module.name} imports mainline_domain.{sorted(offending)[0]}; the lattice must be "
        f"independently runnable and independently auditable"
    )


def test_the_oracle_package_is_not_even_installed_for_this_suite() -> None:
    """A soft statement, not a hard one, and it says which.

    ``mainline-delta-oracle`` is a separate distribution (decision D1).  If it is
    present in the environment the AST checks above still hold, and this test
    reports the fact rather than failing — a developer with both packages
    installed is not doing anything wrong, but a run in which the oracle is
    absent is a stronger proof that the lattice never needed it.
    """
    if importlib.util.find_spec("mainline_delta_oracle") is not None:  # pragma: no cover
        pytest.skip(
            "mainline-delta-oracle is installed in this environment; the AST checks still "
            "prove the lattice does not import it, but the stronger 'it is not even here' "
            "claim is not available from this run"
        )
    assert importlib.util.find_spec("mainline_delta_oracle") is None


def test_a_verdict_is_reproducible_byte_for_byte_across_two_runs() -> None:
    """Determinism, asserted rather than assumed.

    Nothing here reads a clock or a PRNG, but the point of the claim is that an
    opposing expert gets the same answer, so it is checked rather than argued.
    """
    from _lattice_fixtures import AS_OF, cat, empty_registry, qty
    from mainline_domain.lattice import explain, rule_catalogue_fingerprint

    reference = cat(
        deontic="MUST",
        parameter="max_operating_pressure",
        comparator="<=",
        value=qty("1750", "kPa"),
        exceptions=(),
        verification=("hold_point",),
        coverage_quantifier="all",
    )
    descendant = cat(
        deontic="SHOULD",
        parameter="max_operating_pressure",
        comparator="<",
        value=qty("2100", "kPa"),
        exceptions=("where practicable",),
        verification=(),
        coverage_quantifier="selected",
    )

    first = explain(reference, descendant, empty_registry(), AS_OF)
    second = explain(reference, descendant, empty_registry(), AS_OF)

    assert first.verdict == second.verdict
    assert first.findings == second.findings
    assert first.minimal == second.minimal
    assert first.repair == second.repair
    assert rule_catalogue_fingerprint() == rule_catalogue_fingerprint()
    assert len(rule_catalogue_fingerprint()) == 32
