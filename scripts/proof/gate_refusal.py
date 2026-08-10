#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""THE PROOF: the database refuses a permit merge, and says exactly why.

This script is the product's central claim reduced to something a skeptic can run.
It builds a throwaway database, applies the whole migration tree into it, seeds the
smallest history in which the claim is decidable — a clause, an incident that wrote
it, a recalled precursor that arrived after the permit was drafted, and a permit
whose merge depends on that precursor — and then asks the database to merge.

It captures THREE outcomes, and all three are load-bearing:

1. **The refusal.**  One open obligation, no signed disposition.  The exhibit is
   ``23514`` on ``gate_closed_when_issued`` (conformance case CF-01).
2. **The drift refusal.**  The projected counter is forced to zero out of band, the
   way a bad ``UPDATE`` or a disarmed projector would leave it.  The gate re-derives
   the open count from the base tables, disagrees with the counter, and refuses with
   ``P0001`` naming ``mainline.fn_permit_merge_gate`` (conformance case CF-03).
   This is the case no ``CHECK`` can hold, and it is why P-2 says a projection is
   *enforced, never trusted*.
3. **The admission.**  A disposition is signed against the obligation, the projection
   trigger closes the counter, and the same merge SUCCEEDS.

The third is not decoration.  **A gate that always refuses is a broken gate, not a
safe one**, and a proof that only shows a refusal has not distinguished the two.

AND BEFORE ALL THREE: WHO DID THE WORK
--------------------------------------
A refusal is only as good as the projection it refused against, so the run opens by
measuring the projection itself rather than assuming it.  ``mainline.permit`` is read
IMMEDIATELY BEFORE and IMMEDIATELY AFTER the single ``INSERT INTO
mainline.blocking_check``, and ``mainline_ops.outbox`` is read back for the row the
trigger emitted.  Every clause of the sentence

    *the trigger projected the counter, emitted the CDC signal, bumped the epoch,
    and the gate refused*

is therefore a value in :data:`~evidence` ``projection`` — ``open_blocking`` 0 → 1,
``gate_epoch`` 0 → 1, one ``mainline_ops.outbox`` row whose ``kind`` is
``check_opened`` and whose ``subject_id`` is the ``check_id`` — and each is an
ASSERTION that can turn the verdict red, not a field that is merely populated.  If
the trigger is absent, if the outbox row is missing, or if the epoch did not move,
the verdict is ``NOT PROVEN`` and ``projection.assertions`` says which clause failed.

The ``max_severity`` on that row is the sharpest of them.  This script inserts the
blocking check with ``severity = 0``; ``fn_check_project`` (BEFORE INSERT, 0120)
overwrites it from ``clause_blame_current``; ``fn_check_materialised`` (AFTER INSERT,
0121) then copies ``(NEW).severity`` into the outbox row.  A signal carrying ``4``
where the client wrote ``0`` is the projection ordering demonstrated, not asserted.

WHAT THIS SCRIPT WILL NOT DO
----------------------------
It will not create a table that has no migration, and for most of this repository's
life that refusal had a visible cost.  Five tables had consumers and no producer —
``mainline_ops.outbox``, ``mainline.identity_assignment``, ``mainline.patrol_run``,
``mainline_meas.agent_action``, ``mainline_meas.standing`` — fifteen consumer
migrations failed because of them, and this script RECORDED each failure with its
file name and SQLSTATE rather than inventing a number the allocation table had not
granted.  A recorded gap is a finding; an invented table is a lie about what the
schema is.

**They were authored on 2026-08-10 by the producer-completion wave**, in the numbers
four already-committed artefacts had fixed for them (each consumer's ``requires:``
header, ``GRANTS.yaml``'s ``since:``, ARCHITECTURE.md §18, ``RLS-MATRIX.yaml``):
``0049d`` ``identity_assignment`` · ``0089`` ``agent_action`` · ``0090``
``patrol_run`` · ``0099`` ``outbox``, plus two gaps no census could see because
CockroachDB names only the FIRST absent relation in a statement — ``0089a``
``person_measure_policy`` (shadowed by ``standing`` in both views that join it) and
``0099a`` ``site_register_signal`` (named only by an RLS negative assertion) — and
three append-only welds at ``0145f`` / ``0149a`` / ``0149b``.  ``mainline_ops.outbox``
deliberately gets NO weld: it is the one row-level-TTL table in ``mainline_ops``, and
a ``BEFORE DELETE`` refusal would make the TTL job fail forever.

:data:`UNPRODUCED_TABLES` is therefore now empty, and that is a RATCHET rather than
tidiness: :func:`apply_chain` classifies a failure as *explained* only when it is
attributable to a listed table, so an empty tuple turns any residual failure into
``chain.failures_unexplained``, which is a hard NOT PROVEN.

It also does not stop at the first failing migration.  ``trappoint migrate up`` is
forward-only and halts on the first refusal — correct for a deployment, useless for a
census — so the chain is applied here file by file, each in its own transaction,
CONTINUING past a failure so that the report names every one.

``trappoint migrate bootstrap`` IS run first, and that is not optional: kernel ruling
D6 puts the ``trappoint`` bookkeeping schema OUTSIDE the numbered sequence, and
``0119a_fn_explain_refusal.sql`` needs that schema to exist.  Applying the raw files
without bootstrapping makes 0119a fail for a reason that is not a defect.

Usage::

    python scripts/proof/gate_refusal.py \\
        --dsn postgresql://root@localhost:26257/defaultdb?sslmode=disable

Exit codes:

* ``0`` — the claim is proven: the chain applied in full, the projection was performed
  by the trigger and read back from ``mainline_ops.outbox``, both refusals were
  captured with the SQLSTATE and exhibit the conformance manifest fixes, and the
  admission succeeded.
* ``1`` — the claim is NOT proven.  The evidence file is still written, and it says
  which half failed.  **Publish it.**
* ``2`` — the invocation was wrong, or there was no database to talk to.  Distinct
  from 1 so that "there was no cluster" is never read as "the gate did not refuse".
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import re
import subprocess
import sys
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import psycopg
from psycopg.types.json import Jsonb

EXIT_PROVEN = 0
EXIT_NOT_PROVEN = 1
EXIT_USAGE = 2

# ─────────────────────────────────────────────────────────────────────────────────────
# THE ENUMERATED GAPS — NOW EMPTY, AND THAT IS THE RATCHET
#
# This tuple used to name five tables with consumers and no producer. A migration that
# failed because one of them was absent was CLASSIFIED rather than merely counted, so
# that the day a producer landed, the list would shrink in a reviewable diff instead of
# a failure quietly changing category.
#
# That day was 2026-08-10. Seven producers were authored — the five below plus
# `mainline_meas.person_measure_policy` and `mainline_ops.site_register_signal`, which
# no SQLSTATE census could see because CockroachDB names only the first absent relation
# in a statement — and the list is now empty:
#
#     mainline_ops.outbox            -> 0099_outbox.sql
#     mainline.identity_assignment   -> 0049d_identity_assignment.sql
#     mainline.patrol_run            -> 0090_patrol_run.sql
#     mainline_meas.agent_action     -> 0089_agent_action.sql
#     mainline_meas.standing         -> 0089b_standing.sql
#
# An EMPTY tuple is strictly stronger than a populated one. `_classify` can no longer
# return "unproduced_dependency" for anything, so every residual failure lands in
# `chain.failures_unexplained`, and a non-empty `failures_unexplained` is a hard NOT
# PROVEN. The tolerance this proof used to extend to fifteen known-bad files is gone;
# nothing is forgiven any more.
#
# If a future tree acquires a genuine gap, the honest move is unchanged: record it here
# so the failure is named, never create the table from this script. A new table takes a
# number from a band whose owner and mode match in
# verticals/mainline/db/migrations.allocation.toml, and this worker owns no band.
# ─────────────────────────────────────────────────────────────────────────────────────
UNPRODUCED_TABLES: tuple[str, ...] = ()

#: The gate objects. If any of these is absent the proof is not merely red, it is
#: unanswerable, and saying so is different from saying the gate admitted the merge.
GATE_OBJECTS: tuple[tuple[str, str, str], ...] = (
    ("table", "mainline", "permit"),
    ("table", "mainline", "blocking_check"),
    ("table", "mainline", "disposition"),
    ("table", "mainline", "merge_record"),
    ("table", "mainline", "refusal_ledger"),
    ("routine", "mainline", "fn_permit_merge_gate"),
    ("routine", "mainline", "merge_permit"),
    ("trigger", "mainline.permit", "permit_merge_gate"),
)

#: `spec/conformance/manifest.toml`, group 1. These two rows are what this script is
#: for; every other case belongs to `trappoint-conform`.
CF01_SQLSTATE, CF01_EXHIBIT = "23514", "gate_closed_when_issued"
CF03_SQLSTATE, CF03_EXHIBIT = "P0001", "mainline.fn_permit_merge_gate"

#: The projection under test. `0121_trg_check_materialised.sql` welds
#: `mainline.fn_check_materialised` (0101) to `mainline.blocking_check` AFTER INSERT;
#: the function bumps two counters on the gated subject and emits ONE row into the
#: deployment's single CDC-query source. Each name here is read back from the live
#: catalogue or the live row, never assumed.
PROJECTION_TRIGGER = "check_materialised"
PROJECTION_TABLE_SCHEMA, PROJECTION_TABLE_NAME = "mainline", "blocking_check"
PROJECTION_FUNCTION = "mainline.fn_check_materialised"
COUNTER_SOURCE_TRIGGER = f"trigger {PROJECTION_TRIGGER} -> {PROJECTION_FUNCTION}"
OUTBOX_SCHEMA, OUTBOX_TABLE = "mainline_ops", "outbox"
OUTBOX_KIND = "check_opened"

#: The client writes this severity into `mainline.blocking_check`; `fn_check_project`
#: (BEFORE INSERT, 0120) overwrites it from `clause_blame_current` before
#: `fn_check_materialised` (AFTER INSERT, 0121) copies it into the outbox row. An
#: emitted `max_severity` that still reads this value would mean the BEFORE trigger did
#: not run, which is a different defect from the AFTER trigger not running.
CLIENT_SUPPLIED_SEVERITY = 0

#: `spec/errors.md` §3.1: `diag.constraint_name` is empty for P0001, so the exhibit is
#: recovered from the message the raising body wrote. Recorded as `parsed` rather than
#: `reported`, because a parsed exhibit is a weaker diagnosis and the refusal ledger's
#: own CHECK (`refusal_p0001_exhibit_is_parsed`) insists the difference be stated.
_REFUSED_BY = re.compile(r"refused by ([A-Za-z_][A-Za-z0-9_.]*)")

_ZERO32 = b"\x00" * 32


# ═════════════════════════════════════════════════════════════════════════════════════
# small helpers
# ═════════════════════════════════════════════════════════════════════════════════════


def _now_utc() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _sha(*parts: bytes | str) -> bytes:
    digest = hashlib.sha256()
    for part in parts:
        digest.update(part.encode("utf-8") if isinstance(part, str) else part)
    return digest.digest()


def _jcs(payload: dict[str, Any]) -> bytes:
    """A canonical serialisation of *payload*: sorted keys, no insignificant whitespace.

    RFC 8785 for the ASCII, integer and string values this script actually uses. It is
    NOT a general JCS implementation and does not claim to be — `spec/custody` names
    `trappoint_jcs` as the authority, and the procedure takes these bytes from the
    CLIENT precisely so that a third party can recompute them without this cluster.
    """
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def _repo_root(start: Path | None = None) -> Path:
    """The workspace root: the nearest ancestor holding both `spec/` and `compose.yaml`."""
    here = (start or Path(__file__).resolve().parent).resolve()
    for candidate in (here, *here.parents):
        if (candidate / "spec").is_dir() and (candidate / "compose.yaml").is_file():
            return candidate
    return Path.cwd().resolve()


def _rewrite_dsn(
    dsn: str, *, database: str | None = None, connect_timeout: int | None = None
) -> str:
    """Return *dsn* with the database swapped and a ``connect_timeout`` guaranteed.

    The timeout is not a nicety. ``docs/leads/quality-repair.md`` §1.4 records a full-suite
    run that HUNG rather than failed because its fixtures connected without one, and this
    script hits the same edge from the other direction: on a host where ``localhost``
    resolves to ``::1`` before ``127.0.0.1`` and nothing is listening on the v6 address,
    libpq waits out the operating system's TCP timeout — measured at **130 seconds per
    connection** on the machine this proof was developed on. ``connect_timeout`` is applied
    by libpq PER ADDRESS, so setting it makes the dead address family cost a few seconds and
    then fall through to the live one. An explicit value in the DSN always wins.
    """
    parts = urlsplit(dsn)
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)]
    if connect_timeout is not None and not any(k == "connect_timeout" for k, _ in query):
        query.append(("connect_timeout", str(connect_timeout)))
    path = f"/{database}" if database is not None else parts.path
    return urlunsplit((parts.scheme, parts.netloc, path, urlencode(query), parts.fragment))


