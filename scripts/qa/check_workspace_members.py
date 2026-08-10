#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The workspace guard: the tree and the lockfile must agree about who is a member.

On 2026-08-10 they did not, and had not for a long time. `uv.lock`'s
`[manifest] members` named **seven** distributions:

    mainline-boundary, mainline-domain, mainline-recall-agent,
    trappoint-conformance, trappoint-jcs, trappoint-migrate, trappoint-recall

against **twenty-nine** `pyproject.toml` files on disk under the workspace globs —
thirty once `mainline-corpus` was given the one it had always been missing. Twenty-three
distributions were in the repository and absent from its single resolution. `uv lock
--check` (ci.yml job 1) and `uv sync --frozen --all-packages` (job 2) could not pass, and
the green ticks they had been showing were green ticks about a workspace that stopped
describing this repository twenty-three distributions ago.

THE DRIFT IS SILENT IN BOTH DIRECTIONS, WHICH IS WHY A SCRIPT HAS TO SAY IT.

* **Tree-only.** A new `pyproject.toml` lands. The workspace globs admit it with no edit
  to the root, so `uv sync` on a laptop that already has a lock does *not* fail — it
  installs what the lock says and the new package is simply missing. The author's own
  laptop keeps working, because their editable install predates the lock. It breaks for
  the next person, and it breaks in CI as an unrelated `ModuleNotFoundError` three jobs
  later. This is the exact hole `mainline-corpus` fell into: ninety-four modules, four
  importers, no distribution, and a `PYTHONPATH` in everyone's shell profile.

* **Lock-only.** A distribution is deleted or renamed and the lock still names it.
  Measured: `uv lock --check` DOES catch this one — but it catches it by re-resolving,
  which needs a network in the general case, and it reports it as a lockfile that is
  "not up to date" rather than as a member that no longer exists. This check names the
  member.

WHY NOT JUST `uv lock --check`. Because it answers a different question. `uv lock --check`
asks *"would re-resolving produce this same lock?"* — a question about versions, markers,
indexes and hashes, which needs uv installed and (usually) a network. This asks *"is the
member set the same set?"* — a question about the shape of the repository, answerable from
two files with the standard library alone, in milliseconds, on a machine where uv has never
been installed. On 2026-08-10 uv was not installed on the machine this repository is
developed on, while every `just` recipe and seven of eleven workflows began with it. A guard
that requires the missing tool to report the missing tool's problem is not a guard.

WHAT COUNTS AS A MEMBER. The globs in `[tool.uv.workspace] members`, read out of the root
`pyproject.toml` rather than hardcoded, minus `exclude`. Reading them is the point: a guard
that carried its own copy of the globs would pass on the day someone narrowed the real ones.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

#: Read when the root `pyproject.toml` declares no globs at all. Never used as an
#: override — if `[tool.uv.workspace] members` exists, it wins, because the guard's whole
#: value is that it reads the same declaration uv reads.
FALLBACK_MEMBER_GLOBS = ("packages/*", "verticals/*/packages/*")

#: uv's own default. A workspace with no `exclude` still must not walk a pnpm tree.
FALLBACK_EXCLUDE_GLOBS = ("**/node_modules",)


class WorkspaceError(RuntimeError):
    """A file the guard must read is absent or unparseable. Distinct from a drift."""


@dataclass(frozen=True)
class Member:
    """One distribution found on disk: its declared name and where it lives."""

    name: str
    path: str

    def __str__(self) -> str:
        return f"{self.name}  ({self.path})"


@dataclass
class Report:
    """The verdict, and enough detail to act on it without opening either file."""

    missing_from_lock: list[Member] = field(default_factory=list)
    missing_from_tree: list[str] = field(default_factory=list)
    unnamed: list[str] = field(default_factory=list)
    tree_members: int = 0
    lock_members: int = 0
    globs: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not (self.missing_from_lock or self.missing_from_tree or self.unnamed)

    def as_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "tree_members": self.tree_members,
            "lock_members": self.lock_members,
            "globs": self.globs,
            "missing_from_lock": [{"name": m.name, "path": m.path} for m in self.missing_from_lock],
            "missing_from_tree": self.missing_from_tree,
            "unnamed": self.unnamed,
        }


def _load_toml(path: Path) -> dict[str, object]:
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise WorkspaceError(f"{path} does not exist") from exc
    except tomllib.TOMLDecodeError as exc:
        raise WorkspaceError(f"{path} is not valid TOML: {exc}") from exc


def _str_list(value: object) -> list[str]:
    return [item for item in value if isinstance(item, str)] if isinstance(value, list) else []


def read_workspace_globs(root_pyproject: Path) -> tuple[list[str], list[str]]:
    """Return `(members, exclude)` from `[tool.uv.workspace]`, with uv's defaults."""
    data = _load_toml(root_pyproject)
    tool = data.get("tool")
    workspace = tool.get("uv", {}).get("workspace", {}) if isinstance(tool, dict) else {}
    if not isinstance(workspace, dict):
        workspace = {}
    members = _str_list(workspace.get("members")) or list(FALLBACK_MEMBER_GLOBS)
    exclude = _str_list(workspace.get("exclude")) or list(FALLBACK_EXCLUDE_GLOBS)
    return members, exclude


