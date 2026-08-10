#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
#
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
#   4  lambda package   scripts/deploy/build_lambda.sh             (skipped by --phase1)
#   5  site payload     console build, then capture_demo_bundle.py
#   6  infrastructure   terraform init + apply
#   7  publish          aws s3 sync + CloudFront invalidation
#   8  proof            demo_acceptance.py against the live URL — MUST exit 0
#   9  hand-off         the URL and the judge credential block
#
# `--phase1` stops after stage 7 and skips stage 4 entirely: no Lambda, no API, no
# `/v1/*` behaviour. It is the cut line from `docs/leads/deploy-plan.md` § 4 and it exists
# so that THE URL IS NEVER HOSTAGE TO THE BACKEND. It still runs stage 3 (the database is
# what the EvidenceBundle was captured from) and stage 5 (the bundle is the demo), and it
# still ends with a live HTTPS check of its own before it prints anything.
#
# WHAT THIS SCRIPT NEVER DOES
#   · echo the DSN, a password, or any string that could contain one — stage 2 builds its
#     payload in a temp file with 0600 and deletes it in a trap, and `set -x` is refused
#   · create an AWS resource outside the `mainline-demo-` prefix
#   · claim success it did not measure — stage 8 exits non-zero if the live gate did not
#     refuse and then admit over HTTPS
#
# USAGE
#   scripts/deploy/deploy.sh                     full phase-2 deploy
#   scripts/deploy/deploy.sh --phase1            URL + console + bundle, no Lambda
#   scripts/deploy/deploy.sh --dry-run           preflight + prerequisites only, no writes
#   scripts/deploy/deploy.sh --preflight-only    stage 0 and stop
#   scripts/deploy/deploy.sh --recreate-db       pass --recreate to cloud_chain.py
#   scripts/deploy/deploy.sh --skip-db           the database is already correct
#   scripts/deploy/deploy.sh --skip-build        reuse the existing dist/ and zip
#   scripts/deploy/deploy.sh --any-account       do not insist on account 022950218246
#   scripts/deploy/deploy.sh --arch x86_64       build and declare x86_64 instead of arm64
#
# ENVIRONMENT
#   COCKROACH_DSN         admin DSN for the Cloud cluster. Read from the repo-root .env
#                         if not exported. Required by stage 3.
#   MAINLINE_API_DSN      the application DSN the Lambda will use, i.e. COCKROACH_DSN with
#                         the userinfo swapped for mainline_api and its password. This is
#                         what stage 2 writes to SSM. Required unless --phase1.
#   MAINLINE_API_PASSWORD alternative to the above: stage 2 derives the DSN from
#                         COCKROACH_DSN by swapping the userinfo. Never printed.
#   MAINLINE_LAMBDA_ZIP   override the path stage 4 is expected to have produced.
#   MAINLINE_CONSOLE_BUILD_CMD  override stage 5's console build command.
#   MAINLINE_STATE_BUCKET override the derived state bucket name.
#
# EXIT CODES
#   0 the URL printed at the end was reachable over HTTPS and, in phase 2, proved itself
#   1 a stage failed — the message names the stage and what to do about it
#   2 usage error
#   3 preflight refused: wrong account, missing tool, or missing credential

set -euo pipefail

# `set -x` would defeat stage 2. Refuse rather than leak.
case "${SHELLOPTS:-}" in *xtrace*) printf 'deploy: refusing to run under `set -x` — stage 2 handles a database password.\n' >&2; exit 3 ;; esac

# ── Where everything is ───────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
TF_DIR="$ROOT/infra/envs/demo"
CONSOLE_DIR="$ROOT/verticals/mainline/apps/console"
DIST_BUNDLE="$ROOT/dist/demo-bundle"

# arm64 is `build_lambda.sh`'s default and `infra/modules/demo-api`'s default: Graviton2
# is ~20 % cheaper per GB-second and psycopg-binary 3.3.4 ships a cp313 aarch64 wheel.
# ONE variable drives both the filename and the Terraform `architecture`, because a zip
# built for one architecture on a function declared as the other is a clean plan, a clean
# apply, and an ELFCLASS error on the first request.
ARCH="arm64"

