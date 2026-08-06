<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: Apache-2.0
-->

# I14 — Minimal refusal

> Part of the **TRAPPOINT `1.0.0-rc.1`** public API. Adding an invariant is a MAJOR bump; see
> [`../VERSIONING.md`](../VERSIONING.md).

- **Instantiated by:** kernel; every refusal
- **MAINLINE schema invariants that instantiate it:** `MI02`, `MI11`
- **Conformance cases:** 2 (2 on the reference profile)

---

## NORMATIVE STATEMENT

**Every refusal MUST emit an irreducible reason set and, where computable, the nearest admissible
alternative.**

- The reason set MUST be a **minimal unsatisfiable subset**: remove any one element and the transition
  would have been admissible. A superset labelled as a MUS is non-conformant.
- The reason set MUST be drawn from the modelled fact families — an open obligation, a cited clause, a
  precursor event, an authority gap, a capability gap — and MUST NOT contain free prose in place of a
  fact.
- Where minimality cannot be established within the diagnosis budget, the emitter MUST say so —
  diagnosis `none`, alternative `null`, reason `probe_budget_exhausted` — rather than emit an
  unproven set.
- The nearest admissible alternative MUST be the **minimum-cardinality** change to the attempted
  history that restores admissibility, or explicitly `null` with a reason from a closed set.
- The diagnosis MUST be produced by the **same constraint engine that produced the refusal**, so that
  the explanation cannot disagree with the refusal.
- The diagnosis MUST NOT be able to mutate the gate: it runs in a separate transaction, rolled back
  unconditionally, never on the completion path.
- A refusal MUST be attempted **exactly once**. A retried refusal writes duplicate diagnoses and
  destroys the meaning of the refusal record.

---

## MECHANISM

| Role | SQL object |
|---|---|
| declarative decomposition | primary, deterministic, no probe: the refused constraint maps to its counter, and the counter's witness rows *are* the MUS |
| the alternative | the minimum-cardinality set of obligations whose disposition restores admissibility; for a lattice refusal, the verdict kinds that **do** exist at that classification |
| one round trip | `trappoint.explain_refusal(subject_kind, subject_id, constraint_name)` returning the payload as JSON, so the diagnosis is a single statement and is plan-assertable |
| the general algorithm | QuickXplain over savepoint probes, with the database as the oracle: `SAVEPOINT p; <apply subset>; <attempt>; ROLLBACK TO SAVEPOINT p` |
| safety | separate transaction, unconditional rollback in a `finally`, bounded oracle budget, never on the completion path |
| the record | an append-only refusal ledger storing the constraint name **verbatim**, because the constraint name is the exhibit |
| the wire form | [`../wire/refusal.schema.json`](../wire/refusal.schema.json) |

Extracting a minimal unsatisfiable subset is a solved problem *with a solver*. Using the database's
own constraint engine as the oracle — so the explanation is produced by the mechanism that produced
the refusal — is the part that makes the explanation trustworthy rather than merely plausible.

---

## OBSERVABLE

| Attempt | SQLSTATE | Exhibit | Payload |
|---|---|---|---|
| complete with three obligations, two dispositioned | `23514` | `gate_closed_when_issued` | `mus` names exactly the one open obligation; `naa.kind = dispose_obligations`, `cardinality = 1` |
| a verdict kind absent from the lattice | `23503` | `fk_clearance` | `naa.kind = substitute_kind`, listing exactly the kinds present at that classification |
| a verdict absent at the highest classification | `23503` | `fk_clearance` | `naa = null`, `naa_reason = no_legal_verdict_exists` |
| a composite refusal beyond the budget | any | the refusing constraint | `diagnosis = none`, `naa = null`, `naa_reason = probe_budget_exhausted` |

Every payload validates against the wire schema, and the conformance runner asserts minimality rather
than mere presence.

---

## CONFORMANCE

| Case | History | SQLSTATE | Exhibit | Profiles | Depth |
|---|---|---|---|---|---|
| [`CF-70`](../conformance/manifest.toml) | A permit refused with three obligations of which two are already dispositioned emits a MUS naming exactly the third | `23514` | `gate_closed_when_issued` | both | 2 |
| [`CF-71`](../conformance/manifest.toml) | A clearance-lattice refusal names exactly the verdict kinds that DO exist at that virulence | `23503` | `fk_clearance` | both | 1 |

Generated from [`../conformance/manifest.toml`](../conformance/manifest.toml); the manifest is
authoritative wherever this table disagrees with it.

---

## NOT CLAIMED

- **It does not claim the alternative is advice worth taking.** The nearest admissible alternative is
  the smallest change that restores admissibility, which is often *not* the right thing to do. It
  makes the refusal navigable; it does not make it optional. Acting on it still goes through the gate.
- **It does not claim the MUS is the cause.** It is the irreducible set of *modelled facts* whose
  joint presence produced the refusal. Causation in the world is a different question.
- **`no_legal_verdict_exists` is not a diagnoser failure.** It is the product working: at that
  ancestral severity there is no way to sign this away. A consumer that renders it as an error has
  misunderstood the system.
- **It does not claim a refusal is never routed around.** A determined organisation can open a
  different subject, or not use the system. It claims the refusal is *explained*, which is what
  removes the most common and most reasonable motive for routing around it.
