#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Put a database into exactly the state the camera expects — then prove it did.

The founder is holding a microphone. Between him and a take there is a database that
must be in one precise condition: the migration chain applied, the gate objects
present, one permit whose merge is blocked by one undispositioned obligation, the
``gate_closed_when_issued`` constraint still attached (shot ``s12`` films an admin
dropping it, so it has to be there to drop), the append-only trigger welded onto
``mainline.blocking_check`` (shot ``s11`` films the ``DELETE`` bouncing off it), and
``trappoint.explain_refusal`` installed (shot ``s10`` recovers the constraint NAME
with it, because a raw CockroachDB shell prints the check EXPRESSION and not the name).

Getting that state by hand is nine minutes of typing and one chance to get it wrong in
a way nobody notices until the footage is on the timeline. This is one command.

WHAT IT DOES NOT DO
-------------------
It does not reimplement the proof. Every primitive here — ``_prepare_database``,
``apply_chain``, ``seed_history``, ``attempt_merge``, ``force_counter``,
``sign_disposition`` — is IMPORTED from ``scripts/proof/gate_refusal.py``. If the proof
and the demo state ever disagreed about what "seeded" means, the video would be filming
a history the proof does not make. They cannot disagree: there is one implementation.

It does not create a table that has no migration, and it does not assume which tables
those are. ``mainline_ops.outbox`` is the one that matters here: while it has no producer
migration, ``0121_trg_check_materialised.sql`` cannot apply, and ``open_blocking`` is then
written by the seeding code rather than by the gate's own projection trigger. **That
question is printed on every run, in both modes, and ANSWERED from the catalogue** — never
from a sentence somebody wrote down once. Nothing is filmed under a false impression.

It does not execute the destructive on-camera statement. ``ALTER TABLE
mainline.permit DROP CONSTRAINT gate_closed_when_issued`` is verified by asking the
catalogue whether the constraint is *there*, never by dropping it. The three refusals
ARE executed, each in its own transaction, each rolled back — a refused attempt must
leave the database exactly as it found it, and the last check in the table asserts that
it did.

Usage::

    python scripts/submission/seed_demo_state.py                  # build, then verify
    python scripts/submission/seed_demo_state.py --verify-only    # verify what is there

Exit codes:

* ``0`` — the state is exactly right; roll camera.
* ``1`` — the state is NOT right. Every failing row is named in the table above the
  verdict. Do not record against this database.
* ``2`` — the invocation was wrong, or there was no cluster to talk to. Distinct from
  ``1`` so that "the node is down" is never read as "the gate did not refuse".
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import sys
import textwrap
import uuid
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

import psycopg

#: EVERY CAMERA-FACING LINE FITS IN THIS MANY COLUMNS — the `--camera` block and the
#: caveat. That is a camera decision rather than a style one: a terminal soft-wraps a long
#: line wherever the window happens to end, so an unwrapped 475-character caveat re-flows
#: differently on the founder's machine than it did here, and a shot composed around a line
#: that moves is a re-record. Measured before this was added: the caveat printed as a single
#: 475-character line; the `--camera` block now maxes at exactly this width.
#:
#: The VERIFICATION TABLE is deliberately NOT bounded. It runs to whatever its observed
#: values need — around 135 columns, mostly UUIDs — because it is a diagnostic the operator
#: reads before recording, never a frame. Truncating a permit_id to make a table pretty
#: would cost the one value the next command has to be given.
CAMERA_WIDTH = 96


def wrapped(text: str, *, indent: str = "", first: str | None = None) -> str:
    """Fold *text* to `CAMERA_WIDTH`, hanging-indented so a wrap reads as a wrap."""
    return textwrap.fill(
        " ".join(text.split()),
        width=CAMERA_WIDTH,
        initial_indent=first if first is not None else indent,
        subsequent_indent=indent,
        break_long_words=False,
        break_on_hyphens=False,
    )


EXIT_OK = 0
EXIT_WRONG_STATE = 1
EXIT_USAGE = 2

DEFAULT_DSN = "postgresql://root@localhost:26257/defaultdb?sslmode=disable"
DEFAULT_DATABASE = "w_s08_demo_state"

#: The seeded permit's external reference. `seed_history` writes it; this is how the
#: verifier finds the permit again in `--verify-only`, where it did not do the seeding.
PERMIT_EXTERNAL_REF = "PTW-PROOF-1"

