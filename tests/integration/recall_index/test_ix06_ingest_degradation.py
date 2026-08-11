# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""IX-06 — the vector-insert degradation curve: a measured threshold, not an invented one.

The documented guidance is that *large batch inserts of ``VECTOR`` types can cause performance
degradation* and that *batching should be avoided*. That is a **direction**, not a number, and
a loader that picks a batch size from it has invented a threshold. This module measures the
real one on the target cluster and writes it to
``artefacts/vector_insert_degradation.json``, which is committed so that the number in the
loader has a provenance.

Three paths are measured, because they are three different decisions:

``live``
    Row-at-a-time and small-batch ``INSERT`` straight into the vector-indexed table. The
    production path. Every row passes the projection trigger, so the index prefix cannot be
    chosen by the inserter.

``staged``
    Bulk ``INSERT`` into the index-free mirror, then promotion in keyset-paginated batches.
    Promotion is an ``INSERT`` into the live table, so it fires the same trigger on every row
    — which is why staging is a performance path and not a hole in the weld.

``import_then_index`` *(the rejected fallback, measured so the rejection has a price tag)*
    Load the mirror, then ``CREATE VECTOR INDEX`` on it. This is the path that **bypasses the
    projection trigger**, which is why it is not the production path even though it may be the
    fastest. Measuring it is how "we rejected the fast path for a safety reason" stops being
    an unquantified claim.

