#!/usr/bin/env python
# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
#
# MI: none — this file makes no database claim of its own and opens no connection.
#     It runs one pytest lane and reports what that lane did.
# I: QA-SKIP-CENSUS-1 — the set of tests that CI *does not execute* is a measurement,
#    taken from the one lane that runs the whole-repository `testpaths` collection, with
#    every non-execution carrying the reason string its own fixture wrote and the test
#    root it belongs to. A skip that no file names is a test that reads as green.
# RATIONALE: `ci.yml`'s `hermetic-tests` job is the only lane in this repository that
#    runs the whole-repo collection, and it runs it `--crdb=none`. Measured 2026-08-13
#    on TRAPPOINT, that lane leaves 988 of 9839 collected tests unexecuted, 974 of them
#    for want of a database, and 187 of *those* are the demo API's suite — the product's
#    headline path, which no lane in this repository has ever pointed a cluster at.
#    Nothing on any dashboard distinguishes those 988 from a pass. That job's own step
#    comment already says a census is owed — "`-ra` renders a census of exactly what
#    this lane did not prove. That census is the honest half of a green tick." — but it
#    renders it to a log, where nothing counts it, names it or refuses an increase. The
#    per-package census (`scripts/qa/report_test_state.py`) cannot answer this question
#    either, because it runs each target in its own subprocess with its own selector;
#    "what does the CI lane skip" can only be answered by running the CI lane.
"""The CI skip census: which tests the hermetic lane does not execute, and why.

Runs `ci.yml`'s `hermetic-tests` argv once, in a subprocess, with a JUnit XML report,
and writes `qa/ci-skip-census.json` — one entry per skipped test, not per reason string.

    python scripts/qa/ci_skip_census.py            # measure and write the census
    python scripts/qa/ci_skip_census.py --check     # re-measure and refuse any drift

JUnit rather than `-ra`: the reason arrives as data on a `<skipped message=...>` attribute,
one element per test, instead of a line that has to be regexed back out of a terminal report
that groups identical reasons under one `SKIPPED [n]` heading and re-wraps them for a human.
`junit_family=xunit1` rather than the default `xunit2`: measured on pytest 9.1.1, only
`xunit1` emits the `file` and `line` attributes, and a skip that cannot name its file cannot
be attributed to a test root or to a lane.

**Exit status is about the CENSUS, not about the suite.** `0` means the lane ran and the
census was written; a red suite still exits `0`, because recording a failure is the job.
`1` means `--check` found drift between a fresh measurement and the committed file.
`2` means the tooling itself is wrong — pytest could not be run, `ci.yml` no longer
declares the selector this script reads, or a `--check` was asked for across an
interpreter, a pytest or an operating system the committed file was not taken with.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from collections import Counter
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA = "mainline.qa.ci-skip-census/1"

_HERE = Path(__file__).resolve().parent


def repo_root(start: Path | None = None) -> Path:
    """Locate the clone root by its marker files rather than by counting ``..``."""
    base = (start or _HERE).resolve()
    for parent in [base, *base.parents]:
        if (parent / "pyproject.toml").is_file() and (parent / "compose.yaml").is_file():
            return parent
    raise SystemExit(f"cannot locate the repository root above {base}")


ROOT = repo_root()

DEFAULT_JSON = ROOT / "qa" / "ci-skip-census.json"

#: The workflow file and job whose argv this census reproduces. Named, not paraphrased,
#: so a reader can open the lane and check that the two still agree.
LANE_FILE = ".github/workflows/ci.yml"
LANE_JOB = "hermetic-tests"
LANE_STEP = "The suite, with every cluster test SKIPPED FOR A NAMED REASON"

#: `RED_SELECTOR` is read out of `ci.yml` as raw text, never restated here. W4 raises the
#: red-by-design set in that file; a census that hard-coded today's selector would keep
#: measuring yesterday's lane and never say so.
_RED_SELECTOR_RE = re.compile(r'^\s*RED_SELECTOR:\s*"([^"]+)"\s*$', re.MULTILINE)

#: Wall-clock ceiling for the one subprocess. Measured on TRAPPOINT 2026-08-13, the lane
#: took 610.2 s, 576.1 s and 524 s on three runs of the same afternoon under varying load;
#: the ceiling is generous because a census that gets killed measures nothing at all.
DEFAULT_TIMEOUT_SECONDS = 2700

#: The four spellings every container-spawning fixture in this tree checks *first*. They
#: are REMOVED from the child's environment: CI has none of them set, and a census taken
#: with a DSN in the environment would be measuring a different lane than the one it names.
DSN_ENV_NAMES = ("MAINLINE_TEST_DSN", "COCKROACH_URL", "CRDB_URL", "TRAPPOINT_DSN")

#: A DSN or a machine-local temp path inside a reason string would make this file differ
#: between two machines that measured the same thing. Same two expressions
#: `scripts/qa/report_test_state.py` already uses, for the same reason.
_DSN_RE = re.compile(r"postgresql://[^\s'\"]+")
_TMPPATH_RE = re.compile(r"[A-Za-z]:\\\\?[^\s'\"]*[Tt]emp[^\s'\"]*")

#: WHAT MAKES A SKIP "CLUSTER-SHAPED".
#:
#: The definition is the lead's, verbatim: *the reason string names a cluster, a
#: CockroachDB, a node, a database or a DSN*. It is a property of the REASON the fixture
#: wrote, not of the test, and every distinct reason is published in this file with the
#: side it landed on, so a reader can disagree with the classification in one glance
#: instead of taking it on trust.
#:
#: `cluster` and `crdb` are matched WITHOUT word boundaries, deliberately. An earlier
#: draft of this expression wrote `\bcluster\b`, which does not match inside
#: `MAINLINE_MCP_CLUSTER_ID` or `CRDB_CLUSTER` because `_` is a word character — and 32
#: skips whose reason literally asks for a cluster id fell out of the count. Over-
#: inclusion is also the SAFE direction here: a skip wrongly marked cluster-shaped must
#: be attributed to a lane or to an `unlanded` entry before the ratchet is satisfied,
#: while one wrongly marked otherwise escapes attribution entirely and reads as green.
_CLUSTER_SHAPED_RE = re.compile(
    r"(?i)(--crdb=|crdb|cockroach|cluster|\bDSN\b|_DSN\b|\bdatabase\b|\bnode\b)"
)

#: THE SUBSET A `docker run cockroachdb/cockroach` WOULD NOT UNSKIP.
#:
#: Measured 2026-08-13: 33 of the cluster-shaped skips do not want a node at all. They
#: want a CockroachDB *Cloud* credential — a Managed-MCP API key and a cluster id, or an
#: unattended `ccloud` login — and W2's lane could stand up a pinned single node all day
#: without moving one of them. They are still cluster-shaped, and they still have to be
#: attributed; they simply cannot be attributed to a container. Published as a named
#: subset so a ratchet does not put them on a lane that can never execute them.
_CREDENTIAL_SHAPED_RE = re.compile(
    r"(?i)(MCP_CLUSTER_ID|CRDB_CLUSTER|MCP_API_KEY|CC_API_KEY|\bccloud\b|CockroachDB Cloud)"
)

_EXIT_MEANING = {
    0: "all selected tests passed",
    1: "tests were collected and at least one failed",
    2: "the run was interrupted by the user or an internal signal",
    3: "an internal pytest error occurred",
    4: "pytest was used incorrectly (usage error)",
    5: "no tests were collected",
}

#: `(\d+) deselected` out of pytest's own terminal summary. JUnit XML has no concept of a
#: deselected test — it contains one `<testcase>` per test that was SELECTED — so the
#: deselection count is the one number here that does not come out of the XML, and it is
#: labelled as such in the document (`deselected_source`).
_DESELECTED_RE = re.compile(r"(\d+) deselected")


# ── the lane ─────────────────────────────────────────────────────────────────────────────


def read_red_selector(workflow: Path) -> str:
    """Lift `RED_SELECTOR` out of `ci.yml` as RAW TEXT.

    Raw text, not PyYAML: the value is an ordinary mapping entry and would survive a
    parse, but every other reader of these files in this repository reads them as text
    (the Contract A lane markers are comments, which PyYAML discards), and one parser is
    one fewer dependency between this census and the lane it claims to reproduce.
    """
    if not workflow.is_file():
        raise SystemExit(f"{workflow} is not on disk; this census has no lane to reproduce")
    matches = _RED_SELECTOR_RE.findall(workflow.read_text(encoding="utf-8"))
    if len(matches) != 1:
        raise SystemExit(
            f'expected exactly one `RED_SELECTOR: "..."` line in {workflow}, found '
            f"{len(matches)}. This census runs the lane's selector rather than restating "
            "it; fix the lane or fix this reader, but do not let the two drift apart."
        )
    return matches[0]


def census_argv(selector: str, junit: Path) -> list[str]:
    """The argv this script runs. See `argv_differs_from_ci` for what it adds and why."""
    return [
        sys.executable,
        "-m",
        "pytest",
        "--crdb=none",
        "-m",
        f"not ({selector})",
        "-q",
        "--durations=10",
        "-p",
        "no:cacheprovider",
        "-o",
        "junit_family=xunit1",
        "--junit-xml",
        str(junit),
    ]


def ci_argv(selector: str) -> str:
    """The lane's own command line, with the selector this run actually used."""
    return (
        f'uv run --frozen --all-packages pytest --crdb=none -m "not ({selector})" -q --durations=10'
    )


