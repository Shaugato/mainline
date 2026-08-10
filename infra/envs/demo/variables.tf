# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
#
# Every variable here has a default that works on this account, so that
# `terraform apply` with no `-var` at all is a valid thing to do. The defaults are not
# placeholders: they are the values `scripts/deploy/deploy.sh` uses.
#
# The one exception is `lambda_package_path`, which has a default but whose default is a
# *build output* — the file does not exist in a clean checkout, and `terraform plan` will
# say so plainly rather than pretend. That is why `var.enable_api` exists.

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

    This is a safety control, not a cosmetic one. The AWS account 022950218246 holds four
    unrelated live projects. `scripts/deploy/teardown.sh` refuses to delete anything whose
    name does not start with this prefix AND which does not carry the tag
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

variable "site_bucket_name" {
  description = <<-EOT
    The S3 bucket holding the console build and the EvidenceBundle.

    Empty (the default) means "derive it": `<name_prefix>-site-<account id>`, which on
    this account is `mainline-demo-site-022950218246`. S3 bucket names are globally
    unique across all AWS customers, so a hard-coded constant in a public repository is a
    name somebody else has already taken; deriving from the account id makes it unique
    without asking the operator to invent anything, and keeps the `mainline-demo-` prefix
    teardown keys on.

    The bucket is PRIVATE. It has no website configuration and no public policy — reads
    arrive only through CloudFront Origin Access Control.
  EOT
  type        = string
  default     = ""
}

variable "enable_api" {
  description = <<-EOT
    Whether to create the Lambda, its Function URL, its IAM role, its log group, its
    alarms, and the CloudFront behaviour that routes `/v1/*` at it.

    `false` is THE PHASE-1 CUT LINE (`docs/leads/deploy-plan.md` § 4). It produces a
    complete, working, HTTPS demo URL serving the console over the verified
    EvidenceBundle with a `REPLAY` badge, and no backend at all. Nothing about that path
    can be broken by a Lambda that is not ready.

    `scripts/deploy/deploy.sh --phase1` sets this. Flipping it back to `true` and
    re-applying adds the API to the SAME distribution and the SAME URL; the judge's link
    never changes.
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
