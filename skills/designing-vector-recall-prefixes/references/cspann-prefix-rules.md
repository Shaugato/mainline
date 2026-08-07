<!-- SPDX-FileCopyrightText: 2026 MAINLINE contributors -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# C-SPANN prefix rules — the mechanics behind the guidance

Everything in `SKILL.md` follows from four facts about how CockroachDB's distributed vector
index works. This file states them, says what each one implies, and marks clearly which
statements are documented and which are inference or measurement.

---

## 1. A vector index is used only if EACH prefix column is constrained to a specific value

**Documented.** The vector-index documentation gives the rule and both sides of it:

* uses the index — `WHERE department_id = 100 AND category_id = 200`
* **does not** use the index — `WHERE department_id = 100 AND category_id >= 200`

**What it implies.** "Constrained to a specific value" is a plan-time property. Equality
against a literal qualifies. A range, an inequality, a `LIKE`, a function of another column, or
simply omitting the column does not — and the query still succeeds, by scanning. There is no
error and no warning. In any system where "this row was not returned" is a meaningful outcome,
this is the failure to design against first.

**Multi-value filtering** is supported with tuple `IN`:

```sql
WHERE (department_id, category_id) IN ((100, 200), (300, 400))
```

See §3 for why that is not automatically the right answer.

---

## 2. There is a separate K-means tree per distinct prefix value

**Documented behaviour of the index design** (Cockroach Labs' distributed vector indexing and
C-SPANN write-ups). The prefix does not filter a result set produced by one big search; it
selects the structure that gets searched.

**Three implications, in the order they bite:**

**(a) Prefix cardinality sets tree size.**

```
vectors per tree  ≈  total rows ÷ distinct prefix-value combinations
```

Work it out before choosing a prefix, not after:

| rows | distinct prefix values | vectors/tree | verdict |
|---|---|---|---|
| 1 000 000 | 5 | 200 000 | approximate search is doing real work |
| 1 000 000 | 200 | 5 000 | reasonable |
| 1 000 000 | 2 000 | 500 | ANN is pointless here; you built a filtered scan |
| 1 000 000 | 100 000 | 10 | strictly worse than a secondary index on the prefix |

There is no single correct number, but the direction is not a matter of taste: below roughly a
few thousand vectors per tree, the approximation stops paying for itself, and you should either
coarsen the prefix or stop using a vector index for that access path.

**(b) A composite prefix multiplies.** `(tenant, category, kind)` has cardinality
`|tenant| × |category| × |kind|` *as they co-occur* — which is usually far less than the
product, and is worth measuring rather than estimating:

```sql
SELECT count(*) FROM (SELECT DISTINCT tenant_id, category_id, kind FROM items);
SELECT count(*) / (SELECT count(*) FROM (SELECT DISTINCT tenant_id, category_id, kind FROM items))
  AS approx_vectors_per_tree FROM items;
```

**(c) Writing the prefix is choosing reachability.** A row written under prefix value `X` is
reachable only by queries that bind the prefix to `X`. If a client supplies the prefix columns,
a client can make a row unreachable — and nothing about that row will look wrong. Where that
consequence matters, derive the prefix columns in a `BEFORE INSERT` trigger from an
authoritative parent row and raise when the parent is absent. The check that matters is not
"are the values valid" but "who chose them".

**(d) Deliberately unpartitioned indexes are a legitimate design.** A single constant prefix
column gives you exactly one tree. That is the right shape when the index's job is to be a
fallback for rows whose scoping attribute is wrong or missing — one big tree, no partitioning,
searched without a scope. Pairing a narrow-prefix index with a single-tree fallback index costs
storage and buys coverage of your own classification errors.

---

## 3. `optimizer_span_limit` is a silent cliff

**Documented, v25.4+.** The session variable bounds how many spans the optimizer will build for
a single constrained index scan:

* *if a single `IN` set has more items than this limit, that `IN` set will not be used to build
  a constrained index scan*;
* for a composite index, *if the cross product of two or more `IN` sets would produce more
  spans than this limit, then only a prefix of the `IN` sets will be used to produce spans*.

**What it implies.** A query that used the index at 8 scopes can stop using it at 40, at a
threshold nobody is watching, with no error. The degradation is to a scan: correct results,
linear cost.

**How to handle it, in order of preference:**

1. **Read the value at runtime — never assume the default.**

   ```sql
   SHOW optimizer_span_limit;
   ```

   The setting is version-dependent. A test that hard-codes a value characterises its own
   assumption.

2. **Bound the number of scopes you query at once**, and make the overflow *visible* — a log
   line, a counter, a recorded record — rather than silently dropping scopes.

3. **Prefer `UNION ALL` of individually-constrained branches** when the branch count is not
   small and fixed. Per-branch spans are one each, per-branch `EXPLAIN` is assertable, and
   nothing about the shape degrades as the branch count grows (though the plan does get large:
   assert branches individually if your tooling has a response-size limit).

4. **If you use tuple-`IN`, characterise it on your version**, at span counts either side of
   the runtime limit, against a brute-force oracle. Expect the answer to change across
   upgrades; that is the reason to have the test rather than a reason not to.

