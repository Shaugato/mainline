# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
#
# ══════════════════════════════════════════════════════════════════════════════════════
#  cost-guard — the mechanism that can stop the demo function, and the proof it is wired
# ══════════════════════════════════════════════════════════════════════════════════════
#
# Before this module, NOTHING IN THIS REPOSITORY COULD STOP THE DEMO. The only bound in
# force was an AWS account concurrency quota of 10 that nobody chose and that AWS marks
# `Adjustable: true`.
#
# THE WORST CASE IS NOT USD 33,250 PER 30 DAYS. That figure, which this header carried
# until 2026-08-13, assumed a 100 ms invocation. `docs/deploy/LATENCY.md` measured the
# static beats a flood is made of at 5.66 ms and 14.11 ms, and because
# `rate = concurrency / duration` the assumption understated the bound about SEVENFOLD:
# `docs/leads/cost-finish-plan.md` §0.5 recomputes it at **USD 229,759 per 30 days** with
# the measured durations in it. That is a MODEL BOUND and not a forecast - it assumes AWS
# sustains 708 rps x 1.55 MB of egress from ten 512 MB execution environments, which nobody
# has observed - but it is the honest headline, and the correction runs in the direction
# that makes this module more necessary rather than less.
#
# `log_retention_days = 7` bounds log STORAGE and not ingestion;
# `timeout` and `memory_size` bound ONE invocation and not the RATE. Every existing
# control leaves the third factor of `rate x bytes x time-until-something-stops-it` at
# THIRTY DAYS. This module brings that factor to minutes.
#
# ──────────────────────────────────────────────────────────────────────────────────────
#  1 · THERE IS NO LAMBDA BUDGET ACTION. THIS IS THE FIRST THING TO KNOW.
# ──────────────────────────────────────────────────────────────────────────────────────
#
# A reader arriving here reasonably expects `aws_budgets_budget_action` - a budget that,
# on breach, does something. It exists, and it CANNOT STOP A LAMBDA. Its three action
# types are, exhaustively:
#
#   APPLY_IAM_POLICY     attaches an IAM policy to users/groups/roles. It can deny a
#                        PRINCIPAL. A Lambda Function URL with `authorization_type = NONE`
#                        is invoked by ANONYMOUS callers - there is no principal to deny.
#   APPLY_SCP_POLICY     a Service Control Policy, which requires AWS Organizations.
#                        THIS ACCOUNT IS NOT IN AN ORGANIZATION, so this action type is
#                        not available here at all.
#   RUN_SSM_DOCUMENTS    runs `AWS-StartEC2Instance` / `AWS-StopEC2Instance` /
#                        `AWS-StopRdsInstance`. EC2 and RDS. There is no Lambda document.
#
# None of the three stops a Lambda function. So the path is not native and this module
# builds it explicitly:
#
#       Budgets notification ──┐
#       Invocations / 60 s  ───┼──► ONE SNS topic ──► responder Lambda
#       Invocations / 3600 s ──┤                          │
#       Logs IncomingBytes  ───┘                          ▼
#                                     lambda:PutFunctionConcurrency(demo-api, 0)
#
# AND THE BUDGETS LEG IS A BACKSTOP, NOT A BOUND. AWS Budgets evaluates against Cost
# Explorer, which refreshes on an 8-24 hour lag. A budget cannot stop anything inside a
# day. The two `Invocations` alarms and the `IncomingBytes` alarm are what bound the bill;
# the budget catches what all three miss, and anything this project did not model at all.
# `docs/leads/cost-bound-plan.md` sec 0.3 is the three-timescale argument in full.
#
# ──────────────────────────────────────────────────────────────────────────────────────
#  2 · THE TRADE THIS MODULE MAKES, NAMED RATHER THAN FOOTNOTED
# ──────────────────────────────────────────────────────────────────────────────────────
#
# THIS CONVERTS A COST ATTACK INTO AN AVAILABILITY ATTACK.
#
# Anyone who can generate 3,001 invocations in a minute can stop the demo. The URL is
# `authorization_type = NONE` by the founder's explicit choice, so anyone at all can. The
# function then stays stopped - reserved concurrency 0, every caller gets HTTP 429 with no
# body - UNTIL A HUMAN RUNS:
#
#       scripts/deploy/kill_switch.sh --restore --expect-account <id> --yes
#
# That script already exists and this module does not reimplement it. Read its header
# before editing anything here: RESTORE IS `DeleteFunctionConcurrency`, NOT
# `PutFunctionConcurrency(-1)`. The `-1` is a TERRAFORM sentinel meaning "no reservation";
# the API's minimum is 0 and it rejects -1 outright. A responder that tried to restore by
# putting -1 would fail exactly when it was needed, which is why this responder is not
# allowed to try - see the explicit IAM Deny below.
#
# The trade is the right one. An availability outage is recoverable by one command; an
# unbounded bill is not recoverable at all. But it is a trade, it belongs in the residual
# column, and README.md puts it there.
#
# ──────────────────────────────────────────────────────────────────────────────────────
#  3 · NOTHING HERE IS BEHIND `count = 0`
# ──────────────────────────────────────────────────────────────────────────────────────
#
# The finding that produced this wave was that the bound was DOCUMENTED and NOT
# IMPLEMENTED. A default-off stop is a documented stop. So every resource in this file is
# created unconditionally - the topic, the responder, its role, its grant, the budget, and
# all three alarms. There is exactly one `for_each` in the file and it is over
# `var.notification_emails`, a list of human subscribers that defaults to empty and gates
# nothing in the stop path; and exactly one `dynamic` block, adding a SECOND cost filter
# to a budget that already has one.
#
# ──────────────────────────────────────────────────────────────────────────────────────
#  4 · THE RESIDUAL THIS MODULE CANNOT CLOSE, STATED BECAUSE IT IS REAL
# ──────────────────────────────────────────────────────────────────────────────────────
#
# THE RESPONDER COMPETES FOR THE SAME TEN CONCURRENT EXECUTIONS AS THE FLOOD.
#
# The account ceiling is 10 (measured). A positive reserved concurrency on the responder
# would guarantee it a slot and AWS REFUSES ONE: a reservation may not drop
# `UnreservedConcurrentExecutions` below the floor AWS keeps back, and with a total quota
# of 10 that floor is already violated. `scripts/deploy/kill_switch.sh` records the same
# constraint from the other direction - reserving ZERO is accepted precisely because it
# takes nothing from the pool.
#
# So under a flood saturating all 10, the responder's own invocation can be THROTTLED.
# What saves the stop is that SNS invokes Lambda ASYNCHRONOUSLY: the event enters Lambda's
# internal async queue, and throttled async invocations are retried with backoff until
# `maximum_event_age_in_seconds`, which defaults to 21,600 s (6 hours). The stop is
# therefore delayed, not lost. Measured detection-to-stop latency is not knowable without
# an apply and is not claimed.
#
# THE REPAIR, so nobody looks for a cleverer one: raise the account concurrency quota, at
# which point a positive reservation for the responder becomes possible and the tail
# disappears. That is a support-ticket quota change nobody has authorised, and it is out
# of this wave's scope. It is not a code change and there is no code change that
# substitutes for it.
#
# ──────────────────────────────────────────────────────────────────────────────────────
#  5 · AN UNTRIGGERED ACTION IS INDISTINGUISHABLE FROM NO ACTION
# ──────────────────────────────────────────────────────────────────────────────────────
#
# Nobody may `terraform apply` in this wave, and nobody may make a mutating AWS call -
# including `put-function-concurrency`, including "just to prove the responder works". So
# the proof that this mechanism fires is not an apply and is not a hope. It is
# `tests/deploy/test_cost_guard_responder.py`, which feeds the responder the REAL AWS
# Budgets SNS envelope and the REAL CloudWatch-alarm SNS envelope and proves through
# `botocore.stub.Stubber` that exactly ONE `PutFunctionConcurrency` call is made, with
# `ReservedConcurrentExecutions = 0`, against the function name taken from the responder's
# own environment - and NONE for a malformed message, a foreign topic, or an alarm going
# back to OK. That test carries its own falsification: it deletes the stop call from the
# source, re-executes the mutated module, and asserts the same envelope now makes no call.
# If the stop ever stops working, that test goes red without anyone touching AWS.

