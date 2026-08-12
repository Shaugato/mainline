<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# W3 — the DSN, the state backend, blast radius and rollback

**Worker:** W3 (deploy-verification pass, lead plan `docs/leads/deploy-verify-plan2.md`).
**Date:** 2026-08-12. **Account:** `0229REDACTED8246`, region `ap-southeast-1`, profile `mainline-dev`.
**Evidence:** `evidence/deploy/verify/state-and-teardown-audit.json`.

**What I was allowed to do, and did.** Read-only AWS calls, no `terraform` of any kind
(W5 owns that directory), and the local Docker CockroachDB node as the only database I
mutated — scratch database `w_w3`, created and dropped. **No credential appears in this
document, in the evidence JSON, or in anything I printed.** Every twelve-digit account id
is masked as `0229REDACTED8246`.

**Verdict, up front: GO for my slice.** The one fix worth making is W3-F1 and it does not
block the apply. §7 states it exactly.

---

## 1. The DSN, hop by hop

The claim under audit is that the CockroachDB Cloud password reaches the Lambda **only**
as a KMS-encrypted SecureString read at runtime, and touches no plan, no state, no log and
no committed file. Every hop below is a file and a line I read.

| # | Where | What happens to the value |
|---|---|---|
| 1 | `scripts/deploy/deploy.sh:367-369` | `COCKROACH_DSN` read from the repo-root `.env` when not exported. `.env` is untracked and gitignored at `.gitignore:6`. |
| 2 | `deploy.sh:718-720` | payload built in a `mktemp` file, `chmod 600`, `trap 'rm -f' EXIT INT TERM` |
| 3 | `deploy.sh:727-759` | inline Python swaps the userinfo to `mainline_api` and forces `/<demo_database>`; **refuses at `:747`** if the result does not name `mainline_api` |
| 4 | `deploy.sh:761` | `aws ssm put-parameter --cli-input-json file://<paramfile> --query Version`. The value never enters an argument vector, `ps`, or shell history. **No `KeyId` is supplied** — see §1.3. |
| 5 | `deploy.sh:764` | paramfile removed, trap cleared |
| 6 | `deploy.sh:774-776` | read back **without** `--with-decryption`; asserts `Parameter.Type == SecureString` |
| 7 | `deploy.sh:157`, `:484-489`, `:913` | the **name** `/mainline/demo/cockroach_dsn` is a constant, asserted at preflight to equal `var.dsn_parameter_name`'s default, then passed as `-var dsn_parameter_name=` |
| 8 | `infra/envs/demo/variables.tf:210-231` | `validation { condition = can(regex("^/mainline/", …)) }` |
| 9 | `infra/envs/demo/main.tf:291` | the name enters `module.api` |
| 10 | `infra/modules/demo-api/main.tf:94-95` | leading slash normalised; `local.dsn_parameter_arn` built |
| 11 | `infra/modules/demo-api/main.tf:112-114` | `MAINLINE_DSN_PARAM = local.dsn_parameter_path` — the name, never the value |
| 12 | `infra/modules/demo-api/main.tf:188-234` | `ssm:GetParameter` on exactly one ARN; `kms:Decrypt` on `*` narrowed by `kms:ViaService` **and** `kms:EncryptionContext:PARAMETER_ARN` |
| 13 | `db.py:270-273` | **`MAINLINE_DSN` wins if set and non-empty.** It is not set — §1.2. |
| 14 | `db.py:275-292` | otherwise `MAINLINE_DSN_PARAM` + `AWS_REGION` → `_ssm_get_parameter` |
| 15 | `db.py:161-252` | hand-rolled SigV4 `POST https://ssm.<region>.amazonaws.com/`, target `AmazonSSM.GetParameter`, body `{"Name":…,"WithDecryption":true}`. Credentials come from the runtime-injected `AWS_ACCESS_KEY_ID` / `_SECRET_ACCESS_KEY` / `_SESSION_TOKEN` only — no profile, no IMDS walk, no credential file. |
| 16 | `db.py:118`, `:265-268`, `:290-292` | `_dsn_cache` is a module global and `resolve_dsn` short-circuits on it: **one `GetParameter` and one KMS decrypt per execution environment**, not per invocation |
| 17 | `db.py:332` → `db.py:303-310` | `psycopg.connect(dsn, autocommit=True, connect_timeout=…, application_name=…, row_factory=dict_row)` |

