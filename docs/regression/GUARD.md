<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# THE REGRESSION GUARD, AND THE VIOLATIONS IT WAS SHOWN TO CATCH

`scripts/qa/regression_guard.py` is one command that re-verifies every claim this
repository currently makes. It exists because individual suites answer *does this unit
behave?* and nothing answered **is anything that used to be true no longer true?** — the
only question that matters while a large wave is editing the console, the seed, the copy
and possibly the migration chain at the same time.

```
python scripts/qa/regression_guard.py                      # everything
python scripts/qa/regression_guard.py --no-live            # no HTTP to the deployed demo
python scripts/qa/regression_guard.py --no-cloud           # no SQL over the network
python scripts/qa/regression_guard.py --only KERNEL,BOUNDS --json qa/guard.json
```

One line per check — family, name, `PASS`/`FAIL`/`SKIP`, the measured value beside the
expected one — then a verdict line, and a non-zero exit on any `FAIL`. **A `SKIP` is
printed with the reason it skipped and counted separately, and the verdict line refuses
the word GREEN whenever there is one.** A skip that reads like a pass is how a suite goes
green while asserting nothing, and this repository has already had that.

## THE POINT OF THIS FILE

**A guard nobody has falsified is decoration.** Every check below was made to fail on
purpose, its message recorded verbatim, and the plant reverted. Where a check could not be
falsified it is named here as UNPROVEN rather than counted as a pass — that discipline
outranks the count of green checks, and it is why this document is longer than the script's
own README would be.

Nothing was planted by editing a file this worker does not own. Every plant is a temp copy,
a scratch database, a scratch role or a scratch HTTP stub, reached through a flag the guard
already needs for its own reasons (`--kernel-evidence` lets a lane re-check published
evidence; `--junit` lets it re-read what CI already produced; `--api-src`, `--static-site`,
`--artefact`, `--cloud-roles`, `--seed-dsn`, `--role` and `--base-url` all point the guard
at a different tree). **No planted violation was left behind, and no scratch object
survives**: the two scratch databases and the one scratch role created below were dropped
and their absence confirmed.

---

## THE CHECK INVENTORY — 31 checks in 6 families

| Family | Checks | What a regression means here |
|---|---|---|
| KERNEL | 7 | The gate stopped refusing, or started refusing differently. |
| SUITES | 5 | A test was deleted, started failing, or started skipping. |
| BOUNDS | 3 | Somebody raised the ceiling to make the arithmetic agree. |
| PRIVILEGES | 5 | The code needs something the role cannot reach. |
| LIVE | 4 | The deployed demo stopped telling the truth it was deployed to tell. |
| SEED | 7 | The demo's world lost the shape the demo depends on. |

**KERNEL** — `scripts/proof/gate_refusal.py` is re-run and its EVIDENCE FILE read (not its
terminal output): `verdict` is `PROVEN`, `caveats` is empty, the refusal is
`23514 gate_closed_when_issued`, the drift refusal is `P0001 mainline.fn_permit_merge_gate`,
the admission is `ADMITTED [00000]`. *A different SQLSTATE is a regression even when the
verdict still says PROVEN* — see plant K1, which leaves the verdict at `PROVEN` and moves
four exhibits underneath it.

