<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# STATE OF THE BUILD

**Re-certified 2026-08-14 by the FIFTH re-verification agent**, against local `HEAD`
`9cdebc7` **plus 51 modified and 42 untracked paths that have never been committed**, and
against `origin/master` `1a6e10a`, which is **three commits behind local HEAD**. Deadline
2026-08-18.

Four prior verifications returned NO-GO and each was right. This one was instructed to
assume the wave failed until it proved otherwise. Every number below came from a command
this agent ran on this machine today; suite totals are read from `--junitxml` root
elements and from nowhere else.

The paragraph a reader in a hurry needs:

> **The engineering succeeded and the repository did not receive it.** The shortcut check
> passes — with a stronger proof than any previous wave produced, because one test was
> deliberately left FAILING where the evidence sided against the seed. The demo-api suite
> is now **527 passed / 1 failed / 0 errors** against a real CockroachDB, down from
> 453 / 7 / 63, and it returns the **identical** result under four randomised orders with
> a real shuffler. Beat 4 is `PROVEN`, the gate proof is `PROVEN` and caveat-free, the
> cost residual is quantified in dollars, and the Terraform plan now reproduces locally
> with zero mutating AWS calls. **And none of it is committed.** The cluster lane — the
> instrument built to catch exactly this — ran at the pushed head and failed in 29 seconds
> with five collection errors, because `credentials.py`, `logbudget.py` and
> `ratelimit.py` exist only in this working tree. `infra/modules/cost-guard/` is likewise
> untracked while `infra/envs/demo/main.tf` instantiates it, so a fresh clone cannot even
> `terraform init`. **This is a NO-GO for the fifth time, on one cause rather than many:
> the build that works is not the build that is published.**

---

## 0 · The five GO conditions, scored

| condition | verdict | evidence |
|---|---|---|
| No shortcut taken | **PASS** | §1 |
| Suite green in any order against a real cluster | **FAIL** | green locally in 4 orders (§2); **does not collect** in the cluster lane (§3) |
| Cluster lane running AND falsified | **FAIL** | running and red; the 2×2 control has never completed one cell (§3) |
| Beat 4 `PROVEN` | **PASS** | §4 |
| Cost residual quantified | **PASS** | §5 |

Three of five. The two that fail are the same fact seen twice.

---

## 1 · The shortcut check — PASSED, and this is the strongest such proof yet

This came first because everything else is worthless if the suite was bent to fit. The
wave moved **six test assertions toward the seed** — the exact direction the no-shortcut
rule exists to police. It is not a shortcut, and the reason is that a **seventh was left
failing** where the same method pointed the other way.

### 1.1 · The negative control for the historical incident is GREEN

The one shortcut this repository was actually caught taking was enrolling a DERIVED
credential id in `demo_world.sql` so the seed matched the code. Re-checked directly:

```
tests/ci/test_demo_seed_is_frozen.py::test_the_seed_derives_the_demo_credentials_from_their_names   PASSED
sha256(b"credsigner") = 487adc50409e8811b1f12055ee183ce9d8548f11262807d01776fb67cd09c765
grep -rn 487adc50409e8811 verticals/mainline/db/seeds/   ->  NOT PRESENT in any seed
demo_world.sql:124   digest('mainline-demo/credential/demo.signer', 'sha256')
demo_world.sql:132   digest('mainline-demo/credential/demo.countersigner', 'sha256')
```

The enrolment is still the name-derived expression. The derived constant appears in no
seed file.

### 1.2 · The six assertions that moved, and the artefact that decided each

`docs/decisions/demo-clause-version-singleton.md` records these. The method is correct and
was applied rather than asserted: in every case the tiebreaker is a **third artefact** —
the console a judge drives, a committed JSON Schema, or the migration that defines the
table — which is a party to neither side of the dispute.

| assertion | was | is | third artefact that decided it |
|---|---|---|---|
| `clause_version` addressing | `seed["commit_v2"]` | `seed["commit_id"]` | `console/.../useGateData.ts:193` builds `commit_id: subjectCheck?.commit_id`; zero hits for `clause-v2` anywhere in `console/` |
| permit state / counter | `'draft'`, `0` | `'dispositioned'`, `1` | `demo_permit.sql` header + migration 0011's state alphabet |
| check openness | `open False`, a `disposition_id`, `INC-W3-1` | `open True`, `None`, `DEMO-INC-0001` | `disposition = NO ROWS` by design — signing **is** beat 4 |
| ancestry | `commit_chain [1, 2]` | `[1]` | same single-version ruling |
| silence flags | `s 2`, `n 4` | `s 1`, `n 1` | `s == n` is `boundaryAtEnd`; an empty ledger is *required* for coherence |
| audit surface | 1 call | `[]` | the only INSERT into `mainline_meas.agent_action` in this tree is in a *test* |

