# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Loader for the hand-written corpus gazetteer.

Every literal the corpus generator writes down — asset tag, citation, control class, setpoint,
surname, document code — comes from this package and from nowhere else.  See ``README.md`` in
this directory for why that is a hard rule rather than a preference.

Design notes that are load-bearing:

* **A missing file raises.**  ``load("assets")`` on an absent ``assets.yaml`` is a
  ``GazetteerError``, never ``None`` and never ``{}``.  A gazetteer that silently returns empty
  turns every anchor-based refusal into a silent pass, which is the single worst failure mode
  available to this package.
* **Loads are cached and the cached object is deep-frozen.**  Callers get mappings and tuples,
  not lists, so a generator cannot mutate the vocabulary halfway through a run and produce two
  different corpora from one seed.
* **``yaml.safe_load`` only.**  Never ``load``; these files are data.
* **No import-time I/O.**  Reading happens on first ``load()``, so importing the package is
  cheap and a broken YAML file fails at the call site that needed it.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from functools import cache
from pathlib import Path
from typing import Any, Final

import yaml

__all__ = [
    "FILES",
    "GazetteerError",
    "as_mapping",
    "as_sequence",
    "checksum",
    "freeze",
    "load",
]

_HERE: Final[Path] = Path(__file__).resolve().parent

#: Every gazetteer file, in load order.  ``skeleton.build`` loads all of them so that a broken
#: file fails at the start of a run rather than nine seconds in.
FILES: Final[tuple[str, ...]] = (
    "anchors",
    "assets",
    "citations",
    "control_classes",
    "documents",
    "hazard_energies",
    "people",
    "phrases",
    "setpoints",
    "sites",
    "taxonomy",
)


class GazetteerError(RuntimeError):
    """A gazetteer file is missing, unparseable, or not the shape the caller needs."""


def _path(name: str) -> Path:
    return _HERE / f"{name}.yaml"


def freeze(value: Any) -> Any:
    """Recursively convert ``dict``/``list`` into immutable equivalents.

    Mappings become :class:`types.MappingProxyType`-like read-only ``dict`` copies wrapped by
    ``MappingProxyType``; sequences become tuples.  Scalars pass through.
    """
    from types import MappingProxyType

    if isinstance(value, dict):
        return MappingProxyType({key: freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(freeze(item) for item in value)
    return value


@cache
def load(name: str) -> Mapping[str, Any]:
    """Return the parsed, frozen contents of ``<name>.yaml``.

    Raises :class:`GazetteerError` if the file is absent, is not a mapping, or omits the
    ``version`` key every gazetteer file is required to carry.
    """
    path = _path(name)
    if not path.is_file():
        raise GazetteerError(
            f"gazetteer file {path.name!r} is missing from {_HERE}. "
            "The corpus generator refuses to run against an incomplete vocabulary: an empty "
            "gazetteer produces a corpus with no anchors, which passes every test while "
            "testing nothing."
        )
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:  # pragma: no cover - exercised only on a malformed edit
        raise GazetteerError(f"gazetteer file {path.name!r} is not valid YAML: {exc}") from exc
    if not isinstance(raw, dict):
        raise GazetteerError(
            f"gazetteer file {path.name!r} must contain a mapping at the top level, "
            f"got {type(raw).__name__}"
        )
    if "version" not in raw:
        raise GazetteerError(f"gazetteer file {path.name!r} has no `version` key")
    frozen = freeze(raw)
    assert isinstance(frozen, Mapping)
    return frozen


def as_mapping(source: Mapping[str, Any], key: str, *, origin: str) -> Mapping[str, Any]:
    """Fetch ``source[key]`` and require it to be a mapping."""
    try:
        value = source[key]
    except KeyError as exc:
        raise GazetteerError(f"{origin}: required key {key!r} is missing") from exc
    if not isinstance(value, Mapping):
        raise GazetteerError(f"{origin}: key {key!r} must be a mapping, got {type(value).__name__}")
    return value


def as_sequence(source: Mapping[str, Any], key: str, *, origin: str) -> Sequence[Any]:
    """Fetch ``source[key]`` and require it to be a non-empty sequence.

    Empty is an error on purpose.  Every one of these lists is drawn from; an empty one means a
    generator would either crash far downstream or, worse, quietly emit nothing.
    """
    try:
        value = source[key]
    except KeyError as exc:
        raise GazetteerError(f"{origin}: required key {key!r} is missing") from exc
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise GazetteerError(f"{origin}: key {key!r} must be a sequence, got {type(value).__name__}")
    if len(value) == 0:
        raise GazetteerError(f"{origin}: key {key!r} is empty; the corpus cannot draw from it")
    return value


def iter_files() -> Iterator[tuple[str, Path]]:
    """Yield ``(name, path)`` for every declared gazetteer file, in load order."""
    for name in FILES:
        yield name, _path(name)


def checksum() -> str:
    """SHA-256 over every gazetteer file, in ``FILES`` order.

    This is what ties a generated corpus to the exact vocabulary that produced it.  It is
    recorded in the skeleton's ``index.json`` and is a lock input for ``corpus-freeze-load``:
    if the vocabulary changes, the corpus digest must change, and a build that claims otherwise
    is lying about its provenance.
    """
    import hashlib

    digest = hashlib.sha256()
    for name, path in iter_files():
        if not path.is_file():
            raise GazetteerError(f"gazetteer file {name!r} is missing; cannot checksum")
        digest.update(name.encode("utf-8"))
        digest.update(b"\x00")
        digest.update(path.read_bytes())
        digest.update(b"\x00")
    return digest.hexdigest()
