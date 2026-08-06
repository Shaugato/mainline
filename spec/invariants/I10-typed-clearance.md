<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: Apache-2.0
-->

# I10 — Typed clearance

> Part of the **TRAPPOINT `1.0.0-rc.1`** public API. Adding an invariant is a MAJOR bump; see
> [`../VERSIONING.md`](../VERSIONING.md).

- **Instantiated by:** the signature layer; the clearance lattice
- **MAINLINE schema invariants that instantiate it:** `MI11`, `MI25`, `MI29`
- **Conformance cases:** 10 (9 on the reference profile)

---

## NORMATIVE STATEMENT

**The legal set of clearing verdicts MUST be a function of *ancestral* severity, enforced by composite
foreign key against a versioned table.**

- The verdict kind and the projected classification MUST together be a foreign key onto a
  `(classification, kind)` relation. A pair absent from that relation MUST be **non-existent**, not
  flagged.
- The classification MUST be **ancestral** — derived from the lineage of the thing being changed — and
  MUST NOT be the change's own declared risk. A writer MUST NOT be able to lower the required verdict
  set by describing their change as minor.
- The relation MUST be **versioned data with a named approver from the customer's organisation**, not
  code. Contesting a cell MUST be an amendment with a signature, not a pull request.
- Requirements attached to a legal cell — a compensating control, a second signer, a foreign-org
  countersigner, a bounded predicate, a reassertion date, a rank floor, a maximum window — MUST be
  **projected onto the disposition** and enforced by `CHECK`, one named constraint per requirement.
- Where the relation holds **no** row for a pair, the projection trigger MUST project the strictest
  values and let the foreign key fire with its name attached (see [`../errors.md`](../errors.md) §3.3).

---

## MECHANISM

| Role | SQL object |
|---|---|
| the lattice | `fk_clearance` — `FOREIGN KEY (virulence, kind)` onto the versioned clearance relation |
| the classification | projected from the authority source by `fn_disposition_project()`, re-derived from the closure and **never inherited from the obligation row**, so a laundered obligation cannot launder its disposition |
| the requirements | `needs_compensating`, `needs_second_signer`, `needs_foreign_org`, `needs_predicate`, `needs_reassert`, `rank_floor`, `ttl_enforced`, `override_escalates`, `waiver_authority` — one `CHECK` each |
| the deliberate holes | the three absent cells: the two verdicts that would dismiss a fatality-written control, and the one a customer may reasonably contest — versioned, approved, dated |
| the escalation ladder | the override rank floor rises with the person's prior override count, projected across subjects, with no ceiling |

**There is no disposition constructor that dismisses a control written by a fatality.** Signing it is
not a warning and not a flagged event — it is `23503`, for every writer, including a database
administrator and including any managed audit path.

---

## OBSERVABLE

| Attempt | SQLSTATE | Exhibit |
|---|---|---|
| a verdict kind that does not exist at that classification | `23503` | `fk_clearance` |
| a verdict below the classification's rank floor | `23514` | `rank_floor` |
| a verdict missing its required second signer / foreign org / compensating control / predicate / reassertion | `23514` | `needs_second_signer` · `needs_foreign_org` · `needs_compensating` · `needs_predicate` · `needs_reassert` |
| an override that does not escalate | `23514` | `override_escalates` |
| a waiver by a signer without the frozen authorisation | `23514` | `waiver_authority` |

---

## CONFORMANCE

| Case | History | SQLSTATE | Exhibit | Profiles | Depth |
|---|---|---|---|---|---|
| [`CF-07`](../conformance/manifest.toml) | A check claiming virulence='routine', severity=1 on a clause whose closure holds max_severity=5, then a mechanism_absent disposition against it | `23503` | `fk_clearance` | both | 1 |
| [`CF-23`](../conformance/manifest.toml) | accept_residual disposition at virulence blood_major | `23503` | `fk_clearance` | both | 1 |
| [`CF-27`](../conformance/manifest.toml) | Clearance kind requiring a second signer, supplied without one | `23514` | `needs_second_signer` | both | 1 |
| [`CF-28`](../conformance/manifest.toml) | Clearance kind requiring a foreign-org countersigner, countersigned inside the same org | `23514` | `needs_foreign_org` | both | 1 |
| [`CF-29`](../conformance/manifest.toml) | Clearance kind requiring a compensating control, supplied without one | `23514` | `needs_compensating` | both | 1 |
| [`CF-30`](../conformance/manifest.toml) | mechanism_absent disposition with no bounded machine-checkable predicate | `23514` | `needs_predicate` | both | 1 |
| [`CF-32`](../conformance/manifest.toml) | Clearance kind requiring reassertion, supplied with no reassert_by | `23514` | `needs_reassert` | both | 1 |
| [`CF-34`](../conformance/manifest.toml) | Emergency override signed at a rank below 3 + prior_override_count | `23514` | `override_escalates` | both | 1 |
| [`CF-35`](../conformance/manifest.toml) | Waiver at blood_fatal by a signer whose frozen competency snapshot lacks the isolation authorisation | `23514` | `waiver_authority` | mainline | 1 |
| [`CF-71`](../conformance/manifest.toml) | A clearance-lattice refusal names exactly the verdict kinds that DO exist at that virulence | `23503` | `fk_clearance` | both | 1 |

Generated from [`../conformance/manifest.toml`](../conformance/manifest.toml); the manifest is
authoritative wherever this table disagrees with it.

---

## NOT CLAIMED

- **It does not claim the lattice is right.** It is the customer's signed policy, versioned, with an
  approver's name on it. The invariant guarantees it is *enforced and dated*, not that it is wise.
- **It does not claim the classification is right.** That is [`I05`](I05-ancestry-monotone.md)'s and
  the ancestry layer's problem. This invariant guarantees the classification the gate uses is
  *projected*, not declared.
- **It does not claim a legal verdict is a good verdict.** A cell existing means the verdict is
  representable at that severity, not that using it was reasonable in the circumstances.
- **It does not prevent an emergency proceeding.** It prices it: mandatory expiry, escalating rank,
  a countersignature, and a permanent ladder entry. The permit proceeds; the record is loud.
