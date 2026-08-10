# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
#
# Version floors, and the reason for each one.
#
#   terraform >= 1.10.0   `use_lockfile = true` in the S3 backend is native S3 state
#                         locking, added in 1.10. It is the reason this stack has no
#                         DynamoDB table: no $0.25/month, one less resource for
#                         `scripts/deploy/teardown.sh` to find and delete, and one less
#                         thing that can be left behind. Below 1.10 the argument is an
#                         unsupported attribute and `terraform init` fails loudly —
#                         which is the correct outcome, because silently falling back to
#                         an unlocked backend is how two applies corrupt one state file.
#                         Measured on this machine: Terraform v1.14.8.
#
#   aws >= 5.60.0         CloudFront Origin Access Control with `origin_access_control
#                         _origin_type = "lambda"` — the thing that lets one distribution
#                         put an IAM-authenticated Lambda Function URL behind the same
#                         hostname as the S3 origin — needs a 5.x provider of at least
#                         this vintage. The same floor is already used by
#                         `infra/modules/evidence-store`, so one provider version
#                         satisfies the whole repository and `terraform init` never has
#                         to reconcile two ranges.
#
#   aws <  7.0.0          A major-version bump is a breaking change by definition. Eight
#                         days from a deadline is not when to discover which resource
#                         changed shape.
#
# OpenTofu: everything in this root is in the common subset. `tofu init && tofu apply`
# works unchanged — there is no `terraform { encryption { … } }` block, no Terraform
# Cloud block, no provider outside `hashicorp/aws`. See README.md § "OpenTofu".

terraform {
  required_version = ">= 1.10.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.60.0, < 7.0.0"
    }
  }
}
