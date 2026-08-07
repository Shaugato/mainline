# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Repository location and file walking.

Nothing clever here, but two decisions matter. The repo root is located by a
*content* marker rather than by ``.git`` alone, so the checks keep working inside
a source tarball or a container layer that has no git metadata. And the excluded
directory set is a closed list rather than a gitignore parse, so a check can
never be silenced by adding a line to ``.gitignore``.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Sequence
from pathlib import Path

#: A directory containing any one of these is the repository root.
ROOT_MARKERS: tuple[str, ...] = ("spec/TRAPPOINT-SPEC.md", "docs/leads/workers.json", ".git")

#: Never walked. Deliberately a closed list — see module docstring.
EXCLUDED_DIR_NAMES: frozenset[str] = frozenset(
    {
        ".git",
        ".github-cache",
        ".hypothesis",
        ".hypothesis-corpus",
        ".idea",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        ".venv",
        "__pycache__",
        "build",
        "dist",
        "node_modules",
        "site-packages",
        "venv",
    }
)


def find_repo_root(start: Path | None = None) -> Path:
    """Walk up from ``start`` (default: this file) until a root marker is found.

    Falls back to the highest directory containing a ``spec`` and a ``packages``
    directory, and finally to ``start`` itself, so this never raises: a wrong
    root produces loud "root absent" skips, which is the outcome we want, rather
    than an exception in collection that looks like an infrastructure problem.
    """
    here = (start or Path(__file__)).resolve()
    candidates = [here, *here.parents]
    for candidate in candidates:
        for marker in ROOT_MARKERS:
            if (candidate / marker).exists():
                return candidate
    for candidate in candidates:
        if (candidate / "spec").is_dir() and (candidate / "packages").is_dir():
            return candidate
    return here if here.is_dir() else here.parent


def iter_files(
    root: Path,
    suffixes: Iterable[str],
    *,
    excluded: frozenset[str] = EXCLUDED_DIR_NAMES,
) -> Iterator[Path]:
    """Yield every file under ``root`` whose suffix is in ``suffixes``, sorted.

    Sorted output matters: a report whose finding order depends on filesystem
    iteration order is a report whose diff is noise.
    """
    wanted = {s.lower() for s in suffixes}
    if root.is_file():
        if root.suffix.lower() in wanted:
            yield root
        return
    if not root.is_dir():
        return
    stack = [root]
    found: list[Path] = []
    while stack:
        current = stack.pop()
        try:
            entries = sorted(current.iterdir())
        except (PermissionError, OSError):
            continue
        for entry in entries:
            if entry.is_dir():
                if entry.name not in excluded:
                    stack.append(entry)
            elif entry.suffix.lower() in wanted:
                found.append(entry)
    yield from sorted(found)


def iter_python_files(root: Path) -> Iterator[Path]:
    yield from iter_files(root, (".py",))


def expand_roots(repo_root: Path, patterns: Sequence[str]) -> dict[str, tuple[Path, ...]]:
    """Glob-expand each root pattern relative to ``repo_root``.

    Returns pattern → matched paths. A pattern that matched nothing maps to an
    empty tuple, which callers must turn into a *skip with reason* — never into
    silence. This is the mechanism behind the ``mainline-gate-svc`` trap: the
    package does not exist yet, so its pattern matches nothing, and the check
    must say so out loud.
    """
    out: dict[str, tuple[Path, ...]] = {}
    for pattern in patterns:
        if any(ch in pattern for ch in "*?["):
            matches = tuple(sorted(p for p in repo_root.glob(pattern) if p.exists()))
        else:
            direct = repo_root / pattern
            matches = (direct,) if direct.exists() else ()
        out[pattern] = matches
    return out


def rel(path: Path, root: Path) -> str:
    """POSIX-style path relative to ``root``; absolute POSIX path if unrelated."""
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def is_test_path(path: Path) -> bool:
    """True for files that are part of a test suite rather than shipped code."""
    parts = {p.lower() for p in path.parts}
    if parts & {"tests", "test", "testing"}:
        return True
    name = path.name.lower()
    return name.startswith("test_") or name.endswith("_test.py") or name == "conftest.py"
