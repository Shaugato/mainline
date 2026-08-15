#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
#
# MI: none — this program makes no database claim of its own. Every value it prints was
#     produced by `scripts/deploy/seed_demo.py`, by the deployed API, or by one of two
#     SELECTs that no other program in this repository runs. It asserts; it never computes.
"""Answer one question before the camera rolls: *is the world still the world we filmed?*

WHY THIS EXISTS
---------------
A retake should cost ten seconds, not ten minutes. It does — but only if somebody can tell,
quickly and without judgement, that the seeded world is exactly as the last take left it.
That is a question with eight parts, and answering it by eye means opening a browser, a psql
session and two documents. This program asks all eight, prints one PASS/FAIL line each, and
ends in a verdict.

**IT IS A VERIFIER FIRST AND A REPAIRER SECOND, AND THE ORDER IS A CLAIM WE MAKE.**
``docs/demo/proof-and-polish-plan.md`` §R1: ``POST /v1/demo/gate-run`` ends in ``ROLLBACK``
(``docs/deploy/gate-run-contract.md`` §2) and ``docs/deploy/cloud-database.md`` §6 measured
that a full rollback leaves the seeded row untouched — *"No per-visitor state, no reset
button, no cleanup sweeper."* So there is nothing to reset. ``--check`` is the default, it is
read-only, and the eighth fact it checks is that this very run changed nothing, read back out
of the database rather than asserted in a comment.

WHAT IT DOES NOT DO
-------------------
It reimplements nothing. Every fact comes from a primitive that already existed:

* the deployment is asked over HTTP — ``GET /v1/health``, ``GET /v1/demo/subjects``,
  ``GET /v1/permits/{permit_id}/blocking-checks``, ``GET /v1/change-requests/{cr_id}`` and
  the one permitted ``POST /v1/demo/gate-run`` (plan §R4). No other wire traffic, ever.
* a local database is asked through ``scripts/deploy/seed_demo.py``: its parser builds the
  arguments, its :func:`run` produces the evidence, and this file reads that evidence. There
  is no second census, no second merge probe and no second opinion about what "seeded" means.
  If those two programs ever disagreed, the film would narrate a state the proof does not
  make.
* the two facts ``seed_demo`` does not carry — *which* signing subjects are enrolled, and
  whether the change request is still gated — are two SELECTs, and they are the only SQL in
  this file.

THE TWO TARGETS, AND WHY THE DEPLOYMENT IS NEVER REACHED BY DSN
---------------------------------------------------------------
``demo_ready.py`` with no arguments checks the DEPLOYMENT, over HTTP. ``--dsn`` checks a
LOCAL database, over psycopg. The deployment is never opened as a database: the only traffic
this wave is permitted to put on the wire to it is read-only ``GET``s and the one
``gate-run`` POST, and a psycopg connection is neither.

``--repair`` therefore exists for the local database alone. Pointed at ``mainline_demo`` —
the name the deployment and its local mirror share — it refuses to write, prints the exact
command the orchestrator runs, and exits ``3``. Three rather than one, because *"a human must
act"* and *"the gate did not refuse"* are different findings and only one of them is about
the product.

EXIT CODES
----------
* ``0`` — READY. Every fact passed. Roll camera.
* ``1`` — NOT READY. At least one fact failed; the line that failed says which and why.
* ``2`` — USAGE. No target, no cluster, no route to the deployment. Nothing was measured.
* ``3`` — ACTION REQUIRED. A write was asked for against a target this program will not
  write to. Nothing was measured and nothing was written; the command a human must run is
  printed.

Usage::

    .venv/Scripts/python.exe scripts/demo/demo_ready.py
    .venv/Scripts/python.exe scripts/demo/demo_ready.py --url https://…on.aws
    .venv/Scripts/python.exe scripts/demo/demo_ready.py \\
        --dsn postgresql://root@127.0.0.1:26257/w_p1?sslmode=disable
    .venv/Scripts/python.exe scripts/demo/demo_ready.py \\
        --dsn postgresql://root@127.0.0.1:26257/w_p1?sslmode=disable --repair

``127.0.0.1`` rather than ``localhost``, and it is not a preference. Measured on this machine
on 2026-08-16 against the node this project documents: **0.01 s** to ``127.0.0.1`` and
**130.06 s** to ``localhost``, which resolves to ``::1`` first and gets no answer there. This
command opens three connections. It says so on stderr when it happens and it does not rewrite
anybody's DSN — see :func:`_slow_host_note`.

STDOUT IS DETERMINISTIC AND STDERR IS NOT, ON PURPOSE
------------------------------------------------------
Two runs against an unchanged world print byte-identical stdout — that is what makes
"nothing moved" checkable by ``diff`` rather than by reading. Nothing that varies between two
identical runs is allowed on stdout: no timestamp, no elapsed millisecond, no ``run_id``.
Those go to stderr, where the elapsed total is reported against its ten-second bound, and
where any output from ``seed_demo`` is passed through verbatim.
"""

from __future__ import annotations

import argparse
import contextlib
import http.client
import io
import json
import ssl
import sys
import textwrap
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

# Run as a module (`python -m scripts.demo.demo_ready`) or as a path
# (`python scripts/demo/demo_ready.py`). The second form gives Python `scripts/demo` as
# sys.path[0] and no package context, so the sibling imports below would fail — and the
# second form is how an operator invokes it on a machine where `uv` is not installed. Same
# two lines, same reason, as `scripts/deploy/seed_demo.py`.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

REPO_ROOT = Path(__file__).resolve().parents[2]

EXIT_OK = 0
EXIT_NOT_READY = 1
EXIT_USAGE = 2
EXIT_ACTION_REQUIRED = 3

#: The deployed Function URL. A host name, not an identifier; the same constant, spelled the
#: same way, as `scripts/demo/capture_memory_loop.py:67`. `--url` overrides it.
DEFAULT_BASE = "https://ihuuyvm4z6nfuktihnkey77fpy0eyrhj.lambda-url.ap-southeast-1.on.aws"

#: The command the ORCHESTRATOR runs to put the demo world into the deployed database. This
#: program never runs it against anything but a local database, and prints it verbatim when a
#: human has to. Plan §R2.
ORCHESTRATOR_SEED_COMMAND = ".venv/Scripts/python.exe scripts/deploy/seed_demo.py"

#: The identifiers the seed files fix, restated here so this program can be read on its own.
#: `tests/demo/test_demo_ready.py` asserts each one against its source — PERMIT_ID and
#: CHECK_ID against `scripts/deploy/seed_demo.py`, CR_ID against `demo_world.sql` — so a
#: drift between this file and the seed is a test failure and not a silent mismatch. They are
#: EXPECTATIONS, never addressing: every request below is addressed with the identifier
#: `GET /v1/demo/subjects` handed back, and these constants are what that answer is checked
#: against.
PERMIT_ID = "dec0de00-0006-4000-8000-000000000001"
CHECK_ID = "dec0de00-0007-4000-8000-000000000001"
CR_ID = "dec0de00-000c-4000-8000-000000000001"

#: The permit's and the change request's own external references, and the precursor's.
#: Checked as well as the UUIDs because a judge reads these on screen and a UUID is not what
#: anybody remembers.
PERMIT_EXTERNAL_REF = "DEMO-PTW-0001"
CR_EXTERNAL_REF = "DEMO-MOC-0001"
PRECURSOR_EXTERNAL_REF = "DEMO-INC-0001"

