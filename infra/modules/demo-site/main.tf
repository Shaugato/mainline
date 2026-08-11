# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
#
# ═══════════════════════════════════════════════════════════════════════════════════════
#  `demo-site` — THE OPTIONAL CDN UPGRADE. IT NO LONGER PRODUCES THE DEMO URL.
# ═══════════════════════════════════════════════════════════════════════════════════════
#
# ── READ THIS FIRST: THIS MODULE IS OPTIONAL AND OFF BY DEFAULT ────────────────────────
#
# It used to be the only thing in the repository that emitted the demo URL. It is not any
# more, and the reason is a refusal from AWS rather than a change of mind. A real
# `terraform apply` of `infra/envs/demo` on 2026-08-10 created seven resources and was
# refused the eighth:
#
#     Error: creating CloudFront Distribution: operation error CloudFront:
#     CreateDistributionWithTags, https response error StatusCode: 403,
#     RequestID: 3e63e30d-8c5b-441b-a01b-b70085eba504, AccessDenied:
#     Your account must be verified before you can add new CloudFront resources.
#
# The same refusal comes from a bare `aws cloudfront create-distribution`, from an identity
# holding `AdministratorAccess`. It is an account-level verification hold on NEW CloudFront
# resources, liftable only by AWS Support. Decision D1 (`docs/leads/ship-final.md` §1.4)
# therefore moved the hostname to the Lambda Function URL in `../demo-api`, and this module
# became the upgrade you apply the day the hold lifts.
#
# HOW ABSENCE IS EXPRESSED. `infra/envs/demo` instantiates this module with
# `count = var.enable_cloudfront ? 1 : 0`, default `false`. NOTHING INSIDE THIS FILE HAS TO
# CHANGE for that to work — a zero-count module is simply not expanded — but two things are
# true of the caller and are stated here because a future caller will otherwise rediscover
# them the hard way:
#
#   1. Every reference to this module's outputs must be INDEXED AND WRAPPED IN `try`:
#      `try(module.site[0].distribution_arn, null)`. `module.site[0]` on a zero-count module
#      is an INVALID INDEX — an error, not a null — and a splat `module.site[*].x` depends on
#      the `module.site (close)` node, which every resource below feeds, which rebuilds the
#      2026-08-10 dependency cycle in mirror image. See `infra/envs/demo/main.tf`'s header.
#   2. `count` on the module may only key on a plain plan-time-known boolean, for the same
#      reason `local.has_api` below may only key on `var.enable_api`.
#
# Everything from here down is unchanged, correct, and still planned on every run — see
# `evidence/deploy/terraform-plan-cloudfront.txt`, where these ten resources appear.
#
# "Provide a URL to your functional demo app." — Stage One, pass/fail. There is no partial
# credit and no second chance: a submission without a working URL is not judged on Agentic
# Memory Design, or on anything else. That sentence is why this module was written to fail
# loudly at plan time rather than subtly at 02:00, and it is now also why it is not on the
# critical path.
#
# WHAT IT BUILDS
#
#   a private S3 bucket        the console SPA and the EvidenceBundle. No public access on
#                              any of the four settings; readable by exactly one principal.
#   two origin access controls one for S3, one for the Lambda Function URL. Both SigV4.
#   one CloudFront distribution  default behaviour -> S3, `/v1/*` -> the Function URL.
#
# THREE DECISIONS A REVIEWER WILL WANT THE REASON FOR
#
#   1. THE HOST HEADER IS NOT FORWARDED TO THE API ORIGIN, and that is the single most
#      load-bearing line in this file. A Lambda Function URL authenticated with `AWS_IAM`
#      verifies a SigV4 signature whose canonical request INCLUDES the `Host` header. The
#      signature CloudFront's OAC computes is over `Host: <fn-id>.lambda-url.<region>.on.aws`
#      — the origin's own name. If the distribution also forwards the VIEWER's `Host`
#      (`dXXXXXXXX.cloudfront.net`), Lambda recomputes the signature over that instead, the
#      digests differ, and every request to the API returns 403 Forbidden with a body that
#      says nothing useful. `Managed-AllViewerExceptHostHeader` is therefore not a
#      performance choice, it is a correctness requirement, and it is the single most common
#      way this exact stack breaks. `Managed-AllViewer` is the wrong policy here and looks
#      right.
#
#   2. THE BUCKET POLICY GRANTS `s3:GetObject` TO ONE DISTRIBUTION, BY ARN. The principal is
#      the `cloudfront.amazonaws.com` service, narrowed by `AWS:SourceArn` to this
#      distribution's ARN. Without the condition, the grant reads "any CloudFront
#      distribution in any AWS account may read this bucket", which is the confused-deputy
#      hole OAC exists to close. There is no cycle: bucket -> distribution -> bucket policy,
#      because the distribution references the bucket's regional domain name and not its
#      policy.
#
#   3. THE API ORIGIN IS OPTIONAL, AND ITS ABSENCE IS THE PLAN, NOT THE FALLBACK.
#      `api_origin_domain = null` yields a one-origin distribution with no `/v1/*`
#      behaviour, which is a complete, working, HTTPS demo URL serving a signed
#      EvidenceBundle with no backend that can fall over. deploy-plan.md §4: the URL never
#      depends on the Lambda. Adding the origin later is an in-place update; the hostname
#      printed on day one is the hostname in the submission form on day eight.
#
# WHAT IT DELIBERATELY DOES NOT BUILD: no Route 53 zone, no ACM certificate, no custom
# domain (§2.3 — $0.50/month for a prettier string in a form), no WAF, no Synthetics canary
# (§2.3 — $10.37/month, thirty times the cost of everything else combined), no access-log
# bucket by default, and no `random` provider (see `local.bucket_name`).

