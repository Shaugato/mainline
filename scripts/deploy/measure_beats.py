#!/usr/bin/env python
# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Measure the wall time of every demo beat through the REAL handler, over a REAL socket.

WHY THIS EXISTS
---------------
`docs/deploy/COST-BOUND.md` §2.1 assumes an invocation duration of 100-300 ms and says so
honestly. Three of the four cost terms depend on that number and they depend on it the way
nobody expects:

    rate      = concurrency / duration                            proportional to 1/duration
    egress    = rate x bytes x window                              proportional to 1/duration
    requests  = rate x window                                      proportional to 1/duration
    compute   = concurrency x memory_GB x window x price_per_GBs   INDEPENDENT of duration

So the measured duration is what makes the worst-case dollar figure right or four times
wrong, in *either* direction, and until this program ran nobody had measured it. It is also
the number that decides whether the founder's requested ~3 s `timeout` is honest: a timeout
that truncates the headline beat is a far worse defect than a larger bill.

WHAT IT DRIVES, AND WHAT IT DOES NOT RE-IMPLEMENT
------------------------------------------------
It starts `scripts/deploy/local_furl.py` as a subprocess and talks to it over TCP. That
program is the existing in-process Function URL emulator: the real
`mainline_demo_api.app.handler`, the real payload-format-2.0 encode/decode, a real socket.
**No emulator is written here.** What this file adds is a clock, an ordering discipline, and
a percentile.

Five beats, each named in the output:

    index        GET  /                              the console entry document
    asset_js     GET  /assets/index-BjAGxrVJ.js      largest non-map object, 433,396 B
    asset_map    GET  /assets/index-BjAGxrVJ.js.map  largest emittable object, 1,554,168 B
    health       GET  /v1/health
    gate_run     POST /v1/demo/gate-run              the headline four-beat gate run

...against TWO database targets: the local `trappoint-crdb` container and the CockroachDB
Cloud cluster in `aws-ap-southeast-1`, where the 40001 retry loop is live and the tail is
real. `index`, `asset_js` and `asset_map` never touch a database; measuring them under both
targets is deliberate, and their agreement across targets is the harness's own control.

ONE EMULATOR PROCESS PER BEAT, AND WHY THAT IS NOT PARANOIA
-----------------------------------------------------------
`transitions._prepare` (transitions.py:293-294) and `_demo_gate_run` (:1032-1033) set
`conn.autocommit = False` on the module-scope connection `db.py:306` opened with
`autocommit=True`, and never restore it. Measured through this harness on 2026-08-13: a
`GET /v1/health` issued after a `POST /v1/demo/gate-run` in the same process answers **503**.
A harness that interleaved beats in one process would therefore measure the defect instead of
the beat, and — worse — would look like a flaky network. Each beat gets a fresh process, and
:func:`connection_state_probe` then reproduces the 503 on purpose, in its own process, and
records it as a finding rather than routing around it.

CREDENTIAL DISCIPLINE
---------------------
The cloud DSN carries a password. It is never passed on a command line (argv is world-
readable in a process listing), never printed, and never written to the evidence. It reaches
the emulator exactly two ways: `--env-file`, which `local_furl` reads itself, or `$MAINLINE_DSN`
in the child's environment. Every byte this program captures from a child is put through
:func:`redact` before it can reach stdout, and the evidence records a target by
scheme/host/port/database only — never user, never password, never query string.

WHAT IS MEASURED AND WHAT IS EXTRAPOLATED
-----------------------------------------
Measured: wall time at the socket, response bytes, the server's own `elapsed_ms` where it
reports one, the cold cost of `import psycopg` plus the first connection in a fresh
interpreter, and this machine's sensitivity to a *fraction* of a CPU core.

Extrapolated, and labelled `extrapolation` in the payload at every point it is used: what a
Lambda in `ap-southeast-1` would see. Two corrections are applied and both are named -
(1) the round-trip correction, because this workstation is ~445 ms from the cluster and a
same-region Lambda is single-digit milliseconds from it, and (2) the CPU correction, because
Lambda allocates CPU in proportion to `memory_size` (1,769 MB = 1 vCPU) and this machine's
core is not a Graviton2 core. **No claim in the payload mixes the two categories without
saying which it is.**

EXIT CODES
----------
``0`` every requested target was reached and every beat answered its expected status ·
``1`` a beat did not answer as expected, or a target could not be reached ·
``2`` usage.
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import hashlib
import http.client
import json
import math
import os
import platform
import re
import statistics
import subprocess
import sys
import tempfile
import time
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

EXIT_OK: Final = 0
EXIT_FAILED: Final = 1
EXIT_USAGE: Final = 2

REPO_ROOT: Final = Path(__file__).resolve().parents[2]
LOCAL_FURL: Final = REPO_ROOT / "scripts" / "deploy" / "local_furl.py"
#: The distribution `local_furl` imports the handler from; the same default it uses.
DEFAULT_APP_SRC: Final = REPO_ROOT / "verticals" / "mainline" / "apps" / "demo-api" / "src"
DEFAULT_WEB_ROOT: Final = REPO_ROOT / "verticals" / "mainline" / "apps" / "console" / "dist"
DEFAULT_OUT: Final = REPO_ROOT / "evidence" / "deploy" / "cost" / "latency-baseline.json"

SCHEMA_ID: Final = "mainline/deploy/latency-baseline/1"

#: The local node this repository pins. `127.0.0.1` and NOT `localhost` on purpose, and the
#: difference is 10 seconds: `localhost` resolves to `::1` first on this Windows host, the
#: container publishes `127.0.0.1:26257` only, and libpq waits the whole of its
#: `connect_timeout` on the AF_INET6 address before it falls back. `db.py`'s
#: `CONNECT_TIMEOUT_SECONDS = 10` is therefore paid IN FULL on every cold connect that names
#: `localhost`. Measured 2026-08-13: 8.7 ms via `127.0.0.1`, 10,078 ms via `localhost` at
#: connect_timeout=10, 30,075 ms at connect_timeout=30. That is a workstation artefact, not a
#: Lambda property, and mixing it into a baseline would have overstated cold start by 10 s.
DEFAULT_LOCAL_DSN: Final = "postgresql://root@127.0.0.1:26257/{database}?sslmode=disable"

#: AWS allocates CPU to a Lambda in linear proportion to `memory_size`; 1,769 MB buys one
#: full vCPU. Documented by AWS, not measured here, and used only inside values the payload
#: labels `extrapolation`.
LAMBDA_FULL_VCPU_MB: Final = 1769

#: A same-region hop (Lambda in ap-southeast-1 to a CockroachDB Cloud cluster in
#: ap-southeast-1). NOT measured by this program - nothing here runs in that region. It is a
#: conservative round number used as the second term of the round-trip correction, and the
#: correction is reported at BOTH values below so a reader can see how little it matters.
IN_REGION_RTT_MS: Final = 2.0
IN_REGION_RTT_MS_PESSIMISTIC: Final = 5.0

_CREDENTIAL_RE: Final = re.compile(r"(?P<scheme>[a-zA-Z][a-zA-Z0-9+.-]*://)[^\s/@]*@")


def redact(text: str) -> str:
    """Replace every ``scheme://userinfo@`` with ``scheme://<redacted>@``.

    Applied to EVERY byte captured from a child process before it can reach stdout or a
    file. `local_furl` already prints a password-redacted DSN in its banner; this is the
    second gate, because "the other program redacts it" is a property that can regress.
    """
    return _CREDENTIAL_RE.sub(lambda m: f"{m.group('scheme')}<redacted>@", text)


