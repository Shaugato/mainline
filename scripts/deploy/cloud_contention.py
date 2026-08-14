#!/usr/bin/env python
# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Induce ``40001`` on CockroachDB Cloud and on the local node, in ONE sitting, and compare.

WHY THIS EXISTS, AND WHAT IT IS *NOT* ALLOWED TO BE
====================================================

``docs/deploy/CLOUD-40001.md`` §2.1 proved ``40001 RETRY_SERIALIZABLE`` six times out of six
**against the single local node**, and that reproduction has been repeated independently three
times. It retired the premise *"a single node never produces 40001"*. What it could not do —
and said so, at length, in its own §3 — is say anything about the platform the demo actually
runs on. This program is the other half: the **same race, the same code, the same sitting**,
driven against CockroachDB Cloud and against ``127.0.0.1`` so that the difference between them
is a *comparison* rather than two anecdotes taken on different days by different people.

**The observable is the SQLSTATE and the restart REASON, produced by a race somebody
constructed.** Nothing here counts nodes. ``crdb_internal`` and ``system`` are restricted for
``mainline-sql`` on Cloud Basic and answer ``42501 InsufficientPrivilege``; a probe that tried
to establish "multi-node" by reading ``crdb_internal.gossip_nodes`` would report a privilege
refusal and call it a topology. There is no such statement in this file, deliberately, and
that absence is the point rather than an oversight.

THE THREE REASONS FOR ONE CODE
-------------------------------
``40001`` is one SQLSTATE wearing at least three costumes, and they are recorded **verbatim**:

* ``RETRY_SERIALIZABLE`` — the read-write cycle could not be ordered.
* ``RETRY_WRITE_TOO_OLD`` (``WriteTooOldError``) — a write landed under a newer timestamp.
* ``ReadWithinUncertaintyInterval`` — a read landed inside the clock-uncertainty window.
  **This one has no local analogue**: one node has one clock and nothing to disagree with.

A client that discriminated on the *message* would get one of the three wrong.
:mod:`trappoint_core.retry` discriminates on the **code**, and this program records the reason
only as evidence — never as a control-flow input. Every record carries the server's own first
line so that the classification below can be checked rather than believed.

TWO ARMS, AND WHY EACH IS SHAPED THE WAY IT IS
================================================

**ARM A — ``constructed``.** Two rows in a database this program CREATEs and DROPs. Caller A
reads key 1 then writes key 2; caller B reads key 2 then writes key 1. A one-shot
:class:`_Rendezvous` makes both finish reading before either writes, so the cycle is closed by
construction rather than by luck. The cycle is unorderable: whichever transaction the database
picks to go second must be told to start again.

*It runs in a scratch database and never in ``mainline_demo``.* ``evidence/deploy/
cloud-seed.json`` publishes the demo's exact Cloud row counts as committed evidence; a probe
that moved one of them would falsify a committed artefact and break the demo a founder's card
is paying for. The scratch database is created, used, and dropped, and the drop is *proven*
rather than assumed. **If ``CREATE DATABASE`` is ever refused, that refusal is the result** —
it is recorded and reported, and it is never routed around by writing into ``mainline_demo``.

**ARM B — ``gate-run``.** Two concurrent ``POST /v1/demo/gate-run`` against the demo database.
This one is *allowed* to touch ``mainline_demo`` for exactly one reason: the endpoint is
savepoint-fenced and rolls its whole transaction back, so it writes nothing. That permission
is conditional, and the condition is enforced here: the ten tables the four beats can write
are counted before and after the whole arm, and the counts are additionally checked against
``evidence/deploy/cloud-seed.json`` on Cloud.

**Arm B is expected to fail, and that failure is this program's most valuable output.**
``gate_run._FINGERPRINT_SQL`` counts whole tables, unscoped. Two runs racing each other can
each see the other's uncommitted-then-rolled-back work only if something commits — but they
share a *permit*, and the run that reads second can observe a different world than the run
that read first. When that happens the endpoint answers ``verdict: NOT PROVEN`` and accuses
itself, in its own payload, of a write it did not make. **This program records that result
whatever it says. It does not narrow the fingerprint, does not serialise the race, and does
not retry until the answer is nice.** The mechanism belongs to whoever owns ``gate_run.py``;
the measurement belongs here.

WHAT IS REUSED RATHER THAN REBUILT
====================================
There is **no retry primitive in this file**. :func:`trappoint_core.retry.run_gate` is the
loop — it retries ``40001`` and only ``40001``, attempts each refusal code exactly once ever,
and ``tests/concurrency/test_retry_taxonomy_spy.py`` watches it do so.
:func:`trappoint_testkit.txn.run_txn` already binds it to a connection **factory**, which is
the half that matters here: a retry must open a NEW connection, because a statement replayed
into a transaction CockroachDB has already aborted is not a retry of anything. A second loop
written here would be a second taxonomy to keep correct, and the day the two disagreed the one
nobody was spying on would win. :class:`trappoint_core.retry.RecordingObserver` is the spy, and
every round records whether it **actually** retried rather than assuming the loop was reached.

The DSN handling — ``load_dotenv``, ``rewrite_dsn``, ``cluster_label``, ``database_report``,
``redact`` — is imported from :mod:`scripts.deploy.cloud_chain` for the same reason.

THE DATABASE IS SELECTED BY NAME
=================================
The committed ``COCKROACH_DSN``'s path segment is ``defaultdb``, **not** ``mainline_demo``.
Anything that reads the segment verbatim and then counts ``mainline.*`` gets zero and concludes
the deployment is empty — the single most time-wasting false negative this deployment has
produced. Every connection this program opens names its database explicitly and then confirms
it with ``SELECT current_database()``; a mismatch is a refusal, not a warning.

NO CREDENTIAL IS PRINTED. Every message that leaves this program passes through
``cloud_chain.redact`` before it reaches a terminal or the evidence file.

EXIT CODES
----------
``0`` the census was taken (whatever it says — a ``NOT PROVEN`` in Arm B is a *result*) ·
``1`` a probe could not be taken at all, or the scratch database survived, or a row count moved
· ``2`` usage.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import platform
import re
import statistics
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

import psycopg

# Run as a module (`python -m scripts.deploy.cloud_contention`) or as a path. The second form
# gives Python `scripts/deploy` as sys.path[0] and no package context, so the sibling import
# below would fail — and that is exactly how an operator invokes it.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from trappoint_testkit.txn import from_dsn, run_txn

from scripts.deploy.cloud_chain import (
    cluster_label,
    connected_database,
    database_report,
    dsn_path_segment,
    load_dotenv,
    redact,
    repo_root,
    rewrite_dsn,
    sqlstate_of,
)
from trappoint_core.errors import (
    AuthorisationDenied,
    GateRefused,
    RetryBudgetExhausted,
    UnmodelledRefusal,
)
from trappoint_core.retry import RecordingObserver, RetryPolicy

EXIT_OK: Final = 0
EXIT_UNUSABLE: Final = 1
EXIT_USAGE: Final = 2

#: The retryable code. Named once; every comparison in this file reads this constant so that a
#: reader can grep for the string and find one definition rather than eleven literals.
RETRYABLE: Final = "40001"

#: The scratch database Arm A builds. Named for the worker that owns it, so that a database
#: left behind on a shared cluster is attributable to a person rather than to "some script".
SCRATCH_DEFAULT: Final = "w_w1"

#: The demo database on Cloud. NEVER taken from the DSN's path segment — see the module
#: docstring. Arm B reads it; Arm A never touches it.
DEMO_DATABASE: Final = "mainline_demo"