EXPECTED_ACCOUNT="022950218246"
REGION="ap-southeast-1"
PROFILE="${AWS_PROFILE:-mainline-dev}"
DSN_PARAM="/mainline/demo/cockroach_dsn"
NAME_PREFIX="mainline-demo"

PHASE1=0
DRY_RUN=0
PREFLIGHT_ONLY=0
ANY_ACCOUNT=0
RECREATE_DB=0
SKIP_DB=0
SKIP_BUILD=0
AUTO_APPROVE="-auto-approve"

# ── Output. Deliberately plain: this runs in CI, in Git Bash and over ssh. ─────────────
BOLD=""; DIM=""; RESET=""
if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then BOLD=$'\033[1m'; DIM=$'\033[2m'; RESET=$'\033[0m'; fi

STAGE_N=0
stage() { STAGE_N="$1"; printf '\n%s══ stage %s · %s%s\n' "$BOLD" "$1" "$2" "$RESET"; }
info()  { printf '   %s\n' "$*"; }
ok()    { printf '   %s✓%s %s\n' "$BOLD" "$RESET" "$*"; }
skip()  { printf '   %s· skipped — %s%s\n' "$DIM" "$*" "$RESET"; }
die()   { printf '\n%sdeploy: stage %s FAILED%s\n   %s\n\n' "$BOLD" "$STAGE_N" "$RESET" "$1" >&2; exit "${2:-1}"; }

usage() { sed -n '5,72p' "$0" | sed 's/^# \{0,1\}//'; exit "${1:-2}"; }

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
    --phase1)         PHASE1=1; shift ;;
    --dry-run)        DRY_RUN=1; shift ;;
    --preflight-only) PREFLIGHT_ONLY=1; shift ;;
    --any-account)    ANY_ACCOUNT=1; shift ;;
    --recreate-db)    RECREATE_DB=1; shift ;;
    --skip-db)        SKIP_DB=1; shift ;;
    --skip-build)     SKIP_BUILD=1; shift ;;
    --interactive)    AUTO_APPROVE=""; shift ;;
    --arch)           ARCH="${2:-}"; shift 2 ;;
    --profile)        PROFILE="${2:-}"; shift 2 ;;
    --region)         REGION="${2:-}"; shift 2 ;;
    --state-bucket)   MAINLINE_STATE_BUCKET="${2:-}"; shift 2 ;;
    -h|--help)        usage 0 ;;
    *) printf 'deploy: unknown argument %s\n' "$1" >&2; usage 2 ;;
  esac
done

export AWS_PROFILE="$PROFILE"
export AWS_REGION="$REGION"
export AWS_DEFAULT_REGION="$REGION"
AWSX=(aws --profile "$PROFILE" --region "$REGION" --output text --no-cli-pager)

printf '%sMAINLINE demo deploy%s   phase=%s  region=%s  profile=%s\n' \
  "$BOLD" "$RESET" "$([ "$PHASE1" -eq 1 ] && echo '1 (replay, no API)' || echo '2 (live API)')" "$REGION" "$PROFILE"
[ "$DRY_RUN" -eq 1 ] && printf '%sDRY RUN — nothing will be created, changed or uploaded.%s\n' "$DIM" "$RESET"

# ══════════════════════════════════════════════════════════════════════════════════════
# STAGE 0 — PREFLIGHT
# ══════════════════════════════════════════════════════════════════════════════════════
stage 0 "preflight"

need() {
  command -v "$1" >/dev/null 2>&1 \
    || die "'$1' is not on PATH. $2" 3
}
need aws       "Install the AWS CLI v2."
need terraform "Install Terraform >= 1.10 (this stack needs use_lockfile). OpenTofu >= 1.8 also works; set TF=tofu."
need curl      "curl is used for the live HTTPS check in stages 8 and 9."

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
info "python         $("$PY" --version 2>&1)  ($PY)"

