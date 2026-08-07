<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: Apache-2.0
-->

# RFC 8785 conformance vectors

Third-party ground truth. Nothing in this directory was written by us except this file and
[`es6_numgen.py`](es6_numgen.py), and nothing here may be edited to make a test pass — if
our output disagrees with these bytes, our output is wrong.

## Provenance

| Path | Origin | Licence |
|---|---|---|
| `input/*.json` | [`cyberphone/json-canonicalization`](https://github.com/cyberphone/json-canonicalization) `testdata/input`, verbatim | Apache-2.0, © 2018 Anders Rundgren |
| `output/*.json` | same repository, `testdata/output`, verbatim | Apache-2.0, © 2018 Anders Rundgren |
| `outhex/*.txt` | same repository, `testdata/outhex`, verbatim | Apache-2.0, © 2018 Anders Rundgren |
| `es6testfile1k.txt` | **generated here** by `es6_numgen.py`; its SHA-256 equals the value upstream publishes for the first 1 000 lines | Apache-2.0 |
| `es6_numgen.py` | our Python port of upstream's `testdata/numgen.go` | Apache-2.0 |

Each vendored file carries a `.license` sidecar naming the upstream copyright holder, per
[REUSE](https://reuse.software/). Copies were taken from the repository's `master` branch
and are asserted three ways in
[`../test_rfc8785_vectors.py`](../test_rfc8785_vectors.py): our bytes against `output/`,
our bytes against `outhex/`, and `output/` against `outhex/`. The third assertion exists
because a vector directory that disagrees with itself has been tampered with, and that is
worth finding out from a test rather than from an opposing expert.

## The six structural vectors, and what each one catches

| Vector | The trap |
|---|---|
| `arrays` | array members keep their order; object members inside them do not (`"1"`, `"10"`, `"d"`) |
| `french` | sorting is **not** locale-aware: `péché` sorts after `peach` because canonicalisation ignores collation |
| `structures` | `56.0` serialises as `56`; empty objects survive; `"\n"` as a *member name* |
| `unicode` | no Unicode normalisation — `A` + U+030A stays two code points and does **not** become `Å` |
| `values` | the whole ES6 number surface: `1E30 → 1e+30`, `4.50 → 4.5`, `2e-3 → 0.002`, `1e-27`, and `333333333.33333329 → 333333333.3333333` |
| `weird` | **the surrogate trap.** U+1F602 (😂) is code point 0x1F602 and sorts *above* U+FB33 (דּ) in Python; its UTF-16 encoding starts with the surrogate 0xD83D and sorts *below*. RFC 8785 §3.2.3 mandates the UTF-16 order. Also: U+007F is emitted literally, and `</script>` is not escaped |

## The ES6 number file

The official vector is `es6testfile100m.txt` — 100 million lines, ~4.0 GB uncompressed,
distributed as a GitHub release asset. Committing it is absurd; downloading it in CI makes
our ES6 conformance claim depend on a network we do not control.

Neither is necessary. The file is **deterministically generated**, and upstream publishes
the SHA-256 of its first *N* lines precisely so that implementations can verify offline:

> "Deterministic generation of the test inputs allows an implementation to verify
> correctness of ES6 number formatting without requiring any network bandwidth by
> generating the test file locally and computing its hash."

| lines | SHA-256 | bytes |
|---:|---|---:|
| 1 000 | `be18b62b6f69cdab33a7e0dae0d9cfa869fda80ddc712221570f9f40a5878687` | 37 967 |
| 10 000 | `b9f7a8e75ef22a835685a52ccba7f7d6bdc99e34b010992cbc5864cd12be6892` | 399 022 |
| 100 000 | `22776e6d4b49fa294a0d0f349268e5c28808fe7e0cb2bcbe28f63894e494d4c7` | 4 031 728 |
| 1 000 000 | `49415fee2c56c77864931bd3624faad425c3c577d6d74e89a83bc725506dad16` | 40 357 417 |

Each line is `<lowercase hex of the IEEE-754 bits, unpadded>,<expected serialisation>\n`.
The **expected** half is produced by `trappoint_jcs.canon_v1.es6_number`, so reproducing
the published digest is a statement about our serialiser rather than about our copy of a
file: one mis-formatted value anywhere in the sequence changes the hash.

The suite runs the 1 000-line and 10 000-line prefixes on every invocation (about a
second). The 100 000 and 1 000 000 prefixes are in the table so that a reviewer who wants
more can get it with a one-line change:

```python
from es6_numgen import PUBLISHED_DIGESTS, generate_lines
from trappoint_jcs.canon_v1 import es6_number
import hashlib

digest, size = PUBLISHED_DIGESTS[1_000_000]
running = hashlib.sha256()
for line in generate_lines(1_000_000, es6_number):
    running.update(line)
assert running.hexdigest() == digest
```

The generated sequence is: 168 fixed bit patterns (zeros, both signed zeros, the smallest
subnormal, the largest finite double, the ±1-ULP neighbourhoods of 0.1 and 1.0, the 2⁵³
boundary, the 1e21 boundary, the 1e-6 boundary), then 2 000 consecutive bit patterns from
the smallest positive normal upward, then an endless SHA-256 chain reinterpreted as
little-endian doubles with zero, NaN and the infinities skipped. The edge cases are
deliberately front-loaded, which is why the 1 000-line prefix is already a serious test.
