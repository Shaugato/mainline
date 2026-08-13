#!/usr/bin/env python
# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
#
# MI: none — this file makes no database claim of its own. It *reports* what the suite
#     did, including against a live node, but it asserts no invariant.
# I: QA-CENSUS-1 — the repository's test state is a census, taken per distribution and
#    per test root, in two passes (no cluster, then the session's one cluster), with
#    every skip carrying the reason string its own fixture wrote. No adjective in
#    `docs/HONESTY.md` may stand where a number from this file could stand instead.
# RATIONALE: the quality-repair plan, §1.4, records that the full suite could not be
#    censused at all: thirteen private CockroachDB containers started concurrently, all
#    exited 7/8, took the shared node down with them, and the run then *hung* rather
#    than failed — 300 CPU-seconds accumulating at roughly one per wall minute, with
#    `timeout = 120` never firing because pytest-timeout's thread method cannot
#    interrupt a hang inside session-scoped fixture setup. Two things make the census
#    obtainable now: `--crdb=none` (trappoint-testkit's ProcessGuard, so a cluster test
#    SKIPS WITH A REASON instead of starting a container), and a per-target subprocess
#    with a wall-clock timeout this script enforces itself, so a target that wedges is
#    recorded as `timed_out` rather than eating the session.
"""Per-package test census for MAINLINE.

Runs pytest once per target — every distribution that owns a ``tests/`` directory, and
every root test root — in two passes:

* ``--crdb=none``  — no database is obtained and none may be started. Every
  cluster-backed test skips with the reason its own fixture writes.
* ``--crdb=reuse`` — the session's ONE shared cluster, reused and never spawned.

Each run is a separate subprocess with its own JUnit XML, so a target that crashes the
interpreter, wedges, or collides on a module basename damages only its own row.

Writes ``qa/test-state.json`` (passed / failed / errored / skipped / xfailed per target
per pass, plus every distinct skip reason string with its count) and renders
``docs/release/test-state.md`` from it.

    python scripts/qa/report_test_state.py
    python scripts/qa/report_test_state.py --pass none --timeout 300
    python scripts/qa/report_test_state.py --targets packages/trappoint-jcs tests/unit

Exit status is about the CENSUS, not about the suite: ``0`` means every target was
measured, ``1`` means at least one target could not be measured (timed out, or pytest
exited with an internal/usage error), ``2`` means the tooling itself is wrong. **A red
suite still exits 0** — recording a failure is the job, not a reason to fail.
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
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA = "mainline.qa.test-state/1"

#: Where the repository root is, found by the two marker files that identify it.
_HERE = Path(__file__).resolve().parent


def repo_root(start: Path | None = None) -> Path:
    """Locate the clone root by its marker files rather than by counting ``..``."""
    base = (start or _HERE).resolve()
    for parent in [base, *base.parents]:
        if (parent / "pyproject.toml").is_file() and (parent / "compose.yaml").is_file():
            return parent
    raise SystemExit(f"cannot locate the repository root above {base}")


ROOT = repo_root()

DEFAULT_JSON = ROOT / "qa" / "test-state.json"
DEFAULT_MARKDOWN = ROOT / "docs" / "release" / "test-state.md"

#: Pass names, in the order they are run and reported.
PASSES: tuple[str, ...] = ("none", "cluster")

#: ``--crdb`` mode for each pass. ``reuse``, not ``auto``: a census that quietly started a
#: container would be measuring a different repository than the one it claims to measure.
CRDB_MODE = {"none": "none", "cluster": "reuse"}

#: The four spellings every container-spawning fixture in this tree checks *first*.
DSN_ENV_NAMES = ("MAINLINE_TEST_DSN", "COCKROACH_URL", "CRDB_URL", "TRAPPOINT_DSN")

DEFAULT_DSN = "postgresql://root@localhost:26257/defaultdb?sslmode=disable"


#: WHY THE HOST SPELLING IS RECORDED WITH EVERY MERGE, AND WHY THE DEFAULT IS UNCHANGED.
#:
#: `localhost` is what the project's own runbook publishes, so it stays the default. It is
#: also, on a dual-stack machine, not the same address as `127.0.0.1`. MEASURED 2026-08-13
#: on TRAPPOINT, where the node is published by `-p 127.0.0.1:26257:26257`:
#:
#:     getaddrinfo('localhost', 26257) -> [AF_INET6 ('::1', …), AF_INET ('127.0.0.1', …)]
#:     connect ::1:26257        TimeoutError after 6.00 s   <- SYN dropped, never refused
#:     connect 127.0.0.1:26257  connected in 0.00 s
#:
#: `socket.create_connection` carries a timeout and falls through to the IPv4 address after
#: six seconds. A `psycopg.connect` given no `connect_timeout` does not: it sits in
#: `waiting.wait_conn` -> `select.select` forever. The demo API's
#: `tests/test_credentials.py:200` connects that way, so publishing the DSN under the four
#: environment names as `localhost` wedges that target — twice measured here, 900.02 s and
#: killed, `0P 0F 0E 0S`, against 43 s and a full result for the same suite on `127.0.0.1`.
#: pytest-timeout cannot save it; the hang is inside session-scoped fixture setup.
#:
#: The default is therefore NOT changed to dodge it — that would hide a real defect in a
#: suite this script exists to measure, and a CI runner resolving `localhost` to `::1`
#: would hit exactly the same wall. Instead the host actually dialled is recorded beside
#: every merged row, so a reader can tell which spelling produced the numbers.
def dsn_host(dsn: str) -> str:
    """The `host:port` a DSN dials, with any credential dropped on the floor."""
    tail = dsn.rsplit("@", maxsplit=1)[-1]
    return tail.split("/", maxsplit=1)[0] or "?"


#: Wall-clock ceiling per target subprocess. Not pytest's `timeout = 120`, which is
#: per-test and cannot interrupt session-scoped fixture setup (quality-repair plan §1.4).
DEFAULT_TIMEOUT_SECONDS = 900

#: How many failing/erroring node ids to name per target before saying so and stopping.
MAX_NAMED_TESTS = 40

#: APPLICATIONS WITH A PYTHON TEST SUITE, NAMED — NOT GLOBBED.
#:
#: `discover_targets` walked `packages/*` and `verticals/*/packages/*` and stopped there,
#: so `qa/test-state.json`'s 26 targets contained no row for the demo API at all: 444
#: tests, the product's headline path, absent from the census that `docs/HONESTY.md`
#: cites. That is the THIRD occurrence of one defect class, one directory level across,
#: after `testpaths = ["tests", "packages"]` (2026-08-10) and
#: `+ verticals/*/packages/*/tests` (2026-08-13).
#:
#: It is a tuple of literal paths and not the glob `verticals/*/apps/*` for the reason
#: `pyproject.toml` already gives in writing above its own `testpaths`: the app segment is
#: exactly where this repository's Python/TypeScript boundary lies. Measured 2026-08-13,
#: `verticals/mainline/apps/` holds three entries and only one is Python —
#: `console/tests` is a vitest suite with 148 entries and ZERO `*.py` files, and `steward`
#: has no `tests/` at all. Handing `console/tests` to pytest is the same category error
#: that `[tool.uv.workspace] members` refuses one file over. Adding an app here is a
#: deliberate line, which is the point.
NAMED_APP_TARGETS: tuple[str, ...] = ("verticals/mainline/apps/demo-api",)

_EXIT_MEANING = {
    0: "all collected tests passed",
    1: "tests were collected and at least one failed",
    2: "the run was interrupted by the user or an internal signal",
    3: "an internal pytest error occurred",
    4: "pytest was used incorrectly (usage error)",
    5: "no tests were collected",
}

#: A DSN in a skip reason would make the census differ between machines for no reason.
_DSN_RE = re.compile(r"postgresql://[^\s'\"]+")
_TMPPATH_RE = re.compile(r"[A-Za-z]:\\\\?[^\s'\"]*[Tt]emp[^\s'\"]*")


# ── target enumeration ───────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Target:
    """One unit of the census: a path pytest is pointed at, and what kind of thing it is."""

    id: str
    path: str
    kind: str  # "distribution" | "test-root"
    distribution: str | None = None

    @property
    def abspath(self) -> Path:
        return ROOT / self.path


def discover_targets() -> list[Target]:
    """Every distribution with a ``tests/`` directory, and every root test root.

    "Distribution" here means a directory with its own ``pyproject.toml`` and its own
    ``tests/``, whether or not it is a ``uv`` workspace member: ``mainline-demo-api`` is
    deliberately NOT a member (``verticals/*/apps/*`` is absent from
    ``[tool.uv.workspace] members`` because the console beside it is a pnpm workspace),
    and a census that only counted members would inherit that exclusion as a blind spot.

    Ordered distributions-then-roots, and alphabetically within each, so two runs of this
    script on the same tree produce byte-identical target ordering.
    """
    targets: list[Target] = []
    distributions: list[Target] = []
    for pattern in ("packages/*", "verticals/*/packages/*"):
        for pkg in sorted(ROOT.glob(pattern)):
            if not (pkg / "tests").is_dir():
                continue
            rel = pkg.relative_to(ROOT).as_posix()
            distributions.append(
                Target(id=rel, path=f"{rel}/tests", kind="distribution", distribution=pkg.name)
            )
    for rel in NAMED_APP_TARGETS:
        pkg = ROOT / rel
        if not (pkg / "tests").is_dir():
            continue
        distributions.append(
            Target(id=rel, path=f"{rel}/tests", kind="distribution", distribution=pkg.name)
        )
    # Sorted as one list rather than appended after the globs, so the docstring's promise
    # of alphabetical ordering holds for the named apps too. Measured: this reproduces the
    # existing seventeen rows in their existing order and slots the app in beside them.
    targets.extend(sorted(distributions, key=lambda target: target.id))
    tests_dir = ROOT / "tests"
    if tests_dir.is_dir():
        for child in sorted(tests_dir.iterdir()):
            if not child.is_dir() or child.name.startswith((".", "__")):
                continue
            if not any(child.rglob("test_*.py")):
                continue
            rel = child.relative_to(ROOT).as_posix()
            targets.append(Target(id=rel, path=rel, kind="test-root"))
    return targets


# ── running ──────────────────────────────────────────────────────────────────────────────


@dataclass
class RunResult:
    """What one pytest subprocess did to one target."""

    argv: list[str] = field(default_factory=list)
    exit_code: int | None = None
    exit_meaning: str = ""
    duration_seconds: float = 0.0
    timed_out: bool = False
    junit_written: bool = False
    tests: int = 0
    passed: int = 0
    failed: int = 0
    errored: int = 0
    skipped: int = 0
    xfailed: int = 0
    xpassed: int = 0
    skip_reasons: list[dict[str, Any]] = field(default_factory=list)
    failed_tests: list[str] = field(default_factory=list)
    errored_tests: list[str] = field(default_factory=list)
    names_truncated: bool = False
    stderr_tail: str = ""


def _pytest_argv(target: Target, mode: str, junit: Path) -> list[str]:
    return [
        sys.executable,
        "-m",
        "pytest",
        target.path,
        f"--crdb={mode}",
        "-q",
        "--no-header",
        "-p",
        "no:cacheprovider",
        "--junit-xml",
        str(junit),
    ]


def _child_env(phase: str, dsn: str | None) -> dict[str, str]:
    env = dict(os.environ)
    # A connect that never times out is how the earlier census turned into a 300-second
    # hang. Five seconds, unless the operator has already chosen.
    env.setdefault("PGCONNECT_TIMEOUT", "5")
    env["PYTHONIOENCODING"] = "utf-8"
    # NOTHING ELSE is injected. An earlier draft set `HYPOTHESIS_DATABASE_FILE=""` to keep
    # the census from racing other workers for the example database; measured, that turned
    # 82 passed into 75 passed and 7 failed in packages/trappoint-jcs, because an empty
    # value makes hypothesis's runner None. A census that changes the number it is
    # measuring is not a census, so the environment is inherited and left alone.
    if phase == "cluster" and dsn:
        for name in DSN_ENV_NAMES:
            env[name] = dsn
    else:
        for name in DSN_ENV_NAMES:
            env.pop(name, None)
    return env


def run_target(target: Target, phase: str, *, dsn: str | None, timeout: int) -> RunResult:
    """Run one target in one pass, in its own subprocess, and parse its JUnit XML."""
    result = RunResult()
    tmpdir = Path(tempfile.mkdtemp(prefix="mainline-census-"))
    junit = tmpdir / "junit.xml"
    argv = _pytest_argv(target, CRDB_MODE[phase], junit)
    result.argv = argv[1:]  # sys.executable differs per machine; the rest does not.
    started = time.monotonic()
    try:
        completed = subprocess.run(
            argv,
            cwd=str(ROOT),
            env=_child_env(phase, dsn),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
        result.exit_code = completed.returncode
        result.exit_meaning = _EXIT_MEANING.get(
            completed.returncode, f"undocumented pytest exit code {completed.returncode}"
        )
        if completed.returncode in (3, 4) or completed.returncode is None:
            result.stderr_tail = (completed.stderr or completed.stdout or "")[-2000:]
    except subprocess.TimeoutExpired:
        result.timed_out = True
        result.exit_meaning = (
            f"the target did not finish within {timeout}s of wall clock and was killed by "
            "report_test_state.py; nothing below it was measured"
        )
    result.duration_seconds = round(time.monotonic() - started, 2)

    if junit.is_file():
        result.junit_written = True
        _parse_junit(junit, result)
    shutil.rmtree(tmpdir, ignore_errors=True)
    return result


def _redact(text: str) -> str:
    text = _DSN_RE.sub("<dsn>", text)
    text = _TMPPATH_RE.sub("<tmp>", text)
    return " ".join(text.split())


def _parse_junit(path: Path, result: RunResult) -> None:
    """Fill ``result`` from a JUnit XML file, distinguishing xfail from skip by type."""
    try:
        tree = ET.parse(path)  # noqa: S314 - the file was written by our own subprocess
    except ET.ParseError as exc:  # pragma: no cover - only on a killed writer
        result.stderr_tail = f"unparseable junit xml: {exc}"
        return
    reasons: Counter[str] = Counter()
    for case in tree.getroot().iter("testcase"):
        result.tests += 1
        node = _node_id(case)
        failure = case.find("failure")
        error = case.find("error")
        skipped = case.find("skipped")
        if failure is not None:
            result.failed += 1
            _append_bounded(result.failed_tests, node, result)
        elif error is not None:
            result.errored += 1
            _append_bounded(result.errored_tests, node, result)
        elif skipped is not None:
            kind = (skipped.get("type") or "").strip()
            message = _redact(skipped.get("message") or skipped.text or "")
            if kind == "pytest.xfail":
                result.xfailed += 1
            else:
                result.skipped += 1
                reasons[message or "(no reason string)"] += 1
        else:
            result.passed += 1
    result.skip_reasons = [
        {"reason": reason, "count": count}
        for reason, count in sorted(reasons.items(), key=lambda kv: (-kv[1], kv[0]))
    ]


def _append_bounded(bucket: list[str], node: str, result: RunResult) -> None:
    if len(bucket) < MAX_NAMED_TESTS:
        bucket.append(node)
    else:
        result.names_truncated = True


def _node_id(case: ET.Element) -> str:
    classname = case.get("classname") or ""
    name = case.get("name") or "?"
    return f"{classname}::{name}" if classname else name


# ── cluster probe ────────────────────────────────────────────────────────────────────────


def probe_cluster(dsn: str) -> dict[str, Any]:
    """Ask the node what it is. Never starts anything; a refusal here is a recorded fact."""
    record: dict[str, Any] = {"dsn": _redact(dsn), "reachable": False}
    try:
        import psycopg
    except ImportError as exc:
        record["error"] = f"psycopg is not importable in this interpreter ({exc})"
        return record
    os.environ.setdefault("PGCONNECT_TIMEOUT", "5")
    try:
        with psycopg.connect(dsn, connect_timeout=5) as conn:
            row = conn.execute("SELECT version()").fetchone()
            record["reachable"] = True
            record["version"] = row[0] if row else None
            ttl = conn.execute(
                "SELECT raw_config_sql FROM [SHOW ZONE CONFIGURATION FOR RANGE default]"
            ).fetchone()
            if ttl and ttl[0]:
                match = re.search(r"gc\.ttlseconds\s*=\s*(\d+)", ttl[0])
                if match:
                    record["gc_ttlseconds"] = int(match.group(1))
    except Exception as exc:  # noqa: BLE001 - any failure is "not reachable", and named
        record["error"] = f"{type(exc).__name__}: {_redact(str(exc))}"
    return record


#: The micro-benchmark's shape, chosen to match the one the kernel lead ran on 2026-08-07
#: so the two numbers are comparable rather than merely adjacent.
BENCH_ROWS = 5000
BENCH_DIM = 256
BENCH_BATCH = 500


def measure_platform(dsn: str, *, benchmark_db: str, run_benchmark: bool = True) -> dict[str, Any]:
    """Why every duration in this file is a LOCAL duration, and what local costs.

    Two kinds of field live here and they are labelled, because mixing them silently is
    exactly the defect this repository exists to refuse:

    * ``measured_here: true``  — this function ran it, just now, against ``dsn``.
    * ``measured_here: false`` — transcribed from a named file, with the line, because it
      needs a credential or a region this census does not hold.
    """
    platform: dict[str, Any] = {
        "note": (
            "Context for reading every duration in this file. The census runs against a "
            "LOCAL single-node CockroachDB; no timing here is a Cloud timing, and none of "
            "them is a statement about the deployed system."
        ),
        "measured_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "regions": {
            "measured_here": False,
            "recorded_by": "docs/adr/0002-g1-platform-ground-truth.md",
            "inference": "ap-southeast-2 (Sydney) — 8 au.* Claude inference profiles",
            "database_cloud": "aws-ap-southeast-1 (Singapore), Basic tier",
            "why_the_split": (
                "ap-southeast-2 is Advanced-tier only on CockroachDB Cloud and is absent "
                "from the Basic and Standard region lists, so the development database "
                "cannot be co-located with the inference that reads it"
            ),
            "cross_region_hop": "real, and not measured under load anywhere in this repository",
            "bedrock_rerank_available_in_ap_southeast_2": False,
            "end_to_end_australian_residency": False,
        },
        "kernel_lead_local_reference": {
            "measured_here": False,
            "recorded_by": "docs/leads/kernel.md line 311",
            "seconds": 2.4,
            "operation": "DDL + 5,000 vector inserts, local node",
            "why_it_differs_from_local_benchmark": (
                "a different shape measured on a different day: this census's benchmark "
                "also builds a vector INDEX before inserting, and neither run recorded the "
                "other's dimensionality or batch size. Quote the census's own number for "
                "the census's own shape; the two are the same order of magnitude and are "
                "not the same measurement"
            ),
        },
        "cloud_basic_comparison": {
            "measured_here": False,
            "recorded_by": "docs/leads/kernel.md line 311",
            "seconds": 120,
            "seconds_is_a_floor": True,
            "operation": "9 DDL statements on CockroachDB Cloud Basic (Singapore)",
            "why_not_re_measured": (
                "this census holds no Cloud credential and takes none; re-measuring it is "
                "cloud-verify.yml's job, nightly, not a laptop's"
            ),
        },
    }
    if not run_benchmark:
        platform["local_benchmark"] = {
            "measured_here": False,
            "skipped": "not requested (--no-benchmark)",
        }
        return platform
    platform["local_benchmark"] = _run_local_benchmark(dsn, benchmark_db)
    return platform


def _vector(rng: Any) -> str:
    """One literal ``VECTOR`` value, in the text form CockroachDB parses."""
    return str([round(rng.uniform(-1, 1), 4) for _ in range(BENCH_DIM)])


def _run_local_benchmark(dsn: str, benchmark_db: str) -> dict[str, Any]:
    """DDL plus ``BENCH_ROWS`` vector inserts against the local node, timed end to end."""
    bench: dict[str, Any] = {
        "measured_here": False,
        "shape": (
            f"CREATE DATABASE/TABLE with a VECTOR({BENCH_DIM}) column and a "
            f"prefix-constrained vector index, then {BENCH_ROWS} inserts in batches of "
            f"{BENCH_BATCH}"
        ),
        "rows": BENCH_ROWS,
        "dimensions": BENCH_DIM,
        "database": benchmark_db,
    }
    try:
        import psycopg
    except ImportError as exc:
        bench["error"] = f"psycopg is not importable in this interpreter ({exc})"
        return bench
    import random

    rng = random.Random(20260810)  # noqa: S311 - a benchmark payload, not a secret
    try:
        with psycopg.connect(dsn, connect_timeout=5, autocommit=True) as admin:
            admin.execute(f'DROP DATABASE IF EXISTS "{benchmark_db}" CASCADE')
            admin.execute(f'CREATE DATABASE "{benchmark_db}"')
        bench_dsn = re.sub(r"/[^/?]+(\?|$)", f"/{benchmark_db}\\1", dsn, count=1)
        started = time.monotonic()
        with psycopg.connect(bench_dsn, connect_timeout=5, autocommit=True) as conn:
            conn.execute(
                f"CREATE TABLE bench (site UUID NOT NULL, id INT8 NOT NULL, "
                f"embedding VECTOR({BENCH_DIM}), PRIMARY KEY (site, id))"
            )
            conn.execute("CREATE VECTOR INDEX bench_ann ON bench (site, embedding)")
            ddl_seconds = round(time.monotonic() - started, 3)
            site = "3f6f4f2a-0000-4000-8000-000000000001"
            rows_started = time.monotonic()
            # ONE multi-row INSERT per batch, not `executemany`. Measured on this machine:
            # `executemany` over 5000 rows took 12.749 s against 6.483 s for the same rows
            # in batched multi-row statements — 5000 round trips against 10. The batched
            # form is what any loader would do, so it is what the benchmark measures.
            with conn.cursor() as cur:
                for offset in range(0, BENCH_ROWS, BENCH_BATCH):
                    params: list[Any] = []
                    for i in range(BENCH_BATCH):
                        params += [site, offset + i, _vector(rng)]
                    values = ", ".join(["(%s, %s, %s)"] * BENCH_BATCH)
                    cur.execute(
                        f"INSERT INTO bench (site, id, embedding) VALUES {values}",  # noqa: S608
                        params,
                    )
            insert_seconds = round(time.monotonic() - rows_started, 3)
            counted = conn.execute("SELECT count(*) FROM bench").fetchone()
        total = round(ddl_seconds + insert_seconds, 3)
        bench.update(
            {
                "measured_here": True,
                "ddl_seconds": ddl_seconds,
                "insert_seconds": insert_seconds,
                "seconds": total,
                "rows_committed": counted[0] if counted else None,
            }
        )
    except Exception as exc:  # noqa: BLE001 - any failure is "not measured", and named
        bench["error"] = f"{type(exc).__name__}: {_redact(str(exc))}"
    return bench


#: Verifications a stranger runs that pytest does not collect. They belong in the census
#: for the same reason the skips do: a check that nothing counts is a check nobody notices
#: has stopped running.
EXTERNAL_CHECKS: dict[str, dict[str, Any]] = {
    "custody_bundle_verification": {
        "what": (
            "trappoint-verify, offline, over the committed reference ledger — the Tier-1 "
            "verification in VERIFY.md, the one that needs no credential at all"
        ),
        "argv": [
            "-m",
            "trappoint_verify.cli",
            "verify",
            "--bundle",
            "evidence/reference-ledger/bundle.json",
            "--json",
        ],
        "exit_code_meaning": {
            "0": "every check ran and held",
            "2": "everything that ran held, and at least one check did not run",
            "1": "at least one check failed",
        },
    }
}


def run_external_checks() -> dict[str, Any]:
    """Run the non-pytest verifications and record their own JSON verdicts verbatim."""
    results: dict[str, Any] = {}
    for name, spec in EXTERNAL_CHECKS.items():
        record: dict[str, Any] = {
            "what": spec["what"],
            "command": "python " + " ".join(spec["argv"]),
            "exit_code_meaning": spec["exit_code_meaning"],
        }
        try:
            completed = subprocess.run(
                [sys.executable, *spec["argv"]],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=300,
                check=False,
            )
            record["exit_code"] = completed.returncode
            try:
                payload = json.loads(completed.stdout)
            except json.JSONDecodeError:
                record["error"] = "the command did not emit JSON"
                record["stderr_tail"] = (completed.stderr or completed.stdout)[-1200:]
                results[name] = record
                continue
            record["counts"] = payload.get("counts")
            record["tool"] = f"{payload.get('tool')} {payload.get('tool_version')}"
            record["not_checked"] = [
                {"check_id": entry.get("check_id"), "name": entry.get("name")}
                for entry in payload.get("not_checked", [])
            ]
            record["failed"] = [
                {"check_id": entry.get("check_id"), "name": entry.get("name")}
                for entry in payload.get("outcomes", [])
                if entry.get("verdict") == "FAIL"
            ]
        except (subprocess.SubprocessError, OSError) as exc:
            record["error"] = f"{type(exc).__name__}: {exc}"
        results[name] = record
    return results


def _tool_versions() -> dict[str, Any]:
    versions: dict[str, Any] = {
        "python": sys.version.split()[0],
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


# ── the census ───────────────────────────────────────────────────────────────────────────


def _blank_totals() -> dict[str, int]:
    return {
        "targets": 0,
        "tests": 0,
        "passed": 0,
        "failed": 0,
        "errored": 0,
        "skipped": 0,
        "xfailed": 0,
        "timed_out_targets": 0,
        "unmeasured_targets": 0,
    }


def take_census(
    targets: Sequence[Target],
    passes: Sequence[str],
    *,
    dsn: str | None,
    timeout: int,
) -> dict[str, Any]:
    """Run every target in every pass and return the document that becomes the JSON."""
    packages: dict[str, Any] = {}
    totals = {name: _blank_totals() for name in passes}
    global_reasons: dict[str, Counter[str]] = {name: Counter() for name in passes}

    for target in targets:
        row: dict[str, Any] = {
            "path": target.path,
            "kind": target.kind,
            "distribution": target.distribution,
            "runs": {},
        }
        for phase in passes:
            print(f"  {phase:>7} · {target.id} … ", end="", flush=True)
            result = run_target(target, phase, dsn=dsn, timeout=timeout)
            row["runs"][phase] = asdict(result)
            bucket = totals[phase]
            bucket["targets"] += 1
            for key in ("tests", "passed", "failed", "errored", "skipped", "xfailed"):
                bucket[key] += getattr(result, key)
            if result.timed_out:
                bucket["timed_out_targets"] += 1
            if not result.junit_written:
                bucket["unmeasured_targets"] += 1
            for entry in result.skip_reasons:
                global_reasons[phase][entry["reason"]] += entry["count"]
            print(
                f"{result.passed}P {result.failed}F {result.errored}E "
                f"{result.skipped}S in {result.duration_seconds}s"
                + (" [TIMED OUT]" if result.timed_out else "")
            )
        packages[target.id] = row

    return {
        "packages": packages,
        "totals": totals,
        "skip_reasons": {
            name: [
                {"reason": reason, "count": count}
                for reason, count in sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))
            ]
            for name, counter in global_reasons.items()
        },
    }


def recompute(doc: dict[str, Any], passes: Sequence[str]) -> None:
    """Rebuild ``totals`` and ``skip_reasons`` from ``packages``, in place.

    Called after a merge. The totals are never carried forward from the document being
    merged into: a stale total is the one number in this file a reader would not think to
    check, so it is always derived from the rows that are actually present.
    """
    totals = {name: _blank_totals() for name in passes}
    reasons: dict[str, Counter[str]] = {name: Counter() for name in passes}
    for row in doc["packages"].values():
        for name in passes:
            run = row["runs"].get(name)
            if run is None:
                continue
            bucket = totals[name]
            bucket["targets"] += 1
            for key in ("tests", "passed", "failed", "errored", "skipped", "xfailed"):
                bucket[key] += run[key]
            if run["timed_out"]:
                bucket["timed_out_targets"] += 1
            if not run["junit_written"]:
                bucket["unmeasured_targets"] += 1
            for entry in run["skip_reasons"]:
                reasons[name][entry["reason"]] += entry["count"]
    doc["totals"] = totals
    doc["skip_reasons"] = {
        name: [
            {"reason": reason, "count": count}
            for reason, count in sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))
        ]
        for name, counter in reasons.items()
    }


def build_document(
    census: dict[str, Any],
    *,
    passes: Sequence[str],
    cluster: dict[str, Any] | None,
    platform: dict[str, Any] | None,
    external_checks: dict[str, Any],
    timeout: int,
    elapsed: float,
) -> dict[str, Any]:
    """Assemble the JSON document, with the caveats that make it readable in five years."""
    return {
        "schema": SCHEMA,
        "SPDX-FileCopyrightText": "2026 MAINLINE contributors",
        "SPDX-License-Identifier": "Apache-2.0",
        "generated_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "generated_by": "scripts/qa/report_test_state.py",
        "note": (
            "A census, not a scoreboard. Every count below came out of a JUnit XML file "
            "written by a pytest subprocess this script started; nothing is estimated and "
            "nothing is rounded. A skip is only counted as a skip when the reason string is "
            "carried with it, because a skip with no reason is indistinguishable from a "
            "test that was quietly deleted."
        ),
        "tool": _tool_versions(),
        "passes": {
            "none": {
                "crdb": "none",
                "means": (
                    "no CockroachDB is obtained and trappoint-testkit's ProcessGuard "
                    "prevents any fixture from starting one; every cluster-backed test "
                    "skips with the reason its own fixture writes"
                ),
            },
            "cluster": {
                "crdb": "reuse",
                "means": (
                    "the session reuses ONE already-running node published under all four "
                    "DSN spellings; reuse mode never starts a container, so a missing node "
                    "is a skip with a reason rather than thirteen private clusters"
                ),
            },
        },
        "passes_run": list(passes),
        "per_target_timeout_seconds": timeout,
        "wall_clock_seconds": round(elapsed, 1),
        "cluster": cluster,
        "platform": platform,
        "external_checks": external_checks,
        "caveats": [
            (
                "Each target is a separate pytest process. Cross-target interference "
                "(module basename collisions, shared temp state) is therefore NOT measured "
                "here; a single whole-repository invocation may collect differently."
            ),
            (
                "`totals` is the sum over targets, not the number a single `pytest` prints. "
                "The targets are discovered by directory — every distribution owning a "
                "`tests/` directory, plus every root test root — which is a superset of "
                "whatever `testpaths` happens to say on the day."
            ),
            (
                "A target that timed out contributes whatever its JUnit XML contained at "
                "the moment it was killed, which is usually nothing. Its row carries "
                "`timed_out: true` and its counts are a floor, not a measurement."
            ),
        ],
        **census,
    }


# ── markdown ─────────────────────────────────────────────────────────────────────────────


def _fmt_run(run: dict[str, Any] | None) -> str:
    """One cell of the per-target table: the counts that are non-zero, and nothing else."""
    if run is None:
        return "—"
    if run.get("timed_out"):
        return "**TIMED OUT**"
    parts = [f"{run['passed']}P"]
    if run["failed"]:
        parts.append(f"**{run['failed']}F**")
    if run["errored"]:
        parts.append(f"**{run['errored']}E**")
    if run["skipped"]:
        parts.append(f"{run['skipped']}S")
    if run["xfailed"]:
        parts.append(f"{run['xfailed']}X")
    return " ".join(parts)


def _md_header(doc: dict[str, Any]) -> list[str]:
    tool = doc["tool"]
    return [
        "<!--",
        "SPDX-FileCopyrightText: 2026 MAINLINE contributors",
        "SPDX-License-Identifier: CC-BY-4.0",
        "-->",
        "",
        "# Test state — the census",
        "",
        "**Generated file. Do not edit.** Every number here is read out of",
        "[`qa/test-state.json`](../../qa/test-state.json), written by",
        "[`scripts/qa/report_test_state.py`](../../scripts/qa/report_test_state.py).",
        "Re-derive the whole document in one command:",
        "",
        "```",
        "python scripts/qa/report_test_state.py",
        "```",
        "",
        (
            f"Taken `{doc['generated_utc']}` with `{tool.get('pytest', 'pytest ?')}` on "
            f"Python {tool['python']} ({tool['platform']}), "
            f"{doc['wall_clock_seconds']} s of wall clock."
        ),
        "",
        *_md_merges(doc),
    ]


def _md_merges(doc: dict[str, Any]) -> list[str]:
    """Rows re-measured after the first census, named — a total nobody can date is a rumour."""
    merges = doc.get("merges") or []
    if not merges:
        return []
    lines = [
        (
            "**Some rows were re-measured after that timestamp** and the totals recomputed "
            "from every row present. Nothing is carried forward."
        ),
        "",
    ]
    for entry in merges:
        targets = ", ".join(f"`{t}`" for t in entry["targets"])
        passes = ", ".join(f"`--crdb={CRDB_MODE[p]}`" for p in entry["passes"])
        host = entry.get("dsn_host")
        where = f", dialled `{host}`" if host else ""
        lines.append(
            f"* `{entry['merged_utc']}` — {targets}, {passes}, "
            f"ceiling {entry['per_target_timeout_seconds']} s{where}"
        )
    lines.append("")
    return lines


def _md_cluster(doc: dict[str, Any], passes: Sequence[str]) -> list[str]:
    cluster = doc.get("cluster") or {}
    if "cluster" not in passes:
        return ["Passes run: " + ", ".join(f"`{p}`" for p in passes) + ".", ""]
    if cluster.get("reachable"):
        ttl = cluster.get("gc_ttlseconds")
        tail = f", `gc.ttlseconds = {ttl}`." if ttl is not None else "."
        version = cluster.get("version", "version unknown")
        return [f"Cluster pass ran against `{cluster.get('dsn')}` — {version}{tail}", ""]
    return [
        (
            f"**The cluster pass had no cluster.** `{cluster.get('dsn')}` — "
            f"{cluster.get('error', 'unreachable')}. Every cluster-backed test in that pass "
            "is a skip with a reason, and the two passes are the same measurement twice."
        ),
        "",
    ]


def _md_totals(doc: dict[str, Any], passes: Sequence[str]) -> list[str]:
    head = "| pass | targets | tests | passed | failed | errored | skipped | xfailed | timed out |"
    lines = ["## Totals", "", head, "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for name in passes:
        t = doc["totals"][name]
        lines.append(
            f"| `--crdb={CRDB_MODE[name]}` | {t['targets']} | {t['tests']} | {t['passed']} | "
            f"{t['failed']} | {t['errored']} | {t['skipped']} | {t['xfailed']} | "
            f"{t['timed_out_targets']} |"
        )
    lines += [
        "",
        "`P` passed · `F` failed · `E` errored (including collection errors) · `S` skipped ·",
        "`X` xfailed. A bold count is non-zero.",
        "",
    ]
    return lines


def _md_per_target(doc: dict[str, Any], passes: Sequence[str]) -> list[str]:
    header = "| target | kind | " + " | ".join(f"`--crdb={CRDB_MODE[p]}`" for p in passes) + " |"
    lines = ["## Per target", "", header, "|---|---|" + "---|" * len(passes)]
    for tid, row in doc["packages"].items():
        cells = " | ".join(_fmt_run(row["runs"].get(p)) for p in passes)
        lines.append(f"| `{tid}` | {row['kind']} | {cells} |")
    return lines


def _md_skips(doc: dict[str, Any], passes: Sequence[str]) -> list[str]:
    lines: list[str] = []
    for name in passes:
        reasons = doc["skip_reasons"][name]
        lines += ["", f"## Every skip reason — `--crdb={CRDB_MODE[name]}` pass", ""]
        if not reasons:
            lines.append("Nothing skipped in this pass.")
            continue
        lines += ["| count | reason string, verbatim |", "|---:|---|"]
        for entry in reasons:
            reason = entry["reason"].replace("|", "\\|")
            lines.append(f"| {entry['count']} | {reason} |")
    return lines


def _md_red(doc: dict[str, Any]) -> list[str]:
    failing = [
        (tid, name, run)
        for tid, row in doc["packages"].items()
        for name, run in row["runs"].items()
        if run["failed"] or run["errored"] or run["timed_out"]
    ]
    lines = ["", "## What is red", ""]
    if not failing:
        lines.append("No target reported a failure, an error or a timeout in any pass.")
        return lines
    for tid, name, run in failing:
        timed = ", **timed out**" if run["timed_out"] else ""
        lines += [
            f"### `{tid}` — `--crdb={CRDB_MODE[name]}`",
            "",
            (
                f"exit `{run['exit_code']}` ({run['exit_meaning']}), {run['failed']} failed, "
                f"{run['errored']} errored{timed}."
            ),
            "",
        ]
        lines += [f"* `{node}`" for node in run["failed_tests"] + run["errored_tests"]]
        if run["names_truncated"]:
            lines.append(f"* … more than {MAX_NAMED_TESTS} named; see the JSON.")
        if run["stderr_tail"]:
            lines += ["", "```", run["stderr_tail"].strip()[-1200:], "```"]
        lines.append("")
    return lines


def _md_external(doc: dict[str, Any]) -> list[str]:
    external = doc.get("external_checks") or {}
    if not external:
        return []
    lines = ["", "## Checks a stranger runs that pytest does not collect", ""]
    for name, record in external.items():
        command = record.get("command", "")
        lines += [f"### `{name}`", "", record.get("what", ""), "", "```", command, "```", ""]
        if "error" in record:
            lines += [f"**Did not run:** {record['error']}", ""]
            continue
        counts = record.get("counts") or {}
        meaning = record.get("exit_code_meaning", {}).get(str(record.get("exit_code")), "?")
        lines += [
            f"exit `{record.get('exit_code')}` — {meaning}.",
            "",
            (
                f"**{counts.get('passed')} passed, {counts.get('failed')} failed, "
                f"{counts.get('not_checked')} not checked**, of {counts.get('total')} checks."
            ),
            "",
        ]
        if record.get("not_checked"):
            named = ", ".join(
                f"`{entry['check_id']} {entry['name']}`" for entry in record["not_checked"]
            )
            lines += ["Not checked: " + named, ""]
    return lines


def _md_platform(doc: dict[str, Any]) -> list[str]:
    platform = doc.get("platform") or {}
    if not platform:
        return []
    bench = platform.get("local_benchmark", {})
    regions = platform.get("regions", {})
    cloud = platform.get("cloud_basic_comparison", {})
    lines = [
        "",
        "## Where this ran, and why every duration above is a LOCAL duration",
        "",
        "| fact | value | measured by this script? |",
        "|---|---|---|",
    ]
    if bench.get("measured_here"):
        lines.append(
            f"| DDL + {bench['rows']} `VECTOR({bench['dimensions']})` inserts, local node "
            f"| **{bench['seconds']} s** ({bench['ddl_seconds']} s DDL + "
            f"{bench['insert_seconds']} s inserts) | yes |"
        )
    else:
        why = bench.get("error") or bench.get("skipped", "not run")
        lines.append(f"| DDL + vector inserts, local node | not measured — {why} | no |")
    rerank = regions.get("bedrock_rerank_available_in_ap_southeast_2")
    residency = regions.get("end_to_end_australian_residency")
    lines += [
        (
            f"| {cloud.get('operation', 'CockroachDB Cloud Basic')} | >{cloud.get('seconds')} s "
            f"| **no** — transcribed from `{cloud.get('recorded_by')}` |"
        ),
        (
            f"| inference region | `{regions.get('inference')}` "
            f"| **no** — recorded in `{regions.get('recorded_by')}` |"
        ),
        f"| database region (Cloud) | `{regions.get('database_cloud')}` | **no** — same |",
        (
            "| Bedrock Rerank in `ap-southeast-2` | "
            f"{'available' if rerank else '**not available**'} | **no** — same |"
        ),
        (
            "| end-to-end Australian data residency | "
            f"{'yes' if residency else '**no**'} | **no** — same |"
        ),
        "",
        f"The cross-region hop between them is {regions.get('cross_region_hop')}.",
        "",
    ]
    return lines


def render_markdown(doc: dict[str, Any]) -> str:
    """Render the census as the document a reviewer reads instead of the JSON."""
    passes = doc["passes_run"]
    lines: list[str] = []
    lines += _md_header(doc)
    lines += _md_cluster(doc, passes)
    lines += _md_totals(doc, passes)
    lines += _md_per_target(doc, passes)
    lines += _md_skips(doc, passes)
    lines += _md_red(doc)
    lines += _md_external(doc)
    lines += _md_platform(doc)
    lines += ["", "## Caveats carried from the JSON", ""]
    lines += [f"* {caveat}" for caveat in doc["caveats"]]
    lines.append("")
    return "\n".join(lines)


# ── entry point ──────────────────────────────────────────────────────────────────────────


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="report_test_state.py",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--pass",
        dest="passes",
        choices=("none", "cluster", "both"),
        default="both",
        help="which pass(es) to run (default: both)",
    )
    parser.add_argument(
        "--targets",
        nargs="+",
        default=None,
        help="restrict the census to these target ids (default: every one discovered)",
    )
    parser.add_argument(
        "--dsn",
        default=os.environ.get("MAINLINE_TEST_DSN", DEFAULT_DSN),
        help="the ONE cluster the cluster pass reuses (default: $MAINLINE_TEST_DSN, else local)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=f"wall-clock ceiling per target subprocess (default: {DEFAULT_TIMEOUT_SECONDS}s)",
    )
    parser.add_argument("--out", type=Path, default=DEFAULT_JSON, help="JSON census path")
    parser.add_argument(
        "--markdown", type=Path, default=DEFAULT_MARKDOWN, help="rendered census path"
    )
    parser.add_argument(
        "--no-markdown", action="store_true", help="write only the JSON, render nothing"
    )
    parser.add_argument(
        "--render-only",
        action="store_true",
        help="do not run anything; re-render the markdown from the existing JSON",
    )
    parser.add_argument(
        "--platform-only",
        action="store_true",
        help=(
            "run no tests; take the platform measurement, merge it into the existing JSON "
            "and re-render. For refreshing the local benchmark without a two-pass census."
        ),
    )
    parser.add_argument(
        "--merge",
        action="store_true",
        help=(
            "merge the runs measured now into the existing JSON instead of replacing it, "
            "and recompute the totals. For re-measuring one target that timed out."
        ),
    )
    parser.add_argument(
        "--benchmark-db",
        default="w_qr_readme_honesty",
        help="scratch database the local benchmark drops and recreates",
    )
    parser.add_argument(
        "--no-benchmark",
        action="store_true",
        help="skip the local DDL+vector-insert benchmark (records that it was skipped)",
    )
    parser.add_argument("--list-targets", action="store_true", help="print targets and exit")
    return parser.parse_args(argv)


def _selected(targets: Iterable[Target], wanted: Sequence[str] | None) -> list[Target]:
    if not wanted:
        return list(targets)
    index = {t.id: t for t in targets}
    chosen: list[Target] = []
    for name in wanted:
        key = name.rstrip("/")
        if key in index:
            chosen.append(index[key])
            continue
        matches = [t for t in index.values() if key in t.id]
        if not matches:
            raise SystemExit(f"no target matches {name!r}; --list-targets prints them all")
        chosen.extend(matches)
    return chosen


def _update_without_running(args: argparse.Namespace) -> int:
    """``--render-only`` / ``--platform-only``: touch the document, collect no test."""
    if not args.out.is_file():
        print(f"{args.out} does not exist; nothing to update", file=sys.stderr)
        return 2
    doc = json.loads(args.out.read_text(encoding="utf-8"))
    if args.platform_only:
        doc["platform"] = measure_platform(
            args.dsn,
            benchmark_db=args.benchmark_db,
            run_benchmark=not args.no_benchmark,
        )
        doc["external_checks"] = run_external_checks()
        args.out.write_text(json.dumps(doc, indent=2, sort_keys=False) + "\n", encoding="utf-8")
        print(f"updated platform and external_checks in {args.out}")
    args.markdown.parent.mkdir(parents=True, exist_ok=True)
    args.markdown.write_text(render_markdown(doc), encoding="utf-8")
    print(f"rendered {args.markdown}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    targets = discover_targets()

    if args.list_targets:
        for target in targets:
            print(f"{target.id}\t{target.kind}\t{target.path}")
        return 0

    if args.render_only or args.platform_only:
        return _update_without_running(args)

    passes: tuple[str, ...] = PASSES if args.passes == "both" else (args.passes,)
    chosen = _selected(targets, args.targets)
    if not chosen:
        print("no targets discovered", file=sys.stderr)
        return 2

    cluster: dict[str, Any] | None = None
    if "cluster" in passes:
        cluster = probe_cluster(args.dsn)
        state = "reachable" if cluster["reachable"] else f"NOT reachable — {cluster.get('error')}"
        print(f"cluster: {cluster['dsn']} — {state}")

    print(f"census: {len(chosen)} targets x {len(passes)} pass(es)")
    started = time.monotonic()
    census = take_census(chosen, passes, dsn=args.dsn, timeout=args.timeout)
    elapsed = time.monotonic() - started

    if args.merge and args.out.is_file():
        doc = json.loads(args.out.read_text(encoding="utf-8"))
        # Merge at the RUN level, not the row level. `dict.update` on `packages` replaces
        # the whole target and silently discards the pass this invocation did not run —
        # measured the hard way: re-running one target's cluster pass deleted its
        # no-cluster row and moved the `none` totals by more than a thousand tests.
        for target_id, incoming in census["packages"].items():
            existing = doc["packages"].setdefault(target_id, {**incoming, "runs": {}})
            existing["path"] = incoming["path"]
            existing["kind"] = incoming["kind"]
            existing["distribution"] = incoming["distribution"]
            existing["runs"].update(incoming["runs"])
        merged = sorted({*doc.get("passes_run", []), *passes})
        doc["passes_run"] = [name for name in PASSES if name in merged]
        recompute(doc, doc["passes_run"])
        doc.setdefault("merges", []).append(
            {
                "merged_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "targets": [t.id for t in chosen],
                "passes": list(passes),
                "per_target_timeout_seconds": args.timeout,
                "dsn_host": dsn_host(args.dsn),
                "why": (
                    "these rows were re-measured and replaced; totals and skip_reasons were "
                    "recomputed from every row present, never carried forward"
                ),
            }
        )
    else:
        platform = measure_platform(
            args.dsn, benchmark_db=args.benchmark_db, run_benchmark=not args.no_benchmark
        )
        external_checks = run_external_checks()
        doc = build_document(
            census,
            passes=passes,
            cluster=cluster,
            platform=platform,
            external_checks=external_checks,
            timeout=args.timeout,
            elapsed=elapsed,
        )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(doc, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    print(f"wrote {args.out}")

    if not args.no_markdown:
        args.markdown.parent.mkdir(parents=True, exist_ok=True)
        args.markdown.write_text(render_markdown(doc), encoding="utf-8")
        print(f"wrote {args.markdown}")

    # One row that both timed out and wrote no JUnit is ONE unmeasured target-pass, not two.
    unmeasured = sum(
        1
        for row in doc["packages"].values()
        for name, run in row["runs"].items()
        if name in passes and (run["timed_out"] or not run["junit_written"])
    )
    for name in passes:
        t = doc["totals"][name]
        print(
            f"{name:>7}: {t['passed']} passed, {t['failed']} failed, {t['errored']} errored, "
            f"{t['skipped']} skipped, {t['xfailed']} xfailed across {t['targets']} targets"
        )
    if unmeasured:
        print(f"{unmeasured} target-pass(es) could not be measured", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