def describe_dsn(dsn: str) -> dict[str, Any]:
    """A DSN reduced to the parts that are not secret: scheme, host, port, database.

    Never the user, never the password, never the query string. The host is already a
    recorded identifier elsewhere in `evidence/deploy/` (cloud-chain.json, cloud-seed.json),
    so recording it here is consistent rather than a new disclosure; the sha256 prefix is
    carried beside it so two runs can be shown to have hit the same cluster even by a reader
    who is handed only the digest.
    """
    split = urllib.parse.urlsplit(dsn)
    host = split.hostname or ""
    return {
        "scheme": split.scheme,
        "host": host,
        "port": split.port,
        "database": split.path.lstrip("/") or None,
        "host_sha256_12": hashlib.sha256(host.encode("utf-8")).hexdigest()[:12],
    }


# =====================================================================================
# the beats
# =====================================================================================


@dataclass(frozen=True, slots=True)
class Beat:
    name: str
    method: str
    path: str
    body: bytes | None
    expect_status: int
    touches_database: bool
    why: str


BEATS: Final[tuple[Beat, ...]] = (
    Beat(
        name="index",
        method="GET",
        path="/",
        body=None,
        expect_status=200,
        touches_database=False,
        why="the document a judge's browser asks for first",
    ),
    Beat(
        name="asset_js",
        method="GET",
        path="/assets/index-BjAGxrVJ.js",
        body=None,
        expect_status=200,
        touches_database=False,
        why="largest non-map object in the served tree (M5: 433,396 B)",
    ),
    Beat(
        name="asset_map",
        method="GET",
        path="/assets/index-BjAGxrVJ.js.map",
        body=None,
        expect_status=200,
        touches_database=False,
        why="largest emittable object in the served tree (M4: 1,554,168 B)",
    ),
    Beat(
        name="health",
        method="GET",
        path="/v1/health",
        body=None,
        expect_status=200,
        touches_database=True,
        why="the cheapest database beat: one connection, one fingerprint read",
    ),
    Beat(
        name="gate_run",
        method="POST",
        path="/v1/demo/gate-run",
        body=b"{}",
        expect_status=200,
        touches_database=True,
        why="the headline four-beat gate run; the beat that decides the timeout",
    ),
)


# =====================================================================================
# statistics
# =====================================================================================


def nearest_rank(sorted_values: list[float], quantile: float) -> float:
    """The nearest-rank percentile: the ceil(q*N)-th smallest observation.

    Named rather than assumed. `statistics.quantiles` interpolates, which invents a value
    between two observations; for a latency tail an interpolated p99 is a number nobody
    measured. Every percentile in the evidence is an observation that actually happened.
    """
    if not sorted_values:
        raise ValueError("no samples")
    rank = max(1, math.ceil(quantile * len(sorted_values)))
    return sorted_values[min(rank, len(sorted_values)) - 1]


def summarise(samples: list[float]) -> dict[str, Any]:
    ordered = sorted(samples)
    count = len(ordered)
    return {
        "n": count,
        "estimator": "nearest-rank (ceil(q*N)-th smallest observation; never interpolated)",
        "min_ms": round(ordered[0], 3),
        "p50_ms": round(nearest_rank(ordered, 0.50), 3),
        "p95_ms": round(nearest_rank(ordered, 0.95), 3),
        "p99_ms": round(nearest_rank(ordered, 0.99), 3),
        "max_ms": round(ordered[-1], 3),
        "mean_ms": round(statistics.fmean(ordered), 3),
        "stdev_ms": round(statistics.stdev(ordered), 3) if count > 1 else None,
        # With fewer than 100 samples the nearest-rank p99 IS the maximum. Saying so is the
        # difference between a percentile and a number shaped like one.
        "p99_is_max": count < 100,
    }


# =====================================================================================
# the emulator, one process per beat
# =====================================================================================


@dataclass
class Target:
    name: str
    dsn: str | None = None
    env_file: Path | None = None
    dsn_key: str = "COCKROACH_DSN"
    database: str | None = None
    scenario: dict[str, str] = field(default_factory=dict)
    described: dict[str, Any] = field(default_factory=dict)


