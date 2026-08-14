#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
#
# BEGIN-USAGE
# ══════════════════════════════════════════════════════════════════════════════════════
#  plan_repro.sh — reproduce the shipping Terraform plan without one mutating AWS call
# ══════════════════════════════════════════════════════════════════════════════════════
#
# THE PROBLEM THIS SOLVES. `infra/envs/demo/backend.tf` declares a PARTIAL S3 backend: it
# fixes the key, the region, encryption and `use_lockfile`, but not the bucket, because an
# S3 bucket name must be globally unique across every AWS customer and therefore cannot be
# a constant in a repository anybody can clone. So `terraform init` with no
# `-backend-config` cannot complete, `terraform init -backend=false` completes but leaves
# `plan` refusing with *"Changes to backend configurations require reinitialization"*, and
# the only documented way to get a real bucket is `bootstrap_state.sh`, which CREATES one.
# Creating a bucket is a mutating AWS call, and a reviewer asked to reproduce a plan should
# not have to write to the account to do it.
#
# ── THE EQUIVALENCE THIS SCRIPT RESTS ON, AND WHEN IT EXPIRES ─────────────────────────
#
# This script points Terraform at a LOCAL backend whose state file lives outside the
# repository and starts empty. That is only a faithful reproduction of the shipping plan
# because NOTHING HAS BEEN APPLIED: the remote S3 state is empty, an empty local state and
# an empty remote state contain the same zero resources, and a plan is a function of the
# configuration plus the state. Same configuration, same (empty) state, same plan.
#
# THAT EQUIVALENCE EXPIRES AT THE FIRST `terraform apply`. From the moment one resource
# exists in the remote state, a plan against an empty local state will report creating
# resources that already exist, and every count it prints will be wrong in the direction
# that reads like success. So this script does not merely assert the precondition in a
# comment — it MEASURES it, read-only, on every run (stage 2), and refuses to plan when it
# no longer holds. After the first apply, use the real S3 backend
# (`docs/deploy/RUNBOOK.md` § 5.6.2); this script will tell you so and exit 5.
#
# ── WHAT IT WILL NOT DO ───────────────────────────────────────────────────────────────
#
# Every Terraform invocation goes through one wrapper, `tf`, which carries an ALLOWLIST of
# `init`, `validate`, `plan`, `show` and `version`. `apply`, `destroy`, `import`, `state`,
# `taint` and `force-unlock` are refused by name, before `terraform` is executed, with exit
# 2. `--prove-refusal` runs that refusal as a negative control in one second and prints the
# result, so the guard is falsifiable rather than claimed:
#
#     scripts/deploy/plan_repro.sh --prove-refusal
#
# The AWS calls this script makes are `sts get-caller-identity`, `s3api list-buckets`,
# `s3api head-object`, `lambda get-function` and whatever the AWS provider reads for the
# plan itself (`data.aws_caller_identity`). Every one of them is read-only.
# `bootstrap_state.sh` is NOT called except under `--print-backend-config`, which that
# script documents as making zero AWS calls.
#
# USAGE
#   scripts/deploy/plan_repro.sh                          # the shipping plan (FURL)
#   scripts/deploy/plan_repro.sh --cloudfront             # the enable_cloudfront variant
#   scripts/deploy/plan_repro.sh --out-dir /path          # where the plan text is written
#   scripts/deploy/plan_repro.sh --json                   # also emit `terraform show -json`
#   scripts/deploy/plan_repro.sh --print-backend-config   # the real-S3 init line, no plan
#   scripts/deploy/plan_repro.sh --prove-refusal          # negative control, no AWS calls
#   scripts/deploy/plan_repro.sh --prove-expiry-refusal <fn> --region <r>
#                                                         # negative control for stage 2
#
# EXIT CODES
#   0  the plan was reproduced and agrees with the committed artefact
#   2  usage error, or a mutating Terraform subcommand was refused
#   3  no usable AWS identity, or the caller is not the account named by --expect-account
#   5  THE EMPTY-STATE EQUIVALENCE DOES NOT HOLD, or could not be established read-only
#   6  the plan was produced and DISAGREES with the committed artefact — the artefact is
#      stale and must be regenerated. This script never edits it
#   7  terraform init, validate or plan failed
#   8  the run left residue in the working tree (this should be unreachable)
#   9  the plan is valid but carries a value PRE-APPLY.md's gate refuses (§ G6)
#  10  a GITIGNORED BUILD INPUT the plan reads is missing — the deployment zip named by
#      `var.lambda_package_path`. A fresh clone never has it; `scripts/deploy/
#      build_lambda.sh` makes it. Measured from a fresh clone on 2026-08-14: without this
#      check the run got as far as rendering the whole plan and then died inside
#      `filebase64sha256`, which reads as a Terraform bug rather than a missing build
# END-USAGE