**Undocumented and worth measuring yourself:** whether tuple-`IN` combined with
`ORDER BY distance LIMIT k` yields a global top-k across the matched trees or a top-k per tree.
Per-branch `LIMIT` in a `UNION ALL` has no such ambiguity.

---

## 4. Ingest constraints are design inputs, not operational trivia

**Documented:**

* **`IMPORT INTO` is not supported on tables with vector indexes.** The remedy given is
  import-then-index.
* **Large batch inserts of `VECTOR` types can cause performance degradation**; the guidance is
  that batching should be avoided.
* **Creating a vector index on a populated table** backfills, and blocks mutations while it
  does. Declaring the index at `CREATE TABLE` time on an empty table avoids this.

**What it implies.**

Import-then-index means the bulk load happens *before* the index exists — and therefore before
anything that depends on the index, including any trigger you wrote to derive the prefix
columns from an authoritative source. If your prefix columns are a correctness surface (§2c),
import-then-index is the one path that bypasses the guard. The alternative that preserves it:

```sql
-- Stage into an index-free mirror (bulk-loadable), then promote in batches.
INSERT INTO live_table (id, prefix_a, prefix_b, embedding)
SELECT s.id, s.prefix_a, s.prefix_b, s.embedding
  FROM stage_table s
 WHERE s.id > $1
 ORDER BY s.id
 LIMIT 500;
```

The promotion is an `INSERT`, so every row passes the same trigger the single-row path does.
Staging becomes a throughput decision rather than a hole in the guard.

**"Batching should be avoided" is a direction, not a number.** Measure the knee on your own
cluster — sweep batch size across at least three orders of magnitude, at fixed row count, and
take the **largest batch still delivering ≥80 % of peak throughput**. Put that number in the
loader with a comment naming the measurement. Anything else is an invented threshold.

---

## 5. The `EXPLAIN` fragments to assert

**Documented shape:**

```
• vector search
  table: items@items_customer_id_embedding_idx
  target count: 3
  prefix spans: [/1 - /1]
```

Assert **four** things (`scripts/assert_prefix_index_used.py` implements all four):

| Check | Failure it catches |
|---|---|
| a `vector search` node exists | the optimizer chose a scan |
| `table:` names the expected `table@index` | a second vector index is being preferred |
| `prefix spans` present and **non-empty** | a prefix column was not constrained |
| **no** `spans: FULL SCAN` anywhere in the plan | a predicate that could not be pushed reappeared as a scan beside the vector search |

**Do not require `target count == LIMIT` unless you have observed it on your version.** The
documented example shows them equal; whether the count is ever inflated to serve re-ranking is
not documented. Report the value, and turn the equality into a requirement only on evidence.

**Two renderings exist.** CockroachDB prints plans flat for shallow plans and with
`│ ├── └──` glyphs for deeper ones. A parser that handles only the flat form reports zero
nodes for every nested plan — which looks exactly like "the index was not used". Handle both,
and make "no nodes parsed" a distinct, loud error rather than a negative verdict.

**`EXPLAIN ANALYZE` is not needed** and is unavailable on some managed surfaces. The claim
being established is *which plan the optimizer chose*, which plain `EXPLAIN` answers without
executing anything.

---

## 6. What plan text does not prove

Plan text says what was planned. It does not say what the executor did, and it says nothing
about whether an approximate search returned the neighbours that mattered. Two further checks
close that gap, and both are cheap:

* **latency scaling** — p50 across a doubling corpus, median of three runs; a scan doubles, a
  tree search barely moves. Run the same measurement against a forced primary-index scan to
  confirm your harness can tell the two apart at all.
* **planted-neighbour recall** — a row written deliberately close to a known query must come
  back in top-k. `vector_search_beam_size` (default 32) trades recall for latency; if you tune
  it, this is the check that tells you what it cost.

There is **no bit-identical replay of an approximate search**. The trees mutate on every
insert. If you need to be able to justify a result later, persist the returned candidates and
their scores — not merely the parameters that produced them.

---

## Sources

* CockroachDB — Vector Indexes: <https://www.cockroachlabs.com/docs/stable/vector-indexes>
  (prefix-constraint rule, tuple-`IN` syntax, the `EXPLAIN` example, `vector_search_beam_size`,
  `IMPORT INTO` and batch-insert limitations)
* CockroachDB — What's New in v25.4: <https://www.cockroachlabs.com/docs/releases/v25.4>
  (`optimizer_span_limit`)
* Cockroach Labs — Distributed vector indexing in CockroachDB:
  <https://www.cockroachlabs.com/blog/distributed-vector-indexing-cockroachdb/>
* Cockroach Labs — C-SPANN: real-time indexing of billions of vectors:
  <https://www.cockroachlabs.com/blog/cspann-real-time-indexing-billions-vectors/>

Sizing tables, the ≥80 %-of-peak knee rule and the 1.7 latency-ratio ceiling are **our
heuristics**, offered as starting points with the method for deriving your own — not as
documented platform behaviour.
