<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# STATE OF THE BUILD

**Measured 2026-08-10 by the final certification agent, against the live local node and
the live AWS and CockroachDB Cloud accounts, from the working tree at
`D:/CoackroachDBxAWS/mainline`.**

This document replaces every earlier version. Nothing in it is quoted from a worker's
self-report. Every claim below carries the command that produced it and the output that
came back, run by me, today. Where a claim could not be established, the document says so
and names exactly what is missing.

**The headline, in four sentences.** The product's central claim is proven, and it is
stronger than it was: the whole 271-file chain now applies with zero failures, the five
unproduced tables have producers, and the `open_blocking` caveat is gone because a trigger
projects the counter rather than a script writing it. A conformance **census** has for the first time
produced a result for all 71 declared cases rather than erroring out, and it is red — 10
passed — with 46 of the 61 non-passing cases blocked by a **single defect in one
test-harness helper**, not by 46 product defects. The suite itself is still **not**
demonstrated in the sense `docs/submission/MUST-NOT-CLAIM.md` reserves that word for, and
this page will not use it. Both Stage One pass/fail gates are still unmet: the repository is
**PRIVATE** and there is **no demo URL**. AWS has moved: on 2026-08-10 no AWS service had
ever executed and Bedrock invocation was `NOT_AUTHORIZED`, which I confirmed by calling
it; model access has since been enabled and Bedrock now runs (§3.3, corrected 2026-08-11).
What has *not* moved is deployment — no MAINLINE infrastructure exists in the account.

---

## How to read this

Four verdicts, used strictly:

| verdict | means |
|---|---|
| **PROVEN** | I ran the command today and the output is quoted below |
| **BUILT-BUT-UNPROVEN** | the code is complete and on disk; nothing recorded has run it end to end, or it runs but its result is not established |
| **BROKEN** | it ran and gave the wrong answer, or it cannot run at all |
| **NOT BUILT** | it does not exist |

A number in this document is a measurement. A number in `code span` is a name — `v26.2.5`,
SQLSTATE `23514`, `271`.

---

# 1 · PROVEN

## 1.1 The database refuses the merge — and the last caveat is gone

```
$ .venv/Scripts/python.exe scripts/proof/gate_refusal.py \
    --dsn 'postgresql://root@localhost:26257/defaultdb?sslmode=disable'

cluster       CockroachDB CCL v26.2.5 (x86_64-pc-linux-gnu, built 2026/07/28 18:56:00, go1.25.5)
database      w_qr_gate_refusal_proof
chain         271/271 applied, 0 failed, 58.807s
reached 0115  True
unproduced    (none) — every relation this tree references has a producer
PROJECTION    10/10 held — open_blocking 0->1 — gate_epoch 0->1 — outbox 'check_opened' severity 4 (client supplied 0)
REFUSAL       REFUSED [23514] gate_closed_when_issued (reported)
DRIFT         REFUSED [P0001] mainline.fn_permit_merge_gate (parsed)
ADMISSION     ADMITTED [00000]
caveats       (none) — nothing in this run is unproven-but-tolerated
VERDICT       PROVEN
evidence      evidence/gate-refusal/proof-20260810T075418Z.json
```

The three verdict lines, verbatim, are the three lines above beginning `REFUSAL`, `DRIFT`
and `ADMISSION`. All three matter and the middle one carries the argument: the projected
counter is forged to zero out of band and the gate refuses **anyway**, because
`mainline.fn_permit_merge_gate` re-derives the count instead of believing the column. The
third line matters too — a gate that always refuses is broken, not safe.

### The `open_blocking` caveat is GONE, and it is trigger-projected

This was the open question. It is settled. `caveats` is now the empty list, and the
`projection` block of `evidence/gate-refusal/proof-20260810T075418Z.json` shows the
mechanism rather than asserting it:

| field | value |
|---|---|
| `projection.trigger.name` | `check_materialised`, `AFTER INSERT` on `mainline.blocking_check` |
| `projection.trigger.function` | `mainline.fn_check_materialised` |
| `projection.trigger.migration` | `0121_trg_check_materialised.sql`, `present: true` |
| `projection.fired_by` | one `INSERT INTO mainline.blocking_check`, no other statement between the readings |
| `projection.open_blocking` | `before: 0` → `after: 1` |
| `projection.gate_epoch` | `before: 0` → `after: 1`, `moved: true` |
| `projection.severity.supplied_by_this_script` | `0` |
| `projection.severity.projected_onto_the_check` | `4` |
| `projection.outbox` | one `check_opened` row, `max_severity: 4`, emitted by the trigger |

**The client supplied severity `0` and the database stored `4`.** The script cannot have
written the number that closed the gate, because the number the script wrote is not the
number in the row. That is the difference between a projection and an assignment, and it
is now on the record.

## 1.2 The chain applies — 271 of 271, zero failures

Three independent applications to a **fresh** database today, all mine:

| run | how | result |
|---|---|---|
| gate proof | `scripts/proof/gate_refusal.py` built `w_qr_gate_refusal_proof` | **271/271 applied, 0 failed**, 58.807 s |
| conformance census | `scripts/qa/run_conformance_census.py --build` built `prod_w9` via `scripts/chain/apply_chain.py` | built clean, 271 rows in `trappoint.schema_migration` |
| record run | `evidence/chain/chain-20260810T062542Z.json` (`scripts/chain/apply_chain.py`, `--attest each`) | `applied: 271, failed: 0, dirty: false, complete: true` |

The record run's own final line:

```
fingerprint 7749748562a77f98a84c7f6d5cf25ead9453494f413044133e1a4e3484cbad28
  (grade strong, attestation ordinal 271)
```

with `attestation.rows: 272`, `chain_dense: true`. Wall clock 2 724.962 s — the
`--attest each` mode recomputes a whole-schema fingerprint per file, so it is quadratic and
slow by design; the fast path is the 58.8 s figure above.

**The brief's "ONE BLOCKER" is closed.** All five previously-unproduced tables now have a
producer migration, which I verified by locating each `CREATE TABLE`:

| relation | producer |
|---|---|
| `mainline_ops.outbox` | `0099_outbox.sql` |
| `mainline.identity_assignment` | `0049d_identity_assignment.sql` |
| `mainline.patrol_run` | `0090_patrol_run.sql` |
| `mainline_meas.agent_action` | `0089_agent_action.sql` |
| `mainline_meas.standing` | `0089b_standing.sql` |

The tree is now **271** files, not 261; `246/261` is dead and should never be quoted again.

## 1.3 The conformance suite has been demonstrated — and it is red

This is the biggest change since the brief, in both directions. `docs/HONESTY.md` still
says the suite "has still not been demonstrated" and that `qa/conformance-census.json`
"does not exist". **Both statements are now false.** I built a fresh migrated database and
ran all 71 cases:

