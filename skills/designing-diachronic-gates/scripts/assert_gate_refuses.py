#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Assert that a CockroachDB gate REFUSES an illegal history, with the exhibit it must name.

A gate that has never been observed refusing is a comment. This script spins a throwaway
single-node CockroachDB, applies the schema an agent just scaffolded, replays a history
that must be illegal, and **fails unless the database raises the expected SQLSTATE and the
expected exhibit** — the constraint name, or for ``P0001`` the raising object recovered
from the message. Asserting only the SQLSTATE is not an assertion: *"an exception was
raised"* is worthless in a system whose deliverable is the diagnosis.

    # the gate you just wrote, on a node this script creates and destroys
    python assert_gate_refuses.py --schema gate.sql --prelude legal.sql \
        --history illegal.sql --expect-sqlstate 23514 \
        --expect-exhibit gate_closed_when_issued

    # against a cluster you already have (a throwaway database is created and dropped)
    python assert_gate_refuses.py --dsn "$DSN" --schema gate.sql ...

    # the built-in reference gate, welded and unwelded six ways: proves the assertion
    # can go RED, which is the only thing that makes a green run mean anything
    python assert_gate_refuses.py --self-test

    # no database anywhere: prove the diagnostic parser itself
    python assert_gate_refuses.py --parser-self-test

Exit status: ``0`` refused exactly as asserted · ``1`` it did not · ``2`` the arguments or
the environment were wrong (which is never reported as a passing gate).

Standard library only. The cluster is reached through the ``cockroach`` binary if one is on
PATH, and through ``docker`` otherwise; no driver is installed, imported or required.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

# ── the wire shapes `cockroach sql` prints on failure ────────────────────────────────────
# Verified against cockroachdb/cockroach v26.2.5 on 2026-08-10. A CHECK violation prints
# ERROR / SQLSTATE / CONSTRAINT; a foreign-key violation prints those plus DETAIL; a
# PL/pgSQL RAISE prints ERROR / SQLSTATE and NO CONSTRAINT line at all, which is why the
# P0001 exhibit has to be recovered from the message and is reported as `parsed`.
_ERROR = re.compile(r"^ERROR:\s*(?P<body>.*)$")
_SQLSTATE = re.compile(r"^SQLSTATE:\s*(?P<code>[0-9A-Za-z]{5})\s*$")
_CONSTRAINT = re.compile(r"^CONSTRAINT:\s*(?P<name>\S+)\s*$")
_FIELD_LINE = re.compile(r"^(SQLSTATE|CONSTRAINT|DETAIL|HINT|NOTICE|WARNING|TIP):")
# `<PREFIX>: … refused by <schema>.<object> …` — the message convention that makes a
# P0001 exhibit recoverable. Anything else yields no exhibit rather than a guessed one.
_RAISED_BY = re.compile(r"refused by\s+(?P<object>[A-Za-z_][A-Za-z0-9_.$]*)")

_STARTUP_TIMEOUT_S = 90.0
_STATEMENT_TIMEOUT_S = 120.0
_POLL_INTERVAL_S = 1.0
_DEFAULT_IMAGE = "cockroachdb/cockroach:v26.2.5"
_ADMITTED = "ADMITTED"


def _say(text: str = "") -> None:
    """Write one line to stdout.

    A single output funnel: the caller never touches the stream, and the repository's
    ban on bare ``print`` outside a CLI entry point stays enforceable without scattering
    suppression comments through a file a stranger is meant to read.
    """
    sys.stdout.write(text + "\n")


class EnvironmentProblem(RuntimeError):
    """The environment could not answer the question — exit 2, never exit 0.

    Distinct from a failed assertion on purpose. "No CockroachDB was reachable" and
    "the gate admitted an illegal history" are opposite facts, and a harness that
    reports the first as the second is the exact defect this script exists to refuse.
    """


# ── outcomes ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Outcome:
    """What the database did with one batch of SQL."""

    admitted: bool
    sqlstate: str | None
    exhibit: str | None
    exhibit_source: str
    message: str
    raw: str

    def describe(self) -> str:
        """Render the outcome as one line a human can read in a CI log."""
        if self.admitted:
            return _ADMITTED
        source = "" if self.exhibit_source == "reported" else f" ({self.exhibit_source})"
        return f"{self.sqlstate} / {self.exhibit or '<no exhibit>'}{source}"


