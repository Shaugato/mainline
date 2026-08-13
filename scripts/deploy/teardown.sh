#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: Apache-2.0
#
# BEGIN-USAGE
# ══════════════════════════════════════════════════════════════════════════════════════
#  teardown.sh — remove everything the demo created, and prove it removed it
# ══════════════════════════════════════════════════════════════════════════════════════
#
# THE ACCOUNT HOLDS SEVEN BUCKETS BELONGING TO UNRELATED LIVE PROJECTS. That single fact
# shapes this whole script. A teardown that is merely correct is not good enough; it has
# to be incapable of touching somebody else's bucket even when it is pointed at one.
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
#   0  inventory                   what carries our prefix, and what does not
#   1  terraform destroy           the Lambda, the Function URL, the execution role, the
#                                  log group, the four alarms, the dashboard, and the
#                                  distribution + bucket if they ever existed
#   2  site bucket                 emptied of every version and delete marker, then gone
#   3  SSM parameter               the DSN SecureString
#   4  Cloud database + logins     DROP DATABASE mainline_demo CASCADE, then the users
#   5  state bucket                LAST, because step 1 needs it to read the state
#
# Step 5 is last for a reason a first draft gets wrong: deleting the state bucket before
# `terraform destroy` leaves every AWS resource alive and unmanaged, and the only way
# back is to import them by hand.
#
# ── WHAT "COMPLETE" MEANS HERE ────────────────────────────────────────────────────────
#
# An apply creates SEVEN classes of resource. Deleting them is step 1's job. PROVING they
# are gone is the verify block's, and it re-reads all seven from AWS rather than trusting
# that the deletions returned success:
#
#     s3 buckets        mainline-demo-*                                  account-wide
#     iam role          mainline-demo-api-exec                           account-wide
#     lambda functions  mainline-demo-*                                  $REGION
#     log group         /aws/lambda/mainline-demo-api                    $REGION
#     alarms x4         mainline-demo-api-{errors,throttles,             $REGION
#                                          duration-p99,concurrency}
#     dashboard         mainline-demo-api                                $REGION
#     ssm parameter     /mainline/demo/cockroach_dsn                     $REGION
#
# It used to read three of those seven and then print "nothing this project created
# remains in account <id>". THE ORPHAN COST OF THE OTHER FOUR IS USD 0.00 — `terraform
# destroy` really does delete all seven — so that was never a leak, and must not be sold
# as one. It was a completeness claim with 43 % of its own subject unmeasured, which in a
# repository whose whole argument is that its claims are checkable is the worse of the
# two. The four checks make the sentence true rather than lucky, and they catch the two
# ways it could genuinely be false: a `terraform destroy` that partially failed, and a
# resource created outside Terraform — not hypothetical, since Lambda creates its own log
# group on first invocation if Terraform has not.
#
# UNDER DECISION D1 there is normally no site bucket and no distribution at all — the
# console and the evidence bundle are served out of the Lambda package. Steps 1 and 2
# handle their absence rather than assuming it, because `--enable-cloudfront` deploys
# still create them and a teardown that only works against one shape is a teardown that
# leaves a bill behind after the other.
#
# ── WHICH AWS ACCOUNT (decision D2) ───────────────────────────────────────────────────
#
# No account id is written in this file. The live account is read from
#
#     aws sts get-caller-identity --query Account --output text
#
# and compared against the one you name, either way round:
#
#     --expect-account 123456789012          (wins over the environment)
#     export MAINLINE_AWS_ACCOUNT=123456789012
#
# SUPPLY NEITHER AND THIS SCRIPT DELETES NOTHING (exit 3). `--any-account` is the only
# override. `--dry-run` is exempt from the requirement because it deletes nothing by
# construction; it still refuses if you name an account and the caller is a different one.
#
# USAGE
#   scripts/deploy/teardown.sh --dry-run                     list what would go; delete nothing
#   scripts/deploy/teardown.sh --expect-account <id> --yes   do it
#   scripts/deploy/teardown.sh --expect-account <id> --yes --keep-db     leave the database
#   scripts/deploy/teardown.sh --expect-account <id> --yes --keep-state  leave the state bucket
#
# EXIT CODES
#   0  everything this script was asked to delete is gone, verified by re-reading AWS
#   1  a deletion failed
#   2  usage error
#   3  a safety refusal: something did not carry the prefix, the tag, or the account
# END-USAGE

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
TF_DIR="$ROOT/infra/envs/demo"

