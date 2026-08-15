<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->
<!-- prose-hygiene: register -->
<!--
This file quotes forbidden sentences beside true ones, in the same three-column form
docs/submission/MUST-NOT-CLAIM.md and docs/demo/research/r6-honesty.md use. It therefore
carries the `prose-hygiene: register` marker. If this path is ever added to a prose
scanner's sweep list, the scanner must PRINT that it skipped this file, so "not scanned"
is never read as "passed".
-->

# STORY AND SCRIPT PLAN — the two minutes, and the fifty seconds after them

**Story lead** · 2026-08-15 · tree `4af05e1` · live origin
`https://ihuuyvm4z6nfuktihnkey77fpy0eyrhj.lambda-url.ap-southeast-1.on.aws`

This is the direction document for seven workers. It fixes the shape, rules on everything the
research left open, and hands each worker a self-contained brief. **It is not the script.**
The script is `docs/demo/film/VO-DEMO.md` and its siblings, which the workers write.

---

## 0 · THE FILM IN ONE PARAGRAPH

A site supervisor opens the permit-to-work form his crew needs before they open a live
machine, and presses **ISSUE**. His own software refuses him, because a database underneath it
re-derived an obligation out of a 2019 incident's blame ancestry and would not let the merge
through. Somebody then forces the counter the gate reads to zero — and the gate refuses again,
because it does not trust the number. A safety engineer answers the obligation with a signed
disposition, the permit issues, and none of it persisted. Fifty seconds of on-screen text then
names the AWS services and the CockroachDB features that did it.

**Total running time: 170 s (2:50).** 120 s demo + 48 s naming block + 2 s end card. Rule is
under 3:00; the repository's own CI hard-fail for the other cut is 176 s. **Hard stop 174 s.**

---

## 1 · THE OPENING — problem, audience, and the promise, inside eight words

### 1.1 The spoken opener (t=0:00, over the operator's own screen, cursor already on ISSUE)

> **"This is the form a site supervisor signs before a crew opens a live machine — and in a
> moment, a database is going to refuse to let it through."**

30 words · ~16 s at 1.9 w/s. It runs into the click; the click should land while the sentence
is still finishing. Adopted from `r4-story.md` §6 unchanged — it names **who it is for** (a
site supervisor) and **what the software is** in eight words, it promises the refusal instead
of describing a problem in the abstract, and every clause is checkable.

### 1.2 The on-screen strap that states the problem (t=0:00–0:07, one line, lower third)

Devpost asks for the problem and the audience in one sentence up front, and the spoken opener
spends its words on the promise. So the problem sentence is **written, not spoken** — it costs
zero seconds:

> **The lesson a past incident taught is a memo people forget. Here it is a constraint the
> database enforces — for the supervisors and safety engineers who issue permits to work.**