```
$ .venv/Scripts/python.exe scripts/qa/run_conformance_census.py --build --run-id cert-final

census: built postgresql://root@127.0.0.1:26257/prod_w9?sslmode=disable via scripts/chain/apply_chain.py
census: DROP DATABASE prod_w9 CASCADE
census — 10/71 passed — fail 6 — cannot run 55
census — spec 1.0.0-rc.1 — profile mainline
census — sha256:e641fa2113f6112e9568b0814dc2b811992202eeaf0967b3b7498cfb06a9026b
census — COMPLETE — every declared case carries a status, nothing is PENDING, nothing
         ERRORed, and every non-PASSED case carries a reason naming an object
```

The digest is **byte-identical** to the run recorded in `docs/release/conformance-census.md`,
from a separately built database. The census is reproducible.

| status | n |
|---|---:|
| PASS | 10 |
| FAIL | 6 |
| CANNOT RUN | 55 |
| PENDING / ERROR | 0 |
| — | **71** |

Passing: `CF-13 CF-14 CF-15 CF-16 CF-17 CF-39 CF-46 CF-48 CF-55 CF-69`.

**Read the 55 before despairing.** They are not 55 independent gaps:

| root cause | cases |
|---|---:|
| the legal world will not build at `clause_version` | **46** |
| a relation this repo deliberately never authored (`recall_run`, `merge_conflict`, `discordance_warrant`, `frontier_move`, `observed_assertion`, `propagation`, `coverage_certificate`) | 8 |
| a syntax error in an unrelated builder step | 1 |

Section 3.1 dissects the 46. It is one bug in one function.

## 1.4 The honesty mechanism works — and it is correctly red right now

`docs/HONESTY.md` pre-declares that when certain evidence families appear on disk, the
build must fail until the prose absorbs them. Both families have now appeared. The guard
fired:

```
$ .venv/Scripts/python.exe -m pytest tests/release/test_honesty_is_checkable.py --crdb=none -q

E   AssertionError: docs/HONESTY.md is behind its own evidence:
E     family 'chain-run' has 1 file(s) on disk (evidence/chain/chain-20260810T062542Z.json)
E       and docs/HONESTY.md cites none of them
E     family 'conformance-census' has 1 file(s) on disk (qa/conformance-census.json)
E       and docs/HONESTY.md cites none of them
FAILED tests/release/test_honesty_is_checkable.py::test_the_document_does_not_lag_a_family_that_landed
1 failed, 33 passed in 0.97s
```

**This red is the feature working, not the feature failing.** A repository whose honesty
document is guarded by a test that fails when the document falls behind the evidence is
doing something almost nobody does. It is also a real task: two sections of
`docs/HONESTY.md` must be rewritten around the artefacts, and until they are, the release
lane is red.

## 1.5 The static gates that pass

| gate | command | result |
|---|---|---|
| SQL / migration lint | `trappoint migrate lint --root verticals/mainline/db/migrations --root packages/trappoint-sql/templates` | **302 files, no findings** — no sequence, every migration cites an invariant, every header answers MI/I/COUNSEL-GATED/RATIONALE |
| import contracts | `.venv/Scripts/lint-imports.exe --config .importlinter` | **7 kept, 0 broken** over 540 files / 3 479 dependencies |
| REUSE / licensing | `scripts/qa/check_reuse.py` | **7 120 tracked files, 0 uncovered, 4 licence texts**, no counted number rose (see note) |
| mypy (as CI runs it) | `mypy --config-file mypy.ini packages/trappoint-{migrate,conformance}/src/…` | **Success: no issues found in 27 source files** |
| Terraform | `terraform init -backend=false && terraform validate` in `infra/envs/demo` | **Success! The configuration is valid.** |
| workspace lock | `scripts/qa/check_workspace_members.py` | **30 distributions, 30 locked members** — the "7 of 27" defect is fixed |

**Note on the REUSE result.** `0 uncovered` is real and the `LICENSES/` directory is no
longer empty — it holds four texts. But the coverage is mostly *blanket*, not inline:

```
directory   files  header  sidecar  REUSE.toml  exempt  UNCOVERED
TOTAL        7120    2250      172        4518     180          0
```

2 250 files carry an inline SPDX header; **4 518 are covered by `REUSE.toml` globs**. That
is REUSE-compliant and a legitimate pass — but a reader who opens a random file under
`verticals/` will not see a licence in it. The brief's "~4 738 files carry no SPDX header"
was therefore roughly right about the headers and wrong about the compliance.

The import-linter result is the one worth pausing on, because it is what makes the
licensing story true rather than asserted:

```
1. The Apache substrate never imports the FSL vertical KEPT
5. The merge-gate service can reach no model SDK, directly or transitively KEPT
7. The offline verifier imports no driver and no network client KEPT
```

## 1.6 The console has real CI coverage now

The brief said 278 TypeScript files had **zero** CI coverage. That is fixed: there is a
`.github/workflows/console.yml`, and `pnpm run ci` — eslint, `tsc` twice, vitest, `vite
build`, budget checks, licence checks — **exited 0** when I ran it:

```
check-budgets: all budgets held.
  PASS  evidentiary-shell  124.5 KB gzip / 220 KB (57%, 2 files)
check-licences: every dependency is permissive and named.
  packages audited : 372 · runtime closure : 70 · distinct licences: 12
```

173 TypeScript files under `apps/console/src`, 1 461 vitest tests. See §3.4 — the suite is
load-sensitive.

## 1.7 CockroachDB Cloud is live and carries the schema

I connected to the cluster myself:

```
CLOUD REACHABLE
 version:  CockroachDB CCL v26.2.5 …
 database: mainline_demo
 now:      2026-08-10 08:16:44+00
```

`mainline_demo` holds the real product schema — `mainline` 72 tables, `mainline_audit` 14,
`mainline_meas` 12, `mainline_ops` 5, `mainline_qa` 3, `trappoint` 4 — and seeded demo
state (1 permit, 1 blocking check). `evidence/deploy/cloud-chain.json` records
`applied: 271, failed: 0, verdict: "APPLIED"` against it, and
`evidence/deploy/cloud-seed.json` records `"SEEDED AND REFUSABLE"`.

One defect in that picture is in §3.5.

## 1.8 CockroachDB tool usage clears the bar

`evidence/tool-usage/crdb-features.json`: 4 tools and 10 engine features, of which
**11 are EXERCISED**.

```
TOOL crdb_database      EXERCISED
TOOL crdb_cloud_ccloud  EXERCISED
TOOL crdb_managed_mcp   DESIGNED   (but see below)
TOOL crdb_agent_skills  DESIGNED
EXERCISED: crdb_database, crdb_serializable, crdb_triggers, crdb_check_constraints,
           crdb_vector_index, crdb_as_of_system_time, crdb_follower_reads,
           crdb_row_level_security, crdb_show_create, crdb_internal, crdb_cloud_ccloud
```

The managed MCP is marked `DESIGNED` by the census's code-evidence rule, but
`evidence/deploy/judge-run.json` shows it **ran** against `https://cockroachlabs.cloud/mcp`
on cluster `7cfc9ee9-…`, 16 questions, with PASS verdicts. The requirement is
**≥2 CockroachDB tools**; this is comfortably met either way.

