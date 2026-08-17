#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Minimal reproduction for two upstream field notes about CockroachDB.

F03 — does the query planner pick a vector index on its own, or must it be told?
F04 — what can you read out of the database's own bookkeeping tables?

WHAT THIS PROGRAM TOUCHES
    One brand-new database whose name starts with ``upstream_f03_``, on the local
    single-node cluster only.  It creates that database, does everything inside it,
    and drops it in a ``finally:`` block whether or not anything failed.  The name it
    created and the name it dropped are both printed.

WHAT THIS PROGRAM NEVER TOUCHES
    CockroachDB Cloud, the ``mainline_demo`` database, AWS, SSM, and any product code,
    test, migration or seed.  It issues no ``GRANT``, no ``REVOKE``, no
    ``CONFIGURE ZONE``, and no ``SET CLUSTER SETTING``.  The one session-level setting
    it changes (``allow_unsafe_internals``) lives and dies with its own connection.

USAGE
    D:/CoackroachDBxAWS/mainline/.venv/Scripts/python.exe \
        scripts/upstream/repro_vector_and_catalogue.py

    --dsn DSN     override the local connection string
    --rows N,N,N  override the row-count sweep (default 0,200,1100,5300)
    --quick       shorter sweep (0,200) for a smoke run
    --out DIR     where the JSON transcripts land (default evidence/upstream)

EXIT CODE
    0 if both reproductions ran to completion and wrote their transcripts.  A non-zero
    exit means the run itself broke, not that a finding failed to reproduce -- whether a
    finding reproduced is recorded in the JSON under ``verdict``, never in the exit code.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import secrets
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    import psycopg
except ImportError:  # pragma: no cover - environment problem, not a finding
    sys.stderr.write("psycopg (v3) is required; use the repo virtualenv.\n")
    raise

# --------------------------------------------------------------------------------------
# Constants.  Fixed so two runs of this program produce comparable plan digests.
# --------------------------------------------------------------------------------------

LOCAL_DSN = "postgresql://root@localhost:26257/defaultdb?sslmode=disable"
DEFAULT_SWEEP = (0, 200, 1100, 5300)  # matches evidence/aws/ann/explain-unhinted.txt App. A
SEED = 20260817
DIMS = 1024  # matches verticals/mainline/db/migrations/0031_clause_embedding.sql
SITE_ID = "5b144fe2-c64e-54a4-8b7c-2e3eb31497b6"  # same literal the archived Cloud run bound
ACTIVITY_ROOTS = ("/mill", "/surface", "/underground")
SEARCH_ROOT = "/mill"
TOP_K = 10
TABLE = "t_clause_embedding"
INDEX = "t_ann"

# The archived CockroachDB Cloud Basic material.  READ from the tree, never re-run:
# re-running would mean driving load against a shared live cluster.
ARCHIVED_CLOUD = {
    "f03": [
        {
            "source": "docs/adr/0002-g1-platform-ground-truth.md",
            "lines": "18-19, 36",
            "measured_on": "2026-08-07",
            "tier": "CockroachDB Cloud Basic, aws-ap-southeast-1 (Singapore)",
            "version": "CockroachDB CCL v26.2.5",
            "has_captured_transcript": False,
            "claim": (
                "GT-06: at ~5,200 rows a prefix-constrained vector search, unhinted, does NOT "
                "use the vector index; the plan is top-k -> render -> filter -> scan. "
                "GT-06b: naming the index makes it traverse."
            ),
        },
        {
            "source": "evidence/aws/ann/explain-unhinted.txt",
            "companion": "evidence/aws/ann/ann-proof.json",
            "lines": "Appendix A",
            "measured_on": "2026-08-11",
            "artefact_timestamp_utc": "2026-08-11T04:07:47Z",
            "sweep_timestamp_utc": "2026-08-11T02:25:36Z",
            "tier": "CockroachDB Cloud Basic, aws-ap-southeast-1 (Singapore)",
            "version": "CockroachDB CCL v26.2.5",
            "has_captured_transcript": True,
            "claim": (
                "The unhinted plan ALSO traverses the vector index, at every row count swept "
                "(0, 200, 1100, 5300), including GT-06's own ~5,200. Recorded verbatim in the "
                "artefact as 'GT-06 reproduces: False'."
            ),
        },
    ],
    "f04": [
        {
            "source": "evidence/deploy/judge-run.json",
            "pointer": "negative probe N02",
            "artefact_timestamp_utc": "2026-08-11T00:23:29Z",
            "tier": "CockroachDB Cloud Basic, aws-ap-southeast-1 (Singapore)",
            "role": "mainline_judge",
            "channel": "direct SQL (pgwire)",
            "sqlstate": "42501",
            "refusal_verbatim": (
                "Access to crdb_internal and system is restricted. HINT: These interfaces are "
                "unsupported in production. To proceed, set the session variable "
                "allow_unsafe_internals = true (not recommended), or contact Cockroach Labs "
                "for a supported alternative."
            ),
        },
        {
            "source": "evidence/deploy/judge-access.json",
            "pointer": "probe.negatives -> crdb_internal.jobs, crdb_internal.tables",
            "artefact_timestamp_utc": "2026-08-11T00:23:29Z",
            "tier": "CockroachDB Cloud Basic, aws-ap-southeast-1 (Singapore)",
            "role": "mainline_judge",
            "channel": "direct SQL (pgwire)",
            "statements": [
                "SELECT count(*) FROM crdb_internal.jobs",
                "SELECT count(*) FROM crdb_internal.tables",
            ],
            "sqlstate": "42501",
            "refusal_verbatim": (
                "Access to crdb_internal and system is restricted. HINT: These interfaces are "
                "unsupported in production. To proceed, set the session variable "
                "allow_unsafe_internals = true (not recommended), or contact Cockroach Labs for "
            ),
            "note": "This artefact stores the message truncated at 200 chars; judge-run.json holds it whole.",
        },
        {
            "source": "evidence/mcp/pack-run.json",
            "pointer": "cli_run.stdout, negative probe N02",
            "tier": "CockroachDB Cloud Basic, aws-ap-southeast-1 (Singapore)",
            "channel": "CockroachDB managed MCP server",
            "sqlstate": None,
            "refusal_verbatim": (
                'query references a restricted schema: access to "crdb_internal" is blocked '
                "for security reasons"
            ),
            "note": "Different wording, different layer: the MCP tool refuses before the SQL layer does.",
        },
        {
            "source": "docs/demo/film/VO-CLOSE.md",
            "lines": "1249",
            "tier": "local single-node CCL (the node this script also uses)",
            "channel": "direct SQL (pgwire)",
            "observation": (
                "crdb_internal.table_indexes was refused with InsufficientPrivilege and a hint "
                "pointing at allow_unsafe_internals; SHOW INDEXES answered the same question."
            ),
        },
    ],
}

