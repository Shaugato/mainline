#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""CU-9 — the chain trigger the database runs is the body the specification specifies.

``spec/custody/chain-verification.md`` §2 carries the **normative** PL/pgSQL body of
``mainline.fn_permit_event_chain`` (adversarial-review finding **S9**; attacks **A11** and
**A13**). Custody specifies it; the kernel/datamodel leads implement it in
``verticals/mainline/db/migrations/**``. Migrations have exactly one owner, so the
specification is made executable rather than duplicated — by this check.

Four assertions, two of which need no cluster at all:

``A1`` **spec ↔ migration** (offline). The normative ``CREATE FUNCTION`` body equals the
    body in ``0105_fn_permit_event_chain.sql`` — and its ``cr_event`` mirror equals
    ``0106_fn_cr_event_chain.sql`` — modulo whitespace, comments and keyword case.
``A2`` **spec ↔ weld** (offline). The normative ``CREATE TRIGGER`` shape (timing, event,
    level, table, function) equals ``0125``/``0126``. A body nobody welded to a table is a
    body that refuses nothing.
``A3`` **spec ↔ live** (needs a cluster). ``pg_get_functiondef()`` for the live function
    equals the server's own rendering of the *specified* body — see "Why a probe" below.
``A4`` **weld ↔ live** (needs a cluster). ``pg_get_triggerdef()`` shows the trigger still
    attached, with the specified shape. Its absence is the signature of attack **A13**.

Exit codes
----------
``0``  every applicable assertion held (possibly with SKIPs, printed loudly).
``1``  an assertion failed, or ``--strict`` was given and something was skipped.

A SKIP is printed in the same column and the same voice as a FAIL. A check that quietly
reports success when it did not look is the worst artefact this repository could contain,
and this one is pointed at the single sentence an opposing expert will test hardest.

Why a probe, and not a text diff against ``pg_get_functiondef``
---------------------------------------------------------------
``chain-verification.md`` §3 specifies "collapse runs of whitespace, strip comments,
lowercase keywords" and compare. **Measured on cockroachdb/cockroach:v26.2.5 (2026-08-10),
that normalisation is not sufficient, and no purely textual one could be.**
``pg_get_functiondef`` does not return the submitted text: it re-prints the parsed tree.
The same body submitted verbatim comes back with

* comments removed and tab indentation imposed;
* ``NEW`` folded to ``new`` and ``<>`` rewritten to ``!=``;
* ``SELECT … INTO x FROM t`` rewritten as ``SELECT … FROM t AS t INTO x`` — the ``INTO``
  clause **relocated to the end**, and table aliases synthesised;
* ``WHERE a AND b`` rewritten as ``WHERE (a) AND (b)``;
* an attribute block (``VOLATILE``/``NOT LEAKPROOF``/``CALLED ON NULL INPUT``/
  ``SECURITY INVOKER``) inserted that the submitted text never contained.

A textual comparison would therefore report a difference **when the bodies are identical**,
and the only way to make it stop would be a normaliser so aggressive that a real semantic
change would slip through it — precisely what §3 forbids. So ``A3`` puts *both* sides
through the same renderer: the specified body is created under a throwaway schema, the
server is asked to render it, and the two renderings are compared. Identical bodies then
compare equal exactly, and any semantic difference survives. Measured on the same node: the
probe rendering of the §2 body is byte-identical to a same-body function in ``mainline``
apart from the schema in its header.

``A3`` therefore **creates and drops a schema** on the target cluster. That is a write, it
is stated here rather than discovered, and ``--no-probe`` turns it off (at the cost of
``A3`` reporting SKIP, because there is no sound textual substitute).

A second measurement, recorded here because it decides a reconciliation
--------------------------------------------------------------------------
On the same node, a trigger function whose body spells ``NEW.field`` is **created without
complaint and then refuses to weld**: ``CREATE TRIGGER … EXECUTE FUNCTION`` answers
``42P01 no data source matches prefix: new in this context``, hinting
``(varName).fieldName`` (https://go.crdb.dev/issue-v/114687/v26.2). The identical body
spelled ``(NEW).field`` welds. The A/B was run side by side on one table.

The body currently in §2 spells ``NEW.seq``. It is therefore not merely different from the
shipped migration — **it cannot run on this platform**, and no cluster can make ``A3`` and
``A4`` both green for it. That is a finding for the custody and kernel leads, not something
this check may paper over, and it is why the failure text names the forced direction.

Usage
-----
::

    python scripts/custody/check_chain_fn_matches_spec.py
    python scripts/custody/check_chain_fn_matches_spec.py --dsn postgresql://root@127.0.0.1:26257/defaultdb?sslmode=disable
    python scripts/custody/check_chain_fn_matches_spec.py --strict          # SKIP becomes failure
    python scripts/custody/check_chain_fn_matches_spec.py --print-renderings
    python scripts/custody/check_chain_fn_matches_spec.py --selftest

Zero third-party dependencies at import time. ``psycopg`` is imported lazily and only for
the live assertions; its absence is a SKIP with a reason, never a silent pass.
"""

from __future__ import annotations

import argparse
import difflib
import os
import re
import secrets
import sys
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NamedTuple

SPEC_RELATIVE = Path("spec/custody/chain-verification.md")
MIGRATIONS_RELATIVE = Path("verticals/mainline/db/migrations")

PASS = "PASS"  # noqa: S105 - a verdict label, not a credential
FAIL = "FAIL"
SKIP = "SKIP"

#: Read in this order, matching ``tests/integration/schema/conftest.py`` and
#: ``trappoint_conformance.cli``. One convention, four spellings, no fifth.
DSN_ENV = ("MAINLINE_TEST_DSN", "COCKROACH_URL", "CRDB_URL", "TRAPPOINT_DSN", "LOCAL_DSN")

NO_CLUSTER_REASON = (
    "no cluster: pass --dsn, or set one of "
    + "/".join(DSN_ENV)
    + ". For a local single-node node — `docker compose up -d crdb` then "
    "TRAPPOINT_DSN=postgresql://root@127.0.0.1:26257/defaultdb?sslmode=disable"
)


# ======================================================================================
# A small, dollar-quote-aware SQL scanner
# ======================================================================================


class Token(NamedTuple):
    """One lexical region of a SQL text.

    ``kind`` ∈ ``{code, comment, string, qident, dollar}``. ``inner`` is populated for
    ``dollar`` only, and holds the text between the two delimiters.
    """

    kind: str
    raw: str
    inner: str


_DOLLAR_TAG = re.compile(r"\$(?:[A-Za-z_][A-Za-z_0-9]*)?\$")
_WHITESPACE = re.compile(r"\s+")


def _end_of_line_comment(sql: str, start: int) -> int:
    end = sql.find("\n", start)
    return len(sql) if end == -1 else end


def _end_of_block_comment(sql: str, start: int) -> int:
    """Postgres block comments nest, so a depth counter is required, not a ``find``."""
    depth = 1
    cursor = start + 2
    length = len(sql)
    while cursor < length and depth > 0:
        if sql[cursor : cursor + 2] == "/*":
            depth += 1
            cursor += 2
        elif sql[cursor : cursor + 2] == "*/":
            depth -= 1
            cursor += 2
        else:
            cursor += 1
    return cursor


