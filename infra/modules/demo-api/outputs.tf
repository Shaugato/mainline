# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
#
# Nothing here is sensitive, and nothing here is the DSN.
#
# The Function URL used to be emitted in the clear on the grounds that it was useless to
# anyone who could not sign for `lambda:InvokeFunctionUrl`. Under decision D1 that
# justification is gone and the real one is simpler and larger: with
# `url_authorization_type = "NONE"` THIS URL IS THE DEMO, it goes in the submission form,
# and a hostname that has to be secret to be safe was never safe.
#
# THIS HEADER USED TO ADD "what bounds it is the reserved-concurrency cap and the
# rolled-back transaction". Half of that was wrong: `reserved_concurrent_executions` is -1,
# and at 20 it never bound anything either - the account ceiling of 10 was already lower
# (`min(20, 10) = 10`), and this account refuses every positive reservation outright. What
# bounds the RATE is the account's measured concurrency ceiling and nothing else; the
# rolled-back transaction bounds database STATE, not spend. Both are indeed unaffected by
# who knows the URL, which is the only part of the original sentence that survives. See
# `docs/deploy/COST-BOUND.md`.
#
# `authorization_type` is echoed back so a caller does not have to infer which shape it
# got. `terraform output -raw authorization_type` is the assertion the deploy report and
# the acceptance run make before they trust `function_url`.

output "authorization_type" {
  description = <<-EOT
    The Function URL's authorisation type as actually configured, read back off the
    resource rather than off `var.url_authorization_type` - so it is the deployed truth and
    not a restatement of the request. `NONE` means `function_url` is publicly reachable and
    is the demo hostname; `AWS_IAM` means an unsigned request gets 403 and only the
    CloudFront distribution named in the invoke grant can reach it.
  EOT
  value       = aws_lambda_function_url.this.authorization_type
}

output "cloudfront_invoke_grant_created" {
  description = <<-EOT
    Whether this module created the `lambda:InvokeFunctionUrl` grant for
    `cloudfront.amazonaws.com`. `false` in the D1 default shape, where the resource is
    `count = 0` and absent from the plan entirely rather than present and inert - which is
    the property a reviewer wants to assert mechanically instead of by reading the plan.
  EOT
  value       = length(aws_lambda_permission.cloudfront_invoke) > 0
}

output "function_name" {
  description = "The deployed function's name. `aws lambda get-function-configuration --function-name` takes it verbatim."
  value       = aws_lambda_function.this.function_name
}

output "function_arn" {
  description = "The function ARN. Unqualified (no version suffix), which is what the Function URL and the CloudFront permission are both attached to."
  value       = aws_lambda_function.this.arn
}

output "function_url" {
  description = <<-EOT
    The full Function URL, `https://<id>.lambda-url.<region>.on.aws/`, with AWS's trailing
    slash preserved.

    WHEN `authorization_type` IS `NONE` - the default, and the shape decision D1 selects
    because AWS will not create a CloudFront distribution on this account - THIS IS THE
    DEMO URL. It is the value that goes in `docs/submission/SUBMISSION.json.demo_url` and
    in the submission form's demo field: HTTPS on an AWS-issued certificate, free and
    unrestricted, serving the console SPA at `/`, the signed evidence bundle at `/bundle/*`
    and the API at `/v1/*` from one origin.

    When it is `AWS_IAM` this is an origin, not a destination: a plain `curl` gets 403 with
    an empty body, and the hostname a judge visits is the CloudFront distribution's.
  EOT
  value       = aws_lambda_function_url.this.function_url
}

output "function_url_domain" {
  description = <<-EOT
    Host only - `<id>.lambda-url.<region>.on.aws` - for the `demo-site` module's CloudFront
    origin `domain_name`, which rejects a scheme and a path. Derived from the URL rather
    than rebuilt from `url_id`, so the two can never disagree. Only meaningful in the
    `AWS_IAM` shape; emitted unconditionally so the env root can reference it with a static
    expression instead of a splat (see infra/envs/demo/main.tf on why a splat is a cycle).
  EOT
  value       = replace(trimsuffix(aws_lambda_function_url.this.function_url, "/"), "https://", "")
}

output "function_url_id" {
  description = "The Function URL's opaque id, the leftmost label of `function_url_domain`. Useful in a CloudFront origin id, and in a log filter."
  value       = aws_lambda_function_url.this.url_id
}

output "log_group_name" {
  description = "`/aws/lambda/<function>`, created by this module with a finite retention so Lambda never makes an unmanaged, never-expiring one. `aws logs tail <this>` is the demo's debugger."
  value       = aws_cloudwatch_log_group.this.name
}