**RULING (story lead):** these two sentences together satisfy the organiser's "state what
problem you're solving and who it's for in one sentence up front" **and** Devpost's "explain
what your app does in the first few seconds", without a title card. **There is no title card
before the demo.** The product name appears in the closing block, where it has been earned.
Authority: r1-judging (the organiser's own "get to the live demo within the first 20 to 30
seconds"); r4-story §2.2 (Devpost's screencast guidance); r4-story §6's rejection table, which
already ruled `s03-title` belongs at the end.

### 1.3 What the first thirty seconds contain, measured against the organiser's instruction

| t | what a judge sees |
|---|---|
| `0:00` | Live product. The supervisor's own permit form, on the deployed origin, URL bar in frame. |
| `0:12` | A real click, a real in-flight request, a genuine pending state. |
| `0:22` | **The first refusal — `23514 · gate_closed_when_issued`**, inside the supervisor's app. |

**First refusal at 0:22.** The committed console cut reaches its first refusal at 0:51
(`SHOT-LIST.yaml:241`); this one clears the organiser's bar by eight seconds without spending
any of the running-time margin.

---

## 2 · THE BEAT SHEET — 120 s, nine beats

Adopted from `r4-story.md` §5 with the four amendments ruled in §3 below. Durations sum to
**120 s exactly**. Word budgets assume **1.9 w/s** (114 wpm).

| # | in | dur | beat | what is on screen | VO w | axis |
|---|---|---|---|---|---|---|
| **B0** | `0:00` | 12 s | **THE ORDINARY MOMENT** | Permit form. `DEMO-PTW-0001`, blue cold-work edge, `[ DISPOSITIONED ]` chip, `refs/permits/demo-0001`, validity line, hazard card. Cursor resting on **ISSUE**. Founder types the tail of the work description on camera. | 24 | Impact |
| **B1** | `0:12` | 10 s | **THE ATTEMPT** | Click. Real pending state, real in-flight `POST /v1/demo/gate-run`. DevTools already docked. Nothing else moves. | 16 | Impact |
| **B2** | `0:22` | 14 s | **THE REFUSAL** — *filmed calm* | Refusal band inside the operator app: `REFUSED · 23514 · gate_closed_when_issued · source: reported`, the database's own predicate `((state != 'merged':::mainline.subject_state) OR (open_blocking = 0:::INT8))`, and the payload's remedy line. DevTools in frame ~2 s: one request, `200`, real byte count, real TTFB. | 26 | Tech Impl |
| **B3** | `0:36` | 18 s | **WHY — THE MEMORY LOOP** | Three labelled panels **STORE → RETRIEVE → ACT**. Two timestamps large: `2026-08-02T03:00:00Z` → `2026-08-02T03:00:10Z`. `n_candidates 1 · n_blocking 1 · index g1`. Then the projection: seed `severity 0 / routine` beside live `severity 4 / blood_major`. | 34 | **Agentic Memory** |
| **B4** | `0:54` | 10 s | **THE HUMAN MOVE** | The MAINLINE gate-transcript panel, beneath the app. Beat 3's own `statement` string on screen — `UPDATE mainline.permit SET open_blocking = 0 …; CALL mainline.merge_permit(…)` — under the payload's own label: *"THE ATTACK: force the projected counter to zero out of band, then merge again."* Counter reads `open_blocking 0`; the CHECK is now **satisfied**. | 19 | Creativity |
| **B5** | `1:04` | 16 s | **REFUSED ANYWAY — the peak** | `REFUSED · P0001 · mainline.fn_permit_merge_gate`, verbatim: *"re-derived open obligation count is 1 while the projected counter reads zero"*, beside `open_blocking 0 / open_blocking_derived 1`. The diagnosis chip renders **weaker**: `constraint_source: parsed`, `naa: null`, `naa_reason: not_computable`, MUS `kind: capability_gap`. **Hold in silence after the line.** | 30 | **Creativity + Tech Impl** |
| **B6** | `1:20` | 18 s | **THE ANSWER IS A QUESTION** | Safety engineer's disposition screen. Three defeaters as questions, no global "N/A". Beside them the lattice: `mechanism_absent` costs rank 4 + a second signer + a foreign org + a predicate + re-assertion; `emergency_override` costs rank 5 and dies in 12 hours. Sign as `demo.signer`. | 34 | Impact + Readiness |
| **B7** | `1:38` | 12 s | **AND THEN IT ADMITS** | `ADMITTED · 00000`. `state merged`, `open_blocking 0`, `head_seq 3`, `merged_commit 4fbbd371…`. The permit screen turns from blocked to issued. | 22 | Tech Impl |
| **B8** | `1:50` | 10 s | **NONE OF IT HAPPENED** | `persisted false · single_transaction true · isolation SERIALIZABLE`; the minted `disposition_id` and `minted_disposition_rows_after_rollback: 0`; identical opened/closed logical timestamps. Then one cut: `DEMO-MOC-0001`, read-only, still carrying `open_blocking 1` from the same 2019 closure. | 20 | **Readiness** |
| | | **120 s** | | | **225 w** | |

225 w / 120 s = **1.88 w/s**.

### 2.1 The emotional map — where the weight sits, and where it must not

B0–B1 **low, deliberately**. B2 **medium; resist inflating it** — a `CHECK` refusing is table
stakes and every database can do it. B3 **rising**, and it is the film's only tenderness: not
sympathy for a person, recognition of a fact that outlived everyone who knew it. B4 **tension,
played matter-of-fact — the shrug, not the villainy.** **B5 is the peak and takes all of it.**
B6 release, B7 relief, B8 cool.

**The single most likely way to get this wrong is trying to make B0–B3 sad.** There is nobody
to be sad about; the seed says so in its own column (§4, R-E). Every second spent reaching for
it is stolen from B5.

### 2.2 Scope-cut ladder — pre-committed, never improvised at 02:00

1. **B8's second half** (the change-request cut) — 4 s. Weakest-supported on camera: use case
   two is told, not driven.
2. **B0** 12 s → 8 s. Keep the cursor-on-button frame; lose the establishing pan.
3. **B6** 18 s → 14 s. Two defeaters instead of three; keep the lattice.
4. **B7** 12 s → 9 s.
5. **Naming block C4** 8 s → 4 s (end card only).

**Never cut B3 or B5.** B3 is a rules requirement — *"footage showing the CockroachDB memory
layer at work"*. B5 is the product.

---

## 3 · THE CLOSING FIFTY SECONDS — naming the surfaces

**RULING (story lead):** the naming block is **on-screen text over live picture, not a stock
slide.** Devpost's tip says "text overlay or slide"; r5-craft's tell #17 says a segment naming
services should run with the real surfaces behind it. Both are satisfied by overlay-over-live.
A judge can pause and confirm every line against the repository.

| # | in | dur | on screen (text a judge can pause on) | VO |
|---|---|---|---|---|
| **C1** | `2:00` | 12 s | Three words, large: **STORE · RETRIEVE · ACT**, each with its table and its timestamp under it. | "That was the whole loop…" |
| **C2** | `2:12` | 16 s | **AWS** — `Lambda (arm64, mainline-demo-api)` · `Lambda Function URL (authorization_type = NONE)` · `SSM Parameter Store /mainline/demo/cockroach_dsn` · `IAM` · `S3 (Terraform state, versioned, SSE-S3, public access blocked)` · `CloudWatch Alarms + SNS + AWS Budgets — the cost guard` · and on its own line, labelled: `Amazon Bedrock — exercised in this repository, NOT in this request path`. | names them |
| **C3** | `2:28` | 14 s | **CockroachDB** — `CockroachDB Cloud (Basic) · aws-ap-southeast-1 · CCL v26.2.5` · `SERIALIZABLE` · `CHECK constraint gate_closed_when_issued` · `PL/pgSQL trigger functions fn_permit_merge_gate / fn_check_project` · `recursive CTE blame closure` · `composite foreign keys` · `user-defined enum mainline.subject_state` · `SQLSTATEs read back by the client: 23514 · P0001 · 42501`. | names them |
| **C4** | `2:42` | 8 s | The honest limit, then the repo URL and the live URL. | 2 sentences |
| — | `2:50` | 2 s | End card. | — |

**C2/C3 name only what fired or was applied.** Never *CloudFront*, never *CDN*, never *edge*,
never a CloudWatch console window on screen, never CMEK, never PrivateLink, never
"multi-region", never "vector search found the precursor", never "changefeeds". Authority:
r6-honesty A6/A7, `CAMERA-STRINGS.yaml:127-131`.

**C4 must answer the criteria's own second sentences**, which appear nowhere in
`docs/submission/` and are four unanswered scoring hooks (r1-judging). One clause each, and
each honest: *access control and what happens when things go wrong* → the refusal itself, plus
`42501` on 256/256 ungranted pairs and a published honesty ledger; *used for more than toy
queries* → the memory is transactional state read inside the same `SERIALIZABLE` transaction
as the decision — **and we do not claim scale**; *correctly and safely* → `persisted: false`,
the endpoint cannot write; *what makes agentic systems different* → the database is in the
reasoning loop as the thing that constrains the agent.

---

## 4 · RULINGS — everything the research left open, with authority

Each ruling is binding on all seven workers. Where a worker disagrees, they may write a
dissent into their own file; they may not act on it.

**R-A · Where the film lives.** All new artefacts go under `docs/demo/film/`. **Nothing in
`verticals/mainline/demo/script/` is edited, added to or deleted this wave.** *Authority:*
`.github/workflows/claims.yml` triggers on `verticals/mainline/demo/**`;
`claim_hygiene.py` `TARGET_GLOBS` reaches `verticals/mainline/demo/script/*.md|*.yaml`; and
`validate_shotlist.py` validates the committed 2:51 cut in CI. A second film dropped in beside
it risks a red claims lane on a green baseline. Which cut is submitted is the orchestrator's
call; my recommendation is on the record in §7.

**R-B · Scanner coverage is not lost, it is invoked by hand.** `docs/demo/film/` is outside
every glob, so **every worker runs `.venv/Scripts/python.exe scripts/demo/claim_hygiene.py
--check <their files>` and pastes the verdict into their file's header block.** *Authority:*
the scanner's own `--check FILE...` mode (`scripts/demo/claim_hygiene.py` docstring). A file
that must quote a forbidden sentence carries `<!-- prose-hygiene: register -->` and quotes it
on a line that also carries an explicit negation (`MUST NOT SAY:`), which the scanner's
documented negation exemption reads as stating the rule.

**R-C · One press, progressive disclosure — and the screen says so.** The film contains
**one** `POST /v1/demo/gate-run`. Beats 3 and 4 are revealed from the response already in
hand, by controls labelled as reveals. *Authority:* `FIRST-RUN.md:29-33` (R11) sanctions the
pattern; `POST /v1/permits/{id}/merge` measured **423 `demo_subject_write_protected`**, so
independent per-beat merges are impossible against the shared subject; and three presses would
be three identical four-beat responses, which multiplies the ambiguity rather than removing
it. **Non-negotiable companion:** a persistent line, small, from B2 onward —

> *All four beats arrived in one already-rolled-back SERIALIZABLE transaction. This panel
> reveals them in order as a reading aid; every timing shown is the server's.*

— plus **"one request · four beats · response received `<generated_at>`"** in the panel
header. Without those, the reveal is indistinguishable from faked sequencing.

**R-D · The falsification is a reveal, never a re-enactment, and it happens in a different
register.** A supervisor's app does not contain a control that forges a counter. B4/B5
therefore surface a **MAINLINE gate-transcript panel beneath the operator app** — infrastructure
becoming visible under the product — and that panel renders the payload's own beat-3
`statement` and `label` strings verbatim. **No fake admin console, no simulated SQL prompt, no
UI-side decrement of the counter.** *Authority:* r4-story §5.1 B4; r6-honesty A17.1; the
founder's own frame (MAINLINE is underneath the system).

**R-E · One world only — the demo-api world.** On screen: `DEMO-PTW-0001`, `DEMO-INC-0001`,
`2019-03-14`, `demo_site`, `demo.signer`, `DEMO-MOC-0001`. **Never** `WO-88213`, never the
2013 gland-seal fire, never "two contractors burned", never `INC-2013-044`, never
`INC-2024-0117`, **never the year 2024 in any sentence.** *Authority:* r6-honesty A15.3 (two
permits, two databases, on purpose); r4-story §1.1; `docs/decisions/demo-use-cases.md:126-142`
(the propagation payload may not be narrated at all).

**R-F · The incident is a severity, not an injury.** Say *"a severity-four stored-energy
release during intrusive work."* Never "a worker was hurt", never "someone died", nothing
about a person. **Leave the `SYNTHETIC —` prefix visible on screen; do not crop it out to make
the frame prettier.** *Authority:* `demo_world.sql:276-278` — the narrative's own last clause
is that it *describes nobody*; r4-story §1.3.

**R-G · `demo.signer` is the acceptor, not the issuing authority.** The column behind that
name is `exposure_receipt.actor_sub` — *who the obligation was shown to* — which is HSG250
Figure 1 element 10, acceptance. Render them on the acceptance row. The **Issue** row stays
unsigned until B7. *Authority:* r3-operator §10's own flagged ambiguity, resolved here against
its §6.1 suggestion, because the column's meaning is unambiguous and the role assignment is
not.

**R-H · The four fields with no column are typed by a human, on camera.** HSG250 Figure 1
elements 1 (permit title), 3 (job location free text), 5 (description of work) and 8 (PPE)
have no column in this deployment. Elements 1/3/5 are **input controls carrying visibly typed
text, with no provenance chip**, and the founder types the tail of element 5 on camera in B0.
Element 8 renders **empty and labelled** *"not carried by this deployment"*. **The on-screen
convention that makes this checkable: every server value carries a provenance chip; nothing
typed does.** Hard-coding a plausible crew, plant name or PPE list is forbidden — it is the
same class of act as reshaping a seed to match a constant. *Authority:* r3-operator §5.3.

**R-I · The change request is told, never driven.** `DEMO-MOC-0001` appears once, read-only,
in B8, showing `open_blocking 1` and its own three defeater codes, with the approve control
**rendered disabled and the obligation named as the reason**. **MUST NOT SAY:** *"watch the
same debt block the change request."* There is no merge route (measured 404) and no diff:
`mainline.change_request` carries no title, description, proposed text, requester or target
clause. **A hard-coded "proposed" clause string is forbidden.** *Authority:* r6-honesty A13.5;
r3-operator §5.4.

**R-J · The silence receipt is OUT of the 120 s.** It carries one `staged: true` field
(`receipt.bound.statement`, reproduced from spec and produced by no column) and would need a
STAGED chip and a caveat sentence to be shown honestly. Four seconds cannot carry that, and B3
already discharges the rules requirement. It stays a linked screen, and the fallback document
carries the one-sentence answer if a judge asks about it. *Authority:* r4-story §4.3 and §8
Q4, resolved; `FIRST-RUN.md:176-182`.

**R-K · Nothing on screen is rounded, and nothing spoken is unseen.** Per-beat numbers are the
payload's own `elapsed_ms` to their printed digits (`0.011 / 572.251 / 564.509 / 516.003` on
the recorded run — **re-derive from your own run**), never the reveal delay, never a stopwatch,
never offered as a product latency. `merged_commit 4fbbd371…` is stable and may be quoted;
**`clearance_digest` may never be captioned as a constant** — four runs on 2026-08-15 produced
four different digests, and if it were ever stable the rollback proof would be broken.
*Authority:* r6-honesty A2, A14; r5-craft §7 tells 2, 3, 8.

