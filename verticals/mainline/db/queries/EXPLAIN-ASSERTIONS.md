<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: FSL-1.1-ALv2
-->

# EXPLAIN assertions — the blame closure

**Owner:** `datamodel/dm-blame`, band `0032`–`0039z`.
**Subjects:** `queries/closure_write.sql`, `queries/closure_read.sql`, and the two indexes
migration `0038` declares.
**Asserted by:** `tests/integration/schema/test_mi_blame.py`, cluster tier.
**Measured against:** CockroachDB CCL **v26.2.5** (`cockroachdb/cockroach:latest-v26.2`, build tag
`v26.2.5`, built 2026-07-28), single node, on **2026-08-10**, after applying the 62 migrations
numbered at or below `0036` plus this band. Every fragment below is **copied from that run**, not
predicted.

A projection whose cost is unbounded is a projection that stops running, and a gate that reads a
projection that stopped running fails closed on every permit in the fleet. So the plans below are
not documentation of what we hope happens. Each one is either **asserted in CI**, or **explicitly
recorded as measured-but-not-asserted, with the reason**. There is no third category.

Fragments are quoted in the shape CockroachDB's `EXPLAIN` actually prints — `table:
relation@index` on one line, `spans: …` on the next — because that is the shape the test's parser
reads. A plan assertion written against prettified output breaks on a formatting change and
passes on a regression.

---

## 0. What "asserted" means here, and the one platform ruling that shapes it

Platform ground truth **F1** (`docs/adr/0002-g1-platform-ground-truth.md`) found that at
demo-corpus scale the optimizer will not choose a *vector* index unless it is named explicitly,
and ruled that every ANN arm pins its index. The same *engineering* argument — not the same
measurement — applies to any plan sitting beneath a safety gate: **a plan that flips on table
statistics must not be the thing a refusal depends on.**

**F1's `IN (...)` trap does not apply to anything in this file.** It is a constraint on vector
index *prefix columns*. `cbc_anc` is an inverted (GIN) index and `cbc_sev` is an ordinary
secondary index; neither has a prefix-column rule of that kind. Recorded because generalising a
vector-index rule to every index is an easy and expensive mistake.

**Measured, and worth knowing:** on this build the containment predicate chooses `cbc_anc`
**without a hint**, on an empty-statistics table. CI still asserts the **hinted** form. That is
not superstition: the unhinted choice is the optimizer's estimate under `missing stats`, and an
assertion that depends on an estimate is an assertion that changes meaning after the first
`ANALYZE`. Pinning asserts our index; not pinning asserts their costing.

---

## 1. `closure_write.sql` — the recursive walk

The whole statement plans as a `root` with four `subquery` buffers (`anc`, `uniq`, `kept`, and
two scalar aggregates), an `insert`, and a `constraint-check`. Four fragments in it matter.

### 1.1 Base case — `mainline.blame_edge`

```sql
WHERE b.clause_uuid = $1 AND b.commit_id = $2 AND b.state = 'active'
```

`0037` declares `INDEX by_clause_commit (clause_uuid, commit_id, state)` for exactly this. All
three columns are equality-constrained and in index order. Measured:

```
• recursive cte
  └── • render
      └── • scan
            table: blame_edge@by_clause_commit
            spans: [/'…clause_uuid…'/'\x…commit…'/'active' - /'…clause_uuid…'/'\x…commit…'/'active']
```

**ASSERTED.** `test_the_closure_writer_seeks_its_base_case` fails on `blame_edge@blame_edge_pk`
(the primary index — correct but wider: it range-scans every edge of the clause and then filters
two columns) and fails outright on `FULL SCAN`. Without `by_clause_commit` the plan is *correct*
and gets slowly worse as a clause accumulates bases and commits. That is the failure mode a plan
assertion exists to catch: not wrongness, drift.

### 1.2 Recursion — `mainline.event_edge`

```sql
JOIN mainline.event_edge AS e ON e.child_event_id = a.event_id
```

`child_event_id` leads `event_edge_pk (child_event_id, parent_event_id, relation)`, so the join
is a seek against the primary index.

**MEASURED AS NOT INSPECTABLE, AND THEREFORE NOT ASSERTED.** CockroachDB's `EXPLAIN` renders a
`recursive cte` node showing only its **initial** term; the recursive term does not appear in the
plan at all. So there is no fragment to assert, and a test that claimed to assert one would be
asserting nothing. What guards this path instead is structural and is stated where it is enforced:
the join column is the primary-key prefix (`0034`), the walk is bounded at `depth < 64`
(`closure_write.sql`), and `no_self_edge` (`0034`) removes the cheapest way to burn that bound.
`0034`'s `INDEX up (parent_event_id, child_event_id)` serves the opposite direction — descendants,
for the console — and is not on this path.

### 1.3 Severity lookup — `mainline.event`

```sql
WHERE ev.event_id IN (SELECT a.event_id FROM anc AS a)
```

Measured:

```
• lookup join
  table: event@event_pk
  equality: (event_id) = (event_id)
  equality cols are key
  └── • distinct
        distinct on: event_id