### 1.1 The planned environment is exactly the six keys, and no `MAINLINE_DSN`

Read out of the committed plan, not out of the HCL:

```
evidence/deploy/terraform-plan-furl.json
  module.api[0].aws_lambda_function.this .change.after.environment[0].variables
    LOG_LEVEL                    = INFO
    MAINLINE_DEMO_DATABASE       = mainline_demo
    MAINLINE_DEMO_PERMIT_ID      = 077a6fdd-2167-559c-b2ff-8e3c8352504d
    MAINLINE_DSN_PARAM           = /mainline/demo/cockroach_dsn
    MAINLINE_SCENARIO_PERMIT_ID  = 077a6fdd-2167-559c-b2ff-8e3c8352504d
    MAINLINE_WEB_ROOT            = /var/task/web
  key count = 6 · MAINLINE_DSN present = false
```

`MAINLINE_DEMO_ALLOW_MUTATION` and `MAINLINE_DEBUG` are also absent, so the demo-subject
guard is armed and the debug traceback path at `app.py:390` is dead.

### 1.2 The absence is structural, not incidental

`extra_environment` is the only merge point into that map (`main.tf:112`), and
`infra/modules/demo-api/variables.tf:478-489` refuses seven keys outright:

```hcl
condition = length(setintersection(keys(var.extra_environment), [
  "MAINLINE_DSN", "MAINLINE_DSN_PARAM", "MAINLINE_DEMO_DATABASE",
  "MAINLINE_SCENARIO_PERMIT_ID", "MAINLINE_DEMO_PERMIT_ID",
  "MAINLINE_WEB_ROOT", "LOG_LEVEL",
])) == 0
```

A second validation (`:491-500`) refuses Lambda's reserved names. And
`grep -rn extra_environment infra/envs/` returns **nothing** — the root never sets it at
all. So `MAINLINE_DSN` cannot be smuggled in through the only door.

**Can anything else set it?** Measured, not argued:

* **The artefact.** `out/lambda/mainline-demo-api-arm64.zip`, 206 entries. Top-level
  members are `mainline_demo_api`, `psycopg`, `psycopg_binary`, `web` and dist-info.
  `scripts/deploy/local_furl.py` — the one file in the repo that assigns
  `os.environ["MAINLINE_DSN"]`, at `:671` — **is not in the package.** No `.py` member
  assigns that variable or calls `load_dotenv`. No `.env`, `credential`, `.pem` or `.key`
  member. A regex sweep of **every** member for `postgres(ql)://user:pass@` and for
  `AKIA|ASIA[0-9A-Z]{16}` returned **zero hits**.
  The package's sha256 base64 is `yF1/AKVXbkEt+wEkrZPEAQR1cBEXnQApNh2ajbW4pLA=`, which is
  **byte-identical to the plan's `source_code_hash`** — the plan describes this zip.
* **CI.** `MAINLINE_DSN` appears once under `.github/`, at
  `.github/workflows/judge-pack.yml:255`, set to the **empty string**.
  `resolve_dsn` does `os.environ.get(DSN_ENV, "").strip()`, so empty falls through to
  `MAINLINE_DSN_PARAM`. Harmless, and it never touches the deployed function.

### 1.3 KMS: which key, and what the missing key meant

`deploy.sh:750-758` (and `deploy.ps1:755-761`) build the put-parameter payload as
`Name / Type / Overwrite / Tier / Description / Value` — **no `KeyId`**. So SSM encrypts
under the account's default `alias/aws/ssm`, never a CMK. The module agrees:
`ssm_kms_key_arn` defaults to `""`, which makes `kms_decrypt_resources = ["*"]`
(`main.tf:97-101`) and pushes the narrowing into two conditions instead.

