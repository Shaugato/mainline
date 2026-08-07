# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The fitted-PCA (``raw_f32``) branch of the projection loader, exercised end to end.

Why this file exists.  The committed coarse projection is the *provisional* ternary map
(recall.md D4: bge is not MRL-trained, the real PCA needs real bge embeddings, and this
machine has neither the weights nor a network).  ``test_projection.py`` covers that path.
What it does not cover is the branch that runs on the day someone *does* fit the PCA:
``storage: "raw_f32"`` — a float32 matrix file, a separate mean file, two independent
digest verifications, and mean-centring at projection time.

Leaving that untested would mean the fitted-PCA path first executes on a machine holding
production weights, at the moment a recall number is about to be published.  So the fitter
is run here for real, on synthetic embeddings with a genuine low-rank structure, and the
artefact it emits is loaded through the ordinary ``load_projection`` code path.

Two claims are deliberately NOT made here: that bge's coarse space is good (that needs the
weights), and that 256 PCA components suffice for the real corpus (that is an ablation
number, not a unit test).  What is proved is narrower and load-bearing: *the loader reads
what the fitter writes, verifies both digests, subtracts the mean, and is deterministic.*
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from mainline_recall_agent.providers.errors import ProjectionError, VectorShapeError
from mainline_recall_agent.providers.projection import load_projection
from mainline_recall_agent.providers.types import COARSE_DIM, EMBED_DIM
from mainline_recall_agent.providers.vectors import is_unit, l2_normalise

#: More rows than components: a rank-deficient fit is not a projection, and the fitter
#: refuses one.  64 latent dimensions plus a little noise gives the top components real
#: variance structure to find — the property a random projection does not have.
_SAMPLES = 320
_LATENT = 64
_PROJECTION_ID = "fixture.coarse256.pca.1"


def _sample_rows(seed: int, count: int) -> np.ndarray:
    """Unit-norm rows from a fixed low-rank generative model.

    Shaped like what a real embedder returns rather than like arbitrary noise: unit norm,
    and concentrated in a cone (the ``+0.4`` offset) exactly as a sentence encoder's output
    is.  That offset is the thing PCA must learn to subtract; the separation test below is
    only meaningful against inputs drawn from the distribution the map was fitted on, which
    is also the only regime the coarse sweep ever sees.
    """
    rng = np.random.default_rng(seed)
    mixing = np.random.default_rng(20260804).standard_normal((_LATENT, EMBED_DIM))
    latent = rng.standard_normal((count, _LATENT))
    data = latent @ mixing + 0.02 * rng.standard_normal((count, EMBED_DIM)) + 0.4
    norms = np.linalg.norm(data, axis=1, keepdims=True)
    unit: np.ndarray = data / norms
    return unit


def _synthetic_embeddings() -> np.ndarray:
    return _sample_rows(20260804, _SAMPLES)


def _install_data_dir(monkeypatch: pytest.MonkeyPatch, directory: Path) -> None:
    """Point ``load_projection`` at ``directory`` instead of the packaged ``data/``."""
    from importlib import resources

    class _Base:
        def __truediv__(self, name: str) -> Path:
            return directory / name

    # projection.py does `from importlib import resources`, so patching the module object
    # itself is what its call site sees.
    monkeypatch.setattr(resources, "files", lambda _pkg: _Base())
    load_projection.cache_clear()


@pytest.fixture
def fitted_dir(tmp_path: Path) -> Path:
    """Run the real fitter and return the directory holding its artefacts."""
    from mainline_recall_agent.providers.fit_projection import main as fit_main

    embeddings_path = tmp_path / "embeddings.npy"
    np.save(embeddings_path, _synthetic_embeddings())
    out_dir = tmp_path / "data"
    exit_code = fit_main(
        [
            "--embeddings",
            str(embeddings_path),
            "--source-model",
            "synthetic-fixture-space",
            "--source-revision",
            "n/a-synthetic",
            "--corpus-sha256",
            "0" * 64,
            "--projection-id",
            _PROJECTION_ID,
            "--out",
            str(out_dir),
            "--out-dim",
            str(COARSE_DIM),
        ]
    )
    assert exit_code == 0
    return out_dir


def _load(monkeypatch: pytest.MonkeyPatch, directory: Path, resource: str | None = None) -> Any:
    _install_data_dir(monkeypatch, directory)
    return load_projection(resource or f"{_PROJECTION_ID}.json")


# --------------------------------------------------------------------------------------
# The fitter's artefact loads through the ordinary path
# --------------------------------------------------------------------------------------


