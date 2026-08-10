#!/usr/bin/env python
# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Judge access: provision the read-only login, prove it from the other side, run the pack.

THREE SUBCOMMANDS, AND WHY THEY ARE ONE PROGRAM
-----------------------------------------------
``provision``   apply ``verticals/mainline/db/demo/judge_grants.sql``, then connect AS
                ``mainline_judge`` and assert what it can and cannot read.
``judge-run``   execute the sixteen questions in ``verticals/mainline/demo/judge/QUESTIONS.yaml``
                against the live cluster, over Managed MCP and/or pgwire, and write
                ``evidence/deploy/judge-run.json``.
``credentials`` print the block that goes in ``docs/deploy/JUDGE-PACK.md``.

They share a program because they share a claim. The credential block is only publishable if the
probes passed, and the pack run is only meaningful if it ran as the identity the credential names.
Splitting them would let a stale credential block outlive the run that justified it.

WHAT THIS PROGRAM MEASURED, ON 2026-08-10, THAT NOTHING ELSE IN THE REPOSITORY KNEW
-----------------------------------------------------------------------------------
**Managed MCP is available on SERVERLESS/Basic.** ``docs/leads/deploy-plan.md`` §6 lists "Managed
MCP is unavailable on Basic" as a risk and asks this worker to measure it. It is available:
``initialize`` against ``https://cockroachlabs.cloud/mcp`` returns HTTP 200 with
``serverInfo.name = "cockroachdb-cloud"``, protocol ``2025-06-18``, and twelve tools — including
the two the pack uses, ``select_query`` and ``explain_query``.

**The endpoint runs as a dedicated SQL user named ``managed-mcp``.** That is day-1 check GT-10,
which ``verticals/mainline/demo/judge/FALLBACK.md`` records as unanswered and assumes
pessimistically. ``SELECT current_user`` over the endpoint answers it: not ``root``, not the
cluster owner, a purpose-built identity.

**Three of the four negatives are enforced by the MCP server itself**, as a schema blocklist that
precedes SQL privilege: ``crdb_internal``, ``pg_catalog`` and ``information_schema`` all come back
``query references a restricted schema: access to "X" is blocked for security reasons``. That is a
stronger guarantee than a grant, because no privilege change on our side can weaken it.

**The fourth negative does not hold, and the difference matters.**
``SELECT count(*) FROM mainline_qa.v_disposition_profile`` over MCP returns ``{"rows":[{"n":0}]}``
— zero rows, not a refusal. N01 claims an MCP identity *cannot read* per-person deliberation
measurements. Measured, it reads them and finds none. Those are different facts and only one of
them is a security property; RLS-MATRIX.yaml's own warning is that zero rows is indistinguishable
from nothing being wrong.

**And the key cannot be published.** ``create_database`` over the same endpoint with the same
credential returned ``{"success": true}`` — a database was created on the production demo cluster
and dropped immediately afterwards. FALLBACK.md Branch A rests on the premise that the MCP write
surface is "insert-only and bound to ``mainline_meas.external_attestation``". It is not: the tool
list carries ``create_database``, ``create_table`` and ``insert_rows``, and the credential that
reaches them is the account's Cloud service-account key, which also enumerates every cluster the
account owns. So the branch that executes is B — **not** because Managed MCP is unavailable, which
was the anticipated reason, but because the credential that reaches it is far too powerful to hand
to a stranger. The published credential is the read-only SQL login instead.

WHY THE PACK'S OWN RUNNER IS NOT INVOKED FOR THE MCP CHANNEL
-------------------------------------------------------------
``verticals/mainline/demo/judge/`` belongs to the agents-mcp domain and this worker does not edit
it. Its runner is imported and its questions are loaded through its own ``pack.load_pack`` — the
questions executed here are byte-for-byte the questions in ``QUESTIONS.yaml``, not a re-typed copy.

But ``cli.py run --via mcp`` cannot reach the live surface today, and this program records why
rather than routing around it silently. ``mainline_mcp.client.ToolDialect`` sends the statement as
``statement=`` and omits ``database=``; the live server requires ``query=`` and makes ``database``
mandatory. The result is ``ToolCallFailed: tools/call: must contain exactly one statement`` on the
first positive question — the session, the auth and the cluster pin are all fine, the argument
names are not. That dataclass's own docstring anticipates exactly this ("a live-surface difference
is a one-line fix"), so the fix is two field values in one object, and it is theirs to make.

``cli.py run --via sql`` does not reach the end either: it calls ``envelope.enforce`` on every
question including the negatives, and N01 names ``mainline_qa``, which the envelope refuses
outright — ``QaSchemaRefused`` propagates as an uncaught exception. FALLBACK.md B2 says the runner
"skips them here, with the reason printed". It raises instead.

Both are reported in this program's evidence and in ``docs/deploy/JUDGE-PACK.md``. Neither file is
touched.

NOTHING HERE PRINTS A SECRET
-----------------------------
Passwords are generated, written to SSM by the caller, and returned once. Every DSN that reaches
stdout or an evidence file goes through :func:`scripts.deploy.cloud_chain.redact`. The MCP key is
read from the environment and never echoed, not even truncated.
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import json
import os
import secrets
import sys
import time
from pathlib import Path
from typing import Any, Final
from urllib.parse import urlsplit, urlunsplit

import psycopg

if __package__ in (None, ""):  # direct execution: `python scripts/deploy/judge_access.py`
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.deploy.cloud_chain import (
    load_dotenv,
    one_line,
    redact,
    repo_root,
    rewrite_dsn,
    sqlstate_of,
)

# WINDOWS. This program is run from a `cp1252` console on the machine that deploys it, and a
# box-drawing character in a banner raised `UnicodeEncodeError` *after* the password had already
# been rotated — so the credential was changed on the live cluster and then lost. Never again:
# stdout and stderr degrade unencodable characters instead of raising. A cosmetic `?` in a banner
# is not worth an exception between `ALTER USER` and the line that prints the result.
for _stream in (sys.stdout, sys.stderr):
    with contextlib.suppress(AttributeError, ValueError):
        _stream.reconfigure(errors="replace")  # type: ignore[union-attr]

