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
# There is also deliberately NO `function_url_authorization_type` variable. A public
# Function URL is a public unauthenticated database gateway and an unbounded bill, and a
# variable that can turn the authentication off is a variable somebody turns off at 02:00
# to make a curl work.

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

    MEASURED 2026-08-10, account 022950218246:
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
    The permit the three demo beats drive. Default is the value
    `mainline_demo_api.scenario` derives - `uuid5(uuid5(NAMESPACE_URL,
    "https://mainline.trappoint.org/demo/2026-08"), "permit")` - which is committed in
    that module's `EXPECTED` table and is what `scripts/deploy/seed_demo.py` seeds.

    Published under TWO names, on purpose:
      MAINLINE_SCENARIO_PERMIT_ID  the name this module's brief specifies
      MAINLINE_DEMO_PERMIT_ID      the name `scenario.from_env` actually reads
                                   (ENV_PREFIX "MAINLINE_DEMO_" + "PERMIT_ID")
    Setting only the first would leave the override silently inert. See the README.
  EOT
  type        = string
  default     = "077a6fdd-2167-559c-b2ff-8e3c8352504d"

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
    `w5-tf-site` module. This is the `SourceArn` on the one `lambda:InvokeFunctionUrl`
    grant, so it is the difference between "invocable by our distribution" and "invocable
    by any CloudFront distribution in the world, including one an attacker creates".
  EOT
  type        = string

  validation {
    condition     = can(regex("^arn:aws[a-z-]*:cloudfront::[0-9]{12}:distribution/[A-Z0-9]+$", var.cloudfront_distribution_arn))
    error_message = "cloudfront_distribution_arn must look like arn:aws:cloudfront::<account>:distribution/<ID>."
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
    Seconds. 25 s, chosen against CloudFront's 30 s origin read timeout: the function must
    fail before the distribution gives up, so the judge sees this API's JSON problem
    document rather than CloudFront's 504 HTML. The `duration_p99_threshold_ms` alarm at
    20 000 ms is the warning that this ceiling is being approached.
  EOT
  type        = number
  default     = 25

  validation {
    condition     = var.timeout >= 1 && var.timeout <= 29
    error_message = "timeout must be 1-29 s: above 29 s the function outlives CloudFront's 30 s origin read timeout and the caller gets a 504 with no diagnosis in it."
  }
}

variable "reserved_concurrent_executions" {
  description = <<-EOT
    Hard concurrency cap, and the only control here that actually STOPS a bill rather than
    reporting one. 20 is the default and matches `concurrency_alarm_threshold`, so the
    tripwire fires exactly when the cap starts biting.

    Two consequences worth knowing before changing it. (1) It reserves 20 of the account's
    1 000 unreserved executions, which the four unrelated projects in this account share;
    2 % is the price of a demo that cannot be turned into a bill. (2) Lambda emits the
    per-function `ConcurrentExecutions` metric reliably for functions that HAVE reserved
    concurrency, so setting this to -1 (unreserved) is also what leaves the concurrency
    alarm sitting in INSUFFICIENT_DATA.
  EOT
  type        = number
  default     = 20

  validation {
    condition     = var.reserved_concurrent_executions == -1 || (var.reserved_concurrent_executions >= 0 && var.reserved_concurrent_executions <= 1000)
    error_message = "reserved_concurrent_executions must be -1 (unreserved) or 0-1000. Note that 0 disables the function entirely."
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
  description = "p99 duration, in ms, above which the demo API is treated as approaching its 25 s timeout. Default 20 000."
  type        = number
  default     = 20000

  validation {
    condition     = var.duration_p99_threshold_ms > 0 && var.duration_p99_threshold_ms <= 900000
    error_message = "duration_p99_threshold_ms must be between 1 and 900000."
  }
}

variable "concurrency_alarm_threshold" {
  description = "Concurrent executions above which the demo is assumed to be under abuse rather than under judging. Default 20, matching the reserved-concurrency cap."
  type        = number
  default     = 20

  validation {
    condition     = var.concurrency_alarm_threshold >= 1
    error_message = "concurrency_alarm_threshold must be at least 1."
  }
}

variable "alarm_actions" {
  description = <<-EOT
    SNS topic ARNs notified on ALARM. Empty by default and that is deliberate: an SNS
    topic with an email subscription needs a confirmed subscriber to be worth anything,
    and an unconfirmed one is a control that looks present and is not. With no actions the
    alarms still evaluate, still show state in the console and on the dashboard, and are
    still readable by `aws cloudwatch describe-alarms` - which is what W10's GitHub Actions
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
      "LOG_LEVEL",
    ])) == 0
    error_message = "extra_environment must not set MAINLINE_DSN (the DSN is never in Terraform state - use dsn_parameter_name) nor any key this module already sets: MAINLINE_DSN_PARAM, MAINLINE_DEMO_DATABASE, MAINLINE_SCENARIO_PERMIT_ID, MAINLINE_DEMO_PERMIT_ID, LOG_LEVEL."
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
