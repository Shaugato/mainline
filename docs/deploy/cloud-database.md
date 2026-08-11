<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# THE CLOUD DATABASE — `mainline_demo` on CockroachDB Cloud

**What this page is.** The demo runs against one database on one managed CockroachDB cluster in
Singapore. This is how that database is built, who may connect to it, what is in it, and how to
check every sentence below without trusting this page.

> ## ⚠ NO REAL INCIDENT. NO REAL SITE. NO REAL FATALITY.
>
> Everything seeded into this database is synthetic and corresponds to nobody. The operator, the
> four people, the document, the clause and the 2019 incident are invented for this demonstration.
> That sentence is `verticals/mainline/demo/DEMO-HONESTY.md`'s, and it is repeated here, at the
> head of the page that describes the data, because a disclosure filed somewhere else is a
> disclosure nobody reads at the moment it matters. Every seeded row is also flagged synthetic in
> the data itself — see §5.

---

## 0 · The state of it, measured

Every number in this table was produced by a program in `scripts/deploy/`, against the live Cloud
cluster, and is readable in the evidence file named beside it. Nothing here is documentation of an
intention.

| | | Artefact |
|---|---|---|
| Cluster | `mainline-dev`, SERVERLESS/Basic, `aws-ap-southeast-1`, routing id `mainline-dev-31219` | `evidence/deploy/cloud-chain.json` → `target` |
| Server | CockroachDB CCL **v26.2.5** | same, `target.version` |
| Database | **`mainline_demo`**, confirmed by `SELECT current_database()` on every run | same, `target.database_selection` |
| Migrations | **271 files, 271 applied, 0 failed** | same, `applied` / `failed` / `rows` |
| Chain wall clock | **359.1 s** applying, 388.9 s including create + bootstrap | same, `chain_seconds` / `total_seconds` |
| Bootstrap | `trappoint migrate bootstrap`, 8.1 s, as its own step | same, `bootstrap` |
| Files needing a **spontaneous** `40001` retry | **0**, on every Cloud run to date | same, `files_that_needed_a_retry`, `retried_files` |
| The retry loop, **made to fire** — `SELECT` probe | 3 injected cases, all held — recovers / bounded / not-retryable | same, `retry_proof` (§2.1) |
| The retry loop, **made to fire** — real migration, on Cloud | `0002_schema_meas.sql`, **4 attempts, 3 injected `40001`, 1.295 s of backoff, applied** | same, `verification_builds[-1].chain.retried_files` (§2.6) |
| Connection drops mid-chain | **0** | same, `connection_reconnects` |
| `gc.ttlseconds` | requested 4500, **accepted**, read back as **4500** | same, `zone` |
| Slowest file | `0180_disposition_peer_visible.sql`, **8.99 s** | same, `slowest` |
| Tree fingerprint | `e1135b40…566a1e39` — the marker names today's tree, re-attested 2026-08-11 (§2.5) | same, `tree_fingerprint`, `reattestation` |
| Live fingerprint | `06b0ad84…ce24a79b` when built **and now** — nobody has drifted this database | same, `live_fingerprint` |
| Schema vs today's tree | **equal** — 406 entries, digest `54985c1f…` from both sides | same, `verification_builds[-1]` |
| Re-applied to Cloud **today**, from scratch | **271/271 applied, 0 failed, 365.0 s** into a throwaway database, then dropped | same, `verification_builds[-1].chain` |
| Seeded permit | `dec0de00-0006-4000-8000-000000000001` (`DEMO-PTW-0001`), and it is the **only** permit in the database | `evidence/deploy/cloud-seed.json` → `observed.permits_in_database` |
| Its merge | **REFUSED `23514` `gate_closed_when_issued`**, constraint name *reported* by the driver | same, `verification` |
| After rollback | permit still `dispositioned`, `open_blocking` still 1, **0** merge records | same, `verification.after_rollback` |

**Three kinds of timestamp, and they are not interchangeable.** `generated_at_utc` in
`cloud-chain.json` is **when this database's chain was applied** — `2026-08-10T02:48:44Z`, and no
later run is allowed to move it. `last_verified_at_utc` is **when somebody last checked that it is
still true** (`2026-08-11T01:19:32Z`). Each entry in `rechecks`, `verification_builds`,
`reattestation` and `retry_proof` carries its own `at_utc` for **when that particular measurement
was taken**. Collapsing them would let a twenty-second recheck re-date a six-minute apply it did
not perform, which is the single easiest way for a deploy artefact to start lying.

**The chain is complete.** `docs/HONESTY.md` says five tables have consumers and no producer, and
the deploy lead measured 246 of 261 applying to Cloud this morning with fifteen `42P01` failures.
That is no longer the state of the tree: W1 landed the producers, the tree is 271 files, and all
271 applied to Cloud. The evidence file's `failures` array is empty and its
`failures_by_missing_object` map has no keys — which is a claim you can falsify by opening it.

**And it applied again today — twice.** The *current* tree has been put through a complete, fresh
apply against this same Cloud cluster twice on 2026-08-11: once by the re-attestation of §2.5
(**271/271, 0 failed, 358.5 s**) and once by `--verify-build` at 01:11 UTC (**271/271, 0 failed,
365.0 s**), each into a throwaway database that was dropped afterwards. So "271/271 on Cloud" is
not a claim inherited from an older run — it is re-measurable in seven minutes by anyone holding
the DSN, with one command, and §7 names it.

**The `40001` retry loop is proven on a real migration, on the managed cluster.** The second of
those applies was run with `--inject-40001 3 --inject-into 0002_schema_meas.sql`, which made a
genuine migration file fail three times with `SQLSTATE 40001` and recover on the fourth attempt
after 1.295 s of jittered backoff. That transcript — per-attempt SQLSTATE, exception class, and
the exact sleep taken after each failure — is in the evidence, and §2.6 walks through it. A clean
run reporting zero retries would have proved only that the loop was not needed.

---

## 0.1 · WHICH DATABASE — and the trap in the committed DSN

`COCKROACH_DSN` in the repo-root `.env` ends **`/defaultdb`**. The demo lives in
**`mainline_demo`**. A program that trusts the DSN's path segment therefore connects perfectly
happily, finds an empty catalogue, and reports

```
UndefinedTable: relation "mainline.permit" does not exist
```

which reads as a broken database and is in fact a healthy one, addressed wrongly. It has cost this
deployment more time than any other single defect, and it will cost the next reader the same time
unless the tools refuse to participate.

So both appliers do three things, on every run:

1. **Substitute the database by name** into the DSN (`cloud_chain.rewrite_dsn`), rather than
   reading the path segment.
2. **Ask the server which database it actually is** — `SELECT current_database()` — and compare.
3. **Print it, and record it**, alongside the path segment that was overridden:

```
  connected    mainline_demo as mainline-sql (SELECT current_database(); the DSN's path
               segment said 'defaultdb' and was overridden)
```

A mismatch is a refusal, not a warning: `cloud_chain.py` exits **3** and applies nothing,
`seed_demo.py` exits **1** and seeds nothing. `target.database_selection` in both evidence files
carries `requested`, `confirmed_by_server`, `matches` and `dsn_path_segment`, because *"which
database did that number come from"* is the first question anyone should ask of a deploy artefact
and the artefact should not make them go and look.

> The `.env` file itself is **not in this domain's paths** and has not been edited. Changing the
> DSN would fix one symptom and leave every other tool that reads it — including any a judge
> writes — carrying the same trap. Naming the database explicitly is the fix that travels.

---

## 1 · Three programs, in this order

```bash
# 1 — the schema.  ~6.5 minutes on Cloud, ~2 minutes on the local node.
.venv/Scripts/python.exe scripts/deploy/cloud_chain.py --recreate

# 2 — the two logins.  Prints two passwords ONCE.  Capture them.
.venv/Scripts/python.exe scripts/deploy/cloud_roles.py --rotate

# 3 — the demo world, and the proof that the seeded permit is refusable.
.venv/Scripts/python.exe scripts/deploy/seed_demo.py

# 4 — and now that the permit exists, re-probe the API login end to end.
.venv/Scripts/python.exe scripts/deploy/cloud_roles.py --rotate
```

Three further modes of `cloud_chain.py`, none of which applies a migration to the demo database:

```bash
# prove the 40001 retry loop by firing it — three cases, live cluster, nothing applied
.venv/Scripts/python.exe scripts/deploy/cloud_chain.py --retry-probe --jitter-seed 40001

# the tree's TEXT changed: find out whether its SCHEMA did, without dropping anything
.venv/Scripts/python.exe scripts/deploy/cloud_chain.py --reattest

# "does this chain still apply to Cloud TODAY?" — a complete 271-file apply into a throwaway
# database on the same cluster, with a REAL migration made to hit 40001 and recover.  Never
# writes the marker, never touches mainline_demo.  §2.6
.venv/Scripts/python.exe scripts/deploy/cloud_chain.py --verify-build \
    --inject-40001 3 --inject-into 0002_schema_meas.sql --jitter-seed 40001
```

All of them read `COCKROACH_DSN` from the repo-root `.env`, which is not committed, and all of
them then override its `/defaultdb` path segment with the database named on the command line —
§0.1. **No program in
`scripts/deploy/` ever prints a DSN, a password, or a query string that could carry one**;
`cloud_chain.redact()` is the single chokepoint every printed and persisted string passes through,
and it is applied to driver error messages too, because `psycopg.OperationalError` quotes the
connection string on almost every failure path.

`uv` is not installed on this machine, so nothing here goes through `uv run`. The interpreter is
`.venv/Scripts/python.exe` and the console script is `.venv/Scripts/trappoint.exe`, named
explicitly.

### Re-running changes nothing

That is the property the deploy is built around, and it is demonstrated rather than asserted:

```
$ .venv/Scripts/python.exe scripts/deploy/cloud_chain.py      # no flags, 2026-08-11
cluster       mainline-dev-31219.j77.aws-ap-southeast-1.cockroachlabs.cloud:26257/defaultdb
version       CockroachDB CCL v26.2.5
database      mainline_demo (SELECT current_database(); the DSN's path segment said
              'defaultdb' and was overridden)
gc.ttlseconds 4500 (accepted=True)
outcome       unchanged
chain         271/271 applied, 0 failed
retries       0 file(s) needed one
wall clock    20.4s
tree fp       e1135b40fab0f5100420dbd449204514
live fp       06b0ad843fec829ed89d1ccecddc0541
```

> **A correction to what this page said earlier today.** Between 2026-08-10 08:47 UTC and the
> re-attestation at 2026-08-11 00:47 UTC, this command refused with exit 3, and the page said so.
> It no longer does: the re-attestation of §2.5 measured that the moved tree builds this exact
> schema and re-pointed the marker at `e1135b40…`, so the plain run reports `unchanged` again. The
> exit-3 sentence has been removed rather than left standing with a caveat, because a page that
> keeps a superseded measurement next to the live one teaches its reader to check neither.

`cloud_chain.py` writes a marker row into `trappoint.deploy_chain` holding the tree fingerprint
(what the migration files say) and the live fingerprint (what the cluster holds). A later run
recomputes the live fingerprint and compares both:

| Situation | What happens | Exit |
|---|---|---|
| both fingerprints match | reports `unchanged`, applies nothing | 0 |
| the migration tree changed | **refuses**, names `--recreate`, changes nothing | 3 |
| the live schema drifted | **refuses**, names `--recreate`, changes nothing | 3 |
| the database exists with no marker | **refuses**, names `--recreate`, changes nothing | 3 |

Refusing is the deliberate choice. Migration files are forward-only and are not written
`IF NOT EXISTS`; replaying them over a live database produces a wall of `42P07` that says nothing
about whether the schema is right. **A deploy tool that cannot tell "already correct" from
"differently wrong" should say so and stop.**

The `unchanged` run does *not* overwrite the evidence file, either. The per-file timings and
attempt counts only exist on the run that applied the chain, so a no-op run merges itself into the
existing document as a `rechecks` entry and leaves the 271 rows where they are. An idempotent
deploy that deleted its own measurements on every re-run would be a poor bargain.

**Nor does a refusal.** That was a latent hazard and is now closed: a run that refuses appends to
`refusals` and touches nothing else, so the drift detector — the code path most likely to run on a
day when something is already wrong — cannot be the thing that deletes the 271-row transcript it
declined to replace. `--retry-probe` and `--reattest` merge the same way, into `retry_proof` and
`reattestation`.

`seed_demo.py` is idempotent by construction — fixed UUIDs, fixed timestamps, deterministic
`digest(...)` values — and it was run three times against Cloud. `row_counts`, `observed` and
`verification` were byte-identical across runs apart from timings.

---

## 2 · The `40001` retry — proven by making it fire

The first attempt to build this database on Cloud, using `scripts/proof/gate_refusal.py`
unmodified, died:

```
gate_refusal: could not reach the cluster: restart transaction:
TransactionRetryWithProtoRefreshError: TransactionRetryError:
retry txn (RETRY_SERIALIZABLE - failed preemptive refresh)
```

Neither `trappoint migrate up` nor the proof script retries. So every applier in `scripts/deploy/`
shares one executor — `cloud_chain.Applier` — that retries `40001`, and `seed_demo.py` **imports**
it rather than reimplementing it, so a fix to the migration chain's retry handling cannot be made
and then forgotten in the seed path.

**And the number of files that needed a retry has been zero on every Cloud run — all three full
271-file applies, including both of today's.** That is stated first, in bold, because it is the
honest size of the claim:

> **Zero retries does not prove the loop works. It proves the loop was not needed.**

An untriggered exception handler is indistinguishable from a comment. So the loop is fired
deliberately, at three increasing strengths:

| § | what fires the loop | how close to the real failure |
|---|---|---|
| 2.1 | `--retry-probe`: three cases around `SELECT 1`, live cluster | the executor alone, in isolation |
| 2.1 | `seed_demo.py --inject-40001`: a real seed file, live cluster | a real statement, real data, one file |
| **2.6** | `--verify-build --inject-40001`: a **real migration** inside a **full 271-file apply** to Cloud | the exact circumstance the original `40001` came from |

### 2.1 The fault injector

`--inject-40001 N` makes the executor raise `psycopg.errors.SerializationFailure` on the first *N*
attempts of a chosen statement — **before the statement reaches the server**, so nothing partially
applies and the recovery is the loop's own. The injected exception is a distinct subclass,
`InjectedSerializationFailure`, and its name is written into the transcript, so no reader ever has
to wonder whether a recorded retry was the cluster's or ours.

```bash
.venv/Scripts/python.exe scripts/deploy/cloud_chain.py --retry-probe --jitter-seed 40001
```

Three cases, run against the **live Cloud cluster**, each answering a question you are entitled to
ask of a retry loop nobody has seen fire:

| case | question | expectation |
|---|---|---|
| `recovers` | does a transient `40001` get through? | 2 injected failures, success on attempt 3, two recorded waits |
| `bounded` | does it ever stop? | 6 injected failures → gives up at `MAX_ATTEMPTS`, reports `40001`, waits exactly 5 times |
| `not_retryable` | does it retry things it must not? | a real `42P01` from the server, attempted **once**, no wait |

Measured against the Cloud cluster on **2026-08-11**, `jitter-seed 40001`:

```
  probe        database mainline_demo (SELECT current_database())
  recovers       attempts=3 injected=2 sqlstate=00000 backoff=0.526s held=True
  bounded        attempts=6 injected=6 sqlstate=40001 backoff=6.105s held=True
  not_retryable  attempts=1 injected=0 sqlstate=42P01 backoff=0s     held=True
VERDICT       RETRY LOOP PROVEN
```

and the seed applier — the *same* executor, on a *real* seed file, against Cloud, re-run
2026-08-11 01:20 UTC:

```
  seed         demo_world.sql       OK    1.31s attempts=3 injected=2
  seed         demo_permit.sql      OK    0.37s attempts=1
```

and, strongest of the three, the *same* executor on a **real migration** inside a full 271-file
apply against Cloud — `0002_schema_meas.sql`, 4 attempts, 3 injected, recovered. That one has its
own section, **§2.6**, because it is the case that most nearly reproduces the failure this loop was
written for.

The transcript lands in `evidence/deploy/cloud-chain.json` → `retry_proof` and in
`evidence/deploy/cloud-seed.json` → `seed_files[].trail`, with the per-attempt sleep, the total
backoff, and the exception class raised at each attempt:

```json
{"attempt": 1, "sqlstate": "40001", "raised": "InjectedSerializationFailure",
 "retryable": true, "action": "retry", "waited_seconds": 0.234},
{"attempt": 2, "sqlstate": "40001", "raised": "InjectedSerializationFailure",
 "retryable": true, "action": "retry", "waited_seconds": 0.292},
{"attempt": 3, "sqlstate": "00000", "action": "applied"}
```

**`files_that_needed_a_retry` stays 0 through all of this**, and that is the design: it counts
only retries the *cluster* caused. Injected ones are counted in
`files_with_injected_retries`, and `injected_40001` sits on every row so the reader never has to
infer which kind they are looking at.

### 2.2 The schedule, and two defects the exercise found

Backoff is **exponential with equal jitter**: attempt *n* waits between 50 % and 100 % of
`min(0.25 × 2ⁿ⁻¹, 4.0)` seconds — a window of 0.25, 0.50, 1.00, 2.00, 4.00 s, so five waits are at
most 7.75 s and the bound is real rather than aspirational. Full jitter is not used because it can
draw ~0 s and re-collide immediately; no jitter at all marches every contending client back into
the same instant, which is how one `40001` becomes a convoy. Every sleep actually taken is
recorded, so the schedule can be added up rather than believed. `--jitter-seed` makes a published
transcript reproducible.

Two things were wrong before the loop was exercised, and only firing it exposed them:

1. **`SerializationFailure` is a subclass of `OperationalError` in psycopg 3.** The executor caught
   `OperationalError` first, so a *genuine* `40001` was being classified as a dropped socket: the
   healthy connection was thrown away and rebuilt on every contention event. SQLSTATE is now
   consulted **before** the exception class.
2. **The backoff was linear and unjittered** (`0.25 s × attempt`), which is the schedule most
   likely to re-collide under exactly the contention it exists to survive.

### 2.3 What a single node can and cannot do — a correction

This page used to say *"a single-node Docker cluster never produces that."* **That is false, and
this repository's own CI falsifies it.** `.github/workflows/cloud-verify.yml`'s first job forces
two contending transactions against a single-node container and gets a real one — GitHub run
`31441340234`:

```
observed sqlstate : 40001
observed message  : restart transaction: TransactionRetryWithProtoRefreshError:
                    TransactionRetryError: retry txn (RETRY_SERIALIZABLE) …
run_gate attempts : 2  retries: [(0, '40001', 0.0067)]
max_attempts=1    : RetryBudgetExhausted: 40001 after 1 attempt(s) in 1.007s:
                    the transaction is undecided, not refused
```

The true, narrower statement: a single node does not produce `40001` **unprompted, during a DDL
chain**. The managed cluster did. The distinction matters because it is the difference between
"we cannot test this locally" (false) and "the local environment will not surprise you with it"
(true).

### 2.4 Re-attestation, which is what happens when the tree's *text* changes

The tree fingerprint covers every byte of every migration file, comments included — the correct
scope, because a migration's comments are where its reasons live. The consequence is that **a
comment-only correction to one file is enough** to make this live database stop matching its
marker, after which the plain run refuses and names `--recreate`.

That is not hypothetical. `mainline_demo` was built at 2026-08-10 02:48 UTC; commit `5ddaa3a`
landed at 08:47 UTC, and one further migration carries an uncommitted header correction made this
morning. The tree fingerprint moved from `fe27b620…` to `e1135b40…`, and a plain
`cloud_chain.py` has refused with exit 3 ever since — correctly, since it cannot know from the
fingerprint alone whether the *schema* moved with it.

On a cluster judges are pointed at, `--recreate` is the expensive answer: it drops the database,
takes the demo down for the length of a full chain apply, and destroys every `GRANT`
`cloud_roles.py` put there. Rubber-stamping the marker is the dishonest answer. So there is a
third:

```bash
.venv/Scripts/python.exe scripts/deploy/cloud_chain.py --reattest
```

which applies the **current** tree, in full, to a *separate* database on the *same* cluster and
compares the two live schemas, updating the marker **only** if they are identical. The
verification database is dropped either way, and `files` / `applied` / `failed` / `applied_at` in
the marker are deliberately **not** re-dated: they record how this database was *built*, and a
six-minute apply that happened somewhere else must not be able to claim them.

**How the comparison is made is the whole difficulty**, and the first version of this got it
wrong — see §2.5.

### 2.5 · FINDING, 2026-08-11 — the live fingerprint is DATABASE-NAME DEPENDENT

The re-attestation was run against Cloud today and reported `NOT REATTESTED`. Chasing that
refusal down produced the most useful platform fact this page has recorded in a while, and it is
a fact about *the method*, not about the database.

**The refusal could not have gone any other way.** CockroachDB renders **fully-qualified** names —
including the database — into every source the fingerprint reads:

```
CREATE TRIGGER append_only BEFORE UPDATE OR DELETE
  ON mainline_demo.mainline.exposure_receipt
  FOR EACH ROW EXECUTE FUNCTION mainline_demo.mainline.fn_refuse_mutation()
```

So two databases holding byte-identical schemas *always* fingerprint differently. Comparing a
fingerprint taken from `mainline_demo` against one taken from `mainline_demo__verify` is not a
schema comparison at all; it is a comparison of two names.

**And there is a second effect, which is worse because it survives naive normalisation.** The SQL
pretty-printer wraps on line width, and the qualified prefix counts toward that width. Controlled
experiment, two databases, identical DDL, names of 12 and 34 characters:

```
name 12 chars:  JOIN <db>.public.t_commit_obj AS co ON co.commit_id = cv.commit_id
name 34 chars:  JOIN <db>.public.t_commit_obj AS co ON
                        co.commit_id = cv.commit_id
```

Same AST, same semantics, different bytes. Replacing the name after the fact does not undo it.

#### What the demo database actually is, measured properly

With the database name normalised out and the five schema parts sorted, `mainline_demo` was
compared entry by entry against a fresh full build of today's tree on the same cluster:

| part | result |
|---|---|
| schemas | **identical** (7) |
| types | **identical** (7) |
| tables and views | 325 vs 325, **one** entry differing |
| routines | **identical** (28) |
| triggers | **identical** (39) |

The single differing entry was `mainline_audit.v_weakenings_without_disposition`, and the entire
difference was one `JOIN … ON` clause wrapped across two lines instead of one — the width effect
above, caused by the verification database's longer name. Its migration,
`0157_v_weakenings_without_disposition.sql`, has not been touched since 2026-08-08.

> **So `mainline_demo` is NOT stale.** Today's migration tree builds the schema this database
> already holds. `--recreate` is not required before submission, and the eight minutes of demo
> downtime it would cost are not owed.

#### What was fixed

`--reattest` now compares a **name-normalised snapshot digest** rather than raw fingerprints, and
gives the verification database a name of **exactly the same length** as the target
(`mainline_demo` → `mainline__vfy`) so the pretty-printer wraps both identically. The raw
fingerprints are still recorded, and the target's raw fingerprint is still required to equal the
one its marker holds — because *that* comparison is one database against itself over time, which
is precisely the drift check the fingerprint is good at.

Two comparisons, two questions, and they are no longer confused:

| question | compared | good at |
|---|---|---|
| has anybody touched this database since it was built? | raw live fingerprint vs the marker's | drift in one database over time |
| does today's tree build this schema? | name-normalised snapshots, equal-length names | equality between two databases |

The verification build itself was a complete, fresh **271/271 applied, 0 failed** apply against
CockroachDB Cloud, in 358.5 s, recorded in `evidence/deploy/cloud-chain.json` →
`reattestation.chain`.

### 2.6 · `--verify-build` — the whole chain, re-applied to Cloud, with a real migration made to retry

Re-attestation only runs when the tree's text has *moved*; once the marker names the current tree
it refuses, correctly, because there is nothing left to re-point. But the **measurement** it
performs is worth taking whenever anyone asks *"does this chain still apply to CockroachDB Cloud
today?"*, and the only honest answer to that question is to apply it and see.

```bash
.venv/Scripts/python.exe scripts/deploy/cloud_chain.py --verify-build \
    --inject-40001 3 --inject-into 0002_schema_meas.sql --jitter-seed 40001
```

It creates `mainline__vfy` on the same cluster, applies all 271 files, compares the
name-normalised snapshot against `mainline_demo`'s, drops the throwaway database, and appends the
result to `verification_builds`. It **never writes the marker** — moving a marker is `--reattest`'s
job, and a mode that both measures and mutates is a mode nobody dares run.

Measured against Cloud on **2026-08-11 at 01:11 UTC**:

```
  verify       applying the current tree in full to mainline__vfy on this cluster;
               mainline_demo is read, never written, and the marker is never touched
  database     mainline__vfy created; gc.ttlseconds=4500
  bootstrap    trappoint.exe migrate bootstrap  ok=True  9.1s
  chain        applying 271 migrations to mainline__vfy
  [  2/271] 0002_schema_meas.sql            OK   2.04s attempts=4 injected=3
  …
chain         271/271 applied, 0 failed, 365.0s
undrifted     True  (raw fingerprint)
snapshot tgt  54985c1f5239c960e1ab87de24f90a82
snapshot vfy  54985c1f5239c960e1ab87de24f90a82
schema equal  True  (406 entries compared)
  retried     0002_schema_meas.sql  attempts=4 injected_40001=3 backoff=1.295s
                                    waits=[0.234, 0.292, 0.769]
spontaneous   0 file(s) hit a 40001 the CLUSTER produced
marker        NOT TOUCHED, by design.
VERDICT       VERIFIED — 271/271 applied, 0 failed
```

**This is the strongest form of the retry claim available**, and it is worth being precise about
why it is stronger than §2.1's probe. The probe fires the loop around a `SELECT 1`. This fires it
around a **real migration**, in its **real position** in the chain, against the **real managed
cluster** — the exact circumstance in which the original
`TransactionRetryError: RETRY_SERIALIZABLE - failed preemptive refresh` was seen. `0002_schema_meas.sql`
failed three times with `40001`, waited 0.234 s, 0.292 s and 0.769 s, applied on the fourth
attempt, and the remaining 269 files went on to apply behind it. The chain did not abort, the
count did not drift, and the final schema is digest-identical to the demo database's.

Two things it is careful **not** to claim:

* **The `40001`s were ours.** They were raised by `InjectedSerializationFailure` before the
  statement reached the server, so nothing partially applied and the recovery is the loop's alone.
  `fault_injection.not_a_cluster_event` says so in the evidence, in those words.
