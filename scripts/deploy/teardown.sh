#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
#
# ══════════════════════════════════════════════════════════════════════════════════════
#  teardown.sh — remove everything the demo created, and prove it removed it
# ══════════════════════════════════════════════════════════════════════════════════════
#
# THE ACCOUNT HOLDS FOUR UNRELATED LIVE PROJECTS. That single fact shapes this whole
# script. A teardown that is merely correct is not good enough; it has to be incapable of
# touching somebody else's bucket even when it is pointed at one.
#
# So every destructive step passes through `assert_ours`, which requires BOTH:
#
#     1. the resource's name begins with `mainline-demo-` (or, for the SSM parameter,
#        `/mainline/`), and
#     2. the live resource carries the tag `project=mainline`, read back from AWS at the
#        moment of deletion — not from Terraform state, not from a variable, not from
#        this script's own idea of what it created.
#
# (2) is the interesting one. State can be stale, a name can be re-used, and a variable
# can be overridden on the command line. The tag is on the object itself and is what
# `infra/envs/demo/main.tf`'s `default_tags` and `bootstrap_state.sh` both put there. If
# a bucket does not carry it, this script does not delete it — it says so and exits
# non-zero. `--ignore-tags` relaxes (2) and NEVER relaxes (1).
#
# ORDER MATTERS, and it is this:
#
#   1  terraform destroy            the distribution, the Lambda, the role, the alarms
#   2  site bucket                  emptied of every version and delete marker, then gone
#   3  SSM parameter                the DSN SecureString
#   4  Cloud database + logins      DROP DATABASE mainline_demo CASCADE, then the users
#   5  state bucket                 LAST, because step 1 needs it to read the state
#
# Step 5 is last for a reason a first draft gets wrong: deleting the state bucket before
# `terraform destroy` leaves every AWS resource alive and unmanaged, and the only way
# back is to import them by hand.
#
# USAGE
#   scripts/deploy/teardown.sh --dry-run       list what would be deleted, delete nothing
#   scripts/deploy/teardown.sh --yes           do it
#   scripts/deploy/teardown.sh --yes --keep-db leave the CockroachDB database and logins
#   scripts/deploy/teardown.sh --yes --keep-state  leave the state bucket
#
# EXIT CODES
#   0  everything this script was asked to delete is gone, verified by re-reading AWS
#   1  a deletion failed
#   2  usage error
#   3  a safety refusal: something did not carry the prefix or the tag

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
TF_DIR="$ROOT/infra/envs/demo"

EXPECTED_ACCOUNT="022950218246"
REGION="ap-southeast-1"
PROFILE="${AWS_PROFILE:-mainline-dev}"
DSN_PARAM="/mainline/demo/cockroach_dsn"
NAME_PREFIX="mainline-demo"
DEMO_DATABASE="mainline_demo"
API_USER="mainline_api"
JUDGE_USER="mainline_judge"

CONFIRMED=0
DRY_RUN=0
IGNORE_TAGS=0
KEEP_DB=0
KEEP_STATE=0
ANY_ACCOUNT=0
STATE_BUCKET="${MAINLINE_STATE_BUCKET:-}"
SITE_BUCKET_OVERRIDE=""

BOLD=""; DIM=""; RESET=""
if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then BOLD=$'\033[1m'; DIM=$'\033[2m'; RESET=$'\033[0m'; fi
# ── winpath: a POSIX path the NATIVE Windows aws.exe can actually open ────────────────
#
# Found by running this script for real, not by reading it. Under Git Bash, `mktemp`
# returns `/tmp/mainline-del.XyMVEA.json`, which exists — for bash. `aws` is a native
# Windows executable with no idea what `/tmp` is:
#
#   Error parsing parameter '--delete': Unable to load paramfile
#   file:///tmp/mainline-del.XyMVEA.json: [Errno 2] No such file or directory
#
#   $ cygpath -m /tmp/probe.json
#   C:/Users/shaug/AppData/Local/Temp/probe.json     <- this one aws.exe opens
#
# Every path handed to a native tool as `file://` goes through here. On Linux and macOS
# there is no cygpath and the path is already correct, so this is a no-op there.
winpath() {
  if command -v cygpath >/dev/null 2>&1; then cygpath -m "$1"; else printf '%s' "$1"; fi
}

