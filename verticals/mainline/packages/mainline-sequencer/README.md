<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
-->

# `mainline-sequencer`

**The singleton that turns intake into a dense, fork-free log — and the reason "a gap
MEANS tampering" is a true sentence rather than a slogan.**

Certificate Transparency splits *submission* from *merge*. So do we. Intake
(`mainline.ledger_intake`, random primary key, no hot row) scales with the cluster;
sequencing (`mainline.ledger_leaf`, dense, fork-free) is one writer per site. This package
is that writer, plus the intake sink that feeds it.

---

## The four properties, and the mechanism behind each

### 1. `seq` is a compare-and-swap, never a sequence — CU-2

```sql
seq := COALESCE((SELECT max(seq) FROM mainline.ledger_leaf WHERE site_code = $1), -1) + 1
```

derived **inside** the appending transaction. `CREATE SEQUENCE`, `nextval()`, `SERIAL` and
`unique_rowid()` are banned repository-wide and `trappoint migrate lint` enforces it.

> Sequence increments **survive rollback**. A ledger numbered by a sequence has legitimate
> gaps, so a gap means nothing. A ledger numbered by in-transaction compare-and-swap has
> none, so **a gap MEANS tampering** — and that sentence is verifier check 9.

The ban is load-bearing rather than stylistic because **`CREATE SEQUENCE` succeeds on the
target cluster** (`docs/adr/0002` F4): nothing but the lint stands between this schema and
a numbering whose gaps mean nothing.

### 2. The retry predicate matches on constraint NAME, never on SQLSTATE

Four constraints raise `23505` and they are four different facts:

| constraint | what it means | the CAS loop |
|---|---|---|
| `ledger_leaf_pkey` | somebody else took this position | **retry** |
| `ledger_linear` | somebody else claimed this predecessor (attack A6) | **retry** |
| `ledger_leaf_entry_unique` | this entry was already sequenced — "already done" | **escape** |
| `ledger_node_pkey` | a settled interior hash was written twice with different content | **escape** |

Bounded at eight attempts. `40001` is retried with capped exponential backoff and full
jitter, per `spec/errors.md`. **A `23505` whose constraint cannot be named is not retried
either** — an unnamed retry is a blanket retry wearing a specific loop's clothes.

Retrying the third row would turn a detected duplicate into a silent one. That is why the
load-bearing test in this package is a negative one:
`test_other_unique_violations_escape_the_cas_loop`. The single legitimate retry in this
repository must not become a laundry for real refusals.

### 3. Sequenced-ness is derived, never written

The batch is an anti-join against `ledger_leaf`. There is no `sequenced` flag and there
must never be one, so **the entire ledger path is `INSERT` + `SELECT`** — which is why the
`mainline_ledger` role holds exactly those grants, why `agent_relay` holds `INSERT` and not
even `SELECT`, and why the Managed MCP server's insert-only write surface is a structural
match rather than a coincidence.

`tests/test_batch_antijoin.py::test_no_update_against_any_ledger_table` reads this
package's own source and asserts that every mutation it contains targets
`mainline_ops.sequencer_lease`. A grep is a weak test in general and a strong one here,
because what is being asserted is the *absence* of a capability.

### 4. The lease is a performance mechanism, not a correctness one

CockroachDB has **no advisory locks**, so one sequencer per site is elected by a CAS on
`mainline_ops.sequencer_lease.epoch`. Delete every lease row and the system still cannot
fork: correctness is `ledger_leaf_pkey` and `ledger_linear`, which hold at any isolation
level and with no lease at all.

That is not a claim, it is a test.
`tests/concurrency/custody/test_sequencer_cas.py::test_sixteen_sequencers_without_a_lease_still_produce_a_dense_fork_free_log`
runs sixteen threads against one site **with no election at all** and asserts the log is
still dense `0..n-1`, contains every intake row exactly once, and has a link chain that
recomputes from genesis. Observed on CockroachDB v26.2.5: 16 workers, 212 rounds, 160
leaves, 317 CAS attempts, zero exhausted, zero unmodelled refusals.

---

## Modules

| module | what it owns |
|---|---|
| `lease.py` | `observe` / `acquire` / `contend` / `release`. `acquire` takes the caller's transaction; `contend` owns one and retries `40001` only. |
| `batch.py` | `SELECT_UNSEQUENCED` — the anti-join, ordered `(hlc, entry_id)`, `LIMIT B <= 2048`. |
| `append.py` | the CAS loop, the head read, the tree extension, the checkpoint insert, and the constraint classifier. |
| `sink.py` | `record_intake` (canonicalise → hash → insert) and `MainlineLedgerSink.emit` (that, plus a Signed Disposition Receipt). |
| `handler.py` | the EventBridge Lambda: contend, select, append, release, report. |

