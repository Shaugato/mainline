# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
#
# THE DEMO API: one Lambda, one Function URL that IS the demo hostname, one log group,
# four alarms.
#
# Under decision D1 (docs/leads/ship-final.md sec 1.4) this module provisions the WHOLE demo
# origin, not half of it: the console SPA, the signed evidence bundle and `/v1/*` all answer
# on one hostname, and that hostname is this function's own URL. Everything here lives in
# `ap-southeast-1`, beside the CockroachDB Cloud cluster: a Lambda-to-CRDB round trip
# in-region is single-digit milliseconds, the same call from ap-southeast-2 pays about
# 90 ms each way, and the gate surface makes six of them - which is 1.1 s of pure geography
# on the one screen the judges are looking at.
#
# Four decisions a reviewer should not have to guess the reason for:
#
#   1. THE FUNCTION URL'S AUTHORISATION TYPE IS A VARIABLE, AND ITS DEFAULT IS `NONE`.
#      This file used to hard-code `AWS_IAM` and state, here, that there was deliberately
#      no variable that could change it. That was the correct design for a stack with a
#      CloudFront distribution in front of it. THIS ACCOUNT CANNOT HAVE ONE:
#
#          Error: creating CloudFront Distribution: StatusCode: 403,
#          RequestID: 3e63e30d-8c5b-441b-a01b-b70085eba504, AccessDenied:
#          Your account must be verified before you can add new CloudFront resources.
#
#      recorded in docs/deploy/RUNBOOK.md:26 from a real `terraform apply`, and reproduced
#      from a bare `aws cloudfront create-distribution` with no Terraform involved. The
#      identity holds AdministratorAccess; this is an account-level verification hold that
#      only AWS Support can lift. With no distribution there is no principal to grant
#      `lambda:InvokeFunctionUrl` to, so an `AWS_IAM` Function URL is not a hardened demo -
#      it is a demo nobody, including the judges, can reach.
#
#      So `var.url_authorization_type` has two legal values and the default is `NONE`:
#
#        NONE     the Function URL is public and IS the demo hostname. No CloudFront
#                 resource of any shape appears in the plan - the invoke grant below is
#                 `count = 0`, not merely unused.
#        AWS_IAM  the pre-D1 shape. The URL answers 403 to an unsigned request and the one
#                 `lambda:InvokeFunctionUrl` grant below is created, scoped by SourceArn to
#                 a single distribution.
#
#      A public URL is a public gateway to a database and this module does not pretend
#      otherwise. What actually bounds it is written down rather than assumed:
#      `reserved_concurrent_executions` (default 20) is a hard cap that stops a bill rather
#      than reporting one; the handler's write surface is one transaction that ends in
#      ROLLBACK; the CockroachDB Basic cluster carries its own spend limit; and the
#      `-concurrency` alarm below is the tripwire. That is a smaller claim than "invocable
#      by one distribution and nothing else", and it is the true one for this account.
#
#   2. THE DSN IS NOT A RESOURCE HERE. Terraform is given the SSM parameter's NAME. A
#      Terraform-managed secret is a plaintext secret in the state file, and the state
#      bucket has a wider read audience than the parameter does. `scripts/deploy` writes
#      the SecureString with `aws ssm put-parameter` before the first apply.
#
#   3. THE LOG GROUP IS CREATED BEFORE THE FUNCTION. Lambda creates
#      `/aws/lambda/<name>` on first invocation if it does not exist, with NO expiry and
#      owned by nothing - it survives `terraform destroy` and accrues storage forever. The
#      function's `logging_config.log_group` references the managed group, so the ordering
#      is enforced by the dependency graph rather than by a comment.
#
#   4. THERE IS NO CLOUDWATCH SYNTHETICS CANARY. One canary at five-minute intervals is
#      8 640 runs a month at $0.0012 = $10.37 - thirty times the cost of the entire rest of
#      this stack. Health checking is a GitHub Actions cron against `/v1/health` -
#      `.github/workflows/demo-health.yml` - which costs nothing and whose failures are
#      visible in the repository the judges are already reading. It fails every hour today
#      and correctly so: there is no deployed demo yet, and it goes green on its own the
#      moment there is one.

