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
   (S13, §11.2). Written to be asserted against the **grant** rather than against our
   client's politeness — which is why :func:`~mainline_mcp.client.probe_insert_rows_unbound`
   exists. **This one is no longer probed over the wire**, and the reason is not caution:
   measured 2026-08-16, the probe cannot reach a grant at all. See :class:`TestWriteSurface`.
4. A tool call naming a different cluster fails. Two statements in one call fail.

Each probe deliberately bypasses our own client-side screen, because a control that lives
only in our client is a control an attacker skips by not using our client. What the probe
records is that the **server** refused.

**This module never passes without a credential.** The skip is module-level. A negative
suite that went green with nothing to talk to would be the most dangerous green in the
repository: it would assert that unreachable things are unreachable by never having tried.

── WHAT THE FIRST LIVE RUN CHANGED, 2026-08-16 ──────────────────────────────────────

This file had never executed. Running it against the live endpoint found **three ways it
could have gone green while asserting nothing**, and every one of them is now closed:

*A refusal is not a refusal until you read it.* ``_assert_server_refused`` accepted any
error at all. Measured today, three unrelated mistakes produce an error from this
endpoint: a statement sent under the wrong property name (``must contain exactly one
statement``), a query against a database that has no such relation (``relation "…" does
not exist``), and an actual security refusal (``query references a restricted schema:
access to "crdb_internal" is blocked for security reasons``). Only the third is evidence.
Every probe now names the sentence it expects, and a refusal for the wrong reason is a
failure.

*The database was never sent, and the fallback is not ours.* ``select_query`` advertises
``database`` as required but does not error without it — the statement runs against a
default database. ``SELECT count(*) FROM mainline_qa.v_disposition_profile`` with no
database therefore comes back ``relation … does not exist``, which the old helper would
have recorded as **proof that ``mainline_qa`` is unreachable**. It is nothing of the kind.
Hence :func:`control`: before any negative is believed, this suite proves it is talking to
the right database as the right identity, through the same client, in the same session.

*The write negatives could not have tested a grant.* See :class:`TestWriteSurface`.

── THE ONE THAT IS STILL RED, ON PURPOSE ────────────────────────────────────────────

