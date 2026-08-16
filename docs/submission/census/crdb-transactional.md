<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# CENSUS · W4 — CockroachDB transaction, isolation and time semantics

**Worker:** W4 · **Plan:** [`docs/submission/feature-census-plan.md`](../feature-census-plan.md) ·
**Date measured:** 2026-08-16 · **HEAD when measured:** `c951558` (the plan cites its parent
`5f57146`; nothing on this page depends on the difference) · **Deadline:** 2026-08-18 17:00 EDT

This file owns the half of CockroachDB that makes it the **memory layer rather than a store**:
what the database refuses to interleave, what it does when it cannot order two histories, how
far back it will let anyone look, and how the cluster is shaped. Plan §0.1 makes *Agentic
Memory Design* the tie-break axis; these are the rows that argue it, because they are the rows
where the database — not the application — is the thing holding the line.

**Every state below is backed by a command run today, with its real output pasted.** Three
things on this page are corrections to the existing census and they are collected in §3.

---

## 0. HOW TO CHECK EVERY ROW ON THIS PAGE

Four probes. Two are one paste each; two are short scripts reproduced in full in §7 so that a
stranger can run them without trusting a summary.

### 0.1 The cluster says what it is (one paste, ~2 s)

```bash
docker exec trappoint-crdb ./cockroach sql --insecure -d defaultdb \
  -e "SELECT version(); SHOW transaction_isolation; SHOW default_transaction_isolation;"
```

Run 2026-08-16, output verbatim:

```
version
CockroachDB CCL v26.2.5 (x86_64-pc-linux-gnu, built 2026/07/28 18:56:00, go1.25.5)
transaction_isolation
serializable
default_transaction_isolation
serializable
```

### 0.2 The live origin says the same thing, for free, to anyone (one `curl`, ~1 s)

```bash
curl -s https://ihuuyvm4z6nfuktihnkey77fpy0eyrhj.lambda-url.ap-southeast-1.on.aws/v1/health
```

Run 2026-08-16 11:02:35 UTC, output verbatim:

```json
{
  "applied_by": "scripts/deploy/cloud_chain.py",
  "cluster_version": "CockroachDB CCL v26.2.5 (x86_64-pc-linux-gnu, built 2026/07/28 18:56:00, go1.25.5)",
  "database": "mainline_demo",
  "deploy_chain_applied": 271,
  "deploy_chain_files": 271,
  "migrations_applied": 0,
  "ok": true,
  "schema_fingerprint": "ec9b1ce70a8df066e5763056c5ad9376800ef5df9362f7d0502b1dc7e7450339",
  "seconds": 0.0095,
  "server_date": "2026-08-16T11:02:35.388695Z"
}
```

The local container and the deployed origin are the **same build string, character for
character**. That is what entitles the rest of this page to measure locally and speak about the
demo.

### 0.3 The demo endpoint reports its own isolation level (one `curl`, ~1 s)

```bash
curl -s -X POST -H 'content-type: application/json' -d '{}' \
  https://ihuuyvm4z6nfuktihnkey77fpy0eyrhj.lambda-url.ap-southeast-1.on.aws/v1/demo/gate-run \
  | python -c "import json,sys; print(json.dumps(json.load(sys.stdin)['data']['transaction'], indent=2))"
```

Run 2026-08-16, output verbatim:

```json
{
  "canonicalisation": "mainline_demo_api.gate_run.canonical_json (sorted-key JSON; ASCII payloads only)",
  "closed_logical_timestamp": "1786878171346040996.0000000000",
  "disposition": "rolled_back",
  "isolation": "SERIALIZABLE",
  "opened_logical_timestamp": "1786878171346040996.0000000000",
  "retry_sqlstate": null,
  "savepoints": [
    "gate_run_beat_2",
    "gate_run_beat_3",
    "gate_run_beat_4"
  ],
  "single_transaction": true
}
```

Same request, the rest of the envelope: `verdict PROVEN`, `outcome completed`, `persisted
false`, `failures []`, four beats with SQLSTATEs `00000 / 23514 / P0001 / 00000` and
`matched_expectation` true on all four, `persistence_check.identical true`,
`self_persisted false`.

### 0.4 The two scripts

`§7.1` reproduces `w4_isolation_race.py` — the crossed-race probe, SERIALIZABLE vs READ
COMMITTED, six trials each — and `§7.2` reproduces `w4_aost.py`, the `AS OF SYSTEM TIME` horizon
probe. Both are printed **in full and unabridged**, both write **only** to scratch database
`w_w4`, both touch no product table, and both run in well under a minute against
`postgresql://root@127.0.0.1:26257/w_w4?sslmode=disable`. Every block of script output quoted on
this page is the output of the script as printed in §7 — not of a variant.

> Use `127.0.0.1`, not `localhost`. On this workstation `localhost` resolves to `::1` first and
> every connection pays a five-second fallback; a six-trial probe then looks hung and gets
> killed. Recorded because it cost this worker two runs.

---

## 1. THE ONE MEASUREMENT THAT CARRIES THE AXIS

Everything else on this page supports this paragraph.

`§7.1` runs the *same* two-connection crossed history — A reads row 2, B reads row 1, A writes
row 1, B writes row 2, both commit — six times at each of two isolation levels, on the same
node, in one sitting. Run 2026-08-16, **complete output, nothing omitted**:

```
cluster: CockroachDB CCL v26.2.5 (x86_64-pc-linux-gnu, built 2026/07/28 18:56:00, go1.25.5)
sql.txn.read_committed_isolation.enabled = True
SHOW transaction_isolation inside the downgraded txn = read committed
cluster_logical_timestamp() at READ COMMITTED -> 0A000 unsupported in READ COMMITTED isolation
  SERIALIZABLE   trial 1: sqlstate=40001 :: A lost :: restart transaction: TransactionRetryWithProtoRefreshError: TransactionRetryError: retry txn (RE
  SERIALIZABLE   trial 2: sqlstate=40001 :: A lost :: restart transaction: TransactionRetryWithProtoRefreshError: TransactionRetryError: retry txn (RE
  SERIALIZABLE   trial 3: sqlstate=40001 :: A lost :: restart transaction: TransactionRetryWithProtoRefreshError: TransactionRetryError: retry txn (RE
  SERIALIZABLE   trial 4: sqlstate=40001 :: A lost :: restart transaction: TransactionRetryWithProtoRefreshError: TransactionRetryError: retry txn (RE
  SERIALIZABLE   trial 5: sqlstate=40001 :: A lost :: restart transaction: TransactionRetryWithProtoRefreshError: TransactionRetryError: retry txn (RE
  SERIALIZABLE   trial 6: sqlstate=40001 :: A lost :: restart transaction: TransactionRetryWithProtoRefreshError: TransactionRetryError: retry txn (RE
SERIALIZABLE    : 40001 in 6 of 6 crossed races
  READ COMMITTED trial 1: sqlstate=None :: both committed (write skew admitted)
  READ COMMITTED trial 2: sqlstate=None :: both committed (write skew admitted)
  READ COMMITTED trial 3: sqlstate=None :: both committed (write skew admitted)
  READ COMMITTED trial 4: sqlstate=None :: both committed (write skew admitted)
  READ COMMITTED trial 5: sqlstate=None :: both committed (write skew admitted)
  READ COMMITTED trial 6: sqlstate=None :: both committed (write skew admitted)
READ COMMITTED  : 40001 in 0 of 6 crossed races
```