need node "Install Node 20+."
info "node           $(node --version)"
if command -v pnpm >/dev/null 2>&1; then
  info "pnpm           $(pnpm --version)"
else
  [ "$SKIP_BUILD" -eq 1 ] || die "pnpm is not on PATH and stage 5 builds the console with it.
   Install pnpm, or pass --skip-build and put a built console in $CONSOLE_DIR/dist." 3
fi

# AWS identity. This is the refusal that protects the four unrelated live projects in
# this account from a deploy pointed at the wrong credentials.
ACCOUNT="$("${AWSX[@]}" sts get-caller-identity --query Account 2>/dev/null)" \
  || die "aws sts get-caller-identity failed for profile '$PROFILE'.
   Run 'aws configure --profile $PROFILE', or pass --profile <name>." 3
ARN="$("${AWSX[@]}" sts get-caller-identity --query Arn 2>/dev/null || echo '?')"
info "aws account    $ACCOUNT"
info "aws identity   $ARN"
if [ "$ACCOUNT" != "$EXPECTED_ACCOUNT" ] && [ "$ANY_ACCOUNT" -eq 0 ]; then
  die "this is account $ACCOUNT, not $EXPECTED_ACCOUNT.
   Everything this script creates carries the 'mainline-demo-' prefix, but a deploy into
   the wrong account still costs money and still has to be cleaned up by hand.
   Pass --any-account if you really mean it." 3
fi
[ "$ACCOUNT" != "$EXPECTED_ACCOUNT" ] && info "(--any-account: proceeding into a non-default account)"

# The DSN. Read from the repo-root .env when not exported, exactly like every program in
# scripts/deploy/. Its VALUE is never printed — only whether it is present and its host.
if [ -z "${COCKROACH_DSN:-}" ] && [ -f "$ROOT/.env" ]; then
  COCKROACH_DSN="$(sed -n 's/^COCKROACH_DSN=//p' "$ROOT/.env" | head -1 | sed 's/^"//; s/"$//')"
  export COCKROACH_DSN
fi
if [ -z "${COCKROACH_DSN:-}" ]; then
  if [ "$SKIP_DB" -eq 1 ]; then
    skip "COCKROACH_DSN unset, and --skip-db was passed"
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

# The application DSN for the Lambda. Phase 1 has no Lambda and does not need it.
API_DSN_SOURCE=""
if [ "$PHASE1" -eq 0 ]; then
  if [ -n "${MAINLINE_API_DSN:-}" ]; then
    API_DSN_SOURCE="MAINLINE_API_DSN"
  elif [ -n "${MAINLINE_API_PASSWORD:-}" ] && [ -n "${COCKROACH_DSN:-}" ]; then
    API_DSN_SOURCE="derived from COCKROACH_DSN + MAINLINE_API_PASSWORD"
  else
    die "the Lambda's DSN is not available, so stage 2 has nothing to write to SSM.
   Mint the login's password once:
       $PY scripts/deploy/cloud_roles.py --rotate
   then either export the whole DSN:
       export MAINLINE_API_DSN='postgresql://mainline_api:<pw>@<host>:26257/mainline_demo?sslmode=verify-full'
   or just the password, and this script will swap the userinfo into COCKROACH_DSN:
       export MAINLINE_API_PASSWORD='<pw>'
   Or run with --phase1, which needs neither." 3
  fi
  info "api dsn        available ($API_DSN_SOURCE)"
fi

STATE_BUCKET="${MAINLINE_STATE_BUCKET:-${NAME_PREFIX}-tfstate-${ACCOUNT}}"
info "state bucket   $STATE_BUCKET"
info "dsn parameter  $DSN_PARAM  (name only; the value is never in Terraform)"

ok "preflight passed"
[ "$PREFLIGHT_ONLY" -eq 1 ] && { printf '\n--preflight-only: stopping here.\n'; exit 0; }

