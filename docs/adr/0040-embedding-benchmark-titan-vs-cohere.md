<!--
SPDX-FileCopyrightText: 2026 MAINLINE
SPDX-License-Identifier: CC-BY-4.0
-->

# ADR 0040 — Embeddings: KEEP Titan v2. The Cohere question is settled by residency, not by score

**Status:** Accepted · **Date:** 2026-08-11 · **Decider:** aws-exec worker `cohere-bench` · **Milestone:** G1 follow-through
**Closes:** the open item in ADR 0002 — *"`cohere.embed-v4:0` is also available and was not in the design. Recorded as a benchmark candidate against Titan in the recall evaluation harness; no change made unilaterally."*
**Corrects:** one sentence of ADR 0002 (see §1.2). **Does not supersede it.**
**Depends on:** ADR 0002 (platform ground truth) · `verticals/mainline/db/migrations/0031_clause_embedding.sql` · `providers/bedrock_titan.py::REQUIRED_REGION`
**Evidence:** `evidence/aws/bench/residency-finding.json` · `evidence/aws/bench/cohere-vs-titan.json` · `evidence/aws/bench/raw-cohere-invoke.json`
**Produced by:** `scripts/aws/bench_cohere.py` — re-runnable, and it changes no provider code.

> **Numbering note.** `docs/adr/0040-custody-red-before-green.md` already carries the number
> 0040. This file was commissioned under that number by the AWS-execution plan and is written
> under it rather than silently renumbered, because a citation that points at nothing is worse
> than a collision that is disclosed. The two are unrelated in subject. Renumbering is a
> one-line change for whoever owns the ADR index.

---

## 1. Context

### 1.1 What ADR 0002 left open

ADR 0002 recorded, from a live session against this account, that `cohere.embed-v4:0` was
visible in `ap-southeast-2` and was not in the design. It refused to act on that unilaterally
and left an instruction: benchmark it against Titan. That instruction has now been carried
out, and the answer arrived in a shape the instruction did not anticipate.

### 1.2 The one sentence in ADR 0002 that is wrong

> "**`cohere.embed-v4:0` is also available**"

It is **listed**, not **available**. `ListFoundationModels` returns it with
`inferenceTypesSupported: ["INFERENCE_PROFILE"]` — no `ON_DEMAND` — and an attempt to invoke
the bare id is refused. The distinction is not pedantry: it is the whole finding, because the
only identifier that *can* serve the model routes out of the country.

ADR 0002 is otherwise accurate and is not superseded. This ADR corrects that clause and
nothing else; ADR 0002 remains the platform ground truth of record.

---

## 2. The measurement that decides it, and it is not a score

Every line below was produced by `scripts/aws/bench_cohere.py` against account
`arn:aws:iam::<redacted>:user/mainline-dev` in `ap-southeast-2` on 2026-08-11, and is
recorded verbatim in `evidence/aws/bench/residency-finding.json`.

### 2.1 Three model identifiers, three different structural answers

| model id | `inferenceTypesSupported` | invocation | width returned |
|---|---|---|---|
| `amazon.titan-embed-text-v2:0` | `["ON_DEMAND"]` | **HTTP 200** | 1024 |
| `cohere.embed-english-v3` | `["ON_DEMAND"]` | **HTTP 200** | 1024 |
| `cohere.embed-v4:0` | `["INFERENCE_PROFILE"]` | **refused** | — |
| `global.cohere.embed-v4:0` | *(an inference profile)* | **HTTP 200** | 1536 |

The refusal, verbatim, `ValidationException`, HTTP 400,
`RequestId 08ad4794-ca38-4992-b5d1-1d596cfd1e09`, message digest
`sha256:89694584cbfdd26b875ecb0f32d4e00098d5383311e629c6dc85853fd4c6f826`:

> Invocation of model ID cohere.embed-v4:0 with on-demand throughput isn’t supported. Retry
> your request with the ID or ARN of an inference profile that contains this model.

The digest is worth carrying: `evidence/aws/probe/raw-cohere-refusal.json`, written by a
different worker on a different run, records the same one. Two independent invocations produced
byte-identical text, so this is Bedrock's message rather than one machine's transcription of it.

`ListInferenceProfiles` returns **29** profiles in this region. Filtered to those whose member
list contains `cohere.embed-v4`, **exactly one** comes back:

