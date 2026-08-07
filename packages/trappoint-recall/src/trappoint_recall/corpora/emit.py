# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Writing gold sets to disk, and the flag that keeps a weak label out of a headline.

Three things are enforced here rather than remembered:

**1. The calibrator-only flag travels inside the qrels file.** G2 (structured-code
co-membership) is a large, automatable, *weak* signal: same accident classification,
same injury source, same equipment. It trains the calibrator and it must never appear in
``P@block`` or ``Retro-Recall``. A sidecar file can be lost in a copy; a naming
convention can be renamed. So the flag is written as the first line of the JSONL itself,
as a ``//!meta`` comment — a line
:func:`~trappoint_recall.eval.qrels.load_qrels_jsonl` already skips, and a line that
cannot be separated from the judgements it governs. The sidecar is written *as well*,
for tools that read metadata without parsing the data.

**2. Merging is refused, not resolved.** Two gold sets grading the same pair differently
is a real disagreement — G2 says "weak positive, grade 1", G3's adjudicator says
"irrelevant, grade 0" — and averaging it or taking the last writer would erase the one
observation that matters. :func:`merge_judgements` raises, mirroring
:meth:`~trappoint_recall.eval.qrels.QrelSet.build`.

**3. Every emitted file gets a REUSE ``.license`` sidecar.** JSONL cannot carry an SPDX
header on line 1 without becoming a file whose first record is not a record, so the
licence lives beside it, which is what REUSE specifies for exactly this case.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from trappoint_recall.corpora.provenance import FixtureProvenance
from trappoint_recall.eval.qrels import Judgement, QrelError, QrelSet

__all__ = [
    "HEADLINE_FORBIDDEN_GOLD_SETS",
    "META_PREFIX",
    "GoldSetMeta",
    "HeadlineUseRefused",
    "merge_judgements",
    "overlay_judgements",
    "read_qrels_meta",
    "refuse_headline_use",
    "sorted_judgements",
    "write_json",
    "write_jsonl",
    "write_license_sidecar",
    "write_qrels",
]

META_PREFIX: Final = "//!meta "
"""Marks the metadata line at the top of a qrels file.

Begins with ``//`` so the harness's loader skips it as a comment, and carries ``!meta``
so a reader can find it with a fixed-string grep."""

HEADLINE_FORBIDDEN_GOLD_SETS: Final[frozenset[str]] = frozenset({"G2"})
"""Gold sets whose labels may never appear in a published metric.

G2 is distant supervision over structured codes. Same classification + same injury
source + same equipment makes a plausible pair, not a relevant one, and a precision
figure computed over it would be measuring the coding manual."""

SPDX_HEADER: Final = (
    "SPDX-FileCopyrightText: 2026 MAINLINE contributors\nSPDX-License-Identifier: Apache-2.0\n"
)


class HeadlineUseRefused(RuntimeError):
    """Raised when a calibrator-only gold set is about to be scored as a headline metric."""


@dataclass(frozen=True, slots=True)
class GoldSetMeta:
    """The metadata line that governs a qrels file.

    Attributes:
        gold_set: ``G1``..``G4``, ``GS0``, or another identifier.
        calibrator_only: True when these labels may train a calibrator but may never be
            reported. Written as a flag, checked by :func:`refuse_headline_use`.
        headline_forbidden_reason: Why, in one sentence, so the flag is not cargo cult.
        n_judgements: Count, so a truncated file is visible without parsing it all.
        basis: How the labels were produced.
        provenance: Where the underlying records came from and who may see them.
        build: Free-form build detail (drop counts, walls, seeds).
    """

    gold_set: str
    calibrator_only: bool
    headline_forbidden_reason: str
    n_judgements: int
    basis: str
    provenance: FixtureProvenance
    build: Mapping[str, object]

    def to_dict(self) -> dict[str, object]:
        return {
            "gold_set": self.gold_set,
            "calibrator_only": self.calibrator_only,
            "headline_forbidden_reason": self.headline_forbidden_reason,
            "n_judgements": self.n_judgements,
            "basis": self.basis,
            "provenance": self.provenance.model_dump(mode="json"),
            "build": dict(self.build),
            "schema": "https://mainline.dev/schema/recall/qrels-v1.schema.json",
        }

    def to_meta_line(self) -> str:
        return META_PREFIX + json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))