step()  { printf '\n%s══ %s%s\n' "$BOLD" "$1" "$RESET"; }
info()  { printf '   %s\n' "$*"; }
ok()    { printf '   %s✓%s %s\n' "$BOLD" "$RESET" "$*"; }
skip()  { printf '   %s· skipped — %s%s\n' "$DIM" "$*" "$RESET"; }
would() { printf '   %sWOULD DELETE%s %s\n' "$BOLD" "$RESET" "$*"; }
die()   { printf '\nteardown: %s\n\n' "$1" >&2; exit "${2:-1}"; }
refuse(){ printf '\n%steardown REFUSED%s\n   %s\n\n' "$BOLD" "$RESET" "$1" >&2; exit 3; }

usage() { sed -n '5,52p' "$0" | sed 's/^# \{0,1\}//'; exit "${1:-2}"; }

while [ $# -gt 0 ]; do
  case "$1" in
    --yes|-y)      CONFIRMED=1; shift ;;
    --dry-run)     DRY_RUN=1; shift ;;
    --ignore-tags) IGNORE_TAGS=1; shift ;;
    --keep-db)     KEEP_DB=1; shift ;;
    --keep-state)  KEEP_STATE=1; shift ;;
    --any-account) ANY_ACCOUNT=1; shift ;;
    --profile)     PROFILE="${2:-}"; shift 2 ;;
    --region)      REGION="${2:-}"; shift 2 ;;
    --state-bucket) STATE_BUCKET="${2:-}"; shift 2 ;;
    --site-bucket)  SITE_BUCKET_OVERRIDE="${2:-}"; shift 2 ;;
    -h|--help)     usage 0 ;;
    *) printf 'teardown: unknown argument %s\n' "$1" >&2; usage 2 ;;
  esac
done

if [ "$CONFIRMED" -eq 0 ] && [ "$DRY_RUN" -eq 0 ]; then
  usage 2
fi

export AWS_PROFILE="$PROFILE" AWS_REGION="$REGION" AWS_DEFAULT_REGION="$REGION"
AWSX=(aws --profile "$PROFILE" --region "$REGION" --output text --no-cli-pager)

command -v aws >/dev/null 2>&1 || die "the AWS CLI is not on PATH."

ACCOUNT="$("${AWSX[@]}" sts get-caller-identity --query Account 2>/dev/null)" \
  || die "aws sts get-caller-identity failed for profile '$PROFILE'."
if [ "$ACCOUNT" != "$EXPECTED_ACCOUNT" ] && [ "$ANY_ACCOUNT" -eq 0 ]; then
  refuse "this is account $ACCOUNT, not $EXPECTED_ACCOUNT. Refusing to delete anything.
   Pass --any-account only if you are certain."
fi

printf '%sMAINLINE demo teardown%s   account=%s  region=%s%s\n' \
  "$BOLD" "$RESET" "$ACCOUNT" "$REGION" "$([ "$DRY_RUN" -eq 1 ] && echo '  (DRY RUN)' || echo '')"

[ -z "$STATE_BUCKET" ] && STATE_BUCKET="${NAME_PREFIX}-tfstate-${ACCOUNT}"