The lead recorded (§0.4) that `alias/aws/ssm` had **no `TargetKeyId`** — no backing key.
**That is no longer true, and the change happened during this pass.** Measured:

```
read at            2026-08-12T12:47:39Z
alias/aws/ssm      TargetKeyId 81edadd5-dfa0-428b-a3c6-7694a7917577
KeyManager         AWS          KeyState  Enabled
CreationDate       2026-08-12T12:46:08Z      <- 91 seconds before the read
SSM parameters in ap-southeast-1   0
```

Zero parameters exist, so **no SecureString write created it**. It was materialised by a
read — `aws kms list-aliases` / `describe-key`, which are the only KMS calls made here. I
report it because it is what the account looks like now, not because I intended it; I ran
no write call, and creating an AWS-managed key is free and not deletable either way.

Two consequences:

* **First cold start.** The concern was that the very first `GetParameter WithDecryption`
  would race key creation. The key now exists and is `Enabled`, so that concern is gone.
* **The `kms:EncryptionContext:PARAMETER_ARN` condition is still unexercised.** No
  SecureString has ever been decrypted on this account. SSM documents `PARAMETER_ARN` as
  the encryption context on every SecureString, and the plan's condition value is the exact
  ARN the module computes — but "documented" is not "measured". If it does not match, the
  cold start fails `AccessDeniedException` on `kms:Decrypt` and `/v1/health` reports
  `dsn_unavailable`. The fallback is already named and is one variable:
  `restrict_kms_to_parameter = false` (`variables.tf:180-198`), which keeps `kms:ViaService`.
  **This is a runtime risk, not an apply risk, and it is reversible in one plan.**

### 1.4 Nothing logs the value — proven, not asserted

`dsn_source()` returns a *name* (`db.py:295-297`). `health.py:133` puts `db.redact(dsn)`
in the unreachable-database body. I exercised both:

```
redact("postgresql://mainline_api:<pw>@host…cockroachlabs.cloud:26257/mainline_demo?sslmode=verify-full")
  -> postgresql://mainline_api:***@host…cockroachlabs.cloud:26257/mainline_demo?sslmode=verify-full
redact("postgresql://u:p@ss$w0rd@h:26257/d")   -> postgresql://u:***@h:26257/d   (@ in password handled)
redact("not-a-dsn-at-all")                     -> ***
```

The bigger risk is the four `f"[{exc.sqlstate}] {str(exc).splitlines()[0][:400]}"` bodies
(`app.py:353/380/457`, `health.py:132`) — does libpq echo the DSN? I connected to the local
node with a sentinel password and searched the exception **and the full traceback**:

```
sqlstate                  : None
sentinel in str(exc)      : False
sentinel in full traceback: False
message                   : connection failed: connection to server at "127.0.0.1", port 26257
                            failed: ERROR:  password authentication failed for user scratchuser
```

So those bodies cannot carry the password, and `redact()` is belt to that pair of braces.
`DsnUnavailable` messages are built from the parameter *name*, the region, and env-var
names — never from a value.

---

## 2. Public-repo exposure: a measurement, not an assurance

The repo is public. I scanned the working tree (**7,402 tracked paths**) and **every one of
the 53 commits reachable from all refs** (`git rev-list --all`; 47 on `master`, the other
six on Dependabot branches). Method: `git grep -I -n -E` per commit, every match classified
**in-process** and never echoed. Locations only below.

### A CockroachDB DSN carrying a password — **ABSENT**

| | matches | live credentials |
|---|---|---|
| working tree | 16 | **0** |
| all 53 commits | 382 | **0** |

