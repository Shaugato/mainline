<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: Apache-2.0
-->

# I15 — Allegation firewall

> Part of the **TRAPPOINT `1.0.0-rc.1`** public API. Adding an invariant is a MAJOR bump; see
> [`../VERSIONING.md`](../VERSIONING.md).

- **Instantiated by:** kernel; constrains every layer
- **MAINLINE schema invariants that instantiate it:** none in this vertical
- **Conformance cases:** 2 (0 on the reference profile)

---

## NORMATIVE STATEMENT

**No substrate table MAY store a threshold, score or flag characterising a named human's conduct.**

- The substrate MAY persist **facts about events with names attached**, and **distributions without
  names**. It MUST NOT persist a derived characterisation of a named person's diligence, honesty,
  competence or intent.
- A derived authority level about a named person — *standing* — is representable **if and only if** all
  four of these hold:
  1. it is a **precondition of a state transition the database enforces**, not a report;
  2. it is computed from a **pre-committed, versioned, signed policy that predates the data it
     scores**;
  3. it is **recomputable from primary facts by a third party**;
  4. **the scored person can obtain their own score and its derivation.**
- An identifier of a person MUST be a span attribute, never a metric label: a dimension nobody can
  aggregate on is a dimension nobody can accidentally publish.
- Measurements that could characterise a person MUST be recorded with **neutral polarity and neutral
  names**, and the consequence MUST be named after the system's obligation rather than the person's
  character.
- A refusal payload, an obligation record, a log line and a dashboard MUST all obey this rule. It is
  not a storage rule; it is a rule about what may exist anywhere in the product.

---

## MECHANISM

| Role | SQL object / control |
|---|---|
| the policy precondition | `measure_policy_predates_data` — a standing score computed over data predating the signed policy is not an insertable row |
| the subject's own access | a scoped view returning a person their own record and its derivation |
| partitioning | restrictive policies that blind peers to each other's verdicts until the reader has recorded their own — access control doing epistemics |
| vocabulary | a lint over migrations, telemetry configuration and dashboards: the flag has positive polarity and a neutral name; the consequence is named `countersignature_required`; the pejorative form **does not exist**, in schema or telemetry, ever |
| observing the observer | every read of a per-person view writes a custody entry recording actor, purpose, filter and result digest |
| the wire | the refusal and obligation schemas admit no score field, and their extension objects carry the same prohibition |

---

## OBSERVABLE

| Attempt | SQLSTATE | Exhibit |
|---|---|---|
| insert a standing measurement over data predating the signed policy | `23514` | `measure_policy_predates_data` |
| write outside the single permitted attestation relation as the audit identity | `42501` | `grant:INSERT:<relation>:<audit role>` |
| a migration, dashboard or collector introducing a pejorative per-person field | build failure (lint), not a runtime code |

The last row is deliberate: this invariant is enforced partly by the build, because a field that must
never exist cannot be caught by a constraint on a table that should not have it.

---

## CONFORMANCE

| Case | History | SQLSTATE | Exhibit | Profiles | Depth |
|---|---|---|---|---|---|
| [`CF-68`](../conformance/manifest.toml) | Compute a standing measurement over data predating the customer-signed measurement policy | `23514` | `measure_policy_predates_data` | mainline | 1 |
| [`CF-69`](../conformance/manifest.toml) | The audit identity attempts to write outside its single permitted attestation table | `42501` | `grant:INSERT:mainline.disposition:mainline_auditor` | mainline | 1 |

Generated from [`../conformance/manifest.toml`](../conformance/manifest.toml); the manifest is
authoritative wherever this table disagrees with it.

---

## NOT CLAIMED

- **It does not claim the system is kind to individuals.** It records uncomfortable facts — whether
  evidence was opened, how long a decision took, how many overrides a person has signed. It refuses to
  turn those facts into a *characterisation*. The distinction is the whole invariant.
- **It does not claim per-person data is unobtainable in litigation.** It is discoverable. What the
  design buys is that it arrives with a signed record of who looked, when, and why — which is the
  difference between surveillance and a quality-assurance programme a court can see.
- **It does not claim compliance with any particular privacy statute.** That is a legal opinion about
  a deployment, not a property of a schema.
- **It does not claim the measurement is fair.** It requires the measurement to be pre-committed,
  recomputable, and visible to its subject. Fairness is argued from those three properties; it is not
  supplied by them.
