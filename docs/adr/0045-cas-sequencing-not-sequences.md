<!--
SPDX-FileCopyrightText: 2026 MAINLINE
SPDX-License-Identifier: CC-BY-4.0
-->

# ADR 0045 — CU-2: `seq` is a compare-and-swap, and one `23505` is retryable by NAME

**Status:** Accepted · **Date:** 2026-08-04 · **Decider:** custody lead · **Milestone:** K2
**Supersedes:** nothing · **Implements:** `docs/leads/custody.md` §2 decision **CU-2**
**Depends on:** ADR 0002 (platform ground truth, finding F4)

## Context

Verifier check 9 says a gap in `mainline.ledger_leaf.seq` is evidence of tampering. That
sentence is either the most useful thing the ledger says or a lie, and which one it is
depends entirely on how `seq` is produced.

**A sequence cannot support it.** `nextval()` increments are non-transactional: they
survive a rollback by design, because that is what makes a sequence fast. A ledger numbered
by a sequence therefore has *legitimate* gaps — every rolled-back transaction leaves one —
and a verifier that found one could say nothing at all. The presence of a gap would be
consistent with an ordinary failed insert and with a deleted leaf, and a check that cannot
distinguish those is not a check.

**`CREATE SEQUENCE` works on our cluster.** ADR 0002 finding **F4** measured it: the
statement succeeds on CockroachDB CCL v26.2.5. Nothing about the platform prevents somebody
from adding one. The repository-wide ban on `CREATE SEQUENCE` / `nextval(` / `SERIAL` /
`unique_rowid()` is therefore **load-bearing rather than stylistic**, and `trappoint migrate
lint` is the only thing standing between this schema and a numbering whose gaps mean
nothing.

There is a second, subtler problem. Once `seq` is derived by compare-and-swap, two
concurrent appenders collide, and the collision arrives as `23505`. But `23505` is also how
the database says *"this entry was already sequenced"* (`ledger_leaf_entry_unique`) and
*"a settled interior hash was written twice with different content"* (`ledger_node_pkey`).
`spec/errors.md` classifies `23505` as **REFUSE**, not **RETRY**. Introducing a retryable
`23505` punches a hole in the one taxonomy the whole gate argument rests on, and the shape
of that hole decides whether the ledger's numbering is trustworthy or merely plausible.

## Decision

**1. `seq` is derived inside the appending transaction.**

```sql
seq := COALESCE((SELECT max(seq) FROM mainline.ledger_leaf WHERE site_code = $1), -1) + 1
```

Implemented as a single read — `SELECT seq, link_hash … ORDER BY seq DESC LIMIT 1` — so the
position and the predecessor come from one observation of the table rather than two.

**2. The append has refusal depth 2 (CU-1).** `PRIMARY KEY (site_code, seq)` refuses two
leaves at one position; `UNIQUE (site_code, prev_link_hash)` refuses two leaves claiming one
predecessor. Drop either and the concurrent write still fails. Genesis is 32 zero bytes
rather than `NULL`, so the linearity constraint applies uniformly from the first leaf — under
a nullable column every genesis row would be distinct to the unique index and `seq = 0`
would be the one position at which a fork was permitted.

**3. The resulting `23505` is the ONLY retryable `23505` in the repository, and the retry
predicate matches on CONSTRAINT NAME.**

| constraint | fact | disposition |
|---|---|---|
| `ledger_leaf_pkey` | somebody else took this position | retry, bounded at 8 |
| `ledger_linear` | somebody else claimed this predecessor (attack A6) | retry, bounded at 8 |
| `ledger_leaf_entry_unique` | already sequenced | **escape** |
| `ledger_node_pkey` | a settled hash rewritten | **escape** |
| anything else | a refusal | **escape** |

**4. A `23505` whose constraint cannot be named is not retried.** `exc.diag.constraint_name`
is preferred; the driver's message (`… violates unique constraint "ledger_leaf_pkey"`) is
parsed as a fallback because CockroachDB's population of that pgwire field is
version-dependent and was not verified for every constraint class. When neither yields a
name, the exception propagates. A retry keyed on an absent name is a blanket retry in
disguise.

**5. The retry is re-derivation, not repetition.** Each attempt re-reads the head *and*
re-runs the already-sequenced anti-join inside the same transaction. That is what makes
`ledger_leaf_entry_unique` safe to exclude from the retry set: by the time an attempt
inserts, it observed those entries unsequenced in the very transaction it is committing.

