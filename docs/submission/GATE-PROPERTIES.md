<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# Four properties of the gate, and what we measured about each

`README.md` explains the gate in three steps — PROJECT, PIN, REFUSE. This page holds the claims
underneath it that a reviewer is entitled to press on. Each one names what was measured, not what
was intended, and two of them record a result weaker than we hoped for.

---

## 0 · What the trigger actually did, in the committed run

One blocking check was inserted, **with no other statement between the readings either side** —
which is what makes the before-and-after comparison mean anything.

| reading | before | after |
|---|---|---|
| `open_blocking` on the permit row | `0` | `1` |
| `gate_epoch` | `0` | `1` |
| rows of kind `check_opened` in `mainline_ops.outbox` — the changefeed table other systems subscribe to | — | `1` |
| severity on that row | client supplied `0` | database projected `4` |

Ten of ten assertions held
[src: `evidence/gate-refusal/proof-20260816T151248Z.json#projection`].

**A counter a client writes is a client's opinion; a counter a trigger writes is the database's.**

---

## 0b · One refusal in this demo is the application's, and we do not round it up

A signer setting an obligation aside must give a reason code. **The database does not check that
the code was ever offered.** `0066_disposition.sql` declares that column `NOT NULL` and non-empty
and adds no foreign key onto the table of offered codes. Python closes the gap — the function
`resolve_defeater_vocabulary` raises — and it is written down here rather than papered over
[src: `docs/submission/MUST-NOT-CLAIM.md` §14].

---

## 1 · The counter is a *materialised conflict*

Two transactions touching the projected counter collide instead of interleaving. That keeps the
gate welded even if the isolation level drops to `READ COMMITTED` — a weaker mode in which two
transactions can each read a value the other is in the middle of changing. That is the design.

**What we did not measure.** The conformance case that would exercise it, `CF-45`, is recorded
`cannot_run` in `qa/conformance-census.json`, and `spec/invariants/I02-projected-refusal.md`
states that drift *detection* is weaker there.

## 2 · Refusal is not structurally redundant, and we measured that instead of assuming it

An unwelding harness removes one mechanism at a time and replays the identical illegal history.
**Nine of nine merge-gate histories came back at depth 1** — one mechanism refuses each
[src: `packages/trappoint-conformance/REFUSAL_DEPTH.md`].

That is deliberate. The gate declines to raise while the projected counter agrees with the
re-derivation, so the named `CHECK` stays the exhibit. But the file's own verdict on a depth of
one is *cut the mechanism, do not ship it*, and we have left that verdict standing rather than
softening it.

## 3 · The ledger is gap-free by compare-and-swap, not by sequence

A **compare-and-swap** write names the value it expects to find and fails if it finds anything
else, so two writers cannot both think they won.

`CREATE SEQUENCE`, `nextval` and `unique_rowid()` are banned repository-wide, because a
sequence's increment is **not** rolled back with its transaction — so a sequence-numbered ledger
grows gaps in normal operation and a gap tells you nothing. Here a gap *means* tampering
[src: `docs/adr/0045-cas-sequencing-not-sequences.md`].

## 4 · The gate is self-attesting

`pg_get_triggerdef()` and `pg_get_functiondef()` are CockroachDB functions that return the
source text of a trigger or a routine. We snapshot the gate's own source through them into the
migration attestation, so weakening the gate moves a recorded digest.

**Against a cluster administrator this is tamper-evidence, not prevention**
[src: `packages/trappoint-migrate/src/trappoint_migrate/attest.py`]. Row-level security here —
the database restricting which rows a login can see — is tenancy and least privilege, and is not
a defence against `root`.
