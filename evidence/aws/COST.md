<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# What this fleet actually spent on AWS

**Every USD figure on this page is derived from token counts AWS published about itself**,
read from CloudWatch `AWS/Bedrock` and recorded in
[`evidence/aws/cloudwatch/bedrock-metrics.json`](cloudwatch/bedrock-metrics.json).
None of it is derived from this repository's own accounting. That is deliberate: the
repository's ledgers and AWS's counters disagree, the disagreement is explained in
[`evidence/aws/cloudwatch/reconciliation.json`](cloudwatch/reconciliation.json), and when
two sources disagree about what we spent, the honest thing is to publish the number from
the source that is not us.

* **Window:** `2026-08-10T00:00:00Z` → `2026-08-11T05:10:22Z` (region `ap-southeast-2`)
* **Generated:** `2026-08-11T05:05:29Z` by `scripts/aws/cloudwatch_evidence.py`
* **Nothing was provisioned to produce this page.** No log group, no IAM role or policy, no
  alarm, no dashboard, no metric filter, no Bedrock invocation logging, no `terraform apply`.
  The absence is *read back and recorded* in `bedrock-metrics.json` under
  `account_state`, not merely asserted here.

> **AWS confirms this repository token for token.** The 300-second CloudWatch bucket at `2026-08-10T22:00:00Z` contains the three calls `evidence/aws/probe/bedrock-probe.json` recorded, and 3 of 3 models agree exactly on invocations and on both token counters — `amazon.titan-embed-text-v2:0` 36 in, `au.anthropic.claude-haiku-4-5-20251001-v1:0` 22 in / 8 out, `cohere.embed-v4:0` 0 in. Every other number on this page is AWS's alone; that one is both sides saying the same thing.

---

## 1 · The bill, per model, from AWS's own token counters

| model | invocations | input tokens | output tokens | USD/1k in | USD/1k out | USD |
|---|---|---|---|---|---|---|
| `amazon.titan-embed-text-v2:0` | 7,542 | 1,026,175 | 0 | 0.00002 | 0 | **0.020524** |
| `au.anthropic.claude-haiku-4-5-20251001-v1:0` | 33 | 33,535 | 7,857 | 0.001 | 0.005 | **0.072820** |
| `au.anthropic.claude-sonnet-4-5-20250929-v1:0` | 1 | 15 | 7 | 0.003 | 0.015 | **0.000150** |
| `cohere.embed-english-v3` | 331 | 59,345 | 0 | 0.0001 | 0 | **0.005934** |
| `cohere.embed-v4:0` | 10 | 0 | 0 | 0.00012 | 0 | **0.000000** |
| `global.cohere.embed-v4:0` | 330 | 92,089 | 0 | 0.00012 | 0 | **0.011051** |

**Total model spend: USD 0.110479** — 11.0 US cents, across 6 models
and 8,247 invocations AWS served and counted.

The single dearest line is `au.anthropic.claude-haiku-4-5-20251001-v1:0` at USD 0.072820 across 33 invocations, while `amazon.titan-embed-text-v2:0` cost USD 0.020524 across 7,542. Generation is roughly 811x the per-call cost of embedding here, which is worth knowing before anyone designs a memory system that reasons where it could retrieve.

### The arithmetic, shown

```
    amazon.titan-embed-text-v2:0
      1,026,175 / 1000 * 0.00002 = 0.02052350  (embedding model: input billed only)
    au.anthropic.claude-haiku-4-5-20251001-v1:0
      33,535 / 1000 * 0.001 = 0.03353500  +  7,857 / 1000 * 0.005 = 0.03928500
    au.anthropic.claude-sonnet-4-5-20250929-v1:0
      15 / 1000 * 0.003 = 0.00004500  +  7 / 1000 * 0.015 = 0.00010500
    cohere.embed-english-v3
      59,345 / 1000 * 0.0001 = 0.00593450  (embedding model: input billed only)
    cohere.embed-v4:0
      0 / 1000 * 0.00012 = 0.00000000  (embedding model: input billed only)
    global.cohere.embed-v4:0
      92,089 / 1000 * 0.00012 = 0.01105068  (embedding model: input billed only)

    model total                       USD 0.11047868
    CloudWatch GetMetricStatistics    110 / 1000 * 0.01 = 0.00110000
    ------------------------------------------------------------------
    grand total                       USD 0.11157868
```

The second line is the cost of *reading the evidence*: 110
`GetMetricStatistics` requests at the published USD 0.01 per 1 000.
It is counted because a cost report that prices the models and treats its own instrument as
free is not a cost report — and it is an **upper bound**, because CloudWatch's free tier may
absorb it entirely and this page does not assume a discount it has not verified.
`ListMetrics`, `DescribeAlarms`, `ListDashboards` and
`GetModelInvocationLoggingConfiguration` are not billed per request.

### One model AWS saw and this fleet cannot price

No entry exists in `USD_PER_1K_TOKENS` for `apac.anthropic.claude-3-5-sonnet-20241022-v2:0` (it appears in `reconciliation.json` with `usd_total: null`, not with a zero — an unpriced model must look like a hole in the ledger, never like a free one). It carries **0 input and 0 output tokens** in AWS's own counters, so the hole cannot be hiding spend: the invocation was refused before any token was consumed.

### What the prices are, and are not

