# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The NEGATIVE suite: what the Managed-MCP identity must not be able to reach, ever.

A positive assertion beside no negative one is a claim, not a test. These are the four
negatives that carry the audit surface:

1. ``mainline_qa`` is unreachable. It holds per-named-person deliberation measurement and
   receives no MCP service account on any tier, ever (S14). **This one is ours** — the
   server has no opinion about the schema; the grant does.
2. ``system``, ``crdb_internal``, ``pg_catalog``, ``information_schema`` and
   ``pg_extension`` are unreachable. That is CockroachDB's constraint, and asserting it is
   what proves the ``mainline_audit`` ops views are the API rather than a bypass around it.
3. ``insert_rows`` is rejected on every table except ``mainline_meas.external_attestation``
   (S13, §11.2). Asserted against the **grant**, not against our client's politeness —
   which is why :func:`~mainline_mcp.client.probe_insert_rows_unbound` exists.
4. A tool call naming a different cluster fails.

Each probe deliberately bypasses our own client-side screen, because a control that lives
only in our client is a control an attacker skips by not using our client. What the probe
records is that the **server** refused.

**This module never passes without a credential.** The skip is module-level. A negative
suite that went green with nothing to talk to would be the most dangerous green in the
repository: it would assert that unreachable things are unreachable by never having tried.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SRC = _REPO_ROOT / "packages" / "mainline-mcp" / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from mainline_mcp.client import (  # noqa: E402
    Client,
    ToolResult,
    probe_insert_rows_unbound,
    probe_select_unscreened,
)
from mainline_mcp.limits import (  # noqa: E402
    EXTERNAL_ATTESTATION_TABLE,
    FORBIDDEN_SCHEMAS,
    NEVER_MCP_SCHEMAS,
    ClusterPinViolation,
    ExplainAnalyzeRefused,
    McpClientError,
    MultipleStatements,
    QaSchemaRefused,
    enforce_statement,
)

_WHY_SCHEMA = (
    "negative reachability: our own screen is a diagnosability aid; the security property "
    "is the server's, and the only way to record that it holds is to ask the server"
)
_WHY_WRITE = (
    "negative reachability: the grant on mainline_auditor is what must refuse this, not our "
    "client's politeness"
)


def _credentials() -> tuple[str, str] | None:
    api_key = os.environ.get("MAINLINE_MCP_API_KEY") or os.environ.get("CC_API_KEY")
    cluster = os.environ.get("MAINLINE_MCP_CLUSTER_ID") or os.environ.get("CRDB_CLUSTER")
    if api_key and cluster:
        return api_key, cluster
    return None


_REASON = (
    ""
    if _credentials() is not None
    else (
        "no Managed-MCP credential: set MAINLINE_MCP_API_KEY and MAINLINE_MCP_CLUSTER_ID "
        "(or CC_API_KEY and CRDB_CLUSTER). This suite SKIPS rather than passes — a negative "
        "suite that goes green without ever trying asserts the opposite of what it claims."
    )
)

pytestmark = [
    pytest.mark.requires_cluster,
    pytest.mark.skipif(bool(_REASON), reason=_REASON or "credential present"),
]

# Statements chosen to be legal SQL that a permitted identity could run, so a refusal is
# attributable to reachability and not to a syntax error.
UNREACHABLE_STATEMENTS = {
    "system": "SELECT count(*) FROM system.jobs",
    "crdb_internal": "SELECT count(*) FROM crdb_internal.jobs",
    "pg_catalog": "SELECT count(*) FROM pg_catalog.pg_class",
    "information_schema": "SELECT count(*) FROM information_schema.tables",
    "pg_extension": "SELECT count(*) FROM pg_extension.pg_extension",
    "mainline_qa": "SELECT count(*) FROM mainline_qa.v_disposition_profile",
}

FORBIDDEN_WRITE_TARGETS = (
    "mainline.permit",
    "mainline.disposition",
    "mainline.blocking_check",
    "mainline.ledger_leaf",
    "mainline_meas.silence_ledger",
    "mainline_qa.v_disposition_profile",
)


@pytest.fixture(scope="module")
def client():
    credentials = _credentials()
    assert credentials is not None
    api_key, cluster_id = credentials
    connected = Client.connect(api_key=api_key, cluster_id=cluster_id)
    yield connected
    connected.close()


