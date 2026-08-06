<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: Apache-2.0
-->

# I06 — Derived dependency

> Part of the **TRAPPOINT `1.0.0-rc.1`** public API. Adding an invariant is a MAJOR bump; see
> [`../VERSIONING.md`](../VERSIONING.md).

- **Instantiated by:** the dependency layer; every gate that reads a graph
- **MAINLINE schema invariants that instantiate it:** `MI03`, `MI19`
- **Conformance cases:** 2 (0 on the reference profile)

---

## NORMATIVE STATEMENT

**A dependency edge consumed by a gate MUST be computed, never declared.**

- Where a gate's decision depends on a relationship between two objects — one control depending on
  another, one barrier being independent of another, one document carrying another's clauses — that
  relationship MUST be derived by the substrate from primary facts and MUST NOT be an attribute a
  writer asserts.
- A writer-supplied relationship MAY be stored as a **claim**, distinguishable by type from a derived
  edge, and MUST NOT be readable by a gate.
- Deriving MUST be reproducible: the derivation's inputs, method and version MUST be recorded with
  the edge, so a third party can recompute it.
- An object MUST NOT be able to leave the scope of a gate while a derived edge still binds it — the
  superseding-with-live-dependants case MUST refuse.

---

## MECHANISM

| Role | SQL object |
|---|---|
| the derived edge | the blame / dependency edge relations, written by a projector role and by nobody else |
| type separation | an evidential-basis enumeration distinguishing a derived edge from an asserted one, with the gate reading only derived states |
| the refusal | `no_orphan_controls` — a document cannot be superseded while it still carries a live control series |
| independence | derived from editorial provenance rather than declared: two barriers whose defining clauses descend from one commit are not two barriers, and the substrate stores the descent, not the claim |
| privilege | the projector role holds `INSERT` on the derived relation **and nothing else**; the roles that can write claims cannot write edges |

---

## OBSERVABLE

| Attempt | SQLSTATE | Exhibit |
|---|---|---|
| supersede a document still carrying a live control series | `23514` | `no_orphan_controls` |
| use an asserted (non-derived) edge to arm a gate | `23514` | `inference_never_blocks` |
| write a derived edge as a role that is not the projector | `42501` | `grant:INSERT:<edge relation>:<role>` |

---

## CONFORMANCE

| Case | History | SQLSTATE | Exhibit | Profiles | Depth |
|---|---|---|---|---|---|
| [`CF-49`](../conformance/manifest.toml) | Merge a permit carrying un-dispositioned identity residue | `23514` | `identity_conserved_when_issued` | mainline | 2 |
| [`CF-60`](../conformance/manifest.toml) | Supersede a document that still carries a live control series | `23514` | `no_orphan_controls` | mainline | 1 |

Generated from [`../conformance/manifest.toml`](../conformance/manifest.toml); the manifest is
authoritative wherever this table disagrees with it.

---

## NOT CLAIMED

- **It does not claim the derivation is right.** It claims the gate reads a *computed* relation whose
  method and version are recorded, so a wrong edge is a reproducible wrong edge rather than an
  unfalsifiable assertion.
- **It does not claim declared relationships are useless.** They are often the only thing available.
  They are stored, typed, and kept off the gate.
- **It does not claim completeness of the graph.** A dependency nobody modelled is absent, and this
  invariant is silent about absence — which is why the boundary-certification counter treats an
  unmodelled asset as *unknown and blocking* rather than as safe.
