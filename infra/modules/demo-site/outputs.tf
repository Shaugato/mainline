# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
#
# These outputs exist so that the deploy script, the teardown script and the judge pack can
# each do their job without hard-coding a name that only Terraform knows.
#
# NONE OF THEM IS READABLE WHEN THE MODULE IS ABSENT, AND ABSENT IS THE DEFAULT.
# `infra/envs/demo` instantiates this module with `count = var.enable_cloudfront ? 1 : 0`
# and that variable defaults to `false` (AWS refuses to create a distribution on this
# account — see main.tf's header for the 403 and its RequestID). A caller therefore reaches
# every value below as `try(module.site[0].<name>, null)`: on a zero-count module
# `module.site[0]` is an INVALID INDEX rather than a null, and a splat would depend on the
# module's close node and rebuild the dependency cycle `infra/envs/demo/main.tf` documents.

output "demo_url" {
  description = <<-EOT
    `https://` + the distribution's domain name, with no trailing slash.

    THIS IS NO LONGER THE SUBMISSION'S DEMO URL BY DEFAULT. Under decision D1
    (`docs/leads/ship-final.md` §1.4) the hostname belongs to the Lambda Function URL in
    `../demo-api`, because AWS will not create a CloudFront distribution on this account.
    This value is the URL only when the caller sets `enable_cloudfront = true`, in which
    case `infra/envs/demo`'s own `demo_url` output switches to it and says so in
    `demo_url_source`.

    It is stable for the life of the distribution: adding the API origin later is an
    in-place update, not a replacement.
  EOT
  value       = "https://${aws_cloudfront_distribution.site.domain_name}"
}

output "domain_name" {
  description = "The distribution's `dXXXXXXXX.cloudfront.net` hostname, without a scheme. Use `demo_url` for anything a human will click."
  value       = aws_cloudfront_distribution.site.domain_name
}

output "distribution_domain_name" {
  description = "Identical to `domain_name`, under the name `infra/envs/demo` reads. Both spellings are kept because the root builds its own `demo_url` from this one and renaming an output is how a deploy that worked yesterday stops resolving today."
  value       = aws_cloudfront_distribution.site.domain_name
}

output "distribution_id" {
  description = "CloudFront distribution id, e.g. `E1ABCDEFGHIJKL`. The deploy script passes it to `aws cloudfront create-invalidation`; see `invalidation_command`."
  value       = aws_cloudfront_distribution.site.id
}

output "distribution_arn" {
  description = "ARN of the distribution. This is the value the bucket policy pins with `AWS:SourceArn`, and it is the value the Lambda's resource policy must pin for the same reason — pass it to the API module so the Function URL can be reached by THIS distribution and by nothing else."
  value       = aws_cloudfront_distribution.site.arn
}

output "distribution_hosted_zone_id" {
  description = "CloudFront's global hosted-zone id (`Z2FDTNDATAQYW2`). Unused by this stack, which has no custom domain, and emitted so that adding one later is a Route 53 alias record rather than a re-read of the module."
  value       = aws_cloudfront_distribution.site.hosted_zone_id
}

output "bucket_name" {
  description = <<-EOT
    Name of the private site bucket. `aws s3 sync <dist>/ s3://<this>/ --delete` is the
    deploy's upload step; the name always carries the caller's prefix, which is what the
    teardown script checks before it deletes anything.

    Read off `.bucket` and not `.id`. They hold the same string, but `.id` is provider-
    computed and therefore "(known after apply)" — so an output built on it cannot be read
    off a plan, and a deploy script could not know where it was about to upload until after
    the apply. `.bucket` is the configured value and is known at plan time.
  EOT
  value       = aws_s3_bucket.site.bucket
}

output "bucket_arn" {
  description = "ARN of the site bucket. Grant it to whatever role runs the upload; the bucket policy in this module grants read to CloudFront only and says nothing about who may write."
  value       = aws_s3_bucket.site.arn
}

output "bucket_regional_domain_name" {
  description = "The bucket's regional domain name, which is what the distribution uses as its S3 origin. Emitted for debugging a 403 from the origin: if this is not the `origin.domain_name` in `aws cloudfront get-distribution-config`, the OAC is signing for a different bucket than the one the policy grants."
  value       = aws_s3_bucket.site.bucket_regional_domain_name
}

output "api_origin_enabled" {
  description = "`false` when the distribution was built with `api_origin_domain = null` — a Phase-1, static-only site with no `/v1/*` behaviour. The console reads the same fact at runtime to decide whether it may show the LIVE badge; a console that shows LIVE against a distribution where this is `false` is lying."
  value       = local.has_api
}

output "api_path_pattern" {
  description = "The path pattern actually routed to the API origin, or `null` when there is no API origin. The console's transport base path must match this exactly."
  value       = local.has_api ? var.api_path_pattern : null
}

output "s3_origin_access_control_id" {
  description = "Id of the S3 origin access control."
  value       = aws_cloudfront_origin_access_control.s3.id
}

output "api_origin_access_control_id" {
  description = "Id of the Lambda origin access control, or `null` when there is no API origin."
  value       = local.has_api ? aws_cloudfront_origin_access_control.api[0].id : null
}

output "tags" {
  description = "The tag set every taggable resource in this module carries. `project = mainline` is set by the module and cannot be overridden by the caller, because it is what teardown filters on in an account holding four unrelated live projects."
  value       = local.tags
}

output "invalidation_command" {
  description = <<-EOT
    The exact command the deploy script runs after `aws s3 sync`, ready to paste.

    `/*` is ONE path for billing purposes and the first 1,000 invalidation paths per month
    are free, so a demo that redeploys twenty times in a week invalidates twenty times and
    is billed nothing. Invalidating a list of specific files would be cheaper in theory and
    is strictly worse here: miss one and a judge holds a stale `index.html` pointing at a
    hashed bundle that no longer exists, which fails as a blank page with a console error.
  EOT
  value       = "aws cloudfront create-invalidation --distribution-id ${aws_cloudfront_distribution.site.id} --paths '/*'"
}