def _end_of_string(sql: str, start: int, *, backslash_escapes: bool) -> int:
    """*backslash_escapes* is true only for ``E'…'``.

    A plain ``'…'`` gives a backslash no special meaning, and reading one as if it did
    would swallow the closing quote of ``'\\'`` and run the scanner off the end of the
    statement.
    """
    cursor = start + 1
    length = len(sql)
    while cursor < length:
        if backslash_escapes and sql[cursor] == "\\" and cursor + 1 < length:
            cursor += 2
            continue
        if sql[cursor] == "'":
            if sql[cursor + 1 : cursor + 2] == "'":
                cursor += 2
                continue
            return cursor + 1
        cursor += 1
    return cursor


def _end_of_quoted_identifier(sql: str, start: int) -> int:
    cursor = start + 1
    length = len(sql)
    while cursor < length:
        if sql[cursor] == '"':
            if sql[cursor + 1 : cursor + 2] == '"':
                cursor += 2
                continue
            return cursor + 1
        cursor += 1
    return cursor


def tokenise(sql: str) -> list[Token]:
    """Split *sql* into literal-preserving regions.

    The distinction that matters is the one between text whose case and spacing are
    semantically free (keywords, unquoted identifiers, punctuation) and text whose case
    and spacing are load-bearing (string literals, quoted identifiers). Everything this
    module does downstream is a fold over these tokens.
    """
    tokens: list[Token] = []
    buffer: list[str] = []
    index = 0
    length = len(sql)

    def flush() -> None:
        if buffer:
            tokens.append(Token("code", "".join(buffer), ""))
            buffer.clear()

    def emit(kind: str, start: int, end: int, inner: str = "") -> None:
        flush()
        tokens.append(Token(kind, sql[start:end], inner))

    while index < length:
        character = sql[index]
        pair = sql[index : index + 2]

        if pair == "--":
            end = _end_of_line_comment(sql, index)
            emit("comment", index, end)
        elif pair == "/*":
            end = _end_of_block_comment(sql, index)
            emit("comment", index, end)
        elif character == "'":
            end = _end_of_string(sql, index, backslash_escapes=bool(buffer) and buffer[-1] in "eE")
            emit("string", index, end)
        elif character == '"':
            end = _end_of_quoted_identifier(sql, index)
            emit("qident", index, end)
        else:
            match = _DOLLAR_TAG.match(sql, index) if character == "$" else None
            close = -1 if match is None else sql.find(match.group(0), match.end())
            if match is None or close == -1:
                buffer.append(character)
                index += 1
                continue
            end = close + len(match.group(0))
            emit("dollar", index, end, sql[match.end() : close])
        index = end

    flush()
    return tokens


def normalise_sql(sql: str) -> str:
    """Return *sql* reduced to the form §3 of the specification compares on.

    Exactly four transformations, and deliberately not a fifth:

    1. comments are removed;
    2. text outside literals is lowercased — unquoted identifiers and keywords fold in
       SQL, so this cannot change meaning, while quoted identifiers and string literals
       are preserved byte-for-byte because for them it could;
    3. runs of whitespace collapse to one space;
    4. the dollar-quote delimiter is normalised to ``$$`` and its contents normalised
       recursively, because ``$$`` and ``$body$`` are the same routine.

    Not, for instance, ``(NEW).seq`` → ``NEW.seq``, which is also meaning-preserving. The
    §3 warning is the governing one: anything more aggressive lets a semantic change pass,
    and this check exists because a comment once claimed a property the schema lacked.

    Transformation 4 assumes dollar quoting delimits *routine bodies*, which is its only
    use in this repository. A dollar-quoted string used as data would be normalised as if
    it were SQL.
    """
    pieces: list[str] = []
    for token in tokenise(sql):
        if token.kind == "comment":
            pieces.append(" ")
        elif token.kind in ("string", "qident"):
            pieces.append(token.raw)
        elif token.kind == "dollar":
            pieces.append(" $$ " + normalise_sql(token.inner) + " $$ ")
        else:
            pieces.append(token.raw.lower())
    collapsed = _WHITESPACE.sub(" ", "".join(pieces)).strip()
    while collapsed.endswith(";"):
        collapsed = collapsed[:-1].strip()
    return collapsed


