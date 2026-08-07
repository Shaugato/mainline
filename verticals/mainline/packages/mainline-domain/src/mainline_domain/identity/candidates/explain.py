# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Turning ``EXPLAIN`` output into an assertion about an S4 arm.

A vector index in CockroachDB is used **only** when every prefix column is
constrained to a specific value.  That sentence is the load-bearing platform
fact behind :mod:`.semantic`, and the only way to know it held for a particular
statement is to read the plan.

The documented fragment that proves it::

    • vector search
      table: clause_embedding@ce_ann
      target count: 8
      prefix spans: [/1/'maintenance' - /1/'maintenance']

Four independent things must hold, and the fourth is the one that is easy to
forget:

1. a node of type ``vector search`` exists — otherwise the optimiser did not
   use the index at all;
2. it reads the expected ``table@index``;
3. its ``prefix spans:`` line is present **and non-empty** — an absent or empty
   span list is the documented condition under which the vector index is *not*
   used, and it is what an accidental ``IN (...)`` or an unbound prefix looks
   like in plan text;
4. **no node anywhere in the plan is a full scan.**  A plan can contain a
   vector search node and still be wrong: a predicate the optimiser could not
   push into the prefix reappears as a scan beside it, and the arm that looked
   proven is the arm that reads the whole table.

All four are reported separately, because *which* one failed is the entire
diagnostic value and a boolean throws it away.

**What this does not prove, stated plainly.**  That a plan was chosen says
nothing about what the executor did, and nothing about whether C-SPANN's
approximate search returned the neighbour that mattered.  Plan text is one
layer.  The second is behavioural — work that grows sublinearly as the corpus
doubles — because *a silently unused index scales linearly regardless of how
the plan text is formatted*.  Neither layer substitutes for the other, and this
package ships both.

This module is deliberately standalone.  ``packages/trappoint-recall`` has a
richer plan parser; it belongs to the recall lead, it is Apache-2.0 substrate,
and the event-cue arms are its subject.  Importing it here would couple two
domains' release cadences for the sake of ~120 lines, so these ~120 lines are
here instead.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final

__all__ = [
    "EMPTY_SPAN_RENDERINGS",
    "FULL_SCAN_MARKER",
    "VECTOR_SEARCH_NODE",
    "ArmPlanAssertion",
    "PlanNode",
    "assert_arm_plan",
    "assert_arm_set_plans",
    "parse_plan",
]

VECTOR_SEARCH_NODE: Final[str] = "vector search"
"""The node type CockroachDB prints for a prefix-constrained ANN lookup."""

FULL_SCAN_MARKER: Final[str] = "FULL SCAN"
"""What a scan node prints on its ``spans:`` line when it reads everything."""

EMPTY_SPAN_RENDERINGS: Final[frozenset[str]] = frozenset({"", "[]", "-", "none", "full span"})
"""Renderings of a span list that mean *the prefix was not constrained*.

Compared case-insensitively after stripping.  Anything not in this set counts
as a constrained prefix, which is the fail-*loud* direction: an unrecognised
rendering does not silently pass as "constrained", it is reported by the
``expected_index`` check or by the full-scan check instead.
"""

_BULLET: Final[str] = "•"
_GLYPHS: Final[str] = "│├└─┌┐┘┴┬┼| `+-"
_FIELD_RE: Final[re.Pattern[str]] = re.compile(
    r"^(?P<key>[A-Za-z][A-Za-z0-9 _-]*?)\s*:\s*(?P<value>.*)$"
)


@dataclass(frozen=True, slots=True)
class PlanNode:
    """One plan node: its type and its ``key: value`` fields."""

    node_type: str
    fields: Mapping[str, str]

    @property
    def table_ref(self) -> str | None:
        """The ``table@index`` string exactly as printed, or ``None``."""
        return self.fields.get("table")

    @property
    def prefix_spans(self) -> str | None:
        """The ``prefix spans:`` value exactly as printed, or ``None`` if absent."""
        return self.fields.get("prefix spans")

    @property
    def has_constrained_prefix(self) -> bool:
        """``True`` iff ``prefix spans`` is present and is not an empty rendering."""
        spans = self.prefix_spans
        if spans is None:
            return False
        return spans.strip().lower() not in EMPTY_SPAN_RENDERINGS

    @property
    def is_full_scan(self) -> bool:
        """``True`` iff any field on this node announces a full scan."""
        return any(FULL_SCAN_MARKER in value.upper() for value in self.fields.values())


def _strip(line: str) -> str:
    return line.lstrip(_GLYPHS).strip()


