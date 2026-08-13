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

variable "demo_signer_sub" {
  description = <<-EOT
    The principal the demo's fourth beat signs as, published as
    `$MAINLINE_DEMO_SIGNER_SUB`.

    THE AUTHORITATIVE SOURCE OF THIS VALUE IS THE SEED, NOT THIS FILE. The default mirrors
    `verticals/mainline/db/seeds/demo/demo_world.sql` line 125, which inserts the literal
    `'demo.signer'` into `mainline.signing_credential.signer_sub` (the credential row
    beginning at line 124), matching the `mainline.person` row that file inserts at line 98.
    `scripts/deploy/seed_demo.py:115` applies that file - `SEED_FILES = ("demo_world.sql",
    "demo_permit.sql")` - to whatever database this function is pointed at, so the seed is
    what EXISTS and this variable only states what the deployment expects to find. A
    deployment seeded with a different principal changes THIS VARIABLE, and never the seed.

    WHY IT IS PUBLISHED AT ALL, GIVEN THAT THE DEFAULT ALREADY MATCHES.
    `mainline_demo_api.scenario.from_env` reads `ENV_PREFIX + "SIGNER_SUB"` - `ENV_PREFIX`
    is `"MAINLINE_DEMO_"`, `scenario.py:107` and `:209` - and falls back to the in-code
    constant `"demo.signer"` when the variable is absent or blank. Before this variable
    existed the module published NOTHING for it, and the beat that writes a disposition ran
    on a constant compiled into the application, agreeing with the seed because both happen
    to say the same thing rather than because anything makes them.

    That is a WORSE state than the one `scenario_permit_id`'s comment above describes, not a
    milder one. An override that looks configured and behaves inert is at least visible in
    `aws lambda get-function-configuration`; a load-bearing value that is never published is
    invisible there, and a seed carrying a different principal would then produce a beat-4
    failure with nothing in the function's configuration to point at. Publishing it makes
    the expectation READABLE off the deployed function and makes a divergence a diff between
    two named things.

    WHAT DEPENDS ON IT, AND THIS IS THE MEASUREMENT THAT SETTLES WHETHER IT IS LOAD-BEARING.
    `mainline.fn_disposition_project` - the trigger function that overwrites most of a
    disposition from authoritative rows (invariant I02) - reads the AUTHORITY for the
    signer's rank, organisation and competency by looking `mainline.person` up BY THIS
    STRING: `WHERE pr.signer_sub = (NEW).signer_sub`,
    `verticals/mainline/db/migrations/0102_fn_disposition_project.sql:155`, declared at that
    file's line 52 as `@authority mainline.person (signer_sub) <= NEW (signer_sub)`. The sub
    is a KEY the projector joins on, not a label it copies. `mainline.disposition.signer_sub`
    additionally carries its own CHECK - `disposition_signer_sub_stated CHECK (signer_sub <>
    '')`, `verticals/mainline/db/migrations/0066_disposition.sql:210` - and the row's
    `signer_credential_id` is a FOREIGN KEY into `mainline.signing_credential`, the table
    `demo_world.sql` seeds under this same sub.

    CONTRAST IT WITH `SITE_ID`, WHICH THIS MODULE DELIBERATELY DOES NOT PUBLISH.
    `scenario.from_env` reads a `SITE_ID` override too, so the two look alike from the
    outside. The SAME projector function projects the site AWAY - the disposition's site is
    read from elsewhere and the supplied value is overwritten (`gate_run.py:106-111`,
    invariant I02) - so publishing `MAINLINE_DEMO_SITE_ID` would ship an override that looks
    configured and is inert. This variable exists and that one does not for the same reason,
    applied in opposite directions. See the comment beside the environment block in main.tf.

    ONE VALIDATION HERE, AND THE OTHER HALF IS A PRECONDITION. The rule that this value and
    `demo_countersigner_sub` must DIFFER is the database's own
    (`needs_second_signer CHECK (... countersigner_sub <> signer_sub)`,
    `0066_disposition.sql:176`), and it reads two variables. A `validation` block cannot
    read a second variable before Terraform 1.9 and this module's floor is 1.6, so that
    check lives as a `lifecycle.precondition` on `aws_lambda_function.this` in main.tf -
    the same reason `duration_p99_threshold_ms` is checked against `timeout` there and not
    here.
  EOT
  type        = string
  default     = "demo.signer"

  validation {
    # TWO FAILURES IN ONE CONDITION, AND BOTH ARE THE "LOOKS CONFIGURED, IS NOT" SHAPE.
    # `scenario.from_env` computes `src.get(...).strip() or "demo.signer"`, so an EMPTY or
    # whitespace-only value is not an override at all - it silently reverts to the in-code
    # constant, which is precisely the state publishing this variable exists to end. And a
    # PADDED value (`" demo.signer "`) is stripped before use, so the string an operator
    # reads back from `get-function-configuration` would not be the string the handler
    # matched on. Both are refused at plan time rather than discovered at beat 4.
    condition     = var.demo_signer_sub != "" && trimspace(var.demo_signer_sub) == var.demo_signer_sub
    error_message = "demo_signer_sub must be non-empty and must carry no leading or trailing whitespace. mainline_demo_api.scenario.from_env computes `env.get(\"MAINLINE_DEMO_SIGNER_SUB\", \"\").strip() or \"demo.signer\"` (scenario.py:209), so a blank value is not an override - it silently falls back to the in-code constant while still appearing in `aws lambda get-function-configuration`, and a padded value is stripped before use so the published string is not the string the handler matches on. The database refuses the empty case too: `disposition_signer_sub_stated CHECK (signer_sub <> '')`, verticals/mainline/db/migrations/0066_disposition.sql:210. The authoritative value is whatever verticals/mainline/db/seeds/demo/demo_world.sql:125 seeds into mainline.signing_credential.signer_sub."
  }
}