REGION="ap-southeast-1"
PROFILE="${AWS_PROFILE:-mainline-dev}"
DSN_PARAM="/mainline/demo/cockroach_dsn"
NAME_PREFIX="mainline-demo"
DEMO_DATABASE="${MAINLINE_DEMO_DATABASE:-mainline_demo}"
API_USER="mainline_api"
JUDGE_USER="mainline_judge"

# D2: no account id is written in this file.
EXPECT_ACCOUNT="${MAINLINE_AWS_ACCOUNT:-}"

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
export PYTHONIOENCODING="utf-8"
export PYTHONUTF8=1

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

# ── the same problem as winpath, pointing the other way ───────────────────────────────
#
# Also found by running this for real. Git Bash rewrites any argument that LOOKS like an
# absolute POSIX path before the native executable ever sees it. Measured on this machine,
# with a native python.exe standing in for the native aws.exe:
#
#   $ python.exe -c 'import sys;[print(repr(a)) for a in sys.argv[1:]]' \
#         /mainline/demo/cockroach_dsn /aws/lambda/mainline-demo mainline-demo
#   'C:/Program Files/Git/mainline/demo/cockroach_dsn'
#   'C:/Program Files/Git/aws/lambda/mainline-demo'
#   'mainline-demo'
#
# `winpath` exists because one argument MUST arrive in Windows form. This exists because
# two others must arrive UNCHANGED: they are not paths at all — one is an SSM parameter
# name, the other a CloudWatch log group name. Both begin with `/`, and that is the whole
# of what the rewriting looks at.
#
# Left alone, one of the two fails loudly and the other fails SILENTLY:
#
#   logs describe-log-groups --log-group-name-prefix /aws/lambda/mainline-demo
#     -> InvalidParameterException: Member must satisfy [\.\-_/#A-Za-z0-9]+
#        (the mangled value contains a colon and a space). Loud: aws_query would die.
#
#   ssm get-parameter --name /mainline/demo/cockroach_dsn
#     -> ParameterNotFound, WHICH IS ALSO THE ANSWER WHEN THE PARAMETER IS SIMPLY GONE.
#
# The second is the dangerous one, and it is dangerous in this script's own idiom: step 3
# tests exactly that call, so it would skip the delete and leave the DSN SecureString in
# place, and the verify block would then print `[ok] /mainline/demo/cockroach_dsn is gone`
# about a secret it never managed to look at. That is a green tick standing on a call that
# never reached AWS — the identical failure `aws_query` was written to make impossible for
# list calls. The defect is latent today only because no /mainline/* parameter exists in
# this account, so both spellings answer ParameterNotFound; it bites the first time there
# is something to delete.
#
# MSYS_NO_PATHCONV=1 turns the rewriting off. It is a Git-for-Windows variable and an
# inert exported string on Linux and macOS. Nothing here wants the conversion: the one
# argument that must be Windows-form goes through `winpath`, which is explicit about it.
export MSYS_NO_PATHCONV=1

step()  { printf '\n%s== %s%s\n' "$BOLD" "$1" "$RESET"; }
info()  { printf '   %s\n' "$*"; }
ok()    { printf '   %s[ok]%s %s\n' "$BOLD" "$RESET" "$*"; }
skip()  { printf '   %s[skipped] %s%s\n' "$DIM" "$*" "$RESET"; }
would() { printf '   %sWOULD DELETE%s %s\n' "$BOLD" "$RESET" "$*"; }
wont()  { printf '   %sWOULD NOT TOUCH%s %s\n' "$DIM" "$RESET" "$*"; }
die()   { printf '\nteardown: %s\n\n' "$1" >&2; exit "${2:-1}"; }
refuse(){ printf '\n%steardown REFUSED%s\n   %s\n\n' "$BOLD" "$RESET" "$1" >&2; exit 3; }

usage() { sed -n '/^# BEGIN-USAGE$/,/^# END-USAGE$/p' "$0" | sed '1d;$d' | sed 's/^# \{0,1\}//'; exit "${1:-2}"; }

