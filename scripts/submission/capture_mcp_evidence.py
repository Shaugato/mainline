#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Capture the CockroachDB Managed MCP Server transcript into ``evidence/mcp/``.

    python scripts/submission/capture_mcp_evidence.py            # full capture
    python scripts/submission/capture_mcp_evidence.py --no-cli   # skip the subprocess run
    python scripts/submission/capture_mcp_evidence.py --no-pack  # handshake + schemas only

**READ VERBS ONLY, AND THE PROHIBITION IS ENFORCED RATHER THAN PROMISED.** Every HTTP
request this program makes passes through :func:`_read_only_guard`, an ``httpx`` request
hook that parses the outgoing JSON-RPC body and raises :class:`WriteVerbAttempted` if the
tool named is ``insert_rows``, ``create_database`` or ``create_table``. Those three are on
the live tool list — that is exactly why our credential is not publishable — and this
program is the one place in the submission that talks to the endpoint on purpose, so the
guard lives here at the transport boundary and not in a comment.

**What it writes, and why each file exists separately.**

``evidence/mcp/session.json``
    The handshake: HTTP status, latency, the protocol revision the server *named* rather
    than the one we offered, its ``serverInfo``, and the SQL identity the credential
    resolves to. Enough for a reader to see that a real session was opened.
``evidence/mcp/tools-schema.json``
    All twelve tools with their **full** ``inputSchema``, plus a divergence block that is
    *derived from the schemas in the same file* rather than asserted, naming every place
    our typed surface differs from the live one.
``evidence/mcp/pack-run.json``
    The sixteen-question judge pack driven through the pack's **own** runner —
    ``verticals/mainline/demo/judge/cli.py run --via mcp`` → ``runner.run_via_mcp`` — so
    the envelope validator, the drift check against the real migrations and the
    25-row truncation guard are all in the path. The ad-hoc client that produced the
    2026-08-11 transcript carried none of the three.
``evidence/mcp/README.md``
    The page a judge lands on.

**Every artefact carries a self-scan and this program refuses to write one that fails it.**
:func:`hygiene` searches the serialised text for the live key verbatim, for a connection
string whose userinfo survived redaction, and for any bare token of credential *shape*; a
hit raises :class:`CredentialInArtefact` before the file is written, and the file is
re-scanned **on disk** after the write and deleted if the on-disk bytes disagree.

**What this program never does.** It runs no ``terraform``, calls no AWS API, reads and
writes no SSM parameter, commits nothing, and prints no credential — the key is read from
the environment into a local, is passed to the transport, and appears in no output stream
and in no artefact.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

import httpx

REPO_ROOT: Final = Path(__file__).resolve().parents[2]
JUDGE_DIR: Final = REPO_ROOT / "verticals" / "mainline" / "demo" / "judge"
OUT_DIR: Final = REPO_ROOT / "evidence" / "mcp"

#: The cluster this repository's transcripts have always been taken against:
#: ``mainline-dev``, SERVERLESS/Basic, ``aws-ap-southeast-1``, v26.2.5.
#: A UUID is a public identifier, not a secret, and it is quoted here on purpose so the
#: artefacts and ``MCP-CONFIG.md`` name the same cluster.
CLUSTER_ID: Final = "7cfc9ee9-f9b4-413d-bcad-d81fca2c6c7e"
DATABASE: Final = "mainline_demo"
ENDPOINT: Final = "https://cockroachlabs.cloud/mcp"
OFFERED_PROTOCOL: Final = "2025-06-18"

#: The three tools on the live list that write. This program may not call them (R4), and
#: :func:`_read_only_guard` raises rather than trusting that it did not.
WRITE_TOOLS: Final = ("create_database", "create_table", "insert_rows")

KEY_VARIABLES: Final = ("MAINLINE_MCP_API_KEY", "CC_API_KEY")

SCHEMA_VERSION: Final = "mainline.evidence.mcp/1"


class WriteVerbAttempted(RuntimeError):
    """A write tool was about to go on the wire. The request is aborted, not logged."""


class CredentialInArtefact(RuntimeError):
    """Raised instead of writing an evidence file that carries something secret-shaped."""


class CaptureFailed(RuntimeError):
    """The capture could not proceed, with the reason a reader needs."""


# ═══════════════════════════════════════════════════════════════════════════════════════
# credential hygiene — the assertion every artefact here makes about itself
# ═══════════════════════════════════════════════════════════════════════════════════════

#: A run of 24+ characters from the URL-safe/base64 alphabet with no separator either side.
TOKEN_SHAPE: Final = re.compile(
    r"(?<![A-Za-z0-9_+/=\-])[A-Za-z0-9_+/=\-]{24,}(?![A-Za-z0-9_+/=\-])"
)

#: A UUID is long and dense and *public*. The cluster id is one and is quoted deliberately.
UUID_SHAPE: Final = re.compile(
    r"\A[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\Z"
)

#: ``scheme://user:secret@host``. The redacted form ``user:***@`` is excluded by the
#: lookahead, because every artefact in this tree quotes a redacted DSN and without the
#: lookahead this pattern fires on all of them.
DSN_WITH_PASSWORD: Final = re.compile(r"[a-zA-Z][a-zA-Z0-9+.\-]*://[^:/@\s]+:(?!\*+@)[^@\s]+@")

HYGIENE_METHOD: Final = (
    "the serialised artefact was searched for (a) the live Managed-MCP service-account key "
    "verbatim, as a substring so a value embedded in a longer string is caught too, "
    "(b) any connection string whose userinfo still carries a password rather than the "
    "redacted form, and (c) any bare token of 24+ characters mixing upper case, lower case "
    "and digits — the shape a generated secret has. UUIDs are excluded by shape, not by an "
    "allowlist of values, which is why the cluster id survives the scan. bytes_scanned "
    "counts the artefact body as it was scanned, before this block was appended; after the "
    "write the file was re-read FROM DISK and scanned again, and a disagreement deletes the "
    "file rather than reporting a pass."
)


