#!/usr/bin/env python
# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
#
# MI: none — this file makes no database claim.
# I: SUB-PATHLEN-1 — the longest tracked path in this repository is a published number
#    that may fall and may not rise, because it is the number that decides whether a
#    stranger on Windows can check the repository out at all.
# RATIONALE: this file used to record that the console's replay frames "cannot be
#    renamed without breaking the console loader and the bundle manifest (lead ruling
#    L-2)", that the judge-facing repair was a clone flag, and that counting the exposure
#    was all this domain could do. That was measured again on 2026-08-10 and it was
#    wrong on the only point that mattered.
#
#    The frames were named by spelling the whole request line into the file name with a
#    `~XX` escape, which produced a 218-character path — 40 characters of clone
#    destination, against the 44 of `C:\Users\someone\Documents\projects\mainline`. The
#    encoder could not be fixed by escaping less: the longest request key is 132
#    characters BEFORE any escaping, and `132 + 5 + 67` is 204 against a budget of 198,
#    so even an identity encoding that wrote `/` and `?` straight into a file name would
#    have blown it. A name that does not grow with the request was therefore forced.
#
#    Frames are now content-addressed, `frames/<METHOD>-<sha256(key)[:16]>.json`, written
#    by `verticals/mainline/apps/console/scripts/capture-bundle.ts`. Nothing about the
#    bundle's meaning moved: the request line is carried verbatim in the manifest as
#    `files[].key`, INSIDE the digest-sealed set the in-browser verifier hashes, and the
#    console addresses frames by that field. The measurement fell 218 -> 141 and the
#    count of paths a 60-character destination cannot check out fell 4 -> 0.
#
#    The standing rule is unchanged and is the reason this file exists: the budget below
#    is falling-only, a rise names the paths that caused it and exits 1, and the repair
#    for a rise is a shorter name — never a larger budget and never a clone flag.
"""Windows clone-path budget for the MAINLINE repository.

Windows' `MAX_PATH` is 260 characters *including* the terminating NUL, so 259 characters
of path are usable by any program that has not opted into long paths. A checkout costs

    len(clone destination) + 1 (separator) + len(path relative to the repo root)

so the longest tracked path fixes a hard ceiling on where a stranger may clone. This
script measures that ceiling, publishes it, and refuses an increase.

    python scripts/submission/check_path_lengths.py            # measure + enforce
    python scripts/submission/check_path_lengths.py --json     # the report on stdout
    python scripts/submission/check_path_lengths.py --update   # lower a budget that fell
    python scripts/submission/check_path_lengths.py --self-test

Exit codes:

* ``0`` — measured at or under budget (or the budget was lowered under ``--update``).
* ``1`` — a counted number ROSE. The offending paths are named.
* ``2`` — the script could not run: no git, not a repository, or no budget recorded and
  ``--update`` was not given. Distinct from 1 so "could not measure" is never read as
  "the budget was blown".

Stdlib only. No network. The only file it may write is the report JSON, and only under
``--update``.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA = "mainline.qa.path-lengths/1"

# Windows MAX_PATH is 260 *including* the terminating NUL. Measured on this machine:
# a 259-character path opens; a 260-character path raises FileNotFoundError from CPython
# 3.13 while `LongPathsEnabled` is 0. See qa/judge-dry-run.json -> clone_threshold.
WINDOWS_MAX_PATH = 260
WINDOWS_USABLE_PATH = WINDOWS_MAX_PATH - 1

# NTFS refuses a single name component longer than this, long paths enabled or not.
NTFS_MAX_COMPONENT = 255

# A "typical" judge destination: C:\Users\someone\code\mainline is 27 characters, a
# Documents\projects tree is comfortably past 50. 60 is the round number this repository
# counts itself against, and the count is a ratchet.
TYPICAL_PREFIX = 60

EXIT_OK = 0
EXIT_ROSE = 1
EXIT_CANNOT_RUN = 2

DEFAULT_REPORT = Path("qa") / "judge-dry-run.json"

BUDGET_NOTE = (
    "Falling-only. Each number below was measured, never chosen. A number that falls may "
    "be lowered with --update; a number that rises names the paths that raised it and "
    "exits 1. The ceiling is not a style rule: it is the length at which `git clone` on "
    "default Windows stops producing a working tree."
)


class CannotRun(Exception):
    """The measurement could not be taken at all."""


# --------------------------------------------------------------------------- measuring


def tracked_paths(repo: Path) -> list[str]:
    """Return every path git tracks, repo-relative, with forward slashes.

    `git ls-files -z` is the authority: it is the same set that lands in a clone, it
    honours `.gitignore` for free, and NUL separation means a path containing a newline
    (legal on Linux, and this repository is cloned on Linux in CI) cannot corrupt it.
    """
    try:
        completed = subprocess.run(  # fixed argv, no shell
            ["git", "-C", str(repo), "ls-files", "-z"],
            capture_output=True,
            check=False,
            timeout=120,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise CannotRun(f"could not run git: {exc}") from exc
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", "replace").strip()
        raise CannotRun(f"git ls-files failed in {repo}: {detail or completed.returncode}")
    raw = completed.stdout.decode("utf-8", "surrogateescape")
    return [p for p in raw.split("\0") if p]


def parse_ls_files_z(raw: str) -> list[str]:
    """Split the NUL-separated payload of `git ls-files -z`. Exposed for --self-test."""
    return [p for p in raw.split("\0") if p]


def head_sha(repo: Path) -> str | None:
    try:
        completed = subprocess.run(  # fixed argv, no shell
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return completed.stdout.strip() or None if completed.returncode == 0 else None


def longest_component(path: str) -> tuple[int, str]:
    """Longest single name component of a repo-relative path, and the component."""
    parts = path.split("/")
    best = max(parts, key=len)
    return len(best), best


def measure(
    paths: list[str],
    *,
    usable: int = WINDOWS_USABLE_PATH,
    typical_prefix: int = TYPICAL_PREFIX,
    top: int = 8,
) -> dict[str, Any]:
    """Measure the path-length exposure of a set of repo-relative paths.

    The arithmetic, stated once so it can be checked:

        full = len(destination) + 1 + len(relative path)
        a program without long-path support needs  full <= usable
        therefore                                  len(destination) <= usable - 1 - longest
    """
    if not paths:
        raise CannotRun("no tracked paths — is this an empty repository?")

    ranked = sorted(paths, key=lambda p: (-len(p), p))
    longest_len = len(ranked[0])
    max_prefix = usable - 1 - longest_len

    comp_len, comp_name = max((longest_component(p) for p in paths), key=lambda t: t[0])
    comp_owner = next(p for p in paths if comp_name in p.split("/"))

    budget_at_typical = usable - 1 - typical_prefix
    unclonable = [p for p in ranked if len(p) > budget_at_typical]

    return {
        "schema": SCHEMA,
        "measured_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "method": "git ls-files -z",
        "arithmetic": (
            "full = len(clone destination) + 1 + len(path relative to the repo root); a "
            f"program without long-path support needs full <= {usable}"
        ),
        "windows_max_path_chars": WINDOWS_MAX_PATH,
        "windows_usable_path_chars": usable,
        "ntfs_max_component_chars": NTFS_MAX_COMPONENT,
        "tracked_files": len(paths),
        "max_tracked_path_chars": longest_len,
        "max_safe_clone_prefix_chars": max_prefix,
        "longest_paths": [{"chars": len(p), "path": p} for p in ranked[:top]],
        "longest_component": {
            "chars": comp_len,
            "component": comp_name,
            "in_path": comp_owner,
            "ntfs_headroom_chars": NTFS_MAX_COMPONENT - comp_len,
        },
        "typical_prefix_chars": typical_prefix,
        "files_unclonable_at_typical_prefix": len(unclonable),
        "unclonable_at_typical_prefix": [
            {"chars": len(p), "path": p} for p in unclonable[:top]
        ],
    }


# ---------------------------------------------------------------------------- budgeting

#: (report key, budget key, human name). Every one of these may fall and may not rise.
COUNTED = (
    ("max_tracked_path_chars", "max_tracked_path_chars", "longest tracked path (chars)"),
    (
        "files_unclonable_at_typical_prefix",
        "files_unclonable_at_typical_prefix",
        f"tracked paths a {TYPICAL_PREFIX}-char clone prefix cannot check out",
    ),
)


def seed_budget(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "policy": "falling-only",
        "note": BUDGET_NOTE,
        "set_utc": report["measured_utc"],
        "typical_prefix_chars": report["typical_prefix_chars"],
        **{bkey: report[rkey] for rkey, bkey, _ in COUNTED},
    }


def enforce(report: dict[str, Any], budget: dict[str, Any] | None) -> tuple[str, list[str]]:
    """Compare the measurement against the budget.

    Returns ``(status, complaints)`` where status is one of ``OK``, ``SLACK``,
    ``EXCEEDED`` or ``NO_BUDGET``.
    """
    if not budget:
        return "NO_BUDGET", []

    complaints: list[str] = []
    slack = False
    for rkey, bkey, human in COUNTED:
        if bkey not in budget:
            complaints.append(f"budget has no entry for {bkey!r} ({human})")
            continue
        measured, allowed = report[rkey], budget[bkey]
        if measured > allowed:
            complaints.append(f"{human}: {measured} > budget {allowed} — RISE REFUSED")
        elif measured < allowed:
            slack = True

    if complaints:
        return "EXCEEDED", complaints
    return ("SLACK" if slack else "OK"), []


def lower_budget(report: dict[str, Any], budget: dict[str, Any]) -> list[str]:
    """Lower every counted number that fell. Never raises one. Returns a change log."""
    changed: list[str] = []
    for rkey, bkey, human in COUNTED:
        measured = report[rkey]
        allowed = budget.get(bkey)
        if allowed is None or measured < allowed:
            budget[bkey] = measured
            changed.append(f"{human}: {allowed} -> {measured}")
    if changed:
        budget["set_utc"] = report["measured_utc"]
        budget.setdefault("policy", "falling-only")
        budget.setdefault("note", BUDGET_NOTE)
        budget["typical_prefix_chars"] = report["typical_prefix_chars"]
    return changed


# ------------------------------------------------------------------------- report file


def load_report_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CannotRun(f"{path} is not readable JSON: {exc}") from exc
    if not isinstance(loaded, dict):
        raise CannotRun(f"{path} does not hold a JSON object")
    return loaded


def write_report_file(path: Path, document: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def merge_into_document(
    document: dict[str, Any], report: dict[str, Any], budget: dict[str, Any] | None
) -> dict[str, Any]:
    """Put ``report`` under the ``path_lengths`` key, carrying ``budget`` with it."""
    block = dict(report)
    if budget is not None:
        block["budget"] = budget
    document["path_lengths"] = block
    return document


def survive_a_narrow_console() -> None:
    """Never let an encoding raise. A cp1252 console cannot encode the em dashes here."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        # A stream that will not take the argument is a stream we print to unchanged,
        # which is exactly what this function exists to guarantee.
        with contextlib.suppress(OSError, ValueError):
            reconfigure(errors="replace")


