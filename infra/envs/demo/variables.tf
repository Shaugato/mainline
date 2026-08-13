# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
#
# Every variable here has a default that works on the account the deploy runs in, so that
# `terraform apply` with no `-var` at all is a valid thing to do. The defaults are not
# placeholders: they are the values `scripts/deploy/deploy.sh` uses.
#
# The one exception is `lambda_package_path`, which has a default but whose default is a
# *build output* — the file does not exist in a clean checkout, and `terraform plan` will
# say so plainly rather than pretend. That is why `var.enable_api` exists.
#
# `lambda_reserved_concurrency` exists to KEEP that first sentence true. The module it
# feeds defaults to a value AWS refuses on this account, so a root that passed nothing
# would produce a plan that is valid, committed, reviewed — and dies six API calls into
# the apply. A root variable is how the environment's measured facts override a module
# default that was written for a different account.
#
# ── NO ACCOUNT ID IS SPELLED IN THIS FILE, AND THAT IS DECISION D2 ─────────────────────
#
# An earlier revision wrote the twelve-digit account number into three descriptions and
# into the derived bucket-name example. An account id is not a credential, but an
# *executable default* carrying one is a default that is wrong on every machine except the
# one it was written on, and `docs/leads/ship-final.md` §1.6 (decision D2) removes it from
# every executable position in the repository. Where the id is needed it is DERIVED, at
# run time, from `data.aws_caller_identity.current.account_id` — see `main.tf`'s
# `local.site_bucket_name` — or, outside Terraform, from:
#
#     aws sts get-caller-identity --query Account --output text
#
# Where it appears as *recorded evidence* — a quoted apply refusal, a committed plan — it
# stays, because scrubbing a measurement is the one thing `docs/HONESTY.md` will not do.
# `<account-id>` below is a placeholder, never a value to copy.

variable "aws_region" {
  description = <<-EOT
    Where every AWS resource in this root is created.

    `ap-southeast-1` (Singapore) because that is where the CockroachDB Cloud Basic
    cluster `mainline-dev` lives, and the Lambda talks to it over pgwire on every
    request. In-region is single-digit milliseconds; from `ap-southeast-2` it is ~90 ms
    each way and the gate surface makes six round trips. CloudFront is global either way,
    so the region choice costs the judge's browser nothing.

    Bedrock is deliberately NOT here — the `au.*` inference profiles live in
    `ap-southeast-2` and the demo makes at most one Bedrock call per recall query. That
    cross-region hop is named in `docs/HONESTY.md` rather than hidden.
  EOT
  type        = string
  default     = "ap-southeast-1"

  validation {
    condition     = can(regex("^[a-z]{2}-[a-z]+-[0-9]$", var.aws_region))
    error_message = "aws_region must look like an AWS region, e.g. ap-southeast-1."
  }
}

variable "name_prefix" {
  description = <<-EOT
    The prefix carried by the NAME of every resource this root creates.

    This is a safety control, not a cosmetic one. The AWS account this deploys into holds
    four unrelated live projects. `scripts/deploy/teardown.sh` refuses to delete anything
    whose name does not start with this prefix AND which does not carry the tag
    `project=mainline`. Changing this value without changing teardown's default makes
    teardown refuse to clean up — which is the failure direction we want.
  EOT
  type        = string
  default     = "mainline-demo"

  validation {
    condition     = can(regex("^mainline-demo", var.name_prefix))
    error_message = "name_prefix must begin with 'mainline-demo' — scripts/deploy/teardown.sh keys its safety refusal on that prefix."
  }
}

# ── THE ARCHITECTURAL SWITCH ──────────────────────────────────────────────────────────

variable "enable_cloudfront" {
  description = <<-EOT
    Whether to create the CloudFront distribution, the site bucket and the Origin Access
    Controls — i.e. whether `module.site` exists at all.

    THE DEFAULT IS `false` AND IT IS A MEASUREMENT, NOT A PREFERENCE. A real
    `terraform apply` of this root on 2026-08-10 created seven resources and was then
    refused the eighth by AWS:

        Error: creating CloudFront Distribution: operation error CloudFront:
        CreateDistributionWithTags, https response error StatusCode: 403,
        RequestID: 3e63e30d-8c5b-441b-a01b-b70085eba504, AccessDenied:
        Your account must be verified before you can add new CloudFront resources.
        To verify your account, please contact AWS Support and include this error message.

    The identical refusal, with the same message, comes from a bare
    `aws cloudfront create-distribution` carrying a minimal three-field config and no
    Terraform anywhere, issued by an identity holding `AdministratorAccess`. It is an AWS
    **account-level verification hold on new CloudFront resources**, liftable only by AWS
    Support. It is not an IAM problem, not a module defect, and not something a retry
    fixes. The transcript is `docs/deploy/RUNBOOK.md` line 26; the decision that follows
    from it is D1, `docs/leads/ship-final.md` §1.4.

    WHAT EACH SETTING PRODUCES

      false (default)   `module.site` is `count = 0`: no bucket, no OACs, no distribution.
                        `module.api`'s Lambda Function URL is created with
                        `authorization_type = "NONE"` and IS the demo hostname —
                        `https://<id>.lambda-url.<region>.on.aws`, HTTPS on an AWS-issued
                        certificate, no ACM, no hosted zone, no account verification. One
                        origin serves the console SPA, `/bundle/*` and `/v1/*`, so there
                        is no CORS and one URL goes in the submission form.

      true              `module.site` is created and owns the hostname; the Function URL
                        reverts to `authorization_type = "AWS_IAM"` and is reachable only
                        through the distribution's Origin Access Control. This is the
                        pre-D1 shape. It will not apply on an account under the hold
                        above; it plans cleanly, which is what makes it a one-variable
                        upgrade the day Support lifts it.

    `output.demo_url` follows this variable, so flipping it is the whole architectural
    switch and no other input has to change with it.
  EOT
  type        = bool
  default     = false
}