set -euo pipefail

# ── Where things are ──────────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/../.." && pwd)"
ENV_DIR="$REPO_ROOT/infra/envs/demo"
OVERRIDE="$ENV_DIR/backend_override.tf"

REGION="ap-southeast-1"
PROFILE="${AWS_PROFILE:-mainline-dev}"
EXPECT_ACCOUNT="${MAINLINE_AWS_ACCOUNT:-}"
STATE_BUCKET=""
OUT_DIR=""
WANT_CLOUDFRONT=0
WANT_JSON=0
MODE="plan"
FUNCTION_NAME="mainline-demo-api"

say()  { printf '%s\n' "$*"; }
step() { printf '  %-22s %s\n' "$1" "$2"; }
die()  { printf '\nplan_repro: %s\n' "$1" >&2; exit "${2:-4}"; }

usage() {
  sed -n '/^# BEGIN-USAGE$/,/^# END-USAGE$/p' "$0" | sed '1d;$d' | sed 's/^# \{0,1\}//'
  exit "${1:-2}"
}

# ══════════════════════════════════════════════════════════════════════════════════════
#  THE REFUSAL. One wrapper, one allowlist, checked before `terraform` is executed.
# ══════════════════════════════════════════════════════════════════════════════════════
#
# A script that says it is read-only in its header is a claim. This is the mechanism. It
# is deliberately not a grep over the file — a grep can be satisfied by spelling `apply`
# in a variable — it is the single point every Terraform invocation in this file passes
# through, and `--prove-refusal` demonstrates it refusing.
TF_ALLOWED='init validate plan show version'

tf() {
  local sub="${1:-}"
  case " $TF_ALLOWED " in
    *" $sub "*) : ;;
    *)
      printf 'plan_repro: REFUSED — `terraform %s` is not on this script'"'"'s allowlist.\n' "$sub" >&2
      printf '  Allowed: %s\n' "$TF_ALLOWED" >&2
      printf '  This script is read-only by construction. It does not apply, and it cannot\n' >&2
      printf '  be persuaded to. The apply belongs to the orchestrator with the founder,\n' >&2
      printf '  behind MAINLINE_APPLY_APPROVED=1 in scripts/deploy/deploy.sh.\n' >&2
      exit 2 ;;
  esac
  # `-destroy` turns `plan` into a destroy plan. Still non-mutating, still not the plan
  # the founder is approving, so it is refused for correctness rather than for safety.
  local a
  for a in "$@"; do
    case "$a" in
      -destroy|-refresh-only|-auto-approve)
        printf 'plan_repro: REFUSED — `%s` does not belong in a reproduction of the\n' "$a" >&2
        printf '  shipping plan.\n' >&2
        exit 2 ;;
    esac
  done
  ( cd "$ENV_DIR" && terraform "$@" )
}

prove_refusal() {
  say "plan_repro --prove-refusal — the negative control for the read-only claim"
  say ""
  say "Nothing below touches AWS. Each line calls the same wrapper every real Terraform"
  say "invocation in this script goes through, and shows it refusing."
  say ""
  local sub rc
  local failures=0
  for sub in apply destroy import taint force-unlock state; do
    rc=0
    ( tf "$sub" >/dev/null 2>&1 ) || rc=$?
    if [ "$rc" -eq 2 ]; then
      step "terraform $sub" "REFUSED, exit 2   [ok]"
    else
      step "terraform $sub" "NOT REFUSED, exit $rc   [THIS IS A DEFECT]"
      failures=$((failures + 1))
    fi
  done
  rc=0
  ( tf plan -destroy >/dev/null 2>&1 ) || rc=$?
  if [ "$rc" -eq 2 ]; then
    step "terraform plan -destroy" "REFUSED, exit 2   [ok]"
  else
    step "terraform plan -destroy" "NOT REFUSED, exit $rc   [THIS IS A DEFECT]"
    failures=$((failures + 1))
  fi
  say ""
  if [ "$failures" -ne 0 ]; then
    die "$failures of the seven refusals did not fire. The read-only claim is FALSE." 1
  fi
  say "Seven refusals, seven exits of 2. The allowlist is: $TF_ALLOWED"
  say "A reviewer who does not believe the header can run this in one second."
  exit 0
}