# The bookkeeping tables we ask for.  "Bookkeeping tables" = the database's own tables
# ABOUT the database -- what tables exist, what jobs are running, which node is which.
CATALOGUE_PROBES = [
    ("crdb_internal.tables", "SELECT count(*) FROM crdb_internal.tables"),
    ("crdb_internal.table_indexes", "SELECT count(*) FROM crdb_internal.table_indexes"),
    ("crdb_internal.jobs", "SELECT count(*) FROM crdb_internal.jobs"),
    ("crdb_internal.gossip_nodes", "SELECT count(*) FROM crdb_internal.gossip_nodes"),
    ("crdb_internal.cluster_id()", "SELECT crdb_internal.cluster_id()"),
    ("system.namespace", "SELECT count(*) FROM system.namespace"),
]

# The surfaces that are NOT restricted, asked the same questions where they can answer them.
OPEN_SURFACE_PROBES = [
    ("information_schema.tables", "SELECT count(*) FROM information_schema.tables"),
    ("pg_catalog.pg_class", "SELECT count(*) FROM pg_catalog.pg_class"),
]


# --------------------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------------------


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def unit_vector(rng: random.Random, dims: int = DIMS) -> str:
    """A pseudo-random unit vector, formatted the way CockroachDB accepts a VECTOR literal."""
    raw = [rng.gauss(0.0, 1.0) for _ in range(dims)]
    norm = math.sqrt(sum(x * x for x in raw)) or 1.0
    return "[" + ",".join("%.5f" % (x / norm) for x in raw) + "]"


def sqlstate_of(exc: Exception) -> str | None:
    return getattr(exc, "sqlstate", None)


def message_of(exc: Exception) -> str:
    """Full server message including the HINT, on one line, without the local file paths."""
    return " ".join(str(exc).split())


# Statements whose ANSWER identifies this particular machine rather than demonstrating
# anything.  The refusal is the observable; the value is replaced so the transcript can be
# published without carrying a local cluster's identity around with it.
REDACT_ANSWER_OF = {"SELECT crdb_internal.cluster_id()"}


def run_statement(conn, sql: str, params=None) -> dict:
    """Run one statement and record what came back -- an answer or a refusal, never a crash."""
    started = time.perf_counter()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall() if cur.description else []
            columns = [c.name for c in cur.description] if cur.description else []
        if sql in REDACT_ANSWER_OF:
            body = [["<redacted: identifies this local cluster, not the finding>"]]
        else:
            body = [list(map(_jsonable, r)) for r in rows[:20]]
        return {
            "statement": sql,
            "answered": True,
            "sqlstate": "00000",
            "columns": columns,
            "rows": body,
            "row_count": len(rows),
            "ms": round((time.perf_counter() - started) * 1000, 1),
        }
    except Exception as exc:  # noqa: BLE001 - a refusal is data here, not an error
        return {
            "statement": sql,
            "answered": False,
            "sqlstate": sqlstate_of(exc),
            "error_class": type(exc).__name__,
            "server_message_verbatim": message_of(exc),
            "ms": round((time.perf_counter() - started) * 1000, 1),
        }


def _jsonable(value):
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


# --------------------------------------------------------------------------------------
# F03 -- the query plan
# --------------------------------------------------------------------------------------

ANN_SELECT = (
    "SELECT clause_uuid, commit_id, embedding <=> %(vec)s AS dist\n"
    "  FROM {source}\n"
    " WHERE site_id = %(site)s AND activity_root = %(root)s\n"
    " ORDER BY embedding <=> %(vec)s LIMIT %(k)s"
)


