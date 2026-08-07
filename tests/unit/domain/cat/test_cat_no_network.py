# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Path A must be independently runnable and independently auditable.

Worker W5 owns the domain-wide AST boundary test that keeps a model SDK out of
``mainline_domain`` (``tests/unit/domain/boundaries/test_no_model_in_domain.py``).
This file asserts the *narrower and stricter* property that CATSEAL alone has to
satisfy: the CAT extractor reaches nothing outside the process at all — no
network, no clock, no randomness, no environment.

Why stricter, and why here rather than folded into W5's test.  ``mainline_domain``
as a whole may legitimately open a socket one day (a psycopg arm runner lives
behind ``PrefixArmRunner``, and W7 ships one).  ``mainline_domain.cat`` may not.
Its output is an identity — a ``cat_key`` a blame edge attaches through — and an
identity that could vary with a clock, a random seed, an environment variable or
a remote service is not an identity at all.  It could not be reproduced in three
years by someone handed the same clause and the same commit.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Final

import mainline_domain.cat as cat_package
import pytest

_PACKAGE_ROOT: Final[Path] = Path(cat_package.__file__).resolve().parent

_FORBIDDEN_MODULES: Final[frozenset[str]] = frozenset(
    {
        # model SDKs (principle P7, decision D1)
        "boto3",
        "botocore",
        "anthropic",
        "strands",
        "langchain",
        "openai",
        # network
        "socket",
        "ssl",
        "http",
        "urllib",
        "urllib3",
        "requests",
        "httpx",
        "aiohttp",
        "ftplib",
        "smtplib",
        "telnetlib",
        "xmlrpc",
        "asyncio",
        # non-determinism
        "random",
        "secrets",
        "time",
        "datetime",
        "uuid",
        "tempfile",
        "subprocess",
        "multiprocessing",
        "threading",
    }
)

_FORBIDDEN_NAMES: Final[frozenset[str]] = frozenset({"getenv", "environ", "urandom", "monotonic"})


def _modules() -> list[Path]:
    found = sorted(_PACKAGE_ROOT.rglob("*.py"))
    assert found, f"no modules found under {_PACKAGE_ROOT}"
    return found


def _imported_roots(tree: ast.AST) -> set[str]:
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".", 1)[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # relative import inside mainline_domain
                continue
            if node.module:
                roots.add(node.module.split(".", 1)[0])
    return roots


@pytest.mark.parametrize("path", _modules(), ids=lambda p: p.name)
def test_module_imports_nothing_forbidden(path: Path) -> None:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    offending = sorted(_imported_roots(tree) & _FORBIDDEN_MODULES)
    assert offending == [], (
        f"{path.name} imports {offending}. mainline_domain.cat produces an identity that a "
        f"blame edge attaches through; an identity that can vary with a clock, a seed, an "
        f"environment variable or a remote service cannot be reproduced under oath."
    )


@pytest.mark.parametrize("path", _modules(), ids=lambda p: p.name)
def test_module_reads_no_environment_and_no_entropy(path: Path) -> None:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    hits: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in _FORBIDDEN_NAMES:
            hits.add(node.attr)
        elif isinstance(node, ast.Name) and node.id in _FORBIDDEN_NAMES:
            hits.add(node.id)
    assert not hits, f"{path.name} touches {sorted(hits)}"


def test_the_boundary_test_can_actually_fail() -> None:
    """A guard that has never rejected anything is not a guard (PL-2).

    The detector is run against synthetic sources here rather than by editing a
    real module, so the assertion covers the checking logic itself.
    """
    forbidden = ast.parse("import boto3\nfrom urllib import request\n")
    assert _imported_roots(forbidden) & _FORBIDDEN_MODULES == {"boto3", "urllib"}

    clean = ast.parse("import re\nfrom decimal import Decimal\nfrom ..contracts import CAT\n")
    assert not _imported_roots(clean) & _FORBIDDEN_MODULES


def test_the_only_optional_import_is_the_declared_w2_seam() -> None:
    """``quantity_bridge`` imports ``importlib`` on purpose; nothing else may.

    The seam to worker W2 is a deliberate, documented, lazy lookup of
    ``mainline_domain.quantity``.  Pinning it here means a second dynamic import
    appearing anywhere in the package is a test failure rather than a discovery.
    """
    dynamic: dict[str, set[str]] = {}
    for path in _modules():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        roots = _imported_roots(tree)
        if "importlib" in roots:
            dynamic[path.name] = roots
    assert set(dynamic) == {"quantity_bridge.py"}, dynamic