#: Every way the census's argv differs from the lane's, and why. Four differences, all
#: additive: none of them selects, deselects or skips a test the lane would not.
ARGV_DIFFERENCES: tuple[dict[str, str], ...] = (
    {
        "flag": "--junit-xml <tmp>",
        "why": (
            "the census reads counts and skip reasons out of the report rather than out "
            "of a terminal summary; no test sees this flag"
        ),
    },
    {
        "flag": "-o junit_family=xunit1",
        "why": (
            "measured on pytest 9.1.1, the default `xunit2` writes only "
            "classname/name/time, so a skip could not name its file or its test root; "
            "`ci.yml`'s `red-by-design` job already sets this for the same reason"
        ),
    },
    {
        "flag": "-p no:cacheprovider",
        "why": (
            "the census must not leave `.pytest_cache` behind in a tree other workers "
            "are writing to; no test in this repository reads the cache"
        ),
    },
    {
        "flag": "python -m pytest instead of uv run --frozen --all-packages",
        "why": (
            "`uv --version` is `command not found` on the machine this census was taken "
            "on; the interpreter is the pinned `.venv` one that resolves the same "
            "lockfile. `tool.python_executable_is_venv` records whether that held for "
            "the run that wrote this file"
        ),
    },
)


def child_env() -> dict[str, str]:
    env = dict(os.environ)
    env.setdefault("PGCONNECT_TIMEOUT", "5")
    env["PYTHONIOENCODING"] = "utf-8"
    for name in DSN_ENV_NAMES:
        env.pop(name, None)
    return env


