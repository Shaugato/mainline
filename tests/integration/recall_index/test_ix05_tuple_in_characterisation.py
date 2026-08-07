# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""IX-05 — layer 3: the nightly characterisation of the form we did NOT ship.

Tuple-``IN`` over prefix columns is documented and supported. It is not shipped, for three
reasons stated in :mod:`trappoint_recall.arms.tuple_in`. This module is what keeps that
decision *evidence-based* rather than *historical*: it exercises the form at span counts below
and above the runtime value of ``optimizer_span_limit``, against brute force on a fixed
5 000-vector fixture, and records what happened.

**``optimizer_span_limit`` is read at runtime with ``SHOW``. It is never assumed.** The
setting shipped in v25.4 and its default is a version-dependent implementation detail; a
characterisation test that hard-coded a value would be characterising its own assumption, and
the whole point of a characterisation test is that it has none.

**This test is EXPECTED to change across versions. That is its purpose.** The first run writes
a baseline; later runs compare against it and fail loudly on drift, with a message that says
the correct response is to look at what changed and update the baseline **deliberately** —
not to silence the test. The two things it asserts unconditionally, because they are not
version-dependent, are that the brute-force oracle really is exhaustive and that the span
counts are the ones the probe was built to have.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest
from _support import (
    ARTEFACTS,
    CUE_SCOPED,
    POPULATED_FACETS,
    CorpusState,
    env_int,
    grow_corpus,
    pgwire_explain_source,
    read_setting,
    unit_vector,
)
from trappoint_recall.arms import parse_explain
from trappoint_recall.arms.tuple_in import (
    SHIPPED,
    SPAN_LIMIT_SETTING,
    TupleInProbe,
    brute_force_sql,
    tuple_in_sql,
)

pytestmark = [pytest.mark.nightly, pytest.mark.slow]

FIXTURE_ROWS = env_int("MAINLINE_RECALL_INDEX_TUPLEIN_ROWS", 5000)
BASELINE = ARTEFACTS / "tuple_in_characterisation.json"
K = 12


def test_ix05_the_shipped_answer_is_recorded_as_a_constant() -> None:
    """Greppable. "Do you ship tuple-IN?" must be answerable without reading prose."""
    assert SHIPPED is False


@pytest.fixture(scope="module")
def probe_context(session_conn: object, corpus: CorpusState) -> dict:
    grow_corpus(session_conn, corpus, target_vectors=FIXTURE_ROWS)
    limit_raw = read_setting(session_conn, SPAN_LIMIT_SETTING)
    if limit_raw is None:
        pytest.skip(
            f"this cluster does not know `{SPAN_LIMIT_SETTING}` (it shipped in v25.4). That "
            "is information, not a pass: the cliff this test characterises may not exist here."
        )
    try:
        span_limit = int(str(limit_raw).strip())
    except ValueError:  # pragma: no cover - a non-integer setting is a platform change
        pytest.skip(f"`{SPAN_LIMIT_SETTING}` read back as {limit_raw!r}, which is not an integer")
    print(f"[ix05] {SPAN_LIMIT_SETTING} read at runtime = {span_limit}")
    return {"span_limit": span_limit, "corpus": corpus}


def _probe(corpus: CorpusState, *, spans: int) -> TupleInProbe:
    """A probe with exactly ``spans`` distinct prefix tuples.

    Real scopes are used where they exist and synthetic UUIDs pad the rest: the spans the
    optimizer must build are what is being varied, and a span that matches no rows still
    counts against the limit.
    """
    tuples: list[tuple[object, ...]] = []
    real = [
        (corpus.taxonomy.site_id, scope, facet)
        for scope in corpus.taxonomy.levels.values()
        for facet in POPULATED_FACETS
    ]
    tuples.extend(real[:spans])
    while len(tuples) < spans:
        tuples.append(
            (
                corpus.taxonomy.site_id,
                uuid.uuid5(uuid.NAMESPACE_URL, f"pad/{len(tuples)}"),
                POPULATED_FACETS[0],
            )
        )
    return TupleInProbe(
        table=CUE_SCOPED,
        tuples=tuple(tuples),
        query_vector=tuple(unit_vector(1024, f"query/{POPULATED_FACETS[0]}")),
        k=K,
    )


