# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The committed permutation table is evidence, so it is checked, not trusted.

``data/minhash/permutations-v1.json`` fixes the 128 affine permutations behind
every ``band_hash`` in ``mainline.clause_band``.  Three properties have to hold
for it to be worth committing, and all three are asserted here rather than
assumed:

1. it **re-derives** from the recipe printed inside it, so an opposing expert
   can rebuild it from the docstring and nothing else;
2. it carries a **self-digest** over the coefficients, so tampering is loud;
3. ``load_params`` **refuses** a table that fails either check — a warning
   would be worthless, because a cascade running on unverified permutations
   produces candidate sets nobody can reproduce.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from mainline_domain.data import data_file
from mainline_domain.identity.candidates.minhash import (
    MERSENNE_61,
    MinHashTableError,
    band_knee,
    coefficient_digest,
    default_params,
    derive_coefficients,
    load_params,
)

TABLE = data_file("minhash", "permutations-v1.json")


@pytest.fixture
def payload() -> dict[str, object]:
    data = json.loads(TABLE.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def test_the_committed_table_loads_and_verifies() -> None:
    params = load_params()
    assert params.minhash_version == 1
    assert params.n_perms == 128
    assert params.bands == 16
    assert params.rows_per_band == 8
    assert params.shingle_size == 5
    assert params.prime == MERSENNE_61


def test_every_coefficient_re_derives_from_the_published_recipe(
    payload: dict[str, object],
) -> None:
    """The whole reason the table can be committed rather than seeded."""
    committed = [tuple(pair) for pair in payload["coefficients"]]  # type: ignore[index]
    assert committed == list(derive_coefficients(128, MERSENNE_61))


def test_the_self_digest_matches(payload: dict[str, object]) -> None:
    params = default_params()
    assert payload["coefficients_sha256"] == coefficient_digest(params.coefficients).hex()


def test_the_declared_knee_matches_the_analytic_one(payload: dict[str, object]) -> None:
    assert payload["band_knee_jaccard"] == pytest.approx(band_knee(16, 8))
    assert band_knee(16, 8) == pytest.approx(0.7071067811865476)


def test_a_altered_coefficient_is_refused(tmp_path: Path, payload: dict[str, object]) -> None:
    """One digit changed anywhere in the table, and the file stops loading."""
    tampered = dict(payload)
    coefficients = [list(pair) for pair in payload["coefficients"]]  # type: ignore[index]
    coefficients[64][0] += 1
    tampered["coefficients"] = coefficients
    target = tmp_path / "tampered.json"
    target.write_text(json.dumps(tampered), encoding="utf-8")

    with pytest.raises(MinHashTableError, match="has been altered"):
        load_params(target)


def test_a_digest_updated_to_match_a_tampered_table_is_still_refused(
    tmp_path: Path, payload: dict[str, object]
) -> None:
    """The second line of defence: the digest can be recomputed, the recipe cannot."""
    tampered = dict(payload)
    coefficients = [list(pair) for pair in payload["coefficients"]]  # type: ignore[index]
    coefficients[3][1] ^= 1
    tampered["coefficients"] = coefficients
    tampered["coefficients_sha256"] = coefficient_digest(
        tuple((a, b) for a, b in coefficients)
    ).hex()
    target = tmp_path / "resealed.json"
    target.write_text(json.dumps(tampered), encoding="utf-8")

    with pytest.raises(MinHashTableError, match="blake2b-kdf-v1"):
        load_params(target)


def test_a_zero_multiplier_is_refused(tmp_path: Path, payload: dict[str, object]) -> None:
    """``a = 0`` collapses a permutation to a constant and silently destroys recall."""
    broken = dict(payload)
    coefficients = [list(pair) for pair in payload["coefficients"]]  # type: ignore[index]
    coefficients[0][0] = 0
    broken["coefficients"] = coefficients
    target = tmp_path / "zeroed.json"
    target.write_text(json.dumps(broken), encoding="utf-8")

    with pytest.raises(MinHashTableError, match=r"outside \[1, p-1\]"):
        load_params(target)


def test_a_band_geometry_that_does_not_multiply_out_is_refused(
    tmp_path: Path, payload: dict[str, object]
) -> None:
    broken = dict(payload)
    broken["bands"] = 15
    target = tmp_path / "geometry.json"
    target.write_text(json.dumps(broken), encoding="utf-8")

    with pytest.raises(MinHashTableError, match="!= n_perms"):
        load_params(target)


def test_a_missing_key_is_named(tmp_path: Path, payload: dict[str, object]) -> None:
    broken = {k: v for k, v in payload.items() if k != "shingle_size"}
    target = tmp_path / "missing.json"
    target.write_text(json.dumps(broken), encoding="utf-8")

    with pytest.raises(MinHashTableError, match="shingle_size"):
        load_params(target)


def test_a_missing_table_raises_rather_than_returning_a_default() -> None:
    with pytest.raises((MinHashTableError, FileNotFoundError)):
        load_params(TABLE.parent / "permutations-v999.json")


def test_the_table_declares_its_algorithm_in_words(payload: dict[str, object]) -> None:
    """A number table with no prose is a number table nobody can re-implement."""
    algorithm = payload["algorithm"]
    assert isinstance(algorithm, str)
    for token in ("blake2b", "5-gram", "mainline-mh1", "mainline-band1", "signed INT8"):
        assert token in algorithm
