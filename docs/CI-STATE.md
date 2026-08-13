<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# CI state — what GitHub actually says

**Measured 2026-08-13 by W9 of the CI-TRUTH wave, at commit `53197f5` on `master`, on a
repository that is PUBLIC.** All eighteen workflows were **dispatched in this sitting**,
between `02:55:41Z` and `02:56:50Z`, against the public tip, **after every other worker in
this wave had landed** — the dispatch was held until `origin/master` stopped moving for
three consecutive minutes, and the SHA of every run below was checked against the tip
afterwards. Every log was read **warm**, in the same sitting, with
`gh run view <id> --log-failed`. Every run id opens without an account.

**No row on this page is inherited, projected, or measured on a branch.** The revision this
replaces carried a caveat that governed the whole page: its rows sat on work that was not
committed. That caveat does not survive here. §0.2 states the different, smaller one that
does.

---

## THE BOARD, STATED PLAINLY

```
18 workflows        10 GREEN        8 RED
                                    ├─ 5 RED ON PURPOSE   schema · db · demo-health ·
                                    │                     custody-chain · db-schema
                                    └─ 3 RED ON A DEFECT  ci · aws-evidence ·
                                                          nightly-differential

3 things that ASSERT NOTHING, named here rather than counted as passes:
    ci                   the PL-2 job, on a dispatch — push-gated; it did not run (§1.1)
    aws-evidence         the mutation family         — aborts before it plants, so not one
                                                       plant is tested (§3.2)
    nightly-differential the gate/oracle comparison  — the harness dies before the
                                                       comparison is made (§3.3)
```

**What a judge scanning the Actions tab needs first.** Five of the eight reds are lanes
refusing to certify something this repository has not built yet, and **each one now says so
in the first clause of the message GitHub renders**. That wording is the whole of what this
worker changed in `schema.yml`, `ci.yml` and `demo-health.yml`: **no assertion was relaxed,
no threshold moved, no job skipped.** The three reds that are defects are `ci` (one stale
cassette index, plus three by-design custody rows), `aws-evidence` (a scanner
false-positive on a 300 GiB byte count) and `nightly-differential` (its own test harness).

Nothing here was made green by being quieter. Measured across the whole of
`.github/workflows/` at `53197f5`:

```
$ git grep -nE "^\s*continue-on-error:" -- .github/workflows/     → no matches
$ git grep -n "|| true"               -- .github/workflows/       → one live line:
      db.yml:564:  run: docker rm -f trappoint-crdb || true
```

Every other textual hit is a comment recording where a suppression used to be. The survivor
is a container-cleanup line whose only failure mode is "it was already gone".

---

## 0. Method, and the caveat that governs this page

### 0.1 Re-check every number here yourself

```bash
# every workflow's real conclusion on the default branch
gh run list --branch master --limit 200 \
  --json databaseId,workflowName,conclusion,createdAt,event \
  --jq 'group_by(.workflowName)[] | max_by(.createdAt) | "\(.workflowName)|\(.conclusion)|\(.databaseId)"'

# one workflow's conclusion, job by job
gh run view <run-id> --json jobs --jq '.jobs[] | "\(.conclusion) :: \(.name)"'

# the precise cause of a red — the command every claim below rests on
gh run view <run-id> --log-failed
```

Every workflow in this repository declares `workflow_dispatch`, so every row here was
**created** rather than found: `gh workflow run <name> --ref master`, eighteen times, then
the logs read before they went anywhere. **Logs expire, and a recorded board is not
evidence** — that is why the board was re-created rather than re-read. A run id is a claim
that something happened; only a log somebody opened is a claim about *what*.

**One methodological warning, earned the hard way on this page.** An earlier draft of §2.5
reported that `db-schema`'s `mi-red` had narrowed from five refusals to two. It had not.
The "two" was an artefact of a `tail -25` on this author's own `gh run view` pipeline, which
cut the first three lines off a five-line list. It was caught by re-running the same grep
without the tail against three different runs, which agreed on five. **A quoted cause is
only as good as the command that produced it, and the command belongs in the note.**

### 0.2 The caveat that governs this page, stated once