def parse_plan(text: str) -> tuple[PlanNode, ...]:
    """Parse ``EXPLAIN`` outline text into nodes.

    Tolerant of the tree-drawing glyphs and of the leading preamble, because
    both vary between versions and neither carries the facts under assertion.
    Lines before the first ``•`` are preamble and are ignored; a ``key: value``
    line attaches to the most recent node.
    """
    nodes: list[PlanNode] = []
    current_type: str | None = None
    current_fields: dict[str, str] = {}

    for raw in text.splitlines():
        stripped = _strip(raw)
        if not stripped:
            continue
        if stripped.startswith(_BULLET):
            if current_type is not None:
                nodes.append(PlanNode(current_type, dict(current_fields)))
            current_type = stripped[len(_BULLET) :].strip()
            current_fields = {}
            continue
        if current_type is None:
            continue
        match = _FIELD_RE.match(stripped)
        if match is not None:
            current_fields[match.group("key").strip().lower()] = match.group("value").strip()

    if current_type is not None:
        nodes.append(PlanNode(current_type, dict(current_fields)))
    return tuple(nodes)


@dataclass(frozen=True, slots=True)
class ArmPlanAssertion:
    """The four checks, kept apart, plus the message an assertion should carry."""

    ok: bool
    has_vector_search: bool
    reads_expected_index: bool
    prefix_constrained: bool
    no_full_scan: bool
    failures: tuple[str, ...]
    nodes: tuple[PlanNode, ...]

    def message(self) -> str:
        """Render a multi-line explanation naming every check that failed."""
        if self.ok:
            return "arm plan ok: prefix-constrained vector search, no full scan"
        return "arm plan REFUSED:\n" + "\n".join(f"  - {f}" for f in self.failures)


def assert_arm_plan(
    plan_text: str,
    *,
    expected_index: str = "ce_ann",
    expected_table: str = "clause_embedding",
    raises: bool = True,
) -> ArmPlanAssertion:
    """Assert one arm's plan.  Returns the breakdown; raises by default.

    :param expected_index: the index name the arm must read.  ``ce_ann`` is the
        inline ``VECTOR INDEX`` on ``mainline.clause_embedding`` (ARCHITECTURE.md
        §5.3).
    :param raises: ``False`` returns the breakdown instead of raising, which is
        what a test asserting the *failure* modes needs.

    :raises AssertionError: when any of the four checks fails and ``raises``.
    """
    nodes = parse_plan(plan_text)
    vector_nodes = tuple(n for n in nodes if n.node_type == VECTOR_SEARCH_NODE)
    full_scans = tuple(n for n in nodes if n.is_full_scan)
    failures: list[str] = []

    has_vector_search = bool(vector_nodes)
    if not has_vector_search:
        failures.append(
            "no `vector search` node in the plan — the optimiser did not use the vector "
            "index, which is what an unconstrained prefix looks like from here"
        )

    reads_expected_index = False
    prefix_constrained = False
    if has_vector_search:
        if len(vector_nodes) != 1:
            failures.append(
                f"{len(vector_nodes)} `vector search` nodes in a single-arm plan; expected "
                f"exactly 1 — an arm is one fully-constrained ANN query"
            )
        node = vector_nodes[0]
        ref = node.table_ref or ""
        reads_expected_index = ref.endswith(f"@{expected_index}") and expected_table in ref
        if not reads_expected_index:
            failures.append(
                f"vector search reads {ref!r}; expected a table ref containing "
                f"{expected_table!r} and ending with '@{expected_index}'"
            )
        prefix_constrained = node.has_constrained_prefix
        if not prefix_constrained:
            failures.append(
                f"prefix spans are {node.prefix_spans!r} — the prefix was not constrained to "
                f"specific values, which is the documented condition under which the vector "
                f"index is NOT used"
            )

    no_full_scan = not full_scans
    if full_scans:
        offenders = ", ".join(sorted({n.node_type for n in full_scans}))
        failures.append(
            f"the plan contains a FULL SCAN ({offenders}) — a vector search node beside a "
            f"full scan is an arm that reads the whole table"
        )

    result = ArmPlanAssertion(
        ok=not failures,
        has_vector_search=has_vector_search,
        reads_expected_index=reads_expected_index,
        prefix_constrained=prefix_constrained,
        no_full_scan=no_full_scan,
        failures=tuple(failures),
        nodes=nodes,
    )
    if raises and not result.ok:
        raise AssertionError(result.message())
    return result


def assert_arm_set_plans(
    plans: Sequence[str],
    *,
    expected_index: str = "ce_ann",
    expected_table: str = "clause_embedding",
) -> tuple[ArmPlanAssertion, ...]:
    """Assert every arm in a fan-out.  All arms are checked before raising.

    Checking all of them first matters: a fan-out where arm 7 of 12 lost its
    prefix constraint is a very different report from "the first arm failed",
    and stopping at the first failure hides how far the problem spread.
    """
    results = tuple(
        assert_arm_plan(
            text, expected_index=expected_index, expected_table=expected_table, raises=False
        )
        for text in plans
    )
    bad = [(i, r) for i, r in enumerate(results) if not r.ok]
    if bad:
        detail = "\n".join(f"arm {i}: {r.message()}" for i, r in bad)
        raise AssertionError(f"{len(bad)} of {len(results)} arms refused:\n{detail}")
    return results
