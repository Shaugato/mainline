# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
#
# ═══════════════════════════════════════════════════════════════════════════════════════
#  THE DEMO ENVIRONMENT — one distribution, one hostname, two origins
# ═══════════════════════════════════════════════════════════════════════════════════════
#
#                          ┌────────────────────────────────────────────┐
#   judge's browser ─────► │ CloudFront   dXXXXXXXX.cloudfront.net      │  HTTPS, free cert
#                          │   default behaviour  →  S3 (OAC, private)  │  console + bundle
#                          │   /v1/*              →  Lambda FURL (OAC)  │  the live API
#                          └───────────────────┬────────────────────────┘
#                                              │ SigV4, AWS_IAM Function URL
#                                              ▼
#                                  Lambda · ap-southeast-1 · python3.13
#                                              │ pgwire/TLS, same region
#                                              ▼
#                         CockroachDB Cloud Basic · mainline-dev · Singapore
#
# One distribution and one hostname buys three things at once: no CORS anywhere, one URL
# to put in the submission form, and a Function URL with `authorization_type = AWS_IAM`
# that therefore CANNOT be invoked except through CloudFront. That last one is
# simultaneously the security posture and the cost ceiling.
#
# ── THE DEPENDENCY THAT LOOKS LIKE A CYCLE, AND IS NOT — BUT ONLY IF WRITTEN THIS WAY ─
#
# The two modules refer to each other:
#
#     module.site  needs  module.api.function_url_domain   → to create the /v1/* origin
#     module.api   needs  module.site.distribution_arn     → to scope the invoke grant
#
# At the MODULE level that reads as a cycle. At the RESOURCE level, which is the level
# Terraform's graph actually works at, it is not one — because the invoke grant is a
# separate resource from the function:
#
#     aws_lambda_function        (api)   ─┐
#     aws_lambda_function_url    (api)   ─┴─► aws_cloudfront_distribution (site)
#                                                          │
#                                             aws_lambda_permission (api) ◄─┘
#
# That is the theory. THE THEORY IS NOT ENOUGH, and this file was written twice because
# of it. The first version reached the Function URL with a splat:
#
#     api_origin_domain = join("", module.api[*].function_url_domain)      # WRONG
#
# and `terraform plan` refused, on Terraform v1.14.8, with a real cycle:
#
#     Error: Cycle: module.site.output.distribution_arn (expand),
#     module.api.var.distribution_arn (expand), module.api.aws_lambda_permission
#     .cloudfront, module.api (close), local.api_origin_domain (expand),
#     module.site.var.api_origin_domain (expand), module.site.local.has_api (expand),
#     module.site.aws_cloudfront_distribution.this
#
# Read the fourth element. `module.api (close)` is the whole-module node a SPLAT over a
# counted module depends on — and every resource in the module feeds it, INCLUDING
# `aws_lambda_permission`. The splat therefore says "the distribution depends on
# everything in the api module", which drags the permission back into the site's
# dependencies and closes the loop. An INDEXED reference does not touch the close node:
# it depends on that one output, which depends on `aws_lambda_function_url` alone.
#
#     api_origin_domain = try(module.api[0].function_url_domain, "")       # RIGHT
#
# `try()` and not a `? :` conditional, because with `enable_api = false` the count is
# zero and `module.api[0]` is an invalid index — an error the conditional cannot dodge
# and `try` catches, yielding "" and therefore the Phase-1 shape. Measured after the fix,
# against the real module contract, on this machine:
#
#     terraform plan -var enable_api=true    →  Plan: 11 to add, 0 to change, 0 to destroy
#     terraform plan -var enable_api=false   →  Plan:  5 to add, 0 to change, 0 to destroy
#
# One plan, one apply, no cycle, in both phases. No two-stage apply is needed and none is
# shipped; README.md § "The dependency that looks like a cycle" carries the transcript.
#
# The consequence for the two modules is a contract, and README.md § "Module contract"
# states it normatively. Two clauses of it exist ONLY because the harness found them:
#
#   · `demo-api`'s ONLY reference to `demo-site` must be from `aws_lambda_permission`.
#     If the Function URL, the function, or the role ever reads `var.distribution_arn`,
#     the cycle is real and no amount of indexing saves it.
#   · `demo-site` must take `enable_api` as its own plan-time-known boolean and must NOT
#     derive `count`/`for_each` from `api_origin_domain != ""`. The domain is unknown
#     until apply, and a count that depends on it fails with "Invalid count argument:
#     The count value depends on resource attributes that cannot be determined until
#     apply". That was the second error this harness produced, and it is the reason
#     `enable_api` is passed to BOTH modules rather than inferred from the string.
#
# ── WHAT IS NOT HERE ───────────────────────────────────────────────────────────────────
#
#   · No Route 53 zone, no ACM certificate. `https://dXXXXXXXX.cloudfront.net` is valid
#     HTTPS on CloudFront's own certificate and costs nothing; a hosted zone is $0.50 a
#     month and an ACM cert for CloudFront must be issued in us-east-1, which means a
#     second provider alias. Rejected as gold-plating (deploy-plan § 2.3).
#   · No DynamoDB lock table. See backend.tf.
#   · No secret. See variables.tf § dsn_parameter_name.
#   · No CloudWatch Synthetics canary: one canary at five-minute intervals is $10.37 a
#     month, thirty times the cost of everything else in this file combined.

