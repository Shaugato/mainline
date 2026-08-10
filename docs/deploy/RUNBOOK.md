<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# THE DEPLOY RUNBOOK — clean checkout to a demo URL, and back to nothing

**What this page is.** The one command that produces the demo URL, what each of its nine
stages does, what to do when each one fails, how to remove everything afterwards, and what
it costs — with the arithmetic, not a claim.

**What it is not.** A design document. That is
[`docs/leads/deploy-plan.md`](../leads/deploy-plan.md). The Terraform is explained in
[`infra/envs/demo/README.md`](../../infra/envs/demo/README.md), the database in
[`docs/deploy/cloud-database.md`](cloud-database.md).

> **A note on the numbers below.** Everything marked *measured* was produced on this build
> machine against the live systems, and the transcript is quoted. Everything else is
> marked as an estimate. `docs/HONESTY.md` is the standing commitment; this page is
> written to it.

---

## ⛔ READ THIS FIRST — the deploy cannot complete on this AWS account today

**AWS account `022950218246` is not permitted to create CloudFront distributions.** A real
`terraform apply` of the Phase-1 path was run on 2026-08-10 and got as far as the
distribution before AWS refused:

```
module.site.aws_cloudfront_origin_access_control.s3: Creation complete after 2s [id=E2SG85QVMCDKDB]
module.site.aws_s3_bucket.site:                      Creation complete after 6s [id=mainline-demo-site-022950218246]
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

The identity has `AdministratorAccess`. `aws cloudfront list-distributions` returns
`None`; this account has never had one. This is an **AWS account-level verification hold**
that only AWS Support can lift.

### What to do, in this order

1. **Open an AWS Support case now** — Service: CloudFront, Category: account verification —
   and paste the error message above including its `RequestID`. This is usually cleared
   within hours, but it is a queue, not an API, and the deadline is 2026-08-18.
2. **Until it clears, `deploy.sh` / `deploy.ps1` will fail at stage 6** with that error.
   Everything before stage 6 works. The partial apply leaves seven resources (the bucket,
   its five configurations, and one origin access control); `terraform destroy` removed
   all seven, and `scripts/deploy/teardown.sh --yes` then removed the state bucket and
   verified no residue — both run for real, see § 3 and § 6.
3. **The Stage-One requirement is "a URL to a functional demo app", not "a URL served by
   CloudFront."** If the hold is not cleared in time, the architecture needs a fallback
   that does not touch CloudFront. That decision belongs to the deploy lead, not to this
   runbook, but the constraint it has to satisfy is worth stating: an S3 *website* endpoint
   is **HTTP-only** and therefore not an answer. A Lambda Function URL is HTTPS on an
   AWS-issued certificate at `https://<id>.lambda-url.ap-southeast-1.on.aws` and needs no
   CloudFront and no account verification — which makes "serve the console and the bundle
   from the same Lambda that serves `/v1/*`" the obvious candidate.

The rest of this page is written as though the hold is cleared, because everything in it
was verified as far as the hold allows and all of it is correct the moment it lifts.

---

## 0 · The one command

```powershell
# Windows (this build machine)
pwsh -File scripts\deploy\deploy.ps1
```

```bash
# Linux / macOS / Git Bash
scripts/deploy/deploy.sh
```

It ends by printing the URL and the judge access block. If it does not print a URL, it
exited non-zero and said which stage failed and what to do — **there is no path through
this script that prints a URL it did not just fetch over HTTPS.**

### The three flags that matter

| Flag | What it does |
|---|---|
| `--phase1` / `-Phase1` | Stop after stage 7. **No Lambda at all.** A complete HTTPS demo URL serving the console over the verified EvidenceBundle with a `REPLAY` badge. This is the cut line: *nobody is allowed to let the live path hold the URL hostage.* |
| `--dry-run` / `-DryRun` | Preflight, then check every artefact the other workers owe. Writes nothing. **Exits non-zero if anything is missing** — this is the check, not a preview. |
| `--preflight-only` / `-PreflightOnly` | Stage 0 and stop. Answers "is this machine able to deploy at all". |

Also: `--skip-db`, `--skip-build`, `--recreate-db`, `--any-account`, `--arch x86_64`,
`--interactive` (drop `-auto-approve` and show you the plan).

---

## 1 · Prerequisites

### Tools — measured on this machine, 2026-08-10

