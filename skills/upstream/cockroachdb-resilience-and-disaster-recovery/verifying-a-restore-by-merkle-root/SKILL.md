---
name: verifying-a-restore-by-merkle-root
description: Proves that a restored CockroachDB table reproduces a Merkle root committed before the backup was taken, so a restore is verified rather than assumed. Use when a restore drill must produce evidence rather than a green job status, when an append-only or hash-chained table has to be shown to have survived backup and restore intact, when deciding what a disaster-recovery runbook should record so a future restore can be checked at all, or when a restored table must be compared against a root held outside the cluster. Covers canonical row encoding, domain-separated Merkle construction, binding the chain height and head hash so truncation at the head cannot pass, bisecting to the first divergent row, and the interaction between row-level TTL, garbage collection and a lineage a root commits to.
compatibility: Requires CockroachDB v22.2 or later for RESTORE and SHOW BACKUP as used here, a table whose rows can be enumerated in a deterministic order, and Python 3.10 or later to run the bundled script. The script uses only the standard library.
metadata:
  author: shaugato
  version: "1.0"
---

# Verifying a restore by Merkle root

A restore job that reports success has told you that bytes moved. It has not told you that
the rows you needed are the rows you got. For an audit trail, an evidence table, a
transaction log or any append-only record, the difference matters: the failure mode that
hurts is not a corrupt file, it is a **quietly shorter table** that reads perfectly.

The remedy is to commit to the table's contents *before* the backup, in a value held
somewhere the cluster cannot reach, and to recompute that value from the restored rows.

## How to Apply this Skill

Apply it in two phases, and treat the first as part of ordinary operation rather than part
of the drill.

**Before the backup — commit.** Compute a Merkle root over the table in a fixed order,
together with the row count and the last row's hash, and write that triple somewhere outside
the cluster: object storage under a retention lock, a signed file in a separate account, a
transparency log. This is the only step with a deadline. A root computed after a restore is
evidence of nothing.

**After the restore — verify.** Recompute the same three values from the restored table and
require all three to match, byte for byte. On a mismatch, bisect to the first divergent row
and report it, because *"the roots differ"* is not an actionable finding and *"row 41 208
onward differs, the first one is this"* is.

Run the bundled script's self-test first, on any machine, with no database:

```bash
python scripts/verify_restore_merkle_root.py --self-test
```

It proves the checker detects a truncated tail, a tampered row and a reordering — and it
demonstrates the failure this skill exists to prevent: a chain whose links all verify while
rows are missing from the end.

## Prerequisites

- A table with a **deterministic total order** over its rows. A primary key is enough; a
  monotonic sequence column is better because it also lets you detect gaps.
- A **canonical encoding** for a row: fixed column order, explicit types, no dependence on
  JSON key order, locale, timezone rendering or floating-point formatting. Two runs of the
  verifier on the same data must produce identical bytes, on different machines and different
  library versions.
- Somewhere **outside the cluster** to hold the committed triple, that the credentials used
  by the cluster cannot overwrite.
- Read access to the restored table, ideally from a machine with **no write access to
  anything**.
- `cockroach sql` or any PostgreSQL client, and Python 3.10+ for the script.

## Step 1 — Commit to the table before the backup

Compute the triple and store it externally:

```bash
cockroach sql --url "$DSN" --format=tsv \
  --execute "SELECT id, ts, payload FROM audit_log ORDER BY id" \
  | python scripts/verify_restore_merkle_root.py \
      --emit-checkpoint --tsv - --segment 1024 --label 'audit_log @ 2026-08-10' \
  > checkpoint.json
```

Record alongside it the cluster timestamp the computation describes, so a future verifier
knows which backup it applies to:

```sql
SELECT cluster_logical_timestamp();
```

Take the backup at or after that timestamp. If you compute the root from a historical read
instead, use an explicit timestamp and keep it:

```sql
SELECT id, payload FROM audit_log AS OF SYSTEM TIME '2026-08-10 04:00:00'
 ORDER BY id;
```

Note the constraint that decides your options here: `AS OF SYSTEM TIME` can only read as far
back as the garbage-collection window for the zone, which is `gc.ttlseconds` and is commonly
hours, not months. It is a tool for reading a few hours ago, not for reconstructing last
quarter. Anything you may need to prove later must be committed to at the time.

## Step 2 — Enumerate the restored rows in the same order

```sql
SELECT id, ts, payload FROM audit_log ORDER BY id;
```

`ORDER BY` is not optional and no default order exists. Rows come back in whatever order the
plan produced them, which changes with the plan, and a Merkle root is order-sensitive by
construction — that is most of its value.

For a large table, stream it. The script reads a TSV stream on standard input so nothing is
materialised twice:

```bash
cockroach sql --url "$DSN" --format=tsv \
  --execute "SELECT id, ts, payload FROM audit_log ORDER BY id" \
  | python scripts/verify_restore_merkle_root.py --checkpoint checkpoint.json --tsv -
```

## Step 3 — Encode each row canonically, then hash it

The leaf hash is over an encoding you control, not over anything a driver chose for you.
The script's default encoding joins the columns of a row with a byte that cannot occur in
the values and length-prefixes each field, so that `("ab", "c")` and `("a", "bc")` cannot
collide. If you write your own, keep that property: **field boundaries must be recoverable
from the bytes.**

Rules that repay the effort:

