#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Minimal reproduction for upstream finding F07, and for the three things that worked.

WHAT THIS PROGRAM DOES, IN PLAIN LANGUAGE
-----------------------------------------
It makes one throwaway database on a local CockroachDB node and asks it two sets
of questions.

The first set is a complaint. We once wrote a line of SQL that called one function
inside another, got it wrong, and the error message we got back named the OUTER
function -- the one that was fine -- rather than the inner one that was broken. We
went looking in the wrong place. This program writes that same mistake again and
prints the exact message, so anyone can see the misdirection for themselves.

The second set is praise, and it is measured the same way rather than asserted.
Three things about CockroachDB carried this product, and each one is checked here
with live SQL: a rule written into a table refuses a bad write on its own; the
strongest safety setting for concurrent work is already switched on before anyone
configures anything; and the error codes are exact enough to put on a screen.

Vocabulary, glossed once each:

    SQLSTATE          the five-character code a database returns with an error.
                      ``42883`` means "no function by that name takes those
                      argument types"; ``23514`` means "a CHECK rule refused it";
                      ``P0001`` means "a procedure refused it deliberately";
                      ``40001`` means "two transactions collided, ask again".
    CHECK constraint  a rule written into a table's own definition. The database
                      refuses any row that breaks it, whoever is writing.
    trigger           a small program stored in the database that the database
                      itself runs when a row changes. No application calls it.
    routine           a stored procedure or function living inside the database.
    SERIALIZABLE      the strongest isolation setting: concurrent transactions
                      are guaranteed to come out as if they had run one after
                      another, in some order.
    scratch database  a throwaway database made for one measurement and dropped
                      straight after.
    tier              which hosting plan a measurement was taken on. A local
                      single-node cluster and CockroachDB Cloud Basic are two
                      different exams, and a result on one is not claimed for the
                      other.

SAFETY
------
Local single-node CockroachDB only. This program refuses to run against any host
other than localhost/127.0.0.1 and refuses any database whose name contains
``mainline_demo``. It creates exactly one object outside itself -- the scratch
database -- and drops it in a ``finally`` block, printing both the create and the
drop. It creates no role. It makes no AWS call, reads no credential, writes no
parameter, and edits no product code, test, migration or seed.

USAGE
-----
    .venv/Scripts/python.exe scripts/upstream/repro_semantics_and_praise.py

Exit code 0 means every measurement was taken AND matched what the published
documents claim. Exit code 1 means reality moved and a published claim needs
revisiting -- which is the entire point of keeping this program.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

try:
    import psycopg
except ModuleNotFoundError:  # pragma: no cover - environment guard
    sys.stderr.write(
        "psycopg is required. Use the project interpreter:\n"
        "  .venv/Scripts/python.exe scripts/upstream/repro_semantics_and_praise.py\n"
    )
    raise SystemExit(2)

REPO_ROOT = Path(__file__).resolve().parents[2]

# `localhost` can resolve to ::1 on Windows, where a single-node CockroachDB
# listening on IPv4 never answers and the connect simply hangs. 127.0.0.1 is the
# same node, said unambiguously. (Measured while writing this script.)
DEFAULT_DSN = "postgresql://root@127.0.0.1:26257/defaultdb?sslmode=disable"

ALLOWED_HOSTS = {"localhost", "127.0.0.1", "::1", "[::1]"}
FORBIDDEN_DB_SUBSTRINGS = ("mainline_demo",)

# ---------------------------------------------------------------------------
# What the published documents claim. A re-run that disagrees exits 1.
# ---------------------------------------------------------------------------
EXPECTED_F07_VERDICT = "OUTER-NAME-ATTRIBUTION-CONFIRMED"


