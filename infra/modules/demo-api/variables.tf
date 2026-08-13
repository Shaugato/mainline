# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
#
# THE DSN IS NOT IN THIS FILE, AND THERE IS NO VARIABLE THAT COULD CARRY IT.
#
# `dsn_parameter_name` is a NAME. Terraform is never given the value, because a
# Terraform-managed secret is a plaintext secret in the state file - `terraform show`,
# `terraform state pull` and the S3 object all carry it forever, and the state bucket has
# a wider read audience than the parameter ever would. The deploy script writes the
# SecureString with `aws ssm put-parameter` before `terraform apply`; this module grants
# the function permission to read it and nothing more.
#
# THERE IS NOW A `url_authorization_type` VARIABLE, AND THAT IS A REVERSAL.
#
# This file used to say, here, that no such variable existed because "a variable that can
# turn the authentication off is a variable somebody turns off at 02:00 to make a curl
# work". The reasoning was sound and the premise was wrong: it assumed a CloudFront
# distribution would front the function, and AWS refuses to create one on this account
# (403 AccessDenied, "Your account must be verified before you can add new CloudFront
# resources", RequestID 3e63e30d-8c5b-441b-a01b-b70085eba504 - docs/deploy/RUNBOOK.md:26,
# reproduced from a bare `aws cloudfront create-distribution`). An `AWS_IAM` Function URL
# with no distribution to grant to is not a hardened demo; it is a URL that answers 403 to
# everyone including the judges. Decision D1, docs/leads/ship-final.md sec 1.4.
#
# The variable admits exactly two values and its validation names both. It is a decision
# recorded in HCL, not a knob: the `NONE` shape's cost ceiling is the ACCOUNT's concurrency
# quota - see `account_concurrency_ceiling`, measured at 10 - and NOT
# `reserved_concurrent_executions`, which this file used to name here and which this
# account refuses at any positive value. The README states the exposure plainly rather than
# calling a public URL private.

variable "function_name" {
  description = <<-EOT
    Name of the demo API function. Also fixes the log group (`/aws/lambda/<name>`), the
    alarm names and the dashboard name, so it is the one string that has to be unique in
    the account. The `mainline-demo-` prefix is a convention this repository relies on:
    the AWS account holds four unrelated projects and the teardown script filters on the
    prefix and on `project=mainline` before it deletes anything.
  EOT
  type        = string
  default     = "mainline-demo-api"

  validation {
    condition     = can(regex("^[A-Za-z0-9_-]{1,64}$", var.function_name))
    error_message = "function_name must be 1-64 characters of [A-Za-z0-9_-]; that is the Lambda name grammar."
  }
}

variable "url_authorization_type" {
  description = <<-EOT
    Authorisation on the Lambda Function URL. Exactly two values are legal.

      NONE     (default) The URL is PUBLIC and IS the demo hostname:
               `https://<id>.lambda-url.<region>.on.aws`, HTTPS on an AWS-issued
               certificate, no ACM, no hosted zone, no account verification. The console
               SPA, the signed evidence bundle and `/v1/*` all answer on it, so there is
               one origin, no CORS and one URL to put in the submission form. No
               `aws_lambda_permission` for `cloudfront.amazonaws.com` is created - the
               resource is `count = 0`, absent from the plan, not present-and-inert.

      AWS_IAM  The pre-D1 shape. An unsigned request gets `403 Forbidden` with an empty
               body, and the single `lambda:InvokeFunctionUrl` grant is created with
               `cloudfront_distribution_arn` as its SourceArn. Requires that ARN to be
               non-empty; a `lifecycle.precondition` on the grant refuses an empty one,
               because a grant to `cloudfront.amazonaws.com` with no SourceArn is readable
               as "any CloudFront distribution in any account may invoke this URL".

    WHY THE DEFAULT IS `NONE`. AWS holds this account from creating new CloudFront
    resources (403 AccessDenied, RequestID 3e63e30d-8c5b-441b-a01b-b70085eba504), a hold
    only AWS Support can lift. `AWS_IAM` without a distribution is a URL that refuses
    everyone. See decision D1, docs/leads/ship-final.md sec 1.4.

    WHAT BOUNDS THE `NONE` SHAPE, honestly: not authentication, and not as many things as
    this paragraph used to list. It named four bounds; exactly one of them bounds spend.

      THE ACCOUNT CONCURRENCY CEILING - REAL, and the only one. 10, measured in both
      regions (see `account_concurrency_ceiling`). It caps concurrency, hence request rate,
      hence egress, hence the bill. It is also `Adjustable: true`, so it is a bound nobody
      here chose and anybody here could remove.

      `reserved_concurrent_executions` - NOT A BOUND. It defaulted to 20 above a ceiling of
      10, so it never bound anything, and every positive value is refused at apply on this
      account. It now defaults to -1. Its `0` setting IS a real stop, but as a kill switch
      run deliberately, not as a standing cap.

      The `-concurrency` alarm - NOT A BOUND, by construction. An alarm reports; it does
      not stop. It defaulted to 20 against a metric that tops out at 10, so it could not
      even report; it is now 8, below the ceiling, which makes it a working tripwire and
      still not a bound.

      The handler's single rolled-back transaction - REAL, but for DATABASE STATE, not
      spend. The flood target is the static tree, which never opens a connection.

      The CockroachDB Basic spend limit - REAL, and bounds the DATABASE side only. Same
      reason: it is not in the path of the bytes.

    The honest one-line version is that a public URL on this account is bounded by an AWS
    default. `docs/deploy/COST-BOUND.md` carries the arithmetic and the menu of levers that
    would add a second bound. If the CloudFront hold lifts, set this to `AWS_IAM`, pass the
    distribution ARN, and re-apply; nothing else in this module changes.
  EOT
  type        = string
  default     = "NONE"

  validation {
    condition     = contains(["NONE", "AWS_IAM"], var.url_authorization_type)
    error_message = "url_authorization_type must be exactly \"NONE\" (public Function URL, which under decision D1 is the demo hostname) or \"AWS_IAM\" (403 to unsigned callers, plus the single lambda:InvokeFunctionUrl grant scoped to cloudfront_distribution_arn). No other value is accepted, and the empty string is not a synonym for either."
  }
}

