# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""``migrations.lock.json`` — a **manifest** of the migration tree, never a declaration.

Migration-reconciliation ruling **MR-6 lock 1**:
``verticals/mainline/db/migrations.allocation.toml`` is the authority for numbers, and
the lock file is *generated* by walking
:func:`trappoint_migrate.discovery.discover` over the tree and resolving each file
against that allocation. The distinction is the entire point of the file:

> a lock file that is hand-written is a second source of truth, which is the class of
> failure this ruling exists to end.

The incident it ends is on the record. Two domains implemented the same section of the
migration order under two conventions; the pre-dispatch collision check compared one
side's *bands* with the other side's *file paths* as strings, found nothing in common,
and reported zero collisions. It was wrong by twenty numbers. Every field below is
derived from a file on disk or from the allocation — nothing is asserted — so a
disagreement between the manifest and the tree is a **regeneration**, never a debate.

What each field answers, and why it is worth a field:

===================== ===========================================================
``number`` / ``band`` which grant this file is written under (MR-6 rule B)
``owner``             who to ask before touching it
``mode``              rendered or authored; a hand-authored twin of a rendered file
                      is CI-green and deploy-dead, so the mode is checked, not assumed
``template``          for a rendered file, the ``.j2`` a change to it must be made in
``invariants``        the ``MI:``/``I:`` citation the MI catalogue projects from
``sha256``            exactly what the runner records in ``trappoint.schema_migration``
``counsel_gated``     DM-17's five files, addressable as a set rather than by memory;
                      ``null`` when the header does not say, which is not "no"
===================== ===========================================================

DR-7 in `docs/leads/datamodel.md` is what this answers: seventy-nine tables across two
hundred files is more surface than one review pass can hold, and the header block plus
this manifest plus the MI catalogue are what make the set *walkable* by a stranger.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .discovery import MigrationFile, discover
from .errors import MigrationTreeInvalid, UsageError
from .header import parse_header
from .lint import RENDERED_BANNER, Allocation, find_allocation, key_of_filename
from .sqltext import header_comment

__all__ = [
    "LOCK_FILENAME",
    "LOCK_SCHEMA_VERSION",
    "LockEntry",
    "build_lock",
    "counsel_gated_files",
    "lock_path_for",
    "render_lock",
    "verify_lock",
    "write_lock",
]

#: The lock lives beside the tree it describes, sharing the allocation's naming shape:
#: ``<dir>/migrations`` is described by ``<dir>/migrations.lock.json``.
LOCK_FILENAME = "migrations.lock.json"

LOCK_SCHEMA_VERSION = 1

_TEMPLATE_KEY = "@template"
_BANNER_WINDOW = 4096

_COMMENT = (
    "GENERATED — DO NOT EDIT BY HAND. This file is a manifest of the migration tree, "
    "not a declaration about it. Every field is derived from the files on disk and from "
    "migrations.allocation.toml, which is the authority for numbers (MR-6 lock 1). A "
    "hand-edited entry is a second source of truth, which is the class of failure the "
    "migration reconciliation of 2026-08-08 exists to end. Regenerate; do not patch."
)

_GENERATED_FROM: dict[str, Any] = {
    "allocation": "<tree>.allocation.toml",
    "ruling": "docs/leads/migration-reconciliation.md",
    "convention": "NNNN[a-z]_lower_snake_slug.sql (MR-5)",
    "discovery": "trappoint_migrate.discovery.discover()",
    "band_resolution": (
        "trappoint_migrate.lint.load_allocation() + trappoint_migrate.lint.key_of_filename()"
    ),
    "mode_resolution": (
        "presence of '-- @rendered-by  trappoint render' in the first 4096 characters "
        "(the window trappoint_migrate.lint reads)"
    ),
    "sha256": (
        "sha256 of the file bytes; asserted equal to "
        "trappoint_migrate.discovery.MigrationFile.sha256, which is what the runner "
        "records in trappoint.schema_migration"
    ),
    "invariants": (
        "trappoint_migrate.discovery.MigrationFile.cited_invariants, de-duplicated on "
        "first appearance"
    ),
    "counsel_gated": (
        "the 'COUNSEL-GATED:' key of the leading comment block "
        "(trappoint_migrate.sqltext.header_comment); null when the header omits it"
    ),
    "ordering": (
        "lexicographic on the whole version stem, which is the order the runner applies "
        "in (ruling D7)"
    ),
    "generator": "trappoint_migrate.lockfile.build_lock() — `trappoint migrate lock --write`",
    "verified_by": [
        "trappoint migrate lint --root <tree>",
        "trappoint migrate lock --check --migrations <tree>",
    ],
}


@dataclass(frozen=True, slots=True)
class LockEntry:
    """One migration as the manifest records it."""

    file: str
    version: str
    number: str
    mode: str
    band: str | None
    owner: str | None
    template: str | None
    invariants: tuple[str, ...]
    sha256: str
    counsel_gated: bool | None

    def as_json(self) -> dict[str, Any]:
        """Return the entry in the manifest's committed field order."""
        return {
            "file": self.file,
            "version": self.version,
            "number": self.number,
            "mode": self.mode,
            "band": self.band,
            "owner": self.owner,
            "template": self.template,
            "invariants": list(self.invariants),
            "sha256": self.sha256,
            "counsel_gated": self.counsel_gated,
        }


