# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
#
# Nothing here is sensitive, and nothing here is the DSN.
#
# The Function URL used to be emitted in the clear on the grounds that it was useless to
# anyone who could not sign for `lambda:InvokeFunctionUrl`. Under decision D1 that
# justification is gone and the real one is simpler and larger: with
# `url_authorization_type = "NONE"` THIS URL IS THE DEMO, it goes in the submission form,
# and a hostname that has to be secret to be safe was never safe. What bounds it is the
# reserved-concurrency cap and the rolled-back transaction, both of which are unaffected by
# who knows the URL.
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
  description = "The four alarm names, for `aws cloudwatch describe-alarms --alarm-names` in the hourly `demo-health` workflow."
  value = [
    aws_cloudwatch_metric_alarm.errors.alarm_name,
    aws_cloudwatch_metric_alarm.throttles.alarm_name,
    aws_cloudwatch_metric_alarm.duration_p99.alarm_name,
    aws_cloudwatch_metric_alarm.concurrency.alarm_name,
  ]
}

output "dashboard_name" {
  description = "CloudWatch dashboard name, or null when `create_dashboard = false`."
  value       = var.create_dashboard ? aws_cloudwatch_dashboard.this[0].dashboard_name : null
}