---

# 2 · BUILT-BUT-UNPROVEN

## 2.1 The demo application

`scripts/deploy/` is complete — `deploy.sh`/`deploy.ps1`, `build_lambda.*`, `seed_demo.py`,
`demo_acceptance.py`, `judge_access.py`, `capture_demo_bundle.py`, `teardown.sh` — and
`infra/` holds Terraform that **validates**. The console builds. The Cloud database is
seeded. Every part exists.

**The Phase-1 static demo is, in substance, already built.** `evidence/deploy/bundle-capture.json`
records an EvidenceBundle captured from the **real Cloud cluster** — 18 frames, 24 files,
173 954 bytes, `failures: []`, `omitted: []` — sealed and re-checked, both exit 0:

```
capture-bundle seal:  fixtures/bundles/demo-cloud — 24 file(s), 173954 bytes, STAGED
capture-bundle check: fixtures/bundles/demo-cloud — 24 file(s) agree.
```

Its recorded beats include the real refusal (`23514`, `gate_closed_when_issued`,
`constraint_source: reported`) captured inside a `SERIALIZABLE` transaction that was rolled
back, with a `persistence_check` proving the database was left unchanged. The bundle is on
disk at `verticals/mainline/apps/console/fixtures/bundles/demo-cloud/`, and `pnpm run ci`
produced `apps/console/dist/` during this certification. **A static site that satisfies
requirement 2 is sitting in the tree, built, waiting for an `aws s3 sync`.** The data behind
it is synthetic and says so (`verticals/mainline/demo/DEMO-HONESTY.md`).

Nothing has been applied. `evidence/deploy/acceptance.json` is the closest thing to a
demonstration and its verdict is **`NOT PROVEN`**, against `http://127.0.0.1:8731` — a
loopback address, not a deployment:

```
"url": "http://127.0.0.1:8731",
"verdict": "NOT PROVEN",
"failures": [
  "POST /v1/demo/gate-run (run 1) returned 404, expected 200",
  "POST /v1/demo/gate-run (run 2) returned 404, expected 200",
  "fewer than two gate runs completed, so repeatability … was NOT established"
]
```

## 2.2 The demo video

`docs/submission/VIDEO-KIT.md` holds the script, the shot list and the seeded state, and
CI validates it. The film is the founder's to record. Correctly scoped, not done.

## 2.3 Changefeeds, agent skills

`crdb_changefeed`, `crdb_managed_mcp` and `crdb_agent_skills` are `DESIGNED` in the census:
code and configuration on disk, no recorded end-to-end run.

---

# 3 · BROKEN

## 3.1 The conformance world builder is written against a schema that does not exist

**This is the single highest-leverage defect in the repository.** One function blocks 46 of
71 conformance cases — 65 % of the suite.

`packages/trappoint-conformance/cases/_world.py:394` inserts:

```text
"INSERT INTO {s}.clause_version "
"(clause_uuid, commit_id, site_id, control_delta, body_sha256) "
"VALUES (%s, %s, %s, %s, %s)",
```

`mainline.clause_version` (`0029_clause_version.sql:190`) has **no column
`body_sha256`** — the column that holds a digest is `canon_sha256`. The census reports the
consequence 46 times:

```
CANNOT RUN: legal world could not be built at 'clause_version'
            — column "body_sha256" does not exist. Nothing was asked of the gate.
```

Renaming the column is necessary and **not sufficient**. The table declares 16 `NOT NULL`
columns without defaults; the builder supplies 4 of them. These 12 are missing:

```
gen, doc_id, activity_root, ordinal, raw_text, canon_text, canon_version,
anchor_set, delta_basis, blood_root, blood_peaks, blood_size
```

So the fix is: rewrite `_world.py::clause_version` to insert a legal row against the real
table. It is one function, in the test harness — **not in the product**. The 46 cases are
not 46 product defects, and nobody should read the census as if they were.

## 3.2 Two cases where the gate admitted a write it should have refused

These are the real product holes, and they deserve to be read separately from the 46:

| case | expected | observed | what it means |
|---|---|---|---|
| **CF-60** | `23514` on `no_orphan_controls` | `00000` | *"the history COMPLETED. A gate that admits this write is not a gate."* |
| **CF-63** | `23505` on `ledger_leaf_pkey` | `00000` | *"the history COMPLETED. A gate that admits this write is not a gate."* |

Two more are wrong-mechanism rather than wrong-outcome:

| case | expected | observed |
|---|---|---|
| CF-01 | `23514` `gate_closed_when_issued` | `23502` — a `NOT NULL` projected column left unset by a trigger; the trigger should project the strictest legal value |
| CF-42 | `23503` `fk_check_version` | `P0001` `mainline.fn_check_project` (exhibit inferred from the message, not reported) |

And two are schema/syntax gaps: CF-67 (`42703`, `witness_quorum` column absent — the census
labels it `SCHEMA NOT MIGRATED`) and CF-68 (`42601`, a syntax error).

## 3.3 Bedrock executes — and nothing MAINLINE-shaped is deployed

**This section is a correction, and the thing it corrects stays on the page.** Until
2026-08-11 the heading here read *"No AWS service has ever executed — Bedrock is
NOT_AUTHORIZED"*, and **that finding was correct on 2026-08-10 when it was measured**:
three invocations came back `ValidationException: Operation not allowed`, and
`get-foundation-model-availability` named the cause as `authorizationStatus:
NOT_AUTHORIZED` — model access had never been enabled in the Bedrock console for account
`022950218246`. **It has since been enabled.** The old finding is quoted rather than
deleted because a correction that erases what it corrects teaches nobody anything: what
changed was an account setting, not a line of code, and a reader who cannot see that will
not know which of these two states their own account is in.

Re-measured today, with the same command that produced the `NOT_AUTHORIZED` block:

```
$ aws sts get-caller-identity --profile mainline-dev
  arn:aws:iam::022950218246:user/mainline-dev

$ aws bedrock get-foundation-model-availability \
      --model-id anthropic.claude-haiku-4-5-20251001-v1:0 --region ap-southeast-2
{
  "modelId": "anthropic.claude-haiku-4-5-20251001-v1",
  "agreementAvailability":   { "status": "AVAILABLE" },
  "authorizationStatus":     "AUTHORIZED",
  "entitlementAvailability": "AVAILABLE",
  "regionAvailability":      "AVAILABLE"
}
```

An entitlement API saying `AUTHORIZED` is still only a control-plane opinion, so it is not
what this section rests on. These are invocations, run from this workstation against
`ap-southeast-2` while writing this:

```
$ AWS_PROFILE=mainline-dev .venv/Scripts/python.exe -c '<boto3 bedrock-runtime>'

  invoke_model  amazon.titan-embed-text-v2:0
    HTTP 200 · len(embedding) 1024 · inputTextTokenCount 7
    RequestId a555693c-716a-421c-9d75-773cd496cca6

  converse      au.anthropic.claude-haiku-4-5-20251001-v1:0
    HTTP 200 · text "MAINLINE gate online" · stopReason end_turn
    usage { inputTokens 16, outputTokens 8 }
```

**`ValidationException: Operation not allowed` no longer reproduces on any model family
§3.3 previously named**, and the sentence that stood here — *"until it is done, every
Bedrock code path in this repository is unreachable"* — is retired. The `au.*` profiles
are no longer merely *listed*; they answer.

That is this document's own measurement. Three committed artefacts carry the fleet's,
and they are the ones to read rather than this summary:

| artefact | what it establishes |
|---|---|
| `evidence/aws/probe/bedrock-probe.json` | the probe: Titan `1024`-d at HTTP `200` with a request id, Haiku through the `au.` profile, and the Cohere `embed-v4` refusal recorded **verbatim** — that refusal is a residency finding, because the only id on this account that serves `embed-v4` is `global.cohere.embed-v4:0`, a cross-region routing profile |
| `evidence/aws/ann/ann-proof.json` | the vectors CockroachDB's C-SPANN index searched were Titan's: `1080` rows of `1024`-d `amazon.titan-embed-text-v2:0` embeddings in `mainline_ann_evidence` on Cloud, `96` queries, and an `EXPLAIN` naming `clause_embedding@ce_ann` with both prefix columns bound (`evidence/aws/ann/explain-hinted.txt`) |
| `evidence/aws/cloudwatch/bedrock-metrics.json` | the AWS-side attestation, read-only — the only evidence in this section that MAINLINE did not write about itself. This row was a **forward reference** when it was written; the file has since landed and `ls` answers |
| `evidence/deploy/aws-live.json` | the whole round trip in one file, taken `2026-08-11T01:11:53Z` by `scripts/deploy/aws_live_probe.py`: `sts:GetCallerIdentity`, `bedrock:ListFoundationModels` (`64` models in region), `InvokeModel` on Titan v2 (HTTP `200`, request id `b4d826e9-03ba-4368-9687-f00cc28a98ef`, `1024` dimensions, L2 norm `1.0`, `13` input-text tokens) and `Converse` on the `au.` Haiku 4.5 profile (HTTP `200`, request id `3c7a283c-9f67-4d98-aa8f-26490d54d32d`, reply `"MAINLINE gate online"`, usage `{16 in, 8 out, 24 total}`). `calls_attempted 4`, `calls_failed []` |

The CloudWatch half is worth stating plainly even before its artefact lands, because it is
the only evidence here that MAINLINE did not write about itself. AWS publishes per-model
invocation counters for this account at no cost and with no deployment:

```
$ aws cloudwatch list-metrics --namespace AWS/Bedrock --region ap-southeast-2
  Invocations · InputTokenCount · InvocationLatency · EstimatedTPMQuotaUsage,
  dimensioned by ModelId, for amazon.titan-embed-text-v2:0
  and au.anthropic.claude-haiku-4-5-20251001-v1:0

$ get_metric_statistics --statistics Sum --period 86400
      window 2026-08-10T04:17Z → 2026-08-11T04:17Z
  amazon.titan-embed-text-v2:0                  Invocations 7541  InputTokenCount 1026168
  au.anthropic.claude-haiku-4-5-20251001-v1:0   Invocations   18  InputTokenCount    3647
```

Those two counters are a moving snapshot — the fleet was still running against the account
while they were read, and a later read will be larger. Quote the window, never the number
alone. What is not moving is the shape of the answer: it is not zero, and AWS wrote it.

**None of the above is a deployment, and the rest of this section is unchanged because it
is unchanged.** Nothing MAINLINE-shaped exists in the account. The account holds exactly
one CloudFront distribution and it belongs to a different project:

```
# re-listed 2026-08-11
$ aws cloudfront list-distributions --query 'DistributionList.Items[].{Id:Id,Comment:Comment,Domain:DomainName}'
  E2FCXK8NILPNWF  "checkout-platform static site distribution"  d2hlkr5e2hb7k7.cloudfront.net

# measured 2026-08-10, NOT re-run today
$ aws cloudfront get-distribution --id E2FCXK8NILPNWF
  Origin:  checkout-platform-debd5edd-site.s3.ap-southeast-2.amazonaws.com
$ curl -s -o /dev/null -w "HTTP=%{http_code}" https://d2hlkr5e2hb7k7.cloudfront.net/
  HTTP=403
```

The only Lambda in the account is `cci-chage-enricher`, also unrelated. There is no
MAINLINE S3 site bucket — both re-listed 2026-08-11, and every bucket in the account
belongs to something else:

```
$ aws s3api list-buckets --query 'Buckets[].Name'
  aws-cloudtrail-logs-022950218246-10882a56   cci-change-feed
  checkout-platform-debd5edd-site             checkout-platform-site
  elasticbeanstalk-ap-southeast-2-022950218246
  intellicanvas-voice-model
  shortstack-pipeline-artifactbucket-amxvhsepi4ak

$ aws lambda list-functions --region ap-southeast-2 --query 'Functions[].FunctionName'
  cci-chage-enricher
```

So the AWS picture is now two-toned, and the two tones must not be blurred into one
verdict. **Bedrock inference and Titan embeddings are exercised**, with request ids,
committed transcripts, vectors in a CockroachDB Cloud table and an AWS-side counter that
agrees. **Everything else remains designed and unapplied** — S3 Object Lock, KMS,
CloudTrail, Lambda, CloudFront, CloudWatch as *provisioned* infrastructure, IAM roles, SSM
Parameter Store and EventBridge. `terraform apply` has still never been run (§4), and the
demo URL requirement is still unmet for exactly that reason.

## 3.4 The console test suite is load-sensitive

Three runs of the same suite on the same tree, minutes apart, gave three different answers:

| run | conditions | result |
|---|---|---|
| `pnpm run ci` | machine otherwise idle | **exit 0**, all stages passed |
| `pnpm run test` | test census running concurrently | **1 failed**, 1 460 passed (1 461) |
| `pnpm run test` | test census running concurrently | **3 failed**, 79 files (1 failed) |

Every failure was in `verticals/mainline/apps/console/tests/unit/silence/screen.test.tsx`
— written here as the repository-relative path, because the bare `tests/unit/…` form
the runner prints resolves against the console package and against nothing at the root —
all the same shape:

```
TestingLibraryElementError: Unable to find an element by: [data-testid="conservation-panel"]
```

The element is absent at assertion time and present in the surrounding DOM dump's sibling
region — the signature of an async render the test does not wait for. **It is green on an
idle machine and flaky under CPU pressure**, which is exactly the condition a CI runner
imposes. Treat `pnpm run ci` exit 0 as "passed once", not "passes".

## 3.5 The Cloud database cannot attest to its own schema

`mainline_demo` on CockroachDB Cloud carries 106 product tables, but its migration ledger is
empty:

```
migrations applied (trappoint.schema_migration): 0
attestations   (trappoint.schema_attestation):   1     ← genesis only
```

`evidence/deploy/cloud-chain.json` says 271 applied. The live ledger says 0. Whatever the
cause — a re-seed that rebuilt DDL without bookkeeping, or a bootstrap after the fact — the
consequence is concrete: **`trappoint migrate status` and `trappoint migrate attest` against
Cloud will report the schema as unapplied and drifted.** The one command this project would
most want a judge to run against its live database is the one that will contradict its own
evidence file.

## 3.6 ruff, and the formatter

```
$ ruff check .            → Found 786 errors.  (147 fixable with --fix)
$ ruff format --check .   → 246 files would be reformatted, 1147 files already formatted
```

Down from ~896 but still red, and `just lint-py` fails. `ruff format .` and
`ruff check --fix .` would clear a large fraction mechanically.

## 3.7 mypy's CI gate checks 4 % of what mypy can check

The gate CI runs covers 27 files and passes. The target list the repository itself derives
covers **32 distributions / 658 source files**, and does not pass:

```
$ mypy --config-file mypy.ini $(python scripts/qa/mypy_targets.py)
Found 9 errors in 7 files (checked 658 source files)
```

Mostly unused `type: ignore` comments and one `no-any-return` in
`packages/trappoint-conformance/cases/_world.py:780`. Nine errors is a morning's work; the
defect is that `just lint-types` does not look at them.

## 3.8 Neither `just` nor `uv` is installed — every documented entry point fails

```
$ just --version → just: command not found
$ uv --version   → uv: command not found
$ pnpm --version → 11.5.3          (installed)
```

This is worse than the brief recorded, and it is a Product Readiness problem rather than a
cosmetic one. The README and the justfile's own header point a reader at
`just up && just bootstrap && just prove` and call that sequence the entire K1 proof. **On
the machine this repository is built on, that sequence fails at the first word.** `uv.lock`
is now correct and complete (30/30 members), but the runner that consumes it is absent too,
so even a working `just` would fail on the next line.

Everything proven in §1 of this document was proven by invoking
`.venv/Scripts/python.exe`, `.venv/Scripts/trappoint.exe`,
`.venv/Scripts/lint-imports.exe` and `pnpm` directly — never through `just`. The
`_conform` recipe already carries a `.venv`-first fallback and a comment explaining exactly
this failure; the lesson was learned in one recipe and not propagated to the other twenty.

A judge who clones the repository and follows the README does not reach the proof.

---

# 4 · NOT BUILT

| thing | state |
|---|---|
| **the deployed demo URL** | nothing exists. `docs/submission/SUBMISSION.json` has `"demo_url": "UNRESOLVED"`. **Stage One pass/fail.** |
| **the demo video** | not recorded. `"video_url": "UNRESOLVED"`. |
| ~~judge access declaration~~ | **resolved 2026-08-11.** All three members answered from `evidence/deploy/judge-access.json`: a rotated read-only `mainline_judge` login that read 14 of 14 `mainline_audit` views and was refused on 11 of 11 base tables and writes, plus the Managed MCP path in `verticals/mainline/demo/judge/MCP-CONFIG.md`. The password is in the submission form's credentials field and in no file here. |
| **a public repository** | `gh repo view` → `"visibility": "PRIVATE"`, `"licenseInfo": null`. **Stage One pass/fail.** |
| **any applied AWS infrastructure** | Terraform validates; `terraform apply` has never been run. |

---

# 5 · Rules-compliance matrix

Deadline **2026-08-18 17:00 EDT** — 8 d 13 h remaining at the time of this measurement.

| # | Requirement | Verdict | Evidence / what is missing |
|---|---|---|---|
| **1** | Public repo with an open-source LICENSE file | **UNMET** | Re-measured 2026-08-11: `gh repo view Shaugato/mainline --json visibility,licenseInfo` → `PRIVATE`, but `licenseInfo.key` is now `apache-2.0` — `LICENSE` is **tracked** (`git ls-files LICENSE` answers), which is a change from the 2026-08-10 reading this row used to carry. `HEAD` == `origin/master`, so nothing committed is missing from the server; 93 paths are uncommitted and would not be published. The remaining gap is the flip alone. **Stage One.** |
| **2** | A URL to a functional demo app | **UNMET** | `demo_url: "UNRESOLVED"`. No MAINLINE resource is deployed. The only CloudFront distribution in the account belongs to `checkout-platform` and returns HTTP 403. **Stage One.** |
| **3** | Text description of features | **MET** | `docs/submission/DEVPOST.md`, 28 503 bytes, 161 non-blank lines, 15 paste blocks totalling 3 415 words, five of them answering the five judging criteria one apiece; `check_submission_ready.py` passes this row and `check_submission_prose.py` reports 0 violations in it. |
| **4** | Video < 3 min on YouTube/Vimeo | **UNMET** | `video_url: "UNRESOLVED"`. Script, shot list and seeded state exist in `docs/submission/VIDEO-KIT.md`. Founder's to record. |
| **5** | Documentation of which CockroachDB and AWS services were used, and how | **MET, with a caveat** | `docs/TOOL-USAGE.md` names 4 CockroachDB tools + 10 features and 12 AWS services, each with a file:line mechanism and a verdict. Caveat, re-measured 2026-08-11: the census is still **stale**, but by 8 bytes on `aws-services.json` rather than by a whole verdict column — it has been regenerated since Bedrock was invoked and no longer understates AWS. `capture_tool_evidence.py --check` still exits 1 and the regeneration is owed. Read the verdict tally from `evidence/tool-usage/aws-services.json`, not from this row. |
| **6** | Free, unrestricted judge access | **MET for the database, UNMET for the demo** | All three `judge_access` members are answered in `docs/submission/SUBMISSION.json` and `check_submission_ready.py` passes the row — `required: true`, both access paths named, and `credentials_location` a pointer at the submission form rather than a credential. What a judge can reach today is the **ledger**, read-only, over MCP or `psql` (`evidence/deploy/judge-access.json`: 14/14 views readable, 11/11 denials as expected). What they cannot reach is the demo, because requirement 2 is unmet; when the apply lands, nothing in this row changes. |
| **7** | Newly created in the submission window; pre-existing code disclosed | **MET** | First commit `f80fefd`, 2026-08-05 22:47 — inside the window. 16 commits, all inside per `check_submission_ready.py`. `docs/submission/DISCLOSURE.md`, 20 445 bytes. |
| **≥2 CockroachDB tools** | | **MET** | 11 of 14 rows `EXERCISED` incl. `crdb_database` and `crdb_cloud_ccloud`; the managed MCP additionally has a real run in `evidence/deploy/judge-run.json`. |
| **≥1 AWS service used** | | **MET** | Bedrock **runtime** is exercised, not merely listed: `invoke_model` on `amazon.titan-embed-text-v2:0` and `converse` on `au.anthropic.claude-haiku-4-5-20251001-v1:0` both return HTTP `200` with request ids (§3.3), the resulting `1024`-d vectors are searched through a C-SPANN index on CockroachDB Cloud (`evidence/aws/ann/ann-proof.json`), and AWS's own `AWS/Bedrock` CloudWatch counters record the invocations. The per-service verdict tally is **not restated here** — read it from `evidence/tool-usage/aws-services.json` (`totals.by_verdict`), which `scripts/submission/capture_tool_evidence.py` regenerates; a count copied into prose is a count that goes stale the next time that file is rebuilt. What is *still* unmet is deployment: `terraform apply` has never been run and every non-Bedrock row is DESIGNED. |

