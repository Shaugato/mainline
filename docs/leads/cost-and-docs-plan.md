<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# Cost-and-docs lead — plan, rulings, and six worker briefs

**Lead:** cost-and-docs · **Written:** 2026-08-14 · **Tree:** `master` @ `e944407` (plus an
uncommitted working set, enumerated in §1.3)
**Nothing in this plan applies anything.** `init`, `validate`, `plan`, `show` and read-only
AWS calls only. No worker is authorised to run `terraform apply`, and §2 R9 withdraws
authorisation for one script the runbook currently recommends.

---

## 0 · The rule that outranks every task below

A worker was once caught editing `demo_world.sql` to enrol a derived credential id — making
the seed match the code. **When a test and the code disagree, never move whichever side is
easier. Ask which side is AUTHORITATIVE.** Changing a seed, fixture, ceiling, threshold or
expected value to obtain a green converts a real defect into a permanent invisible one.

This wave is unusually exposed to that failure, because **two of the eight baseline failures
are documentation ratchets that are red for the correct reason** (§1.2). The cheapest way to
green them is to edit the test or delete the sentence. One of the two tests exists
specifically to catch the deletion — its docstring says *"A claim deleted is not a claim
corrected."* Do not try.

If you believe a fixture, ceiling or expectation is wrong, **say so in `still_broken` with
evidence and leave it alone.**

---

## 1 · Baseline, measured by me, before any decomposition

### 1.1 The numbers

Taken from `--junitxml`, never from a terminal scroll, per the standing warning that this
suite is I/O-bound and silent for minutes.

```
.venv/Scripts/python.exe -m pytest \
  verticals/mainline/apps/demo-api/tests tests/deploy \
  --crdb=reuse -q -p no:randomly --junitxml=<scratch>/demoapi-deploy.xml
```

| Metric | Baseline |
|---|---|
| tests collected | **619** |
| **passed** | **547** |
| failed | **8** |
| errors | **63** |
| skipped | 1 |
| wall clock | 53.09 s |

CockroachDB reachable: `CockroachDB CCL v26.2.5`. This is the demo-api + deploy scope, which
is the scope this wave touches; it is not the whole-repository figure and is not offered as
one.

### 1.2 The two baseline failures that belong to this wave

Both live in `tests/deploy/test_cost_model.py` and both are **correct**:

```
AssertionError: The committed plan artefacts report 22
  (evidence/deploy/terraform-plan-cloudfront.txt), 24 (evidence/deploy/terraform-plan-furl.txt).

AssertionError: the shipping plan is 'Plan: 24 to add' per evidence\deploy\terraform-plan-furl.txt,
  and no live document says so. A claim deleted is not a claim corrected.
```

The tree already had the control that catches the lie in this brief's item (c). The lie
outlived it only because the control was never green. **These two must go green by moving
the prose, not the test.**

The other six baseline failures (`test_response_contract.py` ×4, the `silence` seed row, the
undeclared-query-parameter refusal) and all 63 errors (`test_reads.py` `payloads` fixture,
`KeyError: 'commit_v2'`) belong to other leads. **No worker in this wave may touch them**,
and no worker may count them as their own regression.

### 1.3 Working-set hazard

`git status` shows 29 modified tracked files and one **untracked** directory,
`evidence/deploy/cost/`, which contains `cost-model.json` — the evidence every figure in
§3 is derived from. **The table's own evidence is not in the repository** (R10). Workers must
not `git checkout` or `git stash` anything; the uncommitted set includes the regenerated FURL
plan artefacts this wave depends on.

---

## 2 · Rulings — made before any worker acts

### R1 · The brief's formula is arithmetically wrong, and must be written correctly

The brief says multiply *period × evaluation periods × datapoints*. **`datapoints_to_alarm`
is the M in an M-of-N evaluation, not a multiplier.** Worst-case time from first breaching
request to alarm state change is `period × evaluation_periods`. For the burst alarm
(`infra/modules/cost-guard/main.tf:673`): `period = 60`, `evaluation_periods = 1`,
`datapoints_to_alarm = 1` → **60 s**. Multiplying by `datapoints_to_alarm` is harmless here
only by the coincidence that it equals 1. Write the formula correctly so it stays correct if
the alarm is ever retuned.

