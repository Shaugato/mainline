# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""Human confirmation on a held-out sample, reported with Wilson bounds.

``diachronic-recall.md`` §3 sets the acceptance test: hold out 300 documents for human
confirmation, and require **>= 0.85 top-1 at file level and >= 0.95 at fonds level**.  This
module computes it, and it makes three choices that change what the numbers mean.

**Every number comes back as a** :class:`~trappoint_recall.eval.measurement.Measurement`.
Not a float.  The eval package's type carries the point estimate, the Wilson interval, the
denominator and the split policy together so the interval cannot be dropped on the way to a
slide, and ``scripts/recall/no_bare_point_estimates.py`` greps prose for the same rule.  The
package is imported here rather than re-derived: a locally reimplemented Wilson bound would
be a second definition of the confidence the release gates use, and the two would drift.

**Acceptance gates on the Wilson lower bound, not the point estimate.**  At n = 300 a
point estimate of 0.85 has a lower bound near 0.81, so this is a strictly harder test than
reading the accuracy off the top of the report — which is the correct direction for a
threshold that decides whether a classification scheme is frozen into a physical index.
``gate_on="value"`` is available and is recorded in the report, so a run that used the
looser reading says so in its own artefact.

**A truth label with no node in the taxonomy counts as a miss.**  When the human's
confirmation label was merged away or dropped below the support floor, the taxonomy failed
to cover a real activity.  Scoring it as "unresolvable, excluded" would move the failure
into a footnote and raise the accuracy by exactly the amount the taxonomy is missing.

The holdout split is a hash of the document id, not a shuffle: reproducible on every
machine, stable as the corpus grows, and impossible to re-draw until it flatters a result.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final

from .errors import EvalPackageUnavailable, HoldoutTooSmall
from .induction import InductionDocument, SnapshotBuild
from .models import LEVEL_FILE, LEVEL_FONDS, LEVEL_SERIES, TaxonomySnapshot

if TYPE_CHECKING:  # pragma: no cover - typing only
    # `trappoint-recall` is the Apache-2.0 substrate package that owns Measurement and the
    # Wilson interval.
    #
    # There is NO `type: ignore` here any more, and its absence is the measurement. The
    # ignore that used to sit on this line said "mypy cannot see this package"; on
    # 2026-08-10 `mypy --config-file mypy.ini` over the derived target list reported it as
    # an UNUSED ignore, because `packages/trappoint-recall/src` is on `mypy_path` and
    # `trappoint_recall/eval/measurement.py` ships beside a `py.typed`. The import
    # resolves, `Measurement` is a real type here, and re-adding the ignore would put back
    # the claim that it is not.
    #
    # STILL TRUE, and raised as a cross-domain note rather than fixed here:
    # `trappoint-recall` is absent from this distribution's runtime `dependencies`
    # (`mainline-recall-agent/pyproject.toml` declares anthropic, boto3, numpy, pydantic).
    # The workspace sync is what makes the import resolve today. Because the import is
    # under `TYPE_CHECKING` it can never fail at runtime, so this is a declaration defect,
    # not a breakage — but a stranger installing the wheel alone would type-check it
    # differently than CI does, and that is exactly the property PL-1 asks for.
    from trappoint_recall.eval.measurement import Measurement

    from .classifier import TaxonomyClassifier

__all__ = [
    "DEFAULT_HOLDOUT_SIZE",
    "FILE_LEVEL_FLOOR",
    "FONDS_LEVEL_FLOOR",
    "HoldoutReport",
    "holdout_split",
    "score_holdout",
]

#: diachronic-recall.md §3.
DEFAULT_HOLDOUT_SIZE: Final[int] = 300
FILE_LEVEL_FLOOR: Final[float] = 0.85
FONDS_LEVEL_FLOOR: Final[float] = 0.95

#: The minimum sample this module will report an acceptance decision from.  Below it the
#: Wilson interval is wider than the gap between the two floors and the decision is noise.
MIN_HOLDOUT: Final[int] = 30


