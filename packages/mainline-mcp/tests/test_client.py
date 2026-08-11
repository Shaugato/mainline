# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The client: the cluster pin, the write binding, and the real HTTP path with no socket.

``TestStreamableHttp`` drives :class:`~mainline_mcp.client.HttpStreamableTransport` —
the actual production transport, byte for byte — against ``httpx.MockTransport``. The
handshake, the session header, the SSE framing and the cluster header are therefore
covered offline. What such a test cannot cover is whether CockroachDB's own server names
its ``select_query`` argument ``statement``; that one unverifiable detail is isolated in
:class:`~mainline_mcp.client.ToolDialect` and is stated as unverified in the README and
in ``VERIFY.md``, rather than being asserted here as though it were known.
"""

from __future__ import annotations

import inspect
import json

import httpx
import pytest
from mainline_mcp.client import (
    Client,
    HttpStreamableTransport,
    ToolResult,
    probe_insert_rows_unbound,
    probe_select_unscreened,
)
from mainline_mcp.limits import (
    EXTERNAL_ATTESTATION_TABLE,
    MAX_RESPONSE_BYTES,
    READ_VERBS,
    WRITE_VERB,
    ClusterPinViolation,
    ForbiddenSchema,
    ProtocolError,
    ResponseTooLarge,
    WriteTargetRefused,
)

from conftest import StubResponse, StubTransport, rows_payload, text_payload

PINNED = "cl-stub-0001"


class TestClusterPin:
    def test_a_different_cluster_id_is_refused_before_transmission(self, client, transport):
        with pytest.raises(ClusterPinViolation) as excinfo:
            client.call("select_query", {"statement": "SELECT 1", "cluster_id": "cl-other"})
        assert "cl-other" in str(excinfo.value)
        assert transport.calls == []

    def test_the_pinned_cluster_id_passes(self, client, transport):
        client.call("select_query", {"statement": "SELECT 1", "cluster_id": PINNED})
        assert len(transport.calls) == 1

    def test_the_pin_is_read_from_the_transport_not_re_declared(self, client):
        assert client.cluster_id == PINNED


class TestWriteBinding:
    def test_the_write_verb_has_no_table_parameter(self):
        # The binding is in the TYPE. If a `table` parameter is ever added here, this
        # test is what notices — before a reviewer has to.
        parameters = set(inspect.signature(Client.insert_external_attestation).parameters)
        assert parameters == {"self", "rows"}

    def test_the_write_verb_targets_external_attestation_and_nothing_else(self, client, transport):
        client.insert_external_attestation([{"verifier": "acme", "outcome": "pass"}])
        tool, arguments = transport.calls[0]
        assert tool == WRITE_VERB
        assert arguments["table"] == EXTERNAL_ATTESTATION_TABLE

    def test_an_empty_attestation_is_refused(self, client):
        with pytest.raises(WriteTargetRefused):
            client.insert_external_attestation([])


class TestReadVerbs:
    def test_every_documented_read_verb_is_exposed(self):
        for verb in READ_VERBS:
            assert hasattr(Client, verb), verb

    def test_select_query_enforces_the_statement_limits_first(self, client, transport):
        with pytest.raises(ForbiddenSchema):
            client.select_query("SELECT * FROM crdb_internal.jobs")
        assert transport.calls == []

    def test_list_verbs_are_capped_at_one_hundred(self, client):
        from mainline_mcp.limits import RowLimitTooHigh

        with pytest.raises(RowLimitTooHigh):
            client.list_databases(limit=101)
        with pytest.raises(RowLimitTooHigh):
            client.show_running_queries(limit=101)

    def test_a_response_at_the_cap_is_refused_as_a_possible_truncation(self):
        transport = StubTransport(
            handlers={"select_query": lambda _a: StubResponse(rows_payload([]), MAX_RESPONSE_BYTES)}
        )
        client = Client(transport)
        with pytest.raises(ResponseTooLarge):
            client.select_query("SELECT * FROM mainline_audit.v_ledger_health LIMIT 25")

    def test_the_cap_check_can_be_waived_so_the_prober_can_measure(self):
        transport = StubTransport(
            handlers={"select_query": lambda _a: StubResponse(rows_payload([]), MAX_RESPONSE_BYTES)}
        )
        client = Client(transport)
        result = client.select_query(
            "SELECT * FROM mainline_audit.v_ledger_health LIMIT 25",
            enforce_cap=False,
        )
        assert result.byte_count == MAX_RESPONSE_BYTES


class TestRowExtraction:
    def test_rows_are_recovered_from_a_json_text_block(self):
        result = ToolResult.from_raw(
            "select_query",
            _raw(rows_payload([{"site_id": "s1", "n": 2}])),
        )
        assert result.row_count == 1
        assert result.rows is not None
        assert result.rows[0]["site_id"] == "s1"

    def test_rows_are_recovered_from_structured_content(self):
        payload = {"structuredContent": {"rows": [{"a": 1}, {"a": 2}]}, "content": []}
        result = ToolResult.from_raw("select_query", _raw(payload))
        assert result.row_count == 2

    def test_a_bare_json_list_is_accepted_as_rows(self):
        payload = {"content": [{"type": "text", "text": json.dumps([{"a": 1}])}]}
        assert ToolResult.from_raw("select_query", _raw(payload)).row_count == 1

    def test_unparseable_text_reports_no_row_count_rather_than_zero(self):
        # Reporting 0 here would be a lie that reads as "the view is empty".
        result = ToolResult.from_raw("select_query", _raw(text_payload("relation does not exist")))
        assert result.rows is None
        assert result.row_count is None

    def test_an_error_result_is_visible(self):
        result = ToolResult.from_raw("select_query", _raw(text_payload("nope", is_error=True)))
        assert result.is_error


class TestProbes:
    def test_the_unscreened_probe_requires_a_stated_reason(self, client):
        with pytest.raises(WriteTargetRefused):
            probe_select_unscreened(client, "SELECT * FROM crdb_internal.jobs", why="  ")

    def test_the_unscreened_probe_reaches_the_transport(self, client, transport):
        probe_select_unscreened(
            client,
            "SELECT * FROM crdb_internal.jobs",
            why="negative reachability: the server must be the one that refuses",
        )
        assert transport.calls[0][0] == "select_query"

    def test_the_unscreened_probe_still_enforces_the_shape_limits(self, client):
        from mainline_mcp.limits import MultipleStatements

        with pytest.raises(MultipleStatements):
            probe_select_unscreened(
                client,
                "SELECT * FROM crdb_internal.jobs; SELECT 1",
                why="two statements are refused even in a probe",
            )

    def test_the_unbound_insert_probe_requires_a_stated_reason(self, client):
        with pytest.raises(WriteTargetRefused):
            probe_insert_rows_unbound(client, "mainline.permit", [{"a": 1}], why="")

    def test_the_unbound_insert_probe_can_name_any_table(self, client, transport):
        probe_insert_rows_unbound(
            client,
            "mainline.permit",
            [{"a": 1}],
            why="negative reachability: the grant, not our client, must be what refuses",
        )
        assert transport.calls[0][1]["table"] == "mainline.permit"


# ── the real transport, no socket ────────────────────────────────────────────────


def _raw(payload):
    from mainline_mcp.client import RawResponse

    return RawResponse(byte_count=len(json.dumps(payload).encode()), payload=payload)


def _jsonrpc(request: httpx.Request):
    return json.loads(request.content.decode())


class _Server:
    """A minimal MCP server good enough to exercise the transport's whole handshake."""

    def __init__(self, *, sse: bool = False, protocol_version: str = "2025-06-18") -> None:
        self.sse = sse
        self.protocol_version = protocol_version
        self.seen: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.seen.append(request)
        message = _jsonrpc(request)
        method = message.get("method")
        if method == "notifications/initialized":
            return httpx.Response(202)
        if method == "initialize":
            result = {
                "protocolVersion": self.protocol_version,
                "capabilities": {},
                "serverInfo": {"name": "cockroachdb-managed-mcp", "version": "test"},
            }
            return self._reply(message["id"], result, headers={"Mcp-Session-Id": "sess-1"})
        if method == "tools/list":
            return self._reply(
                message["id"],
                {"tools": [{"name": name} for name in (*READ_VERBS, WRITE_VERB)]},
            )
        if method == "tools/call":
            return self._reply(message["id"], rows_payload([{"ok": True}]))
        return self._reply(message["id"], {})

    def _reply(self, request_id, result, headers=None):
        body = json.dumps({"jsonrpc": "2.0", "id": request_id, "result": result})
        if self.sse:
            return httpx.Response(
                200,
                text=f"event: message\ndata: {body}\n\n",
                headers={"content-type": "text/event-stream", **(headers or {})},
            )
        return httpx.Response(
            200,
            text=body,
            headers={"content-type": "application/json", **(headers or {})},
        )


