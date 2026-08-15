<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# PROOF AND POLISH — make the demo survive contact with a judge

**Lead:** proof-and-polish (PROOF LEAD). **Date:** 2026-08-15. **Workers:** 7.
**Tree:** `D:/CoackroachDBxAWS/mainline`, branch `master`, HEAD `4af05e1`.
**Target:** `https://ihuuyvm4z6nfuktihnkey77fpy0eyrhj.lambda-url.ap-southeast-1.on.aws`

The operator-UI leads are building the two screens the film is shot on. This lead builds
everything that has to be **true underneath them**: a starting state a retake can return to
in seconds, a transcript that proves every beat came off the live URL, a claim table that
survives a judge with the repo open, and a guard that stops this wave from breaking the 987
things that already pass.

The single hardest number in this document is at §0.3: **the console entry chunk may grow by
63 bytes.** Two new screens are being written into a bundle with 63 bytes of room. If that is
crossed, the deployed origin answers `413` to its own entry JavaScript and a judge gets a
blank page — a total demo outage with no warning from production, because the shell keeps
answering `200`.

---

## 0 · The baseline, measured by this lead on 2026-08-15

Nothing in this section is quoted from a document. Every number came out of a command run in
this sitting against the working tree or the live URL.

### 0.1 The live URL answers

```
GET https://ihuuyvm4z6nfuktihnkey77fpy0eyrhj.lambda-url.ap-southeast-1.on.aws/v1/health
{ "ok": true,
  "database": "mainline_demo",
  "deploy_chain_applied": 271, "deploy_chain_files": 271,
  "migrations_applied": 0,
  "cluster_version": "CockroachDB CCL v26.2.5 (…built 2026/07/28…)",
  "schema_fingerprint": "ec9b1ce70a8df066e5763056c5ad9376800ef5df9362f7d0502b1dc7e7450339",
  "seconds": 0.0393, "server_date": "2026-08-15T10:52:59.712684Z" }
```

### 0.2 The suite baseline

`qa/final6.xml` root element, written `2026-08-15T18:09:01+10:00`:

```
tests="988"  failures="0"  errors="0"  skipped="1"   time="205.555"
```

**988 collected / 987 passed / 0 failed / 0 errors / 1 skipped.** The one skip is
`test_gate_run.py::test_payload_validates_against_the_json_schema` — *jsonschema is not a
workspace dependency*. Argv is the two suites `verticals/mainline/apps/demo-api/tests` and
`tests/deploy` under `--crdb=reuse`, which is what `scripts/qa/regression_guard.py`'s
`SUITE_PATHS` names.

**And `SUITE_BASELINE` in that guard is stale.** It reads
`{"collected": 911, "passed": 910, "failed": 0, "errors": 0, "skipped": 1}` at
`scripts/qa/regression_guard.py:191`, measured earlier the same day (`qa/final5.xml`,
`tests="911"`). The tree has gained 77 tests since. A guard whose baseline is 77 below the
truth cannot see 77 tests disappear. §R6 rules on what may be done about that.

### 0.3 The console bundle, and the 63 bytes

Measured by reading the central directory of `out/lambda/mainline-demo-api-arm64.zip` —
**the archive, never `console/dist`**, because only the archive carries the `.gz` siblings the
origin actually serves:

| | bytes | source |
|---|---|---|
| largest served wire object | **138,177** | `web/assets/index-LoN3Sn_L.js.gz` |
| second largest | 18,263 | `web/assets/surface-BD2Wh4U2.js.gz` |
| `DEFAULT_MAX_RESPONSE_BYTES` | **139,264** | `136 * 1024`, `static_site.py` |
| headroom today | **1,087** | 0.78 % of the ceiling |
| `_MINIMUM_HEADROOM_BYTES` | **1,024** | a BOUND; CI goes red below it |
| **growth this wave may spend** | **63** | 1,087 − 1,024 |

The second-largest object is 18 KB. **There is no bundle problem — there is an *entry chunk*
problem.** A lazy chunk or a second HTML entry has 120 KB of room; the shared
`assets/index-*.js` has 63 bytes.

And `budgets.json` will not catch it: the `evidentiary-shell` budget is `225,280` gzip bytes,
**87 KB looser than the wire ceiling that actually governs**. It would pass a build that takes
the demo dark. §R3 and worker **P5** close that.

### 0.4 What already exists, so nobody rebuilds it