def lock_path_for(root: Path) -> Path:
    """Return the manifest path for the migration tree *root*.

    Beside the directory, not inside it: a ``.json`` in the apply path is one glob away
    from being read as a migration, and the allocation file already sits here for the
    same reason.
    """
    directory = root if root.is_dir() else root.parent
    return directory.parent / f"{directory.name}.lock.json"


def _template_of(sql: str) -> str | None:
    """Return the template a rendered file names, or None when it names none."""
    window = sql[:_BANNER_WINDOW]
    if RENDERED_BANNER not in window:
        return None
    for line in header_comment(sql).splitlines():
        stripped = line.strip()
        if not stripped.startswith("--"):
            continue
        body = stripped[2:].strip()
        if body.startswith(_TEMPLATE_KEY):
            value = body[len(_TEMPLATE_KEY) :].strip()
            if value:
                return value
    return None


def _mode_of(sql: str) -> str:
    return "rendered" if RENDERED_BANNER in sql[:_BANNER_WINDOW] else "authored"


def _dedupe(tokens: Sequence[str]) -> tuple[str, ...]:
    """De-duplicate on first appearance.

    ``MigrationFile.cited_invariants`` scans the whole header comment and returns every
    occurrence, so a file that names ``MI22`` in its ``MI:`` line, again in its
    ``RATIONALE:`` and again in a ``source:`` cross-reference yields it three times. The
    manifest records the *set* a file serves, in the order a reader meets it — anything
    else would make the entry a histogram of how often a header repeats itself.
    """
    seen: dict[str, None] = {}
    for token in tokens:
        seen.setdefault(token, None)
    return tuple(seen)


def _entry(migration: MigrationFile, allocation: Allocation | None) -> LockEntry:
    key = key_of_filename(migration.path.name)
    if key is None:  # pragma: no cover - `discover` already refuses such a filename
        raise MigrationTreeInvalid(
            f"{migration.path.name} carries no NNNN[a-z]_ prefix, so it cannot be "
            "resolved against the allocation"
        )
    band = allocation.band_for(key) if allocation is not None else None
    header = parse_header(migration.sql)
    return LockEntry(
        file=migration.path.name,
        version=migration.version,
        number=f"{key[0]:04d}{key[1]}",
        mode=_mode_of(migration.sql),
        band=band.label if band is not None else None,
        owner=band.owner if band is not None else None,
        template=_template_of(migration.sql),
        invariants=_dedupe(migration.cited_invariants),
        sha256=migration.sha256.hex(),
        counsel_gated=header.counsel_gated,
    )


def build_lock(root: Path, *, repo_root: Path | None = None) -> dict[str, Any]:
    """Walk *root* and return the manifest as a JSON-ready mapping.

    *repo_root* only affects how the ``tree`` and ``allocation`` strings are written —
    relative to the repository when it is given, absolute otherwise — so that the
    committed file does not carry a developer's home directory.

    Raises:
        UsageError: when *root* holds no migrations. An empty manifest is
            indistinguishable from a manifest of an empty tree, and "the path was wrong"
            is by far the more likely of the two.
        MigrationTreeInvalid: propagated from ``discover`` — a duplicate version, a
            ``.down.sql``, or a filename the convention does not admit.
    """
    migrations = discover(root)
    if not migrations:
        raise UsageError(
            f"{root} holds no migration files. Refusing to write an empty manifest: an "
            "empty lock and a lock of an empty tree are the same bytes, and the first is "
            "almost always a mistyped path."
        )
    allocation = find_allocation(root)

    def _relative(path: Path) -> str:
        if repo_root is None:
            return str(path)
        try:
            return path.resolve().relative_to(repo_root.resolve()).as_posix()
        except ValueError:
            return str(path)

    entries = [_entry(migration, allocation) for migration in migrations]
    undeclared = sorted(e.file for e in entries if e.counsel_gated is None)

    generated_from = dict(_GENERATED_FROM)
    generated_from["allocation"] = _relative(allocation.source) if allocation is not None else None

    bands: list[dict[str, Any]] = []
    if allocation is not None:
        counts_by_band = {band.label: 0 for band in allocation.bands}
        for entry in entries:
            if entry.band is not None:
                counts_by_band[entry.band] += 1
        bands = [
            {
                "band": band.label,
                "owner": band.owner,
                "mode": band.mode,
                "files": counts_by_band[band.label],
            }
            for band in allocation.bands
        ]

    return {
        "$comment": _COMMENT,
        "schema_version": LOCK_SCHEMA_VERSION,
        "tree": _relative(root),
        "generated_from": generated_from,
        "counts": {
            "files": len(entries),
            "rendered": sum(1 for e in entries if e.mode == "rendered"),
            "authored": sum(1 for e in entries if e.mode == "authored"),
            "counsel_gated": sum(1 for e in entries if e.counsel_gated is True),
            "counsel_gated_undeclared": len(undeclared),
            "bands_occupied": sum(1 for band in bands if band["files"]),
        },
        "counsel_gated_undeclared": undeclared,
        "bands": bands,
        "migrations": [entry.as_json() for entry in entries],
    }