data "aws_caller_identity" "current" {}

data "aws_partition" "current" {}

data "aws_region" "current" {}

locals {
  account_id = data.aws_caller_identity.current.account_id
  partition  = data.aws_partition.current.partition
  region     = data.aws_region.current.region

  # Set by the module, never by the caller. `var.tags` is merged UNDER these, so a caller
  # cannot retag this stack out from under the teardown script's `project=mainline` filter.
  tags = merge(var.tags, {
    project    = "mainline"
    component  = "demo-api"
    managed_by = "terraform"
  })

  log_group_name = "/aws/lambda/${var.function_name}"

  # An SSM parameter ARN is `...:parameter/<name-without-leading-slash>`. Both
  # `/mainline/demo/dsn` and `mainline/demo/dsn` name the same parameter, and the two spell
  # the same ARN, so the leading slash is normalised here rather than being made the
  # caller's problem.
  dsn_parameter_path = startswith(var.dsn_parameter_name, "/") ? var.dsn_parameter_name : "/${var.dsn_parameter_name}"
  dsn_parameter_arn  = "arn:${local.partition}:ssm:${local.region}:${local.account_id}:parameter${local.dsn_parameter_path}"

  # Empty `ssm_kms_key_arn` means the AWS-managed `aws/ssm` key, whose ARN cannot be
  # resolved before the first SecureString exists in the region (see variables.tf for the
  # measured `list-aliases` output). The grant is then scoped by CONDITION instead - see
  # `data.aws_iam_policy_document.dsn_access`.
  kms_decrypt_resources = var.ssm_kms_key_arn == "" ? ["*"] : [var.ssm_kms_key_arn]

  # THE ONE PLAN-TIME-KNOWN GATE. `count` may not depend on a value that is unknown until
  # apply, and `var.cloudfront_distribution_arn` IS unknown at plan time whenever the caller
  # wires it straight from the site module's output - which is exactly how
  # `infra/envs/demo/main.tf` wires it. `var.url_authorization_type` is a string variable and
  # is therefore constant by the time `count` is evaluated, in every configuration. The
  # non-empty ARN half of the condition is enforced by a `lifecycle.precondition` on the
  # grant instead; see the resource, and see README.md for the reproduction that settled it.
  create_cloudfront_invoke_grant = var.url_authorization_type == "AWS_IAM"

  environment = merge(var.extra_environment, {
    # Read by `mainline_demo_api.db`. The NAME of the SecureString; never its value.
    MAINLINE_DSN_PARAM = local.dsn_parameter_path

    # Declarative. The handler takes the database from the DSN; this states which database
    # the function is SUPPOSED to be pointed at, so `aws lambda get-function-configuration`
    # answers that question without anyone decrypting the DSN. `/v1/health` reports the
    # database it actually reached, and a disagreement between the two is a finding.
    #
    # (It shares the `MAINLINE_DEMO_` prefix that `scenario.from_env` scans, but `DATABASE`
    # is not one of the six identifiers that function reads, so there is no collision.)
    MAINLINE_DEMO_DATABASE = var.demo_database

    # THE SAME VALUE UNDER TWO NAMES, AND THAT IS NOT AN ACCIDENT.
    # `MAINLINE_SCENARIO_PERMIT_ID` is the name this module was specified to publish.
    # `MAINLINE_DEMO_PERMIT_ID` is the name `mainline_demo_api.scenario.from_env` actually
    # reads (`ENV_PREFIX = "MAINLINE_DEMO_"` + `"PERMIT_ID"`). Publishing only the first
    # would make the override look configured and behave inert, which is the worst of the
    # three possible states. The README records the discrepancy rather than hiding it.
    MAINLINE_SCENARIO_PERMIT_ID = var.scenario_permit_id
    MAINLINE_DEMO_PERMIT_ID     = var.scenario_permit_id

    # Published because it is the conventional name an operator looks for. What actually
    # filters records in the managed python3.13 runtime is `logging_config
    # .application_log_level` below, which is set from the same variable.
    LOG_LEVEL = var.log_level

    # WHERE THE SPA LIVES INSIDE THE PACKAGE. Under D1 this function serves the console and
    # the signed bundle as well as `/v1/*`, from one origin, because there is no CloudFront
    # distribution and no S3 bucket in the request path. `mainline_demo_api.app` reads this
    # to find the static tree; the build script places it at the package root, and Lambda
    # unpacks the package at `/var/task`, so `/var/task/web` is the default and the two
    # halves of that agreement are stated in one variable rather than in two comments.
    MAINLINE_WEB_ROOT = var.web_root
  })
}

