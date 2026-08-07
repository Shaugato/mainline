# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The tuple-``IN`` form — **NOT SHIPPED**. A characterisation-test generator only.

CockroachDB documents filtering a vector index on multiple prefix values with tuple ``IN``::

    WHERE (department_id, category_id) IN ((100, 200), (300, 400))

It is supported, and it is still not what this domain ships. Three reasons, none of which it
can satisfy:

1. **The arms are not homogeneous.** Each carries its own ``k``, its own fusion weight — a
   file-level ``recurrence_test`` hit outweighs a fonds-level ``narrative`` hit — and its own
   facet-specific query vector. One tuple-``IN`` returns one undifferentiated top-k and
   throws that structure away. There is no arrangement of a single ``IN`` list that recovers
   it.
2. **``optimizer_span_limit`` is a silent cliff.** *"If a single IN set has more items than
   this limit, that IN set will not be used to build a constrained index scan"*, and for a
   composite index *"if the cross product of two or more IN sets would produce more spans
   than this limit, then only a prefix of the IN sets will be used"*. A growing arm set
   crosses that threshold and degrades to a scan with no error and no log line. **In this
   product a silently unused index is a safety defect, not a performance regression.**
3. **Whether tuple-``IN`` with ``ORDER BY distance LIMIT k`` yields a global top-k or a
   top-k per tree is undocumented.** Per-arm ``LIMIT`` has no such ambiguity, and per-arm
   ``EXPLAIN`` is assertable — which matters because the audit claim *"the vector index was
   used"* is asserted from ``EXPLAIN`` output.

So the form lives here, generated but never issued on the gate path, and exercised nightly at
span counts below and above the runtime value of ``optimizer_span_limit`` against brute force
on a fixed fixture. **It is expected to change across versions. That is its purpose.** The day
it stops changing, or the day its results converge with the shipped form at every span count,
is the day the decision above can be revisited on evidence.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from .binding import VectorTable
from .spec import ArmSpec, PrefixValue, SqlForm
from .sql import RenderedSql, render_prefix_literal, render_vector_literal

__all__ = [
    "SHIPPED",
    "SPAN_LIMIT_SETTING",
    "TupleInProbe",
    "brute_force_sql",
    "from_arms",
    "span_count",
    "tuple_in_sql",
]

#: Read by the characterisation test, and by anyone grepping this repository for the answer
#: to "do you ship tuple-IN?". The answer is no, and it is a constant rather than a comment
#: so that a test can assert it.
SHIPPED: Final = False

#: The session setting whose value decides where the cliff is. **Read it at runtime with
#: ``SHOW optimizer_span_limit``. Never assume the default** — it shipped in v25.4 and a
#: characterisation test that assumed a value would be characterising its own assumption.
SPAN_LIMIT_SETTING: Final = "optimizer_span_limit"


@dataclass(frozen=True, slots=True)
class TupleInProbe:
    """One tuple-``IN`` probe: the prefix tuples, the query vector, and the global ``k``.

    Note what is *absent* compared with an arm set: no per-tuple ``k``, no per-tuple weight,
    no per-tuple vector. Their absence is the first of the three objections, made visible in
    the type rather than argued in prose.
    """

    table: VectorTable
    tuples: tuple[tuple[PrefixValue, ...], ...]
    query_vector: tuple[float, ...]
    k: int

    def __post_init__(self) -> None:
        if not self.tuples:
            raise ValueError("a tuple-IN probe with no tuples constrains nothing")
        arity = self.table.prefix_arity
        for row in self.tuples:
            if len(row) != arity:
                raise ValueError(
                    f"tuple {row!r} has arity {len(row)}; {self.table.index_ref} declares "
                    f"{arity} prefix columns and a short tuple leaves one unconstrained"
                )
        if len(self.query_vector) != self.table.dimensions:
            raise ValueError(
                f"probe carries a {len(self.query_vector)}-dimension vector against a "
                f"{self.table.dimensions}-dimension column"
            )

    @property
    def span_count(self) -> int:
        """How many spans this probe asks the optimizer to build — one per distinct tuple."""
        return len(set(self.tuples))


