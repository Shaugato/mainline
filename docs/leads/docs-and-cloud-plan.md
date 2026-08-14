<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# DOCS-AND-DEPLOY — the wave that makes every document true about its own repository

**Lead:** docs-and-deploy · **Written:** 2026-08-14 on TRAPPOINT · HEAD `eefae1c`, branch
`master`, working tree clean at the time this baseline was taken
· **Interpreter:** `D:/CoackroachDBxAWS/mainline/.venv/Scripts/python.exe`
· **Terraform:** v1.14.8, `windows_amd64`
· **Workers:** 6, disjoint paths, enumerated literally in §4

**Nothing in this wave applies anything.** `terraform init`, `validate`, `plan` and `show`
only; read-only AWS calls only. No worker in this wave may run `terraform apply`, and no
worker may edit an evidence artefact to agree with a document.

---

## 0 · Why this wave exists, in one sentence

MAINLINE's entire pitch is that it tells you what it has not proven. **A document that is
false about its own repository is the exact failure this product sells against** — and
`github.com/Shaugato/mainline` is PUBLIC, so every claim in `docs/` is a claim a judge can
open a second tab and check. This wave's deliverable is not prose quality. It is that a
stranger who tries to catch us out cannot.

---

## 1 · MY BASELINE, measured before decomposing anything

Everything below was run by me, on this machine, at HEAD `eefae1c`, before any worker was
briefed. Numbers are from the tools' own output, not from a terminal scroll I skimmed.

### 1.1 · The doc-truth harness that already exists, and is already RED

```
$ .venv/Scripts/python.exe -m pytest tests/deploy/test_cost_model.py --crdb=none -q -p no:randomly
1 failed, 35 passed in 0.95s
```

The one failure is a **real defect, correctly caught**:

```
test_the_shipping_plan_count_in_the_docs_matches_the_plan_evidence
  The committed plan artefacts report 24 (evidence/deploy/terraform-plan-furl.txt),
                                      35 (evidence/deploy/terraform-plan-cloudfront.txt).
  These live claims quote a count nothing supports:
    docs/deploy/OBSERVABILITY.md:308 says 'Plan: 11 to add', which no committed plan
    artefact reports
  Re-read the regenerated plan evidence and correct the documents. Do NOT edit the
  evidence file to match the documents.
```

**This is the single most important fact in this plan.** A doc-truth ratchet already exists,
it already works, and it is already red against the tree. This wave does not invent a
mechanism. It **turns that red green for the right reason, and then widens the ratchet's
aperture so the next drift is caught by a test rather than by a lead reading 15,012 lines.**

`AFTER` for this wave must read `36 passed` on this file, plus whatever W6 adds.

### 1.2 · The other gates, for the record

| Gate | Baseline | Note |
|---|---|---|
| `tests/release/test_honesty_is_checkable.py` | **34 passed, 0 failed** | green; do not disturb |
| `scripts/submission/check_submission_prose.py` | **3 claim-hygiene violations**, all `docs/HONESTY.md` `[HYG-sha-literal]` | `HONESTY.md` is **out of scope for this wave** and is under an absolute prohibition. Not ours. Report, do not touch |
| `scripts/submission/check_submission_ready.py` | **NOT READY — 2 unresolved rows**: `demo_url`, `video_url`, both `UNRESOLVED` | **correct and must stay that way** (RULING 6) |

### 1.3 · The tree, measured directly

```
$ .venv/Scripts/python.exe  # zipfile over out/lambda/mainline-demo-api-{arm64,x86_64}.zip
arm64  web entries 114  bytes 1,274,342
       maps 0   identity 57 / 985,030 B   gz 57 / 289,312 B
       largest identity  web/assets/index-BjAGxrVJ.js      433,396
       largest gz        web/assets/index-BjAGxrVJ.js.gz   124,127
x86_64 identical, byte for byte
```

Against `evidence/deploy/cost/package-shape.json`, which carries **both** trees:

| | files | bytes | source maps | `.gz` siblings | largest object |
|---|---:|---:|---:|---:|---:|
| `before` — the packer's **input** tree | 75 | 3,571,990 | 18 / 2,586,960 B | 0 | **1,554,168 B** `index-BjAGxrVJ.js.map` |
| `after` — the **deployed** package | 114 | 1,274,342 | **0** | 57 | 433,396 B identity / **124,127 B** gz |

**Both columns are true. Of different trees.** That single sentence is the whole of blocker 5
(a), and §2 rules on it.

