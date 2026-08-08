# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""S2's pushdown must return exactly what S2's in-memory implementation returns.

:data:`ANCHOR_STAGE_SQL` exists so the anchor stage can run *inside* the
cluster over a real ``mainline.clause_version``, and :func:`anchor_stage` exists
so it can run over an in-memory corpus with no cluster at all.  Two
implementations of one gate is a place where a divergence would move a floor
without anyone editing a number, so the two are compared directly here — on the
kept set, which is the only thing a caller consumes.

Three separate platform facts are under test and each one is a way the statement
could be wrong while looking right:

* ``anchor_set @> $2 AND anchor_set <@ $2`` really is set equality on a
  ``STRING[]``, and the array binding really does reach the server as an array;
* ``%`` really is a trigram containment filter over ``canon_text``, and it never
  excludes a pair the 0.55 floor would have kept — which is the only direction
  that has to hold for the pushdown to be safe;
* ``similarity()`` really is orderable in a plain ``ORDER BY`` — the ``<->``
  distance-operator family is unsupported and nothing in this domain uses it.

Skips with a reason when no cluster is reachable, and a skipped run entitles
nobody to say the pushdown was verified.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from _w7_support import INSERT_CLAUSE_VERSION, SITE, build_corpus
from mainline_domain.anchors import extract_anchors
from mainline_domain.identity.candidates import (
    ANCHOR_STAGE_SQL,
    anchor_stage,
    identity_anchor_array,
    trigram_similarity,
)
from mainline_domain.identity.candidates.thresholds import DEFAULT_BANDS

pytestmark = pytest.mark.requires_cluster

CORPUS_SIZE = 60

#: A query whose identity anchors (``P-101A``, ``ISOL-4471``, ``PIT-1204``) are
#: shared by the planted near-duplicates and by nothing else in the corpus.
QUERY = (
    "The authorised person shall isolate pump P-101A at ISOL-4471 and verify zero "
    "energy at PIT-1204 before breaking containment."
)


@pytest.fixture
def versions(cluster_conn: Any) -> Any:
    """Load a corpus into ``mainline.clause_version``, anchor sets and all."""
    corpus = build_corpus(CORPUS_SIZE)
    rows = [
        {
            "clause_uuid": str(record.ref.clause_uuid),
            "commit_id": record.ref.commit_id,
            "site_id": str(SITE),
            "canon_text": record.canon_text,
            "canon_sha256": record.canon_sha256,
            "anchor_set": identity_anchor_array(record.anchors),
        }
        for record in corpus.records
    ]
    with cluster_conn.cursor() as cur:
        cur.executemany(INSERT_CLAUSE_VERSION, rows)
    return cluster_conn


def _pushdown(conn: Any, limit: int = 50) -> list[tuple[str, bytes, float]]:
    params = {
        "canon_text": QUERY,
        "site_id": str(SITE),
        "identity_anchors": identity_anchor_array(extract_anchors(QUERY)),
        "limit": limit,
    }
    with conn.cursor() as cur:
        cur.execute(ANCHOR_STAGE_SQL, params)
        return [(str(r[0]), bytes(r[1]), float(r[2])) for r in cur.fetchall()]


def test_the_statement_runs_and_binds_a_string_array(versions: Any) -> None:
    """The shape assertion is offline; that the server accepts it is not."""
    rows = _pushdown(versions)
    assert rows, (
        "the pushdown returned nothing at all: either the array binding did not reach "
        "the server as a STRING[], or `%` filtered every anchor-equal pair"
    )


def test_the_pushdown_agrees_with_the_in_memory_stage(versions: Any) -> None:
    """One gate, two implementations, one kept set."""
    corpus = build_corpus(CORPUS_SIZE)
    in_memory = anchor_stage(
        query_anchors=extract_anchors(QUERY),
        query_text=QUERY,
        corpus=corpus.records,
    )
    expected = {(str(c.ancestor_clause_uuid), c.ancestor_commit) for c in in_memory.candidates}
    from_sql = {
        (clause_uuid, commit_id)
        for clause_uuid, commit_id, trgm in _pushdown(versions)
        if trgm >= DEFAULT_BANDS.anchor_trigram_floor
    }
    assert from_sql == expected, (
        "S2's pushdown and S2's in-memory implementation disagree about which pairs "
        "clear the anchor gate and the trigram floor"
    )


def test_the_scores_agree_to_six_places(versions: Any) -> None:
    """``similarity()`` on the server must equal :func:`trigram_similarity` here."""
    corpus = {
        (str(r.ref.clause_uuid), r.ref.commit_id): r.canon_text
        for r in build_corpus(CORPUS_SIZE).records
    }
    for clause_uuid, commit_id, theirs in _pushdown(versions):
        ours = trigram_similarity(QUERY, corpus[(clause_uuid, commit_id)])
        assert abs(theirs - ours) < 1e-6, f"{clause_uuid}: cluster={theirs:.6f} python={ours:.6f}"


def test_the_containment_filter_keeps_everything_above_the_floor(versions: Any) -> None:
    """``%`` is a pre-filter; a pre-filter that drops a survivor is a bug.

    Checked against the *whole* corpus rather than against the statement's own
    output, because the failure this guards is the statement's output being
    short — a pair the in-memory stage keeps and the filter silently removed.
    """
    corpus = build_corpus(CORPUS_SIZE)
    query_anchors = identity_anchor_array(extract_anchors(QUERY))
    returned = {(u, c) for u, c, _ in _pushdown(versions, limit=CORPUS_SIZE * 2)}
    for record in corpus.records:
        if identity_anchor_array(record.anchors) != query_anchors:
            continue
        if trigram_similarity(QUERY, record.canon_text) < DEFAULT_BANDS.anchor_trigram_floor:
            continue
        key = (str(record.ref.clause_uuid), record.ref.commit_id)
        assert key in returned, (
            f"`%` excluded an anchor-equal pair scoring "
            f"{trigram_similarity(QUERY, record.canon_text):.3f}, above the "
            f"{DEFAULT_BANDS.anchor_trigram_floor} floor: {record.canon_text[:48]!r}"
        )


def test_an_anchor_swap_is_not_returned(versions: Any) -> None:
    """The gate is equality, so ``P-101B`` must not come back for a ``P-101A`` query.

    This is the S2 half of the same refusal S4 makes with the veto.  It is
    asserted against the *server's* operators rather than against Python's set
    comparison, because ``@>``/``<@`` are what decide it in production.
    """
    swapped = QUERY.replace("P-101A", "P-101B").replace("ISOL-4471", "ISOL-9999")
    ref_uuid = uuid.uuid5(uuid.NAMESPACE_URL, "mainline/w7/anchor-swap")
    with versions.cursor() as cur:
        cur.execute(
            INSERT_CLAUSE_VERSION,
            {
                "clause_uuid": str(ref_uuid),
                "commit_id": b"\xbb" * 32,
                "site_id": str(SITE),
                "canon_text": swapped,
                "canon_sha256": b"\x00" * 32,
                "anchor_set": identity_anchor_array(extract_anchors(swapped)),
            },
        )
    assert trigram_similarity(QUERY, swapped) > DEFAULT_BANDS.anchor_trigram_floor, (
        "the fixture is not exercising the gate: the swapped clause is below the "
        "trigram floor, so it would be excluded for the wrong reason"
    )
    assert str(ref_uuid) not in {u for u, _, _ in _pushdown(versions, limit=CORPUS_SIZE * 2)}