**This board is `53197f5` — the public tip — and it is the whole of what a stranger can
check.** At the moment of measurement the working tree also carried **31 tracked files
modified and not committed by workers other than this one** — two other waves running in
parallel (demo-correctness and deploy-safety) and the one CI-TRUTH worker who did not land.
(Measured as `git status --porcelain -uno`, minus this worker's own three files.)
**Nothing on this page credits any of it.**

That is a different caveat from the previous revision's, and the difference is the point:

* the previous revision's rows were measured **on work that was not on `master`**, so a
  reader could not reproduce them;
* every row here is measured **on `master`**, so a reader can reproduce all of them. The
  uncommitted work is named only where it would move a row, always as *"this is not on the
  board"*, never as a row.

**Exactly one red would move if that work landed:** `aws-evidence` (§3.2), whose scanner fix
sits uncommitted in `scripts/aws/verify_evidence.py`. **A repair without a run id is a
plan**, and this page counts plans as red.

**This board was taken twice, and the first taking is not published.** A full eighteen-lane
dispatch was made at `9221d0c`; while its logs were being read, four more commits landed on
`master` — the envelope teeth, the `mypy` and `ruff` repairs, and two anti-vacuity
documents. Every one of those changed a row. **The first board was discarded rather than
patched**, because a board whose rows come from two different trees is a board a reader has
to date row by row, which is the specific defect this revision exists to remove.

---

## 1. Every workflow, with its real conclusion

| workflow | conclusion | run | kind | § |
|---|---|---|---|---|
| `boundary` | success | [31662351225](https://github.com/Shaugato/mainline/actions/runs/31662351225) | — | §4 |
| `claims` | success | [31662354680](https://github.com/Shaugato/mainline/actions/runs/31662354680) | — | §4 |
| `cloud-verify` | success | [31662358004](https://github.com/Shaugato/mainline/actions/runs/31662358004) | — smaller claim than its name | §4.2 |
| `console` | success | [31662361883](https://github.com/Shaugato/mainline/actions/runs/31662361883) | — | §4 |
| `judge-pack` | success | [31662365372](https://github.com/Shaugato/mainline/actions/runs/31662365372) | — **and its envelope step is now falsifiable** | §5.2 |
| `mutation-ratchet` | success | [31662368980](https://github.com/Shaugato/mainline/actions/runs/31662368980) | — | §4 |
| `release-proof` | success | [31662372526](https://github.com/Shaugato/mainline/actions/runs/31662372526) | — | §4 |
| `skills` | success | [31662376108](https://github.com/Shaugato/mainline/actions/runs/31662376108) | — | §4 |
| `submission` | success | [31662344526](https://github.com/Shaugato/mainline/actions/runs/31662344526) | — | §4.1 |
| `supply-chain` | success | [31662348026](https://github.com/Shaugato/mainline/actions/runs/31662348026) | — | §4 |
| `schema` | failure | [31662337715](https://github.com/Shaugato/mainline/actions/runs/31662337715) | **RED ON PURPOSE** | §2.1 |
| `db` | failure | [31662326715](https://github.com/Shaugato/mainline/actions/runs/31662326715) | **RED ON PURPOSE** — same cause | §2.2 |
| `demo-health` | failure | [31662379410](https://github.com/Shaugato/mainline/actions/runs/31662379410) | **RED ON PURPOSE** | §2.3 |
| `custody-chain` | failure | [31662333865](https://github.com/Shaugato/mainline/actions/runs/31662333865) | **RED ON PURPOSE** — two causes | §2.4 |
| `db-schema` | failure | [31662330242](https://github.com/Shaugato/mainline/actions/runs/31662330242) | **RED ON PURPOSE** — five promotions owed | §2.5 |
| `ci` | failure | [31662323414](https://github.com/Shaugato/mainline/actions/runs/31662323414) | defect — 10 of 12 jobs green | §3.1 |
| `aws-evidence` | failure | [31662340980](https://github.com/Shaugato/mainline/actions/runs/31662340980) | defect — **and it silences a family** | §3.2 |
| `nightly-differential` | failure | [31662319746](https://github.com/Shaugato/mainline/actions/runs/31662319746) | defect — **asserts nothing** | §3.3 |

**Score: 10 green, 8 red, 0 never-run.** (A nineteenth entry, `Dependabot Updates`, is
GitHub's own managed workflow, not this repository's lane.)

### 1.1 One red cannot be produced by a dispatch, and this page says which

`ci`'s **PL-2** job is gated on `github.event_name == 'push' && github.ref ==
'refs/heads/master'`. On dispatched run 31662323414 it reported **success**, because on any
other event it emits a `::warning` instead of failing. **That green asserts nothing.** The
by-design red it exists to raise is recorded in §7, from a push run, and this page will not
launder a dispatch green into a claim that PL-2 held.

---

## 2. The five reds that are red on purpose

Every lane here **must stay red**, and every one now states in the first clause of the
annotation GitHub renders that it is deliberate, plus the artefact that would end it.

### 2.1 `schema` — two objects the reference vertical references and nothing creates

Run [31662337715](https://github.com/Shaugato/mainline/actions/runs/31662337715). Three
jobs red, one green (*anomaly coverage and manifest totality*), **one cause**. From the log,
verbatim:

```
##[error]RED BY DESIGN, NOT A CI DEFECT: 2 object(s) referenced by
packages/trappoint-sql/refvertical/sql and created by no file in it: trappoint_ref.clause,
trappoint_ref.event. This lane refuses to be closed by narrowing the matrix, skipping a job
or dropping the foreign key -- only a CREATE TABLE migration for each object named above
turns it green, because two bindings that both render is the substrate claim and one
binding is a template engine with an audience of one.
```

**What turns it green:** a `CREATE TABLE` migration for `trappoint_ref.event` and one for
`trappoint_ref.clause`, at `packages/trappoint-sql/refvertical/sql/<nnnn>_<table>.sql`.
Owner: KERNEL domain, `docs/leads/kernel.md` 1.1.

**This is the model red of the repository, because it refuses the cheap fixes.** Narrowing
the matrix, skipping the job or dropping the foreign key would each close the lane by
deleting the question, and the message now says so in one sentence so that nobody tries.

Re-measured on this workstation, independently of the runner:

```
reference vertical: 22 tables created, 12 referenced, 2 with no producer
  MISSING: trappoint_ref.clause consumed by 0066_disposition
  MISSING: trappoint_ref.event  consumed by 0058_blocking_check
109 .sql files scanned
```

Two of the three red jobs — *unwelding matrix* and *the self-attesting gate* — are
**COLLATERAL**: they never reached their own subjects. Their annotations carry the word
**UNPROVEN**, because "did not run" and "ran and failed" are different findings:

```
##[error]RED BY DESIGN, NOT A CI DEFECT. 2 object(s) are referenced by … CockroachDB
refused at 0058_blocking_check on trappoint_ref.event, the first of them. … This job did
NOT fail on its own subject -- the unwelding matrix did not execute, so it is UNPROVEN by
this run rather than failing. WHAT TURNS IT GREEN: a CREATE TABLE migration for each object
named above. WHAT DOES NOT: narrowing the matrix, skipping this job, or dropping the
foreign key -- each of those closes the lane by deleting the question.
```

### 2.2 `db` — the same finding, a second lane, and its old finding is paid

Run [31662326715](https://github.com/Shaugato/mainline/actions/runs/31662326715). Census job
green, migrate job red on the identical cause:

```
one version constant, and it lives in compose.yaml ............ success
migrate + conform, on a node pinned to Cloud's gc.ttlseconds ... failure
    trappoint migrate: REFUSED: 0058_blocking_check: [42P01]
    relation "trappoint_ref.event" does not exist
```

**`db`'s previously recorded cause is gone.** The image census now reads

```
floating tag:     0  (ceiling 0)
restated literal: 18 (ceiling 19)
```

so the `restated literal rose from 19 to 20` red that earlier boards carried is **paid**,
and the floating-tag count is at zero against a ceiling of zero. The lane's own notice asks
for the restated ceiling to come down to 18. **This page records that rather than doing it:
lowering a ceiling changes an assertion, and changing an assertion is not a documentation
task.**

**What turns `db` green:** the two producers of §2.1, after which `db`'s `CONFORMANCE` step
executes for the first time in this repository's history.

**What `db` still does not do:** say *red by design* in its own message. Three workflows
were in this worker's scope for that change and `db.yml` was not one of them, so a reader of
the Actions tab still has to come here for `db`. Named, not hidden.

### 2.3 `demo-health` — no demo is deployed, and the red names its cure

Run [31662379410](https://github.com/Shaugato/mainline/actions/runs/31662379410). Verbatim:

```
##[error]no demo URL is published; this lane is red because the demo is not deployed, not
because it is broken.

RED BY DESIGN, NOT A CI DEFECT. THE ARTEFACT THAT WOULD MAKE THIS LANE GREEN IS ONE
FIELD IN ONE FILE: docs/submission/SUBMISSION.json -> demo_url, holding the https URL
of a deployed demo. Nothing else in this repository has to change.
```

The annotation continues, on the run summary page as well as in the log, with **the
assertions it did not get to make** — `GET /` returning an HTML document, `GET /v1/health`
returning `ok:true` with a `server_date` inside the freshness window, and the four beats of
`POST /v1/demo/gate-run` with their SQLSTATEs (`00000`; `23514 gate_closed_when_issued`;
`P0001 mainline.fn_permit_merge_gate`; `00000`), plus `persisted:false` and the server's own
`PROVEN`. **A reader therefore learns the size of the hole, not only its name.**

**What turns it green:** `docs/submission/SUBMISSION.json` → `demo_url` holding an `https`
URL. No repository variable, no secret, no workflow edit. `terraform apply` has not been run;
the plan is committed and the founder re-authorises before any apply.

**And the lane can be proved sound today, with no deployment at all** — the red prints the
command itself:

```
gh workflow run demo-health -f url=https://<a host that answers>
```

The dispatch input outranks the file, so such a run exercises every assertion above and
never reaches the failing step. **An intentional red nobody can falsify is
indistinguishable from a lane that has quietly stopped working**, which is why that command
is in the error rather than in a comment.

### 2.4 `custody-chain` — 7 of 16 checks have no implementation, and three K2 artefacts do not exist

Run [31662333865](https://github.com/Shaugato/mainline/actions/runs/31662333865). **Five
jobs green, two red, two independent by-design causes.**

**Cause 1 — 7/16.** Verbatim:

```
NOT CHECKED — 7 of 16 checks did not run
16 checks | 9 passed | 0 failed | 7 not checked
##[error]Checks 4, 5, 6, 7, 8, 11, 12 did not run. Owner: verify-crypto. This lane is
RED ON PURPOSE and stays red until the modules named in the annotations below exist.
Nothing is skipped, excused or ratcheted to conceal it.
```

Each of the seven carries its own annotation naming the module, the test, and what it
*would* have proved — log signature, RFC-3161 bracket, beacon, witness quorum, S3
object-lock, gate self-attestation, WebAuthn re-verification. **What turns it green:** those
seven runners under `packages/trappoint-verify/src/trappoint_verify/checks/`. The lane's own
error text carries the words *RED ON PURPOSE*; that was verified in this run's log, not
inferred from a source comment.

**Cause 2 — the K2 exit criteria**, `3 failed, 10 passed, 2 skipped`:

```
K2.4 NOT MET — MISSING ARTEFACT: evidence/k2-checkpoint-cadence.json
K2.5 NOT MET — MISSING ENTRY: spec/CHANGELOG.md carries no line naming
               `wire/checkpoint.md` at v1.0.
K2.6 NOT MET — MISSING ARTEFACT: evidence/k2-migration-attestation.json
```

Each names its owner and its cure — for K2.4, *"a file at that path carrying keys 'samples'
(>= 30), 'p50_seconds', 'p95_seconds', 'max_seconds' and 'measured_at', written by observing
consecutive checkpoint publications against a running sequencer"* — and each says why it is
not faked: *"the ~60 s window of undetectable mutation is the single honest number the whole
custody argument turns on. A number this test invented would be a number nobody measured."*

**The canonicaliser drift earlier boards recorded here is gone**, and its absence is
measured, not assumed — see §6.1.

### 2.5 `db-schema` — the catalogue is green; `mi-red` refuses five promotions

Run [31662330242](https://github.com/Shaugato/mainline/actions/runs/31662330242). Two of
three jobs green — *the catalogue is committed, current and well-formed* and *the version
comparison bites* — and `mi-red` red:

```
5 HELD (the red law refuses on these) · 2 RED (an owning test fails; the law holds) ·
14 UNWITNESSED (no owning test resolves at all)
REFUSED: MI06 is pending but its tests pass — promote it in mi_catalogue.yaml
REFUSED: MI10 …   REFUSED: MI21 …   REFUSED: MI22 …   REFUSED: MI27 …
scripts/mi_ratchet.py red exited 1 (0 held, 1 law broken, 2 cannot determine)
```

This is a **red-before-green integrity law doing its job**: an invariant marked `pending`
whose owning tests all pass is either already enforced (and the catalogue is stale) or its
tests witness nothing. The lane refuses to guess, and states its own falsifiability:

> *"promote only if one of the tests above makes an object above REFUSE. A test that would
> still pass with that object dropped witnesses nothing, and an `enforced` row recorded on
> it is the false green PL-2 exists to forbid."*

**What turns it green:** for each of MI06, MI10, MI21, MI22 and MI27, either a promotion in
`mi_catalogue.yaml` backed by a test observed to make the enforcing object refuse, or an
owning test that actually fails.

**This set has not moved.** Identical across three runs on three commits — 31657335542 at
`06f41f8`, 31660091618 at `9221d0c`, 31662330242 at `53197f5`. The earlier board's cause for
this lane, a DM-9 violation, **is paid**; what is left is this, and it was here before.

### 2.6 `ci`'s PL-2 job — by design, and it only fires on a push

PL-2 asks for the URL of a `db` run in which the **`CONFORMANCE` step itself** went red. No
such run exists, because `CONFORMANCE` has never executed (§2.2). Recording any other red
`db` run would put a URL in a field that asks for a different observation. The annotation now
carries all of that where a reader sees it:

```
::error title=RED BY DESIGN - PL-2: the db lane's red conform run URL is still UNRECORDED::
RED BY DESIGN, NOT A CI DEFECT. … WHAT TURNS IT GREEN: the producer for trappoint_ref.event
lands, the next db push-run on master reaches CONFORMANCE, that step is red, and THAT run's
URL replaces the word UNRECORDED in docs/adr/0005-red-before-green.md. WHAT DOES NOT: any
other red db run, deleting the line, or relaxing this check.
```

The push-run row is §7, because the dispatch that produced every other row on this page
cannot exercise this job.

---

## 3. The three reds that are defects

### 3.1 `ci` — 10 of 12 jobs green; one stale cassette index and three by-design rows

Run [31662323414](https://github.com/Shaugato/mainline/actions/runs/31662323414).

| job | verdict |
|---|---|
| every checker this lane invokes exists | success |
| **actionlint** | **success** — all eighteen workflows, `shellcheck` over every `run:` |
| PL-2 — the red run is recorded | success — **push-gated, asserts nothing here** (§1.1) |
| import-linter contracts · and no package outside them | success |
| REUSE — every file names its licence | success |
| the lockfile is authoritative · workspace membership | success |
| **mypy · and the target list is complete** | **success** |
| **ruff format · the counted lint ratchet** | **success** |
| the sequence ban, repository-wide | success |
| RED BY DESIGN, and it must stay red | success — every declared red is still red |
| pytest --crdb=none | **failure** |
| CI summary | **failure** (aggregate) |

**`ruff` and `mypy` are green for the first time on this board.** Confirmed independently on
this workstation against a fresh LF export (`git archive HEAD | tar -x`), which is
byte-for-byte what the runner checks out:

```
$ ruff format --check .        # ruff 0.16.1, on the LF export of 53197f5
1443 files already formatted
```

**The same sweep on the Windows working tree reports 227 files.** That number is a
line-ending artefact — this checkout has no `.gitattributes` — and appears here only so that
nobody takes it for a fact about the code. **There must be no `ruff format .` sweep on this
tree.**

**`pytest --crdb=none`:** `4 failed, 8468 passed, 839 skipped, 13 deselected, 2 warnings in
334.02s`. The four, named:

| test | cause | classification |
|---|---|---|
| `test_k2_4_checkpoint_cadence_measured_and_deadman_defined` | K2.4 missing artefact | by design (§2.4) |
| `test_k2_5_checkpoint_wire_format_tagged_v1_0_with_changelog_entry` | K2.5 missing entry | by design (§2.4) |
| `test_k2_6_migration_attestation_chained_with_a_stable_fingerprint` | K2.6 missing artefact | by design (§2.4) |
| `test_every_recorded_body_hashes_to_its_index_row` | `assert '11d32dd3a13f…7d6d2573735fe' == '136eec3462c2…993e7c8f9ffea'` | **defect** |

**The last row is a finding this page records for the first time.**
`packages/mainline-agentkit/tests/test_live_cassettes.py` asserts that every recorded
cassette body hashes to its index row, and one does not. A recorded body that disagrees with
its own index is either an edited transcript or a stale index. **It must not be closed by
rewriting the index to match the body** — that makes the check tautological and destroys the
only thing it was measuring. Owner: the agentkit domain. Red on its own subject.

**So `ci`'s red is now one real defect and three by-design custody rows.** The lint and type
debt earlier boards recorded here is paid.

### 3.2 `aws-evidence` — one false positive, three red jobs, one anti-vacuity family switched off

Run [31662340980](https://github.com/Shaugato/mainline/actions/runs/31662340980). All three
jobs red on **one literal**:

```
##[error][SEC-ACCOUNT-ID] evidence/deploy/verify/aws-quota-and-cost.json:30: a bare 12-digit
run '322122547200' survives UUID/digest/decimal masking and has the shape of an AWS account
id. An account number is not a credential, and publishing one still enables cross-account
enumeration
1 failure(s) across 1 invariant(s): SEC-ACCOUNT-ID
```

`322122547200` is **Lambda's 300 GiB code-storage quota in bytes** — 300 × 1024³. It is
twelve digits long and it is not an account id.

**The expensive consequence** is the third job, *the red half is red for the reason it
claims*:

```
FAMILY red-for-the-wrong-reason: an unmutated copy of evidence/ already fails, so every
plant below would be red for a reason that is not its plant
```

**A false positive has switched off a whole anti-vacuity family.** The lane that exists to
prove *"the red half is red for the reason it claims"* cannot plant a single defect. So this
lane's red is real, **and its anti-vacuity claim is currently asserting nothing** — two
separate facts, both true.

**What turns it green:** the scanner learning to tell a byte count from an account id, at
cause, in `scripts/aws/verify_evidence.py`. **Not** an allow-list of one literal — *a scanner
carrying an exception for one such literal would carry it for any* — and **never** by editing
`evidence/deploy/verify/aws-quota-and-cost.json`, which is a recorded measurement. Editing
evidence to please a scanner is forging evidence.

**A repair exists uncommitted and is therefore not on this board.** It has been exercised
against a clean export, never on a runner: see §5.3.

### 3.3 `nightly-differential` — red on its own harness, so it says nothing about the gate

Run [31662319746](https://github.com/Shaugato/mainline/actions/runs/31662319746). One job
green (*64 parallel merges of one subject*), **both differential jobs red**, on the same pair
of harness errors:

```
E  psycopg.OperationalError: sending prepared query failed: another command is already in
   progress
   .venv/lib/python3.13/site-packages/psycopg/cursor.py:117: OperationalError
E  hypothesis.errors.FlakyStrategyDefinition: Inconsistent data generation! Data generation
   behaved differently between test cases. Is your data generation depending on external
   state?
FAILED packages/trappoint-model/tests/test_read_committed.py::
       test_gate_agrees_with_the_oracle_at_read_committed
FAILED packages/trappoint-model/tests/test_differential.py::
       test_gate_agrees_with_the_oracle_at_serializable
```

**This is the worst red on the board and the count does not show it.** The lane's subject is
*the database gate agrees with the reference oracle, at two isolation levels*. It never got
there: a Hypothesis strategy is reading external state, and a psycopg cursor is being reused
while a command is in flight. **The comparison between gate and oracle was not made, at
either isolation level.**

**Not a flake — a defect that reproduces.** The identical pair of errors was recorded at
`06f41f8` (run 31657318276) and at `9221d0c` (run 31660134173).

**What turns it green:** a fix at the cause — a strategy that does not depend on external
state, one cursor per in-flight command. **What must not:** a retry, an `xfail`, or a
narrowed example budget. Each would leave the gate/oracle comparison exactly as unmeasured
as it is now, while painting the lane green.

---

## 4. The ten greens, and what each green does and does not mean

`boundary`, `claims`, `cloud-verify`, `console`, `judge-pack`, `mutation-ratchet`,
`release-proof`, `skills`, `submission`, `supply-chain`.

A green is worth exactly what its lane can refuse; §5 audits that. Two greens need a
sentence here first.

### 4.1 `submission` is green, and the last suppression pair in the repository was in it

Run [31662344526](https://github.com/Shaugato/mainline/actions/runs/31662344526), three jobs
green: *the submission gate can say no*, *submission readiness (report-only until D-3)*, *a
stranger can clone it, and every file names a licence*.

The step called *The machine record* used to carry `continue-on-error: true` **and** a
`|| true` on the command inside it — two independent reasons it could not fail, which means
it asserted nothing about the machine record. **Both are gone**; the repository-wide
measurement is at the top of this page.

### 4.2 `cloud-verify` is green, and it has never touched CockroachDB Cloud in CI

Run [31662358004](https://github.com/Shaugato/mainline/actions/runs/31662358004): success.
The name invites a reading the lane does not support. **Nothing in this repository has ever
run against CockroachDB Cloud in CI.** The lane verifies the artefacts and configuration a
Cloud run would need, against the local pinned node. A useful claim, and a smaller one than
the name suggests.

---

## 5. Anti-vacuity — which greens are load-bearing, which are not

A green means *"this lane can say no, and today it said yes"* only if the lane has been seen
saying no. This section carries forward the anti-vacuity verdicts this wave produced, **each
re-measured on the runs above rather than quoted from a worker's summary**, and names what
is still not falsifiable. The long form is [`docs/ci/anti-vacuity.md`](ci/anti-vacuity.md);
what follows is what survived re-measurement at `53197f5`.

### 5.1 PROVEN — the image pin is now a claim about the running server

Earlier audits found that `custody-chain.yml`, `db-schema.yml` and `db.yml` read the pin out
of `compose.yaml`, `docker run` it, then poll `SELECT 1`. **Nothing ever asked the running
server what version it was**, so the assertion could catch a pin that failed to arrive but
not a pin that was wrong when it was requested.

Closed, with its own negative control. From `db-schema` run 31662330242, job *the version
comparison bites — a neighbouring tag must fail it*, read at `9221d0c` and green again here:

```
pin-truth:   tag v26.2.5 -> server said 'CockroachDB CCL v26.2.5 (x86_64-pc-linux-gnu,
             built 2026/07/28 18:56:00, go1.25.5)' -> MATCHES the pin v26.2.5
pin-control: tag v26.2.4 -> server said 'CockroachDB CCL v26.2.4 (x86_64-pc-linux-gnu,
             built 2026/07/14 16:50:57, go1.25.5)' -> does not match the pin v26.2.5
the comparison bites: v26.2.5 accepted and v26.2.4 rejected by the same pattern, in the
same step, against two nodes that both answered SQL
```

**Two nodes, one comparison, opposite verdicts, in one step.** That is a claim, not a poll.
The same job is green in `custody-chain` run 31662333865.

### 5.2 PROVEN — `judge-pack`'s envelope step grew teeth, and this page had it as UNPROVEN one board ago

**This row moved between the discarded board and this one, and the movement is the honest
part.** At `9221d0c` the envelope step was measured as **unproven**: `judge-pack`'s run had
four jobs, the `green` job ran `cli.py envelope` with no flag, printed eleven `ok`s and
exited 0, and no input was known that could make it exit non-zero.

At `53197f5` the same lane has **five** jobs, and the fifth is *the envelope step goes red
for each row it prints*. From run 31662365372, verbatim:

```
unmutated copy: exit 0
  plant: envelope.py REQUEST_TIMEOUT_SECONDS 20 -> 25   -> exit 1, names
         request_timeout_seconds/DISAGREES: True
  plant: envelope.py MAX_RESPONSE_BYTES 10240 -> 10241  -> exit 1, names
         MAX_RESPONSE_BYTES/DISAGREEMENT: True
  plant: QUESTIONS.yaml Q10 EXPLAIN padded past the 16384 cap -> exit 1, names
         Q10/DOES NOT FIT: True
  plant: QUESTIONS.yaml select_page_rows 25 -> 50       -> exit 1, names
         select_page_rows/DISAGREES: True
  plant: both judge-side files move to 10241 together   -> exit 1, names
         MAX_RESPONSE_BYTES/DISAGREEMENT: True

5 plants: an unmutated copy is green, every plant is red, and every red names the row its
plant targets.
working tree clean — every plant lived in a temporary copy
```

**Five plants, five reds, each naming the row it targets, and the control green.** That is a
claim.

**Two limits, kept from the audit that produced it and re-checked here.** The lane's `green`
job still invokes `cli.py envelope` **without** `--require-cross-check`
(`.github/workflows/judge-pack.yml:449`); only the teeth job passes the flag
(`:249`, `:256`). And `validate --strict` still tolerates an absent cross-check — it prints
`NOT RUN` and adds no warning. So **every `judge-pack` green recorded on this repository
before the teeth landed carries `cross-check: NOT RUN`**, and any claim that the judge pack's
limits were confirmed against a second implementation *in CI* is false for all of them.

### 5.3 BLOCKED — the mutation family, and what "proven against an export" is worth

`aws-evidence`'s *"the red half is red for the reason it claims"* aborts before it plants
anything (§3.2). The family has been exercised against a **clean export carrying the
uncommitted scanner fix**, not against `master`, so:

* **the blast-radius step has never executed on a runner**;
* **sixteen `aws-evidence` invariants have no plant at all** and are carried on a written
  exemption list in `self_test` — named rather than hidden, which is the right shape, but a
  named exemption is still an unexercised check;
* **the blast-radius declaration is a measurement, not a derivation.** It records what each
  plant fires today; it cannot say whether a sibling *should* fire, only that the set stopped
  matching what a reviewer wrote down.

Blocked, named, not counted as proven.

### 5.4 UNPROVEN — `nightly-differential`'s gate/oracle comparison

Recorded here as well as in §3.3, because colour and vacuity have different answers. The lane
is **red**, so no reader is misled by a green. But its subject — *the gate agrees with the
oracle* — **was not measured at either isolation level**, and has not been across three
commits. A red lane and an unmeasured claim are different findings; this page keeps them
apart.

### 5.5 Greens whose refusal capability was checked, and how far

| lane | the standing job whose subject is "this lane can say no" | run | how far this page checked |
|---|---|---|---|
| `db-schema` | *the version comparison bites — a neighbouring tag must fail it* | 31662330242 | **log read** (§5.1) |
| `judge-pack` | *the envelope step goes red for each row it prints* | 31662365372 | **log read** (§5.2) |
| `custody-chain` | *the version comparison bites — a neighbouring tag must fail it* | 31662333865 | conclusion only |
| `judge-pack` | *the validator fires on every planted violation*; *a run with no cluster exits 3, never 0*; *the red half is red for the reason it claims* | 31662365372 | conclusion only |
| `submission` | *the submission gate can say no* | 31662344526 | conclusion only |
| `ci` | *RED BY DESIGN, and it must stay red* — an inverted job that fails if a declared red goes green | 31662323414 | conclusion only |

**The last column is not decoration.** Two rows were checked by reading what the job printed;
four by reading the conclusion of a job whose *name* claims a refusal. The four are weaker
evidence and are labelled rather than promoted.

### 5.6 What this section does not claim

It does not claim the remaining greens are vacuous. It claims they were **not audited on this
board** — a different sentence, and the honest one. `boundary`, `claims`, `cloud-verify`,
`console`, `mutation-ratchet`, `release-proof`, `skills` and `supply-chain` each passed;
whether each can be made to fail was not re-established here.

---

## 6. Claims on earlier boards that did not survive re-measurement

Each was true when written and is false at `53197f5`.

### 6.1 "`custody-chain` — the canonicaliser has drifted from its pin" → **repaired**

On the runner, in run 31662333865: `16 checks | 9 passed | 0 failed | 7 not checked`, with
check 10 `PASS`. On this workstation, twice over:

```
$ sha256(packages/trappoint-jcs/src/trappoint_jcs/canon_v1.py)
  260ed37ddc610f1fb94ddce98998fe4ae5ce883698ad5c7033839cd258dcd659   = the registry pin
$ python scripts/custody/check_vendored_canon.py
  canonicaliser registry: 3 passed, 0 failed, 0 skipped
```

The cause was a machine formatting sweep that added four blank lines to each shipped
canonicaliser; the repair restored the bytes **and** excluded both files from `ruff format`.
[`docs/HONESTY.md`](HONESTY.md) carries the full account, including the residual gap: the
exclude is not `force-exclude`, so a path named explicitly on a command line is still
formatted.

### 6.2 "`db` is red because `restated literal rose from 19 to 20`" → **paid**

`restated literal: 18 (ceiling 19)`, `floating tag: 0 (ceiling 0)` (§2.2).

### 6.3 "`db-schema` is red on a DM-9 violation" → **paid; a different red is left**

`mi-red` refuses on MI06, MI10, MI21, MI22, MI27 (§2.5).

### 6.4 "`ci` is red on `ruff`, `mypy`, `pytest` and the summary" → **`ruff` and `mypy` green**

Ten of twelve jobs green; `pytest` down from five failures to four, and three of the four are
by-design custody rows (§3.1).

### 6.5 "`judge-pack`'s envelope step cannot be shown to fail" → **it can, five ways** (§5.2)

### 6.6 "`ruff format --check` reports 10 unformatted on the runner" → **0**

`1443 files already formatted` on an LF export of `53197f5`, and the runner's `ruff format`
job is green.

### 6.7 Two claims that survived, and are listed because they were expected to move

* **`nightly-differential` is red on its own test harness.** Unchanged across three commits
  (§3.3).
* **`aws-evidence` is red on `SEC-ACCOUNT-ID`.** Unchanged; the fix is uncommitted (§3.2).

### 6.8 A claim this page made about itself, and then caught

An earlier draft of §2.5 said `mi-red` had narrowed from five refusals to two. **False**, and
the cause was this author's own `tail -25` truncating a five-line list. Corrected against
three runs. Recorded because the mechanism that caught it — re-running the command instead of
trusting the note — is the only mechanism this page has.

---

## 7. The row a dispatch cannot produce: `ci`'s PL-2 red on a push

PL-2 is push-gated (§1.1, §2.6), so this row comes from the **push** run created by the
commit that published this document.

* **run:** [31664015447](https://github.com/Shaugato/mainline/actions/runs/31664015447) —
  `ci`, event `push`, ref `refs/heads/master`, head `52fb799` (the commit that published
  the revision of this document you are reading)
* **job:** `PL-2 — the red run is recorded` — **failure**
* **cause, quoted from the job log, read warm:**

```
##[error]RED BY DESIGN, NOT A CI DEFECT. This job asks for the URL of a db run in which the
CONFORMANCE step itself went red. No such run exists, because CONFORMANCE has never
executed: db.yml stops one step earlier, at 0058_blocking_check on the missing
trappoint_ref.event. Recording any other red db run would put a URL in a field that asks
for a different observation, which is the precise laundering the field was created to
prevent, so it stays UNRECORDED and this job stays red. WHAT TURNS IT GREEN: the producer
for trappoint_ref.event lands, the next db push-run on master reaches CONFORMANCE, that
step is red, and THAT run's URL replaces the word UNRECORDED in
docs/adr/0005-red-before-green.md. WHAT DOES NOT: any other red db run, deleting the line,
or relaxing this check.
PL-2: the db lane's red conform run URL is still UNRECORDED.
MISSING ARTEFACT: a producer for 'trappoint_ref.event' in
OWNER: the KERNEL domain — docs/leads/kernel.md 1.1. Recorded in
CONSEQUENCE: db.yml's 'Apply the reference vertical' step fails, so its
WHAT FILLS THIS FIELD: the producer lands, the next db run on master reaches
WHAT DOES NOT: any other red db run. The field names one observation, not a colour.
##[error]Process completed with exit code 1.
```

**How this row was obtained, because `gh run view --log-failed` does not return it.** While
the rest of the run was still `in_progress`, the run-level log bundle was not yet
assembled; the job log was fetched directly:

```bash
gh api "repos/Shaugato/mainline/actions/runs/31664015447/jobs?per_page=100"   --jq '.jobs[] | select(.name|startswith("PL-2")) | .id'      # → 94334650682
gh api "repos/Shaugato/mainline/actions/jobs/94334650682/logs"
```

**Every other job in that push run agrees with the dispatched board, checked to
completion**: `actionlint`, `ruff format`, `mypy`, `import-linter`, `REUSE`, the lockfile,
the sequence ban, `every checker this lane invokes exists` and
`RED BY DESIGN, and it must stay red` all green; `pytest --crdb=none` and `CI summary` red,
the same two as run 31662323414 in §3.1. **PL-2 is the one job the dispatch could not
reach**, and on a push it is red, by design, with the reason in the annotation — so `ci` is
red on a push for **three** jobs rather than two, and the third is deliberate.

**Consequence for the board.** `ci` is red on a push for one more reason than on a dispatch,
and that reason is by design. It does not change §1: `ci` is red either way.

---

## 8. What this page did not achieve

* **One CI-TRUTH worker did not land**, so one red this page records was expected to be paid
  and is not: `aws-evidence` (§3.2). Its repair sits uncommitted. **Uncommitted is red.**
* **`db.yml`'s red does not say "by design" in its own message.** Three workflows were in
  scope for that change; `db.yml` was not, and its reader still has to come here.
* **`db`'s census asks for a ceiling to come down to 18** and this page did not do it,
  because changing an assertion is not a documentation task.
* **`nightly-differential` has not compared the gate to the oracle across three commits**
  (§3.3, §5.4). It is red, so nobody is misled — but the claim the lane exists to make is
  unmeasured, and no worker in this wave owned it.
* **A new defect was found and not fixed:** `test_every_recorded_body_hashes_to_its_index_row`
  (§3.1), recorded with both hashes and left to the owning domain, because a recorded body
  that disagrees with its index must be diagnosed, not reconciled by rewriting one side.
* **Eight greens were not audited for vacuity** (§5.6).
* **One cross-reference into this page is now stale and belongs to another owner.**
  `.github/workflows/custody-chain.yml:693` cites "`docs/CI-STATE.md` 3.1" for the
  seven-unimplemented-checks finding, which is §2.4 in this revision. The equivalent
  reference in `ci.yml` was rewritten to cite the owning **domain document** instead of a
  section number, for the reason the new text gives: this page is re-derived from a fresh
  measurement every time the board moves, so a section number embedded in a workflow is a
  cross-reference that rots silently. `custody-chain.yml` is not this worker's file;
  reported, not edited.
* **No lane's Cloud half has ever run in CI** (§4.2). Unchanged, and stated again so it is
  not read out of the ten greens.
