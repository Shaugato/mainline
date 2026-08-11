<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# SHIP-FINAL — the demo URL, the public flip, and an honest submission

**Domain implementation plan. Ten workers, strictly disjoint literal paths.**
Lead: deploy-and-submit. Written `2026-08-11`. Deadline `2026-08-18` 17:00 EDT (`2026-08-18T21:00:00Z`).

Everything in §1 was measured **by this lead, today, on this machine, against the live
systems**. Every number names the command that produced it. Where a previously committed
document says otherwise, §1 says so and names the file.

---

## 0 · The two sentences this plan exists to change

Stage One is pass/fail on six requirements. Four are met. Two are not:

1. **The repository is PRIVATE.** `gh repo view --json visibility` → `PRIVATE`.
2. **There is no demo URL.** `docs/submission/SUBMISSION.json` → `"demo_url": "UNRESOLVED"`.

Everything else in this plan is in service of those two, or is the honesty apparatus that
makes it safe to resolve them. **The `UNRESOLVED` token is a feature.** A worker that
writes a value it cannot prove has done more damage than one that leaves the row red.

---

## 1 · GROUND TRUTH — measured today by the lead

### 1.1 CockroachDB Cloud is live, migrated, seeded and role-partitioned

Connected from this machine to `mainline-dev-31219.j77.aws-ap-southeast-1.cockroachlabs.cloud`
with `psycopg`, database `mainline_demo`:

```
connected 2.91 s | mainline_demo | mainline-sql | CockroachDB CCL v26.2.5
  permits              1
  demo permit          1        (dec0de00-0006-4000-8000-000000000001)
  audit relations     14        (information_schema.tables, schema mainline_audit)
  roles                mainline-sql, mainline_api, mainline_auditor,
                       mainline_judge, mainline_migrator, mainline_owner
```

`evidence/deploy/cloud-chain.json` records `files 271 · applied 271 · failed 0 ·
files_that_needed_a_retry 0`, tree fingerprint
`fe27b6208d2281929a9d3c554e4612ac7453bd8f30ae9679ddbe2da7db7a1a15`. That matches the
orchestrator's `chain 271/271 applied, 0 failed`. **The database side of the demo is done.**

One correction to record: `COCKROACH_DSN` in `.env` points at `/defaultdb`, not
`/mainline_demo`. A connection on the committed DSN answers, then fails
`UndefinedTable: relation "mainline.permit" does not exist`. Every applier in this domain
must select the database explicitly rather than trust the DSN's path segment.

### 1.2 Bedrock genuinely executes — I called it, twice, just now

`ap-southeast-2`, profile `mainline-dev`, `boto3` from `.venv`:

```
TITAN  amazon.titan-embed-text-v2:0             → 1024-dim embedding, inputTextTokenCount 4
HAIKU  au.anthropic.claude-haiku-4-5-...-v1:0   → "MAINLINE gate online"
                                                  in 16 / out 8 / total 24
```

Both succeeded. The `ValidationException: Operation not allowed` is gone.

**Therefore `docs/STATE-OF-THE-BUILD.md` lines 400–440 and 614 are STALE and wrong.** They
state that all three Bedrock calls failed, that `authorizationStatus` is `NOT_AUTHORIZED`,
that "every Bedrock code path in this repository is unreachable", and they tell the reader
to go and enable model access. `docs/TOOL-USAGE.md` line 712 says "No live Bedrock
inference transcript is committed." All of that must be corrected **with a committed
transcript**, not with an assertion. This is W10's first job and it is the difference
between "≥1 AWS service, DESIGNED" and "≥1 AWS service, EXECUTED".

### 1.3 The demo's headline beat 404s, and I found the exact line

`evidence/deploy/acceptance.json` says `verdict: NOT PROVEN`, because:

```
POST /v1/demo/gate-run (run 1) returned 404, expected 200
POST /v1/demo/gate-run (run 2) returned 404, expected 200
```

The cause is one omission, not a subtle bug.
`verticals/mainline/apps/demo-api/src/mainline_demo_api/transitions.py:104` declares:

```python
TRANSITION_RESOURCES = {
    "materialise_checks": (...),
    "sign_disposition": (...),
    "merge_permit": (...),
    "suspend_permit": (...),
    "demo_gate_run": (None, None, False),  # <- implemented, line 888
}
```

