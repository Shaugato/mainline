#!/usr/bin/env python
# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
#
# MI: none — this script asserts no product invariant. It is a field measurement.
# I: UPSTREAM-READONLY-1 — a script that documents damage caused by databases nobody
#    dropped may not leave a database behind. Exactly one object is created here, it is
#    named `upstream_f05_<8 hex>`, its CREATE and its DROP are both printed, and the DROP
#    runs from a `finally:` block so it happens on the error path too.
#
# WHAT THIS IS, IN ONE PARAGRAPH
# -----------------------------
# The minimal reproduction behind two field notes we are sending to CockroachDB:
#
#   F05  a cluster-wide ceiling on how many schema objects may exist (tables, views,
#        schemas, databases, functions). The ceiling is 20,000 by default. We hit it,
#        because our own throwaway test databases piled up. The error message is good;
#        where it arrives is the problem, and nothing counts down towards it.
#
#   F06  `gc.ttlseconds` — how long CockroachDB keeps superseded row versions, and so
#        how far into the past a `AS OF SYSTEM TIME` query may read. We published a
#        sentence saying CockroachDB Cloud's Basic tier "defaults to 4500". We cannot
#        support that sentence, and this script shows precisely how a careful team ends
#        up believing it.
#
# WHAT IT TOUCHES
# ---------------
# One local CockroachDB node, over the DSN below. It does not touch CockroachDB Cloud,
# it does not touch the shared `mainline_demo` database, it runs no AWS call, it prints
# no credential, and every statement except the create/drop of its own scratch database
# is a read. `CONFIGURE ZONE` is issued exactly once, against the scratch database this
# script created and is about to drop.
#
# USAGE
# -----
#   .venv/Scripts/python.exe scripts/upstream/repro_limits.py
#   .venv/Scripts/python.exe scripts/upstream/repro_limits.py --dsn ... --out-dir ...
#
# Exit 0 means every probe answered. Exit 1 means a probe that is load-bearing for a
# published finding did not answer, and the finding must be re-labelled before it ships.

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import psycopg
    from psycopg import sql as pgsql
except ModuleNotFoundError:  # pragma: no cover - the venv always has it
    print("psycopg is not importable; use .venv/Scripts/python.exe", file=sys.stderr)
    raise

DEFAULT_DSN = "postgresql://root@localhost:26257/defaultdb?sslmode=disable"
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT_DIR = REPO_ROOT / "evidence" / "upstream"

#: Schemas CockroachDB synthesises in every database. They are not what the object
#: ceiling counts, so a census that includes them over-counts by thousands.
VIRTUAL_SCHEMAS = ("information_schema", "pg_catalog", "pg_extension", "crdb_internal")

#: Databases the node ships with, plus the one shared database this wave may not touch.
NOT_SCRATCH = frozenset({"defaultdb", "postgres", "system", "mainline_demo"})

#: The exact expression `scripts/deploy/cloud_chain.py:1029` uses to lift the number out
#: of `SHOW ZONE CONFIGURATION`. Reproduced here verbatim, because F06 is about what this
#: expression throws away — not about the expression being wrong.
CLOUD_CHAIN_REGEX = r"gc\.ttlseconds\s*=\s*(\d+)"

LICENSE_SIDECAR = (
    "SPDX-FileCopyrightText: 2026 MAINLINE contributors\n"
    "SPDX-License-Identifier: CC-BY-4.0\n"
)


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def one_line(value: object) -> str:
    return " ".join(str(value).split())


def error_row(exc: BaseException) -> dict[str, Any]:
    """A SQL failure, recorded as data rather than as a traceback."""
    return {
        "ok": False,
        "sqlstate": getattr(exc, "sqlstate", None),
        "error": one_line(exc),
    }


def say(*parts: object) -> None:
    print(*parts, flush=True)


# --------------------------------------------------------------------------------------
# F05 — the schema-object ceiling
# --------------------------------------------------------------------------------------


