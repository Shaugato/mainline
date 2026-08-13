#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
#
# MI: none — this file makes no database claim. It reads Python source and never connects.
# I: QA-RATCHET-3 — every statement that READS a row declares the shape it reads it in,
#    and the number of statements that do not is a counted, published number that may
#    fall and may not rise. A count recorded at 0 for a unit is a hard gate there.
# RATIONALE: `db.py:309` opens every production connection with `row_factory=dict_row`
#    while psycopg's own default is `tuple_row`, so the SHAPE of a row is a property of
#    whoever opened the connection and not of the statement that reads it. Both
#    consequences have already been paid for in this repository: `scenario.resolve`
#    unpacked a dict into eight names and bound the string "check_id" as a uuid (22P02),
#    and `refusal._explain` indexed a one-key dict at [0] (KeyError: 0) and took
#    `/v1/gate/run` to a 500 on beats 2 and 3 of EVERY gate run. Banning the shape
#    outright is not available: `reads.py` makes 43 name-keyed accesses across twelve GET
#    resources and is CORRECT to inherit dict rows. So the rule is not "never inherit" but
#    "always declare", and this script counts the statements that do not.

"""Repo-wide row-factory scanner: a statement must declare the row shape it reads.

WHAT A DECLARATION IS. Exactly one of four things, resolved at the reading site:

  1. ``scenario.positional(conn, sql, params)`` — the cursor is told to produce tuples.
     POSITION.
  2. ``conn.cursor(row_factory=<factory>)`` — the cursor is told what to produce. POSITION
     for ``tuple_row``, NAME for ``dict_row``/``class_row``/``namedtuple_row``.
  3. The module opened the connection itself — ``psycopg.connect(...)``, with an explicit
     ``row_factory=`` or on psycopg's default. An opener has already answered the question
     for its own reads.
  4. A ``# rowshape: position`` / ``# rowshape: name`` pragma on the statement.

An unadorned ``conn.execute(...).fetchone()`` on a connection the module did not open is
INHERITED: it reads whatever shape the caller chose. That is not an offence by itself — it
is how ``reads.py`` and ``db.server_now`` are written, and they are right — but it becomes
one the moment the module does something only one shape supports.

WHY THE POSITIONAL-READ FINDING IS GATED ON A HAZARD, AND WHAT THAT COST.

Measured on 2026-08-13 against this tree: 247 connections are opened on psycopg's default
factory and 14 with an explicit one. Reading a borrowed connection positionally is
therefore the CORRECT thing to do almost everywhere, and an ungated rule reported 508
sites — a number in which the four real defects were invisible. A finding nobody can act
on is a finding nobody believes, so the rule is gated on the disagreement the brief names:
a borrowed positional read counts only inside a UNIT (an importable ``src/<module>``
directory, or a directory of scripts or tests) that also contains a NON-DEFAULT opener, or
in a module that names ``db.connection`` — the one production factory. Inside such a unit
the mapping rows genuinely arrive, and the read genuinely cannot know. Everywhere else the
count is published as a census number (``positional_borrowers``) rather than as an
accusation.

THE FIVE FINDINGS, and why each is a defect rather than a style preference:

  inherited_positional_read
      A borrowed row is indexed by integer or unpacked into names, inside a unit that
      opens mapping rows. ``KeyError: 0`` and ``22P02`` verbatim.

  both_shapes
      One row is read BOTH positionally and by name, or dispatched on with
      ``isinstance(row, (list, tuple))``. Measured example, and the reason this finding
      exists: ``mainline_custody_patrol/collect.py:376`` writes
      ``row[0] if isinstance(row, (list, tuple)) else row['seq']``. Nothing is broken
      today. What is wrong is that the author could not know which shape arrives, so the
      code answers both — and a defensive branch is a convention that was never declared,
      which is the state every defect above started from. Ungated: it needs no hazard,
      because the code is already telling you it does not know.

  declared_shape_contradicted
      A statement declared one shape and its row is read in the other. The sharpest
      finding available: the intent is on the page and the code disagrees with it.

  mixed_conventions
      A module declares POSITION at one statement and declares nothing at another. This is
      what ``refusal.py`` looked like on 2026-08-12: four statements through
      ``positional()`` and one bare ``conn.execute(...).fetchone()``, with no way for a
      reader to tell whether the bare one was a deliberate mapping read or an oversight.
      It was an oversight, and it was a 500 on every gate run.

  mutates_connection_row_factory
      ``conn.row_factory = ...``. A fix of this shape makes the current statement work and
      silently changes every statement served afterwards on the same warm Lambda
      container. ``tests/test_row_factory_contract.py`` asserts against it behaviourally;
      this finds it without running anything.

WHAT THIS DELIBERATELY DOES NOT DO. It does not import the modules it scans and it does
not connect to anything, so it runs in the ``--crdb=none`` lane and on a checkout where
nothing is installed. It does not guess: a subscript whose key is a variable
(``record[column]`` in ``reads.audit``) is counted neither way, and a name that is bound
twice in one scope is dropped rather than reasoned about. A manufactured finding is how a
ratchet stops being believed. It never writes to a source file; its only possible write is
``--write``.

Exit codes: 0 at or below the ceiling, 1 above it, 2 tooling/usage failure.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final, NamedTuple

REPO_ROOT: Final = Path(__file__).resolve().parents[2]
SCHEMA: Final = "mainline.qa.row-factory-ratchet/1"

# ── The taxonomy ────────────────────────────────────────────────────────────────────

#: Rows are tuples; columns are read by ordinal.
POSITION: Final = "position"
#: Rows are mappings; columns are read by name.
NAME: Final = "name"
#: Declared, but as neither of the two — `scalar_row`, or a `class_row(...)` whose target
#: this scanner will not resolve. *Declared* is the property that matters.
DECLARED: Final = "declared"
#: No declaration reachable from the reading site: the row is the opener's choice.
INHERITED: Final = "inherited"

#: Where a shape came from. `cursor` is a declaration AT the statement; `opener` is the
#: module having opened the connection itself; `unknown` is a borrowed connection.
FROM_CURSOR: Final = "cursor"
FROM_OPENER: Final = "opener"
FROM_UNKNOWN: Final = "unknown"

_FETCHERS: Final = frozenset({"fetchone", "fetchall", "fetchmany"})
_PLURAL_FETCHERS: Final = frozenset({"fetchall", "fetchmany"})
_POSITION_FACTORIES: Final = frozenset({"tuple_row", "TupleRow", "args_row"})
_NAME_FACTORIES: Final = frozenset(
    {"dict_row", "DictRow", "class_row", "namedtuple_row", "kwargs_row"}
)
#: Mapping methods. Calling one on a row is a NAME read as surely as ``row["x"]``.
_NAME_METHODS: Final = frozenset({"get", "keys", "values", "items"})
#: Names that answer "which factory produced this?" rather than "what type is this column?"
_SHAPE_TYPES: Final = frozenset(
    {"list", "tuple", "dict", "Mapping", "MutableMapping", "Sequence", "TupleRow", "DictRow"}
)

#: ``db.connection()`` — `mainline_demo_api.db.connection`, the single production factory
#: (`db.py:309`), which opens `dict_row`. Naming it turns "you inherited something" into
#: "you contradicted dict_row", which is a message worth more. The alias form matches the
#: `db_mod.connection(...)` the demo-api tests import it as.
_PRODUCTION_CONNECTION: Final = re.compile(r"(?:^|\.)db[a-z_]*\.connection$")

#: Trees, longest-intent-first, taken verbatim from `scripts/qa/ruff_ratchet.py` so the two
#: ratchets bucket the repository the same way. `other/` is the deliberate catch-all.
TREES: Final[tuple[str, ...]] = (
    "packages/trappoint-*",
    "packages/mainline-*",
    "verticals/",
    "tests/",
    "scripts/",
    "other/",
)
_TOP_LEVEL: Final = {"verticals": "verticals/", "tests": "tests/", "scripts": "scripts/"}

#: Directories that are not this repository's source, even when they sit inside it.
SKIP_DIRS: Final = frozenset(
    {
        ".git",
        ".venv",
        ".tox",
        ".nox",
        ".mypy_cache",
        ".ruff_cache",
        ".pytest_cache",
        "__pycache__",
        "node_modules",
        "site-packages",
        "build",
        "dist",
        ".terraform",
    }
)

#: A file with none of these words issues no statement this scanner can have an opinion
#: about. Purely a speed gate: every construct that can produce a finding contains one.
_INTERESTING: Final = re.compile(r"fetch(?:one|all|many)|\.cursor\(|row_factory|psycopg")

#: ``# rowshape: position`` / ``# rowshape: name``, on any physical line the statement
#: spans. A DECLARATION, not a suppression: the shape it names is checked against how the
#: row is actually read, so a wrong pragma fails as `declared_shape_contradicted` instead
#: of silencing anything.
_PRAGMA: Final = re.compile(r"#\s*rowshape:\s*(position|name)\b")

KINDS: Final[tuple[str, ...]] = (
    "inherited_positional_read",
    "both_shapes",
    "declared_shape_contradicted",
    "mixed_conventions",
    "mutates_connection_row_factory",
)


def classify(rel_posix: str) -> str:
    """Map a repo-relative POSIX path to exactly one tree name from :data:`TREES`."""
    parts = rel_posix.split("/")
    head = parts[0]
    if head == "packages":
        sub = parts[1] if len(parts) > 1 else ""
        for prefix in ("trappoint-", "mainline-"):
            if sub.startswith(prefix):
                return f"packages/{prefix}*"
        return "other/"
    return _TOP_LEVEL.get(head, "other/")


def unit_of(rel_posix: str) -> str:
    """The blast radius of one opener's choice: an importable module, or a directory.

    Connections flow from whatever opens them to whatever the same distribution hands them
    to, so ``src/<module>`` is the natural unit for library code. A script or a test
    directory has no ``src/``; there the directory is the unit, which is right for
    ``demo-api/tests`` where one ``conftest.py`` opens `dict_row` for every sibling.
    """
    parts = rel_posix.split("/")
    if "src" in parts:
        index = parts.index("src")
        if index + 1 < len(parts) - 1:
            return "/".join(parts[: index + 2])
    return "/".join(parts[:-1]) or "."


# ── The report ──────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Finding:
    """One statement that does not declare the shape it reads, and the correction."""

    kind: str
    path: str
    line: int
    symbol: str
    detail: str
    fix: str

    @property
    def tree(self) -> str:
        return classify(self.path)

    @property
    def key(self) -> tuple[str, str, int, str]:
        return (self.kind, self.path, self.line, self.symbol)

    def render(self) -> str:
        return (
            f"{self.path}:{self.line}  {self.kind}\n"
            f"    {self.symbol}\n"
            f"    {self.detail}\n"
            f"    fix: {self.fix}"
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "file": self.path,
            "line": self.line,
            "symbol": self.symbol,
            "tree": self.tree,
            "detail": self.detail,
            "fix": self.fix,
        }


class Site(NamedTuple):
    """One statement whose ROWS are read, and the shape it turned out to have."""

    line: int
    convention: str
    source: str
    expr: str


@dataclass(frozen=True)
class ModuleConvention:
    """What convention one module reads rows in, and the sites that decide it.

    The verdict is the answer to the question the ratchet actually asks — "does this
    module read by position or by name?" — computed rather than declared, so a module
    added to a package cannot arrive unclassified.
    """

    path: str
    verdict: str
    position_sites: tuple[int, ...]
    name_sites: tuple[int, ...]
    undeclared_sites: tuple[int, ...]

    #: A module that issues no row-reading statement at all. `app.py`, `envelope.py` and
    #: `static_site.py` are here, and being here is a fact worth asserting: the day one of
    #: them grows a query, its convention becomes a decision someone has to make.
    SILENT: Final = "silent"
    #: Declares position at every reading site.
    POSITION: Final = POSITION
    #: Reads by name — either declared at the cursor, or inherited from an opener that
    #: chose `dict_row`, which under `db.connection()` is the same thing.
    NAME: Final = NAME
    #: Position AND at least one site declaring nothing. The state `refusal.py` was in on
    #: 2026-08-12, and the only one of these five that is an offence by itself.
    MIXED: Final = "mixed"
    #: Position at some statements and name at others, with EVERY statement declaring
    #: which. Legitimate: the declaration is what the rule asks for, not uniformity.
    DECLARED_BOTH: Final = "declared-both"

    @property
    def sites(self) -> int:
        return len(self.position_sites) + len(self.name_sites) + len(self.undeclared_sites)

    def as_dict(self) -> dict[str, Any]:
        return {
            "file": self.path,
            "verdict": self.verdict,
            "position_sites": list(self.position_sites),
            "name_sites": list(self.name_sites),
            "undeclared_sites": list(self.undeclared_sites),
        }


@dataclass(frozen=True)
class Opener:
    """One site that opens a connection and so CHOOSES the shape for everything downstream."""

    path: str
    line: int
    factory: str
    convention: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "file": self.path,
            "line": self.line,
            "factory": self.factory,
            "convention": self.convention,
        }


@dataclass
class Report:
    """The census and the verdict, in the shape a ratchet can compare."""

    findings: list[Finding] = field(default_factory=list)
    non_default_openers: list[Opener] = field(default_factory=list)
    default_openers: int = 0
    positional_borrowers: list[str] = field(default_factory=list)
    hazard_units: list[str] = field(default_factory=list)
    #: Every scanned file, including the ones that issue no statement. A per-package
    #: assertion is only worth making if the scanner can be shown to have SEEN the
    #: package; a table with an entry per file is that proof.
    conventions: dict[str, ModuleConvention] = field(default_factory=dict)
    files_scanned: int = 0
    files_parsed: int = 0
    unparseable: list[str] = field(default_factory=list)

    @property
    def count(self) -> int:
        """The ratchet number: statements that do not declare the shape they read."""
        return len(self.findings)

    def by_kind(self) -> dict[str, int]:
        counts = dict.fromkeys(KINDS, 0)
        for finding in self.findings:
            counts[finding.kind] = counts.get(finding.kind, 0) + 1
        return counts

    def by_tree(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for finding in self.findings:
            counts[finding.tree] = counts.get(finding.tree, 0) + 1
        return dict(sorted(counts.items(), key=lambda kv: TREES.index(kv[0])))

    def ordered(self) -> list[Finding]:
        return sorted(self.findings, key=lambda f: (KINDS.index(f.kind), f.path, f.line))

    def under(self, prefix: str) -> list[Finding]:
        """Findings under a repo-relative path prefix — how one unit gates itself at 0."""
        return [f for f in self.ordered() if f.path == prefix or f.path.startswith(prefix)]

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA,
            "generated_utc": datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "files_scanned": self.files_scanned,
            "files_parsed": self.files_parsed,
            "unparseable": sorted(self.unparseable),
            "count": self.count,
            "by_kind": self.by_kind(),
            "by_tree": self.by_tree(),
            "openers": {
                "non_default": [o.as_dict() for o in self.non_default_openers],
                "non_default_count": len(self.non_default_openers),
                "psycopg_default_count": self.default_openers,
            },
            "census": {
                "hazard_units": sorted(self.hazard_units),
                "positional_borrowers": sorted(set(self.positional_borrowers)),
                "positional_borrower_count": len(set(self.positional_borrowers)),
            },
            "conventions": [self.conventions[path].as_dict() for path in sorted(self.conventions)],
            "findings": [f.as_dict() for f in self.ordered()],
        }


# ── Reading the source ──────────────────────────────────────────────────────────────


class Shape(NamedTuple):
    """A row shape and where the knowledge of it came from."""

    convention: str
    source: str


UNKNOWN_SHAPE: Final = Shape(INHERITED, FROM_UNKNOWN)


def _dotted(node: ast.AST | None) -> str | None:
    """Render ``a.b.c`` / ``self.connection`` as a dotted string; None for anything else."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _dotted(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    return None


