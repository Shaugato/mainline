#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
#
# BEGIN-USAGE
# ══════════════════════════════════════════════════════════════════════════════════════
#  kill_switch.sh — stop the demo Lambda from being invoked, and put it back
# ══════════════════════════════════════════════════════════════════════════════════════
#
# WHY THIS FILE EXISTS
#
# The demo origin is a Lambda Function URL with `authorization_type = NONE`. The account
# ceiling of 10 concurrent executions is the ONLY real bound on what it can cost, and a
# 30-day flood against it is worth USD 11,700-33,250. docs/deploy/COST-BOUND.md has the
# measured arithmetic.
#
# This script is lever L9 of that document: the floor under everything else. It exists so
# that the first time anyone needs it is not also the first time anyone writes it.
#
# WHAT IT DOES
#
#   --stop      reserve 0 concurrent executions   -> the function stops being invoked
#   --restore   remove the reservation            -> back to the unreserved default
#
# `--stop` is immediate. Lambda refuses new invocations as soon as the reservation lands;
# a Function URL caller gets HTTP 429 with no body from the handler. Spend goes to zero
# except for whatever is already in flight.
#
# THE -1 / DeleteFunctionConcurrency SUBTLETY — read this before editing
#
# Terraform writes `reserved_concurrent_executions = -1` to mean "no reservation". That is
# a TERRAFORM sentinel, not an API value. `PutFunctionConcurrency` will not accept -1; its
# minimum is 0. The API that removes a reservation is `DeleteFunctionConcurrency`, and
# that is what --restore calls. Restoring by putting -1 does not work, and a version of
# this script that tried it would fail exactly when it was needed.
#
#   --stop     ->  aws lambda put-function-concurrency    --reserved-concurrent-executions 0
#   --restore  ->  aws lambda delete-function-concurrency
#
# WHY RESERVING 0 IS ACCEPTED ON AN ACCOUNT THAT REFUSES 20
#
# This account's ConcurrentExecutions limit is 10 (measured; COST-BOUND.md I1). A positive
# reservation is refused because it would push UnreservedConcurrentExecutions below the
# floor AWS keeps back. Reserving ZERO takes nothing from the unreserved pool, so it is
# accepted. This is documented AWS behaviour; it is NOT measured on this account, because
# measuring it requires a mutating call against a function that does not exist yet.
#
# ── WHICH AWS ACCOUNT (decision D2) ───────────────────────────────────────────────────
#
# No account id is written in this file, and this script never PRINTS one either -- the
# live account is shown masked (first four and last four digits), matching how the account
# id is masked across the tracked tree. The live account is read from
#
#     aws sts get-caller-identity --query Account --output text
#
# and compared against the one you name, either way round:
#
#     --expect-account 123456789012          (wins over the environment)
#     export MAINLINE_AWS_ACCOUNT=123456789012
#
# SUPPLY NEITHER AND THIS SCRIPT CHANGES NOTHING (exit 3). `--any-account` is the only
# override. `--dry-run` is exempt from the requirement because it changes nothing by
# construction; it still refuses if you name an account and the caller is a different one.
#
# USAGE
#   scripts/deploy/kill_switch.sh --dry-run                       show both calls, make none
#   scripts/deploy/kill_switch.sh --stop    --dry-run             show the stop call only
#   scripts/deploy/kill_switch.sh --stop    --expect-account <id> --yes
#   scripts/deploy/kill_switch.sh --restore --expect-account <id> --yes
#   scripts/deploy/kill_switch.sh --status                        read-only; what is set now
#
# EXIT CODES
#   0  the reservation is in the state you asked for, verified by re-reading AWS
#   1  the call failed
#   2  usage error
#   3  a safety refusal: the account did not match, or none was named
#   4  --status / --stop / --restore ran against a function that does not exist
# END-USAGE

set -euo pipefail