#: The two signing subjects `demo_world.sql` enrols. `mainline_demo_api.scenario` defaults to
#: exactly these and lets a deployment override them from the environment, which is why the
#: LIVE check asserts that two credentials RESOLVED and not that they are spelled this way —
#: see :func:`_gate_run_facts`. The LOCAL check reads the spelling out of the table.
SIGNER_SUB = "demo.signer"
COUNTERSIGNER_SUB = "demo.countersigner"

#: Measured against the deployment on 2026-08-15 by the proof-and-polish lead
#: (`docs/demo/proof-and-polish-plan.md` §0.1) and again by this program on 2026-08-16.
#: A chain that is longer than this is not broken — it is a chain nobody re-recorded, and the
#: film's own overlay says 271. So it FAILS here, loudly, with the remedy in the line.
EXPECTED_DEPLOY_CHAIN = 271

#: The database the deployment answers out of. Checked so that a Function URL repointed at a
#: scratch database cannot pass as the demo.
EXPECTED_DEPLOY_DATABASE = "mainline_demo"

#: What the seeded permit's merge is refused with, and by what. Not this file's opinion:
#: `scripts/deploy/seed_demo.py` names the same pair as EXPECTED_SQLSTATE /
#: EXPECTED_CONSTRAINT and `tests/demo/test_demo_ready.py` asserts the two agree.
EXPECTED_REFUSAL_SQLSTATE = "23514"
EXPECTED_REFUSAL_CONSTRAINT = "gate_closed_when_issued"

#: The four beats `POST /v1/demo/gate-run` drives, as `(name, outcome, sqlstate, exhibit)`.
#: `docs/deploy/cloud-database.md` §6 records the same four. The third is the one no CHECK
#: can hold — the projected counter is forced to zero out of band and the gate refuses anyway
#: because it re-derives the count instead of trusting the column.
EXPECTED_BEATS: tuple[tuple[str, str, str, str], ...] = (
    ("read", "read", "00000", ""),
    ("merge", "refused", "23514", "gate_closed_when_issued"),
    ("projection_drift_attack", "refused", "P0001", "mainline.fn_permit_merge_gate"),
    ("admit", "admitted", "00000", ""),
)

#: The eight facts, in the order they are printed, and it is the SAME eight in both modes.
#: The two targets answer them from different places — the deployment over HTTP, a local
#: database through ``seed_demo`` — but a fact that existed in one mode and not the other
#: would mean "ready" meant two things, and an operator would learn which one by being
#: surprised. ``tests/demo/test_demo_ready.py`` asserts both paths produce exactly this list.
FACT_ORDER: tuple[str, ...] = (
    "target",
    "permit",
    "obligation",
    "change_request",
    "zeros",
    "signers",
    "refusal",
    "unchanged",
)

#: The two counts that ARE the demonstration. `docs/deploy/cloud-database.md` §5: "The two
#: zeros are the demonstration. Everything else is the history a real permit would carry; the
#: one thing missing is a human's signed answer to the one obligation the recall pass raised."
ZERO_TABLES = ("mainline.disposition", "mainline.merge_record")

#: The bound §R1 sets for "may I roll camera?". Reported against, never enforced: a slow
#: network is a statement about the network and not about the seeded world, and a command
#: that went red for latency would teach an operator to ignore its own exit code.
SECONDS_BOUND = 10.0

#: Column widths. The table is a diagnostic an operator reads before recording, never a frame,
#: so it is not bounded to a camera width the way `scripts/submission/seed_demo_state.py`'s
#: `--camera` block is. It IS aligned, because eight lines that do not line up are eight lines
#: nobody scans.
_STATUS_W = 4
_ID_W = 14
_SOURCE_W = 44

#: The width the PROSE notes under the table are wrapped to. Only the prose: see
#: :func:`render` for why the fact lines are left alone.
_NOTE_WIDTH = 96

_USER_AGENT = "mainline-demo-ready/1 (+scripts/demo/demo_ready.py)"


class Unreachable(RuntimeError):
    """The target could not be asked. NOT a finding about the world — exit 2, not exit 1."""


class ActionRequired(RuntimeError):
    """A write was asked for against a target this program will not write to. Exit 3."""


@dataclass(frozen=True, slots=True)
class Fact:
    """One checked fact: what it is, where the value came from, and what the value was.

    ``detail`` is the observed value in the observed world, never a restatement of the
    expectation. A FAIL line therefore reads as a diagnosis rather than as ``expected X got
    Y``: eight facts with eight different remedies are worth eight different sentences.
    """

    fact_id: str
    ok: bool
    source: str
    detail: str

    def line(self) -> str:
        status = "PASS" if self.ok else "FAIL"
        return (
            f"{status:<{_STATUS_W}}  {self.fact_id:<{_ID_W}}  "
            f"{self.source:<{_SOURCE_W}}  {self.detail}"
        )


# ── the wire, and nothing else on it ──────────────────────────────────────────────────────


class Wire:
    """One keep-alive HTTPS connection to the deployment, and a record of what went over it.

    ONE connection for five requests, not five. Measured from this machine to
    ``ap-southeast-1`` on 2026-08-16: 5.85 s with a fresh TLS handshake per request, 3.58 s
    reusing one. The ten-second bound in §R1 is not generous enough to spend four handshakes
    on, and an operator who has to wait is an operator who stops running the check.

    Every request this class can make is a ``GET``, except the single ``POST`` to
    ``/v1/demo/gate-run`` that plan §R4 permits by name. There is no method parameter with a
    default; the caller says which of the two it is.
    """

    def __init__(self, base: str, *, timeout: float) -> None:
        parts = urlsplit(base)
        if parts.scheme not in ("https", "http") or not parts.hostname:
            raise Unreachable(f"{base!r} is not an http(s) origin")
        self.base = base.rstrip("/")
        self._host = parts.hostname
        self._timeout = timeout
        self._conn: http.client.HTTPConnection
        if parts.scheme == "https":
            self._conn = http.client.HTTPSConnection(
                parts.hostname, parts.port, timeout=timeout, context=ssl.create_default_context()
            )
        else:
            self._conn = http.client.HTTPConnection(parts.hostname, parts.port, timeout=timeout)
        self.requests = 0

    def _send(self, method: str, path: str, body: bytes | None) -> tuple[int, Any]:
        headers = {"accept": "application/json", "user-agent": _USER_AGENT}
        if body is not None:
            headers["content-type"] = "application/json"
        try:
            self._conn.request(method, path, body=body, headers=headers)
            response = self._conn.getresponse()
            raw = response.read()
            status = response.status
        except (TimeoutError, OSError, http.client.HTTPException) as exc:
            # A socket that never answered is not evidence about the seeded world. It is
            # exit 2, and it says so here rather than being classified as a failed fact.
            raise Unreachable(f"{method} {path} — {type(exc).__name__}: {exc}") from exc
        self.requests += 1
        try:
            return status, json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return status, {"_unparsed": raw[:400].decode("utf-8", "replace")}

    def get(self, path: str) -> tuple[int, Any]:
        return self._send("GET", path, None)

    def gate_run(self) -> tuple[int, Any]:
        """``POST /v1/demo/gate-run`` with ``{}``.

        The body is the one `scripts/deploy/cloud_contention.py` and
        `scripts/demo/capture_memory_loop.py` already send: the driver takes its subjects from
        the server's own environment, so there is nothing for a caller to choose.
        """
        return self._send("POST", "/v1/demo/gate-run", b"{}")

    def close(self) -> None:
        with contextlib.suppress(OSError):
            self._conn.close()


