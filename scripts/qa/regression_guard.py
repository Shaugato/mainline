#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""ONE COMMAND THAT ANSWERS: *is anything that used to be true no longer true?*

Every suite in this repository answers a different question — *does this unit behave?*
This program answers the only question a wave of concurrent editors makes urgent, which
is whether the CLAIMS the project already publishes still hold. A claim is not a test.
A test can be deleted, skipped, re-baselined or quietly narrowed and the lane stays
green; a claim has a number attached to it, in a README, an evidence file or a judge's
browser, and when the number moves the claim becomes a lie without anything going red.

Six families, because a reader who is told "three checks failed" learns nothing and a
reader who is told "PRIVILEGES failed" already knows which way to walk.

KERNEL — the product's central sentence
--------------------------------------
``scripts/proof/gate_refusal.py`` builds a throwaway database, applies the whole
migration chain, and asks the gate to merge a permit three times. This family re-runs it
and reads its EVIDENCE FILE rather than its terminal output, then asserts four things the
verdict line alone does not:

* the verdict is ``PROVEN`` **and** ``caveats`` is empty. The proof publishes caveats
  precisely so that a run can be proven-but-qualified; a guard that read only the verdict
  would call a qualified run a clean one.
* the refusal is ``23514`` on ``gate_closed_when_issued`` (CF-01), the drift refusal is
  ``P0001`` naming ``mainline.fn_permit_merge_gate`` (CF-03), the admission is ``00000``.

**A DIFFERENT SQLSTATE IS A REGRESSION EVEN WHEN THE VERDICT STILL SAYS PROVEN.** The
exhibits are what ``spec/conformance/manifest.toml`` pins and what the console prints; a
gate that starts refusing with ``23505`` has stopped being the gate the documents
describe, whatever the summary line says. This is also the one family whose failure mode
was already lived: ``attempt_merge`` used to classify ``40001`` as a refusal and write it
into ``mainline.refusal_ledger``, so "the gate refused" and "the transaction restarted"
were the same string until somebody looked at the SQLSTATE.

SUITES — the numbers, from the root element only
------------------------------------------------
demo-api and ``tests/deploy`` under ``--crdb=reuse``. The counts are read from the
``--junitxml`` ROOT ELEMENT and never from a terminal tail, because the tail is written by
a summary line that a crashed session, a hard timeout or a plugin can truncate — this
guard's own first baseline run printed a ``Timeout`` traceback and no summary at all while
the XML sat there carrying ``tests="579"``, which is exactly the disagreement the root
element exists to settle.

Failures are reported BY NODE ID. "3 failed" tells a reader nothing; three node ids tell a
reader whether the console wave broke the console tests or broke the gate.

BOUNDS — the constants a previous wave was forbidden from moving
----------------------------------------------------------------
``static_site.DEFAULT_MAX_RESPONSE_BYTES`` is ``136 * 1024``. Around it sit two facts that
are only interesting together: the largest object the deployment actually serves is BELOW
the ceiling, and the largest object on disk is ABOVE it, so exactly ONE identity GET is
refused with ``413`` and every gzipped GET succeeds. That straddle is what makes the
ceiling a measurement rather than a preference.

The temptation this family exists to refuse is specific and has a name: when the arithmetic
stops agreeing, RAISE THE CEILING. A previous wave was explicitly forbidden from doing it,
and the reason is that the ceiling is not ours — it is what Lambda's response payload limit
leaves after base64 expansion, and moving it does not move the limit, it only moves where
the failure appears. So this family reads the constant out of the SOURCE (the expression
text, not just its value) and recomputes the two extremes from the BUILT ARTEFACT's central
directory, which is the tree that actually ships. ``console/dist`` is deliberately not
consulted: it carries source maps and zero ``.gz`` siblings, so every number taken from it
is a number about a tree nobody serves.

PRIVILEGES — the family with a body count
-----------------------------------------
**Five separate live outages in one day, each found one HTTP request at a time**, because
nothing in this repository compared what the application code NEEDS against what the
``mainline_api`` role HOLDS. Both halves existed — the SQL is in the source, the grants are
in the cluster — and no program had ever put them side by side.

