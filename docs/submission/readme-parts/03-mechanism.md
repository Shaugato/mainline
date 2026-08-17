## How it works

A **`CHECK` constraint** is a rule the database applies to every write, from every client, with no way to
ask it nicely. Application code can be patched, bypassed or forgotten; a `CHECK` cannot. So the design is
one move: take a fact that lives across many rows, write it as a number on the row being written, and put
a `CHECK` on that number. Every shipping permit system is **synchronic** — it gates on the current state
of the world. This one is **diachronic**: it gates on *blame ancestry*, the chain of past events that
wrote the rule. Three steps, each stated plainly and then precisely.

**PROJECT.** When an obligation appears, the database itself writes onto the permit how many are
outstanding. An *obligation* is a lesson a past incident left behind that someone must sign off; a
*projection* is that cross-row fact copied onto a plain column of the subject row. A row-level trigger
derives it from an authoritative table, never from whoever is writing, and overwrites any supplied value
unconditionally, so a correct guess confers no privilege [src: spec/invariants/I02-projected-refusal.md].

**PIN.** Once a permit is merged, nobody can quietly attach a new obligation to it. An *epoch* is a counter
that ticks every time a new obligation lands. The merge record takes a composite foreign key onto
`(subject_id, gate_epoch)`, declared `ON UPDATE RESTRICT ON DELETE RESTRICT`, which makes attaching an
obligation to a completed transition physically impossible rather than merely disallowed [src: spec/invariants/I03-epoch-pin.md].

**REFUSE.** The merge is then refused by the constraint, for every writer, forever. A plain-column `CHECK`
named `gate_closed_when_issued` reads `(state != 'merged') OR (open_blocking = 0)`. It raises SQLSTATE
`23514` — the five-character code the SQL standard gives a violated `CHECK` — and names itself in the error text [src: evidence/gate-refusal/proof-20260816T151248Z.json#refusal].

| The property | What was measured |
|---|---|
| The counter is a **materialised conflict** | Two transactions touching it collide instead of interleaving, which keeps the gate welded if isolation drops to `READ COMMITTED`. That is the design. The case that would exercise it, `CF-45`, is recorded `cannot_run` in `qa/conformance-census.json`, and `I02` states that drift *detection* is weaker there. |
| Refusal is **not** structurally redundant, and we measured that instead of assuming it | An unwelding harness removes one mechanism at a time and replays the identical illegal history. Nine of nine merge-gate histories came back at **depth 1** — one mechanism refuses each [src: packages/trappoint-conformance/REFUSAL_DEPTH.md]. That is deliberate: the gate declines to raise while the projected counter agrees with the re-derivation, so the named `CHECK` stays the exhibit. The file's own verdict on a depth of one is *cut the mechanism, do not ship it*. |
| The ledger is **gap-free by compare-and-swap**, not by sequence | `CREATE SEQUENCE`, `nextval` and `unique_rowid()` are banned repository-wide: a sequence's increment is not rolled back with its transaction. A gap therefore *means* tampering rather than a discarded number [src: docs/adr/0045-cas-sequencing-not-sequences.md]. |
| The gate is **self-attesting** | `pg_get_triggerdef()` and `pg_get_functiondef()` snapshot the gate's own source into the migration attestation, so weakening it moves a recorded digest [src: packages/trappoint-migrate/src/trappoint_migrate/attest.py]. Against a cluster administrator the claim is tamper-*evidence*, not prevention. Row-level security here is tenancy and least privilege, not a defence against `root`. |

**The attack we run against our own gate.** `just prove` does not stop at the refusal above. It forces `open_blocking`
to zero out of band — the exact tampering a `CHECK` alone cannot catch, since `(open_blocking = 0)` is now satisfied —
and attempts the merge again. It is refused anyway, `P0001` from `mainline.fn_permit_merge_gate`: *re-derived open
obligation count is 1 while the projected counter reads zero* [src: evidence/gate-refusal/proof-20260816T151248Z.json#drift_refusal].
The function re-derives the count from the base tables rather than trusting the column. **Projections are enforced,
never trusted.** Both refusals are then ledgered and read back, each naming the smallest unmet obligation set that explains it.

**What the trigger actually did, in the committed run.** One blocking check was inserted, with no other statement
between the readings either side. `open_blocking` went 0 → 1, `gate_epoch` 0 → 1, and one row of kind `check_opened`
landed in `mainline_ops.outbox` — the changefeed table other systems subscribe to. Severity **4** was projected onto a
row where the client supplied **0**, and ten of ten assertions held [src: evidence/gate-refusal/proof-20260816T151248Z.json#projection].
A counter a client writes is a client's opinion; a counter a trigger writes is the database's.

**One refusal in this demo is the application's, and we will not round it up.** A signer setting an
obligation aside must give a reason code. The database does not check that the code was ever offered:
`0066_disposition.sql` declares that column `NOT NULL` and non-empty, and adds no foreign key onto the
table of offered codes. Python closes the gap, by `resolve_defeater_vocabulary` raising, and it is written
down rather than papered over [src: docs/submission/MUST-NOT-CLAIM.md §14].

```
verticals/mainline/    the product (LicenseRef-FSL-1.1-ALv2)                                    ── runs on ──▼
packages/trappoint-*   the substrate — a spec, a SQL template, a conformance suite (Apache-2.0) ── enforced by ──▼
CockroachDB v26.2.5    constraints, triggers, SERIALIZABLE, changefeeds, RLS. The refusal happens here, not above it.
```