### 1.4 · The committed plan artefacts, read directly

```
evidence/deploy/terraform-plan-furl.txt:843        Plan: 24 to add, 0 to change, 0 to destroy.
evidence/deploy/terraform-plan-cloudfront.txt:1219 Plan: 35 to add, ...
```

Attributes read out of `terraform-plan-furl.txt` by line:

| Attribute | Artefact says | Line |
|---|---:|---:|
| `memory_size` | **256** | 290 |
| `reserved_concurrent_executions` | **-1** | 296 |
| `timeout` | **14** | 315 |
| `authorization_type` | **`"NONE"`** | 351 |

And from the tree:

```
infra/envs/demo/main.tf:631   module "guard" {
infra/envs/demo/main.tf:632     source = "../../modules/cost-guard"
infra/envs/demo/main.tf:292     guard_stop_topic_actions = try([module.guard[0].sns_topic_arn], [])
infra/envs/demo/main.tf:586     alarm_actions = local.guard_stop_topic_actions
```

### 1.5 · The fresh-clone reproduction, attempted by me, twice

| Attempt | Result |
|---|---|
| `git clone --depth 1` into the **scratchpad** (a 121-character parent path) | **7,584 files silently missing from the checkout.** `git clone` printed a soft warning and exited without a hard failure; `git status --short` showed 7,584 `D` rows. `core.longpaths` is unset on this machine, system and global |
| `git clone --depth 1` into `D:/_fc` (a 6-character parent path) | **0 missing.** Clean checkout |
| `terraform init -backend=false` in the fresh clone | **Success.** `hashicorp/aws v6.58.0` installed and signature-verified from the committed `.terraform.lock.hcl` |
| `terraform validate` | **`Success! The configuration is valid.`** |
| `terraform plan` | **REFUSED**, verbatim: *"Changes to backend configurations require reinitialization … run `terraform init` with either the `-reconfigure` or `-migrate-state` flags"* |

So the brief's scope (c) statement is **confirmed by measurement**: from a clean clone,
today, only `init -backend=false` and `validate` run. `plan` does not.

**And there is a fresh-clone hazard nobody has written down**: on Windows without
`core.longpaths=true`, `git clone` of this repository into a long parent directory loses
thousands of files *without failing loudly*. A reviewer who hits that and then runs
`terraform validate` in the fragment they got is validating something that is not this
repository. That belongs in the runbook (W4).

### 1.6 · What I found ALREADY DONE that the brief assumes is not

I checked before assigning. Three of the brief's items are already true, and a worker sent
to "fix" them would move a correct document:

1. **`docs/deploy/terraform-plan.md` does NOT still say the count "did not move".** Its §0.1
   is titled *"the resource count moved, and this page had said it did not"* and reads
   *"**That was false**"*, with a table giving 11 → **24** and 22 → **35** against the
   artefact lines. It is already the corrected document. See RULING 5.
2. **`scripts/deploy/plan_repro.sh` already exists** and already solves the partial-backend
   problem, with an allowlisted `tf` wrapper that refuses `apply`/`destroy`/`import`/`state`/
   `taint`/`force-unlock` by name before `terraform` is executed, a `--prove-refusal`
   negative control, and a stage-2 empty-state equivalence check that exits 5 when the
   equivalence expires. Scope (c) is therefore **prove and document**, not **build**.
3. **`docs/deploy/COST-BOUND.md` §0.1 row T already states the trade in the table**, not in a
   footnote — *"THE GUARD CONVERTS A COST ATTACK INTO AN AVAILABILITY ATTACK"* — and the
   prose beneath it records that it was moved out of a blockquote on 2026-08-14 precisely
   because *"a footnote wearing a heading"* is not the table. Scope (b) is therefore
   **verify and close the gaps around it**, not **write it**.

A lead who did not measure would have spent three workers re-doing finished work and moved
two correct documents in the wrong direction. **Measure first. It is the rule.**

---

## 2 · RULINGS — decided in writing, before any worker acts, each naming its authority

The brief poses the question directly: `COST-BOUND.md` gives 1,554,168 B and 3,571,990 B in
one section and 124,127 B and "0 source maps" two sections away. Which side moves?

### RULING 1 — The numbers 1,554,168 / 3,571,990 / 2,586,960 **do not move**. The label and the sourcing move.

