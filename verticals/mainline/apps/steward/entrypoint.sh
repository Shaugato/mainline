#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 MAINLINE contributors
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
#
# ONE OCCURRENCE, IN SIX STEPS, IN THIS ORDER.
#
# The order is the argument. Everything that can be refused is refused before a
# credential is used and before a single row is read:
#
#   1. require the environment           — a run that cannot name itself does not read
#   2. check out the pinned skills       — a floating skill is a floating claim
#   3. verify the pins by content        — the commit says which bytes; this says the same
#   4. render the prompt                 — prompt_version is one seventh of agent_identity
#   5. run headless Claude Code          — the tool loop, capability-starved by settings.json
#   6. attest                            — WE do the reads and the hashing, not the model
#
# STEP 6 IS NOT A FORMALITY AND IT IS NOT THE MODEL'S OUTPUT. `mainline-steward attest`
# re-issues every contracted read itself, through the typed MCP client, and hashes the
# rows. The Claude Code session in step 5 produces NARRATIVE, which is attached to
# findings that already exist. An LLM ops report is evidence that a review occurred, not
# evidence of a condition — so the report and the evidence are produced by different
# things on purpose, and the evidence survives the report being wrong.
#
# Step 5 is allowed to fail. A session that crashed, timed out or refused leaves the run
# with no narrative and a complete attestation; step 6 is what must not fail silently.
#
# THERE IS NO INLINE PYTHON IN THIS FILE. Everything the shell needs is a verb on
# `mainline-steward`, so each step is testable off the container and a heredoc cannot
# quietly become the place a rule lives.

set -euo pipefail

STEWARD_HOME="${STEWARD_HOME:-/opt/steward}"
APP_DIR="${STEWARD_HOME}/app"
RUN_DIR="${STEWARD_HOME}/run"
STATE_DIR="${STEWARD_HOME}/state"
SKILLS_DIR="${STEWARD_HOME}/skills"
CONTRACT="${MAINLINE_MCP_CONTRACT:-${STEWARD_HOME}/spec/mcp/audit-surface.contract.yaml}"
SKILLS_REPO="${MAINLINE_STEWARD_SKILLS_REPO:-https://github.com/cockroachlabs/cockroachdb-skills.git}"

log() { printf '%s  steward  %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >&2; }
die() { log "REFUSED: $*"; exit 1; }

# ── 1. Require the environment ───────────────────────────────────────────────────────
#
# EventBridge Scheduler supplies SCHEDULE_ID and OCCURRENCE_TS through the target's input
# transformer; OCCURRENCE_TS must be `<aws.scheduler.scheduled-time>`, which carries the
# SAME value on every retry of one occurrence. That sameness is the entire idempotency
# story, so a run started by hand must pass the same field and never `date -u`.
: "${SCHEDULE_ID:?SCHEDULE_ID is required (a schedule_id declared in schedules.yaml)}"
: "${OCCURRENCE_TS:?OCCURRENCE_TS is required (EventBridge <aws.scheduler.scheduled-time>)}"
: "${MAINLINE_SITE_CODE:?MAINLINE_SITE_CODE is required (the ledger partition)}"
: "${MAINLINE_MCP_CLUSTER_ID:?MAINLINE_MCP_CLUSTER_ID is required (pins exactly one cluster)}"
: "${CC_MCP_API_KEY:?CC_MCP_API_KEY is required (Cluster Operator, mcp:read + one INSERT)}"
: "${MAINLINE_SCHEMA_VERSION:?MAINLINE_SCHEMA_VERSION is required (one of the seven A13 inputs)}"
: "${MAINLINE_STEWARD_TASK_ROLE_ARN:?MAINLINE_STEWARD_TASK_ROLE_ARN is required (A13 input)}"
: "${MAINLINE_STEWARD_INFERENCE_PROFILE_ARN:?MAINLINE_STEWARD_INFERENCE_PROFILE_ARN is required}"

export MAINLINE_STEWARD_MODEL_ID="${MAINLINE_STEWARD_MODEL_ID:-au.anthropic.claude-opus-5}"
MAINLINE_STEWARD_CLAUDE_CODE_VERSION="$(claude --version 2>/dev/null | head -n1 || true)"
[ -n "${MAINLINE_STEWARD_CLAUDE_CODE_VERSION}" ] \
  || die "claude --version produced nothing; the runtime version is in every attestation"
export MAINLINE_STEWARD_CLAUDE_CODE_VERSION

# §10.1: the residency control is a VPC-endpoint policy enumerating au.* inference-profile
# ARNs. A non-au profile would be a run whose inference left Australia; it is refused HERE
# as well so the failure is attributable rather than a 403 with no context. Residency is
# stated precisely and never overstated — inference is in ap-southeast-2 (Sydney) and the
# DATABASE is in aws-ap-southeast-1 (Singapore), so end-to-end Australian residency is not
# a claim this deployment can make.
case "${MAINLINE_STEWARD_INFERENCE_PROFILE_ARN}" in
  *au.*) : ;;
  *) die "MAINLINE_STEWARD_INFERENCE_PROFILE_ARN does not name an au.* inference profile" ;;
esac

[ -f "${CONTRACT}" ] || die "no audit-surface contract at ${CONTRACT}. It is owned by the \
fleet-contracts worker (spec/mcp/audit-surface.contract.yaml), and every statement this \
run would issue comes from it — there is nothing to read without it."

RUN_SLUG="$(printf '%s' "${SCHEDULE_ID}-${OCCURRENCE_TS}" | tr -c 'A-Za-z0-9._-' '-')"
TRANSCRIPT="${RUN_DIR}/${RUN_SLUG}.session.json"
PROMPT_FILE="${RUN_DIR}/${RUN_SLUG}.prompt.md"
mkdir -p "${RUN_DIR}" "${STATE_DIR}" "${SKILLS_DIR}"