class Transcript:
    """An ordered, printable, JSON-serialisable record of every step taken."""

    def __init__(self) -> None:
        self.steps: list[dict[str, Any]] = []

    def record(
        self,
        what: str,
        *,
        sql: str | None = None,
        result: Any = None,
        error: str | None = None,
        note: str | None = None,
    ) -> dict[str, Any]:
        step = {
            "step": len(self.steps) + 1,
            "what": what,
            "sql": sql,
            "result": result,
            "error": error,
            "note": note,
        }
        self.steps.append(step)
        head = f"  [{step['step']:>2}] {what}"
        if sql:
            print(f"{head}\n       sql    {sql}")
        else:
            print(head)
        if error is not None:
            print(f"       ERROR  {error}")
        else:
            print(f"       ->     {result!r}")
        if note:
            print(f"       note   {note}")
        return step

    def for_json(self, only: set[int] | None = None) -> list[dict[str, Any]]:
        if only is None:
            return self.steps
        return [s for s in self.steps if s["step"] in only]


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------


def sqlstate_of(exc: Exception) -> str | None:
    return getattr(exc, "sqlstate", None) or getattr(getattr(exc, "diag", None), "sqlstate", None)


def constraint_of(exc: Exception) -> str | None:
    return getattr(getattr(exc, "diag", None), "constraint_name", None)


def first_line(exc: Exception) -> str:
    text = str(exc).strip()
    return text.splitlines()[0] if text else exc.__class__.__name__


def describe(exc: Exception) -> str:
    state = sqlstate_of(exc)
    return f"{state} {first_line(exc)}" if state else first_line(exc)


def guard_dsn(dsn: str) -> None:
    parts = urlsplit(dsn)
    host = (parts.hostname or "").lower()
    if host not in ALLOWED_HOSTS:
        raise SystemExit(
            f"refusing to run against host {host!r}: this reproduction is local-only "
            f"(allowed: {sorted(ALLOWED_HOSTS)})"
        )
    dbname = parts.path.lstrip("/").lower()
    for bad in FORBIDDEN_DB_SUBSTRINGS:
        if bad in dbname:
            raise SystemExit(f"refusing to run against database {dbname!r}")


def connect(dsn: str, *, autocommit: bool = True) -> "psycopg.Connection":
    return psycopg.connect(dsn, autocommit=autocommit, connect_timeout=15)


def scratch_dsn(dsn: str, dbname: str) -> str:
    parts = urlsplit(dsn)
    query = f"?{parts.query}" if parts.query else ""
    return f"{parts.scheme}://{parts.netloc}/{dbname}{query}"


def scalar(conn: "psycopg.Connection", sql: str, params: tuple = ()) -> Any:
    row = conn.execute(sql, params).fetchone()
    return None if row is None else row[0]


def attempt(conn: "psycopg.Connection", t: Transcript, what: str, sql: str, *, note: str | None = None) -> dict[str, Any]:
    """Run one statement and record whatever came back -- success or refusal.

    The error IS the measurement in most of this file, so an exception here is an
    ordinary outcome and never an abort.
    """
    try:
        cur = conn.execute(sql)
        rows = cur.fetchall() if cur.description is not None else None
        out = {"ok": True, "sqlstate": "00000", "rows": [[str(c) for c in r] for r in rows] if rows else None,
               "constraint": None, "message": None}
        t.record(what, sql=sql, result=out["rows"] if out["rows"] is not None else "ok", note=note)
    except Exception as exc:  # noqa: BLE001 - the refusal is the point
        out = {
            "ok": False,
            "sqlstate": sqlstate_of(exc),
            "rows": None,
            "constraint": constraint_of(exc) or None,
            "message": first_line(exc),
        }
        t.record(what, sql=sql, error=describe(exc), note=note)
    return out


# ---------------------------------------------------------------------------
# F07
# ---------------------------------------------------------------------------

# The two columns the original statement touched, with the types the product
# actually declares. `body` is text; `root_hash` is raw bytes. Written here as
# the product's own migration writes them, so the mistake below is the mistake
# we actually made rather than a re-imagining of it.
F07_FIXTURE = [
    (
        "create a table shaped like the one the original statement ran against",
        "CREATE TABLE checkpoint (id INT8 PRIMARY KEY, body STRING NOT NULL, root_hash BYTES NOT NULL)",
    ),
    (
        "put one row in it, with a three-line note in body",
        "INSERT INTO checkpoint VALUES (1, 'mainline/site' || chr(10) || '2' || chr(10) "
        "|| 'deadbeef' || chr(10), b'\\x01\\x02')",
    ),
]


