<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
-->

# PRE-APPLY — the ordered gate the orchestrator walks before `terraform apply`

**Owner:** W7 (deploy-safety) · **Measured:** 2026-08-13, this machine, `AWS_PROFILE=mainline-dev`
**G1, G2, G3, G6 and G7 re-measured 2026-08-14** — G7 now has an executable form,
[`scripts/deploy/plan_repro.sh`](../../scripts/deploy/plan_repro.sh), and the plan it
reproduces is no longer eleven resources.
**Every command on this page is read-only.** Nothing here creates, changes or deletes an AWS
resource, and no `terraform apply` was run to produce it.

---

## 0 · What this page is, and what it is not

[`RUNBOOK.md`](RUNBOOK.md) already documents **how** to create each precondition — §5.1 for
the state bucket, §5.2 for the SSM SecureString, §5.3 for the database, §5.4 for the
package. Those procedures are correct and are **not repeated here**. Duplicating them would
create a second copy to drift.

What did not exist until this page is the **gate**: the preconditions in the order they must
hold, the one read-only command that *proves* each one, the output that counts as proof, and
what to run when the proof comes back empty. A procedure tells you how to do a thing. A gate
tells you whether it has been done, and refuses to move on when it has not.

**Two of these preconditions are absent from the account right now.** Measured today, both
commands below returned nothing:

```
$ aws ssm describe-parameters --region ap-southeast-1 --query 'Parameters[].Name'
[]

$ aws s3api list-buckets --query "Buckets[?starts_with(Name, 'mainline-')].Name"
[]
```

The Lambda's `MAINLINE_DSN_PARAM` points at `/mainline/demo/cockroach_dsn`, which does not
exist. The S3 backend wants `mainline-demo-tfstate-<account>`, which does not exist. **An
apply attempted right now dies at `terraform init`, before it ever reaches the concurrency
problem in G6.** That is the honest state of the account, and G2 and G3 are where it gets
fixed.

### The rule this page runs on

> **A gate that cannot be proven is a gate that failed.** Not "probably fine", not "it was
> there last week". If the proving command does not print the expected output, stop, run the
> remedy, and re-run the proving command. There is no gate on this page whose proof costs
> more than a few seconds.

### One asymmetry worth knowing before you start

**G3 is the only gate `terraform apply` cannot fail on.** Terraform *constructs* the parameter
ARN from `var.dsn_parameter_name` (`infra/modules/demo-api/main.tf:118`); it never reads the
parameter, and there is no `data "aws_ssm_parameter"` anywhere in this tree. So an apply with
no parameter in Parameter Store **succeeds, creates all twenty-four resources, and produces a
demo whose first request cannot reach a database.** The handler resolves `$MAINLINE_DSN_PARAM` on
cold start, the signed `GetParameter` comes back `400 ParameterNotFound`, and `db.py` raises
`DsnUnavailable` — a type that exists precisely because *"nobody told this function where the
database is"* and *"the database did not answer"* are fixed by different people.