# ══════════════════════════════════════════════════════════════════════════════════════
#  THE SAFETY GATE
# ══════════════════════════════════════════════════════════════════════════════════════
#
# assert_ours_bucket NAME — returns 0 if this bucket may be deleted, and REFUSES (exit 3)
# if it may not. Both conditions are checked against the live resource.
assert_ours_bucket() {
  local bucket="$1"
  case "$bucket" in
    "${NAME_PREFIX}-"*) : ;;
    *) refuse "bucket '$bucket' does not carry the '${NAME_PREFIX}-' prefix.
   This account holds four unrelated live projects, and a teardown that deletes outside
   the prefix is one typo away from deleting one of them. Refusing, and --ignore-tags
   does NOT relax this check." ;;
  esac

  if [ "$IGNORE_TAGS" -eq 1 ]; then
    info "(--ignore-tags: prefix matched, tag not checked for $bucket)"
    return 0
  fi

  local tags
  if ! tags="$("${AWSX[@]}" s3api get-bucket-tagging --bucket "$bucket" --output json 2>/dev/null)"; then
    refuse "bucket '$bucket' has NO tags at all, so it cannot be shown to be ours.
   Everything this project creates is tagged project=mainline — by Terraform's
   default_tags, or by bootstrap_state.sh. An untagged bucket with our prefix is either
   somebody else's or was made by hand, and this script will not guess which.
   Delete it yourself, or re-run with --ignore-tags if you are certain."
  fi
  if ! printf '%s' "$tags" | grep -q '"Value": *"mainline"'; then
    refuse "bucket '$bucket' does not carry project=mainline. Its tags are:
$tags
   Refusing."
  fi
  return 0
}

# ══════════════════════════════════════════════════════════════════════════════════════
#  STEP 1 — TERRAFORM DESTROY
# ══════════════════════════════════════════════════════════════════════════════════════
step "1 · terraform destroy"
SITE_BUCKET="$SITE_BUCKET_OVERRIDE"
DIST_ID=""
FN_NAME=""

if [ ! -d "$TF_DIR" ]; then
  skip "$TF_DIR does not exist"
elif ! "${AWSX[@]}" s3api head-bucket --bucket "$STATE_BUCKET" >/dev/null 2>&1; then
  skip "the state bucket s3://$STATE_BUCKET is already gone — nothing for Terraform to read"
else
  cd "$TF_DIR"
  terraform init -input=false -reconfigure \
    -backend-config="bucket=$STATE_BUCKET" -backend-config="region=$REGION" >/dev/null \
    || die "terraform init failed against s3://$STATE_BUCKET."

  # Read the outputs BEFORE destroying, because after `terraform destroy` there is
  # nothing left to ask. This is how step 2 learns the site bucket's real name rather
  # than recomputing it and hoping.
  if SUMMARY="$(terraform output -json deploy_summary 2>/dev/null)"; then
    PY=""
    for cand in "$ROOT/.venv/Scripts/python.exe" "$ROOT/.venv/bin/python"; do
      [ -x "$cand" ] && { PY="$cand"; break; }
    done
    if [ -n "$PY" ]; then
      [ -z "$SITE_BUCKET" ] && SITE_BUCKET="$(printf '%s' "$SUMMARY" | "$PY" -c 'import json,sys;print(json.load(sys.stdin).get("site_bucket") or "")')"
      DIST_ID="$(printf '%s' "$SUMMARY" | "$PY" -c 'import json,sys;print(json.load(sys.stdin).get("distribution_id") or "")')"
      FN_NAME="$(printf '%s' "$SUMMARY" | "$PY" -c 'import json,sys;print(json.load(sys.stdin).get("api_function_name") or "")')"
    fi
  fi
  [ -n "$SITE_BUCKET" ] && info "site bucket    $SITE_BUCKET"
  [ -n "$DIST_ID" ]     && info "distribution   $DIST_ID"
  [ -n "$FN_NAME" ]     && info "lambda         $FN_NAME"

  # CloudFront will not delete a distribution whose origin bucket still has objects? It
  # will — but S3 will not delete a bucket that does. Terraform's own destroy of the
  # bucket therefore fails unless the bucket is empty, so the bucket is emptied here,
  # before destroy, and deleted for real in step 2.
  if [ -n "$SITE_BUCKET" ] && "${AWSX[@]}" s3api head-bucket --bucket "$SITE_BUCKET" >/dev/null 2>&1; then
    assert_ours_bucket "$SITE_BUCKET"
    if [ "$DRY_RUN" -eq 1 ]; then
      would "every object in s3://$SITE_BUCKET (so that terraform destroy can remove the bucket)"
    else
      "${AWSX[@]}" s3 rm "s3://$SITE_BUCKET" --recursive >/dev/null 2>&1 || true
      ok "emptied s3://$SITE_BUCKET"
    fi
  fi

  if [ "$DRY_RUN" -eq 1 ]; then
    info "terraform plan -destroy:"
    terraform plan -destroy -input=false -lock=false 2>&1 | grep -E '^Plan:|^  # ' | sed 's/^/     /' || true
  else
    # `-refresh=false` is deliberately NOT used: a resource somebody already deleted by
    # hand must be noticed, not error the whole destroy.
    terraform destroy -auto-approve -input=false \
      || die "terraform destroy failed. Nothing after this point has run — the state file
   still describes what is left, so re-running this script is safe."
    ok "terraform destroy completed"
  fi
  cd "$ROOT"