```
inferenceProfileId  global.cohere.embed-v4:0
name                Global Cohere Embed v4
description         Routes requests to Embed v4 globally across all supported AWS Regions.
type                SYSTEM_DEFINED     status  ACTIVE
models              arn:aws:bedrock:::foundation-model/cohere.embed-v4:0
                    arn:aws:bedrock:ap-southeast-2::foundation-model/cohere.embed-v4:0
```

### 2.2 What `global.` means, in AWS's own words and in one ARN

Two independent tells, both from AWS rather than from us:

1. The profile's own description says it **routes requests globally across all supported AWS
   Regions**.
2. Its first member ARN — `arn:aws:bedrock:::foundation-model/cohere.embed-v4:0` — has an
   **empty region segment**. It is not pinned to anywhere.

Which region actually serves a given request is chosen by AWS at call time and is not
observable to the caller. That is the operative harm, and it is worth stating precisely: the
risk is not that the data certainly leaves Australia. It is that **we could no longer prove it
did not.** A residency claim that cannot be checked is not a weaker claim; it is a different
kind of claim, and this system's entire proposition is that its claims are checkable.

### 2.3 Our own guard already refuses it, and was run rather than quoted

`scripts/aws/_common.py::assert_in_region` was called on all four identifiers. Three are
admitted. One raises `ResidencyError`:

> `'global.cohere.embed-v4:0'` routes through the `'global'` cross-region inference profile;
> MAINLINE embeds and reasons over Australian safety narratives in ap-southeast-2 or not at
> all (ARCHITECTURE §10.1). Use an `'au.'` profile or a bare in-region model id.

Note what the guard does *not* refuse: the bare `cohere.embed-v4:0`, which carries no routing
prefix. Our guard is about routing; Bedrock's refusal is about throughput. They are different
refusals, and together they close the door from both sides.

The commitment those refusals enforce lives in two constants that are in the tree and under
test — `providers/bedrock_titan.py::REQUIRED_REGION` and `providers/resolve.py::REQUIRED_REGION`,
both `"ap-southeast-2"`. Both cite `ARCHITECTURE §10.1`; **that document is not committed to
this repository**, so the binding artefacts are the constants and the refusal string, not the
citation. That gap is recorded here rather than papered over.

---

## 3. The two constraints that are also not scores

### 3.1 `cohere.embed-english-v3` cannot ingest this corpus without being cut

Sent one 4 680-character document with `truncate: "END"`, Bedrock answered
`ValidationException`, HTTP 400:

> Malformed input request: #/texts/0: expected maxLength: 2048, actual: 4680, please reformat
> your input and try again.

This is a **request-schema validation**, not a model-side truncation: `truncate: "END"` does
not soften it, which was tested rather than assumed. The same 4 680 characters were accepted by
`amazon.titan-embed-text-v2:0` (782 tokens) and by `global.cohere.embed-v4:0` (781 tokens).

**96 of the 1 071 documents** in the synthetic corpus — every fatality investigation report —
exceed 2 048 characters after the production embedding template is applied. Adopting v3 means
adopting a chunking strategy, and a chunking strategy is a retrieval design decision, not a
configuration value.

### 3.2 `VECTOR(1024)` is a shape, and the platform enforces it

Migration `0031_clause_embedding.sql` says a dimension change is *"a new table, never an
`ALTER`"*. That was an architectural claim. It has now been executed, against CockroachDB CCL
v26.2.5 in scratch database `w_cohere_bench`:

| statement | outcome | SQLSTATE | message |
|---|---|---|---|
| `INSERT` a 1024-d vector into `VECTOR(1024)` | accepted | — | — |
| `INSERT` a 1536-d vector into `VECTOR(1024)` | **refused** | `22000` | `expected 1024 dimensions, not 1536` |
| `ALTER … ALTER COLUMN embedding TYPE VECTOR(1536)` | **refused** | `22000` | `failed to construct index entries during backfill: expected 1536 dimensions, not 1024` |

`global.cohere.embed-v4:0` returns **1536** coordinates natively. It therefore cannot enter
`mainline.clause_embedding` at all without an expand/contract migration — a new sidecar, a read
view over both, one cutover, then the old table dropped. `cohere.embed-english-v3` returns 1024
and would fit the existing column unchanged.

---

## 4. Throughput — the strongest argument *against* this ADR's decision

This section exists because the benchmark's first attempt died to a
`ThrottlingException`, and treating that as a flaky run would have buried a real finding.

