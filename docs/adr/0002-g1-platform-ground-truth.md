<!--
SPDX-FileCopyrightText: 2026 MAINLINE
SPDX-License-Identifier: CC-BY-4.0
-->

# ADR 0002 — G1 platform ground truth: measured, not assumed

**Status:** Accepted · **Date:** 2026-08-07 · **Cluster:** `mainline-dev` · CockroachDB CCL **v26.2.5**, cluster version 26.2, Basic tier, `aws-ap-southeast-1` (Singapore)

Executed against the live cluster. Every row below was **run**, not read from documentation.

## Results

| ID | Check | Result | Consequence |
|---|---|---|---|
| GT-01 | Server version | `v26.2.5` (built 2026-07-28) | Target platform confirmed |
| GT-03 | `feature.vector_index.enabled` | **`true` by default** | No cluster-setting change needed; the feasibility pass's correction holds |
| GT-04 | `VECTOR(n)` + prefix-column vector index on **Basic** | **Created** | **The single largest platform risk is retired.** No paid tier, no self-hosting |
| GT-05 | Vector inserts (5,200 rows, batched) | OK | `IMPORT INTO` avoidance strategy is sound |
| GT-06 | Prefix-constrained ANN, **unhinted** | **Index NOT used** — plan is `top-k → render → filter → scan` | **See "The finding" below** |
| GT-06b | Same query with `@index_name` hint | **Index used** | ANN traversal works; the optimizer is the variable, not the index |
| GT-07 | `gc.ttlseconds` | **4500** (75 minutes) | Tighter than the 14400 assumed in ARCHITECTURE.md §5 |
| GT-08 | PL/pgSQL trigger with `RAISE EXCEPTION` | OK | The PROJECT and REFUSE halves of TRAPPOINT are available |
| GT-09 | **CTE inside a UDF** | OK | Confirms feasibility finding F1: the "no CTE in UDFs" claim was stale (removed v25.1) |
| GT-10 | `ALTER TABLE … ENABLE ROW LEVEL SECURITY` | OK | RLS tenant/treaty wall available |
| GT-11 | `AS OF SYSTEM TIME '-1h'` | Refused — relation did not exist at that timestamp | Behaves exactly as the design requires; see below |
| GT-12 | `CREATE SEQUENCE` | **Succeeds** | Therefore the CI lint banning it is **load-bearing, not decorative** |
| GT-13 | `STORED` computed column with `digest()` | OK | The `dedupe_key` fix for adversarial finding S5 is implementable |
| GT-14 | Partial `UNIQUE` index | OK | The one-custodian invariant (I04 / MI-linear-head) is implementable |
| GT-15 | `kv.rangefeed.enabled` | `true` | Changefeeds available for the event spine |

Session variables observed, confirming the ANN machinery is present and tunable: `vector_search_beam_size = 32`, `vector_search_rerank_multiplier = 50`.

## The finding that changes a design decision

**At 5,200 rows the optimizer does not choose the vector index.** The unhinted plan filters *after* scanning. The index is traversed only when named explicitly (`FROM tbl@idx_name`).

`ARCHITECTURE.md` §6 and the `recall-ann-arms-explain` brief both specify a CI assertion of the form *"EXPLAIN proves the prefix-constrained ANN uses the index."* **As written, that assertion fails at demo corpus scale** — not because the index is broken, but because a cost-based optimizer legitimately prefers a scan on a small table.

**Decision: the recall arms pin the index explicitly rather than relying on optimizer choice.**

Rationale, and why this is an improvement rather than a workaround:

1. MAINLINE's thesis is **determinism under a safety gate**. A plan that flips based on table statistics is precisely the kind of non-determinism that must not sit beneath a refusal.
2. The CI assertion becomes meaningful again: it asserts the index *is* traversed, rather than asserting the optimizer *happened to agree* on that day's statistics.
3. It removes a silent-degradation failure mode in production — a corpus that shrinks (or statistics that go stale) would otherwise quietly turn ANN recall into a full scan, changing latency without changing behaviour, which is the worst kind of regression for a p99-bounded gate.

The prefix-column rule still binds: every prefix column must be constrained to a single value, so the ancestor walk remains one hinted ANN query per ancestor, `UNION ALL`-ed and re-ranked. **The `IN (...)` trap is unchanged.**

## Second finding: the time-travel window is even narrower than assumed

`gc.ttlseconds = 4500` — **75 minutes**, not the 14400 (4 hours) recorded in the architecture. The design's ruling stands and is strengthened: **all long-horizon versioning is the application-level commit DAG**, and no demo beat, claim, or exhibit may depend on `AS OF SYSTEM TIME` reaching further than roughly an hour.

GT-11's refusal is the constraint demonstrating itself: the relation did not exist at the requested timestamp, so the query was refused rather than silently returning a wrong answer. That is the correct behaviour and is worth keeping as a conformance case.

## Region and residency

The cluster is **Singapore (`aws-ap-southeast-1`)**. Sydney (`ap-southeast-2`) is **Advanced-tier only** — it is absent from the Basic and Standard region lists. Bedrock inference remains in **Sydney (`ap-southeast-2`)** on `au.*` inference profiles.

**Therefore: inference in Australia, database in Singapore.** Any claim of end-to-end Australian data residency is **false for the development deployment** and must not appear in the README, the submission, the video, or the console. `DEMO-HONESTY.md` states the split explicitly. Sydney remains available on Advanced for a production or customer deployment; ~AUD 400 of trial credit is held in reserve for that decision.

## AWS ground truth (same session)

- Identity: account `0229…8246`, `user/mainline-dev`. [The account id is masked for public release; the full twelve-digit value lives in the founder's `.env`, which is gitignored and has never been committed.]
- **8 `au.*` Claude inference profiles ACTIVE** in `ap-southeast-2`, including `au.anthropic.claude-sonnet-5` and `au.anthropic.claude-opus-5`.
- **`amazon.titan-embed-text-v2:0` is available in `ap-southeast-2`** — this closes the `recall-providers` worker's explicitly-flagged unverified item (AWS's launch announcement listed only US regions).
- **`cohere.embed-v4:0` is also available** and was not in the design. Recorded as a benchmark candidate against Titan in the recall evaluation harness; no change made unilaterally.
- Bedrock Rerank remains absent from `ap-southeast-2`, as the design assumed. No dependency taken.

## Actions arising

1. `recall-ann-arms-explain`: pin the index in every ANN arm; rewrite the CI EXPLAIN assertion to assert traversal of the named index.
2. `recall-eval-harness` / conformance: add GT-11 (time-travel beyond the GC window is refused, not silently wrong) as a case.
3. `cd-honesty-card`: record the inference-in-Sydney / database-in-Singapore split verbatim.
4. Kernel CI lint banning `CREATE SEQUENCE` / `nextval` / `SERIAL` / `unique_rowid()` is confirmed necessary — sequences are creatable on this cluster.
5. Re-run this attestation as `cloud-verify.yml` nightly once CI exists, per `BUILD_PLAN.md` §2(b).
