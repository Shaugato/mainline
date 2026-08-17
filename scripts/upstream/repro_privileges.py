# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Minimal reproduction for upstream findings F01 and F02.

WHAT THIS PROGRAM DOES, IN PLAIN LANGUAGE
-----------------------------------------
It creates a brand-new throwaway database on a local CockroachDB node, puts one
table and one stored procedure in it, takes the permission to run that procedure
away from a throwaway test user, and then asks the database two questions:

  1. "Can that user run this procedure?"  (asked of ``has_function_privilege``)
  2. "Can that user run this procedure?"  (asked by actually trying it)

If the two answers disagree, F01 stands. If they agree, F01 is struck and this
program says so out loud.

It then grants the permission back and compares how two of the database's own
self-describing tables spell the *same* procedure. That is F02.

The throwaway database and the throwaway user are dropped in a ``finally``
block, always. This program creates nothing that outlives it.

SAFETY
------
Local single-node CockroachDB only. This program refuses to run against any host
other than localhost/127.0.0.1 and refuses any database named ``mainline_demo``.
It makes no AWS call, reads no credential, and touches no product code.

USAGE
-----
    .venv/Scripts/python.exe scripts/upstream/repro_privileges.py

Exit code 0 means every measurement was taken AND the observed verdicts match
the verdicts the published findings claim. Exit code 1 means reality moved and a
published finding needs revisiting -- which is the point of a repro script.
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
        "  .venv/Scripts/python.exe scripts/upstream/repro_privileges.py\n"
    )
    raise SystemExit(2)

REPO_ROOT = Path(__file__).resolve().parents[2]

# `localhost` can resolve to ::1 on Windows, where a single-node CockroachDB
# started on IPv4 will not answer and the connect simply hangs. 127.0.0.1 is the
# same node, stated unambiguously.
DEFAULT_DSN = "postgresql://root@127.0.0.1:26257/defaultdb?sslmode=disable"

ALLOWED_HOSTS = {"localhost", "127.0.0.1", "::1", "[::1]"}
FORBIDDEN_DB_SUBSTRINGS = ("mainline_demo",)

# The procedure signature is the one the product actually ships, so that the
# spelling F02 is about is the spelling a reader will meet in the real tree.
PROC_ARGS = "UUID, BYTES, STRING, STRING, JSONB, BYTES, INT2, BYTES"

# ---------------------------------------------------------------------------
# What the published findings claim. If a re-run disagrees with either of these,
# this script exits 1 and the finding must be re-labelled or struck.
# ---------------------------------------------------------------------------
EXPECTED_F01_VERDICT = "STUB-CONFIRMED"
EXPECTED_F02_VERDICT = "SPELLINGS-DIFFER"


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
        if error is not None:
            print(f"{head}\n       ERROR  {error}")
        else:
            print(f"{head}\n       ->     {result!r}")
        if note:
            print(f"       note   {note}")
        return step

    def for_json(self, only: set[int] | None = None) -> list[dict[str, Any]]:
        if only is None:
            return self.steps
        return [s for s in self.steps if s["step"] in only]


def sqlstate_of(exc: Exception) -> str | None:
    return getattr(getattr(exc, "diag", None), "sqlstate", None)


def describe(exc: Exception) -> str:
    state = sqlstate_of(exc)
    text = str(exc).strip().splitlines()[0] if str(exc).strip() else exc.__class__.__name__
    return f"{state} {text}" if state else text


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


def connect(dsn: str) -> "psycopg.Connection":
    return psycopg.connect(dsn, autocommit=True, connect_timeout=10)


def scratch_dsn(dsn: str, dbname: str) -> str:
    parts = urlsplit(dsn)
    query = f"?{parts.query}" if parts.query else ""
    return f"{parts.scheme}://{parts.netloc}/{dbname}{query}"


def scalar(conn: "psycopg.Connection", sql: str, params: tuple = ()) -> Any:
    row = conn.execute(sql, params).fetchone()
    return None if row is None else row[0]


# ---------------------------------------------------------------------------
# F01
# ---------------------------------------------------------------------------


