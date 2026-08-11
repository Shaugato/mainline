#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
#
# BEGIN-USAGE
# ══════════════════════════════════════════════════════════════════════════════════════
#  bootstrap_state.sh — the one resource Terraform cannot create for itself
# ══════════════════════════════════════════════════════════════════════════════════════
#
# `infra/envs/demo/backend.tf` declares an S3 backend with a partial configuration: it
# knows the key, the region, that it wants encryption and that it wants Terraform ≥ 1.10
# native S3 locking, but it does not know the bucket. The bucket name has to be globally
# unique across every AWS customer, so it cannot be a constant in a repository; and the
# bucket cannot be created by the Terraform run that requires it to already exist.
#
# This script closes that loop with four AWS CLI calls, and then prints the exact
# `-backend-config` line to hand to `terraform init`. There is no second Terraform root,
# no committed state file, and no `terraform init -backend=false` dance.
#
# THERE IS NO DYNAMODB TABLE, HERE OR ANYWHERE. Locking is `use_lockfile = true` — a
# conditional PUT of `demo/terraform.tfstate.tflock` into this same bucket, native since
# Terraform 1.10. That saves $0.25/month and, more usefully, removes a second stateful
# resource that teardown would have to find.
#
# IDEMPOTENT. Run it a hundred times. It creates the bucket if it is absent and re-asserts
# versioning, public-access-block, encryption and tags every time, because a bucket that
# somebody turned versioning off on is worse than a bucket that does not exist: the first
# silently loses the ability to recover a clobbered state file.
#
# ── THE BUCKET NAME, AND WHY NO ACCOUNT ID IS WRITTEN HERE (decision D2) ──────────────
#
# The default name is `mainline-demo-tfstate-<account id>`, and the account id is READ AT
# RUN TIME from the live caller identity:
#
#     aws sts get-caller-identity --query Account --output text
#
# It is not written in this file, in the example below, or anywhere else in the deploy
# scripts. Deriving it costs one API call this script was going to make anyway, keeps the
# name globally unique (S3 bucket names are shared across every AWS customer), and keeps
# the `mainline-demo-` prefix that `teardown.sh` keys its safety refusal on.
#
# `--expect-account` is the same guard `deploy.sh` and `teardown.sh` carry: name the
# account you mean and this script refuses to create anything in a different one. It is
# optional here and mandatory there, because this script's blast radius is one empty,
# private, versioned bucket and theirs is the whole stack.
#
# USAGE
#   scripts/deploy/bootstrap_state.sh                       # derive the name from STS
#   scripts/deploy/bootstrap_state.sh --expect-account <id>
#   scripts/deploy/bootstrap_state.sh --bucket mainline-demo-tfstate-<account id> \
#                                     --region ap-southeast-1 --profile mainline-dev
#   scripts/deploy/bootstrap_state.sh --print-backend-config --bucket <name>   # no writes
#
# EXIT CODES
#   0  the bucket exists, is versioned, is private, is encrypted and is tagged ours
#   2  usage error, or the bucket name does not carry the mainline-demo- prefix
#   3  the bucket exists but belongs to somebody else, is in the wrong region, or the
#      caller is not the account named by --expect-account
#   4  an AWS call failed
# END-USAGE

set -euo pipefail

BUCKET=""
REGION="ap-southeast-1"
PROFILE="${AWS_PROFILE:-}"
PRINT_ONLY=0
NAME_PREFIX="mainline-demo"
EXPECT_ACCOUNT="${MAINLINE_AWS_ACCOUNT:-}"

say()  { printf '%s\n' "$*"; }
step() { printf '  %-14s %s\n' "$1" "$2"; }
die()  { printf 'bootstrap_state: %s\n' "$1" >&2; exit "${2:-4}"; }

usage() {
  sed -n '/^# BEGIN-USAGE$/,/^# END-USAGE$/p' "$0" | sed '1d;$d' | sed 's/^# \{0,1\}//'
  exit "${1:-2}"
}

while [ $# -gt 0 ]; do
  case "$1" in
    --bucket)  BUCKET="${2:-}"; shift 2 ;;
    --region)  REGION="${2:-}"; shift 2 ;;
    --profile) PROFILE="${2:-}"; shift 2 ;;
    --expect-account) EXPECT_ACCOUNT="${2:-}"; shift 2 ;;
    --print-backend-config) PRINT_ONLY=1; shift ;;
    -h|--help) usage 0 ;;
    *) printf 'bootstrap_state: unknown argument %s\n' "$1" >&2; usage 2 ;;
  esac
done

