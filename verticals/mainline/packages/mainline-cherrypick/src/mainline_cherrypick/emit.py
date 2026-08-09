# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""Statements and parameters. No driver, no credential, and two impossible writes.

Every function here returns a :class:`Statement`; the caller opens the connection,
holds ``agent_fleet`` and owns the transaction boundary. That absence is what
``mainline-boundary``'s E3 SBOM scan reads.

Two writes are absent on purpose and :func:`assert_fleet_safe` keeps them absent.

**Nothing here writes ``mainline.disposition``.** ``svc_disposition`` is the only
role that can, no agent holds it, and — since §5.1 — an agent could not sign even
if it did, because it has no enrolled WebAuthn credential. *An agent signed away a
fatality-linked precursor* is a sentence that must be impossible to produce in
discovery, and the cost of that is one absent statement.

**Nothing here writes ``merge_conflict``'s resolution columns.** ``agent_fleet``
holds ``INSERT`` on that table and no ``UPDATE``, so ``resolved_commit``,
``resolved_by``, ``resolution_sig`` and ``resolution_source`` are unreachable after
insert. §5.9: *a recorded resolution is proposed, never auto-applied.* Writing an
``UPDATE`` here that the database would refuse anyway would be a statement whose
only purpose is to be refused — and a future reader would reasonably assume it once
worked.

The one ``UPDATE`` in this module sets ``prop_state`` and nothing else, because
§11.2 scopes ``agent_fleet``'s ``UPDATE`` on ``propagation`` to that column by
trigger. ``open_conflicts`` is a trigger-maintained projection over
``merge_conflict`` — the same shape as ``permit.open_blocking`` over
``blocking_check`` — so a site cannot declare itself conflict-free.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final

from .errors import AgentWouldResolve, ForbiddenWriteTarget
from .travel import assert_may_travel

if TYPE_CHECKING:
    from collections.abc import Sequence

    from .types import (
        HumanResolution,
        Lesson,
        MergeConflict,
        Propagation,
        PropState,
        ResolutionMemoryRow,
    )

__all__ = [
    "FLEET_ROLE",
    "FORBIDDEN_TARGETS",
    "INSERT_LESSON_SQL",
    "INSERT_MERGE_CONFLICT_SQL",
    "INSERT_PROPAGATION_SQL",
    "INSERT_RESOLUTION_MEMORY_SQL",
    "STATEMENTS",
    "UPDATE_PROPAGATION_STATE_SQL",
    "Statement",
    "assert_fleet_safe",
    "insert_lesson",
    "insert_merge_conflict",
    "insert_propagation",
    "insert_resolution_memory",
    "update_propagation_state",
]

#: The SQL role these statements are written for. INSERT on `lesson`,
#: `merge_conflict`, `resolution_memory` and `mainline_ops.outbox`; INSERT plus a
#: trigger-scoped UPDATE on `propagation`; nothing on `disposition`, ever.
FLEET_ROLE: Final[str] = "agent_fleet"

#: Objects no statement in this package may name. Checked over the SQL text of
#: every statement this module can produce, so the guarantee is a property of the
#: strings rather than of a review.
FORBIDDEN_TARGETS: Final[frozenset[str]] = frozenset(
    {
        "disposition",
        "carried_disposition",
        "blocking_check",
        "permit",
        "permit_event",
        "merge_record",
        "clause_blame_closure",
        "signing_credential",
    }
)

_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*")
_RESOLUTION_COLUMNS = ("resolved_commit", "resolved_by", "resolution_sig")


@dataclass(frozen=True, slots=True)
class Statement:
    """One statement and its parameters. This package never holds a driver."""

    sql: str
    params: tuple[Any, ...] = ()


def _names(sql: str) -> frozenset[str]:
    """Every bare and schema-qualified identifier tail appearing in ``sql``."""
    found: set[str] = set()
    for match in _IDENTIFIER.finditer(sql):
        token = match.group(0)
        found.add(token)
        if "." in token:
            found.add(token.rsplit(".", 1)[1])
    return frozenset(found)


