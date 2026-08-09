# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""Statements and parameters — this package's entire contact with the database.

There is no driver here and there is no credential here. :func:`insert_blame_edge`
returns a statement and a parameter tuple; the caller holds the SQL role and the
transaction. That separation is what ``mainline-boundary``'s E3 SBOM scan reads, and it
is why a component that has just finished reading a hostile PDF cannot also be the
component that wrote a row.

Three things about the statements below are deliberate:

* **``state`` is written as a literal ``'provisional'``, not bound from a parameter.**
  A parameter is a value a caller chooses. A literal is a value nobody chooses. The DDL
  constraint ``inference_never_blocks`` already refuses ``active`` on this basis; making
  the statement itself incapable of expressing it means the constraint is a second
  defence rather than the only one.
* **``basis`` is likewise a literal.** The same argument, and it also keeps this module
  from ever becoming the place somebody writes an ``asserted_document`` edge without a
  quote.
* **``p_link`` is rendered from integer thousandths through :class:`~decimal.Decimal`.**
  The column is ``FLOAT8``, but nothing in our process ever holds the value as a Python
  float, so nothing that gets hashed can depend on IEEE-754 formatting (ADR 0042). The
  conversion happens once, in one line, at the wire.

The read statements are here too, as constants rather than as functions, because the
resolver deliberately takes rows rather than a connection: the SQL a caller runs to feed
:func:`mainline_cartographer.resolve.resolve_blame_pointer` should be reviewable in one
place next to the code that consumes its output.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Any

from .errors import InferenceActivated
from .types import BlameBasis, BlameState

if TYPE_CHECKING:
    from .types import ProvisionalBlameEdge

__all__ = [
    "CLAUSE_BLAME_CLOSURE_SQL",
    "CLAUSE_BLAME_EDGES_SQL",
    "INSERT_BLAME_EDGE_SQL",
    "P_LINK_SCALE",
    "ancestor_events_sql",
    "insert_blame_edge",
]

#: ``p_link_milli`` is thousandths, so the wire value is the integer scaled by 10**-3.
P_LINK_SCALE = -3

#: The projection the gate reads, for one clause version. ``clause_blame_current``
#: already takes ``max(closure_gen)``, which is why no call site here does.
CLAUSE_BLAME_CLOSURE_SQL = """
SELECT clause_uuid,
       encode(as_of_commit, 'hex') AS as_of_commit,
       closure_gen,
       site_id,
       ancestor_events,
       ancestor_count,
       max_severity,
       virulence,
       depth,
       truncated,
       computed_by,
       projector_ver
  FROM mainline.clause_blame_current
 WHERE clause_uuid = $1
   AND as_of_commit = decode($2, 'hex')
"""

#: Every edge on the clause, at every basis and state. The resolver uses these only to
#: assert the inference law and to report what was correctly excluded — the ancestry
#: itself comes from the closure, never from a walk done here.
CLAUSE_BLAME_EDGES_SQL = """
SELECT event_id, clause_uuid, basis, state
  FROM mainline.blame_edge
 WHERE clause_uuid = $1
   AND commit_id = decode($2, 'hex')
"""

#: The one row this package writes. `state` and `basis` are literals: see the module
#: docstring. `ON CONFLICT DO NOTHING` on the natural key makes a redelivered changefeed
#: message idempotent — the real idempotency is always a database primary key.
INSERT_BLAME_EDGE_SQL = """
INSERT INTO mainline.blame_edge (
    event_id, clause_uuid, basis, state, site_id, commit_id,
    p_link, features, attribution,
    evidence_doc_id, evidence_span, evidence_quote_sha256,
    provisional_until, model_id, prompt_version
) VALUES (
    $1, $2, 'inferred_semantic', 'provisional', $3, decode($4, 'hex'),
    $5, $6, $7,
    $8, ARRAY[$9::INT8, $10::INT8], decode($11, 'hex'),
    $12, $13, $14
)
ON CONFLICT (clause_uuid, event_id, basis) DO NOTHING
"""


def ancestor_events_sql() -> str:
    """Return the index-accelerated *"which clauses inherit incident E?"* lookup.

    One inverted-index lookup on ``(site_id, ancestor_events)``. It is a function rather
    than a constant only so that the comment travels with the caller who asks for it:
    ``@>`` is index-accelerated on a multi-column GIN **provided the inverted column is
    last**, which is why the index is declared in that order.
    """
    return """
SELECT clause_uuid, closure_gen, max_severity, virulence, truncated
  FROM mainline.clause_blame_current
 WHERE site_id = $1
   AND ancestor_events @> ARRAY[$2::UUID]
"""


def insert_blame_edge(edge: ProvisionalBlameEdge) -> tuple[str, tuple[Any, ...]]:
    """Return the statement and parameters for one provisional inferred edge.

    Raises:
        InferenceActivated: if the edge is not inferred-and-provisional. The type
            already refuses to be built any other way; this is the assertion that holds
            if somebody constructs one through ``dataclasses.replace``.
    """
    if edge.basis is not BlameBasis.INFERRED_SEMANTIC or edge.state is not BlameState.PROVISIONAL:
        raise InferenceActivated(
            f"refusing to emit an INSERT for a blame_edge with basis={edge.basis!s} and "
            f"state={edge.state!s}"
        )
    start, end = edge.evidence_span
    params: tuple[Any, ...] = (
        edge.event_id,
        edge.clause_uuid,
        edge.site_id,
        edge.commit_id,
        # Exact: Decimal(500).scaleb(-3) is 0.500, with no binary rounding anywhere in
        # our process. The driver widens it to FLOAT8 at the wire and nothing we hash
        # ever holds the widened value.
        Decimal(edge.p_link_milli).scaleb(P_LINK_SCALE),
        dict(edge.features),
        edge.attribution,
        edge.evidence_doc_id,
        start,
        end,
        edge.evidence_quote_sha256,
        edge.provisional_until,
        edge.model_id,
        edge.prompt_version,
    )
    return INSERT_BLAME_EDGE_SQL, params
