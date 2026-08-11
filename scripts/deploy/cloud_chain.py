#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Apply the MAINLINE migration chain to CockroachDB Cloud, idempotently, with 40001 retry.

WHAT THIS IS FOR
----------------
The demo runs against database ``mainline_demo`` on the Cloud cluster ``mainline-dev``
(SERVERLESS/Basic, ``aws-ap-southeast-1``). This program is how that database comes to
exist, and how a second run of the deploy proves it did not change it.

THREE THINGS THIS DOES THAT ``trappoint migrate up`` DOES NOT
-------------------------------------------------------------
1. **It retries ``40001``, and it can be made to prove it.**  The first attempt to build
   this database on Cloud died with

       TransactionRetryWithProtoRefreshError: TransactionRetryError:
       retry txn (RETRY_SERIALIZABLE - failed preemptive refresh)

   and neither ``trappoint migrate up`` nor ``scripts/proof/gate_refusal.py`` retries.
   Every statement here gets up to :data:`MAX_ATTEMPTS` attempts with an exponential
   backoff that is capped and jittered, a dropped connection is re-established rather than
   counted as a failure, and the report says **how many files needed a retry**.

   One correction to the claim this file used to make. It said a single-node Docker
   cluster *never* produces ``40001``. That is not true and the repository's own CI
   falsifies it: ``.github/workflows/cloud-verify.yml``'s first job forces two contending
   transactions on a single-node container and gets a genuine
   ``RETRY_SERIALIZABLE`` — GitHub run ``31441340234``, ``observed sqlstate : 40001``. What
   a single node does not do is produce one **unprompted, during a DDL chain**, which is
   what the managed cluster did. The narrower statement is the true one.

   That number has been ``0`` on every Cloud run so far, and **zero retries is not evidence
   that the loop works — it is evidence that it was not needed**. So the loop is exercised
   deliberately: ``--inject-40001 N`` makes the executor raise
   ``psycopg.errors.SerializationFailure`` on the first *N* attempts of a chosen statement,
   *before* the statement reaches the server, so no partial work is done and the recovery
   is the loop's alone. ``--retry-probe`` runs three such cases against the live cluster and
   writes the transcript into the evidence:

   ===========================  ====================================================
   ``recovers``                  2 injected failures, third attempt succeeds
   ``bounded``                   :data:`MAX_ATTEMPTS` injected failures, gives up, reports 40001
   ``not_retryable``             a real ``42P01`` is attempted **once** and not retried
   ===========================  ====================================================

   An injected retry is never allowed to be mistaken for a spontaneous one: every row
   carries ``injected_40001``, and ``files_that_needed_a_retry`` counts only the retries
   the *cluster* caused.

   The classification matters too. In psycopg 3, ``SerializationFailure`` is a subclass of
   ``OperationalError`` — so a naive ``except psycopg.OperationalError`` catches a genuine
   ``40001`` and treats it as a dropped socket, throwing away and rebuilding a perfectly
   healthy connection. SQLSTATE is therefore consulted **before** the exception class.

2. **It continues past a failure and attributes each one.**  ``migrate up`` is
   forward-only and halts on the first refusal — right for a deployment, useless for a
   census. A failure here is recorded with its file, its SQLSTATE and, when the message
   names one, the relation that was missing, so that "15 failed" is never a number
   without a reason beside it.

3. **It is idempotent, and the database is the authority for that.**  A marker row in
   ``trappoint.deploy_chain`` records the tree fingerprint (what the files say) and the
   live fingerprint (what the cluster holds). A second run recomputes the live
   fingerprint and compares both:

   ===============================  ==========================================
   both match                        report ``unchanged``, apply nothing, exit 0
   tree fingerprint differs          refuse, name ``--recreate``, exit 3
   live fingerprint differs          refuse, name ``--recreate``, exit 3
   database exists, no marker row    refuse, name ``--recreate``, exit 3
   ===============================  ==========================================

   Refusing rather than re-applying is deliberate. Migration files are forward-only and
   are not written ``IF NOT EXISTS``; replaying them over a live database produces a wall
   of ``42P07`` that says nothing about whether the schema is right. A deploy tool that
   cannot tell "already correct" from "differently wrong" should say so and stop.

WHY THE MARKER LIVES IN ``trappoint``
-------------------------------------
Kernel ruling D6 already puts the runner's bookkeeping in a ``trappoint`` schema outside
the numbered sequence, for the reason that applies again here: bookkeeping about applying
migrations cannot itself be a migration. The table is created by this program with
``IF NOT EXISTS``, inside the demo database only, and it holds no product data. It *is*
inside the fingerprint's schema prefixes (``trappoint%``), so it is created before the
fingerprint is taken and therefore appears in both the recorded value and the check.

WHICH DATABASE — AND WHY THE DSN IS NOT ASKED
---------------------------------------------
``COCKROACH_DSN`` in the repo-root ``.env`` ends ``/defaultdb``. The demo lives in
``mainline_demo``. A program that trusts the DSN's path segment connects successfully,
finds an empty catalogue and fails ``UndefinedTable: relation "mainline.permit" does not
exist`` — a confusing report of a database that is perfectly healthy. So the target
database is **always** substituted into the DSN by name (:func:`rewrite_dsn`), and then
**read back out of the server** with ``SELECT current_database()`` and compared. The
comparison is printed on every run and recorded in the evidence, along with the path
segment that was overridden, because "which database did that number come from" is the
first question anyone asks of a deploy artefact.

Usage::

    .venv/Scripts/python.exe scripts/deploy/cloud_chain.py                  # Cloud, from .env
    .venv/Scripts/python.exe scripts/deploy/cloud_chain.py --recreate       # drop and rebuild
    .venv/Scripts/python.exe scripts/deploy/cloud_chain.py --retry-probe    # prove the 40001 loop
    .venv/Scripts/python.exe scripts/deploy/cloud_chain.py --verify-build \\
        --inject-40001 3 --inject-into 0002_schema_meas.sql --jitter-seed 40001
                                        # re-apply all 271 to Cloud, into a throwaway database,
                                        # with a REAL migration made to hit 40001 and recover
    .venv/Scripts/python.exe scripts/deploy/cloud_chain.py \\
        --dsn postgresql://root@localhost:26257/defaultdb?sslmode=disable \\
        --database w_w2_cloud_database                                       # local rehearsal

Exit codes:

* ``0`` — the chain is applied and the database matches its marker. Includes the
  ``unchanged`` path and the "applied with attributed failures" path: an attributed
  failure is a *recorded gap*, not a deploy error, and the evidence names every one.
  Under ``--retry-probe``, all three retry cases behaved as specified.
* ``1`` — at least one migration failed for a reason this program could not attribute, or
  a ``--retry-probe`` case did not behave as specified.
* ``2`` — no DSN, no migration tree, or the cluster could not be reached.
* ``3`` — the database exists and does not match, or the server reports a different
  ``current_database()`` from the one requested. Nothing was changed. ``--recreate``.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import random
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import psycopg

EXIT_OK = 0
EXIT_UNATTRIBUTED = 1
EXIT_USAGE = 2
EXIT_MISMATCH = 3

#: Attempts per statement — the BOUND. Five waits under the schedule below total at most
#: 7.75 s, which is longer than any contention window observed on this cluster and short
#: enough that a statement which is genuinely broken does not hold the deploy for a minute.
#: A retry loop without a bound is a hang with better manners.
MAX_ATTEMPTS = 6

#: Backoff base and ceiling. Attempt *n* draws from a window whose top is
#: ``min(BACKOFF_BASE * 2 ** (n - 1), BACKOFF_CAP)`` — 0.25, 0.50, 1.00, 2.00, 4.00 s.
BACKOFF_BASE = 0.25
BACKOFF_CAP = 4.0

#: Equal jitter: half the window is always waited, half is random. Full jitter can draw
#: ~0 s and re-collide immediately; no jitter marches every contending client back into
#: the same instant, which is the behaviour that turns one ``40001`` into a convoy. The
#: exact sleep of every attempt is recorded, so the schedule is auditable rather than
#: asserted.
JITTER_FLOOR = 0.5

#: Seeded so a published transcript can be reproduced. ``--jitter-seed`` sets it; without
#: it the generator is seeded from the OS and the evidence says ``"os entropy"``.
_JITTER = random.Random()  # noqa: S311 - a backoff schedule, not a key; reproducibility wanted

#: The retryable SQLSTATE, and the only one. ``40001`` is CockroachDB's serialization
#: failure; every other state is a fact about the SQL and retrying it is a way of
#: reporting the same defect five more times.
RETRYABLE = "40001"

#: What the demo database is called. Not a throwaway name: the read API, the seeds and
#: the judge pack all address this database by name.
DEFAULT_DATABASE = "mainline_demo"

#: Cloud Basic enforces ``gc.ttlseconds = 4500``. Pinning the same value locally makes the
#: laptop the *stricter* environment, so a query that works locally works on Cloud.
DEFAULT_GC_TTLSECONDS = 4500

#: Fingerprint scope. Mirrors ``trappoint_migrate.runner.DEFAULT_SCHEMA_PREFIXES``, and is
#: restated here so that this program keeps working if the import is unavailable.
SCHEMA_PREFIXES: tuple[str, ...] = ("mainline%", "trappoint%")

_MIGRATION_NAME = re.compile(r"^(\d{4})([a-z]?)_[a-z0-9_]+\.sql$")
_MISSING_RELATION = re.compile(r'relation "([^"]+)" does not exist')
_UNDEFINED_OBJECT = re.compile(r'(?:type|function|column) "?([A-Za-z0-9_.]+)"? does not exist')

MARKER_DDL = """
CREATE TABLE IF NOT EXISTS trappoint.deploy_chain (
    marker_id        STRING      NOT NULL,
    tree_fingerprint BYTES       NOT NULL,
    live_fingerprint BYTES       NOT NULL,
    files            INT8        NOT NULL,
    applied          INT8        NOT NULL,
    failed           INT8        NOT NULL,
    retried          INT8        NOT NULL,
    total_seconds    FLOAT8      NOT NULL,
    applied_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    applied_by       STRING      NOT NULL,
    CONSTRAINT deploy_chain_pkey PRIMARY KEY (marker_id),
    CONSTRAINT deploy_chain_tree_sized CHECK (length(tree_fingerprint) = 32),
    CONSTRAINT deploy_chain_live_sized CHECK (length(live_fingerprint) = 32),
    CONSTRAINT deploy_chain_counts_agree CHECK (applied + failed = files),
    CONSTRAINT deploy_chain_retried_bounded CHECK (retried >= 0 AND retried <= applied)
)
""".strip()