| I need | It is already here |
|---|---|
| seed the cloud world, idempotently | `scripts/deploy/seed_demo.py` (`--check` = verify only) |
| seed a local camera database | `scripts/submission/seed_demo_state.py` (`--verify-only`) |
| drive the live URL as a stranger | `scripts/deploy/demo_acceptance.py --phase2` |
| walk every request the artefact declares | `scripts/deploy/judge_walk.py` |
| re-verify every claim in the repo | `scripts/qa/regression_guard.py` (31 checks, 6 families) |
| ban a sentence we may not say | `scripts/demo/claim_hygiene.py` |
| the AWS / CockroachDB census | `evidence/tool-usage/{aws-services,crdb-features}.json` |
| the judge's own walk-up | `docs/deploy/JUDGE-PACK.md` (1,025 lines), `README.md` |

**The gap is not tooling. It is composition, currency and evidence**: no single command
answers *"is the world ready to film?"*; no transcript proves the four beats and the memory
loop came off the live URL in one sitting; the AWS census still says `aws_lambda: DESIGNED`
while a Lambda is answering `ok:true`; and `budgets.json` cannot see the cliff at §0.3.

### 0.5 The four beats, and the memory loop, as routes that already exist

`verticals/mainline/apps/demo-api/src/mainline_demo_api/app.py:229-252` — measured, not
recalled:

```
GET  /v1/clauses/{clause_uuid}/ancestry        STORE     the blame edge to the clause
GET  /v1/recall-runs/{run_id}                  RETRIEVE  started_at, n_candidates, n_blocking
GET  /v1/receipts/{receipt_id}                 SHOWN TO  actor_sub, issued_at, digest
GET  /v1/permits/{permit_id}/blocking-checks   ACT       the obligation that is still open
POST /v1/demo/gate-run                         the four beats, one SERIALIZABLE transaction
POST /v1/permits/{permit_id}/merge             423 Locked — THE TRAP, never a refusal banner
```

---

## 1 · RULINGS

Each names its authority. Where the authority is a measurement, the measurement is in §0.

### R1 — The demo needs no reset. `demo-ready` is a verifier first and a repairer second.

**Authority:** `docs/deploy/gate-run-contract.md` §2 — the whole gate-run transaction ends in
`ROLLBACK`, beat 4 included; and `docs/deploy/cloud-database.md` §6 — *"No per-visitor state,
no reset button, no cleanup sweeper,"* with `after_rollback` reading state `dispositioned`,
`open_blocking` still `1`, zero merge records.

**Ruling.** A retake costs one HTTP call because the previous take changed nothing. The
one-command starting state is therefore **`--check` by default, read-only, zero writes**, and
its job is to answer *"may I roll camera?"* in under ten seconds. Repair is the exception path,
not the happy path. Anyone who builds a "reset the demo" button has misread the product: the
absence of one is a claim we make.

### R2 — No worker in this wave writes to the cloud database, and none touches AWS.

**Authority:** the task's absolute prohibitions, and *"the orchestrator deploys."*

**Ruling.** `demo_ready --repair` is implemented and tested **against a local database only**.
Pointed at `mainline_demo` it refuses to write, prints the exact command the orchestrator
would run (`.venv/Scripts/python.exe scripts/deploy/seed_demo.py`), and exits **3 = ACTION
REQUIRED** — distinct from 1 (wrong state) and 2 (usage), so *"a human must act"* is never read
as *"the gate did not refuse."* No `terraform` verb, no `aws` client, no SSM write, no
credential printed, by anyone, for any reason.

### R3 — The entry chunk may grow by 63 bytes, and the fix when it goes red is a smaller chunk.

**Authority:** measured in §0.3 at HEAD `4af05e1`; `_MINIMUM_HEADROOM_BYTES` and its comment in
`verticals/mainline/apps/demo-api/tests/test_static_site.py:958-992`.

**Ruling.** `DEFAULT_MAX_RESPONSE_BYTES` and `_MINIMUM_HEADROOM_BYTES` **may not move**, in
either direction, by anyone in this wave. The operator screens must be a **lazy route or a
second HTML entry**, never statically reachable from `main.tsx`'s import closure — and that is
enforced by a budget, not by a convention. `_LARGEST_SERVED_WIRE_BYTES` **is** a measurement and
is re-recorded from a fresh archive, which is the one number in that file that is allowed to
move. Raising the ceiling to make the arithmetic agree is the exact violation
`scripts/qa/regression_guard.py`'s BOUNDS family exists to catch.

### R4 — Against the live URL: every `GET`, and `POST /v1/demo/gate-run`. Nothing else.

**Authority:** `docs/deploy/gate-run-contract.md` §7 — the demo subject is write-protected and
a mutating transition answers `423 Locked` naming `POST /v1/demo/gate-run` instead; independently
found by researchers r3 and r4.

