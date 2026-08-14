#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""Prove the LIVE console against the REAL handler, in a REAL browser, on this machine.

WHY THIS PROGRAM EXISTS
-----------------------
On 2026-08-14 the founder opened the deployed demo URL and the header read
``TRANSPORT REPLAY (staged)``. Every byte on that screen was a recorded
``EvidenceBundle`` played back over an origin that had a live kernel sitting behind it.
``src/app/source-select.ts`` was not wrong: it was handed ``VITE_MAINLINE_API_BASE:""``
by the build, and an empty string is unset. **The defect was a build-time value, not a
logic error**, and no test of a pure function can catch a build-time value, because such
a test supplies the value itself.

So the proof has to be a BUILD plus a BROWSER, end to end, with nothing stubbed:

1. build the console with ``VITE_MAINLINE_API_BASE`` and ``MAINLINE_BUILD_ID`` set;
2. read the COMPILED literal back out of ``dist/assets/index-*.js`` before trusting it;
3. run the packaging guard (``build_lambda``'s embedded packer, W4) over that dist under
   ``--console-transport live`` and require it to PASS -- and over the artefact that
   shipped and require it to REFUSE, which is the same guard falsified rather than
   merely exercised;
4. serve the dist through ``scripts/deploy/local_furl.py``, which calls
   ``mainline_demo_api.app.handler(event, None)`` UNSTUBBED behind a Lambda Function URL
   payload-format-2.0 emulation;
5. drive a real chromium at it and record what the page did.

THE ANSWER IS 503 ``dsn_unset``, AND THAT IS THE PASSING CONDITION
-------------------------------------------------------------------
The SSM parameter ``/mainline/demo/cockroach_dsn`` is the founder's step and is not this
wave's. Until it is written, LIVE mode answers ``503 dsn_unset`` -- a reachable route
refusing for a NAMED reason, which is not a 404 and must never be described as one. What
this program proves is that the console **attempts the live kernel** and **renders the
refusal honestly**. Ruling R8 of ``docs/leads/console-live-plan.md``. A green that
required a working DSN would be a green nobody in this wave could run.

**No DSN is supplied, read, printed or guessed anywhere below.** The emulator is started
with ``MAINLINE_DSN``, ``MAINLINE_DSN_PARAM`` and every ``AWS_*`` name removed from its
environment, so the handler cannot reach a database or an SSM parameter even by accident,
and every string captured from the wire passes through :func:`redact` before it is
written down.

THE EMULATOR IS NOT THE DEPLOYMENT, AND THE EVIDENCE SAYS SO IN ITS OWN FIELD
-----------------------------------------------------------------------------
``local_furl.py`` stamps ``x-mainline-emulator: local_furl`` on every response precisely
so that a transcript taken against it can never be mistaken for one taken against
``https://…lambda-url.ap-southeast-1.on.aws``. That header is read back off the wire here
and recorded, and ``target.is_the_deployment`` is a first-class ``false`` in the output.

THE HAZARD THAT HAS BITTEN THIS REPOSITORY BEFORE
--------------------------------------------------
``docs/deploy/console-build.md`` §1 records MSYS path conversion turning
``VITE_MAINLINE_API_BASE=/`` into ``C:/Program Files/Git/`` on a Git Bash command line --
observed in a real artefact on 2026-08-10 and again on 2026-08-14. This program never
builds a command line: it passes an environment MAPPING to :func:`subprocess.run`, which
no shell ever sees. It then reads the compiled literal back out of the bytes and refuses
a converted value BY NAME. Verifying the artefact is not optional here; it is step 2.

WHAT IT WILL NOT DO
-------------------
No ``terraform apply``. No Lambda update. No upload of anything it builds -- the dists go
to a temporary directory, never to ``dist/``, and the ORCHESTRATOR deploys. It writes the
SSM parameter never, prints a DSN never, and marks no failing assertion advisory.

USAGE
-----
::

    D:/CoackroachDBxAWS/mainline/.venv/Scripts/python.exe \\
        scripts/deploy/console_live_acceptance.py

    --out PATH        evidence file (default evidence/deploy/console-live.json)
    --build-id ID     what the artefact calls itself (default: UTC stamp + git sha)
    --api-base VALUE  compiled into the LIVE build (default "/", one origin, no CORS)
    --keep            keep the temporary build and serve trees for inspection
    --skip-replay     run only the LIVE proof (the contrast run is on by default)
    --headed          watch the browser
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import types
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

REPO_ROOT: Final = Path(__file__).resolve().parents[2]
CONSOLE: Final = REPO_ROOT / "verticals" / "mainline" / "apps" / "console"
DEMO_API_SRC: Final = REPO_ROOT / "verticals" / "mainline" / "apps" / "demo-api" / "src"
SOURCE_PKG: Final = DEMO_API_SRC / "mainline_demo_api"
EVIDENCE_BUNDLE: Final = CONSOLE / "fixtures" / "bundles" / "demo-cloud"
BUILD_SH: Final = REPO_ROOT / "scripts" / "deploy" / "build_lambda.sh"
BUILD_PS1: Final = REPO_ROOT / "scripts" / "deploy" / "build_lambda.ps1"
LOCAL_FURL: Final = REPO_ROOT / "scripts" / "deploy" / "local_furl.py"
DRIVER: Final = CONSOLE / "scripts" / "drive-console.mjs"
DEFAULT_OUT: Final = REPO_ROOT / "evidence" / "deploy" / "console-live.json"

#: The heredoc markers ``build_lambda.sh`` / ``.ps1`` wrap the embedded packer in. The
#: same two constants ``tests/deploy/test_console_transport_guard.py`` uses, because the
#: guard under test here is the same program that test pins.
SH_BEGIN: Final = "cat > \"$PACKER.crlf\" <<'PACKER_EOF'"
SH_END: Final = "PACKER_EOF"
PS_BEGIN: Final = "$Packer = @'"
PS_END: Final = "'@"

#: ``$MAINLINE_WEB_ROOT`` for the emulator is ``<stage>/web``: the packer's own tree
#: shape, so ``strip_maps`` and ``gzip_siblings`` can be called on it unmodified.
WEB: Final = "web"

#: Anything shaped like a connection string never reaches the evidence file. Nothing
#: below is expected to produce one -- the emulator runs with no DSN at all -- and that
#: is exactly why the guard is cheap to keep.
DSN_PATTERN: Final = re.compile(r"(?i)\b(?:postgres(?:ql)?|cockroach(?:db)?)://[^\s\"'<>]*")

#: Names removed from the emulator's environment. Without them ``db.connection()`` raises
#: ``DsnUnavailable`` and ``app.py`` answers ``503 dsn_unset`` -- which is the answer this
#: program is here to see rendered, and is also the answer that guarantees no credential
#: and no cloud call is anywhere in this run.
SCRUBBED_ENV: Final = (
    "MAINLINE_DSN",
    "MAINLINE_DSN_PARAM",
    "MAINLINE_DEMO_PERMIT_ID",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
    "AWS_PROFILE",
    "AWS_REGION",
    "AWS_DEFAULT_REGION",
)

EXIT_OK: Final = 0
EXIT_FAILED: Final = 1
EXIT_UNUSABLE: Final = 3


# ══════════════════════════════════════════════════════════════════════════════════════
# small helpers
# ══════════════════════════════════════════════════════════════════════════════════════


def say(message: str) -> None:
    sys.stdout.write(f"console_live: {message}\n")
    sys.stdout.flush()


def redact(value: str | None) -> str | None:
    """Replace anything shaped like a connection string. Applied to every captured byte."""
    if value is None:
        return None
    return DSN_PATTERN.sub("[redacted: a connection string was here]", value)


def utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_text(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
    """``subprocess.run`` with the decoding pinned, because Windows does not pin it.

    ``text=True`` alone decodes with ``locale.getencoding()`` -- cp1252 on this
    workstation -- and vite prints a U+2713 in its success line. The first run of this
    program died inside the reader thread on exactly that byte, and lost the child's
    stderr with it: a measurement destroyed by the act of reading it. UTF-8 with
    ``errors="replace"`` decodes every child in this file the same way on every platform.
    """
    return subprocess.run(
        argv,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        **kwargs,
    )


def git_short_sha() -> str:
    """The commit, for the build id. ``nogit`` rather than a guess when there is none."""
    try:
        done = run_text(["git", "rev-parse", "--short", "HEAD"], cwd=str(REPO_ROOT))
    except OSError:
        return "nogit"
    out = done.stdout.strip()
    return out if done.returncode == 0 and out else "nogit"


def free_port() -> int:
    """A port the OS just told us is free. ``--port 0`` inside local_furl would also do
    this, but the ready-file handshake is simpler when the caller already knows it."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class Result:
    """One named claim, with the values that produced the verdict beside it.

    There is no advisory tier and no skip. Ruling: never mark a failing assertion
    advisory. A step that fails is recorded as failed and the program exits non-zero.
    """

    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def record(self, step: str, ok: bool, expected: Any, actual: Any, why: str) -> bool:
        self.rows.append(
            {"step": step, "ok": bool(ok), "expected": expected, "actual": actual, "why": why}
        )
        if not ok:
            say(f"FAILED {step}: expected {expected!r}, got {actual!r}")
        return bool(ok)

    @property
    def failures(self) -> list[dict[str, Any]]:
        return [row for row in self.rows if not row["ok"]]

    @property
    def ok(self) -> bool:
        return not self.failures


# ══════════════════════════════════════════════════════════════════════════════════════
# the packaging guard, extracted the way the wrappers extract it
# ══════════════════════════════════════════════════════════════════════════════════════


def packer_body(path: Path, begin: str, end: str) -> str:
    """The embedded packer, LF-normalised exactly as both wrappers normalise it."""
    lines = path.read_text(encoding="utf-8").split("\n")
    start = lines.index(begin) + 1
    stop = lines.index(end, start)
    return "\n".join(line.rstrip("\r") for line in lines[start:stop]) + "\n"


def extract_packer(into: Path) -> tuple[Path, dict[str, Any]]:
    """Write the packer out of ``build_lambda.sh`` and check the ``.ps1`` twin agrees.

    Both wrappers print the packer's sha256 for exactly this reason. Checking it here
    means this program cannot prove a dist against a guard that only half of the build
    machinery carries.
    """
    body = packer_body(BUILD_SH, SH_BEGIN, SH_END)
    twin = packer_body(BUILD_PS1, PS_BEGIN, PS_END)
    target = into / "_packer_under_proof.py"
    target.write_text(body, encoding="utf-8", newline="")
    return target, {
        "extracted_from": str(BUILD_SH.relative_to(REPO_ROOT)).replace(os.sep, "/"),
        "sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
        "twin_is_identical": body == twin,
        "bytes": len(body.encode("utf-8")),
    }


def load_packer(path: Path) -> types.ModuleType:
    """Import the extracted packer by path. It is a program, not a package."""
    spec = importlib.util.spec_from_file_location("mainline_packer_for_console_live", path)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise RuntimeError(f"{path} is not importable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def run_guard(packer_path: Path, dist: Path, transport: str) -> dict[str, Any]:
    """``--mode preflight`` in a subprocess: the gate as the wrappers reach it.

    Preflight is where both wrappers gate the dist, before pip touches the network, and
    it is the mode whose only inputs are a handler package, a dist and a bundle. Running
    it as a program rather than calling ``console_gate`` directly proves the WIRING too:
    a gate that is correct and unreachable is the defect this whole wave is about.
    """
    argv = [
        sys.executable,
        str(packer_path),
        "--mode",
        "preflight",
        "--source-pkg",
        str(SOURCE_PKG),
        "--dist",
        str(dist),
        "--bundle",
        str(EVIDENCE_BUNDLE),
        "--console-transport",
        transport,
    ]
    done = run_text(argv, cwd=str(REPO_ROOT))
    return {
        "console_transport": transport,
        "exit_code": done.returncode,
        "stdout": redact(done.stdout),
        "stderr": redact(done.stderr),
    }


# ══════════════════════════════════════════════════════════════════════════════════════
# the build
# ══════════════════════════════════════════════════════════════════════════════════════

ENV_LITERAL: Final = re.compile(r'VITE_MAINLINE_([A-Z_]+):"((?:[^"\\]|\\.)*)"')
BUILD_ID_LITERAL: Final = re.compile(r'buildId:"((?:[^"\\]|\\.)*)"')

#: The exact value MSYS produced when it converted a bare ``/`` on a Git Bash command
#: line, measured 2026-08-10 and again 2026-08-14. Refused by name: a compiled console
#: that names a path on somebody's laptop is not a subtle failure, but it is a silent one.
MSYS_CONVERTED: Final = "Program Files"


def build_console(
    label: str,
    out_dir: Path,
    api_base: str | None,
    build_id: str | None,
    pnpm: str,
) -> dict[str, Any]:
    """``pnpm exec vite build --mode demo`` with an environment MAPPING, never a command line.

    ``api_base`` of ``None`` means "do not set it": ``.env.demo`` declares it empty on
    purpose, which is Phase 1 and is the artefact that shipped. ``build_id`` of ``None``
    means ``MAINLINE_BUILD_ID`` is not supplied, which is how ``vite.config.ts``'s
    ``'dev'`` fallback ends up in the bytes.
    """
    env = dict(os.environ)
    env.pop("VITE_MAINLINE_API_BASE", None)
    env.pop("MAINLINE_BUILD_ID", None)
    if api_base is not None:
        env["VITE_MAINLINE_API_BASE"] = api_base
    if build_id is not None:
        env["MAINLINE_BUILD_ID"] = build_id

    argv = [
        pnpm,
        "exec",
        "vite",
        "build",
        "--mode",
        "demo",
        "--outDir",
        str(out_dir),
        "--emptyOutDir",
    ]
    started = time.monotonic()
    done = run_text(argv, cwd=str(CONSOLE), env=env)
    elapsed_ms = int((time.monotonic() - started) * 1000)
    return {
        "label": label,
        "out_dir": str(out_dir),
        "env_supplied": {
            "VITE_MAINLINE_API_BASE": api_base,
            "MAINLINE_BUILD_ID": build_id,
        },
        "command": ["<pnpm>", *argv[1:]],
        "passed_as": "an environment mapping to subprocess.run: no shell, so no MSYS "
        "path conversion is possible on this line (docs/deploy/console-build.md §1)",
        "exit_code": done.returncode,
        "elapsed_ms": elapsed_ms,
        "stdout_tail": redact("\n".join(done.stdout.splitlines()[-12:])),
        "stderr_tail": redact("\n".join(done.stderr.splitlines()[-24:])),
    }


def read_compiled_literals(dist: Path) -> dict[str, Any]:
    """Read back what vite actually inlined. Step 2, and it is never skipped.

    Only ``assets/*.js`` is scanned, which is what ``probe_console`` scans, so the two
    readings are of the same bytes. The entry chunk is reported separately because the
    brief names ``dist/assets/index-*.js`` as the thing to verify.
    """
    assets = dist / "assets"
    literals: dict[str, list[str]] = {}
    build_ids: list[str] = []
    entry: dict[str, Any] | None = None
    for path in sorted(assets.glob("*.js")):
        text = path.read_text(encoding="utf-8", errors="replace")
        for key, value in ENV_LITERAL.findall(text):
            literals.setdefault(f"VITE_MAINLINE_{key}", [])
            if value not in literals[f"VITE_MAINLINE_{key}"]:
                literals[f"VITE_MAINLINE_{key}"].append(value)
        for value in BUILD_ID_LITERAL.findall(text):
            if value not in build_ids:
                build_ids.append(value)
        if path.name.startswith("index-") and entry is None:
            entry = {
                "name": f"assets/{path.name}",
                "bytes": path.stat().st_size,
                "sha256": sha256_of(path),
            }
    return {
        "entry_chunk": entry,
        "literals": {key: sorted(values) for key, values in sorted(literals.items())},
        "build_ids": sorted(build_ids),
        "scanned_js": len(list(assets.glob("*.js"))),
        "how": 'grep -o \'VITE_MAINLINE_API_BASE:"[^"]*"\' over dist/assets/*.js, in '
        "Python so no shell can rewrite the pattern",
    }


# ══════════════════════════════════════════════════════════════════════════════════════
# the served tree
# ══════════════════════════════════════════════════════════════════════════════════════


def stage_web_root(
    packer: types.ModuleType, dist: Path, stage: Path, bundle: Path | None
) -> dict[str, Any]:
    """Compose the tree the Lambda would serve, using the PACKER'S OWN two functions.

    ``strip_maps`` and ``gzip_siblings`` are imported from the extracted packer rather
    than reimplemented here. That matters for one measured reason: ``static_site.py``
    refuses any single response above ``DEFAULT_MAX_RESPONSE_BYTES`` (136 KiB), the
    console's entry chunk is ~450 KB of identity bytes, and it is served at all only
    because the packer wrote a level-9 ``.gz`` sibling beside it and the browser sent
    ``accept-encoding: gzip``. A serve tree without the siblings would answer a browser
    with ``413 response_too_large`` -- so an emulator fed raw ``dist/`` would be testing a
    tree that does not exist anywhere, and raising the ceiling to make it work would be
    weakening the exact cost control that ceiling is.

    ``bundle`` is copied to ``web/bundle/`` for the REPLAY contrast run, which is where
    ``VITE_MAINLINE_BUNDLE_URL=./bundle/`` resolves to.
    """
    web = stage / WEB
    if stage.exists():
        shutil.rmtree(stage)
    shutil.copytree(dist, web)
    if bundle is not None:
        shutil.copytree(bundle, web / "bundle")
    packer.refusals[:] = []
    removed = packer.strip_maps(str(stage))
    siblings = packer.gzip_siblings(str(stage))
    census = packer.web_census(str(stage))
    return {
        "web_root": str(web),
        "bundle_staged": None
        if bundle is None
        else str(bundle.relative_to(REPO_ROOT)).replace(os.sep, "/"),
        "source_maps_removed": len(removed),
        "gz_siblings_written": len(siblings),
        "entries": census["entries"],
        "bytes": census["bytes"],
        "largest_identity": packer.largest_web(str(stage), False),
        "largest_gz": packer.largest_web(str(stage), True),
        "packer_refusals": list(packer.refusals),
        "why": "the packer's own strip_maps() and gzip_siblings(), so the emulator serves "
        "the tree the Lambda would serve rather than a raw dist/ that static_site.py "
        "would answer with 413 response_too_large",
    }


# ══════════════════════════════════════════════════════════════════════════════════════
# the emulator
# ══════════════════════════════════════════════════════════════════════════════════════


class Emulator:
    """``scripts/deploy/local_furl.py`` in a child process, with a scrubbed environment.

    The handler is the real one and is never stubbed: ``local_furl`` imports
    ``mainline_demo_api.app`` and calls ``handler(event, None)`` with a Lambda Function
    URL payload-format-2.0 event it builds from the HTTP request.
    """

    def __init__(self, web_root: Path, log: Path, ready: Path) -> None:
        self.web_root = web_root
        self.log = log
        self.ready = ready
        self.port = free_port()
        self.base_url = f"http://127.0.0.1:{self.port}"
        self.process: subprocess.Popen[bytes] | None = None
        self.scrubbed: list[str] = []

    def start(self) -> None:
        env = dict(os.environ)
        for name in SCRUBBED_ENV:
            if env.pop(name, None) is not None:
                self.scrubbed.append(name)
        argv = [
            sys.executable,
            str(LOCAL_FURL),
            "--host",
            "127.0.0.1",
            "--port",
            str(self.port),
            "--web-root",
            str(self.web_root),
            "--require-web-root",
            "--ready-file",
            str(self.ready),
            "--quiet",
        ]
        handle = self.log.open("wb")
        self.process = subprocess.Popen(
            argv, cwd=str(REPO_ROOT), env=env, stdout=handle, stderr=subprocess.STDOUT
        )
        deadline = time.monotonic() + 45.0
        while time.monotonic() < deadline:
            if self.ready.exists() and self.ready.read_text(encoding="utf-8").strip():
                return
            if self.process.poll() is not None:
                raise RuntimeError(
                    f"local_furl exited {self.process.returncode} before listening; see {self.log}"
                )
            time.sleep(0.2)
        raise RuntimeError(f"local_furl did not report ready within 45 s; see {self.log}")

    def stop(self) -> None:
        if self.process is None:
            return
        self.process.terminate()
        try:
            self.process.wait(timeout=15)
        except subprocess.TimeoutExpired:  # pragma: no cover - defensive
            self.process.kill()
            self.process.wait(timeout=15)

    def banner(self) -> list[str]:
        if not self.log.exists():
            return []
        text = self.log.read_text(encoding="utf-8", errors="replace")
        return [redact(line) or "" for line in text.splitlines()]


def probe(base_url: str, method: str, path: str, body: bytes | None = None) -> dict[str, Any]:
    """One HTTP exchange against the emulator, recorded verbatim and redacted.

    ``curl`` is not used: a subprocess would put the URL on a command line, and this
    program's whole discipline is that nothing it measures passes through a shell.

    The scheme is asserted rather than assumed. ``base_url`` is built in :class:`Emulator`
    from a loopback host and a port the OS handed us, so it cannot be anything else -- and
    a check that can never fail is exactly the check that survives the refactor which
    makes it fail. It is also what makes the ``S310`` suppression below an argument rather
    than a silencing.
    """
    url = f"{base_url}{path}"
    if not url.startswith("http://127.0.0.1:"):
        raise ValueError(f"probe refuses a non-loopback URL: {url!r}")
    request = urllib.request.Request(url, method=method, data=body)  # noqa: S310 - scheme
    # is asserted on the line above; this program never probes anything but its own
    # emulator on 127.0.0.1.
    request.add_header("accept", "application/json")
    if body is not None:
        request.add_header("content-type", "application/json")
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 - loopback
            status = response.status
            headers = dict(response.headers.items())
            payload = response.read()
    except urllib.error.HTTPError as exc:
        status = exc.code
        headers = dict(exc.headers.items())
        payload = exc.read()
    elapsed_ms = int((time.monotonic() - started) * 1000)
    text = payload.decode("utf-8", "replace")
    parsed: Any = None
    try:
        parsed = json.loads(text)
    except ValueError:
        parsed = None
    return {
        "method": method,
        "path": path,
        "status": status,
        "bytes": len(payload),
        "elapsed_ms": elapsed_ms,
        "headers": {key.lower(): redact(value) for key, value in headers.items()},
        "emulator_header": headers.get("x-mainline-emulator", headers.get("X-Mainline-Emulator")),
        "body": redact(text),
        "body_json": json.loads(redact(json.dumps(parsed))) if parsed is not None else None,
    }


# ══════════════════════════════════════════════════════════════════════════════════════
# the browser
# ══════════════════════════════════════════════════════════════════════════════════════


def drive(node: str, base_url: str, out: Path, options: list[str]) -> dict[str, Any]:
    """``node scripts/drive-console.mjs`` -- the Playwright LIBRARY API, ruling R7.

    Never ``playwright test``, never a config, never a file under ``tests/browser/``.
    """
    argv = [node, str(DRIVER), "--base-url", base_url, "--out", str(out), *options]
    done = run_text(argv, cwd=str(CONSOLE))
    record: Any = None
    if out.exists():
        record = json.loads(redact(out.read_text(encoding="utf-8")) or "null")
    return {
        "exit_code": done.returncode,
        "stdout": redact(done.stdout),
        "stderr": redact(done.stderr),
        "run": record,
    }


def measure_console_lint(pnpm: str) -> dict[str, Any]:
    """MEASURE what ``pnpm run lint`` makes of the driver. A known conflict, on the record.

    THIS IS NOT A STEP OF THE PROOF, AND IT IS NOT MARKED ADVISORY EITHER. It is a
    measurement of a collision between two things that are both correct, reported so a
    lead can decide rather than discover.

    Measured on 2026-08-14 in this workspace:

    * ``pnpm exec eslint . --max-warnings 0`` with the driver ABSENT -> exit 0, clean;
    * the same command with ``scripts/drive-console.mjs`` PRESENT -> exit 1::

          Parsing error: "parserOptions.project" has been provided for
          @typescript-eslint/parser. The file was not found in any of the provided
          project(s): scripts\\drive-console.mjs

    The cause is in ``eslint.config.js``: the block that supplies
    ``parserOptions.project: ['./tsconfig.json', './tsconfig.node.json']`` carries **no**
    ``files`` key, so it applies the type-aware TypeScript parser to every linted file --
    including ``.mjs``, which no tsconfig includes (neither sets ``allowJs``). Any
    ``.mjs``/``.cjs``/``.js`` anywhere in this workspace except ``eslint.config.js``
    itself, which has its own override, hits it.

    ``docs/leads/console-live-plan.md`` names
    ``verticals/mainline/apps/console/scripts/drive-console.mjs`` as this worker's path
    and ``eslint.config.js`` as nobody's. So the file is delivered where the plan puts it
    and the collision is reported here rather than resolved by editing another worker's
    file or by quietly renaming the deliverable.

    The remedy is one line, and the better of the two fixes the class rather than the
    instance -- give that block a ``files: ['**/*.{ts,tsx}']`` so type-aware linting
    applies to the files a tsconfig actually contains. Adding ``'scripts/**/*.mjs'`` to
    ``ignores`` also works and stops linting the file at all, which is worse.
    """
    done = run_text(
        [pnpm, "exec", "eslint", str(DRIVER.relative_to(CONSOLE)), "--max-warnings", "0"],
        cwd=str(CONSOLE),
    )
    return {
        "command": "pnpm exec eslint scripts/drive-console.mjs --max-warnings 0",
        "exit_code": done.returncode,
        "clean": done.returncode == 0,
        "output": redact("\n".join((done.stdout + done.stderr).splitlines()[:12])),
        "measured_baseline": (
            "pnpm exec eslint . --max-warnings 0 with this file ABSENT exited 0 on "
            "2026-08-14; the console workspace lint was green before this file and this "
            "file is the only cause of any failure recorded here."
        ),
        "cause": (
            "eslint.config.js supplies parserOptions.project in a block with no `files` "
            "key, so the type-aware TypeScript parser is applied to .mjs as well, and no "
            "tsconfig in this workspace includes .mjs (neither sets allowJs)."
        ),
        "remedy": (
            "One line in eslint.config.js: give that languageOptions block "
            "`files: ['**/*.{ts,tsx}']`. That fixes the class. Adding 'scripts/**/*.mjs' "
            "to `ignores` fixes the instance and stops linting the file, which is worse."
        ),
        "owner": (
            "eslint.config.js is owned by no worker in docs/leads/console-live-plan.md §2. "
            "This worker did not edit it. The lead assigns it."
        ),
        "not_a_defect_in": str(DRIVER.relative_to(REPO_ROOT)).replace(os.sep, "/"),
    }


# ══════════════════════════════════════════════════════════════════════════════════════
# the program
# ══════════════════════════════════════════════════════════════════════════════════════


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="console_live_acceptance",
        description=(
            "Build the console for LIVE, gate it with the packaging guard, serve it "
            "through the real handler and drive a real chromium at it."
        ),
    )
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--build-id", default="")
    parser.add_argument(
        "--api-base",
        default="/",
        help="compiled into the LIVE build. '/' means one origin and no CORS anywhere.",
    )
    parser.add_argument("--keep", action="store_true", help="keep the temporary trees")
    parser.add_argument("--skip-replay", action="store_true", help="skip the contrast run")
    parser.add_argument(
        "--skip-lint-probe",
        action="store_true",
        help="do not measure what pnpm run lint makes of the driver (see the module note)",
    )
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--timeout", type=int, default=30000, help="browser timeout, ms")
    parser.add_argument(
        "--chromium",
        default="",
        help=(
            "a chromium executable to drive. Default: the newest chromium already "
            "installed on this machine. Nothing is ever downloaded."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:  # noqa: PLR0912, PLR0915 - one linear
    # program with one report at the end; splitting it would separate a measurement from
    # the claim it supports, which is the failure mode this whole wave is about.
    args = build_parser().parse_args(argv)
    result = Result()

    pnpm = shutil.which("pnpm")
    node = shutil.which("node")
    if pnpm is None or node is None:
        say("pnpm and node must both be on PATH; this program builds and drives the console")
        return EXIT_UNUSABLE

    build_id = args.build_id or f"w5-{utc_now()}-{git_short_sha()}"
    workspace = Path(tempfile.mkdtemp(prefix="mainline-console-live-"))
    say(f"workspace {workspace}")
    say(f"build id  {build_id}")

    record: dict[str, Any] = {
        "schema": "mainline.evidence.console-live/1",
        "generated_at": utc_now(),
        "generated_by": "scripts/deploy/console_live_acceptance.py",
        "purpose": (
            "Prove that a console built with VITE_MAINLINE_API_BASE set reads LIVE in its "
            "own honesty chrome, addresses POST /v1/demo/gate-run on its own origin, and "
            "renders the kernel's answer verbatim -- driven by a real chromium against the "
            "real, unstubbed mainline_demo_api.app.handler."
        ),
        "target": {
            "kind": "local_emulator",
            "is_the_deployment": False,
            "emulator": "scripts/deploy/local_furl.py",
            "emulates": "AWS Lambda Function URL, payload format 2.0, authorization NONE",
            "handler": "mainline_demo_api.app.handler(event, None), UNSTUBBED",
            "marker": "every response carries x-mainline-emulator: local_furl",
            "the_deployment_is": (
                "https://ihuuyvm4z6nfuktihnkey77fpy0eyrhj.lambda-url.ap-southeast-1.on.aws "
                "-- NOT measured here. Nothing in this file is a transcript of it, and the "
                "emulator header above is what keeps the two apart."
            ),
        },
        "secrets": {
            "dsn_supplied": False,
            "ssm_parameter_written": False,
            "scrubbed_from_the_emulator_environment": list(SCRUBBED_ENV),
            "note": (
                "The SSM parameter /mainline/demo/cockroach_dsn is the founder's step and "
                "is not this wave's. The kernel therefore answers 503 dsn_unset, and that "
                "answer rendered honestly IS the passing condition (ruling R8). Every "
                "captured string passes through a connection-string redaction before it is "
                "written here."
            ),
        },
        "deploy": {
            "terraform_apply": False,
            "lambda_updated": False,
            "anything_uploaded": False,
            "note": "Built to a temporary directory, never to dist/. The ORCHESTRATOR deploys.",
        },
        "build_id": build_id,
        "runs": [],
    }

    if not args.skip_lint_probe:
        record["console_workspace_lint"] = measure_console_lint(pnpm)
        if not record["console_workspace_lint"]["clean"]:
            say(
                "NOTE eslint refuses scripts/drive-console.mjs; see console_workspace_lint "
                "in the evidence file. Cause and one-line remedy are recorded there."
            )

    try:
        packer_path, packer_info = extract_packer(workspace)
        packer = load_packer(packer_path)
        record["packaging_guard"] = packer_info
        result.record(
            "the_two_builders_embed_the_same_guard",
            packer_info["twin_is_identical"],
            True,
            packer_info["twin_is_identical"],
            "build_lambda.sh and build_lambda.ps1 carry one program byte for byte. A guard "
            "in one twin and not the other is half a guard.",
        )

        plans = [
            {
                "label": "live",
                "api_base": args.api_base,
                "build_id": build_id,
                "declared_transport": "live",
                "guard_must": 0,
                # The LIVE dist declared REPLAY must be REFUSED too. Both builds carry
                # VITE_MAINLINE_BUNDLE_URL, so this is the direction that proves the gate
                # reads `initial` -- what selectSource would START with -- rather than
                # "is a bundle URL present anywhere". A guard that only ever refused the
                # replay-only dist would be satisfied by testing for one variable.
                "also_gate_as": "replay",
                "stage_bundle": False,
            }
        ]
        if not args.skip_replay:
            plans.append(
                {
                    # The Phase-1 command, verbatim: .env.demo alone, no
                    # VITE_MAINLINE_API_BASE and no MAINLINE_BUILD_ID. This reproduces the
                    # artefact the founder opened -- VITE_MAINLINE_API_BASE:"" and
                    # buildId:"dev" -- so the contrast is the real thing and not a mock-up.
                    "label": "replay",
                    "api_base": None,
                    "build_id": None,
                    "declared_transport": "replay",
                    "guard_must": 0,
                    "also_gate_as": "live",
                    "stage_bundle": True,
                }
            )

        for plan in plans:
            label = str(plan["label"])
            say(f"--- {label} -----------------------------------------------------")
            dist = workspace / f"dist-{label}"
            stage = workspace / f"serve-{label}"

            built = build_console(
                label,
                dist,
                plan["api_base"],
                plan["build_id"],
                pnpm,  # type: ignore[arg-type]
            )
            result.record(
                f"{label}_build_succeeded",
                built["exit_code"] == 0,
                0,
                built["exit_code"],
                "vite build --mode demo, with the variables supplied as an environment "
                "mapping rather than on a command line.",
            )
            if built["exit_code"] != 0:
                record["runs"].append({"label": label, "build": built})
                continue

            compiled = read_compiled_literals(dist)
            api_literals = compiled["literals"].get("VITE_MAINLINE_API_BASE", [])
            expected_api = plan["api_base"] if plan["api_base"] is not None else ""
            result.record(
                f"{label}_compiled_api_base_is_what_was_supplied",
                api_literals == [expected_api],
                [expected_api],
                api_literals,
                "Read back out of dist/assets/*.js. This is the step that catches the "
                "class of defect that shipped: a build-time value, invisible to any test "
                "that supplies its own value.",
            )
            result.record(
                f"{label}_no_msys_path_conversion",
                all(MSYS_CONVERTED not in value for value in api_literals),
                f"no literal containing {MSYS_CONVERTED!r}",
                api_literals,
                "docs/deploy/console-build.md §1: a bare '/' on a Git Bash line becomes "
                "C:/Program Files/Git/ -- a path on somebody's laptop, named by a page "
                "served on the internet. Observed in a real artefact on 2026-08-10.",
            )
            if plan["build_id"] is not None:
                result.record(
                    f"{label}_compiled_build_id_names_the_artefact",
                    str(plan["build_id"]) in compiled["build_ids"]
                    and "dev" not in compiled["build_ids"],
                    {"contains": plan["build_id"], "excludes": "dev"},
                    compiled["build_ids"],
                    "Ruling R5: an artefact that cannot name itself cannot be the artefact "
                    "a screenshot names.",
                )

            guard = run_guard(packer_path, dist, str(plan["declared_transport"]))
            result.record(
                f"{label}_guard_accepts_the_declared_transport",
                guard["exit_code"] == plan["guard_must"],
                plan["guard_must"],
                guard["exit_code"],
                f"build_lambda's packer, --mode preflight --console-transport "
                f"{plan['declared_transport']}. W4's gate, run over the dist this program "
                "is about to serve.",
            )
            falsification = None
            if plan["also_gate_as"] is not None:
                falsification = run_guard(packer_path, dist, str(plan["also_gate_as"]))
                result.record(
                    f"{label}_guard_REFUSES_the_wrong_declaration",
                    falsification["exit_code"] == 2,
                    2,
                    falsification["exit_code"],
                    "The falsification, in this direction: this dist starts "
                    f"{plan['declared_transport'].upper()}, so declaring "
                    f"{str(plan['also_gate_as']).upper()} must be REFUSED. A guard that "
                    "only ever accepted would be a guard nobody has run, and one that "
                    "refused in a single direction would be satisfied by testing for the "
                    "presence of one variable rather than for what selectSource starts.",
                )

            staged = stage_web_root(
                packer, dist, stage, EVIDENCE_BUNDLE if plan["stage_bundle"] else None
            )
            result.record(
                f"{label}_serve_tree_staged_without_refusal",
                staged["packer_refusals"] == [],
                [],
                staged["packer_refusals"],
                "strip_maps() and gzip_siblings() from the packer itself, so the emulator "
                "serves the tree the Lambda would serve.",
            )

            emulator = Emulator(
                Path(staged["web_root"]),
                workspace / f"furl-{label}.log",
                workspace / f"ready-{label}.txt",
            )
            run_record: dict[str, Any] = {
                "label": label,
                "build": built,
                "compiled_literals": compiled,
                "packaging_guard": {"declared": guard, "falsification": falsification},
                "served_tree": staged,
            }
            try:
                emulator.start()
                say(f"{label} emulator {emulator.base_url}")
                run_record["emulator"] = {
                    "base_url": emulator.base_url,
                    "web_root": str(emulator.web_root),
                    # BOTH halves, because an empty "removed" list is ambiguous on its
                    # own: it reads equally as "nothing was there" and as "nothing was
                    # done". `checked` is the closed set this program guarantees the
                    # child cannot see, and `removed` is which of them were actually
                    # present in this shell.
                    "env_names_checked": list(SCRUBBED_ENV),
                    "env_names_removed": emulator.scrubbed,
                    "env_names_absent_already": [
                        name for name in SCRUBBED_ENV if name not in emulator.scrubbed
                    ],
                    "banner": emulator.banner(),
                }

                probes = {
                    "root": probe(emulator.base_url, "GET", "/"),
                    "health": probe(emulator.base_url, "GET", "/v1/health"),
                    "gate_run": probe(emulator.base_url, "POST", "/v1/demo/gate-run", body=b"{}"),
                }
                run_record["http_probes"] = probes
                result.record(
                    f"{label}_the_console_shell_serves",
                    probes["root"]["status"] == 200,
                    200,
                    probes["root"]["status"],
                    "GET / through the same static_site module the Lambda uses.",
                )
                result.record(
                    f"{label}_every_response_is_marked_as_the_emulator",
                    all(row["emulator_header"] == "local_furl" for row in probes.values()),
                    "local_furl on all three",
                    {key: row["emulator_header"] for key, row in probes.items()},
                    "The marker that keeps this transcript from ever being mistaken for "
                    "one taken against the deployed URL.",
                )
                result.record(
                    f"{label}_the_gate_run_route_is_reachable_and_refuses_by_name",
                    probes["gate_run"]["status"] == 503
                    and (probes["gate_run"]["body_json"] or {}).get("error", {}).get("kind")
                    == "dsn_unset",
                    {"status": 503, "kind": "dsn_unset"},
                    {
                        "status": probes["gate_run"]["status"],
                        "kind": (probes["gate_run"]["body_json"] or {})
                        .get("error", {})
                        .get("kind"),
                    },
                    "A reachable route refusing for a NAMED reason. NOT a 404, and it must "
                    "never be described as one.",
                )

                driver_out = workspace / f"drive-{label}.json"
                options = [
                    "--expect",
                    "live" if label == "live" else "replay",
                    "--label",
                    label,
                    "--timeout",
                    str(args.timeout),
                    "--screenshot",
                    str(workspace / f"{label}.png"),
                ]
                if label == "live":
                    options += [
                        "--expect-build-id",
                        build_id,
                        "--expect-api-base",
                        str(args.api_base),
                        "--expect-status",
                        "503",
                        "--expect-kind",
                        "dsn_unset",
                    ]
                else:
                    options += ["--expect-bundle-url", "./bundle/"]
                if args.headed:
                    options.append("--headed")
                if args.chromium:
                    options += ["--chromium", str(args.chromium)]

                driven = drive(node, emulator.base_url, driver_out, options)
                run_record["browser"] = driven
                result.record(
                    f"{label}_chromium_run_passed_every_assertion",
                    driven["exit_code"] == 0,
                    0,
                    driven["exit_code"],
                    "A real chromium over the Playwright library API. Ruling R7: no "
                    "playwright.config.ts, and nothing under tests/browser/** is touched.",
                )
                if isinstance(driven["run"], dict):
                    failed = driven["run"].get("failed_assertions") or []
                    result.record(
                        f"{label}_browser_assertion_ledger_is_clean",
                        failed == [],
                        [],
                        failed,
                        "Every browser-side claim, by name. No advisory tier exists.",
                    )
            finally:
                emulator.stop()
                run_record.setdefault("emulator", {})["banner"] = emulator.banner()

            record["runs"].append(run_record)

    finally:
        record["steps"] = result.rows
        record["failed_steps"] = [row["step"] for row in result.failures]
        record["ok"] = result.ok
        record["workspace"] = {
            "path": str(workspace),
            "kept": bool(args.keep),
            "note": "Temporary. The dists built here are never uploaded and never replace "
            "verticals/mainline/apps/console/dist.",
            "screenshots": (
                "The PNGs named under runs[].browser.run.screenshot live in this "
                "workspace and are REMOVED with it unless --keep was passed, so a digest "
                "recorded here may name a file that no longer exists. That is deliberate "
                "and is why no assertion reads one: this worker owns four repository "
                "paths and an image is not among them. Re-run with --keep to inspect them."
            ),
        }
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(record, indent=2, sort_keys=False) + "\n", encoding="utf-8")
        licence = out_path.with_suffix(out_path.suffix + ".license")
        licence.write_text(
            "SPDX-FileCopyrightText: 2026 MAINLINE contributors\n"
            "SPDX-License-Identifier: CC-BY-4.0\n",
            encoding="utf-8",
        )
        say(f"wrote {out_path}")
        if not args.keep:
            shutil.rmtree(workspace, ignore_errors=True)
        else:
            say(f"kept {workspace}")

    if result.ok:
        say(f"PASSED {len(result.rows)} steps against the LOCAL EMULATOR (not the demo URL)")
        return EXIT_OK
    say(f"FAILED {len(result.failures)} of {len(result.rows)} steps")
    return EXIT_FAILED


if __name__ == "__main__":
    sys.exit(main())