data "aws_caller_identity" "current" {}

data "aws_partition" "current" {}

data "aws_region" "current" {}

locals {
  account_id = data.aws_caller_identity.current.account_id
  partition  = data.aws_partition.current.partition
  region     = data.aws_region.current.region

  name_prefix    = var.name_prefix == "" ? "${var.guarded_function_name}-guard" : var.name_prefix
  log_group_name = var.guarded_log_group_name == "" ? "/aws/lambda/${var.guarded_function_name}" : var.guarded_log_group_name

  responder_name        = "${local.name_prefix}-responder"
  responder_source_file = var.responder_source_file == "" ? "${path.module}/../../../scripts/deploy/cost_guard_responder.py" : var.responder_source_file

  # THE ONE ARN THE RESPONDER MAY TOUCH. Unqualified - no `:*` version suffix, no alias,
  # no wildcard of any kind. `lambda:PutFunctionConcurrency` operates on the unqualified
  # function, so a qualified ARN here would grant nothing and the responder would fail
  # closed at the worst moment.
  guarded_function_arn = "arn:${local.partition}:lambda:${local.region}:${local.account_id}:function:${var.guarded_function_name}"

  # Set by the module, never by the caller - same rule as `infra/modules/demo-api`. A
  # caller who could overwrite `project` could retag this stack out from under
  # `scripts/deploy/teardown.sh` AND out from under this module's own budget filter.
  tags = merge(var.tags, {
    project    = "mainline"
    component  = "cost-guard"
    managed_by = "terraform"
  })

  # ── The reachability arithmetic, computed once so the alarm descriptions and the
  #    preconditions cannot disagree with each other ────────────────────────────────
  #
  #   invocations_max(W) = ceiling * W / d          d = fastest billed duration
  #   d_visible(T, W)    = ceiling * W / T          the slowest flood an alarm can see
  #
  # Both are in milliseconds internally to avoid a float division that reads as an
  # integer one.
  invocations_max_60s   = var.account_concurrency_ceiling * 60 * 1000 / var.fastest_invocation_ms
  invocations_max_3600s = var.account_concurrency_ceiling * 3600 * 1000 / var.fastest_invocation_ms
  invocations_max_300s  = var.account_concurrency_ceiling * 300 * 1000 / var.fastest_invocation_ms

  burst_visible_ms  = var.account_concurrency_ceiling * 60 * 1000 / var.invocations_burst_threshold
  hourly_visible_ms = var.account_concurrency_ceiling * 3600 * 1000 / var.invocations_hourly_threshold

  # The most bytes this log group can physically receive in 300 s: every invocation the
  # window can hold, each emitting the per-invocation ceiling.
  log_bytes_max_300s = local.invocations_max_300s * var.log_bytes_per_invocation_ceiling
}

