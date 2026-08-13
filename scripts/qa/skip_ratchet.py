#!/usr/bin/env python
# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
#
# MI: none — this file makes no database claim. It reads a census of what CI did NOT run.
# I: QA-RATCHET-2 — a test that skips for want of a cluster is either EXECUTED by a named
#    CI lane, or it is on an enumerated `unlanded` list with a reason and an owner, and
#    that list is a ceiling that may only shrink. A cluster-shaped skip that is neither is
#    a hard failure naming the node id.
# RATIONALE: measured 2026-08-13 at HEAD 073dfea, `pytest --crdb=none -m "not (g4alpha or
#    pl2_red)"` over the whole repository reported 988 skips out of 9839 collected, and 974
#    of those 988 name a cluster, a node, a database or a DSN. Fixing that by giving every
#    one of them a lane is a multi-wave programme across eight domain leads. Deleting the
#    tests would be a lie. Marking them `xfail` would exit 0 and say nothing. The fourth
#    option is the honest one and it is the only one that gets smaller by itself: attribute
#    every cluster-shaped skip to the lane that runs it, enumerate the remainder with a
#    reason and an owner, publish both, and refuse an increase. The rule that makes the
#    wave permanent is the FIRST one: after this lands, adding a cluster-backed test that
#    no lane runs fails the build.
"""The skip ratchet: a skipped test can never again read as green.

Consumes `qa/ci-skip-census.json` (schema `mainline.qa.ci-skip-census/1`, written by
`scripts/qa/ci_skip_census.py`) and compares it against `qa/skip-ratchet.json`.

    a cluster-shaped skip attributed to neither a lane nor `unlanded` -> exit 1, by node id
    an `unlanded` count above its ceiling                             -> exit 1, by pattern
    a per-root `skipped` count above its ceiling                      -> exit 1, by root
    a skip with an empty reason                                       -> exit 1, by node id
    a declared cluster lane that no longer starts a node              -> exit 1, by lane
    anything smaller                                                  -> exit 0

The default invocation reads committed files only: no pytest, no cluster, no network.
`--rebaseline` is the one mode that runs anything — it re-derives the lane map by
executing each lane's own pytest argv with `--collect-only`, because PATH-GREPPING CANNOT
ANSWER THAT QUESTION. (The lead's mechanical attempt returned "968 covered / 19 uncovered"
because the substring `verticals` occurs in eleven workflow files; `demo-api/tests/
conftest.py` came back covered by all eleven. Recorded here so it is not tried again.)

Exit codes: 0 clean, 1 ratchet regression, 2 tooling/usage failure.
"""

from __future__ import annotations

import argparse
import json
import re
import shlex
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
BASELINE_PATH = REPO_ROOT / "qa" / "skip-ratchet.json"
CENSUS_PATH = REPO_ROOT / "qa" / "ci-skip-census.json"
WORKFLOWS = REPO_ROOT / ".github" / "workflows"

SCHEMA = "mainline.qa.skip-ratchet/1"
CENSUS_SCHEMA = "mainline.qa.ci-skip-census/1"

# A pytest INVOCATION, in a workflow file read as RAW TEXT. The Contract A lane marker is
# a comment and PyYAML discards comments, so nothing here may go through a YAML parser.
_INVOKE = re.compile(r"(?:(?<=\s)|^)(?:python[0-9.]* -m )?pytest(?=\s)")
_JOB = re.compile(r"^  ([A-Za-z0-9_.-]+):\s*(?:#.*)?$")
# The node is started from a RESOLVED image output — Contract B forbids restating the
# image literal in a workflow — so the CockroachDB tell is the SUBCOMMAND, not the tag.
_NODE = re.compile(r"\bdocker run\b(?=.*\s-d\b)(?=.*start-single-node)")
# A pytest invocation is a SHELL COMMAND, so its first word is a runner. Requiring that is
# what keeps prose out: `ci.yml:736` is the sentence "MEASURED 2026-08-10 on pytest 9.1.1"
# inside a docstring and `release-proof.yml:259` is a quoted string containing "pytest
# exits 0". Both contain the word and neither is an invocation. Measured on this tree, the
# rule admits exactly the 32 real invocations and neither of those two.
_RUNNER = re.compile(r"^(?:python[0-9.]*|uvx?|pytest)$")
_LEADING = re.compile(r"^(?:run:\s*|set\s+-\S+\s*;?\s*|if\s+|!\s*|then\s+|[A-Z_][A-Z0-9_]*=\S+\s+)")
# Everything after one of these belongs to the shell, not to pytest.
_SHELL_BREAK = re.compile(r"\s(?:\||>|>>|2>&1|;|&&)\s|\s(?:\||>|>>|;|&&)$")


