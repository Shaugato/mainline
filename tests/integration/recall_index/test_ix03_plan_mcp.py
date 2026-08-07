# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""IX-03 — the same claim, over CockroachDB's own public endpoint.

*"Our vector search is real"* asserted by our test against our cluster is a claim about our
code. The same assertion driven through the Managed MCP ``explain_query`` tool is a claim
proved on **CockroachDB's** endpoint, under **its** limits, by a caller with no privileged
access to anything. That is the difference this module exists to make.

The module splits deliberately into two halves:

**The half that always runs, with no credentials.** Whether every statement the suite would
send is legal for that surface: one statement per call, ≤16 384 characters, and a response
budget with headroom rather than one measured at 100 % of the cap. These are properties of the
generated text, they are the constraints that decided the one-arm-per-call design, and they
are checkable on a laptop with no network.

**The half that needs a cluster and a service-account key.** The live call. It skips with a
loud reason when the credentials are absent, and *nothing here may be claimed on the basis of
a skipped run*. As of this commit it has not been executed against a live endpoint — the
transport below is written from the Managed MCP surface description and the MCP Streamable
HTTP transport, and the first live run is what verifies it. That is stated here rather than
discovered by a reviewer.

The client is deliberately minimal and prefers ``mainline_mcp.client`` when that package is
importable, because the MCP client belongs to the agents domain and a second maintained copy
is a second thing to keep correct.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
import uuid
from collections.abc import Callable
from dataclasses import dataclass

import pytest
from _support import (
    CUE_SCOPED,
    CUE_SWEEP,
    POPULATED_FACETS,
    CorpusState,
    env_int,
    grow_corpus,
    policy,
    unit_vector,
)
from trappoint_recall.arms import (
    MCP_MAX_RESPONSE_BYTES,
    MCP_MAX_STATEMENT_CHARS,
    MCP_SELECT_ROW_CAP,
    MCP_TIMEOUT_SECONDS,
    AncestorChain,
    ArmSet,
    SqlForm,
    SweepRequest,
    assert_arm_plan,
    check_envelope,
    explain_sql,
    generate_arms,
    index_plan_digest,
    parse_explain,
)
from trappoint_recall.arms.mcp import check_response_size

pytestmark = pytest.mark.mcp

DEFAULT_MCP_URL = "https://cockroachlabs.cloud/mcp"
MCP_CORPUS_ROWS = env_int("MAINLINE_RECALL_INDEX_PLAN_ROWS", 5000)


def _arm_set(site: uuid.UUID, tenant: uuid.UUID, levels: dict[int, uuid.UUID]) -> ArmSet:
    return generate_arms(
        site=site,
        chain=AncestorChain.of("permit-slice-1", levels),
        facet_vectors={f: unit_vector(1024, f"query/{f}") for f in POPULATED_FACETS},
        policy=policy(),
        scoped_table=CUE_SCOPED,
        sweep=SweepRequest(
            tenant=tenant, query_vector=unit_vector(256, "query/coarse"), table=CUE_SWEEP
        ),
    )


#: A synthetic arm set for the credential-free half. Uses fixed identifiers so the character
#: counts asserted below are the counts a real permit produces — UUIDs are fixed-width.
OFFLINE_ARMS = _arm_set(
    uuid.UUID("11111111-1111-4111-8111-111111111111"),
    uuid.UUID("22222222-2222-4222-8222-222222222222"),
    {
        3: uuid.UUID("33333333-3333-4333-8333-333333333333"),
        2: uuid.UUID("44444444-4444-4444-8444-444444444444"),
        1: uuid.UUID("55555555-5555-4555-8555-555555555555"),
    },
)


# ── the half that always runs ────────────────────────────────────────────────────────────


def test_ix03_every_arm_explain_is_legal_for_the_public_surface() -> None:
    worst = 0
    for arm in OFFLINE_ARMS.arms:
        statement = explain_sql(arm, form=SqlForm.EXPLAIN_MCP)
        check = check_envelope(statement.text)
        assert check.ok, f"arm {arm.arm_id}: {check.violations}"
        assert check.statements == 1
        assert check.within_margin, (
            f"arm {arm.arm_id} uses {check.utilisation:.0%} of the "
            f"{MCP_MAX_STATEMENT_CHARS}-character cap, over the working margin"
        )
        assert "ANALYZE" not in statement.text.upper(), (
            "the surface does not accept EXPLAIN ANALYZE, and the claim being proved is which "
            "plan the optimizer chose — which the non-analyzing form answers"
        )
        worst = max(worst, check.chars)
    print(f"[ix03] longest arm EXPLAIN for the public surface: {worst} chars")