def _sqlstate(exc: psycopg.Error) -> str:
    state = exc.sqlstate
    if state:
        return state
    diag = getattr(exc, "diag", None)
    return (diag.sqlstate if diag is not None else None) or "no-sqlstate"


def _constraint(exc: psycopg.Error) -> tuple[str, str]:
    """Return ``(exhibit, source)`` — the constraint name and how it was obtained."""
    diag = getattr(exc, "diag", None)
    reported = (diag.constraint_name if diag is not None else None) or ""
    if reported:
        return reported, "reported"
    match = _REFUSED_BY.search(str(exc))
    if match is not None:
        return match.group(1), "parsed"
    return "", "absent"


def _message(exc: BaseException) -> str:
    return " ".join(str(exc).split())


# ═════════════════════════════════════════════════════════════════════════════════════
# the chain
# ═════════════════════════════════════════════════════════════════════════════════════


@dataclass(slots=True)
class MigrationFailure:
    version: str
    sqlstate: str
    message: str
    classification: str
    unproduced_table: str | None = None

    def as_json(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "sqlstate": self.sqlstate,
            "message": self.message,
            "classification": self.classification,
            "unproduced_table": self.unproduced_table,
        }


@dataclass(slots=True)
class ChainReport:
    migrations_dir: str
    files: int = 0
    applied: list[str] = field(default_factory=list)
    failures: list[MigrationFailure] = field(default_factory=list)
    bootstrap: dict[str, Any] = field(default_factory=dict)
    seconds: float = 0.0

    @property
    def unexplained(self) -> list[MigrationFailure]:
        return [f for f in self.failures if f.classification == "unexplained"]

    def as_json(self) -> dict[str, Any]:
        return {
            "migrations_dir": self.migrations_dir,
            "files": self.files,
            "applied_count": len(self.applied),
            "failed_count": len(self.failures),
            "seconds": round(self.seconds, 3),
            "bootstrap": self.bootstrap,
            "reached_0115_fn_permit_merge_gate": "0115_fn_permit_merge_gate" in self.applied,
            "unproduced_tables_enumerated": list(UNPRODUCED_TABLES),
            "failures_attributable_to_an_unproduced_table": [
                f.as_json() for f in self.failures if f.classification == "unproduced_dependency"
            ],
            "failures_unexplained": [f.as_json() for f in self.unexplained],
        }


def _discover(migrations: Path) -> list[Path]:
    """Every migration under *migrations*, in ALLOCATION ORDER.

    Allocation order is lexicographic on the whole filename stem, which is what makes
    ``(49, "z") < (50, "")`` — the fact that put one syntax error between this
    repository and its central claim. ``trappoint_migrate.discovery`` is the authority
    and is used when it imports; the fallback is the same rule, so a machine with no
    workspace installed still gets the same sequence.
    """
    try:
        from trappoint_migrate.discovery import discover

        return [m.path for m in discover(migrations)]
    except ImportError:
        return sorted(
            (p for p in migrations.iterdir() if p.is_file() and p.name.endswith(".sql")),
            key=lambda p: p.name[: -len(".sql")],
        )


def _classify(message: str) -> tuple[str, str | None]:
    """Attribute a migration failure to an enumerated gap, or call it unexplained.

    With :data:`UNPRODUCED_TABLES` empty the loop below cannot match, so every failure
    is now ``unexplained`` and therefore fatal. The loop is kept rather than deleted
    because the mechanism is the point: the day a real gap has to be recorded again,
    naming it in one tuple restores the classification without touching this function.
    """
    lowered = message.lower()
    for table in UNPRODUCED_TABLES:
        schema, _, name = table.partition(".")
        if table.lower() in lowered or (schema in lowered and f'"{name}"' in lowered):
            return "unproduced_dependency", table
    return "unexplained", None