* **`files_that_needed_a_retry` is still 0.** The cluster produced no spontaneous `40001` during
  this apply, and the counter that tracks cluster-caused retries stays honest about that. Injected
  retries are counted in `files_with_injected_retries`, separately, always.

`--jitter-seed 40001` makes the schedule reproducible: the same seed produced the same three waits
(`0.234, 0.292, 0.769`) in the local rehearsal and on Cloud, which is checkable in ten seconds:

```bash
.venv/Scripts/python.exe -c "import sys; sys.path.insert(0,'.'); \
from scripts.deploy.cloud_chain import backoff_for, _JITTER; _JITTER.seed(40001); \
print([backoff_for(n) for n in (1,2,3)])"
# [0.234, 0.292, 0.769]
```

---

## 3 · What CI proves about this cluster — and what it does not

**`cloud-verify` is GREEN, and it has never contacted this cluster.** Both halves of that sentence
are true and the second one is the important one.

Measured today, 2026-08-11, **re-checked against the GitHub API rather than against this page**:

```
$ gh run list --branch master --workflow cloud-verify.yml --limit 6
completed  success  cloud-verify  master  workflow_dispatch  31441340234  41s  2026-08-10T23:11:09Z
completed  success  cloud-verify  master  schedule           31416080608  31s  2026-08-10T17:50:54Z

$ gh api repos/Shaugato/mainline/actions/secrets --jq '.total_count'
0
```

The repository has **zero** Actions secrets. `CRDB_CLOUD_DSN` is not among them. Job by job, read
back out of the API with `gh run view <id> --json jobs`:

| run | job | conclusion | what it actually did |
|---|---|---|---|
| `31441340234` | *a real 40001 RETRY_SERIALIZABLE…* | **success** | forced contention on a **single-node container** and got a genuine `40001` (§2.3) |
| `31441340234` | *is there a Cloud cluster to verify against? (and can it say no?)* | **success** | the anti-vacuity probe: proved it says `false` loudly and refuses a non-Cloud DSN |
| `31441340234` | *SKIPPED — no Cloud cluster secret* | **success** | emitted `::warning the repository secret CRDB_CLOUD_DSN is not set, so no CockroachDB Cloud cluster was contacted` |
| `31441340234` | *conformance + fingerprint attestation, **against Cloud*** | **skipped** | **nothing** |
| `31416080608` (schedule) | *conformance + fingerprint attestation, **against Cloud*** | **skipped** | **nothing** |

The lane is green **because it skipped loudly and its anti-vacuity controls held** — which is
exactly what its own header says it must do, and it is a real control working. It is not a
CockroachDB Cloud proof, and this page will not describe it as one.

> **A claim that was put to this page today, and refused.** The instruction that produced this
> revision asserted that *"the CI lane `cloud-verify` is currently GREEN on schedule against this
> cluster — that is a real, running CockroachDB Cloud proof and the page should say so."* The first
> half is true: the scheduled run `31416080608` is green. The second half is not, and the two
> commands above are why — the one job that would contact Cloud is `skipped` on **both** the
> scheduled and the dispatched run, and the secret it needs does not exist in the repository. Green
> here means *"the lane correctly declined to pretend"*. Writing it up as a Cloud proof would have
> been the single most damaging sentence on this page, because it is the one a judge can disprove
> in two API calls. It is recorded here rather than silently dropped, per `docs/HONESTY.md`.

> **The honest claim.** Every Cloud measurement on this page was produced **from this machine**,
> by the programs in `scripts/deploy/`, against the live cluster, and is committed in
> `evidence/deploy/`. No CI run has ever spoken to CockroachDB Cloud. Setting the
> `CRDB_CLOUD_DSN` repository secret would make the fourth job run and would convert a
> loudly-skipped lane into a continuously-verified one; that is a decision for whoever owns the
> repository's secrets, and until it is taken the row above is what is true.

---

## 4 · The two logins

`scripts/deploy/cloud_roles.py` creates exactly two, and nothing else.

### `mainline_api` — what the Lambda connects as

| Holds | Why |
|---|---|
| `CONNECT` on `mainline_demo` | |
| `USAGE` on `mainline`, `mainline_meas`, `mainline_audit`, `mainline_ops` | |
| `SELECT` on 31 enumerated tables and views | the demo's read surfaces (`API_READ`) |
| `SELECT` on 10 further tables | **what the gate transaction's trigger chain reads** (`API_GATE_READ`) |
| `SELECT` on the 14 `mainline_audit` views | enumerated by name, never wildcarded |
| `UPDATE` on `permit`, `blocking_check`, `change_request` | what `merge_permit` and the disposition triggers write |
| `INSERT` on `permit_event`, `merge_record`, `refusal_ledger`, `disposition`, `disposition_citation`, `override_ledger`, `ledger_intake`, `mainline_ops.outbox` | ditto |
| `EXECUTE` on `mainline.merge_permit` | the merge itself |
| Membership in `auditor_ro`, `agent_gate`, `svc_disposition` | **row-level-security scope — see below** |
| **Nothing at all in `mainline_qa`** | S14, re-revoked on every run |
| **No `DELETE`, anywhere** | MI01 |

**Why memberships and not only grants.** Four tables carry `FORCE ROW LEVEL SECURITY`
(`RLS-MATRIX.yaml`: `permit`, `change_request`, `disposition`, `mainline_meas.standing`), and under
FORCE, *"if RLS is enabled but no policies apply to a given combination of user and SQL statement,
access is denied by default."* A bare `GRANT SELECT ON mainline.permit` therefore buys **zero
rows, silently** — the worst failure an audit surface can have, because it is indistinguishable
from a clean site. The policies are written `TO <role>` and match any member, so `mainline_api` is
made a member of the three roles the demo's three beats impersonate: `auditor_ro` (`fleet_scope`,
`disposition_service_read`), `agent_gate` (`service_read`, `gate_insert`, `gate_write`) and
`svc_disposition` (`gate_write`, `disposition_insert`).

The memberships buy **scope**, not privileges: `GRANTS.yaml`'s table matrix is applied by
`trappoint migrate grants apply`, and on a freshly migrated database
`information_schema.table_privileges` for those three roles returns **no rows**. So every table
privilege is granted directly. Relying on inheritance would have produced a login that can see
nothing.

**The gate-read list was discovered by running it, not by reading the schema.** No trigger function
in migrations 0100–0149 is `SECURITY DEFINER` — `GRANTS.yaml` records that as an open coupling
rather than hiding it — so the merge transaction's triggers read tables no demo screen ever shows.
The method was a loop: run the three beats as `mainline_api`, parse the `42501`, grant exactly the
named privilege on the named relation, repeat. Thirteen grants, in the order they were demanded:

```
UPDATE blocking_check · SELECT change_request · INSERT ledger_intake · SELECT identity_residue
SELECT permit_boundary · SELECT permit_slice · SELECT override_ledger · SELECT unwitnessed_debt
SELECT disposition_citation · SELECT mechanism_predicate · UPDATE change_request
SELECT cr_clause · SELECT cr_event
```