EXIT_OK: Final = 0
EXIT_PROBE_DISAGREED: Final = 1
EXIT_USAGE: Final = 2
EXIT_NOT_RUN: Final = 3

JUDGE_USER: Final = "mainline_judge"

#: ``insufficient_privilege``. What a grant that was never made looks like from the other side.
REFUSED: Final = "42501"

#: The audit surface, in the order judge_grants.sql names it. Asserted equal to
#: ``cloud_roles.AUDIT_VIEWS`` at run time — two copies of a security-relevant list is one too
#: many, and a divergence should be a failed run rather than a quiet difference.
AUDIT_VIEWS: Final[tuple[str, ...]] = (
    "v_agent_actions",
    "v_blame_coverage",
    "v_cbm_ledger",
    "v_changefeed_health",
    "v_disposition_coverage",
    "v_fixity_coverage",
    "v_gate_latency_daily",
    "v_ledger_health",
    "v_open_gate_summary",
    "v_recall_conservation",
    "v_silence_summary",
    "v_txn_restart_daily",
    "v_unused_indexes",
    "v_weakenings_without_disposition",
)

#: The live Managed MCP surface. Pinned as a constant so the evidence file and the documentation
#: quote the same string.
MCP_ENDPOINT: Final = "https://cockroachlabs.cloud/mcp"
MCP_PROTOCOL: Final = "2025-06-18"

#: MEASURED, not documented. ``mainline_mcp.client.ToolDialect`` defaults to ``statement`` and
#: omits ``database``; the live server requires these two. See the module docstring.
MCP_SQL_ARGUMENT: Final = "query"
MCP_DATABASE_ARGUMENT: Final = "database"

GRANTS_SQL: Final = "verticals/mainline/db/demo/judge_grants.sql"
QUESTIONS_YAML: Final = "verticals/mainline/demo/judge/QUESTIONS.yaml"

#: What each known divergence MEANS. Keyed ``(channel, qid)``. Every entry here was measured on
#: 2026-08-10 against the live cluster; none is a prediction.
#:
#: The two channels turn out to be COMPLEMENTARY rather than redundant, which is the most useful
#: thing this run established. Each covers the other's gap:
#:
#:   N01  fails over MCP, passes over SQL  — the judge login is more tightly scoped than
#:                                           `managed-mcp` on the one schema that matters most
#:   N03  passes over MCP, fails over SQL  — a server-side schema blocklist is a property of the
#:   N04                                     MCP transport and pgwire has no equivalent
#:   Q10  passes over MCP, fails over SQL  — the judge login deliberately holds no base-table
#:   Q10C                                    privilege, which is the point of it
#:
#: Publishing both channels is therefore stronger than publishing either, and the honest summary
#: is that ONE property (N01) is unmet by any channel we control.
DISPOSITIONS: Final[dict[tuple[str, str], dict[str, Any]]] = {
    ("mcp", "N01"): {
        "disposition": "real_gap",
        "by_design": False,
        "reading": (
            "mainline_qa IS readable by the Managed MCP identity. N01 claims an MCP identity "
            "cannot read per-person deliberation measurement; measured, `managed-mcp` runs "
            "SELECT count(*) FROM mainline_qa.v_disposition_profile successfully. GRANTS.yaml "
            "S14 and PACK.md's envelope both assert this is impossible. It is not. The read-only "
            "SQL login refuses the same statement with 42501 (no USAGE on the schema), so the "
            "credential this deployment actually publishes is the tighter of the two."
        ),
    },
    ("sql", "N03"): {
        "disposition": "wrong_transport",
        "by_design": True,
        "reading": (
            "pg_catalog is readable over pgwire by every login — measured, 654 rows as "
            "mainline_judge. It is a per-user-filtered catalogue, not a secret. N03 is a claim "
            "about the MCP transport's schema blocklist, where it passes. FALLBACK.md B2 says "
            "exactly this: reporting a pass here would invert the question's meaning."
        ),
    },
    ("sql", "N04"): {
        "disposition": "wrong_transport",
        "by_design": True,
        "reading": (
            "information_schema is readable over pgwire by every login — measured, 446 rows as "
            "mainline_judge — and is how any client introspects. Same reading as N03: the "
            "property belongs to the MCP transport, where it passes."
        ),
    },
    ("sql", "Q10"): {
        "disposition": "by_grant_design",
        "by_design": True,
        "reading": (
            "42501 on mainline.event_cue_embedding. The plan-proof questions read a base table, "
            "and the judge login holds SELECT on the fourteen mainline_audit views and on no "
            "base relation anywhere. This failure IS the grant working. The plan proof is "
            "available over the MCP channel, which runs as a different identity."
        ),
    },
    ("sql", "Q10C"): {
        "disposition": "by_grant_design",
        "by_design": True,
        "reading": (
            "42501 on mainline.event_cue_coarse, for the same reason as Q10: the judge login "
            "holds no base-table privilege. Granting it to make this line green would widen the "
            "published credential to make a test pass."
        ),
    },
}


def utc_now() -> str:
    return dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def generate_password() -> str:
    """A 32-character URL-safe secret.

    URL-safe because the value is inlined into ``ALTER USER ... PASSWORD '...'`` — CockroachDB
    takes no placeholder there — and an alphabet with no quote, backslash or space in it makes
    that inlining safe by construction rather than by an escaping routine somebody has to get
    right. It also survives being pasted into a DSN without shell quoting games.
    """
    return secrets.token_urlsafe(24)


def as_user(dsn: str, user: str, password: str, database: str) -> str:
    """The same DSN with the userinfo replaced, everything else carried over untouched.

    A Cloud Basic DSN's query string is load-bearing — it carries the routing id — so rebuilding
    it by hand is how a probe ends up testing a different cluster from the one being provisioned.
    An empty *password* sends none, which is the only thing that works against the insecure local
    node.
    """
    parts = urlsplit(rewrite_dsn(dsn, database=database, application_name="mainline-judge-probe"))
    host = parts.hostname or "localhost"
    port = f":{parts.port}" if parts.port else ""
    userinfo = f"{user}:{password}@" if password else f"{user}@"
    return urlunsplit(
        (parts.scheme, f"{userinfo}{host}{port}", parts.path, parts.query, parts.fragment)
    )


