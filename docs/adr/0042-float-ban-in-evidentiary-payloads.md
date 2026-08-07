<!--
SPDX-FileCopyrightText: 2026 MAINLINE
SPDX-License-Identifier: CC-BY-4.0
-->

# ADR 0042 — CU-5: the ledger payload profile bans IEEE-754 floats

**Status:** Accepted · **Date:** 2026-08-07 · **Decider:** custody lead · **Milestone:** K2
**Supersedes:** nothing · **Implements:** `docs/leads/custody.md` §2 decision **CU-5**

## Context

Every custody claim MAINLINE makes reduces to one sentence: *a stranger, holding only the
record and an open-source verifier, reproduces the bytes we hashed.* `canon_bytes` is
those bytes. RFC 8785 (JSON Canonicalization Scheme) specifies how to produce them, and
§3.2.2.3 requires numbers to be serialised exactly as ECMAScript
`Number.prototype.toString` does.

That last requirement is the sharpest edge in the specification, and it cuts in a place
nobody looks. ECMAScript switches from positional to exponential notation when the decimal
exponent is below −6 or at least 21. Every other runtime disagrees:

| value | ECMAScript / RFC 8785 | Python `repr` | Go `%v` |
|---|---|---|---|
| `1e-5` | `0.00001` | `1e-05` | `1e-05` |
| `1e-7` | `1e-7` | `1e-07` | `1e-07` |
| `1e17` | `100000000000000000` | `1e+17` | `1e+17` |
| `1e21` | `1e+21` | `1e+21` | `1e+21` |
| `-0.0` | `0` | `-0.0` | `-0` |

A canonicaliser that reaches for its language's default float formatter is wrong on the
first two rows and the last, and the failure is silent: the bytes hash, the leaf commits,
the checkpoint signs, and the disagreement surfaces years later when somebody else's
verifier says `leaf_hash` does not match — which reads, in a report, as *tampering*.

That is the failure mode this ADR exists to remove. Not "our floats might be slightly
wrong". **Our own tamper-evidence scheme manufacturing a false accusation against us.**

Two further facts bear on the decision:

1. **No evidentiary quantity in MAINLINE is a binary float.** A setpoint is a decimal
   string on a nameplate. A severity is an integer 1–5. A pressure is an integer in its
   smallest unit. A timestamp is RFC 3339 text. A confidence score is not evidence and
   does not enter the ledger. The set of payload fields that genuinely need `float` is
   empty, and it was empty before we looked.
2. **Decimal fractions are not representable.** `0.1 + 0.2 != 0.3` is not a curiosity when
   the number in question is a lockout setpoint that a court will read aloud. Carrying an
   exact integer in millibar is both more reproducible and more honest than carrying a
   double that approximates bar.

## Decision

**`trappoint_jcs.canon_v1` implements RFC 8785 in full, including the ES6 number path, and
is asserted conformant against the published vectors on exact bytes. Separately,
`canonicalise_payload()` — the function the sequencer, the intake client and every agent
call — raises `NonEvidentiaryNumber` on any `float`, at any depth, before serialising a
single byte.**

Three supporting rulings, all narrow:

- **Integers are exact within ±(2⁵³−1) and refused outside it** (`NonInteroperableNumber`).
  Inside the range, ES6 output and exact-integer output are identical, so we are both
  conformant and exact. Outside it, a conforming ECMAScript canonicaliser rounds, so no
  two implementations agree; refusing is the only behaviour that never produces bytes a
  third party disputes. Carry such a value as a decimal string.
- **`NaN` and the infinities raise** on both paths. JSON has no literal for them.
- **The conformance path keeps the capability.** `canonicalise(3.5)` still returns `b'3.5'`.
  The ban is a *profile*, not an amputation, so RFC 8785 conformance remains testable and
  a future non-evidentiary caller is not blocked.

The intended encodings, stated so the ban has an answer rather than only a refusal:

| Instead of | Carry |
|---|---|
| `{"pressure_bar": 1.01325}` | `{"pressure_millibar": 1013}` or `{"pressure_bar": "1.01325"}` |
| `{"score": 0.87}` | scores are not evidence; if it must be recorded, `{"score_permille": 870}` |
| `{"elapsed": 12.5}` | `{"elapsed_ms": 12500}` |

## Consequences

**We keep the conformance claim and lose the exposure.** `packages/trappoint-jcs` passes
the six cyberphone structural vectors byte-for-byte and reproduces upstream's published
SHA-256 for the 1 000- and 10 000-line prefixes of the ES6 number file — that digest covers
the expected serialisation of every value in the sequence, so a single wrong number breaks
it. The ES6 implementation is real, tested and shipped. It simply never runs on an
evidentiary payload.

**The refusal is early and it names the alternative.** `canonicalise_payload` walks the
whole structure before emitting anything, so the exception carries the offending value and
the sentence "carry the value as an exact integer in its smallest unit, or as a decimal
string" rather than arriving half-way through a byte stream.

**Payload authors are constrained.** Every worker emitting a ledger payload — the gate
service, the recall orchestrator, the agent fleet, the migration attestation sink — must
encode quantities as integers or strings. This is enforced at the canonicaliser, which is
the one place every payload passes through, so it cannot be forgotten in a new call site.
It will be discovered the first time somebody writes `{"tau": 0.62}`, which is the correct
time to discover it.

**A narrow, documented deviation exists.** Refusing integers beyond ±(2⁵³−1) is stricter
than RFC 8785, which would have us round them. The deviation only ever *refuses*; it never
emits bytes a conforming implementation would not emit. It is recorded here, in the module
docstring, and in `spec/custody/canon-registry.yaml` so a third-party implementer is not
surprised by it.

**Retention is forever.** `canon_v1` is pinned by SHA-256 in
`spec/custody/canon-registry.yaml`; `scripts/custody/check_vendored_canon.py` fails any
change to it and any drift between it and the copy vendored into `trappoint-verify`. If
the float ban ever needs lifting, that is `canon_v2` with a new `payload_ver` — never an
edit to this file.

## Revisit trigger

A vertical whose evidentiary quantities are genuinely continuous and genuinely
float-native — a laboratory instrument stream, say — would need `canon_v2` with the ban
lifted and the ES6 path load-bearing. That is a new canonicaliser, a new `payload_ver` and
a new registry row, not a change here. MAINLINE is not that vertical.

## References

- RFC 8785 §3.2.2.3, and Appendix B on ES6 number serialisation
- `docs/leads/custody.md` §2 CU-5, §1.4a
- `packages/trappoint-jcs/src/trappoint_jcs/canon_v1.py`
- `packages/trappoint-jcs/tests/vectors/README.md` — provenance of the ground truth
- ARCHITECTURE.md §7.2 (canonicalisation is client-side, never SQL)
