# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""What a prefix-constrained vector table looks like, expressed as data.

Nothing in this package hard-codes a table, a column or an index name. A C-SPANN vector
index is only used when **every prefix column is constrained to a specific value**, so the
identity of the prefix columns is the single most load-bearing fact about a query this
package generates — and a fact that load-bearing belongs in an explicit, validated value
object rather than in a format string.

The deployment that consumes this substrate supplies two bindings: the scoped table (three
prefix columns: a site/tenant token, an archival scope, a facet) and the coarse sweep table
(one constant prefix column, deliberately one big unpartitioned tree). Both are
:class:`VectorTable`.

IDENTIFIER SAFETY IS NOT STYLE HERE. Every identifier is interpolated into SQL text without
quoting, because CockroachDB folds unquoted identifiers to lower case and the generated SQL
must be byte-comparable across runs for the plan digest to mean anything. The constructor
therefore refuses anything that is not a bare lower-case identifier, which makes the
interpolation safe by construction rather than by review.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

__all__ = [
    "IDENTIFIER_RE",
    "InvalidBinding",
    "VectorTable",
]

#: A bare, unquoted, lower-case SQL identifier. CockroachDB folds unquoted identifiers to
#: lower case; anything needing quotes is refused rather than quoted, so that the rendered
#: SQL is exactly the text a human would write.
IDENTIFIER_RE: Final = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")

#: The distance operators pgvector-compatible CockroachDB exposes. Restricted to a closed set
#: because the operator is interpolated into the `ORDER BY` that the vector index must serve,
#: and an operator that does not match the index's ops class silently loses the index.
_DISTANCE_OPERATORS: Final = frozenset({"<->", "<=>", "<#>"})


class InvalidBinding(ValueError):
    """A table binding that cannot be rendered into SQL safely, or at all."""


def _check_identifier(name: str, *, what: str) -> str:
    if not IDENTIFIER_RE.match(name):
        raise InvalidBinding(
            f"{what} {name!r} is not a bare lower-case SQL identifier. This package "
            "interpolates identifiers without quoting so that the generated statement is "
            "byte-stable; a name needing quotes is refused, not quoted."
        )
    return name


@dataclass(frozen=True, slots=True)
class VectorTable:
    """One vector-indexed table, and the columns the index prefix is built from.

    ``prefix_columns`` is ordered and must match the index declaration's prefix order. The
    order is not cosmetic: it is the order the spans are printed in by ``EXPLAIN``, and a
    binding whose order disagrees with the index is a binding whose generated arms will not
    be recognised as fully constrained.

    ``index`` is the index's bare name. ``EXPLAIN`` prints ``table@index`` with the table
    unqualified (documented example: ``table: items@items_customer_id_embedding_idx``), which
    is why :attr:`index_ref` omits the schema.
    """

    schema: str
    table: str
    index: str
    prefix_columns: tuple[str, ...]
    vector_column: str
    id_column: str
    dimensions: int
    distance_operator: str = "<=>"

    def __post_init__(self) -> None:
        _check_identifier(self.schema, what="schema")
        _check_identifier(self.table, what="table")
        _check_identifier(self.index, what="index")
        _check_identifier(self.vector_column, what="vector column")
        _check_identifier(self.id_column, what="id column")
        if not self.prefix_columns:
            raise InvalidBinding(
                f"{self.schema}.{self.table} declares no prefix columns. A vector index with "
                "no prefix cannot be scoped, and this package exists to scope one."
            )
        seen: set[str] = set()
        for column in self.prefix_columns:
            _check_identifier(column, what="prefix column")
            if column in seen:
                raise InvalidBinding(f"prefix column {column!r} is declared twice")
            seen.add(column)
        if self.vector_column in seen:
            raise InvalidBinding(
                f"{self.vector_column!r} is both the vector column and a prefix column"
            )
        if self.dimensions < 1:
            raise InvalidBinding(f"dimensions must be >= 1, got {self.dimensions}")
        if self.distance_operator not in _DISTANCE_OPERATORS:
            raise InvalidBinding(
                f"distance operator {self.distance_operator!r} is not one of "
                f"{sorted(_DISTANCE_OPERATORS)}. The operator must match the index's ops "
                "class or the index is silently not used."
            )

    @property
    def qualified_name(self) -> str:
        """``schema.table`` — what the ``FROM`` clause carries."""
        return f"{self.schema}.{self.table}"

    @property
    def index_ref(self) -> str:
        """``table@index`` — what ``EXPLAIN`` prints, unqualified, on its ``table:`` line."""
        return f"{self.table}@{self.index}"

    @property
    def prefix_arity(self) -> int:
        return len(self.prefix_columns)
