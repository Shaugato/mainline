# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""Channels A and B — the deterministic spine, and the only part that may never degrade.

**Channel A, deterministic ancestry.** For each clause the permit cites, the active blame
closure (`mainline.clause_blame_current`, the `DISTINCT ON` view over the highest
`closure_gen`) holds `ancestor_events`. Each such event is admitted when one of its
`control_failure.control_class` values intersects the clause's CAT control class. No
threshold, no calibration, no rerank: graph truth. `control_delta in (weaken, remove)` on a
clause whose ancestry holds severity >= 4 is the headline claim of the whole product, and it
resolves to a join.

**Channel B, the bonded set.** Every severity-5 event bonded to the permit's activity node or
*any ancestor of it*, admitted unconditionally. This is where *"a fatality never decays"*
lives — structurally, as `bonded_fatalities_all_blocking` (MI16), not as a score hack. The
walk is an explicit recursive CTE with a depth bound, because CockroachDB has no `CYCLE`
clause and an unbounded walk inside a safety gate is a latent hang.

Neither channel touches a model, and that is the property the degradation ladder rests on: a
run with Bedrock throttled, a model refusal or a guardrail block completes on A+B alone,
records `arms_degraded = true`, and **still blocks the merge**.

The GIN probe, and why a redundant query is not redundancy
-----------------------------------------------------------
:data:`ANCESTRY_CONTAINMENT_SQL` re-derives, through the inverted index
`cbc_anc (site_id, ancestor_events)`, the containment that :data:`ANCESTRY_SQL` already read
out of the array column. Running both is deliberate. The first reads the closure row we
selected; the second asks the index *which clauses inherit this event* — ARCHITECTURE 5.4's
own query, verbatim — and a candidate that the index cannot confirm is not graph truth and is
refused rather than admitted. That is P2 applied to a channel: **a fact the gate depends on is
enforced, never trusted**, including when the source of the fact is us.

The probe is one statement per admitted event because a C-SPANN-adjacent inverted lookup wants
its prefix column bound to a single value and its `@>` operand to be a constant array. A
handful of statements for a handful of admitted precursors is the correct trade; the arm
generator makes the same trade for the same reason.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final
from uuid import UUID

from mainline_recall_agent.run.session import SqlSession

__all__ = [
    "ANCESTRY_CONTAINMENT_SQL",
    "ANCESTRY_SQL",
    "BONDED_SEV5_SQL",
    "CITED_CLAUSES_SQL",
    "MAX_SCOPE_WALK_DEPTH",
    "AncestryHit",
    "BondedHit",
    "CitedClause",
    "channel_a",
    "channel_b",
    "cited_clauses",
]

#: The archival taxonomy is three levels (fonds, series, file), so four hops is already one
#: more than the tree can hold. The bound exists because CockroachDB has no `CYCLE` clause and
#: a mis-parented `activity_node` would otherwise loop inside the gate's own retrieval.
MAX_SCOPE_WALK_DEPTH: Final = 8

CITED_CLAUSES_SQL: Final = """
SELECT pc.clause_uuid,
       encode(pc.commit_id, 'hex'),
       pc.relation
  FROM mainline.permit_clause pc
 WHERE pc.permit_id = $1
 ORDER BY pc.clause_uuid, pc.relation
""".strip()