``mainline_qa.v_disposition_profile`` **is** readable by the ``managed-mcp`` identity.
That was recorded as gap **N01** on 2026-08-11 and it reproduced live on 2026-08-16. The
assertion below is not relaxed and the grant is not revoked: ruling **R7** puts a grant
change on submission eve with the founder and nowhere else, and deleting the divergence to
make a suite green is the failure mode this whole file exists to refuse. It fails, loudly,
with the gap's name in its message. ``qa/mcp-live.json`` records the same fact where a
reader will find it without running anything.
"""

from __future__ import annotations

import os
import re
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

#: Measured 2026-08-16: a cluster NAME in the ``mcp-cluster-id`` header is an HTTP 400.
_UUID = re.compile(r"\A[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\Z", re.I)

DATABASE = os.environ.get("MAINLINE_MCP_DATABASE") or "mainline_demo"

#: The positive control's two questions: who am I, and can I read a schema that IS mine.
CONTROL_IDENTITY = "SELECT current_user AS u"
CONTROL_REACHABLE = "SELECT count(*) AS n FROM mainline_audit.v_open_gate_summary"


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
            "(or CC_API_KEY and CRDB_CLUSTER). This suite SKIPS rather than passes — a negative "
            "suite that goes green without ever trying asserts the opposite of what it claims."
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

#: The server's own words, quoted rather than paraphrased. Re-read live on 2026-08-16 for
#: all five schemas; identical to the 2026-08-11 transcript. ``%s`` is the schema name,
#: which the server echoes back in quotes — so a probe cannot be satisfied by a refusal
#: aimed at some *other* schema.
_RESTRICTED_SCHEMA = 'restricted schema: access to "%s" is blocked for security reasons'

#: The refusal that would prove S14. Measured 2026-08-16: it does NOT arrive — see N01.
#: ``relation … does not exist`` is deliberately NOT accepted here: a missing relation is
#: not a refused grant, and treating the two as the same is how this file could have
#: reported a security property it had never observed.
_PERMISSION_DENIED = re.compile(r"permission denied", re.IGNORECASE)


@pytest.fixture(scope="module")
def client():
    credentials = _credentials()
    assert credentials is not None
    api_key, cluster_id = credentials
    connected = Client.connect(api_key=api_key, cluster_id=cluster_id, database=DATABASE)
    yield connected
    connected.close()


@pytest.fixture(scope="module")
def control(client) -> str:
    """Prove the probes below are aimed at something before believing what they miss.

    Two facts, both measured through the same client and session the negatives use:

    * the SQL actually arrives — ``SELECT current_user`` answers ``managed-mcp``. If the
      dialect were wrong the server would answer *"must contain exactly one statement"* to
      every probe in this file, and each of them would read that as a refusal.
    * the database is the one holding our schemas — ``mainline_audit.v_open_gate_summary``
      is readable. Without this, ``mainline_qa … does not exist`` looks like S14 holding.

    Fails the run rather than skipping it. A negative suite whose aim cannot be verified
    has not been prevented from running; it has been prevented from *meaning* anything,
    and that is a red.
    """
    identity = client.select_query(CONTROL_IDENTITY)
    if identity.is_error or not identity.rows:
        pytest.fail(
            "the control query did not answer, so nothing below can be trusted: "
            f"{identity.text[:400]!r}"
        )
    who = str(identity.rows[0].get("u", ""))
    if who != "managed-mcp":
        pytest.fail(
            f"the endpoint answers as {who!r}, not 'managed-mcp'. Every negative in this file "
            "is a statement about that identity's grants and none of them applies to another."
        )
    reachable = client.select_query(CONTROL_REACHABLE)
    if reachable.is_error:
        pytest.fail(
            f"mainline_audit is not readable in database {DATABASE!r}: "
            f"{reachable.text[:400]!r}. Set MAINLINE_MCP_DATABASE. Until a schema that IS "
            "reachable can be read here, a schema that is not reachable proves nothing — an "
            "absent database and a refused grant produce the same shape of error."
        )
    print(f"control: identity {who!r}, mainline_audit readable in {DATABASE!r}")
    return who


def _assert_server_refused(action, *, what: str, because: re.Pattern[str]) -> str:
    """Run ``action``, assert the SERVER refused it, and assert it said WHY.

    ``because`` is the load-bearing argument. A helper that accepts any error accepts a
    typo, a wrong property name, a missing argument and a wrong database as evidence of a
    security boundary — and on this endpoint all four produce an error.
    """
    try:
        result = action()
    except McpClientError as exc:
        refusal = f"{type(exc).__name__}: {exc}"
    else:
        assert result.is_error, (
            f"{what} was NOT refused. The server answered: {result.text[:400]!r}. "
            "This is a reachability failure, not a test failure."
        )
        refusal = result.text
    assert because.search(refusal), (
        f"{what} was refused, but not for the reason this test claims to have proved.\n"
        f"  expected to match: /{because.pattern}/\n"
        f"  the server said:   {refusal[:400]!r}\n"
        "A refusal for the wrong reason is not evidence of the right one."
    )
    return refusal


class TestSchemasAreUnreachable:
    @pytest.mark.usefixtures("control")
    @pytest.mark.parametrize("schema", sorted(FORBIDDEN_SCHEMAS))
    def test_a_system_schema_is_unreachable(self, client, schema):
        refusal = _assert_server_refused(
            lambda: probe_select_unscreened(
                client, UNREACHABLE_STATEMENTS[schema], why=_WHY_SCHEMA
            ),
            what=f"a SELECT against {schema}",
            because=re.compile(re.escape(_RESTRICTED_SCHEMA % schema)),
        )
        print(f"{schema}: refused — {refusal[:200]}")

    @pytest.mark.usefixtures("control")
    def test_mainline_qa_is_unreachable_on_any_tier_ever(self, client):
        # GAP N01, OPEN AND STATED. Recorded 2026-08-11, reproduced live 2026-08-16: this
        # SELECT succeeds and returns a row count. GRANTS.yaml S14 and the judge pack's
        # envelope both assert it cannot. The assertion below is therefore RED, and it
        # stays red until somebody with the authority to change a grant changes one.
        #
        # DO NOT make this pass by revoking a grant (ruling R7 — a grant change under
        # deadline is the founder's call in either direction), by weakening `because` to
        # accept "does not exist", or by dropping the database so the relation vanishes.
        # All three produce a green that means the opposite of what this test claims.
        refusal = _assert_server_refused(
            lambda: probe_select_unscreened(
                client, UNREACHABLE_STATEMENTS["mainline_qa"], why=_WHY_SCHEMA
            ),
            what=(
                "a SELECT against mainline_qa.v_disposition_profile as managed-mcp — "
                "S14 says no MCP identity reads this schema on any tier, ever. THIS IS "
                "GAP N01 (evidence/deploy/judge-run.json, docs/TOOL-USAGE.md), open since "
                "2026-08-11 and reproduced live on 2026-08-16. Closing it means REVOKING a "
                "grant, which ruling R7 reserves to the founder"
            ),
            because=_PERMISSION_DENIED,
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
    """S13's grant — and why this suite no longer probes it over the live endpoint.

    The probe was written to prove the *grant*: ``managed-mcp`` may INSERT into
    ``mainline_meas.external_attestation`` and nowhere else. Measured 2026-08-16, it
    cannot prove that, because the live ``insert_rows`` takes ``{database, query}`` — a
    whole INSERT statement — and :func:`~mainline_mcp.client.probe_insert_rows_unbound`
    sends ``{table, rows}``. The server rejects those arguments on their *shape*, before
    any grant is consulted. Six green rows would have recorded "the server dislikes our
    JSON" under the heading "the write surface is bound to one table". That is precisely
    the class of false green this file was written to refuse, so the probes are skipped
    with the reason stated rather than run for a result that would be misread.

    Making them meaningful means composing INSERT statements naming forbidden tables and
    sending them to a live cluster. **Ruling R4 forbids it this week** and the ruling is
    right: the honest way to assert a grant is to read the grant, which
    ``tests/integration/steward`` and ``scripts/deploy/judge_access.py`` already do
    against ``GRANTS.yaml``. This suite's claim is narrowed to what it can still show.
    """

    _WHY_SKIPPED = (
        "R4: no live insert_rows this week. And measured 2026-08-16 the probe could not "
        "prove what it claims anyway — the live insert_rows schema is {cluster_id, database, "
        "query} with a whole INSERT statement, while probe_insert_rows_unbound sends "
        "{table, rows}, so the server refuses on argument shape and never reaches the grant. "
        "The grant itself is asserted against GRANTS.yaml, not over the wire."
    )

    @pytest.mark.parametrize("table", FORBIDDEN_WRITE_TARGETS)
    def test_insert_rows_is_rejected_outside_external_attestation(self, table):
        pytest.skip(f"{self._WHY_SKIPPED} (target: {table})")

    def test_the_only_writable_table_is_the_one_the_architecture_names(self):
        assert EXTERNAL_ATTESTATION_TABLE == "mainline_meas.external_attestation"
        assert EXTERNAL_ATTESTATION_TABLE not in FORBIDDEN_WRITE_TARGETS


class TestClusterPin:
    def test_our_client_refuses_a_different_cluster_before_transmission(self, client):
        with pytest.raises(ClusterPinViolation):
            client.call(
                "select_query",
                {
                    client.dialect.statement: "SELECT 1 AS one",
                    client.dialect.database: DATABASE,
                    client.dialect.cluster_id: "cl-definitely-not-ours",
                },
            )

    @pytest.mark.usefixtures("control")
    def test_the_server_refuses_a_different_cluster_too(self, client):
        # Bypass our own screen the only way there is — go at the transport directly —
        # so what is recorded is the SERVER's refusal of a foreign cluster_id. Every OTHER
        # argument is the one the control fixture just proved works, so the refusal is
        # attributable to the cluster_id and to nothing else.
        def foreign_cluster_call() -> ToolResult:
            raw = client.transport.call_tool(
                "select_query",
                {
                    client.dialect.statement: "SELECT 1 AS one",
                    client.dialect.database: DATABASE,
                    client.dialect.cluster_id: "cl-definitely-not-ours",
                },
            )
            return ToolResult.from_raw("select_query", raw)

        refusal = _assert_server_refused(
            foreign_cluster_call,
            what="a select_query naming a foreign cluster_id",
            because=re.compile("cluster_id"),
        )
        print(f"foreign cluster_id: refused — {refusal[:200]}")


class TestOtherRefusals:
    def test_explain_analyze_is_unavailable(self, client):
        with pytest.raises(ExplainAnalyzeRefused):
            client.explain_query("EXPLAIN ANALYZE SELECT 1")

    def test_two_statements_in_one_call_are_refused(self, client):
        with pytest.raises(MultipleStatements):
            client.select_query("SELECT 1; SELECT 2")

    @pytest.mark.usefixtures("control")
    def test_the_server_refuses_two_statements_too(self, client):
        # The server's own one-statement limit, recorded rather than assumed. It goes at
        # the transport because our scanner refuses two statements before transmission —
        # and it depends on `control` because "must contain exactly one statement" is also
        # what the server says when the statement arrives under a property it does not
        # read. Without the control, this test would pass hardest when it was most wrong.
        def two_statements() -> ToolResult:
            raw = client.transport.call_tool(
                "select_query",
                {
                    client.dialect.statement: "SELECT 1 AS a; SELECT 2 AS b",
                    client.dialect.database: DATABASE,
                },
            )
            return ToolResult.from_raw("select_query", raw)

        refusal = _assert_server_refused(
            two_statements,
            what="a select_query carrying two statements",
            because=re.compile("exactly one statement"),
        )
        print(f"two statements: refused — {refusal[:200]}")