- render timestamps in one explicit format at one explicit precision, in UTC;
- render `NULL` as a value distinct from an empty string;
- never hash a `JSONB` column's rendered text without a canonical form — key order is not
  guaranteed to survive a restore, and neither is whitespace.

## Step 4 — Build the root with domain separation

```
leaf(x)        = SHA-256(0x00 || x)
node(l, r)     = SHA-256(0x01 || l || r)
odd node       promoted unchanged to the next level, never duplicated
empty tree     SHA-256(0x02)
```

The prefixes matter. Without them, an internal node's digest is indistinguishable from a
leaf's, and a tree can be reinterpreted as a different tree with the same root. Promoting an
odd node rather than duplicating it matters for the same reason: **duplicating the last node
lets two different row sets produce the same root**, which is a well-known Merkle
construction flaw and is straightforward to hit with a table whose length changes.

## Step 5 — Compare all three values, not just the root

```bash
python scripts/verify_restore_merkle_root.py \
    --checkpoint checkpoint.json --tsv rows.tsv
```

The script requires `root`, `height` (the row count) and `head` (the hash of the last leaf)
to match. Requiring the root alone is enough in theory and is a trap in practice: the moment
anybody "optimises" the verifier to walk a `prev_hash` chain forward instead of rebuilding
the tree, a truncated table starts passing. Every remaining link is valid. Nothing is
inconsistent. The rows are simply not there.

`--self-test` demonstrates exactly that case rather than describing it.

## Step 6 — Bisect on mismatch

A root alone can only say *different*. To say *where*, the checkpoint has to carry
intermediate roots — one per block of rows — which costs a few kilobytes and is the
difference between a finding and a shrug. `--emit-checkpoint --segment 1024` writes them;
the verifier then reports the first divergent block:

```
root    MISMATCH expected 9f2c… observed 4ab1…
height  MISMATCH expected 41208 observed 41190 (18 row(s) short)
head    MISMATCH expected 7d81… observed 0c44…
        first divergent segment 40: rows 40960.. are ABSENT
```

Use it to answer the operational question, which is never "is it different" but "what is
missing, from where, and does the gap line up with anything".

A tail-only difference means truncation — usually a backup that raced the writers, or a
retention policy that deleted rows the root commits to. A difference in the middle with
matching height means a row changed. A difference at index 0 usually means the encoding
differs, not the data: check the canonicalisation before concluding anything about the
restore.

## Step 7 — Bind the verification to the backup it claims

Record which backup was restored, so the evidence is not merely "some restore reproduced the
root":

```sql
SHOW BACKUP FROM LATEST IN 's3://…' AS OF SYSTEM TIME '2026-08-10 04:00:00';
```

Keep the backup's identity, the restore job's id, the checkpoint's identity and the verifier's
output together. Any one of them alone is an assertion; together they are a record.

## Safety Considerations

- **A chain verified only forward misses truncation at the head.** Walking `prev_hash`
  links from the genesis row proves every surviving link is intact and proves nothing about
  the rows that are gone from the end — every check passes and the table is short. This is
  the most likely silent failure in this whole procedure. Always bind the **height** and the
  **head hash**, and prefer rebuilding the tree over walking the chain.
- **A TTL policy can garbage-collect a lineage the root commits to.** Row-level TTL deletes
  rows on a schedule. If a table under TTL is also under a committed root, verification will
  fail later for a reason nobody remembers configuring — and if the *restored* cluster still
  carries the TTL storage parameters, the restore re-arms the same deletion against the
  restored rows. Decide explicitly which tables are evidence and exempt them, and re-check
  the TTL settings on the restored table, not only on the source.
- **Never read the expected root from the restored cluster.** A root fetched from the same
  system you are verifying makes the check circular: anything that could rewrite the rows
  could rewrite the root. Fetch it from the external store, over a path the cluster's
  credentials cannot write.
- **Do not duplicate the last node in an odd Merkle level.** Two different row sets can then
  produce the same root, so a passing verification stops meaning what it appears to mean.
- **`AS OF SYSTEM TIME` cannot reach past the garbage-collection window.** It is not a
  substitute for having committed to the data at the time, and a runbook that assumes
  otherwise fails at the moment it is needed.
- **Verify from a machine with no write credentials**, and treat the verifier as something
  an outside party could run. If verification requires privileges only your team holds, the
  result is a claim about your team rather than about the data.
- **A restore into a live cluster is destructive.** Restore into a scratch database or a
  scratch cluster for verification. `RESTORE` can overwrite a table, and a verification drill
  that destroys the thing it was verifying is a bad afternoon.

## Supporting Documentation

- [`RESTORE`](https://www.cockroachlabs.com/docs/stable/restore)
- [`BACKUP`](https://www.cockroachlabs.com/docs/stable/backup)
- [`SHOW BACKUP`](https://www.cockroachlabs.com/docs/stable/show-backup)
- [Backup Validation](https://www.cockroachlabs.com/docs/stable/backup-validation)
- [`AS OF SYSTEM TIME`](https://www.cockroachlabs.com/docs/stable/as-of-system-time)
- [Batch Delete Expired Data with Row-Level TTL](https://www.cockroachlabs.com/docs/stable/row-level-ttl)
- [Configure Replication Zones — `gc.ttlseconds`](https://www.cockroachlabs.com/docs/stable/configure-replication-zones)
- [Disaster Recovery Overview](https://www.cockroachlabs.com/docs/stable/disaster-recovery-overview)