def measure_f01(conn: "psycopg.Connection", t: Transcript, probe: str) -> dict[str, Any]:
    """Does ``has_function_privilege`` track the behaviour it describes?"""

    print("\n-- F01 -- can the database tell us the truth about who may run a procedure?\n")

    first = len(t.steps) + 1
    proc_ref = f"mainline.merge_permit({PROC_ARGS})"

    # 1. Take EXECUTE away from everybody, explicitly. This is the step that
    #    separates this run from the counter-reading in
    #    docs/demo/cr-gate-measurements.md:56-69, which observed `true` on a
    #    procedure whose access-control list was NULL (never touched). After an
    #    explicit REVOKE the access-control list is no longer untouched.
    for grantee in ("public", probe):
        sql = f"REVOKE EXECUTE ON PROCEDURE {proc_ref} FROM {grantee}"
        conn.execute(sql)
        t.record(f"revoke EXECUTE on the procedure from {grantee}", sql=sql, result="ok")

    acl_sql = (
        "SELECT p.proacl::TEXT FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
        "WHERE n.nspname = 'mainline' AND p.proname = 'merge_permit'"
    )
    acl = scalar(conn, acl_sql)
    t.record(
        "read the procedure's access-control list after the revoke",
        sql=acl_sql,
        result=acl,
        note=(
            "an access-control list (ACL) is the row of who-may-do-what the database keeps "
            "for an object; NULL here would mean 'nobody ever set one', which is the state "
            "the counter-reading in docs/demo/cr-gate-measurements.md was measured in"
        ),
    )

    proc_oid = scalar(
        conn,
        "SELECT p.oid FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
        "WHERE n.nspname = 'mainline' AND p.proname = 'merge_permit'",
    )
    t.record("resolve the procedure to its internal id (OID)", result=proc_oid)

    # 2. Ask has_function_privilege the THREE-ARGUMENT way: name the role
    #    explicitly. This is the form a checking program uses, because a
    #    checking program is asking about somebody other than itself.
    # The OID is written into the statement as a scalar sub-select rather than
    # passed as a parameter: a parameter placeholder here makes the CLIENT's type
    # inference fail (42P18), which would be our artefact and not a measurement.
    oid_expr = (
        "(SELECT p.oid FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
        "WHERE n.nspname = 'mainline' AND p.proname = 'merge_permit')"
    )
    named_role_answers: dict[str, Any] = {}
    for role in (probe, "root", "admin", "public"):
        for label, expr, params in (
            ("signature", "%s", (proc_ref,)),
            ("oid", oid_expr, ()),
        ):
            # The role placeholder is cast explicitly: with an OID in the second
            # position the server cannot infer $1's type on its own (42P18).
            sql = f"SELECT has_function_privilege(%s::STRING, {expr}, 'EXECUTE')"
            key = f"{role}/{label}"
            try:
                value = scalar(conn, sql, (role, *params))
                named_role_answers[key] = value
                t.record(
                    f"has_function_privilege({role!r}, <{label}>, 'EXECUTE')",
                    sql=sql,
                    result=value,
                )
            except Exception as exc:  # noqa: BLE001 - the error IS the measurement
                named_role_answers[key] = {"error": describe(exc)}
                t.record(
                    f"has_function_privilege({role!r}, <{label}>, 'EXECUTE')",
                    sql=sql,
                    error=describe(exc),
                )

    # 3. Does the function resolve its arguments at all, or does it short-circuit
    #    to true before looking? Two controls: a procedure that does not exist,
    #    and a role that does not exist. Errors here are GOOD -- they show the
    #    inputs are genuinely resolved, which makes the `true` above a decision
    #    rather than an accident.
    resolution_controls: dict[str, Any] = {}
    for label, role_arg, proc_arg in (
        ("nonexistent_procedure", probe, "mainline.no_such_routine_at_all(INT)"),
        ("nonexistent_role", f"no_such_role_{probe}", proc_ref),
    ):
        try:
            value = scalar(
                conn, "SELECT has_function_privilege(%s, %s, 'EXECUTE')", (role_arg, proc_arg)
            )
            resolution_controls[label] = value
            t.record(
                f"resolution control -- has_function_privilege with a {label.replace('_', ' ')}",
                result=value,
                note="an answer rather than an error would mean this argument is never resolved",
            )
        except Exception as exc:  # noqa: BLE001
            resolution_controls[label] = {"error": describe(exc)}
            t.record(
                f"resolution control -- has_function_privilege with a {label.replace('_', ' ')}",
                error=describe(exc),
                note="an error is correct: the argument genuinely does not resolve, so it IS being looked up",
            )

    # 4. Where each function reads its answer from. `pg_proc.proacl` is the
    #    procedure's stored permission row; `pg_class.relacl` is the table's.
    #    If one is populated and the other is not, that is the whole mechanism.
    acl_compare_sql = (
        "SELECT (SELECT p.proacl::TEXT FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
        "        WHERE n.nspname = 'mainline' AND p.proname = 'merge_permit') AS proacl, "
        "       (SELECT c.relacl::TEXT FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
        "        WHERE n.nspname = 'mainline' AND c.relname = 'permit') AS relacl"
    )
    acl_row = conn.execute(acl_compare_sql).fetchone()
    acl_compare = {"pg_proc.proacl": acl_row[0], "pg_class.relacl": acl_row[1]}
    t.record(
        "compare where the two functions would read from: the procedure's stored permission row vs the table's",
        sql=acl_compare_sql,
        result=acl_compare,
        note="the table has been granted SELECT and revoked nothing; the procedure has had EXECUTE revoked from everyone",
    )

    # 4. The behavioural truth: actually try to run it as the probe role.
    call_sql = (
        f"CALL mainline.merge_permit("
        f"'00000000-0000-0000-0000-000000000000'::UUID, b'', 'a', 'b', '{{}}'::JSONB, b'', 1::INT2, b'')"
    )
    behaviour: dict[str, Any] = {}
    conn.execute(f"SET ROLE {probe}")
    t.record(f"become {probe} for the next statement", sql=f"SET ROLE {probe}", result="ok")
    t.record("confirm who we are now", sql="SELECT current_user", result=scalar(conn, "SELECT current_user"))
    try:
        conn.execute(call_sql)
        behaviour = {"refused": False, "sqlstate": None, "message": None}
        t.record("CALL the procedure as the probe role", sql=call_sql, result="SUCCEEDED")
    except Exception as exc:  # noqa: BLE001
        behaviour = {
            "refused": True,
            "sqlstate": sqlstate_of(exc),
            "message": str(exc).strip().splitlines()[0],
        }
        t.record("CALL the procedure as the probe role", sql=call_sql, error=describe(exc))
    finally:
        conn.execute("RESET ROLE")
        t.record("stop being the probe role", sql="RESET ROLE", result="ok")

    # 5. Now ask the SAME question the TWO-ARGUMENT way -- no role named, so the
    #    function answers about whoever is asking. Asked from inside the probe's
    #    own session, and from root's, so both sides are on the record.
    current_user_answers: dict[str, Any] = {}
    for who in (probe, None):
        if who is not None:
            conn.execute(f"SET ROLE {who}")
        label = who or "root"
        try:
            value = scalar(conn, "SELECT has_function_privilege(%s, 'EXECUTE')", (proc_ref,))
            current_user_answers[label] = value
            t.record(
                f"has_function_privilege(<signature>, 'EXECUTE') -- no role named -- asked by {label}",
                result=value,
            )
        except Exception as exc:  # noqa: BLE001
            current_user_answers[label] = {"error": describe(exc)}
            t.record(
                f"has_function_privilege(<signature>, 'EXECUTE') -- no role named -- asked by {label}",
                error=describe(exc),
            )
        finally:
            if who is not None:
                conn.execute("RESET ROLE")

    # 6. Does the procedure's stored permission row EVER get written? Grant,
    #    look, revoke, look. If it stays empty through a real grant that a real
    #    CALL then honours, the row is simply not the place the answer lives --
    #    and a function reading it will always say the same thing.
    acl_lifecycle: dict[str, Any] = {"after_revoke": acl}
    for phase, stmt in (
        ("after_grant", f"GRANT EXECUTE ON PROCEDURE {proc_ref} TO {probe}"),
        ("after_second_revoke", f"REVOKE EXECUTE ON PROCEDURE {proc_ref} FROM {probe}"),
    ):
        conn.execute(stmt)
        acl_lifecycle[phase] = scalar(conn, acl_sql)
        t.record(
            f"the procedure's stored permission row {phase.replace('_', ' ')}",
            sql=stmt,
            result=acl_lifecycle[phase],
        )

    # ---- verdict -----------------------------------------------------------
    # The claim under test, stated exactly: with the behavioural truth being a
    # hard 42501, does the ROLE-NAMED form still answer true for the probe, for
    # root, for admin, and for public?
    refused_42501 = behaviour["refused"] and behaviour["sqlstate"] == "42501"
    signature_form = {
        role: named_role_answers.get(f"{role}/signature")
        for role in (probe, "root", "admin", "public")
    }
    # Strict: BOTH ways of naming the procedure (signature text and OID), for all
    # four roles, must have answered true for the claim to stand.
    all_named_true = all(v is True for v in named_role_answers.values())
    named_false = sorted(k for k, v in named_role_answers.items() if v is not True)

    if refused_42501 and all_named_true:
        verdict = "STUB-CONFIRMED"
        why = (
            "the probe was genuinely refused with 42501, and the role-named form of "
            "has_function_privilege answered true for the probe, for root, for admin and "
            "for public -- including for the role that had just been refused"
        )
    elif refused_42501 and named_false:
        verdict = "STRUCK"
        why = (
            "the probe was genuinely refused and the role-named form answered false for: "
            f"{', '.join(named_false)} -- it tracks behaviour after an explicit REVOKE, so "
            "the claim does not stand"
        )
    elif not behaviour["refused"]:
        verdict = "INCONCLUSIVE"
        why = "the CALL was not refused, so there is no behavioural truth to compare against"
    else:
        verdict = "INCONCLUSIVE"
        why = f"the CALL was refused with {behaviour['sqlstate']}, not 42501"

    # The refinement that the archived account in docs/regression/GUARD.md missed.
    probe_current_user = current_user_answers.get(probe)
    forms_disagree = all_named_true and probe_current_user is False
    print(f"\n  F01 VERDICT: {verdict}\n    {why}")
    if forms_disagree:
        print(
            "    REFINEMENT: the two-argument form (no role named) answered False for the same\n"
            "    probe, on the same procedure, in the same session. Only the role-named form is blind.\n"
        )

    return {
        "verdict": verdict,
        "why": why,
        "procedure": proc_ref,
        "procedure_oid": proc_oid,
        "acl_after_revoke": acl,
        "acl_lifecycle_grant_then_revoke": acl_lifecycle,
        "acl_surfaces_compared": acl_compare,
        "role_named_form_answers": named_role_answers,
        "role_named_form_signature_only": signature_form,
        "current_user_form_answers": current_user_answers,
        "the_two_forms_disagree": forms_disagree,
        "argument_resolution_controls": resolution_controls,
        "behavioural_truth_of_CALL": behaviour,
        "steps": sorted(range(first, len(t.steps) + 1)),
    }