# ═══════════════════════════════════════════════════════════════════════════════════════
# provisioning
# ═══════════════════════════════════════════════════════════════════════════════════════


def split_statements(sql: str) -> list[str]:
    """Split the grants file into statements: strip comments FIRST, then split on ``;``.

    THE ORDER IS THE WHOLE FUNCTION, and getting it backwards is a real bug that this program
    shipped for one run. Splitting on ``;`` first tears comment blocks apart wherever the PROSE
    contains a semicolon — "a grant is a claim about intent; a 42501 is evidence about behaviour"
    is one of several in the grants file — and the fragment after the split no longer begins with
    ``--``, so it survives comment-stripping and is sent to the server as SQL. Observed: seven
    ``42601`` syntax errors and one silently missing ``GRANT`` that had been glued onto the tail
    of a comment, which is the dangerous half. A judge would have found thirteen readable views
    where the reviewable list says fourteen.

    Deliberately still simple after the fix: the file it parses is one this worker owns and
    contains no dollar quoting, no string literal bearing a semicolon, and no procedure body. A
    general SQL splitter here would be a second parser to keep correct for no benefit. If the file
    ever grows a construct this cannot handle, the right move is to stop using this, not to grow
    it — and ``apply_grants`` counting statements against the file's own ``GRANT``/``REVOKE``
    line count is what would catch that.
    """
    # Cut every line at its first `--`, which removes whole-line banners AND the trailing
    # `-- Q02` markers that sit after a statement's semicolon. Without the second half, each
    # marker migrates into the FOLLOWING fragment and every applied statement arrives with a
    # stray comment glued to its front — harmless to the server, and exactly the kind of thing
    # that makes a later reader distrust the log. Safe here because the grants file contains no
    # string literal, so no `--` can be inside one.
    uncommented = "\n".join(line.split("--", 1)[0] for line in sql.splitlines())
    return [statement.strip() for statement in uncommented.split(";") if statement.strip()]


def apply_grants(
    conn: psycopg.Connection[Any], grants_path: Path, database: str
) -> list[dict[str, Any]]:
    """Apply the grants file, substituting ``@DATABASE@``, skipping absent objects.

    GRANTS.yaml's contract for ``grants apply`` is explicit and is followed here: a row whose
    object is absent from the connected database is SKIPPED WITH A WARNING, never an error,
    because a cluster migrated only part-way must still be grantable. Everything else is a real
    failure. ``42P01`` on this path is expected exactly once — see the grants file's §4.
    """
    text = grants_path.read_text(encoding="utf-8").replace("@DATABASE@", f'"{database}"')
    statements = split_statements(text)

    # THE PARSER MUST AGREE WITH THE FILE. Count the executable verbs the file starts a line with
    # and require the split to produce exactly that many statements. This is the assertion that
    # would have caught the comment/split ordering bug immediately instead of one run later: a
    # torn comment produces extra fragments, and a GRANT glued to a comment tail produces one
    # fewer real statement than the file visibly contains.
    declared = sum(
        1
        for line in text.splitlines()
        if line.lstrip().upper().startswith(("GRANT ", "REVOKE ", "CREATE ROLE", "ALTER "))
        and not line.lstrip().startswith("--")
    )
    if declared != len(statements):
        raise RuntimeError(
            f"{grants_path.name}: the file declares {declared} executable statements but the "
            f"splitter produced {len(statements)}. Refusing to apply a partially parsed grant "
            "file — a missing GRANT here is a judge staring at an empty view."
        )

    log: list[dict[str, Any]] = []
    for statement in statements:
        summary = " ".join(statement.split())[:120]
        try:
            conn.execute(statement)  # type: ignore[arg-type]
        except psycopg.Error as exc:
            state = sqlstate_of(exc)
            if state in {"42P01", "42883", "3F000"}:
                log.append(
                    {
                        "statement": summary,
                        "skipped": True,
                        "sqlstate": state,
                        "why": one_line(exc),
                    }
                )
            else:
                log.append(
                    {
                        "statement": summary,
                        "ok": False,
                        "sqlstate": state,
                        "error": one_line(exc),
                    }
                )
        else:
            log.append({"statement": summary, "ok": True})
    return log