**Six of six, and zero of six.** The history that CockroachDB refuses to order under
`SERIALIZABLE` is a history it silently admits under `READ COMMITTED`. That is write skew,
measured, on the version we ship, in one paste. It is the reason this project sets the
isolation level explicitly on every gate transaction instead of inheriting a pool default, and
it is the reason the demo response *reports* the level rather than asserting it in prose.

The fourth line is the same fact from the other side: `cluster_logical_timestamp()` — the
hybrid-logical clock reading the demo uses to witness that all four beats shared one
transaction — is **refused with `0A000` at `READ COMMITTED`**. The witness the gate relies on
does not exist at the weaker level. This is the platform fact
`packages/trappoint-conformance/cases/cf45_read_committed.py:40-52` describes in a comment;
the comment is now measured.

---

## 2. THE ROWS

Row shape is plan §4. States are plan **R2**: LIVE · REPO · APPLIED · DECLARED · NOT-AVAILABLE.

---

### 2.1 `SERIALIZABLE` isolation, set explicitly on every gate transaction

**state:** `LIVE`

**what it is:** every transaction this project opens against a subject issues `SET TRANSACTION
ISOLATION LEVEL SERIALIZABLE` as its first statement, and the demo endpoint reports the level
it ran at in its own response body.

**where:**

| site | file:line |
|---|---|
| the permit gate-run, per attempt | `verticals/mainline/apps/demo-api/src/mainline_demo_api/gate_run.py:603` |
| the change-request gate-run, per attempt | `verticals/mainline/apps/demo-api/src/mainline_demo_api/cr_gate_run.py:572` |
| the four committing transitions, per attempt | `verticals/mainline/apps/demo-api/src/mainline_demo_api/transitions.py:459` |
| the substrate constant both are compared against | `packages/trappoint-core/src/trappoint_core/gate.py:56` (`ISOLATION_STATEMENT`) |
| the conformance harness pins it in its constructor | `packages/trappoint-conformance/src/trappoint_conformance/harness.py:152` |
| the migrator pins it per connection | `packages/trappoint-migrate/src/trappoint_migrate/db.py:108` |
| what the response reports | `gate_run.py:941` · `cr_gate_run.py:803` |

**verify in 60s:** §0.3. First line of the `transaction` block: `"isolation": "SERIALIZABLE"`.

**why the statement is issued even though the cluster default is already `serializable`** —
because the retried unit is the *whole* transaction (§2.2), so a re-attempt re-issues it; a
loop that retried a statement would inherit whatever the session last had. §0.1 shows the
default; `gate.py:56` exists so a wire log can be diffed against a constant rather than against
a remembered sentence.

**four beats, one transaction, rolled back.** The four beats of the demo — read, refused merge,
refused projection-drift attack, admitted write — run inside **one** transaction that is rolled
back at the end. The response proves it two ways rather than asserting it:
`opened_logical_timestamp == closed_logical_timestamp` (`gate_run.py:948`), because
`cluster_logical_timestamp()` is constant within a CockroachDB transaction and moves between
them, and `persistence_check.identical: true`, a before/after row-count fingerprint taken
outside the transaction. In §0.3's run both timestamps are `1786878171346040996.0000000000`.

**say this:** *"The demo runs four beats — a read, two refusals and an admitted write — inside
one `SERIALIZABLE` transaction that is then rolled back, and the response tells you the
isolation level, the two logical timestamps that prove it was one transaction, and the three
savepoints, so you never have to take our word for any of it."*

**never say:** *"CockroachDB is serializable so we get this for free."* The level is set
explicitly on every attempt, and §1 is the measurement of what is lost one level down.

---

### 2.2 `SQLSTATE 40001` — retried, and the carve-out that says why it is not a failure

**state:** `LIVE` (the loop is in the request path of all five POSTs) ·
proof-that-it-fires: `REPO`

**what it is:** `40001` is the only SQLSTATE this project ever retries, it is retried by
re-running the **whole transaction from `BEGIN`**, and it is classified as *undecided* rather
than *failed* — because a `40001` is a transaction the database aborted, so no row was written
and no decision was taken.

**where:**

| thing | file:line |
|---|---|
| the constant, named in the live path | demo-api `db.py:154-155` — the comment reads *"SQLSTATE 40001, `serialization_failure`. CockroachDB's `RETRY_SERIALIZABLE`."* |
| the loop the Lambda actually runs | demo-api `retry.py` (`run_transaction`, `classify_for_retry`, `full_jitter`) |
| the substrate's reference loop | `packages/trappoint-core/src/trappoint_core/retry.py` |
| the taxonomy both conform to | `packages/trappoint-core/src/trappoint_core/errors.py:71-81` |
| the migrator's own loop | `packages/trappoint-migrate/src/trappoint_migrate/db.py:139` — `except psycopg.errors.SerializationFailure as exc:  # 40001, and only 40001` |
| what a spent budget surfaces | demo-api `retry.py:106` and `transitions.py:1602` — `503 transaction_undecided` carrying `sqlstate: "40001"` |
| the reproducibility note this row is built on | demo-api `retry.py:111-117` |

Everything above with a bare filename lives in
`verticals/mainline/apps/demo-api/src/mainline_demo_api/`.

**the taxonomy, verbatim from `errors.py:71-81`:**

```python
RETRYABLE_SQLSTATE: Final = "40001"
REFUSAL_SQLSTATES: Final[frozenset[str]] = frozenset({"23514", "23503", "23505", "P0001"})
DENIED_SQLSTATE: Final = "42501"
MODELLED_SQLSTATES: Final[frozenset[str]] = REFUSAL_SQLSTATES | {RETRYABLE_SQLSTATE}
```

`40001` is retried. The four refusal codes are **attempted exactly once, ever** — not once per
budget, once — because `mainline.refusal_ledger` records decisions the gate made, and a client
that retries a `23514` writes five identical refusals for one attempted history, at which point
the count of refusals stops being a count of anything. `42501` is not retried because the writer
never reached the gate. Everything else propagates unwrapped.

**the carve-out that is worth a judge's attention.** `40003` — *"the commit may or may not have
landed"* — is deliberately **not** treated as a serialization failure and is classified
`unmodelled`, so it propagates unretried. `40001` means aborted; `40003` means ambiguous. Two
codes that a decorator retrying "on exception" would collapse into one, and the difference
between them is the product. `tenacity`, `backoff`, `retrying` and `stamina` are forbidden
imports repository-wide under `.importlinter` contract 4 for exactly that reason.

**verify in 60s — that the code fires, six times out of six.** Run `§7.1`; its SERIALIZABLE
block is quoted in §1 and ends `40001 in 6 of 6 crossed races`.

The **untruncated** message from one such trial, read from psycopg's exception object rather
than from a rendered error string:

```
psycopg.errors.SerializationFailure: restart transaction:
TransactionRetryWithProtoRefreshError: TransactionRetryError: retry txn
(RETRY_SERIALIZABLE): "sql txn" meta={id=a41090f6 key=/Table/112137/1/1/0 iso=Serializable
pri=0.01140400 epo=0 ts=1786878125.562938098,1 min=1786878125.561464471,0 seq=2} lock=true
stat=PENDING rts=1786878125.561464471,0 gul=1786878126.061464471,0 obs={n1@1786878125.561464471,0}
HINT:  See: https://www.cockroachlabs.com/docs/v26.2/transaction-retry-error-reference.html#retry_serializable
```

**`40001` is reproducible on a single node, and that deserves its own sentence.** It is not a
hazard this project guessed at and then wrote a guard for. A contended history produces
`RETRY_SERIALIZABLE` deterministically, on one node, in under a second, six times out of six —
which is why the loop can be tested rather than merely reasoned about.

