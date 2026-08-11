# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
"""Conformance against the published RFC 8785 vectors, asserted on **exact bytes**.

Two independent bodies of evidence:

1. ``tests/vectors/{input,output,outhex}`` — the six structural vectors from
   ``cyberphone/json-canonicalization``, committed verbatim. Byte equality is asserted
   against ``output/`` *and* independently against the hexadecimal transcription in
   ``outhex/``, because a vector directory that disagrees with itself is a vector
   directory that has been edited.
2. The ES6 number file, reproduced locally from the upstream deterministic generator and
   checked against upstream's published SHA-256. Upstream states the intent plainly:
   "Deterministic generation of the test inputs allows an implementation to verify
   correctness of ES6 number formatting without requiring any network bandwidth by
   generating the test file locally and computing its hash."

String equality is never used here. ``canonicalise`` returns ``bytes``; comparing
``.decode()`` output would let a UTF-8 encoding defect pass, and the encoding is half of
what RFC 8785 specifies.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import es6_numgen
import pytest

from trappoint_jcs.canon_v1 import canonicalise, canonicalise_json, es6_number

VECTORS = Path(__file__).resolve().parent / "vectors"
NAMES = ["arrays", "french", "structures", "unicode", "values", "weird"]


@pytest.mark.parametrize("name", NAMES)
def test_structural_vector_matches_output_bytes(name: str) -> None:
    source = (VECTORS / "input" / f"{name}.json").read_bytes()
    expected = (VECTORS / "output" / f"{name}.json").read_bytes()
    assert canonicalise_json(source) == expected


@pytest.mark.parametrize("name", NAMES)
def test_structural_vector_matches_hex_transcription(name: str) -> None:
    """``outhex/`` is a second, independent statement of the same expected bytes."""
    source = (VECTORS / "input" / f"{name}.json").read_bytes()
    hex_text = (VECTORS / "outhex" / f"{name}.txt").read_text(encoding="ascii")
    expected = bytes.fromhex(hex_text.replace("\n", " "))
    assert canonicalise_json(source) == expected


@pytest.mark.parametrize("name", NAMES)
def test_output_and_outhex_agree(name: str) -> None:
    expected = (VECTORS / "output" / f"{name}.json").read_bytes()
    hex_text = (VECTORS / "outhex" / f"{name}.txt").read_text(encoding="ascii")
    assert expected == bytes.fromhex(hex_text.replace("\n", " "))


def test_canonical_output_is_idempotent() -> None:
    """Canonicalising already-canonical bytes changes nothing, for every vector."""
    for name in NAMES:
        once = canonicalise_json((VECTORS / "input" / f"{name}.json").read_bytes())
        assert canonicalise_json(once) == once


def test_member_ordering_is_utf16_not_codepoint() -> None:
    """The surrogate-pair trap, isolated from the ``weird.json`` vector.

    U+1F602 (a smiley) is code point 0x1F602, which sorts *above* U+FB33 by Python ``str``
    comparison. Its UTF-16 encoding begins with the high surrogate U+D83D, which sorts
    *below* U+FB33. RFC 8785 §3.2.3 mandates the UTF-16 order, so the smiley comes first.
    """
    smiley = "\U0001f602"
    dalet = "דּ"
    assert smiley > dalet, "precondition: Python's own ordering disagrees"
    canonical = canonicalise({dalet: 1, smiley: 2})
    assert canonical.index(smiley.encode("utf-8")) < canonical.index(dalet.encode("utf-8"))


def test_committed_es6_prefix_file_is_authentic() -> None:
    """The committed 1000-line prefix hashes to the value upstream published."""
    digest, size = es6_numgen.PUBLISHED_DIGESTS[1000]
    raw = (VECTORS / "es6testfile1k.txt").read_bytes()
    assert len(raw) == size
    assert hashlib.sha256(raw).hexdigest() == digest


def test_es6_serialisation_reproduces_committed_prefix() -> None:
    """Every one of the 1000 committed expectations is reproduced, line for line."""
    expected_lines = (VECTORS / "es6testfile1k.txt").read_bytes().splitlines(keepends=True)
    produced = list(es6_numgen.generate_lines(1000, es6_number))
    assert produced == expected_lines


def test_es6_serialisation_reproduces_published_10k_digest() -> None:
    """Ten thousand values, checked against upstream's digest rather than a local file.

    This is the load-bearing ES6 assertion: the digest covers the *expected* half of every
    line, so a single mis-formatted number anywhere in the sequence changes it.
    """
    digest, size = es6_numgen.PUBLISHED_DIGESTS[10_000]
    running = hashlib.sha256()
    total = 0
    for line in es6_numgen.generate_lines(10_000, es6_number):
        running.update(line)
        total += len(line)
    assert total == size
    assert running.hexdigest() == digest


@pytest.mark.parametrize(
    ("bits", "expected"),
    [
        (0x0000000000000000, "0"),
        (0x8000000000000000, "0"),  # -0.0 collapses to "0"
        (0x4340000000000001, "9007199254740994"),
        (0x4340000000000002, "9007199254740996"),
        (0x444B1AE4D6E2EF50, "1e+21"),
        (0x3EB0C6F7A0B5ED8D, "0.000001"),
        (0x3EB0C6F7A0B5ED8C, "9.999999999999997e-7"),
        (0x0000000000000001, "5e-324"),  # smallest subnormal
        (0x7FEFFFFFFFFFFFFF, "1.7976931348623157e+308"),  # largest finite
    ],
)
def test_es6_documented_edge_cases(bits: int, expected: str) -> None:
    """The sample lines upstream prints in its README, plus the two extremes."""
    import struct

    value = struct.unpack("<d", struct.pack("<Q", bits))[0]
    assert es6_number(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        # The threshold Python gets wrong in the positive direction: repr(1e17) is
        # '1e+17', but ECMAScript stays positional until 1e21.
        (1e16, "10000000000000000"),
        (1e17, "100000000000000000"),
        (1e20, "100000000000000000000"),
        (1e21, "1e+21"),
        # ...and in the negative direction: repr(1e-5) is '1e-05', ECMAScript is positional
        # until below 1e-6.
        (1e-4, "0.0001"),
        (1e-5, "0.00001"),
        (1e-6, "0.000001"),
        (1e-7, "1e-7"),
        (1.5, "1.5"),
        (56.0, "56"),
    ],
)
def test_es6_threshold_disagreements_with_python(value: float, expected: str) -> None:
    assert es6_number(value) == expected