# ---------------------------------------------------------------------------------------
# Reading a workflow file as raw text
# ---------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Invocation:
    """One pytest invocation, with the job it sits in and whether a node precedes it."""

    file: str
    line: int
    job: str
    command: str
    node_started_at: tuple[int, ...]

    @property
    def lane(self) -> str:
        return f"{self.file}#{self.job}"

    @property
    def cluster(self) -> bool:
        return bool(self.node_started_at)


def _blocks(lines: list[str]):
    """Yield (start index, joined command) for each backslash-continued shell block."""
    i = 0
    while i < len(lines):
        if i > 0 and lines[i - 1].rstrip().endswith("\\"):
            i += 1
            continue
        chunk = [lines[i].rstrip()]
        j = i
        while chunk[-1].endswith("\\"):
            j += 1
            if j >= len(lines):
                break
            chunk.append(lines[j].rstrip())
        yield i, " ".join(part.rstrip("\\").strip() for part in chunk)
        i = j + 1


def _jobs(lines: list[str]) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    in_jobs = False
    for n, line in enumerate(lines):
        if line.rstrip() == "jobs:":
            in_jobs = True
            continue
        if in_jobs:
            match = _JOB.match(line)
            if match:
                found.append((n, match.group(1)))
    return found


def _is_invocation(command: str) -> bool:
    text = command.strip()
    if not _INVOKE.search(text) or "pip install" in text:
        return False
    while True:
        stripped = _LEADING.sub("", text, count=1)
        if stripped == text:
            break
        text = stripped
    first = text.split(maxsplit=1)[0] if text.split() else ""
    return bool(_RUNNER.match(first))


def scan_workflows(root: Path = WORKFLOWS) -> list[Invocation]:
    """Every pytest invocation in every workflow, with its job and its node, raw text."""
    out: list[Invocation] = []
    for path in sorted(root.glob("*.yml")):
        lines = path.read_text(encoding="utf-8").splitlines()
        jobs = _jobs(lines)
        nodes: list[int] = []
        calls: list[tuple[int, str]] = []
        for i, command in _blocks(lines):
            if _NODE.search(command):
                nodes.append(i)
            if _is_invocation(command):
                calls.append((i, command))
        for i, command in calls:
            start, end, name = 0, len(lines), "<top-level>"
            for k, (at, job_name) in enumerate(jobs):
                if at <= i:
                    start, name = at, job_name
                    end = jobs[k + 1][0] if k + 1 < len(jobs) else len(lines)
                else:
                    break
            before = tuple(n + 1 for n in nodes if start <= n < end and n < i)
            out.append(Invocation(path.name, i + 1, name, command, before))
    return out


# ---------------------------------------------------------------------------------------
# Patterns. Three explicit forms, no glob subtleties, so a reader can predict every match.
# ---------------------------------------------------------------------------------------
def matches(pattern: str, nodeid: str) -> bool:
    """`dir/**` -> any node id under that directory. `file.py::*` -> that file. Else exact."""
    if pattern.endswith("/**"):
        return nodeid.startswith(pattern[:-2])
    if pattern.endswith("::*"):
        return nodeid.split("::", 1)[0] == pattern[:-3]
    return nodeid == pattern