def _status_detail(status: int, path: str) -> str:
    if status == 429:
        return f"HTTP {status} from {path} — the demo API rate-limits; wait and re-run"
    return f"HTTP {status} from {path}"


# ── the eight facts, against the deployment ───────────────────────────────────────────────


def _fact_target_live(status: int, health: Any) -> Fact:
    if status != 200 or not isinstance(health, dict):
        return Fact("target", False, "GET /v1/health", _status_detail(status, "/v1/health"))
    ok = health.get("ok")
    applied = health.get("deploy_chain_applied")
    files = health.get("deploy_chain_files")
    database = health.get("database")
    detail = f"ok={str(ok).lower()}  deploy_chain={applied}/{files}  database={database}"
    if ok is not True:
        return Fact("target", False, "GET /v1/health", detail + "  — the origin says it is not ok")
    if applied != files:
        return Fact(
            "target",
            False,
            "GET /v1/health",
            detail + "  — the deploy chain is part-applied; the deployment is mid-flight",
        )
    if applied != EXPECTED_DEPLOY_CHAIN:
        return Fact(
            "target",
            False,
            "GET /v1/health",
            detail
            + f"  — the film's overlay names {EXPECTED_DEPLOY_CHAIN}; re-record the overlay or "
            "the constant, do not film a number the origin does not say",
        )
    if database != EXPECTED_DEPLOY_DATABASE:
        return Fact(
            "target",
            False,
            "GET /v1/health",
            detail + f"  — expected the demo database {EXPECTED_DEPLOY_DATABASE}",
        )
    return Fact("target", True, "GET /v1/health", detail)


def _fact_permit_live(status: int, subjects: Any) -> tuple[Fact, dict[str, Any]]:
    """The permit, and the ADDRESSING every later request uses.

    Returns the fact and the ``data`` member, because this is the response that hands back the
    identifiers the next two requests are addressed with. Nothing below builds a path out of a
    constant: the constants are what the answer is CHECKED against.
    """
    source = "GET /v1/demo/subjects"
    if status != 200 or not isinstance(subjects, dict):
        return Fact("permit", False, source, _status_detail(status, "/v1/demo/subjects")), {}
    data = subjects.get("data") or {}
    permit = (data.get("subjects") or {}).get("permit") or {}
    absent = data.get("absent") or []
    detail = (
        f"{permit.get('permit_id')}  {permit.get('external_ref')}  {permit.get('state')}  "
        f"open_blocking={permit.get('open_blocking')}  gate_epoch={permit.get('gate_epoch')}"
    )
    problems: list[str] = []
    if absent:
        problems.append(f"{len(absent)} subject(s) the API looked for and did not find")
    if permit.get("count") != 1:
        problems.append(f"{permit.get('count')} permits stand where the demo needs exactly 1")
    if permit.get("permit_id") != PERMIT_ID:
        problems.append(f"the permit is not {PERMIT_ID}")
    if permit.get("external_ref") != PERMIT_EXTERNAL_REF:
        problems.append(f"external_ref is not {PERMIT_EXTERNAL_REF}")
    if permit.get("state") != "dispositioned":
        problems.append("state is not 'dispositioned' — beat 2 has no legal edge to merged")
    if permit.get("open_blocking") != 1:
        problems.append("open_blocking is not 1 — the obligation is answered or was never raised")
    if permit.get("gate_epoch") != 1:
        problems.append("gate_epoch is not 1 — the obligations were re-materialised")
    if problems:
        return Fact("permit", False, source, detail + "  — " + "; ".join(problems)), data
    return Fact("permit", True, source, detail), data


def _fact_obligation_live(status: int, checks: Any) -> Fact:
    source = "GET /v1/permits/{permit_id}/blocking-checks"
    if status != 200 or not isinstance(checks, dict):
        return Fact("obligation", False, source, _status_detail(status, "blocking-checks"))
    rows = (checks.get("data") or {}).get("checks") or []
    if len(rows) != 1:
        return Fact(
            "obligation", False, source, f"{len(rows)} open checks, the demo needs exactly 1"
        )
    row = rows[0]
    precursor = row.get("precursor") or {}
    detail = (
        f"{row.get('check_id')}  open={str(row.get('open')).lower()}  "
        f"disposition_id={row.get('disposition_id')}  severity={row.get('severity')}  "
        f"virulence={row.get('virulence')}  origin={row.get('origin')}  "
        f"precursor={precursor.get('external_ref')}"
    )
    problems: list[str] = []
    if row.get("check_id") != CHECK_ID:
        problems.append(f"the obligation is not {CHECK_ID}")
    if row.get("open") is not True:
        problems.append("the obligation is not open")
    if row.get("disposition_id") is not None:
        problems.append("a disposition already stands against it — beat 2 would not refuse")
    if row.get("severity") != 4:
        problems.append("severity is not 4")
    if row.get("virulence") != "blood_major":
        problems.append("virulence is not 'blood_major'")
    if row.get("origin") != "blame_ancestry":
        problems.append("origin is not 'blame_ancestry'")
    if precursor.get("external_ref") != PRECURSOR_EXTERNAL_REF:
        problems.append(f"the precursor is not {PRECURSOR_EXTERNAL_REF}")
    if problems:
        return Fact("obligation", False, source, detail + "  — " + "; ".join(problems))
    return Fact("obligation", True, source, detail)


def _fact_change_request_live(status: int, payload: Any) -> Fact:
    source = "GET /v1/change-requests/{cr_id}"
    if status != 200 or not isinstance(payload, dict):
        return Fact("change_request", False, source, _status_detail(status, "change-requests"))
    data = payload.get("data") or {}
    counters = data.get("counters") or {}
    named = {c.get("constraint") for c in (data.get("constraints") or [])}
    detail = (
        f"{data.get('cr_id')}  {data.get('external_ref')}  {data.get('state')}  "
        f"open_blocking={counters.get('open_blocking')}  "
        f"merged_commit={data.get('merged_commit')}"
    )
    problems: list[str] = []
    if data.get("cr_id") != CR_ID:
        problems.append(f"the change request is not {CR_ID}")
    if data.get("external_ref") != CR_EXTERNAL_REF:
        problems.append(f"external_ref is not {CR_EXTERNAL_REF}")
    if data.get("state") == "merged":
        problems.append("it has MERGED — the clause it proposes to edit was rewritten")
    if counters.get("open_blocking") != 1:
        problems.append("open_blocking is not 1 — nothing gates it")
    if data.get("merged_commit") is not None:
        problems.append("merged_commit is set")
    if "cr_gate_closed_when_merged" not in named:
        problems.append("the CHECK cr_gate_closed_when_merged is not on the row")
    if problems:
        return Fact("change_request", False, source, detail + "  — " + "; ".join(problems))
    return Fact("change_request", True, source, detail)


