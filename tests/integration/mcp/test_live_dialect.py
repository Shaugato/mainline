# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The DIALECT suite: what this repository recorded, checked against what the server says.

Every other module in this directory asks the Managed MCP Server a *question*. This one
asks it for its **JSON Schemas** and compares them, field by field, with the constants
this repository published after measuring them.

Why that is worth a suite of its own. On 2026-08-16 this package shipped
``ToolDialect.statement = "statement"``. The live ``select_query`` takes ``query``. The
consequence was not an exception with a stack trace — it was
``{"code": 0, "message": "must contain exactly one statement"}``, because the server read
the property it knows about, found nothing there, and truthfully reported that it had been
sent no statement. **A wrong argument name does not look like a wrong argument name.** It
looks like a wrong answer, and in the negative suite next door it looks like a *refusal* —
which is the one shape of wrongness this repository has spent its whole existence refusing
to ship. The fix (M1) was one field. Nothing in the tree would have told us it had come
undone.

So this suite pins the names to their source of truth. Not to our prose, not to
CockroachDB's published documentation, not to a transcript taken once — to
``tools/list``'s ``inputSchema``, fetched live, on the day the suite runs. If Cockroach
Labs renames ``query`` back to ``statement``, or drops ``limit`` from ``list_tables``, or
ships an ``insert_rows`` that finally takes ``{table, rows}``, this repository finds out
from a red test with the tool name and the two property sets in its message, rather than
from a judge watching a demo answer the wrong question.

What is pinned, and against which constant:

======================================  ============================================
constant                                asserted equal to
======================================  ============================================
``limits.LIVE_TOOL_NAMES``              the names in ``tools/list``
``limits.MEASURED_REQUIRED_ARGUMENTS``  each tool's ``inputSchema.required``
``client.DEFAULT_DIALECT``              the property names our verbs actually send
``client.DOCUMENTED_DIALECT``           still **absent** from the surface — the
                                        superseded guess must stay wrong
======================================  ============================================

**This module never passes without a credential.** The skip is module-level and its reason
names the missing variable. A dialect suite that went green with nothing to interrogate
would be asserting that our constants agree with a server it never contacted, which is a
tautology wearing a test's clothes.