**R-L · The watermark stays on frame for the whole film, and it names this film's world.** The
committed string names *Kestrel Resources*, which is the **corpus** world's cleared fictional
operator; this film's site seeds as `demo_site` (`demo_world.sql:72-76`). So unless the
operator UI actually renders a Kestrel site, the watermark reads:

> `SYNTHETIC CORPUS · EVERY SITE, PERMIT, INCIDENT AND PERSON HERE IS AUTHORED`

If the UI does name Kestrel Resources, the committed string is used **verbatim**. Either way
the deviation and its reason are recorded in `ONSCREEN-TEXT.yaml`. *Authority:*
`DEMO-HONESTY.md:35-36` and `:83`; r6-honesty A3. The control is preserved; only the noun
follows the world on screen.

**R-M · Family 12 is not this wave's to move.** The VO may use the A4.1 sanctioned wording and
nothing beyond it, and **no camera is pointed at `docs/submission/SUBMISSION.json`** while its
`demo_url` reads `UNRESOLVED`. Re-deriving MUST-NOT-CLAIM family 12 belongs to that file's
owner, before the shoot, not to a founder on the day. *Authority:* r6-honesty §1 and A4.3;
r4-story §1.5.

**R-N · If it goes wrong on the day, it goes on camera or the shoot moves.** A `40001` retry is
pressed again on camera. A cold press is waited out. If the live origin is down, the film is
**not** made against a mock: it is postponed, or filmed against the local node **and said to
be local, on screen**. *Authority:* r6-honesty A17.1; the hackathon's own Functionality rule —
the Project *"must function as depicted in the video"*, so a staged refusal is a rules
violation, not merely a dishonesty (r1-judging).