# ── parsing ──────────────────────────────────────────────────────────────────────────────


def redact(text: str) -> str:
    text = _DSN_RE.sub("<dsn>", text)
    text = _TMPPATH_RE.sub("<tmp>", text)
    return " ".join(text.split())


def posix(path: str) -> str:
    return path.replace("\\", "/")


def root_of(file_path: str) -> str:
    """The test root a file belongs to.

    The same partition `scripts/qa/report_test_state.py` discovers its targets by — every
    distribution owning a `tests/` directory, plus every root test root — so the two files
    can be read against each other. It is written here as a pure function of the path
    because the census sees paths out of a JUnit report, not directories on disk.
    """
    parts = posix(file_path).split("/")
    if not parts:
        return "?"
    head = parts[0]
    if head == "packages" and len(parts) >= 2:
        return f"packages/{parts[1]}"
    if head == "verticals" and len(parts) >= 4 and parts[2] in {"packages", "apps"}:
        return "/".join(parts[:4])
    if head == "tests" and len(parts) >= 2 and not parts[1].endswith(".py"):
        return f"tests/{parts[1]}"
    return head


def node_id(case: ET.Element) -> str:
    """Rebuild the pytest node id from a `xunit1` testcase.

    `classname` is the dotted module path plus any enclosing classes, and `file` is the
    same module as a rootdir-relative path, so the class part is whatever `classname` has
    that the module path does not.
    """
    name = case.get("name") or "?"
    classname = (case.get("classname") or "").strip()
    file_attr = posix(case.get("file") or "")
    if not file_attr:
        return f"{classname}::{name}" if classname else name
    stem = file_attr[:-3] if file_attr.endswith(".py") else file_attr
    module_dots = stem.replace("/", ".")
    if classname == module_dots:
        return f"{file_attr}::{name}"
    if classname.startswith(f"{module_dots}."):
        inner = classname[len(module_dots) + 1 :].replace(".", "::")
        return f"{file_attr}::{inner}::{name}"
    return f"{file_attr}::{name}"