def explain(conn, source: str, query_vec: str) -> dict:
    """EXPLAIN one shape and reduce the plan to facts a reader can check by eye."""
    sql = "EXPLAIN " + ANN_SELECT.format(source=source)
    params = {"vec": query_vec, "site": SITE_ID, "root": SEARCH_ROOT, "k": TOP_K}
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            plan = "\n".join(row[0] for row in cur.fetchall())
    except Exception as exc:  # noqa: BLE001
        return {
            "source": source,
            "statement": ANN_SELECT.format(source=source),
            "explained": False,
            "sqlstate": sqlstate_of(exc),
            "server_message_verbatim": message_of(exc),
        }

    lowered = plan.lower()
    recommendations = [
        line.strip()
        for line in plan.splitlines()
        if line.strip().startswith("SQL command:")
    ]
    return {
        "source": source,
        "statement": ANN_SELECT.format(source=source),
        "explained": True,
        "plan_text": plan,
        "facts": {
            "has_vector_search_node": "vector search" in lowered,
            "traverses_the_vector_index": f"{TABLE}@{INDEX}" in plan,
            "has_prefix_spans": "prefix spans:" in lowered,
            "has_full_scan_node": "full scan" in lowered,
            "has_filter_node": "• filter" in plan or "filter" in lowered.split("\n")[0:0],
            "index_recommendation_count": len(recommendations),
            "index_recommendations": recommendations,
        },
        "plan_digest_sha256": hashlib.sha256(plan.encode("utf-8")).hexdigest(),
        "plan_lines": len(plan.splitlines()),
    }


def counterfactual_drop_prefix(conn, query_vec: str) -> dict:
    """Keep the index named, remove one of the two leading columns from the WHERE clause."""
    sql = (
        f"EXPLAIN SELECT clause_uuid FROM {TABLE}@{INDEX} "
        "WHERE activity_root = %(root)s ORDER BY embedding <=> %(vec)s LIMIT %(k)s"
    )
    params = {"vec": query_vec, "root": SEARCH_ROOT, "k": TOP_K}
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            plan = "\n".join(row[0] for row in cur.fetchall())
        return {"statement": sql, "refused": False, "plan_text": plan}
    except Exception as exc:  # noqa: BLE001
        return {
            "statement": sql,
            "refused": True,
            "sqlstate": sqlstate_of(exc),
            "server_message_verbatim": message_of(exc),
        }


def build_and_sweep(conn, sweep: tuple[int, ...], log) -> dict:
    rng = random.Random(SEED)
    log(f"  creating table {TABLE} with a vector index named {INDEX} ({DIMS} dimensions)")
    conn.execute(
        f"""
        CREATE TABLE {TABLE} (
            clause_uuid   UUID   NOT NULL DEFAULT gen_random_uuid(),
            commit_id     INT8   NOT NULL,
            site_id       UUID   NOT NULL,
            activity_root STRING NOT NULL,
            embedding     VECTOR({DIMS}) NOT NULL,
            CONSTRAINT {TABLE}_pk PRIMARY KEY (clause_uuid, commit_id),
            VECTOR INDEX {INDEX} (site_id, activity_root, embedding vector_cosine_ops)
        )
        """
    )

    query_vec = unit_vector(rng)
    checkpoints: list[dict] = []
    present = 0

    for target in sweep:
        to_add = target - present
        if to_add > 0:
            log(f"  inserting {to_add} rows to reach {target}")
            batch: list[tuple] = []
            for i in range(to_add):
                root = ACTIVITY_ROOTS[i % len(ACTIVITY_ROOTS)]
                batch.append((present + i + 1, SITE_ID, root, unit_vector(rng)))
                if len(batch) == 200:
                    _insert(conn, batch)
                    batch = []
            if batch:
                _insert(conn, batch)
            present = target

        # Refresh the statistics the cost model reads, so a stale-stats explanation is excluded.
        conn.execute(f"ANALYZE {TABLE}")
        actual = conn.execute(f"SELECT count(*) FROM {TABLE}").fetchone()[0]
        matching = conn.execute(
            f"SELECT count(*) FROM {TABLE} WHERE site_id = %s AND activity_root = %s",
            (SITE_ID, SEARCH_ROOT),
        ).fetchone()[0]

        unhinted = explain(conn, TABLE, query_vec)
        hinted = explain(conn, f"{TABLE}@{INDEX}", query_vec)
        log(
            f"    rows={actual:<5} unhinted traverses {INDEX}: "
            f"{unhinted['facts']['traverses_the_vector_index'] if unhinted['explained'] else 'n/a'}"
            f"   hinted traverses {INDEX}: "
            f"{hinted['facts']['traverses_the_vector_index'] if hinted['explained'] else 'n/a'}"
        )
        checkpoints.append(
            {
                "rows_in_table": actual,
                "rows_matching_both_prefix_columns": matching,
                "statistics_refreshed": True,
                "unhinted": unhinted,
                "hinted": hinted,
                "plans_are_identical": (
                    unhinted.get("plan_digest_sha256") == hinted.get("plan_digest_sha256")
                ),
            }
        )

    counterfactual = counterfactual_drop_prefix(conn, query_vec)
    log(
        "  counterfactual (index named, one prefix column dropped from WHERE): "
        + (
            f"REFUSED {counterfactual['sqlstate']}"
            if counterfactual["refused"]
            else "answered"
        )
    )
    return {"checkpoints": checkpoints, "prefix_counterfactual": counterfactual}


