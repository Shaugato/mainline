# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
#
# These outputs are a machine interface before they are a human one.
# `scripts/deploy/deploy.sh` and `deploy.ps1` read them with `terraform output -json` and
# feed them to `scripts/deploy/demo_acceptance.py` — and, when there is a distribution, to
# `aws s3 sync` and `aws cloudfront create-invalidation`. `scripts/deploy/teardown.sh`
# reads them to know what to delete. Renaming one breaks both scripts, so each name is
# load-bearing.
#
# EVERY DISTRIBUTION-SHAPED OUTPUT IS NULLABLE NOW. `module.site` is `count = 0` by
# default (decision D1 — AWS refuses to create a CloudFront distribution on this account;
# see variables.tf § enable_cloudfront for the 403 and its RequestID), so a reference to
# `module.site[0]` is an INVALID INDEX rather than a null. `try(…, null)` is what converts
# that error into the null a JSON consumer can branch on. `one(module.site[*].x)` would
# also work and is deliberately not used: a splat depends on the `module.site (close)`
# node, and main.tf's header records the cycle that dependency produced on 2026-08-10.
#
# NOTHING HERE IS SENSITIVE. There is no DSN, no password and no credential in this file,
# and there cannot be, because Terraform never held one. `aws_account_id` is a run-time
# value read from `data.aws_caller_identity`, not a committed literal — that is decision
# D2 (`docs/leads/ship-final.md` §1.6), and an AWS account id is in any case an identifier
# rather than a secret.

# ── THE DELIVERABLE ───────────────────────────────────────────────────────────────────

output "demo_url" {
  description = <<-EOT
    THE ONE STRING A HUMAN PASTES INTO A BROWSER, and the value that goes in the hackathon
    submission form's "URL to your functional demo app" field — Stage One, pass/fail.

    WHICH SOURCE PRODUCED IT depends on `var.enable_cloudfront`, and
    `output.demo_url_source` names the winning expression in words:

      enable_cloudfront = false (default)
          `module.api[0].function_url`, with AWS's trailing slash trimmed —
          `https://<id>.lambda-url.<region>.on.aws`. HTTPS on an AWS-issued certificate,
          no ACM, no hosted zone, no account verification. One origin serves the console
          SPA at `/`, the signed EvidenceBundle at `/bundle/*` and the API at `/v1/*`, so
          there is no CORS anywhere and one hostname covers the whole demo.

      enable_cloudfront = true
          `https://` + `module.site[0].distribution_domain_name` —
          `https://dXXXXXXXX.cloudfront.net`, HTTPS on CloudFront's own certificate. The
          Function URL becomes an origin rather than a destination and answers 403 to
          anything that is not this distribution.

    The trailing slash is trimmed in the Function URL branch so both branches have one
    shape and `$${demo_url}/v1/health` can never become `//v1/health`. `demo_acceptance.py`
    is pointed at this string, and a deploy whose acceptance run does not exit 0 against
    it is a failed deploy.
  EOT
  value       = local.demo_url

  precondition {
    # `enable_api = false` with `enable_cloudfront = false` is a root that creates nothing
    # at all. Under D1 the API owns the hostname, so that configuration has no URL to
    # emit, and an empty string presented as a demo URL is exactly the kind of unprovable
    # value `docs/HONESTY.md` exists to refuse. Fail here, loudly, with the fix in the
    # message.
    condition     = var.enable_api || var.enable_cloudfront
    error_message = "enable_api and enable_cloudfront are both false, so this root creates no resource that can serve a URL and demo_url has no source. Under decision D1 (docs/leads/ship-final.md 1.4) the Lambda Function URL IS the demo hostname: set enable_api = true. Set enable_cloudfront = true only if AWS has lifted the account verification hold on new CloudFront resources."
  }
}

output "demo_url_source" {
  description = <<-EOT
    Which expression produced `demo_url`, in words, as a plan-time-known string — so a
    reviewer reading the committed plan can see which resource was going to own the
    hostname without waiting for an apply. `demo_url` itself is "(known after apply)" in
    both branches, because neither a Function URL id nor a CloudFront domain exists until
    the resource does.
  EOT
  value       = local.demo_url_source
}