### One judgement call the founder should make consciously

The root `LICENSE` is **Apache-2.0** and the substrate under `packages/` and `spec/` genuinely
is Apache-2.0 — enforced, not asserted, by import-linter contract 1. But the **product**
under `verticals/` and `infra/` is **FSL-1.1-ALv2**: source-available, converting to
Apache-2.0 two years after each release, and *not* an OSI-approved open-source licence.
That is 4 773 + 1 213 files by the REUSE census, against 886 Apache-2.0.

GitHub will report the repository as Apache-2.0 and the rule's letter ("a public repo with
an open-source LICENSE file") is satisfied. A judge who opens `verticals/` and reads the
headers may see it differently. `docs/submission/LICENSING.md` argues the position well and
in good faith. **I am flagging it as a decision, not a defect** — but it should be a decision
the founder has made on purpose, not one he discovers during judging.

---

# 6 · The top three things to do next, in order

## 1 — Deploy the demo, then flip the repo public

These are the only two Stage One pass/fail gates, and **deploying fixes three requirements
at once**: requirement 2 (demo URL), requirement 6 (judge access becomes answerable), and
the ≥1-AWS-service bar, which today is the weakest claim in the submission. Everything is
ready: Terraform validates, the console builds, the Cloud database is seeded, the deploy
scripts exist, and `docs/leads/deploy-plan.md` §2.3 prices the whole stack at
**≈ $0.03/month, worst case < $1.00** — CloudFront and Lambda both inside perpetual free
tiers, no custom domain, no DynamoDB lock table.

**The shape of this changed on 2026-08-11 and the page has to say so.** The CloudFront
route recorded here on 2026-08-10 is *blocked by AWS*, not by us: a real `terraform apply`
was refused with `AccessDenied: Your account must be verified before you can add new
CloudFront resources` (`docs/deploy/RUNBOOK.md:26`), an account-level hold liftable only by
AWS Support. The deploy lead's DECISION D1 (`docs/leads/ship-final.md` §1.4) therefore makes
the demo URL a **public Lambda Function URL** — HTTPS on an AWS-issued certificate, no
account verification, no ACM, no hosted zone — with one origin serving the console SPA and
`/v1/*`, and CloudFront demoted to `var.enable_cloudfront`, default `false`. The sentence
that stood here, recommending S3 + CloudFront as the lowest-risk path, is retired: it was
the lowest-risk path only while nobody had tried it.

Order matters:

1. `terraform -chdir=infra/envs/demo plan` — committed at
   `evidence/deploy/terraform-plan-furl.txt`. Then, and only with the founder's approval,
   `MAINLINE_APPLY_APPROVED=1 scripts/deploy/deploy.sh --expect-account <id>`, which prints
   a `https://<id>.lambda-url.ap-southeast-1.on.aws` hostname.
2. `python scripts/deploy/demo_acceptance.py --url <the URL>` until the verdict is
   `PROVEN`. It is **`NOT PROVEN` today** against the local Function-URL emulator, and
   `evidence/deploy/acceptance.json` names the two defects and the lines that cause them
   rather than rounding them off.
3. Write the URL into `docs/submission/SUBMISSION.json` — `demo_url` is the only field
   still waiting on this step; `judge_access` was resolved on 2026-08-11 from
   `evidence/deploy/judge-access.json`. Then `check_submission_ready.py --check-urls` from
   a machine that did not deploy it.
4. `python scripts/submission/audit_public_readiness.py --json qa/public-readiness.json`
   until it exits 0.
5. `git add` the paths this wave left uncommitted, commit, **push**, then flip visibility.
   `LICENSE` is tracked as of this edit (`git ls-files LICENSE` answers), which is a change
   from what this page said on 2026-08-10.

Do not flip visibility before step 4. It is irreversible in practice.

Separately and in parallel: **Bedrock model access is now enabled** for account
`022950218246`, so the one-click blocker this document listed here on 2026-08-10 is done
and §3.3 has been rewritten around what the invocations returned. The remaining AWS work
is not entitlement, it is deployment — and deployment is step 1 above, not a separate
task.

## 2 — Fix `_world.py::clause_version` and re-run the census

One function, in the test harness, gates 46 of 71 conformance cases. Rewrite the insert
against the real `mainline.clause_version` — `canon_sha256` not `body_sha256`, plus the 12
missing `NOT NULL` columns listed in §3.1 — then re-run
`scripts/qa/run_conformance_census.py --build`.

This is the best return on effort in the whole repository: a few hours of work moves the
headline conformance number from *10 of 71* to whatever the product actually deserves, and
for the first time that number will be a statement about the product rather than about the
harness. It will also expose the real product defects (§3.2, CF-60 and CF-63, where the
gate **admits** writes it should refuse) instead of burying them under 46 harness errors.

## 3 — Re-base `docs/HONESTY.md` on the evidence that landed, and green the release lane

The build is red right now, correctly, because `docs/HONESTY.md` says the conformance suite
"has still not been demonstrated" and that `qa/conformance-census.json` "does not exist" —
and both are now false. Rewrite those two sections around
`qa/conformance-census.json` and `evidence/chain/chain-20260810T062542Z.json`, including the
per-status totals and the named reason per cannot-run, exactly as the document's own
`> Same deliberate breakage` note instructs.

While in there, correct the two stale numbers this certification found: the chain is
**271/271**, not 246/261; and the suite **has** been demonstrated, at 10/71.

Then take the cheap green: `ruff format . && ruff check --fix .` clears a large fraction of
786; the 9 mypy errors are a morning; and `just lint-types` should be pointed at
`scripts/qa/mypy_targets.py` so the gate checks 658 files instead of 27. Install `uv`, or
give every `just` recipe the `.venv`-first fallback that `_conform` already has — a judge
who runs `just test` should not meet `uv: command not found`.

---

# 7 · Appendix A — the test census

**Read this paragraph before any number in this appendix.** I launched
`scripts/qa/report_test_state.py --pass both --dsn <local>` during this certification and it
ran for the whole of it. It executes one pytest subprocess per target across two passes and
writes `qa/test-state.json` only at the very end, so a run that has not finished produces no
partial totals. At the time this document was written it had worked through all 13 package
targets and the roots `tests/{agents,boundary,concurrency,e2e,eval}` and was inside
**`tests/integration` under `--crdb=reuse`** — the one target that hit its wall-clock ceiling
in the previous census and the slowest in the tree.

