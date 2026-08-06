<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: Apache-2.0
-->

# I13 — Silence is logged

> Part of the **TRAPPOINT `1.0.0-rc.1`** public API. Adding an invariant is a MAJOR bump; see
> [`../VERSIONING.md`](../VERSIONING.md).

- **Instantiated by:** the recall layer
- **MAINLINE schema invariants that instantiate it:** `MI16`, `MI17`
- **Conformance cases:** 2 (0 on the reference profile)

---

## NORMATIVE STATEMENT

**Every declined surfacing, exclusion, truncation and abstention MUST be written, with its arithmetic,
in the same transaction as the decision it belongs to.**

- A candidate that was considered and not surfaced MUST leave a row recording *why*, with the numbers
  that produced the outcome — not a category label.
- The universe MUST be **exactly partitioned**: candidates = surfaced-blocking + surfaced-advisory +
  silenced + deduplicated, with no remainder and no double counting, enforced by `CHECK`.
- The silence record MUST be written in the **same transaction** as the decision. A silence log
  written afterwards is a reconstruction and MUST NOT be represented as a record.
- Where the vertical's own rules make a class of candidate always blocking — a bonded fatality, for
  instance — the substrate MUST refuse a run that classified one of them as advisory.
- Silence records MUST be append-only and MUST NOT be TTL'd.

---

## MECHANISM

| Role | SQL object |
|---|---|
| conservation | `candidates_conserved` — the partition is exact, by `CHECK` |
| the always-blocking class | `bonded_fatalities_all_blocking` — a `CHECK` over a projected count |
| same transaction | the silence rows are written by the same statement sequence that writes the retrieval result; there is no asynchronous silence writer |
| append-only | `fn_refuse_mutation()` on the silence relations; no TTL |
| the commitment | the silence root is a score-sorted commitment disclosing the root, the threshold, the boundary score and the count — enough to verify the cut without republishing the corpus |

---

## OBSERVABLE

| Attempt | SQLSTATE | Exhibit |
|---|---|---|
| record a retrieval whose partition leaves a remainder | `23514` | `candidates_conserved` |
| classify a bonded fatality as advisory | `23514` | `bonded_fatalities_all_blocking` |
| `UPDATE` or `DELETE` a silence record | `P0001` | `mainline.fn_refuse_mutation` |

---

## CONFORMANCE

| Case | History | SQLSTATE | Exhibit | Profiles | Depth |
|---|---|---|---|---|---|
| [`CF-57`](../conformance/manifest.toml) | A severity-5 event bonded to the permit's activity node, materialised as advisory | `23514` | `bonded_fatalities_all_blocking` | mainline | 1 |
| [`CF-58`](../conformance/manifest.toml) | A recall run whose candidate set is not exactly partitioned into blocking, advisory, silenced and deduped | `23514` | `candidates_conserved` | mainline | 1 |

Generated from [`../conformance/manifest.toml`](../conformance/manifest.toml); the manifest is
authoritative wherever this table disagrees with it.

---

## NOT CLAIMED

- **It does not claim the silence was correct.** It claims the silence is *recorded with its
  arithmetic*, so a reviewer can reconstruct the decision and disagree with it. A system that
  silently declines to surface something and keeps no record is the one this invariant exists to
  forbid.
- **It does not claim every relevant thing was considered.** Only candidates that entered the
  universe can be silenced; what never entered is [`I07`](I07-universe-commitment.md)'s and
  [`I08`](I08-certified-null.md)'s territory.
- **It does not make the log comfortable.** A silence record showing a precursor was scored just
  under threshold before an incident is a damaging document. It ships anyway, because a system that
  deliberately declines to record whether it nearly surfaced the warning is a **worse** exhibit — the
  decision to blind ourselves is itself discoverable, dated and authored.