def measure_f07(conn: "psycopg.Connection", t: Transcript) -> dict[str, Any]:
    """Which function does the error name when one call is nested inside another?"""

    print("\n-- F07 -- the error names the function that worked, not the one that did not\n")
    first = len(t.steps) + 1

    for what, sql in F07_FIXTURE:
        conn.execute(sql)
        t.record(what, sql=" ".join(sql.split()), result="ok")

    types = attempt(
        conn,
        t,
        "read the column types from the catalogue rather than assuming them",
        "SELECT column_name, data_type FROM information_schema.columns "
        "WHERE table_name = 'checkpoint' ORDER BY column_name",
        note="body is text and root_hash is bytea; the original comment says this was "
        "checked rather than assumed, and this is that check",
    )

    overloads = attempt(
        conn,
        t,
        "ask the database which argument types convert_from actually accepts",
        "SELECT p.proname || '(' || pg_catalog.pg_get_function_arguments(p.oid) || ')' "
        "FROM pg_proc p WHERE p.proname = 'convert_from'",
        note="one overload only: it takes raw bytes, so handing it text is our error and "
        "the database is right to refuse",
    )

    # --- the mistake, made bare ------------------------------------------------
    bare = attempt(
        conn,
        t,
        "THE MISTAKE, BARE: hand a text column to convert_from",
        "SELECT convert_from(checkpoint.body, 'utf8') FROM checkpoint",
        note="clear and correct: it names convert_from, which is the call that is wrong",
    )

    # --- the same mistake, nested ---------------------------------------------
    nested = attempt(
        conn,
        t,
        "THE FINDING: the identical mistake with split_part wrapped around it",
        "SELECT split_part(convert_from(checkpoint.body, 'utf8'), chr(10), 3) FROM checkpoint",
        note="same defect, same SQLSTATE, but the message now opens with the name of the "
        "function that resolved fine",
    )

    deeper = attempt(
        conn,
        t,
        "and one level deeper again, to see whether the outer names accumulate",
        "SELECT upper(split_part(convert_from(checkpoint.body, 'utf8'), chr(10), 3)) FROM checkpoint",
    )

    other_outer = attempt(
        conn,
        t,
        "a different outer function, to show the prefix is the caller and not split_part in particular",
        "SELECT length(convert_from(checkpoint.body, 'utf8')) FROM checkpoint",
    )

    other_inner = attempt(
        conn,
        t,
        "a different inner function, to show this is not about convert_from in particular",
        "SELECT split_part(encode(checkpoint.body, 'base64'), chr(10), 1) FROM checkpoint",
    )

    # --- the repair, and what the product actually ships ----------------------
    repair = attempt(
        conn,
        t,
        "the repair: give convert_from the bytes it asked for",
        "SELECT split_part(convert_from(checkpoint.body::BYTES, 'utf8'), chr(10), 3) FROM checkpoint",
    )
    shipped = attempt(
        conn,
        t,
        "what the product ships instead: no convert_from at all, because body is already text",
        "SELECT split_part(checkpoint.body, chr(10), 3) FROM checkpoint",
        note="verticals/mainline/db/seeds/demo/demo_world.sql:855",
    )

    # --- the two claims this run does NOT support -----------------------------
    print("\n  -- the same run, testing two claims the original note was read as making --\n")
    on_bytes = attempt(
        conn,
        t,
        "claim A: does convert_from's result need an explicit ::STRING before split_part accepts it?",
        "SELECT split_part(convert_from(checkpoint.root_hash, 'utf8'), chr(10), 3) FROM checkpoint",
        note="no cast anywhere in this statement; if it resolves, claim A does not hold",
    )
    typeof = attempt(
        conn,
        t,
        "claim A, asked directly: what type does convert_from say it returns?",
        "SELECT pg_typeof(convert_from(checkpoint.root_hash, 'utf8')) FROM checkpoint",
    )

    # ---- verdicts ------------------------------------------------------------
    nested_msg = (nested["message"] or "")
    bare_msg = (bare["message"] or "")
    attribution = (
        bare["sqlstate"] == "42883"
        and nested["sqlstate"] == "42883"
        and nested_msg.lower().startswith("split_part()")
        and not bare_msg.lower().startswith("split_part()")
        and "convert_from(string, string)" in nested_msg
    )
    verdict = "OUTER-NAME-ATTRIBUTION-CONFIRMED" if attribution else "NOT-REPRODUCED"
    why = (
        "the same defect reported two ways on one node: bare it says "
        f"{bare_msg!r}; nested inside split_part it says {nested_msg!r}"
        if attribution
        else "the two messages did not differ in the way the finding claims"
    )

    returned_type = (typeof["rows"] or [[None]])[0][0]
    claim_a_holds = not on_bytes["ok"]
    claim_a_note = (
        "does not hold: convert_from applied to a bytes column resolves inside split_part with "
        f"no cast at all, and reports its return type as {returned_type!r}"
        if not claim_a_holds
        else "holds: the uncast form was refused"
    )

    # Claim B, the local-versus-Cloud reading, is answered by the pair above:
    # the SAME node, the SAME version, the SAME statement shape -- one column
    # type fails and the other resolves. The variable is the column, not the
    # cluster.
    claim_b_note = (
        "does not hold as a platform difference: on this one node, the statement fails on a "
        "text column and resolves on a bytes column. The variable that changed between our "
        "two runs was the column type, which our own comment records "
        "(demo_world.sql:848-850, 'a scratch table written from memory made the same mistake')."
        if (not nested["ok"] and on_bytes["ok"])
        else "not answered by this run"
    )

    print(f"\n  F07 VERDICT: {verdict}\n    {why}")
    print(f"    claim A (an explicit ::STRING is required): {claim_a_note}")
    print(f"    claim B (local resolves, Cloud refuses):    {claim_b_note}\n")

    return {
        "verdict": verdict,
        "why": why,
        "column_types": types["rows"],
        "convert_from_overloads": overloads["rows"],
        "bare_call": bare,
        "nested_in_split_part": nested,
        "nested_two_deep": deeper,
        "nested_in_length": other_outer,
        "encode_instead_of_convert_from": other_inner,
        "repair_with_bytes_cast": repair,
        "what_the_product_ships": shipped,
        "claim_A_explicit_string_cast_required": {
            "holds": claim_a_holds,
            "note": claim_a_note,
            "uncast_on_bytes_column": on_bytes,
            "reported_return_type": returned_type,
        },
        "claim_B_local_versus_cloud_divergence": {
            "holds": False if (not nested["ok"] and on_bytes["ok"]) else None,
            "note": claim_b_note,
            "cloud_arm_re_run_today": False,
            "why_not_re_run": (
                "running this statement on CockroachDB Cloud means driving DDL or seeds at a "
                "shared live cluster, which the critique plan forbids (R4)"
            ),
        },
        "steps": sorted(range(first, len(t.steps) + 1)),
    }