REGION="ap-southeast-1"
PROFILE="${AWS_PROFILE:-mainline-dev}"
FUNCTION="${MAINLINE_FUNCTION_NAME:-mainline-demo-api}"

# D2: no account id is written in this file.
EXPECT_ACCOUNT="${MAINLINE_AWS_ACCOUNT:-}"

MODE=""
CONFIRMED=0
DRY_RUN=0
ANY_ACCOUNT=0

BOLD=""; DIM=""; RESET=""
if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then BOLD=$'\033[1m'; DIM=$'\033[2m'; RESET=$'\033[0m'; fi
export PYTHONIOENCODING="utf-8"
export PYTHONUTF8=1

step()  { printf '\n%s== %s%s\n' "$BOLD" "$1" "$RESET"; }
info()  { printf '   %s\n' "$*"; }
ok()    { printf '   %s[ok]%s %s\n' "$BOLD" "$RESET" "$*"; }
would() { printf '   %sWOULD RUN%s %s\n' "$BOLD" "$RESET" "$*"; }
die()   { printf '\nkill_switch: %s\n\n' "$1" >&2; exit "${2:-1}"; }
refuse(){ printf '\n%skill_switch REFUSED%s\n   %s\n\n' "$BOLD" "$RESET" "$1" >&2; exit 3; }

usage() { sed -n '/^# BEGIN-USAGE$/,/^# END-USAGE$/p' "$0" | sed '1d;$d' | sed 's/^# \{0,1\}//'; exit "${1:-2}"; }

# ── mask_account — this script prints no raw account id, ever ─────────────────────────
#
# teardown.sh echoes the account back so an operator can copy it into --expect-account.
# This script does not, because its output is routinely pasted into an incident thread.
# The masked form matches the tracked tree's convention (first four, last four).
mask_account() {
  local a="$1"
  if [ "${#a}" -lt 8 ]; then printf 'REDACTED'; else printf '%sREDACTED%s' "${a:0:4}" "${a: -4}"; fi
}

# ── aws_query — an EMPTY answer and a FAILED call are not the same thing ──────────────
#
# Same rule as teardown.sh: `x="$(aws … || true)"` would report an expired token or a
# missing permission as "no reservation set", which in THIS script is the one wrong answer
# that matters -- it would tell an operator the kill switch is off when it is unknown.
QUERY_OUT=""
aws_query() {  # label, then the aws sub-command and its arguments
  local label="$1"; shift
  if ! QUERY_OUT="$("${AWSX[@]}" "$@" 2>&1)"; then
    die "$label failed, and this script will not treat an unreadable answer as a known one:
   $QUERY_OUT"
  fi
  [ "$QUERY_OUT" = "None" ] && QUERY_OUT=""
  return 0
}

while [ $# -gt 0 ]; do
  case "$1" in
    --stop)          MODE="stop"; shift ;;
    --restore)       MODE="restore"; shift ;;
    --status)        MODE="status"; shift ;;
    --yes|-y)        CONFIRMED=1; shift ;;
    --dry-run)       DRY_RUN=1; shift ;;
    --any-account)   ANY_ACCOUNT=1; shift ;;
    --expect-account) EXPECT_ACCOUNT="${2:-}"; shift 2 ;;
    --function)      FUNCTION="${2:-}"; shift 2 ;;
    --profile)       PROFILE="${2:-}"; shift 2 ;;
    --region)        REGION="${2:-}"; shift 2 ;;
    -h|--help)       usage 0 ;;
    *) printf 'kill_switch: unknown argument %s\n' "$1" >&2; usage 2 ;;
  esac
done

# --dry-run with no mode shows both calls. Any other empty mode is a usage error.
if [ -z "$MODE" ] && [ "$DRY_RUN" -eq 0 ]; then
  usage 2
fi