So this family extracts every schema-qualified relation and routine that
``verticals/mainline/apps/demo-api/src/mainline_demo_api/**`` names inside a SQL string,
WITH THE PRIVILEGE THE VERB IMPLIES (``FROM``/``JOIN`` → SELECT, ``INSERT INTO`` → INSERT,
``UPDATE`` → UPDATE, ``DELETE FROM`` → DELETE, ``CALL`` → EXECUTE), and asks the cluster
``has_table_privilege`` / ``has_function_privilege`` for the role by name. Four traps, each
of which has already cost somebody a wrong answer:

1. **``SHOW GRANTS`` spells a routine with its full signature** —
   ``merge_permit(uuid, bytea, …)`` — while ``information_schema.routines`` gives the bare
   name. Comparing the two naively produces false positives, and did: it cost the
   orchestrator a wrong conclusion earlier today. This program never compares those two
   strings. It resolves routines through ``pg_proc`` to an OID and asks
   ``has_function_privilege`` about the OID, and it keeps a check
   (``privileges.routine_signature_normalised``) whose whole job is to fail if that trap
   ever stops being present — a normalisation nobody exercises is a normalisation nobody
   can trust.
2. **A trigger function needs no grant to the caller.** ``information_schema.routines``
   reports ``data_type = 'trigger'`` for those, and requiring EXECUTE on them would paint
   a healthy deployment red.
3. **``SHOW GRANTS`` for a role lists only its DIRECT grants.** ``mainline_api`` is a
   member of ``agent_gate``, ``auditor_ro`` and ``svc_disposition``, so a direct-grant
   diff under-reports what the role can reach. ``has_table_privilege`` resolves
   membership; that is why it is the authority here and ``SHOW GRANTS`` is not.
4. **Not every schema-qualified name in the source is a required object.**
   ``reads._PROPAGATION_PROBE`` passes ``mainline.lesson``, ``mainline.propagation`` and
   ``mainline.merge_conflict`` to ``to_regclass`` precisely BECAUSE they may not exist, and
   ``mainline_audit`` is reached through an f-string whose relation name comes from the
   catalogue. So the extractor keys on the SQL verb rather than on the dot, and the audit
   views are enumerated from ``information_schema.views`` instead of guessed.

The gate chain gets its own check. When ``mainline_api`` calls ``mainline.merge_permit``
the trigger bodies run AS THE CALLER, so the role needs SELECT on tables the application
source never names. ``scripts/deploy/cloud_roles.API_GATE_READ`` is the list, discovered
the expensive way — "parse the 42501, grant exactly the named privilege, repeat" — and it
is read from that file rather than restated here, so the two cannot drift apart.

LIVE — and a skip that cannot be mistaken for a pass
-----------------------------------------------------
``GET /v1/health`` must answer ``ok=true`` with ``deploy_chain_applied == 271``, and
``POST /v1/demo/gate-run`` must answer ``VERDICT PROVEN`` with all four beats matching
their expectations by outcome, SQLSTATE, exhibit AND exhibit source — beat 2's exhibit is
``reported`` by the driver and beat 3's is ``parsed`` out of the message, and a beat that
started reporting what it used to parse has changed meaning even though both spellings say
``mainline.fn_permit_merge_gate``.

``--no-live`` skips this family and ``--no-cloud`` skips the two that talk SQL over the
network. **A skipped check prints ``SKIP`` with the reason it skipped, and the verdict line
counts skips separately and refuses the word GREEN when there are any.** A skip that looks
like a pass is how a suite goes green while asserting nothing, which is the failure this
repository has already had.

SEED SHAPE — and the ``defaultdb`` trap
----------------------------------------
The demo depends on a shape, not just on rows existing: ``defeater_option`` carries 6 rows
across 2 checks with exactly ONE distinct ``vocab_sha256`` per check (0064 says one
generation has one digest, and beat 4 signs that digest — a second digest on one check
makes the signature pin nothing), the ledger is 4 leaves and 3 nodes with a checkpoint
whose ``tree_size`` matches the leaves it commits to, and the permit, its obligations and
the two enrolled credentials are all there.

**The committed DSN's path segment is ``defaultdb``, not ``mainline_demo``.** Anything that
reads ``COCKROACH_DSN`` verbatim connects successfully, finds zero ``mainline.*`` tables and
concludes the deployment is empty. So the database is substituted BY NAME and then
confirmed with ``SELECT current_database()``; the DSN's own path segment is never trusted,
and the DSN itself is never printed or written to the JSON.

Usage::

    python scripts/qa/regression_guard.py
    python scripts/qa/regression_guard.py --no-live --json qa/regression-guard.json
    python scripts/qa/regression_guard.py --only KERNEL,BOUNDS

Exit codes: ``0`` when no check FAILED (skips are reported, not fatal), ``1`` when any
check FAILED, ``2`` when the invocation itself was wrong.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

EXIT_GREEN = 0
EXIT_RED = 1
EXIT_USAGE = 2

PASS, FAIL, SKIP = "PASS", "FAIL", "SKIP"

FAMILIES = ("KERNEL", "SUITES", "BOUNDS", "PRIVILEGES", "LIVE", "SEED")

# ── KERNEL ───────────────────────────────────────────────────────────────────────────
#: The three exhibits `spec/conformance/manifest.toml` group 1 pins, plus the admission.
#: Restated here rather than imported because importing `gate_refusal` would make this
#: guard agree with the proof BY CONSTRUCTION — the two would move together and the
#: comparison would assert nothing.
KERNEL_REFUSAL = ("23514", "gate_closed_when_issued")
KERNEL_DRIFT = ("P0001", "mainline.fn_permit_merge_gate")
KERNEL_ADMISSION = "00000"

# ── SUITES ───────────────────────────────────────────────────────────────────────────
SUITE_PATHS = ("verticals/mainline/apps/demo-api/tests", "tests/deploy")
#: Measured 2026-08-15 against a clean tree with the local node up. `collected` is the
#: number `--collect-only` reports; the other four come off the junit root element.
SUITE_BASELINE = {"collected": 911, "passed": 910, "failed": 0, "errors": 0, "skipped": 1}

# ── BOUNDS ───────────────────────────────────────────────────────────────────────────
CEILING_EXPRESSION = "136 * 1024"
CEILING_BYTES = 136 * 1024  # 139_264
#: The artefact the deployment ships. NOT `console/dist`, which carries source maps and
#: no `.gz` siblings — see the module docstring.
DEFAULT_ARTEFACT = Path("out/lambda/mainline-demo-api-arm64.zip")
ARTEFACT_WEB_PREFIX = "web/"
GZ_SUFFIX = ".gz"
_CEILING_RE = re.compile(
    r"^DEFAULT_MAX_RESPONSE_BYTES\s*(?::[^=]+)?=\s*(.+?)\s*(?:#.*)?$", re.MULTILINE
)
_ARITHMETIC = re.compile(r"^[0-9_+*() ]+$")

# ── PRIVILEGES ───────────────────────────────────────────────────────────────────────
API_ROLE = "mainline_api"
SCHEMAS = ("mainline", "mainline_ops", "mainline_meas", "mainline_audit", "trappoint")
_SCHEMA_ALT = "|".join(SCHEMAS)
_OBJ = rf"((?:{_SCHEMA_ALT})\.[a-z_][a-z0-9_]*)"
#: The verb decides the privilege. Keying on the dot instead would sweep up
#: `to_regclass('mainline.lesson')` — a probe for a table that deliberately does not
#: exist — and every schema-qualified name that appears only in prose.
SQL_VERBS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("SELECT", re.compile(rf"\b(?:FROM|JOIN)\s+(?:ONLY\s+)?{_OBJ}", re.IGNORECASE)),
    ("INSERT", re.compile(rf"\b(?:INSERT|UPSERT)\s+INTO\s+{_OBJ}", re.IGNORECASE)),
    ("UPDATE", re.compile(rf"\bUPDATE\s+{_OBJ}", re.IGNORECASE)),
    ("DELETE", re.compile(rf"\bDELETE\s+FROM\s+{_OBJ}", re.IGNORECASE)),
    ("EXECUTE", re.compile(rf"\bCALL\s+{_OBJ}", re.IGNORECASE)),
)
DEFAULT_API_SRC = Path("verticals/mainline/apps/demo-api/src/mainline_demo_api")
DEFAULT_STATIC_SITE = DEFAULT_API_SRC / "static_site.py"
CLOUD_ROLES = Path("scripts/deploy/cloud_roles.py")
#: `mainline_audit` is reached as `SELECT * FROM mainline_audit.{name}` where `name` came
#: out of `information_schema.views`. Enumerated from the catalogue, never guessed.
AUDIT_SCHEMA = "mainline_audit"

# ── LIVE ─────────────────────────────────────────────────────────────────────────────
DEFAULT_BASE_URL = "https://ihuuyvm4z6nfuktihnkey77fpy0eyrhj.lambda-url.ap-southeast-1.on.aws"
DEPLOY_CHAIN_APPLIED = 271
USER_AGENT = "mainline-regression-guard/1.0"
#: Outcome, SQLSTATE, exhibit and HOW THE EXHIBIT WAS OBTAINED, for each of the four
#: beats. The last field is the one a careless change silently flips: beat 2's constraint
#: name is `reported` by the driver, beat 3's is `parsed` out of the raised message
#: because P0001 carries no constraint name.
LIVE_BEATS: tuple[tuple[int, str, str, str, str | None, str | None], ...] = (
    (1, "read", "read", "00000", None, None),
    (2, "merge", "refused", "23514", "gate_closed_when_issued", "reported"),
    (
        3,
        "projection_drift_attack",
        "refused",
        "P0001",
        "mainline.fn_permit_merge_gate",
        "parsed",
    ),
    (4, "admit", "admitted", "00000", None, None),
)

# ── SEED ─────────────────────────────────────────────────────────────────────────────
SEED_DATABASE = "mainline_demo"
SEED_ENV_FILE = Path(".env")
SEED_DSN_KEY = "COCKROACH_DSN"
#: Row counts the demo depends on. `mainline.blocking_check` is 2 and not 1: the two seed
#: files together open two obligations, which is also what `evidence/deploy/cloud-seed.json`
#: has recorded since the seed was frozen, and what makes `defeater_option` 6-across-2
#: arithmetic work.
SEED_COUNTS = {
    "mainline.permit": 1,
    "mainline.blocking_check": 2,
    "mainline.signing_credential": 2,
    "mainline.ledger_leaf": 4,
    "mainline.ledger_node": 3,
}
SEED_DEFEATER_ROWS = 6
SEED_DEFEATER_CHECKS = 2


# ═════════════════════════════════════════════════════════════════════════════════════
# the record
# ═════════════════════════════════════════════════════════════════════════════════════


@dataclass(slots=True)
class Check:
    """One claim, its expected value, what was measured, and which way it went."""

    family: str
    name: str
    status: str
    expected: str
    observed: str
    detail: str = ""
    #: Anything a reader would have to re-derive by hand. Lands in `--json`, never on the
    #: one-line-per-check surface, because a line nobody can scan is a line nobody reads.
    extra: dict[str, Any] = field(default_factory=dict)

    def as_json(self) -> dict[str, Any]:
        return {
            "family": self.family,
            "name": self.name,
            "status": self.status,
            "expected": self.expected,
            "observed": self.observed,
            "detail": self.detail,
            **({"extra": self.extra} if self.extra else {}),
        }


def _check(
    family: str,
    name: str,
    holds: bool,
    expected: Any,
    observed: Any,
    detail: str = "",
    **extra: Any,
) -> Check:
    return Check(
        family=family,
        name=name,
        status=PASS if holds else FAIL,
        expected=str(expected),
        observed=str(observed),
        detail=detail,
        extra=extra,
    )


def _skip(family: str, name: str, why: str, expected: Any = "") -> Check:
    """A skip that SAYS SO. Never rendered as a pass, never counted as one."""
    return Check(
        family=family,
        name=name,
        status=SKIP,
        expected=str(expected),
        observed="not measured",
        detail=why,
    )


# ═════════════════════════════════════════════════════════════════════════════════════
# small helpers
# ═════════════════════════════════════════════════════════════════════════════════════


def _repo_root(start: Path | None = None) -> Path:
    """The workspace root: the nearest ancestor holding both `spec/` and `compose.yaml`."""
    here = (start or Path(__file__).resolve().parent).resolve()
    for candidate in (here, *here.parents):
        if (candidate / "spec").is_dir() and (candidate / "compose.yaml").is_file():
            return candidate
    return Path.cwd().resolve()


def read_env_file(path: Path) -> dict[str, str]:
    """Parse ``KEY=VALUE`` lines. No expansion, no ``export``, no shell."""
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def redact_dsn(dsn: str) -> str:
    """A DSN with the password replaced. The only form of it this program will record."""
    try:
        split = urlsplit(dsn)
    except ValueError:
        return "<unparseable DSN>"
    if not split.hostname:
        return "<non-URL DSN, redacted>"
    user = split.username or ""
    auth = f"{user}:***@" if split.password else (f"{user}@" if user else "")
    port = f":{split.port}" if split.port else ""
    return f"{split.scheme}://{auth}{split.hostname}{port}{split.path}"


def with_database(dsn: str, database: str) -> str:
    """Return *dsn* with its path segment replaced. See the docstring's ``defaultdb`` trap."""
    split = urlsplit(dsn)
    return urlunsplit(
        (split.scheme, split.netloc, f"/{database.lstrip('/')}", split.query, split.fragment)
    )


def _sql_literals(source: str) -> list[str]:
    """Every string constant in *source* EXCEPT the docstrings.

    A docstring is a bare string expression statement, and this repository's docstrings
    quote SQL constantly — the module prose above quotes ``INSERT INTO`` itself. Including
    them would make the extractor require whatever the last author happened to mention.
    """
    found: list[str] = []

    class _Visitor(ast.NodeVisitor):
        def visit_Expr(self, node: ast.Expr) -> None:
            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                return
            self.generic_visit(node)

        def visit_Constant(self, node: ast.Constant) -> None:
            if isinstance(node.value, str):
                found.append(node.value)

    _Visitor().visit(ast.parse(source))
    return found


def _http_json(url: str, *, method: str = "GET", body: bytes | None = None, timeout: float) -> Any:
    request = urllib.request.Request(  # noqa: S310 - https URL from the command line
        url,
        data=body,
        method=method,
        headers={
            "User-Agent": USER_AGENT,
            **({"Content-Type": "application/json"} if body else {}),
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
        return json.loads(response.read().decode("utf-8"))


# ═════════════════════════════════════════════════════════════════════════════════════
# KERNEL
# ═════════════════════════════════════════════════════════════════════════════════════


def kernel_evidence(args: argparse.Namespace, root: Path) -> tuple[dict[str, Any] | None, str]:
    """The gate-refusal evidence document, either re-measured or re-read.

    ``--kernel-evidence`` exists for two reasons and both are honest ones: a lane that has
    already run the proof should not run it twice, and a guard has to be falsifiable —
    planting a wrong SQLSTATE into a copy of an evidence file is how this family was shown
    to go red for the right reason without editing a file this worker does not own.
    """
    if args.kernel_evidence is not None:
        path = Path(args.kernel_evidence)
        try:
            return json.loads(path.read_text(encoding="utf-8")), f"read from {path}"
        except (OSError, ValueError) as exc:
            return None, f"could not read {path}: {exc}"

    default_script = root / "scripts/proof/gate_refusal.py"
    script = Path(args.kernel_script) if args.kernel_script else default_script
    if not script.is_file():
        return None, f"no proof script at {script}"
    with tempfile.TemporaryDirectory(prefix="regression-guard-kernel-") as tmp:
        out = Path(tmp) / "gate-refusal.json"
        argv = [
            sys.executable,
            str(script),
            "--dsn",
            args.dsn,
            "--database",
            args.kernel_database,
            "--out",
            str(out),
        ]
        try:
            completed = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                cwd=str(root),
                timeout=args.kernel_timeout,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            return None, f"the proof could not be launched: {type(exc).__name__}: {exc}"
        if not out.is_file():
            tail = " ".join((completed.stderr or completed.stdout or "").split())[-300:]
            return None, f"the proof wrote no evidence (exit {completed.returncode}): {tail}"
        return json.loads(out.read_text(encoding="utf-8")), (
            f"scripts/proof/gate_refusal.py --database {args.kernel_database} "
            f"(exit {completed.returncode})"
        )


def family_kernel(args: argparse.Namespace, root: Path) -> list[Check]:
    evidence, how = kernel_evidence(args, root)
    if evidence is None:
        return [
            Check("KERNEL", name, FAIL, expected, "not measured", how)
            for name, expected in (
                ("verdict", "PROVEN"),
                ("caveats", "(none)"),
                ("refusal_sqlstate", KERNEL_REFUSAL[0]),
                ("refusal_exhibit", KERNEL_REFUSAL[1]),
                ("drift_sqlstate", KERNEL_DRIFT[0]),
                ("drift_exhibit", KERNEL_DRIFT[1]),
                ("admission_sqlstate", KERNEL_ADMISSION),
            )
        ]

    verdict = evidence.get("verdict")
    caveats = evidence.get("caveats") or []
    refusal = evidence.get("refusal") or {}
    drift = evidence.get("drift_refusal") or {}
    admission = evidence.get("admission") or {}
    failures = evidence.get("failures") or []

    return [
        _check(
            "KERNEL",
            "verdict",
            verdict == "PROVEN",
            "PROVEN",
            verdict,
            how,
            proof_failures=failures,
        ),
        _check(
            "KERNEL",
            "caveats",
            not caveats,
            "(none)",
            "(none)" if not caveats else f"{len(caveats)} caveat(s)",
            "a proven-but-qualified run is not a clean one",
            caveats=caveats,
        ),
        _check(
            "KERNEL",
            "refusal_sqlstate",
            refusal.get("sqlstate") == KERNEL_REFUSAL[0],
            KERNEL_REFUSAL[0],
            refusal.get("sqlstate"),
            "CF-01 · a different SQLSTATE is a regression even if the verdict says PROVEN",
        ),
        _check(
            "KERNEL",
            "refusal_exhibit",
            refusal.get("constraint") == KERNEL_REFUSAL[1],
            KERNEL_REFUSAL[1],
            refusal.get("constraint"),
            f"CF-01 · exhibit source {refusal.get('constraint_source')!r}",
        ),
        _check(
            "KERNEL",
            "drift_sqlstate",
            drift.get("sqlstate") == KERNEL_DRIFT[0],
            KERNEL_DRIFT[0],
            drift.get("sqlstate"),
            "CF-03 · the case no CHECK constraint can hold",
        ),
        _check(
            "KERNEL",
            "drift_exhibit",
            drift.get("constraint") == KERNEL_DRIFT[1],
            KERNEL_DRIFT[1],
            drift.get("constraint"),
            f"CF-03 · exhibit source {drift.get('constraint_source')!r}",
        ),
        _check(
            "KERNEL",
            "admission_sqlstate",
            admission.get("sqlstate") == KERNEL_ADMISSION
            and admission.get("outcome") == "ADMITTED",
            f"ADMITTED [{KERNEL_ADMISSION}]",
            f"{admission.get('outcome')} [{admission.get('sqlstate')}]",
            "a gate that always refuses is a broken gate, not a safe one",
        ),
    ]


# ═════════════════════════════════════════════════════════════════════════════════════
# SUITES
# ═════════════════════════════════════════════════════════════════════════════════════


def _junit_root(path: Path) -> ET.Element:
    """The ``<testsuite>`` element, whether or not pytest wrapped it in ``<testsuites>``."""
    root = ET.parse(path).getroot()  # noqa: S314 - a file this program just wrote
    if root.tag == "testsuite":
        return root
    found = root.find("testsuite")
    if found is None:
        raise ValueError(f"{path} carries no <testsuite> element")
    return found


def _node_ids(suite: ET.Element, tag: str) -> list[str]:
    ids: list[str] = []
    for case in suite.iter("testcase"):
        if case.find(tag) is not None:
            classname, name = case.get("classname", ""), case.get("name", "")
            ids.append(f"{classname}::{name}" if classname else name)
    return sorted(ids)


def run_suites(args: argparse.Namespace, root: Path) -> tuple[Path | None, str]:
    """Run the two suites into one junit file, or accept one that already exists."""
    if args.junit is not None:
        return Path(args.junit), f"read from {args.junit}"
    out = Path(args.suite_out) if args.suite_out else root / "qa" / "regression-guard-suites.xml"
    out.parent.mkdir(parents=True, exist_ok=True)
    argv = [
        sys.executable,
        "-m",
        "pytest",
        *SUITE_PATHS,
        "--crdb=reuse",
        "-q",
        "-p",
        "no:cacheprovider",
        f"--timeout={args.suite_timeout}",
        f"--junitxml={out}",
    ]
    try:
        subprocess.run(
            argv,
            capture_output=True,
            text=True,
            cwd=str(root),
            timeout=args.suite_wall_timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        if out.is_file():
            # The session died but the plugin still wrote the XML. That XML is the more
            # honest witness of the two and is read rather than discarded.
            return out, f"pytest aborted ({type(exc).__name__}); reading the XML it left"
        return None, f"pytest could not be run: {type(exc).__name__}: {exc}"
    if not out.is_file():
        return None, "pytest wrote no junit file"
    return out, f"pytest {' '.join(SUITE_PATHS)} --crdb=reuse --timeout={args.suite_timeout}"


def family_suites(args: argparse.Namespace, root: Path) -> list[Check]:
    path, how = run_suites(args, root)
    if path is None or not path.is_file():
        return [
            Check("SUITES", name, FAIL, str(expected), "not measured", how)
            for name, expected in SUITE_BASELINE.items()
        ]
    try:
        suite = _junit_root(path)
    except (ET.ParseError, ValueError) as exc:
        return [
            Check("SUITES", name, FAIL, str(expected), "unreadable", f"{how}: {exc}")
            for name, expected in SUITE_BASELINE.items()
        ]

    collected = int(suite.get("tests") or 0)
    failed = int(suite.get("failures") or 0)
    errors = int(suite.get("errors") or 0)
    skipped = int(suite.get("skipped") or 0)
    passed = collected - failed - errors - skipped
    failed_ids = _node_ids(suite, "failure")
    error_ids = _node_ids(suite, "error")
    skipped_ids = _node_ids(suite, "skipped")
    source = f"{how} · junit root element of {path.name}"

    return [
        _check(
            "SUITES",
            "collected",
            collected == SUITE_BASELINE["collected"],
            SUITE_BASELINE["collected"],
            collected,
            f"{source} — a shrinking collection is a deleted test, not a faster suite",
        ),
        _check(
            "SUITES",
            "passed",
            passed == SUITE_BASELINE["passed"],
            SUITE_BASELINE["passed"],
            passed,
            source,
        ),
        _check(
            "SUITES",
            "failed",
            failed == SUITE_BASELINE["failed"],
            SUITE_BASELINE["failed"],
            failed,
            "; ".join(failed_ids[:6]) or source,
            node_ids=failed_ids,
        ),
        _check(
            "SUITES",
            "errors",
            errors == SUITE_BASELINE["errors"],
            SUITE_BASELINE["errors"],
            errors,
            "; ".join(error_ids[:6]) or source,
            node_ids=error_ids,
        ),
        _check(
            "SUITES",
            "skipped",
            skipped == SUITE_BASELINE["skipped"],
            SUITE_BASELINE["skipped"],
            skipped,
            "; ".join(skipped_ids[:6]) or source,
            node_ids=skipped_ids,
        ),
    ]


# ═════════════════════════════════════════════════════════════════════════════════════
# BOUNDS
# ═════════════════════════════════════════════════════════════════════════════════════


def _ceiling_from_source(path: Path) -> tuple[str | None, int | None, str]:
    """The ceiling as the SOURCE spells it, and as it evaluates.

    Read out of the file rather than imported, so that the check is against the constant a
    reviewer sees in the diff. ``136 * 1024`` and ``139264`` are the same number and NOT
    the same line: the derivation lives in the factorisation.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return None, None, f"could not read {path}: {exc}"
    match = _CEILING_RE.search(text)
    if match is None:
        return None, None, f"DEFAULT_MAX_RESPONSE_BYTES is not assigned in {path}"
    expression = " ".join(match.group(1).split())
    if not _ARITHMETIC.match(expression):
        return expression, None, "the assignment is not integer arithmetic"
    return expression, int(eval(expression, {"__builtins__": {}}, {})), str(path)  # noqa: S307


def _artefact_web(path: Path) -> tuple[dict[str, int], dict[str, int]]:
    """``(identity, gzipped)`` — uncompressed sizes under ``web/``, keyed by relative path.

    The zip's CENTRAL DIRECTORY, not an extraction: ``file_size`` is the byte count the
    handler would read off disk, and nothing has to be written anywhere to learn it.
    """
    identity: dict[str, int] = {}
    gzipped: dict[str, int] = {}
    with zipfile.ZipFile(path) as archive:
        for info in archive.infolist():
            if info.is_dir() or not info.filename.startswith(ARTEFACT_WEB_PREFIX):
                continue
            relative = info.filename[len(ARTEFACT_WEB_PREFIX) :]
            if relative.endswith(GZ_SUFFIX):
                gzipped[relative[: -len(GZ_SUFFIX)]] = info.file_size
            else:
                identity[relative] = info.file_size
    return identity, gzipped


def family_bounds(args: argparse.Namespace, root: Path) -> list[Check]:
    source = Path(args.static_site) if args.static_site else root / DEFAULT_STATIC_SITE
    expression, value, note = _ceiling_from_source(source)
    checks = [
        _check(
            "BOUNDS",
            "ceiling_constant",
            expression == CEILING_EXPRESSION and value == CEILING_BYTES,
            f"{CEILING_EXPRESSION} == {CEILING_BYTES}",
            f"{expression} == {value}",
            f"{note} — the number Lambda's payload limit leaves after base64, not a preference",
        )
    ]

    artefact = Path(args.artefact) if args.artefact else root / DEFAULT_ARTEFACT
    ceiling = value if value is not None else CEILING_BYTES
    if not artefact.is_file():
        why = (
            f"no built artefact at {artefact}; run scripts/deploy/build_lambda.ps1. "
            "console/dist is NOT a substitute — it has source maps and no .gz siblings"
        )
        return [*checks, _skip("BOUNDS", "straddle", why), _skip("BOUNDS", "one_refusal", why)]

    identity, gzipped = _artefact_web(artefact)
    if not identity:
        why = f"{artefact} carries no web/ entries"
        return [*checks, _skip("BOUNDS", "straddle", why), _skip("BOUNDS", "one_refusal", why)]

    # What the wire actually carries for each object: the gzipped sibling when there is
    # one, the object itself when there is not.
    served = {name: gzipped.get(name, size) for name, size in identity.items()}
    largest_served_name = max(served, key=lambda k: served[k])
    largest_served = served[largest_served_name]
    largest_identity_name = max(identity, key=lambda k: identity[k])
    largest_identity = identity[largest_identity_name]
    refused = sorted(name for name, size in identity.items() if size > ceiling)

    checks.append(
        _check(
            "BOUNDS",
            "straddle",
            largest_served < ceiling < largest_identity,
            f"largest_served < {ceiling} < largest_identity",
            f"{largest_served} < {ceiling} < {largest_identity}",
            f"{largest_served_name} gzipped · {largest_identity_name} identity · "
            f"{len(identity)} objects, {len(gzipped)} siblings",
            largest_served=largest_served,
            largest_served_object=largest_served_name,
            largest_identity=largest_identity,
            largest_identity_object=largest_identity_name,
            artefact=str(artefact),
        )
    )
    checks.append(
        _check(
            "BOUNDS",
            "one_refusal",
            len(refused) == 1,
            "exactly 1 identity object above the ceiling",
            f"{len(refused)}: {', '.join(refused) or '(none)'}",
            "one 413 is the measurement; zero means the ceiling stopped binding and two "
            "means an object grew past it",
            refused=refused,
        )
    )
    return checks


# ═════════════════════════════════════════════════════════════════════════════════════
# PRIVILEGES
# ═════════════════════════════════════════════════════════════════════════════════════


def extract_requirements(src: Path) -> dict[str, set[str]]:
    """``{"mainline.permit": {"SELECT", "UPDATE"}, …}`` — what the code needs, by verb."""
    required: dict[str, set[str]] = {}
    for module in sorted(src.rglob("*.py")):
        try:
            literals = _sql_literals(module.read_text(encoding="utf-8"))
        except (OSError, SyntaxError):
            continue
        for literal in literals:
            for privilege, pattern in SQL_VERBS:
                for match in pattern.finditer(literal):
                    required.setdefault(match.group(1).lower(), set()).add(privilege)
    return required


def gate_chain_reads(path: Path) -> list[str]:
    """``cloud_roles.API_GATE_READ``, read out of the file rather than restated here.

    That list was discovered by running the deployment and parsing ``42501`` one HTTP
    request at a time. Restating it would let the copy and the original drift, and the
    drift would be invisible until the next outage.
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return []
    for node in ast.walk(tree):
        targets = [node.target] if isinstance(node, ast.AnnAssign) else getattr(node, "targets", [])
        if not isinstance(node, ast.Assign | ast.AnnAssign) or node.value is None:
            continue
        if any(isinstance(t, ast.Name) and t.id == "API_GATE_READ" for t in targets):
            try:
                value = ast.literal_eval(node.value)
            except ValueError:
                return []
            return [str(v).lower() for v in value]
    return []


def family_privileges(  # noqa: PLR0911, PLR0912, PLR0915 - every early return is a NAMED
    # refusal that must skip or fail all five checks together, and every branch is one of
    # the four traps in the docstring. Splitting it would put the trap and its reason in
    # different files, which is how the false positives got written in the first place.
    args: argparse.Namespace,
    root: Path,
) -> list[Check]:
    names = (
        "references_resolve",
        "relations",
        "routines",
        "routine_signature_normalised",
        "gate_chain",
    )
    if not args.cloud:
        return [
            _skip("PRIVILEGES", n, "--no-cloud: nothing asked the cluster what the role holds")
            for n in names
        ]

    try:
        import psycopg
    except ImportError as exc:  # pragma: no cover - psycopg is a hard dependency here
        return [_skip("PRIVILEGES", n, f"psycopg is not importable: {exc}") for n in names]

    dsn, why = _seed_dsn(args, root)
    if dsn is None:
        return [_skip("PRIVILEGES", n, why) for n in names]

    src = Path(args.api_src) if args.api_src else root / DEFAULT_API_SRC
    required = extract_requirements(src)
    if not required:
        return [
            Check(
                "PRIVILEGES",
                n,
                FAIL,
                "a non-empty reference set",
                "0 objects",
                f"no SQL references extracted from {src} — the extractor found nothing, "
                "which is a defect in the guard or a moved package, never a clean tree",
            )
            for n in names
        ]

    role = args.role
    gate_source = Path(args.cloud_roles) if args.cloud_roles else root / CLOUD_ROLES
    gate_tables = gate_chain_reads(gate_source)
    unresolved: list[str] = []
    relation_denied: list[str] = []
    routine_denied: list[str] = []
    routine_rows: dict[str, tuple[int, str, str]] = {}
    routine_grantees: dict[str, set[str]] = {}
    reachable_as: set[str] = set()
    trigger_routines: list[str] = []
    audit_views: list[str] = []
    grants_spelling: dict[str, str] = {}
    catalogue_spelling: dict[str, str] = {}
    gate_denied: list[str] = []

    try:
        with psycopg.connect(dsn, connect_timeout=args.db_timeout, autocommit=True) as conn:
            selected = conn.execute("SELECT current_database()").fetchone()[0]
            if selected != args.database:
                return [
                    Check(
                        "PRIVILEGES",
                        n,
                        FAIL,
                        args.database,
                        selected,
                        "the server selected a different database; every privilege answer "
                        "below would have been about the wrong one",
                    )
                    for n in names
                ]
            for row in conn.execute(
                "SELECT n.nspname || '.' || p.proname, p.oid, p.prokind, "
                "pg_get_function_identity_arguments(p.oid) "
                "FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
                "WHERE n.nspname = ANY(%s)",
                (list(SCHEMAS),),
            ).fetchall():
                routine_rows[str(row[0]).lower()] = (int(row[1]), str(row[2]), str(row[3]))
            trigger_routines = [
                f"{r[0]}.{r[1]}".lower()
                for r in conn.execute(
                    "SELECT routine_schema, routine_name FROM information_schema.routines "
                    "WHERE routine_schema = ANY(%s) AND data_type = 'trigger'",
                    (list(SCHEMAS),),
                ).fetchall()
            ]
            audit_views = [
                f"{AUDIT_SCHEMA}.{r[0]}".lower()
                for r in conn.execute(
                    "SELECT table_name FROM information_schema.views WHERE table_schema = %s",
                    (AUDIT_SCHEMA,),
                ).fetchall()
            ]
            # `information_schema.routines` gives the BARE name; `SHOW GRANTS` gives the
            # full signature. Both spellings are captured so the normalisation below is
            # demonstrated against live output rather than asserted.
            catalogue_spelling = {
                f"{r[0]}.{r[1]}".lower(): str(r[1])
                for r in conn.execute(
                    "SELECT routine_schema, routine_name FROM information_schema.routines "
                    "WHERE routine_schema = ANY(%s)",
                    (list(SCHEMAS),),
                ).fetchall()
            }
            # ── THE ROUTINE GRANT, READ RATHER THAN ASKED ────────────────────────────
            # `has_function_privilege` is NOT used here, and the reason is measured, not
            # stylistic. On CockroachDB v26.2.5 it is a stub that returns TRUE for every
            # (role, routine) pair — verified against a scratch database where EXECUTE had
            # been revoked from `public` and the behavioural truth was `42501 user
            # w_rg_probe does not have EXECUTE privilege on procedure merge_permit` while
            # `has_function_privilege` still answered `true`, for that role, for `public`,
            # for anybody. A check built on it cannot fail, and a check that cannot fail is
            # decoration. (`has_table_privilege` was put through the same control on the
            # same database and tracks the behaviour exactly, which is why it IS trusted
            # for relations.)
            #
            # So routine EXECUTE is decided from `SHOW GRANTS`, which is real — at the cost
            # of doing by hand the two things the built-in would have done: stripping the
            # signature off the object name, and expanding role membership.
            for row in conn.execute("SHOW GRANTS").fetchall():
                if row[3] != "routine":
                    continue
                bare = str(row[2]).split("(")[0]
                key = f"{row[1]}.{bare}".lower()
                if str(row[5]).upper() in {"EXECUTE", "ALL"}:
                    routine_grantees.setdefault(key, set()).add(str(row[4]))
                if str(row[4]) == role:
                    grants_spelling[key] = str(row[2])

            # Every identity the role can act as. `SHOW GRANTS` lists only DIRECT grants,
            # so without this expansion a routine granted to `agent_gate` would read as
            # denied to `mainline_api`, which is a member of it.
            reachable_as = {role, "public"}
            frontier = [role]
            while frontier:
                current = frontier.pop()
                for row in conn.execute(f"SHOW GRANTS ON ROLE FOR {current}").fetchall():
                    parent = str(row[0])
                    if parent not in reachable_as:
                        reachable_as.add(parent)
                        frontier.append(parent)

            def _table_privilege(obj: str, privilege: str) -> bool | None:
                try:
                    return bool(
                        conn.execute(
                            "SELECT has_table_privilege(%s::STRING, %s::STRING, %s::STRING)",
                            (role, obj, privilege),
                        ).fetchone()[0]
                    )
                except psycopg.Error:
                    return None

            for obj in sorted(required):
                for privilege in sorted(required[obj]):
                    if privilege == "EXECUTE":
                        row = routine_rows.get(obj)
                        if row is None:
                            unresolved.append(f"{obj} (routine, EXECUTE)")
                            continue
                        if obj in trigger_routines:
                            continue  # a trigger function needs no grant to the caller
                        if not (routine_grantees.get(obj, set()) & reachable_as):
                            holders = sorted(routine_grantees.get(obj, set())) or ["(nobody)"]
                            routine_denied.append(
                                f"{obj} EXECUTE — held by {', '.join(holders)}; "
                                f"{role} acts as {', '.join(sorted(reachable_as))}"
                            )
                        continue
                    held = _table_privilege(obj, privilege)
                    if held is None:
                        unresolved.append(f"{obj} ({privilege})")
                    elif not held:
                        relation_denied.append(f"{obj} {privilege}")
            for view in audit_views:
                held = _table_privilege(view, "SELECT")
                if held is None:
                    unresolved.append(f"{view} (SELECT, catalogue-driven)")
                elif not held:
                    relation_denied.append(f"{view} SELECT")
            for table in gate_tables:
                held = _table_privilege(table, "SELECT")
                if held is None or not held:
                    gate_denied.append(f"{table} SELECT")
    except psycopg.Error as exc:
        return [
            Check(
                "PRIVILEGES",
                n,
                FAIL,
                "a reachable cluster",
                "unreachable",
                f"[{exc.sqlstate or '-----'}] {' '.join(str(exc).split())[:200]}",
            )
            for n in names
        ]

    required_routines = sorted(
        obj for obj in required if "EXECUTE" in required[obj] and obj not in trigger_routines
    )
    normalised = [
        r
        for r in required_routines
        if "(" in grants_spelling.get(r, "") and "(" not in catalogue_spelling.get(r, "(")
    ]

    return [
        _check(
            "PRIVILEGES",
            "references_resolve",
            not unresolved,
            "every referenced object resolves in the catalogue",
            f"{len(unresolved)} unresolved",
            "; ".join(unresolved[:6]) or f"{len(required)} objects from {src.name}/**",
            unresolved=unresolved,
            objects=len(required),
        ),
        _check(
            "PRIVILEGES",
            "relations",
            not relation_denied,
            f"{role} reaches every relation the code reads or writes",
            f"{len(relation_denied)} shortfall(s)",
            "; ".join(relation_denied[:6])
            or f"{len(required)} objects + {len(audit_views)} {AUDIT_SCHEMA} views, "
            f"membership-resolved via has_table_privilege",
            denied=relation_denied,
            audit_views=len(audit_views),
        ),
        _check(
            "PRIVILEGES",
            "routines",
            not routine_denied,
            f"{role} may EXECUTE every non-trigger routine the code CALLs",
            f"{len(routine_denied)} shortfall(s)",
            "; ".join(routine_denied[:6])
            or f"{len(required_routines)} routine(s) via SHOW GRANTS (has_function_privilege "
            f"is a stub here); {len(trigger_routines)} trigger functions excluded",
            denied=routine_denied,
            routines=required_routines,
            reachable_as=sorted(reachable_as),
        ),
        _check(
            "PRIVILEGES",
            "routine_signature_normalised",
            bool(required_routines) and len(normalised) == len(required_routines),
            f"{len(required_routines)} routine(s) matched across both spellings",
            f"{len(normalised)} matched",
            "SHOW GRANTS spells a routine with its signature and information_schema does "
            "not; this check fails if that trap stops being exercised",
            show_grants=grants_spelling,
            information_schema=catalogue_spelling
            and {r: catalogue_spelling.get(r) for r in required_routines},
        ),
        _check(
            "PRIVILEGES",
            "gate_chain",
            not gate_denied,
            f"{role} reads every table merge_permit's triggers touch",
            f"{len(gate_denied)} shortfall(s)",
            "; ".join(gate_denied[:6])
            or f"{len(gate_tables)} tables from {gate_source.name}:API_GATE_READ",
            denied=gate_denied,
            source=str(gate_source),
        ),
    ]


# ═════════════════════════════════════════════════════════════════════════════════════
# LIVE
# ═════════════════════════════════════════════════════════════════════════════════════


def family_live(args: argparse.Namespace) -> list[Check]:
    names = ("health_ok", "deploy_chain_applied", "gate_run_verdict", "gate_run_beats")
    if not args.live:
        return [
            _skip("LIVE", n, f"--no-live: {args.base_url} was never asked", e)
            for n, e in zip(
                names, ("ok=true", DEPLOY_CHAIN_APPLIED, "PROVEN", "4 beats matched"), strict=True
            )
        ]

    base = args.base_url.rstrip("/")
    try:
        health = _http_json(f"{base}/v1/health", timeout=args.http_timeout)
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
        why = f"{type(exc).__name__}: {' '.join(str(exc).split())[:160]}"
        return [
            Check("LIVE", n, FAIL, str(e), "unreachable", f"GET {base}/v1/health — {why}")
            for n, e in zip(
                names, ("ok=true", DEPLOY_CHAIN_APPLIED, "PROVEN", "4 beats matched"), strict=True
            )
        ]

    checks = [
        _check(
            "LIVE",
            "health_ok",
            health.get("ok") is True,
            "ok=true",
            f"ok={health.get('ok')}",
            f"GET {base}/v1/health · {health.get('database')}",
        ),
        _check(
            "LIVE",
            "deploy_chain_applied",
            health.get("deploy_chain_applied") == DEPLOY_CHAIN_APPLIED,
            DEPLOY_CHAIN_APPLIED,
            health.get("deploy_chain_applied"),
            f"of {health.get('deploy_chain_files')} files · fingerprint "
            f"{str(health.get('schema_fingerprint'))[:16]}…",
        ),
    ]

    try:
        envelope = _http_json(
            f"{base}/v1/demo/gate-run", method="POST", body=b"{}", timeout=args.http_timeout
        )
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
        why = f"{type(exc).__name__}: {' '.join(str(exc).split())[:160]}"
        return [
            *checks,
            Check("LIVE", "gate_run_verdict", FAIL, "PROVEN", "unreachable", why),
            Check("LIVE", "gate_run_beats", FAIL, "4 beats matched", "unreachable", why),
        ]

    # The console's read envelope wraps every resource; the run itself is `data`.
    payload = envelope.get("data") if isinstance(envelope.get("data"), dict) else envelope
    beats = payload.get("beats") or []
    mismatched: list[str] = []
    for ordinal, name, outcome, sqlstate, exhibit, exhibit_source in LIVE_BEATS:
        beat = next((b for b in beats if b.get("ordinal") == ordinal), None)
        if beat is None:
            mismatched.append(f"beat {ordinal} ({name}) absent")
            continue
        for label, want, got in (
            ("name", name, beat.get("name")),
            ("outcome", outcome, beat.get("outcome")),
            ("sqlstate", sqlstate, beat.get("sqlstate")),
            ("exhibit", exhibit, beat.get("constraint")),
            ("exhibit_source", exhibit_source, beat.get("constraint_source")),
            ("matched_expectation", True, beat.get("matched_expectation")),
        ):
            if want is not None and got != want:
                mismatched.append(f"beat {ordinal} {label}: expected {want!r}, observed {got!r}")

    return [
        *checks,
        _check(
            "LIVE",
            "gate_run_verdict",
            payload.get("verdict") == "PROVEN",
            "PROVEN",
            payload.get("verdict"),
            f"POST {base}/v1/demo/gate-run · run {payload.get('run_id')}",
            failures=payload.get("failures") or [],
        ),
        _check(
            "LIVE",
            "gate_run_beats",
            not mismatched and len(beats) == len(LIVE_BEATS),
            f"{len(LIVE_BEATS)} beats matched by outcome, sqlstate, exhibit and source",
            f"{len(beats)} beats, {len(mismatched)} mismatch(es)",
            "; ".join(mismatched[:6]) or "beat 2 reports its exhibit, beat 3 parses it",
            mismatched=mismatched,
        ),
    ]


# ═════════════════════════════════════════════════════════════════════════════════════
# SEED SHAPE
# ═════════════════════════════════════════════════════════════════════════════════════


def _seed_dsn(args: argparse.Namespace, root: Path) -> tuple[str | None, str]:
    """The cloud DSN with ``mainline_demo`` substituted for ``defaultdb``. Never printed."""
    if args.seed_dsn:
        return with_database(args.seed_dsn, args.database), "--seed-dsn"
    env_file = Path(args.env_file) if Path(args.env_file).is_absolute() else root / args.env_file
    if not env_file.is_file():
        return None, f"no {env_file}; the cloud DSN is read from a file and is never an argument"
    values = read_env_file(env_file)
    dsn = values.get(args.dsn_key)
    if not dsn:
        return None, f"{env_file} carries no {args.dsn_key}"
    return with_database(dsn, args.database), f"{args.dsn_key} from {env_file.name}"


def family_seed(args: argparse.Namespace, root: Path) -> list[Check]:
    names = (
        "database_selected",
        "defeater_option",
        "vocabulary_is_one_per_check",
        "ledger_leaf",
        "ledger_node",
        "checkpoint_tree_size",
        "core_counts",
    )
    if not args.cloud:
        return [_skip("SEED", n, "--no-cloud: the seeded database was never read") for n in names]
    try:
        import psycopg
    except ImportError as exc:  # pragma: no cover
        return [_skip("SEED", n, f"psycopg is not importable: {exc}") for n in names]

    dsn, how = _seed_dsn(args, root)
    if dsn is None:
        return [_skip("SEED", n, how) for n in names]

    try:
        with psycopg.connect(dsn, connect_timeout=args.db_timeout, autocommit=True) as conn:
            conn.read_only = True
            selected = conn.execute("SELECT current_database()").fetchone()[0]
            selection = _check(
                "SEED",
                "database_selected",
                selected == args.database,
                args.database,
                selected,
                f"{how} → substituted by name and confirmed with SELECT current_database(); "
                "the DSN's own path segment is defaultdb and is never trusted",
                dsn=redact_dsn(dsn),
            )
            if selected != args.database:
                return [
                    selection,
                    *[
                        _skip("SEED", n, f"counted nothing: the server selected {selected!r}")
                        for n in names[1:]
                    ],
                ]

            rows, checks_seen, distinct = conn.execute(
                "SELECT count(*), count(DISTINCT check_id), "
                "count(DISTINCT (check_id, vocab_sha256)) FROM mainline.defeater_option"
            ).fetchone()
            offenders = conn.execute(
                "SELECT check_id::STRING, count(DISTINCT vocab_sha256) "
                "FROM mainline.defeater_option GROUP BY 1 HAVING count(DISTINCT vocab_sha256) <> 1"
            ).fetchall()
            leaves, nodes = conn.execute(
                "SELECT (SELECT count(*) FROM mainline.ledger_leaf), "
                "(SELECT count(*) FROM mainline.ledger_node)"
            ).fetchone()
            checkpoints = conn.execute(
                "SELECT c.site_code, max(c.tree_size), "
                "(SELECT count(*) FROM mainline.ledger_leaf l WHERE l.site_code = c.site_code) "
                "FROM mainline.ledger_checkpoint c GROUP BY c.site_code ORDER BY 1"
            ).fetchall()
            counts = {
                table: int(
                    conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]  # noqa: S608
                )
                for table in SEED_COUNTS
            }
    except psycopg.Error as exc:
        return [
            Check(
                "SEED",
                n,
                FAIL,
                "a reachable seeded database",
                "unreadable",
                f"[{exc.sqlstate or '-----'}] {' '.join(str(exc).split())[:200]}",
            )
            for n in names
        ]

    inconsistent = [
        f"{c[0]}: tree_size {c[1]} vs {c[2]} leaves" for c in checkpoints if c[1] != c[2]
    ]
    drift = {t: (SEED_COUNTS[t], counts[t]) for t in SEED_COUNTS if SEED_COUNTS[t] != counts[t]}

    return [
        selection,
        _check(
            "SEED",
            "defeater_option",
            int(rows) == SEED_DEFEATER_ROWS and int(checks_seen) == SEED_DEFEATER_CHECKS,
            f"{SEED_DEFEATER_ROWS} rows across {SEED_DEFEATER_CHECKS} checks",
            f"{rows} rows across {checks_seen} checks",
            "beat 4 signs the digest of the option set it was shown; a check offering "
            "nothing cannot be signed at all",
        ),
        _check(
            "SEED",
            "vocabulary_is_one_per_check",
            not offenders and int(distinct) == int(checks_seen),
            "1 distinct vocab_sha256 per check",
            f"{distinct} (check, digest) pairs over {checks_seen} checks",
            "; ".join(f"{o[0]} has {o[1]}" for o in offenders)
            or "0064: one generation, one digest",
        ),
        _check(
            "SEED",
            "ledger_leaf",
            int(leaves) == SEED_COUNTS["mainline.ledger_leaf"],
            SEED_COUNTS["mainline.ledger_leaf"],
            leaves,
            "mainline.ledger_leaf",
        ),
        _check(
            "SEED",
            "ledger_node",
            int(nodes) == SEED_COUNTS["mainline.ledger_node"],
            SEED_COUNTS["mainline.ledger_node"],
            nodes,
            "mainline.ledger_node",
        ),
        _check(
            "SEED",
            "checkpoint_tree_size",
            not inconsistent,
            "max(tree_size) == leaves committed, per site",
            "; ".join(inconsistent) or f"{len(checkpoints)} site(s) consistent",
            "a checkpoint whose tree_size outruns its leaves commits to a tree that is not there",
            checkpoints=[[c[0], int(c[1]), int(c[2])] for c in checkpoints],
        ),
        _check(
            "SEED",
            "core_counts",
            not drift,
            {
                t: SEED_COUNTS[t]
                for t in (
                    "mainline.permit",
                    "mainline.blocking_check",
                    "mainline.signing_credential",
                )
            },
            {
                t: counts[t]
                for t in (
                    "mainline.permit",
                    "mainline.blocking_check",
                    "mainline.signing_credential",
                )
            },
            "; ".join(f"{t}: expected {e}, observed {o}" for t, (e, o) in drift.items())
            or "permit, obligations and enrolled credentials",
            drift=drift,
            counts=counts,
        ),
    ]


# ═════════════════════════════════════════════════════════════════════════════════════
# the report
# ═════════════════════════════════════════════════════════════════════════════════════


#: The terminal is not the evidence file. `--json` is written as UTF-8 and keeps the
#: typography; stdout on a Windows console is whatever code page that console has, and a
#: guard that raises `UnicodeEncodeError` while reporting a regression has buried the
#: finding under its own stack trace. Folded at the print boundary only.
_ASCII = str.maketrans(
    {
        "—": "-",  # em dash
        "–": "-",  # noqa: RUF001 - the ambiguity IS the entry: this is what it maps away
        "·": "|",  # middle dot
        "…": "...",
        "→": "->",
    }
)


def _ascii(text: str) -> str:
    return text.translate(_ASCII).encode("ascii", "replace").decode("ascii")


def render(checks: list[Check]) -> None:
    width_family = max((len(c.family) for c in checks), default=6)
    width_name = max((len(c.name) for c in checks), default=10)
    last = ""
    for check in checks:
        if check.family != last:
            print()
            last = check.family
        expected = _ascii(check.expected)
        observed = _ascii(check.observed)
        expected = expected if len(expected) <= 46 else expected[:45] + "~"
        observed = observed if len(observed) <= 46 else observed[:45] + "~"
        print(
            f"{check.family:<{width_family}}  {check.name:<{width_name}}  {check.status:<4}  "
            f"expected {expected:<46}  observed {observed}"
        )
        if check.detail and check.status != PASS:
            print(f"{'':<{width_family}}  {'':<{width_name}}        ! {_ascii(check.detail)}")


def verdict_line(checks: list[Check]) -> tuple[str, int]:
    passed = sum(1 for c in checks if c.status == PASS)
    failed = [c for c in checks if c.status == FAIL]
    skipped = [c for c in checks if c.status == SKIP]
    families = sorted({c.family for c in failed})
    if failed:
        return (
            f"VERDICT  REGRESSION — {len(failed)} of {len(checks)} checks FAILED in "
            f"{', '.join(families)} ({passed} PASS, {len(skipped)} SKIP)"
        ), EXIT_RED
    if skipped:
        # NOT "GREEN". A skip is a question nobody asked, and calling it green is the
        # exact move that lets a suite assert nothing while looking healthy.
        return (
            f"VERDICT  NO REGRESSION FOUND, {len(skipped)} of {len(checks)} checks NOT RUN "
            f"— {', '.join(sorted({c.family for c in skipped}))} were skipped, not passed"
        ), EXIT_GREEN
    return f"VERDICT  GREEN — all {len(checks)} checks hold", EXIT_GREEN


def main(argv: list[str] | None = None) -> int:  # noqa: PLR0915 - one add_argument per
    # seam, and every seam is either a flag the brief asks for or the hook a falsification
    # needed. Hiding them behind a builder would hide which flags exist to be planted with.
    root = _repo_root()
    parser = argparse.ArgumentParser(
        prog="regression_guard",
        description="Re-verify every claim this repository currently makes. One command.",
    )
    parser.add_argument(
        "--live",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="ask the deployed demo over HTTP (default: yes)",
    )
    parser.add_argument(
        "--cloud",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="ask CockroachDB Cloud for grants and seed shape (default: yes)",
    )
    parser.add_argument("--json", dest="json_path", default=None, help="write the full record here")
    parser.add_argument(
        "--only",
        default=None,
        help=f"comma-separated families to run; any of {', '.join(FAMILIES)}",
    )
    parser.add_argument(
        "--dsn",
        default=os.environ.get("MAINLINE_TEST_DSN")
        or os.environ.get("TRAPPOINT_DSN")
        or os.environ.get("COCKROACH_URL")
        or os.environ.get("CRDB_URL")
        or "postgresql://root@127.0.0.1:26257/defaultdb?sslmode=disable",
        help="admin DSN for the LOCAL cluster the kernel proof builds its database on",
    )
    parser.add_argument(
        "--kernel-database",
        default="w_regression_guard",
        help="throwaway database for the kernel proof (dropped by the proof)",
    )
    parser.add_argument("--kernel-script", default=None, help="path to gate_refusal.py")
    parser.add_argument(
        "--kernel-evidence",
        default=None,
        help="read this gate-refusal evidence file instead of re-running the proof",
    )
    parser.add_argument("--kernel-timeout", type=float, default=900.0)
    parser.add_argument(
        "--junit", default=None, help="read this junit XML instead of running the suites"
    )
    parser.add_argument("--suite-out", default=None, help="where to write the junit XML")
    parser.add_argument(
        "--suite-timeout",
        type=int,
        default=900,
        help="pytest-timeout per test; the demo-api fixtures build a chain",
    )
    parser.add_argument("--suite-wall-timeout", type=float, default=3600.0)
    parser.add_argument("--artefact", default=None, help="the built Lambda zip")
    parser.add_argument("--static-site", default=None, help="the module holding the ceiling")
    parser.add_argument("--api-src", default=None, help="the demo-api package to extract SQL from")
    parser.add_argument(
        "--role",
        default=API_ROLE,
        help="the login whose reach is compared against what the code needs",
    )
    parser.add_argument(
        "--cloud-roles",
        default=None,
        help="the module carrying API_GATE_READ (default: cloud_roles.py)",
    )
    parser.add_argument("--base-url", default=os.environ.get("MAINLINE_DEMO_URL", DEFAULT_BASE_URL))
    parser.add_argument("--http-timeout", type=float, default=60.0)
    parser.add_argument("--env-file", default=str(SEED_ENV_FILE))
    parser.add_argument("--dsn-key", default=SEED_DSN_KEY)
    parser.add_argument("--database", default=SEED_DATABASE)
    parser.add_argument(
        "--seed-dsn",
        default=None,
        help="an explicit DSN for the seeded database, bypassing --env-file",
    )
    parser.add_argument("--db-timeout", type=float, default=45.0)
    args = parser.parse_args(argv)

    selected = FAMILIES
    if args.only:
        selected = tuple(f.strip().upper() for f in args.only.split(",") if f.strip())
        unknown = [f for f in selected if f not in FAMILIES]
        if unknown:
            print(f"regression_guard: unknown family {', '.join(unknown)}", file=sys.stderr)
            return EXIT_USAGE

    started = datetime.now(UTC)
    checks: list[Check] = []
    for family in FAMILIES:
        if family not in selected:
            continue
        if family == "KERNEL":
            checks.extend(family_kernel(args, root))
        elif family == "SUITES":
            checks.extend(family_suites(args, root))
        elif family == "BOUNDS":
            checks.extend(family_bounds(args, root))
        elif family == "PRIVILEGES":
            checks.extend(family_privileges(args, root))
        elif family == "LIVE":
            checks.extend(family_live(args))
        elif family == "SEED":
            checks.extend(family_seed(args, root))

    render(checks)
    line, code = verdict_line(checks)
    print()
    print(_ascii(line))

    if args.json_path:
        document = {
            "artefact": "MAINLINE regression guard",
            "generated_at_utc": started.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "generated_by": "scripts/qa/regression_guard.py",
            "seconds": round((datetime.now(UTC) - started).total_seconds(), 3),
            "families": list(selected),
            "live": bool(args.live),
            "cloud": bool(args.cloud),
            "totals": {
                "checks": len(checks),
                "pass": sum(1 for c in checks if c.status == PASS),
                "fail": sum(1 for c in checks if c.status == FAIL),
                "skip": sum(1 for c in checks if c.status == SKIP),
            },
            "verdict": line.removeprefix("VERDICT").strip(),
            "checks": [c.as_json() for c in checks],
        }
        out = Path(args.json_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(document, indent=2, default=str) + "\n", encoding="utf-8")
        out.with_suffix(out.suffix + ".license").write_text(
            "SPDX-FileCopyrightText: 2026 MAINLINE contributors\n"
            "SPDX-License-Identifier: CC-BY-4.0\n",
            encoding="utf-8",
        )
        print(f"json     {out}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
