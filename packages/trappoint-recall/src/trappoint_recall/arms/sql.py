# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Rendering arms into SQL text — the one place literals are written.

Three renderings exist, and the difference between them is the reason this module has a long
docstring rather than a short one.

``EXECUTE``
    The hot path. The query vector is a **positional placeholder** the driver binds, so a
    1024-dimension arm costs a handful of bytes of statement text and full ``float64``
    precision. The prefix columns are still literals — always, in every rendering — because a
    prefix column that is not constrained to a specific value means the vector index is not
    used, and "not used" here means a precursor that no arm can reach.

``LITERAL``
    The same statement with the vector inlined, for endpoints with no parameter channel.
    ``EXPLAIN`` over a public HTTP tool surface is one such endpoint.

``EXPLAIN_MCP``
    ``LITERAL`` minus the projected distance expression, so the vector literal appears once
    instead of twice. This is not cosmetic. At 1024 dimensions and six decimal places a
    vector literal is about 10 500 characters; printed twice it is about 21 000, which
    **exceeds the Managed MCP 16 384-character statement cap** and would make the public
    proof-of-index-use call fail on statement length rather than on index truth. Printed once
    it fits with roughly a third of the envelope spare, and :mod:`trappoint_recall.arms.mcp`
    measures that headroom rather than assuming it.

    The elision is only legitimate because the two forms plan identically. That is asserted,
    not assumed: ``tests/integration/recall_index/test_ix02_plan_pgwire.py`` EXPLAINs both
    forms of every arm over pgwire and requires the same plan skeleton and the same
    ``index_plan_digest``. If a CockroachDB release ever makes the projection change the plan,
    that test goes red and the MCP claim is withdrawn — which is the correct outcome, and the
    reason the check exists.

**Float precision.** Literal coordinates are rendered with ``%.6f``. Six decimals is a
rendering choice for the literal forms only — ``EXECUTE`` carries full precision — and it is
recorded here because it is the kind of decision that otherwise gets discovered during an
incident: it bounds the literal at ten characters per coordinate, which is what makes the
envelope arithmetic above hold.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Final

from .binding import VectorTable
from .spec import ArmKind, ArmSet, ArmSpec, PrefixValue, SqlForm

__all__ = [
    "LITERAL_VECTOR_PRECISION",
    "UNION_COLUMNS",
    "PlaceholderStyle",
    "RenderedSql",
    "UnsafeLiteral",
    "arm_sql",
    "explain_sql",
    "explain_union_sql",
    "render_prefix_literal",
    "render_vector_literal",
    "union_all_sql",
]


class PlaceholderStyle(str, Enum):
    """How a bound parameter is spelled.

    ``NUMERIC`` (``$1``) is pgwire's own form, which ``cockroach sql`` and asyncpg speak.
    ``PYFORMAT`` (``%s``) is what psycopg's client-side binder expects. Offered as an explicit
    choice because a mismatch here does not raise: it produces a statement that either binds
    nothing or binds the wrong thing, and on a retrieval path the visible symptom is an empty
    result — a silence with no cause.
    """

    NUMERIC = "numeric"
    PYFORMAT = "pyformat"


#: Decimal places used when a vector is inlined as a literal. See the module docstring.
LITERAL_VECTOR_PRECISION: Final = 6

#: A prefix value that is not a UUID must still be safe to inline. The closed character set is
#: deliberately narrower than "escape the quotes": a facet name is a controlled vocabulary
#: token, and anything outside this set is a sign the caller is passing user text into an
#: index prefix, which is a different bug than a quoting bug.
_SAFE_TOKEN: Final = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.:\-]{0,63}$")

#: The projection every arm shares, so the branches of the ``UNION ALL`` are type-compatible.
UNION_COLUMNS: Final = (
    "cue_id",
    "arm_id",
    "arm_kind",
    "arm_level",
    "arm_facet",
    "arm_weight",
    "dist",
)


class UnsafeLiteral(ValueError):
    """A value that must not be interpolated into SQL text."""


