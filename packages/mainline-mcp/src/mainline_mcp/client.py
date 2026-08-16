# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The typed Managed-MCP client: one cluster, one statement, one writable table.

Three structural properties, each of which is a *shape* rather than a check:

1. **One cluster.** The pin is a constructor argument, it is sent as the
   ``mcp-cluster-id`` header on every request, and any tool argument naming a
   different cluster is refused before transmission
   (:class:`~mainline_mcp.limits.ClusterPinViolation`). The server is documented to
   fail such a call too; refusing here as well means the failure is attributable to us
   attempting it and the assertion has something to catch with no credential present.

2. **One statement, within every documented limit.** Every SQL-bearing verb routes
   through :func:`~mainline_mcp.limits.enforce_statement` first, so a breach is a typed
   refusal naming the limit rather than a truncated string arriving later.

3. **One writable table.** :meth:`Client.insert_external_attestation` has no parameter
   that names a table. ``mainline_meas.external_attestation`` is a constant inside the
   method body. "Insert into something else" is therefore not a call that the supported
   API can express — the binding is in the type, not in a run-time comparison.

Property 3 has one deliberate hole, and it is named: the negative-reachability suite has
to *attempt* the forbidden write in order to record that the server refused it. That
attempt is :func:`probe_insert_rows_unbound`, a module-level function that is not a
method, that takes a mandatory ``why`` argument, and whose only two callers in the
repository are tests.

**Verification status.** The transport is built from the documented MCP Streamable HTTP
transport. It is exercised end-to-end offline against ``httpx.MockTransport``, including
SSE framing, session-header propagation and the cluster pin, so the code path under test
is the real one.

The tool *argument names* were the one thing that could differ on the live service, which
is why they were isolated in :class:`ToolDialect` rather than spelled inline in seven
methods. **On 2026-08-16 they were measured** against
``https://cockroachlabs.cloud/mcp`` — ``initialize`` then ``tools/list``, read out of the
server's own JSON Schema — and one of them was wrong. The correction was one field value
in one object, which is what that isolation was for. The guess we published is kept, named
and dated in :data:`DOCUMENTED_DIALECT`; the measured surface is
:data:`DEFAULT_DIALECT`.
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final, Protocol, Self

import httpx

from .limits import (
    CLUSTER_HEADER,
    EXTERNAL_ATTESTATION_TABLE,
    LIST_DEFAULT_ROWS,
    MCP_ENDPOINT,
    PROTOCOL_VERSION,
    REQUEST_TIMEOUT_SECONDS,
    SELECT_MAX_ROWS,
    SHOW_MAX_ROWS,
    ClusterPinViolation,
    ProtocolError,
    ToolCallFailed,
    WriteTargetRefused,
    enforce_response_size,
    enforce_row_limit,
    enforce_statement,
)

_JSONRPC: Final = "2.0"
_SESSION_HEADER: Final = "mcp-session-id"
_ROW_KEYS: Final = ("rows", "results", "data", "records")
_CLIENT_NAME: Final = "mainline-mcp"
_CLIENT_VERSION: Final = "0.1.0"


