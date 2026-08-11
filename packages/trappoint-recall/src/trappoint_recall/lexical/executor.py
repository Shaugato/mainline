# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Statement construction with no database driver in sight.

This package is Apache-2.0 substrate: it holds no ``psycopg``, no ``boto3`` and no MAINLINE
vocabulary, so everything that touches a cluster does so through a **callable** the caller
supplies.  That is not purity for its own sake — it is what lets the BM25 arithmetic be
differentially tested against a pure-Python oracle on a second SQL engine, on a laptop, with
nothing installed.

Four parameter styles are supported because four consumers exist and they disagree:

``NUMERIC`` (``$1``)
    CockroachDB over the pgwire extended protocol; also what a prepared statement in a
    server-side procedure looks like.  A repeated bind reuses its placeholder.
``QMARK`` (``?``)
    ``sqlite3`` and several DB-API drivers.  Repeated binds must repeat their value.
``PYFORMAT`` (``%s``)
    ``psycopg`` 3's client-side binding.
``LITERAL``
    The Managed-MCP audit surface takes **one statement as a string** with no bind
    parameters at all.  Inlining values is therefore unavoidable there, so it is done
    behind a whitelist guard that refuses anything outside a narrow charset rather than
    behind an escaping function that hopes.

The statement text produced for two styles differs **only** in the placeholder tokens.
``tests/unit/recall_lexical/test_bm25_sql_shape.py`` asserts that by normalising every
placeholder to a sentinel and comparing bytes, which is what makes "the SQL that was
differentially tested is the SQL that ships" a checked claim rather than a hope.
"""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from decimal import Decimal
from enum import StrEnum
from typing import Final, Protocol, runtime_checkable

__all__ = [
    "MCP_MAX_SELECT_ROWS",
    "MCP_MAX_STATEMENT_CHARS",
    "Executor",
    "ParamStyle",
    "SqlBuilder",
    "Statement",
    "UnsafeLiteralError",
    "as_float",
    "as_int",
    "as_text",
    "check_identifier",
    "normalise_placeholders",
    "render_literal",
    "strip_sql_noise",
]

#: ARCHITECTURE §17: the Managed MCP server accepts one statement per call, at most this many
#: characters, and caps a SELECT at 25 rows.  Both are asserted where a statement is rendered
#: for that surface, because discovering the cap at demo time is not a plan.
MCP_MAX_STATEMENT_CHARS: Final[int] = 16384
MCP_MAX_SELECT_ROWS: Final[int] = 25


class ParamStyle(StrEnum):
    NUMERIC = "numeric"
    QMARK = "qmark"
    PYFORMAT = "pyformat"
    LITERAL = "literal"


class UnsafeLiteralError(ValueError):
    """A value was rejected for literal rendering.

    Raised rather than escaped.  Every value this module inlines is either a UUID, a float,
    an integer, or a term that :func:`trappoint_recall.lexical.analyser.is_well_formed_term`
    has already constrained to ``[a-z0-9:._/+-]``.  A value outside that set means the caller
    is passing something the analyser did not produce, and the correct response to that is to
    stop, not to quote it more carefully.
    """


#: Deliberately narrower than "what SQL can quote".  Uppercase is allowed for UUID text and
#: schema/table identifiers; everything else is the analyser's own term charset.
_SAFE_LITERAL: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9:._/+ -]{1,256}$")

#: An identifier (schema, table, column alias) interpolated into statement text.  Not a value:
#: these never come from user input, but a typo that becomes injection is still a defect.
_SAFE_IDENTIFIER: Final[re.Pattern[str]] = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")


def check_identifier(name: str, *, what: str) -> str:
    """Validate a schema or table name before it is interpolated into statement text."""
    if _SAFE_IDENTIFIER.match(name) is None:
        raise UnsafeLiteralError(f"{what} {name!r} is not a plain lowercase SQL identifier")
    return name


def render_literal(value: object) -> str:
    """Render a Python value as SQL literal text, or refuse."""
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise UnsafeLiteralError(f"non-finite float {value!r} cannot be a SQL literal")
        # `repr` round-trips float64 exactly, which matters: the literal form of this
        # statement is the one that goes on the audit surface, and a rendered score that
        # cannot be recomputed from the rendered statement is not an exhibit.
        return repr(value)
    if isinstance(value, str):
        if _SAFE_LITERAL.match(value) is None:
            raise UnsafeLiteralError(
                "refusing to inline a string outside the safe charset: " + repr(value[:64])
            )
        return "'" + value + "'"
    raise UnsafeLiteralError(f"cannot render {type(value).__name__} as a SQL literal")


#: ``--`` to end of line, ``/* … */``, and single-quoted string literals (doubled quotes
#: included).  Order matters: the string-literal alternative is last so that a quote inside a
#: comment is not read as opening a literal.
_SQL_NOISE: Final[re.Pattern[str]] = re.compile(r"--[^\n]*|/\*.*?\*/|'(?:[^']|'')*'", re.DOTALL)


def strip_sql_noise(sql: str) -> str:
    """Blank out comments and string literals so structure can be inspected."""
    return _SQL_NOISE.sub(" ", sql)


class SqlBuilder:
    """Accumulates bind values in textual order and hands back placeholder tokens."""

    __slots__ = ("_params", "_slots", "style")

    def __init__(self, style: ParamStyle = ParamStyle.NUMERIC) -> None:
        self.style = style
        self._params: list[object] = []
        self._slots: dict[str, str] = {}

    def bind(self, value: object, *, key: str | None = None) -> str:
        """Bind ``value`` and return the placeholder to write into the statement.

        ``key`` lets a value that appears more than once in the statement (``k1`` appears
        twice in the BM25 expression; a query term appears in both the ``CASE`` and the ``IN``
        list) reuse one placeholder under ``NUMERIC``, where reuse is legal.  Under ``QMARK``
        and ``PYFORMAT`` it must be repeated, so it is.
        """
        if self.style is ParamStyle.LITERAL:
            return render_literal(value)
        if key is not None and self.style is ParamStyle.NUMERIC and key in self._slots:
            return self._slots[key]
        self._params.append(value)
        token = (
            f"${len(self._params)}"
            if self.style is ParamStyle.NUMERIC
            else ("?" if self.style is ParamStyle.QMARK else "%s")
        )
        if key is not None:
            self._slots[key] = token
        return token

    @property
    def params(self) -> tuple[object, ...]:
        return tuple(self._params)


class Statement:
    """A rendered single statement and the parameters it expects, in order."""

    __slots__ = ("params", "sql", "style")

    def __init__(self, sql: str, params: Sequence[object], style: ParamStyle) -> None:
        self.sql = sql
        self.params = tuple(params)
        self.style = style

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"Statement(style={self.style.value}, params={len(self.params)})\n{self.sql}"

    def is_single_statement(self) -> bool:
        """True when the text holds exactly one statement.

        The Managed MCP surface accepts one statement per call and the gate path issues this
        query as one round trip.  A stray semicolon that turned one statement into two would
        be rejected by the server, but only after the demo had started.

        Comments and string literals are removed before looking: a semicolon inside ``--``
        commentary is not a statement separator, and treating it as one would have made this
        check fire on the very first statement it was written to protect (it did).
        """
        return ";" not in strip_sql_noise(self.sql).strip().rstrip(";")

    def fits_mcp_envelope(self) -> bool:
        return (
            self.style is ParamStyle.LITERAL
            and self.is_single_statement()
            and len(self.sql) <= MCP_MAX_STATEMENT_CHARS
        )


def as_int(value: object) -> int:
    """Coerce a driver cell to ``int``, or say exactly what came back instead.

    Drivers disagree about what a column *is*.  CockroachDB's ``count(*)`` arrives as
    ``Decimal`` through psycopg where SQLite hands back ``int``; ``INT8`` may arrive as
    ``int`` or as ``Decimal`` depending on the adapter registry the caller installed.  Every
    read in this package therefore coerces explicitly at the boundary rather than trusting
    the driver, and refuses loudly on anything unexpected — a silent ``str`` where an ``int``
    was assumed becomes a document frequency of the wrong type inside an IDF.
    """
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float | Decimal):
        return int(value)
    if isinstance(value, str):
        return int(value)
    raise TypeError(f"expected an integer cell, got {type(value).__name__}: {value!r}")


def as_float(value: object) -> float:
    """Coerce a driver cell to ``float``.  See :func:`as_int`."""
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, int | float | Decimal):
        return float(value)
    if isinstance(value, str):
        return float(value)
    raise TypeError(f"expected a numeric cell, got {type(value).__name__}: {value!r}")


def as_text(value: object) -> str:
    """Coerce a driver cell to ``str``.

    ``UUID`` is the case that matters: psycopg returns ``uuid.UUID`` objects where SQLite
    returns text, and a ``site_id`` that is a ``UUID`` on one engine and a ``str`` on the
    other silently breaks every dictionary keyed by it.
    """
    if isinstance(value, str):
        return value
    if value is None:
        raise TypeError("expected a text cell, got NULL")
    return str(value)


_PLACEHOLDER: Final[re.Pattern[str]] = re.compile(r"\$\d+|%s|\?")


def normalise_placeholders(sql: str) -> str:
    """Replace every placeholder token with ``?`` so two renderings can be compared."""
    return _PLACEHOLDER.sub("?", sql)


@runtime_checkable
class Executor(Protocol):
    """The only thing this package needs from a database.

    Returns the result rows for a query and an empty sequence for a statement that returns
    none.  Deliberately not a connection, a cursor or a session: a protocol this small can be
    satisfied by ``sqlite3``, by ``psycopg``, by a recording double, or by a function that
    posts one statement to the Managed MCP server.
    """

    def __call__(
        self, sql: str, params: Sequence[object] = (), /
    ) -> Sequence[Sequence[object]]: ...
