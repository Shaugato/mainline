# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Derived dependency edges: symmetry, irreflexivity, determinism, and provenance.

The property this file exists to make checkable is I06 — *a dependency edge a gate
consumes is computed, never declared.*  After the fact, the only thing separating
a computed edge from a typed one is that the computed one names the code and the
encoding that produced it, so ``computed_by`` and ``footprint_ver`` are asserted
on **every** row rather than spot-checked.
"""

from __future__ import annotations

from uuid import uuid5

import pytest
from _diachronic_fixtures import SITE_ID, commit
from hypothesis import given, settings
from hypothesis import strategies as st
from mainline_domain.diachronic.commutation import (
    COMMUTATION_EDGE_INSERT_SQL,
    ClauseEdit,
    EditRef,
    canonical,
    commutes,
    derive_commutation_edges,
    edge_for,
    edges_for_clause,
    unfootprintable,
)
from mainline_domain.diachronic.errors import FootprintError
from mainline_domain.diachronic.footprint import Footprint
from mainline_domain.diachronic.version import FOOTPRINT_VERSION, computed_by


def edit(label: str, *tokens: str, commit_label: str = "c1") -> ClauseEdit:
    return ClauseEdit(
        ref=EditRef(
            site_id=SITE_ID,
            commit_id=commit(commit_label),
            clause_uuid=uuid5(SITE_ID, f"clause/{label}"),
        ),
        footprint=Footprint(frozenset(tokens)),
    )


# --------------------------------------------------------------------------- #
# The relation                                                                 #
# --------------------------------------------------------------------------- #


def test_disjoint_footprints_commute_and_produce_no_edge():
    a = edit("a", "anchor:equipment_tag:P-101A", "param:max_operating_pressure")
    b = edit("b", "anchor:equipment_tag:TK-204", "param:min_ppe_level")
    assert commutes(a, b) is True
    assert edge_for(a, b) is None


def test_a_shared_anchor_is_enough_to_make_two_edits_dependent():
    a = edit("a", "anchor:equipment_tag:P-101A", "param:max_operating_pressure")
    b = edit("b", "anchor:equipment_tag:P-101A", "param:min_ppe_level")
    assert commutes(a, b) is False
    derived = edge_for(a, b)
    assert derived is not None
    assert derived.footprint_overlap == ("anchor:equipment_tag:P-101A",)


def test_commutation_is_symmetric_and_the_edge_is_the_same_row_either_way():
    a = edit("a", "param:x")
    b = edit("b", "param:x")
    assert commutes(a, b) == commutes(b, a)
    assert edge_for(a, b) == edge_for(b, a)


def test_an_edit_never_commutes_with_itself_and_asking_is_a_refusal():
    a = edit("a", "param:x")
    assert commutes(a, a) is False
    with pytest.raises(FootprintError) as raised:
        canonical(a.ref, a.ref)
    assert "cannot commute with itself" in str(raised.value)


def test_an_empty_footprint_refuses_rather_than_reporting_independence():
    """Fail-open is the one answer this question may not have.

    An empty set is disjoint from everything, so "commutes" would report *we could
    not read this edit* as *this edit is independent of everything* — in a
    computation whose entire purpose is to widen an antecedent set.
    """
    known = edit("a", "param:x")
    blank = edit("b")
    with pytest.raises(FootprintError) as raised:
        commutes(known, blank)
    message = str(raised.value)
    assert "EMPTY footprint" in message
    assert "ignorance as independence" in message


# --------------------------------------------------------------------------- #
# Canonical direction — the Python side of 0049b's CHECK                       #
# --------------------------------------------------------------------------- #


@settings(max_examples=500, deadline=None)
@given(
    left=st.sampled_from(["c1", "c2", "c3"]),
    right=st.sampled_from(["c1", "c2", "c3"]),
    left_clause=st.sampled_from(["a", "b", "c"]),
    right_clause=st.sampled_from(["a", "b", "c"]),
)
def test_canonical_order_matches_the_lexicographic_rule_the_sql_check_enforces(
    left, right, left_clause, right_clause
):
    """``from_commit < to_commit OR (from_commit = to_commit AND from_clause < to_clause)``.

    ``0049b_commutation_edge.sql`` writes that expression as a CHECK.  This
    property proves the Python canonicaliser produces exactly the rows that CHECK
    accepts, over every ordering of a small pool — including the equal-commit case,
    which is the one a hand-written test forgets.
    """
    a = edit(left_clause, "param:x", commit_label=left)
    b = edit(right_clause, "param:x", commit_label=right)
    if a.ref.sort_key == b.ref.sort_key:
        with pytest.raises(FootprintError):
            canonical(a.ref, b.ref)
        return

    first, second = canonical(a.ref, b.ref)
    assert (first.commit_id < second.commit_id) or (
        first.commit_id == second.commit_id and first.clause_uuid < second.clause_uuid
    )
    assert canonical(b.ref, a.ref) == (first, second)


def test_uuid_ordering_agrees_with_the_hex_string_ordering_cockroachdb_uses():
    """CockroachDB orders UUID by its 128-bit value; Python's ``UUID`` does too.

    That agreement is what lets the CHECK and the canonicaliser be two statements
    of one rule.  Asserted rather than assumed, because a mismatch would produce
    rows the database accepts in one direction and refuses in the other, silently,
    only for some pairs.
    """
    values = sorted(uuid5(SITE_ID, f"clause/{i}") for i in range(64))
    assert [str(v) for v in values] == sorted(str(v) for v in values)


# --------------------------------------------------------------------------- #
# Derivation over a set                                                        #
# --------------------------------------------------------------------------- #


def test_every_derived_row_names_the_code_and_the_encoding_that_derived_it():
    edits = [
        edit("a", "param:x", commit_label="c1"),
        edit("b", "param:x", commit_label="c2"),
        edit("c", "param:x", commit_label="c3"),
    ]
    edges = derive_commutation_edges(edits)
    assert len(edges) == 3
    for derived in edges:
        assert derived.computed_by == computed_by()
        assert derived.computed_by.startswith("mainline_domain.diachronic/")
        assert derived.footprint_ver == FOOTPRINT_VERSION
        assert derived.footprint_overlap, "an edge with no overlap is a declaration"


def test_derivation_is_byte_identical_across_two_runs_over_a_shuffled_input():
    edits = [
        edit("a", "param:x", commit_label="c3"),
        edit("b", "param:x", commit_label="c1"),
        edit("c", "param:y", commit_label="c2"),
    ]
    first = derive_commutation_edges(edits)
    second = derive_commutation_edges(list(reversed(edits)))
    assert first == second


def test_no_self_edge_is_ever_derived():
    edits = [edit("a", "param:x"), edit("b", "param:x", commit_label="c2")]
    for derived in derive_commutation_edges(edits):
        assert (derived.from_commit, derived.from_clause_uuid) != (
            derived.to_commit,
            derived.to_clause_uuid,
        )


def test_one_row_per_unordered_pair_and_never_two():
    edits = [edit(name, "param:x", commit_label=f"c{i}") for i, name in enumerate("abcd")]
    edges = derive_commutation_edges(edits)
    keys = {(e.from_commit, e.from_clause_uuid, e.to_commit, e.to_clause_uuid) for e in edges}
    assert len(keys) == len(edges) == 6  # 4 choose 2
    reversed_keys = {(k[2], k[3], k[0], k[1]) for k in keys}
    assert keys.isdisjoint(reversed_keys)


def test_an_unfootprintable_edit_is_skipped_and_reported_rather_than_commuted():
    edits = [
        edit("a", "param:x"),
        edit("b", commit_label="c2"),
        edit("c", "param:x", commit_label="c3"),
    ]
    edges = derive_commutation_edges(edits)
    assert len(edges) == 1
    skipped = unfootprintable(edits)
    assert len(skipped) == 1
    assert skipped[0].clause_uuid == uuid5(SITE_ID, "clause/b")


def test_two_edits_that_claim_one_identity_are_a_refusal():
    """One commit produces at most one version of a clause (``cv_clause_commit_unique``)."""
    duplicate = edit("a", "param:x")
    other = ClauseEdit(ref=duplicate.ref, footprint=Footprint(frozenset({"param:y"})))
    with pytest.raises(FootprintError) as raised:
        derive_commutation_edges([duplicate, other])
    assert "cv_clause_commit_unique" in str(raised.value)


def test_edges_for_clause_finds_a_version_from_either_end():
    edits = [
        edit("a", "param:x", commit_label="c1"),
        edit("b", "param:x", commit_label="c2"),
    ]
    edges = derive_commutation_edges(edits)
    for one in edits:
        found = edges_for_clause(
            edges, commit_id=one.ref.commit_id, clause_uuid=one.ref.clause_uuid
        )
        assert len(found) == 1


# --------------------------------------------------------------------------- #
# The write path                                                               #
# --------------------------------------------------------------------------- #


def test_the_insert_is_append_only_and_never_updates_a_row_a_gate_may_have_read():
    assert "ON CONFLICT" in COMMUTATION_EDGE_INSERT_SQL
    assert "DO NOTHING" in COMMUTATION_EDGE_INSERT_SQL
    assert "DO UPDATE" not in COMMUTATION_EDGE_INSERT_SQL
    assert "mainline.commutation_edge" in COMMUTATION_EDGE_INSERT_SQL


def test_the_bind_parameters_cover_every_placeholder_in_the_insert():
    import re

    placeholders = set(re.findall(r"%\((\w+)\)s", COMMUTATION_EDGE_INSERT_SQL))
    a = edit("a", "param:x", commit_label="c1")
    b = edit("b", "param:x", commit_label="c2")
    derived = edge_for(a, b)
    assert derived is not None
    assert set(derived.as_parameters()) == placeholders


def test_the_overlap_reaches_the_driver_as_a_list_because_cockroachdb_wants_an_array():
    a = edit("a", "param:x", "param:y", commit_label="c1")
    b = edit("b", "param:x", "param:y", commit_label="c2")
    derived = edge_for(a, b)
    assert derived is not None
    parameters = derived.as_parameters()
    assert parameters["footprint_overlap"] == ["param:x", "param:y"]
