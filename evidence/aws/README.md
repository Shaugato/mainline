# `evidence/aws/` — what AWS actually did, and how to check it without trusting us

This directory is the answer to one hackathon question: *which AWS services did you use, and
how?* Everything under it was written by a program in [`scripts/aws/`](../../scripts/aws)
while that program held live credentials for the `mainline-dev` profile in
**`ap-southeast-2`**. You do not have those credentials, so this README's job is to tell you
what each file claims, which command produced it, and — most importantly — **what it does
not prove**.

Start here, then run one command:

```bash
python scripts/aws/verify_evidence.py
```

Standard library only. No credential, no network, no database, no `pip install`. It checks
that every artefact carries its envelope, that the cross-references between artefacts
resolve, that nothing under `evidence/` leaks an account id or a password, and that every
`EXERCISED` verdict in `evidence/tool-usage/aws-services.json` names a file that exists. If
it exits non-zero it prints the invariant that broke. It runs in CI as
[`.github/workflows/aws-evidence.yml`](../../.github/workflows/aws-evidence.yml) on a fresh
checkout with no secrets configured, which is the whole point of writing it that way.

---

## ► THE ONE QUERY

> **File: [`ann/the-one-query.sql`](ann/the-one-query.sql)**
>
> Open a SQL shell on the CockroachDB Cloud cluster `mainline-dev`, `USE
> mainline_ann_evidence;`, and paste the whole file. It is self-contained: the 1024-float
> query vector is inlined, so nothing outside the file has to run.
>
> **What you should see.** Ten rows. The top row is `clause_uuid`
> `9f28c5af-f010-5ea9-b685-adc2c1315cc5`, cosine distance `0.494575` — the goldset's cited
> precursor for the fatality `FAI-2011-142`, at **rank 1 of 10**. Run the `EXPLAIN` at the
> foot of the file and the plan contains a `vector search` node whose table line reads
> `clause_embedding@ce_ann`, with `prefix spans` binding `site_id` and `activity_root` each
> to a single value.
>
> **Why that sentence is the submission.** The query vector was produced by
> **Amazon Bedrock** (`amazon.titan-embed-text-v2:0`, `ap-southeast-2`) from a permit
> narrative written *before* the fatality. The rows it searched are 1024-dimension
> `VECTOR` columns in **CockroachDB**, reached through the C-SPANN index `ce_ann` with both
> prefix columns bound — which is the only shape C-SPANN will descend. Neither half is a
> fixture. The plan, the ranks and the distances are all committed next to the query.
>
> **What it is not.** It is an *exhibit*, chosen by a rule written into
> `scripts/aws/ann_proof.py::_choose_exhibit` before any number was seen, and it is the
> best of `96` retro permits measured in one pass. The distribution across all 96 —
> `74/96 = 0.771 [0.677, 0.844]` 95% Wilson for any-relevant hit@10 on the single-root arm,
> and `28/96 = 0.292 [0.210, 0.389]` at hit@1 — is in
> [`ann/ann-proof.json`](ann/ann-proof.json) under `payload.metrics`. **Quoting the one
> query without that file is quoting the best case as if it were the average.**

---

## Read this before you read anything else

Three disclosures. They are here, at the top, because a directory of evidence that leads
with its strengths is marketing.

**1 · The corpus is SYNTHETIC, and that is a design decision, not a shortfall.**
Every fatality report, Part-50 line, CSB report and state alert embedded here was generated
by `trappoint_recall.corpora.synthetic`. No real incident, no real person, no real
operation, no real permit. The reason is stated plainly in
[`embeddings/corpus-provenance.json`](embeddings/corpus-provenance.json): **every source
record in this domain is a real death, and a repository is a copy.** MAINLINE will not hold
one. The gold sets reference real MSHA document identifiers so the retrieval task keeps its
shape, and the *text* a retriever embeds is fabricated. Every artefact in this tree carries
`"synthetic": true` in its envelope when its subject matter is fabricated, and the verifier
fails if the manifest, the loader record or the ANN proof stops saying so.

**The Bedrock calls, the vectors, the CockroachDB writes, the index traversal, the plans,
the ranks and the latencies are all real.** The subject matter is not.