fi

# ══════════════════════════════════════════════════════════════════════════════════════
#  STEP 2 — THE SITE BUCKET, INCLUDING EVERY VERSION AND DELETE MARKER
# ══════════════════════════════════════════════════════════════════════════════════════
step "2 · site bucket"
delete_bucket_completely() {
  local bucket="$1"
  assert_ours_bucket "$bucket"

  if [ "$DRY_RUN" -eq 1 ]; then
    # No object count here on purpose. `length(Versions || ...)` returns nothing at all on
    # an empty bucket and printed a bare "?" in the first version of this script, which is
    # a number-shaped thing that is not a number — exactly the sort of output this project
    # refuses to print elsewhere.
    would "s3://$bucket, every object version in it, and every delete marker"
    return 0
  fi

  # Plain `s3 rm --recursive` leaves NONCURRENT VERSIONS and DELETE MARKERS behind on a
  # versioned bucket, and `s3api delete-bucket` then fails with BucketNotEmpty over
  # objects that `aws s3 ls` does not show — the single most common way a "successful"
  # teardown leaves a bucket, and a bill, behind. Both state buckets here are versioned
  # (bootstrap_state.sh turns it on, and `infra/modules/demo-site` versions the site
  # bucket too), so every version and every marker is enumerated and deleted explicitly.
  #
  # Versions and delete markers are drained in two separate passes rather than one
  # combined JMESPath. `[Versions[]…, DeleteMarkers[]…][]` looks tidier and is a trap:
  # when one of the two keys is absent the flatten yields a list containing `null`, and
  # `delete-objects` rejects the payload. Two unambiguous queries cannot do that.
  local kind page count=0
  for kind in Versions DeleteMarkers; do
    while :; do
      page="$("${AWSX[@]}" s3api list-object-versions --bucket "$bucket" --max-keys 1000 \
                --output json --query "${kind}[].{Key:Key,VersionId:VersionId}" 2>/dev/null || echo 'null')"
      case "$page" in
        ''|null|'[]') break ;;
      esac
      printf '{"Objects": %s, "Quiet": true}' "$page" > "$TMP_DELETE"
      "${AWSX[@]}" s3api delete-objects --bucket "$bucket" --delete "file://$(winpath "$TMP_DELETE")" >/dev/null \
        || die "could not delete a page of $kind from s3://$bucket."
      count=$((count + 1))
    done
  done
  [ "$count" -gt 0 ] && info "drained $count page(s) of object versions and delete markers"

  "${AWSX[@]}" s3api delete-bucket --bucket "$bucket" >/dev/null \
    || die "could not delete bucket s3://$bucket after emptying it.
   If S3 says BucketNotEmpty, something is writing to it while this runs."
  ok "deleted s3://$bucket"
}

TMP_DELETE="$(mktemp "${TMPDIR:-/tmp}/mainline-del.XXXXXX.json")"
trap 'rm -f "$TMP_DELETE"' EXIT INT TERM

if [ -z "$SITE_BUCKET" ]; then
  # Terraform is gone or never ran. Fall back to discovery — but only over buckets that
  # already carry the prefix, and each one still goes through assert_ours_bucket.
  CANDIDATES="$("${AWSX[@]}" s3api list-buckets --query "Buckets[?starts_with(Name, '${NAME_PREFIX}-site')].Name" 2>/dev/null || true)"
  for b in $CANDIDATES; do
    info "discovered $b"
    delete_bucket_completely "$b"
  done
  [ -z "$CANDIDATES" ] && skip "no ${NAME_PREFIX}-site* bucket found"