@dataclass(frozen=True, slots=True)
class RenderedSql:
    """SQL text plus the parameters it expects, in order.

    ``params`` is empty for every literal rendering. It is non-empty only for
    :attr:`~trappoint_recall.arms.spec.SqlForm.EXECUTE`, where each entry is a vector in
    pgvector text form and the driver binds it — text form because the wire type for a vector
    parameter is the string ``[a,b,c]`` on every driver this substrate has been used with, and
    because a text parameter needs no driver-side type adapter to exist.
    """

    text: str
    params: tuple[str, ...]

    @property
    def char_count(self) -> int:
        return len(self.text)

    @property
    def byte_count(self) -> int:
        return len(self.text.encode("utf-8"))


def render_vector_literal(
    values: Sequence[float], *, precision: int = LITERAL_VECTOR_PRECISION
) -> str:
    """``[0.123456,-0.234567,…]`` — pgvector's text form, at a fixed width per coordinate."""
    return "[" + ",".join(f"{float(v):.{precision}f}" for v in values) + "]"


def render_prefix_literal(value: PrefixValue) -> str:
    """A prefix value as a SQL literal.

    UUIDs are rendered as plain quoted strings rather than ``'…'::UUID``: CockroachDB coerces
    a string literal against a UUID column at plan time, and the un-cast form is the one the
    vector-index documentation uses for prefix equality. Tokens are checked against a closed
    character set and refused otherwise — never escaped — so that no path exists by which
    caller text reaches the index prefix.
    """
    if isinstance(value, uuid.UUID):
        return f"'{value}'"
    text = str(value)
    if not _SAFE_TOKEN.match(text):
        raise UnsafeLiteral(
            f"prefix value {text!r} is outside the safe token set. Prefix values are "
            "controlled-vocabulary tokens and UUIDs; free text reaching an index prefix is a "
            "design error, not a quoting problem."
        )
    return f"'{text}'"


def _distance_expr(alias: str, table: VectorTable, vector_sql: str) -> str:
    return f"{alias}.{table.vector_column} {table.distance_operator} {vector_sql}"


def _where_clause(alias: str, arm: ArmSpec) -> str:
    return " AND ".join(
        f"{alias}.{binding.column} = {render_prefix_literal(binding.value)}"
        for binding in arm.prefix
    )


def arm_sql(
    arm: ArmSpec,
    *,
    form: SqlForm = SqlForm.EXECUTE,
    placeholder_index: int = 1,
    placeholder_style: PlaceholderStyle = PlaceholderStyle.NUMERIC,
    alias: str = "e",
) -> RenderedSql:
    """Render one arm as a parenthesised ``SELECT``.

    The parentheses are load-bearing: ``ORDER BY … LIMIT k`` must bind to the branch, not to
    the whole ``UNION ALL``. An unparenthesised branch would make ``k`` a global limit and
    throw away the per-arm structure that the graded ``k`` and the per-arm weight exist to
    create.
    """
    table = arm.table
    params: tuple[str, ...]
    if form is SqlForm.EXECUTE:
        marker = f"${placeholder_index}" if placeholder_style is PlaceholderStyle.NUMERIC else "%s"
        vector_sql = f"{marker}::VECTOR({table.dimensions})"
        # The query vector appears TWICE in the execute form — projected as `dist` and again
        # in the ORDER BY. A numbered placeholder is one parameter referenced twice; a
        # pyformat placeholder is two parameters. Getting this wrong does not raise on the
        # numbered path and raises an unhelpful arity error on the other, so the count is
        # derived here rather than left to the caller.
        literal = render_vector_literal(arm.query_vector)
        params = (literal,) if placeholder_style is PlaceholderStyle.NUMERIC else (literal, literal)
    else:
        vector_sql = f"'{render_vector_literal(arm.query_vector)}'::VECTOR({table.dimensions})"
        params = ()

    distance = _distance_expr(alias, table, vector_sql)
    facet_literal = "NULL::STRING" if arm.facet is None else render_prefix_literal(arm.facet)
    projection = [
        f"{alias}.{table.id_column} AS {UNION_COLUMNS[0]}",
        f"{render_prefix_literal(arm.arm_id)} AS {UNION_COLUMNS[1]}",
        f"{render_prefix_literal(arm.kind.value)} AS {UNION_COLUMNS[2]}",
        f"{arm.level}::INT2 AS {UNION_COLUMNS[3]}",
        f"{facet_literal} AS {UNION_COLUMNS[4]}",
        f"{arm.weight:.6f}::FLOAT8 AS {UNION_COLUMNS[5]}",
    ]
    if form is not SqlForm.EXPLAIN_MCP:
        projection.append(f"{distance} AS {UNION_COLUMNS[6]}")

    text = (
        "(SELECT "
        + ",\n        ".join(projection)
        + f"\n   FROM {table.qualified_name} AS {alias}"
        + f"\n  WHERE {_where_clause(alias, arm)}"
        + f"\n  ORDER BY {distance}"
        + f"\n  LIMIT {arm.k})"
    )
    return RenderedSql(text=text, params=params)


