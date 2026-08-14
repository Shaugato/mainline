#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
#
# BEGIN-USAGE
# ══════════════════════════════════════════════════════════════════════════════════════
#  deploy.sh — clean checkout to a working https:// demo URL, in one command
# ══════════════════════════════════════════════════════════════════════════════════════
#
# Ten stages, run in order, and NOT ONE OF THEM CONTINUES PAST A FAILURE. That is the
# whole design rule. A deploy script that carries on after a broken stage produces a URL
# that serves yesterday's bytes, and there is no worse outcome for a submission whose
# entire claim is that it does not lie about what it is showing you.
#
#   0  preflight        who am I, what is installed, is the DSN set
#   1  state backend    scripts/deploy/bootstrap_state.sh
#   2  secret           aws ssm put-parameter --type SecureString  (never echoed)
#   3  database         cloud_chain.py then seed_demo.py           (idempotent)
#   4  lambda package   scripts/deploy/build_lambda.sh + manifest verification
#   5  site payload     OPTIONAL — only when --enable-cloudfront (see D1 below)
#   6  infrastructure   terraform init + plan, and apply ONLY behind the approval gate
#   7  publish          resolve the hostname, then PROVE it over HTTPS before printing it
#   8  proof            demo_acceptance.py against the live URL — MUST exit 0
#   9  hand-off         the URL and the judge credential block
#
# ── DECISION D1: THE HOSTNAME IS THE LAMBDA FUNCTION URL ───────────────────────────────
#
# AWS refuses to create new CloudFront distributions on this account (an account-level
# verification hold; see docs/deploy/RUNBOOK.md, which quotes the 403 and its RequestID).
# So the demo URL is the Lambda Function URL:
#
#     https://<id>.lambda-url.ap-southeast-1.on.aws
#
# HTTPS on an AWS-issued certificate. No ACM, no hosted zone, no account verification.
# ONE origin serves the console SPA at `/`, the signed evidence bundle at `/bundle/*` and
# the API at `/v1/*` — so there is no CORS, no S3 in the request path, and exactly one
# hostname in the submission form.
#
# Three consequences are visible in this script:
#   · stage 5's S3 upload is OPTIONAL and off by default — the console and the bundle
#     travel INSIDE the Lambda package, which is why stage 0 checks the zip for them
#   · stage 6 passes `-var enable_cloudfront=false`
#   · stage 7 reads the hostname from the api module's `function_url` output, not from a
#     distribution domain name
#
# `--enable-cloudfront` restores the pre-D1 shape the day AWS Support lifts the hold. It
# plans cleanly today; it will not apply today. Nothing in this project is allowed to let
# CloudFront hold the URL hostage.
#
# ── THE APPROVAL GATE ON STAGE 6 ──────────────────────────────────────────────────────
#
# `terraform apply` creates billable resources in a live AWS account. This script will not
# run one unless the environment says so:
#
#     MAINLINE_APPLY_APPROVED=1 scripts/deploy/deploy.sh
#
# Without it, stage 6 runs `init` and `plan`, saves the plan, prints it, and STOPS with
# exit code 7. That is not a failure — it is the designed halt. The plan committed at
# docs/deploy/terraform-plan.md is what the orchestrator reviews with the founder before
# the apply is approved. The gate is a feature of this script, not scaffolding.
#
# ── WHAT THIS SCRIPT NEVER DOES ───────────────────────────────────────────────────────
#   · echo the DSN, a password, or any string that could contain one — stage 2 builds its
#     payload in a temp file with 0600 and deletes it in a trap, and `set -x` is refused
#   · create an AWS resource outside the `mainline-demo-` prefix
#   · touch an AWS account it was not told to touch (see --expect-account)
#   · PRINT A URL IT DID NOT JUST FETCH OVER HTTPS. Stage 7 GETs `/` and GETs
#     `/v1/health`, asserts 200 on both, and asserts that the health body names the
#     cluster it is talking to. If either fails the script exits non-zero and says which.
#
# USAGE
#   scripts/deploy/deploy.sh --expect-account <id>       plan-only deploy (the gate stops it)
#   MAINLINE_APPLY_APPROVED=1 scripts/deploy/deploy.sh --expect-account <id>
#                                                       the full deploy, through apply
#   scripts/deploy/deploy.sh --dry-run                   prerequisites only, writes NOTHING
#   scripts/deploy/deploy.sh --dry-run --strict-secrets  also require the operator secrets
#   scripts/deploy/deploy.sh --preflight-only            stage 0 and stop
#   scripts/deploy/deploy.sh --recreate-db               pass --recreate to cloud_chain.py
#   scripts/deploy/deploy.sh --skip-db                   the database is already correct
#   scripts/deploy/deploy.sh --skip-build                reuse the existing zip and dist/
#   scripts/deploy/deploy.sh --enable-cloudfront         pre-D1 shape; needs the AWS hold lifted
#   scripts/deploy/deploy.sh --arch x86_64               build and declare x86_64, not arm64
#   scripts/deploy/deploy.sh --any-account               the ONLY way to skip the account guard
#
# ── WHICH AWS ACCOUNT (decision D2) ───────────────────────────────────────────────────
#
# There is no account id written in this file. The live account is read at run time from
#
#     aws sts get-caller-identity --query Account --output text
#
# and compared against the one you named. You name it in one of two ways:
#
#     --expect-account 123456789012          (wins over the environment)
#     export MAINLINE_AWS_ACCOUNT=123456789012
#
# IF YOU SUPPLY NEITHER, THIS SCRIPT REFUSES AND DEPLOYS NOTHING (exit 3). That refusal is
# the safety property, not an inconvenience: this account holds seven buckets belonging to
# unrelated live projects, and a deploy pointed at the wrong credentials still costs money
# and still has to be cleaned up by hand. `--any-account` is the only override, and it says
# so on stdout every time it is used.
#
# TWO PRECISE EXCEPTIONS, and they do not weaken it. `--dry-run` and `--preflight-only`
# create, change and delete nothing at all, so there is no account for them to refuse to
# touch; with no expectation supplied they PRINT the account they can see, state that a
# real deploy will refuse without one, and carry on. Supply an expectation that does NOT
# match and even those two stop, because at that point you are demonstrably pointed at
# something you did not mean.
#
# ENVIRONMENT
#   MAINLINE_AWS_ACCOUNT  the account id this deploy is allowed to touch (see above)
#   MAINLINE_APPLY_APPROVED=1   permit stage 6 to run `terraform apply`
#   COCKROACH_DSN         admin DSN for the Cloud cluster. Read from the repo-root .env
#                         if not exported. Required by stage 3.
#   MAINLINE_API_DSN      the application DSN the Lambda will use, i.e. COCKROACH_DSN with
#                         the userinfo swapped for mainline_api and its password. This is
#                         what stage 2 writes to SSM.
#   MAINLINE_API_PASSWORD alternative to the above: stage 2 derives the DSN from
#                         COCKROACH_DSN by swapping the userinfo. Never printed.
#   MAINLINE_LAMBDA_ZIP   override the path stage 4 is expected to have produced.
#   MAINLINE_CONSOLE_BUILD_CMD  override stage 5's console build command.
#   MAINLINE_STATE_BUCKET override the derived state bucket name.
#   MAINLINE_DEMO_DATABASE  the database /v1/health must report. Default mainline_demo.
#
# EXIT CODES
#   0 the URL printed at the end was fetched over HTTPS and proved itself
#   1 a stage failed — the message names the stage and what to do about it
#   2 usage error
#   3 preflight refused: wrong/unnamed account, missing tool, or missing credential
#   7 STOPPED AT THE APPROVAL GATE. Stage 6 planned and did not apply. Nothing was
#     created, nothing was changed, and no URL was printed because none exists yet.
#     This is a designed halt and NOT a failure. Set MAINLINE_APPLY_APPROVED=1 to proceed.
# END-USAGE

set -euo pipefail

# `set -x` would defeat stage 2. Refuse rather than leak.
case "${SHELLOPTS:-}" in *xtrace*) printf 'deploy: refusing to run under `set -x` — stage 2 handles a database password.\n' >&2; exit 3 ;; esac

# ── Where everything is ───────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
TF_DIR="$ROOT/infra/envs/demo"
CONSOLE_DIR="$ROOT/verticals/mainline/apps/console"
BUNDLE_SRC="$CONSOLE_DIR/fixtures/bundles/demo-cloud"
DIST_BUNDLE="$ROOT/dist/demo-bundle"
PLAN_DOC="$ROOT/docs/deploy/terraform-plan.md"

# arm64 is `build_lambda.sh`'s default and `infra/modules/demo-api`'s default: Graviton2
# is ~20 % cheaper per GB-second and psycopg-binary 3.3.4 ships a cp313 aarch64 wheel.
# ONE variable drives both the filename and the Terraform `architecture`, because a zip
# built for one architecture on a function declared as the other is a clean plan, a clean
# apply, and an ELFCLASS error on the first request.
ARCH="arm64"

REGION="ap-southeast-1"
PROFILE="${AWS_PROFILE:-mainline-dev}"
DSN_PARAM="/mainline/demo/cockroach_dsn"
NAME_PREFIX="mainline-demo"
DEMO_DATABASE="${MAINLINE_DEMO_DATABASE:-mainline_demo}"