variable "demo_countersigner_sub" {
  description = <<-EOT
    The second principal beat 4 countersigns as, published as
    `$MAINLINE_DEMO_COUNTERSIGNER_SUB`. Everything said about `demo_signer_sub` above
    applies unchanged; only the two citations move.

    THE AUTHORITATIVE SOURCE IS `verticals/mainline/db/seeds/demo/demo_world.sql` line 133,
    which inserts the literal `'demo.countersigner'` into
    `mainline.signing_credential.signer_sub` for the credential row beginning at line 132,
    matching the `mainline.person` row that file inserts at line 108. The default mirrors
    it and does not define it.

    `scenario.from_env` reads `ENV_PREFIX + "COUNTERSIGNER_SUB"` (`scenario.py:210-212`) and
    falls back to the in-code constant `"demo.countersigner"` when the variable is absent or
    blank, exactly as it does for the signer.

    IT IS A KEY, NOT A LABEL, BY THE SAME MEASUREMENT. `mainline.fn_disposition_project`
    branches on it and joins `mainline.person` on it -
    `IF (NEW).countersigner_sub IS NULL THEN ... WHERE pr.signer_sub = (NEW).countersigner_sub`,
    `verticals/mainline/db/migrations/0102_fn_disposition_project.sql:167,174` - so a
    countersigner sub that names nobody does not degrade to a missing label; it changes which
    authority row the projector finds, or finds none.

    WHY A SECOND PRINCIPAL EXISTS AT ALL, since it is the question the variable invites: the
    demo's admit beat is a two-signature disposition, and `mainline.disposition` refuses a
    self-countersignature outright -
    `needs_second_signer CHECK (req_second_signer = false OR (countersigner_credential_id IS
    NOT NULL AND countersigner_sub <> signer_sub))`,
    `verticals/mainline/db/migrations/0066_disposition.sql:176`, with the credential-level
    twin `distinct_credential` at `:171-172`. Setting this to the same string as
    `demo_signer_sub` therefore does not degrade the demo - it makes beat 4 fail on a CHECK
    constraint in front of whoever is watching. That is refused at PLAN time instead, by a
    `lifecycle.precondition` on `aws_lambda_function.this` in main.tf; see `demo_signer_sub`
    for why the check cannot live in a `validation` block on this module's Terraform floor.
  EOT
  type        = string
  default     = "demo.countersigner"

  validation {
    # Identical reasoning to `demo_signer_sub`'s validation: `.strip() or <constant>` makes
    # a blank value a silent revert rather than an override, and makes a padded value differ
    # from the string the handler actually matches on.
    condition     = var.demo_countersigner_sub != "" && trimspace(var.demo_countersigner_sub) == var.demo_countersigner_sub
    error_message = "demo_countersigner_sub must be non-empty and must carry no leading or trailing whitespace. mainline_demo_api.scenario.from_env computes `env.get(\"MAINLINE_DEMO_COUNTERSIGNER_SUB\", \"\").strip() or \"demo.countersigner\"` (scenario.py:210-212), so a blank value silently falls back to the in-code constant while still appearing in `aws lambda get-function-configuration`, and a padded value is stripped before use. The authoritative value is whatever verticals/mainline/db/seeds/demo/demo_world.sql:133 seeds into mainline.signing_credential.signer_sub."
  }
}

