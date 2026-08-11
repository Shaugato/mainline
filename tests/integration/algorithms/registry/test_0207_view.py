# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Migration 0207 against a real cluster, and the SQL clause source against the same rows.

Two things are proven here that no unit test can prove:

1. ``CREATE VIEW mainline.v_safe_direction_current`` applies forward from clean
   on CockroachDB v26.2 and returns the seeded parameters, with every field
   extracted from the clause text by ``split_part`` — no column stores a
   direction twice.
2. ``mainline_domain.registry.sql`` reads the same document out of the same
   tables and produces a registry whose answers match the Python path's, so the
   ``WITH RECURSIVE`` ancestry walk and the ``clause_version`` join are not
   merely plausible.

The suite also holds the boundary the view's own header states: **the view is
not what the gate reads.**  A test below writes a later commit that flips a
direction and shows the view following it while a registry loaded at the earlier
commit does not.
"""

from __future__ import annotations

import uuid

import pytest
from _directrix_support import (
    insert_clause_version,
    insert_commit,
    insert_registry_doc,
    rows,
)
from mainline_domain.canon import canon_digest
from mainline_domain.registry import (
    DOC_CODE,
    AbstentionReason,
    EntryStatus,
    SafeDirection,
    clause_uuid_for,
    encode,
    load_registry,
    load_seed,
)
from mainline_domain.registry.sql import SqlClauseVersionSource

pytestmark = pytest.mark.schema


def _clause_text(
    parameter: str,
    dimension_label: str,
    direction: SafeDirection,
    status: EntryStatus = EntryStatus.RATIFIED,
    rationale: str = "stated so that a later reader has something to disagree with",
) -> str:
    return encode(
        parameter=parameter,
        dimension_label=dimension_label,
        direction=direction,
        status=status,
        rationale=rationale,
    )


def _seed_the_document(conn, site_id: uuid.UUID, *, limit: int | None = None):
    """Write the committed seed into the spine as one signed ratification commit."""
    head = insert_commit(conn, site_id=site_id, label=f"head/{site_id}", gen=1)
    doc_id = insert_registry_doc(conn, site_id=site_id, doc_code=DOC_CODE)
    parameters = load_seed()
    if limit is not None:
        parameters = parameters[:limit]
    for ordinal, parameter in enumerate(parameters):
        text = _clause_text(
            parameter.key,
            parameter.dimension_label,
            parameter.direction,
            rationale=parameter.rationale,
        )
        insert_clause_version(
            conn,
            site_id=site_id,
            doc_id=doc_id,
            clause_uuid=clause_uuid_for(site_id, parameter.key),
            commit=head,
            canon_text=text,
            canon_sha256=canon_digest(text),
            ordinal=ordinal,
        )
    return head, doc_id, parameters


def test_the_view_exists_and_is_a_view(conn) -> None:
    found = rows(
        conn,
        """
        SELECT table_type FROM information_schema.tables
         WHERE table_schema = 'mainline' AND table_name = 'v_safe_direction_current'
        """,
    )
    assert found, "migration 0207 did not create mainline.v_safe_direction_current"
    assert found[0][0] == "VIEW"


def test_the_view_returns_the_seeded_parameters(conn, site_id: uuid.UUID) -> None:
    _head, _doc_id, parameters = _seed_the_document(conn, site_id)

    found = rows(
        conn,
        """
        SELECT parameter_key, dimension_label, direction, entry_status, answers
          FROM mainline.v_safe_direction_current
         WHERE site_id = %s
         ORDER BY parameter_key
        """,
        (site_id,),
    )
    assert len(found) == len(parameters)

    by_key = {row[0]: row for row in found}
    for parameter in parameters:
        row = by_key[parameter.key]
        assert row[1] == parameter.dimension_label, parameter.key
        assert row[2] == parameter.direction.value, parameter.key
        assert row[3] == "RATIFIED", parameter.key
        assert row[4] is True, parameter.key


def test_the_rationale_survives_the_extraction_whole(conn, site_id: uuid.UUID) -> None:
    """The last field runs to the end of the clause and must not be truncated.

    ``split_part(canon_text, 'Rationale: ', 2)`` takes everything after the label,
    which matters because rationales contain full stops and an extraction that
    stopped at the first one would leave a truncated justification in the console
    and in the MCP read surface.
    """
    _head, _doc_id, parameters = _seed_the_document(conn, site_id, limit=8)
    found = dict(
        rows(
            conn,
            """
            SELECT parameter_key, rationale FROM mainline.v_safe_direction_current
             WHERE site_id = %s
            """,
            (site_id,),
        )
    )
    for parameter in parameters:
        assert found[parameter.key] == parameter.rationale


def test_a_proposed_or_unsigned_entry_reports_answers_false(conn, site_id: uuid.UUID) -> None:
    """``answers`` is fail-closed in the same direction the Python loader is.

    An operator reading the view must see the same live set the algorithm does,
    and both must exclude anything unratified, unsigned, unparseable or retired.
    """
    signed = insert_commit(conn, site_id=site_id, label=f"signed/{site_id}", gen=1)
    unsigned = insert_commit(
        conn, site_id=site_id, label=f"unsigned/{site_id}", gen=1, signed=False
    )
    doc_id = insert_registry_doc(conn, site_id=site_id, doc_code=DOC_CODE)

    cases = (
        ("max_operating_pressure", signed, EntryStatus.RATIFIED, True),
        ("min_ppe_level", signed, EntryStatus.PROPOSED, False),
        ("isolation_point_count", signed, EntryStatus.WITHDRAWN, False),
        ("max_lifting_load", unsigned, EntryStatus.RATIFIED, False),
    )
    labels = {
        "max_operating_pressure": "pressure",
        "min_ppe_level": "ordinal",
        "isolation_point_count": "count",
        "max_lifting_load": "mass",
    }
    directions = {
        "max_operating_pressure": SafeDirection.LOWER_IS_SAFER,
        "min_ppe_level": SafeDirection.HIGHER_IS_SAFER,
        "isolation_point_count": SafeDirection.HIGHER_IS_SAFER,
        "max_lifting_load": SafeDirection.LOWER_IS_SAFER,
    }
    for ordinal, (parameter, commit, status, _expected) in enumerate(cases):
        text = _clause_text(parameter, labels[parameter], directions[parameter], status)
        insert_clause_version(
            conn,
            site_id=site_id,
            doc_id=doc_id,
            clause_uuid=clause_uuid_for(site_id, parameter),
            commit=commit,
            canon_text=text,
            canon_sha256=canon_digest(text),
            ordinal=ordinal,
        )

    found = dict(
        rows(
            conn,
            "SELECT parameter_key, answers FROM mainline.v_safe_direction_current "
            "WHERE site_id = %s",
            (site_id,),
        )
    )
    for parameter, _commit, _status, expected in cases:
        assert found[parameter] is expected, parameter


def test_a_retired_clause_reports_answers_false(conn, site_id: uuid.UUID) -> None:
    first = insert_commit(conn, site_id=site_id, label=f"live/{site_id}", gen=1)
    second = insert_commit(
        conn, site_id=site_id, label=f"retire/{site_id}", gen=2, parents=(first.commit_id,)
    )
    doc_id = insert_registry_doc(conn, site_id=site_id, doc_code=DOC_CODE)
    text = _clause_text("max_operating_pressure", "pressure", SafeDirection.LOWER_IS_SAFER)
    insert_clause_version(
        conn,
        site_id=site_id,
        doc_id=doc_id,
        clause_uuid=clause_uuid_for(site_id, "max_operating_pressure"),
        commit=first,
        canon_text=text,
        canon_sha256=canon_digest(text),
        ordinal=0,
        retired_commit=second.commit_id,
    )
    found = rows(
        conn,
        "SELECT answers FROM mainline.v_safe_direction_current WHERE site_id = %s",
        (site_id,),
    )
    assert found and found[0][0] is False


def test_a_clause_that_is_not_a_registry_entry_reports_answers_false(
    conn, site_id: uuid.UUID
) -> None:
    """A garbled clause in the document does not become a direction."""
    head = insert_commit(conn, site_id=site_id, label=f"garbled/{site_id}", gen=1)
    doc_id = insert_registry_doc(conn, site_id=site_id, doc_code=DOC_CODE)
    text = "The vessel shall not exceed 50 psig during the intervention."
    insert_clause_version(
        conn,
        site_id=site_id,
        doc_id=doc_id,
        clause_uuid=uuid.uuid4(),
        commit=head,
        canon_text=text,
        canon_sha256=canon_digest(text),
        ordinal=0,
    )
    found = rows(
        conn,
        "SELECT answers, parameter_key FROM mainline.v_safe_direction_current WHERE site_id = %s",
        (site_id,),
    )
    assert found and found[0][0] is False


def test_the_view_only_shows_the_registry_document(conn, site_id: uuid.UUID) -> None:
    """A clause in some other document is not a safe-direction entry, whatever it says."""
    head = insert_commit(conn, site_id=site_id, label=f"other/{site_id}", gen=1)
    other_doc = insert_registry_doc(conn, site_id=site_id, doc_code="PRO-ISOLATION-001")
    text = _clause_text("max_operating_pressure", "pressure", SafeDirection.HIGHER_IS_SAFER)
    insert_clause_version(
        conn,
        site_id=site_id,
        doc_id=other_doc,
        clause_uuid=uuid.uuid4(),
        commit=head,
        canon_text=text,
        canon_sha256=canon_digest(text),
        ordinal=0,
    )
    assert (
        rows(
            conn,
            "SELECT count(*) FROM mainline.v_safe_direction_current WHERE site_id = %s",
            (site_id,),
        )[0][0]
        == 0
    )


def test_the_sql_source_reproduces_the_python_registry(conn, site_id: uuid.UUID) -> None:
    """The whole point of the source protocol: one resolution algorithm, two sources."""
    head, _doc_id, parameters = _seed_the_document(conn, site_id)

    source = SqlClauseVersionSource(connection=conn)
    registry = load_registry(source, site_id=site_id, as_of_commit=head.commit_id)

    assert registry.parameters() == {p.key for p in parameters}
    for parameter in parameters:
        assert registry.safe_direction(parameter.key) is parameter.direction
        entry = registry.entries[parameter.key]
        assert entry.ratification_commit == head.commit_id
        assert entry.ratified_by_sub == "sub-principal-engineer"
        assert entry.ratification_signed is True


def test_the_recursive_ancestry_walk_terminates_on_a_diamond(conn, site_id: uuid.UUID) -> None:
    """``UNION`` and not ``UNION ALL``: a merge must not make the walk loop.

    A diamond is the ordinary shape of any repository with branches, so a walk
    that did not deduplicate would not be slow — it would not return.
    """
    base = insert_commit(conn, site_id=site_id, label=f"d-base/{site_id}", gen=1)
    left = insert_commit(
        conn, site_id=site_id, label=f"d-left/{site_id}", gen=2, parents=(base.commit_id,)
    )
    right = insert_commit(
        conn, site_id=site_id, label=f"d-right/{site_id}", gen=2, parents=(base.commit_id,)
    )
    merge = insert_commit(
        conn,
        site_id=site_id,
        label=f"d-merge/{site_id}",
        gen=3,
        parents=(left.commit_id, right.commit_id),
    )

    source = SqlClauseVersionSource(connection=conn)
    reachable = source.ancestry(merge.commit_id)
    assert reachable == {
        base.commit_id,
        left.commit_id,
        right.commit_id,
        merge.commit_id,
    }
    assert source.ancestry(base.commit_id) == {base.commit_id}


def test_a_branch_entry_is_visible_only_after_the_merge(conn, site_id: uuid.UUID) -> None:
    base = insert_commit(conn, site_id=site_id, label=f"b-base/{site_id}", gen=1)
    branch = insert_commit(
        conn, site_id=site_id, label=f"b-branch/{site_id}", gen=2, parents=(base.commit_id,)
    )
    merge = insert_commit(
        conn,
        site_id=site_id,
        label=f"b-merge/{site_id}",
        gen=3,
        parents=(base.commit_id, branch.commit_id),
    )
    doc_id = insert_registry_doc(conn, site_id=site_id, doc_code=DOC_CODE)
    text = _clause_text("min_escape_route_count", "count", SafeDirection.HIGHER_IS_SAFER)
    insert_clause_version(
        conn,
        site_id=site_id,
        doc_id=doc_id,
        clause_uuid=clause_uuid_for(site_id, "min_escape_route_count"),
        commit=branch,
        canon_text=text,
        canon_sha256=canon_digest(text),
        ordinal=0,
    )

    source = SqlClauseVersionSource(connection=conn)
    at_base = load_registry(source, site_id=site_id, as_of_commit=base.commit_id)
    at_merge = load_registry(source, site_id=site_id, as_of_commit=merge.commit_id)

    assert at_base.parameters() == frozenset()
    assert at_base.resolve("min_escape_route_count").reason is AbstentionReason.DOCUMENT_ABSENT
    assert at_merge.parameters() == {"min_escape_route_count"}


def test_the_view_follows_the_head_and_the_loader_does_not(conn, site_id: uuid.UUID) -> None:
    """The boundary migration 0207's own header states, made a test.

    The view answers "what does the registry say today"; the gate answers "what
    did it say at the commit under test".  Wiring rule R2 to the view would make
    every historical verdict silently re-computable under a registry that has
    since moved, which is the retro-tuning attack rebuilt in a different column.
    """
    first = insert_commit(conn, site_id=site_id, label=f"v1/{site_id}", gen=1)
    second = insert_commit(
        conn, site_id=site_id, label=f"v2/{site_id}", gen=2, parents=(first.commit_id,)
    )
    doc_id = insert_registry_doc(conn, site_id=site_id, doc_code=DOC_CODE)
    clause = clause_uuid_for(site_id, "max_operating_pressure")

    original = _clause_text("max_operating_pressure", "pressure", SafeDirection.LOWER_IS_SAFER)
    insert_clause_version(
        conn,
        site_id=site_id,
        doc_id=doc_id,
        clause_uuid=clause,
        commit=first,
        canon_text=original,
        canon_sha256=canon_digest(original),
        ordinal=0,
    )
    flipped = _clause_text(
        "max_operating_pressure",
        "pressure",
        SafeDirection.HIGHER_IS_SAFER,
        rationale="a later and, one hopes, well-argued reversal of the original entry",
    )
    insert_clause_version(
        conn,
        site_id=site_id,
        doc_id=doc_id,
        clause_uuid=clause,
        commit=second,
        canon_text=flipped,
        canon_sha256=canon_digest(flipped),
        ordinal=0,
    )

    view_says = rows(
        conn,
        "SELECT direction FROM mainline.v_safe_direction_current WHERE site_id = %s",
        (site_id,),
    )
    assert view_says == [("HIGHER_IS_SAFER",)]

    source = SqlClauseVersionSource(connection=conn)
    at_first = load_registry(source, site_id=site_id, as_of_commit=first.commit_id)
    at_second = load_registry(source, site_id=site_id, as_of_commit=second.commit_id)
    assert at_first.safe_direction("max_operating_pressure") is SafeDirection.LOWER_IS_SAFER
    assert at_second.safe_direction("max_operating_pressure") is SafeDirection.HIGHER_IS_SAFER


def test_there_is_no_safe_direction_table(conn) -> None:
    """The mechanism, asserted negatively.

    If a ``mainline.safe_direction`` table ever appears, DIRECTRIX has been
    quietly undone: two columns in a table are an ``UPDATE`` away from inverting
    every setpoint verdict in the system, with no commit, no signature, no blame
    edge and no refusal.
    """
    found = rows(
        conn,
        """
        SELECT table_name FROM information_schema.tables
         WHERE table_schema = 'mainline'
           AND table_name IN ('safe_direction', 'safe_directions', 'directrix')
        """,
    )
    assert found == [], (
        f"a safe-direction TABLE exists ({found}); the registry must be a document in "
        "the gated commit DAG, or the gate's own parameters stop being gated"
    )