variable "site_bucket_name" {
  description = <<-EOT
    The S3 bucket holding the console build and the EvidenceBundle.

    ONLY READ WHEN `enable_cloudfront = true`. With the default `false` there is no site
    module and therefore no bucket; the console is served out of the Lambda package by the
    same origin as the API.

    Empty (the default) means "derive it": `<name_prefix>-site-<account-id>`, where the
    account id comes from `data.aws_caller_identity.current.account_id` at plan time — it
    is not written down anywhere in this configuration (decision D2). S3 bucket names are
    globally unique across all AWS customers, so a hard-coded constant in a public
    repository is a name somebody else has already taken; deriving from the account id
    makes it unique without asking the operator to invent anything, and keeps the
    `mainline-demo-` prefix teardown keys on.

    The bucket is PRIVATE. It has no website configuration and no public policy — reads
    arrive only through CloudFront Origin Access Control.
  EOT
  type        = string
  default     = ""
}

variable "enable_api" {
  description = <<-EOT
    Whether to create the Lambda, its Function URL, its IAM role, its log group and its
    alarms — and, when `enable_cloudfront` is also true, the `/v1/*` behaviour that routes
    at it.

    UNDER D1 THIS IS THE VARIABLE THAT OWNS THE HOSTNAME, and its meaning inverted. It
    used to be the Phase-1 cut line, on the reading that the distribution produced the URL
    and the Lambda was the optional half. AWS refuses to create a distribution on this
    account (see `enable_cloudfront`), so the halves swapped: with the default
    `enable_cloudfront = false`, `enable_api = false` produces a root that creates
    **nothing at all** and has no demo URL to emit. `output.demo_url` carries a
    precondition that says exactly that rather than returning an empty string.

    The two configurations that make sense are therefore:

      enable_api = true,  enable_cloudfront = false   the shipping shape (D1)
      enable_api = true,  enable_cloudfront = true    the pre-D1 shape, blocked by AWS

    `scripts/deploy/deploy.sh` sets this. Flipping `enable_cloudfront` later puts a CDN in
    front of the SAME function; the Function URL is preserved, the public hostname changes
    and the submission form has to be updated with it — which is why the default ships the
    hostname that does not depend on an AWS support queue.
  EOT
  type        = bool
  default     = true
}

variable "lambda_package_path" {
  description = <<-EOT
    The deployment zip produced by `scripts/deploy/build_lambda.sh` / `.ps1`.

    Relative paths are resolved against this root module's directory
    (`infra/envs/demo`), which is why the default climbs three levels to the repository
    root. The deploy script passes an ABSOLUTE path with `-var`, because it knows where
    the build put the file and Terraform should not have to guess.

    It does not exist in a clean checkout. With `enable_api = false` it is never read.

    The default names the arm64 artefact because `build_lambda.sh` defaults to arm64:
    Graviton2 is ~20 % cheaper per GB-second and `psycopg-binary` 3.3.4 publishes a cp313
    aarch64 wheel. IF YOU CHANGE ONE, CHANGE BOTH — a zip carrying aarch64 `.so` files on
    an `x86_64` function imports psycopg and dies with `ELFCLASS` on the first
    invocation, which looks like a database problem and is not.
  EOT
  type        = string
  default     = "../../../out/lambda/mainline-demo-api-arm64.zip"
}

variable "lambda_architecture" {
  description = <<-EOT
    `arm64` or `x86_64`, and it MUST match the zip named by `lambda_package_path`.

    `scripts/deploy/build_lambda.sh --arch <this>` writes
    `out/lambda/mainline-demo-api-<this>.zip`, and `scripts/deploy/deploy.sh` passes both
    values from one variable so they cannot drift apart. Terraform cannot check this for
    you: an architecture mismatch is a valid plan, a successful apply, and a runtime
    `ELFCLASS` error on the first request.
  EOT
  type        = string
  default     = "arm64"

  validation {
    condition     = contains(["arm64", "x86_64"], var.lambda_architecture)
    error_message = "lambda_architecture must be arm64 or x86_64."
  }
}