def _blank_root() -> dict[str, int]:
    return {
        "tests": 0,
        "passed": 0,
        "failed": 0,
        "errored": 0,
        "skipped": 0,
        "xfailed": 0,
        "cluster_skipped": 0,
    }


def parse_junit(junit: Path) -> dict[str, Any]:
    """Everything the census knows, read out of one JUnit XML file."""
    tree = ET.parse(junit)  # noqa: S314 - written by this script's own subprocess
    roots: dict[str, dict[str, int]] = {}
    skips: list[dict[str, Any]] = []
    counts = {"tests": 0, "passed": 0, "failed": 0, "errored": 0, "skipped": 0, "xfailed": 0}

    for case in tree.getroot().iter("testcase"):
        file_attr = posix(case.get("file") or "")
        root = root_of(file_attr) if file_attr else "?"
        bucket = roots.setdefault(root, _blank_root())
        counts["tests"] += 1
        bucket["tests"] += 1

        failure = case.find("failure")
        error = case.find("error")
        skipped = case.find("skipped")
        if failure is not None:
            # A testcase that both failed and errored (a teardown error on a failed test)
            # is counted once, as a failure — the same order `report_test_state.py` uses.
            counts["failed"] += 1
            bucket["failed"] += 1
        elif error is not None:
            counts["errored"] += 1
            bucket["errored"] += 1
        elif skipped is not None:
            if (skipped.get("type") or "").strip() == "pytest.xfail":
                counts["xfailed"] += 1
                bucket["xfailed"] += 1
            else:
                reason = redact(skipped.get("message") or skipped.text or "")
                shaped = bool(_CLUSTER_SHAPED_RE.search(reason))
                counts["skipped"] += 1
                bucket["skipped"] += 1
                if shaped:
                    bucket["cluster_skipped"] += 1
                raw_line = case.get("line")
                skips.append(
                    {
                        "nodeid": node_id(case),
                        "file": file_attr,
                        # pytest writes `item.location[1]`, which is ZERO-based; +1 makes
                        # it the line number an editor shows and the one the terminal
                        # `SKIPPED [n] file:line:` report prints.
                        "line": (int(raw_line) + 1) if raw_line is not None else None,
                        "root": root,
                        "reason": reason or "(no reason string)",
                        "cluster_shaped": shaped,
                    }
                )
        else:
            counts["passed"] += 1
            bucket["passed"] += 1

    skips.sort(key=lambda entry: (entry["file"], entry["line"] or 0, entry["nodeid"]))
    return {
        "counts": counts,
        "roots": {name: roots[name] for name in sorted(roots)},
        "skips": skips,
    }