# ══════════════════════════════════════════════════════════════════════════════════════
#  THE TOPIC — one, and everything publishes to it
# ══════════════════════════════════════════════════════════════════════════════════════
#
# ONE topic and not four, because four topics is four subscriptions, four policies and
# four chances for one of them to be the unwired one. Every publisher here means the same
# thing - "stop the demo" - so they share a topic and the responder does not need to know
# which one spoke.

resource "aws_sns_topic" "guard" {
  name         = local.name_prefix
  display_name = "MAINLINE demo cost guard"
  tags         = local.tags
}

# ── The topic policy ───────────────────────────────────────────────────────────────────
#
# THIS RESOURCE REPLACES SNS's DEFAULT TOPIC POLICY ENTIRELY, which is why the first
# statement below re-creates it. Omitting that statement would leave the account unable to
# manage its own topic - subscribe, set attributes, read them - and would break
# `scripts/deploy/aws_live_probe.py` reading it.
#
# WITHOUT THE OTHER TWO STATEMENTS THE BUDGET DOES NOT APPLY AT ALL. AWS Budgets validates
# SNS access during `CreateBudget` and returns "Unable to publish to the SNS topic" when
# the policy does not admit `budgets.amazonaws.com`. The budget below therefore carries an
# explicit `depends_on` for this resource: Terraform's graph would otherwise be free to
# create the budget first, and the apply would fail on a race that reproduces one time in
# three.
#
# THE SOURCE CONDITIONS ARE TRANSCRIBED FROM AWS'S DOCUMENTED EXAMPLES AND ARE NOT
# VERIFIED ON THIS ACCOUNT, because verifying them requires an apply and a real breach.
# They are the confused-deputy protection that stops a stranger who learns this topic's
# ARN from publishing to it and stopping the demo. Their failure mode is the dangerous
# direction - a condition on a key the service does not populate denies the publish, and a
# denied publish is a stop that silently never happens - so:
#
#   IF THE FIRST REAL BUDGET NOTIFICATION OR ALARM ACTION DOES NOT REACH THE RESPONDER,
#   THIS IS THE FIRST PLACE TO LOOK. The symptom is a topic with zero deliveries while the
#   alarm shows ALARM. The repair is to drop the `condition` block from the statement that
#   is failing, not to widen the principal.
#
# `budgets.amazonaws.com` gets `aws:SourceAccount` plus an `ArnLike` over
# `arn:<partition>:budgets::<account>:*` - AWS's own documented form, wildcarded over the
# budget name so that renaming the budget does not silently unwire it.
#
# `cloudwatch.amazonaws.com` gets an `ArnLike` over the THREE EXACT ALARM ARNs. Not
# `alarm:*`: this module knows its alarms' ARNs as resource attributes, so naming them
# exactly costs nothing and means a fourth alarm somebody adds later cannot publish a stop
# without being added here too. That is the "no wildcards" rule of this module's grant,
# applied to the resource policy as well as to the IAM one.

data "aws_iam_policy_document" "topic" {
  statement {
    sid    = "AccountOwnerManagesThisTopic"
    effect = "Allow"

    principals {
      type        = "AWS"
      identifiers = ["*"]
    }

    actions = [
      "SNS:GetTopicAttributes",
      "SNS:SetTopicAttributes",
      "SNS:AddPermission",
      "SNS:RemovePermission",
      "SNS:DeleteTopic",
      "SNS:Subscribe",
      "SNS:ListSubscriptionsByTopic",
      "SNS:Publish",
    ]

    resources = [aws_sns_topic.guard.arn]

    # `Principal: *` narrowed to this account by `AWS:SourceOwner`. This is SNS's own
    # default-policy idiom, reproduced rather than invented: the principal element is wide
    # and the condition is what scopes it.
    condition {
      test     = "StringEquals"
      variable = "AWS:SourceOwner"
      values   = [local.account_id]
    }
  }

  statement {
    sid    = "AwsBudgetsMayPublishAStop"
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["budgets.amazonaws.com"]
    }

    actions   = ["SNS:Publish"]
    resources = [aws_sns_topic.guard.arn]

    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [local.account_id]
    }

    condition {
      test     = "ArnLike"
      variable = "aws:SourceArn"
      values   = ["arn:${local.partition}:budgets::${local.account_id}:*"]
    }
  }

  statement {
    sid    = "TheseThreeAlarmsMayPublishAStop"
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["cloudwatch.amazonaws.com"]
    }

    actions   = ["SNS:Publish"]
    resources = [aws_sns_topic.guard.arn]

    condition {
      test     = "ArnLike"
      variable = "aws:SourceArn"
      values = [
        aws_cloudwatch_metric_alarm.invocations_burst.arn,
        aws_cloudwatch_metric_alarm.invocations_hourly.arn,
        aws_cloudwatch_metric_alarm.log_ingestion.arn,
      ]
    }
  }
}

