# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: FSL-1.1-ALv2
"""MinHash, hand-rolled, over a **committed** permutation table (decision D3).

    5-gram character shingles over ``canon_text``
      → one ``blake2b(digest_size=8)`` base hash per shingle, reduced mod p
      → 128 affine permutations ``(a_i·h + b_i) mod (2**61 - 1)``
      → the per-permutation minimum is the signature element.

**Why hand-rolled.**  Determinism here is an evidentiary requirement, not a
convenience.  A signature decides which ancestor clauses are even *looked at*,
and a signature that cannot be reproduced from committed bytes years later
makes every downstream refusal unfalsifiable.  So:

* the builtin ``hash`` is **banned** repository-wide, and a grep guard in
  ``tests/unit/domain/canon/test_canon_version.py`` enforces the ban across
  every file in this distribution -- including this one, which is why the name
  appears here without its call parentheses.  CPython salts ``str`` hashing per
  process (``PYTHONHASHSEED``), so two runs of the same code on the same text
  would produce different signatures.  ``blake2b`` is specified, seedless and
  stable across interpreter versions.
* ``datasketch`` is **not a dependency**: its permutations come from a seeded
  RNG inside a library whose version is a dependency-resolution outcome.  Here
  the coefficients are a *file in the repository* with a declared
  ``minhash_version``, a self-digest, and a derivation recipe an opposing
  expert can re-run.
* ``numpy`` is deliberately **not used for the modular arithmetic**.  ``a_i·h``
  reaches ~2**122 and ``int64`` wraps silently; Python's arbitrary-precision
  integers do not.  A silently wrapped product is a signature that is wrong in
  a way no assertion in this file would catch.

**The prime.**  ``2**61 - 1`` is a Mersenne prime, so the affine map is a
permutation of the field for any ``a ≠ 0``, and every value fits an 8-byte
big-endian encoding — which is what the band hash concatenates.

Nothing in this module reaches a model, a network, or a clock.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Final

from mainline_domain.data import data_file

__all__ = [
    "BASE_HASH_PERSON",
    "COEFFICIENT_DIGEST_DOMAIN",
    "DEFAULT_TABLE",
    "KDF_PERSON",
    "MERSENNE_61",
    "MinHashParams",
    "MinHashTableError",
    "band_knee",
    "base_hashes",
    "coefficient_digest",
    "default_params",
    "derive_coefficients",
    "exact_jaccard",
    "jaccard_estimate",
    "load_params",
    "s_curve_probability",
    "shingles",
    "signature",
    "signature_from_shingles",
]

MERSENNE_61: Final[int] = (1 << 61) - 1
"""``2**61 - 1``.  Prime, so ``x → (a·x + b) mod p`` is a permutation for ``a ≠ 0``."""

BASE_HASH_PERSON: Final[bytes] = b"mainline-mh1"
"""``blake2b`` personalisation for the per-shingle base hash.