variable "lambda_reserved_concurrency" {
  description = <<-EOT
    The Lambda's reserved concurrency, passed straight through to `module.api`'s
    `reserved_concurrent_executions`. `-1` means "reserve nothing, draw from the account's
    unreserved pool"; `0`-`1000` reserves that many for this function alone.

    THE DEFAULT IS `-1` AND IT IS A MEASUREMENT, NOT A PREFERENCE. The module defaults to
    20 and the committed plan carries `+ reserved_concurrent_executions = 20`. Twenty
    cannot be applied on this account. Measured on 2026-08-13 from this machine under
    `AWS_PROFILE=mainline-dev`, in BOTH regions this project touches:

        aws lambda get-account-settings --region ap-southeast-1
          AccountLimit.ConcurrentExecutions            10
          AccountLimit.UnreservedConcurrentExecutions  10

        aws lambda get-account-settings --region ap-southeast-2
          AccountLimit.ConcurrentExecutions            10
          AccountLimit.UnreservedConcurrentExecutions  10

        aws service-quotas get-service-quota --service-code lambda \
            --quota-code L-B99A9384 --region ap-southeast-1
          QuotaName "Concurrent executions"   Value 10.0   Adjustable true

    AWS refuses any POSITIVE reservation on an account whose ceiling is 10, because
    granting it would push `UnreservedConcurrentExecutions` below the minimum AWS keeps
    free for every other function in the account. `PutFunctionConcurrency` is the SIXTH of
    the eleven API calls this apply makes, so the refusal does not arrive at the start: it
    arrives with five resources already created, and the operator is left holding a
    half-applied stack and an error message about a number rather than about a quota.

    THIS DOES NOT RAISE THE COST CEILING, AND THE ARITHMETIC IS ONE LINE. `min(20, 10) =
    10`. The account ceiling already caps this function at 10 concurrent executions, which
    is BELOW the 20 the module asks to reserve — so the reservation was never the binding
    constraint, and removing it removes an unappliable request while leaving exactly the
    same physical bound in place. The worst case in
    [`docs/deploy/COST-BOUND.md`](../../../docs/deploy/COST-BOUND.md) is computed at
    concurrency 10 for precisely this reason: 10 is what the account permits, and 10 is
    what the account permitted with the 20 still in the file. This change costs nothing
    and unblocks everything; it is the only one in the deploy-safety wave of which both
    halves of that sentence are true.

    THE CEILING OF 10 IS `Adjustable: true`, AND THAT IS THE PART TO BE AFRAID OF. Every
    dollar of the flood arithmetic is LINEAR in this number — the worst case is a byte
    rate, the byte rate is concurrency divided by invocation latency, and raising
    `L-B99A9384` from 10 to 100 multiplies the 30-day worst case by ten. Nothing stands
    behind it: the Function URL is `authorization_type = NONE`, no CloudWatch alarm in
    this stack has an action wired to a reader, and the account's three AWS Budgets are
    already breached by unrelated projects and carry zero actions between them. **Nobody
    requests a concurrency quota increase on this account without reading
    `docs/deploy/COST-BOUND.md` first.** The sentence you are reading is the bound.

    `0` REMAINS SETTABLE, AND IT IS THE KILL SWITCH. Reserving 0 decreases nothing — it
    takes no capacity out of the unreserved pool — so it is the one reservation this
    account can still accept, and it stops the function dead: every invocation is
    throttled before the handler runs, the Function URL answers 429, and spend stops at
    the moment the call returns. That is DOCUMENTED AWS behaviour and it is **not measured
    on this account**, because measuring it requires `PutFunctionConcurrency`, a mutating
    call this wave is forbidden to make. It ships labelled as documented rather than
    asserted as measured. `scripts/deploy/kill_switch.{sh,ps1}` is the one-command form.

    WHAT ELSE READS THIS VALUE — named before it was changed, because in this repository a
    "harmless" default is routinely load-bearing for something else:

      · `infra/modules/demo-api/main.tf` sets `aws_lambda_function
        .reserved_concurrent_executions` from it. That is the only RESOURCE attribute it
        reaches, and the only one whose change AWS charges for.
      · The CloudWatch dashboard's markdown widget interpolates the number verbatim into
        the sentence "The cost ceiling is `reserved_concurrent_executions = …`". At `-1`
        that sentence names a control that no longer exists; the dashboard is
        `infra/modules/demo-api/main.tf`'s to correct, not this file's, and it is on the
        wave's list.
      · Lambda emits the PER-FUNCTION `ConcurrentExecutions` metric dependably for
        functions that HAVE reserved concurrency. At `-1` the `-concurrency` alarm can sit
        in `INSUFFICIENT_DATA` and prove nothing — the module's own alarm description
        already says so, in advance, which is the only reason this is a known cost rather
        than a surprise. That alarm is not this root's to fix, but this variable is the
        reason it must be, and leaving it unsaid would ship exactly the "control that
        looks present and is not" the module's `lifecycle.precondition` idiom exists to
        refuse.
  EOT
  type        = number
  default     = -1

  validation {
    condition     = var.lambda_reserved_concurrency == -1 || (var.lambda_reserved_concurrency >= 0 && var.lambda_reserved_concurrency <= 1000)
    error_message = "lambda_reserved_concurrency must be -1 (unreserved) or 0-1000, mirroring the validation on reserved_concurrent_executions in infra/modules/demo-api/variables.tf. On THIS account the measured concurrency ceiling is 10, so every positive value is refused at apply by PutFunctionConcurrency; -1 and 0 are the only two that apply, and 0 stops the function entirely."
  }
}

variable "dsn_parameter_name" {
  description = <<-EOT
    The NAME — never the value — of the SSM Parameter Store SecureString holding the
    CockroachDB Cloud DSN for the `mainline_api` login.

    Terraform is given the name and grants the Lambda role `ssm:GetParameter` plus
    `kms:Decrypt` on that one ARN. The value is written by `aws ssm put-parameter
    --type SecureString` in step 2 of the deploy script and is never seen by Terraform,
    so it cannot appear in the state file, in a plan, or in `terraform show`.

    The handler reads it once per cold start from `$MAINLINE_DSN_PARAM` and caches it for
    the life of the execution environment — see
    `verticals/mainline/apps/demo-api/src/mainline_demo_api/db.py`, which names this
    exact environment variable.
  EOT
  type        = string
  default     = "/mainline/demo/cockroach_dsn"

  validation {
    condition     = can(regex("^/mainline/", var.dsn_parameter_name))
    error_message = "dsn_parameter_name must live under /mainline/ so teardown can identify it as ours."
  }
}

