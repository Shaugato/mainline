<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: Apache-2.0
-->

# I07 — Universe commitment

> Part of the **TRAPPOINT `1.0.0-rc.1`** public API. Adding an invariant is a MAJOR bump; see
> [`../VERSIONING.md`](../VERSIONING.md).

- **Instantiated by:** the recall layer
- **MAINLINE schema invariants that instantiate it:** `MI18`
- **Conformance cases:** 1 (0 on the reference profile)

---

## NORMATIVE STATEMENT

**Any retrieval informing a gate MUST commit to its candidate universe and its partition of that
universe *before* any disposition may reference it.**

- The retrieval MUST record, in the same transaction as its result, the universe it drew from, the
  partition it applied, and the arithmetic that produced the partition.
- The retrieval MUST run under a **policy version that predates the data it scores** and that is
  **anchored** — committed somewhere the operator cannot later alter — before its results may inform
  a gate.
- A disposition MUST NOT reference a retrieval whose universe commitment is absent, unanchored, or
  written after the fact.
- Thresholds MUST NOT be adjustable after the retrieval they governed. Retro-tuning a threshold so an
  omission looks reasonable MUST be unrepresentable, not merely discouraged.

---

## MECHANISM

| Role | SQL object |
|---|---|
| the commitment | a score-sorted commitment over the candidate universe, disclosing the root, the threshold, the score at the boundary and the count — enough to verify the cut, not enough to leak the corpus |
| the anchor requirement | `fn_recall_policy_anchored()` — `BEFORE INSERT` on the retrieval run; refuses unless the policy's anchored size is non-null and inside a cosigned checkpoint |
| the partition | `candidates_conserved` — `CHECK` that the universe is exactly partitioned (see [`I13`](I13-silence-logged.md)) |
| ordering | the reckoning point that defines the universe is computed **before** the retrieval, not after, and is part of the committed record |

---

## OBSERVABLE

| Attempt | SQLSTATE | Exhibit |
|---|---|---|
| record a retrieval under an unanchored or absent policy version | `P0001` | `mainline.fn_recall_policy_anchored` |
| record a retrieval whose partition does not exhaust its universe | `23514` | `candidates_conserved` |

---

## CONFORMANCE

| Case | History | SQLSTATE | Exhibit | Profiles | Depth |
|---|---|---|---|---|---|
| [`CF-59`](../conformance/manifest.toml) | A recall run under a policy version whose anchoring is absent or outside a cosigned checkpoint | `P0001` | `mainline.fn_recall_policy_anchored` | mainline | 1 |

Generated from [`../conformance/manifest.toml`](../conformance/manifest.toml); the manifest is
authoritative wherever this table disagrees with it.

---

## NOT CLAIMED

- **It does not claim the corpus was exhausted.** It claims *the retrieval that ran* was exhausted
  over the universe it committed to. Those are different sentences and only the second one is true.
  Any material saying otherwise is overclaiming.
- **It does not claim bit-identical replay of an approximate-nearest-neighbour result.** Index
  generations change; that is why the certified null binds to an index generation
  ([`I08`](I08-certified-null.md)) rather than pretending the result is reproducible.
- **It does not claim the threshold was well chosen.** It claims the threshold was chosen *first*, by
  a signed policy, and cannot be moved afterwards to flatter the outcome.
- **It does not claim relevance.** Whether the universe contained the thing that mattered is an
  evaluation question with a measured answer, not an invariant.
