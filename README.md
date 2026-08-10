<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# MAINLINE

**Institutional safety memory as a version-controlled repository whose commits are written by incidents.**

Every clause of a procedure, setpoint, isolation standard and critical control carries a **blame pointer to the event that wrote it**. The permit-to-work is a **protected branch**. Its merge is *refused by the database* until every recalled precursor carries a signed disposition.

Recall is not displayed beside the decision. **Recall is a precondition of the decision.**

---

## Four commands, no account, no credential

```bash
just doctor     # what is missing, and the exact command that fixes it
just setup      # installs uv if absent, then `uv sync --all-packages`
just up         # one CockroachDB node, pinned, aligned with Cloud's gc.ttlseconds
just prove      # the database refuses a permit merge, and says why
```

`just prove` bootstraps a throwaway database, applies the migration chain, and attempts
the same merge three times. This is what it printed on the run committed under
[`evidence/gate-refusal/`](evidence/gate-refusal/):

```
REFUSAL       REFUSED [23514] gate_closed_when_issued (reported)
DRIFT         REFUSED [P0001] mainline.fn_permit_merge_gate (parsed)
ADMISSION     ADMITTED [00000]
VERDICT       PROVEN
```

Three attempts, and the third is the one that matters. A gate that always refuses is a
broken gate, not a safe one. The first refusal is a plain `CHECK` constraint. The second
is the gate catching a *forged projection* — the counter was set to zero out of band and
the merge was refused anyway, because the function re-derives the count instead of
trusting the column. The third is the same history admitted after one signed disposition.

No `just`? `python scripts/qa/doctor.py` and
`python scripts/proof/gate_refusal.py --dsn …` need nothing but the interpreter.
[`docs/release/QUICKSTART.md`](docs/release/QUICKSTART.md) is the long version.

## Read this before you believe any of it

**[`docs/HONESTY.md`](docs/HONESTY.md)** — what is proven, what is synthetic, what is not
built, and where the machine is. Every number in it carries an inline reference to the
file under `qa/` or `evidence/` that produced it, and
`tests/release/test_honesty_is_checkable.py` fails the build when a number and its source
disagree. The short version, because it should not be buried:

* Five tables in the schema have **no migration at all** — their triggers, views and RLS
  policies were written and their producer never was. The chain applies **246 of 261**
  files; the fifteen that fail are enumerated, by file and SQLSTATE, in the evidence JSON.
* **The conformance suite has not been demonstrated.** Against a bare node its cases
  error rather than skip, and the census never migrated one. The case bodies exist; the
  results do not.
* The corpus is **authored**, the model transcripts are **recorded cassettes**, and the
  reference-ledger keys are named `NOT-SECRET` because they are.
* The test suite is censused **per package, twice** — with no database and with one shared
  node — and every skip is published with the reason string its own fixture wrote. The
  counts, including the target that does not finish at all, are in
  [`qa/test-state.json`](qa/test-state.json).
* Inference runs on **Bedrock in `ap-southeast-2` (Sydney)** while the database is in
  **`aws-ap-southeast-1` (Singapore)**. There is no end-to-end Australian residency, the
  cross-region hop is unmeasured under load, and **every timing in the demo is a local
  timing**.

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

The second line of `just prove` is that claim under attack rather than at rest:
`mainline.fn_permit_merge_gate` is handed a projected counter that says zero, re-derives
the obligation count for itself, finds one, and refuses with `P0001`. **P2 projections are
enforced, never trusted.**

## Repository layout

| Path | Contents | Licence |
|---|---|---|
| `spec/` | TRAPPOINT specification, invariants `I01–I16`, SQLSTATE contract, wire formats | Apache-2.0 |
| `packages/trappoint-*` | Substrate: SQL templates, gate runtime, offline verifier, recall prefix builder, MCP surface, conformance suite | Apache-2.0 |
| `skills/` | CockroachDB Agent Skills, upstream-PR-shaped | Apache-2.0 |
| `verticals/mainline/` | The product: domain lattice, gate service, recall agent, custody relay, console | FSL-1.1-ALv2 |
| `infra/` | OpenTofu modules and environments | FSL-1.1-ALv2 |
| `evidence/reference-ledger/` | A signed fixture any stranger can verify offline | Apache-2.0 |
| `qa/` | The counted ratchets and the test census — every number, and the command that re-derives it | CC-BY-4.0 |
| `docs/adr/` | Architecture decision records | CC-BY-4.0 |

The import boundaries are enforced by `import-linter` in CI, and they are simultaneously the **layer** boundary, the **licence** boundary, and the **liability** boundary.

## Verifying without trusting us

[`VERIFY.md`](VERIFY.md) is the three tiers, ordered by how much you have to take on
faith. Tier 2 — clone, `just up`, `just prove` — needs no account of ours and no model
call, and it is the one that reproduces the refusal above on your laptop.

Two artefacts are worth opening on their own:

* [`evidence/gate-refusal/`](evidence/gate-refusal/) — a transcript of what one cluster
  did at one instant, with the SQLSTATE, the constraint name, the migration failures it
  could not repair, and the caveats the run could not honestly avoid.
* [`qa/test-state.json`](qa/test-state.json) — passed, failed, errored and skipped per
  package, **with every skip's reason string**, taken twice: once with no database
  available and once against a live node. Rendered as
  [`docs/release/test-state.md`](docs/release/test-state.md).

## Status

Pre-alpha. Under active construction. Design corpus: `ARCHITECTURE.md` and `BUILD_PLAN.md` in the companion research repository, produced by a 40-agent design operation and hardened by an adversarial review (28 findings) plus an independent feasibility verification.

**Nothing here claims what it cannot prove**, and the claims that are not proven are
listed by name in [`docs/HONESTY.md`](docs/HONESTY.md) rather than left out.

## Licence

Multi-licensed by directory — see the table above, `LICENSES/`, and per-file REUSE headers. `TRADEMARKS.md` governs the names.
