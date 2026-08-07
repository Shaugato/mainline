---
name: designing-vector-recall-prefixes
description: Design and verify prefix-constrained vector indexes on CockroachDB. Use when adding a VECTOR INDEX with prefix columns, when choosing what those prefix columns should be, when an ANN query is slower than expected or returns unexpected neighbours, or when you must prove from EXPLAIN that a vector index is genuinely being used. Covers the rule that every prefix column must be constrained to a specific value, how prefix cardinality sets K-means tree size and therefore recall quality, the optimizer_span_limit cliff behind IN-list filtering, and the three independent checks — plan text, latency scaling, and result correctness — that together establish index use. Includes a standalone script that asserts the EXPLAIN fragment for any table.
license: Apache-2.0
---

<!-- SPDX-FileCopyrightText: 2026 MAINLINE contributors -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Designing vector recall prefixes

## The one rule that decides everything

> **A vector index is used only if EACH prefix column is constrained to a specific value.**

`WHERE department_id = 100 AND category_id = 200` uses the index.
`WHERE department_id = 100 AND category_id >= 200` **does not**. Not "uses it less
efficiently" — does not use it. The query still returns correct rows, by scanning.

And the prefix does more than filter. CockroachDB's C-SPANN implementation maintains a
**separate K-means tree per distinct prefix value**, so the prefix columns select *which tree
is searched*. Two consequences follow immediately, and they are the reason this skill exists:

1. **Prefix cardinality sets tree size, and tree size sets whether ANN is worth doing.** A
   prefix over 2 000 distinct values on 1 000 000 rows gives ~500 vectors per tree, where
   approximate search buys nothing over a scan. A prefix with 5 distinct values on the same
   table gives 200 000 per tree, where it buys everything.
2. **The prefix is a correctness surface, not a performance knob.** A row written under the
   wrong prefix value is not ranked lower. It is in a different tree, so no constrained query
   will ever reach it — with no error and no row anywhere that looks wrong.

## Choosing prefix columns

Work through these in order.

**1. What is always known at query time?** A prefix column that the query cannot bind to a
literal is worse than no prefix column: it makes every query a scan. If your application
sometimes searches across tenants, `tenant_id` cannot be your only prefix design — you need a
second, unprefixed (or differently-prefixed) index for that access path, and you should say so
explicitly rather than discover it.

**2. What is the *stable* partition?** Prefix values are baked into the physical index.
Changing what a prefix value means — re-classifying rows, renumbering categories — means
rewriting trees. Prefer a dimension that changes on the timescale of schema migrations, not on
the timescale of data.

**3. What cardinality does that give you, at your row count?** Aim for trees large enough that
approximate search is doing real work. Compute it: `rows ÷ distinct prefix values`. If the
answer is in the hundreds, either coarsen the prefix or accept that you have built a filtered
scan with extra machinery.

**4. Do you need more than one partitioning of the same data?** If different queries want
different scopes — narrow and precise for one, broad and forgiving for another — the answer is
usually **two indexes**, or two tables, not one clever prefix. One narrow-prefix index for the
scoped lookup, plus one deliberately *unpartitioned* index (a single constant prefix column,
one big tree) as a fallback for the case where the scoping attribute is wrong or missing. The
second index is cheap insurance against a mis-classified row being unreachable forever.

**5. Who writes the prefix columns?** If any client can choose them, any client can choose
which rows are reachable. Where that matters, derive the prefix columns with a `BEFORE INSERT`
trigger from an authoritative parent row, and make the trigger raise when that parent is
missing. A column that decides reachability should not be an input.

## Querying: one constrained query per scope, unioned

When you need to search several scopes at once, the portable shape is a `UNION ALL` of
**fully-constrained** branches, each with its own `LIMIT`:

```sql
SELECT * FROM (
    (SELECT id, embedding <-> $1 AS dist
       FROM items
      WHERE tenant_id = '…' AND category_id = 'tools'
      ORDER BY embedding <-> $1 LIMIT 12)
  UNION ALL
    (SELECT id, embedding <-> $2 AS dist
       FROM items
      WHERE tenant_id = '…' AND category_id = 'hardware'
      ORDER BY embedding <-> $2 LIMIT 12)
) hits;
```

Note the parentheses around each branch: without them, `ORDER BY … LIMIT` binds to the whole
union and each branch loses its own budget.

**The alternative is tuple-`IN`, and it is supported:**

```sql
WHERE (department_id, category_id) IN ((100, 200), (300, 400))
```