Personalisation is domain separation: the same 8 bytes must not be derivable
from any other digest in the system, so that a value lifted out of one table
cannot be replayed into another.
"""

KDF_PERSON: Final[bytes] = b"mainline-mhkdf1"
"""``blake2b`` personalisation for deriving the committed permutation coefficients."""

COEFFICIENT_DIGEST_DOMAIN: Final[bytes] = b"mainline/minhash/coefficients/v1\n"

DEFAULT_TABLE: Final[tuple[str, str]] = ("minhash", "permutations-v1.json")

_COEFFICIENT_PAIR_WIDTH: Final[int] = 2
"""A permutation is exactly ``[a, b]``; anything else is a malformed table."""


class MinHashTableError(ValueError):
    """The committed permutation table is missing, malformed, or does not verify.

    Never a soft failure.  A cascade running on a permutation table it could not
    verify is a cascade whose candidate sets cannot be reproduced, and this
    package would rather stop than produce numbers nobody can check.
    """


@dataclass(frozen=True, slots=True)
class MinHashParams:
    """Everything the signature depends on, loaded from one committed file."""

    minhash_version: int
    prime: int
    n_perms: int
    bands: int
    rows_per_band: int
    shingle_size: int
    derivation_scheme: str
    coefficients: tuple[tuple[int, int], ...]

    def validate(self) -> None:
        """Structural checks that must hold before a single hash is computed."""
        if self.prime != MERSENNE_61:
            raise MinHashTableError(f"prime is {self.prime}, expected {MERSENNE_61} (2**61 - 1)")
        if self.bands * self.rows_per_band != self.n_perms:
            raise MinHashTableError(
                f"bands*rows_per_band = {self.bands}*{self.rows_per_band} != n_perms {self.n_perms}"
            )
        if len(self.coefficients) != self.n_perms:
            raise MinHashTableError(
                f"{len(self.coefficients)} coefficient pairs for {self.n_perms} permutations"
            )
        if self.shingle_size < 1:
            raise MinHashTableError(f"shingle_size must be >= 1, got {self.shingle_size}")
        for i, (a, b) in enumerate(self.coefficients):
            if not 1 <= a <= self.prime - 1:
                raise MinHashTableError(
                    f"permutation {i}: a={a} is outside [1, p-1]; a=0 collapses the "
                    f"permutation to a constant and destroys the estimator"
                )
            if not 0 <= b <= self.prime - 1:
                raise MinHashTableError(f"permutation {i}: b={b} is outside [0, p-1]")

    @property
    def knee(self) -> float:
        """The Jaccard value at which the banding S-curve crosses 0.5-ish.

        See :func:`band_knee`.  Exposed on the params so a caller never has to
        re-derive it from two loose integers.
        """
        return band_knee(self.bands, self.rows_per_band)


def derive_coefficients(n_perms: int, prime: int = MERSENNE_61) -> tuple[tuple[int, int], ...]:
    """Re-derive the committed coefficients from nothing but this function.

    The recipe, stated so it can be re-implemented in any language::

        a_i = 1 + (
            int(blake2b(b"mainline/minhash/v1/a/<i>", digest_size=16, person=KDF_PERSON), "big")
            % (p - 1)
        )
        b_i = (
            int(blake2b(b"mainline/minhash/v1/b/<i>", digest_size=16, person=KDF_PERSON), "big") % p
        )

    ``<i>`` is the decimal index with no padding.  ``a_i`` is shifted into
    ``[1, p-1]`` because ``a = 0`` would map every shingle to the same value.

    This is *why* the table can be a committed artefact rather than a seed: the
    file is checkable against this function, and this function is checkable
    against the docstring, so there is no step where a number's provenance is
    "the RNG did it".
    """
    out: list[tuple[int, int]] = []
    for i in range(n_perms):
        a_raw = hashlib.blake2b(
            f"mainline/minhash/v1/a/{i}".encode(), digest_size=16, person=KDF_PERSON
        ).digest()
        b_raw = hashlib.blake2b(
            f"mainline/minhash/v1/b/{i}".encode(), digest_size=16, person=KDF_PERSON
        ).digest()
        a = 1 + (int.from_bytes(a_raw, "big") % (prime - 1))
        b = int.from_bytes(b_raw, "big") % prime
        out.append((a, b))
    return tuple(out)


def coefficient_digest(coefficients: tuple[tuple[int, int], ...]) -> bytes:
    r"""Digest a canonical rendering of the coefficient table with SHA-256.

    Preimage: :data:`COEFFICIENT_DIGEST_DOMAIN` followed by one ``"{a} {b}\\n"``
    line per permutation in index order.  Decimal, no padding, no JSON — so the
    digest is a function of the numbers rather than of a serialiser's choices,
    and can be recomputed with ``sha256sum`` from a three-line script.
    """
    parts = [COEFFICIENT_DIGEST_DOMAIN]
    parts.extend(f"{a} {b}\n".encode() for a, b in coefficients)
    return hashlib.sha256(b"".join(parts)).digest()


def _parse_table(payload: Any, *, source: str, verify: bool) -> MinHashParams:
    if not isinstance(payload, dict):
        raise MinHashTableError(f"{source}: top level is {type(payload).__name__}, expected object")
    required = (
        "minhash_version",
        "prime",
        "n_perms",
        "bands",
        "rows_per_band",
        "shingle_size",
        "derivation",
        "coefficients",
        "coefficients_sha256",
    )
    missing = [key for key in required if key not in payload]
    if missing:
        raise MinHashTableError(f"{source}: missing key(s) {', '.join(missing)}")

    derivation = payload["derivation"]
    if not isinstance(derivation, dict) or "scheme" not in derivation:
        raise MinHashTableError(f"{source}: `derivation` must be an object with a `scheme`")

    raw_pairs = payload["coefficients"]
    if not isinstance(raw_pairs, list):
        raise MinHashTableError(f"{source}: `coefficients` must be an array of [a, b] pairs")
    coefficients: list[tuple[int, int]] = []
    for i, pair in enumerate(raw_pairs):
        if not isinstance(pair, list) or len(pair) != _COEFFICIENT_PAIR_WIDTH:
            raise MinHashTableError(f"{source}: coefficient {i} is not a two-element array")
        a, b = pair
        if not isinstance(a, int) or not isinstance(b, int) or isinstance(a, bool):
            raise MinHashTableError(f"{source}: coefficient {i} is not a pair of integers")
        coefficients.append((a, b))

    params = MinHashParams(
        minhash_version=int(payload["minhash_version"]),
        prime=int(payload["prime"]),
        n_perms=int(payload["n_perms"]),
        bands=int(payload["bands"]),
        rows_per_band=int(payload["rows_per_band"]),
        shingle_size=int(payload["shingle_size"]),
        derivation_scheme=str(derivation["scheme"]),
        coefficients=tuple(coefficients),
    )
    params.validate()

    if verify:
        declared = str(payload["coefficients_sha256"])
        actual = coefficient_digest(params.coefficients).hex()
        if declared != actual:
            raise MinHashTableError(
                f"{source}: coefficients_sha256 is {declared} but the table digests to "
                f"{actual} — the committed permutation table has been altered"
            )
        if params.derivation_scheme == "blake2b-kdf-v1":
            expected = derive_coefficients(params.n_perms, params.prime)
            if expected != params.coefficients:
                bad = next(
                    i
                    for i, (x, y) in enumerate(zip(expected, params.coefficients, strict=True))
                    if x != y
                )
                raise MinHashTableError(
                    f"{source}: declares derivation scheme 'blake2b-kdf-v1' but coefficient "
                    f"{bad} does not match what that recipe produces"
                )
    return params


def load_params(path: Path | None = None, *, verify: bool = True) -> MinHashParams:
    """Load and (by default) **verify** the committed permutation table.

    Verification is on by default and re-derives every coefficient from
    :func:`derive_coefficients` when the file declares the ``blake2b-kdf-v1``
    scheme.  P2 in miniature: the table a gate's inputs depend on is *checked*,
    not trusted, and the check runs where the value is read rather than in a
    test that a future edit could forget to run.
    """
    target = path if path is not None else data_file(*DEFAULT_TABLE)
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except OSError as exc:  # pragma: no cover - filesystem failure, not logic
        raise MinHashTableError(f"cannot read permutation table {target}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise MinHashTableError(f"{target} is not valid JSON: {exc}") from exc
    return _parse_table(payload, source=str(target), verify=verify)


@lru_cache(maxsize=1)
def default_params() -> MinHashParams:
    """Return the committed table, loaded and verified once per process."""
    return load_params()


def shingles(text: str, size: int) -> tuple[str, ...]:
    """Split ``text`` into distinct character *k*-grams, in first-appearance order.

    Character shingles rather than token shingles because the input is
    ``canon_text``: whitespace is already collapsed, so a character 5-gram
    straddles word boundaries and is robust to the single-word substitutions
    that dominate procedure edits.

    ``text`` shorter than ``size`` yields exactly one shingle — the whole
    string.  Zero shingles would make the signature undefined, and defining it
    as "matches everything" or "matches nothing" would both be a decision made
    by an edge case rather than by a rule.

    :raises ValueError: if ``text`` is empty.  Empty ``canon_text`` is a
        canonicaliser bug and must not be silently absorbed here.
    """
    if not text:
        raise ValueError("cannot shingle empty text: empty canon_text is a canonicaliser bug")
    if size < 1:
        raise ValueError(f"shingle size must be >= 1, got {size}")
    if len(text) <= size:
        return (text,)
    seen: dict[str, None] = {}
    for i in range(len(text) - size + 1):
        seen.setdefault(text[i : i + size], None)
    return tuple(seen)


def base_hashes(items: tuple[str, ...]) -> tuple[int, ...]:
    """One ``blake2b``-64 value per shingle, reduced into ``[0, p)``.

    ``digest_size=8``, big-endian, personalised with :data:`BASE_HASH_PERSON`,
    then ``mod 2**61 - 1``.  The reduction is what puts the value in the field
    the affine permutations act on; it is not a truncation of the digest.
    """
    return tuple(
        int.from_bytes(
            hashlib.blake2b(s.encode("utf-8"), digest_size=8, person=BASE_HASH_PERSON).digest(),
            "big",
        )
        % MERSENNE_61
        for s in items
    )


def signature_from_shingles(items: tuple[str, ...], params: MinHashParams) -> tuple[int, ...]:
    """Compute the ``n_perms``-element MinHash signature of a shingle set."""
    if not items:
        raise ValueError("cannot sign an empty shingle set")
    prime = params.prime
    hashes = base_hashes(items)
    return tuple(min((a * h + b) % prime for h in hashes) for a, b in params.coefficients)


def signature(text: str, params: MinHashParams | None = None) -> tuple[int, ...]:
    """Compute the MinHash signature of ``canon_text``.

    Byte-identical across interpreter processes, interpreter versions and fresh
    virtual environments — asserted, not assumed, by
    ``tests/unit/domain/candidates/test_minhash_determinism.py``, which runs the
    computation in a *separate* process with a different ``PYTHONHASHSEED`` and
    compares.
    """
    p = params if params is not None else default_params()
    return signature_from_shingles(shingles(text, p.shingle_size), p)


def jaccard_estimate(left: tuple[int, ...], right: tuple[int, ...]) -> float:
    """Estimate Jaccard as the fraction of permutations whose minima agree.

    Unbiased for the Jaccard similarity of the underlying shingle sets, with
    standard error ~``1/sqrt(n_perms)`` — about 0.088 at 128 permutations.  That
    error is why the estimate is a *recorded feature* and never a score of
    record: an 0.09 standard error on a number that decides whether an
    obligation carries is not a number that should decide anything.
    """
    if len(left) != len(right):
        raise ValueError(f"signature lengths differ: {len(left)} vs {len(right)}")
    if not left:
        raise ValueError("cannot compare empty signatures")
    return sum(1 for x, y in zip(left, right, strict=True) if x == y) / len(left)


def exact_jaccard(left: str, right: str, size: int) -> float:
    """Compute the true Jaccard similarity of two shingle sets.

    The ground truth the estimator is measured against.  Linear in the text
    length and therefore usable in calibration and in tests, never in the hot
    path — the whole point of banding is not to enumerate the pairs this would
    have to be called on.
    """
    a = set(shingles(left, size))
    b = set(shingles(right, size))
    union = len(a | b)
    return len(a & b) / union if union else 0.0


def s_curve_probability(jaccard: float, bands: int, rows_per_band: int) -> float:
    """``1 - (1 - J**r)**b`` — the probability that a pair shares ≥ 1 band.

    This is the whole trade-off in one line: more bands raises recall, more rows
    per band raises precision.  It is stated here so the calibration test can
    compare *observed* band recall against the analytic curve rather than
    against a number somebody remembered.
    """
    if not 0.0 <= jaccard <= 1.0:
        raise ValueError(f"jaccard must be in [0, 1], got {jaccard}")
    return 1.0 - (1.0 - jaccard**rows_per_band) ** bands


def band_knee(bands: int, rows_per_band: int) -> float:
    """``(1/b)**(1/r)`` — the Jaccard value at the S-curve's steepest point.

    For the committed 16 x 8 configuration this is ``2**-0.5 ≈ 0.7071``.  The
    research note says "τ≈0.75"; 0.7071 is the exact analytic knee for those
    parameters and is what this package uses.  The rounded value is not wrong,
    it is rounded, and a threshold that is 0.04 away from where the curve
    actually turns is a threshold that will be blamed for the wrong thing.
    """
    return float((1.0 / bands) ** (1.0 / rows_per_band))