Of the 16 at HEAD: seven are structural placeholders (`<…>`, `***`, `PASTE_THE_PASSWORD_HERE`);
eight are test fixtures carrying a well-known joke password; one is
`docs/deploy/cloud-database.md:715`, where the host field is the literal `HOST` and the
password field is the literal `PASTE_THE_PASSWORD_HERE`.

Two fixtures use a host that *looks* like a Cloud endpoint —
`scripts/aws/verify_evidence.py:1743` and
`verticals/mainline/apps/demo-api/tests/test_envelope.py:436` — so I checked them
structurally: both carry the joke placeholder password, and the sha256 prefix of their
hostname matches **neither** real cluster host recorded in `evidence/ccloud/cluster-list.txt`.
Both sit inside functions whose job is to plant a fake leak so a detector can catch it
(`leak_dsn`, and a redaction assertion).

Across history the 382 split as 345 placeholder/local-host over 9 paths, plus 37 in
`infra/modules/demo-api/README.md:129` over 37 commits — where the "password" is a literal
ellipsis in a copy-paste example.

### The `mainline_judge` password — **ABSENT**

The identifier appears on 133 lines at HEAD across 11 paths, and in 334
(path, line, commit) triples in history that also mention a password-shaped word. **Zero**
of them carry a password literal. A separate sweep for `PASSWORD '<literal>'` across all 53
commits found 111 matches over 2 paths, every one a placeholder. One candidate survived
automated triage — `docs/submission/SUBMISSION.json:19` — and turned out to be the key
`credentials_location` holding a 373-character prose sentence with no digits in it.

**The password the STATE says was echoed to a transcript twice is not in the working tree
and is not in any commit.** The transcript exposure is real and outside the repo; the
rotation the orchestrator owns is still the right response, and nothing in the repository
needs a history rewrite.

### AWS access keys — **ABSENT**