def strip_comments(sql: str) -> str:
    """Remove comments from *sql*, preserving every other byte.

    Unlike :func:`normalise_sql` this does not fold case or collapse whitespace, so the
    result is still submittable SQL. It exists because a statement's leading comment block
    can quote the statement — migration ``0105``'s header literally contains the words
    ``CREATE FUNCTION mainline.fn_permit_event_chain`` — and a rewrite that matched there
    would leave the real one untouched and produce a very confusing server error.
    """
    return "".join(" " if token.kind == "comment" else token.raw for token in tokenise(sql)).strip()


def split_statements(sql: str) -> list[str]:
    """Split *sql* on top-level semicolons, ignoring those inside literals and bodies."""
    statements: list[str] = []
    current: list[str] = []

    for token in tokenise(sql):
        if token.kind != "code":
            current.append(token.raw)
            continue
        start = 0
        for offset, character in enumerate(token.raw):
            if character == ";":
                current.append(token.raw[start : offset + 1])
                statements.append("".join(current))
                current = []
                start = offset + 1
        current.append(token.raw[start:])

    trailing = "".join(current)
    if trailing.strip():
        statements.append(trailing)

    return [statement.strip() for statement in statements if normalise_sql(statement)]


def find_statement(statements: list[str], prefix: str) -> str | None:
    """Return the first statement whose normalised form starts with *prefix*."""
    wanted = normalise_sql(prefix)
    for statement in statements:
        if normalise_sql(statement).startswith(wanted):
            return statement
    return None


# ======================================================================================
# The two subjects: permit_event and its cr_event mirror
# ======================================================================================


@dataclass(frozen=True)
class Variant:
    """One of the two chains the specification governs.

    §2 of ``chain-verification.md`` states the ``permit_event`` body and then says
    ``cr_event`` "mirrors this exactly … substituting ``cr_id`` for ``permit_id``". The
    mirror is therefore *derived* here rather than transcribed: a transcription is a second
    thing to keep in step, and the point of this file is that nothing drifts silently.
    """

    label: str
    schema: str
    function: str
    trigger: str
    table: str
    function_migration: str
    trigger_migration: str


PERMIT = Variant(
    label="permit",
    schema="mainline",
    function="fn_permit_event_chain",
    trigger="permit_event_chain",
    table="permit_event",
    function_migration="0105_fn_permit_event_chain.sql",
    trigger_migration="0125_trg_permit_event_chain.sql",
)

CHANGE_REQUEST = Variant(
    label="cr",
    schema="mainline",
    function="fn_cr_event_chain",
    trigger="cr_event_chain",
    table="cr_event",
    function_migration="0106_fn_cr_event_chain.sql",
    trigger_migration="0126_trg_cr_event_chain.sql",
)

VARIANTS = (PERMIT, CHANGE_REQUEST)

#: Longest-first, because ``fn_permit_event_chain`` contains ``permit_event`` which
#: contains ``permit``. A shorter-first pass would corrupt the longer names.
_MIRROR = (
    ("fn_permit_event_chain", "fn_cr_event_chain"),
    ("permit_event_chain", "cr_event_chain"),
    ("permit_event", "cr_event"),
    ("permit_id", "cr_id"),
)

_MIRROR_PATTERN = re.compile("|".join(re.escape(source) for source, _ in _MIRROR))
_MIRROR_MAP = dict(_MIRROR)


def mirror_to_change_request(sql: str) -> str:
    """Rewrite the ``permit_event`` statement into its ``cr_event`` mirror (§2)."""
    return _MIRROR_PATTERN.sub(lambda match: _MIRROR_MAP[match.group(0)], sql)


# ======================================================================================
# Reading the normative body out of the specification
# ======================================================================================


_FENCE = re.compile(r"^```sql[ \t]*\n(.*?)^```", re.MULTILINE | re.DOTALL)


class SpecificationError(RuntimeError):
    """The normative document does not have the shape this check is specified against."""


@dataclass(frozen=True)
class Normative:
    """The two statements §2 of the specification fences."""

    create_function: str
    create_trigger: str


def extract_normative(markdown: str) -> Normative:
    """Pull §2's fenced ``sql`` block apart into its function and its trigger.

    Raises rather than returning a partial result. A check that silently compares against
    half a specification is worse than one that is not run, because it reports PASS.
    """
    blocks = [
        block
        for block in _FENCE.findall(markdown)
        if "create function" in block.lower() and PERMIT.function in block
    ]
    if len(blocks) != 1:
        raise SpecificationError(
            f"expected exactly one fenced `sql` block defining {PERMIT.schema}.{PERMIT.function}"
            f" in {SPEC_RELATIVE.as_posix()}, found {len(blocks)}"
        )

    statements = split_statements(blocks[0])
    create_function = find_statement(
        statements, f"CREATE FUNCTION {PERMIT.schema}.{PERMIT.function}("
    )
    create_trigger = find_statement(statements, f"CREATE TRIGGER {PERMIT.trigger} ")
    if create_function is None:
        raise SpecificationError(
            f"{SPEC_RELATIVE.as_posix()} §2 has no `CREATE FUNCTION "
            f"{PERMIT.schema}.{PERMIT.function}(`"
        )
    if create_trigger is None:
        raise SpecificationError(
            f"{SPEC_RELATIVE.as_posix()} §2 has no `CREATE TRIGGER {PERMIT.trigger}`"
        )
    return Normative(create_function=create_function, create_trigger=create_trigger)