def repo_root_of(start: Path) -> Path:
    for candidate in (start, *start.parents):
        if (candidate / ".git").exists():
            return candidate
    return start


# -------------------------------------------------------------------------- self-test


def _self_test() -> int:  # noqa: PLR0915 — a flat list of assertions reads better flat
    """Exercise the arithmetic, the ratchet and the file round-trip. No repo needed."""
    import tempfile

    failures: list[str] = []

    def check(name: str, condition: bool, detail: str = "") -> None:
        if condition:
            print(f"  ok   {name}")
        else:
            print(f"  FAIL {name}{(' — ' + detail) if detail else ''}")
            failures.append(name)

    print("check_path_lengths --self-test")

    # 1. NUL splitting, including a path containing a newline.
    parsed = parse_ls_files_z("a/b.txt\0c/d\ne.txt\0\0")
    check("parse_ls_files_z splits on NUL only", parsed == ["a/b.txt", "c/d\ne.txt"], repr(parsed))

    # 2. The arithmetic, against a synthetic tree with a known longest path.
    longest = "x" * 200
    paths = ["short.txt", "a/" + longest, "a/b/c.txt"]
    report = measure(paths, top=3)
    check("longest is measured, not guessed", report["max_tracked_path_chars"] == 202)
    check(
        "max_safe_clone_prefix = usable - 1 - longest",
        report["max_safe_clone_prefix_chars"] == WINDOWS_USABLE_PATH - 1 - 202,
        str(report["max_safe_clone_prefix_chars"]),
    )
    check("longest component found", report["longest_component"]["chars"] == 200)
    check("tracked_files counted", report["tracked_files"] == 3)

    # 2b. The boundary this whole file exists for: 259 fits, 260 does not.
    at_limit = measure(["p" * (WINDOWS_USABLE_PATH - 1 - 44)], top=1)
    check(
        "a 44-char destination is exactly admissible",
        at_limit["max_safe_clone_prefix_chars"] == 44,
        str(at_limit["max_safe_clone_prefix_chars"]),
    )

    # 3. Counting what a typical prefix cannot check out.
    typ = measure(["y" * 199, "y" * 198, "small"], typical_prefix=60, top=3)
    check(
        "files over the typical prefix are counted",
        typ["files_unclonable_at_typical_prefix"] == 1,
        str(typ["files_unclonable_at_typical_prefix"]),
    )

    # 4. The ratchet: equal is OK, lower is SLACK, higher is EXCEEDED.
    budget = seed_budget(report)
    status, complaints = enforce(report, budget)
    check("equal measurement is OK", status == "OK" and not complaints, status)

    fell = measure(["a/" + "x" * 100], top=1)
    status, complaints = enforce(fell, budget)
    check("a fall is SLACK, not a failure", status == "SLACK" and not complaints, status)

    rose = measure(["a/" + "x" * 300], top=1)
    status, complaints = enforce(rose, budget)
    check("a rise is EXCEEDED", status == "EXCEEDED", status)
    check(
        "a rise names its numbers",
        any("RISE REFUSED" in c for c in complaints),
        "; ".join(complaints),
    )

    # 5. --update lowers and never raises.
    lowered = dict(budget)
    changed = lower_budget(fell, lowered)
    check("a fall lowers the budget", lowered["max_tracked_path_chars"] == 102, str(changed))
    not_changed = dict(lowered)
    raised = lower_budget(rose, not_changed)
    check(
        "a rise does not raise the budget",
        not_changed["max_tracked_path_chars"] == 102 and raised == [],
        str(not_changed["max_tracked_path_chars"]),
    )

    # 6. No budget recorded is its own state, not a pass.
    status, _ = enforce(report, None)
    check("absent budget is NO_BUDGET", status == "NO_BUDGET", status)

    # 7. File round-trip preserves keys this script does not own.
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "nested" / "report.json"
        write_report_file(target, {"kept_by_another_worker": 42})
        doc = load_report_file(target)
        doc = merge_into_document(doc, report, budget)
        write_report_file(target, doc)
        reloaded = load_report_file(target)
        check(
            "merge preserves foreign keys",
            reloaded.get("kept_by_another_worker") == 42,
            json.dumps(sorted(reloaded)),
        )
        check(
            "merge writes the budget under path_lengths",
            reloaded["path_lengths"]["budget"]["max_tracked_path_chars"] == 202,
        )

    # 8. An empty repository is a CannotRun, not a zero.
    try:
        measure([])
    except CannotRun:
        check("empty tree raises CannotRun", True)
    else:
        check("empty tree raises CannotRun", False, "no exception")

    print()
    if failures:
        print(f"SELF-TEST FAILED — {len(failures)} of the checks above did not hold")
        for name in failures:
            print(f"  - {name}")
        return EXIT_ROSE
    print("SELF-TEST PASSED")
    return EXIT_OK