def _excluded(relative: str, exclude: list[str]) -> bool:
    """True when a member directory matches any `exclude` glob.

    `**/node_modules` has to match `a/b/node_modules` and `node_modules` alike, which
    `fnmatch` does not do for `**` on its own, so the leading `**/` form is also tried
    without its prefix.
    """
    candidates = {relative, *(f"{relative}/",)}
    for pattern in exclude:
        bare = pattern[3:] if pattern.startswith("**/") else pattern
        for candidate in candidates:
            if fnmatch.fnmatch(candidate, pattern) or fnmatch.fnmatch(candidate, f"*/{bare}"):
                return True
            if candidate.rstrip("/") == bare:
                return True
    return False


def discover_tree_members(
    repo_root: Path, globs: list[str], exclude: list[str]
) -> tuple[list[Member], list[str]]:
    """Every distribution on disk that the workspace globs admit, sorted by name.

    Returns `(members, unnamed)`. A member is a directory matching a glob and containing a
    `pyproject.toml` with a `[project] name`. A directory with a `pyproject.toml` and no
    `[project]` table is a nested *virtual* workspace, which uv does not treat as a member
    either — it comes back as `unnamed` rather than being silently dropped, because a
    distribution that cannot be named cannot be locked and someone needs to be told which
    one it is. Both are returned rather than raised so that every finding in one tree is
    reported in one run.
    """
    members: dict[str, Member] = {}
    unnamed: list[str] = []
    for glob in globs:
        for pyproject in sorted(repo_root.glob(f"{glob}/pyproject.toml")):
            relative = pyproject.parent.relative_to(repo_root).as_posix()
            if _excluded(relative, exclude):
                continue
            project = _load_toml(pyproject).get("project")
            name = project.get("name") if isinstance(project, dict) else None
            if isinstance(name, str) and name:
                members[name] = Member(name=name, path=relative)
            else:
                unnamed.append(relative)
    return sorted(members.values(), key=lambda m: m.name), sorted(unnamed)


def read_lock_members(lock_path: Path) -> list[str]:
    """`[manifest] members` from `uv.lock`, sorted.

    Parsed with `tomllib` rather than by running `uv`: this guard must work on a checkout
    where uv is not installed, which on 2026-08-10 was every checkout on this machine.
    """
    manifest = _load_toml(lock_path).get("manifest")
    if not isinstance(manifest, dict):
        raise WorkspaceError(f"{lock_path} has no [manifest] table; it is not a uv lockfile")
    return sorted(_str_list(manifest.get("members")))


def check(repo_root: Path, lock_path: Path | None = None) -> Report:
    """Compare the two member sets and return the verdict."""
    root_pyproject = repo_root / "pyproject.toml"
    lock = lock_path if lock_path is not None else repo_root / "uv.lock"

    globs, exclude = read_workspace_globs(root_pyproject)
    tree, unnamed = discover_tree_members(repo_root, globs, exclude)
    locked = read_lock_members(lock)

    tree_names = {member.name for member in tree}
    report = Report(
        tree_members=len(tree),
        lock_members=len(locked),
        globs=list(globs),
        unnamed=unnamed,
    )
    report.missing_from_lock = [m for m in tree if m.name not in set(locked)]
    report.missing_from_tree = sorted(set(locked) - tree_names)
    return report


def render(report: Report, lock_path: Path) -> str:
    """The human-readable report. Every failure line names the fix."""
    lines: list[str] = []
    if report.missing_from_lock:
        lines.append(f"these distributions are on disk and absent from {lock_path.name}:")
        lines.extend(f"  {member}" for member in report.missing_from_lock)
        lines.append(
            "  fix: run `uv lock`. Until you do, `uv sync --frozen --all-packages` "
            "installs a workspace that is missing them and every importer fails as an "
            "unrelated ModuleNotFoundError."
        )
    if report.missing_from_tree:
        lines.append(f"these {lock_path.name} members have no distribution on disk:")
        lines.extend(f"  {name}" for name in report.missing_from_tree)
        lines.append(
            "  fix: run `uv lock`. A member that was renamed or deleted leaves the lock "
            "describing a package nobody can build."
        )
    if report.unnamed:
        lines.append("these member directories have a pyproject.toml with no [project] name:")
        lines.extend(f"  {path}" for path in report.unnamed)
        lines.append("  fix: give it a `[project] name`, or move it out of the member globs.")
    if report.ok:
        lines.append(
            f"the tree and {lock_path.name} agree: {report.tree_members} distributions, "
            f"{report.lock_members} locked members, globs {report.globs}."
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """Run the guard. 0 when the two member sets are equal, 1 when they are not."""
    parser = argparse.ArgumentParser(
        prog="check_workspace_members",
        description=(
            "Refuse a build in which the uv workspace on disk and the member set in "
            "uv.lock are not the same set."
        ),
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="repository root (default: two levels above this script)",
    )
    parser.add_argument(
        "--lock",
        type=Path,
        default=None,
        help="path to uv.lock (default: <repo-root>/uv.lock)",
    )
    parser.add_argument("--json", action="store_true", help="emit the report as JSON")
    args = parser.parse_args(argv)

    repo_root: Path = args.repo_root.resolve()
    lock_path: Path = args.lock if args.lock is not None else repo_root / "uv.lock"

    try:
        report = check(repo_root, lock_path)
    except WorkspaceError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(report.as_dict(), indent=2, sort_keys=True))
    else:
        print(render(report, lock_path))
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