resource "aws_sns_topic_policy" "guard" {
  arn    = aws_sns_topic.guard.arn
  policy = data.aws_iam_policy_document.topic.json
}

# ── Human subscribers ──────────────────────────────────────────────────────────────────
#
# The stop is automatic; the RESTORE is a human running `kill_switch.sh --restore`, so a
# human has to find out. This is the only `for_each` in the file and it defaults to empty.
#
# AN EMAIL SUBSCRIPTION IS `PendingConfirmation` UNTIL SOMEBODY CLICKS THE LINK. Terraform
# reports it created either way and AWS delivers nothing in the meantime. That is a
# control that looks present and is not, which is why this is opt-in and why the variable
# says so at length rather than defaulting to a plausible address.

resource "aws_sns_topic_subscription" "email" {
  for_each = toset(var.notification_emails)

  topic_arn = aws_sns_topic.guard.arn
  protocol  = "email"
  endpoint  = each.value
}

# ══════════════════════════════════════════════════════════════════════════════════════
#  THE RESPONDER — one function, one permission, one call
# ══════════════════════════════════════════════════════════════════════════════════════

data "archive_file" "responder" {
  type        = "zip"
  source_file = local.responder_source_file

  # INTO THE ROOT MODULE'S `.terraform/`, and both halves of that are deliberate.
  #
  # `path.root` rather than `path.module`: a build artefact belongs to the run, not to the
  # source tree, and a module that wrote a zip next to its own `.tf` files would put a
  # generated binary into a directory a reviewer reads.
  #
  # `.terraform/` rather than any new directory: the repository's `.gitignore` ignores
  # `.terraform/` and nothing else terraform-shaped. MEASURED - an earlier draft wrote to
  # `.terraform-build/`, which `git status` would have offered to commit. A generated zip
  # in the tracked tree is exactly the artefact `docs/HONESTY.md` exists to keep out of it.
  # The directory is guaranteed to exist, because `terraform init` creates it and no plan
  # runs without one.
  #
  # The entry name inside the zip is the source file's BASENAME, which is why the handler
  # below is `cost_guard_responder.handler`. Renaming the source file renames the module
  # and breaks that string.
  output_path = "${path.root}/.terraform/cost-guard-responder.zip"

  # PLATFORM-INDEPENDENT ENTRY MODE, AND WITHOUT IT THIS MODULE PLANS A REDEPLOY EVERY TIME
  # THE PLANNING MACHINE CHANGES. MEASURED 2026-08-13: on Windows the archiver takes the
  # entry mode from the source file's own stat, which reads back as 0o100666; on Linux the
  # same file is 0o100644. The mode is part of the zip's central directory, so the two
  # platforms produce different BYTES from identical source, therefore different
  # `output_base64sha256`, therefore an `aws_lambda_function` update in a plan that changed
  # no code. Pinning the mode makes the archive a function of the source bytes alone -
  # which is the same property `scripts/deploy/build_lambda.sh` goes to trouble to obtain
  # for the demo package, and versions.tf records the measurement that shows the timestamp
  # half of it is already free.
  output_file_mode = "0644"
}

# Created before the function, for the reason `infra/modules/demo-api` states about its
# own: Lambda creates `/aws/lambda/<name>` on first invocation if it does not exist, with
# NO expiry and owned by nothing - it then survives `terraform destroy` and accrues storage
# forever.
resource "aws_cloudwatch_log_group" "responder" {
  name              = "/aws/lambda/${local.responder_name}"
  retention_in_days = var.responder_log_retention_days
  tags              = local.tags
}

