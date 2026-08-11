# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""The evaluation corpus: queries, judgements, and the split policy that binds them.

A recall evaluation set is not a list of search strings. Each query is a *permit* —
either a retro permit synthesised from a real severity-5 investigation's own
description of the work (gold set G4, the money metric) or a routine permit from the
24-month uneventful replay that measures nuisance. The two are scored by different
metrics and must never be pooled, so ``kind`` is part of the query, not a filter
applied later by whoever is writing the report.

Ids are opaque strings rather than UUIDs. This package is Apache-2.0 substrate and
must stay usable against a corpus that has never seen a MAINLINE schema.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, Literal

from trappoint_recall.eval.qrels import QrelSet, load_qrels_jsonl
from trappoint_recall.eval.splits import SplitPolicy

__all__ = [
    "CorpusError",
    "EvalCorpus",
    "EvalQuery",
    "PermitKind",
    "load_corpus",
]

PermitKind = Literal["retro", "routine"]
"""``retro``: synthesised from a real incident, has a truth precursor.
``routine``: uneventful permit replay, the negative control for nuisance rate."""

CUE_FACETS: Final = ("mechanism", "precondition", "control_failure", "recurrence_test", "narrative")
"""The four Recurrence-Condition Cue facets plus the narrative safety net (ARCHITECTURE 6.2)."""


class CorpusError(ValueError):
    """Raised when a corpus directory is missing, malformed or internally inconsistent."""