variable "package_path" {
  description = <<-EOT
    Path to the deployment zip built by `scripts/deploy/build_lambda.{sh,ps1}`, e.g.
    `../../out/lambda/mainline-demo-api-arm64.zip`. Its ARCHITECTURE MUST MATCH
    `var.architecture`: a zip carrying aarch64 `.so` files on an `x86_64` function
    imports psycopg and dies with `ELFCLASS` on the first invocation, and Lambda cannot
    detect that at deploy time. The build script prints the architecture it built for and
    writes it into `<zip>.json` beside the artefact.

    The file must exist when `terraform plan` runs, because `source_code_hash` is
    computed from it with `filebase64sha256`.
  EOT
  type        = string

  validation {
    condition     = can(regex("\\.zip$", var.package_path))
    error_message = "package_path must point at a .zip file."
  }
}

variable "architecture" {
  description = <<-EOT
    `arm64` (Graviton2) or `x86_64`. arm64 is the default: it is roughly 20 % cheaper per
    GB-second, and psycopg-binary 3.3.4 publishes a cp313 aarch64 wheel - though under the
    `manylinux_2_28_aarch64` tag rather than `manylinux2014_aarch64`, which is why the
    build script carries a per-architecture tag table instead of one string. Both
    architectures were unzipped inside `public.ecr.aws/lambda/python:3.13` and imported
    psycopg successfully; the transcripts are in this module's README.
  EOT
  type        = string
  default     = "arm64"

  validation {
    condition     = contains(["arm64", "x86_64"], var.architecture)
    error_message = "architecture must be arm64 or x86_64."
  }
}

variable "dsn_parameter_name" {
  description = <<-EOT
    NAME - never the value - of the SSM SecureString holding the CockroachDB Cloud DSN,
    e.g. `/mainline/demo/dsn`. Written out of band by
    `aws ssm put-parameter --type SecureString`; NOT a resource in this module.

    The execution role is granted `ssm:GetParameter` on exactly the ARN derived from this
    name, and `kms:Decrypt` conditioned on that same ARN as the encryption context. A
    leading slash is optional and is normalised.
  EOT
  type        = string
  default     = "/mainline/demo/dsn"

  validation {
    condition     = can(regex("^/?[A-Za-z0-9_.-]+(/[A-Za-z0-9_.-]+)*$", var.dsn_parameter_name))
    error_message = "dsn_parameter_name must be a valid SSM parameter name: slash-separated segments of [A-Za-z0-9_.-], no wildcard, no trailing slash."
  }

  validation {
    # `*` or `?` here would widen the IAM grant from one parameter to a family of them,
    # silently, from a variable that reads like a name.
    condition     = !can(regex("[*?]", var.dsn_parameter_name))
    error_message = "dsn_parameter_name must not contain a wildcard: the whole point of this variable is that the grant names ONE parameter."
  }
}