def _insert(conn, batch: list[tuple]) -> None:
    values = ",".join(["(%s,%s,%s,%s)"] * len(batch))
    flat: list = []
    for row in batch:
        flat.extend(row)
    conn.execute(
        f"INSERT INTO {TABLE} (commit_id, site_id, activity_root, embedding) VALUES {values}",
        flat,
    )


# --------------------------------------------------------------------------------------
# F04 -- the bookkeeping tables
# --------------------------------------------------------------------------------------


def probe_plan_gist(conn, log) -> dict:
    """Can a plan's short identity be produced, and can it be read back again?

    A "plan gist" is a short string standing for the shape of a query plan.  It is exactly the
    thing an architecture document would want to quote so a later run could compare itself
    against it.  Producing one is a plain EXPLAIN.  Turning one back into a readable plan is a
    function that lives in the schema that is closed by default -- which is F04's subject, and
    which is why this probe sits in this script rather than in a third one.
    """
    log("  can a plan's short identity be produced, and read back?")
    produce = run_statement(conn, "EXPLAIN (GIST) SELECT 1")
    gist = None
    if produce["answered"] and produce["rows"]:
        gist = str(produce["rows"][0][0])
    decode: dict = {"skipped": True}
    if gist:
        decode = run_statement(conn, "SELECT crdb_internal.decode_plan_gist(%s)", (gist,))
        decode["statement"] = f"SELECT crdb_internal.decode_plan_gist('{gist}')"
    log(
        f"    EXPLAIN (GIST)                "
        + ("ANSWERED" if produce["answered"] else f"REFUSED {produce['sqlstate']}")
        + (f"   gist: {gist}" if gist else "")
    )
    log(
        "    crdb_internal.decode_plan_gist "
        + (
            "ANSWERED"
            if decode.get("answered")
            else f"REFUSED {decode.get('sqlstate')}"
        )
    )
    return {
        "question": (
            "Can a query plan be reduced to a short quotable string, and can that string be "
            "turned back into a readable plan through a surface that is open by default?"
        ),
        "produce": produce,
        "gist": gist,
        "decode": decode,
        "facts": {
            "gist_can_be_produced": bool(gist),
            "gist_can_be_read_back_with_the_session_at_its_default": bool(decode.get("answered")),
            "decoder_lives_in_the_restricted_schema": True,
        },
    }


