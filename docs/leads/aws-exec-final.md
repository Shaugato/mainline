<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# AWS execution — turning "Bedrock is reachable" into "AWS powers this product"

**Lead:** AWS-EXECUTION LEAD · **Written:** 2026-08-11 · **Branch:** `master` at `ed4a12f`
**Every measurement below was taken by me on this workstation today, with the command shown.**
Nothing in this document is inherited from a brief, a previous wave, or a document already in
the tree. Where a repository document disagrees with a measurement here, the measurement wins
and §7 names the file that has to change.

---

## 1. What I measured before deciding anything

### 1.1 Bedrock, `ap-southeast-2`, profile `mainline-dev`

`aws sts get-caller-identity` → `arn:aws:iam::022950218246:user/mainline-dev`.

| call | result |
|---|---|
| `invoke_model amazon.titan-embed-text-v2:0` | **HTTP 200**, `len(embedding) == 1024`, `inputTextTokenCount 8`, latency 361 ms, `RequestId cf15c64d-85e3-45da-8746-d51a3404582e` |
| `converse au.anthropic.claude-haiku-4-5-20251001-v1:0` | **HTTP 200**, text `MAINLINE gate online`, `usage {inputTokens 16, outputTokens 8}`, `stopReason end_turn` |
| `invoke_model cohere.embed-v4:0` | **ValidationException** — *"Invocation of model ID cohere.embed-v4:0 with on-demand throughput isn't supported. Retry your request with the ID or ARN of an inference profile that contains this model."* |
| `invoke_model global.cohere.embed-v4:0` | **HTTP 200**, 1024-d |
| `invoke_model cohere.embed-english-v3` | **HTTP 200**, 1024-d, in-region on-demand |

The `ValidationException: Operation not allowed` recorded in `docs/STATE-OF-THE-BUILD.md` §3.3 no
longer reproduces on any of the three model families it names. **§3.3 is stale and false.**

**The Cohere finding is a residency finding, not a benchmark footnote.** The only Bedrock
identifier in this account that can serve `embed-v4` is `global.cohere.embed-v4:0`. The `global.`
prefix is a cross-region routing profile: it is the exact opposite of the guarantee
`bedrock_titan.py::REQUIRED_REGION` and `ARCHITECTURE §10.1` make about Australian safety
narratives never leaving `ap-southeast-2`. ADR 0002 left "benchmark Cohere against Titan" open.
The answer is now partly structural and must be reported that way: on this account, at v4, the
choice is *residency* versus *that model*, and the in-region alternative is `cohere.embed-english-v3`.

### 1.2 CloudWatch already corroborates every call, for free

```
aws cloudwatch list-metrics --namespace AWS/Bedrock --region ap-southeast-2
  → Invocations / InputTokenCount / OutputTokenCount / InvocationLatency /
    EstimatedTPMQuotaUsage, dimensioned by ModelId, for
    amazon.titan-embed-text-v2:0 and au.anthropic.claude-haiku-4-5-20251001-v1:0
```

`get_metric_statistics`, 3-hour window ending 2026-08-11T06:5xZ, `Period 3600`, `Sum`:

| ModelId | Invocations | InputTokenCount |
|---|---|---|
| `amazon.titan-embed-text-v2:0` | **5.0** | **33.0** |
| `au.anthropic.claude-haiku-4-5-20251001-v1:0` | **4.0** | **63.0** |

This is the single most valuable thing I found. It is an **AWS-side attestation, written by AWS,
that our code invoked these models** — obtainable read-only, at zero cost, needing no deployment
and no account-settings change. Every token count this fleet publishes will be reconciled against
it. `get-model-invocation-logging-configuration` returns empty; enabling it is an account-settings
change and is **out of scope for every worker** (see §6).

### 1.3 The database: Cloud is the target, local Docker is not

- `docker ps` → `failed to connect to the docker API at npipe:////./pipe/dockerDesktopLinuxEngine`.
  I launched Docker Desktop and re-ran `docker compose up -d crdb` twice; the engine did not come
  up reliably and no `crdb` container exists. **The local node is not available and must not be a
  precondition for any AWS proof.**
- Cloud `mainline-dev` (SERVERLESS Basic, `aws-ap-southeast-1`) is live: `CockroachDB CCL v26.2.5`,
  databases `defaultdb, mainline_demo, postgres, system, w_deploy_cloud_probe`.
- `mainline_demo` carries 72 `mainline` tables, 12 `mainline_meas`, 4 `trappoint`.
- `SHOW CREATE TABLE mainline.clause_embedding` on Cloud returns the real thing:

```
embedding VECTOR(1024) NOT NULL,
VECTOR INDEX ce_ann (site_id, activity_root, embedding vector_cosine_ops),
FAMILY f_meta (...), FAMILY f_vec (embedding)
CONSTRAINT fk_version FOREIGN KEY (clause_uuid, commit_id) REFERENCES mainline.clause_version
WITH (schema_locked = true) LOCALITY REGIONAL BY TABLE IN PRIMARY REGION
```

**It has 0 rows.** `mainline.clause_version` has 1 row and carries triggers `append_only`,
`z_delta_witness_required`, `clause_version_guard`. So the production table is ready to receive
Bedrock vectors, but bulk-loading a corpus through it means fighting the gate — which is the gate
working correctly. §3 says what to do about that.

### 1.4 The vectors in this repository today are 8-dimensional and fake

`tests/integration/algorithms/candidates/_w7_support.py` creates
`embedding VECTOR(8)` and fills it from `fixture_embedding(text, dim=8)`, whose own docstring says
*"Not a model output and never claimed to be one."* Every ANN assertion in the tree rests on that.
**The 1024-d real path has never executed anywhere.** That is the gap this fleet closes.

### 1.5 The corpus is hermetic and already built

- `trappoint_recall.corpora.synthetic.generate()` runs clean and yields **96 fatality reports,
  24 CSB reports, 60 AU alerts, 901 Part-50 lines** — with text.
- Committed goldsets: `g4_retro.queries.jsonl` **96 queries**, `g4_retro.qrels.jsonl` **982
  judgements**, `gs0/queries.jsonl` **396**, `gs0/qrels.jsonl` **981**, `g1_citations` 248,
  `g2_codes` 3 995, `g3_adjudicated` 49; `build_report.json` pins
  `corpus_commit sha256:719c31fa…0b317`.
- The MAINLINE clause corpus: `answer-key/clause.jsonl` **893**, `clause_revision.jsonl` **2 597**
  (metadata only — prose comes from `mainline_corpus.docx.bodies`).
- The goldset qrels reference MSHA `doc_id`s whose source PDFs are deliberately **not committed**
  (`scripts/recall/fetch_corpora.py` explains why). The document text a retriever must embed
  therefore comes from `synthetic.generate()`, and every artefact must stamp `SYNTHETIC`.

### 1.6 The evaluation harness runs against `NullBackend` on purpose

`tests/eval/recall/test_g4alpha_gates.py` scores `NullBackend`; five gates are RED;
`tests/eval/recall/g4alpha_lane.py` compares that colour to `g4alpha_expected.json` (which says
`RED`) and is therefore **green**. The lane is designed so that a working retriever makes the lane
**fail** until a human flips the expectation in a reviewable commit. That is a feature. No worker
in this fleet may edit `g4alpha_expected.json`, the gate tests, or the gate floors.

### 1.7 Cost

Titan v2 is ~USD 0.00002 / 1 000 input tokens. A full pass — 180 synthetic documents + 96 retro
query narratives + 893 clause bodies ≈ 350 000 tokens — is **≈ USD 0.007**. Cohere v4 at
~0.00012 / 1 000 is **≈ USD 0.04** for the same corpus. Haiku for the agent lane is single-digit
cents. Total fleet spend is budgeted at **under USD 0.25, one-time**, against a ceiling of
USD 5/month. Every worker writes its own token count and every count is reconciled against
CloudWatch (§1.2).

### 1.8 Toolchain facts workers will otherwise rediscover the hard way

- Python: `D:/CoackroachDBxAWS/mainline/.venv/Scripts/python.exe`. `boto3 1.43.66`,
  `numpy 2.5.1`, `psycopg 3.3.4` are present. `reuse`, `uv`, `just` are **not** installed locally.
- `PYTHONPATH` separator is `;`. Package sources live at `packages/<name>/src`.
- `out/` is gitignored — large vector blobs go there, manifests go under `evidence/`.
- `REUSE.toml` already annotates `evidence/**` as CC-BY-4.0. **Do not write `.license` sidecars
  under `evidence/`**; they are redundant and add review noise.
- `CREATE SEQUENCE` / `nextval` / `SERIAL` / `unique_rowid()` are banned. `FAMILY` is reserved.
- Cloud needs a `40001 RETRY_SERIALIZABLE` retry loop that a single-node Docker never triggers.

---

## 2. Strategy — one query is the deliverable

The hackathon asks for ≥1 AWS service. The weak answer is "we call Bedrock". The answer this
fleet ships is:

> **The vectors CockroachDB's C-SPANN index searches were produced by Amazon Bedrock, and here is
> the hinted, prefix-constrained ANN query — with its `EXPLAIN` naming `clause_embedding@ce_ann` —
> that recovered the true precursor of a fatality from a permit written before it happened.**