def sorted_judgements(judgements: Iterable[Judgement]) -> tuple[Judgement, ...]:
    """Deterministic order: ``(query_id, -grade, doc_id)``.

    Descending grade puts the precursor first, which makes a hand-inspected file readable
    top-down; the total order makes a rebuild byte-identical.
    """
    return tuple(sorted(judgements, key=lambda j: (j.query_id, -j.grade, j.doc_id)))


def merge_judgements(*groups: Sequence[Judgement]) -> tuple[Judgement, ...]:
    """Concatenate judgement groups, refusing a contradiction.

    Raises:
        QrelError: when two groups grade the same ``(query_id, doc_id)`` differently.
            Adjudicate the pair; do not average it.
    """
    seen: dict[tuple[str, str], Judgement] = {}
    out: list[Judgement] = []
    for group in groups:
        for judgement in group:
            key = (judgement.query_id, judgement.doc_id)
            previous = seen.get(key)
            if previous is None:
                seen[key] = judgement
                out.append(judgement)
                continue
            if previous.grade != judgement.grade:
                raise QrelError(
                    f"contradictory judgements for {key}: gold set {previous.gold_set} "
                    f"graded {previous.grade}, gold set {judgement.gold_set} graded "
                    f"{judgement.grade}. Merging would erase a real disagreement between "
                    "a weak signal and an adjudicator; adjudicate the pair instead."
                )
    return sorted_judgements(out)


def overlay_judgements(
    base: Sequence[Judgement], overlay: Sequence[Judgement]
) -> tuple[Judgement, ...]:
    """``overlay`` supersedes ``base`` on any ``(query_id, doc_id)`` they share.

    Unlike :func:`merge_judgements` this is not a refusal, because the disagreement it
    resolves is not a contradiction between equals: an adjudicated human judgement
    *supersedes* a distantly-supervised one by construction, and the note on the surviving
    judgement records what it replaced.

    Use :func:`merge_judgements` between peers and this between a weak signal and its
    adjudication. Using the wrong one is how a human grade gets silently overwritten by a
    heuristic, so they are two functions with two names rather than one with a flag.
    """
    superseding = {(j.query_id, j.doc_id): j for j in overlay}
    out: list[Judgement] = [
        j for j in base if (j.query_id, j.doc_id) not in superseding
    ]
    out.extend(superseding.values())
    return sorted_judgements(out)


def refuse_headline_use(
    judgements: Iterable[Judgement] | QrelSet, *, metric: str
) -> None:
    """Refuse to compute a published metric over calibrator-only labels.

    Args:
        judgements: The labels about to be scored.
        metric: The metric being computed, quoted back in the refusal.

    Raises:
        HeadlineUseRefused: if any judgement belongs to a calibrator-only gold set.
    """
    items = judgements.judgements if isinstance(judgements, QrelSet) else tuple(judgements)
    offenders = sorted({j.gold_set for j in items if j.gold_set in HEADLINE_FORBIDDEN_GOLD_SETS})
    if offenders:
        raise HeadlineUseRefused(
            f"{metric} refused over gold set(s) {offenders}: these are calibrator-only. "
            "G2 pairs share an accident classification, an injury source and an equipment "
            "code — that is a plausible pair, not a relevant one, and a precision figure "
            "computed over it measures the coding manual rather than the retriever."
        )


# --------------------------------------------------------------------------------------
# Writers
# --------------------------------------------------------------------------------------


def write_license_sidecar(path: Path | str) -> Path:
    """Write ``<path>.license`` with the REUSE SPDX header. Returns the sidecar path."""
    sidecar = Path(f"{path}.license")
    sidecar.parent.mkdir(parents=True, exist_ok=True)
    sidecar.write_text(SPDX_HEADER, encoding="utf-8")
    return sidecar


