# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""Where the archival path comes from — and where it must never come from.

The Level-Materialised Bond writer and the bond writer both need the ancestry of a node.
Neither of them accepts it as an argument.  They take a :class:`ActivityNodeSource` and
resolve the chain themselves, because the alternative is a caller handing in a list of
scope ids, and a caller that chooses the scope ids chooses the K-means trees.

This is the application-side reading of TRAPPOINT P2 — *projections are enforced, never
trusted*.  In the kernel the same idea is a ``BEFORE INSERT`` trigger that overwrites
``event_cue_embedding``'s prefix columns from the parent ``event_cue`` row and ``RAISE``s
when it is absent (recall.md D1).  Here, one hop earlier, the writer derives the prefix
set from ``mainline.activity_node`` and raises when the table does not corroborate it.
Both layers are needed: the trigger stops a hostile inserter, this stops an honest bug.

Two implementations ship.  :class:`InMemoryNodeSource` is the one tests and the fixture
corpus use.  :class:`SqlNodeSource` runs the two obvious queries against any DB-API
connection whose ``execute`` returns a cursor — psycopg 3 is what the repository uses, but
nothing here imports it, so this module has no database dependency and no way to acquire
one implicitly.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any, Final, Protocol, runtime_checkable

from .errors import ArchivalPathError
from .models import LEVEL_FONDS, ActivityNode, ArchivalPath, TaxonomySnapshot

__all__ = [
    "SELECT_ANCESTORS",
    "SELECT_NODE",
    "ActivityNodeSource",
    "InMemoryNodeSource",
    "SqlNodeSource",
    "resolve_path",
]

#: Guard against a cycle in ``parent_scope``.  The table permits one (a self-referential FK
#: cannot forbid it), levels are capped at 3, and an unbounded walk on corrupt data is a
#: hang rather than an error.
_MAX_WALK: Final[int] = 8


@runtime_checkable
class ActivityNodeSource(Protocol):
    """Read-only access to ``mainline.activity_node``."""

    def get(self, scope_id: str) -> ActivityNode | None: ...


def resolve_path(source: ActivityNodeSource, scope_id: str) -> ArchivalPath:
    """Walk ``scope_id`` up to its fonds and return the validated path.

    Every failure mode is an exception, never a shorter path.  A truncated path is the
    dangerous outcome: it looks like a level-1-only event, produces fewer cue rows and
    fewer bonds, and nothing downstream can tell the difference between "this event has no
    file-level classification" and "this event's file-level node could not be read".
    """
    chain: list[ActivityNode] = []
    seen: set[str] = set()
    cursor: str | None = scope_id
    while cursor is not None:
        if cursor in seen:
            raise ArchivalPathError(
                "cycle in activity_node.parent_scope", scope_id=cursor, walked=len(chain)
            )
        if len(chain) >= _MAX_WALK:
            raise ArchivalPathError(
                "ancestry walk exceeded the depth bound; activity_node.level is capped at 3 "
                "so anything deeper is corrupt parentage",
                scope_id=scope_id,
                walked=len(chain),
            )
        seen.add(cursor)
        node = source.get(cursor)
        if node is None:
            raise ArchivalPathError(
                "activity_node row is missing on the ancestry chain; the writer refuses to "
                "guess a prefix, because a guessed prefix files the cue into a tree no arm "
                "will ever bind",
                missing_scope_id=cursor,
                requested=scope_id,
            )
        chain.append(node)
        cursor = node.parent_scope
    path = ArchivalPath(tuple(reversed(chain)))
    if path.fonds.level != LEVEL_FONDS:  # pragma: no cover - ArchivalPath already refuses
        raise ArchivalPathError("resolved chain does not terminate at a fonds")
    return path


class InMemoryNodeSource:
    """An :class:`ActivityNodeSource` over a fixed set of nodes.

    Used by the unit suite and by the fixture-corpus pipeline.  It is a real
    implementation, not a mock: it answers from a dict and returns ``None`` for an unknown
    scope, which is exactly what makes the "missing ancestor" refusal testable without a
    cluster.
    """

    def __init__(self, nodes: Iterable[ActivityNode]) -> None:
        self._nodes: dict[str, ActivityNode] = {node.scope_id: node for node in nodes}

    @classmethod
    def from_snapshot(cls, snapshot: TaxonomySnapshot) -> InMemoryNodeSource:
        return cls(snapshot.nodes)

    def __len__(self) -> int:
        return len(self._nodes)

    def get(self, scope_id: str) -> ActivityNode | None:
        return self._nodes.get(scope_id)

    def all_nodes(self) -> tuple[ActivityNode, ...]:
        return tuple(self._nodes.values())


SELECT_NODE: Final[str] = """
SELECT scope_id::STRING, site_id::STRING, level, parent_scope::STRING, label,
       activity_root, taxonomy_ver, induced_by, frozen
  FROM mainline.activity_node
 WHERE scope_id = %s
""".strip()

SELECT_ANCESTORS: Final[str] = """
SELECT scope_id::STRING, site_id::STRING, level, parent_scope::STRING, label,
       activity_root, taxonomy_ver, induced_by, frozen
  FROM mainline.activity_node
 WHERE site_id = %s AND taxonomy_ver = %s AND activity_root = %s
 ORDER BY level
""".strip()


def _row_to_node(row: Sequence[Any]) -> ActivityNode:
    return ActivityNode(
        scope_id=str(row[0]),
        site_id=str(row[1]),
        level=int(row[2]),
        parent_scope=str(row[3]) if row[3] is not None else None,
        label=str(row[4]),
        activity_root=str(row[5]),
        taxonomy_ver=int(row[6]),
        induced_by=str(row[7]),
        frozen=bool(row[8]),
    )


class SqlNodeSource:
    """An :class:`ActivityNodeSource` over a live ``mainline.activity_node``.

    Duck-typed on purpose: ``connection.execute(sql, params)`` returning something with
    ``fetchone()`` is the whole contract.  psycopg 3 satisfies it, and this package
    declares no database dependency — the recall agent's providers run offline and adding
    a driver import here would make ``import mainline_recall_agent.taxonomy`` fail on a
    machine that has no cluster and never needed one.

    Statements are parameterised.  No identifier or value is ever interpolated into the
    SQL text: this reader is reachable from an ingest path whose input is a document.

    Unverified on this machine: no CockroachDB instance is reachable here, so these two
    statements have not been executed against a real cluster.  The integration lane in
    ``tests/integration/recall_schema`` is the place that proves it, and it is skipped —
    with a reason — until migrations 0032/0033 (``activity_node``, ``event``) land.
    """

    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def get(self, scope_id: str) -> ActivityNode | None:
        cursor = self._connection.execute(SELECT_NODE, (scope_id,))
        row = cursor.fetchone()
        if row is None:
            return None
        return _row_to_node(row)

    def fonds_roots(
        self, *, site_id: str, taxonomy_ver: int, activity_root: str
    ) -> tuple[ActivityNode, ...]:
        """Every node under one level-1 code, level-ordered.  Used by the bond backfill."""
        cursor = self._connection.execute(SELECT_ANCESTORS, (site_id, taxonomy_ver, activity_root))
        return tuple(_row_to_node(row) for row in cursor.fetchall())