@dataclass(frozen=True, slots=True)
class EvalQuery:
    """One permit presented to a retrieval backend.

    Attributes:
        query_id: Stable identifier.
        kind: ``retro`` or ``routine``.
        text: The permit's work description, as the backend would receive it.
        site_id: Tenant/site scope. Part of every ANN arm's prefix.
        activity_path: Position in the functional taxonomy, e.g.
            ``/underground/ground-support/rehabilitation``.
        asset_class: Equipment class, used by the embedding template (D3).
        severity: Severity of the true precursor for a retro permit; ``None`` for routine.
        wall: Time wall *t* for this retro permit. ``None`` for routine permits, which
            are replayed at corpus head.
        truth_doc_id: The precursor that actually preceded the incident. ``None`` for
            routine permits.
        bonded_sev5: Severity-5 events bonded to this permit's activity node or an
            ancestor. Channel B truth: **every one of these must come back blocking**
            (MI16). This is corpus ground truth, never the backend's self-report.
        facets: The exposure cue facets, if the corpus ships them.
    """

    query_id: str
    kind: PermitKind
    text: str
    site_id: str
    activity_path: str
    asset_class: str
    severity: int | None = None
    wall: datetime | None = None
    truth_doc_id: str | None = None
    bonded_sev5: tuple[str, ...] = ()
    facets: Mapping[str, str] = field(default_factory=dict)
    blinded: bool = False

    def __post_init__(self) -> None:
        if not self.query_id:
            raise CorpusError("query_id is mandatory")
        if self.kind == "retro":
            if self.truth_doc_id is None:
                raise CorpusError(
                    f"{self.query_id}: a retro permit without truth_doc_id measures nothing"
                )
            if self.wall is None:
                raise CorpusError(
                    f"{self.query_id}: a retro permit without a time wall cannot be "
                    "temporally blocked; Retro-Recall would silently score on the future"
                )
            if self.severity is None:
                raise CorpusError(
                    f"{self.query_id}: a retro permit must carry the precursor severity"
                )
        else:
            if self.truth_doc_id is not None:
                raise CorpusError(
                    f"{self.query_id}: a routine permit must not carry a truth precursor; "
                    "it is the negative control"
                )
        if self.severity is not None and not (1 <= self.severity <= 5):
            raise CorpusError(f"{self.query_id}: severity must be 1..5, got {self.severity}")
        if self.wall is not None and self.wall.tzinfo is None:
            raise CorpusError(f"{self.query_id}: wall must be timezone-aware")
        unknown = set(self.facets) - set(CUE_FACETS)
        if unknown:
            raise CorpusError(f"{self.query_id}: unknown cue facets {sorted(unknown)}")

    @property
    def is_severity_5(self) -> bool:
        return self.severity == 5

    def to_dict(self) -> dict[str, object]:
        return {
            "query_id": self.query_id,
            "kind": self.kind,
            "text": self.text,
            "site_id": self.site_id,
            "activity_path": self.activity_path,
            "asset_class": self.asset_class,
            "severity": self.severity,
            "wall": self.wall.astimezone(UTC).isoformat() if self.wall else None,
            "truth_doc_id": self.truth_doc_id,
            "bonded_sev5": list(self.bonded_sev5),
            "facets": dict(self.facets),
            "blinded": self.blinded,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> EvalQuery:
        def _str(key: str, *, required: bool = True, default: str = "") -> str:
            value = payload.get(key)
            if value is None:
                if required:
                    raise CorpusError(f"query is missing required field {key!r}")
                return default
            if not isinstance(value, str):
                raise CorpusError(f"field {key!r} must be a string, got {type(value).__name__}")
            return value

        raw_kind = _str("kind")
        if raw_kind not in ("retro", "routine"):
            raise CorpusError(f"kind must be 'retro' or 'routine', got {raw_kind!r}")
        kind: PermitKind = "retro" if raw_kind == "retro" else "routine"

        severity_raw = payload.get("severity")
        severity = int(severity_raw) if isinstance(severity_raw, (int, float)) else None

        wall_raw = payload.get("wall")
        wall = datetime.fromisoformat(wall_raw) if isinstance(wall_raw, str) else None

        truth_raw = payload.get("truth_doc_id")
        truth = truth_raw if isinstance(truth_raw, str) else None

        bonded_raw = payload.get("bonded_sev5", [])
        if not isinstance(bonded_raw, list):
            raise CorpusError("bonded_sev5 must be a list of document ids")
        bonded = tuple(str(x) for x in bonded_raw)

        facets_raw = payload.get("facets", {})
        if not isinstance(facets_raw, dict):
            raise CorpusError("facets must be an object")
        facets = {str(k): str(v) for k, v in facets_raw.items()}

        return cls(
            query_id=_str("query_id"),
            kind=kind,
            text=_str("text"),
            site_id=_str("site_id"),
            activity_path=_str("activity_path"),
            asset_class=_str("asset_class", required=False, default="unspecified"),
            severity=severity,
            wall=wall,
            truth_doc_id=truth,
            bonded_sev5=bonded,
            facets=facets,
            blinded=bool(payload.get("blinded", False)),
        )


@dataclass(frozen=True, slots=True)
class EvalCorpus:
    """Queries + judgements + split policy + provenance, loaded as one object.

    ``preliminary`` and ``synthetic`` are carried on the corpus rather than remembered
    by the person writing the slide. Every report this package renders stamps them.
    """

    name: str
    queries: tuple[EvalQuery, ...]
    qrels: QrelSet
    split_policy: SplitPolicy
    preliminary: bool = True
    synthetic: bool = False
    provenance: str = ""

    def __post_init__(self) -> None:
        if not self.queries:
            raise CorpusError(f"{self.name}: an empty corpus gates nothing")
        seen: set[str] = set()
        for q in self.queries:
            if q.query_id in seen:
                raise CorpusError(f"{self.name}: duplicate query_id {q.query_id!r}")
            seen.add(q.query_id)
        for q in self.queries:
            if q.kind == "retro" and q.truth_doc_id is not None:
                grade = self.qrels.grade(q.query_id, q.truth_doc_id)
                if grade is None:
                    raise CorpusError(
                        f"{self.name}: retro query {q.query_id} names truth precursor "
                        f"{q.truth_doc_id} but carries no judgement for it; the money "
                        "metric would score against a pair nobody adjudicated"
                    )
                if grade < 2:
                    raise CorpusError(
                        f"{self.name}: retro query {q.query_id} names truth precursor "
                        f"{q.truth_doc_id} graded {grade}; a truth precursor must be "
                        "graded at least 2 on the UMBRELA scale"
                    )

    @property
    def split_policy_id(self) -> str:
        return self.split_policy.policy_id

    def by_kind(self, kind: PermitKind) -> tuple[EvalQuery, ...]:
        return tuple(q for q in self.queries if q.kind == kind)

    @property
    def retro_severity_5(self) -> tuple[EvalQuery, ...]:
        return tuple(q for q in self.queries if q.kind == "retro" and q.is_severity_5)

    def label(self) -> str:
        """One line naming what this corpus is and is not. Rendered on every report."""
        bits = [self.name, f"n={len(self.queries)}", f"split={self.split_policy_id}"]
        if self.synthetic:
            bits.append("SYNTHETIC")
        if self.preliminary:
            bits.append("PRELIMINARY (no customer-grade floor claimed)")
        return " | ".join(bits)

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "n_queries": len(self.queries),
            "n_retro": len(self.by_kind("retro")),
            "n_retro_sev5": len(self.retro_severity_5),
            "n_routine": len(self.by_kind("routine")),
            "n_judgements": len(self.qrels),
            "split_policy": self.split_policy.to_dict(),
            "preliminary": self.preliminary,
            "synthetic": self.synthetic,
            "provenance": self.provenance,
        }


