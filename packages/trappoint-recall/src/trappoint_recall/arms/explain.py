# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Parsing CockroachDB ``EXPLAIN`` output, and turning it into an assertion.

The documented fragment that proves a prefix-constrained vector search was planned is::

    • vector search
      table: items@items_customer_id_embedding_idx
      target count: 3
      prefix spans: [/1 - /1]

Four things must hold, and the fourth is the one that is easy to forget:

1. a node of type ``vector search`` exists;
2. its ``table:`` line names the expected ``table@index``;
3. its ``prefix spans:`` line is present **and non-empty** — an empty or absent prefix span
   means the prefix was not constrained, which is the documented condition under which the
   vector index is not used;
4. **no node anywhere in the plan is a full scan.** A plan can contain a vector search node
   and still be wrong: a filter the optimizer could not push into the prefix reappears as a
   scan beside it, and the arm that looked proven is the arm that reads the whole table.

This module reports all four independently. ``ok`` is the conjunction, but every component is
kept, because *"which of the four failed"* is the whole diagnostic value and an assertion that
collapses to a boolean throws it away.

**What this does NOT prove.** That the plan was chosen says nothing about what the executor
did, and nothing about whether C-SPANN's approximate search returned the neighbour that
mattered. Plan text is layer one of three. Layer two is behavioural — latency that grows
sublinearly as the corpus doubles, and a planted precursor that comes back in top-k, because
*a silently unused index scales linearly regardless of how the plan text is formatted*. Layer
three is the nightly characterisation test. No layer substitutes for another.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Final, Protocol

__all__ = [
    "FULL_SCAN_MARKER",
    "VECTOR_SEARCH_NODE",
    "ExplainPlan",
    "ExplainSource",
    "PlanAssertion",
    "PlanNode",
    "UnionPlanAssertion",
    "assert_arm_plan",
    "assert_arm_set_plan",
    "parse_explain",
]

#: The node type CockroachDB prints for a prefix-constrained ANN lookup.
VECTOR_SEARCH_NODE: Final = "vector search"

#: What CockroachDB prints on a scan node's ``spans:`` line when it reads everything.
FULL_SCAN_MARKER: Final = "FULL SCAN"

#: Tree-drawing glyphs EXPLAIN uses to render the plan as an outline. Stripped for field
#: parsing but their *column* is preserved first, because the column is the only reliable
#: signal of nesting depth.
_GLYPHS: Final = "│├└─┌┐┘┴┬┼|`+-"

_NODE_BULLET: Final = "•"
_FIELD_RE: Final = re.compile(r"^(?P<key>[A-Za-z][A-Za-z0-9 _\-]*?)\s*:\s*(?P<value>.*)$")
_TABLE_REF_RE: Final = re.compile(r"^(?P<table>[^\s@]+)@(?P<index>\S+)$")


class ExplainSource(Protocol):
    """Anything that can answer ``EXPLAIN <one statement>`` with its text.

    Deliberately a callable, not a connection. This package holds no database driver: the
    caller supplies pgwire, a Managed MCP tool call, or a recorded fixture, and the same
    assertions run over all three. That is what makes *"the claim is proven on CockroachDB's
    own public endpoint rather than on ours"* a matter of passing a different callable rather
    than of maintaining a second implementation.
    """

    def __call__(self, statement: str, /) -> str: ...


@dataclass(frozen=True, slots=True)
class PlanNode:
    """One node of the plan: its type, its nesting depth, and its ``key: value`` fields."""

    node_type: str
    depth: int
    column: int
    fields: Mapping[str, str]

    @property
    def table_ref(self) -> str | None:
        """The ``table@index`` string, exactly as printed, or ``None``."""
        return self.fields.get("table")

    @property
    def index_name(self) -> str | None:
        ref = self.table_ref
        if ref is None:
            return None
        match = _TABLE_REF_RE.match(ref)
        return match.group("index") if match else None

    @property
    def target_count(self) -> int | None:
        raw = self.fields.get("target count")
        if raw is None:
            return None
        try:
            return int(raw.strip())
        except ValueError:
            return None

    @property
    def prefix_spans(self) -> str | None:
        return self.fields.get("prefix spans")

    @property
    def is_full_scan(self) -> bool:
        return any(FULL_SCAN_MARKER in value.upper() for value in self.fields.values())


@dataclass(frozen=True, slots=True)
class ExplainPlan:
    """A parsed plan: the preamble, the nodes in printed order, and the raw text."""

    nodes: tuple[PlanNode, ...]
    preamble: Mapping[str, str]
    raw: str = field(repr=False)

    @property
    def vector_search_nodes(self) -> tuple[PlanNode, ...]:
        return tuple(n for n in self.nodes if n.node_type == VECTOR_SEARCH_NODE)

    @property
    def full_scan_nodes(self) -> tuple[PlanNode, ...]:
        return tuple(n for n in self.nodes if n.is_full_scan)

    @property
    def has_full_scan(self) -> bool:
        return bool(self.full_scan_nodes)

    def nodes_of(self, node_type: str) -> tuple[PlanNode, ...]:
        return tuple(n for n in self.nodes if n.node_type == node_type)