# ── Identity, names, and the three AWS-managed policies ───────────────────────────────

# Read from STS only when the caller did not supply it, so that the module can be planned
# with no credentials at all. Same idiom, same reason, as infra/modules/evidence-store.
data "aws_caller_identity" "current" {
  count = var.account_id == "" ? 1 : 0
}

locals {
  account_id = var.account_id != "" ? var.account_id : data.aws_caller_identity.current[0].account_id

  # `name_prefix` is the same safety string as `bucket_prefix` spelled without its trailing
  # hyphen, because the env root names its whole stack from one variable and a module that
  # demanded a second spelling of a safety control would be a module the root had to
  # remember to translate for.
  effective_prefix = var.name_prefix != null ? "${var.name_prefix}-" : var.bucket_prefix

  # A deterministic digest instead of `random_id`. `random_id` would add a second provider
  # for eight characters of entropy AND would make the bucket name a function of state
  # rather than of inputs — lose the state file and you orphan the old bucket and create a
  # twin. sha256 over (account, region, name) is globally unique in practice, stable across
  # a state rebuild, and reveals neither the account number nor the region to whoever reads
  # a pasted plan.
  #
  # `coalesce` and not `var.bucket_name != null ? … : …`, because `coalesce` skips the
  # empty string as well as null — and "" is what a root module's own
  # `var.site_bucket_name` default is, before it derives a real one.
  bucket_name = coalesce(
    var.bucket_name,
    "${local.effective_prefix}${var.name}-${substr(sha256("${local.account_id}/${var.region_hint}/${var.name}"), 0, 10)}",
  )

  s3_origin_id  = "${var.name}-s3"
  api_origin_id = "${var.name}-api"

  # THE ONLY VALUE `count` AND `for_each` IN THIS MODULE MAY KEY ON, and it is deliberately
  # NOT `var.api_origin_domain != ""`.
  #
  # A Lambda Function URL hostname does not exist until apply. A `count` derived from it is
  # a count derived from an unknown, and Terraform refuses the entire plan with "Invalid
  # count argument: The count value depends on resource attributes that cannot be determined
  # until apply" — measured on Terraform v1.14.8 by `infra/envs/demo`, whose header carries
  # the transcript. So the caller passes a separate plan-time-known boolean, and
  # `api_origin_domain` is only ever read as a VALUE inside a resource body, where an
  # unknown is perfectly legal.
  #
  # `enable_api = null` falls back to inference, which is correct and safe in exactly the
  # case where the caller wrote the hostname as a literal and it is therefore known.
  has_api = var.enable_api != null ? var.enable_api : (var.api_origin_domain != null && var.api_origin_domain != "")

  # `component` and `project` are what the teardown script filters on and what makes a
  # resource in this account identifiable as ours; `var.tags` is merged FIRST so the caller
  # cannot overwrite them.
  tags = merge(var.tags, {
    project    = "mainline"
    component  = "demo-site"
    managed_by = "terraform"
  })

  # AWS-MANAGED POLICY IDS, PINNED AS CONSTANTS AND VERIFIED AGAINST THE LIVE ACCOUNT.
  #
  # These are account-independent and region-independent AWS-managed policies. They are
  # written here as literals rather than resolved through `data.aws_cloudfront_cache_policy`
  # for the same reason evidence-store derives its bucket ARN from inputs: a value that is
  # "known after apply" is a value no gate can read off a plan, and a data source is an API
  # call and an IAM permission that can fail on the one day it matters.
  #
  # Verified against the live account on 2026-08-10 with:
  #   aws cloudfront list-cache-policies --type managed \
  #     --query "CachePolicyList.Items[].{Name:CachePolicy.CachePolicyConfig.Name,Id:CachePolicy.Id}"
  #   aws cloudfront list-origin-request-policies --type managed \
  #     --query "OriginRequestPolicyList.Items[].{Name:OriginRequestPolicy.OriginRequestPolicyConfig.Name,Id:OriginRequestPolicy.Id}"
  #
  #   Managed-CachingOptimized           658327ea-f89d-4fab-a63d-7e88639e58f6
  #   Managed-CachingDisabled            4135ea2d-6df8-44a3-9df3-4b5a84be39ad
  #   Managed-AllViewerExceptHostHeader  b689b0a8-53d0-40ab-baf2-68738e2966ac

  # Long TTLs, compression on, query strings and cookies out of the cache key. Correct for
  # a fingerprinted SPA bundle.
  cache_policy_caching_optimized = "658327ea-f89d-4fab-a63d-7e88639e58f6"

  # No caching at all, and no headers/cookies/query strings in the cache key. Correct for an
  # API whose whole job is to run a gate against the live database and report what the
  # database said.
  cache_policy_caching_disabled = "4135ea2d-6df8-44a3-9df3-4b5a84be39ad"

  # Everything the viewer sent EXCEPT `Host`. See decision 1 in the header.
  origin_request_policy_all_viewer_except_host = "b689b0a8-53d0-40ab-baf2-68738e2966ac"
}