# ── aws_query — an EMPTY answer and a FAILED call are not the same thing ──────────────
#
# `x="$(aws … || true)"` conflates them, and in an inventory that conflation is a lie: a
# throttle, an expired token or a missing permission would be reported as "no resources
# found", which is the one wrong answer this script must never give. So every list call
# goes through here, empty is returned as empty, and a non-zero exit is fatal with the
# API's own words attached.
#
# `--output text` renders an empty JMESPath list as the empty string and a null projection
# as the four characters `None`; both mean "nothing", and both are normalised to "".
QUERY_OUT=""
aws_query() {  # label, then the aws sub-command and its arguments
  local label="$1"; shift
  if ! QUERY_OUT="$("${AWSX[@]}" "$@" 2>&1)"; then
    die "$label failed, and this script will not treat an unreadable account as an empty one:
   $QUERY_OUT"
  fi
  [ "$QUERY_OUT" = "None" ] && QUERY_OUT=""
  return 0
}

while [ $# -gt 0 ]; do
  case "$1" in
    --yes|-y)        CONFIRMED=1; shift ;;
    --dry-run)       DRY_RUN=1; shift ;;
    --ignore-tags)   IGNORE_TAGS=1; shift ;;
    --keep-db)       KEEP_DB=1; shift ;;
    --keep-state)    KEEP_STATE=1; shift ;;
    --any-account)   ANY_ACCOUNT=1; shift ;;
    --expect-account) EXPECT_ACCOUNT="${2:-}"; shift 2 ;;
    --profile)       PROFILE="${2:-}"; shift 2 ;;
    --region)        REGION="${2:-}"; shift 2 ;;
    --state-bucket)  STATE_BUCKET="${2:-}"; shift 2 ;;
    --site-bucket)   SITE_BUCKET_OVERRIDE="${2:-}"; shift 2 ;;
    -h|--help)       usage 0 ;;
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

# ── THE ACCOUNT GUARD ─────────────────────────────────────────────────────────────────
if [ "$ANY_ACCOUNT" -eq 1 ]; then
  info "account guard DISABLED by --any-account"
elif [ -n "$EXPECT_ACCOUNT" ] && [ "$ACCOUNT" != "$EXPECT_ACCOUNT" ]; then
  refuse "this is account $ACCOUNT. You said $EXPECT_ACCOUNT. Deleting nothing.
   Fix the profile (--profile <name>) or the expectation (--expect-account <id>)."
elif [ -z "$EXPECT_ACCOUNT" ] && [ "$DRY_RUN" -eq 0 ]; then
  refuse "NOTHING TOLD THIS SCRIPT WHICH AWS ACCOUNT IT MAY DELETE FROM, so it will not
   delete from one. The caller is account $ACCOUNT. Name it:

       scripts/deploy/teardown.sh --expect-account $ACCOUNT --yes
   or
       export MAINLINE_AWS_ACCOUNT=$ACCOUNT

   No account id is hard-coded in this file (decision D2). --any-account is the only
   override. --dry-run needs none of this, because it deletes nothing."
fi

printf '%sMAINLINE demo teardown%s   account=%s  region=%s%s\n' \
  "$BOLD" "$RESET" "$ACCOUNT" "$REGION" "$([ "$DRY_RUN" -eq 1 ] && echo '  (DRY RUN — deletes nothing)' || echo '')"

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
   This account holds seven buckets across unrelated live projects, and a teardown that
   deletes outside the prefix is one typo away from deleting one of them. Refusing, and
   --ignore-tags does NOT relax this check." ;;
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
#  STEP 0 — INVENTORY
# ══════════════════════════════════════════════════════════════════════════════════════
#
# Printed BEFORE anything is deleted, and printed in both directions: what carries our
# prefix, and — by name — what does not and therefore will never be touched. A teardown
# that only lists its own targets tells you nothing about the blast radius; this one shows
# you the whole account and draws the line through it.
step "0 · inventory"
aws_query "s3api list-buckets" s3api list-buckets --query 'Buckets[].Name'
ALL_BUCKETS="$QUERY_OUT"
OURS=""; THEIRS=""
for b in $ALL_BUCKETS; do
  case "$b" in
    "${NAME_PREFIX}-"*) OURS="$OURS $b" ;;
    *) THEIRS="$THEIRS $b" ;;
  esac