@dataclass(frozen=True, slots=True)
class ToolDialect:
    """The tool *argument names*, isolated so a live-surface difference is a one-line fix.

    Everything else in this package is derived from documented behaviour that a second
    reader can check. These names were the part that no published document pinned
    precisely enough to be sure of, so they live here, in one object, rather than being
    spelled inline in seven methods where a correction would be seven edits and a guess
    would look like a fact.

    **The defaults below are now MEASURED, not read.** On 2026-08-16 an ``initialize`` +
    ``tools/list`` against ``https://cockroachlabs.cloud/mcp`` returned twelve tools with
    their JSON Schemas, and these values are copied out of ``inputSchema.properties``.
    See :data:`DOCUMENTED_DIALECT` for what we had guessed and where the guess was wrong.

    Field-by-field, against the schemas as measured:

    ``statement``
        ``"query"`` — required on ``select_query``, ``explain_query``, ``insert_rows``;
        the only property of ``show_statement`` that is required.
    ``database``
        ``"database"`` — **required** on ``select_query``, ``explain_query``,
        ``list_tables``, ``get_table_schema`` and ``insert_rows``; optional on
        ``show_statement``; absent from ``list_databases`` and ``show_running_queries``.
    ``schema``
        ``"schema"`` — an optional property of ``get_table_schema`` only, documented as
        defaulting to ``public``. ``mainline_audit`` is not ``public``, so a schema-less
        call cannot see the audit views at all.
    ``table``
        ``"table"`` — required on ``get_table_schema``. It is **not** a property of
        ``insert_rows``; see :meth:`Client.insert_external_attestation` and the README's
        recorded divergence.
    ``rows``
        Not a property of any measured tool. Retained because the typed write surface it
        serves is deliberately unchanged — see the divergence note on the write method.
    ``limit``
        ``"limit"`` — a real integer property of ``list_databases`` and ``list_tables``
        (default 100, max 10000), alongside ``offset``. It is **not** a property of
        ``select_query``, ``explain_query``, ``show_statement`` or
        ``show_running_queries``; on ``select_query`` the schema says pagination is
        ``LIMIT``/``OFFSET`` *inside the statement*.
    ``cluster_id``
        ``"cluster_id"`` — an optional property of every cluster-scoped tool, documented
        as *"Required when the MCP config has no cluster_id; otherwise must be omitted."*
        This client pins by the ``mcp-cluster-id`` header and therefore never sends it;
        the field exists so :meth:`Client._screen_cluster` and the negative suite can
        name it.
    """

    statement: str = "query"
    database: str = "database"
    table: str = "table"
    rows: str = "rows"
    limit: str = "limit"
    cluster_id: str = "cluster_id"
    schema: str = "schema"


DEFAULT_DIALECT: Final = ToolDialect()
"""The measured live surface, 2026-08-16. Used unless a caller injects another."""

#: WHAT WE HAD GUESSED, KEPT ON PURPOSE.
#:
#: Until 2026-08-16 this package shipped ``statement="statement"`` and the README called
#: the names "our best reading of the documented surface". The reading was wrong in
#: exactly one field, and the server said so in five words: a ``select_query`` carrying
#: ``{"database": ..., "statement": ...}`` returns
#: ``{"code": 0, "message": "must contain exactly one statement"}`` — the session, the
#: bearer and the cluster pin were all fine; the required ``query`` property was simply
#: absent, so the server saw zero statements.
#:
#: Two further divergences were call sites rather than names, and are fixed at the call
#: sites rather than here:
#:
#: * ``limit`` was being *sent* to ``show_statement`` and ``show_running_queries``, which
#:   have no such property. It is no longer transmitted on those two verbs; the ceiling
#:   is still refused client-side, and is now ours rather than an argument.
#: * ``rows`` was being sent to ``insert_rows`` beside ``table``. The live shape is
#:   ``{database, query}`` with a full INSERT statement. That call is **not** corrected,
#:   because correcting it means building SQL inside the one method whose published
#:   guarantee is that no parameter names a table. The divergence is recorded instead.
#:
#: This constant is not dead code with a comment on it: ``tests/test_client.py`` asserts
#: that it differs from :data:`DEFAULT_DIALECT` in precisely the one field, so the
#: repository cannot quietly erase a guess it published.
DOCUMENTED_DIALECT: Final = ToolDialect(statement="statement")


@dataclass(frozen=True, slots=True)
class RawResponse:
    """One decoded MCP response together with the exact number of bytes it arrived as.

    ``byte_count`` is measured on the wire body, not on a re-serialisation of
    ``payload``: the response budget is a property of what the server sent, and
    re-encoding it here would measure our JSON writer instead.
    """

    byte_count: int
    payload: Mapping[str, Any]