def pattern_for_target(target: str) -> str:
    """Turn one pytest positional argument into the pattern its lane therefore reaches."""
    if "::" in target:
        return target
    if (REPO_ROOT / target).is_dir():
        return f"{target}/**"
    return f"{target}::*"


# ---------------------------------------------------------------------------------------
# The census
# ---------------------------------------------------------------------------------------
@dataclass
class Census:
    raw: dict[str, Any]
    path: Path

    @property
    def skips(self) -> list[dict[str, Any]]:
        skips: list[dict[str, Any]] = self.raw["skips"]
        return skips

    @property
    def cluster_shaped(self) -> list[dict[str, Any]]:
        return [s for s in self.skips if s.get("cluster_shaped")]

    def roots_skipped(self) -> dict[str, int]:
        return {root: int(v.get("skipped", 0)) for root, v in self.raw.get("roots", {}).items()}


def load_census(path: Path) -> Census:
    if not path.is_file():
        msg = (
            f"census not found: {path}. It is written by `python scripts/qa/ci_skip_census.py`, "
            "which runs ci.yml's own hermetic argv and records one entry per skipped test."
        )
        raise RuntimeError(msg)
    raw = json.loads(path.read_text(encoding="utf-8"))
    if raw.get("schema") != CENSUS_SCHEMA:
        msg = f"{path} declares schema {raw.get('schema')!r}; this ratchet reads {CENSUS_SCHEMA!r}"
        raise RuntimeError(msg)
    for key in ("skips", "roots", "collected", "skipped", "deselected"):
        if key not in raw:
            msg = f"{path} carries no `{key}`; it cannot be ratcheted"
            raise RuntimeError(msg)
    return Census(raw, path)


# ---------------------------------------------------------------------------------------
# The verdict
# ---------------------------------------------------------------------------------------
@dataclass
class Verdict:
    failures: list[str] = field(default_factory=list)
    improvements: list[str] = field(default_factory=list)
    lines: list[str] = field(default_factory=list)


def cluster_lane_patterns(baseline: dict[str, Any]) -> dict[str, list[str]]:
    """{lane: patterns} for lanes that actually stand a node up. Others attribute nothing."""
    return {
        lane: list(entry.get("patterns", []))
        for lane, entry in baseline.get("lanes", {}).items()
        if entry.get("cluster")
    }


def check_lanes_still_exist(baseline: dict[str, Any], verdict: Verdict) -> None:
    """A declared lane that no longer starts a node attributes nothing and must say so.

    Without this, deleting `cluster-tests.yml` would leave 187 demo-api skips attributed to
    a job that no longer exists — the ratchet would keep reporting them as executed. The
    check is raw text and costs nothing.
    """
    live: dict[str, list[Invocation]] = {}
    for call in scan_workflows():
        live.setdefault(call.lane, []).append(call)
    for lane, entry in sorted(baseline.get("lanes", {}).items()):
        calls = live.get(lane, [])
        if not calls:
            verdict.failures.append(
                f"LANE GONE            {lane}: no pytest invocation in that workflow's job. "
                f"{len(entry.get('patterns', []))} pattern(s) were attributed to it."
            )
            continue
        if entry.get("cluster") and not any(c.cluster for c in calls):
            verdict.failures.append(
                f"LANE LOST ITS NODE   {lane}: declared `cluster: true`, but no "
                "`docker run -d … start-single-node` precedes its pytest step in that job. "
                "Every skip attributed to it is now unexecuted and unattributed."
            )