def parse_outcome(returncode: int, stdout: str, stderr: str) -> Outcome:
    """Turn one ``cockroach sql`` invocation into an Outcome.

    The exhibit is taken from the ``CONSTRAINT:`` line when the server reported one and
    from the message otherwise, and which of the two happened is carried in
    ``exhibit_source``. A run whose exhibits were inferred must never be
    indistinguishable from a run whose exhibits were reported.
    """
    text = stderr if stderr.strip() else stdout
    if returncode == 0 and not _has_error(text):
        return Outcome(True, None, None, "none", "", text)

    message_lines: list[str] = []
    sqlstate: str | None = None
    constraint: str | None = None
    collecting = False
    for line in text.splitlines():
        stripped = line.strip()
        error = _ERROR.match(stripped)
        if error is not None:
            message_lines = [error.group("body").strip()]
            collecting = True
            continue
        state = _SQLSTATE.match(stripped)
        if state is not None:
            sqlstate = state.group("code")
            collecting = False
            continue
        name = _CONSTRAINT.match(stripped)
        if name is not None:
            constraint = name.group("name").strip('"')
            collecting = False
            continue
        if _FIELD_LINE.match(stripped):
            collecting = False
            continue
        if collecting and stripped:
            message_lines.append(stripped)

    message = " ".join(message_lines).strip()
    source = "reported"
    if constraint is None:
        raised = _RAISED_BY.search(message)
        constraint = raised.group("object") if raised is not None else None
        source = "parsed" if constraint else "none"
    return Outcome(False, sqlstate, constraint, source, message, text)


def _has_error(text: str) -> bool:
    return any(_ERROR.match(line.strip()) for line in text.splitlines())


@dataclass(frozen=True)
class Verdict:
    """The result of comparing an Outcome against what was asserted."""

    ok: bool
    expected: str
    observed: str
    failures: list[str] = field(default_factory=list)


def judge(outcome: Outcome, *, expect_sqlstate: str | None, expect_exhibit: str | None) -> Verdict:
    """Compare an outcome against the asserted refusal.

    ``expect_sqlstate=None`` asserts the history is ADMITTED, which is the shape the
    unwelding matrix needs: an unwelded gate that still refuses has not been unwelded.
    """
    expected = _ADMITTED if expect_sqlstate is None else f"{expect_sqlstate} / {expect_exhibit}"
    failures: list[str] = []
    if expect_sqlstate is None:
        if not outcome.admitted:
            failures.append(
                f"expected the history to be ADMITTED, but the database refused it: "
                f"{outcome.describe()} — {outcome.message}"
            )
        return Verdict(not failures, expected, outcome.describe(), failures)

    if outcome.admitted:
        failures.append(
            "the database ADMITTED the illegal history. Nothing refused it: no CHECK, no "
            "foreign key, no trigger. This is the failure this script exists to find."
        )
        return Verdict(False, expected, outcome.describe(), failures)
    if outcome.sqlstate != expect_sqlstate:
        failures.append(
            f"SQLSTATE is {outcome.sqlstate}, expected {expect_sqlstate}. The gate refused, "
            f"but by a different mechanism than the one asserted: {outcome.message}"
        )
    if expect_exhibit is not None and outcome.exhibit != expect_exhibit:
        failures.append(
            f"exhibit is {outcome.exhibit!r}, expected {expect_exhibit!r}. The refusal is not "
            "the one that was asserted, and the constraint name is what a reader is shown."
        )
    if expect_exhibit is not None and outcome.exhibit_source == "none":
        failures.append(
            "no exhibit could be recovered: the server reported no CONSTRAINT and the message "
            "does not follow the `refused by <object>` convention, so this refusal cannot be "
            "named. Fix the RAISE message rather than weakening the assertion."
        )
    return Verdict(not failures, expected, outcome.describe(), failures)


# ── talking to a cluster ─────────────────────────────────────────────────────────────────


def _which(name: str) -> str | None:
    return shutil.which(name)


