# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

variable "region" {
  description = <<-EOT
    The evidence account's region. REGION PIN (ARCHITECTURE.md §10.1) requires
    `aws_region(Kernel) == aws_region(Custody) == crdb_region(cluster)`; the platform
    ground truth (docs/adr/0002) records that the cluster is in `aws-ap-southeast-1`
    (Singapore) on the Basic tier while inference is in `ap-southeast-2` (Sydney).

    THAT SPLIT IS REAL AND MUST NOT BE PAPERED OVER: any claim of end-to-end Australian
    data residency is FALSE for this deployment. The default here follows the cluster, and
    a customer install moves Kernel, Memory and Custody together by changing one value.
  EOT
  type        = string
  default     = "ap-southeast-1"
}

variable "evidence_account_role_arn" {
  description = <<-EOT
    Role to assume in the SECOND AWS account, where the evidence lives. Separate account,
    not a separate bucket: a database boundary is a convenience boundary and only an
    account boundary makes "the people who operate the application cannot delete the
    evidence" an organisational fact rather than a policy hope.

    Empty means "use the ambient credentials" — correct for a one-account demo and wrong
    for anything a customer relies on, which is why it is stated rather than defaulted
    away.
  EOT
  type        = string
  default     = ""
}

variable "site_code" {
  description = "The site whose ledger this stack anchors. Becomes part of the bucket name."
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9-]{1,30}$", var.site_code))
    error_message = "site_code must be lowercase alphanumerics and hyphens."
  }
}

variable "bucket_name" {
  description = "Override for the checkpoint bucket name. Defaults to `mainline-custody-<site_code>`."
  type        = string
  default     = ""
}

variable "retention_years" {
  description = "COMPLIANCE retention, in whole years. Set ONCE at provisioning (GT-18); raising it later affects only objects written afterwards."
  type        = number
  default     = 7
}

variable "signer_role_arn" {
  description = "The sole holder of `kms:Sign` — `relay_task` in ARCHITECTURE.md §10.3."
  type        = string
}

variable "writer_role_arn" {
  description = "The role that PUTs checkpoint objects. Its retention and legal-hold powers are constrained by bucket-policy condition to COMPLIANCE / full term / hold ON."
  type        = string
}

variable "reader_role_arns" {
  description = "Read-only roles: the verifier's `--s3` path, the bundle builder, an external auditor."
  type        = list(string)
  default     = []
}

variable "break_glass_role_arn" {
  description = "The two-person break-glass role — the only principal not denied `kms:ScheduleKeyDeletion` and `kms:DisableKey`."
  type        = string
}

variable "key_administrator_role_arns" {
  description = "Roles permitted read-only and tagging administration of the log key."
  type        = list(string)
  default     = []
}

variable "cloudtrail_bucket_name" {
  description = <<-EOT
    A bucket in a THIRD account — the log archive — that receives this trail. Three
    accounts, because a trail whose objects the traced account can delete is a trail that
    records exactly as much as its subject chooses.

    That bucket's own policy must permit `cloudtrail.amazonaws.com` to write with
    `s3:x-amz-acl = bucket-owner-full-control`. It is out of this root module's scope on
    purpose: this stack must not hold write access to the account that audits it.
  EOT
  type        = string
}

variable "cloudtrail_kms_key_arn" {
  description = "Optional CMK in the log-archive account for CloudTrail log encryption. Empty leaves CloudTrail's default SSE-S3 encryption in place — which, unlike the checkpoint bucket, is a genuine choice rather than a constraint, because CloudTrail objects are replaceable and checkpoint notes are not."
  type        = string
  default     = ""
}

variable "cloudtrail_name" {
  description = "Name of the organisation trail covering this account."
  type        = string
  default     = "mainline-evidence-trail"
}

variable "tags" {
  description = "Tags merged onto everything this stack creates."
  type        = map(string)
  default     = {}
}

variable "account_id" {
  description = <<-EOT
    The twelve-digit evidence account. Optional; empty falls back to `aws_caller_identity`.
    Supplying it makes the break-glass `NotPrincipal` ARN readable off the plan rather than
    "known after apply", and lets the stack be planned with no credentials at all so that
    `scripts/custody/check_evidence_plan.py` can read a REAL plan today.
  EOT
  type        = string
  default     = ""
}