# ── Arguments ─────────────────────────────────────────────────────────────────────────
while [ $# -gt 0 ]; do
  case "$1" in
    --region)          REGION="${2:-}"; shift 2 ;;
    --profile)         PROFILE="${2:-}"; shift 2 ;;
    --expect-account)  EXPECT_ACCOUNT="${2:-}"; shift 2 ;;
    --state-bucket)    STATE_BUCKET="${2:-}"; shift 2 ;;
    --out-dir)         OUT_DIR="${2:-}"; shift 2 ;;
    --cloudfront)      WANT_CLOUDFRONT=1; shift ;;
    --json)            WANT_JSON=1; shift ;;
    --print-backend-config) MODE="backend-config"; shift ;;
    --prove-refusal)   MODE="prove-refusal"; shift ;;
    --prove-expiry-refusal) MODE="prove-expiry"; FUNCTION_NAME="${2:-}"; shift 2
                       [ -n "$FUNCTION_NAME" ] || { printf 'plan_repro: --prove-expiry-refusal needs a function name that EXISTS.\n' >&2; usage 2; } ;;
    -h|--help)         usage 0 ;;
    *) printf 'plan_repro: unknown argument %s\n' "$1" >&2; usage 2 ;;
  esac
done

[ "$MODE" = "prove-refusal" ] && prove_refusal

# TF_CLI_ARGS is injected into every Terraform invocation by the environment and would
# defeat the allowlist above by adding flags this script never wrote. It is refused rather
# than tolerated: a reproduction that silently picked up an extra `-var` is not one.
for v in $(env | sed -n 's/^\(TF_CLI_ARGS[A-Za-z_]*\)=.*/\1/p'); do
  die "$v is set in this environment. It would be spliced into every Terraform command
  and this script could no longer state what it ran. Unset it and re-run." 2
done

command -v terraform >/dev/null 2>&1 || die "terraform is not on PATH." 3
command -v aws       >/dev/null 2>&1 || die "the AWS CLI is not on PATH." 3

AWSCLI=(aws)
[ -n "$PROFILE" ] && AWSCLI+=(--profile "$PROFILE")
AWSCLI+=(--region "$REGION" --output text --no-cli-pager)

# ── ONE IDENTITY, NOT TWO ──────────────────────────────────────────────────────────────
#
# Stage 1 proves an identity with the AWS CLI and `--profile`. Terraform's AWS provider
# resolves its own credentials independently, and the FIRST version of this script did not
# hand it the profile at all: the CLI answered from `mainline-dev`, Terraform fell through
# to the default chain, and `plan` died on
#
#     InvalidClientTokenId: The security token included in the request is invalid
#
# after printing a plausible-looking output diff. A script whose two halves can disagree
# about who they are is a script that proves nothing, so the profile is EXPORTED here and
# the two collapse into one.
#
# Static keys in the environment outrank AWS_PROFILE in the Go SDK but are outranked by
# `--profile` in the CLI — the exact configuration in which the two halves silently differ
# again. It is refused rather than ranked.
if [ -n "${AWS_ACCESS_KEY_ID:-}" ] && [ -n "$PROFILE" ]; then
  die "AWS_ACCESS_KEY_ID is set in this environment AND a profile ($PROFILE) was chosen.
  The AWS CLI would honour the profile and the Terraform provider would honour the keys,
  so the identity this script PROVES would not be the identity that plans. Unset the keys,
  or run with --profile '' to use them for both." 3
fi
export AWS_PROFILE="$PROFILE"
export AWS_REGION="$REGION"
export AWS_DEFAULT_REGION="$REGION"
[ -z "$PROFILE" ] && unset AWS_PROFILE

