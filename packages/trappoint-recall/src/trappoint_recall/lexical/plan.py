# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Reading a CockroachDB ``EXPLAIN`` and refusing a full scan.

A BM25 statement that has silently degraded to a full scan of ``lex_posting`` still returns
**the correct answer**.  It returns it slower, on a corpus that is small during the demo and
large in production, and nothing anywhere fails.  That is the entire reason this module
exists: the defect it hunts has no symptom until it has a bad one, so it is asserted rather
than observed.

What is asserted, precisely:

1. the plan contains at least one access to ``lex_posting`` — a statement that never touched
   the posting list would trivially satisfy "no full scan";
2. every access to ``lex_posting`` goes through its primary index ``lex_posting_pk``, whose
   key is ``(site_id, term, event_id)``;
3. every such access is *constrained*: a ``scan`` node carries a ``spans`` attribute that is
   not ``FULL SCAN``, or the node is a lookup join, which is constrained by construction.

Honesty about provenance.  The parser understands the ``EXPLAIN`` text grammar that
CockroachDB emits (the ``• node`` tree with indented ``table:``/``spans:`` attributes).  The
specimens committed under ``tests/unit/recall_lexical/`` are **hand-written examples of that
grammar, not captures from a live cluster** — no CockroachDB was reachable from the machine
this was written on.  They make the parser and the assertion testable with no cluster; they do
not, and are not claimed to, prove what a real optimiser does.  The live assertion is
``tests/integration/recall_lexical/test_plan_assertion_live.py``, which runs ``EXPLAIN`` against a
real cluster and skips with a reason when there is none.  A skipped run verifies nothing.

``EXPLAIN`` and never ``EXPLAIN ANALYZE``: the Managed MCP surface forbids the latter, and the
question here is about the plan, which does not require execution to answer.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Final

__all__ = [
    "PlanAssertionError",
    "ScanNode",
    "assert_constrained_lex_scan",
    "parse_plan",
    "plan_digest",
    "plan_text_from_rows",
]

#: Box-drawing and bullet characters CockroachDB uses to draw the plan tree.
_TREE_CHARS: Final[str] = "│├└─┌┐┘┬┴┼|+-\\/ \t"

_NODE = re.compile(r"^[^\S\n]*[│├└─\s]*•\s*(?P<name>\S.*?)\s*$")
_TABLE = re.compile(r"^[\s│├└─]*table:\s*(?P<table>[^@\s]+)@(?P<index>\S+)\s*$")
_SPANS = re.compile(r"^[\s│├└─]*spans:\s*(?P<spans>\S.*?)\s*$")
_EQUALITY = re.compile(r"^[\s│├└─]*equality(?: cols)?:\s*(?P<equality>\S.*?)\s*$")
_ESTIMATED = re.compile(r"^[\s│├└─]*estimated row count:\s*(?P<rows>\S.*?)\s*$")

#: Node kinds that reach a table without a ``spans`` attribute but are nevertheless a point or
#: prefix lookup: the join feeds them keys, so there is no unconstrained span to report.
_CONSTRAINED_BY_CONSTRUCTION: Final[frozenset[str]] = frozenset(
    {"lookup join", "index join", "zigzag join"}
)


class PlanAssertionError(AssertionError):
    """The plan did not constrain the scan the way the design requires."""


@dataclass(frozen=True, slots=True)
class ScanNode:
    """One table access in the plan."""

    node: str
    table: str
    index: str
    spans: str | None
    equality: str | None
    line: int

    @property
    def bare_table(self) -> str:
        """``mainline.lex_posting`` and ``lex_posting`` are the same table."""
        return self.table.rsplit(".", 1)[-1].strip('"')

    @property
    def is_full_scan(self) -> bool:
        return self.spans is not None and "FULL SCAN" in self.spans.upper()

    @property
    def is_constrained(self) -> bool:
        if self.spans is not None:
            return not self.is_full_scan
        return self.node.lower().strip() in _CONSTRAINED_BY_CONSTRUCTION


def plan_text_from_rows(rows: str | Iterable[str | Sequence[object]]) -> str:
    """Join the single-column rows a driver returns for ``EXPLAIN`` into one text.

    ``EXPLAIN`` comes back as one row per plan line, and drivers disagree about whether that
    row is a 1-tuple or a bare string.  Both are accepted, and so is an already-joined text,
    so a caller never has to know which it has.
    """
    if isinstance(rows, str):
        return rows
    lines: list[str] = []
    for row in rows:
        if isinstance(row, str):
            lines.append(row)
        else:
            lines.append("" if not row else str(row[0]))
    return "\n".join(lines)


