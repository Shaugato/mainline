#!/usr/bin/env python
# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The first thing that happens after ``terraform apply`` is a MEASUREMENT, not a hope.

WHY THIS FILE EXISTS
====================
An apply that returns exit 0 has told you that Terraform's API calls succeeded. It has not
told you that the Function URL answers, that its certificate verifies, that the demo's four
beats produce the four SQLSTATEs the console is built to render, that the alarms guarding
the founder's card can SEE the function they are pointed at, or that the kill switch —
lever L9 of ``docs/deploy/COST-BOUND.md``, the floor under every other cost control —
actually stops and actually restores.

Each of those is a *measurement*, and until one is taken the corresponding claim is a hope.
This program takes them, in that order, and refuses out loud when it cannot.

THE HARD PART: A VERIFIER THAT HAS NEVER FAILED HAS NEVER DISCRIMINATED
=======================================================================
``docs/leads/cloud-hardening-final.md`` ruling **R8**. As this file was written the stack
did not exist —

    aws lambda get-function --function-name mainline-demo-api --region ap-southeast-1
      -> ResourceNotFoundException: Function not found

— so it could not be proven by running it against a good stack. It is instead proven the
only honest way available: **every refusal branch below is demonstrated firing** in
``tests/deploy/test_post_apply_verify.py``, by feeding synthetic AWS answers and synthetic
HTTP answers into the seams named in :class:`Probes`, and each demonstration is paired with
a **mutant** of this file with that one check removed which does NOT refuse the same input.
A check that stops discriminating therefore turns its own control red. That is the pattern
``tests/ci/test_cluster_lane_report.py`` established and this file is held to it.

WHAT THE SEAMS ARE FOR, AND WHAT THEY ARE NOT FOR
-------------------------------------------------
:class:`Probes` bundles four collaborators — a Terraform reader, an HTTP client, an AWS
reader and a kill-switch driver. In production every one of them shells out or opens a
socket. In the controls every one of them is a synthetic that answers with a recorded or
constructed failure. The seams exist so that **failure is reachable in a test**; they are
not a mode, not a ``--simulate`` flag, and there is no code path in which this program
grades a synthetic answer and reports it as a live reading. What distinguishes the two is
:attr:`Check.source` — ``"live"`` when a socket was opened or a process was run,
``"synthetic"`` when a control supplied the answer — which every check carries and the
evidence file prints, so a reading taken under fault injection can never be cited as a
reading taken against a deployment.

WHAT IT NEVER DOES
==================
* **It never applies anything.** ``terraform output`` is the only Terraform verb it knows.
* **It never mutates a live stack unless asked in words.** ``--kill-switch dry`` (the
  default) drives ``--status`` and ``--dry-run`` only, and records the live half as
  **NOT satisfied, with the reason**. ``--kill-switch live`` is the only way to reserve
  concurrency on a real function, and it additionally requires ``--yes``.
* **It never relaxes ``treat_missing_data``.** Every alarm ships ``missing``, which is
  correct: ``INSUFFICIENT_DATA`` on a function nobody has called is the honest state, and
  the old ``notBreaching`` rendered that as ``OK``. This program's alarm-visibility check
  therefore does not ask the alarms to be ``OK``; it asks whether the metric behind each
  one has **datapoints inside the window in which this program itself made invocations**.
  An alarm over a metric with no datapoints cannot fire, and an alarm that cannot fire is
  not evidence no matter what colour the console paints it.
* **It never prints a credential**, and it masks every twelve-digit run as ``<account>``
  before anything reaches stdout or the evidence file.

EXIT CODES
==========
``0``  every check was satisfied.
``1``  at least one check could not be satisfied; the summary names each one and why.
``2``  usage error.

There is no third outcome and no defaulted return code. "Could not be attempted" is a
*kind* of not-satisfied, printed with its own reason, and it does not soften the exit.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import socket
import ssl
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

EXIT_OK = 0
EXIT_UNSATISFIED = 1
EXIT_USAGE = 2

#: Where the demo is deployed. The alarms and the function live here; Bedrock answers in
#: ``ap-southeast-2`` and the two being different is a fact about the accounts.
DEFAULT_REGION = "ap-southeast-1"
DEFAULT_PROFILE = "mainline-dev"
DEFAULT_FUNCTION = "mainline-demo-api"
DEFAULT_ALARM_PREFIX = "mainline-demo-api"

#: ``infra/envs/demo`` — the only Terraform root this program reads, and it reads it with
#: ``output`` and nothing else.
DEFAULT_TF_DIR = "infra/envs/demo"

#: The Terraform output that carries the Function URL. Never a hostname written here: a
#: hardcoded host is a verifier that passes against last week's deployment.
FUNCTION_URL_OUTPUT = "api_function_url"

#: The four beats, in order, with the SQLSTATE each must produce. Taken from
#: ``scripts/deploy/demo_acceptance.py``'s ``EXPECTED_BEATS``, which is itself checked
#: against ``verticals/mainline/apps/demo-api/contracts/gate-run.schema.json`` — the
#: committed schema is authoritative for what the demo must carry, and this table is
#: derived from it rather than invented here.
EXPECTED_BEATS: tuple[dict[str, Any], ...] = (
    {"ordinal": 1, "name": "read", "outcome": "read", "sqlstate": "00000", "constraint": None},
    {
        "ordinal": 2,
        "name": "merge",
        "outcome": "refused",
        "sqlstate": "23514",
        "constraint": "gate_closed_when_issued",
    },
    {
        "ordinal": 3,
        "name": "projection_drift_attack",
        "outcome": "refused",
        "sqlstate": "P0001",
        "constraint": "mainline.fn_permit_merge_gate",
    },
    {"ordinal": 4, "name": "admit", "outcome": "admitted", "sqlstate": "00000", "constraint": None},
)

#: ``sha256`` rendered by ``encode(clearance_digest, 'hex')`` — 64 lowercase hex characters.
#: Shape alone is not provenance, which is why :func:`check_clearance_digest` also refuses a
#: digest this program could have supplied. See that function.
_HEX64 = re.compile(r"^[0-9a-f]{64}$")

#: Any bare twelve-digit run. Masked before anything is printed or written.
_TWELVE_DIGITS = re.compile(r"\b\d{12}\b")

#: ``kill_switch.sh``'s own partial mask — first four digits, ``REDACTED``, last four. That
#: form is right for a terminal an operator is looking at and wrong for a **tracked** file:
#: eight of twelve digits published forever is a narrower search than twelve, not a private
#: one. Ruling **R9** says ``<account>`` in everything tracked, so this program collapses the
#: partial mask rather than passing it through because it "looks masked already".
_PARTIAL_MASK = re.compile(r"\b\d{4}REDACTED\d{4}\b")