| Tool | Needed | Here | Checked by |
|---|---|---|---|
| AWS CLI | v2 | `aws-cli/2.32.21` | stage 0 |
| Terraform | **≥ 1.10** | `v1.14.8` | stage 0, with a version comparison |
| Python | 3.13 in `.venv` | `3.13.14` at `.venv/Scripts/python.exe` | stage 0 |
| Node | 20+ | `v24.14.0` | stage 0 |
| pnpm | any | `11.5.3` | stage 0 |
| curl | any | `C:\Windows\System32\curl.exe` | stage 0 |
| Git Bash | any | `C:\Program Files\Git\bin\bash.exe` | stage 0 (**PowerShell only**) |

**Terraform ≥ 1.10 is not negotiable.** `use_lockfile = true` — native S3 state locking —
arrived in 1.10, and this stack has deliberately no DynamoDB table to fall back to. Stage
0 compares the version and refuses below it.

**`uv` is not installed on this machine.** Every `just` recipe that shells out to `uv run`
is dead here. Every script in `scripts/deploy/` therefore calls
`.venv/Scripts/python.exe` by name.

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
| `AWS_PROFILE` | `mainline-dev` → account `022950218246`. Stage 0 **refuses any other account** unless `--any-account`. |
| `COCKROACH_DSN` | Admin DSN. Read from the repo-root `.env` if not exported. Needed by stage 3. |
| `MAINLINE_API_DSN` | The Lambda's DSN — `COCKROACH_DSN` with the userinfo swapped for `mainline_api`. Needed by stage 2 unless `--phase1`. |
| `MAINLINE_API_PASSWORD` | Alternative to the above: stage 2 derives the DSN itself. |

Mint the login passwords once, and capture them — they are printed once and never stored:

```bash
.venv/Scripts/python.exe scripts/deploy/cloud_roles.py --rotate
```

Then, in PowerShell:

```powershell
$env:MAINLINE_API_PASSWORD = '<the mainline_api password>'
```

**No script in `scripts/deploy/` ever prints a DSN or a password.** `deploy.sh` refuses to
run under `set -x` for that reason, and stage 2 builds its SSM payload in a temp file so
the DSN never enters an argument vector, `ps` output, or shell history.

---

## 2 · The nine stages

### Stage 0 — preflight

Identity, tool versions, interpreter, and whether the DSNs are available. Prints the
account id and the DSN's **host** — never the DSN.

**Refuses (exit 3) when:** the account is not `022950218246`; Terraform is below 1.10; the
venv is missing; on Windows, no Git Bash; `COCKROACH_DSN` is unset without `--skip-db`;
the Lambda DSN is unavailable without `--phase1`.

> **If it refuses on the account**, you have the wrong profile. This account holds seven
> buckets across four unrelated live projects; a deploy pointed at the wrong credentials
> still costs money and still has to be cleaned up by hand.

### Stage 1 — state backend

`scripts/deploy/bootstrap_state.sh` creates `mainline-demo-tfstate-<account>` if absent
and re-asserts its configuration every run. Measured, first run:

```
bootstrap_state
  account        022950218246
  region         ap-southeast-1
  bucket         mainline-demo-tfstate-022950218246
  exists         no — creating
  created        ok
  versioning     Enabled
  public         blocked (all four)
  encryption     SSE-S3 (AES256)
  tags           project=mainline, mainline:role=terraform-state
  lifecycle      noncurrent versions expire after 30 days
```

It **refuses a bucket name outside the `mainline-demo-` prefix** (exit 2), because
`teardown.sh` keys its own refusal on that prefix — a state bucket named anything else
would be created here and then be undeletable by our own tools.

**If it fails:** a `403` on `head-bucket` means the name is taken by another AWS customer
(S3 bucket names are global). Choose another name and pass `--state-bucket`. Do not retry.

### Stage 2 — the secret

`aws ssm put-parameter --type SecureString --overwrite` writes the Lambda's DSN to
`/mainline/demo/cockroach_dsn`. The payload goes in via `--cli-input-json file://…` from a
`0600` temp file removed in a trap, so the value never enters an argument vector. It is
read back **without** `--with-decryption` — only the type is asserted, so the script
cannot print the value even by accident.

**Terraform never sees this value.** It is given the parameter *name*; the Lambda role is
granted `ssm:GetParameter` + `kms:Decrypt` on that one ARN; the handler reads it once per
cold start from `$MAINLINE_DSN_PARAM` and caches it. `terraform show` cannot print a
password Terraform never held.

**If it fails:** the IAM identity needs `ssm:PutParameter` and `kms:Encrypt` on
`alias/aws/ssm`. Skipped entirely by `--phase1`.

### Stage 3 — the database

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

