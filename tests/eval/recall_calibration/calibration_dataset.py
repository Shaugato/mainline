# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Where the calibration numbers come from — one resolution rule, one place.

The lane and the tests must answer the same question: *which labelled set produced this
reliability diagram?* Answering it twice is how a report ends up naming a corpus other than
the one it measured, so the rule lives here.

Resolution order:

1. ``$TRAPPOINT_RECALL_CALIBRATION_SET`` — an explicit override, for a lane pointed at the
   real adjudicated set.
2. ``tests/fixtures/recall/gs0/calibration_g2g3.json`` — the shared gold set, once
   ``recall-corpora-goldsets`` lands it.
3. ``tests/eval/recall_calibration/fixtures/calibration_g2g3.json`` — the committed
   synthetic stand-in.

**The fallback is never a skip, and never silent.** A lane that skips because a corpus is
missing is not a lane; a lane that falls back without saying so publishes a synthetic number
under a real corpus's name. So the fixture header carries ``synthetic`` and ``preliminary``,
every artefact reproduces them, and an override that points at nothing raises.

The split is the harness's own: :class:`~trappoint_recall.eval.splits.SplitPolicy` with the
three conjunctive predicates (``occurred_at < wall``, ``ingested_at < wall``,
``corpus_commit <= wall``) and no ``AS OF SYSTEM TIME`` anywhere near it — CockroachDB's
default ``gc.ttlseconds`` is four hours, so an AOST read cannot reach a wall months back
(recall lead D12). Fit takes what the wall admits; evaluation takes what it withholds; and
:func:`load_calibration_set` refuses a set in which any fold straddles the wall, because a
fold on both sides is a leak wearing a plausible name.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Final

SUITE_DIR: Final[Path] = Path(__file__).resolve().parent
REPO_ROOT: Final[Path] = SUITE_DIR.parents[2]
PACKAGE_SRC: Final[Path] = REPO_ROOT / "packages" / "trappoint-recall" / "src"

SELFTEST_SET: Final[Path] = SUITE_DIR / "fixtures" / "calibration_g2g3.json"
GS0_SET: Final[Path] = REPO_ROOT / "tests" / "fixtures" / "recall" / "gs0" / "calibration_g2g3.json"
ARTEFACTS: Final[Path] = SUITE_DIR / "artefacts"

ENV_OVERRIDE: Final = "TRAPPOINT_RECALL_CALIBRATION_SET"
SCHEMA: Final = "mainline.recall.calibration_set/1"

__all__ = [
    "ARTEFACTS",
    "ENV_OVERRIDE",
    "GS0_SET",
    "PACKAGE_SRC",
    "REPO_ROOT",
    "SELFTEST_SET",
    "SUITE_DIR",
    "CalibrationSet",
    "ensure_import_paths",
    "load_calibration_set",
    "resolve_calibration_set",
]


def ensure_import_paths() -> None:
    """Put the suite directory and the package source on ``sys.path``.

    Normally a no-op under the uv workspace. It exists so the lane also runs from a bare
    checkout: *"the calibration suite would not import"* must never be why a lane reports
    anything other than red.
    """
    for entry in (SUITE_DIR, PACKAGE_SRC):
        text = str(entry)
        if entry.is_dir() and text not in sys.path:
            sys.path.insert(0, text)


ensure_import_paths()

from trappoint_recall.eval.splits import (  # noqa: E402
    SplitPolicy,
    SplitRecord,
    temporally_blocked_split,
)
from trappoint_recall.fusion.calibration import CalibrationSample  # noqa: E402


def resolve_calibration_set(environ: dict[str, str] | None = None) -> tuple[Path, str]:
    """Return the labelled set this run must measure, and where it came from.

    Raises:
        RuntimeError: if the override is set but names no file. Refusing to fall back is the
            point: an override that misses is a misconfiguration, not a default.
    """
    env = os.environ if environ is None else environ
    override = env.get(ENV_OVERRIDE)
    if override:
        path = Path(override)
        if not path.is_file():
            raise RuntimeError(
                f"{ENV_OVERRIDE} points at {path}, which is not a file. Refusing to fall "
                "back silently: a synthetic number published under a real corpus's name is "
                "worse than no number."
            )
        return path, f"env:{ENV_OVERRIDE}"
    if GS0_SET.is_file():
        return GS0_SET, "gs0"
    return SELFTEST_SET, "selftest"


