# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
#
# These outputs are a machine interface before they are a human one.
# `scripts/deploy/deploy.sh` and `deploy.ps1` read them with `terraform output -json` and
# feed them to `aws s3 sync`, `aws cloudfront create-invalidation` and
# `scripts/deploy/demo_acceptance.py`. `scripts/deploy/teardown.sh` reads them to know
# what to delete. Renaming one breaks both scripts, so each name is load-bearing.
#
# NOTHING HERE IS SENSITIVE. There is no DSN, no password and no credential in this file,
# and there cannot be, because Terraform never held one.

output "demo_url" {
  description = <<-EOT
    THE DELIVERABLE. The URL that goes in the submission form.

    HTTPS on CloudFront's own certificate, no custom domain, no ACM, no Route 53. This is
    the string `scripts/deploy/demo_acceptance.py` is pointed at, and a deploy whose
    acceptance run does not exit 0 against this URL is a failed deploy.
  EOT
  value       = "https://${module.site.distribution_domain_name}"
}

output "distribution_id" {
  description = "CloudFront distribution id. Step 7 of the deploy invalidates /index.html and / against it."
  value       = module.site.distribution_id
}

output "distribution_arn" {
  description = <<-EOT
    The distribution's ARN — the value `module.api`'s `aws_lambda_permission` scopes the
    invoke grant to, so that the Function URL is reachable from this distribution and
    from nothing else on the internet.
  EOT
  value       = module.site.distribution_arn
}

output "distribution_domain_name" {
  description = "The bare hostname, without the scheme. Convenient for `curl -I`."
  value       = module.site.distribution_domain_name
}

output "site_bucket" {
  description = <<-EOT
    The private S3 bucket the console build and the EvidenceBundle are synced into.

    Teardown empties and deletes this bucket, and refuses to touch any bucket whose name
    does not start with `mainline-demo-`.
  EOT
  value       = module.site.bucket_name
}

output "api_enabled" {
  description = "false is the Phase-1 cut line: a working URL with no Lambda behind it."
  value       = var.enable_api
}

output "api_function_name" {
  description = "Lambda function name, or null in Phase 1. `aws logs tail /aws/lambda/<this>` is the first thing to run when /v1/health is unhappy."
  value       = one(module.api[*].function_name)
}

output "api_function_url_domain" {
  description = "The Function URL host CloudFront forwards /v1/* to, or null in Phase 1. Not directly invocable — the URL is AWS_IAM-authenticated."
  value       = one(module.api[*].function_url_domain)
}

output "dsn_parameter_name" {
  description = <<-EOT
    The NAME of the SSM SecureString the Lambda reads its DSN from — echoed back so the
    deploy script can assert that what it wrote in step 2 is what Terraform granted the
    function access to in step 6. The VALUE is not here and never will be.
  EOT
  value       = var.dsn_parameter_name
}

output "aws_region" {
  description = "Region every resource above was created in. Teardown asserts against it before deleting anything."
  value       = var.aws_region
}

output "aws_account_id" {
  description = "The account this actually applied into. 022950218246 is the expected value; the deploy script refuses any other unless --any-account is passed."
  value       = data.aws_caller_identity.current.account_id
}

output "deploy_summary" {
  description = <<-EOT
    One object holding everything the deploy script needs after `terraform apply`, so it
    makes one `terraform output -json` call rather than nine. Reading nine separate
    outputs is nine chances to read eight of them.
  EOT
  value = {
    demo_url                = "https://${module.site.distribution_domain_name}"
    distribution_id         = module.site.distribution_id
    site_bucket             = module.site.bucket_name
    api_enabled             = var.enable_api
    api_function_name       = one(module.api[*].function_name)
    api_function_url_domain = one(module.api[*].function_url_domain)
    dsn_parameter_name      = var.dsn_parameter_name
    aws_region              = var.aws_region
    aws_account_id          = data.aws_caller_identity.current.account_id
    phase                   = var.enable_api ? "2-live" : "1-replay"
  }
}