---

## 5 · THE MUST-NOT-SAY SHORTLIST — pinned to every worker's desk

The full register is `docs/demo/research/r6-honesty.md` Part A and
`docs/submission/MUST-NOT-CLAIM.md` (fourteen families). These are the ones this film can
actually trip over. Read the TRUE INSTEAD column; do not paraphrase it into something stronger.

| MUST NOT SAY | TRUE INSTEAD |
|---|---|
| "Watch it remember." · "The system just retrieved the incident and blocked the permit." · anything **present-tense** about the retrieval | "The recall already ran — you are looking at its record, `mainline_meas.recall_run`, every field a column. What runs **now** is the third step: the database re-derives the obligation from blame ancestry and refuses the merge." |
| "Our agent decided to block it." | The decision is a `CHECK` constraint and a PL/pgSQL trigger. No model is in this path. |
| "The system searched every past incident." | Exhaustion is of **the retrieval that ran**, never of the corpus. |
| "An agent called this and it was refused." | `v_agent_actions` holds **0 rows** because no MCP agent has called this deployment. Zero is the true answer and the view stays visible and empty. |
| "Every refusal in this demo is the database's." · "The database refuses a defeater code that was never offered." | `mainline.disposition` has **no foreign key** onto `mainline.defeater_option`; that one gap is closed in the application. What is true and better: the disposition **pins the digest of the option set the signer was shown**. |
| "Defence in depth, proven." · "drop the constraint and the trigger still refuses; disable the trigger and the constraint still refuses" | Beat 3 proves **one direction, live**. The other direction is asserted by an unwelding matrix that **has never executed in CI**. |
| "Tamper-proof." · "The ledger can't be tampered with." · **"split-view resistant"** in any form | "Tamper-**evident**, never tamper-proof. There is one witness, it is ours, `q = 1`, and split-view resistance is **not** claimed." |
| "It catches rubber-stamping." · "It proves someone actually read it." | "**Nothing in this data model separates a considered disposition from a rubber stamp.** It makes the question unavoidable, the record precise, the worst stamp non-representable. We measure deliberation and never threshold it." |
| "vector search finds the precursor" · "changefeeds propagate the lesson" · "we time-travel to the 2013 clause" | The demo world seeds no embeddings and runs no vector query; there is no `CREATE CHANGEFEED` in any of the 271 migrations; `AS OF SYSTEM TIME` produces no frame of this film — **every date on screen is a column value.** |
| "Everything runs in Australia." | Database in Singapore `aws-ap-southeast-1`; Bedrock inference in Sydney `ap-southeast-2`; **no end-to-end Australian residency, and we say so.** |
| "It refuses in milliseconds in production." · any product latency | "One Lambda in Singapore to a Basic cluster in Singapore, measured on this call. This repository contains no p50, no p99 and no load profile." |
| "We proved it in CI." · "Our CI is green." | Nothing in CI has ever asserted this URL, and the reds are catalogued with owners. |
| "the 2024 incident" · "the rewritten clause" | `2019-03-14`. Nothing was rewritten — **somebody has proposed** to rewrite it. |
| "an open-source agentic memory layer" as the opening line | Lead with the refusal. |