**Ruling.** `POST /v1/permits/{id}/merge` on the seeded subject is **recorded as a documented
trap** in the transcript — status, body, `use_instead` — precisely so that no screen ever wires
an ISSUE button to it. A `423` in a refusal banner is a fabricated exhibit in front of a judge.
The transcript records it once, labelled, and the screens read the label.

### R5 — DESIGNED → EXERCISED requires a committed evidence file that already exists on disk.

**Authority:** R2, plus this repository's standing discipline that a verdict carries its basis
(`evidence/tool-usage/README.md`, `docs/HONESTY.md`).

**Ruling.** No worker calls an AWS API to earn a promotion. If `evidence/deploy/LIVE.md`,
`aws-live.json`, `live-health.json`, `lambda-bundle.json` or the Terraform plan artefacts
already prove the service ran, the row is promoted and the promotion **names the file**. If they
do not, the row **stays DESIGNED** and the gap is written down. A row promoted on a memory of a
deploy is worse than a row left honest.

### R6 — Baselines are re-recorded upward with a reason, never downward.

**Authority:** `docs/regression/GUARD.md` — *"A guard nobody has falsified is decoration"*; and
its own record of a run that printed no summary line while the XML on disk carried
`tests="579" failures="8"`.

**Ruling.** `SUITE_BASELINE` moves `911 → the measured figure` with the date, the argv and the
sentence *why it rose* (tests were added; §0.2). A count that **falls** is a regression and stops
the wave — it is never re-recorded down to make a run green. Counts come from the `--junitxml`
**root element** and never from a terminal tail (R10 below is the same rule stated for anyone who
skims).

### R7 — The memory loop needs no new endpoint, and may not be composed client-side.

**Authority:** the route table at `app.py:229-252`, read in this sitting (§0.5).

**Ruling.** STORE, RETRIEVE and ACT are each already a live `GET`. Nobody adds a route to make
the loop filmable, and nobody assembles the loop in TypeScript from constants — every value on
screen arrives in an HTTP response body. `n_candidates 1 / n_blocking 1 / 0 silenced` and the
**ten seconds** between `recall_run.started_at` and the obligation's materialisation are the
loop; they are columns, and they are fetched.

### R8 — The incident is 2019-03-14, and nothing was rewritten.

**Authority:** r4's measurement of `verticals/mainline/db/seeds/demo/demo_world.sql:272` and
`:226-250`; `docs/decisions/demo-use-cases.md` §1.3/§1.4.

**Ruling.** Exactly one `clause_version` exists, `gen 1`, `control_delta introduce`.
`DEMO-MOC-0001` **proposes** an edit and is unmerged; `POST /v1/change-requests/{cr_id}/merge`
is `404`. Any artefact this wave produces that says "2024", or that says the clause *was*
rewritten, is wrong and is fixed at the artefact.

### R9 — Severity 4 / `blood_major` is projected. Every artefact that prints it prints where it came from.

**Authority:** `docs/deploy/cloud-database.md` §5 — the seed supplies `0` / `routine`, and
`fn_check_project` overwrites both from `mainline.clause_blame_current` under invariant MI25.

**Ruling.** *"Nobody typed the four"* is one of the strongest sentences we own and it is only
true because the projection ran. Wherever `4` or `blood_major` appears in a transcript, a
judge-pack table or an on-screen claim, the projector is named beside it. A `4` with no
provenance is a number somebody could have typed.

### R10 — A test count comes from the JUnit root element. Never from a summary line.

**Authority:** `docs/regression/GUARD.md`, which records the disagreement first-hand.

### R11 — Underclaiming is an accuracy failure, and there is one on the page today.

**Authority:** `docs/submission/DEVPOST.md:118, 173, 274` says *"nothing is deployed"*, *"no
judge can visit any of it"*, *"there is no deployed URL"*, and carries an acceptance verdict of
`NOT PROVEN` against `http://127.0.0.1:8764` with `target_is_local_emulator: true`. Measured by
this lead at `2026-08-15T10:52:59Z`, `GET /v1/health` on the public Function URL answers
`ok: true`, `deploy_chain 271/271`.

**Ruling.** A judge who watches a live refusal and then reads the repository saying the thing is
not deployed finds the repo contradicting the film — which is the *Functionality* rule's failure
mode approached from the other side. The stale sentences are corrected **to what is measured, and
to nothing more**. Not one concession, gap, red count or caveat elsewhere on that page is
softened, deleted or rounded while the correction is made. The five gaps stay. The custody
`7 of 16` stays. The CloudFront `AccessDenied` stays, verbatim, with its RequestID.

---

## 2 · THE SEVEN WORKERS

Disjoint, literally enumerated paths. **No worker edits a path owned by another.** Where a
worker needs a fact from a file it does not own, it reads it and cites it.

