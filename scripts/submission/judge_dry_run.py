#!/usr/bin/env python
# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
#
# MI: none — this file makes no database claim of its own. It RUNS the script that does
#     (scripts/proof/gate_refusal.py) inside a fresh clone and records what it printed.
# I: SUB-DRYRUN-1 — the claim "a judge can clone this and reproduce the refusal in five
#    minutes" is either measured against a real clone of HEAD or it is not made. A step
#    that did not run is NOT RUN. It is never PASS.
# RATIONALE: docs/STATE-OF-THE-BUILD.md §5 compared the working tree against a fresh
#    clone by hand and found they disagreed. The finding aged out in a day; the method
#    did not. This file is that method as a program, so the comparison is re-derivable by
#    anyone at any commit instead of being re-argued.
"""The judge's first five minutes, executed rather than asserted.

Clones HEAD of this repository into a temporary directory the way a stranger would, then
runs — inside the clone — the exact commands `README.md` and `docs/release/QUICKSTART.md`
tell that stranger to run, recording for each one its argv, exit code, wall-clock
duration and the first and last 40 lines of its combined output.

    python scripts/submission/judge_dry_run.py \\
        --dsn postgresql://root@127.0.0.1:26257/defaultdb?sslmode=disable

    python scripts/submission/judge_dry_run.py --skip-cluster   # no database at all

WHAT IT REFUSES TO DO
---------------------
It will not report a step it did not execute as a pass. Every step carries one of:

======================  =====================================================
``PASS``                executed; exit code 0
``PASS (CAVEATED)``     executed; exit code 0, but something about the run
                        makes the result mean less than it looks — the caveat
                        is a sentence in ``caveats``
``FAIL``                executed; non-zero exit code
``TIMEOUT``             executed; killed at the deadline
``SKIPPED``             deliberately not executed, e.g. under ``--skip-cluster``;
                        ``reason`` says which switch caused it
``NOT RUN``             could not be executed — a prerequisite was missing
``NOT PRESENT``         the documented file simply is not in the clone
======================  =====================================================

The default status of every step, before anything happens to it, is ``NOT RUN``.

A step whose non-zero exit is the CORRECT answer — `doctor.py` on a machine with no
``uv`` and no ``just`` — still says ``FAIL``, because that is what happened. It carries
``expected_failure: true`` and ``nonzero_expected_because``, and it is exempt from this
program's own exit code. Relabelling it ``PASS`` would be the one move this repository
exists to refuse.

WINDOWS CLONE THRESHOLD
-----------------------
``--probe-threshold`` binary-searches the destination-path length at which
``git clone`` stops producing a working tree on Windows, with and without
``-c core.longpaths=true``, by performing real clones into successively longer
directories. It is measurement, not arithmetic: the arithmetic lives in
``check_path_lengths.py`` and the two are compared in the output.

OUTPUT
------
One JSON document, by default ``qa/judge-dry-run.json``, schema
``mainline.qa.judge-dry-run/1``. Top-level keys, which downstream renderers may rely on:

``schema``, ``generated_utc``, ``generated_by``, ``note``
``host``            os, python running this script, git version, docker presence
``source``          the repository cloned: path, HEAD sha, branch, dirty/untracked
                    counts, divergence from ``origin``
``operator_notes``  free text passed with ``--note``, recorded verbatim — what else
                    the machine was doing, and anything a reader must know to
                    interpret the durations
``path_lengths``    written by ``check_path_lengths.py``; carries ``budget``
``clone_threshold`` the empirical Windows measurement, with every probe kept
``clone_attempts``  each clone tried, in order, with its flags and result
``clone_used``      the label of the clone the steps ran in
``interpreters``    every python the steps were run with, probed
``runs``            one object per interpreter: ``{interpreter, steps: [...]}``
``documented_commands``  what README/QUICKSTART tell a judge to type, and whether
                    the literal string is still in those files in the clone
``findings``        ordered, human-readable, each with a ``severity``
``verdict``         ``PROVEN`` / ``PROVEN_WITH_CAVEATS`` / ``NOT_PROVEN`` / ``NOT_RUN``
``reproduce``       the single command that regenerates this file

Exit codes: ``0`` the dry run completed and every non-skipped step passed; ``1`` the dry
run completed and something failed (the JSON is still written — publish it); ``2`` the
dry run could not start.

Stdlib only. No network beyond the local clone and the DSN it is given.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import platform
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_path_lengths as cpl  # sibling script, not a package: path first, import second

SCHEMA = "mainline.qa.judge-dry-run/1"
GENERATED_BY = "scripts/submission/judge_dry_run.py"

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_CANNOT_RUN = 2

HEAD_LINES = 40
TAIL_LINES = 40

STATUS_PASS = "PASS"  # noqa: S105 — a status word, not a credential
STATUS_CAVEATED = "PASS (CAVEATED)"
STATUS_FAIL = "FAIL"
STATUS_TIMEOUT = "TIMEOUT"
STATUS_SKIPPED = "SKIPPED"
STATUS_NOT_RUN = "NOT RUN"
STATUS_NOT_PRESENT = "NOT PRESENT"

#: The four commands the front door promises, and the fallback each one has when `just`
#: is absent. `just` is a single binary and is NOT a Python dependency, so on a machine
#: without it the right column is what a judge actually types.
DOCUMENTED = (
    ("just doctor", "python scripts/qa/doctor.py"),
    ("just setup", "uv sync --all-packages"),
    ("just up", "docker compose -f compose.yaml up -d"),
    ("just prove", "python scripts/proof/gate_refusal.py --dsn <dsn>"),
)

NOTE = (
    "A recording, not a claim. Every step below was executed inside a clone of HEAD made "
    "by this script; the argv, the exit code and the output excerpts are what the "
    "subprocess actually produced. A step that did not run says NOT RUN and never PASS. "
    "Re-derive the whole file with the command in `reproduce`."
)


# ------------------------------------------------------------------------ small helpers


def now_utc() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def survive_a_narrow_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        with contextlib.suppress(OSError, ValueError):
            reconfigure(errors="replace")


def long_path(path: Path) -> str:
    r"""Windows-safe absolute path.

    ``\\?\`` opts a single call out of ``MAX_PATH``. Needed here because this script
    deliberately creates trees that exceed it and then has to delete them again.
    """
    resolved = str(Path(path).absolute())
    if os.name == "nt" and not resolved.startswith("\\\\?\\"):
        return "\\\\?\\" + resolved.replace("/", "\\")
    return resolved


def force_rmtree(path: Path) -> bool:
    """Delete a tree, including read-only git objects and over-long Windows paths."""

    def on_error(func: Any, target: str, _exc: Any) -> None:
        with contextlib.suppress(OSError):
            Path(target).chmod(stat.S_IWRITE)
            func(target)

    if not Path(path).exists():
        return True
    with contextlib.suppress(OSError):
        shutil.rmtree(long_path(path), onerror=on_error)
    return not Path(path).exists()


def excerpt(text: str) -> dict[str, Any]:
    """First and last 40 lines of a captured stream, with the elision made explicit."""
    lines = text.splitlines()
    if len(lines) <= HEAD_LINES + TAIL_LINES:
        return {"lines_total": len(lines), "head": lines, "tail": [], "elided": 0}
    return {
        "lines_total": len(lines),
        "head": lines[:HEAD_LINES],
        "tail": lines[-TAIL_LINES:],
        "elided": len(lines) - HEAD_LINES - TAIL_LINES,
    }


def run_command(
    argv: list[str],
    *,
    cwd: Path | None = None,
    timeout: int = 600,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Execute one command, merging stderr into stdout the way a terminal does."""
    record: dict[str, Any] = {
        "argv": argv,
        "cwd": str(cwd) if cwd else None,
        "status": STATUS_NOT_RUN,
        "exit_code": None,
        "duration_s": None,
        "output": None,
    }
    started = time.monotonic()
    try:
        completed = subprocess.run(  # fixed argv, no shell
            argv,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
            env=env,
        )
    except subprocess.TimeoutExpired as exc:
        record["duration_s"] = round(time.monotonic() - started, 3)
        record["status"] = STATUS_TIMEOUT
        record["reason"] = f"killed at the {timeout}s deadline"
        record["output"] = excerpt(
            (exc.stdout or b"").decode("utf-8", "replace")
            if isinstance(exc.stdout, bytes)
            else (exc.stdout or "")
        )
        return record
    except (OSError, subprocess.SubprocessError) as exc:
        record["duration_s"] = round(time.monotonic() - started, 3)
        record["status"] = STATUS_NOT_RUN
        record["reason"] = f"could not start: {type(exc).__name__}: {exc}"
        return record

    record["duration_s"] = round(time.monotonic() - started, 3)
    record["exit_code"] = completed.returncode
    combined = (completed.stdout or "") + (completed.stderr or "")
    record["output"] = excerpt(combined)
    record["status"] = STATUS_PASS if completed.returncode == 0 else STATUS_FAIL
    record["_text"] = combined  # stripped before serialisation
    return record