done
if [ -n "${OURS// /}" ]; then
  for b in $OURS; do info "ours    s3://$b"; done
else
  ok "no s3 bucket in this account carries the '${NAME_PREFIX}-' prefix"
fi
for b in $THEIRS; do wont "s3://$b  (no '${NAME_PREFIX}-' prefix)"; done

aws_query "lambda list-functions" lambda list-functions --query 'Functions[].FunctionName'
LAMBDAS="$QUERY_OUT"
OUR_LAMBDAS=""
for f in $LAMBDAS; do
  case "$f" in "${NAME_PREFIX}-"*) OUR_LAMBDAS="$OUR_LAMBDAS $f" ;; *) wont "lambda $f  (no '${NAME_PREFIX}-' prefix)" ;; esac
done
if [ -n "${OUR_LAMBDAS// /}" ]; then
  for f in $OUR_LAMBDAS; do info "ours    lambda $f"; done
else
  ok "no lambda function in $REGION carries the '${NAME_PREFIX}-' prefix"
fi

aws_query "ssm describe-parameters" ssm describe-parameters \
  --parameter-filters "Key=Name,Option=BeginsWith,Values=/mainline/" --query 'Parameters[].Name'
OUR_PARAMS="$QUERY_OUT"
if [ -n "$OUR_PARAMS" ]; then
  for p in $OUR_PARAMS; do info "ours    ssm $p"; done
else
  ok "no SSM parameter under /mainline/ exists in $REGION"
fi

# CloudFront is global, so it is listed and matched on ORIGIN rather than on region. Under
# D1 we create none; a distribution belonging to somebody else must be visible here and
# visibly excluded, not silently skipped.
if ! CF="$(aws --profile "$PROFILE" --no-cli-pager --output text cloudfront list-distributions \
        --query 'DistributionList.Items[].[Id,DomainName,Origins.Items[0].DomainName]' 2>&1)"; then
  die "cloudfront list-distributions failed, and this script will not treat an unreadable
   account as an empty one:
   $CF"
fi
[ "$CF" = "None" ] && CF=""
if [ -n "$CF" ]; then
  while IFS=$'\t' read -r cid cdomain corigin; do
    [ -z "${cid:-}" ] && continue
    case "$corigin" in
      "${NAME_PREFIX}-"*) info "ours    cloudfront $cid  $cdomain  origin $corigin" ;;
      *) wont "cloudfront $cid  $cdomain  (origin $corigin — not ours)" ;;
    esac
  done <<EOF
$CF
EOF
else
  ok "no CloudFront distribution is visible to this identity"
fi

# ── the four classes this inventory used to leave out ─────────────────────────────────
#
# An apply creates seven classes; step 0 listed three, so an operator reading a --dry-run
# before typing --yes was shown less than half of what the run would touch.
#
# These four are listed in ONE direction only, unlike the buckets and Lambdas above, and
# the asymmetry is deliberate rather than an omission. This script deletes buckets BY
# DISCOVERY, so for those it has to show you the whole account and draw the line through
# it. It never deletes a role, a log group, an alarm or a dashboard by discovery — step 1
# destroys exactly what Terraform holds in state, and these listings exist to CHECK that.
# There is no blast radius here to draw a line through, so nothing is claimed about one.
#
# SCOPE IS NOT UNIFORM ACROSS THE SEVEN, and averaging over it is precisely how a closing
# sentence ends up broader than its evidence:
#
#   IAM is GLOBAL. Measured on this account: `iam list-roles --query 'length(Roles)'`
#     returns 15 under --region ap-southeast-1 and 15 under --region ap-southeast-2 — the
#     same roles both times. `--region` is accepted and ignored, so this listing is
#     account-wide whatever --region was passed, and it says "account-wide" for that
#     reason and not as a figure of speech.
#
#   Log groups, alarms and dashboards are read through the REGIONAL CloudWatch endpoint,
#     so they are listed for $REGION — which is where the provider in infra/envs/demo
#     creates them and therefore where a survivor would be. Whether the DASHBOARD
#     namespace is itself account-global could not be settled from here: this account
#     holds zero dashboards in ap-southeast-1, ap-southeast-2 and us-east-1, so the
#     question has no observable answer on it today. Nothing depends on which way it
#     falls — a global store would still answer a $REGION call — so this reports what it
#     looked at and claims nothing about regions it did not.
aws_query "iam list-roles" iam list-roles \
  --query "Roles[?starts_with(RoleName, '${NAME_PREFIX}-')].RoleName"