# The probe list IS the security surface: each entry is one assertion with its own message, and a
# generic loop would report "a denial failed" where the useful sentence names which one.
def probe_as_judge(dsn: str, password: str, database: str) -> dict[str, Any]:
    """Connect AS ``mainline_judge`` and assert both directions.

    Both directions, because **a login that can read nothing passes every negative test.** The
    positives are what make the negatives mean something.
    """
    judge_dsn = as_user(dsn, JUDGE_USER, password, database)
    result: dict[str, Any] = {
        "connected": False,
        "identity": None,
        "views": [],
        "denials": [],
        "readable": 0,
        "non_empty": 0,
        "refused": 0,
    }
    try:
        conn = psycopg.connect(judge_dsn, autocommit=True, connect_timeout=30)
    except psycopg.Error as exc:
        state = sqlstate_of(exc)
        result["error"] = f"[{state}] {one_line(exc)}"
        result["dsn"] = redact(judge_dsn)
        # "I HAD NO CREDENTIAL" IS NOT "THE GRANTS ARE BROKEN", and a summary reading
        # `0/14 readable` for the first of those is a lie told by an honest program. This is the
        # same NOT-RUN distinction the judge pack draws, and it is needed here for the same
        # reason: a cluster that requires a password, probed without one, must report that it was
        # never probed. Observed against Cloud on 2026-08-10 when `--rotate` was omitted.
        if state in {"28P01", "28000"} or not password:
            result["not_run"] = True
            result["reason"] = (
                "the judge login could not authenticate, so NOTHING was probed and the grants "
                "above are UNVERIFIED. Re-run with --rotate to issue a password, or supply one "
                "with --password-from-env. (The local insecure node needs no password; a Cloud "
                "cluster does.)"
            )
        return result
    result["connected"] = True
    try:
        row = conn.execute("SELECT current_user, current_database()").fetchone()
        result["identity"] = {"user": row[0], "database": row[1]} if row else None

        # ── the positives: every named view must answer ──────────────────────────────────
        for view in AUDIT_VIEWS:
            started = time.monotonic()
            try:
                # `view` comes from the AUDIT_VIEWS constant tuple in this module, never from
                # input; CockroachDB takes no placeholder for a relation name.
                statement = f"SELECT count(*) FROM mainline_audit.{view}"  # noqa: S608
                got = conn.execute(statement).fetchone()  # type: ignore[arg-type]
                rows = int(got[0]) if got else 0
            except psycopg.Error as exc:
                conn.rollback()
                result["views"].append(
                    {
                        "view": f"mainline_audit.{view}",
                        "readable": False,
                        "sqlstate": sqlstate_of(exc),
                        "detail": one_line(exc)[:220],
                    }
                )
                result["refused"] += 1
            else:
                result["views"].append(
                    {
                        "view": f"mainline_audit.{view}",
                        "readable": True,
                        "rows": rows,
                        "ms": round((time.monotonic() - started) * 1000, 1),
                    }
                )
                result["readable"] += 1
                result["non_empty"] += 1 if rows else 0

        # ── the negatives: each must be refused, and the SQLSTATE is the evidence ────────
        #
        # `pg_catalog` and `information_schema` are NOT in this list, and their absence is a
        # finding rather than an oversight. Measured as this login: pg_catalog.pg_class returns
        # 654 rows and information_schema.tables returns 446. Both are per-user-filtered
        # catalogues and are readable by any login on CockroachDB. The judge pack's N03 and N04
        # assert they are unreachable — which is true over the Managed MCP channel, whose server
        # blocks them by name, and false over pgwire. Asserting it here would manufacture a pass.
        denials = [
            (
                "mainline_qa.v_disposition_profile",
                "SELECT count(*) FROM mainline_qa.v_disposition_profile",
            ),
            ("mainline_qa.v_my_record", "SELECT count(*) FROM mainline_qa.v_my_record"),
            (
                "mainline_qa.v_standing_components",
                "SELECT count(*) FROM mainline_qa.v_standing_components",
            ),
            ("crdb_internal.jobs", "SELECT count(*) FROM crdb_internal.jobs"),
            ("crdb_internal.tables", "SELECT count(*) FROM crdb_internal.tables"),
            ("base table mainline.permit", "SELECT count(*) FROM mainline.permit"),
            ("base table mainline.disposition", "SELECT count(*) FROM mainline.disposition"),
            ("base table mainline_meas.standing", "SELECT count(*) FROM mainline_meas.standing"),
        ]
        for label, sql in denials:
            try:
                got = conn.execute(sql).fetchone()  # type: ignore[arg-type]
            except psycopg.Error as exc:
                state = sqlstate_of(exc)
                result["denials"].append(
                    {
                        "target": label,
                        "refused": True,
                        "sqlstate": state,
                        "expected_sqlstate": REFUSED,
                        "as_expected": state == REFUSED,
                        "detail": one_line(exc)[:220],
                    }
                )
                conn.rollback()
            else:
                # READ SUCCEEDED WHERE IT MUST NOT. Zero rows is not a refusal and is recorded as
                # a failure, loudly, because an empty result from a forbidden object is the exact
                # shape of a security hole that looks like a pass.
                result["denials"].append(
                    {
                        "target": label,
                        "refused": False,
                        "sqlstate": "00000",
                        "expected_sqlstate": REFUSED,
                        "as_expected": False,
                        "detail": (
                            f"READ SUCCEEDED, rows={got[0] if got else 0} — this must not happen"
                        ),
                    }
                )
    finally:
        conn.close()
    return result


def verdict_for(probe: dict[str, Any]) -> tuple[str, list[str]]:
    """``PROVEN`` only when both directions held. One sentence per failure."""
    failures: list[str] = []
    if probe.get("not_run"):
        return "NOT RUN", [str(probe.get("reason"))]
    if not probe.get("connected"):
        failures.append(f"the judge login could not connect: {probe.get('error', 'unknown')}")
        return "NOT PROVEN", failures
    if probe["readable"] != len(AUDIT_VIEWS):
        failures.append(
            f"{probe['readable']} of {len(AUDIT_VIEWS)} audit views were readable; "
            "the judge surface is incomplete"
        )
    if probe["non_empty"] == 0:
        failures.append(
            "every audit view came back empty. Under FORCE ROW LEVEL SECURITY that is what a "
            "missing view_owner_read policy looks like, and it is indistinguishable from "
            "'nothing is wrong' (RLS-MATRIX.yaml). Refusing to certify."
        )
    for denial in probe["denials"]:
        if not denial["as_expected"]:
            failures.append(f"{denial['target']}: {denial['detail']}")
    return ("PROVEN" if not failures else "NOT PROVEN"), failures


# ═══════════════════════════════════════════════════════════════════════════════════════
# the Managed MCP channel — measured against the live endpoint
# ═══════════════════════════════════════════════════════════════════════════════════════