variable "demo_signer_sub" {
  description = <<-EOT
    The principal the demo's fourth beat signs as, passed through to `module.api`'s
    `demo_signer_sub` and published to the function as `$MAINLINE_DEMO_SIGNER_SUB`.

    THIS ROOT AND THE MODULE HOLD THE SAME DEFAULT, AND THE SEED HOLDS THE TRUTH.
    `verticals/mainline/db/seeds/demo/demo_world.sql` line 125 inserts the literal
    `'demo.signer'` into `mainline.signing_credential.signer_sub`, and
    `scripts/deploy/seed_demo.py` is what applies that file to the database this deployment
    points at. Both Terraform defaults MIRROR that line. If the database this root deploys
    against is seeded with a different principal, this variable is where that is said - the
    seed is never edited to match Terraform.

    WHY IT IS WIRED HERE AT ALL RATHER THAN LEFT TO THE MODULE DEFAULT. It is the same
    argument `lambda_reserved_concurrency` makes at the top of this file: a value that is
    load-bearing for a beat, and that could differ between this environment's database and
    the module's assumption, belongs in the environment that owns the database. The module's
    default is right for THIS seed; a root variable is how a second environment says
    otherwise without patching the module.

    `mainline_demo_api.scenario.from_env` reads `MAINLINE_DEMO_SIGNER_SUB`
    (`scenario.py:209`) and falls back to the in-code constant `"demo.signer"` when it is
    absent or blank. Until this wave the module published nothing for it, so the beat that
    writes a disposition ran on a compiled-in constant. `mainline.fn_disposition_project`
    joins `mainline.person` on this string
    (`verticals/mainline/db/migrations/0102_fn_disposition_project.sql:155`), so it is a key
    the database reads, not a label the application carries.

    It must DIFFER from `demo_countersigner_sub`; the database refuses the equal case
    (`0066_disposition.sql:176`) and the module refuses it at plan time with a
    `lifecycle.precondition` rather than letting it reach beat 4.
  EOT
  type        = string
  default     = "demo.signer"

  validation {
    condition     = var.demo_signer_sub != "" && trimspace(var.demo_signer_sub) == var.demo_signer_sub
    error_message = "demo_signer_sub must be non-empty and carry no leading or trailing whitespace, mirroring the validation on demo_signer_sub in infra/modules/demo-api/variables.tf. scenario.from_env computes `.strip() or \"demo.signer\"`, so a blank value silently falls back to the in-code constant while still showing up in `aws lambda get-function-configuration` - an override that looks set and is not."
  }
}

variable "demo_countersigner_sub" {
  description = <<-EOT
    The second principal beat 4 countersigns as, passed through to `module.api`'s
    `demo_countersigner_sub` and published as `$MAINLINE_DEMO_COUNTERSIGNER_SUB`.
    Everything said about `demo_signer_sub` above applies; only the citation moves.

    THE AUTHORITATIVE SOURCE IS `verticals/mainline/db/seeds/demo/demo_world.sql` line 133,
    which inserts `'demo.countersigner'` into `mainline.signing_credential.signer_sub`.
    `scenario.from_env` reads the variable at `scenario.py:210-212` and falls back to the
    in-code constant when it is absent or blank;
    `verticals/mainline/db/migrations/0102_fn_disposition_project.sql:167,174` joins
    `mainline.person` on it.

    It must differ from `demo_signer_sub`. The demo's admit beat is a two-signature
    disposition and `mainline.disposition` refuses a self-countersignature
    (`needs_second_signer`, `0066_disposition.sql:176`), so equality is not a degraded demo
    but a CHECK violation in the only beat that writes anything. `module.api` refuses it at
    plan time.
  EOT
  type        = string
  default     = "demo.countersigner"

  validation {
    condition     = var.demo_countersigner_sub != "" && trimspace(var.demo_countersigner_sub) == var.demo_countersigner_sub
    error_message = "demo_countersigner_sub must be non-empty and carry no leading or trailing whitespace, mirroring the validation on demo_countersigner_sub in infra/modules/demo-api/variables.tf. scenario.from_env computes `.strip() or \"demo.countersigner\"`, so a blank value silently falls back to the in-code constant."
  }
}

# ══════════════════════════════════════════════════════════════════════════════════════
#  THE SHAPE OF THE FUNCTION, AND THE SIX BOUNDS IT ENFORCES
# ══════════════════════════════════════════════════════════════════════════════════════
#
# EVERY VARIABLE IN THIS SECTION EXISTS BECAUSE ITS VALUE WAS PREVIOUSLY A MODULE DEFAULT
# NOBODY IN THIS ENVIRONMENT HAD CHOSEN. That is the same argument
# `lambda_reserved_concurrency` makes at the top of this file, applied to ten more values:
# a module default is written against the account and the measurements its author had, and
# this root is the thing that knows which database, which region and which bill are
# actually involved.
#
# Two of them — `api_timeout_seconds` and `api_memory_size_mb` — were 15 s and 512 MB, and
# both defaults were justified by reasoning `docs/deploy/LATENCY.md` has since falsified by
# measurement. Six of them — the `MAINLINE_*` bounds — were not published to the function
# at all, so they ran on constants compiled into the application: in force, correct, and
# unreadable from `aws lambda get-function-configuration`.
#
# THE AUTHORITY FOR THE SIX IS THE APPLICATION, NOT THIS FILE. Each default cites the
# constant it mirrors. If a code default moves, THESE MOVE TO MATCH — the same rule
# `demo_signer_sub` follows toward the seed, pointed at the application instead. Publishing
# a value that disagrees with the code is worse than publishing nothing, because the
# environment variable WINS at runtime while reading like documentation.

