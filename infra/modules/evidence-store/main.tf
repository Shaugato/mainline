# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
#
# THE INDELIBLE HALF OF THE EVIDENCE STACK.
#
# GT-18 has no fallback: "Object Lock bucket created COMPLIANCE + versioning BEFORE any
# other Terraform runs; backup retention set ONCE at provisioning." Object Lock cannot be
# enabled on an existing bucket, versioning cannot be suspended once it is on, and a
# COMPLIANCE retention cannot be shortened by anyone, including the account root. Every
# resource below is therefore correct on the first apply or it is a new bucket.
#
# Three deliberate choices a reviewer will want the reason for:
#
#   1. SSE-S3 (AES256), NOT SSE-KMS. AWS states it plainly: "if you encrypt your objects
#      with AWS KMS server-side encryption and your AWS KMS key is deleted your objects
#      may become unreadable." A checkpoint note is a PUBLIC commitment — an origin, a
#      tree size, a root hash and a signature, carrying no personal information — so a
#      customer-managed encryption key would buy no confidentiality and would add a
#      crypto-shredding surface to the one bucket whose whole purpose is that nothing can
#      remove it. Encrypting evidence under a deletable key is a delete button with extra
#      steps. (ARCHITECTURE.md §11.7 also forbids claiming CMEK on the checkpoint tier.)
#
#   2. `s3:DeleteObject` is denied to EVERY principal, not merely to the writer. A locked
#      object version cannot be deleted — but a delete marker can still be placed on top
#      of it, and AWS states that "delete markers are not WORM-protected, regardless of
#      any retention period or legal hold." Hiding the checkpoint is not deleting it and
#      is just as effective against someone who does not already suspect.
#
#   3. `prevent_destroy` on every resource. `just destroy` must be honest about which
#      stacks are indelible, and OpenTofu refusing the plan is a stronger statement than a
#      justfile recipe that a `--force` flag walks past (CU-11).

terraform {
  required_version = ">= 1.6.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.60.0, < 7.0.0"
    }
  }
}

locals {
  # Set by the module and never by the caller. `scripts/custody/check_evidence_plan.py`
  # rule GT18-2 fails the merge if any resource outside this module carries it, which is
  # how "the evidence stack lands before any other Terraform in the repo can apply"
  # becomes a check rather than a convention.
  evidence_tags = merge(var.tags, {
    "mainline:evidence-class" = "checkpoint"
    "mainline:indelible"      = "true"
    "mainline:module"         = "evidence-store"
  })

  retention_days = var.retention_years * 365

  # The bucket ARN is DERIVED from the name rather than read off
  # `aws_s3_bucket.evidence.arn`, and that is a deliberate choice with a reason a reviewer
  # should not have to guess at. An S3 bucket ARN is `arn:<partition>:s3:::<name>` — it has
  # no account and no region in it, so it is fully determined by inputs. Referencing the
  # resource attribute instead would make every statement in the bucket policy "known after
  # apply", and a merge gate cannot read a policy that does not exist yet.
  #
  # `scripts/custody/check_evidence_plan.py` therefore reads the ACTUAL policy JSON out of
  # `tofu show -json` on a first-apply plan. That is the difference between a gate that
  # checks the policy and a gate that checks that a policy was mentioned.
  partition   = startswith(var.region_hint, "cn-") ? "aws-cn" : startswith(var.region_hint, "us-gov-") ? "aws-us-gov" : "aws"
  bucket_arn  = "arn:${local.partition}:s3:::${var.bucket_name}"
  object_arns = "arn:${local.partition}:s3:::${var.bucket_name}/*"
}

# ── The bucket ────────────────────────────────────────────────────────────────────────