def assert_fleet_safe(statement: Statement) -> Statement:
    """Return ``statement`` unchanged, or refuse it.

    Three refusals:

    * naming any object in :data:`FORBIDDEN_TARGETS`;
    * an ``UPDATE`` or ``DELETE`` on ``merge_conflict`` — the resolution columns
      are unreachable by grant and must be unreachable in code too, so that a
      reader never has to work out which of the two is load-bearing;
    * a statement that assigns one of the resolution columns at all.

    Deliberately over-inclusive on identifiers: a *column* named ``permit`` would
    trip this. That direction of error costs a rename; the other direction costs a
    write nobody expected from a role nobody audited.
    """
    named = _names(statement.sql)
    for target in sorted(FORBIDDEN_TARGETS):
        if target in named:
            raise ForbiddenWriteTarget(target, statement.sql)
    upper = statement.sql.upper().strip()
    if "MERGE_CONFLICT" in upper and (upper.lstrip().startswith(("UPDATE", "DELETE"))):
        raise AgentWouldResolve(
            f"statement mutates merge_conflict after insert. A recorded resolution is "
            f"proposed, never auto-applied. SQL: {statement.sql!r}"
        )
    for column in _RESOLUTION_COLUMNS:
        if column in statement.sql.lower():
            raise AgentWouldResolve(
                f"statement assigns {column!r}. Only a human-authenticated pgwire path "
                f"writes a resolution. SQL: {statement.sql!r}"
            )
    return statement


INSERT_LESSON_SQL: Final[str] = """
INSERT INTO mainline.lesson (
  lesson_id, origin_site, origin_commit, anchor_event, max_severity,
  control_delta, patch_digest, merge_base, envelope
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (lesson_id) DO NOTHING
RETURNING lesson_id
""".strip()

INSERT_PROPAGATION_SQL: Final[str] = """
INSERT INTO mainline.propagation (
  lesson_id, site_id, state, score, model_version, proposed_at, due_by,
  already_present_clause, declination_kind, declination_predicate_id,
  declination_expires_at
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (lesson_id, site_id) DO NOTHING
RETURNING lesson_id, site_id
""".strip()

#: The only UPDATE in the package, and it sets one column. `open_conflicts` and
#: `adopted_commit` are trigger-maintained projections; a `SET` on either would be
#: an agent writing a value the gate reads.
UPDATE_PROPAGATION_STATE_SQL: Final[str] = """
UPDATE mainline.propagation
   SET state = %s
 WHERE lesson_id = %s AND site_id = %s AND state = %s
RETURNING lesson_id, site_id, state
""".strip()

INSERT_MERGE_CONFLICT_SQL: Final[str] = """
INSERT INTO mainline.merge_conflict (
  conflict_id, lesson_id, site_id, clause_uuid,
  base_digest, ours_digest, theirs_digest, opened_at
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (conflict_id) DO NOTHING
RETURNING conflict_id
""".strip()

INSERT_RESOLUTION_MEMORY_SQL: Final[str] = """
INSERT INTO mainline.resolution_memory (
  clause_uuid, base_digest, ours_digest, theirs_digest,
  resolution_text, origin_conflict
) VALUES (%s, %s, %s, %s, %s, %s)
ON CONFLICT (clause_uuid, base_digest, ours_digest, theirs_digest) DO NOTHING
RETURNING clause_uuid
""".strip()

#: Every statement this package can produce, for the starvation test to walk.
STATEMENTS: Final[tuple[str, ...]] = (
    INSERT_LESSON_SQL,
    INSERT_PROPAGATION_SQL,
    UPDATE_PROPAGATION_STATE_SQL,
    INSERT_MERGE_CONFLICT_SQL,
    INSERT_RESOLUTION_MEMORY_SQL,
)


def insert_lesson(lesson: Lesson, delta_set_size: int) -> Statement:
    """Build the ``lesson`` insert.

    :func:`~mainline_cherrypick.travel.assert_may_travel` runs here, immediately
    before the statement is built, so the check applies to the object about to be
    written rather than to the object that was once constructed.

    ``delta_set_size`` is carried into ``envelope`` under a reserved key so a
    reader of the row can tell a one-clause lesson from a forty-clause one without
    resolving the patch digest. It is metadata about the lesson, not a predicate,
    and :func:`~mainline_cherrypick.travel.evaluate_envelope` ignores unknown
    top-level keys by refusing multi-key nodes — so it is stored beside the
    envelope, never inside it.
    """
    assert_may_travel(lesson)
    envelope = {"predicate": dict(lesson.envelope), "delta_set_size": delta_set_size}
    return assert_fleet_safe(
        Statement(
            sql=INSERT_LESSON_SQL,
            params=(
                lesson.lesson_id,
                lesson.origin_site,
                lesson.origin_commit,
                lesson.anchor_event,
                lesson.max_severity,
                lesson.control_delta.value,
                lesson.patch_digest,
                lesson.merge_base,
                envelope,
            ),
        )
    )