variable "api_timeout_seconds" {
  description = <<-EOT
    The demo function's timeout, in seconds. 14.

    IT IS A RELIABILITY BOUND AND IT IS NOT A SPEND BOUND. Lambda bills actual duration, so
    a 5.66 ms invocation costs exactly the same under a 14 s timeout as under a 3 s one:
    THIS NUMBER MOVES THE BILL BY NOTHING. Under a sustained flood the four cost terms are
    `egress`, `requests`, `compute` and the request count, and `timeout` appears in none of
    them (`docs/deploy/LATENCY.md` §6). Nobody may present it as a cost lever.

    THE 3 s THAT WAS ASKED FOR IS REFUSED, on arithmetic rather than on preference. 3,000 ms
    is 0.80x the warm in-region `gate_run` p99 corrected to Lambda (3,729 ms), so it would
    truncate the headline beat — the only beat that writes anything, and the one on screen
    — on the p99 alone, with no cold start and no `40001` retry involved. `LATENCY.md` §5.1
    lists five separate things 3 s truncates; the fifth is 100 of 100 measured cloud gate
    runs at 11,688 ms p99, which is what a judge running `demo_acceptance.py` from outside
    ap-southeast-1 sees. A truncated headline beat is a far worse defect than a larger bill,
    and here it is not even a trade, because of the paragraph above.

    14 is the smallest whole second that clears `LATENCY.md` §5.1's binding case — a cold
    start at 256 MB with a 2x worse tail, 13,022.9 ms — and it clears it by 1.07x. The
    module's own `timeout` variable carries the term-by-term table.

    IT IS COUPLED TO `api_memory_size_mb` AND TO `api_duration_p99_threshold_ms`, and both
    couplings are checked at plan time by `lifecycle.precondition`s in the module. Halving
    memory raised the binding case from 10,497 ms to 13,023 ms, which is why 14 and not 11;
    and the p99 alarm threshold must sit strictly below `timeout * 1000` or it cannot fire.
    SATISFY THOSE PRECONDITIONS BY CHOOSING CONSISTENT VALUES. Never relax one to make a
    plan succeed.
  EOT
  type        = number
  default     = 14

  validation {
    condition     = var.api_timeout_seconds >= 1 && var.api_timeout_seconds <= 29
    error_message = "api_timeout_seconds must be 1-29, mirroring the validation on timeout in infra/modules/demo-api/variables.tf: above 29 s the function outlives CloudFront's 30 s origin read timeout in the AWS_IAM shape. docs/deploy/LATENCY.md 5.1 says do not go below 14 and do not go near 3; that instruction is not encoded as a floor here because a caller on a different model may honestly need a different number, and encoding a recommendation as a validation would make it unarguable rather than checked."
  }
}

variable "api_memory_size_mb" {
  description = <<-EOT
    The demo function's memory, in MB. 256, down from the module's old 512.

    IT IS THE ONLY LEVER IN THE MENU THAT IS DURATION-INDEPENDENT, and that — not its size
    — is why it is taken. Under a flood at the account concurrency ceiling, `egress`,
    `requests` and the flood rate itself all scale as `1/duration`, so making the function
    slower gives back most of what any byte lever takes; `compute` is
    `concurrency x memory_GB x window x price` and does not. Halving memory halves compute
    outright AND roughly halves the flood rate, because the CPU-bound beats then take about
    twice as long. `docs/leads/cost-finish-plan.md` §0.5 puts the compute line at
    USD 173 -> USD 86 per 30 days: 0.2 % of the modelled bill, and worth taking for the
    direction rather than for the dollars.

    WHAT IT COSTS, AND IT LANDS ON THE JUDGE'S FIRST CLICK: the modelled cold start rises
    from 5,248 ms to 6,511 ms, and the static-asset beats roughly double. There is NO
    MEASUREMENT of a 256 MB Lambda anywhere in this evidence and there cannot be one without
    an apply — `LATENCY.md` §4 is a throttled-core proxy, it is noisy, and it is labelled a
    proxy in both places it is used.

    WHY THE HEADLINE BEAT SURVIVES IT, MEASURED: 93 % of the gate run is CockroachDB
    executing (1,244.9 ms of a 1,336.6 ms server-reported run), and CockroachDB does not
    get slower when Lambda gets less CPU.

    RAISING IT BACK TO 512 IS A TWO-VARIABLE CHANGE, not a one-variable one:
    `api_duration_p99_threshold_ms`'s floor is derived from the cold path at THIS memory,
    so the admissible band moves with it.
  EOT
  type        = number
  default     = 256

  validation {
    condition     = var.api_memory_size_mb >= 128 && var.api_memory_size_mb <= 10240 && var.api_memory_size_mb % 64 == 0
    error_message = "api_memory_size_mb must be 128-10240 MB in 64 MB steps, mirroring the validation on memory_size in infra/modules/demo-api/variables.tf."
  }
}