**2 · The parent table in `mainline_ann_evidence` is a STUB.**
The corpus-scale ANN work runs in a *separate* database, `mainline_ann_evidence`, whose
`mainline.clause_embedding` DDL is copied verbatim from
`verticals/mainline/db/migrations/0031_clause_embedding.sql` — line-by-line proof of that in
[`load/schema-fidelity.json`](load/schema-fidelity.json), `diff_line_count` `0`. But its
parent `mainline.clause_version` is a **two-column stub**: primary key only, and **none of
the production table's `append_only`, `z_delta_witness_required` or `clause_version_guard`
triggers**. So:

* nothing in `mainline_ann_evidence` demonstrates the gate,
* the ANN proof declares `payload.database.parent_table_is_stub: true` and the verifier
  fails if that flag is ever removed,
* the *production* table — full triggers, full FK — is exercised separately and minimally
  in [`load/demo-row.json`](load/demo-row.json): **one** real Titan vector accepted by
  `mainline_demo.mainline.clause_embedding` under its actual constraints. One row is a small
  claim. It is also an unimpeachable one, and it is the honest way to say "the production
  table takes a Bedrock vector" without forging writes past a gate whose entire purpose is
  to refuse them.

**3 · No AWS infrastructure is deployed. None.**
There is no bucket, no KMS key, no CloudTrail trail, no Lambda function, no CloudFront
distribution, no EventBridge rule, no SSM parameter, no IAM role created by this project.
The Terraform under `infra/` is written, validated and planned, and `terraform apply` has
never been run. Every AWS service in `evidence/tool-usage/aws-services.json` other than the
Bedrock rows is `DESIGNED`, which in this repository means *the configuration is complete
and on disk and nothing recorded has run it end to end*. What ran is **model inference and
read-only metrics** — API calls against services AWS already operates.

Two further limits worth having in front of you:

* **Bedrock Rerank is `NOT-AVAILABLE` in `ap-southeast-2`.** It is listed in the census
  rather than omitted, because a services list that drops what you checked for and could not
  have is a list nobody can audit.
* **The recall gates are RED and stay red.** [`recall/gate-report.md`](recall/gate-report.md)
  reports `verdict: FAIL` on a synthetic corpus, and the numbers say why. Nothing in this
  fleet lowered a floor to change that colour.

---

## What is in each subdirectory

Every program below is re-runnable, writes to a fixed filename (the timestamp lives *inside*
the JSON), and needs `AWS_PROFILE=mainline-dev`.

### `probe/` — Bedrock executed, and here are the request ids

**Produced by** `python scripts/aws/probe_bedrock.py`

| file | what it proves |
|---|---|
| [`probe/bedrock-probe.json`](probe/bedrock-probe.json) | the summary: Titan `HTTP 200` returning a 1024-d unit-norm embedding, Claude Haiku 4.5 answering through the Australia-only `au.` inference profile, and Cohere `embed-v4` refusing on-demand invocation. `verdict: PROVEN`. |
| [`probe/raw-titan-invoke.json`](probe/raw-titan-invoke.json) | the full `bedrock-runtime:InvokeModel` request and response for `amazon.titan-embed-text-v2:0`, with the AWS request id and the response-body digest. |
| [`probe/raw-haiku-converse.json`](probe/raw-haiku-converse.json) | the full `bedrock-runtime:Converse` exchange with `au.anthropic.claude-haiku-4-5-20251001-v1:0` — request id, `stopReason end_turn`, `usage` — and `sampling_parameters_sent: []`, because no MAINLINE generation sends a sampling parameter. |
| [`probe/raw-cohere-refusal.json`](probe/raw-cohere-refusal.json) | the `ValidationException` verbatim, kept because the refusal is a *finding*, not an error to hide. |
| [`probe/model-availability.json`](probe/model-availability.json) | the control-plane census: foundation models in region, and the inference profiles split by routing prefix. This is the file that makes `assert_in_region` non-hypothetical. |

**This directory replaces a claim.** `docs/STATE-OF-THE-BUILD.md` §3.3 used to record *"no
AWS service has ever executed"* and a `ValidationException: Operation not allowed`. That was
true when written and does not reproduce; `bedrock-probe.json` carries a `supersedes` field
saying exactly that.

### `embeddings/` — 2 060 real Titan vectors, and what they cost

**Produced by** `python scripts/aws/embed_corpus.py`