# D2: no account id is written in this file. This is where the operator's answer lands.
EXPECT_ACCOUNT="${MAINLINE_AWS_ACCOUNT:-}"

DRY_RUN=0
STRICT_SECRETS=0
PREFLIGHT_ONLY=0
ANY_ACCOUNT=0
RECREATE_DB=0
SKIP_DB=0
SKIP_BUILD=0
ENABLE_CLOUDFRONT=0
APPLY_APPROVED=0
[ "${MAINLINE_APPLY_APPROVED:-}" = "1" ] && APPLY_APPROVED=1

# ── Output. Deliberately plain: this runs in CI, in Git Bash and over ssh. ─────────────
BOLD=""; DIM=""; RESET=""
if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then BOLD=$'\033[1m'; DIM=$'\033[2m'; RESET=$'\033[0m'; fi

STAGE_N=0
stage() { STAGE_N="$1"; printf '\n%s== stage %s · %s%s\n' "$BOLD" "$1" "$2" "$RESET"; }
info()  { printf '   %s\n' "$*"; }
ok()    { printf '   %s[ok]%s %s\n' "$BOLD" "$RESET" "$*"; }
bad()   { printf '   %s[NO]%s %s\n' "$BOLD" "$RESET" "$*" >&2; }
skip()  { printf '   %s[skipped] %s%s\n' "$DIM" "$*" "$RESET"; }
die()   { printf '\n%sdeploy: stage %s FAILED%s\n   %s\n\n' "$BOLD" "$STAGE_N" "$RESET" "$1" >&2; exit "${2:-1}"; }

# Marker-delimited so the help text cannot drift out of sync with a line number.
usage() { sed -n '/^# BEGIN-USAGE$/,/^# END-USAGE$/p' "$0" | sed '1d;$d' | sed 's/^# \{0,1\}//'; exit "${1:-2}"; }

# ── winpath: a POSIX path the NATIVE Windows aws.exe can actually open ────────────────
#
# Measured, not theorised. Under Git Bash `mktemp` returns `/tmp/x.json`, which exists —
# for bash. `aws` is a native Windows executable and answers:
#
#   Error parsing parameter '--cli-input-json': Unable to load paramfile
#   file:///tmp/probe.fSxxqQ.json: [Errno 2] No such file or directory
#
#   $ cygpath -m /tmp/probe.fSxxqQ.json
#   C:/Users/shaug/AppData/Local/Temp/probe.fSxxqQ.json     <- this one it opens
#
# Stage 2 passes the DSN to `aws ssm put-parameter` as a `file://` paramfile precisely so
# the secret never enters an argument vector, which makes this conversion load-bearing on
# Windows rather than cosmetic. On Linux and macOS there is no cygpath and this is a no-op.
winpath() {
  if command -v cygpath >/dev/null 2>&1; then cygpath -m "$1"; else printf '%s' "$1"; fi
}

while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run)          DRY_RUN=1; shift ;;
    --strict-secrets)   STRICT_SECRETS=1; shift ;;
    --preflight-only)   PREFLIGHT_ONLY=1; shift ;;
    --any-account)      ANY_ACCOUNT=1; shift ;;
    --expect-account)   EXPECT_ACCOUNT="${2:-}"; shift 2 ;;
    --recreate-db)      RECREATE_DB=1; shift ;;
    --skip-db)          SKIP_DB=1; shift ;;
    --skip-build)       SKIP_BUILD=1; shift ;;
    --enable-cloudfront) ENABLE_CLOUDFRONT=1; shift ;;
    --arch)             ARCH="${2:-}"; shift 2 ;;
    --profile)          PROFILE="${2:-}"; shift 2 ;;
    --region)           REGION="${2:-}"; shift 2 ;;
    --state-bucket)     MAINLINE_STATE_BUCKET="${2:-}"; shift 2 ;;
    --phase1)
      # Retired by D1, and saying so is better than silently doing something else.
      printf 'deploy: --phase1 no longer means anything under decision D1.\n' >&2
      printf '   It used to mean "a CloudFront URL with no Lambda behind it". Under D1 the\n' >&2
      printf '   LAMBDA IS THE HOSTNAME, so a deploy with no Lambda has no URL at all.\n' >&2
      printf '   The REPLAY/LIVE distinction did not disappear, it moved: the console reads\n' >&2
      printf '   `transport.describe().mode` at run time and shows a REPLAY badge over the\n' >&2
      printf '   signed bundle when the database is unreachable. Nothing has to be deployed\n' >&2
      printf '   differently to get it. See docs/deploy/RUNBOOK.md § 1.\n' >&2
      exit 2 ;;
    -h|--help)          usage 0 ;;
    *) printf 'deploy: unknown argument %s\n' "$1" >&2; usage 2 ;;
  esac
done

case "$ARCH" in arm64|x86_64) : ;; *) printf 'deploy: --arch must be arm64 or x86_64, not %s\n' "$ARCH" >&2; exit 2 ;; esac

export AWS_PROFILE="$PROFILE"
export AWS_REGION="$REGION"
export AWS_DEFAULT_REGION="$REGION"
# Measured on this machine: without these, a Python helper printing `·` lands as `?` in the
# Git Bash transcript, because CPython picks the ANSI code page for stdout when it is a
# pipe. The transcript is committed as evidence, so mojibake in it is a defect.
export PYTHONIOENCODING="utf-8"
export PYTHONUTF8=1
AWSX=(aws --profile "$PROFILE" --region "$REGION" --output text --no-cli-pager)

SHAPE="$([ "$ENABLE_CLOUDFRONT" -eq 1 ] && echo 'cloudfront (pre-D1, needs the AWS hold lifted)' || echo 'D1 — Lambda Function URL is the hostname')"
printf '%sMAINLINE demo deploy%s   shape=%s\n' "$BOLD" "$RESET" "$SHAPE"
printf '                        region=%s  profile=%s  arch=%s\n' "$REGION" "$PROFILE" "$ARCH"
[ "$DRY_RUN" -eq 1 ] && printf '%sDRY RUN — nothing will be created, changed, uploaded or written.%s\n' "$DIM" "$RESET"

# ══════════════════════════════════════════════════════════════════════════════════════
# STAGE 0 — PREFLIGHT
# ══════════════════════════════════════════════════════════════════════════════════════
stage 0 "preflight"

need() {
  command -v "$1" >/dev/null 2>&1 \
    || die "'$1' is not on PATH. $2" 3
}
need aws       "Install the AWS CLI v2."
need terraform "Install Terraform >= 1.10 (this stack needs use_lockfile for native S3 state locking)."
need curl      "curl is used for the live HTTPS proof in stage 7."