def _text_of(output: str | Sequence[str] | Iterable[Sequence[object]]) -> str:
    """Accept the three shapes an EXPLAIN answer arrives in.

    pgwire returns rows of one column; some tool surfaces return a list of strings; a fixture
    is one blob. All three are normalised here rather than at four call sites, because a
    parser that only accepts one shape gets copies of itself.
    """
    if isinstance(output, str):
        return output
    lines: list[str] = []
    for row in output:
        if isinstance(row, str):
            lines.append(row)
        elif isinstance(row, Sequence) and not isinstance(row, (bytes, bytearray)):
            lines.append(" ".join(str(cell) for cell in row))
        else:  # pragma: no cover - defensive; an unknown row shape must not be guessed at
            raise TypeError(f"cannot read EXPLAIN output row of type {type(row)!r}")
    return "\n".join(lines)


def parse_explain(output: str | Sequence[str] | Iterable[Sequence[object]]) -> ExplainPlan:
    """Parse plan text into nodes and fields.

    Robust to the two renderings CockroachDB produces — the flat two-space form and the tree
    form with ``│``/``└──`` glyphs — because both appear depending on plan depth, and a parser
    that only handles the flat form silently reports zero nodes for every nested plan, which
    would make *"no vector search node"* the default answer for the wrong reason.
    """
    text = _text_of(output)
    raw_nodes: list[tuple[str, int, dict[str, str]]] = []
    preamble: dict[str, str] = {}
    current: dict[str, str] | None = None

    for line in text.splitlines():
        if not line.strip():
            continue
        bullet = line.find(_NODE_BULLET)
        if bullet != -1:
            node_type = line[bullet + len(_NODE_BULLET) :].strip()
            fields: dict[str, str] = {}
            raw_nodes.append((node_type, bullet, fields))
            current = fields
            continue
        stripped = line.strip().lstrip(_GLYPHS).strip()
        if not stripped:
            continue
        match = _FIELD_RE.match(stripped)
        if match is None:
            continue
        key = match.group("key").strip().lower()
        value = match.group("value").strip()
        if current is None:
            preamble[key] = value
        elif key not in current:
            # First occurrence wins: CockroachDB prints `table:` once per node, and a repeat
            # inside one node would mean the glyph stripping merged two nodes — which the
            # column-based depth below would also show, so it is recorded rather than hidden.
            current[key] = value

    columns = sorted({column for _, column, _ in raw_nodes})
    depth_of = {column: depth for depth, column in enumerate(columns)}
    nodes = tuple(
        PlanNode(node_type=node_type, depth=depth_of[column], column=column, fields=fields)
        for node_type, column, fields in raw_nodes
    )
    return ExplainPlan(nodes=nodes, preamble=preamble, raw=text)


@dataclass(frozen=True, slots=True)
class PlanAssertion:
    """The structured verdict for one arm. Every component is kept, not just the conjunction."""

    arm_id: str | None
    expected_index_ref: str
    vector_search_present: bool
    vector_search_count: int
    observed_index_ref: str | None
    index_matches: bool
    target_count: int | None
    target_count_present: bool
    expected_target_count: int | None
    target_count_matches: bool
    prefix_spans: str | None
    prefix_spans_nonempty: bool
    full_scan_present: bool
    failures: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.failures

    def describe(self) -> str:
        if self.ok:
            return (
                f"arm {self.arm_id}: vector search on {self.observed_index_ref}, "
                f"target count {self.target_count}, prefix spans {self.prefix_spans}"
            )
        return f"arm {self.arm_id}: " + "; ".join(self.failures)


#: Empty renderings of a span list. ``prefix spans:`` present but empty means the optimizer
#: printed the line and constrained nothing, which is indistinguishable in effect from the
#: line being absent, and must fail for the same reason.
_EMPTY_SPANS: Final = frozenset({"", "[]", "-", "none", "<empty>"})


