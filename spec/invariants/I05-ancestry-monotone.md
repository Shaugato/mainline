<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: Apache-2.0
-->

# I05 — Ancestry monotone

> Part of the **TRAPPOINT `1.0.0-rc.1`** public API. Adding an invariant is a MAJOR bump; see
> [`../VERSIONING.md`](../VERSIONING.md).

- **Instantiated by:** the ancestry layer; every lineage accumulator
- **MAINLINE schema invariants that instantiate it:** `MI01`, `MI15`, `MI26`
- **Conformance cases:** 2 (1 on the reference profile)

---

## NORMATIVE STATEMENT

**A child's ancestry commitment MUST extend its parent's, and inherited severity MUST NOT decrease.**

- For any versioned object with a declared parent, the child's ancestor set MUST be a superset of the
  parent's and the child's maximum inherited severity MUST be `>=` the parent's.
- A closure or accumulator recomputing an ancestry MUST be **append-only and generation-dense**: a new
  generation MUST be exactly `previous + 1`, so a skipped generation is detectable rather than
  plausible.
- A decrease in inherited severity MUST NOT be representable as an ordinary recomputation. It is
  admissible **only** with a positive, signed severity-revision row written in the same transaction —
  a second rater's dated act, not a recalculation.
- An ancestry commitment MUST NOT be shrinkable by rewording, re-authoring, re-filing or
  re-classifying the object it belongs to.

---

## MECHANISM

| Role | SQL object |
|---|---|
| version-level guard | `fn_clause_version_guard()` — refuses when a child's `sev_max` or ancestry size is below its parent's |
| closure-level guard | `fn_closure_guard()` — generations dense and monotone; a severity decrease requires a signed revision row in the same transaction; writes a custody entry in the same statement so a closure rewrite is impossible to perform invisibly |
| append-only | `fn_refuse_mutation()` on the closure relation, plus a grant that lets exactly one role insert into it and nothing else |
| the reason it is K1 work | the guard is what makes the ancestry layer's asynchrony safe; it ships before the ancestry layer exists |

---

## OBSERVABLE

| Attempt | SQLSTATE | Exhibit |
|---|---|---|
| a child version whose inherited severity is below its parent's | `P0001` | `mainline.fn_clause_version_guard` |
| `UPDATE` a closure row | `P0001` | `mainline.fn_refuse_mutation` |
| a new closure generation lowering severity, unsigned | `P0001` | `mainline.fn_closure_guard` |
| a closure generation that is not exactly `previous + 1` | `P0001` | `mainline.fn_closure_guard` |

---

## CONFORMANCE

| Case | History | SQLSTATE | Exhibit | Profiles | Depth |
|---|---|---|---|---|---|
| [`CF-08`](../conformance/manifest.toml) | Rewrite the blame closure: as an UPDATE, then as a new generation with a lowered severity | `P0001` | `mainline.fn_refuse_mutation` | both | 2 |
| [`CF-56`](../conformance/manifest.toml) | A clause version whose sev_max is lower than its parent's | `P0001` | `mainline.fn_clause_version_guard` | mainline | 1 |

Generated from [`../conformance/manifest.toml`](../conformance/manifest.toml); the manifest is
authoritative wherever this table disagrees with it.

---

## NOT CLAIMED

- **It does not claim the ancestry is complete.** An edge nobody derived is not in the closure, and
  monotonicity says nothing about edges that were never found. What it forecloses is *shrinkage* — the
  laundering path where a control is reworded across four revisions until nobody recalls what wrote it.
- **It does not claim severity is correct.** Severity is a fitted quantity with a method and a
  version; this invariant constrains its *direction over lineage*, not its value.
- **It does not claim a downgrade is always wrong.** It requires a downgrade to be an **act** — signed,
  dated, attributable, and by a second rater — rather than an arithmetic outcome nobody has to own.
- **It does not defend against a rebuilt closure from doctored inputs.** Generation density makes the
  rebuild visible; whether the inputs were honest is the custody layer's question.
