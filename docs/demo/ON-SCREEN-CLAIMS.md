<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# ON-SCREEN CLAIMS — every name the overlay may carry, and every name it may not

**Read this while the overlay is being written, not after.** The Devpost brief asks us to
*"name the specific AWS services and CockroachDB features on screen (text overlay or slide)
so judges can confirm them quickly"* — **confirm** is the operative word. A judge who pauses
the film on the last minute and opens the repository must find every name here with a
verdict, the file that does the work, and the artefact that records it having run.

**One rule governs the whole page.** A name may appear on the overlay if and only if its
census row reads **EXERCISED**. `DESIGNED` means *written and never run end to end*;
`NOT-AVAILABLE` means *checked on this platform and absent*. Both are honest verdicts and
neither is a credit. Putting a DESIGNED name on a screen headed *"what we used"* converts an
honest census into an overclaim in one frame, and it is the cheapest way this submission
could lose the Functionality axis.

**The census is the authority, not this page.** Re-derive before the take:

```bash
.venv/Scripts/python.exe scripts/submission/capture_tool_evidence.py --check   # must exit 0
```

It reads the tree, opens no socket and holds no credential. Counts move whenever anybody adds
a file, so a green here is a green about the tree it was run against and no other.

---

## AWS — the six names that may appear

Verdicts from `evidence/tool-usage/aws-services.json`, regenerated `2026-08-15`:
**6 EXERCISED · 5 DESIGNED · 1 NOT-AVAILABLE** over `12` rows.