CloudWatch, `AWS/Bedrock`, 12-hour window ending 2026-08-11T03:22:38Z, read-only. This is an
attestation written by AWS, not by us, and it counts every call this account made in the window
— this fleet's other workers and this benchmark's own failed first attempt included:

| `ModelId` dimension | `Invocations` | `InvocationThrottles` | `InputTokenCount` |
|---|---|---|---|
| `amazon.titan-embed-text-v2:0` | 5 939 | **55 180** | 777 003 |
| `cohere.embed-english-v3` | 329 | 0 | 58 001 |
| `global.cohere.embed-v4:0` | 328 | 93 | 90 553 |
| `cohere.embed-v4:0` | 10 | 0 | **0** |

Two things in that table are worth reading twice.

**The last row is the residency finding, in AWS's own accounting.** Eight invocations of the
bare `cohere.embed-v4:0` and **zero input tokens**: the requests were counted and no model was
reached. Every token actually processed under Embed v4 is metered against
`global.cohere.embed-v4:0` — a separate CloudWatch dimension — which is AWS confirming that the
cross-region profile, not the in-region model, is what served the work.

**The first row is the throughput problem.** More than nine in ten Titan requests in this window
were refused.

Service Quotas (`ListServiceQuotas`, `ServiceCode=bedrock`, read-only) states the ceilings, and
a 96-text probe against each model states what one request can actually carry:

| model | on-demand requests/min | adjustable | texts per request (measured) | texts/min ceiling |
|---|---|---|---|---|
| `amazon.titan-embed-text-v2:0` | 60 | no | **1** — see the refusal below | **60** |
| `cohere.embed-english-v3` | 20 | no | **96** returned in one call, 672 tokens | **1 920** |
| `global.cohere.embed-v4:0` | 20 | yes | **96** returned in one call, 768 tokens | **1 920** |

Titan's "1" is measured, not inferred. Handing it a 96-element array produces
`ValidationException`, HTTP 400:

> Malformed input request: expected type: String, found: JSONArray, please reformat your input
> and try again.

Read the requests-per-minute column alone and Titan looks three times faster. Read both columns
and the ranking reverses by a factor of thirty-two.

And the ceiling was not what this account served. After a ten-minute rest with zero calls,
`amazon.titan-embed-text-v2:0` returned **4 successes out of 20 attempts** at 15 requests per
minute, and **1 out of 8** at 6 requests per minute — slowing down did not help, which is what
distinguishes an exhausted allowance from a rate limit. In a probe of six calls per model,
`cohere.embed-english-v3` and `global.cohere.embed-v4:0` each returned **6 out of 6** while Titan
returned **1 out of 6**.

The cause of the depletion is worth naming, because it is a defect a reader could repeat: the
sweep's first attempt used botocore's default retry policy, whose retries are **invisible to the
caller's own rate limiter**. One `invoke_model` per second with up to five SDK retries inside it
is up to five requests per second, and every retried request still counts against the per-minute
quota that caused the retry. The fix is in `bench_cohere.py::bench_runtime`: `max_attempts=1`, so
the rate the pacer enforces is the rate AWS sees, and a throttle reaches the program where it can
be counted and waited out.

A quota increase is an account-settings change and is out of scope for this fleet. The finding is
recorded and left for the founder.

**This is a real operational disadvantage for the incumbent and it is not resolved by this
ADR.** It is a reason to plan corpus-scale embedding as a batched, restartable job with a
journal — which is what `bench_cohere.py` now does — and it is a standing risk to any worker
that needs a thousand Titan vectors in an afternoon.

---

## 5. The retrieval measurement

### 5.1 What was measured, and on what

One corpus, one query set, one embedding template, three arms. Every arm saw the identical
strings, composed by the production template `providers/base.py::embed_text`
(`{activity_path} | {asset_class} | {facet}: {cue_text}`, digest `08a1b8d5…`) and normalised by
the production `normalise_text`.

- **Corpus:** the whole merged synthetic replica — 1 071 records (891 Part 50 extracts, 96
  fatality reports, 60 Australian regulator alerts, 24 CSB reports). Not a sample.
- **Queries:** all 96 G4 retro permits. `n = 96` for every proportion below.
- **Time wall:** applied per query — `occurred_at < t AND ingested_at < t AND corpus_commit_at
  <= t`, the three predicates `trappoint_recall.eval.splits.SplitPolicy` applies, with `t` read
  from each query's own grade-3 judgement. Walled candidate pool: 282 documents at minimum, 831
  median, 1 065 maximum.