def test_ix03_the_one_arm_per_call_rule_is_arithmetic_not_etiquette() -> None:
    """Why the whole arm set is never sent to this endpoint, expressed as two numbers."""
    from trappoint_recall.arms import explain_union_sql

    union = explain_union_sql(OFFLINE_ARMS, form=SqlForm.LITERAL)
    assert not check_envelope(union.text).ok
    per_arm = max(len(explain_sql(a, form=SqlForm.EXPLAIN_MCP).text) for a in OFFLINE_ARMS.arms)
    assert per_arm <= MCP_MAX_STATEMENT_CHARS
    print(
        f"[ix03] union {len(union.text)} chars vs cap {MCP_MAX_STATEMENT_CHARS}; "
        f"per-arm worst case {per_arm}"
    )


def test_ix03_a_plan_response_must_fit_the_response_cap_with_headroom() -> None:
    """Measured against the hand-written fixtures, which is the only sizing available offline.

    A plan that fits 10 KiB today with two bytes to spare will truncate tomorrow, and a
    silently truncated proof of index use is exactly the defect this product exists to refuse.
    """
    from _support import FIXTURES

    for path in sorted((FIXTURES / "plans").glob("*.txt")):
        size, fits = check_response_size(path.read_text(encoding="utf-8"))
        assert fits, f"{path.name} is {size} bytes, over the {MCP_MAX_RESPONSE_BYTES}-byte cap"
        assert size < MCP_MAX_RESPONSE_BYTES * 0.8, (
            f"{path.name} is {size} bytes — over 80 % of the response cap. A single-arm plan "
            "must stay far inside it, because the failure mode is truncation, not an error."
        )


def test_ix03_the_surface_limits_this_suite_relies_on_are_stated_in_one_place() -> None:
    limits = (
        MCP_MAX_STATEMENT_CHARS,
        MCP_MAX_RESPONSE_BYTES,
        MCP_SELECT_ROW_CAP,
        MCP_TIMEOUT_SECONDS,
    )
    assert limits == (16384, 10240, 25, 20)


# ── the live half ────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class McpCredentials:
    url: str
    token: str
    cluster_id: str
    database: str | None


def _credentials() -> McpCredentials | None:
    token = os.environ.get("MAINLINE_MCP_TOKEN") or os.environ.get("CC_MCP_TOKEN")
    cluster = os.environ.get("MAINLINE_MCP_CLUSTER_ID") or os.environ.get("CC_CLUSTER_ID")
    if not token or not cluster:
        return None
    return McpCredentials(
        url=os.environ.get("MAINLINE_MCP_URL", DEFAULT_MCP_URL),
        token=token,
        cluster_id=cluster,
        database=os.environ.get("MAINLINE_MCP_DATABASE"),
    )


def _decode(body: bytes) -> dict:
    """Accept a plain JSON body or a Server-Sent-Events frame, which is what MCP may return."""
    text = body.decode("utf-8").strip()
    if text.startswith("{"):
        return json.loads(text)
    for line in text.splitlines():
        if line.startswith("data:"):
            return json.loads(line[5:].strip())
    raise AssertionError(f"unreadable MCP response body: {text[:400]}")