---

## 6 · WHAT WE ARE ENTITLED TO SAY AND ARE NOT SAYING — put these in the film

Under-claiming is not a virtue when it costs the rubric's first criterion.

1. **The refusal names its own cause.** Beat 2's `mus[0]` carries `origin: blame_ancestry`,
   the `event_id` of the 2019 incident, the `clause_id` it damaged, `severity 4`,
   `virulence blood_major` — and beside it the nearest admissible alternative,
   `kind: dispose_obligations`, `cardinality: 1`, with the exact obligation id. **Store →
   retrieve → act, in one JSON body a judge can read in devtools.** Hold that block still.
2. **Nobody typed the four.** The seed wrote `severity 0 / routine`; the trigger overwrote both
   to `4 / blood_major` from the clause's own blame closure. *A counter a client writes is a
   client's opinion. A counter a trigger writes, on a row the client did not touch, is the
   database's.*
3. **Ten seconds.** `recall_run.started_at 2026-08-02T03:00:00Z` → obligation materialised
   `2026-08-02T03:00:10Z`. Not "the system searched its memory". Ten seconds, both timestamps
   on screen.
4. **An attacker who owns the counter does not own the gate.** B5's line. Then silence.
5. **The endpoint cannot write.** `persisted: false`, `disposition: rolled_back`,
   `isolation: SERIALIZABLE`. A judge can press it a hundred times.
