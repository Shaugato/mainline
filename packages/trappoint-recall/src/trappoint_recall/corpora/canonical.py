# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Deterministic canonical JSON and digests, for artefacts that are compared by hash.

The panel digest and the config digest on a THYMOGATE certificate are only meaningful if
two people serialising the same object get the same bytes. RFC 8785 (JCS) defines that,
and the custody domain implements the full canonicaliser for the ledger.

This module deliberately does **not** reimplement JCS. It implements the strict subset
JCS and ``json.dumps(sort_keys=True, separators=(',', ':'), ensure_ascii=False)`` agree
on — objects, arrays, strings, booleans, null and **integers** — and it *refuses* the
one value class where they can diverge:

    floats.

JCS pins number formatting to ECMAScript ``Number::toString``; Python's ``repr`` agrees
for every value we would plausibly emit, but "plausibly" is not a property you want
under a digest that a certificate depends on. Refusing floats makes the agreement a
theorem rather than an observation, and costs nothing: every field under these digests
is an identifier, a count or an enum.

*Unverified:* this module has not been differentially tested against the custody
domain's JCS canonicaliser. It does not need to be — the two digests cover different
artefacts — but if they are ever compared, that test must exist first.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Mapping, Sequence
from typing import Final

__all__ = [
    "CANONICAL_NAMESPACE",
    "CanonicalisationRefused",
    "canonical_bytes",
    "canonical_json",
    "deterministic_uuid",
    "digest_hex",
]

CANONICAL_NAMESPACE: Final = uuid.UUID("6f0a4b2e-9c31-5d7a-8b64-1f2e3d4c5b6a")
"""Fixed namespace for :func:`deterministic_uuid`. Changing it renames every artefact."""


class CanonicalisationRefused(TypeError):
    """Raised when a value cannot be canonicalised without ambiguity."""


def _check(value: object, *, path: str) -> object:
    if value is None or isinstance(value, str):
        return value
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        raise CanonicalisationRefused(
            f"{path}: a float under a digest is refused. RFC 8785 pins number formatting "
            "and this module does not implement that pinning, so a float here would make "
            "the digest depend on a formatting rule nobody checked. Quantise it to an "
            "integer first — the recall domain already does this for scores "
            "(score_q = round(p x 10**6), lead decision D10)."
        )
    if isinstance(value, Mapping):
        out: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise CanonicalisationRefused(
                    f"{path}: object keys must be strings, got {type(key).__name__}"
                )
            out[key] = _check(item, path=f"{path}.{key}")
        return out
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_check(item, path=f"{path}[{i}]") for i, item in enumerate(value)]
    raise CanonicalisationRefused(
        f"{path}: {type(value).__name__} is not canonicalisable. Convert it to a string, "
        "an int, a bool, a list or a dict at the point where the conversion is reviewable."
    )


def canonical_json(value: object) -> str:
    """Canonical JSON text: sorted keys, no insignificant whitespace, no float."""
    return json.dumps(
        _check(value, path="$"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def canonical_bytes(value: object) -> bytes:
    """UTF-8 bytes of :func:`canonical_json`. This is what gets hashed."""
    return canonical_json(value).encode("utf-8")


def digest_hex(value: object) -> str:
    """Hex sha256 over the canonical bytes of ``value``."""
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def deterministic_uuid(*parts: str) -> uuid.UUID:
    """A UUIDv5 over ``parts``, so a rebuilt artefact keeps its identity.

    Random ids would make every rebuild a diff, and a gold set whose ids churn cannot be
    compared across two runs of the build.
    """
    return uuid.uuid5(CANONICAL_NAMESPACE, "\x1f".join(parts))