ANCESTRY_SQL: Final = """
WITH cat AS (
  SELECT (spec->>'clause_uuid')::UUID          AS clause_uuid,
         decode(spec->>'commit_id', 'hex')     AS commit_id,
         cc                                    AS control_class
    FROM jsonb_array_elements($2::JSONB) AS spec
    CROSS JOIN LATERAL jsonb_array_elements_text(spec->'control_classes') AS cc
),
scope AS (
  SELECT DISTINCT clause_uuid, commit_id FROM cat
),
closure AS (
  SELECT s.clause_uuid,
         s.commit_id,
         cbc.closure_gen,
         cbc.max_severity,
         cbc.truncated,
         cbc.ancestor_events
    FROM scope s
    JOIN mainline.clause_blame_current cbc
      ON cbc.clause_uuid = s.clause_uuid
     AND cbc.as_of_commit = s.commit_id
   WHERE cbc.site_id = $1
),
anc AS (
  SELECT c.clause_uuid,
         c.commit_id,
         c.closure_gen,
         c.max_severity,
         c.truncated,
         ae AS event_id
    FROM closure c
    CROSS JOIN LATERAL unnest(c.ancestor_events) AS ae
)
SELECT a.event_id,
       a.clause_uuid,
       encode(a.commit_id, 'hex'),
       a.closure_gen,
       a.max_severity,
       a.truncated,
       ev.severity_gate,
       ev.title,
       ev.occurred_at,
       array_agg(DISTINCT cf.control_class),
       array_agg(DISTINCT cf.failure_mode),
       array_agg(DISTINCT cf.hazard_energy)
  FROM anc a
  JOIN mainline.event ev
    ON ev.event_id = a.event_id
   AND ev.site_id = $1
  JOIN mainline.control_failure cf
    ON cf.event_id = a.event_id
  JOIN cat
    ON cat.clause_uuid = a.clause_uuid
   AND cat.commit_id = a.commit_id
   AND cat.control_class = cf.control_class
 GROUP BY a.event_id, a.clause_uuid, a.commit_id, a.closure_gen, a.max_severity,
          a.truncated, ev.severity_gate, ev.title, ev.occurred_at
 ORDER BY ev.severity_gate DESC, ev.occurred_at DESC, a.event_id
""".strip()

#: ARCHITECTURE 5.4's own containment query: *"which clauses inherit incident E?"*, one
#: index lookup against the inverted index `cbc_anc (site_id, ancestor_events)`.
ANCESTRY_CONTAINMENT_SQL: Final = """
SELECT DISTINCT cbc.clause_uuid,
       encode(cbc.as_of_commit, 'hex')
  FROM mainline.clause_blame_current cbc
 WHERE cbc.site_id = $1
   AND cbc.ancestor_events @> ARRAY[$2::UUID]
""".strip()

BONDED_SEV5_SQL: Final = """
WITH RECURSIVE up(scope_id, depth) AS (
    SELECT an.scope_id, 0
      FROM mainline.activity_node an
     WHERE an.scope_id = $2
       AND an.site_id = $1
  UNION
    SELECT child.parent_scope, u.depth + 1
      FROM up u
      JOIN mainline.activity_node child
        ON child.scope_id = u.scope_id
     WHERE child.parent_scope IS NOT NULL
       AND u.depth < $4
)
SELECT DISTINCT ev.event_id,
       ev.severity_gate,
       ev.title,
       ev.occurred_at,
       eb.scope_id,
       eb.bond_basis,
       up.depth
  FROM up
  JOIN mainline.event_bond eb
    ON eb.scope_id = up.scope_id
   AND eb.taxonomy_ver = $3
  JOIN mainline.event ev
    ON ev.event_id = eb.event_id
   AND ev.site_id = $1
 WHERE ev.severity_gate = 5
 ORDER BY ev.occurred_at DESC, ev.event_id
""".strip()


@dataclass(frozen=True, slots=True)
class CitedClause:
    """One clause version the permit cites, with the CAT control classes it asserts."""

    clause_uuid: UUID
    commit_id: str
    relation: str
    control_classes: tuple[str, ...] = ()

    def spec(self) -> dict[str, Any]:
        """The JSON shape :data:`ANCESTRY_SQL` binds as ``$2``."""
        return {
            "clause_uuid": str(self.clause_uuid),
            "commit_id": self.commit_id,
            "control_classes": list(self.control_classes),
        }