variable "api_duration_p99_threshold_ms" {
  description = <<-EOT
    The `-duration-p99` alarm's threshold, in ms. 13,500, and it is PINNED BETWEEN A FLOOR
    AND A CEILING rather than set to a comfortable fraction of the timeout.

    IT WENT UP, FROM THE MODULE'S OLD 12,000, AND THAT IS THE UNCOMFORTABLE DIRECTION — so
    the reason is stated rather than left to be inferred. 12,000 was chosen when this alarm
    had NO ACTION. This root now passes `module.guard`'s SNS topic as `alarm_actions`, and
    everything subscribed to that topic calls
    `PutFunctionConcurrency(ReservedConcurrentExecutions=0)`. A breach is therefore not a
    red square any more; it takes the demo down until a human runs
    `scripts/deploy/kill_switch.sh --restore`. A threshold that was merely sensitive became
    a threshold that can cause an outage, so it had to be re-derived against the new
    consequence.

        FLOOR    13,023 ms   `LATENCY.md` §5.1's binding case — a COLD start at 256 MB with
                             a 2x worse tail. Below this the demo stops on a judge's first
                             click, which is not abuse and not an incident.
        CEILING  14,000 ms   `api_timeout_seconds * 1000`. Lambda caps the Duration
                             datapoint at the timeout, so at or above this the alarm cannot
                             fire at all.

    Both edges are `lifecycle.precondition`s on `aws_cloudwatch_metric_alarm.duration_p99`
    in `infra/modules/demo-api/main.tf`, checked at plan time and FALSIFIED rather than
    asserted: 12,000 and 13,022 are refused, 13,023 and the shipping 13,500 pass, 14,000 is
    refused by the ceiling half.

    THE FLOOR IS UNCONDITIONAL, AND ITS FIRST DRAFT WAS NOT. It was written to apply only
    when `alarm_actions` was non-empty, and that version DID NOT FIRE: this root reaches the
    topic through `try([module.guard[0].sns_topic_arn], [])`, `try()` yields a wholly
    unknown value when its argument contains an unknown, and Terraform defers an unknown
    precondition to apply instead of failing the plan. Planting `12000` planned cleanly. A
    precondition that cannot be evaluated at plan time is a control that looks present and
    is not, so the guard clause was deleted rather than repaired.

    THE BAND IS 1.075x WIDE AND THAT IS A REAL PROPERTY, NOT AN ARTEFACT. At 256 MB the
    modelled cold path very nearly fills the 14 s timeout, so "approaching the timeout" and
    "a cold start happened" are nearly the same event. If that band is ever EMPTY, the
    finding is that `api_timeout_seconds` is too small for `api_memory_size_mb` — it is not
    that a precondition should be widened.
  EOT
  type        = number
  default     = 13500

  validation {
    condition     = var.api_duration_p99_threshold_ms > 0 && var.api_duration_p99_threshold_ms <= 900000
    error_message = "api_duration_p99_threshold_ms must be between 1 and 900000. Both of its real edges read a second variable and are therefore checked at plan time by preconditions on aws_cloudwatch_metric_alarm.duration_p99: strictly below api_timeout_seconds * 1000 always, and strictly above the module's modelled_worst_legitimate_duration_ms whenever the alarm carries an action."
  }
}

variable "api_log_level" {
  description = <<-EOT
    The demo function's APPLICATION log level, published as `$LOG_LEVEL` and wired into
    `logging_config.application_log_level`. `WARN`, down from the module's old `INFO`.

    Log ingestion is billed on ARRIVAL and nothing in AWS bounds it natively;
    `log_retention_days` bounds storage and refunds nothing. Dropping a level costs nothing
    a reader wants, because `evidence/deploy/cost/log-bytes.json` measured this handler
    emitting p50 = 0 and mean = 0.001 wire bytes of its own per invocation across all five
    beats and across a sustained 429 flood. A working handler is silent at any level; the
    level only decides how loud a misbehaving one may be.

    WHAT IT DOES NOT DO, because the two knobs get confused: this is the APPLICATION level.
    The SYSTEM level — Lambda's own `platform.*` accounting, the 956 B/invocation term every
    ingestion threshold in `infra/modules/cost-guard` is derived from — is a separate field
    whose valid values are only `DEBUG | INFO | WARN`, is already hard-coded to `WARN` (the
    quietest the API accepts), and has NO PUBLISHED MAPPING from level to event type. So
    nothing in AWS's reference establishes that START / REPORT lines are suppressed at WARN,
    and this repository counts them as present. See `infra/modules/demo-api/variables.tf`
    § log_level for the citation and for what that pessimism buys.
  EOT
  type        = string
  default     = "WARN"

  validation {
    condition     = contains(["TRACE", "DEBUG", "INFO", "WARN", "ERROR", "FATAL"], var.api_log_level)
    error_message = "api_log_level must be one of TRACE, DEBUG, INFO, WARN, ERROR, FATAL - the set Lambda's application_log_level accepts. Note that the SYSTEM log level accepts only DEBUG, INFO and WARN; the two enums differ and a value legal here can be illegal there."
  }
}

variable "account_concurrency_ceiling" {
  description = <<-EOT
    The AWS Lambda `ConcurrentExecutions` quota of the account this root deploys into. 10.

    IT IS PASSED TO BOTH MODULES FROM HERE, and that is the whole reason it is a root
    variable. `infra/modules/demo-api` and `infra/modules/cost-guard` each default it to 10
    independently, and every reachability `lifecycle.precondition` in both of them divides
    by it. Two independent defaults for ONE measured account fact is two things that can
    drift apart silently, and the symptom of the drift would be a precondition guarding
    against the wrong ceiling — which is a control that looks present and is checking the
    wrong number.

    MEASURED 2026-08-13 under `AWS_PROFILE=mainline-dev`, in both regions this project
    touches, all four answers identical:

        aws lambda get-account-settings --region ap-southeast-1
          AccountLimit.ConcurrentExecutions            10
          AccountLimit.UnreservedConcurrentExecutions  10
        aws service-quotas get-service-quota --service-code lambda \
            --quota-code L-B99A9384 --region ap-southeast-1
          QuotaName "Concurrent executions"   Value 10.0   Adjustable true

    IT IS NOT A CONTROL. AWS marks it `Adjustable: true`, nobody here chose it, and a
    support ticket moves it. Raising this variable does not raise any limit — it only tells
    the two modules what your limit already is. Raising it to silence a precondition without
    raising the real quota re-creates the exact defect the precondition exists to refuse,
    and the modules' error messages say so.

    AND NOTE WHICH DIRECTION THE MONEY RUNS. The demo's Function URL is
    `authorization_type = NONE`, and the 30-day worst case is LINEAR in this number: raising
    `L-B99A9384` from 10 to 100 multiplies it by ten. Read `docs/deploy/COST-BOUND.md`
    before requesting an increase.
  EOT
  type        = number
  default     = 10

  validation {
    condition     = var.account_concurrency_ceiling >= 1
    error_message = "account_concurrency_ceiling must be at least 1; it is a measured account quota, not a limit this configuration sets."
  }
}