def _gate_run_facts(status: int, payload: Any) -> list[Fact]:
    """The four facts one ``POST /v1/demo/gate-run`` answers, in reading order.

    ``zeros``, ``signers``, ``refusal`` and ``unchanged``. One request, because it is one
    transaction: the payload's ``persistence_check`` counts the rows BEFORE that transaction
    opened and again after it was rolled back, which is where both zeros and the proof that
    this command wrote nothing come from.
    """
    source = "POST /v1/demo/gate-run"
    if status != 200 or not isinstance(payload, dict):
        detail = _status_detail(status, "/v1/demo/gate-run")
        return [
            Fact("zeros", False, source, detail),
            Fact("signers", False, source, detail),
            Fact("refusal", False, source, detail),
            Fact("unchanged", False, source, detail),
        ]
    data = payload.get("data") or {}
    persistence = data.get("persistence_check") or {}
    before = (persistence.get("before") or {}).get("row_counts") or {}
    beats = data.get("beats") or []

    counts = {table: before.get(table) for table in ZERO_TABLES}
    zeros_detail = "  ".join(f"{table}={counts[table]}" for table in ZERO_TABLES)
    zeros_ok = all(counts[table] == 0 for table in ZERO_TABLES)
    zeros = Fact(
        "zeros",
        zeros_ok,
        source,
        zeros_detail
        if zeros_ok
        else zeros_detail + "  — the two zeros ARE the demonstration; one of them is not zero",
    )

    # BOTH credential ids are resolved by `mainline_demo_api.gate_run` BEFORE the beats'
    # transaction opens, from `mainline.signing_credential`, and a subject with no unrevoked
    # credential raises `ScenarioNotSeeded` → HTTP 422. So four beats in a 200 body is proof
    # that two credentials resolved. It is NOT proof of how they are spelled: `scenario.py`
    # lets a deployment override both subs from the environment and the payload does not
    # carry them, so this line asserts the resolution and the footnote names the seed.
    signers_ok = len(beats) == len(EXPECTED_BEATS) and data.get("outcome") == "completed"
    signers_detail = (
        f"{len(beats)} beats returned 200  outcome={data.get('outcome')}  "
        "-> two signing credentials resolved before beat 1"
    )
    signers = Fact(
        "signers",
        signers_ok,
        source,
        signers_detail
        if signers_ok
        else signers_detail + "  — a missing or revoked credential is 422, never a 200",
    )

    observed = [
        (
            str(beat.get("name")),
            str(beat.get("outcome")),
            str(beat.get("sqlstate")),
            str(beat.get("constraint") or ""),
            bool(beat.get("matched_expectation")),
        )
        for beat in beats
    ]
    refusal_detail = "  ".join(
        f"{name}[{sqlstate}]{'/' + exhibit if exhibit else ''}"
        for name, _outcome, sqlstate, exhibit, _matched in observed
    )
    refusal_detail = f"verdict={data.get('verdict')}  " + refusal_detail
    problems: list[str] = []
    if data.get("verdict") != "PROVEN":
        problems.append(f"verdict is {data.get('verdict')!r}")
    if len(observed) != len(EXPECTED_BEATS):
        problems.append(f"{len(observed)} beats, expected {len(EXPECTED_BEATS)}")
    else:
        for got, want in zip(observed, EXPECTED_BEATS, strict=True):
            name, outcome, sqlstate, exhibit, matched = got
            if (name, outcome, sqlstate, exhibit) != want:
                problems.append(f"beat {name} answered [{sqlstate}] {exhibit or '-'}")
            elif not matched:
                problems.append(f"beat {name} did not match its own expectation")
    refusal = Fact(
        "refusal",
        not problems,
        source,
        refusal_detail if not problems else refusal_detail + "  — " + "; ".join(problems),
    )

    identical = persistence.get("identical")
    persisted = data.get("persisted")
    self_persisted = persistence.get("self_persisted")
    unchanged_detail = (
        f"persisted={str(persisted).lower()}  row_counts_identical={str(identical).lower()}  "
        f"self_persisted={str(self_persisted).lower()}  "
        f"over {len(persistence.get('tables') or [])} tables"
    )
    unchanged_ok = persisted is False and identical is True and self_persisted is False
    unchanged = Fact(
        "unchanged",
        unchanged_ok,
        source,
        unchanged_detail
        if unchanged_ok
        else unchanged_detail + "  — this run CHANGED the world; the next take is not the last one",
    )
    return [zeros, signers, refusal, unchanged]


def _in_order(facts: list[Fact]) -> list[Fact]:
    """Sort a mode's facts into :data:`FACT_ORDER` and refuse a set that is not the eight.

    Structural rather than conventional. Both modes build their facts in whatever order their
    sources make cheap — the deployment answers three of them in one POST, the local path
    answers two of them in SQL after the census — and this is the one place the printed order
    is decided. A mode that produced seven facts, or a ninth nobody documented, stops here
    instead of printing a table an operator would read as complete.
    """
    by_id = {fact.fact_id: fact for fact in facts}
    if set(by_id) != set(FACT_ORDER) or len(by_id) != len(facts):
        raise RuntimeError(
            f"the fact set is {sorted(by_id)}, which is not the eight in FACT_ORDER "
            f"({list(FACT_ORDER)}). A pre-flight check with a missing question is a green "
            "light nobody earned."
        )
    return [by_id[fact_id] for fact_id in FACT_ORDER]


def check_live(base: str, *, timeout: float) -> tuple[list[Fact], int]:
    """Ask the deployment its eight questions over one connection. Read-only by construction.

    Five requests, four of them ``GET``. The fifth is ``POST /v1/demo/gate-run``, which plan
    §R4 permits by name and which ends in ``ROLLBACK`` — and the ``unchanged`` fact is the
    database's own before-and-after row counts saying so, rather than this program promising
    it.
    """
    wire = Wire(base, timeout=timeout)
    try:
        facts: list[Fact] = []
        facts.append(_fact_target_live(*wire.get("/v1/health")))
        permit_fact, subjects = _fact_permit_live(*wire.get("/v1/demo/subjects"))
        facts.append(permit_fact)
        # ADDRESSED WITH WHAT THE API ANSWERED, never with the constants above. When the
        # answer carries no identifier at all there is nothing to address, and the dependent
        # fact fails rather than being sent to a path this file made up.
        permit_id = subjects.get("permit_id")
        cr_id = subjects.get("cr_id")
        if permit_id:
            facts.append(
                _fact_obligation_live(*wire.get(f"/v1/permits/{permit_id}/blocking-checks"))
            )
        else:
            facts.append(
                Fact(
                    "obligation",
                    False,
                    "GET /v1/permits/{permit_id}/blocking-checks",
                    "not asked: /v1/demo/subjects returned no permit_id to address it with",
                )
            )
        if cr_id:
            facts.append(_fact_change_request_live(*wire.get(f"/v1/change-requests/{cr_id}")))
        else:
            facts.append(
                Fact(
                    "change_request",
                    False,
                    "GET /v1/change-requests/{cr_id}",
                    "not asked: /v1/demo/subjects returned no cr_id to address it with",
                )
            )
        facts.extend(_gate_run_facts(*wire.gate_run()))
        return _in_order(facts), wire.requests
    finally:
        wire.close()


# ── the same eight facts, against a local database ────────────────────────────────────────