def strip_internals(node: Any) -> Any:
    """Remove the private ``_text`` payloads before the document is written."""
    if isinstance(node, dict):
        return {k: strip_internals(v) for k, v in node.items() if not k.startswith("_")}
    if isinstance(node, list):
        return [strip_internals(v) for v in node]
    return node


# ---------------------------------------------------------------------------- the host


def git_version() -> str | None:
    out = run_command(["git", "--version"], timeout=60)
    return (out.get("_text") or "").strip() or None if out["status"] == STATUS_PASS else None


def windows_longpaths_enabled() -> bool | None:
    """Read HKLM LongPathsEnabled. ``None`` off Windows or when it cannot be read."""
    if os.name != "nt":
        return None
    try:
        import winreg
    except ImportError:  # pragma: no cover - Windows only
        return None
    try:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\FileSystem"
        ) as key:
            value, _ = winreg.QueryValueEx(key, "LongPathsEnabled")
            return bool(value)
    except OSError:
        return None


def host_block() -> dict[str, Any]:
    docker = run_command(["docker", "--version"], timeout=60)
    return {
        "platform": platform.platform(),
        "os_name": os.name,
        "python_running_this_script": {
            "executable": sys.executable,
            "version": sys.version.split()[0],
        },
        "git": git_version(),
        "docker": (docker.get("_text") or "").strip() or None,
        "windows_longpaths_enabled": windows_longpaths_enabled(),
        "windows_max_path_chars": cpl.WINDOWS_MAX_PATH,
        "tools_on_path": {
            name: shutil.which(name) for name in ("git", "docker", "just", "uv", "python", "node")
        },
    }


