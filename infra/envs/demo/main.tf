# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
#
# ═══════════════════════════════════════════════════════════════════════════════════════
#  THE DEMO ENVIRONMENT — one hostname, and AWS decides which resource owns it
# ═══════════════════════════════════════════════════════════════════════════════════════
#
# ── THE SHIPPING SHAPE, var.enable_cloudfront = false (DEFAULT) ────────────────────────
#
#                          ┌────────────────────────────────────────────┐
#   judge's browser ─────► │ https://<id>.lambda-url.<region>.on.aws    │  HTTPS, AWS cert
#                          │   AWS Lambda · python3.13 · auth = NONE    │  ONE origin
#                          │     GET  /            → console SPA        │  from the zip
#                          │     GET  /bundle/*    → signed evidence    │  REPLAY source
#                          │     GET  /v1/*        → read resources     │  LIVE source
#                          │     POST /v1/demo/gate-run → the four beats│
#                          └───────────────────┬────────────────────────┘
#                                              │ pgwire/TLS, same region
#                                              ▼
#                         CockroachDB Cloud Basic · mainline-dev · Singapore
#
# ── THE UPGRADE, var.enable_cloudfront = true ──────────────────────────────────────────
#
#                          ┌────────────────────────────────────────────┐
#   judge's browser ─────► │ CloudFront   dXXXXXXXX.cloudfront.net      │  HTTPS, free cert
#                          │   default behaviour  →  S3 (OAC, private)  │  console + bundle
#                          │   /v1/*              →  Lambda FURL (OAC)  │  the live API
#                          └───────────────────┬────────────────────────┘
#                                              │ SigV4, AWS_IAM Function URL
#                                              ▼
#                                  Lambda · ap-southeast-1 · python3.13
#
# ── WHY THE DEFAULT INVERTED — THIS IS A MEASUREMENT, NOT A PREFERENCE ─────────────────
#
# This file used to say, on the `module "site"` block below, that the SITE MODULE OWNS THE
# HOSTNAME, that it exists in every configuration of this root, and that nothing else here
# is allowed to be able to take the URL down. The reasoning was right and the premise was
# wrong. A real `terraform apply` on 2026-08-10 created seven resources and AWS refused the
# eighth:
#
#     Error: creating CloudFront Distribution: operation error CloudFront:
#     CreateDistributionWithTags, https response error StatusCode: 403,
#     RequestID: 3e63e30d-8c5b-441b-a01b-b70085eba504, AccessDenied:
#     Your account must be verified before you can add new CloudFront resources.
#     To verify your account, please contact AWS Support and include this error message.
#
# The same refusal comes from a bare `aws cloudfront create-distribution` with a minimal
# config and no Terraform involved, from an identity holding `AdministratorAccess`. It is
# an ACCOUNT-LEVEL VERIFICATION HOLD ON NEW CLOUDFRONT RESOURCES — the account already has
# one distribution from an unrelated project, created 2026-04-16, so the hold is on new
# ones and not on the service. Only AWS Support can lift it, and the submission deadline
# is 2026-08-18. `docs/deploy/RUNBOOK.md` line 26 carries the transcript.
#
# So decision D1 (`docs/leads/ship-final.md` §1.4): THE API OWNS THE HOSTNAME AND THE SITE
# IS OPTIONAL. A Lambda Function URL is HTTPS on an AWS-issued certificate, needs no
# account verification, no ACM and no hosted zone, and one origin serving both the SPA and
# `/v1/*` means no CORS and one string in the submission form. Nobody is allowed to let
# CloudFront hold the URL hostage.
#
# Two facts make the inversion cheap and both were checked before it was made:
# `verticals/mainline/apps/console/vite.config.ts` sets `base: './'`, and the console uses
# HASH ROUTING. A relative-base SPA with hash routes serves correctly from any prefix,
# including a Function URL root, with no rebuild-time knowledge of the host.
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
# and `try` catches, yielding "" and therefore the site-only shape.
#
# ALL FOUR CONFIGURATIONS, MEASURED ON THIS MACHINE ON 2026-08-11, Terraform v1.14.8 with
# `hashicorp/aws v6.58.0`, against the real modules and real AWS credentials:
#
#   enable_cloudfront  enable_api   terraform plan
#   ─────────────────  ──────────   ────────────────────────────────────────────────────
#   false (default)    true         Plan: 11 to add, 0 to change, 0 to destroy   ← SHIPS
#   true               true         Plan: 22 to add, 0 to change, 0 to destroy
#   true               false        Plan:  9 to add, 0 to change, 0 to destroy
#   false              false        REFUSED at plan — output "demo_url" precondition
#
# One plan, one apply, no cycle, in every configuration that builds anything. No two-stage
# apply is needed and none is shipped. The first two rows are committed verbatim as
# `evidence/deploy/terraform-plan-furl.txt` and `evidence/deploy/terraform-plan-cloudfront
# .txt`; README.md § "The dependency that looks like a cycle" carries the reasoning.
#
# ── THE SAME TRAP NOW EXISTS IN THE REVERSE DIRECTION, AND IS DISARMED THE SAME WAY ────
#
# `module.site` is now counted too (`var.enable_cloudfront`), so THE REVERSE REFERENCE HAS
# BECOME AN INDEX AS WELL and it is written to the identical rule:
#
#     cloudfront_distribution_arn = try(module.site[0].distribution_arn, "")   # RIGHT
#     cloudfront_distribution_arn = join("", module.site[*].distribution_arn)  # WRONG
#
# The splat form would depend on `module.site (close)`, which every S3 resource and the
# distribution feed — and the distribution depends, via `local.api_origin_domain`, on the
# api module. The loop closes exactly as it did in 2026-08-10's first attempt, in mirror
# image. Anything wired between these two modules in future must go through `try()` and an
# index, in BOTH directions, or not be wired at all.
#
# The other half of the rule is unchanged and is the reason `enable_cloudfront` is a plain
# `bool` variable rather than something derived: A `count` MAY ONLY DEPEND ON A VALUE THAT
# IS KNOWN AT PLAN TIME. `count = var.enable_cloudfront ? 1 : 0` is safe because
# `var.enable_cloudfront` is a variable and is therefore constant by the time counts are
# evaluated. `count = local.api_origin_domain != "" ? 1 : 0` is NOT safe, because a Lambda
# Function URL hostname does not exist until apply and Terraform refuses the whole plan
# with "Invalid count argument: The count value depends on resource attributes that cannot
# be determined until apply". That was the second error this harness produced and it is
# still the reason `enable_api` is passed to BOTH modules rather than inferred.
#
# The consequence for the two modules is a contract, and README.md § "Module contract"
# states it normatively. Two clauses of it exist ONLY because the harness found them:
#
#   · `demo-api`'s ONLY reference to `demo-site` must be from `aws_lambda_permission`.
#     If the Function URL, the function, or the role ever reads `var.distribution_arn`,
#     the cycle is real and no amount of indexing saves it.
#   · `demo-site` must take `enable_api` as its own plan-time-known boolean and must NOT
#     derive `count`/`for_each` from `api_origin_domain != ""`.
#
# ── WHAT IS NOT HERE ───────────────────────────────────────────────────────────────────
#
#   · No Route 53 zone, no ACM certificate. Neither hostname needs one: a Function URL and
#     a `*.cloudfront.net` name are both valid HTTPS on an AWS-issued certificate and cost
#     nothing. A hosted zone is $0.50 a month and an ACM cert for CloudFront must be issued
#     in us-east-1, which means a second provider alias. Rejected as gold-plating
#     (deploy-plan § 2.3).
#   · No DynamoDB lock table. See backend.tf.
#   · No secret. See variables.tf § dsn_parameter_name.
#   · No CloudWatch Synthetics canary: one canary at five-minute intervals is $10.37 a
#     month, thirty times the cost of everything else in this file combined.
#   · No literal account id. See variables.tf § "NO ACCOUNT ID IS SPELLED IN THIS FILE".