def normative_for(spec: Normative, variant: Variant) -> Normative:
    """The normative pair for *variant*, mirrored from the ``permit`` original if needed."""
    if variant is PERMIT:
        return spec
    return Normative(
        create_function=mirror_to_change_request(spec.create_function),
        create_trigger=mirror_to_change_request(spec.create_trigger),
    )


# ======================================================================================
# Trigger shape — compared structurally, because renderings differ by qualification
# ======================================================================================


@dataclass(frozen=True)
class TriggerShape:
    """What a ``CREATE TRIGGER`` says, stripped of how it was spelled.

    ``pg_get_triggerdef()`` on CockroachDB v26.2.5 returns names qualified with the
    *database* (``defaultdb.mainline.permit_event``) and no trailing semicolon, while the
    migration writes two-part names. Comparing the strings would report a difference that
    is purely a rendering convention; comparing these five fields reports only real ones.
    """

    name: str
    timing: str
    events: tuple[str, ...]
    level: str
    table: str
    function: str


_TRIGGER_NAME = re.compile(r"\bcreate\s+trigger\s+([a-z0-9_.\"]+)")
_TRIGGER_TIMING = re.compile(r"\b(before|after|instead\s+of)\b")
_TRIGGER_EVENTS = re.compile(r"\b(insert|update|delete|truncate)\b")
_TRIGGER_TABLE = re.compile(r"\bon\s+([a-z0-9_.\"]+)")
_TRIGGER_LEVEL = re.compile(r"\bfor\s+each\s+(row|statement)\b")
_TRIGGER_FUNCTION = re.compile(r"\bexecute\s+(?:function|procedure)\s+([a-z0-9_.\"]+)\s*\(")


def _tail(qualified: str, keep: int = 2) -> str:
    """Drop leading qualification, keeping the last *keep* dotted components."""
    return ".".join(qualified.split(".")[-keep:])


def parse_trigger(sql: str) -> TriggerShape:
    """Parse a ``CREATE TRIGGER`` statement — ours or the server's rendering of it."""
    text = normalise_sql(sql)
    name = _TRIGGER_NAME.search(text)
    timing = _TRIGGER_TIMING.search(text)
    table = _TRIGGER_TABLE.search(text)
    level = _TRIGGER_LEVEL.search(text)
    function = _TRIGGER_FUNCTION.search(text)
    if not (name and timing and table and level and function):
        raise SpecificationError(f"not a parseable CREATE TRIGGER statement: {text[:160]}")

    between = text[timing.end() : table.start()]
    events = tuple(sorted({match.group(1) for match in _TRIGGER_EVENTS.finditer(between)}))
    if not events:
        raise SpecificationError(f"CREATE TRIGGER names no event: {text[:160]}")

    return TriggerShape(
        name=_tail(name.group(1), keep=1),
        timing=_WHITESPACE.sub(" ", timing.group(1)),
        events=events,
        level=level.group(1),
        table=_tail(table.group(1)),
        function=_tail(function.group(1)),
    )


# ======================================================================================
# Diffing
# ======================================================================================


def _wrap(text: str) -> list[str]:
    return textwrap.wrap(text, width=88) or [""]


def unified(expected: str, actual: str, *, expected_label: str, actual_label: str) -> str:
    """A readable unified diff of two normalised single-line SQL strings."""
    return "\n".join(
        difflib.unified_diff(
            _wrap(expected),
            _wrap(actual),
            fromfile=expected_label,
            tofile=actual_label,
            lineterm="",
        )
    )


# ======================================================================================
# The live cluster
# ======================================================================================


class ClusterUnavailable(RuntimeError):
    """No cluster could be reached, or the driver is absent. Always a SKIP, never a PASS."""