# ── Prerequisite files produced by other workers. Named, checked, and named in the
#    failure message — a missing artefact should say WHICH program produces it. ─────────
check_artifact() {  # path, who, what
  if [ -e "$1" ]; then ok "$3: $1"; return 0; fi
  printf '   %s✗%s %s is MISSING: %s\n      produced by: %s\n' "$BOLD" "$RESET" "$3" "$1" "$2" >&2
  return 1
}

BUILD_LAMBDA=""
for cand in "$SCRIPT_DIR/build_lambda.sh" "$SCRIPT_DIR/build_lambda.ps1"; do
  [ -f "$cand" ] && { BUILD_LAMBDA="$cand"; break; }
done
CAPTURE_BUNDLE="$SCRIPT_DIR/capture_demo_bundle.py"
ACCEPTANCE="$SCRIPT_DIR/demo_acceptance.py"

if [ "$DRY_RUN" -eq 1 ]; then
  stage 0 "dry run · prerequisites"
  MISSING=0
  check_artifact "$TF_DIR/main.tf"                 "this worker"                      "terraform root"      || MISSING=1
  check_artifact "$ROOT/infra/modules/demo-site"   "w5-tf-site"                       "site module"         || MISSING=1
  check_artifact "$SCRIPT_DIR/cloud_chain.py"      "w2-cloud-database"                "migration applier"   || MISSING=1
  check_artifact "$SCRIPT_DIR/seed_demo.py"        "w2-cloud-database"                "demo seed"           || MISSING=1
  check_artifact "$CAPTURE_BUNDLE"                 "w9-evidence-bundle"               "bundle capture"      || MISSING=1
  check_artifact "$CONSOLE_DIR/package.json"       "w8-console-composition"           "console"             || MISSING=1
  if [ "$PHASE1" -eq 0 ]; then
    check_artifact "$ROOT/infra/modules/demo-api"  "w6-tf-api"                        "api module"          || MISSING=1
    [ -n "$BUILD_LAMBDA" ] && ok "lambda build: $BUILD_LAMBDA" || { printf '   %s✗%s lambda build is MISSING: scripts/deploy/build_lambda.sh\n      produced by: w6-tf-api\n' "$BOLD" "$RESET" >&2; MISSING=1; }
    check_artifact "$ACCEPTANCE"                   "w10-judge-and-acceptance"         "acceptance prover"   || MISSING=1
  fi
  printf '\n'
  if [ "$MISSING" -ne 0 ]; then
    die "one or more prerequisites are missing (listed above). A dry run that found a
   hole exits non-zero on purpose: this is the check, not a preview." 1
  fi
  ok "every prerequisite is present — a real run would proceed"
  exit 0
fi

# ══════════════════════════════════════════════════════════════════════════════════════
# STAGE 1 — STATE BACKEND
# ══════════════════════════════════════════════════════════════════════════════════════
stage 1 "state backend"
bash "$SCRIPT_DIR/bootstrap_state.sh" --bucket "$STATE_BUCKET" --region "$REGION" --profile "$PROFILE" \
  || die "bootstrap_state.sh refused or failed. Its message above says which.
   Nothing has been created by this run beyond what it reported." 1
ok "s3://$STATE_BUCKET ready (versioned, private, encrypted, tagged, native locking)"

# ══════════════════════════════════════════════════════════════════════════════════════
# STAGE 2 — THE SECRET, INTO SSM, NEVER INTO TERRAFORM
# ══════════════════════════════════════════════════════════════════════════════════════
stage 2 "secret"
if [ "$PHASE1" -eq 1 ]; then
  skip "phase 1 has no Lambda, so nothing reads the DSN"
else
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
  "$PY" - "$SSM_JSON" <<'PY' || die "could not build the SSM payload." 1
import json, os, sys, urllib.parse