# ═════════════════════════════════════════════════════════════════════════════════════
# secrets, DSNs and the one place either is allowed near stdout
# ═════════════════════════════════════════════════════════════════════════════════════


def redact(text: str) -> str:
    """Strip anything password-shaped out of *text*.

    Every string this package prints or writes to an evidence file passes through here.
    A driver error message quotes the connection string more often than anyone expects —
    ``psycopg.OperationalError`` does it on almost every failure path — so the redaction
    belongs at the boundary rather than at each call site, where one missed ``print`` is a
    password in a committed JSON file.
    """
    text = re.sub(r"(?i)(postgres(?:ql)?://[^:/@\s]+):[^@\s]*@", r"\1:***@", text)
    text = re.sub(r"(?i)\bpassword\s*=\s*'[^']*'", "password = '***'", text)
    return re.sub(r"(?i)\bpassword\s*=\s*[^\s&;]+", "password=***", text)


def rewrite_dsn(
    dsn: str,
    *,
    database: str | None = None,
    connect_timeout: int = 20,
    application_name: str = "mainline-deploy",
) -> str:
    """Return *dsn* pointed at *database*, with a connect timeout and an application name.

    ``connect_timeout`` is applied by libpq **per resolved address**, which is what stops a
    host where ``localhost`` resolves to a dead ``::1`` first from costing a full TCP
    timeout per connection. ``application_name`` shows up in ``SHOW SESSIONS`` and in the
    Cloud console, so a long-running deploy is attributable without anyone guessing.
    """
    parts = urlsplit(dsn)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query.setdefault("connect_timeout", str(connect_timeout))
    query["application_name"] = application_name
    path = f"/{database}" if database is not None else (parts.path or "/defaultdb")
    return urlunsplit((parts.scheme, parts.netloc, path, urlencode(query), parts.fragment))


def cluster_label(dsn: str) -> str:
    """A human label for the target — host, port and database, and nothing else."""
    parts = urlsplit(dsn)
    host = parts.hostname or "?"
    port = parts.port or 26257
    return f"{host}:{port}{parts.path or ''}"


def dsn_path_segment(dsn: str) -> str:
    """The database the DSN *claims*, which this program deliberately does not believe."""
    return (urlsplit(dsn).path or "").lstrip("/") or "(none)"


def connected_database(conn: psycopg.Connection[Any]) -> str:
    """The database the SERVER says we are on. The only answer this program accepts."""
    row = conn.execute("SELECT current_database()").fetchone()
    return str(row[0]) if row else ""


def database_report(dsn: str, requested: str, observed: str) -> dict[str, Any]:
    """Record which database was used, what the DSN said, and that the two were compared.

    The committed ``COCKROACH_DSN`` ends ``/defaultdb`` while the demo lives in
    ``mainline_demo``. Both facts belong in the artefact: a reader who finds a row count in
    this file and cannot tell which database produced it has been given a number, not
    evidence.
    """
    return {
        "requested": requested,
        "confirmed_by_server": observed,
        "matches": observed == requested,
        "dsn_path_segment": dsn_path_segment(dsn),
        "selected_how": (
            "substituted into the DSN by name and verified with SELECT current_database(); "
            "the DSN's own path segment is never trusted"
        ),
    }


def sqlstate_of(exc: psycopg.Error) -> str:
    state = exc.sqlstate
    if state:
        return state
    diag = getattr(exc, "diag", None)
    return (diag.sqlstate if diag is not None else None) or "no-sqlstate"


def one_line(exc: BaseException) -> str:
    return redact(" ".join(str(exc).split()))[:400]


# ═════════════════════════════════════════════════════════════════════════════════════
# the retrying executor — the piece the whole package shares
# ═════════════════════════════════════════════════════════════════════════════════════


def backoff_for(attempt: int) -> float:
    """The wait after failed *attempt* (1-based), in seconds — capped, jittered, bounded."""
    window = min(BACKOFF_BASE * (2 ** (attempt - 1)), BACKOFF_CAP)
    return round(float(window * JITTER_FLOOR + window * (1.0 - JITTER_FLOOR) * _JITTER.random()), 3)