class LiveCluster:
    """The three catalogue reads and the one probe this check needs.

    Every statement is issued on an autocommit connection. The probe is the only write,
    it is confined to a schema whose name is generated per run, and it is dropped in a
    ``finally``.
    """

    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def _one(self, statement: str, parameters: tuple[Any, ...] = ()) -> Any:
        with self._connection.cursor() as cursor:
            cursor.execute(statement, parameters)
            row = cursor.fetchone()
        return None if row is None else row[0]

    def _one_text(self, statement: str, parameters: tuple[Any, ...] = ()) -> str | None:
        """A catalogue read whose single column is text.

        The driver's row type is untyped at this boundary, so the narrowing happens here,
        once, rather than as an ``Any`` leaking into every caller's return type.
        """
        value = self._one(statement, parameters)
        return None if value is None else str(value)

    def table_exists(self, schema: str, table: str) -> bool:
        return bool(
            self._one(
                """
                SELECT count(*) FROM pg_catalog.pg_class c
                JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = %s AND c.relname = %s AND c.relkind = 'r'
                """,
                (schema, table),
            )
        )

    def function_definition(self, schema: str, name: str) -> str | None:
        return self._one_text(
            """
            SELECT pg_get_functiondef(p.oid) FROM pg_catalog.pg_proc p
            JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
            WHERE n.nspname = %s AND p.proname = %s
            """,
            (schema, name),
        )

    def trigger_definition(self, schema: str, table: str, trigger: str) -> str | None:
        return self._one_text(
            """
            SELECT pg_get_triggerdef(t.oid) FROM pg_catalog.pg_trigger t
            JOIN pg_catalog.pg_class c ON c.oid = t.tgrelid
            JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
            WHERE NOT t.tgisinternal AND n.nspname = %s AND c.relname = %s AND t.tgname = %s
            """,
            (schema, table, trigger),
        )

    def render(self, create_function: str, variant: Variant) -> str:
        """Ask the server to render the *specified* body, so both sides share a renderer.

        Returns the rendering with the throwaway schema rewritten back to *variant*'s, so
        the only remaining difference from the live rendering would be a real one.
        """
        probe_schema = f"trappoint_chainspec_probe_{secrets.token_hex(4)}"
        # Anchored, and over comment-stripped text: the statement's own header comment
        # quotes the CREATE FUNCTION line, and an unanchored rewrite would hit that copy.
        pattern = re.compile(
            r"\A(create\s+function\s+)" + re.escape(f"{variant.schema}.{variant.function}"),
            re.IGNORECASE,
        )
        probe_sql, substitutions = pattern.subn(
            lambda match: match.group(1) + f"{probe_schema}.{variant.function}",
            strip_comments(create_function),
            1,
        )
        if substitutions != 1:
            raise SpecificationError(
                "the normative statement does not begin "
                f"`CREATE FUNCTION {variant.schema}.{variant.function}`"
            )

        try:
            with self._connection.cursor() as cursor:
                # The schema name is generated here from `secrets`, never from input.
                cursor.execute(f"CREATE SCHEMA {probe_schema}")
                cursor.execute(probe_sql)
                cursor.execute(
                    """
                    SELECT pg_get_functiondef(p.oid) FROM pg_catalog.pg_proc p
                    JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
                    WHERE n.nspname = %s AND p.proname = %s
                    """,
                    (probe_schema, variant.function),
                )
                row = cursor.fetchone()
        finally:
            self._drop_probe(probe_schema)

        if row is None:
            raise SpecificationError("the probe function was created but cannot be read back")
        rendered: str = row[0]
        return rendered.replace(f"{probe_schema}.", f"{variant.schema}.")

    def _drop_probe(self, probe_schema: str) -> None:
        """Remove the throwaway schema, on a fresh cursor, and shout if it survives.

        A fresh cursor because the failure this runs after may have left the previous one
        unusable, and a check that litters someone else's cluster with orphan schemas is a
        check they will disable. If the drop itself fails the name is printed: a leftover
        nobody was told about is worse than the leftover.
        """
        try:
            with self._connection.cursor() as cursor:
                cursor.execute(f"DROP SCHEMA IF EXISTS {probe_schema} CASCADE")
        except Exception as exc:  # noqa: BLE001 - reported, never swallowed
            print(
                f"{FAIL}  the probe schema {probe_schema} could NOT be dropped "
                f"({type(exc).__name__}: {str(exc).strip()[:160]}). Drop it by hand.",
                file=sys.stderr,
            )


def resolve_dsn(explicit: str | None) -> str | None:
    if explicit:
        return explicit
    for name in DSN_ENV:
        value = os.environ.get(name)
        if value:
            return value
    return None


def connect(dsn: str) -> Any:
    """Open an autocommit connection, or raise :class:`ClusterUnavailable`."""
    try:
        import psycopg
    except ImportError as exc:  # pragma: no cover - exercised only in the floor lane
        raise ClusterUnavailable(f"psycopg is not installed ({exc})") from exc
    try:
        return psycopg.connect(
            dsn, autocommit=True, connect_timeout=10, application_name="check-chain-fn"
        )
    except psycopg.Error as exc:
        raise ClusterUnavailable(f"cannot connect: {str(exc).strip()}") from exc


# ======================================================================================
# The report
# ======================================================================================


class Report:
    def __init__(self) -> None:
        self.lines: list[tuple[str, str]] = []
        self.details: list[str] = []
        self.failed = 0
        self.skipped = 0
        self.passed = 0

    def record(self, verdict: str, message: str, detail: str = "") -> None:
        self.lines.append((verdict, message))
        if verdict == FAIL:
            self.failed += 1
        elif verdict == SKIP:
            self.skipped += 1
        else:
            self.passed += 1
        if detail:
            self.details.append(f"── {message}\n{detail}")

    def emit(self) -> None:
        for verdict, message in self.lines:
            print(f"{verdict:<4}  {message}")
        for detail in self.details:
            print()
            print(detail)