and `handle_transition` dispatches it at line 966. But
`verticals/mainline/apps/demo-api/src/mainline_demo_api/app.py:120 _routes()` returns
**sixteen** routes, "transcribed from `console/src/data/resources.ts`", and
`POST /v1/demo/gate-run` **is not among them**. The router therefore returns 404 before
the dispatcher is ever reached. The four beats are fully implemented in `gate_run.py`
(SAVEPOINT/ROLLBACK per beat, lines 475–617) and unreachable over HTTP.

`verticals/mainline/apps/console/src/features/gate/DemoDriver.tsx:255` renders the string
*"POST /v1/demo/gate-run is not addressable from this console"* — the console has been
telling the truth about this the whole time.

**This is the single highest-value defect in the repository right now.** One route entry
converts `NOT PROVEN` into a provable demo.

### 1.4 CloudFront cannot be created on this account — the architecture must change

`docs/deploy/RUNBOOK.md:26` records a **real `terraform apply`** run on 2026-08-10 that got
as far as the distribution and was refused by AWS:

```
Error: creating CloudFront Distribution: ... StatusCode: 403,
RequestID: 3e63e30d-8c5b-441b-a01b-b70085eba504, AccessDenied:
Your account must be verified before you can add new CloudFront resources.
```

The same refusal came from a bare `aws cloudfront create-distribution`. The identity holds
`AdministratorAccess`. This is an AWS **account-level verification hold**, liftable only by
AWS Support, on a queue, with seven days left.

I verified today that the partial apply left **no residue**: `aws s3api list-buckets`
returns seven buckets and none carries the `mainline-demo-` prefix; `aws lambda
list-functions --region ap-southeast-1` returns `{"Functions": []}`. Teardown worked.

One claim in that runbook is now false and must be corrected: it says
`aws cloudfront list-distributions` returns `None` and "this account has never had one".
It returns **one distribution**, `E2FCXK8NILPNWF`, `d2hlkr5e2hb7k7.cloudfront.net`,
created 2026-04-16, origin `checkout-platform-debd5edd-site.s3.ap-southeast-2.amazonaws.com`
— a different project's. The hold is on *new* resources, which is a narrower and more
accurate statement than the one on the page.

> **DECISION D1 — the demo URL is a public Lambda Function URL. CloudFront becomes an
> optional upgrade, not a dependency.**
>
> `https://<id>.lambda-url.ap-southeast-1.on.aws` is HTTPS on an AWS-issued certificate,
> needs no account verification, no ACM, no hosted zone, and is inside the Lambda perpetual
> free tier. One origin serves the console SPA **and** `/v1/*`, so there is no CORS, no
> second bucket in the request path, and one hostname in the submission form.
>
> The runbook itself already named this candidate (§⛔ item 3) and left the decision to the
> deploy lead. This is the deploy lead making it.

The two facts that make D1 cheap were confirmed today:
`verticals/mainline/apps/console/vite.config.ts:71` already sets `base: './'` and the app
already uses **hash routing** — `dist/index.html` references `./assets/index-BjAGxrVJ.js`.
A relative-base SPA with hash routes serves correctly from any prefix, including a Lambda
Function URL root, with no rebuild-time host knowledge.

CloudFront stays in the tree behind `var.enable_cloudfront`, default `false`. If Support
lifts the hold before the deadline, flipping one variable and re-applying puts a CDN in
front of the same origin and the URL in the submission form can be updated. If it does not
lift, nothing is blocked. **Nobody is allowed to let CloudFront hold the URL hostage.**

### 1.5 Terraform is valid today, and I ran it

```
$ terraform -chdir=infra/envs/demo init -backend=false   → success, aws v6.58.0
$ terraform -chdir=infra/envs/demo validate               → Success! The configuration is valid.
$ terraform version                                       → v1.14.8 (OpenTofu absent)
```

So the change surface for D1 is small and known: `authorization_type` on
`aws_lambda_function_url` is hard-coded `"AWS_IAM"` at
`infra/modules/demo-api/main.tf:262`, and `infra/envs/demo/main.tf:141` comments that the
**site module owns the hostname**. Both assumptions invert under D1.

### 1.6 Public-readiness has REGRESSED, and it is the gate on the flip

`python scripts/submission/audit_public_readiness.py --json qa/public-readiness.json`,
run by me today:

```
VERDICT NOT READY
failed_checks   ['secrets_tracked', 'secrets_history', 'absolute_paths']
totals          checks 7 · passed 3 · failed 3 · informational 1
                unresolved_findings 105 · allowlisted_findings 60
```