OUR_ROLES="$QUERY_OUT"
if [ -n "$OUR_ROLES" ]; then
  for r in $OUR_ROLES; do info "ours    iam role $r  (account-wide)"; done
else
  ok "no IAM role carries the '${NAME_PREFIX}-' prefix (account-wide)"
fi

aws_query "logs describe-log-groups" logs describe-log-groups \
  --log-group-name-prefix "/aws/lambda/${NAME_PREFIX}" --query 'logGroups[].logGroupName'
OUR_LOG_GROUPS="$QUERY_OUT"
if [ -n "$OUR_LOG_GROUPS" ]; then
  for g in $OUR_LOG_GROUPS; do info "ours    log group $g"; done
else
  ok "no /aws/lambda/${NAME_PREFIX}* log group exists in $REGION"
fi

# Composite alarms are read as well as metric ones. The module creates only metric alarms,
# but "nothing this project created remains" must not quietly narrow to "no metric alarm
# remains" — and a composite alarm is exactly the sort of thing added by hand later.
# describe-alarms always returns BOTH keys (measured against this account, which has
# neither: `{"MetricAlarms": [], "CompositeAlarms": []}`), so this flatten cannot produce
# the list-containing-null that step 2's comment warns about — there is no absent key for
# it to flatten into a null.
aws_query "cloudwatch describe-alarms" cloudwatch describe-alarms \
  --alarm-name-prefix "${NAME_PREFIX}-" \
  --query '[MetricAlarms[].AlarmName, CompositeAlarms[].AlarmName][]'
OUR_ALARMS="$QUERY_OUT"
if [ -n "$OUR_ALARMS" ]; then
  for a in $OUR_ALARMS; do info "ours    alarm $a"; done
else
  ok "no ${NAME_PREFIX}-* CloudWatch alarm exists in $REGION"
fi

aws_query "cloudwatch list-dashboards" cloudwatch list-dashboards \
  --dashboard-name-prefix "${NAME_PREFIX}-" --query 'DashboardEntries[].DashboardName'
OUR_DASHBOARDS="$QUERY_OUT"
if [ -n "$OUR_DASHBOARDS" ]; then
  for d in $OUR_DASHBOARDS; do info "ours    dashboard $d"; done
else
  ok "no ${NAME_PREFIX}-* CloudWatch dashboard exists in $REGION"
fi

# ══════════════════════════════════════════════════════════════════════════════════════
#  STEP 1 — TERRAFORM DESTROY
# ══════════════════════════════════════════════════════════════════════════════════════
step "1 · terraform destroy"
SITE_BUCKET="$SITE_BUCKET_OVERRIDE"
DIST_ID=""
FN_NAME=""

PY=""
for cand in "$ROOT/.venv/Scripts/python.exe" "$ROOT/.venv/bin/python" "$ROOT/.venv/bin/python3"; do
  [ -x "$cand" ] && { PY="$cand"; break; }
