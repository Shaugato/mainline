# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
#
# ═══════════════════════════════════════════════════════════════════════════════════════
#  STATE — one S3 object, locked by S3 itself, with no DynamoDB table anywhere
# ═══════════════════════════════════════════════════════════════════════════════════════
#
# PARTIAL CONFIGURATION, ON PURPOSE. `bucket` is absent from this file and is supplied at
# `terraform init` time:
#
#     terraform init -backend-config="bucket=mainline-demo-tfstate-<account-id>"
#
# `<account-id>` IS A PLACEHOLDER AND NOT A VALUE TO COPY. It is the twelve digits printed
# by:
#
#     aws sts get-caller-identity --query Account --output text
#
# An earlier revision of this comment spelled a real account number here. That is an
# EXECUTABLE EXAMPLE — somebody pastes it — and an executable example carrying one
# account's id is wrong on every other account, so decision D2
# (`docs/leads/ship-final.md` §1.6) removes it. Nobody has to remember the digits in
# practice: `scripts/deploy/bootstrap_state.sh --bucket mainline-demo-tfstate-"$(aws sts
# get-caller-identity --query Account --output text)"` creates the bucket and PRINTS the
# finished `-backend-config` line to copy; `--print-backend-config` prints it and writes
# nothing.
#
# The bucket name has to be globally unique across all of S3, so it cannot be a constant
# in a repository that anybody else might clone; and the bucket cannot be created by the
# Terraform run that needs it to already exist. `bootstrap_state.sh` creates it with the
# AWS CLI — versioning on, all public access blocked, SSE-S3 on, tagged `project=mainline`.
# `scripts/deploy/deploy.sh` and `deploy.ps1` call it as step 1 and pass the name through.
# That is the whole of the chicken-and-egg, resolved without committing a state file and
# without a second Terraform root.
#
# `terraform init -backend=false` needs none of this and is what the committed plan
# evidence in `evidence/deploy/` was produced with: no state, no bucket, no lock, and
# therefore nothing an unreviewed plan run could disturb.
#
# `use_lockfile = true` is Terraform ≥ 1.10's native S3 locking: the lock is a
# `demo/terraform.tfstate.tflock` object written with a conditional PUT, released on
# completion, and breakable with `terraform force-unlock`. Before 1.10 this needed a
# DynamoDB table — a second stateful resource, $0.25/month, and one more thing teardown
# has to remember. There is no `dynamodb_table` argument here and there is no table in
# the account. See `docs/deploy/RUNBOOK.md` § "If a run says the state is locked".
#
# `encrypt = true` asks S3 for server-side encryption on the state object. The bucket
# also has SSE-S3 set as its default (bootstrap_state.sh), so this is belt and braces:
# the bucket policy is the control, this flag is the client saying so out loud.
#
# THE STATE FILE STILL HOLDS NO DATABASE PASSWORD. The CockroachDB Cloud DSN is written
# to SSM Parameter Store as a SecureString by the deploy script with `aws ssm
# put-parameter`, and Terraform is given only the parameter *name* (`var.dsn_parameter
# _name`). Terraform never reads the value, so `terraform show` cannot print it and this
# object cannot leak it. See `docs/leads/deploy-plan.md` § 2.5.

terraform {
  backend "s3" {
    key          = "demo/terraform.tfstate"
    region       = "ap-southeast-1"
    encrypt      = true
    use_lockfile = true
  }
}
