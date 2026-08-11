# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
#
# Every default in this file is the CHEAP and SAFE value, and every variable that can cost
# money is off unless the caller turns it on. Two of them — `bucket_prefix` and `tags` —
# exist because this AWS account holds four unrelated live projects
# (deploy-plan.md §1.5) and a teardown that filters on the wrong thing is unforgivable.
#
# No `validation` block below references another variable. That is deliberate: cross-object
# references in `validation` are a Terraform 1.9+ feature whose OpenTofu equivalence this
# module does not want to depend on (see versions.tf). Where a constraint spans two
# variables it is expressed as a `precondition` in main.tf instead.

# ── Naming: what the teardown filters on ──────────────────────────────────────────────

variable "bucket_prefix" {
  description = <<-EOT
    Prefix for the site bucket's name. The caller passes `mainline-demo-`.

    This is not cosmetic. `aws s3api list-buckets` on the deploy account returns seven
    buckets belonging to four unrelated live projects, and the teardown script identifies
    what it may delete by this prefix and by the `project = mainline` tag. A bucket that
    carries neither is a bucket teardown must refuse to touch.

    Must be a legal leading fragment of an S3 bucket name: lowercase alphanumerics, dots
    and hyphens, starting with an alphanumeric. Trailing hyphen is expected and allowed.
  EOT
  type        = string
  default     = "mainline-demo-"

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9.-]{0,29}$", var.bucket_prefix))
    error_message = "bucket_prefix must start with a lowercase alphanumeric, contain only lowercase alphanumerics, dots and hyphens, and be at most 30 characters. The 30-character ceiling exists so that prefix + name + the 10-character account digest can never exceed S3's 63-character limit."
  }
}

variable "name_prefix" {
  description = <<-EOT
    Alias for `bucket_prefix` that takes the prefix WITHOUT its trailing hyphen —
    `mainline-demo` rather than `mainline-demo-`. When set (not `null`) it wins over
    `bucket_prefix`, and the module appends the hyphen itself.

    It exists because `infra/envs/demo` names every resource in the stack from one
    `name_prefix` variable — the same string `scripts/deploy/teardown.sh` refuses to delete
    anything without — and a module that demanded a differently-spelled version of that one
    safety control would be a module the root had to remember to translate for. There is
    exactly one safety string, and both spellings of it lead here.
  EOT
  type        = string
  default     = null

  validation {
    condition     = var.name_prefix == null || can(regex("^[a-z0-9][a-z0-9.-]{0,28}$", var.name_prefix))
    error_message = "name_prefix must start with a lowercase alphanumeric, contain only lowercase alphanumerics, dots and hyphens, and be at most 29 characters (one shorter than bucket_prefix, because the module appends the hyphen)."
  }
}

variable "name" {
  description = <<-EOT
    Short component name, appended to `bucket_prefix` and used for the origin ids, the two
    origin access controls and the distribution comment. `site` is right for the demo
    console; change it only if a second, independent site is ever provisioned into the same
    account, because two instances of this module with the same `name` would compute the
    same bucket name and collide.
  EOT
  type        = string
  default     = "site"

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9-]{0,19}$", var.name))
    error_message = "name must be 1-20 characters of lowercase alphanumerics and hyphens, starting with an alphanumeric."
  }
}

variable "bucket_name" {
  description = <<-EOT
    Explicit, fully-specified bucket name. `null` (the default) means the module computes
    one as `<bucket_prefix><name>-<10 hex chars of sha256(account/region/name)>`, e.g.
    `mainline-demo-site-9f0f1e6b2d`.

    The digest — rather than a `random_id` — is how the name stays globally unique without
    pulling in a second provider, and it is DETERMINISTIC: losing the state file and
    re-applying computes the same bucket rather than orphaning the old one and creating a
    twin. It is derived from the account id and region, which are not secret, but it is
    hashed rather than spelled out so the account number is not printed in a plan that gets
    pasted into a chat window.

    Set this only when an operator needs a name they can type from memory. It is NOT
    validated against `bucket_prefix`; a name set here that drops the prefix is a bucket the
    teardown script will refuse to delete, and that refusal is the point of the prefix.
  EOT
  type        = string
  default     = null

  validation {
    condition     = var.bucket_name == null || var.bucket_name == "" || can(regex("^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$", var.bucket_name))
    error_message = "bucket_name must be null, empty, or a valid S3 bucket name: 3-63 lowercase alphanumerics, dots and hyphens, starting and ending with an alphanumeric."
  }
}