Prefer `UNION ALL` anyway when any of the following is true — and if none of them is, tuple-`IN`
is simpler and you should use it:

* **the branches are not homogeneous.** Different `k` per scope, different weights when you
  fuse the results, or a different query vector per scope. A single `IN` returns one
  undifferentiated top-k and throws that structure away.
* **the set of scopes grows.** `optimizer_span_limit` bounds how many spans the optimizer will
  build for a constrained scan. Past it, the `IN` set stops being used to build a constrained
  index scan — **silently**. See `references/cspann-prefix-rules.md`.
* **you have to prove index use per scope.** `EXPLAIN` on a `UNION ALL` shows one vector
  search node per branch, each with its own prefix spans. That is directly assertable.

Whichever you choose, decide it on evidence and re-check it after upgrades. Behaviour here has
changed across versions.

## Proving it — three independent checks

Do all three. None of them substitutes for another.

### 1. Plan text

```
• vector search
  table: items@items_customer_id_embedding_idx
  target count: 3
  prefix spans: [/1 - /1]
```

Four things must hold:

* a `vector search` node exists;
* its `table:` line names the index you meant;
* `prefix spans` is present **and non-empty**;
* **no node anywhere in the plan is a full scan.** A plan can contain a real vector search and
  a full scan side by side when a predicate could not be pushed into the prefix. An assertion
  that stops at "does the plan mention vector search" passes that plan.

Run `scripts/assert_prefix_index_used.py` in CI rather than eyeballing it:

```bash
python scripts/assert_prefix_index_used.py --self-test          # prove the check can fail
python scripts/assert_prefix_index_used.py --dsn "$DSN" \
       --index items@items_customer_id_embedding_idx \
       --statement "SELECT id FROM items WHERE customer_id = 1
                    ORDER BY embedding <-> '[…]' LIMIT 10"
```

### 2. Latency scaling

**A silently unused index scales linearly regardless of how the plan text is formatted.**
Measure p50 latency at n, 2n and 4n rows and require the ratio to stay well under 2.0 — 1.7 is
a useful ceiling because a scan cannot pass it while a tree search is nowhere near it. Take the
median of three runs; one run measures the machine's mood.

Run the same measurement against a deliberately unindexed variant (`@{FORCE_INDEX=[1]}` forces
the primary index by ID, which survives primary-index renames). If the two curves look the
same, your harness cannot tell them apart and the plan-text check is the only evidence you
actually have.

### 3. Result correctness

Plant a row whose vector is deliberately near a known query, and assert it comes back in
top-k at every size. A plan can be perfect while the executor returns neighbours you did not
expect — approximate search is approximate, and `vector_search_beam_size` (default 32) trades
recall against latency. If you tune that, re-run this check; that is what it is for.

## Writing data

* **Declare the vector index at `CREATE TABLE` time, on an empty table.** Creating one on a
  populated table backfills and blocks writes until it finishes.
* **`IMPORT INTO` is not supported on a table with a vector index.** The documented remedy is
  import-then-index — which means the bulk path runs *before* the index exists, and therefore
  before any trigger that derives the prefix columns. If your prefix columns are a correctness
  surface, stage into an index-free mirror table and promote with `INSERT … SELECT` instead, so
  every row still passes the same trigger.
* **Large batch inserts of `VECTOR` degrade**, and the guidance is that batching should be
  avoided. That is a direction, not a number. **Measure your own knee** — largest batch still
  delivering ≥80 % of peak throughput — and put *that* in the loader. A batch size chosen from
  a sentence in the docs is an invented threshold.

## Pitfalls, ranked by how quietly they fail

| Pitfall | How it shows up |
|---|---|
| A prefix column left unbound, or bound with a range | Correct results, linear latency, no error. The index is simply not used. |
| An `IN` set that grew past `optimizer_span_limit` | Same as above, and it appears at a row count nobody was watching. |
| A second vector index the optimizer prefers | `vector search` present, on the wrong index, searching different trees. |
| A full scan beside a legitimate vector search | The plan looks right if you only grep for `vector search`. |
| Prefix cardinality too high | Tiny trees; ANN slower and less accurate than a filtered scan. |
| Prefix columns written by the client | Rows land in trees nobody queries. Unreachable, forever, silently. |
| Asserting `target count == LIMIT` | Undocumented equality. Report it; do not require it without having observed it on your version. |

## Reference

`references/cspann-prefix-rules.md` — the prefix rule, tree-per-prefix-value mechanics and how
to size them, the `optimizer_span_limit` cliff, the ingest constraints, and the exact `EXPLAIN`
fragments to assert.