# --print-backend-config makes no AWS call at all, so it is the one mode that cannot
# derive a name and must be given one.
if [ "$PRINT_ONLY" -eq 1 ] && [ -z "$BUCKET" ]; then
  printf 'bootstrap_state: --print-backend-config needs --bucket; it makes no AWS call and\n' >&2
  printf '  therefore cannot read the account id to derive the name from.\n' >&2
  usage 2
fi

# An explicitly supplied name is checked BEFORE any AWS call, so a typo is answered with
# the typo rather than with a credentials error. A derived name is checked again below,
# after the account id is known — the same `case`, because there is one rule.
if [ -n "$BUCKET" ]; then
  case "$BUCKET" in
    mainline-demo-*) : ;;
    *) die "bucket name '$BUCKET' must start with '${NAME_PREFIX}-'.
  scripts/deploy/teardown.sh keys its refusal on that prefix. Omit --bucket entirely and
  this script derives ${NAME_PREFIX}-tfstate-<account id> from the live caller identity." 2 ;;
  esac
fi

AWSCLI=(aws)
[ -n "$PROFILE" ] && AWSCLI+=(--profile "$PROFILE")
AWSCLI+=(--region "$REGION" --output text --no-cli-pager)

backend_config() {
  say ""
  say "  terraform init \\"
  say "    -backend-config=\"bucket=$BUCKET\" \\"
  say "    -backend-config=\"region=$REGION\""
  say ""
}

if [ "$PRINT_ONLY" -eq 1 ]; then
  backend_config
  exit 0
fi

command -v aws >/dev/null 2>&1 || die "the AWS CLI is not on PATH." 4

ACCOUNT="$("${AWSCLI[@]}" sts get-caller-identity --query Account 2>/dev/null)" \
  || die "aws sts get-caller-identity failed. Are the credentials for profile '${PROFILE:-<default>}' valid?" 4

if [ -n "$EXPECT_ACCOUNT" ] && [ "$ACCOUNT" != "$EXPECT_ACCOUNT" ]; then
  die "this is account $ACCOUNT. You said $EXPECT_ACCOUNT. Creating nothing.
  Fix the profile (--profile <name>) or the expectation (--expect-account <id>)." 3
fi

# ── The name, derived rather than written down (decision D2) ──────────────────────────
DERIVED=0
if [ -z "$BUCKET" ]; then
  BUCKET="${NAME_PREFIX}-tfstate-${ACCOUNT}"
  DERIVED=1
fi

# ── THE SAFETY REFUSAL ────────────────────────────────────────────────────────────────
#
# This account holds seven buckets belonging to unrelated live projects. Everything this
# repository creates carries the `mainline-demo-` prefix, and `scripts/deploy/teardown.sh`
# will delete a bucket only if it carries that prefix. A state bucket named anything else
# would be created here and then be undeletable by our own teardown — so it is refused at
# the point of creation instead, where the fix is free.
case "$BUCKET" in
  mainline-demo-*) : ;;
  *) die "bucket name '$BUCKET' must start with '${NAME_PREFIX}-'.
  scripts/deploy/teardown.sh keys its refusal on that prefix, and this account holds
  seven buckets across unrelated projects. A bucket outside the prefix would be
  unmanageable by our own tools. Omit --bucket entirely and this script derives
  ${NAME_PREFIX}-tfstate-<account id> from the live caller identity." 2 ;;
esac

say "bootstrap_state"
step "account" "$ACCOUNT"
step "region"  "$REGION"
step "bucket"  "$BUCKET$([ "$DERIVED" -eq 1 ] && printf '   (derived from sts get-caller-identity)')"

# ── Does it exist, and is it ours? ────────────────────────────────────────────────────
#
# head-bucket distinguishes three cases by exit status and stderr: absent (404), present
# and ours (0), present and somebody else's (403). Conflating the last two is how a
# deploy writes state into a stranger's bucket, so 403 is a hard stop, not a retry.
if HEAD_ERR="$("${AWSCLI[@]}" s3api head-bucket --bucket "$BUCKET" 2>&1)"; then
  step "exists" "yes — re-asserting configuration"
  EXISTED=1
else
  case "$HEAD_ERR" in
    *404*|*"Not Found"*|*NoSuchBucket*)
      EXISTED=0 ;;
    *403*|*Forbidden*)
      die "bucket '$BUCKET' exists and this account cannot access it. It belongs to
  somebody else — S3 bucket names are global. Choose another name; do NOT retry." 3 ;;
    *)
      die "head-bucket on '$BUCKET' failed in a way this script does not understand:
  $HEAD_ERR" 4 ;;
  esac
fi