variable "account_id" {
  description = <<-EOT
    The twelve-digit account this stack is provisioned into. Empty (the default) falls back
    to `aws_caller_identity`.

    Supplying it lets the whole module be PLANNED with no AWS credentials at all, which is
    what makes the module reviewable on a machine that has never been given a key — the
    same reason `infra/modules/evidence-store` takes this variable.
  EOT
  type        = string
  default     = ""

  validation {
    condition     = var.account_id == "" || can(regex("^[0-9]{12}$", var.account_id))
    error_message = "account_id must be empty or exactly twelve digits."
  }
}

variable "region_hint" {
  description = <<-EOT
    The region this stack is provisioned into. It is passed to NO resource — the provider's
    own region is authoritative for placement — and is used only as an input to the bucket
    name digest, so that the same module applied in two regions of one account computes two
    different bucket names instead of colliding on a global namespace.

    `ap-southeast-1` is the demo's region: beside the CockroachDB Cloud cluster
    (deploy-plan.md §2.4). CloudFront itself is global and ignores this entirely.
  EOT
  type        = string
  default     = "ap-southeast-1"
}

variable "tags" {
  description = <<-EOT
    Tags merged onto every taggable resource. The three that matter — `project = mainline`,
    `component = demo-site`, `managed_by = terraform` — are set BY THE MODULE and win over
    anything passed here, because the teardown script filters on `project = mainline` and a
    caller who can overwrite that tag is a caller who can hide a resource from teardown or,
    worse, make an unrelated project's resource look like ours.
  EOT
  type        = map(string)
  default     = {}
}

# ── The API origin: absent in Phase 1, present in Phase 2 ─────────────────────────────

variable "enable_api" {
  description = <<-EOT
    Whether to build the second origin and the `/v1/*` behaviour. `null` (the default)
    means "infer it from `api_origin_domain`", which is correct whenever that value is a
    literal the caller already knows.

    PASS THIS EXPLICITLY WHENEVER `api_origin_domain` COMES FROM ANOTHER RESOURCE, and
    understand that it is not a convenience. A Lambda Function URL's hostname does not
    exist until apply, so an expression like `count = var.api_origin_domain != "" ? 1 : 0`
    is a count that depends on an unknown value, and Terraform refuses the whole plan:

        Invalid count argument: The count value depends on resource attributes that
        cannot be determined until apply.

    That error was produced on Terraform v1.14.8 by `infra/envs/demo` and is transcribed in
    that root's own header. `enable_api` is therefore a SEPARATE, plan-time-known boolean:
    it is the only thing this module's `count` and `for_each` are ever allowed to key on,
    and `api_origin_domain` is used strictly as a VALUE inside a resource body, where an
    unknown is fine.

    Two inputs where one would read more elegantly, because the elegant version does not
    plan.
  EOT
  type        = bool
  default     = null
}

variable "api_origin_domain" {
  description = <<-EOT
    Hostname of the Lambda Function URL that serves the API, with NO scheme and NO path —
    `abc123def456.lambda-url.ap-southeast-1.on.aws`, never
    `https://abc123def456.lambda-url.ap-southeast-1.on.aws/`.

    `null` — and the empty string, which a root module that reaches a counted module with
    `try(module.api[0].function_url_domain, "")` will produce — is the load-bearing case,
    not the degenerate one. With no domain the distribution has ONE origin and NO `/v1/*`
    behaviour, so the site ships, with a real HTTPS URL, before any Lambda exists anywhere.
    deploy-plan.md §4 calls this the Phase-1 cut line: "Nobody is allowed to let the live
    path hold the URL hostage." A demo URL is Stage One pass/fail for the whole submission;
    the API is not.

    Adding the domain later is an in-place distribution update, not a replacement, so the
    URL printed on day one is the URL in the submission form on day eight.

    When this value is unknown at plan time — which it always is when it comes from a
    Function URL resource — you must also pass `enable_api`. See that variable.
  EOT
  type        = string
  default     = null

  validation {
    condition     = var.api_origin_domain == null || var.api_origin_domain == "" || can(regex("^[a-z0-9][a-z0-9.-]*[a-z0-9]$", var.api_origin_domain))
    error_message = "api_origin_domain must be null, empty, or a bare hostname: no scheme, no port, no path, no trailing slash. `https://x.lambda-url.ap-southeast-1.on.aws/` is wrong; `x.lambda-url.ap-southeast-1.on.aws` is right."
  }
}