def render_lock(document: Mapping[str, Any]) -> str:
    """Serialise the manifest deterministically: 1-space indent, UTF-8, one trailing NL.

    Byte-stability matters more than prettiness here. ``verify_lock`` compares the
    committed file with a fresh render, and a serialiser whose output depended on a
    dictionary's iteration order would report drift on every regeneration.
    """
    return json.dumps(document, indent=1, ensure_ascii=False) + "\n"


def write_lock(path: Path, document: Mapping[str, Any]) -> None:
    """Write the manifest to *path* with LF endings, on every platform.

    ``newline=""`` is not incidental. This repository is authored on Windows and
    fingerprinted on Linux; a CRLF manifest would make ``--check`` fail on the runner for
    a file nobody edited.
    """
    path.write_text(render_lock(document), encoding="utf-8", newline="")


def _entry_index(document: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    raw = document.get("migrations")
    if not isinstance(raw, list):
        raise MigrationTreeInvalid(
            "the manifest carries no 'migrations' array; it is not a migration lock"
        )
    index: dict[str, dict[str, Any]] = {}
    for item in raw:
        if isinstance(item, dict) and isinstance(item.get("file"), str):
            index[str(item["file"])] = item
    return index


def _field_disagreements(
    filename: str, recorded: Mapping[str, Any], fresh: Mapping[str, Any]
) -> Iterable[str]:
    for field in ("version", "number", "mode", "band", "owner", "template", "sha256"):
        if recorded.get(field) != fresh.get(field):
            yield (
                f"{filename}: manifest says {field}={recorded.get(field)!r}, the tree "
                f"says {fresh.get(field)!r}"
            )
    if list(recorded.get("invariants") or []) != list(fresh.get("invariants") or []):
        yield (
            f"{filename}: manifest records invariants "
            f"{list(recorded.get('invariants') or [])}, the header cites "
            f"{list(fresh.get('invariants') or [])}"
        )
    if recorded.get("counsel_gated") != fresh.get("counsel_gated"):
        yield (
            f"{filename}: manifest records counsel_gated="
            f"{recorded.get('counsel_gated')!r}, the header says "
            f"{fresh.get('counsel_gated')!r}"
        )


def verify_lock(path: Path, root: Path, *, repo_root: Path | None = None) -> list[str]:
    """Compare the committed manifest at *path* with a fresh walk of *root*.

    Returns a list of findings, empty when the manifest is current. Findings rather than
    an exception, so that ``--check`` can print every disagreement at once: a manifest
    that is 156 files behind produces 156 sentences, and stopping at the first would make
    the operator regenerate-and-rerun 156 times to learn the same thing.

    The comparison is field-by-field rather than byte-by-byte on purpose. A byte compare
    would report "the file differs" for a change in the ``$comment`` prose, which is
    documentation of the generator and not a claim about the tree.
    """
    if not path.is_file():
        absent = (
            f"{path} does not exist. The manifest is a K1 deliverable: run "
            "`trappoint migrate lock --write`."
        )
        return [absent]

    try:
        committed: Any = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"{path} is not valid JSON: {exc}"]
    if not isinstance(committed, dict):
        return [f"{path} is not a JSON object"]

    fresh = build_lock(root, repo_root=repo_root)
    recorded_entries = _entry_index(committed)
    fresh_entries = _entry_index(fresh)

    findings: list[str] = []
    if committed.get("schema_version") != fresh["schema_version"]:
        findings.append(
            f"{path.name}: schema_version {committed.get('schema_version')!r} != "
            f"{fresh['schema_version']!r}"
        )

    for filename in sorted(set(fresh_entries) - set(recorded_entries)):
        findings.append(f"{filename} is on disk but absent from the manifest (stale lock)")
    for filename in sorted(set(recorded_entries) - set(fresh_entries)):
        findings.append(
            f"{filename} is in the manifest but not on disk — a migration was deleted or "
            "renamed, and a renamed migration is a new one"
        )
    for filename in sorted(set(recorded_entries) & set(fresh_entries)):
        findings.extend(
            _field_disagreements(filename, recorded_entries[filename], fresh_entries[filename])
        )

    if findings:
        findings.append(
            "regenerate with `trappoint migrate lock --write`; the manifest is derived, "
            "never authored (MR-6 lock 1)"
        )
    return findings


def counsel_gated_files(document: Mapping[str, Any]) -> Sequence[str]:
    """Return the files whose header declares ``COUNSEL-GATED: yes`` — DM-17's set.

    Exposed because "which files does the counsel answer move?" is a question the
    disposition domain and the submission both ask, and the answer should be a query
    against a manifest rather than a search of two hundred headers.
    """
    entries = _entry_index(document)
    return sorted(name for name, entry in entries.items() if entry.get("counsel_gated") is True)