output "enable_cloudfront" {
  description = <<-EOT
    Echo of the switch, so a consumer does not have to infer the shape from whether
    `distribution_id` came back null.

    `false` — the default — means no distribution, no site bucket, no Origin Access
    Controls, and a PUBLIC Lambda Function URL that is the demo hostname. The default is a
    measurement: AWS returned `403 AccessDenied, "Your account must be verified before you
    can add new CloudFront resources"`, RequestID
    `3e63e30d-8c5b-441b-a01b-b70085eba504`, to a real apply on 2026-08-10 and to a bare
    `aws cloudfront create-distribution` on the same day. See variables.tf.
  EOT
  value       = var.enable_cloudfront
}

# ── Placement, read back from the run rather than restated from a literal ─────────────

output "aws_region" {
  description = "Region every resource above was created in. Teardown asserts against it before deleting anything."
  value       = var.aws_region
}

output "aws_account_id" {
  description = <<-EOT
    The account this configuration actually resolves against, read at run time from
    `data.aws_caller_identity.current.account_id`.

    IT IS AN OUTPUT AND NOT A COMMITTED LITERAL, and that is decision D2
    (`docs/leads/ship-final.md` §1.6): an account id written into a `variables.tf` default,
    a `backend-config` example or a deploy script's `EXPECTED_ACCOUNT` is an executable
    value that is correct on exactly one machine and wrong everywhere else. Derived, it is
    correct everywhere. Outside Terraform the same value comes from
    `aws sts get-caller-identity --query Account --output text`.

    The deploy script compares this against the account it was told to deploy into and
    refuses a mismatch unless `--any-account` is passed.
  EOT
  value       = data.aws_caller_identity.current.account_id
}

# ── The API — the hostname's owner in the default shape ───────────────────────────────

output "api_enabled" {
  description = "Whether `module.api` exists. Under D1 this is the module that owns the hostname, so `false` together with `enable_cloudfront = false` is a root that creates nothing — `demo_url`'s precondition refuses it."
  value       = var.enable_api
}

output "api_function_name" {
  description = "Lambda function name, or null when `enable_api = false`. `aws logs tail /aws/lambda/<this>` is the first thing to run when `/v1/health` is unhappy."
  value       = try(module.api[0].function_name, null)
}

output "api_function_url" {
  description = <<-EOT
    The full Function URL as AWS returns it, trailing slash and all, or null when
    `enable_api = false`.

    When `enable_cloudfront = false` this is `demo_url` modulo that trailing slash. It is
    emitted separately and unmodified so an operator can compare it byte for byte against
    `aws lambda get-function-url-config --function-name <name> --query FunctionUrl`.
  EOT
  value       = try(module.api[0].function_url, null)
}

output "api_function_url_domain" {
  description = "The Function URL host with no scheme and no path — what CloudFront's `/v1/*` origin takes as `domain_name`. Null when `enable_api = false`."
  value       = try(module.api[0].function_url_domain, null)
}

output "api_authorization_type" {
  description = <<-EOT
    `NONE` or `AWS_IAM`, read back off `aws_lambda_function_url.authorization_type` rather
    than off the variable that requested it — so it is the deployed truth and not a
    restatement of the request.

    `NONE` means `api_function_url` is publicly reachable and is the demo. `AWS_IAM` means
    an unsigned request gets 403 and only the CloudFront distribution named in the invoke
    grant can reach it. It follows `enable_cloudfront` by construction; an assertion in the
    acceptance run that these two disagree is a finding, not a formality.
  EOT
  value       = try(module.api[0].authorization_type, null)
}

output "cloudfront_invoke_grant_created" {
  description = "Whether the module created the `lambda:InvokeFunctionUrl` grant for `cloudfront.amazonaws.com`. `false` in the default shape, where the resource is `count = 0` and absent from the plan entirely rather than present and inert."
  value       = try(module.api[0].cloudfront_invoke_grant_created, false)
}

output "api_alarm_names" {
  description = <<-EOT
    The four alarm names `module.api` creates — `-errors`, `-throttles`, `-duration-p99`,
    `-concurrency` — or null when `enable_api = false`.

    ALL FOUR NOW CARRY AN ACTION, which they did not before this wave: `guard_sns_topic_arn`
    below. That topic's only subscriber stops the function, so a breach of any of these is
    an outage and not a notification. `api_alarm_arns` exists next to it for the one
    comparison that matters — see there.

    `treat_missing_data = "missing"` on all four, so `describe-alarms` answers
    INSUFFICIENT_DATA on a demo nobody has visited. That is the TRUE state and a consumer
    must not read it as a pass.
  EOT
  value       = try(module.api[0].alarm_names, null)
}

