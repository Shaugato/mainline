<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# THE DEPLOY RUNBOOK — clean checkout to a demo URL, and back to nothing

**What this page is.** The one command that produces the demo URL, what each of its ten
stages does, what to do when each one fails, how to remove everything afterwards, and what
it costs — with the arithmetic, not a claim.

**What it is not.** A design document. That is
[`docs/leads/ship-final.md`](../leads/ship-final.md). The Terraform is explained in
[`infra/envs/demo/README.md`](../../infra/envs/demo/README.md), the database in
[`docs/deploy/cloud-database.md`](cloud-database.md).

> **A note on the numbers below.** Everything marked *measured* was produced on this build
> machine against the live systems, and the transcript is quoted or committed. Everything
> else is marked as an estimate. `docs/HONESTY.md` is the standing commitment; this page is
> written to it.

---

## 1 · THE SHAPE — the hostname is a Lambda Function URL

**AWS will not create new CloudFront distributions on this account.** That is an
account-level verification hold, not a bug in this repository, and only AWS Support can
lift it. The full transcript, the `RequestID`, and everything that was tried are in
**[Appendix A](#appendix-a--the-cloudfront-hold-the-evidence-and-the-upgrade-path)**.

This page is written as though **the hold never clears**, because a runbook that assumes a
support queue will answer in time is not a runbook. Everything here works today.

```
              ┌──────────────────────────────────────────────────────────┐
 judge  ────► │  https://<id>.lambda-url.ap-southeast-1.on.aws           │  HTTPS, AWS cert
              │  AWS Lambda · python3.13 · arm64 · auth_type = NONE      │  ONE origin
              │                                                          │
              │   GET  /                → web/index.html  (console SPA)  │  from the package
              │   GET  /assets/*        → hashed js/css, immutable       │  from the package
              │   GET  /bundle/*        → the verified EvidenceBundle    │  REPLAY source
              │   GET  /v1/health       → liveness + cluster fingerprint │
              │   GET  /v1/*            → the read resources             │  LIVE source
              │   POST /v1/demo/gate-run→ the four beats, one txn, rolled back
              └───────────────────────┬──────────────────────────────────┘
                                      │ pgwire · TLS · same region
                                      ▼
                CockroachDB Cloud Basic · mainline_demo · aws-ap-southeast-1
```

Three properties fall out of the single origin, and they are what make this survivable at
3 a.m. on the 18th:

* **No CORS, ever.** The SPA and the API share an origin.
* **No S3 in the request path.** One resource to be wrong about. The console and the
  bundle travel *inside the Lambda package*, which is why stage 0 opens the zip and checks
  for `web/index.html` and `web/bundle/manifest.json` before anything is deployed.
* **REPLAY and LIVE on the same hostname.** The badge is read off
  `transport.describe().mode` at run time, off the object holding the bytes, so it cannot
  disagree with the screen. A build that compiles **both** sources starts LIVE and carries a
  control that switches to REPLAY — one click, same URL, same package, no redeploy — which
  is why there is no longer a `--phase1` deploy mode. Passing `--phase1` now exits 2 and
  explains this; under D1 a deploy with no Lambda has no URL at all, because the Lambda
  **is** the hostname.
  **Corrected 2026-08-14: that switch is a control a reader presses, not an automatic
  degradation.** Nothing swaps transport because a request failed; a failed live request is
  rendered as a failure, verbatim. §7 has the measurement and the reason this distinction
  is load-bearing rather than pedantic.

---

## 2 · The one command

```bash
# Linux / macOS / Git Bash
scripts/deploy/deploy.sh --expect-account <your account id>
```

```powershell
# Windows (this build machine)
pwsh -File scripts\deploy\deploy.ps1 -ExpectAccount <your account id>
```

It ends by printing the URL and the judge access block. If it does not print a URL, it
exited non-zero and said which stage failed and what to do — **there is no path through
this script that prints a URL it did not just fetch over HTTPS.** Stage 7 `GET`s `/`,
asserts `200` and `Content-Type: text/html`, then `GET`s `/v1/health`, asserts `200`, and
asserts that the body names the cluster it is talking to. Only then does anything print.

### Two things it will refuse to do

| | |
|---|---|
| **Touch an AWS account you did not name.** | Supply `--expect-account <id>` or `MAINLINE_AWS_ACCOUNT=<id>`. The flag wins. Neither → exit 3 and nothing happens. `--any-account` is the only override. See § 3. |
| **Run `terraform apply` on its own initiative.** | Stage 6 plans, prints the plan, and stops with **exit 7** unless `MAINLINE_APPLY_APPROVED=1` is in the environment. See § 5.6. |

### The flags that matter

| Flag (bash / PowerShell) | What it does |
|---|---|
| `--dry-run` / `-DryRun` | Preflight the machine, then check every artefact the repository owes. **Writes nothing, anywhere.** Exits non-zero if anything is missing — this is the check, not a preview. |
| `--strict-secrets` / `-StrictSecrets` | With `--dry-run`, also require the operator secrets. Off by default: a clean checkout never has one. |
| `--expect-account <id>` / `-ExpectAccount` | The account this deploy may touch. |
| `--preflight-only` / `-PreflightOnly` | Stage 0 and stop. Answers "is this machine able to deploy at all". |
| `--enable-cloudfront` / `-EnableCloudFront` | Restore the pre-D1 shape. Plans cleanly; will not apply while the hold stands. See Appendix A. |
| `--skip-db`, `--skip-build`, `--recreate-db`, `--arch x86_64`, `--any-account` | as named |

### Exit codes

| | |
|---|---|
| `0` | the URL printed at the end was fetched over HTTPS and proved itself |
| `1` | a stage failed; the message names the stage and what to do |
| `2` | usage error |
| `3` | preflight refused: wrong or unnamed account, missing tool, missing credential |
| **`7`** | **stopped at the approval gate.** Stage 6 planned and did not apply. Nothing created, nothing changed, no URL printed because none exists. **A designed halt, not a failure.** |

---

## 3 · Which AWS account (decision D2)

**No account id is written in any of the four deploy scripts.** `grep -c 0229REDACTED8246`
over `deploy.sh`, `deploy.ps1`, `teardown.sh` and `bootstrap_state.sh` is `0`. The live
account is read at run time:

```bash
aws sts get-caller-identity --query Account --output text
```

and compared against the one you named. **The safety property is unchanged from the version
that hard-coded it: the script refuses to touch an account it was not told to touch, and
`--any-account` is the only override.** What changed is where the id comes from.

```
$ scripts/deploy/deploy.sh                       # nothing named, and this run would write
deploy: stage 0 FAILED
   NOTHING TOLD THIS SCRIPT WHICH AWS ACCOUNT IT MAY TOUCH, so it will not touch one.
   The caller is account <id>. Name it, and this run proceeds:
       scripts/deploy/deploy.sh --expect-account <id>
   or
       export MAINLINE_AWS_ACCOUNT=<id>
exit=3
```

**Two precise exceptions, and they do not weaken it.** `--dry-run` and `--preflight-only`
create, change and delete nothing at all, so there is no account for them to refuse to
touch; with no expectation supplied they *print* the account they can see, state that a
real deploy will refuse without one, and carry on. Supply an expectation that does **not**
match and even those two stop, because at that point you are demonstrably pointed at
something you did not mean. `teardown.sh` behaves the same way.

`bootstrap_state.sh` goes one step further: run it with no `--bucket` at all and it derives
`mainline-demo-tfstate-<account id>` from the caller identity. That is the only place the
account id ever appears in a resource name, and it is never typed by a human.

---

## 4 · Prerequisites

### Tools — measured on this machine, 2026-08-11

| Tool | Needed | Here | Checked by |
|---|---|---|---|
| AWS CLI | **v2** | `aws-cli/2.32.21` | stage 0, with a major-version assertion |
| Terraform | **≥ 1.10** | `v1.14.8` | stage 0, with a version comparison |
| Python | **3.13** in `.venv` | `3.13.14` at `.venv/Scripts/python.exe` | stage 0, with a minor-version assertion |
| Node | 20+ | `v24.14.0` | stage 0 |
| pnpm | any | `11.5.3` | stage 0 |
| curl | any | `curl 8.14.1` (`C:\Windows\System32\curl.exe`) | stage 0 |
| Git Bash | any | `C:\Program Files\Git\bin\bash.exe` | stage 0 (**PowerShell only**) |

**Terraform ≥ 1.10 is not negotiable.** `use_lockfile = true` — native S3 state locking —
arrived in 1.10, and this stack has deliberately no DynamoDB table to fall back to.

**Python 3.13 exactly is not negotiable either.** The Lambda runtime is `python3.13` and
`build_lambda.sh` downloads `cp313` wheels; building the package with a different minor
version produces a zip that imports here and fails on Lambda.

**`uv` is not installed on this machine.** Every `just` recipe that shells out to `uv run`
is dead here. Every script in `scripts/deploy/` therefore calls `.venv/Scripts/python.exe`
by name.

**A fresh clone has no `.venv`, no `node_modules`, no `dist/` and no `out/`** — all four are
gitignored. §5.6.0 is the ordered walk that creates them, and it is the section to read if
you have just cloned this repository and want the plan.

### How to clone this repository on Windows

```bash
git clone --config core.longpaths=true --config core.autocrlf=false \
    https://github.com/Shaugato/mainline.git
```

Neither flag is decoration. Without `core.longpaths` a clone into a long parent directory
prints **"Clone succeeded, but checkout failed"**, exits `128`, and leaves a tree that
`terraform validate` is perfectly happy with — the measurement, and the guard that refuses
it, are in §5.6.0 step 0. Without `core.autocrlf=false` the checkout can convert `.tf` files
to CRLF, which changes no resource count and does change the bytes of every regenerated plan
artefact.

### The Git Bash trap, on Windows — measured

`deploy.ps1` needs Git Bash for stage 1, and it will not use the `bash` on `PATH`:

```
PS> bash -c "uname -a; command -v aws || echo 'NO AWS IN THIS BASH'"
Linux AetherX 6.6.87.2-microsoft-standard-WSL2 ...
NO AWS IN THIS BASH

PS> & "C:\Program Files\Git\bin\bash.exe" -c "uname -o; command -v aws"
Msys
/c/Program Files/Amazon/AWSCLIV2/aws
```

`bash` on `PATH` is `C:\WINDOWS\system32\bash.exe` — **WSL**. A different machine, a
different filesystem, and no AWS CLI. `deploy.ps1` searches for a Git Bash specifically,
verifies `uname -o` says `Msys`, and refuses with that explanation rather than letting the
confusion propagate. `$env:MAINLINE_BASH` overrides the search.

### Credentials and secrets

| | |
|---|---|
| `AWS_PROFILE` | `mainline-dev` by default. The **account** is asserted separately; see § 3. |
| `COCKROACH_DSN` | Admin DSN. Read from the repo-root `.env` if not exported. Needed by stage 3. |
| `MAINLINE_API_DSN` | The Lambda's DSN — `COCKROACH_DSN` with the userinfo swapped for `mainline_api`. Needed by stage 2. |
| `MAINLINE_API_PASSWORD` | Alternative to the above: stage 2 derives the DSN itself. |
| `MAINLINE_APPLY_APPROVED` | `1` opens the stage-6 apply gate. Nothing else does. |

Mint the login password once and capture it — it is printed once and never stored:

```bash
.venv/Scripts/python.exe scripts/deploy/cloud_roles.py --rotate
```

Then, in PowerShell:

```powershell
$env:MAINLINE_API_PASSWORD = '<the mainline_api password>'
```

**No script in `scripts/deploy/` ever prints a DSN or a password.** `deploy.sh` refuses to
run under `set -x` for that reason, and stage 2 builds its SSM payload in a `0600` temp
file so the DSN never enters an argument vector, `ps` output, or shell history.

> **`COCKROACH_DSN` in `.env` names `/defaultdb`, and the demo lives in `mainline_demo`.**
> Every program in this domain selects the database explicitly rather than trusting the
> DSN's path segment — stage 2 rewrites the path, stage 0's Cloud probe overrides it, and
> stage 7 asserts that `/v1/health` reports `mainline_demo`. A tool that trusts the path
> reads an empty database and reports `UndefinedTable`.

---

## 5 · The ten stages

### 5.0 · Preflight, and `--dry-run`

Identity, tool versions, interpreter, and whether the DSNs are available. Prints the
account id and the DSN's **host** — never the DSN.

`--dry-run` then checks every artefact the repository owes, in two classes, and **the
distinction is deliberate**:

* **ARTEFACT** — something this repository owes. A stranger cloning the repo either has it
  or does not. **Gated**: a missing one exits non-zero.
* **OPERATOR** — a secret a human mints. A clean checkout *never* has one, so gating on it
  by default would make `--dry-run` permanently red for exactly the person it is meant to
  serve. Reported always; gated by `--strict-secrets`.

The gated list, in the order it runs:

| | checked | owed by |
|---|---|---|
| terraform | root `main.tf`, `variables.tf`; `var.enable_cloudfront` is declared | `w4-tf-root-and-plan` |
| terraform | `infra/modules/demo-api` emits `output "function_url"` | `w3-tf-api-public-url` |
| terraform | the SSM parameter name in `deploy.sh` equals `var.dsn_parameter_name`'s default | both |
| terraform | `docs/deploy/terraform-plan.md` — the committed plan the orchestrator reviews | `w4-tf-root-and-plan` |
| package | the zip and its `.json` manifest exist | `w2-lambda-bundle` |
| package | the manifest's `sha256` matches the zip **on disk, byte for byte** | `w2-lambda-bundle` |
| package | the manifest's `architecture` matches `--arch`; `runtime` is `python3.13` | `w2-lambda-bundle` |
| package | the zip carries `web/index.html` and `web/bundle/manifest.json` | `w2-lambda-bundle` |
| package | the manifest's `web_root` agrees with the module default `/var/task/web` | `w2-lambda-bundle` |
| site | the console `dist/` is built; the EvidenceBundle manifest exists | `w1`, `w2` |
| programs | `cloud_chain.py`, `seed_demo.py`, `capture_demo_bundle.py`, `build_lambda.sh`, `demo_acceptance.py`, `bootstrap_state.sh`, `teardown.sh` | various |
| live | `aws ssm describe-parameters` answers for `/mainline/` | — |
| live | CockroachDB Cloud answers **as `mainline_demo`** and carries a schema attestation | `w6-live-services` |

The last two are real network calls and they are **read-only**: one `describe-parameters`,
one `SELECT`. Nothing is written by a dry run, anywhere, ever.

**Why the package checks are worth their weight.** Under D1 the zip is the entire
deployable. A package missing `web/index.html` deploys cleanly, answers `/v1/health` with a
green `200`, and **404s the URL a judge opens** — because `static_site.resolve()` will not
fall back to `index.html` under `/assets/` or `/bundle/`. That is the single most expensive
failure available to this project and it costs one `zipfile.namelist()` to prevent.

The verbatim transcript of a passing run, a run with the zip renamed away, and a
`--strict-secrets` run are committed to
[`evidence/deploy/deploy-dry-run.json`](../../evidence/deploy/deploy-dry-run.json), with
exit codes `0`, `1` and `3` respectively.

### 5.1 · State backend

> ## ⚠ THIS IS THE FIRST MUTATING ACTION OF THE WHOLE DEPLOY
>
> Everything before this line — stage 0, `--dry-run`, `--preflight-only`, and the entire plan
> reproduction in §5.6.1 — creates, changes and deletes nothing. `bootstrap_state.sh` without
> `--print-backend-config` calls `s3api create-bucket`, `put-bucket-versioning`,
> `put-bucket-encryption`, `put-bucket-tagging` and `put-bucket-lifecycle-configuration`
> (`scripts/deploy/bootstrap_state.sh:194–262`). Those write.
>
> **It belongs to the orchestrator, with the founder — the same pair who authorise the apply.
> No worker runs it,** and no agent runs it on the strength of a document telling it to.
>
> `--print-backend-config` is the mode that is always safe: the script documents at line 92
> that it makes **zero** AWS calls, and it prints the exact `-backend-config` line without
> touching anything.

`scripts/deploy/bootstrap_state.sh` creates `mainline-demo-tfstate-<account>` if absent and
re-asserts its configuration every run. Measured, first run:

```
bootstrap_state
  account        <account id>
  region         ap-southeast-1
  bucket         mainline-demo-tfstate-<account id>   (derived from sts get-caller-identity)
  exists         no — creating
  created        ok
  versioning     Enabled
  public         blocked (all four)
  encryption     SSE-S3 (AES256)
  tags           project=mainline, mainline:role=terraform-state
  lifecycle      noncurrent versions expire after 30 days
```

It **refuses a bucket name outside the `mainline-demo-` prefix** (exit 2), before making
any AWS call, because `teardown.sh` keys its own refusal on that prefix — a state bucket
named anything else would be created here and then be undeletable by our own tools.

**If it fails:** a `403` on `head-bucket` means the name is taken by another AWS customer
(S3 bucket names are global). Choose another name and pass `--state-bucket`. Do not retry.

### 5.2 · The secret

`aws ssm put-parameter --type SecureString --overwrite` writes the Lambda's DSN to
`/mainline/demo/cockroach_dsn`. The payload goes in via `--cli-input-json file://…` from a
`0600` temp file removed in a trap, so the value never enters an argument vector. It is
read back **without** `--with-decryption` — only the type is asserted, so the script cannot
print the value even by accident.

**Terraform never sees this value.** It is given the parameter *name*; the Lambda role is
granted `ssm:GetParameter` + `kms:Decrypt` on that one ARN; the handler reads it once per
cold start from `$MAINLINE_DSN_PARAM` and caches it. `terraform show` cannot print a
password Terraform never held.

**If it fails:** the IAM identity needs `ssm:PutParameter` and `kms:Encrypt` on
`alias/aws/ssm`.

### 5.3 · The database

`cloud_chain.py` then `seed_demo.py`, both idempotent, both against CockroachDB Cloud.

| `cloud_chain.py` exit | Meaning | What to do |
|---|---|---|
| `0` | applied, or already correct and unchanged | nothing |
| `3` | **refused** — the migration tree or the live schema drifted from the fingerprint in `trappoint.deploy_chain` | re-run with `--recreate-db`; nothing was changed |
| other | a migration failed | its output names the file and the SQLSTATE |

Exit 3 is a feature. Migrations here are forward-only and are not written
`IF NOT EXISTS`; replaying them over a live database produces a wall of `42P07` that says
nothing about whether the schema is right. *A deploy tool that cannot tell "already
correct" from "differently wrong" should say so and stop.*

**If a file fails with `40001`:** it should not — every applier retries `40001` with
backoff. If one still surfaces, re-run; the chain is idempotent.

### 5.4 · The Lambda package

`scripts/deploy/build_lambda.sh --arch arm64 --out out/lambda/mainline-demo-api-arm64.zip`.
arm64 is the default: ~20 % cheaper per GB-second, and `psycopg-binary` 3.3.4 publishes a
`cp313` aarch64 wheel.

**The architecture in the filename and in `-var lambda_architecture` must agree.** The
deploy script drives both from one `--arch` flag precisely because a mismatch is a clean
plan, a clean apply, and an `ELFCLASS` error on the first request — which reads like a
database problem and is not.

The stage then re-runs the same package assertions `--dry-run` runs, on the zip that was
just built, and refuses to hand a package to Terraform whose contents it cannot state.

### 5.5 · The site payload — optional under D1

The console is built (`pnpm install --frozen-lockfile && pnpm run build`) and
`capture_demo_bundle.py` refreshes the verified EvidenceBundle. **Both still happen**,
because stage 4's zip is built from them.

What does *not* happen under D1 is the upload: there is no S3 bucket in the request path,
so nothing is synced anywhere. `--enable-cloudfront` re-enables the upload, with explicit
content types (see Appendix A for why that mattered).

**If `capture_demo_bundle.py` is missing, the deploy FAILS.** It is not skipped and not
faked. There is no way to forge that file and none is attempted.

### 5.6 · Infrastructure — plan always, apply only behind the gate

`terraform init -reconfigure -backend-config=…`, then `terraform plan -out=<tmp>` with:

```
-var aws_region=…            -var enable_api=true
-var dsn_parameter_name=…    -var enable_cloudfront=false      ← D1
-var name_prefix=…           -var lambda_package_path=…  -var lambda_architecture=…
```

Then **the gate**:

```
STOPPED AT THE APPROVAL GATE — stage 6 planned, and did not apply.

   Nothing was created. Nothing was changed. No URL was printed, because none exists.
   THIS IS NOT A FAILURE. It is the designed halt, and it exits 7 so that neither a human
   nor a CI job can mistake it for a completed deploy.

   The plan above is the one the orchestrator reviews with the founder. The reviewed copy
   lives at:

       docs/deploy/terraform-plan.md

   To proceed once it is approved:

       MAINLINE_APPLY_APPROVED=1 scripts/deploy/deploy.sh --expect-account <id>
```

> **This gate is a feature of the script, not a scaffold, and it is not removed when the
> demo ships.** `terraform apply` is the one irreversible, billable step in ten stages. The
> script therefore cannot apply on its own initiative: the environment has to say so, once,
> deliberately, by a human who has read the plan. Stages 1 to 5 are idempotent, so the
> approved run repeats them cheaply and picks up exactly here.
>
> `deploy.sh` contains **exactly one** executable `terraform apply`, and it is unreachable
> unless `MAINLINE_APPLY_APPROVED=1`. `deploy.ps1` is the same shape. Both print the gate's
> state — `OPEN` or `CLOSED` — during preflight, on every run, before anything happens.

The apply, when approved, applies **the saved plan file**, not a fresh one. What the
founder reviewed is what runs.

**If it says the state is locked:** see § 7.

---

#### 5.6.0 · From `git clone` to `Plan: 24 to add` — the ordered walk, measured end to end

**A runbook that only works on one workstation is not a runbook.** Everything below was
walked on 2026-08-14 from a genuinely fresh `git clone` of `github.com/Shaugato/mainline`
at `master` = **`7535670`**, into a directory that had never held this repository, on a
machine holding no `out/`, no `dist/`, no `node_modules/` and no `.venv/`. Every exit code
quoted is the shell's `$?` for that command, read immediately after it and never from the
tail of a pipeline. The full transcript is
[`evidence/deploy/lead/plan-repro-fresh-clone.json`](../../evidence/deploy/lead/plan-repro-fresh-clone.json).

**Why this section exists at all: the plan reads two build outputs that a clone does not
have.** `infra/modules/demo-api/main.tf:342` calls `filebase64sha256(var.package_path)`,
which Terraform evaluates at **plan** time, not at apply time. So the deployment zip must
exist before `terraform plan` — and the zip is built from `verticals/mainline/apps/console/dist/`,
which is itself a build output. `out/` and `dist/` are both gitignored
([`.gitignore:9,10`](../../.gitignore)). Before this section was written, a fresh clone got
as far as rendering the **whole** plan diff and then died inside `filebase64sha256`, which
reads as a Terraform bug rather than as a missing build.

##### Step 0 — clone, and check that the clone is complete

```bash
git clone --config core.longpaths=true --config core.autocrlf=false \
    https://github.com/Shaugato/mainline.git mainline
cd mainline
```

> ### ⚠ On Windows, `git clone` can print "Clone succeeded" and leave you a tree that is not this repository
>
> Measured on TRAPPOINT, 2026-08-14, cloning `7535670` into a 125-character parent directory
> **without** `core.longpaths`:
>
> ```
> error: unable to create file skills/upstream/…/verify_restore_merkle_root.py: Filename too long
> fatal: unable to checkout working tree
> warning: Clone succeeded, but checkout failed.
> ```
>
> | question | answer |
> |---|---:|
> | `git clone` exit code | `128` |
> | paths in `HEAD` | 7,577 |
> | paths **absent from the working tree** | **2** |
> | `git ls-files --deleted` | **0** ← a confident wrong answer |
> | `git ls-files \| wc -l` (the index) | **0** ← never written |
> | `git status --short` rows | 7,613 ← over-reports; a detector, not a census |
> | missing under `infra/` | **0** |
> | missing under `scripts/deploy/` | **0** |
> | missing under `evidence/deploy/` | **0** |
> | missing under `docs/deploy/` | **0** |
>
> **Read the last four rows.** Every path Terraform reads was present, so
> `terraform init -backend=false` and `terraform validate` both **succeed** on that tree — a
> reviewer gets a green tick from something that is not this repository. And the obvious
> detector, `git ls-files --deleted`, answers **zero**, because the aborted checkout left the
> index empty and `--deleted` compares the working tree against the index.
>
> **`plan_repro.sh` stage 0 refuses this by name, with exit 11, before Terraform or the AWS
> CLI is invoked.** It takes its census from `git ls-tree -r HEAD` — the one list a failed
> checkout cannot corrupt, because the object transfer succeeded — and diffs it against the
> filesystem. Both of its branches are demonstrated firing in the evidence file: the
> empty-index branch against the real truncated clone, and the missing-paths branch against a
> complete clone with two `.tf` files moved aside.

Do not take the guard on trust; it costs a second:

```bash
scripts/deploy/plan_repro.sh --prove-truncation-refusal <a directory holding a bad checkout>
#   verdict   REFUSED with exit 11   [ok — the truncated-checkout guard fires]
```

`--config core.autocrlf=false` changes **no resource count** — it is there so that a
regenerated plan artefact is byte-comparable with the committed one. This repository ships
no `.gitattributes` and Git for Windows sets `core.autocrlf=true` at **system** level, so
without it a clone can convert `.tf` files on checkout and every regenerated
`terraform show -json` differs in its embedded `description` heredocs for a reason that is
not a drift. Stage 0 measures the conversion with `git ls-files --eol` and reports it; it
does not refuse it.

##### Step 1 — build the console, **in `demo` mode**

```bash
cd verticals/mainline/apps/console
pnpm install --frozen-lockfile          # exit 0
pnpm exec vite build --mode demo        # exit 0  → dist/, 49 files
cd ../../../..
```

> **`--mode demo` is load-bearing and `pnpm run build` is not a substitute.** Measured on
> the fresh clone: `pnpm run build` succeeds, produces a `dist/`, and `build_lambda.sh` then
> prints its own detector's verdict on it —
>
> ```
> build_lambda: console   WARNING this dist/ carries neither VITE_MAINLINE_API_BASE nor
> build_lambda: console           VITE_MAINLINE_BUNDLE_URL (import.meta.env MODE=production). The site
> build_lambda: console           loads and then renders NO SOURCE on every surface. It is a
> build_lambda: console           website with no data.
> ```
>
> The demo-mode build reads `verticals/mainline/apps/console/.env.demo`, which is tracked, and
> the same detector then prints `VITE_MAINLINE_BUNDLE_URL=./bundle/`. **A judge opening a
> production-mode build sees a site that loads and shows nothing** — the most expensive
> failure available to this project, and it is one flag.
>
> `scripts/deploy/deploy.sh:879` runs `pnpm run build`. That is the deploy script's line and
> not this page's to change; it is reported to its owner in the evidence file. **The
> authority here is the artefact check, not the command** — `build_lambda.sh` inspects the
> `dist/` it is handed and says what is in it, and a command that produces a `dist/` the
> checker objects to is the command that is wrong.

> **THE ARTEFACT CHECK WAS WEAKER THAN THIS PARAGRAPH READS. MEASURED 2026-08-14.**
> The transcript above is real and reproduces — but it only reproduces for a
> **production-mode** build, and understanding why is the whole finding.
>
> `probe_console()` collected the compiled literals **keyed on the variable NAME, with no
> test on the VALUE** (`found.setdefault(key, value)`). `pnpm run build` reads no `.env`
> file at all — this console has `.env.demo` and no `.env` — so neither key is inlined,
> `found` is empty, and the warning fires, exactly as printed. A `--mode demo` build reads
> `.env.demo`, which declares `VITE_MAINLINE_API_BASE=` **empty on purpose**, so Vite
> inlines `VITE_MAINLINE_API_BASE:""`, `found` is never empty, and the warning branch is
> **unreachable**. The branch was live for the build nobody ships and dead for the build
> everybody ships.
>
> That is not hypothetical. The artefact on the demo URL was packaged that way and served a
> REPLAY console over a live kernel; the compiled literals are in
> [`console-build.md`](console-build.md) §7.1, extracted from the JavaScript the URL
> actually serves. The packer now takes a **required** `--console-transport live|replay|both`
> and **refuses** a `dist/` that does not match the declaration, rather than printing a line
> about it ([`console-build.md`](console-build.md) §7.3). **Treat the warning above as a
> historical transcript, not as the guard.** The guard is the refusal.

##### Step 2 — the evidence bundle is already in the clone; do not re-capture it to read a plan

`build_lambda.sh` reads `verticals/mainline/apps/console/fixtures/bundles/demo-cloud/`, and
that directory is **tracked** — 26 files at `7535670`, present in any complete clone.
`capture_demo_bundle.py` (§5.5) *refreshes* it against CockroachDB Cloud and is a **deploy**
step; it needs a Cloud DSN and it is not needed to reproduce a plan. The zip's bytes reach
the plan as exactly one value, `source_code_hash`, and change no resource count.

##### Step 3 — an interpreter for the build

A fresh clone has no `.venv`. `build_lambda.sh` looks for `.venv/Scripts/python.exe`, then
`.venv/bin/python`, then `python3`/`python` on `PATH`. **Give it a CPython 3.13** — §4 says
why — by making the repository's own venv:

```bash
python3.13 -m venv .venv          # Windows: py -3.13 -m venv .venv
```

On this build machine the 3.13 is registered with the launcher as
`-V:Astral/CPython3.13.14` rather than as `-3.13`, so `py -3.13` answers *"No suitable
Python runtime found"* and the base interpreter has to be named directly. **That is a
property of this machine, not of the repository**, which is why the step is written as
"any CPython 3.13" and not as a path.

##### Step 4 — build the deployment package

```bash
scripts/deploy/build_lambda.sh --arch arm64        # exit 0, ~8 s with a warm wheelhouse
```

It downloads two wheels from PyPI on the first run (`psycopg`, `psycopg-binary`, both
`cp313`, both `--only-binary=:all:` for the `manylinux_2_28_aarch64` tag), stages them,
copies in the handler, the console `dist/` and the evidence bundle, strips source maps,
writes the `.gz` siblings, packs reproducibly, and then re-opens the finished zip with
`bundle_manifest.py --strict`, which printed `VERDICT PASS`.

##### Step 5 — the plan

```bash
scripts/deploy/plan_repro.sh --out-dir <a directory OUTSIDE the repository> --json
```

Read §5.6.1 for what that script is and what it refuses. On the fresh clone it exited **0**
— 79 s on the first run, which downloads `hashicorp/aws v6.58.0` and `hashicorp/archive
v2.8.0` into `.terraform/`, and 50 s on a re-run once they are cached — and printed:

```
  fresh plan             Plan: 24 to add, 0 to change, 0 to destroy.
  committed artefact     evidence/deploy/terraform-plan-furl.txt  says Plan: 24 to add
```

`scripts/deploy/plan_repro.sh --cloudfront` on the same clone exited **0** at
`Plan: 35 to add, 0 to change, 0 to destroy.`, also agreeing with its committed artefact.

##### The walk, as one table

| # | Command | Exit | What it produced |
|---:|---|---:|---|
| 0 | `git clone --config core.longpaths=true --config core.autocrlf=false …` | `0` | 7,577/7,577 files, `git status --short` empty |
| 0a | `plan_repro.sh --prove-refusal` | `0` | seven mutating subcommands refused, seven exits of 2 |
| 0b | `plan_repro.sh --prove-truncation-refusal <bad checkout>` | `0` | the stage-0 guard demonstrated refusing with 11 |
| 1 | `pnpm install --frozen-lockfile` | `0` | `node_modules/` |
| 2 | `pnpm exec vite build --mode demo` | `0` | `dist/`, 49 files |
| 3 | `python3.13 -m venv .venv` | `0` | an interpreter for step 4 |
| 4 | `scripts/deploy/build_lambda.sh --arch arm64` | `0` | `out/lambda/mainline-demo-api-arm64.zip`, `VERDICT PASS` |
| 4a | the same, with the zip moved aside | **`10`** | the stage-2b refusal, before `backend_override.tf` is written |
| 5 | `scripts/deploy/plan_repro.sh --out-dir <outside> --json` | `0` | **`Plan: 24 to add, 0 to change, 0 to destroy.`** |
| 5b | `scripts/deploy/plan_repro.sh --out-dir <outside> --cloudfront` | `0` | `Plan: 35 to add, 0 to change, 0 to destroy.` |

Rows 0a, 0b and 4a are in the walk because they **refused**. A guard that has never been
seen refusing is a comment; each of those three costs a second or two and is the reason the
rows above them can be believed.

**Residue after all of it:** `git status --porcelain` in the clone listed exactly the one
file this worker had overlaid and nothing else; `infra/envs/demo/backend_override.tf` was
absent and `infra/envs/demo/.terraform/terraform.tfstate` was absent, both removed by the
script's `EXIT` trap. **No `terraform apply` appears anywhere in the walk**, and
`aws lambda get-function --function-name mainline-demo-api` still answers
`ResourceNotFoundException`.

**What steps 1–4 do NOT change.** The zip's bytes reach the plan as one value,
`source_code_hash`. They do not change the resource count, so a plan built from a different
package is still `Plan: 24 to add` — and it is *not* byte-identical to the committed
artefact. §5.6.1's exit 6 is about the **count**; artefact bytes are
[`docs/deploy/terraform-plan.md`](terraform-plan.md) §1's subject.

---

#### 5.6.1 · Reproducing the plan with no mutating AWS call

**The founder must approve the plan that will actually run, and until 2026-08-14 that plan
was unreproducible on a clean checkout.** `infra/envs/demo/backend.tf` declares a **partial**
S3 backend: key, region, `encrypt`, `use_lockfile` — and no bucket, because an S3 bucket name
must be globally unique across every AWS customer and therefore cannot be a constant in a
repository anybody can clone. So `terraform init` alone cannot complete;
`terraform init -backend=false` completes but leaves `plan` refusing with *"Changes to
backend configurations require reinitialization"*; and the only documented way to get a real
bucket is §5.1, which **writes**. Reading the plan required a mutating call first, which is
backwards.

One command, read-only, on a clean checkout:

```bash
scripts/deploy/plan_repro.sh                 # the shipping plan (enable_cloudfront = false)
scripts/deploy/plan_repro.sh --cloudfront    # the enable_cloudfront variant
scripts/deploy/plan_repro.sh --json          # also emit `terraform show -json`
```

It needs **read-only AWS credentials** — a plan is not credential-free, because the root
reads `data.aws_caller_identity.current` — and it needs the Terraform and AWS CLI versions in
§4. It writes the plan text to a directory **outside the repository** and refuses an
`--out-dir` inside it.

**THE PROCEDURE, AND THE FACT IT RESTS ON, IN ONE PARAGRAPH.** The script points Terraform at
a **local** backend — a `backend_override.tf` it writes into `infra/envs/demo` and removes in
a trap on *any* exit — whose state file lives outside the repository and starts empty; it then
runs `terraform init -reconfigure`, `terraform validate` and `terraform plan`. That is a
faithful reproduction of the shipping plan **only because nothing has been applied: the remote
S3 state is empty, an empty local state and an empty remote state hold the same zero
resources, and a plan is a function of the configuration plus the state — so the same
configuration against the same empty state produces the same plan. THAT EQUIVALENCE EXPIRES AT
THE FIRST `terraform apply`.** From the moment one resource exists in the remote state, a plan
against an empty local state reports creating resources that already exist, and every count it
prints is wrong in the direction that reads like success. After the first apply the only
correct plan is the one against the real backend, §5.6.2 below.

**The expiry is measured, not merely promised.** Stage 2 of the script asks AWS three
read-only questions on every run — does any `mainline-demo-tfstate-*` bucket exist
(`s3api list-buckets`); if one does, does it hold `demo/terraform.tfstate`
(`s3api head-object`); and, independently of any bucket name, does the demo Lambda already
exist (`lambda get-function`) — and it **refuses with exit 5** if any of them says the stack
has been applied, or if any of them cannot be answered, because *"I could not tell"* is not
*"the state is empty"*. The third question is the one that closes the hole in the first two:
an operator who bootstrapped a non-default bucket name would pass them for the wrong reason.

> **One residue to know about.** `backend_override.tf` is **not** in `.gitignore`. The script
> refuses to start if one already exists — it will not clobber somebody else's — and removes
> its own in a trap on any exit, including a failed plan; the 2026-08-14 run left
> `git status -- infra/envs/demo` byte-identical to what it found. But a hard-killed process
> runs no trap, and a committed `backend_override.tf` would silently point every clone's
> Terraform at a local state file. **After an interrupted run, check `git status` before you
> commit.**

Measured on this machine, **2026-08-14**. The account id is masked and the absolute scratch
paths are replaced by their meaning; every other byte, and the order of every line, is as the
script printed it:

```
plan_repro — reproducing the shipping plan with no mutating AWS call

== 1 · identity (read-only)
  caller                 arn:aws:iam::<account>:user/mainline-dev
  region                 ap-southeast-1
  profile                mainline-dev

== 2 · the empty-state equivalence, measured read-only
  state buckets          none — no mainline-demo-tfstate-* bucket in this account
  lambda mainline-demo-api does not exist   [equivalence holds]

  NOTHING HAS BEEN APPLIED, so the remote S3 state is empty, so a plan against an
  empty LOCAL state is resource-identical to a plan against the empty remote state.
  THIS EQUIVALENCE EXPIRES AT THE FIRST APPLY, and stage 2 re-measures it every run.

== 3 · a local backend, outside the repository, starting empty
  override               infra/envs/demo/backend_override.tf  (removed on exit, any exit)
  state path             <scratch>/demo-plan.tfstate
  state now              absent/empty

== 4 · terraform init -reconfigure / validate / plan
  init                   ok   (<scratch>/init-furl.log)
  validate               Success! The configuration is valid.
  plan                   ok   (<scratch>/terraform-plan-furl.txt)

== 5 · the plan, and the committed artefact
  fresh plan             Plan: 24 to add, 0 to change, 0 to destroy.
  committed artefact     evidence/deploy/terraform-plan-furl.txt  says Plan: 24 to add
  G6 reservation         reserved_concurrent_executions = -1
  G7 zero-mask           0 occurrence(s) of twelve zeros   (expected 0)
  account id             12 occurrence(s) in the RAW plan text — mask before it enters evidence/

  The plan the founder would approve is Plan: 24 to add, and the committed
  artefact agrees. No AWS resource was created, changed or deleted by this run.
  Raw plan (UNMASKED account id): <scratch>/terraform-plan-furl.txt
exit=0
```

`exit=0` is the shell's report of the script's status, not a line the script prints.

**It cannot apply, and that is a mechanism rather than a promise.** Every Terraform
invocation in the script passes one wrapper carrying an allowlist of `init`, `validate`,
`plan`, `show`, `version`; `apply`, `destroy`, `import`, `state`, `taint`, `force-unlock` and
`plan -destroy` are refused by name, before `terraform` is executed. Both refusals are
falsifiable in about a second:

```bash
scripts/deploy/plan_repro.sh --prove-refusal
#   terraform apply        REFUSED, exit 2   [ok]      … seven of these, then:
#   Seven refusals, seven exits of 2. The allowlist is: init validate plan show version

scripts/deploy/plan_repro.sh --prove-expiry-refusal <a function that exists> --region <its region>
#   plan_repro: THE EQUIVALENCE HAS EXPIRED — the Lambda '…' already exists in …
#   verdict                REFUSED with exit 5   [ok — the expiry guard fires]
```

**Two traps this script exists to have already stepped in, both measured here.**

* **The two halves must be the same identity.** The first version proved an identity with
  `aws --profile mainline-dev` and then let Terraform resolve its own credentials. On this
  machine no `AWS_*` variable is set, so the provider fell through to the default chain and
  `plan` died on `InvalidClientTokenId: The security token included in the request is
  invalid` — *after* printing a plausible output diff. The profile is now exported, and
  static keys alongside a profile are refused rather than ranked, because the CLI would
  honour the profile and the provider would honour the keys.
* **The raw plan contains the AWS account id, and a correct plan always will.** Twelve
  occurrences in the FURL plan, nineteen in the CloudFront one — `data.aws_caller_identity`
  puts them there. Zero is a property of the **committed, masked** artefact
  (`docs/deploy/terraform-plan.md` §1.2), never of the raw output. The script counts them and
  says so; it does not mask the file, because a file described as verbatim should not be
  quietly rewritten on its way to disk.

**If it exits 6, the committed artefact is stale — regenerate the artefact, never the
number.** **This page used to say `plan_repro.sh --cloudfront` exits 6 today.** Re-measured
on 2026-08-14 from the fresh clone of `7535670`, it exits **0** at `Plan: 35 to add, 0 to
change, 0 to destroy.` and the committed CloudFront artefact agrees. The sentence was true
when it was written — the artefact then recorded `Plan: 22 to add` and predated the
`cost-guard` instantiation at `infra/envs/demo/main.tf:631` — and it has since been
regenerated. It is corrected here against a measurement rather than deleted, because *the
plan is the fact and the artefact is the record*: the artefact moved to the plan, which is
the only direction that is ever allowed.

**The other exits worth knowing before you meet them.** `10` is the gitignored deployment
zip missing — §5.6.0 step 4 is the fix, and the check exists because without it the run
renders the entire plan diff and then dies inside `filebase64sha256`. `11` is a checkout
that is not a complete copy of this repository — §5.6.0 step 0, and it is the one refusal
on this page that fires *before* any AWS call, because it costs nothing and because
`terraform validate` is green on a truncated clone.

---

#### 5.6.2 · The real S3 backend — the path the founder applies from

This is the path for the actual deploy, and it is the *only* correct path once anything has
been applied. In order:

1. **Get the backend line.** Read-only; §5.1's script makes zero AWS calls in this mode.

   ```bash
   scripts/deploy/plan_repro.sh --print-backend-config
   # or:  scripts/deploy/bootstrap_state.sh --print-backend-config --bucket <name>
   #
   #   terraform init \
   #     -backend-config="bucket=mainline-demo-tfstate-<account>" \
   #     -backend-config="region=ap-southeast-1"
   ```

   That line carries your account id. It is not a credential, but do not paste it into a
   tracked file — `scripts/submission/audit_public_readiness.py` fails the build on a literal
   occurrence (decision D2).

2. **Create the bucket — THE FIRST MUTATING ACTION.** §5.1. Orchestrator and founder only.

   ```bash
   scripts/deploy/bootstrap_state.sh --expect-account <id>
   ```

3. **Init against the real backend and plan.** From here the state is real, `use_lockfile`
   takes and releases an S3 lock, and §5.6.1's local-override reproduction is no longer
   equivalent and must not be used to check the count.

   ```bash
   cd infra/envs/demo
   terraform init -reconfigure -backend-config="bucket=<the bucket>" -backend-config="region=ap-southeast-1"
   terraform plan -no-color -input=false -out=<scratch>/tfplan.binary
   ```

4. **Or just run the deploy script**, which does all of the above and stops at the approval
   gate: `scripts/deploy/deploy.sh --expect-account <id>` → exit 7, §5.6.

**Whichever path produced it, the plan the founder approves is the plan that is applied**, as
a saved plan file. `plan_repro.sh` is for *reading* the plan before there is a backend; it is
not a substitute for stage 6, which is what actually runs.

### 5.7 · Publish, and prove the hostname over HTTPS

**THE BINDING RULE: there is no path through this script that prints a URL it did not just
fetch over HTTPS.** Everything in this stage exists to keep it true.

1. `terraform output -json`, once. The hostname is resolved from the first of these keys
   that holds an `https://` string, and **the script prints which key it used**:
   `demo_url`, `deploy_summary.demo_url`, `api_function_url`,
   `deploy_summary.api_function_url`, `function_url`, `deploy_summary.function_url`.
   None of them → exit 1, listing what it looked for and what the root actually emitted.
2. Under D1, if Terraform reports the Function URL's `authorization_type` as anything but
   `NONE`, the script stops: an unsigned `GET` to an `AWS_IAM` Function URL is a `403` with
   an empty body, and no judge could open it.
3. `GET <url>/` — up to 20 attempts at 15 s. Must answer `200`, and must answer with
   `Content-Type: text/html`. A `200` that is not HTML means a judge gets a download, not a
   console.
4. `GET <url>/v1/health` — must answer `200`, and the body must satisfy **all four**:
   `ok` is `true`; `cluster_version` contains `CockroachDB`; `database` equals
   `mainline_demo`; `schema_fingerprint` is non-empty.

Only then is the URL printed.

**If step 3 times out:** under D1 that means the package's `web/` root is missing or
`$MAINLINE_WEB_ROOT` disagrees with it. Compare `terraform output -raw web_root` against
`unzip -l <package> | grep ' web/'`.

**If step 4 returns 503:** the body names the reason. `dsn_unset` — the Lambda cannot read
the SSM parameter. `unreachable` — the DSN is wrong or the cluster refused.
`no_bookkeeping` — it connected to a database the migration chain never touched, which is
almost always `defaultdb`.

> **`dsn_unset` has two causes and the body tells you which. Measured 2026-08-14 against
> the deployed URL**, `GET /v1/health` returns `503` with
>
> ```
> "reason": "dsn_unset",
> "detail": "SSM GetParameter '/mainline/demo/cockroach_dsn' in ap-southeast-1 answered
>            HTTP 400: {\"__type\":\"ParameterNotFound\"}"
> ```
>
> `ParameterNotFound` means **the parameter does not exist** — stage 5.2 has not run, or
> has run into a different name or region. `AccessDeniedException` would mean the parameter
> exists and the role cannot read it, which is the `ssm:GetParameter` grant. **They are
> different failures with different fixes and the `detail` string distinguishes them
> without guessing.** Read it before touching IAM.
>
> Writing that parameter is a **secret-handling step and is deliberately not scripted on
> this page**: §5.2 owns it, the value is the `mainline_api` DSN and not the operator's own,
> and no DSN is printed anywhere in this repository.

### 5.8 · Proof

`scripts/deploy/demo_acceptance.py --url <the URL>`, and **the deploy exits non-zero if it
does**. A deploy that cannot show the live gate refusing, refusing under attack, and then
admitting — over HTTPS — is a failed deploy, and it says so rather than printing a URL.

**If it fails:** `aws logs tail /aws/lambda/mainline-demo-api --since 10m`. Do not submit
the URL.

### 5.9 · Hand-off

Prints the URL, what was proved about it, the shape, the account, the Lambda name, and the
judge access block — which says plainly that the URL needs no credential, names the
read-only `mainline_judge` login, and states that its password is *not stored by this
script or anywhere in the repository*.

### 5.10 · What the URL serves today — measured 2026-08-14, and not dressed up

**The apply has run.** The stages above are the procedure; this section is the state, and it
is written because a runbook whose "what happens next" is a description of a hypothetical is
a runbook nobody can check.

| request | answer | measured |
|---|---|---|
| `GET /` | **`200`**, 4,655 B, 1.52 s | the static console shell serves |
| `GET /assets/index-DzVoV1YM.js` (`--compressed`) | **`200`**, 124,177 B | the entry chunk |
| `GET /v1/health` | **`503`**, `ok=false`, `reason="dsn_unset"` | §5.7 step 4 |
| `POST /v1/demo/gate-run` | **`503`**, `kind="dsn_unset"`, 174-byte body | **not `404`** — the route exists and is reachable |

Both API answers carry the same `detail`, naming the cause exactly:
`SSM GetParameter '/mainline/demo/cockroach_dsn' in ap-southeast-1 answered HTTP 400:
{"__type":"ParameterNotFound"}`.

> **The byte counts and the status codes reproduce; the elapsed time does not, and it is not
> supposed to.** Four independent readings of `GET /` were taken on 2026-08-14 by four
> programs and people — **1.52 s** here, **1.63 s** in
> [`evidence/deploy/APPLIED.md`](../../evidence/deploy/APPLIED.md), **1,617.4 ms** by
> `scripts/deploy/judge_walk.py` and **0.700 s** by the package-and-verify lead — and all four
> returned **200** and **4,655 B**. A cold Lambda's first byte is a distribution, not a
> constant, so none of those supersedes another and none is corrected to match. **What must
> agree is the status, the body size and the reason string, and those four readings agree on
> every one.** §5.11 is how to take a fifth.

#### The parameter is the founder's step and nobody else's

`/mainline/demo/cockroach_dsn` must hold the **`mainline_api`** DSN — the least-privileged
role, holding `CONNECT`/`USAGE`/`SELECT`/`UPDATE`/`INSERT`/`EXECUTE` and nothing more. It
must **not** hold the administrative DSN this repository's `.env` carries, which holds `ALL`
on every object in the demo database, because the Function URL is `authorization_type = NONE`
and anyone with the hostname reaches the handler that reads it. **No DSN appears in this
repository, in this page, or in any example on it, and none may be added.**

#### Until it lands, `dsn_unset` is the demo beat — and it is a good one

This is the part not to apologise for. With a correctly built LIVE console in front of that
handler, a judge presses a control and the console:

1. issues `POST /v1/demo/gate-run` **to the page's own origin** — no CORS, no second
   hostname, the request is visible in the network panel;
2. gets `503` with a body that is not an envelope, which `src/data/transport.ts` classifies
   as a `status` failure rather than a gate refusal — *"the client asked wrongly"* and
   *"the gate refused"* are different findings and only one of them is about the product;
3. renders the answer **verbatim**. The body is 174 bytes and the transport quotes the first
   200, so the whole thing reaches the screen, `ParameterNotFound` and the parameter's name
   included.

**A judge is shown a console that reached its own kernel and printed exactly what the kernel
said, including the fact that an operator has not finished.** That is the product's central
claim demonstrated on the one screen where it is cheapest to fake. Compare what it replaces:
the artefact deployed today is a **REPLAY** console — `TRANSPORT REPLAY (staged)`,
`BUILD dev`, every byte a recording — which looks healthier and proves less.
[`console-build.md`](console-build.md) §7 has the compiled literals and the packaging guard
that now refuses to ship that combination.

**What this section does NOT claim.** It does not claim the four beats run; they cannot until
the parameter exists. It does not claim the deployed artefact is the corrected one; it is not,
and no worker in this wave deploys — the orchestrator does. `demo_acceptance.py` against this
URL will exit non-zero for exactly this reason, and that is the correct behaviour: **a deploy
that cannot show the gate refusing and then admitting is a failed deploy and says so** (§5.8).

### 5.11 · Re-run this whole section yourself — `scripts/deploy/judge_walk.py`

**Every reading in §5.10 is regenerable by one command, from a bare checkout, with no AWS
credential, no `terraform init` and no state file.** That is the whole point of the program:
§5.10 is a transcript, and a transcript nobody can reproduce is a screenshot.

```bash
python scripts/deploy/judge_walk.py \
  --base-url https://ihuuyvm4z6nfuktihnkey77fpy0eyrhj.lambda-url.ap-southeast-1.on.aws
```

On Windows: `.venv\Scripts\python.exe scripts\deploy\judge_walk.py --base-url <the URL>`.
It writes [`evidence/deploy/judge-walk.json`](../../evidence/deploy/judge-walk.json) and prints
a step-by-step account. **It is not `post_apply_verify.py`** (§5.7): that one reads
`terraform output`, calls AWS for alarm inventory and drives the kill switch, so it needs
credentials and state. This one takes **a URL and nothing else**.

| flag | what it does |
|---|---|
| `--base-url <url>` | required; the only input |
| `--out <path>` | where the JSON document goes (default `evidence/deploy/judge-walk.json`) |
| `--enumeration origin\|repo\|auto` | where the request list is read from; `auto` prefers the origin and records which it used |
| `--allow-replay` | **downgrades the REPLAY finding from FAILED to a named refusal.** It must be typed; a document produced with it is stamped `allow_replay_declared: true` and can never be cited as a reading of a LIVE artefact |

**Three outcomes and a closed set of reasons.** `SATISFIED` — it answered what it was supposed
to answer. `REFUSED` — it refused **for a reason from a written-down table**, and that refusal
is the correct behaviour of a correct deployment in a known state. `FAILED` — anything else.
`REFUSED` without a reason from that table is not representable: the program raises rather than
inventing one. **`dsn_unset` is a `REFUSED`, not a `FAILED`**, and the walk says the words in
full: *the origin is up, the route is reachable, and the SSM parameter is the founder's
remaining step.* A walk that exited red for a step belonging to somebody else would teach its
reader to ignore it tomorrow.

**It drives what the artefact itself declares, not a list somebody typed here.** The console
ships an EvidenceBundle whose `manifest.json` enumerates every request the console makes and
the REPLAY counterpart of each; the walk reads that manifest — from the origin, at the bundle
URL *compiled into the served JavaScript*, falling back to the repository copy and saying which
it used — and drives all **18** frames. A hand-written endpoint list is a list that drifts from
the console in silence.

**What it said on 2026-08-14, against this URL, live:**

```
23 steps: 2 satisfied, 20 refused (dsn_unset), 1 FAILED (transport: REPLAY)   -> exit 1
with --allow-replay:  21 refused, 0 failed                                    -> exit 0
```

**Exit 1 is the correct answer today and the transport step is why.** `dsn_unset` is a correct
deployment answering correctly about somebody else's step; a REPLAY console is a **wrong
artefact**, and filing the two in the same exit-neutral drawer would hand a reader a green walk
while they look at a recording. The transport step reads the compiled `VITE_MAINLINE_*`
literals out of the served entry chunk and applies `source-select.ts`'s own `trimmed()` rule —
no browser, no screenshot, the bytes a judge executes. **Once the artefact is rebuilt LIVE and
the orchestrator redeploys, the bare command exits 0 with `dsn_unset` recorded**, and that
transition — not a re-worded page — is what will show this section has moved.

**It writes nothing to AWS.** It knows no Terraform verb and no AWS API, it never reads or
writes `/mainline/demo/cockroach_dsn`, and it masks every `postgres(ql)://` URL, every embedded
`user:password@` and every bare twelve-digit run before anything reaches stdout or the file.
Its own caveat, which is not hidden: three of the eighteen frames are `POST` merges, so driving
them against a seeded live cluster **writes**, exactly as a judge clicking the console writes.
Nothing is skipped to avoid that; `scripts/deploy/seed_demo.py` restores the world.

---

## 6 · Teardown

```bash
scripts/deploy/teardown.sh --dry-run                        # list what would go; delete nothing
scripts/deploy/teardown.sh --expect-account <id> --yes      # do it
```

On Windows: `& "C:\Program Files\Git\bin\bash.exe" scripts/deploy/teardown.sh --expect-account <id> --yes`.

Order, and it matters:

0. **inventory** — what carries our prefix, and, by name, what does not
1. `terraform destroy` — the Lambda, the Function URL, the role, the log group, the alarms
2. the site bucket, if one exists — **every version and every delete marker**, then the bucket
3. the SSM SecureString
4. `DROP DATABASE mainline_demo CASCADE`, then `mainline_api`, then `mainline_judge`
5. the state bucket, **last** — deleting it before step 1 leaves every AWS resource alive
   and unmanaged, recoverable only by importing them by hand

### The three safety gates

Every destructive step passes `assert_ours`, which requires **both**:

* the name begins with `mainline-demo-` (or `/mainline/` for the SSM parameter), and
* the **live** resource carries `project=mainline`, read back from AWS at the moment of
  deletion — not from Terraform state, not from a variable

and the whole script requires that you named the account. `--ignore-tags` relaxes the tag
check. **Nothing relaxes the prefix check, and only `--any-account` relaxes the account
check.**

### Measured against the live account, 2026-08-11

```
$ scripts/deploy/teardown.sh --dry-run
MAINLINE demo teardown   account=<id>  region=ap-southeast-1  (DRY RUN — deletes nothing)

== 0 · inventory
   [ok] no s3 bucket in this account carries the 'mainline-demo-' prefix
   WOULD NOT TOUCH s3://aws-cloudtrail-logs-<account>-10882a56  (no 'mainline-demo-' prefix)
   WOULD NOT TOUCH s3://cci-change-feed  (no 'mainline-demo-' prefix)
   WOULD NOT TOUCH s3://checkout-platform-debd5edd-site  (no 'mainline-demo-' prefix)
   WOULD NOT TOUCH s3://checkout-platform-site  (no 'mainline-demo-' prefix)
   WOULD NOT TOUCH s3://elasticbeanstalk-ap-southeast-2-<account>  (no 'mainline-demo-' prefix)
   WOULD NOT TOUCH s3://intellicanvas-voice-model  (no 'mainline-demo-' prefix)
   WOULD NOT TOUCH s3://shortstack-pipeline-artifactbucket-amxvhsepi4ak  (no prefix)
   [ok] no lambda function in ap-southeast-1 carries the 'mainline-demo-' prefix
   [ok] no SSM parameter under /mainline/ exists in ap-southeast-1
   WOULD NOT TOUCH cloudfront E2FCXK8NILPNWF  d2hlkr5e2hb7k7.cloudfront.net
                   (origin checkout-platform-debd5edd-site.s3.ap-southeast-2… — not ours)
…
== verify
   dry run — nothing was deleted, so there is nothing to verify.
   [ok] and there was nothing to delete: ZERO resources in account <id> carry the
   [ok] 'mainline-demo-' prefix or live under /mainline/. The last teardown was clean.
exit=0
```

**Seven unrelated buckets and one unrelated distribution, each named, each excluded.** A
teardown that lists only its own targets tells you nothing about the blast radius; this one
shows the whole account and draws the line through it. The full transcript is committed to
[`evidence/deploy/deploy-dry-run.json`](../../evidence/deploy/deploy-dry-run.json) as run
`D`, and the three refusals below are run `E`:

```
$ scripts/deploy/teardown.sh --dry-run --site-bucket aws-cloudtrail-logs-<account>-10882a56
teardown REFUSED
   bucket 'aws-cloudtrail-logs-…' does not carry the 'mainline-demo-' prefix.
exit=3

$ scripts/deploy/teardown.sh --dry-run --expect-account SOMEONE-ELSES-ACCOUNT
teardown REFUSED
   this is account <id>. You said SOMEONE-ELSES-ACCOUNT. Deleting nothing.
   Fix the profile (--profile <name>) or the expectation (--expect-account <id>).
exit=3

$ scripts/deploy/teardown.sh --yes                       # no account named
teardown REFUSED
   NOTHING TOLD THIS SCRIPT WHICH AWS ACCOUNT IT MAY DELETE FROM, so it will not
   delete from one.
exit=3
```

**Why the second refusal names a word and not a number.** The natural way to demonstrate
the account gate is to type a wrong twelve-digit account id, and that is how it was
demonstrated when this page was first written. It cannot stay that way, because
`scripts/aws/verify_evidence.py` refuses to let *any* bare twelve-digit run into
`evidence/` — invariant `SEC-ACCOUNT-ID`, enforced by the `aws-evidence` lane on every
push — and it is right to: a scanner that cannot tell a deliberately-wrong account id from
a real one is a scanner with a hole in it, and one carved exception becomes the next. The
gate is a plain string comparison against `aws sts get-caller-identity`
(`scripts/deploy/teardown.sh:250`, compared at `:256`), so `SOMEONE-ELSES-ACCOUNT` reaches exactly the branch a
mistyped account id reaches, and refuses with exit `3` for exactly the same reason. The
transcript in `evidence/deploy/deploy-dry-run.json` is the output of that command run
against the live account on 2026-08-12 — the block above was re-measured, not re-worded.

### Why versions, not just objects

`aws s3 rm --recursive` leaves noncurrent versions and delete markers behind on a versioned
bucket, and `delete-bucket` then fails with `BucketNotEmpty` over objects `aws s3 ls` does
not show. That is the single most common way a "successful" teardown leaves a bucket, and a
bill, behind. Teardown drains `Versions` and `DeleteMarkers` in two separate passes — not
one combined JMESPath, because when one of the two keys is absent the flatten yields a list
containing `null` and `delete-objects` rejects the payload.

### Why `DROP DATABASE` comes before `DROP USER` — measured

Against the local CockroachDB v26.2.5 node, with the grant shape `cloud_roles.py` produces:

```
== REVERSE order: DROP USER while grants still exist ==
  [2BP01] DROP USER IF EXISTS w7rev_api
          cannot drop role/user w7rev_api: grants still exist on w_w7_rev, w_w7_rev.public.t

== then the correct order ==
  OK       DROP DATABASE IF EXISTS w_w7_rev CASCADE
  OK       DROP USER IF EXISTS w7rev_api
```

`CASCADE` takes the grants with it, and only then do the logins drop. The other way round
leaves two users behind on a cluster the next deploy reuses — still holding a password.

Teardown then **re-reads AWS** and reports residue rather than trusting its own deletions.
It is safe to run twice.

---

## 7 · When something goes wrong

### "Error acquiring the state lock"

```
Error: Error acquiring the state lock
  Lock Info: ID: … Path: mainline-demo-tfstate-…/demo/terraform.tfstate
```

A previous run died between acquiring and releasing. The lock is an S3 object
(`demo/terraform.tfstate.tflock`), not a DynamoDB row. **Confirm no other apply is
running**, then:

```bash
cd infra/envs/demo
terraform force-unlock <the ID from the message>
```

### The deploy exited 7 and printed no URL

It planned and stopped at the approval gate. That is the designed behaviour. Read the plan,
have it approved, then re-run with `MAINLINE_APPLY_APPROVED=1`. See § 5.6.

### `--dry-run` exits 1 naming an artefact

Exactly as designed. The message names the missing path **and the worker that owes it**.
That is the check, not a preview.

### `--dry-run` exits 3

Either the account you named is not the caller, or `--strict-secrets` was passed and an
operator secret is missing. The message says which. Exit 3 is always a *refusal*, never a
*missing artefact* — those are exit 1.

### The URL 404s but `/v1/health` is green

The package's `web/` root is missing or empty, or `$MAINLINE_WEB_ROOT` points somewhere the
packer did not write. This is exactly what stage 0 and stage 4 check for; if you got here,
something bypassed them. `unzip -l <package> | grep ' web/'`.

### The URL serves a blank page with a console error

Almost always a `Content-Type`. Under D1 the handler sets them from its own table, so check
the entry chunk:

```bash
curl -sSI https://<id>.lambda-url.ap-southeast-1.on.aws/assets/index-XXXXXXXX.js | grep -i content-type
```

It must be `text/javascript` or `application/javascript`, never `text/plain`.

### `/v1/*` returns 403

Under D1 the Function URL's `authorization_type` is `NONE` and nothing should 403. If it
does, Terraform reverted to `AWS_IAM` — stage 7 asserts against exactly this and would have
refused to print the URL. Check `terraform output -raw api_authorization_type`.

### The demo is broken and judging starts in an hour

There is no `--phase1` any more, and there does not need to be — but the sentence that used
to be here overstated how automatic the fallback is, so read the correction before relying
on it.

> ~~If the database is unreachable the console **degrades to the signed EvidenceBundle on
> its own** and shows a `REPLAY` badge saying so — same URL, same package, no redeploy. That
> is a run-time property of the console, not a deploy mode.~~
>
> **CORRECTED 2026-08-14: the switch is a CONTROL, not an automatic degradation.** Read
> against `src/app/source-select.ts`, the source is chosen by a pure function of the
> **build** and of nothing else — its own header says so: *"decided by a pure function of
> the BUILD, and of nothing else"*. With both variables compiled in, the console starts
> **LIVE** and renders a control that switches to **REPLAY**; with one, it uses that one and
> renders no control. **Nothing anywhere switches transport because a request failed.** A
> console that silently swapped a live answer for a recording when the live answer was
> inconvenient would be the exact machine this product argues against, so the absence of
> that behaviour is a feature and not the gap this paragraph implied.

What is true, and is what you actually get:

* **Same URL, same package, no redeploy — one click.** A LIVE-built console keeps the
  REPLAY bundle inside the same package and the control is on screen, so a reader who wants
  the recorded evidence is one click from it and the badge tells them which one they are
  looking at. The badge is read from `transport.describe().mode`, off the object holding the
  bytes, so it cannot disagree with what is on screen.
* **A failed live request renders as a failure, verbatim.** That is the honest outcome and
  §5.10 is what it looks like today: `503 dsn_unset`, the parameter named, on screen.
* **If the artefact was built with only the bundle**, as the currently deployed one was, the
  console is REPLAY and there is no control at all — and no request ever reaches the kernel.
  That is the failure mode to check for first: read the badge, and read
  [`console-build.md`](console-build.md) §1's `grep` if you have the `dist/`.

---

## 8 · What it costs

**There are two bills, and confusing them is the most expensive mistake available in this
document.** The demo nobody attacks costs about two cents a month. The demo somebody floods
is bounded by exactly one thing — an AWS account default of 10 concurrent executions — and
that bound sits at four to five orders of magnitude higher.

| | Steady state | Adversarial |
|---|---|---|
| Who is calling | judges, a health cron, us | anyone who finds an `on.aws` hostname |
| What bounds it | the free tiers below | **the account concurrency ceiling of 10, and the shipped levers** |
| 30 days | **≈ $0.02** | **see [`COST-BOUND.md`](COST-BOUND.md) — one authority, no copy here** |
| Measured in | §8.1 below | [`COST-BOUND.md`](COST-BOUND.md) |

The steady-state number is measured, and §8.1 shows the arithmetic. **The adversarial number
is deliberately not restated in this runbook.** This table used to carry *"USD 11,538 –
33,257"*, and that range assumed a **100 ms** invocation nobody had measured; at the measured
duration it is understated about sevenfold. A second copy of a figure is a second thing that
can go stale, and this one already had. Read `COST-BOUND.md` before the apply — not after.

An earlier version of this section ended *"round it to two cents a month, and call the worst
case a dollar"* — a sentence that was wrong by a factor of about thirty thousand, and wrong
in the direction that gets a founder's card charged. It is deleted rather than softened,
because a reader who took it at face value would have had no reason to open `COST-BOUND.md`
at all.

### 8.1 · Steady state — ≈ $0.02/month

Free tiers here are AWS's **perpetual** free tiers, not the 12-month new-account ones, so
the arithmetic does not expire.

| Line | Basis | Arithmetic | USD/month |
|---|---|---|---|
| Lambda | perpetual free: 1 M requests, 400 000 GB-s | **256 MB** × 300 ms × 10 000 req = **768 GB-s → 0.19 %** of the allowance (~~512 MB … 1 536 GB-s → 0.4 %~~) | **0.00** |
| Lambda **Function URL** | no charge beyond the invocation | — | **0.00** |
| CloudWatch Logs | 7-day retention | far under the 5 GB free ingest | **0.00** |
| CloudWatch alarms | **7** alarms (4 `demo-api` + 3 `guard`); first 10 free (~~4 alarms~~) | | **0.00** |
| S3 — **state bucket only** | one small versioned object, noncurrent versions expire at 30 days | < 1 MB | **0.01** |
| **State locking** | `use_lockfile = true` | **no DynamoDB table** | **0.00** *(vs $0.25)* |
| SSM Parameter Store | Standard SecureString | Standard tier is free | **0.00** |
| Bedrock Titan Embed v2 | one seed pass, then ~50 tokens/query | 0.2 M × $0.02/M | **0.01** |
| CockroachDB Cloud Basic | inside the free allowance; `spend_limit` is a hard ceiling | | **0.00** |
| CloudFront | **not created** — D1 | | **0.00** |
| S3 site bucket | **not created** — D1; the payload is in the package | | **0.00** |
| Route 53 / ACM | **not used** — the Function URL's own AWS certificate | | **0.00** |
| CloudWatch Synthetics | **not used** — see below | | **0.00** |
| | | **Total** | **≈ $0.02** |

> **TWO STALE INPUTS CORRECTED 2026-08-14, AND THE CONCLUSION IS UNCHANGED — SAID OUT LOUD
> RATHER THAN LEFT IMPLICIT.**
>
> 1. **The Lambda row divided by 512 MB; the plan ships 256.**
>    `evidence/deploy/terraform-plan-furl.txt:290` reads `memory_size = 256`, confirmed by
>    the plan-known `api_published_bounds.memory_size_mb = 256` at `:867`. Recomputed at
>    256 MB the figure **halves**, to 768 GB-s and 0.19 % of the 400 000 GB-s allowance.
>    (Both the old and new numbers use this table's own 1 GB = 1000 MB convention; at
>    1 GB = 1024 MB it is 750 GB-s / 0.19 %. The choice does not matter at three orders of
>    magnitude of headroom.) **The row still rounds to $0.00 and the ≈ $0.02 total does not
>    move** — the input was stale, not the conclusion.
> 2. **The alarm row counted 4; the stack now plans 7.** `module.guard[0]` adds
>    `-invocations-burst`, `-invocations-hourly` and `-log-ingestion`. **Still under the
>    first-10-free allowance, so still $0.00.**
>
> **WHAT THIS TABLE STILL DOES NOT COST, STATED AS A GAP RATHER THAN A ZERO.** It predates
> `module "guard"` and does not have a row for the other ten resources it creates (SNS topic,
> topic policy, responder subscription, responder Lambda + its log group, IAM role, two
> policies, an attachment, and an AWS Budgets budget). Idle, all of them bill nothing I can
> show: the responder is invoked only on a breach, and SNS's first million requests are free.
> **The exception is `aws_budgets_budget.guard`: UNRESOLVED.** AWS Budgets bills per budget
> per day beyond a free allotment, and settling it needs two facts this machine cannot supply
> — the current AWS Budgets tariff, and how many budgets already exist in account
> `0229…8246`. **A read-only `aws budgets describe-budgets --account-id …` against the real
> account, plus the published Budgets price, settles it.** Nothing is applied, so no budget
> exists to bill yet.

**Round it to two cents a month.** The founder's ceiling is ~USD 5/month, and *this table*
is two orders of magnitude under it. Removing CloudFront and the site bucket from the
request path made this bill *smaller*.

**What this table assumes, and where it stops.** Every row above is priced at demo volume —
on the order of 10 000 requests a month, which is what judging plus an hourly cron
produces. Not one of these lines has a ceiling in it. They are small because the traffic is
small, and the traffic is small because nobody has decided otherwise. §8.2 is what happens
when somebody does.

The three refusals worth naming:

* **No custom domain.** A hosted zone is $0.50/month — twenty-five times the rest of the
  stack combined — and it buys a prettier string in a form.
* **No Synthetics canary.** One canary at five-minute intervals is 8 640 runs/month ×
  $0.0012 = **$10.37/month**, roughly five hundred times the rest of the stack. The health
  check is a GitHub Actions cron against `/v1/health`, which costs nothing and whose
  failures are visible in the repository the judges are already reading.
* **No DynamoDB lock table.** Native S3 locking, since Terraform 1.10.

Within the table, the line that grows without a ceiling on its own is CloudWatch Logs,
which is why `log_retention_days` is validated against a short list and can never be `0`
("never expire"). **Under §8.2 it is not the line that matters** — data transfer out is,
and no variable in this repository bounds it.

### 8.2 · Adversarial — bounded only by an account default of 10

The demo URL is a Lambda Function URL with `authorization_type = NONE`. It is meant to be:
the judges must open it without an account, and CloudFront — the usual answer — is refused
on this account (Appendix A). So the origin answers everyone, and the only question is how
fast.

The answer, measured: **10**. `L-B99A9384` "Concurrent executions" reads `Value 10.0` in
`ap-southeast-1`, and `ConcurrentExecutions` cannot physically exceed it. Multiplied by 30
days and by the largest response the package can emit, that is a figure with five digits in
front of the decimal point — **and this page no longer names it, because it named it wrong
for a week.** The published *"USD 11,538 – 33,257"* was built on an assumed 100 ms
invocation; the measured duration is 14.106 ms, which makes the true number roughly seven
times larger. `COST-BOUND.md` carries it, derives it from `scripts/deploy/cost_model.py`, and
is the only place it is written down.

**The arithmetic, the inputs it is built from, and the menu of levers that change it are in
[`docs/deploy/COST-BOUND.md`](COST-BOUND.md), and are not repeated here.** Read it before
the apply, not after. Two things from it belong in this runbook because they are operating
instructions rather than analysis:

> **THE QUOTA IS `Adjustable: true`, AND NOBODY REQUESTS AN INCREASE.**
>
> ```
> aws service-quotas get-service-quota --service-code lambda \
>     --quota-code L-B99A9384 --region ap-southeast-1
>   QuotaName  "Concurrent executions"   Value 10.0   Adjustable true
> ```
>
> Every dollar in `COST-BOUND.md` scales very nearly linearly with that number. At 100 the
> worst case is ≈ $325,000; at AWS's usual default of 1 000 it is ≈ $3.2 M. The ceiling of
> 10 is **the only real bound this deployment has**, it arrived by accident, and it is one
> support ticket away from being gone. Not for load testing, not "temporarily for judging".
> A change that appears to need a higher ceiling is a change that is wrong.

> **The kill switch is `reserved_concurrent_executions = 0`, and it is one command.**
>
> ```bash
> scripts/deploy/kill_switch.sh --status                 # read-only
> scripts/deploy/kill_switch.sh --stop --expect-account <id> --yes
> ```
>
> It is the one reservation this account can still accept, and it stops the function
> immediately. `COST-BOUND.md` §8 documents it, including what it does not do.

**The AWS Budgets on this account stop nothing.** Three budgets — $10, $5 and $1 — all
three already breached by unrelated projects, and `describe-budget-actions-for-budget`
returns `{"Actions": []}` for each. They notify. There is no Budgets action that can
disable a Lambda function; see `COST-BOUND.md` §3.6 for why, and for what the real backstop
would cost in lag.

---

## 9 · What has and has not been proven

Honesty is the moat, so this section is explicit.

**Measured on this machine, against live systems, 2026-08-10, 2026-08-11 and 2026-08-14:**

* **§5.6.1 end to end, 2026-08-14.** `scripts/deploy/plan_repro.sh` run in the published
  order on this machine: stage 2's three read-only checks, `init -reconfigure`, `validate`
  (*Success! The configuration is valid.*), `plan` → **`Plan: 24 to add, 0 to change, 0 to
  destroy.`**, agreeing with `evidence/deploy/terraform-plan-furl.txt`; exit 0;
  `git status --porcelain -- infra/envs/demo` identical before and after, and
  `backend_override.tf` gone. Both refusals were exercised as negative controls the same day:
  **seven refusals at exit 2** — `apply`, `destroy`, `import`, `taint`, `force-unlock`,
  `state`, and `plan -destroy` — and the expiry guard at **exit 5** when pointed at a Lambda
  that does exist. A runbook nobody has run is a hypothesis; this one has been run
* `terraform validate` and `terraform plan` against the real modules — no cycle, one pass
* the cycle and the `Invalid count` error that shaped the wiring — both reproduced, both
  transcribed in `infra/envs/demo/README.md`
* **a real `terraform apply` against the real S3 backend** (2026-08-10, the pre-D1 shape).
  State lock acquired and released; seven resources created; the eighth — the CloudFront
  distribution — refused by AWS. See Appendix A. `terraform destroy` then removed all seven
* `bootstrap_state.sh` creating the real state bucket, versioned, private, SSE-S3, tagged,
  with the lifecycle rule — and refusing a bucket name outside the prefix
* **a real `teardown.sh --yes` run**: it drained two pages of object versions and delete
  markers from the versioned state bucket, deleted it, then re-read AWS and reported no
  residue. Exit 0
* **`teardown.sh --dry-run` against the live account, 2026-08-11**: zero `mainline-demo-`
  resources, seven unrelated buckets and one unrelated distribution named and excluded
* **`deploy.sh --dry-run` exiting 0** with every prerequisite present, **exiting 1** with
  the Lambda zip renamed away, and **exiting 3** under `--strict-secrets`. All three
  transcripts are in `evidence/deploy/deploy-dry-run.json`
* the account guard refusing an unnamed account, a mismatched account, and permitting a
  matched one — in `deploy.sh`, `teardown.sh` and `bootstrap_state.sh`
* the `DROP DATABASE … CASCADE` → `DROP USER` ordering, and the `2BP01` the reverse produces
* the WSL-vs-Git-Bash distinction that shaped `deploy.ps1`
* the Windows `mimetypes` results that justify Appendix A's explicit content types
* **one real bug, found by running rather than reading.** Under Git Bash, `mktemp` returns
  `/tmp/x.json` and the native `aws.exe` cannot open it, so the first real teardown died
  with `Unable to load paramfile file:///tmp/mainline-del.XyMVEA.json`. Both scripts now
  route every `file://` paramfile through `cygpath -m`. This mattered twice: teardown's
  delete payload, and — more importantly — stage 2's SSM payload, which is a paramfile
  *specifically* so the DSN never enters an argument vector
* **a second real bug, in `deploy.ps1`.** `& $Py $tmp; return $LASTEXITCODE` returns the
  interpreter's *output* as well as its exit code, because PowerShell collects every
  uncaptured value into the return — so `-eq 0` compared an array and silently swallowed a
  probe's explanation. `Invoke-PyInline` exists to make that impossible

**Not proven, and stated here rather than implied away:**

* ~~**A live demo URL. There is none yet**, because `terraform apply` is gated on the
  founder's approval of the committed plan and that approval has not been given.~~
  **SUPERSEDED 2026-08-14: the apply has run and the URL serves.** Measured, not inferred:
  `GET https://ihuuyvm4z6nfuktihnkey77fpy0eyrhj.lambda-url.ap-southeast-1.on.aws/` answers
  **`200`** with 4,655 B of console shell. This page records the *observable consequence*;
  the approval itself is the founder's and is not something this document witnessed.
  What is **still** not proven, and is the narrower claim the struck bullet was standing in
  for: **that the URL can run the four beats.** It cannot. Stage 5.2 has not written
  `/mainline/demo/cockroach_dsn` — the API answers `503` with `ParameterNotFound`, verbatim
  — so the Lambda has no database, and `demo_acceptance.py` against that hostname exits
  non-zero at the health check, correctly. Separately, the console artefact deployed on it
  is a **REPLAY** build, so nothing on its screen is that kernel. §5.10 has the whole
  measured picture and [`console-build.md`](console-build.md) §7 has the packaging defect
  that produced it. Every artefact upstream is built, hashed and checked; `deploy.sh
  --dry-run` exits 0.
* **Stage 6's runtime behaviour end to end.** Reaching stage 6 requires stage 1 to create
  the state bucket and stage 2 to write the real `mainline_api` DSN to SSM. Stage 6 is
  therefore verified statically — exactly one executable `terraform apply`, unreachable
  without `MAINLINE_APPLY_APPROVED=1` — and by the `apply gate CLOSED` line the preflight
  prints on every run. Its first execution will be the approved one. **§5.6.1 does not close
  this gap and does not claim to:** it proves the plan is reproducible read-only, not that
  stage 6 behaves as written.
* **§5.6.2, the real-S3-backend path, has NOT been run in this wave.** Step 2 of it is
  `bootstrap_state.sh` without `--print-backend-config`, which creates a bucket — a mutating
  call, and this wave is read-only, so it was not run and its transcript is the 2026-08-10
  one quoted in §5.1 rather than a fresh one. What *was* verified read-only on 2026-08-14 is
  step 1, `--print-backend-config`, which emits the two `-backend-config` lines and makes no
  AWS call. **Steps 2 and 3 are documented, not demonstrated.** Saying so is cheaper than
  discovering it at the gate.
* **Stage 7's HTTPS proof.** It cannot run before something is deployed. Its assertions are
  written against the measured shape of `health.py`, not against a guess.
* **`deploy.ps1` stages 1–9.** Its preflight and `-DryRun` were run here and behave
  identically to the bash script. Its later stages carry the same gate and the same guards
  but have not executed.
* **The OpenTofu commands in `infra/envs/demo/README.md`.** OpenTofu is not installed here;
  "the HCL is in the common subset" is a claim about the code, not a measurement.
* **`/v1/health` will report `migrations_applied: 0`, not 271.** Measured directly against
  the Cloud cluster on 2026-08-11: `trappoint.schema_migration` is empty, while
  `trappoint.deploy_chain` holds one row and `trappoint.schema_attestation` holds one
  (fingerprint `ec9b1ce70a8df066…`). Health still answers `200` because `ok` keys on the
  fingerprint. This is not this page's to fix; it is recorded here and in
  `evidence/deploy/deploy-dry-run.json` so nobody asserts `271` against the live demo.

---

## Appendix A — the CloudFront hold, the evidence, and the upgrade path

This appendix exists because the evidence is worth keeping, **not** because anything in
this runbook is waiting on it. Nothing here is on the critical path. If AWS Support never
answers, the demo ships exactly as described above.

### A.1 · What AWS said, verbatim

A real `terraform apply` of the pre-D1 path was run on **2026-08-10** and got as far as the
distribution before AWS refused:

```
module.site.aws_cloudfront_origin_access_control.s3: Creation complete after 2s [id=E2SG85QVMCDKDB]
module.site.aws_s3_bucket.site:                      Creation complete after 6s [id=mainline-demo-site-0229REDACTED8246]
module.site.aws_cloudfront_distribution.site:        Creating...

Error: creating CloudFront Distribution: operation error CloudFront:
CreateDistributionWithTags, https response error StatusCode: 403,
RequestID: 3e63e30d-8c5b-441b-a01b-b70085eba504, AccessDenied:
Your account must be verified before you can add new CloudFront resources.
To verify your account, please contact AWS Support and include this error message.
```

It is **not** a Terraform problem, an IAM policy problem, or a module problem. The same
refusal comes from a bare AWS CLI call with a minimal three-field distribution config and
no Terraform anywhere:

```
$ aws cloudfront create-distribution --distribution-config file://minimal.json
An error occurred (AccessDenied) when calling the CreateDistribution operation:
Your account must be verified before you can add new CloudFront resources.
```

The identity holds `AdministratorAccess`.

> **Note for `w9-public-readiness`, for the disclosure register.** The two blocks above are
> **recorded evidence** under decision D2 and must stay verbatim, `RequestID` included. The
> AWS account id appears inside them at the resource name
> `mainline-demo-site-0229REDACTED8246`, and again in this appendix's § A.2 output. Both are
> quoted transcripts, not executable defaults, and belong in
> `docs/submission/DISCLOSURE-DECISIONS.yaml` with the reason *"a quoted AWS refusal;
> redacting it would make the evidence unverifiable"*. Every executable occurrence in the
> four deploy scripts has been removed — `grep -c` over them is `0`. `RequestID`
> `3e63e30d-8c5b-441b-a01b-b70085eba504` is not a credential; it is the case reference AWS
> Support asks for.

### A.2 · The correction — this account HAS a distribution, and it is not ours

A previous version of this page said `aws cloudfront list-distributions` returns `None` and
that *"this account has never had one"*. **That was wrong.** Measured 2026-08-11:

```
$ aws cloudfront list-distributions \
    --query 'DistributionList.Items[].[Id,DomainName,Origins.Items[0].DomainName]' --output text
E2FCXK8NILPNWF   d2hlkr5e2hb7k7.cloudfront.net   checkout-platform-debd5edd-site.s3.ap-southeast-2.amazonaws.com
```

One distribution: **`E2FCXK8NILPNWF`**, `d2hlkr5e2hb7k7.cloudfront.net`,
`LastModifiedTime 2026-04-16T13:13:03Z`, `Status: Deployed`, origin
`checkout-platform-debd5edd-site.s3.ap-southeast-2.amazonaws.com` — **a different project's,
in a different region, and nothing to do with MAINLINE.**

The accurate statement, which is narrower than the one it replaces, is:

> **The hold is on creating NEW CloudFront resources.** An existing distribution predating
> the hold continues to serve.

`teardown.sh` lists that distribution in its inventory and marks it `WOULD NOT TOUCH`,
because its origin does not carry the `mainline-demo-` prefix. It is visible and visibly
excluded rather than silently skipped.

### A.3 · If Support lifts it

Nothing has to be redesigned. `infra/envs/demo` keeps `module.site` behind
`var.enable_cloudfront`, default `false`:

```bash
scripts/deploy/deploy.sh --expect-account <id> --enable-cloudfront
```

That flips `module.site` on, reverts the Function URL to `AWS_IAM` behind an Origin Access
Control, re-enables stage 5's S3 upload and stage 7's cache invalidation, and produces a
`d…cloudfront.net` hostname. The submission's `demo_url` would then be updated. Stage 7's
proof is identical either way, because it asserts on the URL Terraform emitted rather than
on which module emitted it.

To open the case: **Service: CloudFront, Category: account verification**, and paste the
error message from § A.1 including its `RequestID`.

### A.4 · The content-type trap, kept for the CloudFront path

Only reachable with `--enable-cloudfront`, and worth keeping because it is measured. S3
uploads must set content types **explicitly** and not leave them to `aws s3 sync`'s guess,
because that guess comes from Python's `mimetypes`, which on Windows reads the registry:

```
.js    → application/javascript      fine
.mjs   → text/plain                  a module served as text/plain does not load
.map   → text/plain                  harmless
.woff2 → None                        falls back to binary/octet-stream
```

One wrong `Content-Type` on the entry chunk is a blank page with a console error, on the one
URL the whole submission depends on. So hashed assets go up `immutable` for a year,
`index.html` goes up `no-cache` — it is the only file whose name does not change when its
contents do — and each family names its own type.

Under D1 none of this runs: the handler sets content types from its own table inside
`static_site.py`, and there is no bucket in the request path to get them wrong.