def _sibling(dotted: str) -> Any:
    """Import a ``scripts.…`` module, restoring ``sys.path`` if it had to be changed.

    The insert at the top of this file happens when ``__package__`` is empty, which covers
    the two ways an operator runs this program. It does NOT cover a caller that loaded this
    module by path and then handed ``sys.path`` back — which is exactly what
    ``tests/demo/test_demo_ready.py`` does, for the measured reason
    ``verticals/mainline/apps/demo-api/tests/conftest.py`` records: a repository root left on
    the path makes eight top-level directories importable as namespace packages for
    everything collected afterwards.

    So the root goes on for the duration of the import and comes off again. The imported
    module stays in ``sys.modules``, so nothing pays this twice.
    """
    import importlib

    root = str(REPO_ROOT)
    added = root not in sys.path
    if added:
        sys.path.insert(0, root)
    try:
        return importlib.import_module(dotted)
    finally:
        if added:
            with contextlib.suppress(ValueError):
                sys.path.remove(root)


def _seed_demo() -> Any:
    """``scripts.deploy.seed_demo``, imported rather than restated.

    Imported inside the function so that the LIVE path — the default, and the one with a
    ten-second bound on it — never pays for ``psycopg``, ``trappoint_testkit`` or
    ``trappoint_core``. The local path needs a driver anyway.
    """
    return _sibling("scripts.deploy.seed_demo")


def _guard() -> Any:
    """``scripts.deploy.verify_demo_checkpoints``, for its refusal vocabulary ONLY.

    ``LOCAL_HOSTS``, ``PROTECTED_DATABASES`` and ``require_local`` are IMPORTED, not
    re-derived. That module already refuses to write to a database other lanes read, and the
    set of names it protects is exactly the set this one must protect: if somebody adds a name
    there, this program starts refusing it too, with no edit here. Imported inside the
    function because it puts two more source roots on ``sys.path`` and pulls in the whole demo
    API, which the live path has no use for.
    """
    return _sibling("scripts.deploy.verify_demo_checkpoints")


def _fact_target_local(evidence: dict[str, Any], database: str) -> Fact:
    """The local parallel of ``GET /v1/health``: is the schema the seed needs actually here?

    ``seed_demo``'s census counts 27 relations by name and records ``ERROR 42P01`` for any it
    cannot reach, so "the schema is present" is a fact that census already answers. A local
    database has no ``/v1/health`` and no deploy-chain counter to read, and inventing one here
    would be this program asserting a number nothing measured.
    """
    counts = evidence.get("row_counts") or {}
    missing = sorted(name for name, value in counts.items() if isinstance(value, str))
    source = "seed_demo:row_counts (census)"
    detail = (
        f"{len(counts) - len(missing)} of {len(counts)} seeded relations present  "
        f"database={database}"
    )
    if missing:
        return Fact("target", False, source, detail + "  — unreachable: " + ", ".join(missing[:4]))
    return Fact("target", True, source, detail)


def _fact_permit_local(evidence: dict[str, Any]) -> Fact:
    source = "seed_demo:observed.permit"
    observed = evidence.get("observed") or {}
    permit = observed.get("permit")
    if not permit:
        return Fact("permit", False, source, "the seeded permit does not exist in this database")
    detail = (
        f"{permit.get('permit_id')}  {permit.get('external_ref')}  {permit.get('state')}  "
        f"open_blocking={permit.get('open_blocking')}  gate_epoch={permit.get('gate_epoch')}"
    )
    problems: list[str] = []
    if observed.get("permits_in_database") != 1:
        problems.append(
            f"{observed.get('permits_in_database')} permits stand in mainline.permit, expected 1"
        )
    if permit.get("permit_id") != PERMIT_ID:
        problems.append(f"the permit is not {PERMIT_ID}")
    if permit.get("external_ref") != PERMIT_EXTERNAL_REF:
        problems.append(f"external_ref is not {PERMIT_EXTERNAL_REF}")
    if permit.get("state") != "dispositioned":
        problems.append("state is not 'dispositioned'")
    if permit.get("open_blocking") != 1:
        problems.append("open_blocking is not 1")
    if permit.get("gate_epoch") != 1:
        problems.append("gate_epoch is not 1")
    if problems:
        return Fact("permit", False, source, detail + "  — " + "; ".join(problems))
    return Fact("permit", True, source, detail)


def _fact_obligation_local(evidence: dict[str, Any]) -> Fact:
    source = "seed_demo:observed.blocking_check"
    observed = evidence.get("observed") or {}
    check = observed.get("blocking_check")
    if not check:
        return Fact("obligation", False, source, "the seeded blocking check does not exist")
    detail = (
        f"{check.get('check_id')}  severity={check.get('severity')}  "
        f"virulence={check.get('virulence')}  origin={check.get('origin')}  "
        f"dispositions={observed.get('dispositions_against_the_check')}  "
        f"re_derived_open={observed.get('re_derived_open_obligations')}"
    )
    problems: list[str] = []
    if check.get("check_id") != CHECK_ID:
        problems.append(f"the obligation is not {CHECK_ID}")
    if check.get("severity") != 4:
        problems.append("severity is not 4")
    if check.get("virulence") != "blood_major":
        problems.append("virulence is not 'blood_major'")
    if check.get("origin") != "blame_ancestry":
        problems.append("origin is not 'blame_ancestry'")
    if observed.get("dispositions_against_the_check") != 0:
        problems.append("a disposition already stands against it — beat 2 would not refuse")
    if observed.get("re_derived_open_obligations") != 1:
        problems.append("the re-derived open count is not 1")
    if not observed.get("projection_trigger_check_materialised_present"):
        problems.append("the projection trigger check_materialised is absent")
    if problems:
        return Fact("obligation", False, source, detail + "  — " + "; ".join(problems))
    return Fact("obligation", True, source, detail)


def _fact_zeros_local(evidence: dict[str, Any]) -> Fact:
    source = "seed_demo:row_counts"
    counts = evidence.get("row_counts") or {}
    values = {table: counts.get(table) for table in ZERO_TABLES}
    detail = "  ".join(f"{table}={values[table]}" for table in ZERO_TABLES)
    if all(values[table] == 0 for table in ZERO_TABLES):
        return Fact("zeros", True, source, detail)
    return Fact(
        "zeros",
        False,
        source,
        detail + "  — the two zeros ARE the demonstration; one of them is not zero",
    )


def _fact_refusal_local(evidence: dict[str, Any]) -> Fact:
    """The local parallel of the four beats: ``seed_demo``'s rolled-back merge probe.

    One beat rather than four, and the line says so. ``seed_demo`` asks the database to merge
    the seeded permit inside a transaction it rolls back and records the SQLSTATE and the
    exhibit it saw; the other three beats live in the deployed ``POST /v1/demo/gate-run`` and
    are checked there. ``UNDECIDED`` — ``40001`` on every attempt of the retry budget — is
    reported as itself, because the database did not decide and that is not a finding about
    the gate.
    """
    source = "seed_demo:verification"
    verification = evidence.get("verification") or {}
    outcome = verification.get("outcome")
    detail = (
        f"merge {outcome} [{verification.get('sqlstate')}] {verification.get('constraint')} "
        f"({verification.get('constraint_source')})"
    )
    if outcome == "UNDECIDED":
        return Fact(
            "refusal",
            False,
            source,
            detail + "  — 40001 on every attempt; the cluster never decided. Re-run; this is "
            "not evidence about the gate",
        )
    problems: list[str] = []
    if outcome != "REFUSED":
        problems.append("the seeded permit MERGED — the gate admitted an open obligation")
    elif not verification.get("as_expected"):
        problems.append(f"expected [{EXPECTED_REFUSAL_SQLSTATE}] {EXPECTED_REFUSAL_CONSTRAINT}")
    if problems:
        return Fact("refusal", False, source, detail + "  — " + "; ".join(problems))
    return Fact("refusal", True, source, detail)