RECONCILE = (
    "Reconcile deliberately, in one commit, with an ADR. MEASURED CONSTRAINT, "
    "cockroachdb/cockroach:v26.2.5 on 2026-08-10: a trigger function whose body spells "
    "`NEW.field` is CREATEd without complaint and then refuses to WELD — "
    "`CREATE TRIGGER … EXECUTE FUNCTION` answers 42P01 `no data source matches prefix: "
    "new in this context`, hinting `(varName).fieldName` "
    "(https://go.crdb.dev/issue-v/114687/v26.2). The same body spelled `(NEW).field` "
    "welds. So if the difference is that spelling, the direction is forced: "
    "`spec/custody/chain-verification.md` §2 must be restated to the shipped body "
    "(owner: custody · custody-spec-and-red) — the current §2 body cannot run on this "
    "platform at all. For any other difference the choice is open, and the migration "
    "side is re-rendered from `packages/trappoint-sql/templates/0105_fn_event_chain.sql.j2` "
    "(owner: kernel · projection-triggers). Do NOT relax this check: a normative body "
    "the database does not run is the exhibit finding S9 exists to prevent."
)


# ======================================================================================
# The assertions
# ======================================================================================


def check_offline(root: Path, spec: Normative, report: Report) -> None:
    """A1 and A2 — no cluster, no credential, no network."""
    migrations = root / MIGRATIONS_RELATIVE

    for variant in VARIANTS:
        wanted = normative_for(spec, variant)
        qualified = f"{variant.schema}.{variant.function}"

        # ── A1: the body ────────────────────────────────────────────────────────────
        function_path = migrations / variant.function_migration
        if not function_path.is_file():
            report.record(
                SKIP,
                f"A1 {qualified}: {variant.function_migration} has not landed — NOT CHECKED",
            )
        else:
            shipped = find_statement(
                split_statements(function_path.read_text(encoding="utf-8")),
                f"CREATE FUNCTION {qualified}(",
            )
            if shipped is None:
                report.record(
                    FAIL,
                    f"A1 {qualified}: {variant.function_migration} contains no "
                    f"`CREATE FUNCTION {qualified}(`",
                )
            else:
                expected = normalise_sql(wanted.create_function)
                actual = normalise_sql(shipped)
                if expected == actual:
                    report.record(
                        PASS, f"A1 {qualified}: {variant.function_migration} matches the spec body"
                    )
                else:
                    report.record(
                        FAIL,
                        f"A1 {qualified}: {variant.function_migration} has DRIFTED from "
                        f"{SPEC_RELATIVE.as_posix()} §2",
                        unified(
                            expected,
                            actual,
                            expected_label=f"{SPEC_RELATIVE.as_posix()} §2 (normative)",
                            actual_label=f"{MIGRATIONS_RELATIVE.as_posix()}/{variant.function_migration}",
                        )
                        + "\n\n"
                        + textwrap.fill(RECONCILE, width=92),
                    )

        # ── A2: the weld ────────────────────────────────────────────────────────────
        trigger_path = migrations / variant.trigger_migration
        if not trigger_path.is_file():
            report.record(
                SKIP,
                f"A2 {variant.trigger}: {variant.trigger_migration} has not landed — NOT CHECKED",
            )
            continue
        welded = find_statement(
            split_statements(trigger_path.read_text(encoding="utf-8")),
            f"CREATE TRIGGER {variant.trigger} ",
        )
        if welded is None:
            report.record(
                FAIL,
                f"A2 {variant.trigger}: {variant.trigger_migration} contains no "
                f"`CREATE TRIGGER {variant.trigger}` — an unwelded body refuses nothing",
            )
            continue
        expected_shape = parse_trigger(wanted.create_trigger)
        actual_shape = parse_trigger(welded)
        if expected_shape == actual_shape:
            report.record(
                PASS,
                f"A2 {variant.trigger}: welded {actual_shape.timing} "
                f"{'/'.join(actual_shape.events)} for each {actual_shape.level} on "
                f"{actual_shape.table}",
            )
        else:
            report.record(
                FAIL,
                f"A2 {variant.trigger}: the weld in {variant.trigger_migration} is not the "
                f"specified one",
                f"  spec:    {expected_shape}\n  shipped: {actual_shape}",
            )


def check_live_body(
    cluster: LiveCluster, wanted: Normative, variant: Variant, report: Report, *, probe: bool
) -> None:
    """A3 — is the body the database is running the body §2 specifies?"""
    qualified = f"{variant.schema}.{variant.function}"
    live_function = cluster.function_definition(variant.schema, variant.function)

    if live_function is None:
        report.record(
            FAIL,
            f"A3 {qualified}: {variant.schema}.{variant.table} exists but the chain "
            "function DOES NOT. The chain is unverified on this cluster right now "
            "(attack A11 is unrefused).",
        )
        return
    if not probe:
        report.record(
            SKIP,
            f"A3 {qualified}: --no-probe was given. pg_get_functiondef re-prints the "
            "parsed tree, so there is no sound textual comparison against the spec "
            "source; the probe is the comparison. NOT CHECKED",
        )
        return

    try:
        rendered_spec = cluster.render(wanted.create_function, variant)
    except SpecificationError as exc:
        report.record(FAIL, f"A3 {qualified}: the normative body is malformed — {exc}")
        return
    except Exception as exc:  # noqa: BLE001 - the driver's error IS the skip reason
        report.record(
            SKIP,
            f"A3 {qualified}: the server refused the probe schema "
            f"({type(exc).__name__}: {str(exc).strip()[:200]}). A read-only role "
            "cannot run this assertion. NOT CHECKED",
        )
        return

    expected = normalise_sql(rendered_spec)
    actual = normalise_sql(live_function)
    if expected == actual:
        report.record(
            PASS,
            f"A3 {qualified}: the live body is the specified body (both via pg_get_functiondef)",
        )
        return
    report.record(
        FAIL,
        f"A3 {qualified}: the LIVE body differs from {SPEC_RELATIVE.as_posix()} §2",
        unified(
            expected,
            actual,
            expected_label="spec body, rendered by this server",
            actual_label=f"live pg_get_functiondef({qualified})",
        )
        + "\n\n"
        + textwrap.fill(RECONCILE, width=92),
    )