- **Ranking:** exhaustive cosine in-process. No database and no ANN index — deliberately, so
  this result does not depend on another worker's index and is not confounded by its recall.
- **Task:** given a permit synthesised from a fatality investigation's own description of the
  work, does the prior incident the investigator cited surface before the wall?

### 5.2 Two properties of this corpus that decide how the numbers read

**The corpus is synthetic**, and every score below is therefore a statement about a generator.
It models fatalities. It is synthetic because every real record is a real death and a repository
is a copy.

**The corpus repeats itself.** The 1 071 documents reduce to **224 distinct embedding inputs**,
and the 96 queries to **24**. Identical text gives an identical vector and an exact cosine tie.
This benchmark therefore breaks ties **against** the right answer: the truth precursor is ranked
behind everything scoring equal to it, not in front. A retriever that cannot separate the answer
from documents identical to it has not found it. Under that rule 8 of 96 queries have a tied
truth precursor, at most 7 documents deep — identical across all three arms, because the ties
come from the corpus rather than from any model.

### 5.3 Retro-recall — did the true precursor surface? (grade 3, `n = 96`, 95% Wilson)

| arm | hit@1 | hit@3 | hit@10 |
|---|---|---|---|
| `amazon.titan-embed-text-v2:0` | 0.0729 [0.0358, 0.1429] · 7/96 | 0.3021 [0.2193, 0.4001] · 29/96 | 0.6250 [0.5251, 0.7153] · 60/96 |
| `cohere.embed-english-v3` | 0.1042 [0.0576, 0.1812] · 10/96 | 0.3021 [0.2193, 0.4001] · 29/96 | 0.5521 [0.4525, 0.6476] · 53/96 |
| `global.cohere.embed-v4:0` ⚠ | 0.1042 [0.0576, 0.1812] · 10/96 | 0.3750 [0.2847, 0.4749] · 36/96 | 0.8854 [0.8064, 0.9348] · 85/96 |

Any relevant document in the window (grade ≥ 2, `n = 96`, 95% Wilson):

| arm | hit@1 | hit@3 | hit@10 |
|---|---|---|---|
| `amazon.titan-embed-text-v2:0` | 0.4062 [0.3135, 0.5063] · 39/96 | 0.5729 [0.4730, 0.6672] · 55/96 | 0.9062 [0.8313, 0.9499] · 87/96 |
| `cohere.embed-english-v3` | 0.3438 [0.2564, 0.4431] · 33/96 | 0.5104 [0.4120, 0.6081] · 49/96 | 0.8542 [0.7700, 0.9111] · 82/96 |
| `global.cohere.embed-v4:0` ⚠ | 0.5625 [0.4628, 0.6574] · 54/96 | 0.7500 [0.6549, 0.8259] · 72/96 | 0.9688 [0.9121, 0.9893] · 93/96 |

Rank-sensitive measures — means of per-query quantities, so a deterministic bootstrap percentile
interval rather than Wilson, `n = 96`:

| arm | MRR of the truth precursor | nDCG@10 | mean rank of the truth precursor |
|---|---|---|---|
| `amazon.titan-embed-text-v2:0` | 0.2364 [0.1870, 0.2912] | 0.4320 [0.3645, 0.4995] | 24.65 [15.37, 35.79] |
| `cohere.embed-english-v3` | 0.2484 [0.1911, 0.3104] | 0.3421 [0.2802, 0.4094] | 28.22 [18.28, 39.53] |
| `global.cohere.embed-v4:0` ⚠ | 0.3124 [0.2604, 0.3677] | 0.5089 [0.4481, 0.5702] | 16.94 [8.11, 27.87] |

⚠ = **residency-violating**, measured for completeness on a synthetic corpus only, never proposed
for use.

### 5.4 The paired comparison, which is the one that answers the question

All three arms were scored on the same 96 queries, so these are paired data and the independent
intervals above answer a weaker question than the one being asked. The discordant counts — the
queries one arm got and the other missed — carry the information, and the p-values are exact
two-sided sign tests with no normal approximation.

| comparison | Titan only | challenger only | n discordant | exact p |
|---|---|---|---|---|
| Titan vs v3, hit@1 | 5 | 8 | 13 | 0.581 |
| Titan vs v3, hit@3 | 16 | 16 | 32 | 1.000 |
| Titan vs v3, hit@10 | 21 | 14 | 35 | 0.311 |
| Titan vs v4 ⚠, hit@1 | 2 | 5 | 7 | 0.453 |
| Titan vs v4 ⚠, hit@3 | 9 | 16 | 25 | 0.230 |
| **Titan vs v4 ⚠, hit@10** | **3** | **28** | **31** | **0.000005** |