def attribute(census: Census, baseline: dict[str, Any], verdict: Verdict) -> None:
    """Rule (a) and rule (d): every cluster-shaped skip is landed, unlanded, or a failure."""
    lanes = cluster_lane_patterns(baseline)
    unlanded_patterns = [u["pattern"] for u in baseline.get("unlanded", [])]

    for skip in census.skips:
        if not (skip.get("reason") or "").strip():
            verdict.failures.append(
                f"SKIP WITH NO REASON  {skip['nodeid']}: a skip with no reason is "
                "indistinguishable from a deleted test. `pytest.skip(reason=…)` is not "
                "optional here, at any count."
            )

    landed: dict[str, int] = dict.fromkeys(lanes, 0)
    unlanded_counts: dict[str, int] = dict.fromkeys(unlanded_patterns, 0)
    orphans: list[str] = []

    attributed = 0
    for skip in census.cluster_shaped:
        nodeid = skip["nodeid"]
        # Counted against EVERY lane that reaches it, not the first one matched: two lanes
        # do run it, and reporting 116 for a lane that executes 187 understates the cover.
        hits = [ln for ln, pats in lanes.items() if any(matches(p, nodeid) for p in pats)]
        if hits:
            attributed += 1
            for lane in hits:
                landed[lane] += 1
            continue
        pattern = next((p for p in unlanded_patterns if matches(p, nodeid)), None)
        if pattern:
            unlanded_counts[pattern] += 1
            continue
        orphans.append(nodeid)

    for nodeid in orphans:
        verdict.failures.append(
            f"UNATTRIBUTED SKIP    {nodeid}: this test skips for want of a cluster and NO "
            "CI lane runs it. Point a lane at it, or add it to `unlanded` in "
            "qa/skip-ratchet.json with a reason and an owner. A cluster-backed test that no "
            "lane executes reads exactly like a passing one on the Actions tab."
        )

    verdict.lines.append(
        f"cluster-shaped skips {len(census.cluster_shaped)}  ->  "
        f"{attributed} executed by {sum(1 for v in landed.values() if v)} lane(s)  ·  "
        f"{sum(unlanded_counts.values())} unlanded  ·  {len(orphans)} unattributed"
    )
    for lane, n in sorted(landed.items(), key=lambda kv: -kv[1]):
        verdict.lines.append(f"    executed {n:4d}  {lane}")

    _ratchet_unlanded(baseline, unlanded_counts, verdict)


def _ratchet_unlanded(baseline: dict[str, Any], measured: dict[str, int], verdict: Verdict) -> None:
    """Rule (b): the unlanded total is a ceiling, and so is every pattern's own count."""
    total = 0
    for entry in baseline.get("unlanded", []):
        pattern = entry["pattern"]
        recorded = int(entry.get("count", 0))
        now = measured.get(pattern, 0)
        total += now
        if now > recorded:
            verdict.failures.append(
                f"UNLANDED ROSE        {pattern}: ceiling {recorded}, measured {now} "
                f"(+{now - recorded}). Owner {entry.get('owner', '?')}. The unlanded list is "
                "a ceiling: it may fall, it may not rise."
            )
        elif now < recorded:
            verdict.improvements.append(
                f"unlanded fell        {pattern}: ceiling {recorded}, measured {now} "
                f"(-{recorded - now}); tighten with --update"
            )
    ceiling = int(baseline.get("unlanded_ceiling", 0))
    if total > ceiling:
        verdict.failures.append(
            f"UNLANDED TOTAL ROSE  ceiling {ceiling}, measured {total} (+{total - ceiling})"
        )
    elif total < ceiling:
        verdict.improvements.append(
            f"unlanded total fell  ceiling {ceiling}, measured {total} (-{ceiling - total})"
        )
    verdict.lines.append(f"unlanded total {total} against a ceiling of {ceiling}")


def ratchet_roots(census: Census, baseline: dict[str, Any], verdict: Verdict) -> None:
    """Rule (c): `skipped` per test root is a ceiling too, so a regression is attributable."""
    recorded = {k: int(v) for k, v in baseline.get("roots", {}).items()}
    measured = census.roots_skipped()
    for root in sorted(set(recorded) | set(measured)):
        was, now = recorded.get(root, 0), measured.get(root, 0)
        if now > was:
            verdict.failures.append(
                f"ROOT SKIPS ROSE      {root}: ceiling {was}, measured {now} (+{now - was})"
                + ("  [HARD GATE: ceiling is 0]" if was == 0 else "")
            )
        elif now < was:
            verdict.improvements.append(
                f"root skips fell      {root}: ceiling {was}, measured {now} (-{was - now})"
            )