@dataclass(frozen=True, slots=True)
class AncestryHit:
    """One channel-A admission: an ancestral event whose control class the clause asserts."""

    event_id: UUID
    clause_uuid: UUID
    commit_id: str
    closure_gen: int
    closure_max_severity: int
    closure_truncated: bool
    severity_gate: int
    title: str
    control_classes: tuple[str, ...]
    failure_modes: tuple[str, ...]
    hazard_energies: tuple[str, ...]
    index_confirmed: bool = False

    def evidence_summary(self) -> str:
        """The prose that becomes ``blocking_check.evidence_summary``.

        Deterministic, model-free and citing the join that produced it. Channel A's
        justification must be readable by someone who does not believe our reranker, because
        the whole point of the channel is that it did not use one.
        """
        classes = ", ".join(self.control_classes)
        modes = ", ".join(self.failure_modes)
        return (
            f"Deterministic ancestry: event {self.event_id} (severity {self.severity_gate}) "
            f"is in the active blame closure of clause {self.clause_uuid} at commit "
            f"{self.commit_id[:12]} (closure_gen {self.closure_gen}, closure max_severity "
            f"{self.closure_max_severity}). Its recorded control failure class(es) "
            f"[{classes}] intersect the clause's CAT control class; failure mode(s) "
            f"[{modes}]. No threshold, calibration or rerank was consulted."
            + (
                " The closure is TRUNCATED at the ancestor cap, so this ancestry is a lower "
                "bound."
                if self.closure_truncated
                else ""
            )
        )


@dataclass(frozen=True, slots=True)
class BondedHit:
    """One channel-B admission: a severity-5 event bonded at or above the permit's activity."""

    event_id: UUID
    severity_gate: int
    title: str
    scope_id: UUID
    bond_basis: str
    depth: int

    def evidence_summary(self, activity_scope_id: UUID) -> str:
        """The prose that becomes ``blocking_check.evidence_summary``."""
        where = (
            "the permit's own activity node"
            if self.depth == 0
            else f"an ancestor {self.depth} level(s) above the permit's activity node"
        )
        return (
            f"Bonded fatality: event {self.event_id} (severity_gate 5) is bonded to "
            f"{where} ({self.scope_id}; permit activity {activity_scope_id}) with bond basis "
            f"{self.bond_basis!r}. Admitted unconditionally — a fatality in this fonds is "
            "always recalled, and MI16 (bonded_fatalities_all_blocking) refuses any run row "
            "that recognises it without a blocking obligation."
        )


def _texts(value: object) -> tuple[str, ...]:
    """Normalise a driver's array column into a tuple of strings, sorted and deduplicated."""
    if value is None:
        return ()
    if isinstance(value, (list, tuple)):
        return tuple(sorted({str(item) for item in value if item is not None}))
    return (str(value),)


def cited_clauses(
    session: SqlSession,
    permit_id: UUID,
    control_classes: Mapping[UUID, Sequence[str]],
) -> tuple[CitedClause, ...]:
    """Read the permit's cited clause versions and attach their CAT control classes.

    ``control_classes`` is resolved upstream from ``clause_version.cat_json`` by the CAT
    extractor (``mainline_domain.cat``), which owns that parse. A clause with no resolved
    control class contributes nothing to channel A — and *that is a fact worth recording*, so
    it is returned with an empty tuple rather than dropped, and the orchestrator writes an
    ``unreachable`` silence row for it.
    """
    rows = session.query(CITED_CLAUSES_SQL, (str(permit_id),))
    result: list[CitedClause] = []
    for row in rows:
        clause_uuid = UUID(str(row[0]))
        result.append(
            CitedClause(
                clause_uuid=clause_uuid,
                commit_id=str(row[1]),
                relation=str(row[2]),
                control_classes=tuple(control_classes.get(clause_uuid, ())),
            )
        )
    return tuple(result)


@dataclass(frozen=True, slots=True)
class ChannelAResult:
    """Channel A's admissions, plus the clauses that could not contribute one."""

    hits: tuple[AncestryHit, ...]
    unresolved_clauses: tuple[CitedClause, ...] = field(default_factory=tuple)
    unconfirmed: tuple[AncestryHit, ...] = field(default_factory=tuple)


