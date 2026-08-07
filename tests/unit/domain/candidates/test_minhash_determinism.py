# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""MinHash signatures must be byte-identical across processes, seeds and venvs.

This is the exit criterion that makes the committed permutation table worth
committing.  A signature decides which ancestor clauses are ever compared; if it
cannot be reproduced from committed bytes years later, every refusal downstream
of it is unfalsifiable.

The interesting failure mode is specific and easy to reintroduce: CPython salts
``str.__hash__`` per process, so a MinHash built on ``hash()`` produces a
different signature on every run — and *the code looks fine*, because within one
process it is perfectly self-consistent.  The only way to catch it is to compute
the signature in a **second interpreter, with a different PYTHONHASHSEED**, and
compare.  That is what this file does.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from mainline_domain.identity.candidates.band import band_hashes
from mainline_domain.identity.candidates.minhash import (
    MERSENNE_61,
    default_params,
    jaccard_estimate,
    shingles,
    signature,
)

REPO_ROOT = Path(__file__).resolve().parents[4]
SRC = REPO_ROOT / "verticals" / "mainline" / "packages" / "mainline-domain" / "src"

CLAUSE = (
    "The authorised person shall isolate pump P-101A at ISOL-4471 and verify zero "
    "energy at PIT-1204 before breaking containment. A second signature is required "
    "on the isolation certificate."
)

_CHILD = """
import json, sys
sys.path.insert(0, sys.argv[1])
from mainline_domain.identity.candidates.minhash import signature, default_params
from mainline_domain.identity.candidates.band import band_hashes
params = default_params()
sig = signature(sys.argv[2], params)
print(json.dumps({
    "signature": list(sig),
    "bands": list(band_hashes(sig, params)),
    "hashseed": sys.flags.hash_randomization,
}))
"""


def _child_signature(text: str, hashseed: str) -> dict[str, object]:
    env = dict(os.environ)
    env["PYTHONHASHSEED"] = hashseed
    completed = subprocess.run(
        [sys.executable, "-c", _CHILD, str(SRC), text],
        capture_output=True,
        text=True,
        env=env,
        check=True,
        timeout=90,
    )
    payload = json.loads(completed.stdout.strip().splitlines()[-1])
    assert isinstance(payload, dict)
    return payload


@pytest.mark.slow
def test_signature_is_identical_in_two_interpreter_processes() -> None:
    """The exit criterion: two processes, two hash seeds, one signature."""
    local = list(signature(CLAUSE))
    first = _child_signature(CLAUSE, "1")
    second = _child_signature(CLAUSE, "987654321")

    assert first["signature"] == local, (
        "a child interpreter with PYTHONHASHSEED=1 produced a different signature — "
        "something in the hash path is process-salted"
    )
    assert second["signature"] == local, (
        "a child interpreter with PYTHONHASHSEED=987654321 produced a different "
        "signature — something in the hash path is process-salted"
    )
    assert first["bands"] == second["bands"] == list(band_hashes(tuple(local)))


@pytest.mark.slow
def test_the_child_really_did_randomise_its_hashes() -> None:
    """Guard the guard: a child with hash randomisation off proves nothing."""
    payload = _child_signature(CLAUSE, "1")
    assert payload["hashseed"] == 1, (
        "the child process ran with hash randomisation disabled, so this suite would "
        "not have caught a hash()-based implementation"
    )


def test_signature_is_pure() -> None:
    """Same input, same output, twice in the same process."""
    assert signature(CLAUSE) == signature(CLAUSE)


def test_signature_length_matches_the_committed_table() -> None:
    params = default_params()
    assert len(signature(CLAUSE, params)) == params.n_perms == 128


def test_every_element_is_inside_the_field() -> None:
    """A value outside ``[0, p)`` means the affine map escaped its field."""
    for value in signature(CLAUSE):
        assert 0 <= value < MERSENNE_61


def test_every_element_fits_eight_bytes_big_endian() -> None:
    """The band hash concatenates 8-byte minima; a wider value would truncate."""
    for value in signature(CLAUSE):
        assert value.to_bytes(8, "big")


def test_shingles_are_five_grams_deduplicated_and_ordered() -> None:
    text = "abcabcabc"
    assert shingles(text, 5) == ("abcab", "bcabc", "cabca")


def test_short_text_yields_exactly_one_shingle() -> None:
    assert shingles("abc", 5) == ("abc",)
    assert shingles("abcde", 5) == ("abcde",)


def test_empty_text_raises_rather_than_signing_nothing() -> None:
    with pytest.raises(ValueError, match="canonicaliser bug"):
        shingles("", 5)


def test_identical_text_estimates_jaccard_one() -> None:
    sig = signature(CLAUSE)
    assert jaccard_estimate(sig, sig) == 1.0


def test_estimate_tracks_true_jaccard_within_the_estimator_error() -> None:
    """128 permutations gives a standard error near 1/sqrt(128) ~= 0.088.

    The tolerance below is three standard errors, which is the honest bound for
    an estimator — and it is also why the MinHash number is a recorded feature
    and never a score of record.
    """
    from mainline_domain.identity.candidates.minhash import exact_jaccard

    other = CLAUSE.replace("shall isolate", "shall check")
    params = default_params()
    truth = exact_jaccard(CLAUSE, other, params.shingle_size)
    estimate = jaccard_estimate(signature(CLAUSE, params), signature(other, params))
    assert abs(estimate - truth) < 3 / 128**0.5