#: THE CAVEAT. Printed on EVERY run, in both modes, whether or not anything is wrong —
#: this is the sentence `scripts/proof/gate_refusal.py` puts in its own `caveats` block,
#: and it is the difference between filming a database refusal and filming a script's
#: arrangement of one. The founder is entitled to know which he is pointing a camera at
#: before he says a sentence about it out loud.
#:
#: It is printed unconditionally and ANSWERED conditionally, because the answer has
#: already changed once. The committed evidence
#: (`evidence/gate-refusal/proof-20260810T004200Z.json`) records 246 of 261 migrations
#: applied and `0121_trg_check_materialised` among the casualties; on a working tree
#: that has since gained producer migrations for the five unproduced tables, the trigger
#: installs and writes the counter itself. Printing a fixed sentence for a moving fact
#: is how a video ends up narrating a state the database left behind.
CAVEAT_QUESTION = (
    "WHO WROTE mainline.permit.open_blocking? The gate's own projection trigger "
    "(check_materialised, migration 0121) depends on mainline_ops.outbox. Where that "
    "table has no producer migration the trigger cannot install, and the seeded history "
    "writes the counter itself — to the value the gate independently re-derives from "
    "mainline.blocking_check LEFT JOIN mainline.disposition. The refusal on camera is "
    "the database's either way; the COUNTER that provoked it may not be."
)
CAVEAT_ANSWER = {
    True: (
        "MEASURED ON THIS RUN: the trigger IS installed, so the counter is the "
        "database's own projection. You may say the projection closed the counter."
    ),
    False: (
        "MEASURED ON THIS RUN: the trigger is ABSENT, so the counter was written by "
        "this script. Do NOT say 'the trigger closed the counter' on camera; say the "
        "gate re-derived the count and refused."
    ),
    None: (
        "NOT MEASURED ON THIS RUN: there was no seeded database to ask. Say nothing "
        "about the counter until a run of this script has answered the question."
    ),
}


def caveat(trigger_present: bool | None) -> str:
    return (
        wrapped(CAVEAT_QUESTION, indent="         ", first="CAVEAT   ")
        + "\n"
        + wrapped(CAVEAT_ANSWER[trigger_present], indent="         ")
    )


# ═════════════════════════════════════════════════════════════════════════════════════
# importing the proof rather than copying it
# ═════════════════════════════════════════════════════════════════════════════════════


def repo_root(start: Path | None = None) -> Path:
    """The workspace root: the nearest ancestor holding both `spec/` and `compose.yaml`.

    Same rule as `scripts/proof/gate_refusal.py::_repo_root`, deliberately, so that a
    checkout in which one of them finds the root and the other does not is impossible.
    """
    here = (start or Path(__file__).resolve().parent).resolve()
    for candidate in (here, *here.parents):
        if (candidate / "spec").is_dir() and (candidate / "compose.yaml").is_file():
            return candidate
    return Path.cwd().resolve()