def _fact_unchanged_local(evidence: dict[str, Any]) -> Fact:
    source = "seed_demo:after_rollback"
    after = (evidence.get("verification") or {}).get("after_rollback") or {}
    detail = (
        f"permit_state={after.get('permit_state')}  open_blocking={after.get('open_blocking')}  "
        f"gate_epoch={after.get('gate_epoch')}  merge_record_rows={after.get('merge_record_rows')}"
    )
    if after.get("nothing_persisted") is True:
        return Fact("unchanged", True, source, detail)
    return Fact(
        "unchanged",
        False,
        source,
        detail + "  — the rollback did not hold; the world moved under a transaction that "
        "was rolled back",
    )


_SIGNERS_SQL = """
SELECT signer_sub
  FROM mainline.signing_credential
 WHERE signer_sub = ANY(%s) AND revoked_at IS NULL
"""

_CHANGE_REQUEST_SQL = """
SELECT state::STRING, external_ref, open_blocking, merged_commit IS NULL
  FROM mainline.change_request
 WHERE cr_id = %s
"""


def _facts_from_sql(dsn: str) -> tuple[list[Fact], float]:
    """The two facts ``seed_demo`` does not carry, and the only SQL in this file.

    ``seed_demo``'s census counts ``mainline.signing_credential`` but does not say which
    subjects it found, and it does not look at ``mainline.change_request`` at all. "Two rows
    exist" and "these two subjects are enrolled" are different claims and the demo depends on
    the second, so it is asked for directly rather than inferred from a count.

    Returns the facts and HOW LONG THE CONNECT TOOK, which is not decoration — see
    :func:`_slow_host_note`.
    """
    import psycopg

    facts: list[Fact] = []
    opened = time.perf_counter()
    with psycopg.connect(dsn) as conn:
        connect_seconds = time.perf_counter() - opened
        found = sorted(
            str(row[0])
            for row in conn.execute(_SIGNERS_SQL, ([SIGNER_SUB, COUNTERSIGNER_SUB],)).fetchall()
        )
        detail = f"enrolled and unrevoked: {', '.join(found) if found else 'none'}"
        missing = sorted({SIGNER_SUB, COUNTERSIGNER_SUB} - set(found))
        facts.append(
            Fact("signers", not missing, "SELECT mainline.signing_credential", detail)
            if not missing
            else Fact(
                "signers",
                False,
                "SELECT mainline.signing_credential",
                detail + "  — absent or revoked: " + ", ".join(missing),
            )
        )
        row = conn.execute(_CHANGE_REQUEST_SQL, (CR_ID,)).fetchone()
        source = "SELECT mainline.change_request"
        if row is None:
            facts.append(Fact("change_request", False, source, f"{CR_ID} is not in this database"))
        else:
            state, external_ref, open_blocking, unmerged = row
            cr_detail = (
                f"{CR_ID}  {external_ref}  {state}  open_blocking={open_blocking}  "
                f"merged_commit={'None' if unmerged else 'set'}"
            )
            problems: list[str] = []
            if external_ref != CR_EXTERNAL_REF:
                problems.append(f"external_ref is not {CR_EXTERNAL_REF}")
            if state == "merged":
                problems.append("it has MERGED — the clause it proposes to edit was rewritten")
            if int(open_blocking) != 1:
                problems.append("open_blocking is not 1 — nothing gates it")
            if not unmerged:
                problems.append("merged_commit is set")
            facts.append(
                Fact("change_request", not problems, source, cr_detail)
                if not problems
                else Fact("change_request", False, source, cr_detail + "  — " + "; ".join(problems))
            )
    return facts, connect_seconds


#: A connect that takes longer than this is a name-resolution problem, not a busy cluster.
#: Measured on this machine, 2026-08-16, against the node the whole project documents:
#: ``postgresql://root@127.0.0.1:26257/w_p1`` connected in **0.01 s** and
#: ``postgresql://root@localhost:26257/w_p1`` took **130.06 s** — the same 130.1 s
#: ``conftest.py`` records — because ``localhost`` resolves to ``::1`` first and nothing
#: answers there. libpq spends the whole timeout on that address before trying IPv4, once per
#: connection, and this command opens three.
_SLOW_CONNECT_SECONDS = 1.0


def _slow_host_note(dsn: str, connect_seconds: float) -> str | None:
    """Name the cause when a local connect was slow. NEVER rewrite the caller's DSN.

    A pre-flight check that takes a minute is a pre-flight check nobody runs twice, and the
    minute is not the database's fault — it is four characters in a host name. Saying so is
    the whole fix available here: silently substituting ``127.0.0.1`` would mean this command
    measured a target the operator did not name, which is a worse defect than the delay.
    """
    if connect_seconds < _SLOW_CONNECT_SECONDS:
        return None
    host = urlsplit(dsn).hostname or ""
    if not host or host.replace(".", "").isdigit() or ":" in host:
        return None
    return (
        f"the connect to host {host!r} took {connect_seconds:.1f}s, and this command opens "
        f"three. On this machine {host!r} resolves to an address that does not answer and "
        f"libpq spends the whole connect timeout on it before trying the next one "
        f"(measured 2026-08-16: 130.06s unset, 0.01s to 127.0.0.1). Spell the host "
        f"127.0.0.1 in --dsn. This program does not rewrite your DSN."
    )


def check_local(
    dsn: str, database: str, *, repair: bool, connect_timeout: int
) -> tuple[list[Fact], float]:
    """Ask a LOCAL database the same eight questions, through ``seed_demo``.

    ``seed_demo.build_parser()`` builds the arguments and ``seed_demo.run()`` produces the
    evidence — its census, its ``observe``, its rolled-back merge probe. This function reads
    that evidence and adds the two facts it does not carry. It does not count a row that
    ``seed_demo`` counts, and it does not open a second opinion about what "seeded" means.

    ``repair`` is the ONE difference: ``--check`` is passed when it is false, so the two seed
    files are not applied. ``seed_demo``'s own stdout goes to stderr, tagged, so that this
    program's stdout stays byte-identical between two runs against an unchanged world.
    """
    seed_demo = _seed_demo()
    argv = ["--dsn", dsn, "--database", database, "--connect-timeout", str(connect_timeout)]
    if not repair:
        argv.append("--check")
    args = seed_demo.build_parser().parse_args(argv)

    captured = io.StringIO()
    try:
        with contextlib.redirect_stdout(captured):
            _code, evidence = seed_demo.run(args)
    finally:
        text = captured.getvalue().strip()
        if text:
            label = "seed_demo.py" + ("" if repair else " --check")
            sys.stderr.write(f"--- {label} said ---\n{text}\n--- end ---\n")
            sys.stderr.flush()

    # The SAME rewriting `seed_demo` just used, called rather than repeated, so the two
    # SELECTs below cannot end up pointed at a different database from the census above.
    sql_dsn = seed_demo.rewrite_dsn(
        dsn,
        database=database,
        connect_timeout=connect_timeout,
        application_name="mainline-demo-ready",
    )
    sql_facts, connect_seconds = _facts_from_sql(sql_dsn)
    return (
        _in_order(
            [
                _fact_target_local(evidence, database),
                _fact_permit_local(evidence),
                _fact_obligation_local(evidence),
                _fact_zeros_local(evidence),
                *sql_facts,
                _fact_refusal_local(evidence),
                _fact_unchanged_local(evidence),
            ]
        ),
        connect_seconds,
    )


