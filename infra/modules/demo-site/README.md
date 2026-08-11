<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
-->

# `demo-site` — the optional CDN upgrade

> ## ⛔ THIS MODULE IS OPTIONAL, IT IS OFF BY DEFAULT, AND IT NO LONGER PRODUCES THE DEMO URL
>
> `infra/envs/demo` instantiates it with `count = var.enable_cloudfront ? 1 : 0`, and that
> variable **defaults to `false`**. The default is a measurement, not a preference. A real
> `terraform apply` on 2026-08-10 created seven resources and AWS refused the eighth:
>
> ```
> Error: creating CloudFront Distribution: operation error CloudFront:
> CreateDistributionWithTags, https response error StatusCode: 403,
> RequestID: 3e63e30d-8c5b-441b-a01b-b70085eba504, AccessDenied:
> Your account must be verified before you can add new CloudFront resources.
> ```
>
> The identical refusal comes from a bare `aws cloudfront create-distribution` with no
> Terraform involved, from an identity holding `AdministratorAccess`. It is an AWS
> **account-level verification hold on new CloudFront resources** — the account already
> carries one distribution from an unrelated project — and only AWS Support can lift it.
>
> **Decision D1** (`docs/leads/ship-final.md` §1.4) therefore moved the hostname to the
> Lambda Function URL in [`../demo-api`](../demo-api): `https://<id>.lambda-url.<region>.on.aws`
> is HTTPS on an AWS-issued certificate, needs no account verification, no ACM and no
> hosted zone, and serves the SPA and `/v1/*` from one origin. This module is what you
> apply **the day the hold lifts**, and flipping `enable_cloudfront` is the whole change.
>
> Everything below is still correct and is still planned on every run —
> `evidence/deploy/terraform-plan-cloudfront.txt` shows these ten resources in a clean
> plan. What changed is which module the submission depends on.

S3 + CloudFront + Origin Access Control. A private bucket serving the MAINLINE console
over HTTPS, and — optionally — a second origin that routes `/v1/*` to a Lambda Function
URL on the same hostname, so the console makes same-origin requests and there is no CORS
anywhere in the system.

> *"Provide a URL to your functional demo app."* — hackathon Stage One, pass/fail.

That sentence is why this module was written to fail loudly at plan time rather than
subtly at 02:00. It is also why it is no longer on the critical path: a Stage One
requirement may not depend on a support queue.

---

## Being absent, correctly

A zero-count module needs nothing inside it to change — Terraform simply does not expand
it. Two obligations fall on the **caller**, and both are load-bearing:

1. **Every output must be reached indexed, through `try`.**

   ```hcl
   distribution_arn = try(module.site[0].distribution_arn, null)   # RIGHT
   distribution_arn = join("", module.site[*].distribution_arn)    # WRONG
   ```

   `module.site[0]` on a zero-count module is an **invalid index** — an error, not a null —
   which is what `try` converts. And a splat depends on the `module.site (close)` node,
   which every resource in this module feeds, including the distribution; since the
   distribution depends on `demo-api`'s Function URL, the splat rebuilds the dependency
   cycle transcribed in [`infra/envs/demo/main.tf`](../../envs/demo/main.tf), in mirror
   image.

2. **`count` may key only on a plan-time-known boolean** — `var.enable_cloudfront`, a plain
   variable — for exactly the reason `local.has_api` inside this module may key only on
   `var.enable_api`. See *The two-input rule* below.

---

## The shape

```
                       ┌─────────────────────────────────────────┐
  judge's browser ───► │ CloudFront  dXXXXXXXX.cloudfront.net    │  HTTPS, default cert
                       │  default behaviour  →  S3   (OAC, sigv4)│  console SPA + bundle
                       │  /v1/*              →  Lambda FURL (OAC)│  the API   ← optional
                       └────────────────┬────────────────────────┘
                                        │ SigV4, IAM-only Function URL
                                        ▼
                              AWS Lambda  ap-southeast-1
```