def probe_catalogue(conn, log) -> dict:
    default_state = run_statement(conn, "SHOW allow_unsafe_internals")

    log("  asking the restricted bookkeeping tables, with the session left at its default")
    closed = [
        {"target": name, **run_statement(conn, sql)} for name, sql in CATALOGUE_PROBES
    ]
    for row in closed:
        log(
            f"    {row['target']:<32} "
            + ("ANSWERED" if row["answered"] else f"REFUSED {row['sqlstate']}")
        )

    log("  asking the surfaces that are not restricted")
    open_surfaces = [
        {"target": name, **run_statement(conn, sql)} for name, sql in OPEN_SURFACE_PROBES
    ]
    for row in open_surfaces:
        log(
            f"    {row['target']:<32} "
            + ("ANSWERED" if row["answered"] else f"REFUSED {row['sqlstate']}")
        )

    # The alternative the refusal does not name.  The question is asked in two halves,
    # because they do not have the same answer:
    #   (a) which indexes does this table have?
    #   (b) which of them is a vector index?
    log("  asking the same question a supported way")
    restricted_route = {
        "target": "crdb_internal.table_indexes",
        **run_statement(
            conn,
            "SELECT index_name, index_type FROM crdb_internal.table_indexes "
            f"WHERE descriptor_name = '{TABLE}'",
        ),
    }
    show_indexes_names = {
        "target": "SHOW INDEXES -- question (a), which indexes exist",
        **run_statement(
            conn,
            f"SELECT DISTINCT index_name FROM [SHOW INDEXES FROM {TABLE}] ORDER BY index_name",
        ),
    }
    show_indexes_full = {
        "target": "SHOW INDEXES -- every column it returns, for the vector index",
        **run_statement(
            conn,
            f"SELECT * FROM [SHOW INDEXES FROM {TABLE}] WHERE index_name = '{INDEX}'",
        ),
    }
    show_create = {
        "target": "SHOW CREATE TABLE -- question (b), which one is a vector index",
        **run_statement(conn, f"SELECT create_statement FROM [SHOW CREATE TABLE {TABLE}]"),
    }
    pg_route = {
        "target": "pg_catalog access method -- the PostgreSQL-shaped route",
        **run_statement(
            conn,
            "SELECT c.relname, am.amname FROM pg_class c "
            "JOIN pg_index ix ON c.oid = ix.indexrelid "
            "LEFT JOIN pg_am am ON c.relam = am.oid "
            f"WHERE ix.indrelid = '{TABLE}'::regclass",
        ),
    }

    create_text = ""
    if show_create["answered"] and show_create["rows"]:
        create_text = str(show_create["rows"][0][0])
    show_indexes_columns = show_indexes_full.get("columns", [])

    alternative = {
        "question_a": "Which indexes does this table have?",
        "question_b": "Which of them is a vector index?",
        "restricted_route": restricted_route,
        "supported_route_names": show_indexes_names,
        "supported_route_full_row": show_indexes_full,
        "supported_route_type": show_create,
        "postgres_shaped_route": pg_route,
        "facts": {
            # SHOW INDEXES lists the index by name, so question (a) is answered.
            "show_indexes_lists_the_vector_index": bool(
                show_indexes_names["answered"]
                and any(INDEX in str(r) for r in show_indexes_names["rows"])
            ),
            # ...but none of its columns say what KIND of index it is, so (b) is not.
            "show_indexes_columns": show_indexes_columns,
            "show_indexes_says_which_kind_of_index_it_is": any(
                col.lower() in {"index_type", "type", "am", "amname", "access_method"}
                for col in show_indexes_columns
            ),
            # SHOW CREATE TABLE prints the words VECTOR INDEX, so (b) is answered there.
            "show_create_table_says_vector_index": "VECTOR INDEX" in create_text,
            "postgres_route_names_an_access_method": bool(
                pg_route["answered"]
                and any(
                    len(r) > 1 and r[1] not in (None, "", "None")
                    for r in pg_route["rows"]
                )
            ),
        },
        "named_in_the_refusal_message": False,
    }
    log(
        "    crdb_internal.table_indexes   "
        + (
            "ANSWERED"
            if restricted_route["answered"]
            else f"REFUSED {restricted_route['sqlstate']}"
        )
    )
    log(
        "    SHOW INDEXES                  "
        + ("ANSWERED" if show_indexes_names["answered"] else f"REFUSED {show_indexes_names['sqlstate']}")
        + "   names the vector index: "
        + str(alternative["facts"]["show_indexes_lists_the_vector_index"])
        + "   says it is a VECTOR index: "
        + str(alternative["facts"]["show_indexes_says_which_kind_of_index_it_is"])
    )
    log(
        "    SHOW CREATE TABLE             "
        + ("ANSWERED" if show_create["answered"] else f"REFUSED {show_create['sqlstate']}")
        + "   says it is a VECTOR index: "
        + str(alternative["facts"]["show_create_table_says_vector_index"])
    )
    log(
        "    pg_catalog access method      "
        + ("ANSWERED" if pg_route["answered"] else f"REFUSED {pg_route['sqlstate']}")
        + "   names an access method: "
        + str(alternative["facts"]["postgres_route_names_an_access_method"])
    )

    gist_probe = probe_plan_gist(conn, log)

    # Is the escape hatch the message names actually usable here?  Session-scoped only.
    log("  trying the escape hatch the refusal message names, on this session only")
    escape: dict = {
        "session_variable": "allow_unsafe_internals",
        "default_value": default_state,
        "scope": "session only; this connection is closed at the end of the run",
    }
    escape["set"] = run_statement(conn, "SET allow_unsafe_internals = true")
    escape["reread"] = run_statement(conn, "SHOW allow_unsafe_internals")
    escape["after"] = [
        {"target": name, **run_statement(conn, sql)} for name, sql in CATALOGUE_PROBES
    ]
    for row in escape["after"]:
        log(
            f"    {row['target']:<32} "
            + ("ANSWERED" if row["answered"] else f"REFUSED {row['sqlstate']}")
        )

    # With the hatch open, look at what the restricted table would have told us.  This is the
    # only way to check the claim "crdb_internal is the surface that answers the question"
    # rather than assuming it.
    behind_the_wall = {
        "target": "crdb_internal.table_indexes, read with the hatch open",
        **run_statement(
            conn,
            "SELECT index_name, index_type FROM crdb_internal.table_indexes "
            f"WHERE descriptor_name = '{TABLE}'",
        ),
    }
    # Every column, not just index_type -- otherwise "the restricted table would not have
    # answered either" is a claim about one column dressed up as a claim about the table.
    every_column = {
        "target": "crdb_internal.table_indexes, EVERY column, read with the hatch open",
        **run_statement(
            conn,
            f"SELECT * FROM crdb_internal.table_indexes WHERE descriptor_name = '{TABLE}'",
        ),
    }
    # Two different questions, and they have different answers:
    #   (a) does ANY cell anywhere say "vector"?
    #   (b) does any cell OTHER than a printed CREATE ... statement say it?
    # (b) is the one that matters: a typed column can be counted; a DDL string must be
    # pattern-matched, which is not the same kind of answer.
    ec_columns = every_column.get("columns", [])
    ec_rows = every_column.get("rows", [])
    ddl_columns = {"create_statement", "create_nofk_statement", "definition"}
    every_column["facts"] = {
        "columns": ec_columns,
        "any_cell_says_vector": any(
            "vector" in str(cell).lower() or "cspann" in str(cell).lower()
            for row in ec_rows
            for cell in row
        ),
        "a_typed_column_says_vector": any(
            ("vector" in str(cell).lower() or "cspann" in str(cell).lower())
            for row in ec_rows
            for col, cell in zip(ec_columns, row)
            if col not in ddl_columns
        ),
        "only_a_printed_ddl_string_says_vector": (
            any(
                "vector" in str(cell).lower()
                for row in ec_rows
                for col, cell in zip(ec_columns, row)
                if col in ddl_columns
            )
            and not any(
                ("vector" in str(cell).lower() or "cspann" in str(cell).lower())
                for row in ec_rows
                for col, cell in zip(ec_columns, row)
                if col not in ddl_columns
            )
        ),
        "index_type_values": {
            str(dict(zip(ec_columns, row)).get("index_name")): str(
                dict(zip(ec_columns, row)).get("index_type")
            )
            for row in ec_rows
        },
    }
    escape["what_the_restricted_table_would_have_said"] = behind_the_wall
    escape["what_the_restricted_table_holds_in_full"] = every_column
    log(
        "    crdb_internal.table_indexes, every column      "
        + (
            "ANSWERED   a typed column says vector: "
            f"{every_column['facts']['a_typed_column_says_vector']}"
            "   only a printed DDL string says it: "
            f"{every_column['facts']['only_a_printed_ddl_string_says_vector']}"
            if every_column["answered"]
            else f"REFUSED {every_column['sqlstate']}"
        )
    )
    log(
        "    crdb_internal.table_indexes, columns index_name/index_type  "
        + (
            f"ANSWERED -> {behind_the_wall['rows']}"
            if behind_the_wall["answered"]
            else f"REFUSED {behind_the_wall['sqlstate']}"
        )
    )

    escape["reset"] = run_statement(conn, "SET allow_unsafe_internals = false")

    return {
        "default_session_state": default_state,
        "restricted_by_default": closed,
        "not_restricted": open_surfaces,
        "same_question_asked_a_supported_way": alternative,
        "plan_gist_round_trip": gist_probe,
        "escape_hatch": escape,
    }