provider "aws" {
  region = var.aws_region

  # Applied to every taggable resource created by this root, INCLUDING the ones inside
  # the two modules. `scripts/deploy/teardown.sh` reads `project=mainline` back off the
  # live resource before it deletes anything, so this block is the mechanism by which
  # teardown can tell our four resources apart from the four unrelated projects living in
  # this account. It is not decoration.
  default_tags {
    tags = merge(
      {
        project    = "mainline"
        managed_by = "terraform"
      },
      var.tags,
    )
  }
}

data "aws_caller_identity" "current" {}

locals {
  # Derived rather than required, so that `terraform apply` with no arguments works and
  # still produces a globally unique bucket name carrying the `mainline-demo-` prefix.
  site_bucket_name = (
    var.site_bucket_name != ""
    ? var.site_bucket_name
    : "${var.name_prefix}-site-${data.aws_caller_identity.current.account_id}"
  )

  # INDEXED, wrapped in `try`. Not a splat — a splat depends on `module.api (close)` and
  # produces the cycle transcribed in the header. Not a `? :` conditional either — with
  # `enable_api = false` the count is zero and `module.api[0]` is an invalid index that a
  # conditional does not dodge. `try` catches exactly that error and yields "", which is
  # the signal `demo-site` takes to mean "no second origin, no /v1/* behaviour".
  #
  # This is a load-bearing three-token expression. Changing it to `one(...)`,
  # `join("", ...)` or `coalesce(...)` reintroduces the splat and the cycle with it.
  api_origin_domain = try(module.api[0].function_url_domain, "")
}

# ── The site: private S3 bucket, CloudFront distribution, both behaviours ─────────────
#
# This module owns the hostname. It exists in every configuration of this root, including
# Phase 1, because THE URL IS THE DELIVERABLE and nothing else in this file is allowed to
# be able to take it down.

module "site" {
  source = "../../modules/demo-site"

  name_prefix = var.name_prefix
  bucket_name = local.site_bucket_name
  price_class = var.cloudfront_price_class
  tags        = var.tags

  # TWO inputs and not one, and that is a measured requirement rather than a preference.
  # `enable_api` is known at plan time and is what the module's `count`/`for_each` must
  # key on; `api_origin_domain` is unknown until the Function URL exists and may only be
  # used as a VALUE inside a resource. Collapsing them into `api_origin_domain != ""`
  # fails the plan with "Invalid count argument". See the header.
  enable_api        = var.enable_api
  api_origin_domain = local.api_origin_domain
}

# ── The API: Lambda, IAM-only Function URL, role, logs, alarms ────────────────────────
#
# `count` and not `for_each`: there is one API or there is no API, and `count = 0` is the
# Phase-1 cut line stated as HCL.

module "api" {
  source = "../../modules/demo-api"
  count  = var.enable_api ? 1 : 0

  # `function_name` and not `name_prefix`: the module takes the whole Lambda name,
  # because that one string also fixes the log group `/aws/lambda/<name>`, the alarm
  # names and the dashboard name. Composing it here keeps the `mainline-demo-` prefix —
  # which teardown keys on — under this root's control rather than the module's.
  function_name      = "${var.name_prefix}-api"
  package_path       = var.lambda_package_path
  architecture       = var.lambda_architecture
  dsn_parameter_name = var.dsn_parameter_name
  log_retention_days = var.log_retention_days
  tags               = var.tags

  # The one reference back into `site`. It is consumed by `aws_lambda_permission`, which
  # is a different resource from `aws_lambda_function` and `aws_lambda_function_url` —
  # and that separation is the entire reason a single apply converges. See the header.
  cloudfront_distribution_arn = module.site.distribution_arn
}
