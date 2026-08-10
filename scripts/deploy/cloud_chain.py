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
1. **It retries ``40001``.**  The first attempt to build this database on Cloud died with

       TransactionRetryWithProtoRefreshError: TransactionRetryError:
       retry txn (RETRY_SERIALIZABLE - failed preemptive refresh)

   A single-node Docker cluster never produces that; a managed multi-node cluster does,
   and neither ``trappoint migrate up`` nor ``scripts/proof/gate_refusal.py`` retries.
   Every file here gets up to :data:`MAX_ATTEMPTS` attempts with a bounded linear-scaled
   backoff, a dropped connection is re-established rather than counted as a failure, and
   the report says **how many files needed a retry**, because insurance whose premium is
   never quoted is indistinguishable from superstition. On the run that produced
   ``evidence/deploy/lead/cloud-chain-20260810T110400Z.json`` the answer was zero — which
   is exactly why the number is published rather than the loop merely being present.

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

Usage::

    .venv/Scripts/python.exe scripts/deploy/cloud_chain.py                  # Cloud, from .env
    .venv/Scripts/python.exe scripts/deploy/cloud_chain.py --recreate       # drop and rebuild
    .venv/Scripts/python.exe scripts/deploy/cloud_chain.py \\
        --dsn postgresql://root@localhost:26257/defaultdb?sslmode=disable \\
        --database w_w2_cloud_database                                       # local rehearsal

Exit codes:

* ``0`` — the chain is applied and the database matches its marker. Includes the
  ``unchanged`` path and the "applied with attributed failures" path: an attributed
  failure is a *recorded gap*, not a deploy error, and the evidence names every one.
* ``1`` — at least one migration failed for a reason this program could not attribute.
* ``2`` — no DSN, no migration tree, or the cluster could not be reached.
* ``3`` — the database exists and does not match. Nothing was changed. ``--recreate``.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
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

#: Attempts per file. Six with the backoff below is 5.25 s of waiting in the worst case,
#: which is longer than any contention window observed on this cluster and short enough
#: that a file which is genuinely broken does not hold the deploy for a minute.
MAX_ATTEMPTS = 6

#: Backoff base. Attempt *n* waits ``BACKOFF_BASE * n`` seconds: 0.25, 0.50, 0.75, 1.00,
#: 1.25. Linear-scaled rather than doubling because ``RETRY_SERIALIZABLE`` on a DDL
#: statement clears on the next timestamp push, not after an exponentially long quiet
#: period, and a doubling schedule mostly buys sleep.
BACKOFF_BASE = 0.25

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


@dataclass(slots=True)
class Attempted:
    """One statement's outcome: what happened, how many tries, and how long."""

    seconds: float
    attempts: int
    sqlstate: str
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


