# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
#
# No output here carries an account id, a topic secret or a credential. The ARNs below do
# contain the account id by construction - that is what an ARN is - and they are outputs of
# a module the env root already holds, not something printed into a log or an evidence
# file. `scripts/deploy/kill_switch.sh` masks the account id when it prints one, and
# nothing in this module prints anything.

output "sns_topic_arn" {
  description = <<-EOT
    THE ONE OUTPUT W6 NEEDS. The guard topic. Publishing to it stops the demo function.

    ── READ THIS BEFORE WIRING IT INTO `var.alarm_actions` ─────────────────────────────

    THIS IS A STOP TOPIC, NOT A NOTIFICATION TOPIC. Everything subscribed to it triggers
    `PutFunctionConcurrency(<guarded function>, 0)`. `infra/modules/demo-api` has a single
    `var.alarm_actions` list that it wires into ALL FOUR of its alarms
    (`errors`, `throttles`, `duration_p99`, `concurrency`) AND into their `ok_actions`.
    Passing this ARN there means, in full:

        errors        > 0 in 5 min  -> ONE handler exception stops the demo
        throttles     > 0 in 5 min  -> one throttled invocation stops the demo
        duration_p99  over threshold-> one slow CockroachDB round trip stops the demo
        concurrency   over threshold-> stops the demo (this one is arguably right)
        AND every OK transition of all four fires the stop responder again

    The first three are not cost signals; they are health signals, and stopping the demo
    because one request raised is a self-inflicted outage in front of judges. The
    responder refuses an OK transition on its own, so the `ok_actions` half is inert - but
    it is inert because of a check in the responder rather than because the wiring was
    right, and that is not where a control belongs.

    THE THREE ALARMS IN THIS MODULE ALREADY POINT AT THIS TOPIC, unconditionally, with no
    `ok_actions`. They are the cost alarms. `demo-api`'s four are the health alarms, they
    exist to be READ, and if they are ever given an action it should be a different topic
    with a different subscriber.
  EOT
  value       = aws_sns_topic.guard.arn
}

output "sns_topic_name" {
  description = "The guard topic's name, for an operator running `aws sns list-subscriptions-by-topic` during an incident."
  value       = aws_sns_topic.guard.name
}

output "responder_function_name" {
  description = <<-EOT
    The responder function's name. Useful for `aws logs tail /aws/lambda/<name> --follow`
    after an incident: the responder logs one JSON line per decision - stopped, refused,
    ignored - and that line is the record of whether the stop actually fired.
  EOT
  value       = aws_lambda_function.responder.function_name
}

output "responder_function_arn" {
  description = "The responder function's ARN, as subscribed to the guard topic."
  value       = aws_lambda_function.responder.arn
}

output "responder_role_arn" {
  description = <<-EOT
    The responder's execution role. It holds exactly two things: AWS's
    `AWSLambdaBasicExecutionRole` for logs, and one inline policy allowing
    `lambda:PutFunctionConcurrency` on exactly `guarded_function_arn` - plus an explicit
    Deny on `lambda:DeleteFunctionConcurrency`, so the responder cannot undo its own stop
    even if its code is rewritten to try.
  EOT
  value       = aws_iam_role.responder.arn
}

output "guarded_function_arn" {
  description = <<-EOT
    The single function ARN this guard is scoped to, spelled exactly as it appears in the
    responder's IAM grant. Emitted so that a reviewer can compare it against
    `module.demo_api.function_arn` in the env root without opening the policy: if those two
    strings differ, the guard is armed at a function that does not exist and the stop is a
    403 nobody will see until the incident.
  EOT
  value       = local.guarded_function_arn
}

output "budget_name" {
  description = "The budget's name, for `aws budgets describe-budget --budget-name <name>`."
  value       = aws_budgets_budget.guard.name
}

output "alarm_names" {
  description = <<-EOT
    The three alarm names, in timescale order: 60 s, 3600 s, 300 s-ingestion.
    `aws cloudwatch describe-alarms --alarm-names $(...)` reads their state; expect
    INSUFFICIENT_DATA on a demo nobody has visited, which is the true state and the
    deliberate consequence of `treat_missing_data = "missing"`.
  EOT
  value = [
    aws_cloudwatch_metric_alarm.invocations_burst.alarm_name,
    aws_cloudwatch_metric_alarm.invocations_hourly.alarm_name,
    aws_cloudwatch_metric_alarm.log_ingestion.alarm_name,
  ]
}

output "alarm_arns" {
  description = "The three alarm ARNs, in the same order as `alarm_names`. These are the exact ARNs named in the topic policy's `aws:SourceArn` condition - a fourth alarm added elsewhere cannot publish a stop without being added there too."
  value = [
    aws_cloudwatch_metric_alarm.invocations_burst.arn,
    aws_cloudwatch_metric_alarm.invocations_hourly.arn,
    aws_cloudwatch_metric_alarm.log_ingestion.arn,
  ]
}

output "thresholds" {
  description = <<-EOT
    Every threshold this module enforces, and the reachability arithmetic behind it, in one
    object - so that `terraform output` answers "what is actually in force?" without anyone
    reading variables.tf or decoding a zip.

    `*_visible_ms` is the slowest flood each invocation alarm can see: at the account
    concurrency ceiling, a flood of invocations slower than that cannot put enough of them
    into the window to breach. That is the number an operator needs when an alarm did not
    fire and the bill still moved.
  EOT
  value = {
    invocations_burst_per_60s    = var.invocations_burst_threshold
    invocations_hourly_per_3600s = var.invocations_hourly_threshold
    log_incoming_bytes_per_300s  = var.log_incoming_bytes_threshold
    budget_limit_usd             = var.budget_limit_usd
    account_concurrency_ceiling  = var.account_concurrency_ceiling
    burst_visible_ms             = local.burst_visible_ms
    hourly_visible_ms            = local.hourly_visible_ms
    invocations_max_60s          = local.invocations_max_60s
    invocations_max_3600s        = local.invocations_max_3600s
    log_bytes_max_300s           = local.log_bytes_max_300s
    stop_action                  = "lambda:PutFunctionConcurrency(ReservedConcurrentExecutions=0)"
    restore_action               = "scripts/deploy/kill_switch.sh --restore  (DeleteFunctionConcurrency, NOT a put of -1)"
  }
}
