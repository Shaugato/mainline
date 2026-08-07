<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: Apache-2.0
-->

# The ledger schema — normative addendum for the datamodel lead

**Normative for `verticals/mainline/db/migrations/0072–0079`.** The custody domain
**specifies** this schema; the datamodel lead **implements** it. Migrations have exactly one
owner, and a second writer would break the lock-file discipline — so what lives here is the
requirement and its justification, and `scripts/custody/check_chain_fn_matches_spec.py`
plus the conformance suite are what make the specification executable rather than advisory.

Base DDL is ARCHITECTURE.md §5.6. This document carries **the additions and constraints
custody requires on top of it**, each with the attack it exists to refuse.

---

## 1. CU-1 — `ledger_leaf` gains a linearity CAS

```sql
-- ADDITIONS to mainline.ledger_leaf as specified in ARCHITECTURE.md §5.6
ALTER TABLE mainline.ledger_leaf
  ADD COLUMN prev_link_hash BYTES NOT NULL;

ALTER TABLE mainline.ledger_leaf
  ADD CONSTRAINT ledger_linear UNIQUE (site_code, prev_link_hash);
```

**Genesis is 32 zero bytes** (`'\x0000…00'::BYTES`, 32 of them), so `seq = 0` is not a
special case in any reader and the constraint applies uniformly from the first leaf.

### Why

This is the architecture's own `UNIQUE (permit_id, prev_seq)` compare-and-swap idiom,
transplanted from the gate to the ledger. It buys three things:

1. **Refusal depth 2 on append.** Two concurrent appenders collide on the primary key
   `(site_code, seq)` *and* on `ledger_linear`. Drop either one and the write still fails.
   The ledger is thereby held to the same standard the kernel holds the gate to, and the
   unwelding suite can prove it one constraint at a time.
2. **A fork becomes physically impossible**, not merely unlikely, even under a hypothetical
   primary-key bypass and even at READ COMMITTED. Two leaves cannot both claim the same
   predecessor.
3. **`prev_link_hash` becomes readable data**, so the verifier's chain recomputation
   (check 9) reads the claimed predecessor rather than inferring it from `seq` — which
   matters precisely in the case where `seq` has been tampered with (attack **A2**).

`link_hash` remains `SHA-256(prev_link_hash ‖ leaf_hash)`, so `prev_link_hash` is
redundant-by-derivation and load-bearing-by-constraint. Redundancy that a constraint reads
is not duplication; it is the only way to make the relationship enforceable by the database
rather than by the writer.

### What it does not buy

A T1 adversary drops the constraint. This is refusal depth, not tamper-evidence; the
tamper-evidence is the checkpoint that already left the building.

---

## 2. `seq` derivation — CU-2

```sql
-- NORMATIVE: seq is derived inside the appending transaction.
--   seq := COALESCE((SELECT max(seq) FROM mainline.ledger_leaf WHERE site_code = $1), -1) + 1
```

**`CREATE SEQUENCE`, `nextval`, `SERIAL` and `unique_rowid()` are banned repository-wide**,
and the ledger is the reason the ban is not merely stylistic:

> Sequence increments **survive rollback**. A ledger numbered by a sequence has legitimate
> gaps, so a gap means nothing. A ledger numbered by in-transaction compare-and-swap has no
> legitimate gaps, so **a gap MEANS tampering** — and that sentence is verifier check 9.

The resulting `23505` on `ledger_leaf_pkey` or `ledger_linear` is **the only retryable
`23505` in the repository**. The sequencer's retry loop matches on **constraint name**,
never on SQLSTATE, is bounded at 8 attempts, and is asserted by a test that a `23505` on any
other constraint **escapes** the loop. Otherwise the one legitimate retry becomes a laundry
for real refusals, which would be a far worse defect than the contention it exists to
absorb.

---

## 3. Append-only, and the one exception

Every table below is in `fn_refuse_mutation`'s list: `UPDATE` and `DELETE` raise `P0001`.

```
ledger_intake · ledger_leaf · ledger_node · ledger_checkpoint · cosignature
custodian_attestation · destruction_record
```

There is **no exception** for any `ledger_*` table. Not for a correction, not for a
migration, not for an operator with a good reason. A checkpoint found to be defective is
answered by a **new** entry recording the defect; repairing history to make verification
pass is precisely the behaviour this product exists to detect, and a mechanism that permits
it under any flag will eventually be used under that flag.

`unwitnessed_debt.discharged_tree_size` is the single exception in the custody surface: it
is `NULL` until a retro-cosigned checkpoint discharges the debt, and its `UPDATE` is
permitted **only** on that column, only from `NULL`, and only to a `tree_size` that exists
in `ledger_checkpoint`. Discharge is a fact about the world arriving late, not a rewrite of
what was recorded.

---

## 4. Sequenced-ness is derived, never written

