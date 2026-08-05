# MAINLINE

**Institutional safety memory as a version-controlled repository whose commits are written by incidents.**

Every clause of a procedure, setpoint, isolation standard and critical control carries a **blame pointer to the event that wrote it**. The permit-to-work is a **protected branch**. Its merge is *refused by the database* until every recalled precursor carries a signed disposition.

Recall is not displayed beside the decision. **Recall is a precondition of the decision.**

---

## The one-sentence version

> An engineer raises a routine, entirely defensible change to a compressor alarm setpoint. The system runs `blame` on the clause. It was written 2013-06-12 by an author who left the company in 2017, with the commit message *"Lowered 150 to 135 after seal fire INC-2013-044 — two contractors burned."* The permit merge is mechanically refused until a named competent person signs a disposition against a thirteen-year-old death.

No shipping permit system can express that, because every one of them is **synchronic** — it gates on the current state of the world. MAINLINE is **diachronic**: it gates on *ancestry*.

## Why this is memory, not workflow

The memory is not a panel next to the transaction. It is a **precondition of the state transition**, enforced as a database invariant under `SERIALIZABLE` — not as a UI nag that can be dismissed.

The memory also has *semantics* rather than being a document store:

- **provenance** — clause → the incident that wrote it
- **ancestry** — a commit DAG, walked, not a "related documents" list
- **severity floors** — a fatality's relevance never decays
- **archival bonds** — recall keyed to an activity taxonomy, not to keywords
- **fixity** — as-documented reconciled against as-operated
- **logged silence** — every precursor the system *declined* to surface is recorded, with its arithmetic

## Architecture in one layer diagram

```
verticals/mainline/   ← the product (FSL-1.1-ALv2)
        │  runs on
        ▼
packages/trappoint-*  ← the substrate: a spec, a SQL template, a conformance suite (Apache-2.0)
        │  enforced by
        ▼
CockroachDB v26.2     ← the memory layer. Constraints, triggers, SERIALIZABLE, C-SPANN vectors,
                        changefeeds, RLS. The refusal happens here, not in application code.
```

### TRAPPOINT — the kernel

The substrate is not a library; it is a **specification with a conformance suite**. One idiom, three steps:

> **PROJECT** — a row-level trigger writes the cross-row fact onto a scalar column of the subject row, derived from an authoritative table, *never from the inserter*.
> **PIN** — a completed transition takes a composite foreign key onto `(subject_id, epoch)`; any new obligation increments the epoch; `ON UPDATE RESTRICT` makes attaching an obligation to a completed transition *physically impossible*.
> **REFUSE** — a plain-column `CHECK` over the projected scalar refuses the write, for every writer, forever.

Four properties make it load-bearing:

| Property | Why it matters |
|---|---|
| The projected counter is a **materialised conflict** | The gate stays welded even if isolation is downgraded to `READ COMMITTED` |
| Refusal is **structurally redundant** | Proven by an unwelding harness: disable the trigger, drop the constraint — one at a time — and the write *still* fails |
| The ledger is **gap-free by compare-and-swap, not by sequence** | `CREATE SEQUENCE` is banned, because sequence updates are not rolled back. A gap therefore *means* tampering |
| The gate is **self-attesting** | `pg_get_triggerdef()` is snapshotted into the ledger on every migration. Nobody quietly weakens the gate that prevents quietly weakening controls |

Every refusal emits a **minimal unsatisfiable subset** and, where computable, the nearest admissible alternative. A gate that only says "no" gets routed around — and an invariant that is routed around is not an invariant.

## Repository layout

| Path | Contents | Licence |
|---|---|---|
| `spec/` | TRAPPOINT specification, invariants `I01–I16`, SQLSTATE contract, wire formats | Apache-2.0 |
| `packages/trappoint-*` | Substrate: SQL templates, gate runtime, offline verifier, recall prefix builder, MCP surface, conformance suite | Apache-2.0 |
| `skills/` | CockroachDB Agent Skills, upstream-PR-shaped | Apache-2.0 |
| `verticals/mainline/` | The product: domain lattice, gate service, recall agent, custody relay, console | FSL-1.1-ALv2 |
| `infra/` | OpenTofu modules and environments | FSL-1.1-ALv2 |
| `evidence/reference-ledger/` | A signed fixture any stranger can verify offline | Apache-2.0 |
| `docs/adr/` | Architecture decision records | CC-BY-4.0 |

The import boundaries are enforced by `import-linter` in CI, and they are simultaneously the **layer** boundary, the **licence** boundary, and the **liability** boundary.

## Status

Pre-alpha. Under active construction. Design corpus: `ARCHITECTURE.md` and `BUILD_PLAN.md` in the companion research repository, produced by a 40-agent design operation and hardened by an adversarial review (28 findings) plus an independent feasibility verification.

**Nothing here claims what it cannot prove.** Where a capability is unverified on the target platform, it is listed as unverified. See `docs/HONESTY.md`.

## Licence

Multi-licensed by directory — see the table above, `LICENSES/`, and per-file REUSE headers. `TRADEMARKS.md` governs the names.