# ---------------------------------------------------------------------------
# WHAT WORKED -- praise, measured
# ---------------------------------------------------------------------------

PRAISE_FIXTURE = [
    (
        "a table with one named rule written into its own definition",
        """CREATE TABLE subject (
             id            INT8 PRIMARY KEY,
             state         STRING NOT NULL DEFAULT 'open',
             open_blocking INT8   NOT NULL DEFAULT 0,
             CONSTRAINT demo_gate_closed_when_issued
               CHECK (state <> 'merged' OR open_blocking = 0))""",
    ),
    (
        "the rows the counter is supposed to be counting",
        "CREATE TABLE obligation (id INT8 PRIMARY KEY, subject_id INT8 NOT NULL, "
        "settled BOOL NOT NULL DEFAULT false)",
    ),
    (
        "a small program stored in the database that recounts them",
        """CREATE FUNCTION fn_demo_merge_gate() RETURNS TRIGGER LANGUAGE PLpgSQL AS $fn$
             DECLARE v_derived INT8;
             BEGIN
               SELECT count(*) INTO v_derived FROM obligation o
                WHERE o.subject_id = (NEW).id AND NOT o.settled;
               IF v_derived <> 0 AND (NEW).open_blocking = 0 THEN
                 RAISE EXCEPTION USING ERRCODE = 'P0001',
                   MESSAGE = 'DEMO: merge refused by fn_demo_merge_gate'
                             || ' - re-derived open obligation count is ' || v_derived::STRING
                             || ' while the projected counter reads zero';
               END IF;
               RETURN NEW;
             END $fn$""",
    ),
    (
        "weld it to the table, on the one transition it is about",
        """CREATE TRIGGER demo_merge_gate BEFORE UPDATE ON subject
             FOR EACH ROW WHEN ((NEW).state = 'merged' AND (OLD).state <> 'merged')
             EXECUTE FUNCTION fn_demo_merge_gate()""",
    ),
    ("one subject, not yet issued, with one thing outstanding", "INSERT INTO subject VALUES (1, 'open', 1)"),
    ("the outstanding thing itself", "INSERT INTO obligation VALUES (1, 1, false)"),
]