**Authority:** `docs/decisions/response-ceiling-authoritative-tree.md` — a ratified decision
document, §1: *"**Ruling: the deployed tree.** Cost is incurred by bytes leaving the deployed
origin"* — read together with §8 of the same file, which already names this exact defect and
hands it to this wave:

> `docs/deploy/COST-BOUND.md` declares interface **I4** as *"Largest response the origin can
> emit: 1,554,168 B"* … **The zip contains zero source maps.** … Both are the input-tree
> error this ruling corrects, in the document the ceiling is quoted from. … **One of the two
> has to move, and it is not the summary.**

**Which is not the same as "retype the numbers."** Three independent authorities forbid that:

1. **COST-BOUND's own preservation rule**, in its header: *"Where a §1–§9 sentence has since
   become false, it is struck through or annotated in place, never removed. A claim deleted
   is not a claim corrected."*
2. **The reproduction gate.** The header declares §1–§9 the **reproduction baseline**, and
   `tests/deploy/test_cost_model.py::test_the_model_reproduces_every_published_headline`
   fails the build unless `scripts/deploy/cost_model.py` re-derives §2.2's **$33,251.87**
   from those inputs. 1,554,168 B is a *load-bearing input* to that reproduction.
3. **§0.1 row L1 consumes it as the honest "before."** The measured-duration row is
   `708 rps × 1,554,168 B`. Retype the input and the ×6.91 correction — the largest single
   honesty finding in the document — evaporates.

**So the defect is not arithmetic. It is tense and sourcing.** Rows I4/I6/I7 say *"Largest
response the origin **can emit**"*, present tense, sourced to *"`zipfile` over
`out/lambda/mainline-demo-api-arm64.zip`"* — the **deployed** package, which does not contain
what the row describes. **That sourcing line is the false claim**, and it is false in the
worst way available: it names an artefact anyone can open in thirty seconds and be told the
opposite.

**The fix, exactly:** keep every digit; re-label the rows as the packer's **input** tree;
correct the sourcing to `evidence/deploy/cost/package-shape.json` → `architectures[].before`;
add the deployed-tree row beside each; annotate in place in the same visual idiom §3.2/§3.3
already use; and **add §1 to the header's enumerated list of annotated sections**, which
today reads "(§3.2, §3.3, §3.6, §5, §5.1, §6, §9)" and omits §1 — which is *why* §1 reads as
current when it is historical.

### RULING 2 — Two trees, both authoritative, for different questions.

**Authority:** the same decision document, plus the standing already-true finding that *"the
DEPLOYED tree is authoritative because cost is bytes leaving the origin."*

* **What the origin can emit today, and therefore every cost and ceiling claim** → the
  **deployed** package. 114 entries, 1,274,342 B, 0 maps, 433,396 B identity / 124,127 B gz.
* **The pre-strip baseline that §2.2's $33,251.87 reproduces from** → the packer's **input**
  tree. 75 entries, 3,571,990 B, 18 maps, 1,554,168 B largest.

Neither is wrong. **A figure that does not name its tree is wrong**, whichever tree it came
from. Every worker states the tree beside every byte figure it writes.

### RULING 3 — `LATENCY.md`'s `asset_map` beat stays. Annotated, not deleted.

**Authority:** `COST-BOUND.md` §0.1 row L1 is built on `14.106 ms`, which is exactly this
beat. Deleting the row orphans the only measurement the honest "before" rests on, and the
preservation rule in RULING 1 applies to it identically.

**What is false** is the implicature, not the measurement: the row reads as a beat of the
shipping origin, and the shipping origin answers **404** to `GET /assets/index-BjAGxrVJ.js.map`
because the package holds zero maps. The measurement was taken against `local_furl.py` over
the packer's input tree, and it is a true measurement **of a tree that no longer deploys**.
Annotate it as such, in place, with the deployed-origin beat (`asset_js`, 5.66 ms, 433,396 B)
named as the row that describes what a request can actually reach today.

### RULING 4 — For resource counts and function-shape attributes, the committed plan artefact is authoritative and prose is derived.

**Authority:** `docs/deploy/terraform-plan.md` §0.1 states it in terms — *"The committed plan
artefact is **authoritative** and this prose is **derived**"* — and
`tests/deploy/test_cost_model.py::test_the_shipping_plan_count_in_the_docs_matches_the_plan_evidence`
enforces it, with an assertion message that ends *"Do NOT edit the evidence file to match the
documents."*

This settles four live staleness findings at once, all of which are prose losing to the
artefact:

| Live claim | Says | Artefact says | Line |
|---|---|---|---|
| `COST-BOUND.md:307` I9 | `memory_size = 512`, `timeout = 15`, `reserved = 20` | **256 / 14 / -1** | `furl.txt:290,315,296` |
| `COST-BOUND.md:306` I8 | cites `furl.txt:329` | `authorization_type` is at **351** | — |
| `OBSERVABILITY.md:161` | `-duration-p99 > 12 000 ms`, "the 15 s timeout" | **13,500 ms**, **14 s** | `furl.txt:124,315` |
| `OBSERVABILITY.md:300-310` | *"`infra/envs/demo/main.tf` has **no `module "guard"` block**"* and `Plan: 11 to add` "records **today**" | the block is at **`main.tf:631`**; the artefact says **24** | — |

That last one is the worst document in the repository right now: it asserts the absence of a
block that is in the tree, and it does so in a paragraph that *correctly explains* that the
count is checked by a test — a document explaining its own ratchet while failing it.

### RULING 5 — Do not "fix" `terraform-plan.md` §0.1. It is already correct.

**Authority:** direct read, §1.6 above. The brief's item (d) is stale about the tree in
exactly the way this wave exists to prevent, which is worth stating out loud rather than
quietly working around. What **is** genuinely open on that page is one citation:
`terraform-plan.md:45` cites `infra/envs/demo/main.tf:632` for the module block, and **632 is
the `source` line — the block opens at 631**. Off by one, checkable, ours.

### RULING 6 — `docs/submission/SUBMISSION.json` is not touched. `UNRESOLVED` stays.

**Authority:** the file is the declared single write point for `demo_url`/`video_url`;
`check_submission_ready.py` is the gate; nothing is deployed and no film is shot; and the
brief says leave `UNRESOLVED` wherever it genuinely is. It genuinely is. **Writing a URL that
does not answer is the failure mode this whole product is a rebuttal to.** No worker edits
that file. W5 documents the two rows as UNMET and moves on.

### RULING 7 — If a regenerated plan returns a count other than 24 / 35, that is an escalation, not an edit.

**Authority:** RULING 4 plus the standing prohibition on moving an authoritative value to
match a derived one. W4 regenerates; if the regenerated artefact disagrees with the committed
one, **W4 stops and reports to the lead**. It does not update the docs to the new number on
its own authority, and it does not restore the old artefact to protect the docs. Either
direction taken silently is the seed-editing defect wearing a different hat.

### RULING 8 — `docs/HONESTY.md` and `docs/CI-STATE.md` are OUT OF SCOPE for this wave.

**Authority:** the standing absolute prohibition — *"NEVER weaken HONESTY.md, CI-STATE.md, a
ratchet or an assertion."* The prose gate's 3 baseline violations are all in `HONESTY.md`.
They are **reported in §1.2 and left exactly where they are.** A docs wave that touches the
honesty ledger to make its own numbers look better is the single most damaging thing this
wave could do. If a worker believes `HONESTY.md` is false, it reports to the lead and stops.

---

## 3 · THE NO-SHORTCUT RULE — reproduced verbatim in all six briefs

> **When a document and an artefact disagree, do not move whichever is easier. Ask which
> side is AUTHORITATIVE, and name that authority in writing before you edit either.** The
> ratified tiebreaker: **the console and the committed JSON schemas are authoritative for
> what the demo must carry, and the seed and the tests are BOTH checked against them —
> either may lose.** For this wave the same shape applies one layer out: **the committed
> evidence artefact and the tree are authoritative; the prose is derived.**
>
> Concretely, and none of these is negotiable:
> * **NEVER** edit a file under `evidence/` so that a document becomes true.
> * **NEVER** delete a claim instead of correcting it. A claim deleted is not a claim
>   corrected, and the correction is only checkable against the claim it corrects.
> * **NEVER** lower `COLLECTED_FLOOR`, a skip ceiling, a known-red list, or any threshold.
> * **NEVER** add `continue-on-error` or `|| true`.
> * **NEVER** run `terraform apply`. `init` / `validate` / `plan` / `show` only, and
>   read-only AWS calls only.
> * **NEVER** print or rotate a credential.
> * **NEVER** weaken `docs/HONESTY.md`, `docs/CI-STATE.md`, a ratchet or an assertion.
> * If the only way to make a claim true is to weaken the thing that checks it, **the claim
>   was the defect. Say so in the document and leave the check alone.**
> * A number you cannot re-derive on this machine today does not go in a document. Write
>   `UNRESOLVED` and name what would settle it. **`UNRESOLVED` is a permitted answer in this
>   wave and a preferred one over a guess.**

