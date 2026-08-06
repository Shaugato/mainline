<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: Apache-2.0
-->

# I03 — Epoch pin

> Part of the **TRAPPOINT `1.0.0-rc.1`** public API. Adding an invariant is a MAJOR bump; see
> [`../VERSIONING.md`](../VERSIONING.md).

- **Instantiated by:** kernel; every completed transition
- **MAINLINE schema invariants that instantiate it:** `MI07`
- **Conformance cases:** 2 (2 on the reference profile)

---

## NORMATIVE STATEMENT

**A completed transition MUST pin the subject's epoch by composite foreign key, and any new
obligation MUST bump that epoch.**

- Every gated subject MUST carry a non-decreasing integer `gate_epoch` and MUST expose
  `UNIQUE (subject_id, gate_epoch)` as a foreign-key target.
- Materialising an obligation MUST increment `gate_epoch` in the same transaction. Retracting a
  disposition MUST increment it. Revoking a disposition's bounded predicate MUST increment it.
- The completion record MUST hold `FOREIGN KEY (subject_id, gate_epoch)` declared
  **`ON UPDATE RESTRICT ON DELETE RESTRICT`**. `CASCADE` MUST NOT appear in either position: a
  cascade rewrites history, which is the precise offence this substrate exists to detect.
- Consequently, attaching an obligation to a completed subject MUST be **impossible**, not merely
  forbidden — the write fails on referential integrity before any policy is consulted.
- The declared remedy MUST be a **fork**: suspend the completed subject and open a child whose gate
  is cleared afresh. A binding MUST NOT provide a path that re-opens a completed subject.

---

## MECHANISM

| Role | SQL object |
|---|---|
| the pin | `epoch_pin_permit` / `epoch_pin_cr` — composite FK from the completion record onto `(subject_id, gate_epoch)`, `ON UPDATE RESTRICT ON DELETE RESTRICT` |
| the FK target | `UNIQUE (permit_id, gate_epoch)` / `UNIQUE (cr_id, gate_epoch)` on the subject |
| the bump | `fn_check_materialised()` — `open_blocking + 1` **and** `gate_epoch + 1`, in one statement |
| the retraction bump | `fn_disposition_retract_only()` — same two increments |
| the deterministic refusal | `fn_check_materialised()` raises `P0001` when the subject is already complete, so the observable is a sentence rather than a race between two structural refusals |

Once the completion record references `(subject_id, e)`, the database refuses **any** update that
changes `gate_epoch` — and every new obligation must change it. That is branch discipline expressed
as referential integrity: never rewrite a merged commit, open a revert branch.

---

## OBSERVABLE

| Attempt | SQLSTATE | Exhibit |
|---|---|---|
| materialise an obligation against a completed subject | `P0001` | `mainline.fn_check_materialised` |
| retract a disposition after the subject completed | `23503` | `epoch_pin_permit` |
| directly `UPDATE` a completed subject's `gate_epoch` | `23503` | `epoch_pin_permit` |
| delete a completed subject that a completion record pins | `23503` | `epoch_pin_permit` |

At runtime the deterministic `P0001` fires first, by construction. The *structural* refusals behind
it — the counter's `CHECK` on a completed row and the pinned-epoch foreign key — are proved by the
unwelding harness, never asserted from a log.

---

## CONFORMANCE

| Case | History | SQLSTATE | Exhibit | Profiles | Depth |
|---|---|---|---|---|---|
| [`CF-10`](../conformance/manifest.toml) | Materialise a blocking check against an already-merged permit | `P0001` | `mainline.fn_check_materialised` | both | 3 |
| [`CF-40`](../conformance/manifest.toml) | Retract a disposition after the permit has merged | `23503` | `epoch_pin_permit` | both | 2 |

Generated from [`../conformance/manifest.toml`](../conformance/manifest.toml); the manifest is
authoritative wherever this table disagrees with it.

---

## NOT CLAIMED

- **It does not prevent the fact from arriving.** A precursor discovered after completion is real and
  the world does not care about our foreign keys. The invariant makes the *record* honest: the fact
  cannot be back-fitted into a closed transition, and the only representable response is a new,
  dated, gated child subject.
- **It does not close the operational window.** Between the discovery and the crew being told, people
  are still working. That is an operations SLA, not a database property, and no schema retires it.
- **It does not claim serializability solves this.** It cannot: a fact arriving after commit is not a
  serialization anomaly, and `SERIALIZABLE` provably does not address it. The pin is a *structural*
  answer to an anomaly isolation cannot reach, which is why it exists at all.
- **It does not claim the epoch is a clock.** It counts obligation events, not time, and two subjects'
  epochs are not comparable.