def _observe(conn: object, probe: TupleInProbe) -> dict:
    source = pgwire_explain_source(conn)
    plan = parse_explain(source("EXPLAIN " + tuple_in_sql(probe).text))
    approximate = [
        str(row[0]) for row in conn.execute(tuple_in_sql(probe).text).fetchall()  # type: ignore[attr-defined]
    ]
    exact = [
        str(row[0]) for row in conn.execute(brute_force_sql(probe).text).fetchall()  # type: ignore[attr-defined]
    ]
    overlap = len(set(approximate) & set(exact))
    return {
        "spans": probe.span_count,
        "vector_search_nodes": len(plan.vector_search_nodes),
        "index_refs": sorted({n.table_ref or "" for n in plan.vector_search_nodes}),
        "full_scan": plan.has_full_scan,
        "node_types": sorted({n.node_type for n in plan.nodes}),
        "returned": len(approximate),
        "oracle_returned": len(exact),
        "recall_at_k": round(overlap / len(exact), 4) if exact else None,
    }


def test_ix05_characterise_tuple_in_below_and_above_the_span_limit(
    session_conn: object, probe_context: dict
) -> None:
    span_limit = probe_context["span_limit"]
    corpus = probe_context["corpus"]
    below = max(2, min(span_limit - 1, 12))
    above = span_limit + 1
    observations = {
        "span_limit_read_at_runtime": span_limit,
        "fixture_rows": FIXTURE_ROWS,
        "k": K,
        "below": _observe(session_conn, _probe(corpus, spans=below)),
        "above": _observe(session_conn, _probe(corpus, spans=above)),
    }
    print("[ix05] " + json.dumps(observations, indent=2))

    # Invariants that are NOT version-dependent, and so are asserted rather than recorded.
    assert observations["below"]["spans"] == below
    assert observations["above"]["spans"] == above
    assert observations["above"]["spans"] > span_limit
    assert observations["below"]["oracle_returned"] > 0, (
        "the brute-force oracle returned nothing, so there is no ground truth to characterise "
        "against and the fixture is wrong, not the database"
    )

    # The documented behaviour below the limit. If THIS fails, the documentation and the
    # implementation disagree on this version, which is exactly the finding this lane exists
    # to produce.
    assert observations["below"]["vector_search_nodes"] >= 1, (
        f"below the runtime span limit ({below} spans < {span_limit}) tuple-IN did not plan a "
        "vector search at all. Documented behaviour and observed behaviour disagree on this "
        f"version.\n{json.dumps(observations['below'], indent=2)}"
    )

    ARTEFACTS.mkdir(parents=True, exist_ok=True)
    if BASELINE.is_file():
        previous = json.loads(BASELINE.read_text(encoding="utf-8"))
        drifted = {
            key
            for key in ("below", "above")
            if _shape(previous.get(key, {})) != _shape(observations[key])
        }
        assert not drifted, (
            f"tuple-IN behaviour changed at {sorted(drifted)}. THIS IS THE POINT OF THIS TEST "
            "— it is expected to change across versions. Read the diff, decide whether the "
            "decision not to ship tuple-IN still holds, and update the baseline deliberately:\n"
            f"  was: {json.dumps({k: previous.get(k) for k in drifted}, indent=2)}\n"
            f"  now: {json.dumps({k: observations[k] for k in drifted}, indent=2)}\n"
            f"  baseline: {BASELINE}"
        )
    else:
        BASELINE.write_text(
            json.dumps(observations, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(f"[ix05] wrote first baseline to {BASELINE}")


def _shape(observation: dict) -> dict:
    """The version-sensitive part of an observation: the plan shape, not the timings.

    ``recall_at_k`` is excluded because C-SPANN is approximate and its trees mutate on every
    insert, so a recall figure that moved by one candidate is not a platform change. What is
    compared is whether a vector search was planned at all, on which index, and whether the
    optimizer fell back to a scan.
    """
    return {
        "vector_search_nodes": observation.get("vector_search_nodes"),
        "index_refs": observation.get("index_refs"),
        "full_scan": observation.get("full_scan"),
        "returned": observation.get("returned"),
    }


def test_ix05_the_span_limit_is_read_not_assumed(session_conn: object) -> None:
    """Guards the one mistake that would void this whole lane."""
    value = read_setting(session_conn, SPAN_LIMIT_SETTING)
    if value is None:
        pytest.skip(f"`{SPAN_LIMIT_SETTING}` is not present on this cluster")
    source = Path(__file__).read_text(encoding="utf-8")
    for invented in ("span_limit = 10000", "span_limit = 1000", "SPAN_LIMIT = "):
        assert invented not in source, (
            f"a hard-coded span limit ({invented!r}) appears in this module. The setting must "
            "be read at runtime; a characterisation test with an assumed constant "
            "characterises the constant."
        )