class Transport(Protocol):
    """What the client needs from a transport: a pinned cluster and two verbs."""

    @property
    def cluster_id(self) -> str:
        """The one cluster this transport is pinned to."""
        ...

    def call_tool(self, name: str, arguments: Mapping[str, Any]) -> RawResponse:
        """Invoke one MCP tool and return the decoded response with its byte count."""
        ...

    def list_tool_names(self) -> tuple[str, ...]:
        """Return the tool names the server advertises."""
        ...

    def close(self) -> None:
        """Release any underlying connection."""
        ...


def _iter_sse_data(body: str) -> Iterator[str]:
    """Yield the ``data:`` payload of each SSE frame in ``body``."""
    buffer: list[str] = []
    for line in body.splitlines():
        if line.startswith("data:"):
            buffer.append(line[5:].lstrip())
        elif not line.strip() and buffer:
            yield "\n".join(buffer)
            buffer = []
    if buffer:
        yield "\n".join(buffer)


def _decode(response: httpx.Response) -> Mapping[str, Any]:
    """Decode a Streamable-HTTP response, which may be JSON or a single SSE frame."""
    content_type = response.headers.get("content-type", "")
    text = response.text
    if "text/event-stream" in content_type:
        for chunk in _iter_sse_data(text):
            try:
                decoded = json.loads(chunk)
            except json.JSONDecodeError:
                continue
            if isinstance(decoded, dict):
                return decoded
        raise ProtocolError("event-stream response contained no decodable JSON-RPC frame")
    try:
        decoded_body = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ProtocolError(f"response body is not JSON: {text[:200]!r}") from exc
    if not isinstance(decoded_body, dict):
        raise ProtocolError(
            f"response body is not a JSON-RPC object: {type(decoded_body).__name__}"
        )
    return decoded_body


