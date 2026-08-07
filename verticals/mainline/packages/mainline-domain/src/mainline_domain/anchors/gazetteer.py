# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Loader for the committed ANCHORLOCK gazetteers.

Five TOML files under ``mainline_domain/data/gazetteer/``, loaded once, cached,
never fetched.  A gazetteer that can change between runs makes anchor drop
unfalsifiable — the whole point of a hard anchor is that it needs no model, no
threshold and no drift, and a mutable word list is drift by another name.

Every loader here is strict: a malformed file raises at import of the extractor
rather than degrading to an empty set.  An empty gazetteer would silently turn
every anchor-based refusal into a pass.

**Versioned, and fingerprinted.**  Each file declares an integer ``version`` and
the loader *reads* it — a declared version nothing reads is decoration.  The six
files' ``(name, version, sha256(bytes))`` triples are folded into one 32-byte
:func:`gazetteer_fingerprint`, which is what a downstream row stamps to record
*which word lists decided this anchor set*.  This is ANCHORLOCK's analogue of
``canon_version`` being bound into the CANONHOLD digest preimage: without it a
gazetteer could be edited with no version bump, no digest change and no trace,
and the set of things that count as an anchor would depend on which checkout ran
the extractor — which makes anchor drop unfalsifiable.

The fingerprint covers the **bytes of the committed files**, not the parsed
entries, so a comment-only edit moves it.  That is deliberate: the question the
fingerprint answers is "which bytes were in the tree", because those bytes are
what an opposing expert would be handed.
"""

from __future__ import annotations

import hashlib
import tomllib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Final

from ..data import data_file

__all__ = [
    "GAZETTEER_FINGERPRINT_DOMAIN",
    "Gazetteers",
    "gazetteer_fingerprint",
    "load_gazetteers",
    "require_version",
]

GAZETTEER_FINGERPRINT_DOMAIN: Final[bytes] = b"mainline/anchors/gazetteer/v1"
"""Domain-separation prefix for :func:`gazetteer_fingerprint`."""

_EQUIPMENT: Final[tuple[str, ...]] = ("gazetteer", "equipment.toml")
_INSTRUMENT: Final[tuple[str, ...]] = ("gazetteer", "instrument.toml")
_ISOLATION: Final[tuple[str, ...]] = ("gazetteer", "isolation.toml")
_CITATIONS: Final[tuple[str, ...]] = ("gazetteer", "citations.toml")
_ROLES: Final[tuple[str, ...]] = ("gazetteer", "roles.toml")
_SETPOINTS: Final[tuple[str, ...]] = ("gazetteer", "setpoint-units.toml")

# Subdivision tokens collapse to a coarse kind.  'WHS Reg r.62' and
# 'WHS Regulation 62' are one citation; 'WHS s.62' (a section of the Act) is
# not, so the distinction survives while the spelling does not.
_SUBDIVISION_KIND: Final[dict[str, str]] = {
    "reg": "REG",
    "regs": "REG",
    "regulation": "REG",
    "regulations": "REG",
    "r": "REG",
    "rr": "REG",
    "cl": "CL",
    "clause": "CL",
    "s": "S",
    "sec": "S",
    "section": "S",
    "sch": "SCH",
    "schedule": "SCH",
    "part": "PART",
    "div": "DIV",
}


def require_version(section: Mapping[str, object], source: str) -> int:
    """Return the declared ``version`` of one gazetteer table, or raise.

    Strict on purpose.  A default would let a file that declares no version load
    cleanly, and the whole point of the version is that editing a word list is a
    deliberate, recorded act.  ``bool`` is rejected explicitly because
    ``isinstance(True, int)`` is ``True`` in Python and ``version = true`` must
    not silently mean version 1.
    """
    version = section.get("version")
    if isinstance(version, bool) or not isinstance(version, int):
        raise TypeError(f"{source}: [version] must be an integer, got {version!r}")
    if version < 1:
        raise ValueError(f"{source}: [version] must be >= 1, got {version}")
    return version


def gazetteer_fingerprint(entries: Iterable[tuple[str, int, bytes]]) -> bytes:
    """Fold ``(file name, version, sha256 of the file's bytes)`` into 32 bytes.

    Order-independent (entries are sorted) and unambiguous (every field is
    length-prefixed, so no renaming of files can produce a colliding preimage).
    Reproducible by hand: ``sha256sum`` each gazetteer, read each ``version``,
    sort by name, and concatenate.
    """
    hasher = hashlib.sha256(GAZETTEER_FINGERPRINT_DOMAIN)
    for name, version, digest in sorted(entries):
        for field in (name.encode("utf-8"), str(version).encode("ascii"), digest):
            hasher.update(len(field).to_bytes(4, "big"))
            hasher.update(field)
    return hasher.digest()


def _table(path: Path, name: str) -> dict[str, object]:
    with path.open("rb") as handle:
        document = tomllib.load(handle)
    section = document.get(name)
    if not isinstance(section, dict):
        raise TypeError(f"{path.name}: missing [{name}] table")
    return section


def _stamp(path: Path, section: Mapping[str, object]) -> tuple[str, int, bytes]:
    """``(file name, declared version, sha256 of the file's bytes)``."""
    return path.name, require_version(section, path.name), hashlib.sha256(path.read_bytes()).digest()


def _strings(section: dict[str, object], key: str, path: Path) -> tuple[str, ...]:
    raw = section.get(key)
    if not isinstance(raw, list):
        raise TypeError(f"{path.name}: [{key}] must be an array of strings")
    out: list[str] = []
    for item in raw:
        if not isinstance(item, str) or not item:
            raise TypeError(f"{path.name}: {key} contains a non-string or empty entry")
        out.append(item)
    if not out:
        raise ValueError(f"{path.name}: {key} is empty; an empty gazetteer disables a refusal")
    return tuple(out)


def _longest_first(values: tuple[str, ...]) -> tuple[str, ...]:
    """Alternation order.  Without this, ``AS`` shadows ``AS/NZS``."""
    return tuple(sorted(set(values), key=lambda v: (-len(v), v)))


@dataclass(frozen=True, slots=True)
class Gazetteers:
    """Every committed word list the extractor needs, already ordered."""

    equipment_codes: frozenset[str]
    instrument_codes: frozenset[str]
    isolation_prefixes: tuple[str, ...]
    citation_bodies: tuple[str, ...]
    citation_regulations: tuple[str, ...]
    subdivision_kinds: dict[str, str]
    role_variants: tuple[tuple[str, str], ...]
    setpoint_units: tuple[str, ...]
    setpoint_qualifiers: tuple[str, ...]

    versions: tuple[tuple[str, int], ...]
    """``(file name, declared version)`` for every gazetteer, sorted by name."""

    fingerprint: bytes
    """32 bytes identifying *exactly* these word lists — see the module docstring.

    A row that records an anchor decision should carry this next to the
    ``identity_policy`` hash decision D11 already puts there, so that
    "which gazetteer said that was a tag" is answerable years later.
    """


@lru_cache(maxsize=1)
def load_gazetteers() -> Gazetteers:
    """Load and cache all six gazetteers, with their versions and fingerprint."""
    equipment_path = data_file(*_EQUIPMENT)
    instrument_path = data_file(*_INSTRUMENT)
    isolation_path = data_file(*_ISOLATION)
    citations_path = data_file(*_CITATIONS)
    roles_path = data_file(*_ROLES)
    setpoints_path = data_file(*_SETPOINTS)

    equipment = _table(equipment_path, "equipment")
    instrument = _table(instrument_path, "instrument")
    isolation = _table(isolation_path, "isolation")
    citations = _table(citations_path, "citations")
    setpoints = _table(setpoints_path, "setpoints")

    with roles_path.open("rb") as handle:
        roles_doc = tomllib.load(handle)
    roles_meta = roles_doc.get("roles")
    if not isinstance(roles_meta, dict):
        raise TypeError("roles.toml: missing [roles] table")
    role_entries = roles_doc.get("role")
    if not isinstance(role_entries, list) or not role_entries:
        raise TypeError("roles.toml: missing or empty [[role]] array")

    # Every gazetteer's identity, computed before any of it is used.  A file
    # that declares no version never reaches the extractor.
    stamps = (
        _stamp(equipment_path, equipment),
        _stamp(instrument_path, instrument),
        _stamp(isolation_path, isolation),
        _stamp(citations_path, citations),
        _stamp(roles_path, roles_meta),
        _stamp(setpoints_path, setpoints),
    )

    variants: list[tuple[str, str]] = []
    for entry in role_entries:
        if not isinstance(entry, dict):
            raise TypeError("roles.toml: [[role]] entries must be tables")
        norm = entry.get("norm")
        raw_variants = entry.get("variants")
        if not isinstance(norm, str) or not norm:
            raise TypeError("roles.toml: every [[role]] needs a non-empty norm")
        if not isinstance(raw_variants, list) or not raw_variants:
            raise TypeError(f"roles.toml: role {norm} has no variants")
        for variant in raw_variants:
            if not isinstance(variant, str) or not variant:
                raise TypeError(f"roles.toml: role {norm} has an empty variant")
            variants.append((variant.casefold(), norm))
    variants.sort(key=lambda pair: (-len(pair[0]), pair[0]))

    subdivisions = _strings(citations, "subdivision_tokens", citations_path)
    unknown = [token for token in subdivisions if token.casefold() not in _SUBDIVISION_KIND]
    if unknown:
        raise ValueError(f"citations.toml: subdivision tokens with no kind mapping: {unknown}")

    return Gazetteers(
        equipment_codes=frozenset(_strings(equipment, "codes", equipment_path)),
        instrument_codes=frozenset(_strings(instrument, "codes", instrument_path)),
        isolation_prefixes=_longest_first(_strings(isolation, "prefixes", isolation_path)),
        citation_bodies=_longest_first(_strings(citations, "bodies", citations_path)),
        citation_regulations=_longest_first(_strings(citations, "regulations", citations_path)),
        subdivision_kinds=dict(_SUBDIVISION_KIND),
        role_variants=tuple(variants),
        setpoint_units=_longest_first(_strings(setpoints, "units", setpoints_path)),
        setpoint_qualifiers=_longest_first(_strings(setpoints, "qualifiers", setpoints_path)),
        versions=tuple(sorted((name, version) for name, version, _ in stamps)),
        fingerprint=gazetteer_fingerprint(stamps),
    )