def source_block(repo: Path) -> dict[str, Any]:
    def git(*args: str) -> str:
        out = run_command(["git", "-C", str(repo), *args], timeout=120)
        return (out.get("_text") or "").strip() if out["status"] == STATUS_PASS else ""

    porcelain = git("status", "--porcelain")
    lines = [line for line in porcelain.splitlines() if line.strip()]
    ahead_behind = git("rev-list", "--left-right", "--count", "origin/HEAD...HEAD") or git(
        "rev-list", "--left-right", "--count", "origin/master...HEAD"
    )
    behind, ahead = [*ahead_behind.split(), "", ""][:2] if ahead_behind else ("", "")

    # What a stranger gets TODAY is the remote, not this disk. Two numbers say how far
    # apart they are, and one of them is whether the front door even mentions the
    # commands this dry run just executed.
    differing = [
        line for line in git("diff", "--name-only", "origin/master..HEAD").splitlines() if line
    ]
    remote_readme = git("show", "origin/master:README.md")
    remote_has_commands = (
        None if not remote_readme else all(command in remote_readme for command, _ in DOCUMENTED)
    )

    return {
        "repo": repo.as_posix(),
        "head": git("rev-parse", "HEAD") or None,
        "head_subject": git("log", "-1", "--pretty=%s") or None,
        "head_committed_utc": git("log", "-1", "--date=iso-strict", "--pretty=%cd") or None,
        "branch": git("rev-parse", "--abbrev-ref", "HEAD") or None,
        "remote": git("remote", "get-url", "origin") or None,
        "commits_ahead_of_origin": int(ahead) if ahead.isdigit() else None,
        "commits_behind_origin": int(behind) if behind.isdigit() else None,
        "files_differing_from_origin_master": len(differing),
        "origin_master_readme_has_the_documented_commands": remote_has_commands,
        "working_tree_modified_or_untracked": len(lines),
        "working_tree_note": (
            "A clone gets HEAD, not this disk. Everything counted above is INVISIBLE to a "
            "judge until it is committed and pushed."
        ),
    }


# ---------------------------------------------------------------------------- cloning