#: WHERE EACH ARM-B DATABASE CAME FROM, recorded into the artefact rather than left in a
#: worker's head. Ruling **R4** makes local authoritative for *what a stranger can reproduce* —
#: and a stranger cannot reproduce the local column of this census without the two commands
#: that built the database it ran against. The Cloud row exists so the two are not confusable:
#: `mainline_demo` is the LIVE demo and is never built by this program.
DATABASE_PROVENANCE: Final[dict[str, str]] = {
    "mainline_demo": (
        "the LIVE demo database on CockroachDB Cloud. NOT built by this program and never "
        "written to by it: Arm B is allowed here only because POST /v1/demo/gate-run is "
        "savepoint-fenced and rolls back, and the row counts before and after are the proof. "
        "It was seeded by scripts/deploy/seed_demo.py — see evidence/deploy/cloud-seed.json."
    ),
    "w_w1_demo": (
        "a local demo world this worker built for the comparison, so that both columns run the "
        "SAME code against the SAME shape. Reproduce it with:\n"
        "  python -m scripts.deploy.cloud_chain --dsn <local> --database w_w1_demo --recreate\n"
        "  python -m scripts.deploy.seed_demo  --dsn <local> --database w_w1_demo\n"
        "Measured on this workstation: 271/271 migrations in 123.4 s, then both seed files in "
        "0.56 s, verdict SEEDED AND REFUSABLE."
    ),
    "*": "not a database this program knows the provenance of; state it before citing the run.",
}

#: The seeded demo permit on Cloud. `evidence/deploy/cloud-seed.json` publishes it, and the
#: uuid5-derived default in `mainline_demo_api.scenario` is a DIFFERENT permit that Cloud does
#: not carry — so the gate-run arm must be told which one, exactly as W3's acceptance walk was.
DEMO_PERMIT_ID: Final = "dec0de00-0006-4000-8000-000000000001"

#: The ten tables ``gate_run._FINGERPRINT_TABLES`` counts. Transcribed rather than imported:
#: importing the handler's private tuple would make this probe agree with the handler by
#: construction, and the point of counting them here is to be a SECOND opinion about whether
#: the arm moved anything. If the two ever disagree, that disagreement is a finding.
FINGERPRINT_TABLES: Final[tuple[str, ...]] = (
    "mainline.permit",
    "mainline.permit_event",
    "mainline.merge_record",
    "mainline.disposition",
    "mainline.ledger_intake",
    "mainline.refusal_ledger",
    "mainline.blocking_check",
    "mainline.exposure_receipt",
    "mainline.exposure_line",
    "mainline_ops.outbox",
)

#: The restart reasons CockroachDB names inside a ``40001`` message. Ordered longest-first so
#: that a message carrying both ``WriteTooOldError`` and the generic word never matches the
#: shorter token first.
RESTART_REASONS: Final[tuple[str, ...]] = (
    "ReadWithinUncertaintyInterval",
    "RETRY_WRITE_TOO_OLD",
    "RETRY_SERIALIZABLE",
    "WriteTooOldError",
    "RETRY_ASYNC_WRITE_FAILURE",
    "RETRY_COMMIT_DEADLINE_EXCEEDED",
    "ABORT_REASON_",
)

#: The retry policy the probe drives the loop with. `max_attempts` is DEFAULT_POLICY's five —
#: this program is measuring the platform, not re-arguing the budget — but the delays are
#: pulled in so twelve rounds against Singapore do not spend their afternoon asleep. Recorded
#: into the evidence so nobody has to read this file to know what was in force.
PROBE_POLICY: Final = RetryPolicy(max_attempts=5, base_delay_s=0.01, cap_delay_s=0.1)


def restart_reason(message: str) -> str:
    """Return the restart reason CockroachDB named in *message*, or ``"unnamed"``.

    **PARSED FROM THE MESSAGE, AND EVIDENCE ONLY.** Nothing in this repository branches on
    this string: ``40001`` is the code, the code is what
    :func:`trappoint_core.retry.run_gate` discriminates on, and three different reasons share
    that one code. The value exists so the census can say *which* costume was worn, and every
    record that carries it also carries the server's own first line so the classification can
    be checked rather than believed.
    """
    for token in RESTART_REASONS:
        if token in message:
            return token.rstrip("_") if token.endswith("_") else token
    return "unnamed"


def first_line(exc: BaseException, limit: int = 420) -> str:
    """The server's own words, whitespace-collapsed, redacted, and bounded.

    Redaction is not optional and is not the caller's job to remember: a psycopg error can
    quote the connection string, and one forgotten ``print`` is a password in a committed JSON
    file.
    """
    return redact(" ".join(str(exc).split()))[:limit]


class _Rendezvous:
    """Both callers finish READING before either starts WRITING. Once, on the first attempt.

    An honest interleaving device rather than a thumb on the scale: two clients that arrive at
    the same moment read at the same moment, and forcing that makes the race **repeatable**
    instead of a coin toss about thread scheduling. The same device
    ``tests/concurrency/test_seed_permit_needs_retry.py`` uses, and for the same reason.

    It fires exactly once. A *retry* must not wait on a partner that has already committed and
    gone home — a :class:`threading.Barrier` reused after both parties passed it deadlocks the
    guarded half, which is a hang that looks like a slow cluster.
    """

    def __init__(self, parties: int, timeout_s: float) -> None:
        """Build a rendezvous for *parties* callers with a wall-clock ceiling."""
        self._barrier = threading.Barrier(parties)
        self._timeout_s = timeout_s
        self._passed = False
        self.broken = False

    def wait(self) -> None:
        """Block until every party has read, or record that one never arrived."""
        if self._passed:
            return
        try:
            self._barrier.wait(timeout=self._timeout_s)
        except threading.BrokenBarrierError:
            # A partner died before reaching the rendezvous. The survivor's outcome is still
            # real, so it is recorded rather than raised — but the fact travels out, because a
            # race that half-happened must never be reported as a race that happened.
            self.broken = True
        self._passed = True


# ═══════════════════════════════════════════════════════════════════════════════════════
# connections — the database is named, then confirmed
# ═══════════════════════════════════════════════════════════════════════════════════════


class DatabaseNotSelected(RuntimeError):
    """The server answered ``current_database()`` with something other than what was asked.

    A hard refusal rather than a warning. On the committed DSN a program that trusted the path
    segment would connect to ``defaultdb``, find no ``mainline`` schema, and report a scary
    ``UndefinedTable`` about a database that is perfectly healthy.
    """


def open_admin(dsn: str, database: str, *, connect_timeout: int, application_name: str) -> Any:
    """Open one autocommit connection on *database*, and prove the server agrees.

    Autocommit because every caller of this function is doing DDL or a census — one statement,
    one transaction, nothing to roll back. The *race* connections are opened by
    :func:`trappoint_testkit.txn.from_dsn`, which pins ``autocommit=False`` and cannot be
    talked out of it.
    """
    conn = psycopg.connect(
        rewrite_dsn(
            dsn,
            database=database,
            connect_timeout=connect_timeout,
            application_name=application_name,
        ),
        autocommit=True,
    )
    observed = connected_database(conn)
    if observed != database:
        conn.close()
        raise DatabaseNotSelected(
            f"asked for database {database!r} and the server answered "
            f"current_database() = {observed!r}. Nothing was measured and nothing was read."
        )
    return conn


def census(conn: Any, tables: Iterable[str]) -> dict[str, int]:
    """Count every table in *tables*, one statement each, in declaration order."""
    counts: dict[str, int] = {}
    for table in tables:
        row = conn.execute(f"SELECT count(*) FROM {table}").fetchone()  # noqa: S608 - fixed list
        counts[table] = int(row[0]) if row else -1
    return counts


# ═══════════════════════════════════════════════════════════════════════════════════════
# ARM A — the constructed read-write cycle, in a scratch database
# ═══════════════════════════════════════════════════════════════════════════════════════