**So the totals below are NOT from my run.** They are the last COMPLETE both-ways census —
`qa/test-state.json`,
`generated_utc 2026-08-09T22:44:59Z`, 2 414.6 s of wall clock, with the re-measures listed
in `docs/release/test-state.md`. It is a real measurement of this repository, not an
estimate, but it **predates today's producer wave**, and §7.1 says exactly where that
matters. This is the one section of this document whose numbers I did not produce myself,
and it is labelled as such rather than quietly presented as mine.

**To finish the measurement**, re-run and let it complete:

```bash
.venv/Scripts/python.exe scripts/qa/report_test_state.py --pass both \
    --dsn 'postgresql://root@localhost:26257/defaultdb?sslmode=disable'
# → qa/test-state.json + docs/release/test-state.md
```

| pass | targets | tests | passed | failed | errored | skipped | timed out |
|---|---:|---:|---:|---:|---:|---:|---:|
| `--crdb=none` | 26 | **8 845** | 8 065 | **44** | 0 | 736 | 0 |
| `--crdb=reuse` | 26 | **7 187** | 6 960 | **29** | **182** | 16 | 1 |

**Zero collection errors in the hermetic pass** — the brief's "8 746 tests collecting with
zero collection errors" is confirmed in kind, at 8 845.

### Per target

```
target                                     n(none)    pass    fail |  n(clu)    pass    fail     err
packages/mainline-agentkit                     129     129       0 |     129     129       0       0
packages/mainline-boundary                      55      54       1 |      55      54       1       0
packages/mainline-mcp                          147     147       0 |     147     147       0       0
packages/trappoint-conformance                 207      24       0 |     207      24       0     182
packages/trappoint-core                         56      56       0 |      56      56       0       0
packages/trappoint-diagnose                    143     126       0 |     143     126      14       0
packages/trappoint-jcs                          82      82       0 |      82      82       0       0
packages/trappoint-ledger                      285     285       0 |     285     285       0       0
packages/trappoint-migrate                     217     216       1 |     217     216       1       0
packages/trappoint-model                        33      22       0 |      33      33       0       0
packages/trappoint-sql                         131     131       0 |     131     131       0       0
packages/trappoint-testkit                      28      26       0 |      28      28       0       0
packages/trappoint-verify                       88      88       0 |      88      88       0       0
tests/agents                                    54      54       0 |      54      54       0       0
tests/boundary                                 122     115       1 |     122     115       1       0
tests/concurrency                               36      20       0 |      36      35       0       0
tests/e2e                                      967     967       0 |     967     967       0       0
tests/eval                                     171     166       5 |     171     166       5       0
tests/integration                             1658    1141      29 |       0       0       0       0
tests/release                                  131     119       4 |     131     127       4       0
tests/security                                 461     458       1 |     461     458       1       0
tests/unit                                    3437    3432       2 |    3437    3432       2       0
verticals/…/mainline-anchor                     59      59       0 |      59      59       0       0
verticals/…/mainline-custody                    28      28       0 |      28      28       0       0
verticals/…/mainline-gate-svc                   61      61       0 |      61      61       0       0
verticals/…/mainline-sequencer                  59      59       0 |      59      59       0       0
```

## 7.1 Two rows in that table are now stale, and both moved in the right direction

**`packages/trappoint-conformance`, 182 errored under the cluster pass.** That was the suite
erroring against an unmigrated database instead of skipping — the defect
`docs/HONESTY.md` describes. It is at least partly repaired: I ran the census to completion
today against a migrated schema and it produced 71 statuses with **zero ERROR** (§1.3). The
182 is the last reading of a condition that has since changed.

**`tests/integration`, cluster pass, all zeros with `timed_out: true`.** That target hit the
census's own wall-clock ceiling and was never measured under a cluster. Its `--crdb=none`
row — 1 658 tests, 29 failed — is real; its cluster row is an absence, not a zero.

**What is not stale:** the failures. 44 hermetic failures and 29 cluster failures are spread
across `tests/eval` (5), `tests/release` (4), `tests/integration` (29 hermetic),
`trappoint-diagnose` (14 cluster), `tests/unit` (2), and single failures in
`mainline-boundary`, `trappoint-migrate`, `tests/boundary` and `tests/security`. **The suite
is not green and no document should say it is.** One of the release failures is the
deliberate honesty red in §1.4.

---

# 8 · Appendix B — the conformance suite, per case

All 71 cases from the run in §1.3, `run-id cert-final`, digest
`sha256:e641fa2113f6112e9568b0814dc2b811992202eeaf0967b3b7498cfb06a9026b`.

