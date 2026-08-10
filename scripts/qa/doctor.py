#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
#
# MI: none — this file makes no database claim. It ASKS the database questions and
#     reports the answers; every assertion about the schema lives in a migration.
# I: QA-DOCTOR-1 — a stranger's first five minutes must fail, if they fail, with a
#    sentence and a numbered remedy, never with `command not found` from a file whose
#    own header promises it runs on a stranger's laptop.
# RATIONALE: measured on this machine on 2026-08-10 — `uv` is NOT INSTALLED, and every
#    recipe in `justfile` began with `uv run`. `just` is not installed either. The
#    Docker Desktop engine answered HTTP 500 after a full-suite run started thirteen
#    CockroachDB containers, so probing the `docker` BINARY says nothing; the API must
#    be asked. The node answered `remote wall time is too far ahead (9.94 s) to be
#    trustworthy` after a host sleep, and the fix — `docker restart` — belonged in a
#    script rather than in folklore. Local `gc.ttlseconds` is 14400 against Cloud's
#    4500, i.e. local is MORE permissive, which is how a time-travel assumption hides
#    until the nightly Cloud run. (Quality-repair plan §1.1, §1.4, §1.9.)
"""Preflight for the MAINLINE one-command loop: say what is missing, before it fails.

Run it directly, or as ``just doctor``::

    python scripts/qa/doctor.py
    python scripts/qa/doctor.py --json
    python scripts/qa/doctor.py --print-pin

It writes nothing, starts nothing, pulls nothing and needs no credential. Every check
is a question with an observable answer, and every failing check carries the exact
command that fixes it.

Exit codes
----------

* ``0`` — everything the Tier-2 proof (``just up && just doctor && just prove``) needs
  is present. Advisory warnings may still be printed.
* ``1`` — at least one blocking check failed. A numbered remedy list follows the table.
* ``2`` — the doctor could not run (bad usage, or ``--print-pin`` found no pin).

``--strict`` promotes every warning to a blocking failure, which is what a release
workflow wants and what a laptop does not.

The one thing this script imports from the repository is the testkit's compose-pin
reader, loaded **by file path** rather than by package name: ``trappoint_testkit``'s
``__init__`` pulls in ``cluster``, which needs ``psycopg``, and the whole point of the
doctor is to work on a checkout where nothing is installed yet. If that file cannot be
loaded the parse falls back to a copy of its regex, and the two are cross-checked
whenever both are available — a doctor that reports a pin the testkit would not agree
with is a doctor lying about the one constant the repository has.
"""

from __future__ import annotations

import argparse
import contextlib
import importlib.util
import json
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_PATH = REPO_ROOT / "compose.yaml"
TESTKIT_IMAGE_PY = (
    REPO_ROOT / "packages" / "trappoint-testkit" / "src" / "trappoint_testkit" / "image.py"
)
CONSOLE_PACKAGE_JSON = REPO_ROOT / "verticals" / "mainline" / "apps" / "console" / "package.json"
MIGRATIONS_DIR = REPO_ROOT / "verticals" / "mainline" / "db" / "migrations"
PROOF_SCRIPT = REPO_ROOT / "scripts" / "proof" / "gate_refusal.py"

#: The comment that marks the one line carrying the version constant. Byte-identical to
#: ``trappoint_testkit.image.IMAGE_PIN_MARKER``; the test in
#: ``tests/release/test_one_command_loop.py`` asserts they have not drifted apart.
IMAGE_PIN_MARKER = "trappoint:crdb-image-pin"
_IMAGE_LINE = re.compile(r"^\s*image:\s*(?P<image>\S+)\s*$")
_PIN_LOOKAHEAD = 3

#: What CockroachDB Cloud enforces. Local defaults to 14400 — four hours instead of
#: seventy-five minutes — so a query that reaches back beyond Cloud's horizon passes on
#: a laptop and fails on the nightly truth check. Aligning local DOWN is the honest
#: direction; aligning Cloud up is not available.
CLOUD_GC_TTL_SECONDS = 4500
LOCAL_DEFAULT_GC_TTL_SECONDS = 14400

#: The four spellings every cluster fixture in this repository already honours.
DSN_ENV_NAMES = ("MAINLINE_TEST_DSN", "TRAPPOINT_DSN", "COCKROACH_URL", "CRDB_URL", "LOCAL_DSN")
DEFAULT_DSN = "postgresql://root@127.0.0.1:26257/defaultdb?sslmode=disable"

#: CockroachDB's own default maximum clock offset is 500 ms; past it a node refuses to
#: serve rather than risk a stale read. Measured healthy on this machine: 0.023 s.
#: Measured broken after a host sleep: 9.94 s, reported by the node itself as
#: `remote wall time is too far ahead (9.94 s) to be trustworthy`.
CLOCK_SKEW_WARN_SECONDS = 0.25
CLOCK_SKEW_FAIL_SECONDS = 1.0

#: Substrings the node uses when it has decided its own clock cannot be trusted.
CLOCK_ERROR_MARKERS = ("too far ahead", "too far behind", "wall time", "clock offset")

#: Substrings a wedged Docker Desktop engine puts on stderr. The binary answers fine.
ENGINE_DEAD_MARKERS = (
    "error during connect",
    "cannot connect to the docker daemon",
    "500 internal server error",
    "the system cannot find the file specified",
    "is the docker daemon running",
    "open //./pipe/docker_engine",
)

#: Every distribution in the tree declares requires-python >= 3.13. Kept as a constant
#: rather than a literal in the comparison so the runtime check survives a static
#: analyser that has already been told this file only runs on 3.13+.
MINIMUM_PYTHON = (3, 13)

