# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Reading ``spec/conformance/manifest.toml``.

The manifest is the single source of truth for the suite, and this module is a reader,
not an interpreter. Where the manifest disagrees with prose anywhere in ``spec/``, the
manifest wins — that is stated in the file's own header — so nothing here defaults,
infers or repairs a field. A case missing ``expect_constraint`` is a broken manifest and
is reported as one.

The one thing this module does add is the ``requires`` contract: a case whose capability
token is not satisfied **skips with a printed reason**. A skipped case is never a passed
case, and a suite that skips silently is a suite that passes by absence.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

__all__ = ["Case", "Manifest", "find_manifest", "load_manifest"]

_REQUIRED_FIELDS = (
    "id",
    "title",
    "class",
    "invariants",
    "mi",
    "anomaly",
    "expect_sqlstate",
    "expect_constraint",
    "profiles",
    "refusal_depth_min",
    "milestone",
)


class ManifestError(Exception):
    """The manifest is unreadable or a case is missing a required field."""


@dataclass(frozen=True, slots=True)
class Case:
    """One conformance case: a history plus an exact expectation about the last write."""

    id: str
    title: str
    cls: str
    invariants: tuple[str, ...]
    mi: tuple[str, ...]
    anomaly: str
    expect_sqlstate: str
    expect_constraint: str
    profiles: tuple[str, ...]
    refusal_depth_min: int
    milestone: str
    requires: tuple[str, ...] = ()
    secondary_sqlstate: str | None = None
    secondary_constraint: str | None = None
    payload_schema: str | None = None
    asserts_payload: bool = False
    asserts_stored_row: str | None = None
    note: str = ""
    retired: bool = False

    def runs_in(self, profile: str) -> bool:
        """Whether this case is selected for *profile*."""
        return profile in self.profiles and not self.retired


@dataclass(frozen=True, slots=True)
class Manifest:
    """The parsed manifest."""

    path: Path
    spec_version: str
    profiles: tuple[str, ...]
    gate_taxonomy: tuple[str, ...]
    cases: tuple[Case, ...]
    declared_case_count: int
    declared_ref_profile_case_count: int
    meta: dict[str, object] = field(default_factory=dict)

    def for_profile(self, profile: str) -> tuple[Case, ...]:
        """Cases selected for *profile*, in manifest order."""
        return tuple(c for c in self.cases if c.runs_in(profile))

    def by_id(self, case_id: str) -> Case | None:
        """Look up a case by id."""
        return next((c for c in self.cases if c.id == case_id), None)


def find_manifest(start: Path | None = None) -> Path:
    """Locate ``spec/conformance/manifest.toml`` by walking up from *start*.

    Raises:
        ManifestError: when no ancestor carries one. The runner never falls back to a
            bundled copy: a conformance claim is made against the specification in the
            tree being tested, not against whatever the tool shipped with.
    """
    here = (start or Path.cwd()).resolve()
    for candidate in (here, *here.parents):
        manifest = candidate / "spec" / "conformance" / "manifest.toml"
        if manifest.is_file():
            return manifest
    raise ManifestError(
        f"no spec/conformance/manifest.toml above {here}. The runner asserts the "
        "specification in the tree it is run from; it ships no copy of its own."
    )


def _as_str_tuple(value: object, *, case_id: str, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ManifestError(f"{case_id}: {field_name} must be an array")
    return tuple(str(v) for v in value)


def _as_int(value: object, *, case_id: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ManifestError(f"{case_id}: refusal_depth_min must be an integer")
    return value


def _case_from(raw: dict[str, object]) -> Case:
    case_id = str(raw.get("id", "<no id>"))
    missing = [f for f in _REQUIRED_FIELDS if f not in raw]
    if missing:
        raise ManifestError(f"{case_id}: missing required field(s) {', '.join(missing)}")

    expect_constraint = str(raw["expect_constraint"])
    if not expect_constraint:
        raise ManifestError(
            f"{case_id}: expect_constraint is empty. A test asserting only a SQLSTATE is "
            "not conformant — 'an exception was raised' is worthless in a product whose "
            "deliverable is the diagnosis (spec/errors.md §3.1)."
        )

    asserts_stored = raw.get("asserts_stored_row")
    return Case(
        id=case_id,
        title=str(raw["title"]),
        cls=str(raw["class"]),
        invariants=_as_str_tuple(raw["invariants"], case_id=case_id, field_name="invariants"),
        mi=_as_str_tuple(raw["mi"], case_id=case_id, field_name="mi"),
        anomaly=str(raw["anomaly"]),
        expect_sqlstate=str(raw["expect_sqlstate"]),
        expect_constraint=expect_constraint,
        profiles=_as_str_tuple(raw["profiles"], case_id=case_id, field_name="profiles"),
        refusal_depth_min=_as_int(raw["refusal_depth_min"], case_id=case_id),
        milestone=str(raw["milestone"]),
        requires=(
            _as_str_tuple(raw["requires"], case_id=case_id, field_name="requires")
            if "requires" in raw
            else ()
        ),
        secondary_sqlstate=(
            str(raw["secondary_sqlstate"]) if raw.get("secondary_sqlstate") else None
        ),
        secondary_constraint=(
            str(raw["secondary_constraint"]) if raw.get("secondary_constraint") else None
        ),
        payload_schema=str(raw["payload_schema"]) if raw.get("payload_schema") else None,
        asserts_payload=bool(raw.get("asserts_payload", False)),
        asserts_stored_row=None if asserts_stored is None else str(asserts_stored),
        note=str(raw.get("note", "")),
        retired=bool(raw.get("retired", False)),
    )


def load_manifest(path: Path | None = None) -> Manifest:
    """Parse the manifest at *path*, or the nearest one above the working directory."""
    manifest_path = path or find_manifest()
    with manifest_path.open("rb") as handle:
        document = tomllib.load(handle)

    meta = document.get("manifest", {})
    if not isinstance(meta, dict):
        raise ManifestError(f"{manifest_path}: [manifest] must be a table")

    raw_cases = document.get("case", [])
    if not isinstance(raw_cases, list) or not raw_cases:
        raise ManifestError(f"{manifest_path}: no [[case]] entries")

    cases = tuple(_case_from(dict(raw)) for raw in raw_cases)

    seen: set[str] = set()
    for case in cases:
        if case.id in seen:
            raise ManifestError(f"duplicate case id {case.id!r}")
        seen.add(case.id)

    return Manifest(
        path=manifest_path,
        spec_version=str(meta.get("spec_version", "unknown")),
        profiles=tuple(str(p) for p in meta.get("profiles", [])),
        gate_taxonomy=tuple(str(c) for c in meta.get("gate_taxonomy", [])),
        cases=cases,
        declared_case_count=int(meta.get("case_count", len(cases))),
        declared_ref_profile_case_count=int(meta.get("ref_profile_case_count", 0)),
        meta=dict(meta),
    )