| id | title | owns |
|---|---|---|
| **P1** | One command back to demo-ready | `scripts/demo/demo_ready.py`, `docs/demo/DEMO-READY.md`, `tests/demo/test_demo_ready.py` |
| **P2** | The four beats, proven on the live URL | `scripts/proof/live_beats.py`, `evidence/demo/live-beats.json`, `docs/demo/LIVE-BEATS.md` |
| **P3** | STORE → RETRIEVE → ACT, as an artefact | `scripts/proof/memory_loop.py`, `evidence/demo/memory-loop.json`, `docs/demo/MEMORY-LOOP.md` |
| **P4** | The regression surface, before and after | `scripts/qa/regression_guard.py`, `qa/wave-before.xml`, `qa/wave-after.xml`, `docs/regression/WAVE-PROOF.md` |
| **P5** | The 63 bytes | `verticals/mainline/apps/console/budgets.json`, `…/console/scripts/check-budgets.ts`, `verticals/mainline/apps/demo-api/tests/test_static_site.py`, `qa/bundle-headroom.json`, `docs/deploy/console-headroom.md` |
| **P6** | Every service named on screen | `evidence/tool-usage/aws-services.json`, `evidence/tool-usage/crdb-features.json`, `scripts/submission/capture_tool_evidence.py`, `docs/TOOL-USAGE.md`, `docs/demo/ON-SCREEN-CLAIMS.md`, `docs/submission/DEVPOST.md` |
| **P7** | The repo backs up the video | `README.md`, `docs/deploy/JUDGE-PACK.md`, `docs/submission/JUDGE-START.md`, `docs/submission/JUDGING-AXES.md`, `docs/demo/JUDGE-90-SECONDS.md` |

### Sequencing

**P4 runs twice and brackets the wave.** Its `qa/wave-before.xml` is taken at HEAD `4af05e1`
before any other worker edits a file; its `qa/wave-after.xml` is taken last, after every other
worker including the operator-UI leads has landed. **P5 also brackets the wave**: it records the
entry-chunk figure now, and re-measures after the screens land. P1, P2, P3, P6 and P7 are
independent of each other and may run concurrently. P7 reads P1/P2/P3's outputs and is therefore
finished after them.

---

## 3 · WHAT EVERY WORKER IS BOUND BY

Reproduced in every brief, because a rule that lives only in the lead's plan is a rule a worker
never read:

1. **NEVER fake a refusal, a latency, a SQLSTATE, a row or a seal.** Every number in an artefact
   is one the kernel or the deployment produced, in this sitting, and the artefact says which
   command produced it. Reshaping a value to match a constant is the offence this repository has
   already reverted a worker for.
2. **NEVER `terraform apply`, redeploy, touch AWS, write an SSM parameter, or print a
   credential.** The orchestrator deploys. Read-only `GET`s to the public demo URL and
   `POST /v1/demo/gate-run` are permitted (R4); nothing else on the wire is.
3. **Do not commit.** Leave the tree for the orchestrator.
4. **Do not break what works.** 988 / 987 / 0 / 0 / 1 is the floor. `DEFAULT_MAX_RESPONSE_BYTES`
   is `136 * 1024` and may not move. `continue-on-error` and `|| true` are banned. Do not weaken
   `docs/HONESTY.md`, `docs/CI-STATE.md`, a ratchet or an assertion.
5. **A skip is not a pass, and a `SKIP` that reads like a `PASS` is the failure mode this
   repository has already had.** Print the reason, count it separately, refuse the word GREEN.
6. Python is `D:/CoackroachDBxAWS/mainline/.venv/Scripts/python.exe`. **`uv` is not on PATH.**
   Paths in output are absolute.

---

## 4 · DONE, FOR THIS LEAD

* One command answers *may I roll camera?* against local and against the deployment, twice in a
  row, with byte-identical verdicts (P1).
* One transcript, generated in one sitting, carries the four beats with the SQLSTATE the
  database produced and the `elapsed_ms` the payload reported — and carries the `423` trap
  labelled as a trap (P2).
* One artefact renders STORE / RETRIEVE / ACT with a table, a column and a timestamp behind each
  of the three words, and the ten-second gap on its face (P3).
* `wave-before.xml` and `wave-after.xml` both parse, both come from the root element, and after
  is ≥ before with every delta named (P4).
* The console entry chunk is measured, budgeted below the wire ceiling, and the operator screens
  are proven lazy (P5).
* Every service and feature that may appear in the last minute of the film has a row with a
  verdict, a file and an evidence path — and no row was promoted on a memory (P6).
* A judge who pauses the film on any number finds that number in the repository in under ninety
  seconds (P7).