`docs/submission/PUBLIC-READINESS.md` §1 says checks 1, 3, 4 and 6 PASS and only 2 and 7
FAIL. **That table is out of date in the bad direction.** What changed:

| finding | count | why it is new |
|---|---|---|
| `aws_account_id` `022950218246`, literal | **18 tracked files, 37 lines** | introduced by commit `5ddaa3a` (infra, deploy scripts, RUNBOOK, module READMEs) |
| `abs_windows_path` | 33 unresolved (was 14 allowlisted) | new evidence artefacts and new docs quoting `D:\CoackroachDBxAWS\...` |
| `high_entropy_secret` in `docs/deploy/JUDGE-PACK.md:68`, `docs/deploy/cloud-database.md:282`, `scripts/deploy/judge_access.py:13,1143` | 4 | judge/API DSN shapes |

One row **improved**: `repo_state` is now **PASS** — `origin=https://github.com/Shaugato/mainline.git;
branch=master; HEAD=ed4a12f; origin/master=ed4a12f; behind=0 ahead=0; working tree: 0`
modified paths. I confirmed this independently with `git rev-parse HEAD` and
`git rev-parse origin/master` — identical. **The tree that would be published is the tree
on disk.** That was red at the last audit and is green now.

The account id is the interesting one, and it is a **disclosure decision, not a bug**.
AWS account ids are not credentials; they are also not something you scatter for fun. The
honest resolution is neither "redact the evidence" (that is exactly what `docs/HONESTY.md`
refuses) nor "silently allowlist" (that is a scanner weakened for a green). It is:

> **DECISION D2 — split the account id by role.**
> Where the account id is an **executable default** — `EXPECTED_ACCOUNT` in `deploy.sh`,
> a `variables.tf` default, a `backend-config` example — it is **removed** and derived at
> run time from `aws sts get-caller-identity`. Where it is **recorded evidence** — a quoted
> apply refusal, a measured verification block, a committed plan — it **stays**, and it is
> declared in a new `docs/submission/DISCLOSURE-DECISIONS.yaml` with a per-path reason. The
> audit gains a third disposition, `DISCLOSED`, which is non-gating **only** when the path
> is named in that file. An undeclared occurrence stays `UNRESOLVED` and stays red.

That keeps the scanner strictly as strong, removes ~20 of the 37 lines outright, and makes
the remaining publication a decision somebody signed rather than a leak nobody noticed.

### 1.7 The judge credential, and what "rotate" has to mean

`docs/deploy/JUDGE-PACK.md:59-75` publishes host, port, database, user `mainline_judge`,
`sslmode=verify-full`, and says *"The password is not in this repository."* That is true of
the tree. The orchestrator's instruction is that the password **was echoed in a transcript**,
which is a disclosure the tree cannot see. `scripts/deploy/judge_access.py` already has
`--rotate` / `--show-password` and a comment at line 113 recording that a previous rotation
lost the credential. The rotation is therefore mandatory, and the new password must be
**shown once, never written to any tracked file**, and delivered through the submission
form's credentials field.

`evidence/deploy/judge-run.json` shows the 16-question judge pack already ran over the
**Managed MCP channel** against cluster `7cfc9ee9-f9b4-413d-bcad-d81fca2c6c7e`, endpoint
`https://cockroachlabs.cloud/mcp`, with per-question `PASS` verdicts. Managed MCP is
therefore **available**, not absent — `docs/leads/deploy-plan.md` §6 hedged on this and the
hedge can now be resolved in the affirmative, with the artefact.

### 1.8 CI, as GitHub actually reports it

`gh run list --branch master --limit 20`, today:

* `cloud-verify` — **success**, on schedule. This is a real CockroachDB Cloud proof running
  in CI, and it is an asset the submission currently under-claims.
* `demo-health` — failing **every hour** (7 s, 6 s, 9 s…). Correct: there is no deployed
  demo. It must stay red until there is, and go green on its own the moment there is.
* `submission` — red for one precise reason, which I read from the log:
  ```
  REFUSED [RATCHET] metric=non_spdx_spelling.FSL-1.1-ALv2 baseline=1213 measured=1254
  ```
  Forty-one files added by the last wave carry the non-SPDX spelling `FSL-1.1-ALv2` instead
  of `LicenseRef-FSL-1.1-ALv2`. I re-measured locally: **1254**, unchanged.