**and it was measured against CockroachDB Cloud too.** `evidence/deploy/cloud-contention.json`
(generated 2026-08-14 by `scripts/deploy/cloud_contention.py`) ran twelve rounds of the same
constructed race against **both** the Cloud Basic cluster and the local node in one sitting.
Both columns, identically:

```
rounds 12 · callers 24 · sqlstates {"00000": 24, "40001": 12}
restart_reasons_for_40001 {"RETRY_SERIALIZABLE": 12}
where_the_40001_surfaced {"commit": 12}
rounds_where_both_callers_committed 12
callers_run_gate_actually_retried 12
callers_undecided_retry_budget_exhausted 0
callers_where_record_and_spy_disagree 0
attempt_latency_seconds  cloud median 0.4519 · local median 0.0024
```

Twelve rounds, twelve restarts, and **both callers committed in all twelve** — the loop did not
merely observe the failure, it recovered from it. `record_agrees_with_spy` is a
`RecordingObserver` cross-check: every caller records whether the loop *actually* retried rather
than assuming it was reached, and the two views disagreed zero times.

**verify in 60s:** `python -c "import json;d=json.load(open('evidence/deploy/cloud-contention.json'));print(json.dumps(d['comparison']['arms']['constructed'],indent=1))"`

**say this:** *"`40001` is the only code we retry, we retry the whole transaction rather than a
statement, and we call it undecided rather than failed because the database aborted it — so
nothing was written and nothing was decided. Twelve induced races on CockroachDB Cloud and
twelve on a local node each produced `RETRY_SERIALIZABLE` at commit, and the loop recovered
every one. When the budget is spent the caller gets `503 transaction_undecided` carrying
`sqlstate: 40001` — never a refusal, because the gate never got to say anything."*

**never say:** *"we have observed `40001` on the deployed Lambda."* We have not. The live
origin's `retry_sqlstate` was `null` in §0.3 and the demo is uncontended. The Cloud arm of
`cloud-contention.json` drove `trappoint_core.retry.run_gate` and drove the demo-api handler
from a **local** HTTP server pointed at the Cloud database; the deployed Lambda's own
`retry.py` loop firing in production is **UNPROVEN**, and demo-api `retry.py:116-117` says so in
the source — *"The Cloud behaviour of this loop is UNPROVEN and is reported as unproven; local
green does not stand in for it."*
Also never say *"we retry on serialization errors"* without the once-only half — the refusal
discipline is the more interesting claim.

---

### 2.3 `READ COMMITTED` — shipped as a contrast, and currently CANNOT RUN

**state:** `REPO` for the isolation downgrade (exercised today, §1, script in §7.1) ·
`DECLARED` for the conformance case

**what it is:** `packages/trappoint-conformance/cases/cf45_read_committed.py` runs the entire
gate history one isolation level down and asserts, from `SHOW transaction_isolation` on a
dedicated connection, that the downgrade actually happened — *"a case that meant to run at
`READ COMMITTED` and silently ran at `SERIALIZABLE` would be the most reassuring possible way
to prove nothing."*

**where:** `packages/trappoint-conformance/cases/cf45_read_committed.py`, whole file; the
assertion at lines 80 and 87-93.

**what the case claims, and what it explicitly refuses to claim** (docstring, lines 13-18): the
gate stays welded at `READ COMMITTED` because the conflict is **materialised in data** —
`open_blocking` is a real column on the subject row written by a trigger, and the `CHECK` reads
it in the same statement that completes the transition, which needs the row to be *current*,
not the transaction to be serializable. What degrades is **drift detection**: the re-derivation
inside `fn_permit_merge_gate` takes a snapshot per statement, so a concurrent materialisation
can land between the re-derivation and the counter read. The case says in its own docstring
that it "does not claim READ COMMITTED is equivalent to SERIALIZABLE, and the corpus must never
be read as claiming it".

**verify in 60s — and this is a correction:**

```bash
python -m trappoint_conformance.cli \
  --dsn "postgresql://root@127.0.0.1:26257/mainline_demo?sslmode=disable" \
  --profile mainline --autodetect-requires --case CF-45 --json
```

Run 2026-08-16, output verbatim:

```json
{
  "detail": "WORLD NOT BUILT — CF-45: building the LEGAL world failed at 'clause_version'. The world a case is illegal in must itself be legal, so this is a broken case or an unmigrated schema, not a refusal. Cause: column \"body_sha256\" does not exist",
  "expect_constraint": "gate_closed_when_issued",
  "expect_sqlstate": "23514",
  "id": "CF-45",
  "status": "cannot_run"
}
```

**CF-45 does not currently run.** It is one of the 46 cases blocked by a single setup defect —
a `clause_version.body_sha256` column the world-builder names and the schema calls
`canon_sha256`. That is already the project's own published position:
`qa/conformance-census.json` records **71 declared · 10 passed · 6 failed · 55 cannot-run · 0
errored**, `docs/HONESTY.md:863` names this exact cause, and
`docs/release/conformance-census.md:116` prints it per case. Today's run reproduces the census
exactly. `body_sha256` appears in **no** database on this node — confirmed with
`SELECT table_catalog, table_schema, table_name FROM information_schema.columns WHERE
column_name='body_sha256' AND table_name='clause_version'`, which returns a header and zero
rows.

**so the honest READ COMMITTED claim is the measured one, not the case.** §1 is a direct
platform measurement anyone can reproduce from `§7.1`: at `READ COMMITTED` the crossed history
commits both sides zero-for-six, and `cluster_logical_timestamp()` is refused `0A000`.

**say this:** *"We ship a conformance case that re-runs the whole gate history one isolation
level down, because a gate that has only ever been tried at its best isolation level has not
been tried. On the schema currently deployed that case cannot build its world — it is one of
the 46 blocked by a single missing column, and our own conformance census prints that number.
What we can show you in one paste is the platform contrast the case exists to make: the same
crossed history that CockroachDB refuses six times out of six at `SERIALIZABLE` it admits six
times out of six at `READ COMMITTED`."*

**never say:** *"CF-45 passes"*, *"our conformance suite is green"*, or *"we have proved the
gate holds at READ COMMITTED"*. None of the three is true. `docs/demo/research/r6-honesty.md:297`
already fixes the permitted wording for the suite as a whole and this row does not widen it.

---

### 2.4 `AS OF SYSTEM TIME` — used, and then proved unable to reach

**state:** `REPO`

**what it is:** the project uses time-travel reads where they work, and ships a conformance case
whose entire purpose is to demonstrate where they stop — plus a library function that **refuses
to execute any SQL string containing `AS OF SYSTEM TIME`** on the evaluation path.

**where:**

| thing | file:line |
|---|---|
| the case that proves the wall | `packages/trappoint-conformance/cases/cf46_time_travel_cannot_reach.py:106` — `SELECT count(*) FROM {s}.permit AS OF SYSTEM TIME '-2160h'` |
| the case reads the cluster's own retention | same file, lines 91-98 — `SHOW ZONE CONFIGURATION FROM RANGE default`, every column scanned |
| the refusal, unconditional | `packages/trappoint-recall/src/trappoint_recall/eval/splits.py:70-90` (`refuse_as_of_system_time`) |
| the refusal, as a lint on any SQL string | `splits.py:93-100` (`assert_no_as_of_system_time`) |
| what replaces it | `packages/trappoint-recall/src/trappoint_recall/corpora/g4_retro.py:19-20, 259-260` |