Nine resources without an API origin, ten with one:

| | |
|---|---|
| `aws_s3_bucket` | the site bucket, named from the caller's prefix |
| `aws_s3_bucket_public_access_block` | all four settings on |
| `aws_s3_bucket_ownership_controls` | `BucketOwnerEnforced` — ACLs off entirely |
| `aws_s3_bucket_versioning` | enabled |
| `aws_s3_bucket_server_side_encryption_configuration` | SSE-S3 (`AES256`) |
| `aws_s3_bucket_lifecycle_configuration` | expire superseded versions (optional, on by default) |
| `aws_s3_bucket_policy` | `s3:GetObject` to one distribution, by ARN; TLS-only deny |
| `aws_cloudfront_origin_access_control` ×1 or ×2 | `s3` type, and `lambda` type when there is an API |
| `aws_cloudfront_distribution` | one hostname, one or two behaviours |

---

## Usage

### Phase 1 — the site alone, before any Lambda exists

```hcl
module "demo_site" {
  source = "../../modules/demo-site"

  bucket_prefix = "mainline-demo-"
  name          = "site"
  tags          = { env = "demo" }
}

output "demo_url" { value = module.demo_site.demo_url }
```

One origin, no `/v1/*` behaviour, a real HTTPS URL. **This is the plan, not the
fallback** — `docs/leads/deploy-plan.md` §4 is explicit that the URL never depends on the
Lambda, because a demo URL is Stage One pass/fail and the API is not.

### Phase 2 — add the API without changing the URL

```hcl
module "demo_site" {
  source = "../../modules/demo-site"

  name_prefix = "mainline-demo"
  name        = "site"
  tags        = { env = "demo" }

  # TWO inputs, not one. See "The two-input rule" below — it is a measured requirement.
  enable_api        = var.enable_api                              # plan-time-known bool
  api_origin_domain = try(module.api[0].function_url_domain, "")  # unknown until apply
}
```

Adding the API is an **in-place distribution update**, not a replacement. The hostname
printed by the first Phase-1 apply is the hostname in the submission form eight days later.

### The two-input rule

`enable_api` and `api_origin_domain` look redundant and are not. **`enable_api` is the only
value this module's `count` and `for_each` key on**, and `api_origin_domain` is only ever
read as a value inside a resource body.

A Lambda Function URL's hostname does not exist until apply. Writing
`count = var.api_origin_domain != "" ? 1 : 0` is a count derived from an unknown, and
Terraform refuses the whole plan:

```
Invalid count argument: The count value depends on resource attributes that
cannot be determined until apply.
```

That error was produced on Terraform v1.14.8 by `infra/envs/demo`, whose header carries the
transcript. Two inputs where one would read more elegantly, because the elegant version does
not plan.

`enable_api` may be left `null`, in which case the module infers it from
`api_origin_domain` — correct and safe in exactly the case where the caller wrote the
hostname as a literal and it is therefore known at plan time. **Pass it explicitly whenever
the hostname comes from another resource.**

`enable_api = true` with an empty hostname is refused by a `precondition` on the
distribution, because it would otherwise build a demo URL that serves the console perfectly
and 502s on every API call.

### Deploy

```bash
terraform apply
aws s3 sync ./dist/ "s3://$(terraform output -raw bucket_name)/" --delete
aws cloudfront create-invalidation \
  --distribution-id "$(terraform output -raw distribution_id)" \
  --paths '/*'
open "$(terraform output -raw demo_url)"
```

`terraform output -raw invalidation_command` emits that third command with the id already
substituted, so the deploy script does not have to assemble it.

`/*` is **one** path for billing and the first 1,000 invalidation paths per month are
free, so twenty redeploys in a week cost nothing. Invalidating a list of named files would
be cheaper in theory and is strictly worse here: miss one and a judge holds a stale
`index.html` pointing at a content-hashed bundle that no longer exists, which presents as a
blank page and a console error rather than as an obvious failure.