class HttpStreamableTransport:
    """MCP Streamable HTTP against ``https://cockroachlabs.cloud/mcp``.

    Auth is a service-account key as ``Authorization: Bearer``; the cluster is pinned by
    the ``mcp-cluster-id`` header. The 20-second documented statement timeout is used as
    the client's own deadline, so a call that the server would abandon is abandoned here
    too rather than hanging behind a default socket timeout.
    """

    def __init__(
        self,
        *,
        api_key: str,
        cluster_id: str,
        endpoint: str = MCP_ENDPOINT,
        timeout: float = REQUEST_TIMEOUT_SECONDS,
        http_client: httpx.Client | None = None,
        protocol_version: str = PROTOCOL_VERSION,
    ) -> None:
        """Build a transport. No network traffic happens until the first call."""
        if not api_key:
            raise ProtocolError("an MCP service-account key is required")
        if not cluster_id:
            raise ProtocolError("a cluster id is required; the surface pins exactly one cluster")
        self._endpoint = endpoint
        self._cluster_id = cluster_id
        self._offered_version = protocol_version
        self._negotiated_version: str | None = None
        self._session_id: str | None = None
        self._request_id = 0
        self._server_info: Mapping[str, Any] = {}
        self._owns_client = http_client is None
        self._http = http_client or httpx.Client(timeout=timeout)
        self._headers: dict[str, str] = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            CLUSTER_HEADER: cluster_id,
        }

    @property
    def cluster_id(self) -> str:
        """The one cluster this transport is pinned to."""
        return self._cluster_id

    @property
    def negotiated_version(self) -> str | None:
        """The protocol revision the server named, once ``initialize`` has run."""
        return self._negotiated_version

    @property
    def server_info(self) -> Mapping[str, Any]:
        """The server's self-description from ``initialize``."""
        return self._server_info

    def __enter__(self) -> Self:
        """Open the session eagerly so a bad credential fails at the top of a block."""
        self.initialize()
        return self

    def __exit__(self, *_exc: object) -> None:
        """Close the underlying HTTP client if this transport created it."""
        self.close()

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    def _post(self, message: Mapping[str, Any]) -> httpx.Response:
        headers = dict(self._headers)
        if self._session_id is not None:
            headers["Mcp-Session-Id"] = self._session_id
        if self._negotiated_version is not None:
            headers["MCP-Protocol-Version"] = self._negotiated_version
        response = self._http.post(self._endpoint, headers=headers, json=message)
        if response.status_code >= httpx.codes.BAD_REQUEST:
            raise ToolCallFailed(
                str(message.get("method", "?")),
                f"HTTP {response.status_code}: {response.text[:400]}",
            )
        return response

    def _request(self, method: str, params: Mapping[str, Any]) -> RawResponse:
        message = {
            "jsonrpc": _JSONRPC,
            "id": self._next_id(),
            "method": method,
            "params": params,
        }
        response = self._post(message)
        session = response.headers.get(_SESSION_HEADER)
        if session:
            self._session_id = session
        payload = _decode(response)
        if "error" in payload:
            err = payload["error"]
            message_text = err.get("message", str(err)) if isinstance(err, dict) else str(err)
            raise ToolCallFailed(method, message_text)
        result = payload.get("result")
        if not isinstance(result, dict):
            raise ProtocolError(f"{method}: response carried no result object")
        return RawResponse(byte_count=len(response.content), payload=result)

    def initialize(self) -> Mapping[str, Any]:
        """Run the MCP handshake once; subsequent calls are a no-op.

        The offered protocol revision is ours; the **negotiated** one is whatever the
        server names, and it is recorded rather than asserted. A server on a different
        revision should produce a recorded fact, not a client-side opinion.
        """
        if self._negotiated_version is not None:
            return self._server_info
        raw = self._request(
            "initialize",
            {
                "protocolVersion": self._offered_version,
                "capabilities": {},
                "clientInfo": {"name": _CLIENT_NAME, "version": _CLIENT_VERSION},
            },
        )
        version = raw.payload.get("protocolVersion")
        self._negotiated_version = version if isinstance(version, str) else self._offered_version
        info = raw.payload.get("serverInfo")
        self._server_info = info if isinstance(info, dict) else {}
        notification = {"jsonrpc": _JSONRPC, "method": "notifications/initialized"}
        self._post(notification)
        return self._server_info

    def list_tool_names(self) -> tuple[str, ...]:
        """Return the advertised tool names."""
        self.initialize()
        raw = self._request("tools/list", {})
        tools = raw.payload.get("tools", [])
        if not isinstance(tools, list):
            raise ProtocolError("tools/list did not return a list")
        return tuple(
            str(entry["name"]) for entry in tools if isinstance(entry, dict) and "name" in entry
        )

    def call_tool(self, name: str, arguments: Mapping[str, Any]) -> RawResponse:
        """Invoke one tool."""
        self.initialize()
        return self._request("tools/call", {"name": name, "arguments": dict(arguments)})

    def close(self) -> None:
        """Close the HTTP client if this transport owns it."""
        if self._owns_client:
            self._http.close()


def _extract_rows(payload: Mapping[str, Any], text: str) -> tuple[Mapping[str, Any], ...] | None:
    """Recover the result rows from an MCP tool result, or ``None`` if they are not there.

    Tolerant on purpose, and honest about it: a tool result may carry structured content
    or a JSON string in a text block, and the exact envelope of CockroachDB's
    ``select_query`` was not verifiable from this machine. What is **not** tolerant is
    the caller — :mod:`mainline_mcp.budget` treats ``None`` as a budget breach, because
    an audit view whose row count cannot be determined has not been verified.
    """

    def from_container(container: Any) -> tuple[Mapping[str, Any], ...] | None:
        if isinstance(container, list):
            if all(isinstance(entry, dict) for entry in container):
                return tuple(container)
            return None
        if isinstance(container, dict):
            for key in _ROW_KEYS:
                if key in container:
                    return from_container(container[key])
        return None

    structured = payload.get("structuredContent")
    if structured is not None:
        found = from_container(structured)
        if found is not None:
            return found
    if text:
        try:
            decoded = json.loads(text)
        except json.JSONDecodeError:
            return None
        return from_container(decoded)
    return None


