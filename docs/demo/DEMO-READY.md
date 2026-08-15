<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# DEMO-READY — one command, eight facts, and the answer to *may I roll camera?*

**Program:** `D:/CoackroachDBxAWS/mainline/scripts/demo/demo_ready.py`
**Tests:** `D:/CoackroachDBxAWS/mainline/tests/demo/test_demo_ready.py`
**Authority:** `docs/demo/proof-and-polish-plan.md` §R1, §R2, §R4, §R9

```
.venv/Scripts/python.exe scripts/demo/demo_ready.py
```

That is the whole command. It asks the deployed demo eight questions, prints one PASS/FAIL
line per question and ends in a verdict. Measured from this machine to `ap-southeast-1` on
2026-08-16, four consecutive runs: **3.8 s, 3.9 s, 4.3 s, 4.5 s — five requests each,
byte-identical stdout every time, exit 0.**

```
VERDICT  READY — 8 of 8 facts PASS, 0 failed. Roll camera.
```

---

## 1 · There is no reset button, and its absence is a claim we make

A retake costs one command because the previous take changed nothing.

`docs/deploy/gate-run-contract.md` §2: the whole `POST /v1/demo/gate-run` transaction ends in
`ROLLBACK`, beat 4 included. `docs/deploy/cloud-database.md` §6 measured the consequence —
after a full rollback the permit is still `dispositioned`, `open_blocking` is still `1` and
there are zero merge records: *"No per-visitor state, no reset button, no cleanup sweeper."*

So this program is a **verifier first and a repairer second**, and the order is the point.
`--check` is the default. It writes nothing, and it does not merely promise that: the eighth
fact it prints is the row counts the database itself took before that transaction opened and
again after it was rolled back. `persisted=false`, `row_counts_identical=true`, over ten
tables. If a run of this command ever did move the world, the command is what says so.

Anyone who builds a "reset the demo" button has misread the product.

---

## 2 · The eight facts

Same eight in both modes, same order, enforced by `FACT_ORDER` and `_in_order()` in the
program: a fact that existed against one target and not the other would mean *ready* meant two
things, and an operator would find out which by being surprised.

| `fact` | what must be true | live source | local source |
|---|---|---|---|
| `target` | the thing being asked is the demo | `GET /v1/health` — `ok=true`, `deploy_chain 271/271`, `database=mainline_demo` | `seed_demo` census — 27 of 27 seeded relations present |
| `permit` | one permit, `dispositioned`, `open_blocking=1`, `gate_epoch=1`, `DEMO-PTW-0001` | `GET /v1/demo/subjects` | `seed_demo → observed.permit` |
| `obligation` | one open blocking check, no disposition on it, severity `4`, virulence `blood_major`, origin `blame_ancestry`, precursor `DEMO-INC-0001` | `GET /v1/permits/{permit_id}/blocking-checks` | `seed_demo → observed.blocking_check` |
| `change_request` | `DEMO-MOC-0001` is still **gated** — not `merged`, `open_blocking=1`, `merged_commit` null, `cr_gate_closed_when_merged` on the row | `GET /v1/change-requests/{cr_id}` | `SELECT mainline.change_request` |
| `zeros` | `mainline.disposition = 0` **and** `mainline.merge_record = 0` | `POST /v1/demo/gate-run` → `persistence_check.before.row_counts` | `seed_demo → row_counts` |
| `signers` | `demo.signer` and `demo.countersigner` are enrolled and unrevoked | `POST /v1/demo/gate-run` (see §4) | `SELECT mainline.signing_credential` |
| `refusal` | the gate still refuses, with the exhibit the film shows | `POST /v1/demo/gate-run` → four beats + `verdict` | `seed_demo → verification` (one beat; see §4) |
| `unchanged` | *this run* changed nothing | `POST /v1/demo/gate-run` → `persistence_check` | `seed_demo → after_rollback` |

**The two zeros are the demonstration.** `docs/deploy/cloud-database.md` §5: *"Everything else
is the history a real permit would carry; the one thing missing is a human's signed answer to
the one obligation the recall pass raised."*

**Severity `4` and virulence `blood_major` are PROJECTED**, and the program prints the
projector beside them on every run — `mainline.fn_check_project`, from
`mainline.clause_blame_current`, invariant MI25. The seed supplies `0` / `routine` and both are
overwritten, which is how you know the projection ran. Nobody typed the four. (Plan §R9: a `4`
with no provenance is a number somebody could have typed.)