def _run(argv: list[str], *, stdin: str | None = None, timeout: float) -> tuple[int, str, str]:
    """Run one child process and return (returncode, stdout, stderr).

    The single subprocess funnel in this file. Every argument vector is built here from
    literals and paths this script owns; nothing is passed through a shell.
    """
    try:
        completed = subprocess.run(  # noqa: S603 — argv is a list, shell=False, no user string is interpolated
            argv,
            input=stdin,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError as exc:
        raise EnvironmentProblem(f"{argv[0]} is not executable here: {exc}") from exc
    except subprocess.TimeoutExpired as exc:
        raise EnvironmentProblem(
            f"{argv[0]} did not return within {timeout}s. A gate assertion that hangs is not "
            "a passing gate assertion."
        ) from exc
    return completed.returncode, completed.stdout or "", completed.stderr or ""


class Cluster:
    """A CockroachDB a batch of SQL can be sent to, in a database this object owns."""

    def __init__(self, label: str) -> None:
        """Record the human-readable label used in diagnostics."""
        self.label = label

    def execute(self, sql: str, *, database: str) -> Outcome:
        """Send one batch of SQL and report what the database did with it."""
        raise NotImplementedError

    def close(self) -> None:
        """Release whatever this object created. Safe to call twice."""

    def fresh_database(self) -> str:
        """Create and return the name of a database no other run is using."""
        name = f"gate_probe_{secrets.token_hex(4)}"
        outcome = self.execute(f"CREATE DATABASE {name};", database="defaultdb")
        if not outcome.admitted:
            raise EnvironmentProblem(f"could not create a probe database: {outcome.message}")
        return name

    def drop_database(self, name: str) -> None:
        """Drop a probe database, ignoring the case where it never existed."""
        self.execute(f"DROP DATABASE IF EXISTS {name} CASCADE;", database="defaultdb")


class BinaryCluster(Cluster):
    """Reached with the ``cockroach`` binary over a DSN."""

    def __init__(self, dsn: str, binary: str, label: str) -> None:
        """Bind to a DSN and the ``cockroach`` binary that will carry the statements."""
        super().__init__(label)
        self._dsn = dsn
        self._binary = binary

    def execute(self, sql: str, *, database: str) -> Outcome:
        """Send one batch through ``cockroach sql``, reading the batch from stdin."""
        url = _with_database(self._dsn, database)
        code, out, err = _run(
            [self._binary, "sql", "--url", url, "--format", "tsv", "--set", "errexit=true"],
            stdin=sql,
            timeout=_STATEMENT_TIMEOUT_S,
        )
        return parse_outcome(code, out, err)


class DockerCluster(Cluster):
    """A throwaway node this script started with ``docker run`` and will remove."""

    def __init__(self, container: str, docker: str, label: str) -> None:
        """Bind to a running container id and the ``docker`` binary that reaches it."""
        super().__init__(label)
        self._container = container
        self._docker = docker
        self._closed = False

    def execute(self, sql: str, *, database: str) -> Outcome:
        """Send one batch through ``cockroach sql`` inside the container."""
        code, out, err = _run(
            [
                self._docker,
                "exec",
                "-i",
                self._container,
                "./cockroach",
                "sql",
                "--insecure",
                "--database",
                database,
                "--format",
                "tsv",
                "--set",
                "errexit=true",
            ],
            stdin=sql,
            timeout=_STATEMENT_TIMEOUT_S,
        )
        return parse_outcome(code, out, err)

    def close(self) -> None:
        """Remove the container. A leaked node is a leaked port on the next run."""
        if self._closed:
            return
        self._closed = True
        _run([self._docker, "rm", "-f", self._container], timeout=60.0)


def _with_database(dsn: str, database: str) -> str:
    """Point a DSN at a different database without disturbing its query string."""
    head, _, tail = dsn.partition("?")
    base, _, _ = head.rpartition("/")
    if not base:
        base = head.rstrip("/")
    url = f"{base}/{database}"
    return f"{url}?{tail}" if tail else url


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def start_local_node(binary: str) -> tuple[Cluster, subprocess.Popen[str], Path]:
    """Start ``cockroach start-single-node --insecure`` on a free loopback port."""
    port = _free_port()
    store = Path(tempfile.mkdtemp(prefix="gate-probe-store-"))
    process = subprocess.Popen(  # noqa: S603 — argv is a list, shell=False, every element is ours
        [
            binary,
            "start-single-node",
            "--insecure",
            f"--listen-addr=127.0.0.1:{port}",
            "--http-addr=127.0.0.1:0",
            f"--store={store}",
            "--cache=.15",
            "--max-sql-memory=.15",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    dsn = f"postgresql://root@127.0.0.1:{port}/defaultdb?sslmode=disable"
    cluster = BinaryCluster(dsn, binary, f"local cockroach on :{port}")
    _await_sql(cluster, lambda: process.poll() is None)
    return cluster, process, store


def start_docker_node(docker: str, image: str) -> DockerCluster:
    """Start a throwaway in-memory single node in a container and wait for SQL."""
    # No --listen-addr and no published port, deliberately. Statements are carried by
    # `docker exec`, so the node never has to be reachable from the host — and on v26.2.5
    # an --insecure node REFUSES a non-loopback listen address outright ("hostname of
    # listen_addr must be \"127.0.0.1\" or \"localhost\""), measured 2026-08-10. A node
    # with no authentication that is reachable from the LAN is the failure that restriction
    # exists to prevent, and inheriting the container default keeps us on the right side of
    # it without an argument.
    code, out, err = _run(
        [
            docker,
            "run",
            "-d",
            "--rm",
            "--name",
            f"gate-probe-{secrets.token_hex(4)}",
            image,
            "start-single-node",
            "--insecure",
            "--store=type=mem,size=1GiB",
        ],
        timeout=300.0,
    )
    if code != 0:
        raise EnvironmentProblem(
            f"docker could not start {image}: {err.strip() or out.strip()}. Pull it first "
            f"(`docker pull {image}`) if this machine has never seen the image."
        )
    cluster = DockerCluster(out.strip(), docker, f"docker {image}")
    try:
        _await_sql(cluster, lambda: True)
    except EnvironmentProblem:
        cluster.close()
        raise
    return cluster


def _await_sql(cluster: Cluster, alive: object) -> None:
    """Block until the node answers SQL, or fail with a reason rather than a timeout."""
    deadline = time.monotonic() + _STARTUP_TIMEOUT_S
    last = ""
    while time.monotonic() < deadline:
        if callable(alive) and not alive():
            raise EnvironmentProblem("the node exited before it answered SQL")
        outcome = cluster.execute("SELECT 1;", database="defaultdb")
        if outcome.admitted:
            return
        last = outcome.message
        time.sleep(_POLL_INTERVAL_S)
    raise EnvironmentProblem(
        f"{cluster.label} never answered SQL within {_STARTUP_TIMEOUT_S:.0f}s. Last error: {last}"
    )


# ── the reference gate: PROJECT, PIN, REFUSE ─────────────────────────────────────────────
# This is the schema `--self-test` welds and unwelds. It is the smallest complete instance
# of the idiom, and every line of it was executed against CockroachDB v26.2.5 on 2026-08-10.

REFERENCE_SCHEMA = """
-- The authority relation. `severity_class` decides what BLOCKS; the inserter does not.
CREATE TABLE severity_class (
  severity    INT8 NOT NULL,
  is_blocking BOOL NOT NULL,
  CONSTRAINT pk_severity_class PRIMARY KEY (severity)
);
INSERT INTO severity_class (severity, is_blocking)
VALUES (1, false), (2, false), (3, true), (4, true), (5, true);

-- The subject: the protected branch's head row.
--   open_blocking is PROJECTED. It is written by a trigger from `obligation` joined to
--   `severity_class`, never by the writer, and the gate reads only this scalar.
--   gate_epoch is the PIN's target. It increments when a new blocking obligation lands.
CREATE TABLE subject (
  subject_id    INT8 NOT NULL,
  state         STRING NOT NULL DEFAULT 'open',
  gate_epoch    INT8 NOT NULL DEFAULT 0,
  open_blocking INT8 NOT NULL DEFAULT 0,
  CONSTRAINT pk_subject PRIMARY KEY (subject_id),
  CONSTRAINT subject_epoch_target UNIQUE (subject_id, gate_epoch),
  CONSTRAINT subject_counter_nonneg CHECK (open_blocking >= 0),
  -- THE REFUSAL. A plain-column CHECK over a projected scalar: no subquery, no trigger,
  -- no application. It refuses for every writer, forever, including the one nobody
  -- anticipated. Its NAME is the exhibit.
  CONSTRAINT gate_closed_when_issued CHECK (state <> 'closed' OR open_blocking = 0)
);

CREATE TABLE obligation (
  obligation_id INT8 NOT NULL,
  subject_id    INT8 NOT NULL,
  severity      INT8 NOT NULL,
  discharged    BOOL NOT NULL DEFAULT false,
  CONSTRAINT pk_obligation PRIMARY KEY (obligation_id),
  CONSTRAINT fk_obligation_subject FOREIGN KEY (subject_id)
    REFERENCES subject (subject_id) ON UPDATE RESTRICT ON DELETE RESTRICT
);

-- THE PIN. The completed transition takes a composite foreign key onto
-- (subject_id, gate_epoch) under ON UPDATE RESTRICT. Once this row exists the subject's
-- epoch is physically immutable, so an obligation arriving afterwards -- which must bump
-- the epoch -- cannot be attached at all. Not "is detected". Cannot be attached.
CREATE TABLE completion (
  subject_id INT8 NOT NULL,
  gate_epoch INT8 NOT NULL,
  CONSTRAINT pk_completion PRIMARY KEY (subject_id),
  CONSTRAINT completion_pin FOREIGN KEY (subject_id, gate_epoch)
    REFERENCES subject (subject_id, gate_epoch) ON UPDATE RESTRICT ON DELETE RESTRICT
);

-- THE PROJECTION. Derived from the authority relation, never from the inserter, and it
-- RAISES when the authority row is missing: absence of evidence refuses, it does not
-- default to admissible.
CREATE FUNCTION fn_project_open_blocking() RETURNS TRIGGER LANGUAGE PLpgSQL AS $fn$
DECLARE
  v_subject  INT8;
  v_blocking BOOL;
  v_count    INT8;
BEGIN
  IF TG_OP = 'DELETE' THEN
    v_subject := (OLD).subject_id;
  ELSE
    v_subject := (NEW).subject_id;
    SELECT sc.is_blocking INTO v_blocking
      FROM severity_class sc WHERE sc.severity = (NEW).severity;
    IF v_blocking IS NULL THEN
      RAISE EXCEPTION USING ERRCODE = 'P0001',
        MESSAGE = 'GATE: refused by fn_project_open_blocking'
                  || ' — no severity_class row for severity ' || (NEW).severity::STRING;
    END IF;
  END IF;

  SELECT count(*) INTO v_count
    FROM obligation o JOIN severity_class sc ON sc.severity = o.severity
   WHERE o.subject_id = v_subject AND o.discharged = false AND sc.is_blocking;

  IF TG_OP = 'INSERT' AND v_blocking THEN
    UPDATE subject s SET open_blocking = v_count, gate_epoch = s.gate_epoch + 1
     WHERE s.subject_id = v_subject;
  ELSE
    UPDATE subject s SET open_blocking = v_count WHERE s.subject_id = v_subject;
  END IF;

  IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
  RETURN NEW;
END $fn$;

CREATE TRIGGER trg_project_open_blocking
AFTER INSERT OR UPDATE OR DELETE ON obligation
FOR EACH ROW EXECUTE FUNCTION fn_project_open_blocking();

-- THE DRIFT CHECK. The projection is enforced, never trusted: the completing transition
-- re-derives the count from the base tables and refuses when the derivation disagrees.
-- It deliberately does NOT pre-empt the CHECK -- it fires only when the counter reads
-- zero -- because a synthetic 23514 carries no constraint name, and the name is the
-- exhibit. BEFORE, not AFTER: the table's CHECKs are evaluated on the row this function
-- returns, so an AFTER trigger could never refuse anything the CHECKs had already passed.
CREATE FUNCTION fn_subject_close_gate() RETURNS TRIGGER LANGUAGE PLpgSQL AS $fn$
DECLARE
  v_derived INT8;
BEGIN
  SELECT count(*) INTO v_derived
    FROM obligation o JOIN severity_class sc ON sc.severity = o.severity
   WHERE o.subject_id = (NEW).subject_id AND o.discharged = false AND sc.is_blocking;
  IF v_derived <> 0 AND (NEW).open_blocking = 0 THEN
    RAISE EXCEPTION USING ERRCODE = 'P0001',
      MESSAGE = 'GATE: refused by fn_subject_close_gate — re-derived open obligation count'
                || ' is ' || v_derived::STRING || ' while the projected counter reads zero';
  END IF;
  RETURN NEW;
END $fn$;

CREATE TRIGGER subject_close_gate BEFORE UPDATE ON subject
  FOR EACH ROW WHEN ((NEW).state = 'closed' AND (OLD).state <> 'closed')
  EXECUTE FUNCTION fn_subject_close_gate();
"""


@dataclass(frozen=True)
class Case:
    """One illegal history, its legal prelude, and what the welded gate must do with it."""

    name: str
    prelude: str
    history: str
    sqlstate: str | None
    exhibit: str | None
    why: str


CASES: dict[str, Case] = {
    "close_with_open_obligation": Case(
        name="close_with_open_obligation",
        prelude=(
            "INSERT INTO subject (subject_id) VALUES (101);\n"
            "INSERT INTO obligation (obligation_id, subject_id, severity) VALUES (1101, 101, 4);\n"
        ),
        history="UPDATE subject SET state = 'closed' WHERE subject_id = 101;\n",
        sqlstate="23514",
        exhibit="gate_closed_when_issued",
        why="the projected counter is non-zero, so the plain-column CHECK refuses the transition",
    ),
    "attach_after_completion": Case(
        name="attach_after_completion",
        prelude=(
            "INSERT INTO subject (subject_id) VALUES (102);\n"
            "INSERT INTO obligation (obligation_id, subject_id, severity) VALUES (1102, 102, 4);\n"
            "UPDATE obligation SET discharged = true WHERE obligation_id = 1102;\n"
            "BEGIN;\n"
            "UPDATE subject SET state = 'closed' WHERE subject_id = 102;\n"
            "INSERT INTO completion (subject_id, gate_epoch)\n"
            "  SELECT subject_id, gate_epoch FROM subject WHERE subject_id = 102;\n"
            "COMMIT;\n"
        ),
        history=(
            "INSERT INTO obligation (obligation_id, subject_id, severity) VALUES (1103, 102, 5);\n"
        ),
        sqlstate="23514",
        exhibit="gate_closed_when_issued",
        why=(
            "the projection lands on a completed subject and the CHECK fires first; the PIN "
            "is the second, independent refusal underneath it (see the check_dropped row)"
        ),
    ),
    "disarm_the_counter": Case(
        name="disarm_the_counter",
        prelude=(
            "INSERT INTO subject (subject_id) VALUES (104);\n"
            "INSERT INTO obligation (obligation_id, subject_id, severity) VALUES (1104, 104, 5);\n"
            "UPDATE subject SET open_blocking = 0 WHERE subject_id = 104;\n"
        ),
        history="UPDATE subject SET state = 'closed' WHERE subject_id = 104;\n",
        sqlstate="P0001",
        exhibit="fn_subject_close_gate",
        why=(
            "a direct UPDATE zeroed the counter, which the projection trigger does not defend "
            "because it is armed on `obligation`; the completing transition re-derives and "
            "refuses on drift"
        ),
    ),
}


@dataclass(frozen=True)
class Unwelding:
    """One deliberate weakening of the schema, and what it must do to one case."""

    name: str
    sql: str
    case: str
    sqlstate: str | None
    exhibit: str | None
    claim: str


UNWELDINGS: tuple[Unwelding, ...] = (
    Unwelding(
        name="check_dropped",
        sql="ALTER TABLE subject DROP CONSTRAINT gate_closed_when_issued;",
        case="close_with_open_obligation",
        sqlstate=None,
        exhibit=None,
        claim="drop the CHECK and the illegal close is ADMITTED — the CHECK is load-bearing",
    ),
    Unwelding(
        name="check_dropped_pin_survives",
        sql="ALTER TABLE subject DROP CONSTRAINT gate_closed_when_issued;",
        case="attach_after_completion",
        sqlstate="23503",
        exhibit="completion_pin",
        claim="REFUSAL DEPTH 2: with the CHECK gone the epoch pin still refuses, by itself",
    ),
    Unwelding(
        name="pin_dropped",
        sql=(
            "ALTER TABLE completion DROP CONSTRAINT completion_pin;\n"
            "ALTER TABLE subject DROP CONSTRAINT gate_closed_when_issued;"
        ),
        case="attach_after_completion",
        sqlstate=None,
        exhibit=None,
        claim="drop BOTH and a precursor can be attached to a completed subject — ADMITTED",
    ),
    Unwelding(
        name="projection_disabled",
        sql="ALTER TABLE obligation DISABLE TRIGGER trg_project_open_blocking;",
        case="close_with_open_obligation",
        sqlstate="P0001",
        exhibit="fn_subject_close_gate",
        claim="REFUSAL DEPTH 2: with the projection disabled the re-derivation refuses on drift",
    ),
    Unwelding(
        name="gate_trigger_disabled",
        sql="ALTER TABLE subject DISABLE TRIGGER subject_close_gate;",
        case="disarm_the_counter",
        sqlstate=None,
        exhibit=None,
        claim="disable the gate trigger and a disarmed counter closes the subject — ADMITTED",
    ),
    Unwelding(
        name="fully_unwelded",
        sql=(
            "ALTER TABLE obligation DISABLE TRIGGER trg_project_open_blocking;\n"
            "ALTER TABLE subject DISABLE TRIGGER subject_close_gate;"
        ),
        case="close_with_open_obligation",
        sqlstate=None,
        exhibit=None,
        claim="both triggers off: the counter never moves, nothing re-derives — ADMITTED",
    ),
)


# ── running one assertion ────────────────────────────────────────────────────────────────


def run_assertion(
    cluster: Cluster,
    *,
    schema: str,
    prelude: str,
    history: str,
    expect_sqlstate: str | None,
    expect_exhibit: str | None,
    unweld: str = "",
) -> tuple[Verdict, Outcome]:
    """Apply a schema to a fresh database, replay a history, and judge the outcome."""
    database = cluster.fresh_database()
    try:
        applied = cluster.execute(schema, database=database)
        if not applied.admitted:
            raise EnvironmentProblem(
                "the schema itself did not apply, so nothing was asserted about the gate: "
                f"{applied.sqlstate} {applied.message}"
            )
        if unweld:
            weakened = cluster.execute(unweld, database=database)
            if not weakened.admitted:
                raise EnvironmentProblem(
                    f"the unwelding statement failed, so the matrix row is meaningless: "
                    f"{weakened.sqlstate} {weakened.message}"
                )
        if prelude.strip():
            legal = cluster.execute(prelude, database=database)
            if not legal.admitted:
                raise EnvironmentProblem(
                    "the LEGAL prelude was refused. The history under test never ran, so a "
                    f"refusal here proves nothing about the gate: {legal.sqlstate} {legal.message}"
                )
        outcome = cluster.execute(history, database=database)
    finally:
        cluster.drop_database(database)
    return judge(outcome, expect_sqlstate=expect_sqlstate, expect_exhibit=expect_exhibit), outcome


def self_test(cluster: Cluster) -> int:
    """Weld the reference gate, then unweld it six ways, and require every row to hold.

    Three of the six rows must end in ADMITTED. Those are the rows that prove this script
    can go red; without them a green run means only that the script never fails.
    """
    rows: list[tuple[str, str, str, bool]] = []
    failures = 0

    for case in CASES.values():
        verdict, _ = run_assertion(
            cluster,
            schema=REFERENCE_SCHEMA,
            prelude=case.prelude,
            history=case.history,
            expect_sqlstate=case.sqlstate,
            expect_exhibit=case.exhibit,
        )
        rows.append(("welded", case.name, f"{verdict.expected} → {verdict.observed}", verdict.ok))
        failures += 0 if verdict.ok else 1
        for failure in verdict.failures:
            _say(f"    ! {failure}")

    for unwelding in UNWELDINGS:
        case = CASES[unwelding.case]
        verdict, _ = run_assertion(
            cluster,
            schema=REFERENCE_SCHEMA,
            prelude=case.prelude,
            history=case.history,
            expect_sqlstate=unwelding.sqlstate,
            expect_exhibit=unwelding.exhibit,
            unweld=unwelding.sql,
        )
        rows.append(
            (unwelding.name, case.name, f"{verdict.expected} → {verdict.observed}", verdict.ok)
        )
        failures += 0 if verdict.ok else 1
        for failure in verdict.failures:
            _say(f"    ! {failure}")

    width = max(len(row[0]) for row in rows)
    _say("")
    _say(f"unwelding matrix — {cluster.label}")
    _say("-" * 96)
    for variant, case_name, detail, ok in rows:
        _say(f"[{'PASS' if ok else 'FAIL'}] {variant:<{width}}  {case_name:<28}  {detail}")
    _say("-" * 96)
    admitted = sum(1 for row in rows if "→ ADMITTED" in row[2])
    _say(f"{len(rows)} rows, {failures} wrong, {admitted} of them proving the assertion can fail")
    return 0 if failures == 0 else 1


def parser_self_test() -> int:
    """Prove the diagnostic parser on recorded v26.2.5 output, with no database at all.

    Every fixture below is real output captured from cockroachdb/cockroach v26.2.5 on
    2026-08-10, not written from memory of what the server prints.
    """
    fixtures: list[tuple[str, str, str, str | None, str | None, str]] = [
        (
            "check violation names its constraint",
            (
                "ERROR: failed to satisfy CHECK constraint ((state != 'closed':::STRING) OR "
                "(open_blocking = 0:::INT8))\nSQLSTATE: 23514\n"
                'CONSTRAINT: gate_closed_when_issued\nFailed running "sql"'
            ),
            "23514",
            "gate_closed_when_issued",
            "reported",
            "",
        ),
        (
            "fk violation names its constraint, past a DETAIL line",
            (
                'ERROR: update on table "s" violates foreign key constraint "completion_pin" '
                'on table "completion"\nSQLSTATE: 23503\n'
                "DETAIL: Key (subject_id, gate_epoch)=(1, 1) is still referenced from table "
                '"completion".\nCONSTRAINT: completion_pin\nFailed running "sql"'
            ),
            "23503",
            "completion_pin",
            "reported",
            "",
        ),
        (
            "P0001 carries NO constraint line; the exhibit is parsed from the message",
            (
                "ERROR: GATE: refused by fn_subject_close_gate — re-derived open obligation "
                "count is 1 while the projected counter reads zero\nSQLSTATE: P0001\n"
                'Failed running "sql"'
            ),
            "P0001",
            "fn_subject_close_gate",
            "parsed",
            "",
        ),
        (
            "a P0001 that does not follow the message convention yields NO exhibit",
            'ERROR: something went wrong\nSQLSTATE: P0001\nFailed running "sql"',
            "P0001",
            None,
            "none",
            "",
        ),
    ]
    failed = 0
    for name, text, sqlstate, exhibit, source, _ in fixtures:
        outcome = parse_outcome(1, "", text)
        ok = (
            not outcome.admitted
            and outcome.sqlstate == sqlstate
            and outcome.exhibit == exhibit
            and outcome.exhibit_source == source
        )
        failed += 0 if ok else 1
        _say(f"[{'PASS' if ok else 'FAIL'}] {name}: {outcome.describe()}")

    admitted = parse_outcome(0, "UPDATE 1\n", "")
    ok = admitted.admitted
    failed += 0 if ok else 1
    _say(f"[{'PASS' if ok else 'FAIL'}] a clean run is reported as ADMITTED, not as a refusal")

    # The judge must call an admission a failure. A harness that cannot say "the gate let
    # it through" has nothing to say at all.
    red = judge(admitted, expect_sqlstate="23514", expect_exhibit="gate_closed_when_issued")
    wrong_name = judge(
        parse_outcome(1, "", "ERROR: x\nSQLSTATE: 23514\nCONSTRAINT: some_other_check"),
        expect_sqlstate="23514",
        expect_exhibit="gate_closed_when_issued",
    )
    negatives = (("an admission is a FAIL", red), ("a wrong exhibit is a FAIL", wrong_name))
    for label, verdict in negatives:
        failed += 0 if not verdict.ok else 1
        _say(f"[{'PASS' if not verdict.ok else 'FAIL'}] {label}")

    _say("")
    _say("parser self-test: " + ("OK" if failed == 0 else f"{failed} case(s) wrong"))
    return 0 if failed == 0 else 1


# ── entry point ──────────────────────────────────────────────────────────────────────────


def _use_utf8_io() -> None:
    """Force UTF-8 on stdout and stderr, whatever the console's code page says.

    Not cosmetic. `--print-schema` emits SQL containing non-ASCII punctuation, and on a
    machine whose default encoding is not UTF-8 (a Windows console, most obviously) the
    redirected file comes back mojibake — which then fails to decode when it is read as a
    schema. That failure exits non-zero and can be mistaken for "the gate went red",
    which is the one confusion this script must never produce.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8")


def _read(path: str | None) -> str:
    if not path:
        return ""
    try:
        return Path(path).read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise EnvironmentProblem(
            f"{path} is not valid UTF-8 ({exc.reason} at byte {exc.start}). A SQL file that "
            "lost its encoding on the way here cannot be asserted about: this is an "
            "environment failure (exit 2), NOT a gate that refused."
        ) from exc
    except OSError as exc:
        raise EnvironmentProblem(f"cannot read {path}: {exc}") from exc


def _acquire_cluster(args: argparse.Namespace) -> tuple[Cluster, list[object]]:
    """Return a cluster and the resources the caller must release afterwards."""
    cleanup: list[object] = []
    if args.dsn:
        binary = _which("cockroach")
        if binary is None:
            raise EnvironmentProblem(
                "--dsn needs the `cockroach` binary on PATH to carry the statements. Without "
                "it, omit --dsn and let this script start a throwaway node with docker."
            )
        return BinaryCluster(args.dsn, binary, f"cluster at {args.dsn.split('@')[-1]}"), cleanup

    if not args.docker_only:
        binary = _which("cockroach")
        if binary is not None:
            cluster, process, store = start_local_node(binary)
            cleanup.extend((process, store))
            return cluster, cleanup

    docker = _which("docker")
    if docker is None:
        raise EnvironmentProblem(
            "no CockroachDB is reachable: neither `cockroach` nor `docker` is on PATH and no "
            "--dsn was given. This is an environment problem and is reported as one (exit 2); "
            "it is NOT a passing gate assertion."
        )
    cluster = start_docker_node(docker, args.image)
    cleanup.append(cluster)
    return cluster, cleanup


def _release(cleanup: list[object]) -> None:
    for item in reversed(cleanup):
        if isinstance(item, DockerCluster):
            item.close()
        elif isinstance(item, subprocess.Popen):
            item.terminate()
            try:
                item.wait(timeout=30)
            except subprocess.TimeoutExpired:
                item.kill()
        elif isinstance(item, Path):
            shutil.rmtree(item, ignore_errors=True)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Assert a CockroachDB gate refuses an illegal history with a named exhibit.",
        epilog="With no --dsn, a throwaway node is started and destroyed by this script.",
    )
    parser.add_argument("--schema", help="DDL for the gate under test")
    parser.add_argument("--prelude", help="legal setup that MUST succeed before the history")
    parser.add_argument("--history", help="the illegal history that MUST be refused")
    parser.add_argument("--expect-sqlstate", help="e.g. 23514, 23503, 23505, P0001")
    parser.add_argument(
        "--expect-exhibit",
        help="the constraint name, or for P0001 the raising object named in the message",
    )
    parser.add_argument("--dsn", help="use this cluster instead of starting one")
    parser.add_argument("--image", default=_DEFAULT_IMAGE, help="docker image for the node")
    parser.add_argument(
        "--docker-only", action="store_true", help="ignore a `cockroach` binary on PATH"
    )
    parser.add_argument("--json", action="store_true", help="print the verdict as JSON")
    parser.add_argument(
        "--self-test", action="store_true", help="weld and unweld the reference gate"
    )
    parser.add_argument(
        "--parser-self-test", action="store_true", help="prove the parser; needs no database"
    )
    parser.add_argument(
        "--print-schema", action="store_true", help="print the reference gate DDL and exit"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Parse arguments, obtain a cluster, run the requested assertion, report."""
    _use_utf8_io()
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.print_schema:
        _say(REFERENCE_SCHEMA.strip())
        return 0
    if args.parser_self_test:
        return parser_self_test()
    if not args.self_test:
        missing = [flag for flag in ("schema", "history") if not getattr(args, flag)]
        if missing:
            parser.error("--" + ", --".join(missing) + " required (or use --self-test)")
        if not args.expect_sqlstate:
            parser.error(
                "--expect-sqlstate is required. A test that accepts any refusal accepts a "
                "typo in a column name as proof that a safety gate works."
            )

    cleanup: list[object] = []
    try:
        cluster, cleanup = _acquire_cluster(args)
        if args.self_test:
            return self_test(cluster)
        verdict, outcome = run_assertion(
            cluster,
            schema=_read(args.schema),
            prelude=_read(args.prelude),
            history=_read(args.history),
            expect_sqlstate=args.expect_sqlstate,
            expect_exhibit=args.expect_exhibit,
        )
    except EnvironmentProblem as problem:
        _say(f"ENVIRONMENT: {problem}")
        return 2
    finally:
        _release(cleanup)

    if args.json:
        _say(
            json.dumps(
                {
                    "ok": verdict.ok,
                    "expected": verdict.expected,
                    "observed": verdict.observed,
                    "sqlstate": outcome.sqlstate,
                    "exhibit": outcome.exhibit,
                    "exhibit_source": outcome.exhibit_source,
                    "message": outcome.message,
                    "failures": verdict.failures,
                },
                indent=2,
                sort_keys=True,
            )
        )
    elif verdict.ok:
        _say(f"OK  refused by {verdict.observed}")
        _say(f"    {outcome.message}")
    else:
        _say("FAIL")
        for failure in verdict.failures:
            _say(f"  - {failure}")
    return 0 if verdict.ok else 1


if __name__ == "__main__":
    if os.environ.get("GATE_ASSERT_TRACE"):  # pragma: no cover - operator convenience
        _say(f"python {sys.version.split()[0]} on {sys.platform}")
    raise SystemExit(main())