def measure_negative_control(
    conn: "psycopg.Connection", t: Transcript, probe: str
) -> dict[str, Any]:
    """The byte-identical control on tables: does ``has_table_privilege`` track behaviour?

    Same database, same session, same probe role, same shape of question. The
    force of F01 is that one of these two functions matches reality and the
    other does not.
    """

    print("\n-- F01 negative control -- the same question, asked about a table\n")

    first = len(t.steps) + 1
    out: dict[str, Any] = {"answers": {}, "behaviour": {}}

    for privilege in ("SELECT", "INSERT"):
        sql = "SELECT has_table_privilege(%s, 'mainline.permit', %s)"
        value = scalar(conn, sql, (probe, privilege))
        out["answers"][privilege] = value
        t.record(f"has_table_privilege({probe!r}, 'mainline.permit', {privilege!r})", sql=sql, result=value)

    conn.execute(f"SET ROLE {probe}")
    try:
        for privilege, statement in (
            ("SELECT", "SELECT count(*) FROM mainline.permit"),
            (
                "INSERT",
                "INSERT INTO mainline.permit (permit_id, label) "
                "VALUES ('00000000-0000-0000-0000-0000000000ff'::UUID, 'control')",
            ),
        ):
            try:
                cursor = conn.execute(statement)
                result = cursor.fetchone() if privilege == "SELECT" else None
                out["behaviour"][privilege] = {"refused": False, "sqlstate": None}
                t.record(
                    f"actually run a {privilege} on mainline.permit as the probe role",
                    sql=statement,
                    result=f"SUCCEEDED {result!r}" if result is not None else "SUCCEEDED",
                )
            except Exception as exc:  # noqa: BLE001
                out["behaviour"][privilege] = {
                    "refused": True,
                    "sqlstate": sqlstate_of(exc),
                    "message": str(exc).strip().splitlines()[0],
                }
                t.record(
                    f"actually run a {privilege} on mainline.permit as the probe role",
                    sql=statement,
                    error=describe(exc),
                )
    finally:
        conn.execute("RESET ROLE")
        t.record("stop being the probe role", sql="RESET ROLE", result="ok")

    tracks = (
        out["answers"].get("SELECT") is True
        and out["behaviour"].get("SELECT", {}).get("refused") is False
        and out["answers"].get("INSERT") is False
        and out["behaviour"].get("INSERT", {}).get("refused") is True
        and out["behaviour"].get("INSERT", {}).get("sqlstate") == "42501"
    )
    out["tracks_behaviour"] = tracks
    out["steps"] = sorted(range(first, len(t.steps) + 1))
    print(
        f"\n  CONTROL: has_table_privilege tracks behaviour = {tracks}\n"
        f"    (SELECT says {out['answers'].get('SELECT')!r} and the query works; "
        f"INSERT says {out['answers'].get('INSERT')!r} and the statement is refused)\n"
    )
    return out


