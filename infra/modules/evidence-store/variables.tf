# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
#
# Every variable here is either a name, an ARN, or a number that only ever moves in the
# safe direction. There is deliberately NO variable that can turn a control off:
# no `object_lock_enabled`, no `enable_versioning`, no `retention_mode`. GT-18 says Object
# Lock and versioning cannot be retrofitted, so a flag that lets an operator provision
# without them is a flag that produces an unrecoverable bucket at 02:00.

variable "bucket_name" {
  description = <<-EOT
    Name of the COMPLIANCE-locked checkpoint bucket, e.g. `mainline-custody-blk07`.
    Globally unique across all of S3, and permanent in practice: the bucket cannot be
    destroyed while any object is under retention, so a rename is a new bucket and a
    second place a stranger has to be told to look.
  EOT
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$", var.bucket_name))
    error_message = "bucket_name must be a valid S3 bucket name: 3-63 lowercase alphanumerics, dots and hyphens."
  }

  validation {
    # ARCHITECTURE.md §10.2 splits three buckets on purpose: COMPLIANCE for the
    # commitments, GOVERNANCE for the bulk corpus, GOVERNANCE for audit output. This
    # module builds ONLY the first, and a name that says "bulk" or "audit" is somebody
    # about to lock the wrong content into seven irrevocable years.
    condition     = !can(regex("(bulk|audit|backup|log)", var.bucket_name))
    error_message = "This module provisions the COMPLIANCE checkpoint bucket only. A bucket named bulk/audit/backup/log must not be COMPLIANCE-locked: over-retention of the corpus is a permanent discovery liability, and COMPLIANCE on the Ancestry-Audit output would lock a catalogue of unreviewed machine claims into seven-year retention (ARCHITECTURE.md §10.2)."
  }
}

variable "retention_years" {
  description = "Default COMPLIANCE retention, in whole years, applied by the bucket to every object written to it."
  type        = number
  default     = 7

  validation {
    condition     = var.retention_years >= 7 && var.retention_years <= 100
    error_message = "retention_years must be between 7 (the custody floor) and 100 (the S3 maximum). It may be raised and it may never be lowered: a COMPLIANCE retention already applied cannot be shortened by anyone, including the account root."
  }
}

variable "signer_role_arn" {
  description = <<-EOT
    The ONE role that may call `kms:Sign` on the log key — `relay_task` in
    ARCHITECTURE.md §10.3's identity map. Not the kernel, not the recall plane, not CI.
    "The operator re-signed the history" must require compromising KMS rather than
    reading a secret, and that sentence is only true while this list has one entry.
  EOT
  type        = string

  validation {
    condition     = can(regex("^arn:aws[a-z-]*:iam::[0-9]{12}:role/", var.signer_role_arn))
    error_message = "signer_role_arn must be an IAM role ARN."
  }
}

variable "writer_role_arn" {
  description = <<-EOT
    The role that writes checkpoint objects. Holds `s3:PutObject` and `s3:GetObject`, plus
    `s3:PutObjectRetention` and `s3:PutObjectLegalHold` CONSTRAINED BY CONDITION so that
    the only retention it can ever set is COMPLIANCE for at least `retention_years`, and
    the only legal-hold value it can ever set is ON. See README §"The one grant that looks
    wrong and is not".
  EOT
  type        = string

  validation {
    condition     = can(regex("^arn:aws[a-z-]*:iam::[0-9]{12}:role/", var.writer_role_arn))
    error_message = "writer_role_arn must be an IAM role ARN."
  }
}

variable "reader_role_arns" {
  description = "Roles that may read checkpoint objects and their lock metadata — the verifier's `--s3` path, the bundle builder, an auditor. Read-only, always."
  type        = list(string)
  default     = []
}

variable "break_glass_role_arn" {
  description = <<-EOT
    The two-person break-glass role. The ONLY principal not denied `kms:ScheduleKeyDeletion`
    and `kms:DisableKey` by the key policy. ARCHITECTURE.md §11.6: crypto-shredding is
    document destruction, and a recreated key means yesterday's ledger is unreadable —
    the same offence committed by accident.

    The "unconditionally while any `legal_hold` row is open" half of §11.6 is an
    ORGANISATION-level SCP keyed off a database fact, which no key policy can express. It
    is out of this module's scope and named in the README so that its absence here is a
    stated gap rather than a silent one.
  EOT
  type        = string

  validation {
    condition     = can(regex("^arn:aws[a-z-]*:iam::[0-9]{12}:role/", var.break_glass_role_arn))
    error_message = "break_glass_role_arn must be an IAM role ARN."
  }
}

variable "key_administrator_role_arns" {
  description = "Roles that may read and tag the key. Deliberately excludes every destructive action; those are denied to everyone but break-glass."
  type        = list(string)
  default     = []
}

variable "kms_alias_name" {
  description = "Alias for the log signing key, without the `alias/` prefix."
  type        = string
  default     = "mainline-log-signing"

  validation {
    condition     = can(regex("^[a-zA-Z0-9/_-]{1,250}$", var.kms_alias_name))
    error_message = "kms_alias_name must be alias-name-safe and carry no `alias/` prefix."
  }
}

variable "tags" {
  description = "Tags merged onto every resource. `mainline:evidence-class` is set by the module and cannot be overridden — `scripts/custody/check_evidence_plan.py` keys the GT-18 single-bucket rule off it."
  type        = map(string)
  default     = {}
}

variable "account_id" {
  description = <<-EOT
    The twelve-digit account this stack is provisioned into. Optional: empty falls back to
    `aws_caller_identity`. Supplying it does two things — it makes the break-glass
    `NotPrincipal` ARN a constant a reviewer can read off the PLAN instead of a value that
    is "known after apply", and it lets the whole stack be planned with no credentials at
    all, which is what makes `scripts/custody/check_evidence_plan.py` runnable today.
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
    The region this stack is provisioned into, used ONLY to derive the ARN partition
    (`aws`, `aws-cn`, `aws-us-gov`). It is not passed to any resource — the provider's own
    region is authoritative for placement — and it exists so that the bucket ARN in the
    policy document is a constant at plan time rather than "known after apply". A merge
    gate cannot read a policy that does not exist yet.
  EOT
  type        = string
  default     = "ap-southeast-1"
}