out = sys.argv[1]
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
    # The database is forced to mainline_demo: the admin DSN usually points at defaultdb,
    # and a Lambda connected to the wrong database fails in a way that reads like a
    # privilege error. The query string is kept verbatim because a Cloud Basic DSN's
    # sslmode and options are load-bearing.
    dsn = urllib.parse.urlunsplit((u.scheme, f"{userinfo}@{host}{port}", "/mainline_demo", u.query, ""))
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
fi

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
   mainline_demo from empty. Nothing was changed." 1 ;;
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
stage 4 "lambda package"
LAMBDA_ZIP="${MAINLINE_LAMBDA_ZIP:-$ROOT/out/lambda/mainline-demo-api-$ARCH.zip}"
if [ "$PHASE1" -eq 1 ]; then
  skip "--phase1 creates no Lambda"
elif [ "$SKIP_BUILD" -eq 1 ]; then
  [ -f "$LAMBDA_ZIP" ] || die "--skip-build was passed but $LAMBDA_ZIP does not exist." 1
  skip "--skip-build, reusing $LAMBDA_ZIP"
else
  [ -n "$BUILD_LAMBDA" ] || die "scripts/deploy/build_lambda.sh does not exist. It is produced by
   worker w6-tf-api and builds the psycopg-bearing deployment zip. Until it lands, run
   with --phase1, which needs no Lambda at all and still produces a working demo URL." 1
  case "$BUILD_LAMBDA" in
    *.ps1) pwsh -NoProfile -File "$BUILD_LAMBDA" -Arch "$ARCH" -Out "$LAMBDA_ZIP" || die "build_lambda.ps1 failed." 1 ;;
    *)     bash "$BUILD_LAMBDA" --arch "$ARCH" --out "$LAMBDA_ZIP" || die "build_lambda.sh failed." 1 ;;
  esac
  [ -f "$LAMBDA_ZIP" ] || die "build_lambda finished but $LAMBDA_ZIP is not there.
   Set MAINLINE_LAMBDA_ZIP if it writes somewhere else." 1
  ok "$LAMBDA_ZIP ($(wc -c < "$LAMBDA_ZIP" | tr -d ' ') bytes)"
fi

# ══════════════════════════════════════════════════════════════════════════════════════
# STAGE 5 — THE SITE PAYLOAD: CONSOLE BUILD, THEN THE EVIDENCE BUNDLE
# ══════════════════════════════════════════════════════════════════════════════════════
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
      || die "the console build failed. If w8-console-composition documents a different
   command, export MAINLINE_CONSOLE_BUILD_CMD and re-run." 1
  fi
  [ -f "$CONSOLE_DIR/dist/index.html" ] || die "the build produced no dist/index.html." 1
  ok "console built: $(find "$CONSOLE_DIR/dist" -type f | wc -l | tr -d ' ') files"
fi

if [ -f "$CAPTURE_BUNDLE" ]; then
  "$PY" "$CAPTURE_BUNDLE" --out "$DIST_BUNDLE" \
    || die "capture_demo_bundle.py failed. The bundle is the Phase-1 demo and the console's
   REPLAY source; publishing without it would serve a console with nothing to show." 1
  ok "EvidenceBundle captured into $DIST_BUNDLE"
else
  die "scripts/deploy/capture_demo_bundle.py does not exist. It is produced by worker
   w9-evidence-bundle and captures the cryptographically verified bundle from the Cloud
   cluster. Without it the console has no REPLAY source. There is no way to fake this
   file and none is attempted." 1
fi

# ══════════════════════════════════════════════════════════════════════════════════════
# STAGE 6 — INFRASTRUCTURE
# ══════════════════════════════════════════════════════════════════════════════════════
stage 6 "infrastructure"
cd "$TF_DIR"
terraform init -input=false -reconfigure \
  -backend-config="bucket=$STATE_BUCKET" \
  -backend-config="region=$REGION" \
  || die "terraform init failed. If it complains about a state lock, see
   docs/deploy/RUNBOOK.md § 'If a run says the state is locked'." 1

TF_VARS=(-var "aws_region=$REGION" -var "dsn_parameter_name=$DSN_PARAM" -var "name_prefix=$NAME_PREFIX")
if [ "$PHASE1" -eq 1 ]; then
  TF_VARS+=(-var "enable_api=false")