def probe_object_ceiling(cur: Any) -> dict[str, Any]:
    """Read the ceiling, then hand-count how close this node is to it.

    There is no supported view that answers "how many schema objects do I have".
    `crdb_internal` holds one and is refused (see `catalogue_gauge` below), so the count
    here is summed out of `information_schema`, one database at a time. It is an
    approximation and is labelled as one.
    """
    out: dict[str, Any] = {"measured_at_utc": utc_now()}

    cur.execute("SHOW CLUSTER SETTING sql.schema.approx_max_object_count")
    ceiling = int(cur.fetchone()[0])
    out["ceiling_setting"] = "sql.schema.approx_max_object_count"
    out["ceiling"] = ceiling

    cur.execute("SELECT database_name FROM [SHOW DATABASES] ORDER BY 1")
    databases = [row[0] for row in cur.fetchall()]
    out["databases"] = databases
    out["database_count"] = len(databases)

    scratch = [d for d in databases if d not in NOT_SCRATCH]
    out["scratch_shaped"] = scratch
    out["scratch_shaped_count"] = len(scratch)

    virtual = ", ".join(f"'{s}'" for s in VIRTUAL_SCHEMAS)
    totals = {"tables": 0, "schemas": 0, "routines": 0}
    per_database: dict[str, int] = {}
    skipped: list[dict[str, Any]] = []

    for database in databases:
        subtotal = 0
        for key, relation, column in (
            ("tables", "information_schema.tables", "table_schema"),
            ("schemas", "information_schema.schemata", "schema_name"),
            ("routines", "information_schema.routines", "routine_schema"),
        ):
            try:
                # `information_schema.routines` answers for the SESSION's database, not
                # for the database named in the query, so the session is moved first.
                # `SET database` is a session variable; it changes nothing on the node.
                cur.execute(pgsql.SQL("SET database = {}").format(pgsql.Identifier(database)))
                cur.execute(f"SELECT count(*) FROM {relation} WHERE {column} NOT IN ({virtual})")
                value = int(cur.fetchone()[0])
            except Exception as exc:  # noqa: BLE001 - recorded, never raised
                skipped.append({"database": database, "relation": relation, **error_row(exc)})
                continue
            totals[key] += value
            subtotal += value
        per_database[database] = subtotal

    cur.execute("SET database = defaultdb")

    counted = sum(totals.values()) + len(databases)
    out["counted"] = {
        **totals,
        "databases": len(databases),
        "total": counted,
        "method": (
            "sum over every database of information_schema.tables + .schemata + .routines, "
            f"excluding the schemas {VIRTUAL_SCHEMAS}, plus one per database"
        ),
        "is_approximation": True,
        "why_approximate": (
            "the server counts descriptors; this counts catalogue rows. User-defined types "
            "are not counted. Expect this to differ from the number the server prints when "
            "it refuses a CREATE."
        ),
    }
    out["skipped"] = skipped
    out["headroom"] = ceiling - counted
    out["percent_of_ceiling"] = round(100.0 * counted / ceiling, 1)
    out["heaviest_databases"] = sorted(
        ({"database": d, "objects": n} for d, n in per_database.items()),
        key=lambda row: -int(row["objects"]),
    )[:10]

    say(f"F05  ceiling            {ceiling} ({out['ceiling_setting']})")
    say(f"F05  databases          {len(databases)}, of which {len(scratch)} are scratch-shaped")
    say(f"F05  counted objects    {counted} (approximate), {out['percent_of_ceiling']}% of the ceiling")
    say(f"F05  headroom           {out['headroom']}")
    return out


def probe_catalogue_gauge(cur: Any) -> dict[str, Any]:
    """Is there a supported way to ask how many schema objects exist? Measure it."""
    out: dict[str, Any] = {"question": "can a reader read their own object count?"}
    try:
        cur.execute("SELECT count(*) FROM crdb_internal.tables")
        out["crdb_internal"] = {"ok": True, "value": int(cur.fetchone()[0])}
    except Exception as exc:  # noqa: BLE001
        out["crdb_internal"] = error_row(exc)
    say(
        "F05  crdb_internal      "
        + ("readable" if out["crdb_internal"].get("ok") else f"refused {out['crdb_internal'].get('sqlstate')}")
    )
    return out


def probe_ceiling_warning(cur: Any, notices: list[str], database: str) -> dict[str, Any]:
    """Does anything warn on the way up? Create one database and count the warnings."""
    before = len(notices)
    cur.execute(pgsql.SQL("CREATE DATABASE {}").format(pgsql.Identifier(database)))
    emitted = notices[before:]
    out = {
        "statement": f"CREATE DATABASE {database}",
        "ok": True,
        "notices_emitted": emitted,
        "notice_count": len(emitted),
    }
    say(f"F05  CREATE {database}  ok, {len(emitted)} notice(s) from the server")
    return out