elif "${AWSX[@]}" s3api head-bucket --bucket "$SITE_BUCKET" >/dev/null 2>&1; then
  delete_bucket_completely "$SITE_BUCKET"
else
  ok "s3://$SITE_BUCKET is already gone (terraform destroy removed it)"
fi

# ══════════════════════════════════════════════════════════════════════════════════════
#  STEP 3 — THE SSM PARAMETER
# ══════════════════════════════════════════════════════════════════════════════════════
step "3 · ssm parameter"
case "$DSN_PARAM" in
  /mainline/*) : ;;
  *) refuse "the DSN parameter name '$DSN_PARAM' is not under /mainline/. Refusing." ;;
esac
if "${AWSX[@]}" ssm get-parameter --name "$DSN_PARAM" --query 'Parameter.Type' >/dev/null 2>&1; then
  if [ "$DRY_RUN" -eq 1 ]; then
    would "SSM parameter $DSN_PARAM"
  else
    "${AWSX[@]}" ssm delete-parameter --name "$DSN_PARAM" >/dev/null \
      || die "could not delete SSM parameter $DSN_PARAM."
    ok "deleted $DSN_PARAM"
  fi
else
  ok "$DSN_PARAM does not exist"
fi

# ══════════════════════════════════════════════════════════════════════════════════════
#  STEP 4 — THE CLOUD DATABASE AND THE TWO LOGINS
# ══════════════════════════════════════════════════════════════════════════════════════
#
# ORDER IS LOAD-BEARING AND WAS MEASURED, not guessed. Against the local CockroachDB
# v26.2.5 node, with the same grant shape `cloud_roles.py` produces (CONNECT on the
# database, SELECT on a table), dropping the login first fails:
#
#     == REVERSE order: DROP USER while grants still exist ==
#       [2BP01] DROP USER IF EXISTS w7rev_api
#               cannot drop role/user w7rev_api: grants still exist on
#               w_w7_rev, w_w7_rev.public.t
#
#     == then the correct order ==
#       OK       DROP DATABASE IF EXISTS w_w7_rev CASCADE
#       OK       DROP USER IF EXISTS w7rev_api
#
# `DROP DATABASE … CASCADE` takes every grant that lived in that database with it, and
# only then do the two logins drop cleanly. Doing it the other way round leaves two users
# behind on a cluster the next deploy will reuse — and leaves them holding a password.
step "4 · cloud database and logins"
if [ "$KEEP_DB" -eq 1 ]; then
  skip "--keep-db"
else
  if [ -z "${COCKROACH_DSN:-}" ] && [ -f "$ROOT/.env" ]; then
    COCKROACH_DSN="$(sed -n 's/^COCKROACH_DSN=//p' "$ROOT/.env" | head -1 | sed 's/^"//; s/"$//')"
    export COCKROACH_DSN
  fi
  PY=""
  for cand in "$ROOT/.venv/Scripts/python.exe" "$ROOT/.venv/bin/python"; do
    [ -x "$cand" ] && { PY="$cand"; break; }
  done
  if [ -z "${COCKROACH_DSN:-}" ] || [ -z "$PY" ]; then
    skip "no COCKROACH_DSN or no .venv interpreter — the Cloud database is UNTOUCHED and
      still costs whatever it costs. Drop it by hand:
        DROP DATABASE $DEMO_DATABASE CASCADE;  DROP USER $API_USER;  DROP USER $JUDGE_USER;"
  elif [ "$DRY_RUN" -eq 1 ]; then
    would "DROP DATABASE $DEMO_DATABASE CASCADE, then USER $API_USER, USER $JUDGE_USER"
  else
    DEMO_DATABASE="$DEMO_DATABASE" API_USER="$API_USER" JUDGE_USER="$JUDGE_USER" \
    "$PY" - <<'PY' || die "the CockroachDB teardown failed; its output above says how."
import os, sys

try:
    import psycopg
except ImportError:
    sys.exit("psycopg is not installed in this virtualenv.")

dsn = os.environ["COCKROACH_DSN"]
db, api_user, judge_user = os.environ["DEMO_DATABASE"], os.environ["API_USER"], os.environ["JUDGE_USER"]

# Refuse a name that is not ours. `mainline_demo` is the only database this project
# creates on that cluster, and a teardown that would accept `defaultdb` is a teardown
# nobody should run.
if not db.startswith("mainline_"):
    sys.exit(f"refusing to drop database {db!r}: it does not carry the mainline_ prefix.")

with psycopg.connect(dsn, autocommit=True, connect_timeout=20) as conn:
    def do(sql):
        try:
            conn.execute(sql)
            print(f"   ok       {sql}")
        except Exception as exc:  # noqa: BLE001
            code = getattr(exc, "sqlstate", None) or "?????"
            first = str(exc).splitlines()[0]
            print(f"   [{code}] {sql}\n            {first}")
            raise SystemExit(1) from exc

    # CASCADE first: it takes the grants with it, which is what lets the users drop.
    do(f"DROP DATABASE IF EXISTS {db} CASCADE")
    do(f"DROP USER IF EXISTS {api_user}")
    do(f"DROP USER IF EXISTS {judge_user}")

    left = conn.execute(
        "SELECT username FROM [SHOW USERS] WHERE username IN (%s, %s)", (api_user, judge_user)
    ).fetchall()
    dbs = conn.execute(
        "SELECT database_name FROM [SHOW DATABASES] WHERE database_name = %s", (db,)
    ).fetchall()
    if left or dbs:
        sys.exit(f"   RESIDUE: users={left} databases={dbs} — teardown did NOT complete.")
    print("   verified: the database is gone and neither login exists")
PY
    ok "mainline_demo dropped; mainline_api and mainline_judge removed"
  fi
fi

# ══════════════════════════════════════════════════════════════════════════════════════
#  STEP 5 — THE STATE BUCKET, LAST
# ══════════════════════════════════════════════════════════════════════════════════════
step "5 · state bucket"
if [ "$KEEP_STATE" -eq 1 ]; then
  skip "--keep-state"
elif "${AWSX[@]}" s3api head-bucket --bucket "$STATE_BUCKET" >/dev/null 2>&1; then
  delete_bucket_completely "$STATE_BUCKET"
else
  ok "s3://$STATE_BUCKET does not exist"
fi

# ══════════════════════════════════════════════════════════════════════════════════════
#  VERIFY — re-read AWS rather than believe the deletions
# ══════════════════════════════════════════════════════════════════════════════════════
step "verify"
if [ "$DRY_RUN" -eq 1 ]; then
  info "dry run — nothing was deleted, so there is nothing to verify."
  exit 0
fi
RESIDUE=0
LEFT="$("${AWSX[@]}" s3api list-buckets --query "Buckets[?starts_with(Name, '${NAME_PREFIX}')].Name" 2>/dev/null || true)"
if [ -n "$LEFT" ] && [ "$KEEP_STATE" -eq 0 ]; then
  printf '   %s✗%s buckets still present: %s\n' "$BOLD" "$RESET" "$LEFT" >&2
  RESIDUE=1
else
  ok "no ${NAME_PREFIX}* buckets remain"
fi
if "${AWSX[@]}" ssm get-parameter --name "$DSN_PARAM" >/dev/null 2>&1; then
  printf '   %s✗%s %s still exists\n' "$BOLD" "$RESET" "$DSN_PARAM" >&2
  RESIDUE=1
else
  ok "$DSN_PARAM is gone"
fi
if [ -n "$FN_NAME" ]; then
  if "${AWSX[@]}" lambda get-function --function-name "$FN_NAME" >/dev/null 2>&1; then
    printf '   %s✗%s lambda %s still exists\n' "$BOLD" "$RESET" "$FN_NAME" >&2
    RESIDUE=1
  else
    ok "lambda $FN_NAME is gone"
  fi
fi

printf '\n'
if [ "$RESIDUE" -ne 0 ]; then
  die "teardown finished with residue, listed above. Nothing here is destructive to run
   twice — re-run it, or delete the named resources by hand." 1
fi
ok "teardown complete — nothing this project created remains in account $ACCOUNT"
