# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
#
# Terraform 1.14.8 is what is installed on the build machine; OpenTofu is not, and
# installing a second toolchain eight days from a deadline is risk with no return
# (docs/leads/deploy-plan.md sec 2.7). Nothing in this module uses a Terraform-only
# feature, so `tofu init && tofu apply` works unchanged - the floor below is 1.6 rather
# than 1.14 so that a stranger with an older binary is not turned away for no reason.
# The ENV ROOT pins the higher floor it needs for S3 native state locking; a module has
# no business asserting a backend requirement it does not configure.

terraform {
  required_version = ">= 1.6.0"

  required_providers {
    aws = {
      source = "hashicorp/aws"
      # Floor 6.0: this module reads `data.aws_region.current.region`, which is the
      # attribute that replaced the deprecated `.name` in provider 6.0. Reading `.name`
      # instead would emit a deprecation warning on every plan, and a plan whose warnings
      # are routinely ignored is a plan nobody reads. Ceiling 7.0 because a major bump is
      # a decision, not an upgrade.
      version = ">= 6.0.0, < 7.0.0"
    }
  }
}