output "log_group_arn" {
  description = "ARN of the log group, for a subscription filter or a cross-account reader that does not exist yet."
  value       = aws_cloudwatch_log_group.this.arn
}

output "role_arn" {
  description = "Execution role ARN. Its whole non-managed grant is `ssm:GetParameter` on one parameter plus a conditioned `kms:Decrypt`; `aws iam get-role-policy --role-name <name> --policy-name <function>-dsn-read` prints it."
  value       = aws_iam_role.this.arn
}

output "role_name" {
  description = "Execution role name, for `aws iam get-role-policy`."
  value       = aws_iam_role.this.name
}

output "dsn_parameter_arn" {
  description = <<-EOT
    The ONE SSM parameter ARN this function may read. Emitted so the deploy script can
    write the SecureString to exactly the ARN the policy grants, instead of to a name that
    looks the same and normalises differently. The VALUE is never in Terraform.
  EOT
  value       = local.dsn_parameter_arn
}

output "web_root" {
  description = <<-EOT
    The path the function will look for the console SPA at, as published in
    `$MAINLINE_WEB_ROOT`. Emitted so the deploy script can assert that the zip it just
    uploaded actually contains that directory - `unzip -l <pkg> | grep '^ *[0-9].* web/'` -
    rather than discovering at judging time that `/` 404s while `/v1/health` is green.
  EOT
  value       = var.web_root
}

output "architecture" {
  description = "The architecture actually deployed. Asserted against the package manifest by a `lifecycle.precondition` on the function, and worth re-asserting in the deploy report."
  value       = var.architecture
}

output "package_sha256_base64" {
  description = "`source_code_hash` as deployed - base64 of the package's SHA-256. The build script prints the same digest in hex; `openssl base64 -d <<< <this> | xxd -p -c 32` converts between them."
  value       = aws_lambda_function.this.source_code_hash
}

output "alarm_names" {
  description = <<-EOT
    The four alarm names, for `aws cloudwatch describe-alarms --alarm-names <these>`.

    THIS DESCRIPTION USED TO SAY "in the hourly `demo-health` workflow". IT DOES NOT RUN
    THERE. `.github/workflows/demo-health.yml` makes outbound HTTP requests against
    `/v1/health` and declares `permissions: contents: read`; it has no `cloudwatch` call
    and no credential, and NO workflow in this repository has an AWS credential to read
    with (the only `AWS_*` mention in `.github/workflows` is an `env -u` in
    `aws-evidence.yml` that unsets them all, deliberately). The reader is a workstation
    that HAS a credential - `scripts/deploy/aws_live_probe.py` - plus the console and the
    dashboard's alarm widget. See the observability header in main.tf.

    All four now use `treat_missing_data = "missing"`, so `describe-alarms` answers
    INSUFFICIENT_DATA on an unexercised demo rather than OK. That is the point: a caller
    asserting on this output must treat OK as "measured and fine" and must NOT treat
    INSUFFICIENT_DATA as a pass.
  EOT
  value = [
    aws_cloudwatch_metric_alarm.errors.alarm_name,
    aws_cloudwatch_metric_alarm.throttles.alarm_name,
    aws_cloudwatch_metric_alarm.duration_p99.alarm_name,
    aws_cloudwatch_metric_alarm.concurrency.alarm_name,
  ]
}

output "alarm_arns" {
  description = <<-EOT
    The four alarm ARNs, in the same order as `alarm_names`.

    IT EXISTS TO BE COMPARED AGAINST ONE OTHER LIST. `infra/modules/cost-guard`'s SNS topic
    policy admits `cloudwatch.amazonaws.com` under an `ArnLike` on `aws:SourceArn` naming
    exactly ITS OWN three alarm ARNs (`cost-guard/outputs.tf`, `alarm_arns`). None of these
    four is in that list, and `infra/envs/demo` nonetheless passes that topic as
    `var.alarm_actions` here. Whether these four can publish to it therefore depends on the
    policy's first statement - SNS's default `Principal AWS:*` scoped by `AWS:SourceOwner` -
    and NOTHING SHORT OF AN APPLY AND A REAL BREACH SETTLES IT. Emitting both lists as
    outputs makes the comparison one command instead of two policy documents:

        aws cloudwatch describe-alarms --alarm-names $(terraform output -json api_alarm_names)
        aws sns get-topic-attributes --topic-arn $(terraform output -raw guard_sns_topic_arn)

    A topic policy that does not admit an alarm turns that alarm's action into a denied
    publish, which `describe-alarms` cannot distinguish from a delivered one.
  EOT
  value = [
    aws_cloudwatch_metric_alarm.errors.arn,
    aws_cloudwatch_metric_alarm.throttles.arn,
    aws_cloudwatch_metric_alarm.duration_p99.arn,
    aws_cloudwatch_metric_alarm.concurrency.arn,
  ]
}

