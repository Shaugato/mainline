# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Load the historical fixture revisions, and refuse a malformed one.

The loader validates rather than trusts, for the same reason every projection
in this system is enforced rather than trusted (P2): a fixture whose recorded
``parameter`` silently stopped matching what the extractor produces would move
every setpoint mutant into the *inapplicable* bucket, and inapplicable mutants
do not appear in the denominator.  The published kill rate would rise because
its hardest trials quietly left, and nothing would look wrong.

That specific check needs the extractor and therefore lives in
``tests/e2e/mutation/test_fixtures.py`` rather than here — the loader must not
import the CAT extractor, because the fixture list is also read by the report
renderer and by the SQL writer, neither of which should drag a lexicon in.
What is checked *here* is everything checkable from the file alone.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from .errors import FixtureError
from .model import Revision
from .resources import load_fixtures_toml

__all__ = ["families", "fixture_by_id", "load_fixtures"]

_REQUIRED: tuple[str, ...] = (
    "fixture_id",
    "family",
    "title",
    "numbering_prefix",
    "furniture_lines",
    "raw_text",
    "parameter",
    "directrix_ratified",
    "setpoint_token",
    "setpoint_value",
    "setpoint_unit",
)


def _one(entry: dict[str, Any], declared_families: frozenset[str]) -> Revision:
    missing = [key for key in _REQUIRED if key not in entry]
    if missing:
        raise FixtureError(
            f"fixture {entry.get('fixture_id', '<unnamed>')!r} is missing {missing}; every "
            "fixture declares all eleven fields so that a reader of the artefact can "
            "reconstruct the ancestor exactly"
        )
    family = str(entry["family"])
    if family not in declared_families:
        raise FixtureError(
            f"fixture {entry['fixture_id']!r} declares family {family!r}, which is not in "
            f"[meta].families {sorted(declared_families)}. The family is the breakdown axis of "
            "the published metric; an undeclared one would appear in the artefact as a "
            "category no reader was told about"
        )
    if not str(entry["raw_text"]).strip():
        raise FixtureError(f"fixture {entry['fixture_id']!r} has empty raw_text")
    return Revision(
        fixture_id=str(entry["fixture_id"]),
        family=family,
        title=str(entry["title"]),
        raw_text=str(entry["raw_text"]),
        numbering_prefix=str(entry["numbering_prefix"]),
        furniture_lines=tuple(str(line) for line in entry["furniture_lines"]),
        parameter=str(entry["parameter"]),
        directrix_ratified=bool(entry["directrix_ratified"]),
        setpoint_token=str(entry["setpoint_token"]),
        setpoint_value=str(entry["setpoint_value"]),
        setpoint_unit=str(entry["setpoint_unit"]),
    )


@lru_cache(maxsize=1)
def load_fixtures() -> tuple[Revision, ...]:
    """Every fixture revision, in file order.

    File order, never sorted: the runner enumerates fixtures in this order and a
    ``mutant_id`` is a function of the fixture id rather than of its position,
    so the order affects only which row appears first in a report.  Keeping it
    the file's order means a reader comparing the artefact against the TOML
    reads down both at the same rate.
    """
    parsed = load_fixtures_toml()
    meta = parsed.get("meta", {})
    declared = frozenset(str(f) for f in meta.get("families", ()))
    if not declared:
        raise FixtureError("fixtures-v1.toml declares no [meta].families")
    entries = parsed.get("fixture", [])
    if not entries:
        raise FixtureError("fixtures-v1.toml declares no [[fixture]] entries")

    out = tuple(_one(entry, declared) for entry in entries)
    seen: set[str] = set()
    for revision in out:
        if revision.fixture_id in seen:
            raise FixtureError(
                f"duplicate fixture_id {revision.fixture_id!r}; mutant ids are derived from it "
                "and a duplicate would make two different mutants share one identity"
            )
        seen.add(revision.fixture_id)
    return out


@lru_cache(maxsize=1)
def _index() -> dict[str, Revision]:
    return {revision.fixture_id: revision for revision in load_fixtures()}


def fixture_by_id(fixture_id: str) -> Revision:
    """Return one fixture, or raise :class:`~mainline_mutation.errors.FixtureError`."""
    revision = _index().get(fixture_id)
    if revision is None:
        raise FixtureError(f"no fixture {fixture_id!r}; the fixture set is {sorted(_index())}")
    return revision


def families() -> tuple[str, ...]:
    """The declared document families, sorted, as the metric breaks the number down."""
    return tuple(sorted({revision.family for revision in load_fixtures()}))