else
  TF_VARS+=(-var "enable_api=true" -var "lambda_package_path=$LAMBDA_ZIP" -var "lambda_architecture=$ARCH")
fi

terraform apply -input=false $AUTO_APPROVE "${TF_VARS[@]}" \
  || die "terraform apply failed. Nothing else in this script has run; the state file
   records exactly what did get created, and 'scripts/deploy/teardown.sh --yes' removes it.

   IF THE ERROR MENTIONS CloudFront AND 'Your account must be verified':
     that is an AWS account-level hold on creating CloudFront distributions, not a bug in
     this repository. It was reproduced on 2026-08-10 with a bare 'aws cloudfront
     create-distribution' and no Terraform involved, from an identity holding
     AdministratorAccess. Only AWS Support can lift it — open a case under
     Service: CloudFront, Category: account verification, and paste the RequestID.
     docs/deploy/RUNBOOK.md carries the transcript and the fallback options." 1

SUMMARY="$(terraform output -json deploy_summary)"
read_summary() { printf '%s' "$SUMMARY" | "$PY" -c "import json,sys;print(json.load(sys.stdin).get(sys.argv[1]) or '')" "$1"; }
DEMO_URL="$(read_summary demo_url)"
DIST_ID="$(read_summary distribution_id)"
SITE_BUCKET="$(read_summary site_bucket)"
FN_NAME="$(read_summary api_function_name)"
[ -n "$DEMO_URL" ] || die "terraform applied but produced no demo_url output." 1
ok "distribution $DIST_ID → $DEMO_URL"
ok "site bucket  $SITE_BUCKET"
[ -n "$FN_NAME" ] && ok "lambda       $FN_NAME"

# ══════════════════════════════════════════════════════════════════════════════════════
# STAGE 7 — PUBLISH
# ══════════════════════════════════════════════════════════════════════════════════════
#
# Content types are set EXPLICITLY and not left to `aws s3 sync`'s guess, because that
# guess comes from Python's `mimetypes`, which on Windows reads the registry. Measured on
# this machine with the repository interpreter:
#
#     .js    → application/javascript      (fine)
#     .mjs   → text/plain                  ← a module served as text/plain does not load
#     .map   → text/plain                  (harmless)
#     .woff2 → None                        ← falls back to binary/octet-stream
#
# One wrong Content-Type on the entry chunk is a blank page with a console error, on the
# one URL the whole submission depends on. So each family is uploaded with its type named.
stage 7 "publish"
S3X=(aws --profile "$PROFILE" --region "$REGION" --no-cli-pager)

# Hashed, immutable assets first — everything except the entry document.
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
ok "assets uploaded with explicit content types, immutable for a year"

# The entry document: never cached, because it is the only file whose name does not change
# when its contents do.
"${S3X[@]}" s3 cp "$CONSOLE_DIR/dist/index.html" "s3://$SITE_BUCKET/index.html" \
  --content-type "text/html; charset=utf-8" \
  --cache-control "no-cache, no-store, must-revalidate" >/dev/null \
  || die "s3 cp of index.html failed." 1
ok "index.html uploaded, no-cache"

if [ -d "$DIST_BUNDLE" ]; then
  "${S3X[@]}" s3 sync "$DIST_BUNDLE/" "s3://$SITE_BUCKET/evidence/" --delete \
    --content-type "application/json; charset=utf-8" \
    --cache-control "no-cache, must-revalidate" >/dev/null \
    || die "s3 sync of the EvidenceBundle failed." 1
  ok "EvidenceBundle published under /evidence/"
fi

"${S3X[@]}" cloudfront create-invalidation --distribution-id "$DIST_ID" \
  --paths "/index.html" "/" --output text >/dev/null \
  || die "the CloudFront invalidation failed. The objects are uploaded; judges would see
   the previous index.html until the cache expires. Re-run:
     aws cloudfront create-invalidation --distribution-id $DIST_ID --paths '/index.html' '/'" 1
ok "invalidated /index.html and /"

