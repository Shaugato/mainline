# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""JSONL emission, byte-reproducibly, with the projected-column guard.

Four properties, each of which is a test somebody else is going to run:

1. **LF line endings, always.**  Files are opened with ``newline="\\n"`` so a Windows producer
   and a Linux CI runner emit the same bytes.  Without this the whole reproducibility claim
   dies on the OS matrix, silently, and only on one leg of it.
2. **Key-sorted, separator-tight JSON.**  ``sort_keys=True`` with ``(",", ":")`` separators, so
   the serialisation is a function of the *value* and not of dict insertion order.
3. **Rows sorted by a declared key.**  Every table declares how to sort itself.  A generator
   that emits in draw order would produce a diff on every unrelated parameter change.
4. **No projected column, ever.**  Decision D8: a corpus loader that writes ``open_blocking`` or
   ``sev_max`` directly would launder the flagship claim one hop upstream — the projection would
   look right while never having been derived from anything.  This module refuses such a row at
   the point of emission, so the failure is a build error and not a passing test.

The guard is *enforced, not trusted* (principle P2): the denylist is the union of a built-in
list and ``PROJECTED-COLUMNS.yaml`` when ``corpus-freeze-load`` has shipped it, and the file
takes priority in the sense that anything it adds is added.  It can never *remove* a name.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

import yaml

__all__ = [
    "BUILTIN_PROJECTED_COLUMNS",
    "Emitter",
    "ProjectedColumnError",
    "TableSpec",
    "canonical_json",
    "projected_columns",
]


class ProjectedColumnError(RuntimeError):
    """A row named a column that only a trigger may write."""


#: Columns that a trigger projects from an authoritative table.  Naming one in an emitted row —
#: and therefore in an ``INSERT`` — would mean the gate reads a number the writer supplied.
#:
#: Sources: ARCHITECTURE.md §5.2 (``doc.open_token_count``), §5.3 (the M2 bloodline columns),
#: §5.4 (``clause_blame_closure``), §5.5 (the six permit counters, ``blocking_check.severity``
#: and ``virulence``, ``boundary_certificate``'s derived counts), §5.8 (``identity_residue``).
BUILTIN_PROJECTED_COLUMNS: Final[frozenset[str]] = frozenset(
    {
        # permit / change_request counters — the six named refusals read these
        "open_blocking",
        "open_residue",
        "open_conflicts",
        "open_warrants",
        "unmodelled_asset_count",
        "unmet_floor_count",
        "countersigned_count",
        # the epoch pin and the RLS scope token are trigger-filled
        "site_role",
        "head_seq",
        "gate_epoch",
        # clause_version bloodline (M2)
        "sev_max",
        "blood_root",
        "blood_peaks",
        "blood_size",
        # banded once, in the closure, from the blame ancestry
        "virulence",
        # doc: control series still carried
        "open_token_count",
        # clause_blame_closure derivations
        "ancestor_events",
        "ancestor_count",
        "max_severity",
        "closure_gen",
        # boundary_certificate: derived from the energy graph, never declared
        "tags_resolved",
        "tags_unmodelled",
        "under_declared",
        # identity_residue
        "max_ancestral_severity",
    }
)


def _load_shipped_denylist(repo_root: Path | None) -> frozenset[str]:
    """Union in ``PROJECTED-COLUMNS.yaml`` if ``corpus-freeze-load`` has shipped it.

    Absent, this returns empty and the built-in list stands alone — the guard degrades to
    "fewer names", never to "no guard".  Present, it can only add.
    """
    if repo_root is None:
        return frozenset()
    candidate = (
        repo_root
        / "verticals"
        / "mainline"
        / "packages"
        / "mainline-corpus"
        / "PROJECTED-COLUMNS.yaml"
    )
    if not candidate.is_file():
        return frozenset()
    try:
        parsed = yaml.safe_load(candidate.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError):
        # A malformed sibling file owned by another worker must not break this build, and it must
        # not silently weaken the guard either: the built-in denylist still applies in full.
        return frozenset()
    names: set[str] = set()

    def _walk(node: Any) -> None:
        if isinstance(node, str):
            names.add(node)
        elif isinstance(node, Mapping):
            for key, value in node.items():
                if isinstance(key, str) and key not in {"version", "columns", "tables", "notes"}:
                    names.add(key)
                _walk(value)
        elif isinstance(node, Sequence):
            for item in node:
                _walk(item)

    _walk(parsed)
    return frozenset(name for name in names if name.isidentifier())


def projected_columns(repo_root: Path | None = None) -> frozenset[str]:
    """The effective denylist: built-in, plus anything the shipped YAML adds."""
    return BUILTIN_PROJECTED_COLUMNS | _load_shipped_denylist(repo_root)