**If a file fails with `40001`:** it should not — every applier retries `40001` six times
with backoff. If one still surfaces, re-run; the chain is idempotent.

### Stage 4 — the Lambda package

`scripts/deploy/build_lambda.sh --arch arm64 --out out/lambda/mainline-demo-api-arm64.zip`.
arm64 is the default: ~20 % cheaper per GB-second, and `psycopg-binary` 3.3.4 publishes a
cp313 aarch64 wheel.

**The architecture in the filename and in `-var lambda_architecture` must agree.** The
deploy script drives both from one `--arch` flag precisely because a mismatch is a clean
plan, a clean apply, and an `ELFCLASS` error on the first request — which reads like a
database problem and is not.

Skipped entirely by `--phase1`.

### Stage 5 — the site payload

`pnpm install --frozen-lockfile && pnpm run build` in
`verticals/mainline/apps/console`, then `capture_demo_bundle.py` writes the verified
EvidenceBundle into `dist/demo-bundle`.

**If W8 documents a different build command**, set `MAINLINE_CONSOLE_BUILD_CMD` and re-run;
the script says so in its own failure message.

**If `capture_demo_bundle.py` is missing, the deploy FAILS.** It is not skipped and not
faked. The bundle is the Phase-1 demo and the console's `REPLAY` source; publishing
without it would serve a console with nothing to show.

### Stage 6 — infrastructure

`terraform init -reconfigure -backend-config=…` then `terraform apply`. Phase 1 passes
`-var enable_api=false`; phase 2 adds `lambda_package_path` and `lambda_architecture`.

Then one `terraform output -json deploy_summary` — one call rather than nine, because
reading nine outputs is nine chances to read eight of them.

**If it says the state is locked:** see § 5.

**If it reports a cycle:** it should not; see
[`infra/envs/demo/README.md` § The dependency that looks like a cycle](../../infra/envs/demo/README.md).
Both phases were measured to plan in one pass against the real modules.

### Stage 7 — publish

`aws s3 sync` + explicit content types + a CloudFront invalidation of `/index.html` and `/`.

**Content types are set explicitly and not left to `aws s3 sync`'s guess**, because that
guess comes from Python's `mimetypes`, which on Windows reads the registry. Measured with
this repository's interpreter:

```
.js    → application/javascript      fine
.mjs   → text/plain                  a module served as text/plain does not load
.map   → text/plain                  harmless
.woff2 → None                        falls back to binary/octet-stream
```

One wrong `Content-Type` on the entry chunk is a blank page with a console error, on the
one URL the whole submission depends on. So hashed assets go up `immutable` for a year,
`index.html` goes up `no-cache` — it is the only file whose name does not change when its
contents do — and each family names its own type.

The stage ends with **a live HTTPS check of the script's own**, in both phases: up to 20
attempts at 15 s, and the script exits non-zero rather than print a URL that answered
anything but `200`.

**If the check times out at `403`:** the objects uploaded but CloudFront cannot read the
bucket — check the OAC and the bucket policy in `infra/modules/demo-site`.
**At `404`:** `index.html` did not upload, or `default_root_object` is unset.

### Stage 8 — proof

`scripts/deploy/demo_acceptance.py --url <the URL>`, and **the deploy exits non-zero if it
does**. A phase-2 deploy that cannot show the live gate refusing, refusing under attack,
and then admitting — over HTTPS — is a failed deploy, and it says so rather than printing
a URL.

**If it fails:** `aws logs tail /aws/lambda/mainline-demo-api --since 10m`. Do not submit
the URL. `--phase1` ships the URL without the live path, honestly badged.

Skipped by `--phase1`, which has no live gate to prove.

### Stage 9 — hand-off

Prints the URL, the phase, the account, the bucket, the distribution, and the judge access
block — which says plainly that the URL needs no credential, names the read-only
`mainline_judge` login, and states that its password is *not stored by this script or
anywhere in the repository*.

---

## 3 · Teardown

```bash
scripts/deploy/teardown.sh --dry-run    # list what would go; delete nothing
scripts/deploy/teardown.sh --yes        # do it
```

On Windows: `& "C:\Program Files\Git\bin\bash.exe" scripts/deploy/teardown.sh --yes`.

Order, and it matters:

1. `terraform destroy` — distribution, Lambda, role, alarms, log group
2. the site bucket — **every version and every delete marker**, then the bucket
3. the SSM SecureString
4. `DROP DATABASE mainline_demo CASCADE`, then `mainline_api`, then `mainline_judge`
5. the state bucket, **last** — deleting it before step 1 leaves every AWS resource alive
   and unmanaged, recoverable only by importing them by hand