AWS_VER="$(aws --version 2>&1 | sed -n 's#^aws-cli/\([0-9][^ ]*\).*#\1#p')"
info "aws cli        ${AWS_VER:-unknown}"
case "$AWS_VER" in
  2.*) : ;;
  *) die "the AWS CLI reports version '${AWS_VER:-unknown}'. This stack needs v2: v1 has no
   \`s3api list-object-versions --max-keys\` paging shape teardown relies on, and its
   \`ssm put-parameter --cli-input-json\` handling differs." 3 ;;
esac

TF_VER="$(terraform version -json 2>/dev/null | sed -n 's/.*"terraform_version": *"\([^"]*\)".*/\1/p' | head -1)"
[ -n "$TF_VER" ] || TF_VER="$(terraform version | head -1 | sed 's/^Terraform v//')"
info "terraform      $TF_VER"
case "$TF_VER" in
  0.*|1.[0-9].*) die "Terraform $TF_VER is older than 1.10, which is where \`use_lockfile\`
   (native S3 state locking) was added. infra/envs/demo/backend.tf depends on it and
   there is deliberately no DynamoDB table to fall back to." 3 ;;
esac

# The interpreter. `uv` is not installed on this machine and every `just` recipe that
# shells out to `uv run` is dead here, so the venv interpreter is named explicitly.
PY=""
for cand in "$ROOT/.venv/Scripts/python.exe" "$ROOT/.venv/bin/python" "$ROOT/.venv/bin/python3"; do
  [ -x "$cand" ] && { PY="$cand"; break; }
done
[ -n "$PY" ] || die "no interpreter at .venv/Scripts/python.exe or .venv/bin/python.
   Create the virtualenv first: python -m venv .venv && .venv/bin/pip install -e ." 3
PY_VER="$("$PY" -c 'import sys;print("%d.%d.%d" % sys.version_info[:3])' 2>/dev/null || echo '')"
info "python         ${PY_VER:-unknown}  ($PY)"
case "$PY_VER" in
  3.13.*) : ;;
  *) die "the virtualenv interpreter is ${PY_VER:-unreadable}, not 3.13.x. The Lambda runtime
   is python3.13 and \`build_lambda.sh\` downloads cp313 wheels; building the package with
   a different minor version produces a zip that imports on this machine and fails on
   Lambda with a bytecode or ABI error." 3 ;;
esac

need node "Install Node 20+."
info "node           $(node --version)"
if command -v pnpm >/dev/null 2>&1; then
  info "pnpm           $(pnpm --version)"
else
  [ "$SKIP_BUILD" -eq 1 ] || die "pnpm is not on PATH and stage 5 builds the console with it.
   Install pnpm, or pass --skip-build and put a built console in $CONSOLE_DIR/dist." 3
fi
info "curl           $(curl --version 2>/dev/null | head -1 | cut -d' ' -f1-2)"

# ── AWS identity, and the account guard (decision D2) ─────────────────────────────────
#
# THE ACCOUNT ID IS NOT WRITTEN IN THIS FILE. It is read from the live caller identity and
# compared against the one the operator named. The safety property is unchanged from the
# version that hard-coded it: this script refuses to touch an account it was not told to
# touch, and --any-account is the only override.
ACCOUNT="$("${AWSX[@]}" sts get-caller-identity --query Account 2>/dev/null)" \
  || die "aws sts get-caller-identity failed for profile '$PROFILE'.
   Run 'aws configure --profile $PROFILE', or pass --profile <name>." 3
ARN="$("${AWSX[@]}" sts get-caller-identity --query Arn 2>/dev/null || echo '?')"
info "aws account    $ACCOUNT"
info "aws identity   $ARN"

ACCOUNT_GUARD="unnamed"
if [ "$ANY_ACCOUNT" -eq 1 ]; then
  ACCOUNT_GUARD="disabled"
  info "account guard  DISABLED by --any-account — proceeding into account $ACCOUNT"
elif [ -z "$EXPECT_ACCOUNT" ] && { [ "$DRY_RUN" -eq 1 ] || [ "$PREFLIGHT_ONLY" -eq 1 ]; }; then
  # A dry run and a preflight WRITE NOTHING, so there is no account to refuse to touch.
  # Requiring the expectation here would make the one command a stranger runs first fail
  # for a reason that has nothing to do with whether this machine can deploy. The refusal
  # below still stands for every run that can create, change or delete something, which is
  # exactly where the safety property lives.
  info "account guard  NOT NAMED — harmless here (this run writes nothing), FATAL for a real"
  info "               deploy. Supply --expect-account $ACCOUNT or MAINLINE_AWS_ACCOUNT=$ACCOUNT."
elif [ -z "$EXPECT_ACCOUNT" ]; then
  die "NOTHING TOLD THIS SCRIPT WHICH AWS ACCOUNT IT MAY TOUCH, so it will not touch one.

   The caller is account $ACCOUNT. Name it, and this run proceeds:

       scripts/deploy/deploy.sh --expect-account $ACCOUNT
   or
       export MAINLINE_AWS_ACCOUNT=$ACCOUNT

   The flag wins over the environment variable. --any-account skips the check entirely
   and is the only thing that does.

   Why the refusal exists: this account holds seven S3 buckets belonging to unrelated
   live projects. Everything this script creates carries the '$NAME_PREFIX-' prefix, but a
   deploy pointed at the wrong credentials still costs money and still has to be cleaned
   up by hand. No account id is hard-coded here (decision D2, docs/leads/ship-final.md
   §1.6), so the operator supplies it and the script checks it." 3
elif [ "$ACCOUNT" != "$EXPECT_ACCOUNT" ]; then
  die "this is account $ACCOUNT. You said $EXPECT_ACCOUNT.
   Refusing to create, change or delete anything. Fix the profile (--profile <name>), fix
   the expectation (--expect-account <id>), or pass --any-account if you really mean it." 3
else
  ACCOUNT_GUARD="matched"
  ok "account guard  $ACCOUNT matches the account you named"
fi

# The DSN. Read from the repo-root .env when not exported, exactly like every program in
# scripts/deploy/. Its VALUE is never printed — only whether it is present and its host.
if [ -z "${COCKROACH_DSN:-}" ] && [ -f "$ROOT/.env" ]; then
  COCKROACH_DSN="$(sed -n 's/^COCKROACH_DSN=//p' "$ROOT/.env" | head -1 | sed 's/^"//; s/"$//')"
  export COCKROACH_DSN
fi
DSN_HOST=""
if [ -z "${COCKROACH_DSN:-}" ]; then
  if [ "$SKIP_DB" -eq 1 ] || [ "$DRY_RUN" -eq 1 ]; then
    bad "COCKROACH_DSN is unset and the repo-root .env does not define it"
  else
    die "COCKROACH_DSN is not set and the repo-root .env does not define it.
   Stage 3 applies the migration chain and the demo seed against the Cloud cluster and
   cannot proceed without it. Export it, or pass --skip-db if the database is already
   built." 3
  fi
else
  DSN_HOST="$(printf '%s' "$COCKROACH_DSN" | sed -n 's#^[a-z+]*://[^@]*@\([^/:?]*\).*#\1#p')"
  info "cockroach dsn  set  (host ${DSN_HOST:-<unparsed>})"
fi

# The application DSN for the Lambda. Every deploy needs it now: under D1 there is no
# shape of this stack that has no Lambda.
API_DSN_SOURCE=""
if [ -n "${MAINLINE_API_DSN:-}" ]; then
  API_DSN_SOURCE="MAINLINE_API_DSN"
elif [ -n "${MAINLINE_API_PASSWORD:-}" ] && [ -n "${COCKROACH_DSN:-}" ]; then
  API_DSN_SOURCE="derived from COCKROACH_DSN + MAINLINE_API_PASSWORD"
fi
API_DSN_ADVICE="the Lambda's DSN is not available, so stage 2 has nothing to write to SSM.
   It is an OPERATOR SECRET: minted once, shown once, and deliberately stored nowhere in
   this repository. Mint it:
       .venv/Scripts/python.exe scripts/deploy/cloud_roles.py --rotate
   then export either the whole DSN:
       export MAINLINE_API_DSN='postgresql://mainline_api:<pw>@<host>:26257/$DEMO_DATABASE?sslmode=verify-full'
   or just the password, and this script swaps the userinfo into COCKROACH_DSN:
       export MAINLINE_API_PASSWORD='<pw>'"
if [ -n "$API_DSN_SOURCE" ]; then
  info "api dsn        available ($API_DSN_SOURCE)"
elif [ "$DRY_RUN" -eq 0 ]; then
  die "$API_DSN_ADVICE" 3
fi

STATE_BUCKET="${MAINLINE_STATE_BUCKET:-${NAME_PREFIX}-tfstate-${ACCOUNT}}"
info "state bucket   $STATE_BUCKET"
info "dsn parameter  $DSN_PARAM  (name only; the value is never in Terraform)"
if [ "$APPLY_APPROVED" -eq 1 ]; then
  info "apply gate     OPEN — MAINLINE_APPLY_APPROVED=1, stage 6 will apply"
else
  info "apply gate     CLOSED — stage 6 will plan and stop (exit 7). Set MAINLINE_APPLY_APPROVED=1 to open it."
fi

ok "preflight passed"
[ "$PREFLIGHT_ONLY" -eq 1 ] && { printf '\n--preflight-only: stopping here.\n'; exit 0; }

# ── Named prerequisites, and who owes each one ────────────────────────────────────────
BUILD_LAMBDA="$SCRIPT_DIR/build_lambda.sh"
[ -f "$BUILD_LAMBDA" ] || BUILD_LAMBDA="$SCRIPT_DIR/build_lambda.ps1"
CAPTURE_BUNDLE="$SCRIPT_DIR/capture_demo_bundle.py"
ACCEPTANCE="$SCRIPT_DIR/demo_acceptance.py"
LAMBDA_ZIP="${MAINLINE_LAMBDA_ZIP:-$ROOT/out/lambda/mainline-demo-api-$ARCH.zip}"
LAMBDA_MANIFEST="$LAMBDA_ZIP.json"

# ══════════════════════════════════════════════════════════════════════════════════════
# --dry-run — THE PREREQUISITE CHECK. WRITES NOTHING, ANYWHERE.
# ══════════════════════════════════════════════════════════════════════════════════════
#
# Two classes, and the distinction is deliberate:
#
#   ARTEFACT   something this repository owes. A stranger cloning the repo either has it
#              or does not, and if they do not, the fix is a worker's job. GATED: missing
#              one exits non-zero.
#   OPERATOR   a secret a human mints and exports. A clean checkout NEVER has one, so
#              gating on it by default would make --dry-run permanently red for exactly
#              the person it is meant to serve. Reported always; gated by --strict-secrets.
#
# The rule for the gated class is the one this whole project runs on: a dry run that
# found a hole exits non-zero on purpose. This is the check, not a preview.
if [ "$DRY_RUN" -eq 1 ]; then
  stage 0 "dry run · prerequisites"
  MISSING=0
  SECRETS_MISSING=0

  need_file() {  # path, owner, what
    if [ -e "$1" ]; then ok "$3"; info "     $1"; return 0; fi
    bad "$3 is MISSING"
    printf '        want: %s\n        owed by: %s\n' "$1" "$2" >&2
    return 1
  }

  info "-- machine ------------------------------------------------------------------"
  ok "aws-cli $AWS_VER · terraform $TF_VER · python $PY_VER · node $(node --version) · curl present"
  if command -v pnpm >/dev/null 2>&1; then ok "pnpm $(pnpm --version)"; else bad "pnpm is not on PATH"; MISSING=1; fi
  ok "aws account $ACCOUNT · guard $ACCOUNT_GUARD · apply gate $([ "$APPLY_APPROVED" -eq 1 ] && echo OPEN || echo CLOSED)"

  info "-- terraform (w3 · w4) ------------------------------------------------------"
  need_file "$TF_DIR/main.tf"                    "w4-tf-root-and-plan" "terraform root"        || MISSING=1
  need_file "$TF_DIR/variables.tf"               "w4-tf-root-and-plan" "terraform variables"   || MISSING=1
  need_file "$ROOT/infra/modules/demo-api"       "w3-tf-api-public-url" "api module"           || MISSING=1
  if grep -q 'variable "enable_cloudfront"' "$TF_DIR/variables.tf" 2>/dev/null; then
    ok "the root declares var.enable_cloudfront — the D1 switch is present"
  else
    bad "infra/envs/demo/variables.tf does not declare var.enable_cloudfront"
    printf '        stage 6 passes -var enable_cloudfront=%s and would fail on an undeclared variable.\n' \
      "$([ "$ENABLE_CLOUDFRONT" -eq 1 ] && echo true || echo false) " >&2
    printf '        owed by: w4-tf-root-and-plan\n' >&2
    MISSING=1
  fi
  if grep -q 'output "function_url"' "$ROOT/infra/modules/demo-api/outputs.tf" 2>/dev/null; then
    ok "the api module emits output.function_url — stage 7 reads the hostname from it"
  else
    bad "infra/modules/demo-api/outputs.tf emits no output \"function_url\""
    printf '        under D1 that output IS the demo hostname. owed by: w3-tf-api-public-url\n' >&2
    MISSING=1
  fi
  # The parameter name is a contract between this script and Terraform: stage 2 writes the
  # SecureString to $DSN_PARAM and stage 6 grants the Lambda role read on whatever the root
  # defaults to. A silent disagreement is a Lambda that 503s with `dsn_unset` against a
  # parameter that exists.
  TF_DSN_DEFAULT="$(sed -n '/variable "dsn_parameter_name"/,/^}/p' "$TF_DIR/variables.tf" 2>/dev/null \
                    | sed -n 's/^ *default *= *"\(.*\)"/\1/p' | head -1)"
  if [ -z "$TF_DSN_DEFAULT" ]; then
    bad "could not read var.dsn_parameter_name's default from infra/envs/demo/variables.tf"; MISSING=1
  elif [ "$TF_DSN_DEFAULT" = "$DSN_PARAM" ]; then
    ok "ssm parameter name agrees: $DSN_PARAM (this script) == var.dsn_parameter_name default"
  else
    bad "ssm parameter name DISAGREES: this script writes $DSN_PARAM, the root defaults to $TF_DSN_DEFAULT"
    MISSING=1
  fi
  need_file "$PLAN_DOC" "w4-tf-root-and-plan" "the committed terraform plan (what the orchestrator reviews)" || MISSING=1

  info "-- lambda package (w2) ------------------------------------------------------"
  ZIP_OK=1
  need_file "$LAMBDA_ZIP"      "w2-lambda-bundle" "lambda package"          || { MISSING=1; ZIP_OK=0; }
  need_file "$LAMBDA_MANIFEST" "w2-lambda-bundle" "lambda package manifest" || { MISSING=1; ZIP_OK=0; }
  if [ "$ZIP_OK" -eq 1 ]; then
    # Read-only. Opens the zip's central directory and hashes the file; writes nothing.
    if MAINLINE_ARCH="$ARCH" "$PY" - "$LAMBDA_ZIP" "$LAMBDA_MANIFEST" <<'PY'
import hashlib, json, os, sys, zipfile

zip_path, manifest_path = sys.argv[1], sys.argv[2]
want_arch = os.environ["MAINLINE_ARCH"]
problems = []

try:
    manifest = json.loads(open(manifest_path, encoding="utf-8").read())
except Exception as exc:  # noqa: BLE001
    print(f"        manifest does not parse as JSON: {exc}")
    raise SystemExit(1)

h = hashlib.sha256()
with open(zip_path, "rb") as fh:
    for chunk in iter(lambda: fh.read(1 << 20), b""):
        h.update(chunk)
digest = h.hexdigest()

declared = str(manifest.get("sha256") or "")
if declared != digest:
    problems.append(
        "the manifest's sha256 does not match the zip on disk\n"
        f"          manifest {declared or '<absent>'}\n"
        f"          measured {digest}\n"
        "          the package and its manifest were produced by different runs"
    )
if str(manifest.get("architecture") or "") != want_arch:
    problems.append(
        f"the manifest declares architecture {manifest.get('architecture')!r}, this deploy uses {want_arch!r}.\n"
        "          A zip built for one architecture on a function declared as the other is a\n"
        "          clean plan, a clean apply, and an ELFCLASS error on the first request."
    )
if str(manifest.get("runtime") or "") != "python3.13":
    problems.append(f"the manifest declares runtime {manifest.get('runtime')!r}, not 'python3.13'")

names = set()
with zipfile.ZipFile(zip_path) as zf:
    names = set(zf.namelist())

# D1: ONE origin. The console SPA and the signed bundle travel inside this zip, because
# there is no S3 in the request path and no CloudFront in front of it. A package without
# them deploys, answers /v1/health with a green 200, and 404s the URL a judge opens.
#
# The paths below are the handler's, not a guess: `static_site.resolve()` maps a request
# path onto `<web root>/<path>`, so `/` is `web/index.html` and `/bundle/manifest.json` is
# `web/bundle/manifest.json`. `/assets/` and `/bundle/` are the two prefixes it will NOT
# fall back to index.html for, which is precisely why a miss there has to be caught here.
if "web/index.html" not in names:
    problems.append(
        "the package carries no web/index.html.\n"
        "          Under decision D1 the Lambda serves the console SPA at `/` from\n"
        "          $MAINLINE_WEB_ROOT (module default /var/task/web). Without it the demo\n"
        "          URL 404s while /v1/health is perfectly green — the exact failure the\n"
        "          demo-api module's `web_root` output exists to let a deploy catch here."
    )
if "web/bundle/manifest.json" not in names:
    problems.append(
        "the package carries no web/bundle/manifest.json.\n"
        "          That is the console's REPLAY source, served at /bundle/manifest.json.\n"
        "          `static_site` does not fall back to index.html under /bundle/, so a miss\n"
        "          there is a hard 404 and the REPLAY badge has nothing behind it."
    )
# The module's `web_root` default is /var/task/web and this script does not pass
# `-var web_root=…`, so a manifest declaring anything else means the handler will look
# somewhere the packer did not write.
declared_root = str(manifest.get("web_root") or "")
if declared_root and declared_root != "/var/task/web":
    problems.append(
        f"the manifest declares web_root {declared_root!r}, but stage 6 passes no\n"
        "          -var web_root and the demo-api module defaults to '/var/task/web'."
    )

print(f"        sha256 {digest}")
print(f"        {len(names)} entries · arch {manifest.get('architecture')} · runtime {manifest.get('runtime')}")
print(f"        web/ {sum(1 for n in names if n.startswith('web/'))} entries · "
      f"web/bundle/ {sum(1 for n in names if n.startswith('web/bundle/'))} entries · "
      f"web_root {declared_root or '<undeclared>'}")
for p in problems:
    print(f"        - {p}")
raise SystemExit(1 if problems else 0)
PY
    then ok "package and manifest agree, and the package carries the console and the bundle"
    else bad "the lambda package is not deployable as it stands (owed by: w2-lambda-bundle)"; MISSING=1
    fi
  fi

  info "-- console and evidence bundle (w1 · w2) ------------------------------------"
  need_file "$CONSOLE_DIR/package.json"          "w1-gate-run-route" "console source"            || MISSING=1
  need_file "$CONSOLE_DIR/dist/index.html"       "w1-gate-run-route" "console build (dist/)"     || MISSING=1
  need_file "$BUNDLE_SRC/manifest.json"          "w2-lambda-bundle"  "EvidenceBundle manifest"   || MISSING=1

  info "-- deploy programs ----------------------------------------------------------"
  need_file "$SCRIPT_DIR/cloud_chain.py"  "w6-live-services"        "migration applier" || MISSING=1
  need_file "$SCRIPT_DIR/seed_demo.py"    "w6-live-services"        "demo seed"         || MISSING=1
  need_file "$CAPTURE_BUNDLE"             "w2-lambda-bundle"        "bundle capture"    || MISSING=1
  need_file "$BUILD_LAMBDA"               "w2-lambda-bundle"        "lambda build"      || MISSING=1
  need_file "$ACCEPTANCE"                 "w8-acceptance-and-video" "acceptance prover" || MISSING=1
  need_file "$SCRIPT_DIR/bootstrap_state.sh" "w5-deploy-scripts"    "state bootstrap"   || MISSING=1
  need_file "$SCRIPT_DIR/teardown.sh"        "w5-deploy-scripts"    "teardown"          || MISSING=1

  info "-- live services (read-only probes) -----------------------------------------"
  # SSM: can this identity see the /mainline/ path at all, and is the parameter already
  # there? Absent is FINE and expected before the first deploy — stage 2 creates it. What
  # is not fine is the API refusing the call, because stage 2 would then fail after the
  # state bucket exists.
  if SSM_LIST="$("${AWSX[@]}" ssm describe-parameters --parameter-filters "Key=Name,Option=BeginsWith,Values=/mainline/" --query 'Parameters[].Name' 2>&1)"; then
    if [ -n "$SSM_LIST" ]; then
      ok "ssm answers for /mainline/ — present: $SSM_LIST"
    else
      ok "ssm answers for /mainline/ — no parameter yet (stage 2 creates $DSN_PARAM)"
    fi
  else
    bad "aws ssm describe-parameters was refused: $SSM_LIST"
    printf '        stage 2 needs ssm:PutParameter and kms:Encrypt on alias/aws/ssm.\n' >&2
    MISSING=1
  fi

  # The Cloud cluster. Connect for real, select the demo database EXPLICITLY rather than
  # trusting the DSN's path segment (the committed DSN names /defaultdb; the demo lives in
  # mainline_demo, and a tool that trusts the path reads an empty database and reports
  # UndefinedTable). Read-only: three SELECTs, no DDL, no writes.
  if [ -z "${COCKROACH_DSN:-}" ]; then
    bad "no COCKROACH_DSN — cannot probe the Cloud cluster"; MISSING=1
  elif MAINLINE_DEMO_DATABASE="$DEMO_DATABASE" "$PY" - <<'PY'
import os, sys, time, urllib.parse

try:
    import psycopg
except ImportError:
    print("        psycopg is not installed in this virtualenv")
    raise SystemExit(1)

base = os.environ["COCKROACH_DSN"]
db = os.environ["MAINLINE_DEMO_DATABASE"]
u = urllib.parse.urlsplit(base)
target = urllib.parse.urlunsplit((u.scheme, u.netloc, "/" + db, u.query, ""))
started = time.monotonic()
try:
    with psycopg.connect(target, connect_timeout=25) as conn:
        row = conn.execute(
            "SELECT version(), current_database(),"
            " (SELECT count(*) FROM trappoint.deploy_chain),"
            " (SELECT encode(fingerprint,'hex') FROM trappoint.schema_attestation"
            "   ORDER BY ordinal DESC LIMIT 1)"
        ).fetchone()
except Exception as exc:  # noqa: BLE001
    code = getattr(exc, "sqlstate", None) or "-----"
    print(f"        [{code}] {str(exc).splitlines()[0][:300]}")
    print(f"        host {u.hostname}:{u.port or 26257} database {db}")
    raise SystemExit(1)
elapsed = time.monotonic() - started
version, current, chains, fp = row
print(f"        {u.hostname} · {current} · {version.split(' (')[0]} · {elapsed:.2f}s")
print(f"        deploy_chain rows {chains} · schema_attestation fingerprint {(fp or '')[:16]}…")
if current != db:
    print(f"        connected to {current!r}, wanted {db!r}")
    raise SystemExit(1)
if not fp:
    print("        trappoint.schema_attestation is empty: /v1/health would answer 503 no_bookkeeping")
    raise SystemExit(1)
PY
  then ok "CockroachDB Cloud answered, and $DEMO_DATABASE carries the bookkeeping schema"
  else bad "the Cloud cluster did not answer as $DEMO_DATABASE (owed by: w6-live-services)"; MISSING=1
  fi

  info "-- operator secrets (NOT gated unless --strict-secrets) ---------------------"
  if [ -n "${COCKROACH_DSN:-}" ]; then ok "COCKROACH_DSN present (host $DSN_HOST)"; else bad "COCKROACH_DSN absent"; SECRETS_MISSING=1; fi
  if [ -n "$API_DSN_SOURCE" ]; then
    ok "the Lambda's DSN is available ($API_DSN_SOURCE)"
  else
    bad "the Lambda's DSN is NOT available — stage 2 would refuse"
    printf '%s\n' "$API_DSN_ADVICE" | sed 's/^ *//; s/^/        /' >&2
    SECRETS_MISSING=1
  fi
  if [ "$STRICT_SECRETS" -eq 1 ]; then
    info "--strict-secrets: the rows above are gated on this run."
  else
    info "A clean checkout never has these; they are minted once and stored nowhere in the"
    info "repository. Re-run with --strict-secrets to make them fatal, which is what a real"
    info "deploy does at stage 0 and stage 2."
  fi

  printf '\n'
  if [ "$MISSING" -ne 0 ]; then
    die "one or more prerequisites are missing or wrong (listed above, each naming the worker
   that owes it). A dry run that found a hole exits non-zero on purpose: this is the
   check, not a preview. NOTHING WAS WRITTEN." 1
  fi
  if [ "$STRICT_SECRETS" -eq 1 ] && [ "$SECRETS_MISSING" -ne 0 ]; then
    die "--strict-secrets was passed and an operator secret is missing (listed above).
   Every artefact this repository owes IS present; what is absent is a credential a human
   mints. NOTHING WAS WRITTEN." 3
  fi
  ok "every prerequisite is present — a real run would proceed"
  info "It would still stop at the apply gate unless MAINLINE_APPLY_APPROVED=1."
  exit 0
fi

# ══════════════════════════════════════════════════════════════════════════════════════
# STAGE 1 — STATE BACKEND
# ══════════════════════════════════════════════════════════════════════════════════════
stage 1 "state backend"
bash "$SCRIPT_DIR/bootstrap_state.sh" --bucket "$STATE_BUCKET" --region "$REGION" --profile "$PROFILE" \
  --expect-account "$ACCOUNT" \
  || die "bootstrap_state.sh refused or failed. Its message above says which.
   Nothing has been created by this run beyond what it reported." 1
ok "s3://$STATE_BUCKET ready (versioned, private, encrypted, tagged, native locking)"

# ══════════════════════════════════════════════════════════════════════════════════════
# STAGE 2 — THE SECRET, INTO SSM, NEVER INTO TERRAFORM
# ══════════════════════════════════════════════════════════════════════════════════════
stage 2 "secret"
# The payload is built in a 0600 temp file and passed with --cli-input-json, so the DSN
# never appears in an argument vector, in `ps`, in shell history, or in a log. The trap
# removes it on every exit path including a failed AWS call.
SSM_JSON="$(mktemp "${TMPDIR:-/tmp}/mainline-ssm.XXXXXX.json")"
chmod 600 "$SSM_JSON"
trap 'rm -f "$SSM_JSON"' EXIT INT TERM

MAINLINE_API_DSN="${MAINLINE_API_DSN:-}" \
MAINLINE_API_PASSWORD="${MAINLINE_API_PASSWORD:-}" \
COCKROACH_DSN="${COCKROACH_DSN:-}" \
DSN_PARAM="$DSN_PARAM" \
MAINLINE_DEMO_DATABASE="$DEMO_DATABASE" \
"$PY" - "$SSM_JSON" <<'PY' || die "could not build the SSM payload." 1
import json, os, sys, urllib.parse

out = sys.argv[1]
db = os.environ.get("MAINLINE_DEMO_DATABASE") or "mainline_demo"
dsn = os.environ.get("MAINLINE_API_DSN", "").strip()
if not dsn:
    base = os.environ.get("COCKROACH_DSN", "").strip()
    pw = os.environ.get("MAINLINE_API_PASSWORD", "").strip()
    if not (base and pw):
        sys.exit("neither MAINLINE_API_DSN nor (COCKROACH_DSN + MAINLINE_API_PASSWORD)")
    u = urllib.parse.urlsplit(base)
    host = u.hostname or ""
    port = f":{u.port}" if u.port else ""
    userinfo = f"mainline_api:{urllib.parse.quote(pw, safe='')}"
    # The database is forced: the admin DSN usually points at defaultdb, and a Lambda
    # connected to the wrong database fails in a way that reads like a privilege error.
    # The query string is kept verbatim because a Cloud Basic DSN's sslmode and options
    # are load-bearing.
    dsn = urllib.parse.urlunsplit((u.scheme, f"{userinfo}@{host}{port}", f"/{db}", u.query, ""))
if "mainline_api" not in dsn:
    sys.exit("refusing: the DSN does not name the mainline_api login. The Lambda must not "
             "connect as an admin — see docs/deploy/cloud-database.md section 3.")
with open(out, "w", encoding="utf-8") as fh:
    json.dump({
        "Name": os.environ["DSN_PARAM"],
        "Type": "SecureString",
        "Overwrite": True,
        "Tier": "Standard",
        "Description": "CockroachDB Cloud DSN for the mainline_demo Lambda. Written by scripts/deploy/deploy.sh, never by Terraform.",
        "Value": dsn,
    }, fh)
PY

VERSION="$("${AWSX[@]}" ssm put-parameter --cli-input-json "file://$(winpath "$SSM_JSON")" --query Version 2>/dev/null)" \
  || die "aws ssm put-parameter failed for $DSN_PARAM.
   The IAM identity needs ssm:PutParameter and kms:Encrypt on alias/aws/ssm." 1
rm -f "$SSM_JSON"; trap - EXIT INT TERM
ok "$DSN_PARAM written as SecureString, version $VERSION"

# Tagged separately: put-parameter with Overwrite=true rejects Tags outright.
"${AWSX[@]}" ssm add-tags-to-resource --resource-type Parameter --resource-id "$DSN_PARAM" \
  --tags Key=project,Value=mainline Key=managed_by,Value=deploy.sh >/dev/null 2>&1 \
  || info "(could not tag the parameter — teardown falls back to the /mainline/ name prefix)"

# Read the metadata back WITHOUT --with-decryption. This proves the write landed and
# cannot print the value even by accident.
TYPE="$("${AWSX[@]}" ssm get-parameter --name "$DSN_PARAM" --query 'Parameter.Type' 2>/dev/null || echo '?')"
[ "$TYPE" = "SecureString" ] || die "the parameter came back as type '$TYPE', not SecureString." 1
ok "read back: type=SecureString (value not requested, and never will be by this script)"

# ══════════════════════════════════════════════════════════════════════════════════════
# STAGE 3 — THE DATABASE
# ══════════════════════════════════════════════════════════════════════════════════════
stage 3 "database"
if [ "$SKIP_DB" -eq 1 ]; then
  skip "--skip-db"
else
  CHAIN_ARGS=()
  [ "$RECREATE_DB" -eq 1 ] && CHAIN_ARGS+=(--recreate)
  set +e
  "$PY" "$SCRIPT_DIR/cloud_chain.py" "${CHAIN_ARGS[@]+"${CHAIN_ARGS[@]}"}"
  CHAIN_RC=$?
  set -e
  case "$CHAIN_RC" in
    0) ok "migration chain applied or already correct" ;;
    3) die "cloud_chain.py refused: the migration tree or the live schema has drifted from
   the fingerprint recorded in trappoint.deploy_chain, and it will not replay
   forward-only migrations over a live database. Re-run with --recreate-db to rebuild
   $DEMO_DATABASE from empty. Nothing was changed." 1 ;;
    *) die "cloud_chain.py exited $CHAIN_RC. Its output above names the file and SQLSTATE." 1 ;;
  esac

  "$PY" "$SCRIPT_DIR/seed_demo.py" \
    || die "seed_demo.py failed. The demo world is what the console and the EvidenceBundle
   both read; a deploy on top of an unseeded database would serve an empty screen." 1
  ok "demo world seeded and the seeded permit verified refusable"
fi

# ══════════════════════════════════════════════════════════════════════════════════════
# STAGE 4 — THE LAMBDA PACKAGE
# ══════════════════════════════════════════════════════════════════════════════════════
#
# Under D1 this zip is the ENTIRE deployable: handler, psycopg, the console SPA under
# web/, and the signed evidence bundle under bundle/. There is no second artefact and no
# S3 in the request path, so what is not in here is not on the internet.
stage 4 "lambda package"
if [ "$SKIP_BUILD" -eq 1 ]; then
  [ -f "$LAMBDA_ZIP" ] || die "--skip-build was passed but $LAMBDA_ZIP does not exist." 1
  skip "--skip-build, reusing $LAMBDA_ZIP"
else
  [ -f "$BUILD_LAMBDA" ] || die "neither scripts/deploy/build_lambda.sh nor build_lambda.ps1 exists.
   It is owed by worker w2-lambda-bundle and builds the psycopg-bearing deployment zip." 1
  # --console-transport live, HARD-WIRED, and not an option of this script.
  #
  # This stage packages the console for THIS origin, and this origin has a live kernel
  # behind it: infra/modules/demo-api serves /v1/* and the SPA from one Function URL. So
  # the only honest declaration a deploy can make is `live`, and making it a flag would
  # be offering an operator the ability to re-ship the defect of 2026-08-14 -- a console
  # compiled with VITE_MAINLINE_API_BASE="" and VITE_MAINLINE_BUNDLE_URL="./bundle/",
  # every byte on a judge's screen a recording of a run that happened somewhere else.
  #
  # This is not a lock-out. An operator who genuinely means to deploy a different artefact
  # builds it themselves with `scripts/deploy/build_lambda.sh --console-transport <x>` and
  # passes --skip-build here, which is a decision that appears in a shell history and in
  # this script's log rather than one that happens by default.
  case "$BUILD_LAMBDA" in
    *.ps1) pwsh -NoProfile -File "$BUILD_LAMBDA" -Arch "$ARCH" -Out "$LAMBDA_ZIP" -ConsoleTransport live || die "build_lambda.ps1 failed. If it REFUSED [CONSOLE TRANSPORT] or
   [CONSOLE BUILD ID], the console dist/ is not a live artefact: rebuild it with
   VITE_MAINLINE_API_BASE and MAINLINE_BUILD_ID set (docs/deploy/console-build.md)." 1 ;;
    *)     bash "$BUILD_LAMBDA" --arch "$ARCH" --out "$LAMBDA_ZIP" --console-transport live || die "build_lambda.sh failed. If it REFUSED [CONSOLE TRANSPORT] or
   [CONSOLE BUILD ID], the console dist/ is not a live artefact: rebuild it with
   VITE_MAINLINE_API_BASE and MAINLINE_BUILD_ID set (docs/deploy/console-build.md)." 1 ;;
  esac
  [ -f "$LAMBDA_ZIP" ] || die "build_lambda finished but $LAMBDA_ZIP is not there.
   Set MAINLINE_LAMBDA_ZIP if it writes somewhere else." 1
fi
[ -f "$LAMBDA_MANIFEST" ] || die "$LAMBDA_MANIFEST is missing. The build writes a manifest beside
   the zip and this script refuses to deploy a package whose contents it cannot assert." 1
MAINLINE_ARCH="$ARCH" "$PY" - "$LAMBDA_ZIP" "$LAMBDA_MANIFEST" <<'PY' \
  || die "the package and its manifest disagree, or the package is missing the console or the
   bundle (detail above). Rebuild it: scripts/deploy/build_lambda.sh --arch $ARCH" 1
import hashlib, json, os, sys, zipfile

zip_path, manifest_path = sys.argv[1], sys.argv[2]
want = os.environ["MAINLINE_ARCH"]
manifest = json.loads(open(manifest_path, encoding="utf-8").read())
h = hashlib.sha256()
with open(zip_path, "rb") as fh:
    for chunk in iter(lambda: fh.read(1 << 20), b""):
        h.update(chunk)
digest = h.hexdigest()
bad = []
if str(manifest.get("sha256") or "") != digest:
    bad.append(f"sha256 mismatch: manifest {manifest.get('sha256')} vs measured {digest}")
if str(manifest.get("architecture") or "") != want:
    bad.append(f"architecture {manifest.get('architecture')!r} != {want!r}")
with zipfile.ZipFile(zip_path) as zf:
    names = set(zf.namelist())
if "web/index.html" not in names:
    bad.append("no web/index.html — the demo URL would 404 while /v1/health stayed green")
if "web/bundle/manifest.json" not in names:
    bad.append("no web/bundle/manifest.json — the console's REPLAY source is absent")
declared_root = str(manifest.get("web_root") or "")
if declared_root and declared_root != "/var/task/web":
    bad.append(f"manifest web_root {declared_root!r} != the module default '/var/task/web'")
for b in bad:
    print(f"   - {b}", file=sys.stderr)
print(f"   sha256 {digest} · {len(names)} entries")
raise SystemExit(1 if bad else 0)
PY
ok "$LAMBDA_ZIP ($(wc -c < "$LAMBDA_ZIP" | tr -d ' ') bytes) verified against its manifest"

# ══════════════════════════════════════════════════════════════════════════════════════
# STAGE 5 — THE SITE PAYLOAD (OPTIONAL UNDER D1)
# ══════════════════════════════════════════════════════════════════════════════════════
#
# Under D1 there is no S3 bucket in the request path: the console and the bundle are in
# the zip stage 4 just verified. This stage still BUILDS them, because stage 4's zip is
# built from them — but it uploads nothing unless --enable-cloudfront restores the site.
stage 5 "site payload"
if [ "$SKIP_BUILD" -eq 1 ]; then
  [ -d "$CONSOLE_DIR/dist" ] || die "--skip-build was passed but $CONSOLE_DIR/dist does not exist." 1
  skip "--skip-build, reusing $CONSOLE_DIR/dist"
else
  if [ -n "${MAINLINE_CONSOLE_BUILD_CMD:-}" ]; then
    info "console build: \$MAINLINE_CONSOLE_BUILD_CMD"
    ( cd "$CONSOLE_DIR" && eval "$MAINLINE_CONSOLE_BUILD_CMD" ) || die "the console build command failed." 1
  else
    ( cd "$CONSOLE_DIR" && pnpm install --frozen-lockfile && pnpm run build ) \
      || die "the console build failed. If the console documents a different command,
   export MAINLINE_CONSOLE_BUILD_CMD and re-run." 1
  fi
  [ -f "$CONSOLE_DIR/dist/index.html" ] || die "the build produced no dist/index.html." 1
  ok "console built: $(find "$CONSOLE_DIR/dist" -type f | wc -l | tr -d ' ') files"
fi

[ -f "$CAPTURE_BUNDLE" ] || die "scripts/deploy/capture_demo_bundle.py does not exist. It captures the
   cryptographically verified EvidenceBundle from the Cloud cluster and is the console's
   REPLAY source. There is no way to fake this file and none is attempted." 1
"$PY" "$CAPTURE_BUNDLE" \
  || die "capture_demo_bundle.py failed. The bundle is the console's REPLAY source and it
   ships inside the Lambda package; deploying without it would serve a REPLAY badge with
   nothing behind it." 1
ok "EvidenceBundle captured into $BUNDLE_SRC"

if [ "$ENABLE_CLOUDFRONT" -eq 0 ]; then
  skip "no S3 upload — under D1 the console and the bundle are served from the Lambda package"
fi

# ══════════════════════════════════════════════════════════════════════════════════════
# STAGE 6 — INFRASTRUCTURE  ·  PLAN ALWAYS, APPLY ONLY BEHIND THE GATE
# ══════════════════════════════════════════════════════════════════════════════════════
stage 6 "infrastructure"
cd "$TF_DIR"
terraform init -input=false -reconfigure \
  -backend-config="bucket=$STATE_BUCKET" \
  -backend-config="region=$REGION" \
  || die "terraform init failed. If it complains about a state lock, see
   docs/deploy/RUNBOOK.md § 'Error acquiring the state lock'." 1

TF_VARS=(
  -var "aws_region=$REGION"
  -var "dsn_parameter_name=$DSN_PARAM"
  -var "name_prefix=$NAME_PREFIX"
  -var "enable_api=true"
  -var "lambda_package_path=$LAMBDA_ZIP"
  -var "lambda_architecture=$ARCH"
)
if [ "$ENABLE_CLOUDFRONT" -eq 1 ]; then
  TF_VARS+=(-var "enable_cloudfront=true")
  info "enable_cloudfront=true — the pre-D1 shape. AWS will refuse the distribution on an"
  info "account still under the verification hold; see docs/deploy/RUNBOOK.md appendix A."
else
  TF_VARS+=(-var "enable_cloudfront=false")
  info "enable_cloudfront=false — D1. The Lambda Function URL is the hostname."
fi

TF_PLAN="$(mktemp "${TMPDIR:-/tmp}/mainline-plan.XXXXXX.tfplan")"
trap 'rm -f "$TF_PLAN"' EXIT INT TERM
terraform plan -input=false -out="$TF_PLAN" "${TF_VARS[@]}" \
  || die "terraform plan failed. Nothing has been created or changed by this stage." 1
ok "plan written"

# ── THE APPROVAL GATE ─────────────────────────────────────────────────────────────────
#
# This is a feature of the script, not a scaffold, and it is not removed when the demo
# ships. `terraform apply` is the one irreversible, billable step in nine stages, and the
# founder reviews the plan before it runs. The script therefore cannot apply on its own
# initiative — the environment has to say so.
if [ "$APPLY_APPROVED" -ne 1 ]; then
  rm -f "$TF_PLAN"; trap - EXIT INT TERM
  cat >&2 <<EOF

${BOLD}STOPPED AT THE APPROVAL GATE — stage 6 planned, and did not apply.${RESET}

   Nothing was created. Nothing was changed. No URL was printed, because none exists.
   THIS IS NOT A FAILURE. It is the designed halt, and it exits 7 so that neither a human
   nor a CI job can mistake it for a completed deploy.

   The plan above is the one the orchestrator reviews with the founder. The reviewed copy
   lives at:

       docs/deploy/terraform-plan.md

   To proceed once it is approved:

       MAINLINE_APPLY_APPROVED=1 scripts/deploy/deploy.sh --expect-account $ACCOUNT

   Stages 1 to 5 have already run and are idempotent, so the approved run repeats them
   cheaply and picks up exactly here.

EOF
  exit 7
fi

terraform apply -input=false "$TF_PLAN" \
  || die "terraform apply failed. Nothing else in this script has run; the state file
   records exactly what did get created, and 'scripts/deploy/teardown.sh --yes' removes it.

   IF THE ERROR MENTIONS CloudFront AND 'Your account must be verified':
     that is an AWS account-level hold on creating NEW CloudFront resources, not a bug in
     this repository, and D1 exists precisely so it cannot block the demo. Re-run WITHOUT
     --enable-cloudfront. docs/deploy/RUNBOOK.md appendix A carries the transcript." 1
rm -f "$TF_PLAN"; trap - EXIT INT TERM
ok "apply completed"

# ══════════════════════════════════════════════════════════════════════════════════════
# STAGE 7 — PUBLISH, AND PROVE THE HOSTNAME OVER HTTPS
# ══════════════════════════════════════════════════════════════════════════════════════
#
# THE BINDING RULE: THERE IS NO PATH THROUGH THIS SCRIPT THAT PRINTS A URL IT DID NOT JUST
# FETCH OVER HTTPS. Everything below exists to keep it true.
stage 7 "publish"
OUTPUTS="$(terraform output -json)" || die "terraform output -json failed after a successful apply." 1
cd "$ROOT"

# The hostname. Under D1 it comes from the api module's `function_url`, surfaced by the
# root; with --enable-cloudfront it is the distribution's. The resolver names the key it
# used, so the transcript records where the URL came from rather than asserting it.
RESOLVED="$(printf '%s' "$OUTPUTS" | "$PY" - <<'PY'
import json, sys

outputs = json.load(sys.stdin)
flat = {}
for name, spec in outputs.items():
    value = spec.get("value") if isinstance(spec, dict) else spec
    flat[name] = value
    if isinstance(value, dict):
        for k, v in value.items():
            flat.setdefault(f"{name}.{k}", v)

# Order matters: `demo_url` is the root's own answer to "which hostname is the demo" and
# it already follows var.enable_cloudfront, so it wins. The others are the fallbacks that
# let this script work against a root that has not surfaced demo_url yet.
CANDIDATES = [
    "demo_url",
    "deploy_summary.demo_url",
    "api_function_url",
    "deploy_summary.api_function_url",
    "function_url",
    "deploy_summary.function_url",
]
for key in CANDIDATES:
    value = flat.get(key)
    if isinstance(value, str) and value.startswith("https://"):
        print(json.dumps({"key": key, "url": value.rstrip("/"), "flat": sorted(flat)}))
        break
else:
    print(json.dumps({"key": None, "url": None, "flat": sorted(flat), "candidates": CANDIDATES}))
PY
)"
DEMO_URL="$(printf '%s' "$RESOLVED" | "$PY" -c 'import json,sys;print(json.load(sys.stdin)["url"] or "")')"
URL_KEY="$(printf '%s' "$RESOLVED" | "$PY" -c 'import json,sys;print(json.load(sys.stdin)["key"] or "")')"
if [ -z "$DEMO_URL" ]; then
  printf '%s' "$RESOLVED" | "$PY" -c '
import json,sys
d=json.load(sys.stdin)
print("   looked for, in order: " + ", ".join(d["candidates"]))
print("   the root emitted:     " + ", ".join(d["flat"]))' >&2
  die "terraform applied but no output holds an https:// demo hostname (see above).
   Under D1 the root must surface the api module's function_url. Nothing is printed as a
   working URL until one exists." 1
fi
ok "hostname from terraform output '$URL_KEY': $DEMO_URL"

summary_key() {  # read one key from deploy_summary, falling back to the top-level output
  printf '%s' "$OUTPUTS" | MAINLINE_KEY="$1" "$PY" -c '
import json, os, sys
o = json.load(sys.stdin)
key = os.environ["MAINLINE_KEY"]
s = (o.get("deploy_summary") or {}).get("value") or {}
print(s.get(key) or (o.get(key) or {}).get("value") or "")'
}
SITE_BUCKET="$(summary_key site_bucket)"
DIST_ID="$(summary_key distribution_id)"
FN_NAME="$(summary_key api_function_name)"
URL_SOURCE="$(summary_key demo_url_source)"
AUTH_TYPE="$(summary_key api_authorization_type)"
PHASE="$(summary_key phase)"
[ -n "$URL_SOURCE" ] && ok "terraform's own account of it: demo_url_source = $URL_SOURCE"
[ -n "$PHASE" ]      && ok "phase        $PHASE"
[ -n "$FN_NAME" ]    && ok "lambda       $FN_NAME"
[ -n "$AUTH_TYPE" ]  && ok "furl auth    $AUTH_TYPE"
if [ "$ENABLE_CLOUDFRONT" -eq 0 ] && [ -n "$AUTH_TYPE" ] && [ "$AUTH_TYPE" != "NONE" ]; then
  die "the Function URL is the demo hostname in this shape, but Terraform reports its
   authorization_type as '$AUTH_TYPE'. An unsigned GET to an AWS_IAM Function URL is a 403
   with an empty body, so no judge could open it. Nothing is printed as a working URL." 1
fi

# ── The optional S3 upload. Only reachable with --enable-cloudfront. ──────────────────
#
# Content types are set EXPLICITLY and not left to `aws s3 sync`'s guess, because that
# guess comes from Python's `mimetypes`, which on Windows reads the registry. Measured on
# this machine with the repository interpreter:
#
#     .js    → application/javascript      (fine)
#     .mjs   → text/plain                  ← a module served as text/plain does not load
#     .map   → text/plain                  (harmless)
#     .woff2 → None                        ← falls back to binary/octet-stream
if [ "$ENABLE_CLOUDFRONT" -eq 1 ] && [ -n "$SITE_BUCKET" ]; then
  S3X=(aws --profile "$PROFILE" --region "$REGION" --no-cli-pager)
  "${S3X[@]}" s3 sync "$CONSOLE_DIR/dist/" "s3://$SITE_BUCKET/" --delete \
    --exclude "index.html" --exclude "*.mjs" --exclude "*.js" --exclude "*.css" --exclude "*.woff2" --exclude "*.map" \
    --cache-control "public, max-age=31536000, immutable" \
    || die "s3 sync of the static assets failed." 1
  sync_typed() {  # glob, content-type
    "${S3X[@]}" s3 cp "$CONSOLE_DIR/dist/" "s3://$SITE_BUCKET/" --recursive \
      --exclude "*" --include "$1" \
      --content-type "$2" --cache-control "public, max-age=31536000, immutable" >/dev/null \
      || die "s3 cp of $1 failed." 1
  }
  sync_typed "*.js"    "text/javascript; charset=utf-8"
  sync_typed "*.mjs"   "text/javascript; charset=utf-8"
  sync_typed "*.css"   "text/css; charset=utf-8"
  sync_typed "*.map"   "application/json; charset=utf-8"
  sync_typed "*.woff2" "font/woff2"
  "${S3X[@]}" s3 cp "$CONSOLE_DIR/dist/index.html" "s3://$SITE_BUCKET/index.html" \
    --content-type "text/html; charset=utf-8" \
    --cache-control "no-cache, no-store, must-revalidate" >/dev/null \
    || die "s3 cp of index.html failed." 1
  ok "console uploaded to s3://$SITE_BUCKET with explicit content types"
  if [ -d "$DIST_BUNDLE" ] || [ -d "$BUNDLE_SRC" ]; then
    SRC="$([ -d "$DIST_BUNDLE" ] && echo "$DIST_BUNDLE" || echo "$BUNDLE_SRC")"
    "${S3X[@]}" s3 sync "$SRC/" "s3://$SITE_BUCKET/bundle/" --delete \
      --cache-control "no-cache, must-revalidate" >/dev/null \
      || die "s3 sync of the EvidenceBundle failed." 1
    ok "EvidenceBundle published under /bundle/"
  fi
  if [ -n "$DIST_ID" ]; then
    "${S3X[@]}" cloudfront create-invalidation --distribution-id "$DIST_ID" \
      --paths "/index.html" "/" --output text >/dev/null \
      || die "the CloudFront invalidation failed. The objects are uploaded; judges would see
   the previous index.html until the cache expires. Re-run:
     aws cloudfront create-invalidation --distribution-id $DIST_ID --paths '/index.html' '/'" 1
    ok "invalidated /index.html and /"
  fi
else
  skip "no S3 publish step in the D1 shape — the payload is inside the deployed package"
fi

# ── THE HTTPS PROOF. Two GETs, both asserted, before a single character of URL is printed.
info "fetching $DEMO_URL/ over HTTPS…"
CODE=""
CTYPE=""
for i in $(seq 1 20); do
  CODE="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 20 "$DEMO_URL/" 2>/dev/null || echo 000)"
  [ "$CODE" = "200" ] && break
  sleep 15
done
[ "$CODE" = "200" ] || die "GET $DEMO_URL/ answered HTTP $CODE after five minutes of trying.
   The infrastructure exists; the hostname does not serve the console. Under D1 that means
   the package's web/ root is missing or \$MAINLINE_WEB_ROOT disagrees with it — check
   'terraform output -raw web_root' against the zip. NOTHING IS PRINTED AS A WORKING URL
   UNTIL IT IS ONE." 1
CTYPE="$(curl -sSI --max-time 20 "$DEMO_URL/" 2>/dev/null | tr -d '\r' | sed -n 's/^[Cc]ontent-[Tt]ype: *//p' | head -1)"
ok "GET $DEMO_URL/ → 200  ($CTYPE)"
case "$CTYPE" in
  text/html*) : ;;
  *) die "GET $DEMO_URL/ answered 200 but with Content-Type '$CTYPE', not text/html.
   A judge opening that URL gets a download or a wall of text, not the console." 1 ;;
esac

info "fetching $DEMO_URL/v1/health…"
# `set +e` rather than `|| true`: a transport failure must leave HEALTH_CODE unset so the
# assertion below fails, and it must not be silently converted into a success by `set -e`
# being disarmed for the rest of the line.
set +e
HEALTH_BODY="$(curl -sS --max-time 25 -w '\n%{http_code}' "$DEMO_URL/v1/health" 2>&1)"
CURL_RC=$?
set -e
[ "$CURL_RC" -eq 0 ] || die "curl could not reach $DEMO_URL/v1/health (exit $CURL_RC):
   $HEALTH_BODY
   GET / answered 200 a moment ago, so this is the API path specifically." 1
HEALTH_CODE="$(printf '%s' "$HEALTH_BODY" | tail -1)"
HEALTH_JSON="$(printf '%s' "$HEALTH_BODY" | sed '$d')"
[ "$HEALTH_CODE" = "200" ] || die "GET $DEMO_URL/v1/health answered HTTP $HEALTH_CODE, not 200.
   Body: $HEALTH_JSON
   A 503 with reason 'dsn_unset' means the Lambda cannot see $DSN_PARAM (check the role's
   ssm:GetParameter grant). 'unreachable' means the DSN is wrong or the cluster refused.
   'no_bookkeeping' means it connected to a database the migration chain never touched.
   THE URL IS NOT PRINTED." 1

MAINLINE_DEMO_DATABASE="$DEMO_DATABASE" "$PY" - "$HEALTH_JSON" <<'PY' \
  || die "/v1/health answered 200 but the body does not name the cluster it is talking to
   (detail above). A health check that cannot say which database answered is not proof of
   anything, so this URL is not printed." 1
import json, os, sys

want_db = os.environ["MAINLINE_DEMO_DATABASE"]
try:
    body = json.loads(sys.argv[1])
except Exception as exc:  # noqa: BLE001
    print(f"   /v1/health returned non-JSON: {exc}", file=sys.stderr)
    raise SystemExit(1)

problems = []
if body.get("ok") is not True:
    problems.append(f"ok is {body.get('ok')!r}: reason={body.get('reason')!r} detail={body.get('detail')!r}")
version = body.get("cluster_version") or ""
if "CockroachDB" not in version:
    problems.append(f"cluster_version does not name CockroachDB: {version!r}")
if body.get("database") != want_db:
    problems.append(f"database is {body.get('database')!r}, expected {want_db!r}")
if not body.get("schema_fingerprint"):
    problems.append("schema_fingerprint is empty — the cluster carries no attestation ledger")
for p in problems:
    print(f"   - {p}", file=sys.stderr)
if problems:
    raise SystemExit(1)
print(f"   cluster      {version.split(' (')[0]}")
print(f"   database     {body['database']}")
print(f"   fingerprint  {body['schema_fingerprint'][:32]}…")
print(f"   migrations   {body.get('migrations_applied')} applied · round trip {body.get('seconds')}s")
PY
ok "GET $DEMO_URL/v1/health → 200, and the body names the cluster"

# ══════════════════════════════════════════════════════════════════════════════════════
# STAGE 8 — PROOF
# ══════════════════════════════════════════════════════════════════════════════════════
stage 8 "proof"
[ -f "$ACCEPTANCE" ] || die "scripts/deploy/demo_acceptance.py does not exist. It is owed by worker
   w8-acceptance-and-video and is the only thing that proves the live gate refuses and
   then admits over HTTPS. A deploy that cannot prove itself is a failed deploy, so this
   is fatal rather than a warning." 1
"$PY" "$ACCEPTANCE" --url "$DEMO_URL" \
  || die "the acceptance prover exited non-zero against $DEMO_URL.
   THE DEPLOY IS FAILED. The live gate did not refuse and then admit over HTTPS, which is
   the product's entire claim. Do not submit this URL. Read the prover's output above,
   then 'aws logs tail /aws/lambda/${FN_NAME:-<function>} --since 10m'." 1
ok "the live gate refused, refused under attack, and then admitted — over HTTPS"

# ══════════════════════════════════════════════════════════════════════════════════════
# STAGE 9 — HAND-OFF
# ══════════════════════════════════════════════════════════════════════════════════════
stage 9 "hand-off"
cat <<EOF

  ${BOLD}DEMO URL${RESET}   $DEMO_URL
  proved     GET / → 200 text/html · GET /v1/health → 200 naming $DEMO_DATABASE
  shape      $SHAPE
  region     $REGION (AWS)   ·   aws-ap-southeast-1 (CockroachDB Cloud)
  account    $ACCOUNT
$([ -n "$FN_NAME" ]     && printf '  lambda     %s\n' "$FN_NAME")
$([ -n "$SITE_BUCKET" ] && printf '  bucket     s3://%s\n' "$SITE_BUCKET")
$([ -n "$DIST_ID" ]     && printf '  cloudfront %s\n' "$DIST_ID")

  ${BOLD}JUDGE ACCESS${RESET} — free and unrestricted, no sign-up, no key
  · The URL above needs no credential. Open it.
  · Read-only SQL, if a judge wants to check the database themselves:
      user      mainline_judge
      database  $DEMO_DATABASE   on cluster mainline-dev (aws-ap-southeast-1)
      scope     SELECT on the fourteen mainline_audit views, and nothing else
      password  minted by 'scripts/deploy/judge_access.py --rotate', printed once, and
                deliberately not stored by this script or anywhere in the repository.
                Paste it into the submission form's private notes field.
  · The judge pack, with the questions and the fallbacks:
      docs/deploy/JUDGE-PACK.md
  · What is broken, published on the same site as the claims:
      docs/HONESTY.md

  Teardown, when judging is over:
      scripts/deploy/teardown.sh --expect-account $ACCOUNT --yes

EOF
ok "done"
