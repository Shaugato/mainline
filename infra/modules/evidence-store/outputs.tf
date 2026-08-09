# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

output "bucket_name" {
  description = "The COMPLIANCE checkpoint bucket. `trappoint-verify --s3` reads it; `mainline_anchor.aws.S3ObjectLockArchive` writes to it."
  value       = aws_s3_bucket.evidence.id
}

output "bucket_arn" {
  description = "ARN of the checkpoint bucket."
  value       = aws_s3_bucket.evidence.arn
}

output "bucket_region" {
  description = "The bucket's region. REGION PIN (ARCHITECTURE.md §10.1) is asserted against this at process start-up by `mainline_anchor.aws.assert_region`."
  value       = aws_s3_bucket.evidence.region
}

output "retention_years" {
  description = "The COMPLIANCE default retention actually provisioned. Emitted so a caller asserts it rather than assuming the module's default."
  value       = var.retention_years
}

output "kms_key_arn" {
  description = "ARN of the log signing key. Pass to `mainline_anchor.aws.kms_sign_port`."
  value       = aws_kms_key.log_signing.arn
}

output "kms_key_id" {
  description = "Key id of the log signing key."
  value       = aws_kms_key.log_signing.key_id
}

output "kms_alias_arn" {
  description = "ARN of the alias. Sign through the KEY ARN, not the alias: an alias can be repointed at a different key, and a checkpoint signed by a different key is an unverifiable checkpoint that still looks fine."
  value       = aws_kms_alias.log_signing.arn
}

output "evidence_tags" {
  description = "The tag set every resource in this module carries, including `mainline:evidence-class = checkpoint`, which is the key `scripts/custody/check_evidence_plan.py` rule GT18-2 uses to detect a second checkpoint bucket declared anywhere else in the repository."
  value       = local.evidence_tags
}

output "signing_algorithm" {
  description = "The one algorithm the key policy permits. Matches `mainline_anchor.ports.KMS_SIGNING_ALGORITHM` and ruling CU-3; a mismatch between these two values is a checkpoint that cannot be signed at all, which is the failure we want rather than the silent one."
  value       = "ECDSA_SHA_256"
}