---

## The single most important line in this module

```hcl
origin_request_policy_id = "b689b0a8-53d0-40ab-baf2-68738e2966ac"  # Managed-AllViewerExceptHostHeader
```

**The `Host` header must not be forwarded to a Lambda Function URL.**

A Function URL with `authorization_type = AWS_IAM` verifies a SigV4 signature, and the
canonical request that signature covers **includes the `Host` header**. CloudFront's OAC
signs with `Host: <fn-id>.lambda-url.<region>.on.aws` — the origin's own name. If the
distribution also forwards the viewer's `Host` (`dXXXXXXXX.cloudfront.net`), Lambda
recomputes the signature over *that* and the digests differ. Every request to `/v1/*` then
returns `403 Forbidden` with a body that says nothing useful, the site keeps working
perfectly, and the failure looks like an IAM problem for as long as you let it.

`Managed-AllViewer` is the policy that looks right and is wrong. It forwards everything,
including `Host`. `Managed-AllViewerExceptHostHeader` exists for precisely this pairing.
This is the single most common way this exact stack breaks.

Two consequences worth knowing:

* The Lambda handler cannot see the viewer's hostname on `Host`. It sees the Function URL's
  own name. If it ever needs to build an absolute URL, it must use `X-Forwarded-Host`,
  which the policy *does* forward.
* Everything else the viewer sent — method, path, query string, all other headers, cookies
  — reaches the handler unchanged.

---

## The sharp edge: custom error responses are distribution-wide

`spa_error_responses = true` (the default) maps origin **403** and **404** to
`/index.html` with HTTP **200**, so a judge who pastes a deep link gets the console instead
of an S3 `AccessDenied` page. 403 is the code that actually fires: the bucket policy grants
`s3:GetObject` and not `s3:ListBucket`, so S3 answers a missing key with 403 rather than
404, which is also why the grant is written that way — it leaks nothing about what the
bucket contains.

**CloudFront custom error responses are configured per distribution, not per cache
behaviour.** There is no path scoping. The rewrite therefore also applies to 403 and 404
produced by the *API* origin: a `/v1/*` handler that answers "no such permit" with a bare
404 will have that 404 replaced by the HTML of `index.html` carrying status 200, and the
console's `fetch` will fail to parse JSON with an error that points nowhere near the cause.

The contract that keeps both features is therefore:

> **The API must not use bare 403 or 404 as a semantic response.** It returns its error
> envelope under 200, or under a status outside `{403, 404}` — 400, 409, 422, 503.

This module cannot enforce that, because it cannot see the handler. It is stated here, and
recorded as a cross-domain note against the API workers, rather than left to be discovered
at 02:00. Set `spa_error_responses = false` to hand those two status codes back to the API,
at the cost of SPA deep links.

---

## What this module deliberately does not build

| Not built | Why |
|---|---|
| Route 53 hosted zone, ACM certificate, custom domain | $0.50/month for a prettier string in a submission form. `https://dXXXXXXXX.cloudfront.net` is valid HTTPS and free. deploy-plan.md §2.3. |
| WAF web ACL | $5/month minimum plus per-request, to protect a read-only demo over synthetic data. |
| CloudWatch Synthetics canary | $10.37/month at five-minute intervals — thirty times the cost of everything else combined. The health check is a GitHub Actions cron. deploy-plan.md §2.3. |
| Access-log bucket | Storage and PUT charges forever, for a demo nobody audits, and it would require re-enabling S3 ACLs. Pass `logging_bucket` if you want it. |
| A `random` provider for bucket uniqueness | See `bucket_name` below — a digest of the inputs is deterministic where `random_id` is a function of state. |