if [ "$EXISTED" -eq 0 ]; then
  step "exists" "no — creating"
  # us-east-1 is the one region where LocationConstraint must be omitted; every other
  # region requires it. This stack is ap-southeast-1, but the branch costs one line and
  # removes a failure that reads like a permissions problem when it is not.
  if [ "$REGION" = "us-east-1" ]; then
    "${AWSCLI[@]}" s3api create-bucket --bucket "$BUCKET" >/dev/null \
      || die "create-bucket failed for '$BUCKET'." 4
  else
    "${AWSCLI[@]}" s3api create-bucket --bucket "$BUCKET" \
      --create-bucket-configuration "LocationConstraint=$REGION" >/dev/null \
      || die "create-bucket failed for '$BUCKET'." 4
  fi
  "${AWSCLI[@]}" s3api wait bucket-exists --bucket "$BUCKET" \
    || die "the bucket was created but never became visible." 4
  step "created" "ok"
fi

# ── Region check ──────────────────────────────────────────────────────────────────────
#
# A pre-existing bucket in another region silently breaks the backend: Terraform signs
# for `region`, S3 answers 301. Better to say so here.
if ! LOC="$("${AWSCLI[@]}" s3api get-bucket-location --bucket "$BUCKET" --query LocationConstraint 2>&1)"; then
  die "get-bucket-location on '$BUCKET' failed, and a region this script could not read is
  not a region it may assume is right:
  $LOC" 4
fi
# `None` is how the API renders "no LocationConstraint", which means us-east-1.
[ "$LOC" = "None" ] && LOC="us-east-1"
if [ -n "$LOC" ] && [ "$LOC" != "$REGION" ]; then
  die "bucket '$BUCKET' lives in '$LOC' but this backend is configured for '$REGION'.
  S3 answers 301 to a signed request for the wrong region and Terraform reports it as a
  credentials problem. Use --region $LOC, or a different bucket." 3
fi

# ── Versioning: the ability to recover a clobbered state file ─────────────────────────
"${AWSCLI[@]}" s3api put-bucket-versioning --bucket "$BUCKET" \
  --versioning-configuration Status=Enabled >/dev/null \
  || die "could not enable versioning on '$BUCKET'." 4
step "versioning" "Enabled"

# ── Public access: all four blocks, unconditionally ───────────────────────────────────
"${AWSCLI[@]}" s3api put-public-access-block --bucket "$BUCKET" \
  --public-access-block-configuration \
  "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true" >/dev/null \
  || die "could not block public access on '$BUCKET'." 4
step "public" "blocked (all four)"

# ── Encryption: SSE-S3, not SSE-KMS ───────────────────────────────────────────────────
#
# AES256 and not a customer-managed key, for the same reason `infra/modules/evidence
# -store` gives: a deletable key over data whose whole purpose is to still be there later
# is a delete button with extra steps. The state file holds no secret — the DSN is in SSM
# and Terraform never reads it — so a CMK would buy no confidentiality and would add a
# crypto-shredding surface. `BucketKeyEnabled` is set anyway; it costs nothing and is the
# right default if somebody later swaps AES256 for aws:kms.
"${AWSCLI[@]}" s3api put-bucket-encryption --bucket "$BUCKET" \
  --server-side-encryption-configuration \
  '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"},"BucketKeyEnabled":true}]}' >/dev/null \
  || die "could not set default encryption on '$BUCKET'." 4
step "encryption" "SSE-S3 (AES256)"

# ── Tags: what makes this bucket deletable by our own teardown ────────────────────────
"${AWSCLI[@]}" s3api put-bucket-tagging --bucket "$BUCKET" --tagging \
  'TagSet=[{Key=project,Value=mainline},{Key=managed_by,Value=bootstrap_state.sh},{Key=mainline:role,Value=terraform-state}]' >/dev/null \
  || die "could not tag '$BUCKET'. teardown.sh refuses to delete an untagged bucket, so
  this is fatal rather than cosmetic." 4
step "tags" "project=mainline, mainline:role=terraform-state"

# ── Lifecycle: keep the last few noncurrent state versions, not all of them forever ────
#
# Versioning is on for recovery, not for archaeology. Thirty days of noncurrent versions
# is more than enough to undo a bad apply and keeps the bucket's size — and therefore its
# $0.01/month — from being a function of how many times we deployed.
"${AWSCLI[@]}" s3api put-bucket-lifecycle-configuration --bucket "$BUCKET" \
  --lifecycle-configuration '{"Rules":[{"ID":"expire-noncurrent-state","Status":"Enabled","Filter":{"Prefix":""},"NoncurrentVersionExpiration":{"NoncurrentDays":30},"AbortIncompleteMultipartUpload":{"DaysAfterInitiation":7}}]}' >/dev/null \
  || die "could not set the lifecycle rule on '$BUCKET'." 4
step "lifecycle" "noncurrent versions expire after 30 days"

say ""
say "State backend ready. Native S3 locking — there is no DynamoDB table."
backend_config