```

**ASSERTED as "not a full scan".** A full scan here means the optimizer decided the `IN` list was
large enough to prefer reading every event — legitimate at high cardinality, a red flag at the
1–20 ancestors this system actually sees.

### 1.4 Generation lookup — through the view

```sql
FROM mainline.clause_blame_current AS c WHERE c.clause_uuid = $1 AND c.as_of_commit = $2
```

Both columns are the leading two of `clause_blame_closure_pk (clause_uuid, as_of_commit,
closure_gen)` **and** they are the entire `DISTINCT ON` list. Measured — and better than
predicted, because the optimizer recognises that and drops the de-duplication node entirely:

```
• revscan
  table: clause_blame_closure@clause_blame_closure_pk
  spans: [/'…clause_uuid…'/'\x…commit…'/0 - /'…clause_uuid…'/'\x…commit…']
  limit: 1
```

A reverse scan with `limit: 1`. **ASSERTED as "not a full scan".** This is why `closure_gen` is
derived inside the writer rather than passed by the caller: the discipline costs one seek, so the
P2 argument for deriving it is free.

### 1.5 The composite FK

Measured, at the tail of the writer's plan:

```
• constraint-check
  └── • error if rows
      └── • lookup join (anti)
            table: clause_version@cv_clause_commit_unique
            equality: (?column?, ?column?) = (clause_uuid, commit_id)
            equality cols are key
```

`fk_version` resolving against `0029`'s `cv_clause_commit_unique` as an anti-join. Not asserted —
it is the FK doing exactly what an FK does — but recorded, because it is the visible proof that a
closure cannot be recorded for a clause text that was never committed.

### 1.6 One index recommendation, deliberately not taken

The run emitted:

```
index recommendations: 1
1. type: index creation
   SQL command: CREATE INDEX ON mainline.clause_version (commit_id) STORING (site_id);
```

**Not taken, and not this band's to take.** `mainline.clause_version` is `dm-spine`'s (`0029`),
and the writer's own lookup on it is already a seek (§1.5) because `(clause_uuid, commit_id)` is
unique. The recommendation is for the *other* direction — "every clause touched by this commit" —
which is a real question the fleet sweep asks and a real index somebody may want. Recorded here
rather than acted on: an index added from inside another band is exactly the collision this
repository already had once.

---

## 2. `closure_read.sql` — the containment lookup, and where §5.4 overstates

### 2.1 The claim as written in ARCHITECTURE

> *"Which clauses inherit incident E?"* is then one index lookup:
> ```sql
> SELECT clause_uuid FROM mainline.clause_blame_current
>  WHERE site_id = $1 AND ancestor_events @> ARRAY[$2::UUID];
> ```

### 2.2 What is actually true, measured, and why the optimizer is right

`ancestor_events` and `site_id` are neither in `clause_blame_current`'s `DISTINCT ON` list
(`clause_uuid, as_of_commit`) nor functionally determined by it as far as the optimizer can know.
A filter on such a column **cannot be pushed below the de-duplication**: doing so would change the
answer, surfacing generation 2 — which contains event E — for a clause whose current generation 3
does not. That is not a missed optimisation. It is the view being correct. Measured:

```
• filter
  filter: (site_id = '…') AND (ancestor_events @> ARRAY['…'])
  └── • distinct
      │ distinct on: clause_uuid, as_of_commit
      └── • revscan
            table: clause_blame_closure@clause_blame_closure_pk
            spans: FULL SCAN
```

**NOT ASSERTED AS AN INDEX HIT, AND RECORDED AS SUCH.** A CI assertion that `cbc_anc` is traversed
here would be an assertion that fails on a correct database. What
`test_the_containment_lookup_omits_a_superseded_only_match` asserts instead is the *behaviour*: a
clause whose current generation contains E is returned, and a clause whose **superseded**
generation contains E while its current one does not is **omitted**. That is the property the read
path exists for, and it is the one any faster plan must preserve.

**Nor is the full scan asserted.** Asserting a weakness makes an optimizer improvement look like a
regression. It is recorded here so that the sentence "one index lookup" is never quoted somewhere
a regulator can hear it without this paragraph attached.

### 2.3 What IS asserted about `cbc_anc`

That the index exists, is shaped correctly, and is traversed for a containment predicate. The
assertion runs against the **table** with the index pinned — which a test may do and a service may
not (DM-9):

```sql
EXPLAIN SELECT clause_uuid
          FROM mainline.clause_blame_closure@cbc_anc
         WHERE site_id = $1 AND ancestor_events @> ARRAY[$2::UUID];
```

```
• scan
  table: clause_blame_closure@cbc_anc
  spans: 1 span