> **BINDING CONSTRAINT on all ten workers.** Every file you create or edit carries
> `SPDX-License-Identifier: Apache-2.0` (code, scripts, Terraform) or `CC-BY-4.0` (prose,
> evidence JSON), matching the file it sits beside. **Nobody writes `FSL-1.1-ALv2`.** Before
> you finish, run `python scripts/qa/check_reuse.py` and confirm the measured value is
> **still 1254 or lower**. Raising it is a regression you caused. Repairing the 1213→1254
> gap is a repo-wide header sweep and belongs to another domain — see §6.

---

## 2 · THE SHAPE, after D1

```
              ┌──────────────────────────────────────────────────────────┐
 judge  ────► │  https://<id>.lambda-url.ap-southeast-1.on.aws           │  HTTPS, AWS cert
              │  AWS Lambda · python3.13 · authorization_type = NONE     │  ONE origin
              │                                                          │
              │   GET  /                → index.html   (console SPA)     │  from the bundle
              │   GET  /assets/*        → hashed js/css, immutable       │  from the bundle
              │   GET  /bundle/*        → verified EvidenceBundle        │  REPLAY source
              │   GET  /v1/health       → liveness + cluster fingerprint │
              │   GET  /v1/*            → 12 read resources              │  LIVE source
              │   POST /v1/demo/gate-run→ the four beats, one txn, rolled back
              └───────────────────────┬──────────────────────────────────┘
                                      │ pgwire · TLS · same region
                                      ▼
                CockroachDB Cloud Basic · mainline_demo · aws-ap-southeast-1
                     271/271 migrations · 14 mainline_audit views · 6 roles

  OPTIONAL, var.enable_cloudfront = false by default, blocked by an AWS account hold:
              CloudFront ──► S3 (OAC) for /*, Lambda FURL (OAC) for /v1/*
```

Three properties fall out of the single origin and are worth naming because they are what
make this survivable at 3 a.m. on the 18th:

* **No CORS, ever.** Same origin for the SPA and the API.
* **No S3 in the request path.** One resource to be wrong about.
* **REPLAY and LIVE on the same hostname**, the badge read off `transport.describe().mode`,
  which `verticals/mainline/apps/console/src/app/composition.tsx` already constructs. If the
  database is unreachable the console degrades to the signed bundle and *says so on screen*.

### 2.1 The cost, re-checked under D1

| line | basis | USD/month |
|---|---|---|
| Lambda | free tier 1 M req + 400 k GB-s; 512 MB × 300 ms × 10 k req = 1 536 GB-s | 0.00 |
| Lambda Function URL | no charge beyond the invocation | 0.00 |
| CloudWatch Logs | 7-day retention, far under 5 GB free ingest | 0.00 |
| S3 (Terraform state only, under D1) | one small versioned object, native S3 locking | 0.01 |
| SSM Parameter Store | Standard SecureString | 0.00 |
| Bedrock | one seed embedding pass + ~50 tokens/query | 0.01 |
| CockroachDB Cloud Basic | inside the free allowance, `spend_limit` is the hard ceiling | 0.00 |
| CloudFront | **not created** | 0.00 |
| **total** | | **≈ 0.02, worst case < 1.00** |

Removing CloudFront and the site bucket from the request path made the bill *smaller*.
The founder's ceiling is ~USD 5/month; we are two orders of magnitude under it.

### 2.2 What is NOT done by these ten workers

**`terraform apply` is not run.** Workers run `init`, `validate` and `plan`, and commit the
plan. The orchestrator reviews the plan with the founder and performs the apply. Every
artefact these workers produce is therefore *apply-ready*: the bundle is built and hashed,
the console `dist/` is built, the database is seeded, the plan is committed, and
`deploy.sh --dry-run` exits 0 with every prerequisite present.

**The video is not recorded.** W8 produces the script, the timings, the exact commands, the
seeded state and the shot list. The founder films it.

**The visibility flip is not performed.** W9 produces a signed checklist and drives the
audit to exit 0 honestly. The orchestrator flips it. It is irreversible.

---

## 3 · SEQUENCING