output "published_bounds" {
  description = <<-EOT
    EVERY BOUND THIS FUNCTION ENFORCES, AS ONE OBJECT, so that "what is actually in force?"
    is one `terraform output` and not an unzip of a 7.6 MB package.

    All six `MAINLINE_*` values are also environment variables on the function itself, which
    is the readable-from-AWS half of the same claim - `aws lambda
    get-function-configuration --function-name <name> --query Environment.Variables`. This
    output is the readable-from-Terraform half, and it carries the two numbers that are NOT
    environment variables because they are AWS-side configuration rather than application
    configuration: the timeout and the memory size.

    EVERY FIELD HERE IS KNOWN AT PLAN TIME, DELIBERATELY, and that is why
    `alarm_actions_armed` is a SEPARATE output rather than a field in this object. It is
    derived from `length(var.alarm_actions)`, the env root reaches that list through a
    `try()` over a counted module, and `try()` returns a wholly UNKNOWN value when its
    argument contains one - so a single boolean would have rendered this entire object as
    "(known after apply)" in the committed plan. The whole point of the object is that a
    reviewer can read the bounds in force off the plan artefact without an apply and
    without decoding a zip; one unknown field would have taken that away for all seventeen.
  EOT
  value = {
    max_response_bytes                    = var.max_response_bytes
    rate_global_rps                       = var.rate_global_rps
    rate_global_burst                     = var.rate_global_burst
    rate_ip_rps                           = var.rate_ip_rps
    rate_ip_burst                         = var.rate_ip_burst
    log_budget_bytes                      = var.log_budget_bytes
    timeout_seconds                       = var.timeout
    memory_size_mb                        = var.memory_size
    application_log_level                 = var.log_level
    system_log_level                      = "WARN"
    duration_p99_threshold_ms             = var.duration_p99_threshold_ms
    modelled_worst_legitimate_duration_ms = var.modelled_worst_legitimate_duration_ms
    concurrency_alarm_threshold           = var.concurrency_alarm_threshold
    account_concurrency_ceiling           = var.account_concurrency_ceiling
    reserved_concurrent_executions        = var.reserved_concurrent_executions
  }
}

output "alarm_actions_armed" {
  description = <<-EOT
    Whether the four alarms have any ALARM action at all. `false` means they report and
    nothing else; `true` means a breach of any one of them publishes to whatever is in
    `var.alarm_actions` - and in `infra/envs/demo` that is the cost guard's STOP topic, so
    `true` there means a breach takes the demo down until a human runs
    `scripts/deploy/kill_switch.sh --restore`.

    IT IS "(known after apply)" IN THE PLAN AND THAT IS NOT AVOIDABLE. The env root reaches
    the topic through `try([module.guard[0].sns_topic_arn], [])`, and `try()` yields an
    unknown value whenever its argument contains one - so the list's LENGTH is unknown at
    plan time even though its shape is not. What IS provable from the plan artefact is the
    wiring itself, in the `configuration` section rather than in `planned_values`:
    `module_calls.api.expressions.alarm_actions.references` reads
    `["local.guard_stop_topic_actions"]`, and the four alarms' `alarm_actions` sit in
    `after_unknown` while their `ok_actions` do not - which is exactly the signature of one
    list wired to a resource that does not exist yet and one list that is empty.
    `evidence/deploy/cost/plan-shape.json` records both facts.
  EOT
  value       = length(var.alarm_actions) > 0
}

output "ok_actions_armed" {
  description = <<-EOT
    Whether the four alarms notify anything on RECOVERY. `false`, and it is a different
    list from `alarm_actions` since this wave precisely so that arming one does not arm the
    other: an OK transition reaching a topic whose only verb is "stop" would fire the stop
    responder on the demo getting BETTER. See `var.ok_actions`.
  EOT
  value       = length(var.ok_actions) > 0
}

output "dashboard_name" {
  description = "CloudWatch dashboard name, or null when `create_dashboard = false`."
  value       = var.create_dashboard ? aws_cloudwatch_dashboard.this[0].dashboard_name : null
}
