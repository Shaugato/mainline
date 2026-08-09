<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
-->

# The Steward — operations runbook

> **An LLM ops report is evidence that a review occurred, not evidence of a condition.**
>
> Everything below follows from that sentence. If you read one line of this runbook, read
> that one; `tests/integration/steward/test_evidence_sentence.py` asserts it is also in
> this distribution's `README.md` and in `mainline_steward/attestation.py`, so it cannot
> be quietly dropped from one of the three.

## 1. What the Steward is

A Fargate ARM64 task, started by EventBridge Scheduler, that runs headless Claude Code
over pinned CockroachDB Agent Skills against the Managed MCP Server, and then emits one
hashed `ops_attestation` committed by a single row in
`mainline_meas.external_attestation`.

It is one of only two components in MAINLINE that hold a tool loop, and both of them live
in the Control plane — that is, neither can write a field the merge gate reads. The
Steward's SQL identity is `mainline_auditor`, which holds `SELECT` on `mainline_audit`
views and `INSERT` on exactly one table. It has no path to `mainline`, none to
`mainline_qa`, and no `UPDATE` or `DELETE` anywhere.

## 2. The six steps of a run

`entrypoint.sh` does these in order and refuses early rather than late.

| # | Step | Refuses when |
|---|---|---|
| 1 | Require the environment | any of the eight required variables is unset; the inference profile is not `au.*`; the audit-surface contract is absent |
| 2 | `git fetch --depth 1 origin <pinned commit>` | the object name is not fetchable |
| 3 | `mainline-steward skills verify` | a checkout is empty, or its digest differs from a recorded `expected_sha256` |
| 4 | `mainline-steward prompt` | a prompt asset is missing |
| 5 | `claude -p …` | **never** — a failed session costs the run its narrative and nothing else |
| 6 | `mainline-steward attest` | the occurrence was already attested (exit 0); a contracted view is not in the contract; the payload will not canonicalise; the write is rejected |

**Step 6 does the reads.** This is the part people get wrong when they first read the
image. The model in step 5 reads views too — that is what makes it a review — but its
output is *narrative*. The statements and the row hashes in the attestation are produced
in step 6, by `mainline_mcp.Client`, from the audit-surface contract. A reader who throws
the narrative away loses nothing that the attestation asserts.

## 3. The allowlist is the capability boundary

`settings.json` carries an **allowlist**, not a denylist with exceptions. In `claude -p`
there is nobody to answer a permission prompt, so anything not on the list is refused. The
list is:

- the seven Managed-MCP read verbs, and
- `insert_rows`, and
- `Read` under `/opt/steward/app` and `/opt/steward/skills`.

Every entry appears twice, once as `MCP(crdb.<verb>)` and once as `mcp__crdb__<verb>`.
Claude Code has used both spellings for MCP tools in permission rules across versions, and
an allowlist that silently became empty would be either a broken Steward or a capability
escape depending on how the empty case is read. Eight extra lines remove the question.

**Why `insert_rows` is on an otherwise read-only list.** The service account is a Cluster
Operator key with `mcp:read` plus `INSERT` on `mainline_meas.external_attestation` and
nothing else (S13). The allowlist is written to match the SQL grant *exactly*, because a
narrower allowlist would be a second, weaker copy of the boundary that a reader would then
have to reconcile against the grant — and the grant is the one that is actually enforced.
The run's own attestation is not written by the session: step 6 writes it, with a
`subject_ref` the session never sees. A row the session wrote itself would carry a shape
the emitter did not mint, and is therefore detectable.

`create_database` and `create_table` — the surface's other two write verbs — are **denied
explicitly** rather than merely omitted, because the denylist takes precedence over every
settings scope and no future user- or managed-scope rule may reach them.

The commentary above is here rather than inside `settings.json` because JSON has no
comments and Claude Code's tolerance of an unrecognised top-level key could not be
verified from the build machine. `tests/integration/steward/test_capability_boundary.py`
asserts this section and the file agree.

## 4. `crdb_internal` is unreachable, and that is the ops API

The Managed MCP surface cannot reach `system`, `crdb_internal`, `pg_catalog`,
`information_schema` or `pg_extension` at all. Most of the stock CockroachDB Agent Skills'
native diagnostics read exactly those schemas, so **they will not run here**, and no amount
of prompting will make them.

They are pointed at four pre-materialised `mainline_audit` views instead —
`v_gate_latency_daily`, `v_txn_restart_daily`, `v_unused_indexes`, `v_changefeed_health` —
declared in the audit-surface contract and implemented by the data-model lead's migration
band. See `runbooks/ops-views-are-the-api.md` for the per-view reading guide and for what
each one cannot tell you.

This is a real limitation and it is also the product's shape: with no `crdb_internal`, an
operator-facing question has nowhere to go except a view somebody wrote, versioned and
budgeted. The limitation, taken seriously, **is** the ops API.

## 5. Idempotency, and what is not claimed

The idempotency key is `(schedule_id, occurrence_ts)`, where `occurrence_ts` is
EventBridge's `<aws.scheduler.scheduled-time>` — the same value on every retry of one
occurrence.

Two mechanisms:

1. `OccurrenceGuard` claims the key in `/opt/steward/state` with an `O_EXCL` create before
   any read, and releases it if the run fails before attesting. A second delivery of a
   completed occurrence exits **0** with `nothing to do:` on stdout.