**6. The constraint names are an interface.** Renaming one is a breaking change to
`mainline_sequencer.append`, and
`tests/test_append_unit.py::test_the_constraint_names_the_retry_predicate_uses_exist_in_the_migration`
diffs the names the code uses against migration `0073_ledger_leaf.sql`.

## Alternatives considered and rejected

**`CREATE SEQUENCE`.** Rejected above: it makes check 9 vacuous. Cheaper, faster, and it
deletes the product.

**Retry on SQLSTATE `23505`.** One line shorter and it converts every detected duplicate
and every rewritten interior hash into a silent success. The one legitimate retry in this
repository would become a laundry for real refusals — a far worse defect than the contention
it absorbs.

**A lease that guarantees a single writer, with no CAS.** Rejected because it makes
correctness depend on a mutable row in `mainline_ops` that a T1 adversary can rewrite. The
lease is kept as a *performance* mechanism and is explicitly not relied on:
`tests/concurrency/custody/test_sequencer_cas.py` runs sixteen appenders **with no election
at all** and asserts the log is still dense and fork-free.

**An advisory lock.** CockroachDB has none.

**A `sequenced BOOL` flag on intake.** It would need `UPDATE` on an append-only table, and
the first `UPDATE` grant is the one that makes attack A1 (`delete_and_relink`) a single
statement for a role that already holds it. Sequenced-ness stays an anti-join.

## Consequences

**Good.** A gap now means exactly one thing. The ledger is held to the same standard the
kernel holds the gate to — refusal depth ≥ 2 — and the unwelding suite can remove one
constraint at a time and watch the other still refuse. The whole ledger write path is
`INSERT` + `SELECT`, which is what lets `agent_relay` hold `INSERT` and not even `SELECT`.

**Costs, accepted.** Appends to one site serialise: throughput is one batch per round trip
per site, which is why the batch exists and why `B ≤ 2048`. Under sustained contention an
invocation can exhaust its eight attempts and append nothing; that is reported as
`CasExhausted` rather than absorbed, and the next EventBridge tick re-selects the same rows
by anti-join, so nothing is lost. The signer is called *inside* the transaction — the note
body is a function of the head that transaction read — so a retry re-signs. Correct, because
the body differs, and one of the reasons the bound is eight rather than sixty.

## Verification

Measured 2026-08-04 against a disposable single-node **CockroachDB CCL v26.2.5**:

* **16 sequencers, one site, no lease, 160 intake rows, batch 8** → 212 rounds, 160 leaves,
  **317 CAS attempts** (so ≈ 117 genuine retries), 0 exhausted, 0 unmodelled refusals. `seq`
  dense `0..159`, every intake row present exactly once, no two leaves sharing a
  predecessor, link chain recomputing from genesis.
* **Two transactions both deriving `seq = 0`** → exactly one leaf exists afterwards and the
  loser is refused by a constraint inside the retry set.
* **Unit:** `ledger_leaf_entry_unique`, `ledger_node_pkey`, `fk_intake` and an unnameable
  unique violation each escape the loop on the first attempt.

## Two platform findings recorded here because this ADR is where they were found

**F4 is confirmed in force.** The sequence ban is the only thing preventing a valid
`CREATE SEQUENCE` on this cluster.

**`cluster_logical_timestamp()` is UNQUALIFIED on v26.2.5.**
`crdb_internal.cluster_logical_timestamp()` — the spelling `ARCHITECTURE.md` §5.6 and
migration `0072a`'s rationale both use in prose — raises `UndefinedFunction: unknown
function`. The unqualified builtin works. `mainline_sequencer.sink.INSERT_INTAKE_SQL` uses
the spelling that was observed to resolve and carries the measurement as a comment. This is
documentation drift, not a schema defect: nothing executes those prose lines.

**A note on 40001.** Sixteen contenders for one lease row on the same EventBridge tick
produce `40001 TransactionRetryWithProtoRefreshError: WriteTooOldError` on the CAS, not
merely a zero-row result. Those are different facts — *undecided* versus *somebody else won*
— and `mainline_sequencer.lease.contend` exists to keep them apart: `40001` is retried
because re-running re-observes the epoch and therefore cannot elect a second holder; a
zero-row result is returned as `None` and never retried.