def _tail(dotted: str | None) -> str:
    return dotted.rsplit(".", 1)[-1] if dotted else ""


def _kwarg(call: ast.Call, name: str) -> ast.expr | None:
    for keyword in call.keywords:
        if keyword.arg == name:
            return keyword.value
    return None


def _factory_convention(node: ast.expr) -> str:
    """Classify a ``row_factory=`` VALUE. Unrecognised is DECLARED, never INHERITED."""
    name = _dotted(node)
    if name is None and isinstance(node, ast.Call):
        name = _dotted(node.func)
    tail = _tail(name)
    if tail in _POSITION_FACTORIES:
        return POSITION
    if tail in _NAME_FACTORIES:
        return NAME
    return DECLARED


def _is_connect(call: ast.Call) -> bool:
    dotted = _dotted(call.func) or ""
    return dotted.endswith(("psycopg.connect", "Connection.connect", "AsyncConnection.connect"))


def _is_production_connection(call: ast.Call) -> bool:
    return bool(_PRODUCTION_CONNECTION.search(_dotted(call.func) or ""))


def _walk_scope(body: Iterable[ast.stmt]) -> Iterator[ast.AST]:
    """Every node in THIS scope, not descending into a nested function or class.

    The stop is on the scope node itself, not on its children: stopping one level too late
    put every function's body into the module scope as well as its own, which both doubled
    every finding and let a module-level binding claim a local name. Measured, and the
    reason this helper is written out rather than being an ``ast.walk`` with a filter.
    """
    stack: list[ast.AST] = list(body)
    while stack:
        node = stack.pop()
        yield node
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            continue
        stack.extend(ast.iter_child_nodes(node))


