# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The SQL band probe must return exactly what the reference implementation does.

``InMemoryBandIndex`` is not a convenience — it is the thing the statement is
checked *against*.  Every unit test in this package runs over it, so if the SQL
and the reference ever disagreed, the entire offline suite would be measuring an
algorithm the product does not run.

Also asserted here: the documented alternative probe shape (a single tuple-``IN``
instead of sixteen ``UNION ALL``'d equality selects) returns the same rows.  The
package does not use it, and the reason is written down in ``band.py``: sixteen
fully-constrained selects have exactly one possible plan shape and the tuple
form's is an optimiser outcome.  This test is what would let that choice be
revisited on evidence rather than on preference.

Skips with a reason when no cluster is reachable.  A skipped run proves nothing
and the skip message says so.
"""

from __future__ import annotations

from typing import Any

import pytest
from _w7_support import SITE, build_corpus
from mainline_domain.identity.candidates import (
    INSERT_BAND_SQL,
    InMemoryBandIndex,
    band_hashes,
    band_probe_params,
    band_probe_sql,
    band_rows,
    signature,
)

pytestmark = pytest.mark.requires_cluster

CORPUS_SIZE = 120


@pytest.fixture
def loaded(cluster_conn: Any) -> tuple[Any, InMemoryBandIndex, tuple[int, ...], str]:
    """The same corpus in the cluster and in the reference index."""
    corpus = build_corpus(CORPUS_SIZE)
    reference = InMemoryBandIndex(SITE)
    rows = []
    for record in corpus.records:
        sig = signature(record.canon_text)
        reference.add(record.ref, sig)
        rows.extend(band_rows(SITE, record.ref, sig))

    with cluster_conn.cursor() as cur:
        cur.executemany(INSERT_BAND_SQL, [r.as_params() for r in rows])
    return cluster_conn, reference, signature(corpus.query_text), corpus.query_text


def test_the_sql_probe_agrees_with_the_reference_implementation(
    loaded: tuple[Any, InMemoryBandIndex, tuple[int, ...], str],
) -> None:
    conn, reference, query_signature, _ = loaded
    hashes = band_hashes(query_signature)

    with conn.cursor() as cur:
        cur.execute(band_probe_sql(len(hashes)), band_probe_params(SITE, hashes))
        from_sql = {(str(row[0]), bytes(row[1])): int(row[2]) for row in cur.fetchall()}

    expected = {
        (str(ref.clause_uuid), ref.commit_id): hits
        for ref, hits in reference.probe(query_signature).items()
    }
    assert from_sql == expected


def test_the_probe_is_idempotent_because_a_clause_version_is_immutable(
    loaded: tuple[Any, InMemoryBandIndex, tuple[int, ...], str],
) -> None:
    """Re-inserting every band row changes nothing: ``ON CONFLICT DO NOTHING``."""
    conn = loaded[0]
    corpus = build_corpus(CORPUS_SIZE)
    rows = [
        row
        for record in corpus.records
        for row in band_rows(SITE, record.ref, signature(record.canon_text))
    ]
    with conn.cursor() as cur:
        cur.executemany(INSERT_BAND_SQL, [r.as_params() for r in rows])
        cur.execute("SELECT count(*) FROM mainline.clause_band")
        total = int(cur.fetchone()[0])
    assert total == CORPUS_SIZE * 16


def test_the_tuple_in_alternative_returns_the_same_rows(
    loaded: tuple[Any, InMemoryBandIndex, tuple[int, ...], str],
) -> None:
    """Characterising the shape the package deliberately does not use."""
    conn, _, query_signature, _ = loaded
    hashes = band_hashes(query_signature)

    tuples = ", ".join(f"(%(b{i})s::INT2, %(h{i})s::INT8)" for i in range(len(hashes)))
    alt_sql = (
        "SELECT clause_uuid, commit_id, count(*)::INT8 AS band_hits\n"  # noqa: S608
        "  FROM mainline.clause_band\n"
        " WHERE site_id = %(site_id)s\n"
        f"   AND (band_no, band_hash) IN ({tuples})\n"
        " GROUP BY clause_uuid, commit_id\n"
        " ORDER BY band_hits DESC, clause_uuid, commit_id"
    )
    alt_params: dict[str, object] = {"site_id": str(SITE)}
    for i, value in enumerate(hashes):
        alt_params[f"b{i}"] = i
        alt_params[f"h{i}"] = value

    with conn.cursor() as cur:
        cur.execute(band_probe_sql(len(hashes)), band_probe_params(SITE, hashes))
        union = [(str(r[0]), bytes(r[1]), int(r[2])) for r in cur.fetchall()]
        cur.execute(alt_sql, alt_params)
        tuple_in = [(str(r[0]), bytes(r[1]), int(r[2])) for r in cur.fetchall()]

    assert sorted(union) == sorted(tuple_in)


def test_the_probe_plan_contains_no_full_scan(
    loaded: tuple[Any, InMemoryBandIndex, tuple[int, ...], str],
) -> None:
    """The cost claim, read off the plan the cluster actually chose.

    Sixteen selects, each binding the whole ``(site_id, band_no, band_hash)``
    primary-key prefix.  A ``FULL SCAN`` anywhere in that plan means S3's cost
    grows with the corpus and the stage's entire justification is gone.
    """
    conn, _, query_signature, _ = loaded
    hashes = band_hashes(query_signature)
    with conn.cursor() as cur:
        cur.execute("EXPLAIN " + band_probe_sql(len(hashes)), band_probe_params(SITE, hashes))
        plan = "\n".join(str(row[0]) for row in cur.fetchall())
    assert "FULL SCAN" not in plan.upper(), plan


def test_band_hashes_survive_the_int8_round_trip(cluster_conn: Any) -> None:
    """A signed fold that the column could not hold would fail on some rows only."""
    text = "The authorised person shall isolate pump P-101A before breaking containment."
    hashes = band_hashes(signature(text))
    corpus = build_corpus(8)
    rows = band_rows(SITE, corpus.records[0].ref, signature(text))

    with cluster_conn.cursor() as cur:
        cur.executemany(INSERT_BAND_SQL, [r.as_params() for r in rows])
        cur.execute(
            "SELECT band_no, band_hash FROM mainline.clause_band "
            "WHERE site_id = %s ORDER BY band_no",
            (str(SITE),),
        )
        stored = [(int(a), int(b)) for a, b in cur.fetchall()]

    assert stored == list(enumerate(hashes))