SCRATCH_DDL: Final = "CREATE TABLE IF NOT EXISTS race (k INT PRIMARY KEY, v INT NOT NULL)"
SCRATCH_SEED: Final = "UPSERT INTO race (k, v) VALUES (1, 0), (2, 0)"
READ_SQL: Final = "SELECT v FROM race WHERE k = %s"
WRITE_SQL: Final = "UPDATE race SET v = v + 1 WHERE k = %s"


class _WatchedConnection:
    """A connection that WRITES DOWN the exception ``COMMIT`` raises, and changes nothing else.

    **This class exists because the first version of this probe was wrong, and the way it was
    wrong is worth keeping on the record.** The per-attempt record used to be built inside
    ``work``, wrapping the SELECT and the UPDATE in ``try/except``. That reads plausibly and it
    lost the entire finding: under SERIALIZABLE, CockroachDB very often detects the unorderable
    cycle at **commit time**, not at a statement. So ``work`` returned cleanly, ``run_txn``
    called ``commit()``, the commit raised ``40001``, ``run_gate`` retried it — and the census
    printed ``rounds_with_40001: 0`` for a round the spy had recorded a ``40001`` retry in.

    The spy was right and the record was wrong, so the record moved. A probe whose two
    observations disagree has found something; the half that is derived is the half that gives
    way, and the derived half here was the hand-rolled per-statement recorder.

    It satisfies :class:`trappoint_testkit.txn.TransactionalConnection` structurally, delegates
    every method, and **re-raises everything unchanged**. It suppresses nothing: ``run_gate``
    still classifies the exception, ``run_txn`` still discards the poisoned connection, and this
    object's only effect is that the message is written down on the way past.
    """

    def __init__(self, inner: Any, sink: Callable[[psycopg.Error, str], None]) -> None:
        """Wrap *inner*, reporting any :class:`psycopg.Error` to *sink* before re-raising."""
        self._inner = inner
        self._sink = sink

    @property
    def autocommit(self) -> bool:
        """Delegated, so ``txn._fresh``'s autocommit guard still sees the truth."""
        return bool(self._inner.autocommit)

    @property
    def info(self) -> Any:
        """Delegated, so ``txn._fresh`` and ``txn._committable`` read the real status."""
        return self._inner.info

    def execute(self, query: Any, params: Any = None) -> Any:
        """Run one statement, recording a refusal as coming from a STATEMENT."""
        try:
            return self._inner.execute(query, params)
        except psycopg.Error as exc:
            self._sink(exc, "statement")
            raise

    def commit(self) -> None:
        """Commit, recording a refusal as coming from the COMMIT. The interesting one."""
        try:
            self._inner.commit()
        except psycopg.Error as exc:
            self._sink(exc, "commit")
            raise

    def rollback(self) -> None:
        """Delegated. Not recorded: a rollback of an already-failed transaction is not news."""
        self._inner.rollback()

    def close(self) -> None:
        """Delegated. The adapter opened it, so the adapter closes it."""
        self._inner.close()


def _caller(
    dsn: str,
    read_key: int,
    write_key: int,
    rendezvous: _Rendezvous,
    policy: RetryPolicy,
) -> dict[str, Any]:
    """One half of the cycle, run as ONE whole transaction through the loop that already exists.

    Every attempt is recorded with the SQLSTATE, the restart reason and the server's verbatim
    first line — **wherever the refusal surfaced**, statement or commit. See
    :class:`_WatchedConnection` for why that distinction is the whole measurement.
    """
    spy = RecordingObserver()
    attempts: list[dict[str, Any]] = []
    started = time.perf_counter()

    def observe(exc: psycopg.Error, where: str) -> None:
        """Write the refusal onto the attempt that is currently open."""
        if not attempts:  # pragma: no cover - a refusal before `work` ran is not reachable
            attempts.append({"attempt": 0, "opened_at": time.perf_counter()})
        record = attempts[-1]
        record["sqlstate"] = sqlstate_of(exc)
        record["restart_reason"] = restart_reason(str(exc))
        record["message_verbatim"] = first_line(exc)
        record["raised_at"] = where
        # Assigned, not defaulted: `work` may already have written the statements' cost, and
        # this is the later and more informative event — the moment the attempt was refused.
        record["seconds"] = round(time.perf_counter() - record["opened_at"], 4)

    def factory() -> Any:
        return _WatchedConnection(from_dsn(dsn)(), observe)

    def work(conn: Any) -> int:
        record: dict[str, Any] = {
            "attempt": len(attempts),
            "opened_at": time.perf_counter(),
            "sqlstate": "00000",
            "restart_reason": None,
            "message_verbatim": None,
            "raised_at": None,
        }
        attempts.append(record)
        row = conn.execute(READ_SQL, (read_key,)).fetchone()
        record["read"] = int(row[0]) if row else None
        rendezvous.wait()
        conn.execute(WRITE_SQL, (write_key,))
        # NOT the attempt's whole cost: `run_txn` commits AFTER this returns, and on this shape
        # the commit is where the conflict usually surfaces. Overwritten by `observe` only when
        # nothing was raised, so a committed attempt reports its statements and a refused one
        # reports the moment it was refused.
        record["seconds"] = round(time.perf_counter() - record["opened_at"], 4)
        return int(record["attempt"])

    outcome: dict[str, Any] = {}
    try:
        run_txn(factory, work, policy=policy, observer=spy)
    except RetryBudgetExhausted as exc:
        # UNDECIDED, and reported as such. `spec/errors.md` §5: an undecided transaction is not
        # a refusal and is not a success. It is the one outcome a census must never round.
        outcome = {"outcome": "undecided", "detail": f"RetryBudgetExhausted after {exc.attempts}"}
    except GateRefused as exc:
        outcome = {"outcome": "refused", "sqlstate": exc.sqlstate, "constraint": exc.constraint}
    except AuthorisationDenied as exc:
        outcome = {"outcome": "denied", "detail": first_line(exc)}
    except UnmodelledRefusal as exc:
        # The taxonomy met a code it does not model. `UnmodelledRefusal` existing is the design
        # working; swallowing it would be the design defeated.
        outcome = {"outcome": "unmodelled", "sqlstate": exc.sqlstate, "detail": first_line(exc)}
    except psycopg.Error as exc:
        outcome = {"outcome": "error", "sqlstate": sqlstate_of(exc), "detail": first_line(exc)}
    else:
        outcome = {"outcome": "committed"}

    for record in attempts:
        record.pop("opened_at", None)

    # THE PROBE'S OWN NEGATIVE CONTROL, and it is here because it has already caught this file
    # being wrong once. Two independent observers watched the same attempts: the spy inside
    # `run_gate`, which counts what the LOOP judged retryable, and `_WatchedConnection`, which
    # writes down what the SERVER said. If the two ever disagree about how many 40001s there
    # were, the census below is reporting a number nobody should believe — so the disagreement
    # is carried into the evidence per caller rather than averaged away.
    recorded_40001 = sum(1 for a in attempts if a.get("sqlstate") == RETRYABLE)

    # `commit_attempt` is the attempt index that committed, or None. It is the number that says
    # "the retry converged", and it is read from the SPY rather than from the loop's return
    # value, so that a loop which stopped calling its observer would show up as a hole here.
    return {
        **outcome,
        "read_key": read_key,
        "write_key": write_key,
        "attempts": attempts,
        "attempt_count": len(attempts),
        "recorded_40001": recorded_40001,
        "seconds": round(time.perf_counter() - started, 4),
        "spy_retries": [
            {"attempt": a, "sqlstate": s, "delay_s": round(d, 4)} for a, s, d in spy.retries
        ],
        "spy_retried": bool(spy.retries),
        "spy_refusals": [
            {"attempt": a, "sqlstate": s, "constraint": c} for a, s, c in spy.refusals
        ],
        "spy_attempts_for_40001": spy.attempts_for(RETRYABLE),
        "record_agrees_with_spy": recorded_40001 == spy.attempts_for(RETRYABLE),
        "commit_attempt": spy.successes[0] if spy.successes else None,
    }