@dataclass(frozen=True, slots=True)
class ToolResult:
    """One tool response: its text, its rows if they could be recovered, and its size."""

    tool: str
    byte_count: int
    is_error: bool
    text: str
    rows: tuple[Mapping[str, Any], ...] | None
    payload: Mapping[str, Any] = field(repr=False)

    @property
    def row_count(self) -> int | None:
        """Number of rows, or ``None`` when the envelope could not be parsed as rows."""
        return None if self.rows is None else len(self.rows)

    @classmethod
    def from_raw(cls, tool: str, raw: RawResponse) -> ToolResult:
        """Build a result from a decoded response, flattening the content blocks to text."""
        content = raw.payload.get("content", [])
        blocks: list[str] = []
        if isinstance(content, list):
            blocks = [
                str(block.get("text", ""))
                for block in content
                if isinstance(block, dict) and block.get("type") == "text"
            ]
        text = "\n".join(b for b in blocks if b)
        return cls(
            tool=tool,
            byte_count=raw.byte_count,
            is_error=bool(raw.payload.get("isError", False)),
            text=text,
            rows=_extract_rows(raw.payload, text),
            payload=raw.payload,
        )


class Client:
    """The read verbs, the one write verb, and every documented limit enforced first."""

    def __init__(
        self,
        transport: Transport,
        *,
        dialect: ToolDialect = DEFAULT_DIALECT,
        database: str | None = None,
    ) -> None:
        """Wrap a transport. The cluster pin is read from the transport, never re-declared.

        ``database`` is the measured consequence of 2026-08-16: the live ``select_query``
        and ``explain_query`` schemas list ``database`` as **required**, and every caller
        in this repository — the auditor, the prober, the judge-pack runner — asks its
        question of a *view*, not of a database, and so never had one to pass. Carrying it
        on the client rather than threading it through every call site keeps the question
        the caller's and the connection detail ours. When it is unset the argument is
        omitted, which is what this client did before the measurement and is therefore not
        a behaviour change for any offline caller; against the live server an omitted
        required argument produces the server's own error, which is a recorded fact rather
        than a silent success.
        """
        self._transport = transport
        self._dialect = dialect
        self._database = database
        self._last_elapsed_ms: float = 0.0

    @classmethod
    def connect(
        cls,
        *,
        api_key: str,
        cluster_id: str,
        endpoint: str = MCP_ENDPOINT,
        timeout: float = REQUEST_TIMEOUT_SECONDS,
        database: str | None = None,
    ) -> Client:
        """Build a client over a live Streamable-HTTP transport."""
        return cls(
            HttpStreamableTransport(
                api_key=api_key,
                cluster_id=cluster_id,
                endpoint=endpoint,
                timeout=timeout,
            ),
            database=database,
        )

    @property
    def cluster_id(self) -> str:
        """The pinned cluster."""
        return self._transport.cluster_id

    @property
    def dialect(self) -> ToolDialect:
        """The tool-argument names in use, read by the probes below."""
        return self._dialect

    @property
    def database(self) -> str | None:
        """The database sent when a call does not name one, or ``None`` to omit it."""
        return self._database

    def _resolve_database(self, database: str | None) -> str | None:
        """Per-call database, else the client's, else ``None`` meaning "omit"."""
        return database if database is not None else self._database

    @property
    def transport(self) -> Transport:
        """The underlying transport.

        Public because the negative-reachability suite has to reach past the client's own
        cluster screen to record that the *server* refuses a foreign ``cluster_id``. A
        control that exists only in our client is a control an attacker skips by not using
        our client, so the suite must be able to skip it too.
        """
        return self._transport

    @property
    def last_elapsed_ms(self) -> float:
        """Wall-clock duration of the most recent tool call, in milliseconds."""
        return self._last_elapsed_ms

    def tool_names(self) -> tuple[str, ...]:
        """Return the tool names the server advertises."""
        return self._transport.list_tool_names()

    def close(self) -> None:
        """Release the transport."""
        self._transport.close()

    def __enter__(self) -> Self:
        """Return self; the transport opens lazily on first use."""
        return self

    def __exit__(self, *_exc: object) -> None:
        """Release the transport."""
        self.close()

    def _screen_cluster(self, arguments: Mapping[str, Any]) -> None:
        """Refuse any argument that names a cluster other than the pinned one."""
        for key, value in arguments.items():
            if key.endswith("cluster_id") and str(value) != self.cluster_id:
                raise ClusterPinViolation(
                    f"argument {key}={value!r} names a cluster other than the pinned "
                    f"{self.cluster_id!r}; the surface pins exactly one cluster"
                )

    def call(
        self,
        tool: str,
        arguments: Mapping[str, Any],
        *,
        enforce_cap: bool = True,
    ) -> ToolResult:
        """Invoke a tool with the cluster screen and the response-size check applied."""
        self._screen_cluster(arguments)
        started = time.monotonic()
        raw = self._transport.call_tool(tool, arguments)
        self._last_elapsed_ms = (time.monotonic() - started) * 1000.0
        if enforce_cap:
            enforce_response_size(raw.byte_count, tool=tool)
        return ToolResult.from_raw(tool, raw)

    # ── read verbs ───────────────────────────────────────────────────────────────

    def list_databases(self, *, limit: int = LIST_DEFAULT_ROWS) -> ToolResult:
        """List databases on the pinned cluster.

        ``limit`` is a real property here — measured 2026-08-16, integer, "default: 100,
        max: 10000". This client keeps its own ceiling at 100, which is below the
        server's and therefore never widens it.
        """
        rows = enforce_row_limit(limit, verb="list_databases", maximum=LIST_DEFAULT_ROWS)
        return self.call("list_databases", {self._dialect.limit: rows})

    def list_tables(self, database: str, *, limit: int = LIST_DEFAULT_ROWS) -> ToolResult:
        """List tables in ``database``. ``database`` and ``limit`` are both measured real."""
        rows = enforce_row_limit(limit, verb="list_tables", maximum=LIST_DEFAULT_ROWS)
        return self.call(
            "list_tables",
            {self._dialect.database: database, self._dialect.limit: rows},
        )

    def get_table_schema(
        self,
        database: str,
        table: str,
        *,
        schema: str | None = None,
    ) -> ToolResult:
        """Return the schema of one table.

        ``schema`` is optional on the wire and, measured 2026-08-16, *"defaults to
        'public' if not specified"*. Every view this product exposes lives in
        ``mainline_audit``, so omitting it is the difference between reading our audit
        surface and reading nothing. It stays optional rather than required because the
        server's default is a real default, not an error.
        """
        arguments: dict[str, Any] = {
            self._dialect.database: database,
            self._dialect.table: table,
        }
        if schema is not None:
            arguments[self._dialect.schema] = schema
        return self.call("get_table_schema", arguments)

    def select_query(
        self,
        statement: str,
        *,
        database: str | None = None,
        max_rows: int = SELECT_MAX_ROWS,
        enforce_cap: bool = True,
    ) -> ToolResult:
        """Run one ``SELECT``, refusing client-side if it would breach a documented limit.

        ``max_rows`` may lower the ceiling and never raise it: it is clamped to the
        server's documented maximum first. A caller — including a contract file — that
        asks for a wider read than the surface can serve gets a refusal naming the
        server's limit, not a widened client.

        There is no ``limit`` **argument** on this verb — measured 2026-08-16, the schema
        carries exactly ``cluster_id``, ``database`` and ``query`` and says *"Use
        LIMIT/OFFSET in your query for pagination."* So the row ceiling is enforced by
        reading the ``LIMIT`` the caller wrote, which is what ``enforce_statement``
        already did, and nothing about the ceiling is sent.
        """
        ceiling = min(max_rows, SELECT_MAX_ROWS)
        enforce_statement(statement, verb="select_query", max_rows=ceiling)
        arguments: dict[str, Any] = {self._dialect.statement: statement}
        resolved = self._resolve_database(database)
        if resolved is not None:
            arguments[self._dialect.database] = resolved
        return self.call("select_query", arguments, enforce_cap=enforce_cap)

    def explain_query(self, statement: str, *, database: str | None = None) -> ToolResult:
        """Run one ``EXPLAIN``.

        **Pass the query to be explained, NOT an ``EXPLAIN`` statement.** Measured
        2026-08-16: the property is documented as *"The SQL query to explain"*, the server
        prepends ``EXPLAIN`` itself, and a statement that already begins with ``EXPLAIN``
        comes back as ``EXPLAIN is not allowed for EXPLAIN statements``. A bare
        ``SELECT * FROM mainline_audit.v_open_gate_summary LIMIT 25`` returned a 4 421-byte
        plan on the same connection. This method does **not** strip a leading ``EXPLAIN``
        for you: rewriting a caller's SQL is exactly the silent helpfulness this package
        exists to refuse, so the divergence is stated here and the caller decides.

        ``EXPLAIN ANALYZE`` is still refused before transmission — that screen is what
        stops a caller who writes it from *executing* the query on a plan-shape call, and
        it fires whether or not the server would have accepted the prefix.

        The per-arm discipline that keeps a plan inside the 10 KiB cap (decision A10 — one
        ANN arm per call, never a twelve-arm ``UNION ALL``) belongs to
        ``packages/mainline-indextruth``, which is this verb's only caller in the product.
        """
        enforce_statement(statement, verb="explain_query", max_rows=SELECT_MAX_ROWS)
        arguments: dict[str, Any] = {self._dialect.statement: statement}
        resolved = self._resolve_database(database)
        if resolved is not None:
            arguments[self._dialect.database] = resolved
        return self.call("explain_query", arguments)

    def show_statement(
        self,
        statement: str,
        *,
        limit: int = SHOW_MAX_ROWS,
        database: str | None = None,
    ) -> ToolResult:
        """Run one ``SHOW``, whose output this client holds to 100 rows.

        ``limit`` is **refused client-side and not transmitted.** Measured 2026-08-16,
        this tool's schema is ``{cluster_id, database, query}`` with ``query`` the only
        required property — there is no ``limit`` argument to carry a ceiling in. Keeping
        the refusal while dropping the argument is the honest reading of that: the number
        is now ours, enforced here, and no longer described as the server's.

        ``database`` is optional on this verb by measurement — *"optional for
        cluster-level statements like SHOW DATABASES"* — so it is optional here too.
        """
        enforce_statement(statement, verb="show_statement", max_rows=SHOW_MAX_ROWS)
        enforce_row_limit(limit, verb="show_statement", maximum=SHOW_MAX_ROWS)
        arguments: dict[str, Any] = {self._dialect.statement: statement}
        resolved = self._resolve_database(database)
        if resolved is not None:
            arguments[self._dialect.database] = resolved
        return self.call("show_statement", arguments)

    def show_running_queries(self, *, limit: int = SHOW_MAX_ROWS) -> ToolResult:
        """List currently running queries, held to 100 rows by this client.

        Measured 2026-08-16, this tool's schema carries ``cluster_id`` and nothing else.
        As with :meth:`show_statement`, ``limit`` is refused here and not sent.
        """
        enforce_row_limit(limit, verb="show_running_queries", maximum=SHOW_MAX_ROWS)
        return self.call("show_running_queries", {})

    # ── the one write verb ───────────────────────────────────────────────────────

    def insert_external_attestation(self, rows: Sequence[Mapping[str, Any]]) -> ToolResult:
        """Append rows to ``mainline_meas.external_attestation`` — the only writable table.

        There is no ``table`` parameter, and there will not be one. An external
        verifier's agent records the outcome of *its own* verification into our log;
        that is a third party's claim about our log and never our claim about the world,
        which is exactly why the insert-only write surface is the right shape for it.

        The target table is trigger-free by construction (risk AR-5): whether
        ``insert_rows`` fires server-side triggers is unverified, and the design is
        correct under either answer.

        **A DIVERGENCE, RECORDED RATHER THAN CLOSED.** Measured 2026-08-16, the live
        ``insert_rows`` schema is ``{cluster_id, database, query}`` with ``database`` and
        ``query`` required, and ``query`` documented as *"The INSERT statement to
        execute. Include the full table name with optional schema prefix …"*. There is no
        ``table`` property and no ``rows`` property. Speaking that shape means composing
        an INSERT statement — with a table name in it — inside the one method whose entire
        published guarantee is that no parameter names a table. That guarantee is worth
        more than the call, so this method is left exactly as it was, **this call has not
        been sent to the live server, and no claim is made that it succeeds there.** The
        divergence is stated in the package README and is the honest end of the sentence
        the class docstring starts.
        """
        if not rows:
            raise WriteTargetRefused("an attestation with no rows records nothing")
        return self.call(
            "insert_rows",
            {
                self._dialect.table: EXTERNAL_ATTESTATION_TABLE,
                self._dialect.rows: [dict(row) for row in rows],
            },
        )