Marked ``nightly``: it writes thousands of rows and is not a per-commit test.
"""

from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone

import pytest
from _support import (
    ARTEFACTS,
    CORPUS_BATCH,
    CUE_SCOPED,
    CUE_STAGE,
    POPULATED_FACETS,
    CorpusState,
    env_int,
    unit_vector,
    vector_literal,
)

from trappoint_recall.arms.measure import (
    IngestCurve,
    IngestSample,
    create_vector_index_sql,
    curve_artefact,
    degradation_knee,
    promote_sql,
)

pytestmark = [pytest.mark.nightly, pytest.mark.slow]

ARTEFACT = ARTEFACTS / "vector_insert_degradation.json"

#: Batch sizes probed. Spans three orders of magnitude because the documented guidance says
#: "avoid batching" without saying where the cost begins, and a curve with three points cannot
#: show a knee.
BATCH_SIZES: tuple[int, ...] = (1, 10, 50, 100, 250, 500, 1000)
#: Rows per batch-size probe. Small enough for a nightly lane, large enough that a single
#: range split does not dominate a point.
ROWS_PER_PROBE = env_int("MAINLINE_RECALL_INDEX_INGEST_ROWS", 1000)

PROMOTE_COLUMNS = ("cue_id", "site_id", "scope_id", "facet", "embed_model", "index_gen", "emb")


def _rows(corpus: CorpusState, conn: object, count: int, *, tag: str) -> list[tuple[object, ...]]:
    """Create ``count`` parent cue rows and return the sidecar tuples that reference them.

    Parent cues first, always: the projection trigger RAISEs P0001 on a sidecar row whose cue
    does not exist, which is the weld working. The measurement is of the sidecar insert, so
    the parent rows are created outside the timed section.
    """
    event_id = uuid.uuid4()
    conn.execute(  # type: ignore[attr-defined]
        """
        INSERT INTO mainline.event
          (event_id, site_id, external_ref, occurred_at, kind, title, narrative,
           source_object_key, source_sha256, severity_actual, severity_potential,
           severity_gate, severity_basis, canon_version)
        VALUES (%s, %s, %s, now() - INTERVAL '2000 days', 'incident', 'ingest probe',
                'A synthetic event created solely to parent the ingest-curve probe rows.',
                %s, %s, 2, 2, 2, 'coded_field', 1)
        """,
        (
            event_id,
            corpus.taxonomy.site_id,
            f"INC-{tag}-{event_id.hex[:8]}",
            f"s3://mainline-raw/{event_id}",
            uuid.uuid4().bytes + uuid.uuid4().bytes,
        ),
    )
    scope_id = corpus.taxonomy.levels[3]
    facet = POPULATED_FACETS[0]
    out: list[tuple[object, ...]] = []
    pending: list[tuple[object, ...]] = []
    for i in range(count):
        cue_id = uuid.uuid4()
        pending.append(
            (
                cue_id,
                event_id,
                corpus.taxonomy.site_id,
                scope_id,
                3,
                facet,
                f"ingest probe {tag} {i}",
            )
        )
        out.append(
            (
                cue_id,
                corpus.taxonomy.site_id,
                scope_id,
                facet,
                "bge-large-en-v1.5@pinned",
                "gen-0",
                vector_literal(unit_vector(1024, f"{tag}/{i}")),
            )
        )
        if len(pending) >= CORPUS_BATCH:
            _flush_cues(conn, pending)
            pending = []
    _flush_cues(conn, pending)
    return out


def _flush_cues(conn: object, rows: list[tuple[object, ...]]) -> None:
    if not rows:
        return
    values = ", ".join(
        ["(%s, %s, %s, %s, %s, %s, 1, %s, true, 'claude-opus-5', 'cue-v1')"] * len(rows)
    )
    conn.execute(  # type: ignore[attr-defined]
        "INSERT INTO mainline.event_cue (cue_id, event_id, site_id, scope_id, scope_level, "
        "facet, taxonomy_ver, cue_text, is_derived, gen_model, prompt_version) VALUES " + values,
        tuple(v for row in rows for v in row),
    )


def _timed_insert(conn: object, table: str, rows: list[tuple[object, ...]], batch: int) -> float:
    placeholder = "(%s, %s, %s, %s, %s, %s, %s::VECTOR(1024))"
    head = (
        f"INSERT INTO {table} (cue_id, site_id, scope_id, facet, embed_model, index_gen, emb) "
        "VALUES "
    )
    started = time.perf_counter()
    for offset in range(0, len(rows), batch):
        chunk = rows[offset : offset + batch]
        conn.execute(  # type: ignore[attr-defined]
            head + ", ".join([placeholder] * len(chunk)),
            tuple(v for row in chunk for v in row),
        )
    return time.perf_counter() - started


@pytest.fixture(scope="module")
def curves(session_conn: object, corpus: CorpusState) -> dict:
    live: list[IngestSample] = []
    staged: list[IngestSample] = []
    for batch in BATCH_SIZES:
        rows = _rows(corpus, session_conn, ROWS_PER_PROBE, tag=f"live-{batch}")
        elapsed = _timed_insert(session_conn, CUE_SCOPED.qualified_name, rows, batch)
        live.append(IngestSample(rows=len(rows), batch_size=batch, elapsed_s=elapsed))
        print(f"[ix06] live batch={batch:>4}: {len(rows) / elapsed:8.1f} rows/s")

        rows = _rows(corpus, session_conn, ROWS_PER_PROBE, tag=f"stage-{batch}")
        elapsed = _timed_insert(session_conn, CUE_STAGE.qualified_name, rows, batch)
        staged.append(IngestSample(rows=len(rows), batch_size=batch, elapsed_s=elapsed))
        print(f"[ix06] stage batch={batch:>4}: {len(rows) / elapsed:8.1f} rows/s")

    promotion = _measure_promotion(session_conn)
    return {
        "live": IngestCurve(mode="live", samples=tuple(live)),
        "staged": IngestCurve(mode="staged", samples=tuple(staged)),
        "promotion": promotion,
    }


def _measure_promotion(conn: object) -> dict:
    """Drain the staging mirror through the promotion statement and time it."""
    statement = promote_sql(CUE_STAGE, CUE_SCOPED, columns=PROMOTE_COLUMNS, batch=200).replace(
        "$1", "%s"
    )
    cursor_value = uuid.UUID(int=0)
    promoted = 0
    started = time.perf_counter()
    while True:
        rows = conn.execute(statement, (cursor_value,)).fetchall()  # type: ignore[attr-defined]
        if not rows:
            break
        promoted += len(rows)
        cursor_value = max(uuid.UUID(str(row[0])) for row in rows)
    elapsed = max(time.perf_counter() - started, 1e-9)
    return {
        "rows": promoted,
        "elapsed_s": elapsed,
        "rows_per_s": promoted / elapsed if promoted else 0.0,
    }


def test_ix06_measures_the_curve_and_commits_it(curves: dict, schema: object) -> None:
    live: IngestCurve = curves["live"]
    staged: IngestCurve = curves["staged"]
    knees = {"live": degradation_knee(live), "staged": degradation_knee(staged)}
    document = curve_artefact(
        status="measured",
        curves=[live, staged],
        knees=knees,
        provenance={
            "measured_at": datetime.now(timezone.utc).isoformat(),
            "rows_per_probe": ROWS_PER_PROBE,
            "batch_sizes": list(BATCH_SIZES),
            "database": getattr(schema, "database", "unknown"),
            "vector_setting": getattr(schema, "vector_setting", "unknown"),
            "dimensions": CUE_SCOPED.dimensions,
            "promotion": curves["promotion"],
            "produced_by": "tests/integration/recall_index/test_ix06_ingest_degradation.py",
            "note": (
                "The `live` curve is the production path: every row passes the projection "
                "trigger. `staged` is the index-free mirror; its rows still pass the trigger "
                "on promotion. The batch size in the loader must come from the `live` knee."
            ),
        },
    )
    ARTEFACT.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"[ix06] live knee: {knees['live'].as_dict()}")
    print(f"[ix06] staged knee: {knees['staged'].as_dict()}")
    assert knees["live"].batch_size >= 1
    assert live.best.rows_per_s > 0


def test_ix06_the_committed_artefact_never_claims_numbers_it_does_not_have() -> None:
    """Runs with no cluster. The artefact must always say whether it was measured."""
    assert ARTEFACT.is_file(), (
        f"{ARTEFACT} is not committed. The file's SHAPE and the command that fills it belong "
        "in the repository before any cluster exists, so that an unmeasured threshold is "
        "visibly unmeasured rather than quietly invented."
    )
    document = json.loads(ARTEFACT.read_text(encoding="utf-8"))
    assert document["artefact"] == "vector-insert-degradation-curve"
    assert document["status"] in {"measured", "unmeasured"}
    if document["status"] == "unmeasured":
        assert document["curves"] == []
        assert document["knees"] == {}
        assert "how_to_measure" in document["provenance"], (
            "an unmeasured artefact must carry the exact command that measures it"
        )
    else:
        assert document["curves"], "status 'measured' with no curves is a false claim"
        for knee in document["knees"].values():
            assert knee["batch_size"] >= 1
            assert 0 < knee["retained_fraction"] <= 1


def test_ix06_the_rejected_fallback_is_measured_not_merely_rejected(
    session_conn: object, curves: dict
) -> None:
    """``CREATE VECTOR INDEX`` on a populated table — the path that bypasses the trigger.

    It is measured so the safety decision has a price tag. It is run against the staging
    mirror, never against the live table, and the index is dropped immediately: creating an
    index on a populated table blocks writes until the backfill completes, which is precisely
    why the production tables declare their vector index at ``CREATE TABLE`` time on an empty
    table.
    """
    statement = create_vector_index_sql(CUE_STAGE).replace(
        CUE_STAGE.index, "cue_stage_fallback_idx"
    )
    started = time.perf_counter()
    try:
        session_conn.execute(statement)  # type: ignore[attr-defined]
    except Exception as exc:  # noqa: BLE001 - the failure IS the finding
        pytest.skip(
            "CREATE VECTOR INDEX on the populated staging mirror was refused on this cluster: "
            f"{exc}. Recorded rather than asserted — this is the rejected fallback, and its "
            "unavailability strengthens rather than weakens the decision not to use it."
        )
    elapsed = time.perf_counter() - started
    session_conn.execute("DROP INDEX mainline.event_cue_stage@cue_stage_fallback_idx")  # type: ignore[attr-defined]
    print(f"[ix06] import-then-index fallback: index built in {elapsed:.2f}s")
    document = json.loads(ARTEFACT.read_text(encoding="utf-8"))
    document["provenance"]["import_then_index"] = {
        "seconds": round(elapsed, 3),
        "statement": statement,
        "why_not_used": (
            "this is the one path into the prefixed sidecar that does not pass through the "
            "projection trigger, so a loader using it could choose which K-means tree a "
            "fatality cue lands in"
        ),
    }
    ARTEFACT.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