#: Caller A reads key 1 and writes key 2; caller B reads key 2 and writes key 1. Neither
#: transaction can be ordered before the other, so under SERIALIZABLE one of them MUST be told
#: to start again. This is the measurement.
CYCLE: Final[tuple[tuple[int, int], tuple[int, int]]] = ((1, 2), (2, 1))

#: THE NEGATIVE CONTROL, and the reason it is a constant in the program rather than a trick in
#: a test. Caller A reads and writes key 1; caller B reads and writes key 2. The two
#: transactions touch **nothing in common**, so there is no cycle and no conflict, and the
#: correct answer is **zero** ``40001``.
#:
#: It exists because an instrument that reports ``40001`` no matter what it is pointed at is
#: reporting nothing. Measured on the local node: the shape above gives 12 of 12, and this one
#: gives **0 of 6, twelve clean commits**. Two other candidate controls were tried first and
#: BOTH still produced 6 of 6 — removing the rendezvous, and pointing both callers at the same
#: single key — because two concurrent read-modify-writes of one row are also unorderable. They
#: are recorded here so nobody re-derives them believing they discriminate: **only disjointness
#: does.**
DISJOINT: Final[tuple[tuple[int, int], tuple[int, int]]] = ((1, 1), (2, 2))


def arm_constructed(
    dsn: str,
    scratch: str,
    rounds: int,
    policy: RetryPolicy,
    keys: tuple[tuple[int, int], tuple[int, int]] = CYCLE,
) -> dict[str, Any]:
    """Race *rounds* times in *scratch* over the key pairs in *keys*, then drop *scratch*.

    Args:
        dsn: the cluster. The database is replaced by *scratch* and confirmed by the server.
        scratch: a database this function CREATEs and DROPs. Never ``mainline_demo``.
        rounds: how many races.
        policy: forwarded to ``run_gate`` unchanged.
        keys: ``((read, write), (read, write))`` for callers A and B. :data:`CYCLE` is the
            measurement and :data:`DISJOINT` is the negative control that must produce none.

    The database is created here and dropped in the ``finally``. **The drop is verified**: a
    scratch database left behind on a managed cluster is somebody's bill and somebody's
    confusion, and "I issued a DROP" is not the same claim as "it is gone".
    """
    control = psycopg.connect(
        rewrite_dsn(dsn, database=None, connect_timeout=30, application_name="mainline-w1-ddl"),
        autocommit=True,
    )
    lifecycle: dict[str, Any] = {
        "scratch_database": scratch,
        "keys": {"A": list(keys[0]), "B": list(keys[1])},
        "shape": "cycle" if keys == CYCLE else ("disjoint" if keys == DISJOINT else "custom"),
    }
    rows: list[dict[str, Any]] = []
    try:
        started = time.perf_counter()
        control.execute(f"DROP DATABASE IF EXISTS {scratch} CASCADE")
        control.execute(f"CREATE DATABASE {scratch}")
        lifecycle["create_seconds"] = round(time.perf_counter() - started, 3)
        lifecycle["create_refused"] = None

        conn = open_admin(dsn, scratch, connect_timeout=30, application_name="mainline-w1-ddl")
        try:
            conn.execute(SCRATCH_DDL)
            conn.execute(SCRATCH_SEED)
            lifecycle["confirmed_by_server"] = connected_database(conn)
        finally:
            conn.close()

        race_dsn = rewrite_dsn(
            dsn, database=scratch, connect_timeout=30, application_name="mainline-w1-race"
        )
        for index in range(1, rounds + 1):
            rendezvous = _Rendezvous(2, timeout_s=60.0)
            results: dict[str, dict[str, Any]] = {}

            def one(
                name: str,
                read_key: int,
                write_key: int,
                *,
                into: dict[str, dict[str, Any]] = results,
                gate: _Rendezvous = rendezvous,
            ) -> None:
                """One caller. The two loop-scoped objects are bound at definition time.

                Default arguments rather than closure capture: a closure over ``results``
                would be re-bound on the next iteration, and a thread that outlived its round
                would write its answer into the following round's dictionary.
                """
                into[name] = _caller(race_dsn, read_key, write_key, gate, policy)

            round_started = time.perf_counter()
            threads = [
                threading.Thread(target=one, args=("A", *keys[0]), name=f"w1-a-{index}"),
                threading.Thread(target=one, args=("B", *keys[1]), name=f"w1-b-{index}"),
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=180)
            rows.append(
                {
                    "round": index,
                    "seconds": round(time.perf_counter() - round_started, 4),
                    "rendezvous_broken": rendezvous.broken,
                    "callers": results,
                }
            )
            print(
                f"  arm A round {index:>2}  "
                + "  ".join(
                    f"{name}={_sketch(results.get(name))}" for name in sorted(results) or ["A", "B"]
                ),
                flush=True,
            )
    except psycopg.Error as exc:
        # A REFUSED `CREATE DATABASE` IS THE RESULT, not a reason to write into mainline_demo.
        lifecycle["create_refused"] = {"sqlstate": sqlstate_of(exc), "detail": first_line(exc)}
    finally:
        dropped = _drop_and_prove(control, scratch)
        lifecycle.update(dropped)
        control.close()

    return {"lifecycle": lifecycle, "rounds": rows}


def _sketch(caller: dict[str, Any] | None) -> str:
    """A one-token summary of a caller, for the operator watching the terminal."""
    if caller is None:
        return "(no result)"
    states = "/".join(str(a.get("sqlstate")) for a in caller["attempts"])
    reasons = "/".join(str(a.get("restart_reason") or "-") for a in caller["attempts"])
    return f"{caller['outcome']}[{states}:{reasons}]"


def _drop_and_prove(control: Any, scratch: str) -> dict[str, Any]:
    """Drop *scratch* and then ASK whether it is gone. Two different claims."""
    record: dict[str, Any] = {}
    try:
        started = time.perf_counter()
        control.execute(f"DROP DATABASE IF EXISTS {scratch} CASCADE")
        record["drop_seconds"] = round(time.perf_counter() - started, 3)
    except psycopg.Error as exc:
        record["drop_seconds"] = None
        record["drop_refused"] = {"sqlstate": sqlstate_of(exc), "detail": first_line(exc)}
    try:
        row = control.execute(
            "SELECT count(*) FROM [SHOW DATABASES] WHERE database_name = %s", (scratch,)
        ).fetchone()
        record["survivors_after_drop"] = int(row[0]) if row else -1
    except psycopg.Error as exc:
        record["survivors_after_drop"] = None
        record["survivor_check_refused"] = {"sqlstate": sqlstate_of(exc), "detail": first_line(exc)}
    record["scratch_is_gone"] = record.get("survivors_after_drop") == 0
    return record


# ═══════════════════════════════════════════════════════════════════════════════════════
# ARM B — two concurrent POST /v1/demo/gate-run against the demo database
# ═══════════════════════════════════════════════════════════════════════════════════════


