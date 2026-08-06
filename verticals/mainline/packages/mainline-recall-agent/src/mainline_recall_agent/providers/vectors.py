# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""Vector arithmetic: normalisation, Matryoshka truncation, and the wire encoding.

Every vector this package emits is L2-unit.  ``vector_cosine_ops`` in CockroachDB does not
require it, but a unit corpus makes cosine and inner product the same number, which is the
difference between a fusion stage that can be recomputed from stored features and one that
cannot (ARCHITECTURE §8.2: *the model proposes; the arithmetic decides; both are on the
record*).
"""

from __future__ import annotations

import base64
import math
from collections.abc import Sequence

import numpy as np

from .errors import VectorShapeError
from .types import COARSE_DIM, EMBED_DIM, Vector256

__all__ = [
    "b64_to_vector",
    "check_dim",
    "is_unit",
    "l2_normalise",
    "matryoshka_coarse",
    "to_float32",
    "vector_to_b64",
]

#: float32 is what ``VECTOR(n)`` stores in CockroachDB, so a "unit" vector that has made a
#: round trip through the database is unit to about 1e-7, not to 1e-15.  Tests and
#: assertions use this tolerance rather than pretending to float64 exactness.
UNIT_TOLERANCE: float = 1e-6


def check_dim(vec: Sequence[float], expected: int) -> None:
    if len(vec) != expected:
        raise VectorShapeError(
            "wrong vector width", expected=expected, actual=len(vec)
        )
    for i, component in enumerate(vec):
        if not math.isfinite(component):
            raise VectorShapeError("non-finite vector component", index=i, value=component)


def l2_normalise(vec: Sequence[float]) -> tuple[float, ...]:
    """Return ``vec / ||vec||``.

    A zero vector is refused rather than passed through: it has no direction, every cosine
    against it is undefined, and in an ANN index it is a point that matches nothing while
    still occupying a leaf.
    """
    norm = math.sqrt(math.fsum(float(c) * float(c) for c in vec))
    if norm == 0.0 or not math.isfinite(norm):
        raise VectorShapeError("cannot normalise a zero or non-finite vector", norm=norm)
    return tuple(float(c) / norm for c in vec)


def is_unit(vec: Sequence[float], tolerance: float = UNIT_TOLERANCE) -> bool:
    norm = math.sqrt(math.fsum(float(c) * float(c) for c in vec))
    return abs(norm - 1.0) <= tolerance


def matryoshka_coarse(vec: Sequence[float], out_dim: int = COARSE_DIM) -> Vector256:
    """Truncate to ``out_dim`` and renormalise **client-side**.

    Valid only for a Matryoshka-trained (MRL) space.  Titan v2 is MRL-trained and
    documents 256/512/1024 as selectable widths; truncating a non-MRL space (bge-large,
    for instance) produces a vector whose neighbours are not the full vector's neighbours,
    which is why ``LocalBGE`` uses a committed projection instead (recall.md D4).

    Renormalisation is client-side because the prefix of a unit vector is not a unit
    vector, and ``event_cue_coarse`` is compared with ``vector_cosine_ops``.
    """
    check_dim(vec, EMBED_DIM)
    if out_dim <= 0 or out_dim > EMBED_DIM:
        raise VectorShapeError("illegal coarse width", out_dim=out_dim)
    return Vector256(l2_normalise(vec[:out_dim]))


def to_float32(vec: Sequence[float]) -> tuple[float, ...]:
    """Round to float32 precision — the width ``VECTOR(n)`` actually stores.

    Applied before any determinism assertion so the claim being made is the one the
    database can honour.
    """
    return tuple(float(x) for x in np.asarray(vec, dtype=np.float32).tolist())


def vector_to_b64(vec: Sequence[float]) -> str:
    """Encode as base64 of little-endian float32 — the cassette wire form."""
    arr = np.asarray(vec, dtype="<f4")
    return base64.b64encode(arr.tobytes()).decode("ascii")


def b64_to_vector(payload: str, expected_dim: int) -> tuple[float, ...]:
    arr = np.frombuffer(base64.b64decode(payload.encode("ascii")), dtype="<f4")
    vec = tuple(float(x) for x in arr.tolist())
    check_dim(vec, expected_dim)
    return vec