def ratchet_totals(census: Census, baseline: dict[str, Any], verdict: Verdict) -> None:
    """The headline counts, so a repository-wide rise is named even if no root moved."""
    recorded = baseline.get("totals", {})
    for key in ("skipped", "cluster_shaped"):
        was = int(recorded.get(key, 0))
        now = len(census.cluster_shaped) if key == "cluster_shaped" else int(census.raw["skipped"])
        if now > was:
            verdict.failures.append(
                f"TOTAL ROSE           {key}: ceiling {was}, measured {now} (+{now - was})"
            )
        elif now < was:
            verdict.improvements.append(
                f"total fell           {key}: ceiling {was}, measured {now} (-{was - now})"
            )


# ---------------------------------------------------------------------------------------
# --rebaseline: the only mode that runs anything
# ---------------------------------------------------------------------------------------
def _pytest_targets(
    command: str, workflow: str, expansions: dict[str, str]
) -> tuple[list[str], bool]:
    """Positional path arguments of a pytest command, and whether a filter narrows them."""
    found = _INVOKE.search(command)
    if found is None:  # pragma: no cover - callers filter with _is_invocation first
        return [], False
    tail = command[found.end() :]
    broken = _SHELL_BREAK.search(tail)
    if broken:
        tail = tail[: broken.start()]
    tail = re.sub(r"\$\{\{\s*([^}]+?)\s*\}\}", r"${{\1}}", tail)
    # shlex, not `.split()`: `-m "not (${RED_SELECTOR})"` is ONE argument, and splitting on
    # whitespace leaves `(${RED_SELECTOR})` looking like a positional target.
    try:
        tokens = shlex.split(tail, posix=True)
    except ValueError:
        tokens = tail.replace('"', " ").replace("'", " ").split()
    targets: list[str] = []
    filtered = False
    skip_next = False
    for token in tokens:
        if skip_next:
            skip_next = False
            continue
        if token in {"-m", "-k", "--deselect", "--ignore", "-p", "-o", "-c", "--rootdir"}:
            filtered = filtered or token in {"-m", "-k", "--deselect", "--ignore"}
            skip_next = True
            continue
        if token.startswith("-"):
            continue
        if token.startswith("$") or "${" in token:
            expanded = expansions.get(f"{workflow}:{token}")
            if expanded is None:
                msg = (
                    f"unexpanded variable {token!r} in a pytest invocation in {workflow}. A "
                    "target this script cannot resolve cannot be attributed to a lane, and "
                    "GUESSING is how the lead's path-grep produced '968 covered'. Add "
                    f"`{workflow}:{token}` to `expansions` in qa/skip-ratchet.json, with the "
                    "file and line you read its value from."
                )
                raise RuntimeError(msg)
            targets.extend(expanded.split())
            continue
        if "/" in token or token.endswith(".py"):
            targets.append(token)
    return targets, filtered