# --------------------------------------------------------------------------------------
# F06 — the time-travel window, and where its provenance goes
# --------------------------------------------------------------------------------------


def read_zone(cur: Any, statement: pgsql.Composable, label: str) -> dict[str, Any]:
    """Read one zone configuration, keeping BOTH columns.

    Column 1 is the target — the object the settings actually belong to. Column 2 is the
    settings, rendered as a runnable `ALTER ... CONFIGURE ZONE USING ...` statement. When
    an object has no settings of its own, column 1 names whatever it inherited from and
    column 2 still renders a complete statement. Keeping only column 2 loses that.
    """
    cur.execute(statement)
    row = cur.fetchone()
    target, raw = row[0], row[1]
    match = re.search(CLOUD_CHAIN_REGEX, str(raw))
    return {
        "asked_about": label,
        "target": target,
        "inherited": target != label,
        "raw_config": str(raw),
        "gc_ttlseconds_via_cloud_chain_regex": int(match.group(1)) if match else None,
    }


def probe_zone_provenance(cur: Any, database: str) -> dict[str, Any]:
    """Show that an inherited value and a set value are the same number, differently owned."""
    out: dict[str, Any] = {"measured_at_utc": utc_now()}

    out["range_default"] = read_zone(
        cur, pgsql.SQL("SHOW ZONE CONFIGURATION FOR RANGE default"), "RANGE default"
    )
    out["fresh_database_before"] = read_zone(
        cur,
        pgsql.SQL("SHOW ZONE CONFIGURATION FOR DATABASE {}").format(pgsql.Identifier(database)),
        f"DATABASE {database}",
    )

    # The one write in this script, against the throwaway database it is about to drop.
    cur.execute(
        pgsql.SQL("ALTER DATABASE {} CONFIGURE ZONE USING gc.ttlseconds = 4500").format(
            pgsql.Identifier(database)
        )
    )
    out["fresh_database_after_explicit_pin"] = read_zone(
        cur,
        pgsql.SQL("SHOW ZONE CONFIGURATION FOR DATABASE {}").format(pgsql.Identifier(database)),
        f"DATABASE {database}",
    )

    before = out["fresh_database_before"]
    after = out["fresh_database_after_explicit_pin"]
    out["the_point"] = {
        "value_before_anyone_configured_it": before["gc_ttlseconds_via_cloud_chain_regex"],
        "value_after_we_configured_it": after["gc_ttlseconds_via_cloud_chain_regex"],
        "values_are_identical": (
            before["gc_ttlseconds_via_cloud_chain_regex"]
            == after["gc_ttlseconds_via_cloud_chain_regex"]
        ),
        "target_before": before["target"],
        "target_after": after["target"],
        "targets_are_identical": before["target"] == after["target"],
        "reading": (
            "the regex used by scripts/deploy/cloud_chain.py:1029 returns the same number "
            "in both states. Only the target column separates 'the platform gave me this' "
            "from 'we set this'."
        ),
    }

    say(f"F06  RANGE default      gc.ttlseconds = {out['range_default']['gc_ttlseconds_via_cloud_chain_regex']}")
    say(
        "F06  fresh database     "
        f"gc.ttlseconds = {before['gc_ttlseconds_via_cloud_chain_regex']}, "
        f"target = {before['target']!r} (nobody configured this database)"
    )
    say(
        "F06  after our pin      "
        f"gc.ttlseconds = {after['gc_ttlseconds_via_cloud_chain_regex']}, "
        f"target = {after['target']!r}"
    )
    return out


