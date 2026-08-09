# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The dependency floor, asserted by walking the AST rather than by promising.

*"A stranger needs nothing but Python and ``cryptography``"* is the claim on which the
whole custody argument rests: if a verifier needs a MAINLINE package, then verifying our
log requires trusting our code, and an opposing expert is entitled to say so.

This file makes the claim mechanical.

* **Every top-level import name** in every shipped module must be in the standard library,
  or ``cryptography``, or this package itself. Nothing else.
* **``trappoint_ledger`` and ``trappoint_jcs`` are not imported at all**, at any level.
  RFC 6962 is reimplemented on ``hashlib`` and ``canon_v1`` is vendored byte-for-byte,
  precisely so that neither name can appear in an import statement here. (Both appear in
  *prose*, which is why this test reads the syntax tree and not the text.)
* **No dynamic-import escape hatch.** ``__import__``, ``importlib.import_module``, ``eval``
  and ``exec`` are refused outright: a floor that a computed module name can step over is
  a floor in name only, and an AST walk cannot see through one.
"""

from __future__ import annotations

import ast
import hashlib
import sys
import tomllib
from pathlib import Path

import pytest

_PACKAGE_ROOT = Path(__file__).resolve().parents[1]
_SRC = _PACKAGE_ROOT / "src"
if str(_SRC) not in sys.path:  # pragma: no cover - import bootstrap
    sys.path.insert(0, str(_SRC))

import trappoint_verify  # noqa: E402

ALLOWED_THIRD_PARTY = frozenset({"cryptography"})
FORBIDDEN_IMPORTS = frozenset({"trappoint_ledger", "trappoint_jcs", "trappoint_core"})
FORBIDDEN_CALLS = frozenset({"__import__", "eval", "exec", "import_module"})


def shipped_modules() -> list[Path]:
    """Every ``.py`` file that goes into the wheel, vendored code included."""
    return sorted(path for path in _SRC.rglob("*.py") if "__pycache__" not in path.parts)


def top_level_imports(tree: ast.AST) -> set[str]:
    """The set of *absolute* top-level module names imported anywhere in *tree*."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module.split(".")[0])
    return names


def test_there_is_something_to_check():
    """A test that walks an empty file list is a test that asserts nothing."""
    modules = shipped_modules()
    assert len(modules) >= 6, modules
    assert any(path.name == "canon_v1.py" for path in modules)


@pytest.mark.parametrize("path", shipped_modules(), ids=lambda p: p.name)
def test_module_imports_only_the_standard_library_and_cryptography(path: Path):
    """The floor itself."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imported = top_level_imports(tree)
    allowed = set(sys.stdlib_module_names) | ALLOWED_THIRD_PARTY | {"trappoint_verify"}
    offending = sorted(imported - allowed)
    assert not offending, (
        f"{path.relative_to(_PACKAGE_ROOT)} imports {offending}, which is outside the "
        "dependency floor of `cryptography` plus the standard library"
    )


@pytest.mark.parametrize("path", shipped_modules(), ids=lambda p: p.name)
def test_no_mainline_package_is_imported(path: Path):
    """Zero MAINLINE dependencies — at any import level, relative or absolute."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(
                alias.name.split(".")[0]
                for alias in node.names
                if alias.name.split(".")[0] in FORBIDDEN_IMPORTS
            )
        elif isinstance(node, ast.ImportFrom) and node.module:
            head = node.module.split(".")[0]
            if head in FORBIDDEN_IMPORTS:
                found.add(head)
    assert not found, (
        f"{path.relative_to(_PACKAGE_ROOT)} imports {sorted(found)}. The verifier's value "
        "is that it shares no code with the log it is checking."
    )


@pytest.mark.parametrize("path", shipped_modules(), ids=lambda p: p.name)
def test_no_dynamic_import_escape_hatch(path: Path):
    """``__import__``/``importlib``/``eval``/``exec`` would make the AST walk above blind."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    offending: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        function = node.func
        if isinstance(function, ast.Name) and function.id in FORBIDDEN_CALLS:
            offending.append(function.id)
        elif isinstance(function, ast.Attribute) and function.attr in FORBIDDEN_CALLS:
            offending.append(function.attr)
    assert not offending, (
        f"{path.relative_to(_PACKAGE_ROOT)} calls {sorted(set(offending))}; every import in "
        "this package is a literal so that the floor is checkable"
    )


def test_the_declared_dependencies_are_exactly_the_floor():
    """``pyproject.toml`` and the AST must agree, or one of them is decoration."""
    manifest = tomllib.loads((_PACKAGE_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    declared = manifest["project"]["dependencies"]
    assert len(declared) == 1, declared
    assert declared[0].startswith("cryptography>="), declared
    assert manifest["project"]["optional-dependencies"]["beacon"] == []


def test_version_matches_pyproject():
    """A report naming a version the wheel does not have is a report nobody can reproduce."""
    manifest = tomllib.loads((_PACKAGE_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert trappoint_verify.__version__ == manifest["project"]["version"]


def _repo_root() -> Path | None:
    for candidate in [_PACKAGE_ROOT, *_PACKAGE_ROOT.parents]:
        if (candidate / "spec" / "custody" / "canon-registry.yaml").is_file():
            return candidate
    return None


def test_the_vendored_canonicaliser_is_byte_identical_to_its_source():
    """The one-dependency claim dies quietly the moment the copy drifts.

    ``scripts/custody/check_vendored_canon.py`` is the repository-wide gate; this is the
    same assertion inside the package's own suite, so a fork that runs only these tests
    still finds out.
    """
    root = _repo_root()
    if root is None:  # pragma: no cover - only when the wheel is tested outside the repo
        pytest.skip("not running inside the MAINLINE checkout; the source copy is unreachable")
    original = root / "packages/trappoint-jcs/src/trappoint_jcs/canon_v1.py"
    vendored = _SRC / "trappoint_verify/vendor/canon_v1.py"
    normalise = lambda path: hashlib.sha256(  # noqa: E731 - one expression, used twice
        path.read_bytes().replace(b"\r\n", b"\n")
    ).hexdigest()
    assert normalise(vendored) == normalise(original), (
        "the vendored canonicaliser has drifted from packages/trappoint-jcs; the verifier "
        "would disagree with the ledger about what bytes were hashed"
    )