def clone_once(source: Path, dest: Path, *, longpaths: bool, timeout: int = 900) -> dict[str, Any]:
    """One `git clone`, classified. Never leaves a half-tree behind for the caller."""
    force_rmtree(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    flags = ["-c", "core.longpaths=true"] if longpaths else []
    argv = ["git", *flags, "clone", "--quiet", str(source), str(dest)]
    record = run_command(argv, timeout=timeout)
    text = record.get("_text") or ""
    record["dest"] = dest.as_posix()
    record["dest_chars"] = len(str(dest))
    record["longpaths"] = longpaths
    record["filename_too_long_errors"] = text.count("Filename too long")
    record["checkout_failed"] = "unable to checkout working tree" in text
    return record


def tree_health(dest: Path, longest_rel: str) -> dict[str, Any]:
    """Is the checked-out tree complete, and can a plain program read its longest file?"""
    status = run_command(["git", "-C", str(dest), "status", "--porcelain"], timeout=300)
    dirty = [ln for ln in (status.get("_text") or "").splitlines() if ln.strip()]
    target = Path(dest) / longest_rel
    readable, read_error = False, None
    try:
        with open(target, "rb") as handle:  # noqa: PTH123 — the point is the plain call
            handle.read(1)
        readable = True
    except OSError as exc:
        read_error = f"{type(exc).__name__}: errno {exc.errno}"
    return {
        "git_status_dirty_lines": len(dirty),
        "longest_file_full_path_chars": len(str(target)),
        "longest_file_readable_by_plain_open": readable,
        "longest_file_read_error": read_error,
    }


def classify_clone(record: dict[str, Any], health: dict[str, Any]) -> str:
    if record["status"] != STATUS_PASS or record["filename_too_long_errors"]:
        return STATUS_FAIL
    if health["git_status_dirty_lines"] or not health["longest_file_readable_by_plain_open"]:
        return STATUS_CAVEATED
    return STATUS_PASS


# ------------------------------------------------------- the empirical clone threshold


def probe_root_default(repo: Path) -> Path:
    drive = os.path.splitdrive(str(repo.absolute()))[0]
    return Path((drive or "") + os.sep + "_mlp")


def threshold_probe(
    source: Path,
    probe_root: Path,
    longest_rel: str,
    *,
    longpaths: bool,
    lo: int,
    hi: int,
    timeout: int,
) -> dict[str, Any]:
    """Binary-search the shortest destination length at which the clone stops working.

    A length "works" when git reports no `Filename too long`, the tree is clean, and the
    longest file can be opened by a plain `open()` — because a checkout no other program
    can read is not a checkout a judge can use.
    """
    probes: list[dict[str, Any]] = []
    memo: dict[int, dict[str, Any]] = {}
    root = str(probe_root).rstrip("\\/")
    floor = len(root) + 2  # root + separator + one character

    def dest_for(length: int) -> Path:
        pad = length - len(root) - 1
        return Path(root) / ("d" * pad)

    def works(length: int) -> dict[str, Any]:
        if length in memo:
            return memo[length]
        dest = dest_for(length)
        record = clone_once(source, dest, longpaths=longpaths, timeout=timeout)
        health = tree_health(dest, longest_rel) if record["status"] == STATUS_PASS else {}
        ok = record["status"] == STATUS_PASS and not record["filename_too_long_errors"]
        usable = bool(ok and health.get("longest_file_readable_by_plain_open"))
        probe = {
            "dest_chars": length,
            "clone_exit_code": record["exit_code"],
            "filename_too_long_errors": record["filename_too_long_errors"],
            "checkout_failed": record["checkout_failed"],
            "duration_s": record["duration_s"],
            "git_checkout_complete": ok,
            "longest_file_readable": health.get("longest_file_readable_by_plain_open"),
            "git_status_dirty_lines": health.get("git_status_dirty_lines"),
        }
        probes.append(probe)
        force_rmtree(dest)
        memo[length] = {"probe": probe, "git_ok": ok, "usable": usable}
        return memo[length]

    def bisect(predicate: str) -> dict[str, Any]:
        """Largest length satisfying ``predicate``, and the smallest that does not.

        Both bounds are probed first, so a range in which nothing fails is reported as
        "no failure observed up to N" rather than as a fabricated boundary.
        """
        if not works(lo)[predicate]:
            return {
                "max_ok_dest_chars": None,
                "first_failing_dest_chars": lo,
                "note": f"the shortest destination tested ({lo} chars) already fails",
            }
        if works(hi)[predicate]:
            return {
                "max_ok_dest_chars": hi,
                "first_failing_dest_chars": None,
                "no_failure_observed_up_to": hi,
            }
        low, high = lo, hi  # invariant: low satisfies, high does not
        while high - low > 1:
            mid = (low + high) // 2
            if works(mid)[predicate]:
                low = mid
            else:
                high = mid
        return {"max_ok_dest_chars": low, "first_failing_dest_chars": high}

    lo = max(lo, floor)
    result: dict[str, Any] = {
        "variant": "core.longpaths=true" if longpaths else "as documented (no flags)",
        "search_range": [lo, hi],
        "predicates": {
            "git_ok": "git clone exited 0 with no `Filename too long` and a clean tree",
            "usable": "git_ok AND a plain open() can read the longest tracked file",
        },
    }

    git_search = bisect("git_ok")
    result["max_working_dest_chars"] = git_search["max_ok_dest_chars"]
    result["first_failing_dest_chars"] = git_search["first_failing_dest_chars"]
    if "no_failure_observed_up_to" in git_search:
        result["no_failure_observed_up_to"] = git_search["no_failure_observed_up_to"]
    if "note" in git_search:
        result["note"] = git_search["note"]

    # Second, independent threshold: where the tree stops being READABLE by a program
    # that has not opted into long paths. With core.longpaths=true git will happily
    # create files that nothing else on the machine can open.
    read_search = bisect("usable")
    result["max_readable_dest_chars"] = read_search["max_ok_dest_chars"]
    result["min_unreadable_dest_chars"] = read_search["first_failing_dest_chars"]
    if "no_failure_observed_up_to" in read_search:
        result["no_unreadable_tree_observed_up_to"] = read_search["no_failure_observed_up_to"]

    result["probes_taken"] = len(probes)
    result["probes"] = sorted(probes, key=lambda p: p["dest_chars"])
    return result


def probe_thresholds(
    source: Path, probe_root: Path, longest_rel: str, lo: int, hi: int, timeout: int
) -> dict[str, Any]:
    created = not probe_root.exists()
    probe_root.mkdir(parents=True, exist_ok=True)
    try:
        plain = threshold_probe(
            source, probe_root, longest_rel, longpaths=False, lo=lo, hi=hi, timeout=timeout
        )
        flagged = threshold_probe(
            source, probe_root, longest_rel, longpaths=True, lo=lo, hi=hi, timeout=timeout
        )
    finally:
        if created:
            force_rmtree(probe_root)
    return {
        "method": (
            "real `git clone` into destinations of increasing length under a short probe "
            "root, binary-searched; every probe is kept below"
        ),
        "probe_root": probe_root.as_posix(),
        "longest_tracked_path": longest_rel,
        "longest_tracked_path_chars": len(longest_rel),
        "without_longpaths": plain,
        "with_longpaths": flagged,
    }


# ----------------------------------------------------------------------- interpreters


PROBE_SOURCE = r"""
import importlib.util, json, sys
def where(name):
    try:
        spec = importlib.util.find_spec(name)
    except Exception as exc:          # a broken install is a finding, not a crash
        return {"importable": False, "error": type(exc).__name__ + ": " + str(exc)}
    if spec is None:
        return {"importable": False, "error": "not found"}
    return {"importable": True, "origin": spec.origin}
print(json.dumps({
    "version": sys.version.split()[0],
    "executable": sys.executable,
    "psycopg": where("psycopg"),
    "pytest": where("pytest"),
    "trappoint_core": where("trappoint_core"),
    "trappoint_migrate": where("trappoint_migrate"),
}))
"""


def probe_interpreter(python: str, label: str, clone: Path | None) -> dict[str, Any]:
    resolved = shutil.which(python) or python
    block: dict[str, Any] = {"label": label, "requested": python, "resolved": resolved}
    out = run_command([python, "-c", PROBE_SOURCE], cwd=clone, timeout=180)
    if out["status"] != STATUS_PASS:
        block["usable"] = False
        block["reason"] = out.get("reason") or f"probe exited {out['exit_code']}"
        block["probe_output"] = out["output"]
        return block
    try:
        payload = json.loads((out.get("_text") or "").strip().splitlines()[-1])
    except (ValueError, IndexError) as exc:
        block["usable"] = False
        block["reason"] = f"probe produced no JSON: {exc}"
        return block
    block["usable"] = True
    block.update(payload)
    if clone is not None:
        clone_str = str(Path(clone).absolute()).replace("\\", "/").lower()
        outside = []
        for name in ("trappoint_core", "trappoint_migrate", "pytest"):
            origin = (payload.get(name) or {}).get("origin")
            if origin and clone_str not in origin.replace("\\", "/").lower():
                outside.append({"module": name, "origin": origin})
        block["modules_resolved_outside_the_clone"] = outside
    return block


def default_interpreters(repo: Path) -> list[tuple[str, str]]:
    """(`python` as a judge types it) then (the workspace venv) when one exists."""
    chosen: list[tuple[str, str]] = []
    on_path = shutil.which("python") or shutil.which("python3")
    if on_path:
        chosen.append((on_path, "python-on-PATH (what a judge types)"))
    venv = repo / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if venv.exists() and str(venv) != on_path:
        chosen.append((str(venv), "workspace venv (the state after `just setup`)"))
    if not chosen:
        chosen.append((sys.executable, "the interpreter running this script"))
    return chosen


# ------------------------------------------------------------------------- the steps


def documented_commands_block(clone: Path) -> dict[str, Any]:
    """What the front door promises, and whether it still literally says so."""

    def text_of(path: Path) -> str:
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8", errors="replace")

    readme = text_of(clone / "README.md")
    quickstart = text_of(clone / "docs" / "release" / "QUICKSTART.md")
    just_path = shutil.which("just")
    rows = []
    for command, fallback in DOCUMENTED:
        rows.append(
            {
                "documented": command,
                "in_readme": command in readme,
                "in_quickstart": command in quickstart,
                "runnable_here": just_path is not None,
                "reason": None if just_path else "`just` is not on PATH on this machine",
                "fallback_actually_run": fallback,
            }
        )
    return {
        "readme_present_in_clone": bool(readme),
        "quickstart_present_in_clone": bool(quickstart),
        "just_on_path": just_path,
        "commands": rows,
    }


def build_steps(
    python: str, *, dsn: str | None, database: str, skip_cluster: bool
) -> list[dict[str, Any]]:
    """The ordered list of what a judge types, before any of it is executed."""
    proof_argv = [python, "scripts/proof/gate_refusal.py"]
    if dsn:
        proof_argv += ["--dsn", dsn, "--database", database]
    return [
        {
            "id": "doctor",
            "documented_as": "just doctor",
            "typed": f"{Path(python).name} scripts/qa/doctor.py",
            "requires": "scripts/qa/doctor.py",
            "argv": [python, "scripts/qa/doctor.py"],
            "timeout_s": 600,
            "expect": "one table, and exit 0 only when everything `just prove` needs is present",
            "nonzero_expected_because": (
                "`uv` and `just` are not installed on this machine, so the doctor is RIGHT to "
                "exit 1. That is a finding about the host, not a defect of the clone — and it "
                "is exactly what the doctor exists to say."
            ),
        },
        {
            "id": "compose-config",
            "documented_as": "just up",
            "typed": "docker compose -f compose.yaml config",
            "requires": "compose.yaml",
            "argv": ["docker", "compose", "-f", "compose.yaml", "config"],
            "timeout_s": 300,
            "expect": "exit 0; the compose file in the clone parses and pins the image",
        },
        {
            "id": "gate-refusal",
            "documented_as": "just prove",
            "typed": (
                f"{Path(python).name} scripts/proof/gate_refusal.py --dsn ... --database {database}"
            ),
            "requires": "scripts/proof/gate_refusal.py",
            "argv": proof_argv,
            "timeout_s": 1800,
            "expect": "exit 0 and VERDICT PROVEN",
            "skip": (
                "--skip-cluster was given: no database was contacted, so the central claim "
                "is UNTESTED by this run"
            )
            if skip_cluster or not dsn
            else None,
        },
        {
            "id": "pytest-collect",
            "documented_as": "just test",
            "typed": f"{Path(python).name} -m pytest --crdb=none --collect-only -q",
            "requires": "conftest.py",
            "argv": [python, "-m", "pytest", "--crdb=none", "--collect-only", "-q"],
            "timeout_s": 1800,
            "expect": "exit 0; the suite collects with no collection errors",
        },
        {
            "id": "check-reuse",
            "documented_as": ".github/workflows/ci.yml job `checkers`",
            "typed": f"{Path(python).name} scripts/qa/check_reuse.py",
            "requires": "scripts/qa/check_reuse.py",
            "argv": [python, "scripts/qa/check_reuse.py"],
            "timeout_s": 600,
            "expect": "present and exit 0; CI names this exact path",
        },
    ]


def execute_steps(
    steps: list[dict[str, Any]],
    clone: Path,
    env: dict[str, str],
    interpreter: dict[str, Any],
) -> None:
    """Run each step in the clone, in order, mutating it in place. Never fabricates."""
    # `just setup` is the second of the four documented commands. An interpreter that has
    # not had it run against it cannot import the workspace, so the proof and the suite
    # are EXPECTED to fail there — and saying so is the whole point of running both.
    workspace_installed = bool((interpreter.get("trappoint_migrate") or {}).get("importable"))
    if not workspace_installed:
        for step in steps:
            if step["id"] in ("gate-refusal", "pytest-collect"):
                step["nonzero_expected_because"] = (
                    "`trappoint_migrate` is not importable by this interpreter, so the "
                    "workspace has never been installed into it. `just setup` "
                    "(`uv sync --all-packages`) is the second of the four documented "
                    "commands; a judge who skips it lands exactly here."
                )

    for step in steps:
        required = clone / step["requires"]
        if step.get("skip"):
            step["status"] = STATUS_SKIPPED
            step["reason"] = step.pop("skip")
            continue
        step.pop("skip", None)
        if not required.exists():
            step["status"] = STATUS_NOT_PRESENT
            step["reason"] = f"{step['requires']} is not in the clone"
            continue
        result = run_command(step["argv"], cwd=clone, timeout=step["timeout_s"], env=env)
        step["status"] = result["status"]
        step["exit_code"] = result["exit_code"]
        step["duration_s"] = result["duration_s"]
        step["output"] = result["output"]
        if "reason" in result:
            step["reason"] = result["reason"]
        text = result.get("_text") or ""
        if step["id"] == "gate-refusal":
            step["verdict_line"] = next(
                (ln.strip() for ln in text.splitlines() if ln.startswith("VERDICT")), None
            )
            step["chain_line"] = next(
                (ln.strip() for ln in text.splitlines() if ln.startswith("chain")), None
            )
            step["refusal_lines"] = [
                ln.strip()
                for ln in text.splitlines()
                if ln.startswith(("REFUSAL", "DRIFT", "ADMISSION"))
            ]
        if step["id"] == "pytest-collect":
            step["summary_line"] = next(
                (
                    ln.strip()
                    for ln in reversed(text.splitlines())
                    if "test" in ln and ("collected" in ln or "error" in ln)
                ),
                None,
            )
        # An expected non-zero stays FAIL. Renaming it PASS would be the one move this
        # repository refuses; what it gets instead is a reason and exemption from the
        # process exit code.
        if step["status"] == STATUS_FAIL and step.get("nonzero_expected_because"):
            step["expected_failure"] = True


# ------------------------------------------------------------------------- the verdict


def derive_findings(document: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []

    def add(severity: str, headline: str, detail: str) -> None:
        findings.append({"severity": severity, "headline": headline, "detail": detail})

    threshold = document.get("clone_threshold") or {}
    plain = threshold.get("without_longpaths") or {}
    flagged = threshold.get("with_longpaths") or {}
    if plain.get("first_failing_dest_chars"):
        add(
            "BLOCKING-ON-WINDOWS",
            f"a plain `git clone` fails at a destination of "
            f"{plain['first_failing_dest_chars']} characters",
            f"measured: {plain.get('max_working_dest_chars')} characters works, "
            f"{plain['first_failing_dest_chars']} does not. "
            f"`git clone -c core.longpaths=true` "
            + (
                f"showed no failure up to {flagged.get('no_failure_observed_up_to')} characters"
                if flagged.get("first_failing_dest_chars") is None
                else f"first failed at {flagged.get('first_failing_dest_chars')}"
            )
            + ". The README's copy-paste block must carry the flag.",
        )
    if flagged.get("min_unreadable_dest_chars"):
        add(
            "MAJOR",
            "the clone flag makes git succeed where other programs still cannot read the tree",
            f"with core.longpaths=true a clone at {flagged['min_unreadable_dest_chars']} "
            "characters completes, but the longest fixture then exceeds "
            f"{cpl.WINDOWS_USABLE_PATH} characters and a plain open() raises. "
            f"The tree is fully readable only up to {flagged.get('max_readable_dest_chars')} "
            "characters of destination.",
        )

    source = document.get("source") or {}
    if source.get("working_tree_modified_or_untracked"):
        add(
            "MAJOR",
            f"{source['working_tree_modified_or_untracked']} files on the author's disk are "
            "not in the clone",
            "everything a judge sees is HEAD. Uncommitted work does not exist for them.",
        )
    if source.get("commits_ahead_of_origin"):
        add(
            "BLOCKING",
            f"HEAD is {source['commits_ahead_of_origin']} commits ahead of origin, and "
            f"{source.get('files_differing_from_origin_master')} files differ",
            "this dry run cloned the LOCAL repository. A judge clones the remote, which is "
            "behind it"
            + (
                ", and whose README does not contain the four documented commands"
                if source.get("origin_master_readme_has_the_documented_commands") is False
                else ""
            )
            + ". `git push` before anything measured here is quotable.",
        )

    for run in document.get("runs") or []:
        outside = (run.get("interpreter") or {}).get("modules_resolved_outside_the_clone") or []
        if outside:
            add(
                "CAVEAT",
                f"interpreter {run['interpreter']['label']!r} imports workspace code from "
                "outside the clone",
                "; ".join(f"{o['module']} <- {o['origin']}" for o in outside)
                + ". The SQL and the scripts under test are the clone's; the installed "
                "Python packages are the host's editable installs.",
            )
        for step in run.get("steps") or []:
            if step["status"] in (STATUS_FAIL, STATUS_TIMEOUT):
                add(
                    "EXPECTED-FAILURE" if step.get("expected_failure") else "FAILURE",
                    f"[{run['interpreter']['label']}] {step['typed']} -> {step['status']}"
                    + (f" (exit {step['exit_code']})" if step.get("exit_code") is not None else ""),
                    step.get("nonzero_expected_because")
                    or step.get("reason")
                    or step.get("expect")
                    or "",
                )
            elif step["status"] == STATUS_NOT_PRESENT:
                add(
                    "FAILURE",
                    f"[{run['interpreter']['label']}] {step['requires']} is not in the clone",
                    "a documented command has no file behind it at this commit",
                )
            elif step["status"] == STATUS_SKIPPED:
                add(
                    "SKIP",
                    f"[{run['interpreter']['label']}] {step['typed']} was not run",
                    step.get("reason") or "",
                )

    documented = document.get("documented_commands") or {}
    if documented.get("just_on_path") is None:
        add(
            "MAJOR",
            "`just` is not installed on this machine, so the four documented commands were "
            "not runnable as written",
            "each one was run through the fallback recorded in documented_commands. "
            "`uv` is absent for the same reason, so `just setup` has never been executed "
            "here either.",
        )
    return findings


def derive_verdict(document: dict[str, Any]) -> str:
    proof_steps = [
        step
        for run in document.get("runs") or []
        for step in run.get("steps") or []
        if step["id"] == "gate-refusal"
    ]
    if not proof_steps or all(s["status"] == STATUS_SKIPPED for s in proof_steps):
        return "NOT_RUN"
    passed = [s for s in proof_steps if s["status"] in (STATUS_PASS, STATUS_CAVEATED)]
    if not passed:
        return "NOT_PROVEN"
    proven = [s for s in passed if (s.get("verdict_line") or "").endswith("PROVEN")]
    if not proven:
        return "NOT_PROVEN"
    chain = proven[0].get("chain_line") or ""
    clean = "0 failed" in chain
    return "PROVEN" if clean else "PROVEN_WITH_CAVEATS"


# -------------------------------------------------------------------------------- main


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="judge_dry_run",
        description=(
            "Clone HEAD into a temporary directory and execute, inside it, the exact "
            "commands README.md and docs/release/QUICKSTART.md tell a judge to run."
        ),
    )
    parser.add_argument("--source", type=Path, default=None, help="repository to clone")
    parser.add_argument("--dest", type=Path, default=None, help="where to clone (kept if given)")
    parser.add_argument(
        "--dsn",
        default=os.environ.get("MAINLINE_TEST_DSN") or os.environ.get("TRAPPOINT_DSN"),
        help="admin DSN for the proof, e.g. postgresql://root@127.0.0.1:26257/"
        "defaultdb?sslmode=disable",
    )
    parser.add_argument(
        "--database",
        default=None,
        help="throwaway database name for the proof (default: w_s04_ffm_<8 hex>)",
    )
    parser.add_argument(
        "--skip-cluster",
        action="store_true",
        help="contact no database; the proof step is recorded as a named SKIP, never a pass",
    )
    parser.add_argument(
        "--python",
        action="append",
        default=None,
        help="interpreter to run the steps with; repeatable (default: `python` on PATH, "
        "then the workspace venv if one exists)",
    )
    parser.add_argument(
        "--probe-threshold",
        action="store_true",
        help="binary-search the Windows clone-path failure threshold with real clones",
    )
    parser.add_argument("--probe-root", type=Path, default=None, help="short root for the probe")
    parser.add_argument("--probe-lo", type=int, default=9, help="shortest destination to try")
    parser.add_argument("--probe-hi", type=int, default=140, help="longest destination to try")
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="report path (default: <source>/qa/judge-dry-run.json)",
    )
    parser.add_argument("--keep", action="store_true", help="leave the clone on disk")
    parser.add_argument(
        "--note",
        action="append",
        default=None,
        help="operator note recorded verbatim in the report, e.g. what else the machine "
        "was doing; repeatable",
    )
    return parser