#: ``sys.platform`` read once into a plain ``str``. mypy special-cases a direct
#: ``sys.platform == "…"`` comparison as a compile-time constant for the host it is
#: running on, and calls every other branch unreachable — which on this Windows machine
#: means the Linux and macOS install commands below type-check as dead code. They are
#: not dead; they are the only ones a stranger on Linux will ever see.
HOST_PLATFORM: str = sys.platform

REQUIRED_NODE_MAJOR = 24
REQUIRED_PNPM_MAJOR = 11

#: What compose.yaml names the node. Used only as the fallback in a `docker restart`
#: remedy when nothing CockroachDB-shaped is currently running to read a name from.
DEFAULT_CONTAINER_NAME = "trappoint-crdb"

OK = "OK"
WARN = "WARN"
FAIL = "FAIL"
SKIP = "SKIP"

EXIT_READY = 0
EXIT_NOT_READY = 1
EXIT_USAGE = 2


@dataclass
class Check:
    """One question, its answer, and — when the answer is wrong — how to fix it."""

    key: str
    title: str
    status: str
    observed: str
    remedy: list[str] = field(default_factory=list)
    blocking: bool = True
    detail: dict[str, Any] = field(default_factory=dict)

    @property
    def is_blocking_failure(self) -> bool:
        """True when this check alone is enough to stop the Tier-2 proof."""
        return self.blocking and self.status == FAIL

    def as_dict(self) -> dict[str, Any]:
        """The row, as JSON."""
        return {
            "key": self.key,
            "title": self.title,
            "status": self.status,
            "observed": self.observed,
            "blocking": self.blocking,
            "remedy": self.remedy,
            "detail": self.detail,
        }


# ── the compose pin ──────────────────────────────────────────────────────────────────────


class PinNotFound(RuntimeError):
    """No compose file, or a compose file with no marked ``image:`` line."""


def _read_pin_locally(compose_path: Path) -> str:
    """Parse the marked ``image:`` line with a copy of the testkit's regex."""
    if not compose_path.is_file():
        raise PinNotFound(f"no compose file at {compose_path}")
    lines = compose_path.read_text(encoding="utf-8").splitlines()
    for index, line in enumerate(lines):
        if IMAGE_PIN_MARKER not in line:
            continue
        for candidate in lines[index + 1 : index + 1 + _PIN_LOOKAHEAD]:
            match = _IMAGE_LINE.match(candidate)
            if match is not None:
                return match.group("image")
    raise PinNotFound(
        f"{compose_path} carries no line marked '{IMAGE_PIN_MARKER}' followed within "
        f"{_PIN_LOOKAHEAD} lines by an 'image:' key"
    )


def _load_testkit_image_module() -> Any | None:
    """Load ``trappoint_testkit/image.py`` by path, without importing the package.

    The package ``__init__`` imports ``cluster``, which imports ``psycopg``. A doctor
    that needs a third-party wheel installed before it can tell you nothing is
    installed is not a doctor.
    """
    if not TESTKIT_IMAGE_PY.is_file():
        return None
    try:
        spec = importlib.util.spec_from_file_location("_doctor_testkit_image", TESTKIT_IMAGE_PY)
        if spec is None or spec.loader is None:
            return None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    except Exception:  # noqa: BLE001 - any failure here means "use the local copy"
        return None
    return module


def read_pin(compose_path: Path = COMPOSE_PATH) -> tuple[str, str]:
    """Return ``(pin, source)`` — the pinned image and which parser produced it.

    Raises:
        PinNotFound: no compose file, or no marked ``image:`` line in it.
    """
    module = _load_testkit_image_module()
    local: str | None
    try:
        local = _read_pin_locally(compose_path)
    except PinNotFound:
        local = None
    if module is not None:
        try:
            through_testkit = module.read_pin(compose_path)
        except Exception as exc:  # reported, never swallowed
            if local is None:
                raise PinNotFound(str(exc)) from exc
            return local, f"doctor copy (trappoint_testkit.image refused it: {exc})"
        if local is not None and local != through_testkit:
            raise PinNotFound(
                f"the two parsers disagree: trappoint_testkit.image reads "
                f"{through_testkit!r}, this script reads {local!r}"
            )
        return through_testkit, "trappoint_testkit.image"
    if local is None:
        raise PinNotFound(f"no marked '{IMAGE_PIN_MARKER}' line in {compose_path}")
    return local, "doctor copy (trappoint_testkit not on disk)"


# ── small helpers ────────────────────────────────────────────────────────────────────────