def assert_arm_plan(
    plan: ExplainPlan,
    *,
    expected_index_ref: str,
    arm_id: str | None = None,
    expected_target_count: int | None = None,
    require_exact_target_count: bool = False,
    expect_single_vector_search: bool = True,
) -> PlanAssertion:
    """Assert the documented fragment over a single-arm plan.

    ``require_exact_target_count`` defaults to **False** and that is a deliberate piece of
    honesty. The documented example shows ``target count`` equal to the query's ``LIMIT``, and
    every plan observed while writing this agreed — but whether CockroachDB ever inflates the
    target count to serve re-ranking is not documented, so equality is *recorded and
    reported* rather than *required*. A deployment that has observed the equality on its own
    version may turn the requirement on; this package will not assert an undocumented
    invariant on the deployment's behalf.
    """
    failures: list[str] = []
    vector_nodes = plan.vector_search_nodes
    present = bool(vector_nodes)
    if not present:
        failures.append(
            "no `vector search` node in the plan — the optimizer did not use the vector "
            f"index. Node types present: {sorted({n.node_type for n in plan.nodes})}"
        )
    if expect_single_vector_search and len(vector_nodes) > 1:
        failures.append(
            f"{len(vector_nodes)} `vector search` nodes in a single-arm plan; expected 1"
        )

    node = vector_nodes[0] if vector_nodes else None
    observed_ref = node.table_ref if node else None
    index_matches = observed_ref == expected_index_ref
    if node is not None and not index_matches:
        failures.append(
            f"vector search reads {observed_ref!r}, expected {expected_index_ref!r}"
        )

    target = node.target_count if node else None
    target_present = target is not None
    if node is not None and not target_present:
        failures.append("vector search node prints no `target count:` line")
    target_matches = expected_target_count is not None and target == expected_target_count
    if (
        node is not None
        and require_exact_target_count
        and expected_target_count is not None
        and not target_matches
    ):
        failures.append(f"target count is {target}, expected {expected_target_count}")

    spans = node.prefix_spans if node else None
    spans_ok = spans is not None and spans.strip().lower() not in _EMPTY_SPANS
    if node is not None and not spans_ok:
        failures.append(
            f"prefix spans are {spans!r} — the prefix was not constrained to specific values, "
            "so this arm is not searching the tree it claims to be searching"
        )

    full_scan = plan.has_full_scan
    if full_scan:
        offenders = ", ".join(n.node_type for n in plan.full_scan_nodes)
        failures.append(f"the plan contains a FULL SCAN ({offenders})")

    return PlanAssertion(
        arm_id=arm_id,
        expected_index_ref=expected_index_ref,
        vector_search_present=present,
        vector_search_count=len(vector_nodes),
        observed_index_ref=observed_ref,
        index_matches=index_matches,
        target_count=target,
        target_count_present=target_present,
        expected_target_count=expected_target_count,
        target_count_matches=target_matches,
        prefix_spans=spans,
        prefix_spans_nonempty=spans_ok,
        full_scan_present=full_scan,
        failures=tuple(failures),
    )


@dataclass(frozen=True, slots=True)
class UnionPlanAssertion:
    """The verdict over a whole ``UNION ALL`` plan.

    Vector-search nodes in a union plan cannot be matched back to individual arms — the plan
    prints no arm identifier — so this asserts what *is* provable: how many vector searches
    there are, which indexes they read, that every one of them carries non-empty prefix spans,
    and that nothing in the plan is a full scan.
    """

    expected_arm_count: int
    vector_search_count: int
    index_refs: tuple[str, ...]
    expected_index_refs: tuple[str, ...]
    all_prefix_spans_nonempty: bool
    full_scan_present: bool
    failures: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.failures


def assert_arm_set_plan(
    plan: ExplainPlan, *, expected_arm_count: int, expected_index_refs: Sequence[str]
) -> UnionPlanAssertion:
    """Assert the whole arm set's plan: one vector search per arm, none of them unconstrained."""
    failures: list[str] = []
    nodes = plan.vector_search_nodes
    if len(nodes) != expected_arm_count:
        failures.append(
            f"{len(nodes)} `vector search` nodes for {expected_arm_count} arms. Every arm "
            "must plan as its own constrained lookup; a missing one is an arm that became a "
            "scan or was folded away."
        )
    observed = tuple(n.table_ref or "<no table line>" for n in nodes)
    unexpected = sorted(set(observed) - set(expected_index_refs))
    if unexpected:
        failures.append(f"vector searches read unexpected indexes: {unexpected}")
    missing = sorted(set(expected_index_refs) - set(observed))
    if missing:
        failures.append(f"no vector search reads expected index(es): {missing}")
    spans_ok = True
    for node in nodes:
        spans = node.prefix_spans
        if spans is None or spans.strip().lower() in _EMPTY_SPANS:
            spans_ok = False
            failures.append(
                f"a vector search on {node.table_ref!r} has prefix spans {spans!r}; every arm "
                "must bind every prefix column to a specific value"
            )
    if plan.has_full_scan:
        failures.append(
            "the arm set's plan contains a FULL SCAN: "
            + ", ".join(n.node_type for n in plan.full_scan_nodes)
        )
    return UnionPlanAssertion(
        expected_arm_count=expected_arm_count,
        vector_search_count=len(nodes),
        index_refs=observed,
        expected_index_refs=tuple(expected_index_refs),
        all_prefix_spans_nonempty=spans_ok,
        full_scan_present=plan.has_full_scan,
        failures=tuple(failures),
    )