def union_all_sql(
    arm_set: ArmSet,
    *,
    form: SqlForm = SqlForm.EXECUTE,
    first_placeholder: int = 1,
    placeholder_style: PlaceholderStyle = PlaceholderStyle.NUMERIC,
) -> RenderedSql:
    """The whole arm set as one statement: ``SELECT * FROM ( … UNION ALL … ) AS hits``.

    Placeholder numbering runs in emission order, so ``params`` may be passed straight to the
    driver. Arm order is the generator's order (descending fusion weight), which is stable for
    a given policy and inputs — a requirement for the plan digest to be comparable run to run.
    """
    if not arm_set.arms:
        raise ValueError("an empty arm set has no SQL: there is nothing to search")
    branches: list[str] = []
    params: list[str] = []
    index = first_placeholder
    for arm in arm_set.arms:
        rendered = arm_sql(
            arm, form=form, placeholder_index=index, placeholder_style=placeholder_style
        )
        branches.append(rendered.text)
        params.extend(rendered.params)
        # One numbered placeholder per arm regardless of how often it is referenced.
        index += 1 if placeholder_style is PlaceholderStyle.NUMERIC else 0
    body = "\n  UNION ALL\n".join(branches)
    text = f"SELECT * FROM (\n{body}\n) AS hits"
    return RenderedSql(text=text, params=tuple(params))


def explain_sql(arm: ArmSpec, *, form: SqlForm = SqlForm.EXPLAIN_MCP) -> RenderedSql:
    """``EXPLAIN`` for one arm, as one statement with no parameters.

    Plain ``EXPLAIN``, never ``EXPLAIN ANALYZE``: the Managed MCP surface does not accept
    ``ANALYZE``, and the claim being proved is *which plan the optimizer chose*, which the
    non-analyzing form answers without executing anything.
    """
    if form is SqlForm.EXECUTE:
        raise ValueError(
            "EXPLAIN cannot carry a placeholder vector on an endpoint with no parameter "
            "channel; render the arm as LITERAL or EXPLAIN_MCP"
        )
    rendered = arm_sql(arm, form=form)
    return RenderedSql(text="EXPLAIN " + rendered.text, params=())


def explain_union_sql(arm_set: ArmSet, *, form: SqlForm = SqlForm.LITERAL) -> RenderedSql:
    """``EXPLAIN`` for the whole arm set — the pgwire-side assertion.

    Deliberately not offered over the Managed MCP path: a full arm set's plan exceeds the
    10 KiB response cap and would come back truncated, and *a silently truncated proof of
    index use is exactly the defect this product exists to refuse*. One arm per call over
    MCP; the whole plan over pgwire.
    """
    if form is SqlForm.EXECUTE:
        raise ValueError("EXPLAIN over the union form requires literal vectors")
    rendered = union_all_sql(arm_set, form=form)
    return RenderedSql(text="EXPLAIN " + rendered.text, params=())


def arm_kind_of(arm: ArmSpec) -> ArmKind:
    """Tiny accessor kept so callers need not import the enum to branch on it."""
    return arm.kind
