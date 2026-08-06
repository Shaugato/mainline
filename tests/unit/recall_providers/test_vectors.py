# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""Renormalisation, Matryoshka truncation, and the cassette wire encoding."""

from __future__ import annotations

import math

import pytest

from mainline_recall_agent.providers.errors import VectorShapeError
from mainline_recall_agent.providers.types import COARSE_DIM, EMBED_DIM
from mainline_recall_agent.providers.vectors import (
    b64_to_vector,
    is_unit,
    l2_normalise,
    matryoshka_coarse,
    to_float32,
    vector_to_b64,
)


def _ramp(dim: int = EMBED_DIM) -> list[float]:
    # Offset so no component is exactly zero: the direction-preservation assertions below
    # divide component-wise.
    return [math.sin(i * 0.37) + 0.1 * i + 1.0 for i in range(dim)]


def test_normalisation_produces_a_unit_vector() -> None:
    vec = l2_normalise(_ramp())
    assert len(vec) == EMBED_DIM
    assert is_unit(vec)
    assert abs(math.sqrt(math.fsum(c * c for c in vec)) - 1.0) < 1e-12


def test_normalisation_is_idempotent() -> None:
    once = l2_normalise(_ramp())
    twice = l2_normalise(once)
    assert max(abs(a - b) for a, b in zip(once, twice, strict=True)) < 1e-12


def test_zero_vector_is_refused_rather_than_passed_through() -> None:
    with pytest.raises(VectorShapeError):
        l2_normalise([0.0] * EMBED_DIM)


def test_non_finite_component_is_refused() -> None:
    bad = _ramp()
    bad[7] = float("nan")
    with pytest.raises(VectorShapeError):
        matryoshka_coarse(bad)


def test_matryoshka_truncation_renormalises_client_side() -> None:
    full = l2_normalise(_ramp())
    coarse = matryoshka_coarse(full)
    assert len(coarse) == COARSE_DIM
    assert is_unit(coarse)
    # The prefix of a unit vector is NOT a unit vector: this is the whole reason the
    # renormalisation is client-side rather than assumed.
    prefix_norm = math.sqrt(math.fsum(c * c for c in full[:COARSE_DIM]))
    assert prefix_norm < 0.999


def test_matryoshka_preserves_direction_of_the_prefix() -> None:
    full = l2_normalise(_ramp())
    coarse = matryoshka_coarse(full)
    scale = coarse[0] / full[0]
    for a, b in zip(coarse, full[:COARSE_DIM], strict=True):
        assert abs(a - b * scale) < 1e-9


def test_illegal_coarse_width_is_refused() -> None:
    full = l2_normalise(_ramp())
    with pytest.raises(VectorShapeError):
        matryoshka_coarse(full, out_dim=0)
    with pytest.raises(VectorShapeError):
        matryoshka_coarse(full, out_dim=EMBED_DIM + 1)


def test_wrong_width_is_refused() -> None:
    with pytest.raises(VectorShapeError):
        matryoshka_coarse(l2_normalise(_ramp(512)))


def test_base64_round_trip_is_exact_at_float32() -> None:
    original = to_float32(l2_normalise(_ramp()))
    restored = b64_to_vector(vector_to_b64(original), EMBED_DIM)
    assert restored == original


def test_base64_round_trip_checks_the_declared_width() -> None:
    payload = vector_to_b64(l2_normalise(_ramp()))
    with pytest.raises(VectorShapeError):
        b64_to_vector(payload, COARSE_DIM)
