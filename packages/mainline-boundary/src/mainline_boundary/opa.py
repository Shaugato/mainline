# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Run the Rego re-statement of E1/E2/E4 with conftest or OPA.

The Rego under ``tests/boundary/policy/`` exists for one reason: E2 is the
enforcement a security reviewer believes *because it does not depend on our code
being correct*, and a Rego policy evaluated by somebody else's engine is the
cheapest way to make that literally true. If the Python and the Rego disagree,
one of them is wrong and the suite says so.

Neither binary is a dependency of this package. When neither is on ``PATH`` the
runner returns ``None`` and the caller records a **skip with a reason** — never a
pass. The CI workflow installs conftest, so the skip is a local-development
convenience and a CI impossibility.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

DEFAULT_TIMEOUT_SECONDS = 120

#: The Rego package prefix every policy in tests/boundary/policy/ lives under.
POLICY_PACKAGE = "mainline.boundary"


@dataclass(frozen=True, slots=True)
class PolicyRunner:
    tool: str  # "conftest" | "opa"
    executable: str


@dataclass(frozen=True, slots=True)
class RegoResult:
    runner: PolicyRunner
    failures: tuple[str, ...]
    warnings: tuple[str, ...]
    raw_stdout: str
    raw_stderr: str
    returncode: int

    @property
    def ok(self) -> bool:
        return not self.failures


def find_policy_runner() -> PolicyRunner | None:
    """conftest first (it reports per-policy), OPA second."""
    for tool in ("conftest", "opa"):
        executable = shutil.which(tool)
        if executable:
            return PolicyRunner(tool=tool, executable=executable)
    return None


def run_rego(
    policy_dir: Path,
    input_path: Path,
    *,
    runner: PolicyRunner | None = None,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> RegoResult | None:
    """Evaluate ``policy_dir`` against ``input_path``. ``None`` when no engine exists."""
    engine = runner or find_policy_runner()
    if engine is None:
        return None
    if engine.tool == "conftest":
        return _run_conftest(engine, policy_dir, input_path, timeout)
    return _run_opa(engine, policy_dir, input_path, timeout)


def _run_conftest(
    engine: PolicyRunner, policy_dir: Path, input_path: Path, timeout: int
) -> RegoResult:
    completed = subprocess.run(
        [
            engine.executable,
            "test",
            "--policy",
            str(policy_dir),
            "--all-namespaces",
            "--output",
            "json",
            str(input_path),
        ],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    failures: list[str] = []
    warnings: list[str] = []
    try:
        payload = json.loads(completed.stdout or "[]")
    except json.JSONDecodeError:
        return RegoResult(
            runner=engine,
            failures=(
                f"conftest produced output that is not JSON (exit {completed.returncode}): "
                f"{completed.stdout.strip()[:400]} {completed.stderr.strip()[:400]}",
            ),
            warnings=(),
            raw_stdout=completed.stdout,
            raw_stderr=completed.stderr,
            returncode=completed.returncode,
        )
    for entry in payload if isinstance(payload, list) else []:
        if not isinstance(entry, dict):
            continue
        for item in entry.get("failures") or ():
            failures.append(_message(item))
        for item in entry.get("warnings") or ():
            warnings.append(_message(item))
    return RegoResult(
        runner=engine,
        failures=tuple(failures),
        warnings=tuple(warnings),
        raw_stdout=completed.stdout,
        raw_stderr=completed.stderr,
        returncode=completed.returncode,
    )


def _run_opa(
    engine: PolicyRunner, policy_dir: Path, input_path: Path, timeout: int
) -> RegoResult:
    query = f"data.{POLICY_PACKAGE}"
    completed = subprocess.run(
        [
            engine.executable,
            "eval",
            "--format",
            "json",
            "--data",
            str(policy_dir),
            "--input",
            str(input_path),
            query,
        ],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if completed.returncode != 0:
        return RegoResult(
            runner=engine,
            failures=(
                f"opa eval failed (exit {completed.returncode}): "
                f"{completed.stderr.strip()[:600]}",
            ),
            warnings=(),
            raw_stdout=completed.stdout,
            raw_stderr=completed.stderr,
            returncode=completed.returncode,
        )
    failures: list[str] = []
    try:
        payload = json.loads(completed.stdout or "{}")
    except json.JSONDecodeError:
        return RegoResult(
            runner=engine,
            failures=("opa eval produced output that is not JSON",),
            warnings=(),
            raw_stdout=completed.stdout,
            raw_stderr=completed.stderr,
            returncode=completed.returncode,
        )
    for result in payload.get("result", []):
        for expression in result.get("expressions", []):
            failures.extend(_collect_denies(expression.get("value")))
    return RegoResult(
        runner=engine,
        failures=tuple(sorted(set(failures))),
        warnings=(),
        raw_stdout=completed.stdout,
        raw_stderr=completed.stderr,
        returncode=completed.returncode,
    )


def _message(item: object) -> str:
    """conftest reports a failure as either a bare string or ``{"msg": ...}``."""
    if isinstance(item, dict):
        text = item.get("msg") or item.get("message") or ""
        metadata = item.get("metadata")
        if isinstance(metadata, dict) and metadata.get("query"):
            return f"{text}  [{metadata['query']}]"
        return str(text)
    return str(item)


def _collect_denies(value: object) -> list[str]:
    """Walk ``data.mainline.boundary.*`` and collect every ``deny`` set."""
    out: list[str] = []
    if isinstance(value, dict):
        for key, inner in value.items():
            if key == "deny" and isinstance(inner, list):
                out.extend(str(item) for item in inner)
            else:
                out.extend(_collect_denies(inner))
    elif isinstance(value, list):
        for item in value:
            out.extend(_collect_denies(item))
    return out


def describe_missing_runner() -> str:
    return (
        "neither `conftest` nor `opa` is on PATH, so the Rego re-statement of "
        "E1/E2/E4 was not evaluated. The Python assertions in this suite still "
        "stand; the independent second opinion does not. CI installs conftest, so "
        "this skip cannot occur there."
    )


def policy_files(policy_dir: Path) -> Sequence[Path]:
    return sorted(policy_dir.glob("*.rego"))