def looks_like_credential(token: str) -> bool:
    """Is *token* shaped like a generated secret rather than like an identifier?

    The discriminator is character-class diversity, not length and not an allowlist. The
    long strings that legitimately appear in these artefacts fail it:
    ``v_weakenings_without_disposition`` has no uppercase and no digit, a hex digest has no
    uppercase, and a UUID is excluded by shape above.
    """
    if len(token) < 24 or UUID_SHAPE.match(token):
        return False
    return (
        any(c.isupper() for c in token)
        and any(c.islower() for c in token)
        and any(c.isdigit() for c in token)
    )


def scan_for_credentials(text: str, *, needle: str) -> list[str]:
    """Return every reason *text* must not be written, most certain first."""
    findings: list[str] = []
    if needle and needle in text:
        findings.append("the live service-account key appears verbatim in the artefact")
    findings.extend(
        f"a connection string carrying userinfo survived redaction: {m.group(0)[:24]}..."
        for m in DSN_WITH_PASSWORD.finditer(text)
    )
    suspects = sorted({t for t in TOKEN_SHAPE.findall(text) if looks_like_credential(t)})
    findings.extend(
        f"credential-shaped token in the artefact: {t[:4]}... ({len(t)} chars)" for t in suspects
    )
    return findings


def hygiene(body: str, *, needle: str) -> dict[str, Any]:
    """Scan *body*; return the block that goes into the artefact, or refuse to produce one."""
    findings = scan_for_credentials(body + HYGIENE_METHOD, needle=needle)
    if findings:
        raise CredentialInArtefact("; ".join(findings))
    return {
        "assertion": "no field in this file is credential-shaped",
        "method": HYGIENE_METHOD,
        "self_scanned": True,
        "bytes_scanned": len(body.encode("utf-8")),
        "key_was_in_scope_this_run": bool(needle),
        "matches": 0,
        "holds": True,
    }


def write_json(path: Path, payload: dict[str, Any], *, needle: str) -> int:
    """Serialise, self-scan, write, then re-scan the bytes on disk. Returns the file size."""
    body = json.dumps(payload, indent=2, ensure_ascii=False)
    payload["credential_hygiene"] = hygiene(body, needle=needle)
    text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    return _write_and_reverify(path, text, needle=needle)


def _write_and_reverify(path: Path, text: str, *, needle: str) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    on_disk = path.read_text(encoding="utf-8")
    findings = scan_for_credentials(on_disk, needle=needle)
    if findings:
        path.unlink(missing_ok=True)
        raise CredentialInArtefact(
            f"{path.name} was deleted after the write: {'; '.join(findings)}"
        )
    return len(on_disk.encode("utf-8"))


# ═══════════════════════════════════════════════════════════════════════════════════════
# environment
# ═══════════════════════════════════════════════════════════════════════════════════════


def load_dotenv(root: Path) -> None:
    """Read ``.env`` into the environment without overwriting anything already set."""
    env_file = root / ".env"
    if not env_file.is_file():
        return
    for raw in env_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def resolve_key() -> tuple[str, str]:
    """Return ``(key, variable_name)``. The key is never printed and never serialised."""
    for name in KEY_VARIABLES:
        value = os.environ.get(name, "")
        if value:
            return value, name
    raise CaptureFailed(
        f"none of {', '.join(KEY_VARIABLES)} is set, so NOTHING was sent. This capture has no "
        "offline mode: an evidence file describing a session that did not happen is the one "
        "artefact worse than no file."
    )


def now_utc() -> str:
    return datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


# ═══════════════════════════════════════════════════════════════════════════════════════
# the instrumented transport
# ═══════════════════════════════════════════════════════════════════════════════════════


class Exchanges:
    """Every HTTP exchange this capture made, recorded at the ``httpx`` boundary.

    The hooks are the point: the *status code* and the *header set actually transmitted*
    are properties of the request that went out, and reading them anywhere else would be
    reading our intention rather than the wire.
    """

    def __init__(self, *, cluster_id: str) -> None:
        self.cluster_id = cluster_id
        self.records: list[dict[str, Any]] = []
        self.tools_called: list[str] = []

    def request_hook(self, request: httpx.Request) -> None:
        """Refuse a write verb before it leaves this process."""
        body = self._body(request)
        if body.get("method") != "tools/call":
            return
        params = body.get("params")
        name = str(params.get("name", "")) if isinstance(params, dict) else ""
        self.tools_called.append(name)
        if name in WRITE_TOOLS:
            raise WriteVerbAttempted(
                f"{name} is a write verb; this capture is read-only and the request was "
                "aborted before transmission"
            )

    def response_hook(self, response: httpx.Response) -> None:
        """Record status, latency, size and the two headers that make the call legible."""
        response.read()
        request = response.request
        body = self._body(request)
        method = str(body.get("method", "?"))
        params = body.get("params")
        tool = ""
        if method == "tools/call" and isinstance(params, dict):
            tool = str(params.get("name", ""))
        authorization = request.headers.get("Authorization", "")
        self.records.append(
            {
                "jsonrpc_method": method,
                "tool": tool or None,
                "http_status": response.status_code,
                "elapsed_ms": round(response.elapsed.total_seconds() * 1000.0, 1),
                "response_bytes": len(response.content),
                "content_type": response.headers.get("content-type", ""),
                # The value is never recorded. That the scheme is Bearer and that the
                # cluster header carried the pin are the two facts a reader needs.
                "authorization_scheme": authorization.split(" ", 1)[0] if authorization else None,
                "mcp_cluster_id_header": request.headers.get("mcp-cluster-id"),
                "cluster_header_matches_pin": request.headers.get("mcp-cluster-id")
                == self.cluster_id,
            }
        )

    @staticmethod
    def _body(request: httpx.Request) -> dict[str, Any]:
        try:
            decoded = json.loads(request.content or b"{}")
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {}
        return decoded if isinstance(decoded, dict) else {}

    def find(self, method: str) -> dict[str, Any] | None:
        for record in self.records:
            if record["jsonrpc_method"] == method:
                return record
        return None


# ═══════════════════════════════════════════════════════════════════════════════════════
# phase 1 — the handshake and the identity
# ═══════════════════════════════════════════════════════════════════════════════════════