**One difference in this table is resolvable and five are not.** At `n = 96`, Titan and
`cohere.embed-english-v3` are indistinguishable at every cutoff: neither has an advantage this
sample can detect, and the hit@3 row is an exact 16-16 tie. The single clear result is that
`global.cohere.embed-v4:0` recovers the true precursor in the top ten far more often than Titan
does — 85 of 96 against 60 of 96, and it wins 28 of the 31 queries where the two disagree.

**That result should be read plainly: on this corpus the best retriever is the model this ADR
refuses.** Nothing in §6 rests on Cohere being worse, because on the evidence here it is not.

### 5.5 Cost, tokens and latency

Every call was one text, sequentially, with the arms interleaved and rotated so no arm
systematically held the warm socket. Latency is reported over the calls that **nothing retried** —
a throttled call's wall clock is the account's quota wearing a model's name — and the excluded
count is shown so the exclusion cannot be mistaken for a clean sweep.

| arm | calls | input tokens (documents) | mean tokens/doc | USD / 1 000 documents | latency, clean calls only (ms) |
|---|---|---|---|---|---|
| `amazon.titan-embed-text-v2:0` | 1 167 | 111 085 | 103.72 | **0.00207** | 82.94 [82.21, 83.71], n = 1 119 |
| `cohere.embed-english-v3` | 1 167 | 84 354 | 78.76 | 0.00788 | 104.83 [102.75, 107.07], n = 1 167 |
| `global.cohere.embed-v4:0` ⚠ | 1 167 | 111 710 | 104.30 | 0.01252 | 377.37 [367.55, 388.24], n = 921 |

Titan is roughly **3.8× cheaper** per thousand documents than `cohere.embed-english-v3` and
**6× cheaper** than Embed v4, at published list prices. It is also the fastest per call. 48 Titan
calls and 246 Embed v4 calls were excluded from the latency figures as retried; no
`cohere.embed-english-v3` call was throttled at all.

`cohere.embed-english-v3` shows the *lowest* token count of the three, and that is not an
efficiency: **96 of its 1 167 inputs were cut client-side at 2 048 characters** (the longest from
3 998) because Bedrock refuses it anything longer. It was charged for less text because it was
shown less text. §3.1.

**Whole-run spend: 3 501 calls, 337 741 input tokens, USD 0.0265** at published list prices, from
the ledger in `cohere-vs-titan.json` — against a per-run fleet ceiling of USD 0.50.

---

## 6. Decision

**KEEP `amazon.titan-embed-text-v2:0`. Change no provider code, and switch no model.**
`providers/bedrock_titan.py::TITAN_EMBED_MODEL_ID` is untouched by this ADR and by the program
that produced it.

The reasoning, in the order the constraints bind. Note that **the retrieval scores are not the
first four reasons and are not decisive** — the constraints that decide this are structural.

1. **`cohere.embed-v4:0` is unavailable at any price this system can pay.** Its only identifier
   on this account routes globally, and MAINLINE's residency commitment is not a preference to
   be traded against a benchmark score. §2. This is the load-bearing reason, and §5.4 shows it
   costs something real: v4 recovered the true precursor in the top ten 85 times out of 96
   against Titan's 60, the one difference in the whole comparison that the sample can resolve.
   **We are refusing the better retriever, knowingly, and the price of that refusal is now
   measured rather than assumed.**
2. **Even setting residency aside, v4 does not fit the schema.** 1536 ≠ 1024, and the platform
   refuses both the narrow insert and the in-place widen. §3.2.
3. **`cohere.embed-english-v3` is the genuinely close call, and it is not beaten on quality.**
   Paired against Titan on the same 96 queries it is indistinguishable at every cutoff — hit@3
   is an exact 16-16 split, and no cutoff reaches significance. §5.4. It loses on a structural
   constraint: Bedrock refuses it any single text over 2 048 characters, which 96 of the 1 071
   corpus documents exceed, so adopting it means adopting a chunking design — a retrieval
   decision, not a configuration value. §3.1.