# -------------------------------------------------------------------------------- main


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="check_path_lengths",
        description=(
            "Measure the longest tracked path, derive the longest Windows clone "
            "destination that still checks out, and refuse an increase."
        ),
    )
    parser.add_argument("--repo", type=Path, default=None, help="repository (default: this one)")
    parser.add_argument(
        "--report",
        type=Path,
        default=None,
        help=f"JSON carrying the budget (default: <repo>/{DEFAULT_REPORT.as_posix()})",
    )
    parser.add_argument(
        "--from-file",
        type=Path,
        default=None,
        help="read paths from a file, one per line, instead of asking git (for testing)",
    )
    parser.add_argument("--json", action="store_true", help="print the report and no table")
    parser.add_argument(
        "--update", action="store_true", help="write the report; lower a budget that fell"
    )
    parser.add_argument(
        "--typical-prefix",
        type=int,
        default=TYPICAL_PREFIX,
        help=f"prefix length the second counted number is taken at (default {TYPICAL_PREFIX})",
    )
    parser.add_argument("--top", type=int, default=8, help="how many long paths to list")
    parser.add_argument("--self-test", action="store_true", help="run the built-in checks and exit")
    return parser


def print_table(report: dict[str, Any], status: str, complaints: list[str]) -> None:
    print(f"MAINLINE path-length budget — {report['measured_utc']}")
    print()
    print(f"  tracked files                     {report['tracked_files']}")
    print(f"  longest tracked path              {report['max_tracked_path_chars']} chars")
    print(f"  longest single name component     {report['longest_component']['chars']} chars")
    print(f"  Windows usable path               {report['windows_usable_path_chars']} chars")
    print(f"  MAX SAFE CLONE DESTINATION        {report['max_safe_clone_prefix_chars']} chars")
    print(
        f"  paths a {report['typical_prefix_chars']}-char destination cannot check out   "
        f"{report['files_unclonable_at_typical_prefix']}"
    )
    print()
    print("  longest paths:")
    for row in report["longest_paths"]:
        print(f"    {row['chars']:>4}  {row['path']}")
    print()
    budget = report.get("budget")
    if budget:
        print(
            f"  budget: max_tracked_path_chars={budget.get('max_tracked_path_chars')} "
            f"files_unclonable_at_typical_prefix={budget.get('files_unclonable_at_typical_prefix')}"
            f"  ({budget.get('policy')})"
        )
    print(f"  STATUS: {status}")
    for complaint in complaints:
        print(f"    ! {complaint}")
    if status == "SLACK":
        print("    a counted number fell; re-run with --update to lower the budget")
    if status == "NO_BUDGET":
        print("    no budget recorded; re-run with --update to seed one")