**this is a better claim than "we use time-travel queries", and here is why.** `-2160h` is
ninety days — a quarter, which is what an auditor asks for. CF-46 issues it, catches the
refusal, and stores it as **evidence rather than as an expectation** — the case's own docstring
(lines 23-26) is explicit that the refusal is deliberately *not* the assertion, because it is
outside the modelled gate taxonomy and *"recording it as evidence rather than as an expectation
is the difference between documenting a platform limit and modelling it as a product
behaviour."* The case then asserts the thing that keeps the sentence honest as the cluster
changes: `gc.ttlseconds < requested_horizon_seconds`. If someone raises retention past ninety
days, **the case goes red before the prose goes wrong.**

**verify in 60s, part one — the horizon probe (`§7.2`).** Run 2026-08-16, **complete output**,
every SQLSTATE read from psycopg's `sqlstate` field rather than from a rendered error string:

```
rows before insert=2  now=3  AS OF SYSTEM TIME '-5s'=3
-10s     -> 2 row(s)
-90m     -> SQLSTATE 42P01 :: relation "w4_race" does not exist
-2160h   -> SQLSTATE XXUUU :: error in retrieving descs between 1779103016.089424462,0,
            1786581608.543783676,0: batch timestamp 1779103016.089424462,0
gc.ttlseconds line: ['gc.ttlseconds = 4500,']
```

**Line one and line two together are the proof that this is real time travel, and they are the
reason the probe inserts a row before it reads.** The script counts rows (`2`), inserts one
(`3`), sleeps six seconds, then reads at two different points in the past: `-5s` returns **3**,
because the insert had already happened five seconds ago, and `-10s` returns **2**, the state
*before* the insert. Same table, same connection, same instant of asking, two different answers,
each correct for the timestamp it was asked about. Nothing about that is inferable from a
schema — it is MVCC, being read.

Then the wall. At `-90m` the read returns `42P01`: this table did not exist ninety minutes ago,
which is a correct historical answer rather than an error about time travel. At `-2160h` — ninety
days, the horizon an auditor actually asks about — the database **refuses**, and the message
names the boundary it crossed rather than the symptom downstream of it; the full text continues
*"… must be after replica GC threshold"*. The zone's own `gc.ttlseconds = 4500` is read in the
same run, from the second column of `SHOW ZONE CONFIGURATION`, so the wall and the refusal are
measured together and never asserted from memory.

Time travel works, works honestly, and stops at a wall the cluster will tell you about.

**verify in 60s, part two — the case is green today:**

```bash
python -m trappoint_conformance.cli \
  --dsn "postgresql://root@127.0.0.1:26257/mainline_demo?sslmode=disable" \
  --profile mainline --autodetect-requires --case CF-46 --json
```

```
"green": true,
"summary": "1/1 · spec 1.0.0-rc.1 · profile mainline",
"detail": "CF-46: completed (00000)"
```

**the refusal, exercised.** `splits.py` does not merely document the limit, it refuses to let
anyone reach for it. Run today:

```python
>>> assert_no_as_of_system_time(
...     "SELECT cue_id FROM event_cue AS OF SYSTEM TIME follower_read_timestamp()",
...     context="census probe")
AsOfSystemTimeRefused: AS OF SYSTEM TIME refused for 'census probe': gc.ttlseconds is 14400
(4.0h), so an AOST read cannot reach a time wall months in the past. The evaluation time wall
is enforced by the predicates occurred_at < t AND ingested_at < t AND corpus_commit <= t
(recall lead decision D12). Use SplitPolicy.admits().
```

The evaluation time wall is three predicates — `occurred_at < t`, `ingested_at < t`,
`corpus_commit <= t` — and long-horizon reconstruction is the application-level commit DAG plus
the `permit_event` hash chain, not MVCC.

**one number in that message is generous and this page will not round it off.**
`splits.py:54` sets `GC_TTL_SECONDS_DEFAULT = 4 * 60 * 60` with the docstring *"Verified: 4
hours"*, so the refusal message says `14400 (4.0h)`. The cluster measures **4500** — seventy-five
minutes, not four hours. The refusal is unconditional, so a stale constant cannot make it fire
wrongly; it only makes the explanation more generous than reality, in the direction that
weakens our own case. Logged as an open question in §6, **not edited** — that file is not this
page's to touch.

**say this:** *"We use `AS OF SYSTEM TIME`, and then we ship a conformance case whose whole
purpose is to prove it cannot do the thing people assume it does. In one script you can watch
the same query return three rows at five seconds ago and two rows at ten seconds ago — real MVCC,
being read — and then watch ninety days ago get refused by the replica GC threshold, with
`gc.ttlseconds = 4500` read off the cluster in the same run. So our evaluation harness refuses
outright to execute any SQL containing `AS OF SYSTEM TIME`: a time wall that silently evaluates
over a window nobody intended is worse than one that fails. Long-horizon history is the
application-level commit DAG and the database-computed hash chain instead."*

**never say:** *"we can prove the state at any time T"*, or *"time-travel queries give us
audit history"*. Both are the claim CF-46 exists to destroy.

---

### 2.5 Follower reads — **confirmed**, not downgraded

**state:** `REPO`

Plan §2/§3 flags `crdb_follower_reads EXERCISED` as needing an artefact or a downgrade. **The
artefact exists and it ran today.** The row stands.

**what it is:** the fixity patrol and coverage scans read at
`AS OF SYSTEM TIME follower_read_timestamp()` — roughly 4.2 s of staleness — so a background
integrity sweep never contends with a merge, and a patrol run that cannot state its
follower-read timestamp is refused by its own emitter.

**where:**

| thing | file:line |
|---|---|
| the role comment that grants it | `verticals/mainline/db/migrations/0180c_role_agent_patroller.sql:37` |
| the coverage view | `verticals/mainline/db/migrations/0163_v_fixity_coverage.sql:80` |
| the module, and the one combination never allowed | `verticals/mainline/packages/mainline-fixity/src/mainline_fixity/follower.py:3-30` |
| the emitter that refuses a patrol without one | `verticals/mainline/packages/mainline-fixity/src/mainline_fixity/emit.py:331, 352` |
| the cluster test | `tests/integration/fixity/test_fixity_cluster.py:126` |

**the design rule is a prohibition, and it is the interesting half.** `follower.py:5-11`
requires that patrol reads use `AS OF SYSTEM TIME follower_read_timestamp()` **and** that gate
reads never use follower or bounded-staleness reads. Read together the two forbid exactly one
thing — *a stale read of a gate table*. A patrol that answered a gate question from a follower
read would be answering with data 4.2 seconds old, and the failure would be invisible: the
merge would succeed, the finding would be recorded, and the two would disagree about a moment
nobody wrote down. So the module makes both rules structural — every patrol read is constructed
through `patrol_read()`, which welds the preamble on and **refuses any statement naming a table
the merge gate reads**. `follower.py:25-27` names the cost of skipping it, and it is the sort of
detail only measurement produces: the scan then takes read locks on rows a permit merge is
trying to write, and *"the first symptom is a `40001` **on the merge**, in a different process,
minutes later."*

**verify in 60s, part one — the platform:**

Against the two-row table `§7.1` leaves behind:

```bash
docker exec trappoint-crdb ./cockroach sql --insecure -d w_w4 \
  -e "BEGIN; SET TRANSACTION AS OF SYSTEM TIME follower_read_timestamp();
      SELECT count(*) FROM w4_race; SELECT cluster_logical_timestamp(); COMMIT;"
```

Run 2026-08-16, output verbatim:

```
BEGIN
SET TRANSACTION
count
2
cluster_logical_timestamp
1786878864915164000.0000000000
COMMIT
```