Because there are no `aliases`, `minimum_protocol_version` is not set: CloudFront fixes it
when the default certificate is in use, and any value written here would be a claim the
distribution does not honour. A plan will show `minimum_protocol_version = "TLSv1"` —
that is CloudFront's own value for the default certificate, not a choice this module made.

---

## Terraform / OpenTofu equivalence

**`tofu init && tofu validate && tofu apply` runs this directory unchanged.** Nothing here
is Terraform-specific. The module is written to the intersection of the two toolchains on
purpose:

* one provider, `hashicorp/aws`, and no provider aliases — CloudFront forces none, because
  there is no ACM certificate and therefore no `us-east-1` provider;
* no `cloud` block, no Terraform Cloud, no remote-state data source;
* no `moved`, `import`, `removed` or `check` blocks;
* no provider-defined functions;
* no cross-variable references inside `validation` blocks — where a constraint spans two
  variables it is a `precondition` in `main.tf` instead;
* `required_version = ">= 1.10.0"`, which both toolchains reached (Terraform 1.10,
  OpenTofu 1.10). The floor exists because the env root that consumes this module uses the
  S3 backend's native `use_lockfile` locking rather than a DynamoDB table, and a CLI below
  the floor would silently drop the lock.

Verification on this machine used Terraform v1.14.8, because that is what is installed —
OpenTofu is not, and installing a second toolchain eight days from a deadline is risk with
no return (deploy-plan.md §2.7). The equivalence above is a claim about the language
features used, and it is checkable by reading the three `.tf` files.

One Terraform/OpenTofu behaviour to know if you consume this module from a **scratch root
on another drive**: an absolute path in `source` is copied into `.terraform/modules/` at
`init` rather than read in place, so edits to the module are not picked up until
`terraform init -upgrade` (or deleting `.terraform/modules`). A root inside the repository
uses a relative source such as `../../modules/demo-site` and does not have this problem.

---

## Inputs

### Naming — what teardown filters on

| Name | Type | Default | Description |
|---|---|---|---|
| `bucket_prefix` | `string` | `"mainline-demo-"` | Prefix for the bucket name, **with** its trailing hyphen. **Not cosmetic.** This AWS account holds seven buckets belonging to four unrelated live projects; teardown identifies what it may delete by this prefix *and* the `project = mainline` tag. Validated to ≤30 characters of lowercase alphanumerics, dots and hyphens. |
| `name_prefix` | `string` | `null` | The same safety string **without** the trailing hyphen — `mainline-demo`. Wins over `bucket_prefix` when set. Exists so that `infra/envs/demo`, which names its whole stack from one `name_prefix`, does not have to translate its one safety control into a second spelling on the way in. |
| `name` | `string` | `"site"` | Short component name. Feeds the bucket name, both origin ids, both OAC names and the distribution comment. Two instances of this module with the same `name` in one account compute the same bucket name and collide. 1–20 characters. |
| `bucket_name` | `string` | `null` | Explicit bucket name, overriding the computed one. `""` is treated as "not set" and falls back to the computed name, because that is what a root module's own bucket-name variable defaults to before it derives a real one. Not validated against `bucket_prefix` — a name set here that drops the prefix is a bucket teardown will refuse to delete, and that refusal is the point of the prefix. |
| `account_id` | `string` | `""` | Twelve digits, or empty to read `aws_caller_identity`. Supplying it lets the module be planned with **no AWS credentials at all**. |
| `region_hint` | `string` | `"ap-southeast-1"` | Passed to no resource. Feeds only the bucket-name digest, so the same module in two regions of one account computes two names instead of colliding on S3's global namespace. |
| `tags` | `map(string)` | `{}` | Merged onto every taggable resource. `project`, `component` and `managed_by` are set by the module and **win over anything passed here** — a caller who can overwrite `project = mainline` is a caller who can hide a resource from teardown, or make another project's resource look like ours. |

