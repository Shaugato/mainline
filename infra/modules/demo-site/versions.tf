# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
#
# THE COMMON SUBSET, ON PURPOSE.
#
# Terraform v1.14.8 is what is installed on the build machine; OpenTofu is not, and
# installing a second toolchain eight days from a deadline is risk with no return
# (docs/leads/deploy-plan.md §2.7). So this module is written to the intersection of the
# two: ONE provider (`hashicorp/aws`), no provider aliases, no Terraform Cloud / `cloud`
# block, no `moved`/`import` blocks, no provider-defined functions, no cross-variable
# references inside `validation` blocks. `tofu init && tofu validate && tofu apply` runs
# this directory unchanged.
#
# `>= 1.10.0` is not decoration. The env root that consumes this module uses the S3
# backend's native `use_lockfile` locking (deploy-plan.md §2.6), which landed in Terraform
# 1.10 / OpenTofu 1.10, and pinning the floor here stops someone planning the module with a
# CLI that would silently drop the lock in the root.

terraform {
  required_version = ">= 1.10.0"

  required_providers {
    aws = {
      source = "hashicorp/aws"

      # >= 5.72.0 because `origin_access_control_origin_type = "lambda"` — the whole point
      # of the second OAC — is rejected by the provider's own value validation on earlier
      # 5.x releases. < 7.0.0 matches infra/modules/evidence-store so that a single root
      # module can hold both without a version conflict.
      version = ">= 5.72.0, < 7.0.0"
    }
  }
}