# ══════════════════════════════════════════════════════════════════════════════════════
#  STAGE 1 · Identity — read-only, and the account id is masked in everything printed
# ══════════════════════════════════════════════════════════════════════════════════════
say "plan_repro — reproducing the shipping plan with no mutating AWS call"
say ""
say "== 1 · identity (read-only)"

ACCOUNT="$("${AWSCLI[@]}" sts get-caller-identity --query Account 2>/dev/null || true)"
[ -n "$ACCOUNT" ] || die "aws sts get-caller-identity returned nothing. A plan needs a
  readable identity: the root reads data.aws_caller_identity.current. Set AWS_PROFILE
  (default here: $PROFILE) and try again." 3

# Everything this script prints goes through mask(). The account id is not a credential,
# but decision D2 keeps it out of tracked files, and a transcript pasted into an issue is
# one copy-paste away from being one.
mask() { sed -e "s/$ACCOUNT/<account>/g"; }

CALLER_ARN="$("${AWSCLI[@]}" sts get-caller-identity --query Arn)"
step "caller" "$(printf '%s' "$CALLER_ARN" | mask)"
step "region" "$REGION"
step "profile" "${PROFILE:-<none>}"

if [ -n "$EXPECT_ACCOUNT" ] && [ "$EXPECT_ACCOUNT" != "$ACCOUNT" ]; then
  die "this is not the account you named. Reading a plan for the wrong account is worse
  than reading none, because it looks like an answer. Fix --profile or --expect-account." 3
fi

if [ "$MODE" = "backend-config" ]; then
  BUCKET="${STATE_BUCKET:-mainline-demo-tfstate-$ACCOUNT}"
  say ""
  say "== the REAL S3 backend init line (this mode makes no further AWS call)"
  say ""
  bash "$SCRIPT_DIR/bootstrap_state.sh" --print-backend-config --bucket "$BUCKET" --region "$REGION"
  say ""
  say "  The bucket above does not exist yet. Creating it is scripts/deploy/bootstrap_state.sh"
  say "  WITHOUT --print-backend-config, and that is the FIRST MUTATING ACTION of the whole"
  say "  deploy. It belongs to the orchestrator with the founder. No worker runs it."
  say ""
  say "  That line contains your AWS account id. It is not a credential, but do not paste"
  say "  it into a tracked file: scripts/submission/audit_public_readiness.py fails on it."
  exit 0
fi

# ══════════════════════════════════════════════════════════════════════════════════════
#  STAGE 2 · THE EQUIVALENCE, MEASURED — not assumed, and not merely commented
# ══════════════════════════════════════════════════════════════════════════════════════
#
# Three read-only questions, in the order that a "no" to any one of them invalidates the
# local-backend reproduction:
#
#   a. does any `mainline-demo-tfstate-*` bucket exist at all?
#   b. if one does, does it hold `demo/terraform.tfstate`?
#   c. independently of any bucket name, does the demo Lambda exist?
#
# (c) is the one that closes the hole in (a) and (b): an operator who bootstrapped a
# non-default bucket name would pass (a) and (b) for the wrong reason. Asking AWS whether
# the thing the plan would create already exists does not depend on knowing where the
# state lives.
#
# THIS CHECK CANNOT BE FALSIFIED ON AN UNAPPLIED ACCOUNT WITHOUT APPLYING, which is the
# one thing this wave may not do. `--prove-expiry-refusal <name>` therefore runs THIS
# FUNCTION ONLY, against a Lambda that does exist somewhere in the account, and asserts it
# exits 5. It never proceeds to a plan, so it cannot be used to wave the guard through.
check_equivalence() {
say ""
say "== 2 · the empty-state equivalence, measured read-only"

BUCKETS="$("${AWSCLI[@]}" s3api list-buckets \
  --query "Buckets[?starts_with(Name,'mainline-demo-tfstate-')].Name" 2>/dev/null || echo "__ERROR__")"
[ "$BUCKETS" = "__ERROR__" ] && die "s3api list-buckets failed. 'I could not tell' is not
  'the state is empty', so this run stops here rather than planning against an assumption." 5

if [ -n "$STATE_BUCKET" ]; then
  BUCKETS="$BUCKETS $STATE_BUCKET"
fi

if [ -z "${BUCKETS// /}" ]; then
  step "state buckets" "none — no mainline-demo-tfstate-* bucket in this account"
else
  step "state buckets" "$(printf '%s' "$BUCKETS" | mask)"
  for b in $BUCKETS; do
    HEAD_RC=0
    HEAD_ERR="$("${AWSCLI[@]}" s3api head-object --bucket "$b" --key demo/terraform.tfstate 2>&1)" || HEAD_RC=$?
    if [ "$HEAD_RC" -eq 0 ]; then
      die "THE EQUIVALENCE HAS EXPIRED.

  s3://$(printf '%s' "$b" | mask)/demo/terraform.tfstate EXISTS, so something has been
  applied. A plan against an empty LOCAL state would report creating resources that
  already exist — a wrong number that reads like success.

  Use the real S3 backend instead. docs/deploy/RUNBOOK.md § 5.6.2 has the procedure:
      scripts/deploy/plan_repro.sh --print-backend-config
      cd infra/envs/demo && terraform init -reconfigure -backend-config=... && terraform plan" 5
    fi
    case "$HEAD_ERR" in
      *404*|*"Not Found"*|*NoSuchBucket*|*NoSuchKey*)
        step "  $b" "no demo/terraform.tfstate   [equivalence holds]" ;;
      *)
        die "head-object on that bucket failed in a way this script does not understand,
  and an unreadable state is not an empty state:
  $(printf '%s' "$HEAD_ERR" | mask)" 5 ;;
    esac
  done