There is deliberately **no catch-all `SequencerError`**. A caller able to catch everything
from the ledger path in one clause is a caller able to silence a refusal, and in a product
whose deliverable is a refusal that is the defect class rather than a style nit.

---

## What this package does not own, and why that is visible in the code

RFC 6962 hashing, the link-chain step, the C2SP checkpoint note text and the receipt
signature all live in `packages/trappoint-ledger`. They are **not re-implemented here**: a
second implementation of an evidentiary hash is a second thing that can drift, and this
domain already pays a CI byte-equality check to keep one canonicaliser from drifting from
its vendored copy.

They are consumed through two Protocols — `append.LedgerAlgebra` and `sink.ReceiptIssuer`
— bound lazily by `append.default_algebra()` and `sink.default_receipt_issuer()`. When a
symbol is missing the failure is a named exception **saying which one**:

```
LedgerAlgebraUnavailable: trappoint_ledger.checkpoint.build_body is required and was not
importable, so no C2SP tlog-checkpoint note text can be assembled. …
```

Nothing degrades silently and nothing falls back to a local approximation. That is also
why `trappoint-ledger` is **not** in `dependencies` yet: declaring a `{ workspace = true }`
source for a member that does not exist makes `uv lock` fail for every worker in the
repository. The lazy binding is the honest expression of a dependency that is real and not
yet resolvable.

### The one performance debt, stated

`MerkleTree` is constructed from leaf hashes and has no restore-from-stored-nodes
constructor, so extending the tree reads **every** leaf hash for the site: O(n) rather than
O(log n) per checkpoint. At 100k leaves that is a 3.2 MB read and roughly 50 ms of hashing
every fifteen seconds — affordable, and not free. The fix is one constructor in the
substrate package (`MerkleTree.from_nodes(fringe)`), not a Merkle implementation here.

---

## Running the tests

```bash
# Unit lane — no cluster, no network. 59 tests, under a second.
uv run pytest verticals/mainline/packages/mainline-sequencer

# Database lanes — a DISPOSABLE single-node CockroachDB, discovered in this order:
#   $MAINLINE_TEST_DSN  →  a `cockroach` binary on PATH  →  the Docker daemon
uv run pytest tests/integration/custody/test_ledger_append.py
uv run pytest tests/concurrency/custody/test_sequencer_cas.py
```

Both database lanes **refuse any DSN whose host is not `localhost`/`127.0.0.1`**. They
write leaves and checkpoints, and a ledger lane that can reach a real deployment is itself
an attack surface. When no cluster can be found they skip with a message naming what was
missing and saying plainly that a skipped run proves nothing.

---

## Deployment

`handler.lambda_handler`, one Lambda per site, invoked by EventBridge every 15 s.

| variable | |
|---|---|
| `MAINLINE_SEQUENCER_DSN` | required |
| `MAINLINE_LOG_DOMAIN` | required — origin is `mainline.<domain>/site/<site_code>` |
| `MAINLINE_SITE_CODE` | required unless `event["site_code"]` is given |
| `MAINLINE_LOG_KMS_KEY_ID` | required |
| `MAINLINE_SEQUENCER_BATCH` | optional, default 512, ceiling 2048 |
| `MAINLINE_LEASE_TTL_SECONDS` | optional, default 60 |
| `AWS_REGION` | optional, default `ap-southeast-2` |

The two beacon values arrive in the invocation event (`event["beacon"]["drand"]` and
`["nist"]`), fetched by `mainline-anchor`, so this Lambda needs no egress and a beacon
outage cannot become a reason not to record a checkpoint.

**Nothing is invented when configuration is missing.** There is no default key, no
synthesised beacon and no development mode that signs with something else: a checkpoint
signed by a key nobody anchored is a weaker exhibit that looks identical to a strong one.
`RuntimeNotConfigured` names what is absent instead.

---

## The window is 60 seconds and that is the honest number

Between a disposition being recorded and its leaf appearing under a signed checkpoint
there is a Maximum Merge Delay. Ours is 60 s. The Signed Disposition Receipt is what turns
that gap from an invisible hole into a signed promise held by the party who signed the
disposition — so a leaf that quietly never gets sequenced becomes affirmative, portable
proof of log misbehaviour rather than nothing at all.

A ledger that claims a zero window is lying.

---

**References.** `ARCHITECTURE.md` §5.6, §7.2 · `spec/custody/ledger-schema.md` §§1–6 ·
`spec/wire/checkpoint.md` v1.0 · `spec/wire/receipt.md` v1.0 · `docs/leads/custody.md` CU-1,
CU-2 · `docs/adr/0045-cas-sequencing-not-sequences.md` · migrations `0072`–`0075`, `0079`.
