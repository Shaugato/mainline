# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Execute the judge pack — over the Managed MCP endpoint, or over a local SQL connection.

**The one rule this module exists to hold.** A run that had nothing to talk to reports
``NOT RUN`` and exits non-zero. It never reports success. The reason is sharper than
tidiness:

* a green *positive* run against no cluster asserts nothing;
* a green *negative* run against no cluster asserts **the opposite of what it claims** —
  "``crdb_internal`` was unreachable" is trivially true when nothing was reachable.

So :class:`RunReport` distinguishes ``answered`` / ``refused`` / ``skipped`` / ``error``
and :meth:`RunReport.exit_code` refuses to return zero when nothing ran.

**Two channels, and they do not prove the same thing.**

``--via mcp`` is the real claim: the statements go to CockroachDB's own managed endpoint
with none of our code in the path except the transport. The negatives are sent through
``probe_select_unscreened``, which deliberately turns our client-side screen off so the
*server* is the thing that refuses — a control that lives only in our client is a control
an attacker skips by not using our client.

``--via sql`` is the offline substitute: a local CockroachDB reached over pgwire. It can
check that every prompt parses, that every column exists, that the plan really shows a
vector search, and that the response would fit the budget. It **cannot** check the
negatives: over pgwire as cluster admin they succeed, so they are reported ``skipped``
with that reason rather than run and scored. The byte counts it reports are a JSON
serialisation of the rows — a proxy for the MCP response body and explicitly not the MCP
wire size.
"""

from __future__ import annotations

import importlib
import json
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

from . import envelope as env
from .drift import bind_and_measure, required_plan_substrings
from .pack import Pack, Question

DSN_VARIABLES: Final = ("TRAPPOINT_DSN", "MAINLINE_DSN", "COCKROACH_URL")
MCP_KEY_VARIABLE: Final = "MAINLINE_MCP_API_KEY"
MCP_CLUSTER_VARIABLE: Final = "MAINLINE_MCP_CLUSTER_ID"

ANSWERED: Final = "answered"
REFUSED: Final = "refused"
SKIPPED: Final = "skipped"
ERROR: Final = "error"


@dataclass(frozen=True, slots=True)
class RunResult:
    """What happened to one question on one channel."""

    qid: str
    channel: str
    outcome: str
    detail: str
    rows: int | None = None
    response_bytes: int | None = None
    possibly_truncated: bool = False
    plan_text: str = field(repr=False, default="")

    @property
    def is_expected(self) -> bool:
        return self.outcome in (ANSWERED, REFUSED)

    def render(self) -> str:
        bits = [f"{self.outcome.upper():9}", self.qid]
        if self.rows is not None:
            bits.append(f"rows={self.rows}")
        if self.response_bytes is not None:
            bits.append(f"bytes={self.response_bytes}")
        if self.possibly_truncated:
            bits.append("POSSIBLY-TRUNCATED")
        bits.append(self.detail)
        return "  ".join(bits)


@dataclass(frozen=True, slots=True)
class RunReport:
    """Every result from one run, plus whether the run was able to assert anything at all."""

    channel: str
    ran: bool
    reason: str
    results: tuple[RunResult, ...]

    def counts(self) -> dict[str, int]:
        counts = {ANSWERED: 0, REFUSED: 0, SKIPPED: 0, ERROR: 0}
        for result in self.results:
            counts[result.outcome] = counts.get(result.outcome, 0) + 1
        return counts

    def exit_code(self) -> int:
        """``0`` only when something really ran and every executed question behaved.

        ``3`` means NOT RUN, which is deliberately a different number from ``1``: an
        operator, a CI job and a judge all need to tell "we could not check" apart from
        "we checked and it is wrong", and a single non-zero code makes that impossible.
        """
        if not self.ran:
            return 3
        counts = self.counts()
        if counts[ERROR]:
            return 1
        if counts[ANSWERED] + counts[REFUSED] == 0:
            return 3
        return 0


def _dsn_from_environment() -> tuple[str | None, str]:
    for name in DSN_VARIABLES:
        value = os.environ.get(name)
        if value:
            return value, name
    return None, ", ".join(DSN_VARIABLES)


def _measure_rows(rows: Sequence[Mapping[str, Any]]) -> int:
    """Bytes of a JSON serialisation of the rows, as a proxy for the response body.

    Explicitly a proxy. The MCP wire body carries a protocol envelope this does not model,
    so the number is used to spot a view that has grown past the budget, never to claim
    the exact size of a response nobody measured.
    """
    return len(json.dumps(rows, default=str, ensure_ascii=False).encode("utf-8"))


def _truncation_verdict(question: Question, rows: int) -> tuple[bool, str]:
    scanned = env.scan(question.sql)
    limit = scanned.explicit_limit
    if limit is not None and rows >= limit:
        return True, (
            f"returned exactly the {limit}-row page, which is the shape a truncated result has; "
            "read the counts as lower bounds"
        )
    return False, "row count is under the page, so the page is the whole answer"


# ── The SQL channel ──────────────────────────────────────────────────────────────


def _psycopg() -> Any | None:
    try:
        # Imported inside the function so the validator, the renderer and the whole
        # offline path work on a machine with no database driver installed.
        import psycopg
    except ImportError:
        return None
    return psycopg


def _sql_select(cursor: Any, question: Question) -> RunResult:
    cursor.execute(question.sql.rstrip(";"))
    columns = [desc.name for desc in (cursor.description or [])]
    rows = [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]
    truncated, note = _truncation_verdict(question, len(rows))
    size = _measure_rows(rows)
    over_budget = size >= env.OUR_RESPONSE_BUDGET_BYTES
    detail = note
    if over_budget:
        detail = (
            f"{note}; the serialised rows are {size} bytes, at or over our "
            f"{env.OUR_RESPONSE_BUDGET_BYTES}-byte budget (a proxy for the MCP body, never "
            "the wire size)"
        )
    return RunResult(
        qid=question.qid,
        channel="sql",
        outcome=ERROR if over_budget else ANSWERED,
        detail=detail,
        rows=len(rows),
        response_bytes=size,
        possibly_truncated=truncated,
    )


def _sql_explain(cursor: Any, question: Question, *, repo_root: Path) -> RunResult:
    bound, _ = bind_and_measure(question, repo_root=repo_root)
    if bound is None or not bound.sql:
        return RunResult(
            qid=question.qid,
            channel="sql",
            outcome=SKIPPED,
            detail="the statement could not be bound to literals; see the drift check",
        )
    cursor.execute(bound.sql.rstrip(";"))
    plan = "\n".join(str(row[0]) for row in cursor.fetchall())
    required = required_plan_substrings(repo_root)
    missing = [s for s in required if s not in plan]
    if not required:
        return RunResult(
            qid=question.qid,
            channel="sql",
            outcome=SKIPPED,
            detail=(
                "demo/REFUSAL-STRINGS.yaml named no required plan substrings, so the plan was "
                "printed but nothing was asserted about it. This is not a pass."
            ),
            plan_text=plan,
        )
    if missing:
        return RunResult(
            qid=question.qid,
            channel="sql",
            outcome=ERROR,
            detail=f"the plan is missing {missing}; the index was not traversed as claimed",
            plan_text=plan,
        )
    return RunResult(
        qid=question.qid,
        channel="sql",
        outcome=ANSWERED,
        detail=f"plan contains {list(required)} on {bound.dimension} dimensions",
        plan_text=plan,
    )


def _sql_one(cursor: Any, question: Question, *, repo_root: Path) -> RunResult:
    if question.channel == "mcp_only":
        return RunResult(
            qid=question.qid,
            channel="sql",
            outcome=SKIPPED,
            detail=(
                "mcp_only: over a pgwire connection as cluster admin this statement SUCCEEDS. "
                "Running it here and reporting a pass would invert its meaning."
            ),
        )
    try:
        if question.verb == "explain_query":
            return _sql_explain(cursor, question, repo_root=repo_root)
        return _sql_select(cursor, question)
    except Exception as exc:  # noqa: BLE001 - the driver's exception tree is the server's
        return RunResult(
            qid=question.qid,
            channel="sql",
            outcome=ERROR,
            detail=f"{type(exc).__name__}: {exc}",
        )


def run_via_sql(pack: Pack, *, repo_root: Path, dsn: str | None = None) -> RunReport:
    """Run the pack against a CockroachDB reached over pgwire, or report why it did not."""
    driver = _psycopg()
    if driver is None:
        return RunReport(
            channel="sql",
            ran=False,
            reason=(
                "psycopg is not importable in this environment, so NOTHING was executed. "
                "`uv sync` in the workspace, or run the offline validator instead."
            ),
            results=(),
        )
    resolved = dsn or _dsn_from_environment()[0]
    if not resolved:
        return RunReport(
            channel="sql",
            ran=False,
            reason=(
                f"no DSN in the environment ({_dsn_from_environment()[1]}), so NOTHING was "
                "executed. Start a local cluster with `just corpus:up` and export TRAPPOINT_DSN."
            ),
            results=(),
        )
    for question in pack:
        env.enforce(
            question.sql,
            verb=question.verb,
            require_explicit_limit=not question.is_negative,
        )
    results: list[RunResult] = []
    with driver.connect(resolved, autocommit=True) as connection, connection.cursor() as cursor:
        for question in pack:
            results.append(_sql_one(cursor, question, repo_root=repo_root))
    return RunReport(
        channel="sql",
        ran=True,
        reason=(
            "executed over pgwire. This checks that every prompt parses, every column exists and "
            "the plan is real; it does NOT check the negatives, and its byte counts are a JSON "
            "proxy for the MCP response body rather than the MCP wire size."
        ),
        results=tuple(results),
    )


# ── The MCP channel ──────────────────────────────────────────────────────────────


def _mcp_modules() -> tuple[Any, Any] | None:
    try:
        # Optional by design, and resolved by name: the offline half of this pack must work
        # on a machine that has never installed the MCP client, so its absence is a reported
        # NOT-RUN rather than an import error at module load.
        mcp_client = importlib.import_module("mainline_mcp.client")
        mcp_limits = importlib.import_module("mainline_mcp.limits")
    except ImportError:
        return None
    return mcp_client, mcp_limits


def _mcp_positive(client: Any, question: Question, *, repo_root: Path) -> RunResult:
    if question.verb == "explain_query":
        bound, _ = bind_and_measure(question, repo_root=repo_root)
        if bound is None or not bound.sql:
            return RunResult(
                qid=question.qid,
                channel="mcp",
                outcome=SKIPPED,
                detail="the statement could not be bound to literals; see the drift check",
            )
        result = client.explain_query(bound.sql.rstrip(";"))
        required = required_plan_substrings(repo_root)
        missing = [s for s in required if s not in result.text]
        outcome = ERROR if (missing or not required) else ANSWERED
        detail = (
            f"the plan is missing {missing}"
            if missing
            else "no required plan substrings were declared, so nothing was asserted"
            if not required
            else f"plan contains {list(required)}"
        )
        return RunResult(
            qid=question.qid,
            channel="mcp",
            outcome=outcome,
            detail=detail,
            response_bytes=result.byte_count,
            plan_text=result.text,
        )
    result = client.select_query(question.sql.rstrip(";"), max_rows=env.SELECT_PAGE_ROWS)
    rows = result.row_count
    truncated = False
    note = "rows could not be parsed out of the response envelope"
    if rows is not None:
        truncated, note = _truncation_verdict(question, rows)
    return RunResult(
        qid=question.qid,
        channel="mcp",
        outcome=ERROR if result.is_error else ANSWERED,
        detail=result.text[:200] if result.is_error else note,
        rows=rows,
        response_bytes=result.byte_count,
        possibly_truncated=truncated,
    )


def _mcp_negative(client: Any, probe: Any, question: Question) -> RunResult:
    why = (
        f"{question.qid}: the client-side screen is deliberately off so the SERVER is the thing "
        "that refuses. A control that lives only in our client is not a control."
    )
    try:
        result = probe(client, question.sql.rstrip(";"), why=why)
    except Exception as exc:  # noqa: BLE001 - a transport failure is a result, not a crash
        return RunResult(
            qid=question.qid,
            channel="mcp",
            outcome=REFUSED,
            detail=f"refused before an answer came back: {type(exc).__name__}: {exc}",
        )
    if result.is_error:
        return RunResult(
            qid=question.qid,
            channel="mcp",
            outcome=REFUSED,
            detail=f"server refused: {result.text[:200]}",
            response_bytes=result.byte_count,
        )
    return RunResult(
        qid=question.qid,
        channel="mcp",
        outcome=ERROR,
        detail=(
            "THE SERVER ANSWERED. This statement must fail; that it did not is the most serious "
            "result this pack can produce."
        ),
        rows=result.row_count,
        response_bytes=result.byte_count,
    )


def run_via_mcp(pack: Pack, *, repo_root: Path) -> RunReport:
    """Run the pack over the Managed MCP endpoint, or report precisely why it did not."""
    modules = _mcp_modules()
    if modules is None:
        return RunReport(
            channel="mcp",
            ran=False,
            reason=(
                "packages/mainline-mcp is not importable in this environment, so NOTHING was "
                "sent. Any MCP client will do — this one exists to make the limits diagnosable, "
                "not to be required."
            ),
            results=(),
        )
    mcp_client, _ = modules
    api_key = os.environ.get(MCP_KEY_VARIABLE)
    cluster_id = os.environ.get(MCP_CLUSTER_VARIABLE)
    if not api_key or not cluster_id:
        return RunReport(
            channel="mcp",
            ran=False,
            reason=(
                f"{MCP_KEY_VARIABLE} and {MCP_CLUSTER_VARIABLE} are not both set, so NOTHING was "
                "sent. With no key this is a NOT-RUN, never a pass: a green negative run with "
                "nothing to talk to would assert the opposite of what it claims."
            ),
            results=(),
        )
    results: list[RunResult] = []
    client = mcp_client.Client.connect(api_key=api_key, cluster_id=cluster_id)
    try:
        for question in pack:
            if question.is_negative:
                results.append(_mcp_negative(client, mcp_client.probe_select_unscreened, question))
            else:
                results.append(_mcp_positive(client, question, repo_root=repo_root))
    finally:
        client.close()
    return RunReport(
        channel="mcp",
        ran=True,
        reason=f"executed against cluster {cluster_id} over {env.MCP_ENDPOINT}",
        results=tuple(results),
    )
