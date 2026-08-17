<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# W4 claim ledger — section E, `## What it is built on`

Fragment: `docs/submission/readme-parts/04-platform.md`. **45 lines, 4 181 bytes** — at the
budget, not over it. Dispositions follow plan ruling **R2**: `KEPT` (present in the fragment),
`MOVED` (a named existing file already holds it, with the grep that proves it), `DROPPED` (with
the reason). No destination file was edited. No capture, census, AWS or Terraform command was
run; every number below was read out of the committed JSON.

---

## 1 · Every number printed, and the artefact key it was read from

| printed in the fragment | JSON key read | value |
|---|---|---|
| "Four CockroachDB tools" | `evidence/tool-usage/crdb-features.json#totals.by_kind.tool` | `4` |
| "Twelve AWS services" | `evidence/tool-usage/aws-services.json#totals.by_kind.service` | `12` |
| "six EXERCISED" | `evidence/tool-usage/aws-services.json#totals.by_verdict.EXERCISED` | `6` |
| "five DESIGNED" | `evidence/tool-usage/aws-services.json#totals.by_verdict.DESIGNED` | `5` |
| "one NOT-AVAILABLE" | `evidence/tool-usage/aws-services.json#totals.by_verdict.NOT-AVAILABLE` | `1` |
| "sixteen-question judge pack" | `evidence/deploy/judge-run.json#/questions`, quoted in `crdb-features.json#rows.crdb_managed_mcp.verdict_basis` | `16` |

Every **verdict** printed equals the `verdict` field of its census row, checked one by one:
`crdb_vector_index` EXERCISED, `crdb_managed_mcp` EXERCISED, `crdb_cloud_ccloud` EXERCISED,
`crdb_agent_skills` DESIGNED; `aws_bedrock_runtime`, `aws_bedrock_embeddings`, `aws_lambda`,
`aws_cloudwatch`, `aws_iam`, `aws_ssm_parameter_store` EXERCISED; `aws_s3_object_lock`,
`aws_kms`, `aws_cloudtrail`, `aws_cloudfront`, `aws_eventbridge` DESIGNED;
`aws_bedrock_rerank` NOT-AVAILABLE. **No verdict was moved by this worker.**

---

## 2 · Prose / JSON relationships found while reading

**(a) The criterion's four tools and the census's four `tool` rows are not the same four —
recorded, because a reader who opens the JSON will notice.** `docs/TOOL-USAGE.md:177–182` lists
the criterion's order — distributed vector index, MCP Server, `ccloud` CLI, Agent Skills — and
cites `totals.by_kind.tool` = `4` beside it at `docs/TOOL-USAGE.md:11`. The census's four rows
with `"kind": "tool"` are `crdb_database`, `crdb_cloud_ccloud`, `crdb_managed_mcp`,
`crdb_agent_skills`; `crdb_vector_index` carries `"kind": "feature"`. **The count `4` is
correct on either reading and no verdict differs**, so nothing is a numeric disagreement — but
the two sets differ by one member, so the fragment states plainly that the census files the
database as a fourth tool and the vector index as an engine feature, and that the table follows
the criterion's list. **The JSON is authoritative and is what the fragment cites.**

**(b) "Thirteen rows below, twelve services."** `docs/TOOL-USAGE.md:1042` renders thirteen table
rows because the `cohere.embed-v4` refusal gets its own line as a measured finding.
`aws-services.json#totals.rows` is `12`. The fragment prints **twelve**, the JSON's figure.

**(c) The submission gate counts differently, and both figures stand.**
`scripts/submission/check_submission_ready.py` reports `10` AWS services and `5` marked as
having run, against the census's `12` and `6`, because the gate holds a fixed ten-name table and
counts *Amazon Bedrock* once where the census emits two Bedrock rows.
`docs/TOOL-USAGE.md:1048–1083` reconciles this at length. The fragment prints the census
figures only and does not repeat the reconciliation. `DROPPED` — see §3.

No case was found where a number in `docs/TOOL-USAGE.md` contradicts its cited JSON.

---

## 3 · Claims in today's `README.md` that touch this section

