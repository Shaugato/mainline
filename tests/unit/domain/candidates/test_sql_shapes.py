# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The statements are pure functions, so their shape is assertable without a cluster.

No cluster is reachable from the build machine and AWS credentials are not
valid, so nothing here may *require* either.  What can be proven offline is
substantial and is exactly the part that goes wrong quietly:

* every band probe binds the whole primary-key prefix (``site_id``,
  ``band_no``, ``band_hash``) to a specific value — the property that makes S3
  sixteen point lookups instead of a scan;
* every ANN arm binds both C-SPANN prefix columns to a specific value, and no
  statement anywhere in this package contains ``IN (`` on a prefix column;
* no statement orders by a trigram distance operator, because CockroachDB does
  not support one.

The live counterparts live in ``tests/integration/algorithms/candidates/`` and
skip, with a reason naming the missing DSN, when no cluster is up.
"""

from __future__ import annotations

import re
import uuid

import pytest
from mainline_domain.identity.candidates import (
    ANCHOR_STAGE_SQL,
    ARM_SQL,
    EXACT_SQL,
    INSERT_BAND_SQL,
    Arm,
    ClauseRef,
    InMemoryBandIndex,
    band_hashes,
    band_probe_params,
    band_probe_sql,
    band_rows,
    identity_anchor_array,
    signature,
    vector_literal,
)
from mainline_domain.identity.candidates.semantic import arm_union_sql, arms_for

SITE = uuid.UUID("11111111-1111-4111-8111-111111111111")
REF = ClauseRef(uuid.UUID("22222222-2222-4222-8222-222222222222"), b"\xaa" * 32)
CLAUSE = "The authorised person shall isolate pump P-101A before breaking containment."

ALL_STATEMENTS = (ANCHOR_STAGE_SQL, ARM_SQL, EXACT_SQL, INSERT_BAND_SQL, band_probe_sql(16))


# --------------------------------------------------------------------------- #
# banding                                                                     #
# --------------------------------------------------------------------------- #


def test_a_clause_contributes_exactly_one_row_per_band() -> None:
    rows = band_rows(SITE, REF, signature(CLAUSE))
    assert len(rows) == 16
    assert [r.band_no for r in rows] == list(range(16))
    assert all(r.site_id == SITE and r.clause_uuid == REF.clause_uuid for r in rows)


def test_every_band_hash_fits_a_signed_int8() -> None:
    """``band_hash INT8`` is signed; an unsigned fold would fail on some rows only."""
    for value in band_hashes(signature(CLAUSE)):
        assert -(2**63) <= value < 2**63


def test_band_hashes_are_deterministic_and_change_with_the_text() -> None:
    first = band_hashes(signature(CLAUSE))
    assert first == band_hashes(signature(CLAUSE))
    other = band_hashes(signature(CLAUSE.replace("P-101A", "P-101B")))
    assert first != other


def test_the_probe_binds_the_whole_primary_key_prefix() -> None:
    """Sixteen fully-constrained selects: the cost claim, in the statement text."""
    sql = band_probe_sql(16)
    assert sql.count("UNION ALL") == 15
    for i in range(16):
        assert f"band_no = {i} AND band_hash = %(h{i})s" in sql
    assert sql.count("site_id = %(site_id)s") == 16
    assert "IN (" not in sql


def test_the_probe_statement_is_a_pure_function_of_the_band_count() -> None:
    assert band_probe_sql(16) == band_probe_sql(16)
    assert band_probe_sql(4) != band_probe_sql(16)
    with pytest.raises(ValueError, match="n_bands"):
        band_probe_sql(0)


def test_the_probe_parameters_line_up_with_the_statement() -> None:
    hashes = band_hashes(signature(CLAUSE))
    params = band_probe_params(SITE, hashes)
    placeholders = set(re.findall(r"%\((\w+)\)s", band_probe_sql(len(hashes))))
    assert placeholders == set(params)


def test_the_insert_is_idempotent_by_construction() -> None:
    assert "ON CONFLICT DO NOTHING" in INSERT_BAND_SQL


def test_the_row_parameters_are_driver_ready() -> None:
    row = band_rows(SITE, REF, signature(CLAUSE))[0]
    params = row.as_params()
    assert set(params) == {"site_id", "band_no", "band_hash", "clause_uuid", "commit_id"}
    assert params["commit_id"] == REF.commit_id


def test_the_in_memory_index_reproduces_the_bands_it_would_insert() -> None:
    """The reference implementation and the SQL path share one band computation."""
    index = InMemoryBandIndex(SITE)
    emitted = index.add(REF, signature(CLAUSE))
    assert emitted == band_rows(SITE, REF, signature(CLAUSE))
    assert index.bucket_count == 16
    assert dict(index.probe(signature(CLAUSE))) == {REF: 16}


# --------------------------------------------------------------------------- #
# the ANN arms                                                                #
# --------------------------------------------------------------------------- #


def test_an_arm_binds_both_prefix_columns_to_a_specific_value() -> None:
    assert "site_id = %(site_id)s" in ARM_SQL
    assert "activity_root = %(activity_root)s" in ARM_SQL
    assert "IN (" not in ARM_SQL


def test_the_arm_orders_by_the_vector_cosine_operator() -> None:
    """``<=>`` pairs with ``vector_cosine_ops``; the score is ``1 - distance``."""
    assert "ORDER BY embedding <=> %(q)s::VECTOR" in ARM_SQL
    assert "1 - (embedding <=> %(q)s::VECTOR)" in ARM_SQL


def test_the_fan_out_is_union_all_of_single_valued_arms() -> None:
    sql = arm_union_sql(3)
    assert sql.count("UNION ALL") == 2
    for i in range(3):
        assert f"activity_root = %(activity_root_{i})s" in sql
    assert "IN (" not in sql


def test_arms_are_deduplicated_in_first_appearance_order() -> None:
    arms = arms_for(SITE, ["b", "a", "b"])
    assert arms == (Arm(SITE, "b"), Arm(SITE, "a"))


def test_an_empty_activity_root_is_refused() -> None:
    with pytest.raises(ValueError, match="specific value"):
        arms_for(SITE, [""])


def test_an_empty_arm_set_is_refused() -> None:
    with pytest.raises(ValueError, match="cannot be empty"):
        arms_for(SITE, [])


def test_the_vector_literal_round_trips_exactly() -> None:
    q = [0.1, -2.5, 3.0]
    literal = vector_literal(q)
    assert literal == "[0.1,-2.5,3.0]"
    assert [float(x) for x in literal.strip("[]").split(",")] == q


def test_arm_parameters_carry_the_literal_and_the_limit() -> None:
    params = Arm(SITE, "maintenance").params([1.0, 2.0], 8)
    assert params["activity_root"] == "maintenance"
    assert params["q"] == "[1.0,2.0]"
    assert params["k"] == 8


# --------------------------------------------------------------------------- #
# platform traps, asserted across every statement this package ships          #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("statement", ALL_STATEMENTS)
def test_no_statement_uses_an_unsupported_trigram_function(statement: str) -> None:
    """``word_similarity`` and ``strict_word_similarity`` do not exist in CockroachDB."""
    lowered = statement.lower()
    assert "word_similarity" not in lowered
    assert "strict_word_similarity" not in lowered


@pytest.mark.parametrize("statement", ALL_STATEMENTS)
def test_no_statement_orders_by_a_trigram_distance_operator(statement: str) -> None:
    """The ``<->`` family is unsupported for trigrams; filter with ``%``, score with
    ``similarity()``.  The ``<=>`` on a VECTOR column is a different operator and is
    the one the ANN arm is allowed to use."""
    assert "<->" not in statement
    assert "<%" not in statement
    assert "%>" not in statement


@pytest.mark.parametrize("statement", ALL_STATEMENTS)
def test_no_statement_uses_a_banned_sequence_primitive(statement: str) -> None:
    """The ledger is gap-free by CAS; sequences are banned repository-wide."""
    lowered = statement.lower()
    for banned in ("nextval", "unique_rowid", "create sequence", "serial"):
        assert banned not in lowered


def test_the_anchor_stage_uses_containment_both_ways_for_set_equality() -> None:
    assert "anchor_set @> %(identity_anchors)s" in ANCHOR_STAGE_SQL
    assert "anchor_set <@ %(identity_anchors)s" in ANCHOR_STAGE_SQL
    assert "canon_text %% %(canon_text)s" in ANCHOR_STAGE_SQL
    assert "ORDER BY trgm DESC" in ANCHOR_STAGE_SQL


def test_the_identity_anchor_binding_is_sorted_and_deduplicated() -> None:
    from mainline_domain.anchors import extract_anchors

    anchors = extract_anchors("isolate P-101A at ISOL-4471 and P-101A again")
    binding = identity_anchor_array(anchors)
    assert binding == sorted(set(binding))


def test_the_exact_stage_uses_the_declared_digest_index_columns() -> None:
    assert "site_id = %(site_id)s" in EXACT_SQL
    assert "canon_sha256 = %(canon_sha256)s" in EXACT_SQL
    assert "ORDER BY clause_uuid, commit_id" in EXACT_SQL