def insert_propagation(propagation: Propagation) -> Statement:
    """Build the ``propagation`` insert.

    ``ON CONFLICT (lesson_id, site_id) DO NOTHING`` because that pair **is** the
    idempotency key for at-least-once delivery (§5.9, §8.5). An empty result is the
    success case for a redelivery and must not be read as a failed insert.

    ``open_conflicts`` and ``adopted_commit`` are absent from the column list: both
    are projections, and supplying either would be an inserter deciding a value the
    gate reads.
    """
    declination = propagation.declination
    # `already_present_clause` is one column and two callers can populate it: a
    # site that converged independently sets it on the propagation, and a
    # `mitigated` declination names it on the declination. The DDL has one column
    # and one `CHECK`, so the emitter resolves the two here rather than leaving a
    # `mitigated` declination to fail `mitigated_names_local_clause` with a `23514`
    # whose cause is two Python objects disagreeing.
    local_clause = propagation.already_present_clause or (
        declination.already_present_clause if declination else None
    )
    return assert_fleet_safe(
        Statement(
            sql=INSERT_PROPAGATION_SQL,
            params=(
                propagation.lesson_id,
                propagation.site_id,
                propagation.state.value,
                _score(propagation.score_milli),
                propagation.model_version,
                propagation.proposed_at,
                propagation.due_by,
                local_clause,
                declination.kind if declination else None,
                declination.predicate_id if declination else None,
                declination.expires_at if declination else None,
            ),
        )
    )


def update_propagation_state(
    propagation: Propagation,
    previous: PropState,
) -> Statement:
    """Build the state transition as a compare-and-set on the previous state.

    ``WHERE … AND state = %s`` makes this a CAS. Two workers handed the same
    at-least-once delivery cannot both advance the row: the second matches no row
    and returns nothing. That is the same discipline the ledger's
    ``UNIQUE (subject, prev_seq)`` uses, and it works here for the same reason —
    CockroachDB has no advisory locks, so the compare has to be in the predicate.
    """
    return assert_fleet_safe(
        Statement(
            sql=UPDATE_PROPAGATION_STATE_SQL,
            params=(
                propagation.state.value,
                propagation.lesson_id,
                propagation.site_id,
                previous.value,
            ),
        )
    )


def insert_merge_conflict(conflict: MergeConflict) -> Statement:
    """Build the ``merge_conflict`` insert. Opens only; the resolution is a person's."""
    return assert_fleet_safe(
        Statement(
            sql=INSERT_MERGE_CONFLICT_SQL,
            params=(
                conflict.conflict_id,
                conflict.lesson_id,
                conflict.site_id,
                conflict.clause_uuid,
                conflict.base_digest,
                conflict.ours_digest,
                conflict.theirs_digest,
                conflict.opened_at,
            ),
        )
    )


def insert_resolution_memory(
    row: ResolutionMemoryRow,
    resolution: HumanResolution,
) -> Statement:
    """Build the ``resolution_memory`` insert for a resolution a person signed.

    ``resolution`` is required and unused in the parameters, and that is the point:
    :class:`~mainline_cherrypick.types.HumanResolution` cannot be constructed
    without a signature and a human subject, so requiring one as an argument means
    a remembered resolution cannot exist without a signed one having existed first.
    A type that must be constructed in order to be discarded is a cheap, total
    proof obligation.

    Raises:
        AgentWouldResolve: the signed conflict is not the one being remembered.
    """
    if resolution.conflict_id != row.origin_conflict:
        raise AgentWouldResolve(
            f"resolution memory cites origin conflict {row.origin_conflict} but the "
            f"signature covers {resolution.conflict_id}. A memory whose provenance points "
            f"at a different conflict is worse than no memory"
        )
    return assert_fleet_safe(
        Statement(
            sql=INSERT_RESOLUTION_MEMORY_SQL,
            params=(
                row.clause_uuid,
                row.base_digest,
                row.ours_digest,
                row.theirs_digest,
                row.resolution_text,
                row.origin_conflict,
            ),
        )
    )


def _score(milli: int) -> str:
    """Render a milli-unit score for the DDL's ``NUMERIC`` column.

    A decimal **string**, not a float. ``propagation.score`` is ``NUMERIC``, and
    binding a Python float to it would round-trip a value nobody chose through
    IEEE-754 on the way to a column that exists precisely to avoid that.
    """
    return f"{milli // 1000}.{milli % 1000:03d}"


def statements_for_offer(
    lesson: Lesson,
    propagations: Sequence[Propagation],
    delta_set_size: int,
) -> tuple[Statement, ...]:
    """Every statement for offering one lesson to a set of sites, in execution order.

    The lesson row first — the propagations carry a foreign key to it — then one
    propagation per site. Returned as an ordered tuple rather than a set, because
    an ordering contract documented in prose is an ordering contract broken by the
    next refactor that looks harmless.
    """
    return (
        insert_lesson(lesson, delta_set_size),
        *(insert_propagation(propagation) for propagation in propagations),
    )