HONEST_WRITE = "UPDATE subject SET state = 'merged' WHERE id = 1"
FORGED_WRITE = "UPDATE subject SET state = 'merged', open_blocking = 0 WHERE id = 1"


def measure_praise_one(conn: "psycopg.Connection", t: Transcript) -> dict[str, Any]:
    """Does the database refuse the bad write by itself, with no application in the path?"""

    print("\n-- WORKED 1 -- the rule lives in the table, and the table is what refuses\n")
    first = len(t.steps) + 1

    for what, sql in PRAISE_FIXTURE:
        conn.execute(sql)
        t.record(what, sql=" ".join(sql.split()), result="ok")

    who = scalar(conn, "SELECT current_user")
    t.record(
        "who is writing",
        sql="SELECT current_user",
        result=who,
        note="a plain database client. No application code of ours is on this path -- the "
        "statements below are typed straight at the database",
    )

    honest = attempt(
        conn, t, "merge while the counter honestly reads 1", HONEST_WRITE,
        note="refused by the rule in the table definition",
    )
    forged = attempt(
        conn, t, "merge again with the counter forged to 0", FORGED_WRITE,
        note="the rule in the table is now satisfied; the stored program recounts and refuses",
    )

    create = attempt(
        conn,
        t,
        "the rule as anyone with a SQL prompt can read it back",
        "SELECT create_statement FROM [SHOW CREATE TABLE subject]",
    )

    # --- unwelding: take one mechanism away and try the same history again ----
    print("\n  -- take one mechanism away at a time and re-run the same illegal history --\n")
    conn.execute("DROP TRIGGER demo_merge_gate ON subject")
    t.record("drop the trigger, leaving only the rule in the table", sql="DROP TRIGGER demo_merge_gate ON subject", result="ok")
    without_trigger = attempt(conn, t, "merge honestly, with no trigger left", HONEST_WRITE)

    conn.execute(
        "CREATE TRIGGER demo_merge_gate BEFORE UPDATE ON subject FOR EACH ROW "
        "WHEN ((NEW).state = 'merged' AND (OLD).state <> 'merged') EXECUTE FUNCTION fn_demo_merge_gate()"
    )
    conn.execute("ALTER TABLE subject DROP CONSTRAINT demo_gate_closed_when_issued")
    t.record(
        "put the trigger back and drop the rule instead",
        sql="ALTER TABLE subject DROP CONSTRAINT demo_gate_closed_when_issued",
        result="ok",
    )
    without_check = attempt(conn, t, "merge with a forged counter, with no rule left", FORGED_WRITE)

    # restore, so the fixture is in a known state if anything is added later
    conn.execute(
        "ALTER TABLE subject ADD CONSTRAINT demo_gate_closed_when_issued "
        "CHECK (state <> 'merged' OR open_blocking = 0)"
    )

    ok = (
        honest["sqlstate"] == "23514"
        and honest["constraint"] == "demo_gate_closed_when_issued"
        and forged["sqlstate"] == "P0001"
        and without_trigger["sqlstate"] == "23514"
        and without_check["sqlstate"] == "P0001"
    )
    print(
        f"\n  WORKED 1: {'holds' if ok else 'DID NOT HOLD'} -- "
        f"honest write {honest['sqlstate']} on {honest['constraint']!r}; "
        f"forged write {forged['sqlstate']}; "
        f"trigger removed {without_trigger['sqlstate']}; rule removed {without_check['sqlstate']}\n"
    )

    return {
        "holds": ok,
        "writer": who,
        "honest_write_refused_by_the_rule": honest,
        "forged_write_refused_by_the_stored_program": forged,
        "rule_as_shown_by_the_database": (create["rows"] or [[None]])[0][0],
        "with_the_trigger_removed": without_trigger,
        "with_the_rule_removed": without_check,
        "scope": (
            "This is a four-table toy inside a scratch database. It shows what the platform "
            "gives you. It is NOT the product's structural-redundancy claim, which is made in "
            "exactly one place -- packages/trappoint-conformance/unweld/harness.py -- and "
            "nowhere else, per spec section 3.2."
        ),
        "steps": sorted(range(first, len(t.steps) + 1)),
    }