---

## 4 · THE SIX WORKERS — disjoint, literally enumerated paths

No path appears under two workers. If a worker needs a line changed in a file it does not
own, it reports the line to the lead; it does not edit it.

| # | Worker | Owns (literal) | Depends on |
|---|---|---|---|
| W1 | cost-bound-truth | `docs/deploy/COST-BOUND.md`, `docs/leads/cost-bound-plan.md` | — |
| W2 | latency-truth | `docs/deploy/LATENCY.md` | — |
| W3 | deploy-docs-sweep | `docs/deploy/OBSERVABILITY.md`, `RUNBOOK.md`, `PRE-APPLY.md`, `JUDGE-PACK.md`, `lambda-bundle.md`, `console-build.md`, `cloud-database.md`, `gate-run-contract.md`, `replay-fallback.md`, `unproduced-tables.md` | — |
| W4 | plan-repro | `docs/deploy/terraform-plan.md`, `scripts/deploy/plan_repro.sh`, `evidence/deploy/terraform-plan-furl.{txt,json}`, `evidence/deploy/terraform-plan-cloudfront.{txt,json}`, `evidence/deploy/lead/plan-repro-fresh-clone.json` | — |
| W5 | submission-truth | `docs/submission/DEVPOST.md`, `docs/submission/RULES-MATRIX.md`, `docs/TOOL-USAGE.md` | — |
| W6 | doc-truth-ratchet | `tests/deploy/test_cost_model.py`, `tests/deploy/test_docs_are_true.py` (new) | W1, W3, W5 for final green |

**W6 authors immediately and in parallel.** Its tests are written against the *artefacts*,
not against the prose, so they are red at authoring time and go green as W1/W3/W5 land. A
test written after the prose it checks is a test written to pass.

**Shared read-only inputs** (nobody owns, everybody may read): `evidence/deploy/**`,
`infra/**`, `out/lambda/**`, `docs/decisions/response-ceiling-authoritative-tree.md`.

---

## 5 · Acceptance for the wave

| # | Gate | BEFORE | Required AFTER |
|---|---|---|---|
| 1 | `pytest tests/deploy/test_cost_model.py --crdb=none` | **1 failed, 35 passed** | **0 failed**, ≥ 36 passed |
| 2 | `pytest tests/deploy/test_docs_are_true.py --crdb=none` | does not exist | **0 failed**, ≥ 8 passed, ≥ 3 of them negative controls |
| 3 | `pytest tests/release/test_honesty_is_checkable.py --crdb=none` | **34 passed** | **34 passed** — unchanged. A change here is a regression |
| 4 | `check_submission_ready.py` | NOT READY, 2 rows | **NOT READY, exactly the same 2 rows.** Any other outcome means somebody wrote a URL |
| 5 | `check_submission_prose.py` | 3 `HONESTY.md` violations | **the same 3.** Not ours (RULING 8) |
| 6 | Full demo-api suite, `--crdb=reuse` | **528 collected, 527 passed, 1 failed, 0 errors** | **identical or better.** Taken from `--junitxml`, `tests=` attribute read, never from a terminal scroll |
| 7 | `git diff` over `evidence/**` | — | **empty except W4's regenerated plan artefacts**, and W4 must state which side moved and why that side was derived |

Gate 6 is the neighbour check and it is not optional: **a docs fix that breaks a test is
worse than the defect it fixed.** The suite is I/O-bound and silent for minutes under
redirected stdout; healthy runs have been killed for looking hung. Do not kill it. Read
`--junitxml`.

---

## 6 · What this wave will still not have proven

Stated here so no worker has to discover it and no reader is misled:

* **Nothing is applied.** Every plan figure describes an exposure that does not exist.
* **The topic-policy question stays open.** Whether demo-api's four alarms may publish to the
  guard's SNS topic cannot be decided by any `terraform plan`; `evidence/deploy/cost/
  plan-shape.json` records both ARN sets and both outcomes. It stays recorded, not resolved.
* **The sustained-egress assumption stays unobserved.** 1.1 GB/s out of ten 512 MB execution
  environments is what the tariff and the ceiling permit, not what AWS would deliver.
* **`demo_url` and `video_url` stay `UNRESOLVED`.** They are resolved by a person doing a
  thing, and this wave is not that thing.