variable "guard_notification_emails" {
  description = <<-EOT
    Email addresses subscribed to the cost guard's SNS topic, so that a HUMAN finds out the
    demo was stopped and can run `scripts/deploy/kill_switch.{sh,ps1} --restore`.

    EMPTY, AND AN UNCONFIRMED SUBSCRIPTION IS A CONTROL THAT LOOKS PRESENT AND IS NOT.
    `aws_sns_topic_subscription` with `protocol = "email"` is created in
    `PendingConfirmation`; AWS mails a confirmation link and delivers nothing at all until
    somebody clicks it. Terraform reports the resource as created either way and cannot
    click it. A plausible-looking address here would therefore ship a notification path that
    exists in the plan, exists in the console, and never delivers.

    IT GATES NOTHING IN THE STOP PATH. The responder's subscription to the same topic is a
    Lambda subscription, is unconditional, and needs no confirmation — so the demo stops
    with or without a subscriber here. What an empty list costs is only that nobody is TOLD,
    which is why `scripts/deploy/kill_switch.sh --status` exists and why the runbook step
    after an unexplained 429 is to run it.

    Adding an address is a two-step operation and the second step is not Terraform's: apply,
    then open the mail and click the link, then confirm with
    `aws sns list-subscriptions-by-topic`.
  EOT
  type        = list(string)
  default     = []
}