`SELECT follower_read_timestamp()` on the same node returned `2026-08-16 11:14:25.867603+00`.
The ~4.2 s of staleness is the figure `follower.py:9` documents; this page did not time the
delta and does not claim to have.

**verify in 60s, part two — the committed test, run today.** The test is `cluster_shaped` and CI
skips it for a *named* reason. Find the entry with
`python -c "import json;print([s for s in json.load(open('qa/ci-skip-census.json'))['skips'] if 'follower_read' in s['nodeid']])"`:

```json
{"nodeid": "tests/integration/fixity/test_fixity_cluster.py::test_a_follower_read_transaction_reports_its_own_hlc",
 "line": 126, "cluster_shaped": true,
 "reason": "no cluster: set one of MAINLINE_TEST_DSN, COCKROACH_URL, CRDB_URL, TRAPPOINT_DSN. AWS credentials are not valid on this build machine, so a local `cockroach` binary or a container is the intended path"}
```

Point it at a cluster and it runs:

```bash
MAINLINE_TEST_DSN="postgresql://root@localhost:26257/mainline_demo?sslmode=disable" \
python -m pytest tests/integration/fixity/test_fixity_cluster.py \
  -p no:cacheprovider -o junit_family=xunit1 --junit-xml=fixity.xml -q
```

`fixity.xml`, read from the JUnit XML and **not** from a terminal tail:

```
testsuite  tests=3  errors=0  failures=0  skipped=2  time=5.238
  test_a_follower_read_transaction_reports_its_own_hlc            passed   5.029 s
  test_an_undetermined_finding_that_claims_blocking_is_refused    skipped  (migrations 0090-0098 have not landed)
  test_every_emitted_statement_parses_on_the_cluster              skipped  (migrations 0090-0098 have not landed)
```

**1 passed, 0 failed.** The one that passed is precisely the one that settles this row: a
follower-read transaction reports its own HLC as a `DECIMAL`, which is how `patrol_run.as_of_hlc`
gets populated. The other two skip because tables `0090-0098` have not landed — a named reason,
not a silent pass.

**and that result makes a note in our own source stale, in our favour.** `follower.py:29-37`
carries a *"Verified-status note"* saying that the HLC behaviour is documented CockroachDB
behaviour which **"this repository has not yet measured on v26.2"**, and that
`tests/integration/fixity` carries the assertion and skips with a reason until a cluster is
available. A cluster was available today and the assertion passed. The source note is honest
and was correct when written; W7 should know it now understates what has been measured. **This
page does not edit it** — that file belongs to another domain, and a census that quietly
rewrites the source it cites is worth nothing.

**say this:** *"Background integrity patrols read at `follower_read_timestamp()` so an integrity
sweep can never contend with a merge, and the rule is written as a prohibition in both
directions: patrol reads must be follower reads, gate reads must never be. A cluster test
measures that a follower-read transaction reports its own hybrid-logical clock, which is the
timestamp every patrol run is stamped with."*

**never say:** *"follower reads serve the demo."* They do not — `grep -rn "follower_read"
verticals/mainline/apps/demo-api/src/` returns nothing. This is a repository capability with a
cluster test, in the plan's **R4** Bedrock construction.

---

### 2.6 `crdb_internal` — **the existing row is corrected here**

**state:** `NOT-AVAILABLE` for the `crdb_internal` schema (restricted by platform default) ·
`LIVE` for the unqualified HLC builtin

Plan §3 asks W4 to check whether any live path depends on `crdb_internal`. **None does**, and
the existing single row conflates two different things that deserve opposite states.

**measurement one — the schema is refused, by the platform, not by us:**

```bash
docker exec trappoint-crdb ./cockroach sql --insecure -d w_w4 \
  -e "SELECT count(*) FROM crdb_internal.cluster_settings;"
```

```
ERROR: Access to crdb_internal and system is restricted.
SQLSTATE: 42501
HINT: These interfaces are unsupported in production. To proceed, set the session variable
allow_unsafe_internals = true (not recommended), or contact Cockroach Labs for a supported
alternative.
```

With the opt-in, the same query returns `1076`. The number is **not** quoted as a property of
anything — it counts settings on this node on this afternoon. The *opt-in* is the claim.

**measurement two — the qualified spelling does not exist on this version:**

```
SELECT crdb_internal.cluster_logical_timestamp()  ->  42883  unknown function:
                                                            crdb_internal.cluster_logical_timestamp()
SELECT cluster_logical_timestamp()                ->  1786877563585252761.0000000000
```

The builtin the project actually uses is **unqualified**. It is not in `crdb_internal` at all.

**measurement three — no live path touches it:**

```bash
grep -rn "crdb_internal" verticals/mainline/apps/demo-api/src/ | wc -l
```

```
0
```

**what is actually LIVE is the HLC, and it is load-bearing.**
`gate_run.py:367-376` reads `SELECT cluster_logical_timestamp()::STRING` at the open and close
of the demo transaction, and `gate_run.py:948` compares the two to produce
`single_transaction` — the read-only witness in §0.3 that all four beats shared one
transaction. The same clock is the sequencer's ordering key, because `CREATE SEQUENCE`,
`nextval`, `SERIAL` and `unique_rowid()` are banned repo-wide by ADR `0045`.

**the security half is a design property, not an accident.** `crdb_internal` is on the MCP
identity's forbidden list at `packages/mainline-mcp/src/mainline_mcp/limits.py:75` alongside
`pg_catalog`, `information_schema` and `pg_extension`. That it is *also* unreachable **by
platform default** on v26.2.5 strengthens the claim rather than weakening it: the audit surface
is unreachable before any policy of ours is applied.

**verify in 60s:** the three probes above, pasted as-is.

**say this:** *"The hybrid-logical clock is live in the demo's request path — it is what proves
the four beats shared one transaction — and it is an unqualified builtin, not a
`crdb_internal` call. The `crdb_internal` schema itself is refused with `42501` on v26.2.5
unless a session explicitly opts in, which is why our audit views are the API rather than a
bypass around one: on this version the bypass is closed before we close it."*

**never say:** *"we use `crdb_internal` for HLC ordering"* — the qualified function does not
exist on v26.2.5 (`42883`, measured). `docs/submission/DEVPOST.md:124` currently carries
*"`crdb_internal` for the HLC ordering the ledger"*; **W7 must rewrite that clause** to name
`cluster_logical_timestamp()` unqualified. `docs/adr/0045-cas-sequencing-not-sequences.md:142`
also uses the qualified form; recorded as a cross-domain note and not edited here.

---

### 2.7 CHANGEFEED — `DECLARED`, and the reason is good engineering

**state:** `DECLARED` (plan R2: generator verdict `DESIGNED`)

**what it is:** `CREATE CHANGEFEED` is written, discussed in 7 scanned files
(`evidence/tool-usage/crdb-features.json#rows.crdb_changefeed.file_count`, the generator's own
count under its own exclusions — a naive `grep -rl` over a working tree returns more, because it
also sees this page and `docs/TOOL-USAGE.md`), and **has never been run**. It is kept out of
migrations on purpose.

**where and why, verbatim from `packages/trappoint-migrate/README.md:253-255`:**

> **No changefeed creation.** Changefeeds are cluster jobs, not schema. Putting
> `CREATE CHANGEFEED` in a migration makes migrations non-idempotent across environments and
> couples DDL to S3 credentials.

Three defects in two sentences, and each one is real. A changefeed is a **job**, so a migration
that creates one is not a schema statement and cannot be replayed. Replaying it on a second
environment either duplicates the feed or fails. And it drags a sink credential into the DDL
path, so the schema can no longer be applied by anyone who lacks S3.