@dataclass(slots=True)
class _Pending:
    """A table access being assembled: its attributes arrive on the lines after it."""

    node: str
    table: str
    index: str
    line: int
    spans: str | None = None
    equality: str | None = None

    def freeze(self) -> ScanNode:
        return ScanNode(
            node=self.node,
            table=self.table,
            index=self.index,
            spans=self.spans,
            equality=self.equality,
            line=self.line,
        )


def parse_plan(plan_text: str) -> tuple[ScanNode, ...]:
    """Extract every table access from an ``EXPLAIN`` text."""
    nodes: list[ScanNode] = []
    current_node = ""
    pending: _Pending | None = None

    def flush() -> None:
        nonlocal pending
        if pending is not None:
            nodes.append(pending.freeze())
            pending = None

    for number, raw in enumerate(plan_text.splitlines(), start=1):
        line = raw.rstrip()
        if not line.strip(_TREE_CHARS):
            continue
        node_match = _NODE.match(line)
        if node_match is not None:
            flush()
            current_node = node_match.group("name")
            continue
        table_match = _TABLE.match(line)
        if table_match is not None:
            flush()
            pending = _Pending(
                node=current_node,
                table=table_match.group("table"),
                index=table_match.group("index"),
                line=number,
            )
            continue
        if pending is None:
            continue
        spans_match = _SPANS.match(line)
        if spans_match is not None:
            pending.spans = spans_match.group("spans")
            continue
        equality_match = _EQUALITY.match(line)
        if equality_match is not None:
            pending.equality = equality_match.group("equality")
            continue
        if _ESTIMATED.match(line) is not None:
            continue
    flush()
    return tuple(nodes)


def assert_constrained_lex_scan(
    plan_text: str,
    *,
    table: str = "lex_posting",
    index: str = "lex_posting_pk",
) -> tuple[ScanNode, ...]:
    """Refuse a plan in which channel D reads the posting list unconstrained.

    Returns the accesses it approved, so a caller can record them.  Raises
    :class:`PlanAssertionError` with the offending plan text otherwise — the whole plan, not a
    summary, because the next question after "it failed" is always "what did it do instead".
    """
    accesses = parse_plan(plan_text)
    mine = tuple(node for node in accesses if node.bare_table == table)
    if not mine:
        raise PlanAssertionError(
            f"the plan never accesses {table}. Either the statement changed or the plan text "
            f"was not parsed. Accesses found: "
            f"{[n.bare_table for n in accesses] or 'none'}\n--- plan ---\n{plan_text}"
        )
    wrong_index = [n for n in mine if n.index != index]
    if wrong_index:
        raise PlanAssertionError(
            f"{table} was read through {sorted({n.index for n in wrong_index})} rather than "
            f"{index}. The BM25 statement's WHERE clause is written to match that key "
            f"prefix (site_id, term); a different index means it no longer does."
            f"\n--- plan ---\n{plan_text}"
        )
    unconstrained = [n for n in mine if not n.is_constrained]
    if unconstrained:
        detail = ", ".join(
            f"line {n.line}: node={n.node!r} spans={n.spans!r}" for n in unconstrained
        )
        raise PlanAssertionError(
            f"{table} is scanned WITHOUT a constrained span ({detail}). Channel D still "
            "returns the correct ranking this way, which is exactly why this is asserted "
            "rather than noticed: the `p.term IN (...)` predicate is what builds the spans, "
            "and it is not an optimisation."
            f"\n--- plan ---\n{plan_text}"
        )
    return mine


def plan_digest(plan_text: str) -> str:
    """sha256 over the plan with volatile detail removed.

    Row-count estimates and span *counts* move with the data; the shape — which node reads
    which index, constrained or not — does not.  Digesting the shape means a stored digest
    means "the plan changed", not "the table grew".
    """
    normalised: list[str] = []
    for node in parse_plan(plan_text):
        span_kind = "full" if node.is_full_scan else ("constrained" if node.spans else "-")
        normalised.append(f"{node.node}|{node.bare_table}@{node.index}|{span_kind}")
    return hashlib.sha256("\n".join(normalised).encode("utf-8")).hexdigest()