class McpSession:
    """A minimal Streamable-HTTP MCP client, written to the surface that actually answered.

    ``packages/mainline-mcp`` exists and is the better client — it models the documented limits and
    diagnoses them. It is not used here because its argument names do not match the live server
    (see the module docstring) and this worker does not edit that package. This class is forty
    lines and does one thing: put the pack's questions on the wire and bring back what the server
    said.
    """

    def __init__(self, api_key: str, cluster_id: str, *, timeout: float = 40.0) -> None:
        import httpx

        self._http = httpx.Client(timeout=timeout)
        self._cluster_id = cluster_id
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "mcp-cluster-id": cluster_id,
        }
        self._id = 0
        self.server_info: dict[str, Any] = {}

    @staticmethod
    def _events(text: str) -> list[dict[str, Any]]:
        """Decode ``text/event-stream``. The server answers a POST with SSE, not plain JSON."""
        out: list[dict[str, Any]] = []
        for line in text.splitlines():
            if line.startswith("data: "):
                try:
                    out.append(json.loads(line[6:]))
                except json.JSONDecodeError:
                    continue
        return out

    def _post(self, message: dict[str, Any]) -> Any:
        response = self._http.post(MCP_ENDPOINT, json=message, headers=self._headers)
        response.raise_for_status()
        if session := response.headers.get("mcp-session-id"):
            self._headers["Mcp-Session-Id"] = session
        for event in self._events(response.text):
            if "result" in event or "error" in event:
                return event.get("result", event.get("error"))
        return None

    def initialize(self) -> dict[str, Any]:
        self._id += 1
        result = self._post(
            {
                "jsonrpc": "2.0",
                "id": self._id,
                "method": "initialize",
                "params": {
                    "protocolVersion": MCP_PROTOCOL,
                    "capabilities": {},
                    "clientInfo": {"name": "mainline-judge-access", "version": "1.0.0"},
                },
            }
        )
        self._headers["MCP-Protocol-Version"] = MCP_PROTOCOL
        self._http.post(
            MCP_ENDPOINT,
            json={"jsonrpc": "2.0", "method": "notifications/initialized"},
            headers=self._headers,
        )
        self.server_info = (result or {}).get("serverInfo", {})
        return result or {}

    def tools(self) -> list[str]:
        self._id += 1
        result = self._post({"jsonrpc": "2.0", "id": self._id, "method": "tools/list"})
        return sorted(t["name"] for t in (result or {}).get("tools", []))

    def call(self, tool: str, arguments: dict[str, Any]) -> tuple[bool, Any, int]:
        """Return ``(ok, payload, bytes)``. ``ok`` is false for a tool-level refusal."""
        self._id += 1
        started = time.monotonic()
        result = self._post(
            {
                "jsonrpc": "2.0",
                "id": self._id,
                "method": "tools/call",
                "params": {"name": tool, "arguments": arguments},
            }
        )
        elapsed = round((time.monotonic() - started) * 1000, 1)
        if result is None:
            return False, {"message": "no result in the response stream"}, elapsed
        if "message" in result and "content" not in result:
            return False, result, elapsed
        text = ""
        try:
            text = result["content"][0]["text"]
        except (KeyError, IndexError, TypeError):
            return True, result, elapsed
        try:
            return True, json.loads(text), elapsed
        except json.JSONDecodeError:
            return True, {"text": text}, elapsed

    def close(self) -> None:
        self._http.close()


def load_questions(root: Path) -> list[Any]:
    """Load the pack through its OWN loader, so these are its questions and not a copy."""
    demo_dir = root / "verticals/mainline/demo"
    if str(demo_dir) not in sys.path:
        sys.path.insert(0, str(demo_dir))
    from judge.pack import load_pack  # type: ignore[import-not-found]

    return list(load_pack(root / QUESTIONS_YAML))


def _bound_statement(question: Any, root: Path) -> str | None:
    """Ask the PACK's own binder for the literal-bearing form of an EXPLAIN question.

    ``drift.bind_and_measure`` reads the vector width out of the ``CREATE TABLE`` the question
    names, so a column widened from 1024 to 1536 changes the literal here without anybody editing
    this file. Returns the stripped statement, or ``None`` when the binder declined — which is a
    NOT-RUN for that question, never a pass.
    """
    demo_dir = root / "verticals/mainline/demo"
    if str(demo_dir) not in sys.path:
        sys.path.insert(0, str(demo_dir))
    from judge.drift import bind_and_measure  # type: ignore[import-not-found]

    bound, _problems = bind_and_measure(question, repo_root=root)
    if bound is None or not bound.sql:
        return None
    text = bound.sql.rstrip().rstrip(";")
    head, _, tail = text.partition("\n")
    if head.strip().upper() == "EXPLAIN":
        return tail.lstrip()
    if text.upper().startswith("EXPLAIN "):
        return text[len("EXPLAIN ") :].lstrip()
    return text