---

## 3 · Exit codes

| code | verdict | what it means | what to do |
|---|---|---|---|
| `0` | READY | every fact passed | roll camera |
| `1` | NOT READY | at least one fact failed | read the `FAIL` line; it names the diagnosis, not `expected X got Y` |
| `2` | USAGE | no target, no cluster, no route; **nothing was measured** | fix the invocation or the network, then ask again |
| `3` | ACTION REQUIRED | a write was asked for against a target this program will not write to; **nothing was measured and nothing was written** | run the command it printed |

**Three is a separate number on purpose.** Plan §R2: *"a human must act"* and *"the gate did
not refuse"* are different findings and only one of them is about the product. Collapsing 3
into 1 would let a missing seed read as a broken gate.

**Two is separate from one for the same reason.** A `2` means the question was never put. A
`1` means it was put and the answer was wrong. A command that reported an unreachable origin
as a failed fact would be inventing a finding about a world it never saw.

---

## 4 · What the program refuses to overclaim

Three places where the honest fact is narrower than the convenient one.

**`signers`, against the deployment.** There is no read route that lists signing credentials.
What the payload proves is that **two credentials resolved**: `mainline_demo_api.gate_run`
resolves `signer_credential_id` and `countersigner_credential_id` from
`mainline.signing_credential` *before* the beats' transaction opens, and a subject with no
unrevoked credential raises `ScenarioNotSeeded` → HTTP `422`. Four beats inside a `200` is
therefore proof of the resolution. It is **not** proof of the spelling: `scenario.py` lets a
deployment override both subjects from the environment and the payload does not carry them. So
the live line asserts the resolution and says so; run the command against a local copy to see
the two names read out of the table.

**`refusal`, against a local database.** One beat, not four. `seed_demo` asks the database to
merge the seeded permit inside a transaction it rolls back and records the SQLSTATE and the
exhibit — that is the film's second beat, `23514 gate_closed_when_issued`. The forged-counter
beat (`P0001 mainline.fn_permit_merge_gate`) and the admission live in the deployed
`POST /v1/demo/gate-run`, and the local report says so on its face rather than implying it
checked four.

**`target`, when the chain grows.** A deploy chain of `272/272` is not broken — it is a chain
nobody re-recorded, and the film's own overlay says `271`. The line fails, and it says
*re-record the overlay or the constant, do not film a number the origin does not say.* That is
different from `271/272`, which is a part-applied chain and a deployment mid-flight.

**And `UNDECIDED` is not a refusal.** If the local merge probe gets `40001` on every attempt of
its retry budget, the `refusal` line says the cluster never decided and that re-running is the
remedy. `spec/errors.md` §5. A transient conflict published as a broken gate is how a healthy
demo gets declared dead minutes before a judge arrives.

---

## 5 · The two targets, and the wire

```
# the deployment, over HTTP — the default
.venv/Scripts/python.exe scripts/demo/demo_ready.py

# a local database, through scripts/deploy/seed_demo.py
.venv/Scripts/python.exe scripts/demo/demo_ready.py \
    --dsn postgresql://root@127.0.0.1:26257/w_p1?sslmode=disable

# apply the two seed files to a LOCAL scratch database, then verify
.venv/Scripts/python.exe scripts/demo/demo_ready.py \
    --dsn postgresql://root@127.0.0.1:26257/w_p1?sslmode=disable --repair
```

### `127.0.0.1`, not `localhost`, and it is worth 15 seconds

Measured on this machine on 2026-08-16, against the node this project documents everywhere as
`postgresql://root@localhost:26257/…`:

| DSN host | one psycopg connect | the whole `--check` |
|---|---|---|
| `127.0.0.1` | **0.01 s** | **0.5 – 1.0 s** over four runs |
| `localhost` | **130.06 s** unset, 5.1 s at `--connect-timeout 5` | **15.7 s** |

`localhost` resolves to `::1` first, nothing answers there, and libpq spends the whole connect
timeout on that address before trying IPv4 — once **per connection**, and this command opens
three. The 130.06 s is the same figure `conftest.py` recorded when it set
`PGCONNECT_TIMEOUT=5` for the whole test session, for this same reason.

So `--connect-timeout` defaults to `5` here, matching that file, and the program **says what
happened** on stderr when a named host was slow:

```
  note: the connect to host 'localhost' took 5.1s, and this command opens three. On this
        machine 'localhost' resolves to an address that does not answer … Spell the host
        127.0.0.1 in --dsn. This program does not rewrite your DSN.
```

It does not rewrite the DSN. Silently substituting an address would mean the command measured
a target the operator did not name, which is a worse defect than the delay.

**Exactly five requests reach the deployment, over one keep-alive connection:**

```
GET  /v1/health
GET  /v1/demo/subjects
GET  /v1/permits/{permit_id}/blocking-checks
GET  /v1/change-requests/{cr_id}
POST /v1/demo/gate-run                       ← the only non-GET, permitted by plan §R4
```

Nothing else, ever, and `test_only_five_requests_are_possible_and_only_one_is_a_post` reads the
set out of the source so that a sixth path cannot even be *named* in a comment without going
red. One connection rather than five: measured 2026-08-16, **5.85 s** with a fresh TLS
handshake per request against **3.58 s** reusing one.

**The deployment is never opened as a database.** A psycopg connection to the cloud is not
permitted traffic, so `--dsn` is for a local database and `--check` refuses a non-local host
with exit `2`.

**Addressing comes from the API, never from a constant.** `GET /v1/demo/subjects` hands back
`permit_id` and `cr_id`, and the next two requests are built from those. The UUIDs in the
program are **expectations** — what the answer is checked against — and
`test_the_identifiers_agree_with_the_files_that_write_them` holds each one to the file that
writes it (`scripts/deploy/seed_demo.py` for the permit and the check,
`verticals/mainline/db/seeds/demo/demo_world.sql` for the change request and both signers).

---

## 6 · `--repair`, and the one database it will not touch

`--repair` applies `demo_world.sql` and `demo_permit.sql` through `seed_demo`'s own applier and
then verifies. It is implemented and tested **against a local database only**.

Pointed at `mainline_demo` — the name the deployed demo and its local mirror share — it
refuses before opening a connection, prints

```
    .venv/Scripts/python.exe scripts/deploy/seed_demo.py
```

and exits **3**. The protected set is not a second list: `PROTECTED_DATABASES` is imported from
`scripts/deploy/verify_demo_checkpoints.py`, which already refuses to write to a database other
lanes read, so a name added there starts being refused here with no edit.

`--repair` with no `--dsn` at all is the same refusal with a different sentence: the deployed
world is seeded by the orchestrator and by nothing else.

---

## 7 · Idempotence, and the one trap in it

**This is the trap this repository has already been bitten by.** `docs/deploy/cloud-database.md`
§5, measured:

> `ON CONFLICT DO NOTHING` does **not** suppress an exception a BEFORE INSERT trigger has
> already raised — conflict resolution happens after the trigger runs.

A second run of `demo_world.sql` raised

```
P0001  MAINLINE: closure generations must be dense and monotone
```

from `fn_closure_guard`, and aborted the whole batch. That is the guard working correctly:
generation 0 had already been used for that (clause, commit) pair. The fix is in the seed
files, not in this program:

* three tables whose INSERT fires a BEFORE trigger that can raise — `clause_version`,
  `clause_blame_closure`, `cbm_account` — use `INSERT ... SELECT ... WHERE NOT EXISTS`, which
  never offers the row at all;
* the two `permit_event` rows use the same form for a **different** reason: the second event's
  `prev_digest` must read the first event's trigger-computed `chain_digest`, and only an
  `INSERT ... SELECT` can.

`tests/demo/test_demo_ready.py::test_repair_twice_writes_nothing_the_second_time` runs the whole
command **twice in a row** against an already-seeded local database and requires three things:
both runs exit `0`, both print byte-identical stdout, and a 27-table census taken between them
does not move. It also asserts that the seed files really were applied on the second run — a
run that skipped them would prove nothing about idempotence — by reading `seed_demo`'s own
per-file lines off stderr.

Measured on the local scratch database `w_p1`, 2026-08-16, two consecutive `--repair` runs
through `127.0.0.1`:

```
### LOCAL --repair, twice
  exit=0
  exit=0
  REPAIR STDOUT BYTE-IDENTICAL
  SECOND REPAIR WROTE ZERO ROWS          (27-table census, taken after each run)

--- seed_demo.py said ---            (run 2, on stderr — the files WERE applied)
  seed         demo_world.sql       OK                 0.11s attempts=1
  seed         demo_permit.sql      OK                 0.07s attempts=1
--- end ---
```