The computed bucket name is
`<bucket_prefix><name>-<10 hex chars of sha256("<account>/<region>/<name>")>`, e.g.
`mainline-demo-site-df7d591eb6`. A digest rather than `random_id` because `random_id` adds a
second provider for eight characters of entropy *and* makes the name a function of state:
lose the state file, re-apply, and you have orphaned the old bucket and created a twin. The
digest is deterministic, and it hashes the account number rather than spelling it out so
that a pasted plan does not carry it.

### The API origin

| Name | Type | Default | Description |
|---|---|---|---|
| `enable_api` | `bool` | `null` | Whether to build the second origin and the `/v1/*` behaviour. The **only** value this module's `count`/`for_each` key on. `null` infers from `api_origin_domain`. See "The two-input rule". |
| `api_origin_domain` | `string` | `null` | Bare hostname of the Lambda Function URL — `abc123.lambda-url.ap-southeast-1.on.aws`. **No scheme, no port, no path, no trailing slash**; a value with any of those is refused at `validate`. `null` or `""` yields a one-origin distribution with no `/v1/*` behaviour. May be unknown until apply, provided `enable_api` is passed. |
| `api_path_pattern` | `string` | `"/v1/*"` | Path pattern routed to the API origin. Must match the console transport's base path exactly. |
| `api_origin_read_timeout` | `number` | `30` | Seconds CloudFront waits for the first byte. 30 is CloudFront's default and covers a Lambda cold start that installs psycopg and opens a TLS pgwire session in-region. 60 is the ceiling without an AWS quota increase. |
| `api_origin_keepalive_timeout` | `number` | `5` | Seconds CloudFront holds an idle origin connection. 1–60. |

### Cost knobs — every default is the cheap one

| Name | Type | Default | Description |
|---|---|---|---|
| `price_class` | `string` | `"PriceClass_100"` | `PriceClass_100` (NA + EU), `PriceClass_200`, or `PriceClass_All`. See the trade-off below. |
| `logging_bucket` | `string` | `null` | S3 bucket **domain** (`my-logs.s3.amazonaws.com`, not a bare name) for CloudFront standard access logs. `null` leaves logging off. This module does not create the bucket, and CloudFront requires that bucket to have ACLs enabled. |
| `logging_prefix` | `string` | `"cloudfront/"` | Key prefix for access logs. Ignored when `logging_bucket` is `null`. |
| `noncurrent_version_expiration_days` | `number` | `30` | Days before a superseded object version is deleted; `0` disables the lifecycle rule (and with it the 7-day abort of incomplete multipart uploads). Versioning without expiry means every `aws s3 sync` of a 3.2 MB `dist/` leaves the previous 3.2 MB paying storage forever. |

**`PriceClass_100` is a deliberate trade-off, stated plainly.** It serves from North
America and Europe only, so a judge in Asia-Pacific is served from a US or EU edge rather
than a local one — tens of milliseconds worse on the first hit of a static console that is
cached thereafter, against a demo expected to be idle 99.9 % of the time. `PriceClass_All`
adds Asia-Pacific and South America edges and costs materially more per GB in exactly those
regions. Price class changes **nothing** about correctness, availability or the
certificate: every class is HTTPS on the same `*.cloudfront.net` name. It is the right call
for a cost-minimal demo and the wrong call for a product.

### Behaviour

| Name | Type | Default | Description |
|---|---|---|---|
| `spa_error_responses` | `bool` | `true` | Map 403 and 404 to `/index.html` with 200 for SPA deep links. **Read the sharp-edge section above before enabling this alongside an API origin.** |
| `spa_error_caching_min_ttl` | `number` | `10` | Seconds CloudFront caches a rewritten 403/404. Short so a deploy that fixes a missing asset is visible without an invalidation. |
| `comment` | `string` | `null` | Distribution comment. `null` derives one from `name`. |
| `default_root_object` | `string` | `"index.html"` | Object returned for a request to the distribution root, and the target of the SPA error rewrite. Changing it will break the demo URL. |
| `wait_for_deployment` | `bool` | `true` | Block `apply` until the distribution reaches `Deployed` — 3–8 minutes on creation. `true` is right for the demo deploy, whose whole job is to print a URL that works when a human clicks it. `false` shortens the loop when only S3 content changes. |
| `force_destroy` | `bool` | `false` | Allow `destroy` to delete a bucket that still holds objects and versions. `false` means teardown **fails** on a bucket with content, which is the intended behaviour in an account holding four unrelated live projects. Teardown sets it `true` in one place, having first confirmed the prefix. |