def main(argv: list[str] | None = None) -> int:  # noqa: PLR0912 — one flat decision table
    survive_a_narrow_console()
    args = build_parser().parse_args(argv)

    if args.self_test:
        return _self_test()

    repo = (args.repo or repo_root_of(Path(__file__).resolve().parent)).resolve()
    report_path = args.report or (repo / DEFAULT_REPORT)

    try:
        if args.from_file:
            paths = [
                line.strip()
                for line in args.from_file.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            source = f"--from-file {args.from_file}"
        else:
            paths = tracked_paths(repo)
            source = "git ls-files -z"

        report = measure(paths, typical_prefix=args.typical_prefix, top=args.top)
        report["method"] = source
        report["repo"] = repo.as_posix()
        report["head"] = head_sha(repo)

        document = load_report_file(report_path)
    except CannotRun as exc:
        print(f"check_path_lengths: {exc}", file=sys.stderr)
        return EXIT_CANNOT_RUN

    existing = (document.get("path_lengths") or {}).get("budget")
    budget = dict(existing) if isinstance(existing, dict) else None

    status, complaints = enforce(report, budget)
    changes: list[str] = []

    if args.update:
        if budget is None:
            budget = seed_budget(report)
            changes.append("budget seeded from this measurement")
            status, complaints = enforce(report, budget)
        elif status == "EXCEEDED":
            pass  # --update never covers up a rise
        else:
            changes = lower_budget(report, budget)
            status, complaints = enforce(report, budget)

    report["budget"] = budget
    report["budget_status"] = status
    report["budget_complaints"] = complaints

    if args.update and status != "EXCEEDED":
        document = merge_into_document(document, report, budget)
        write_report_file(report_path, document)
        changes.append(f"wrote {report_path.as_posix()}")

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print_table(report, status, complaints)
        for change in changes:
            print(f"    + {change}")

    if status == "EXCEEDED":
        return EXIT_ROSE
    if status == "NO_BUDGET":
        return EXIT_CANNOT_RUN
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