def probe_new_object_time_travel(cur: Any, database: str) -> dict[str, Any]:
    """A read into the past of an object that did not exist then. What does it say?"""
    cur.execute(
        pgsql.SQL("CREATE TABLE {}.public.t (id INT PRIMARY KEY)").format(pgsql.Identifier(database))
    )
    attempts = []
    for offset in ("-30s", "-2h", "-5h"):
        statement = f"SELECT count(*) FROM \"{database}\".public.t AS OF SYSTEM TIME '{offset}'"
        try:
            cur.execute(statement)
            attempts.append({"offset": offset, "ok": True, "rows": int(cur.fetchone()[0])})
        except Exception as exc:  # noqa: BLE001
            attempts.append({"offset": offset, "statement": statement, **error_row(exc)})
    say(
        "F06  new-object AOST    "
        + ", ".join(f"{a['offset']} -> {a.get('sqlstate') or 'ok'}" for a in attempts)
    )
    return {"attempts": attempts}


def probe_gc_window_error(cur: Any, databases: list[str], scratch: str) -> dict[str, Any]:
    """Read past the retention window on a table old enough to have one, and record the error.

    Needs a table older than the window. On a node with no long-lived table this cannot be
    demonstrated, and the probe says so rather than inventing a result.
    """
    virtual = ", ".join(f"'{s}'" for s in VIRTUAL_SCHEMAS)
    candidates = [d for d in databases if d not in NOT_SCRATCH and d != scratch]
    out: dict[str, Any] = {"available": False, "candidates_tried": []}

    for database in candidates:
        try:
            cur.execute(pgsql.SQL("SET database = {}").format(pgsql.Identifier(database)))
            cur.execute(
                "SELECT table_schema, table_name FROM information_schema.tables "
                f"WHERE table_schema NOT IN ({virtual}) AND table_type = 'BASE TABLE' "
                "ORDER BY table_schema, table_name LIMIT 1"
            )
            row = cur.fetchone()
        except Exception as exc:  # noqa: BLE001
            out["candidates_tried"].append({"database": database, **error_row(exc)})
            continue
        if row is None:
            continue

        qualified = f'"{database}"."{row[0]}"."{row[1]}"'
        attempts = []
        for offset in ("-1h", "-2h", "-5h", "-24h"):
            statement = f"SELECT count(*) FROM {qualified} AS OF SYSTEM TIME '{offset}'"
            try:
                cur.execute(statement)
                attempts.append({"offset": offset, "ok": True, "rows": int(cur.fetchone()[0])})
            except Exception as exc:  # noqa: BLE001
                attempts.append({"offset": offset, "statement": statement, **error_row(exc)})

        refused = [a for a in attempts if not a.get("ok") and "GC threshold" in str(a.get("error", ""))]
        if not refused:
            out["candidates_tried"].append({"database": database, "table": qualified, "no_gc_refusal": True})
            continue

        out["available"] = True
        out["table"] = qualified
        out["attempts"] = attempts
        out["mentions_gc_ttlseconds"] = any("ttlseconds" in str(a.get("error", "")) for a in refused)
        out["mentions_table_name"] = any(row[1] in str(a.get("error", "")) for a in refused)
        out["sqlstates"] = sorted({str(a.get("sqlstate")) for a in refused})
        out["derived_window_seconds"] = _derive_window(refused)
        break

    cur.execute("SET database = defaultdb")

    if out["available"]:
        say(
            "F06  retention refusal  "
            f"{out['sqlstates']} | names gc.ttlseconds: {out['mentions_gc_ttlseconds']} | "
            f"names the table: {out['mentions_table_name']} | "
            f"window derived from the message: {out['derived_window_seconds']}"
        )
    else:
        say("F06  retention refusal  NOT AVAILABLE - no table on this node is older than the window")
    return out