The burst alarm is the binding one for a flood: at flood rate the 3,000-invocation threshold
is crossed in **1.70 s**, but the datapoint does not close until the period ends. Worst case
is therefore the **full** period, not the time-to-threshold.

### R2 · 60 s is a FLOOR, not the answer. Publishing it as the answer repeats the 100 ms error

The published USD 33,250 figure was wrong because it assumed a 100 ms invocation nobody had
measured. Publishing `60 s × rate` as *the* residual would make the identical mistake in the
identical way: it assumes the alarm-to-stop path costs zero, which nobody has measured. Between
the period closing and `PutFunctionConcurrency(0)` taking effect there are at least five
further terms — metric publication delay, alarm evaluation delay, SNS delivery, responder
Lambda cold start, and reserved-concurrency propagation with in-flight invocations draining.

**Therefore the honest publication is a rate times a lag budget, not a single scalar:**

* a **measured rate** — §3.1, `USD 1.60 per minute` at flood rate, priced from tier 1;
* a **lag budget** in which every term is separately sourced — measured read-only, or cited
  to AWS's own published documentation as a bound;
* a **sensitivity table** over total detection lag, so the founder sees the slope;
* and any term that is neither measurable read-only nor documented is **named as an unknown
  in the table**, not guessed. The previous agent was right to refuse to invent one. The fix
  is to bound it and name it, not to fill it in.

A single "after" scalar may be published **only** as `rate × a stated lag`, with the lag
visible in the same sentence.

### R3 · Do not scale the 24-hour flood figure down

`cost-model.json` already carries `flood_rate_24h_for_contrast_usd = 1993.99`. Dividing by
1,440 gives USD 1.385/min and is **wrong by −13.6 %**: the 24-hour figure blends the cheaper
$0.085/$0.082 egress tiers, which a 60-second window never reaches. Price each window
directly from tier 1 (§3.1 → USD 1.60/min). This preserves the file's existing
`each_window_priced_from_tier_1` convention and errs conservative.

### R4 · The in-window residual is ADDITIVE to the paced residual, not a replacement

`tests/deploy/test_cost_model.py::test_the_residual_is_computed_at_the_hourly_alarm_threshold_not_at_flood_rate`
asserts the existing residual is **not** at flood rate, and it is right: a caller pacing under
the alarms is a different attacker from a flood. The new in-window figure **is** at flood rate.

These are two different exposures of one system and both are real:

* **paced** — a caller who stays under every threshold, bounded only by the AWS Budgets
  Cost Explorer lag: `worst_usd = 5.44` over 24 h, `564.04` over 30 unattended days;
* **in-window** — a flood that trips the burst alarm and bills at full rate until the stop
  lands.

**That existing test must stay green and must not be weakened.** Add a new key under
`residual` and new controls in a new file. If a worker finds themselves editing that test's
assertion, they have taken the wrong branch — stop and report.

### R5 · The committed plan artefact is AUTHORITATIVE; the prose is DERIVED

`docs/deploy/terraform-plan.md:47` says *"The resource count did not move"* and quotes
`Plan: 11` and `Plan: 22`. `evidence/deploy/terraform-plan-furl.txt:843` says
`Plan: 24 to add, 0 to change, 0 to destroy.`, and the JSON carries 24 creates + 1 read.
**Move the prose to 24.** Never regenerate or reconfigure a plan in order to obtain 22, and
never resolve this by deleting the sentence — a control already catches deletion.

### R6 · The CloudFront artefact is STALE, and 22 is not its answer

`evidence/deploy/terraform-plan-cloudfront.txt` is dated **Aug 13 13:44**; the FURL artefacts
are **Aug 14 01:57**. The CloudFront file predates guard instantiation and still says 22. It
must be **regenerated, not quoted**. Expected ≈ **35** (22 + 13, per R7). **If it comes back
22, that is a finding — the guard is not reaching that configuration — and it must be reported
as such, not accepted as a green.**

### R7 · 11 + 14 = 25, but the plan says 24 — verify the reason, do not assume it

`infra/modules/cost-guard/main.tf` declares 14 `resource` blocks, and the shipping plan moved
11 → 24, which is 13. The expected explanation is that
`aws_sns_topic_subscription.email` is `count = length(var.notification_emails)` and
`guard_notification_emails` defaults to empty. **Confirm this from the plan JSON** — an
off-by-one that happens to net out is exactly the kind of thing this project exists to catch.