variable "log_level" {
  description = <<-EOT
    APPLICATION log level, published as `$LOG_LEVEL` and wired into the function's
    `logging_config.application_log_level`, which is what actually filters records in the
    python3.13 managed runtime. `WARN`.

    ── WHY IT MOVED FROM INFO TO WARN ─────────────────────────────────────────────────

    Log ingestion is billed on ARRIVAL and there is no native ceiling on it anywhere in
    AWS. `log_retention_days` bounds STORAGE and refunds nothing. The only bounds that
    exist are `logbudget.py`'s per-invocation byte budget in the handler
    (`var.log_budget_bytes` below) and `infra/modules/cost-guard`'s `-log-ingestion` alarm,
    and both of those bound how bad it can get rather than how much ordinary operation
    costs. Dropping the application level one notch is the cheap half of that, and it costs
    nothing a reader wants: `evidence/deploy/cost/log-bytes.json` measured this handler
    emitting p50 = 0 and mean = 0.001 wire bytes of its OWN per invocation across all five
    beats and across a sustained 429 flood, so a working handler is silent at any level and
    the level only decides what a MISBEHAVING one is allowed to say.

    ── WHAT `system_log_level` DOES AND DOES NOT SUPPRESS - THE HONEST RECORD ──────────

    `aws_lambda_function.logging_config.system_log_level` is hard-coded to `WARN` in
    main.tf and is a DIFFERENT knob from this one. AWS's API reference for `LoggingConfig`
    (`API_LoggingConfig.html`, retrieved 2026-08-14) defines the two separately:

      * ApplicationLogLevel - filters the APPLICATION logs, i.e. what this function's own
        code writes. Valid values `TRACE | DEBUG | INFO | WARN | ERROR | FATAL`, TRACE the
        highest level of detail and FATAL the lowest. THIS variable.
      * SystemLogLevel - filters the SYSTEM logs, i.e. what Lambda itself writes. Valid
        values `DEBUG | INFO | WARN` only, and the reference states Lambda sends system
        logs "at the selected level of detail and lower, where DEBUG is the highest level
        and WARN is the lowest". So `WARN` is already the quietest setting the API accepts;
        there is no `ERROR` or `OFF` to go to, and `TRACE`/`ERROR`/`FATAL` are rejected on
        this field although they are legal on the one above.

    WHAT THE REFERENCE DOES NOT SAY IS THE PART THAT MATTERS, AND IT IS RECORDED AS A GAP
    RATHER THAN GUESSED AT. It publishes no mapping from a system log level to the platform
    event types (`platform.start`, `platform.report`, `platform.runtimeDone`,
    `platform.initStart`, ...), so NOTHING IN AWS'S PUBLISHED REFERENCE ESTABLISHES THAT
    THE PER-INVOCATION ACCOUNTING LINES ARE SUPPRESSED AT `WARN`. W3 reached the same wall
    - `infra/modules/cost-guard/variables.tf`, `log_bytes_per_invocation_ceiling`, records
    that the event-mapping table could not be retrieved - and took the PESSIMISTIC reading,
    counting `platform.start` (317 B) and `platform.report` (267 B) as PRESENT at
    `system_log_level = WARN`. That reading is inherited here rather than re-litigated: the
    956 B/invocation runtime term in `evidence/deploy/cost/log-bytes.json` assumes these
    lines ship, every threshold derived from it assumes they ship, and if AWS in fact drops
    them at WARN then every one of those margins is larger than stated - which is the safe
    direction to be wrong in.

    THE PRACTICAL SUMMARY, so nobody has to re-read the above: setting this to WARN
    suppresses the handler's INFO/DEBUG/TRACE records and NOTHING ELSE. It does not
    suppress START / END / REPORT accounting, it does not suppress an unhandled exception's
    traceback, and it does not suppress records emitted on a logger the handler's own
    budget filter is not attached to - which `log-bytes.json` measured at 75,800 wire bytes
    for 200 psycopg records charged at ZERO by the budget, and which is the entire reason
    the `-log-ingestion` alarm exists separately from the invocation alarms.
  EOT
  type        = string
  default     = "WARN"

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

# ══════════════════════════════════════════════════════════════════════════════════════
#  THE SIX BOUNDS THAT LIVE IN CODE AND WERE NEVER PUBLISHED
# ══════════════════════════════════════════════════════════════════════════════════════
#
# `static_site.py`, `ratelimit.py` and `logbudget.py` each carry a real, enforced bound and
# each reads an environment variable that can override it. UNTIL THIS WAVE THIS MODULE
# PUBLISHED NONE OF THEM, so every one of the six ran on a constant compiled into the
# application - correct, enforced, and INVISIBLE to
# `aws lambda get-function-configuration`.
#
# That is the same defect `demo_signer_sub` closes one variable group up, and the argument
# is identical: an operator asking "what response ceiling is this function actually
# enforcing?" had to unzip a 7.6 MB deployment package and read a Python constant. Now the
# answer is one read-only API call, and a divergence between what the deployment intends
# and what the code defaults to is a diff between two named things instead of an
# archaeology exercise.
#
# THE DEFAULTS BELOW MIRROR THE CODE AND DO NOT DEFINE IT. Each one cites the constant it
# mirrors. If a code default moves, THESE MOVE TO MATCH - the source of truth is the
# module that enforces the bound, exactly as `demo_world.sql` and not this file is the
# source of truth for the two signer subs. Publishing a value that disagrees with the code
# is worse than publishing nothing, because it is enforced (the env var wins) while reading
# like documentation.
#
# WHAT EACH PARSER DOES WITH A BAD VALUE, because it decides how dangerous a typo is, and
# all three fail in the SAFE direction:
#
#   static_site.max_response_bytes()   non-integer or <= 0  ->  DEFAULT_MAX_RESPONSE_BYTES
#   ratelimit._rate() / ._burst()      non-numeric, <= 0, inf, nan, or above MAX_RPS /
#                                      MAX_BURST             ->  the module default
#   logbudget                          non-integer or <= 0  ->  DEFAULT_BUDGET_BYTES
#
# So nothing an environment variable can say DISARMS one of these; the worst a typo does is
# revert to the compiled-in bound, which is the same state the function was in before this
# group existed. The `validation` blocks below refuse the typo at plan time anyway, because
# a silent revert is still an override that looks configured and is not.

variable "max_response_bytes" {
  description = <<-EOT
    The ceiling, in WIRE bytes, on any single response this function may put on the wire.
    Published as `$MAINLINE_MAX_RESPONSE_BYTES`.

    139 264 (= 136 KiB), mirroring
    `verticals/mainline/apps/demo-api/src/mainline_demo_api/static_site.py`'s
    `DEFAULT_MAX_RESPONSE_BYTES = 136 * 1024`, which W1 derived from the DEPLOYED TREE
    rather than chose: `evidence/deploy/cost/package-shape.json` measures the largest `.gz`
    object that actually ships at 124 127 B, and the ceiling sits at 1.122x it, inside
    interface I3's rule `largest_served_wire_bytes <= MAX_RESPONSE_BYTES < 1.20 x
    largest_served_wire_bytes`. A ceiling above everything it governs is a decoration; that
    is what 512 KiB had become and it is why this number is small and awkward rather than
    round.

    IT IS MEASURED ON WIRE BYTES, NOT ON THE BASE64 ENVELOPE (interface I2). The billed
    quantity is what leaves Lambda after it decodes base64, and a gzip body must travel as
    `isBase64Encoded: true` whose string is 33 % larger. A ceiling applied to the encoded
    form would over-refuse by exactly that.

    PUBLISHING IT DOES NOT SET IT. `static_site.max_response_bytes()` reads this variable
    and falls back to the compiled-in constant on anything that is not a positive integer,
    so this line makes the enforced ceiling READABLE - it does not make it authoritative.
    The test that keeps it derived lives with the code, not here: Terraform cannot see the
    package's contents and must not pretend to.
  EOT
  type        = number
  default     = 139264

  validation {
    condition     = var.max_response_bytes > 0 && floor(var.max_response_bytes) == var.max_response_bytes
    error_message = "max_response_bytes must be a positive whole number of bytes. static_site.max_response_bytes() parses $MAINLINE_MAX_RESPONSE_BYTES with int() and falls back to DEFAULT_MAX_RESPONSE_BYTES on anything else, so a fractional or non-positive value here would publish an override that looks configured and silently is not."
  }
}

variable "rate_global_rps" {
  description = <<-EOT
    Sustained requests per second this execution environment serves, across ALL callers,
    before it answers 429. Published as `$MAINLINE_RATE_GLOBAL_RPS`.

    10, mirroring `ratelimit.py`'s `DEFAULT_GLOBAL_RPS = 10.0`. It is PER EXECUTION
    ENVIRONMENT, so the fleet bound is `10 x account_concurrency_ceiling` = 100 rps -
    which is the number `docs/leads/cost-finish-plan.md` sec 0.5 costs the rate-bounded row
    at, and the first order-of-magnitude lever in that table.

    It is chosen from what the demo must NOT refuse: a judge loading the console fetches
    `index.html` plus its hashed assets - under thirty requests - and then drives the
    three-beat demo at roughly one request per second.
  EOT
  type        = number
  default     = 10

  validation {
    condition     = var.rate_global_rps > 0 && var.rate_global_rps <= 10000
    error_message = "rate_global_rps must be greater than 0 and at most 10000 (ratelimit.MAX_RPS). ratelimit._rate() refuses inf, nan, non-positive values and anything above MAX_RPS by falling back to DEFAULT_GLOBAL_RPS, so a value outside this range publishes an override that silently does not apply."
  }
}

variable "rate_global_burst" {
  description = <<-EOT
    Bucket capacity: how many requests may arrive INSTANTLY, across all callers, before the
    sustained rate binds. Published as `$MAINLINE_RATE_GLOBAL_BURST`.

    100, mirroring `ratelimit.py`'s `DEFAULT_GLOBAL_BURST = 100`. It is a separate knob
    from the rate rather than derived from it, and that is the number that keeps the
    control from breaking the demo: a page load IS a burst, and a bucket sized to the
    sustained rate would refuse the console's own assets on the first click.
  EOT
  type        = number
  default     = 100

  validation {
    condition     = var.rate_global_burst >= 1 && var.rate_global_burst <= 100000 && floor(var.rate_global_burst) == var.rate_global_burst
    error_message = "rate_global_burst must be a whole number between 1 and 100000 (ratelimit.MAX_BURST). ratelimit._burst() parses with int(), which RAISES on \"1.5\" rather than truncating, and falls back to the compiled-in default - so a fractional value here is an override that looks configured and is not."
  }
}

variable "rate_ip_rps" {
  description = <<-EOT
    Sustained requests per second from ONE source address. Published as
    `$MAINLINE_RATE_IP_RPS`.

    5, mirroring `ratelimit.py`'s `DEFAULT_IP_RPS = 5.0` - half the global rate, so one
    caller can never be more than half of an instance's sustained budget.

    WHAT IT DOES NOT DO, said here because the module's own docstring says it: this bounds
    a caller, not an attacker. A flood from many addresses is bounded by the GLOBAL pair
    above and by nothing here.
  EOT
  type        = number
  default     = 5

  validation {
    condition     = var.rate_ip_rps > 0 && var.rate_ip_rps <= 10000
    error_message = "rate_ip_rps must be greater than 0 and at most 10000 (ratelimit.MAX_RPS); outside that range ratelimit._rate() falls back to DEFAULT_IP_RPS and the published value is inert."
  }
}

variable "rate_ip_burst" {
  description = <<-EOT
    Bucket capacity for one source address. Published as `$MAINLINE_RATE_IP_BURST`.

    50, mirroring `ratelimit.py`'s `DEFAULT_IP_BURST = 50`: half the global burst, and
    still large enough to swallow a whole page load in one go so that the first click on
    the console is never the thing this control refuses.
  EOT
  type        = number
  default     = 50

  validation {
    condition     = var.rate_ip_burst >= 1 && var.rate_ip_burst <= 100000 && floor(var.rate_ip_burst) == var.rate_ip_burst
    error_message = "rate_ip_burst must be a whole number between 1 and 100000 (ratelimit.MAX_BURST); ratelimit._burst() parses with int() and falls back to DEFAULT_IP_BURST on anything else."
  }
}

variable "log_budget_bytes" {
  description = <<-EOT
    How many bytes of its OWN log records this handler may emit per invocation before the
    budget truncates. Published as `$MAINLINE_LOG_BUDGET_BYTES`.

    4 096, mirroring `logbudget.py`'s `DEFAULT_BUDGET_BYTES = 4096`.

    IT IS THE ONLY BOUND ON INGESTION THAT LIVES IN THE HANDLER, and it is smaller than it
    looks. `logbudget.OVERRUN_BOUND` adds 947 B for the "a diagnostic was cut here" notice,
    so the code ceiling is 5 043 MESSAGE bytes, which becomes 5 217 B on the wire once
    Lambda's 148 B JSON envelope and CloudWatch's documented 26 B per event are added.
    `infra/modules/cost-guard`'s `log_bytes_per_invocation_ceiling` takes the MEASURED
    4 305 B rather than that code bound, and every threshold in the guard is derived from
    it - so RAISING THIS NUMBER REQUIRES RAISING `log_incoming_bytes_threshold`
    PROPORTIONALLY, which `evidence/deploy/cost/log-bytes.json` states from the other side.

    WHAT IT DOES NOT BOUND, measured rather than imagined: records written on a logger the
    budget's filter is not attached to. 200 psycopg records reached a handler as 75 800
    wire bytes and this budget charged ZERO for them. That shape decouples bytes from
    invocations without limit and is the entire reason the guard's `-log-ingestion` alarm
    exists separately from its two invocation alarms.
  EOT
  type        = number
  default     = 4096

  validation {
    condition     = var.log_budget_bytes >= 1 && floor(var.log_budget_bytes) == var.log_budget_bytes
    error_message = "log_budget_bytes must be a positive whole number of bytes; logbudget parses $MAINLINE_LOG_BUDGET_BYTES with int() and falls back to DEFAULT_BUDGET_BYTES on anything else, so a fractional or non-positive value publishes an inert override."
  }
}

variable "memory_size" {
  description = <<-EOT
    MB. 256, AND THE 512 THAT STOOD HERE WAS JUSTIFIED BY A SENTENCE THAT IS FALSE.

    That sentence read: "CPU is allocated in proportion to memory, so lowering this makes
    cold starts worse WITHOUT MAKING THE BILL SMALLER - the free tier is not the binding
    constraint." The first clause is true and the second is not, and the difference is the
    whole reason this default moved. The free tier is not the binding constraint on a
    function that is being deliberately flooded; the ACCOUNT CONCURRENCY CEILING is
    (`account_concurrency_ceiling`, measured at 10). Under a sustained flood at that
    ceiling the four cost terms behave like this -
    `docs/deploy/LATENCY.md` sec 6, and the algebra is one line each:

        rate     = concurrency / duration                          proportional to 1/d
        egress   = rate x bytes x window                           proportional to 1/d
        requests = rate x window                                   proportional to 1/d
        compute  = concurrency x memory_GB x window x price        INDEPENDENT of d

    `memory_size` is the ONLY lever in the whole menu that pushes every one of those the
    same way. It halves the compute term outright, and - because the CPU-bound beats then
    take about twice as long - it halves the flood RATE too, which halves egress and
    requests with it. `docs/leads/cost-finish-plan.md` sec 0.5 puts the compute line at
    USD 173 -> USD 86 per 30 days at the modelled flood; that is 0.2 % of the bill and is
    NOT why this is worth taking. It is worth taking because it is duration-independent,
    which no other lever here is.

    WHAT IT COSTS, STATED RATHER THAN BURIED (`LATENCY.md` sec 5.2, and every figure there
    is labelled a model rather than a measurement):

      * the modelled cold start rises from 5,248 ms at 512 MB to 6,511 ms at 256 MB, and
        that lands on a judge's FIRST CLICK. There is no mitigation that does not cost
        money (provisioned concurrency);
      * the static-asset beats roughly double, because they are nearly pure CPU;
      * THERE IS NO MEASUREMENT OF A 256 MB LAMBDA ANYWHERE IN THIS EVIDENCE and there
        cannot be one without an apply. `LATENCY.md` sec 4 is a CPU-share proxy taken on a
        throttled workstation core, it is noisy, and it is labelled as a proxy there and
        here.

    WHY THE HEADLINE BEAT SURVIVES IT, MEASURED: the gate run is database-bound. Four
    beats accounted for 1,244.9 ms of a 1,336.6 ms server-reported run, so 93 % of the gate
    run is CockroachDB executing, and CockroachDB does not get slower when Lambda gets less
    CPU. Halving memory roughly doubles the other 7 %. `var.timeout` is sized against the
    256 MB cold path, not the 512 MB one, for exactly that reason.
  EOT
  type        = number
  default     = 256

  validation {
    condition     = var.memory_size >= 128 && var.memory_size <= 10240 && var.memory_size % 64 == 0
    error_message = "memory_size must be 128-10240 MB in 64 MB steps."
  }
}

variable "timeout" {
  description = <<-EOT
    Seconds. 14 s.

    ── THIS IS A RELIABILITY BOUND. IT IS NOT A SPEND BOUND, AND NOBODY MAY SELL IT AS ONE ─

    LAMBDA BILLS ACTUAL DURATION. A 5.66 ms invocation costs exactly the same under a 14 s
    timeout as under a 3 s one, so MOVING THIS NUMBER MOVES THE BILL BY NOTHING. The four
    cost terms are written out in `var.memory_size` above and `timeout` appears in none of
    them. What a timeout actually bounds is the blast radius of a HUNG invocation - a
    pgwire stall, a connection stranded INTRANS - and that is a reliability property.

    The founder asked for 3 s. THREE SECONDS IS REFUSED, and the reason is arithmetic
    rather than preference: 3,000 ms is 0.80x the warm in-region `gate_run` p99 CORRECTED
    to Lambda, 3,729 ms (`docs/deploy/LATENCY.md` sec 3 method B, sec 5.1). It would
    truncate the headline beat - the one beat the judges watch, the only beat that writes
    anything - on the p99 alone, with no cold start and no `40001` retry in the picture. A
    truncated headline beat is a far worse defect than a larger bill, and it buys nothing,
    because of the paragraph above. `LATENCY.md` sec 5.1 lists five separate things 3 s
    would truncate; the fifth is not an extrapolation at all - it is 100 of 100 measured
    cloud gate runs at 11,688 ms p99, which is what a judge running
    `scripts/deploy/demo_acceptance.py` from outside ap-southeast-1 is.

    ── WHERE 14 COMES FROM (`LATENCY.md` sec 5.1) ──────────────────────────────────────

    | term                                          |      ms | kind                    |
    |-----------------------------------------------|--------:|-------------------------|
    | warm in-region gate run, p99                  | 3,729.0 | extrapolation (sec 3)   |
    | `import psycopg` p99 at 0.145 vCPU            | 2,526.2 | extrapolation (sec 4)   |
    | first connection, in region                   |   256.2 | extrapolation           |
    | **modelled cold start at 256 MB**             | 6,511.4 |                         |
    | **binding case: cold at 256 MB, 2x worse tail**| 13,022.9 |                        |

    14 s is the smallest whole second that clears the binding case, by 1.07x. It is robust
    to sec 4's noisiest input: at perfect CPU proportionality the binding case is
    13,023 ms and at the 1.083 slope an earlier probe measured it is 13,442 ms - 14 s
    either way. Expressed as multiples: 1.20x the cloud gate-run p99 as measured
    (11,688 ms), 3.75x that p99 corrected to in-region, 2.15x the modelled cold start at
    256 MB. `LATENCY.md`'s instruction is explicit and is followed here: do not go below
    14 s, and do not go near 3 s.

    NOTE WHICH MEMORY THE BINDING CASE IS SIZED AT. It is 256 MB, because that is what
    `var.memory_size` now is. The two variables are coupled: halving memory raises the
    modelled cold start from 5,248 ms to 6,511 ms and therefore raises the binding case
    from 10,497 ms to 13,023 ms. Raising `memory_size` back to 512 without lowering this
    would leave 14 s over-provisioned rather than wrong; LOWERING memory below 256 without
    raising this would not.

    ── THE COUPLING TO THE ALARM, WHICH IS CHECKED AND NOT ASSERTED ────────────────────

    `duration_p99_threshold_ms` must sit STRICTLY BELOW `timeout * 1000`, because Lambda
    terminates the invocation at the timeout and caps the `Duration` datapoint there - an
    alarm at or above it cannot fire. That is a `lifecycle.precondition` on
    `aws_cloudwatch_metric_alarm.duration_p99` in main.tf and it is working as intended:
    SATISFY IT BY CHOOSING CONSISTENT VALUES, NEVER BY RELAXING IT. Since this wave the
    same alarm carries a FLOOR as well, and the floor exists because the alarm now has an
    ACTION - see `duration_p99_threshold_ms` and `modelled_worst_legitimate_duration_ms`.

    The 29 s ceiling in the validation stays. It is not needed by the `NONE` shape - a
    Function URL will wait far longer - but it keeps every configuration of this module
    valid for `AWS_IAM` + CloudFront, whose 30 s origin read timeout would otherwise turn
    this API's JSON problem document into CloudFront's 504 HTML.
  EOT
  type        = number
  default     = 14

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
    13 500 - and the number is now pinned between a FLOOR and a CEILING rather than sitting
    at a comfortable fraction of one of them.

    ── WHY IT MOVED UP, WHICH IS THE UNCOMFORTABLE DIRECTION ───────────────────────────

    12 000 stood here, chosen as 80 % of a 15 s timeout, when this alarm had NO ACTION -
    `var.alarm_actions` defaulted to `[]` and the module said, in as many words, that these
    four alarms "exist to be READ". Under `infra/envs/demo` as of this wave THAT IS NO
    LONGER TRUE: the env root wires `module.guard`'s SNS topic into `var.alarm_actions`,
    and that topic is a STOP topic - everything subscribed to it invokes a responder that
    calls `PutFunctionConcurrency(0)`. Breaching this alarm now STOPS THE DEMO.

    An alarm that only reports may be as sensitive as you like; the cost of a false
    positive is a red square. An alarm that ACTS may not fire on an invocation the model
    already calls legitimate, because the cost of that false positive is the demo going
    dark in front of the judges until a human runs `kill_switch.sh --restore`. So the
    threshold had to be re-derived against the new consequence, and it went UP:

        FLOOR    13 022.9 ms   `modelled_worst_legitimate_duration_ms` - LATENCY.md sec 5.1's
                               binding case, a COLD start at 256 MB with a 2x worse tail.
                               A threshold below this stops the demo on a cold start.
        CEILING  14 000 ms     `timeout * 1000`. Lambda caps the Duration datapoint at the
                               timeout, so a threshold at or above this cannot fire.

        BAND     13 023 .. 14 000 - only 1.075x wide, and 13 500 sits at 1.037x the floor
                               and 0.964x the ceiling.

    THE BAND IS NARROW BECAUSE `timeout` IS SIZED AT 1.07x THE SAME BINDING CASE, and that
    is a real property of this configuration rather than an artefact of the arithmetic: at
    256 MB the modelled cold path very nearly fills the timeout, so "approaching the
    timeout" and "a cold start happened" are almost the same event. 13 500 says the honest
    version of that - a p99 within 500 ms of truncation - and the two preconditions on
    `aws_cloudwatch_metric_alarm.duration_p99` in main.tf refuse anything outside the band
    at PLAN time rather than at 3 a.m.

    ── WHAT WOULD MOVE IT ──────────────────────────────────────────────────────────────

    Raising `memory_size` back to 512 lowers the binding case to 10 497 ms, which widens
    the band downward and would ADMIT a more sensitive threshold. Lowering
    `modelled_worst_legitimate_duration_ms` to a MEASURED figure does the same thing, and is
    the honest way to move the floor. Neither is a reason to change this number without
    changing the thing that moved.

    THE FLOOR IS UNCONDITIONAL, AND THE CONDITIONAL VERSION IS A MEASUREMENT WORTH KEEPING.
    It was first written as `length(var.alarm_actions) == 0 || <the comparison>`, on the
    reasoning that an alarm which only REPORTS has no reason to carry a floor. The reasoning
    was fine; the expression did not work. `infra/envs/demo` reaches the stop topic through
    `try([module.guard[0].sns_topic_arn], [])`, `try()` returns a WHOLLY UNKNOWN value when
    its argument contains an unknown, and Terraform DEFERS an unknown precondition to apply
    rather than failing the plan. Planting the violation proved it - `terraform plan -var
    api_duration_p99_threshold_ms=12000` planned cleanly, twice, at 12 000 and at the floor
    exactly. A precondition that cannot be evaluated at plan time is a control that looks
    present and is not, so the guard clause was deleted rather than repaired. See main.tf.

    IT IS NOT PERMITTED TO WIDEN THE BAND BY RAISING `timeout` ALONE. `timeout` is a
    reliability bound derived in its own variable from the cold path; moving it to make an
    alarm fit is the inverse of the ordering this repository uses everywhere else.
  EOT
  type        = number
  default     = 13500

  validation {
    condition     = var.duration_p99_threshold_ms > 0 && var.duration_p99_threshold_ms <= 900000
    error_message = "duration_p99_threshold_ms must be between 1 and 900000. It must ALSO be strictly below timeout * 1000 AND strictly above modelled_worst_legitimate_duration_ms. Both of those read a second variable, so both are checked at plan time by preconditions on aws_cloudwatch_metric_alarm.duration_p99 rather than here: a validation block cannot read a second variable before Terraform 1.9 and this module's floor is 1.6."
  }
}

variable "modelled_worst_legitimate_duration_ms" {
  description = <<-EOT
    The longest a LEGITIMATE invocation of this function is modelled to take, in ms. It is
    the FLOOR under `duration_p99_threshold_ms`, read by an UNCONDITIONAL
    `lifecycle.precondition` on `aws_cloudwatch_metric_alarm.duration_p99`.

    UNCONDITIONAL BECAUSE THE CONDITIONAL FORM WAS MEASURED NOT TO FIRE, not because the
    distinction does not matter. It was written CONDITIONAL first - skipped when `alarm_actions` was empty - and the conditional form was MEASURED NOT TO FIRE: the env root reaches the topic through `try()`, `try()` returns unknown when its argument contains an unknown, and Terraform DEFERS an unknown precondition to apply instead of failing the plan. Planting `api_duration_p99_threshold_ms=12000` planned cleanly. It is unconditional now, which is strictly TIGHTER, and both edges of the band are exercised. The cost of the unconditional form
    is that a caller with no alarm actions can no longer set a deliberately sensitive p99
    warning below this figure - and the honest repair for that caller is to lower THIS
    variable to their own measured worst legitimate invocation, which carries the threshold
    down with it.

    13 022.9 ms, rounded down to 13 022 so the comparison is integral. It is
    `docs/deploy/LATENCY.md` sec 5.1's BINDING CASE: a COLD start at 256 MB whose tail is
    2x worse than this workstation's - runtime init, `import psycopg` at 0.145 vCPU
    (2,526.2 ms extrapolated from a measured 365.6 ms), the first in-region connection
    (256.2 ms), and the warm gate run's p99 corrected to in-region (3,729.0 ms), summed to
    6,511.4 ms and doubled at the tail. `var.timeout` is the smallest whole second that
    clears it, by 1.07x.

    ── WHY THIS EXISTS AS A VARIABLE AND A PRECONDITION RATHER THAN AS A COMMENT ───────

    The module's own rule, stated at the head of the alarm section in main.tf, is that any
    alarm on a metric with a known physical CEILING carries a plan-time precondition
    placing its threshold below that ceiling - because an alarm that cannot fire is a
    control that looks present and is not. Wiring an ACTION onto an alarm creates the
    mirror-image defect and this variable is the mirror-image guard: an alarm that fires on
    an invocation the model calls legitimate is a control that looks like a bound and is an
    OUTAGE. The two preconditions together pin the threshold into a stated band, and both
    sides of both comparisons are plain variables, so the check costs one plan evaluation
    and no API call.

    IT IS A MODEL, NOT A MEASUREMENT, AND IT IS LABELLED THAT WAY IN LATENCY.md TOO. There
    is no measurement of a 256 MB Lambda anywhere in this repository and there cannot be
    one without an apply. If an apply ever produces real `Duration` percentiles, THIS is
    the number to replace with the measured one - and the direction matters: a measured
    figure LOWER than 13 022 widens the band downward and permits a tighter alarm, while a
    measured figure at or above 14 000 means the timeout is too small, not that this
    variable is.
  EOT
  type        = number
  default     = 13022

  validation {
    condition     = var.modelled_worst_legitimate_duration_ms > 0
    error_message = "modelled_worst_legitimate_duration_ms must be greater than zero; it is the floor under duration_p99_threshold_ms whenever that alarm carries an action."
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
    SNS topic ARNs notified on ALARM, on ALL FOUR alarms this module creates. Empty by
    default, and `infra/envs/demo` now passes `module.guard`'s topic.

    ── READ THIS BEFORE PASSING A TOPIC HERE. IT IS ONE LIST AND IT REACHES FOUR ALARMS ─

    This module makes no per-alarm distinction: whatever is in this list becomes the
    `alarm_actions` of `-errors`, `-throttles`, `-duration-p99` AND `-concurrency`. Three
    of those four are HEALTH signals and one is an abuse signal, so a topic whose
    subscriber STOPS the function turns three health signals into self-inflicted outages.
    `infra/modules/cost-guard/outputs.tf` says this at length about its own
    `sns_topic_arn`, and it is right.

    THE ENV ROOT WIRES IT ANYWAY, DELIBERATELY, AND THE REASON IS A RANKING RATHER THAN AN
    OVERSIGHT. `docs/leads/cost-finish-plan.md` sec 0.5: an outage is recoverable by one
    command (`scripts/deploy/kill_switch.sh --restore`) and a bill is not, so over-eager
    stopping is the error direction this project chooses. What that costs, alarm by alarm,
    is written out at the wiring site in `infra/envs/demo/main.tf` rather than left to be
    discovered - and the one false positive that ranking does NOT excuse, a cold start
    tripping `-duration-p99`, is refused at plan time by the floor precondition on that
    alarm (see `modelled_worst_legitimate_duration_ms`).

    ONE UNVERIFIED HAZARD, NAMED HERE BECAUSE NOTHING IN THIS REPOSITORY CAN SETTLE IT
    WITHOUT AN APPLY. `infra/modules/cost-guard`'s topic POLICY admits
    `cloudwatch.amazonaws.com` under an `ArnLike` on `aws:SourceArn` naming exactly its own
    THREE alarm ARNs (main.tf, statement `TheseThreeAlarmsMayPublishAStop`). None of this
    module's four alarms is in that list. Whether they can publish therefore depends on
    whether the policy's FIRST statement - SNS's default idiom, `Principal AWS:*` scoped by
    `AWS:SourceOwner` - admits a same-account CloudWatch alarm. If it does, all four stop
    the demo as described above. If it does not, all four carry an action that SNS denies,
    which is a control that looks present and is not - and `describe-alarms` cannot tell
    the two apart. `evidence/deploy/cost/plan-shape.json` records the two ARN sets side by
    side so the question is visible rather than assumed.

    An SNS topic with only an EMAIL subscription is worth nothing until somebody clicks the
    confirmation link; that was the original reason for the empty default and it still
    applies to any human-facing topic. The guard topic is not that: its responder
    subscription is a Lambda and needs no confirmation.
  EOT
  type        = list(string)
  default     = []
}

variable "ok_actions" {
  description = <<-EOT
    SNS topic ARNs notified when an alarm returns to OK, on all four alarms. EMPTY, and
    SEPARATE FROM `var.alarm_actions` since this wave.

    ── WHY IT IS A SECOND VARIABLE ────────────────────────────────────────────────────

    All four alarms used to read `ok_actions = var.alarm_actions`, i.e. the same list.
    Under the old empty default that was invisible. It stops being invisible the moment the
    list holds a STOP topic: every RECOVERY of every one of the four alarms would then
    invoke the responder that calls `PutFunctionConcurrency(0)` - a stop fired by the demo
    getting better.

    `infra/modules/cost-guard/main.tf` states the rule this now follows, at the head of its
    own alarm section: none of its three alarms has `ok_actions`, because "the correct
    place to not do that is here, where the action is chosen", and the responder's own
    refusal of an OK transition is the second belt rather than the first. This module was
    the odd one out; it no longer is.

    NOTHING IS WEAKENED BY THE SPLIT. The default is `[]`, which is byte-for-byte what
    `ok_actions` evaluated to before, in every configuration that existed - because
    `alarm_actions` was `[]` too. What changed is that a caller who arms `alarm_actions`
    no longer arms `ok_actions` by accident. A caller who genuinely wants OK notifications
    passes a NOTIFICATION topic here; passing a stop topic is the thing this variable
    exists to stop being automatic.
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
    names and every key this module sets itself.

    THAT SECOND LIST IS NOT DECORATION AND IT HAS TO BE KEPT IN STEP WITH `local.environment`
    IN main.tf. `local.environment` is `merge(var.extra_environment, { ...module keys... })`,
    and `merge` lets the LAST argument win - so a caller who set a key the module also sets
    would have their value silently discarded, having written it down in a place that reads
    like configuration. The validation below turns that into a plan-time refusal. Adding a
    key to the module's environment without adding it here re-opens exactly that hole, which
    is why the list and the error message name the same set twice: the reader of a failed
    plan sees the names, and the next person editing main.tf sees them too.
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
      "MAINLINE_DEMO_SIGNER_SUB",
      "MAINLINE_DEMO_COUNTERSIGNER_SUB",
      "MAINLINE_WEB_ROOT",
      "LOG_LEVEL",
      # THE SIX PUBLISHED BOUNDS. Added in the same commit that added them to
      # `local.environment`, because the comment above this validation says that adding a
      # key to the module's environment without adding it here re-opens the hole - a caller
      # who set one of these would have it silently discarded by `merge`, having written it
      # down in a place that reads like configuration.
      "MAINLINE_MAX_RESPONSE_BYTES",
      "MAINLINE_RATE_GLOBAL_RPS",
      "MAINLINE_RATE_GLOBAL_BURST",
      "MAINLINE_RATE_IP_RPS",
      "MAINLINE_RATE_IP_BURST",
      "MAINLINE_LOG_BUDGET_BYTES",
    ])) == 0
    error_message = "extra_environment must not set MAINLINE_DSN (the DSN is never in Terraform state - use dsn_parameter_name) nor any key this module already sets: MAINLINE_DSN_PARAM, MAINLINE_DEMO_DATABASE, MAINLINE_SCENARIO_PERMIT_ID, MAINLINE_DEMO_PERMIT_ID, MAINLINE_DEMO_SIGNER_SUB (use var.demo_signer_sub), MAINLINE_DEMO_COUNTERSIGNER_SUB (use var.demo_countersigner_sub), MAINLINE_WEB_ROOT (use var.web_root), LOG_LEVEL (use var.log_level), MAINLINE_MAX_RESPONSE_BYTES (use var.max_response_bytes), MAINLINE_RATE_GLOBAL_RPS (use var.rate_global_rps), MAINLINE_RATE_GLOBAL_BURST (use var.rate_global_burst), MAINLINE_RATE_IP_RPS (use var.rate_ip_rps), MAINLINE_RATE_IP_BURST (use var.rate_ip_burst), MAINLINE_LOG_BUDGET_BYTES (use var.log_budget_bytes)."
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