def test_the_fitted_artefact_loads_and_declares_itself_fitted(
    fitted_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    projection = _load(monkeypatch, fitted_dir)
    assert projection.fit_status == "fitted"
    assert projection.is_provisional is False
    assert "pca" in projection.fit_method.lower()
    assert projection.matrix.shape == (COARSE_DIM, EMBED_DIM)
    assert projection.mean is not None
    assert projection.mean.shape == (EMBED_DIM,)
    assert projection.explained_variance_ratio is not None
    assert projection.explained_variance_ratio > 0.99
    load_projection.cache_clear()


def test_a_fitted_projection_satisfies_the_require_fitted_gate(
    fitted_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The exact counterpart of the provisional artefact's hard failure.

    ``MAINLINE_RECALL_REQUIRE_FITTED_PROJECTION=1`` must be a gate that a real PCA passes,
    not a switch that fails everything — otherwise nobody would ever set it and the
    provisional map would ship into a published number.
    """
    monkeypatch.setenv("MAINLINE_RECALL_REQUIRE_FITTED_PROJECTION", "1")
    projection = _load(monkeypatch, fitted_dir)
    assert projection.fit_status == "fitted"
    load_projection.cache_clear()


def test_the_fitted_projection_is_deterministic_across_independent_loads(
    fitted_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    vector = l2_normalise([float(np.sin(i * 0.37)) + 0.01 * i for i in range(EMBED_DIM)])
    first = _load(monkeypatch, fitted_dir).project(vector)
    load_projection.cache_clear()
    second = _load(monkeypatch, fitted_dir).project(vector)
    assert first == second
    assert len(first) == COARSE_DIM
    assert is_unit(first)
    load_projection.cache_clear()


def test_the_mean_is_actually_subtracted(
    fitted_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Projecting the corpus centroid yields the zero vector — and is refused.

    This is the assertion that proves the ``mean`` branch runs.  A loader that ignored the
    mean file would map the centroid to some arbitrary non-zero direction and quietly pass
    every other test in this file, while every coarse vector in production sat inside a
    narrow cone around the uncentred first component.

    Refusing rather than emitting is correct: the centroid has no direction, and a point in
    ``event_cue_coarse`` with no direction matches nothing while still occupying a leaf.
    """
    projection = _load(monkeypatch, fitted_dir)
    assert projection.mean is not None
    centroid = [float(x) for x in projection.mean.tolist()]
    with pytest.raises(VectorShapeError, match="zero or non-finite"):
        projection.project(centroid)
    load_projection.cache_clear()


def test_the_fitted_projection_separates_distinct_inputs(
    fitted_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    projection = _load(monkeypatch, fitted_dir)
    held_out = _sample_rows(seed=987, count=2)
    a = projection.project([float(x) for x in held_out[0].tolist()])
    b = projection.project([float(x) for x in held_out[1].tolist()])
    cosine = float(np.dot(np.asarray(a), np.asarray(b)))
    assert abs(cosine) < 0.999, "the fitted projection collapsed two cues onto one point"
    load_projection.cache_clear()


# --------------------------------------------------------------------------------------
# Neither artefact file can drift without the load failing
# --------------------------------------------------------------------------------------


def _corrupt_first_float(path: Path) -> None:
    blob = bytearray(path.read_bytes())
    blob[0] ^= 0xFF
    path.write_bytes(bytes(blob))


def test_a_corrupted_matrix_file_fails_the_digest_check(
    fitted_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _corrupt_first_float(fitted_dir / f"{_PROJECTION_ID}.f32")
    with pytest.raises(ProjectionError, match="digest mismatch"):
        _load(monkeypatch, fitted_dir)
    load_projection.cache_clear()


def test_a_corrupted_mean_file_fails_the_digest_check(
    fitted_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The mean is verified separately, because it is a separate way to move every point."""
    _corrupt_first_float(fitted_dir / f"{_PROJECTION_ID}.mean.f32")
    with pytest.raises(ProjectionError, match="digest mismatch"):
        _load(monkeypatch, fitted_dir)
    load_projection.cache_clear()


def test_a_projection_of_the_wrong_width_is_refused(
    fitted_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``VECTOR(256)`` is in the DDL; a 128-d artefact must not load, however well-formed."""
    from mainline_recall_agent.providers.fit_projection import main as fit_main

    embeddings_path = fitted_dir.parent / "embeddings.npy"
    narrow_id = "fixture.coarse128.pca.1"
    assert (
        fit_main(
            [
                "--embeddings",
                str(embeddings_path),
                "--source-model",
                "synthetic-fixture-space",
                "--source-revision",
                "n/a-synthetic",
                "--corpus-sha256",
                "0" * 64,
                "--projection-id",
                narrow_id,
                "--out",
                str(fitted_dir),
                "--out-dim",
                "128",
            ]
        )
        == 0
    )
    with pytest.raises(ProjectionError, match="vector widths"):
        _load(monkeypatch, fitted_dir, f"{narrow_id}.json")
    load_projection.cache_clear()


def test_an_unknown_storage_form_is_refused(
    fitted_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sidecar = json.loads((fitted_dir / f"{_PROJECTION_ID}.json").read_text(encoding="utf-8"))
    sidecar["storage"] = "pickle"
    (fitted_dir / "pickled.json").write_text(json.dumps(sidecar), encoding="utf-8")
    with pytest.raises(ProjectionError, match="storage form"):
        _load(monkeypatch, fitted_dir, "pickled.json")
    load_projection.cache_clear()


def test_the_fitter_refuses_a_rank_deficient_corpus(tmp_path: Path) -> None:
    """Fewer embeddings than components is not a projection; it is an overfit basis."""
    from mainline_recall_agent.providers.fit_projection import main as fit_main

    path = tmp_path / "tiny.npy"
    np.save(path, np.random.default_rng(3).standard_normal((32, EMBED_DIM)))
    with pytest.raises(SystemExit, match="at least"):
        fit_main(
            [
                "--embeddings",
                str(path),
                "--source-model",
                "synthetic-fixture-space",
                "--source-revision",
                "n/a-synthetic",
                "--corpus-sha256",
                "0" * 64,
                "--projection-id",
                "too-small",
                "--out",
                str(tmp_path / "out"),
            ]
        )