variable "api_path_pattern" {
  description = <<-EOT
    Path pattern routed to the API origin. `/v1/*` matches the console's declared resource
    surface in `verticals/mainline/apps/console/src/data/resources.ts`.

    Everything not matching this falls through to the default behaviour and is served from
    S3, which is why the SPA and the API share one hostname and the console makes
    same-origin requests with no CORS anywhere (deploy-plan.md §2.1).
  EOT
  type        = string
  default     = "/v1/*"
}

variable "api_origin_read_timeout" {
  description = <<-EOT
    Seconds CloudFront waits for the API origin to return the first byte. 30 is CloudFront's
    default and comfortably covers a Lambda cold start that installs psycopg and opens a TLS
    pgwire session inside the same region. 60 is the ceiling without an AWS quota increase.
  EOT
  type        = number
  default     = 30

  validation {
    condition     = var.api_origin_read_timeout >= 1 && var.api_origin_read_timeout <= 60
    error_message = "api_origin_read_timeout must be between 1 and 60 seconds. Above 60 requires an AWS service-quota increase, which this stack deliberately does not depend on."
  }
}

variable "api_origin_keepalive_timeout" {
  description = "Seconds CloudFront holds an idle connection to the API origin open. 5 is CloudFront's default; 60 is the ceiling without a quota increase."
  type        = number
  default     = 5

  validation {
    condition     = var.api_origin_keepalive_timeout >= 1 && var.api_origin_keepalive_timeout <= 60
    error_message = "api_origin_keepalive_timeout must be between 1 and 60 seconds."
  }
}

# ── Cost knobs. Every default is the cheap one. ───────────────────────────────────────

variable "price_class" {
  description = <<-EOT
    CloudFront edge footprint.

    `PriceClass_100` — the default here — serves from North America and Europe only.
    `PriceClass_All` serves from every edge location including Asia-Pacific and South
    America, and costs materially more per GB in exactly those regions.

    The trade-off, stated plainly: the judges' latency is worse from Asia-Pacific under
    `PriceClass_100`, because a request from Singapore is served from a US or EU edge rather
    than a local one. That is tens of milliseconds on a 3 MB static console that is cached
    after the first hit, against a demo that is expected to be idle 99.9 % of the time. It
    is the right call for a cost-minimal demo and the wrong call for a product, and a caller
    who disagrees passes `PriceClass_All` and pays for it.

    Note that price class does NOT change correctness, availability, or the certificate:
    every price class is HTTPS on the same `*.cloudfront.net` name.
  EOT
  type        = string
  default     = "PriceClass_100"

  validation {
    condition     = contains(["PriceClass_100", "PriceClass_200", "PriceClass_All"], var.price_class)
    error_message = "price_class must be one of PriceClass_100, PriceClass_200, PriceClass_All."
  }
}

variable "logging_bucket" {
  description = <<-EOT
    S3 bucket DOMAIN (not name) to receive CloudFront standard access logs, e.g.
    `my-logs.s3.amazonaws.com`. `null` — the default — leaves access logging OFF.

    Off is deliberate. Standard logging costs S3 storage and S3 PUT requests forever, for a
    demo nobody is going to audit, and the log bucket must additionally have ACLs enabled
    (`BucketOwnerPreferred`), which is a control this repository turns off everywhere else
    on principle. The observability that actually matters for this stack is the Lambda's
    CloudWatch log group and the `/v1/health` cron in GitHub Actions
    (deploy-plan.md §2.3) — both of which cost nothing.

    This module does not CREATE the log bucket. Supplying a domain here for a bucket that
    does not exist, or that lacks ACLs, makes CloudFront reject the distribution update.
  EOT
  type        = string
  default     = null
}