def _load_jsonl(path: Path) -> list[Mapping[str, object]]:
    rows: list[Mapping[str, object]] = []
    with path.open("r", encoding="utf-8") as handle:
        for lineno, raw in enumerate(handle, start=1):
            line = raw.strip()
            if not line or line.startswith("//"):
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise CorpusError(f"{path}:{lineno}: not valid JSON: {exc}") from exc
            if not isinstance(payload, dict):
                raise CorpusError(f"{path}:{lineno}: expected a JSON object")
            rows.append(payload)
    return rows


def load_corpus(directory: Path | str) -> EvalCorpus:
    """Load a corpus directory.

    Expected layout::

        <dir>/manifest.json    optional: name, preliminary, synthetic, provenance
        <dir>/queries.jsonl    one EvalQuery per line
        <dir>/qrels.jsonl      one Judgement per line
        <dir>/split.json       {wall, corpus_commit, kind, note}

    Every file is required except ``manifest.json``. A corpus without ``split.json`` is
    refused outright: a recall number with no split policy is not a measurement.
    """
    root = Path(directory)
    if not root.is_dir():
        raise CorpusError(f"corpus directory not found: {root}")

    split_path = root / "split.json"
    if not split_path.is_file():
        raise CorpusError(
            f"{root}: split.json is mandatory. A recall metric without a temporally-blocked "
            "split policy is a number without an experiment."
        )
    split_payload = json.loads(split_path.read_text(encoding="utf-8"))
    if not isinstance(split_payload, dict):
        raise CorpusError(f"{split_path}: expected a JSON object")
    wall_raw = split_payload.get("wall")
    commit_raw = split_payload.get("corpus_commit")
    if not isinstance(wall_raw, str) or not isinstance(commit_raw, str):
        raise CorpusError(f"{split_path}: 'wall' and 'corpus_commit' are mandatory strings")
    policy = SplitPolicy(
        wall=datetime.fromisoformat(wall_raw),
        corpus_commit=commit_raw,
        note=str(split_payload.get("note", "")),
    )

    queries_path = root / "queries.jsonl"
    if not queries_path.is_file():
        raise CorpusError(f"{root}: queries.jsonl not found")
    queries = tuple(EvalQuery.from_dict(row) for row in _load_jsonl(queries_path))

    qrels = load_qrels_jsonl(root / "qrels.jsonl")

    manifest: Mapping[str, object] = {}
    manifest_path = root / "manifest.json"
    if manifest_path.is_file():
        loaded = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise CorpusError(f"{manifest_path}: expected a JSON object")
        manifest = loaded

    return EvalCorpus(
        name=str(manifest.get("name", root.name)),
        queries=queries,
        qrels=qrels,
        split_policy=policy,
        preliminary=bool(manifest.get("preliminary", True)),
        synthetic=bool(manifest.get("synthetic", False)),
        provenance=str(manifest.get("provenance", "")),
    )


def bonded_truth(queries: Iterable[EvalQuery]) -> Mapping[str, Sequence[str]]:
    """``query_id -> bonded severity-5 doc ids``. The MI16 obligation set, from the corpus."""
    return {q.query_id: q.bonded_sev5 for q in queries if q.bonded_sev5}