@dataclass
class _Row:
    """One value bound to a fetched row, and every way this module reads it."""

    shape: Shape
    line: int
    expr: str
    uses: dict[str, int] = field(default_factory=dict)
    defensive: int = 0
    production: bool = False

    def use(self, kind: str, line: int) -> None:
        self.uses.setdefault(kind, line)


class _Scope:
    """One function, class or module body, and what each local name holds inside it."""

    def __init__(self, module: _ModuleScan) -> None:
        self.module = module
        self.conns: dict[str, Shape] = {}
        self.cursors: dict[str, Shape] = {}
        self.rows: dict[str, _Row] = {}
        self.rowsets: dict[str, Shape] = {}
        #: Names bound more than once to different things. Python's scoping is
        #: function-wide, so `row` reused as a comprehension target later in the same
        #: function is indistinguishable from the fetched `row` without running the code.
        #: Dropping them is the honest answer; guessing manufactures findings.
        self.ambiguous: set[str] = set()
        #: Per-SCOPE, never on the module. Keying this by `id(scope)` on a shared module
        #: dict was wrong in a way that only shows up at scale: a `_Scope` is released as
        #: soon as its body is done, CPython reuses the address, and the next scope
        #: inherited the previous one's binding history and marked live names ambiguous.
        self.binding_kinds: dict[str, set[bool]] = {}
        #: Rows that were never given a name — `a, b = cur.fetchone()`, or a subscript
        #: straight off the fetch. Keyed by (line, expression) so the repeated binding
        #: passes collapse onto one row rather than leaving an unresolved copy behind to
        #: be reported as undeclared.
        self.anon: dict[tuple[int, str], _Row] = {}

    # -- resolution -------------------------------------------------------------

    def conn_shape(self, node: ast.expr) -> Shape:
        dotted = _dotted(node)
        if dotted and dotted in self.conns and dotted not in self.ambiguous:
            return self.conns[dotted]
        if isinstance(node, ast.Call):
            if _is_production_connection(node):
                return Shape(NAME, FROM_OPENER)
            if _is_connect(node):
                factory = _kwarg(node, "row_factory")
                if factory is not None:
                    return Shape(_factory_convention(factory), FROM_OPENER)
                # psycopg's own default IS tuple_row. A module that opened its own
                # connection and reads it positionally is correct, and saying otherwise
                # would be 247 false findings in this tree alone.
                return Shape(POSITION, FROM_OPENER)
        return UNKNOWN_SHAPE

    def cursor_shape(self, node: ast.expr) -> Shape | None:
        """The shape of a cursor expression; None when the node is not a cursor."""
        dotted = _dotted(node)
        if dotted and dotted in self.cursors and dotted not in self.ambiguous:
            return self.cursors[dotted]
        if not isinstance(node, ast.Call):
            return None
        func = node.func
        if _tail(_dotted(func)) == "positional":
            return Shape(POSITION, FROM_CURSOR)
        if not isinstance(func, ast.Attribute):
            return None
        return self._method_shape(func, node)

    def _method_shape(self, func: ast.Attribute, node: ast.Call) -> Shape | None:
        """Resolve `.cursor(...)`, `.execute(...)` and `.fetchX()` onto their receiver."""
        if func.attr == "cursor":
            factory = _kwarg(node, "row_factory")
            if factory is not None:
                return Shape(_factory_convention(factory), FROM_CURSOR)
            return self.conn_shape(func.value)
        if func.attr == "execute":
            return self.cursor_shape(func.value) or self.conn_shape(func.value)
        if func.attr in _FETCHERS:
            return self.cursor_shape(func.value)
        return None

    def fetch_shape(self, node: ast.expr) -> Shape | None:
        """The shape of a ``.fetchX()`` call's rows; None when the node is not one."""
        if not isinstance(node, ast.Call):
            return None
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr in _FETCHERS):
            return None
        return self.cursor_shape(func.value) or UNKNOWN_SHAPE

    @staticmethod
    def _is_production(node: ast.expr) -> bool:
        return any(
            isinstance(inner, ast.Call) and _is_production_connection(inner)
            for inner in ast.walk(node)
        )

    # -- binding ----------------------------------------------------------------

    def note_binding(self, target: ast.expr, value: ast.expr) -> None:
        """Record that *target* was assigned, so a name bound twice can be dropped."""
        if not isinstance(target, ast.Name):
            return
        held = self.fetch_shape(value) is not None or self.cursor_shape(value) is not None
        kinds = self.binding_kinds.setdefault(target.id, set())
        kinds.add(held)
        if len(kinds) > 1:
            self.ambiguous.add(target.id)

    def bind(self, target: ast.expr, value: ast.expr) -> None:
        self.note_binding(target, value)
        shape = self.fetch_shape(value)
        if shape is not None:
            plural = _tail(_dotted(value.func)) in _PLURAL_FETCHERS  # type: ignore[attr-defined]
            self._bind_row(target, shape, value, plural=plural)
            return
        cursor = self.cursor_shape(value)
        if cursor is not None:
            if isinstance(target, ast.Name):
                self.cursors[target.id] = cursor
            return
        if isinstance(target, ast.Name):
            conn = self.conn_shape(value)
            if conn.source == FROM_OPENER:
                self.conns[target.id] = conn

    def _remember(self, name: str, shape: Shape, line: int, expr: str, production: bool) -> None:
        """Bind, or UPGRADE a binding made before its cursor had been resolved.

        The binding passes run to a fixed point because `_walk_scope` is a stack and can
        reach `row = cur.fetchone()` before `cur = conn.cursor(row_factory=tuple_row)`.
        A plain `setdefault` therefore froze the first and worst answer — the row stayed
        `inherited` even after the cursor resolved, which reported a fully declared read
        as undeclared. Only UNKNOWN is ever overwritten, so a genuine mixture is still a
        mixture.
        """
        existing = self.rows.get(name)
        if existing is None:
            self.rows[name] = _Row(shape, line, expr, production=production)
            return
        if existing.shape.source == FROM_UNKNOWN and shape.source != FROM_UNKNOWN:
            existing.shape = shape
            existing.line = line
            existing.expr = expr
        existing.production = existing.production or production

    def _anonymous(self, shape: Shape, line: int, expr: str, production: bool) -> _Row:
        """The unnamed row at this site, created once and upgraded on later passes."""
        row = self.anon.get((line, expr))
        if row is None:
            row = _Row(shape, line, expr, production=production)
            self.anon[(line, expr)] = row
            return row
        if row.shape.source == FROM_UNKNOWN and shape.source != FROM_UNKNOWN:
            row.shape = shape
        row.production = row.production or production
        return row

    def _bind_row(self, target: ast.expr, shape: Shape, value: ast.expr, *, plural: bool) -> None:
        line = getattr(value, "lineno", 0)
        expr = ast.unparse(value)[:120]
        production = self._is_production(value)
        if isinstance(target, ast.Name):
            if plural:
                current = self.rowsets.get(target.id)
                if current is None or current.source == FROM_UNKNOWN:
                    self.rowsets[target.id] = shape
            else:
                self._remember(target.id, shape, line, expr, production)
            return
        if isinstance(target, (ast.Tuple, ast.List)) and not plural:
            # `a, b = <fetchone()>` — unpacking IS a positional read, and unpacking a dict
            # yields its KEYS rather than raising. `scenario.resolve`'s original defect
            # exactly, so it is recorded at the unpacking site.
            self._anonymous(shape, line, expr, production).use(POSITION, line)

    def bind_iteration(self, target: ast.expr, iterable: ast.expr) -> None:
        """``for x in <cursor|rowset>`` binds one row per pass; a tuple target reads it."""
        self.note_binding(target, iterable)
        shape = self.fetch_shape(iterable)
        if shape is None:
            dotted = _dotted(iterable)
            if dotted and dotted in self.rowsets and dotted not in self.ambiguous:
                shape = self.rowsets[dotted]
        if shape is None:
            shape = self.cursor_shape(iterable)
        if shape is None:
            return
        line = getattr(iterable, "lineno", 0)
        expr = ast.unparse(iterable)[:120]
        production = self._is_production(iterable)
        if isinstance(target, ast.Name):
            self._remember(target.id, shape, line, expr, production)
        elif isinstance(target, (ast.Tuple, ast.List)):
            self._anonymous(shape, line, expr, production).use(POSITION, line)

    # -- use --------------------------------------------------------------------

    def row_for(self, node: ast.expr) -> _Row | None:
        dotted = _dotted(node)
        if dotted:
            if dotted in self.ambiguous:
                return None
            if dotted in self.rows:
                return self.rows[dotted]
        shape = self.fetch_shape(node)
        if shape is None:
            return None
        return self._anonymous(
            shape,
            getattr(node, "lineno", 0),
            ast.unparse(node)[:120],
            self._is_production(node),
        )