| claim (current `README.md`) | disposition | note / grep |
|---|---|---|
| Inference on Bedrock `ap-southeast-2` (Sydney); database `aws-ap-southeast-1` (Singapore); `ap-southeast-2` is Advanced-tier only on CockroachDB Cloud; no end-to-end Australian residency (`README.md:290–293`) | **KEPT** | verbatim in substance, mandated by plan **R14** |
| The cross-region hop is unmeasured under load (`README.md:294`) | **KEPT** | same sentence |
| "every timing in the demo is a local timing — a single-node CockroachDB in Docker on one laptop" (`README.md:294–295`) | **MOVED** | `docs/HONESTY.md:1169` — *"A stopwatch on the demo is measuring Docker on a laptop, not a managed cluster across a …"*. It is also section H's subject (W6), not section E's. |
| CloudFront blocked by an account verification hold, `AccessDenied` string verbatim, `RequestID` in `docs/deploy/RUNBOOK.md` Appendix A (`README.md:305–309`) | **KEPT** | fragment quotes the string and cites the runbook; source `docs/deploy/RUNBOOK.md:1541–1545` |
| "Which AWS row is EXERCISED and which is still DESIGNED is not this page's to assert" — census pointer (`README.md:309–313`) | **KEPT** | the fragment asserts nothing the census does not; both counts carry `[src: …]` pointers into `aws-services.json` |
| `python scripts/submission/capture_tool_evidence.py --check` as the re-derivation command (`README.md:312`) | **MOVED** | `docs/TOOL-USAGE.md:23` and `docs/TOOL-USAGE.md:1715` both carry the command verbatim. The fragment points at `scripts/aws/verify_evidence.py` instead, per the brief, because that one is the stdlib-only, no-credential, no-network check of the EXERCISED artefacts. |
| `evidence/deploy/aws-live.json` four live calls with AWS request ids — `sts:GetCallerIdentity`, `bedrock:ListFoundationModels`, Titan v2 embedding 1024-d L2 norm `1.0`, Claude Haiku 4.5 `Converse` `end_turn`, `calls_failed: []`, probe under one cent (`README.md:298–302`) | **MOVED** | `docs/TOOL-USAGE.md:1174` (the four-call probe), `:1184` (`bedrock:ListFoundationModels`, `64` models), `:1241` (request id `b4d826e9-…`, `1024` dimensions, L2 norm `1.0`) |
| `evidence/deploy/LIVE.md` and `evidence/demo/live-beats.json` — eleven requests over the internet, `target_is_local_emulator: false` (`README.md:302–304`) | **MOVED** | `docs/deploy/JUDGE-PACK.md:48` — *"eleven requests, `failures: []`, `target_is_local_emulator: false`"*. It is also section C's material (W2), not section E's. |
| The struck-through *"Bedrock genuinely executes, and nothing else on AWS does"* and its `SUPERSEDED` annotation (`README.md:296–297`) | **DROPPED** | Plan **R10** collects superseded/strikethrough archaeology into the single `Corrections` block at the end of §I (W6). The *current* state it was superseded by — six EXERCISED AWS rows including Lambda — is KEPT in the fragment, so the correction loses its interruption and not its content. |
| The gate-vs-census AWS count reconciliation (`10`/`5` against `12`/`6`) — *not* in today's `README.md`, listed here only because §2(c) raises it | **DROPPED** | It lives in full at `docs/TOOL-USAGE.md:1048–1083` and, word for word, at `docs/submission/RULES-MATRIX.md` §1. Section E prints the census figures and does not re-open the arithmetic. |

---

## 4 · Material available to this section and deliberately not printed

Each is `DROPPED` for budget, and each already has a home that this worker did not edit.

* **The CockroachDB half's own verdict split** — `12` EXERCISED and `2` DESIGNED across
  `14` rows [src: `evidence/tool-usage/crdb-features.json#totals.by_verdict`]. The fragment
  prints the four-tool table rather than the fourteen-row census.
  Home: `docs/TOOL-USAGE.md:83–88`.
* **`CHANGEFEED` is the CockroachDB half's other DESIGNED row** — `SHOW CHANGEFEED JOBS`
  answers and reports zero jobs, and `kv.rangefeed.enabled` reads false on the pinned node.
  Home: `evidence/tool-usage/crdb-features.json#rows.crdb_changefeed`. **Not printed**, which
  means the word *changefeed* never appears in the fragment and needs no gloss under **R4**.
* **`file_count` for every row** (for example `355` for Bedrock inference, `448` for the
  database). Home: `docs/TOOL-USAGE.md` Part 1 and Part 2 tables.
* **The `ccloud` `0.6.12` headless-auth limitation** and the Basic-tier `spend_limit` of
  `2500`. Home: `evidence/ccloud/README.md:37`,
  `evidence/tool-usage/crdb-features.json#rows.crdb_cloud_ccloud.how`.
* **The managed-MCP run's own `DIVERGED — KNOWN GAP` verdict**, `15` of `16` PASS, and
  `credential_publishable: false`. Home:
  `evidence/tool-usage/crdb-features.json#rows.crdb_managed_mcp.verdict_basis`,
  `docs/TOOL-USAGE.md:606+`. The fragment says "read verbs only" and claims no pass rate.
* **The measured CockroachDB findings** (`has_function_privilege()`, `SHOW GRANTS` signatures,
  the optimizer not choosing the vector index at demo scale, `crdb_internal` restricted on
  Basic, the 20 000 schema-object cap, `convert_from()`, `gc.ttlseconds` 4500). These are
  section F's subject (W5) and are not duplicated here.
* **The Lambda Function URL's `authorization_type = "NONE"`, the account concurrency ceiling of
  `10`, and the cost guard.** Home:
  `evidence/tool-usage/aws-services.json#rows.aws_lambda.how`, `docs/TOOL-USAGE.md` Part 2.

---

## 5 · Constraints this fragment was checked against

* **45 lines / 4 181 bytes** — at the §2 budget for section E.
* **No sentence over 35 words**, measured per table cell and per prose sentence with code spans
  collapsed.
* **`EXERCISED` / `DESIGNED` / `NOT-AVAILABLE` are defined in the first paragraph**, before any
  table uses them. `vector index` is glossed in twelve words at first use. `C-SPANN` appears
  **once, inside the platform table only** (**R4**). `changefeed`, `canonicalisation`,
  `defeater`, `MUS`, `archival bond` and `fixity` do not appear at all.
* **`MCP`, `IAM`, `KMS` and `CLI` are expanded at first use.**
* **Zero hits** from `mainline_boundary.greps.load_claim_rules()` (the `ARCHITECTURE.md` §11.7
  must-not-claim patterns) and **zero hits** from the nine `SUB-01`…`SUB-09` patterns in
  `scripts/submission/check_submission_prose.py`, both run against the fragment text alone.
  Neither `README.md` nor any file outside this worker's two paths was touched.
* **No banned marketing word** appears.
* Relative links used — `docs/TOOL-USAGE.md`, `docs/deploy/RUNBOOK.md`,
  `evidence/deploy/APPLIED.md` — all resolve from the repository root, which is where
  `README.md` sits.