def span_count(probe: TupleInProbe) -> int:
    return probe.span_count


def from_arms(arms: Sequence[ArmSpec], *, k: int | None = None) -> TupleInProbe:
    """Build the tuple-``IN`` equivalent of an arm set, for side-by-side characterisation.

    The equivalence is deliberately lossy and the loss is the point: every arm's ``k``,
    weight and facet-specific vector collapses into one ``k`` and one vector. This function
    takes the **first** arm's vector and refuses when the arms do not share one, because
    silently picking one facet's query to stand for four would make the comparison flattering
    rather than informative.
    """
    if not arms:
        raise ValueError("no arms to convert")
    table = arms[0].table
    vectors = {arm.query_vector for arm in arms}
    if len(vectors) != 1:
        raise ValueError(
            f"the {len(arms)} arms carry {len(vectors)} distinct query vectors. A tuple-IN "
            "probe has exactly one, so there is no honest single probe for this arm set — "
            "which is objection 1 in the module docstring, arriving as an exception."
        )
    if any(arm.table != table for arm in arms):
        raise ValueError("arms span more than one table; a tuple-IN probe covers one index")
    return TupleInProbe(
        table=table,
        tuples=tuple(arm.prefix_values for arm in arms),
        query_vector=arms[0].query_vector,
        k=k if k is not None else max(arm.k for arm in arms),
    )


def tuple_in_sql(
    probe: TupleInProbe, *, form: SqlForm = SqlForm.LITERAL, alias: str = "e"
) -> RenderedSql:
    """Render the tuple-``IN`` form. Characterisation only; never issued on the gate path."""
    if form is SqlForm.EXECUTE:
        raise ValueError(
            "the tuple-IN form is a characterisation probe, not an execution path; it renders "
            "as literals so that its EXPLAIN can be read directly"
        )
    table = probe.table
    columns = ", ".join(f"{alias}.{column}" for column in table.prefix_columns)
    tuples = ", ".join(
        "(" + ", ".join(render_prefix_literal(value) for value in row) + ")"
        for row in probe.tuples
    )
    vector_sql = f"'{render_vector_literal(probe.query_vector)}'::VECTOR({table.dimensions})"
    distance = f"{alias}.{table.vector_column} {table.distance_operator} {vector_sql}"
    projection = f"{alias}.{table.id_column} AS cue_id"
    if form is not SqlForm.EXPLAIN_MCP:
        projection += f",\n       {distance} AS dist"
    text = (
        f"SELECT {projection}"
        f"\n  FROM {table.qualified_name} AS {alias}"
        f"\n WHERE ({columns}) IN ({tuples})"
        f"\n ORDER BY {distance}"
        f"\n LIMIT {probe.k}"
    )
    return RenderedSql(text=text, params=())


def brute_force_sql(probe: TupleInProbe, *, alias: str = "e") -> RenderedSql:
    """The exact answer, computed without the index — the characterisation test's oracle.

    ``FORCE_INDEX=[1]`` names the primary index **by index ID**, not by name: CockroachDB
    renames the primary index across versions (``primary`` → ``<table>_pkey``) and an oracle
    that stopped forcing the scan because a name changed would silently start comparing the
    approximate answer against itself.
    """
    table = probe.table
    columns = ", ".join(f"{alias}.{column}" for column in table.prefix_columns)
    tuples = ", ".join(
        "(" + ", ".join(render_prefix_literal(value) for value in row) + ")"
        for row in probe.tuples
    )
    vector_sql = f"'{render_vector_literal(probe.query_vector)}'::VECTOR({table.dimensions})"
    distance = f"{alias}.{table.vector_column} {table.distance_operator} {vector_sql}"
    text = (
        f"SELECT {alias}.{table.id_column} AS cue_id,\n       {distance} AS dist"
        f"\n  FROM {table.qualified_name}@{{FORCE_INDEX=[1]}} AS {alias}"
        f"\n WHERE ({columns}) IN ({tuples})"
        f"\n ORDER BY dist"
        f"\n LIMIT {probe.k}"
    )
    return RenderedSql(text=text, params=())