fi

LAMBDA_RC=0
LAMBDA_ERR="$("${AWSCLI[@]}" lambda get-function --function-name "$FUNCTION_NAME" 2>&1)" || LAMBDA_RC=$?
if [ "$LAMBDA_RC" -eq 0 ]; then
  die "THE EQUIVALENCE HAS EXPIRED — the Lambda '$FUNCTION_NAME' already exists in
  $REGION. Whatever the state bucket is called, this stack has been applied. See
  docs/deploy/RUNBOOK.md § 5.6.2 for the real-backend plan, and § 6 for teardown." 5
fi
case "$LAMBDA_ERR" in
  *ResourceNotFoundException*|*"Function not found"*)
    step "lambda $FUNCTION_NAME" "does not exist   [equivalence holds]" ;;
  *)
    die "lambda get-function failed in a way this script does not understand:
  $(printf '%s' "$LAMBDA_ERR" | mask)" 5 ;;
esac

say ""
say "  NOTHING HAS BEEN APPLIED, so the remote S3 state is empty, so a plan against an"
say "  empty LOCAL state is resource-identical to a plan against the empty remote state."
say "  THIS EQUIVALENCE EXPIRES AT THE FIRST APPLY, and stage 2 re-measures it every run."
}

if [ "$MODE" = "prove-expiry" ]; then
  say ""
  say "== negative control: does stage 2 actually refuse when the stack already exists?"
  say "   probing for Lambda '$FUNCTION_NAME' in $REGION, which is expected to EXIST."
  RC=0
  ( check_equivalence ) || RC=$?
  say ""
  if [ "$RC" -eq 5 ]; then
    step "verdict" "REFUSED with exit 5   [ok — the expiry guard fires]"
    exit 0
  fi
  step "verdict" "exit $RC, expected 5   [THE EXPIRY GUARD IS A DECORATION]"
  exit 1
fi

check_equivalence