def _derive_window(refused: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Recover the retention window from the two timestamps the error prints.

    The message reads `batch timestamp <A> must be after replica GC threshold <B>`.
    `A` is `now - offset`; `B` is the oldest instant still readable. So the window in
    force is `offset - (B - A)`. Doing this at several offsets is a consistency check:
    they must all agree.
    """
    pattern = re.compile(r"batch timestamp\s+(\d+\.\d+),\d+\s+must be after replica GC threshold\s+(\d+\.\d+)")
    units = {"s": 1, "m": 60, "h": 3600}
    derived = []
    for attempt in refused:
        match = pattern.search(str(attempt.get("error", "")))
        if not match:
            continue
        offset = str(attempt["offset"]).lstrip("-")
        seconds = float(offset[:-1]) * units[offset[-1]]
        batch_ts, threshold_ts = float(match.group(1)), float(match.group(2))
        derived.append(
            {
                "offset": attempt["offset"],
                "batch_timestamp": batch_ts,
                "gc_threshold": threshold_ts,
                "window_seconds": round(seconds - (threshold_ts - batch_ts), 1),
            }
        )
    return derived


# --------------------------------------------------------------------------------------


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    sidecar = path.with_suffix(path.suffix + ".license")
    sidecar.write_text(LICENSE_SIDECAR, encoding="utf-8")
    say(f"wrote {path}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", default=os.environ.get("MAINLINE_DSN", DEFAULT_DSN))
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    args = parser.parse_args(argv)

    scratch = "upstream_f05_" + secrets.token_hex(4)
    started = time.time()
    notices: list[str] = []

    with psycopg.connect(args.dsn, autocommit=True) as conn:
        conn.add_notice_handler(lambda diag: notices.append(one_line(diag.message_primary)))
        with conn.cursor() as cur:
            cur.execute("SELECT version()")
            version = str(cur.fetchone()[0])
            say(f"node   {version}")
            say(f"exam   local single-node CockroachDB, NOT CockroachDB Cloud")
            say("")

            node = {
                "version": version,
                "exam": "local single-node CockroachDB CCL",
                "not_measured_on": "CockroachDB Cloud (Basic or otherwise): no Cloud statement is issued here",
                "dsn_host": "localhost:26257",
                "measured_at_utc": utc_now(),
            }

            f05: dict[str, Any] = {"finding": "F05", "node": node}
            f06: dict[str, Any] = {"finding": "F06", "node": node}

            f05["ceiling"] = probe_object_ceiling(cur)
            f05["catalogue_gauge"] = probe_catalogue_gauge(cur)

            created = False
            try:
                f05["warning_on_the_way_up"] = probe_ceiling_warning(cur, notices, scratch)
                created = True
                say("")
                f06["zone_provenance"] = probe_zone_provenance(cur, scratch)
                f06["new_object_time_travel"] = probe_new_object_time_travel(cur, scratch)
                f06["retention_refusal"] = probe_gc_window_error(
                    cur, list(f05["ceiling"]["databases"]), scratch
                )
            finally:
                if created:
                    cur.execute(
                        pgsql.SQL("DROP DATABASE {} CASCADE").format(pgsql.Identifier(scratch))
                    )
                    say(f"F05  DROP {scratch}  done - this script leaves no database behind")

            f05["scratch_database"] = {"name": scratch, "created": created, "dropped": created}
            f06["scratch_database"] = {"name": scratch, "created": created, "dropped": created}

            # The claim we are NOT making, recorded so nobody re-derives it from the numbers.
            f06["what_this_does_not_establish"] = (
                "Nothing here is a reading of CockroachDB Cloud. This script cannot and does "
                "not establish what gc.ttlseconds reads on an unconfigured Cloud Basic "
                "database, and the sentence 'gc.ttlseconds defaults to 4500 on Basic' is not "
                "supported by it or by any artefact in this repository."
            )

            f05["elapsed_seconds"] = round(time.time() - started, 1)
            f06["elapsed_seconds"] = round(time.time() - started, 1)

    say("")
    write_json(args.out_dir / "F05-schema-object-cap.json", f05)
    write_json(args.out_dir / "F06-gc-ttlseconds.json", f06)

    # Load-bearing probes. If one of these is missing, a published finding is unsupported.
    problems: list[str] = []
    if f05["ceiling"].get("ceiling") is None:
        problems.append("F05: the object ceiling did not read")
    if f05["catalogue_gauge"]["crdb_internal"].get("ok") is None:
        problems.append("F05: the catalogue gauge probe did not run")
    provenance = f06.get("zone_provenance", {}).get("the_point", {})
    if not provenance.get("values_are_identical"):
        problems.append(
            "F06: the inherited and explicit readings differ, so the provenance claim "
            "does not hold on this node and must be re-stated"
        )
    if provenance.get("targets_are_identical"):
        problems.append(
            "F06: the target column did NOT separate inherited from explicit, so the "
            "'one column would have told us' claim does not hold on this node"
        )

    for problem in problems:
        print(f"UNSUPPORTED  {problem}", file=sys.stderr)
    if problems:
        return 1

    say("OK  every load-bearing probe answered")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