def write_jsonl(
    path: Path | str,
    rows: Iterable[Mapping[str, object]],
    *,
    header: str | None = None,
    licence: bool = True,
) -> Path:
    """Write JSONL with sorted keys and ``\\n`` endings, plus the licence sidecar.

    Line endings are forced to ``\\n`` and the file is opened with ``newline=''`` so a
    Windows checkout produces the same bytes as a Linux one — a digest over a fixture
    that changed only in line endings would fail for a reason nobody could see.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="") as handle:
        if header is not None:
            handle.write(header + "\n")
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
            handle.write("\n")
    if licence:
        write_license_sidecar(target)
    return target


def write_json(path: Path | str, payload: Mapping[str, object], *, licence: bool = True) -> Path:
    """Write pretty-printed JSON with sorted keys, plus the licence sidecar."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="") as handle:
        handle.write(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False))
        handle.write("\n")
    if licence:
        write_license_sidecar(target)
    return target


def write_qrels(path: Path | str, judgements: Sequence[Judgement], meta: GoldSetMeta) -> Path:
    """Write a qrels JSONL with its metadata line, refusing an inconsistent flag.

    Raises:
        ValueError: if ``meta.n_judgements`` disagrees with the judgements written, if a
            judgement's ``gold_set`` disagrees with ``meta.gold_set``, or if the
            calibrator-only flag disagrees with
            :data:`HEADLINE_FORBIDDEN_GOLD_SETS`. All three would produce a file whose
            governing flag was decorative.
    """
    ordered = sorted_judgements(judgements)
    if meta.n_judgements != len(ordered):
        raise ValueError(
            f"{path}: meta declares {meta.n_judgements} judgements, {len(ordered)} written"
        )
    wrong = sorted({j.gold_set for j in ordered if j.gold_set != meta.gold_set})
    if wrong:
        raise ValueError(
            f"{path}: meta names gold set {meta.gold_set!r} but the file carries {wrong}; "
            "one flag cannot govern two gold sets"
        )
    expected_flag = meta.gold_set in HEADLINE_FORBIDDEN_GOLD_SETS
    if expected_flag and not meta.calibrator_only:
        raise ValueError(
            f"{path}: gold set {meta.gold_set!r} is calibrator-only by policy but the "
            "file's flag says otherwise; the flag is the enforcement, so it cannot lie"
        )
    # QrelSet.build is the same validation the harness applies on load. Running it here
    # means a contradictory file is refused at write time rather than at measure time.
    QrelSet.build(ordered)
    return write_jsonl(
        path,
        (j.model_dump(mode="json") for j in ordered),
        header=meta.to_meta_line(),
    )


def read_qrels_meta(path: Path | str) -> GoldSetMeta:
    """Read the ``//!meta`` line back.

    Raises:
        QrelError: if the file has no metadata line. A qrels file without one has no
            governing flag, and an ungoverned weak label is exactly the failure mode the
            flag exists to prevent.
    """
    source = Path(path)
    with source.open("r", encoding="utf-8") as handle:
        for raw in handle:
            line = raw.strip()
            if not line:
                continue
            if not line.startswith(META_PREFIX):
                break
            payload = json.loads(line[len(META_PREFIX) :])
            return GoldSetMeta(
                gold_set=str(payload["gold_set"]),
                calibrator_only=bool(payload["calibrator_only"]),
                headline_forbidden_reason=str(payload["headline_forbidden_reason"]),
                n_judgements=int(payload["n_judgements"]),
                basis=str(payload["basis"]),
                provenance=FixtureProvenance.model_validate(payload["provenance"]),
                build=dict(payload.get("build", {})),
            )
    raise QrelError(
        f"{source}: no {META_PREFIX.strip()} line. Every qrels file this package writes "
        "carries its governing metadata on line 1; a file without one cannot declare "
        "whether its labels may be reported."
    )
