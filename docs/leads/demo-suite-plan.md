<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# DEMO-SUITE — the plan for taking `verticals/mainline/apps/demo-api/tests` green against a real cluster

**Lead:** demo-suite · **Date:** 2026-08-13 · **Branch:** `master` · **HEAD at planning:** `073dfea`
· **Node:** local CockroachDB CCL **v26.2.5** on `127.0.0.1:26257` (container `trappoint-crdb`,
`Up 10 hours (healthy)`) · **Interpreter:** `D:/CoackroachDBxAWS/mainline/.venv/Scripts/python.exe`
(pytest 9.1.1, psycopg 3.3.4).

This wave has exactly one product: **the demo-api suite passing against a real cluster, in
more than one order.** Everything else here is in service of that sentence.

---

## 0 · What I measured before decomposing

**The suite is 444 tests.** Measured, not inherited:

```
$ .venv/Scripts/python.exe -m pytest verticals/mainline/apps/demo-api/tests \
      --collect-only -q --crdb=none
444 tests collected in 0.35s
```

| module | tests |
|---|---:|
| `test_credentials.py` | 17 |
| `test_demo_guard_anonymous.py` | 13 |
| `test_envelope.py` | 50 |
| `test_gate_run.py` | 28 |
| `test_logbudget.py` | 34 |
| `test_ratelimit.py` | 73 |
| `test_reads.py` | 74 |
| `test_refusal_row_factory.py` | 13 |
| `test_response_contract.py` | 42 |
| `test_routes_gate_run.py` | 11 |
| `test_row_factory_contract.py` | 15 |
| `test_static_site.py` | 41 |
| `test_transitions.py` | 33 |
| **total** | **444** |

### 0.1 · THE BASELINE, MEASURED BY ME, AT `073dfea`

```
$ $env:TRAPPOINT_DSN = "postgresql://root@localhost:26257/defaultdb?sslmode=disable"
$ .venv/Scripts/python.exe -u -m pytest verticals/mainline/apps/demo-api/tests \
      --crdb=reuse -q --tb=no -rN --timeout=180 \
      --junitxml=out/demo-suite-baseline.xml

5 failed, 375 passed, 1 skipped, 63 errors in 1535.88s (0:25:35)
```

`out/demo-suite-baseline.xml` → `tests=444 failures=5 errors=63 skipped=1 time=1535.604`.
**The totals reproduce the brief's board exactly.** The composition does not.

### 0.2 · The brief's list of the five failures is wrong in two places, and the correction matters

The five are, verbatim from the XML:

| # | test | assertion that failed |
|---|---|---|
| 1 | `test_demo_guard_anonymous::test_the_four_posts_are_refused_with_the_permit_id_variable_unset` | `{'permit_rows_total': (116, 117)}` — **the row count went UP across four POSTs that were supposed to be refused** |
| 2 | `test_reads::test_an_undeclared_query_parameter_is_refused_rather_than_ignored` | `assert [] == [0, 1]` — the ledger range read returns **no leaves** |
| 3 | `test_reads::test_health_is_200_with_a_real_schema_fingerprint` | `assert 10.103 < 5.0` — `/v1/health` took **10.1 seconds** |
| 4 | `test_refusal_row_factory::test_the_declined_branch_declines_identically_under_both_factories` | `_explain` returned `diagnosis:'declarative', gate_epoch:1` where the test requires `None` |
| 5 | `test_refusal_row_factory::test_the_savepoint_fence_survives_a_raise_inside_one_open_transaction` | same cause as #4 |

All 63 errors are one cause, confirmed from the XML: `failed on setup with "KeyError: 'cr_id' is
not an identifier the deployed demo seed produces…"`, and the message lists what the seed *does*
offer — `check_id, clause_gen, clause_uuid, commit_id, countersigner_credential_id,
countersigner_sub, doc_id, event_id, permit_external_ref, permit_id, permit_state, …` — with no
`cr_id` among them. The single skip is one case in `test_gate_run.py`.

**`test_transitions::test_the_request_after_a_gate_run_is_not_a_503` PASSED.** It is not among
the five. The brief names it as failure family 4 and instructs a worker to hunt the leak behind
it; in this run, in this order, at this HEAD, it is green. I am not treating that as "fixed" —
the orchestrator saw it fail, and a test that passes in one order and fails in another is
exactly the disease this wave is about — but I am **not** spending a worker on hunting a symptom
I cannot reproduce. W5 settles it under randomised order, where an order-dependent failure is
reproducible on purpose instead of by luck. See §2's W4, which is re-cut around what actually
failed.

**And what actually failed is worse than what the brief predicted.** Failure #1 says four POSTs
that the demo guard reports as *refused* left `mainline.permit` with **one more row than it
started with**. A refusal that writes is the single most damaging behaviour this product can
have in front of a judge, because the screen says no and the database says yes. It outranks
everything else on this board, and it was not in the brief at all. Failure #3 —
`/v1/health` at 10.1 s against a 5 s budget — is the second thing a judge meets, and #2 is a
range query silently returning nothing. None of the three were predicted; all three are real.

That is the case for measuring the baseline yourself rather than inheriting one, made once,
concretely, at the top of this plan.

Five other facts I established myself, because a brief that is wrong about one of them would
send a worker in the wrong direction:

| claim | how I checked it | verdict |
|---|---|---|
| the cluster is up and is the pinned version | `docker ps` → `trappoint-crdb Up 10 hours (healthy)`; `SELECT version()` → `CockroachDB CCL v26.2.5` | confirmed |
| the demo seed carries no change request | `grep -n 'change_request\|cr_id'` over `demo_world.sql` **and** `demo_permit.sql` → **no output from either** | confirmed |
| the console nonetheless ships that resource | `resources.ts:84-90` and `:224`; `contracts/change-request.schema.json` committed | confirmed — see §1.1 |
| `0119a`'s fallthrough raises | it does **not**: lines 607-620 RETURN `diagnosis:'none'` | **the brief's premise inverted** — see §1.2 |
| something leaks database sessions | two `application_name='mainline-demo-api'` sessions still open on the local node **four hours** after the run that made them, last query `ROLLBACK TRANSACTION` | confirmed — W4 |

### 0.3 · Two things about measuring this lane that every worker needs before they start

**First: a cold run pays for 271 migrations twice.** `demo_database` (`tests/conftest.py:722`)
builds `w3_demo_api_<fingerprint>` and `w4_database` (`tests/test_gate_run.py:450`) builds a
second scratch database, each applying the full chain and a seed before a single assertion is
evaluated — ~47 s apiece on this node, and both are session-scoped, so a cold invocation spends
minutes before the first dot. Both are cached by fingerprint afterwards. **Editing anything
under `db/migrations/` or `db/seeds/` changes the fingerprint and forces a rebuild** — that is
W1's whole first run, and it is correct behaviour, not a fault.

**Second: a redirected run looks dead when it is not, and I killed two of mine believing it.**
Under `-q` pytest emits one line per ~72 results, so a run whose stdout is a file or a pipe
prints **nothing at all** for its first several minutes — and its CPU time stays near 1 s the
whole while, because this suite is I/O-bound on the cluster rather than compute-bound. I read
that silence as a hang twice and stopped a healthy run each time. It is not a hang; it is a
suite that has not yet finished its first 72 tests. **Use `--junitxml` and read the XML**, which
is written whatever happens to stdout — that is why §4 specifies it, and why every worker
reports numbers from the XML rather than from a terminal scroll they may not get. If you want a
liveness check, `SHOW CLUSTER SESSIONS` on the node will show the run's session; low CPU is not
evidence of a stall.

Neither of these is a defect in the product. Both are the reason nobody runs this lane, and
"nobody runs this lane" *is* the root cause the brief names — `pytest --crdb=none` is 258 passed
/ 186 skipped, no CI job runs the cluster-backed lane at all, and three NO-GO verdicts followed.
**Building that CI lane is not this wave's job**: a concurrent wave already owns it (see the
boundary note at the top of §2). Ours is to make sure that when their lane runs, what it finds
is a suite that certifies the product rather than one that certifies itself — which is why the
last worker in this plan is a falsification audit rather than a workflow file.

---

## 1 · The two rulings I make as lead, so that no worker has to guess

### 1.1 · `cr_id` — **SEED THE CHANGE REQUEST.** Do not assert the 404.

The brief calls both defensible. They are not equally defensible, and the deciding evidence is
not in the test suite at all — it is in the console:

```
verticals/mainline/apps/console/contracts/change-request.schema.json      committed
verticals/mainline/apps/console/src/data/resources.ts:84-90               declare('change_request',
                                                                           'GET', '/v1/change-requests/{cr_id}',
                                                                           `${C}change-request.schema.json`, 'kernel', …)
verticals/mainline/apps/console/src/data/resources.ts:224                 'change_request' ∈ RESOURCE_KEYS
verticals/mainline/apps/demo-api/src/mainline_demo_api/app.py:213         Route("GET", "/v1/change-requests/{cr_id}", "change_request")
verticals/mainline/apps/demo-api/src/mainline_demo_api/reads.py:513       read_change_request(...)
verticals/mainline/db/migrations/0051_change_request.sql                  CREATE TABLE mainline.change_request
verticals/mainline/db/migrations/0017b_subject_transition_seed.sql:38-46  nine legal change_request transitions
```