4. **Titan v2 is the incumbent, and the incumbent wins ties.** It is already the width `0031`
   declares, already in-region on demand, already the model every committed artefact names, and
   at published list prices it is 3.8× cheaper per thousand documents than v3 and 6× cheaper
   than v4, with the lowest per-call latency of the three. §5.5. Switching a model that is
   statistically tied with the incumbent, in exchange for a chunking design and a higher bill,
   is churn.
5. **The one clear argument the other way is throughput**, and it is recorded in §4 rather than
   omitted. It does not outweigh residency and schema fit, but it is the reason a corpus-scale
   embedding pass must be designed as a resumable, journalled job — which is what building this
   benchmark forced, after its first attempt lost every vector it had bought.

---

## 7. When this decision should be revisited

Each of these is a **specific, checkable condition**, not a sentiment. Any one of them makes
this ADR stale and the benchmark worth re-running with `scripts/aws/bench_cohere.py`.

1. **An `au.cohere.embed-v4` inference profile appears in `ap-southeast-2`.** That would
   dissolve the residency objection entirely, and it is the only condition that puts v4 back on
   the table. Check with `ListInferenceProfiles`; the census in `residency-finding.json` is the
   baseline to diff against.
2. **`cohere.embed-v4:0` gains `ON_DEMAND` in `inferenceTypesSupported`** in this region — same
   effect, different mechanism.
3. **Bedrock's per-text `maxLength` for the Cohere v3 family rises above the corpus's longest
   document**, or MAINLINE adopts chunking for its own reasons. Either removes the §3.1
   objection and makes v3 a live candidate on a like-for-like footing.
4. **A new sidecar is being created anyway.** The expand/contract cost in §3.2 is only a cost
   because the table exists at 1024. A second embedding space — `0041`'s event cues, `0042`'s
   coarse sweep — is a new table by construction, and a model of a different width is free at
   that moment and never again.
5. **Titan v2's effective on-demand throughput on this account is not raised**, and a corpus of
   more than a few thousand documents has to be embedded on a deadline. §4 is then the binding
   constraint rather than an annoyance, and Cohere's 96-texts-per-request becomes the deciding
   fact.
6. **A real corpus replaces the synthetic one, or the synthetic one stops repeating itself.**
   Every score in §5 is measured on invented text and is a statement about a generator — one
   that emits 1 071 documents from 224 distinct narratives (§5.2). Real regulator prose does not
   repeat like that, and it could rank the arms differently. Nothing in §5 forbids that, and
   `bench_cohere.py` will run against a different corpus by pointing `FIXTURES` elsewhere.

---

## 8. Consequences

- `providers/bedrock_titan.py`, `providers/registry.py` and `providers/resolve.py` are
  unchanged. No model id moved.
- `mainline.clause_embedding.embedding VECTOR(1024)` stays as `0031` declares it. No
  expand/contract migration is opened.
- `_common.py::CROSS_REGION_PREFIXES` keeps `global` in the refused set, and
  `residency-finding.json` is now the evidence that the refusal has a live target rather than a
  hypothetical one.
- `scripts/aws/bench_cohere.py` is committed and re-runnable, so revisiting condition §7 costs a
  command rather than a reconstruction.
- The throughput finding in §4 is handed to the fleet: any worker planning a corpus-scale Titan
  pass must budget for it.

## 9. What this ADR does not claim

- **It does not claim Cohere is worse. On this corpus Embed v4 is better, measurably.** §5.4
  resolves exactly one difference in six comparisons and it goes against the incumbent. The
  decision rests on residency and schema fit, which are structural; had residency not bound, the
  right answer would have been different, and this document would say so.
- **It does not claim `cohere.embed-english-v3` lost.** It tied. A tie plus a chunking
  requirement plus a higher bill is a reason not to switch, not a finding of inferiority.
- **It does not claim anything about real incident data.** The corpus is
  `trappoint_recall.corpora.synthetic` — invented records, `corpus_class='synthetic_replica'`,
  `tenant_use='harness_only'`. It models fatalities, and it is synthetic precisely because every
  real record is a real death and a repository is a copy.
- **It does not claim the numbers are ANN numbers.** Ranking is exhaustive cosine in-process.
  Those are the ceiling an indexed arm is measured against; an indexed arm scores at or below
  them.
- **It does not claim to have read a bill.** Every USD figure comes from published list prices
  recorded in `_common.py::USD_PER_1K_TOKENS`, carried with `PRICE_BASIS` on every ledger row.
- **It does not claim the account's quotas are correct or final.** They were read, not
  negotiated, and no increase was requested.