Prices come from `scripts/aws/_common.py::USD_PER_1K_TOKENS`, whose own basis line reads:

> published on-demand list price for ap-southeast-2, recorded 2026-08-11; declared, not measured — no bill or Price List API response backs this number

**No bill has been read.** The AWS Price List API is not in this fleet's permission set and
requesting it would be an account change. So the *token counts* are measured and AWS's; the
*unit prices* are declared. Any figure on this page is therefore best read as
"AWS says we consumed these tokens, and at list price that is this much".

---

## 2 · Against the budget

| bound | value | source | this fleet |
|---|---|---|---|
| single-program ceiling | USD 0.50 | `_common.py::RUN_USD_CEILING`, AWS-execution plan §6.6 | USD 0.111579 — **22.32%** |
| project ceiling | USD 5.00/month | founder's standing instruction ("a few dollars" approved) | USD 0.111579 — **2.232%** |
| design target | ≈ USD 0.03/month | AWS-execution plan §1.7 | one-time spend is 3.72x one month of the design target |

The whole fleet — the probe, a 2 000-vector Titan index, a three-arm embedding benchmark,
the ANN proof's corpus, the recall harness's cache, the live agent lane, and every failed,
throttled and abandoned attempt AWS counted along the way — came to **USD 0.1116**.
That is the one-time build, not a monthly rate. It sits under the USD 0.50 single-program
ceiling by a factor of 4.5.

The design target in AWS-execution plan §1.7 is a **steady-state monthly** figure and this
is a **one-time build** figure, so the third row of that table compares two different
quantities and is reported only so nobody else does the division and reads it as an
overrun. Steady state for this system is zero: nothing is deployed.

### The ongoing cost of the committed evidence is **zero**

Everything under `evidence/aws/` is a static JSON or Markdown file in git. Nothing polls,
nothing is deployed, no schedule runs, no metric is published, no alarm evaluates, no log
group retains bytes. Re-running `scripts/aws/cloudwatch_evidence.py` costs at most
USD 0.0011 and invokes no model; *not* re-running it
costs nothing at all. A judge reading these files incurs no AWS charge of any kind.

CockroachDB Cloud spend is not AWS spend and is out of scope for this page; the
`mainline-dev` cluster is SERVERLESS Basic under a USD 25 cap.

---

## 3 · Why these numbers are not the repository's numbers

AWS counts **HTTP requests it served**. This repository's ledgers count **corpus units they
priced**. They are different quantities and they do not agree:

| model | repo-claimed input tokens | AWS-observed input tokens | delta |
|---|---|---|---|
| `amazon.titan-embed-text-v2:0` | 298,498 | 1,026,175 | +727,677 |
| `apac.anthropic.claude-3-5-sonnet-20241022-v2:0` | — | 0 | — |
| `au.anthropic.claude-haiku-4-5-20251001-v1:0` | 17,429 | 33,535 | +16,106 |
| `au.anthropic.claude-sonnet-4-5-20250929-v1:0` | — | 15 | — |
| `cohere.embed-english-v3` | 94,634 | 59,345 | -35,289 |
| `cohere.embed-v4:0` | — | 0 | — |
| `global.cohere.embed-v4:0` | 121,954 | 92,089 | -29,865 |

An em dash in the repo-claimed column means *no ledger among the three reconciled artefacts
names that model* — which is not the same as zero spend. `reconciliation.json` carries a
second column for the probe, ANN and recall artefacts, which do name some of them.

Every non-zero delta is named and quantified per model in
[`reconciliation.json`](cloudwatch/reconciliation.json): probes made before this fleet's
first program existed, requests AWS refused outright, embedding passes that filled a cache
and wrote no ledger of their own, and byte-identical texts priced many times by a ledger
that prices a corpus and once by an AWS that bills a request.

Two obvious candidate causes are carried there at **zero**, because CloudWatch's own
counters rule them out rather than because they were forgotten: SDK and application retries
after a `ThrottlingException`, and the embedding pass's 70 recorded failures. A throttled
request is counted under `InvocationThrottles` and *not* under `Invocations` — proved in
this window by Titan showing 61,552 throttles against 7,542 invocations — so adding retries to our side would have
"explained" several hundred invocations that were never there, and shrunk the honest gap.

What the named causes do not reach is published as `unattributed_residual` and is **not** spread across them until it vanishes: `amazon.titan-embed-text-v2:0` +3,620 invocations; `au.anthropic.claude-haiku-4-5-20251001-v1:0` +11 invocations; `cohere.embed-english-v3` +77 invocations; `global.cohere.embed-v4:0` +81 invocations. The honest reading is that the fleet's own development iterations — passes killed by throttling, benchmark attempts abandoned mid-sweep, ANN proofs re-run against a cold cache — produced them. AWS counted every one; no artefact in this repository records them; so no artefact in this repository claims them.

The direction cuts both ways. For Titan, AWS saw **more** than the repository claims — every
abandoned pass is in AWS's counter and in nobody's ledger. For the Cohere arms, the
repository claims **more** than AWS saw — the benchmark priced 1 167 corpus units per arm
against a journal of 248 distinct texts, and byte-identical texts cost one call.

**This page uses AWS's larger Titan number.** Pricing from our own ledger would have
understated the bill, and a cost report that rounds in its author's favour is not evidence.