provider "aws" {
  region = var.aws_region

  # Applied to every taggable resource created by this root, INCLUDING the ones inside
  # the two modules. `scripts/deploy/teardown.sh` reads `project=mainline` back off the
  # live resource before it deletes anything, so this block is the mechanism by which
  # teardown can tell our resources apart from the four unrelated projects living in
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

# The account id is DERIVED here and nowhere written down (decision D2, ship-final §1.6).
# `output.aws_account_id` reads this, so it is a run-time value rather than a committed
# literal that is correct on exactly one machine.
data "aws_caller_identity" "current" {}

locals {
  # Derived rather than required, so that `terraform apply` with no arguments works and
  # still produces a globally unique bucket name carrying the `mainline-demo-` prefix.
  # Only reaches a resource when `var.enable_cloudfront` is true.
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

  # THE MIRROR IMAGE OF THE LINE ABOVE, and it exists because `module.site` is now counted
  # too. Same rule, same reason, same three tokens: index, never splat. With
  # `enable_cloudfront = false` the count is zero, `module.site[0]` is an invalid index,
  # and `try` yields "" — which `demo-api` reads as "no distribution to scope a grant to",
  # consistent with the `url_authorization_type = "NONE"` it is given in the same shape.
  site_distribution_arn = try(module.site[0].distribution_arn, "")

  # ── THE ONE STRING A HUMAN PASTES INTO A BROWSER ────────────────────────────────────
  #
  # Two candidate hostnames, exactly one of which exists in any given configuration, and
  # `var.enable_cloudfront` decides which. Both branches are wrapped in `try` because the
  # module that produces them is absent in the other branch and `module.X[0]` on a
  # zero-count module is an error rather than a null.
  #
  # AWS returns a Function URL with a trailing slash (`https://<id>.lambda-url.<region>
  # .on.aws/`). It is trimmed here so that `demo_url` has ONE shape in both branches and a
  # consumer building `${demo_url}/v1/health` cannot produce a `//v1/health` that some
  # routers answer and some do not. `output.demo_url_source` names which expression won.
  api_demo_url        = try(trimsuffix(module.api[0].function_url, "/"), "")
  cloudfront_demo_url = try("https://${module.site[0].distribution_domain_name}", "")
  demo_url            = var.enable_cloudfront ? local.cloudfront_demo_url : local.api_demo_url

  # Plan-time known, unlike `demo_url` itself, so a reviewer reading the committed plan can
  # see which resource was going to own the hostname without waiting for an apply.
  demo_url_source = (
    var.enable_cloudfront
    ? "module.site[0].distribution_domain_name (CloudFront)"
    : "module.api[0].function_url (Lambda Function URL)"
  )
}

# ── The site: private S3 bucket, CloudFront distribution, both behaviours ─────────────
#
# OPTIONAL, AND OFF BY DEFAULT. This module used to own the hostname unconditionally; AWS
# refuses to create its central resource on this account (403 AccessDenied, RequestID
# 3e63e30d-8c5b-441b-a01b-b70085eba504 — see the header), so under decision D1 it became
# the upgrade rather than the foundation. Everything in it is still correct and still
# planned; it is simply not the thing the submission form depends on.
#
# `count` on a plain `bool` VARIABLE, which is constant by the time counts are evaluated.
# The header explains at length why a count on anything derived from a resource attribute
# is a plan that does not run.

module "site" {
  source = "../../modules/demo-site"
  count  = var.enable_cloudfront ? 1 : 0

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

# ── The API: Lambda, Function URL, role, logs, alarms ─────────────────────────────────
#
# `count` and not `for_each`: there is one API or there is no API. Under D1 this module
# owns the hostname, so `enable_api = false` together with `enable_cloudfront = false` is
# a root that creates nothing and has no URL to emit — `output.demo_url`'s precondition
# says so out loud instead of returning "".

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

  # ── THIS ONE EXPRESSION IS THE WHOLE ARCHITECTURAL SWITCH ────────────────────────────
  #
  # "NONE"    the Function URL is public and IS the demo hostname. No `aws_lambda_
  #           permission` for `cloudfront.amazonaws.com` is created — the resource is
  #           `count = 0` inside the module, absent from the plan rather than present and
  #           inert. What bounds the exposure is NOT authentication and the module's README
  #           says so plainly: `reserved_concurrent_executions` (a hard cap), the handler's
  #           single rolled-back transaction, the CockroachDB Basic spend limit, and the
  #           `-concurrency` alarm.
  #
  # "AWS_IAM" an unsigned request gets 403 with an empty body, and the single
  #           `lambda:InvokeFunctionUrl` grant is created, scoped by SourceArn to the
  #           distribution below. That shape is only reachable when a distribution exists,
  #           which is precisely what `var.enable_cloudfront` decides — so deriving the
  #           auth type from the same variable is what makes the flip ONE variable instead
  #           of two that can disagree. `AWS_IAM` with no distribution is not a hardened
  #           demo; it is a URL that answers 403 to everyone, including the judges.
  url_authorization_type = var.enable_cloudfront ? "AWS_IAM" : "NONE"

  # The one reference back into `site`. It is consumed by `aws_lambda_permission`, which
  # is a different resource from `aws_lambda_function` and `aws_lambda_function_url` —
  # and that separation is the entire reason a single apply converges. INDEXED through
  # `try` because `site` is counted; a splat here rebuilds the 2026-08-10 cycle in mirror
  # image. See the header.
  cloudfront_distribution_arn = local.site_distribution_arn
}
