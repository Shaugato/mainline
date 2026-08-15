<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->
<!-- prose-hygiene: register -->
<!--
This file quotes forbidden sentences beside true ones so a founder reading it at 02:00 can see
which is which. It therefore carries the `prose-hygiene: register` marker, in the same form
docs/demo/story-and-script-plan.md, docs/submission/MUST-NOT-CLAIM.md and
docs/demo/research/r6-honesty.md use. Every quoted offence sits on a line that also carries an
explicit negation (`MUST NOT SAY:`), which the scanner's documented negation exemption reads as
stating the rule rather than committing it. If this path is ever added to a prose scanner's
sweep list, the scanner must PRINT that it skipped this file, so "not scanned" is never read as
"passed".
-->

# VO-CLOSE — the naming block, 50 s, and the 2 s end card

**Worker W3 · the naming block** · 2026-08-15 · master at HEAD · live origin
`https://ihuuyvm4z6nfuktihnkey77fpy0eyrhj.lambda-url.ap-southeast-1.on.aws`

*(No commit id is written here. `claim_hygiene.py`'s `HYG-sha-literal` rule fired on the tree
hash this header carried in its first draft, and the rule is right: a commit id cannot be
chosen, so none is ever written or spoken. §9 records that firing rather than hiding it.)*

Binding: `docs/demo/story-and-script-plan.md` §3 and §4 (R-O, R-M, R-K, R-L, R-N),
`docs/demo/research/r6-honesty.md` A6 and A7, and `docs/demo/film/BEATS.yaml` for timing.
The plan's own §3 carries an arithmetic inconsistency; **§0.1 states it plainly, resolves it
against W1's spine rather than against my own brief, and preserves the alternate in §5.5.**

**`claim_hygiene.py --check` verdict — recorded per R-B: §9.** It went RED first, on five
findings including one in this file's own header. The red, the fix and the green are all in §9.

---

## 0 · WHAT THIS BLOCK IS, AND THE ONE RULE THAT SHAPES EVERY FRAME

**RULING R-O, restated because it decides the layout:** the naming block is **on-screen text
over live picture, never a stock slide.** The operator app, the gate transcript and the memory
panel stay behind the overlay for all 50 s. A judge who pauses at 2:20 sees the AWS list *and*
the refusal that the AWS list carried, in the same frame. Devpost's tip says "text overlay or
slide"; overlay-over-live satisfies it and a slide does not survive the question *"is that a
picture of your product, or a picture of a list?"*

Two consequences that bind W4 and W5:

1. **Nothing is cut to black between 2:00 and 2:50.** The picture underneath keeps whatever it
   was showing at 2:00 (B8's `persisted false` block, then the read-only `DEMO-MOC-0001` cut).
   Overlays fade in over it; the picture does not change to suit them.
2. **The overlay is text a judge can `Ctrl-F` in this repository.** Every line in §2–§5 carries
   an evidence path in the same table. If a line has no path, it does not go on screen.

### 0.1 · THE ARITHMETIC — an inconsistency in the plan, resolved by the spine, not by me

The plan's §3 table gives in-times `C1 2:00 · C2 2:12 · C3 2:28 · C4 2:42`, calls the block
**48 s**, and states the film's total as **170 s (2:50)** = 120 + 48 + 2. **Those figures cannot
all be true at once.** Those four in-times with an 8 s C4 sum to **50 s**, not 48, and put the
end card's out-point at 2:52. Two readings were available: C4 = 6 s (block 48 s, film 170 s), or
C4 = 8 s (block 50 s, film 172 s).

**`docs/demo/film/BEATS.yaml` rules it, and this file follows the spine.** W1 went first and
owns the shape; `BEATS.yaml` fixes `c4 dur: 8, ends: 170`, `close_s: 50`, `total_s: 172`, with
the note *"174 − 172 = 2 s of margin above the hard stop."* A film cannot carry two timings, and
a voice-over file is not the place to overrule the spine. **My own brief's figure of 48 s is
therefore not met, deliberately and on the record**, because meeting it would put this file 2 s
out of step with `BEATS.yaml` and W5's `ONSCREEN-TEXT.yaml` behind it.

| block | in | dur | out | `BEATS.yaml` |
|---|---|---:|---|---|
| C1 · the loop | `2:00` | 12 s | `2:12` | `c1 t:120 dur:12 ends:132` |
| C2 · AWS | `2:12` | 16 s | `2:28` | `c2 t:132 dur:16 ends:148` |
| C3 · CockroachDB | `2:28` | 14 s | `2:42` | `c3 t:148 dur:14 ends:162` |
| C4 · the limit, and the URLs | `2:42` | **8 s** | `2:50` | `c4 t:162 dur:8 ends:170` |
| **naming block** | | **50 s** | | `close_s: 50` |
| end card | `2:50` | 2 s | `2:52` | `end t:170 dur:2 ends:172` |

**The 48 s variant is preserved, complete, in §5.5** — C4 at 6 s with a one-sentence limit, film
total 170 s. If the orchestrator wants the plan's printed 48/170 rather than the spine's 50/172,
that section is the whole change and nothing else in this file moves. **Do not improvise the
choice at 02:00; it is made here or it is made by whoever owns `BEATS.yaml`.**

### 0.2 · WORD RATE — this block is slower than the demo, deliberately

The demo runs at **1.88 w/s** (plan §2). The naming block runs at **1.64 w/s** — 82 words over
50 s. It is lower on purpose: the on-screen text is doing the naming, and a voice reading a list
*over* a list gives a judge two things to parse and lets him finish neither. Every block below
leaves **0.4–3.4 s of air** at its tail, and that air is where a judge's eye finishes the line.

| block | spoken words | `BEATS.yaml` budget | at 1.9 w/s | block dur | air at tail |
|---|---:|---:|---:|---:|---:|
| C1 | 20 | 22 | 10.5 s | 12 s | 1.5 s |
| C2 | 24 | 24 | 12.6 s | 16 s | 3.4 s |
| C3 | 22 | 22 | 11.6 s | 14 s | 2.4 s |
| C4 | **16** | **15** | 8.4 s | 8 s | **−0.4 s** |
| **total** | **82** | **83** | **43.1 s** | **50 s** | **6.9 s** |

**C4 is one word over `BEATS.yaml`'s budget and 0.4 s over its block, and that is flagged rather
than hidden.** The overrun buys the sanctioned wording of the film's closing line intact —
§5.3 shows the arithmetic and §5.3.1 carries a 15-word cut that fits inside 8 s exactly if the
edit must be frame-clean. Everything else is at or under budget; the block is 1 word under.

### 0.3 · THE CRITERION RAIL — how the four unanswered second sentences get answered

`r1-judging` §1.1 prints the five criteria in full and T6 names the finding: the **second**
sentence of each criterion is unanswered surface, and four of them are scoring hooks nothing in
`docs/submission/` addresses. Plan §3 rules that C4 must answer them.

**C4 is 8 s. Four clauses plus an honest limit plus two URLs cannot be read in 8 s.** So they do
not all arrive at 2:42. They arrive **one per block, in a thin bottom rail** that builds across
the whole 50 s and is complete when the film freezes on C4:

| appears at | criterion, in the organiser's own words | the clause, on the rail |
|---|---|---|
| `2:00` | *"Does it demonstrate insight into what makes agentic systems different from traditional apps?"* | **the database is in the reasoning loop, as the thing that constrains the agent** |
| `2:12` | *"Does the agent use the tools correctly and safely?"* | **`persisted: false` — this endpoint cannot write** |
| `2:28` | *"Is it used for more than toy queries — state, embeddings, context, or transactional data at real scale?"* | **transactional state, read inside the same `SERIALIZABLE` transaction as the decision — and no scale is claimed** |
| `2:42` | *"Has the team thought about resilience, access control, and what happens when things go wrong?"* | **the refusal itself; `42501` on 256/256 ungranted pairs; a ledger that publishes what did not run** |

**Rail typography.** Criterion words in quotation marks, small, italic; the clause after an
arrow, same size, not italic. It reads as *an answer to a question the judge recognises*, which
is the whole value of putting it there. Each line sits beside the block that already proved it,
so a judge who pauses has the evidence and the claim in one frame.

The four clauses hold for 50, 38, 22 and 8 seconds respectively — 118 clause-seconds on screen,
against the 8 seconds a single C4 card could have given them. **Not one of them claims scale**;
the third refuses to, in its own second half, on screen.

---

## 1 · EVIDENCE DISCIPLINE — the three labels, and why the second one exists

Every service and every feature named in §3 and §4 carries one of three labels, printed on
screen in the group heading, not hidden in a footnote:

| label | means | example |
|---|---|---|
| **IN THIS REQUEST** | it executed while the `POST /v1/demo/gate-run` a judge just watched was in flight | `CHECK gate_closed_when_issued` |
| **IN THE APPLY / IN THIS DATABASE, EARLIER** | it was applied into the account, or it ran against this database before the shoot and its output is what the request read | `fn_check_project` |
| **NOT IN THIS PATH** | it is exercised in this repository and had nothing to do with the refusal | Amazon Bedrock |

The second label is the one that makes the block honest. Three named things fall into it and a
looser film would quietly file them under the first: `fn_check_project`, the recursive-CTE blame
closure, and `42501`. **§6.1 is the finding that produced that discipline and it is the most
important thing in this file.**

---

## 2 · C1 · THE LOOP — `2:00` → `2:12` · 12 s

### 2.1 · What stays behind the overlay

B8's frame: `persisted false · single_transaction true · isolation SERIALIZABLE`, and the memory
panel's three columns still filled. The overlay lands *on top of* the panel it is naming.

### 2.2 · Overlay text — exact

```
S T O R E                      R E T R I E V E                 A C T

mainline.event                 mainline_meas.recall_run        mainline.permit
mainline.blame_edge            mainline.clause_blame_current   CHECK gate_closed_when_issued
mainline.clause_blame_closure    (view · DISTINCT ON, gen DESC)  -> 23514
  append-only, generation-                                     mainline.fn_permit_merge_gate
  versioned; superseded,                                         -> P0001
  never deleted

occurred_at                    started_at                      refused at
2019-03-14T06:20:00Z           2026-08-02T03:00:00Z            <THIS RUN>

                               obligation materialised
                               2026-08-02T03:00:10Z
                               ten seconds
```

Strap, small, full width, under the three columns:

```
every date above is a column value · no AS OF SYSTEM TIME produced any frame of this film
```

Rail line 1 fades in at `2:04`:

```
"what makes agentic systems different from traditional apps?"
   -> the database is in the reasoning loop, as the thing that constrains the agent
```

### 2.3 · Spoken — 20 words

> **"An incident from 2019. A retrieval, and ten seconds later, the obligation. And the refusal
> you just watched, re-deriving it."**

**20 words · 10.5 s at 1.9 w/s · 1.5 s of air.** The three words STORE · RETRIEVE · ACT are on
screen in large type and are **not spoken** — saying them while they are that size is the kind
of narration that makes a judge stop reading.

Delivery: the three sentence-fragments land on the three columns. The last one lands on `ACT`
and then stops. Do not add "…and that's the loop."

### 2.4 · Tense — the one line in this block that can go wrong

**MUST NOT SAY:** *"Watch it remember."* · *"The system just retrieved the incident and blocked
the permit."* · anything present-tense about the retrieval. The recall is a record, not an event
happening now; it is `mainline_meas.recall_run`, every field a column, `started_at` two weeks
before the shoot. What runs **now** is the third column. The VO above is past tense for the
first two fragments and present participle only for the third (`re-deriving`), which is the one
that is true of the request in flight.

**Do not compute a "days before" figure out loud.** R-K: nothing spoken is unseen. If a
day-count appears it is computed in the browser from two columns both on screen and labelled
`derived` — never spoken from memory.

### 2.5 · Evidence — every line above

| on-screen line | what proves it |
|---|---|
| `mainline.event` · `occurred_at 2019-03-14T06:20:00Z` | `GET /v1/permits/{permit_id}/blocking-checks` → `/data/checks/0/precursor/occurred_at`, live, 200, 2,408 B (`docs/demo/research/r2-memory.md` §3.1); seeded `verticals/mainline/db/seeds/demo/demo_world.sql:264-284`; table `verticals/mainline/db/migrations/0033_event.sql` |
| `mainline.blame_edge` | `GET /v1/clauses/{clause_uuid}/ancestry` → `/data/blame_edges/0` (`basis asserted_document`, `state active`); table `verticals/mainline/db/migrations/0037_blame_edge.sql`; seeded `demo_world.sql:299-314` |
| `mainline.clause_blame_closure` · append-only, generation-versioned | `verticals/mainline/db/migrations/0038_clause_blame_closure.sql`; the append-only weld is `0128j_trg_refuse_mutation_clause_blame_closure.sql`; rationale for "superseded, never deleted" is `0039_clause_blame_current.sql`'s rationale block |
| `mainline.clause_blame_current` · view · `DISTINCT ON`, gen DESC | `verticals/mainline/db/migrations/0039_clause_blame_current.sql:118-135`; sole legal read path, enforced by `scripts/grep_closure_readpath.py` |
| `mainline_meas.recall_run` · `started_at 2026-08-02T03:00:00Z` | `verticals/mainline/db/seeds/demo/demo_permit.sql:239-252` — the literal is `TIMESTAMPTZ '2026-08-02 03:00:00+00'` at `:250`; served live by `GET /v1/recall-runs/{run_id}`, 200, 2,223 B |
| obligation `materialised 2026-08-02T03:00:10Z` | `demo_permit.sql:306-323` — the literal is `TIMESTAMPTZ '2026-08-02 03:00:10+00'` at `:321`; column `materialised_at` on `mainline.blocking_check` (`0058_blocking_check.sql`) |
| `CHECK gate_closed_when_issued -> 23514` | `evidence/deploy/live-gate-run.json` → `/data/beats/1/{sqlstate,constraint,constraint_source}`; constraint declared `verticals/mainline/db/migrations/0050_permit.sql:114` |
| `mainline.fn_permit_merge_gate -> P0001` | `evidence/deploy/live-gate-run.json` → `/data/beats/2/{sqlstate,constraint}`; function `verticals/mainline/db/migrations/0115_fn_permit_merge_gate.sql` |
| `refused at <THIS RUN>` | **live slot.** Filled from the shoot's own response: `/data/beats/1/refusal/observed_at`. Reference value on the recorded run is `2026-08-14T22:10:33Z` — **re-derive from your own run, per R-K; do not caption the reference value.** |
| `no AS OF SYSTEM TIME produced any frame of this film` | `verticals/mainline/db/seeds/demo/demo_world.sql:149-151` (measured GC window 4500 s); `DEMO-HONESTY.md:147-152`; scanner rule `MNC-09-time-travel` |

---

## 3 · C2 · AWS — `2:12` → `2:28` · 16 s

### 3.1 · Overlay text — exact

Two labelled groups and one labelled exception. **The grouping is the honesty**: a flat list
would let "S3" borrow the credibility of "Lambda", and S3 was never in the request.

```
AWS  ·  IN THIS REQUEST

  AWS Lambda                  arm64 · mainline-demo-api
  Lambda Function URL         authorization_type = NONE   (the founder's explicit choice)
  SSM Parameter Store         /mainline/demo/cockroach_dsn
  AWS IAM                     one execution role; one inline policy, GetParameter on that one name


AWS  ·  IN THE APPLY THAT CREATED IT        24 created · 0 changed · 0 destroyed

  Amazon S3                   Terraform state · versioned · SSE-S3 · public access blocked
  CloudWatch alarms + SNS     the cost guard: three alarms on three timescales into one topic,
  + AWS Budgets               a responder that sets reserved concurrency to zero, and the budget


  Amazon Bedrock  —  EXERCISED IN THIS REPOSITORY.  IT IS NOT IN THIS REQUEST PATH.
  Claude on au.* inference profiles and Titan v2 embeddings, ap-southeast-2 (Sydney).
  The database is aws-ap-southeast-1 (Singapore).  There is no end-to-end Australian
  residency and we do not claim one.
  The refusal you just watched involved no model at all, and that is the point.
```

Rail line 2 fades in at `2:16`:

```
"Does the agent use the tools correctly and safely?"
   -> persisted: false — this endpoint cannot write
```

### 3.2 · Spoken — 24 words

> **"Everything here is either in that request or in the apply that created it. Bedrock is
> exercised in this repository — not in this path."**

**24 words · 12.6 s at 1.9 w/s · 3.4 s of air · exactly `BEATS.yaml`'s `c2` budget of 24.** The
dash is a real pause, not a comma: the last five words are the sentence a judge does not expect,
and they need the silence in front of them. The service names are **not read aloud** —
they are on screen, larger than they would be in speech, and a judge reads a list faster than
anyone can say it. The VO's whole job is to tell him the list has a rule, and to say the
Bedrock line out loud, because that is the sentence a judge does not expect and will remember.

### 3.3 · Evidence — every service named

| on-screen line | label | what proves it |
|---|---|---|
| **AWS Lambda** · arm64 · `mainline-demo-api` | in this request | `evidence/deploy/APPLIED.md:14-21` (24 created, `demo_url` on line 16); the serving artefact is `out/lambda/mainline-demo-api-arm64.zip`, named at `APPLIED.md:168-170` and measured as the deployed bytes at `evidence/deploy/console-mode.json:18`; the resource is `infra/modules/demo-api/main.tf:327-335` (`architectures = [var.architecture]`), name composed at `infra/envs/demo/main.tf:250` (`local.api_function_name = "${var.name_prefix}-api"`) with `name_prefix` defaulting to `mainline-demo` at `infra/envs/demo/variables.tf:68` |
| **Lambda Function URL** · `authorization_type = NONE` | in this request | `infra/modules/demo-api/main.tf:425-432`; the choice and its reason are recorded in the founder's own terms at `evidence/deploy/APPLIED.md:200-203` and `evidence/deploy/LIVE.md:74-76`; the URL itself is the origin every frame of this film is shot against |
| **SSM Parameter Store** · `/mainline/demo/cockroach_dsn` | in this request | `evidence/deploy/APPLIED.md:42-43` — the pre-parameter answers named the exact key verbatim in their own error — and `APPLIED.md:189-210` for why the value is placed by hand; the resource grant is `infra/modules/demo-api/main.tf:318-320` (`aws_iam_role_policy.dsn_access`) |
| **AWS IAM** · one execution role, one inline policy | in this request | `infra/modules/demo-api/main.tf:260-272` (`aws_iam_role.this`, `basic_execution` attachment) and `:318-325` (`dsn_access`); the role's narrowness is the point and it is measured at `evidence/deploy/APPLIED.md:191-203` — `mainline_api` holds CONNECT 1 · USAGE 37 · SELECT 66 · UPDATE 3 · INSERT 8 · EXECUTE 29 (`evidence/deploy/LIVE.md:73`), against `ALL on 417 objects` for the admin role |
| **Amazon S3** · Terraform state, versioned, SSE-S3, public access blocked | in the apply | `evidence/deploy/APPLIED.md:23-25` — the state bucket was the first mutating action of the whole deploy, versioned, all four public-access settings blocked, SSE-S3, noncurrent versions expiring at 30 days |
| **CloudWatch alarms + SNS + AWS Budgets** · the cost guard | in the apply | `evidence/deploy/APPLIED.md:18-21` — thirteen of the twenty-four applied resources: three alarms on three timescales into one SNS topic, a responder calling `PutFunctionConcurrency(ReservedConcurrentExecutions=0)`, plus the budget; module `infra/modules/cost-guard/main.tf`; corroborated by `docs/demo/research/r6-honesty.md` A6 |
| **Amazon Bedrock** · not in this request path | not in this path | `evidence/aws/probe/bedrock-probe.json`, `evidence/aws/probe/raw-haiku-converse.json` (a live `bedrock-runtime:Converse` against `au.anthropic.claude-haiku-4-5-20251001-v1:0` in `ap-southeast-2`), `evidence/aws/embeddings/manifest.json` (Titan v2, 2,060 vectors of width 1,024), `evidence/deploy/aws-live.json`; census row `evidence/tool-usage/aws-services.json` → `rows.aws_bedrock_runtime` / `rows.aws_bedrock_embeddings`, both `EXERCISED` |
| residency, stated as the split | — | `docs/demo/research/r6-honesty.md` A1 and the scanner rule `MNC-02-residency`: the cluster is `aws-ap-southeast-1` (Singapore); only Bedrock inference is `ap-southeast-2` (Sydney) |

### 3.4 · What is NOT on this slide, and why — read this before adding anything

* **Never a CDN and never a distribution.** None exists on this account. `infra/modules/demo-api/main.tf`
  contains a conditional grant that is **not taken** — `create_cloudfront_invoke_grant =
  var.url_authorization_type == "AWS_IAM"`, and the applied value is `NONE`. The word is banned
  on screen and in speech by `CAMERA-STRINGS.yaml:127-131`.
* **No console window.** The cost guard exists and is applied; a metrics console on camera is
  forbidden by the same authority. Say "a cost guard that sets reserved concurrency to zero",
  film the overlay, and film nothing else.
* **Never CMEK and never PrivateLink**, not even as "we would add" — `MNC-03`.
* **No latency figure of any kind.** One of the applied alarms is named for a duration
  percentile. **That alarm's name does not go on screen and is not spoken.** An alarm threshold
  is not a performance claim, and a judge cannot be expected to make that distinction in the
  half-second the overlay gives him. This repository contains no load profile.
* **No CloudTrail, KMS, EventBridge or S3 Object Lock.** All four are real code and none is
  applied — `evidence/tool-usage/aws-services.json` marks them `DESIGNED` and
  `docs/HONESTY.md` says the object-lock check is one of the seven cryptographic checks that
  **did not run**. They belong in the written submission, not on a slide that says "in this
  request".

---

## 4 · C3 · CockroachDB — `2:28` → `2:42` · 14 s

### 4.1 · Overlay text — exact

Two columns. Left is what fired inside the request a judge just watched; right is what ran
against this database earlier and what the client has read back elsewhere.

```
CockroachDB  ·  IN THIS REQUEST                 CockroachDB  ·  IN THIS DATABASE, EARLIER

CockroachDB Cloud (Basic)                       mainline.fn_check_project
  aws-ap-southeast-1 (Singapore)                  a PL/pgSQL trigger function. It overwrote
  CCL v26.2.5                                     this obligation's severity and virulence
  read live from GET /v1/health, not typed        from the blame closure when the row was
                                                  written. The gate reads its output.
SERIALIZABLE                                      It did not run in this request.
  one transaction, three savepoints,
  rolled back                                   recursive CTE  (WITH RECURSIVE)
                                                  the blame-closure writer,
CHECK constraint                                  db/queries/closure_write.sql:152.
  gate_closed_when_issued        -> 23514         THIS world's closure row carries
                                                  computed_by = demo_world.sql
PL/pgSQL trigger function                         projector_ver = demo-1.
  mainline.fn_permit_merge_gate  -> P0001         It did not run in this request.

user-defined enum                               42501
  mainline.subject_state                          read back by this same client during the
  ((state != 'merged':::mainline.subject_state)   deploy, one HTTP request at a time; and
   OR (open_blocking = 0:::INT8))                 256/256 ungranted pairs refused in
  the enum is inside the refusal message           privilege conformance.
                                                  It did not run in this request.
composite foreign keys
  blocking_check -> clause_version
    (clause_uuid, commit_id)
  permit_event -> subject_transition
    (subject_kind, from_state, to_state)


One cluster.  One region.  This repository holds no load profile, and we do not claim scale.
```

Rail line 3 fades in at `2:32`:

```
"Is it used for more than toy queries — state, embeddings, context, or transactional data
 at real scale?"
   -> transactional state, read inside the same SERIALIZABLE transaction as the decision
      — and no scale is claimed
```

**Reading order for the highlight sweep** (W5): `23514` → `P0001` → the enum inside the
predicate → the right-hand column's three `It did not run in this request.` lines. Four
landings in 14 s. Everything else is there to be paused on, not to be swept.

### 4.2 · Spoken — 22 words

> **"Two refusals, two SQLSTATEs, one SERIALIZABLE transaction. The enum in that predicate is
> ours. One cluster, one region, and no scale claim."**

**22 words · 11.6 s at 1.9 w/s · 2.4 s of air.** The last clause is the concession and it is
spoken, not buried: Axis 1's second sentence asks *"at real scale"* and the honest answer is on
the rail, in the strap, and in the founder's mouth. **Conceding it out loud costs one second and
buys the only thing that makes the other twenty-one words believable.**

### 4.3 · Evidence — every feature named

| on-screen line | label | what proves it |
|---|---|---|
| **CockroachDB Cloud (Basic)** · `aws-ap-southeast-1` · `CCL v26.2.5` | in this request | `evidence/deploy/LIVE.md:14-22` — `cluster_version` read back from the deployed `GET /v1/health`, alongside `deploy_chain_applied 271 of 271`; tier and single region are stated at `docs/demo/research/r6-honesty.md` A7; the `ccloud` transcript is `evidence/ccloud/cluster-list.txt` (census row `evidence/tool-usage/crdb-features.json` → `rows.crdb_cloud_ccloud`, `EXERCISED`) |
| **`SERIALIZABLE`** · one transaction, three savepoints, rolled back | in this request | `evidence/deploy/live-gate-run.json` → `/data/transaction/{isolation,single_transaction,savepoints,disposition}` — the payload declares it; the read-only witness is `cluster_logical_timestamp()`, opened and closed timestamps identical; census row `rows.crdb_serializable`, `EXERCISED`, anchor `packages/trappoint-model/src/trappoint_model/cluster.py:222` (a write-skew pair REFUSED on the pinned node) |
| **`CHECK` constraint `gate_closed_when_issued`** → `23514` | in this request | declared `verticals/mainline/db/migrations/0050_permit.sql:114`; fired at `evidence/deploy/live-gate-run.json` → `/data/beats/1`, `constraint_source: reported`; census row `rows.crdb_check_constraints`, `EXERCISED` |
| **`mainline.fn_permit_merge_gate`** → `P0001` | in this request | `verticals/mainline/db/migrations/0115_fn_permit_merge_gate.sql` (re-derivation at `:62-69`); fired at `live-gate-run.json` → `/data/beats/2`, `constraint_source: parsed`, message *"re-derived open obligation count is 1 while the projected counter reads zero"*; census row `rows.crdb_triggers`, `EXERCISED`, anchor `0115_fn_permit_merge_gate.sql:77` |
| **user-defined enum `mainline.subject_state`** | in this request | `verticals/mainline/db/migrations/0011_type_subject_state.sql:27`; and it is **inside the refusal the client read back** — `live-gate-run.json` → `/data/beats/1/message` contains `'merged':::mainline.subject_state` verbatim. This is the cheapest feature to prove in the whole block: the type name is in the error string, not in a caption |
| **composite foreign keys** | in this request | `verticals/mainline/db/migrations/0058_blocking_check.sql:109` — the obligation row's own two-column FK onto `mainline.clause_version (clause_uuid, commit_id)`; and `0059_permit_event.sql:66` — a **three-column** FK onto `mainline.subject_transition (subject_kind, from_state, to_state)`, enforced when beat 4's merge writes a permit event |
| **`mainline.fn_check_project`** | earlier, in this database | `verticals/mainline/db/migrations/0100_fn_check_project.sql:59-83`, welded by `0120_trg_check_project.sql`. The seed supplied `0, 'routine', 0` (`demo_permit.sql:318`, its own comment: *"projected over by fn_check_project"*) and the live row reads `severity 4, virulence blood_major` — `GET /v1/permits/{permit_id}/blocking-checks` → `/data/checks/0/{severity,virulence}`. **The proof that it ran is the delta, and the delta is live.** It fired when the row was written, not while the film's request was in flight |
| **recursive CTE (`WITH RECURSIVE`)** | earlier / elsewhere | `verticals/mainline/db/queries/closure_write.sql:152` — `WITH RECURSIVE anc (event_id, depth)`, the sanctioned writer of `0038_clause_blame_closure`; it walks `mainline.event_edge` (`0034_event_edge.sql:42` quotes the shape in its own header, and its rationale records that the only cycle guard is `depth < 64`). **See §6.1 — this world's closure row was written by the seed, and the overlay says so in the same breath as the feature name** |
| **`42501`** | earlier / elsewhere | `docs/STATE-OF-THE-BUILD.md:179-193` §12.6 — `scripts/qa/privilege_conformance.py`, **256/256 ungranted pairs refused with `42501`, 0 differences**, and that negative direction is falsifiable and was falsified; and `evidence/deploy/LIVE.md:58-71`, where five privilege gaps were found *"one HTTP request at a time"* against the deployment. See §6.2 for the half of §12.6 that is **not** claimed |
| `no load profile` · `no scale claim` | — | `docs/submission/JUDGING-AXES.md:69` already concedes it; `docs/demo/research/r1-judging.md` T6 names the concession as correct and asks only that the *positive* answer be given beside it, which the rail does |

### 4.4 · What is NOT on this slide

* **No vector search, no `EXPLAIN` plan.** The C-SPANN work is real
  (`0031_clause_embedding.sql:149`, `evidence/aws/ann/ann-proof.json`) and **the demo world
  seeds no embeddings and runs no vector query.** `MUST NOT SAY:` *"vector search found the
  precursor."* The retrieval channel is `blame_ancestry` and `tau_applied = 0` —
  `demo_permit.sql:181-185` says in its own words that no threshold was consulted, so none may
  be claimed.
* **No changefeed and no CDC.** There is no `CREATE CHANGEFEED` in any of the 271 migrations;
  `v_changefeed_health` returns 0 rows; the census marks `rows.crdb_changefeed` **`DESIGNED`**.
  What the trigger writes is an **outbox row**, `mainline_ops.outbox`, `check_opened`.
  `MUST NOT SAY:` *"changefeeds propagate the lesson."*
* **No time travel.** `MNC-09`. Every date on screen is a column value and C1's strap says so.
* **No row-level security claim.** `MNC-01` is this project's own headline caveat: RLS is
  evaluated by the same server a cluster admin owns, so it stops a confused query and never the
  administrator.
* **Never "multi-region", never "survives a region failure", never "tamper-proof", and never "split-view resistant" in any form, on any screen, in any caption.**
  Basic tier, one region; one witness, `q = 1`; tamper-**evident**, never tamper-proof.
* **No `merged_commit`, no `clearance_digest`, no `schema_fingerprint` on this slide.** R-K
  permits `merged_commit` in the demo; there is no room for it here, and
  `clearance_digest` may never be captioned as a constant — four runs on 2026-08-15 produced
  four different digests, and if it were ever stable the rollback proof would be broken.

---

## 5 · C4 · THE LIMIT, AND THE TWO URLS — `2:42` → `2:50` · 8 s

### 5.1 · Why the limit closes the film and not the product

The last thing a judge hears should be the sentence a competitor could not say. Every other
project's closing seconds are a claim. This one's is a **concession stated more precisely than
anyone asked for**, and it is the single most credible eight seconds available to us, because a
film that has spent two minutes saying *"the database refuses"* has spent two minutes earning
the right to say what it cannot do.

### 5.2 · Overlay text — exact

```
                        THE LIMIT WE WILL NOT DRESS UP

Nothing in this data model separates a considered disposition from a rubber stamp.
It makes the question unavoidable, the record precise, the worst stamp non-representable.
We measure deliberation and never threshold it.


"what makes agentic systems different from traditional apps?"
   -> the database is in the reasoning loop, as the thing that constrains the agent

"Does the agent use the tools correctly and safely?"
   -> persisted: false — this endpoint cannot write

"Is it used for more than toy queries ... at real scale?"
   -> transactional state, read inside the same SERIALIZABLE transaction as the decision
      — and no scale is claimed

"resilience, access control, and what happens when things go wrong?"
   -> the refusal itself; 42501 on 256/256 ungranted pairs; a ledger that publishes
      what did not run


github.com/Shaugato/mainline
https://ihuuyvm4z6nfuktihnkey77fpy0eyrhj.lambda-url.ap-southeast-1.on.aws
```

The first three rail lines are **already on screen** at 2:42 — they arrived at 2:00, 2:12 and
2:28 and have not moved. At 2:42 the fourth arrives and the rail lifts from the bottom strip
into the block, all four together, under the limit. **Nothing in C4 is read for the first time
except the limit, the fourth clause, and the two URLs.** That is what makes eight seconds enough
for a card this dense — and it is what would still make six enough, if §5.6 is taken.

### 5.3 · Spoken — 16 words, two sentences

> **"Nothing here separates a considered disposition from a rubber stamp. We measure
> deliberation, never threshold it."**

**16 words · 8.4 s at 1.9 w/s, in an 8 s block · one word over `BEATS.yaml`'s `c4` budget of
15.** The overrun is declared in §0.2 rather than absorbed quietly, and the reason is that the
alternatives all cost something worse:

| candidate | words | what it costs |
|---|---:|---|
| *"Nothing here separates … rubber stamp. We measure deliberation, never threshold it."* | **16** | 0.4 s. **Chosen.** |
| *"… We measure deliberation and never threshold it."* | 17 | 0.9 s, and adds nothing the comma does not |
| *"… Deliberation is measured, never thresholded."* | 15 | fits exactly; passive voice on the film's last line |
| *"… We never threshold it."* | 14 | fits, but *it* now has no antecedent — see §5.3.1 |
| *"Nothing separates a considered disposition from a rubber stamp."* alone | 10 | drops the scope word **here**, which is the whole difference between a limit and a slander |

**Sentence one cannot go below ten words with its scope intact.** `MNC-06`'s own text is
*"Nothing in this data model distinguishes a considered disposition from a rubber stamp"*;
`here` is the shortest honest stand-in for *in this data model*, and dropping it turns a
statement about this deployment into a statement about safety records in general, which is not
ours to make.

The second and third sentences of the on-screen limit are **not spoken**: *"the worst stamp
non-representable"* and *"it makes the question unavoidable, the record precise"* are the precise
form, and a judge who pauses gets them exactly. Paraphrasing them at speed is how a concession
turns back into a boast.

**The two URLs are not read aloud.** A judge reads a URL faster than anyone can say one, and
four seconds of spoken hostname is the worst trade in the film.

#### 5.3.1 · If the edit must land inside 8 s exactly

> **"Nothing here separates a considered disposition from a rubber stamp. Deliberation is
> measured, never thresholded."**

**15 words · 7.9 s · 0.1 s of air · exactly `BEATS.yaml`'s budget.** Passive voice, and it fits.
Take it only if the cut must be frame-exact. The 16-word form is better spoken, and its 0.4 s of
overrun lands in a **silent** end card where it costs nothing but that card's first few frames.

### 5.4 · Evidence

| on-screen line | what proves it |
|---|---|
| the limit, all three sentences | `docs/submission/MUST-NOT-CLAIM.md` and scanner rule **`MNC-06-rubber-stamp`**, whose own text reads *"Nothing in this data model distinguishes a considered disposition from a rubber stamp… Claiming otherwise is the project's single worst available overclaim."* The wording on screen is the plan §5's TRUE INSTEAD column, unparaphrased |
| *"the database is in the reasoning loop"* | Cockroach Labs' own architecture framing, quoted at `docs/demo/research/r1-judging.md` §4(b); and it is literal here — the decision is a `CHECK` constraint and a PL/pgSQL trigger, `live-gate-run.json` → `/data/beats/1` and `/data/beats/2` |
| `persisted: false` — this endpoint cannot write | `evidence/deploy/live-gate-run.json` → `/data/persisted` (`false`), `/data/transaction/disposition` (`rolled_back`), and `/data/persistence_check/self_evidence/minted_disposition_rows_after_rollback` (`0`), keyed on a `uuid4` no other writer holds |
| transactional state in the same `SERIALIZABLE` transaction | `live-gate-run.json` → `/data/transaction/{isolation,single_transaction}`; the memory read at gate time is `0115_fn_permit_merge_gate.sql:62-69` and `:91-97`, inside that transaction |
| `42501` on 256/256 ungranted pairs | `docs/STATE-OF-THE-BUILD.md:179-193`; the caveat that must travel with it is §6.2 below |
| *"a ledger that publishes what did not run"* | `docs/HONESTY.md`; `docs/CI-STATE.md`; `evidence/tool-usage/README.md`'s three-verdict table, where `NOT-AVAILABLE` exists *"so Bedrock Rerank appears… as a row with a reason, rather than as a silence"* |
| `github.com/Shaugato/mainline` | `README.md:25` — public since 2026-08-11, root `LICENSE` Apache-2.0; `docs/submission/SUBMISSION.json:21` `repo_url` |
| the live URL | `evidence/deploy/LIVE.md:8`; `evidence/deploy/APPLIED.md:16` |

**R-M holds.** No camera is pointed at `docs/submission/SUBMISSION.json` while its `demo_url`
reads `UNRESOLVED`. The live URL on screen is the origin this film was shot against, read from
the deploy record and confirmed by the request in devtools — not read off that file.

### 5.5 · THE 48 s / 170 s VARIANT — the whole change, in one place

Take this only if the orchestrator prefers the plan's printed **48 s block / 170 s film** over
`BEATS.yaml`'s **50 s / 172 s**. It is one edit and it is entirely inside C4.

| | spine (primary) | 48 s variant |
|---|---|---|
| C1 · C2 · C3 | `2:00` 12 s · `2:12` 16 s · `2:28` 14 s | **unchanged** |
| C4 | `2:42` → `2:50`, **8 s** | `2:42` → `2:48`, **6 s** |
| end card | `2:50` → `2:52` | `2:48` → `2:50` |
| naming block | 50 s | **48 s** |
| film total | 172 s | **170 s** |
| C4 spoken | 16 words (§5.3) | **10 words**, one sentence |

C4's spoken line becomes the first sentence alone:

> **"Nothing here separates a considered disposition from a rubber stamp."**

**10 words · 5.3 s at 1.9 w/s · 0.7 s of air.** *"We measure deliberation and never threshold
it"* stays **on screen** in §5.2's overlay, unspoken, where it is already printed in its exact
sanctioned form. **The overlay in §5.2 does not change. The rail does not change. Nothing in
C1–C3 changes.** Block total becomes 76 words over 48 s = 1.58 w/s.

**What the variant costs:** the film's last spoken clause becomes a statement of the limit
without the statement of what is done instead, so a judge who is listening rather than reading
hears only the concession. That is why it is the alternate and not the primary.

---

## 6 · THE END CARD — `2:50` → `2:52` · 2 s · silent

(`BEATS.yaml` `end t:170 dur:2 ends:172`. Under the §5.5 variant this becomes `2:48` → `2:50`;
its content does not change.)

```
                              M A I N L I N E

        the lesson a past incident taught, as a constraint the database enforces

    github.com/Shaugato/mainline
    https://ihuuyvm4z6nfuktihnkey77fpy0eyrhj.lambda-url.ap-southeast-1.on.aws

    SYNTHETIC CORPUS · EVERY SITE, PERMIT, INCIDENT AND PERSON HERE IS AUTHORED
```

* **No voice-over.** Two seconds is a held frame, not a sentence.
* **First and only appearance of the product name.** Plan §1.2: there is no title card before
  the demo; the name appears in the closing block, where it has been earned.
* **The watermark line is the R-L string**, unchanged, because this film's site seeds as
  `demo_site` and not as a Kestrel site (`demo_world.sql:72-76`). If the operator UI does render
  Kestrel Resources, `DEMO-HONESTY.md:35-36`'s committed string is used verbatim instead, and
  the deviation is recorded in `ONSCREEN-TEXT.yaml` (W5's file, not this one).
* **The URLs are the same two strings as C4**, in the same order, so a judge who paused on C4
  and is now typing does not have to re-find them.

---

## 7 · FINDINGS HANDED ON — three, and the first one changed this file

### 7.1 · THE RECURSIVE-CTE BLAME CLOSURE DID NOT RUN IN THIS WORLD, AND THE PLAN'S C3 LIST WOULD HAVE SAID IT DID

**This is the finding.** Plan §3's C3 list and my own brief both name `recursive CTE blame
closure` in the flat CockroachDB list, beside `SERIALIZABLE` and the `CHECK` constraint. Those
two fired in the filmed request. **The recursive CTE did not fire in this world at all.**

`verticals/mainline/db/seeds/demo/demo_world.sql:333-341` says so in its own words, as a
recorded amendment rather than an oversight: the sanctioned writer
`verticals/mainline/db/queries/closure_write.sql` is *"a parameterised top-level statement into
which the projector binds ten positional values — a seed file that `scripts/deploy/seed_demo.py`
applies as ONE text cannot call it."* So the seed writes the closure row directly, and the row
it writes carries its own confession in two columns a judge can read live:

```
computed_by   = verticals/mainline/db/seeds/demo/demo_world.sql
projector_ver = demo-1
```

— `demo_world.sql:342-359`, served by `GET /v1/clauses/{clause_uuid}/ancestry` →
`/data/closure/{computed_by,projector_ver}` (`docs/demo/research/r2-memory.md` §3.2). I also
checked the request path directly: **there is no `RECURSIVE` anywhere under
`verticals/mainline/apps/demo-api/src/`**, so nothing in the filmed request runs one either.

Naming it in the "IN THIS REQUEST" group would have been a fake of exactly the class this
project reverted a worker for. The overlay therefore names it in the **right-hand column**, with
`computed_by` on the same line — the same treatment Bedrock gets, for the same reason, and the
qualifier costs nothing because the disclosure is already a live column value.

**Handed on to W1, W5 and W7 — and it is already downstream.** `docs/demo/film/BEATS.yaml`'s
`c3.on_screen` inherited the flat list verbatim: *"the CHECK constraint; the two trigger
functions; the recursive CTE blame closure; and the SQLSTATEs the client read back — 23514,
P0001 and the ungranted-pair 42501."* Three of those items — one trigger function
(`fn_check_project`), the recursive CTE, and `42501` — did **not** run in the filmed request,
and `c3.on_screen` reads as though all of them did. `BEATS.yaml` is W1's file and I have not
touched it; the split in §4.1 is what C3 must render, and if `ONSCREEN-TEXT.yaml` takes the
flat list instead, the film ships a false line. **The split is not a style choice.**

### 7.2 · `42501` — CITE THE FALSIFIABLE HALF, NEVER THE OTHER ONE

`docs/STATE-OF-THE-BUILD.md` §12.6 records **two** baselines: `120/120` granted pairs reachable
and `256/256` ungranted pairs refused with `42501`.

**Only the second may go on screen.** The positive direction is **not falsifiable as run** —
`main()` calls `apply_matrix()` unconditionally before probing, in borrowed-database mode too,
so the probe repairs the defect it is meant to detect and a missing grant cannot make it red
(`:189-193`). The negative direction *is* falsifiable and *was* falsified, with a precise red.

**MUST NOT SAY:** *"120 out of 120 granted pairs verified."* That number is real and its
verification is not, and for an `authorization_type = NONE` endpoint it is not the direction
that matters anyway. The overlay carries `256/256` alone. Handed to W7 for the clearance sheet.

### 7.3 · `evidence/tool-usage/aws-services.json` IS STALE WITH RESPECT TO THE APPLY — REPO HYGIENE, NOT AN ON-SCREEN PROBLEM

The census is a **pure function of the source tree** by design (`evidence/tool-usage/README.md`
§"Why there is no timestamp"), and it was generated before 2026-08-14. It therefore still reads:

| row | census verdict | census basis, verbatim in part | what `evidence/deploy/APPLIED.md` records |
|---|---|---|---|
| `aws_lambda` | `DESIGNED` | *"NOTHING IS DEPLOYED. A plan exists and a plan is not an apply"* | 24 created, `demo_url` live |
| `aws_ssm_parameter_store` | `DESIGNED` | *"NOTHING DEPLOYED — no parameter has been written and no role exists"* | the parameter is placed and `/v1/health` reads `ok=true` |
| `aws_iam` | `DESIGNED` | *"eleven `aws_iam_policy_document` data sources exist… offline"* | the execution role and `dsn_access` are applied |
| `aws_cloudwatch` | `EXERCISED` | *"METRICS READ, NOTHING PROVISIONED"* | thirteen of twenty-four applied resources are the guard |

**Nothing on screen is affected** — C2 cites `APPLIED.md` and `LIVE.md`, which are the later and
authoritative measurements, and the live request in devtools is itself the proof. But a judge who
opens the census reads *"NOTHING IS DEPLOYED"* beside our overlay saying `IN THIS REQUEST`, and
that is a bad thirty seconds we can avoid.

**The fix is one command** — `python scripts/submission/capture_tool_evidence.py` — and it
belongs to the owner of `scripts/**` and `evidence/**`, not to this worker: the plan forbids me
touching either. **Handed to the orchestrator, before the shoot.** I did not run it and I did not
edit those files.

---

## 8 · THE BANNED LIST, AS A CHECKLIST TO READ ALOUD BEFORE THE TAKE

Every one of these is banned **on screen and in speech** for the whole 50 s. The list is the
brief's, plus the three C3/C4 additions this file's evidence work produced.

Every row of the left column begins with **never**, because that is what the column is: the
never-list, not a list of things anyone is tempted to say.

| the never-list — on screen and in speech | authority |
|---|---|
| never CloudFront, never a CDN, never "edge", never a metrics console window | `CAMERA-STRINGS.yaml:127-131`; r6-honesty A6 |
| never CMEK, never PrivateLink, not even as "we would add" | `MNC-03` |
| never "multi-region", never "survives a region failure" | r6-honesty A7 — Basic tier, one region |
| never "vector search found the precursor" | r6-honesty A7 — this world seeds no embeddings |
| never "changefeeds propagate", never "CDC stream" — say **outbox row** | no `CREATE CHANGEFEED` in 271 migrations |
| never "Australian residency" — state the split instead | `MNC-02` — database Singapore, inference Sydney |
| never a p50, never a p99, never a production latency, and never **the duration-percentile alarm's name** | plan §5; this repository holds no load profile |
| never "our CI is green", never "we proved it in CI" | nothing in CI has ever asserted this URL |
| never "tamper-proof", and never "split-view resistant" in any form | r6-honesty A10 — tamper-**evident**; one witness, `q = 1` |
| never "120/120 granted pairs verified" | §7.2 — that direction is not falsifiable as run |
| never "the recursive CTE computed this closure" | §7.1 — `computed_by` says the seed did |
| never "`fn_check_project` runs when you press ISSUE" | §4.3 — it ran when the row was written |
| never the year 2024, in any sentence | R-E |
| never a camera on `docs/submission/SUBMISSION.json` | R-M |

**The one to say out loud in the room before rolling:** *no number in these fifty seconds is
rounded, and no number is spoken that is not on screen.* R-K.

### 8.1 · Two clearance notes for W7, so a true string is not mistaken for a banned one

* **`mainline.blame_edge` is a table, and it stays on screen.** The banned word is *edge* in the
  content-delivery sense, forbidden by `CAMERA-STRINGS.yaml:127-131` alongside a CDN. It is not
  a ban on a substring: `mainline.blame_edge` is a real relation
  (`verticals/mainline/db/migrations/0037_blame_edge.sql`) and it is the middle hop of the STORE
  column in C1. Renaming it on screen to dodge a scanner would be a falsification of a schema.
  Likewise `mainline.event_edge`, cited in §4.3.
* **`create_cloudfront_invoke_grant` is quoted in §3.4 as evidence of a branch that is NOT
  taken.** It never goes on screen and is never spoken; it appears in this document only to
  prove the applied value is `NONE` and that no distribution was ever created.

---

## 9 · `claim_hygiene.py --check` — THE VERDICT, AND THE RED THAT PRECEDED IT (R-B)

`docs/demo/film/` is outside every `TARGET_GLOBS` entry, so scanner coverage is not lost — it is
invoked by hand.

### 9.1 · The first run went RED, and that is recorded rather than quietly repaired

**A verbatim paste of a hygiene failure re-commits the offence** — the transcript quotes the
banned line back, so the record of the red becomes a red. That was measured, not reasoned: a
first attempt to paste the failing output turned 5 findings into 12, the seven new ones being
the paste itself. So the record below names **the rule and the line** and never the sentence,
which is lossless for anybody holding the file.

```
$ .venv/Scripts/python.exe scripts/demo/claim_hygiene.py --check docs/demo/film/VO-CLOSE.md
  scanned 1 file(s) against 21 rules
  ... 5 claim-hygiene violation(s)
$ echo $?
1
```

| line, first draft | rule that fired | what was wrong |
|---|---|---|
| 19 | `HYG-sha-literal` | my own header carried a seven-hex tree literal |
| 283 | `MNC-03` | a prohibition written with "No …" — and plain *no* is **not** one of the scanner's negation markers |
| 392 | `MNC-14` | the same, split across a wrapped line so the marker and the phrase were not on one line |
| 593 | `MNC-03` | a never-list table row whose cell named the control without a marker |
| 600 | `MNC-14` | the same, one row down |

Four of the five are §8's own never-list. The scanner cannot tell a banned phrase in a
*prohibition* from one in a *claim* unless the line itself carries a negation marker, and those
four lines carried none. **The fix was to write the prohibitions as prohibitions** — every
never-list row now begins with the word `never`, which is both the marker the scanner reads and
the honest way to write that column. Nothing was exempted, no rule was edited, no marker was
bolted onto a sentence that was not already a denial, and no phrase was deleted to dodge a rule.

The fifth was a real defect in my own header, and `HYG-sha-literal` exists to catch exactly it.
It is gone; the header now says *master at HEAD* and says why.

### 9.2 · The verdict, after the fix, pasted verbatim

```
$ .venv/Scripts/python.exe scripts/demo/claim_hygiene.py --check docs/demo/film/VO-CLOSE.md
  scanned 1 file(s) against 21 rules
  claim hygiene OK
$ echo $?
0
```

**Nothing in this file was softened to reach that line.** The two rules it comes closest to are
`MNC-06-rubber-stamp` (§5.2 states the limit) and `MNC-02-residency` (§3.1 states the split);
both clear the scanner through the documented negation exemption, because both sentences are
denials — which is what they are supposed to be.

### 9.3 · Falsification, because a hygiene check that has never fired is decoration

```
$ .venv/Scripts/python.exe scripts/demo/claim_hygiene.py --self-test
  planted 4 violation families, scanner fired on 4
    RED   [MNC-01] ...      RED   [MNC-15] ...
    RED   [HYG-bare-invariant] ...      RED   [HYG-sha-literal] ...
  self-test OK - the scanner goes red on every planted family
$ echo $?
0
```

The four planted sentences are elided here for the reason §9.1 measured: quoting them would
re-plant them in this file. They are in `SELF_TEST_FIXTURE` in `scripts/demo/claim_hygiene.py`,
where anybody can read them, and in `scripts/demo/fixtures/claim-hygiene-red.md`, which is
committed, deliberately non-compliant, and asserted non-zero by `.github/workflows/claims.yml`.

Two independent demonstrations that the check can go red **on this exact file**: the planted
fixture above, and §9.1, which is this file failing on its own first draft.

---

## 10 · DISSENT — one, on the record, and not acted on

**Plan §2.2's scope-cut ladder rung 5, and `BEATS.yaml`'s `cut_ladder` step rank 5, cut C4 from
8 s to 4 s** — *"the spoken limit; the end card carries the URLs alone."* I disagree, and I have
not acted on it.

If the film must find four more seconds after ranks 1–4, I would take them from **C2**
(16 s → 12 s), which is a list a judge pauses on rather than listens to, and whose spoken line
is already 3.4 s shorter than its block. C4 is the only sentence in the film a competitor cannot
say.

Cutting C4 to an end card removes the film's spoken answer to Axis 4's second sentence
(*"what happens when things go wrong"*) and the spoken half of Axis 1's *"at real scale"*
concession — two of the four scoring hooks `r1-judging` T6 identified as unanswered surface —
and it removes the concession that makes the preceding two minutes credible. `BEATS.yaml`'s own
`why` for that step says as much: *"it answers the criteria's own second sentences, which nothing
else in the film answers."* It ranks the step last for exactly the reason it should not be taken.

**The ladder is the lead's ruling and W1's spine, and it binds. This is a dissent in my own
file, per plan §4's standing permission, and nothing in §0–§8 acts on it.** Two mitigations, if
the cut is taken:

1. **The rail survives.** Three of the four criterion clauses arrived at 2:00, 2:12 and 2:28 and
   are still on screen; only the fourth is lost.
2. **Move the fourth clause up.** Attach it to C2 instead of C4 — access control is an AWS-block
   subject (`authorization_type = NONE` and a narrow role are already on that overlay), so the
   clause reads naturally there and costs C2 one line and zero seconds. **That is a two-word
   edit to `ONSCREEN-TEXT.yaml`, and it means rung 5 costs no criterion answer at all.** W5 and
   W7 should hold it ready rather than discover it on the day.