```

**ASSERTED** by `test_the_inverted_index_is_traversable_for_a_containment_predicate`. It proves
three separate things at once: that a multi-column inverted index was accepted **inline in
`CREATE TABLE`** with the inverted column last, that `@>` is a valid inverted-index constraint on
a `UUID[]`, and that no `STORING` clause crept onto it — CockroachDB refuses one, so its absence is
load-bearing rather than stylistic.

The unhinted form produced the **same** plan on this run. That is recorded, not asserted; see §0.

### 2.4 The accelerated form, written out so nobody has to invent it under pressure

If the read path's cost stops being acceptable, this is the replacement. It is index-accelerated
**and** cannot return a superseded generation:

```sql
WITH candidate AS (
  SELECT DISTINCT clause_uuid, as_of_commit
    FROM mainline.clause_blame_closure@cbc_anc      -- ANY generation: a superset, deliberately
   WHERE site_id = $1 AND ancestor_events @> ARRAY[$2::UUID]
)
SELECT c.clause_uuid, c.as_of_commit, c.closure_gen, c.max_severity, c.virulence, c.truncated
  FROM mainline.clause_blame_current AS c
  JOIN candidate USING (clause_uuid, as_of_commit)
 WHERE c.ancestor_events @> ARRAY[$2::UUID];        -- the answer is decided HERE, on the current row
```

The correctness argument in one line: the CTE is a **superset** of the answer (a clause whose
current generation contains E necessarily has *some* generation containing it), the join resolves
each candidate to its current generation by primary-key prefix, and the outer predicate re-decides
containment on that row — so a candidate that matched only in a superseded generation is dropped.

**It is deliberately not adopted.** Adopting it names `clause_blame_closure` in a file outside
`0038`, `0039` and `closure_write.sql`, which is a **DM-9 amendment**: it requires a matching,
reasoned entry in `scripts/grep_closure_readpath.py`'s `READ_ALLOWLIST` and a note in
`docs/leads/datamodel.md`. One relation as the read path is worth more than one index traversal at
the scale this system runs at, and the day that stops being true it should cost a review, not a
quiet rewrite.

---

## 3. `cbc_sev` — the severity sweep

Same structural caveat as §2.2: through the view, the predicate sits above the de-duplication.
`cbc_sev (site_id, max_severity) STORING (virulence)` serves the direct-table form the fleet
sweep's batch job uses. Measured:

```
• scan
  table: clause_blame_closure@cbc_sev
  spans: [/'…site…'/4 - /'…site…'/5]
```

A constrained span over exactly the blood band. **ASSERTED (hinted), for index shape only.**

The `STORING (virulence)` list is what makes the sweep index-only. `clause_uuid`, `as_of_commit`
and `closure_gen` are primary-key columns carried implicitly, which is why §5.4's printed
`STORING (clause_uuid, virulence, closure_gen)` is corrected in `0038` — CockroachDB refuses a
primary-key column inside `STORING`, and `test_no_primary_key_column_appears_in_a_storing_clause`
stops the correction being un-made by someone transcribing §5.4 again.

---

## 4. Honesty ledger

| Claim | Status |
|---|---|
| Migrations `0037`–`0039` apply on v26.2.5 | **MEASURED PASS**, 2026-08-10, on top of 62 clean prerequisites |
| Inline multi-column `INVERTED INDEX` in `CREATE TABLE` | **MEASURED PASS** — the `0038a` fallback was not needed |
| `@>` is index-accelerated on a `UUID[]` | **MEASURED PASS**, hinted and unhinted |
| `WITH RECURSIVE … INSERT INTO … SELECT` | **MEASURED PASS** — the writer ran and produced the right closure |
| `DISTINCT ON` inside a view | **MEASURED PASS**; a PK-prefix lookup through it is a `revscan … limit: 1` |
| ENUM compared to a string literal inside a `CHECK` | **MEASURED PASS** (`fatal_ancestry_is_banded_fatal`, `blood_needs_severity`) |
| `coalesce(array_length(…, 1), 0)` inside a `CHECK` | **MEASURED PASS** (`count_matches_the_array`) |
| `by_clause_commit` makes the base case one span | **MEASURED PASS** |
| The view's predicate cannot be pushed below `DISTINCT ON` | **MEASURED**: the plan filters above the `distinct`, as the semantics require |
| The recursive term's access path | **NOT INSPECTABLE.** `EXPLAIN` does not render it — see §1.2. No assertion is made |
| Latency, throughput, or behaviour at 10⁶ clause versions | **NOT MEASURED.** Every plan above was taken on a table holding single-digit rows with `missing stats` |

The last row is the one that matters most for anyone quoting this file. These are **plan-shape**
measurements on a tiny fixture, not a benchmark. They prove the indexes exist, are legal, and are
chosen; they prove nothing about p99 under load, and this band makes no such claim.
`test_mi_blame.py` reports a **skip with a reason** rather than a pass when no cluster is
reachable — a plan assertion that was never run asserts nothing, which is PL-2 applied to plans
instead of to refusals.