There is a second, independent constraint that the same package enforces from the other
direction: RLS is never enabled on CDC source tables, because changefeed queries fail on
RLS-enabled and multi-family tables — `verticals/mainline/db/migrations/0198x_no_rls_on_cdc_sources.sql`.

**verify in 60s:**

```bash
docker exec trappoint-crdb ./cockroach sql --insecure -d mainline_demo -e "SHOW CHANGEFEED JOBS;"
docker exec trappoint-crdb ./cockroach sql --insecure -d mainline_demo \
  -e "SELECT count(*) FROM [SHOW JOBS] WHERE job_type = 'CHANGEFEED';"
```

Run 2026-08-16:

```
SHOW CHANGEFEED JOBS 0
count
0
```

Zero. The claim and the cluster agree.

**say this:** *"Changefeeds are designed and deliberately not run. They are cluster jobs rather
than schema, so a `CREATE CHANGEFEED` inside a migration makes the migration non-idempotent
across environments and couples DDL to a sink credential — and the migrator refuses them for
that reason, in writing. `SHOW CHANGEFEED JOBS` on our cluster returns zero and we would rather
say so."*

**never say:** *"we stream memory updates with CDC"*, or anything implying a live feed.

---

### 2.8 `SAVEPOINT` / `ROLLBACK TO SAVEPOINT` — a refusal that undoes only its own beat

**state:** `LIVE`

**what it is:** each beat of the demo that is *expected* to be refused runs inside its own
savepoint, so a `CHECK` violation undoes that beat without poisoning the transaction the next
beat needs. Without it, the four-beats-in-one-transaction property of §2.1 is impossible: in
PostgreSQL wire semantics a statement issued after an aborted one is `25P02`, a client bug.

**where:** `gate_run.py:667, 671, 680, 686` (beat 2) · `693, 711, 720, 727` (beat 3) ·
`760, 805, 839, 840` (beat 4) · `cr_gate_run.py:348-349, 651-703` (two savepoints) ·
declared in the response at `gate_run.py:949` and `cr_gate_run.py:811`.

**verify in 60s:** §0.3 — `"savepoints": ["gate_run_beat_2", "gate_run_beat_3",
"gate_run_beat_4"]`, alongside four beats whose SQLSTATEs are `00000 / 23514 / P0001 / 00000`.
Three savepoints, four beats: beat 1 is a read and needs none.

**say this:** *"Two of the four beats are refusals, and a refusal aborts a PostgreSQL
transaction. Each refusable beat therefore runs inside its own savepoint and is rolled back to
it, which is how four beats — including two refusals and then an admitted write — fit inside one
transaction that a judge can watch report a single logical timestamp at both ends."*

**never say:** the savepoints hide or suppress a refusal. Each refusal's SQLSTATE and constraint
name are in the response; the savepoint scopes the undo, it does not swallow the verdict.

---

### 2.9 No advisory locks — so the migration lease is a row

**state:** `REPO`

**what it is:** `pg_advisory_lock` does not exist in CockroachDB. Every PostgreSQL migration
tool assumes it. This project's migrator therefore holds its lease in a **real table**,
`trappoint.schema_lock`, with a holder and an expiry.

**where:** `packages/trappoint-migrate/src/trappoint_migrate/lock.py:5` states the platform fact
— *"``pg_advisory_lock`` does not exist in CockroachDB"* — and lines 5-16 give the three
consequences. The lease lifecycle is lines 62 (INSERT), 79 (conditional UPDATE), 122 (renew),
149 (DELETE), 164 (context manager).

**why it is an upgrade rather than a workaround**, quoting `lock.py:10-16` in its own terms:

* **it outlives the process**, so a killed migrator leaves the lease held and the next run must
  decide what to do about it — *"It waits for expiry; it never steals."*
* **it has to be renewed**, because a long schema change can outlast any lease short enough to
  be useful after a crash;
* **taking over an expired lease is a conditional `UPDATE`**, not delete-then-insert. The
  condition `expires_at < now()` is evaluated **by the database**, so two migrators racing to
  reclaim one expired lease cannot both win.

The third bullet is the one that matters: the mutual exclusion a session lock would have given
is recovered from the database's own concurrency control, which is the same mechanism §2.1 and
§2.2 are about.

**and the DDL discipline that goes with it** (`db.py:9-20`): `40001` is retried **only for
bookkeeping transactions**; DDL is attempted exactly once, ever, because a CockroachDB DDL
statement starts a background job and *"did it happen"* is a question `SHOW JOBS` answers, not a
question a retry loop should guess at. On a job-name collision the migrator refuses to advance
the version and says so: `db.py:250` — *"The version is NOT advanced; inspect SHOW JOBS before
retrying."*

**verify in 60s:**
`grep -n "advisory" packages/trappoint-migrate/src/trappoint_migrate/lock.py` → line 5,
*"``pg_advisory_lock`` does not exist in CockroachDB."* Then, that the lease is a real relation
rather than a description of one:

```bash
docker exec trappoint-crdb ./cockroach sql --insecure -d mainline_demo \
  -e "SELECT * FROM trappoint.schema_lock;"
```

Run 2026-08-16 — the header is the point, and the emptiness is the correct state for a cluster
with no migration in flight:

```
lock_name	holder	acquired_at	expires_at	reason
```

**say this:** *"CockroachDB has no advisory locks, so our migrator holds its lease as a row with
an expiry — and a crashed migrator then leaves a lease that is visible and inspectable instead
of a mutex that silently vanished. It waits for expiry rather than stealing, and the takeover is
a conditional `UPDATE` the database evaluates, so two migrators racing for one expired lease
cannot both win. DDL itself is attempted exactly once, ever: a CockroachDB schema change is a
background job, so a retry loop guessing at whether it landed is the wrong instrument — the
migrator refuses to advance the version and tells you to read `SHOW JOBS`."*

**never say:** *"we use advisory locks"*, *"we retry DDL"*, or that the lease can be stolen —
`lock.py:11` is explicit: *"It waits for expiry; it never steals."*

---

### 2.10 The version pin, served publicly

**state:** `LIVE`

**what it is:** CockroachDB **CCL v26.2.5** is pinned, the local container and the deployed
origin report the identical build string, and the deployed origin serves it to anyone with no
credential.

**where:** `GET /v1/health` on the live origin; the local container as measured in §0.1.

**verify in 60s:** §0.2. One `curl`, no credential of any kind sent — this worker ran it exactly
as printed. (That the Function URL is configured `authorization_type = NONE` is W1's row to
carry; this row attests only that an unauthenticated `GET` returned the version.)

**say this:** *"Our CockroachDB version is not a claim in a README — a judge reads it out of the
live origin in one unauthenticated request, together with the 271-of-271 deploy chain and the
schema fingerprint, and it is the same build string as the container we measure against:
`CockroachDB CCL v26.2.5 … built 2026/07/28 18:56:00`."*

**never say:** anything about the version without noting `CCL`, which is what the build
actually reports.

---

### 2.11 Multi-region shape — stated honestly, because it is not used

**state:** `NOT-AVAILABLE`

**what it is:** this project uses **no** CockroachDB multi-region feature. Not `SET PRIMARY
REGION`, not `ADD REGION`, not `REGIONAL BY ROW`, not `REGIONAL BY TABLE`, not `GLOBAL`, not
`SURVIVE … FAILURE`.

**verify in 60s, part one — the cluster:**