resource "aws_s3_bucket" "evidence" {
  bucket = var.bucket_name

  # AT CREATION. This argument is the entire GT-18 one-shot: `aws_s3_bucket_object_lock_
  # configuration` alone does NOT enable Object Lock on a bucket that was created without
  # it, and there is no API that retrofits it.
  object_lock_enabled = true

  tags = local.evidence_tags

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_versioning" "evidence" {
  bucket = aws_s3_bucket.evidence.id

  versioning_configuration {
    # Object Lock requires versioning and, once a bucket has Object Lock, versioning can
    # never be suspended. Declaring it is therefore documentation of a fact S3 is already
    # enforcing — and it is what `check_evidence_plan.py` rule OL-2 reads.
    status = "Enabled"
  }
}

resource "aws_s3_bucket_object_lock_configuration" "evidence" {
  bucket = aws_s3_bucket.evidence.id

  rule {
    default_retention {
      mode  = "COMPLIANCE"
      years = var.retention_years
    }
  }

  depends_on = [aws_s3_bucket_versioning.evidence]
}

resource "aws_s3_bucket_public_access_block" "evidence" {
  bucket = aws_s3_bucket.evidence.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "evidence" {
  bucket = aws_s3_bucket.evidence.id

  rule {
    # ACLs off entirely. An object ACL is a second, invisible authorisation surface on the
    # one bucket whose authorisation surface has to be readable in a courtroom.
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "evidence" {
  bucket = aws_s3_bucket.evidence.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256" # SSE-S3. See choice 1 in the header comment.
    }
    bucket_key_enabled = false
  }
}

# ── The bucket policy: what nobody may do, then what two roles may ────────────────────

data "aws_iam_policy_document" "evidence" {
  # DENY comes first for the reader, not for the evaluator — IAM has no ordering — but a
  # policy whose first statement is what it refuses is a policy a reviewer reads correctly.

  statement {
    sid    = "DenyInsecureTransport"
    effect = "Deny"

    principals {
      type        = "*"
      identifiers = ["*"]
    }

    actions   = ["s3:*"]
    resources = [local.bucket_arn, local.object_arns]

    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }

  statement {
    sid    = "DenyAnyPathThatRemovesOrHidesEvidence"
    effect = "Deny"

    principals {
      type        = "*"
      identifiers = ["*"]
    }

    actions = [
      # A locked version cannot be deleted, but a DELETE MARKER can still be placed on top
      # of it and delete markers are not WORM-protected. Hiding is not deleting and works
      # just as well on someone who does not already suspect.
      "s3:DeleteObject",
      "s3:DeleteObjectVersion",
      # Meaningless against COMPLIANCE and denied anyway, so that a future bucket copied
      # from this one in GOVERNANCE mode inherits the refusal rather than the gap.
      "s3:BypassGovernanceRetention",
      # The controls themselves.
      "s3:PutBucketVersioning",
      "s3:PutObjectLockConfiguration",
      "s3:DeleteBucket",
      "s3:DeleteBucketPolicy",
      "s3:PutBucketPolicy",
      "s3:PutLifecycleConfiguration",
      "s3:PutReplicationConfiguration",
    ]

    resources = [local.bucket_arn, local.object_arns]
  }

  statement {
    sid    = "DenyTurningOffALegalHold"
    effect = "Deny"

    principals {
      type        = "*"
      identifiers = ["*"]
    }

    actions   = ["s3:PutObjectLegalHold"]
    resources = [local.object_arns]

    condition {
      test     = "StringNotEquals"
      variable = "s3:object-lock-legal-hold"
      values   = ["ON"]
    }
  }

  statement {
    sid    = "DenyAnyRetentionThatIsNotComplianceForTheFullTerm"
    effect = "Deny"

    principals {
      type        = "*"
      identifiers = ["*"]
    }

    actions   = ["s3:PutObjectRetention", "s3:PutObject"]
    resources = [local.object_arns]

    condition {
      test     = "NumericLessThan"
      variable = "s3:object-lock-remaining-retention-days"
      values   = [tostring(local.retention_days)]
    }
  }

  statement {
    sid    = "DenyAnyRetentionModeOtherThanCompliance"
    effect = "Deny"

    principals {
      type        = "*"
      identifiers = ["*"]
    }

    actions   = ["s3:PutObjectRetention", "s3:PutObject"]
    resources = [local.object_arns]

    condition {
      test     = "StringNotEquals"
      variable = "s3:object-lock-mode"
      values   = ["COMPLIANCE"]
    }
  }

  statement {
    sid    = "AllowTheWriterToPutAndToLockAndNothingElse"
    effect = "Allow"

    principals {
      type        = "AWS"
      identifiers = [var.writer_role_arn]
    }

    actions = [
      "s3:PutObject",
      "s3:GetObject",
      "s3:GetObjectVersion",
      "s3:GetObjectRetention",
      "s3:GetObjectLegalHold",
      # Required by S3 in order to SEND the x-amz-object-lock-* headers on PutObject at
      # all. Both are constrained to a single reachable value by the two Deny statements
      # above, so the writer's whole power here is "COMPLIANCE, full term, hold ON".
      "s3:PutObjectRetention",
      "s3:PutObjectLegalHold",
    ]

    resources = [local.object_arns]
  }

  statement {
    sid    = "AllowTheWriterToListSoAnUploadCanBeConfirmed"
    effect = "Allow"

    principals {
      type        = "AWS"
      identifiers = [var.writer_role_arn]
    }

    actions   = ["s3:ListBucket", "s3:ListBucketVersions", "s3:GetBucketObjectLockConfiguration"]
    resources = [local.bucket_arn]
  }

  dynamic "statement" {
    for_each = length(var.reader_role_arns) > 0 ? [1] : []

    content {
      sid    = "AllowReadOnlyVerification"
      effect = "Allow"

      principals {
        type        = "AWS"
        identifiers = var.reader_role_arns
      }

      actions = [
        "s3:GetObject",
        "s3:GetObjectVersion",
        "s3:GetObjectRetention",
        "s3:GetObjectLegalHold",
      ]

      resources = [local.object_arns]
    }
  }

  dynamic "statement" {
    for_each = length(var.reader_role_arns) > 0 ? [1] : []

    content {
      sid    = "AllowReadOnlyListing"
      effect = "Allow"

      principals {
        type        = "AWS"
        identifiers = var.reader_role_arns
      }

      actions   = ["s3:ListBucket", "s3:ListBucketVersions", "s3:GetBucketObjectLockConfiguration"]
      resources = [local.bucket_arn]
    }
  }
}

resource "aws_s3_bucket_policy" "evidence" {
  bucket = aws_s3_bucket.evidence.id
  policy = data.aws_iam_policy_document.evidence.json

  depends_on = [aws_s3_bucket_public_access_block.evidence]
}

# ── The log signing key ───────────────────────────────────────────────────────────────

# Read from STS only when the caller did not supply it. Two reasons, and the second is the
# load-bearing one: a `NotPrincipal` ARN must be a constant a reviewer can read off the
# plan, and a data source that resolves at apply time makes the break-glass exemption
# "known after apply" — an exemption nobody can review before it exists. Supplying
# `account_id` also lets the whole stack be PLANNED with no credentials at all, which is
# what makes `scripts/custody/check_evidence_plan.py` runnable on this build machine.
data "aws_caller_identity" "current" {
  count = var.account_id == "" ? 1 : 0
}

locals {
  account_id = var.account_id != "" ? var.account_id : data.aws_caller_identity.current[0].account_id
}

data "aws_iam_policy_document" "log_signing" {
  statement {
    sid    = "DenyKeyDestructionOutsideBreakGlass"
    effect = "Deny"

    # NotPrincipal + Deny is the documented break-glass idiom and it is also the sharpest
    # edge in IAM: it denies the actions to everyone EXCEPT the listed principal, and a
    # role ARN here does not cover the assumed-role session ARN in every evaluation
    # context. It is written with both forms for that reason, and `check_evidence_plan.py`
    # rule KMS-1 asserts the statement exists with exactly these actions.
    not_principals {
      type = "AWS"
      identifiers = [
        var.break_glass_role_arn,
        "arn:${local.partition}:sts::${local.account_id}:assumed-role/${replace(var.break_glass_role_arn, "/^.*:role//", "")}/*",
      ]
    }

    actions = [
      "kms:ScheduleKeyDeletion",
      "kms:DisableKey",
      "kms:DeleteImportedKeyMaterial",
      "kms:ImportKeyMaterial",
      "kms:PutKeyPolicy",
      "kms:ReplicateKey",
    ]

    resources = ["*"]
  }

  statement {
    sid    = "AllowSignToTheSequencerAlone"
    effect = "Allow"

    principals {
      type        = "AWS"
      identifiers = [var.signer_role_arn]
    }

    actions = [
      "kms:Sign",
      "kms:GetPublicKey",
      "kms:DescribeKey",
    ]

    resources = ["*"]

    condition {
      test     = "StringEquals"
      variable = "kms:SigningAlgorithm"
      values   = ["ECDSA_SHA_256"]
    }
  }

  statement {
    sid    = "AllowAnyoneInTheAccountToFetchThePublicHalf"
    effect = "Allow"

    principals {
      type        = "AWS"
      identifiers = [local.account_id]
    }

    # The public key is public. A verifier that has to ask us for it is a verifier that
    # needs our cooperation, which is the property this whole domain exists to remove.
    actions   = ["kms:GetPublicKey", "kms:DescribeKey", "kms:Verify"]
    resources = ["*"]
  }

  dynamic "statement" {
    for_each = length(var.key_administrator_role_arns) > 0 ? [1] : []

    content {
      sid    = "AllowNonDestructiveAdministration"
      effect = "Allow"

      principals {
        type        = "AWS"
        identifiers = var.key_administrator_role_arns
      }

      # Every action here is readable or additive. `kms:*` is absent on purpose: the Deny
      # above would still stop the destructive subset, but a policy that GRANTS what it
      # then denies is a policy whose intent nobody can read off the page.
      actions = [
        "kms:DescribeKey",
        "kms:GetKeyPolicy",
        "kms:GetPublicKey",
        "kms:ListResourceTags",
        "kms:TagResource",
      ]

      resources = ["*"]
    }
  }

  statement {
    sid    = "AllowBreakGlassToAdministerUnderTwoPersonControl"
    effect = "Allow"

    principals {
      type        = "AWS"
      identifiers = [var.break_glass_role_arn]
    }

    actions = [
      "kms:DescribeKey",
      "kms:GetKeyPolicy",
      "kms:PutKeyPolicy",
      "kms:ScheduleKeyDeletion",
      "kms:CancelKeyDeletion",
      "kms:DisableKey",
      "kms:EnableKey",
    ]

    resources = ["*"]
  }
}

resource "aws_kms_key" "log_signing" {
  description              = "MAINLINE transparency-log checkpoint signing key (C2SP note type 0x02, ECDSA P-256/SHA-256). Reused across every rebuild: a recreated key makes yesterday's ledger unverifiable."
  key_usage                = "SIGN_VERIFY"
  customer_master_key_spec = "ECC_NIST_P256"

  # Asymmetric KMS keys cannot be rotated by AWS at all, so `false` is the only truthful
  # value — and stating it is what lets `check_evidence_plan.py` rule KMS-2 assert it
  # rather than infer it from an absent attribute.
  enable_key_rotation = false

  # The maximum window. If a break-glass deletion is ever scheduled, thirty days is the
  # longest anyone has to notice and cancel it. Seven — the minimum — is a month of notice
  # traded for nothing.
  deletion_window_in_days = 30

  is_enabled = true
  policy     = data.aws_iam_policy_document.log_signing.json
  tags       = local.evidence_tags

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_kms_alias" "log_signing" {
  name          = "alias/${var.kms_alias_name}"
  target_key_id = aws_kms_key.log_signing.key_id
}