class _ModuleScan:
    """One file, scanned. Bindings, then uses, then — once the tree is known — findings."""

    def __init__(self, path: Path, rel: str, source: str, tree: ast.Module) -> None:
        self.path = path
        self.rel = rel
        self.unit = unit_of(rel)
        self.tree = tree
        self.lines = source.splitlines()
        self.anonymous: list[_Row] = []
        self.rows: list[_Row] = []
        self.findings: list[Finding] = []
        self.openers: list[Opener] = []
        self.default_openers = 0
        self.sites: list[Site] = []
        self.declared_position_sites: list[int] = []
        self.declared_name_sites: list[int] = []
        self.undeclared_sites: list[tuple[int, str]] = []
        self.reads_production_connection = False

    # -- pragmas ----------------------------------------------------------------

    def pragma(self, node: ast.AST) -> str | None:
        """The ``# rowshape:`` declaration covering *node*, if the author wrote one."""
        start = getattr(node, "lineno", None)
        if start is None:
            return None
        end = getattr(node, "end_lineno", start) or start
        for number in range(start, min(end, len(self.lines)) + 1):
            match = _PRAGMA.search(self.lines[number - 1])
            if match:
                return match.group(1)
        return None

    def pragma_at(self, line: int) -> str | None:
        if 1 <= line <= len(self.lines):
            match = _PRAGMA.search(self.lines[line - 1])
            if match:
                return match.group(1)
        return None

    # -- the scan ---------------------------------------------------------------

    def convention(self) -> ModuleConvention:
        """This module's reading convention, computed from its sites rather than declared."""
        position = tuple(sorted(self.declared_position_sites))
        named = tuple(sorted(self.declared_name_sites))
        undeclared = tuple(sorted(line for line, _ in self.undeclared_sites))
        if not (position or named or undeclared):
            verdict = ModuleConvention.SILENT
        elif position and undeclared:
            verdict = ModuleConvention.MIXED
        elif position and named:
            verdict = ModuleConvention.DECLARED_BOTH
        elif position:
            verdict = ModuleConvention.POSITION
        else:
            # Named-at-the-cursor and inherited-from-the-opener are the same convention:
            # `db.connection()` opens `dict_row`, so a borrowed row IS a mapping, and a
            # module that never indexes one is reading by name whether it said so or not.
            verdict = ModuleConvention.NAME
        return ModuleConvention(self.rel, verdict, position, named, undeclared)

    def collect(self) -> None:
        self._census_openers()
        for body in self._scopes():
            self._scan_scope(body)

    def _scopes(self) -> Iterator[list[ast.stmt]]:
        yield list(self.tree.body)
        for node in ast.walk(self.tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                yield list(node.body)

    def _census_openers(self) -> None:
        for node in ast.walk(self.tree):
            if not (isinstance(node, ast.Call)):
                continue
            if _is_production_connection(node):
                self.reads_production_connection = True
                continue
            if not _is_connect(node):
                continue
            factory = _kwarg(node, "row_factory")
            if factory is None:
                self.default_openers += 1
                continue
            self.openers.append(
                Opener(
                    path=self.rel,
                    line=node.lineno,
                    factory=ast.unparse(factory)[:80],
                    convention=_factory_convention(factory),
                )
            )

    def _scan_scope(self, body: list[ast.stmt]) -> None:
        scope = _Scope(self)
        nodes = list(_walk_scope(body))
        # Three passes so a `conn -> cursor -> row` chain resolves regardless of the order
        # the walk visited it in. Three is the longest chain this scanner models; a fourth
        # would bind nothing new.
        for _ in range(3):
            self._bind_pass(scope, nodes)
        self._use_pass(scope, nodes)
        self._site_pass(scope, nodes)
        self.rows.extend(row for name, row in scope.rows.items() if name not in scope.ambiguous)
        self.rows.extend(scope.anon.values())

    def _bind_pass(self, scope: _Scope, nodes: list[ast.AST]) -> None:
        for node in nodes:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    scope.bind(target, node.value)
            elif isinstance(node, (ast.AnnAssign, ast.NamedExpr)) and node.value is not None:
                scope.bind(node.target, node.value)
            elif isinstance(node, (ast.With, ast.AsyncWith)):
                for item in node.items:
                    if item.optional_vars is not None:
                        scope.bind(item.optional_vars, item.context_expr)
            elif isinstance(node, (ast.For, ast.AsyncFor, ast.comprehension)):
                scope.bind_iteration(node.target, node.iter)

    def _use_pass(self, scope: _Scope, nodes: list[ast.AST]) -> None:
        for node in nodes:
            if isinstance(node, ast.Subscript):
                self._subscript(scope, node)
            elif isinstance(node, ast.Call):
                self._call(scope, node)

    def _subscript(self, scope: _Scope, node: ast.Subscript) -> None:
        row = scope.row_for(node.value)
        if row is None:
            return
        key = node.slice
        if not isinstance(key, ast.Constant) or isinstance(key.value, bool):
            # A non-literal key (`record[column]` in `reads.audit`) cannot be resolved
            # without running the module, so it is counted neither way.
            return
        if isinstance(key.value, int):
            row.use(POSITION, node.lineno)
        elif isinstance(key.value, str):
            row.use(NAME, node.lineno)

    def _call(self, scope: _Scope, node: ast.Call) -> None:
        func = node.func
        if isinstance(func, ast.Name) and func.id == "isinstance" and len(node.args) == 2:
            row = scope.row_for(node.args[0])
            if row is not None and self._is_shape_test(node.args[1]):
                row.defensive = node.lineno
            return
        if isinstance(func, ast.Name) and func.id in ("dict", "len") and node.args:
            row = scope.row_for(node.args[0])
            if row is not None and func.id == "dict":
                row.use(NAME, node.lineno)
            return
        if isinstance(func, ast.Attribute) and func.attr in _NAME_METHODS:
            row = scope.row_for(func.value)
            if row is not None:
                row.use(NAME, node.lineno)

    @staticmethod
    def _is_shape_test(node: ast.expr) -> bool:
        """True when an ``isinstance`` second argument names a ROW SHAPE, not a column type.

        ``isinstance(row, (list, tuple))`` and ``isinstance(row, dict)`` are two halves of
        one question — "which factory produced this?" — and asking it is the finding.
        ``isinstance(value, datetime)`` is a check on a COLUMN and is none of this
        scanner's business.
        """
        elements = node.elts if isinstance(node, (ast.Tuple, ast.List)) else [node]
        return any(_tail(_dotted(element)) in _SHAPE_TYPES for element in elements)

    def _declare(self, line: int, convention: str) -> None:
        """Record that line *line* declares *convention*, once."""
        # ONLY a declaration made AT the statement arms the mixing rule. A module that
        # opened its own default connection has declared nothing about the connections it
        # BORROWS, and treating that as a position declaration made every test file in the
        # tree a mixed one - measured, 271 findings.
        target = (
            self.declared_position_sites if convention == POSITION else self.declared_name_sites
        )
        if line not in target:
            target.append(line)

    def _site_pass(self, scope: _Scope, nodes: list[ast.AST]) -> None:
        """Record each reading site's declaration, and every connection mutation."""
        for node in nodes:
            if isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Attribute) and target.attr == "row_factory"
                for target in node.targets
            ):
                self._mutation(node)
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not (isinstance(func, ast.Attribute) and func.attr in _FETCHERS):
                # A cursor declaration is a declaration whether or not its rows are read.
                # `refusal.py` routes its SAVEPOINT / ROLLBACK TO / RELEASE statements
                # through `positional()` although none of them returns a row, because the
                # property being removed from that module is INHERITING a factory, not
                # crashing, and a later `RETURNING` clause must not be able to reintroduce
                # the defect quietly. Counting only fetch sites here would have let a
                # module adopt the position convention at four statements and still not
                # count as having adopted it.
                shape = scope.cursor_shape(node)
                if shape is not None and shape.source == FROM_CURSOR:
                    self._declare(node.lineno, shape.convention)
                continue
            pragma = self.pragma(node)
            shape = scope.cursor_shape(func.value) or UNKNOWN_SHAPE
            source = FROM_CURSOR if pragma is not None else shape.source
            convention = pragma or shape.convention
            expr = ast.unparse(node)[:120]
            self.sites.append(Site(node.lineno, convention, source, expr))
            if source == FROM_UNKNOWN:
                self.undeclared_sites.append((node.lineno, expr))
            elif source == FROM_CURSOR:
                self._declare(node.lineno, convention)

    def _mutation(self, node: ast.Assign) -> None:
        self.findings.append(
            Finding(
                kind="mutates_connection_row_factory",
                path=self.rel,
                line=node.lineno,
                symbol=ast.unparse(node)[:120],
                detail=(
                    "this assigns a row factory onto a live connection, so every statement "
                    "served afterwards on the same warm container reads a shape it did not "
                    "ask for. Saving and restoring the previous value narrows the window; "
                    "it does not close it, because anything the body calls is inside it."
                ),
                fix=(
                    "set the factory on the CURSOR instead: scenario.positional(conn, sql, "
                    "params) for tuples, conn.cursor(row_factory=dict_row) for mappings. "
                    "Neither touches the connection."
                ),
            )
        )

    # -- the verdict ------------------------------------------------------------

    def emit(self, *, hazard: bool) -> None:
        """Decide findings. *hazard* is true when this unit opens non-default rows."""
        for row in [*self.rows, *self.anonymous]:
            self._emit_row(row, hazard=hazard)
        self._emit_mix()

    def _emit_row(self, row: _Row, *, hazard: bool) -> None:
        declared = self.pragma_at(row.line)
        convention = declared or row.shape.convention
        declared_here = declared is not None or row.shape.source != FROM_UNKNOWN
        positional = POSITION in row.uses
        named = NAME in row.uses

        # Reading ONE row both ways is broken under either factory, so it counts however
        # the statement was declared. An `isinstance(row, dict)` counts only where nothing
        # was declared: in code that DID declare its shape the same call is an assertion
        # ABOUT the declaration — which is what `test_the_production_connection_really_is_
        # dict_row` is — and a scanner that cannot tell a premise from a guess would make
        # pinning a premise impossible.
        if (positional and named) or (row.defensive and not declared_here):
            line = row.defensive or max(row.uses.values())
            self.findings.append(
                Finding(
                    kind="both_shapes",
                    path=self.rel,
                    line=line,
                    symbol=row.expr,
                    detail=(
                        "this row is read BOTH by position and by name, so the module does "
                        "not know which factory produced it and answers both. Nothing is "
                        "broken today; what is missing is the declaration, and that is the "
                        "state every row-factory 500 in this repository started from."
                    ),
                    fix=(
                        "decide, at the statement: route it through "
                        "scenario.positional(conn, sql, params) and delete the name branch, "
                        "or open the cursor with conn.cursor(row_factory=dict_row) and "
                        "delete the index branch. Then delete the isinstance()."
                    ),
                )
            )
            return
        if not declared_here and positional and (hazard or row.production):
            self.findings.append(
                Finding(
                    kind="inherited_positional_read",
                    path=self.rel,
                    line=row.uses[POSITION],
                    symbol=row.expr,
                    detail=(
                        "this row is read by POSITION off a connection this module did not "
                        "open, inside a unit that opens MAPPING rows elsewhere"
                        + (" and through db.connection() itself" if row.production else "")
                        + ". Under dict_row an integer index is KeyError and an unpacking "
                        "silently yields the column NAMES instead of their values."
                    ),
                    fix=(
                        "wrap the statement in scenario.positional(conn, sql, params), "
                        "which sets row_factory=tuple_row on the CURSOR and leaves the "
                        "connection alone; or read the columns by name and declare it with "
                        "conn.cursor(row_factory=dict_row)."
                    ),
                )
            )
            return
        if not declared_here:
            return
        if convention == POSITION and named:
            self._contradiction(row, POSITION, NAME, row.uses[NAME])
        elif convention == NAME and positional:
            self._contradiction(row, NAME, POSITION, row.uses[POSITION])

    def _contradiction(self, row: _Row, declared: str, used: str, line: int) -> None:
        self.findings.append(
            Finding(
                kind="declared_shape_contradicted",
                path=self.rel,
                line=line,
                symbol=row.expr,
                detail=(
                    f"the statement at line {row.line} declares the {declared} convention "
                    f"and this reads its row by {used}. The declaration is on the page and "
                    "the code disagrees with it, so exactly one of the two is wrong."
                ),
                fix=(
                    f"either change the read to {declared}, or change the statement's "
                    f"declaration to {used}. If the statement returns columns CockroachDB "
                    "gives duplicate names, only position can carry them at all."
                ),
            )
        )

    def _emit_mix(self) -> None:
        if not (self.declared_position_sites and self.undeclared_sites):
            return
        anchor = min(self.declared_position_sites)
        for line, expr in self.undeclared_sites:
            self.findings.append(
                Finding(
                    kind="mixed_conventions",
                    path=self.rel,
                    line=line,
                    symbol=expr,
                    detail=(
                        f"this module declares the position convention at line {anchor} and "
                        "this statement declares nothing, so a reader cannot tell whether "
                        "the bare fetch is a deliberate mapping read or an oversight. "
                        "refusal.py was in exactly this state on 2026-08-12: it was an "
                        "oversight, and it was a 500 on every gate run."
                    ),
                    fix=(
                        "route it through scenario.positional(conn, sql, params) to join "
                        "the module's convention, or — if it really is meant to be read by "
                        "name - say so, with conn.cursor(row_factory=dict_row) or a "
                        "`# rowshape: name` declaration on the statement."
                    ),
                )
            )


