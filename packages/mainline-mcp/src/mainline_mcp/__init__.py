# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""``mainline-mcp`` — CockroachDB's Managed MCP Server, with its limits made into types.

Four things live here:

``limits``
    Every documented Managed-MCP limit as a constant, a scanner that reads a statement
    without transmitting it, and one exception class per limit. A statement that would
    breach a limit is refused **client-side**, naming the limit and the number that broke
    it, because the server truncates rather than raising and a silently truncated
    aggregate is a safety defect in this product.

``client``
    One pinned cluster, one statement per call, one writable table. The write verb has no
    parameter that names a table: ``mainline_meas.external_attestation`` is a constant
    inside the method body, so "insert somewhere else" is not a call the supported API can
    express. The tool argument names are **measured** — ``DEFAULT_DIALECT``, read from the
    live ``tools/list`` JSON Schema on ``SURFACE_MEASURED_AT`` — and the reading they
    replaced is kept, named and dated in ``DOCUMENTED_DIALECT``.

``catalogue`` / ``budget``
    The audit-surface contract, loaded and made strict, and the prober that measures each
    contracted view's **actual** bytes and rows and fails at 8 192 bytes — 80 % of the
    10 240-byte cap — so a corpus-growth breach lands in CI rather than in front of a
    judge.

``auditor``
    The nine questions a general counsel asks, each bound to exactly one contracted view,
    routed deterministically, with the completeness of every answer stated on the answer.

*The Managed MCP identity is assumed admin-equivalent and RLS is assumed not to apply.
``mainline_audit`` views are therefore designed to be safe if read in full, ``mainline_qa``
never receives an account, and we never market MCP as site-scoped.*
"""

from __future__ import annotations

from .auditor import (
    AUDITOR_QUESTIONS,
    Answer,
    AuditorPersona,
    Completeness,
    Question,
    UnroutableQuestion,
)
from .budget import Breach, BudgetProber, BudgetReport, ViewMeasurement, WorstRow
from .catalogue import (
    ARCHITECTURE_VIEWS,
    Catalogue,
    ContractError,
    ViewSpec,
    contract_path,
    load_contract,
    negative_assertions_path,
    parse_contract,
)
from .client import (
    DEFAULT_DIALECT,
    DOCUMENTED_DIALECT,
    Client,
    HttpStreamableTransport,
    RawResponse,
    ToolDialect,
    ToolResult,
    Transport,
    probe_insert_rows_unbound,
    probe_select_unscreened,
)
from .limits import (
    AUDIT_SCHEMA,
    BUDGET_RESPONSE_BYTES,
    BUDGET_ROWS,
    EXTERNAL_ATTESTATION_TABLE,
    FORBIDDEN_SCHEMAS,
    LIVE_TOOL_NAMES,
    MAX_RESPONSE_BYTES,
    MAX_STATEMENT_CHARS,
    MCP_ENDPOINT,
    MEASURED_REQUIRED_ARGUMENTS,
    NEVER_MCP_SCHEMAS,
    READ_VERBS,
    SELECT_MAX_ROWS,
    SHOW_MAX_ROWS,
    SURFACE_MEASURED_AT,
    WRITE_VERB,
    ClusterPinViolation,
    EmptyStatement,
    ExplainAnalyzeRefused,
    ForbiddenSchema,
    LimitAllRefused,
    LimitRefused,
    McpClientError,
    MultipleStatements,
    ProtocolError,
    QaSchemaRefused,
    ResponseTooLarge,
    RowLimitTooHigh,
    StatementTooLong,
    ToolCallFailed,
    WriteTargetRefused,
    enforce_response_size,
    enforce_row_limit,
    enforce_statement,
    scan,
)

__all__ = [
    "ARCHITECTURE_VIEWS",
    "AUDITOR_QUESTIONS",
    "AUDIT_SCHEMA",
    "BUDGET_RESPONSE_BYTES",
    "BUDGET_ROWS",
    "DEFAULT_DIALECT",
    "DOCUMENTED_DIALECT",
    "EXTERNAL_ATTESTATION_TABLE",
    "FORBIDDEN_SCHEMAS",
    "LIVE_TOOL_NAMES",
    "MAX_RESPONSE_BYTES",
    "MAX_STATEMENT_CHARS",
    "MCP_ENDPOINT",
    "MEASURED_REQUIRED_ARGUMENTS",
    "NEVER_MCP_SCHEMAS",
    "READ_VERBS",
    "SELECT_MAX_ROWS",
    "SHOW_MAX_ROWS",
    "SURFACE_MEASURED_AT",
    "WRITE_VERB",
    "Answer",
    "AuditorPersona",
    "Breach",
    "BudgetProber",
    "BudgetReport",
    "Catalogue",
    "Client",
    "ClusterPinViolation",
    "Completeness",
    "ContractError",
    "EmptyStatement",
    "ExplainAnalyzeRefused",
    "ForbiddenSchema",
    "HttpStreamableTransport",
    "LimitAllRefused",
    "LimitRefused",
    "McpClientError",
    "MultipleStatements",
    "ProtocolError",
    "QaSchemaRefused",
    "Question",
    "RawResponse",
    "ResponseTooLarge",
    "RowLimitTooHigh",
    "StatementTooLong",
    "ToolCallFailed",
    "ToolDialect",
    "ToolResult",
    "Transport",
    "UnroutableQuestion",
    "ViewMeasurement",
    "ViewSpec",
    "WorstRow",
    "WriteTargetRefused",
    "contract_path",
    "enforce_response_size",
    "enforce_row_limit",
    "enforce_statement",
    "load_contract",
    "negative_assertions_path",
    "parse_contract",
    "probe_insert_rows_unbound",
    "probe_select_unscreened",
    "scan",
]

__version__ = "0.1.0"