class MinimalMcpClient:
    """A JSON-RPC-over-HTTP caller for one tool. Not a general MCP client.

    Written only because this suite must be able to prove its claim without waiting on another
    domain's package. If ``mainline_mcp`` is importable it is used instead — see
    :func:`_explain_over_mcp`.

    **Unverified against a live endpoint as of this commit** (no service-account key is
    available on the build machine). The first successful live run is what verifies it; until
    then this class is a design, and the test that uses it skips rather than passing.
    """

    def __init__(self, credentials: McpCredentials) -> None:
        self._credentials = credentials
        self._session: str | None = None

    def _post(self, payload: dict) -> tuple[dict | None, dict[str, str]]:
        request = urllib.request.Request(  # noqa: S310 - fixed https endpoint from env
            self._credentials.url,
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
        )
        request.add_header("Content-Type", "application/json")
        request.add_header("Accept", "application/json, text/event-stream")
        request.add_header("Authorization", f"Bearer {self._credentials.token}")
        request.add_header("mcp-cluster-id", self._credentials.cluster_id)
        if self._session:
            request.add_header("Mcp-Session-Id", self._session)
        with urllib.request.urlopen(request, timeout=MCP_TIMEOUT_SECONDS + 10) as response:  # noqa: S310
            headers = {k.lower(): v for k, v in response.headers.items()}
            body = response.read()
        if not body:
            return None, headers
        return _decode(body), headers

    def initialize(self) -> None:
        result, headers = self._post(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "mainline-recall-index-truth", "version": "0.1.0"},
                },
            }
        )
        self._session = headers.get("mcp-session-id")
        assert result is not None and "error" not in result, f"initialize failed: {result}"
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})

    def explain_query(self, statement: str) -> str:
        arguments: dict[str, object] = {"query": statement}
        if self._credentials.database:
            arguments["database"] = self._credentials.database
        result, _ = self._post(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "explain_query", "arguments": arguments},
            }
        )
        assert result is not None, "explain_query returned an empty body"
        assert "error" not in result, f"explain_query error: {result['error']}"
        content = result.get("result", {}).get("content", [])
        parts = [item.get("text", "") for item in content if item.get("type") == "text"]
        assert parts, f"explain_query returned no text content: {result}"
        return "\n".join(parts)


def _explain_over_mcp(credentials: McpCredentials) -> Callable[[str], str]:
    """Prefer the agents domain's client; fall back to the minimal one in this file."""
    try:
        from mainline_mcp.client import ManagedMcpClient  # type: ignore[import-not-found]
    except ImportError:
        client = MinimalMcpClient(credentials)
        client.initialize()
        return client.explain_query
    shared = ManagedMcpClient(
        url=credentials.url, token=credentials.token, cluster_id=credentials.cluster_id
    )
    return lambda statement: shared.explain_query(statement)


@pytest.fixture(scope="module")
def mcp_explain() -> Callable[[str], str]:
    credentials = _credentials()
    if credentials is None:
        pytest.skip(
            "no Managed MCP credentials: set MAINLINE_MCP_TOKEN and MAINLINE_MCP_CLUSTER_ID "
            "(optionally MAINLINE_MCP_URL, MAINLINE_MCP_DATABASE) to prove index use over "
            "CockroachDB's own endpoint. The claim 'proven on CockroachDB's endpoint' is NOT "
            "supported by a skipped run — only the envelope arithmetic above is."
        )
    try:
        return _explain_over_mcp(credentials)
    except (urllib.error.URLError, AssertionError) as exc:
        pytest.skip(f"Managed MCP endpoint unreachable or refused the handshake: {exc}")


def test_ix03_every_arm_is_explained_one_call_at_a_time_over_the_public_endpoint(
    mcp_explain: Callable[[str], str],
    session_conn: object,
    corpus: CorpusState,
) -> None:
    """One arm per call, the plan asserted from the endpoint's own answer.

    Note what is asserted about the response as well as about the plan: its measured byte size
    against the 10 KiB cap. A proof that arrived truncated would parse into a plan with fewer
    nodes and could pass an assertion that only looked for the words `vector search`.
    """
    grow_corpus(session_conn, corpus, target_vectors=MCP_CORPUS_ROWS)
    arms = _arm_set(corpus.taxonomy.site_id, corpus.taxonomy.tenant_id, corpus.taxonomy.levels)
    plans = []
    for arm in arms.arms:
        statement = explain_sql(arm, form=SqlForm.EXPLAIN_MCP)
        assert check_envelope(statement.text).ok
        answer = mcp_explain(statement.text)
        size, fits = check_response_size(answer)
        assert fits, (
            f"arm {arm.arm_id}: the endpoint returned {size} bytes against a "
            f"{MCP_MAX_RESPONSE_BYTES}-byte cap — the proof may be truncated, which is worse "
            "than no proof"
        )
        plan = parse_explain(answer)
        assertion = assert_arm_plan(
            plan,
            expected_index_ref=arm.table.index_ref,
            arm_id=arm.arm_id,
            expected_target_count=arm.k,
        )
        assert assertion.ok, f"{assertion.failures}\n--- plan ---\n{plan.raw}"
        plans.append(plan)
        print(f"[ix03] {arm.arm_id}: {size} bytes, {assertion.describe()}")
    digest = index_plan_digest(plans)
    print(f"[ix03] index_plan_digest over the public endpoint = {digest.hex()}")