def _run(argv: list[str], timeout: float) -> tuple[int, str, str]:
    """Run *argv* with no shell; return ``(returncode, stdout, stderr)``.

    A timeout is reported as returncode ``124`` with the reason on stderr, because a
    wedged Docker engine hangs rather than answers and a doctor that hangs is the
    problem it was written to remove.
    """
    try:
        completed = subprocess.run(  # fixed argv, never a shell string
            argv,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return 124, "", f"timed out after {timeout:g}s"
    except OSError as exc:
        return 127, "", str(exc)
    return completed.returncode, completed.stdout.strip(), completed.stderr.strip()


_VERSION_RE = re.compile(r"(\d+)(?:\.(\d+))?(?:\.(\d+))?")


def _version_tuple(text: str) -> tuple[int, ...]:
    """First dotted number in *text*, as a tuple. ``()`` when there is none."""
    match = _VERSION_RE.search(text)
    if match is None:
        return ()
    return tuple(int(part) for part in match.groups() if part is not None)


def _looks_like_dead_engine(stderr: str) -> bool:
    lowered = stderr.lower()
    return any(marker in lowered for marker in ENGINE_DEAD_MARKERS)


def _uv_install_lines() -> list[str]:
    if HOST_PLATFORM == "win32":
        return [
            'powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"',
            "or, if you would rather not pipe a script:  pipx install uv",
        ]
    return [
        "curl -LsSf https://astral.sh/uv/install.sh | sh",
        "or, if you would rather not pipe a script:  pipx install uv",
    ]


def _just_install_lines() -> list[str]:
    if HOST_PLATFORM == "win32":
        return [
            "winget install --id Casey.Just --source winget",
            "or:  npm install -g rust-just        (the same binary, from the npm registry)",
        ]
    if HOST_PLATFORM == "darwin":
        return ["brew install just", "or:  cargo install just"]
    return [
        (
            "curl --proto '=https' --tlsv1.2 -sSf https://just.systems/install.sh "
            "| bash -s -- --to ~/.local/bin"
        ),
        "or:  cargo install just",
    ]


def _dsn_from_environment() -> tuple[str, str]:
    """Return ``(dsn, provenance)`` from the four honoured spellings, else the default."""
    for name in DSN_ENV_NAMES:
        value = os.environ.get(name)
        if value:
            return value, f"${name}"
    return DEFAULT_DSN, "the local single-node default"


def _with_connect_timeout(dsn: str, seconds: int) -> str:
    """Append ``connect_timeout`` unless the caller already set one.

    Measured on this machine: a connect to a black-holed address raised after 130.1 s
    with no timeout and 3.1 s at 3. An unset timeout turns a dead node into a hang.
    """
    if "connect_timeout" in dsn:
        return dsn
    separator = "&" if "?" in dsn else "?"
    return f"{dsn}{separator}connect_timeout={seconds}"


def _crdb_container_name() -> str:
    """The name of a running CockroachDB container, for the `docker restart` remedy."""
    docker = shutil.which("docker")
    if docker is None:
        return DEFAULT_CONTAINER_NAME
    # `--filter ancestor=` matches only an exact image reference, and the running node
    # may carry any of the pin's tags; measured here, `ancestor=cockroachdb/cockroach`
    # matched nothing while the container was up. Listing and matching on the image
    # prefix is the version-independent way to ask "which one is CockroachDB".
    code, out, _ = _run([docker, "ps", "--format", "{{.Names}}\t{{.Image}}"], timeout=20)
    if code == 0 and out:
        for line in out.splitlines():
            name, _, image = line.partition("\t")
            if image.strip().startswith("cockroachdb/cockroach"):
                return name.strip()
    return DEFAULT_CONTAINER_NAME


# ── the checks ───────────────────────────────────────────────────────────────────────────


def check_python() -> Check:
    """The interpreter running this file, and whether it is new enough for the tree."""
    version = ".".join(str(part) for part in sys.version_info[:3])
    observed = f"{version} at {sys.executable}"
    if sys.version_info[:2] < MINIMUM_PYTHON:
        return Check(
            key="python",
            title="python >= 3.13",
            status=FAIL,
            observed=observed,
            remedy=[
                "Every distribution in this repository declares requires-python >= 3.13.",
                "Install 3.13 or newer, or let uv fetch one:  uv python install 3.13",
            ],
        )
    return Check(key="python", title="python >= 3.13", status=OK, observed=observed)


def check_docker_cli() -> Check:
    """Is the `docker` binary on PATH at all."""
    docker = shutil.which("docker")
    if docker is None:
        return Check(
            key="docker-cli",
            title="docker (client)",
            status=FAIL,
            observed="not on PATH",
            remedy=[
                "Install Docker Desktop (Windows/macOS) or the Docker Engine (Linux):",
                "    https://docs.docker.com/get-docker/",
                "The whole local proof is one image pull and one container; nothing else.",
            ],
        )
    code, out, err = _run([docker, "--version"], timeout=30)
    if code != 0:
        return Check(
            key="docker-cli",
            title="docker (client)",
            status=FAIL,
            observed=f"`docker --version` exited {code}: {err or out}",
            remedy=["Reinstall or repair the Docker client; the binary on PATH does not run."],
        )
    return Check(key="docker-cli", title="docker (client)", status=OK, observed=out)


def check_docker_engine() -> Check:
    """Ask the engine API, not the binary.

    Measured 2026-08-10: after a full-suite run started thirteen CockroachDB containers,
    `docker --version` still answered instantly and the ENGINE answered HTTP 500. A
    check that stops at the binary would have called that machine healthy.
    """
    docker = shutil.which("docker")
    if docker is None:
        return Check(
            key="docker-engine",
            title="docker engine (API)",
            status=SKIP,
            observed="no docker client to ask with",
            remedy=[],
        )
    code, out, err = _run([docker, "version", "--format", "{{json .Server}}"], timeout=45)
    if code == 124:
        return Check(
            key="docker-engine",
            title="docker engine (API)",
            status=FAIL,
            observed="the engine API did not answer in 45s",
            remedy=[
                "The Docker engine is wedged, not absent. Restart it:",
                "    Docker Desktop -> Troubleshoot -> Restart, or quit and reopen it",
                "    (Linux:  sudo systemctl restart docker)",
            ],
        )
    if code != 0 or not out or out == "null":
        reason = err or out or f"exit {code}"
        dead = _looks_like_dead_engine(reason)
        return Check(
            key="docker-engine",
            title="docker engine (API)",
            status=FAIL,
            observed=(reason.splitlines() or ["(silence)"])[0][:160],
            remedy=[
                "The docker CLI is installed but the engine API did not answer.",
                (
                    "This is the HTTP-500/no-pipe shape, not a missing install."
                    if dead
                    else "Start the engine, then re-run the doctor."
                ),
                "    Start Docker Desktop and wait for the whale to stop animating",
                "    (Linux:  sudo systemctl start docker)",
            ],
        )
    try:
        server = json.loads(out)
    except json.JSONDecodeError:
        server = {}
    version = str(server.get("Version") or "unknown")
    ostype = str(server.get("Os") or server.get("Arch") or "")
    observed = f"server {version}" + (f" ({ostype})" if ostype else "")
    return Check(
        key="docker-engine",
        title="docker engine (API)",
        status=OK,
        observed=observed,
        detail={"server_version": version},
    )


def check_uv() -> Check:
    """The tool every recipe in the justfile and seven of eleven workflows begin with."""
    uv = shutil.which("uv")
    if uv is None:
        return Check(
            key="uv",
            title="uv (python workspace)",
            status=FAIL,
            observed="not on PATH",
            remedy=[
                "uv resolves and installs all 27 distributions from the one lockfile.",
                "Install it:",
                *[f"    {line}" for line in _uv_install_lines()],
                "Then:  just setup      (which runs `uv sync --all-packages`)",
            ],
        )
    code, out, err = _run([uv, "--version"], timeout=30)
    if code != 0:
        return Check(
            key="uv",
            title="uv (python workspace)",
            status=FAIL,
            observed=f"`uv --version` exited {code}: {err or out}",
            remedy=["Reinstall uv:", *[f"    {line}" for line in _uv_install_lines()]],
        )
    return Check(key="uv", title="uv (python workspace)", status=OK, observed=out)


def check_just() -> Check:
    """The command surface QUICKSTART.md names. Four commands, all of them `just`."""
    just = shutil.which("just")
    if just is None:
        return Check(
            key="just",
            title="just (command surface)",
            status=FAIL,
            observed="not on PATH",
            remedy=[
                "QUICKSTART.md is four `just` commands. Install it:",
                *[f"    {line}" for line in _just_install_lines()],
                "Every recipe is one line of bash; `just --list` shows them all.",
            ],
        )
    code, out, err = _run([just, "--version"], timeout=30)
    if code != 0:
        return Check(
            key="just",
            title="just (command surface)",
            status=FAIL,
            observed=f"`just --version` exited {code}: {err or out}",
            remedy=["Reinstall just:", *[f"    {line}" for line in _just_install_lines()]],
        )
    return Check(key="just", title="just (command surface)", status=OK, observed=out)


def _console_engine_requirements() -> dict[str, str]:
    """The `engines` block of the console's package.json, or ``{}``."""
    if not CONSOLE_PACKAGE_JSON.is_file():
        return {}
    try:
        data = json.loads(CONSOLE_PACKAGE_JSON.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    engines = data.get("engines")
    return engines if isinstance(engines, dict) else {}


def check_node() -> Check:
    """node, at the major the console's package.json requires. Advisory for the proof."""
    engines = _console_engine_requirements()
    wanted = engines.get("node", f">={REQUIRED_NODE_MAJOR}.0.0")
    node = shutil.which("node")
    if node is None:
        return Check(
            key="node",
            title=f"node {wanted}",
            status=WARN,
            observed="not on PATH",
            blocking=False,
            remedy=[
                "Only `just console` needs it; the database proof does not.",
                (
                    f"    Install Node {REQUIRED_NODE_MAJOR}:  https://nodejs.org/  "
                    f"(or `nvm install {REQUIRED_NODE_MAJOR}`)"
                ),
            ],
        )
    code, out, _ = _run([node, "--version"], timeout=30)
    found = _version_tuple(out)
    if code != 0 or not found:
        return Check(
            key="node",
            title=f"node {wanted}",
            status=WARN,
            observed=f"`node --version` exited {code}",
            blocking=False,
            remedy=["Repair the Node install, or skip `just console`."],
        )
    if found[0] < REQUIRED_NODE_MAJOR:
        return Check(
            key="node",
            title=f"node {wanted}",
            status=WARN,
            observed=f"{out} (below the required major {REQUIRED_NODE_MAJOR})",
            blocking=False,
            remedy=[
                f"`just console` needs Node >= {REQUIRED_NODE_MAJOR}.",
                f"    nvm install {REQUIRED_NODE_MAJOR} && nvm use {REQUIRED_NODE_MAJOR}",
            ],
        )
    return Check(key="node", title=f"node {wanted}", status=OK, observed=out, blocking=False)


def check_pnpm() -> Check:
    """pnpm, at the major the console's package.json requires. Advisory for the proof."""
    engines = _console_engine_requirements()
    wanted = engines.get("pnpm", f">={REQUIRED_PNPM_MAJOR}.0.0")
    pnpm = shutil.which("pnpm")
    if pnpm is None:
        return Check(
            key="pnpm",
            title=f"pnpm {wanted}",
            status=WARN,
            observed="not on PATH",
            blocking=False,
            remedy=[
                "Only `just console` needs it. The version is pinned in package.json:",
                "    corepack enable && corepack prepare pnpm@11.5.3 --activate",
            ],
        )
    code, out, _ = _run([pnpm, "--version"], timeout=60)
    found = _version_tuple(out)
    if code != 0 or not found:
        return Check(
            key="pnpm",
            title=f"pnpm {wanted}",
            status=WARN,
            observed=f"`pnpm --version` exited {code}",
            blocking=False,
            remedy=["Repair the pnpm install, or skip `just console`."],
        )
    if found[0] < REQUIRED_PNPM_MAJOR:
        return Check(
            key="pnpm",
            title=f"pnpm {wanted}",
            status=WARN,
            observed=f"{out} (below the required major {REQUIRED_PNPM_MAJOR})",
            blocking=False,
            remedy=[
                f"`just console` needs pnpm >= {REQUIRED_PNPM_MAJOR}.",
                "    corepack enable && corepack prepare pnpm@11.5.3 --activate",
            ],
        )
    return Check(key="pnpm", title=f"pnpm {wanted}", status=OK, observed=out, blocking=False)


def check_pin() -> tuple[Check, str | None]:
    """The one version constant, read out of compose.yaml through the testkit's parser."""
    try:
        pin, source = read_pin()
    except PinNotFound as exc:
        return (
            Check(
                key="crdb-pin",
                title="compose.yaml image pin",
                status=FAIL,
                observed=str(exc)[:160],
                remedy=[
                    "compose.yaml is the single home of the CockroachDB version constant.",
                    f"    Restore the line marked `# {IMAGE_PIN_MARKER}` with an `image:`",
                    "    key on the next line. `just image`, db.yml, ci.yml and",
                    "    trappoint_testkit.image all read it back out of that one place.",
                ],
            ),
            None,
        )
    return (
        Check(
            key="crdb-pin",
            title="compose.yaml image pin",
            status=OK,
            observed=f"{pin}  (parsed by {source})",
            detail={"image": pin, "parser": source},
        ),
        pin,
    )


def check_image_pulled(pin: str | None, engine_ok: bool) -> Check:
    """Is the pinned image already local. A judge on hotel wifi wants to know first."""
    if pin is None:
        return Check(
            key="crdb-image",
            title="pinned image present",
            status=SKIP,
            observed="no pin to look for",
            blocking=False,
        )
    docker = shutil.which("docker")
    if docker is None or not engine_ok:
        return Check(
            key="crdb-image",
            title="pinned image present",
            status=SKIP,
            observed="no working docker engine to ask",
            blocking=False,
        )
    code, out, err = _run([docker, "image", "inspect", pin, "--format", "{{.Id}}"], timeout=60)
    if code != 0:
        return Check(
            key="crdb-image",
            title="pinned image present",
            status=FAIL,
            observed=f"{pin} is not pulled",
            remedy=[
                "One pull, about 500 MB, and the proof needs no network again:",
                f"    docker pull {pin}",
                "    (`just up` will pull it too, but then the wait is unexplained.)",
            ],
            detail={"stderr": err[:200]},
        )
    return Check(
        key="crdb-image",
        title="pinned image present",
        status=OK,
        observed=f"{pin} -> {out[:19]}",
        detail={"image_id": out},
    )


def check_port(host: str, port: int, timeout: float) -> tuple[Check, bool]:
    """Is anything listening on the pgwire port at all."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            pass
    except OSError as exc:
        return (
            Check(
                key="crdb-port",
                title=f"pgwire {host}:{port}",
                status=FAIL,
                observed=f"nothing listening ({exc.__class__.__name__}: {exc})"[:160],
                remedy=[
                    "Start the local single-node cluster:",
                    "    just up          (docker compose up -d --wait)",
                    "or point the doctor at a node you already have:",
                    (
                        "    python scripts/qa/doctor.py --dsn "
                        "postgresql://root@HOST:26257/defaultdb?sslmode=disable"
                    ),
                ],
            ),
            False,
        )
    return (
        Check(
            key="crdb-port",
            title=f"pgwire {host}:{port}",
            status=OK,
            observed="a socket accepted the connection",
        ),
        True,
    )


@dataclass
class NodeFacts:
    """What one round-trip to the node told us."""

    version: str | None = None
    gc_ttlseconds: int | None = None
    skew_seconds: float | None = None
    error: str | None = None
    clock_error: bool = False


def interrogate_node(dsn: str, connect_timeout: int) -> NodeFacts:
    """One connection, three questions: version, zone TTL, and whose clock is wrong."""
    facts = NodeFacts()
    try:
        import psycopg
    except ImportError as exc:
        facts.error = f"psycopg is not importable ({exc})"
        return facts
    try:
        with psycopg.connect(_with_connect_timeout(dsn, connect_timeout)) as conn:
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute("SELECT version()")
                row = cur.fetchone()
                facts.version = str(row[0]) if row else None

                before = time.time()
                cur.execute("SELECT now()::TIMESTAMPTZ")
                after = time.time()
                row = cur.fetchone()
                if row is not None:
                    node_now: datetime = row[0]
                    # The midpoint of the round trip removes the RTT from the estimate;
                    # what is left is the difference between two wall clocks.
                    midpoint = datetime.fromtimestamp((before + after) / 2, tz=UTC)
                    facts.skew_seconds = (node_now - midpoint).total_seconds()

                cur.execute("SHOW ZONE CONFIGURATION FOR RANGE default")
                row = cur.fetchone()
                if row is not None:
                    match = re.search(r"gc\.ttlseconds\s*=\s*(\d+)", str(row[-1]))
                    if match is not None:
                        facts.gc_ttlseconds = int(match.group(1))
    except Exception as exc:  # noqa: BLE001 - every failure here is a reportable answer
        message = str(exc).strip()
        facts.error = message or exc.__class__.__name__
        lowered = message.lower()
        facts.clock_error = any(marker in lowered for marker in CLOCK_ERROR_MARKERS)
    return facts


def check_psycopg() -> Check:
    """psycopg 3, which the proof script imports at module scope."""
    try:
        import psycopg
    except ImportError:
        return Check(
            key="psycopg",
            title="psycopg 3 (importable)",
            status=FAIL,
            observed="not importable by this interpreter",
            remedy=[
                "scripts/proof/gate_refusal.py imports psycopg at module scope.",
                "    just setup                       (uv sync --all-packages)",
                "or run the proof inside the workspace environment:",
                "    uv run --package trappoint-migrate python scripts/proof/gate_refusal.py",
            ],
        )
    return Check(
        key="psycopg",
        title="psycopg 3 (importable)",
        status=OK,
        observed=f"psycopg {psycopg.__version__}",
    )


def check_node_version(facts: NodeFacts, pin: str | None, reachable: bool) -> Check:
    """What is actually answering on 26257, and does it match the pin."""
    if not reachable:
        return Check(
            key="crdb-version",
            title="cockroachdb version",
            status=SKIP,
            observed="no node answered",
            blocking=False,
        )
    if facts.version is None:
        return Check(
            key="crdb-version",
            title="cockroachdb version",
            status=FAIL,
            observed=(facts.error or "no answer")[:160],
            remedy=[
                "Something is listening on 26257 but it did not answer `SELECT version()`.",
                "    docker compose -f compose.yaml logs --tail 50 crdb",
                "If another postgres owns the port, stop it or move this cluster.",
            ],
        )
    short = facts.version.split(" (", 1)[0]
    pinned_version = ""
    if pin is not None and ":" in pin:
        pinned_version = pin.split(":", 1)[1]
    if pinned_version and pinned_version.lstrip("v") not in facts.version:
        return Check(
            key="crdb-version",
            title="cockroachdb version",
            status=WARN,
            observed=f"{short}; the pin says {pinned_version}",
            blocking=False,
            remedy=[
                "The live node is not the pinned build. A DDL behaviour difference between",
                "them is exactly the drift the schema fingerprint exists to catch.",
                "    just nuke && just up      (destroys the local data volume, then repins)",
            ],
            detail={"version": facts.version, "pinned": pinned_version},
        )
    return Check(
        key="crdb-version",
        title="cockroachdb version",
        status=OK,
        observed=short,
        blocking=False,
        detail={"version": facts.version},
    )


def _restart_remedy() -> list[str]:
    """The remedy for a skewed node, naming the container that is actually running."""
    return [
        "The node's wall clock and this host's have diverged; the usual cause is a",
        "laptop that slept while the container kept running. CockroachDB refuses to",
        "serve rather than risk a stale read. Restarting the container resynchronises it:",
        f"    docker restart {_crdb_container_name()}",
        "    just doctor          (to confirm)",
    ]


def check_clock(facts: NodeFacts, reachable: bool, fail_at: float, warn_at: float) -> Check:
    """The one that is not hypothetical.

    After a host sleep this node answered `remote wall time is too far ahead (9.94 s)
    to be trustworthy`. The fix is `docker restart`, and it belongs here rather than in
    somebody's memory of a Tuesday.
    """
    if not reachable:
        return Check(
            key="clock",
            title="node clock vs host",
            status=SKIP,
            observed="no node answered",
            blocking=False,
        )
    if facts.clock_error:
        return Check(
            key="clock",
            title="node clock vs host",
            status=FAIL,
            observed=(facts.error or "the node refused on clock grounds")[:160],
            remedy=_restart_remedy(),
        )
    if facts.skew_seconds is None:
        return Check(
            key="clock",
            title="node clock vs host",
            status=SKIP,
            observed=(facts.error or "the node did not answer `SELECT now()`")[:160],
            blocking=False,
        )
    skew = facts.skew_seconds
    observed = f"{skew:+.3f}s (node - host, round trip removed)"
    if abs(skew) >= fail_at:
        return Check(
            key="clock",
            title="node clock vs host",
            status=FAIL,
            observed=observed,
            remedy=_restart_remedy(),
            detail={"skew_seconds": skew, "fail_at": fail_at},
        )
    if abs(skew) >= warn_at:
        return Check(
            key="clock",
            title="node clock vs host",
            status=WARN,
            observed=f"{observed} - CockroachDB's own tolerance is 0.500s",
            blocking=False,
            remedy=[
                (
                    "Not yet refusing, but drifting. If it grows past "
                    f"{fail_at:g}s the node will stop serving:"
                ),
                f"    docker restart {_crdb_container_name()}",
            ],
            detail={"skew_seconds": skew, "warn_at": warn_at},
        )
    return Check(
        key="clock",
        title="node clock vs host",
        status=OK,
        observed=observed,
        detail={"skew_seconds": skew},
    )


def check_gc_ttl(facts: NodeFacts, reachable: bool) -> Check:
    """Local defaults to 14400; Cloud enforces 4500. Local is the MORE permissive one."""
    if not reachable or facts.gc_ttlseconds is None:
        return Check(
            key="gc-ttl",
            title=f"gc.ttlseconds == {CLOUD_GC_TTL_SECONDS}",
            status=SKIP,
            observed="no node answered" if not reachable else "the zone config did not parse",
            blocking=False,
        )
    found = facts.gc_ttlseconds
    if found == CLOUD_GC_TTL_SECONDS:
        return Check(
            key="gc-ttl",
            title=f"gc.ttlseconds == {CLOUD_GC_TTL_SECONDS}",
            status=OK,
            observed=f"{found} - aligned with CockroachDB Cloud",
            blocking=False,
            detail={"gc_ttlseconds": found},
        )
    note = " (the permissive local default)" if found == LOCAL_DEFAULT_GC_TTL_SECONDS else ""
    return Check(
        key="gc-ttl",
        title=f"gc.ttlseconds == {CLOUD_GC_TTL_SECONDS}",
        status=WARN,
        observed=f"{found}{note}, Cloud enforces {CLOUD_GC_TTL_SECONDS}",
        blocking=False,
        remedy=[
            (
                f"Local is MORE permissive than Cloud ({found}s of history against "
                f"{CLOUD_GC_TTL_SECONDS}s), so an AS OF SYSTEM TIME query that reaches"
            ),
            "past Cloud's horizon passes here and fails on the nightly truth check.",
            "Align it:",
            "    just gc-align",
            "or, equivalently:",
            "    docker compose -f compose.yaml run --rm crdb-align",
            (
                "    (ALTER RANGE default CONFIGURE ZONE USING gc.ttlseconds = "
                f"{CLOUD_GC_TTL_SECONDS})"
            ),
            "The proof itself pins its own throwaway database, so this is fidelity, not a",
            "blocker.",
        ],
        detail={"gc_ttlseconds": found},
    )


def check_migration_tree() -> Check:
    """The tree `just prove` applies. Zero files is a checkout problem, not a bug."""
    if not MIGRATIONS_DIR.is_dir():
        return Check(
            key="migrations",
            title="migration tree",
            status=FAIL,
            observed=f"{MIGRATIONS_DIR.relative_to(REPO_ROOT)} does not exist",
            remedy=["This is not a complete checkout. `git status` and re-clone if need be."],
        )
    count = len(list(MIGRATIONS_DIR.glob("*.sql")))
    if count == 0:
        return Check(
            key="migrations",
            title="migration tree",
            status=FAIL,
            observed="0 .sql files",
            remedy=["The migration tree is empty; `just prove` has nothing to apply."],
        )
    return Check(
        key="migrations",
        title="migration tree",
        status=OK,
        observed=f"{count} .sql files in {MIGRATIONS_DIR.relative_to(REPO_ROOT).as_posix()}",
        detail={"files": count},
    )


def check_proof_script() -> Check:
    """`just prove` runs exactly one file; say so if it is not there."""
    if not PROOF_SCRIPT.is_file():
        return Check(
            key="proof",
            title="proof script",
            status=FAIL,
            observed=f"{PROOF_SCRIPT.relative_to(REPO_ROOT).as_posix()} is missing",
            remedy=["`just prove` runs that file. Without it there is no proof to run."],
        )
    return Check(
        key="proof",
        title="proof script",
        status=OK,
        observed=PROOF_SCRIPT.relative_to(REPO_ROOT).as_posix(),
    )


def check_workspace_installed() -> Check:
    """Has `uv sync` been run here yet. Advisory: `just prove` syncs on demand."""
    venv = REPO_ROOT / ".venv"
    if not venv.is_dir():
        return Check(
            key="workspace",
            title="workspace installed",
            status=WARN,
            observed=".venv/ does not exist",
            blocking=False,
            remedy=[
                "Nothing is installed yet. One command:",
                "    just setup        (installs uv if absent, then `uv sync --all-packages`)",
            ],
        )
    return Check(
        key="workspace",
        title="workspace installed",
        status=OK,
        observed=".venv/ present",
        blocking=False,
    )


# ── rendering ────────────────────────────────────────────────────────────────────────────


def render_table(checks: list[Check], stream: Any) -> None:
    """Print the whole preflight as one ASCII table. No colour, no unicode, no guessing."""
    title_width = max((len(c.title) for c in checks), default=10)
    title_width = max(title_width, len("CHECK"))
    header = f"{'STATUS':<6}  {'CHECK':<{title_width}}  OBSERVED"
    rule = f"{'-' * 6}  {'-' * title_width}  {'-' * 48}"
    print(header, file=stream)
    print(rule, file=stream)
    for check in checks:
        print(f"{check.status:<6}  {check.title:<{title_width}}  {check.observed}", file=stream)
    print(rule, file=stream)


def render_remedies(checks: list[Check], strict: bool, stream: Any) -> int:
    """Print the numbered remedy list. Return the count of blocking failures."""
    blocking = [c for c in checks if c.is_blocking_failure]
    advisory = [c for c in checks if c.status == WARN and c.remedy]
    if strict:
        blocking = blocking + [c for c in advisory if c not in blocking]
        advisory = []

    if blocking:
        noun = "check" if len(blocking) == 1 else "checks"
        print(f"\nNOT READY - {len(blocking)} blocking {noun}. In order:\n", file=stream)
        for number, check in enumerate(sorted(blocking, key=lambda c: c.key), start=1):
            print(f"  {number}. {check.title}: {check.observed}", file=stream)
            for line in check.remedy:
                print(f"     {line}", file=stream)
            print("", file=stream)
    else:
        print("\nREADY - everything the Tier-2 proof needs is present.", file=stream)
        print("        just up && just doctor && just prove\n", file=stream)

    if advisory:
        noun = "warning" if len(advisory) == 1 else "warnings"
        print(f"{len(advisory)} advisory {noun} (nothing here stops the proof):\n", file=stream)
        for number, check in enumerate(sorted(advisory, key=lambda c: c.key), start=1):
            print(f"  {number}. {check.title}: {check.observed}", file=stream)
            for line in check.remedy:
                print(f"     {line}", file=stream)
            print("", file=stream)

    return len(blocking)


# ── entry point ──────────────────────────────────────────────────────────────────────────


def collect(args: argparse.Namespace) -> list[Check]:
    """Run every check, in the order a reader wants to be told about them."""
    checks: list[Check] = []
    checks.append(check_python())

    docker_cli = check_docker_cli()
    checks.append(docker_cli)
    engine = check_docker_engine()
    checks.append(engine)

    checks.append(check_uv())
    checks.append(check_just())
    checks.append(check_psycopg())
    checks.append(check_workspace_installed())
    checks.append(check_node())
    checks.append(check_pnpm())

    pin_check, pin = check_pin()
    checks.append(pin_check)
    checks.append(check_image_pulled(pin, engine.status == OK))

    checks.append(check_migration_tree())
    checks.append(check_proof_script())

    dsn, provenance = (args.dsn, "--dsn") if args.dsn else _dsn_from_environment()
    host, port = _host_port(dsn)
    port_check, reachable = check_port(host, port, timeout=float(args.connect_timeout))
    port_check.observed = f"{port_check.observed} [{provenance}]"
    checks.append(port_check)

    facts = (
        interrogate_node(dsn, args.connect_timeout)
        if reachable
        else NodeFacts(error="nothing was listening")
    )
    checks.append(check_node_version(facts, pin, reachable))
    checks.append(check_clock(facts, reachable, args.max_clock_skew, args.warn_clock_skew))
    checks.append(check_gc_ttl(facts, reachable))
    return checks


_HOSTPORT = re.compile(r"^[a-zA-Z0-9+.\-]+://(?:[^@/]*@)?(?P<host>[^:/?#]+)(?::(?P<port>\d+))?")


def _host_port(dsn: str) -> tuple[str, int]:
    """Pull ``(host, port)`` out of a libpq URI; default to the local single node."""
    match = _HOSTPORT.match(dsn)
    if match is None:
        return "127.0.0.1", 26257
    host = match.group("host") or "127.0.0.1"
    port = int(match.group("port") or 26257)
    return host, port


def _survive_a_narrow_console() -> None:
    """Never let an encoding raise. A doctor that dies printing is worse than no doctor.

    A Windows console still running cp1252 cannot encode the em dashes in these remedy
    lines, and ``UnicodeEncodeError`` from the tool that exists to explain failures is
    the least helpful traceback in the repository.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        # `contextlib.suppress`: a stream that will not take an encoding argument is
        # a stream we print to unchanged, which is exactly what this function is for.
        with contextlib.suppress(OSError, ValueError):
            reconfigure(errors="replace")


def main(argv: list[str] | None = None) -> int:
    """Run the preflight; return 0 ready, 1 not ready, 2 could-not-run."""
    _survive_a_narrow_console()
    parser = argparse.ArgumentParser(
        prog="doctor",
        description=(
            "Preflight for the MAINLINE one-command loop. Reports, in one table, "
            "everything `just up && just doctor && just prove` depends on, and prints a "
            "numbered remedy for each thing that is missing."
        ),
    )
    parser.add_argument(
        "--dsn",
        default=None,
        help=(
            "cluster to interrogate; defaults to $MAINLINE_TEST_DSN / $TRAPPOINT_DSN / "
            "$COCKROACH_URL / $CRDB_URL / $LOCAL_DSN, then the local single node"
        ),
    )
    parser.add_argument(
        "--connect-timeout",
        type=int,
        default=5,
        help="seconds to wait for the pgwire socket and for libpq (default 5)",
    )
    parser.add_argument(
        "--max-clock-skew",
        type=float,
        default=CLOCK_SKEW_FAIL_SECONDS,
        help=(
            "seconds of node-vs-host wall-clock difference that FAILS the preflight "
            f"(default {CLOCK_SKEW_FAIL_SECONDS:g}; CockroachDB's own tolerance is 0.5)"
        ),
    )
    parser.add_argument(
        "--warn-clock-skew",
        type=float,
        default=CLOCK_SKEW_WARN_SECONDS,
        help=f"seconds of skew that warns without failing (default {CLOCK_SKEW_WARN_SECONDS:g})",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="treat every advisory warning as a blocking failure (what a workflow wants)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit the whole report as JSON on stdout and print no table",
    )
    parser.add_argument(
        "--print-pin",
        action="store_true",
        help=(
            "print the pinned CockroachDB image from compose.yaml and exit; used by "
            "`just up`, which must work before uv is installed"
        ),
    )
    args = parser.parse_args(argv)

    if args.print_pin:
        try:
            pin, _ = read_pin()
        except PinNotFound as exc:
            print(f"doctor: {exc}", file=sys.stderr)
            return EXIT_USAGE
        print(pin)
        return EXIT_READY

    checks = collect(args)

    if args.json:
        blocking = [c for c in checks if c.is_blocking_failure]
        if args.strict:
            blocking = blocking + [c for c in checks if c.status == WARN and c not in blocking]
        report = {
            "schema": "mainline.qa.doctor/1",
            "generated_utc": datetime.now(UTC).isoformat(timespec="seconds"),
            "host": {
                "platform": HOST_PLATFORM,
                "release": platform.platform(),
                "python": sys.version.split()[0],
            },
            "strict": bool(args.strict),
            "ready": not blocking,
            "blocking": [c.key for c in blocking],
            "checks": [c.as_dict() for c in checks],
        }
        json.dump(report, sys.stdout, indent=2, sort_keys=False)
        sys.stdout.write("\n")
        return EXIT_READY if not blocking else EXIT_NOT_READY

    print(
        f"MAINLINE preflight - {platform.platform()} - "
        f"{datetime.now(UTC).isoformat(timespec='seconds')}\n"
    )
    # Declaration order, deliberately: the table reads top to bottom the way a reader
    # discovers the problem — interpreter, engine, tools, then the cluster itself.
    render_table(checks, sys.stdout)
    failures = render_remedies(checks, args.strict, sys.stdout)
    return EXIT_READY if failures == 0 else EXIT_NOT_READY


if __name__ == "__main__":
    raise SystemExit(main())
