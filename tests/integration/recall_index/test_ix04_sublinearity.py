# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""IX-04 — layer 2: the behavioural proof. Plan text is not evidence of execution.

**A silently unused index scales linearly regardless of how the plan text is formatted.** So
the second layer is a number: per-arm p50 latency across a corpus that doubles twice —
5 000 → 10 000 → 20 000 scoped vectors — with ``t(2n)/t(n) < 1.7`` required at each doubling,
measured as the median of three runs.

1.7 is not a theoretical bound. An approximate-nearest-neighbour lookup over a K-means tree
should be close to flat. 1.7 is a **deliberately loose ceiling that a linear scan cannot
pass**: a scan doubles, giving 2.0. The test is therefore insensitive to machine noise and
sensitive to exactly the failure it exists to catch.

Two more assertions ride along, and both are load-bearing:

* **the planted precursor.** A plan can be perfect and the executor can still return the
  wrong neighbours. A cue written deliberately close to the query vector must come back in
  top-k, at every corpus size, or the arm is fast and useless.
* **the instrument's own sensitivity.** The same measurement is run against a forced
  full-scan variant. If the scan's curve is not visibly worse than the index's, the harness
  cannot tell the two apart on this machine and *none* of the green results above are
  evidence. That control is the red half of this module.
"""

from __future__ import annotations

import json
import time

import pytest
from _support import (
    ARTEFACTS,
    CUE_SCOPED,
    CUE_SWEEP,
    POPULATED_FACETS,
    CorpusState,
    env_int,
    env_sizes,
    grow_corpus,
    plant_precursor,
    policy,
    time_query,
    unit_vector,
    vector_literal,
    warm,
)

from trappoint_recall.arms import (
    DEFAULT_SUBLINEARITY_LIMIT,
    AncestorChain,
    ArmSet,
    PlaceholderStyle,
    SqlForm,
    SweepRequest,
    arm_sql,
    generate_arms,
    sublinearity_verdict,
)
from trappoint_recall.arms.measure import run_median_p50

pytestmark = [pytest.mark.behaviour, pytest.mark.slow]

#: The doubling sequence. Overridable for a smoke run; the nightly lane uses the default,
#: which is the sequence the domain's decision D13 is stated over.
SIZES = env_sizes("MAINLINE_RECALL_INDEX_SIZES", (5000, 10000, 20000))
#: Executions per run, and runs per point. Three runs because one measures the machine's mood
#: and two cannot break a tie.
REPEATS = env_int("MAINLINE_RECALL_INDEX_REPEATS", 10)
RUNS = env_int("MAINLINE_RECALL_INDEX_RUNS", 3)


def _arms(corpus: CorpusState) -> ArmSet:
    return generate_arms(
        site=corpus.taxonomy.site_id,
        chain=AncestorChain.of("permit-slice-1", corpus.taxonomy.levels),
        facet_vectors={f: unit_vector(1024, f"query/{f}") for f in POPULATED_FACETS},
        policy=policy(),
        scoped_table=CUE_SCOPED,
        sweep=SweepRequest(
            tenant=corpus.taxonomy.tenant_id,
            query_vector=unit_vector(256, "query/coarse"),
            table=CUE_SWEEP,
        ),
    )


def _brute_force_sql(corpus: CorpusState, vector: tuple[float, ...], k: int) -> str:
    """The same top-k, forced through the primary index. The control's slow half.

    ``FORCE_INDEX=[1]`` names the primary index by ID rather than by name, so a CockroachDB
    release that renames it cannot silently turn this control back into an indexed query.
    """
    return (
        f"SELECT e.cue_id, e.emb <=> '{vector_literal(vector)}'::VECTOR(1024) AS dist\n"
        f"  FROM {CUE_SCOPED.qualified_name}@{{FORCE_INDEX=[1]}} AS e\n"
        f" WHERE e.site_id = '{corpus.taxonomy.site_id}'\n"
        f"   AND e.scope_id = '{corpus.taxonomy.file}'\n"
        f"   AND e.facet = '{POPULATED_FACETS[0]}'\n"
        f" ORDER BY dist\n"
        f" LIMIT {k}"
    )


@pytest.fixture(scope="module")
def measurements(session_conn: object, corpus: CorpusState) -> dict:
    """Grow the corpus through the sequence, timing every arm at every point.

    Growth is additive: one corpus measured three times, not three corpora. Three separate
    corpora would confound "the index scaled" with "the data changed".
    """
    arms = _arms(corpus)
    per_arm: dict[str, dict[int, float]] = {arm.arm_id: {} for arm in arms.arms}
    brute: dict[int, float] = {}
    planted_hits: dict[int, bool] = {}
    scoped = arms.scoped[0]

    for size in SIZES:
        started = time.perf_counter()
        grow_corpus(session_conn, corpus, target_vectors=size)
        if corpus.planted_cue_id is None:
            plant_precursor(
                session_conn,
                corpus,
                query_vector=scoped.query_vector,
                facet=scoped.facet or POPULATED_FACETS[0],
                level=scoped.level,
            )
        build_s = time.perf_counter() - started

        for arm in arms.arms:
            rendered = arm_sql(
                arm, form=SqlForm.EXECUTE, placeholder_style=PlaceholderStyle.PYFORMAT
            )
            statement = f"SELECT * FROM {rendered.text} AS hit"
            warm(session_conn, statement, rendered.params)
            runs = [
                time_query(session_conn, statement, rendered.params, repeats=REPEATS).milliseconds
                for _ in range(RUNS)
            ]
            per_arm[arm.arm_id][size] = run_median_p50(runs)

        control = _brute_force_sql(corpus, scoped.query_vector, scoped.k)
        warm(session_conn, control, repeats=1)
        brute[size] = run_median_p50(
            [
                time_query(session_conn, control, repeats=max(2, REPEATS // 3)).milliseconds
                for _ in range(RUNS)
            ]
        )

        hit_sql = f"SELECT * FROM {arm_sql(scoped, form=SqlForm.LITERAL).text} AS hit"
        rows = session_conn.execute(hit_sql).fetchall()  # type: ignore[attr-defined]
        planted_hits[size] = any(str(row[0]) == str(corpus.planted_cue_id) for row in rows)
        print(
            f"[ix04] n={size} built in {build_s:.1f}s · "
            f"arm p50 {per_arm[scoped.arm_id][size]:.2f}ms · "
            f"forced scan p50 {brute[size]:.2f}ms · planted in top-k: {planted_hits[size]}"
        )

    return {"arms": arms, "per_arm": per_arm, "brute": brute, "planted": planted_hits}


def test_ix04_every_arm_scales_sublinearly_across_the_doubling(measurements: dict) -> None:
    verdicts = [
        sublinearity_verdict(arm_id=arm_id, p50_by_size=points, limit=DEFAULT_SUBLINEARITY_LIMIT)
        for arm_id, points in measurements["per_arm"].items()
    ]
    ARTEFACTS.mkdir(parents=True, exist_ok=True)
    (ARTEFACTS / "sublinearity.json").write_text(
        json.dumps(
            {
                "artefact": "per-arm-sublinearity",
                "schema_version": 1,
                "limit": DEFAULT_SUBLINEARITY_LIMIT,
                "sizes": list(SIZES),
                "repeats_per_run": REPEATS,
                "runs": RUNS,
                "arms": [v.as_dict() for v in verdicts],
                "forced_scan_control_ms": measurements["brute"],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    failed = [v for v in verdicts if not v.ok]
    assert not failed, (
        "an arm's latency grew at least linearly as the corpus doubled, which is what an "
        "unused index looks like however the plan text is formatted:\n"
        + "\n".join(v.describe() for v in failed)
    )


def test_ix04_the_planted_precursor_is_returned_at_every_corpus_size(measurements: dict) -> None:
    missed = [size for size, hit in measurements["planted"].items() if not hit]
    assert not missed, (
        f"the planted precursor was NOT in top-k at n={missed}. A plan can be perfect while "
        "the executor returns the wrong neighbours; in this product that difference is a "
        "precursor that did not block a permit."
    )


def test_ix04_red_the_measurement_can_tell_a_scan_from_an_index(measurements: dict) -> None:
    """The instrument's sensitivity check — the red half of layer two.

    If a forced full scan's curve is not visibly worse than the arms' curves on this machine,
    then the harness cannot distinguish the two and every green result above is unearned. The
    assertion is comparative on purpose: an absolute latency threshold would be a statement
    about the machine, not about the index.
    """
    scan = sublinearity_verdict(
        arm_id="forced-full-scan-control",
        p50_by_size=measurements["brute"],
        limit=DEFAULT_SUBLINEARITY_LIMIT,
    )
    arms_worst = max(
        max(r.ratio for r in sublinearity_verdict(arm_id=a, p50_by_size=p).ratios)
        for a, p in measurements["per_arm"].items()
    )
    scan_worst = max(r.ratio for r in scan.ratios)
    print(f"[ix04] worst arm ratio {arms_worst:.3f} vs forced-scan ratio {scan_worst:.3f}")
    assert scan_worst > arms_worst, (
        "a forced full scan did not scale worse than the constrained arms. Either the corpus "
        "is too small for the difference to show, or the arms are not using the index either. "
        f"scan {scan_worst:.3f} vs worst arm {arms_worst:.3f}"
    )
    assert scan_worst >= 1.4, (
        f"the forced full scan's latency ratio was {scan_worst:.3f}; a scan over a doubling "
        "corpus should approach 2.0. Below 1.4 the measurement is dominated by fixed overhead "
        "and is not sensitive enough for the green assertions above to mean anything."
    )
