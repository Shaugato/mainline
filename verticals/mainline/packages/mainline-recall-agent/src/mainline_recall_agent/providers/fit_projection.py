# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""Fit the real PCA that replaces the provisional coarse projection.

Run this on a machine that holds the pinned model weights, against embeddings of a
declared corpus::

    python -m mainline_recall_agent.providers.fit_projection \\
        --embeddings build/bge_cues.npy \\
        --source-model BAAI/bge-large-en-v1.5 \\
        --source-revision <git sha of the revision you fetched> \\
        --corpus-sha256 <sha256 of the corpus manifest> \\
        --projection-id coarse256.pca.1 \\
        --out src/mainline_recall_agent/providers/data

It emits ``<projection_id>.f32`` (row-major float32, shape ``(256, 1024)``),
``<projection_id>.mean.f32``, and the sidecar with ``fit_status="fitted"``, the corpus
digest and the explained-variance ratio.  ``projection.py`` verifies both digests on load,
so the artefact cannot drift without the load failing.

Deliberately a separate step rather than something the provider does lazily: a projection
that is fitted at runtime moves every point in ``event_cue_coarse`` whenever the corpus
grows, and the sweep would then be reaching a different set of events from one week to the
next with nothing in the record saying so.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

from .types import COARSE_DIM, EMBED_DIM

__all__ = ["fit_pca", "main"]


def _load_embeddings(path: Path) -> np.ndarray:
    if path.suffix == ".npy":
        arr = np.load(path)
    elif path.suffix in {".jsonl", ".ndjson"}:
        rows = []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    rows.append(json.loads(line)["embedding"])
        arr = np.asarray(rows)
    else:
        raise SystemExit(f"unsupported embeddings file: {path.suffix} (use .npy or .jsonl)")
    arr = np.asarray(arr, dtype=np.float64)
    if arr.ndim != 2 or arr.shape[1] != EMBED_DIM:
        raise SystemExit(f"embeddings must have shape (n, {EMBED_DIM}); got {arr.shape}")
    if arr.shape[0] < COARSE_DIM:
        raise SystemExit(
            f"need at least {COARSE_DIM} embeddings to fit {COARSE_DIM} components; "
            f"got {arr.shape[0]}. A rank-deficient projection is not a projection."
        )
    return arr


def fit_pca(
    embeddings: np.ndarray, out_dim: int = COARSE_DIM
) -> tuple[np.ndarray, np.ndarray, float]:
    """Return ``(components, mean, explained_variance_ratio)``.

    Mean-centred SVD.  Components are the top ``out_dim`` right-singular vectors, as rows,
    so ``components @ (x - mean)`` is the projection.
    """
    mean = embeddings.mean(axis=0)
    centred = embeddings - mean
    _, singular, vt = np.linalg.svd(centred, full_matrices=False)
    variance = singular**2
    total = float(variance.sum())
    kept = float(variance[:out_dim].sum())
    ratio = kept / total if total > 0 else 0.0
    return vt[:out_dim], mean, ratio


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--embeddings", required=True, type=Path)
    parser.add_argument("--source-model", required=True)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--corpus-sha256", required=True)
    parser.add_argument("--projection-id", required=True)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--out-dim", type=int, default=COARSE_DIM)
    args = parser.parse_args(argv)

    embeddings = _load_embeddings(args.embeddings)
    components, mean, ratio = fit_pca(embeddings, args.out_dim)

    out_dir: Path = args.out
    out_dir.mkdir(parents=True, exist_ok=True)
    matrix_name = f"{args.projection_id}.f32"
    mean_name = f"{args.projection_id}.mean.f32"
    matrix_bytes = np.ascontiguousarray(components, dtype="<f4").tobytes()
    mean_bytes = np.ascontiguousarray(mean, dtype="<f4").tobytes()
    (out_dir / matrix_name).write_bytes(matrix_bytes)
    (out_dir / mean_name).write_bytes(mean_bytes)

    sidecar: dict[str, Any] = {
        "schema": "mainline.recall.projection/1",
        "projection_id": args.projection_id,
        "source_model": args.source_model,
        "source_revision": args.source_revision,
        "in_dim": EMBED_DIM,
        "out_dim": args.out_dim,
        "storage": "raw_f32",
        "fit_method": "pca_svd_mean_centred",
        "fit_status": "fitted",
        "fit_corpus_sha256": args.corpus_sha256,
        "fit_sample_count": int(embeddings.shape[0]),
        "explained_variance_ratio": round(ratio, 6),
        "matrix_file": matrix_name,
        "matrix_sha256": hashlib.sha256(matrix_bytes).hexdigest(),
        "mean_file": mean_name,
        "mean_sha256": hashlib.sha256(mean_bytes).hexdigest(),
        "renormalise_output": True,
        "output_dtype": "float32",
        "notes": (
            "Fitted PCA. Replaces the provisional ternary projection. Changing this "
            "artefact moves every point in event_cue_coarse: it is a re-index, and the "
            "projection_id must change with it so assert_homogeneous can see the split."
        ),
    }
    sidecar_path = out_dir / f"{args.projection_id}.json"
    sidecar_path.write_text(json.dumps(sidecar, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {sidecar_path}")
    print(f"explained_variance_ratio={ratio:.6f} over {embeddings.shape[0]} samples")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