| wave | workers | gate to start |
|---|---|---|
| **A — immediately, all parallel** | W1 W3 W6 W7 W9 | none |
| **B** | W2 (needs W1's handler contract), W4 (needs W3's module variables) | W1 / W3 land |
| **C** | W5 (needs W2's bundle + W4's plan), W8 (needs W1 + W2) | W2 / W4 land |
| **D** | W10 (needs W6's AWS evidence, W7's judge facts, W9's audit) | W6 W7 W9 land |

W10 is last on purpose. It is the only worker allowed to write `SUBMISSION.json`, and it
writes each field only after the worker who proved it has landed the artefact.

---

## 4 · THE TEN WORKERS

| # | id | owns, in one line |
|---|---|---|
| 1 | `w1-gate-run-route` | Make `POST /v1/demo/gate-run` addressable; serve the SPA from the handler |
| 2 | `w2-lambda-bundle` | One deterministic, hashed zip: handler + psycopg + console + bundle |
| 3 | `w3-tf-api-public-url` | The Lambda module: public Function URL, its own hostname |
| 4 | `w4-tf-root-and-plan` | The root + site module made optional; `terraform plan`, committed |
| 5 | `w5-deploy-scripts` | One command to the URL; account id from STS; dry-run exits 0 |
| 6 | `w6-live-services` | Cloud chain + seed with a proven 40001 retry; Bedrock transcript |
| 7 | `w7-judge-access` | Rotate `mainline_judge`, prove both directions, MCP snippet, judge pack |
| 8 | `w8-acceptance-and-video` | PROVEN acceptance, hourly health, and the video kit |
| 9 | `w9-public-readiness` | Audit to exit 0 honestly; the disclosure register; the flip checklist |
| 10 | `w10-submission-final` | `SUBMISSION.json`, DEVPOST, RULES-MATRIX, and the AWS correction |

Full briefs are carried in the structured output accompanying this document and are the
authority. This table is their index.

---

## 5 · RISKS

| risk | what is done about it, concretely |
|---|---|
| CloudFront hold never lifts | D1 removes it from the critical path entirely. `enable_cloudfront` defaults `false`. |
| The apply is never approved | Everything short of apply is committed and re-runnable. `demo_url` stays `UNRESOLVED` and the submission says why, on the page, in the form. |
| `40001` on Cloud kills the apply-time seed | W6 proves the retry loop by **fault injection**, not by a clean run that needed none. |
| Judges collide on shared state | The four beats run in one transaction that is rolled back — measured in `evidence/deploy/lead/savepoint-probe-20260810.txt`. Re-proved by W8 with two consecutive runs. |
| The rotated judge password leaks into the tree | W9's scanner runs over W7's output; a credential-shaped value in any tracked file is a red the flip cannot pass. |
| Someone raises `non_spdx_spelling` | Named as a binding constraint; every worker re-measures before finishing. |
| A worker "resolves" a field it cannot prove | Only W10 writes `SUBMISSION.json`, and its `done_when` requires `check_submission_ready.py` to agree row by row. |
| Publishing the account id | D2: declared, per path, with a reason, or removed. Nothing silent. |

---

## 6 · CROSS-DOMAIN NOTES — real, blocking, not mine to fix

1. **`non_spdx_spelling.FSL-1.1-ALv2` is 1254 against a baseline of 1213.** Forty-one files
   spell the identifier `FSL-1.1-ALv2` where REUSE wants `LicenseRef-FSL-1.1-ALv2`. This is
   a repo-wide header sweep across every domain's files and cannot be done inside disjoint
   ownership. It keeps `submission` red. My workers are forbidden to raise it and forbidden
   to lower the baseline.
2. **`COCKROACH_DSN` in `.env` names `/defaultdb`, but the demo lives in `mainline_demo`.**
   Any tool that trusts the DSN's path segment reads an empty database and reports
   `UndefinedTable`. The env file is not in this domain's paths.
3. **`docs/HONESTY.md` still says five unproduced tables.** The chain is 271/271 and the
   orchestrator reports `unproduced (none)`. The page needs its own correction from the
   domain that owns it; W10 must not edit it and will cite it as-is.
4. **The MI ratchet sits at 28/30 invariants** and the custody chain at 7/16 unimplemented.
   Both are true incompleteness counters. The submission text W10 writes must state both
   numbers rather than route around them — an honest 28/30 scores better under
   *Technological Implementation* than a silent 30/30 nobody believes.
5. **`verticals/mainline/demo/judge/PACK.md` names a cluster `mainline-verify` that does not
   exist.** Its source is `QUESTIONS.yaml`, owned by the agents-mcp domain. W7 records the
   discrepancy in the judge pack and does not edit the generator.