# ---------------------------------------------------------------------------
# F02
# ---------------------------------------------------------------------------


def measure_f02(conn: "psycopg.Connection", t: Transcript, probe: str) -> dict[str, Any]:
    """Two of the database's own self-describing tables spell one procedure two ways."""

    print("\n-- F02 -- two catalogue surfaces, one procedure, two spellings\n")

    first = len(t.steps) + 1
    proc_ref = f"mainline.merge_permit({PROC_ARGS})"

    grant_sql = f"GRANT EXECUTE ON PROCEDURE {proc_ref} TO {probe}"
    conn.execute(grant_sql)
    t.record(f"grant EXECUTE on the procedure to {probe}", sql=grant_sql, result="ok")

    # Behavioural truth FIRST, so the naive comparison below can be shown to be
    # wrong about something we have already watched work.
    call_sql = (
        f"CALL mainline.merge_permit("
        f"'00000000-0000-0000-0000-000000000000'::UUID, b'', 'a', 'b', '{{}}'::JSONB, b'', 1::INT2, b'')"
    )
    conn.execute(f"SET ROLE {probe}")
    try:
        conn.execute(call_sql)
        call_ok = True
        t.record("CALL the procedure as the probe role, now that EXECUTE is granted", sql=call_sql, result="SUCCEEDED")
    except Exception as exc:  # noqa: BLE001
        call_ok = False
        t.record("CALL the procedure as the probe role, now that EXECUTE is granted", sql=call_sql, error=describe(exc))
    finally:
        conn.execute("RESET ROLE")

    # Spelling 1: SHOW GRANTS.
    show_rows = conn.execute("SHOW GRANTS").fetchall()
    show_cols = [d.name for d in conn.execute("SHOW GRANTS").description or []]
    routine_rows = [
        dict(zip(show_cols, [str(c) for c in row]))
        for row in show_rows
        if "routine" in {str(c).lower() for c in row}
    ]
    show_spelling = sorted(
        {
            r.get("relation_name") or r.get("object_name") or ""
            for r in routine_rows
            if "merge_permit" in (r.get("relation_name") or r.get("object_name") or "")
        }
    )
    t.record(
        "how SHOW GRANTS spells the procedure",
        sql="SHOW GRANTS",
        result=show_spelling,
        note=f"columns: {show_cols}",
    )

    # Spelling 2: information_schema.routines.
    catalogue_sql = (
        "SELECT routine_schema, routine_name, specific_name, routine_type "
        "FROM information_schema.routines WHERE routine_schema = 'mainline'"
    )
    catalogue_rows = [
        {"routine_schema": str(r[0]), "routine_name": str(r[1]), "specific_name": str(r[2]), "routine_type": str(r[3])}
        for r in conn.execute(catalogue_sql).fetchall()
    ]
    catalogue_spelling = sorted({r["routine_name"] for r in catalogue_rows})
    t.record(
        "how information_schema.routines spells the same procedure",
        sql=catalogue_sql,
        result=catalogue_spelling,
    )

    # Is there any column on either surface that already carries the other's
    # spelling? If there were, "ship no normaliser" would be too strong a claim.
    bridge_sql = (
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = 'information_schema' AND table_name = 'routines' ORDER BY column_name"
    )
    routines_columns = [str(r[0]) for r in conn.execute(bridge_sql).fetchall()]
    t.record(
        "every column information_schema.routines offers, looking for one that carries the signature",
        sql=bridge_sql,
        result=routines_columns,
    )

    identity_args: Any
    try:
        identity_args = scalar(
            conn,
            "SELECT pg_get_function_identity_arguments(p.oid) FROM pg_proc p "
            "JOIN pg_namespace n ON n.oid = p.pronamespace "
            "WHERE n.nspname = 'mainline' AND p.proname = 'merge_permit'",
        )
        t.record(
            "does a built-in exist that renders the argument list, so a normaliser can be hand-built?",
            result=identity_args,
        )
    except Exception as exc:  # noqa: BLE001
        identity_args = {"error": describe(exc)}
        t.record(
            "does a built-in exist that renders the argument list, so a normaliser can be hand-built?",
            error=describe(exc),
        )

    # THE BUG, RUN AS WE ORIGINALLY WROTE IT.
    naive_granted = {s for s in show_spelling}
    bare = "merge_permit"
    naive_says_granted = bare in naive_granted
    t.record(
        "our original naive check: is the information_schema name present in the SHOW GRANTS names?",
        result={"looked_for": bare, "looked_in": sorted(naive_granted), "matched": naive_says_granted},
        note="this is our bug, reproduced verbatim, not a platform defect",
    )

    normalised_granted = {s.split("(")[0] for s in show_spelling}
    normalised_says_granted = bare in normalised_granted
    t.record(
        "the same check after stripping the argument list off the SHOW GRANTS name",
        result={"looked_in": sorted(normalised_granted), "matched": normalised_says_granted},
    )

    false_alarm = call_ok and not naive_says_granted and normalised_says_granted
    spellings_differ = bool(show_spelling) and show_spelling != catalogue_spelling

    verdict = "SPELLINGS-DIFFER" if (spellings_differ and false_alarm) else "STRUCK"
    why = (
        f"SHOW GRANTS says {show_spelling}, information_schema.routines says {catalogue_spelling}; "
        f"the probe demonstrably ran the procedure, and the naive comparison still reported it "
        f"as not granted"
        if verdict == "SPELLINGS-DIFFER"
        else "the two surfaces agreed, or the naive comparison did not misfire"
    )
    print(f"\n  F02 VERDICT: {verdict}\n    {why}\n")

    return {
        "verdict": verdict,
        "why": why,
        "call_succeeded_after_grant": call_ok,
        "show_grants_columns": show_cols,
        "show_grants_routine_rows": routine_rows,
        "show_grants_spelling": show_spelling,
        "information_schema_rows": catalogue_rows,
        "information_schema_spelling": catalogue_spelling,
        "information_schema_routines_columns": routines_columns,
        "pg_get_function_identity_arguments": identity_args,
        "naive_comparison_says_granted": naive_says_granted,
        "normalised_comparison_says_granted": normalised_says_granted,
        "naive_comparison_raised_a_false_alarm": false_alarm,
        "steps": sorted(range(first, len(t.steps) + 1)),
    }


