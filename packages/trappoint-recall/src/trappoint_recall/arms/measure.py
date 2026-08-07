# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Layer two: the behavioural proof, and the ingest curve that replaces a guessed threshold.

**Why plan text is not enough.** ``EXPLAIN`` says which plan the optimizer chose. It does not
say what the executor did, and it cannot be read by anyone who does not already trust the
parser that read it. A silently unused index scales **linearly** regardless of how the plan
text is formatted — so the second proof is a number: per-arm p50 latency across a corpus that
doubles, twice, with the ratio required to stay under a stated bound. A ratio is falsifiable.
"Looks fine" is not.

The bound shipped here is ``t(2n)/t(n) < 1.7`` at each doubling, measured as the median of
three runs. It is not derived from theory — an approximate-nearest-neighbour lookup over a
K-means tree should be far better than 1.7 — it is a **deliberately loose ceiling that a
linear scan cannot pass**: a linear scan doubles, giving 2.0. The test is therefore
insensitive to machine noise and sensitive to exactly the failure it exists to catch.

**The ingest curve.** The documented guidance is that *large batch inserts of ``VECTOR`` types
can cause performance degradation* and *batching should be avoided*, which is a direction, not
a number. A build that picks a batch size from that sentence has invented a threshold. This
module holds the arithmetic for measuring the real one — live row-at-a-time against the
indexed table versus stage-then-index through the index-free mirror — so the number that ends
up in the loader is one somebody measured on the target cluster.
"""

from __future__ import annotations

import itertools
import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final

from .binding import VectorTable

__all__ = [
    "DEFAULT_SUBLINEARITY_LIMIT",
    "DoublingRatio",
    "IngestCurve",
    "IngestSample",
    "KneeEstimate",
    "SublinearityVerdict",
    "create_vector_index_sql",
    "curve_artefact",
    "degradation_knee",
    "p50",
    "promote_sql",
    "run_median_p50",
    "sublinearity_verdict",
]

#: The ceiling on t(2n)/t(n). A linear scan gives 2.0; an ANN lookup should be near 1.0.
DEFAULT_SUBLINEARITY_LIMIT: Final = 1.7

#: How many independent runs are medianed before a doubling ratio is computed. Three, because
#: one run measures the machine's mood and two cannot break a tie.
DEFAULT_RUNS: Final = 3


def p50(samples: Sequence[float]) -> float:
    """The median of one run's per-query latencies."""
    if not samples:
        raise ValueError("no latency samples: an empty measurement is not a fast one")
    return float(statistics.median(samples))


def run_median_p50(runs: Sequence[Sequence[float]]) -> float:
    """The median of the per-run p50s — the statistic the doubling ratio is computed from.

    Median of medians, not mean of medians: one cold cache or one range split during a run
    would drag a mean, and the point of the measurement is the shape of the curve, not the
    absolute latency of any single execution.
    """
    if not runs:
        raise ValueError("no runs to median")
    return float(statistics.median([p50(run) for run in runs]))


@dataclass(frozen=True, slots=True)
class DoublingRatio:
    """One doubling: corpus sizes, the two p50s, the ratio, and the verdict."""

    n_from: int
    n_to: int
    p50_from_ms: float
    p50_to_ms: float
    ratio: float
    limit: float

    @property
    def ok(self) -> bool:
        return self.ratio < self.limit

    def describe(self) -> str:
        verdict = "sublinear" if self.ok else "LINEAR OR WORSE"
        return (
            f"{self.n_from}→{self.n_to}: {self.p50_from_ms:.3f}ms → {self.p50_to_ms:.3f}ms, "
            f"ratio {self.ratio:.3f} (limit {self.limit}) — {verdict}"
        )