```sql
SELECT i.* FROM mainline.ledger_intake i
 WHERE i.site_code = $1
   AND NOT EXISTS (SELECT 1 FROM mainline.ledger_leaf l
                    WHERE l.site_code = i.site_code AND l.entry_id = i.entry_id)
 ORDER BY i.hlc, i.entry_id
 LIMIT $2;                                        -- B <= 2048
```

**There is no `sequenced` flag and there must never be one.** Sequenced-ness is an
anti-join. The consequence is that the entire ledger write path is `INSERT` + `SELECT`,
which is why the `mainline_ledger` role holds exactly those grants and why the Managed MCP
server's insert-only write surface is a genuine structural match rather than a coincidence
we oversell.

`UNIQUE (site_code, entry_id)` on `ledger_leaf` makes replaying a batch a no-op, so the
sequencer is idempotent without holding any lock — which matters because **CockroachDB has
no advisory locks**.

---

## 5. `hlc` is advisory, and the column says so

`crdb_internal.cluster_logical_timestamp()` returns the transaction's **provisional**
timestamp, which can be pushed before commit (cockroach#79591). `ledger_intake.hlc` is
therefore an **ordering hint only**; the authoritative order is the sequencer's `seq`.

No constraint, no check and no proof may read `hlc`. The column comment must say so, and
any query that orders by `hlc` outside the batch-selection above is a defect.

---

## 6. Canonicalisation is client-side — the loud warning

**Do not compute `leaf_hash` in SQL.** CockroachDB's `sha256()` returns a hex *string*, not
`BYTES` (cockroach#73896), and `JSONB` normalises and reorders keys — so
`sha256(payload::STRING)` is not reproducible by a third party.

```
canon_bytes  BYTES NOT NULL   -- RFC 8785 JCS bytes, produced by the CLIENT, stored verbatim
payload_ver  INT2  NOT NULL   -- which canonicaliser; the verifier dispatches on it
leaf_hash    BYTES NOT NULL   -- SHA-256(0x00 || canon_bytes)   [RFC 6962 §2.1]
```

Store the **exact bytes hashed**, alongside the parsed `payload JSONB` for humans. The two
are permitted to be compared and are never permitted to be conflated: a verifier hashes
`canon_bytes` and reports a discrepancy if `payload` disagrees, which is how attack **A3**
surfaces as a legible finding rather than as nothing.

`payload_ver` is a foreign key in spirit to `spec/custody/canon-registry.yaml`. Every
canonicaliser ever shipped is retained forever.

---

## 7. Grants

| Role | On | Grants |
|---|---|---|
| `mainline_ledger` | `ledger_intake`, `ledger_leaf`, `ledger_node`, `ledger_checkpoint`, `cosignature` | `INSERT`, `SELECT` — **never** `UPDATE`, `DELETE` |
| `agent_projector` | `clause_blame_closure` | `INSERT` only, and nothing else anywhere |
| everyone else | every `ledger_*` table | `SELECT` at most |

The `agent_projector` row is here rather than in the datamodel domain because it closes
adversarial-review finding **S2**: the closure projector's Lambda execution role is the
least-protected identity in the architecture, and it was implicitly able to `UPDATE` the
one table every ancestry gate reads.

**Every closure write also emits a `ledger_intake` row** (`entry_kind = 'closure'`, payload
`(clause_uuid, as_of_commit, closure_gen, max_severity, ancestor_count, truncated)`) **in
the same transaction**. That costs one `INSERT` and is what makes verifier check 14
possible at all — without it, a mass closure rewrite is invisible to anyone outside the
database.

---

## 8. Row-level TTL

**No `ledger_*` table may carry a row-level TTL, ever.** The TTL allowlist is a three-table
list and none of them is in this document. `tests/integration/custody/test_k2_exit.py::
test_no_ttl_on_ledger` reads the live schema and fails if that changes.

Silent expiry of an evidentiary row is document destruction performed by a scheduler, which
is worse than document destruction performed by a person, because nobody decided to do it.

---

## 9. What the datamodel lead owns

Everything above is implemented in `verticals/mainline/db/migrations/**`, which is the
datamodel lead's exclusive territory. Custody supplies:

- this document (the requirement),
- [`chain-verification.md`](chain-verification.md) (the normative PL/pgSQL body for `fn_permit_event_chain`),
- `scripts/custody/check_chain_fn_matches_spec.py` (the executable conformance check),
- `trappoint_migrate.attest.LedgerSink` (the real implementation against their Protocol).

A spec with an executable conformance check is stronger than a duplicated migration file,
and it does not fight over a lock file.

---

## References

- ARCHITECTURE.md §5.6, §5.11 item 9, §7.2, §16 (MI01, MI24)
- `docs/leads/custody.md` §2 CU-1, CU-2
- cockroach#73896 (`sha256` returns a string), cockroach#79591 (provisional commit timestamp)
- [`chain-verification.md`](chain-verification.md), [`attacks.yaml`](attacks.yaml) A1, A2, A3, A6, A10
