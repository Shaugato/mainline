<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# `40001` is reachable HERE — the negative control for the retry work

**Worker:** `w4` (judge-can-sign) · **Measured 2026-08-14 on TRAPPOINT**, HEAD `eefae1c`,
working tree dirty (five other workers of this wave were landing files while these numbers
were taken; see §7) · **local single-node CockroachDB CCL v26.2.5**, psycopg 3.3.4,
Python 3.13.14, Windows 11.

**Verdict: the brief's premise is false. `40001 RETRY_SERIALIZABLE` is produced by this
workstation's single-node CockroachDB, by the shape `_seed_permit` actually performs, in 6
of 6 races. A retry guard shipped without a control that fires is an untested guard dressed
as a fix, and this document is the control that fires. Nothing here is evidence about
CockroachDB Cloud, which remains UNPROVEN by this wave.**

---

## 0 · The sentence this document exists to retire

The wave's brief says:

> the demo deploys to CockroachDB **Cloud**, which is multi-node and returns
> `40001 RETRY_SERIALIZABLE` under contention **that single-node Docker never produces**.

The lead's ruling R6 had already measured that as false with a synthetic two-row race. This
document measures it false with the **product's own transaction shape**, and turns the
measurement into a test that fails when it stops being true.

**No worker in this wave may write "this cannot be tested without Cloud."** It is
measurably untrue on the machine the wave is being written on.

---

## 1 · The command, and what it asserts

```
.venv/Scripts/python.exe -m pytest tests/concurrency/test_seed_permit_needs_retry.py \
    --crdb=reuse -q -p no:cacheprovider -s --junit-xml=<report>
```

`tests/concurrency/test_seed_permit_needs_retry.py` holds **two tests that fail
independently**, which is the whole point of a negative control:

| test | asserts |
|---|---|
| `test_the_unguarded_seed_permit_shape_raises_a_real_40001` | the UNGUARDED shape raises `40001`, every observed SQLSTATE is inside the modelled taxonomy, at least one caller commits, and the loser leaves **no rows at all** |
| `test_the_same_shape_under_the_adapter_completes` | the SAME work through `trappoint_testkit.txn.run_txn` commits for **every** caller, a `40001` was **actually retried** (spied, not assumed), and both callers' rows are in the database afterwards |

The second test's middle clause is the one that keeps it honest. A guarded run in which
nothing ever conflicted would pass "nobody raised" while demonstrating nothing whatsoever
about the guard, so the spy's retry count is asserted `>= 1`.

**Result, from the `--junitxml` `testsuite` attributes and not from a terminal scroll:**

| | tests | failures | errors | skipped | time |
|---|---|---|---|---|---|
| `test_seed_permit_needs_retry.py` | **2** | **0** | **0** | **0** | 136.3 s |
| repeat, with `test_txn.py`'s 17 hermetic tests in the same session | **19** | **0** | **0** | **0** | 110.6 s |

Most of that time is the 271-file migration chain the module applies into a database of its
own (113.9 s and 78.0 s in the two runs). See §6. **The census below was identical in both
runs**, which is the difference between a control and an anecdote.

---

## 2 · The environment, stated because a concurrency result without one is an anecdote

| | |
|---|---|
| cluster | `CockroachDB CCL v26.2.5 (x86_64-pc-linux-gnu, built 2026/07/28 18:56:00, go1.25.5)` |
| nodes | **1** (`crdb_internal.gossip_nodes` → 1; every sampled range has one replica) |
| DSN | `postgresql://root@127.0.0.1:26257/…?sslmode=disable` |
| `SHOW default_transaction_isolation` | `serializable` |
| every transaction below | opens with `SET TRANSACTION ISOLATION LEVEL SERIALIZABLE`, per `spec/errors.md` §2.1 — never inherited from a pool default |
| driver | psycopg 3.3.4 |

---

## 3 · The plant: two callers, one subject, the shape `_seed_permit` performs

`verticals/mainline/apps/demo-api/tests/test_transitions.py:224` — `_seed_permit` — reads
the demo subject, writes a `permit`, a `permit_clause`, a `boundary_certificate`, a
`recall_run`, a `silence_receipt`, a `blocking_check`, an `exposure_receipt`, an
`exposure_line`, two `permit_event` rows and the two `UPDATE mainline.permit` statements
that move the head, and commits **once**, with no retry of any kind. Fourteen client
statements; CockroachDB's own transaction metadata numbers them `seq=29` by the time they
reach `COMMIT`, which is where the brief's "roughly 29 statements" comes from.