variable "logging_prefix" {
  description = "Key prefix for access logs. Ignored when `logging_bucket` is null."
  type        = string
  default     = "cloudfront/"
}

variable "noncurrent_version_expiration_days" {
  description = <<-EOT
    Days after which a superseded object version is deleted. `0` disables the lifecycle rule
    entirely.

    Versioning is required on this bucket, and versioning without expiry means every
    `aws s3 sync` of a 3.2 MB console `dist/` leaves the previous 3.2 MB paying storage
    forever. Thirty days is long enough to roll back a bad deploy by hand and short enough
    that the bucket does not grow without bound across a week of iteration.
  EOT
  type        = number
  default     = 30

  validation {
    condition     = var.noncurrent_version_expiration_days >= 0 && var.noncurrent_version_expiration_days <= 3650
    error_message = "noncurrent_version_expiration_days must be between 0 (disabled) and 3650."
  }
}

# ── Behaviour ─────────────────────────────────────────────────────────────────────────

variable "spa_error_responses" {
  description = <<-EOT
    Map origin 403 and 404 to `/index.html` with HTTP 200, so a judge who pastes a deep link
    such as `.../gate/permit/PRM-0007` gets the console instead of an S3 AccessDenied page.
    A private S3 bucket behind OAC answers a missing key with 403, not 404, because the OAC
    policy grants `s3:GetObject` and nothing else — so 403 is the case that actually fires
    and 404 is the belt to its braces.

    READ THIS BEFORE TURNING IT ON ALONGSIDE AN API. CloudFront custom error responses are
    configured per DISTRIBUTION, not per cache behaviour: there is no path scoping, and the
    rewrite therefore also applies to 403 and 404 responses produced by the API origin. A
    `/v1/*` handler that answers "no such permit" with a bare 404 will have that 404 replaced
    by the HTML of `index.html` carrying status 200, and the console's fetch will fail to
    parse JSON with a message that points nowhere near the cause.

    The contract that keeps both features is therefore: **the API must not use bare 403 or
    404 as a semantic response.** It returns its error envelope under 200, or under a status
    outside {403, 404} — 400, 409, 422, 503. This is recorded as a cross-domain note against
    the API workers rather than enforced here, because this module cannot see their handler.

    Set `false` to give the API those two status codes back, at the cost of deep links.
  EOT
  type        = bool
  default     = true
}

variable "spa_error_caching_min_ttl" {
  description = "Seconds CloudFront caches a rewritten 403/404. Short on purpose: a deploy that fixes a missing asset should be visible without an invalidation. Ignored when `spa_error_responses` is false."
  type        = number
  default     = 10

  validation {
    condition     = var.spa_error_caching_min_ttl >= 0 && var.spa_error_caching_min_ttl <= 31536000
    error_message = "spa_error_caching_min_ttl must be between 0 and 31536000 seconds."
  }
}

variable "comment" {
  description = "Distribution comment, shown in the CloudFront console. `null` derives one from `name`. Purely descriptive; changing it is an in-place update."
  type        = string
  default     = null
}

variable "default_root_object" {
  description = "Object CloudFront returns for a request to the distribution root. `index.html` is the SPA's entry point and changing it will break the demo URL."
  type        = string
  default     = "index.html"
}

variable "wait_for_deployment" {
  description = <<-EOT
    Block `apply` until the distribution reaches `Deployed` (typically 3-8 minutes on
    creation, faster on update). `true` is right for the demo deploy: the script's whole job
    is to print a URL that works when a human clicks it, and returning early prints a URL
    that 404s for the next five minutes.

    A caller iterating on the site content — where only the S3 objects change and the
    distribution does not — can set this `false` to shorten the loop.
  EOT
  type        = bool
  default     = true
}

variable "force_destroy" {
  description = <<-EOT
    Allow `terraform destroy` to delete the bucket while it still holds objects and object
    versions.

    `false` is the default and it means teardown will FAIL on a bucket with content. That is
    the intended behaviour for a module operating in an account with four unrelated live
    projects: a destroy that quietly empties a bucket is the failure mode this default
    exists to prevent. The teardown path sets it `true` deliberately, in one place, having
    already confirmed the bucket name carries the `mainline-demo-` prefix.
  EOT
  type        = bool
  default     = false
}
