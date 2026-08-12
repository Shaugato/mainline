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
  `transport.describe().mode` at run time. If the database is unreachable the console
  degrades to the signed bundle and *says so on screen* — which is why there is no longer a
  `--phase1` deploy mode. Passing `--phase1` now exits 2 and explains this; under D1 a
  deploy with no Lambda has no URL at all, because the Lambda **is** the hostname.

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

**If step 4 returns 503:** the body names the reason. `dsn_unset` — the Lambda cannot see
the SSM parameter; check the role's `ssm:GetParameter` grant. `unreachable` — the DSN is
wrong or the cluster refused. `no_bookkeeping` — it connected to a database the migration
chain never touched, which is almost always `defaultdb`.

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

$ scripts/deploy/teardown.sh --dry-run --expect-account 999999999999
teardown REFUSED
   this is account <id>. You said 999999999999. Deleting nothing.
exit=3

$ scripts/deploy/teardown.sh --yes                       # no account named
teardown REFUSED
   NOTHING TOLD THIS SCRIPT WHICH AWS ACCOUNT IT MAY DELETE FROM, so it will not
   delete from one.
exit=3
```

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

There is no `--phase1` any more, and there does not need to be. If the database is
unreachable the console **degrades to the signed EvidenceBundle on its own** and shows a
`REPLAY` badge saying so — same URL, same package, no redeploy. That is a run-time property
of the console, not a deploy mode.

---

## 8 · What it costs

Free tiers here are AWS's **perpetual** free tiers, not the 12-month new-account ones, so
the arithmetic does not expire.

| Line | Basis | Arithmetic | USD/month |
|---|---|---|---|
| Lambda | perpetual free: 1 M requests, 400 000 GB-s | 512 MB × 300 ms × 10 000 req = 1 536 GB-s → 0.4 % of the allowance | **0.00** |
| Lambda **Function URL** | no charge beyond the invocation | — | **0.00** |
| CloudWatch Logs | 7-day retention | far under the 5 GB free ingest | **0.00** |
| CloudWatch alarms | 4 alarms; first 10 free | | **0.00** |
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

**Round it to two cents a month, and call the worst case a dollar.** The founder's ceiling
is ~USD 5/month; this is two orders of magnitude under it. Removing CloudFront and the site
bucket from the request path made the bill *smaller*.

The three refusals worth naming:

* **No custom domain.** A hosted zone is $0.50/month — twenty-five times the rest of the
  stack combined — and it buys a prettier string in a form.
* **No Synthetics canary.** One canary at five-minute intervals is 8 640 runs/month ×
  $0.0012 = **$10.37/month**, roughly five hundred times the rest of the stack. The health
  check is a GitHub Actions cron against `/v1/health`, which costs nothing and whose
  failures are visible in the repository the judges are already reading.
* **No DynamoDB lock table.** Native S3 locking, since Terraform 1.10.

The only line that can grow without a ceiling is CloudWatch Logs, which is why
`log_retention_days` is validated against a short list and can never be `0`
("never expire").

---

## 9 · What has and has not been proven

Honesty is the moat, so this section is explicit.

**Measured on this machine, against live systems, 2026-08-10 and 2026-08-11:**

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

* **A live demo URL. There is none yet**, because `terraform apply` is gated on the
  founder's approval of the committed plan and that approval has not been given. Every
  artefact upstream of it is built, hashed and checked; `deploy.sh --dry-run` exits 0.
* **Stage 6's runtime behaviour end to end.** Reaching stage 6 requires stage 1 to create
  the state bucket and stage 2 to write the real `mainline_api` DSN to SSM. Stage 6 is
  therefore verified statically — exactly one executable `terraform apply`, unreachable
  without `MAINLINE_APPLY_APPROVED=1` — and by the `apply gate CLOSED` line the preflight
  prints on every run. Its first execution will be the approved one.
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