variable "ssm_kms_key_arn" {
  description = <<-EOT
    ARN of the KMS key the SecureString is encrypted under. Empty (the default) means
    "the account's AWS-managed `aws/ssm` key", whose ARN this module deliberately does NOT
    look up.

    MEASURED 2026-08-10, in the deploy account (`aws sts get-caller-identity`; the account
    id is not written down here - decision D2, docs/leads/ship-final.md sec 1.6 - and the
    unelided transcript is quoted once, as evidence, in this module's README):
      aws kms list-aliases --region ap-southeast-1 --query "Aliases[?AliasName=='alias/aws/ssm']"
      -> [{"AliasName": "alias/aws/ssm", "AliasArn": "arn:aws:kms:ap-southeast-1:...:alias/aws/ssm"}]
    with NO `TargetKeyId`. The AWS-managed key does not exist until the first SecureString
    is written, so `data "aws_kms_alias"` would fail the plan on a clean region - a
    chicken-and-egg in the one place a deploy cannot afford one. IAM also refuses an alias
    ARN in a `Resource` element, so the alias could not be named directly even if it
    resolved.

    The grant is therefore scoped by CONDITION rather than by resource: see
    `restrict_kms_to_parameter` and the README. Set this once the key exists to narrow the
    resource as well.
  EOT
  type        = string
  default     = ""

  validation {
    condition     = var.ssm_kms_key_arn == "" || can(regex("^arn:aws[a-z-]*:kms:[a-z0-9-]+:[0-9]{12}:key/", var.ssm_kms_key_arn))
    error_message = "ssm_kms_key_arn must be empty or a KMS KEY arn (arn:aws:kms:<region>:<account>:key/<id>). An alias ARN is not accepted by IAM in a Resource element."
  }
}

variable "restrict_kms_to_parameter" {
  description = <<-EOT
    Add `kms:EncryptionContext:PARAMETER_ARN = <the one parameter ARN>` to the
    `kms:Decrypt` grant. SSM sets that encryption context on every SecureString, so the
    condition reduces the grant to "decrypt the ciphertext of this one parameter" - which
    is TIGHTER than naming the `aws/ssm` key, since that key protects every SecureString
    in the account.

    Left as a variable, and only for this reason: the condition has been read from the
    policy but never exercised against a live `Decrypt`, because this module has been
    planned and not applied. If a cold start fails with `AccessDeniedException` on
    `kms:Decrypt` - which `/v1/health` surfaces as `dsn_unavailable` - setting this to
    `false` falls back to the `kms:ViaService` condition alone, which is still scoped to
    SSM-mediated decrypts in this region. It is not a switch that turns the control off.
  EOT
  type        = bool
  default     = true
}

variable "demo_database" {
  description = <<-EOT
    The CockroachDB database the demo reads, published as `$MAINLINE_DEMO_DATABASE`.
    `scripts/deploy/cloud_chain.py` sets `DEFAULT_DATABASE = "mainline_demo"`, and this
    default matches it.

    HONEST NOTE: the handler does not read this variable. The database is carried by the
    DSN. It is set so that `aws lambda get-function-configuration` states which database
    this function is SUPPOSED to be pointed at, so a mismatch is discoverable without
    decrypting the DSN. `/v1/health` reports the database it actually connected to, and
    the two being different is a finding.
  EOT
  type        = string
  default     = "mainline_demo"

  validation {
    condition     = can(regex("^[a-z_][a-z0-9_]*$", var.demo_database))
    error_message = "demo_database must be a lower_snake_case SQL identifier."
  }
}

variable "scenario_permit_id" {
  description = <<-EOT
    The permit the three demo beats drive. The default is THE ROW THAT IS ACTUALLY
    SEEDED, read back out of the live Cloud database rather than derived:

      SELECT permit_id::string, state::string, open_blocking, head_seq, gate_epoch
        FROM mainline.permit ORDER BY permit_id;
      -> exactly one row
         dec0de00-0006-4000-8000-000000000001 | dispositioned | 1 | 2 | 1

    read read-only against `mainline-dev` / `mainline_demo` (aws-ap-southeast-1) on
    2026-08-12. `scripts/deploy/seed_demo.py:104` fixes that id as PERMIT_ID and
    `verticals/mainline/db/seeds/demo/demo_permit.sql` is what inserts it.

    THIS DEFAULT USED TO BE `077a6fdd-2167-559c-b2ff-8e3c8352504d`, which is
    `mainline_demo_api.scenario`'s uuid5 fallback - `uuid5(uuid5(NAMESPACE_URL,
    "https://mainline.trappoint.org/demo/2026-08"), "permit")`, `scenario.py:77`. That
    derivation is committed in the module's `EXPECTED` table but NOTHING HAS EVER SEEDED
    IT: the query above returns no such row. Deploying with it makes every gate-run
    answer `422 demo_history_not_seeded`. The uuid5 value stays where it belongs, as
    `scenario.py`'s in-code fallback for a database nobody has told it about; it is not
    what this deployment points at.

    Published under TWO names, on purpose:
      MAINLINE_SCENARIO_PERMIT_ID  the name this module's brief specifies
      MAINLINE_DEMO_PERMIT_ID      the name `scenario.from_env` actually reads
                                   (ENV_PREFIX "MAINLINE_DEMO_" + "PERMIT_ID")
    Setting only the first would leave the override silently inert. See the README.
  EOT
  type        = string
  default     = "dec0de00-0006-4000-8000-000000000001"

  validation {
    condition     = can(regex("^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", var.scenario_permit_id))
    error_message = "scenario_permit_id must be a lowercase hyphenated UUID; scenario.py parses it with uuid.UUID and refuses anything else with ScenarioNotSeeded."
  }
}

variable "log_level" {
  description = <<-EOT
    Application log level, published as `$LOG_LEVEL` and wired into the function's
    `logging_config.application_log_level`, which is what actually filters records in the
    python3.13 managed runtime.
  EOT
  type        = string
  default     = "INFO"

  validation {
    condition     = contains(["TRACE", "DEBUG", "INFO", "WARN", "ERROR", "FATAL"], var.log_level)
    error_message = "log_level must be one of TRACE, DEBUG, INFO, WARN, ERROR, FATAL - the set Lambda's application_log_level accepts."
  }
}

variable "cloudfront_distribution_arn" {
  description = <<-EOT
    ARN of the CloudFront distribution allowed to invoke the Function URL, from the
    `demo-site` module. This is the `SourceArn` on the one `lambda:InvokeFunctionUrl`
    grant, so it is the difference between "invocable by our distribution" and "invocable
    by any CloudFront distribution in the world, including one an attacker creates".

    EMPTY IS THE DEFAULT AND IT IS THE NORMAL CASE under decision D1: with
    `url_authorization_type = "NONE"` there is no grant to scope, so there is nothing for
    this to be. It stopped being a required variable when CloudFront stopped being a
    dependency; a required input for a resource that is not created is a caller forced to
    invent a value.

    It becomes REQUIRED again the moment `url_authorization_type = "AWS_IAM"`, and that is
    enforced - by a `lifecycle.precondition` on the grant rather than by a cross-variable
    `validation` block, because cross-variable validation needs Terraform >= 1.9 and this
    module's floor is 1.6.

    It may legitimately be UNKNOWN at plan time (the caller wires it from
    `module.site.distribution_arn`, which does not exist until the distribution does),
    which is why nothing in this module derives a `count` or a `for_each` from it. See
    `local.create_cloudfront_invoke_grant` in main.tf.
  EOT
  type        = string
  default     = ""

  validation {
    condition     = var.cloudfront_distribution_arn == "" || can(regex("^arn:aws[a-z-]*:cloudfront::[0-9]{12}:distribution/[A-Z0-9]+$", var.cloudfront_distribution_arn))
    error_message = "cloudfront_distribution_arn must be empty (the D1 default: no CloudFront, no grant) or look like arn:aws:cloudfront::<account>:distribution/<ID>."
  }
}

variable "web_root" {
  description = <<-EOT
    Absolute path, INSIDE the deployment package, of the static tree the handler serves at
    `/` and `/assets/*`. Published as `$MAINLINE_WEB_ROOT`, which
    `mainline_demo_api.app` reads.

    `/var/task/web` is the default and it is the composition of two facts, neither of which
    is this module's to choose: Lambda unpacks the deployment package at `/var/task`
    (`$LAMBDA_TASK_ROOT`), and the build script places the console's `dist/` at `web/` in
    the package root. Under D1 this function is the whole origin - console, evidence bundle
    and `/v1/*` on one hostname - so if this path is wrong the judges get a 404 at `/` and
    a perfectly healthy `/v1/health`.

    Stated as a variable rather than a constant so the agreement between the handler and
    the package layout is one value in one place, and so a caller who builds the zip a
    different way can say so instead of patching the module.
  EOT
  type        = string
  default     = "/var/task/web"

  validation {
    condition     = startswith(var.web_root, "/") && !endswith(var.web_root, "/")
    error_message = "web_root must be an absolute POSIX path with no trailing slash, e.g. /var/task/web. Lambda's filesystem is Linux regardless of where terraform runs, and a trailing slash produces a double separator in the handler's path join."
  }
}

variable "memory_size" {
  description = <<-EOT
    MB. 512 is the plan's figure and the basis of its cost line: 512 MB x 300 ms x 10 000
    requests = 1 536 GB-s against Lambda's perpetual 400 000 GB-s/month free tier. CPU is
    allocated in proportion to memory, so lowering this makes cold starts worse without
    making the bill smaller - the free tier is not the binding constraint.
  EOT
  type        = number
  default     = 512

  validation {
    condition     = var.memory_size >= 128 && var.memory_size <= 10240 && var.memory_size % 64 == 0
    error_message = "memory_size must be 128-10240 MB in 64 MB steps."
  }
}

variable "timeout" {
  description = <<-EOT
    Seconds. 15 s, and the number is arithmetic rather than a round figure.

    THE COLD PATH, ADDED UP. A cold invocation pays, in order: the python3.13 runtime's own
    init; `import psycopg` plus `psycopg_binary` (a 6.7 MB C extension being dlopen'd);
    one SigV4 `ssm:GetParameter` plus the KMS decrypt behind it; the TLS+pgwire connect to
    CockroachDB Cloud; and then the four-beat gate transaction, which is six round trips
    inside one SAVEPOINT/ROLLBACK envelope.

    THE ONE NUMBER MEASURED RATHER THAN ESTIMATED: connect+query from THIS machine to the
    Singapore cluster is **2.91 s** (docs/leads/ship-final.md sec 1.1). That figure is a
    ceiling, not the Lambda figure - it crosses the public internet from Australia, where
    the function is in-region and pays single-digit milliseconds per round trip. It is
    quoted because it is the only connect latency anyone has actually observed against
    this cluster, and because a budget built on the worst number available is the one that
    survives being wrong.

    So: 2.91 s of worst-case connect, a cold psycopg import that is hundreds of
    milliseconds and not tens, six in-region round trips, and roughly 5 s of margin for the
    tail nobody has measured yet - 15 s. It is also 10 s BELOW the previous default of 25 s,
    which was sized against CloudFront's 30 s origin read timeout; under D1 there is no
    CloudFront, and a demo that hangs for 25 s before failing is a demo a judge has already
    closed the tab on. `duration_p99_threshold_ms` (default 12 000 ms) is the warning that
    this ceiling is being approached, and a `lifecycle.precondition` on that alarm refuses
    any threshold at or above `timeout`.

    The 29 s ceiling in the validation stays. It is not needed by the `NONE` shape - a
    Function URL will wait far longer - but it keeps every configuration of this module
    valid for `AWS_IAM` + CloudFront, whose 30 s origin read timeout would otherwise turn
    this API's JSON problem document into CloudFront's 504 HTML.
  EOT
  type        = number
  default     = 15

  validation {
    condition     = var.timeout >= 1 && var.timeout <= 29
    error_message = "timeout must be 1-29 s: above 29 s the function outlives CloudFront's 30 s origin read timeout in the AWS_IAM shape, and the caller gets a 504 with no diagnosis in it."
  }
}

variable "reserved_concurrent_executions" {
  description = <<-EOT
    Per-function reserved concurrency. `-1` is the default, and it means "reserve nothing,
    draw from the account pool".

    THIS DEFAULT USED TO BE 20, AND THE PARAGRAPH THAT JUSTIFIED IT DESCRIBED A DIFFERENT
    ACCOUNT. It said the reservation took 20 "of the account's 1 000 unreserved
    executions" and called that 2 %. Measured 2026-08-13 under `AWS_PROFILE=mainline-dev`,
    in both regions this project touches:

      aws lambda get-account-settings --region ap-southeast-1
        AccountLimit.ConcurrentExecutions            10
        AccountLimit.UnreservedConcurrentExecutions  10
      aws lambda get-account-settings --region ap-southeast-2
        AccountLimit.ConcurrentExecutions            10
        AccountLimit.UnreservedConcurrentExecutions  10
      aws service-quotas get-service-quota --service-code lambda \
          --quota-code L-B99A9384 --region ap-southeast-1   (and --region ap-southeast-2)
        QuotaName "Concurrent executions"   Value 10.0   Adjustable true

    The account ceiling is TEN, not 1 000. The reservation was not 2 % of the account, it
    was 200 % of it, and that one false sentence is why an unappliable default survived
    review: it read as a small, prudent number because it was measured against an account
    nobody here has.

    WHAT THE CEILING OF 10 MEANS FOR THIS VARIABLE, in three parts.

    (1) EVERY POSITIVE VALUE IS REFUSED OUTRIGHT ON THIS ACCOUNT. `PutFunctionConcurrency`
        rejects a reservation that would drop the account's UNRESERVED concurrency below
        its documented minimum. Unreserved here is already 10, so there is no positive
        reservation this account can accept - not 20, not 5, not 1. The apply does not
        degrade, it fails: `PutFunctionConcurrency` is the sixth of eleven API calls in
        this apply, so five resources exist by the time it is refused.

    (2) `0` IS STILL ACCEPTED, AND IT IS THE DOCUMENTED WAY TO STOP THE FUNCTION. Reserving
        0 decreases nothing, so it does not trip the minimum that refuses every positive
        value; it throttles every invocation before the handler runs. That makes 0 the kill
        switch this account can still use. DOCUMENTED BEHAVIOUR, NOT MEASURED HERE:
        confirming it requires a mutating call, and this module has been planned and never
        applied. It is labelled that way on purpose.

    (3) `-1` DOES NOT RAISE THE CEILING. `min(20, 10) = 10`. The account cap already held
        this function at 10 concurrent executions, BELOW the 20 the module asked to
        reserve, so the reservation was never the binding constraint - it was an
        unappliable request sitting in front of a bound that does not need it. Moving to
        -1 removes the request and leaves the identical physical bound standing. It does
        not add one request per second of exposure, which is why `docs/deploy/COST-BOUND.md`
        computes the worst case at concurrency 10 either way. The ceiling is
        `Adjustable: true`, and every dollar of that worst case is LINEAR in it - raising
        `L-B99A9384` multiplies the bill by the same factor, and there is no second bound
        behind it on an `authorization_type = NONE` URL.

    THE ONE THING THIS VARIABLE STILL BUYS THE ALARMS, and it is a cost of -1, not a
    benefit: Lambda emits the per-function `ConcurrentExecutions` metric DEPENDABLY only
    for functions that HAVE reserved concurrency. At -1 the per-function metric may not be
    published at all, so a `-concurrency` alarm dimensioned on `FunctionName` can sit in
    INSUFFICIENT_DATA and prove nothing. That is a real consequence of this default and it
    is stated here rather than discovered in the console; the alarm is moved onto the
    account-level metric because of it. See `concurrency_alarm_threshold` and
    `account_concurrency_ceiling` below, and `aws_cloudwatch_metric_alarm.concurrency` in
    main.tf.
  EOT
  type        = number
  default     = -1

  validation {
    condition     = var.reserved_concurrent_executions == -1 || (var.reserved_concurrent_executions >= 0 && var.reserved_concurrent_executions <= 1000)
    error_message = "reserved_concurrent_executions must be -1 (unreserved) or 0-1000. That is the Lambda API's grammar, not this account's: on an account whose measured ceiling is 10 (see account_concurrency_ceiling) every POSITIVE value is refused at apply by PutFunctionConcurrency, so -1 and 0 are the only two that apply, and 0 stops the function entirely."
  }
}

variable "log_retention_days" {
  description = <<-EOT
    CloudWatch Logs retention. 7 days: long enough to debug a judging session, short
    enough that storage never leaves the free tier, and - the actual reason the log group
    is a resource at all - Lambda's own auto-created group has NO expiry and is not
    managed by anything, so it survives `terraform destroy` and accrues forever.
  EOT
  type        = number
  default     = 7

  validation {
    condition = contains(
      [1, 3, 5, 7, 14, 30, 60, 90, 120, 150, 180, 365, 400, 545, 731, 1096, 1827, 2192, 2557, 2922, 3288, 3653],
      var.log_retention_days
    )
    error_message = "log_retention_days must be one of CloudWatch's accepted values (1, 3, 5, 7, 14, 30, ... 3653). `0` (never expire) is not offered."
  }
}

variable "duration_p99_threshold_ms" {
  description = <<-EOT
    p99 duration, in ms, above which the demo API is treated as approaching its timeout.
    Default 12 000 = 80 % of the 15 s default `timeout`.

    IT MOVED WITH THE TIMEOUT, AND IT HAD TO. The old default was 20 000 ms against a 25 s
    timeout. Dropping `timeout` to 15 s under D1 without touching this would have left the
    threshold ABOVE the ceiling - Lambda terminates the invocation at `timeout` and the
    Duration datapoint is capped there, so a 20 000 ms alarm on a 15 000 ms ceiling can
    never breach. That is the exact shape of a control that looks present and is not, so
    `aws_cloudwatch_metric_alarm.duration_p99` carries a plan-time `lifecycle.precondition`
    refusing any threshold that is not strictly below `timeout * 1000`.
  EOT
  type        = number
  default     = 12000

  validation {
    condition     = var.duration_p99_threshold_ms > 0 && var.duration_p99_threshold_ms <= 900000
    error_message = "duration_p99_threshold_ms must be between 1 and 900000. It must ALSO be strictly below timeout * 1000, which is checked at plan time by a precondition on the alarm rather than here, because a validation block cannot read a second variable before Terraform 1.9 and this module's floor is 1.6."
  }
}

variable "concurrency_alarm_threshold" {
  description = <<-EOT
    Concurrent executions above which the demo is assumed to be under abuse rather than
    under judging. Default 8.

    IT WAS 20, AGAINST A METRIC WHOSE PHYSICAL CEILING IS 10. `ConcurrentExecutions` cannot
    exceed the account's concurrency quota, measured at 10 in both ap-southeast-1 and
    ap-southeast-2 on 2026-08-13 (see `account_concurrency_ceiling` for the two commands).
    An alarm at 20 on a metric that tops out at 10 does not fire late; it CANNOT FIRE. It
    is a control that looks present and is not - a red line on the dashboard, a green alarm
    in `describe-alarms`, and nothing whatsoever between a public Function URL and the
    bill.

    THIS IS THE SAME DEFECT `duration_p99_threshold_ms` ALREADY HAS A PRECONDITION AGAINST,
    ONE RESOURCE HIGHER IN main.tf. `aws_cloudwatch_metric_alarm.duration_p99` carries a
    `lifecycle.precondition` refusing any threshold that is not strictly below
    `timeout * 1000`, because Lambda caps the Duration datapoint at the timeout and an
    alarm above it can never breach. The reasoning transfers exactly: Lambda caps
    ConcurrentExecutions at the account ceiling, and an alarm at or above it can never
    breach. The idiom was invented in this module and then not applied to its immediate
    neighbour. `aws_cloudwatch_metric_alarm.concurrency` now carries the mirroring
    precondition, comparing this variable against `account_concurrency_ceiling`.

    WHY 8 AND NOT 9 OR 10. It must be STRICTLY BELOW the ceiling or it is not a tripwire,
    and it needs enough headroom that the breach is visible before saturation rather than
    at it: 8 of 10 is 80 % of the account's entire Lambda capacity in the region, which no
    judging session reaches. A judging session is a handful of browsers making four
    requests each. If this ever fires during judging, the correct reading is not "raise the
    threshold" - it is that something is holding invocations open, and the threshold is
    doing its job.

    RAISING IT IS A PLAN-TIME ERROR, NOT A RUNTIME SURPRISE. Setting this to 10 or above is
    refused by the precondition on the alarm with the ceiling named in the message. A
    caller genuinely on an account with a higher ceiling raises `account_concurrency_ceiling`
    to their measured value and this threshold with it; nobody edits the module.
  EOT
  type        = number
  default     = 8

  validation {
    condition     = var.concurrency_alarm_threshold >= 1
    error_message = "concurrency_alarm_threshold must be at least 1. It must ALSO be strictly below account_concurrency_ceiling, which is checked at plan time by a precondition on aws_cloudwatch_metric_alarm.concurrency rather than here, because a validation block cannot read a second variable before Terraform 1.9 and this module's floor is 1.6 - the same reason duration_p99_threshold_ms is checked against timeout there and not here."
  }
}

variable "account_concurrency_ceiling" {
  description = <<-EOT
    The AWS Lambda concurrency ceiling of the account this module is applied into. Default
    10, because that is what this account measures. It is the maximum value the
    `ConcurrentExecutions` metric can physically take, and therefore the bound every
    concurrency threshold in this module has to sit strictly below.

    MEASURED 2026-08-13 under `AWS_PROFILE=mainline-dev`, two commands, both regions this
    project touches, all four answers identical:

      aws lambda get-account-settings --region ap-southeast-1
        AccountLimit.ConcurrentExecutions            10
        AccountLimit.UnreservedConcurrentExecutions  10
      aws lambda get-account-settings --region ap-southeast-2
        AccountLimit.ConcurrentExecutions            10
        AccountLimit.UnreservedConcurrentExecutions  10
      aws service-quotas get-service-quota --service-code lambda \
          --quota-code L-B99A9384 --region ap-southeast-1
        QuotaName "Concurrent executions"   Value 10.0   Adjustable true
      aws service-quotas get-service-quota --service-code lambda \
          --quota-code L-B99A9384 --region ap-southeast-2
        QuotaName "Concurrent executions"   Value 10.0   Adjustable true

    Ten is the default account limit for a new AWS account that has not been through a
    quota increase; the more familiar 1 000 is what an aged account has. Assuming 1 000 is
    exactly the mistake this variable exists to make impossible to repeat silently.

    WHY IT IS A VARIABLE AND NOT A LOCAL. A `lifecycle.precondition` is only useful if both
    sides are known at PLAN time. A `data` source lookup of the live quota would be known
    only at apply on some code paths, would need `servicequotas:GetServiceQuota` in the
    plan role, and would make the plan artefact depend on a live API call - and this
    repository's central claim is that its plan is byte-reproducible. A plain number,
    measured once and written down with the commands that produced it, is checkable by
    reading and re-runnable by anyone with read-only credentials.

    THE CONTRACT: `aws_cloudwatch_metric_alarm.concurrency` in main.tf reads this variable
    in its `lifecycle.precondition` and refuses any `concurrency_alarm_threshold` that is
    not strictly below it, with the ceiling named in the error message. That precondition
    is the whole reason this variable exists.

    A CALLER ON A DIFFERENT ACCOUNT SETS THIS HERE RATHER THAN PATCHING THE MODULE. Run the
    two commands above against your own account and pass what they return. Raising this
    number does not raise any limit - it only tells the module what your limit already is,
    so the preconditions compare against the truth. And note which direction the money runs:
    `L-B99A9384` is `Adjustable: true`, the demo's Function URL is
    `authorization_type = NONE`, and the 30-day worst case in `docs/deploy/COST-BOUND.md`
    is LINEAR in this number. A quota increase multiplies the worst case by the same
    factor. Read that document before requesting one.
  EOT
  type        = number
  default     = 10

  validation {
    condition     = var.account_concurrency_ceiling >= 1
    error_message = "account_concurrency_ceiling must be at least 1. It is a measured account quota (aws lambda get-account-settings -> AccountLimit.ConcurrentExecutions, or aws service-quotas get-service-quota --service-code lambda --quota-code L-B99A9384), not a limit this module sets; a ceiling below 1 would describe an account on which no Lambda function can run at all."
  }
}

variable "alarm_actions" {
  description = <<-EOT
    SNS topic ARNs notified on ALARM. Empty by default and that is deliberate: an SNS
    topic with an email subscription needs a confirmed subscriber to be worth anything,
    and an unconfirmed one is a control that looks present and is not. With no actions the
    alarms still evaluate, still show state in the console and on the dashboard, and are
    still readable by `aws cloudwatch describe-alarms` - which is what the `demo-health`
    cron reads. The first ten alarms are free either way.
  EOT
  type        = list(string)
  default     = []
}

variable "create_dashboard" {
  description = "Create the CloudWatch dashboard. The first three dashboards in an account are free; set false if the account already has three."
  type        = bool
  default     = true
}

variable "extra_environment" {
  description = <<-EOT
    Additional environment variables merged into the function's environment. For the
    demo's optional switches - `MAINLINE_DEMO_ALLOW_MUTATION`, `MAINLINE_DEBUG`, the other
    `MAINLINE_DEMO_*` scenario overrides - without giving each of them a variable here.

    It cannot be used to smuggle the DSN past the "secrets are not in Terraform state"
    rule: `MAINLINE_DSN` is rejected by the validation below, as are Lambda's reserved
    names and the four keys this module sets itself.
  EOT
  type        = map(string)
  default     = {}

  validation {
    condition = length(setintersection(keys(var.extra_environment), [
      "MAINLINE_DSN",
      "MAINLINE_DSN_PARAM",
      "MAINLINE_DEMO_DATABASE",
      "MAINLINE_SCENARIO_PERMIT_ID",
      "MAINLINE_DEMO_PERMIT_ID",
      "MAINLINE_WEB_ROOT",
      "LOG_LEVEL",
    ])) == 0
    error_message = "extra_environment must not set MAINLINE_DSN (the DSN is never in Terraform state - use dsn_parameter_name) nor any key this module already sets: MAINLINE_DSN_PARAM, MAINLINE_DEMO_DATABASE, MAINLINE_SCENARIO_PERMIT_ID, MAINLINE_DEMO_PERMIT_ID, MAINLINE_WEB_ROOT (use var.web_root), LOG_LEVEL."
  }

  validation {
    condition = length(setintersection(keys(var.extra_environment), [
      "AWS_REGION", "AWS_DEFAULT_REGION", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY",
      "AWS_SESSION_TOKEN", "AWS_LAMBDA_FUNCTION_NAME", "AWS_LAMBDA_FUNCTION_VERSION",
      "AWS_LAMBDA_FUNCTION_MEMORY_SIZE", "AWS_LAMBDA_LOG_GROUP_NAME",
      "AWS_LAMBDA_LOG_STREAM_NAME", "AWS_LAMBDA_RUNTIME_API", "AWS_EXECUTION_ENV",
      "LAMBDA_TASK_ROOT", "LAMBDA_RUNTIME_DIR", "_HANDLER", "TZ",
    ])) == 0
    error_message = "extra_environment must not contain a Lambda reserved environment variable; the CreateFunction API rejects those, and it does so after Terraform has already reported a plan that looked fine."
  }
}

variable "tags" {
  description = <<-EOT
    Extra tags. `project=mainline`, `component=demo-api` and `managed_by=terraform` are
    added by the module and cannot be overridden - the teardown script filters on
    `project=mainline` before it deletes anything, in an account that holds four unrelated
    projects, so a caller that could overwrite that tag could arm the teardown against
    somebody else's bucket.
  EOT
  type        = map(string)
  default     = {}
}