@contextlib.contextmanager
def emulator(target: Target, web_root: Path) -> Any:
    """Start `local_furl.py` on a free port; yield its base URL; stop it.

    The DSN travels in the child's environment or in `--env-file`, never in argv.
    """
    with tempfile.TemporaryDirectory(prefix="mainline-measure-") as scratch:
        ready = Path(scratch) / "base-url.txt"
        env = {k: v for k, v in os.environ.items() if k != "MAINLINE_DSN"}
        env["MAINLINE_WEB_ROOT"] = str(web_root)
        env.update(target.scenario)
        argv = [
            sys.executable,
            str(LOCAL_FURL),
            "--port",
            "0",
            "--quiet",
            "--require-web-root",
            "--ready-file",
            str(ready),
            "--web-root",
            str(web_root),
        ]
        if target.env_file is not None:
            argv += ["--env-file", str(target.env_file), "--dsn-key", target.dsn_key]
            if target.database:
                argv += ["--database", target.database]
        elif target.dsn is not None:
            env["MAINLINE_DSN"] = target.dsn
        proc = subprocess.Popen(
            argv,
            cwd=str(REPO_ROOT),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        try:
            base = _await_ready(proc, ready)
            yield base
        finally:
            proc.terminate()
            with contextlib.suppress(subprocess.TimeoutExpired):
                proc.wait(timeout=15)
            if proc.poll() is None:  # pragma: no cover - only if terminate was ignored
                proc.kill()
            if proc.stdout is not None:
                proc.stdout.close()


def _await_ready(proc: subprocess.Popen[str], ready: Path, *, seconds: float = 60.0) -> str:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if ready.exists():
            text = ready.read_text(encoding="utf-8").strip()
            if text:
                return text
        if proc.poll() is not None:
            captured = proc.stdout.read() if proc.stdout is not None else ""
            raise RuntimeError(
                f"local_furl exited {proc.returncode} before it listened:\n"
                f"{redact(captured)[-2000:]}"
            )
        time.sleep(0.05)
    raise RuntimeError("local_furl did not write its ready file within 60 s")


@dataclass(frozen=True, slots=True)
class Response:
    status: int
    body: bytes
    elapsed_ms: float


class Client:
    """One keep-alive HTTP/1.1 connection, reopened when the server closes it.

    `local_furl._Server` speaks HTTP/1.1, so keep-alive is real. Reusing the connection is
    deliberate: what is being measured is the handler's contribution, and a fresh TCP
    handshake per sample would add this machine's loopback setup cost to every number
    without adding anything a Lambda pays (AWS terminates TLS in front of the function).
    """

    def __init__(self, base_url: str, timeout: float) -> None:
        split = urllib.parse.urlsplit(base_url)
        self._host = split.hostname or "127.0.0.1"
        self._port = split.port or 80
        self._timeout = timeout
        self._conn: http.client.HTTPConnection | None = None

    def _connection(self) -> http.client.HTTPConnection:
        if self._conn is None:
            self._conn = http.client.HTTPConnection(self._host, self._port, timeout=self._timeout)
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def request(self, beat: Beat) -> Response:
        headers = {"accept": "*/*"}
        if beat.body is not None:
            headers["content-type"] = "application/json"
        started = time.perf_counter()
        try:
            conn = self._connection()
            conn.request(beat.method, beat.path, body=beat.body, headers=headers)
            raw = conn.getresponse()
            payload = raw.read()
            status = raw.status
        except (http.client.HTTPException, OSError):
            # A dropped keep-alive is a transport event, not a latency observation. Reopen
            # and re-issue exactly once; a second failure propagates.
            self.close()
            started = time.perf_counter()
            conn = self._connection()
            conn.request(beat.method, beat.path, body=beat.body, headers=headers)
            raw = conn.getresponse()
            payload = raw.read()
            status = raw.status
        return Response(status, payload, (time.perf_counter() - started) * 1000.0)


def server_elapsed_ms(beat: Beat, body: bytes) -> float | None:
    """The server's own timer, where the beat reports one. Never a substitute for the clock."""
    if beat.name not in ("gate_run", "health"):
        return None
    try:
        document = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        return None
    if beat.name == "health":
        seconds = document.get("seconds")
        return float(seconds) * 1000.0 if isinstance(seconds, (int, float)) else None
    data = document.get("data", document)
    value = data.get("elapsed_ms") if isinstance(data, dict) else None
    return float(value) if isinstance(value, (int, float)) else None


def gate_run_census(bodies: list[bytes]) -> dict[str, Any]:
    """What EVERY gate run in the sample said about itself, as counts and distributions.

    Recording one sample's verdict and calling it the run's verdict is the defect class this
    repository keeps re-finding: a summary that cannot disagree with itself. It is not
    hypothetical here. On 2026-08-13 another wave landed the BLOCKER 1 credential fix DURING
    a 100-sample cloud run, so the samples straddled two regimes -- beat 4 refusing `23503`
    and beat 4 admitting -- and a single-sample record showed only the last one. This function
    counts every sample, so a mixed run is visible as a mixed run.
    """
    outcomes: dict[str, int] = {}
    verdicts: dict[str, int] = {}
    persisted: dict[str, int] = {}
    sqlstates: dict[str, dict[str, int]] = {}
    elapsed: dict[str, list[float]] = {}
    failures: dict[str, int] = {}
    unparsed = 0
    for body in bodies:
        try:
            data = json.loads(body).get("data", {})
        except (ValueError, UnicodeDecodeError):
            unparsed += 1
            continue
        outcomes[str(data.get("outcome"))] = outcomes.get(str(data.get("outcome")), 0) + 1
        verdicts[str(data.get("verdict"))] = verdicts.get(str(data.get("verdict")), 0) + 1
        persisted[str(data.get("persisted"))] = persisted.get(str(data.get("persisted")), 0) + 1
        for message in data.get("failures") or []:
            failures[str(message)] = failures.get(str(message), 0) + 1
        for entry in data.get("beats") or []:
            if not isinstance(entry, dict):
                continue
            name = str(entry.get("name"))
            state = str(entry.get("sqlstate"))
            sqlstates.setdefault(name, {})
            sqlstates[name][state] = sqlstates[name].get(state, 0) + 1
            value = entry.get("elapsed_ms")
            if isinstance(value, (int, float)):
                elapsed.setdefault(name, []).append(float(value))
    return {
        "samples_parsed": len(bodies) - unparsed,
        "samples_unparsed": unparsed,
        "outcome_counts": outcomes,
        "verdict_counts": verdicts,
        "persisted_counts": persisted,
        "beat_sqlstate_counts": sqlstates,
        "beat_elapsed_ms": {name: summarise(values) for name, values in sorted(elapsed.items())},
        "failure_counts": failures,
        "one_regime": len(verdicts) == 1 and all(len(s) == 1 for s in sqlstates.values()),
    }


def drive(
    beat: Beat, base_url: str, *, warmup: int, samples: int, timeout: float
) -> dict[str, Any]:
    """Warm the process, then take *samples* observations of one beat."""
    client = Client(base_url, timeout)
    record: dict[str, Any] = {
        "beat": beat.name,
        "method": beat.method,
        "path": beat.path,
        "why": beat.why,
        "touches_database": beat.touches_database,
        "expect_status": beat.expect_status,
        "warmup_discarded": warmup,
    }
    try:
        cold = client.request(beat)
        record["cold_first_request_ms"] = round(cold.elapsed_ms, 3)
        record["cold_status"] = cold.status
        for _ in range(max(0, warmup - 1)):
            client.request(beat)
        walls: list[float] = []
        server: list[float] = []
        statuses: set[int] = set()
        sizes: set[int] = set()
        # Bodies are retained ONLY for the gate run, and parsed after the loop rather than
        # inside it. A gate-run body is ~9 KB; an asset_map body is 1.5 MB and 200 of them
        # would be 300 MB held for nothing.
        bodies: list[bytes] = []
        for _ in range(samples):
            answer = client.request(beat)
            walls.append(answer.elapsed_ms)
            statuses.add(answer.status)
            sizes.add(len(answer.body))
            reported = server_elapsed_ms(beat, answer.body)
            if reported is not None:
                server.append(reported)
            if beat.name == "gate_run":
                bodies.append(answer.body)
    finally:
        client.close()
    record["statuses_observed"] = sorted(statuses)
    record["status_ok"] = statuses == {beat.expect_status}
    record["response_bytes"] = sorted(sizes)
    record["response_bytes_stable"] = len(sizes) == 1
    record["wall_ms"] = summarise(walls)
    if server:
        record["server_reported_ms"] = summarise(server)
        record["harness_overhead_p50_ms"] = round(
            record["wall_ms"]["p50_ms"] - record["server_reported_ms"]["p50_ms"], 3
        )
    if bodies:
        record["gate_run"] = gate_run_census(bodies)
    return record


# =====================================================================================
# the cold cost, in a fresh interpreter
# =====================================================================================

#: Runs in a child interpreter with $MAINLINE_DSN in its environment. It prints ONE line of
#: JSON carrying only durations - never the DSN, never a row, never a hostname.
_COLD_PROGRAM: Final = r"""
import json, os, time
t0 = time.perf_counter()
import psycopg
t1 = time.perf_counter()
conn = psycopg.connect(os.environ["MAINLINE_DSN"], connect_timeout=15, autocommit=True)
t2 = time.perf_counter()
rtts = []
for _ in range(int(os.environ["MAINLINE_RTT_SAMPLES"])):
    s = time.perf_counter()
    conn.execute("SELECT 1").fetchone()
    rtts.append((time.perf_counter() - s) * 1000.0)
conn.close()
print(json.dumps({
    "import_psycopg_ms": (t1 - t0) * 1000.0,
    "first_connect_ms": (t2 - t1) * 1000.0,
    "rtt_ms": rtts,
}))
"""


def cold_probe(dsn: str, *, samples: int, rtt_samples: int) -> dict[str, Any]:
    """Time `import psycopg` and the first connection, in a NEW interpreter, *samples* times.

    A fresh process each time is the whole point: an in-process loop would measure a warm
    import cache and report a cold start that no execution environment ever pays.
    """
    imports: list[float] = []
    connects: list[float] = []
    rtts: list[float] = []
    env = dict(os.environ)
    env["MAINLINE_DSN"] = dsn
    env["MAINLINE_RTT_SAMPLES"] = str(rtt_samples)
    for _ in range(samples):
        result = subprocess.run(
            [sys.executable, "-c", _COLD_PROGRAM],
            cwd=str(REPO_ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(f"cold probe failed: {redact(result.stderr)[-1500:]}")
        document = json.loads(result.stdout.strip().splitlines()[-1])
        imports.append(document["import_psycopg_ms"])
        connects.append(document["first_connect_ms"])
        rtts.extend(document["rtt_ms"])
    return {
        "samples": samples,
        "fresh_interpreter_per_sample": True,
        "import_psycopg_ms": summarise(imports),
        "first_connect_ms": summarise(connects),
        "select_1_round_trip_ms": summarise(rtts),
        "note": (
            "import_psycopg is pure CPU and therefore scales with memory_size; first_connect "
            "is dominated by network round trips (TLS handshake) and does not."
        ),
    }


# =====================================================================================
# the CPU-share probe: what a FRACTION of a core does to a CPU-bound beat
# =====================================================================================

#: Pins itself to logical CPU 0 and then either spins forever (`spin`) or runs the handler's
#: real hot CPU operation - `json.dumps` of the largest served object, which is M15 - a fixed
#: number of times and prints the elapsed milliseconds.
_CPU_PROGRAM: Final = r"""
import json, os, sys, time


def pin_to_core_zero():
    if hasattr(os, "sched_setaffinity"):
        os.sched_setaffinity(0, {0})
        return "sched_setaffinity"
    if sys.platform == "win32":
        import ctypes
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        # HANDLE is pointer-wide. Without these two lines ctypes marshals the
        # GetCurrentProcess pseudo-handle (HANDLE)-1 through a 32-bit c_int and the call
        # fails with ERROR_INVALID_HANDLE on win-amd64.
        kernel32.GetCurrentProcess.restype = ctypes.c_void_p
        kernel32.SetProcessAffinityMask.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
        if not kernel32.SetProcessAffinityMask(kernel32.GetCurrentProcess(), 1):
            raise OSError(ctypes.get_last_error())
        return "SetProcessAffinityMask"
    raise OSError("no affinity API")


mechanism = pin_to_core_zero()
if sys.argv[1] == "spin":
    print(json.dumps({"mechanism": mechanism}), flush=True)
    while True:
        pass
payload = open(os.environ["MAINLINE_CPU_ASSET"], "rb").read().decode("utf-8", "replace")
rounds = int(sys.argv[2])
for _ in range(3):
    json.dumps({"body": payload})
best = None
started = time.perf_counter()
for _ in range(rounds):
    s = time.perf_counter()
    json.dumps({"body": payload})
    d = (time.perf_counter() - s) * 1000.0
    best = d if best is None else min(best, d)
total = (time.perf_counter() - started) * 1000.0
print(json.dumps({"mechanism": mechanism, "best_ms": best, "mean_ms": total / rounds}))
"""


def _cpu_worker(asset: Path, rounds: int) -> tuple[float, float]:
    env = dict(os.environ)
    env["MAINLINE_CPU_ASSET"] = str(asset)
    result = subprocess.run(
        [sys.executable, "-c", _CPU_PROGRAM, "work", str(rounds)],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=1800,
        check=True,
    )
    document = json.loads(result.stdout.strip().splitlines()[-1])
    return float(document["mean_ms"]), float(document["best_ms"])


def cpu_share_probe(asset: Path, *, rounds: int, competitors: tuple[int, ...]) -> dict[str, Any]:
    """Measure the handler's hot CPU op at 1, 1/2, 1/3 ... of ONE core.

    Lambda gives a function a FRACTION of a vCPU in linear proportion to `memory_size`
    (1,769 MB = 1 vCPU), and it delivers that fraction by time-slicing. This reproduces the
    same shape locally: the worker pins itself to logical CPU 0, and *k* competitor processes
    pin themselves to the SAME core and spin, so the worker receives 1/(k+1) of it.

    What this establishes is narrow and stated as such: whether wall time on THIS machine is
    inversely proportional to the share of a core a CPU-bound task receives. It does not, and
    cannot, tell anyone what an arm64 Graviton2 core does. Every use of the slope downstream
    is labelled `extrapolation`.
    """
    if not asset.is_file():
        return {"supported": False, "reason": f"{asset} is not a file"}
    if not hasattr(os, "sched_setaffinity") and sys.platform != "win32":
        return {"supported": False, "reason": f"no CPU-affinity API on {sys.platform}"}
    points: list[dict[str, Any]] = []
    baseline: float | None = None
    for count in competitors:
        spinners: list[subprocess.Popen[str]] = []
        try:
            for _ in range(count):
                spinners.append(
                    subprocess.Popen(
                        [sys.executable, "-c", _CPU_PROGRAM, "spin"],
                        cwd=str(REPO_ROOT),
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                    )
                )
            if spinners:
                time.sleep(0.75)
            mean, best = _cpu_worker(asset, rounds)
        finally:
            for spinner in spinners:
                spinner.kill()
                with contextlib.suppress(subprocess.TimeoutExpired):
                    spinner.wait(timeout=10)
                if spinner.stdout is not None:
                    spinner.stdout.close()
        if baseline is None:
            baseline = mean
        share = 1.0 / (count + 1)
        points.append(
            {
                "competitors_on_the_same_core": count,
                "core_share": round(share, 4),
                "mean_ms": round(mean, 3),
                "best_ms": round(best, 3),
                "slowdown_vs_full_core": round(mean / baseline, 3),
                "slowdown_if_perfectly_proportional": round(1.0 / share, 3),
                "equivalent_lambda_memory_mb": round(LAMBDA_FULL_VCPU_MB * share),
            }
        )
    return {
        "supported": True,
        "operation": "json.dumps({'body': <largest non-map served object, decoded>})",
        "operation_why": "M15: the handler's own hot CPU op when it answers with that object",
        "rounds_per_point": rounds,
        "statistic": (
            "MEAN over the whole run, which is throughput under time-slicing. best_ms is "
            "carried beside it and is NOT used for the slope: a minimum finds the one round "
            "that fitted inside a single scheduler quantum unpreempted, so at 1/7 of a core "
            "it still reports full-core speed. Measured 2026-08-13: best-of-rounds gave a "
            "1.08x slowdown at a 0.143 share where the mean gives the real figure."
        ),
        "points": points,
        "claim": (
            "measured on THIS machine only: wall time of a CPU-bound task against the share of "
            "one core it receives"
        ),
        "not_a_claim": (
            "nothing here measures an arm64 Graviton2 core, an AWS scheduler, or the demo-api "
            "handler under a real Lambda"
        ),
    }


# =====================================================================================
# the connection-state probe: the defect a per-beat process would otherwise hide
# =====================================================================================


def connection_state_probe(target: Target, web_root: Path, timeout: float) -> dict[str, Any]:
    """gate-run, then health, in ONE process. Records what actually comes back.

    `transitions._prepare` sets `conn.autocommit = False` on the module-scope connection that
    `db.py:306` opened with `autocommit=True`, and never restores it. This probe is the
    falsifiable statement of that: if the next request after a gate run answers 200, the
    finding is gone and this evidence says so on its own.
    """
    by_name = {beat.name: beat for beat in BEATS}
    gate, health = by_name["gate_run"], by_name["health"]
    with emulator(target, web_root) as base:
        client = Client(base, timeout)
        try:
            first = client.request(gate)
            second = client.request(health)
            third = client.request(gate)
        finally:
            client.close()
    detail = ""
    if second.status != 200:
        with contextlib.suppress(ValueError, UnicodeDecodeError):
            detail = str(json.loads(second.body).get("detail") or "")[:300]
    return {
        "sequence": ["POST /v1/demo/gate-run", "GET /v1/health", "POST /v1/demo/gate-run"],
        "statuses": [first.status, second.status, third.status],
        "health_after_gate_run_is_200": second.status == 200,
        "health_after_gate_run_detail": redact(detail),
        "finding": (
            "transitions._prepare (transitions.py:293-294) and _demo_gate_run (:1032-1033) set "
            "conn.autocommit = False on the shared module-scope connection and never restore "
            "it; db.py:306 opened it autocommit=True and health.py:106 documents that "
            "assumption. On a warm container the next non-gate-run request is stranded INTRANS."
        ),
        "owner": "NOT owned by the cost-bound wave; recorded here because it was measured here",
    }


# =====================================================================================
# the model, and the recommendation
# =====================================================================================


#: How many CLIENT round trips one gate run costs, counted a second way so the derived figure
#: has something to disagree with. NOT read off the source: measured on 2026-08-13 by
#: snapshotting `crdb_internal.node_statement_statistics` for `application_name =
#: 'mainline-demo-api'` on the local node either side of exactly ONE warm gate run, which
#: attributed **79 executed statements** to it. Those 79 are not 79 round trips: CockroachDB
#: records the statements a UDF, trigger or stored procedure runs SERVER-SIDE, and it renders
#: those database-qualified (`w_w1_cost.mainline.permit`) while the ones the client actually
#: wrote stay unqualified (`mainline.permit`). Splitting the delta on that boundary gives
#: **24 client statements**. Transaction control does not appear in those statistics at all
#: and every one of them is still a round trip: `BEGIN`, three
#: SAVEPOINT/ROLLBACK-TO/RELEASE triplets and four `ROLLBACK`s -- 14 more. 24 + 14 = **38** on
#: the path where beat 4 is ADMITTED; **36** where it refuses at the foreign key and so skips
#: the merge CALL and the merge-record read.
#:
#: **36 is deliberately the low side.** Both targets now admit beat 4 -- BLOCKER 1's 23503 was
#: fixed on the cloud cluster on 2026-08-13 -- so 38 is the count that applies today. The
#: correction below SUBTRACTS trips x RTT from a measured figure, so a smaller count subtracts
#: less and leaves a larger in-region estimate, and a timeout chosen from an optimistic
#: correction truncates the demo while one chosen from a pessimistic correction costs nothing.
#:
#: Recorded to two significant figures on purpose. The classification above is a judgement
#: about statement text, and a number carried to the unit would claim a precision it has not
#: got. What it is for is to catch a derived figure that is wrong by a FACTOR.
MEASURED_ROUND_TRIPS: Final = 36


def round_trip_model(
    local_gate: dict[str, Any],
    cloud_gate: dict[str, Any],
    local_rtt: dict[str, Any],
    cloud_rtt: dict[str, Any],
) -> dict[str, Any]:
    """Derive the gate run's client-server round-trip count, then correct for a same-region hop.

    Two measurements of the SAME code differing only in the network between the handler and
    the cluster give the number of round trips directly:

        round_trips = (cloud_p50 - local_p50) / (cloud_rtt_p50 - local_rtt_p50)

    THE WEAKNESS, STATED RATHER THAN SMOOTHED. The path to `aws-ap-southeast-1` from this
    workstation is not stable: `SELECT 1` measured 220.7 ms in one session and 445 ms in
    another on 2026-08-13, and the derived trip count moves by 2x with it. So the derivation
    is not trusted on its own. It is computed, it is compared against
    :data:`MEASURED_ROUND_TRIPS` -- counted from the cluster's own statement statistics, and
    immune to the network -- and the figure carried forward into the recommendation is the
    LEAST FAVOURABLE of three: the two corrections and the local measurement, which is a floor
    because CockroachDB Cloud Basic is a shared serverless tier and is not faster per statement
    than a dedicated local node.

    Every value produced here is an EXTRAPOLATION and every one of them says so.
    """
    local_rtt_ms = local_rtt["p50_ms"]
    cloud_rtt_ms = cloud_rtt["p50_ms"]
    delta_rtt = cloud_rtt_ms - local_rtt_ms
    derived = (cloud_gate["p50_ms"] - local_gate["p50_ms"]) / delta_rtt if delta_rtt > 0 else 0.0

    def corrected(percentile: str, trips: float, rtt: float) -> float:
        return cloud_gate[percentile] - trips * (cloud_rtt_ms - rtt)

    from_derived = corrected("p99_ms", derived, IN_REGION_RTT_MS)
    from_counted = corrected("p99_ms", MEASURED_ROUND_TRIPS, IN_REGION_RTT_MS)
    used = max(from_derived, from_counted)
    return {
        "kind": "extrapolation",
        "method": (
            "two measurements of the same handler against clusters at different distances; the "
            "difference divided by the round-trip difference is the round-trip count"
        ),
        "local_rtt_ms": local_rtt,
        "cloud_rtt_ms": cloud_rtt,
        "derived_round_trips": round(derived, 1),
        "counted_round_trips": MEASURED_ROUND_TRIPS,
        "counted_round_trips_method": (
            "crdb_internal.node_statement_statistics for application_name='mainline-demo-api', "
            "snapshotted either side of exactly one warm gate run on the local node: 79 "
            "statements executed, of which 24 were written by the client (the rest are "
            "database-qualified because CockroachDB expanded them inside a UDF, trigger or "
            "stored procedure and they never left the server), plus 14 transaction-control "
            "statements that the statistics do not record and psycopg still sends"
        ),
        "the_two_methods_agree_within": (
            f"{abs(derived - MEASURED_ROUND_TRIPS) / MEASURED_ROUND_TRIPS:.0%} of the counted "
            f"figure"
        ),
        "in_region_rtt_ms_assumed": IN_REGION_RTT_MS,
        "in_region_rtt_ms_pessimistic": IN_REGION_RTT_MS_PESSIMISTIC,
        "gate_run_in_region_p50_ms_from_derived_trips": round(
            corrected("p50_ms", derived, IN_REGION_RTT_MS), 1
        ),
        "gate_run_in_region_p99_ms_from_derived_trips": round(from_derived, 1),
        "gate_run_in_region_p99_ms_from_counted_trips": round(from_counted, 1),
        "gate_run_in_region_p99_ms_pessimistic_rtt": round(
            corrected("p99_ms", derived, IN_REGION_RTT_MS_PESSIMISTIC), 1
        ),
        "local_measured_p50_ms": local_gate["p50_ms"],
        "local_measured_p99_ms": local_gate["p99_ms"],
        "gate_run_in_region_p99_ms": round(used, 1),
        "gate_run_in_region_p99_ms_basis": (
            "max(derived-trip correction, counted-trip correction) -- the less favourable of "
            "the two, because a timeout chosen from an optimistic correction truncates the "
            "demo and one chosen from a pessimistic correction costs nothing but a longer hang"
        ),
        "why_the_local_p99_is_NOT_in_that_max": (
            "it is a measurement of a DIFFERENT cluster and it is not a floor on what a "
            "same-region Lambda would see against CockroachDB Cloud. Its role is the cross "
            "check below, on the p50, where it is not contaminated"
        ),
        "cross_check": (
            "the counted-trip correction leaves a residue over the local p50 -- "
            f"{corrected('p50_ms', MEASURED_ROUND_TRIPS, IN_REGION_RTT_MS):.0f} ms in region "
            f"against {local_gate['p50_ms']:.0f} ms locally. That residue is NOT error: "
            "CockroachDB Cloud Basic is a shared serverless tier and executes the same gate "
            "run more slowly than a dedicated local container. The derived-trip figure absorbs "
            "that residue into the network term, which is exactly why it comes out larger than "
            "the counted figure and why the counted one is the conservative choice"
        ),
    }


def recommend(
    cloud_gate: dict[str, Any],
    model: dict[str, Any],
    colds: dict[str, dict[str, Any]],
    cpu_slope: float | None,
    current: dict[str, Any],
) -> dict[str, Any]:
    """Turn the measurements into a `timeout` and a `memory_size`, with the multiples shown."""
    measured_p99 = cloud_gate["p99_ms"]
    in_region_p99 = model["gate_run_in_region_p99_ms"]

    # `import psycopg` is the same operation whichever cluster the probe went on to reach, so
    # the two targets give two independent samples of it and the SMALLER is the right input:
    # it is the least CPU-contended estimate of a full-core import, and the CPU correction
    # below multiplies by the memory/vCPU ratio. Taking the larger would apply a contention
    # penalty this workstation happened to have AND the Lambda's fractional-core penalty to
    # the same number, which is the same slowdown counted twice.
    import_samples = {name: cold["import_psycopg_ms"]["p99_ms"] for name, cold in colds.items()}
    import_p99 = min(import_samples.values())
    connect_p99 = colds["cloud"]["first_connect_ms"]["p99_ms"]

    # Cold start, in region, at 512 MB. Two terms, each labelled:
    #   * the import is pure CPU, so it is scaled by the memory/vCPU ratio (extrapolation),
    #     times the slope the CPU-share probe measured -- CLAMPED AT 1.0. Perfect
    #     proportionality is AWS's documented relationship; the probe's job is to CONFIRM it
    #     and, if this machine is worse than proportional, to make the bound larger. It is not
    #     allowed to make a safety bound SMALLER, because a local scheduler artefact is not
    #     evidence that AWS will be generous. The clamp is not theoretical: two runs of the
    #     same probe on 2026-08-13 measured slopes of 1.083 and 0.838, the second because its
    #     six-competitor point under-delivered contention on a machine that was already busy.
    #   * the connect is nearly all TLS round trips, so it is RTT-corrected the same way the
    #     gate run is (extrapolation), with a floor because the handshake also costs CPU.
    measured_slope = cpu_slope if cpu_slope and cpu_slope > 0 else None
    slope = max(1.0, measured_slope) if measured_slope is not None else 1.0
    cpu_factor_512 = LAMBDA_FULL_VCPU_MB / 512.0 * slope
    cpu_factor_256 = LAMBDA_FULL_VCPU_MB / 256.0 * slope
    import_512 = import_p99 * cpu_factor_512
    import_256 = import_p99 * cpu_factor_256
    connect_in_region = max(connect_p99 * 0.10, 60.0)
    cold_512 = in_region_p99 + import_512 + connect_in_region
    cold_256 = in_region_p99 + import_256 + connect_in_region
    cold_256_flat = in_region_p99 + import_p99 * LAMBDA_FULL_VCPU_MB / 256.0 + connect_in_region

    # The binding case is the worst modelled one: cold, at the smaller memory, with a tail
    # twice as bad as this workstation's. The recommendation is the smallest whole second
    # that clears it, NOT a round number chosen first and justified afterwards. The 2x is
    # carried INSIDE the binding case rather than reported beside it because the lead's
    # ranking is explicit -- a timeout that truncates the headline beat is a worse defect
    # than a larger bill -- and because the timeout is not a spend bound in the first place.
    binding_ms = cold_256 * 2.0
    timeout_s = max(1, math.ceil(binding_ms / 1000.0))

    return {
        "timeout_seconds": timeout_s,
        "timeout_basis": (
            "the smallest whole second that clears the worst MODELLED case: a cold start at "
            "256 MB with a tail twice as bad as this workstation's"
        ),
        "timeout_seconds_at_perfect_cpu_proportionality": max(
            1, math.ceil(cold_256_flat * 2.0 / 1000.0)
        ),
        "timeout_precision_caveat": (
            "the two figures above differ by less than this model's own uncertainty, and the "
            "model's dominant unknown -- a Graviton2 core against this one -- is not measured "
            "at all. The operative instruction is the FLOOR, not the digit: do not go below "
            "the larger of them, and do not go anywhere near 3 s"
        ),
        "cold_start_model_ms": {
            "kind": "extrapolation",
            "cpu_slope_measured": round(measured_slope, 3) if measured_slope else None,
            "cpu_slope_applied": round(slope, 3),
            "cpu_slope_source": (
                "the CPU-share probe's measured slowdown divided by perfect 1/share "
                "proportionality, averaged over its fractional-core points, then clamped at "
                "1.0: the probe may make this bound larger and may not make it smaller"
            ),
            "import_psycopg_p99_measured_ms": import_samples,
            "import_psycopg_p99_used_ms": round(import_p99, 1),
            "import_psycopg_p99_used_why": (
                "the smaller of the two independent samples of the same operation: the CPU "
                "correction is applied once, not twice"
            ),
            "first_connect_p99_measured_from_this_workstation_ms": round(connect_p99, 1),
            "first_connect_in_region_ms": round(connect_in_region, 1),
            "first_connect_in_region_why": (
                "the TLS handshake is round trips; in region they nearly vanish, so 10% of the "
                "measured figure with a 60 ms floor for the handshake's own CPU"
            ),
            "warm_gate_run_in_region_p99_ms": in_region_p99,
            "cold_at_512mb_ms": round(cold_512, 1),
            "cold_at_256mb_ms": round(cold_256, 1),
        },
        "timeout_as_multiple_of": {
            "cloud_gate_run_p99_measured_from_this_workstation": round(
                timeout_s * 1000.0 / measured_p99, 2
            ),
            "cloud_gate_run_p99_rtt_corrected_to_in_region": round(
                timeout_s * 1000.0 / in_region_p99, 2
            ),
            "in_region_cold_start_at_512mb": round(timeout_s * 1000.0 / cold_512, 2),
            "in_region_cold_start_at_256mb": round(timeout_s * 1000.0 / cold_256, 2),
        },
        "founder_requested_timeout_seconds": 3,
        "founder_request_is_honest": bool(binding_ms <= 3000.0),
        "what_3s_would_truncate": [
            (
                f"every cold-start gate run at 256 MB (modelled {cold_256:.0f} ms, "
                f"{cold_256 / 3000.0:.2f}x of 3 s)"
            ),
            (
                f"every cold-start gate run at 512 MB if the tail is 2x worse "
                f"(modelled {cold_512 * 2:.0f} ms)"
            ),
            "any warm gate run that takes one 40001 retry, which replays the whole beat set",
            (
                f"every gate run driven by a caller as far from the cluster as this workstation "
                f"(measured p99 {measured_p99:.0f} ms) -- which is what a judge running the demo "
                f"driver from outside ap-southeast-1 is"
            ),
        ],
        "what_the_recommendation_would_truncate": [
            (
                f"a warm in-region gate run whose tail is more than "
                f"{timeout_s * 1000.0 / in_region_p99:.1f}x the corrected p99"
            ),
            (
                f"a cold start at 256 MB whose CPU is more than "
                f"{timeout_s * 1000.0 / cold_256:.1f}x slower than modelled"
            ),
            "nothing measured on either target today",
        ],
        "if_the_tail_is_2x_worse_in_lambda": {
            "warm_in_region_p99_ms": round(in_region_p99 * 2, 1),
            "cold_512_ms": round(cold_512 * 2, 1),
            "cold_256_ms": round(cold_256 * 2, 1),
            "recommendation_still_holds": bool(timeout_s * 1000.0 >= cold_256 * 2),
        },
        "memory_size_mb": 256,
        "memory_size_basis": (
            "the gate run is DATABASE-BOUND, not CPU-bound: the three beat statements account "
            "for nearly all of its server-reported elapsed time, and that time is CockroachDB "
            "executing, not Lambda computing. Halving memory halves the compute term outright "
            "(it is the one term independent of duration), halves the flood rate because the "
            "CPU-bound beats take twice as long, and therefore halves egress and request "
            "charges too -- while barely moving the headline beat."
        ),
        "memory_size_costs": [
            (
                f"cold start roughly doubles: {cold_512:.0f} ms -> {cold_256:.0f} ms modelled, "
                f"and that lands on a judge's FIRST click"
            ),
            "the static-asset beats roughly double, because they are nearly pure CPU",
            (
                "there is no measurement of a 256 MB Lambda anywhere in this evidence, and "
                "there cannot be one without an apply"
            ),
        ],
        "memory_extrapolation": {
            "kind": "extrapolation",
            "relationship": (
                f"AWS allocates CPU in linear proportion to memory_size; "
                f"{LAMBDA_FULL_VCPU_MB} MB = 1 vCPU. 512 MB = "
                f"{512 / LAMBDA_FULL_VCPU_MB:.3f} vCPU, 256 MB = "
                f"{256 / LAMBDA_FULL_VCPU_MB:.3f} vCPU"
            ),
            "measured_locally": (
                "the CPU-share probe reproduces a fractional core by pinning competitors to "
                "the same logical CPU; its measured slowdown is compared against 1/share"
            ),
            "measured_slope_vs_proportional": cpu_slope,
            "applies_to": "the CPU-bound share of a beat only, never to database wait",
        },
        "current": current,
        "cost_consequence": (
            "under a sustained flood, egress and request charges scale as 1/duration while the "
            "compute term does not. The beat an attacker would choose is NOT the gate run: it "
            "is the largest static object, whose duration is two orders of magnitude smaller. "
            "A cost model that applies the gate run's duration to a flood understates the bill "
            "by that ratio, and one that applies the static beat's duration to the timeout "
            "truncates the demo."
        ),
    }


# =====================================================================================
# main
# =====================================================================================


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="measure_beats",
        description=(
            "Measure p50/p95/p99/max wall time and response bytes for every demo beat, driven "
            "over HTTP through scripts/deploy/local_furl.py, against the local container and "
            "the CockroachDB Cloud cluster. Read-only: nothing is applied and nothing is "
            "seeded."
        ),
    )
    parser.add_argument("--targets", default="local,cloud", help="comma list of local,cloud")
    parser.add_argument("--web-root", type=Path, default=DEFAULT_WEB_ROOT)
    parser.add_argument("--local-database", default="defaultdb")
    parser.add_argument("--local-dsn", default=None, help="overrides --local-database")
    parser.add_argument("--env-file", type=Path, default=REPO_ROOT / ".env")
    parser.add_argument("--dsn-key", default="COCKROACH_DSN")
    parser.add_argument("--cloud-database", default="mainline_demo")
    parser.add_argument("--local-permit-id", default=None)
    parser.add_argument("--local-site-id", default=None)
    parser.add_argument("--local-signer-sub", default=None)
    parser.add_argument("--local-countersigner-sub", default=None)
    parser.add_argument("--cloud-permit-id", default="dec0de00-0006-4000-8000-000000000001")
    parser.add_argument("--cloud-site-id", default="dec0de00-0001-4000-8000-000000000001")
    parser.add_argument("--cloud-signer-sub", default="demo.signer")
    parser.add_argument("--cloud-countersigner-sub", default="demo.countersigner")
    parser.add_argument("--samples-static", type=int, default=200)
    parser.add_argument("--samples-health", type=int, default=100)
    parser.add_argument("--samples-gate-local", type=int, default=60)
    parser.add_argument("--samples-gate-cloud", type=int, default=40)
    parser.add_argument("--warmup", type=int, default=5)
    parser.add_argument("--cold-samples", type=int, default=5)
    parser.add_argument("--rtt-samples", type=int, default=50)
    parser.add_argument("--cpu-rounds", type=int, default=250)
    parser.add_argument("--skip-cpu-probe", action="store_true")
    parser.add_argument("--http-timeout", type=float, default=180.0)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--no-write", action="store_true", help="measure and print, write nothing")
    parser.add_argument(
        "--recompute-from",
        type=Path,
        default=None,
        help=(
            "reuse the MEASUREMENTS in an earlier artefact and recompute only the model and "
            "the recommendation. Measures nothing; touches no cluster"
        ),
    )
    parser.add_argument(
        "--local-note",
        default=None,
        help="a condition to disclose beside the local target's numbers",
    )
    parser.add_argument(
        "--cloud-note",
        default=None,
        help="a condition to disclose beside the cloud target's numbers",
    )
    return parser


def _load_replay(args: argparse.Namespace) -> dict[str, Any] | None:
    """Load an earlier artefact's measurements for ``--recompute-from``, or return None."""
    if args.recompute_from is None:
        return None
    document = json.loads(args.recompute_from.read_text(encoding="utf-8"))
    if document.get("schema") != SCHEMA_ID:
        raise RuntimeError(
            f"{args.recompute_from} carries schema {document.get('schema')!r}, not {SCHEMA_ID!r}"
        )
    missing = [name for name in ("targets", "cpu_share_probe") if name not in document]
    if missing:
        raise RuntimeError(f"{args.recompute_from} has no {missing}")
    return document


def _scenario(prefix: str, args: argparse.Namespace) -> dict[str, str]:
    mapping = {
        "MAINLINE_DEMO_PERMIT_ID": getattr(args, f"{prefix}_permit_id"),
        "MAINLINE_DEMO_SITE_ID": getattr(args, f"{prefix}_site_id"),
        "MAINLINE_DEMO_SIGNER_SUB": getattr(args, f"{prefix}_signer_sub"),
        "MAINLINE_DEMO_COUNTERSIGNER_SUB": getattr(args, f"{prefix}_countersigner_sub"),
    }
    return {key: value for key, value in mapping.items() if value}


def _read_env_dsn(env_file: Path, key: str) -> str:
    for line in env_file.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith(f"{key}=") and not stripped.startswith("#"):
            return stripped.split("=", 1)[1].strip().strip("'\"")
    raise RuntimeError(f"{env_file} has no {key}")


def build_targets(args: argparse.Namespace) -> list[Target]:
    wanted = [name.strip() for name in args.targets.split(",") if name.strip()]
    unknown = [name for name in wanted if name not in ("local", "cloud")]
    if unknown:
        raise RuntimeError(f"unknown target(s) {unknown}; choose from local, cloud")
    targets: list[Target] = []
    if "local" in wanted:
        dsn = args.local_dsn or DEFAULT_LOCAL_DSN.format(database=args.local_database)
        targets.append(
            Target(
                name="local",
                dsn=dsn,
                scenario=_scenario("local", args),
                described={
                    **describe_dsn(dsn),
                    "cluster": "local docker container trappoint-crdb, CockroachDB v26.2.5",
                    "seed": "the proof seeder (scripts/proof/gate_refusal.py::seed_history)",
                },
            )
        )
    if "cloud" in wanted:
        dsn = _read_env_dsn(args.env_file, args.dsn_key)
        described = describe_dsn(dsn)
        described["database"] = args.cloud_database
        described["cluster"] = "CockroachDB Cloud, Basic, aws-ap-southeast-1"
        described["seed"] = "verticals/mainline/db/seeds/demo/demo_world.sql (the cloud seed)"
        targets.append(
            Target(
                name="cloud",
                env_file=args.env_file,
                dsn_key=args.dsn_key,
                database=args.cloud_database,
                scenario=_scenario("cloud", args),
                described=described,
            )
        )
    return targets


def _samples_for(beat: Beat, target_name: str, args: argparse.Namespace) -> int:
    if beat.name == "gate_run":
        return args.samples_gate_cloud if target_name == "cloud" else args.samples_gate_local
    if beat.name == "health":
        return args.samples_health
    return args.samples_static


def handler_source() -> dict[str, Any]:
    """SHA-256 of every module in the distribution whose latency this is.

    A latency baseline is a statement about a specific tree, and this one is taken in the
    middle of a wave that is deliberately changing `static_site.py` (the wire ceiling and the
    gzip sibling) and `app.py` (the rate limiter). Without this block a reader six commits
    later cannot tell whether the numbers still describe the code -- they would have to trust
    a date. With it, one `sha256sum` settles it.
    """
    root = DEFAULT_APP_SRC / "mainline_demo_api"
    if not root.is_dir():
        return {"root": str(root), "present": False}
    digests = {
        module.name: hashlib.sha256(module.read_bytes()).hexdigest()[:16]
        for module in sorted(root.glob("*.py"))
    }
    return {
        "root": str(root.relative_to(REPO_ROOT)).replace("\\", "/"),
        "present": True,
        "sha256_16": digests,
        "why": (
            "the baseline describes THIS code. W2, W3 and W4 are changing the package in the "
            "same wave; when any of these digests moves, the static-beat figures are stale"
        ),
    }


def _cold_dsn(target: Target, args: argparse.Namespace) -> str:
    if target.dsn is not None:
        return target.dsn
    raw = _read_env_dsn(args.env_file, args.dsn_key)
    split = urllib.parse.urlsplit(raw)
    return urllib.parse.urlunsplit(
        (split.scheme, split.netloc, f"/{args.cloud_database}", split.query, split.fragment)
    )


def measure_target(target: Target, args: argparse.Namespace) -> dict[str, Any]:
    print(f"[{target.name}] cold probe ({args.cold_samples} fresh interpreters)")
    cold = cold_probe(
        _cold_dsn(target, args), samples=args.cold_samples, rtt_samples=args.rtt_samples
    )
    print(
        f"[{target.name}]   import p50 {cold['import_psycopg_ms']['p50_ms']:.1f} ms | "
        f"connect p50 {cold['first_connect_ms']['p50_ms']:.1f} ms | "
        f"rtt p50 {cold['select_1_round_trip_ms']['p50_ms']:.3f} ms"
    )
    beats: dict[str, Any] = {}
    for beat in BEATS:
        samples = _samples_for(beat, target.name, args)
        print(f"[{target.name}] {beat.name}: warmup {args.warmup}, {samples} samples")
        with emulator(target, args.web_root) as base:
            beats[beat.name] = drive(
                beat, base, warmup=args.warmup, samples=samples, timeout=args.http_timeout
            )
        wall = beats[beat.name]["wall_ms"]
        print(
            f"[{target.name}]   p50 {wall['p50_ms']:.2f} | p95 {wall['p95_ms']:.2f} | "
            f"p99 {wall['p99_ms']:.2f} | max {wall['max_ms']:.2f} ms | "
            f"{beats[beat.name]['response_bytes']} B | status "
            f"{beats[beat.name]['statuses_observed']}"
        )
    print(f"[{target.name}] connection-state probe")
    state = connection_state_probe(target, args.web_root, args.http_timeout)
    print(f"[{target.name}]   statuses {state['statuses']}")
    return {
        "target": target.name,
        "reached": True,
        "database_target": target.described,
        "scenario_env_published_to_the_emulator": sorted(target.scenario),
        "cold": cold,
        "beats": beats,
        "connection_state_probe": state,
    }


def _cpu_slope(probe: dict[str, Any]) -> float | None:
    if not probe.get("supported"):
        return None
    points = [p for p in probe["points"] if p["competitors_on_the_same_core"] > 0]
    if not points:
        return None
    return round(
        statistics.fmean(
            p["slowdown_vs_full_core"] / p["slowdown_if_perfectly_proportional"] for p in points
        ),
        3,
    )


def build_document(results: dict[str, Any], cpu: dict[str, Any], args: argparse.Namespace) -> dict:
    document: dict[str, Any] = {
        "schema": SCHEMA_ID,
        "generated_at": dt.datetime.now(dt.UTC).isoformat(),
        "generated_by": "scripts/deploy/measure_beats.py",
        "what_this_is": (
            "wall-clock latency of every demo beat, driven over a real socket through the real "
            "mainline_demo_api handler by scripts/deploy/local_furl.py, against two database "
            "targets. Nothing was applied, nothing was seeded, nothing was mutated: the gate "
            "run rolls its own transaction back."
        ),
        "host": {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "logical_cpus": os.cpu_count(),
            "note": (
                "an x86_64 workstation. The deployment target is arm64 (Graviton2) at a "
                "fraction of one vCPU. Nothing here measures that."
            ),
        },
        "python": {
            "version": sys.version,
            "implementation": platform.python_implementation(),
            "executable_is_repo_venv": str(REPO_ROOT).lower() in sys.executable.lower(),
        },
        "harness": {
            "emulator": "scripts/deploy/local_furl.py (started as a subprocess, one per beat)",
            "why_one_process_per_beat": (
                "a gate run strands the shared connection INTRANS; interleaving beats in one "
                "process would measure that defect instead of the beat"
            ),
            "transport": "HTTP/1.1 keep-alive over loopback; no TLS (AWS terminates TLS ahead "
            "of the function, so a local TLS hop would measure something the Lambda never pays)",
            "warmup_discarded_per_beat": args.warmup,
            "clock": "time.perf_counter around request-send to body-read-complete",
        },
        "handler_source": handler_source(),
        "targets": results,
        "cpu_share_probe": cpu,
    }
    local = results.get("local")
    cloud = results.get("cloud")
    if local and cloud:
        model = round_trip_model(
            local["beats"]["gate_run"]["wall_ms"],
            cloud["beats"]["gate_run"]["wall_ms"],
            local["cold"]["select_1_round_trip_ms"],
            cloud["cold"]["select_1_round_trip_ms"],
        )
        document["round_trip_model"] = model
        document["recommendation"] = recommend(
            cloud["beats"]["gate_run"]["wall_ms"],
            model,
            {"local": local["cold"], "cloud": cloud["cold"]},
            _cpu_slope(cpu),
            {
                "timeout_seconds": 15,
                "memory_size_mb": 512,
                "source": "infra/modules/demo-api (the plan as it stands today)",
            },
        )
    else:
        document["round_trip_model"] = {
            "computed": False,
            "reason": "both targets are required to separate round-trip cost from server work",
        }
    return document


def _gather(
    targets: list[Target], args: argparse.Namespace, replay: dict[str, Any] | None
) -> tuple[dict[str, Any], list[str]]:
    """Measure (or replay) every target, stamp the disclosures, and collect the failures."""
    results: dict[str, Any] = {}
    failures: list[str] = []
    for target in targets:
        if replay is not None:
            results[target.name] = replay["targets"][target.name]
            continue
        try:
            results[target.name] = measure_target(target, args)
        except (OSError, RuntimeError, subprocess.SubprocessError, ValueError) as exc:
            failures.append(f"{target.name}: {type(exc).__name__}: {redact(str(exc))[:400]}")
            results[target.name] = {
                "target": target.name,
                "reached": False,
                "database_target": target.described,
                "error": f"{type(exc).__name__}: {redact(str(exc))[:400]}",
            }
    for name, note in (("local", args.local_note), ("cloud", args.cloud_note)):
        if note and name in results:
            results[name]["conditions_disclosed_by_the_operator"] = note
    for name, result in results.items():
        for beat_name, beat in (result.get("beats") or {}).items():
            if not beat["status_ok"]:
                failures.append(
                    f"{name}/{beat_name}: observed status {beat['statuses_observed']}, "
                    f"expected {beat['expect_status']}"
                )
    return results, failures


def _cpu_probe(args: argparse.Namespace, replay: dict[str, Any] | None) -> dict[str, Any]:
    if replay is not None:
        return dict(replay["cpu_share_probe"])
    if args.skip_cpu_probe:
        print("cpu-share probe SKIPPED")
        return {"supported": False, "reason": "--skip-cpu-probe"}
    print("cpu-share probe")
    return cpu_share_probe(
        args.web_root / "assets" / "index-BjAGxrVJ.js",
        rounds=args.cpu_rounds,
        competitors=(0, 1, 2, 6),
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.web_root.is_dir():
        print(f"measure_beats: --web-root {args.web_root} is not a directory", file=sys.stderr)
        return EXIT_USAGE
    try:
        targets = build_targets(args)
    except (OSError, RuntimeError) as exc:
        print(f"measure_beats: {redact(str(exc))}", file=sys.stderr)
        return EXIT_USAGE

    replay = _load_replay(args)
    results, failures = _gather(targets, args, replay)
    cpu = _cpu_probe(args, replay)
    document = build_document(results, cpu, args)
    if replay is not None:
        document["measured_at"] = replay["generated_at"]
        document["recomputed"] = {
            "from": str(args.recompute_from),
            "what_was_reused": "every measurement: both targets, both cold probes, the CPU probe",
            "what_was_recomputed": "round_trip_model and recommendation only",
            "why_this_is_allowed": (
                "the measurements are inputs and the model is a function of them. Being able "
                "to re-derive the model from a recorded measurement without re-measuring is "
                "what makes the model checkable by somebody who was not here; a model that can "
                "only be reproduced by re-running a 32-minute measurement cannot be audited. "
                "No number under `targets` or `cpu_share_probe` was recomputed, and "
                "`measured_at` above is when they were taken."
            ),
        }
    document["failures"] = failures
    document["ok"] = not failures

    if args.no_write:
        print(json.dumps(document, indent=2, sort_keys=True))
    else:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"wrote {args.out}")
    recommendation = document.get("recommendation")
    if recommendation:
        print(
            f"RECOMMEND timeout={recommendation['timeout_seconds']}s "
            f"memory_size={recommendation['memory_size_mb']}MB"
        )
    for failure in failures:
        print(f"FAILURE  {failure}", file=sys.stderr)
    return EXIT_OK if not failures else EXIT_FAILED


if __name__ == "__main__":
    raise SystemExit(main())