```bash
docker exec trappoint-crdb ./cockroach sql --insecure \
  -e "SELECT database_name, primary_region, regions, survival_goal FROM [SHOW DATABASES]
      WHERE database_name = 'mainline_demo';"
```

Run 2026-08-16, output verbatim:

```
database_name	primary_region	regions	survival_goal
mainline_demo	NULL	{}	NULL
```

`primary_region` is `NULL`, `regions` is empty, `survival_goal` is `NULL`. The default range
carries `num_replicas = 1` and `cockroach node status` lists **one** node with an empty
locality.

**verify in 60s, part two — the repository:**

```bash
grep -rniE "REGIONAL BY ROW|REGIONAL BY TABLE|SURVIVE .*FAILURE|ADD REGION|SET PRIMARY REGION|GLOBAL TABLE" \
  --include="*.sql" --include="*.py" .
```

Zero hits in SQL or Python. (One hit in `tests/deploy/test_judge_walk.py:1566` is prose about a
red walk *surviving* a failure, unrelated.)

**verify in 60s, part three — the managed cluster.** `evidence/ccloud/cluster-list.txt`, captured
2026-08-10 from `ccloud cluster list -o json`, records the Cloud cluster as
`plan SERVERLESS`, `cloud_provider AWS`, `cockroach_version v26.2.5`,
`regions [{ "name": "ap-southeast-1", "primary": true }]` — **one** region, marked primary
because a Serverless/Basic cluster always has one. That is a tier fact, not a design choice, and
`docs/submission/MUST-NOT-CLAIM.md:64` already rules on it.

**say this:** *"We do not claim multi-region. The cluster is CockroachDB Cloud Basic in
`ap-southeast-1`, one region, and the local node we measure against is a single node with an
empty locality and `num_replicas = 1`. What we do claim is the isolation and retry contract,
which is the part of the distributed story a single node can prove and this repository does
prove. `SHOW DATABASES` returns `primary_region NULL` and we would rather you read that from us
than find it."*

**never say:** *"globally distributed"*, *"survives a region failure"*, *"multi-region memory"*,
or anything implying a replica outside `ap-southeast-1`.

---

## 3. THE THREE CORRECTIONS THIS PAGE MAKES

W7 must carry all three into the master census.

**C1 — `crdb_internal` (plan §3 audit target).** The existing row
`evidence/tool-usage/crdb-features.json#rows.crdb_internal` is `EXERCISED` with 89 matching
files, and it conflates two opposite things. Split it. The **schema** is refused `42501` by
platform default on v26.2.5 and **no live path touches it** (`grep` over
`verticals/mainline/apps/demo-api/src/` returns 0). The **HLC builtin** is
`cluster_logical_timestamp()` — unqualified — and it *is* LIVE in the demo's request path, while
the qualified spelling returns `42883 unknown function`.
`docs/submission/DEVPOST.md:124` says *"`crdb_internal` for the HLC ordering the ledger"* and
must be rewritten.

**C2 — follower reads (plan §3 audit target) are CONFIRMED, not downgraded.**
`tests/integration/fixity/test_fixity_cluster.py::test_a_follower_read_transaction_reports_its_own_hlc`
**passed today** against the local cluster — JUnit XML in §2.5: `tests=3 failures=0 errors=0
skipped=2`. The row stays `EXERCISED` / census-state `REPO`. Its CI skip is a *named* skip for a
missing cluster, not an absent capability.

**C3 — `gc.ttlseconds` is 4500, not 14400.** The measured retention on the pinned local node is
**4500 seconds (75 minutes)**, matching `evidence/gate-refusal/proof-20260810T004200Z.json`,
CF-46's docstring and `docs/TOOL-USAGE.md`. `packages/trappoint-recall/src/trappoint_recall/eval/splits.py:54`
still carries `GC_TTL_SECONDS_DEFAULT = 4 * 60 * 60` and prints `14400 (4.0h)` in its refusal
message. The refusal is unconditional so nothing is broken; the *explanation* is generous by a
factor of 3.2, in the direction that understates our own case. Nobody should write "4 hours" in
the submission. See §6.

---

## 4. DETECTORS, so `scripts/submission/capture_tool_evidence.py` can re-derive these rows (plan R6)

Proposed only. **No worker touches the generator** — this is the input a follow-up needs.

| proposed key | detector | anchor (hand-checked) | verdict |
|---|---|---|---|
| `crdb_serializable` *(exists)* | `pattern="SET TRANSACTION ISOLATION LEVEL SERIALIZABLE"` | `gate_run.py:603` | EXERCISED |
| `crdb_savepoint` **(new)** | `pattern=r"ROLLBACK TO SAVEPOINT"` | `gate_run.py:671` | EXERCISED |
| `crdb_read_committed` **(new)** | `pattern=r"READ COMMITTED"` | `cf45_read_committed.py:78` | DESIGNED — the case is CANNOT RUN; see §2.3 |
| `crdb_retry_40001` **(new)** | `pattern=r"\b40001\b"` | `db.py:154` | EXERCISED — `evidence/deploy/cloud-contention.json` |
| `crdb_hlc_builtin` **(new)** | `pattern=r"cluster_logical_timestamp\(\)"` | `gate_run.py:374` | EXERCISED, live path |
| `crdb_internal` *(exists — split)* | `pattern=r"crdb_internal"` | `limits.py:75` | NOT-AVAILABLE by default (`42501`); used as a negative control |
| `crdb_follower_reads` *(exists)* | `pattern=r"follower_read"` | `0180c_role_agent_patroller.sql:37` | EXERCISED — §2.5 JUnit |
| `crdb_as_of_system_time` *(exists)* | `pattern=r"AS OF SYSTEM TIME"` | `cf46_time_travel_cannot_reach.py:106` | EXERCISED — CF-46 green today |
| `crdb_changefeed` *(exists)* | `pattern=r"CREATE CHANGEFEED"` | `trappoint-migrate/README.md:253` | DESIGNED — `SHOW CHANGEFEED JOBS` = 0 |
| `crdb_no_advisory_locks` **(new)** | `pattern=r"schema_lock"` | `lock.py:5` | EXERCISED |
| `crdb_multi_region` **(new)** | `pattern=r"REGIONAL BY\|SURVIVE .*FAILURE\|ADD REGION"` | none — zero hits is the finding | NOT-AVAILABLE |

A NOT-AVAILABLE row has no anchor by construction; its evidence is the empty result, which is
why the pattern matters more there than anywhere else. Plan §0.5 already argues that a
checked-and-absent row is a credibility asset, and two of the eleven rows above are exactly
that.

Every SQLSTATE quoted on this page is read from a driver's `sqlstate` field, never from a
rendered error string — the rule `docs/TOOL-USAGE.md` adopted after the `cockroach sql` client
printed a refusal without one and nearly put a false correction into a public document.

---

## 5. WHAT W7 MAY LIFT, IN AXIS-ONE ORDER (plan R5)

Ranked by what argues *Agentic Memory Design* hardest, not by feature count.

1. **§1** — the same history, refused six-for-six at `SERIALIZABLE` and admitted six-for-six at
   `READ COMMITTED`. One paste, two numbers, and it is the whole argument for why the memory
   layer is a database and not a cache.
2. **§2.1** — four beats, two of them refusals, inside one transaction that is rolled back, with
   the isolation level and both logical timestamps in the response body.
3. **§2.4** — `AS OF SYSTEM TIME` used, and then proved unable to reach ninety days; and the
   evaluation harness refusing to execute any SQL containing it.
4. **§2.2** — `40001` retried as undecided rather than failed, refusals attempted once ever, and
   `40003` deliberately excluded.