def reason_rollup(skips: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Every distinct reason string with its count and its classification."""
    counter: Counter[tuple[str, bool]] = Counter()
    for entry in skips:
        counter[(entry["reason"], bool(entry["cluster_shaped"]))] += 1
    return [
        {"reason": reason, "count": count, "cluster_shaped": shaped}
        for (reason, shaped), count in sorted(counter.items(), key=lambda kv: (-kv[1], kv[0][0]))
    ]


def credential_subset(skips: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """The cluster-shaped skips that want a Cloud credential rather than a node.

    Named as a subset instead of as a third value of `cluster_shaped`, because W4's
    ratchet consumes that key as a boolean and the shape is pinned in its brief. The
    reason strings are published verbatim so a consumer can select these node ids by
    reason without this file growing a per-skip field the schema does not promise.
    """
    matched = [
        entry
        for entry in skips
        if entry["cluster_shaped"] and _CREDENTIAL_SHAPED_RE.search(entry["reason"])
    ]
    by_reason: Counter[str] = Counter()
    by_root: Counter[str] = Counter()
    for entry in matched:
        by_reason[entry["reason"]] += 1
        by_root[entry["root"]] += 1
    return {
        "count": len(matched),
        "pattern": _CREDENTIAL_SHAPED_RE.pattern,
        "what_it_means": (
            "cluster-shaped, but a `docker run cockroachdb/cockroach` would not unskip "
            "one of them: the reason asks for a CockroachDB Cloud credential — a "
            "Managed-MCP API key and a cluster id, or an unattended `ccloud` login. They "
            "still have to be attributed; they simply cannot be attributed to a lane "
            "that stands up a container. Anything that puts these on a cluster lane is "
            "putting them somewhere they can never execute."
        ),
        "roots": dict(sorted(by_root.items())),
        "reasons": [
            {"reason": reason, "count": count}
            for reason, count in sorted(by_reason.items(), key=lambda kv: (-kv[1], kv[0]))
        ],
    }


def tool_versions() -> dict[str, Any]:
    versions: dict[str, Any] = {
        "python": sys.version.split()[0],
        "python_minor": ".".join(sys.version.split()[0].split(".")[:2]),
        "python_executable_is_venv": ".venv" in sys.executable.replace("\\", "/"),
        "platform": sys.platform,
    }
    try:
        out = subprocess.run(
            [sys.executable, "-m", "pytest", "--version"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        versions["pytest"] = (out.stdout or out.stderr).strip().splitlines()[0]
    except (subprocess.SubprocessError, IndexError) as exc:  # pragma: no cover
        versions["pytest"] = f"unknown ({type(exc).__name__}: {exc})"
    return versions


# ── the measurement ──────────────────────────────────────────────────────────────────────


def measure(*, timeout: int, quiet: bool = False) -> dict[str, Any]:
    """Run the lane once and return the whole census document."""
    selector = read_red_selector(ROOT / LANE_FILE)
    tmpdir = Path(tempfile.mkdtemp(prefix="mainline-skip-census-"))
    junit = tmpdir / "hermetic.xml"
    argv = census_argv(selector, junit)
    if not quiet:
        print(f"lane: {LANE_FILE} · job {LANE_JOB} · selector {selector!r}")
        print("running: " + " ".join(["python", *argv[1:-1], "<tmp>/hermetic.xml"]))
    started = time.monotonic()
    try:
        completed = subprocess.run(
            argv,
            cwd=str(ROOT),
            env=child_env(),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        shutil.rmtree(tmpdir, ignore_errors=True)
        raise SystemExit(
            f"the lane did not finish within {timeout}s and was killed. Nothing was "
            "measured; no census was written. Raise --timeout or find the hang."
        ) from exc
    elapsed = time.monotonic() - started
    stdout = completed.stdout or ""

    if not junit.is_file():
        tail = (completed.stderr or stdout)[-2000:]
        shutil.rmtree(tmpdir, ignore_errors=True)
        raise SystemExit(
            f"pytest exited {completed.returncode} and wrote no JUnit report, so nothing "
            f"was measured. Tail of its output:\n{tail}"
        )
    try:
        parsed = parse_junit(junit)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    deselected_matches = _DESELECTED_RE.findall(stdout)
    deselected = int(deselected_matches[-1]) if deselected_matches else 0
    counts = parsed["counts"]
    skips = parsed["skips"]
    cluster_skipped = sum(1 for entry in skips if entry["cluster_shaped"])
    reasons = reason_rollup(skips)

    document: dict[str, Any] = {
        "schema": SCHEMA,
        "SPDX-FileCopyrightText": "2026 MAINLINE contributors",
        # CC-BY-4.0, not the Apache-2.0 this SCRIPT carries. `REUSE.toml` §3 hands
        # `qa/**` CC-BY-4.0 because quality state is a record rather than code, and
        # carves out `qa/*-ratchet.json` and `qa/test-state.json` only because those two
        # already said Apache-2.0 in band and it refused to contradict their own text. A
        # new artefact in that directory declaring Apache-2.0 would need the same carve-
        # out in a file this worker does not own; declaring the directory's own licence
        # needs nothing and is what the policy says a record is.
        "SPDX-License-Identifier": "CC-BY-4.0",
        "note": (
            "What CI does NOT execute, measured by running CI's own lane. One entry per "
            "skipped test, not per reason string: a rollup by reason cannot be attributed "
            "to a workflow, and attribution is the point. Nothing here is estimated and "
            "nothing is rounded; every count came out of a JUnit report written by a "
            "pytest subprocess this script started."
        ),
        "generated_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "generated_by": "scripts/qa/ci_skip_census.py",
        "tool": tool_versions(),
        "lane": {
            "workflow": LANE_FILE,
            "job": LANE_JOB,
            "step": LANE_STEP,
            "red_selector": selector,
            "red_selector_source": f"{LANE_FILE}, read as raw text, never restated here",
            "ci_argv": ci_argv(selector),
            "why_this_lane": (
                "it is the only lane in this repository that runs the whole-repository "
                "`testpaths` collection, and it runs it with --crdb=none"
            ),
        },
        "argv": ["python", *census_argv(selector, Path("<tmp>/hermetic.xml"))[1:]],
        "argv_differences_from_ci": list(ARGV_DIFFERENCES),
        "exit_code": completed.returncode,
        "exit_meaning": _EXIT_MEANING.get(
            completed.returncode, f"undocumented pytest exit code {completed.returncode}"
        ),
        "wall_clock_seconds": round(elapsed, 1),
        "collected": counts["tests"] + deselected,
        "collected_derivation": (
            "selected testcases in the JUnit report + deselected from pytest's own summary; "
            "JUnit has no element for a deselected test"
        ),
        "passed": counts["passed"],
        "failed": counts["failed"],
        "errored": counts["errored"],
        "skipped": counts["skipped"],
        "xfailed": counts["xfailed"],
        "deselected": deselected,
        "deselected_source": "pytest terminal summary, `(\\d+) deselected`",
        "cluster_shaped": {
            "count": cluster_skipped,
            "other_skips": counts["skipped"] - cluster_skipped,
            "pattern": _CLUSTER_SHAPED_RE.pattern,
            "what_it_means": (
                "the reason string the fixture wrote names a CockroachDB, a cluster, a "
                "node, a database or a DSN. It is a property of the REASON, not of the "
                "test, and it is published with every distinct reason below so a reader "
                "can disagree with it without re-running anything."
            ),
            "needs_a_credential_not_a_node": credential_subset(skips),
        },
        "distinct_reasons": len(reasons),
        "reasons": reasons,
        "roots": parsed["roots"],
        "skips": skips,
        "caveats": [
            (
                "This is a SNAPSHOT of a moving tree. The census was taken while five "
                "other workers were writing to this repository; a test file that lands "
                "after it moves `collected` and `skipped` and makes `--check` red. That "
                "is the intended behaviour — re-take the census in the same commit that "
                "adds the test, and the number stays true."
            ),
            (
                "Every count is what THIS operating system and THIS interpreter observed. "
                "A skip conditioned on the platform (`sys.platform`, a missing binary, an "
                "opt-in credential) is counted here as it fell on the machine named in "
                "`tool`, which is not necessarily how it falls on `ubuntu-24.04`. "
                "`--check` refuses to compare across platforms rather than report a "
                "difference it cannot attribute."
            ),
            (
                "`failed` is a count, not a verdict. This script exits 0 on a red suite "
                "on purpose: recording the failure is the job. The lane's own verdict is "
                "the lane's, in ci.yml."
            ),
            (
                "A test that is DESELECTED is not a test that is skipped. The "
                "red-by-design set is deselected here and executed by ci.yml's "
                "`red-by-design` job, which is why `deselected` is reported separately "
                "and is not folded into `skipped`."
            ),
        ],
    }
    return document


# ── --check ──────────────────────────────────────────────────────────────────────────────

#: The keys `--check` compares. Everything else in the document is either a timestamp, a
#: duration or prose, and a census that went red because a clock moved would be a census
#: nobody runs.
COMPARED_KEYS = (
    "collected",
    "passed",
    "failed",
    "errored",
    "skipped",
    "xfailed",
    "deselected",
    "roots",
    "skips",
)


def _incomparable(fresh: dict[str, Any], committed: dict[str, Any]) -> str | None:
    """Why these two documents cannot be diffed at all, or None if they can."""
    if committed.get("schema") != SCHEMA:
        return (
            f"the committed file declares schema {committed.get('schema')!r} and this "
            f"script writes {SCHEMA!r}"
        )
    old, new = committed.get("tool", {}), fresh["tool"]
    if old.get("platform") != new.get("platform"):
        return (
            f"the committed census was taken on {old.get('platform')!r} and this one on "
            f"{new.get('platform')!r}. Skips conditioned on the platform differ between "
            "them, so a diff would report drift this script cannot attribute."
        )
    if old.get("pytest") != new.get("pytest"):
        return (
            f"the committed census was taken with {old.get('pytest')!r} and this one with "
            f"{new.get('pytest')!r}. Collection and skip behaviour differ between pytest "
            "releases; re-take the census rather than compare across them."
        )
    if old.get("python_minor") != new.get("python_minor"):
        return (
            f"the committed census was taken on Python {old.get('python_minor')} and this "
            f"one on {new.get('python_minor')}"
        )
    if committed.get("lane", {}).get("red_selector") != fresh["lane"]["red_selector"]:
        return (
            "the lane's RED_SELECTOR changed from "
            f"{committed.get('lane', {}).get('red_selector')!r} to "
            f"{fresh['lane']['red_selector']!r}; the two censuses measure different "
            "selections. Re-take rather than compare."
        )
    return None


def report_drift(fresh: dict[str, Any], committed: dict[str, Any]) -> list[str]:
    """Every difference between a fresh measurement and the committed file, named."""
    drift: list[str] = []
    for key in COMPARED_KEYS:
        if key in {"roots", "skips"}:
            continue
        if fresh.get(key) != committed.get(key):
            drift.append(f"{key}: committed {committed.get(key)!r}, measured {fresh.get(key)!r}")

    old_roots = committed.get("roots", {})
    for name in sorted(set(old_roots) | set(fresh["roots"])):
        before, after = old_roots.get(name), fresh["roots"].get(name)
        if before != after:
            drift.append(f"roots[{name}]: committed {before!r}, measured {after!r}")

    old_skips = {entry["nodeid"]: entry for entry in committed.get("skips", [])}
    new_skips = {entry["nodeid"]: entry for entry in fresh["skips"]}
    for nodeid in sorted(set(new_skips) - set(old_skips)):
        drift.append(f"skips: NEW skip not in the committed census — {nodeid}")
    for nodeid in sorted(set(old_skips) - set(new_skips)):
        drift.append(f"skips: committed skip no longer skipped — {nodeid}")
    for nodeid in sorted(set(old_skips) & set(new_skips)):
        before, after = old_skips[nodeid], new_skips[nodeid]
        if before.get("reason") != after.get("reason"):
            drift.append(
                f"skips[{nodeid}].reason: committed {before.get('reason')!r}, "
                f"measured {after.get('reason')!r}"
            )
        elif before.get("cluster_shaped") != after.get("cluster_shaped"):
            drift.append(
                f"skips[{nodeid}].cluster_shaped: committed "
                f"{before.get('cluster_shaped')!r}, measured {after.get('cluster_shaped')!r}"
            )
    return drift


# ── entry point ──────────────────────────────────────────────────────────────────────────


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="ci_skip_census.py",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="re-run the lane, diff against the committed census, exit 1 on any drift",
    )
    parser.add_argument("--out", type=Path, default=DEFAULT_JSON, help="census path")
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=f"wall-clock ceiling for the lane (default: {DEFAULT_TIMEOUT_SECONDS}s)",
    )
    parser.add_argument(
        "--summary-only",
        action="store_true",
        help="print the summary of the committed census and exit; runs nothing",
    )
    return parser.parse_args(argv)


def print_summary(doc: dict[str, Any]) -> None:
    print(
        f"{doc['collected']} collected · {doc['passed']} passed · {doc['failed']} failed · "
        f"{doc['errored']} errored · {doc['skipped']} skipped · "
        f"{doc['deselected']} deselected"
    )
    shaped = doc["cluster_shaped"]
    print(
        f"{shaped['count']} of {doc['skipped']} skips are cluster-shaped; "
        f"{shaped['other_skips']} are not; {doc['distinct_reasons']} distinct reason strings"
    )
    ranked = sorted(doc["roots"].items(), key=lambda kv: (-kv[1]["cluster_skipped"], kv[0]))
    for name, row in ranked:
        if row["cluster_skipped"]:
            print(f"  {row['cluster_skipped']:>4} cluster-shaped skips · {name}")


def _check(fresh: dict[str, Any], out: Path) -> int:
    """`--check`: diff a fresh measurement against the committed census."""
    if not out.is_file():
        print(
            f"{out} does not exist, so there is nothing to check against. Run "
            "`python scripts/qa/ci_skip_census.py` once to write it.",
            file=sys.stderr,
        )
        return 2
    committed = json.loads(out.read_text(encoding="utf-8"))
    blocked = _incomparable(fresh, committed)
    if blocked is not None:
        print(f"cannot compare: {blocked}", file=sys.stderr)
        return 2
    drift = report_drift(fresh, committed)
    print_summary(fresh)
    if not drift:
        print(f"\nno drift against {out}")
        return 0
    print("")
    print(f"{len(drift)} difference(s) between the fresh measurement and {out}:")
    for line in drift[:60]:
        print(f"  {line}")
    if len(drift) > 60:
        print(f"  ... and {len(drift) - 60} more")
    print("")
    print(
        "The census is a measurement of a tree, not a target. If the tree moved on "
        "purpose, re-take it in the same commit that moved it:\n"
        "    python scripts/qa/ci_skip_census.py"
    )
    return 1


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)

    if args.summary_only:
        if not args.out.is_file():
            print(f"{args.out} does not exist; nothing to summarise", file=sys.stderr)
            return 2
        print_summary(json.loads(args.out.read_text(encoding="utf-8")))
        return 0

    fresh = measure(timeout=args.timeout, quiet=False)
    if args.check:
        return _check(fresh, args.out)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(fresh, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    print(f"wrote {args.out}")
    print_summary(fresh)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
