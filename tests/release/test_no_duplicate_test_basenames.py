# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Two test modules may not want the same name, because pytest can only give it to one.

Under pytest's default ``prepend`` import mode a test file that lives in a directory with no
``__init__.py`` is imported as a **top-level module named after its basename**, and its
directory is inserted at ``sys.path[0]``. Two such files with the same basename are two
claims on one entry in ``sys.modules``. The second one collected does not shadow the first
quietly — collection stops::

    import file mismatch:
    imported module 'test_red_first' has this __file__ attribute:
      tests/e2e/mutation/test_red_first.py
    which is not the same as the test file we want to collect:
      tests/unit/domain/lattice/test_red_first.py

and a sibling helper is worse, because it fails as a wrong import rather than as a name
clash — this is the shape it took here on 2026-08-10::

    ImportError: cannot import name 'PREREQ_DIR' from '_support'
                 (tests/integration/recall_index/_support.py)

``tests/integration/recall_schema/conftest.py`` asked for *its* ``_support`` and was handed
``recall_index``'s, because that directory reached ``sys.path`` first.

**Both obvious levers were measured on this tree and both are worse than renaming.**

* ``--import-mode=importlib`` → **34** collection errors, up from 3, because a dozen conftests
  do sibling imports (``from _support import …``) that depend on the ``sys.path`` insertion
  ``prepend`` performs.
* adding ``__init__.py`` to the colliding directories → ``ImportPathMismatchError:
  ('tests.conftest', …mainline-boundary/tests/conftest.py, …trappoint-sql/tests/conftest.py)``.
  Both packages' test directories become the module ``tests``; the collision moves rather
  than clears.

So the four collisions were renamed, and this test is what stops a fifth. It needs no
cluster, no network and no installed workspace: it reads the filesystem.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import pytest

#: Directories that are not source. ``.venv`` and ``site-packages`` matter most: third-party
#: distributions ship thousands of ``tests`` directories and none of them are ours.
PRUNED = frozenset(
    {
        ".git",
        ".hypothesis",
        ".hypothesis-corpus",
        ".import_linter_cache",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        ".venv",
        "__pycache__",
        "build",
        "dist",
        "htmlcov",
        "node_modules",
        "site-packages",
        "venv",
    }
)

#: ``conftest.py`` is EXEMPT, and the exemption is measured rather than assumed: this tree
#: carries **51** of them under test roots and collects 8 475 tests with no conftest-related
#: error, because pytest imports conftest files through its own plugin machinery rather than
#: as ordinary top-level modules. ``__init__.py`` is exempt because it names a package, not a
#: module, and duplicates of it are how packages are built.
EXEMPT_BASENAMES = frozenset({"conftest.py", "__init__.py"})


