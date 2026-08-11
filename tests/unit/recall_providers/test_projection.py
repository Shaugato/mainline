# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""The committed coarse projection: verified, deterministic, and honest about being provisional."""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest
from mainline_recall_agent.providers.errors import ProjectionError
from mainline_recall_agent.providers.projection import (
    derive_ternary_matrix,
    load_projection,
)
from mainline_recall_agent.providers.types import COARSE_DIM, EMBED_DIM
from mainline_recall_agent.providers.vectors import is_unit, l2_normalise


def _ramp(seed: float = 0.37) -> tuple[float, ...]:
    return l2_normalise([math.sin(i * seed) + 0.03 * i for i in range(EMBED_DIM)])


def test_committed_projection_loads_and_verifies_its_digest() -> None:
    projection = load_projection()
    assert projection.in_dim == EMBED_DIM
    assert projection.out_dim == COARSE_DIM
    assert projection.matrix.shape == (COARSE_DIM, EMBED_DIM)
    assert projection.matrix_sha256


def test_the_committed_projection_declares_itself_provisional_and_not_pca() -> None:
    """The claim in the sidecar must match what the artefact actually is.

    recall.md D4 requires a PCA before any recall number is published.  Shipping a random
    projection labelled ``pca`` would be precisely the false claim D4 exists to prevent, so
    the label is asserted rather than trusted.
    """
    projection = load_projection()
    assert projection.is_provisional
    assert projection.fit_status == "provisional"
    assert "pca" not in projection.fit_method.lower()
    assert projection.explained_variance_ratio is None
    assert "NOT PCA" in projection.notes


def test_derivation_is_deterministic_across_calls() -> None:
    first = derive_ternary_matrix("seed-under-test", 8, 32)
    second = derive_ternary_matrix("seed-under-test", 8, 32)
    assert first.tobytes() == second.tobytes()
    assert derive_ternary_matrix("other-seed", 8, 32).tobytes() != first.tobytes()


def test_projection_output_is_deterministic_across_runs() -> None:
    """Same input, same 256-d output — the property the coarse sweep depends on.

    ``load_projection`` is cached, so the cache is cleared between derivations to make sure
    what is being compared is two independent derivations of the matrix, not one matrix
    used twice.
    """
    vector = _ramp()
    load_projection.cache_clear()
    first = load_projection().project(vector)
    load_projection.cache_clear()
    second = load_projection().project(vector)
    assert first == second
    assert len(first) == COARSE_DIM


def test_projection_output_is_unit_and_float32_rounded() -> None:
    import numpy as np

    coarse = load_projection().project(_ramp())
    assert is_unit(coarse)
    assert list(np.asarray(coarse, dtype=np.float32).tolist()) == list(coarse)


def test_projection_separates_distinct_inputs() -> None:
    a = load_projection().project(_ramp(0.37))
    b = load_projection().project(_ramp(1.11))
    cosine = math.fsum(x * y for x, y in zip(a, b, strict=True))
    assert cosine < 0.999, "the projection collapsed two different vectors onto one point"


def test_wrong_input_width_is_refused() -> None:
    from mainline_recall_agent.providers.errors import VectorShapeError

    with pytest.raises(VectorShapeError):
        load_projection().project([0.1] * 512)


def test_a_tampered_sidecar_fails_to_load(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A projection cannot drift without the load failing."""
    from importlib import resources

    import mainline_recall_agent.providers.projection as projection_module

    source = Path(projection_module.__file__).parent / "data" / "bge_large_en_v1_5.coarse256.json"
    sidecar = json.loads(source.read_text(encoding="utf-8"))
    sidecar["generator"]["seed"] = "a-different-seed"
    target_dir = tmp_path / "data"
    target_dir.mkdir()
    (target_dir / "tampered.json").write_text(json.dumps(sidecar), encoding="utf-8")

    class _Base:
        def __truediv__(self, name: str) -> Path:
            return target_dir / name

    # projection.py does `from importlib import resources`, so patching the module object
    # itself is what its call site sees.
    monkeypatch.setattr(resources, "files", lambda _pkg: _Base())
    load_projection.cache_clear()
    with pytest.raises(ProjectionError) as excinfo:
        load_projection("tampered.json")
    assert "digest mismatch" in str(excinfo.value)
    load_projection.cache_clear()


def test_require_fitted_projection_env_makes_the_provisional_artefact_a_hard_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MAINLINE_RECALL_REQUIRE_FITTED_PROJECTION", "1")
    load_projection.cache_clear()
    with pytest.raises(ProjectionError) as excinfo:
        load_projection()
    assert "provisional" in str(excinfo.value)
    load_projection.cache_clear()


def test_fit_pca_produces_ranked_orthonormal_components() -> None:
    """The fitter is real code, exercised on synthetic data — not a stub for later."""
    import numpy as np
    from mainline_recall_agent.providers.fit_projection import fit_pca

    rng = np.random.default_rng(7)
    latent = rng.standard_normal((512, 16))
    mixing = rng.standard_normal((16, EMBED_DIM))
    data = latent @ mixing + 0.01 * rng.standard_normal((512, EMBED_DIM))

    components, mean, ratio = fit_pca(data, out_dim=16)
    assert components.shape == (16, EMBED_DIM)
    assert mean.shape == (EMBED_DIM,)
    # 16 latent dimensions plus a little noise: the top 16 components must capture nearly
    # all the variance, which is the property a random projection does NOT have.
    assert ratio > 0.99
    gram = components @ components.T
    assert np.allclose(gram, np.eye(16), atol=1e-8)