def _bootstrap(dsn: str, repo_root: Path) -> dict[str, Any]:
    """Run ``trappoint migrate bootstrap`` against *dsn*.

    The subprocess is tried first because the brief names the command, and the command
    is the supported entry point. The in-process fallback exists for an environment
    where the console script is not on PATH; it calls the same function the CLI calls,
    so the two cannot diverge.
    """
    argv = [sys.executable, "-m", "trappoint_migrate", "bootstrap", "--dsn", dsn]
    try:
        completed = subprocess.run(  # fixed argv, no shell
            argv,
            capture_output=True,
            text=True,
            cwd=str(repo_root),
            timeout=180,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        completed = None
        launch_error: str | None = _message(exc)
    else:
        launch_error = None

    if completed is not None and completed.returncode == 0:
        return {
            "how": "trappoint migrate bootstrap (subprocess)",
            "argv": ["python", "-m", "trappoint_migrate", "bootstrap", "--dsn", "<dsn>"],
            "stdout": completed.stdout.strip(),
            "ok": True,
        }

    fallback_note = (
        launch_error
        if launch_error is not None
        else f"exit {completed.returncode}: {(completed.stderr or '').strip()}"
        if completed is not None
        else "unknown"
    )
    from trappoint_migrate.bootstrap import bootstrap as bootstrap_fn
    from trappoint_migrate.runner import DEFAULT_SCHEMA_PREFIXES, actor

    with psycopg.connect(dsn, autocommit=True) as conn:
        ensured = bootstrap_fn(conn, applied_by=actor(), schema_prefixes=DEFAULT_SCHEMA_PREFIXES)
    return {
        "how": "trappoint_migrate.bootstrap.bootstrap (in-process fallback)",
        "subprocess_note": fallback_note,
        "ensured": list(ensured),
        "ok": True,
    }


def apply_chain(
    conn: psycopg.Connection[Any], dsn: str, migrations: Path, repo_root: Path
) -> ChainReport:
    """Bootstrap, then apply every migration in allocation order, continuing past failures.

    *conn* must be in autocommit, which is what puts each file in a transaction of its own:
    CockroachDB DDL inside a multi-statement transaction can fail at COMMIT even when every
    statement succeeded, so a shared transaction would make one late failure retroactively
    un-apply files this report had already called applied.
    """
    report = ChainReport(migrations_dir=str(migrations))
    started = datetime.now(UTC)
    report.bootstrap = _bootstrap(dsn, repo_root)

    paths = _discover(migrations)
    report.files = len(paths)
    for path in paths:
        version = path.name[: -len(".sql")]
        sql = path.read_text(encoding="utf-8")
        try:
            conn.execute(sql)  # type: ignore[arg-type]
        except psycopg.Error as exc:
            message = _message(exc)
            classification, table = _classify(message)
            report.failures.append(
                MigrationFailure(
                    version=version,
                    sqlstate=_sqlstate(exc),
                    message=message,
                    classification=classification,
                    unproduced_table=table,
                )
            )
        else:
            report.applied.append(version)
    report.seconds = (datetime.now(UTC) - started).total_seconds()
    return report


def inspect_gate_objects(conn: psycopg.Connection[Any]) -> dict[str, bool]:
    """Which gate objects exist. Asked of the catalogue, not of the file tree."""
    present: dict[str, bool] = {}
    for kind, owner, name in GATE_OBJECTS:
        if kind == "table":
            row = conn.execute(
                "SELECT count(*) FROM information_schema.tables "
                "WHERE table_schema = %s AND table_name = %s",
                (owner, name),
            ).fetchone()
        elif kind == "routine":
            row = conn.execute(
                "SELECT count(*) FROM information_schema.routines "
                "WHERE routine_schema = %s AND routine_name = %s",
                (owner, name),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT count(*) FROM information_schema.triggers "
                "WHERE event_object_schema = %s AND event_object_table = %s "
                "AND trigger_name = %s",
                (*owner.split("."), name),
            ).fetchone()
        label = f"trigger:{owner}:{name}" if kind == "trigger" else f"{kind}:{owner}.{name}"
        present[label] = bool(row and row[0])
    return present


# ═════════════════════════════════════════════════════════════════════════════════════
# the history
# ═════════════════════════════════════════════════════════════════════════════════════


@dataclass(slots=True)
class History:
    """Every identifier the seeded history minted, so the evidence names its own subject."""

    site_id: uuid.UUID
    site_code: str
    signer_sub: str
    countersigner_sub: str
    commit_id: bytes
    clause_uuid: uuid.UUID
    event_id: uuid.UUID
    permit_id: uuid.UUID
    check_id: uuid.UUID
    receipt_id: uuid.UUID
    recall_run_id: uuid.UUID
    merged_commit: bytes
    counter_source: str
    projection_trigger_present: bool
    #: What the trigger did, measured on both sides of the one INSERT that fires it.
    #: Built by :func:`_capture_projection` and published as the top-level ``projection``
    #: block by :func:`evaluate_projection`; deliberately NOT folded into
    #: :meth:`as_json`, because a claim that can fail the verdict belongs at the top
    #: level of the evidence rather than inside a bag of identifiers.
    projection: dict[str, Any] = field(default_factory=dict)

    def as_json(self) -> dict[str, Any]:
        return {
            "site_id": str(self.site_id),
            "site_code": self.site_code,
            "signer_sub": self.signer_sub,
            "countersigner_sub": self.countersigner_sub,
            "clause_version_commit": self.commit_id.hex(),
            "clause_uuid": str(self.clause_uuid),
            "precursor_event_id": str(self.event_id),
            "permit_id": str(self.permit_id),
            "blocking_check_id": str(self.check_id),
            "exposure_receipt_id": str(self.receipt_id),
            "recall_run_id": str(self.recall_run_id),
            "merged_commit": self.merged_commit.hex(),
            "open_blocking_counter_written_by": self.counter_source,
            "projection_trigger_check_materialised_present": self.projection_trigger_present,
        }


# ─────────────────────────────────────────────────────────────────────────────────────
# THE PROJECTION, MEASURED
#
# Every read below is deliberately narrow and deliberately guarded. The seed runs inside
# ONE SERIALIZABLE transaction, and on CockroachDB an error inside a transaction poisons
# it — so a `SELECT` against a table that might not exist would take the whole seed down
# and report the absence of a table as "the history could not be seeded". Existence is
# therefore asked of `information_schema` first, which cannot fail, and the table is read
# only once it is known to be there.
# ─────────────────────────────────────────────────────────────────────────────────────


def _relation_present(conn: psycopg.Connection[Any], schema: str, name: str) -> bool:
    row = conn.execute(
        "SELECT count(*) FROM information_schema.tables "
        "WHERE table_schema = %s AND table_name = %s",
        (schema, name),
    ).fetchone()
    return bool(row and row[0])


def _trigger_present(conn: psycopg.Connection[Any], schema: str, table: str, name: str) -> bool:
    row = conn.execute(
        "SELECT count(*) FROM information_schema.triggers "
        "WHERE event_object_schema = %s AND event_object_table = %s AND trigger_name = %s",
        (schema, table, name),
    ).fetchone()
    return bool(row and row[0])


def _permit_counters(conn: psycopg.Connection[Any], permit_id: uuid.UUID) -> dict[str, int | None]:
    """``open_blocking`` and ``gate_epoch`` as they stand right now.

    Called twice — immediately before and immediately after the single INSERT into
    ``mainline.blocking_check`` — with nothing in between. The gap between the two
    readings contains exactly one statement, so whatever moved was moved by the weld on
    that statement and by nothing else.
    """
    row = conn.execute(
        "SELECT open_blocking, gate_epoch FROM mainline.permit WHERE permit_id = %s",
        (permit_id,),
    ).fetchone()
    if row is None:
        return {"open_blocking": None, "gate_epoch": None}
    return {"open_blocking": int(row[0]), "gate_epoch": int(row[1])}


def _capture_projection(
    conn: psycopg.Connection[Any],
    permit_id: uuid.UUID,
    check_id: uuid.UUID,
    site_id: uuid.UUID,
    before: dict[str, int | None],
    after: dict[str, int | None],
    *,
    trigger_present: bool,
) -> dict[str, Any]:
    """Read back the evidence that ``fn_check_materialised`` did the work.

    Three artefacts, from three different places: the counters on the gated subject, the
    severity the BEFORE trigger projected onto the obligation row, and the row the AFTER
    trigger emitted into the one CDC-query source in the deployment. None of them is
    supplied by this script; all three are read out of the database after the fact.
    """
    projected = conn.execute(
        "SELECT severity, virulence::STRING, closure_gen FROM mainline.blocking_check "
        "WHERE check_id = %s",
        (check_id,),
    ).fetchone()

    outbox_present = _relation_present(conn, OUTBOX_SCHEMA, OUTBOX_TABLE)
    rows: list[dict[str, Any]] = []
    total = None
    if outbox_present:
        total_row = conn.execute("SELECT count(*) FROM mainline_ops.outbox").fetchone()
        total = int(total_row[0]) if total_row else None
        for emitted in conn.execute(
            "SELECT signal_id, kind, subject_id, site_id, target_site, activity_root, "
            # NUMERIC comes back as Decimal, which json.dumps will not serialise; the
            # cast keeps the evidence file writable without rounding the value.
            "max_severity, score::STRING, payload, emitted_at, expires_at "
            "FROM mainline_ops.outbox WHERE subject_id = %s ORDER BY emitted_at",
            (check_id,),
        ).fetchall():
            rows.append(
                {
                    "signal_id": str(emitted[0]),
                    "kind": emitted[1],
                    "subject_id": str(emitted[2]),
                    "site_id": str(emitted[3]),
                    "target_site": None if emitted[4] is None else str(emitted[4]),
                    "activity_root": emitted[5],
                    "max_severity": int(emitted[6]),
                    "score": emitted[7],
                    "payload": emitted[8],
                    "emitted_at": emitted[9].astimezone(UTC).isoformat(),
                    "expires_at": emitted[10].astimezone(UTC).isoformat(),
                }
            )

    return {
        "claim": (
            "the trigger projected the counter, emitted the CDC signal, bumped the epoch, "
            "and the gate refused"
        ),
        "trigger": {
            "name": PROJECTION_TRIGGER,
            "timing": "AFTER INSERT",
            "on": f"{PROJECTION_TABLE_SCHEMA}.{PROJECTION_TABLE_NAME}",
            "function": PROJECTION_FUNCTION,
            "migration": "0121_trg_check_materialised.sql",
            "present": trigger_present,
        },
        "subject": {
            "permit_id": str(permit_id),
            "check_id": str(check_id),
            "site_id": str(site_id),
        },
        "fired_by": (
            "one INSERT INTO mainline.blocking_check, with no other statement between the "
            "before and after readings"
        ),
        "open_blocking": {
            "before": before["open_blocking"],
            "after": after["open_blocking"],
            "expected_after": 1,
        },
        "gate_epoch": {
            "before": before["gate_epoch"],
            "after": after["gate_epoch"],
            "moved": (
                after["gate_epoch"] is not None
                and before["gate_epoch"] is not None
                and after["gate_epoch"] > before["gate_epoch"]
            ),
        },
        "severity": {
            "supplied_by_this_script": CLIENT_SUPPLIED_SEVERITY,
            "projected_onto_the_check": None if projected is None else int(projected[0]),
            "virulence_projected": None if projected is None else projected[1],
            "closure_gen_projected": None if projected is None else int(projected[2]),
        },
        "outbox": {
            "relation": f"{OUTBOX_SCHEMA}.{OUTBOX_TABLE}",
            "relation_present": outbox_present,
            "rows_in_table": total,
            "rows_for_this_check": len(rows),
            "expected_kind": OUTBOX_KIND,
            "row": rows[0] if rows else None,
            "all_rows_for_this_check": rows,
        },
    }


def evaluate_projection(history: History) -> tuple[dict[str, Any], list[str]]:
    """Turn the captured projection into ASSERTIONS, and say which ones failed.

    The distinction the brief insists on, and the reason this function exists rather than
    the block simply being written into the evidence: a populated field proves nothing,
    because nobody reads it. An assertion that can turn the verdict red is read by the
    exit code. Every clause of the sentence in ``projection.claim`` is one row here.
    """
    block = dict(history.projection)
    if not block:
        return (
            {
                "captured": False,
                "why": "the history was not seeded, so there was no INSERT to measure",
                "assertions": [],
            },
            ["projection: nothing was measured — the history was not seeded"],
        )

    outbox = block["outbox"]
    row = outbox["row"] or {}
    open_before, open_after = block["open_blocking"]["before"], block["open_blocking"]["after"]
    epoch_before, epoch_after = block["gate_epoch"]["before"], block["gate_epoch"]["after"]

    checks: list[tuple[str, str, bool, str]] = [
        (
            "trigger_present",
            (
                f"the {PROJECTION_TRIGGER} trigger is welded to "
                f"{PROJECTION_TABLE_SCHEMA}.{PROJECTION_TABLE_NAME}"
            ),
            bool(block["trigger"]["present"]),
            f"present={block['trigger']['present']}",
        ),
        (
            "counter_source_is_the_trigger",
            "open_blocking was written by the trigger, not by this script",
            history.counter_source == COUNTER_SOURCE_TRIGGER,
            history.counter_source,
        ),
        (
            "open_blocking_projected",
            "the trigger raised open_blocking from 0 to 1 across the one INSERT",
            open_before == 0 and open_after == 1,
            f"{open_before} -> {open_after}",
        ),
        (
            "gate_epoch_strictly_increased",
            "the trigger bumped gate_epoch, pinning the subject to a new (id, epoch) pair",
            epoch_before is not None and epoch_after is not None and epoch_after > epoch_before,
            f"{epoch_before} -> {epoch_after}",
        ),
        (
            "outbox_relation_present",
            f"{OUTBOX_SCHEMA}.{OUTBOX_TABLE} exists — 0099_outbox.sql applied",
            bool(outbox["relation_present"]),
            f"present={outbox['relation_present']}",
        ),
        (
            "outbox_row_emitted",
            "exactly one CDC signal was emitted for this obligation",
            outbox["rows_for_this_check"] == 1,
            f"rows_for_this_check={outbox['rows_for_this_check']}",
        ),
        (
            "outbox_kind_is_check_opened",
            f"the emitted signal's kind is {OUTBOX_KIND!r}",
            row.get("kind") == OUTBOX_KIND,
            repr(row.get("kind")),
        ),
        (
            "outbox_subject_is_the_check",
            "the emitted signal's subject_id is the blocking check's id",
            row.get("subject_id") == str(history.check_id),
            f"{row.get('subject_id')} vs check_id {history.check_id}",
        ),
        (
            "outbox_site_is_the_seeded_site",
            "the emitted signal carries the site denormalised, as a CDC query needs",
            row.get("site_id") == str(history.site_id),
            f"{row.get('site_id')} vs site_id {history.site_id}",
        ),
        (
            "outbox_max_severity_is_the_projected_severity",
            (
                "the signal carries the severity the BEFORE trigger projected, not the "
                "severity this script supplied"
            ),
            row.get("max_severity") is not None
            and row.get("max_severity") == block["severity"]["projected_onto_the_check"]
            and row.get("max_severity") != CLIENT_SUPPLIED_SEVERITY,
            (
                f"emitted={row.get('max_severity')} "
                f"projected={block['severity']['projected_onto_the_check']} "
                f"supplied={CLIENT_SUPPLIED_SEVERITY}"
            ),
        ),
    ]

    block["captured"] = True
    block["assertions"] = [
        {"id": name, "claim": claim, "holds": holds, "observed": observed}
        for name, claim, holds, observed in checks
    ]
    block["assertions_total"] = len(checks)
    block["assertions_held"] = sum(1 for check in checks if check[2])
    failures = [
        f"projection.{name}: {claim} — observed {observed}"
        for name, claim, holds, observed in checks
        if not holds
    ]
    return block, failures


# One statement per row the history needs, in the order the trigger chains demand.
# Collapsing them into a loop over a table of inserts would hide exactly the thing this
# function exists to show: which row each refusal below depends on.
def seed_history(conn: psycopg.Connection[Any]) -> History:  # noqa: PLR0915
    """The smallest history in which the central claim is decidable.

    A clause, an incident whose ancestry reaches it, a blame closure that bands the
    ancestry as ``blood_major``, a permit that relies on the clause version, and one
    blocking check standing for the recalled precursor. The permit is then walked
    ``draft -> checks_materialised -> dispositioned`` through its own event chain, which
    is the client CLAIMING that every obligation is disposed of. It is not. That claim
    is exactly what the gate exists to disbelieve.
    """
    site_id = uuid.uuid4()
    # `mainline.fn_recall_policy_anchored` compares `ledger_checkpoint.site_code`
    # against `(NEW).site_id::STRING`, so the ledger partition key for this site is its
    # own identifier. That is a quirk of the shipped function, recorded rather than
    # worked around: a proof that renamed the seam would be proving a different schema.
    site_code = str(site_id)
    site_role = "proof_site"
    signer, countersigner = "proof.signer", "proof.countersigner"
    signer_cred, cosign_cred = _sha("cred", "signer"), _sha("cred", "cosigner")
    commit_id = _sha("commit", "clause-v1")
    merged_commit = _sha("commit", "permit-merge")
    clause_uuid, doc_id = uuid.uuid4(), uuid.uuid4()
    event_id, permit_id = uuid.uuid4(), uuid.uuid4()
    activity_root = "proof/isolation"
    competency = {
        "authorisations": ["ISOLATION_AUTHORITY"],
        "training": ["LOTO-3"],
        "source": "proof-fixture",
    }

    conn.execute(
        "INSERT INTO mainline.site (site_id, site_code, site_role, tenant_id, taxonomy_ver) "
        "VALUES (%s, %s, %s, %s, 1)",
        (site_id, site_code, site_role, uuid.uuid4()),
    )
    for sub, org, rank in ((signer, "proof-operator", 5), (countersigner, "proof-assurer", 5)):
        conn.execute(
            "INSERT INTO mainline.person (signer_sub, effective_from, org, rank, "
            "competency_source_id, competency_sha256, competency_snapshot, identity_source, "
            "enrolment_assurance) "
            "VALUES (%s, now() - INTERVAL '30 days', %s, %s, %s, %s, %s, %s, %s)",
            (
                sub,
                org,
                rank,
                uuid.uuid4(),
                _sha("competency", sub),
                Jsonb(competency),
                "hr_system_of_record",
                "hr_system_of_record",
            ),
        )
    for cred, sub in ((signer_cred, signer), (cosign_cred, countersigner)):
        conn.execute(
            "INSERT INTO mainline.signing_credential (credential_id, signer_sub, "
            "public_key_cose, aaguid, transports, attachment, enrolment_assurance) "
            "VALUES (%s, %s, %s, %s, ARRAY['usb'], 'cross-platform', 'hr_system_of_record')",
            (cred, sub, _sha("cose", sub), _sha("aaguid", sub)[:16]),
        )

    envelope = {"kind": "proof-commit", "clause": str(clause_uuid)}
    conn.execute(
        "INSERT INTO mainline.commit_obj (commit_id, site_id, gen, ref_name, author_sub, "
        "message, envelope, envelope_bytes) VALUES (%s, %s, 1, 'refs/heads/main', %s, %s, %s, %s)",
        (
            commit_id,
            site_id,
            signer,
            "the clause version the permit relies on",
            Jsonb(envelope),
            _jcs(envelope),
        ),
    )
    conn.execute(
        "INSERT INTO mainline.doc (doc_id, site_id, doc_code, title) VALUES (%s, %s, %s, %s)",
        (doc_id, site_id, "proof-sop-1", "Isolation of stored energy"),
    )
    conn.execute(
        "INSERT INTO mainline.clause (clause_uuid, site_id, birth_commit, activity_root, "
        "head_commit) VALUES (%s, %s, %s, %s, %s)",
        (clause_uuid, site_id, commit_id, activity_root, commit_id),
    )
    canon_text = (
        "Before any intrusive work, stored energy shall be isolated, locked and "
        "verified at zero by a competent person."
    )
    conn.execute(
        "INSERT INTO mainline.clause_version (clause_uuid, gen, commit_id, site_id, doc_id, "
        "activity_root, ordinal, printed_label, raw_text, canon_text, canon_version, "
        "canon_sha256, anchor_set, cat_confidence, control_delta, delta_basis, blood_root, "
        "blood_peaks, blood_size, sev_max) "
        "VALUES (%s, 1, %s, %s, %s, %s, 1, '7.3.2(b)', %s, %s, 1, %s, "
        "ARRAY['LOTO','ZERO_ENERGY'], 'ok', 'introduce', 'lattice', %s, ARRAY[]::BYTES[], 0, 4)",
        (
            clause_uuid,
            commit_id,
            site_id,
            doc_id,
            activity_root,
            canon_text,
            canon_text,
            _sha(canon_text),
            _ZERO32,
        ),
    )

    # ── THE PRECURSOR. A severity-4 incident that reaches this clause. It is the fact
    #    the permit's merge depends on, and in the narrative it is RECALLED — found by
    #    the recall pass after the permit was already drafted.
    conn.execute(
        "INSERT INTO mainline.event (event_id, site_id, external_ref, occurred_at, "
        "ingested_at, kind, title, narrative, source_object_key, source_sha256, "
        "severity_actual, severity_potential, severity_gate, severity_basis, canon_version) "
        "VALUES (%s, %s, 'INC-PROOF-1', now() - INTERVAL '400 days', now() - INTERVAL '2 days', "
        "'incident', %s, %s, 'proof/incident-1.pdf', %s, 4, 4, 4, 'human_rated', 1)",
        (
            event_id,
            site_id,
            "Stored energy release during intrusive work",
            (
                "An isolation was signed off without verification at zero; residual "
                "hydraulic pressure released while the guard was removed."
            ),
            _sha("incident", "proof-1"),
        ),
    )
    conn.execute(
        "INSERT INTO mainline.blame_edge (event_id, clause_uuid, basis, state, site_id, "
        "commit_id, features, attribution, evidence_doc_id, evidence_quote_sha256) "
        "VALUES (%s, %s, 'asserted_document', 'active', %s, %s, %s, %s, %s, %s)",
        (
            event_id,
            clause_uuid,
            site_id,
            commit_id,
            Jsonb({"quote_offsets": [0, 96], "source": "investigation report §4"}),
            "The investigation names this clause as the control that failed.",
            doc_id,
            _sha("quote", "proof-1"),
        ),
    )
    # `fn_closure_guard` demands the FIRST generation for a clause version be zero, and
    # ledgers the closure in the same transaction. Both happen here, unhelped.
    conn.execute(
        "INSERT INTO mainline.clause_blame_closure (clause_uuid, as_of_commit, closure_gen, "
        "site_id, ancestor_events, ancestor_count, max_severity, virulence, depth, truncated, "
        "computed_by, projector_ver) "
        "VALUES (%s, %s, 0, %s, ARRAY[%s]::UUID[], 1, 4, 'blood_major', 1, false, "
        "'proof/gate_refusal.py', 'proof-1')",
        (clause_uuid, commit_id, site_id, event_id),
    )

    # ── THE PERMIT and what it cites.
    conn.execute(
        "INSERT INTO mainline.permit (permit_id, site_id, site_role, external_ref, ref_name, "
        "horizon_at) VALUES (%s, %s, %s, 'PTW-PROOF-1', 'refs/permits/proof-1', "
        "now() + INTERVAL '30 days')",
        (permit_id, site_id, site_role),
    )
    conn.execute(
        "INSERT INTO mainline.permit_clause (permit_id, clause_uuid, commit_id, relation) "
        "VALUES (%s, %s, %s, 'relies_on')",
        (permit_id, clause_uuid, commit_id),
    )
    conn.execute(
        "INSERT INTO mainline.boundary_certificate (permit_id, cert_gen, asset_graph_version, "
        "tags_declared, tags_resolved, tags_unmodelled, under_declared) "
        "VALUES (%s, 1, 'proof-asset-graph-1', 1, 1, 0, 0)",
        (permit_id,),
    )
    # The blame account for every cited commit. `z_cbm_gate` refuses a merge whose cited
    # commit has no account, and refuses again if the account disagrees with live
    # residue. Nothing here is residue, so the account is a balanced zero.
    conn.execute(
        "INSERT INTO mainline.cbm_account (site_id, commit_id, account_gen, inherited, carried, "
        "split_carried, merge_carried, residue_open, residue_disposed, computed_by, wrote_as, "
        "projector_ver) VALUES (%s, %s, 0, 0, 0, 0, 0, 0, 0, 'proof/gate_refusal.py', "
        "current_user, 'proof-1')",
        (site_id, commit_id),
    )

    # ── THE RECALL PASS that found the precursor. `mainline_meas.silence_receipt` is
    #    what an exposure receipt must point at, and a silence receipt belongs to a run,
    #    and a run may not cite an unanchored policy. So the anchor and the cosigned
    #    checkpoint are seeded too, and the trigger chain is walked rather than bypassed.
    conn.execute(
        "INSERT INTO mainline.ledger_checkpoint (site_code, tree_size, root_hash, body, beacon, "
        "log_sig, canon_src_sha256, admissible) "
        "VALUES (%s, 1, %s, %s, %s, %s, %s, true)",
        (
            site_code,
            _sha("root", site_code),
            f"mainline/{site_code}\n1\n{_sha('root', site_code).hex()}\n",
            Jsonb({"drand_round": 1, "nist_pulse": 1}),
            _sha("logsig", site_code),
            _sha("canon-src"),
        ),
    )
    conn.execute(
        "INSERT INTO mainline.cosignature (site_code, tree_size, witness_id, trust_domain, "
        "adverse, sig) VALUES (%s, 1, 'witness.proof/hsr-1', 'union_hsr', true, %s)",
        (site_code, _sha("cosig", site_code)),
    )
    policy_version = "proof-recall-1.0"
    conn.execute(
        "INSERT INTO mainline_meas.recall_policy (policy_version, taxonomy_ver, embed_model, "
        "gen_model, prompt_version, beam_size, tau, arms, calibration_set_sha256, author_sub, "
        "signature, anchored_tree_size, anchored_at) "
        "VALUES (%s, 1, 'amazon.titan-embed-text-v2:0', 'au.anthropic.claude', 'p-1', 8, %s, %s, "
        "%s, %s, %s, 1, now())",
        (
            policy_version,
            Jsonb({"tau0": 5, "rho": 4}),
            Jsonb({"lexical": True, "vector": True}),
            _sha("calibration"),
            signer,
            _sha("policy-sig"),
        ),
    )
    recall_run_id = uuid.uuid4()
    conn.execute(
        "INSERT INTO mainline_meas.recall_run (run_id, permit_id, site_id, corpus_commit, "
        "policy_version, index_plan_digest, index_generation, n_candidates, n_blocking, "
        "n_advisory, n_silenced, n_deduped) "
        "VALUES (%s, %s, %s, %s, %s, %s, 'g1', 1, 1, 0, 0, 0)",
        (recall_run_id, permit_id, site_id, commit_id, policy_version, _sha("plan")),
    )
    silence_receipt_id = uuid.uuid4()
    conn.execute(
        "INSERT INTO mainline_meas.silence_receipt (silence_receipt_id, run_id, permit_id, "
        "corpus_root, candidate_root, theta, s, n, boundary_proof, policy_version) "
        "VALUES (%s, %s, %s, %s, %s, 0.35, 1, 1, %s, %s)",
        (
            silence_receipt_id,
            recall_run_id,
            permit_id,
            _sha("corpus-root"),
            _sha("candidate-root"),
            Jsonb({"leaf_s": [], "leaf_s_plus_1": []}),
            policy_version,
        ),
    )

    # ── THE OBLIGATION, AND THE ONE STATEMENT THE WHOLE PROJECTION HANGS OFF.
    #    severity / virulence / closure_gen are supplied and immediately overwritten by
    #    `fn_check_project` (BEFORE INSERT, 0120) from `clause_blame_current`; they are
    #    inputs to nothing (invariant MI25). `fn_check_materialised` (AFTER INSERT, 0121)
    #    then bumps the subject's counters and emits the CDC signal.
    #
    #    The permit's counters are read on BOTH SIDES of this INSERT with nothing in
    #    between, so the delta cannot be attributed to anything else in the seed.
    check_id = uuid.uuid4()
    counters_before = _permit_counters(conn, permit_id)
    conn.execute(
        "INSERT INTO mainline.blocking_check (check_id, subject_kind, permit_id, site_id, "
        "clause_uuid, commit_id, precursor_event_id, origin, severity, virulence, closure_gen, "
        "recall_run_id, evidence_summary) "
        "VALUES (%s, 'permit', %s, %s, %s, %s, %s, 'blame_ancestry', %s, "
        "'routine', 0, %s, %s)",
        (
            check_id,
            permit_id,
            site_id,
            clause_uuid,
            commit_id,
            event_id,
            CLIENT_SUPPLIED_SEVERITY,
            recall_run_id,
            "Recalled precursor INC-PROOF-1 reaches the clause this permit relies on.",
        ),
    )
    counters_after = _permit_counters(conn, permit_id)

    # ── WHO WROTE THE COUNTER, AND THE EVIDENCE THAT THEY DID.
    #    `check_materialised` (0121) is the projection that bumps `open_blocking` and
    #    `gate_epoch` and emits `check_opened` into `mainline_ops.outbox`. Since
    #    0099_outbox.sql landed, that trigger applies, so the counters above moved on
    #    their own and the outbox row is read back below as proof of it.
    #
    #    The fallback branch is kept for a tree where the weld is missing. It is no
    #    longer a caveat that the run tolerates: `evaluate_projection` turns an absent
    #    trigger into a FAILED ASSERTION, so the verdict goes red and the JSON names the
    #    clause that broke. The hand-written counter exists only so the three refusal
    #    beats below still run and a reader can see which half failed.
    projection_present = _trigger_present(
        conn, PROJECTION_TABLE_SCHEMA, PROJECTION_TABLE_NAME, PROJECTION_TRIGGER
    )
    if projection_present:
        counter_source = COUNTER_SOURCE_TRIGGER
    else:
        counter_source = (
            "scripts/proof/gate_refusal.py — the check_materialised trigger is ABSENT from "
            "this schema, so 0121_trg_check_materialised.sql did not apply. The value "
            "written here is the count the gate re-derives from mainline.blocking_check "
            "LEFT JOIN mainline.disposition. This is a FAILED ASSERTION, not a caveat: see "
            "projection.assertions."
        )
        conn.execute(
            "UPDATE mainline.permit SET open_blocking = ("
            "  SELECT count(*) FROM mainline.blocking_check bc"
            "   WHERE bc.permit_id = %s"
            "     AND NOT EXISTS (SELECT 1 FROM mainline.disposition d"
            "                      WHERE d.check_id = bc.check_id"
            "                        AND d.retracted_by IS NULL"
            "                        AND (d.expires_at IS NULL OR d.expires_at > now()))),"
            " gate_epoch = gate_epoch + 1 "
            "WHERE permit_id = %s",
            (permit_id, permit_id),
        )

    projection = _capture_projection(
        conn,
        permit_id,
        check_id,
        site_id,
        counters_before,
        counters_after,
        trigger_present=projection_present,
    )

    # ── THE EXPOSURE RECEIPT. Issued ten minutes ago so that the reading-rate floor is
    #    genuinely met rather than papered over by the countersignature.
    receipt_id = uuid.uuid4()
    conn.execute(
        "INSERT INTO mainline.exposure_receipt (receipt_id, subject_kind, permit_id, actor_sub, "
        "issued_at, issued_hlc, expires_at, corpus_root, silence_receipt_id, policy_version, "
        "total_tokens, receipt_digest) "
        "VALUES (%s, 'permit', %s, %s, now() - INTERVAL '10 minutes', %s, "
        "now() + INTERVAL '2 hours', %s, %s, %s, 200, %s)",
        (
            receipt_id,
            permit_id,
            signer,
            Decimal("1"),
            _sha("corpus-root"),
            silence_receipt_id,
            policy_version,
            _sha("receipt", str(receipt_id)),
        ),
    )
    conn.execute(
        "INSERT INTO mainline.exposure_line (receipt_id, check_id, payload_digest, tokens) "
        "VALUES (%s, %s, %s, 200)",
        (receipt_id, check_id, _sha("line", str(check_id))),
    )

    # ── THE CLIENT'S CLAIM. draft -> checks_materialised -> dispositioned, appended to
    #    the permit's own hash chain. The last edge is the client asserting that every
    #    obligation now carries a signed disposition. It does not. The database is about
    #    to find that out for itself.
    _append_event(conn, permit_id, signer, "draft", "checks_materialised")
    _append_event(conn, permit_id, signer, "checks_materialised", "dispositioned")

    return History(
        site_id=site_id,
        site_code=site_code,
        signer_sub=signer,
        countersigner_sub=countersigner,
        commit_id=commit_id,
        clause_uuid=clause_uuid,
        event_id=event_id,
        permit_id=permit_id,
        check_id=check_id,
        receipt_id=receipt_id,
        recall_run_id=recall_run_id,
        merged_commit=merged_commit,
        counter_source=counter_source,
        projection_trigger_present=projection_present,
        projection=projection,
    )


def _append_event(
    conn: psycopg.Connection[Any],
    permit_id: uuid.UUID,
    actor_sub: str,
    from_state: str,
    to_state: str,
) -> None:
    """Append one permit_event and move the head. The chain trigger verifies the link."""
    row = conn.execute(
        "SELECT head_seq FROM mainline.permit WHERE permit_id = %s", (permit_id,)
    ).fetchone()
    head = int(row[0]) if row else 0
    prev = conn.execute(
        "SELECT chain_digest FROM mainline.permit_event WHERE permit_id = %s AND seq = %s",
        (permit_id, head),
    ).fetchone()
    conn.execute(
        "INSERT INTO mainline.permit_event (permit_id, seq, prev_seq, from_state, to_state, "
        "subject_kind, actor_sub, payload, prev_digest) "
        "VALUES (%s, %s, %s, %s, %s, 'permit', %s, %s, %s)",
        (
            permit_id,
            head + 1,
            head,
            from_state,
            to_state,
            actor_sub,
            Jsonb({"proof": "gate_refusal", "to": to_state}),
            prev[0] if prev else _ZERO32,
        ),
    )
    conn.execute(
        "UPDATE mainline.permit SET state = %s, head_seq = %s WHERE permit_id = %s",
        (to_state, head + 1, permit_id),
    )


# ═════════════════════════════════════════════════════════════════════════════════════
# the merge
# ═════════════════════════════════════════════════════════════════════════════════════


def _merge_payload(history: History) -> tuple[dict[str, Any], bytes, bytes]:
    payload = {
        "permit": str(history.permit_id),
        "merged_by": history.signer_sub,
        "proof": "gate_refusal",
    }
    canon = _jcs(payload)
    return payload, canon, _sha(b"\x00" + canon)


def attempt_merge(conn: psycopg.Connection[Any], history: History) -> dict[str, Any]:
    """Call ``mainline.merge_permit`` in its own SERIALIZABLE transaction.

    Returns the outcome as evidence: on refusal, the SQLSTATE, the exhibit and how the
    exhibit was obtained; on admission, ``00000``. The transaction is never reused, because
    a refused attempt must leave the database exactly as it found it and the only honest way
    to show that is a rollback.
    """
    payload, canon, leaf = _merge_payload(history)
    conn.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
    try:
        conn.execute(
            "CALL mainline.merge_permit(%s, %s, %s, %s, %s, %s, %s, %s)",
            (
                history.permit_id,
                history.merged_commit,
                history.signer_sub,
                "human",
                Jsonb(payload),
                canon,
                1,
                leaf,
            ),
        )
    except psycopg.Error as exc:
        conn.rollback()
        exhibit, source = _constraint(exc)
        return {
            "outcome": "REFUSED",
            "sqlstate": _sqlstate(exc),
            "constraint": exhibit,
            "constraint_source": source,
            "message": _message(exc),
        }
    conn.commit()
    return {"outcome": "ADMITTED", "sqlstate": "00000"}


def record_refusal(
    conn: psycopg.Connection[Any], history: History, refusal: dict[str, Any], note: str
) -> dict[str, Any]:
    """Write the captured refusal into ``mainline.refusal_ledger`` and read it back.

    The ledger's own CHECKs are the point of doing this: `refusal_payload_names_the_exhibit`,
    `refusal_payload_names_the_code` and `refusal_p0001_exhibit_is_parsed` mean a row that
    misdescribes the refusal it records cannot be written at all. A refusal this script
    made up would be refused by the table that stores refusals.
    """
    epoch_row = conn.execute(
        "SELECT gate_epoch FROM mainline.permit WHERE permit_id = %s", (history.permit_id,)
    ).fetchone()
    gate_epoch = int(epoch_row[0]) if epoch_row else 0
    mus = [
        {
            "kind": "obligation",
            "obligation_id": str(history.check_id),
            "origin": "blame_ancestry",
            "severity": 4,
            "virulence": "blood_major",
            "detail": note,
        }
    ]
    payload = {
        "class": "gate",
        "sqlstate": refusal["sqlstate"],
        "constraint": refusal["constraint"],
        "subject_id": str(history.permit_id),
        "subject_kind": "permit",
        "diagnosis": "declarative",
        "mus": mus,
        "naa": {"kind": "dispose_obligations"},
    }
    try:
        conn.execute(
            "INSERT INTO mainline.refusal_ledger (spec_version, sqlstate, constraint_name, "
            "constraint_source, message, subject_kind, subject_id, gate_epoch, diagnosis, "
            "probe_calls, mus_cardinality, naa_kind, payload, recorded_by) "
            "VALUES ('1.0.0-rc.1', %s, %s, %s, %s, 'permit', %s, %s, 'declarative', 0, %s, "
            "'dispose_obligations', %s, 'scripts/proof/gate_refusal.py')",
            (
                refusal["sqlstate"],
                refusal["constraint"],
                refusal["constraint_source"],
                refusal["message"][:2000],
                history.permit_id,
                gate_epoch,
                len(mus),
                Jsonb(payload),
            ),
        )
    except psycopg.Error as exc:
        conn.rollback()
        return {
            "written": False,
            "sqlstate": _sqlstate(exc),
            "message": _message(exc),
        }
    conn.commit()
    row = conn.execute(
        "SELECT refusal_id, observed_at, sqlstate, constraint_name, constraint_source, "
        "subject_kind, subject_id, gate_epoch, diagnosis, mus_cardinality, naa_kind, "
        "recorded_by FROM mainline.refusal_ledger WHERE sqlstate = %s AND constraint_name = %s "
        "ORDER BY observed_at DESC LIMIT 1",
        (refusal["sqlstate"], refusal["constraint"]),
    ).fetchone()
    conn.commit()
    if row is None:
        return {"written": True, "read_back": False}
    return {
        "written": True,
        "read_back": True,
        "refusal_id": str(row[0]),
        "observed_at": row[1].astimezone(UTC).isoformat(),
        "sqlstate": row[2],
        "constraint_name": row[3],
        "constraint_source": row[4],
        "subject_kind": row[5],
        "subject_id": str(row[6]),
        "gate_epoch": int(row[7]),
        "diagnosis": row[8],
        "mus_cardinality": int(row[9]),
        "naa_kind": row[10],
        "recorded_by": row[11],
    }


def force_counter(conn: psycopg.Connection[Any], history: History, value: int) -> None:
    """Set ``open_blocking`` out of band — the disarmed-projector history (CF-03, anomaly A8)."""
    conn.execute(
        "UPDATE mainline.permit SET open_blocking = %s WHERE permit_id = %s",
        (value, history.permit_id),
    )
    conn.commit()


def sign_disposition(conn: psycopg.Connection[Any], history: History) -> dict[str, Any]:
    """File one signed disposition against the open obligation.

    Almost every column on this row is PROJECTED by ``fn_disposition_project`` and the
    values supplied here are overwritten: the subject, the site, the virulence, the
    clearance requirements, the signer's rank and organisation, the competency snapshot
    and the reading-floor verdict all come from authoritative rows. What the signer
    actually chooses is the KIND, the defeater code, the rationale and the signature.
    """
    rationale = (
        "The recalled precursor INC-PROOF-1 is answered by a verified zero-energy "
        "isolation procedure that was re-issued after the incident, and the permit's "
        "scope is covered by that procedure in full. Verification at zero is witnessed "
        "and recorded before any intrusive work begins, so the mechanism the incident "
        "found missing is present and exercised on this permit."
    )
    disposition_id = uuid.uuid4()
    conn.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
    try:
        conn.execute(
            "INSERT INTO mainline.disposition (disposition_id, check_id, receipt_id, "
            "subject_kind, permit_id, site_id, kind, virulence, closure_gen, defeater_code, "
            "defeater_vocab_sha256, rationale, evidence_sha256, signer_sub, signer_rank, "
            "signer_org, signer_credential_id, countersigner_sub, countersigner_credential_id, "
            "signature_alg, authenticator_data, client_data_json, user_verified, "
            "competency_snapshot, competency_source_id, competency_sha256, req_compensating, "
            "req_second_signer, req_foreign_org, req_predicate, req_reassert, min_signer_rank, "
            "severity_snapshot, deliberation_seconds, evidence_opened, prior_override_count) "
            "VALUES (%s, %s, %s, 'permit', %s, %s, 'applied', 'routine', 0, "
            "'MECHANISM_PRESENT_AND_VERIFIED', %s, %s, %s, %s, 1, 'x', %s, %s, %s, "
            "'ES256', %s, %s, true, %s, %s, %s, false, false, false, false, false, 1, 0, 0, "
            "true, 0)",
            (
                disposition_id,
                history.check_id,
                history.receipt_id,
                history.permit_id,
                history.site_id,
                _sha("defeater-vocab"),
                rationale,
                _sha("evidence", str(disposition_id)),
                history.signer_sub,
                _sha("cred", "signer"),
                history.countersigner_sub,
                _sha("cred", "cosigner"),
                _sha("authenticator", str(disposition_id)),
                _jcs({"challenge": disposition_id.hex, "type": "webauthn.get"}),
                Jsonb({"authorisations": ["ISOLATION_AUTHORITY"]}),
                uuid.uuid4(),
                _sha("competency", history.signer_sub),
            ),
        )
    except psycopg.Error as exc:
        conn.rollback()
        return {
            "signed": False,
            "sqlstate": _sqlstate(exc),
            "constraint": _constraint(exc)[0],
            "message": _message(exc),
        }
    conn.commit()
    row = conn.execute(
        "SELECT d.virulence::STRING, d.signer_rank, d.reading_floor_met, "
        "d.deliberation_seconds, p.open_blocking, p.unmet_floor_count, p.countersigned_count "
        "FROM mainline.disposition d JOIN mainline.permit p ON p.permit_id = d.permit_id "
        "WHERE d.disposition_id = %s",
        (disposition_id,),
    ).fetchone()
    conn.commit()
    return {
        "signed": True,
        "disposition_id": str(disposition_id),
        "kind": "applied",
        "virulence_projected": row[0] if row else None,
        "signer_rank_projected": int(row[1]) if row else None,
        "reading_floor_met_projected": bool(row[2]) if row else None,
        "deliberation_seconds_projected": int(row[3]) if row else None,
        "permit_open_blocking_after": int(row[4]) if row else None,
        "permit_unmet_floor_count_after": int(row[5]) if row else None,
        "permit_countersigned_count_after": int(row[6]) if row else None,
    }


def read_merge_record(conn: psycopg.Connection[Any], history: History) -> dict[str, Any]:
    """Read back what the admitted merge actually wrote: the record, and the event chain."""
    row = conn.execute(
        "SELECT m.subject_kind, m.subject_id, m.gate_epoch, m.merged_by, "
        "encode(m.merged_commit, 'hex'), encode(m.clearance_digest, 'hex'), m.merged_at, "
        "p.state::STRING, p.open_blocking "
        "FROM mainline.merge_record m JOIN mainline.permit p ON p.permit_id = m.permit_id "
        "WHERE m.subject_id = %s",
        (history.permit_id,),
    ).fetchone()
    events = conn.execute(
        "SELECT seq, from_state::STRING, to_state::STRING, encode(chain_digest, 'hex') "
        "FROM mainline.permit_event WHERE permit_id = %s ORDER BY seq",
        (history.permit_id,),
    ).fetchall()
    conn.commit()
    if row is None:
        return {"present": False, "event_chain": []}
    return {
        "present": True,
        "subject_kind": row[0],
        "subject_id": str(row[1]),
        "gate_epoch": int(row[2]),
        "merged_by": row[3],
        "merged_commit": row[4],
        "clearance_digest": row[5],
        "merged_at": row[6].astimezone(UTC).isoformat(),
        "permit_state": row[7],
        "permit_open_blocking": int(row[8]),
        "event_chain": [
            {"seq": int(e[0]), "from": e[1], "to": e[2], "chain_digest": e[3]} for e in events
        ],
    }


# ═════════════════════════════════════════════════════════════════════════════════════
# the run
# ═════════════════════════════════════════════════════════════════════════════════════


def _prepare_database(admin_dsn: str, database: str, gc_ttlseconds: int) -> dict[str, Any]:
    with psycopg.connect(admin_dsn, autocommit=True) as conn:
        version = conn.execute("SELECT version()").fetchone()
        conn.execute(f'DROP DATABASE IF EXISTS "{database}" CASCADE')
        conn.execute(f'CREATE DATABASE "{database}"')
        zone: dict[str, Any]
        try:
            conn.execute(
                f'ALTER DATABASE "{database}" CONFIGURE ZONE USING gc.ttlseconds = {gc_ttlseconds}'
            )
        except psycopg.Error as exc:
            zone = {"gc_ttlseconds": None, "error": _message(exc)}
        else:
            zone = {"gc_ttlseconds": gc_ttlseconds}
    return {"version": version[0] if version else "unknown", "database": database, "zone": zone}


def _drop_database(admin_dsn: str, database: str) -> None:
    with psycopg.connect(admin_dsn, autocommit=True) as conn:
        conn.execute(f'DROP DATABASE IF EXISTS "{database}" CASCADE')


# One branch per CLASS OF EVIDENCE, and each one writes a different sentence into the
# report. Collapsing them into a loop over a table of checks would make the failure
# messages generic, and the failure message is the product here.
def run(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:  # noqa: PLR0912, PLR0915
    repo_root = _repo_root()
    migrations = args.migrations or (repo_root / "verticals" / "mainline" / "db" / "migrations")
    if not migrations.is_dir():
        raise SystemExit(f"gate_refusal: no migration tree at {migrations}")

    admin_dsn = _rewrite_dsn(args.dsn, connect_timeout=args.connect_timeout)
    cluster = _prepare_database(admin_dsn, args.database, args.gc_ttlseconds)
    dsn = _rewrite_dsn(args.dsn, database=args.database, connect_timeout=args.connect_timeout)

    evidence: dict[str, Any] = {
        "artefact": "MAINLINE gate-refusal proof",
        "claim": (
            "The trigger projected the counter, emitted the CDC signal, bumped the epoch, "
            "and the gate refused: the database refuses a permit merge when a recalled "
            "precursor carries no signed disposition, and admits the same merge once a "
            "disposition is signed."
        ),
        "generated_at_utc": _now_utc(),
        "generated_by": "scripts/proof/gate_refusal.py",
        "conformance_cases": {
            "projection": "the check_materialised weld (0121), read back from mainline_ops.outbox",
            "refusal": "CF-01 (23514 gate_closed_when_issued)",
            "drift_refusal": "CF-03 (P0001 mainline.fn_permit_merge_gate)",
            "admission": "the same history, after one signed disposition",
        },
        "cluster": cluster,
        "caveats": [],
    }
    failures: list[str] = []

    # ONE connection for the whole proof after this point. Not a micro-optimisation: on a
    # host where `localhost` resolves to a dead `::1` first, every additional connection
    # costs a full TCP timeout, and a proof whose runtime is dominated by DNS is a proof
    # nobody runs. Correctness does not depend on connection count — it depends on each
    # merge attempt getting its own transaction, which it does.
    work = psycopg.connect(dsn, autocommit=True)
    chain = apply_chain(work, dsn, migrations, repo_root)
    evidence["chain"] = chain.as_json()
    if chain.unexplained:
        # With UNPRODUCED_TABLES empty this fires on ANY failure. That is the ratchet:
        # there is no longer a class of migration failure this proof forgives.
        enumerated = (
            f"the {len(UNPRODUCED_TABLES)} enumerated unproduced tables"
            if UNPRODUCED_TABLES
            else "an enumerated unproduced table — the list is EMPTY, so no migration "
            "failure is excused any more"
        )
        failures.append(
            f"{len(chain.unexplained)} migration(s) failed for a reason that is not "
            f"{enumerated}: " + ", ".join(f"{f.version} [{f.sqlstate}]" for f in chain.unexplained)
        )
    if chain.failures:
        evidence["caveats"].append(
            f"{len(chain.failures)} of {chain.files} migrations did not apply. Every one is "
            "listed under chain.failures_* with its file name and SQLSTATE. This script does "
            "not create a table that has no migration: a new table takes a number the "
            "allocation table grants, and this worker owns no band."
        )

    objects = inspect_gate_objects(work)
    evidence["gate_objects"] = objects
    missing = sorted(name for name, ok in objects.items() if not ok)
    if missing:
        failures.append("gate objects absent: " + ", ".join(missing))
        # The key is present on every exit path, so a reader never has to distinguish
        # "the projection was not measured" from "the field was forgotten".
        evidence["projection"] = {
            "captured": False,
            "why": "gate objects were absent, so no history was seeded and no trigger fired",
            "assertions": [],
        }
        evidence["verdict"] = "NOT PROVEN"
        evidence["failures"] = failures
        work.close()
        return EXIT_NOT_PROVEN, evidence

    work.autocommit = False
    work.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
    try:
        history = seed_history(work)
    except psycopg.Error as exc:
        work.rollback()
        work.close()
        evidence["seed"] = {
            "seeded": False,
            "sqlstate": _sqlstate(exc),
            "constraint": _constraint(exc)[0],
            "message": _message(exc),
        }
        evidence["projection"] = {
            "captured": False,
            "why": "the history could not be seeded, so there was no INSERT to measure",
            "assertions": [],
        }
        evidence["verdict"] = "NOT PROVEN"
        evidence["failures"] = [*failures, f"the history could not be seeded: {_message(exc)}"]
        return EXIT_NOT_PROVEN, evidence
    work.commit()
    evidence["history"] = {"seeded": True, **history.as_json()}

    # ── 0 · THE PROJECTION. Who moved the counter, what signal it emitted, and whether
    #        the epoch moved. Ten assertions, each of which can turn the verdict red.
    #        This block replaces a caveat: the run used to APOLOGISE for writing
    #        open_blocking by hand, and now it demonstrates that it did not have to.
    projection, projection_failures = evaluate_projection(history)
    evidence["projection"] = projection
    failures.extend(projection_failures)
    if not history.projection_trigger_present:
        # Still a caveat as well as a failure: the caveat explains what the hand-written
        # counter is, so a reader of a red run knows the refusals below are still the
        # database's own. A caveat is only written when something is genuinely unproven.
        evidence["caveats"].append(
            "mainline.permit.open_blocking was written by this script, not by the "
            "check_materialised trigger, because that trigger is absent from this schema "
            "(0121_trg_check_materialised.sql did not apply). The value written is the "
            "count the gate re-derives for itself, so the refusals below are still the "
            "database's — but the projection is NOT proven, and projection.assertions "
            "names every clause that failed."
        )

    # ── 1 · THE REFUSAL. One open obligation, no disposition.
    refusal = attempt_merge(work, history)
    refusal["case"] = "CF-01"
    refusal["history"] = "one open blocking check, no signed disposition"
    refusal["expected_sqlstate"] = CF01_SQLSTATE
    refusal["expected_constraint"] = CF01_EXHIBIT
    if refusal["outcome"] != "REFUSED":
        failures.append("CF-01: the merge was ADMITTED with an open obligation")
    else:
        if refusal["sqlstate"] != CF01_SQLSTATE:
            failures.append(
                f"CF-01: expected SQLSTATE {CF01_SQLSTATE}, observed {refusal['sqlstate']}"
            )
        if refusal["constraint"] != CF01_EXHIBIT:
            failures.append(
                f"CF-01: expected exhibit {CF01_EXHIBIT!r}, observed {refusal['constraint']!r}"
            )
        refusal["refusal_ledger"] = record_refusal(
            work,
            history,
            refusal,
            "the recalled precursor carries no signed disposition",
        )
    evidence["refusal"] = refusal

    # ── 2 · THE DRIFT REFUSAL. The counter is forced to zero; the gate re-derives.
    force_counter(work, history, 0)
    drift = attempt_merge(work, history)
    drift["case"] = "CF-03"
    drift["history"] = "open_blocking forced to zero out of band; the obligation is still open"
    drift["expected_sqlstate"] = CF03_SQLSTATE
    drift["expected_constraint"] = CF03_EXHIBIT
    if drift["outcome"] != "REFUSED":
        failures.append("CF-03: the merge was ADMITTED against a drifted counter")
    else:
        if drift["sqlstate"] != CF03_SQLSTATE:
            failures.append(
                f"CF-03: expected SQLSTATE {CF03_SQLSTATE}, observed {drift['sqlstate']}"
            )
        if drift["constraint"] != CF03_EXHIBIT:
            failures.append(
                f"CF-03: expected exhibit {CF03_EXHIBIT!r}, observed {drift['constraint']!r}"
            )
        drift["refusal_ledger"] = record_refusal(
            work, history, drift, "the projected counter disagrees with the re-derived count"
        )
    evidence["drift_refusal"] = drift

    # ── 3 · THE ADMISSION. Put the counter back where the derivation says it belongs,
    #        sign one disposition, and ask again.
    force_counter(work, history, 1)
    signature = sign_disposition(work, history)
    evidence["disposition"] = signature
    if not signature["signed"]:
        failures.append(f"the disposition could not be signed: {signature.get('message')}")
        evidence["admission"] = {"attempted": False}
    else:
        admission = attempt_merge(work, history)
        admission["case"] = "admission"
        admission["expected_sqlstate"] = "00000"
        if admission["outcome"] != "ADMITTED":
            failures.append(
                "the merge was REFUSED after a signed disposition — a gate that always "
                f"refuses is a broken gate: [{admission.get('sqlstate')}] "
                f"{admission.get('constraint')} {admission.get('message')}"
            )
        admission["merge_record"] = read_merge_record(work, history)
        evidence["admission"] = admission

    work.close()
    evidence["failures"] = failures
    evidence["verdict"] = "PROVEN" if not failures else "NOT PROVEN"
    return (EXIT_PROVEN if not failures else EXIT_NOT_PROVEN), evidence


def _print_summary(evidence: dict[str, Any], out: Path) -> None:
    chain = evidence.get("chain", {})
    print(f"cluster       {evidence['cluster']['version']}")
    print(f"database      {evidence['cluster']['database']}")
    print(
        f"chain         {chain.get('applied_count', 0)}/{chain.get('files', 0)} applied, "
        f"{chain.get('failed_count', 0)} failed, {chain.get('seconds', 0)}s"
    )
    print(f"reached 0115  {chain.get('reached_0115_fn_permit_merge_gate')}")
    unproduced = chain.get("unproduced_tables_enumerated", [])
    print(
        "unproduced    (none) — every relation this tree references has a producer"
        if not unproduced
        else f"unproduced    {len(unproduced)}: " + ", ".join(unproduced)
    )
    for failure in chain.get("failures_unexplained", []):
        print(f"  ! UNEXPLAINED {failure['version']} [{failure['sqlstate']}] {failure['message']}")
    for failure in chain.get("failures_attributable_to_an_unproduced_table", []):
        print(
            f"  - no producer {failure['version']} [{failure['sqlstate']}] "
            f"needs {failure['unproduced_table']}"
        )

    projection = evidence.get("projection", {})
    if projection.get("captured"):
        outbox = projection["outbox"]
        row = outbox.get("row") or {}
        print(
            f"PROJECTION    {projection['assertions_held']}/{projection['assertions_total']} "
            f"held · open_blocking {projection['open_blocking']['before']}"
            f"->{projection['open_blocking']['after']} · gate_epoch "
            f"{projection['gate_epoch']['before']}->{projection['gate_epoch']['after']} · "
            f"outbox {row.get('kind')!r} severity {row.get('max_severity')} "
            f"(client supplied {projection['severity']['supplied_by_this_script']})"
        )
        for assertion in projection.get("assertions", []):
            if not assertion["holds"]:
                print(f"  ! {assertion['id']}: {assertion['observed']}")
    else:
        print(f"PROJECTION    NOT MEASURED — {projection.get('why', 'no reason recorded')}")

    for key, label in (("refusal", "REFUSAL"), ("drift_refusal", "DRIFT  ")):
        section = evidence.get(key)
        if section:
            print(
                f"{label}       {section['outcome']} [{section.get('sqlstate')}] "
                f"{section.get('constraint')} ({section.get('constraint_source')})"
            )
    admission = evidence.get("admission")
    if admission:
        print(f"ADMISSION     {admission.get('outcome')} [{admission.get('sqlstate')}]")
    # The empty case is PRINTED, not omitted. A reader who sees no caveat line cannot
    # tell "there were none" from "the field was dropped", and the difference between
    # those two is the whole reason this repository publishes its caveats.
    caveats = evidence.get("caveats", [])
    if not caveats:
        print("caveats       (none) — nothing in this run is unproven-but-tolerated")
    for caveat in caveats:
        print(f"caveat        {caveat}")
    for failure in evidence.get("failures", []):
        print(f"  ! {failure}")
    print(f"VERDICT       {evidence['verdict']}")
    print(f"evidence      {out}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="gate_refusal",
        description=(
            "Prove that the database refuses a permit merge when a recalled precursor "
            "carries no signed disposition — and admits it when one is signed."
        ),
    )
    parser.add_argument(
        "--dsn",
        default=os.environ.get("MAINLINE_TEST_DSN")
        or os.environ.get("TRAPPOINT_DSN")
        or os.environ.get("COCKROACH_URL")
        or os.environ.get("CRDB_URL")
        or os.environ.get("LOCAL_DSN"),
        help="admin DSN; the throwaway database is created on this cluster",
    )
    parser.add_argument(
        "--database",
        default="w_qr_gate_refusal_proof",
        help="name of the throwaway database (dropped and recreated on every run)",
    )
    parser.add_argument(
        "--migrations",
        type=Path,
        default=None,
        help="migration tree (default: verticals/mainline/db/migrations under the repo root)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="evidence path (default: evidence/gate-refusal/proof-<utc>.json)",
    )
    parser.add_argument(
        "--gc-ttlseconds",
        type=int,
        default=4500,
        help="zone gc.ttlseconds for the throwaway database; 4500 is what Cloud enforces",
    )
    parser.add_argument(
        "--connect-timeout",
        type=int,
        default=10,
        help=(
            "seconds libpq waits per resolved address before trying the next one. Guards "
            "against a host where `localhost` resolves to a dead ::1 first, which is worth "
            "130 seconds per connection when it is not set"
        ),
    )
    parser.add_argument(
        "--keep",
        action="store_true",
        help="leave the throwaway database in place for inspection",
    )
    args = parser.parse_args(argv)

    if not args.dsn:
        print(
            "gate_refusal: no DSN. Pass --dsn, or set MAINLINE_TEST_DSN / TRAPPOINT_DSN / "
            "COCKROACH_URL / CRDB_URL / LOCAL_DSN. For the local single-node cluster: "
            "postgresql://root@127.0.0.1:26257/defaultdb?sslmode=disable",
            file=sys.stderr,
        )
        return EXIT_USAGE

    repo_root = _repo_root()
    out = args.out or (repo_root / "evidence" / "gate-refusal" / f"proof-{_stamp()}.json")
    out.parent.mkdir(parents=True, exist_ok=True)

    try:
        code, evidence = run(args)
    except psycopg.OperationalError as exc:
        # No cluster is not a refusal. Keeping the two apart is what lets a red lane mean
        # something: "the gate did not refuse" and "there was nothing to ask" are
        # different findings and only one of them is about the product.
        print(f"gate_refusal: could not reach the cluster: {_message(exc)}", file=sys.stderr)
        return EXIT_USAGE
    finally:
        if not args.keep:
            with contextlib.suppress(psycopg.Error):
                _drop_database(
                    _rewrite_dsn(args.dsn, connect_timeout=args.connect_timeout), args.database
                )

    out.write_text(json.dumps(evidence, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    # REUSE sidecar. A generated artefact carries no comment syntax, and `evidence/` is
    # already covered by `.license` files for exactly this reason; emitting it here keeps
    # the compliance checker green without anyone having to remember.
    out.with_suffix(out.suffix + ".license").write_text(
        "SPDX-FileCopyrightText: 2026 MAINLINE contributors\nSPDX-License-Identifier: CC-BY-4.0\n",
        encoding="utf-8",
    )
    _print_summary(evidence, out)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
