<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: Apache-2.0
-->

# I08 — Certified null

> Part of the **TRAPPOINT `1.0.0-rc.1`** public API. Adding an invariant is a MAJOR bump; see
> [`../VERSIONING.md`](../VERSIONING.md).

- **Instantiated by:** the recall layer
- **MAINLINE schema invariants that instantiate it:** `MI21`
- **Conformance cases:** 2 (0 on the reference profile)

---

## NORMATIVE STATEMENT

**An empty or partial retrieval result MUST be representable only with a coverage certificate bound
to the index generation that produced it.**

- *"Nothing found"* MUST NOT be insertable as a bare fact. A result with zero admitted candidates MUST
  carry a certificate naming the index generation, the universe, and the arithmetic of the cut.
- A truncated result MUST be typed as truncated, with the truncation point recorded, and MUST NOT be
  presentable as complete.
- Where coverage cannot be established, the result MUST be typed **undetermined**, and an undetermined
  result MUST NOT arm a gate — but it MUST also never be recorded as a clean pass.
- A certificate MUST bind to a **generation identifier**, not to a timestamp, because the index is
  the thing that changed.

---

## MECHANISM

| Role | SQL object |
|---|---|
| the certificate | a coverage-certificate relation carrying the index fingerprint, the universe commitment, and the boundary arithmetic |
| the refusal | `empty_result_certified` — `CHECK` that a zero-candidate result carries a certificate |
| the third verdict | an `undetermined` result kind, plus `undetermined_never_blocks` so an undetermined comparison is never laundered into a finding |
| binding to the index | the certificate's index fingerprint, captured at retrieval time |

---

## OBSERVABLE

| Attempt | SQLSTATE | Exhibit |
|---|---|---|
| record an empty result with no coverage certificate | `23514` | `empty_result_certified` |
| use an undetermined result to block | `23514` | `undetermined_never_blocks` |

---

## CONFORMANCE

| Case | History | SQLSTATE | Exhibit | Profiles | Depth |
|---|---|---|---|---|---|
| [`CF-62`](../conformance/manifest.toml) | An UNDETERMINED fixity result used to block | `23514` | `undetermined_never_blocks` | mainline | 1 |
| [`CF-65`](../conformance/manifest.toml) | Record an empty retrieval result with no coverage certificate bound to the index generation | `23514` | `empty_result_certified` | mainline | 1 |

Generated from [`../conformance/manifest.toml`](../conformance/manifest.toml); the manifest is
authoritative wherever this table disagrees with it.

---

## NOT CLAIMED

- **It does not claim the empty answer is correct.** It claims the empty answer is a *checkable
  claim about a universe* rather than an unexamined absence. A certified null can still be wrong; it
  cannot be silent.
- **It does not claim the index was good.** Certification binds the answer to a generation so that a
  later, better index does not retroactively make the earlier answer look negligent — and so that it
  does not retroactively make it look fine either.
- **It does not retire the fundamental limit.** A cue that was never in the corpus cannot be
  retrieved, certified or otherwise. The certificate bounds the honest claim; it does not extend it.
- **`undetermined_never_blocks` is the one place unknown does not block**, and that is deliberate: an
  undetermined comparison is not a finding, and treating it as one manufactures alarm fatigue with no
  argument behind it.