class Applier:
    """An autocommit connection that retries ``40001`` and reconnects when dropped.

    Autocommit is not an optimisation. CockroachDB DDL inside a multi-statement
    transaction can fail at ``COMMIT`` even when every statement succeeded, so a shared
    transaction would let one late failure retroactively un-apply files this report had
    already called applied.
    """

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self.conn = psycopg.connect(dsn, autocommit=True)
        self.reconnects = 0

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

    def run(self, sql: str) -> Attempted:
        started = time.time()
        attempts = 0
        state = "00000"
        error: str | None = None
        while attempts < MAX_ATTEMPTS:
            attempts += 1
            try:
                self.conn.execute(sql)  # type: ignore[arg-type]
            except psycopg.OperationalError as exc:
                # The connection itself went away — a Cloud node drained, or the proxy
                # cut an idle session. That is not the file's fault and must not be
                # counted as one, so we rebuild the connection and try again.
                error, state = one_line(exc), sqlstate_of(exc)
                if attempts >= MAX_ATTEMPTS:
                    break
                try:
                    self._reconnect()
                except psycopg.Error as reconnect_exc:
                    error, state = one_line(reconnect_exc), sqlstate_of(reconnect_exc)
                    break
                time.sleep(BACKOFF_BASE * attempts * 2)
                continue
            except psycopg.Error as exc:
                error, state = one_line(exc), sqlstate_of(exc)
                if state != RETRYABLE or attempts >= MAX_ATTEMPTS:
                    break
                time.sleep(BACKOFF_BASE * attempts)
                continue
            else:
                error, state = None, "00000"
                break
        return Attempted(
            seconds=round(time.time() - started, 3),
            attempts=attempts,
            sqlstate=state,
            error=error,
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


@dataclass(slots=True)
class ChainRun:
    rows: list[dict[str, Any]] = field(default_factory=list)
    applied: int = 0
    failed: int = 0
    retried: int = 0
    reconnects: int = 0
    seconds: float = 0.0

    @property
    def unattributed(self) -> list[dict[str, Any]]:
        return [r for r in self.rows if r["error"] and r["attribution"]["kind"] == "unattributed"]


def apply_chain(applier: Applier, paths: list[Path], *, quiet: bool = False) -> ChainRun:
    run = ChainRun()
    started = time.time()
    for index, path in enumerate(paths, 1):
        outcome = applier.run(path.read_text(encoding="utf-8"))
        row: dict[str, Any] = {
            "file": path.name,
            "seconds": outcome.seconds,
            "attempts": outcome.attempts,
            "sqlstate": outcome.sqlstate,
            "error": outcome.error,
            "attribution": attribute(outcome.error) if outcome.error else {"kind": "applied"},
        }
        run.rows.append(row)
        if outcome.ok:
            run.applied += 1
            if outcome.attempts > 1:
                run.retried += 1
        else:
            run.failed += 1
        if not quiet and (index % 25 == 0 or not outcome.ok or outcome.attempts > 1):
            status = "OK" if outcome.ok else f"FAIL {outcome.sqlstate}"
            print(
                f"  [{index:>3}/{len(paths)}] {path.name:<44} {status:<12} "
                f"{outcome.seconds:>6.2f}s attempts={outcome.attempts}",
                flush=True,
            )
    run.seconds = round(time.time() - started, 1)
    run.reconnects = applier.reconnects
    return run


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
def build(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:  # noqa: PLR0915
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
    print(f"  chain        applying {len(paths)} migrations", flush=True)
    applier = Applier(work_dsn)
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
    evidence["connection_reconnects"] = run.reconnects
    evidence["chain_seconds"] = run.seconds
    evidence["total_seconds"] = round(time.time() - started, 1)
    evidence["slowest"] = sorted(run.rows, key=lambda r: -r["seconds"])[:15]
    evidence["retried_files"] = [
        {"file": r["file"], "attempts": r["attempts"]} for r in run.rows if r["attempts"] > 1
    ]
    evidence["failures"] = failures
    evidence["failures_by_missing_object"] = by_object
    evidence["rows"] = run.rows

    if run.unattributed:
        evidence["verdict"] = "UNATTRIBUTED FAILURES"
        return EXIT_UNATTRIBUTED, evidence
    evidence["verdict"] = "APPLIED" if run.failed == 0 else "APPLIED WITH ATTRIBUTED GAPS"
    return EXIT_OK, evidence


def summarise(evidence: dict[str, Any]) -> None:
    target = evidence["target"]
    print()
    print(f"cluster       {target['cluster']}")
    print(f"version       {target.get('version', '?')}")
    print(f"database      {target['database']}")
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
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    if evidence.get("outcome") == "unchanged" and path.is_file():
        try:
            prior = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            prior = None
        if (
            isinstance(prior, dict)
            and prior.get("outcome") == "applied"
            and prior.get("target", {}).get("database") == evidence["target"]["database"]
            and prior.get("live_fingerprint") == evidence.get("live_fingerprint")
        ):
            rechecks = prior.setdefault("rechecks", [])
            if isinstance(rechecks, list):
                rechecks.append(
                    {
                        "at_utc": evidence["generated_at_utc"],
                        "outcome": "unchanged",
                        "seconds": evidence.get("total_seconds"),
                        "zone": evidence.get("zone"),
                        "tree_fingerprint": evidence.get("tree_fingerprint"),
                        "live_fingerprint": evidence.get("live_fingerprint"),
                        "note": (
                            "Re-ran the deploy against a database that already matched its "
                            "marker. No migration was applied and nothing changed."
                        ),
                    }
                )
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

    try:
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