`git log -S commit_v2` puts every one of these values inside the **old** conftest at
`5ddaa3a`, which built a parallel world the fixture rewrite deleted. A value inherited from
a deleted fixture is derived. That is the finding, and it is checkable.

### 1.3 · The seventh, left failing on purpose — this is what makes §1.2 credible

`test_the_disposition_carries_the_lattice_and_the_projected_requirements` **still fails,
and its failing assertion is byte-for-byte intact.** `mainline.defeater_option` holds zero
rows. Here the seed is the wrong side, and again the evidence is outside both parties:
`0064_defeater_option.sql` says the vocabulary is per-check with no global fallback;
`console/src/a11y/contract.ts` declares a `defeater` step inside a path it asserts has no
pointer-only step; `types.generated.ts` declares `defeater_options` non-optional; and
**nothing in this tree writes such a row.** A judge who reaches the disposition screen
cannot choose a defeater and therefore cannot sign.

Weakening that to `== set()` would have bought a clean green. It was not taken. **A rule
that always moved the seed, or always moved the test, would not be a rule** — and this is
the only wave that has demonstrated the rule cutting both ways in the same commit.

### 1.4 · The ceiling: the shortcut wearing a lab coat was NOT taken

`DEFAULT_MAX_RESPONSE_BYTES` **did not move.** It is still `136 * 1024 = 139,264`.
`docs/decisions/response-ceiling-authoritative-tree.md` rules the **deployed** tree
authoritative over the packer's input tree, because cost is incurred by bytes leaving the
deployed origin and `build_lambda` strips `web/**/*.map` by default.

The tell that this is a ruling implemented rather than an expectation fitted to output:

* the measured input-tree refusal list has **five** entries (`index-…js` plus three maps
  plus one more); the declared list has **one**. **They differ.** Pasting the measured list
  in was the available shortcut and it is not what is in the file.
* the tiebreaker came from `test_static_site.py` §(f) — a *sibling module by a different
  wave* — which had already named this file's input-tree fallback as the mistake in
  writing.
* eleven falsifying mutations are logged, each applied, run red, and reverted.
* the document records a **disagreement with its own lead** (`cut` is 3.4916, the plan says
  3.4917) rather than silently adopting the lead's figure.

**Verdict: no shortcut found.** Nothing green in this document was obtained by moving an
authoritative value.

---

## 2 · The suite — PROVEN green locally, in four orders

Full `verticals/mainline/apps/demo-api` suite, `--crdb=reuse`, against the real local
CockroachDB CCL v26.2.5 at `127.0.0.1:26257`. Numbers from `--junitxml`.

| run | tests | passed | failed | errors | skipped | wall |
|---|---:|---:|---:|---:|---:|---:|
| brief's baseline | 523 | 453 | 7 | 63 | — | — |
| **default order (this agent)** | **528** | **527** | **1** | **0** | 1 | 40.8 s |
| `--random-order` seed 777 bucket `global` | 528 | 527 | 1 | 0 | 1 | — |
| `--random-order` seed 777 bucket `module` | 528 | 527 | 1 | 0 | 1 | — |
| `--random-order` seed 888 bucket `global` | 528 | 527 | 1 | 0 | 1 | — |
| `--random-order` seed 888 bucket `module` | 528 | 527 | 1 | 0 | 1 | — |

**The one failure is §1.3's, in every run.** The failing set is identical across all five
orders — not merely the same count, the same node id.

**The 63 errors are gone**, and they had a single cause exactly as the brief said: one
absent fixture key failing a session-scoped fixture during setup, which turned every test
in `test_reads.py` into an error and left **every assertion in that file unexecuted for
weeks behind it**. Fixing the address surfaced seven real failures; six were the archaeology
of §1.2 and one is §1.3.