# ── probes: the two calls the supported API deliberately cannot express ──────────


def probe_select_unscreened(client: Client, statement: str, *, why: str) -> ToolResult:
    """Send a ``SELECT`` with the forbidden-schema screen OFF, so the SERVER refuses it.

    The client-side screen in :mod:`mainline_mcp.limits` is a diagnosability aid. The
    security property is the server's, and the only way to record that the server holds
    it is to ask the server. That is what this function is for, and it is why
    ``tests/integration/mcp/test_negative_reachability.py`` exists.

    Args:
        client: a connected client.
        statement: the statement to send, screens off.
        why: a non-empty sentence recording why the screen was bypassed. Mandatory:
            an unscreened call with no stated reason is indistinguishable from a
            mistake, and this function's whole value is that it is never a mistake.

    Returns:
        The result, including a server error result, which the caller asserts on.
    """
    if not why.strip():
        raise WriteTargetRefused("probe_select_unscreened requires a stated reason")
    enforce_statement(
        statement,
        verb="select_query",
        max_rows=SELECT_MAX_ROWS,
        screen_schemas=False,
    )
    arguments: dict[str, Any] = {client.dialect.statement: statement}
    if client.database is not None:
        arguments[client.dialect.database] = client.database
    return client.call("select_query", arguments, enforce_cap=False)


def probe_insert_rows_unbound(
    client: Client,
    table: str,
    rows: Sequence[Mapping[str, Any]],
    *,
    why: str,
) -> ToolResult:
    """Attempt ``insert_rows`` against an arbitrary table, so the SERVER refuses it.

    The supported API cannot name a table (see
    :meth:`Client.insert_external_attestation`). This function exists so the negative
    suite can prove the *grant* holds — ``mainline_auditor`` has INSERT on
    ``mainline_meas.external_attestation`` and on nothing else (§11.2, S13) — rather
    than merely proving that our own client is polite.

    Args:
        client: a connected client.
        table: the fully qualified table to attempt.
        rows: the rows to attempt.
        why: a non-empty sentence recording why an unbound write was attempted.

    Returns:
        The result, which for any table other than ``external_attestation`` is expected
        to be an error result.
    """
    if not why.strip():
        raise WriteTargetRefused("probe_insert_rows_unbound requires a stated reason")
    return client.call(
        "insert_rows",
        {
            client.dialect.table: table,
            client.dialect.rows: [dict(row) for row in rows],
        },
        enforce_cap=False,
    )