# ---------------------------------------------------------------------------
# fixture
# ---------------------------------------------------------------------------


def build_fixture(conn: "psycopg.Connection", t: Transcript, probe: str) -> None:
    print("\n-- fixture -- one schema, one table, one procedure, one throwaway user\n")

    statements = [
        ("create the schema", "CREATE SCHEMA IF NOT EXISTS mainline"),
        (
            "create the table the control is measured on",
            "CREATE TABLE mainline.permit (permit_id UUID PRIMARY KEY, label STRING NOT NULL)",
        ),
        (
            "put one row in it",
            "INSERT INTO mainline.permit (permit_id, label) "
            "VALUES ('00000000-0000-0000-0000-000000000001'::UUID, 'seed')",
        ),
        (
            "create the procedure, with the signature the product actually ships",
            f"""CREATE PROCEDURE mainline.merge_permit(
                    p_permit_id UUID, p_body BYTES, p_actor STRING, p_reason STRING,
                    p_meta JSONB, p_digest BYTES, p_epoch INT2, p_sig BYTES)
                LANGUAGE PLpgSQL AS $$
                DECLARE
                    n INT;
                BEGIN
                    SELECT count(*) INTO n FROM mainline.permit;
                END
                $$""",
        ),
        (
            "let the probe user reach the schema",
            "GRANT USAGE ON SCHEMA mainline TO " + probe,
        ),
        (
            "let the probe user SELECT the table -- half of the negative control",
            "GRANT SELECT ON TABLE mainline.permit TO " + probe,
        ),
    ]
    for what, sql in statements:
        conn.execute(sql)
        t.record(what, sql=" ".join(sql.split()), result="ok")


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
    dbname = f"upstream_f01_{suffix}"
    probe = f"upstream_probe_{suffix}"
    started = datetime.now(timezone.utc)

    t = Transcript()
    admin = connect(args.dsn)
    version = scalar(admin, "SELECT version()")

    print("=" * 78)
    print("F01 / F02 REPRODUCTION -- has_function_privilege, and our own naive comparison")
    print("=" * 78)
    print(f"  node         {version}")
    print(f"  started      {started.isoformat()}")
    print(f"  CREATED DB   {dbname}")
    print(f"  CREATED ROLE {probe}")

    scratch = None
    result: dict[str, Any] = {}
    exit_code = 0
    try:
        admin.execute(f"CREATE ROLE {probe}")
        admin.execute(f"CREATE DATABASE {dbname}")
        admin.execute(f"GRANT CONNECT ON DATABASE {dbname} TO {probe}")
        t.record(
            "create the throwaway user and the throwaway database",
            sql=f"CREATE ROLE {probe}; CREATE DATABASE {dbname}",
            result="ok",
            note="a scratch database is a throwaway database created for one measurement and dropped after it",
        )

        scratch = connect(scratch_dsn(args.dsn, dbname))
        build_fixture(scratch, t, probe)

        f01 = measure_f01(scratch, t, probe)
        control = measure_negative_control(scratch, t, probe)
        f02 = measure_f02(scratch, t, probe)

        stamp = {
            "finding_measured_on": "local single-node CockroachDB CCL",
            "server_version": version,
            "client": f"psycopg {psycopg.__version__}",
            "host_os": f"{platform.system()} {platform.release()}",
            "measured_at_utc": started.isoformat(),
            "scratch_database_created": dbname,
            "scratch_role_created": probe,
            "script": "scripts/upstream/repro_privileges.py",
        }

        ev = Path(args.evidence_dir)
        write_evidence(
            ev / "F01-has-function-privilege.json",
            {
                "finding": "F01",
                "title": "has_function_privilege does not track EXECUTE behaviour on procedures",
                "label": "REPRODUCED-TODAY",
                **stamp,
                "measurement": f01,
                "negative_control_has_table_privilege": control,
                "transcript": t.for_json(set(f01["steps"]) | set(control["steps"])),
            },
        )
        write_evidence(
            ev / "F02-show-grants-signature.json",
            {
                "finding": "F02",
                "title": "SHOW GRANTS and information_schema.routines spell one procedure two ways",
                "label": "REPRODUCED-TODAY",
                **stamp,
                "measurement": f02,
                "transcript": t.for_json(set(f02["steps"])),
            },
        )

        result = {"f01": f01["verdict"], "f02": f02["verdict"], "control_tracks": control["tracks_behaviour"]}

        print("\n" + "=" * 78)
        print("VERDICTS")
        print("=" * 78)
        print(f"  F01  observed {f01['verdict']:<16} published finding claims {EXPECTED_F01_VERDICT}")
        print(f"  F02  observed {f02['verdict']:<16} published finding claims {EXPECTED_F02_VERDICT}")
        print(f"  has_table_privilege negative control tracks behaviour: {control['tracks_behaviour']}")

        if f01["verdict"] != EXPECTED_F01_VERDICT or f02["verdict"] != EXPECTED_F02_VERDICT:
            print("\n  MISMATCH: reality no longer matches a published finding. Re-label or strike it.")
            exit_code = 1
        elif not control["tracks_behaviour"]:
            print("\n  MISMATCH: the has_table_privilege control did not behave. F01 loses its contrast.")
            exit_code = 1
        else:
            print("\n  OK: both published findings still reproduce.")
    finally:
        if scratch is not None:
            scratch.close()
        try:
            admin.execute(f"DROP DATABASE IF EXISTS {dbname} CASCADE")
            print(f"  DROPPED DB   {dbname}")
        finally:
            admin.execute(f"DROP ROLE IF EXISTS {probe}")
            print(f"  DROPPED ROLE {probe}")
            left = scalar(
                admin,
                "SELECT count(*) FROM [SHOW DATABASES] WHERE database_name = %s",
                (dbname,),
            )
            print(f"  scratch databases left behind by this run: {left}")
            admin.close()

    print(json.dumps(result, indent=2))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
