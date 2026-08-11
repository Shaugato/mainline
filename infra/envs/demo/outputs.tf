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
    phase = (
      var.enable_cloudfront
      ? (var.enable_api ? "2-cloudfront" : "1-replay")
      : "2-furl"
    )
  }
}