The control races the part of that shape two callers can genuinely run at once over one
subject:

* the subject's `permit` row is created **once**, before the race, by the three statements
  `_seed_permit` opens with. Racing that would be two INSERTs of one `permit_id`, which is
  `23505` — a **refusal**, which `spec/errors.md` §4 requires be attempted exactly once and
  never retried. It is not a serialisation conflict and must not be dressed as one.
* both callers then read the subject's `state` and `head_seq`, write their children of it,
  append a `permit_event` at the sequence they read, and move the head.

That is a read-modify-write on one row from two SERIALIZABLE transactions: the loser is
`40001` **by construction**, not by luck. It is also the contention the demo actually has —
two judges reaching `POST /v1/demo/gate-run` at the same moment (lead's ruling R11).

A `threading.Barrier` makes both callers finish READING before either starts WRITING. That
is an interleaving device, not a thumb on the scale: two clients that arrive together read
together, and forcing it makes the race repeatable instead of a coin toss about thread
scheduling. It fires once per race — a *retry* must not wait on a partner that has already
finished.

---

## 4 · What was measured

### 4.1 The unguarded shape — 6 races, 12 callers

```
[control] unguarded census over 6 races: {'40001': 6, '00000': 6}
```

**Six of six races produced exactly one `40001` and one commit.** No other SQLSTATE appeared;
the test asserts that too, because a census entry outside `{00000, 40001, 23514, 23503,
23505, P0001}` would be a mechanism refusing this shape for a reason nobody has modelled.

The exhibit, quoted rather than paraphrased:

```
restart transaction: TransactionRetryWithProtoRefreshError: WriteTooOldError: write for key
/Table/31248/1/"…"/0 at timestamp 1786665610.710035062,0 too old; must write at or above
1786665610.711517187,1: "sql txn" meta={id=45106f45 key=/Table/31281/1/"…"/0
iso=Serializable pri=0.01593651 epo=0 ts=1786665610.711517187,1
min=1786665610.710035062,0 seq=7} lock=true stat=PENDING …
```

and, from the variant in §5, the other costume the same code wears:

```
restart transaction: TransactionRetryWithProtoRefreshError: TransactionRetryError: retry txn
(RETRY_SERIALIZABLE - failed preemptive refresh): "sql txn" meta={id=7bcba616
key=/Table/27537/1/"…"/0 iso=Serializable pri=0.00866982 epo=0 ts=1786663502.961019263,1
min=1786663502.958971274,0 seq=29} lock=true stat=PENDING …
HINT: See: https://www.cockroachlabs.com/docs/v26.2/transaction-retry-error-reference.html#retry_serializable
```

**Both are SQLSTATE `40001`.** `RETRY_WRITE_TOO_OLD` and `RETRY_SERIALIZABLE` are two
reasons for one verdict, and a client that discriminated on the message instead of the code
would have got one of them wrong. `trappoint_core.retry` discriminates on the code.

**What the defect costs, asserted per race.** After each unguarded race the control counts
`permit_event` rows for that subject and requires the count to equal the number of callers
that committed. It does: **one**. The loser does not merely see an exception — it loses the
entire history it was writing: a recall run, a Proof of Exhausted Recall, an obligation, the
exposure receipt that displayed it, the line that bound them, and the event that claimed it
disposed of.

### 4.2 The same work under the adapter — 6 races, 12 callers

```
[control] guarded: 12 commits, 6 retried 40001(s)
```

Twelve of twelve callers committed. Six `40001`s were met and retried — one per race,
exactly the losers of §4.1. Afterwards the database holds `2 × 6 = 12` `permit_event` rows
and 12 `exposure_line` rows across the six subjects: **both** callers' whole histories, not
one and a fragment.

That last count is also what proves the retry **re-read** rather than replayed. The loser's
second attempt writes `seq = 2` from state `checks_materialised`, because it read the head
the winner had moved; a replay of the first attempt would have written `seq = 1` again and
met the event chain's unique index. `spec/errors.md` §2.1 in one row of a count.

### 4.3 A refusal the database was right about, met on the way

The first guarded run failed with `GateRefused: 23505 blocking_check_dedupe_key_key`.
`0058_blocking_check.sql` gives `blocking_check` a **server-computed**
`dedupe_key = digest(permit_id | cr_id | clause_uuid | commit_id | precursor_event_id |
origin)` under `UNIQUE (dedupe_key)`. Two callers materialising the *same* finding against
one subject are ONE obligation, and the second is refused.

**That refusal is correct and was not worked around.** The loop attempted it exactly once
and surfaced it, which is the specified behaviour. What was wrong was the plant: two
concurrent recall runs produce two *different* findings, so each caller now carries its own
`origin` and the obligations are distinct **by content** rather than by a collision the
retry loop was being asked to paper over. Verified directly: four distinct origins against
one subject insert cleanly and `permit.open_blocking` counts 4.

---

## 5 · A weaker plant, measured and REJECTED — and what it says about CI

The first plant raced two callers each running the WHOLE shape for a **different** new
permit, sharing only the read of the demo subject. Its results:

| database | permits in `mainline.permit` | races | `40001` |
|---|---:|---:|---:|
| built, then used by earlier probes | 73 | 6 | **6 of 6** |
| built the same way, raced immediately | 13 | 6 | **0 of 6** |
| the used one, re-raced later to check it was not ambient load | 73 | 3 | **3 of 3** |

`EXPLAIN` of the shared read is **identical** in both databases — point spans on
`permit@pk_permit`, `permit_clause@pk_permit_clause` and `blocking_check@bc_open`, a lookup
join on `site@site_pk` — so the plan is not the difference. Bisecting the statement list on
the used database put the onset of contention exactly at the `mainline.exposure_receipt`
INSERT (statements 1-7 never conflicted; 8 onwards always did). The obvious hypothesis, that
`cluster_logical_timestamp()` in that statement pins the commit timestamp and so forbids a
preemptive refresh, was tested by substituting a literal and **refuted**: the conflict
persisted 3 of 3.

**The mechanism was not isolated, so no claim is made about it.** The variant was rejected
as a plant because a control whose firing depends on how used the database is cannot be
trusted when it stays silent.

It is recorded here because it says something uncomfortable that is worth a lead's
attention: **this defect is less visible in a fresh database than in a used one**, and the
database `_seed_permit` really runs against — `w_w4_api_transitions`, deliberately REUSED
across runs and holding one more permit per mutating test — is the used kind. A CI lane that
builds a database, runs once and throws it away is the configuration least likely to see
this, which is a plausible part of why it has never been seen.

---

## 6 · Cleanliness, and what this cost

* The control builds its own database through `trappoint-testkit`'s module-scoped
  `crdb_dsn` fixture, which **creates it on the session's one cluster and DROPS it**. The
  migration chain (271 files, ~114 s) and the demo history come from the repository's own
  `scripts/proof/gate_refusal.py`, not from a private copy of either.
* Nothing is written into a database another suite adopts. No row is written outside that
  database. Every scratch database this worker created while measuring — `w_w4_retry_probe`,
  `w_w4_retry_probe2`, and the isolated demo-api database `w_w4_ctl_api` used for the
  before/after suite runs — was dropped afterwards.
* The module is marked `requires_cluster` and `slow`, and both tests carry
  `@pytest.mark.timeout(900)` because the repository-wide default of 120 s covers setup and
  the chain does not fit in it.

---

## 7 · What is NOT proven, in the words the ruling requires

**This is a SINGLE-NODE observation.** One node, one replica per range, no cross-node
latency, no clock-uncertainty restart, and no `RETRY_WRITE_TOO_OLD` arising from a
follower's clock rather than from a local write.

CockroachDB **Cloud** is multi-node and adds **rate and variety** — clock-uncertainty
restarts, cross-node latency, more shapes of `40001` — **not existence**. This measurement
therefore shows the guard is *needed and works here*. It does not show what the guard does
against Cloud, and no run in this wave has reached Cloud: per the lead's ruling R7, the
Cloud DSN is a GitHub repository secret and is not present in this environment. **The Cloud
claim is UNPROVEN. Local green does not cover it, and this document may not be cited as
though it did.**

---

## 8 · Suite numbers, before and after, and a hazard worth naming

Command (both runs, from the `--junitxml` `testsuite` attributes — never a terminal scroll):

```
MAINLINE_W4_DATABASE=w_w4_ctl_api .venv/Scripts/python.exe -m pytest \
    verticals/mainline/apps/demo-api/tests --crdb=reuse -q -p no:cacheprovider \
    --junit-xml=<report>
```

| | tests | failures | errors | skipped | time |
|---|---:|---:|---:|---:|---:|
| BEFORE (09:32) | 556 | 22 | 23 | 0 | 204.4 s |
| AFTER (10:01) | 557 | 20 | 13 | 0 | 27.3 s |

**Neither of those is this worker's baseline and neither is this worker's result.** The set
of failing and erroring node ids was diffed between the two runs:

* **in AFTER but not in BEFORE: none.** No failure and no error appeared that was not
  already there.
* in BEFORE but not in AFTER: twelve, all in `test_defeaters.py` and `test_transitions.py`
  — another worker's files, landing while these numbers were taken.

None of this worker's four files is imported by the demo-api suite:
`trappoint_testkit/__init__.py` deliberately re-exports nothing from `txn.py`, so the
`trappoint_testkit.plugin` import in that suite's `conftest.py` does not reach it.

**The two lanes this worker did add files to were run whole, because a fix that breaks a
neighbour is worse than the defect:**

```
.venv/Scripts/python.exe -m pytest tests/concurrency packages/trappoint-testkit/tests \
    --crdb=reuse -q -p no:cacheprovider --junit-xml=<report>
```

| | tests | failures | errors | skipped | time |
|---|---:|---:|---:|---:|---:|
| `tests/concurrency` + `packages/trappoint-testkit/tests` | **83** | **0** | **0** | **1** | 159.6 s |

The one skip is pre-existing and correct: `test_single_merge.py`'s N=64 nightly arm, which
*"is skipped rather than scaled down because a 64-way race that quietly ran 8-way would
report a contention level nobody measured."*

`mypy --strict` was also asked the question a reader would ask of a protocol-typed adapter —
does a real `psycopg.Connection` satisfy `TransactionalConnection`? — with a caller that
uses `from_dsn` and a caller that writes its own factory. Both check clean, so the ~19 sites
ruling R10 hands to W5 will type-check against this signature.

**The hazard, named because it corrupted this worker's first measurement.** The first BEFORE
run used the default scratch database `w_w4_api_transitions` and reported 528 tests with 21
failures and 13 errors, including a wave of
`mainline_demo_api.retry.RetryBudgetExhausted: 40001 after 5 attempt(s) in 0.200s`. That is
`test_gate_run.py:143`'s **fixed** scratch-database name meeting more than one worker at
once — precisely the measurement hazard the lead's ruling R8 orders replaced with a content
fingerprint. Every number above was re-taken against a database only this worker used. A
before/after pair taken against a shared fixed-name database is not a measurement.

**One observation handed on rather than acted on**, because the file is not this worker's:
`RetryBudgetExhausted` was raised **4 times** in the isolated BEFORE run and **0 times** in
the AFTER run, from `verticals/mainline/apps/demo-api/src/mainline_demo_api/retry.py` — a
module another worker was landing while these numbers were taken. A retry budget of five
attempts exhausted inside 0.2 s against a *single-node* cluster during an ordinary suite run
is worth someone's attention: either the contention is heavier than the ladder, or the
retried unit is not the whole transaction from `BEGIN`, which is the failure mode
`spec/errors.md` §2.1 describes and the one `run_txn` above is shaped to make impossible.
This worker did not touch that file and makes no claim about which it is.

---

## 9 · Files

| file | what it is |
|---|---|
| `packages/trappoint-testkit/src/trappoint_testkit/txn.py` | the adapter: `run_txn(connect, work)` binds `trappoint_core.retry.run_gate` to a psycopg connection **factory**. No second retry loop, no second taxonomy (ruling R10) |
| `packages/trappoint-testkit/tests/test_txn.py` | 17 hermetic tests, no cluster: the factory contract, `40001` retried on a fresh connection each time, each refusal SQLSTATE attempted once ever, the backoff ladder with injected sleep and jitter |
| `tests/concurrency/test_seed_permit_needs_retry.py` | this document's measurement, as two independently-failing tests |
| `docs/diagnosis/retry-negative-control.md` | this document |
