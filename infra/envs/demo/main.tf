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
  # ── THE ONE STRING TWO MODULES SHARE, AND THE CYCLE THAT IS ONE TOKEN AWAY ───────────
  #
  # `module "api"` composed this inline as `function_name = "${var.name_prefix}-api"` until
  # `module "guard"` existed. It is hoisted because TWO modules need it and they reference
  # each other's neighbourhood:
  #
  #     module.guard  needs  the function NAME             to scope its stop
  #     module.api    needs  module.guard.sns_topic_arn    to arm its alarms
  #
  # `infra/modules/cost-guard` is built so this never has to be a cycle: it takes
  # `guarded_function_name` as a plain STRING and constructs the ARN itself from
  # `aws_caller_identity` / `aws_region` / `aws_partition` (`cost-guard/main.tf:158`). So
  # the name is computed HERE, from a variable, and handed to both modules as a constant.
  #
  # ── WHAT THIS COMMENT CLAIMED, AND WHAT PLANTING IT ACTUALLY MEASURED ────────────────
  #
  # It asserted that `guarded_function_name = module.api[0].function_name` "produces
  # `Error: Cycle:` at plan time" and that this was "the only one of the three variants an
  # index and a `try()` cannot disarm". THAT WAS WRONG, and it was written without being
  # run. Both forms were planted on this machine, Terraform v1.14.8, `hashicorp/aws
  # v6.58.0`, read-only credentials:
  #
  #   guarded_function_name = module.api[0].function_name        INDEXED
  #     -> Plan: 24 to add, 0 to change, 0 to destroy.           NO CYCLE
  #
  #   guarded_function_name = one(module.api[*].function_name)   SPLAT
  #     -> Error: Cycle: module.api.output.alarm_actions_armed (expand),
  #        module.api.aws_cloudwatch_dashboard.this, module.api.output.dashboard_name
  #        (expand), module.api.output.alarm_names (expand), MODULE.API (CLOSE),
  #        module.api.aws_cloudwatch_metric_alarm.concurrency, ...
  #        module.guard.aws_sns_topic.guard, module.guard.output.sns_topic_arn (expand),
  #        local.guard_stop_topic_actions (expand), module.api.var.alarm_actions (expand),
  #        ... module.guard.var.guarded_function_name (expand)
  #
  # So the rule is EXACTLY the one this file's header already states, not a new one: it is
  # the SPLAT that is fatal, because a splat depends on the `module.api (close)` node and
  # every alarm in that module feeds it - and those alarms now consume the guard's topic,
  # which closes the loop. An INDEXED reference touches one output and its one resource,
  # and the api/guard pair is the same shape as the api/site pair: the two references land
  # on different resources (`aws_lambda_function.this` out, the four alarms in).
  #
  # ── SO WHY KEEP THE LOCAL, GIVEN THE INDEXED FORM WORKS ─────────────────────────────
  #
  # Three reasons, none of them "otherwise it cycles":
  #
  #   1. IT IS ONE TOKEN FROM A CYCLE AND THE FAILURE IS TOTAL. `[0]` -> `[*]` is a
  #      refactor somebody makes to "handle the disabled case", and it takes the whole plan
  #      down with a message that names sixteen graph nodes. A constant cannot be
  #      refactored into a splat because there is nothing to splat.
  #   2. THE GUARD BECOMES INDEPENDENT OF THE API MODULE. `cost-guard` validates this name
  #      against `^[A-Za-z0-9_-]{1,64}$` and builds one exact IAM ARN from it. Taken from a
  #      local, that validation and that ARN are plan-time known no matter what the api
  #      module is doing; `guard_guarded_function_arn` is a concrete string in the
  #      committed plan rather than "(known after apply)", which is what lets a reviewer
  #      compare it against `api_function_name` before an apply instead of after.
  #   3. It is interface I6 of `docs/leads/cost-finish-plan.md`, fixed there so six workers
  #      would not each rediscover the graph.
  api_function_name = "${var.name_prefix}-api"

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

  # THE STOP TOPIC, REACHED BY THE SAME THREE TOKENS EVERY CROSS-MODULE REFERENCE IN THIS
  # FILE USES: index, never splat, wrapped in `try`. `module.guard` is counted on
  # `var.enable_api`, so at count zero `module.guard[0]` is an INVALID INDEX rather than a
  # null and `try` is what turns that into the empty list `demo-api` reads as "these four
  # alarms report and do not act". A splat would depend on `module.guard (close)`, which is
  # the shape of the 2026-08-10 cycle recorded in the header — and here it would be a live
  # hazard rather than a theoretical one, because `module.guard` and `module.api` genuinely
  # do reference each other's neighbourhood.
  #
  # There is deliberately no `? :` conditional: with `enable_api = false` the index is an
  # error and a conditional does not dodge an error, it evaluates both branches' validity.
  # That is the same three-line reasoning `local.api_origin_domain` carries above, and it is
  # repeated rather than cross-referenced because a reader arriving at this line is trying
  # to decide whether to "simplify" it.
  guard_stop_topic_actions = try([module.guard[0].sns_topic_arn], [])

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
  # which teardown keys on — under this root's control rather than the module's. It is now
  # a LOCAL rather than an inline expression, because `module.guard` needs the identical
  # string and taking it from this module's output would be a cycle — see `local
  # .api_function_name`.
  function_name      = local.api_function_name
  package_path       = var.lambda_package_path
  architecture       = var.lambda_architecture
  dsn_parameter_name = var.dsn_parameter_name
  log_retention_days = var.log_retention_days
  tags               = var.tags

  # ── THE SHAPE OF THE FUNCTION, PASSED RATHER THAN INHERITED ──────────────────────────
  #
  # These four stood at the module's defaults until this wave, which meant `timeout` was
  # 15 s and `memory_size` 512 MB because a module written for a different account said so,
  # and NOBODY IN THIS ENVIRONMENT HAD CHOSEN EITHER. `docs/deploy/LATENCY.md` has since
  # measured the beats and both defaults moved with it; they are passed explicitly here so
  # that the environment that owns the database and the bill is the thing that states them.
  #
  # `api_timeout_seconds` is a RELIABILITY bound and NOT a spend bound. Lambda bills actual
  # duration, so a 5.66 ms invocation costs exactly the same at 14 s as at 3 s. Nobody may
  # present this number as a cost lever; variables.tf carries the refusal of the 3 s that
  # was asked for, and `LATENCY.md` §5.1 carries the arithmetic.
  timeout                   = var.api_timeout_seconds
  memory_size               = var.api_memory_size_mb
  duration_p99_threshold_ms = var.api_duration_p99_threshold_ms
  log_level                 = var.api_log_level

  # The measured account fact, passed from ONE place to BOTH modules that reason about it,
  # so `demo-api` and `cost-guard` cannot end up holding two different ideas of the same
  # quota. Every reachability precondition in either module divides by it.
  account_concurrency_ceiling = var.account_concurrency_ceiling

  # ── THE SIX BOUNDS THAT WERE IN FORCE AND UNREADABLE ─────────────────────────────────
  #
  # `static_site.py`, `ratelimit.py` and `logbudget.py` each enforce a real bound and each
  # reads an environment variable that overrides it. None was published, so all six ran on
  # constants compiled into the application: enforced, correct, and invisible to
  # `aws lambda get-function-configuration`. The rate bound in particular is the FIRST
  # order-of-magnitude lever in `docs/leads/cost-finish-plan.md` §0.5's table — the one that
  # takes the modelled worst case from USD 47,297 to USD 4,205 — and it was running on a
  # code default nobody had chosen either.
  #
  # THE SEED-VS-CODE RULE APPLIES HERE TOO, POINTING THE OTHER WAY. For the two signer subs
  # the DATABASE is authoritative and Terraform mirrors it. For these six the APPLICATION is
  # authoritative and Terraform mirrors it: each default below cites the constant it copies,
  # and if a code default moves these move to match. Publishing a value that disagrees with
  # the code is worse than publishing nothing, because the environment variable WINS while
  # reading like documentation.
  max_response_bytes = var.api_max_response_bytes
  rate_global_rps    = var.api_rate_global_rps
  rate_global_burst  = var.api_rate_global_burst
  rate_ip_rps        = var.api_rate_ip_rps
  rate_ip_burst      = var.api_rate_ip_burst
  log_budget_bytes   = var.api_log_budget_bytes

  # ── THE TWO PRINCIPALS BEAT 4 SIGNS AS, AND THE REASON THEY ARE WIRED FROM HERE ───────
  #
  # `mainline_demo_api.scenario.from_env` reads `MAINLINE_DEMO_SIGNER_SUB` and
  # `MAINLINE_DEMO_COUNTERSIGNER_SUB` (scenario.py:209-212) and falls back to the constants
  # "demo.signer" / "demo.countersigner" compiled into the application when they are absent.
  # The module published NEITHER until this wave, so the only beat that writes a disposition
  # ran on values no deployed configuration named. The defaults are correct — they mirror
  # `verticals/mainline/db/seeds/demo/demo_world.sql:125,133`, which is what
  # `scripts/deploy/seed_demo.py` applies — and correct-but-unpublished is precisely the
  # state this root exists to end for a value whose authority lives in THIS environment's
  # database. `mainline.fn_disposition_project` joins `mainline.person` on both strings
  # (0102_fn_disposition_project.sql:155,174), so they are keys the database reads.
  #
  # `MAINLINE_DEMO_SITE_ID` is NOT passed and there is no variable for it. The same
  # projector projects the site away (invariant I02, gate_run.py:106-111), so it is measured
  # NOT load-bearing, and publishing it would ship an override that looks configured and is
  # inert. See the module's environment block.
  demo_signer_sub        = var.demo_signer_sub
  demo_countersigner_sub = var.demo_countersigner_sub

  # ── THIS ONE EXPRESSION IS THE WHOLE ARCHITECTURAL SWITCH ────────────────────────────
  #
  # "NONE"    the Function URL is public and IS the demo hostname. No `aws_lambda_
  #           permission` for `cloudfront.amazonaws.com` is created — the resource is
  #           `count = 0` inside the module, absent from the plan rather than present and
  #           inert. What bounds the exposure is NOT authentication, and the honest list is
  #           SHORTER than the one this comment used to carry: the AWS account's measured
  #           concurrency ceiling of 10 (see `lambda_reserved_concurrency` below — it is
  #           the only bound on rate, and nobody chose it), the handler's single
  #           rolled-back transaction (which bounds database STATE, not spend), and the
  #           CockroachDB Basic spend limit (which bounds the database side only — the
  #           flood target is the static tree in the zip, which never opens a connection).
  #           `reserved_concurrent_executions` is NOT on that list any more and the
  #           `-concurrency` alarm never was: an alarm reports, it does not stop.
  #
  # "AWS_IAM" an unsigned request gets 403 with an empty body, and the single
  #           `lambda:InvokeFunctionUrl` grant is created, scoped by SourceArn to the
  #           distribution below. That shape is only reachable when a distribution exists,
  #           which is precisely what `var.enable_cloudfront` decides — so deriving the
  #           auth type from the same variable is what makes the flip ONE variable instead
  #           of two that can disagree. `AWS_IAM` with no distribution is not a hardened
  #           demo; it is a URL that answers 403 to everyone, including the judges.
  url_authorization_type = var.enable_cloudfront ? "AWS_IAM" : "NONE"

  # ── THE ONE ATTRIBUTE THAT DECIDES WHETHER THIS PLAN CAN BE APPLIED AT ALL ───────────
  #
  # The module defaults this to 20. TWENTY CANNOT BE APPLIED ON THIS ACCOUNT, and that is
  # a measurement taken on 2026-08-13 under `AWS_PROFILE=mainline-dev`, in both regions
  # this project touches:
  #
  #     aws lambda get-account-settings --region ap-southeast-1
  #       AccountLimit.ConcurrentExecutions            10
  #       AccountLimit.UnreservedConcurrentExecutions  10
  #     aws lambda get-account-settings --region ap-southeast-2
  #       AccountLimit.ConcurrentExecutions            10
  #       AccountLimit.UnreservedConcurrentExecutions  10
  #     aws service-quotas get-service-quota --service-code lambda \
  #         --quota-code L-B99A9384 --region ap-southeast-1
  #       QuotaName "Concurrent executions"   Value 10.0   Adjustable true
  #
  # AWS refuses every POSITIVE reservation on an account whose ceiling is 10, because
  # granting one would push `UnreservedConcurrentExecutions` below the minimum it keeps
  # free. `PutFunctionConcurrency` is the SIXTH of this apply's eleven API calls, so the
  # refusal lands with five resources already created — a half-applied stack, and an error
  # about a number rather than about a quota. The plan artefact was never the defect; the
  # account it targets cannot run it.
  #
  # THE COST CEILING IS UNCHANGED BY THIS LINE, and the arithmetic is `min(20, 10) = 10`.
  # The account ceiling already caps this function at 10 — below the 20 the module asked
  # to reserve — so the reservation was never the binding constraint. Passing -1 removes
  # an unappliable request and leaves the identical physical bound standing. It does not
  # raise exposure by one request per second, and `docs/deploy/COST-BOUND.md` computes the
  # worst case at concurrency 10 for exactly that reason.
  #
  # AND THE CEILING IS `Adjustable: true`. Every dollar of that worst case is LINEAR in
  # it: raising `L-B99A9384` from 10 to 100 multiplies the 30-day figure by ten, and there
  # is no second bound behind it — this URL is `authorization_type = NONE`, no alarm here
  # has a reader, and the account's budgets are already breached with zero actions on
  # them. NOBODY REQUESTS A CONCURRENCY QUOTA INCREASE WITHOUT READING
  # `docs/deploy/COST-BOUND.md` FIRST.
  #
  # `0` is still settable and is the documented kill switch — reserving 0 decreases
  # nothing, so it is the one reservation this account can still accept, and it throttles
  # every invocation before the handler runs. DOCUMENTED, NOT MEASURED HERE: confirming it
  # needs `PutFunctionConcurrency`, a mutating call this wave does not make.
  reserved_concurrent_executions = var.lambda_reserved_concurrency

  # The one reference back into `site`. It is consumed by `aws_lambda_permission`, which
  # is a different resource from `aws_lambda_function` and `aws_lambda_function_url` —
  # and that separation is the entire reason a single apply converges. INDEXED through
  # `try` because `site` is counted; a splat here rebuilds the 2026-08-10 cycle in mirror
  # image. See the header.
  cloudfront_distribution_arn = local.site_distribution_arn

  # ══════════════════════════════════════════════════════════════════════════════════════
  #  THE LINE THAT ARMS FOUR ALARMS, AND EXACTLY WHAT IT COSTS
  # ══════════════════════════════════════════════════════════════════════════════════════
  #
  # `infra/modules/cost-guard` was complete, valid and Stubber-tested for a whole wave and
  # WAS NEVER INSTANTIATED. `var.alarm_actions` stayed `[]`, so every alarm on this function
  # was actionless, and `evidence/deploy/terraform-plan-furl.txt` read `Plan: 11 to add`.
  # The previous wave's own finding — the bound is DOCUMENTED and NOT IMPLEMENTED — had
  # reproduced one level up as CODED and NOT INSTANTIATED, which on a plan output is the
  # same picture. These two lines and the `module "guard"` block below are that finding
  # closed.
  #
  # ── THIS IS A STOP TOPIC. IT DOES NOT NOTIFY; IT STOPS. ─────────────────────────────
  #
  # Everything subscribed to `module.guard[0].sns_topic_arn` invokes a responder that calls
  # `lambda:PutFunctionConcurrency(ReservedConcurrentExecutions=0)` on this function. The
  # URL then answers HTTP 429 with no body, to everyone, until a human runs
  # `scripts/deploy/kill_switch.{sh,ps1} --restore`. `demo-api` has ONE `alarm_actions` list
  # and wires it into all four of its alarms, so this line means, in full:
  #
  #   -errors        Sum > 0 / 5 min   ONE handler exception stops the demo
  #   -throttles     Sum > 0 / 5 min   one throttled invocation stops the demo
  #   -duration-p99  p99 > 13,500 ms   one slow window stops the demo
  #   -concurrency   Max > 8 / 5 min   an abuse tripwire stops the demo — the one of the
  #                                    four that is unambiguously a cost signal
  #
  # THREE OF THOSE ARE HEALTH SIGNALS AND STOPPING ON THEM IS A SELF-INFLICTED OUTAGE.
  # `infra/modules/cost-guard/outputs.tf` says so at length about this exact ARN and it is
  # right. It is done anyway, and the reason is a RANKING that this repository states rather
  # than a fact it overlooked — `docs/leads/cost-finish-plan.md` §0.5: an outage is
  # recoverable by one command and a bill is not. Under the founder's bounded-but-open
  # posture the URL has no authentication, so anyone at all can already trip the guard's own
  # burst alarm and stop the demo; these four widen the set of ways that can happen, they do
  # not create it. The residual column in `docs/deploy/COST-BOUND.md` is where that trade
  # belongs, and W6 owns writing it there.
  #
  # ── THE ONE CONSEQUENCE THAT IS REFUSED RATHER THAN ACCEPTED ────────────────────────
  #
  # A COLD START IS NOT AN INCIDENT. At `memory_size = 256` the modelled cold path is
  # 6,511 ms and its 2x-tail binding case is 13,023 ms (`LATENCY.md` §5.1), which is a
  # legitimate first click, not abuse — and `-duration-p99` at the old default of 12,000 ms
  # would have stopped the demo on it. The module therefore now carries a FLOOR precondition
  # on that alarm, pinning the threshold into 13,022 < T < 14,000. It is checked at PLAN
  # time and it is FALSIFIED rather than asserted: planting 12,000 or 13,022 is refused,
  # 13,023 and the shipping 13,500 pass, and 14,000 is refused by the ceiling half.
  #
  # THE FLOOR IS UNCONDITIONAL, AND ITS FIRST DRAFT WAS NOT. It read
  # `length(var.alarm_actions) == 0 || <the comparison>`, so a reporting-only caller would
  # not carry a floor - and it DID NOT FIRE, because the local below reaches the topic
  # through `try()`, `try()` yields unknown when its argument contains an unknown, and
  # Terraform defers an unknown precondition to apply rather than failing the plan. A
  # precondition that cannot be evaluated at plan time is a control that looks present and
  # is not, so the guard clause was deleted rather than repaired.
  #
  # ── AND ONE HAZARD THAT CANNOT BE SETTLED WITHOUT AN APPLY ──────────────────────────
  #
  # The guard's topic POLICY admits `cloudwatch.amazonaws.com` under an `ArnLike` on
  # `aws:SourceArn` naming exactly the guard's OWN THREE alarm ARNs
  # (`cost-guard/main.tf`, sid `TheseThreeAlarmsMayPublishAStop`). NONE of this module's
  # four alarms is in that list. Whether they can publish at all therefore rests on the
  # policy's first statement — SNS's default idiom, `Principal AWS:*` narrowed by
  # `AWS:SourceOwner` — and no plan can decide it: it takes a real breach on a real apply.
  # Both outcomes are recorded rather than assumed, because they are opposite defects:
  #
  #   admitted  -> the four alarms stop the demo, as described above
  #   denied    -> the four alarms carry an action SNS refuses, which `describe-alarms`
  #                renders identically to a delivered one — a control that looks present
  #                and is not, which is the exact defect this wave exists to close
  #
  # `evidence/deploy/cost/plan-shape.json` records both ARN sets side by side so the
  # question is visible in the evidence rather than living in one worker's head. THE
  # RESOLUTION IS NOT TO UNWIRE THIS LINE AND IT IS NOT TO WIDEN THE TOPIC POLICY'S
  # PRINCIPAL: it is for `infra/modules/cost-guard` to take an explicit list of additional
  # publisher ARNs, which is that module's owner's change and not this file's.
  alarm_actions = local.guard_stop_topic_actions

  # DELIBERATELY NOT `var.alarm_actions`, AND THIS IS THE HALF THAT HAS NO DEFENCE AT ALL.
  # `demo-api` used to compute `ok_actions = var.alarm_actions`, so arming the stop topic
  # would also have fired the STOP RESPONDER ON EVERY RECOVERY — a stop triggered by the
  # demo getting better. The responder refuses an OK transition on its own, but a control
  # belongs where the action is chosen and not in the thing that receives it;
  # `infra/modules/cost-guard` states that rule about its own three alarms and this is the
  # module that was the exception. Left empty: nothing in this stack has a human-facing
  # notification topic yet, and an alarm's recovery is not an event that should reach a
  # responder whose only verb is "stop".
  ok_actions = []
}

