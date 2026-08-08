# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The Managed-MCP hard limits, expressed as constants, a scanner and typed refusals.

Every constant here is a **documented limit of CockroachDB's Managed MCP Server**
(``ARCHITECTURE.md`` §9.1, ``research/05-architecture/crdb-deep-verify.md`` §4), not a
preference of ours. The reason they are modelled as types rather than written in a
comment is narrow and specific:

    When a statement exceeds a Managed-MCP limit the server does not raise — it
    **truncates**. A truncated answer about how many precursors went undispositioned
    is indistinguishable, on the wire, from a small one. In this product a silently
    truncated aggregate is a safety defect, so the refusal has to happen on *this*
    side of the network, name the limit it broke, and carry the number that broke it.

So :func:`enforce_statement` refuses client-side and every refusal is a distinct
exception class carrying ``limit``, ``limit_value`` and ``observed``. A caller that
catches :class:`LimitRefused` can render "16 512 characters against a 16 384 limit"
without parsing a string.

Two of the limits here are **ours, not CockroachDB's**, and are marked as such:

* :data:`BUDGET_RESPONSE_BYTES` — 8 192, which is 80 % of the server's 10 240-byte
  response cap. A limit tested at 100 % breaches in front of a judge the first time
  the corpus grows; testing at 80 % means the alarm fires with 20 % of headroom left
  (decision A11, risk AR-6).
* :data:`NEVER_MCP_SCHEMAS` — ``mainline_qa``. The server would happily read it; the
  product forbids it on every tier, forever (S14, ``ARCHITECTURE.md`` §17).

**Verification status.** The limit *values* are documentation-derived and were not
re-measured against the live endpoint on this machine (no MCP service-account key is
available at build time — see ``VERIFY.md``). The *scanner* is fully tested offline.
Where the two could disagree, the client is the stricter of the two by construction:
it refuses at or below every documented threshold, never above one.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

# ── The endpoint and the documented server limits ────────────────────────────────

MCP_ENDPOINT: Final = "https://cockroachlabs.cloud/mcp"
"""The Managed MCP Server. One endpoint; the cluster is pinned by header, not by URL."""

CLUSTER_HEADER: Final = "mcp-cluster-id"
"""Pins exactly one cluster. Documented: a tool call passing a different ``cluster_id`` fails."""

MAX_STATEMENT_CHARS: Final = 16_384
"""Documented per-statement character limit."""

MAX_STATEMENTS_PER_CALL: Final = 1
"""Documented: exactly one statement per call. Not a style rule — a wire limit."""

REQUEST_TIMEOUT_SECONDS: Final = 20.0
"""Documented server-side statement timeout. The client uses it as its own deadline."""

MAX_RESPONSE_BYTES: Final = 10_240
"""Documented response cap. At or above this the answer may have been TRUNCATED."""

SELECT_DEFAULT_ROWS: Final = 25
"""``select_query`` returns 25 rows when the statement carries no explicit ``LIMIT``."""

SELECT_MAX_ROWS: Final = 10_000
"""Largest explicit ``LIMIT`` ``select_query`` accepts."""

LIST_DEFAULT_ROWS: Final = 100
"""Default page size of the list verbs (``list_databases``, ``list_tables``)."""

SHOW_MAX_ROWS: Final = 100
"""``SHOW`` output is capped at 100 rows."""

FORBIDDEN_SCHEMAS: Final = frozenset(
    {"system", "crdb_internal", "pg_catalog", "information_schema", "pg_extension"}
)
"""Schemas the Managed MCP tools cannot reach **at all**.

This is the constraint that makes ``mainline_audit`` a product surface rather than a
convenience: with no ``crdb_internal``, an auditor-facing question has nowhere to go
except a view we wrote, versioned and budgeted. The negative suite asserts these are
unreachable *over the live endpoint*, because that assertion is what proves the ops
views are the API and not a bypass.
"""

# ── Limits that are ours, not CockroachDB's ──────────────────────────────────────