6. **The system grades its own evidence down.** On its best refusal it reports
   `constraint_source: parsed`, `naa: null`, `naa_reason: not_computable`, MUS
   `kind: capability_gap`. **Leave that weakening on screen** — a demo that downgrades its own
   exhibit is not one anybody believes is faked.

---

## 7 · WHAT THIS PLAN DOES NOT DECIDE

* **Which cut is submitted.** The committed 2:51 console cut stays untouched (R-A). My
  recommendation on the record: **this film supersedes it as the submission cut**, because it
  reaches its first refusal at 0:22 rather than 0:51, it films the memory loop the rules
  require, and it puts the refusal inside the software the story's people actually use. The
  orchestrator decides.
* **Whether the two operator screens exist.** No console feature directory is a permit-to-work
  or disposition surface. `CLICKS.md` is written so the UI wave can build against it; `W6`
  owns the fallback if they do not land.
* **MUST-NOT-CLAIM family 12** (R-M) and the `SUBMISSION.json` `demo_url` field.

---

## 8 · THE SEVEN WORKERS

Sequence: **W1 first.** W2–W6 in parallel behind it. **W7 last**, and W7 may not begin until
W1–W6 have written their files.

| id | title | owns (literal paths, disjoint) |
|---|---|---|
| W1 | Spine and beats | `docs/demo/film/BEATS.yaml`, `docs/demo/film/SPINE.md` |
| W2 | The demo voice-over | `docs/demo/film/VO-DEMO.md` |
| W3 | The naming block | `docs/demo/film/VO-CLOSE.md` |
| W4 | Clicks and inputs | `docs/demo/film/CLICKS.md` |
| W5 | On-screen text | `docs/demo/film/ONSCREEN-TEXT.yaml` |
| W6 | Fallbacks and pre-flight | `docs/demo/film/FALLBACKS.md` |
| W7 | Claims clearance | `docs/demo/film/CLAIMS-CLEARANCE.md` |