# ══════════════════════════════════════════════════════════════════════════════════════
#  STAGE 2b · THE GITIGNORED BUILD INPUT THE PLAN READS, checked before terraform is asked
# ══════════════════════════════════════════════════════════════════════════════════════
#
# MEASURED 2026-08-14 from a genuinely fresh clone of github.com/Shaugato/mainline at
# `eefae1c`: stage 1, stage 2, `init -reconfigure` and `validate` all succeeded, the plan
# rendered its whole output diff, and only then did the run die with
#
#   Error: Error in function call
#     on ..\..\modules\demo-api\main.tf line 342, in resource "aws_lambda_function" "this":
#    342:   source_code_hash = filebase64sha256(var.package_path)
#   Call to function "filebase64sha256" failed: open
#   ..\..\..\out\lambda\mainline-demo-api-arm64.zip: The system cannot find the path
#   specified.
#
# `out/` is gitignored (`.gitignore:9`), so the deployment zip is NOT in a fresh clone,
# and `filebase64sha256` is evaluated at PLAN time rather than at apply time. Without
# this check a reviewer meets that as a Terraform stack trace ninety seconds into a run
# that has already printed four green steps. The refusal is a NEW exit code, not a
# relaxation of anything: nothing here touches the allowlist or the stage-2 equivalence.
#
# The path is read out of the root's own `default` rather than hardcoded here, so moving
# `variable "lambda_package_path"` cannot leave this check pointing at the wrong file and
# reporting a green.
say ""
say "== 2b · the build inputs the plan reads (gitignored; not in a fresh clone)"

PKG_REL="$(awk '/^variable "lambda_package_path"/{f=1}
                f && /^ *default *=/{sub(/^ *default *= *"/,""); sub(/".*$/,""); print; exit}' \
           "$ENV_DIR/variables.tf")"
if [ -z "$PKG_REL" ]; then
  step "package path" "UNREADABLE from $ENV_DIR/variables.tf — skipping this check"