def main(argv: list[str] | None = None) -> int:  # noqa: PLR0912, PLR0915
    survive_a_narrow_console()
    args = build_parser().parse_args(argv)

    source = (args.source or cpl.repo_root_of(Path(__file__).resolve().parent)).resolve()
    if not (source / ".git").exists():
        print(f"judge_dry_run: {source} is not a git repository", file=sys.stderr)
        return EXIT_CANNOT_RUN
    out_path = args.out or (source / "qa" / "judge-dry-run.json")
    database = args.database or f"w_s04_ffm_{uuid.uuid4().hex[:8]}"

    print(f"judge_dry_run: source {source}")
    document: dict[str, Any] = {
        "schema": SCHEMA,
        "generated_utc": now_utc(),
        "generated_by": GENERATED_BY,
        "note": NOTE,
        "status_vocabulary": {
            STATUS_PASS: "executed, exit code 0",
            STATUS_CAVEATED: "executed, but the caveat field says why it means less",
            STATUS_FAIL: "executed, non-zero exit code",
            STATUS_TIMEOUT: "executed, killed at the deadline",
            STATUS_SKIPPED: "deliberately not executed; `reason` names the switch",
            STATUS_NOT_RUN: "could not be executed; a prerequisite was missing",
            STATUS_NOT_PRESENT: "the documented file is not in the clone",
        },
        "host": host_block(),
        "source": source_block(source),
        "operator_notes": list(args.note or []),
    }

    # ---- path-length arithmetic, from the sibling script, budget carried forward
    try:
        paths = cpl.tracked_paths(source)
        lengths = cpl.measure(paths)
        lengths["repo"] = source.as_posix()
        lengths["head"] = document["source"]["head"]
        existing = (cpl.load_report_file(out_path).get("path_lengths") or {}).get("budget")
        budget = dict(existing) if isinstance(existing, dict) else cpl.seed_budget(lengths)
        status, complaints = cpl.enforce(lengths, budget)
        lengths["budget"] = budget
        lengths["budget_status"] = status
        lengths["budget_complaints"] = complaints
        document["path_lengths"] = lengths
        longest_rel = lengths["longest_paths"][0]["path"]
    except cpl.CannotRun as exc:
        print(f"judge_dry_run: {exc}", file=sys.stderr)
        return EXIT_CANNOT_RUN
    print(
        f"judge_dry_run: longest tracked path {lengths['max_tracked_path_chars']} chars; "
        f"arithmetic says a destination may be at most "
        f"{lengths['max_safe_clone_prefix_chars']} chars"
    )

    # ---- the empirical threshold
    if args.probe_threshold:
        root = args.probe_root or probe_root_default(source)
        print(f"judge_dry_run: probing the clone threshold under {root} (real clones, slow)")
        document["clone_threshold"] = probe_thresholds(
            source, root, longest_rel, args.probe_lo, args.probe_hi, timeout=900
        )
        plain = document["clone_threshold"]["without_longpaths"]
        print(
            f"judge_dry_run: without the flag, {plain.get('max_working_dest_chars')} chars "
            f"works and {plain.get('first_failing_dest_chars')} does not"
        )
    else:
        document["clone_threshold"] = {
            "status": STATUS_NOT_RUN,
            "reason": "--probe-threshold was not given",
        }

    # ---- the clone the steps will run in
    attempts: list[dict[str, Any]] = []
    temp_parent: Path | None = None
    if args.dest:
        candidates = [
            (Path(args.dest), False, "as documented, at --dest"),
            (Path(args.dest), True, "core.longpaths=true, at --dest"),
        ]
    else:
        temp_parent = Path(tempfile.mkdtemp(prefix="mainline-judge-"))
        short_root = probe_root_default(source) / "jdr"
        candidates = [
            (temp_parent / "mainline", False, "as documented, in the system temp directory"),
            (temp_parent / "mainline", True, "core.longpaths=true, in the system temp directory"),
            (short_root, False, "as documented, into a destination inside the safe prefix"),
        ]

    clone_used: dict[str, Any] | None = None
    for dest, longpaths, label in candidates:
        if clone_used is not None and clone_used["classification"] == STATUS_PASS:
            break
        print(f"judge_dry_run: cloning -> {label} ({len(str(dest))} chars)")
        record = clone_once(source, dest, longpaths=longpaths)
        health = tree_health(dest, longest_rel) if record["status"] == STATUS_PASS else {}
        record["label"] = label
        record["health"] = health
        record["classification"] = classify_clone(record, health) if health else STATUS_FAIL
        record.pop("_text", None)
        attempts.append(record)
        print(f"judge_dry_run:   {record['classification']} (exit {record['exit_code']})")
        if record["classification"] in (STATUS_PASS, STATUS_CAVEATED):
            if clone_used is None or record["classification"] == STATUS_PASS:
                clone_used = record
        else:
            force_rmtree(dest)

    document["clone_attempts"] = attempts
    if clone_used is None:
        document["clone_used"] = None
        document["runs"] = []
        document["documented_commands"] = {
            "status": STATUS_NOT_RUN,
            "reason": "no clone produced a usable tree",
        }
        document["findings"] = derive_findings(document)
        document["verdict"] = "NOT_RUN"
        document["reproduce"] = reproduce_command(args)
        write_document(out_path, document)
        print("judge_dry_run: NO USABLE CLONE — report written anyway", file=sys.stderr)
        return EXIT_FAILED

    clone = Path(clone_used["dest"])
    document["clone_used"] = {
        "label": clone_used["label"],
        "dest": clone_used["dest"],
        "dest_chars": clone_used["dest_chars"],
        "longpaths": clone_used["longpaths"],
        "classification": clone_used["classification"],
        "health": clone_used["health"],
    }
    print(f"judge_dry_run: running the steps in {clone}")

    document["documented_commands"] = documented_commands_block(clone)

    # ---- the steps, once per interpreter
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)  # the clone must not inherit the author's sys.path
    requested = (
        [(p, f"--python {p}") for p in args.python] if args.python else default_interpreters(source)
    )
    runs: list[dict[str, Any]] = []
    for python, label in requested:
        print(f"judge_dry_run: interpreter {label}")
        interp = probe_interpreter(python, label, clone)
        steps = build_steps(
            python,
            dsn=None if args.skip_cluster else args.dsn,
            database=database,
            skip_cluster=args.skip_cluster,
        )
        if not interp.get("usable"):
            for step in steps:
                step["status"] = STATUS_NOT_RUN
                step["reason"] = f"interpreter unusable: {interp.get('reason')}"
        else:
            execute_steps(steps, clone, env, interp)
        for step in steps:
            print(f"judge_dry_run:   {step['status']:<16} {step['typed']}")
        runs.append({"interpreter": interp, "steps": steps})

    document["runs"] = runs
    document["findings"] = derive_findings(document)
    document["verdict"] = derive_verdict(document)
    document["reproduce"] = reproduce_command(args)
    write_document(out_path, document)

    if not args.keep and not args.dest:
        for record in attempts:
            force_rmtree(Path(record["dest"]))
        if temp_parent is not None:
            force_rmtree(temp_parent)
        short_root_parent = probe_root_default(source)
        with contextlib.suppress(OSError):
            if short_root_parent.exists() and not any(short_root_parent.iterdir()):
                short_root_parent.rmdir()
        document["clone_used"]["removed_after_the_run"] = True
        write_document(out_path, document)

    # An expected non-zero (the doctor on a machine with no `uv` and no `just`) is a
    # finding, not a failure of this instrument, so it does not colour the exit code.
    bad = [
        step
        for run in runs
        for step in run["steps"]
        if step["status"] in (STATUS_FAIL, STATUS_TIMEOUT, STATUS_NOT_PRESENT, STATUS_NOT_RUN)
        and not step.get("expected_failure")
    ]
    print(f"\njudge_dry_run: VERDICT {document['verdict']}")
    for step in bad:
        print(f"judge_dry_run: unexpected {step['status']}: {step['typed']}")
    print(f"judge_dry_run: wrote {out_path}")
    return EXIT_FAILED if bad else EXIT_OK


def reproduce_command(args: argparse.Namespace) -> str:
    parts = ["python scripts/submission/judge_dry_run.py"]
    if args.skip_cluster:
        parts.append("--skip-cluster")
    elif args.dsn:
        parts.append('--dsn "postgresql://root@127.0.0.1:26257/defaultdb?sslmode=disable"')
    if args.probe_threshold:
        parts.append("--probe-threshold")
    return " ".join(parts)


def write_document(path: Path, document: dict[str, Any]) -> None:
    payload = strip_internals(document)
    payload.setdefault("SPDX-FileCopyrightText", "2026 MAINLINE contributors")
    payload.setdefault("SPDX-License-Identifier", "Apache-2.0")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