NEVER_MCP_SCHEMAS: Final = frozenset({"mainline_qa"})
"""Schemas no MCP service account may ever read, on any tier (S14).

``mainline_qa`` holds per-named-person deliberation measurements. The server has no
opinion about it; we do. Enforced here client-side *and* asserted server-side by
``tests/integration/mcp/test_negative_reachability.py`` — because a control that only
exists in our client is a control an attacker skips by not using our client.
"""

AUDIT_SCHEMA: Final = "mainline_audit"
"""The only schema the auditor persona reads from."""

EXTERNAL_ATTESTATION_TABLE: Final = "mainline_meas.external_attestation"
"""The only table ``insert_rows`` may write, ever (S13).

Bound into the *signature* of the write verb rather than checked at run time: the
supported client API has no parameter that names a table, so "insert into something
else" is not a call a caller can express.
"""

BUDGET_RESPONSE_BYTES: Final = 8_192
"""OUR budget: 80 % of :data:`MAX_RESPONSE_BYTES` (A11 / AR-6)."""

BUDGET_ROWS: Final = 25
"""OUR budget, equal to the server's default page: every audit view is aggregate-first."""

READ_VERBS: Final = (
    "list_databases",
    "list_tables",
    "get_table_schema",
    "select_query",
    "explain_query",
    "show_statement",
    "show_running_queries",
)
"""The read tools this client exposes."""

WRITE_VERB: Final = "insert_rows"
"""The single permitted write tool, and it is bound to one table."""

PROTOCOL_VERSION: Final = "2025-06-18"
"""MCP protocol revision this client offers at ``initialize``.

Unverified against the managed endpoint on this machine. The client sends it, then
**adopts whatever revision the server names in its initialize result** and records it,
so a server on a different revision produces a recorded fact rather than a mismatch.
"""


# ── Refusals ─────────────────────────────────────────────────────────────────────


class McpClientError(Exception):
    """Base class for every error this package raises."""


class LimitRefused(McpClientError):
    """A call was refused **before transmission** because it would breach a known limit.

    Carries the limit's name, its value and what was observed, so an operator sees
    "statement_chars: 16512 observed against a limit of 16384" rather than a sentence.
    """

    limit: str = "unnamed"

    def __init__(self, *, limit_value: object, observed: object, detail: str) -> None:
        """Record the limit, the observed value and a human sentence."""
        self.limit_value = limit_value
        self.observed = observed
        self.detail = detail
        super().__init__(f"{self.limit}: {detail} (limit {limit_value!r}, observed {observed!r})")


class StatementTooLong(LimitRefused):
    """The statement exceeds the documented 16 384-character limit."""

    limit = "statement_chars"


class MultipleStatements(LimitRefused):
    """More than one statement in a single call, which the server does not accept."""

    limit = "statements_per_call"


class EmptyStatement(LimitRefused):
    """No statement at all. A call with nothing in it would be answered, emptily."""

    limit = "statements_per_call"


class ForbiddenSchema(LimitRefused):
    """The statement names a schema the MCP tools cannot reach."""

    limit = "forbidden_schema"


class QaSchemaRefused(LimitRefused):
    """The statement names ``mainline_qa``, which no MCP identity may read (S14)."""

    limit = "never_mcp_schema"


class ExplainAnalyzeRefused(LimitRefused):
    """``EXPLAIN ANALYZE`` is not available over MCP; only ``EXPLAIN``."""

    limit = "explain_analyze"


class RowLimitTooHigh(LimitRefused):
    """The explicit ``LIMIT`` exceeds the documented maximum for the verb."""

    limit = "row_limit"


class LimitAllRefused(LimitRefused):
    """``LIMIT ALL`` is disallowed; an unbounded read cannot fit a 10 KiB response."""

    limit = "limit_all"


class ResponseTooLarge(LimitRefused):
    """The response reached the server's cap, so it may be a truncation rather than an answer.

    Raised at ``>=`` the cap, never ``>``: a response that exactly fills the cap is
    the shape a truncated response has.
    """

    limit = "response_bytes"


class ClusterPinViolation(McpClientError):
    """A tool argument named a cluster other than the pinned one.

    The server is documented to fail this too. It is refused here as well so the
    failure is attributable to *us* attempting it, and so the assertion in the test
    suite has something to catch when no credential is present.
    """


class WriteTargetRefused(McpClientError):
    """An attempt to write somewhere other than ``mainline_meas.external_attestation``."""