Everything else in this plan exists to make that sentence auditable: the probe proves the calls
happened, the embedder proves the vectors are Titan's, the loader proves they reached CockroachDB
Cloud, the ANN proof is the sentence itself, the harness turns it into honest numbers with
intervals, CloudWatch corroborates from outside the repository, and the census, docs and README
stop the tree from claiming otherwise.

**Three refusals hold the fleet up.**

1. **No number without its interval and its artefact.** `scripts/recall/no_bare_point_estimates.py`
   is enforced on `docs/` and `README.md`. Every recall figure ships as a `Measurement` with a
   Wilson interval and an `n`.
2. **No green bought by weakening a ratchet.** The g4alpha gates stay red if the numbers say red,
   and the numbers say *why*. `g4alpha_expected.json`, gate floors, `docs/HONESTY.md`'s
   unfavourable findings and `docs/CI-STATE.md` are not editable by this fleet except where §7
   names a specific stale sentence.
3. **No claim beyond the evidence.** The corpus is synthetic; every artefact says `SYNTHETIC`.
   The parent-table stub in the evidence database is a stub; the artefact says so, in the same
   file as the result.

---

## 3. The database decision

Three surfaces, deliberately, because each proves something the others cannot.

- **`mainline_demo.mainline.clause_embedding` (Cloud, production schema, full triggers and FK).**
  One row: a real Titan 1024-d vector for the one existing `clause_version`. This proves *the
  production table, under its constraints, accepts a Bedrock vector.* Small claim, unimpeachable.
- **`mainline_ann_evidence` (Cloud, new database, DDL copied verbatim from
  `verticals/mainline/db/migrations/0031_clause_embedding.sql` with a minimal parent stub).**
  ~1 200 real Titan vectors. This is where the ANN proof and the recall harness run, because it is
  the only way to get corpus-scale rows behind the real `ce_ann` index without forging writes past
  a gate whose whole purpose is to refuse them. The stub is disclosed in every artefact it touches.
- **Local Docker: optional, never required.** If a worker gets the engine up, it re-runs its proof
  locally and records both. If not, it records `local_node: unavailable` with the exact docker
  error. No worker blocks on it.

Cloud writes go through a `40001 RETRY_SERIALIZABLE` retry loop with jittered backoff, and the
loop's trip count is recorded — a retry that never fires is not evidence that the loop works.

---

## 4. Sequencing

```
layer 0   W1 probe + shared client contract
layer 1   W2 Titan embeddings            (needs W1)
layer 2   W3 load into CockroachDB Cloud (needs W2)
layer 3   W4 the ANN proof               (needs W3)
          W5 recall harness on real vectors (needs W3)
layer 1'  W6 Cohere benchmark            (needs W1, W2)
          W7 live agent cassettes        (needs W1)
layer 4   W8 CloudWatch + cost ledger    (needs W2, W6, W7)
layer 5   W9 doc corrections             (needs W1, W4, W8)
          W10 census, verifier, judge README (needs everything)
```

W1 owns `scripts/aws/_common.py`. Its public API is specified verbatim in W1's brief **and
repeated in every dependent brief**, so a dependent can begin against a known signature.

---

## 5. The ten workers

| # | id | owns (summary) | done when |
|---|---|---|---|
| 1 | `aws-probe` | `scripts/aws/_common.py`, `probe_bedrock.py`, `evidence/aws/probe/*` | probe JSON records 200s with request ids for Titan + Haiku, and the Cohere refusal verbatim |
| 2 | `titan-embed` | `scripts/aws/embed_corpus.py`, `evidence/aws/embeddings/*` | ≥1 200 vectors in `out/aws/`, manifest with per-vector sha256 and a token ledger |
| 3 | `cloud-load` | `scripts/aws/load_vectors.py`, `evidence/aws/load/*`, evidence DDL | Cloud row counts match the manifest; the 40001 loop's trip count is recorded |
| 4 | `ann-proof` | `scripts/aws/ann_proof.py`, `evidence/aws/ann/*`, `tests/integration/aws/` | hinted `EXPLAIN` names `clause_embedding@ce_ann`; the unhinted counterfactual is recorded |
| 5 | `real-recall` | `eval/bedrock_backend.py`, `scripts/aws/recall_real.py`, `evidence/aws/recall/*` | metrics for all five gates with Wilson intervals; gate colours unchanged in CI |
| 6 | `cohere-bench` | `scripts/aws/bench_cohere.py`, `evidence/aws/bench/*`, ADR 0040 | head-to-head on one corpus + the `global.` residency finding; no model switched |
| 7 | `agent-live` | `scripts/aws/agent_live.py`, live cassette stores, `evidence/aws/agent/*` | fresh `provenance: live` cassettes replay byte-identically twice |
| 8 | `cloudwatch-cost` | `scripts/aws/cloudwatch_evidence.py`, `evidence/aws/cloudwatch/*`, `COST.md` | AWS-side token counts reconcile with the repo's, and the delta is explained |
| 9 | `docs-correct` | `STATE-OF-THE-BUILD.md`, `HONESTY.md`, `DEVPOST.md` | §3.3 replaced with measured results; no unfavourable finding deleted |
| 10 | `census-verify` | `capture_tool_evidence.py`, tool-usage JSON, `TOOL-USAGE.md`, `evidence/aws/README.md`, verifier + workflow | `EXERCISED > 0`; hermetic verifier passes with no AWS credentials |