2. The key is inside the attestation's `subject_ref`
   (`ops_attestation:<schedule_id>@<occurrence_ts>`), so a duplicate row is identifiable
   and collapsible by any reader with no access to the guard.

**Exactly-once is not claimed.** `mainline_auditor` holds `INSERT` and no `SELECT`, so
this container cannot read back to deduplicate; and a task that dies between the write and
the guard record will re-run its occurrence. That is the correct side to fail on — a
missing review is worse than a duplicated one. The structural fix is a
`UNIQUE (attestor, subject_kind, subject_ref)` on `mainline_meas.external_attestation`,
which belongs to the migration that creates the table and is filed as a cross-domain note.

## 6. Failure modes, and what to do

| Symptom | Meaning | Action |
|---|---|---|
| `REFUSED SkillPinRefused: … content digest … does not match` | the checked-out bytes are not the pinned bytes | do **not** re-run. Establish whether the upstream commit was force-pushed or the checkout was tampered with. A pin that is "fixed" by re-recording is not a pin |
| `REFUSED ConfigurationRefused: … audit-surface contract is unusable` | `spec/mcp/audit-surface.contract.yaml` is missing or malformed | the contract is the fleet-contracts worker's; every statement comes from it, so there is nothing to run without it |
| `nothing to do: … has already been attested` | at-least-once redelivery | none. Exit 0 is correct and this must not page anybody |
| outcome `indeterminate` | at least one contracted read did not answer | look at the finding whose `outcome` is `unanswered`; its `detail` carries the surface's refusal. Do not read the other findings as coverage |
| `ResponseTooLarge` on a view | the response reached the 10 KiB server cap and may be **truncated** | this is a contract defect, not a transient. The view needs to aggregate harder; raise it with the data-model lead. AR-6 sets the alarm at 8 KiB precisely so this fires with 20 % headroom |
| the session exited non-zero, run completed | the model leg failed | the attestation is complete and carries `narrative_source` explaining what was recovered. Investigate at leisure |
| `REFUSED CcloudUnavailable` | no shim and no fixtures | the custodian patrol did not run. An unrun patrol must never be reportable as a clean one, which is why this refuses instead of emitting an empty one |

## 7. Verifying an attestation by hand

Given a run's `<slug>.ops-attestation.json` (the **canonical** bytes, not the pretty copy):

```bash
# 1. the leaf hash, exactly as ledger_intake computes it (RFC 6962 §2.1)
printf '\x00' | cat - "<slug>.ops-attestation.json" | sha256sum
#    → must equal the detail_sha256 in the external_attestation row

# 2. re-run any finding's statement yourself, over the same public endpoint
#    (the statement is in the payload, verbatim; it came from the contract, not a model)

# 3. canonicalise the rows you got back under RFC 8785 and hash them
#    → must equal that finding's result_sha256
```

Step 2 is the point. You are re-running our SQL against CockroachDB's own endpoint with
none of our code in the path.

## 8. Running one occurrence by hand

```bash
docker build --platform linux/arm64 \
  -f verticals/mainline/apps/steward/Dockerfile -t mainline-steward:dev .

docker run --rm --platform linux/arm64 \
  -e SCHEDULE_ID=observability-nightly \
  -e OCCURRENCE_TS=2026-08-04T15:00:00Z \
  -e MAINLINE_SITE_CODE=BLK-07 \
  -e MAINLINE_MCP_CLUSTER_ID="$CRDB_CLUSTER" \
  -e CC_MCP_API_KEY="$CC_MCP_API_KEY" \
  -e MAINLINE_SCHEMA_VERSION="$MAINLINE_SCHEMA_VERSION" \
  -e MAINLINE_STEWARD_TASK_ROLE_ARN=arn:aws:iam::000000000000:role/local \
  -e MAINLINE_STEWARD_INFERENCE_PROFILE_ARN=au.anthropic.claude-opus-5 \
  mainline-steward:dev
```

`MAINLINE_SCHEMA_VERSION` is the migration-tree fingerprint the cluster is at — the value
`trappoint migrate attest` compares against the attestation head (`just attest`). It is one
of the seven inputs to `agent_identity`, so it is injected by the task definition in the
deployed posture and must be set by hand here; there is deliberately no default, because a
Steward that guesses which schema it read has attested to an identity it cannot name.

`MAINLINE_STEWARD_SEND` is unset, so the attestation is built, hashed and written to
`/opt/steward/run` and **no row is written**. Set it to `1` only against
`mainline-verify`. `insert_rows` is a real append to a real evidentiary table, and a test
run is not a reason to add a row to one.

## 9. What has and has not been exercised

Verified offline, on a machine with no CockroachDB Cloud organisation and no AWS
credentials: the schedule loader, the pin verifier, the prompt renderer, the finding
builders, the payload canonicalisation and leaf hash, the emitter's single write path,
the `ccloud` parsing and its missing-field refusal, and the capability-boundary
assertions.

**Not verified, and marked as such in the code that depends on it:** whether the Managed
MCP `insert_rows` verb accepts a `BYTES` column as a `\x`-prefixed hex string (isolated in
`BytesEncoding`, two members, one place to change); whether `insert_rows` executes
server-side triggers (`GT-09` — safe under either answer, because
`external_attestation` is trigger-free by construction); and the base image digest, which
was read from Docker Hub's registry API and never pulled here. A wrong digest fails the
build loudly, which is the correct failure.