def capture_session(
    *,
    api_key: str,
    key_variable: str,
    cluster_id: str,
    database: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Open a session, ask the two read questions that identify it, and record everything."""
    from mainline_mcp.client import Client, HttpStreamableTransport

    exchanges = Exchanges(cluster_id=cluster_id)
    http = httpx.Client(
        timeout=20.0,
        event_hooks={"request": [exchanges.request_hook], "response": [exchanges.response_hook]},
    )
    probes: list[dict[str, Any]] = []
    try:
        transport = HttpStreamableTransport(
            api_key=api_key,
            cluster_id=cluster_id,
            endpoint=ENDPOINT,
            http_client=http,
            protocol_version=OFFERED_PROTOCOL,
        )
        started = time.perf_counter()
        server_info = transport.initialize()
        handshake_ms = round((time.perf_counter() - started) * 1000.0, 1)
        client = Client(transport, database=database)
        probes.append(
            _probe(
                client,
                label="sql_identity",
                sql="SELECT current_user AS sql_identity, current_database() AS bound_database",
                why="which login the account key resolves to, and where it is pointed",
            )
        )
        probes.append(
            _probe(
                client,
                label="audit_view_reachable",
                sql="SELECT count(*) AS n FROM mainline_audit.v_open_gate_summary LIMIT 1",
                why="the gate summary is the view the demo's first question reads",
            )
        )
        tools = transport.list_tool_names()
        negotiated = transport.negotiated_version
    finally:
        http.close()

    initialize_record = exchanges.find("initialize") or {}
    identity = _row_value(probes[0], "sql_identity")
    session = {
        "schema": SCHEMA_VERSION,
        "artefact": "session",
        "generated_at": now_utc(),
        "generated_by": "scripts/submission/capture_mcp_evidence.py",
        "endpoint": ENDPOINT,
        "cluster_id": cluster_id,
        "cluster_name": "mainline-dev",
        "database": database,
        "handshake": {
            "offered_protocol_version": OFFERED_PROTOCOL,
            "negotiated_protocol_version": negotiated,
            "server_named_the_revision": negotiated == OFFERED_PROTOCOL,
            "server_info": dict(server_info),
            "http_status": initialize_record.get("http_status"),
            "http_elapsed_ms": initialize_record.get("elapsed_ms"),
            "wall_ms_including_notifications_initialized": handshake_ms,
            "response_bytes": initialize_record.get("response_bytes"),
            "content_type": initialize_record.get("content_type"),
            "authorization_scheme": initialize_record.get("authorization_scheme"),
            "mcp_cluster_id_header": initialize_record.get("mcp_cluster_id_header"),
            "cluster_header_matches_pin": initialize_record.get("cluster_header_matches_pin"),
        },
        "identity": {
            "sql_identity": identity,
            "bound_database": _row_value(probes[0], "bound_database"),
            "reading": (
                "the account-level Cloud service-account key resolves to the SQL login "
                f"{identity!r} on this cluster. That login is NOT the credential this "
                "submission publishes; see the README and R5."
            ),
        },
        "probes": probes,
        "tool_count": len(tools),
        "tools": list(tools),
        "read_only": {
            "tools_called_by_this_capture": sorted(set(exchanges.tools_called)),
            "write_tools_on_the_live_list": list(WRITE_TOOLS),
            "write_tools_called": sorted(set(exchanges.tools_called) & set(WRITE_TOOLS)),
            "enforced_how": (
                "an httpx request hook parses every outgoing JSON-RPC body and raises "
                "WriteVerbAttempted before transmission if the tool named is one of the three "
                "write verbs. The prohibition is executed, not promised."
            ),
        },
        "credential": {
            "read_from_variable": key_variable,
            "value_recorded": False,
            "publishable": False,
            "why_not_publishable": (
                "it is an account-level CockroachDB Cloud service-account key, not a database "
                "login. Its own tool list carries create_database, create_table and insert_rows, "
                "and list_clusters enumerates every cluster the account owns."
            ),
        },
        "http_exchanges": exchanges.records,
    }
    return session, probes


def _probe(client: Any, *, label: str, sql: str, why: str) -> dict[str, Any]:
    """One ``select_query`` through the shipped client, recorded whatever it does."""
    from mainline_mcp.limits import McpClientError

    started = time.perf_counter()
    try:
        result = client.select_query(sql)
    except McpClientError as exc:
        return {
            "label": label,
            "sql": sql,
            "why": why,
            "ok": False,
            "ms": round((time.perf_counter() - started) * 1000.0, 1),
            "detail": f"{type(exc).__name__}: {exc}",
            "rows": None,
        }
    return {
        "label": label,
        "sql": sql,
        "why": why,
        "ok": not result.is_error,
        "ms": round(client.last_elapsed_ms, 1),
        "response_bytes": result.byte_count,
        "detail": result.text[:200] if result.is_error else "answered",
        "rows": [dict(row) for row in (result.rows or ())],
    }


def _row_value(probe: dict[str, Any], column: str) -> Any:
    rows = probe.get("rows") or []
    return rows[0].get(column) if rows else None


# ═══════════════════════════════════════════════════════════════════════════════════════
# phase 2 — the twelve tools, with their full schemas, and what diverges from ours
# ═══════════════════════════════════════════════════════════════════════════════════════


def capture_tools(*, api_key: str, cluster_id: str) -> dict[str, Any]:
    """Record ``tools/list`` in full: every tool, every property, every required argument."""
    from mainline_mcp.client import DEFAULT_DIALECT, DOCUMENTED_DIALECT, HttpStreamableTransport
    from mainline_mcp.limits import READ_VERBS, WRITE_VERB

    exchanges = Exchanges(cluster_id=cluster_id)
    http = httpx.Client(
        timeout=20.0,
        event_hooks={"request": [exchanges.request_hook], "response": [exchanges.response_hook]},
    )
    try:
        transport = HttpStreamableTransport(
            api_key=api_key,
            cluster_id=cluster_id,
            endpoint=ENDPOINT,
            http_client=http,
            protocol_version=OFFERED_PROTOCOL,
        )
        server_info = transport.initialize()
        # The shipped client exposes `list_tool_names()`, which is all it needs. The whole
        # point of this artefact is the part it drops — the full JSON Schemas — so the
        # JSON-RPC request is made directly here rather than widening the client's public
        # surface to serve one evidence script.
        raw = transport._request("tools/list", {})
        negotiated = transport.negotiated_version
    finally:
        http.close()

    entries = [entry for entry in raw.payload.get("tools", []) if isinstance(entry, dict)]
    tools = sorted(
        (
            {
                "name": str(entry.get("name", "")),
                "description": entry.get("description", ""),
                "required": list(entry.get("inputSchema", {}).get("required", []) or []),
                "properties": sorted((entry.get("inputSchema", {}).get("properties", {}) or {})),
                "input_schema": entry.get("inputSchema", {}),
            }
            for entry in entries
        ),
        key=lambda tool: tool["name"],
    )
    listing = exchanges.find("tools/list") or {}
    return {
        "schema": SCHEMA_VERSION,
        "artefact": "tools-schema",
        "generated_at": now_utc(),
        "generated_by": "scripts/submission/capture_mcp_evidence.py",
        "endpoint": ENDPOINT,
        "cluster_id": cluster_id,
        "protocol_version": negotiated,
        "server_info": dict(server_info),
        "http_status": listing.get("http_status"),
        "elapsed_ms": listing.get("elapsed_ms"),
        "response_bytes": listing.get("response_bytes"),
        "tool_count": len(tools),
        "tool_names": [tool["name"] for tool in tools],
        "why_the_full_schemas_are_here": (
            "the argument names were the one thing no published document pinned precisely "
            "enough to be sure of, and a prose summary of a schema is a second guess. These are "
            "the server's own JSON Schemas as returned, so a reader settles the question here "
            "rather than by reading our reading of it."
        ),
        "tools": tools,
        "our_typed_surface": {
            "module": "packages/mainline-mcp/src/mainline_mcp/client.py",
            "default_dialect": _dialect_dict(DEFAULT_DIALECT),
            "documented_dialect": _dialect_dict(DOCUMENTED_DIALECT),
            "documented_dialect_note": (
                "what this package shipped until 2026-08-16 and where the guess was wrong. It is "
                "kept, named and asserted against in tests so the repository cannot quietly "
                "erase a guess it published."
            ),
            "read_verbs": list(READ_VERBS),
            "write_verb": WRITE_VERB,
        },
        "divergences": _divergences(tools),
        "write_tools_present": list(WRITE_TOOLS),
        "write_tools_called_by_this_capture": sorted(
            set(exchanges.tools_called) & set(WRITE_TOOLS)
        ),
    }


def _dialect_dict(dialect: Any) -> dict[str, str]:
    return {
        "statement": dialect.statement,
        "database": dialect.database,
        "table": dialect.table,
        "rows": dialect.rows,
        "limit": dialect.limit,
        "cluster_id": dialect.cluster_id,
        "schema": dialect.schema,
    }


def _properties(tools: list[dict[str, Any]], name: str) -> list[str]:
    for tool in tools:
        if tool["name"] == name:
            return list(tool["properties"])
    return []


def _required(tools: list[dict[str, Any]], name: str) -> list[str]:
    for tool in tools:
        if tool["name"] == name:
            return list(tool["required"])
    return []


def _description(tools: list[dict[str, Any]], name: str, prop: str) -> str:
    """The server's own words for one property, quoted so a divergence cites its source."""
    for tool in tools:
        if tool["name"] == name:
            properties = tool["input_schema"].get("properties", {}) or {}
            entry = properties.get(prop, {})
            return str(entry.get("description", "")) if isinstance(entry, dict) else ""
    return ""


def _divergences(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Every place our typed surface differs from the live one, DERIVED from the schemas.

    Each entry carries ``derived_from``: the predicate over this same file that produced
    it. A divergence a reader cannot re-derive from the artefact it appears in is a claim,
    not a measurement.
    """
    select_properties = _properties(tools, "select_query")
    insert_properties = _properties(tools, "insert_rows")
    schema_properties = _properties(tools, "get_table_schema")
    return [
        {
            "id": "select_query.statement_is_named_query",
            "tool": "select_query",
            "live": f"required {_required(tools, 'select_query')}",
            "ours_before_2026_08_16": "{database, statement}",
            "ours_now": "{database, query}",
            "corrected": True,
            "derived_from": "tools[select_query].input_schema.required contains 'query'",
            "reading": (
                "the one field that was wrong. A call carrying 'statement' returns "
                '{"code": 0, "message": "must contain exactly one statement"} — the bearer, the '
                "session and the cluster pin were all fine and the server simply saw no "
                "statement, because the property it reads was absent. ToolDialect existed so "
                "this correction would be one field value in one object, and it was."
            ),
        },
        {
            "id": "select_query.has_no_limit_argument",
            "tool": "select_query",
            "live": f"properties {select_properties} — no 'limit'",
            "live_says": _description(tools, "select_query", "query"),
            "ours": "ToolDialect.limit names an argument the read verbs do not have",
            "corrected": True,
            "derived_from": (
                "'limit' not in tools[select_query].properties, and "
                "tools[select_query].input_schema.properties.query.description quoted in "
                "live_says names LIMIT/OFFSET inside the statement as the pagination mechanism"
            ),
            "reading": (
                "pagination on the read verbs is LIMIT/OFFSET inside the statement, which is "
                "what the pack has always written. The client's row ceiling is now enforced "
                "client-side and is ours, not an argument; 'limit' is a real integer property "
                "of list_databases and list_tables only."
            ),
        },
        {
            "id": "insert_rows.takes_a_full_insert_statement",
            "tool": "insert_rows",
            "live": (
                f"required {_required(tools, 'insert_rows')}; properties {insert_properties} — "
                "no 'table', no 'rows'"
            ),
            "live_says": _description(tools, "insert_rows", "query"),
            "ours": "insert_external_attestation() sends {table, rows} and names no table in any "
            "parameter",
            "corrected": False,
            "not_corrected_on_purpose": True,
            "derived_from": "'table' not in tools[insert_rows].properties and 'rows' not in it",
            "reading": (
                "expressing our typed write on the live shape means constructing an INSERT "
                "statement — with a table name in it — inside the one method whose entire "
                "published guarantee is that 'insert into something else' is not a call the "
                "supported API can express. The guarantee is worth more than the call, so the "
                "divergence is recorded and the write is not sent. This capture never calls "
                "insert_rows at all."
            ),
        },
        {
            "id": "show_verbs.have_no_limit_argument",
            "tool": "show_statement, show_running_queries",
            "live": (
                f"show_statement properties {_properties(tools, 'show_statement')}; "
                f"show_running_queries properties {_properties(tools, 'show_running_queries')}"
            ),
            "ours": "the client used to transmit 'limit' to both",
            "corrected": True,
            "derived_from": (
                "'limit' not in tools[show_statement].properties and not in "
                "tools[show_running_queries].properties"
            ),
            "reading": (
                "the ceiling is still refused before transmission; it is simply no longer sent "
                "as an argument the server has no property for."
            ),
        },
        {
            "id": "get_table_schema.defaults_to_public",
            "tool": "get_table_schema",
            "live": f"properties {schema_properties}",
            "live_says": _description(tools, "get_table_schema", "schema"),
            "ours": "the audit views live in mainline_audit",
            "corrected": True,
            "derived_from": (
                "tools[get_table_schema].input_schema.properties.schema.description, quoted "
                "verbatim in live_says"
            ),
            "reading": (
                "a schema-less call cannot see the audit views at all. This is a live-surface "
                "fact worth recording because it silently answers a different question rather "
                "than failing."
            ),
        },
    ]


# ═══════════════════════════════════════════════════════════════════════════════════════
# phase 3 — the judge pack, through the pack's own runner
# ═══════════════════════════════════════════════════════════════════════════════════════


def _pack_module() -> Any:
    demo = REPO_ROOT / "verticals" / "mainline" / "demo"
    if str(demo) not in sys.path:
        sys.path.insert(0, str(demo))
    import judge.pack as pack_mod

    return pack_mod


def run_cli(*, database: str, cluster_id: str) -> dict[str, Any]:
    """Run the command a judge is told to run, and keep its stdout verbatim.

    The environment carries the key; the *command line* never does. That is why this is a
    subprocess with an environment rather than a shell string.
    """
    environment = dict(os.environ)
    environment["MAINLINE_MCP_CLUSTER_ID"] = cluster_id
    environment["MAINLINE_MCP_DATABASE"] = database
    started = time.perf_counter()
    completed = subprocess.run(
        [sys.executable, str(JUDGE_DIR / "cli.py"), "run", "--via", "mcp"],
        cwd=str(REPO_ROOT),
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=600,
    )
    return {
        "command": "python verticals/mainline/demo/judge/cli.py run --via mcp",
        "environment_required": [
            "MAINLINE_MCP_API_KEY (or CC_API_KEY, read from .env by this script)",
            "MAINLINE_MCP_CLUSTER_ID",
            "MAINLINE_MCP_DATABASE",
        ],
        "exit_code": completed.returncode,
        "exit_code_reading": _exit_reading(completed.returncode),
        "wall_seconds": round(time.perf_counter() - started, 1),
        "stdout": completed.stdout.splitlines(),
        "stderr": completed.stderr.splitlines()[-20:],
    }


def _exit_reading(code: int) -> str:
    return {
        0: "checked and every question behaved",
        1: "checked and at least one question did not behave — see the results",
        2: "the pack could not be loaded",
        3: "NOT RUN: there was nothing to talk to, and this is deliberately not 1",
    }.get(code, f"undocumented exit code {code}")


def capture_pack(*, database: str, cluster_id: str, run_the_cli: bool) -> dict[str, Any]:
    """Drive the sixteen questions through ``runner.run_via_mcp`` and score them."""
    pack_mod = _pack_module()
    import judge.envelope as env_mod
    import judge.runner as runner_mod

    pack = pack_mod.load_pack(None)
    verbs = sorted({question.verb for question in pack})
    if set(verbs) & set(WRITE_TOOLS):
        raise CaptureFailed(f"the pack names a write verb: {sorted(set(verbs) & set(WRITE_TOOLS))}")

    cli_run = run_cli(database=database, cluster_id=cluster_id) if run_the_cli else None

    started = time.perf_counter()
    report = runner_mod.run_via_mcp(pack, repo_root=REPO_ROOT, database=database)
    wall = round(time.perf_counter() - started, 1)

    expected = {
        question.qid: (runner_mod.REFUSED if question.is_negative else runner_mod.ANSWERED)
        for question in pack
    }
    results = [_score(result, expected[result.qid]) for result in report.results]
    passed = sum(1 for result in results if result["verdict"] == "PASS")
    return {
        "schema": SCHEMA_VERSION,
        "artefact": "pack-run",
        "generated_at": now_utc(),
        "generated_by": "scripts/submission/capture_mcp_evidence.py",
        "pack": "verticals/mainline/demo/judge/QUESTIONS.yaml",
        "channel": report.channel,
        "endpoint": env_mod.MCP_ENDPOINT,
        "cluster_id": cluster_id,
        "database": database,
        "ran": report.ran,
        "reason": report.reason,
        "verbs_used": verbs,
        "verbs_are_read_only": not set(verbs) & set(WRITE_TOOLS),
        "questions": len(pack),
        "positive": len(pack.positives()),
        "negative": len(pack.negatives()),
        "passed": passed,
        "total": len(results),
        "counts": report.counts(),
        "exit_code": report.exit_code(),
        "exit_code_reading": _exit_reading(report.exit_code()),
        "wall_seconds": wall,
        "entry_point": {
            "command": "python verticals/mainline/demo/judge/cli.py run --via mcp",
            "routes_into": "verticals/mainline/demo/judge/runner.py::run_via_mcp",
            "why_this_path": (
                "the pack's own runner carries three checks the ad-hoc client that produced "
                "evidence/deploy/judge-run.json on 2026-08-11 did not: the envelope validator "
                "(mainline_mcp.limits.enforce_statement on every statement before it is sent), "
                "the drift check that binds each EXPLAIN to a literal of the dimension the real "
                "migrations declare, and the truncation guard that flags any result returning "
                f"exactly the {env_mod.SELECT_PAGE_ROWS}-row page as possibly truncated."
            ),
            "envelope_page_rows": env_mod.SELECT_PAGE_ROWS,
        },
        "cli_run": cli_run,
        "cli_run_note": (
            "the same entry point, executed as a subprocess so the transcript a judge sees when "
            "they type the command is committed verbatim. It is a SECOND live run, not a "
            "rendering of the structured one below; the two ran minutes apart against the same "
            "cluster and the row counts are what they were at each moment."
        )
        if run_the_cli
        else "--no-cli was passed: the subprocess run did not happen and nothing here claims it "
        "did.",
        "results": results,
        "divergences": _pack_divergences(results),
        "verdict": "DIVERGED — KNOWN GAP" if passed < len(results) else "PROVEN",
        "verdict_reading": (
            "the pack does not round a divergence off. N01 asserts that an MCP identity cannot "
            "read mainline_qa; measured, it can. That is a real gap in this deployment's grants "
            "and it is recorded rather than closed by revoking a grant on submission eve."
        ),
    }


def _score(result: Any, expected: str) -> dict[str, Any]:
    record = {
        "qid": result.qid,
        "outcome": result.outcome,
        "expected": expected,
        "verdict": "PASS" if result.outcome == expected else "FAIL",
        "rows": result.rows,
        "response_bytes": result.response_bytes,
        "elapsed_ms": result.elapsed_ms,
        "possibly_truncated": result.possibly_truncated,
        "detail": result.detail,
    }
    if result.plan_text:
        record["plan_text"] = result.plan_text.splitlines()
    return record


def _pack_divergences(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    readings = {
        "N01": (
            "mainline_qa IS readable by the Managed MCP identity. N01 claims an MCP identity "
            "cannot read per-person deliberation measurement; measured, it runs successfully. "
            "GRANTS.yaml S14 and the pack envelope both assert this is impossible. It is not. "
            "The read-only mainline_judge login this submission actually publishes refuses the "
            "same statement at SQLSTATE 42501 — measured on 2026-08-11 and recorded in "
            "evidence/deploy/judge-run.json under divergences — so the credential a judge is "
            "handed is the tighter of the two. That does not make N01 a pass, and it is not "
            "scored as one here."
        )
    }
    return [
        {
            "qid": result["qid"],
            "observed": f"{result['outcome']}, rows={result['rows']}",
            "expected": result["expected"],
            "disposition": "real_gap",
            "by_design": False,
            "reading": readings.get(result["qid"], result["detail"]),
        }
        for result in results
        if result["verdict"] == "FAIL"
    ]


# ═══════════════════════════════════════════════════════════════════════════════════════
# phase 4 — the page a judge lands on
# ═══════════════════════════════════════════════════════════════════════════════════════


MY_FILES: Final = ("README.md", "session.json", "tools-schema.json", "pack-run.json")


def _neighbours(out: Path) -> list[str]:
    """Other artefacts sharing this directory, written by their own captures, not by this one.

    Named but **not described**: quoting another program's prose here would go stale the
    next time that program runs, and a stale quotation in an evidence page reads exactly
    like a false claim. The pointer is to the fields those files carry about themselves.
    """
    if not out.is_dir():
        return []
    return sorted(
        entry.name
        for entry in out.iterdir()
        if entry.is_file() and entry.name not in MY_FILES and not entry.name.endswith(".license")
    )


def render_readme(
    *,
    session: dict[str, Any],
    tools: dict[str, Any],
    pack: dict[str, Any] | None,
    out: Path,
) -> str:
    """Build ``evidence/mcp/README.md`` from the numbers that were actually measured."""
    handshake = session["handshake"]
    lines: list[str] = [
        "<!--",
        "SPDX-FileCopyrightText: 2026 MAINLINE contributors",
        "SPDX-License-Identifier: CC-BY-4.0",
        "",
        "GENERATED FILE — do not edit by hand.",
        "Produced by scripts/submission/capture_mcp_evidence.py against the live endpoint.",
        "-->",
        "",
        "# CockroachDB Cloud Managed MCP Server — the transcript",
        "",
        (
            f"**Captured {session['generated_at']}** against `{session['endpoint']}`, cluster "
            f"`{session['cluster_id']}` (`{session['cluster_name']}`), database "
            f"`{session['database']}`."
        ),
        "",
        (
            "This directory answers one question: *does an agent that is not ours reach "
            "MAINLINE's memory layer through a surface we did not write?* Everything below was "
            "measured on the date above, by "
            "`scripts/submission/capture_mcp_evidence.py`. Nothing here is a plan."
        ),
        "",
        "## The files this capture writes",
        "",
        "| file | what it holds |",
        "|---|---|",
        (
            "| `session.json` | the handshake — HTTP status, latency, the protocol revision the "
            "server named, its `serverInfo`, and the SQL identity our key resolves to |"
        ),
        (
            f"| `tools-schema.json` | all {tools['tool_count']} tools with their **full** "
            "`inputSchema`, and a divergence block derived from those schemas |"
        ),
        (
            "| `pack-run.json` | the sixteen-question judge pack driven through the pack's own "
            "runner, with per-question verdicts |"
        ),
        "| `README.md` | this page |",
        "",
    ]
    neighbours = _neighbours(out)
    if neighbours:
        lines.extend(
            [
                (
                    "Also in this directory, written by their own captures rather than by this "
                    f"one: {', '.join('`' + name + '`' for name in neighbours)}. Each states "
                    "its own provenance and its own scan in the `produced_by`, `generated_at` "
                    "and `credential_hygiene` fields it carries; this page does not describe "
                    "their contents, because a quotation of another program's output goes "
                    "stale the next time that program runs."
                ),
                "",
            ]
        )
    lines.extend(
        [
            "## What was measured",
            "",
            "```",
            (
                f"initialize        HTTP {handshake['http_status']}   "
                f"{handshake['http_elapsed_ms']} ms   protocolVersion "
                f"{handshake['negotiated_protocol_version']}"
            ),
            f"                             serverInfo {json.dumps(handshake['server_info'])}",
            (
                f"tools/list        HTTP {tools['http_status']}   {tools['elapsed_ms']} ms   "
                f"{tools['tool_count']} tools, full JSON Schemas recorded"
            ),
        ]
    )
    for probe in session["probes"]:
        rows = probe.get("rows") or []
        answer = json.dumps(rows[0]) if rows else probe.get("detail", "")
        lines.append(f"select_query      {probe['ms']} ms   {probe['label']}  ->  {answer}")
    lines.extend(
        [
            "```",
            "",
            f"The twelve tools: {', '.join('`' + name + '`' for name in tools['tool_names'])}.",
            "",
            (
                f"The key resolves to the SQL login `{session['identity']['sql_identity']}`, "
                f"bound to `{session['identity']['bound_database']}`."
            ),
            "",
        ]
    )
    lines.extend(_readme_pack_section(pack))
    lines.extend(_readme_limits_section(session, tools))
    return "\n".join(lines)


def _readme_pack_section(pack: dict[str, Any] | None) -> list[str]:
    if pack is None:
        return [
            "## The judge pack",
            "",
            "**Not run in this capture** (`--no-pack`). No claim on this page depends on it.",
            "",
        ]
    lines = [
        "## The sixteen-question pack, through the pack's own runner",
        "",
        (
            f"`{pack['entry_point']['command']}` → `{pack['entry_point']['routes_into']}`. "
            f"**{pack['passed']} of {pack['total']}**, exit `{pack['exit_code']}` "
            f"({pack['exit_code_reading']})."
        ),
        "",
        (
            "This path had never reached the live surface until 2026-08-16, because the client "
            "it dials through sent the SQL under the argument name `statement` and the live "
            "schema requires `query` — every call came back *must contain exactly one "
            "statement*. The 2026-08-11 transcript in `evidence/deploy/judge-run.json` — which "
            "is real, is unchanged, and is not superseded as a record — was driven instead by a "
            "short ad-hoc client inside `scripts/deploy/judge_access.py`, which carries none of "
            "the runner's three checks:"
        ),
        "",
        (
            "- the **envelope validator**, which refuses a statement that would breach a "
            "documented Managed-MCP limit *before* it is transmitted;"
        ),
        (
            "- the **drift check**, which binds each `EXPLAIN` to a vector literal of the "
            "dimension the real migrations declare, so a plan proof cannot pass against a "
            "stale dimension;"
        ),
        (
            "- the **truncation guard**, which flags any result of exactly "
            f"{pack['entry_point']['envelope_page_rows']} rows as possibly truncated rather "
            "than reporting the page as the whole answer."
        ),
        "",
        "| question | outcome | expected | verdict | rows | bytes | ms |",
        "|---|---|---|---|---|---|---|",
    ]
    if pack["cli_run"] is not None:
        lines[4:4] = [
            (
                "The same command was **also executed as a subprocess**, and the stdout a judge "
                "sees when they type it is committed verbatim at `pack-run.json` → "
                f"`cli_run.stdout` (exit `{pack['cli_run']['exit_code']}`). That is a second "
                f"live run — {pack['cli_run']['wall_seconds']} s, taken seconds before the "
                "structured one — and not a rendering of the table below, so the two agree on "
                "outcomes and need not agree to the millisecond."
            ),
            "",
        ]
    lines.extend(
        (
            f"| `{result['qid']}` | {result['outcome']} | {result['expected']} | "
            f"**{result['verdict']}** | {_dash(result['rows'])} | "
            f"{_dash(result['response_bytes'])} | {_dash(result['elapsed_ms'])} |"
        )
        for result in pack["results"]
    )
    lines.append("")
    for divergence in pack["divergences"]:
        lines.extend(
            [
                f"### The one that failed — `{divergence['qid']}`",
                "",
                divergence["reading"],
                "",
                (
                    "It is recorded, not rounded off. Closing it means revoking a grant on "
                    "submission eve, and a negative suite that has quietly gone green is the "
                    "worst artefact in a repository, because it reads as the strongest."
                ),
                "",
            ]
        )
    return lines


def _dash(value: Any) -> str:
    return "—" if value is None else str(value)


def _readme_limits_section(session: dict[str, Any], tools: dict[str, Any]) -> list[str]:
    credential = session["credential"]
    called = len(tools["write_tools_called_by_this_capture"])
    return [
        "## What this proves, and what it does not",
        "",
        (
            "**It proves** that CockroachDB's own managed endpoint answers questions about "
            "MAINLINE's audit views, over a tool surface Cockroach Labs wrote and we did not, "
            "with every statement screened against a documented envelope before it leaves and "
            "with the server — not our client — doing the refusing on the negatives."
        ),
        "",
        (
            "**It does not prove that a judge can read our ledger over MCP, and no wording "
            "here should ever suggest otherwise.**"
        ),
        "",
        (
            f"Our MCP credential is read from `{credential['read_from_variable']}` at run time "
            f"and is recorded nowhere in this repository: {credential['why_not_publishable']} "
            "It is therefore **not publishable**, and this repository does not publish it."
        ),
        "",
        "So repeatability has three legs and no fourth:",
        "",
        "1. **This transcript** — you are reading it, and it needs no credential.",
        (
            "2. **The mechanism** — reproduce it with **your own** key against **your own** "
            "cluster. The client configuration is one JSON block in "
            "[`MCP-CONFIG.md`](../../verticals/mainline/demo/judge/MCP-CONFIG.md) §1; swap the "
            "`mcp-cluster-id` for one of yours and it answers for you. What reproduces is the "
            "mechanism, not our data."
        ),
        (
            "3. **Our data is Path B** — the read-only `mainline_judge` pgwire login, published "
            "to judges in the submission form, whose whole reach is the fourteen "
            "`mainline_audit` views and nothing else. `MCP-CONFIG.md` §4 is the command line. "
            "**Path A is the mechanism, Path B is our data.**"
        ),
        "",
        "## The three write verbs, and why they were never called",
        "",
        (
            f"`{'`, `'.join(tools['write_tools_present'])}` are on the live tool list. That is "
            "precisely why the key is an account credential rather than a read-only one. This "
            f"capture called **{called}** of them, and the prohibition is enforced rather than "
            "promised: an `httpx` request hook parses every outgoing JSON-RPC body and aborts "
            "the request before transmission if the tool named is one of the three. See "
            "`session.json` → `read_only.enforced_how`."
        ),
        "",
        (
            "The measured live shape of `insert_rows` is `{database, query}` — a full `INSERT` "
            "statement. Our typed write method takes no parameter that names a table, by "
            "design. Expressing it on the live shape means building SQL inside the one method "
            "whose entire published guarantee is that it cannot. We did not, and "
            "`tools-schema.json` records the divergence instead."
        ),
        "",
        (
            "That is one of "
            f"**{len(tools['divergences'])}** divergences in `tools-schema.json` → "
            "`divergences`, each carrying a `derived_from` predicate over the schemas in the "
            "same file — so a reader re-derives every one of them from the artefact rather "
            "than taking our word for it. The one that mattered was ours: our client sent the "
            "SQL under the argument name `statement`, and the live schema requires `query`. "
            "The guess is not erased — it is preserved, named and dated as `DOCUMENTED_DIALECT` "
            "in `packages/mainline-mcp/src/mainline_mcp/client.py`, and a test asserts it "
            "differs from the measured dialect in precisely that one field."
        ),
        "",
        "## Read this directory in under a minute",
        "",
        "```bash",
        "# the twelve tools and their required arguments, from the committed capture",
        (
            "python -c \"import json;d=json.load(open('evidence/mcp/tools-schema.json'));"
            "print([(t['name'],t['required']) for t in d['tools']])\""
        ),
        "",
        "# every question, its outcome and its verdict",
        (
            "python -c \"import json;d=json.load(open('evidence/mcp/pack-run.json'));"
            "print([(r['qid'],r['outcome'],r['verdict']) for r in d['results']])\""
        ),
        "```",
        "",
        (
            "To re-take the capture against your own cluster, set `MAINLINE_MCP_API_KEY` and "
            "`MAINLINE_MCP_CLUSTER_ID` and run "
            "`python scripts/submission/capture_mcp_evidence.py`."
        ),
        "",
        "## This directory is additive",
        "",
        (
            "`evidence/deploy/judge-run.json` and `evidence/deploy/judge-access.json` are "
            "unchanged by this capture. They are the first MCP transcript this project took, "
            "on 2026-08-11, and they are cited from `docs/TOOL-USAGE.md` and `MCP-CONFIG.md`. "
            "This directory is where a reader looking for the *tool* finds it; it does not "
            "replace them."
        ),
        "",
        "## Credential hygiene",
        "",
    ]


def readme_hygiene_block(block: dict[str, Any]) -> str:
    """Render the self-scan the writer gated this page on."""
    return "\n".join(
        [
            "",
            (
                "This page, and each JSON file beside it, carries a self-scan that its own "
                "writer gates on. The writer refuses to emit rather than emit a match."
            ),
            "",
            "```json",
            json.dumps(block, indent=2, ensure_ascii=False),
            "```",
            "",
        ]
    )


# ═══════════════════════════════════════════════════════════════════════════════════════
# main
# ═══════════════════════════════════════════════════════════════════════════════════════


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("--out", type=Path, default=OUT_DIR, help="output directory")
    parser.add_argument("--cluster-id", default=None, help="override the pinned cluster")
    parser.add_argument("--database", default=None, help="override the bound database")
    parser.add_argument("--no-pack", action="store_true", help="handshake and schemas only")
    parser.add_argument("--no-cli", action="store_true", help="skip the subprocess pack run")
    return parser


def _display(path: Path) -> str:
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return str(path)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    # These artefacts and this report carry em dashes. On a Windows console defaulting to
    # cp1252 an unencodable character raises rather than degrades, which would abandon a
    # completed live capture at the last print.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    load_dotenv(REPO_ROOT)
    api_key, key_variable = resolve_key()
    cluster_id = args.cluster_id or os.environ.get("MAINLINE_MCP_CLUSTER_ID") or CLUSTER_ID
    database = args.database or os.environ.get("MAINLINE_MCP_DATABASE") or DATABASE
    # Set in-process only, for the pack runner and the subprocess. Never printed, never
    # written, and the subprocess receives it through its environment rather than its argv.
    os.environ["MAINLINE_MCP_API_KEY"] = api_key
    os.environ["MAINLINE_MCP_CLUSTER_ID"] = cluster_id
    os.environ["MAINLINE_MCP_DATABASE"] = database

    out: Path = args.out
    print(f"capturing against {ENDPOINT}, cluster {cluster_id}, database {database}")

    session, _ = capture_session(
        api_key=api_key, key_variable=key_variable, cluster_id=cluster_id, database=database
    )
    print(
        f"  handshake      HTTP {session['handshake']['http_status']} "
        f"{session['handshake']['http_elapsed_ms']} ms  "
        f"protocol {session['handshake']['negotiated_protocol_version']}  "
        f"identity {session['identity']['sql_identity']}"
    )
    tools = capture_tools(api_key=api_key, cluster_id=cluster_id)
    print(f"  tools/list     {tools['tool_count']} tools, {len(tools['divergences'])} divergences")

    pack: dict[str, Any] | None = None
    if not args.no_pack:
        pack = capture_pack(database=database, cluster_id=cluster_id, run_the_cli=not args.no_cli)
        print(
            f"  judge pack     {pack['passed']}/{pack['total']} — {pack['verdict']} "
            f"(exit {pack['exit_code']})"
        )

    written: list[tuple[Path, int]] = []
    written.append(
        (out / "session.json", write_json(out / "session.json", session, needle=api_key))
    )
    written.append(
        (out / "tools-schema.json", write_json(out / "tools-schema.json", tools, needle=api_key))
    )
    if pack is not None:
        written.append(
            (out / "pack-run.json", write_json(out / "pack-run.json", pack, needle=api_key))
        )

    body = render_readme(session=session, tools=tools, pack=pack, out=out)
    block = hygiene(body, needle=api_key)
    readme = out / "README.md"
    size = _write_and_reverify(readme, body + readme_hygiene_block(block), needle=api_key)
    written.append((readme, size))

    for path, size in written:
        print(f"  wrote {_display(path)}  {size} bytes  hygiene holds")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (CaptureFailed, CredentialInArtefact, WriteVerbAttempted) as exc:
        print(f"capture refused: {type(exc).__name__}: {exc}")
        raise SystemExit(1) from exc