class TestStreamableHttp:
    def _transport(self, server: _Server) -> HttpStreamableTransport:
        return HttpStreamableTransport(
            api_key="key-for-a-test-only",
            cluster_id=PINNED,
            http_client=httpx.Client(transport=httpx.MockTransport(server)),
        )

    def test_handshake_sends_the_bearer_and_the_cluster_header(self):
        server = _Server()
        with self._transport(server) as transport:
            assert transport.cluster_id == PINNED
        first = server.seen[0]
        assert first.headers["authorization"] == "Bearer key-for-a-test-only"
        assert first.headers["mcp-cluster-id"] == PINNED

    def test_the_session_header_is_echoed_on_later_requests(self):
        server = _Server()
        transport = self._transport(server)
        transport.initialize()
        transport.list_tool_names()
        assert server.seen[-1].headers["mcp-session-id"] == "sess-1"

    def test_the_negotiated_protocol_version_is_recorded_not_asserted(self):
        server = _Server(protocol_version="2099-01-01")
        transport = self._transport(server)
        transport.initialize()
        assert transport.negotiated_version == "2099-01-01"

    def test_an_sse_framed_response_decodes(self):
        server = _Server(sse=True)
        transport = self._transport(server)
        assert set(transport.list_tool_names()) == {*READ_VERBS, WRITE_VERB}

    def test_the_advertised_tools_include_every_verb_this_client_uses(self):
        server = _Server()
        client = Client(self._transport(server))
        names = set(client.tool_names())
        assert set(READ_VERBS) <= names
        assert WRITE_VERB in names

    def test_a_tool_call_measures_the_wire_bytes(self):
        server = _Server()
        client = Client(self._transport(server))
        result = client.select_query("SELECT * FROM mainline_audit.v_ledger_health LIMIT 25")
        assert result.byte_count > 0
        assert result.row_count == 1

    def test_a_missing_credential_is_refused_at_construction(self):
        with pytest.raises(ProtocolError):
            HttpStreamableTransport(api_key="", cluster_id=PINNED)
        with pytest.raises(ProtocolError):
            HttpStreamableTransport(api_key="k", cluster_id="")

    def test_an_http_error_is_raised_with_the_body(self):
        from mainline_mcp.limits import ToolCallFailed

        def failing(_request: httpx.Request) -> httpx.Response:
            return httpx.Response(403, text="forbidden: the key has no access to this cluster")

        transport = HttpStreamableTransport(
            api_key="k",
            cluster_id=PINNED,
            http_client=httpx.Client(transport=httpx.MockTransport(failing)),
        )
        with pytest.raises(ToolCallFailed) as excinfo:
            transport.initialize()
        assert "403" in str(excinfo.value)