def load_proof(root: Path) -> ModuleType:
    """Import `scripts/proof/gate_refusal.py` as a module.

    `scripts/` is not a package and must not become one — adding `__init__.py` files to
    a directory of standalone entry points changes how every one of them is invoked. So
    the module is loaded from its path. The failure mode is named rather than left as a
    bare ImportError, because "the proof script is missing" and "psycopg is missing" are
    different problems and only one of them is about this repository.
    """
    path = root / "scripts" / "proof" / "gate_refusal.py"
    if not path.is_file():
        raise SystemExit(
            f"seed_demo_state: the proof script is not at {path}. This tool imports its "
            "primitives rather than reimplementing them; without it there is nothing to "
            "seed and nothing to verify."
        )
    spec = importlib.util.spec_from_file_location("mainline_gate_refusal", path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"seed_demo_state: could not load {path} as a module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# ═════════════════════════════════════════════════════════════════════════════════════
# the verification table
# ═════════════════════════════════════════════════════════════════════════════════════


@dataclass(slots=True)
class Row:
    """One line of the verification table.

    `required` is the whole point. An INFO row reports something the operator should
    know; a required row that is not `ok` makes the run exit non-zero. Nothing is
    reported as a pass because it was not looked at.
    """

    check: str
    ok: bool
    observed: str
    required: bool = True
    shots: str = ""

    @property
    def status(self) -> str:
        if not self.required:
            return "INFO"
        return "OK" if self.ok else "FAIL"


class Table:
    def __init__(self) -> None:
        self.rows: list[Row] = []

    def add(
        self, check: str, ok: bool, observed: str, *, required: bool = True, shots: str = ""
    ) -> Row:
        row = Row(check=check, ok=ok, observed=observed, required=required, shots=shots)
        self.rows.append(row)
        return row

    @property
    def failures(self) -> list[Row]:
        return [r for r in self.rows if r.required and not r.ok]

    def render(self) -> str:
        widths = (
            max(6, *(len(r.check) for r in self.rows)),
            6,
            max(5, *(len(r.shots) for r in self.rows)),
        )
        head = (
            f"{'CHECK'.ljust(widths[0])}  {'STATUS'.ljust(6)}  {'SHOTS'.ljust(widths[2])}  OBSERVED"
        )
        rule = f"{'-' * widths[0]}  {'-' * 6}  {'-' * widths[2]}  {'-' * 44}"
        lines = [head, rule]
        for row in self.rows:
            lines.append(
                f"{row.check.ljust(widths[0])}  {row.status.ljust(6)}  "
                f"{row.shots.ljust(widths[2])}  {row.observed}"
            )
        lines.append(rule)
        return "\n".join(lines)


# ═════════════════════════════════════════════════════════════════════════════════════
# reading the seeded history back out of the database
# ═════════════════════════════════════════════════════════════════════════════════════


@dataclass(slots=True)
class Found:
    """What `--verify-only` could find. Every field may be absent; absence is a finding."""

    permit_id: uuid.UUID | None = None
    site_id: uuid.UUID | None = None
    state: str | None = None
    open_blocking: int | None = None
    check_id: uuid.UUID | None = None
    receipt_id: uuid.UUID | None = None
    clause_uuid: uuid.UUID | None = None
    event_id: uuid.UUID | None = None
    live_dispositions: int | None = None
    permits_matching: int = 0
    #: Whether `check_materialised` (0121) is installed. `None` means nothing asked.
    projection_trigger_present: bool | None = None


def find_history(conn: psycopg.Connection[Any]) -> Found:
    """Locate the seeded permit and everything the camera commands need to name it."""
    found = Found()
    rows = conn.execute(
        "SELECT permit_id, site_id, state::STRING, open_blocking FROM mainline.permit "
        "WHERE external_ref = %s ORDER BY permit_id",
        (PERMIT_EXTERNAL_REF,),
    ).fetchall()
    found.permits_matching = len(rows)
    if not rows:
        return found
    found.permit_id, found.site_id, found.state, found.open_blocking = (
        rows[0][0],
        rows[0][1],
        rows[0][2],
        int(rows[0][3]),
    )
    check = conn.execute(
        "SELECT check_id, clause_uuid, precursor_event_id FROM mainline.blocking_check "
        "WHERE permit_id = %s ORDER BY check_id",
        (found.permit_id,),
    ).fetchall()
    if check:
        found.check_id, found.clause_uuid, found.event_id = check[0][0], check[0][1], check[0][2]
    receipt = conn.execute(
        "SELECT receipt_id FROM mainline.exposure_receipt WHERE permit_id = %s "
        "ORDER BY issued_at DESC LIMIT 1",
        (found.permit_id,),
    ).fetchone()
    if receipt:
        found.receipt_id = receipt[0]
    live = conn.execute(
        "SELECT count(*) FROM mainline.disposition d JOIN mainline.blocking_check bc "
        "ON bc.check_id = d.check_id WHERE bc.permit_id = %s AND d.retracted_by IS NULL "
        "AND (d.expires_at IS NULL OR d.expires_at > now())",
        (found.permit_id,),
    ).fetchone()
    found.live_dispositions = int(live[0]) if live else None
    return found


def history_from(proof: ModuleType, found: Found) -> Any:
    """Rebuild the proof's `History` from what is in the database.

    `attempt_merge` needs a `History`, and in `--verify-only` this process did not do
    the seeding. Every field it actually reads is recovered from the catalogue except
    `merged_commit`, which `seed_history` derives deterministically as sha256 over
    ("commit", "permit-merge") — so it is re-derived with the proof's own `_sha`, not
    guessed and not stored.
    """
    return proof.History(
        site_id=found.site_id,
        site_code=str(found.site_id),
        signer_sub="proof.signer",
        countersigner_sub="proof.countersigner",
        commit_id=proof._sha("commit", "clause-v1"),
        clause_uuid=found.clause_uuid,
        event_id=found.event_id,
        permit_id=found.permit_id,
        check_id=found.check_id,
        receipt_id=found.receipt_id,
        recall_run_id=uuid.UUID(int=0),
        merged_commit=proof._sha("commit", "permit-merge"),
        counter_source="read back by scripts/submission/seed_demo_state.py",
        projection_trigger_present=False,
    )


# ═════════════════════════════════════════════════════════════════════════════════════
# catalogue probes
# ═════════════════════════════════════════════════════════════════════════════════════


def constraint_present(conn: psycopg.Connection[Any], schema: str, table: str, name: str) -> bool:
    row = conn.execute(
        "SELECT count(*) FROM information_schema.table_constraints "
        "WHERE constraint_schema = %s AND table_name = %s AND constraint_name = %s",
        (schema, table, name),
    ).fetchone()
    return bool(row and row[0])


def trigger_present(conn: psycopg.Connection[Any], schema: str, table: str, name: str) -> bool:
    row = conn.execute(
        "SELECT count(*) FROM information_schema.triggers "
        "WHERE event_object_schema = %s AND event_object_table = %s AND trigger_name = %s",
        (schema, table, name),
    ).fetchone()
    return bool(row and row[0])


def routine_present(conn: psycopg.Connection[Any], schema: str, name: str) -> bool:
    row = conn.execute(
        "SELECT count(*) FROM information_schema.routines "
        "WHERE routine_schema = %s AND routine_name = %s",
        (schema, name),
    ).fetchone()
    return bool(row and row[0])


def database_present(admin_dsn: str, database: str) -> bool:
    """Does *database* exist on this cluster?

    Asked with ``[SHOW DATABASES]`` rather than ``crdb_internal.databases``: on
    CockroachDB v26.2.5 the `crdb_internal` schema is restricted and a plain ``root``
    session is refused with ``42501`` and a hint about ``allow_unsafe_internals``.
    Measured on the local node, not assumed.
    """
    with psycopg.connect(admin_dsn, autocommit=True) as conn:
        row = conn.execute(
            "SELECT count(*) FROM [SHOW DATABASES] WHERE database_name = %s", (database,)
        ).fetchone()
        return bool(row and row[0])


# ═════════════════════════════════════════════════════════════════════════════════════
# the three refusals, executed and rolled back
# ═════════════════════════════════════════════════════════════════════════════════════


def _refuses(
    conn: psycopg.Connection[Any], sql: str, params: tuple[Any, ...], proof: ModuleType
) -> tuple[str, str, str]:
    """Run *sql*, expect it to fail, and return ``(sqlstate, exhibit, message)``.

    On success — which for these three statements would itself be the finding — the
    transaction is rolled back anyway and the tuple says ``00000``. Nothing this
    function runs is allowed to survive it.
    """
    try:
        conn.execute(sql, params)  # type: ignore[arg-type]
    except psycopg.Error as exc:
        conn.rollback()
        return proof._sqlstate(exc), proof._constraint(exc)[0], proof._message(exc)
    conn.rollback()
    return "00000", "", "the statement SUCCEEDED and was rolled back"


def probe_merge_refusal(conn: psycopg.Connection[Any], proof: ModuleType, found: Found) -> dict:
    """Shots s08/s09: the merge our client attempts, and the refusal it renders."""
    history = history_from(proof, found)
    return proof.attempt_merge(conn, history)


def probe_raw_update(conn: psycopg.Connection[Any], proof: ModuleType, found: Found):
    """Shot s10: cluster admin, raw SQL, the application bypassed entirely."""
    return _refuses(
        conn,
        "UPDATE mainline.permit SET state = 'merged' WHERE permit_id = %s",
        (found.permit_id,),
        proof,
    )


def probe_delete_obligation(conn: psycopg.Connection[Any], proof: ModuleType, found: Found):
    """Shot s11: the obligation is append-only, so it cannot be deleted."""
    return _refuses(
        conn,
        "DELETE FROM mainline.blocking_check WHERE permit_id = %s",
        (found.permit_id,),
        proof,
    )


# ═════════════════════════════════════════════════════════════════════════════════════
# verify
# ═════════════════════════════════════════════════════════════════════════════════════


def verify(conn: psycopg.Connection[Any], proof: ModuleType, table: Table) -> Found:
    """Fill *table* with everything the first on-camera shot depends on.

    One branch per class of evidence, deliberately not a loop over a list of predicates:
    the observed column is what somebody reads at 06:00 on capture day, and a generic
    "expected True, got False" is not an instruction.
    """
    conn.autocommit = False

    objects = proof.inspect_gate_objects(conn)
    missing = sorted(name for name, ok in objects.items() if not ok)
    table.add(
        "gate objects",
        not missing,
        f"{len(objects) - len(missing)}/{len(objects)} present"
        + (f"; ABSENT: {', '.join(missing)}" if missing else ""),
        shots="s08-s12",
    )

    found = find_history(conn)
    table.add(
        "permit row",
        found.permits_matching == 1,
        f"{found.permits_matching} permit(s) with external_ref={PERMIT_EXTERNAL_REF!r}"
        + (f"; permit_id={found.permit_id}" if found.permit_id else ""),
        shots="s08",
    )
    if found.permit_id is None:
        table.add(
            "seeded history",
            False,
            "no seeded permit — run without --verify-only to build the state",
            shots="all",
        )
        # The counter question is still answerable from the catalogue even with no
        # history, and answering it is cheaper than telling the operator to run again.
        found.projection_trigger_present = trigger_present(
            conn, "mainline", "blocking_check", "check_materialised"
        )
        conn.rollback()
        return found

    table.add(
        "permit state",
        found.state == "dispositioned",
        f"state={found.state!r} (the client's claim that every obligation is disposed of)",
        shots="s08",
    )
    table.add(
        "open obligation",
        found.open_blocking == 1,
        f"permit.open_blocking={found.open_blocking}",
        shots="s08 s09",
    )
    table.add(
        "obligation row",
        found.check_id is not None,
        f"blocking_check check_id={found.check_id}",
        shots="s11",
    )
    table.add(
        "no disposition yet",
        found.live_dispositions == 0,
        f"{found.live_dispositions} live disposition(s) against the obligation",
        shots="s08 s13",
    )
    table.add(
        "exposure receipt",
        found.receipt_id is not None,
        f"receipt_id={found.receipt_id}",
        required=False,
        shots="s14",
    )

    ok = constraint_present(conn, "mainline", "permit", "gate_closed_when_issued")
    table.add(
        "gate constraint attached",
        ok,
        "mainline.permit CONSTRAINT gate_closed_when_issued"
        + ("" if ok else " is ABSENT — s12 has nothing to drop"),
        shots="s09 s12",
    )
    ok = trigger_present(conn, "mainline", "blocking_check", "append_only")
    table.add(
        "append-only weld",
        ok,
        "TRIGGER append_only ON mainline.blocking_check"
        + ("" if ok else " is ABSENT — s11 cannot be filmed"),
        shots="s11",
    )
    ok = routine_present(conn, "trappoint", "explain_refusal")
    table.add(
        "explain_refusal installed",
        ok,
        "trappoint.explain_refusal(kind, id, constraint, attempt)"
        + ("" if ok else " is ABSENT — s10 cannot recover the constraint NAME"),
        shots="s10",
    )

    # ── the three refusals, each executed for real and each rolled back ───────────────
    # `attempt_merge` rolls back a refusal and COMMITS an admission — that asymmetry is
    # correct for the proof, where an admission is the third beat. Here an admission is
    # a failure, and it is a failure that has already committed by the time we see it.
    # So it is reported as spent rather than merely wrong: this database cannot be
    # filmed again and no amount of re-verifying will change that.
    merge = probe_merge_refusal(conn, proof, found)
    hit = (
        merge.get("outcome") == "REFUSED"
        and merge.get("sqlstate") == proof.CF01_SQLSTATE
        and merge.get("constraint") == proof.CF01_EXHIBIT
    )
    if merge.get("outcome") == "ADMITTED":
        observed = (
            "ADMITTED [00000] — the gate let it through, and the admission COMMITTED. "
            "This database is SPENT; rebuild it before recording."
        )
    else:
        observed = (
            f"{merge.get('outcome')} [{merge.get('sqlstate')}] "
            f"{merge.get('constraint') or '(no exhibit)'} ({merge.get('constraint_source')})"
        )
    table.add("merge REFUSES", hit, observed, shots="s08 s09")

    state, _exhibit2, message = probe_raw_update(conn, proof, found)
    table.add(
        "raw UPDATE REFUSES",
        state == "23514",
        f"[{state}] {message[:64]}",
        shots="s10",
    )

    state, _exhibit, message = probe_delete_obligation(conn, proof, found)
    expected = "MAINLINE: this table is append-only"
    table.add(
        "DELETE REFUSES",
        state == "P0001" and expected in message,
        f"[{state}] {message[:72]}",
        shots="s11",
    )

    # ── and the state is exactly where it was before those three ran ─────────────────
    after = find_history(conn)
    intact = (
        after.state == found.state
        and after.open_blocking == found.open_blocking
        and after.live_dispositions == found.live_dispositions
        and after.check_id == found.check_id
    )
    table.add(
        "state intact after probes",
        intact,
        f"state={after.state!r} open_blocking={after.open_blocking} "
        f"dispositions={after.live_dispositions}",
        shots="s08-s12",
    )

    present = trigger_present(conn, "mainline", "blocking_check", "check_materialised")
    found.projection_trigger_present = present
    after.projection_trigger_present = present
    table.add(
        "open_blocking written by",
        True,
        (
            "trigger check_materialised (0121) — the database's own projection"
            if present
            else "scripts/submission/seed_demo_state.py — 0121 is absent; see the caveat"
        ),
        required=False,
        shots="s08",
    )
    conn.rollback()
    return found


# ═════════════════════════════════════════════════════════════════════════════════════
# build
# ═════════════════════════════════════════════════════════════════════════════════════


def build(args: argparse.Namespace, proof: ModuleType, root: Path, table: Table) -> str:
    """Create the database, apply the chain, seed the history. Return the working DSN."""
    migrations = args.migrations or (root / "verticals" / "mainline" / "db" / "migrations")
    if not migrations.is_dir():
        raise SystemExit(f"seed_demo_state: no migration tree at {migrations}")

    admin_dsn = proof._rewrite_dsn(args.dsn, connect_timeout=args.connect_timeout)
    cluster = proof._prepare_database(admin_dsn, args.database, args.gc_ttlseconds)
    dsn = proof._rewrite_dsn(args.dsn, database=args.database, connect_timeout=args.connect_timeout)
    table.add("cluster", True, str(cluster.get("version", "unknown")), required=False)
    zone = cluster.get("zone", {})
    table.add(
        "gc.ttlseconds",
        True,
        f"{zone.get('gc_ttlseconds')} on {args.database} (Cloud enforces 4500)",
        required=False,
    )

    work = psycopg.connect(dsn, autocommit=True)
    try:
        chain = proof.apply_chain(work, dsn, migrations, root)
        unexplained = chain.unexplained
        table.add(
            "migration chain",
            not unexplained,
            f"{len(chain.applied)}/{chain.files} applied, {len(chain.failures)} failed, "
            f"{len(unexplained)} unexplained, {round(chain.seconds, 1)}s",
            shots="all",
        )
        for failure in unexplained:
            table.add(
                f"  ! {failure.version}",
                False,
                f"[{failure.sqlstate}] {failure.message[:70]}",
                shots="all",
            )
        table.add(
            "reached 0115 merge gate",
            "0115_fn_permit_merge_gate" in chain.applied,
            "0115_fn_permit_merge_gate applied",
            shots="s08 s09",
        )

        work.autocommit = False
        work.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
        try:
            history = proof.seed_history(work)
        except psycopg.Error as exc:
            work.rollback()
            table.add(
                "seed history",
                False,
                f"[{proof._sqlstate(exc)}] {proof._message(exc)[:80]}",
                shots="all",
            )
            return dsn
        work.commit()
        table.add(
            "seed history",
            True,
            f"permit_id={history.permit_id} check_id={history.check_id}",
            shots="all",
        )
    finally:
        work.close()
    return dsn


# ═════════════════════════════════════════════════════════════════════════════════════
# output
# ═════════════════════════════════════════════════════════════════════════════════════


def run_camera(  # noqa: PLR0915
    conn: psycopg.Connection[Any], proof: ModuleType, found: Found
) -> int:
    """Film beat 2 from one command: three statements, three outcomes, all rolled back.

    WHY THIS MODE EXISTS, stated plainly so nobody mistakes it for staging.

    Shot ``s09`` films "our client, which reads ``diag.constraint_name``" — because on
    CockroachDB v26.2.5 a ``23514`` MESSAGE names the check EXPRESSION and not the
    constraint, so a raw shell cannot show the name the voice-over says. That client is
    `trappoint_core.errors`, and it is what this mode calls. **Every SQLSTATE, every
    message and every constraint name below is the server's. The layout is this
    script's, and the banner says so on camera.**

    Measured divergence, recorded rather than smoothed over: the shipped
    ``GateRefused`` renders as ``GateRefused("23514 gate_closed_when_issued: failed to
    satisfy CHECK constraint (…)")``, which is NOT the
    ``GateRefused(constraint=…, sqlstate=…)`` form written into
    ``verticals/mainline/demo/REFUSAL-STRINGS.yaml`` as ``client_render``. Neither file
    is this worker's to edit. This mode therefore prints the fields on their own labelled
    lines, which carries every string the tape matches on — ``SQLSTATE: 23514``, the
    constraint name, and ``MAINLINE: this table is append-only`` — without asserting a
    repr the client does not produce.
    """
    from trappoint_core.errors import diagnose  # the shipped client, not a local copy

    conn.autocommit = False
    bar = "=" * 78
    print()
    print(bar)
    print("BEAT 2 · THE REFUSAL AND THE BYPASS")
    print("SQLSTATE, message and constraint are the SERVER'S. The layout is this script's.")
    print("Every statement below is rolled back; the database is unchanged.")
    print(bar)

    print()
    print("s09 · OUR CLIENT · CALL mainline.merge_permit(...)")
    merge = probe_merge_refusal(conn, proof, found)
    print(f"    outcome     {merge.get('outcome')}")
    print(f"    SQLSTATE: {merge.get('sqlstate')}")
    print(f"    constraint: {merge.get('constraint') or '(no exhibit)'}")
    print(f"    source:     diag.constraint_name ({merge.get('constraint_source')})")
    ok = merge.get("sqlstate") == proof.CF01_SQLSTATE and merge.get("constraint") == (
        proof.CF01_EXHIBIT
    )

    print()
    print("s10 · RAW SQL AS CLUSTER ADMIN · the application bypassed entirely")
    print("    UPDATE mainline.permit SET state = 'merged'")
    print(f"      WHERE permit_id = '{found.permit_id}';")
    try:
        conn.execute(
            "UPDATE mainline.permit SET state = 'merged' WHERE permit_id = %s",
            (found.permit_id,),
        )
    except psycopg.Error as exc:
        conn.rollback()
        diagnosis = diagnose(exc)
        print(wrapped(proof._message(exc), indent="           ", first="    ERROR: "))
        print(f"    SQLSTATE: {proof._sqlstate(exc)}")
        print(f"    constraint: {diagnosis.constraint}   <- from diag.constraint_name")
        ok = ok and proof._sqlstate(exc) == "23514"
    else:
        conn.rollback()
        print("    !! the statement SUCCEEDED. The gate is not attached. Do not record.")
        ok = False
    print("    SELECT trappoint.explain_refusal(")
    print(f"      'permit', '{found.permit_id}', 'gate_closed_when_issued');")
    row = conn.execute(
        "SELECT trappoint.explain_refusal('permit', %s, 'gate_closed_when_issued')",
        (found.permit_id,),
    ).fetchone()
    conn.rollback()
    payload = row[0] if row else {}
    naa = payload.get("naa", {}) if isinstance(payload, dict) else {}
    print(f"    class:      {payload.get('class')}")
    print(f"    constraint: {payload.get('constraint')}")
    print(f"    mus:        {len(payload.get('mus', []))} obligation(s)")
    print(f"    naa:        {naa.get('kind')}")
    print(wrapped(str(naa.get("description")), indent="                "))

    print()
    print("s11 · RAW SQL AS CLUSTER ADMIN · the obligation is append-only")
    print("    DELETE FROM mainline.blocking_check")
    print(f"      WHERE permit_id = '{found.permit_id}';")
    try:
        conn.execute("DELETE FROM mainline.blocking_check WHERE permit_id = %s", (found.permit_id,))
    except psycopg.Error as exc:
        conn.rollback()
        print(f"    ERROR: {proof._message(exc)}")
        print(f"    SQLSTATE: {proof._sqlstate(exc)}")
        ok = ok and proof._sqlstate(exc) == "P0001"
    else:
        conn.rollback()
        print("    !! the DELETE SUCCEEDED. The append-only weld is missing. Do not record.")
        ok = False

    print()
    print("s12 · NOT RUN HERE. It is destructive and it is meant to be:")
    print("    ALTER TABLE mainline.permit DROP CONSTRAINT gate_closed_when_issued;")
    print("    Type it on camera. Then rebuild this database before the next take.")
    print(bar)
    return EXIT_OK if ok else EXIT_WRONG_STATE


def print_camera_block(found: Found, database: str) -> None:
    """The literal statements the camera films, with the seeded identifiers substituted.

    Copy-paste, not transcription. A UUID retyped on capture day is a take.
    """
    if found.permit_id is None:
        return
    print()
    print("ON-CAMERA SUBSTITUTIONS  (copy-paste; do not retype a UUID on capture day)")
    print(f"  database        {database}")
    print(f"  permit_id       {found.permit_id}")
    print(f"  check_id        {found.check_id}")
    print(f"  site_id         {found.site_id}")
    print()
    print("  s10  UPDATE mainline.permit SET state = 'merged'")
    print(f"         WHERE permit_id = '{found.permit_id}';")
    print("       SELECT trappoint.explain_refusal(")
    print(f"         'permit', '{found.permit_id}', 'gate_closed_when_issued');")
    print("  s11  DELETE FROM mainline.blocking_check")
    print(f"         WHERE permit_id = '{found.permit_id}';")
    print("  s12  ALTER TABLE mainline.permit DROP CONSTRAINT gate_closed_when_issued;")
    print("       ^ DESTRUCTIVE and deliberately so. Re-run this script afterwards.")


def main(argv: list[str] | None = None) -> int:  # noqa: PLR0915
    parser = argparse.ArgumentParser(
        prog="seed_demo_state",
        description=(
            "Put a database into exactly the state the first on-camera shot expects, and "
            "then prove it did. Primitives are imported from scripts/proof/gate_refusal.py."
        ),
    )
    parser.add_argument(
        "--dsn",
        default=os.environ.get("MAINLINE_TEST_DSN")
        or os.environ.get("TRAPPOINT_DSN")
        or os.environ.get("COCKROACH_URL")
        or os.environ.get("CRDB_URL")
        or os.environ.get("LOCAL_DSN")
        or DEFAULT_DSN,
        help=f"admin DSN (default: the running local node, {DEFAULT_DSN})",
    )
    parser.add_argument(
        "--database",
        default=DEFAULT_DATABASE,
        help=f"the demo database (default: {DEFAULT_DATABASE}); dropped and rebuilt unless "
        "--verify-only",
    )
    parser.add_argument("--migrations", type=Path, default=None, help="migration tree")
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="do not build anything; check the state that is already there",
    )
    parser.add_argument(
        "--camera",
        action="store_true",
        help=(
            "verify, then print beat 2 in the large labelled form a 1080p frame can read: "
            "the s09 client refusal, the s10 raw-SQL bypass with explain_refusal, and the "
            "s11 append-only refusal. Every statement is rolled back. Implies --verify-only"
        ),
    )
    parser.add_argument(
        "--gc-ttlseconds",
        type=int,
        default=4500,
        help="zone gc.ttlseconds for the demo database; 4500 is what Cloud enforces",
    )
    parser.add_argument(
        "--connect-timeout",
        type=int,
        default=10,
        help="seconds libpq waits per resolved address before trying the next one",
    )
    args = parser.parse_args(argv)
    if args.camera:
        args.verify_only = True

    root = repo_root()
    proof = load_proof(root)
    table = Table()

    admin_dsn = proof._rewrite_dsn(args.dsn, connect_timeout=args.connect_timeout)
    mode = "camera" if args.camera else "verify" if args.verify_only else "build"
    print(f"MAINLINE demo state - {args.database} - {mode}")
    print()

    try:
        if args.verify_only:
            if not database_present(admin_dsn, args.database):
                table.add(
                    "database",
                    False,
                    f"{args.database} does not exist on this cluster — run without "
                    "--verify-only to build it",
                    shots="all",
                )
                print(table.render())
                print()
                print(caveat(None))
                print()
                print("VERDICT  NOT READY - 1 check failed")
                return EXIT_WRONG_STATE
            table.add("database", True, f"{args.database} exists", required=False)
            dsn = proof._rewrite_dsn(
                args.dsn, database=args.database, connect_timeout=args.connect_timeout
            )
        else:
            dsn = build(args, proof, root, table)

        conn = psycopg.connect(dsn, autocommit=True)
    except psycopg.OperationalError as exc:
        print(
            f"seed_demo_state: could not reach the cluster: {proof._message(exc)}",
            file=sys.stderr,
        )
        return EXIT_USAGE

    try:
        found = verify(conn, proof, table)
        print(table.render())
        print()
        print(caveat(found.projection_trigger_present))

        failures = table.failures
        if failures:
            print()
            print(f"VERDICT  NOT READY - {len(failures)} check(s) failed:")
            for row in failures:
                print(f"  ! {row.check}: {row.observed}")
            print("  Do NOT record against this database.")
            return EXIT_WRONG_STATE

        # --camera runs ONLY after the table is green. Filming beat 2 out of a database
        # that did not verify is how a take gets to the timeline before anyone notices.
        if args.camera:
            code = run_camera(conn, proof, found)
            if code != EXIT_OK:
                print("VERDICT  NOT READY - beat 2 did not produce the expected refusals.")
                return code

        print_camera_block(found, args.database)
        print()
        print(f"VERDICT  READY - {len(table.rows)} checks, 0 failed. Roll camera.")
        return EXIT_OK
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