# A mutating mode needs --yes. --dry-run and --status never do.
if [ "$MODE" = "stop" ] || [ "$MODE" = "restore" ]; then
  if [ "$CONFIRMED" -eq 0 ] && [ "$DRY_RUN" -eq 0 ]; then
    refuse "--$MODE changes live AWS state and you did not pass --yes.

   Add --yes when you mean it, or --dry-run to see the exact API call and make none."
  fi
fi

export AWS_PROFILE="$PROFILE" AWS_REGION="$REGION" AWS_DEFAULT_REGION="$REGION"
AWSX=(aws --profile "$PROFILE" --region "$REGION" --output text --no-cli-pager)

command -v aws >/dev/null 2>&1 || die "the AWS CLI is not on PATH."

ACCOUNT="$("${AWSX[@]}" sts get-caller-identity --query Account 2>/dev/null)" \
  || die "aws sts get-caller-identity failed for profile '$PROFILE'."
ACCOUNT_MASKED="$(mask_account "$ACCOUNT")"

# ── THE ACCOUNT GUARD ─────────────────────────────────────────────────────────────────
if [ "$ANY_ACCOUNT" -eq 1 ]; then
  info "account guard DISABLED by --any-account"
elif [ -n "$EXPECT_ACCOUNT" ] && [ "$ACCOUNT" != "$EXPECT_ACCOUNT" ]; then
  refuse "this is account $ACCOUNT_MASKED, which is not the one you named. Changing nothing.
   Fix the profile (--profile <name>) or the expectation (--expect-account <id>)."
elif [ -z "$EXPECT_ACCOUNT" ] && [ "$DRY_RUN" -eq 0 ] && [ "$MODE" != "status" ]; then
  refuse "NOTHING TOLD THIS SCRIPT WHICH AWS ACCOUNT IT MAY CHANGE, so it will not change
   one. The caller is account $ACCOUNT_MASKED. Name it in full:

       aws sts get-caller-identity --query Account --output text      # read it
       scripts/deploy/kill_switch.sh --$MODE --expect-account <id> --yes
   or
       export MAINLINE_AWS_ACCOUNT=<id>

   No account id is hard-coded in this file and none is printed by it (decision D2).
   --any-account is the only override. --dry-run and --status need none of this,
   because they change nothing."
fi

printf '%sMAINLINE demo kill switch%s   account=%s  region=%s  function=%s%s\n' \
  "$BOLD" "$RESET" "$ACCOUNT_MASKED" "$REGION" "$FUNCTION" \
  "$([ "$DRY_RUN" -eq 1 ] && echo '  (DRY RUN — changes nothing)' || echo '')"

# ── the two calls, written once so the dry run and the real run cannot drift ──────────
STOP_CALL="aws --profile $PROFILE --region $REGION lambda put-function-concurrency \\
                 --function-name $FUNCTION --reserved-concurrent-executions 0"
RESTORE_CALL="aws --profile $PROFILE --region $REGION lambda delete-function-concurrency \\
                 --function-name $FUNCTION"

# ── read the current reservation ──────────────────────────────────────────────────────
#
# get-function-concurrency returns an empty projection when NO reservation is set, and the
# integer when one is. ResourceNotFoundException means the function is not deployed, which
# is a different thing again and gets its own exit code.
CURRENT="unknown"
read_current() {
  local out
  if out="$("${AWSX[@]}" lambda get-function-concurrency --function-name "$FUNCTION" \
              --query 'ReservedConcurrentExecutions' 2>&1)"; then
    [ "$out" = "None" ] && out=""
    if [ -z "$out" ]; then CURRENT="unreserved"; else CURRENT="$out"; fi
    return 0
  fi
  case "$out" in
    *ResourceNotFoundException*|*"Function not found"*) CURRENT="absent"; return 0 ;;
    *) die "reading the current reservation failed, and this script will not guess:
   $out" ;;
  esac
}