def _collect(targets: list[str], extra: list[str]) -> list[str]:
    """Run `--collect-only -q` and return repo-relative node ids.

    `--rootdir=.` is a NORMALISATION, not a change of scope: pytest names a node id
    relative to the rootdir it discovers, and a nested `pyproject.toml` moves that rootdir
    (measured: `pytest verticals/mainline/apps/demo-api/tests --collect-only -q` names
    `tests/test_reads.py::…` while the whole-repository run the census takes names
    `verticals/mainline/apps/demo-api/tests/test_reads.py::…`). Measured on four targets,
    the collected COUNT is identical with and without it; only the prefix changes.
    """
    argv = [
        sys.executable,
        "-m",
        "pytest",
        *targets,
        *extra,
        "--crdb=none",
        "--collect-only",
        "-q",
        "-p",
        "no:cacheprovider",
        "--rootdir=.",
    ]
    proc = subprocess.run(argv, cwd=str(REPO_ROOT), capture_output=True, check=False)
    if proc.returncode not in (0, 5):
        detail = proc.stdout.decode("utf-8", errors="replace")[-800:]
        msg = f"collection failed (exit {proc.returncode}) for {' '.join(targets)}:\n{detail}"
        raise RuntimeError(msg)
    ids = []
    for line in proc.stdout.decode("utf-8", errors="replace").splitlines():
        text = line.strip()
        if "::" in text and not text.startswith(("=", "-", "E ", "SKIP", "ERROR", "no tests")):
            ids.append(text.replace("\\", "/"))
    return ids


def measure_lanes(expansions: dict[str, str]) -> dict[str, dict[str, Any]]:
    """Lift every lane's own pytest argv and RUN it, because path-grepping cannot answer.

    Only a lane that stands a node up is collected: a lane with no node executes no
    cluster-backed test whatever its argv says, so its reach cannot attribute a skip and
    measuring it would be a number with nothing behind it. Its argv is still recorded, so
    the day somebody adds a `docker run` to that job the lane is already named here.
    """
    lanes: dict[str, dict[str, Any]] = {}
    for call in scan_workflows():
        targets, filtered = _pytest_targets(call.command, call.file, expansions)
        entry = lanes.setdefault(
            call.lane, {"cluster": False, "invocations": [], "patterns": [], "reaches": 0}
        )
        entry["cluster"] = entry["cluster"] or call.cluster
        entry["invocations"].append(
            {
                "line": call.line,
                "argv": call.command,
                "node_started_at": list(call.node_started_at),
                "targets": targets,
                "narrowed_by_a_filter": filtered,
            }
        )
        if not (call.cluster and targets):
            continue
        reached = _collect(targets, _filter_args(call.command))
        entry["reaches"] = max(entry["reaches"], len(reached))
        # A filter means the targets do NOT imply the reach, so the reach is the measured
        # node ids and nothing wider. `schema.yml#unweld` runs `unweld -m schema` and
        # reaches 4 of that directory's tests; a `unweld/**` pattern would claim them all.
        new = reached if filtered else [pattern_for_target(t) for t in targets]
        entry["patterns"] = sorted({*entry["patterns"], *new})
    for entry in lanes.values():
        if not entry["cluster"]:
            entry["note"] = (
                "no `docker run -d … start-single-node` precedes a pytest step in this job, "
                "so this lane executes no cluster-backed test and attributes nothing."
            )
    return lanes


def _filter_args(command: str) -> list[str]:
    """Re-emit the `-m` expression of a lane so its collection is the lane's collection."""
    match = re.search(r"-m\s+(\"[^\"]+\"|'[^']+'|\S+)", command)
    if not match:
        return []
    return ["-m", match.group(1).strip("\"'")]


# ---------------------------------------------------------------------------------------
# I/O
# ---------------------------------------------------------------------------------------
def load_baseline(path: Path) -> dict[str, Any]:
    if not path.is_file():
        msg = f"baseline not found: {path}. Create it with --rebaseline."
        raise RuntimeError(msg)
    doc: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    if doc.get("schema") != SCHEMA:
        msg = f"{path} declares schema {doc.get('schema')!r}; this script writes {SCHEMA!r}"
        raise RuntimeError(msg)
    return doc