class ToolCallFailed(McpClientError):
    """The server answered, and the answer was an error."""

    def __init__(self, tool: str, message: str) -> None:
        """Record which tool failed and what the server said."""
        self.tool = tool
        self.message = message
        super().__init__(f"{tool}: {message}")


class ProtocolError(McpClientError):
    """The transport answered with something that is not a well-formed MCP response."""


# ── The scanner ──────────────────────────────────────────────────────────────────

_LINE_COMMENT: Final = "--"
_BLOCK_OPEN: Final = "/*"
_BLOCK_CLOSE: Final = "*/"

_DOLLAR_TAG: Final = re.compile(r"\$[A-Za-z_][A-Za-z0-9_]*\$|\$\$")
_LIMIT_N: Final = re.compile(r"\bLIMIT\s+(\d+)\b", re.IGNORECASE)
_LIMIT_ALL: Final = re.compile(r"\bLIMIT\s+ALL\b", re.IGNORECASE)
_EXPLAIN_ANALYZE: Final = re.compile(
    r"\bEXPLAIN\b(?:\s*\([^)]*\))?\s+ANALY[SZ]E\b|\bEXPLAIN\s*\([^)]*\bANALY[SZ]E\b",
    re.IGNORECASE,
)
_QUALIFIER: Final = re.compile(r"(?<![\w.$])([A-Za-z_][A-Za-z0-9_$]*)\s*\.")
_FIRST_WORD: Final = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

# `system` is refused only when it appears as a *qualifier* (`system.jobs`), because
# "system" is an ordinary English word that can legitimately be a column name in a
# mining record. The other four names are distinctive enough that a bare mention is
# itself evidence of intent, so they are refused unqualified as well — which also
# catches `SET search_path = crdb_internal` and `SHOW TABLES FROM information_schema`.
_BARE_FORBIDDEN: Final = frozenset(
    {"crdb_internal", "pg_catalog", "information_schema", "pg_extension"}
)
_BARE_WORD: Final = re.compile(r"(?<![\w.$])([A-Za-z_][A-Za-z0-9_$]*)")


@dataclass(frozen=True, slots=True)
class ScannedStatement:
    """What the scanner learned about a statement, with literals and comments removed.

    ``code`` is the statement with every string literal, dollar-quoted body and comment
    blanked out. Every subsequent question — how many statements, which schemas, is
    there a ``LIMIT`` — is asked of ``code`` and never of ``raw``, so a semicolon inside
    ``'a;b'`` does not read as a second statement and the word ``crdb_internal`` inside
    a comment does not read as an access attempt.
    """

    raw: str
    code: str
    statement_count: int
    char_count: int
    verb: str
    explicit_limit: int | None
    has_limit_all: bool
    has_explain_analyze: bool
    qualifiers: frozenset[str]
    bare_words: frozenset[str]

    @property
    def forbidden_schemas(self) -> frozenset[str]:
        """Schemas named by this statement that the MCP tools cannot reach."""
        qualified = {q for q in self.qualifiers if q in FORBIDDEN_SCHEMAS}
        bare = {w for w in self.bare_words if w in _BARE_FORBIDDEN}
        return frozenset(qualified | bare)

    @property
    def qa_schemas(self) -> frozenset[str]:
        """``mainline_qa`` references, which are ours to refuse rather than the server's."""
        qualified = {q for q in self.qualifiers if q in NEVER_MCP_SCHEMAS}
        bare = {w for w in self.bare_words if w in NEVER_MCP_SCHEMAS}
        return frozenset(qualified | bare)


def _end_of_line_comment(sql: str, start: int) -> int:
    """Index just past a ``--`` comment (the newline itself is kept)."""
    newline = sql.find("\n", start)
    return len(sql) if newline == -1 else newline


def _end_of_block_comment(sql: str, start: int) -> int:
    """Index just past a ``/* */`` comment, honouring PostgreSQL's nesting rule."""
    depth = 1
    i = start + 2
    n = len(sql)
    while i < n and depth:
        if sql.startswith(_BLOCK_OPEN, i):
            depth += 1
            i += 2
        elif sql.startswith(_BLOCK_CLOSE, i):
            depth -= 1
            i += 2
        else:
            i += 1
    return i


