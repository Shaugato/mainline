# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
#
# Nothing here is sensitive, and nothing here is the DSN. The Function URL is useless to
# anyone who cannot sign for `lambda:InvokeFunctionUrl` as the one CloudFront distribution
# named in `aws_lambda_permission.cloudfront_invoke`, which is why it is emitted in the
# clear: publishing it lets W7's deploy report and W10's acceptance run assert against it.

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
    slash preserved. Requires SigV4 as `cloudfront.amazonaws.com`; a plain `curl` gets 403
    with an empty body, which is the intended and load-bearing behaviour.
  EOT
  value       = aws_lambda_function_url.this.function_url
}

output "function_url_domain" {
  description = <<-EOT
    Host only - `<id>.lambda-url.<region>.on.aws` - for W5's CloudFront origin
    `domain_name`, which rejects a scheme and a path. Derived from the URL rather than
    rebuilt from `url_id`, so the two can never disagree.
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

output "architecture" {
  description = "The architecture actually deployed. Asserted against the package manifest by a `lifecycle.precondition` on the function, and worth re-asserting in the deploy report."
  value       = var.architecture
}

output "package_sha256_base64" {
  description = "`source_code_hash` as deployed - base64 of the package's SHA-256. The build script prints the same digest in hex; `openssl base64 -d <<< <this> | xxd -p -c 32` converts between them."
  value       = aws_lambda_function.this.source_code_hash
}

output "alarm_names" {
  description = "The four alarm names, for `aws cloudwatch describe-alarms --alarm-names` in W10's health cron."
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