### R8 · Item (e) is discharged: the `.gz` serving code EXISTS. Write none

`verticals/mainline/apps/demo-api/src/mainline_demo_api/static_site.py` already implements
full content negotiation: `accepts_gzip()` honours `q=0` as a refusal and `x-gzip` as a
spelling, the sibling's bytes are served under the *identity* object's media type with
`content-encoding: gzip`, `vary: accept-encoding` is set, and **a direct request for any path
ending `.gz` is a 404** to avoid the cache-poisoning bug. The standing instruction was
*"check whether serving code now exists before writing any"* — the answer is **yes**.
**Do not write serving code. Do not stop shipping the siblings.** They are not dead bytes;
they are the bytes every real browser receives, and they are what makes the L3 lever worth
USD 113,000/30d. Verify with a control and document.

### R9 · `bootstrap_state.sh` MUTATES, and is therefore not authorised in this wave

The runbook's state-backend step calls `s3api create-bucket`, `put-bucket-versioning`,
`put-bucket-encryption`, `put-bucket-tagging` and `put-bucket-lifecycle-configuration`
(`scripts/deploy/bootstrap_state.sh:194–262`). Creating the state bucket is a **mutating AWS
call**. My standing constraint is read-only AWS calls only. **No worker may run
`bootstrap_state.sh` without `--print-backend-config`.**

`--print-backend-config` makes **zero** AWS calls (the script says so at line 92) and is
authorised.

The local reproduction must therefore be non-mutating. The path is a **local backend override
against empty state**, and its validity rests on a fact that must be stated wherever the
procedure is published: **nothing has been applied**, so the S3 state is empty, so a plan
against an empty local state is resource-identical to a plan against the empty remote state.
**That equivalence expires at the first apply.** Say so in the runbook, in the same
paragraph, or the procedure becomes a trap the day after it is first used.

### R10 · The evidence directory must be committed

`evidence/deploy/cost/` is untracked. Every figure in the honest table derives from
`cost-model.json` inside it. An unpublished evidence file in a public repository is a citation
to nothing. Commit it with REUSE `.license` sidecars — a control
(`test_the_evidence_file_carries_its_reuse_license_sidecar`) already requires them.

### R11 · The residual depends on a ceiling another lead is actively deciding

`response_ceiling_in_force()` reads `DEFAULT_MAX_RESPONSE_BYTES` (currently 139,264 B =
136 KiB) **at model time**, which is why the reachable residual is the 124,127 B gzip sibling
(USD 5.44) and not the 433,396 B identity object (USD 18.80). The `test_response_contract.py`
ceiling cascade is **another lead's ruling** and is out of scope here. **Preserve the
read-at-model-time design** — never hard-code 139,264 — so this wave's numbers follow that
ruling automatically instead of silently contradicting it. Publish both the reachable and
the lifted-ceiling rows, as the model already does.

---

## 3 · The residual, computed

### 3.1 The in-window rate

Computed with the model's **own** `Flood`/`price()` so the figure derives from authoritative
code rather than my arithmetic. Inputs read from `evidence/deploy/cost/cost-model.json`:
`after_largest_gz_bytes = 124,127`, `asset_js_p50_ms = 5.66`, concurrency 10, memory 256 MB,
`audit-decimal`, no free tier.

Flood rate = 10 / 0.00566 s = **1,766.784 rps**.

| Detection lag | Requests | USD | USD/min |
|---|---|---|---|
| **60 s** (R1 floor: `period × evaluation_periods`) | 106,007 | **1.60** | 1.60 |
| 120 s | 212,014 | 3.20 | 1.60 |
| 180 s | 318,021 | 4.81 | 1.60 |
| 300 s | 530,035 | 8.01 | 1.60 |
| 600 s | 1,060,071 | 16.02 | 1.60 |
| 900 s | 1,590,106 | 24.03 | 1.60 |

**Linear at USD 1.60/min**, because a window this short never leaves egress tier 1. That
linearity is the useful property: the founder can price any lag budget by multiplying.

**The floor is USD 1.60 per alarm window.** The honest figure is `1.60 × (60 s + the
unmeasured tail)/60`, and W1's job is to bound that tail by measurement or citation and name
what remains unknown.

### 3.2 What the table must say (item b)