# ── The log group, first ────────────────────────────────────────────────────────────

resource "aws_cloudwatch_log_group" "this" {
  name              = local.log_group_name
  retention_in_days = var.log_retention_days
  tags              = local.tags
}

# ── Execution role: the managed basics, plus exactly one parameter ──────────────────

data "aws_iam_policy_document" "assume_role" {
  statement {
    sid     = "LambdaAssume"
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "this" {
  name                 = "${var.function_name}-exec"
  description          = "Execution role for the MAINLINE demo API Lambda. Reads one SSM parameter and writes to one log group."
  assume_role_policy   = data.aws_iam_policy_document.assume_role.json
  max_session_duration = 3600
  tags                 = local.tags
}

# CreateLogGroup / CreateLogStream / PutLogEvents. This is AWS's own managed policy and it
# is wildcarded over log groups; that is the one wildcard in this role and it is not ours
# to narrow without also narrowing what Lambda's runtime is allowed to do at cold start.
resource "aws_iam_role_policy_attachment" "basic_execution" {
  role       = aws_iam_role.this.name
  policy_arn = "arn:${local.partition}:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

data "aws_iam_policy_document" "dsn_access" {
  statement {
    sid     = "ReadTheDemoDsnParameter"
    effect  = "Allow"
    actions = ["ssm:GetParameter"]

    # ONE ARN. Not `parameter/mainline/*`, not `parameter/*`. `db.py` calls
    # `GetParameter` and only `GetParameter`, so `GetParameters`, `GetParametersByPath`
    # and `DescribeParameters` are all absent as well.
    resources = [local.dsn_parameter_arn]
  }

  statement {
    sid     = "DecryptThatParameterAndNothingElse"
    effect  = "Allow"
    actions = ["kms:Decrypt"]

    resources = local.kms_decrypt_resources

    # The AWS-managed `aws/ssm` key protects EVERY SecureString in the account, so naming
    # that key as the resource would be a wider grant than what follows. `kms:ViaService`
    # restricts the grant to decrypts that SSM itself performs, in this region.
    condition {
      test     = "StringEquals"
      variable = "kms:ViaService"
      values   = ["ssm.${local.region}.amazonaws.com"]
    }

    # SSM sets `PARAMETER_ARN` as the encryption context on every SecureString. With this
    # condition the role can decrypt the ciphertext of exactly one parameter, whatever the
    # Resource element says.
    dynamic "condition" {
      for_each = var.restrict_kms_to_parameter ? [1] : []
      content {
        test     = "StringEquals"
        variable = "kms:EncryptionContext:PARAMETER_ARN"
        values   = [local.dsn_parameter_arn]
      }
    }
  }
}

resource "aws_iam_role_policy" "dsn_access" {
  name   = "${var.function_name}-dsn-read"
  role   = aws_iam_role.this.id
  policy = data.aws_iam_policy_document.dsn_access.json
}

# ── The function ────────────────────────────────────────────────────────────────────

resource "aws_lambda_function" "this" {
  function_name = var.function_name
  description   = "MAINLINE demo API: the gate, refusing and admitting, over CockroachDB Cloud in Singapore."
  role          = aws_iam_role.this.arn

  # `app.handler(event, context)` is the whole server. No FastAPI, no Mangum, no WSGI
  # adapter - a Lambda invocation is already a function call with a dict argument.
  handler       = "mainline_demo_api.app.handler"
  runtime       = "python3.13"
  architectures = [var.architecture]

  filename = var.package_path
  # The redeploy trigger. Computed from the package's BYTES, which is why the build script
  # goes to the trouble of fixing entry timestamps and order: a hash that moved because the
  # clock moved would show a Lambda update in every plan, and a plan whose noise is routine
  # is a plan nobody reads.
  source_code_hash = filebase64sha256(var.package_path)

  memory_size                    = var.memory_size
  timeout                        = var.timeout
  reserved_concurrent_executions = var.reserved_concurrent_executions

  environment {
    variables = local.environment
  }

  # JSON log format is what makes `application_log_level` available at all; with the text
  # format Lambda has no structured level to filter on. `log_group` is the managed group
  # above, so the "create the group before the function" ordering is a real edge in the
  # dependency graph and not a naming convention two resources happen to agree on.
  logging_config {
    log_format            = "JSON"
    application_log_level = var.log_level
    system_log_level      = "WARN"
    log_group             = aws_cloudwatch_log_group.this.name
  }

  tags = local.tags

  depends_on = [
    aws_cloudwatch_log_group.this,
    aws_iam_role_policy_attachment.basic_execution,
    aws_iam_role_policy.dsn_access,
  ]

  lifecycle {
    precondition {
      # The build script writes `<zip>.json` beside the artefact. An aarch64 package on an
      # x86_64 function imports psycopg and dies with an ELFCLASS error on the FIRST
      # invocation - Lambda accepts the deployment happily and fails at request time, which
      # is the worst moment to find out. `try` keeps the manifest optional for a caller
      # who builds the zip some other way.
      condition     = try(jsondecode(file("${var.package_path}.json")).architecture, var.architecture) == var.architecture
      error_message = "The package manifest beside ${var.package_path} was built for a different architecture than var.architecture (${var.architecture}). Rebuild with `scripts/deploy/build_lambda.sh --arch ${var.architecture}`; a mismatched package deploys cleanly and then fails every invocation with an ELFCLASS error."
    }

    precondition {
      condition     = try(jsondecode(file("${var.package_path}.json")).handler, "mainline_demo_api.app.handler") == "mainline_demo_api.app.handler"
      error_message = "The package manifest beside ${var.package_path} declares a handler other than mainline_demo_api.app.handler, which is what this function is configured to call."
    }
  }
}

# ── The Function URL: under D1 this IS the demo hostname ────────────────────────────

resource "aws_lambda_function_url" "this" {
  function_name = aws_lambda_function.this.function_name

  # `NONE` by default. See decision 1 at the top of this file for the 403 that forced it.
  # The variable admits exactly two values and refuses everything else at plan time, so
  # this cannot become a typo that silently deploys an unauthenticated URL somebody meant
  # to authenticate, or the reverse.
  authorization_type = var.url_authorization_type

  # THERE IS DELIBERATELY NO `cors` BLOCK.
  #
  # Under D1 the SPA and the API answer on ONE origin - `GET /` and `GET /v1/*` are the
  # same hostname, the same scheme and the same port - so every request the console makes
  # is same-origin and the browser never sends a `Origin` header the function would have to
  # answer. A `cors { allow_origins = ["*"] }` block would therefore change nothing about
  # whether the demo works, and would change one thing about what an attacker can do: it
  # turns "any page on the internet may make a no-credentials request to this URL and not
  # read the answer" into "any page on the internet may make one and read it". That is a
  # widening nobody needs and nobody audited, in exchange for zero function.
  #
  # If a future caller ever does serve the console from a second hostname, the repair is a
  # `cors` block naming THAT hostname, not `*`, and it belongs in the same commit as the
  # second hostname.

  # BUFFERED, not RESPONSE_STREAM: every response this API produces is a small JSON
  # envelope or a static asset out of the package, and streaming would only add a mode in
  # which a partial body reaches the console with a 200 already on it.
  invoke_mode = "BUFFERED"
}

# ── The CloudFront grant: created ONLY in the AWS_IAM shape ─────────────────────────
#
# `count = 0` and not "created but harmless". A `NONE` plan that still contained an
# `aws_lambda_permission` naming `cloudfront.amazonaws.com` would be a plan whose reader
# has to work out that the resource is inert, and a reviewer who has to work that out for
# one resource stops checking the next one.

resource "aws_lambda_permission" "cloudfront_invoke" {
  count = local.create_cloudfront_invoke_grant ? 1 : 0

  statement_id  = "AllowCloudFrontOacInvoke"
  action        = "lambda:InvokeFunctionUrl"
  function_name = aws_lambda_function.this.function_name
  principal     = "cloudfront.amazonaws.com"

  # Without SourceArn the grant reads "any CloudFront distribution in any account may
  # invoke this URL", which includes one an attacker creates in their own account and
  # points at our origin. With it, exactly one distribution can.
  source_arn = var.cloudfront_distribution_arn

  # Consistent with the variable rather than hard-coded, so the statement asserts the auth
  # type the URL actually carries. A grant whose `function_url_auth_type` disagrees with
  # the URL authorises nothing and reports no error.
  function_url_auth_type = var.url_authorization_type

  lifecycle {
    precondition {
      # The other half of "AWS_IAM **and** a non-empty distribution ARN". It is a
      # precondition and not a `count` conjunct because `count` may not depend on a value
      # that is unknown until apply, and this one is: `infra/envs/demo/main.tf` passes
      # `module.site.distribution_arn`, which does not exist until the distribution does.
      # Measured, this machine, Terraform v1.14.8 - the two-conjunct `count` fails with
      # `Error: Invalid count argument ... cannot be determined until apply`, while this
      # precondition plans cleanly and is checked at apply. The transcript is in README.md.
      condition     = var.cloudfront_distribution_arn != ""
      error_message = "url_authorization_type is \"AWS_IAM\", so this module creates a lambda:InvokeFunctionUrl grant - but cloudfront_distribution_arn is empty, and a grant to cloudfront.amazonaws.com with no SourceArn reads \"any CloudFront distribution in any account may invoke this URL\", including one an attacker creates. Pass the distribution ARN, or leave url_authorization_type at its default \"NONE\", in which case no grant is created at all."
    }
  }
}

# ── Observability: four alarms and a dashboard, all inside free tiers ───────────────

# CloudWatch's first ten alarms per account are free, and these are four of them. None has
# an action by default (see `var.alarm_actions`); they exist to be READ - by the console,
# by the dashboard, and by the hourly `demo-health` workflow, which calls `describe-alarms`.

resource "aws_cloudwatch_metric_alarm" "errors" {
  alarm_name = "${var.function_name}-errors"
  alarm_description = join(" ", [
    "Any handler error at all in a 5-minute window.",
    "The demo API is supposed to answer refusals with a 200 and a REFUSED verdict, and failures with a JSON problem document -",
    "so a Lambda `Errors` datapoint means the handler RAISED, which it is written never to do.",
  ])

  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  dimensions          = { FunctionName = aws_lambda_function.this.function_name }
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"

  # No invocations is not a failure; it is a demo nobody is looking at yet.
  treat_missing_data = "notBreaching"

  alarm_actions = var.alarm_actions
  ok_actions    = var.alarm_actions
  tags          = local.tags
}

resource "aws_cloudwatch_metric_alarm" "throttles" {
  alarm_name = "${var.function_name}-throttles"
  alarm_description = join(" ", [
    "The reserved-concurrency cap is refusing invocations.",
    "Either the demo is under more load than a judging session produces, or reserved_concurrent_executions is set too low.",
    "A throttled Function URL invocation reaches the caller as HTTP 429 with no body from the handler, so this is user-visible and undiagnosable from the browser.",
  ])

  namespace           = "AWS/Lambda"
  metric_name         = "Throttles"
  dimensions          = { FunctionName = aws_lambda_function.this.function_name }
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"

  alarm_actions = var.alarm_actions
  ok_actions    = var.alarm_actions
  tags          = local.tags
}

resource "aws_cloudwatch_metric_alarm" "duration_p99" {
  alarm_name = "${var.function_name}-duration-p99"
  alarm_description = join(" ", [
    "p99 duration is approaching the ${var.timeout}s function timeout.",
    "On this stack that almost always means the pgwire round trip to CockroachDB Cloud got slow, not that the handler did -",
    "`/v1/health` reports the connect time separately, which is the first thing to look at.",
  ])

  namespace   = "AWS/Lambda"
  metric_name = "Duration"
  dimensions  = { FunctionName = aws_lambda_function.this.function_name }

  # p99 rather than Average: the average of a demo that is idle most of the day is
  # dominated by whichever few requests happened, and hides exactly the tail this alarm is
  # about. `extended_statistic` is the field percentiles go in; `statistic` must be unset.
  extended_statistic  = "p99"
  period              = 300
  evaluation_periods  = 1
  threshold           = var.duration_p99_threshold_ms
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"

  alarm_actions = var.alarm_actions
  ok_actions    = var.alarm_actions
  tags          = local.tags

  lifecycle {
    precondition {
      # An alarm threshold at or above the timeout is an alarm that cannot fire: Lambda
      # kills the invocation at `timeout` and the Duration datapoint is capped there. Both
      # sides are plain variables, so this is checked at PLAN time and costs nothing.
      # It exists because the D1 timeout drop from 25 s to 15 s would otherwise have left
      # the default threshold of 20 000 ms sitting silently above a 15 000 ms ceiling.
      condition     = var.duration_p99_threshold_ms < var.timeout * 1000
      error_message = "duration_p99_threshold_ms (${var.duration_p99_threshold_ms} ms) is not below the function timeout (${var.timeout} s = ${var.timeout * 1000} ms). Lambda terminates the invocation at the timeout and the Duration datapoint is capped there, so this alarm could never breach - a control that looks present and is not. Lower duration_p99_threshold_ms, or raise timeout."
    }
  }
}

resource "aws_cloudwatch_metric_alarm" "concurrency" {
  alarm_name = "${var.function_name}-concurrency"
  alarm_description = join(" ", [
    "Abuse tripwire: more than ${var.concurrency_alarm_threshold} concurrent executions.",
    "A judging session is a handful of browsers making four requests each; this threshold is not reachable by legitimate use of the demo.",
    "NOTE: Lambda emits per-function ConcurrentExecutions dependably for functions that have reserved concurrency;",
    "with reserved_concurrent_executions = -1 this alarm can sit in INSUFFICIENT_DATA and prove nothing.",
  ])

  namespace           = "AWS/Lambda"
  metric_name         = "ConcurrentExecutions"
  dimensions          = { FunctionName = aws_lambda_function.this.function_name }
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 1
  threshold           = var.concurrency_alarm_threshold
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"

  alarm_actions = var.alarm_actions
  ok_actions    = var.alarm_actions
  tags          = local.tags
}

resource "aws_cloudwatch_dashboard" "this" {
  count = var.create_dashboard ? 1 : 0

  dashboard_name = var.function_name

  dashboard_body = jsonencode({
    widgets = [
      {
        type   = "text"
        x      = 0
        y      = 0
        width  = 24
        height = 3
        properties = {
          markdown = join("\n", [
            "# MAINLINE demo API - ${var.function_name}",
            "",
            "`${var.architecture}` / `python3.13` / ${var.memory_size} MB / ${var.timeout}s timeout, in `${local.region}`, beside the CockroachDB Cloud cluster.",
            (
              var.url_authorization_type == "NONE"
              ? "Function URL authorisation: **NONE** - this URL is the public demo hostname and serves the console, the bundle and `/v1/*` from one origin. The cost ceiling is `reserved_concurrent_executions = ${var.reserved_concurrent_executions}`, not authentication."
              : "Function URL authorisation: **AWS_IAM** - invocable only by the one CloudFront distribution named in the `lambda:InvokeFunctionUrl` grant."
            ),
            "Logs: `${local.log_group_name}` (${var.log_retention_days}-day retention).",
            "Health: `GET /v1/health`. There is no Synthetics canary - a five-minute canary costs $10.37/month, thirty times the rest of this stack.",
          ])
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 3
        width  = 12
        height = 6
        properties = {
          title   = "Invocations and errors (5 min sum)"
          region  = local.region
          view    = "timeSeries"
          stacked = false
          period  = 300
          stat    = "Sum"
          metrics = [
            ["AWS/Lambda", "Invocations", "FunctionName", var.function_name, { label = "invocations" }],
            ["AWS/Lambda", "Errors", "FunctionName", var.function_name, { label = "errors", color = "#d13212" }],
          ]
          yAxis = { left = { min = 0 } }
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 3
        width  = 12
        height = 6
        properties = {
          title   = "Duration p50 / p99 (ms)"
          region  = local.region
          view    = "timeSeries"
          stacked = false
          period  = 300
          metrics = [
            ["AWS/Lambda", "Duration", "FunctionName", var.function_name, { stat = "p50", label = "p50" }],
            ["AWS/Lambda", "Duration", "FunctionName", var.function_name, { stat = "p99", label = "p99", color = "#ff7f0e" }],
          ]
          yAxis = { left = { min = 0 } }
          annotations = {
            horizontal = [
              { label = "p99 alarm", value = var.duration_p99_threshold_ms, color = "#ff7f0e" },
              { label = "timeout", value = var.timeout * 1000, color = "#d13212" },
            ]
          }
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 9
        width  = 12
        height = 6
        properties = {
          title   = "Concurrency and throttles"
          region  = local.region
          view    = "timeSeries"
          stacked = false
          period  = 300
          metrics = [
            ["AWS/Lambda", "ConcurrentExecutions", "FunctionName", var.function_name, { stat = "Maximum", label = "concurrent (max)" }],
            ["AWS/Lambda", "Throttles", "FunctionName", var.function_name, { stat = "Sum", label = "throttles", color = "#d13212" }],
          ]
          yAxis = { left = { min = 0 } }
          annotations = {
            horizontal = [
              { label = "abuse tripwire", value = var.concurrency_alarm_threshold, color = "#d13212" },
            ]
          }
        }
      },
      {
        # An `alarm` widget rather than a `metric` widget carrying `annotations.alarms`:
        # the latter renders one alarm over one metric, and what an operator wants on this
        # dashboard is the state of all four at a glance.
        type   = "alarm"
        x      = 12
        y      = 9
        width  = 12
        height = 6
        properties = {
          title = "Alarm state"
          alarms = [
            aws_cloudwatch_metric_alarm.errors.arn,
            aws_cloudwatch_metric_alarm.throttles.arn,
            aws_cloudwatch_metric_alarm.duration_p99.arn,
            aws_cloudwatch_metric_alarm.concurrency.arn,
          ]
        }
      },
    ]
  })
}