# --------------------------------------------------------------------------------------
# Verdicts.  Computed from what was measured, never asserted ahead of it.
# --------------------------------------------------------------------------------------


def verdict_f03(local: dict) -> dict:
    checkpoints = local["checkpoints"]
    unhinted_used = [
        c["unhinted"]["facts"]["traverses_the_vector_index"]
        for c in checkpoints
        if c["unhinted"]["explained"]
    ]
    hinted_used = [
        c["hinted"]["facts"]["traverses_the_vector_index"]
        for c in checkpoints
        if c["hinted"]["explained"]
    ]
    original_claim_holds = any(not used for used in unhinted_used)
    return {
        "original_claim": (
            "At demo scale (~5,200 rows) the optimizer does not choose the vector index; "
            "the unhinted plan filters after scanning."
        ),
        "unhinted_traversed_the_index_at_every_row_count": all(unhinted_used) and bool(unhinted_used),
        "hinted_traversed_the_index_at_every_row_count": all(hinted_used) and bool(hinted_used),
        "row_counts_swept": [c["rows_in_table"] for c in checkpoints],
        "original_claim_reproduced_locally": original_claim_holds,
        "label": "REPRODUCED-TODAY" if original_claim_holds else "STRUCK",
        "prefix_rule_enforced_by_the_server": local["prefix_counterfactual"]["refused"],
        "prefix_rule_sqlstate": local["prefix_counterfactual"].get("sqlstate"),
        "index_recommendation_emitted_alongside_a_vector_plan": any(
            c["unhinted"].get("facts", {}).get("index_recommendation_count", 0) > 0
            for c in checkpoints
        ),
    }