class _Container:
    """One ``scripts/deploy/local_furl.py`` process — the REAL handler, one warm container.

    Two of these, not one with ``--concurrency parallel``. ``mainline_demo_api.db`` caches ONE
    psycopg connection at module scope, which is correct for Lambda — the platform hands each
    concurrent request its own container — and unsafe for a single process fielding two at
    once. Racing two requests through one cached connection would not be a race between two
    judges; it would be one connection being used wrongly, and it would produce a SQLSTATE
    about that instead of about contention.
    """

    def __init__(
        self, index: int, dsn: str, database: str, permit_id: str, root: Path, state: Path
    ) -> None:
        """Record what this container will be started with. Nothing is spawned yet.

        *state* is a scratch directory outside the repository. The ready-file is a transient,
        and a transient written into a working tree is one crashed process away from an
        untracked file somebody has to explain in a ``git status``.
        """
        self.index = index
        self._root = root
        self._ready = state / f"w1-container-{index}.url"
        self._argv = [
            sys.executable,
            str(root / "scripts" / "deploy" / "local_furl.py"),
            "--port",
            "0",
            "--dsn",
            dsn,
            "--database",
            database,
            "--permit-id",
            permit_id,
            "--ready-file",
            str(self._ready),
            "--quiet",
        ]
        self.process: subprocess.Popen[bytes] | None = None
        self.base: str | None = None

    def start(self, timeout_s: float = 90.0) -> None:
        """Spawn the process and wait for it to publish the URL it is listening on."""
        with contextlib.suppress(FileNotFoundError):
            self._ready.unlink()
        # The DSN is on the argv of a child process this program spawns; it never reaches a
        # shell, a log line or the evidence file. `local_furl` itself redacts its own banner.
        self.process = subprocess.Popen(
            self._argv,
            cwd=str(self._root),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError(
                    f"container {self.index} exited with {self.process.returncode} before it "
                    "published a URL; re-run it by hand to see its banner"
                )
            if self._ready.is_file():
                text = self._ready.read_text(encoding="utf-8").strip()
                if text:
                    self.base = text.splitlines()[0].strip()
                    return
            time.sleep(0.1)
        raise RuntimeError(f"container {self.index} never became ready within {timeout_s:.0f}s")

    def stop(self) -> None:
        """Terminate the process and remove its ready file."""
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            with contextlib.suppress(subprocess.TimeoutExpired):
                self.process.wait(timeout=20)
            if self.process.poll() is None:
                self.process.kill()
        with contextlib.suppress(FileNotFoundError):
            self._ready.unlink()


def _post_gate_run(base: str, timeout_s: float) -> dict[str, Any]:
    """One ``POST /v1/demo/gate-run``, recorded whatever it answers."""
    url = base.rstrip("/") + "/v1/demo/gate-run"
    request = urllib.request.Request(  # noqa: S310 - a 127.0.0.1 URL this program built
        url,
        data=b"{}",
        method="POST",
        headers={"content-type": "application/json", "accept": "application/json"},
    )
    started = time.perf_counter()
    record: dict[str, Any] = {"url": url}
    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as response:  # noqa: S310
            record["status"] = response.status
            body = response.read()
    except urllib.error.HTTPError as exc:
        record["status"] = exc.code
        body = exc.read()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        record["status"] = None
        record["transport_error"] = redact(str(exc))[:300]
        record["seconds"] = round(time.perf_counter() - started, 4)
        return record
    record["seconds"] = round(time.perf_counter() - started, 4)
    try:
        envelope = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        record["body_not_json"] = redact(str(exc))[:200]
        record["body_head"] = redact(body[:400].decode("utf-8", "replace"))
        return record
    data = envelope.get("data", envelope) if isinstance(envelope, dict) else {}
    persistence = data.get("persistence_check") or {}
    record["verdict"] = data.get("verdict")
    record["persisted"] = data.get("persisted")
    record["outcome"] = data.get("outcome")
    # THE TWO CLAIMS THE PAYLOAD NOW SEPARATES, AND WHY BOTH ARE RECORDED.
    #
    # `identical` is the ten UNSCOPED whole-table counts: it answers "did the database move
    # between the two readings", and under a race it can be False because of the *other* run.
    # `self_persisted` is the claim the payload actually makes — "did anything THIS run wrote
    # survive" — and it is what the verdict keys on.
    #
    # Recording only the first would report a foreign write as this run's failure, which is the
    # exact defect the handler was carrying. Recording only the second would throw away the one
    # observation that makes the separation *visible on Cloud*: an `identical: false` sitting
    # underneath a `verdict: PROVEN` is a concurrent write that the endpoint saw, attributed
    # correctly, and did not blame itself for. That pairing is the finding, so both are kept.
    record["persistence_identical"] = persistence.get("identical")
    record["self_persisted"] = persistence.get("self_persisted")
    record["concurrent_writes"] = persistence.get("concurrent_writes")
    record["failures"] = data.get("failures")
    record["beats"] = [
        {"ordinal": b.get("ordinal"), "name": b.get("name"), "sqlstate": b.get("sqlstate")}
        for b in (data.get("beats") or [])
    ]
    # A 40001 on the demo's own headline path arrives as `outcome: retry` and a 503 — the
    # contract's word for UNDECIDED. It is the single most interesting thing this arm can find
    # and it is lifted out so a census can count it without walking the payload.
    record["undecided_40001"] = data.get("outcome") == "retry"
    return record


def arm_gate_run(
    dsn: str,
    database: str,
    permit_id: str,
    rounds: int,
    root: Path,
    connect_timeout: int,
    request_timeout: float,
) -> dict[str, Any]:
    """Race two ``POST /v1/demo/gate-run`` *rounds* times, and prove nothing was written.

    The ten fingerprint tables are counted before the first round and after the last one. That
    census is the CONDITION on this arm's permission to touch a live demo database at all — and
    it is taken by this program, over its own connection, rather than read out of the payload
    the endpoint returns about itself.
    """
    result: dict[str, Any] = {
        "database": database,
        "permit_id": permit_id,
        "database_provenance": DATABASE_PROVENANCE.get(database, DATABASE_PROVENANCE["*"]),
        "rounds": [],
    }
    conn = open_admin(
        dsn, database, connect_timeout=connect_timeout, application_name="mainline-w1-census"
    )
    try:
        result["database_selection"] = database_report(dsn, database, connected_database(conn))
        result["row_counts_before"] = census(conn, FINGERPRINT_TABLES)
    finally:
        conn.close()

    state = Path(tempfile.mkdtemp(prefix="w1-contention-"))
    containers = [_Container(i, dsn, database, permit_id, root, state) for i in (1, 2)]
    try:
        for container in containers:
            container.start()
        result["containers"] = [
            {"index": c.index, "base": c.base, "process": "scripts/deploy/local_furl.py"}
            for c in containers
        ]
        # One warm-up request per container, NOT counted. The first call to a cold container
        # pays a TLS handshake plus auth to Singapore — 2-3 s, measured — and a census whose
        # first round carried that would report a cold start as a contention latency.
        result["warmup"] = [
            {"index": c.index, **_post_gate_run(str(c.base), request_timeout)} for c in containers
        ]
        for index in range(1, rounds + 1):
            rendezvous = _Rendezvous(2, timeout_s=request_timeout)
            answers: dict[str, dict[str, Any]] = {}

            def one(
                name: str,
                base: str,
                *,
                into: dict[str, dict[str, Any]] = answers,
                gate: _Rendezvous = rendezvous,
            ) -> None:
                """Wait for the partner, then POST. Bound by default argument — see Arm A."""
                gate.wait()
                into[name] = _post_gate_run(base, request_timeout)

            round_started = time.perf_counter()
            threads = [
                threading.Thread(
                    target=one, args=(f"c{c.index}", str(c.base)), name=f"w1-g{c.index}"
                )
                for c in containers
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=request_timeout * 2 + 30)
            result["rounds"].append(
                {
                    "round": index,
                    "seconds": round(time.perf_counter() - round_started, 4),
                    "rendezvous_broken": rendezvous.broken,
                    "callers": answers,
                }
            )
            print(
                f"  arm B round {index:>2}  "
                + "  ".join(
                    f"{name}={answers[name].get('status')}/{answers[name].get('verdict')}"
                    for name in sorted(answers)
                ),
                flush=True,
            )
    except (RuntimeError, OSError) as exc:
        result["arm_failed"] = redact(str(exc))[:400]
    finally:
        for container in containers:
            container.stop()
        with contextlib.suppress(OSError):
            state.rmdir()

    conn = open_admin(
        dsn, database, connect_timeout=connect_timeout, application_name="mainline-w1-census"
    )
    try:
        result["row_counts_after"] = census(conn, FINGERPRINT_TABLES)
    finally:
        conn.close()
    result["row_counts_moved"] = {
        table: [before, result["row_counts_after"].get(table)]
        for table, before in result["row_counts_before"].items()
        if result["row_counts_after"].get(table) != before
    }
    result["nothing_persisted"] = not result["row_counts_moved"]
    return result


# ═══════════════════════════════════════════════════════════════════════════════════════
# the census — what the two arms, on the two platforms, actually said
# ═══════════════════════════════════════════════════════════════════════════════════════


def census_constructed(arm: dict[str, Any]) -> dict[str, Any]:
    """Tally SQLSTATEs, restart reasons and retries over every attempt of every caller."""
    sqlstates: dict[str, int] = {}
    reasons: dict[str, int] = {}
    latencies: list[float] = []
    raised_at: dict[str, int] = {}
    rounds_with_40001 = 0
    rounds_both_committed = 0
    retried_by_run_gate = 0
    undecided = 0
    disagreements = 0
    for row in arm["rounds"]:
        saw_40001 = False
        committed = 0
        for caller in row["callers"].values():
            disagreements += int(caller.get("record_agrees_with_spy") is False)
            for attempt in caller["attempts"]:
                state = str(attempt.get("sqlstate"))
                sqlstates[state] = sqlstates.get(state, 0) + 1
                if state == RETRYABLE:
                    saw_40001 = True
                    reason = str(attempt.get("restart_reason"))
                    reasons[reason] = reasons.get(reason, 0) + 1
                    where = str(attempt.get("raised_at"))
                    raised_at[where] = raised_at.get(where, 0) + 1
                if attempt.get("seconds") is not None:
                    latencies.append(float(attempt["seconds"]))
            if caller.get("outcome") == "committed":
                committed += 1
            if caller.get("outcome") == "undecided":
                undecided += 1
            if caller.get("spy_retried"):
                retried_by_run_gate += 1
        rounds_with_40001 += int(saw_40001)
        rounds_both_committed += int(committed == 2)
    return {
        "rounds": len(arm["rounds"]),
        "callers": 2 * len(arm["rounds"]),
        "sqlstates": dict(sorted(sqlstates.items())),
        "restart_reasons_for_40001": dict(sorted(reasons.items())),
        "where_the_40001_surfaced": dict(sorted(raised_at.items())),
        "rounds_with_40001": rounds_with_40001,
        "rounds_where_both_callers_committed": rounds_both_committed,
        "callers_run_gate_actually_retried": retried_by_run_gate,
        "callers_undecided_retry_budget_exhausted": undecided,
        "callers_where_record_and_spy_disagree": disagreements,
        "attempt_latency_seconds": _latency(latencies),
    }


def census_gate_run(arm: dict[str, Any]) -> dict[str, Any]:
    """Tally statuses, verdicts and the persistence claim over every raced request."""
    statuses: dict[str, int] = {}
    verdicts: dict[str, int] = {}
    latencies: list[float] = []
    identical_true = 0
    identical_false = 0
    self_persisted_true = 0
    saw_a_concurrent_write = 0
    foreign_write_not_blamed = 0
    undecided = 0
    rounds_both_proven = 0
    rounds_with_a_not_proven = 0
    for row in arm.get("rounds", []):
        proven = 0
        not_proven = 0
        for caller in row["callers"].values():
            statuses[str(caller.get("status"))] = statuses.get(str(caller.get("status")), 0) + 1
            verdict = str(caller.get("verdict"))
            verdicts[verdict] = verdicts.get(verdict, 0) + 1
            if caller.get("seconds") is not None:
                latencies.append(float(caller["seconds"]))
            if caller.get("persistence_identical") is True:
                identical_true += 1
            elif caller.get("persistence_identical") is False:
                identical_false += 1
            self_persisted_true += int(caller.get("self_persisted") is True)
            saw_a_concurrent_write += int(bool(caller.get("concurrent_writes")))
            # THE PAIRING THAT IS THE WHOLE POINT OF ARM B: the run saw the database move
            # under it, correctly attributed the movement to somebody else, and still answered
            # PROVEN. Before 2026-08-14 that same observation produced NOT PROVEN.
            foreign_write_not_blamed += int(
                caller.get("persistence_identical") is False
                and caller.get("self_persisted") is False
                and verdict == "PROVEN"
            )
            undecided += int(bool(caller.get("undecided_40001")))
            proven += int(verdict == "PROVEN")
            not_proven += int(verdict == "NOT PROVEN")
        rounds_both_proven += int(proven == 2)
        rounds_with_a_not_proven += int(not_proven > 0)
    return {
        "rounds": len(arm.get("rounds", [])),
        "requests": sum(statuses.values()),
        "http_statuses": dict(sorted(statuses.items())),
        "verdicts": dict(sorted(verdicts.items())),
        "rounds_where_both_were_proven": rounds_both_proven,
        "rounds_with_at_least_one_not_proven": rounds_with_a_not_proven,
        "persistence_check_identical_true": identical_true,
        "persistence_check_identical_false": identical_false,
        "requests_claiming_self_persisted": self_persisted_true,
        "requests_that_saw_a_concurrent_write": saw_a_concurrent_write,
        "requests_that_saw_a_foreign_write_and_did_not_blame_themselves": foreign_write_not_blamed,
        "requests_undecided_40001": undecided,
        "request_latency_seconds": _latency(latencies),
        "nothing_persisted": arm.get("nothing_persisted"),
        "row_counts_moved": arm.get("row_counts_moved"),
    }


#: The four things a CockroachDB restart message says about the cluster that produced it.
#: ``obs={nN@ts}`` is the set of nodes whose clocks this transaction has observed; ``key=`` is
#: the conflicting key, whose prefix is ``/Tenant/<id>/Table/...`` on a multi-tenant deployment
#: and ``/Table/...`` on a single-tenant one; ``rts`` and ``gul`` are the read timestamp and the
#: **global uncertainty limit**, whose difference is the cluster's configured maximum clock
#: offset.
_OBSERVED_NODE = re.compile(r"obs=\{([^}]*)\}")
_NODE_ID = re.compile(r"n(\d+)@")
_KEY_PREFIX = re.compile(r"key=(/[A-Za-z]+)")
_READ_TS = re.compile(r"\brts=(\d+\.\d+)")
_UNCERTAINTY_LIMIT = re.compile(r"\bgul=(\d+\.\d+)")


def structural_differences(arm: dict[str, Any]) -> dict[str, Any]:
    """Read the CLUSTER's shape out of the restart messages the race already produced.

    **This is ruling R3's method paying a dividend nobody costed for it.** `crdb_internal` and
    `system` are restricted, so no probe here may count nodes — and it turns out none needs to.
    A ``40001`` message names the nodes whose clocks the transaction observed, the key it
    conflicted on, and the width of the clock-uncertainty window. All three come out of text the
    server volunteered because a race was constructed, and all three distinguish a multi-tenant
    multi-node deployment from one process on a laptop.

    Nothing here is a node **count**. ``obs={n6@…}`` says the range was served by a node whose
    id is 6; CockroachDB hands out ids in join order from 1, so a single-node cluster cannot
    produce it — but a cluster that has *had* six nodes join is not the same claim as a cluster
    that has six now, and this function does not make the second one.

    Derived from ``arm``'s own recorded messages, so it is recomputable by anybody holding
    ``evidence/deploy/cloud-contention.json`` and is not a number this program asks to be
    believed on its own authority.
    """
    nodes: dict[str, int] = {}
    prefixes: dict[str, int] = {}
    offsets: list[float] = []
    messages = 0
    for row in arm.get("rounds", []):
        for caller in row["callers"].values():
            for attempt in caller["attempts"]:
                message = attempt.get("message_verbatim")
                if not message:
                    continue
                messages += 1
                for group in _OBSERVED_NODE.findall(message):
                    for node in _NODE_ID.findall(group):
                        nodes[node] = nodes.get(node, 0) + 1
                for prefix in _KEY_PREFIX.findall(message):
                    prefixes[prefix] = prefixes.get(prefix, 0) + 1
                read_ts = _READ_TS.search(message)
                limit = _UNCERTAINTY_LIMIT.search(message)
                if read_ts and limit:
                    offsets.append(round(float(limit.group(1)) - float(read_ts.group(1)), 4))
    return {
        "messages_read": messages,
        "observed_clock_node_ids": dict(sorted(nodes.items())),
        "conflicting_key_prefixes": dict(sorted(prefixes.items())),
        "max_clock_offset_seconds": sorted(set(offsets)),
        "how": (
            "parsed out of the restart messages this race produced. No crdb_internal and no "
            "system catalogue was read: both are restricted for mainline-sql on Cloud Basic "
            "(42501), and a node count read from a privilege refusal is not a topology."
        ),
        "what_the_node_id_does_not_say": (
            "obs={nN@...} names a node whose clock this transaction observed. Ids are assigned "
            "in join order from 1, so an id above 1 cannot come from a single-node cluster — "
            "but it is not a count of the nodes running now, and it is not offered as one."
        ),
    }


def _latency(values: list[float]) -> dict[str, Any]:
    """min / median / max, or nulls — never a mean over an empty list."""
    if not values:
        return {"n": 0, "min": None, "median": None, "max": None}
    return {
        "n": len(values),
        "min": round(min(values), 4),
        "median": round(statistics.median(values), 4),
        "max": round(max(values), 4),
    }


def target_fingerprint(dsn: str, database: str, connect_timeout: int) -> dict[str, Any]:
    """Who the server says it is — version, user, isolation, and which database.

    No ``crdb_internal``, no ``system``, no node count. Both catalogues are restricted for
    ``mainline-sql`` on Cloud Basic and answer ``42501``; *"we could not read the node list"* is
    not a result about ranges, replicas or clocks and is not offered as one here.
    """
    conn = psycopg.connect(
        rewrite_dsn(
            dsn, database=database, connect_timeout=connect_timeout, application_name="mainline-w1"
        ),
        autocommit=True,
    )
    try:
        started = time.perf_counter()
        version = conn.execute("SELECT version()").fetchone()
        connect_seconds = round(time.perf_counter() - started, 3)
        user = conn.execute("SELECT current_user").fetchone()
        isolation = conn.execute("SHOW default_transaction_isolation").fetchone()
        observed = connected_database(conn)
        return {
            "cluster": cluster_label(dsn),
            "version": str(version[0]) if version else "unknown",
            "connected_as": str(user[0]) if user else "unknown",
            "default_transaction_isolation": str(isolation[0]) if isolation else "unknown",
            "database_selection": database_report(dsn, database, observed),
            "first_query_seconds": connect_seconds,
            "node_topology": (
                "NOT READ, ON PURPOSE. crdb_internal and system are restricted for this role on "
                "CockroachDB Cloud Basic (42501 InsufficientPrivilege), and a probe that proved "
                "'multi-node' by counting gossip nodes would be reporting a privilege refusal as "
                "a topology. The observable is the SQLSTATE and the restart reason, produced by "
                "a race this program constructed."
            ),
        }
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════════════════════════════
# the program
# ═══════════════════════════════════════════════════════════════════════════════════════


def probe_target(
    name: str,
    dsn: str,
    *,
    demo_database: str,
    scratch: str,
    permit_id: str,
    rounds: int,
    arms: set[str],
    root: Path,
    connect_timeout: int,
    request_timeout: float,
    policy: RetryPolicy,
) -> dict[str, Any]:
    """Run the requested arms against one platform and return everything they said."""
    # ASCII ONLY in everything printed. This runs on a Windows console whose default code page
    # is cp1252, where a box-drawing character is not a cosmetic problem but an
    # UnicodeEncodeError that kills the run before the first round — measured, on this machine.
    print(f"\n== {name}: {cluster_label(dsn)}", flush=True)
    record: dict[str, Any] = {"target": name}
    record["fingerprint"] = target_fingerprint(dsn, demo_database, connect_timeout)
    print(
        f"  connected    {record['fingerprint']['database_selection']['confirmed_by_server']} "
        f"as {record['fingerprint']['connected_as']} "
        f"(SELECT current_database(); the DSN's path segment said "
        f"'{dsn_path_segment(dsn)}' and was overridden)",
        flush=True,
    )
    if "constructed" in arms:
        record["arm_constructed"] = arm_constructed(dsn, scratch, rounds, policy)
        record["census_constructed"] = census_constructed(record["arm_constructed"])
        shape = structural_differences(record["arm_constructed"])
        print(
            f"  cluster shape  nodes observed {list(shape['observed_clock_node_ids'])} "
            f"key prefix {list(shape['conflicting_key_prefixes'])} "
            f"max clock offset {shape['max_clock_offset_seconds']} s "
            "(read from the restart messages, never from crdb_internal)",
            flush=True,
        )
    if "gate-run" in arms:
        record["arm_gate_run"] = arm_gate_run(
            dsn, demo_database, permit_id, rounds, root, connect_timeout, request_timeout
        )
        record["census_gate_run"] = census_gate_run(record["arm_gate_run"])
    return record


def side_by_side(targets: list[dict[str, Any]]) -> dict[str, Any]:
    """The comparison this program exists to produce, and the caveats that bound it."""
    by_name = {t["target"]: t for t in targets}
    table: dict[str, Any] = {}
    for arm, key in (("constructed", "census_constructed"), ("gate-run", "census_gate_run")):
        present = {n: t[key] for n, t in by_name.items() if key in t}
        if present:
            table[arm] = present
    return {
        "arms": table,
        "how_to_read_this": (
            "Cloud is authoritative for what the DEMO will meet; local is authoritative for "
            "what a stranger can reproduce. Neither column is edited to match the other and "
            "neither is deleted when it disagrees (docs/leads/cloud-hardening-final.md R4)."
        ),
        "what_a_zero_would_not_license": (
            "If a column shows zero 40001, that is a fact about how contended THAT run was. It "
            "is not evidence that the retry guards are unnecessary — docs/deploy/CLOUD-40001.md "
            "§7 fixes that reading in advance, and this program does not get to revise it after "
            "seeing its own numbers."
        ),
    }


def unmet_conditions(targets: list[dict[str, Any]], scratch: str) -> list[str]:
    """The conditions this run is allowed to be believed under, CHECKED rather than claimed.

    Four of them, and every one is a thing a previous version of some probe in this repository
    asserted in prose and never tested:

    * the scratch database is **gone**, not merely dropped;
    * the two independent observers of Arm A agree about how many ``40001``s there were;
    * Arm B moved **no** row count — the condition R5 attaches to its permission to race
      against a live demo database at all;
    * Arm B actually **ran**. An arm that died after two rounds is not a twelve-round census
      and must not be tallied as one.
    """
    unmet: list[str] = []
    for record in targets:
        name = record["target"]
        arm_a = record.get("arm_constructed")
        if arm_a and not arm_a["lifecycle"].get("scratch_is_gone"):
            unmet.append(
                f"{name}: the scratch database {scratch!r} was not proven gone after the DROP"
            )
        disagreed = (record.get("census_constructed") or {}).get(
            "callers_where_record_and_spy_disagree"
        )
        if disagreed:
            unmet.append(
                f"{name}: {disagreed} caller(s) where the per-attempt record and the run_gate "
                "spy disagree about how many 40001s there were. One of the two observers is "
                "broken and this census cannot be believed until it is known which."
            )
        arm_b = record.get("arm_gate_run")
        if arm_b and arm_b.get("row_counts_moved"):
            unmet.append(
                f"{name}: the gate-run arm MOVED row counts {arm_b['row_counts_moved']!r} — "
                "the endpoint is supposed to persist nothing"
            )
        if arm_b and arm_b.get("arm_failed"):
            unmet.append(f"{name}: gate-run arm did not complete: {arm_b['arm_failed']}")
    return unmet


def build_parser() -> argparse.ArgumentParser:
    """The command line. Defaults run both arms against both platforms, twelve rounds each."""
    parser = argparse.ArgumentParser(
        prog="cloud_contention",
        description=(
            "Induce 40001 on CockroachDB Cloud and on the local node in one sitting, record "
            "every SQLSTATE and every restart reason verbatim, and compare the two."
        ),
    )
    parser.add_argument(
        "--cloud-dsn",
        default=None,
        help="Cloud DSN (default: COCKROACH_DSN from the repo-root .env)",
    )
    parser.add_argument(
        "--local-dsn",
        default="postgresql://root@127.0.0.1:26257/defaultdb?sslmode=disable",
        help="the local single node. 127.0.0.1, never 'localhost': a dead ::1 costs a full "
        "connect timeout per attempt before the IPv4 address is tried.",
    )
    parser.add_argument("--rounds", type=int, default=12, help="races per arm per target (min 12)")
    parser.add_argument(
        "--arms",
        default="constructed,gate-run",
        help="which arms to run: constructed, gate-run, or both",
    )
    parser.add_argument(
        "--targets", default="cloud,local", help="which platforms to drive: cloud, local, or both"
    )
    parser.add_argument("--scratch", default=SCRATCH_DEFAULT, help="Arm A's scratch database")
    parser.add_argument("--cloud-database", default=DEMO_DATABASE, help="Arm B's database on Cloud")
    parser.add_argument(
        "--local-database",
        default="w_w1_demo",
        help="Arm B's database on the local node — a demo world this worker built",
    )
    parser.add_argument("--permit-id", default=DEMO_PERMIT_ID, help="the seeded demo permit")
    parser.add_argument("--connect-timeout", type=int, default=30)
    parser.add_argument("--request-timeout", type=float, default=120.0)
    parser.add_argument("--out", type=Path, default=None, help="where the evidence is written")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Drive the arms, write the evidence, and refuse to call a half-run a census."""
    args = build_parser().parse_args(argv)
    root = repo_root()
    load_dotenv(root)

    arms = {a.strip() for a in args.arms.split(",") if a.strip()}
    targets = [t.strip() for t in args.targets.split(",") if t.strip()]
    unknown = arms - {"constructed", "gate-run"}
    if unknown:
        print(f"cloud_contention: unknown arm(s) {sorted(unknown)}", file=sys.stderr)
        return EXIT_USAGE
    if args.rounds < 1:
        print("cloud_contention: --rounds must be at least 1", file=sys.stderr)
        return EXIT_USAGE

    cloud_dsn = args.cloud_dsn or os.environ.get("COCKROACH_DSN")
    if "cloud" in targets and not cloud_dsn:
        # R1: the credential IS on this workstation. If it is not, say which name was looked
        # for and where — never "this cannot be tested without Cloud".
        print(
            "cloud_contention: no Cloud DSN. Pass --cloud-dsn, or put COCKROACH_DSN in the "
            f"repo-root .env at {root / '.env'}. The value is never printed.",
            file=sys.stderr,
        )
        return EXIT_UNUSABLE

    started = time.time()
    evidence: dict[str, Any] = {
        "artefact": "MAINLINE cloud-vs-local contention census",
        "generated_at_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "generated_by": "scripts/deploy/cloud_contention.py",
        "worker": "W1 · cloud-contention",
        "question": (
            "Does CockroachDB Cloud produce 40001 under a race this repository constructs, "
            "which restart REASONS does it name, and what differs from the single local node "
            "when the same code runs against both in one sitting?"
        ),
        "method": {
            "retry_loop": (
                "trappoint_core.retry.run_gate, reached through trappoint_testkit.txn.run_txn. "
                "No retry primitive is defined in this program: run_gate retries 40001 and only "
                "40001, attempts each refusal code exactly once ever, and "
                "tests/concurrency/test_retry_taxonomy_spy.py watches it do so."
            ),
            "spy": (
                "trappoint_core.retry.RecordingObserver. Every caller records whether the loop "
                "ACTUALLY retried rather than assuming it was reached."
            ),
            "policy": {
                "max_attempts": PROBE_POLICY.max_attempts,
                "base_delay_s": PROBE_POLICY.base_delay_s,
                "cap_delay_s": PROBE_POLICY.cap_delay_s,
                "note": (
                    "max_attempts is DEFAULT_POLICY's five — this program measures the platform "
                    "and does not re-argue the budget. Only the sleep ladder is shortened."
                ),
            },
            "restart_reason_provenance": (
                "PARSED from the server's message and recorded beside the verbatim first line. "
                "Nothing branches on it: 40001 is the code, three reasons share it, and a "
                "client discriminating on the message would get one of the three wrong."
            ),
            "topology": (
                "Never read. crdb_internal and system are restricted for this role on Cloud "
                "Basic (42501). Contention is INDUCED and the SQLSTATE is observed."
            ),
            "database_selection": (
                "Every connection names its database explicitly and confirms it with SELECT "
                "current_database(). The committed DSN's path segment is 'defaultdb' and is "
                "never trusted."
            ),
        },
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "psycopg": psycopg.__version__,
        },
        "rounds_requested": args.rounds,
        "arms_requested": sorted(arms),
        "targets": [],
    }

    failures: list[str] = []
    for name in targets:
        dsn = cloud_dsn if name == "cloud" else args.local_dsn
        if not dsn:
            failures.append(f"target {name!r} has no DSN")
            continue
        demo_database = args.cloud_database if name == "cloud" else args.local_database
        try:
            evidence["targets"].append(
                probe_target(
                    name,
                    dsn,
                    demo_database=demo_database,
                    scratch=args.scratch,
                    permit_id=args.permit_id,
                    rounds=args.rounds,
                    arms=arms,
                    root=root,
                    connect_timeout=args.connect_timeout,
                    request_timeout=args.request_timeout,
                    policy=PROBE_POLICY,
                )
            )
        except (psycopg.Error, DatabaseNotSelected, RuntimeError, OSError) as exc:
            failures.append(f"target {name!r} could not be probed: {redact(str(exc))[:300]}")
            evidence["targets"].append({"target": name, "unreachable": redact(str(exc))[:300]})

    evidence["comparison"] = side_by_side(evidence["targets"])
    failures.extend(unmet_conditions(evidence["targets"], args.scratch))

    evidence["total_seconds"] = round(time.time() - started, 1)
    evidence["failures"] = failures
    evidence["verdict"] = "CENSUS TAKEN" if not failures else "CENSUS INCOMPLETE"

    out = args.out or (root / "evidence" / "deploy" / "cloud-contention.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(evidence, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    licence = out.with_suffix(out.suffix + ".license")
    if not licence.exists():
        licence.write_text(
            "SPDX-FileCopyrightText: 2026 MAINLINE contributors\n"
            "SPDX-License-Identifier: CC-BY-4.0\n",
            encoding="utf-8",
        )
    print(f"\n  evidence     {out}", flush=True)
    for line in failures:
        print(f"  FAILURE      {line}", flush=True)
    print(f"  verdict      {evidence['verdict']}", flush=True)
    return EXIT_OK if not failures else EXIT_UNUSABLE


if __name__ == "__main__":
    raise SystemExit(main())