One table, per layer, worst case USD/30d, **with the availability trade as a column, not a
footnote**:

| Layer | USD/30d | Status |
|---|---|---|
| L0 published headline (100 ms, assumed) | 33,251.87 | superseded — a floor, understated ~7× |
| **L1 corrected baseline (measured 14.106 ms)** | **229,804.98** | the honest "before" |
| L2 strip source maps (default) | 160,667.84 | in code |
| L3 gzip on the wire | 47,363.92 | in code, and R8 says it is served |
| L4 memory 512 → 256 | 47,277.52 | in code |
| L5 rate bound | 4,172.63 | in code |
| residual — paced under the alarms, 24 h | 5.44 | Budgets lag |
| residual — paced, 30 d unattended | 564.04 | if nobody looks |
| **residual — in-window at flood rate** | **1.60 / alarm minute** | §3.1, new |
| **the trade** | — | **the guard converts a cost attack into an availability attack** |

The last row is mandatory and belongs in the table. The URL is `authorization_type = NONE`
by the founder's explicit choice, so **anyone at all** can trip the burst alarm, and the
responder's stop is not aimed at attackers — it stops the demo for everyone, at reserved
concurrency 0, until a human runs `kill_switch.{sh,ps1} --restore`. That is the right trade,
because an outage is recoverable by one command and an unbounded bill is not. It is still a
trade, and the founder accepted the risk on the condition that the numbers are honest.

---

## 4 · Six workers, disjoint enumerated paths

No path appears in two rows. No worker edits another's files; cross-file needs go through the
lead.

| # | Worker | Owns (exclusively) | Depends on |
|---|---|---|---|
| W1 | The residual, in code | `scripts/deploy/cost_model.py`, `tests/deploy/test_cost_residual.py` (new), `evidence/deploy/cost/**` | — |
| W2 | The one honest table | `docs/deploy/COST-BOUND.md` | W1 |
| W3 | The plan page made true | `docs/deploy/terraform-plan.md` | W6 |
| W4 | A plan the founder can reproduce | `docs/deploy/PRE-APPLY.md`, `docs/deploy/RUNBOOK.md`, `scripts/deploy/plan_repro.sh` (new) | — |
| W5 | The downstream quoters | `docs/deploy/JUDGE-PACK.md`, `docs/submission/DEVPOST.md`, `docs/submission/JUDGE-START.md`, `docs/STATE-OF-THE-BUILD.md`, `scripts/submission/check_submission_ready.py` | W6 |
| W6 | Artefacts and the `.gz` question | `evidence/deploy/terraform-plan-furl.{txt,json}`, `evidence/deploy/terraform-plan-cloudfront.{txt,json}`, `tests/deploy/test_furl_compression.py`, `docs/deploy/lambda-bundle.md` | W4 |

**Nobody owns** `tests/deploy/test_cost_model.py`. Its 27 controls — including the two red
ones — are the referee for this wave. If a worker believes one is wrong, that goes in
`still_broken` with evidence; it does not get edited.

Every brief carries the no-shortcut rule, and every worker reports demo-api + `tests/deploy`
`--crdb=reuse` junitxml counts **before and after**, against the §1.1 baseline of
**619 / 547 passed / 8 failed / 63 errors / 1 skipped**.

---

## 5 · Sequencing

```
W1 ──► W2
W4 ──► W6 ──► W3
              └─► W5
```

W1 and W4 start immediately. W6 cannot regenerate artefacts until W4 has established a
non-mutating reproduction path (R9). W3 and W5 cannot quote counts until W6 has produced
them.

---

## 6 · Done, for the wave

1. `tests/deploy/test_cost_model.py` plan-count controls are **green because the prose moved**.
2. Passed ≥ 547 + 2. No new failure, no new error. Regressions are reported, not absorbed.
3. `docs/deploy/COST-BOUND.md` no longer says the guard is uninstantiated, and carries one
   table with the availability trade as a row.
4. `docs/deploy/terraform-plan.md` no longer says the count did not move.
5. A founder on a clean machine can produce the shipping plan by following one document,
   with no mutating call, and the equivalence's expiry is stated.
6. Both plan artefacts and `evidence/deploy/cost/` are committed, with `.license` sidecars.
7. The residual exists as `rate × lag`, with every lag term sourced and any residue named
   as unknown.