It is not undetectable, and the distinction matters for how much this gate is worth:
**Terraform will not notice; stage 5.7 of the deploy will.** Its `/v1/health` assertion
refuses to print a URL unless `database` equals `mainline_demo`, and a missing parameter
surfaces there as `503 dsn_unset` ([`RUNBOOK.md` §5.7](RUNBOOK.md#57--publish-and-prove-the-hostname-over-https)).
So the cost of skipping G3 is not a silent broken demo — it is a **failed deploy after the
billable, irreversible step**, with twenty-four resources standing and a teardown to run. Two
seconds here, or a full apply-and-destroy cycle there.

---

## 1 · The gate, in order

| # | Precondition | Proven by | Absent today? |
|---|---|---|---|
| G0 | The tree is a **complete** checkout of the reviewed commit, and the toolchain matches | `plan_repro.sh` stage 0 / `terraform version` | no |
| G1 | The caller is the intended identity in the intended account | `aws sts get-caller-identity` | no |
| G2 | The Terraform state bucket exists and is configured | `aws s3api list-buckets` | **YES — ABSENT** |
| G3 | The DSN SecureString exists in Parameter Store | `aws ssm describe-parameters` | **YES — ABSENT** |
| G4 | CockroachDB Cloud carries the schema and the one seeded permit | `seed_demo.py --check` | no |
| G5 | The Lambda zip exists and its manifest matches it byte for byte | `bundle_manifest.py` | no |
| G6 | The account concurrency ceiling still reads 10, and the plan asks for `-1` | `get-account-settings` | no |
| G7 | The plan is 24 resources and is the artefact the founder reviewed | `plan_repro.sh` | no |
| G8 | The cost decision has been taken and recorded | read `COST-BOUND.md` §6 | — |
| G9 | `MAINLINE_APPLY_APPROVED=1` is set by a human who read G7 | `echo` | no |

The order is not cosmetic. G6 must precede G7 because a plan carrying a positive reservation
is a plan that dies partway through the apply with resources already created. G9 is last
because it is the only gate whose subject is a person.

**One ordering constraint was removed on 2026-08-14, and saying so is the point.** This page
used to read *"G2 must precede G7 because `terraform init` fails without the bucket"* — which
made the plan the founder approves unreachable until somebody had created an S3 bucket, i.e.
until after the first mutating AWS call. It no longer holds:
[`scripts/deploy/plan_repro.sh`](../../scripts/deploy/plan_repro.sh) reproduces the shipping
plan against a **local** backend and makes no mutating call, so **G7 can be walked before
G2**, by a reviewer with read-only credentials, on a clean checkout. G2 remains a gate for
the apply — the apply writes real state and needs the real bucket — but it is no longer a
gate for *reading the plan*. The equivalence that makes the local reproduction faithful, and
the moment it expires, are in G7.

---

## G0 · The tree is the reviewed commit, and the toolchain matches

**Must be true:** the working tree is clean, at the commit whose plan the founder reviewed,
and the four tools are the versions the plan was produced with. A plan generated by a
different Terraform minor is not the plan that was approved.

```bash
git -C . status --porcelain          # expect: no output
git -C . rev-parse --short HEAD      # expect: the commit named in the approval
terraform version                    # expect: Terraform v1.14.8
aws --version                        # expect: aws-cli/2.x  (v2 is not negotiable)
.venv/Scripts/python.exe --version   # expect: Python 3.13.x
```

Measured today: `Terraform v1.14.8`, `aws-cli/2.32.21`, `Python 3.13.14`.

### G0.1 — "clean" is not "complete", and on Windows the difference is silent

**`git status --porcelain` printing nothing does not establish that this tree is the
repository.** Measured on TRAPPOINT, 2026-08-14, cloning `7535670` into a 125-character
parent without `core.longpaths`: `git clone` printed **"Clone succeeded, but checkout
failed"** and exited `128`, two of 7,577 tracked paths never reached the disk, the index was
never written — and therefore:

| the question you would ask | the answer you would get | the truth |
|---|---:|---:|
| `git ls-files --deleted` | **0** | 2 paths missing |
| `git ls-files \| wc -l` | 0 | HEAD names 7,577 |
| `git status --short` rows | 7,613 | 7,575 files were present |
| missing under `infra/`, `scripts/deploy/`, `evidence/deploy/`, `docs/deploy/` | 0, 0, 0, 0 | 0, 0, 0, 0 — **all true** |

The last row is why this gate needs its own step. **Every path Terraform reads was present,
so `terraform init -backend=false` and `terraform validate` both succeeded** against a tree
that is not this repository, and the first three rows are three different wrong answers to
"is anything missing?" — one under-reporting to zero, one meaningless, one over-reporting by
three thousand.

The census that is not fooled is taken from `HEAD`, which the clone's object transfer wrote
successfully and no failed checkout can corrupt:

```bash
scripts/deploy/plan_repro.sh --prove-truncation-refusal <a directory holding a bad checkout>
# expect: verdict   REFUSED with exit 11   [ok — the truncated-checkout guard fires]
```

Stage 0 of `plan_repro.sh` runs that census on **every** invocation, before Terraform and
before the AWS CLI, and refuses with **exit 11**. G7 therefore carries this check for free;
this step is here so that the gate says out loud what G7 is relying on.

**If it fails:** re-clone with
`git clone --config core.longpaths=true --config core.autocrlf=false …`. Do not `git restore`
your way out of it — a checkout that aborted has an index that does not describe `HEAD`, and
every subsequent index-relative answer is unreliable.

**If it fails on the version table instead:** [`RUNBOOK.md` §4](RUNBOOK.md#4--prerequisites)
has the reasons each floor is a floor — Terraform ≥ 1.10 for `use_lockfile`, Python 3.13
exactly because `build_lambda.sh` fetches `cp313` wheels. On Windows, read §4's Git Bash trap
before blaming the tools: `bash` on `PATH` is WSL and has no AWS CLI.

---

## G1 · Identity and account assertion

**Must be true:** the credentials in scope belong to the account this deploy is meant to
touch. This account holds four unrelated live projects; an apply against the wrong one is
not recoverable by re-running anything.

```bash
aws sts get-caller-identity --query 'Arn' --output text
# expect: arn:aws:iam::<account>:user/mainline-dev

aws sts get-caller-identity --query 'Account' --output text
# expect: the twelve digits you are about to pass to --expect-account
```

Measured today: the ARN is `arn:aws:iam::<account>:user/mainline-dev`.

**Do not paste the account id into this file, a commit message, or a chat.** It is masked as
`0229REDACTED8246` across every tracked file in this repository (DECISION D2), and
`scripts/submission/audit_public_readiness.py` fails the build on a literal occurrence. It
travels as an argument to `--expect-account`, and nowhere else.

**If it fails:** `export AWS_PROFILE=mainline-dev`. If the ARN names a different principal,
stop — every remaining gate on this page would be measuring the wrong account, and each one
would pass or fail for reasons that have nothing to do with this deploy.

**Why the assertion is not optional even though the scripts do it too.** `deploy.sh` refuses
to run without `--expect-account` or `MAINLINE_AWS_ACCOUNT`
([`RUNBOOK.md` §3](RUNBOOK.md#3--which-aws-account-decision-d2)). This gate exists so the
orchestrator knows the value *before* it starts, rather than discovering at stage 0 that it
has been reading a different account's state for the last twenty minutes.

---

## G2 · The Terraform state bucket — **ABSENT TODAY**

**Must be true:** a bucket named `mainline-demo-tfstate-<account>` exists, versioned,
private, encrypted, and tagged. `backend.tf` declares an S3 backend with the bucket supplied
at `init` time, so without it `terraform init` fails and nothing downstream runs.

```bash
aws s3api list-buckets --query "Buckets[?starts_with(Name, 'mainline-')].Name" --output json
# expect: ["mainline-demo-tfstate-<account>"]
```

**Measured today: `[]`.** Seven buckets exist in this account and not one of them carries the
`mainline-` prefix. **This gate fails right now.**

Once it exists, the configuration is worth re-asserting rather than assuming — an unversioned
state bucket is a single overwrite away from an unrecoverable state file:

```bash
BUCKET=mainline-demo-tfstate-"$(aws sts get-caller-identity --query Account --output text)"
aws s3api get-bucket-versioning --bucket "$BUCKET"
# expect: {"Status": "Enabled"}
aws s3api get-public-access-block --bucket "$BUCKET" \
    --query 'PublicAccessBlockConfiguration'
# expect: all four true
aws s3api get-bucket-encryption --bucket "$BUCKET" \
    --query 'ServerSideEncryptionConfiguration.Rules[].ApplyServerSideEncryptionByDefault.SSEAlgorithm'
# expect: ["AES256"]
```

**To create it:** [`RUNBOOK.md` §5.1](RUNBOOK.md#51--state-backend) — `bootstrap_state.sh`,
which creates it with all four properties above and re-asserts them on every subsequent run.
It **refuses any bucket name outside the `mainline-demo-` prefix** (exit 2) before making a
single AWS call, because `teardown.sh` keys its own refusal on that prefix: a state bucket
named anything else would be created by our tools and then be undeletable by them.

> **`bootstrap_state.sh` WITHOUT `--print-backend-config` IS THE FIRST MUTATING ACTION OF
> THE ENTIRE DEPLOY.** `s3api create-bucket`, `put-bucket-versioning`,
> `put-bucket-encryption`, `put-bucket-tagging` and `put-bucket-lifecycle-configuration`
> (`scripts/deploy/bootstrap_state.sh:194–262`) all write. It belongs to **the orchestrator,
> with the founder** — the same pair who authorise the apply — and **no worker runs it**.
> Everything else on this page, and every step of
> [`RUNBOOK.md` §5.6.1](RUNBOOK.md#561--reproducing-the-plan-with-no-mutating-aws-call), is
> read-only and can be walked before this bucket exists.

To see the exact `-backend-config` line without writing anything — the script documents this
mode at `bootstrap_state.sh:92` as making **zero** AWS calls:

```bash
scripts/deploy/bootstrap_state.sh --print-backend-config --bucket "$BUCKET"

# or, deriving the name from the live caller identity (one read-only sts call):
scripts/deploy/plan_repro.sh --print-backend-config
```

Measured 2026-08-14, account masked:

```
  terraform init \
    -backend-config="bucket=mainline-demo-tfstate-<account>" \
    -backend-config="region=ap-southeast-1"
```

**If it fails with 403 on `head-bucket`:** the name is taken by another AWS customer — S3
bucket names are global. Choose another and pass `--state-bucket`. Do not retry.

---

## G3 · The DSN SecureString — **ABSENT TODAY**

**Must be true:** `/mainline/demo/cockroach_dsn` exists in Parameter Store in
`ap-southeast-1` as a `SecureString`, holding the `mainline_api` DSN.

```bash
aws ssm describe-parameters --region ap-southeast-1 \
    --query 'Parameters[].[Name,Type]' --output json
# expect: [["/mainline/demo/cockroach_dsn","SecureString"]]
```

**Measured today: `[]`.** No parameter under `/mainline/` exists in this region. **This gate
fails right now** — and, per §0, it is the one failure the apply itself will not tell you
about.

Assert the **type**, never the value. `--with-decryption` is not part of any check on this
page and must not be added to one: a gate that prints the DSN to prove the DSN is there has
published the DSN.

```bash
aws ssm get-parameter --name /mainline/demo/cockroach_dsn --region ap-southeast-1 \
    --query 'Parameter.[Type,Version,LastModifiedDate]' --output json
# expect: ["SecureString", <n>, "<timestamp>"]   — no value, by construction
```

**To create it:** [`RUNBOOK.md` §5.2](RUNBOOK.md#52--the-secret) — `aws ssm put-parameter
--type SecureString --overwrite`, with the payload passed as `--cli-input-json file://…`
from a `0600` temp file removed in a trap, **so the DSN never enters an argument vector**,
`ps` output, or shell history. Read that section before typing the command by hand; the temp
file is the whole point of it.

**Terraform never sees this value**, which is why this gate is separate from G7. The module
is given the parameter *name* and grants `ssm:GetParameter` plus `kms:Decrypt` on that one
constructed ARN. `terraform show` cannot print a password Terraform never held — and, by the
same token, `terraform plan` cannot notice that the parameter is missing.

---

## G4 · CockroachDB Cloud — schema and seed

**Must be true:** the Cloud cluster answers **as `mainline_demo`**, carries the migrated
schema, and holds the one seeded permit the demo drives.

```bash
.venv/Scripts/python.exe scripts/deploy/seed_demo.py --check --out <scratch>/seed-check.json
# --check verifies only; it applies neither seed file. Exit 0 is the gate.
```

> **`--out` is not optional here, and leaving it off is how I found that out.** `--check`
> applies no seed and writes nothing to the database — but it still writes its evidence file,
> and its default path is the **committed** `evidence/deploy/cloud-seed.json`. Running the
> bare command replaced a real 2026-08-11 seeding transcript — one carrying an injected
> `40001` retry trail that a check-only run cannot reproduce — with a thinner record of the
> check. Nothing warned; the exit code was `0`.
>
> A recorded transcript is evidence, and a gate that quietly overwrites evidence on its way
> to proving something is a gate that costs more than it proves. **Always redirect `--out` to
> a scratch path.** If the bare command has already been run, `git checkout --
> evidence/deploy/cloud-seed.json` restores it; check `git status` before you commit
> anything.

Measured today, read-only against the live Cloud cluster, with `--out` redirected:

```
cluster       …aws-ap-southeast-1.cockroachlabs.cloud:26257/defaultdb
database      mainline_demo  (confirmed by SELECT current_database(); the DSN path segment
                              says 'defaultdb' and is never trusted)
permits       1 in mainline.permit, 1 is the demo permit
permit        dec0de00-0006-4000-8000-000000000001
state         dispositioned  open_blocking=1  gate_epoch=1  head_seq=2
MERGE         REFUSED [23514] gate_closed_when_issued (reported)
rollback      nothing_persisted=True
VERDICT       SEEDED AND REFUSABLE                                          exit 0
```

Independently, a direct read of the same cluster: `72` tables in schema `mainline`, and
exactly one row in `mainline.permit`, whose `permit_id` is the uuid above.

**That permit id is the gate, not a detail.** It is the id the public hostname hands out at
`/bundle/manifest.json`, and it is what `var.scenario_permit_id` must equal. Until recently
that variable defaulted to a uuid5 derivation **nothing had ever seeded**, while
`transitions._demo_guard` returns `423` only when `subject_id == scenario.permit_id` — so the
guard was armed at an id no caller would ever send, leaving four committing kernel POSTs
reachable by any anonymous caller on a URL with `authorization_type = NONE`. The default is
now `dec0de00-0006-4000-8000-000000000001` and it matches the row above. **If a future seed
changes this id, the guard disarms silently.** Compare them here, at the gate, where it is
one command:

```bash
awk '/variable "scenario_permit_id"/,/^}/' infra/modules/demo-api/variables.tf \
    | grep -E '^\s+default'
# measured: default     = "dec0de00-0006-4000-8000-000000000001"
# it must equal the permit_id the check above printed
```

(The `awk` range matters. `grep -A2 … | grep default` finds the word *default* inside the
variable's prose and prints a sentence instead of the value — a command that looks like it
answered.)

**If the schema is missing or drifted:** [`RUNBOOK.md` §5.3](RUNBOOK.md#53--the-database).
`cloud_chain.py` exit `3` means *refused, nothing changed* — the migration tree and the live
schema disagree — and is a feature, not a failure. Cloud needs the **`40001`
`RETRY_SERIALIZABLE` retry loop**; every applier here has one, so a bare `40001` reaching you
means something re-ran a statement outside it.

---

## G5 · The Lambda package and its manifest

**Must be true:** the zip named in `-var lambda_package_path` exists, its manifest describes
*that* zip byte for byte, and it carries the four roots the handler serves from.

```bash
.venv/Scripts/python.exe scripts/deploy/bundle_manifest.py \
    out/lambda/mainline-demo-api-arm64.zip --quiet
# expect a line ending: VERDICT PASS
```

Measured against the committed package shape (`evidence/deploy/cost/package-shape.json` →
`architectures[arm64].after`, the **post-strip, deployed** package):

```
bundle_manifest: mainline-demo-api-arm64.zip sha256=09af589c…30f45914 zipped=7646264
                 unzipped=26117193 entries=246 VERDICT PASS
manifest sha256 == zip sha256 on disk:  True
runtime python3.13   architecture arm64
```

> **CORRECTED 2026-08-14 — THIS BLOCK QUOTED THE PRE-STRIP PACKAGE AND CALLED IT "MEASURED
> TODAY".** The struck figures — ~~`sha256=c85d7f00…b5b8a4b0 zipped=7989296
> unzipped=28364357 entries=206`~~ — are `architectures[arm64].**before**` in the same
> evidence file: the packer's input, before `--strip-source-maps` became the default and
> before the `.gz` siblings were written. They were never wrong, they were **the wrong
> tree**, presented in the present tense (RULING 2: *a figure that does not name its tree is
> wrong whichever tree it came from*). The entry count moves **up** 206 → 246 because 57
> `.gz` siblings are added, while both byte figures move **down** because 18 source maps
> totalling 2 586 960 B are removed — which is why a reader who only checked "the number got
> bigger" would not have caught this.
>
> **A rebuild on this machine today does NOT reproduce that sha, and that is expected rather
> than a defect.** `out/lambda/mainline-demo-api-arm64.zip` currently hashes
> `cb34e123…f09cb9b` at 250 entries / 7 701 872 B zipped, because the working tree carries
> source files not yet committed at HEAD `eefae1c` (`defeaters.py`, `retry.py`). **The
> `web/**` tree is byte-identical either way — 114 entries, 1 274 342 B, 0 source maps** —
> so every cost and ceiling claim that rests on the served tree is unaffected. The
> whole-package sha becomes reproducible again once those sources are committed and
> `package-shape.json` is regenerated; that file belongs to whoever owns `evidence/`.

**The architecture in the filename and in `-var lambda_architecture` must agree.** A mismatch
is a clean plan, a clean apply, and an `ELFCLASS` error on the first request — which reads
like a database problem and is not.

**Why the roots are checked and not assumed.** Under D1 the zip is the entire deployable. A
package missing `web/index.html` deploys cleanly, answers `/v1/health` with a green `200`,
and **404s the URL a judge opens**, because `static_site.resolve()` will not fall back to
`index.html` under `/assets/` or `/bundle/`. That is the most expensive failure available to
this project and it costs one `zipfile.namelist()` to prevent.

### G5.1 — on a fresh clone this gate is reached by building, and the build has an order

`out/` and `dist/` are gitignored, so **a clone has no package and no console to build one
from**, and `filebase64sha256` is evaluated at *plan* time — so G7 cannot be walked before
this one on a fresh machine. [`RUNBOOK.md` §5.6.0](RUNBOOK.md#560--from-git-clone-to-plan-24-to-add--the-ordered-walk-measured-end-to-end)
is the walk, measured end to end on 2026-08-14 from a clone of `7535670`:

```
pnpm install --frozen-lockfile              exit 0
pnpm exec vite build --mode demo            exit 0   → dist/, 49 files
python3.13 -m venv .venv                    exit 0
scripts/deploy/build_lambda.sh --arch arm64 exit 0   → VERDICT PASS, 250 entries, 7 702 186 B
```

> **`--mode demo`, and not `pnpm run build`.** Both exit 0. The production-mode build makes a
> `dist/` that `build_lambda.sh`'s own console check then objects to — *"carries neither
> `VITE_MAINLINE_API_BASE` nor `VITE_MAINLINE_BUNDLE_URL` … a website with no data"* — and it
> would deploy cleanly, pass `/v1/health`, and render **no source on every surface** in front
> of a judge. The demo-mode build reads the tracked `.env.demo` and the same check then prints
> `VITE_MAINLINE_BUNDLE_URL=./bundle/`. **The artefact check is the authority here, not the
> command**: `scripts/deploy/deploy.sh:879` runs `pnpm run build`, which is that script's line
> to correct, and it is reported to its owner rather than edited from this page.

**If it fails:** [`RUNBOOK.md` §5.4](RUNBOOK.md#54--the-lambda-package). Rebuild; do not
hand-edit the manifest. The manifest is a description of the zip, and a description that was
adjusted to match is not a check.

---

## G6 · The concurrency ceiling, re-checked — and what the plan asks for

**Must be true:** the account ceiling is still what the plan was designed against, and the
plan asks for a reservation this account can accept.

```bash
aws lambda get-account-settings --region ap-southeast-1 \
    --query 'AccountLimit.[ConcurrentExecutions,UnreservedConcurrentExecutions]' --output json
# expect: [10, 10]

aws service-quotas get-service-quota --service-code lambda \
    --quota-code L-B99A9384 --region ap-southeast-1 \
    --query 'Quota.[QuotaName,Value,Adjustable]' --output json
# expect: ["Concurrent executions", 10.0, true]
```

Measured today: `10`, and `["Concurrent executions", 10.0, true]`.

Measured 2026-08-14: `[10, 10]`, unchanged.

Then, in the plan artefact G7 produces:

```bash
grep -E '^ *\+ *reserved_concurrent_executions +=' <the plan text>
# expect: + reserved_concurrent_executions = -1
# a POSITIVE value here means the apply WILL fail — see below
```

> **The pattern is anchored on the assignment, and the earlier revision of this page was
> not.** A bare `grep reserved_concurrent_executions` now matches the concurrency alarm's
> `alarm_description` first, because that prose explains why the reservation is `-1`. It
> prints a paragraph and looks like it answered — the same failure G4 records for
> `grep -A2 … | grep default`. `plan_repro.sh` asserts this one for you and exits **9** on a
> positive reservation.

**Why this gate is not paperwork.** Any positive reservation is refused on an account whose
`UnreservedConcurrentExecutions` is 10, and `PutFunctionConcurrency` happens *after* the
function it configures exists — so when it is refused, resources are already standing and
the deploy has to be torn down rather than retried. `-1` removes the reservation; because
`min(20, 10) = 10`, the physical bound is unchanged and the cost ceiling does not move — it
was always the account, never the reservation.

> **A number was removed here rather than updated, on purpose.** This paragraph used to say
> `PutFunctionConcurrency` is *"the sixth of eleven API calls"* and that *"five resources
> already exist"* when it fails. Those ordinals were derived from an eleven-resource plan;
> the plan is now twenty-four, the call order is Terraform's dependency graph, and **the only
> way to observe the real ordinal is to run an apply** — which is the one thing this page
> exists to gate. An ordinal that cannot be re-measured read-only is not evidence, so it is
> gone rather than guessed at. The property that matters survives without it: the refusal
> lands after creation has started.

> **STANDING WARNING — `L-B99A9384` is `Adjustable: true` at 10, and nobody requests an
> increase.**
>
> That ceiling was the **only real bound** on a Function URL with `authorization_type = NONE`
> when this warning was written. It is no longer the only one — the response ceiling
> (139,264 B, derived from the deployed tree), the source-map strip, and the in-handler rate
> limiter have all landed since — **but it is still the load-bearing one**, because every
> other bound divides a number that this one sets.
>
> Every dollar in [`COST-BOUND.md` §0.1](COST-BOUND.md) scales very nearly linearly with it:
> at a quota of 100 the 30-day worst case is ≈ $325,000; at AWS's usual default of 1 000 it
> is ≈ $3.2 M. It got to 10 by accident and it is one support ticket away from being gone.
> Not for load testing, not "temporarily for judging". **A change that appears to need a
> higher ceiling is a change that is wrong.**
>
> The worst case at the quota of 10 is also **not $33,250** — that figure assumed a 100 ms
> invocation nobody had measured. At the measured duration it is **$229,805** before the
> shipped levers and **$47,278** after them, which is why the stop
> (`infra/modules/cost-guard/`) is the item on this checklist that matters most.
>
> **That parenthesis used to end "still not instantiated", and that is no longer true.** The
> module is instantiated at `infra/envs/demo/main.tf:631`, it contributes thirteen of the
> twenty-four resources in G7's plan, and its three alarms appear in the plan text as
> `mainline-demo-api-invocations-burst`, `-invocations-hourly` and `-log-ingestion`. The
> sentence is corrected rather than deleted, because a checklist that quietly drops the item
> it was most worried about reads, afterwards, as if nobody had been worried.

---

## G7 · The plan — 24 resources, and the one the founder reviewed

**Must be true:** `terraform plan` regenerates the artefact the founder approved, and the
count has not moved *since that artefact was committed*.

One command, and it is the whole gate:

```bash
scripts/deploy/plan_repro.sh
```

**Re-measured 2026-08-14 from a genuinely fresh `git clone` of `master` = `7535670`, on a
path that had never held this repository and a machine holding no `out/`.** That is the
difference between "the gate passes here" and "the gate passes"; the ordered chain that gets
a clone to this point — console build, interpreter, package — is
[`RUNBOOK.md` §5.6.0](RUNBOOK.md#560--from-git-clone-to-plan-24-to-add--the-ordered-walk-measured-end-to-end),
and the whole transcript with every exit code is
[`evidence/deploy/lead/plan-repro-fresh-clone.json`](../../evidence/deploy/lead/plan-repro-fresh-clone.json).
The run took 79 s and exited 0.

**This is an ABRIDGEMENT, not a verbatim copy** — the account id is masked, absolute scratch
paths are dropped, and so are the script's own explanatory lines, leaving the lines this gate
asserts on. No value is changed and no line is reordered. The unabridged transcript is in
[`RUNBOOK.md` §5.6.1](RUNBOOK.md#561--reproducing-the-plan-with-no-mutating-aws-call), and the
authority is the command.

```
== 0 · this is a complete checkout of this repository (no terraform, no AWS, no network)
  HEAD                   7535670  (7577 tracked path(s))
  on disk                7577 of 7577 present   (7577 file(s) walked)
  index                  7577 entr(ies)
  worktree eol           0 of 50 file(s) under infra/ converted on checkout

plan_repro — reproducing the shipping plan with no mutating AWS call

== 1 · identity (read-only)
  caller                 arn:aws:iam::<account>:user/mainline-dev
  region                 ap-southeast-1
  profile                mainline-dev

== 2 · the empty-state equivalence, measured read-only
  state buckets          none — no mainline-demo-tfstate-* bucket in this account
  lambda mainline-demo-api does not exist   [equivalence holds]

== 3 · a local backend, outside the repository, starting empty
  override               infra/envs/demo/backend_override.tf  (removed on exit, any exit)
  state now              absent/empty

== 4 · terraform init -reconfigure / validate / plan
  init                   ok
  validate               Success! The configuration is valid.
  plan                   ok

== 5 · the plan, and the committed artefact
  fresh plan             Plan: 24 to add, 0 to change, 0 to destroy.
  committed artefact     evidence/deploy/terraform-plan-furl.txt  says Plan: 24 to add
  G6 reservation         reserved_concurrent_executions = -1
  G7 zero-mask           0 occurrence(s) of twelve zeros   (expected 0)
  account id             12 occurrence(s) in the RAW plan text — mask before it enters evidence/
exit=0
```

### Why a local backend is a faithful reproduction, and when it stops being one

`terraform init -backend=false` is **not sufficient** on this tree — `plan` then refuses with
*"Changes to backend configurations require reinitialization"*, because `backend.tf` declares
S3 — and a real `-backend-config` needs an S3 bucket that does not exist yet and cannot be
created without a mutating call (G2). So the reproduction points Terraform at a **local**
backend whose state file lives outside the repository and starts empty. **That is faithful
only because nothing has been applied: the remote S3 state is empty, an empty local state and
an empty remote state hold the same zero resources, and a plan is a function of the
configuration plus the state — so same configuration plus same empty state gives the same
plan. THIS EQUIVALENCE EXPIRES AT THE FIRST `terraform apply`.** From the moment one resource
exists remotely, a plan against an empty local state reports creating things that already
exist, and every count it prints is wrong in the direction that reads like success. After the
first apply, the only correct plan is the one against the real backend —
[`RUNBOOK.md` §5.6.2](RUNBOOK.md#562--the-real-s3-backend--the-path-the-founder-applies-from).

`plan_repro.sh` does not merely assert that precondition, it **measures it on every run**
(stage 2, three read-only calls: `s3api list-buckets`, `s3api head-object`,
`lambda get-function`) and refuses with **exit 5** when it no longer holds. The refusal is
falsifiable in one command, pointed at a Lambda that does exist elsewhere in the account:

```bash
scripts/deploy/plan_repro.sh --prove-expiry-refusal <an existing function> --region <its region>
# measured 2026-08-14: "THE EQUIVALENCE HAS EXPIRED", verdict REFUSED with exit 5   [ok]
```

### 24 is a contract

The count is quoted across `JUDGE-PACK.md`, `docs/submission/DEVPOST.md`,
`docs/submission/JUDGE-START.md`, `docs/STATE-OF-THE-BUILD.md` and
`scripts/submission/check_submission_ready.py`. A plan that adds a twenty-fifth resource has
not just changed the infrastructure — it has falsified five documents nobody edited.

**Do not take that list on trust; it rots.** The live authority is
`tests/deploy/test_cost_model.py::test_the_shipping_plan_count_in_the_docs_matches_the_plan_evidence`,
which fails naming *every* live document quoting a count no committed artefact supports, and
its sibling `…_is_actually_stated_somewhere_live`, which fails if the count is deleted rather
than corrected. **The committed plan artefact is authoritative and the prose is derived.**
Never regenerate or reconfigure a plan in order to obtain the number a document already
carries.

The count moved 11 → 24 when `module "guard"` was instantiated at
`infra/envs/demo/main.tf:631` (`:632` is its `source` line). It is 11 + 13, not 11 + 14:
`cost-guard` declares fourteen `resource` blocks, and `aws_sns_topic_subscription.email`
(`infra/modules/cost-guard/main.tf:337`) is **`for_each = toset(var.notification_emails)`**
— ~~`count = length(var.notification_emails)`~~ — over a list that defaults to empty, so it
plans zero instances.

### Also assert, on the plan text

* `reserved_concurrent_executions = -1` (G6) — `plan_repro.sh` exits **9** if it is positive
* the `-concurrency` alarm's `threshold` is **below 10** — a threshold at or above the
  account ceiling is an alarm that cannot fire, which is a control that looks present and is
  not. Measured in the 2026-08-14 plan: `8`
* **zero** occurrences of a twelve-zero placeholder — two checkers disagreed about whether
  twelve identical digits is a mask or a value, and the resolution recorded in
  [`docs/CI-STATE.md`](../CI-STATE.md) is to remove the digits rather than relax either
  checker

```bash
grep -cE '(^|[^0-9])0{12}([^0-9]|$)' <the plan text>     # expect: 0
```

(The pattern is written as a repeat rather than spelled out, so that this gate does not
itself become an occurrence of the string it is checking for.)

> **A correction this gate owes its own reader.** The earlier revision also demanded *"zero
> occurrences of the real account id"* **in the plan text**, and that is false of any plan
> anybody actually runs: the root reads `data.aws_caller_identity.current`, so the account id
> is in the output by construction — **12 occurrences** in the 2026-08-14 FURL plan, 19 in
> the CloudFront variant. Zero is the property of the **committed, masked artefact**, not of
> the raw plan, and conflating the two makes a correct plan look like a leak. `plan_repro.sh`
> therefore *counts* the occurrences and says plainly that the raw file must be masked before
> it enters `evidence/`; it writes that file **outside the repository** and refuses an
> `--out-dir` inside it.

**Nothing on this page runs `terraform apply`.** `plan_repro.sh` cannot: every Terraform
invocation in it passes one allowlist of `init`, `validate`, `plan`, `show`, `version`, and
`--prove-refusal` demonstrates seven refusals in about a second. The orchestrator applies,
after the founder re-authorises, and it applies **the saved plan file** — what was reviewed
is what runs.

---

## G8 · The cost decision has been taken and recorded

**Must be true:** somebody with the authority to spend the money has read
[`COST-BOUND.md`](COST-BOUND.md) and recorded which levers are being taken.

This gate does not have a correct answer and this page does not supply one. What it requires
is that the answer **exists and is written down** before the apply, rather than being
reconstructed afterwards from a bill. The material is `COST-BOUND.md` §3 (the menu, nine
levers with what each does and does not bound) and §6 (the recommendation). The arithmetic is
in §2 and is not repeated here or in the runbook.

Record, in the approval:

- [ ] which levers are taken, by number
- [ ] the resulting worst case, from the menu row — not re-derived
- [ ] that `RUNBOOK.md` §8's two-bill split has been read: a steady state of ≈ $0.02/month,
      and an adversarial case bounded only by G6's ceiling. **Take the adversarial figure
      from `COST-BOUND.md` and from nowhere else.** This checklist used to carry the range
      *"USD 11,538–33,257"*; that range assumed a 100 ms invocation nobody had measured, is
      understated about sevenfold at the measured duration, and is not restated here —
      a second copy of a number is a second thing that can be stale, and this one already was
- [ ] that the kill switch has been located before it is needed:
      `scripts/deploy/kill_switch.sh --status` is read-only and answers in one line

---

## G9 · `MAINLINE_APPLY_APPROVED`

**Must be true:** the environment says a human read G7's plan and approved *that* plan.

```bash
echo "${MAINLINE_APPLY_APPROVED:-<unset>}"
# expect: 1
```

`deploy.sh` contains **exactly one** executable `terraform apply` and it is unreachable
unless `MAINLINE_APPLY_APPROVED=1`; `deploy.ps1` is the same shape. Both print the gate's
state — `OPEN` or `CLOSED` — during preflight, on every run, before anything happens. Without
it the script stops at stage 6 and exits **7**, which is the designed halt and not a failure:

```
STOPPED AT THE APPROVAL GATE — stage 6 planned, and did not apply.
```

**This variable is exported for one run and then unset.** A shell that carries
`MAINLINE_APPLY_APPROVED=1` is a shell in which every later `deploy.sh` — including one typed
out of muscle memory to check something — applies. The gate is not a setting; it is a
signature on one plan.

---

## 2 · The gate as one pass

Copy-paste, read-only, stops nowhere on its own — **read every line before you act on the
last one**. This prints proofs; it does not decide anything.

```bash
export AWS_PROFILE=mainline-dev
REGION=ap-southeast-1

echo "== G1 identity ==";  aws sts get-caller-identity --query Arn --output text
echo "== G2 bucket ==";    aws s3api list-buckets \
    --query "Buckets[?starts_with(Name,'mainline-')].Name" --output json
echo "== G3 parameter =="; aws ssm describe-parameters --region "$REGION" \
    --query 'Parameters[].[Name,Type]' --output json
echo "== G4 database ==";  .venv/Scripts/python.exe scripts/deploy/seed_demo.py --check \
    --out "$(mktemp -t seed-check-XXXX.json)"          # --out: see G4, it is not optional
echo "== G5 package ==";   .venv/Scripts/python.exe scripts/deploy/bundle_manifest.py \
    out/lambda/mainline-demo-api-arm64.zip --quiet
echo "== G6 ceiling ==";   aws lambda get-account-settings --region "$REGION" \
    --query 'AccountLimit.[ConcurrentExecutions,UnreservedConcurrentExecutions]' --output json
echo "== G7 plan ==";      scripts/deploy/plan_repro.sh     # local backend, no mutating call
echo "== G9 approval ==";  echo "MAINLINE_APPLY_APPROVED=${MAINLINE_APPLY_APPROVED:-<unset>}"
```

Run against this account on 2026-08-14, that pass prints an ARN, **`[]`**, **`[]`**, a green
database, `VERDICT PASS`, `[10,10]`, `Plan: 24 to add` at exit 0, and `<unset>`. **Two empty
brackets and an unset variable: the apply is three gates away, and the two empty ones are G2
and G3.**

**G7 is now in that pass, and it was not before.** It could not be, while reading the plan
required a state bucket that only a mutating call creates. `plan_repro.sh` takes about
fifteen seconds and is the only line above that runs Terraform at all.

---

## 3 · After the apply — the first thing to read

Not part of the gate, but the gate is where you learn the command, because after the apply
you will want it inside a minute:

```bash
.venv/Scripts/python.exe scripts/deploy/aws_live_probe.py --alarms-only
```

Read-only, free, and the **only alarm reader that can exist** — there is no CI reader,
because no AWS credential exists in any workflow in this repository.
[`OBSERVABILITY.md`](OBSERVABILITY.md) §3 says why, and what each alarm state means. Measured
2026-08-14, that command exits `3` and prints four `DOES NOT EXIST` lines, which is the
correct answer for an unapplied stack and is exactly the reading this page's G2 and G3
predict.

> **Four, and the plan now creates seven. Read this before trusting a green from it.**
> `aws_live_probe.py:179` carries `ALARM_SUFFIXES = ("-errors", "-throttles",
> "-duration-p99", "-concurrency")` — a hard-coded four. The 2026-08-14 plan creates **seven**
> alarms whose names begin `mainline-demo-api`: those four plus
> `-invocations-burst`, `-invocations-hourly` and `-log-ingestion`, which are the guard's, and
> the guard's are the ones wired to the stop. So *after* the apply this probe will report
> *"All 4 alarms exist and none is in ALARM"* while never having looked at the three that
> matter most — a reader that is complete-looking and is not. **This is a finding against
> `scripts/deploy/aws_live_probe.py`, which this page does not own**; it is recorded here
> because this page is where the command is learned, and a caveat that lives only in the
> owner's backlog is a caveat nobody reads at 3 a.m.