else
  PKG_ABS="$ENV_DIR/$PKG_REL"
  if [ -f "$PKG_ABS" ]; then
    step "lambda package" "$PKG_REL   [present]"
  else
    die "THE PLAN CANNOT BE PRODUCED: the deployment package is missing.

  var.lambda_package_path defaults to
      $PKG_REL
  resolved against infra/envs/demo, and no file is there.

  \`out/\` is gitignored, so a FRESH CLONE never has it, and
  infra/modules/demo-api/main.tf:342 calls filebase64sha256() on it at PLAN time — so
  this is not an apply-time problem you can defer. Build it first:

      scripts/deploy/build_lambda.sh          # arm64, the deployed default

  and note that the build reads verticals/mainline/apps/console/dist/, which is ALSO a
  gitignored build output — build the console before the package. docs/deploy/
  terraform-plan.md § 1.3 is the numbered fresh-clone runbook and lists both in order.

  The package's bytes reach the plan as ONE value, source_code_hash. It does not change
  the resource count, so a plan produced with a different package is still 'Plan: 24 to
  add' — but it is not byte-identical to the committed artefact, and § 1.3 says which
  differences are expected and which would be findings." 10
  fi
fi

# ══════════════════════════════════════════════════════════════════════════════════════
#  STAGE 3 · The override, written outside the repository's state and removed on any exit
# ══════════════════════════════════════════════════════════════════════════════════════
if [ -z "$OUT_DIR" ]; then
  OUT_DIR="${TMPDIR:-${TEMP:-/tmp}}/mainline-plan-repro"
fi
mkdir -p "$OUT_DIR"
OUT_DIR="$(cd -- "$OUT_DIR" && pwd)"

case "$OUT_DIR" in
  "$REPO_ROOT"|"$REPO_ROOT"/*)
    die "--out-dir is inside the repository ($OUT_DIR). The raw plan text contains your
  AWS account id unmasked; writing it into the tree is how it reaches a commit. Choose a
  path outside $REPO_ROOT." 2 ;;
esac

# Terraform here is a native Windows binary; an MSYS path like /c/Users/... is not a path
# it can open. This is the same class of bug that broke the first real teardown.
tfpath() { if command -v cygpath >/dev/null 2>&1; then cygpath -m "$1"; else printf '%s' "$1"; fi; }

if [ -e "$OVERRIDE" ]; then
  die "$OVERRIDE already exists. This script writes and removes that file, and it will
  not clobber somebody else's. Remove it, or find out who is mid-run." 2
fi

STATE_PATH="$(tfpath "$OUT_DIR")/demo-plan.tfstate"

# The residue check compares the working tree AFTER the run against a snapshot taken
# BEFORE it. The first version compared against "clean" and reported six files another
# worker had modified hours earlier as this script's residue — an alarm that cries wolf is
# an alarm somebody turns off. What this script is answerable for is the DELTA it caused.
GIT_OK=""
STATUS_BEFORE=""
if git -C "$REPO_ROOT" rev-parse --git-dir >/dev/null 2>&1; then
  GIT_OK=1
  STATUS_BEFORE="$(git -C "$REPO_ROOT" status --porcelain -- infra/envs/demo 2>/dev/null || true)"
fi

cleanup() {
  local rc=$?
  rm -f "$OVERRIDE"
  # Return the directory to "Backend initialization required" so the next operator has to
  # init deliberately rather than inheriting this run's local backend.
  rm -f "$ENV_DIR/.terraform/terraform.tfstate"
  if [ -n "${GIT_OK:-}" ]; then
    local after delta
    after="$(git -C "$REPO_ROOT" status --porcelain -- infra/envs/demo 2>/dev/null || true)"
    delta="$(printf '%s\n' "$after" | grep -Fxv -f <(printf '%s\n' "$STATUS_BEFORE") || true)"
    delta="$(printf '%s' "$delta" | sed '/^[[:space:]]*$/d')"
    if [ -n "$delta" ]; then
      printf '\nplan_repro: THIS RUN changed infra/envs/demo, and it should not have:\n%s\n' "$delta" >&2
      [ "$rc" -eq 0 ] && rc=8
    fi
  fi
  exit "$rc"
}
trap cleanup EXIT

say ""
say "== 3 · a local backend, outside the repository, starting empty"
cat > "$OVERRIDE" <<EOF
# WRITTEN BY scripts/deploy/plan_repro.sh AND REMOVED ON EXIT. NEVER COMMIT THIS FILE.
terraform {
  backend "local" {
    path = "$STATE_PATH"
  }
}
EOF
step "override" "infra/envs/demo/backend_override.tf  (removed on exit, any exit)"
step "state path" "$STATE_PATH"
step "state now" "$([ -s "$OUT_DIR/demo-plan.tfstate" ] && echo 'NOT EMPTY — see stage 2' || echo 'absent/empty')"

# ══════════════════════════════════════════════════════════════════════════════════════
#  STAGE 4 · init, validate, plan — the three subcommands, through the allowlist
# ══════════════════════════════════════════════════════════════════════════════════════
say ""
say "== 4 · terraform init -reconfigure / validate / plan"

if [ "$WANT_CLOUDFRONT" -eq 1 ]; then
  CF="true";  LABEL="cloudfront"; ARTEFACT="$REPO_ROOT/evidence/deploy/terraform-plan-cloudfront.txt"
else
  CF="false"; LABEL="furl";       ARTEFACT="$REPO_ROOT/evidence/deploy/terraform-plan-furl.txt"
fi
PLAN_TXT="$OUT_DIR/terraform-plan-$LABEL.txt"

tf init -reconfigure -input=false -no-color > "$OUT_DIR/init-$LABEL.log" 2>&1 \
  || { sed -e "s/$ACCOUNT/<account>/g" "$OUT_DIR/init-$LABEL.log" >&2; die "terraform init failed." 7; }
step "init" "ok   ($OUT_DIR/init-$LABEL.log)"

tf validate -no-color > "$OUT_DIR/validate-$LABEL.log" 2>&1 \
  || { sed -e "s/$ACCOUNT/<account>/g" "$OUT_DIR/validate-$LABEL.log" >&2; die "terraform validate failed." 7; }
step "validate" "$(grep -m1 -E 'Success|configuration is valid' "$OUT_DIR/validate-$LABEL.log" \
                   || tail -n 1 "$OUT_DIR/validate-$LABEL.log")"

set +e
tf plan -no-color -input=false -var "enable_cloudfront=$CF" > "$PLAN_TXT" 2>&1
PLAN_RC=$?
set -e
if [ "$PLAN_RC" -ne 0 ]; then
  sed -e "s/$ACCOUNT/<account>/g" "$PLAN_TXT" | tail -n 40 >&2
  die "terraform plan exited $PLAN_RC. The full output is at $PLAN_TXT (UNMASKED)." 7
fi
step "plan" "ok   ($PLAN_TXT)"

if [ "$WANT_JSON" -eq 1 ]; then
  tf plan -no-color -input=false -var "enable_cloudfront=$CF" -out "$(tfpath "$OUT_DIR")/tfplan-$LABEL.binary" \
    > /dev/null 2>&1 || die "terraform plan -out failed." 7
  tf show -no-color -json "$(tfpath "$OUT_DIR")/tfplan-$LABEL.binary" > "$OUT_DIR/terraform-plan-$LABEL.json" 2>/dev/null \
    || die "terraform show -json failed." 7
  rm -f "$OUT_DIR/tfplan-$LABEL.binary"
  step "json" "$OUT_DIR/terraform-plan-$LABEL.json"
fi

# ══════════════════════════════════════════════════════════════════════════════════════
#  STAGE 5 · What the plan says, and whether the committed artefact still tells the truth
# ══════════════════════════════════════════════════════════════════════════════════════
say ""
say "== 5 · the plan, and the committed artefact"

COUNT_LINE="$(grep -E '^Plan: [0-9]+ to add' "$PLAN_TXT" | head -n 1 || true)"
[ -n "$COUNT_LINE" ] || die "the plan text carries no 'Plan: N to add' line. Read
  $PLAN_TXT before believing anything else this script printed." 7
FRESH="$(printf '%s' "$COUNT_LINE" | sed -E 's/^Plan: ([0-9]+) to add.*/\1/')"
step "fresh plan" "$COUNT_LINE"

if [ -f "$ARTEFACT" ]; then
  COMMITTED="$(grep -oE 'Plan: [0-9]+ to add' "$ARTEFACT" | head -n 1 | sed -E 's/^Plan: ([0-9]+).*/\1/')"
  step "committed artefact" "evidence/deploy/$(basename "$ARTEFACT")  says Plan: ${COMMITTED:-<none>} to add"
else
  COMMITTED=""
  step "committed artefact" "MISSING: $ARTEFACT"
fi

# Two read-only assertions the gate in docs/deploy/PRE-APPLY.md § G6 and § G7 depend on.
#
# THE PATTERN IS ANCHORED ON THE ASSIGNMENT, NOT ON THE WORD. A bare
# `grep reserved_concurrent_executions` matches the concurrency alarm's `alarm_description`
# first, because that prose explains why the reservation is -1 — so it prints a paragraph
# and looks like it answered. PRE-APPLY § G4 records the same mistake being made with
# `grep -A2 … | grep default`; it is made once per document.
RCE="$(grep -oE '^ *\+ *reserved_concurrent_executions +=.*' "$PLAN_TXT" | head -n 1 | sed -E 's/^ *\+ *//' || true)"
step "G6 reservation" "${RCE:-<not present in this plan>}"
case "$RCE" in
  *"= -1") : ;;
  "") say ""; say "  WARNING: no reserved_concurrent_executions assignment in this plan." ;;
  *)
    say ""
    say "  THE PLAN CARRIES A POSITIVE CONCURRENCY RESERVATION: $RCE"
    say "  PutFunctionConcurrency is the sixth API call of this apply, and AWS refuses every"
    say "  positive reservation on an account whose UnreservedConcurrentExecutions is 10."
    say "  Five resources would already exist when it fails. See PRE-APPLY.md § G6."
    exit 9 ;;
esac
ZEROS="$(grep -cE '(^|[^0-9])0{12}([^0-9]|$)' "$PLAN_TXT" || true)"
step "G7 zero-mask" "$ZEROS occurrence(s) of twelve zeros   (expected 0)"
RAW_ACCT="$(grep -c "$ACCOUNT" "$PLAN_TXT" || true)"
step "account id" "$RAW_ACCT occurrence(s) in the RAW plan text — mask before it enters evidence/"

say ""
if [ -n "$COMMITTED" ] && [ "$COMMITTED" != "$FRESH" ]; then
  say "  THE COMMITTED ARTEFACT IS STALE. The plan that will run says $FRESH; the artefact"
  say "  in the repository says $COMMITTED. The artefact is the record, the plan is the fact."
  say "  Regenerate the artefact from this run — never edit the number by hand, and never"
  say "  reconfigure a plan to obtain the number the artefact already carries."
  exit 6
fi

say "  The plan the founder would approve is Plan: $FRESH to add, and the committed"
say "  artefact agrees. No AWS resource was created, changed or deleted by this run."
say "  Raw plan (UNMASKED account id): $PLAN_TXT"
