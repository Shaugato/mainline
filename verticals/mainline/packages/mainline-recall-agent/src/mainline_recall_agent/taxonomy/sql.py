# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The three writes this package performs, as parameterised statements.

Statement text and parameter tuples, and nothing else — no connection, no driver import,
no transaction management.  The caller owns the transaction because the caller knows what
else is in it: the LMB rows and the bond rows for one event belong in **one** transaction,
and a helper here that opened its own would make that impossible to arrange from outside.

Three deliberate omissions:

``cue_id`` is absent.
    ``mainline.event_cue.cue_id`` has ``DEFAULT gen_random_uuid()``.  Supplying it from the
    application would be a second identity authority for a row the sidecars reference by
    primary key.  (Contrast ``activity_node.scope_id``, which this package *does* supply —
    see :mod:`~mainline_recall_agent.taxonomy.models` for why the deviation is worth it
    there and not here.)

``tsv`` is absent.
    It is a ``STORED`` computed column over ``cue_text``.  Writing it would either fail or,
    worse, be silently accepted by some future column definition and give the lexical
    channel a tsvector that disagrees with the text beside it.

No ``ON CONFLICT`` anywhere.
    ``event_bond``'s primary key is ``(event_id, scope_id, taxonomy_ver)`` and its only
    other column is ``bond_basis``.  ``ON CONFLICT DO NOTHING`` would silently keep an
    older basis when a re-bond disagrees with it — a provenance downgrade with no
    record — and ``DO UPDATE`` would silently overwrite one.  A 23505 on a re-bond is
    information: someone bonded this event twice under one taxonomy version, and the
    correct response is to look, not to swallow.

Placeholders are ``%s`` (psycopg's paramstyle, which is what the repository uses).  Nothing
is interpolated into the SQL text: these writers sit downstream of document ingestion, so
their inputs are attacker-influenced by construction.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Final

from .models import ActivityNode, BondRow, CueRow

__all__ = [
    "INSERT_ACTIVITY_NODE",
    "INSERT_EVENT_BOND",
    "INSERT_EVENT_CUE",
    "activity_node_params",
    "bond_batch",
    "bond_params",
    "cue_batch",
    "cue_params",
]

INSERT_ACTIVITY_NODE: Final[str] = """
INSERT INTO mainline.activity_node
       (scope_id, site_id, level, parent_scope, label, activity_root,
        taxonomy_ver, induced_by, frozen)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
""".strip()

INSERT_EVENT_CUE: Final[str] = """
INSERT INTO mainline.event_cue
       (event_id, site_id, scope_id, scope_level, facet, taxonomy_ver,
        cue_text, source_span, is_derived, gen_model, prompt_version)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
""".strip()

INSERT_EVENT_BOND: Final[str] = """
INSERT INTO mainline.event_bond (event_id, scope_id, taxonomy_ver, bond_basis)
VALUES (%s, %s, %s, %s)
""".strip()


def activity_node_params(node: ActivityNode) -> tuple[Any, ...]:
    """Parameters for :data:`INSERT_ACTIVITY_NODE`, in declaration order."""
    return (
        node.scope_id,
        node.site_id,
        node.level,
        node.parent_scope,
        node.label,
        node.activity_root,
        node.taxonomy_ver,
        node.induced_by,
        node.frozen,
    )


def cue_params(row: CueRow) -> tuple[Any, ...]:
    """Parameters for :data:`INSERT_EVENT_CUE`, in declaration order.

    ``source_span`` is sent as a Python list so the driver adapts it to ``INT8[2]``; the
    column is nullable and a facet with no anchored span sends ``NULL`` rather than an
    empty array, because an empty array would claim a span of length zero exists.
    """
    return (
        row.event_id,
        row.site_id,
        row.scope_id,
        row.scope_level,
        row.facet,
        row.taxonomy_ver,
        row.cue_text,
        list(row.source_span) if row.source_span is not None else None,
        row.is_derived,
        row.gen_model,
        row.prompt_version,
    )


def bond_params(row: BondRow) -> tuple[Any, ...]:
    """Parameters for :data:`INSERT_EVENT_BOND`, in declaration order.

    ``scope_level`` is deliberately not sent: it is a convenience on
    :class:`~mainline_recall_agent.taxonomy.models.BondRow` for the writer's own closure
    assertions, and ``mainline.event_bond`` has no such column.  Sending it would be a
    schema drift that only shows up as a 42703 on first contact with a cluster.
    """
    return (row.event_id, row.scope_id, row.taxonomy_ver, row.bond_basis)


def cue_batch(rows: Sequence[CueRow]) -> list[tuple[Any, ...]]:
    """Parameter list for ``executemany(INSERT_EVENT_CUE, ...)``."""
    return [cue_params(row) for row in rows]


def bond_batch(rows: Sequence[BondRow]) -> list[tuple[Any, ...]]:
    """Parameter list for ``executemany(INSERT_EVENT_BOND, ...)``."""
    return [bond_params(row) for row in rows]