def channel_a(
    session: SqlSession,
    site_id: UUID,
    clauses: Sequence[CitedClause],
) -> ChannelAResult:
    """Deterministic ancestry, with every admission re-confirmed through the inverted index.

    Returns:
        The confirmed hits, the cited clauses that asserted no CAT control class, and any hit
        the index could not confirm.

    A hit that the ``@>`` probe does not confirm is **not** admitted. It is returned in
    ``unconfirmed`` so the orchestrator can write an ``unreachable`` silence row naming it:
    the closure row said one thing and the index said another, and admitting on the strength
    of the reading we happen to have done first would be trusting a projection rather than
    enforcing it.
    """
    usable = [clause for clause in clauses if clause.control_classes]
    unresolved = tuple(clause for clause in clauses if not clause.control_classes)
    if not usable:
        return ChannelAResult(hits=(), unresolved_clauses=unresolved)

    payload = json.dumps([clause.spec() for clause in usable], sort_keys=True)
    rows = session.query(ANCESTRY_SQL, (str(site_id), payload))

    candidates = [
        AncestryHit(
            event_id=UUID(str(row[0])),
            clause_uuid=UUID(str(row[1])),
            commit_id=str(row[2]),
            closure_gen=int(row[3]),
            closure_max_severity=int(row[4]),
            closure_truncated=bool(row[5]),
            severity_gate=int(row[6]),
            title=str(row[7]),
            control_classes=_texts(row[9]),
            failure_modes=_texts(row[10]),
            hazard_energies=_texts(row[11]),
        )
        for row in rows
    ]

    confirmed: list[AncestryHit] = []
    unconfirmed: list[AncestryHit] = []
    containment: dict[UUID, set[tuple[str, str]]] = {}
    for hit in candidates:
        if hit.event_id not in containment:
            probe = session.query(
                ANCESTRY_CONTAINMENT_SQL, (str(site_id), str(hit.event_id))
            )
            containment[hit.event_id] = {
                (str(entry[0]), str(entry[1])) for entry in probe
            }
        key = (str(hit.clause_uuid), hit.commit_id)
        target = confirmed if key in containment[hit.event_id] else unconfirmed
        target.append(
            AncestryHit(
                event_id=hit.event_id,
                clause_uuid=hit.clause_uuid,
                commit_id=hit.commit_id,
                closure_gen=hit.closure_gen,
                closure_max_severity=hit.closure_max_severity,
                closure_truncated=hit.closure_truncated,
                severity_gate=hit.severity_gate,
                title=hit.title,
                control_classes=hit.control_classes,
                failure_modes=hit.failure_modes,
                hazard_energies=hit.hazard_energies,
                index_confirmed=target is confirmed,
            )
        )

    return ChannelAResult(
        hits=tuple(confirmed),
        unresolved_clauses=unresolved,
        unconfirmed=tuple(unconfirmed),
    )


def channel_b(
    session: SqlSession,
    site_id: UUID,
    activity_scope_id: UUID,
    taxonomy_ver: int,
) -> tuple[BondedHit, ...]:
    """Every severity-5 event bonded to the permit's activity node or any ancestor of it.

    Admitted unconditionally. The severity comes from ``event.severity_gate``, which
    ``model_cannot_arm`` already forbids a model from setting at or above 4 — so this channel
    cannot be armed by a model's opinion, only by a coded field, a regulator classification or
    a signed human.
    """
    rows = session.query(
        BONDED_SEV5_SQL,
        (str(site_id), str(activity_scope_id), taxonomy_ver, MAX_SCOPE_WALK_DEPTH),
    )
    return tuple(
        BondedHit(
            event_id=UUID(str(row[0])),
            severity_gate=int(row[1]),
            title=str(row[2]),
            scope_id=UUID(str(row[4])),
            bond_basis=str(row[5]),
            depth=int(row[6]),
        )
        for row in rows
    )