def measure_praise_two(dsn: str, t: Transcript) -> dict[str, Any]:
    """Is the strongest isolation level already on, before anyone configures anything?"""

    print("\n-- WORKED 2 -- the strongest setting is the one you get without asking\n")
    first = len(t.steps) + 1

    fresh = connect(dsn)
    try:
        default_level = scalar(fresh, "SHOW default_transaction_isolation")
        t.record(
            "first statement on a brand-new connection: what is the default?",
            sql="SHOW default_transaction_isolation",
            result=default_level,
            note="no SET was issued on this connection before this statement",
        )
    finally:
        fresh.close()

    txn = connect(dsn, autocommit=False)
    in_txn: Any
    try:
        with txn.cursor() as cur:
            cur.execute("SHOW transaction_isolation")
            in_txn = cur.fetchone()[0]
        t.record(
            "and inside an explicit transaction where we still issued no SET",
            sql="BEGIN; SHOW transaction_isolation",
            result=in_txn,
        )
        txn.rollback()
    finally:
        txn.close()

    # A collision, best effort. If the node is busy this may not land; a miss is
    # recorded as a miss and never dressed up.
    collision: dict[str, Any] = {"attempted": True, "sqlstate": None, "note": None}
    a = connect(dsn, autocommit=False)
    b = connect(dsn, autocommit=False)
    try:
        with a.cursor() as ca, b.cursor() as cb:
            ca.execute("SET statement_timeout = '20s'")
            cb.execute("SET statement_timeout = '20s'")
            ca.execute("SELECT count(*) FROM obligation")
            cb.execute("SELECT count(*) FROM obligation")
            ca.execute("INSERT INTO obligation VALUES (900, 1, true)")
            a.commit()
            try:
                cb.execute("INSERT INTO obligation VALUES (901, 1, true)")
                b.commit()
                collision.update(sqlstate="00000", note="both transactions committed; no conflict arose this run")
            except Exception as exc:  # noqa: BLE001
                collision.update(sqlstate=sqlstate_of(exc), note=first_line(exc))
                b.rollback()
        t.record(
            "two transactions racing on the same rows, to see what a collision is called",
            sql="two sessions: read, read, write, commit, write, commit",
            result=collision,
            note="40001 is the code the retry loop retries, and the only one it retries "
            "(packages/trappoint-core/src/trappoint_core/retry.py:173)",
        )
    finally:
        try:
            a.rollback()
        finally:
            a.close()
        try:
            b.rollback()
        finally:
            b.close()

    ok = str(default_level).lower() == "serializable" and str(in_txn).lower() == "serializable"
    print(
        f"\n  WORKED 2: {'holds' if ok else 'DID NOT HOLD'} -- default {default_level!r}, "
        f"inside a transaction {in_txn!r}, collision reported as {collision['sqlstate']!r}\n"
    )

    return {
        "holds": ok,
        "default_transaction_isolation": default_level,
        "transaction_isolation_inside_an_untouched_transaction": in_txn,
        "collision_probe": collision,
        "scope": (
            "This says the strongest level is the default and cost nothing to obtain. It does "
            "NOT say the level is what makes our gate correct: docs/architecture/"
            "01-the-mechanism.md:269-274 records that the gate stays welded at READ COMMITTED, "
            "because the conflict is materialised in a row rather than inferred."
        ),
        "steps": sorted(range(first, len(t.steps) + 1)),
    }