output "api_alarm_arns" {
  description = <<-EOT
    The four demo-api alarm ARNs, same order as `api_alarm_names`, or null when
    `enable_api = false`.

    IT IS HERE TO BE COMPARED AGAINST `guard_alarm_arns`, AND THE COMPARISON IS AN OPEN
    QUESTION RATHER THAN A FORMALITY. The guard's SNS topic policy admits
    `cloudwatch.amazonaws.com` under an `ArnLike` on `aws:SourceArn` naming exactly the
    guard's OWN three alarms. None of these four is in that list, and this root nonetheless
    passes the guard topic as their `alarm_actions`. Whether they can publish rests on the
    policy's first statement (SNS's default `Principal AWS:*` narrowed by
    `AWS:SourceOwner`), and only an apply plus a real breach settles it. If they cannot,
    four alarms carry an action SNS denies — indistinguishable in `describe-alarms` from one
    that delivers. `evidence/deploy/cost/plan-shape.json` records both sets so the question
    survives outside this description.
  EOT
  value       = try(module.api[0].alarm_arns, null)
}

output "api_published_bounds" {
  description = <<-EOT
    EVERY BOUND THE DEMO FUNCTION ENFORCES, IN ONE OBJECT — the six `MAINLINE_*` application
    bounds, the two AWS-side shape values (`timeout`, `memory_size`), the two log levels and
    the alarm thresholds. Null when `enable_api = false`.

    It exists because until this wave the honest answer to "what response ceiling, what rate
    limit, what log budget is this deployment enforcing?" was: unzip a 7.6 MB package and
    read a Python constant. Now it is `terraform output api_published_bounds`, and — because
    all six are also environment variables on the function — `aws lambda
    get-function-configuration --query Environment.Variables` from any read-only credential.

    EVERY FIELD IS KNOWN AT PLAN TIME, so this object is readable in the committed plan
    artefact and not only after an apply. Whether the alarms are ARMED is deliberately not
    one of those fields — it is `api_alarm_actions_armed` below, and it cannot be
    plan-known — because one unknown field would render the whole object as "(known after
    apply)" and take the readability away from all seventeen.
  EOT
  value       = try(module.api[0].published_bounds, null)
}

output "api_alarm_actions_armed" {
  description = <<-EOT
    Whether the four demo-api alarms carry an ALARM action. In this root that means the
    cost guard's STOP topic, so `true` says a breach of `-errors`, `-throttles`,
    `-duration-p99` or `-concurrency` takes the demo down until somebody runs
    `scripts/deploy/kill_switch.sh --restore`. Null when `enable_api = false`.

    "(known after apply)" in the plan, and not fixable: `local.guard_stop_topic_actions`
    reaches a counted module through `try()`, which yields unknown whenever its argument
    contains an unknown. The wiring is nonetheless provable from the plan's `configuration`
    section — see `evidence/deploy/cost/plan-shape.json`.
  EOT
  value       = try(module.api[0].alarm_actions_armed, null)
}

output "api_ok_actions_armed" {
  description = "Whether the four demo-api alarms notify anything on RECOVERY. `false`: a stop topic must not be reached by an alarm getting better, and since this wave `ok_actions` is a separate list from `alarm_actions` so that arming one cannot arm the other. Null when `enable_api = false`."
  value       = try(module.api[0].ok_actions_armed, null)
}

# ── The cost guard — the stop, and the three alarms that reach it ─────────────────────
#
# `module.guard` exists exactly when `module.api` does (`count = var.enable_api ? 1 : 0`),
# because a guard scoped to a function that does not exist is a stop mechanism whose alarms
# sit in INSUFFICIENT_DATA and whose one API call would 404. Every output below is
# `try(…, null)` for the same reason every site-shaped output above is: at count zero
# `module.guard[0]` is an INVALID INDEX, not a null, and `try` is what converts that error
# into something a JSON consumer can branch on.