**Randomised order is now a real instrument, and it is honest about what it proves.**
`pytest-random-order 1.2.0` is installed, declared in `pyproject.toml`'s `dev` group and
locked (`uv lock --check` green, 15 additive lines, lockfile `revision` unchanged). It was
chosen over `pytest-randomly` because the latter is on by default for all 9,324 collected
tests and reseeds `random`/`numpy.random` before every test, and sixteen modules here drive
Hypothesis — a run that changes both the ORDER and the DATA cannot attribute a new failure
to either. Inertness was **verified**, not assumed: two default `--collect-only` runs, one
with the plugin and one with `-p no:random_order`, produced byte-identical collections.

`docs/ci/demo-suite-random-order.md` reports 15 further randomised runs and reaches the
correct verdict rather than the convenient one: intra-process order contamination is
**NOT-OBSERVED**, not *fixed*, because the measurement host had five workers on it and the
cross-process channel was open throughout. It then *found and reproduced* the real
contaminant with a negative control — `test_gate_run.py:143` names its scratch database
with a fixed string, so simultaneous runs collide on `40001` — 3 of 4 runs red sharing a
database, 0 of 4 with one each. **That is a repository defect discovered by the instrument,
not a defect the instrument was bent around.** My four runs were taken with
`MAINLINE_W4_DATABASE` and `MAINLINE_W1_DATABASE` set to private names, i.e. with that
channel closed.

**Caveat that must not be dropped:** this is a green on ONE laptop against a single-node
local cluster. §3 is why that is not the same sentence as "the suite is green".

---

## 3 · The cluster lane — RUNNING, RED, and NOT falsified. This is the blocker.

Both lanes now exist, are committed, and executed at `origin/master` `1a6e10a`. Their real
verdicts, read warm:

### 3.1 · `cluster-tests` — FAILED in 29 s, before a single test ran

```
E   ImportError: cannot import name 'logbudget' from 'mainline_demo_api'
E   ModuleNotFoundError: No module named 'mainline_demo_api.credentials'
ERROR .../tests/test_credentials.py
ERROR .../tests/test_demo_guard_anonymous.py
ERROR .../tests/test_response_contract.py
ERROR .../tests/test_row_factory_contract.py
ERROR .../tests/test_transitions.py
!!! Interrupted: 5 errors during collection !!!
207 tests collected, 5 errors in 1.63s
```

The lane's own error text diagnosed it precisely: *"most often a module the committed tests
import that was itself left uncommitted — and it is answered by landing what is missing."*
`credentials.py`, `logbudget.py` and `ratelimit.py` are `??` in `git status`. **The lane is
working. The tree is not.**

The 527/528 in §2 is therefore a measurement of a working tree that exists on one machine.
On the published repository the suite collects 207 of 528 tests and stops.

### 3.2 · `cluster-lane-bites` — FAILED at its own precondition; the 2×2 has never run a cell

The bites lane never reached its matrix. It failed at *"The frozen-seed guard is GREEN
again"*:

```
demo_world.sql has changed: it hashes 80adc33a…, and this test records 50535d1d…
```

That guard is right and its message is right — *"THIS IS A QUESTION, NOT A VERDICT … replace
the hash IN THE SAME COMMIT as the seed change."* The seed change is uncommitted, so the
re-baseline cannot have happened in the same commit. Locally the worktree seed hashes
`e2aa9706…`, a third value, so there are two outstanding re-baselines, not one.

**Consequence, stated plainly: the 2×2 control has never produced a discrimination.**
Nobody has yet observed plant-present/hermetic passing the same count as plant-absent, which
is the assertion that proves the hermetic lane could not have seen the plant. Until one
green matrix exists, `cluster-tests.yml`'s claim that its properties are *"exercised by
controls"* remains **unproven for the lane itself**.

### 3.3 · `cluster_lane_report.py` — controls now EXIST, and they pass

Blocker 3 is answered in the working tree: `tests/ci/test_cluster_lane_report.py` and
`tests/ci/test_plant_cluster_defect.py` give **137 passing controls**, including planted-red
and vacuity cases. **Both files are untracked**, so on the published repository the report
still has zero controls and `cluster-tests.yml`'s sentence is still false there.

### 3.4 · CI at the pushed head — 2 green of 6