@dataclass(slots=True)
class Attempted:
    """One statement's outcome: what happened, how many tries, how long, and why it waited.

    ``waits`` is the actual sleep taken after each failed attempt, in order. It is carried
    rather than recomputed because a jittered schedule that is only described cannot be
    checked, and the whole point of publishing the retry loop is that somebody can add the
    numbers up.
    """

    seconds: float
    attempts: int
    sqlstate: str
    error: str | None = None
    waits: list[float] = field(default_factory=list)
    injected_40001: int = 0
    reconnects: int = 0
    trail: list[dict[str, Any]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.error is None

    @property
    def backoff_seconds(self) -> float:
        return round(sum(self.waits), 3)


class InjectedSerializationFailure(psycopg.errors.SerializationFailure):
    """A ``40001`` this program raised on purpose, so the recovery can be watched.

    A distinct subclass, not a bare ``SerializationFailure``, for one reason: nothing that
    reads the evidence should ever have to wonder whether a recorded retry was the
    cluster's or ours. The class name lands in ``trail[*].raised``, the count lands in
    ``injected_40001``, and the honest totals exclude it.
    """


class Applier:
    """An autocommit connection that retries ``40001`` and reconnects when dropped.

    Autocommit is not an optimisation. CockroachDB DDL inside a multi-statement
    transaction can fail at ``COMMIT`` even when every statement succeeded, so a shared
    transaction would let one late failure retroactively un-apply files this report had
    already called applied.

    ``inject_40001`` arms the fault injector: the first *N* attempts of the first statement
    whose label or text contains ``inject_into`` raise before the statement is sent, so the
    server never sees the attempt and no partial work has to be undone. The budget is
    consumed once — a chain run with ``--inject-40001 2`` perturbs exactly one file.
    """

    def __init__(self, dsn: str, *, inject_40001: int = 0, inject_into: str | None = None) -> None:
        self._dsn = dsn
        self.conn = psycopg.connect(dsn, autocommit=True)
        self.reconnects = 0
        self._inject_budget = max(0, inject_40001)
        self._inject_into = inject_into or ""
        self.injections: list[dict[str, Any]] = []

    @property
    def database(self) -> str:
        """What the SERVER says this connection is on. Never the DSN's path segment."""
        row = self.conn.execute("SELECT current_database()").fetchone()
        return str(row[0]) if row else ""

    def arm(self, inject_40001: int, inject_into: str | None = None) -> None:
        """Re-arm the fault injector between probe cases, on the same live connection."""
        self._inject_budget = max(0, inject_40001)
        self._inject_into = inject_into or ""

    def close(self) -> None:
        # Closing a connection the server already dropped raises, and there is nothing to do
        # about it: the socket is gone either way. Suppressed rather than logged, because a
        # deploy log that reports a failure to close a dead connection trains its reader to
        # skim.
        with contextlib.suppress(Exception):
            self.conn.close()

    def _reconnect(self) -> None:
        self.close()
        self.conn = psycopg.connect(self._dsn, autocommit=True)
        self.reconnects += 1

    def _maybe_inject(self, label: str, sql: str, attempt: int) -> None:
        if self._inject_budget <= 0:
            return
        if self._inject_into and self._inject_into not in label and self._inject_into not in sql:
            return
        self._inject_budget -= 1
        self.injections.append({"label": label, "attempt": attempt})
        raise InjectedSerializationFailure(
            "injected by scripts/deploy/cloud_chain.py --inject-40001: simulated "
            "TransactionRetryError: retry txn (RETRY_SERIALIZABLE - failed preemptive refresh)"
        )

    # One branch per FAILURE CLASS, and the order of the branches is the load-bearing part.
    # `psycopg.errors.SerializationFailure` inherits from `OperationalError`, so testing the
    # exception class first would file every genuine 40001 under "the socket died" and throw
    # away a healthy connection to recover from contention. SQLSTATE first, class second.
    def run(self, sql: str, *, label: str = "") -> Attempted:
        started = time.time()
        attempts = 0
        state = "00000"
        error: str | None = None
        waits: list[float] = []
        injected = 0
        reconnects_before = self.reconnects
        trail: list[dict[str, Any]] = []
        while attempts < MAX_ATTEMPTS:
            attempts += 1
            try:
                self._maybe_inject(label, sql, attempts)
                self.conn.execute(sql)
            except psycopg.Error as exc:
                state, error = sqlstate_of(exc), one_line(exc)
                retryable = state == RETRYABLE
                if isinstance(exc, InjectedSerializationFailure):
                    injected += 1
                entry: dict[str, Any] = {
                    "attempt": attempts,
                    "sqlstate": state,
                    "raised": type(exc).__name__,
                    "retryable": retryable,
                }
                if not retryable and isinstance(exc, psycopg.OperationalError):
                    # Not contention — the connection itself went away, a Cloud node drained
                    # or the proxy cut an idle session. Not the statement's fault, so it is
                    # not counted as one: rebuild the socket and try the same statement again.
                    entry["action"] = "reconnect"
                    retryable = True
                    if attempts < MAX_ATTEMPTS:
                        try:
                            self._reconnect()
                        except psycopg.Error as reconnect_exc:
                            state, error = sqlstate_of(reconnect_exc), one_line(reconnect_exc)
                            entry["action"] = "reconnect_failed"
                            trail.append(entry)
                            break
                if not retryable or attempts >= MAX_ATTEMPTS:
                    entry.setdefault("action", "give_up" if retryable else "not_retryable")
                    trail.append(entry)
                    break
                wait = backoff_for(attempts)
                entry.setdefault("action", "retry")
                entry["waited_seconds"] = wait
                trail.append(entry)
                waits.append(wait)
                time.sleep(wait)
                continue
            else:
                error, state = None, "00000"
                trail.append({"attempt": attempts, "sqlstate": "00000", "action": "applied"})
                break
        return Attempted(
            seconds=round(time.time() - started, 3),
            attempts=attempts,
            sqlstate=state,
            error=error,
            waits=waits,
            injected_40001=injected,
            reconnects=self.reconnects - reconnects_before,
            trail=trail,
        )


# ═════════════════════════════════════════════════════════════════════════════════════
# fingerprints
# ═════════════════════════════════════════════════════════════════════════════════════


def repo_root() -> Path:
    here = Path(__file__).resolve().parent
    for candidate in (here, *here.parents):
        if (candidate / "verticals").is_dir() and (candidate / "packages").is_dir():
            return candidate
    return Path.cwd().resolve()


def tree_fingerprint(migrations: Path) -> bytes:
    """The fingerprint of the *inputs* — the migration files, before anything is applied.

    ``trappoint_migrate.fingerprint.stable_tree_fingerprint`` is the authority and is used
    when it imports. The fallback is the same rule stated locally (POSIX-relative path,
    CRLF normalised, trailing whitespace stripped, sorted by path) so that a machine
    without the workspace installed still gets the same digest for the same tree.
    """
    try:
        from trappoint_migrate.fingerprint import stable_tree_fingerprint

        return stable_tree_fingerprint([migrations]).digest
    except Exception:  # noqa: BLE001 - a missing workspace must not stop a deploy
        import hashlib

        accumulator = hashlib.sha256()
        for path in sorted(migrations.rglob("*.sql"), key=lambda p: p.as_posix()):
            body = path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
            body = "\n".join(line.rstrip() for line in body.split("\n")).strip("\n") + "\n"
            accumulator.update(path.relative_to(migrations).as_posix().encode("utf-8"))
            accumulator.update(b"\x1f")
            accumulator.update(body.encode("utf-8"))
            accumulator.update(b"\x1e")
        return accumulator.digest()


def live_fingerprint(conn: psycopg.Connection[Any]) -> bytes:
    """The fingerprint of what the cluster actually holds.

    ``trappoint_migrate.attest.stable_fingerprint`` computes it twice and refuses when the
    two disagree, which is the property that makes it usable as a deploy gate: a
    fingerprint that flickers trains everyone to ignore the alarm. The fallback below is a
    catalogue digest over the same schema prefixes — weaker, because it does not read
    routine bodies, and the evidence records which of the two was used.
    """
    try:
        from trappoint_migrate.fingerprint import live_fingerprint as _live

        return _live(conn, schema_prefixes=SCHEMA_PREFIXES).digest
    except Exception:  # noqa: BLE001
        import hashlib

        rows = conn.execute(
            "SELECT table_schema, table_name, column_name, data_type, is_nullable "
            "FROM information_schema.columns "
            "WHERE table_schema LIKE 'mainline%' OR table_schema LIKE 'trappoint%' "
            "ORDER BY table_schema, table_name, column_name"
        ).fetchall()
        accumulator = hashlib.sha256()
        for row in rows:
            accumulator.update(("\x1f".join(str(value) for value in row) + "\x1e").encode("utf-8"))
        return accumulator.digest()


#: The five parts of the live schema, in the order they are hashed. Mirrors
#: ``trappoint_migrate.attest.fingerprint``'s scope so that the name-normalised digest below
#: covers exactly what the authoritative fingerprint covers, and nothing more.
_SNAPSHOT_STATEMENTS: tuple[tuple[str, str], ...] = (
    ("schemas", "SHOW CREATE ALL SCHEMAS"),
    ("types", "SHOW CREATE ALL TYPES"),
    ("tables", "SHOW CREATE ALL TABLES"),
)


def schema_snapshot(conn: psycopg.Connection[Any], database: str) -> dict[str, list[str]]:
    """The live schema as sorted text, with the DATABASE NAME replaced by a placeholder.

    WHY THIS EXISTS, AND IT IS A MEASURED PLATFORM FACT RATHER THAN A PREFERENCE
    ---------------------------------------------------------------------------
    The authoritative live fingerprint is a digest of ``SHOW CREATE ALL {SCHEMAS,TYPES,TABLES}``
    plus ``pg_get_functiondef`` and ``pg_get_triggerdef``. On CockroachDB v26.2.5 **every one of
    those renders fully-qualified names that include the database**::

        CREATE TRIGGER append_only BEFORE UPDATE OR DELETE
          ON mainline_demo.mainline.exposure_receipt …

    so two databases holding byte-identical schemas produce different fingerprints purely because
    they are called different things. That is correct for the fingerprint's own job — detecting
    drift in *one* database over time — and fatal for comparing *two*.

    There is a second, subtler effect, and it was found by controlled experiment: the SQL
    pretty-printer wraps on line width, and the qualified prefix counts toward that width. The
    same view DDL, applied to two databases whose names differ only in LENGTH, renders as::

        db name 12 chars:   JOIN <db>.public.t_commit_obj AS co ON co.commit_id = cv.commit_id
        db name 34 chars:   JOIN <db>.public.t_commit_obj AS co ON
                                    co.commit_id = cv.commit_id

    Replacing the name is therefore not enough. The comparison is only sound when the two
    databases have names of the **same length** — which is why :func:`verification_database_name`
    returns a name exactly as long as the one it stands in for.
    """
    out: dict[str, list[str]] = {}
    for label, statement in _SNAPSHOT_STATEMENTS:
        out[label] = sorted(
            str(row[0]).replace(database, "<db>") for row in conn.execute(statement).fetchall()
        )
    out["routines"] = sorted(
        f"{name}\n{body}".replace(database, "<db>")
        for name, body in conn.execute(
            "SELECT p.proname, pg_get_functiondef(p.oid) FROM pg_catalog.pg_proc p "
            "JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace "
            "WHERE n.nspname LIKE 'mainline%' OR n.nspname LIKE 'trappoint%'"
        ).fetchall()
    )
    out["triggers"] = sorted(
        f"{name}\n{body}".replace(database, "<db>")
        for name, body in conn.execute(
            "SELECT t.tgname, pg_get_triggerdef(t.oid) FROM pg_catalog.pg_trigger t "
            "WHERE NOT t.tgisinternal"
        ).fetchall()
    )
    return out


def snapshot_digest(snapshot: dict[str, list[str]]) -> str:
    import hashlib

    accumulator = hashlib.sha256()
    for label in ("schemas", "types", "tables", "routines", "triggers"):
        for entry in snapshot.get(label, []):
            accumulator.update(entry.encode("utf-8"))
            accumulator.update(b"\x1e")
    return accumulator.hexdigest()


def verification_database_name(database: str) -> str:
    """A name for the throwaway verification database that is **exactly as long** as *database*.

    Equal length is load-bearing, not cosmetic — see :func:`schema_snapshot`. A longer name
    changes where the SQL pretty-printer wraps a long ``JOIN … ON`` clause, and the comparison
    then reports a difference that is entirely an artefact of the name it chose for itself.
    """
    suffix = "_vfy"
    if len(database) <= len(suffix):
        return database[:-1] + "v" if len(database) > 1 else "v"
    return database[: len(database) - len(suffix)] + suffix


def fingerprint_source() -> str:
    try:
        import trappoint_migrate.fingerprint  # noqa: F401
    except Exception:  # noqa: BLE001
        return "scripts/deploy/cloud_chain.py fallback (information_schema.columns only)"
    return "trappoint_migrate.fingerprint (stable, double-computed)"


# ═════════════════════════════════════════════════════════════════════════════════════
# the chain
# ═════════════════════════════════════════════════════════════════════════════════════


def discover(migrations: Path) -> list[Path]:
    """Every migration, in ALLOCATION ORDER.

    Allocation order is lexicographic on the filename stem, which is what makes
    ``(49, "z") < (50, "")``. ``trappoint_migrate.discovery`` is the authority; the
    fallback sorts on ``(number, letter)`` explicitly, which is the same sequence.
    """
    try:
        from trappoint_migrate.discovery import discover as _discover

        return [migration.path for migration in _discover(migrations)]
    except Exception:  # noqa: BLE001
        found: list[tuple[int, str, Path]] = []
        for path in migrations.glob("*.sql"):
            match = _MIGRATION_NAME.match(path.name)
            if match:
                found.append((int(match.group(1)), match.group(2), path))
        found.sort(key=lambda item: (item[0], item[1]))
        return [path for _, _, path in found]


def attribute(message: str) -> dict[str, Any]:
    """Say *why* a migration failed, in the terms a reader can act on.

    An attributed failure names the object that was absent. That is the difference between
    "15 migrations failed" — which reads as a broken repository — and "15 migrations have a
    consumer and no producer, here they are" — which is a finding with a fix beside it.
    """
    missing = _MISSING_RELATION.search(message)
    if missing:
        return {"kind": "missing_relation", "object": missing.group(1)}
    undefined = _UNDEFINED_OBJECT.search(message)
    if undefined:
        return {"kind": "missing_object", "object": undefined.group(1)}
    return {"kind": "unattributed", "object": None}


def row_of(name: str, outcome: Attempted) -> dict[str, Any]:
    """One statement's row, shaped the same way in the chain report and the seed report.

    ``injected_40001`` is present on every row rather than only on perturbed ones, so that
    "0" is a statement the file makes rather than a key a reader has to notice is absent.
    """
    row: dict[str, Any] = {
        "file": name,
        "seconds": outcome.seconds,
        "attempts": outcome.attempts,
        "sqlstate": outcome.sqlstate,
        "error": outcome.error,
        "injected_40001": outcome.injected_40001,
    }
    if outcome.attempts > 1:
        row["backoff_seconds"] = outcome.backoff_seconds
        row["waits_seconds"] = outcome.waits
        row["trail"] = outcome.trail
    return row


@dataclass(slots=True)
class ChainRun:
    rows: list[dict[str, Any]] = field(default_factory=list)
    applied: int = 0
    failed: int = 0
    retried: int = 0
    injected_retried: int = 0
    reconnects: int = 0
    seconds: float = 0.0

    @property
    def unattributed(self) -> list[dict[str, Any]]:
        return [r for r in self.rows if r["error"] and r["attribution"]["kind"] == "unattributed"]


def apply_chain(applier: Applier, paths: list[Path], *, quiet: bool = False) -> ChainRun:
    run = ChainRun()
    started = time.time()
    for index, path in enumerate(paths, 1):
        outcome = applier.run(path.read_text(encoding="utf-8"), label=path.name)
        row = row_of(path.name, outcome)
        row["attribution"] = attribute(outcome.error) if outcome.error else {"kind": "applied"}
        run.rows.append(row)
        if outcome.ok:
            run.applied += 1
            # SPONTANEOUS retries only. A file that retried solely because this program
            # injected the failure is counted separately, so `files_that_needed_a_retry`
            # never gets to claim the cluster did something it did not do.
            if outcome.attempts > outcome.injected_40001 + 1:
                run.retried += 1
            if outcome.injected_40001:
                run.injected_retried += 1
        else:
            run.failed += 1
        if not quiet and (index % 25 == 0 or not outcome.ok or outcome.attempts > 1):
            status = "OK" if outcome.ok else f"FAIL {outcome.sqlstate}"
            injected = f" injected={outcome.injected_40001}" if outcome.injected_40001 else ""
            print(
                f"  [{index:>3}/{len(paths)}] {path.name:<44} {status:<12} "
                f"{outcome.seconds:>6.2f}s attempts={outcome.attempts}{injected}",
                flush=True,
            )
    run.seconds = round(time.time() - started, 1)
    run.reconnects = applier.reconnects
    return run


# ═════════════════════════════════════════════════════════════════════════════════════
# the retry probe — the loop, watched, against the live cluster
# ═════════════════════════════════════════════════════════════════════════════════════

#: The probe's statement. ``SELECT 1`` writes nothing, locks nothing and costs nothing, so
#: the transcript is about the executor and about nothing else. The relation named by the
#: third case does not exist and is not meant to: a real ``42P01`` from the real server is
#: the only honest way to show that a non-retryable state is attempted exactly once.
PROBE_OK = "SELECT 1"
PROBE_MISSING = "SELECT 1 FROM mainline.no_such_relation_retry_probe"


def retry_probe(applier: Applier, *, injections: int = 2) -> dict[str, Any]:
    """Fire the ``40001`` loop on purpose and record what it did, case by case.

    Three cases, and each one answers a question a reader is entitled to ask of a retry
    loop that has never been seen to fire:

    * **recovers** — does a transient ``40001`` actually get past it? *N* injected
      failures, then the statement runs. Attempts, per-attempt sleeps and total backoff
      are recorded.
    * **bounded** — does it stop? :data:`MAX_ATTEMPTS` injected failures, and the loop
      must give up at exactly that number and report ``40001`` rather than spin.
    * **not_retryable** — does it retry things it should not? A genuine ``42P01`` from the
      server must be attempted once and reported once.

    Failing a case is a defect in this file, and the caller exits non-zero for it.
    """
    cases: list[dict[str, Any]] = []

    applier.arm(injections, "retry-probe")
    recovered = applier.run(PROBE_OK, label="retry-probe/recovers")
    cases.append(
        {
            "case": "recovers",
            "statement": PROBE_OK,
            "injected_40001": recovered.injected_40001,
            "attempts": recovered.attempts,
            "sqlstate": recovered.sqlstate,
            "error": recovered.error,
            "waits_seconds": recovered.waits,
            "backoff_seconds": recovered.backoff_seconds,
            "elapsed_seconds": recovered.seconds,
            "trail": recovered.trail,
            "expected": (
                f"{injections} injected failures, then success on attempt {injections + 1}"
            ),
            "held": (
                recovered.ok
                and recovered.injected_40001 == injections
                and recovered.attempts == injections + 1
                and len(recovered.waits) == injections
            ),
        }
    )

    applier.arm(MAX_ATTEMPTS, "retry-probe")
    exhausted = applier.run(PROBE_OK, label="retry-probe/bounded")
    cases.append(
        {
            "case": "bounded",
            "statement": PROBE_OK,
            "injected_40001": exhausted.injected_40001,
            "attempts": exhausted.attempts,
            "sqlstate": exhausted.sqlstate,
            "error": exhausted.error,
            "waits_seconds": exhausted.waits,
            "backoff_seconds": exhausted.backoff_seconds,
            "elapsed_seconds": exhausted.seconds,
            "trail": exhausted.trail,
            "expected": (
                f"gives up after MAX_ATTEMPTS={MAX_ATTEMPTS} and reports {RETRYABLE}, "
                f"having waited {MAX_ATTEMPTS - 1} times"
            ),
            "held": (
                not exhausted.ok
                and exhausted.attempts == MAX_ATTEMPTS
                and exhausted.sqlstate == RETRYABLE
                and len(exhausted.waits) == MAX_ATTEMPTS - 1
            ),
        }
    )

    applier.arm(0)
    refused = applier.run(PROBE_MISSING, label="retry-probe/not_retryable")
    cases.append(
        {
            "case": "not_retryable",
            "statement": PROBE_MISSING,
            "injected_40001": refused.injected_40001,
            "attempts": refused.attempts,
            "sqlstate": refused.sqlstate,
            "error": refused.error,
            "waits_seconds": refused.waits,
            "backoff_seconds": refused.backoff_seconds,
            "elapsed_seconds": refused.seconds,
            "trail": refused.trail,
            "expected": "a real 42P01 from the server, attempted once, not retried",
            "held": (
                not refused.ok
                and refused.attempts == 1
                and refused.sqlstate == "42P01"
                and not refused.waits
            ),
        }
    )

    return {
        "what_this_is": (
            "The 40001 retry loop, made to fire. Every Cloud chain run so far has reported "
            "files_that_needed_a_retry = 0, which proves the loop was not needed, not that "
            "it works. These three cases inject psycopg.errors.SerializationFailure BEFORE "
            "the statement reaches the server — so no partial work is done and the recovery "
            "is the loop's alone — and record what the loop did about it."
        ),
        "injected_by": (
            "scripts/deploy/cloud_chain.py --inject-40001 (InjectedSerializationFailure)"
        ),
        "not_a_cluster_event": (
            "These 40001s were raised by this program. The cluster did not produce them. "
            "No number in this file's `files_that_needed_a_retry` comes from here."
        ),
        "max_attempts": MAX_ATTEMPTS,
        "backoff": (
            f"equal jitter: attempt n waits between {JITTER_FLOOR:.0%} and 100% of "
            f"min({BACKOFF_BASE} * 2^(n-1), {BACKOFF_CAP}) seconds"
        ),
        "retryable_sqlstate": RETRYABLE,
        "cases": cases,
        "verdict": "RETRY LOOP PROVEN" if all(c["held"] for c in cases) else "RETRY LOOP FAILED",
    }


def bootstrap(dsn: str, root: Path, *, quiet: bool = False) -> dict[str, Any]:
    """Run ``trappoint migrate bootstrap`` as its OWN step, before the file loop.

    Separate on purpose. The first Cloud attempt died inside bootstrap, and a bootstrap
    folded into the loop reports that as "file 0001 failed", which is a diagnosis of the
    wrong thing. Ruling D6 also makes it genuinely a different operation: the bookkeeping
    schema sits outside the numbered sequence, and ``0119a_fn_explain_refusal.sql`` needs
    it to exist, so skipping it makes a later file fail for a reason that is not a defect.
    """
    started = time.time()
    console = root / ".venv" / "Scripts" / "trappoint.exe"
    argv = (
        [str(console), "migrate", "bootstrap", "--dsn", dsn]
        if console.is_file()
        else [sys.executable, "-m", "trappoint_migrate", "bootstrap", "--dsn", dsn]
    )
    try:
        completed = subprocess.run(  # fixed argv, no shell
            argv, capture_output=True, text=True, cwd=str(root), timeout=300, check=False
        )
    except (OSError, subprocess.SubprocessError) as exc:
        result = {"ok": False, "how": "subprocess", "error": one_line(exc)}
    else:
        result = {
            "ok": completed.returncode == 0,
            "how": argv[0].rsplit("\\", 1)[-1] + " migrate bootstrap",
            "returncode": completed.returncode,
            "stdout": redact(completed.stdout.strip())[-1200:],
            "stderr": redact(completed.stderr.strip())[-1200:],
        }
    if not result["ok"]:
        # The console script is not on PATH in every environment the demo is deployed
        # from. The in-process path calls the same function the CLI calls, so the two
        # cannot diverge, and the evidence records that the fallback was taken.
        try:
            from trappoint_migrate.bootstrap import bootstrap as bootstrap_fn
            from trappoint_migrate.runner import actor

            with psycopg.connect(dsn, autocommit=True) as conn:
                ensured = bootstrap_fn(conn, applied_by=actor(), schema_prefixes=SCHEMA_PREFIXES)
            result = {
                "ok": True,
                "how": "trappoint_migrate.bootstrap.bootstrap (in-process fallback)",
                "subprocess_note": redact(str(result))[:400],
                "ensured": list(ensured),
            }
        except Exception as exc:  # noqa: BLE001
            result["fallback_error"] = one_line(exc)
    result["seconds"] = round(time.time() - started, 1)
    if not quiet:
        print(
            f"  bootstrap    {result['how']}  ok={result['ok']}  {result['seconds']}s", flush=True
        )
    return result


# ═════════════════════════════════════════════════════════════════════════════════════
# the marker — how a second run knows it has nothing to do
# ═════════════════════════════════════════════════════════════════════════════════════


def database_exists(admin: psycopg.Connection[Any], database: str) -> bool:
    """Is *database* on this cluster?

    Asked of ``[SHOW DATABASES]`` rather than of ``crdb_internal.databases``, because
    CockroachDB v26.2 refuses the latter outright — *"Access to crdb_internal and system
    is restricted"*, ``42501``, with a hint offering ``allow_unsafe_internals``. Taking
    that hint would make a deploy tool depend on an interface the vendor calls
    unsupported; the bracketed statement source is the supported alternative and returns
    the same answer.
    """
    row = admin.execute(
        "SELECT count(*) FROM [SHOW DATABASES] WHERE database_name = %s", (database,)
    ).fetchone()
    return bool(row and row[0])


def read_marker(conn: psycopg.Connection[Any], database: str) -> dict[str, Any] | None:
    try:
        row = conn.execute(
            "SELECT tree_fingerprint, live_fingerprint, files, applied, failed, retried, "
            "total_seconds, applied_at, applied_by FROM trappoint.deploy_chain "
            "WHERE marker_id = %s",
            (database,),
        ).fetchone()
    except psycopg.Error:
        return None
    if row is None:
        return None
    return {
        "tree_fingerprint": bytes(row[0]),
        "live_fingerprint": bytes(row[1]),
        "files": int(row[2]),
        "applied": int(row[3]),
        "failed": int(row[4]),
        "retried": int(row[5]),
        "total_seconds": float(row[6]),
        "applied_at": row[7].astimezone(UTC).isoformat(),
        "applied_by": row[8],
    }


def write_marker(
    conn: psycopg.Connection[Any], database: str, tree: bytes, live: bytes, run: ChainRun
) -> None:
    conn.execute(MARKER_DDL)
    conn.execute(
        "UPSERT INTO trappoint.deploy_chain (marker_id, tree_fingerprint, live_fingerprint, "
        "files, applied, failed, retried, total_seconds, applied_at, applied_by) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, now(), %s)",
        (
            database,
            tree,
            live,
            len(run.rows),
            run.applied,
            run.failed,
            run.retried,
            run.seconds,
            "scripts/deploy/cloud_chain.py",
        ),
    )


def configure_zone(
    admin: psycopg.Connection[Any], database: str, gc_ttlseconds: int
) -> dict[str, Any]:
    """Pin ``gc.ttlseconds``, and read back what the cluster actually kept.

    Asserted every run, not only on create. It is idempotent, it is one statement, and
    the alternative is a zone that silently reverts on a cluster operation and a demo
    that starts failing historical reads for a reason nobody can see.
    """
    try:
        admin.execute(
            f'ALTER DATABASE "{database}" CONFIGURE ZONE USING gc.ttlseconds = {gc_ttlseconds}'
        )
    except psycopg.Error as exc:
        return {"requested": gc_ttlseconds, "accepted": False, "error": one_line(exc)}
    observed: int | None = None
    try:
        row = admin.execute(f'SHOW ZONE CONFIGURATION FOR DATABASE "{database}"').fetchone()
        if row is not None:
            match = re.search(r"gc\.ttlseconds\s*=\s*(\d+)", str(row[1]))
            if match:
                observed = int(match.group(1))
    except psycopg.Error:
        observed = None
    return {"requested": gc_ttlseconds, "accepted": True, "observed": observed}


# ═════════════════════════════════════════════════════════════════════════════════════
# the run
# ═════════════════════════════════════════════════════════════════════════════════════


# One branch per OUTCOME, and each one writes a different sentence into the evidence and into
# the operator's terminal. "the tree changed", "the schema drifted", "there is no marker",
# "already correct" and "just built it" are five different findings, and the whole value of an
# idempotent deploy tool is that it can tell them apart. Collapsing them into a table-driven
# loop would make every message generic, and the message is the product here.
def build(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:  # noqa: PLR0911, PLR0915
    root = repo_root()
    migrations = args.migrations or (root / "verticals" / "mainline" / "db" / "migrations")
    if not migrations.is_dir():
        raise SystemExit(f"cloud_chain: no migration tree at {migrations}")

    admin_dsn = rewrite_dsn(args.dsn, database="defaultdb", connect_timeout=args.connect_timeout)
    work_dsn = rewrite_dsn(args.dsn, database=args.database, connect_timeout=args.connect_timeout)
    started = time.time()

    evidence: dict[str, Any] = {
        "artefact": "MAINLINE cloud chain",
        "generated_at_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "generated_by": "scripts/deploy/cloud_chain.py",
        "target": {
            "cluster": cluster_label(args.dsn),
            "database": args.database,
            "migrations_dir": str(migrations.relative_to(root))
            if root in migrations.parents
            else str(migrations),
        },
        "fingerprint_source": fingerprint_source(),
    }

    tree = tree_fingerprint(migrations)
    evidence["tree_fingerprint"] = tree.hex()

    admin = psycopg.connect(admin_dsn, autocommit=True)
    version_row = admin.execute("SELECT version()").fetchone()
    evidence["target"]["version"] = str(version_row[0]) if version_row else "unknown"
    exists = database_exists(admin, args.database)

    # ── the idempotent path: an existing database that matches its own marker ─────────
    if exists and not args.recreate:
        probe = psycopg.connect(work_dsn, autocommit=True)
        evidence["target"]["database_selection"] = database_report(
            args.dsn, args.database, connected_database(probe)
        )
        if not evidence["target"]["database_selection"]["matches"]:
            observed = evidence["target"]["database_selection"]["confirmed_by_server"]
            probe.close()
            admin.close()
            evidence["outcome"] = "refused"
            evidence["reason"] = (
                f"asked for database {args.database!r} and the server answered "
                f"current_database() = {observed!r}. Nothing was read and nothing was changed."
            )
            return EXIT_MISMATCH, evidence
        marker = read_marker(probe, args.database)
        if marker is None:
            probe.close()
            admin.close()
            evidence["outcome"] = "refused"
            evidence["reason"] = (
                f'database "{args.database}" exists on {cluster_label(args.dsn)} but carries no '
                "trappoint.deploy_chain marker, so this program cannot tell what is in it. "
                "Nothing was changed. Re-run with --recreate to drop and rebuild it."
            )
            return EXIT_MISMATCH, evidence
        live = live_fingerprint(probe)
        probe.close()
        evidence["live_fingerprint"] = live.hex()
        evidence["marker"] = {
            **{k: v for k, v in marker.items() if not k.endswith("fingerprint")},
            "tree_fingerprint": marker["tree_fingerprint"].hex(),
            "live_fingerprint": marker["live_fingerprint"].hex(),
        }
        if marker["tree_fingerprint"] != tree:
            admin.close()
            evidence["outcome"] = "refused"
            evidence["reason"] = (
                "the migration tree has changed since this database was built "
                f"(tree {marker['tree_fingerprint'].hex()[:16]} recorded, {tree.hex()[:16]} now). "
                "Migration files are forward-only and are not written IF NOT EXISTS, so replaying "
                "them over a live database says nothing. Nothing was changed. Use --recreate."
            )
            return EXIT_MISMATCH, evidence
        if marker["live_fingerprint"] != live:
            admin.close()
            evidence["outcome"] = "refused"
            evidence["reason"] = (
                "the live schema no longer matches the fingerprint recorded when it was built "
                f"({marker['live_fingerprint'].hex()[:16]} recorded, {live.hex()[:16]} now) — "
                "something changed this database outside this program. Nothing was changed. "
                "Use --recreate."
            )
            return EXIT_MISMATCH, evidence
        evidence["zone"] = configure_zone(admin, args.database, args.gc_ttlseconds)
        admin.close()
        evidence["outcome"] = "unchanged"
        evidence["files"] = marker["files"]
        evidence["applied"] = marker["applied"]
        evidence["failed"] = marker["failed"]
        evidence["files_that_needed_a_retry"] = marker["retried"]
        evidence["total_seconds"] = round(time.time() - started, 1)
        evidence["chain_seconds_when_built"] = marker["total_seconds"]
        evidence["note"] = (
            "The chain was already applied and both fingerprints match. No migration ran. "
            "This is the second-run path and it is what 'idempotent' means here."
        )
        return EXIT_OK, evidence

    # ── the building path ─────────────────────────────────────────────────────────────
    if exists:
        print(f"  dropping     {args.database} (--recreate)", flush=True)
        admin.execute(f'DROP DATABASE IF EXISTS "{args.database}" CASCADE')
    admin.execute(f'CREATE DATABASE "{args.database}"')
    evidence["zone"] = configure_zone(admin, args.database, args.gc_ttlseconds)
    print(
        f"  database     {args.database} created; "
        f"gc.ttlseconds={evidence['zone'].get('observed', evidence['zone'].get('requested'))}",
        flush=True,
    )

    evidence["bootstrap"] = bootstrap(work_dsn, root)

    paths = discover(migrations)
    applier = Applier(work_dsn, inject_40001=args.inject_40001, inject_into=args.inject_into)
    evidence["target"]["database_selection"] = database_report(
        args.dsn, args.database, applier.database
    )
    if not evidence["target"]["database_selection"]["matches"]:
        observed = evidence["target"]["database_selection"]["confirmed_by_server"]
        applier.close()
        admin.close()
        evidence["outcome"] = "refused"
        evidence["reason"] = (
            f"asked for database {args.database!r} and the server answered "
            f"current_database() = {observed!r}. No migration was applied."
        )
        return EXIT_MISMATCH, evidence
    print(
        f"  chain        applying {len(paths)} migrations to "
        f"{evidence['target']['database_selection']['confirmed_by_server']}",
        flush=True,
    )
    run = apply_chain(applier, paths)

    # THE MARKER TABLE IS CREATED BEFORE THE FINGERPRINT IS TAKEN, and the order is
    # load-bearing rather than tidy. `trappoint%` is inside SCHEMA_PREFIXES, so
    # trappoint.deploy_chain is itself part of the live schema; recording a fingerprint
    # taken before it existed and then checking one taken after guarantees a mismatch on
    # every second run. Measured: it did exactly that once, and this comment is the
    # reason it will not do it again.
    applier.conn.execute(MARKER_DDL)
    live = live_fingerprint(applier.conn)
    write_marker(applier.conn, args.database, tree, live, run)
    applier.close()
    admin.close()

    failures = [r for r in run.rows if r["error"]]
    by_object: dict[str, list[str]] = {}
    for row in failures:
        key = row["attribution"].get("object") or "unattributed"
        by_object.setdefault(key, []).append(row["file"])

    evidence["live_fingerprint"] = live.hex()
    evidence["outcome"] = "applied"
    evidence["files"] = len(paths)
    evidence["applied"] = run.applied
    evidence["failed"] = run.failed
    evidence["files_that_needed_a_retry"] = run.retried
    evidence["files_with_injected_retries"] = run.injected_retried
    evidence["connection_reconnects"] = run.reconnects
    evidence["chain_seconds"] = run.seconds
    evidence["total_seconds"] = round(time.time() - started, 1)
    evidence["slowest"] = sorted(run.rows, key=lambda r: -r["seconds"])[:15]
    evidence["retried_files"] = [
        {
            "file": r["file"],
            "attempts": r["attempts"],
            "injected_40001": r["injected_40001"],
            "backoff_seconds": r.get("backoff_seconds"),
            "waits_seconds": r.get("waits_seconds"),
            "trail": r.get("trail"),
        }
        for r in run.rows
        if r["attempts"] > 1
    ]
    evidence["failures"] = failures
    evidence["failures_by_missing_object"] = by_object
    evidence["rows"] = run.rows

    if run.unattributed:
        evidence["verdict"] = "UNATTRIBUTED FAILURES"
        return EXIT_UNATTRIBUTED, evidence
    evidence["verdict"] = "APPLIED" if run.failed == 0 else "APPLIED WITH ATTRIBUTED GAPS"
    return EXIT_OK, evidence


def reattest(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:  # noqa: PLR0912, PLR0915
    """Re-point a live database's marker at the CURRENT tree, but only after measuring that
    the current tree builds exactly the schema that database already holds.

    THE PROBLEM THIS SOLVES, WHICH IS A REAL ONE AND NOT A CONVENIENCE
    -----------------------------------------------------------------
    The tree fingerprint covers every byte of every migration file, comments included. That
    is the correct scope — a comment is where a schema's *reasons* live, and a tool that
    ignored them would be blind to the edit most likely to be made carelessly. The
    consequence is that a comment-only correction to one migration makes a live database
    stop matching its marker, and the plain run then refuses with ``--recreate``.

    On a demo cluster that judges are pointed at, ``--recreate`` is the expensive answer: it
    drops the database, takes the demo down for the length of a full chain apply, and
    destroys every GRANT ``cloud_roles.py`` put on it, which another operator then has to
    restore. Rubber-stamping the marker is the dishonest answer.

    So this is the third answer, and it is a measurement rather than an assertion: apply the
    current tree, in full, to a **separate** database on the **same** cluster, and compare the
    two live schemas. The marker is re-pointed only if they are identical.

    THE COMPARISON IS NOT A FINGERPRINT COMPARISON, AND THE FIRST VERSION OF THIS FUNCTION
    WAS WRONG BECAUSE IT WAS
    -------------------------------------------------------------------------------------
    The authoritative live fingerprint embeds the database name in every rendered identifier,
    and the SQL pretty-printer's line wrapping depends on that name's *length* — both
    measured, see :func:`schema_snapshot`. Two byte-identical schemas in differently-named
    databases therefore have different fingerprints, always, and a re-attestation built on
    comparing them could never have succeeded. It refused for a reason that was about its own
    method rather than about the schema, which is the worst kind of red: one that looks like
    a finding.

    What is compared instead is the **name-normalised snapshot digest** — the same five parts,
    with the database name replaced by a placeholder, sorted and hashed — taken from two
    databases whose names are the same length, so the pretty-printer wraps them identically.
    The raw fingerprints are still recorded, and the target's raw fingerprint is still
    required to equal the one its marker recorded, because *that* comparison is between one
    database and itself and is exactly what proves nobody has drifted it.

    The verification build is not a rehearsal, either: it is a complete 271-file apply
    against the managed cluster, and its per-file transcript is what lands in the evidence.

    ``--verify-build`` RUNS THE SAME MEASUREMENT WITH NOTHING TO RE-ATTEST
    ---------------------------------------------------------------------
    Re-attestation refuses when the marker already names the tree, because there is then no
    marker to move. But the *measurement* it performs — apply the current tree, in full,
    to the live managed cluster, and compare the resulting schema with the demo database's —
    is worth taking on its own, and it is the only way to answer "does this chain still apply
    to CockroachDB Cloud **today**" without dropping the database judges are pointed at.

    ``--verify-build`` therefore performs exactly that build and comparison, **never writes
    the marker**, and appends the result to ``verification_builds`` in the evidence rather
    than overwriting the re-attestation that explains why the tree fingerprint last moved.
    Combined with ``--inject-40001 N --inject-into <file>`` it is also the strongest
    available proof of the retry loop: the file that retries is a *real migration*, applied
    to the *real managed cluster*, and its attempts, per-attempt sleeps and total backoff
    land in ``verification_builds[-1].chain.retried_files``.
    """
    root = repo_root()
    migrations = args.migrations or (root / "verticals" / "mainline" / "db" / "migrations")
    verify_db = verification_database_name(args.database)
    started = time.time()
    verify_only = bool(getattr(args, "verify_build", False))
    report_key = "verification_build" if verify_only else "reattestation"

    work_dsn = rewrite_dsn(
        args.dsn,
        database=args.database,
        connect_timeout=args.connect_timeout,
        application_name="mainline-deploy-verify" if verify_only else "mainline-deploy-reattest",
    )
    probe = psycopg.connect(work_dsn, autocommit=True)
    observed = connected_database(probe)
    version_row = probe.execute("SELECT version()").fetchone()
    tree = tree_fingerprint(migrations)

    evidence: dict[str, Any] = {
        "artefact": (
            f"MAINLINE cloud chain — full re-apply against {cluster_label(args.dsn)}"
            if verify_only
            else "MAINLINE cloud chain — tree re-attestation"
        ),
        "generated_at_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "generated_by": (
            "scripts/deploy/cloud_chain.py --verify-build"
            if verify_only
            else "scripts/deploy/cloud_chain.py --reattest"
        ),
        "outcome": "verified" if verify_only else "reattested",
        "target": {
            "cluster": cluster_label(args.dsn),
            "database": args.database,
            "version": str(version_row[0]) if version_row else "unknown",
            "database_selection": database_report(args.dsn, args.database, observed),
        },
        "tree_fingerprint": tree.hex(),
    }
    if observed != args.database:
        probe.close()
        evidence["outcome"] = "refused"
        evidence["reason"] = (
            f"asked for database {args.database!r} and the server answered "
            f"current_database() = {observed!r}. Nothing was verified."
        )
        return EXIT_MISMATCH, evidence

    marker = read_marker(probe, args.database)
    if marker is None:
        probe.close()
        evidence["outcome"] = "refused"
        evidence["reason"] = (
            f'database "{args.database}" carries no trappoint.deploy_chain marker, so there '
            "is nothing to re-attest. Nothing was changed."
        )
        return EXIT_MISMATCH, evidence
    live_now = live_fingerprint(probe)
    target_snapshot = schema_snapshot(probe, args.database)
    if marker["tree_fingerprint"] == tree and not verify_only:
        probe.close()
        evidence["outcome"] = "refused"
        evidence["reason"] = (
            "the marker already names this tree; there is nothing to re-attest. Run without "
            "--reattest, or with --verify-build to re-apply the chain to this cluster anyway."
        )
        return EXIT_MISMATCH, evidence

    if verify_only:
        print(
            f"  verify       applying the current tree in full to {verify_db} on this cluster; "
            f"{args.database} is read, never written, and the marker is never touched",
            flush=True,
        )
    else:
        print(
            f"  reattest     tree changed {marker['tree_fingerprint'].hex()[:16]} -> "
            f"{tree.hex()[:16]}; building {verify_db} to find out whether it matters",
            flush=True,
        )
    verify_args = argparse.Namespace(**vars(args))
    verify_args.database = verify_db
    verify_args.recreate = True
    verify_args.reattest = False
    verify_code, verify_evidence = build(verify_args)

    live_verify = (
        bytes.fromhex(verify_evidence.get("live_fingerprint", ""))
        if verify_code == EXIT_OK
        else b""
    )

    # The sound comparison, and the part that decides. Two conditions, and they answer two
    # different questions: has anybody touched the TARGET since it was built (raw fingerprint,
    # one database against itself), and does today's tree build the SAME SCHEMA (name-normalised
    # snapshot, two equal-length databases against each other).
    verify_snapshot: dict[str, list[str]] = {}
    differing_parts: list[dict[str, Any]] = []
    if verify_code == EXIT_OK:
        verify_conn = psycopg.connect(
            rewrite_dsn(args.dsn, database=verify_db, connect_timeout=args.connect_timeout),
            autocommit=True,
        )
        verify_snapshot = schema_snapshot(verify_conn, verify_db)
        verify_conn.close()
        for part in ("schemas", "types", "tables", "routines", "triggers"):
            mine, theirs = target_snapshot.get(part, []), verify_snapshot.get(part, [])
            if mine != theirs:
                only_target = [e.split("\n")[0][:120] for e in mine if e not in theirs]
                only_verify = [e.split("\n")[0][:120] for e in theirs if e not in mine]
                differing_parts.append(
                    {
                        "part": part,
                        "entries_target": len(mine),
                        "entries_verification": len(theirs),
                        "only_in_target": only_target[:10],
                        "only_in_verification_build": only_verify[:10],
                    }
                )

    target_unchanged = live_now == marker["live_fingerprint"]
    schema_equal = bool(verify_snapshot) and not differing_parts
    identical = target_unchanged and schema_equal

    report: dict[str, Any] = {
        "why": (
            (
                "Re-measurement on demand. The current tree was applied IN FULL to a separate "
                f"database on {cluster_label(args.dsn)}, so that 'the chain still applies to "
                "this cluster' is a number taken today rather than one copied out of an older "
                "file. The target database was read and never written; no marker moved."
            )
            if verify_only
            else (
                "The migration tree's text changed. Rather than drop a database judges are "
                "pointed at, the current tree was applied in full to a separate database on "
                "the same cluster and the two live schemas compared."
            )
        ),
        "how_the_comparison_is_made": (
            "NOT by comparing live fingerprints across databases — that can never succeed. "
            "CockroachDB renders fully-qualified names into SHOW CREATE, pg_get_functiondef and "
            "pg_get_triggerdef, so the fingerprint embeds the database name; and the SQL "
            "pretty-printer wraps on line width, so the name's LENGTH changes where a long JOIN "
            "clause breaks. Measured, by controlled experiment: identical DDL in databases named "
            "with 12 and 34 characters renders differently. So the verification database is given "
            "a name of exactly the same length, the name is replaced by a placeholder in every "
            "rendered definition, the five parts are sorted, and THOSE are compared."
        ),
        "verification_database": verify_db,
        "verification_database_name_length_matches": len(verify_db) == len(args.database),
        "tree_fingerprint_recorded": marker["tree_fingerprint"].hex(),
        "tree_fingerprint_now": tree.hex(),
        "live_fingerprint_recorded_by_marker": marker["live_fingerprint"].hex(),
        "live_fingerprint_of_target_now": live_now.hex(),
        "live_fingerprint_of_verification_build": live_verify.hex() if live_verify else None,
        "target_undrifted_since_it_was_built": target_unchanged,
        "normalised_snapshot_digest_target": snapshot_digest(target_snapshot),
        "normalised_snapshot_digest_verification": (
            snapshot_digest(verify_snapshot) if verify_snapshot else None
        ),
        "schema_entries_compared": sum(len(v) for v in target_snapshot.values()),
        "parts_that_differ": differing_parts,
        "current_tree_builds_this_exact_schema": schema_equal,
        "all_three_identical": identical,
        "chain": {
            "files": verify_evidence.get("files"),
            "applied": verify_evidence.get("applied"),
            "failed": verify_evidence.get("failed"),
            "files_that_needed_a_retry": verify_evidence.get("files_that_needed_a_retry"),
            "files_with_injected_retries": verify_evidence.get("files_with_injected_retries"),
            "connection_reconnects": verify_evidence.get("connection_reconnects"),
            "chain_seconds": verify_evidence.get("chain_seconds"),
            "bootstrap": verify_evidence.get("bootstrap"),
            "zone": verify_evidence.get("zone"),
            "retried_files": verify_evidence.get("retried_files"),
            "failures": verify_evidence.get("failures"),
            "failures_by_missing_object": verify_evidence.get("failures_by_missing_object"),
            "slowest": verify_evidence.get("slowest"),
            "verdict": verify_evidence.get("verdict"),
        },
    }
    if args.inject_40001:
        report["fault_injection"] = {
            "requested": args.inject_40001,
            "into": args.inject_into,
            "what_it_does": (
                "raises psycopg.errors.SerializationFailure (SQLSTATE 40001) on the first N "
                "attempts of the named migration BEFORE the statement reaches the server, so "
                "the cluster does no partial work and the recovery is the retry loop's alone"
            ),
            "files_with_injected_retries": verify_evidence.get("files_with_injected_retries"),
            "spontaneous_retries_this_run": verify_evidence.get("files_that_needed_a_retry"),
            "read_the_transcript_at": f"{report_key}.chain.retried_files",
            "not_a_cluster_event": (
                "These 40001s were raised by this program against a real migration on the real "
                "managed cluster. files_that_needed_a_retry counts only the ones the CLUSTER "
                "produced, and it is reported separately above."
            ),
        }
    evidence[report_key] = report

    if identical and verify_only:
        report["marker_updated"] = (
            "NOT TOUCHED, by design. --verify-build never writes trappoint.deploy_chain: it "
            "measures that the current tree still applies to this cluster and still builds "
            "this exact schema, and says so. Moving a marker is --reattest's job."
        )
        chain = report["chain"]
        evidence["verdict"] = (
            f"VERIFIED — {chain.get('applied')}/{chain.get('files')} applied, "
            f"{chain.get('failed')} failed, against {cluster_label(args.dsn)}, and the current "
            "tree builds this exact schema"
        )
        code = EXIT_OK
    elif identical:
        probe.execute(
            "UPDATE trappoint.deploy_chain SET tree_fingerprint = %s WHERE marker_id = %s",
            (tree, args.database),
        )
        report["marker_updated"] = (
            "trappoint.deploy_chain.tree_fingerprint now names the current tree. "
            "files / applied / failed / retried / applied_at were NOT touched: they record "
            "how this database was BUILT, and re-dating them would be a lie about a "
            "six-minute apply that did not happen to it."
        )
        evidence["verdict"] = "REATTESTED — the current tree builds this exact schema"
        code = EXIT_OK
    else:
        report["marker_updated"] = (
            "NO. The marker was left exactly as it was and nothing was changed."
        )
        stem = "NOT VERIFIED" if verify_only else "NOT REATTESTED"
        evidence["verdict"] = (
            f"{stem} — this database has drifted since it was built"
            if not target_unchanged
            else f"{stem} — the current tree does not build this schema"
        )
        code = EXIT_MISMATCH
    probe.close()

    # The verification database has served its purpose and is 271 tables of duplicate DDL on
    # a metered cluster. Dropped on both paths, including the refusal path, because a
    # diagnostic that leaves litter behind gets run once and then avoided.
    dropped: dict[str, Any] = {"database": verify_db}
    try:
        admin = psycopg.connect(
            rewrite_dsn(args.dsn, database="defaultdb", connect_timeout=args.connect_timeout),
            autocommit=True,
        )
        admin.execute(f'DROP DATABASE IF EXISTS "{verify_db}" CASCADE')
        admin.close()
        dropped["ok"] = True
    except psycopg.Error as exc:
        dropped["ok"] = False
        dropped["error"] = one_line(exc)
    report["verification_database_dropped"] = dropped
    evidence["total_seconds"] = round(time.time() - started, 1)
    return code, evidence


def probe_only(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    """``--retry-probe``: exercise the executor against the live cluster, change nothing.

    Deliberately NOT folded into the chain run. Proving the retry loop must not require
    dropping and re-applying 271 migrations against the demo database a judge may be
    reading at that moment; and a proof that costs six minutes is a proof nobody re-runs.
    This connects, confirms the database, runs three ``SELECT``-only cases and disconnects.
    """
    work_dsn = rewrite_dsn(
        args.dsn,
        database=args.database,
        connect_timeout=args.connect_timeout,
        application_name="mainline-deploy-retry-probe",
    )
    started = time.time()
    applier = Applier(work_dsn)
    observed = applier.database
    version_row = applier.conn.execute("SELECT version()").fetchone()

    evidence: dict[str, Any] = {
        "artefact": "MAINLINE cloud chain — 40001 retry probe",
        "generated_at_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "generated_by": "scripts/deploy/cloud_chain.py --retry-probe",
        "outcome": "retry_probe",
        "target": {
            "cluster": cluster_label(args.dsn),
            "database": args.database,
            "version": str(version_row[0]) if version_row else "unknown",
            "database_selection": database_report(args.dsn, args.database, observed),
        },
        "jitter_seed": args.jitter_seed if args.jitter_seed is not None else "os entropy",
    }
    if observed != args.database:
        applier.close()
        evidence["outcome"] = "refused"
        evidence["reason"] = (
            f"asked for database {args.database!r} and the server answered "
            f"current_database() = {observed!r}. The probe did not run."
        )
        return EXIT_MISMATCH, evidence

    print(f"  probe        database {observed} (SELECT current_database())", flush=True)
    proof = retry_probe(applier, injections=max(1, args.inject_40001 or 2))
    applier.close()
    evidence["retry_proof"] = proof
    evidence["total_seconds"] = round(time.time() - started, 1)
    evidence["verdict"] = proof["verdict"]
    for case in proof["cases"]:
        print(
            f"  {case['case']:<14} attempts={case['attempts']} "
            f"injected={case['injected_40001']} sqlstate={case['sqlstate']} "
            f"backoff={case['backoff_seconds']}s held={case['held']}",
            flush=True,
        )
    return (EXIT_OK if proof["verdict"] == "RETRY LOOP PROVEN" else EXIT_UNATTRIBUTED), evidence


def summarise(evidence: dict[str, Any]) -> None:
    target = evidence["target"]
    selection = target.get("database_selection", {})
    print()
    print(f"cluster       {target['cluster']}")
    print(f"version       {target.get('version', '?')}")
    if selection:
        print(
            f"database      {selection['confirmed_by_server']} "
            f"(SELECT current_database(); the DSN's path segment said "
            f"'{selection['dsn_path_segment']}' and was overridden)"
        )
    else:
        print(f"database      {target['database']}")
    if evidence["outcome"] == "retry_probe":
        proof = evidence.get("retry_proof", {})
        print("outcome       retry probe - nothing was applied and nothing was changed")
        print(f"max attempts  {proof.get('max_attempts')}")
        print(f"backoff       {proof.get('backoff')}")
        print(f"VERDICT       {evidence.get('verdict')}")
        return
    if evidence["outcome"] in {"reattested", "verified"}:
        verified = evidence["outcome"] == "verified"
        again = evidence["verification_build" if verified else "reattestation"]
        chain = again["chain"]
        print(
            f"outcome       {'full re-apply' if verified else 're-attestation'} via "
            f"{again['verification_database']}"
        )
        print(
            f"chain         {chain.get('applied')}/{chain.get('files')} applied, "
            f"{chain.get('failed')} failed, {chain.get('chain_seconds')}s"
        )
        print(f"tree was      {again['tree_fingerprint_recorded'][:32]}")
        print(f"tree now      {again['tree_fingerprint_now'][:32]}")
        print(f"undrifted     {again['target_undrifted_since_it_was_built']}  (raw fingerprint)")
        print(f"snapshot tgt  {again['normalised_snapshot_digest_target'][:32]}")
        print(f"snapshot vfy  {str(again['normalised_snapshot_digest_verification'])[:32]}")
        print(
            f"schema equal  {again['current_tree_builds_this_exact_schema']}  "
            f"({again['schema_entries_compared']} entries compared)"
        )
        for part in again["parts_that_differ"]:
            print(f"  differs     {part['part']}: {part['only_in_target'][:2]}")
        print(f"identical     {again['all_three_identical']}")
        for retried in chain.get("retried_files") or []:
            print(
                f"  retried     {retried['file']}  attempts={retried['attempts']} "
                f"injected_40001={retried['injected_40001']} "
                f"backoff={retried.get('backoff_seconds')}s "
                f"waits={retried.get('waits_seconds')}"
            )
        print(
            f"spontaneous   {chain.get('files_that_needed_a_retry')} file(s) hit a 40001 the "
            f"CLUSTER produced"
        )
        print(f"marker        {again['marker_updated']}")
        print(f"VERDICT       {evidence.get('verdict')}")
        return
    zone = evidence.get("zone", {})
    print(
        f"gc.ttlseconds {zone.get('observed', zone.get('requested'))} "
        f"(accepted={zone.get('accepted')})"
    )
    print(f"outcome       {evidence['outcome']}")
    if evidence["outcome"] == "refused":
        print(f"reason        {evidence['reason']}")
        return
    print(
        f"chain         {evidence.get('applied', 0)}/{evidence.get('files', 0)} applied, "
        f"{evidence.get('failed', 0)} failed"
    )
    print(f"retries       {evidence.get('files_that_needed_a_retry', 0)} file(s) needed one")
    print(f"wall clock    {evidence.get('total_seconds')}s")
    print(f"tree fp       {evidence.get('tree_fingerprint', '')[:32]}")
    print(f"live fp       {evidence.get('live_fingerprint', '')[:32]}")
    for missing, files in sorted(evidence.get("failures_by_missing_object", {}).items()):
        print(
            f"  - absent    {missing}  breaks {len(files)}: {', '.join(files[:4])}"
            + (" …" if len(files) > 4 else "")
        )
    if "verdict" in evidence:
        print(f"VERDICT       {evidence['verdict']}")


def write_evidence(path: Path, evidence: dict[str, Any]) -> None:
    """Write the evidence, WITHOUT letting a no-op run erase the record of the run that built it.

    The per-file timings, attempt counts and SQLSTATEs only exist on the run that actually applied
    the chain. A second run finds everything in order and has nothing to report — and if it simply
    overwrote the file, re-running the deploy (which is the whole point of it being idempotent)
    would delete the only measurement anyone has. So an ``unchanged`` outcome MERGES into the
    existing document as a ``rechecks`` entry, and the applied run's rows stay where they are.

    ``--retry-probe`` merges the same way, into ``retry_proof``. Both merges stamp
    ``last_verified_at_utc``, which is the answer to "when was this last true" — a different
    question from ``generated_at_utc``, which answers "when was the chain applied", and
    conflating the two would let a re-run silently re-date a six-minute apply it did not do.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    if evidence.get("outcome") in {
        "unchanged",
        "retry_probe",
        "reattested",
        "verified",
        "refused",
    } and (path.is_file()):
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            loaded = None
        prior: dict[str, Any] | None = loaded if isinstance(loaded, dict) else None
        if (
            prior is not None
            and prior.get("outcome") == "applied"
            and prior.get("target", {}).get("database") == evidence["target"]["database"]
        ):
            if evidence["outcome"] == "refused":
                # A REFUSAL MUST NEVER DELETE THE TRANSCRIPT IT REFUSED TO REPLACE. The 271
                # per-file rows exist only on the run that applied them; overwriting them
                # with a two-line "I declined to act" would make the drift detector the most
                # destructive code path in the program. It appends instead.
                refusals = prior.setdefault("refusals", [])
                if isinstance(refusals, list):
                    refusals.append(
                        {
                            "at_utc": evidence["generated_at_utc"],
                            "by": evidence["generated_by"],
                            "reason": evidence.get("reason"),
                            "tree_fingerprint_on_disk": evidence.get("tree_fingerprint"),
                            "database_selection": evidence["target"].get("database_selection"),
                        }
                    )
                    prior["last_verified_at_utc"] = evidence["generated_at_utc"]
                    evidence = prior
            elif evidence["outcome"] == "verified":
                # APPENDED, never overwritten, and never on top of `reattestation`. A
                # verification build and a re-attestation answer different questions — "does
                # the chain still apply to Cloud today" and "why did the tree fingerprint
                # move" — and the second one is the harder to reconstruct if it is lost.
                builds = prior.setdefault("verification_builds", [])
                if isinstance(builds, list):
                    entry = dict(evidence["verification_build"])
                    entry["at_utc"] = evidence["generated_at_utc"]
                    entry["verdict"] = evidence.get("verdict")
                    entry["total_seconds"] = evidence.get("total_seconds")
                    builds.append(entry)
                    prior["last_verified_at_utc"] = evidence["generated_at_utc"]
                    evidence = prior
            elif evidence["outcome"] == "reattested":
                again = dict(evidence["reattestation"])
                again["at_utc"] = evidence["generated_at_utc"]
                again["verdict"] = evidence.get("verdict")
                prior["reattestation"] = again
                if again.get("all_three_identical"):
                    prior.setdefault("tree_fingerprint_when_applied", prior.get("tree_fingerprint"))
                    prior["tree_fingerprint"] = evidence["tree_fingerprint"]
                prior["last_verified_at_utc"] = evidence["generated_at_utc"]
                evidence = prior
            elif evidence["outcome"] == "retry_probe":
                prior["retry_proof"] = {
                    "at_utc": evidence["generated_at_utc"],
                    "jitter_seed": evidence.get("jitter_seed"),
                    "database_selection": evidence["target"].get("database_selection"),
                    **evidence["retry_proof"],
                }
                prior["last_verified_at_utc"] = evidence["generated_at_utc"]
                evidence = prior
            elif prior.get("live_fingerprint") == evidence.get("live_fingerprint"):
                rechecks = prior.setdefault("rechecks", [])
                if isinstance(rechecks, list):
                    rechecks.append(
                        {
                            "at_utc": evidence["generated_at_utc"],
                            "outcome": "unchanged",
                            "seconds": evidence.get("total_seconds"),
                            "zone": evidence.get("zone"),
                            "database_selection": evidence["target"].get("database_selection"),
                            "tree_fingerprint": evidence.get("tree_fingerprint"),
                            "live_fingerprint": evidence.get("live_fingerprint"),
                            "note": (
                                "Re-ran the deploy against a database that already matched its "
                                "marker. No migration was applied and nothing changed."
                            ),
                        }
                    )
                    prior["last_verified_at_utc"] = evidence["generated_at_utc"]
                    evidence = prior
    path.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    path.with_suffix(path.suffix + ".license").write_text(
        "SPDX-FileCopyrightText: 2026 MAINLINE contributors\nSPDX-License-Identifier: CC-BY-4.0\n",
        encoding="utf-8",
    )


def load_dotenv(root: Path) -> None:
    """Read ``.env`` into the environment without overwriting anything already set.

    The Cloud DSN carries a password and lives in the repo-root ``.env``, which is not
    committed. Reading it here means no operator ever types the password on a command
    line, where it would land in shell history.
    """
    env_file = root / ".env"
    if not env_file.is_file():
        return
    for raw in env_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cloud_chain",
        description=(
            "Apply the MAINLINE migration chain to a CockroachDB database, idempotently, "
            "retrying 40001 and attributing every failure."
        ),
    )
    parser.add_argument("--dsn", default=None, help="admin DSN (default: COCKROACH_DSN from .env)")
    parser.add_argument("--database", default=DEFAULT_DATABASE, help="target database")
    parser.add_argument("--migrations", type=Path, default=None, help="migration tree")
    parser.add_argument("--out", type=Path, default=None, help="evidence path")
    parser.add_argument(
        "--recreate", action="store_true", help="DROP the database and build it again"
    )
    parser.add_argument("--gc-ttlseconds", type=int, default=DEFAULT_GC_TTLSECONDS)
    parser.add_argument("--connect-timeout", type=int, default=20)
    parser.add_argument(
        "--retry-probe",
        action="store_true",
        help="prove the 40001 loop against the live cluster; apply nothing",
    )
    parser.add_argument(
        "--reattest",
        action="store_true",
        help=(
            "the tree's TEXT changed but the schema may not have: apply the current tree to "
            "a separate database on the same cluster and, only if the two live schemas are "
            "identical, re-point the marker. Never drops the target database."
        ),
    )
    parser.add_argument(
        "--verify-build",
        action="store_true",
        help=(
            "apply the current tree IN FULL to a separate database on the same live cluster "
            "and compare the two schemas, without dropping the target and without ever "
            "writing its marker. Answers 'does this chain still apply to Cloud today'. "
            "Combine with --inject-40001 to make a real migration retry."
        ),
    )
    parser.add_argument(
        "--inject-40001",
        type=int,
        default=0,
        metavar="N",
        help=(
            "raise a simulated 40001 on the first N attempts of one statement, before it "
            "reaches the server (default 2 under --retry-probe)"
        ),
    )
    parser.add_argument(
        "--inject-into",
        default=None,
        metavar="SUBSTRING",
        help="only inject into the statement whose file name or text contains SUBSTRING",
    )
    parser.add_argument(
        "--jitter-seed",
        type=int,
        default=None,
        help="seed the backoff jitter so a published transcript is reproducible",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    root = repo_root()
    load_dotenv(root)
    args = build_parser().parse_args(argv)
    args.dsn = args.dsn or os.environ.get("COCKROACH_DSN")
    if not args.dsn:
        print(
            "cloud_chain: no DSN. Pass --dsn, or put COCKROACH_DSN in the repo-root .env.",
            file=sys.stderr,
        )
        return EXIT_USAGE
    out = args.out or (root / "evidence" / "deploy" / "cloud-chain.json")
    if args.jitter_seed is not None:
        _JITTER.seed(args.jitter_seed)

    try:
        if args.retry_probe:
            code, evidence = probe_only(args)
        elif args.reattest or args.verify_build:
            code, evidence = reattest(args)
        else:
            code, evidence = build(args)
    except psycopg.OperationalError as exc:
        # "there was no cluster" and "the chain did not apply" are different findings and
        # only one of them is about this repository. Keeping them apart is the whole
        # reason this exit code exists.
        print(f"cloud_chain: could not reach the cluster: {one_line(exc)}", file=sys.stderr)
        return EXIT_USAGE

    write_evidence(out, evidence)
    summarise(evidence)
    print(f"evidence      {out}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