| file | what it proves |
|---|---|
| [`embeddings/manifest.json`](embeddings/manifest.json) | one entry per vector: id, text digest, vector digest, token count, latency. `2060` vectors, `1024` dimensions, `unit_norm_verified: 2060`, `index_gen: titan2-1`. The vectors themselves live under `out/` (gitignored — a 8 MB float blob is not a document); the manifest is what makes them checkable. |
| [`embeddings/token-ledger.json`](embeddings/token-ledger.json) | `177345` input tokens across `2060` calls at list price, and a `reconciliation` block that admits a `delta` of `74` vectors the build history cannot attribute to a named run. A ledger that reconciles perfectly on the first try is usually a ledger that has not been checked. |
| [`embeddings/corpus-provenance.json`](embeddings/corpus-provenance.json) | which corpus, which generator, which seed, which gold sets, and the sentence *"SYNTHETIC — no real incident record is committed to this repository"*. |
| [`embeddings/raw-request-sample.json`](embeddings/raw-request-sample.json) / [`embeddings/raw-response-sample.json`](embeddings/raw-response-sample.json) | one full request and one full response, so the wire format is not something you have to take on faith. |

### `load/` — the vectors reached CockroachDB

**Produced by** `python scripts/aws/load_vectors.py`

| file | what it proves |
|---|---|
| [`load/cloud-load.json`](load/cloud-load.json) | rows written into `mainline_ann_evidence` on CockroachDB Cloud (`aws-ap-southeast-1`), with the DDL issued, the per-prefix row survey, and the manifest join that rejects any vector of the wrong width or the wrong digest. |
| [`load/demo-row.json`](load/demo-row.json) | the small unimpeachable claim: **one** Titan vector accepted by the *production* `mainline_demo.mainline.clause_embedding`, under its real FK and its real triggers. |
| [`load/schema-fidelity.json`](load/schema-fidelity.json) | the evidence database's DDL against migration `0031_clause_embedding.sql`, line by line. `diff_line_count: 0` is what earns the phrase "the real index". |
| [`load/retry-40001.json`](load/retry-40001.json) | the `40001 RETRY_SERIALIZABLE` loop, and the unflattering truth that the bulk load observed **zero** serialization failures — so the loop was also *induced* deliberately, by a write-after-read conflict, and made to fire (`retries_40001: 1`). Insurance whose premium is never quoted is indistinguishable from superstition. |

**You can re-derive the fidelity claim yourself, on your own node, in a minute.** `just up`
starts the pinned `cockroachdb/cockroach:v26.2.5`; then apply
`verticals/mainline/db/evidence/ann_evidence_schema.sql` to a scratch database and run
`SHOW CREATE TABLE mainline.clause_embedding`. Verified this way on 2026-08-11 against
`postgresql://root@localhost:26257`: the file applies clean and the resulting table carries
`VECTOR INDEX ce_ann`, `VECTOR(1024)`, `FAMILY f_meta` / `FAMILY f_vec`, `CONSTRAINT
fk_version`, `CONSTRAINT embed_model_stated` and `CONSTRAINT index_gen_stated` — no account
and no cloud cluster involved. That checks the *shape* of the table. It does **not** check
the rows: those live on the Cloud cluster and a local node has none.

### `ann/` — the claim itself

**Produced by** `python scripts/aws/ann_proof.py`

| file | what it proves |
|---|---|
| [`ann/ann-proof.json`](ann/ann-proof.json) | `96` retro queries against `1080` searched rows, three retrieval arms, every metric as a fraction with an `n` and a 95% Wilson interval. Also the exhibit, the corpus provenance, and the token ledger for the pass. |
| [`ann/the-one-query.sql`](ann/the-one-query.sql) | the exhibit, self-contained. See the block at the top of this file. |
| [`ann/explain-hinted.txt`](ann/explain-hinted.txt) | the plan the submission rests on: a `vector search` node over `clause_embedding@ce_ann` with both prefix columns bound. |
| [`ann/explain-unhinted.txt`](ann/explain-unhinted.txt) | **the control, and it contradicts our own ADR.** ADR 0002 GT-06 recorded that the optimizer does *not* choose the vector index unhinted at demo scale. Measured here, it does — `gt06_counterfactual_reproduces: false` — and rather than delete the finding, the artefact carries a row-count sweep through GT-06's own row count and reports that the hint changed nothing at this size. The hint stays because a plan that flips with table statistics must not sit beneath a safety gate. |

### `bench/` — the model choice, and a residency finding that outranks it

**Produced by** `python scripts/aws/bench_cohere.py`