# ── Walking the tree ────────────────────────────────────────────────────────────────


def iter_sources(roots: list[Path]) -> Iterator[Path]:
    """Every ``.py`` file under *roots* that is this repository's own source."""
    seen: set[Path] = set()
    for root in roots:
        candidates = [root] if root.is_file() else sorted(root.rglob("*.py"))
        for path in candidates:
            if any(part in SKIP_DIRS for part in path.parts):
                continue
            if path in seen:
                continue
            seen.add(path)
            yield path


def _rel(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root).as_posix()
    except ValueError:
        return path.as_posix()


def scan(roots: list[Path], repo_root: Path = REPO_ROOT) -> Report:
    """Scan *roots* and return the census. Never imports, never connects, never writes.

    Two phases, and the order is the whole point: a unit's openers are what decide whether
    a borrowed positional read in that unit is a defect or the ordinary correct thing, so
    nothing can be judged until every file has been read.
    """
    report = Report()
    scans: list[_ModuleScan] = []
    hazards: set[str] = set()

    for path in iter_sources(roots):
        report.files_scanned += 1
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            report.unparseable.append(_rel(path, repo_root))
            continue
        rel = _rel(path, repo_root)
        if not _INTERESTING.search(source):
            # No `fetch`, no `.cursor(`, no `row_factory`, no `psycopg`: the file cannot
            # read a row, so it is SILENT without being parsed. Recorded rather than
            # dropped, so `conventions` really is every file and a package assertion can
            # prove the scanner saw it.
            report.conventions[rel] = ModuleConvention(rel, ModuleConvention.SILENT, (), (), ())
            continue
        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError:
            # Reported, not skipped: a scanner that quietly ignores what it cannot read
            # reports a clean tree.
            report.unparseable.append(rel)
            continue
        report.files_parsed += 1
        module = _ModuleScan(path, rel, source, tree)
        module.collect()
        report.conventions[rel] = module.convention()
        scans.append(module)
        report.non_default_openers.extend(module.openers)
        report.default_openers += module.default_openers
        if any(opener.convention != POSITION for opener in module.openers):
            hazards.add(module.unit)
        if module.reads_production_connection:
            hazards.add(module.unit)

    report.hazard_units = sorted(hazards)
    deduped: dict[tuple[str, str, int, str], Finding] = {}
    for module in scans:
        module.emit(hazard=module.unit in hazards)
        for finding in module.findings:
            deduped.setdefault(finding.key, finding)
        if any(
            POSITION in row.uses and row.shape.source == FROM_UNKNOWN
            for row in [*module.rows, *module.anonymous]
        ):
            report.positional_borrowers.append(module.rel)
    report.findings = list(deduped.values())
    return report