_JSON_SCALARS: Final[tuple[type, ...]] = (str, int, float, bool, type(None))


def _check_json_native(value: Any, *, path: str) -> None:
    """Refuse anything that is not already a JSON-native value.

    ``json.dumps`` would happily serialise a ``uuid.UUID`` via ``default=str`` if we let it, and
    a ``datetime`` via ``isoformat`` — and then the emitted offset would depend on whichever
    helper reached it first.  Conversion happens in the generators, deliberately and visibly, so
    that every string in the corpus was produced by exactly one code path.
    """
    if isinstance(value, bool) or value is None or isinstance(value, (str, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise TypeError(f"{path}: non-finite float {value!r} cannot be serialised reproducibly")
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError(f"{path}: object keys must be strings, got {type(key).__name__}")
            _check_json_native(item, path=f"{path}.{key}")
        return
    if isinstance(value, (list, tuple)):
        for position, item in enumerate(value):
            _check_json_native(item, path=f"{path}[{position}]")
        return
    raise TypeError(
        f"{path}: {type(value).__name__} is not JSON-native. Convert UUIDs with str() and "
        "datetimes with clock.iso() in the generator, so every emitted string has exactly one "
        "producer."
    )


def canonical_json(row: Mapping[str, Any]) -> str:
    """Serialise one row: key-sorted, tight separators, UTF-8, no trailing whitespace."""
    _check_json_native(row, path="row")
    return json.dumps(row, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


@dataclass(frozen=True, slots=True)
class TableSpec:
    """How one output file is written and what it means.

    ``table`` is the ``mainline.*`` table the rows load into, or ``None`` for a file that is
    corpus scaffolding rather than a database table (the asset registry, the revision cadence,
    the pending register).  ``index.json`` records the distinction so the loader never has to
    guess, and so a reader can tell at a glance which files are claims about the schema.
    """

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
class Emitter:
    """Writes the skeleton tree and the index that describes it."""

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

    def guard(self, row: Mapping[str, Any], *, origin: str) -> None:
        """Raise if the row names a projected column."""
        offending = sorted(set(row).intersection(self._denylist))
        if offending:
            raise ProjectedColumnError(
                f"{origin}: row names projected column(s) {offending}. "
                "A projection is written by a trigger from an authoritative table; a corpus that "
                "supplies one directly makes the gate read a number the writer chose (D8, P2)."
            )

    def write(self, spec: TableSpec, rows: Iterable[Mapping[str, Any]]) -> FileRecord:
        """Write one JSONL file and return its record.

        Rows are materialised, guarded, sorted by ``spec.sort_key`` and serialised.  The sort is
        checked for total order: two rows with the same key would make the output depend on the
        generator's emission order, which is exactly the class of nondeterminism this module
        exists to remove.
        """
        materialised = [dict(row) for row in rows]
        for position, row in enumerate(materialised):
            self.guard(row, origin=f"{spec.filename}[{position}]")

        keys = [spec.sort_key(row) for row in materialised]
        if len(set(keys)) != len(keys):
            duplicates = sorted({key for key in keys if keys.count(key) > 1})[:5]
            raise ValueError(
                f"{spec.filename}: sort key is not unique (e.g. {duplicates}). "
                "A non-total sort makes the file order depend on emission order, which is not "
                "reproducible."
            )
        materialised.sort(key=spec.sort_key)

        payload = "".join(canonical_json(row) + "\n" for row in materialised)
        encoded = payload.encode("utf-8")
        target = self.out_dir / spec.filename
        with target.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)

        record = FileRecord(
            filename=spec.filename,
            table=spec.table,
            rows=len(materialised),
            sha256=hashlib.sha256(encoded).hexdigest(),
            bytes_written=len(encoded),
            description=spec.description,
        )
        self._files.append(record)
        return record

    def write_index(self, payload: Mapping[str, Any]) -> FileRecord:
        """Write ``index.json``.

        It describes every other file and is deliberately written last, so a build that dies
        halfway leaves an output tree with no index — which is unambiguously incomplete rather
        than plausibly complete.
        """
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
        _check_json_native(body, path="index")
        text = json.dumps(body, sort_keys=True, ensure_ascii=False, indent=2) + "\n"
        encoded = text.encode("utf-8")
        target = self.out_dir / "index.json"
        with target.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        record = FileRecord(
            filename="index.json",
            table=None,
            rows=len(self._files),
            sha256=hashlib.sha256(encoded).hexdigest(),
            bytes_written=len(encoded),
            description="manifest of this skeleton tree; written last",
        )
        return record