# ── refusals, before anything is opened ───────────────────────────────────────────────────


def guard_target(dsn: str | None, database: str, *, repair: bool) -> None:
    """Refuse, BEFORE a connection is opened, every target this program will not act on.

    Three refusals, and each is a different sentence because each has a different remedy:

    * ``--repair`` with no ``--dsn`` — the deployment is seeded by the orchestrator, not by
      this program and not by the person holding the camera.
    * ``--repair`` against a protected database (``mainline_demo`` and the three system
      databases, the set ``verify_demo_checkpoints.PROTECTED_DATABASES`` already protects) —
      the name the deployment and its local mirror share. Exit 3, plan §R2.
    * any ``--dsn`` whose host is not this machine — the deployment is asked over HTTP and
      never as a database, whatever the verb.
    """
    guard = _guard()
    if dsn is None:
        if repair:
            raise ActionRequired(
                "--repair has no local database to repair. The DEPLOYED demo world is seeded "
                "by the orchestrator and by nothing else, and this program will not write to "
                "it. Run, from the repository root:\n"
                f"    {ORCHESTRATOR_SEED_COMMAND}\n"
                "Then re-run this command with no arguments to verify the result over HTTP."
            )
        return

    host = urlsplit(dsn).hostname or ""
    if host not in guard.LOCAL_HOSTS:
        message = (
            f"refusing to open a database connection to host {host!r}. The deployment is "
            "checked over HTTP — read-only GETs and the one permitted POST — and is never "
            "opened as a database by this program. Drop --dsn to check the deployment."
        )
        # A remote --repair is ACTION REQUIRED (3): somebody meant to seed the deployment and
        # a human has to. A remote --check is USAGE (2): nothing needed doing, the command was
        # simply pointed at the wrong surface.
        if repair:
            raise ActionRequired(
                message + f"\nTo seed the deployment, the orchestrator runs:\n    "
                f"{ORCHESTRATOR_SEED_COMMAND}"
            )
        raise Unreachable(message)

    if repair and database in guard.PROTECTED_DATABASES:
        raise ActionRequired(
            f"refusing to write to the database {database!r}. That is the name the deployed "
            "demo and its local mirror share, and a program run beside a camera is not what "
            "seeds either of them. Nothing was written and nothing was measured. Run, from "
            "the repository root:\n"
            f"    {ORCHESTRATOR_SEED_COMMAND}\n"
            "or point --repair at a scratch database of your own "
            "(--dsn postgresql://root@localhost:26257/w_p1?sslmode=disable)."
        )


# ── the report ────────────────────────────────────────────────────────────────────────────

#: Printed under the table, once, beneath the fact each one is about, whether that fact
#: passed or failed. Plan §R9: wherever a `4` or a `blood_major` is printed, the projector
#: that produced it is named beside it, because a `4` with no provenance is a number somebody
#: could have typed.
#:
#: THERE ARE TWO SETS, and there have to be. The same eight facts are answered from different
#: places in the two modes, and a note that names `gate-run` under a line that came out of
#: `seed_demo`'s rolled-back merge probe would be this file explaining a request it never
#: made. Only the `obligation` note is common, because the projection is the projection
#: wherever it ran.
_NOTE_OBLIGATION = (
    "severity 4 and virulence 'blood_major' are PROJECTED by mainline.fn_check_project from "
    "mainline.clause_blame_current (MI25). The seed supplies 0 / 'routine' and both are "
    "overwritten — which is how you know the projection ran. Nobody typed the four."
)

FOOTNOTES_LIVE: tuple[tuple[str, str], ...] = (
    ("obligation", _NOTE_OBLIGATION),
    (
        "signers",
        (
            "demo_world.sql enrols demo.signer and demo.countersigner in "
            "mainline.signing_credential. Over HTTP this line asserts that TWO CREDENTIALS "
            "RESOLVED — mainline_demo_api.gate_run resolves both from that table before beat "
            "1 and the API answers 422 when one is missing — and NOT how they are spelled, "
            "because scenario.py lets a deployment override both subjects and the payload "
            "does not carry them. Run this against a local copy to see the spelling."
        ),
    ),
    (
        "unchanged",
        (
            "the demo needs no reset. gate-run's whole transaction ends in ROLLBACK "
            "(docs/deploy/gate-run-contract.md §2) and this line is the row counts the "
            "database itself took before that transaction opened and again after it was "
            "rolled back — not a promise this program makes about itself."
        ),
    ),
)

FOOTNOTES_LOCAL: tuple[tuple[str, str], ...] = (
    ("obligation", _NOTE_OBLIGATION),
    (
        "signers",
        (
            "the query asks mainline.signing_credential for exactly demo.signer and "
            "demo.countersigner, unrevoked, and prints the ones it found. A subject that is "
            "enrolled under some other name is not this line's business: these two are the "
            "ones demo_world.sql writes and the ones mainline_demo_api.scenario defaults to."
        ),
    ),
    (
        "refusal",
        (
            "ONE beat here, not four. seed_demo asks the database to merge the seeded permit "
            "inside a transaction it rolls back, and records the SQLSTATE and the exhibit it "
            "saw; that is the film's second beat. The forged-counter beat and the admission "
            "live in the deployed POST /v1/demo/gate-run and are checked by running this "
            "command with no --dsn."
        ),
    ),
    (
        "unchanged",
        (
            "the demo needs no reset. This line is the permit and mainline.merge_record read "
            "back AFTER the merge probe above was rolled back. docs/deploy/cloud-database.md "
            "§6: this is the property the whole demo rests on — no per-visitor state, no "
            "reset button, no cleanup sweeper."
        ),
    ),
)

#: `--repair` DID write, or tried to, and the word "unchanged" must not be allowed to imply
#: otherwise. The fact is about the merge PROBE, which is rolled back in both modes; the seed
#: files are a separate thing this run applied on purpose, and the note says so rather than
#: leaving an operator to infer which of the two the line covers.
_REPAIR_QUALIFIER = (
    " This run also APPLIED the two seed files, which is what --repair is; that is not what "
    "this line measures. Both files are idempotent and a second run writes nothing — "
    "docs/demo/DEMO-READY.md §7."
)

FOOTNOTES_LOCAL_REPAIR: tuple[tuple[str, str], ...] = tuple(
    (fact_id, note + _REPAIR_QUALIFIER if fact_id == "unchanged" else note)
    for fact_id, note in FOOTNOTES_LOCAL
)