836 matches of `AKIA|ASIA[0-9A-Z]{16}`, **0 of real shape**: 827 are AWS's own documented
example key (redaction fixtures and the public-readiness audit's own corpus), and 9 are a
single keyboard-row string at `scripts/aws/verify_evidence.py:1749` — a fixture the
evidence verifier plants to prove its own leak detector fires. (Not reproduced here, so this
file adds no new `AKIA`-shaped token to a public repo.)

### `.env`

Untracked, gitignored at `.gitignore:6`, and `git log --all -- .env` is **empty** — it was
never committed. `.env.example` is tracked; lines 34-42 are `root@localhost` DSNs with no
password at all, and lines 123-124 are commented-out empty `COCKROACH_DSN=` / `CC_API_KEY=`.

### One thing that *is* public, deliberately

**12 tracked files carry the real Cloud cluster hostname**: `docs/deploy/JUDGE-PACK.md`,
`docs/deploy/cloud-database.md`, `docs/leads/ship-final.md`,
`evidence/ccloud/cluster-list.txt`, five files under `evidence/deploy/`,
`infra/modules/demo-api/README.md`, `verticals/mainline/demo/judge/MCP-CONFIG.md`.

This is a **decided disclosure**, not a leak: `docs/submission/DISCLOSURE-DECISIONS.yaml`
lines 391-426 record the decision and its reason — a judge has to be able to connect. No
password accompanies it anywhere. It does mean the SQL endpoint is a public target for
online password guessing, which is exactly what makes the `mainline_judge` rotation
load-bearing rather than hygienic.

---

## 3. The state backend

`infra/envs/demo/backend.tf:56-63` is a partial config: `key = demo/terraform.tfstate`,
`region = ap-southeast-1`, `encrypt = true`, `use_lockfile = true`, no `dynamodb_table`,
bucket supplied at `init`.

**`use_lockfile`'s requirements are met by `versions.tf`.** `required_version = ">= 1.10.0"`
(`versions.tf:34`) is the floor where native S3 locking landed; Terraform on this machine is
**1.14.8**, and the committed plan records `terraform_version 1.14.8`. The provider is
locked to `hashicorp/aws 6.58.0`, inside `>= 5.60.0, < 7.0.0`. The lock object needs
`PutObject` with `If-None-Match`, `GetObject` and `DeleteObject` on
`demo/terraform.tfstate.tflock`; the deploying identity holds `AdministratorAccess`, so
that is satisfied.

**The bucket does not exist today.**

```
aws s3api head-bucket --bucket mainline-demo-tfstate-0229REDACTED8246
  An error occurred (404) when calling the HeadBucket operation: Not Found
```

Seven buckets exist in the account and **none** carries the `mainline-demo-` prefix. So
`terraform init` with the S3 backend fails until `bootstrap_state.sh` runs — which is
`deploy.sh` stage 1.

**What `bootstrap_state.sh` actually sets** (quoted from the script, not from the README):

| control | set | line | value |
|---|---|---|---|
| versioning | yes | `:224-227` | `Status=Enabled` |
| public access block | yes | `:230-234` | `BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true` |
| encryption | yes | `:244-248` | SSE-S3 `AES256`, `BucketKeyEnabled=true` — deliberately not a CMK |
| tags | yes, **fatal if it fails** | `:251-255` | `project=mainline`, `managed_by=bootstrap_state.sh`, `mainline:role=terraform-state` |
| lifecycle | yes | `:262-265` | noncurrent versions expire after 30 days; incomplete multipart aborted after 7 |
| **bucket policy** | **NO** | — | `put-bucket-policy` appears nowhere in `scripts/deploy/**` or `infra/envs/**` |

Plus three guards worth naming: a wrong-region pre-existing bucket is a hard stop
(`:210-221`); a `head-bucket` **403** is treated as "this name belongs to another AWS
customer" and never retried (`:172-186`); and any name outside `mainline-demo-` is refused
before the first AWS call (`:100-110`, `:153-160`). It is idempotent by design — it
re-asserts every control on every run.

**Who can read the state object.** With no bucket policy, confidentiality is entirely IAM:
the account root, IAM user `mainline-dev` (measured: `AdministratorAccess`, plus
`AmazonS3FullAccess` and `AmazonBedrockFullAccess`), and anyone holding that user's
long-lived keys. **Nobody anonymously** — all four public-access blocks are on and no policy
grants anything. Cross-account access is impossible without a policy. The gap the missing
policy leaves is a `Deny` on `aws:SecureTransport = false`; see W3-F3.

**What the state will contain.** From the plan's `after` values: the role ARN, the inline
`dsn_access` policy JSON (which embeds the account id and the parameter ARN), the function
ARN/name/runtime/architecture/memory/timeout/`source_code_hash`, the six non-secret
environment variables including `MAINLINE_DSN_PARAM` (**a name**), the Function URL and its
domain, the log group ARN, four alarm ARNs, the dashboard body, and the root outputs — which
include `aws_account_id`. **No secret.** Terraform is never handed the DSN value, so
`terraform show` cannot print it and the object cannot leak it.

---

## 4. Blast radius, from the plan JSON

```
evidence/deploy/terraform-plan-furl.json   format_version 1.2, terraform 1.14.8
resource_changes                           11
action tally                               {"create": 11}      update 0 · delete 0 · replace 0
every change's .before                     null   (0 exceptions)
prior_state managed resources              0      (6 data sources only:
                                                   aws_caller_identity x2, aws_iam_policy_document x2,
                                                   aws_partition, aws_region)
import / moved / removed blocks            0
resource_drift                             null
```

The eleven, by type:

```
aws_cloudwatch_log_group        module.api[0].aws_cloudwatch_log_group.this
aws_iam_role                    module.api[0].aws_iam_role.this
aws_iam_role_policy             module.api[0].aws_iam_role_policy.dsn_access
aws_iam_role_policy_attachment  module.api[0].aws_iam_role_policy_attachment.basic_execution
aws_lambda_function             module.api[0].aws_lambda_function.this
aws_lambda_function_url         module.api[0].aws_lambda_function_url.this
aws_cloudwatch_metric_alarm     …errors · …throttles · …duration_p99 · …concurrency
aws_cloudwatch_dashboard        module.api[0].aws_cloudwatch_dashboard.this[0]
```

**Zero CloudFront resources. Zero S3 resources. Zero database resources of any kind.**
`enable_cloudfront = "false"` and `site_bucket_name = ""` in the plan's variables, and the
site module contributes nothing.

**Nothing pre-existing is addressed.** Every `before` is null and prior state holds no
managed resource, so there is no adoption, no replacement and no in-place edit available to
this plan even in principle. Against the account:

* **CloudFront:** one distribution, `E2FCXK8NILPNWF`, `Deployed`, comment
  *checkout-platform static site distribution*. Not addressed by the plan.
* **S3:** seven buckets — `aws-cloudtrail-logs-0229REDACTED8246-10882a56`, `cci-change-feed`,
  `checkout-platform-debd5edd-site`, `checkout-platform-site`,
  `elasticbeanstalk-ap-southeast-2-0229REDACTED8246`, `intellicanvas-voice-model`,
  `shortstack-pipeline-artifactbucket-amxvhsepi4ak`. **None** carries the `mainline-demo-`
  prefix; **none** is addressed by the plan.

And the target region is empty, so there is no name to collide with:

```
lambda functions ap-southeast-1     0
IAM roles named mainline*           0
log groups ap-southeast-1           0
CloudWatch alarms ap-southeast-1    0
CloudWatch dashboards               0
SSM parameters ap-southeast-1       0
```

One honest caveat: **the plan bounds the blast radius; IAM does not.** The deploying
identity holds `AdministratorAccess`, so a mistyped `-var` or a different root would not be
refused by permissions. The safety here is the reviewed plan and the `--expect-account`
guard, not least privilege at the operator level. (The *Lambda's* least privilege is W1's
finding, and `dsn_access` is genuinely one action on one ARN.)

---

## 5. The wrapper: what `deploy.sh` does to the Cloud database around the apply

Stage order is `0 preflight · 1 bootstrap_state · 2 ssm put-parameter · 3 cloud_chain +
seed_demo · 4 build zip · 5 optional site · 6 terraform · 7 https proof · 8 acceptance ·
9 hand-off`. So **everything the database sees happens at stage 3, before the apply.**

* **`cloud_chain.py`, default path — non-destructive.** Forward-only, and it *refuses*
  (exit 3, changing nothing) when the migration-tree fingerprint drifts, when the live
  fingerprint drifts, or when the database exists without a marker row (`:1080-1131`).
  There are no down-migrations anywhere in the chain tooling, so an applied migration is
  not reversible by this repository — but it is additive, and the refusal is the guard.
* **`cloud_chain.py --recreate` — destructive and irreversible.** `DROP DATABASE IF EXISTS
  "<db>" CASCADE` at `:1152`, then `CREATE DATABASE` at `:1153`. Reachable only via
  `deploy.sh --recreate-db`, an explicit opt-in flag.
* **The verification database is not the demo database.** `cloud_chain.py:1297` names a
  throwaway via `verification_database_name()`, which for `mainline_demo` yields
  `mainline__vfy` — same length, different name — built to compare schemas and dropped on
  both the success and the refusal path (`:1545`).
* **`seed_demo.py` — non-destructive.** `ON CONFLICT DO NOTHING` throughout, rollback on
  failure (`:211/:322/:336`), commits at `:292/:361`. A second run inserts nothing.
* **After the apply, nothing writes.** Stage 7 GETs `/` and `/v1/health`; stage 8 runs
  `demo_acceptance.py`, which POSTs `/v1/demo/gate-run` twice — the one handler that ends
  in ROLLBACK.

**The one thing worth saying out loud (W3-F4):** the approval gate at `deploy.sh:940-965`
gates *stage 6 only*. By the time it prints "STOPPED AT THE APPROVAL GATE", stages 1-5 have
already created the state bucket, written the DSN SecureString and migrated + seeded the
Cloud database. The script's own gate text admits it — *"Stages 1 to 5 have already run and
are idempotent"* (`:959`). Only `--dry-run` and `--preflight-only` write nothing at all.
That is a defensible design, but "plan-only deploy" is a phrase that invites the opposite
reading.

---

## 6. Rollback: exactly what survives

### `terraform destroy` alone removes

the Lambda function · the Function URL · the execution role, its inline policy and the
managed-policy attachment · `/aws/lambda/mainline-demo-api` and its events · all four
alarms · the dashboard.

### `terraform destroy` alone LEAVES BEHIND

| survivor | why | cost |
|---|---|---|
| **SSM SecureString `/mainline/demo/cockroach_dsn`** | written by `deploy.sh` with the CLI; **never a Terraform resource** | USD 0.00 — but it is a live database password sitting in an account nobody is watching |
| **`s3://mainline-demo-tfstate-<account-id>`**, `demo/terraform.tfstate`, every noncurrent version, and any stuck `.tflock` | the backend cannot delete itself | ~USD 0.01/month |
| **CockroachDB Cloud `mainline_demo` + logins `mainline_api`, `mainline_judge`** | not Terraform resources at all | whatever the Basic cluster costs |
| **the AWS-managed KMS key behind `alias/aws/ssm`** | AWS-managed; a customer cannot schedule it for deletion | USD 0.00 |

### `terraform destroy` + `teardown.sh` leaves behind

* **the AWS-managed KMS key** — permanent, free, and now unavoidable in this region;
* **the Cloud database, but only if step 4 was skipped.** `teardown.sh:516-519` skips it
  when `COCKROACH_DSN` is unset or the venv is missing, and **prints the three statements to
  run by hand** rather than pretending it succeeded;
* **nothing else this project created**, re-read and verified at `:605-626`.

### Does the prefix + `project=mainline` filter really protect the other four projects?

Yes, and it is stronger than a single check:

* **Buckets.** `assert_ours_bucket` (`:216-245`) requires **both** the `mainline-demo-` name
  prefix **and** a live `project=mainline` tag read back from AWS at the moment of deletion.
  `--ignore-tags` relaxes the tag and **never** the prefix. Measured: **none of the seven
  pre-existing buckets carries the prefix**, so none is reachable by
  `delete_bucket_completely` even with `--ignore-tags`.
* **SSM.** Step 3 is gated on the `/mainline/` name prefix (`:472-475`), and `DSN_PARAM` is a
  hard-coded constant with no CLI flag to change it. The account holds zero parameters under
  `/mainline/` — or anywhere else.
* **CloudFront.** Teardown **never deletes a distribution.** It lists them and prints
  `WOULD NOT TOUCH` for any origin outside the prefix. `E2FCXK8NILPNWF`'s origin is
  `checkout-platform-debd5edd-site`, which is outside it.
* **Lambda.** Teardown never calls `lambda delete-function`; removal is `terraform destroy`'s
  job, and a stray `mainline-demo*` function is reported as residue.
* **The account.** No account id is written in the file; `--expect-account` or
  `MAINLINE_AWS_ACCOUNT` is mandatory for a real run and a mismatch exits 3 (`:187-203`).
* **The database.** The inline Python refuses any name not starting with `mainline_`
  (`:539-540`), so `MAINLINE_DEMO_DATABASE=defaultdb` cannot arm it.
* **Unreadable is not empty.** `aws_query` (`:147-155`) makes a *failed* list call fatal
  instead of reporting it as "nothing found" — the one wrong answer a teardown must never
  give.

### The drop-order claim, reproduced

`teardown.sh:492-507` claims `DROP USER` before `DROP DATABASE` fails, and that CASCADE
first fixes it. On the local node (CockroachDB CCL **v26.2.5**), scratch database `w_w3`,
with the same grant shape `cloud_roles.py` produces:

```
== REVERSE order: DROP USER while grants still exist ==
  [2BP01] DROP USER IF EXISTS w3_api
          cannot drop role/user w3_api: grants still exist on w_w3, w_w3.public.t

== teardown.sh order: DROP DATABASE CASCADE, then the users ==
  OK  DROP DATABASE IF EXISTS w_w3 CASCADE
  OK  DROP USER IF EXISTS w3_api
  OK  DROP USER IF EXISTS w3_judge
  residue: users=[]  databases=[]
```

**Claim true, same SQLSTATE, same message shape.**

---

## 7. Findings

| id | sev | finding | fix | blocks apply |
|---|---|---|---|---|
| **W3-F1** | medium | **teardown's verify has four blind spots.** `:602-626` re-reads buckets, the SSM parameter and Lambda functions — never the IAM role, the log group, the alarms or the dashboard. `:332` skips step 1 entirely whenever the state bucket is already gone, so those six resources can be orphaned while teardown exits 0 saying *"nothing this project created remains"*. Orphan cost is USD 0.00 (free role, empty log group, 4 alarms inside the free 10, 1 dashboard inside the free 3) — the defect is the false statement, not the bill. | add three read-only checks to the verify block: `iam list-roles` filtered on `${NAME_PREFIX}`, `logs describe-log-groups --log-group-name-prefix /aws/lambda/${NAME_PREFIX}`, `cloudwatch describe-alarms --alarm-name-prefix ${NAME_PREFIX}` | no |
| **W3-F2** | low | **the bucket tag check is a substring match.** `:239` runs `grep -q '"Value": *"mainline"'` over the JSON of *all* tags, so any tag whose value is `mainline` passes — not only `project=mainline`. Unreachable except for a bucket already carrying the prefix, and no such bucket exists. | assert the *pair* on the parsed `TagSet` | no |
| **W3-F3** | low | **the state bucket has no bucket policy.** No `Deny` on `aws:SecureTransport = false`, no principal allowlist. The object holds no secret and the public-access block already excludes anonymous readers, so this is defence in depth, not a hole. | one `put-bucket-policy` with a single `SecureTransport` deny, after the public-access-block call in `bootstrap_state.sh` | no |
| **W3-F4** | info | **the approval gate does not gate the secret write or the migration** (§5). | one sentence in `docs/deploy/RUNBOOK.md` | no |
| **W3-F5** | info | **`infra/modules/demo-api/README.md:129` shows `/mainline/demo/dsn`**; everything that executes uses `/mainline/demo/cockroach_dsn`. `deploy.sh:484-489` asserts the real agreement at preflight, so this can only misdirect a hand-fix. | one-word README edit | no |
| **W3-F6** | info | **the lead's "`alias/aws/ssm` has no backing key" is no longer true** (§1.3) — measured `Enabled`, AWS-managed, created during this pass with zero parameters in the region. Resolves the first-cold-start concern; leaves the `EncryptionContext` condition unexercised. | none | no |

---

## 8. Verdict

> **GO — for W3's slice.** The DSN reaches the Lambda only as a KMS-encrypted SecureString
> read at runtime and cached once per execution environment; it appears in no plan, no state,
> no log, no committed file, and in none of the 53 commits — as does no `mainline_judge`
> password and no real AWS key. The plan is 11 creates that address nothing pre-existing, in
> a region that holds nothing, with zero CloudFront, S3 or database resources. Destroy plus
> teardown is bounded by a prefix-**and**-live-tag filter that provably cannot reach the seven
> unrelated buckets or the one unrelated distribution, and the residue it leaves is a
> SecureString, a state bucket and a Cloud database — each of which teardown deletes and names
> when it cannot. **The only fix worth making first is W3-F1, and it does not block the apply.**

**Not mine to decide:** `reserved_concurrent_executions = 20` against an account ceiling of
10 (W4/W5), and the unauthenticated mutating routes (W2). Either can still make the
aggregate a NO-GO.
