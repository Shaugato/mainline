# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The committed 1024 -> 256 coarse projection for non-Matryoshka embedding spaces.

recall.md D4: *bge is not MRL-trained, so truncating it would be a false claim.*  The
coarse sweep therefore needs a real linear map, committed to the repository and loaded
from the package rather than fitted at runtime, because a projection that changes shifts
every point in ``event_cue_coarse`` and silently changes what the sweep can reach.

Two storage forms, one loader:

``deterministic_ternary``
    A sparse ternary (Achlioptas) random projection derived from a declared keystream.
    The matrix is *integers*, so it regenerates bit-identically on every platform and
    needs no binary blob in git.  It is **not PCA** and the sidecar says so:
    ``fit_status = "provisional"``.  It preserves distances in expectation
    (Johnson-Lindenstrauss) and preserves nothing about the corpus's variance structure.

``raw_f32``
    The fitted PCA: a ``(out_dim, in_dim)`` little-endian float32 file plus a mean vector,
    produced by ``fit_projection.py`` from real embeddings of a declared corpus.  The
    sidecar then carries ``fit_status = "fitted"``, the corpus digest and the explained
    variance ratio.

Both forms are sha256-verified after load, so a projection cannot drift without the load
failing.  ``projection_id`` is folded into ``index_gen`` by the callers, which means a
corpus coarsened under the provisional map can never be silently compared with one
coarsened under the fitted PCA — ``assert_homogeneous`` catches it.

Set ``MAINLINE_RECALL_REQUIRE_FITTED_PROJECTION=1`` (the eval harness and any deployment
that publishes a number must) to make loading a provisional projection a hard failure.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources
from typing import Any, Final

import numpy as np

from .errors import ProjectionError
from .types import COARSE_DIM, EMBED_DIM, Vector256
from .vectors import check_dim, l2_normalise, to_float32

__all__ = [
    "DEFAULT_PROJECTION_RESOURCE",
    "CommittedProjection",
    "derive_ternary_matrix",
    "load_projection",
]

DEFAULT_PROJECTION_RESOURCE: Final[str] = "bge_large_en_v1_5.coarse256.json"
_SIDECAR_SCHEMA: Final[str] = "mainline.recall.projection/1"
_PERSON: Final[bytes] = b"mainline-proj"


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def derive_ternary_matrix(seed: str, out_dim: int, in_dim: int) -> np.ndarray:
    """Derive the sparse ternary matrix from a keystream — exact, platform-independent.

    Keystream: ``blake2b(counter, key=utf8(seed), person=b"mainline-proj", digest_size=64)``
    for counter = 0, 1, 2, ...  Each byte ``b`` yields one entry:
    ``b % 6 == 0 -> +1``, ``b % 6 == 1 -> -1``, otherwise ``0`` (density 1/3, the
    Achlioptas construction).  The global scale is irrelevant because the output is
    renormalised, so no ``sqrt(3/k)`` factor is applied.
    """
    if out_dim <= 0 or in_dim <= 0:
        raise ProjectionError("illegal projection shape", out_dim=out_dim, in_dim=in_dim)
    needed = out_dim * in_dim
    key = seed.encode("utf-8")
    chunks: list[bytes] = []
    produced = 0
    counter = 0
    while produced < needed:
        block = hashlib.blake2b(
            counter.to_bytes(8, "big"), key=key, person=_PERSON, digest_size=64
        ).digest()
        chunks.append(block)
        produced += len(block)
        counter += 1
    stream = np.frombuffer(b"".join(chunks)[:needed], dtype=np.uint8)
    residue = stream % 6
    matrix = np.zeros(needed, dtype=np.int8)
    matrix[residue == 0] = 1
    matrix[residue == 1] = -1
    shaped = matrix.reshape(out_dim, in_dim)
    if not shaped.any(axis=1).all():
        raise ProjectionError("derived projection has an all-zero row", seed=seed)
    return shaped