def _measurement_type() -> Any:
    try:
        from trappoint_recall.eval.measurement import Measurement as _Measurement
    except ImportError as exc:
        raise EvalPackageUnavailable(
            "trappoint_recall.eval is not importable, so no Wilson bound can be computed. "
            "Install the workspace (`uv sync`) or put packages/trappoint-recall/src on "
            "sys.path. A holdout accuracy without an interval is exactly the bare point "
            "estimate the repository refuses to publish.",
            error=str(exc),
        ) from exc
    return _Measurement


def holdout_split(
    doc_ids: Sequence[str], size: int = DEFAULT_HOLDOUT_SIZE
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Split ``doc_ids`` into ``(train, holdout)`` by a digest of the id.

    Returns the *train* ids first.  Deterministic, order-independent, and stable under
    corpus growth: a document's side of the split is a property of its own id, so adding
    documents never moves an existing one from holdout into training.
    """
    ranked = sorted(doc_ids, key=lambda doc_id: hashlib.sha256(doc_id.encode("utf-8")).hexdigest())
    take = max(min(size, len(ranked)), 0)
    holdout = set(ranked[:take])
    train = tuple(doc_id for doc_id in doc_ids if doc_id not in holdout)
    held = tuple(doc_id for doc_id in doc_ids if doc_id in holdout)
    return train, held


@dataclass(frozen=True, slots=True)
class HoldoutReport:
    """Accuracy at each archival level, with the arithmetic that decided acceptance."""

    n: int
    fonds_level: Measurement
    series_level: Measurement
    file_level: Measurement
    file_floor: float
    fonds_floor: float
    gate_on: str
    accepted: bool
    corpus_provenance: str
    split_policy_id: str
    unresolvable_truth: int = 0
    taxonomy_ver: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "n": self.n,
            "taxonomy_ver": self.taxonomy_ver,
            "corpus_provenance": self.corpus_provenance,
            "split_policy_id": self.split_policy_id,
            "gate_on": self.gate_on,
            "accepted": self.accepted,
            "floors": {"file": self.file_floor, "fonds": self.fonds_floor},
            "unresolvable_truth": self.unresolvable_truth,
            "fonds_level": self.fonds_level.to_dict(),
            "series_level": self.series_level.to_dict(),
            "file_level": self.file_level.to_dict(),
        }

    def render(self) -> str:
        """One block, every interval attached.  The only sanctioned rendering."""
        verdict = "ACCEPTED" if self.accepted else "NOT ACCEPTED"
        return "\n".join(
            [
                f"holdout confirmation ({self.n} documents, gate on {self.gate_on}) -> {verdict}",
                f"  corpus: {self.corpus_provenance}",
                f"  {self.fonds_level.render()}   floor {self.fonds_floor}",
                f"  {self.series_level.render()}",
                f"  {self.file_level.render()}   floor {self.file_floor}",
                f"  truth labels with no node in this taxonomy: {self.unresolvable_truth} "
                "(counted as misses)",
            ]
        )


def _ancestor_at(snapshot: TaxonomySnapshot, scope_id: str, level: int) -> str | None:
    node = snapshot.by_scope(scope_id)
    while node is not None:
        if node.level == level:
            return node.scope_id
        if node.parent_scope is None:
            return None
        node = snapshot.by_scope(node.parent_scope)
    return None


def _truth_scope(build: SnapshotBuild, document: InductionDocument) -> str | None:
    """Resolve a human confirmation label to a scope, through the merge alias map."""
    root = document.truth_activity_root
    if document.truth_file:
        scope = build.leaf_index.get((root, document.truth_file))
        if scope is not None:
            return scope
    if document.truth_series:
        scope = build.series_index.get((root, document.truth_series))
        if scope is not None:
            return scope
    return None


def score_holdout(
    *,
    build: SnapshotBuild,
    classifier: TaxonomyClassifier,
    documents: Sequence[InductionDocument],
    split_policy_id: str,
    corpus_provenance: str,
    file_floor: float = FILE_LEVEL_FLOOR,
    fonds_floor: float = FONDS_LEVEL_FLOOR,
    gate_on: str = "lower",
    minimum: int = MIN_HOLDOUT,
) -> HoldoutReport:
    """Score the held-out documents at fonds, series and file level.

    ``documents`` are the holdout documents themselves — this function does not split.
    Splitting is :func:`holdout_split`'s job and it happens before induction, because a
    holdout the taxonomy was induced from confirms nothing.
    """
    if gate_on not in ("lower", "value"):
        raise HoldoutTooSmall(
            "gate_on is 'lower' (the Wilson lower bound, the release-gate default) or "
            "'value' (the point estimate)",
            gate_on=gate_on,
        )
    if len(documents) < minimum:
        raise HoldoutTooSmall(
            "too few holdout documents to report an acceptance decision; below this the "
            "Wilson interval is wider than the gap between the two acceptance floors",
            n=len(documents),
            minimum=minimum,
        )
    measurement = _measurement_type()
    snapshot = build.snapshot

    predictions = classifier.predict([document.text for document in documents])
    levels = {LEVEL_FONDS: 0, LEVEL_SERIES: 0, LEVEL_FILE: 0}
    denominators = {LEVEL_FONDS: 0, LEVEL_SERIES: 0, LEVEL_FILE: 0}
    unresolvable = 0

    for document, predicted in zip(documents, predictions, strict=True):
        truth = _truth_scope(build, document)
        if truth is None:
            unresolvable += 1
            for level in denominators:
                denominators[level] += 1
            continue
        for level in denominators:
            truth_ancestor = _ancestor_at(snapshot, truth, level)
            if truth_ancestor is None:
                # The truth label does not reach this level (a series-only confirmation
                # scored at file level). Not a hit, and still in the denominator.
                denominators[level] += 1
                continue
            denominators[level] += 1
            if _ancestor_at(snapshot, predicted, level) == truth_ancestor:
                levels[level] += 1

    detail_common: Mapping[str, Any] = {
        "criterion": "top-1 assignment agrees with the human confirmation label",
        "taxonomy_ver": snapshot.taxonomy_ver,
        "corpus_provenance": corpus_provenance,
        "unresolvable_truth_counted_as_miss": unresolvable,
    }
    fonds = measurement.proportion(
        "taxonomy_holdout_top1_fonds",
        levels[LEVEL_FONDS],
        denominators[LEVEL_FONDS],
        split_policy_id=split_policy_id,
        detail=dict(detail_common, level="fonds"),
    )
    series = measurement.proportion(
        "taxonomy_holdout_top1_series",
        levels[LEVEL_SERIES],
        denominators[LEVEL_SERIES],
        split_policy_id=split_policy_id,
        detail=dict(detail_common, level="series"),
    )
    leaf = measurement.proportion(
        "taxonomy_holdout_top1_file",
        levels[LEVEL_FILE],
        denominators[LEVEL_FILE],
        split_policy_id=split_policy_id,
        detail=dict(detail_common, level="file"),
    )
    if gate_on == "lower":
        accepted = bool(
            leaf.meets_floor(file_floor, on="lower") and fonds.meets_floor(fonds_floor, on="lower")
        )
    else:
        accepted = bool(
            leaf.meets_floor(file_floor, on="value") and fonds.meets_floor(fonds_floor, on="value")
        )
    return HoldoutReport(
        n=len(documents),
        fonds_level=fonds,
        series_level=series,
        file_level=leaf,
        file_floor=file_floor,
        fonds_floor=fonds_floor,
        gate_on=gate_on,
        accepted=accepted,
        corpus_provenance=corpus_provenance,
        split_policy_id=split_policy_id,
        unresolvable_truth=unresolvable,
        taxonomy_ver=snapshot.taxonomy_ver,
    )