Seven layers of this product — a table, a transition alphabet, four independently-named
CHECK refusals, a reader, a route, a committed JSON Schema, and a navigable console resource —
exist for a subject **the demo world does not contain**. `grep -n 'change_request' on
`verticals/mainline/db/seeds/demo/demo_world.sql` and `demo_permit.sql` returns **nothing at
all.** The console's own description of the resource is *"The second gated subject. The
repository is the protected branch; the permit is one of its refs."* — which is the thesis of
the product. A judge who clicks it gets a 404.

Asserting the 404 would make the suite green while certifying that the demo's second gated
subject is furniture. That is the same category of act as reshaping a seed to match a
constant: it moves the defect from *visible* to *documented-as-intended*. So:

> **RULING: `demo_world.sql` gains a change request, its precursor obligation, and whatever
> authority rows the projection triggers require, and `tests/conftest.py::_identifiers` READS
> `cr_id` BACK OUT OF THE DATABASE with a `_sole(...)` query — exactly as it already does for
> `permit_id`, `check_id`, `receipt_id`, `signer_sub`, `clause_uuid` and both credential ids.**

Three properties make this the opposite of the shortcut that was caught:

1. **The seed grows a subject the product declares; it is not reshaped to match a Python
   constant.** No value in `demo_world.sql` is chosen to equal anything in the codebase.
2. **The fixture still mints nothing.** `_Seed.__missing__` stays exactly as written, word for
   word. Its instruction — *"Seed it in `demo_world.sql` so the deployment carries it too, or
   assert the 404"* — is being obeyed, on the branch it names first.
3. **The deployment carries it.** `scripts/deploy/seed_demo.py` applies `demo_world.sql` to
   CockroachDB Cloud, so this row reaches the judge's URL and not only the laptop.

And the 404 is not lost: W2 adds a **separate** test that an unknown `cr_id` is a 404, so the
suite asserts both that the subject exists and that a nonexistent one is refused honestly.

### 1.2 · `_RAISES` — a *different real* raising constraint, or a written admission that none exists

`0119a_fn_explain_refusal.sql` has exactly ten handled constraint names and one fallthrough.
The fallthrough **does not raise** — it returns `diagnosis: 'none'`, `naa_reason:
'not_computable'` (lines 607-620). So an unhandled constraint name cannot be used to reach the
raising branch, and a worker who reaches for one has written a test that asserts nothing.

The branches that genuinely `RAISE … ERRCODE = 'P0001'` are: the null/empty constraint guard
(line 71), the absent-subject guard (line 105), and inside each counter branch, **the two
drift guards** — `v_value IS NULL OR v_value <= 0` and `v_open_n = 0`. The six permit counter
constraints are `gate_closed_when_issued`, `identity_conserved_when_issued`,
`conflicts_resolved_when_issued`, `no_open_warrant_when_issued`,
`boundary_certified_when_issued`, `reading_floor_when_issued`.

> **RULING: W3 measures every one of the six counters on the seeded permit and picks a
> constraint whose counter is genuinely zero on the seed as it stands.** That is not moving
> the goalposts — the test's stated requirement is *"a permit whose projected counter is
> zero"*, and the constraint name was only ever the instrument for reaching it. If **no**
> counter is zero, W3 does **not** relax the assertion, does not widen the regex, and does not
> touch the seed: it writes the measurement into `still_broken` and into
> `docs/diagnosis/refusal-raising-branch.md`, and says plainly that the branch the `SAVEPOINT`
> exists for is no longer reachable without a write.

---

## 2 · The six workers

Paths are **absolute and disjoint**. No worker may edit a file another worker owns; a finding
outside your own paths goes to the lead in `still_broken`, with the evidence, unedited.

| id | title | depends on |
|---|---|---|
| `w1-change-request-seed` | The demo world gains its second gated subject, and the fixture reads it back | — |
| `w2-read-surface` | The twelfth read, the empty ledger range, and a ten-second `/v1/health` | `w1` |
| `w3-raising-branch` | A constraint that genuinely cannot decompose — or the admission that none remains | — |
| `w4-refusal-that-writes` | Four refused POSTs left a permit row behind | — |
| `w5-order-independence` | Randomised order, repeated runs, and every module nobody else owns | `w1`,`w2`,`w3`,`w4` |
| `w6-falsification-audit` | Re-plant every defect this wave claims to have fixed, and stop the `cr_id` gap recurring | `w1`,`w2`,`w3`,`w4`,`w5` |

> **A boundary that binds all six: `.github/workflows/` is not ours.** A concurrent wave —
> `docs/leads/ci-runs-cluster-plan.md`, same HEAD — is building the cluster-backed CI lane
> (`cluster-tests.yml`, `cluster-lane-bites.yml`), and its workers own `.github/workflows/`,
> `docs/CI-STATE.md`, `docs/HONESTY.md`, `qa/` and `scripts/ci/`. **No worker in this wave edits
> any of those.** Their W2 expects to execute this suite in CI and classify each failure
> `known` / `NEW`; the fewer failures we leave, the shorter their known-red list. The two waves
> are complements: they build the lane, we remove what it would find. If you need something from
> them, say so in `still_broken` and I will carry it across.

### W1 · `w1-change-request-seed`

**Owns**
`verticals/mainline/db/seeds/demo/demo_world.sql` ·
`verticals/mainline/apps/demo-api/tests/conftest.py` ·
`docs/decisions/demo-change-request.md` (new)

**Done when** `pytest verticals/mainline/apps/demo-api/tests --crdb=reuse` reports **0 errors**;
`seed["cr_id"]` is a value read back out of the database by a query; `_Seed.__missing__` is
byte-identical to what it is today; and the whole-suite before/after numbers are reported.

The 63 errors have one cause: `tests/test_reads.py:90` asks for `seed["cr_id"]` and
`_Seed.__missing__` (`tests/conftest.py:414`) refuses, because neither `demo_world.sql` nor
`demo_permit.sql` contains the word `change_request` anywhere. Because `payloads`
(`test_reads.py:107`) is **session-scoped**, that one `KeyError` errors every test that depends
on it. §1.1 of this plan is my ruling: **seed the row.** Read §1.1 before you start; you are
implementing a decision, not making one.

`mainline.change_request` is defined in `verticals/mainline/db/migrations/0051_change_request.sql`
— which you may not edit, it is `trappoint render` output. Read it. `site_role`,
`open_blocking`, `open_residue` and `open_conflicts` are **trigger-projected** with
`@on_missing raise`: you supply none of them, and the authority rows must exist or the INSERT
refuses. `cr_external_ref_unique (site_id, external_ref)` and `cr_epoch_target (cr_id,
gate_epoch)` are your uniqueness constraints. `0017b_subject_transition_seed.sql:38-46` gives
the nine legal `change_request` transitions; seed the subject in a state that has something
true to say — the console describes it as *"the second gated subject"*, so a change request in
`checks_materialised` with at least one open blocking obligation tells the demo's story, while
`draft` tells none. Reuse the `site_id` the permit already uses; do not invent a second site.

**Do not use `gen_random_uuid()` for `cr_id` in the seed.** The seed is applied to CockroachDB
Cloud by `scripts/deploy/seed_demo.py` and the fixture reads identifiers back, so a stable
literal in the `dec0de00-…` family the rest of `demo_world.sql` uses keeps the deployed demo
and the laptop demo talking about the same row. `CREATE SEQUENCE`, `nextval`, `SERIAL` and
`unique_rowid()` are BANNED on this platform.

Then, in `tests/conftest.py`, add a `_CR_SQL` alongside `_PERMIT_SQL` / `_CHECK_SQL` /
`_RECEIPT_SQL` and one `_sole(...)` call in `_identifiers`. `_sole` demands **exactly one** row
and says how many it actually got — keep that. Every value must be `SELECT`ed; the file must
still contain no SHA-256 helper and no restated literal from the seed. Read the comment at
`tests/conftest.py:534-546` about why: a fixture that recomputes what the database owns is how
beat 4 reached a judge behind 291 green tests.

**Three traps in `_identifiers` that will cost you 74 tests if you walk into them.** All three
are `_sole(...)` calls, and `_sole` refuses anything that is not **exactly one** row:

* `_CHECK_SQL` (`conftest.py:499`) is `SELECT … FROM mainline.blocking_check WHERE permit_id = %s`.
  `mainline.blocking_check` carries **both** `permit_id` and `cr_id` — that is how a change
  request gets an open obligation (`0119a:358`, `WHERE bc.cr_id = p_subject_id`). Seed the
  change request's obligation with `cr_id` set and `permit_id` **NULL**, or `_sole` sees two
  rows for the permit and every read test dies.
* `_OTHER_PERSON_SQL` (`conftest.py:528`) is `SELECT DISTINCT signer_sub … WHERE signer_sub <> %s`
  under `_sole`. **Do not add a third person.** The change request's actors are the two people
  the world already has.
* `_PERMIT_SQL` (`conftest.py:484`) is unfiltered `FROM mainline.permit` under `_sole`. Do not
  add a second permit.

Editing a seed file changes `_fingerprint()` (`tests/conftest.py`), which forces a full rebuild
of `w3_demo_api_<fingerprint>` — 271 migrations, ~47 s. That is correct, not a fault. Expect
your first post-change run to be slow.

Write `docs/decisions/demo-change-request.md`: the evidence in §1.1 restated as your own
measurement, the row you seeded, the state you put it in and why, and the sentence that this is
a subject the product declares in seven places — not a value reshaped to match a constant.
Include the SPDX header the sibling documents carry.

**The no-shortcut rule, and it binds you hardest of the six:** NEVER change a seed, fixture,
ceiling, threshold or expected value to obtain a green. You are the one worker authorised to
touch a seed in this wave, and only to ADD the subject §1.1 names, and only with the
justification written down. If any *other* value in `demo_world.sql` looks wrong to you, do not
touch it: report it in `still_broken` with your evidence. A previous worker edited this exact
file to enrol an application-derived constant so beat 4 would stop failing `23503`; three
negative controls caught it and it was reverted. Ask which side is AUTHORITATIVE — the database
owns anything behind a FOREIGN KEY, a CHECK or a projection trigger.

### W2 · `w2-read-surface`

**Owns**
`verticals/mainline/apps/demo-api/tests/test_reads.py` ·
`verticals/mainline/apps/demo-api/src/mainline_demo_api/reads.py` ·
`verticals/mainline/apps/demo-api/src/mainline_demo_api/health.py` ·
`verticals/mainline/apps/demo-api/src/mainline_demo_api/app.py`

**Depends on** `w1`. **Done when** all 74 tests in `test_reads.py` pass under `--crdb=reuse` —
the 63 that W1 unblocks plus the two that fail on their own merits — and a new test asserts that
an unknown `cr_id` is answered 404 rather than 500 or an empty envelope.

You own **three** defects. Two of them are measured and named; the third only becomes visible
after W1 lands.

**(a) The ledger range read returns nothing.** `test_an_undeclared_query_parameter_is_refused_rather_than_ignored`
(`test_reads.py:599`) fails on its **third** clause with `assert [] == [0, 1]`. The two refusal
clauses pass: `permit` does refuse `as_of` and `ledger` does refuse `limit`, so parameter
validation is working and is **not** your bug. What fails is
`read_resource(conn, "ledger", {}, {"site_code": …, "from_seq": "0", "to_seq": "1"})` returning
an empty `leaves` list where the test requires seq 0 and seq 1. A range query that silently
returns nothing is the same defect class as a silently-ignored filter — the caller believes an
answer was computed. Find out whether the leaves exist in `mainline.ledger_checkpoint` and the
range predicate is wrong, or whether they do not exist at all. **If they do not exist, that is a
fact about the seed: report it to the lead in `still_broken`. W1 owns the seed, you do not**, and
you may not make this green by deleting the clause, by loosening it to `!= None`, or by changing
`[0, 1]` to `[]`.

**(b) `/v1/health` takes ten seconds.** `test_health_is_200_with_a_real_schema_fingerprint` fails
`assert 10.103 < 5.0`. The endpoint answers correctly and answers **slowly**, which is why no
other test noticed. `health.py` computes a schema fingerprint; find out what it costs — a
catalog scan over 271 migrations' worth of objects is the obvious suspect, and `db.py`'s
`read()` retry loop wrapping a slow statement is the second. **The 5.0 s ceiling is not
yours to move.** It is the assertion, not the setting: `/v1/health` is the first thing a judge's
browser calls and the thing the CloudWatch alarm polls. If the honest conclusion is that the
fingerprint cannot be computed in under 5 s, the fix is to compute it differently — cache it per
container, read it from the migration ledger the deploy already writes, or narrow the query —
not to raise the number. If you conclude the ceiling is genuinely wrong, say so in
`still_broken` with the measurement and leave it alone. If the cause turns out to be in `db.py`,
that is W4's file: report it, do not edit it.

**(c) The change request actually reads.** `read_change_request` (`reads.py:513`) selects four
columns and calls `_gate_constraints(conn, "change_request", _CR_COUNTERS, row)`. It must
satisfy `verticals/mainline/apps/console/contracts/change-request.schema.json` — the file the
console really loads, validated by `SchemaRegistry` in the central test. If the payload fails
validation, the authority is the **committed schema**, and the reader moves; the schema does
not. `test_reads.py:290` (`cr_identity_conserved_when_merged`) asserts a constraint name came
out of the catalog rather than a list in Python — keep that property.

Add the 404 test: `read_resource(conn, "change_request", {"cr_id": <a uuid the seed does not
carry>}, {})` must raise the module's not-found error carrying `resource="change_request"`
(`reads.py:528`), and `app.py:213`'s route must turn that into a 404. This is the assertion the
"assert the 404" option would have given us; we keep it *and* the row.

**The no-shortcut rule:** NEVER change a fixture, expected value, ceiling, threshold or
assertion to obtain a green. When a test and the code disagree, ask which side is
AUTHORITATIVE: here it is the console's committed JSON Schema and the database catalog, never
`reads.py`'s convenience. Widening a regex until it matches the message you now get is
weakening an assertion and is banned. Report the whole-suite numbers before and after; a green
in `test_reads.py` bought with a red in `test_response_contract.py` is not a fix.

### W3 · `w3-raising-branch`

**Owns**
`verticals/mainline/apps/demo-api/tests/test_refusal_row_factory.py` ·
`verticals/mainline/apps/demo-api/src/mainline_demo_api/refusal.py` ·
`verticals/mainline/apps/demo-api/src/mainline_demo_api/scenario.py` ·
`docs/diagnosis/refusal-raising-branch.md` (new)

**Done when** both `test_refusal_row_factory` failures pass with the raising branch of
`refusal._explain` genuinely exercised — **or** the file records, in prose and with measurements,
that no such branch is reachable without a write, and both facts are in `still_broken`.

Two tests fail because `_RAISES = "gate_closed_when_issued"` no longer reaches the branch it was
chosen for. The test says so itself (`test_refusal_row_factory.py:364`): *"the seeded permit's
counter is no longer zero"*. It fails in isolation, so this is genuine precondition drift, not
contamination — confirm that yourself by running the file alone before anything else.

Read `verticals/mainline/db/migrations/0119a_fn_explain_refusal.sql` end to end; you may not
edit it (`trappoint render --check` is a zero-diff assertion). Facts I have already established
so you do not have to: it handles **ten** constraint names and has one fallthrough at line 607
which **returns** `diagnosis: 'none'` rather than raising — so an unhandled name cannot reach
the raising branch and a test built on one asserts nothing. The six permit counter constraints
are `gate_closed_when_issued`, `identity_conserved_when_issued`,
`conflicts_resolved_when_issued`, `no_open_warrant_when_issued`,
`boundary_certified_when_issued`, `reading_floor_when_issued` (lines 112, 184, 214, 244, 274,
304). Each raises `P0001` when its counter `IS NULL OR <= 0`, and again when the re-derived
witness set is empty while the counter is not.

So: **measure all six counters on the seeded permit** (`SELECT open_blocking, open_residue,
open_conflicts, … FROM mainline.permit`) against the fixture database, and pick a constraint
whose counter is genuinely zero. That is not moving the goalposts — the docstring's requirement
is *"a permit whose projected counter is zero"*, and the constraint name was only the
instrument. Update the two docstrings (`test_refusal_row_factory.py:46` and `:82`) to say which
counter you measured, what it was, and on what date, so the next drift is legible.

If **no** counter is zero: do not relax `assert "not reproducible" in why_not or "drift" in
why_not`, do not widen it, do not mark the test xfail, and do not touch the seed. Write the six
measurements into `docs/diagnosis/refusal-raising-branch.md`, say plainly that the `SAVEPOINT`
fence's branch is no longer reachable without an INSERT — and note that the file's own
docstring promises *"NOTHING HERE WRITES"*, so a seeded write would be a contract change for the
lead to rule on, not for you.

Falsify whatever you land: put `_RAISES` back to a constraint that decomposes and watch the test
go red with the drift message. A test that passes either way has not been fixed.

**The no-shortcut rule:** NEVER change a seed, fixture, ceiling, threshold or expected value to
obtain a green. The single most damaging act available in this repository is converting a real
defect into a permanent invisible one. If you believe a fixture is genuinely wrong, say so in
`still_broken` with your evidence and leave it alone. Report whole-suite numbers before and after.

### W4 · `w4-refusal-that-writes`

**Owns**
`verticals/mainline/apps/demo-api/tests/test_demo_guard_anonymous.py` ·
`verticals/mainline/apps/demo-api/tests/test_transitions.py` ·
`verticals/mainline/apps/demo-api/src/mainline_demo_api/transitions.py` ·
`verticals/mainline/apps/demo-api/src/mainline_demo_api/db.py` ·
`docs/diagnosis/refusal-that-writes.md` (new)

**Done when** `test_the_four_posts_are_refused_with_the_permit_id_variable_unset` passes because
the four POSTs write nothing — never because the assertion counts differently — the mechanism is
named with a file and a line, and a test fails when the defect is put back.

**Read §0.2 of this plan before anything else. Your brief has been re-cut.** The wave brief sent
this worker after `test_transitions::test_the_request_after_a_gate_run_is_not_a_503`; I measured
the full suite at `073dfea` and **that test passed**. It is not on the board. What is on the
board, and what the brief did not mention at all, is worse:

```
test_demo_guard_anonymous::test_the_four_posts_are_refused_with_the_permit_id_variable_unset
AssertionError: {'permit_rows_total': (116, 117)}
  Differing items: {'permit_rows_total': 117} != {'permit_rows_total': 116}
