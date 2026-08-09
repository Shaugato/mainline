# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Bind the declared catalogue to the implemented operators, and refuse a mismatch.

Two failure modes this module exists to make impossible:

* **A declared class with no operator.**  It would be counted as zero trials,
  which under :func:`~mainline_mutation.wilson.wilson_interval` returns a lower
  bound of ``0.0`` and drags the published aggregate down.  A number that fell
  because of a wiring bug is worse than a number that fell because of a defect,
  because only one of them is actionable.
* **An operator with no declaration.**  Its trials would appear in the artefact
  under a class no reader was told about, with no ``rationale`` and no
  ``expected`` sentence to weigh them against.

``operator_fingerprint()`` digests the SOURCE TEXT of every registered operator.
That is what makes "traceable to the code that produced it" literally true: an
operator edited without a ``HARNESS_VERSION`` bump still moves the fingerprint,
and the fingerprint is on every published number and every SQL row.
"""

from __future__ import annotations

import hashlib
import inspect
from functools import lru_cache
from typing import Any, Final

from .errors import CatalogueError
from .model import KILL, SURVIVE, MutationClass, MutationKind, Operator
from .operators import KILL_OPERATORS, SURVIVE_OPERATORS
from .resources import load_catalogue_toml

__all__ = [
    "OPERATOR_DOMAIN",
    "class_by_id",
    "confidence",
    "load_catalogue",
    "operator_fingerprint",
    "operator_for",
    "operators",
]

#: Domain separator for :func:`operator_fingerprint`.
OPERATOR_DOMAIN: Final[bytes] = b"mainline/mutation/operators/v1\n"

_KINDS: Final[tuple[MutationKind, ...]] = (KILL, SURVIVE)


def operators() -> dict[str, Operator]:
    """Every registered operator, keyed by ``class_id``.

    A fresh dict on every call so that a caller cannot mutate the registry the
    fingerprint was computed over.
    """
    return {**KILL_OPERATORS, **SURVIVE_OPERATORS}


def _one(entry: dict[str, Any]) -> MutationClass:
    kind = str(entry.get("kind", ""))
    if kind not in _KINDS:
        raise CatalogueError(
            f"class {entry.get('class_id', '<unnamed>')!r} declares kind {kind!r}; the only "
            f"kinds are {list(_KINDS)}, and they are two different products (decision D13)"
        )
    for key in ("class_id", "title", "rationale", "expected"):
        if not str(entry.get(key, "")).strip():
            raise CatalogueError(
                f"class {entry.get('class_id', '<unnamed>')!r} has an empty {key!r}. Every "
                "field here is printed into the published artefact; an empty one is a number "
                "with no sentence beside it"
            )
    return MutationClass(
        class_id=str(entry["class_id"]),
        kind=kind,
        title=str(entry["title"]),
        rationale=str(entry["rationale"]),
        expected=str(entry["expected"]),
        magnitude=None if entry.get("magnitude") is None else str(entry["magnitude"]),
        applies_when_ratified=bool(entry.get("applies_when_ratified", False)),
    )


@lru_cache(maxsize=1)
def load_catalogue() -> tuple[MutationClass, ...]:
    """The declared catalogue, validated against the implemented operators."""
    parsed = load_catalogue_toml()
    entries = parsed.get("class", [])
    if not entries:
        raise CatalogueError("catalogue-v1.toml declares no [[class]] entries")

    declared = tuple(_one(entry) for entry in entries)
    ids = [c.class_id for c in declared]
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    if duplicates:
        raise CatalogueError(f"catalogue-v1.toml declares {duplicates} more than once")

    implemented = operators()
    missing_operator = sorted(set(ids) - set(implemented))
    if missing_operator:
        raise CatalogueError(
            f"{missing_operator} are declared in catalogue-v1.toml with no operator. A declared "
            "class with no operator contributes zero trials, whose Wilson lower bound is 0.0, "
            "and the published aggregate would fall for a wiring bug"
        )
    undeclared = sorted(set(implemented) - set(ids))
    if undeclared:
        raise CatalogueError(
            f"{undeclared} are implemented with no declaration in catalogue-v1.toml. Their "
            "trials would appear in the artefact under a class no reader was told about"
        )

    for mutation_class in declared:
        registry = KILL_OPERATORS if mutation_class.kind == KILL else SURVIVE_OPERATORS
        if mutation_class.class_id not in registry:
            raise CatalogueError(
                f"{mutation_class.class_id!r} is declared {mutation_class.kind} but its operator "
                f"is registered in the other catalogue. The two catalogues are judged by "
                "opposite rules and a class in the wrong one would be scored backwards"
            )
    return declared


@lru_cache(maxsize=1)
def _index() -> dict[str, MutationClass]:
    return {c.class_id: c for c in load_catalogue()}


def class_by_id(class_id: str) -> MutationClass:
    """One declared class, or a refusal naming the catalogue."""
    found = _index().get(class_id)
    if found is None:
        raise CatalogueError(f"no catalogue class {class_id!r}; declared: {sorted(_index())}")
    return found


def operator_for(class_id: str) -> Operator:
    """The operator bound to one class.  :func:`load_catalogue` has already paired them."""
    load_catalogue()
    return operators()[class_id]


@lru_cache(maxsize=1)
def operator_fingerprint() -> str:
    """Digest the source text of every registered operator, in ``class_id`` order.

    ``inspect.getsource`` rather than a hash of the module file: a module carries
    tables, helpers and a docstring, and a fingerprint that moved when a comment
    changed would be a fingerprint nobody trusted.  Sorted by ``class_id`` so the
    digest is a function of the code and not of dict insertion order.
    """
    parts = [OPERATOR_DOMAIN]
    for class_id, operator in sorted(operators().items()):
        source = inspect.getsource(operator).encode("utf-8")
        parts.append(f"class={class_id}\n".encode())
        parts.append(len(source).to_bytes(4, "big"))
        parts.append(source)
    return hashlib.sha256(b"".join(parts)).hexdigest()


def confidence() -> str:
    """The confidence level ``[meta].confidence`` declares, e.g. ``'0.95'``."""
    meta = load_catalogue_toml().get("meta", {})
    return str(meta.get("confidence", "0.95"))