def check_live_weld(
    cluster: LiveCluster, wanted: Normative, variant: Variant, report: Report
) -> None:
    """A4 — is the body still welded to the table, with the specified shape?"""
    live_trigger = cluster.trigger_definition(variant.schema, variant.table, variant.trigger)
    if live_trigger is None:
        report.record(
            FAIL,
            f"A4 {variant.trigger}: NO SUCH TRIGGER on {variant.schema}.{variant.table}. "
            "Either it was never applied or it was dropped — the signature of attack "
            "A13. Every insert on this table is currently unverified.",
        )
        return

    expected_shape = parse_trigger(wanted.create_trigger)
    try:
        actual_shape = parse_trigger(live_trigger)
    except SpecificationError as exc:
        report.record(FAIL, f"A4 {variant.trigger}: unparseable pg_get_triggerdef — {exc}")
        return

    if expected_shape == actual_shape:
        report.record(
            PASS,
            f"A4 {variant.trigger}: live weld is {actual_shape.timing} "
            f"{'/'.join(actual_shape.events)} for each {actual_shape.level} on "
            f"{actual_shape.table} → {actual_shape.function}",
        )
        return
    report.record(
        FAIL,
        f"A4 {variant.trigger}: the live weld is not the specified one",
        f"  spec: {expected_shape}\n  live: {actual_shape}",
    )


def check_live(cluster: LiveCluster, spec: Normative, report: Report, *, probe: bool) -> None:
    """A3 and A4 — what the database is actually running, right now."""
    for variant in VARIANTS:
        wanted = normative_for(spec, variant)
        if not cluster.table_exists(variant.schema, variant.table):
            report.record(
                SKIP,
                f"A3/A4 {variant.schema}.{variant.function}: {variant.schema}.{variant.table} "
                "does not exist on this cluster — the migrations have not been applied. "
                "NOT CHECKED",
            )
            continue
        check_live_body(cluster, wanted, variant, report, probe=probe)
        check_live_weld(cluster, wanted, variant, report)


def print_renderings(cluster: LiveCluster, spec: Normative) -> None:
    """Print both renderings verbatim, so a reconciliation is a copy rather than a retype."""
    for variant in VARIANTS:
        wanted = normative_for(spec, variant)
        qualified = f"{variant.schema}.{variant.function}"
        print(f"\n════ {qualified} — spec body as this server renders it ════")
        try:
            print(cluster.render(wanted.create_function, variant))
        except Exception as exc:  # noqa: BLE001 - this is a diagnostic printer
            print(f"(unavailable: {type(exc).__name__}: {str(exc).strip()[:200]})")
        print(f"\n════ {qualified} — live pg_get_functiondef ════")
        print(cluster.function_definition(variant.schema, variant.function) or "(absent)")


# ======================================================================================
# Self-test
# ======================================================================================


_SELFTEST_SPEC = """\
# fn_permit_event_chain — the normative body

```sql
prev_digest BYTES NOT NULL,
```

## 2. The normative body

```sql
-- a comment the migration need not carry
CREATE FUNCTION mainline.fn_permit_event_chain() RETURNS TRIGGER LANGUAGE PLpgSQL AS $$
DECLARE expected BYTES;
BEGIN
  IF NEW.seq = 0 THEN RETURN NEW; END IF;
  SELECT chain_digest INTO expected FROM mainline.permit_event
   WHERE permit_id = NEW.permit_id AND seq = NEW.prev_seq;
  IF expected IS NULL THEN
    RAISE EXCEPTION USING ERRCODE='P0001',
      MESSAGE='MAINLINE: no predecessor event for the declared prev_seq';
  END IF;
  RETURN NEW;
END $$;

CREATE TRIGGER permit_event_chain BEFORE INSERT ON mainline.permit_event
  FOR EACH ROW EXECUTE FUNCTION mainline.fn_permit_event_chain();
```
"""


def _selftest_tree(root: Path, *, mutate: bool, weld: bool) -> None:
    """Write a miniature repository whose migrations agree with (or drift from) the spec."""
    (root / SPEC_RELATIVE).parent.mkdir(parents=True, exist_ok=True)
    (root / SPEC_RELATIVE).write_text(_SELFTEST_SPEC, encoding="utf-8", newline="\n")

    normative = extract_normative(_SELFTEST_SPEC)
    migrations = root / MIGRATIONS_RELATIVE
    migrations.mkdir(parents=True, exist_ok=True)

    for variant in VARIANTS:
        wanted = normative_for(normative, variant)
        body = wanted.create_function
        if mutate:
            # The exact defect the check exists to catch: a guard that no longer bites on
            # a NULL. Semantic, small, and invisible to the eye in a large migration.
            body = body.replace("IF expected IS NULL THEN", "IF expected IS NOT NULL THEN")
        banner = "-- SPDX-License-Identifier: FSL-1.1-ALv2\n-- rendered; do not edit\n\n"
        (migrations / variant.function_migration).write_text(
            banner + body + "\n", encoding="utf-8", newline="\n"
        )
        trigger_text = wanted.create_trigger if weld else "-- the weld was removed\n"
        (migrations / variant.trigger_migration).write_text(
            banner + trigger_text + "\n", encoding="utf-8", newline="\n"
        )