The `change_request` entries are there because `fn_disposition_close` and `fn_check_materialised`
branch on `subject_kind` and touch the change-request arm even when the subject is a permit.
Guessing this list from the architecture would have produced a login that fails in the middle of
the demo's second beat, in front of a judge, with a privilege error.

### `mainline_judge` — what a judge gets

`SELECT` on the fourteen `mainline_audit` views. That is the whole of it.

It also holds `USAGE` on `mainline`, `mainline_meas` and `mainline_ops` — **and that is not a
loophole, it is a measured requirement.** On CockroachDB v26.2.5 a view runs the underlying query
with its owner's *table* privileges, but the *schema* `USAGE` check is made against the invoker
regardless:

```
with USAGE on mainline_audit only:
  SELECT count(*) FROM mainline_audit.v_open_gate_summary
    → 42501  user mainline_judge does not have USAGE privilege on schema mainline

with USAGE additionally on mainline, mainline_meas, mainline_ops:
  SELECT count(*) FROM mainline_audit.v_open_gate_summary   → OK, rows=1
  SELECT count(*) FROM mainline.permit
    → 42501  user mainline_judge does not have SELECT privilege on relation permit
```

`USAGE` is the right to name a schema; it is not the right to read anything in it, and the second
probe is the evidence rather than the assurance. `mainline_qa` is absent from that list and always
will be — without `USAGE` the schema is not even nameable, which is a stronger position than a
revoked `SELECT`.

### The probes, which are the actual control

`GRANTS.yaml`'s own header says it: *a GRANT is a claim about intent, a `42501` is evidence about
behaviour.* `cloud_roles.py` connects **as each login** and asserts in both directions. Seventeen
probes, all agreeing, against the Cloud cluster:

```
probes        mainline_api
  ok [00000] read the gated subject (RLS must let it through)      rows=1
  ok [00000] read the obligation                                   rows=1
  ok [00000] read the corpus                                       rows=1
  ok [00000] read the recall pass                                  rows=1
  ok [00000] read the audit surface                                rows=1
  ok [42501] mainline_qa is unreachable (S14)
  ok [42501] mainline_qa per-person view is unreachable (S14)
  ok [42501] no DELETE anywhere (MI01)
  ok [23514] drive the demo's first beat (CALL mainline.merge_permit)  gate_closed_when_issued

probes        mainline_judge
  ok [00000] read the audit surface                                rows=1
  ok [00000] read the silence summary                              rows=0
  ok [00000] read the conservation law                             rows=1
  ok [42501] the base tables are unreachable
  ok [42501] the corpus is unreachable
  ok [42501] mainline_meas is unreachable
  ok [42501] mainline_qa is unreachable (S14)
  ok [42501] no write path exists
```

The last `mainline_api` probe is the one that matters most: it calls `mainline.merge_permit` on the
seeded permit and asserts the refusal is the **product's** refusal rather than a privilege error.
The statement aborts on the refusal, so nothing is written. A login that reads everything and
cannot drive the gate would pass the other eight probes and fail the demo.

### The passwords

Generated by `secrets.token_urlsafe(24)`, printed to stdout **once**, never written to a file,
never logged, never in an evidence artefact. There is no `--password` option, deliberately: an
operator who cannot pass a password on a command line cannot leave one in shell history.

They were **rotated after this page's measurements were taken and were not retained.** Run

```bash
.venv/Scripts/python.exe scripts/deploy/cloud_roles.py --rotate
```

when you are ready to capture them, and put them straight into SSM Parameter Store as
SecureStrings — which is also where the deploy plan §2.5 says the DSN belongs, written by the CLI
and never by Terraform, because a Terraform-managed secret is a plaintext secret in the state file.

A re-run **without** `--rotate` leaves existing passwords alone and says so. A deploy script that
silently rotated a secret would take the demo down every time somebody re-ran it.

**Building an application DSN.** Take `COCKROACH_DSN`, swap the userinfo, **swap the database to
`mainline_demo`** (the committed DSN says `defaultdb` — §0.1), and keep everything else: host,
port, `sslmode=verify-full` and any `options`, because a Cloud Basic DSN's query string is
load-bearing.

```
postgresql://mainline_api:PASTE_THE_PASSWORD_HERE@HOST:26257/mainline_demo?sslmode=verify-full

  where HOST = mainline-dev-31219.j77.aws-ap-southeast-1.cockroachlabs.cloud
  and   PASTE_THE_PASSWORD_HERE is printed once by cloud_roles.py --rotate and is not in
        this repository, this page, or any evidence file
```

> **Note for W9's disclosure register.** This template is a **shape, not a secret** — there is no
> credential in it and never has been. The public-readiness scanner nonetheless flagged the
> previous single-line form at `docs/deploy/cloud-database.md:282` as `high_entropy_secret`,
> because a long unbroken DSN with a `<password>` placeholder inside it looks exactly like a real
> one to an entropy detector reading a line at a time. The template is kept — a reader who cannot
> see the shape cannot build the DSN — and the placeholder is now an unmistakable
> `PASTE_THE_PASSWORD_HERE` on a line the host does not share.
>
> **Measured after this edit**, with the audit's own detectors run over this file alone:
> `scan_text("docs/deploy/cloud-database.md", …)` returns **no findings**. The `high_entropy_secret`
> hit on this page is resolved by making the placeholder unambiguous, not by waiving it — the
> detector is exactly as strong as it was and would still fire on a real DSN pasted here.
>
> **If it ever trips again**, the path to declare is `docs/deploy/cloud-database.md`, family
> `high_entropy_secret`, reason *"an application DSN template with a named placeholder; the
> password is printed once by `cloud_roles.py --rotate` and is in no tracked file."* Declared, not
> allowlisted.

---

## 5 · The demo world

Two SQL files, both readable by a judge, both idempotent:

* `verticals/mainline/db/seeds/demo/demo_world.sql` — the static corpus
* `verticals/mainline/db/seeds/demo/demo_permit.sql` — one permit, one open obligation

### What is in it, measured after seeding

| Table | Rows | | Table | Rows |
|---|---|---|---|---|
| `mainline.site` | 1 | | `mainline.permit` | 1 |
| `mainline.person` | 2 | | `mainline.permit_clause` | 1 |
| `mainline.signing_credential` | 2 | | `mainline.permit_event` | 2 |
| `mainline.commit_obj` | 2 | | `mainline.boundary_certificate` | 1 |
| `mainline.commit_edge` | 1 | | `mainline.blocking_check` | 1 |
| `mainline.doc` | 1 | | `mainline.exposure_receipt` | 1 |
| `mainline.clause` | 1 | | `mainline.exposure_line` | 1 |
| `mainline.clause_version` | 1 | | `mainline_meas.recall_policy` | 1 |
| `mainline.event` | 1 | | `mainline_meas.recall_run` | 1 |
| `mainline.blame_edge` | 1 | | `mainline_meas.silence_receipt` | 1 |
| `mainline.clause_blame_closure` | 1 | | `mainline_ops.outbox` | 1 |
| `mainline.cbm_account` | 1 | | **`mainline.disposition`** | **0** |
| `mainline.ledger_checkpoint` | 1 | | **`mainline.merge_record`** | **0** |
| `mainline.cosignature` | 1 | | | |