**Every worker, every brief, without exception:**

* **NO FAKING.** Every refusal, SQLSTATE, latency, row, digest and seal on screen or in prose
  is one the deployed kernel produced. No hard-coded refusal text, no `setTimeout`, no staged
  screenshot, no number typed from memory. If a judge opens devtools they must find exactly
  what the frame showed. This repository has reverted a worker for reshaping a seed to match a
  constant; faking the one thing the product does is the larger version of the same act — and
  under the hackathon's Functionality rule it is a rules violation, not merely a dishonesty.
* **NO DEPLOY.** Never `terraform apply`, never redeploy, never touch AWS, never write an SSM
  parameter, never print a credential. `GET` against the live URL is fine; **do not `POST`**
  — the recorded gate-run payload in `evidence/deploy/live-gate-run.json` is the reference.
* **NO COMMIT.** Leave the tree for the orchestrator. Do not weaken `HONESTY.md`,
  `CI-STATE.md`, a ratchet or an assertion. `continue-on-error` and `|| true` are banned.
* **DO NOT TOUCH** `verticals/mainline/demo/script/**` or anything under
  `verticals/mainline/**`, `.github/**`, `scripts/**`, `infra/**`. Write only the files you own.
* Run `.venv/Scripts/python.exe scripts/demo/claim_hygiene.py --check <your files>` and record
  the verdict in your file header (R-B).