@dataclass(frozen=True, slots=True)
class CalibrationSet:
    """A labelled set already partitioned by a temporal wall."""

    source: str
    path: Path
    synthetic: bool
    preliminary: bool
    note: str
    policy: SplitPolicy
    fit: tuple[CalibrationSample, ...]
    evaluation: tuple[CalibrationSample, ...]

    @property
    def fit_folds(self) -> tuple[str, ...]:
        return tuple(sorted({sample.fold for sample in self.fit}))

    @property
    def eval_folds(self) -> tuple[str, ...]:
        return tuple(sorted({sample.fold for sample in self.evaluation}))

    @property
    def split_policy_id(self) -> str:
        return self.policy.policy_id

    def label(self) -> str:
        marks = []
        if self.synthetic:
            marks.append("SYNTHETIC")
        if self.preliminary:
            marks.append("PRELIMINARY")
        suffix = f" [{', '.join(marks)}]" if marks else ""
        return f"{self.source}:{self.path.name}{suffix}"

    def provenance(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "path": str(self.path),
            "synthetic": self.synthetic,
            "preliminary": self.preliminary,
            "note": self.note,
            "split": self.policy.to_dict(),
            "fit_folds": list(self.fit_folds),
            "eval_folds": list(self.eval_folds),
            "n_fit": len(self.fit),
            "n_eval": len(self.evaluation),
        }


def load_calibration_set(path: Path | None = None) -> CalibrationSet:
    """Load and temporally partition the labelled set.

    Raises:
        ValueError: on an unknown schema, an empty side of the wall, or a fold that appears
            on both sides of it.
    """
    resolved, source = resolve_calibration_set()
    target = path or resolved
    document: dict[str, Any] = json.loads(target.read_text(encoding="utf-8"))
    if document.get("schema") != SCHEMA:
        raise ValueError(
            f"{target} declares schema {document.get('schema')!r}; this lane reads {SCHEMA!r} "
            "and refuses to guess at the columns"
        )

    policy = SplitPolicy(
        wall=datetime.fromisoformat(str(document["wall"])),
        corpus_commit=str(document["corpus_commit"]),
        note="calibration fit/evaluation wall",
    )
    records = [
        SplitRecord(
            doc_id=str(entry["doc_id"]),
            occurred_at=datetime.fromisoformat(str(entry["occurred_at"])),
            ingested_at=datetime.fromisoformat(str(entry["ingested_at"])),
            corpus_commit_at=datetime.fromisoformat(str(entry["corpus_commit_at"])),
        )
        for entry in document["samples"]
    ]
    split = temporally_blocked_split(records, policy)
    admitted = set(split.indexable)

    fit: list[CalibrationSample] = []
    evaluation: list[CalibrationSample] = []
    for entry in document["samples"]:
        sample = CalibrationSample(
            score=float(entry["raw_score"]),
            label=int(entry["label"]),
            fold=str(entry["fold"]),
            doc_id=str(entry["doc_id"]),
            gold_set=str(entry.get("gold_set", "")),
        )
        (fit if sample.doc_id in admitted else evaluation).append(sample)

    if not fit or not evaluation:
        raise ValueError(
            f"{target}: the wall at {policy.wall.isoformat()} puts every sample on one side "
            "of the split; there is nothing to hold out"
        )
    straddling = sorted({s.fold for s in fit} & {s.fold for s in evaluation})
    if straddling:
        raise ValueError(
            f"{target}: fold(s) {straddling} appear on both sides of the wall. A fold that "
            "straddles the wall leaks the future into the evaluation and does it under a "
            "name that looks blocked."
        )

    return CalibrationSet(
        source=source,
        path=target,
        synthetic=bool(document.get("synthetic", False)),
        preliminary=bool(document.get("preliminary", True)),
        note=str(document.get("note", "")),
        policy=policy,
        fit=tuple(fit),
        evaluation=tuple(evaluation),
    )
