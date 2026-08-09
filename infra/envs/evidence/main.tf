# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
#
# ═══════════════════════════════════════════════════════════════════════════════════════
#  STACK `10-indelible` — THE ROOT MODULE WITH NO DESTROY PATH
# ═══════════════════════════════════════════════════════════════════════════════════════
#
# ARCHITECTURE.md §10.3 splits the infrastructure into four stacks with different destroy
# semantics: `00-bootstrap` (applied once by hand), `10-indelible` (THIS ONE — Object Lock
# bucket, evidence KMS key, CloudTrail; NEVER destroyed), `20-platform`, `30-app`.
# Teardown only ever touches 20 and 30.
#
# CU-11, in one sentence: `just destroy` must be honest about which stacks are indelible,
# and a rebuilt KMS key makes yesterday's ledger unverifiable — the same offence as
# destruction, committed by accident.
#
# THE REFUSAL IS ENFORCED IN THREE PLACES, on purpose, because a single guard is a guard
# somebody walks past at 02:00:
#
#   1. `lifecycle { prevent_destroy = true }` on every resource in
#      `infra/modules/evidence-store` and on the trail below. `tofu destroy` FAILS with
#      "Instance cannot be destroyed" and names the resource.
#   2. `python scripts/custody/check_evidence_plan.py destroy-guard`, which exits non-zero
#      with the explanation. This is what a `just` recipe calls, so the refusal has a
#      message a human reads rather than a Terraform error a human greps.
#   3. S3 Object Lock COMPLIANCE itself. Even with (1) and (2) removed, the bucket cannot
#      be emptied and therefore cannot be deleted, by anyone, including the account root.
#
# Only (3) is a control. (1) and (2) exist so that the person who would have discovered
# (3) the hard way discovers it in a plan instead.
#
# ── STATE AND PLAN ENCRYPTION ──────────────────────────────────────────────────────────
# ARCHITECTURE.md §10.3 requires OpenTofu state AND plan encryption with the `aws_kms` key
# provider and `enforced = true`. That is an OpenTofu-only `terraform { encryption { … } }`
# block: HashiCorp Terraform rejects it as an unsupported block type, and the only
# validator available on this build machine is HashiCorp Terraform 1.14. Rather than ship
# a root module that cannot be validated here, the block is specified verbatim in
# README.md §"State encryption" and is a deployment-time addition owned by the cloud lead
# alongside the backend configuration. Its absence from this file is a stated gap, not an
# oversight — see `cross_domain_notes`.

terraform {
  required_version = ">= 1.6.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.60.0, < 7.0.0"
    }
  }

  # Partial configuration: bucket, key and region come from `-backend-config`, because the
  # state bucket lives in `00-bootstrap` and this module must not know how to create it.
  # `tofu init -backend=false` is enough to validate.
  backend "s3" {
    use_lockfile = true
    encrypt      = true
  }
}

provider "aws" {
  region = var.region

  dynamic "assume_role" {
    for_each = var.evidence_account_role_arn == "" ? [] : [var.evidence_account_role_arn]

    content {
      role_arn     = assume_role.value
      session_name = "mainline-evidence-provisioner"
    }
  }

  default_tags {
    tags = merge(var.tags, {
      "mainline:stack" = "10-indelible"
    })
  }
}

locals {
  bucket_name = var.bucket_name != "" ? var.bucket_name : "mainline-custody-${var.site_code}"
}

module "evidence_store" {
  source = "../../modules/evidence-store"

  bucket_name                 = local.bucket_name
  retention_years             = var.retention_years
  signer_role_arn             = var.signer_role_arn
  writer_role_arn             = var.writer_role_arn
  reader_role_arns            = var.reader_role_arns
  break_glass_role_arn        = var.break_glass_role_arn
  key_administrator_role_arns = var.key_administrator_role_arns
  kms_alias_name              = "mainline-log-signing-${var.site_code}"
  account_id                  = var.account_id
  region_hint                 = var.region

  tags = merge(var.tags, {
    "mainline:site"  = var.site_code
    "mainline:stack" = "10-indelible"
  })
}

# ── CloudTrail, into a THIRD account ──────────────────────────────────────────────────
#
# Three accounts and not two. The application account writes the checkpoints; the evidence
# account holds them; the log-archive account records who touched either. A trail whose
# objects the traced account can delete records exactly as much as its subject chooses.
#
# `enable_log_file_validation` produces CloudTrail's own signed digest files. Those digests
# are a second, independent chain over the same events — weaker than ours (AWS holds the
# key) and useful for precisely that reason: it is a chain we could not have forged.

resource "aws_cloudtrail" "evidence" {
  name                          = var.cloudtrail_name
  s3_bucket_name                = var.cloudtrail_bucket_name
  include_global_service_events = true
  is_multi_region_trail         = true
  enable_log_file_validation    = true
  kms_key_id                    = var.cloudtrail_kms_key_arn != "" ? var.cloudtrail_kms_key_arn : null

  # Management events, always. This is how `kms:ScheduleKeyDeletion`, `PutKeyPolicy`,
  # `PutBucketPolicy` and `PutObjectLockConfiguration` become visible to the custodian
  # patrol within the checkpoint cadence rather than at the next audit.
  advanced_event_selector {
    name = "management-events"

    field_selector {
      field  = "eventCategory"
      equals = ["Management"]
    }
  }

  # Data events on the checkpoint bucket. Expensive on a busy bucket and trivial on this
  # one: a checkpoint every sixty seconds is 1,440 objects a day. Without it, a
  # `GetObject` on evidence — someone reading what they are about to argue with — leaves
  # no record at all.
  advanced_event_selector {
    name = "checkpoint-object-events"

    field_selector {
      field  = "eventCategory"
      equals = ["Data"]
    }

    field_selector {
      field  = "resources.type"
      equals = ["AWS::S3::Object"]
    }

    field_selector {
      field       = "resources.ARN"
      starts_with = ["${module.evidence_store.bucket_arn}/"]
    }
  }

  tags = merge(var.tags, {
    "mainline:evidence-class" = "audit-trail"
    "mainline:indelible"      = "true"
    "mainline:stack"          = "10-indelible"
  })

  lifecycle {
    prevent_destroy = true
  }
}

# ── Outputs ───────────────────────────────────────────────────────────────────────────

output "bucket_name" {
  description = "The COMPLIANCE checkpoint bucket."
  value       = module.evidence_store.bucket_name
}

output "bucket_arn" {
  description = "ARN of the checkpoint bucket."
  value       = module.evidence_store.bucket_arn
}

output "kms_key_arn" {
  description = "The log signing key. Sign through this ARN, never through the alias."
  value       = module.evidence_store.kms_key_arn
}

output "retention_years" {
  description = "The COMPLIANCE retention actually provisioned."
  value       = module.evidence_store.retention_years
}

output "cloudtrail_arn" {
  description = "The trail delivering to the log-archive account."
  value       = aws_cloudtrail.evidence.arn
}

output "anchor_environment" {
  description = <<-EOT
    Everything `mainline_anchor` needs, in the shape the relay task reads it. Emitted as
    one object so that a deployment cannot wire three of the four correctly: REGION PIN is
    asserted at process start-up by `mainline_anchor.aws.assert_region` against the region
    in here.
  EOT
  value = {
    MAINLINE_ANCHOR_BUCKET          = module.evidence_store.bucket_name
    MAINLINE_ANCHOR_KMS_KEY_ARN     = module.evidence_store.kms_key_arn
    MAINLINE_ANCHOR_REGION          = var.region
    MAINLINE_ANCHOR_RETENTION_YEARS = tostring(module.evidence_store.retention_years)
  }
}