def _end_of_quoted(sql: str, start: int, quote: str) -> int:
    """Index just past a quoted run, treating a doubled quote as an escape.

    Backslash is **not** an escape: CockroachDB runs with ``standard_conforming_strings``
    on, where a trailing backslash inside a literal does not extend it.
    """
    i = start + 1
    n = len(sql)
    while i < n:
        if sql[i] == quote:
            if i + 1 < n and sql[i + 1] == quote:
                i += 2
                continue
            return i + 1
        i += 1
    return n


def _end_of_dollar_quoted(sql: str, start: int) -> int | None:
    """Index just past a dollar-quoted body, or ``None`` if this ``$`` opens nothing."""
    match = _DOLLAR_TAG.match(sql, start)
    if match is None:
        return None
    tag = match.group(0)
    close = sql.find(tag, match.end())
    return len(sql) if close == -1 else close + len(tag)


def _blank_noncode(sql: str) -> str:
    r"""Return ``sql`` with comments and literal bodies replaced by spaces.

    Handles the four constructs that can contain a semicolon without ending a
    statement: ``--`` line comments, ``/* */`` block comments (nested, as PostgreSQL
    and CockroachDB both allow), single-quoted strings with ``''`` doubling, and
    dollar-quoted bodies.

    Double-quoted identifiers keep their text — a table really can be called
    ``"crdb_internal"`` and that must still be caught — but any semicolon inside one is
    blanked so it cannot be miscounted as a statement separator.
    """
    out: list[str] = []
    i = 0
    n = len(sql)
    while i < n:
        ch = sql[i]
        if sql.startswith(_LINE_COMMENT, i):
            end = _end_of_line_comment(sql, i)
        elif sql.startswith(_BLOCK_OPEN, i):
            end = _end_of_block_comment(sql, i)
        elif ch == "'":
            end = _end_of_quoted(sql, i, "'")
        elif ch == '"':
            end = _end_of_quoted(sql, i, '"')
            out.append(sql[i:end].replace(";", " ").replace('"', " "))
            i = end
            continue
        else:
            dollar_end = _end_of_dollar_quoted(sql, i) if ch == "$" else None
            if dollar_end is None:
                out.append(ch)
                i += 1
                continue
            end = dollar_end
        out.append(" " * (end - i))
        i = end
    return "".join(out)


def scan(sql: str) -> ScannedStatement:
    """Scan one candidate statement without executing or transmitting anything."""
    code = _blank_noncode(sql)
    segments = [s for s in code.split(";") if s.strip()]
    first = _FIRST_WORD.search(code)
    limits = [int(m.group(1)) for m in _LIMIT_N.finditer(code)]
    return ScannedStatement(
        raw=sql,
        code=code,
        statement_count=len(segments),
        char_count=len(sql),
        verb=first.group(0).upper() if first else "",
        explicit_limit=max(limits) if limits else None,
        has_limit_all=_LIMIT_ALL.search(code) is not None,
        has_explain_analyze=_EXPLAIN_ANALYZE.search(code) is not None,
        qualifiers=frozenset(m.group(1).lower() for m in _QUALIFIER.finditer(code)),
        bare_words=frozenset(m.group(1).lower() for m in _BARE_WORD.finditer(code)),
    )


def _enforce_shape(scanned: ScannedStatement) -> None:
    """Refuse on length and statement count — the two limits that apply to every verb."""
    if scanned.statement_count == 0:
        raise EmptyStatement(
            limit_value=MAX_STATEMENTS_PER_CALL,
            observed=0,
            detail="no statement to send; an empty call is answered emptily and proves nothing",
        )
    if scanned.statement_count > MAX_STATEMENTS_PER_CALL:
        raise MultipleStatements(
            limit_value=MAX_STATEMENTS_PER_CALL,
            observed=scanned.statement_count,
            detail="the Managed MCP Server accepts exactly one statement per call",
        )
    if scanned.char_count > MAX_STATEMENT_CHARS:
        raise StatementTooLong(
            limit_value=MAX_STATEMENT_CHARS,
            observed=scanned.char_count,
            detail="statement exceeds the documented per-call character limit",
        )