data "aws_iam_policy_document" "responder_assume" {
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

resource "aws_iam_role" "responder" {
  name                 = "${local.name_prefix}-responder-exec"
  description          = "Execution role for the MAINLINE cost-guard responder. Sets reserved concurrency to 0 on exactly one function and writes to one log group. It cannot undo itself."
  assume_role_policy   = data.aws_iam_policy_document.responder_assume.json
  max_session_duration = 3600
  tags                 = local.tags
}

# CreateLogGroup / CreateLogStream / PutLogEvents. AWS's own managed policy, wildcarded
# over log groups. It is the one wildcard attached to this role and it is not ours to
# narrow without also narrowing what the runtime may do at cold start - the identical
# judgement `infra/modules/demo-api` records for the same attachment.
resource "aws_iam_role_policy_attachment" "responder_basic" {
  role       = aws_iam_role.responder.name
  policy_arn = "arn:${local.partition}:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# ── The grant: ONE action, ONE resource, and one Deny that makes the trade structural ──

data "aws_iam_policy_document" "responder_stop" {
  statement {
    sid    = "StopExactlyOneFunction"
    effect = "Allow"

    # ONE ACTION. Not `lambda:*`, not `lambda:Put*`, not the read side either - the
    # responder never calls `GetFunctionConcurrency`, because `PutFunctionConcurrency(0)`
    # is idempotent at the API and a read-before-write would be a second call that can
    # fail and a second decision that can be wrong.
    actions = ["lambda:PutFunctionConcurrency"]

    # ONE RESOURCE, spelled out in `locals` above. No wildcard appears anywhere in it.
    resources = [local.guarded_function_arn]
  }

  statement {
    sid    = "AndItMayNeverUndoItself"
    effect = "Deny"

    # THE TRADE OF SECTION 2, ENFORCED BY IAM RATHER THAN BY GOOD BEHAVIOUR.
    #
    # The responder's code does not call `DeleteFunctionConcurrency` and its test asserts
    # the string does not appear in the source. Both of those are properties of code that
    # somebody could change. This Deny is a property of the ROLE: even a responder rewritten
    # to restore itself cannot, and an explicit Deny cannot be overridden by any Allow.
    #
    # This matters because "the function stays stopped until a human runs
    # kill_switch.sh --restore" is the sentence README.md's residual column rests on. A
    # responder that could restore could also be tricked into restoring, and a stop that
    # can be undone by the thing being stopped is not a stop.
    #
    # `resources = ["*"]` on a Deny is a WIDENING of the refusal, not of any permission.
    actions   = ["lambda:DeleteFunctionConcurrency"]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "responder_stop" {
  name   = "${local.name_prefix}-stop-one-function"
  role   = aws_iam_role.responder.id
  policy = data.aws_iam_policy_document.responder_stop.json
}

resource "aws_lambda_function" "responder" {
  function_name = local.responder_name
  description   = "MAINLINE cost guard: on any message from the guard topic, reserve 0 concurrent executions on ${var.guarded_function_name}. Restore is a human running scripts/deploy/kill_switch.sh --restore."
  role          = aws_iam_role.responder.arn

  # `<module>.<function>` where `<module>` is the zip entry name, which `archive_file`
  # takes from the source file's basename. Renaming `cost_guard_responder.py` therefore
  # breaks this handler string, and the README says so.
  handler       = "cost_guard_responder.handler"
  runtime       = "python3.13"
  architectures = [var.responder_architecture]

  filename         = data.archive_file.responder.output_path
  source_code_hash = data.archive_file.responder.output_base64sha256

  memory_size = var.responder_memory_size
  timeout     = var.responder_timeout

  # -1 MEANS NO RESERVATION, AND IT IS NOT A CHOICE - IT IS THE ONLY VALUE THIS ACCOUNT
  # ACCEPTS. A positive reservation may not drop `UnreservedConcurrentExecutions` below the
  # floor AWS keeps back, and with an account quota of 10 that floor is already violated,
  # so every positive value is refused at apply time. Section 4 of this header carries what
  # that costs: under a saturating flood the responder's own invocation can be throttled,
  # and SNS's asynchronous delivery plus Lambda's async retry queue is what saves the stop.
  reserved_concurrent_executions = -1

  environment {
    variables = {
      # THE FUNCTION THE RESPONDER STOPS. Read by `cost_guard_responder._config`, which
      # REFUSES rather than guessing when it is absent - so this variable and the IAM
      # resource above are two spellings of one fact, and a disagreement between them is a
      # 403 in the responder's log rather than a wrong function stopped.
      MAINLINE_GUARDED_FUNCTION_NAME = var.guarded_function_name

      # THE ONLY TOPIC THE RESPONDER OBEYS. Every SNS record whose `TopicArn` is not this
      # string is refused without a call. A Lambda can be subscribed to a second topic by
      # anyone with `sns:Subscribe`; this is what makes that subscription inert.
      MAINLINE_COST_GUARD_TOPIC_ARN = aws_sns_topic.guard.arn
    }
  }

  logging_config {
    log_format            = "JSON"
    application_log_level = var.responder_log_level
    system_log_level      = "WARN"
    log_group             = aws_cloudwatch_log_group.responder.name
  }

  tags = local.tags

  depends_on = [
    aws_cloudwatch_log_group.responder,
    aws_iam_role_policy_attachment.responder_basic,
    aws_iam_role_policy.responder_stop,
  ]
}

# SNS invokes the responder. `source_arn` pins it to THIS topic: without it the permission
# reads "any SNS topic in this account may invoke the stop", and creating a topic is not a
# privileged act.
resource "aws_lambda_permission" "sns_invoke" {
  statement_id  = "AllowGuardTopicInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.responder.function_name
  principal     = "sns.amazonaws.com"
  source_arn    = aws_sns_topic.guard.arn
}

# THE SUBSCRIPTION THAT MAKES THE WHOLE MODULE MORE THAN A DIAGRAM. Unconditional, no
# `count`, no `for_each`. `depends_on` the permission because SNS does not validate invoke
# rights at subscribe time - it discovers them at delivery time, which is during the
# incident.
resource "aws_sns_topic_subscription" "responder" {
  topic_arn = aws_sns_topic.guard.arn
  protocol  = "lambda"
  endpoint  = aws_lambda_function.responder.arn

  depends_on = [aws_lambda_permission.sns_invoke]
}

# ══════════════════════════════════════════════════════════════════════════════════════
#  THE BUDGET — the days timescale, and the one that is a backstop
# ══════════════════════════════════════════════════════════════════════════════════════

resource "aws_budgets_budget" "guard" {
  name         = local.name_prefix
  budget_type  = "COST"
  limit_amount = format("%.2f", var.budget_limit_usd)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  # Pinned rather than computed. See `var.budget_time_period_start`.
  time_period_start = var.budget_time_period_start

  # THE SCOPE. A service filter and not a tag filter, and `variables.tf` carries the
  # measurement that forced it: this account has ZERO active cost allocation tags, and an
  # inactive tag matches no cost records, so a `TagKeyValue` filter would produce a budget
  # that reports 0.00 USD forever.
  cost_filter {
    name   = "Service"
    values = var.budget_service_filter_values
  }

  # The tag filter, for the day after somebody activates the tag. AWS ANDs multiple cost
  # filters, so this narrows the service filter rather than widening it - and turning it on
  # against an inactive tag turns the budget OFF. `var.use_tag_cost_filter` says so.
  dynamic "cost_filter" {
    for_each = var.use_tag_cost_filter ? [1] : []
    content {
      name   = "TagKeyValue"
      values = ["user:${var.cost_allocation_tag_key}$${var.cost_allocation_tag_value}"]
    }
  }

  cost_types {
    # A FLOOD PAID FOR BY CREDITS IS STILL A FLOOD. With credits included, spend covered by
    # promotional credit reports as 0.00 and this budget never fires while the credit
    # balance drains - and the credit is real money the moment it runs out. Excluding
    # credits makes the budget evaluate the cost INCURRED, which is the number a bound
    # should be about. Same reasoning for refunds.
    include_credit = false
    include_refund = false

    # Everything else at AWS's defaults, written out rather than omitted so that a reader
    # can see what was chosen and what was merely accepted.
    include_discount           = true
    include_other_subscription = true
    include_recurring          = true
    include_subscription       = true
    include_support            = true
    include_tax                = true
    include_upfront            = true
    use_amortized              = false
    use_blended                = false
  }

  # ONE NOTIFICATION, AND IT IS `ACTUAL`.
  #
  # `FORECASTED` would fire earlier, and firing earlier is exactly wrong here: this
  # notification STOPS THE DEMO. Stopping a live demo in front of judges on a PREDICTION
  # that may not come true is a worse failure than a day of Cost Explorer lag. ACTUAL means
  # the money has been spent, which is a fact rather than a model.
  notification {
    comparison_operator       = "GREATER_THAN"
    threshold                 = 100
    threshold_type            = "PERCENTAGE"
    notification_type         = "ACTUAL"
    subscriber_sns_topic_arns = [aws_sns_topic.guard.arn]
  }

  tags = local.tags

  # NOT ORNAMENTAL. AWS Budgets validates SNS publish access during `CreateBudget` and
  # fails the apply with "Unable to publish to the SNS topic" if the topic policy is not in
  # place yet. Terraform's graph has no other edge that would order these two, because the
  # budget references the topic's ARN and not the policy.
  depends_on = [aws_sns_topic_policy.guard]

  lifecycle {
    precondition {
      # A budget whose filter admits nothing is a budget that reports 0.00 USD forever.
      # This cannot check that the STRINGS are valid Cost Explorer service names - no
      # Terraform data source enumerates them - but it can refuse the empty case, which is
      # the one that is checkable at plan time and costs no API call.
      condition     = length(var.budget_service_filter_values) > 0
      error_message = "budget_service_filter_values is empty, which would leave this budget's Service cost filter matching nothing at all - a budget that reports 0.00 USD forever and never notifies. Name at least one Cost Explorer SERVICE value; the defaults are \"AWS Lambda\", \"AWS Data Transfer\" and \"AmazonCloudWatch\"."
    }
  }
}

# ══════════════════════════════════════════════════════════════════════════════════════
#  THE THREE ALARMS — three timescales, one action
# ══════════════════════════════════════════════════════════════════════════════════════
#
# One tripwire is a tripwire an attacker walks under. These are three, each bounding what
# the faster one lets through, all publishing to the same topic:
#
#   minutes   Invocations Sum / 60 s     the flood
#   hours     Invocations Sum / 3600 s   the slow burn pacing under the burst line
#   ingestion Logs IncomingBytes / 300 s bytes decoupled from invocation count
#
# TWO RULES GOVERN ALL THREE, both inherited from `infra/modules/demo-api` and both
# load-bearing here:
#
#   (a) `treat_missing_data = "missing"`, NEVER `notBreaching`. GREEN MUST MEAN
#       MEASURED-AND-FINE AND NEVER NOT-MEASURED. Under `notBreaching` an idle demo
#       displays three green alarms and the one thing an operator reads off green - "I
#       looked, it is healthy" - is false: nobody called the function, so nothing was
#       measured. Under `missing` an unexercised demo reads INSUFFICIENT_DATA, which is the
#       true state. The price is that a demo nobody has visited does not show green. That
#       is not a price.
#
#   (b) ANY ALARM ON A METRIC WITH A KNOWN PHYSICAL CEILING CARRIES A PLAN-TIME
#       PRECONDITION PLACING ITS THRESHOLD STRICTLY BELOW THAT CEILING. A threshold at or
#       above a ceiling the metric cannot reach does not fire late - IT CANNOT FIRE. All
#       three below have such a ceiling, because the account concurrency quota caps how
#       many invocations a window can contain, and all three carry the precondition. Every
#       term is a plain variable, so each costs one plan evaluation and no API call.
#
# AND NONE OF THEM HAS `ok_actions`. An OK action on this topic would invoke the STOP
# responder on RECOVERY. The responder refuses an OK transition on its own - the test
# proves it makes no call for one - but the correct place to not do that is here, where the
# action is chosen, and the responder's refusal is the second belt rather than the first.

resource "aws_cloudwatch_metric_alarm" "invocations_burst" {
  alarm_name = "${var.guarded_function_name}-invocations-burst"
  alarm_description = join(" ", [
    "STOPS THE DEMO. More than ${var.invocations_burst_threshold} invocations of ${var.guarded_function_name} in a single 60-second window.",
    "A judging session is a handful of browsers making tens of requests each: the modelled worst minute is 552 invocations for a realistic 8-judge panel and 1,380 for a deliberately pessimistic 20-judge one, so this threshold carries 5.43x and 2.17x margin respectively.",
    "Breaching it publishes to ${aws_sns_topic.guard.arn}, which invokes ${local.responder_name}, which reserves 0 concurrent executions on this function - callers then receive HTTP 429 with no body until a human runs scripts/deploy/kill_switch.sh --restore.",
    "THIS ALARM CANNOT SEE a flood whose invocations bill slower than ${local.burst_visible_ms} ms, because at the account ceiling of ${var.account_concurrency_ceiling} such a flood cannot put ${var.invocations_burst_threshold} invocations into 60 seconds. The -invocations-hourly alarm is what catches those.",
  ])

  namespace           = "AWS/Lambda"
  metric_name         = "Invocations"
  dimensions          = { FunctionName = var.guarded_function_name }
  statistic           = "Sum"
  period              = 60
  evaluation_periods  = 1
  datapoints_to_alarm = 1
  threshold           = var.invocations_burst_threshold
  comparison_operator = "GreaterThanThreshold"

  # Rule (a). An idle demo has no invocation rate to be fine about.
  treat_missing_data = "missing"

  alarm_actions = [aws_sns_topic.guard.arn]
  tags          = local.tags

  lifecycle {
    precondition {
      # Rule (b). `Invocations` Sum over 60 s cannot exceed `ceiling * 60 / d`.
      condition     = var.invocations_burst_threshold < local.invocations_max_60s
      error_message = "invocations_burst_threshold (${var.invocations_burst_threshold}) is not below the most invocations a 60-second window can physically contain (${local.invocations_max_60s} = account_concurrency_ceiling ${var.account_concurrency_ceiling} x 60 s / fastest_invocation_ms ${var.fastest_invocation_ms} ms). Lambda throttles at the account quota, so no 60-second window can hold more than that and this alarm could never breach - a control that looks present and is not. Lower invocations_burst_threshold, or raise account_concurrency_ceiling to match a quota that was actually increased."
    }
  }
}

resource "aws_cloudwatch_metric_alarm" "invocations_hourly" {
  alarm_name = "${var.guarded_function_name}-invocations-hourly"
  alarm_description = join(" ", [
    "STOPS THE DEMO. More than ${var.invocations_hourly_threshold} invocations of ${var.guarded_function_name} in one hour - the slow burn that paces just under the 60-second line.",
    "${var.invocations_hourly_threshold}/h averages ${floor(var.invocations_hourly_threshold / 60)}/min, which is a small fraction of the burst threshold of ${var.invocations_burst_threshold}/min, and that gap is the alarm's entire job.",
    "Modelled judging hour: 2,568 invocations for a realistic 8-judge panel, 6,420 for a pessimistic 20-judge one - margins of 5.84x and 2.34x.",
    "THIS ALARM CANNOT SEE a flood whose invocations bill slower than ${local.hourly_visible_ms} ms. MEASURED, not hypothesised: a gate-run flood at the corrected in-region p50 of 1,392 ms reaches 25,855/h and IS caught; the same flood at the in-region p99 of 3,729 ms reaches only 9,654/h and is not, and a flood at the 14 s function timeout reaches 2,571/h and is not. That band is invisible to both invocation alarms and costs at most USD 4.61/day; the AWS Budgets leg is what bounds it, on an 8-24 h Cost Explorer lag.",
  ])

  namespace           = "AWS/Lambda"
  metric_name         = "Invocations"
  dimensions          = { FunctionName = var.guarded_function_name }
  statistic           = "Sum"
  period              = 3600
  evaluation_periods  = 1
  datapoints_to_alarm = 1
  threshold           = var.invocations_hourly_threshold
  comparison_operator = "GreaterThanThreshold"

  # Rule (a).
  treat_missing_data = "missing"

  alarm_actions = [aws_sns_topic.guard.arn]
  tags          = local.tags

  lifecycle {
    precondition {
      # Rule (b), over the 3600-second window.
      condition     = var.invocations_hourly_threshold < local.invocations_max_3600s
      error_message = "invocations_hourly_threshold (${var.invocations_hourly_threshold}) is not below the most invocations a 3600-second window can physically contain (${local.invocations_max_3600s} = account_concurrency_ceiling ${var.account_concurrency_ceiling} x 3600 s / fastest_invocation_ms ${var.fastest_invocation_ms} ms). This alarm could never breach. Lower invocations_hourly_threshold."
    }

    precondition {
      # THE THREE-TIMESCALE PROPERTY, CHECKED RATHER THAN ASSERTED. "Each one bounds what
      # the faster one lets through" is only true if the hourly threshold sits below what
      # the burst line permits over an hour. At or above `burst x 60` this alarm can only
      # breach on traffic that already breached the burst alarm sixty times over, which
      # means it adds no timescale at all - a second alarm that is a copy of the first,
      # which is the shape of a control that looks like two and is one.
      condition     = var.invocations_hourly_threshold < var.invocations_burst_threshold * 60
      error_message = "invocations_hourly_threshold (${var.invocations_hourly_threshold}) is not below what the burst line permits over one hour (invocations_burst_threshold ${var.invocations_burst_threshold} x 60 = ${var.invocations_burst_threshold * 60}). Above that, this alarm can only fire on traffic that already tripped the 60-second alarm, so it adds no second timescale and the slow-burn caller it exists to catch is not caught by anything. Lower invocations_hourly_threshold."
    }
  }
}

resource "aws_cloudwatch_metric_alarm" "log_ingestion" {
  alarm_name = "${var.guarded_function_name}-log-ingestion"
  # AWS CAPS alarm_description AT 1024 CHARACTERS and the provider refuses a longer one at
  # PLAN time - `terraform validate` does not catch it, because the limit is the provider's
  # and not the schema's. MEASURED 2026-08-13: an earlier revision of this description ran
  # to ~1,480 characters and `terraform plan` refused it. The full argument for this
  # threshold lives in variables.tf, which has no length limit; what survives here is what
  # an operator needs in the console at 3 a.m.
  alarm_description = join(" ", [
    "STOPS THE DEMO. More than ${var.log_incoming_bytes_threshold} bytes ingested into ${local.log_group_name} in a 5-minute window.",
    "THE ONLY BOUND ON LOG INGESTION IN THIS STACK: log_retention_days = 7 bounds STORAGE, and ingestion is billed on arrival.",
    "It uniquely catches bytes DECOUPLED from invocation count - a traceback storm, a debug level left on, a library logging per row - where neither invocation alarm moves.",
    "Modelled 5-minute window (corrected 2026-08-13 for a unit slip and a measured byte term): 214 x 956 B = 204,584 B realistic, margin 82.0x; 535 x 956 B = 511,460 B pessimistic, margin 32.8x. A WORKING handler emits ZERO bytes of its own, measured.",
    "False-positive floor - a pessimistic panel during a database outage, every invocation logging a full diagnostic - is 535 x 5,261 B = 2,814,635 B, cleared by 5.96x.",
    "NAMESPACE AWS/Logs, DIMENSION LogGroupName: a Logs metric, not a Lambda one, so it will not appear beside them in the console.",
  ])

  namespace           = "AWS/Logs"
  metric_name         = "IncomingBytes"
  dimensions          = { LogGroupName = local.log_group_name }
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  datapoints_to_alarm = 1
  threshold           = var.log_incoming_bytes_threshold
  comparison_operator = "GreaterThanThreshold"

  # Rule (a). A log group nothing has written to has no ingestion rate to be fine about,
  # and `notBreaching` here would be the worst of the three: it would report a bound on
  # ingestion as satisfied for a function that has never run.
  treat_missing_data = "missing"

  alarm_actions = [aws_sns_topic.guard.arn]
  tags          = local.tags

  lifecycle {
    precondition {
      # Rule (b), and the ceiling is a product rather than a quotient: the most invocations
      # a 300-second window can hold, each emitting the per-invocation log ceiling.
      condition     = var.log_incoming_bytes_threshold < local.log_bytes_max_300s
      error_message = "log_incoming_bytes_threshold (${var.log_incoming_bytes_threshold} B) is not below the most this log group can physically receive in 300 seconds (${local.log_bytes_max_300s} B = ${local.invocations_max_300s} invocations x log_bytes_per_invocation_ceiling ${var.log_bytes_per_invocation_ceiling} B). This alarm could never breach - a bound on ingestion that is not one. Lower log_incoming_bytes_threshold, or raise log_bytes_per_invocation_ceiling to match a per-invocation log budget that was actually widened."
    }
  }
}