output "guard_enabled" {
  description = "Whether the cost guard exists. It follows `enable_api`, and there is deliberately no separate switch: a boolean that turns the only stop in this stack off is the variable somebody turns off at 02:00 to make a curl work. The operational off-switch is `scripts/deploy/kill_switch.sh`, which leaves a trace."
  value       = var.enable_api
}

output "guard_sns_topic_arn" {
  description = <<-EOT
    THE STOP TOPIC. Publishing to it invokes the responder, which calls
    `lambda:PutFunctionConcurrency(ReservedConcurrentExecutions=0)` on the demo function.
    Null when `enable_api = false`.

    IT IS NOT A NOTIFICATION TOPIC AND MUST NEVER BE TREATED AS ONE. Anything subscribed
    here stops the demo; anything wired to it as an alarm action stops the demo on breach.
    This root passes it to `module.api`'s `alarm_actions` deliberately and does NOT pass it
    to `ok_actions` — a stop fired by an alarm RECOVERING is not a trade anybody chose.

    A human who wants to be told rather than to stop things wants
    `guard_notification_emails`, and has to click the confirmation link before that
    subscription delivers anything at all.
  EOT
  value       = try(module.guard[0].sns_topic_arn, null)
}

output "guard_responder_function_name" {
  description = "The responder function's name, or null. `aws logs tail /aws/lambda/<this> --follow` after an incident: it logs one JSON line per decision — stopped, refused, ignored — and that line is the record of whether the stop actually fired."
  value       = try(module.guard[0].responder_function_name, null)
}

output "guard_guarded_function_arn" {
  description = <<-EOT
    The single unqualified function ARN the responder's IAM grant names, or null.

    COMPARE IT AGAINST `api_function_name`. Both are built from `local.api_function_name`,
    so they agree by construction rather than by coincidence — that is the whole reason the
    name is hoisted into a local instead of taken from `module.api`'s output, which would be
    a Terraform cycle. If these two ever disagree, the guard is armed at a function that
    does not exist and the stop is a 403 nobody sees until the incident.
  EOT
  value       = try(module.guard[0].guarded_function_arn, null)
}

output "guard_alarm_names" {
  description = "The guard's three alarm names, in timescale order: 60 s invocations, 3600 s invocations, 300 s log ingestion. Null when `enable_api = false`. These are the COST alarms; `api_alarm_names` are the health ones."
  value       = try(module.guard[0].alarm_names, null)
}

output "guard_alarm_arns" {
  description = <<-EOT
    The guard's three alarm ARNs, or null. These are the EXACT ARNs named in the topic
    policy's `aws:SourceArn` condition, which is why they are emitted rather than left
    inside the module: the set of ARNs the topic admits and the set of alarms pointed at it
    are two different lists, and `api_alarm_arns` above is not a subset of this one.
  EOT
  value       = try(module.guard[0].alarm_arns, null)
}

output "guard_budget_name" {
  description = "The budget's name, for `aws budgets describe-budget --budget-name <name>`. Null when `enable_api = false`. It is an ACTUAL-cost notification, so it fires on money already spent — on an 8-24 h Cost Explorer lag AWS documents and no setting shortens. It is the backstop, never the bound."
  value       = try(module.guard[0].budget_name, null)
}

output "guard_thresholds" {
  description = <<-EOT
    Every threshold the cost guard enforces plus the reachability arithmetic behind it, so
    that "what is actually in force?" is one command and not a read of two `variables.tf`
    files. Null when `enable_api = false`.

    `*_visible_ms` is the slowest flood each invocation alarm can SEE: at the account
    concurrency ceiling, a flood of invocations slower than that cannot put enough of them
    into the window to breach. That is the number an operator needs when an alarm did not
    fire and the bill still moved, and it is the reason this object is worth an output.

    These thresholds are NOT restated in this root's variables. They were derived this wave
    inside `infra/modules/cost-guard/variables.tf`, from measured beat durations, a measured
    per-invocation log term and a read-only Cost Explorer query, and each is guarded by a
    `lifecycle.precondition` in that module. Copying them here would create two places that
    can disagree about one derivation.
  EOT
  value       = try(module.guard[0].thresholds, null)
}

# ── The site — null in the default shape, and that is not an error ────────────────────