def measure_praise_three(t: Transcript, one: dict[str, Any]) -> dict[str, Any]:
    """Are the codes exact enough to put on a screen as evidence?"""

    print("\n-- WORKED 3 -- the codes are exact, and one of them carries a name\n")
    first = len(t.steps) + 1

    honest = one["honest_write_refused_by_the_rule"]
    forged = one["forged_write_refused_by_the_stored_program"]

    t.record(
        "the rule's refusal, as the driver hands it over",
        result={
            "sqlstate": honest["sqlstate"],
            "constraint_name_field": honest["constraint"],
            "message_text": honest["message"],
        },
        note="the NAME arrives in its own field. The message text does not contain it -- it "
        "carries the expanded expression instead, which is why our code reads the field and "
        "never parses the message "
        "(verticals/mainline/apps/demo-api/src/mainline_demo_api/refusal.py:184-197)",
    )
    t.record(
        "the stored program's refusal, as the driver hands it over",
        result={
            "sqlstate": forged["sqlstate"],
            "constraint_name_field": forged["constraint"],
            "message_text": forged["message"],
        },
        note="no constraint name, because there is no constraint. That absence is why our own "
        "RAISE writes 'refused by <schema>.<function>' into the message and treats the function "
        "name as the exhibit "
        "(verticals/mainline/db/migrations/0115_fn_permit_merge_gate.sql:38-42)",
    )

    named_by_code = honest["sqlstate"] == "23514" and bool(honest["constraint"])
    unnamed_by_design = forged["sqlstate"] == "P0001" and not forged["constraint"]
    ok = named_by_code and unnamed_by_design

    print(
        f"\n  WORKED 3: {'holds' if ok else 'DID NOT HOLD'} -- 23514 arrives carrying "
        f"{honest['constraint']!r}; P0001 arrives carrying {forged['constraint']!r}\n"
    )

    return {
        "holds": ok,
        "check_refusal_carries_its_name": named_by_code,
        "procedure_refusal_carries_no_name": unnamed_by_design,
        "codes_this_product_puts_on_screen": {
            "23514 / gate_closed_when_issued": "verticals/mainline/db/migrations/0050_permit.sql:114",
            "23514 / cr_gate_closed_when_merged": "verticals/mainline/db/migrations/0051_change_request.sql:85",
            "P0001 / mainline.fn_permit_merge_gate": "verticals/mainline/db/migrations/0115_fn_permit_merge_gate.sql:44",
            "P0001 / mainline.fn_cr_merge_gate": "verticals/mainline/db/migrations/0116_fn_cr_merge_gate.sql:44",
            "42501 on a privilege refusal": (
                "not reproduced by this program -- it needs a second database user, and this "
                "program creates nothing outside its one scratch database. Reproduced live by "
                "scripts/upstream/repro_privileges.py; the transcript is in "
                "evidence/upstream/F01-has-function-privilege.json. Named as a constant at "
                "verticals/mainline/apps/demo-api/src/mainline_demo_api/cr_gate_run.py:222"
            ),
        },
        "where_they_go_on_screen": (
            "verticals/mainline/apps/console/src/design/primitives/Sqlstate.tsx:36-58"
        ),
        "steps": sorted(range(first, len(t.steps) + 1)),
    }


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def write_evidence(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=False, default=str) + "\n", encoding="utf-8")
    print(f"  wrote {path}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dsn", default=os.environ.get("UPSTREAM_REPRO_DSN", DEFAULT_DSN))
    ap.add_argument("--evidence-dir", default=str(REPO_ROOT / "evidence" / "upstream"))
    args = ap.parse_args()

    guard_dsn(args.dsn)

    suffix = secrets.token_hex(4)
    dbname = f"upstream_f07_{suffix}"
    started = datetime.now(timezone.utc)

    t = Transcript()
    admin = connect(args.dsn)
    version = scalar(admin, "SELECT version()")

    print("=" * 78)
    print("F07 REPRODUCTION, AND THE THREE THINGS THAT WORKED")
    print("=" * 78)
    print(f"  node        {version}")
    print(f"  tier        local single-node CockroachDB CCL")
    print(f"  started     {started.isoformat()}")
    print(f"  CREATED DB  {dbname}")

    scratch = None
    exit_code = 0
    summary: dict[str, Any] = {}
    try:
        admin.execute(f"CREATE DATABASE {dbname}")
        t.record(
            "create the scratch database everything below lives inside",
            sql=f"CREATE DATABASE {dbname}",
            result="ok",
            note="a scratch database is a throwaway database made for one measurement and "
            "dropped straight after; this one is dropped in a finally block",
        )

        target = scratch_dsn(args.dsn, dbname)
        scratch = connect(target)

        f07 = measure_f07(scratch, t)
        one = measure_praise_one(scratch, t)
        two = measure_praise_two(target, t)
        three = measure_praise_three(t, one)

        stamp = {
            "measured_on": "local single-node CockroachDB CCL",
            "server_version": version,
            "client": f"psycopg {psycopg.__version__}",
            "host_os": f"{platform.system()} {platform.release()}",
            "measured_at_utc": started.isoformat(),
            "scratch_database_created": dbname,
            "scratch_roles_created": [],
            "script": "scripts/upstream/repro_semantics_and_praise.py",
        }

        ev = Path(args.evidence_dir)
        write_evidence(
            ev / "F07-convert-from-untyped.json",
            {
                "finding": "F07",
                "title": (
                    "a nested call that cannot be resolved is reported under the name of the "
                    "function that could"
                ),
                "label": "REPRODUCED-TODAY",
                **stamp,
                "measurement": f07,
                "transcript": t.for_json(set(f07["steps"])),
            },
        )
        write_evidence(
            ev / "WHAT-WORKED.json",
            {
                "document": "docs/upstream/WHAT-WORKED.md",
                "label": "REPRODUCED-TODAY",
                **stamp,
                "entry_1_rule_and_trigger_in_the_database": one,
                "entry_2_serializable_by_default": two,
                "entry_3_precise_sqlstates": three,
                "transcript": t.for_json(set(one["steps"]) | set(two["steps"]) | set(three["steps"])),
            },
        )

        summary = {
            "f07": f07["verdict"],
            "worked_1_rule_and_trigger": one["holds"],
            "worked_2_serializable_default": two["holds"],
            "worked_3_precise_codes": three["holds"],
        }

        print("\n" + "=" * 78)
        print("VERDICTS")
        print("=" * 78)
        print(f"  F07      observed {f07['verdict']:<32} published finding claims {EXPECTED_F07_VERDICT}")
        print(f"  WORKED 1 rule and trigger refuse on their own      {one['holds']}")
        print(f"  WORKED 2 SERIALIZABLE is the default               {two['holds']}")
        print(f"  WORKED 3 the codes are exact and one is named      {three['holds']}")

        if f07["verdict"] != EXPECTED_F07_VERDICT:
            print("\n  MISMATCH: F07 no longer reproduces. Re-label it or withdraw it.")
            exit_code = 1
        elif not (one["holds"] and two["holds"] and three["holds"]):
            print("\n  MISMATCH: a praise entry no longer measures true. Fix the document.")
            exit_code = 1
        else:
            print("\n  OK: the finding still reproduces and all three praise entries still measure true.")
    finally:
        if scratch is not None:
            scratch.close()
        admin.execute(f"DROP DATABASE IF EXISTS {dbname} CASCADE")
        print(f"  DROPPED DB  {dbname}")
        left = scalar(
            admin,
            "SELECT count(*) FROM [SHOW DATABASES] WHERE database_name = %s",
            (dbname,),
        )
        print(f"  scratch databases left behind by this run: {left}")
        print("  scratch roles created by this run: 0")
        admin.close()

    print(json.dumps(summary, indent=2))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