# A live HTTPS check of our own, in BOTH phases, before anything is printed. A new
# distribution can take a few minutes to propagate; 20 attempts at 15 s is five minutes.
info "waiting for the distribution to answer over HTTPS…"
CODE=""
for i in $(seq 1 20); do
  CODE="$(curl -s -o /dev/null -w '%{http_code}' --max-time 20 "$DEMO_URL/" || echo 000)"
  [ "$CODE" = "200" ] && break
  sleep 15
done
[ "$CODE" = "200" ] || die "$DEMO_URL/ answered HTTP $CODE after five minutes of trying.
   The objects are uploaded and the distribution exists — check the OAC and the bucket
   policy in infra/modules/demo-site. Nothing is printed as a working URL until it is." 1
ok "GET $DEMO_URL/ → 200"

if [ "$PHASE1" -eq 1 ]; then
  printf '\n%s--phase1: stopping after stage 7, as designed.%s\n' "$DIM" "$RESET"
  printf '   No Lambda exists, so there is no live gate to prove and stage 8 is not run.\n'
  printf '   The console serves the verified EvidenceBundle with a REPLAY badge.\n'
fi

# ══════════════════════════════════════════════════════════════════════════════════════
# STAGE 8 — PROOF
# ══════════════════════════════════════════════════════════════════════════════════════
if [ "$PHASE1" -eq 0 ]; then
  stage 8 "proof"
  [ -f "$ACCEPTANCE" ] || die "scripts/deploy/demo_acceptance.py does not exist. It is produced by
   worker w10-judge-and-acceptance and is the only thing that proves the live gate
   refuses and then admits over HTTPS. A phase-2 deploy that cannot prove itself is a
   failed deploy, so this is fatal rather than a warning. Use --phase1 to ship the URL
   without the live path." 1
  "$PY" "$ACCEPTANCE" --url "$DEMO_URL" \
    || die "the acceptance prover exited non-zero against $DEMO_URL.
   THE DEPLOY IS FAILED. The live gate did not refuse and then admit over HTTPS, which is
   the product's entire claim. Do not submit this URL. Read the prover's output above,
   then 'aws logs tail /aws/lambda/${FN_NAME:-<function>} --since 10m'." 1
  ok "the live gate refused, refused under attack, and then admitted — over HTTPS"
fi

# ══════════════════════════════════════════════════════════════════════════════════════
# STAGE 9 — HAND-OFF
# ══════════════════════════════════════════════════════════════════════════════════════
stage 9 "hand-off"
cat <<EOF

  ${BOLD}DEMO URL${RESET}   $DEMO_URL
  phase      $([ "$PHASE1" -eq 1 ] && echo "1 — REPLAY, verified EvidenceBundle, no backend" || echo "2 — LIVE, CockroachDB Cloud Basic in Singapore")
  region     $REGION (AWS)   ·   aws-ap-southeast-1 (CockroachDB Cloud)
  account    $ACCOUNT
  bucket     s3://$SITE_BUCKET
  cloudfront $DIST_ID
$([ -n "$FN_NAME" ] && printf '  lambda     %s\n' "$FN_NAME")

  ${BOLD}JUDGE ACCESS${RESET} — free and unrestricted, no sign-up, no key
  · The URL above needs no credential. Open it.
  · Read-only SQL, if a judge wants to check the database themselves:
      user      mainline_judge
      database  mainline_demo   on cluster mainline-dev (aws-ap-southeast-1)
      scope     SELECT on the fourteen mainline_audit views, and nothing else
      password  minted by 'scripts/deploy/cloud_roles.py --rotate', printed once, and
                deliberately not stored by this script or anywhere in the repository.
                Paste it into the submission form's private notes field.
  · The judge pack, with the questions and the fallbacks:
      verticals/mainline/demo/judge/PACK.md
  · What is broken, published on the same site as the claims:
      docs/HONESTY.md

  Teardown, when judging is over:
      scripts/deploy/teardown.sh --yes

EOF
ok "done"