---

## Outputs

| Name | Description |
|---|---|
| `demo_url` | **The URL.** `https://` + the distribution domain, no trailing slash. This is the string that goes in the submission form. |
| `domain_name` | `dXXXXXXXX.cloudfront.net`, without a scheme. |
| `distribution_domain_name` | Identical to `domain_name`, under the name `infra/envs/demo` reads. Both spellings are kept deliberately: renaming an output is how a deploy that worked yesterday stops resolving today. |
| `distribution_id` | e.g. `E1ABCDEFGHIJKL`. Feeds `create-invalidation`. |
| `distribution_arn` | The ARN the bucket policy pins with `AWS:SourceArn`. **Pass this to the API module** so the Lambda's resource policy can pin the same distribution and the Function URL is unreachable except through it. |
| `distribution_hosted_zone_id` | CloudFront's global zone id (`Z2FDTNDATAQYW2`). Unused here; emitted so that adding a custom domain later is one alias record. |
| `bucket_name` | The site bucket. Known at **plan** time — read off the configured `.bucket` rather than the provider-computed `.id`, so a deploy script knows where it is about to upload before it applies. |
| `bucket_arn` | ARN of the site bucket. Grant it to whatever role runs the upload; this module's policy grants read to CloudFront only and says nothing about who may write. |
| `bucket_regional_domain_name` | What the distribution uses as its S3 origin. Emitted for debugging a 403 from the origin: if this is not the `origin.domain_name` in `get-distribution-config`, the OAC is signing for a different bucket than the policy grants. |
| `api_origin_enabled` | `false` when built with `api_origin_domain = null` — a Phase-1 static site. The console reads the same fact to decide whether it may show the `LIVE` badge; a console showing `LIVE` where this is `false` is lying. |
| `api_path_pattern` | The pattern actually routed to the API, or `null` when there is no API origin. |
| `s3_origin_access_control_id` | Id of the `s3`-type OAC. |
| `api_origin_access_control_id` | Id of the `lambda`-type OAC, or `null`. |
| `tags` | The tag set every taggable resource carries, including the three the caller cannot override. |
| `invalidation_command` | The exact `aws cloudfront create-invalidation` command, id already substituted, ready to run. |

---

## Verification — measured 2026-08-10, re-confirmed 2026-08-11

> **Everything in this section is still true, and the module it describes is now
> optional.** These numbers were produced when this module was instantiated
> unconditionally. It is now `count`-gated by `var.enable_cloudfront`, default `false`, so
> in the shipping configuration **none of these resources is planned at all** — see
> `evidence/deploy/terraform-plan-furl.txt`, whose `Plan: 11 to add` contains no
> `aws_cloudfront_*` and no `aws_s3_*` resource. The measurements below describe what
> `enable_cloudfront = true` still plans, and they were re-confirmed on 2026-08-11 by
> `evidence/deploy/terraform-plan-cloudfront.txt` (`Plan: 22 to add, 0 to change, 0 to
> destroy` — twelve from `demo-api`, ten from here). Nothing here was rewritten to look
> tidier; the heading gained a date and this paragraph.

The AWS-managed policy ids in `main.tf` are written as literals rather than resolved
through `data.aws_cloudfront_cache_policy`, so that they are known at plan time and require
no extra API call or IAM permission. They were read off the live account:

```
$ aws cloudfront list-cache-policies --type managed
    Managed-CachingOptimized           658327ea-f89d-4fab-a63d-7e88639e58f6
    Managed-CachingDisabled            4135ea2d-6df8-44a3-9df3-4b5a84be39ad
$ aws cloudfront list-origin-request-policies --type managed
    Managed-AllViewerExceptHostHeader  b689b0a8-53d0-40ab-baf2-68738e2966ac
```

A scratch root instantiating the module **four** ways against the real account, with
Terraform v1.14.8 and `hashicorp/aws v6.58.0`:

| Case | Inputs | Result |
|---|---|---|
| A | `api_origin_domain` unset | 9 resources, no `/v1/*` behaviour |
| B | literal Function URL host, `enable_api` inferred | 10 resources, `/v1/*` routed |
| C | the env root's shape: `name_prefix`, explicit `bucket_name`, `enable_api = true`, and a host that is **unknown until apply** | 10 resources, two origins, `/v1/*` routed |
| D | `enable_api = false`, `api_origin_domain = ""`, `bucket_name = ""` | 9 resources, name derived |

```
$ terraform validate
Success! The configuration is valid.

$ terraform plan
Plan: 39 to add, 0 to change, 0 to destroy.

  + phase1_bucket              = "mainline-demo-site-df7d591eb6"
  + phase2_bucket              = "mainline-demo-sitelive-3f395933b5"
  + envroot_bucket             = "mainline-demo-siteroot-022950218246"
  + envroot_phase1_bucket      = "mainline-demo-siteoff-4959c5b5c8"
  + phase1_api_enabled         = false
  + phase2_api_enabled         = true
  + envroot_api_enabled        = true
  + envroot_phase1_api_enabled = false
  + phase1_tags = { component = "demo-site", env = "demo",
                    managed_by = "terraform", project = "mainline" }
```

39 = 9 + 10 + 10 + 9, plus the one `terraform_data` that stands in for the Function URL.
**Zero destroys and zero changes** — nothing pre-existing in the account is touched. Every
bucket name carries the `mainline-demo-` prefix.

Case C is the one that matters most. Its hostname is unknown at plan time, and the plan
still succeeds with two origins and a `/v1/*` behaviour — which is the two-input rule
working. The caller in case A passed `project = "SHOULD-BE-OVERRIDDEN"` in `tags`; the plan
shows `project = "mainline"`, which is the override precedence enforced rather than
asserted.

Four bad inputs were confirmed to be refused before any resource is written:

* `api_origin_domain = "https://….on.aws/"` — refused at `validate`;
* `price_class = "PriceClass_Cheap"` — refused at `validate`;
* a `bucket_prefix` long enough to overflow S3's 63-character limit — refused at `validate`;
* `enable_api = true` with an empty hostname — refused at `plan`, by the precondition:
  `Error: Resource precondition failed`.

`terraform fmt -check -recursive` reports no changes.

### Not verified

**This module has never been applied to completion, and it cannot be on this account
today.** The 2026-08-10 apply reached `aws_cloudfront_distribution.site` and was refused
with `403 AccessDenied` (RequestID `3e63e30d-8c5b-441b-a01b-b70085eba504`) — the banner at
the top of this page. Two of its resources *were* created before the refusal, and the
teardown was verified clean afterwards: `aws s3api list-buckets` returns seven buckets and
none carries the `mainline-demo-` prefix.

So every claim above is a claim about a *plan*. In particular these are untested against
live AWS and are the places to look first on the day the hold lifts and the first full
apply runs:

* whether CloudFront accepts `origin_access_control_id` on a `custom_origin_config` origin
  at the API — the provider accepts it and the AWS documentation describes it, but neither
  is the service;
* whether the OAC SigV4 signature is actually accepted by the Function URL end to end,
  which cannot be tested until a Function URL exists;
* propagation time from `Deployed` to a URL that answers, which is why
  `wait_for_deployment` defaults to `true`.