done

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
  # than recomputing it and hoping. Under D1 site_bucket and distribution_id are null and
  # api_function_name is the only one that answers; all three are read the same way.
  if SUMMARY="$(terraform output -json deploy_summary 2>/dev/null)" && [ -n "$PY" ]; then
    read_key() { printf '%s' "$SUMMARY" | MAINLINE_KEY="$1" "$PY" -c '
import json, os, sys
print(json.load(sys.stdin).get(os.environ["MAINLINE_KEY"]) or "")'; }
    [ -z "$SITE_BUCKET" ] && SITE_BUCKET="$(read_key site_bucket)"
    DIST_ID="$(read_key distribution_id)"
    FN_NAME="$(read_key api_function_name)"
  fi
  [ -n "$SITE_BUCKET" ] && info "site bucket    $SITE_BUCKET"
  [ -n "$DIST_ID" ]     && info "distribution   $DIST_ID"
  [ -n "$FN_NAME" ]     && info "lambda         $FN_NAME"

  # S3 will not delete a bucket that still has objects, so Terraform's own destroy of the
  # bucket fails unless it is empty. The bucket is therefore emptied here, before destroy,
  # and deleted for real in step 2.
  if [ -n "$SITE_BUCKET" ] && "${AWSX[@]}" s3api head-bucket --bucket "$SITE_BUCKET" >/dev/null 2>&1; then
    assert_ours_bucket "$SITE_BUCKET"
    if [ "$DRY_RUN" -eq 1 ]; then
      would "every object in s3://$SITE_BUCKET (so that terraform destroy can remove the bucket)"
    else
      # Not fatal, and deliberately so: this is a convenience pass so that Terraform's own
      # destroy of the bucket does not fail on BucketNotEmpty. Step 2 deletes the bucket
      # for real, drains every version and every delete marker, and DOES die on failure —
      # so a problem here is caught there rather than swallowed.
      if "${AWSX[@]}" s3 rm "s3://$SITE_BUCKET" --recursive >/dev/null 2>&1; then
        ok "emptied s3://$SITE_BUCKET"
      else
        info "could not empty s3://$SITE_BUCKET here; step 2 drains it properly and will fail loudly"
      fi
    fi
  fi

  if [ "$DRY_RUN" -eq 1 ]; then
    info "terraform plan -destroy:"
    # The pipeline's exit status is the last command's, so a terraform failure would be
    # invisible behind grep. Capture first, check terraform's own status, then filter.
    if DESTROY_PLAN="$(terraform plan -destroy -input=false -lock=false 2>&1)"; then
      printf '%s\n' "$DESTROY_PLAN" | grep -E '^Plan:|^  # ' | sed 's/^/     /' || info "     (the plan named no resources)"
    else
      printf '%s\n' "$DESTROY_PLAN" | sed 's/^/     /' >&2
      die "terraform plan -destroy failed (output above). A dry run that cannot read the
   state must not print a list of what it would delete."
    fi
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
TMP_DELETE="$(mktemp "${TMPDIR:-/tmp}/mainline-del.XXXXXX.json")"
trap 'rm -f "$TMP_DELETE"' EXIT INT TERM

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
  # teardown leaves a bucket, and a bill, behind. Both buckets here are versioned
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

if [ -z "$SITE_BUCKET" ]; then
  # Terraform is gone, never ran, or this is a D1 deploy that created no site at all.
  # Fall back to discovery — but only over buckets that already carry the prefix, and each
  # one still goes through assert_ours_bucket.
  aws_query "s3api list-buckets" s3api list-buckets --query "Buckets[?starts_with(Name, '${NAME_PREFIX}-site')].Name"
  CANDIDATES="$QUERY_OUT"
  for b in $CANDIDATES; do
    info "discovered $b"
    delete_bucket_completely "$b"
  done
  [ -z "$CANDIDATES" ] && ok "no ${NAME_PREFIX}-site* bucket exists (expected under D1: there is no site bucket)"
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
  if [ -z "${COCKROACH_DSN:-}" ] || [ -z "$PY" ]; then
    skip "no COCKROACH_DSN or no .venv interpreter — the Cloud database is UNTOUCHED and
      still costs whatever it costs. Drop it by hand:
        DROP DATABASE $DEMO_DATABASE CASCADE;  DROP USER $API_USER;  DROP USER $JUDGE_USER;"
  elif [ "$DRY_RUN" -eq 1 ]; then
    would "on CockroachDB Cloud: DROP DATABASE $DEMO_DATABASE CASCADE, then USER $API_USER, USER $JUDGE_USER"
    wont "every other database and every other login on that cluster"
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
    ok "$DEMO_DATABASE dropped; $API_USER and $JUDGE_USER removed"
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
  # All SEVEN classes are counted, because this total is what the "nothing to delete"
  # sentence below rests on. Counting three of seven and then saying ZERO would be the
  # same defect as the closing sentence's, one screen earlier.
  TOTAL_OURS=0
  for b in $OURS;           do TOTAL_OURS=$((TOTAL_OURS + 1)); done
  for f in $OUR_LAMBDAS;    do TOTAL_OURS=$((TOTAL_OURS + 1)); done
  for p in $OUR_PARAMS;     do TOTAL_OURS=$((TOTAL_OURS + 1)); done
  for r in $OUR_ROLES;      do TOTAL_OURS=$((TOTAL_OURS + 1)); done
  for g in $OUR_LOG_GROUPS; do TOTAL_OURS=$((TOTAL_OURS + 1)); done
  for a in $OUR_ALARMS;     do TOTAL_OURS=$((TOTAL_OURS + 1)); done
  for d in $OUR_DASHBOARDS; do TOTAL_OURS=$((TOTAL_OURS + 1)); done
  info "dry run — nothing was deleted, so there is nothing to verify."
  if [ "$TOTAL_OURS" -eq 0 ]; then
    ok "and there was nothing to delete: ZERO resources across all seven classes this"
    ok "project creates — buckets, IAM role, Lambda functions, log group, alarms,"
    ok "dashboard, SSM parameter. Buckets and the role were read account-wide; the other"
    ok "five in $REGION. The last teardown was clean."
  else
    info "$TOTAL_OURS resource(s), across the seven classes this project creates, are"
    info "listed above. Every one of them is re-read after deletion by the verify block."
  fi
  exit 0
fi
RESIDUE=0
# Every listing here goes through aws_query for the reason given at its definition:
# "verified clean" must never be the result of a call that failed.
aws_query "s3api list-buckets (verify)" s3api list-buckets --query "Buckets[?starts_with(Name, '${NAME_PREFIX}')].Name"
# --keep-state keeps EXACTLY ONE bucket, and it keeps it BY NAME. It was previously read
# as a licence to forgive every surviving bucket at once, so a site bucket that outlived
# step 2 would have been waved through by a flag that has nothing to say about it. The
# state bucket is excused by name; anything else with our prefix is still residue.
LEFT=""; STATE_KEPT=0
for b in $QUERY_OUT; do
  if [ "$KEEP_STATE" -eq 1 ] && [ "$b" = "$STATE_BUCKET" ]; then STATE_KEPT=1; continue; fi
  LEFT="$LEFT $b"
done
LEFT="${LEFT# }"
if [ -n "$LEFT" ]; then
  printf '   %s[NO]%s buckets still present: %s\n' "$BOLD" "$RESET" "$LEFT" >&2
  RESIDUE=1
elif [ "$STATE_KEPT" -eq 1 ]; then
  ok "no ${NAME_PREFIX}* buckets remain except s3://$STATE_BUCKET, kept by --keep-state"
else
  ok "no ${NAME_PREFIX}* buckets remain"
fi
if "${AWSX[@]}" ssm get-parameter --name "$DSN_PARAM" >/dev/null 2>&1; then
  printf '   %s[NO]%s %s still exists\n' "$BOLD" "$RESET" "$DSN_PARAM" >&2
  RESIDUE=1
else
  ok "$DSN_PARAM is gone"
fi
aws_query "lambda list-functions (verify)" lambda list-functions --query "Functions[?starts_with(FunctionName, '${NAME_PREFIX}')].FunctionName"
LEFT_FN="$QUERY_OUT"
if [ -n "$LEFT_FN" ]; then
  printf '   %s[NO]%s lambda functions still present: %s\n' "$BOLD" "$RESET" "$LEFT_FN" >&2
  RESIDUE=1
else
  ok "no ${NAME_PREFIX}* lambda function remains in $REGION"
fi

# ── classes 4 to 7: the ones the closing sentence used to assert without reading ──────
#
# Same shape as the three above, same aws_query, same RESIDUE convention, and for the same
# reason: an unreadable account must not be reported as an empty one. Scope per class is
# as established in step 0's inventory — IAM account-wide, the rest in $REGION.
#
# ONE ROLE CHECK COVERS THREE OF THE ELEVEN PLANNED RESOURCES. `aws_iam_role_policy`
# (mainline-demo-api-dsn-read) is an INLINE policy on this role, and
# `aws_iam_role_policy_attachment` (AWSLambdaBasicExecutionRole) is an attachment to it.
# Neither can outlive the role: IAM refuses to delete a role that still carries either, so
# a role that is gone is proof that both went with it. Nothing separate to re-read, and
# nothing assumed — this is IAM's own constraint, not an inference about Terraform.
aws_query "iam list-roles (verify)" iam list-roles \
  --query "Roles[?starts_with(RoleName, '${NAME_PREFIX}')].RoleName"
LEFT_ROLES="$QUERY_OUT"
if [ -n "$LEFT_ROLES" ]; then
  printf '   %s[NO]%s iam roles still present: %s\n' "$BOLD" "$RESET" "$LEFT_ROLES" >&2
  RESIDUE=1
else
  ok "no ${NAME_PREFIX}* iam role remains (account-wide; IAM is global)"
fi

# Lambda creates /aws/lambda/<function> itself on first invocation if Terraform has not,
# so this is the one of the four most likely to survive a destroy Terraform thinks
# succeeded — the log group need never have been in state to exist.
aws_query "logs describe-log-groups (verify)" logs describe-log-groups \
  --log-group-name-prefix "/aws/lambda/${NAME_PREFIX}" --query 'logGroups[].logGroupName'
LEFT_LOGS="$QUERY_OUT"
if [ -n "$LEFT_LOGS" ]; then
  printf '   %s[NO]%s log groups still present: %s\n' "$BOLD" "$RESET" "$LEFT_LOGS" >&2
  RESIDUE=1
else
  ok "no /aws/lambda/${NAME_PREFIX}* log group remains in $REGION"
fi

aws_query "cloudwatch describe-alarms (verify)" cloudwatch describe-alarms \
  --alarm-name-prefix "${NAME_PREFIX}" \
  --query '[MetricAlarms[].AlarmName, CompositeAlarms[].AlarmName][]'
LEFT_ALARMS="$QUERY_OUT"
if [ -n "$LEFT_ALARMS" ]; then
  printf '   %s[NO]%s cloudwatch alarms still present: %s\n' "$BOLD" "$RESET" "$LEFT_ALARMS" >&2
  RESIDUE=1
else
  ok "no ${NAME_PREFIX}* cloudwatch alarm remains in $REGION (metric or composite)"
fi

aws_query "cloudwatch list-dashboards (verify)" cloudwatch list-dashboards \
  --dashboard-name-prefix "${NAME_PREFIX}" --query 'DashboardEntries[].DashboardName'
LEFT_DASH="$QUERY_OUT"
if [ -n "$LEFT_DASH" ]; then
  printf '   %s[NO]%s cloudwatch dashboards still present: %s\n' "$BOLD" "$RESET" "$LEFT_DASH" >&2
  RESIDUE=1
else
  ok "no ${NAME_PREFIX}* cloudwatch dashboard remains in $REGION"
fi

printf '\n'
if [ "$RESIDUE" -ne 0 ]; then
  die "teardown finished with residue, listed above. Nothing here is destructive to run
   twice — re-run it, or delete the named resources by hand." 1
fi

# ── the closing sentence, and exactly what stands behind it ───────────────────────────
#
# Seven classes were re-read above, so the sentence names seven and names the scope each
# was read at. It does not say "nothing this project created remains" full stop, because
# no set of API calls can support that: what it can support is these classes, at these
# scopes, in this account and this region — so that is what it says.
ok "teardown complete — of the seven resource classes this project creates, none remains:"
ok "  no ${NAME_PREFIX}* s3 bucket and no ${NAME_PREFIX}* iam role anywhere in account $ACCOUNT,"
ok "  and no ${NAME_PREFIX}* lambda function, log group, alarm or dashboard, and no"
ok "  $DSN_PARAM, in $REGION. Each re-read from AWS after deletion, not inferred."
# Two flags deliberately leave something behind. A closing tick that did not mention them
# would be back to being broader than its evidence, one flag later.
if [ "$STATE_KEPT" -eq 1 ]; then
  info "EXCEPT s3://$STATE_BUCKET, which --keep-state kept on purpose. It is a bucket this"
  info "project created and it is still there; delete it, or re-run without --keep-state."
fi
if [ "$KEEP_DB" -eq 1 ]; then
  info "--keep-db was passed, so the CockroachDB Cloud database $DEMO_DATABASE and the"
  info "logins $API_USER / $JUDGE_USER are UNTOUCHED and still cost whatever they cost."
  info "They are not in AWS account $ACCOUNT, so nothing above looked for them."
fi
