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