5. **§2.6 / §2.11 / §2.7** — the three places we say what we do **not** have.

---

## 6. UNDECIDABLES, ESCALATED NOT GUESSED (plan R7)

Nothing here was acted on. All are the founder's call.

**Q1 — `splits.py:54` says 4 hours; the cluster says 4500 seconds.** The refusal is
unconditional, so this is a documentation defect, not a behaviour defect. Fixing it touches a
non-census source file and a `Verified:` docstring; out of scope for W4. *Recommendation: leave
the code, and never write "4 hours" in the submission.*

**Q2 — CF-45 and 45 other cases cannot run on the deployed schema** because the world-builder
names `clause_version.body_sha256` and the schema calls it `canon_sha256`. A one-column rename
in the corpus helper would plausibly return a large block of the conformance suite to service
before the deadline — and would move `10 passed` upward, which is a Technological-Implementation
number. It is also a code change to a corpus under a ratchet, two days out, with an unknown
blast radius. *Not attempted. Flagged as the single highest-leverage engineering decision left
in this domain.*

**Q3 — the deployed Lambda's own retry loop has never been observed firing in production.**
Proving it needs induced contention against the live origin, which means writes. The standing
`materialise_checks` / `exposure_receipt` INSERT gap stays open and this page does not reopen
it. *The `UNPROVEN` wording at `retry.py:117` is correct and should stay.*

---

## 7. THE TWO SCRIPTS, IN FULL

Both write only to scratch database `w_w4`. Neither touches a product table, AWS, or a
credential.

### 7.1 `w4_isolation_race.py` — SERIALIZABLE vs READ COMMITTED, six crossed races each

This is the exact file whose output is quoted in §1 and §2.2. Run it with
`python -u w4_isolation_race.py`.

```python
import psycopg

DSN = "postgresql://root@127.0.0.1:26257/w_w4?sslmode=disable"


def one_race(level: str) -> tuple[str | None, str]:
    a = psycopg.connect(DSN, autocommit=False, application_name="w4-race-a")
    b = psycopg.connect(DSN, autocommit=False, application_name="w4-race-b")
    try:
        for c in (a, b):
            c.execute("SET statement_timeout = '5s'")
            c.execute(f"SET TRANSACTION ISOLATION LEVEL {level}")
        a.execute("SELECT v FROM w4_race WHERE id = 2").fetchone()  # A reads row 2
        b.execute("SELECT v FROM w4_race WHERE id = 1").fetchone()  # B reads row 1
        a.execute("UPDATE w4_race SET v = v + 1 WHERE id = 1")  # A writes what B read
        b.execute("UPDATE w4_race SET v = v + 1 WHERE id = 2")  # B writes what A read
        loser = None
        for name, c in (("A", a), ("B", b)):
            try:
                c.commit()
            except psycopg.Error as exc:
                loser = (exc.sqlstate, f"{name} lost :: " + " ".join(str(exc).split())[:96])
        return loser or (None, "both committed (write skew admitted)")
    finally:
        for c in (a, b):
            try:
                c.rollback()
            except Exception:
                pass
            c.close()


boot = psycopg.connect(DSN, autocommit=True)
with boot:
    (ver,) = boot.execute("SELECT version()").fetchone()
    print("cluster:", ver)
    (rc_enabled,) = boot.execute(
        "SHOW CLUSTER SETTING sql.txn.read_committed_isolation.enabled"
    ).fetchone()
    print("sql.txn.read_committed_isolation.enabled =", rc_enabled)
    rc = psycopg.connect(DSN, autocommit=False)
    rc.execute("SET TRANSACTION ISOLATION LEVEL READ COMMITTED")
    (lvl,) = rc.execute("SHOW transaction_isolation").fetchone()
    print("SHOW transaction_isolation inside the downgraded txn =", lvl)
    try:
        print("cluster_logical_timestamp() at READ COMMITTED ->",
              rc.execute("SELECT cluster_logical_timestamp()").fetchone()[0])
    except psycopg.Error as exc:
        print("cluster_logical_timestamp() at READ COMMITTED ->",
              exc.sqlstate, " ".join(str(exc).split())[:60])
    rc.rollback()
    rc.close()
    boot.execute("DROP TABLE IF EXISTS w4_race")
    boot.execute("CREATE TABLE w4_race (id INT PRIMARY KEY, v INT NOT NULL)")
    boot.execute("INSERT INTO w4_race VALUES (1, 0), (2, 0)")

for level in ("SERIALIZABLE", "READ COMMITTED"):
    hits = 0
    for trial in range(1, 7):
        state, note = one_race(level)
        hits += state == "40001"
        print(f"  {level:14s} trial {trial}: sqlstate={state} :: {note}")
    print(f"{level:16s}: 40001 in {hits} of 6 crossed races")
```

Both connections must reach the write stage before either commits — that is what makes the
history unorderable. A shape where one side commits before the other reads is legally
serializable and produces `0 of 6` at **both** levels; this worker measured that first, by
accident, and it is the trap anyone reproducing this will hit.

### 7.2 `w4_aost.py` — the `AS OF SYSTEM TIME` horizon

Run this **after** `§7.1`, which leaves the two-row `w4_race` behind.

```python
import time
import psycopg

DSN = "postgresql://root@127.0.0.1:26257/w_w4?sslmode=disable"
c = psycopg.connect(DSN, autocommit=True)

# 1. time travel actually returns PAST state, inside the window
(before,) = c.execute("SELECT count(*) FROM w4_race").fetchone()
c.execute("INSERT INTO w4_race VALUES (99, 0)")
(after,) = c.execute("SELECT count(*) FROM w4_race").fetchone()
time.sleep(6)
(past,) = c.execute("SELECT count(*) FROM w4_race AS OF SYSTEM TIME '-5s'").fetchone()
print(f"rows before insert={before}  now={after}  AS OF SYSTEM TIME '-5s'={past}")

# 2. and where it stops
for horizon in ("-10s", "-90m", "-2160h"):
    q = f"SELECT count(*) FROM w4_race AS OF SYSTEM TIME '{horizon}'"
    try:
        (n,) = c.execute(q).fetchone()
        print(f"{horizon:8s} -> {n} row(s)")
    except psycopg.Error as exc:
        print(f"{horizon:8s} -> SQLSTATE {exc.sqlstate} :: " + " ".join(str(exc).split())[:120])

(z,) = c.execute("SHOW ZONE CONFIGURATION FROM RANGE default").fetchall()[0][1:2]
print("gc.ttlseconds line:", [l.strip() for l in z.splitlines() if "gc.ttlseconds" in l])
c.close()
```

The zone configuration's retention is in the **second** column of `SHOW ZONE CONFIGURATION`;
reading only the first silently measures the string `RANGE default`. CF-46 scans every column
for the same reason (`cf46_time_travel_cannot_reach.py:87-95`).

---

## 8. SCOPE NOTE

W1 owns the AWS story of `db.py`, `retry.py`, `gate_run.py` and `cr_gate_run.py` — SigV4, SSM,
the single-dependency deployment package. This page owns only their SQL behaviour. Neither
worker edited the other's files; the four Lambda modules were **read, never modified**.

Nothing on this page required a deploy, a `terraform apply`, an SSM write, a grant, a commit, or
a credential. Two `curl` calls were made to the public origin: one `GET /v1/health` and one
`POST /v1/demo/gate-run`, which is the unauthenticated demo endpoint that rolls its own
transaction back — its response reported `persisted: false` and `persistence_check.identical:
true`, so the origin's state is unchanged. Every write went to scratch database `w_w4`.