#: ANSI SGR and the box-drawing Terraform decorates its errors with. Stripped from every
#: captured subprocess stream before it reaches a message. This is not cosmetic: an escape
#: sequence pasted into a JSON evidence file makes the one sentence that says WHY a check
#: failed unreadable, and ``docs/leads/cloud-hardening-final.md`` records a lane whose
#: single failing assertion had to be grepped out of a wall of unrelated log. A diagnosis
#: nobody can read is a diagnosis nobody reads.
_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def plain(text: str) -> str:
    """Strip ANSI escapes and Terraform's gutter glyphs, and collapse the blank lines."""
    stripped = _ANSI.sub("", text or "")
    lines = [line.lstrip("│╰╷╵ \t").rstrip() for line in stripped.splitlines()]
    return "\n".join(line for line in lines if line)


#: The alarms whose metric this program can actually cause a datapoint in by calling the
#: Function URL. ``Invocations`` and ``Duration`` are published per invocation;
#: ``Errors``/``Throttles`` publish only when one occurs, and ``IncomingBytes`` lags by the
#: log-delivery interval. The check below therefore *requires* visibility for the first
#: family and *reports without requiring* it for the second — because demanding an Errors
#: datapoint would demand that the demo error, and a verifier that can only pass on a
#: broken system is worse than no verifier.
METRICS_THIS_PROGRAM_CAN_MOVE = ("Invocations", "Duration", "ConcurrentExecutions")


# ═════════════════════════════════════════════════════════════════════════════════════
# the repository, and the masker
# ═════════════════════════════════════════════════════════════════════════════════════


def repo_root() -> Path:
    here = Path(__file__).resolve().parent
    for candidate in (here, *here.parents):
        if (candidate / "verticals").is_dir() and (candidate / "packages").is_dir():
            return candidate
    return Path.cwd().resolve()


def mask(text: str) -> str:
    """Replace every twelve-digit run with ``<account>``.

    Blunt on purpose. The account id most often leaks inside an ARN in an error message —
    ``is not authorized to perform`` — which is exactly the message a failing verifier
    records. A masker that only knew the account it had already read would miss the one in
    the message it could not read.
    """
    return _PARTIAL_MASK.sub("<account>", _TWELVE_DIGITS.sub("<account>", text))


def say(*parts: object) -> None:
    print(*[mask(str(p)) for p in parts])


# ═════════════════════════════════════════════════════════════════════════════════════
# what a check produces
# ═════════════════════════════════════════════════════════════════════════════════════


@dataclass
class Check:
    """One thing this program promised to measure, and whether it managed to.

    ``satisfied`` is a plain bool. There is no ``"skipped"``, no ``"n/a"`` and no third
    truthy value: a check that could not be attempted is **not satisfied**, and ``why``
    says it could not be attempted. A vocabulary with a soft middle is a vocabulary in
    which an unapplied stack eventually reads as a pass.
    """

    id: str
    title: str
    satisfied: bool
    why: str
    detail: dict[str, Any] = field(default_factory=dict)
    source: str = "live"

    def as_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "satisfied": self.satisfied,
            "why": mask(self.why),
            "source": self.source,
            "detail": json.loads(mask(json.dumps(self.detail, default=str))),
        }


class Unavailable(Exception):
    """A collaborator could not answer. Carries the sentence the check will print."""


# ═════════════════════════════════════════════════════════════════════════════════════
# the collaborators — the seams the controls inject into
# ═════════════════════════════════════════════════════════════════════════════════════


@dataclass
class HttpAnswer:
    status: int
    headers: dict[str, str]
    body: bytes
    elapsed_ms: float

    def json(self) -> Any:
        return json.loads(self.body.decode("utf-8"))


@dataclass
class Ran:
    """The result of running a subprocess: what it exited with and what it said."""

    returncode: int
    stdout: str
    stderr: str