The `--check` default was measured the same way in the same sitting: two runs, byte-identical
stdout, and a census before and after that did not move — `--check` writes nothing at all.

`--repair` mode also changes one line of the report, because the word *unchanged* must not be
allowed to cover something it does not measure. The `unchanged` note gains: *"This run also
APPLIED the two seed files, which is what `--repair` is; that is not what this line
measures."* The fact itself is about the rolled-back merge probe, in both modes.

---

## 8 · stdout is deterministic; stderr is not

Two runs against an unchanged world print **byte-identical stdout**, which is what makes
"nothing moved" checkable with `diff` rather than by reading. Nothing that varies between two
identical runs is allowed on stdout — no timestamp, no elapsed millisecond, no `run_id`.

stderr carries the things that do vary:

* `elapsed 4.3s over 5 requests (bound 10s)` — and `OVER THE BOUND` when it is.
* everything `seed_demo` printed, passed through verbatim between `--- seed_demo.py said ---`
  markers, so the underlying tool is never silently swallowed.

**The ten-second bound is claimed of the deployment check only.** §R1 sets it for *may I roll
camera?*, and that question is asked of the deployed world. The local path's elapsed is
reported and not graded — measured **0.5 s** through `127.0.0.1` and **15.7 s** through
`localhost` on 2026-08-16, the whole difference being the dead `::1` in §5 rather than anything
the database did. **Neither number changes the exit code.** A slow connect is a statement about
a host name and a slow network is a statement about the network; a command that went red for
latency would teach an operator to ignore its own exit code.

Output is forced to UTF-8 on both streams. Windows hands a redirected `stdout` the ANSI code
page — `cp1252` on the machine this was written on — and an em dash in a prose column then
raises `UnicodeEncodeError` *after* the facts were measured. Measured here on 2026-08-16,
before the fix.

---

## 9 · What it reimplements: nothing

| the work | who does it |
|---|---|
| seed a local world, idempotently, and prove it refusable | `scripts/deploy/seed_demo.py` — `build_parser()` builds the arguments, `run()` produces the evidence |
| the census, the `observe`, the rolled-back merge probe | the same, unchanged; this program reads its evidence |
| the `40001` retry loop, on the seeds and on the probe | `scripts/deploy/cloud_chain.Applier` and `trappoint_testkit.txn.run_txn`, through `seed_demo` |
| refuse a remote host or a protected database | `scripts/deploy/verify_demo_checkpoints.py` — `LOCAL_HOSTS`, `PROTECTED_DATABASES` |
| the four beats, one SERIALIZABLE transaction, one ROLLBACK | the deployed `POST /v1/demo/gate-run` |
| the recorded bytes the tests replay | `scripts/demo/capture_memory_loop.py` → `verticals/mainline/apps/console/fixtures/memory-loop/` |

The only SQL this program owns is two SELECTs, and they exist because nothing else asks those
two questions: *which* signing subjects are enrolled (the census counts the rows but does not
name them), and whether the change request is still gated (`seed_demo` does not look at
`mainline.change_request` at all).

**If two programs ever disagreed about what "seeded" means, the film would narrate a state the
proof does not make.** That is why there is no second census here.

---

## 10 · How this document is kept true

`tests/demo/test_demo_ready.py` parses **this file**:

* `test_the_document_states_the_exit_code_table` requires a row for each of `0`, `1`, `2`, `3`
  with the word the program prints;
* `test_the_document_names_the_trap_and_its_measurement` requires §7 to still name
  `ON CONFLICT DO NOTHING`, `BEFORE INSERT`, `P0001`, *closure generations must be dense and
  monotone*, `fn_closure_guard`, `INSERT ... SELECT ... WHERE NOT EXISTS`, all three guarded
  tables, `permit_event`, `prev_digest`, `chain_digest` and its source
  `docs/deploy/cloud-database.md`;
* `test_the_document_names_every_fact_the_program_checks` requires a `` `fact` `` entry in §2
  for every fact the program can print.

And the program itself is falsified rather than trusted: every one of the eight facts is fed a
world in which it is false — a permit that merged, an obligation that was answered, a
`persisted: true` gate-run, a `projection_drift_attack` beat that admitted, a disposition row
that exists, a change request that merged, a part-applied chain — and the line is required to
say `FAIL`. A pre-flight check that cannot go red is a green light nobody earned.
