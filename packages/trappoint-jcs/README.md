<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: Apache-2.0
-->

# `trappoint-jcs` — canonical bytes, before any hash

**Apache-2.0 · Python ≥ 3.13 · zero runtime dependencies.**

A hash of bytes nobody can reproduce is not evidence. This package produces the bytes.

Every leaf in the MAINLINE custody ledger is `SHA-256(0x00 ‖ canon_bytes)`, and
`canon_bytes` is what `canonicalise_payload()` returns. If a third party cannot regenerate
those bytes from the record, the whole custody chain reduces to a checksum we computed
about ourselves. So this module is small, frozen, dependency-free, and pinned by hash in
[`spec/custody/canon-registry.yaml`](../../spec/custody/canon-registry.yaml).

---

## Why it is not done in SQL

Two platform facts, both verified, both fatal to the obvious approach:

- CockroachDB's `sha256()` returns hex **text**, not `BYTES`
  ([cockroach#73896](https://github.com/cockroachdb/cockroach/issues/73896)).
- `JSONB` normalises and reorders keys, so `payload::STRING` is CockroachDB's rendering of
  the document, not the document.

`sha256(payload::STRING)` is therefore a number only we can compute, on only our version
of only our database. Canonicalisation is **client-side, versioned, and frozen**, and the
exact bytes hashed are stored alongside the hash.

---

## The two entry points, and why there are two

```python
from trappoint_jcs import canonicalise, canonicalise_payload

canonicalise({"b": 1, "a": 3.5})          # b'{"a":3.5,"b":1}'   — RFC 8785, in full
canonicalise_payload({"a": 3.5})          # raises NonEvidentiaryNumber
canonicalise_payload({"a_millibar": 3500})  # b'{"a_millibar":3500}'
```

`canonicalise` is **strict RFC 8785**, including the ES6 `Number.prototype.toString`
serialisation, and is asserted against the published conformance vectors on exact bytes.
It exists so that conformance is a fact rather than a claim.

`canonicalise_payload` is the **evidentiary profile** — custody ruling
[CU-5](../../docs/adr/0042-float-ban-in-evidentiary-payloads.md) — and it is what the
sequencer, the intake client and every agent actually call. It refuses IEEE-754 floats
outright.

### The float ban, in one paragraph

The ES6 number path is the single largest interoperability risk in RFC 8785: ECMAScript
switches to exponential notation below `1e-6` and at or above `1e21`, whereas Python's
`repr` switches at `1e-4` and `1e16`, and Go's, Java's and Rust's default formatters each
differ again. A canonicaliser that gets that wrong produces bytes a stranger cannot
reproduce, which is the one failure mode this package exists to prevent. Meanwhile **no
evidentiary quantity is a binary float**: a setpoint is a decimal string, a severity is an
integer, a pressure is an integer in its smallest unit, a timestamp is RFC 3339 text.
Keeping the conformance and refusing the float is strictly better than either alternative.

Integers are exact, and integers outside ±(2⁵³−1) are refused with
`NonInteroperableNumber` — above that bound a conforming ECMAScript implementation would
round, so no two implementations would agree on the bytes.

---

## What is asserted, and against what

| Assertion | Evidence |
|---|---|
| The six structural vectors canonicalise byte-for-byte | `tests/vectors/{input,output,outhex}`, committed verbatim from `cyberphone/json-canonicalization` (Apache-2.0) |
| `output/` and `outhex/` agree with each other | a vector directory that disagrees with itself has been edited |
| ES6 number serialisation is correct for 1 000 and 10 000 values | upstream's **published SHA-256** of the deterministically generated `es6testfile`, reproduced offline — the digest covers the *expected* half of every line, so one wrong number changes it |
| Member ordering is by UTF-16 code unit, not code point | U+1F602 sorts below U+FB33 by UTF-16 and above it in Python; `weird.json` and an isolated test both catch it |
| `canonicalise(json.loads(canonicalise(x))) == canonicalise(x)` | Hypothesis, 400 examples per run |
| The dependency list is empty | a test reads `pyproject.toml` and asserts it |
| `canon_v1.py` imports only the standard library, with no relative imports | an AST test — a relative import would not survive vendoring into `trappoint-verify` |

```console
$ python -m pytest packages/trappoint-jcs
82 passed
```

---

## Retention, and the vendoring equality

**Every canonicaliser ever shipped is retained forever.** Deleting `canon_v1` would not
break any code — new leaves would use `canon_v2` quite happily — it would make every leaf
ever written under `canon_v1` permanently unverifiable. That is a breaking change to
*evidence*, and it is silent, which is why a machine refuses it:

```console
$ python scripts/custody/check_vendored_canon.py
$ python scripts/custody/check_vendored_canon.py --selftest   # prove the guard bites
```

`trappoint-verify` claims a dependency floor of `cryptography` and nothing else, so it
cannot import this package. It carries a **byte-identical copy** of `canon_v1.py` instead,
and the byte-equality is a CI assertion rather than a promise.

`canon_src_sha256()` returns the SHA-256 of this module's own source over **LF-normalised
bytes** — normalised so that the value fingerprints the code rather than the checkout's
line-ending convention. It is written into every checkpoint, and verifier check 10
compares it against the canonicaliser the verifier is running: the scheme's own code is
inside the scheme.

---

## What this package does not do

It does not hash anything (that is `trappoint-ledger`), does not know what a leaf is, does
not know what MAINLINE is, and holds no database driver, no cloud SDK and no domain
vocabulary. A stranger auditing the bytes that every custody claim rests on should have to
read one file, and it should import nothing.