| lane | result | classification |
|---|---|---|
| `aws-evidence` | green | — |
| `submission` | green | — |
| `cluster-tests` | red | **regression** — uncommitted source modules (§3.1) |
| `cluster-lane-bites` | red | **fixable** — frozen-seed re-baseline owed (§3.2) |
| `ci` | red | two jobs: PL-2 *RED BY DESIGN* (**intentional and precise** — awaits a `trappoint_ref.event` producer, and refuses to launder any other red run's URL); *checker registry* missing `skip_ratchet.py` and `check_pytest_lanes.py` (**fixable — both are in unpushed commit `3192c2e`**) |
| `schema` | red | `ANOMALY_COVERAGE.md` stale (**fixable**); unwelding matrix *RED BY DESIGN (COLLATERAL)* (**intentional and precise**) |

Local `9cdebc7` is three commits ahead of `origin/master`. **CI has never seen the cost
model, the QA checkers, or the regenerated plan artefacts.**

---

## 4 · Beat 4 — PROVEN, re-run today

`scripts/proof/gate_refusal.py` against a database built by applying the 271-file migration
chain plus `demo_world.sql` and `demo_permit.sql`. Verbatim:

```
cluster       CockroachDB CCL v26.2.5 (x86_64-pc-linux-gnu, built 2026/07/28 18:56:00, go1.25.5)
database      w_qr_gate_refusal_proof
chain         271/271 applied, 0 failed, 70.706s
reached 0115  True
unproduced    (none) — every relation this tree references has a producer
PROJECTION    10/10 held · open_blocking 0->1 · gate_epoch 0->1 · outbox 'check_opened' severity 4 (client supplied 0)
REFUSAL       REFUSED [23514] gate_closed_when_issued (reported)
DRIFT         REFUSED [P0001] mainline.fn_permit_merge_gate (parsed)
ADMISSION     ADMITTED [00000]
caveats       (none) — nothing in this run is unproven-but-tolerated
VERDICT       PROVEN
evidence      evidence/gate-refusal/proof-20260813T191013Z.json
```

Every beat quoted. **Beat 4 is `ADMISSION [00000]`.** The gate proof is `PROVEN` with the
`caveats` line reading `(none)` — caveat-free, as claimed.

`docs/deploy/LATENCY.md` corroborates over the HTTP path: **both targets ran all four beats
and returned `PROVEN` in 100 of 100 samples**, warm gate run 1,340 ms p50.

**The 10.1 s `/v1/health` is superseded by measurement**, not by a moved ceiling: `health`
now measures 8.21 ms p50 local, 450.35 ms p50 cloud, 2.1 s cold. The 5 s ceiling is not
threatened warm.

---

## 5 · The cost residual — QUANTIFIED, and the trade is named

`evidence/deploy/cost/cost-model.json`, produced by `scripts/deploy/cost_model.py`:

| figure | value | what it prices |
|---|---:|---|
| **in-window residual** | **$1.6022 per minute** | a flood that trips the 60 s burst alarm and bills until `PutFunctionConcurrency(0)` lands |
| paced residual, 24 h | **$5.44** | a caller who stays under every alarm threshold, bounded by the AWS Budgets 8–24 h lag |
| paced residual, 30 d unattended | **$564.04** | nobody looks |
| flood rate, 24 h, for contrast | $1,993.99 | what the stop is worth |

The model is honest in three ways that matter:

* **The answer is a rate times a lag, not a scalar**, and the file says so in a field named
  `answer_is_a_rate_times_a_lag_not_a_scalar`. The alarm evaluation window is 60 s at
  `evaluation_periods 1`, `datapoints_to_alarm 1`; the threshold is crossed in 1.698 s at
  flood rate, so worst-case detection is the full 60 s plus an **unmeasured delivery path**,
  which the model declines to invent a number for.
* **The two residuals are additive, not alternatives.** Paced and in-window describe two
  different attackers; the file refuses to quote one where the other applies.
* **The ceiling dependency is published both ways.** The reachable residual is $5.44 with
  the 139,264 B ceiling refusing the 433,396 B asset, and $18.80 without it — *"a residual
  that silently assumed the favourable one would understate this by 3.5× the moment it
  did."*

The availability trade is named where it belongs: `PutFunctionConcurrency(0)` stops the
demo. That is the point — a bounded-but-open URL with no auth trades availability for a
spend floor, deliberately.

---

## 6 · The plan — now reproducible locally, read-only, and it matches

Blocker 9 is closed. `scripts/deploy/plan_repro.sh`, run today with Terraform v1.14.8:

```
== 2 · the empty-state equivalence, measured read-only
  state buckets          none — no mainline-demo-tfstate-* bucket in this account
  lambda mainline-demo-api does not exist   [equivalence holds]
== 4 · terraform init -reconfigure / validate / plan
  validate               Success! The configuration is valid.
== 5 · the plan, and the committed artefact
  fresh plan             Plan: 24 to add, 0 to change, 0 to destroy.
  committed artefact     evidence/deploy/terraform-plan-furl.txt  says Plan: 24 to add
  G6 reservation         reserved_concurrent_executions = -1
  No AWS resource was created, changed or deleted by this run.
```

The script routes every Terraform call through one wrapper carrying an allowlist of
`init`/`validate`/`plan`/`show`/`version`; `apply`, `destroy`, `import`, `state`, `taint`
and `force-unlock` are refused by name before `terraform` executes. It **measures** the
empty-state equivalence read-only on every run and exits 5 once it expires, rather than
asserting it in a comment. **Nothing was applied.**

**But:** `infra/modules/cost-guard/` is untracked while `infra/envs/demo/main.tf`
instantiates it at `module "guard"`. This plan reproduces on *this* machine only. On a
fresh clone `terraform init` fails to resolve the module source.

---

## 7 · Status matrix

### PROVEN

* **Beat 4 and the gate proof** — `PROVEN`, caveat-free, re-run today (§4).
* **The shortcut discipline** — demonstrated cutting both ways in one commit (§1).
* **The suite, locally** — 527/528, order-invariant across four shuffles (§2).
* **The cost residual** — $1.6022/min in-window, $5.44/24 h paced, $564.04/30 d (§5).
* **The Terraform plan** — 24 resources, reproducible with zero mutating calls (§6).
* **The response ceiling** — `139,264 B` derived from I3 over the deployed artefact, with
  eleven logged falsifications (§1.4).
* **`--strip-source-maps` default; 0 source maps in the artefact; 57 `.gz` siblings served.**
* **`cost-guard`** — complete, valid, Stubber-tested with falsification, instantiated.

### BUILT-BUT-UNPROVEN

* **The cluster lane's falsifiability.** The 2×2 exists and is well designed; not one cell
  has completed (§3.2).
* **`cluster_lane_report.py`'s controls.** 137 pass locally; untracked, so unproven on the
  repository (§3.3).
* **Intra-process order contamination.** NOT-OBSERVED with a stated reason, which is the
  correct claim and is not "fixed" (§2).
* **The demo-api suite on a multi-node cluster.** Every green is from a single-node local
  node. The `40001 RETRY_SERIALIZABLE` loop CockroachDB Cloud requires is exercised by
  nothing here — and `_seed_permit` (`test_transitions.py:224`) commits ~29 statements with
  no retry, which is a fixture that will flake in the environment that matters.

### BROKEN

* **The published repository.** 93 uncommitted paths; the suite collects 207 of 528 and
  errors (§3.1).
* **The defeater vocabulary.** `mainline.defeater_option` is empty; a judge cannot sign
  through the console. One failing test, left failing on purpose (§1.3).
* **Two frozen-seed baselines** owed re-baselining in the same commit as the seed change
  (§3.2).
* **`docs/deploy/COST-BOUND.md`'s interface table** still declares I4 as `1,554,168 B —
  index-BjAGxrVJ.js.map` and I6 as `3,571,990 B over 75 files`. The package contains **zero**
  source maps. The same document's summary already gives the correct `124,127 B`, so the
  document contradicts itself. `docs/leads/cost-bound-plan.md:25,28` carries the same two
  figures; `docs/deploy/LATENCY.md` measures a beat against a `.map` URL the origin 404s.
* **`qa/cluster-known-red.json`** names `cr_id` as the error cause; the cause moved to
  `commit_v2` and is now fixed. Stale against its own tree, and its `unstable` list is aimed
  at three of a thirteen-member family.

### NOT BUILT

* Any auth on the demo URL — **deliberate**, founder's bounded-but-open posture.
* A retry loop in the test fixtures for CockroachDB Cloud's `40001`.
* A producer for `trappoint_ref.event` (the `ci` PL-2 and `schema` unwelding reds both
  wait on it — correctly red, and correctly refusing to launder a different run's URL).

---

## 8 · The rules matrix — every rule checked, none weakened

| rule | status |
|---|---|
| Never move an authoritative value to match a derived one | **HELD** — §1, with a test left failing to prove it |
| Never `terraform apply` | **HELD** — `plan_repro.sh` refuses `apply` by name; nothing applied |
| Never print a credential | **HELD** — no credential in this document or any artefact read |
| Never weaken `HONESTY.md`, `CI-STATE.md`, a ratchet, or an assertion | **HELD** — the ceiling tightened, the refusal set shrank, no assertion relaxed |
| `continue-on-error` / `\|\| true` banned | **HELD** — `cluster-tests.yml` states the ban and fails hard |
| Report before/after `--crdb=reuse` numbers | **HELD** — §2 |
| `reserved_concurrent_executions = -1`; alarms `treat_missing_data = "missing"`; concurrency alarm at 8 under the measured ceiling of 10 | **HELD** — confirmed in the fresh plan |
| Preconditions satisfied, never relaxed | **HELD** |

---

## 9 · What happens next

### Only the founder can do these

1. **Nothing, until §9.2 lands.** There is no decision waiting on you that engineering has
   not already answered. Do **not** approve a deploy: the plan is honest but the artefact it
   would deploy is assembled from files that are not in the repository.
2. **Confirm the SNS email subscription** *after* the guard is applied — Terraform creates it
   `PendingConfirmation` and cannot click the link. Until somebody clicks it the demo stops
   silently. This is the only step in the stop path a machine cannot take.
3. **Decide the defeater vocabulary** (§1.3), if you want a judge to be able to *sign* rather
   than only to watch the gate refuse. This is a product call about what the demo must
   carry, not an engineering one. The gate demo works either way; the console's signature
   path does not.
4. **Accept or reject the availability trade** already encoded: at $1.60/minute of exposure,
   the guard stops the demo rather than letting it bill. Someone can take your demo down for
   the price of a flood. That is the trade a bounded-but-open URL buys, and it is the right
   one — but it is yours to accept out loud.

### Engineering remaining, in order

1. **COMMIT AND PUSH THE WAVE.** This is one action and it unblocks four separate reds.
   93 paths, six workers. It must include, **in the same commit as the seed change**, the two
   `tests/ci/test_demo_seed_is_frozen.py` re-baselines with a message saying what changed in
   the seed and why (the ledger checkpoints, and the `boundary_proof` rebuilt as a real
   one-leaf MTH). Until this happens every number in §2, §4, §5 and §6 describes a machine
   rather than a repository.
2. **Watch the cluster lane go green, then watch `cluster-lane-bites` complete one matrix.**
   The lane is not proven by passing; it is proven by the 2×2 discriminating —
   plant-present/hermetic passing the *same count* as plant-absent. Do not accept the lane
   until that number is on a screen.
3. **Seed `mainline.defeater_option`** (§1.3), or delete the step from
   `console/src/a11y/contract.ts`. One of the two, decided on §9.1(3).
4. **Give `test_gate_run.py:143`'s scratch database a unique name** and add a `40001` retry to
   `_seed_permit`. The first ends a measurement hazard that has already corrupted one
   published `unstable` list; the second is the difference between a fixture that works on a
   single local node and one that works on the managed cluster this demo deploys to.
5. **Fix `docs/deploy/COST-BOUND.md`'s I4/I6 rows** and the two documents that copy them.
   The document currently contradicts itself about the same quantity.
6. **Regenerate `ANOMALY_COVERAGE.md`** and re-run `schema`.
7. **Re-baseline `qa/cluster-known-red.json`** or delete its `groups`, which is what the
   cluster lane's plan says should happen.

---

## 10 · The verdict

**NO-GO. Fifth time.**

Not because the work is bad — this is by a distance the best wave the project has had. The
suite went from 453/7/63 to 527/1/0 and holds under randomisation; the ceiling question was
answered with a ruling and eleven falsifications instead of a paste; the cost residual has a
dollar figure and an honest one; the plan reproduces without touching AWS; and one test was
left red on purpose, which is the single most convincing thing in this document.

It is NO-GO because **the repository does not contain any of that.** The cluster lane, built
by an earlier wave to catch exactly this class of error, ran for the first time and caught
it in twenty-nine seconds. Believing it is the whole point of having built it.

One `git add -A`, one honest commit message carrying the two seed re-baselines, one push,
and four of the six red lanes should turn. Then re-verify. **A sixth verification against a
pushed tree could very plausibly be a GO** — but it cannot be this one, because there is
nothing published to certify.