def _enforce_schemas(scanned: ScannedStatement, *, screen_schemas: bool) -> None:
    """Refuse on schema reachability, unless a probe has explicitly disabled the screen."""
    if not screen_schemas:
        return
    forbidden = sorted(scanned.forbidden_schemas)
    if forbidden:
        raise ForbiddenSchema(
            limit_value=sorted(FORBIDDEN_SCHEMAS),
            observed=forbidden,
            detail=(
                "the MCP tools cannot reach this schema; ask a mainline_audit view instead "
                "— that constraint is what makes the audit views an API rather than a bypass"
            ),
        )
    qa = sorted(scanned.qa_schemas)
    if qa:
        raise QaSchemaRefused(
            limit_value=sorted(NEVER_MCP_SCHEMAS),
            observed=qa,
            detail=(
                "mainline_qa holds per-named-person measurement and receives no MCP account "
                "on any tier, ever (S14)"
            ),
        )


def enforce_statement(
    sql: str,
    *,
    verb: str,
    max_rows: int = SELECT_MAX_ROWS,
    screen_schemas: bool = True,
) -> ScannedStatement:
    """Refuse ``sql`` client-side if it would breach a Managed-MCP limit; else return the scan.

    Args:
        sql: the single statement about to be sent.
        verb: the MCP tool it will be sent to, used only in refusal messages and to
            choose the row ceiling.
        max_rows: the largest explicit ``LIMIT`` this verb accepts.
        screen_schemas: when ``False``, the forbidden-schema screen is skipped. Set only
            by the negative-reachability probes, whose whole purpose is to make the
            *server* refuse and record that it did.

    Returns:
        The :class:`ScannedStatement`, so a caller need not scan twice.

    Raises:
        LimitRefused: one of the typed subclasses, naming the limit it broke.
    """
    scanned = scan(sql)
    _enforce_shape(scanned)
    _enforce_schemas(scanned, screen_schemas=screen_schemas)
    if scanned.has_explain_analyze:
        raise ExplainAnalyzeRefused(
            limit_value="EXPLAIN only",
            observed="EXPLAIN ANALYZE",
            detail=f"{verb} cannot run EXPLAIN ANALYZE over MCP; plan shape only",
        )
    if scanned.has_limit_all:
        raise LimitAllRefused(
            limit_value=max_rows,
            observed="ALL",
            detail=f"{verb} disallows LIMIT ALL; an unbounded read cannot fit the response cap",
        )
    if scanned.explicit_limit is not None and scanned.explicit_limit > max_rows:
        raise RowLimitTooHigh(
            limit_value=max_rows,
            observed=scanned.explicit_limit,
            detail=f"{verb} accepts an explicit LIMIT no larger than {max_rows}",
        )
    return scanned


def enforce_row_limit(requested: int, *, verb: str, maximum: int) -> int:
    """Refuse a row-count argument above ``maximum``; return it unchanged otherwise.

    Used by the list and ``SHOW`` verbs, whose ceilings (100) are lower than
    ``select_query``'s and are enforced as arguments rather than as SQL.
    """
    if requested < 1:
        raise RowLimitTooHigh(
            limit_value=maximum,
            observed=requested,
            detail=f"{verb} needs a positive row count",
        )
    if requested > maximum:
        raise RowLimitTooHigh(
            limit_value=maximum,
            observed=requested,
            detail=f"{verb} is capped at {maximum} rows by the server",
        )
    return requested


def enforce_response_size(body_bytes: int, *, tool: str) -> int:
    """Refuse a response at or above the server's cap; return the size otherwise.

    ``>=`` rather than ``>`` is deliberate. A response that exactly fills the cap is
    the shape a *truncated* response has, and a silently truncated proof is the defect
    this product exists to refuse.
    """
    if body_bytes >= MAX_RESPONSE_BYTES:
        raise ResponseTooLarge(
            limit_value=MAX_RESPONSE_BYTES,
            observed=body_bytes,
            detail=(
                f"{tool} response reached the server cap and may be truncated; "
                "ask an aggregate view instead of a wider one"
            ),
        )
    return body_bytes