The two zeros are the demonstration. Everything else is the history a real permit would carry; the
one thing missing is a human's signed answer to the one obligation the recall pass raised.

### Everything is flagged synthetic *in the data*

Not only in this page, and not only in `DEMO-HONESTY.md`:

* external references are prefixed `DEMO-` (`DEMO-INC-0001`, `DEMO-PTW-0001`, `DEMO-SOP-0001`)
* every free-text field opens with `SYNTHETIC —` (title, narrative, commit message, attribution)
* every JSONB payload carries `"synthetic": true` and names the seed file that wrote it
* every provenance column names the seed file (`computed_by`, `projector_ver`, `wrote_as`)
* every principal is prefixed `demo.` (`demo.signer`, `demo.countersigner`)
* every identifier begins `dec0de00`, so a demo row is greppable in a log by eight characters

`SELECT ... WHERE narrative LIKE 'SYNTHETIC%'` is a census anyone can run.

### The state the seed produces, and what "open" means

```
permit.state          = 'dispositioned'    the client's claim that everything is answered
permit.open_blocking  = 1                  written by the trigger, not by the seed
blocking_check        = 1 row, severity 4, virulence 'blood_major'   (both PROJECTED)
disposition           = 0 rows
```

`mainline.subject_state` has no member called `open` — the alphabet is
draft / checks_materialised / dispositioned / merged / suspended / closed / abandoned (migration
0011). `dispositioned` is the state from which `merged` is the next legal transition, and it is the
state in which the client is *claiming* every obligation now carries a signed disposition. It does
not. That claim is what the gate exists to disbelieve.

**The counter is not written by the seed.** `open_blocking` is incremented by the trigger
`check_materialised` (0121 → `fn_check_materialised`, 0101). `scripts/proof/gate_refusal.py` writes
that counter by hand, because on the tree it was written against `mainline_ops.outbox` had no
producer and 0121 could not apply. On `mainline_demo` it applies, so the projection is the
projection — and `seed_demo.py` records `projection_trigger_check_materialised_present: true` and
`re_derived_open_obligations: 1` in the evidence, because "the trigger wrote it" is a claim that
should carry its check.

`severity` and `virulence` are supplied as `0` / `'routine'` by the seed and are immediately
overwritten by `fn_check_project` from `mainline.clause_blame_current` (invariant MI25). The
evidence reads them back as `4` / `blood_major`, which is how you know the projection ran.

### Two things about these files that are the schema's decision, not a preference

1. **`mainline.site.site_code` is the site's own UUID rendered as text.**
   `mainline.fn_recall_policy_anchored` (0112, fired by 0136) checks
   `WHERE cp.site_code = ((NEW).site_id)::STRING`, so the custody ledger's partition key for a site
   *is* its identifier. Renaming that seam to make the seed prettier would be seeding a different
   schema from the one that ships.

2. **The recall run lives in `demo_permit.sql`, not in `demo_world.sql`.**
   `mainline_meas.recall_run.permit_id` is `NOT NULL REFERENCES mainline.permit`: a recall run in
   this schema is a permit-scoped fact and cannot exist before its permit. CockroachDB validates
   foreign keys per statement and has no deferrable constraints, so no ordering of the two files
   puts the run in the static corpus.

### One thing that is STAGED, and is named as staged

The seeded exposure receipt expires on **2027-01-01**. In the product a receipt's TTL is hours —
`mainline.exposure_receipt` constrains only `expires_at > issued_at` and the application picks the
window. The long window exists so the admission beat keeps working for every judge for the whole
judging period rather than for two hours after somebody ran the deploy. It belongs in
`DEMO-HONESTY.md`'s STAGED column and it is written into `demo_permit.sql` beside the row, so that
nobody reads it as the product's default.

`DEMO-HONESTY.md` §3 already lists the pre-seeded permit under STAGED for the same reason: the
permit's existence is staged, **the gate evaluation is not**, and no part of either seed file
touches the gate.

### Idempotence, and the one trap in it

`ON CONFLICT DO NOTHING` does **not** suppress an exception a BEFORE INSERT trigger has already
raised — conflict resolution happens after the trigger runs. Measured: a second run of
`demo_world.sql` raised

```
P0001  MAINLINE: closure generations must be dense and monotone
```

from `fn_closure_guard` and aborted the whole batch. That is the guard working correctly —
generation 0 has already been used for that (clause, commit). So the three tables whose INSERT
fires a BEFORE trigger that can raise (`clause_version`, `clause_blame_closure`, `cbm_account`) use
`INSERT ... SELECT ... WHERE NOT EXISTS`, which never offers the row. The two `permit_event` rows
use the same form for a different reason: the second event's `prev_digest` must read the first
event's trigger-computed `chain_digest`, and only an `INSERT ... SELECT` can.

---

## 6 · The verification, which is a rolled-back merge

`seed_demo.py` does not stop at counting rows. Counting rows proves the seed ran; it does not prove
the seed produced *the state the demo needs*. A permit with an open obligation **and** a missing
boundary certificate also has one blocking check and also refuses — with a different SQLSTATE,
naming a different exhibit, for a reason that has nothing to do with the product's central claim.

So the script asks the database, and rolls the whole thing back:

```
MERGE         REFUSED [23514] gate_closed_when_issued (reported)
rollback      nothing_persisted=True
```

`constraint_source: "reported"` means the exhibit came from `diag.constraint_name` — the driver's
own field, not a string parsed out of a message. `spec/errors.md` §3.1 requires that distinction to
be recorded, because a parsed exhibit is a weaker diagnosis.

`after_rollback` reads the permit and `merge_record` back in a fresh transaction: state still
`dispositioned`, `open_blocking` still 1, zero merge records. **This is the property the whole demo
rests on** — the deploy plan §1.4 measured that a full `ROLLBACK` leaves the seeded row untouched,
so every judge drives the real gate against the real seeded history, concurrently, and finds the
database exactly as the last one left it. No per-visitor state, no reset button, no cleanup
sweeper. `seed_demo.py` exercises that property on every run, so if it ever stops holding, this is
where it is found out.

The full three-beat sequence — refuse, refuse-under-forged-counter, admit-after-one-signature — was
also driven end to end as `mainline_api` under `SAVEPOINT` / `ROLLBACK TO SAVEPOINT`:

```
beat1   [23514] gate_closed_when_issued
beat2   [P0001] MAINLINE: merge refused by mainline.fn_permit_merge_gate
                — re-derived open obligation count is 1 while the projected counter reads zero
sign    [00000]
beat3   [00000]
```

That is the demo. The second beat is the one no `CHECK` can hold: the projected counter is forced
to zero out of band — exactly what a disarmed projector or a bad `UPDATE` would leave — and the
gate refuses anyway, because it **re-derives** the count instead of trusting the column.

---

## 7 · How to check that this page is not lying

```bash
# the schema, and whether it still matches the tree
.venv/Scripts/python.exe scripts/deploy/cloud_chain.py            # expect: unchanged, 271/271, exit 0

# the 40001 retry loop, fired on purpose against the live cluster; applies nothing
.venv/Scripts/python.exe scripts/deploy/cloud_chain.py --retry-probe --jitter-seed 40001
                                                                  # expect: RETRY LOOP PROVEN, exit 0

# the WHOLE chain, re-applied to Cloud from scratch, with a real migration made to hit 40001.
# ~7 minutes and one throwaway database that is dropped; mainline_demo is never written.
.venv/Scripts/python.exe scripts/deploy/cloud_chain.py --verify-build \
    --inject-40001 3 --inject-into 0002_schema_meas.sql --jitter-seed 40001
                                                                  # expect: VERIFIED 271/271, exit 0

# the seed, and the refusal, without applying anything
.venv/Scripts/python.exe scripts/deploy/seed_demo.py --check      # expect: REFUSED [23514], exit 0

# the seed applier's retry loop, on a real seed file
.venv/Scripts/python.exe scripts/deploy/seed_demo.py \
    --inject-40001 2 --inject-into demo_world.sql --jitter-seed 40001
                                                                  # expect: attempts=3 injected=2, exit 0

# the two logins, in both directions (needs the passwords)
MAINLINE_API_PASSWORD=... MAINLINE_JUDGE_PASSWORD=... \
  .venv/Scripts/python.exe scripts/deploy/cloud_roles.py --verify --password-from-env

# and the same three programs against a throwaway local database, on a laptop
.venv/Scripts/python.exe scripts/deploy/cloud_chain.py \
    --dsn postgresql://root@localhost:26257/defaultdb?sslmode=disable \
    --database w_scratch --recreate
```

The local rehearsal is worth running. It applies the same 271 files to the same server version, in
about two minutes, and it is where every behaviour on this page was found before it was claimed
about Cloud. Note one honest difference: the local development node runs `--insecure` and
CockroachDB refuses to hold a password there at all — *"setting or updating a password is not
supported in insecure mode"* — so `cloud_roles.py` creates the logins without one and says so on
every probe line. A passing rehearsal is not a passing deployment, and the output never lets the
two be confused.

---

## 8 · Cost

The database contributes **$0.00/month**. CockroachDB Cloud Basic's free allowance (100 M RU,
10 GiB) covers a demo whose entire working set is 27 rows and whose gate run is four statements,
and the cluster's `spend_limit` is a hard ceiling: the cluster stops before the bill does.

The `--recreate` path costs one full chain apply (≈390 s of DDL). Everything after that is the
`unchanged` path, which is two fingerprint computations and a `SHOW ZONE CONFIGURATION`.

`--retry-probe` costs **three `SELECT`s and about seven seconds of deliberate sleeping**, all of
it in this process rather than on the cluster. `--reattest` and `--verify-build` each cost one
extra chain apply into a temporary database that is dropped on every exit path, so the storage
footprint is transient and the RU cost is one DDL chain — the same order as a `--recreate`, and the
price of not taking the demo down to answer the question. Three such applies have now been run
against this cluster (2026-08-10 build, 2026-08-11 re-attestation, 2026-08-11 verification) and the
cluster remains inside the free allowance; `spend_limit` is the hard ceiling either way.

**AWS, for completeness, is a rounding error too.** `scripts/deploy/aws_live_probe.py` makes two
billable inference calls per run — one Titan embedding of a single sentence (13 input tokens) and
one Haiku turn (16 in / 8 out) — which is well under USD 0.01. `evidence/deploy/aws-live.json`
records the token counts the API itself reported, so the arithmetic is checkable.

---

## 9 · What is not here

* **No CI verification of this cluster.** `cloud-verify` is green and has never contacted it —
  §3, where the claim that it *had* is recorded and refused. Every Cloud number on this page was
  measured from a developer machine and committed. The one change that would make this bullet
  obsolete is setting the `CRDB_CLOUD_DSN` repository secret, and that is a decision for whoever
  owns the repository's secrets.
* **No AWS service on this page.** Bedrock does execute for this project — measured
  2026-08-11 01:11 UTC in `ap-southeast-2`: `amazon.titan-embed-text-v2:0` returned a
  **1024-dimension** embedding for 13 input tokens, and `au.anthropic.claude-haiku-4-5-…-v1:0`
  answered over `Converse` with **16 in / 8 out / 24 total** tokens. The transcript is
  `evidence/deploy/aws-live.json`, written by `scripts/deploy/aws_live_probe.py`, which exits
  non-zero if any of its four calls fails and records the exception verbatim when one does. The
  correction to `docs/STATE-OF-THE-BUILD.md` §3.3 and `docs/TOOL-USAGE.md` — both of which still
  say no Bedrock call has ever succeeded — belongs to the worker who owns those pages; this page
  is about the database and only names the artefact they should cite.
* **No `mainline_qa` access, for anybody, on any tier.** S14. Both logins are re-revoked on every
  run and both are probed for `42501`. The judge pack's own envelope names `mainline_qa` as
  never-issued and this deployment keeps that true.
* **No second cluster.** `verticals/mainline/demo/judge/PACK.md` names a cluster
  `mainline-verify` that does not exist. This deployment uses one cluster, `mainline-dev`, because
  a second Basic cluster splits the same free allowance for no isolation the demo needs. That
  discrepancy belongs to the judge-pack owner and is recorded here rather than quietly patched.
* **No `AS OF SYSTEM TIME` anywhere.** The GC window on this database is 4500 seconds and the
  demo's ancestry reaches back to 2019. Long-horizon history is the application-level commit DAG
  and the `occurred_at` column, both of which are ordinary data.
* **No adverse witness.** The cosignature in `demo_world.sql` §8 is our own. The mechanism is
  exercised; the row is not an independent party's signature, and `DEMO-HONESTY.md` §4 already says
  adverse witnesses are not running.
* **Row-level security is not a defence against a cluster administrator.** It is tenancy hygiene
  and information partitioning between principals who all legitimately hold the privilege.
  `RLS-MATRIX.yaml`'s SEC-1 header says it first and this page repeats it, because the login that
  built this database can read past every policy on it.