| file | what it proves |
|---|---|
| [`bench/cohere-vs-titan.json`](bench/cohere-vs-titan.json) | Titan v2 against `cohere.embed-english-v3` and `global.cohere.embed-v4:0` on one corpus, paired on the same 96 queries. Recommendation: **keep** `amazon.titan-embed-text-v2:0`. No provider code was changed. |
| [`bench/residency-finding.json`](bench/residency-finding.json) | the structural half. On this account the *only* Bedrock identifier that serves `cohere.embed-v4` is `global.cohere.embed-v4:0` — a **cross-region** routing profile, the exact opposite of the guarantee `providers/bedrock_titan.py::REQUIRED_REGION` makes. At v4, the choice is residency *or* that model. |
| [`bench/raw-cohere-invoke.json`](bench/raw-cohere-invoke.json) | one full request/response per model id, embeddings truncated to their first 16 coordinates with a digest over the whole vector. |

### `recall/` — the numbers, including the ones that fail

**Produced by** `python scripts/aws/recall_real.py`

| file | what it proves |
|---|---|
| [`recall/real-embeddings-metrics.json`](recall/real-embeddings-metrics.json) | all five G4-alpha gates scored against real Bedrock vectors instead of the `NullBackend`. `verdict: FAIL` — three gates red. Every measurement carries its interval and its `n`. |
| [`recall/gate-report.md`](recall/gate-report.md) | the same run, readable, with the attribution for each red gate. |
| [`recall/run-manifest.json`](recall/run-manifest.json) | what was run: corpus, split policy, index generation, embed template digest, prefix reachability ceiling, and the token ledger for the pass. |

**Read the reds as data.** `nuisance_rate` and `mean_blocking_checks_per_permit` are red in
part because of *prefix reachability* — for some retro permits the true precursor does not
live in the `(site_id, activity_root)` partition the permit addresses, so no amount of
retrieval quality can find it. That ceiling is computed and published in the same file
rather than left as an excuse. The G4-alpha CI lane compares these colours against
`g4alpha_expected.json` and is deliberately built so that a *working* retriever makes the
lane fail until a human flips the expectation in a reviewable commit.

### `agent/` — the product's own agent layer, on the live model

**Produced by** `python scripts/aws/agent_live.py`

| file | what it proves |
|---|---|
| [`agent/live-run.json`](agent/live-run.json) | `7` real `InvokeModel` legs through `au.anthropic.claude-haiku-4-5-20251001-v1:0`, each with an AWS request id, each recorded as a cassette — the shipped orchestrator, not a probe. `17429` input tokens and `5297` output tokens at list price. |
| [`agent/determinism.json`](agent/determinism.json) | the same input replayed twice from the live cassette store to a **byte-identical** decision hash, with the three excluded fields named and justified (a fresh receipt uuid, wall-clock latency, a pinned run id); plus five tamper probes, all of which make the cassette **refuse to load** rather than silently answer from an edited fixture. |

**Three things this directory does not claim.** The live legs ran on **Haiku 4.5** while the
shipping request builders target the pinned Opus generation, and four builder fields are
refused on the wire by Haiku — the projection is applied *at the wire*, field by field, and
never written back into a builder, so no cassette key moved. **No live leg refused**
(`live_refusals_observed: 0`), so the "a refusal degrades the run and the gate still holds"
path was exercised against a *constructed* refusing transport, not against a model that
actually said no. And neither cassette loader hashes the *response* — which is why both
live stores ship an `INDEX.json` carrying `response_sha256`, and why the artefact says so
instead of leaving the reader to assume otherwise.

### `cloudwatch/` — the one witness in this tree that we did not write

**Produced by** `python scripts/aws/cloudwatch_evidence.py` — **read-only**

| file | what it proves |
|---|---|
| [`cloudwatch/bedrock-metrics.json`](cloudwatch/bedrock-metrics.json) | `AWS/Bedrock` `Invocations`, `InputTokenCount`, `OutputTokenCount`, `InvocationThrottles` and error counts per `ModelId` in `ap-southeast-2`, each `Sum` taken at `Period` `300` *and* `3600` and required to agree — a Sum is resolution-invariant, so a disagreement would mean a clipped bucket and neither number could be trusted. **This is AWS's own attestation that this repository's code ran.** |
| [`cloudwatch/reconciliation.json`](cloudwatch/reconciliation.json) | AWS's numbers minus the repository's own token ledgers, per model, with every non-zero delta named. |
| [`cloudwatch/COST.md`](COST.md) *(`evidence/aws/COST.md`)* | what the whole fleet cost, priced from AWS's observed counts rather than from what our programs believed they spent. |

**Two things about this directory matter more than the numbers.**