### The two safety gates

Every destructive step passes `assert_ours`, which requires **both**:

* the name begins with `mainline-demo-` (or `/mainline/` for the SSM parameter), and
* the **live** resource carries `project=mainline`, read back from AWS at the moment of
  deletion — not from Terraform state, not from a variable

Both were tested against real resources in this account:

```
$ scripts/deploy/teardown.sh --dry-run --site-bucket aws-cloudtrail-logs-022950218246-10882a56
teardown REFUSED
   bucket 'aws-cloudtrail-logs-...' does not carry the 'mainline-demo-' prefix.
exit=3

$ scripts/deploy/teardown.sh --dry-run --site-bucket mainline-demo-teardown-probe-…   # untagged
teardown REFUSED
   bucket 'mainline-demo-teardown-probe-…' has NO tags at all, so it cannot be shown to be ours.
exit=3

$ aws s3api put-bucket-tagging … 'TagSet=[{Key=project,Value=mainline}]'
$ scripts/deploy/teardown.sh --dry-run --site-bucket mainline-demo-teardown-probe-…
   WOULD DELETE s3://mainline-demo-teardown-probe-…, every object version in it, and every delete marker
exit=0
```

`--ignore-tags` relaxes the second gate. **Nothing relaxes the first.**

### Why versions, not just objects

`aws s3 rm --recursive` leaves noncurrent versions and delete markers behind on a versioned
bucket, and `delete-bucket` then fails with `BucketNotEmpty` over objects `aws s3 ls` does
not show. That is the single most common way a "successful" teardown leaves a bucket, and
a bill, behind. Teardown drains `Versions` and `DeleteMarkers` in two separate passes.

### Why `DROP DATABASE` comes before `DROP USER` — measured

Against the local CockroachDB v26.2.5 node, with the grant shape `cloud_roles.py`
produces:

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

## 4 · What it costs

Free tiers here are AWS's **perpetual** free tiers (CloudFront and Lambda), not the
12-month new-account ones, so the arithmetic does not expire.

| Line | Basis | Arithmetic | USD/month |
|---|---|---|---|
| CloudFront | perpetual free: 1 TB egress, 10 M requests | a judging round is ~10² requests and ~10⁻⁵ TB | **0.00** |
| S3 Standard, ap-southeast-1 | 3.2 MB console `dist` + bundle ≈ 12 MB | 0.012 GB × $0.025/GB | **0.0003** |
| S3 requests | served from the CloudFront cache after the first fetch | ~10³ GET × $0.0004/1 000 | **0.0004** |
| S3 state bucket | one small versioned object, noncurrent versions expire at 30 days | < 1 MB | **0.00003** |
| **State locking** | `use_lockfile = true` | **no DynamoDB table** | **0.00** *(vs $0.25)* |
| Lambda | perpetual free: 1 M requests, 400 000 GB-s | 512 MB × 300 ms × 10 000 req = 1 536 GB-s → 0.4 % of the allowance | **0.00** |
| CloudWatch Logs | 7-day retention | far under the 5 GB free ingest | **0.00** |
| CloudWatch alarms | 4 alarms; first 10 free | | **0.00** |
| SSM Parameter Store | Standard SecureString | Standard tier is free | **0.00** |
| Bedrock Titan Embed v2 | one seed pass ~200 k tokens, then ~50 tokens/query | 0.2 M × $0.02/M | **0.004** |
| CockroachDB Cloud Basic | inside the free allowance; `spend_limit` is a hard ceiling | | **0.00** |
| Route 53 / ACM | **not used** — CloudFront's default certificate and domain | | **0.00** |
| CloudWatch Synthetics | **not used** — see below | | **0.00** |
| | | **Total** | **≈ $0.005** |

**Round it to a cent a month, and call the worst case a dollar.** The two refusals worth
naming:

* **No custom domain.** A hosted zone is $0.50/month — a hundred times the rest of the
  stack combined — and an ACM certificate for CloudFront must be issued in `us-east-1`,
  which means a second provider alias. It buys a prettier string in a form.
* **No Synthetics canary.** One canary at five-minute intervals is 8 640 runs/month ×
  $0.0012 = **$10.37/month**, roughly two thousand times the rest of the stack. The health
  check is a GitHub Actions cron against `/v1/health`, which costs nothing and whose
  failures are visible in the repository the judges are already reading.