def write_baseline(path: Path, doc: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def rebaseline(census: Census, previous: dict[str, Any], path: Path) -> int:
    expansions = previous.get("expansions", {})
    lanes = measure_lanes({k: v["value"] for k, v in expansions.items()})
    attributed = {ln: e["patterns"] for ln, e in lanes.items() if e.get("cluster")}
    unlanded_counts: dict[str, int] = {}
    orphans: list[str] = []
    for skip in census.cluster_shaped:
        nodeid = skip["nodeid"]
        if any(matches(p, nodeid) for pats in attributed.values() for p in pats):
            continue
        pattern = next(
            (u["pattern"] for u in previous.get("unlanded", []) if matches(u["pattern"], nodeid)),
            None,
        )
        if pattern is None:
            orphans.append(nodeid)
            continue
        unlanded_counts[pattern] = unlanded_counts.get(pattern, 0) + 1
    if orphans:
        print(
            f"skip_ratchet: {len(orphans)} cluster-shaped skip(s) match no lane and no "
            "`unlanded` pattern. --rebaseline will NOT invent an entry for them: a pattern "
            "with no reason and no owner is the suppression this ratchet exists to refuse. "
            "Add them to `unlanded` by hand, with a reason and an owner, then re-run.",
        )
        for nodeid in orphans[:20]:
            print(f"    {nodeid}")
        if len(orphans) > 20:
            print(f"    … and {len(orphans) - 20} more")
        return 1

    doc = dict(previous)
    doc["schema"] = SCHEMA
    doc["generated_utc"] = datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    doc["generated_by"] = "scripts/qa/skip_ratchet.py --rebaseline"
    doc["census"] = {
        "path": census.path.relative_to(REPO_ROOT).as_posix(),
        "schema": CENSUS_SCHEMA,
        "generated_utc": census.raw.get("generated_utc"),
        "argv": census.raw.get("argv"),
    }
    doc["totals"] = {
        "collected": int(census.raw["collected"]),
        "skipped": int(census.raw["skipped"]),
        "cluster_shaped": len(census.cluster_shaped),
        "other_skips": int(census.raw["skipped"]) - len(census.cluster_shaped),
        "deselected": int(census.raw["deselected"]),
    }
    doc["roots"] = dict(sorted(census.roots_skipped().items()))
    doc["lanes"] = {lane: lanes[lane] for lane in sorted(lanes)}
    doc["unlanded"] = [
        {**entry, "count": unlanded_counts.get(entry["pattern"], 0)}
        for entry in previous.get("unlanded", [])
    ]
    doc["unlanded_ceiling"] = sum(unlanded_counts.values())
    write_baseline(path, doc)
    print(
        f"skip_ratchet: wrote {path} — {doc['unlanded_ceiling']} unlanded, "
        f"{doc['totals']['cluster_shaped']} cluster-shaped skips."
    )
    return 0


def tighten(baseline: dict[str, Any], census: Census, path: Path) -> int:
    """--update: lower every ceiling to what was measured. It never raises one."""
    lanes = cluster_lane_patterns(baseline)
    counts: dict[str, int] = {}
    for skip in census.cluster_shaped:
        nodeid = skip["nodeid"]
        if any(matches(p, nodeid) for pats in lanes.values() for p in pats):
            continue
        for entry in baseline.get("unlanded", []):
            if matches(entry["pattern"], nodeid):
                counts[entry["pattern"]] = counts.get(entry["pattern"], 0) + 1
                break
    for entry in baseline.get("unlanded", []):
        entry["count"] = min(int(entry.get("count", 0)), counts.get(entry["pattern"], 0))
    baseline["unlanded_ceiling"] = min(
        int(baseline.get("unlanded_ceiling", 0)), sum(counts.values())
    )
    measured_roots = census.roots_skipped()
    baseline["roots"] = {
        root: min(int(was), measured_roots.get(root, 0))
        for root, was in baseline.get("roots", {}).items()
    }
    totals = baseline.setdefault("totals", {})
    totals["skipped"] = min(int(totals.get("skipped", 0)), int(census.raw["skipped"]))
    totals["cluster_shaped"] = min(int(totals.get("cluster_shaped", 0)), len(census.cluster_shaped))
    baseline["generated_utc"] = datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    write_baseline(path, baseline)
    print(f"skip_ratchet: tightened {path}")
    return 0


def report(baseline: dict[str, Any], census: Census) -> int:
    print(
        f"census      {census.path.relative_to(REPO_ROOT).as_posix()}  "
        f"taken {census.raw.get('generated_utc')}"
    )
    print(f"collected   {census.raw['collected']}")
    print(f"skipped     {census.raw['skipped']}  ({len(census.cluster_shaped)} cluster-shaped)")
    print("\nlanes that stand a node up:")
    for lane, entry in sorted(baseline.get("lanes", {}).items()):
        if not entry.get("cluster"):
            continue
        print(f"  {lane}")
        for inv in entry.get("invocations", []):
            print(f"      argv  {inv['argv'][:120]}")
    print("\nunlanded, by ceiling:")
    for entry in sorted(baseline.get("unlanded", []), key=lambda e: -int(e.get("count", 0))):
        print(f"  {int(entry.get('count', 0)):5d}  {entry['pattern']}")
        print(f"         owner {entry.get('owner', '?')} — {entry.get('reason', '')}")
    print(f"\n  total {baseline.get('unlanded_ceiling', 0)}")
    return 0


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="skip_ratchet",
        description="Every cluster-shaped skip is attributed to a lane or to a shrinking list.",
    )
    parser.add_argument("--census", type=Path, default=CENSUS_PATH)
    parser.add_argument("--baseline", type=Path, default=BASELINE_PATH)
    parser.add_argument("--report", action="store_true", help="print the attribution and exit 0")
    parser.add_argument(
        "--update", action="store_true", help="lower ceilings to what was measured; never raises"
    )
    parser.add_argument(
        "--rebaseline",
        action="store_true",
        help="re-run every lane's own collection and rewrite the map; a deliberate act, argue it",
    )
    parser.add_argument("--quiet", action="store_true")
    return parser.parse_args(argv)


