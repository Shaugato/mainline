# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Layer 2: the cascade's work must grow sublinearly as the corpus doubles.

Plan text proves the optimiser *intended* to use an index.  It proves nothing
about what happened, and **a silently unused index scales linearly regardless of
how the plan text is formatted**.  So the plan assertion is not enough, and this
file is the other half.

What is measured, and why it is a *count* rather than a wall clock:

* **Work** is the number of pairs S3 had to rescore — every candidate plus
  every drop that came from a band hit.  Rescoring is the expensive operation
  (an LCS over tokens, a patience diff, a trigram shred, an exact Jaccard); the
  band probe is sixteen hash lookups.  If banding degenerated into a scan, work
  would rise with the corpus.
* A count is **deterministic**.  It is the same number on a laptop, on a loaded
  CI runner and in three years.  A wall-clock assertion on a shared runner is a
  test that fails on a Tuesday and teaches everyone to re-run it — which is how
  a suite stops being read.  The wall clock is measured too, and it is *printed
  into the assertion message*, but it is not what decides.

The cluster-backed counterpart — the same doubling against
``mainline.clause_band`` over pgwire, where latency is the observable — is in
:func:`test_band_probe_latency_grows_sublinearly` and skips with a reason when
no cluster is reachable.
"""

from __future__ import annotations

import time
from itertools import pairwise

import pytest
from _support import build_corpus, prefixes
from mainline_domain.identity.candidates import (
    LexicalCorpus,
    band_hashes,
    band_probe_params,
    band_probe_sql,
    band_rows,
    lexical_stage,
    signature,
)

SIZES = (100, 200, 400, 800)
LARGEST = SIZES[-1]


@pytest.fixture(scope="module")
def measured() -> tuple[tuple[int, int, float], ...]:
    """``(corpus_size, rescored_pairs, probe_seconds)`` at each size.

    The corpus is built once and measured on successive prefixes, so each
    clause is signed exactly once — 800 signatures, not 1500.
    """
    corpus = build_corpus(LARGEST)
    index = LexicalCorpus()
    query_signature = signature(corpus.query_text, index.params)

    out: list[tuple[int, int, float]] = []
    added = 0
    for size, prefix in prefixes(corpus, SIZES):
        for record in prefix.records[added:]:
            index.add(record)
        added = size

        start = time.perf_counter()
        result = lexical_stage(
            query_text=prefix.query_text,
            corpus=index,
            query_signature=query_signature,
        )
        elapsed = time.perf_counter() - start

        rescored = len(result.candidates) + sum(
            1 for d in result.dropped if d.reason != "band_miss"
        )
        out.append((size, rescored, elapsed))
    return tuple(out)


def _render(measured: tuple[tuple[int, int, float], ...]) -> str:
    return " | ".join(f"N={n}: work={w}, {s * 1000:.1f}ms" for n, w, s in measured)


@pytest.mark.slow
def test_the_planted_near_duplicates_are_always_found() -> None:
    """Guard the guard: work that is sublinear because nothing is found proves nothing."""
    corpus = build_corpus(LARGEST)
    index = LexicalCorpus()
    index.extend(corpus.records)
    result = lexical_stage(query_text=corpus.query_text, corpus=index)
    found = {c.ancestor_clause_uuid for c in result.candidates}
    missing = [ref for ref in corpus.planted if ref.clause_uuid not in found]
    assert not missing, f"{len(missing)} of {len(corpus.planted)} planted near-duplicates missed"


@pytest.mark.slow
def test_work_grows_sublinearly_as_the_corpus_doubles(
    measured: tuple[tuple[int, int, float], ...],
) -> None:
    """Eight times the corpus must not mean eight times the work."""
    first_size, first_work, _ = measured[0]
    last_size, last_work, _ = measured[-1]
    corpus_growth = last_size / first_size
    work_growth = last_work / max(first_work, 1)

    assert work_growth < corpus_growth / 2, (
        f"work grew {work_growth:.2f}x while the corpus grew {corpus_growth:.0f}x — "
        f"banding is behaving like a scan. {_render(measured)}"
    )


@pytest.mark.slow
def test_work_per_clause_falls_at_every_doubling(
    measured: tuple[tuple[int, int, float], ...],
) -> None:
    """The sublinearity, stated as a monotone quantity rather than a ratio."""
    per_clause = [work / size for size, work, _ in measured]
    for earlier, later in pairwise(per_clause):
        assert later < earlier, (
            f"work per clause did not fall at a doubling: {per_clause}. {_render(measured)}"
        )


@pytest.mark.slow
def test_the_band_index_keeps_discriminating_as_it_grows() -> None:
    """The complement of the claim: the *index* grows, the *lookup* does not.

    Sixteen rows per clause, always — so if the number of populated buckets
    stopped growing, the corpus would be collapsing into a few buckets and the
    low work count in the tests above would be a collision problem wearing a
    performance costume.

    The bound is on **growth**, not on an absolute rows-per-clause figure,
    because this fixture corpus is deliberately templated (four subjects, four
    verbs, four objects, three tails, plus a unique work-order reference) and
    templated clauses genuinely do share bands.  Real procedure text shares
    fewer.  Measured here: 11.4 buckets per clause at N=100 falling to 8.0 at
    N=800 — falling, because collisions accumulate, but the bucket count still
    grows at better than half the corpus rate.
    """
    corpus = build_corpus(LARGEST)
    index = LexicalCorpus()
    counts: list[tuple[int, int]] = []
    added = 0
    for size, prefix in prefixes(corpus, SIZES):
        for record in prefix.records[added:]:
            index.add(record)
        added = size
        counts.append((size, index.bucket_count))

    assert index.size == LARGEST
    corpus_growth = counts[-1][0] / counts[0][0]
    bucket_growth = counts[-1][1] / counts[0][1]
    assert bucket_growth > corpus_growth / 2, (
        f"populated buckets grew only {bucket_growth:.2f}x for a {corpus_growth:.0f}x "
        f"corpus: {counts}. The signatures are collapsing, not discriminating"
    )
    assert all(later > earlier for (_, earlier), (_, later) in pairwise(counts))


@pytest.mark.slow
def test_every_rescored_pair_is_accounted_for() -> None:
    """Nothing silently drops, at any corpus size."""
    corpus = build_corpus(LARGEST)
    index = LexicalCorpus()
    index.extend(corpus.records)
    query_signature = signature(corpus.query_text, index.params)
    result = lexical_stage(
        query_text=corpus.query_text, corpus=index, query_signature=query_signature
    )
    probed = set(index.probe(query_signature))
    reported = {c.ancestor_clause_uuid for c in result.candidates} | {
        d.ancestor_clause_uuid for d in result.dropped
    }
    assert {ref.clause_uuid for ref in probed} == reported


# --------------------------------------------------------------------------- #
# The same claim where latency is the observable.  Needs a cluster.            #
# --------------------------------------------------------------------------- #


@pytest.mark.requires_cluster
@pytest.mark.slow
def test_band_probe_latency_grows_sublinearly(cluster_conn: object) -> None:
    """Sixteen point lookups against a real ``mainline.clause_band``.

    The bound is deliberately loose (4x latency for 8x data, against a linear
    scan's 8x) because this runs on whatever machine happens to be free.  A
    tight bound here would be a flaky test pretending to be a precise one; what
    is being refuted is *linear*, and 4x refutes it.
    """
    from _support import SITE, build_corpus

    conn: object = cluster_conn
    corpus = build_corpus(LARGEST)
    signatures = {r.ref: signature(r.canon_text) for r in corpus.records}
    query_bands = band_hashes(signature(corpus.query_text))
    probe = band_probe_sql(len(query_bands))
    params = band_probe_params(SITE, query_bands)

    timings: list[tuple[int, float]] = []
    inserted = 0
    for size in (SIZES[0], LARGEST):
        rows = [
            row
            for record in corpus.records[inserted:size]
            for row in band_rows(SITE, record.ref, signatures[record.ref])
        ]
        with conn.cursor() as cur:  # type: ignore[attr-defined]
            from mainline_domain.identity.candidates import INSERT_BAND_SQL

            cur.executemany(INSERT_BAND_SQL, [r.as_params() for r in rows])
        inserted = size

        with conn.cursor() as cur:  # type: ignore[attr-defined]
            cur.execute(probe, params)  # warm
            cur.fetchall()
            start = time.perf_counter()
            for _ in range(5):
                cur.execute(probe, params)
                cur.fetchall()
            timings.append((size, (time.perf_counter() - start) / 5))

    small, large = timings[0][1], timings[1][1]
    growth = large / max(small, 1e-6)
    assert growth < 4.0, (
        f"band probe latency grew {growth:.2f}x for an {LARGEST // SIZES[0]}x corpus "
        f"({small * 1000:.2f}ms -> {large * 1000:.2f}ms); sixteen primary-key point "
        f"lookups should be near-flat"
    )