The only line that can grow without a ceiling is CloudWatch Logs, which is why
`log_retention_days` is validated against a short list and can never be `0` ("never
expire").

---

## 5 · When something goes wrong

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

### "Invalid count argument … cannot be determined until apply"

Something in `demo-site` is deriving `count` from `api_origin_domain` instead of
`enable_api`. See `infra/envs/demo/README.md` § Failure 2. Passing both inputs is the
contract, not a convenience.

### "Error: Cycle: … module.api (close) …"

Something reached the Function URL with a splat. It must be
`try(module.api[0].function_url_domain, "")`. See § Failure 1.

### The URL serves a blank page with a console error

Almost always a `Content-Type`. Check the entry chunk:

```bash
curl -sSI https://dXXXXXXXX.cloudfront.net/assets/index-XXXXXXXX.js | grep -i content-type
```

It must be `text/javascript` or `application/javascript`, never `text/plain`. Stage 7 sets
these explicitly; if you uploaded by hand, that is the difference.

### The URL 404s but the bucket has the files

`default_root_object` on the distribution, or `index.html` did not upload. Re-run stage 7:
the script is idempotent.

### `/v1/*` returns 403

The Function URL is `AWS_IAM`-authenticated and **is meant to be uninvocable except through
CloudFront**. A 403 through CloudFront means the OAC or the `aws_lambda_permission` is
wrong; a 403 when you curl the Function URL directly is the design working.

### The demo is broken and judging starts in an hour

```powershell
pwsh -File scripts\deploy\deploy.ps1 --phase1
```

Same URL, no Lambda, `REPLAY` badge, the verified EvidenceBundle. It cannot be broken by
anything in the API. **That is what Phase 1 is for.**

---

## 6 · What has and has not been proven

Honesty is the moat, so this section is explicit.

**Measured on this machine, against live systems, 2026-08-10:**

* `terraform validate` and `terraform plan` against the real `demo-site` and `demo-api`
  modules — **9 resources in phase 1, 22 in phase 2, one pass, no cycle**
* the cycle and the `Invalid count` error that shaped the wiring — both reproduced, both
  transcribed above and in `infra/envs/demo/README.md`
* **a real `terraform apply` against the real S3 backend.** State lock acquired and
  released; seven resources created; the eighth — the CloudFront distribution — refused by
  AWS for account verification (see the banner at the top). `terraform destroy` then
  removed all seven.
* `bootstrap_state.sh` creating the real state bucket, versioned, private, SSE-S3,
  tagged, with the lifecycle rule — and refusing a bucket name outside the prefix
* **a real `teardown.sh --yes` run**: it drained two pages of object versions and delete
  markers from the versioned state bucket, deleted it, then re-read AWS and reported no
  residue. Exit 0.
* `deploy.ps1` and `deploy.sh` preflight refusing correctly, with an actionable message,
  when the Lambda DSN is absent
* `--dry-run` naming missing artefacts **and the worker that owes each one**
* `teardown.sh` refusing a real unrelated bucket in this account
  (`aws-cloudtrail-logs-022950218246-…`), refusing an untagged bucket carrying our prefix,
  and accepting that same bucket once tagged `project=mainline`
* the `DROP DATABASE … CASCADE` → `DROP USER` ordering, and the `2BP01` the reverse
  produces
* the Windows `mimetypes` results that justify stage 7's explicit content types
* the WSL-vs-Git-Bash distinction that shaped `deploy.ps1`
* **one real bug, found by running rather than reading.** Under Git Bash, `mktemp` returns
  `/tmp/x.json` and the native `aws.exe` cannot open it, so the first real teardown died
  with `Unable to load paramfile file:///tmp/mainline-del.XyMVEA.json`. Both scripts now
  route every `file://` paramfile through `cygpath -m`. This mattered twice: teardown's
  delete payload, and — more importantly — stage 2's SSM payload, which is a paramfile
  *specifically* so the DSN never enters an argument vector.

**Not proven, and stated here rather than implied away:**

* **A live demo URL. There is none, and there cannot be one until AWS lifts the CloudFront
  verification hold on this account.** Everything upstream of the distribution is verified;
  the distribution itself has never been created.
* A full phase-2 deploy: `capture_demo_bundle.py` (W9) and `demo_acceptance.py` (W10) had
  not landed when this page was written. `--dry-run` reports both as missing, names the
  worker that owes each, and exits non-zero — which is why that flag exists.
* `terraform plan` reporting no changes immediately after a successful apply. The apply
  never succeeded, so this remains unverified rather than assumed.
* The OpenTofu commands in `infra/envs/demo/README.md`. OpenTofu is not installed here;
  "the HCL is in the common subset" is a claim about the code, not a measurement.