def _write_mode(args: argparse.Namespace, census: Census, baseline: dict[str, Any]) -> int | None:
    """Run whichever of the writing modes was asked for; None means "just check"."""
    if args.rebaseline:
        return rebaseline(census, baseline, args.baseline)
    if args.report:
        return report(baseline, census)
    if args.update:
        return tighten(baseline, census, args.baseline)
    return None


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        census = load_census(args.census)
        baseline = (
            load_baseline(args.baseline)
            if args.baseline.is_file()
            else {"schema": SCHEMA, "unlanded": [], "expansions": {}}
        )
        early = _write_mode(args, census, baseline)
    except (RuntimeError, json.JSONDecodeError) as exc:
        print(f"skip_ratchet: {exc}")
        return 2
    if early is not None:
        return early

    verdict = Verdict()
    check_lanes_still_exist(baseline, verdict)
    attribute(census, baseline, verdict)
    ratchet_roots(census, baseline, verdict)
    ratchet_totals(census, baseline, verdict)

    if not args.quiet:
        for line in verdict.lines:
            print(line)
        for line in verdict.improvements:
            print("  " + line)

    if verdict.failures:
        print(f"\nskip_ratchet: REFUSED — {len(verdict.failures)} finding(s).")
        for line in verdict.failures[:60]:
            print("  " + line)
        if len(verdict.failures) > 60:
            print(f"  … and {len(verdict.failures) - 60} more")
        print(
            "\n  A cluster-backed test that no lane runs is not a passing test. It is a test\n"
            "  nobody has ever executed, and on the Actions tab those look identical. Point a\n"
            "  lane at it, or enumerate it in qa/skip-ratchet.json with a reason and an owner.\n"
            "  Raising a ceiling is allowed only through --rebaseline, and must be argued in\n"
            "  the commit message."
        )
        return 1

    if not args.quiet:
        tail = (
            f"; {len(verdict.improvements)} ceiling(s) can be tightened with --update"
            if verdict.improvements
            else ""
        )
        print(f"\nskip_ratchet: OK — every cluster-shaped skip is attributed{tail}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