def render(facts: list[Fact], header: list[str], notes: tuple[tuple[str, str], ...]) -> str:
    """The whole of stdout, as one string. Nothing here varies between two identical runs.

    THE NOTES ARE WRAPPED AND THE FACT LINES ARE NOT, and that is the same decision
    ``scripts/submission/seed_demo_state.py`` records at its ``CAMERA_WIDTH``: a paragraph
    that a terminal re-flows at whatever column the window happens to end on is a paragraph
    that looks different on the founder's machine from here, while the verification table
    "runs to whatever its observed values need — around 135 columns, mostly UUIDs — because it
    is a diagnostic the operator reads before recording, never a frame." Truncating a
    ``permit_id`` to make a table pretty would cost the one value the next command needs.
    """
    out: list[str] = ["MAINLINE demo-ready", *header, ""]
    out.extend(fact.line() for fact in facts)
    out.append("")
    by_id = {fact.fact_id for fact in facts}
    indent = " " * (len("note  ") + _ID_W + 2)
    for fact_id, note in notes:
        if fact_id in by_id:
            out.extend(
                textwrap.wrap(
                    note,
                    width=_NOTE_WIDTH,
                    initial_indent=f"note  {fact_id:<{_ID_W}}  ",
                    subsequent_indent=indent,
                    # `break_on_hyphens` defaults True and split `docs/deploy/cloud-` /
                    # `database.md §6` across two lines the first time these notes were
                    # printed. A file path a reader cannot copy in one selection is a
                    # citation that has stopped working.
                    break_on_hyphens=False,
                )
            )
    out.append("")
    passed = sum(1 for fact in facts if fact.ok)
    failed = len(facts) - passed
    if failed:
        out.append(
            f"VERDICT  NOT READY — {passed} of {len(facts)} facts PASS, {failed} FAILED. "
            "Do not roll: the line above says which world you are pointing at."
        )
    else:
        out.append(f"VERDICT  READY — {passed} of {len(facts)} facts PASS, 0 failed. Roll camera.")
    return "\n".join(out) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="demo_ready",
        description=(
            "Answer 'may I roll camera?' against the deployed demo, or against a local "
            "database, in one command and under ten seconds."
        ),
    )
    parser.add_argument(
        "--url",
        default=DEFAULT_BASE,
        help="the deployment to check over HTTP (default: the committed Function URL)",
    )
    parser.add_argument(
        "--dsn",
        default=None,
        help="check a LOCAL database instead, through scripts/deploy/seed_demo.py",
    )
    parser.add_argument(
        "--database",
        default=None,
        help="the database --dsn should select (default: the DSN's own path segment)",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--check",
        action="store_true",
        help="verify and write nothing. THE DEFAULT; accepted so a script can say so out loud",
    )
    mode.add_argument(
        "--repair",
        action="store_true",
        help="apply the seed files to a LOCAL scratch database, then verify. Never the cloud",
    )
    parser.add_argument("--timeout", type=float, default=30.0, help="per-request HTTP timeout")
    # FIVE, not twenty, and the number is `conftest.py`'s DEFAULT_PGCONNECT_TIMEOUT with its
    # reasoning intact: "a connect to a black-holed address raised ConnectionTimeout after
    # 130.1 s with no PGCONNECT_TIMEOUT and after 3.1 s at PGCONNECT_TIMEOUT=3… Five is chosen
    # over three because a cold container's first accept can be slow and a fixture that gives
    # up on a node that is genuinely coming up is its own kind of lie." libpq spends this once
    # per ADDRESS, and a host name that resolves to a dead ::1 first therefore costs it on
    # every one of this command's three connections — see `_slow_host_note`.
    parser.add_argument(
        "--connect-timeout",
        type=int,
        default=5,
        help="seconds libpq may spend on one address of --dsn's host (default 5)",
    )
    return parser


def _utf8(stream: Any) -> None:
    """Force UTF-8 on a stream, because "byte-identical" must not depend on a code page.

    Windows hands a redirected ``stdout`` the ANSI code page — ``cp1252`` on the machine this
    was written on — and an em dash in a prose column then raises ``UnicodeEncodeError`` and
    takes the whole report down AFTER the facts were measured. Measured here on 2026-08-16,
    before this call existed. Reconfiguring is also what makes two runs comparable with
    ``diff``: the same eight facts must produce the same bytes on a console, in a file and in
    CI. ``reconfigure`` is absent on a stream a test or a harness has already replaced, which
    is why the failure is suppressed rather than raised — the report is worth more than the
    encoding.
    """
    with contextlib.suppress(AttributeError, ValueError, OSError):
        stream.reconfigure(encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    _utf8(sys.stdout)
    _utf8(sys.stderr)
    args = build_parser().parse_args(argv)
    started = time.perf_counter()
    database = args.database or (urlsplit(args.dsn).path.lstrip("/") if args.dsn else "")

    try:
        guard_target(args.dsn, database, repair=args.repair)
    except ActionRequired as refusal:
        print(f"ACTION REQUIRED  {refusal}")
        return EXIT_ACTION_REQUIRED
    except Unreachable as refusal:
        print(f"USAGE  {refusal}", file=sys.stderr)
        return EXIT_USAGE

    try:
        if args.dsn:
            mode = (
                "--repair (applies the two seed files, then verifies)"
                if args.repair
                else "--check (read-only)"
            )
            header = [
                f"target    {_seed_demo().cluster_label(args.dsn)} -> {database}  (local database)",
                f"mode      {mode}",
                "asked by  scripts/deploy/seed_demo.py, plus two SELECTs this file owns",
            ]
            facts, connect_seconds = check_local(
                args.dsn, database, repair=args.repair, connect_timeout=args.connect_timeout
            )
            requests = 0
            notes = FOOTNOTES_LOCAL_REPAIR if args.repair else FOOTNOTES_LOCAL
            slow = _slow_host_note(args.dsn, connect_seconds)
        else:
            header = [
                f"target    {args.url.rstrip('/')}  (deployed)",
                "mode      --check (read-only; four GETs and the one permitted POST)",
                "asked by  the deployed API, over HTTP",
            ]
            # `requests` is what the connection COUNTED, never the five this file expects: a
            # run that gave up after two must not report five on stderr.
            facts, requests = check_live(args.url, timeout=args.timeout)
            notes = FOOTNOTES_LIVE
            slow = None
    except Unreachable as exc:
        print(f"USAGE  the target could not be asked: {exc}", file=sys.stderr)
        return EXIT_USAGE
    except Exception as exc:  # noqa: BLE001 - a driver or an origin can raise anything at all
        print(f"USAGE  {type(exc).__name__}: {' '.join(str(exc).split())[:400]}", file=sys.stderr)
        return EXIT_USAGE

    sys.stdout.write(render(facts, header, notes))
    # THE ELAPSED LINE IS ON STDERR AND THE BOUND IS ONLY CLAIMED OF THE LIVE CHECK.
    # §R1 sets ten seconds for "may I roll camera?", and that question is asked of the
    # DEPLOYMENT. The local path runs seed_demo's 27-relation census and its rolled-back merge
    # probe against whatever the node has spare, so its elapsed is reported and not graded.
    # Measured 2026-08-16 against the local node: 0.98 s through 127.0.0.1 and 15.7 s through
    # `localhost`, and the whole of that difference is the dead ::1 named by `_slow_host_note`
    # rather than anything the database did. Neither number changes the exit code — a slow
    # connect is a statement about a host name, not about the seeded world.
    elapsed = time.perf_counter() - started
    if args.dsn:
        tail = " (local; seed_demo's census and merge probe are not bound by the ten seconds)"
    else:
        over = "  OVER THE BOUND" if elapsed > SECONDS_BOUND else ""
        tail = f" over {requests} requests (bound {SECONDS_BOUND:.0f}s){over}"
    sys.stderr.write(f"elapsed {elapsed:.1f}s{tail}\n")
    if slow:
        sys.stderr.write(f"  note: {slow}\n")
    return EXIT_OK if all(fact.ok for fact in facts) else EXIT_NOT_READY


if __name__ == "__main__":
    raise SystemExit(main())
