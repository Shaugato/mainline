<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: FSL-1.1-ALv2
-->

# Cross-verifier golden vectors

**These files are a CONTRACT, not fixtures.**

They bind two independent implementations of the same arithmetic:

| Implementation | Language | Where it runs |
|---|---|---|
| `verticals/mainline/apps/console/src/verify/` | TypeScript, dependency-free | a Web Worker in the reader's browser |
| `packages/trappoint-verify` | Python, dependency floor `cryptography` | offline, on a stranger's laptop |

> **Both must agree on every case byte for byte, or CI fails on whichever side moved.**
> **A vector is never edited to make an implementation pass.**

If the two disagree, exactly one of these is true: the browser is wrong, the offline
verifier is wrong, or the specification is ambiguous. All three are findings. None of them
is fixed by changing a file in this directory.

---

## The files

| File | Subject | Specification |
|---|---|---|
| `index.json` | the manifest, the contract sentence and the case counts | — |
| `jcs.json` | RFC 8785 canonicalisation: unicode escapes, `-0`, large integers, nested UTF-16 key ordering, and five refusals | RFC 8785 |
| `rfc6962.json` | leaf and node hashing, roots at every size, inclusion and consistency proofs, and five negatives | RFC 6962 §2.1, §2.1.1, §2.1.2 |
| `checkpoint.json` | signed notes, a published key pair, an adversary key, and thirteen accept/reject cases | `spec/wire/checkpoint.md` v1.0 |
| `silence-boundary.json` | Proof of Exhausted Recall boundary pairs, including the hand-excluded-item attack | ARCHITECTURE.md §5.7 |
| `ledger-payload.json` | one complete, cryptographically real `ledger` envelope | `contracts/ledger.schema.json` |

---

## Where the values came from

**`jcs.json` was captured from the Python reference.** The `canonical` member of every case
is the output of `packages/trappoint-jcs/src/trappoint_jcs/canon_v1.py`'s `canonicalise()` —
the module vendored byte-for-byte into `trappoint-verify`, whose SHA-256 is written into
every checkpoint as `canon_src_sha256`. A vector file produced by the implementation it
checks would assert only that the implementation equals itself.

The reference was driven with `json.loads(..., parse_int=float)`. That is not a shortcut: it
is the exact emulation of the environment the browser runs in. JavaScript has one number
type, so every JSON number a browser sees is an IEEE-754 double, and comparing an
exact-integer Python run against a double-only browser run would compare two implementations
under different premises. The `number_premise` member records this.

**`rfc6962.json` and `checkpoint.json` were asserted against the frozen worked example.**
`spec/wire/checkpoint.md` §7 publishes five leaves, their hashes, the link chain, the root,
the note text, a P-256 key pair and a signature. The generator recomputed all of them and
**refused to emit a vector that disagreed**. The private key in that document is published
deliberately, signs nothing but the example, and never protected anything.

**The adversary key in `checkpoint.json` was generated once and pinned.** It exists for the
re-signing negative cases and is trusted by no case.

---

## The asymmetries, recorded rather than hidden

`jcs.json`'s `refusals` carry an `enforced_by` member:

- `both` — NaN, the infinities, unpaired surrogates, duplicate member names.
- `python-only` — an integer outside ±(2⁵³−1). Python refuses it because an exact-integer
  implementation and an ECMAScript one would emit different digits. **The browser cannot
  refuse it**: by the time the literal reaches JavaScript it is already a double and the
  offending digits are already gone. The same limit means the CU-5 evidentiary profile
  (refuse binary floats) is unenforceable in a browser, because JavaScript cannot see the
  difference between `1` and `1.0`. Both are writing-side rules.

---

## Adding a case

1. Add it to the generator, which lives with the worker that owns this directory.
2. Run the generator; it captures the Python reference's output and asserts every value that
   also appears in a frozen specification.
3. Run the TypeScript suite. It must pass without any change to `src/verify/`, or the new
   case has found a defect — which is the point.
4. Run the Python suite against the same directory.

A case whose expected value had to be edited after step 3 is not a vector. It is a record of
what the implementation happened to do.