# ── The bucket ────────────────────────────────────────────────────────────────────────

resource "aws_s3_bucket" "site" {
  bucket        = local.bucket_name
  force_destroy = var.force_destroy
  tags          = local.tags

  lifecycle {
    precondition {
      condition     = length(local.bucket_name) >= 3 && length(local.bucket_name) <= 63
      error_message = "The computed bucket name is not a legal S3 bucket name (3-63 characters). Shorten `bucket_prefix` or `name`, or set `bucket_name` explicitly."
    }
  }
}

resource "aws_s3_bucket_public_access_block" "site" {
  bucket = aws_s3_bucket.site.id

  # All four. Three of the four are the ones people remember; `ignore_public_acls` is the
  # one that is forgotten, and it is the one that neutralises an ACL somebody else attaches.
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "site" {
  bucket = aws_s3_bucket.site.id

  rule {
    # ACLs off entirely. With OAC there is no reason for an object ACL to exist, and an
    # object ACL is a second authorisation surface that does not show up in the bucket
    # policy a reviewer is reading.
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_versioning" "site" {
  bucket = aws_s3_bucket.site.id

  versioning_configuration {
    # Not for durability theatre: the demo's site content is a build artefact that gets
    # re-synced on every deploy, and versioning is what makes "the console regressed at
    # 14:00" a recoverable event rather than a story. It is also what makes
    # `noncurrent_version_expiration_days` necessary — see below.
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "site" {
  bucket = aws_s3_bucket.site.id

  rule {
    apply_server_side_encryption_by_default {
      # SSE-S3, not SSE-KMS. The bucket holds a public web bundle and a signed, publishable
      # EvidenceBundle. A customer-managed key would buy no confidentiality over content
      # that is served to the internet by design, and would add both a per-request KMS
      # charge and a key whose deletion silently bricks the demo.
      sse_algorithm = "AES256"
    }
    bucket_key_enabled = false
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "site" {
  count = var.noncurrent_version_expiration_days > 0 ? 1 : 0

  bucket = aws_s3_bucket.site.id

  rule {
    id     = "expire-superseded-and-abandoned"
    status = "Enabled"

    # Empty filter = every object. Declared rather than omitted because the provider
    # requires exactly one of `filter` or the deprecated `prefix`.
    filter {}

    noncurrent_version_expiration {
      noncurrent_days = var.noncurrent_version_expiration_days
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }

  # Noncurrent-version expiry is meaningless on a bucket that is not yet versioned, and the
  # two resources have no implicit dependency because both only reference the bucket id.
  depends_on = [aws_s3_bucket_versioning.site]
}

# ── Origin access controls ────────────────────────────────────────────────────────────

resource "aws_cloudfront_origin_access_control" "s3" {
  name        = "${local.bucket_name}-s3"
  description = "SigV4-signs every CloudFront request to the ${local.bucket_name} origin, so the bucket can stay private on all four public-access settings."

  origin_access_control_origin_type = "s3"

  # `always`, not `no-override`. `no-override` signs only when the viewer request did not
  # already carry an `Authorization` header, which means a viewer can suppress the signature
  # by sending one — against a bucket whose entire access story is that signature.
  signing_behavior = "always"
  signing_protocol = "sigv4"
}

resource "aws_cloudfront_origin_access_control" "api" {
  count = local.has_api ? 1 : 0

  name        = "${local.bucket_name}-api"
  description = "SigV4-signs every CloudFront request to the Lambda Function URL, which is why the Function URL can be AWS_IAM-authenticated and therefore unreachable except through this distribution."

  origin_access_control_origin_type = "lambda"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

# ── The distribution ──────────────────────────────────────────────────────────────────

resource "aws_cloudfront_distribution" "site" {
  enabled             = true
  is_ipv6_enabled     = true
  comment             = coalesce(var.comment, "MAINLINE ${var.name} - demo console and API (project=mainline)")
  default_root_object = var.default_root_object
  price_class         = var.price_class

  # HTTP/3 costs nothing and is a viewer-side improvement only; it changes nothing about
  # either origin.
  http_version = "http2and3"

  wait_for_deployment = var.wait_for_deployment

  # On destroy, disable and delete rather than leaving an orphan distribution behind that
  # nobody can find and everybody keeps paying for.
  retain_on_delete = false

  tags = local.tags

  lifecycle {
    # `enable_api = true` with no hostname would build a distribution with a `/v1/*`
    # behaviour pointing at an origin that does not exist — a demo URL that serves the
    # console perfectly and 502s on every API call. When the hostname is unknown at plan
    # time this check is deferred to apply, which is exactly when the value becomes
    # knowable, and it fails before the distribution is written rather than after.
    precondition {
      condition     = !local.has_api || (var.api_origin_domain != null && var.api_origin_domain != "")
      error_message = "enable_api is true but api_origin_domain is empty. The /v1/* behaviour needs an origin hostname; pass the Lambda Function URL host, or set enable_api = false to ship the Phase-1 site alone."
    }
  }

  # ORIGIN 1 — the private bucket. No `s3_origin_config`: that block is the legacy Origin
  # Access IDENTITY, and setting both is how a distribution ends up authenticating twice and
  # matching neither policy.
  origin {
    origin_id                = local.s3_origin_id
    domain_name              = aws_s3_bucket.site.bucket_regional_domain_name
    origin_access_control_id = aws_cloudfront_origin_access_control.s3.id
  }

  # ORIGIN 2 — the Lambda Function URL. Present only when the caller supplied a hostname.
  dynamic "origin" {
    for_each = local.has_api ? [var.api_origin_domain] : []

    content {
      origin_id                = local.api_origin_id
      domain_name              = origin.value
      origin_access_control_id = aws_cloudfront_origin_access_control.api[0].id

      custom_origin_config {
        http_port  = 80
        https_port = 443

        # A Function URL is HTTPS-only. `match-viewer` would let a plaintext hop exist in
        # principle and would make the origin protocol a function of the viewer's choice.
        origin_protocol_policy = "https-only"

        # TLS 1.2 only. TLS 1.0 and 1.1 are deprecated and the origin does not offer them.
        origin_ssl_protocols = ["TLSv1.2"]

        origin_read_timeout      = var.api_origin_read_timeout
        origin_keepalive_timeout = var.api_origin_keepalive_timeout
      }
    }
  }

  # DEFAULT BEHAVIOUR — the SPA, from S3.
  default_cache_behavior {
    target_origin_id       = local.s3_origin_id
    viewer_protocol_policy = "redirect-to-https"

    allowed_methods = ["GET", "HEAD"]
    cached_methods  = ["GET", "HEAD"]

    # `Managed-CachingOptimized` puts `Accept-Encoding` in the cache key with gzip and
    # brotli enabled, which is the precondition for this flag doing anything at all.
    compress = true

    cache_policy_id = local.cache_policy_caching_optimized
  }

  # `/v1/*` BEHAVIOUR — the API, from the Function URL. See decision 1 in the header for
  # why `origin_request_policy_id` is the line that makes this work.
  dynamic "ordered_cache_behavior" {
    for_each = local.has_api ? [1] : []

    content {
      path_pattern           = var.api_path_pattern
      target_origin_id       = local.api_origin_id
      viewer_protocol_policy = "redirect-to-https"

      allowed_methods = ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"]

      # `cached_methods` may only ever be a subset of `allowed_methods`, and CloudFront
      # accepts only GET+HEAD or GET+HEAD+OPTIONS here. It is moot under CachingDisabled and
      # is stated so the plan is explicit that no mutation is ever served from cache.
      cached_methods = ["GET", "HEAD"]

      # FALSE, and not by oversight. `Managed-CachingDisabled` does not put `Accept-Encoding`
      # in the cache key, and CloudFront only compresses when the cache policy enables it —
      # so `compress = true` here would be an inert flag that reads like a guarantee.
      # `AllViewerExceptHostHeader` forwards the viewer's `Accept-Encoding` to the origin, so
      # the handler may compress its own responses if it ever needs to.
      compress = false

      cache_policy_id          = local.cache_policy_caching_disabled
      origin_request_policy_id = local.origin_request_policy_all_viewer_except_host
    }
  }

  # SPA DEEP LINKS. Distribution-scoped, not behaviour-scoped — see the long note on
  # `var.spa_error_responses`, which is the sharpest edge in this module.
  dynamic "custom_error_response" {
    for_each = var.spa_error_responses ? [403, 404] : []

    content {
      error_code            = custom_error_response.value
      response_code         = 200
      response_page_path    = "/${trimprefix(var.default_root_object, "/")}"
      error_caching_min_ttl = var.spa_error_caching_min_ttl
    }
  }

  # ACCESS LOGS — off unless the caller passes a bucket domain.
  dynamic "logging_config" {
    for_each = var.logging_bucket == null ? [] : [var.logging_bucket]

    content {
      bucket          = logging_config.value
      prefix          = var.logging_prefix
      include_cookies = false
    }
  }

  restrictions {
    geo_restriction {
      # The judges' location is not known in advance and a geo restriction that excludes one
      # of them is a self-inflicted Stage One failure.
      restriction_type = "none"
    }
  }

  viewer_certificate {
    # CloudFront's own `*.cloudfront.net` certificate. No `aliases`, so no ACM certificate in
    # us-east-1, no Route 53 hosted zone, and no $0.50/month. `https://dXXXXXXXX.cloudfront.net`
    # is valid HTTPS and free (deploy-plan.md §2.3). `minimum_protocol_version` is not set
    # because CloudFront fixes it when the default certificate is in use and any value
    # supplied here would be a claim the distribution does not honour.
    cloudfront_default_certificate = true
  }
}

# ── The bucket policy, written last because it names the distribution ─────────────────

data "aws_iam_policy_document" "site" {
  statement {
    sid    = "AllowCloudFrontOACReadOfThisDistributionOnly"
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["cloudfront.amazonaws.com"]
    }

    # `s3:GetObject` and nothing else. No `s3:ListBucket`: without it a request for a
    # missing key returns 403 rather than 404, which leaks nothing about what the bucket
    # contains, and which is precisely why `spa_error_responses` maps 403 as well as 404.
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.site.arn}/*"]

    condition {
      # Without this condition the statement means "any CloudFront distribution in any AWS
      # account may read this bucket". This is the confused-deputy hole that OAC exists to
      # close, and the condition is the half of OAC that lives on the bucket rather than on
      # the distribution.
      test     = "StringEquals"
      variable = "AWS:SourceArn"
      values   = [aws_cloudfront_distribution.site.arn]
    }
  }

  statement {
    sid    = "DenyInsecureTransport"
    effect = "Deny"

    principals {
      type        = "*"
      identifiers = ["*"]
    }

    actions = ["s3:*"]
    resources = [
      aws_s3_bucket.site.arn,
      "${aws_s3_bucket.site.arn}/*",
    ]

    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_s3_bucket_policy" "site" {
  bucket = aws_s3_bucket.site.id
  policy = data.aws_iam_policy_document.site.json

  # `block_public_policy = true` evaluates the policy as it is written. This one is not
  # public — its only Allow is to a service principal narrowed by SourceArn — but the
  # ordering is declared so the guard is provably in place before any policy is attached.
  depends_on = [aws_s3_bucket_public_access_block.site]
}