**SUITES** — `verticals/mainline/apps/demo-api/tests` and `tests/deploy` under
`--crdb=reuse`, counts taken from the `--junitxml` **root element**, failures reported by
node id. Baseline **911 collected / 910 passed / 0 failed / 0 errors / 1 skipped**,
re-measured on 2026-08-15 (`911 tests` in the root element; the one skip is
`test_gate_run.py::test_payload_validates_against_the_json_schema`, *"jsonschema is not a
workspace dependency"*).

> The guard runs the two suites with `--timeout=900` and not the root ini's `timeout=120`.
> That is not a loosened budget, it is the correct one: run TOGETHER the common ancestor is
> the repo root, so the root ini binds, and demo-api fixtures that apply the 271-file chain
> exceed 120 s under load. The first baseline attempt died exactly there — pytest printed a
> `Timeout` traceback and **no summary line at all**, while the XML on disk carried
> `tests="579" failures="8"`. That disagreement is the whole argument for reading the root
> element instead of a terminal tail, and it happened by accident before it was ever a plant.

**BOUNDS** — `DEFAULT_MAX_RESPONSE_BYTES` is read out of `static_site.py` as the
EXPRESSION its author wrote (`136 * 1024`, not merely `139264` — the derivation lives in
the factorisation), and the two extremes are recomputed from the central directory of
`out/lambda/mainline-demo-api-arm64.zip`. Measured: `129400 < 139264 < 457123`, and
exactly one identity object (`assets/index-BH5dfAvF.js`) above the ceiling. `console/dist`
is deliberately not consulted — it carries source maps and zero `.gz` siblings.

**PRIVILEGES** — every schema-qualified relation and routine the demo-api source names
inside a SQL string, **with the privilege the verb implies**, checked against what
`mainline_api` can actually reach across `mainline`, `mainline_ops`, `mainline_meas`,
`mainline_audit` and `trappoint`, plus the catalogue-enumerated `mainline_audit` views and
the trigger-chain read set from `cloud_roles.API_GATE_READ`. Measured on the deployed
cluster: **39 objects extracted** from the source, **14 `mainline_audit` views** enumerated
from the catalogue, **10 tables** from `API_GATE_READ`, **24 trigger functions excluded**
because a trigger function needs no grant to the caller, and the role resolved as
`agent_gate, auditor_ro, mainline_api, public, svc_disposition` — that last list is trap 3
made visible: `SHOW GRANTS` for `mainline_api` alone would have under-reported by four
identities.

**LIVE** — `GET /v1/health` (`ok=true`, `deploy_chain_applied == 271`) and
`POST /v1/demo/gate-run` (`VERDICT PROVEN`, four beats matching by outcome, SQLSTATE,
exhibit **and exhibit source**). Skippable with `--no-live`.

**SEED** — the cloud `mainline_demo` database, reached by reading `COCKROACH_DSN` out of
`.env` and **substituting the database by name**, then confirming with
`SELECT current_database()`. The committed DSN's path segment is `defaultdb`; anything that
reads it verbatim connects fine, counts zero `mainline.*` rows and reports a live
deployment as empty.

---

## THE FALSIFICATION LOG

Each entry: what was planted, where, and the guard's message VERBATIM.

### KERNEL — FALSIFIED

**Control first.** The guard was run against an unmutated copy of a real evidence file and
reported `VERDICT  GREEN - all 7 checks hold`. A guard that is red with the plant *and* red
without it discriminates nothing.

**Plant K1** — a copy of a real gate-refusal evidence document with `refusal.sqlstate`
`23514` → `23505`, `drift_refusal.constraint` renamed, `admission` `ADMITTED [00000]` →
`UNDECIDED [40001]`, and one caveat added. **`verdict` was deliberately left at `PROVEN`.**

```
python scripts/qa/regression_guard.py --only KERNEL --kernel-evidence <scratch>/kernel_PLANTED.json

KERNEL  verdict             PASS  expected PROVEN                    observed PROVEN
KERNEL  caveats             FAIL  expected (none)                    observed 1 caveat(s)
                                  ! a proven-but-qualified run is not a clean one
KERNEL  refusal_sqlstate    FAIL  expected 23514                     observed 23505
                                  ! CF-01 | a different SQLSTATE is a regression even if the verdict says PROVEN
KERNEL  drift_exhibit       FAIL  expected mainline.fn_permit_merge_gate  observed mainline.fn_something_else
                                  ! CF-03 | exhibit source 'parsed'
KERNEL  admission_sqlstate  FAIL  expected ADMITTED [00000]          observed UNDECIDED [40001]
                                  ! a gate that always refuses is a broken gate, not a safe one

VERDICT  REGRESSION - 4 of 7 checks FAILED in KERNEL (3 PASS, 0 SKIP)
```

That first line is the entire reason this family reads the evidence rather than the verdict.

`refusal_exhibit` and `drift_sqlstate` were not mutated in K1 and stayed green; they are
the same comparison as the two that moved, on the same two dictionaries, and are treated
as falsified by construction rather than separately planted.

### SUITES — FALSIFIED

**Plant S1** — a copy of the baseline junit XML with one `<testcase>` given a `<failure>`
child (`failures` bumped to 1) and a second `<testcase>` deleted (`tests` decremented).

```
python scripts/qa/regression_guard.py --only SUITES --junit <scratch>/junit_PLANTED.xml

SUITES  collected  FAIL  expected 911  observed 910
                         ! ... - a shrinking collection is a deleted test, not a faster suite
SUITES  passed     FAIL  expected 910  observed 908
SUITES  failed     FAIL  expected 0    observed 1
                         ! verticals.mainline.apps.demo-api.tests.test_static_site::test_the_live_law_holds_over_the_tree_that_ships_today
SUITES  errors     PASS  expected 0    observed 0
SUITES  skipped    PASS  expected 1    observed 1

VERDICT  REGRESSION - 3 of 5 checks FAILED in SUITES (2 PASS, 0 SKIP)
```

`failed` names the node id, which is the point: *"3 failed"* tells a reader nothing.

**`errors` and `skipped` are UNPROVEN.** They are the same root-element read as `failed`
and `collected` — one `int(suite.get(...))` and one `==` — and both were observed to hold
against a real XML, but neither was independently planted. `errors` additionally proved
itself by accident: the aborted first baseline (`tests="579" failures="8"`) was read
correctly by the same code path.

### BOUNDS — FALSIFIED

**Plant B1** — a temp copy of `static_site.py` with the ceiling raised to `500 * 1024`,
which is exactly the forbidden move: raise the ceiling until the arithmetic agrees.

```
python scripts/qa/regression_guard.py --only BOUNDS --static-site <scratch>/static_site_PLANTED.py

BOUNDS  ceiling_constant  FAIL  expected 136 * 1024 == 139264                        observed 500 * 1024 == 512000
BOUNDS  straddle          FAIL  expected largest_served < 512000 < largest_identity  observed 129400 < 512000 < 457123
BOUNDS  one_refusal       FAIL  expected exactly 1 identity object above the ceiling observed 0: (none)
                                ! one 413 is the measurement; zero means the ceiling stopped binding and two means an object grew past it

VERDICT  REGRESSION - 3 of 3 checks FAILED in BOUNDS (0 PASS, 0 SKIP)
```

Raising the ceiling does not make the deployment healthier — it makes `one_refusal` report
**zero**, which is the guard saying the ceiling has stopped binding at all.

**Plant B2** — a temp copy of the Lambda zip with one extra 200 KB `web/` object appended
and no `.gz` sibling for it.

```
python scripts/qa/regression_guard.py --only BOUNDS --artefact <scratch>/artefact_PLANTED.zip

BOUNDS  ceiling_constant  PASS  expected 136 * 1024 == 139264                        observed 136 * 1024 == 139264
BOUNDS  straddle          FAIL  expected largest_served < 139264 < largest_identity  observed 200002 < 139264 < 457123
                                ! assets/planted-oversize-DEADBEEF.js gzipped | assets/index-BH5dfAvF.js identity | 58 objects, 57 siblings
BOUNDS  one_refusal       FAIL  expected exactly 1 identity object above the ceiling observed 2: assets/index-BH5dfAvF.js, assets/planted-o~

VERDICT  REGRESSION - 2 of 3 checks FAILED in BOUNDS (1 PASS, 0 SKIP)
```

B2 catches an object that ships without a sibling, which is the realistic version of this
regression: a build step drops the gzip pass and the wire size quietly becomes the disk
size.

### PRIVILEGES — FALSIFIED (all five)

**Plant P1** — a temp copy of the demo-api package with two lines appended to `reads.py`:
an `INSERT INTO mainline.person` (a table the role can read and not write) and a
`SELECT … FROM mainline.no_such_table`.

```
python scripts/qa/regression_guard.py --only PRIVILEGES --api-src <scratch>/api_src_PLANTED

PRIVILEGES  references_resolve  FAIL  expected every referenced object resolves…  observed 1 unresolved
                                      ! mainline.no_such_table (SELECT)
PRIVILEGES  relations           FAIL  expected mainline_api reaches every relation…  observed 3 shortfall(s)
                                      ! mainline.exposure_line INSERT; mainline.exposure_receipt INSERT; mainline.person INSERT
```

**Plant P2** — a scratch database on the local node (`w_regression_guard_priv`) carrying
`mainline.permit` and a `mainline.merge_permit(UUID, BYTES, STRING, STRING, JSONB, BYTES,
INT2, BYTES)` procedure with `EXECUTE` revoked from `public`, probed as a scratch role
(`w_rg_probe`) with a minimal `--api-src` that reads the table and calls the procedure.

```
python scripts/qa/regression_guard.py --only PRIVILEGES --api-src <scratch>/api_src_MINIMAL \
  --seed-dsn postgresql://root@127.0.0.1:26257/defaultdb?sslmode=disable \
  --database w_regression_guard_priv --role w_rg_probe

PRIVILEGES  relations                     PASS  observed 0 shortfall(s)
PRIVILEGES  routines                      FAIL  observed 1 shortfall(s)
                                                ! mainline.merge_permit EXECUTE - held by admin, root; w_rg_probe acts as public, w_rg_probe
PRIVILEGES  routine_signature_normalised  FAIL  expected 1 routine(s) matched across both spellings  observed 0 matched
PRIVILEGES  gate_chain                    FAIL  observed 10 shortfall(s)
                                                ! mainline.change_request SELECT; mainline.cr_clause SELECT; …
```

`relations` staying green in the same run is the negative control: the table grant that
WAS made is still seen, so the routine failure is about the routine.

**Plant P3** — an `--api-src` that reads a table and `CALL`s nothing, i.e. the day somebody
stops invoking a stored procedure from the application.

```
PRIVILEGES  routine_signature_normalised  FAIL  expected 0 routine(s) matched across both spellings  observed 0 matched
                                                ! SHOW GRANTS spells a routine with its signature and information_schema does not;
                                                  this check fails if that trap stops being exercised
```

**Plant P4** — a temp copy of `cloud_roles.py` with `mainline.person` and
`mainline.no_such_gate_table` added to `API_GATE_READ`.

```
python scripts/qa/regression_guard.py --only PRIVILEGES --cloud-roles <scratch>/cloud_roles_PLANTED.py

PRIVILEGES  gate_chain  FAIL  observed 1 shortfall(s)
                              ! mainline.no_such_gate_table SELECT
```

`mainline.person` is genuinely readable by `mainline_api` and correctly did NOT appear.

### LIVE — FALSIFIED

**Plant L1** — `--base-url` pointed at a scratch HTTP stub on `127.0.0.1:8731` answering
the two routes with three deliberate regressions: `deploy_chain_applied` 270, beat 3's
`constraint_source` `parsed` → `reported`, and `verdict` `NOT PROVEN`. **Nothing was sent
to the real deployment and no AWS call was made.**

```
LIVE  health_ok             PASS  expected ok=true  observed ok=True
LIVE  deploy_chain_applied  FAIL  expected 271      observed 270
LIVE  gate_run_verdict      FAIL  expected PROVEN   observed NOT PROVEN
LIVE  gate_run_beats        FAIL  expected 4 beats matched by outcome, sqlstate, exhibit~  observed 4 beats, 2 mismatch(es)
                                  ! beat 3 exhibit_source: expected 'parsed', observed 'reported';
                                    beat 3 matched_expectation: expected True, observed False
```

Beat 3 is the one worth staring at: the exhibit string is identical
(`mainline.fn_permit_merge_gate`) and the SQLSTATE is identical (`P0001`). Only *how the
exhibit was obtained* changed, and the guard caught it — because `P0001` carries no
constraint name, so an exhibit that is suddenly `reported` means something other than the
raising body wrote it.

**Plant L2** — `--base-url` pointed at a closed port. All four checks go `FAIL` with
`observed unreachable` and the connection error. *Unreachable is a FAIL, not a skip*: "the
demo could not be asked" is a finding, and only `--no-live` may turn it into a skip.

**Control** — `--no-live` produces four `SKIP` lines, each naming the URL that was never
asked, and the verdict line reads:

```
VERDICT  NO REGRESSION FOUND, 4 of 4 checks NOT RUN - LIVE were skipped, not passed
```

which is the whole requirement: the word GREEN does not appear.

### SEED — FALSIFIED

**Plant D1** — a scratch database on the local node (`w_regression_guard_seed`) holding the
same seven relations with a shape that is wrong in six ways at once: 5 defeater options
instead of 6, one check carrying TWO distinct `vocab_sha256` values, 3 leaves, 2 nodes, a
checkpoint claiming `tree_size` 4 over 3 leaves, 2 permits, 1 obligation, 1 credential.

```
python scripts/qa/regression_guard.py --only SEED \
  --seed-dsn postgresql://root@127.0.0.1:26257/defaultdb?sslmode=disable \
  --database w_regression_guard_seed

SEED  database_selected            PASS  expected w_regression_guard_seed  observed w_regression_guard_seed
SEED  defeater_option              FAIL  expected 6 rows across 2 checks   observed 5 rows across 2 checks
SEED  vocabulary_is_one_per_check  FAIL  expected 1 distinct vocab_sha256 per check  observed 3 (check, digest) pairs over 2 checks
                                         ! dec0de00-0007-4000-8000-000000000001 has 2
SEED  ledger_leaf                  FAIL  expected 4  observed 3
SEED  ledger_node                  FAIL  expected 3  observed 2
SEED  checkpoint_tree_size         FAIL  expected max(tree_size) == leaves committed, per site  observed S: tree_size 4 vs 3 leaves
SEED  core_counts                  FAIL  ! mainline.permit: expected 1, observed 2; mainline.blocking_check: expected 2, observed 1; …

VERDICT  REGRESSION - 6 of 7 checks FAILED in SEED (1 PASS, 0 SKIP)
```

**Plant D2** — the `defaultdb` trap, planted directly: `--database defaultdb`, i.e. what
happens when the DSN's path segment is believed.

```
SEED  database_selected  FAIL  expected a reachable seeded database  observed unreadable
                               ! [42P01] relation "mainline.defeater_option" does not exist
```

A loud `42P01` and not a silent census of zeroes, which is the failure this family was
written around.

---

## WHAT COULD NOT BE FALSIFIED — NAMED, NOT COUNTED AS PASSES

Three checks are UNPROVEN. They ran, they held, and no plant was found that makes them go
red for their own reason.

1. **`SUITES errors`** and **`SUITES skipped`**. Both read the same root element with the
   same two lines of code as `SUITES failed`, which WAS planted; neither was given a plant
   of its own. `errors` has a partial witness — the aborted first baseline run
   (`tests="579" failures="8" errors="0"`) was parsed correctly — but that is evidence the
   read works, not evidence the comparison fails.

2. **`SEED database_selected` — the disagreement branch.** The check asserts that the
   database named on the command line is the one `SELECT current_database()` reports. Plant
   D2 turned that line red, but by a different route (the relations do not exist in
   `defaultdb`, so the count query raised `42P01` and the whole family reported
   `unreadable`). Making the server *confirm a different database than the one requested*
   is not reachable through libpq — the connection string decides — so the branch that
   compares `requested` against `confirmed_by_server` has never been observed firing. It is
   cheap insurance and it is not proven.

3. **`PRIVILEGES routines` against CockroachDB Cloud specifically.** The mechanism was
   falsified on the local node with a real `REVOKE` (plant P2). It was not falsified
   against the cloud cluster, because doing so would mean revoking a grant from the live
   `mainline_api` role — a mutation of the deployment this worker will not make. The
   mechanism is identical (`SHOW GRANTS` plus role-membership expansion) and the cloud path
   was exercised read-only; the *falsification* is local-only, and that is a weaker claim.

---

## TWO THINGS THIS GUARD FOUND ON ITS FIRST RUN

### 1. `has_function_privilege` is a stub on CockroachDB v26.2.5

The first draft of the PRIVILEGES family asked
`has_function_privilege(role, oid, 'EXECUTE')`. Plant P2 was built to make it say `false`,
and it would not: on a scratch database where `EXECUTE` had been revoked from `public` and
the behavioural truth was

```
CALL as probe: REFUSED 42501 user w_rg_probe does not have EXECUTE privilege on procedure merge_permit
```

`has_function_privilege` still answered `true` — for that role, for `root`, for `admin`,
for `public`, for everybody. **A check built on it cannot fail, and a check that cannot
fail is decoration.** It was replaced with a `SHOW GRANTS` read plus explicit
role-membership expansion, which costs the two things the built-in would have done for
free — stripping the signature off the object name, and following `mainline_api`'s
membership in `agent_gate`, `auditor_ro` and `svc_disposition` — and which *can* go red.

`has_table_privilege` was put through the same control on the same database and tracks the
behaviour exactly (`SELECT` → `true` and the query succeeds; `INSERT` → `false` and the
statement raises `42501`), which is why relations are still decided by it.

This is the falsification discipline paying for itself before the guard was ever run in
anger: without a plant, the routine check would have been permanently, invisibly green.

### 2. A sixth grant shortfall, found by comparison rather than by an outage

**The guard is RED on the tree as it was found**, in exactly the family that has the body
count:

```
PRIVILEGES  relations  FAIL  expected mainline_api reaches every relation the code reads or writes
                             observed 2 shortfall(s)
                             ! mainline.exposure_line INSERT; mainline.exposure_receipt INSERT
```

`transitions.materialise_checks` — the handler behind
`POST /v1/permits/checks:materialise` — executes `INSERT INTO mainline.exposure_receipt`
and `INSERT INTO mainline.exposure_line`. Confirmed against the deployed cluster:

```
information_schema.table_privileges → mainline_api holds SELECT on both, and nothing else.
scripts/deploy/cloud_roles.API_WRITE → 11 pairs, and neither table is among them.
```

So the statement would raise `42501` the moment it runs. It has not yet been seen in
production for one reason only: `transitions._demo_guard` answers `423` for the seeded demo
subject before the SQL is reached, so the only permit anybody drives on the deployed demo
never gets there. **That is a mask, not a fix** — any other subject reaches the insert.

This was found by putting the two halves side by side, which is the thing that had never
been done. It was not confirmed by driving the live endpoint, and deliberately so: the
confirming request is a write against the shared demo database, and the static evidence
(the SQL in the source, the grant in the catalogue) is decisive without it.

**Fixing it is out of this worker's scope** — the repair belongs in
`scripts/deploy/cloud_roles.API_WRITE` and in the cluster, and both are somebody else's
file and somebody else's apply. The guard's job was to make the question visible, and it
is now one line of output instead of the next outage.

---

## THE VERDICT AGAINST THE TREE AS IT WAS FOUND

Measured 2026-08-15, all six families in one invocation, live and cloud both on, against
the working tree mid-wave. KERNEL and SUITES were re-measured from source minutes earlier
(the proof re-run end to end; the suites run end to end) and that run's artefacts were fed
back through `--kernel-evidence` / `--junit` so that all 31 checks land in one verdict
line rather than three. Saying which is which is the point — a number is only as good as
the sentence describing how it was taken.

| Family | Result |
|---|---|
| KERNEL | 7/7 PASS — chain 271/271, `PROVEN`, `caveats (none)`, `23514` / `P0001` / `00000` |
| SUITES | 5/5 PASS — 911 collected, 910 passed, 0 failed, 0 errors, 1 skipped |
| BOUNDS | 3/3 PASS — `136 * 1024`, `129400 < 139264 < 457123`, exactly one refusal |
| PRIVILEGES | 4/5 PASS, **1 FAIL** — `mainline.exposure_receipt` and `mainline.exposure_line` INSERT |
| LIVE | 4/4 PASS — `ok=true`, `deploy_chain_applied 271`, `VERDICT PROVEN`, four beats matched |
| SEED | 7/7 PASS — 6 options / 2 checks / 1 digest each, 4 leaves, 3 nodes, tree_size consistent |

**`VERDICT  REGRESSION — 1 of 31 checks FAILED in PRIVILEGES (30 PASS, 0 SKIP)`**

That single red is not the wave's doing and it is not new; it is a standing gap that
nothing had ever been in a position to see. Everything the founder was worried about — the
gate, the suites, the ceiling, the seed, the deployed demo — is intact and now has one
command that says so.