@dataclass(frozen=True)
class CommittedProjection:
    """A loaded, digest-verified linear map from ``in_dim`` to ``out_dim``."""

    projection_id: str
    source_model: str
    source_revision: str | None
    in_dim: int
    out_dim: int
    fit_method: str
    fit_status: str
    matrix_sha256: str
    matrix: np.ndarray
    mean: np.ndarray | None
    explained_variance_ratio: float | None
    notes: str

    @property
    def is_provisional(self) -> bool:
        return self.fit_status != "fitted"

    def project(self, vec: Sequence[float]) -> Vector256:
        """Project, renormalise, and round to the float32 width ``VECTOR(256)`` stores."""
        check_dim(vec, self.in_dim)
        arr = np.asarray(vec, dtype=np.float64)
        if self.mean is not None:
            arr = arr - self.mean
        projected = self.matrix @ arr
        return Vector256(to_float32(l2_normalise(projected.tolist())))

    def describe(self) -> dict[str, Any]:
        """The record a caller pins alongside ``embed_model`` in ``recall_policy``."""
        return {
            "projection_id": self.projection_id,
            "source_model": self.source_model,
            "source_revision": self.source_revision,
            "fit_method": self.fit_method,
            "fit_status": self.fit_status,
            "matrix_sha256": self.matrix_sha256,
            "out_dim": self.out_dim,
        }


def _verify(digest_of: bytes, expected: str, what: str) -> None:
    actual = hashlib.sha256(digest_of).hexdigest()
    if actual != expected:
        raise ProjectionError(
            f"{what} digest mismatch: the committed projection artefact has changed",
            expected=expected,
            actual=actual,
        )


def _load_from_sidecar(sidecar: dict[str, Any], base: Any) -> CommittedProjection:
    if sidecar.get("schema") != _SIDECAR_SCHEMA:
        raise ProjectionError("unknown projection sidecar schema", schema=sidecar.get("schema"))
    in_dim = int(sidecar["in_dim"])
    out_dim = int(sidecar["out_dim"])
    storage = str(sidecar["storage"])
    expected = str(sidecar["matrix_sha256"])

    mean: np.ndarray | None = None
    if storage == "deterministic_ternary":
        seed = str(sidecar["generator"]["seed"])
        matrix_i8 = derive_ternary_matrix(seed, out_dim, in_dim)
        _verify(matrix_i8.tobytes(order="C"), expected, "ternary matrix")
        matrix = matrix_i8.astype(np.float64)
    elif storage == "raw_f32":
        blob = (base / str(sidecar["matrix_file"])).read_bytes()
        _verify(blob, expected, "float32 matrix")
        matrix = np.frombuffer(blob, dtype="<f4").astype(np.float64).reshape(out_dim, in_dim)
        mean_file = sidecar.get("mean_file")
        if mean_file:
            mean_blob = (base / str(mean_file)).read_bytes()
            _verify(mean_blob, str(sidecar["mean_sha256"]), "mean vector")
            mean = np.frombuffer(mean_blob, dtype="<f4").astype(np.float64)
            if mean.shape != (in_dim,):
                raise ProjectionError("mean vector has the wrong width", shape=mean.shape)
    else:
        raise ProjectionError("unknown projection storage form", storage=storage)

    projection = CommittedProjection(
        projection_id=str(sidecar["projection_id"]),
        source_model=str(sidecar["source_model"]),
        source_revision=sidecar.get("source_revision"),
        in_dim=in_dim,
        out_dim=out_dim,
        fit_method=str(sidecar["fit_method"]),
        fit_status=str(sidecar["fit_status"]),
        matrix_sha256=expected,
        matrix=matrix,
        mean=mean,
        explained_variance_ratio=sidecar.get("explained_variance_ratio"),
        notes=str(sidecar.get("notes", "")),
    )
    if projection.is_provisional and _truthy(
        os.environ.get("MAINLINE_RECALL_REQUIRE_FITTED_PROJECTION")
    ):
        raise ProjectionError(
            "MAINLINE_RECALL_REQUIRE_FITTED_PROJECTION is set and the committed coarse "
            "projection is provisional (not fitted from embeddings of a declared corpus). "
            "Run fit_projection.py on a machine holding the pinned model weights.",
            projection_id=projection.projection_id,
            fit_status=projection.fit_status,
        )
    return projection


@lru_cache(maxsize=8)
def load_projection(resource: str = DEFAULT_PROJECTION_RESOURCE) -> CommittedProjection:
    """Load and verify a committed projection shipped inside the package."""
    base = resources.files(f"{__package__}.data")
    handle = base / resource
    if not handle.is_file():
        raise ProjectionError("committed projection sidecar not found", resource=resource)
    sidecar = json.loads(handle.read_text(encoding="utf-8"))
    projection = _load_from_sidecar(sidecar, base)
    if projection.in_dim != EMBED_DIM or projection.out_dim != COARSE_DIM:
        raise ProjectionError(
            "committed projection does not match the DDL's vector widths",
            in_dim=projection.in_dim,
            out_dim=projection.out_dim,
        )
    return projection