log "occurrence ${SCHEDULE_ID}@${OCCURRENCE_TS} · cluster ${MAINLINE_MCP_CLUSTER_ID}"
log "runtime ${MAINLINE_STEWARD_CLAUDE_CODE_VERSION} · model ${MAINLINE_STEWARD_MODEL_ID}"

# ── 2. Check out the pinned skills ───────────────────────────────────────────────────
#
# One commit, fetched by object name. `git fetch --depth 1 origin <sha>` asks the server
# for exactly that object: no branch is consulted, so nothing about `main` moving can
# change what this run consumed. `git checkout FETCH_HEAD` then puts those bytes on disk
# and `git clean` removes anything a previous occurrence left behind.
SKILL_COMMIT="$(mainline-steward skills commit --app-dir "${APP_DIR}")"
[ -n "${SKILL_COMMIT}" ] || die "could not read the pinned skills commit from the lock"

if [ ! -d "${SKILLS_DIR}/.git" ]; then
  git -C "${SKILLS_DIR}" init --quiet
  git -C "${SKILLS_DIR}" remote add origin "${SKILLS_REPO}"
fi
log "fetching skills ${SKILLS_REPO}@${SKILL_COMMIT}"
git -C "${SKILLS_DIR}" fetch --quiet --depth 1 origin "${SKILL_COMMIT}"
git -C "${SKILLS_DIR}" checkout --quiet --detach FETCH_HEAD
git -C "${SKILLS_DIR}" clean --quiet -fdx --exclude=.git

# ── 3. Verify the pins by content, then stage them for the session ───────────────────
#
# The commit says which bytes; this step says the same thing independently and writes the
# digest that goes into the attestation. A pin whose `expected_sha256` is recorded is
# ENFORCED here — a mismatch exits non-zero and no reads happen.
mainline-steward skills verify \
  --app-dir "${APP_DIR}" \
  --skills-root "${SKILLS_DIR}" \
  --schedule-id "${SCHEDULE_ID}"

mainline-steward skills stage \
  --app-dir "${APP_DIR}" \
  --skills-root "${SKILLS_DIR}" \
  --schedule-id "${SCHEDULE_ID}" \
  --destination "${APP_DIR}/.claude/skills"

# ── 4. Render the prompt ─────────────────────────────────────────────────────────────
PROMPT_VERSION="$(mainline-steward prompt --app-dir "${APP_DIR}" \
  "${SCHEDULE_ID}" "${OCCURRENCE_TS}" --version-only)"
mainline-steward prompt --app-dir "${APP_DIR}" "${SCHEDULE_ID}" "${OCCURRENCE_TS}" \
  > "${PROMPT_FILE}"
log "prompt_version ${PROMPT_VERSION}"

# ── 5. The tool loop ─────────────────────────────────────────────────────────────────
#
# `--strict-mcp-config` so ONLY ${APP_DIR}/.mcp.json is loaded: no user-scope server, no
# plugin server, no claude.ai connector. `--settings` so the allowlist is this file's
# rather than a merge with something in a home directory. `--allowedTools` repeats the
# allowlist on the command line because a settings file that failed to load must not
# degrade into a permissive session — the two must agree, and
# tests/integration/steward/test_capability_boundary.py asserts they do.
#
# ALLOWED TO FAIL. `|| log ...`: a crashed, timed-out or refused session costs the run its
# narrative and costs the attestation nothing.
mapfile -t ALLOWED_TOOLS < <(mainline-steward allowlist --app-dir "${APP_DIR}" --mcp-only)
[ "${#ALLOWED_TOOLS[@]}" -gt 0 ] || die "settings.json produced an empty MCP allowlist"

log "running headless claude code with ${#ALLOWED_TOOLS[@]} permitted MCP verbs"
claude -p "$(cat "${PROMPT_FILE}")" \
  --output-format json \
  --settings "${APP_DIR}/settings.json" \
  --mcp-config "${APP_DIR}/.mcp.json" \
  --strict-mcp-config \
  --permission-mode default \
  --allowedTools "${ALLOWED_TOOLS[@]}" \
  --disallowedTools "Bash" "Write" "Edit" "WebFetch" "WebSearch" "Task" \
  > "${TRANSCRIPT}" 2> "${RUN_DIR}/${RUN_SLUG}.session.err" \
  || log "the Claude Code session did not exit 0; the run continues with no narrative"

# ── 6. Attest ────────────────────────────────────────────────────────────────────────
#
# `--send` writes the one permitted row. It is opt-in via MAINLINE_STEWARD_SEND=1 so that
# a smoke run in a new environment produces a complete, hashed attestation on disk and
# adds nothing to a real evidentiary table.
SEND_FLAG=()
if [ "${MAINLINE_STEWARD_SEND:-0}" = "1" ]; then
  SEND_FLAG=(--send)
else
  log "MAINLINE_STEWARD_SEND is not 1: the attestation will be built and NOT written"
fi

exec mainline-steward attest \
  --app-dir "${APP_DIR}" \
  --contract "${CONTRACT}" \
  --site-code "${MAINLINE_SITE_CODE}" \
  --cluster-id "${MAINLINE_MCP_CLUSTER_ID}" \
  --skills-root "${SKILLS_DIR}" \
  --transcript "${TRANSCRIPT}" \
  --out "${RUN_DIR}" \
  --state-dir "${STATE_DIR}" \
  --report "${RUN_DIR}/${RUN_SLUG}.ops-attestation.pretty.json" \
  "${SEND_FLAG[@]}" \
  "${SCHEDULE_ID}" "${OCCURRENCE_TS}"