def _assert_server_refused(action, *, what: str) -> str:
    """Run ``action`` and assert the SERVER refused it; return the refusal text."""
    try:
        result = action()
    except McpClientError as exc:
        return f"{type(exc).__name__}: {exc}"
    assert result.is_error, (
        f"{what} was NOT refused. The server answered: {result.text[:400]!r}. "
        "This is a reachability failure, not a test failure."
    )
    return result.text


class TestSchemasAreUnreachable:
    @pytest.mark.parametrize("schema", sorted(FORBIDDEN_SCHEMAS))
    def test_a_system_schema_is_unreachable(self, client, schema):
        refusal = _assert_server_refused(
            lambda: probe_select_unscreened(
                client, UNREACHABLE_STATEMENTS[schema], why=_WHY_SCHEMA
            ),
            what=f"a SELECT against {schema}",
        )
        print(f"{schema}: refused — {refusal[:200]}")

    def test_mainline_qa_is_unreachable_on_any_tier_ever(self, client):
        refusal = _assert_server_refused(
            lambda: probe_select_unscreened(
                client, UNREACHABLE_STATEMENTS["mainline_qa"], why=_WHY_SCHEMA
            ),
            what="a SELECT against mainline_qa",
        )
        print(f"mainline_qa: refused — {refusal[:200]}")

    def test_our_client_refuses_the_same_schemas_without_a_network_call(self):
        # Belt and braces, and the braces are the ones above. This asserts only that the
        # two agree, so a future relaxation of the client screen is visible next to the
        # server assertion it was supposed to mirror.
        for schema in sorted(FORBIDDEN_SCHEMAS | NEVER_MCP_SCHEMAS):
            with pytest.raises(McpClientError):
                enforce_statement(UNREACHABLE_STATEMENTS[schema], verb="select_query")

    def test_the_qa_refusal_is_typed_as_ours_not_the_servers(self):
        with pytest.raises(QaSchemaRefused):
            enforce_statement(UNREACHABLE_STATEMENTS["mainline_qa"], verb="select_query")


class TestWriteSurface:
    @pytest.mark.parametrize("table", FORBIDDEN_WRITE_TARGETS)
    def test_insert_rows_is_rejected_outside_external_attestation(self, client, table):
        refusal = _assert_server_refused(
            lambda: probe_insert_rows_unbound(
                client,
                table,
                [{"probe": "negative reachability"}],
                why=_WHY_WRITE,
            ),
            what=f"an insert_rows into {table}",
        )
        print(f"{table}: refused — {refusal[:200]}")

    def test_the_only_writable_table_is_the_one_the_architecture_names(self):
        assert EXTERNAL_ATTESTATION_TABLE == "mainline_meas.external_attestation"
        assert EXTERNAL_ATTESTATION_TABLE not in FORBIDDEN_WRITE_TARGETS


class TestClusterPin:
    def test_our_client_refuses_a_different_cluster_before_transmission(self, client):
        with pytest.raises(ClusterPinViolation):
            client.call(
                "select_query",
                {"statement": "SELECT 1", "cluster_id": "cl-definitely-not-ours"},
            )

    def test_the_server_refuses_a_different_cluster_too(self, client):
        # Bypass our own screen the only way there is — go at the transport directly —
        # so what is recorded is the SERVER's refusal of a foreign cluster_id.
        def foreign_cluster_call():
            raw = client.transport.call_tool(
                "select_query",
                {"statement": "SELECT 1", "cluster_id": "cl-definitely-not-ours"},
            )
            return ToolResult.from_raw("select_query", raw)

        refusal = _assert_server_refused(
            foreign_cluster_call,
            what="a select_query naming a foreign cluster_id",
        )
        print(f"foreign cluster_id: refused — {refusal[:200]}")


class TestOtherRefusals:
    def test_explain_analyze_is_unavailable(self, client):
        with pytest.raises(ExplainAnalyzeRefused):
            client.explain_query("EXPLAIN ANALYZE SELECT 1")

    def test_two_statements_in_one_call_are_refused(self, client):
        with pytest.raises(MultipleStatements):
            client.select_query("SELECT 1; SELECT 2")