Full briefs, owned paths and acceptance criteria are carried in the structured output that
accompanies this file.

---

## 6. Standing prohibitions for every worker

1. **`terraform apply` is forbidden.** `init` / `validate` / `plan` only, and a plan must be
   committed as evidence if you run one.
2. **No account-settings changes.** Do not enable Bedrock model-invocation logging, do not create
   IAM roles or policies, do not change Bedrock model access, do not create log groups. CloudWatch
   evidence is **read-only metrics**. If you believe a setting must change, write the finding into
   your artefact and stop.
3. **No secrets in any committed file.** No account id in `evidence/tool-usage/*` (its own note
   forbids it), no DSN with a password, no `CC_API_KEY`. Redact through
   `scripts/aws/_common.py::redact` and assert redaction in your own test.
4. **`continue-on-error` and `|| true` are banned.** So is `xfail` used to hide a real failure.
5. **Do not weaken a ratchet.** Not `g4alpha_expected.json`, not the gate floors, not the MI
   ratchet at 28/30, not `docs/CI-STATE.md`, not `no_bare_point_estimates`.
6. **Spend ceiling.** Announce your token count in your artefact. If a run would exceed
   **USD 0.50** on its own, stop and record why instead.
7. **Stay inside your owned paths.** Anything else goes to `cross_domain_notes`.
8. **Every artefact is re-runnable** with a fixed filename (timestamps go *inside* the JSON, never
   in the name) so a redeploy overwrites rather than accumulates.

---

## 7. The specific claims in the tree that are now false

| file | claim | status |
|---|---|---|
| `docs/STATE-OF-THE-BUILD.md` §3.3 | "No AWS service has ever executed — Bedrock is NOT_AUTHORIZED"; the three `Operation not allowed` lines; the `authorizationStatus: NOT_AUTHORIZED` block | **FALSE** — §1.1. Replace with measured results, keep the citation style, keep the CloudFront/Lambda paragraphs (still true). |
| `docs/STATE-OF-THE-BUILD.md` line 561 | "≥1 AWS service used … AT RISK / effectively UNMET … 0 of 12 EXERCISED" | **STALE** — recompute after W10. |
| `docs/submission/DEVPOST.md` line 92 | "That half is DESIGNED, not EXERCISED: nothing is deployed, and every model call is a recorded cassette." | **PARTLY FALSE** — the deployment half is still true; the model-call half is not. |
| `evidence/tool-usage/aws-services.json` | `by_verdict.EXERCISED = 0`; `aws_bedrock_runtime`/`aws_bedrock_embeddings` `DESIGNED` | **STALE** — W10 flips exactly the rows the evidence supports and no others. |
| `providers/bedrock_titan.py` docstring | "Unverified on this machine: AWS credentials are not valid here" | **FALSE** — W1 corrects this one line and nothing else in that file. |
| `providers/cassette.py` docstring | "AWS credentials are not valid on the build machine, so the judge cassettes committed today are handwritten" | **PARTLY FALSE** — W7 corrects the credentials clause once live cassettes exist. |

Rows that must **not** move: `aws_bedrock_rerank` stays `NOT-AVAILABLE` (still absent in
`ap-southeast-2`); S3/KMS/CloudTrail/Lambda/CloudFront/EventBridge/SSM stay `DESIGNED` — nothing
is deployed and this fleet is forbidden from deploying anything. `aws_cloudwatch` moves to
`EXERCISED` **only** on the strength of W8's read-only metric artefact, and its `verdict_basis`
must say "metrics read, nothing provisioned".

---

## 8. What would make me say this failed

- A green that came from a softened threshold rather than a working retriever.
- An `EXERCISED` verdict whose `verdict_basis` cannot be re-derived from a committed artefact.
- A recall number in prose without its interval.
- A vector in a table whose `embed_model` column does not name the model that actually produced it.
- Any artefact that lets a reader believe the corpus is real incident data. It is synthetic, and
  the reason it is synthetic — every record is a real death and a repository is a copy — is the
  most creditable thing about the corpus design. Say it.