*Nothing was provisioned.* No log group, no alarm, no dashboard, no metric filter, no IAM
role, no Terraform apply, and no model invoked by the reader itself. That is not a promise
in prose: `scripts/aws/cloudwatch_evidence.py` registers a `before-call` guard that raises
for any operation outside a six-item read-only allow-list *before the request is signed*,
and the artefact commits the complete API-call log. The census's CloudWatch verdict says
**"metrics read, nothing provisioned"** and this is what makes that checkable.

*The deltas are the interesting part, and they are large.* AWS counted `7542` Titan
invocations; the repository's ledgers claim `3227`. The gap is named rather than smoothed:
probes made before the fleet's first artefact existed, SDK-internal retries that are
separate HTTP requests AWS served and counted, and — the honest residual — thousands of
calls made while these programs were being written and debugged, which **no artefact in this
repository records, so no artefact in this repository may claim them.** The reconciliation
also declares itself **incomplete**: `sources_missing` lists `agent_live`, because
`scripts/aws/agent_live.py` has written no artefact, so every Anthropic-model figure is
AWS's side only.

---

## How the artefacts hold each other up

The verifier does not take any single file's word for anything. These are the joins it
walks, and any one of them breaking is a red build:

```
embeddings/manifest.json .model_id ─────┬──► ann/ann-proof.json  .vectors.embed_model_expected
                                        ├──► load/cloud-load.json .source.manifest.manifest_model_id
                                        ├──► probe/bedrock-probe.json .titan.model_id
                                        └──► tool-usage/aws-services.json  aws_bedrock_embeddings.verdict_basis

embeddings/manifest.json .index_gen ────┬──► load/cloud-load.json .source.manifest.manifest_index_gen
                                        └──► ann/ann-proof.json  .vectors.index_gen_anywhere_in_table

embeddings/token-ledger.json  .index_cumulative.build_history  ──► .reconciliation (sums, delta)

ann/ann-proof.json .the_one_query  ──► ann/the-one-query.sql (query id, doc id, site id, root)
ann/ann-proof.json .plans.hinted   ──► ann/explain-hinted.txt (`clause_embedding@ce_ann`)

cloudwatch/reconciliation.json .repo_sources[*].json_pointer
        ──► walks INTO each artefact it names and must find the same number there
```

**One join that does *not* close, stated here rather than smoothed over.** Two programs
write into `mainline_ann_evidence.mainline.clause_embedding` and they label their
generations differently: `load_vectors.py` writes the manifest's `titan2-1`, while
`ann_proof.py` loads its own rows under a content-derived label and searches **only** those.
Both generations are present in one table. `ann-proof.json` discloses the other one in
`vectors.index_gen_anywhere_in_table` and enumerates its rows in
`vectors.rows_under_other_prefixes`, so the table's row count is never mistaken for the
searched row count — and the verifier enforces exactly that disclosure rather than
pretending the two labels are equal.

---

## What is deliberately *not* here

* **No live *refusal*.** `agent/live-run.json` records `0` live refusals across seven legs,
  so the refusal path is exercised with a constructed transport and the artefact says so.
* **No Opus-generation live run.** The live legs are Haiku 4.5; the shipping builders target
  the pinned Opus generation, and the four fields Haiku refuses are listed rather than
  smoothed over.
* **No model-invocation log.** Enabling Bedrock invocation logging is an account-settings
  change, and every worker in this fleet was forbidden from making one.
* **No vectors.** The float blobs live under `out/` and are gitignored. The manifest carries
  a SHA-256 per vector, which is the checkable part.
* **No account id, no DSN password, no key material.** Everything written here passes
  through `scripts/aws/_common.py::redact`, and `scripts/aws/verify_evidence.py` re-scans
  the whole of `evidence/` for those shapes on every CI run.

---

## Cost

The entire AWS spend behind this directory is under **USD 0.01** of Bedrock inference at
published list price — `177345` input tokens of Titan v2 plus a handful of Haiku calls.
Prices are *declared, not measured*: no bill and no Price List API response backs them, and
every ledger row says so in its `price_basis`. Nothing here provisions anything, so there is
no standing cost at all.

---

*Licensing: `evidence/**` is CC-BY-4.0 by `REUSE.toml`. Related reading:*
[`docs/TOOL-USAGE.md`](../../docs/TOOL-USAGE.md) *— the full services census;*
[`docs/HONESTY.md`](../../docs/HONESTY.md) *— everything this build gets wrong, counted;*
[`evidence/tool-usage/README.md`](../tool-usage/README.md) *— how the censuses are built.*