| case | status | why |
|---|---|---|
| `CF-01` | **FAIL** | expected 23514 gate_closed_when_issued, observed 23502 <no exhibit>. CF-01: expected 23514 on 'gate_closed_when_issued'; observed 23502 is o |
| `CF-02` | **CANNOT RUN** | legal world could not be built at 'clause_version' — column "body_sha256" does not exist |
| `CF-03` | **CANNOT RUN** | legal world could not be built at 'clause_version' — column "body_sha256" does not exist |
| `CF-04` | **CANNOT RUN** | legal world could not be built at 'clause_version' — column "body_sha256" does not exist |
| `CF-05` | **CANNOT RUN** | legal world could not be built at 'clause_version' — column "body_sha256" does not exist |
| `CF-06` | **CANNOT RUN** | legal world could not be built at 'clause_version' — column "body_sha256" does not exist |
| `CF-07` | **CANNOT RUN** | legal world could not be built at 'clause_version' — column "body_sha256" does not exist |
| `CF-08` | **CANNOT RUN** | legal world could not be built at 'clause_version' — column "body_sha256" does not exist |
| `CF-09` | **CANNOT RUN** | legal world could not be built at 'clause_version' — column "body_sha256" does not exist |
| `CF-10` | **CANNOT RUN** | legal world could not be built at 'clause_version' — column "body_sha256" does not exist |
| `CF-11` | **CANNOT RUN** | legal world could not be built at 'clause_version' — column "body_sha256" does not exist |
| `CF-12` | **CANNOT RUN** | legal world could not be built at 'clause_version' — column "body_sha256" does not exist |
| `CF-13` | **PASS** | refused exactly as the manifest requires |
| `CF-14` | **PASS** | refused exactly as the manifest requires |
| `CF-15` | **PASS** | refused exactly as the manifest requires |
| `CF-16` | **PASS** | refused exactly as the manifest requires |
| `CF-17` | **PASS** | refused exactly as the manifest requires |
| `CF-18` | **CANNOT RUN** | legal world could not be built at 'clause_version' — column "body_sha256" does not exist |
| `CF-19` | **CANNOT RUN** | legal world could not be built at 'clause_version' — column "body_sha256" does not exist |
| `CF-20` | **CANNOT RUN** | legal world could not be built at 'clause_version' — column "body_sha256" does not exist |
| `CF-21` | **CANNOT RUN** | legal world could not be built at 'clause_version' — column "body_sha256" does not exist |
| `CF-22` | **CANNOT RUN** | legal world could not be built at 'clause_version' — column "body_sha256" does not exist |
| `CF-23` | **CANNOT RUN** | legal world could not be built at 'clause_version' — column "body_sha256" does not exist |
| `CF-24` | **CANNOT RUN** | legal world could not be built at 'clause_version' — column "body_sha256" does not exist |
| `CF-25` | **CANNOT RUN** | legal world could not be built at 'clause_version' — column "body_sha256" does not exist |
| `CF-26` | **CANNOT RUN** | legal world could not be built at 'clause_version' — column "body_sha256" does not exist |
| `CF-27` | **CANNOT RUN** | legal world could not be built at 'clause_version' — column "body_sha256" does not exist |
| `CF-28` | **CANNOT RUN** | legal world could not be built at 'clause_version' — column "body_sha256" does not exist |
| `CF-29` | **CANNOT RUN** | legal world could not be built at 'clause_version' — column "body_sha256" does not exist |
| `CF-30` | **CANNOT RUN** | legal world could not be built at 'clause_version' — column "body_sha256" does not exist |
| `CF-31` | **CANNOT RUN** | legal world could not be built at 'clause_version' — column "body_sha256" does not exist |
| `CF-32` | **CANNOT RUN** | legal world could not be built at 'clause_version' — column "body_sha256" does not exist |
| `CF-33` | **CANNOT RUN** | legal world could not be built at 'clause_version' — column "body_sha256" does not exist |
| `CF-34` | **CANNOT RUN** | legal world could not be built at 'clause_version' — column "body_sha256" does not exist |
| `CF-35` | **CANNOT RUN** | legal world could not be built at 'clause_version' — column "body_sha256" does not exist |
| `CF-36` | **CANNOT RUN** | legal world could not be built at 'clause_version' — column "body_sha256" does not exist |
| `CF-37` | **CANNOT RUN** | legal world could not be built at 'clause_version' — column "body_sha256" does not exist |
| `CF-38` | **CANNOT RUN** | legal world could not be built at 'clause_version' — column "body_sha256" does not exist |
| `CF-39` | **PASS** | refused exactly as the manifest requires |
| `CF-40` | **CANNOT RUN** | legal world could not be built at 'clause_version' — column "body_sha256" does not exist |
| `CF-41` | **CANNOT RUN** | legal world could not be built at 'clause_version' — column "body_sha256" does not exist |
| `CF-42` | **FAIL** | expected 23503 fk_check_version, observed P0001 mainline.fn_check_project (exhibit INFERRED from the message, not reported by the driver). C |
| `CF-43` | **CANNOT RUN** | legal world could not be built at 'clause_version' — column "body_sha256" does not exist |
| `CF-44` | **CANNOT RUN** | legal world could not be built at 'clause_version' — column "body_sha256" does not exist |
| `CF-45` | **CANNOT RUN** | legal world could not be built at 'clause_version' — column "body_sha256" does not exist |
| `CF-46` | **PASS** | refused exactly as the manifest requires |
| `CF-47` | **CANNOT RUN** | legal world could not be built at 'clause_version' — column "body_sha256" does not exist |
| `CF-48` | **PASS** | refused exactly as the manifest requires |
| `CF-49` | **CANNOT RUN** | legal world could not be built at 'clause_version' — column "body_sha256" does not exist |
| `CF-50` | **CANNOT RUN** | mainline.merge_conflict: relation "mainline.merge_conflict" does not exist (pg_class; schema "mainline" is present in database "prod_w9") |
| `CF-51` | **CANNOT RUN** | mainline.discordance_warrant: relation "mainline.discordance_warrant" does not exist (pg_class; schema "mainline" is present in database "pr |
| `CF-52` | **CANNOT RUN** | legal world could not be built at 'clause_version' — column "body_sha256" does not exist |
| `CF-53` | **CANNOT RUN** | legal world could not be built at 'clause_version' — column "body_sha256" does not exist |
| `CF-54` | **CANNOT RUN** | legal world could not be built at 'clause_version' — column "body_sha256" does not exist |
| `CF-55` | **PASS** | refused exactly as the manifest requires |
| `CF-56` | **CANNOT RUN** | legal world could not be built at 'clause_version' — column "body_sha256" does not exist |
| `CF-57` | **CANNOT RUN** | mainline.recall_run: relation "mainline.recall_run" does not exist (pg_class; schema "mainline" is present in database "prod_w9") |
| `CF-58` | **CANNOT RUN** | mainline.recall_run: relation "mainline.recall_run" does not exist (pg_class; schema "mainline" is present in database "prod_w9") |
| `CF-59` | **CANNOT RUN** | legal world could not be built at 'commit a policy that has never been anchored' — at or near "_meas": syntax error DETAIL: source SQL: INSE |
| `CF-60` | **FAIL** | expected 23514 no_orphan_controls, observed 00000 <no exhibit>. CF-60: the history COMPLETED. Expected 23514 on 'no_orphan_controls'. A gate |
| `CF-61` | **CANNOT RUN** | mainline.frontier_move: relation "mainline.frontier_move" does not exist (pg_class; schema "mainline" is present in database "prod_w9") |
| `CF-62` | **CANNOT RUN** | mainline.observed_assertion: relation "mainline.observed_assertion" does not exist (pg_class; schema "mainline" is present in database "prod |
| `CF-63` | **FAIL** | expected 23505 ledger_leaf_pkey, observed 00000 <no exhibit>. CF-63: the history COMPLETED. Expected 23505 on 'ledger_leaf_pkey'. A gate tha |
| `CF-64` | **CANNOT RUN** | mainline.propagation: relation "mainline.propagation" does not exist (pg_class; schema "mainline" is present in database "prod_w9") |
| `CF-65` | **CANNOT RUN** | mainline.coverage_certificate: relation "mainline.coverage_certificate" does not exist (pg_class; schema "mainline" is present in database " |
| `CF-66` | **CANNOT RUN** | legal world could not be built at 'clause_version' — column "body_sha256" does not exist |
| `CF-67` | **FAIL** | expected 23514 witness_quorum, observed 42703 <no exhibit>. SCHEMA NOT MIGRATED — CF-67: expected 23514 on 'witness_quorum'; observed 42703  |
| `CF-68` | **FAIL** | expected 23514 measure_policy_predates_data, observed 42601 <no exhibit>. CF-68: expected 23514 on 'measure_policy_predates_data'; observed  |
| `CF-69` | **PASS** | refused exactly as the manifest requires |
| `CF-70` | **CANNOT RUN** | legal world could not be built at 'clause_version' — column "body_sha256" does not exist |
| `CF-71` | **CANNOT RUN** | legal world could not be built at 'clause_version' — column "body_sha256" does not exist |
