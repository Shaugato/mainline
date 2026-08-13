# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
#
# Same floors as `infra/modules/demo-api`, for the same reasons, plus one this module
# adds on its own.
#
# `hashicorp/archive` IS A NEW PROVIDER IN THIS REPOSITORY and it is here on purpose,
# with a measurement behind it rather than a preference.
#
# The responder is one 200-line Python file with no dependencies - `boto3` is in the
# managed python3.13 runtime. Terraform's `aws_lambda_function` takes `filename`,
# `s3_bucket` or `image_uri`; there is no inline-source form. So the zip has to come from
# somewhere, and the two candidates were:
#
#   (a) a build script writing `out/lambda/cost-guard-responder.zip`, which makes the
#       module unusable until somebody runs a second command, and puts a build step in
#       front of `terraform plan`;
#   (b) `data.archive_file`, which zips at plan time and needs nothing else.
#
# (b) was refused in `demo-api` for a real reason - `build_lambda.sh` fixes entry
# timestamps and entry ORDER so that `source_code_hash` moves only when the bytes move,
# and a hash that moved because the clock moved would show a Lambda update in every plan.
# A `data.archive_file` that inherited the source file's mtime would reintroduce exactly
# that defect, and `git clone` does not preserve mtimes, so every fresh checkout would
# plan a redeploy.
#
# MEASURED 2026-08-13 rather than assumed, with hashicorp/archive v2.8.0 on Terraform
# v1.14.8, in a scratch directory:
#
#     terraform plan            -> sha256(out.zip) = 079d3d3e26be0014...80036950
#     os.utime(src, 1000000000) # move the source mtime back to 2001
#     rm out.zip; terraform plan -> sha256(out.zip) = 079d3d3e26be0014...80036950
#
#     zipfile entry date_time  == (2049, 1, 1, 0, 0, 0)
#
# The provider writes a FIXED sentinel timestamp on every entry, so the archive is a
# function of the source BYTES alone. That is the property `build_lambda.sh` goes to
# trouble to get, obtained here for free, and it is why (b) is safe in this module and
# was not in that one. If a future provider release changes that sentinel, the symptom is
# a Lambda update in a plan that changed no source, and this comment is the place to look.
#
# Floor 2.4.0 rather than 2.8.0: 2.4.0 is where `output_base64sha256` and the deterministic
# archive both exist, and pinning the exact version measured above would turn a routine
# `terraform init -upgrade` into a diff nobody asked for. The ceiling is a major bump,
# which is a decision rather than an upgrade - same rule as the aws provider below.

terraform {
  required_version = ">= 1.6.0"

  required_providers {
    aws = {
      source = "hashicorp/aws"
      # Floor 6.0 and ceiling 7.0, identical to `infra/modules/demo-api/versions.tf`, so
      # that a root module composing both resolves ONE provider version rather than
      # discovering an unsatisfiable intersection at `init` time. This module reads
      # `data.aws_region.current.region`, which is the 6.0 attribute that replaced the
      # deprecated `.name`.
      version = ">= 6.0.0, < 7.0.0"
    }

    archive = {
      source  = "hashicorp/archive"
      version = ">= 2.4.0, < 3.0.0"
    }
  }
}