class TerraformReader:
    """``terraform -chdir=<dir> output -json``. The only Terraform verb this program knows.

    ``output`` reads state and changes nothing. There is deliberately no code path here
    that can reach ``apply``, ``destroy``, ``import`` or ``taint``: the argument list is
    constructed literally, never assembled from user input.
    """

    def __init__(self, directory: Path, *, timeout: float = 120.0) -> None:
        self.directory = directory
        self.timeout = timeout

    def outputs(self) -> dict[str, Any]:
        binary = shutil.which("terraform")
        if binary is None:
            raise Unavailable(
                "terraform is not on PATH, so the Function URL cannot be resolved from "
                "state. This program will not accept a URL from anywhere else: a "
                "hardcoded host verifies last week's deployment."
            )
        if not self.directory.is_dir():
            raise Unavailable(f"{self.directory} is not a directory, so there is no state to read.")
        try:
            done = subprocess.run(
                [binary, f"-chdir={self.directory}", "output", "-json"],
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise Unavailable(f"terraform output could not be run: {exc}") from exc
        if done.returncode != 0:
            raise Unavailable(
                "terraform output exited "
                f"{done.returncode}: {plain(done.stderr or done.stdout)[:400]}"
            )
        try:
            parsed = json.loads(done.stdout or "{}")
        except ValueError as exc:
            raise Unavailable(f"terraform output did not emit JSON: {exc}") from exc
        if not isinstance(parsed, dict):
            raise Unavailable("terraform output emitted JSON that is not an object.")
        return parsed


class HttpClient:
    """HTTPS only, certificate verification ON, and the TLS facts recorded rather than assumed.

    There is no ``verify=False``, no ``ssl._create_unverified_context`` and no way to reach
    one from the command line. A demo URL whose certificate does not verify is a finding,
    and a client that could be talked out of checking would convert that finding into a
    silence.
    """

    def __init__(self, *, timeout: float = 30.0) -> None:
        self.timeout = timeout
        self._context = ssl.create_default_context()

    def tls(self, url: str) -> dict[str, Any]:
        split = urllib.parse.urlsplit(url)
        if split.scheme != "https":
            raise Unavailable(
                f"the URL's scheme is {split.scheme!r}, not 'https'. A demo URL that is not "
                "HTTPS has no certificate to verify and no confidentiality to offer."
            )
        host = split.hostname
        if not host:
            raise Unavailable(f"no hostname could be parsed out of {url!r}.")
        port = split.port or 443
        try:
            with (
                socket.create_connection((host, port), timeout=self.timeout) as raw,
                self._context.wrap_socket(raw, server_hostname=host) as tls,
            ):
                cert = tls.getpeercert() or {}
                return {
                    "verified": True,
                    "host": host,
                    "port": port,
                    "protocol": tls.version(),
                    "cipher": (tls.cipher() or (None,))[0],
                    "subject": _flatten_name(cert.get("subject", ())),
                    "issuer": _flatten_name(cert.get("issuer", ())),
                    "not_after": cert.get("notAfter"),
                }
        except ssl.SSLError as exc:
            raise Unavailable(f"TLS verification FAILED for {host}: {exc}") from exc
        except OSError as exc:
            raise Unavailable(f"{host}:{port} could not be reached: {exc}") from exc

    def request(
        self, method: str, url: str, *, body: bytes | None = None, headers: dict[str, str] | None
    ) -> HttpAnswer:
        request = urllib.request.Request(url, data=body, method=method)  # noqa: S310 - https enforced
        if urllib.parse.urlsplit(url).scheme != "https":
            raise Unavailable(f"refusing to issue {method} over a non-HTTPS URL: {url}")
        for key, value in (headers or {}).items():
            request.add_header(key, value)
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(  # noqa: S310 - https enforced above
                request, timeout=self.timeout, context=self._context
            ) as answer:
                payload = answer.read()
                return HttpAnswer(
                    status=answer.status,
                    headers={k.lower(): v for k, v in answer.headers.items()},
                    body=payload,
                    elapsed_ms=(time.perf_counter() - started) * 1000.0,
                )
        except urllib.error.HTTPError as exc:
            payload = exc.read()
            return HttpAnswer(
                status=exc.code,
                headers={k.lower(): v for k, v in (exc.headers or {}).items()},
                body=payload,
                elapsed_ms=(time.perf_counter() - started) * 1000.0,
            )
        except (OSError, ssl.SSLError) as exc:
            raise Unavailable(f"{method} {url} failed: {exc}") from exc


def _flatten_name(name: Any) -> str:
    try:
        return ", ".join(f"{k}={v}" for rdn in name for k, v in rdn)
    except (TypeError, ValueError):
        return ""


class AwsReader:
    """Read-only AWS through the CLI. Every argument list is literal; none is assembled.

    The CLI rather than boto3 so that this module imports on a machine without boto3 —
    which matters because the controls import it, and a control set that cannot load its
    subject is a control set that skips.
    """

    def __init__(self, *, profile: str, region: str, timeout: float = 120.0) -> None:
        self.profile = profile
        self.region = region
        self.timeout = timeout

    def _run(self, *args: str) -> Ran:
        binary = shutil.which("aws")
        if binary is None:
            raise Unavailable("the AWS CLI is not on PATH, so nothing about AWS can be read.")
        argv = [
            binary,
            *args,
            "--profile",
            self.profile,
            "--region",
            self.region,
            "--output",
            "json",
        ]
        try:
            done = subprocess.run(
                argv, capture_output=True, text=True, timeout=self.timeout, check=False
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise Unavailable(f"aws {' '.join(args[:2])} could not be run: {exc}") from exc
        return Ran(done.returncode, done.stdout, done.stderr)

    def _json(self, *args: str) -> Any:
        done = self._run(*args)
        if done.returncode != 0:
            raise Unavailable(
                f"aws {' '.join(args[:2])} exited {done.returncode}: "
                f"{plain(done.stderr or done.stdout)[:400]}"
            )
        try:
            return json.loads(done.stdout or "null")
        except ValueError as exc:
            raise Unavailable(f"aws {' '.join(args[:2])} did not emit JSON: {exc}") from exc

    def get_function(self, name: str) -> dict[str, Any]:
        return self._json("lambda", "get-function", "--function-name", name)

    def describe_alarms(self, prefix: str) -> list[dict[str, Any]]:
        answer = self._json("cloudwatch", "describe-alarms", "--alarm-name-prefix", prefix)
        return list((answer or {}).get("MetricAlarms", []))

    def metric_statistics(
        self, namespace: str, metric: str, dimensions: list[dict[str, str]], start: str, end: str
    ) -> list[dict[str, Any]]:
        args = [
            "cloudwatch",
            "get-metric-statistics",
            "--namespace",
            namespace,
            "--metric-name",
            metric,
            "--start-time",
            start,
            "--end-time",
            end,
            "--period",
            "60",
            "--statistics",
            "Sum",
            "SampleCount",
        ]
        if dimensions:
            args.append("--dimensions")
            args.extend(f"Name={d['Name']},Value={d['Value']}" for d in dimensions)
        answer = self._json(*args)
        return list((answer or {}).get("Datapoints", []))


class KillSwitchDriver:
    """Drives the committed kill switch — never a reimplementation of it.

    Reimplementing the stop here would give the demo two kill switches that could disagree,
    and the one that gets exercised in an incident is the one in the runbook. So this drives
    that file, and the ``--dry-run`` path is what runs unless a human types ``live``.

    TWO SPELLINGS OF ONE LEVER, AND WHY BOTH ARE TRIED
    --------------------------------------------------
    ``kill_switch.sh`` and ``kill_switch.ps1`` are the same lever with the same modes and the
    same exit codes. This driver prefers ``bash``, because the shell script is the one the
    runbook quotes, and falls back to ``pwsh``/``powershell`` with the ``.ps1``. Refusing on a
    Windows box that has PowerShell and no Git Bash would report *"the kill switch cannot be
    driven"* about a machine on which it plainly can be — a false negative about the one
    control the founder's card depends on.
    """

    #: ``(executable, script suffix, how to spell each flag)``. Tried in order.
    _SPELLINGS: tuple[tuple[tuple[str, ...], str, bool], ...] = (
        (("bash",), ".sh", False),
        (("pwsh", "powershell"), ".ps1", True),
    )

    def __init__(self, script: Path, *, function: str, timeout: float = 180.0) -> None:
        self.script = script
        self.function = function
        self.timeout = timeout

    def _resolve(self) -> tuple[str, Path, bool]:
        tried: list[str] = []
        for names, suffix, powershell in self._SPELLINGS:
            script = self.script.with_suffix(suffix)
            for name in names:
                binary = shutil.which(name)
                tried.append(name)
                if binary is not None and script.is_file():
                    return binary, script, powershell
        raise Unavailable(
            "no interpreter for the kill switch is on PATH (tried "
            f"{', '.join(tried)}), or neither {self.script.with_suffix('.sh').name} nor "
            f"{self.script.with_suffix('.ps1').name} exists. The kill switch was NOT driven "
            "and its two checks are unsatisfied; that is a refusal, not a pass."
        )

    def _run(self, *flags: str) -> Ran:
        binary, script, powershell = self._resolve()
        env = dict(os.environ, MAINLINE_FUNCTION_NAME=self.function, NO_COLOR="1")
        if powershell:
            # `--stop` becomes `-Stop`, `--expect-account <id>` becomes `-ExpectAccount <id>`.
            argv = [binary, "-NoProfile", "-File", str(script), *_powershell_flags(flags)]
        else:
            argv = [binary, str(script), *flags]
        try:
            done = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
                env=env,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise Unavailable(f"{script.name} {' '.join(flags)} could not be run: {exc}") from exc
        return Ran(done.returncode, done.stdout, done.stderr)

    def status(self) -> Ran:
        return self._run("--status")

    def dry_run(self) -> Ran:
        return self._run("--dry-run")

    def stop(self, *, expect_account: str | None) -> Ran:
        flags = ["--stop", "--yes"]
        flags.extend(["--expect-account", expect_account] if expect_account else ["--any-account"])
        return self._run(*flags)

    def restore(self, *, expect_account: str | None) -> Ran:
        flags = ["--restore", "--yes"]
        flags.extend(["--expect-account", expect_account] if expect_account else ["--any-account"])
        return self._run(*flags)


def _powershell_flags(flags: tuple[str, ...] | list[str]) -> list[str]:
    """``--expect-account 1234`` -> ``-ExpectAccount 1234``. A value is passed through as-is."""
    out: list[str] = []
    for flag in flags:
        if not flag.startswith("--"):
            out.append(flag)
            continue
        out.append("-" + "".join(part.capitalize() for part in flag[2:].split("-")))
    return out


@dataclass
class Probes:
    """The four collaborators, bundled so a control can replace any subset of them."""

    terraform: Any
    http: Any
    aws: Any
    kill_switch: Any
    source: str = "live"


# ═════════════════════════════════════════════════════════════════════════════════════
# the checks
# ═════════════════════════════════════════════════════════════════════════════════════


def check_function_url(probes: Probes) -> tuple[Check, str | None]:
    """C1 — resolve the Function URL from Terraform state. Never from a literal.

    Refuses when: terraform is absent or errors; the output is missing; the output is null
    (which is what ``infra/envs/demo/outputs.tf`` emits when ``enable_api = false``); or
    the value is not an HTTPS URL.
    """
    detail: dict[str, Any] = {"output_name": FUNCTION_URL_OUTPUT}
    try:
        outputs = probes.terraform.outputs()
    except Unavailable as exc:
        return Check(
            "function_url",
            "Function URL resolved from terraform output",
            False,
            str(exc),
            detail,
            probes.source,
        ), None
    detail["outputs_present"] = sorted(outputs)
    if FUNCTION_URL_OUTPUT not in outputs:
        return (
            Check(
                "function_url",
                "Function URL resolved from terraform output",
                False,
                f"terraform state carries no output named {FUNCTION_URL_OUTPUT!r}. An empty "
                "state and an applied stack are not the same thing, and this program will "
                "not guess a host to tell them apart.",
                detail,
                probes.source,
            ),
            None,
        )
    raw = outputs[FUNCTION_URL_OUTPUT]
    value = raw.get("value") if isinstance(raw, dict) else raw
    if not value:
        return (
            Check(
                "function_url",
                "Function URL resolved from terraform output",
                False,
                f"{FUNCTION_URL_OUTPUT} is null. outputs.tf emits null when enable_api is "
                "false, so this is an unapplied or disabled API, not a URL to probe.",
                detail,
                probes.source,
            ),
            None,
        )
    url = str(value)
    if not url.startswith("https://"):
        return (
            Check(
                "function_url",
                "Function URL resolved from terraform output",
                False,
                f"{FUNCTION_URL_OUTPUT} is not an HTTPS URL. A demo URL served over plain "
                "HTTP cannot be verified and must not be published.",
                {**detail, "scheme": urllib.parse.urlsplit(url).scheme},
                probes.source,
            ),
            None,
        )
    detail["host"] = urllib.parse.urlsplit(url).hostname
    return (
        Check(
            "function_url",
            "Function URL resolved from terraform output",
            True,
            "the URL came out of state, not out of this file.",
            detail,
            probes.source,
        ),
        url.rstrip("/") + "/",
    )


def check_tls(probes: Probes, base: str | None) -> Check:
    """C2 — HTTPS reached with the certificate VERIFIED, and the facts recorded.

    Records what verified rather than asserting that something did.
    """
    if base is None:
        return Check(
            "tls",
            "HTTPS reached and the certificate verifies",
            False,
            "no Function URL was resolved, so no certificate could be verified.",
            {},
            probes.source,
        )
    try:
        facts = probes.http.tls(base)
    except Unavailable as exc:
        return Check(
            "tls", "HTTPS reached and the certificate verifies", False, str(exc), {}, probes.source
        )
    if not facts.get("verified"):
        return Check(
            "tls",
            "HTTPS reached and the certificate verifies",
            False,
            "the handshake completed without the certificate being verified. A verifier "
            "that accepts an unverified certificate is measuring reachability and calling "
            "it security.",
            facts,
            probes.source,
        )
    protocol = str(facts.get("protocol") or "")
    if protocol in {"TLSv1", "TLSv1.1", "SSLv3", "SSLv2"}:
        return Check(
            "tls",
            "HTTPS reached and the certificate verifies",
            False,
            f"the connection negotiated {protocol}, which is deprecated. AWS serves the "
            "Function URL over TLS 1.2 or better; anything less means something is between "
            "this program and the origin.",
            facts,
            probes.source,
        )
    return Check(
        "tls",
        "HTTPS reached and the certificate verifies",
        True,
        f"{protocol} to {facts.get('host')}, certificate issued by {facts.get('issuer')}.",
        facts,
        probes.source,
    )


def check_health(probes: Probes, base: str | None) -> Check:
    """C3 — ``GET /v1/health`` answers 200 and says it reached the database."""
    if base is None:
        return Check(
            "health",
            "GET /v1/health answers 200",
            False,
            "no Function URL was resolved.",
            {},
            probes.source,
        )
    url = urllib.parse.urljoin(base, "v1/health")
    try:
        answer = probes.http.request("GET", url, headers={"accept": "application/json"})
    except Unavailable as exc:
        return Check("health", "GET /v1/health answers 200", False, str(exc), {}, probes.source)
    detail: dict[str, Any] = {"status": answer.status, "elapsed_ms": round(answer.elapsed_ms, 1)}
    if answer.status != 200:
        return Check(
            "health",
            "GET /v1/health answers 200",
            False,
            f"/v1/health answered {answer.status}. The health beat is the cheapest database "
            "beat there is; if it does not answer, nothing measured after it means anything.",
            {**detail, "body_head": answer.body[:400].decode("utf-8", "replace")},
            probes.source,
        )
    try:
        document = answer.json()
    except (ValueError, UnicodeDecodeError) as exc:
        return Check(
            "health",
            "GET /v1/health answers 200",
            False,
            f"/v1/health answered 200 with a body that is not JSON: {exc}",
            detail,
            probes.source,
        )
    detail["body"] = document
    if not isinstance(document, dict) or document.get("ok") is not True:
        return Check(
            "health",
            "GET /v1/health answers 200",
            False,
            "/v1/health answered 200 but its body does not carry ok=true. A 200 whose body "
            "reports a problem is a 200 that a load balancer believes and a judge does not.",
            detail,
            probes.source,
        )
    return Check(
        "health",
        "GET /v1/health answers 200",
        True,
        f"200 in {detail['elapsed_ms']} ms, body carries ok=true.",
        detail,
        probes.source,
    )


# One return per refusal, and the refusals ARE the check. Collapsing them into a single exit
# with an accumulated reason would turn the sentence a reader gets at 3 a.m. into a
# concatenation rather than the one thing that actually went wrong.
def check_beats(  # noqa: PLR0911
    probes: Probes, base: str | None
) -> tuple[Check, dict[str, Any] | None]:
    """C4 — drive the demo and assert each beat's SQLSTATE: 00000 -> 23514 -> P0001 -> 00000.

    The SQLSTATEs are the demo's whole argument. Beat 2 is refused by a plain CHECK
    (``gate_closed_when_issued``, ``23514``); beat 3 forges the counter to zero and is
    refused **anyway** because the gate re-derives it (``P0001``); beat 4 signs one
    disposition and the same merge succeeds (``00000``). A run that produced three of the
    four would still render as a demo and would be arguing something else.
    """
    if base is None:
        return (
            Check(
                "beats",
                "The four beats produce 00000 / 23514 / P0001 / 00000",
                False,
                "no Function URL was resolved.",
                {},
                probes.source,
            ),
            None,
        )
    url = urllib.parse.urljoin(base, "v1/demo/gate-run")
    try:
        answer = probes.http.request(
            "POST", url, body=b"{}", headers={"content-type": "application/json"}
        )
    except Unavailable as exc:
        return (
            Check(
                "beats",
                "The four beats produce 00000 / 23514 / P0001 / 00000",
                False,
                str(exc),
                {},
                probes.source,
            ),
            None,
        )
    detail: dict[str, Any] = {"status": answer.status, "elapsed_ms": round(answer.elapsed_ms, 1)}
    if answer.status != 200:
        return (
            Check(
                "beats",
                "The four beats produce 00000 / 23514 / P0001 / 00000",
                False,
                f"POST /v1/demo/gate-run answered {answer.status}.",
                {**detail, "body_head": answer.body[:400].decode("utf-8", "replace")},
                probes.source,
            ),
            None,
        )
    try:
        document = answer.json()
    except (ValueError, UnicodeDecodeError) as exc:
        return (
            Check(
                "beats",
                "The four beats produce 00000 / 23514 / P0001 / 00000",
                False,
                f"the gate run answered 200 with a body that is not JSON: {exc}",
                detail,
                probes.source,
            ),
            None,
        )
    payload = document.get("data", document) if isinstance(document, dict) else {}
    beats = payload.get("beats") if isinstance(payload, dict) else None
    if not isinstance(beats, list):
        return (
            Check(
                "beats",
                "The four beats produce 00000 / 23514 / P0001 / 00000",
                False,
                "the gate-run payload carries no `beats` array.",
                detail,
                probes.source,
            ),
            None,
        )
    detail["verdict"] = payload.get("verdict")
    detail["beats"] = [
        {
            "ordinal": b.get("ordinal"),
            "name": b.get("name"),
            "outcome": b.get("outcome"),
            "sqlstate": b.get("sqlstate"),
            "constraint": b.get("constraint"),
        }
        for b in beats
        if isinstance(b, dict)
    ]
    failures: list[str] = []
    if len(beats) != len(EXPECTED_BEATS):
        failures.append(
            f"the payload carries {len(beats)} beats; the contract names {len(EXPECTED_BEATS)}"
        )
    by_name = {b.get("name"): b for b in beats if isinstance(b, dict)}
    for expected in EXPECTED_BEATS:
        found = by_name.get(expected["name"])
        if found is None:
            failures.append(f"beat {expected['ordinal']} ({expected['name']}) is absent")
            continue
        if found.get("sqlstate") != expected["sqlstate"]:
            failures.append(
                f"beat {expected['ordinal']} ({expected['name']}): sqlstate is "
                f"{found.get('sqlstate')!r}, the contract requires {expected['sqlstate']!r}"
            )
        if found.get("outcome") != expected["outcome"]:
            failures.append(
                f"beat {expected['ordinal']} ({expected['name']}): outcome is "
                f"{found.get('outcome')!r}, the contract requires {expected['outcome']!r}"
            )
        if expected["constraint"] is not None and found.get("constraint") != expected["constraint"]:
            failures.append(
                f"beat {expected['ordinal']} ({expected['name']}): constraint is "
                f"{found.get('constraint')!r}, the contract requires {expected['constraint']!r}"
            )
    detail["failures"] = failures
    if failures:
        return (
            Check(
                "beats",
                "The four beats produce 00000 / 23514 / P0001 / 00000",
                False,
                "the beats do not carry the SQLSTATEs the contract names: " + "; ".join(failures),
                detail,
                probes.source,
            ),
            payload,
        )
    observed = " -> ".join(str(b.get("sqlstate")) for b in beats)
    return (
        Check(
            "beats",
            "The four beats produce 00000 / 23514 / P0001 / 00000",
            True,
            f"observed {observed}, each with the outcome and constraint the contract names.",
            detail,
            probes.source,
        ),
        payload,
    )


def check_clearance_digest(probes: Probes, payload: dict[str, Any] | None) -> Check:
    """C5 — the admission beat carries a digest the SERVER computed, not one this program sent.

    ``gate_run.py`` reads it back as ``encode(m.clearance_digest, 'hex')`` from
    ``mainline.merge_record`` after the signature lands. Its provenance matters more than
    its presence: an ADMITTED with no exhibit is an assertion, and an ADMITTED echoing a
    digest the caller supplied is worse than no exhibit at all. This program sends a body
    of exactly ``{}`` — it supplies no digest and no seed — so any 64-hex digest that comes
    back was computed server-side over rows this program never named. The check asserts
    that emptiness too, because it is the premise the provenance rests on.
    """
    if payload is None:
        return Check(
            "clearance_digest",
            "The admission beat carries a server-computed clearance_digest",
            False,
            "no gate-run payload was obtained, so there is no admission beat to read.",
            {},
            probes.source,
        )
    beats = payload.get("beats") or []
    admit = next(
        (b for b in beats if isinstance(b, dict) and b.get("name") == "admit"),
        None,
    )
    if admit is None:
        return Check(
            "clearance_digest",
            "The admission beat carries a server-computed clearance_digest",
            False,
            "the payload carries no beat named 'admit'.",
            {},
            probes.source,
        )
    record = (admit.get("observed") or {}).get("merge_record") or {}
    digest = record.get("clearance_digest")
    detail = {"request_body_sent": "{}", "clearance_digest_present": bool(digest)}
    if not digest:
        return Check(
            "clearance_digest",
            "The admission beat carries a server-computed clearance_digest",
            False,
            "the admission beat carries no clearance_digest. An ADMITTED with no "
            "server-computed exhibit is an assertion, not evidence.",
            detail,
            probes.source,
        )
    if not _HEX64.match(str(digest)):
        return Check(
            "clearance_digest",
            "The admission beat carries a server-computed clearance_digest",
            False,
            f"the clearance_digest is not 64 lowercase hex characters: {str(digest)[:32]!r}... "
            "The column is a sha256 rendered by encode(..., 'hex'); anything else did not "
            "come from that column.",
            detail,
            probes.source,
        )
    return Check(
        "clearance_digest",
        "The admission beat carries a server-computed clearance_digest",
        True,
        f"64-hex digest {str(digest)[:12]}… returned against a request body of {{}} — "
        "computed over rows this program never named.",
        {**detail, "clearance_digest_prefix": str(digest)[:12]},
        probes.source,
    )


def check_alarm_inventory(
    probes: Probes, prefix: str, expected: list[str] | None, underivable: str | None
) -> tuple[Check, list[dict[str, Any]]]:
    """C6 — every alarm the MODULES declare exists in the account. The set is derived.

    ``expected`` arrives derived from ``infra/modules/**`` and cross-checked against the
    committed plan (see ``scripts/deploy/aws_live_probe.py``). It is not a literal here,
    and there is no fallback to one: the defect this replaces was a hard-coded four
    checked against a deployment that creates seven, of which the three unseen were the
    guard's — the ones wired to the stop.
    """
    if expected is None:
        return (
            Check(
                "alarm_inventory",
                "Every alarm the modules declare exists",
                False,
                underivable or "the expected alarm set could not be derived from the tree.",
                {},
                probes.source,
            ),
            [],
        )
    detail: dict[str, Any] = {"expected": expected, "expected_count": len(expected)}
    try:
        alarms = probes.aws.describe_alarms(prefix)
    except Unavailable as exc:
        return (
            Check(
                "alarm_inventory",
                "Every alarm the modules declare exists",
                False,
                str(exc),
                detail,
                probes.source,
            ),
            [],
        )
    found = {str(a.get("AlarmName")): a for a in alarms}
    detail["found"] = sorted(found)
    detail["found_count"] = len(found)
    missing = [name for name in expected if name not in found]
    detail["missing"] = missing
    if missing:
        return (
            Check(
                "alarm_inventory",
                "Every alarm the modules declare exists",
                False,
                f"{len(missing)} of {len(expected)} declared alarms do not exist: "
                f"{', '.join(missing)}. An empty or short table is not a green one.",
                detail,
                probes.source,
            ),
            alarms,
        )
    treat = sorted({str(a.get("TreatMissingData")) for a in alarms})
    detail["treat_missing_data"] = treat
    if treat != ["missing"]:
        return (
            Check(
                "alarm_inventory",
                "Every alarm the modules declare exists",
                False,
                f"at least one alarm does not carry treat_missing_data='missing' (saw "
                f"{', '.join(treat)}). 'missing' is correct and is what makes "
                "INSUFFICIENT_DATA legible; a relaxed setting renders a metric nobody "
                "published as OK.",
                detail,
                probes.source,
            ),
            alarms,
        )
    return (
        Check(
            "alarm_inventory",
            "Every alarm the modules declare exists",
            True,
            f"all {len(expected)} declared alarms exist, each with treat_missing_data='missing'.",
            detail,
            probes.source,
        ),
        alarms,
    )


def check_alarm_visibility(
    probes: Probes, alarms: list[dict[str, Any]], window_start: datetime, window_end: datetime
) -> Check:
    """C7 — the alarms can SEE the invocations this program just made.

    An alarm on a metric with no datapoints is not evidence. Every alarm here ships
    ``treat_missing_data = "missing"``, which is **correct and must not be relaxed** — it
    is what makes ``INSUFFICIENT_DATA`` mean "nothing was published" instead of rendering
    as ``OK``. So the question this check asks is not "is the alarm green"; it is *"did the
    metric behind this alarm receive a datapoint in the window in which this program itself
    called the function"*.

    Only the metrics an invocation actually publishes are required: ``Invocations``,
    ``Duration``, ``ConcurrentExecutions``. ``Errors`` and ``Throttles`` publish only when
    one happens and ``IncomingBytes`` lags log delivery, so those are reported and not
    demanded — requiring them would require the demo to be broken before it could pass.
    """
    if not alarms:
        return Check(
            "alarm_visibility",
            "The alarms can see the invocations this program just made",
            False,
            "no alarm was read, so no metric could be asked whether it saw anything. An "
            "empty alarm table is the reason, and it is not a reassuring one.",
            {},
            probes.source,
        )
    start = window_start.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    end = window_end.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    detail: dict[str, Any] = {"window_start": start, "window_end": end, "metrics": []}
    blind: list[str] = []
    for alarm in sorted(alarms, key=lambda a: str(a.get("AlarmName"))):
        name = str(alarm.get("AlarmName"))
        metric = str(alarm.get("MetricName") or "")
        namespace = str(alarm.get("Namespace") or "")
        dimensions = [
            {"Name": str(d.get("Name")), "Value": str(d.get("Value"))}
            for d in (alarm.get("Dimensions") or [])
        ]
        required = metric in METRICS_THIS_PROGRAM_CAN_MOVE
        row: dict[str, Any] = {
            "alarm_name": name,
            "metric_name": metric,
            "namespace": namespace,
            "dimensions": dimensions,
            "state": alarm.get("StateValue"),
            "treat_missing_data": alarm.get("TreatMissingData"),
            "datapoints_required": required,
        }
        try:
            points = probes.aws.metric_statistics(namespace, metric, dimensions, start, end)
        except Unavailable as exc:
            row["error"] = str(exc)
            row["datapoints"] = None
            detail["metrics"].append(row)
            if required:
                blind.append(f"{name}: the metric behind it could not be read ({exc})")
            continue
        row["datapoints"] = len(points)
        row["sum"] = sum(float(p.get("Sum") or 0.0) for p in points)
        detail["metrics"].append(row)
        if required and not points:
            blind.append(
                f"{name}: {namespace}/{metric} has NO datapoints between {start} and {end}, "
                "a window in which this program invoked the function. Under "
                "treat_missing_data='missing' this alarm is INSUFFICIENT_DATA and cannot "
                "fire — it is pointed at a metric it cannot see."
            )
    detail["blind"] = blind
    if blind:
        return Check(
            "alarm_visibility",
            "The alarms can see the invocations this program just made",
            False,
            "an alarm on a metric with no datapoints is not evidence: " + " | ".join(blind),
            detail,
            probes.source,
        )
    watched = [m["alarm_name"] for m in detail["metrics"] if m["datapoints_required"]]
    return Check(
        "alarm_visibility",
        "The alarms can see the invocations this program just made",
        True,
        f"{len(watched)} alarm(s) over metrics this program can move have datapoints inside "
        f"the window {start}..{end}; treat_missing_data stays 'missing' throughout.",
        detail,
        probes.source,
    )


def check_kill_switch(
    probes: Probes, base: str | None, mode: str, *, expect_account: str | None
) -> list[Check]:
    """C8/C9 — the kill switch stops the demo and puts it back, proven end to end.

    ``mode == "live"`` is the only path that mutates anything, and it is the only path that
    can satisfy these two checks. Under ``dry`` this program drives ``--status`` and
    ``--dry-run`` — read-only, and against an unapplied stack ``--status`` exits 4 — then
    records both checks as **NOT satisfied with the reason**, because a stop nobody
    performed is a stop nobody has evidence for. ``dry`` is honest, not green.
    """
    stop_id = "kill_switch_stop"
    restore_id = "kill_switch_restore"
    stop_title = "kill switch --stop produces HTTP 429 with no body"
    restore_title = "kill switch --restore returns the service"

    if mode == "skip":
        why = (
            "--kill-switch skip was passed. Skipping is not a result: these two checks are "
            "unsatisfied and this program exits non-zero because of them."
        )
        return [
            Check(stop_id, stop_title, False, why, {"mode": mode}, probes.source),
            Check(restore_id, restore_title, False, why, {"mode": mode}, probes.source),
        ]

    detail: dict[str, Any] = {"mode": mode}
    try:
        status = probes.kill_switch.status()
        detail["status_exit"] = status.returncode
        detail["status_stdout_tail"] = mask(plain(status.stdout)[-400:])
        dry = probes.kill_switch.dry_run()
        detail["dry_run_exit"] = dry.returncode
        detail["dry_run_names_put"] = "put-function-concurrency" in dry.stdout
        detail["dry_run_names_delete"] = "delete-function-concurrency" in dry.stdout
    except Unavailable as exc:
        why = f"the kill switch could not be driven at all: {exc}"
        return [
            Check(stop_id, stop_title, False, why, detail, probes.source),
            Check(restore_id, restore_title, False, why, detail, probes.source),
        ]

    if mode != "live":
        why = (
            "--kill-switch dry drives --status and --dry-run only. --status exited "
            f"{detail['status_exit']} (4 means the function does not exist). The stop was "
            "NOT performed and the 429 was NOT observed, so this is unsatisfied. Re-run "
            "with --kill-switch live --yes against an applied stack to satisfy it."
        )
        return [
            Check(stop_id, stop_title, False, why, detail, probes.source),
            Check(restore_id, restore_title, False, why, detail, probes.source),
        ]

    return _kill_switch_live(probes, base, detail, expect_account=expect_account)


def _kill_switch_live(
    probes: Probes,
    base: str | None,
    detail: dict[str, Any],
    *,
    expect_account: str | None,
) -> list[Check]:
    """The mutating half: stop, observe 429 with no body, restore, observe the service back.

    Split out of :func:`check_kill_switch` so the read-only paths above it stay short enough
    to read in one screen. **This is the only function in the program that can change
    anything in the account**, and it is reached only from ``--kill-switch live``, which
    itself requires ``--yes``.
    """
    stop_id, restore_id = "kill_switch_stop", "kill_switch_restore"
    stop_title = "kill switch --stop produces HTTP 429 with no body"
    restore_title = "kill switch --restore returns the service"

    checks: list[Check] = []
    try:
        stopped = probes.kill_switch.stop(expect_account=expect_account)
    except Unavailable as exc:
        why = f"--stop could not be run: {exc}"
        return [
            Check(stop_id, stop_title, False, why, detail, probes.source),
            Check(restore_id, restore_title, False, why, detail, probes.source),
        ]
    detail["stop_exit"] = stopped.returncode
    if stopped.returncode != 0:
        why = (
            f"kill_switch.sh --stop exited {stopped.returncode}: "
            f"{mask(plain(stopped.stderr or stopped.stdout)[-400:])}"
        )
        checks.append(Check(stop_id, stop_title, False, why, detail, probes.source))
    else:
        after = _probe_once(probes, base)
        detail["after_stop"] = after
        if after.get("status") != 429:
            checks.append(
                Check(
                    stop_id,
                    stop_title,
                    False,
                    "--stop exited 0 but the origin answered "
                    f"{after.get('status')}, not 429. A kill switch whose call succeeded "
                    "and whose effect did not land is the worst of the three outcomes: it "
                    "reports safety it has not produced.",
                    detail,
                    probes.source,
                )
            )
        elif after.get("body_bytes"):
            checks.append(
                Check(
                    stop_id,
                    stop_title,
                    False,
                    f"the origin answered 429 with {after.get('body_bytes')} bytes of body. "
                    "Lambda's own throttle answers 429 with nothing; a body means the "
                    "handler ran, which means the reservation did not stop it.",
                    detail,
                    probes.source,
                )
            )
        else:
            checks.append(
                Check(
                    stop_id,
                    stop_title,
                    True,
                    "reserved concurrency 0 landed and the origin answers 429 with no body.",
                    detail,
                    probes.source,
                )
            )

    try:
        restored = probes.kill_switch.restore(expect_account=expect_account)
    except Unavailable as exc:
        checks.append(
            Check(
                restore_id,
                restore_title,
                False,
                f"--restore could not be run: {exc}",
                detail,
                probes.source,
            )
        )
        return checks
    detail["restore_exit"] = restored.returncode
    if restored.returncode != 0:
        checks.append(
            Check(
                restore_id,
                restore_title,
                False,
                f"kill_switch.sh --restore exited {restored.returncode}. THE DEMO IS STILL "
                "STOPPED. Restore it by hand before leaving: scripts/deploy/kill_switch.sh "
                "--restore --expect-account <id> --yes",
                detail,
                probes.source,
            )
        )
        return checks
    back = _probe_once(probes, base)
    detail["after_restore"] = back
    if back.get("status") == 429:
        checks.append(
            Check(
                restore_id,
                restore_title,
                False,
                "--restore exited 0 and the origin still answers 429. A 429 that never "
                "cleared is an outage the runbook believes it ended.",
                detail,
                probes.source,
            )
        )
    elif back.get("status") != 200:
        checks.append(
            Check(
                restore_id,
                restore_title,
                False,
                f"after --restore the origin answers {back.get('status')}, not 200.",
                detail,
                probes.source,
            )
        )
    else:
        checks.append(
            Check(
                restore_id,
                restore_title,
                True,
                "the reservation was removed and /v1/health answers 200 again.",
                detail,
                probes.source,
            )
        )
    return checks


def _probe_once(probes: Probes, base: str | None) -> dict[str, Any]:
    """One ``GET /v1/health``, reporting the status even when it is a refusal."""
    if base is None:
        return {"status": None, "why": "no Function URL"}
    try:
        answer = probes.http.request(
            "GET", urllib.parse.urljoin(base, "v1/health"), headers={"accept": "application/json"}
        )
    except Unavailable as exc:
        return {"status": None, "why": str(exc)}
    return {"status": answer.status, "body_bytes": len(answer.body)}


# ═════════════════════════════════════════════════════════════════════════════════════
# the run
# ═════════════════════════════════════════════════════════════════════════════════════


def load_expected_alarms(
    root: Path, prefix: str
) -> tuple[list[str] | None, str | None, dict[str, Any]]:
    """Import the derivation from ``aws_live_probe.py`` and run it. Never a literal here.

    Imported by path rather than by package so this program keeps working from a checkout
    with no ``scripts`` package on ``sys.path``, and so the controls can point it at a
    scratch tree.
    """
    import importlib.util

    probe_path = root / "scripts" / "deploy" / "aws_live_probe.py"
    if not probe_path.is_file():
        return None, f"{probe_path} does not exist, so the alarm set cannot be derived.", {}
    spec = importlib.util.spec_from_file_location("_mainline_aws_live_probe", probe_path)
    if spec is None or spec.loader is None:
        return None, f"{probe_path} could not be loaded as a module.", {}
    module = importlib.util.module_from_spec(spec)
    # Registered for the duration of the exec and removed afterwards. `dataclasses` looks
    # the defining module up in `sys.modules` while it processes a class, and a module that
    # is not there fails with an AttributeError that names nothing useful. Registering it
    # is not optional hygiene; without it this import breaks the moment the probe grows a
    # dataclass, and it breaks in a way that reads like a bug in the probe.
    previous = sys.modules.get(spec.name)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
        names, provenance = module.expected_alarm_names(root, prefix)
    except Exception as exc:  # noqa: BLE001 - any failure here is "cannot state expectation"
        return None, f"the expected alarm set could not be derived: {exc}", {}
    finally:
        if previous is None:
            sys.modules.pop(spec.name, None)
        else:
            sys.modules[spec.name] = previous
    return list(names), None, provenance


def verify(
    probes: Probes, args: argparse.Namespace, root: Path
) -> tuple[list[Check], dict[str, Any]]:
    """Run every check in order and return them with the context the evidence needs."""
    window_start = datetime.now(UTC)
    checks: list[Check] = []

    url_check, base = check_function_url(probes)
    checks.append(url_check)
    checks.append(check_tls(probes, base))
    checks.append(check_health(probes, base))
    beat_check, payload = check_beats(probes, base)
    checks.append(beat_check)
    checks.append(check_clearance_digest(probes, payload))

    expected, underivable, provenance = load_expected_alarms(root, args.alarm_prefix)
    inventory, alarms = check_alarm_inventory(probes, args.alarm_prefix, expected, underivable)
    checks.append(inventory)

    # The window closes AFTER the beats, and opens before them, so it brackets exactly the
    # invocations this program is responsible for. A wider window would let somebody else's
    # traffic satisfy the visibility check, which would make it pass for the wrong reason.
    window_end = datetime.now(UTC) + timedelta(minutes=args.metric_lag_minutes)
    checks.append(check_alarm_visibility(probes, alarms, window_start, window_end))

    checks.extend(
        check_kill_switch(probes, base, args.kill_switch, expect_account=args.expect_account)
    )

    context = {
        "function_url_resolved": base is not None,
        "alarm_prefix": args.alarm_prefix,
        "alarm_set_provenance": provenance,
        "kill_switch_mode": args.kill_switch,
        "window_start": window_start.isoformat(),
        "window_end": window_end.isoformat(),
    }
    return checks, context


def build_document(
    checks: list[Check], context: dict[str, Any], args: argparse.Namespace
) -> dict[str, Any]:
    unsatisfied = [c for c in checks if not c.satisfied]
    return {
        "schema": "mainline.deploy.post-apply-verify/1",
        "generated_at": datetime.now(UTC).isoformat(),
        "program": "scripts/deploy/post_apply_verify.py",
        "region": args.region,
        "profile": args.profile,
        "function_name": args.function_name,
        "account_masking": "every twelve-digit run is replaced with <account> before writing",
        "context": json.loads(mask(json.dumps(context, default=str))),
        "checks_total": len(checks),
        "checks_satisfied": len(checks) - len(unsatisfied),
        "checks_unsatisfied": len(unsatisfied),
        "unsatisfied_ids": [c.id for c in unsatisfied],
        "verdict": "ALL CHECKS SATISFIED" if not unsatisfied else "NOT SATISFIED",
        "checks": [c.as_json() for c in checks],
    }


def summarise(checks: list[Check]) -> None:
    say()
    say("post-apply verification")
    for check in checks:
        flag = "SATISFIED" if check.satisfied else "NOT SATISFIED"
        say(f"  {flag:<14} {check.id:<22} {check.title}")
        if not check.satisfied:
            say(f"  {'':<14} why: {check.why}")
    unsatisfied = [c for c in checks if not c.satisfied]
    say()
    if not unsatisfied:
        say(f"  every one of {len(checks)} checks was satisfied.")
        return
    say(f"  {len(unsatisfied)} of {len(checks)} checks COULD NOT BE SATISFIED:")
    for check in unsatisfied:
        say(f"    - {check.id}: {check.why}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="post_apply_verify.py",
        description="Measure a freshly applied MAINLINE demo stack. Never applies anything.",
    )
    parser.add_argument(
        "--tf-dir", type=Path, default=None, help="Terraform root to read outputs from"
    )
    parser.add_argument("--region", default=DEFAULT_REGION)
    parser.add_argument("--profile", default=DEFAULT_PROFILE)
    parser.add_argument("--function-name", default=DEFAULT_FUNCTION)
    parser.add_argument("--alarm-prefix", default=DEFAULT_ALARM_PREFIX)
    parser.add_argument(
        "--kill-switch",
        choices=("dry", "live", "skip"),
        default="dry",
        help=(
            "dry (default): --status and --dry-run only; the two kill-switch checks are "
            "reported UNSATISFIED with the reason. live: actually stop and restore, and "
            "requires --yes. skip: do not touch it at all, still unsatisfied."
        ),
    )
    parser.add_argument("--yes", action="store_true", help="required by --kill-switch live")
    parser.add_argument(
        "--expect-account",
        default=os.environ.get("MAINLINE_AWS_ACCOUNT") or None,
        help="passed through to kill_switch.sh; never printed",
    )
    parser.add_argument(
        "--metric-lag-minutes",
        type=int,
        default=5,
        help="how far past the last invocation to look for datapoints (CloudWatch lags)",
    )
    parser.add_argument("--out", type=Path, default=None, help="write the evidence document here")
    parser.add_argument("--print-json", action="store_true")
    return parser


def main(argv: list[str] | None = None, probes: Probes | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = repo_root()
    if args.tf_dir is None:
        args.tf_dir = root / DEFAULT_TF_DIR
    if args.kill_switch == "live" and not args.yes:
        print(
            "post_apply_verify: --kill-switch live mutates a live function's reserved "
            "concurrency. Pass --yes as well, and do not pass either against a stack that "
            "does not exist.",
            file=sys.stderr,
        )
        return EXIT_USAGE
    if args.metric_lag_minutes < 0:
        print("post_apply_verify: --metric-lag-minutes cannot be negative.", file=sys.stderr)
        return EXIT_USAGE

    if probes is None:
        probes = Probes(
            terraform=TerraformReader(args.tf_dir),
            http=HttpClient(),
            aws=AwsReader(profile=args.profile, region=args.region),
            kill_switch=KillSwitchDriver(
                root / "scripts" / "deploy" / "kill_switch.sh", function=args.function_name
            ),
            source="live",
        )

    checks, context = verify(probes, args, root)
    document = build_document(checks, context, args)
    summarise(checks)

    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
        say(f"\n  evidence written to {args.out}")
    if args.print_json:
        say(json.dumps(document, indent=2))

    return EXIT_OK if not document["unsatisfied_ids"] else EXIT_UNSATISFIED


if __name__ == "__main__":  # pragma: no cover - exercised through main()
    sys.exit(main())