@dataclass(frozen=True, slots=True)
class SublinearityVerdict:
    """The behavioural proof for one arm across the whole doubling sequence."""

    arm_id: str
    points: tuple[tuple[int, float], ...]
    ratios: tuple[DoublingRatio, ...]
    limit: float

    @property
    def ok(self) -> bool:
        return bool(self.ratios) and all(r.ok for r in self.ratios)

    def describe(self) -> str:
        return f"arm {self.arm_id}\n  " + "\n  ".join(r.describe() for r in self.ratios)

    def as_dict(self) -> dict[str, Any]:
        return {
            "arm_id": self.arm_id,
            "limit": self.limit,
            "points": [{"n": n, "p50_ms": ms} for n, ms in self.points],
            "ratios": [
                {
                    "n_from": r.n_from,
                    "n_to": r.n_to,
                    "p50_from_ms": r.p50_from_ms,
                    "p50_to_ms": r.p50_to_ms,
                    "ratio": r.ratio,
                    "ok": r.ok,
                }
                for r in self.ratios
            ],
            "ok": self.ok,
        }


def sublinearity_verdict(
    *,
    arm_id: str,
    p50_by_size: Mapping[int, float],
    limit: float = DEFAULT_SUBLINEARITY_LIMIT,
) -> SublinearityVerdict:
    """Compute the ratio at every consecutive pair of corpus sizes, in ascending order.

    Consecutive pairs, not first-to-last: a curve that is flat then explodes must fail at the
    doubling where it exploded, and an endpoint-only ratio would average that away.
    """
    if len(p50_by_size) < 2:
        raise ValueError(
            "sublinearity needs at least two corpus sizes; one point is a measurement, not a "
            "curve"
        )
    ordered = sorted(p50_by_size.items())
    ratios: list[DoublingRatio] = []
    for (n_from, t_from), (n_to, t_to) in itertools.pairwise(ordered):
        if t_from <= 0:
            raise ValueError(
                f"p50 at n={n_from} is {t_from}; a non-positive latency means the timer, not "
                "the index, is what was measured"
            )
        ratios.append(
            DoublingRatio(
                n_from=n_from,
                n_to=n_to,
                p50_from_ms=t_from,
                p50_to_ms=t_to,
                ratio=t_to / t_from,
                limit=limit,
            )
        )
    return SublinearityVerdict(
        arm_id=arm_id,
        points=tuple(ordered),
        ratios=tuple(ratios),
        limit=limit,
    )


# ── the ingest curve ─────────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class IngestSample:
    """One measured insert: how many rows, at what batch size, in how long."""

    rows: int
    batch_size: int
    elapsed_s: float

    def __post_init__(self) -> None:
        if self.rows < 1:
            raise ValueError("an ingest sample with no rows measures nothing")
        if self.batch_size < 1:
            raise ValueError("batch size must be >= 1")
        if self.elapsed_s <= 0:
            raise ValueError(
                f"elapsed {self.elapsed_s}s is not positive; a zero-duration insert means the "
                "clock resolution beat the measurement, not that the insert was free"
            )

    @property
    def rows_per_s(self) -> float:
        return self.rows / self.elapsed_s


@dataclass(frozen=True, slots=True)
class IngestCurve:
    """Throughput against batch size for one ingest path."""

    mode: str
    samples: tuple[IngestSample, ...]

    @property
    def best(self) -> IngestSample:
        return max(self.samples, key=lambda s: s.rows_per_s)

    def as_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "samples": [
                {
                    "rows": s.rows,
                    "batch_size": s.batch_size,
                    "elapsed_s": round(s.elapsed_s, 6),
                    "rows_per_s": round(s.rows_per_s, 3),
                }
                for s in sorted(self.samples, key=lambda s: s.batch_size)
            ],
        }


@dataclass(frozen=True, slots=True)
class KneeEstimate:
    """The largest batch size still delivering a stated fraction of peak throughput."""

    batch_size: int
    rows_per_s: float
    peak_rows_per_s: float
    retained_fraction: float
    basis: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "batch_size": self.batch_size,
            "rows_per_s": round(self.rows_per_s, 3),
            "peak_rows_per_s": round(self.peak_rows_per_s, 3),
            "retained_fraction": round(self.retained_fraction, 4),
            "basis": self.basis,
        }