def _repo_root() -> Path:
    """Walk up until the marker files this repository is recognised by are both present."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").is_file() and (parent / "compose.yaml").is_file():
            return parent
    raise RuntimeError(f"cannot locate the repository root above {here}")


REPO_ROOT = _repo_root()


def _walk(directory: Path):
    """Every file below *directory*, skipping the pruned directory names."""
    for entry in sorted(directory.iterdir()):
        if entry.name in PRUNED:
            continue
        if entry.is_dir():
            yield from _walk(entry)
        elif entry.is_file():
            yield entry


def discover_test_roots() -> list[Path]:
    """Every directory named ``tests`` in this repository, outermost only.

    Discovered rather than listed, so a test root that a future package adds is covered the
    day it lands instead of the day someone remembers to add it here. That includes roots
    ``testpaths`` does not yet name — ``verticals/*/packages/*/tests`` has never run in a
    default ``pytest`` invocation, and its collision with ``packages/trappoint-migrate/tests``
    was latent for exactly that reason.
    """
    found: list[Path] = []
    stack = [REPO_ROOT]
    while stack:
        current = stack.pop()
        for entry in sorted(current.iterdir()):
            if not entry.is_dir() or entry.name in PRUNED:
                continue
            if entry.name == "tests":
                found.append(entry)
                continue  # outermost only: a tests/ inside a tests/ is one root
            stack.append(entry)
    return sorted(found)


def _import_key(path: Path) -> str:
    """The name ``prepend`` mode would import *path* under.

    A file in a directory carrying ``__init__.py`` is namespaced by the package chain above
    it, so ``tests/unit/archivist/test_a.py`` imports as ``archivist.test_a`` and cannot
    collide with a bare ``test_a.py``. A file in a directory without one imports as its bare
    basename, and that is where collisions live.
    """
    parts = [path.stem]
    directory = path.parent
    while (directory / "__init__.py").is_file():
        parts.append(directory.name)
        directory = directory.parent
    return ".".join(reversed(parts))


def _collect() -> dict[str, list[Path]]:
    by_key: dict[str, list[Path]] = defaultdict(list)
    for root in discover_test_roots():
        for path in _walk(root):
            if path.suffix != ".py" or path.name in EXEMPT_BASENAMES:
                continue
            by_key[_import_key(path)].append(path)
    return by_key


def test_the_repository_has_test_roots_to_check() -> None:
    """A checker that silently found nothing would pass forever.

    Nineteen ``tests`` directories were counted on 2026-08-10 across ``tests/``,
    ``packages/*/tests`` and ``verticals/*/packages/*/tests``.
    """
    roots = discover_test_roots()
    assert len(roots) >= 10, f"only {len(roots)} test roots found; the walk is not reaching them"
    names = {root.relative_to(REPO_ROOT).as_posix() for root in roots}
    assert "tests" in names
    assert any(name.startswith("packages/") for name in names)
    assert any(name.startswith("verticals/") for name in names), (
        "verticals/*/packages/*/tests must be walked even though `testpaths` does not name it: "
        "the fourth collision was latent there precisely because nothing looked"
    )


def test_no_two_test_modules_claim_the_same_import_name() -> None:
    """The invariant. One name, one file, across every test root in the repository."""
    duplicates = {key: paths for key, paths in _collect().items() if len(paths) > 1}
    if duplicates:
        report = "\n".join(
            f"  {key}\n" + "\n".join(f"    {p.relative_to(REPO_ROOT).as_posix()}" for p in paths)
            for key, paths in sorted(duplicates.items())
        )
        pytest.fail(
            f"{len(duplicates)} import name(s) are claimed by more than one file. Under "
            "pytest's `prepend` import mode this is a collection ERROR, not a warning — the "
            "second file is not collected at all. Rename one of each pair; do not add "
            "`__init__.py` and do not switch import mode, both of which were measured on this "
            f"tree and both of which are worse.\n{report}"
        )


def test_the_four_renames_that_this_test_exists_to_keep() -> None:
    """The specific collisions measured on 2026-08-10, named so a revert is loud.

    A generic invariant tells you *that* something broke. These four say *what*, and they are
    the reason this file exists rather than a comment in a review.
    """
    recall = "tests/integration/recall_schema"
    sql = "packages/trappoint-sql/tests"
    lattice = "tests/unit/domain/lattice"
    patrol = "verticals/mainline/packages/mainline-custody-patrol/tests"
    gone = [
        (f"{recall}/_support.py", f"{recall}/_schema_support.py"),
        (f"{sql}/test_cli.py", f"{sql}/test_sql_cli.py"),
        (f"{lattice}/test_red_first.py", f"{lattice}/test_lattice_red_first.py"),
        (
            f"{patrol}/test_fingerprint_stability.py",
            f"{patrol}/test_patrol_fingerprint_stability.py",
        ),
    ]
    for old, new in gone:
        assert not (REPO_ROOT / old).exists(), (
            f"{old} is back. It collides with a module of the same basename elsewhere in the "
            f"tree; the renamed file is {new}."
        )
        assert (REPO_ROOT / new).is_file(), f"{new} is missing"