Read verbs only. ``tools/list`` is a metadata call and the one tool this module invokes
beyond it is none: no ``select_query``, no ``insert_rows``, no ``create_*``. Reading the
schema of a write verb is not calling it (ruling R4).
"""

from __future__ import annotations

import os
import re
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SRC = _REPO_ROOT / "packages" / "mainline-mcp" / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from mainline_mcp.client import (  # noqa: E402
    DEFAULT_DIALECT,
    DOCUMENTED_DIALECT,
    HttpStreamableTransport,
)
from mainline_mcp.limits import (  # noqa: E402
    LIVE_TOOL_NAMES,
    MEASURED_REQUIRED_ARGUMENTS,
    PROTOCOL_VERSION,
    READ_VERBS,
    SURFACE_MEASURED_AT,
    WRITE_VERB,
)

# ── the credential contract ──────────────────────────────────────────────────────
#
# Duplicated in all three modules in this directory rather than lifted into a
# `conftest.py`, and deliberately: each of these suites must be readable, and skippable,
# on its own terms, and the skip reason a stranger reads in the JUnit XML is the one
# written in the file whose tests were skipped.
#
# `CRDB_CLUSTER` IS NOT A CLUSTER ID. Measured 2026-08-16: this repository's `.env` sets
# `CRDB_CLUSTER=mainline-dev`, which is the cluster's *name*, and the Managed MCP Server
# answers a name in the `mcp-cluster-id` header with
#
#     HTTP 400: invalid cluster_id: must be a valid UUID, got "mainline-dev"
#
# Before this check existed, `_credentials()` returned that name and every test in this
# directory would have died in fixture setup with an HTTP 400 — a suite failing for a
# reason that has nothing to do with what it asserts. A skip that names the defect is
# worth more than a red that hides it.
_UUID = re.compile(r"\A[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\Z", re.I)


def _credentials() -> tuple[str, str] | None:
    api_key = os.environ.get("MAINLINE_MCP_API_KEY") or os.environ.get("CC_API_KEY")
    cluster = os.environ.get("MAINLINE_MCP_CLUSTER_ID") or os.environ.get("CRDB_CLUSTER")
    if api_key and cluster and _UUID.match(cluster):
        return api_key, cluster
    return None


def _skip_reason() -> str:
    api_key = os.environ.get("MAINLINE_MCP_API_KEY") or os.environ.get("CC_API_KEY")
    cluster = os.environ.get("MAINLINE_MCP_CLUSTER_ID") or os.environ.get("CRDB_CLUSTER")
    if not api_key or not cluster:
        return (
            "no Managed-MCP credential: set MAINLINE_MCP_API_KEY and MAINLINE_MCP_CLUSTER_ID "
            "(or CC_API_KEY and CRDB_CLUSTER). This suite SKIPS rather than passes, because "
            "asserting that our recorded schemas agree with a server we never contacted is a "
            "tautology, not a test."
        )
    if not _UUID.match(cluster):
        return (
            f"the cluster id is {cluster!r}, which is a cluster NAME and not a UUID. Measured "
            "2026-08-16, the Managed MCP Server answers a name in the mcp-cluster-id header "
            'with `HTTP 400: invalid cluster_id: must be a valid UUID, got "mainline-dev"`. '
            "Set MAINLINE_MCP_CLUSTER_ID to the cluster UUID; evidence/ccloud/cluster-list.txt "
            "records it for this project's cluster."
        )
    return ""


_REASON = _skip_reason()

pytestmark = [
    pytest.mark.requires_cluster,
    pytest.mark.skipif(bool(_REASON), reason=_REASON or "credential present"),
]

#: Which tools each :class:`~mainline_mcp.client.ToolDialect` field must name a real
#: property of, and which tools it must be ABSENT from. Both halves are load-bearing: the
#: absences are how ``limit`` stopped being sent to ``show_statement`` (a property that
#: does not exist there) and how the ``insert_rows`` divergence stays recorded instead of
#: quietly acquiring a shape nobody measured.
DIALECT_EXPECTATIONS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    # field         present on                                     absent from
    "statement": (
        ("select_query", "explain_query", "show_statement", "insert_rows"),
        ("list_databases", "list_tables", "get_table_schema", "show_running_queries"),
    ),
    "database": (
        ("select_query", "explain_query", "show_statement", "list_tables", "get_table_schema"),
        ("list_databases", "show_running_queries", "list_clusters"),
    ),
    "table": (
        ("get_table_schema",),
        ("insert_rows", "select_query", "explain_query"),
    ),
    "schema": (
        ("get_table_schema",),
        ("select_query", "explain_query", "insert_rows"),
    ),
    "limit": (
        ("list_databases", "list_tables"),
        ("select_query", "explain_query", "show_statement", "show_running_queries"),
    ),
    "cluster_id": (
        ("select_query", "explain_query", "show_statement", "list_databases", "list_tables"),
        ("list_clusters",),
    ),
    "rows": (
        (),
        ("insert_rows", "select_query", "explain_query", "list_tables"),
    ),
}


@pytest.fixture(scope="module")
def transport():
    credentials = _credentials()
    assert credentials is not None
    api_key, cluster_id = credentials
    connected = HttpStreamableTransport(api_key=api_key, cluster_id=cluster_id)
    yield connected
    connected.close()


@pytest.fixture(scope="module")
def handshake(transport) -> Mapping[str, Any]:
    return transport.initialize()


@pytest.fixture(scope="module")
def advertised(transport) -> dict[str, Mapping[str, Any]]:
    """Every tool the server advertises, keyed by name, with its full ``inputSchema``.

    ``transport._request`` rather than the public ``list_tool_names()`` because that
    method deliberately returns only names — the client never needed the schemas, and
    this suite is the reason anything does. If ``mainline_mcp`` ever grows a public
    ``list_tools()``, this fixture is the single call site to move.
    """
    transport.initialize()
    raw = transport._request("tools/list", {})
    entries = raw.payload.get("tools")
    assert isinstance(entries, list), f"tools/list returned {type(entries).__name__}, not a list"
    catalogue = {str(e["name"]): e for e in entries if isinstance(e, dict) and "name" in e}
    assert catalogue, "tools/list returned no named tools at all"
    return catalogue


def _schema(advertised: Mapping[str, Mapping[str, Any]], tool: str) -> Mapping[str, Any]:
    assert tool in advertised, (
        f"the server no longer advertises {tool!r}. It advertises {sorted(advertised)}."
    )
    schema = advertised[tool].get("inputSchema")
    assert isinstance(schema, dict), f"{tool} advertises no inputSchema object"
    return schema


def _properties(advertised: Mapping[str, Mapping[str, Any]], tool: str) -> frozenset[str]:
    return frozenset((_schema(advertised, tool).get("properties") or {}).keys())


def _required(advertised: Mapping[str, Mapping[str, Any]], tool: str) -> tuple[str, ...]:
    return tuple(_schema(advertised, tool).get("required") or ())


class TestTheHandshake:
    def test_the_protocol_revision_is_the_one_we_offer(self, transport):
        transport.initialize()
        assert transport.negotiated_version == PROTOCOL_VERSION, (
            f"the server negotiated {transport.negotiated_version!r}; "
            f"limits.PROTOCOL_VERSION says {PROTOCOL_VERSION!r}"
        )

    def test_the_server_identifies_itself_as_the_one_we_recorded(self, handshake):
        assert handshake.get("name") == "cockroachdb-cloud", handshake
        print(f"serverInfo: {dict(handshake)}")


class TestTheToolList:
    def test_the_advertised_names_are_exactly_the_ones_we_recorded(self, advertised):
        assert tuple(sorted(advertised)) == LIVE_TOOL_NAMES, (
            f"the tool list moved since {SURFACE_MEASURED_AT}.\n"
            f"  recorded: {list(LIVE_TOOL_NAMES)}\n"
            f"  live:     {sorted(advertised)}\n"
            "Update limits.LIVE_TOOL_NAMES with the date of the reading — and check "
            "whether the credential's blast radius moved with it."
        )

    def test_every_verb_this_client_relies_on_is_still_there(self, advertised):
        missing = sorted(set(READ_VERBS) - set(advertised))
        assert not missing, f"the Managed MCP surface no longer advertises {missing}"
        assert WRITE_VERB in advertised

    @pytest.mark.parametrize("tool", sorted(MEASURED_REQUIRED_ARGUMENTS))
    def test_the_required_arguments_are_the_ones_we_recorded(self, advertised, tool):
        recorded = MEASURED_REQUIRED_ARGUMENTS[tool]
        live = _required(advertised, tool)
        assert live == recorded, (
            f"{tool}.inputSchema.required is {list(live)}; limits.MEASURED_REQUIRED_ARGUMENTS "
            f"records {list(recorded)} as of {SURFACE_MEASURED_AT}. A required argument that "
            "appears or disappears changes what every call site must send."
        )
        print(f"{tool}: required {list(live)} · properties {sorted(_properties(advertised, tool))}")


class TestTheDialectWeSend:
    """The one that would have caught the ``statement``/``query`` defect."""

    @pytest.mark.parametrize("tool", ["select_query", "explain_query", "insert_rows"])
    def test_the_sql_argument_is_named_what_our_dialect_calls_it(self, advertised, tool):
        assert DEFAULT_DIALECT.statement in _required(advertised, tool), (
            f"{tool} requires {list(_required(advertised, tool))} and our dialect sends the "
            f"statement as {DEFAULT_DIALECT.statement!r}. THIS IS THE DEFECT OF 2026-08-16: a "
            "statement sent under a property the server does not read is not an error, it is "
            'an empty query — the server answers "must contain exactly one statement" and a '
            "negative suite reads that as a refusal. Fix ToolDialect.statement."
        )

    def test_the_superseded_guess_is_still_wrong(self, advertised):
        # DOCUMENTED_DIALECT is kept so the repository cannot quietly erase a guess it
        # published. This asserts the guess is still a guess: if `statement` ever became a
        # real property of `select_query`, that constant would stop being a record of an
        # error and start being a second, live, undocumented dialect.
        assert DOCUMENTED_DIALECT.statement != DEFAULT_DIALECT.statement
        assert DOCUMENTED_DIALECT.statement not in _properties(advertised, "select_query"), (
            "select_query now advertises a 'statement' property. The name this package "
            "shipped until 2026-08-16 has become correct again; DOCUMENTED_DIALECT and the "
            "prose around it both need rewriting rather than deleting."
        )

    @pytest.mark.parametrize("field", sorted(DIALECT_EXPECTATIONS))
    def test_each_dialect_field_is_present_where_we_send_it(self, advertised, field):
        name = getattr(DEFAULT_DIALECT, field)
        present, _absent = DIALECT_EXPECTATIONS[field]
        for tool in present:
            assert name in _properties(advertised, tool), (
                f"our dialect sends {field}={name!r} to {tool}, whose advertised properties "
                f"are {sorted(_properties(advertised, tool))}"
            )

    @pytest.mark.parametrize("field", sorted(DIALECT_EXPECTATIONS))
    def test_each_dialect_field_is_absent_where_we_recorded_it_absent(self, advertised, field):
        name = getattr(DEFAULT_DIALECT, field)
        _present, absent = DIALECT_EXPECTATIONS[field]
        for tool in absent:
            assert name not in _properties(advertised, tool), (
                f"{tool} has GAINED a {name!r} property. We record it as absent as of "
                f"{SURFACE_MEASURED_AT} and our call sites are written around that absence "
                "— check what the new property means before sending anything to it."
            )

    def test_select_query_still_paginates_inside_the_statement(self, advertised):
        # The reason `Client.select_query` has no `limit` argument to forward: there is
        # nowhere to forward it to. The row ceiling is read off the caller's own LIMIT.
        schema = _schema(advertised, "select_query")
        description = str((schema.get("properties") or {}).get("query", {}).get("description", ""))
        assert "limit" not in _properties(advertised, "select_query")
        assert "LIMIT" in description.upper(), (
            "select_query's query description no longer mentions LIMIT/OFFSET pagination: "
            f"{description!r}"
        )


class TestTheWriteVerbDivergence:
    """The divergence M1 recorded rather than closed, pinned so it cannot drift unnoticed.

    ``Client.insert_external_attestation`` sends ``{table, rows}`` and has never been sent
    to the live server. The live shape is ``{database, query}`` with a full INSERT
    statement in ``query``. Speaking that shape means composing SQL naming a table inside
    the one method whose published guarantee is that no parameter names a table — so the
    method is unchanged, the call is not made, and the difference is asserted here instead
    of being described in a comment somewhere.

    Reading ``insert_rows``'s schema is not calling it (R4).
    """

    def test_the_live_write_verb_takes_a_statement_and_not_a_table(self, advertised):
        assert _required(advertised, "insert_rows") == ("database", "query")
        properties = _properties(advertised, "insert_rows")
        assert DEFAULT_DIALECT.table not in properties
        assert DEFAULT_DIALECT.rows not in properties

    def test_the_write_verb_still_wants_a_whole_insert_statement(self, advertised):
        schema = _schema(advertised, "insert_rows")
        description = str((schema.get("properties") or {}).get("query", {}).get("description", ""))
        assert "INSERT" in description.upper(), (
            "insert_rows no longer describes its query argument as an INSERT statement: "
            f"{description!r}. If it now takes structured rows, the divergence recorded in "
            "packages/mainline-mcp/README.md has closed and the founder can be asked about "
            "the write path on its merits rather than under deadline."
        )