output "distribution_id" {
  description = "CloudFront distribution id, or null when `enable_cloudfront = false`. The deploy's invalidation step is skipped on null rather than run against an empty string."
  value       = try(module.site[0].distribution_id, null)
}

output "distribution_arn" {
  description = <<-EOT
    The distribution's ARN — the value `module.api`'s `aws_lambda_permission` scopes the
    invoke grant to, so that the Function URL is reachable from this distribution and from
    nothing else on the internet. Null when `enable_cloudfront = false`, in which case
    there is no grant either: the Function URL is public by design.
  EOT
  value       = try(module.site[0].distribution_arn, null)
}

output "distribution_domain_name" {
  description = "The bare `dXXXXXXXX.cloudfront.net` hostname, without the scheme. Convenient for `curl -I`. Null when `enable_cloudfront = false`."
  value       = try(module.site[0].distribution_domain_name, null)
}

output "site_bucket" {
  description = <<-EOT
    The private S3 bucket the console build and the EvidenceBundle are synced into, or
    null when `enable_cloudfront = false` — in which case the console ships INSIDE the
    Lambda deployment package and there is no bucket in the request path at all.

    Teardown empties and deletes this bucket, and refuses to touch any bucket whose name
    does not start with `mainline-demo-`.
  EOT
  value       = try(module.site[0].bucket_name, null)
}

# ── Housekeeping ──────────────────────────────────────────────────────────────────────

output "dsn_parameter_name" {
  description = <<-EOT
    The NAME of the SSM SecureString the Lambda reads its DSN from — echoed back so the
    deploy script can assert that what it wrote in step 2 is what Terraform granted the
    function access to in step 6. The VALUE is not here and never will be.
  EOT
  value       = var.dsn_parameter_name
}

output "deploy_summary" {
  description = <<-EOT
    One object holding everything the deploy script needs after `terraform apply`, so it
    makes one `terraform output -json` call rather than fourteen. Reading fourteen separate
    outputs is fourteen chances to read thirteen of them.

    `phase` is a word rather than a boolean because it is what gets printed: `2-furl` is
    the D1 shipping shape (public Function URL owns the hostname), `2-cloudfront` is the
    same API behind a distribution, and `1-replay` is a distribution with no API at all.
  EOT
  value = {
    demo_url                = local.demo_url
    demo_url_source         = local.demo_url_source
    enable_cloudfront       = var.enable_cloudfront
    api_enabled             = var.enable_api
    api_function_name       = try(module.api[0].function_name, null)
    api_function_url        = try(module.api[0].function_url, null)
    api_function_url_domain = try(module.api[0].function_url_domain, null)
    api_authorization_type  = try(module.api[0].authorization_type, null)
    distribution_id         = try(module.site[0].distribution_id, null)
    site_bucket             = try(module.site[0].bucket_name, null)
    dsn_parameter_name      = var.dsn_parameter_name
    aws_region              = var.aws_region
    aws_account_id          = data.aws_caller_identity.current.account_id

    # ── THE GUARD, IN THE OBJECT THE DEPLOY SCRIPT ALREADY READS ──────────────────────
    #
    # Added rather than left to a separate `terraform output` call, because the deploy
    # report is where an operator learns what they just created and "there is now a
    # mechanism that can stop this URL without asking anybody" is the single most
    # surprising thing in this apply. Adding keys is safe for both consumers: `deploy.sh`
    # and `deploy.ps1` read named keys out of this object and ignore the rest.
    #
    # `guard_responder_function_name` is here specifically so that the first thing to run
    # after an unexplained 429 is in the same output as the URL that is 429ing:
    #   aws logs tail /aws/lambda/<guard_responder_function_name> --since 1h
    guard_enabled                 = var.enable_api
    guard_sns_topic_arn           = try(module.guard[0].sns_topic_arn, null)
    guard_responder_function_name = try(module.guard[0].responder_function_name, null)
    guard_budget_name             = try(module.guard[0].budget_name, null)
    api_alarm_actions_armed       = try(module.api[0].published_bounds.alarm_actions_armed, false)
    phase = (
      var.enable_cloudfront
      ? (var.enable_api ? "2-cloudfront" : "1-replay")
      : "2-furl"
    )
  }
}