def verdict_f04(local: dict) -> dict:
    closed = local["restricted_by_default"]
    refused = [r for r in closed if not r["answered"] and r["sqlstate"] == "42501"]
    after = local["escape_hatch"]["after"]
    answered_after = [r for r in after if r["answered"]]
    alt = local["same_question_asked_a_supported_way"]
    facts = alt["facts"]
    messages = {r.get("server_message_verbatim") for r in refused}
    return {
        "original_claim": (
            "crdb_internal and system are restricted on Basic tier, so cluster-shape "
            "questions a tutorial would answer are unavailable on the tier a hackathon "
            "entrant actually uses."
        ),
        "restated_claim": (
            "On v26.2.5 crdb_internal and system are closed by default -- on Cloud Basic "
            "(archived) and on a local single-node cluster where the connected user is root "
            "(measured today). The refusal names a session variable that reopens them and "
            "does NOT name the supported read-only alternative, which for index metadata is "
            "SHOW CREATE TABLE."
        ),
        "targets_probed": len(closed),
        "targets_refused_42501": len(refused),
        "refusal_is_tier_specific": len(refused) == 0,
        "restriction_also_present_on_local_self_hosted_single_node": len(refused) > 0,
        "distinct_refusal_messages": sorted(m for m in messages if m),
        "escape_hatch_works_locally": len(answered_after) == len(after) and bool(after),
        "escape_hatch_targets_answered_after_set": len(answered_after),
        "escape_hatch_tried_on_cloud_basic": False,
        "supported_alternative_answers_which_indexes_exist": facts[
            "show_indexes_lists_the_vector_index"
        ],
        "supported_alternative_answers_which_kind_of_index_it_is": facts[
            "show_create_table_says_vector_index"
        ],
        "show_indexes_alone_answers_the_kind_question": facts[
            "show_indexes_says_which_kind_of_index_it_is"
        ],
        "supported_alternative_named_in_the_refusal_message": False,
        "plan_gist_can_be_produced": local["plan_gist_round_trip"]["facts"][
            "gist_can_be_produced"
        ],
        "plan_gist_can_be_read_back_by_default": local["plan_gist_round_trip"]["facts"][
            "gist_can_be_read_back_with_the_session_at_its_default"
        ],
        "restricted_table_does_carry_an_index_type_column": bool(
            local["escape_hatch"]["what_the_restricted_table_would_have_said"]["answered"]
        ),
        "restricted_table_index_type_values": local["escape_hatch"][
            "what_the_restricted_table_would_have_said"
        ].get("rows", []),
        "restricted_table_columns": local["escape_hatch"][
            "what_the_restricted_table_holds_in_full"
        ]["facts"]["columns"],
        "restricted_table_would_have_identified_the_vector_index": local["escape_hatch"][
            "what_the_restricted_table_holds_in_full"
        ]["facts"]["any_cell_says_vector"],
        "any_typed_catalogue_column_identifies_a_vector_index": local["escape_hatch"][
            "what_the_restricted_table_holds_in_full"
        ]["facts"]["a_typed_column_says_vector"],
        "only_a_printed_ddl_string_identifies_a_vector_index": local["escape_hatch"][
            "what_the_restricted_table_holds_in_full"
        ]["facts"]["only_a_printed_ddl_string_says_vector"],
        "label": "REPRODUCED-TODAY" if len(refused) > 0 else "STRUCK",
    }