# ── The guard: one SNS topic, one responder, three cost alarms, one budget ────────────
#
# `count` on `var.enable_api`, and it is not decoration. A guard is scoped to exactly one
# function — `cost-guard` builds a single unqualified ARN from `guarded_function_name` and
# grants `lambda:PutFunctionConcurrency` on that ARN and nothing else. With
# `enable_api = false` there is no such function, so the alarms would sit in
# INSUFFICIENT_DATA forever and the responder's one call would 404: a stop mechanism that
# looks present and cannot fire. It exists exactly when the thing it stops exists.
#
# THERE IS NO `enable_cost_guard` VARIABLE AND THERE WILL NOT BE ONE. A boolean that turns
# the only stop in this stack off is the "variable somebody turns off at 02:00 to make a
# curl work" that `infra/modules/demo-api/variables.tf` names about authentication. The
# operational off-switch already exists and leaves a trace: `scripts/deploy/kill_switch.sh
# --restore` after a stop, and `--status` to read the current state.
#
# `guarded_function_name` TAKES THE LOCAL AND NEVER `module.api[0].function_name`. See
# `local.api_function_name` for the cycle that substitution produces and for why an index
# and a `try()` cannot disarm this one.
#
# EVERY THRESHOLD IN THE GUARD IS LEFT AT THE MODULE'S OWN DEFAULT, AND THAT IS A CHOICE
# RATHER THAN AN OMISSION — the opposite choice from the four demo-api values passed above.
# The difference is where the derivation lives. `demo-api`'s 15 s / 512 MB were written for
# a different account and are falsified by `docs/deploy/LATENCY.md`, so this environment has
# to state them. `cost-guard`'s three thresholds and its budget limit were derived THIS
# WAVE, in that module's own `variables.tf`, from measured beat durations, a measured
# per-invocation log term and a read-only Cost Explorer query — with `lifecycle
# .precondition`s in the module checking each one for reachability. Restating them here
# would create two places that can disagree about one derivation, and the preconditions
# would go on guarding the copy that is not the reason. `terraform output guard_thresholds`
# prints what is actually in force.

module "guard" {
  source = "../../modules/cost-guard"
  count  = var.enable_api ? 1 : 0

  guarded_function_name = local.api_function_name

  # The same measured account fact `module.api` is given, from one variable, so the two
  # modules cannot hold different ideas of the quota every reachability precondition in
  # both of them divides by.
  account_concurrency_ceiling = var.account_concurrency_ceiling

  # EMPTY BY DEFAULT, AND AN UNCONFIRMED SUBSCRIPTION IS A CONTROL THAT LOOKS PRESENT AND
  # IS NOT. `aws_sns_topic_subscription` with `protocol = "email"` is created in
  # `PendingConfirmation` and delivers nothing until somebody clicks the link; Terraform
  # reports it created either way and cannot click it. It gates nothing in the stop path —
  # the responder's subscription is a Lambda and is unconditional — so the only thing an
  # empty list costs is that the demo stops without anybody being told, which is why the
  # variable exists and why the runbook step is `kill_switch.sh --status`.
  notification_emails = var.guard_notification_emails

  tags = var.tags
}