def degradation_knee(curve: IngestCurve, *, retain: float = 0.8) -> KneeEstimate:
    """The measured batch threshold: the largest batch still at ``retain`` × peak throughput.

    This is the number that belongs in a loader. It replaces "batching should be avoided"
    — a direction — with a size somebody measured on the cluster the corpus is going into.
    """
    if not 0 < retain <= 1:
        raise ValueError(f"retain must be in (0, 1], got {retain}")
    if not curve.samples:
        raise ValueError("an empty curve has no knee")
    peak = curve.best.rows_per_s
    eligible = [s for s in curve.samples if s.rows_per_s >= peak * retain]
    chosen = max(eligible, key=lambda s: s.batch_size)
    return KneeEstimate(
        batch_size=chosen.batch_size,
        rows_per_s=chosen.rows_per_s,
        peak_rows_per_s=peak,
        retained_fraction=chosen.rows_per_s / peak,
        basis=f"largest batch retaining >= {retain:.0%} of peak throughput ({curve.mode})",
    )


def curve_artefact(
    *,
    status: str,
    curves: Sequence[IngestCurve],
    knees: Mapping[str, KneeEstimate],
    provenance: Mapping[str, Any],
) -> dict[str, Any]:
    """The committed JSON artefact.

    ``status`` is mandatory and is checked by the reader: an artefact that does not say
    whether its numbers were measured is worse than no artefact, because it looks like
    evidence. The two legal values are ``measured`` and ``unmeasured``; the second carries no
    curves and exists so that the file's *shape* and the command that fills it are in the
    repository before any cluster is available.
    """
    if status not in {"measured", "unmeasured"}:
        raise ValueError(f"status must be 'measured' or 'unmeasured', got {status!r}")
    if status == "measured" and not curves:
        raise ValueError("status is 'measured' but no curves were supplied")
    if status == "unmeasured" and curves:
        raise ValueError(
            "status is 'unmeasured' but curves were supplied; a file that carries numbers "
            "must say they were measured"
        )
    return {
        "artefact": "vector-insert-degradation-curve",
        "schema_version": 1,
        "status": status,
        "provenance": dict(provenance),
        "curves": [c.as_dict() for c in curves],
        "knees": {mode: knee.as_dict() for mode, knee in knees.items()},
    }


# ── the two ingest paths, as SQL text ────────────────────────────────────────────────────


def promote_sql(
    stage: VectorTable, live: VectorTable, *, columns: Sequence[str], batch: int
) -> str:
    """Stage → live promotion, one keyset-paginated batch at a time.

    An ``INSERT``, deliberately: the live table's projection trigger fires on every promoted
    row and rewrites the prefix columns from the authoritative parent, exactly as it does on
    the row-at-a-time path. There is no bulk path into the prefixed table that skips the weld,
    which is why staging does not open a hole in it.
    """
    if not columns:
        raise ValueError("no columns to promote")
    projection = ", ".join(f"s.{c}" for c in columns)
    return (
        f"INSERT INTO {live.qualified_name} ({', '.join(columns)})\n"
        f"SELECT {projection}\n"
        f"  FROM {stage.qualified_name} s\n"
        f" WHERE s.{stage.id_column} > $1\n"
        f" ORDER BY s.{stage.id_column}\n"
        f" LIMIT {batch}\n"
        f"RETURNING {live.id_column}"
    )


def create_vector_index_sql(table: VectorTable) -> str:
    """``CREATE VECTOR INDEX`` for the import-then-index fallback.

    Kept in one place because this statement is the *rejected* production path: it is the one
    that bypasses the projection trigger, so if it is ever run the load is a privileged,
    attested operation rather than a routine one. It exists here to be **measured against**,
    not to be scheduled.
    """
    ops = "vector_cosine_ops" if table.distance_operator == "<=>" else "vector_l2_ops"
    prefix = "".join(f"{column}, " for column in table.prefix_columns)
    return (
        f"CREATE VECTOR INDEX {table.index} ON {table.qualified_name} "
        f"({prefix}{table.vector_column} {ops})"
    )