# ── The ratchet ─────────────────────────────────────────────────────────────────────


def load_ceiling(path: Path | None) -> int | None:
    if path is None or not path.is_file():
        return None
    doc = json.loads(path.read_text(encoding="utf-8"))
    value = doc.get("count")
    return int(value) if value is not None else None


def render(report: Report, ceiling: int | None, *, quiet: bool) -> str:
    lines: list[str] = []
    if not quiet:
        lines.extend(finding.render() for finding in report.ordered())
        lines.append("")
    kinds = ", ".join(f"{kind}={n}" for kind, n in report.by_kind().items() if n)
    lines.append(
        f"row_factory_ratchet: {report.count} undeclared row read(s) across "
        f"{report.files_parsed} parsed file(s) of {report.files_scanned} scanned"
        + (f"  [{kinds}]" if kinds else "")
    )
    lines.append(
        f"  openers: {len(report.non_default_openers)} with an explicit row_factory "
        f"({len(report.hazard_units)} hazard unit(s)), "
        f"{report.default_openers} on psycopg's default (tuple_row)"
    )
    lines.append(
        f"  census: {len(set(report.positional_borrowers))} module(s) read a borrowed "
        "connection positionally"
    )
    if ceiling is not None:
        if report.count > ceiling:
            lines.append(
                f"  REFUSED: ceiling is {ceiling}, measured {report.count} "
                f"(+{report.count - ceiling}). A row-shape declaration was removed, or an "
                "undeclared read was added. Fix it, or raise the ceiling in a diff someone "
                "has to approve. Raising it is allowed; raising it silently is not."
            )
        elif report.count < ceiling:
            lines.append(
                f"  improved: ceiling is {ceiling}, measured {report.count} "
                f"(-{ceiling - report.count}). Tighten the ceiling to {report.count}."
            )
        else:
            lines.append(f"  at the ceiling ({ceiling}).")
    return "\n".join(lines)


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="row_factory_ratchet",
        description=(
            "Count the statements that read a database row without declaring the shape "
            "they read it in. A count may fall; it may not rise."
        ),
    )
    parser.add_argument(
        "roots",
        nargs="*",
        type=Path,
        help="files or directories to scan (default: the repository root)",
    )
    parser.add_argument("--json", action="store_true", help="emit the census as JSON")
    parser.add_argument(
        "--max",
        type=int,
        default=None,
        dest="ceiling",
        help="refuse when the measured count exceeds this number",
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        default=None,
        help="read the ceiling from this JSON document's `count` field",
    )
    parser.add_argument(
        "--write",
        type=Path,
        default=None,
        help="write the census to this path; the script's only possible write",
    )
    parser.add_argument("--quiet", action="store_true", help="print the totals only")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    roots = [p.resolve() for p in (args.roots or [REPO_ROOT])]
    for root in roots:
        if not root.exists():
            print(f"row_factory_ratchet: no such path: {root}", file=sys.stderr)
            return 2
    try:
        report = scan(roots)
        ceiling = args.ceiling if args.ceiling is not None else load_ceiling(args.baseline)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"row_factory_ratchet: {exc}", file=sys.stderr)
        return 2

    if args.write is not None:
        args.write.parent.mkdir(parents=True, exist_ok=True)
        args.write.write_text(
            json.dumps(report.as_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    if args.json:
        print(json.dumps(report.as_dict(), indent=2, ensure_ascii=False))
    else:
        print(render(report, ceiling, quiet=args.quiet))
    return 1 if ceiling is not None and report.count > ceiling else 0


if __name__ == "__main__":
    raise SystemExit(main())