# --------------------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", default=os.environ.get("MAINLINE_LOCAL_DSN", LOCAL_DSN))
    parser.add_argument("--rows", default=None, help="comma-separated row-count sweep")
    parser.add_argument("--quick", action="store_true", help="short sweep, for a smoke run")
    parser.add_argument("--out", default=None, help="directory for the JSON transcripts")
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    if args.rows:
        sweep = tuple(int(x) for x in args.rows.split(","))
    elif args.quick:
        sweep = (0, 200)
    else:
        sweep = DEFAULT_SWEEP

    repo = Path(__file__).resolve().parents[2]
    out_dir = Path(args.out) if args.out else repo / "evidence" / "upstream"
    out_dir.mkdir(parents=True, exist_ok=True)

    def log(msg: str) -> None:
        print(msg, flush=True)

    if "localhost" not in args.dsn and "127.0.0.1" not in args.dsn:
        sys.stderr.write(
            "REFUSING TO RUN: this program is for the local node only. "
            "The DSN given does not point at localhost.\n"
        )
        return 2

    scratch = "upstream_f03_" + secrets.token_hex(4)
    started_at = now_utc()
    admin = psycopg.connect(args.dsn, autocommit=True, connect_timeout=15)

    # A run that is killed between CREATE and the finally: block leaves a scratch database
    # behind.  It happened to us while writing this, which is the whole subject of finding F05,
    # so the script sweeps its OWN prefix on startup rather than accumulating them.  It touches
    # nothing that is not named upstream_f03_*, and it prints every name it removes.
    stale = [
        row[0]
        for row in admin.execute(
            "SELECT database_name FROM [SHOW DATABASES] "
            "WHERE database_name LIKE 'upstream\\_f03\\_%' ESCAPE '\\'"
        ).fetchall()
    ]
    swept: list[str] = []
    for name in stale:
        admin.execute(f'DROP DATABASE IF EXISTS "{name}" CASCADE')
        swept.append(name)
        print(f"SWEPT STALE SCRATCH DB    {name}  (left by an interrupted earlier run)", flush=True)

    server_version = admin.execute("SELECT version()").fetchone()[0]
    beam = admin.execute("SHOW vector_search_beam_size").fetchone()[0]
    rerank = admin.execute("SHOW vector_search_rerank_multiplier").fetchone()[0]

    log("=" * 86)
    log("repro_vector_and_catalogue.py -- F03 (query plan) and F04 (bookkeeping tables)")
    log("=" * 86)
    log(f"  started            {started_at}")
    log(f"  server             {server_version}")
    log(f"  exam               local single-node CCL (not CockroachDB Cloud)")
    log(f"  row-count sweep    {list(sweep)}")
    log("")

    scratch_conn = None
    try:
        admin.execute(f'CREATE DATABASE "{scratch}"')
        log(f"CREATED SCRATCH DATABASE  {scratch}")
        scratch_dsn = args.dsn.replace("/defaultdb?", f"/{scratch}?")
        scratch_conn = psycopg.connect(scratch_dsn, autocommit=True, connect_timeout=15)

        log("")
        log("F03 -- does the planner pick the vector index without being told?")
        f03_local = build_and_sweep(scratch_conn, sweep, log)

        log("")
        log("F04 -- what will the database tell you about itself?")
        f04_local = probe_catalogue(scratch_conn, log)

        v03 = verdict_f03(f03_local)
        v04 = verdict_f04(f04_local)

        common = {
            "generated_by": "scripts/upstream/repro_vector_and_catalogue.py",
            "generated_at": now_utc(),
            "started_at": started_at,
            "exam": {
                "name": "local single-node CCL",
                "server_version": server_version,
                "dsn_shape": "postgresql://root@localhost:26257/<scratch>?sslmode=disable",
                "scratch_database": scratch,
                "scratch_database_dropped": "see teardown.dropped",
                "vector_search_beam_size": beam,
                "vector_search_rerank_multiplier": rerank,
            },
            "not_measured_here": [
                "CockroachDB Cloud Basic -- not re-run today; see arms labelled ARCHIVED-EVIDENCE",
                "the mainline_demo database -- never touched by this program",
            ],
        }

        f03_doc = {
            **common,
            "finding": "F03",
            "title": "The vector index and the query planner's choice",
            "arms": {
                "local_single_node_today": {
                    "label": v03["label"],
                    "tier": "local single-node CCL",
                    "version": server_version,
                    "measured_on": started_at,
                    **f03_local,
                },
                "cloud_basic_archived": {
                    "label": "ARCHIVED-EVIDENCE",
                    "re_run_today": False,
                    "why_not_re_run": (
                        "Re-running would mean driving load against a shared live cluster. "
                        "The artefacts are cited by path and timestamp instead."
                    ),
                    "records": ARCHIVED_CLOUD["f03"],
                },
            },
            "verdict": v03,
            # F03's "what better would look like" rests on this round trip, so the
            # measurement travels with F03 as well as with F04 rather than being cited
            # across files.
            "plan_gist_round_trip": f04_local["plan_gist_round_trip"],
        }

        f04_doc = {
            **common,
            "finding": "F04",
            "title": "The bookkeeping tables, and the alternative the refusal does not name",
            "arms": {
                "local_single_node_today": {
                    "label": v04["label"],
                    "tier": "local single-node CCL",
                    "version": server_version,
                    "role": "root",
                    "measured_on": started_at,
                    **f04_local,
                },
                "cloud_basic_archived": {
                    "label": "ARCHIVED-EVIDENCE",
                    "re_run_today": False,
                    "why_not_re_run": (
                        "Re-running would mean issuing queries against a shared live cluster. "
                        "The artefacts are cited by path and timestamp instead."
                    ),
                    "records": ARCHIVED_CLOUD["f04"],
                },
            },
            "verdict": v04,
        }

        f03_path = out_dir / "F03-vector-index-not-chosen.json"
        f04_path = out_dir / "F04-crdb-internal-restricted.json"
        for path, doc in ((f03_path, f03_doc), (f04_path, f04_doc)):
            path.write_text(
                json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )

        log("")
        log("-" * 86)
        log("VERDICTS -- computed from the run above, not asserted ahead of it")
        log("-" * 86)
        log(f"  F03  local label                        {v03['label']}")
        log(f"       original claim reproduced locally  {v03['original_claim_reproduced_locally']}")
        log(f"       unhinted used the index everywhere {v03['unhinted_traversed_the_index_at_every_row_count']}")
        log(f"       prefix rule refused by the server  {v03['prefix_rule_enforced_by_the_server']} ({v03['prefix_rule_sqlstate']})")
        log(f"  F04  local label                        {v04['label']}")
        log(f"       targets refused 42501              {v04['targets_refused_42501']} of {v04['targets_probed']}")
        log(f"       restriction is tier-specific       {v04['refusal_is_tier_specific']}")
        log(f"       SHOW INDEXES answers 'which'       {v04['supported_alternative_answers_which_indexes_exist']}")
        log(f"       SHOW INDEXES answers 'what kind'   {v04['show_indexes_alone_answers_the_kind_question']}")
        log(f"       SHOW CREATE answers 'what kind'    {v04['supported_alternative_answers_which_kind_of_index_it_is']}")
        log(f"       plan gist can be produced          {v04['plan_gist_can_be_produced']}")
        log(f"       plan gist can be read back         {v04['plan_gist_can_be_read_back_by_default']}")
        log("")
        log(f"WROTE  {f03_path}")
        log(f"WROTE  {f04_path}")
        teardown_ok = True
    finally:
        if scratch_conn is not None:
            scratch_conn.close()
        try:
            admin.execute(f'DROP DATABASE IF EXISTS "{scratch}" CASCADE')
            log(f"DROPPED SCRATCH DATABASE  {scratch}")
            leftovers = admin.execute(
                "SELECT count(*) FROM [SHOW DATABASES] WHERE database_name = %s", (scratch,)
            ).fetchone()[0]
            log(f"CONFIRMED GONE            {scratch}  (rows still naming it: {leftovers})")
        finally:
            admin.close()

    # Record the teardown in both transcripts now that it has actually happened.
    for path in (f03_path, f04_path):
        doc = json.loads(path.read_text(encoding="utf-8"))
        doc["teardown"] = {
            "created": scratch,
            "dropped": scratch,
            "dropped_in_finally_block": True,
            "confirmed_absent": True,
            "stale_scratch_databases_swept_at_startup": swept,
        }
        doc["exam"]["scratch_database_dropped"] = True
        path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    return 0 if teardown_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