variable "api_max_response_bytes" {
  description = <<-EOT
    The ceiling, in WIRE bytes, on any single response the demo function may emit.
    Published as `$MAINLINE_MAX_RESPONSE_BYTES`.

    139,264 (= 136 KiB), mirroring `static_site.py`'s `DEFAULT_MAX_RESPONSE_BYTES =
    136 * 1024`. That constant is DERIVED FROM THE DEPLOYED TREE and not chosen: the largest
    `.gz` object that actually ships measures 124,127 B
    (`evidence/deploy/cost/package-shape.json`), and the ceiling sits at 1.122x it — inside
    the rule `largest_served_wire_bytes <= MAX_RESPONSE_BYTES < 1.20 x
    largest_served_wire_bytes`. A ceiling above everything it governs is a decoration, which
    is what 512 KiB had silently become once the source-map strip removed the one object it
    refused.

    WIRE BYTES, NOT THE BASE64 ENVELOPE. A gzip body must travel as
    `isBase64Encoded: true` and that string is 33 % larger than what leaves Lambda; a
    ceiling applied to the encoded form would over-refuse by exactly that.

    PUBLISHING IT DOES NOT SET IT. `static_site.max_response_bytes()` reads this variable
    and falls back to the compiled-in constant on anything that is not a positive integer,
    so this makes the ceiling READABLE without making Terraform the authority for it. The
    test that keeps the constant derived lives with the code; Terraform cannot see the
    package's contents and does not pretend to.
  EOT
  type        = number
  default     = 139264

  validation {
    condition     = var.api_max_response_bytes > 0 && floor(var.api_max_response_bytes) == var.api_max_response_bytes
    error_message = "api_max_response_bytes must be a positive whole number of bytes; static_site.max_response_bytes() parses it with int() and silently falls back to DEFAULT_MAX_RESPONSE_BYTES on anything else, which is an override that looks configured and is not."
  }
}

variable "api_rate_global_rps" {
  description = <<-EOT
    Sustained requests per second one execution environment serves across ALL callers before
    answering 429. Published as `$MAINLINE_RATE_GLOBAL_RPS`. 10, mirroring
    `ratelimit.py`'s `DEFAULT_GLOBAL_RPS = 10.0`.

    THIS IS THE FIRST ORDER-OF-MAGNITUDE LEVER IN THE WHOLE COST MODEL and it was running
    unpublished. `docs/leads/cost-finish-plan.md` §0.5 takes the modelled 30-day worst case
    from USD 47,297 to USD 4,205 on this row alone — more than every byte lever multiplied
    together — and until this wave the number producing that reduction was a constant nobody
    had chosen and nobody could read off the deployed function.

    IT IS PER EXECUTION ENVIRONMENT, so the fleet bound is
    `api_rate_global_rps x account_concurrency_ceiling` = 100 rps, which is what §0.5's
    rate-bounded row is costed at. Raising `account_concurrency_ceiling` raises the fleet
    bound proportionally even though this number has not moved.
  EOT
  type        = number
  default     = 10

  validation {
    condition     = var.api_rate_global_rps > 0 && var.api_rate_global_rps <= 10000
    error_message = "api_rate_global_rps must be greater than 0 and at most 10000 (ratelimit.MAX_RPS). ratelimit._rate() refuses inf, nan, non-positive values and anything above MAX_RPS by falling back to the compiled-in default, so a value outside this range is an override that silently does not apply."
  }
}

variable "api_rate_global_burst" {
  description = <<-EOT
    Bucket capacity across all callers: how many requests may arrive instantly before the
    sustained rate binds. Published as `$MAINLINE_RATE_GLOBAL_BURST`. 100, mirroring
    `ratelimit.py`'s `DEFAULT_GLOBAL_BURST = 100`.

    It is a separate knob from the rate rather than derived from it, and this is the number
    that keeps the control from breaking the demo: a page load IS a burst — the console
    fetches `index.html` plus its hashed assets in one go — and a bucket sized to the
    sustained rate would refuse the console's own assets on the first click.
  EOT
  type        = number
  default     = 100

  validation {
    condition     = var.api_rate_global_burst >= 1 && var.api_rate_global_burst <= 100000 && floor(var.api_rate_global_burst) == var.api_rate_global_burst
    error_message = "api_rate_global_burst must be a whole number between 1 and 100000 (ratelimit.MAX_BURST). ratelimit._burst() parses with int(), which RAISES on \"1.5\" rather than truncating, and falls back to the compiled-in default."
  }
}

variable "api_rate_ip_rps" {
  description = <<-EOT
    Sustained requests per second from ONE source address. Published as
    `$MAINLINE_RATE_IP_RPS`. 5, mirroring `ratelimit.py`'s `DEFAULT_IP_RPS = 5.0` — half the
    global rate, so no single caller can be more than half an instance's sustained budget.

    WHAT IT DOES NOT DO, said here because the module says it: this bounds a CALLER, not an
    ATTACKER. A flood from many source addresses is bounded by the global pair and by
    nothing in this variable.
  EOT
  type        = number
  default     = 5

  validation {
    condition     = var.api_rate_ip_rps > 0 && var.api_rate_ip_rps <= 10000
    error_message = "api_rate_ip_rps must be greater than 0 and at most 10000 (ratelimit.MAX_RPS); outside that range ratelimit._rate() falls back to the compiled-in default and the published value is inert."
  }
}

variable "api_rate_ip_burst" {
  description = <<-EOT
    Bucket capacity for one source address. Published as `$MAINLINE_RATE_IP_BURST`. 50,
    mirroring `ratelimit.py`'s `DEFAULT_IP_BURST = 50`: half the global burst, and still
    large enough to swallow a whole page load in one go, so the first click on the console
    is never the thing this control refuses.
  EOT
  type        = number
  default     = 50

  validation {
    condition     = var.api_rate_ip_burst >= 1 && var.api_rate_ip_burst <= 100000 && floor(var.api_rate_ip_burst) == var.api_rate_ip_burst
    error_message = "api_rate_ip_burst must be a whole number between 1 and 100000 (ratelimit.MAX_BURST); ratelimit._burst() parses with int() and falls back to the compiled-in default on anything else."
  }
}

variable "api_log_budget_bytes" {
  description = <<-EOT
    How many bytes of its OWN log records the handler may emit per invocation before the
    budget truncates. Published as `$MAINLINE_LOG_BUDGET_BYTES`. 4,096, mirroring
    `logbudget.py`'s `DEFAULT_BUDGET_BYTES = 4096`.

    RAISING IT IS A TWO-MODULE CHANGE. `infra/modules/cost-guard`'s
    `log_incoming_bytes_threshold` is DERIVED from the per-invocation byte ceiling this
    feeds; `evidence/deploy/cost/log-bytes.json` names raising `DEFAULT_BUDGET_BYTES` as one
    of exactly three things that would invalidate that threshold, and says it must be raised
    proportionally. Moving this alone makes the ingestion alarm fire on traffic the
    invocation alarms deliberately permit.

    WHAT IT DOES NOT BOUND, measured rather than imagined: records written on a logger the
    budget's filter is not attached to. 200 psycopg records reached a handler as 75,800 wire
    bytes and this budget charged ZERO for them. That shape decouples bytes from invocations
    without limit, and it is the whole reason the guard carries an ingestion alarm that is
    not a copy of its invocation alarms.
  EOT
  type        = number
  default     = 4096

  validation {
    condition     = var.api_log_budget_bytes >= 1 && floor(var.api_log_budget_bytes) == var.api_log_budget_bytes
    error_message = "api_log_budget_bytes must be a positive whole number of bytes; logbudget parses $MAINLINE_LOG_BUDGET_BYTES with int() and falls back to DEFAULT_BUDGET_BYTES on anything else."
  }
}

variable "cloudfront_price_class" {
  description = <<-EOT
    `PriceClass_All`, `PriceClass_200` or `PriceClass_100`.

    ONLY READ WHEN `enable_cloudfront = true`. With the default `false` there is no
    distribution and this value reaches no resource.

    `PriceClass_All` is the default and it costs nothing extra here, because the whole
    demo sits inside CloudFront's perpetual free tier (1 TB egress, 10 M requests a
    month) and a judging round is a few hundred requests. A narrower price class would
    save nothing and would add latency for a judge in a region we did not guess.
  EOT
  type        = string
  default     = "PriceClass_All"

  validation {
    condition     = contains(["PriceClass_All", "PriceClass_200", "PriceClass_100"], var.cloudfront_price_class)
    error_message = "cloudfront_price_class must be PriceClass_All, PriceClass_200 or PriceClass_100."
  }
}

variable "log_retention_days" {
  description = <<-EOT
    CloudWatch Logs retention for the Lambda's log group.

    7 days. Well inside the 5 GB/month free ingest, and long enough that a failure during
    judging is still readable the next morning. Never `0` (never expire): an unbounded
    log group is the only line item in this stack that can grow without a ceiling.
  EOT
  type        = number
  default     = 7

  validation {
    condition     = contains([1, 3, 5, 7, 14, 30], var.log_retention_days)
    error_message = "log_retention_days must be one of the short CloudWatch retentions: 1, 3, 5, 7, 14, 30."
  }
}

variable "tags" {
  description = <<-EOT
    Extra tags merged into `default_tags`, on top of `project=mainline` and
    `managed_by=terraform`, which are not overridable from here — teardown keys its
    refusal on `project=mainline`, so making it a variable would make the safety control
    a matter of opinion.
  EOT
  type        = map(string)
  default     = {}
}