def run_pack_over_mcp(  # noqa: PLR0915 - one block per question shape, and each carries the
    # sentence that explains its own verdict.
    questions: list[Any],
    api_key: str,
    cluster_id: str,
    database: str,
    root: Path,
) -> dict[str, Any]:
    """Execute every question over the live Managed MCP endpoint, one verdict each."""
    session = McpSession(api_key, cluster_id)
    report: dict[str, Any] = {
        "channel": "mcp",
        "endpoint": MCP_ENDPOINT,
        "cluster_id": cluster_id,
        "database": database,
        "ran": False,
        "results": [],
    }
    try:
        initialised = session.initialize()
        report["ran"] = True
        report["protocol_version"] = initialised.get("protocolVersion")
        report["server_info"] = initialised.get("serverInfo", {})
        report["tools"] = session.tools()

        identity_ok, identity, _ = session.call(
            "select_query",
            {MCP_DATABASE_ARGUMENT: database, MCP_SQL_ARGUMENT: "SELECT current_user AS u"},
        )
        report["sql_identity"] = (
            identity.get("rows", [{}])[0].get("u") if identity_ok else "unresolved"
        )

        for question in questions:
            tool = "explain_query" if question.verb == "explain_query" else "select_query"
            statement = question.sql.rstrip().rstrip(";")

            if tool == "explain_query":
                # TWO transformations, both measured rather than guessed.
                #
                # 1. The `explain_query` TOOL prepends its own EXPLAIN. The pack writes Q10 and
                #    Q10C as complete `EXPLAIN\nSELECT ...` statements, because over pgwire that
                #    is what you send. Passing them through unchanged returns
                #    `EXPLAIN is not allowed for EXPLAIN statements`. Note the separator is a
                #    NEWLINE, not a space — a `startswith("EXPLAIN ")` test silently does nothing
                #    here, which it did, once.
                #
                # 2. The statements carry `$1..$4` placeholders and the MCP tool binds nothing.
                #    The literals come from the pack's OWN binder, `drift.bind_and_measure`, which
                #    reads the vector width out of the `CREATE TABLE` the question names. Writing
                #    a 1024-float literal here instead would be this program asserting a schema
                #    fact it did not read.
                head, _, tail = statement.partition("\n")
                if head.strip().upper() == "EXPLAIN":
                    statement = tail.lstrip()
                elif statement.upper().startswith("EXPLAIN "):
                    statement = statement[len("EXPLAIN ") :].lstrip()
                bound = _bound_statement(question, root)
                if bound is None:
                    entry_note = (
                        "the pack's binder produced no statement, so the placeholders are "
                        "unbound and nothing was sent"
                    )
                    report["results"].append(
                        {
                            "qid": question.qid,
                            "verb": question.verb,
                            "negative": question.is_negative,
                            "answered": False,
                            "expected": "answered",
                            "verdict": "FAIL",
                            "why": entry_note,
                        }
                    )
                    continue
                statement = bound

            argument = "query" if tool == "explain_query" else MCP_SQL_ARGUMENT
            ok, payload, ms = session.call(
                tool, {MCP_DATABASE_ARGUMENT: database, argument: statement}
            )
            entry: dict[str, Any] = {
                "qid": question.qid,
                "verb": question.verb,
                "negative": question.is_negative,
                "ms": ms,
                "answered": ok,
            }
            if ok:
                rows = payload.get("rows") if isinstance(payload, dict) else None
                entry["rows"] = len(rows) if isinstance(rows, list) else None
                entry["bytes"] = len(json.dumps(payload))
            else:
                entry["refusal"] = (payload or {}).get("message", "")[:300]

            # A NEGATIVE PASSES ONLY BY BEING REFUSED. A negative that answers with zero rows is
            # a FAILURE here, not a pass — that is the N01 case, and calling it green would
            # invert the claim the question exists to make.
            if question.is_negative:
                entry["expected"] = "refused"
                entry["verdict"] = "PASS" if not ok else "FAIL"
                if ok:
                    entry["why"] = (
                        f"the statement ANSWERED (rows={entry.get('rows')}). A negative that "
                        "returns an empty result has not been refused; zero rows and 'you may "
                        "not ask' are different facts."
                    )
            else:
                entry["expected"] = "answered"
                entry["verdict"] = "PASS" if ok else "FAIL"
            report["results"].append(entry)
    except Exception as exc:  # noqa: BLE001 - the transport failure IS the finding
        report["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        session.close()
    passed = sum(1 for r in report["results"] if r.get("verdict") == "PASS")
    report["passed"] = passed
    report["total"] = len(report["results"])
    return report


def run_pack_over_sql(questions: list[Any], dsn: str, database: str, user: str) -> dict[str, Any]:
    """Execute every question over pgwire as *user*, one verdict each."""
    report: dict[str, Any] = {
        "channel": "sql",
        "database": database,
        "identity": user,
        "ran": False,
        "results": [],
    }
    try:
        conn = psycopg.connect(dsn, autocommit=True, connect_timeout=30)
    except psycopg.Error as exc:
        report["error"] = f"[{sqlstate_of(exc)}] {one_line(exc)}"
        return report
    report["ran"] = True
    try:
        row = conn.execute("SELECT current_user").fetchone()
        report["sql_identity"] = row[0] if row else None
        for question in questions:
            started = time.monotonic()
            entry: dict[str, Any] = {
                "qid": question.qid,
                "verb": question.verb,
                "negative": question.is_negative,
            }
            try:
                cursor = conn.execute(question.sql.rstrip().rstrip(";"))  # type: ignore[arg-type]
                rows = cursor.fetchall()
            except psycopg.Error as exc:
                conn.rollback()
                entry.update(
                    answered=False,
                    sqlstate=sqlstate_of(exc),
                    refusal=one_line(exc)[:300],
                )
            else:
                entry.update(answered=True, sqlstate="00000", rows=len(rows))
            entry["ms"] = round((time.monotonic() - started) * 1000, 1)

            if question.is_negative:
                entry["expected"] = "refused"
                entry["verdict"] = "PASS" if not entry["answered"] else "FAIL"
                if entry["answered"]:
                    entry["why"] = (
                        "answered over pgwire. FALLBACK.md B2 says this exactly: over a SQL "
                        "connection these statements can succeed, and reporting a pass would "
                        "invert their meaning. The property is about the MCP transport."
                    )
            else:
                entry["expected"] = "answered"
                entry["verdict"] = "PASS" if entry["answered"] else "FAIL"
            report["results"].append(entry)
    finally:
        conn.close()
    report["passed"] = sum(1 for r in report["results"] if r.get("verdict") == "PASS")
    report["total"] = len(report["results"])
    return report


# ═══════════════════════════════════════════════════════════════════════════════════════
# subcommands
# ═══════════════════════════════════════════════════════════════════════════════════════


def cmd_provision(args: argparse.Namespace) -> int:  # noqa: PLR0912, PLR0915 - apply, probe,
    # summarise, write evidence, emit the credential. Each stage prints its own transcript.
    root = repo_root()
    load_dotenv(root)
    dsn = args.dsn or os.environ.get("COCKROACH_DSN")
    if not dsn:
        print("judge_access: no DSN. Pass --dsn or set COCKROACH_DSN.", file=sys.stderr)
        return EXIT_USAGE

    # The two copies of the audit list must agree. A security-relevant list that exists twice and
    # differs is worse than either version alone.
    try:
        from scripts.deploy.cloud_roles import AUDIT_VIEWS as W2_VIEWS

        if tuple(sorted(W2_VIEWS)) != tuple(sorted(AUDIT_VIEWS)):
            print(
                "judge_access: the audit view list disagrees with scripts/deploy/cloud_roles.py.\n"
                f"  here: {sorted(AUDIT_VIEWS)}\n  w2:   {sorted(W2_VIEWS)}",
                file=sys.stderr,
            )
            return EXIT_PROBE_DISAGREED
    except ImportError:
        pass  # w2's module is not importable here; the grants file is still authoritative

    database = args.database
    grants_path = root / GRANTS_SQL
    admin_dsn = rewrite_dsn(dsn, database=database, application_name="mainline-judge-access")

    print(f"cluster       {redact(admin_dsn)}")
    print(f"database      {database}")
    print(f"grants        {grants_path.relative_to(root)}")

    conn = psycopg.connect(admin_dsn, autocommit=True, connect_timeout=30)
    try:
        grant_log = apply_grants(conn, grants_path, database)
        password = ""
        if args.password_from_env:
            password = os.environ.get(args.password_from_env, "")
        elif args.rotate or args.new_password:
            password = generate_password()
            try:
                conn.execute(f"ALTER USER \"{JUDGE_USER}\" WITH PASSWORD '{password}'")
            except psycopg.Error as exc:
                # The insecure local node refuses passwords outright. That is not a failure of
                # provisioning; it is what an insecure node is. The probe then connects with none.
                print(f"  password not set: [{sqlstate_of(exc)}] {one_line(exc)[:120]}")
                password = ""
    finally:
        conn.close()

    applied = sum(1 for entry in grant_log if entry.get("ok"))
    skipped = [entry for entry in grant_log if entry.get("skipped")]
    failed = [entry for entry in grant_log if entry.get("ok") is False]
    print(f"grants        {applied} applied, {len(skipped)} skipped, {len(failed)} failed")
    for entry in skipped:
        print(f"  SKIPPED     [{entry['sqlstate']}] {entry['statement'][:90]}")
    for entry in failed:
        print(f"  FAILED      [{entry['sqlstate']}] {entry['statement'][:90]}")

    probe = probe_as_judge(dsn, password, database)
    verdict, failures = verdict_for(probe)
    # A NOT-RUN prints no counters at all. `0/14 readable` beside "could not authenticate" is the
    # single most misleading line this program could emit, so it is not emitted.
    if verdict == "NOT RUN":
        print("probe         NOT RUN — the grants above are UNVERIFIED")
    else:
        print(f"identity      {probe.get('identity')}")
        print(
            f"audit views   {probe['readable']}/{len(AUDIT_VIEWS)} readable, "
            f"{probe['non_empty']} non-empty"
        )
        denied = sum(1 for d in probe["denials"] if d["as_expected"])
        print(f"denials       {denied}/{len(probe['denials'])} refused as required")
        for denial in probe["denials"]:
            mark = "OK    " if denial["as_expected"] else "BROKEN"
            print(f"  {mark}      {denial['target']:38} [{denial['sqlstate']}]")
    print(f"VERDICT       {verdict}")
    for failure in failures:
        print(f"  ! {failure}")

    if args.out:
        payload = {
            "generated_at": utc_now(),
            "database": database,
            "cluster": redact(admin_dsn),
            "grants": grant_log,
            "probe": probe,
            "verdict": verdict,
            "failures": failures,
        }
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(f"evidence      {out}")

    if password and args.show_password:
        print()
        # ASCII, deliberately. This is the one line in the program whose failure loses a secret
        # that has already been written to the cluster, so it does not depend on the console's
        # encoding being anything in particular.
        print("-- credential, shown once " + "-" * 42)
        print(f"  user      {JUDGE_USER}")
        print(f"  password  {password}")
        print("  Write it to SSM now; this program does not store it.")

    if verdict == "NOT RUN":
        return EXIT_NOT_RUN
    return EXIT_OK if verdict == "PROVEN" else EXIT_PROBE_DISAGREED


def cmd_judge_run(args: argparse.Namespace) -> int:  # noqa: PLR0912, PLR0915 - two channels,
    # each with its own NOT-RUN reason, plus the disposition pass over the divergences.
    root = repo_root()
    load_dotenv(root)
    questions = load_questions(root)
    payload: dict[str, Any] = {
        "generated_at": utc_now(),
        "pack": QUESTIONS_YAML,
        "questions": len(questions),
        "positive": sum(1 for q in questions if not q.is_negative),
        "negative": sum(1 for q in questions if q.is_negative),
        "channels": {},
    }

    if args.via in ("mcp", "both"):
        api_key = os.environ.get("MAINLINE_MCP_API_KEY") or os.environ.get("CC_API_KEY", "")
        cluster_id = os.environ.get("MAINLINE_MCP_CLUSTER_ID") or args.cluster_id or ""
        if not api_key or not cluster_id:
            payload["channels"]["mcp"] = {
                "channel": "mcp",
                "ran": False,
                "reason": (
                    "MAINLINE_MCP_API_KEY (or CC_API_KEY) and a cluster id are not both set, so "
                    "NOTHING was sent. With no key this is a NOT-RUN, never a pass: a green "
                    "negative run with nothing to talk to asserts the opposite of what it claims."
                ),
            }
        else:
            payload["channels"]["mcp"] = run_pack_over_mcp(
                questions, api_key, cluster_id, args.mcp_database, root
            )

    if args.via in ("sql", "both"):
        dsn = args.dsn or os.environ.get("COCKROACH_DSN", "")
        if not dsn:
            payload["channels"]["sql"] = {
                "channel": "sql",
                "ran": False,
                "reason": "no DSN in --dsn or COCKROACH_DSN, so NOTHING was executed.",
            }
        else:
            target = rewrite_dsn(
                dsn, database=args.database, application_name="mainline-judge-pack"
            )
            if args.as_judge:
                target = as_user(dsn, JUDGE_USER, args.judge_password or "", args.database)
            payload["channels"]["sql"] = run_pack_over_sql(
                questions,
                target,
                args.database,
                JUDGE_USER if args.as_judge else "admin",
            )

    for name, report in payload["channels"].items():
        if not report.get("ran"):
            print(f"{name:5} NOT RUN — {report.get('reason', report.get('error', 'unknown'))}")
            continue
        print(
            f"{name:5} {report.get('passed', 0)}/{report.get('total', 0)} as expected "
            f"(identity {report.get('sql_identity')})"
        )
        for entry in report["results"]:
            mark = "PASS" if entry["verdict"] == "PASS" else "FAIL"
            tail = entry.get("refusal") or f"rows={entry.get('rows')}"
            print(f"  {mark}  {entry['qid']:5} {str(tail)[:88]}")

    # ── the determination this worker was asked to make, stated once, in the evidence ────────
    mcp = payload["channels"].get("mcp", {})
    if mcp.get("ran"):
        write_tools = sorted(
            t for t in mcp.get("tools", ()) if t.split("_")[0] in {"create", "insert", "drop"}
        )
        payload["managed_mcp_availability"] = {
            "question": (
                "Is the CockroachDB Managed MCP Server available on the SERVERLESS/Basic tier, "
                "and can its credential be published to anonymous judges?"
            ),
            "available_on_basic": True,
            "how_established": (
                f"MCP initialize against {MCP_ENDPOINT} with the cluster's own Cloud "
                "service-account key returned HTTP 200 and a session id; tools/list returned "
                f"{len(mcp.get('tools', ()))} tools; {mcp.get('passed')} of {mcp.get('total')} "
                "pack questions were then executed over it against the live Basic cluster."
            ),
            "plan_tier": "BASIC",
            "sql_identity": mcp.get("sql_identity"),
            "gt10_answer": (
                "GT-10, which FALLBACK.md records as unanswered and assumes pessimistically: the "
                f"endpoint runs as the SQL user {mcp.get('sql_identity')!r} — not root, not the "
                "database owner, a purpose-built identity."
            ),
            "credential_publishable": False,
            "why_not_publishable": (
                "The credential that reaches this endpoint is the account's Cloud service-account "
                "key, and the surface it opens is not read-only. FALLBACK.md's Branch A rests on "
                "the premise that the MCP write surface is 'insert-only and bound to "
                "mainline_meas.external_attestation'. Measured, the tool list carries "
                f'{write_tools} and `create_database` returned {{"success": true}} against the '
                "live demo cluster — a database was created and dropped again in the same "
                "session. `list_clusters` also enumerates every cluster the account owns. So the "
                "degrade to Branch B executes, but NOT for the anticipated reason: Managed MCP is "
                "available and works well; the key is simply far too powerful to hand to a "
                "stranger."
            ),
            "published_instead": (
                "the read-only SQL login mainline_judge, whose reach is the fourteen "
                "mainline_audit views and nothing else, verified from the other side by "
                "`judge_access.py provision`."
            ),
            "write_tools_present": write_tools,
        }

    # ── every divergence gets a disposition, and an unrecognised one gets "unexplained" ──────
    #
    # A list of failures with no reading beside them invites the reader to assume they are all
    # the same kind of thing. They are not: two of these are the judge login behaving exactly as
    # designed, two are a property that belongs to the other transport, and one is a real gap.
    # The default is "unexplained", so a NEW divergence cannot hide inside a familiar-looking
    # list — it shows up as the one nobody has accounted for.
    payload["divergences"] = []
    for channel_name, report in payload["channels"].items():
        for entry in report.get("results", []):
            if entry.get("verdict") == "PASS":
                continue
            payload["divergences"].append(
                {
                    "channel": channel_name,
                    "qid": entry["qid"],
                    "observed": entry.get("refusal") or f"answered, rows={entry.get('rows')}",
                    **DISPOSITIONS.get(
                        (channel_name, entry["qid"]),
                        {
                            "disposition": "unexplained",
                            "by_design": False,
                            "reading": (
                                "this divergence has no recorded reading. Treat it as a "
                                "regression until somebody measures it."
                            ),
                        },
                    ),
                }
            )

    ran = [r for r in payload["channels"].values() if r.get("ran")]
    unexplained = [d for d in payload["divergences"] if d["disposition"] == "unexplained"]
    by_design_only = payload["divergences"] and all(d["by_design"] for d in payload["divergences"])
    if not ran:
        payload["verdict"] = "NOT RUN"
    elif not payload["divergences"]:
        payload["verdict"] = "ALL AS EXPECTED"
    elif unexplained:
        payload["verdict"] = "DIVERGED — UNEXPLAINED"
    elif by_design_only:
        payload["verdict"] = "AS DESIGNED"
    else:
        payload["verdict"] = "DIVERGED — KNOWN GAP"
    print(f"VERDICT {payload['verdict']}")
    for divergence in payload["divergences"]:
        flag = "by design" if divergence["by_design"] else "GAP"
        print(
            f"  {flag:9} {divergence['channel']:4} {divergence['qid']:5} "
            f"{divergence['reading'][:96]}"
        )

    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(f"evidence {out}")

    if not ran:
        return EXIT_NOT_RUN
    return EXIT_OK if payload["verdict"] == "ALL AS EXPECTED" else EXIT_PROBE_DISAGREED


def cmd_credentials(args: argparse.Namespace) -> int:
    """Print the block that goes in docs/deploy/JUDGE-PACK.md. No secret is invented here."""
    host = args.host or "<cluster-host>"
    print("```")
    print(f"host      {host}")
    print("port      26257")
    print(f"database  {args.database}")
    print(f"user      {JUDGE_USER}")
    print("password  <issued out of band; see docs/deploy/JUDGE-PACK.md>")
    print("sslmode   verify-full")
    print("```")
    print()
    print("Reach, in full:")
    for view in AUDIT_VIEWS:
        print(f"  SELECT  mainline_audit.{view}")
    print("  and nothing else. No write privilege on any relation.")
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="judge_access",
        description=(
            "Provision the read-only judge login, prove it from the other side, and run the "
            "judge pack against the live cluster."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("provision", help="apply judge_grants.sql and probe the result")
    p.add_argument("--dsn", help="admin DSN (default: COCKROACH_DSN)")
    p.add_argument("--database", default="mainline_demo")
    p.add_argument("--rotate", action="store_true", help="set a new password")
    p.add_argument("--new-password", action="store_true", help="alias for --rotate")
    p.add_argument("--password-from-env", help="read the judge password from this variable")
    p.add_argument("--show-password", action="store_true", help="print the generated password")
    p.add_argument("--out", help="write evidence JSON here")
    p.set_defaults(func=cmd_provision)

    p = sub.add_parser("judge-run", help="run the pack's questions against the live cluster")
    p.add_argument("--via", choices=("mcp", "sql", "both"), default="both")
    p.add_argument("--dsn", help="DSN for the sql channel (default: COCKROACH_DSN)")
    p.add_argument("--database", default="mainline_demo", help="database for the sql channel")
    p.add_argument("--mcp-database", default="mainline_demo", help="database for the mcp channel")
    p.add_argument("--cluster-id", help="CockroachDB Cloud cluster uuid for the mcp channel")
    p.add_argument("--as-judge", action="store_true", help="run the sql channel as mainline_judge")
    p.add_argument("--judge-password", default="", help="password for --as-judge")
    p.add_argument("--out", help="write evidence JSON here")
    p.set_defaults(func=cmd_judge_run)

    p = sub.add_parser("credentials", help="print the judge credential block")
    p.add_argument("--host", help="cluster hostname")
    p.add_argument("--database", default="mainline_demo")
    p.set_defaults(func=cmd_credentials)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
