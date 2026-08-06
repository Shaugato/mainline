<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: Apache-2.0
-->

# I16 — External witness

> Part of the **TRAPPOINT `1.0.0-rc.1`** public API. Adding an invariant is a MAJOR bump; see
> [`../VERSIONING.md`](../VERSIONING.md).

- **Instantiated by:** the custody layer
- **MAINLINE schema invariants that instantiate it:** none in this vertical
- **Conformance cases:** 1 (0 on the reference profile)

---

## NORMATIVE STATEMENT

**No checkpoint MUST be admissible unless cosigned across at least *k* distinct trust domains,
including at least one whose interest is adverse to the operator's.**

- A checkpoint's admissibility MUST be a **projected** flag computed from the cosignatures actually
  received, and MUST NOT be a value any writer supplies.
- Cosignatures MUST record the witness's **trust domain** and whether that domain's interest is
  **adverse**. Two signatures from one domain count once.
- A checkpoint below quorum MUST be representable and MUST be marked **unwitnessed debt** — recorded,
  countable and visible — rather than discarded or silently treated as fine.
- The witness set MUST NOT be selected by the operator on grounds of convenience. Selection MUST be by
  declared adverse interest, and the selection rule MUST be versioned data.
- Admissibility MUST NOT be claimed as split-view resistance until at least one genuinely adverse
  witness is live.

---

## MECHANISM

| Role | SQL object |
|---|---|
| the cosignature record | one row per witness per checkpoint, carrying the trust domain and the adverse flag, primary-keyed so a witness signs a checkpoint once |
| the quorum | `witness_quorum` — a `CHECK` over the projected distinct-domain count and adverse count |
| admissibility is projected | a trigger computes it from the cosignature rows; no writer may set it |
| unwitnessed debt | a below-quorum checkpoint is retained and counted, so the absence of witnessing is itself a measured quantity |
| the anchors either side | a beacon giving a lower time bound and a timestamp token giving an upper one — a checkpoint is thereby bounded in time by two parties who are not us |

---

## OBSERVABLE

| Attempt | SQLSTATE | Exhibit |
|---|---|---|
| mark a checkpoint admissible below quorum, or with no adverse domain | `23514` | `witness_quorum` |
| set the admissibility flag directly | overwritten by projection; the write does not fail, the value does not survive | (see [`I02`](I02-projected-refusal.md)) |

---

## CONFORMANCE

| Case | History | SQLSTATE | Exhibit | Profiles | Depth |
|---|---|---|---|---|---|
| [`CF-67`](../conformance/manifest.toml) | Mark a checkpoint admissible with cosignatures from fewer than k trust domains, or with none adverse | `23514` | `witness_quorum` | mainline | 1 |

Generated from [`../conformance/manifest.toml`](../conformance/manifest.toml); the manifest is
authoritative wherever this table disagrees with it.

---

## NOT CLAIMED

- **It does not claim split-view resistance today.** A quorum of one, over storage the operator
  controls, is **not adverse in the legal sense**, and no material may claim otherwise until a
  genuinely adverse witness is live. This is the invariant most likely to be over-claimed and it is
  written down here so that over-claiming requires editing a normative file.
- **It does not claim the witnesses verified anything.** A cosignature attests that a witness saw a
  checkpoint, not that they audited its contents.
- **It does not claim the log is correct.** Witnessing constrains *consistency across observers*. A
  log that is wrong in the same way for everyone is still wrong, and the ledger's other checks exist
  for that.
- **It does not claim availability.** A witness that stops signing produces unwitnessed debt, which is
  a measured and visible failure — deliberately, because the alternative is a system that quietly
  lowers its own bar when the witness is down.