```

The test drives four POSTs with `MAINLINE_DEMO_PERMIT_ID` unset, expects every one to be
**refused**, and snapshots row counts either side. `mainline.permit` came out with **one more
row than it went in with.** A refusal that writes is the worst behaviour this product can
exhibit in front of a judge, because the screen says no while the database says yes — and it is
the same shape as the defect class this whole repository's negative controls exist to catch. It
outranks everything else on the board. Treat it as a product defect until you have proved
otherwise.

Establish, in this order:

1. **Which POST wrote.** Four are driven; instrument or bisect until you know which one, and
   what statement committed. `transitions.py` is yours; read `_borrowed` (line 287) and
   `_prepare` (line 346) first.
2. **Whether the write precedes the refusal or follows it.** A handler that inserts and *then*
   discovers the guard should have refused, without rolling back, is a different bug from one
   that refuses correctly and leaks a write from an unrelated path.
3. **Whether the row is the test's own or a neighbour's.** The suite is serial, so a row
   appearing between two snapshots taken by one test is almost certainly that test's — but
   `w4_database` (`tests/test_gate_run.py:450`, **session-scoped**, W5's file) is shared with
   `test_gate_run.py` and `test_transitions.py`. If the row turns out to be a neighbour's, that
   is an ordering defect: report it to the lead and to W5 with the evidence; do not edit a file
   you do not own.

Do **not** "fix" this by adding a second place that clears or restores `autocommit`.
`transitions._borrowed` already takes and returns the flag in exactly one place, inside a
`finally`, and `_prepare` is now a tripwire that raises if handed an autocommit connection. That
landed at `531001c` and the reasoning is in the docstring — read it. A second assignment site is
precisely the drift that docstring exists to prevent.

**Two further things you own, both smaller.** First, the `503` test the brief sent you after:
run `test_transitions.py` alone and in suite, record both results, and hand what you find to W5
— you are not chasing it, you are documenting whether it reproduces. Second, session hygiene: I
found two `application_name='mainline-demo-api'` sessions still open on the local node **four
hours** after the run that created them, last query `ROLLBACK TRANSACTION`. Something is not
closing connections. On a warm Lambda that is one idle connection; on a shared cluster it is an
idle-in-transaction `40001` amplifier. `docs/diagnosis/divergence-04-connection-semantics.md`
§F-2 is relevant background and records, with a reproduction, that
`psycopg.SerializationFailure` **is** an `OperationalError`, so `transitions.py:1142` answers
`503 database_unreachable` to a serialization restart — a sentence that is false and
unactionable. Note it in your diagnosis document even if you do not fix it.

**The no-shortcut rule:** NEVER change a fixture, expected value or assertion to obtain a green.
In particular: do not make the row-count assertion pass by excluding `mainline.permit` from the
snapshot, by comparing counts loosely, or by giving the test a private database — the shared
world is the property being asserted. NEVER weaken an assertion. You touch `db.py`, which every
other module imports, so a regression anywhere in the suite is yours; report whole-suite numbers
before and after.

### W5 · `w5-order-independence`

**Owns**
`verticals/mainline/apps/demo-api/tests/test_gate_run.py` ·
`.../tests/test_envelope.py` · `.../tests/test_response_contract.py` ·
`.../tests/test_credentials.py` ·
`.../tests/test_logbudget.py` · `.../tests/test_ratelimit.py` ·
`.../tests/test_routes_gate_run.py` · `.../tests/test_row_factory_contract.py` ·
`.../tests/test_static_site.py` ·
`.../src/mainline_demo_api/gate_run.py` · `.../src/mainline_demo_api/envelope.py` ·
`.../src/mainline_demo_api/credentials.py` · `.../src/mainline_demo_api/logbudget.py` ·
`.../src/mainline_demo_api/ratelimit.py` · `.../src/mainline_demo_api/static_site.py` ·
`scripts/qa/demo_suite_order.py` (new) · `docs/ci/demo-suite-order.md` (new)

**Depends on** `w1`,`w2`,`w3`,`w4`. **Done when** the suite passes in **five** different seeded
orders and in **per-module isolation**, and every ordering dependency found is either fixed or
recorded with its mechanism.

A suite that only passes in one order is a suite that will fail in CI, and this suite has
already proved it has an ordering problem: **the orchestrator recorded
`test_transitions::test_the_request_after_a_gate_run_is_not_a_503` as failing and my full-suite
run at the same HEAD recorded it passing** (§0.2). One of those two runs is lying about the
product, and until you settle which, nobody knows whether that test is green. **Settling it is
your first task**, and it is exactly what randomised order is for: a failure that appears in a
seeded order is reproducible, whereas one that appears in "the suite" is folklore. W4 hands you
its isolated-vs-in-suite results for that test; start from those.

Also settle the one skip: `test_gate_run.py` skipped a case in my baseline. Every skip must
carry its reason — a skip with no reason is indistinguishable from a deleted test. Print it,
and if the reason is not a real environmental fact, say so.

Then the dependencies nobody has looked for. Write
`scripts/qa/demo_suite_order.py`: collect node ids with `pytest --collect-only -q`, shuffle them
with a **seed printed in the output**, write them to a file, and run `pytest @file`. Print the
seed on failure so a red is reproducible — an unreproducible red is worse than none. Also run
each of the thirteen test modules **alone** and diff the per-module results against the
full-suite results; a test that passes alone and fails in suite is contamination, and a test
that passes in suite and fails alone is a hidden dependency on a neighbour's side effects. Both
are defects.

**Do not add a pytest plugin.** `pytest-randomly` and `pytest-random-order` are not in `.venv`
and `uv.lock` is a plan invariant — `uv lock --check` in `ci.yml` is what makes "a stranger
resolves the same graph" true, so adding a dev dependency is a change with CI consequences that
is not yours to make. A stdlib `random.Random(seed).shuffle` in your own script needs no
lockfile edit.

Suspects worth checking first, from my scoping pass: `db.py` module globals `_conn`,
`_dsn_cache`, `_dsn_source`; the session-scoped `w4_database` (`test_gate_run.py:450`) and
`demo_database` (`tests/conftest.py:722`) sharing one cluster; `logbudget.py` and `ratelimit.py`,
which the row-factory conventions table records as *silent* about their row factory; and
`test_envelope.py`, which calls `reset_dsn_cache()` **ten times** — closing `db._conn` under
anyone else who holds it.

Write `docs/ci/demo-suite-order.md`: the seeds you ran, the results, every dependency found, and
the per-module isolation table. It is the input W6 turns into a job.

**Publish the cost, too.** The junit XML carries a `time` attribute per test case. My baseline
took **1535.88 s (25 m 35 s)** for 444 tests, and the ten slowest are dominated by session
fixture setup billed to whichever test touched it first —
`test_row_factory_contract::test_the_production_connection_really_is_dict_row` 50.4 s,
`test_gate_run::test_gate_run_verdict_is_proven` 41.2 s, three cases in
`test_demo_guard_anonymous` at 40.4 s each,
`test_transitions::test_unknown_resource_is_404_and_not_an_envelope` 40.3 s. Reproduce that
table after the wave and put it in your document. W6 cannot budget a CI timeout honestly without
it, and a test genuinely eating 40 s of its own is a defect worth naming rather than a fact of
life.

**The no-shortcut rule:** NEVER change a seed, fixture, ceiling, threshold or expected value to
obtain a green, and never "fix" an ordering dependency by pinning the order — an order pin is a
green that certifies itself. Fix the state that leaks. If a dependency is in a file you do not
own, report it to the lead in `still_broken` with the evidence; do not edit it. Report
whole-suite numbers before and after.

### W6 · `w6-falsification-audit`

**Owns**
`verticals/mainline/apps/demo-api/tests/test_seed_covers_every_console_resource.py` (new) ·
`scripts/qa/demo_suite_falsification.py` (new) ·
`docs/diagnosis/demo-suite-falsification.md` (new)

**Depends on** `w1`,`w2`,`w3`,`w4`,`w5`. **Done when** every defect this wave claims to have
fixed has been independently re-planted and observed to turn the right test red naming the right
file, and a new test refuses a demo seed that does not carry every subject the console declares.

**You are the wave's negative control, and you report to the lead, not to the other workers.**
Three successive NO-GO verdicts on this repository came from fixes that were believed rather
than falsified, and the one caught shortcut — a seed reshaped to match an application constant —
was found by negative controls, not by a green board. A lead who only reads claims is the
failure mode. So: you re-run the experiment.

**Part one — the falsification audit.** For each of W1 through W5, take the defect they say they
fixed, put it back **by hand in a scratch copy of the working tree**, run the specific test, and
record: does it go red, and does the message name the right file and line? Write
`scripts/qa/demo_suite_falsification.py` so this is a command and not a memory — each plant is a
named case with the file, the edit, the test node id, and the expected red. **Revert every plant
and prove the tree is clean with `git diff --exit-code`** before you finish; a falsification
harness that leaves a defect behind is worse than none. A fix whose plant does **not** turn its
test red has not been demonstrated, whatever the board says, and it goes in `still_broken` under
the worker's id — including W1's, including mine if I have ruled wrongly.

**Part two — stop the `cr_id` gap recurring.** The reason 63 tests errored is that the console
declares twelve resources and the demo world carried eleven. Nothing anywhere asserted the
correspondence, so the gap sat there until a fixture happened to ask for `seed["cr_id"]`. Write
`test_seed_covers_every_console_resource.py`: read `RESOURCE_KEYS` out of
`verticals/mainline/apps/console/src/data/resources.ts` (parse it — do **not** restate the list
in Python, a second copy of a list is a second thing to drift), and for each key drive the read
against the seeded fixture database and require a payload rather than a not-found. The console is
the authority for which resources exist; the seed must satisfy it. This is the test that would
have caught W1's defect the day the resource was declared, and it is the deliverable that makes
this wave's work durable rather than a one-time cleanup.

**What you may not do.** `.github/workflows/` belongs to the concurrent CI wave — see the note
at the top of §2 — so you do not add a job, and you do not edit `docs/CI-STATE.md`,
`docs/HONESTY.md`, `qa/` or `scripts/ci/`. Hand your falsification cases to me and I will carry
them across; their W3 is building a CI falsifiability job and yours is the local evidence it
should be pointed at.

**The no-shortcut rule:** NEVER change a seed, fixture, ceiling, threshold or expected value to
obtain a green. Your new test in particular must fail loudly on a seed that is missing a
resource — if you find yourself tempted to exclude a key from `RESOURCE_KEYS` so the test
passes, that exclusion IS the defect and it belongs in `still_broken`. NEVER weaken an
assertion; NEVER edit recorded evidence to silence a checker, fix the checker; NEVER
`terraform apply`. Report whole-suite numbers before and after.

---

## 3 · Rules binding on every worker in this wave

These are not preamble. A worker who breaks one has done net harm, however green the board.

1. **NEVER change a seed, fixture, ceiling, threshold, or expected value to obtain a green.**
   When a test and the code disagree, ask which side is AUTHORITATIVE, and move the other one.
   The database owns anything that is a FOREIGN KEY target, a CHECK, or a trigger projection;
   the committed JSON Schema owns the wire shape; the console owns which resources exist. A
   previous worker "fixed" beat 4 by editing `demo_world.sql` to enrol an application constant
   — making the SEED match the CODE — and three negative controls caught it. It was reverted.
   **If you believe a fixture is genuinely wrong, say so in `still_broken` with your evidence
   and leave it alone.** §1.1 above is a seed change I am authorising as lead, with its
   justification written down and its acceptance test being the deployment, not the suite; it
   is not a licence for a second one.
2. **Run the whole demo-api suite under `--crdb=reuse` before and after your change, and report
   both numbers.** A green obtained by breaking a neighbour is the shortcut in another costume.
   The command is in §4.
3. **NEVER weaken `docs/HONESTY.md`, `docs/CI-STATE.md`, a ratchet, or an assertion.**
   `continue-on-error` and `|| true` are banned. Widening a regex so it matches the message you
   now get is weakening an assertion.
4. **NEVER edit recorded evidence under `evidence/` to silence a checker.** Fix the checker.
5. **NEVER `terraform apply`.** `init` / `validate` / `plan` / `show` and read-only AWS calls only.
6. **NEVER print a credential**, and do not rotate the judge password.
7. **Falsify your own fix.** Before you claim a test now passes, put the defect back by hand and
   watch the test go red naming the right file and line. A test that passes both with and
   without the bug has not been fixed; it has been bypassed. Record the falsification.
8. **CockroachDB constraints are binding:** `CREATE SEQUENCE` / `nextval` / `SERIAL` /
   `unique_rowid()` are BANNED; `FAMILY` is reserved; a vector index is used only when hinted
   (`FROM t@idx`); `db.py:309` opens production connections with `row_factory=dict_row` and that
   fact is a premise of two whole test modules — do not "simplify" it.
9. **Every new file carries an SPDX header** in the form its siblings use (`REUSE.toml` and
   `scripts/qa/check_reuse.py` are the enforcement). Copy the header from the nearest existing
   file of the same kind — `CC-BY-4.0` for `docs/`, `Apache-2.0` for `scripts/`,
   `LicenseRef-FSL-1.1-ALv2` under `verticals/`.
10. **Migrations are rendered, not written.** `verticals/mainline/db/migrations/*.sql` carry
   `@rendered-by trappoint render` and `trappoint render --check` is a zero-diff assertion in
   CI. Nobody in this wave edits a migration. Seeds under `db/seeds/` are hand-authored and are
   W1's alone.

---

## 4 · The command every worker runs, before and after

```powershell
$env:TRAPPOINT_DSN = "postgresql://root@localhost:26257/defaultdb?sslmode=disable"
& D:/CoackroachDBxAWS/mainline/.venv/Scripts/python.exe -u -m pytest `
    D:/CoackroachDBxAWS/mainline/verticals/mainline/apps/demo-api/tests `
    --crdb=reuse -q --tb=line --timeout=180 `
    --junitxml=D:/CoackroachDBxAWS/mainline/out/demo-suite-<worker-id>-<before|after>.xml
```

`--junitxml` is not decoration. pytest's stdout is block-buffered when it is not a terminal and
**I lost a 65-minute run to exactly that**; the XML is written whatever happens to stdout, and
it is what you paste your numbers from. Report `tests`, `failures`, `errors`, `skipped` from the
XML root element.

Note the fixture-database cost (§0.3). Set `MAINLINE_W4_REBUILD=1` only when you have a reason;
it costs ~50 s. A change to any file under `verticals/mainline/db/migrations/` or
`verticals/mainline/db/seeds/` changes `_fingerprint()` and **forces** a rebuild of
`w3_demo_api_<fingerprint>` — W1 should expect its first post-change run to be slow, and that
is correct behaviour, not a fault.

---

## 5 · Sequencing

```
        W1 ── seed the change request, read it back
         │
         ├──► W2 ── the twelfth read, the empty ledger range, the 10 s health
         │
   W3 ───┤        (independent: the refusal raising branch)
   W4 ───┤        (independent: four refused POSTs that left a row behind)
         │
         └──► W5 ── randomised order, repeated runs, the rest of the modules
                     │
                     └──► W6 ── re-plant every fix; make the cr_id gap unrepeatable
```

W1 must land first: 63 of the 68 non-passing results are the one `KeyError` its work removes, and
W2's three defects sit behind it in the same module. W3 and W4 are independent of both and of
each other and start immediately — W4 first among equals, because a refusal that writes is the
most severe thing on the board. W5 starts when W1-W4 have landed, because an ordering dependency
cannot be told apart from an ordinary failure while ordinary failures remain. W6 lands last, so
that every fix it re-plants is a fix that has already been claimed.

The baseline to beat, on every worker's report: **444 tests · 375 passed · 5 failed · 1 skipped ·
63 errors · 1535.88 s**, from `out/demo-suite-baseline.xml` at `073dfea`.

---

## 6 · What I check at merge, and what I will refuse

For each worker, in this order:

1. **The before/after numbers**, from the two junit XMLs, for the whole suite. A worker whose
   "after" has a new failure anywhere is not merged, whatever it fixed.
2. **The falsification.** Re-introduce the defect, watch the test go red, watch it name the
   right file and line. No falsification, no merge.
3. **The diff read against §3.1.** Any change to a seed, a fixture constant, an expected value,
   a ceiling, a threshold, a regex, or a skip condition is read line by line and must carry a
   written justification whose authority is the DATABASE, the committed SCHEMA, or the CONSOLE
   — never "the test now passes".
4. **Every skip carries its reason.** A skip with no reason is indistinguishable from a deleted
   test. A test that moves from *failing* to *skipped* is a regression in this wave and is
   refused; that is precisely how three previous waves reached NO-GO.
5. **`git status`** — no worker may leave a file it does not own modified.
