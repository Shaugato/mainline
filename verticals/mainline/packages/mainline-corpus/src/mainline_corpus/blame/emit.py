# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Byte-reproducible emission for the answer key, on stage 1's rules.

``canonical_json`` and the projected-column denylist are imported from
``mainline_corpus.skeleton.emit`` rather than re-implemented: two canonicalisers in one package
is two chances for a corpus to disagree with itself about what its own bytes are, and the
projected-column guard is a shared safety property, not a per-stage preference.

What this module adds over stage 1's emitter is a second file kind.  The answer key ships JSON
documents as well as JSONL tables — ``gs0.schema.json``, ``spine.json``, the churn report — and
each of them needs to appear in ``index.json`` with a digest, so ``MANIFEST.sha256`` and
``corpus.lock.json`` can cover the whole directory rather than only the tables.

Every emitted data file gets a ``.license`` sidecar.  JSON cannot carry a comment, REUSE's
answer to that is a sidecar, and a fixture tree that fails a licence check is a fixture tree
that fails CI for a reason nobody enjoys diagnosing at 02:00.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..skeleton.emit import ProjectedColumnError, canonical_json, projected_columns

__all__ = ["AnswerKeyEmitter", "FileRecord", "TableSpec"]

_LICENSE_TEXT = (
    "SPDX-FileCopyrightText: 2026 MAINLINE contributors\nSPDX-License-Identifier: FSL-1.1-ALv2\n"
)


@dataclass(frozen=True, slots=True)
class TableSpec:
    """How one JSONL file is written and what it means."""

    filename: str
    table: str | None
    sort_key: Callable[[Mapping[str, Any]], tuple[Any, ...]]
    description: str


@dataclass(slots=True)
class FileRecord:
    filename: str
    table: str | None
    rows: int
    sha256: str
    bytes_written: int
    description: str


@dataclass(slots=True)
class AnswerKeyEmitter:
    """Writes the answer-key tree and the index that describes it."""

    out_dir: Path
    repo_root: Path | None = None
    _denylist: frozenset[str] = field(default_factory=frozenset, init=False)
    _files: list[FileRecord] = field(default_factory=list, init=False)

    def __post_init__(self) -> None:
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self._denylist = projected_columns(self.repo_root)

    @property
    def files(self) -> Sequence[FileRecord]:
        return tuple(self._files)

    @property
    def denylist(self) -> frozenset[str]:
        return self._denylist

    def guard(self, row: Mapping[str, Any], *, origin: str) -> None:
        offending = sorted(set(row).intersection(self._denylist))
        if offending:
            raise ProjectedColumnError(
                f"{origin}: row names projected column(s) {offending}. A projection is written by "
                "a trigger from an authoritative table; an answer key that supplied one would "
                "make the gate read a number the writer chose (D8, P2)."
            )

    def _write_bytes(self, filename: str, payload: bytes) -> None:
        target = self.out_dir / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("wb") as handle:
            handle.write(payload)
        with (self.out_dir / f"{filename}.license").open(
            "w", encoding="utf-8", newline="\n"
        ) as handle:
            handle.write(_LICENSE_TEXT)

    def write_table(self, spec: TableSpec, rows: Iterable[Mapping[str, Any]]) -> FileRecord:
        """Write one JSONL file: guarded, totally ordered, canonically serialised, LF-only."""
        materialised = [dict(row) for row in rows]
        for position, row in enumerate(materialised):
            self.guard(row, origin=f"{spec.filename}[{position}]")

        keys = [spec.sort_key(row) for row in materialised]
        if len(set(keys)) != len(keys):
            counts: dict[tuple[Any, ...], int] = {}
            for key in keys:
                counts[key] = counts.get(key, 0) + 1
            duplicates = sorted(key for key, count in counts.items() if count > 1)[:5]
            raise ValueError(
                f"{spec.filename}: sort key is not unique (e.g. {duplicates}). A non-total sort "
                "makes the file order depend on emission order, which is not reproducible."
            )
        materialised.sort(key=spec.sort_key)

        payload = "".join(canonical_json(row) + "\n" for row in materialised).encode("utf-8")
        self._write_bytes(spec.filename, payload)
        record = FileRecord(
            filename=spec.filename,
            table=spec.table,
            rows=len(materialised),
            sha256=hashlib.sha256(payload).hexdigest(),
            bytes_written=len(payload),
            description=spec.description,
        )
        self._files.append(record)
        return record

    def write_document(
        self, filename: str, body: Mapping[str, Any], *, description: str
    ) -> FileRecord:
        """Write one JSON document — indented, key-sorted, LF-terminated."""
        text = json.dumps(body, sort_keys=True, ensure_ascii=False, indent=2) + "\n"
        payload = text.encode("utf-8")
        self._write_bytes(filename, payload)
        record = FileRecord(
            filename=filename,
            table=None,
            rows=1,
            sha256=hashlib.sha256(payload).hexdigest(),
            bytes_written=len(payload),
            description=description,
        )
        self._files.append(record)
        return record

    def write_index(self, payload: Mapping[str, Any]) -> FileRecord:
        """Write ``index.json`` last, so a build that dies leaves a tree that is visibly partial."""
        body = dict(payload)
        body["files"] = {
            record.filename: {
                "bytes": record.bytes_written,
                "description": record.description,
                "rows": record.rows,
                "sha256": record.sha256,
                "table": record.table,
            }
            for record in sorted(self._files, key=lambda item: item.filename)
        }
        body["projected_columns_denied"] = sorted(self._denylist)
        text = json.dumps(body, sort_keys=True, ensure_ascii=False, indent=2) + "\n"
        encoded = text.encode("utf-8")
        self._write_bytes("index.json", encoded)
        return FileRecord(
            filename="index.json",
            table=None,
            rows=len(self._files),
            sha256=hashlib.sha256(encoded).hexdigest(),
            bytes_written=len(encoded),
            description="manifest of this answer-key tree; written last",
        )