| may appear as | verdict | the file that does the work | the artefact that records it running |
|---|---|---|---|
| **Amazon Bedrock** — Claude inference (`au.*` inference profiles, `ap-southeast-2`) | EXERCISED | `packages/mainline-agentkit/src/mainline_agentkit/transport.py:273` — refuses any model id that is not an `au.*` profile | `evidence/deploy/aws-live.json` (`Converse` `200`, **AWS request id `3c7a283c-9f67-4d98-aa8f-26490d54d32d`**), `evidence/aws/probe/raw-haiku-converse.json`, `evidence/aws/agent/live-run.json` |
| **Amazon Bedrock** — Titan v2 embeddings | EXERCISED | `verticals/mainline/packages/mainline-recall-agent/src/mainline_recall_agent/providers/bedrock_titan.py:55` | `evidence/aws/probe/raw-titan-invoke.json` (**request id `6dcdcdf0-38d3-453f-a476-fa69b2d87863`**, `1024`-d), `evidence/aws/embeddings/manifest.json`, `evidence/deploy/aws-live.json` |
| **AWS Lambda** — the `/v1/*` demo API | EXERCISED | `infra/modules/demo-api/main.tf:432` (the authorisation decision); the function opens at `:326` | `evidence/deploy/APPLIED.md` (`terraform apply` — `24 created, 0 changed, 0 destroyed`), `evidence/deploy/live-health.json` (`ok true`, `deploy_chain 271/271`), `evidence/deploy/live-gate-run.json` (four beats, `PROVEN`), `evidence/deploy/judge-walk.json` |
| **AWS Systems Manager Parameter Store** — the DSN | EXERCISED | `infra/modules/demo-api/main.tf:280` (the grant); the signed call is `verticals/mainline/apps/demo-api/src/mainline_demo_api/db.py:214` | `evidence/deploy/APPLIED.md` with the parameter **absent** (`reason="dsn_unset"`, `ParameterNotFound`) and `evidence/deploy/live-health.json` with it **present** (`ok true`). The refusal is what makes the success checkable |
| **AWS IAM** — the execution role | EXERCISED *(the allow half only)* | `infra/modules/demo-api/main.tf:260` | `evidence/deploy/APPLIED.md` — the role, its inline `dsn_access` policy and the managed attachment are 3 of the 24 created; the role was **assumed** and its one grant **used**, which is what `evidence/deploy/live-health.json` proves |
| **Amazon CloudWatch** | EXERCISED *(metrics read; alarms applied, never fired)* | `scripts/aws/cloudwatch_evidence.py:299` — the guard that refuses any call outside a six-item read-only allow-list | `evidence/aws/cloudwatch/bedrock-metrics.json` (110 `GetMetricStatistics` calls; AWS's own counters for our `ModelId`), `evidence/aws/cloudwatch/reconciliation.json` |

**Say these two out loud if the overlay compresses them, because compressing them creates a
claim we do not hold.**

* **IAM is EXERCISED on its allow half only.** What ran is the execution role's single
  `ssm:GetParameter` grant. The **deny-first** policies this project is proudest of —
  `s3:DeleteObjectVersion` denied to the checkpoint writer, `infra/modules/evidence-store/main.tf:145`
  — are **unapplied**, asserted by Rego against plan fixtures and nowhere else.
* **CloudWatch alarms exist and have never fired.** Seven alarms and a dashboard were created
  by the apply. **No artefact records any of them transitioning to `ALARM`.** An alarm that
  has never fired has demonstrated its existence and nothing about its threshold.

---

## CockroachDB — the twelve names that may appear

Verdicts from `evidence/tool-usage/crdb-features.json`: **12 EXERCISED · 2 DESIGNED** over
`14` rows — `4` tools, `10` engine features, counted separately because counting a feature as
a tool to clear a bar is the arithmetic this repository exists to refuse.

| may appear as | the file that does the work | the artefact that records it running |
|---|---|---|
| **CockroachDB v26.2.5** | `compose.yaml:31` | `evidence/gate-refusal/proof-20260810T004200Z.json#cluster.version`; on the deployment, `evidence/deploy/live-health.json` (`CockroachDB CCL v26.2.5`) |
| **`SERIALIZABLE` isolation** | `packages/trappoint-model/src/trappoint_model/cluster.py:222` | `evidence/deploy/live-gate-run.json` → `data.transaction`: `isolation SERIALIZABLE`, `single_transaction true`, `disposition rolled_back` — **on the deployed Cloud cluster**, not a laptop |
| **PL/pgSQL triggers and functions** | `verticals/mainline/db/migrations/0115_fn_permit_merge_gate.sql:77` (the `RAISE`) | `evidence/deploy/live-gate-run.json` → the `projection_drift_attack` beat, `P0001` from `mainline.fn_permit_merge_gate`; also `evidence/gate-refusal/proof-20260810T004200Z.json` |
| **Named `CHECK` constraints** | `verticals/mainline/db/migrations/0050_permit.sql:114` | `evidence/deploy/live-gate-run.json` → the `merge` beat, `23514` **`gate_closed_when_issued`** — the constraint *name* travelling intact from the node into a JSON body |
| **C-SPANN vector index** (`VECTOR INDEX`, prefix-constrained ANN) | `verticals/mainline/db/migrations/0031_clause_embedding.sql:149` | `evidence/aws/ann/ann-proof.json` + `evidence/aws/ann/explain-hinted.txt` — the plan naming `clause_embedding@ce_ann` with both prefix columns bound. *That runs against the ANN evidence database, whose parent table is a stub: it demonstrates the index, never the gate* |
| **`AS OF SYSTEM TIME`** | `packages/trappoint-conformance/cases/cf46_time_travel_cannot_reach.py:106` | **reproducible, not committed** — measured on the pinned local node; a far-past read is REFUSED with `XXUUU`. No artefact under `evidence/` records it |
| **Follower reads** (`follower_read_timestamp()`) | `verticals/mainline/db/migrations/0180c_role_agent_patroller.sql:37` | **reproducible, not committed** |
| **Row-level security** (`FORCE ROW LEVEL SECURITY`) | `verticals/mainline/db/migrations/0181a_permit_rls_force.sql:54` | **reproducible, not committed** |
| **`SHOW CREATE` self-attestation** | `packages/trappoint-migrate/src/trappoint_migrate/attest.py:243` | **reproducible, not committed** |
| **`crdb_internal`** (used by us, forbidden to the audit identity) | `packages/mainline-mcp/src/mainline_mcp/limits.py:75` | **reproducible, not committed** |
| **CockroachDB Cloud + the `ccloud` CLI** | `evidence/ccloud/README.md:37` | `evidence/ccloud/cluster-list.txt`; the demo world lives on that cluster — `evidence/deploy/cloud-chain.json`, `evidence/deploy/cloud-seed.json` |
| **CockroachDB Managed MCP Server** | `packages/mainline-mcp/src/mainline_mcp/limits.py:45` | `evidence/deploy/judge-run.json` — a live session, `15` of `16` pack questions PASS, **and the run's own verdict is `DIVERGED — KNOWN GAP`** |

**"Reproducible, not committed" is not a weaker way of saying EXERCISED — it is a different
sentence and the overlay must not blur it.** Five features were measured on a pinned local
node and no artefact under `evidence/` holds the transcript. They are EXERCISED because the
measurement was taken and the census records the basis; they are **not** things a judge can
open a file to see. If the overlay wants a name a judge can verify in ten seconds, prefer the
four in the gate-run row above, whose evidence is one committed JSON.

---

## The names that MAY NOT appear

| name | verdict | why, in one line |
|---|---|---|
| **Amazon S3 + Object Lock** (the evidence store) | DESIGNED | No bucket applied. The S3 object-lock comparison is one of the **seven** custody checks that did not run (`qa/test-state.json`). *One S3 bucket does exist — the Terraform **state** bucket in `evidence/deploy/APPLIED.md` — with no Object Lock and no checkpoint in it; it promotes nothing* |
| **AWS KMS** | DESIGNED | The `ECC_NIST_P256` signer is unit-tested against an injected client. The live signature check is another of the seven that did not run |
| **AWS CloudTrail** | DESIGNED | Written, never applied. No trail exists in the account |
| **Amazon CloudFront + OAC** | DESIGNED **and unapplyable** | `403 AccessDenied: Your account must be verified before you can add new CloudFront resources.` — `RequestID 3e63e30d-8c5b-441b-a01b-b70085eba504`, reproduced from a bare `aws cloudfront create-distribution` by an identity holding `AdministratorAccess`. Only AWS Support can lift it (`docs/deploy/RUNBOOK.md` Appendix A) |
| **Amazon EventBridge** | DESIGNED | There is no `aws_cloudwatch_event_*` resource anywhere under `infra/`; the schedule is a container entrypoint |
| **Amazon Bedrock Rerank** | NOT-AVAILABLE | Not offered in `ap-southeast-2` (`evidence/aws/probe/model-availability.json`). Listed rather than dropped, because a services list that omits what you checked is a list nobody can audit |
| **CockroachDB CHANGEFEED / CDC** | DESIGNED | `SHOW CHANGEFEED JOBS` reports `0`, and `kv.rangefeed.enabled` reads **false** on the pinned node — not merely unstarted, not currently startable |
| **CockroachDB Agent Skills** | DESIGNED | Two skills are authored and ship an executable assertion script each; **neither script's run is captured under `evidence/`**. The sentence that is true is *"authored and shipped"* — never *"demonstrated"* |

**If the founder wants CloudFront or the evidence store on screen anyway**, there is one
honest framing and it is a strong one: put them under a heading that says **DESIGNED, NOT
DEPLOYED**, with the `AccessDenied` string visible. A slide that separates *what ran* from
*what is written* is more convincing than one that does not, and it is the reason this
project's census has three verdict values instead of two.

---

## Sentences, not just names

Four claims are worth more than any service name, and each has a wording that holds and a
wording that does not.

* **The strongest beat we own.** *"Somebody forces the counter the gate reads to zero, and the
  gate refuses anyway — because it re-derives from ancestry instead of trusting a number."*
  `P0001`, `mainline.fn_permit_merge_gate`, in `evidence/deploy/live-gate-run.json`, off the
  deployed URL. **Do not** say the counter was "hacked" or that the attack came from outside:
  it was set out of band inside the same transaction, by the demo, on purpose.
* **Severity `4` and `blood_major` are PROJECTED, and the projector is named on the same
  breath.** The seed supplies `0` and `routine`; `fn_check_project` overwrites both from
  `mainline.clause_blame_current`. *"Nobody typed the four"* is only true because the
  projection ran, and a `4` on screen with no provenance beside it is a number somebody could
  have typed.
* **The transaction leaves nothing behind.** `disposition rolled_back`, `persisted false`,
  and the row counts before and after are `identical` — all three in
  `evidence/deploy/live-gate-run.json`. That is why there is no reset button, and the absence
  of one is a claim we make rather than a gap.
* **Residency, which is the easiest sentence to get wrong.** Inference is in Sydney
  (`ap-southeast-2`) and the database in Singapore (`aws-ap-southeast-1`). **Any claim of
  end-to-end Australian data residency is false** and `scripts/demo/claim_hygiene.py`
  MNC-02 fails the build on it.

---

## Discrepancies filed, not smoothed

Three sentences elsewhere in the repository are stale in the **underclaiming** direction and
were deliberately **not** edited, because each is carried word-for-word by documents this
worker does not own and correcting one copy alone would break the only mechanism keeping the
copies equal. They are recorded here so the next owner corrects them together, and so nobody
reads the omission as an oversight.

1. **The owed Cloud four-beat run has been taken.** `docs/submission/DEVPOST.md` item (11)
   carries a blockquote — *"The four-beat run through the HTTP handler has NOT been recorded
   against Cloud … OWED: … `--out evidence/deploy/cloud-gate-run.json`"* — which
   `docs/STATE-OF-THE-BUILD.md`, `docs/HONESTY.md`, `docs/CI-STATE.md` and
   `docs/submission/JUDGING-AXES.md` carry verbatim, five documents deep, precisely so they
   cannot drift. It **has** been recorded, under a different filename:
   `evidence/deploy/live-gate-run.json`, verdict `PROVEN`, through the public Function URL.
   DEVPOST now carries an annotation **beside** the block. **Owed: the same correction in all
   five, in one change.**
2. **`docs/TOOL-USAGE.md` and `docs/submission/RULES-MATRIX.md` §1 share a paragraph**
   reconciling the submission gate's *"2 AWS service(s) marked as having run"* against *"this
   page's `3` EXERCISED rows"*. The census now has **6**. The paragraph is declared identical
   in both files; TOOL-USAGE carries an annotation beside it. **Owed: re-derive both figures
   and correct the two copies together.**
3. **`docs/submission/SUBMISSION.json` still holds `UNRESOLVED` in `demo_url`** while an
   origin exists and answers. That file is the **single write point** for the value and is
   not this worker's to write — and the distinction is real, not pedantic: a URL existing and
   a URL being *submitted* are different facts. **Owed: its owner writes it, and
   `python scripts/submission/check_submission_ready.py` is what says whether it is done.**

---

## Before the take — the four commands

```bash
.venv/Scripts/python.exe scripts/submission/capture_tool_evidence.py --check  # census fresh, anchors on subject
.venv/Scripts/python.exe scripts/aws/verify_evidence.py                       # every EXERCISED row's artefact exists
.venv/Scripts/python.exe scripts/demo/claim_hygiene.py                        # no sentence we may not say
.venv/Scripts/python.exe scripts/demo/demo_ready.py                           # may I roll camera?
```

If the first exits non-zero, **the overlay is not safe to film**: either a count has moved
under it or a citation now points somewhere that does not support it. Fix the artefact, never
the sentence.

Related: [`docs/TOOL-USAGE.md`](../TOOL-USAGE.md) — the same verdicts at length, with every
`how`. [`docs/HONESTY.md`](../HONESTY.md) — everything this build gets wrong, counted.
[`evidence/tool-usage/README.md`](../../evidence/tool-usage/README.md) — how the censuses are
built and why they carry no timestamp.