describe_current() {
  case "$CURRENT" in
    absent)     printf 'the function does not exist in this account/region' ;;
    unreserved) printf 'NO reservation (unreserved — Terraform'"'"'s -1); the function is LIVE' ;;
    0)          printf 'reserved concurrency 0 — the function is STOPPED' ;;
    *)          printf 'reserved concurrency %s — the function is LIVE' "$CURRENT" ;;
  esac
}

step "current state"
read_current
info "$(describe_current)"

# ══════════════════════════════════════════════════════════════════════════════════════
#  DRY RUN — prints the exact calls and makes none
# ══════════════════════════════════════════════════════════════════════════════════════
if [ "$DRY_RUN" -eq 1 ]; then
  step "dry run — the exact API calls, made by nobody"
  if [ -z "$MODE" ] || [ "$MODE" = "stop" ]; then
    printf '\n   %s--stop%s  (spend -> 0; callers get HTTP 429)\n' "$BOLD" "$RESET"
    would "$STOP_CALL"
  fi
  if [ -z "$MODE" ] || [ "$MODE" = "restore" ]; then
    printf '\n   %s--restore%s  (back to unreserved; Terraform'"'"'s -1)\n' "$BOLD" "$RESET"
    would "$RESTORE_CALL"
    printf '   %sNOTE  restore is delete-function-concurrency, NOT a put of -1.\n' "$DIM"
    printf '         PutFunctionConcurrency has a minimum of 0 and rejects -1.%s\n' "$RESET"
  fi
  printf '\n   %sNothing was called. Re-run with --%s --expect-account <id> --yes to act.%s\n\n' \
    "$DIM" "${MODE:-stop}" "$RESET"
  exit 0
fi

# ══════════════════════════════════════════════════════════════════════════════════════
#  STATUS — read-only
# ══════════════════════════════════════════════════════════════════════════════════════
if [ "$MODE" = "status" ]; then
  [ "$CURRENT" = "absent" ] && exit 4
  exit 0
fi

[ "$CURRENT" = "absent" ] && die "there is no function named '$FUNCTION' in account
   $ACCOUNT_MASKED, region $REGION. Nothing to $MODE." 4

# ══════════════════════════════════════════════════════════════════════════════════════
#  MUTATE
# ══════════════════════════════════════════════════════════════════════════════════════
if [ "$MODE" = "stop" ]; then
  if [ "$CURRENT" = "0" ]; then
    ok "already stopped — reserved concurrency is already 0. Nothing to do."
    exit 0
  fi
  step "stopping $FUNCTION"
  info "$STOP_CALL"
  aws_query "put-function-concurrency" lambda put-function-concurrency \
    --function-name "$FUNCTION" --reserved-concurrent-executions 0
else
  if [ "$CURRENT" = "unreserved" ]; then
    ok "already restored — there is no reservation. Nothing to do."
    exit 0
  fi
  step "restoring $FUNCTION to unreserved"
  info "$RESTORE_CALL"
  aws_query "delete-function-concurrency" lambda delete-function-concurrency \
    --function-name "$FUNCTION"
fi

# ── VERIFY by re-reading AWS, not by trusting the call's exit code ─────────────────────
step "verify"
read_current
info "$(describe_current)"

if [ "$MODE" = "stop" ] && [ "$CURRENT" = "0" ]; then
  ok "STOPPED. $FUNCTION accepts no invocations in account $ACCOUNT_MASKED."
  info "spend from this function is now zero. Restore with:"
  info "  scripts/deploy/kill_switch.sh --restore --expect-account <id> --yes"
  exit 0
elif [ "$MODE" = "restore" ] && [ "$CURRENT" = "unreserved" ]; then
  ok "RESTORED. $FUNCTION is live and unreserved (Terraform's -1)."
  info "the account ceiling of 10 concurrent executions is the only bound again."
  info "read docs/deploy/COST-BOUND.md before leaving it that way."
  exit 0
fi

die "the call returned success but the reservation did not land as asked: wanted
   $([ "$MODE" = "stop" ] && echo '0' || echo 'unreserved'), read back '$CURRENT'."