def selftest() -> int:
    """Prove all four assertions bite, on throwaway trees, with no cluster anywhere.

    PL-2: a guard nobody has watched fail is a guard nobody knows is wired up. Every case
    below runs the real ``main``; none of them mocks the thing under test.
    """
    import io
    import tempfile
    from contextlib import redirect_stdout

    cases: list[tuple[str, dict[str, bool], list[str], int]] = [
        ("spec and migrations agree", {"mutate": False, "weld": True}, [], 0),
        ("agreement, --strict (SKIP is fatal)", {"mutate": False, "weld": True}, ["--strict"], 1),
        ("body mutated", {"mutate": True, "weld": True}, [], 1),
        ("weld removed", {"mutate": False, "weld": False}, [], 1),
        ("both", {"mutate": True, "weld": False}, [], 1),
    ]

    failures = 0
    with tempfile.TemporaryDirectory() as raw_root:
        for label, tree, extra, expected in cases:
            root = Path(raw_root) / label.replace(" ", "_").replace(",", "").replace("-", "")
            _selftest_tree(root, **tree)
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                # `--dsn ""` is impossible to satisfy; combined with a cleared environment
                # inside main(), the live assertions are guaranteed to SKIP.
                actual = main(["--repo-root", str(root), "--no-cluster", *extra])
            verdict = PASS if actual == expected else FAIL
            if verdict == FAIL:
                failures += 1
                print(buffer.getvalue())
            print(f"{verdict:<4}  selftest · {label}: expected exit {expected}, got {actual}")

    # The normaliser's own contract, asserted rather than assumed.
    equivalences: list[tuple[str, str, bool]] = [
        ("SELECT A FROM t;", "select   a\n from t", True),
        ("SELECT 1 -- note\n", "SELECT 1", True),
        ("SELECT 'A'", "SELECT 'a'", False),
        ('SELECT "A"', 'SELECT "a"', False),
        ("f() AS $$ BEGIN RETURN 1; END $$", "f() as $body$ begin return 1; end $body$", True),
        ("IF a <> b", "IF a != b", False),
    ]
    for left, right, same in equivalences:
        actual_same = normalise_sql(left) == normalise_sql(right)
        verdict = PASS if actual_same == same else FAIL
        if verdict == FAIL:
            failures += 1
        print(f"{verdict:<4}  selftest · normalise({left!r}) {'==' if same else '!='} {right!r}")

    print(f"\nselftest: {len(cases) + len(equivalences) - failures} passed, {failures} failed")
    return 1 if failures else 0


# ======================================================================================
# Entry point
# ======================================================================================


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="CU-9: the chain trigger the database runs is the body the spec specifies.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parent.parent.parent,
        help="repository root (defaults to the one containing this script)",
    )
    parser.add_argument("--dsn", default=None, help=f"pgwire DSN (or ${' / $'.join(DSN_ENV)})")
    parser.add_argument(
        "--no-cluster",
        action="store_true",
        help="do not attempt any live assertion; A3/A4 report SKIP",
    )
    parser.add_argument(
        "--no-probe",
        action="store_true",
        help="do not create the throwaway probe schema; A3 reports SKIP (see module docstring)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="treat any SKIP as a failure; the K2 exit gate uses this",
    )
    parser.add_argument(
        "--print-renderings",
        action="store_true",
        help="print the live and specified bodies as the server renders them, then exit",
    )
    parser.add_argument(
        "--selftest", action="store_true", help="prove the assertions bite, on throwaway trees"
    )
    arguments = parser.parse_args(argv)

    if arguments.selftest:
        return selftest()

    root: Path = arguments.repo_root.resolve()
    spec_path = root / SPEC_RELATIVE
    if not spec_path.is_file():
        print(f"{FAIL}  the normative document is missing: {spec_path}")
        print("\nchain function conformance: 1 failed")
        return 1

    try:
        spec = extract_normative(spec_path.read_text(encoding="utf-8"))
    except SpecificationError as exc:
        print(f"{FAIL}  {exc}")
        print("\nchain function conformance: 1 failed")
        return 1

    report = Report()
    check_offline(root, spec, report)

    dsn = None if arguments.no_cluster else resolve_dsn(arguments.dsn)
    if dsn is None:
        reason = "--no-cluster was given" if arguments.no_cluster else NO_CLUSTER_REASON
        report.record(SKIP, f"A3/A4 live conformance: {reason}. NOT CHECKED")
    else:
        try:
            connection = connect(dsn)
        except ClusterUnavailable as exc:
            report.record(SKIP, f"A3/A4 live conformance: {exc}. NOT CHECKED")
        else:
            try:
                cluster = LiveCluster(connection)
                if arguments.print_renderings:
                    print_renderings(cluster, spec)
                check_live(cluster, spec, report, probe=not arguments.no_probe)
            finally:
                connection.close()

    report.emit()

    print(
        f"\nchain function conformance: {report.passed} passed, "
        f"{report.failed} failed, {report.skipped} skipped"
    )
    if report.skipped:
        print(
            f"NOT CHECKED: the run above skipped {report.skipped} assertion(s). A skipped "
            "check proves nothing; it is printed here as loudly as a failure so that it "
            "cannot be mistaken for one that passed."
        )
    if report.failed or (arguments.strict and report.skipped):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
