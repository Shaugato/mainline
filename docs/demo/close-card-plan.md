<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# CLOSE-CARD PLAN — getting the four CockroachDB tools onto the screen without touching a second

**Lead:** closing-card lead · **Date:** 2026-08-16 · **Scope:** AUDIT.md FIX 1 in full, and the
parts of FIX 2 that touch the close (**S1, S5, S6, S8**). · **Workers:** 6, disjoint paths.

**Authority read first:** [`../submission/AUDIT.md`](../submission/AUDIT.md). Everything this plan
restates was re-measured today by this lead against the local cluster
`postgresql://root@localhost:26257/mainline_demo`, the committed artefacts, and `infra/` as text.
No AWS call was made, no credential was printed, no grant was touched, nothing was committed.

---

## 0 · THE FOUR PROHIBITIONS THAT BIND EVERY WORKER IN THIS PLAN

Repeated in every brief in §5, and repeated here because a worker who reads only this file must
still be bound:

1. **NO FALSE CLAIM, AND NO CLAIM IN A BETTER STATE THAN IT IS IN.** Agent Skills is **DESIGNED**.
   Bedrock is exercised in this repository and is **not** in the request path. S3 Object Lock is
   DESIGNED. The scopings are the reason the rest of the card is believable. **Nobody may capture,
   generate or commit a run of the Agent Skills assertion scripts to promote that row** — the brief
   rules that the tool is stated in the state it is in, or not stated at all.
2. **NEVER LENGTHEN THE FILM.** `172 s` total (`148` demo + `22` close + `2` end card), `174 s`
   hard stop, `180 s` rule. **Not one second, not one spoken word, is added by this plan.**
3. **NEVER DEPLOY.** No `terraform apply`, no redeploy, no AWS call, no SSM write, no credential
   printed. No file under `infra/`, `evidence/` or `skills/` is written by any worker here.
4. **NEVER REGRESS.** Baseline **1070 collected / 1069 passed / 0 failed / 0 errors**; gate proof
   `PROVEN` caveat-free; `DEFAULT_MAX_RESPONSE_BYTES == 136 * 1024`. The `mainline_qa`
   `v_disposition_profile` divergence stays open and the MCP run's verdict stays
   `DIVERGED — KNOWN GAP`. **Do not commit.** Leave the tree for the orchestrator.

---

## 1 · WHAT I MEASURED, BEFORE RULING ON ANYTHING

Every number this plan puts on a card or into a document was measured by this lead today. Nothing
below is quoted from a document that asserts it.

### 1.1 The role predicate — S1, confirmed exactly as the audit struck it

Run against `postgresql://root@localhost:26257/mainline_demo`:

| predicate | rows | `rolcanlogin` |
|---|---:|---|
| `WHERE rolname LIKE 'mainline%'` — **the published one** | **5** | **`true` on 2**: `mainline_api`, `mainline_judge` |
| `WHERE rolname IN (…nine names…)` — `census/crdb-programmable.md:827` | **9** | **`false` on all nine** |

The five the broken predicate returns are `mainline_api` (t), `mainline_auditor` (f),
`mainline_judge` (t), `mainline_migrator` (f), `mainline_owner` (f). The nine the correct predicate
returns are `agent_gate`, `agent_projector`, `agent_recaller`, `auditor_ro`, `mainline_auditor`,
`mainline_migrator`, `mainline_owner`, `quality_assurance`, `svc_disposition` — **`f` on every
one.** **The published answer is right and the published check is wrong.** The predicate is
restored; the claim is not weakened.

### 1.2 The EventBridge grep — S6, confirmed

| command | result |
|---|---|
| `grep -rn "aws_cloudwatch_event\|aws_scheduler" infra` — **as published** | **3 matches**, every one `Binary file …/terraform-provider-aws_v6.5x.0_x5.exe matches`; **exit 0** |
| `grep -rn --include=*.tf "aws_cloudwatch_event\|aws_scheduler" infra` | **no output; exit 1** |

The conclusion is right and the published command does not produce the published output.

### 1.3 The four tools — measured, and the panel's numbers come from here

| tool | verdict | measured today | evidence path |
|---|---|---|---|
| Distributed Vector Indexing (C-SPANN) | **EXERCISED** | **3** `cspann` indexes · **4** `VECTOR` columns, live on the cluster; `42809` appears 3× in `explain-unhinted.txt`, twice as `REFUSED BY THE SERVER — SQLSTATE 42809` (`:205`, `:220`) | `evidence/aws/ann/` |
| Managed MCP Server | **EXERCISED** | `pack-run.json`: `passed 15`, `total 16`, `exit_code 1`, `verdict DIVERGED — KNOWN GAP`. Second transcript `evidence/deploy/judge-run.json` (2026-08-11): 16 questions, channels `mcp`+`sql`, same verdict | `evidence/mcp/` |
| CockroachDB Cloud + `ccloud` CLI | **EXERCISED** | `cluster-list.txt` present: `ccloud auth whoami` line, then a parsed JSON array carrying `"cockroach_version": "v26.2.5"`, `"cloud_provider": "AWS"` | `evidence/ccloud/cluster-list.txt` |
| CockroachDB Agent Skills | **DESIGNED** | `skills/` holds `designing-diachronic-gates`, `designing-vector-recall-prefixes`, `upstream`, `validate-spec.py`. `evidence/tool-usage/crdb-features.json` → `rows.crdb_agent_skills.verdict == "DESIGNED"` | `skills/` |

`crdb-features.json` **already** reads `crdb_vector_index EXERCISED`, `crdb_cloud_ccloud
EXERCISED`, `crdb_managed_mcp EXERCISED`, `crdb_agent_skills DESIGNED`. **The census is right. It is
`close-block.md`'s prose that is wrong, and the film that is silent.**

### 1.4 The geometry of `k3`, measured because "will it fit" is arithmetic

Using `VO-CLOSE.md` §0.5's own stated budgeting assumptions (advance `0.6 em`, pitch `1.25 em`,
`1824 × 1026` title-safe):

| card | widest | lines | width-bound | height-bound | **runs at** |
|---|---:|---:|---:|---:|---:|
| `k2` composed (committed) | 148 ch | 39 | 20.5 px | 21.0 px | **20.5 px** |
| old `C3` alone (committed at 50 s) | 92 ch | 33 | 33.0 px | 24.9 px | **24.9 px** |
| **`k3` as committed** | **89 ch** | **24** | **34.2 px** | **34.2 px** | **34.2 px** |

**`k3` is the loosest card in the close by a wide margin — 1.67× `k2`'s glyph size — and it is
exactly balanced on both axes.** That is the headroom this plan spends, and it is the reason the
answer is `k3` and not a longer film.

---

## 2 · THE RULINGS

Ten rulings, each naming its authority. Where the brief left something open, I have decided it and
said so.

### R-C1 · THE FOUR TOOLS GO ON `k3`. `k2` IS NOT TOUCHED — NOT ONE LINE, NOT ONE WORD.

**Authority: `VO-CLOSE.md` §0.5 consequence 2 and §4.2, and `VO-CLOSE.md` §7.1's own discipline.**

The geometric argument is the weaker one and I am not resting on it. **The decisive argument is
label truth.** `k2`'s CockroachDB half has exactly two group headings: `IN THIS REQUEST` and
`IN THIS DATABASE, EARLIER`. Three of the four contest tools are **neither**:

* the **Managed MCP** transcripts were driven against the *managed Cloud* endpoint, not against the
  cluster this film's request reads, and not during it;
* **C-SPANN** is excluded from `k2` **by name** — §4.2: *"No vector search, no `EXPLAIN` plan… the
  demo world seeds no embeddings and runs no vector query"*;
* **`ccloud`** is a committed CLI transcript, not a statement this database executed.

Filing any of them under either `k2` heading is precisely the swap `VO-CLOSE.md` §7.1 exists to
prevent — the finding the file itself calls *"the most important thing in this file."* They need
the **third** label, the one the AWS half already gives Bedrock: *exercised in this repository, not
in this request path.* **The tools panel is the CockroachDB mirror of the Bedrock box**, and it
cannot live on `k2`, which has no third group and — §0.5 — no room for one.

**So `k2`'s two overlay strings are frozen.** `k2.overlay.aws_column` and
`k2.overlay.cockroachdb_column` are re-emitted byte-identical or not re-emitted at all. Its 14
spoken words, its four sweep landings, its `vo_word_budget: 16`, its 20.5 px and its 2.6 s of air
are all unmoved. **The tightest card in the film is not re-rendered by this wave.**

### R-C2 · THE PANEL IS A NEW STRING ON `k3`, `k3.overlay.tools`, BETWEEN THE RAIL AND THE URLS

**Authority: `VO-CLOSE.md` §0.3 — *"`k3` is the frame a judge pauses on… it is where a pausing
judge stops by construction"* — and §5.4, where the URLs are already the verification block.**

A judge answering *"did they use two or more CockroachDB tools?"* is doing verification, not
watching a story. That question is answered next to the two URLs he would use to check it, on the
card he has already stopped on. `k1` is refused as a home: `VO-CLOSE.md` §0.4 item 1 records that
`k1` already paid the compression's sharpest cost (12 s → 6 s of dwell on the axis-1 card), and
loading it further spends the same second twice. The end card is refused: two seconds is a held
frame, and its value is that there is nothing on it to read but the name.

**Order within the panel: the criterion's own order,** per `DEVPOST.md:191` — the Technological
Implementation criterion enumerates *"distributed vector index, MCP Server, ccloud CLI"* and the
submission requirement names Agent Skills separately, so Agent Skills is fourth **as the extra it
is**. This is the same principle that put the criterion rail in the organiser's own words on the
same card, and it means a judge holding `DEVPOST.md` and the frame sees one list in one order.

### R-C3 · NOTHING IS SPOKEN. THE 4.1 s OF AIR STAYS AIR.

**Authority: `VO-CLOSE.md` §0.4 — *"The air stays air"* — adopted verbatim; and §3.5's landing-4
alignment.**

The brief offers the air and I am declining it, in writing, with the arithmetic:

* `k3` has **0.7 s**. At the file's own 1.9 w/s that is **1.3 words**. There is no sentence there.
* `k2` has **2.6 s ≈ 5 words**. Adding even *"Four CockroachDB tools, three evidenced"* takes the
  line to 19 words → **10.0 s in a 10 s block, zero air**, on the card a judge is most likely to
  pause on. It would also break `VO-CLOSE.md` §3.5's landing-4 alignment — the sweep landing on the
  three `It did not run in this request.` lines at `6.8 s` *inside* the spoken Bedrock denial —
  which that file calls *"the one moment the parallelism buys something the sequence could not."*
  **REFUSED.**

**The close therefore still delivers 34 spoken words in 22 s at 1.55 w/s.** `close_words: 36`,
`close_s: 22`, `demo_s: 148`, `total_s: 172` and every `vo_word_budget` are unchanged, and any
worker who moves one has broken this plan. **The tools reach the screen through the only channel
that costs layout instead of seconds: text a judge pauses on.**

### R-C4 · THE PANEL'S EXACT TEXT — the words are frozen; only column padding may move

This is the string of record. `VO-CLOSE.md` §5 carries it as the authority; `ONSCREEN-TEXT.yaml`
reproduces it to the character; nothing else invents a variant.

```
------------------------------------------------------------------------------------------------
COCKROACHDB  ·  THE FOUR CONTEST TOOLS.  THE RULES REQUIRE TWO.   three EXERCISED, one DESIGNED

Distributed Vector Indexing (C-SPANN)  EXERCISED  3 cspann, 4 VECTOR, 42809    evidence/aws/ann/
Managed MCP Server                     EXERCISED  15 of 16, DIVERGED, published   evidence/mcp/
CockroachDB Cloud + ccloud CLI         EXERCISED  cluster list -o json, parsed   evidence/ccloud/
CockroachDB Agent Skills               DESIGNED   shipped, validated;  NO RUN IS COMMITTED  skills/
```

**Measured: 99 characters × 7 lines.** Composed onto `k3` with one blank separator line:

```
characters across  =  max(89, 99)  =   99
lines tall         =  24 + 1 + 7   =   32

width-bound   em <= 1824 / (0.6 * 99)  =  30.7 px
height-bound  em <= 1026 / (1.25 * 32) =  25.6 px
k3 runs at the smaller:                =  25.6 px
```

**`k3` lands at 25.6 px — 1.25× `k2`'s 20.5 px and 1.03× the 24.9 px old `C3` was cleared at.**
It is height-bound with **20 characters of width headroom** (up to 119 ch) still in hand.

**The binding budget handed to W1 and W2: `k3` composed must stay ≤ 119 characters across and
≤ 32 lines tall.** If W1's re-measurement against the real face and frame lands below a legible
floor, the remedy ladder is, in order: (1) drop the blank line after the heading — buys 0.9 px;
(2) shorten the horizontal rule, which is decoration; (3) re-wrap the Agent Skills row onto two
lines and drop the rule entirely. **Never a word, never a row, and never the `DESIGNED` state.**

### R-C5 · `DESIGNED` IS THE MOST VALUABLE WORD ON THE PANEL AND IS RENDERED EQUAL TO `EXERCISED`

Same size, same weight, same column, no grey, no footnote marker, no parenthesis. The heading says
the count out loud — **`three EXERCISED, one DESIGNED`** — so a judge gets the ratio before he
reads a row, and `NO RUN IS COMMITTED` is set in the same capitals as `EXERCISED` so the missing
thing is as legible as the present ones. **`MUST NOT SHOW`, in any form, on any card:** *"all four
exercised"*, *"four tools exercised"*, or a panel from which the Agent Skills row has been dropped
to make four look like four. **Dropping the DESIGNED row is how "three exercised, one designed"
silently becomes "four tools", and it is a REFUSE.**

### R-C6 · THE PANEL MAKES NO MCP ROUTE CLAIM, AND I DO NOT TOUCH `JUDGE-START.md`

**Authority: `close-block.md` §8, which bans *"judges can query our ledger over MCP"* by name;
`evidence/deploy/judge-access.json` → `credential_publishable: false`.**

The MCP row cites `evidence/mcp/` — **a committed transcript** — and never an endpoint a judge can
point a client at. `15 of 16, DIVERGED, published` reads as *"we drove it, here is what came
back"*, which is the true sentence. **No worker in this plan writes to `docs/submission/JUDGE-START.md`.**
S2 belongs to the judge-documents lead and is out of scope here; my obligation is only that nothing
this plan puts on screen makes S2 worse, and R-C6 discharges it.

### R-C7 · NO HIGHLIGHT SWEEP IN `k3`. THE PANEL IS READ, NEVER SWEPT.

**Authority: `VO-CLOSE.md` §3.5, which caps the sweep at four landings and spends all four in
`k2`.** A 6 s card already carrying a 10-word spoken line, a three-line limit and a four-stanza
rail cannot also carry a pointer; a fifth landing here would be the roving highlight that
`ONSCREEN-TEXT.yaml` calls *"a card nobody reads"*. The panel is pause material by design, which is
the same rule that leaves `k2`'s AWS half unswept.

### R-C8 · `VO-CLOSE.md` IS THE AUTHORITY. `close-block.md` §7.1 DEFERS TO IT EXPLICITLY. (S8)

Two documents from one wave prescribe different content for the same 22 seconds:
`close-block.md:284` prescribes a card line that `VO-CLOSE.md` §4.1 does not carry, and §4.1 states
*"Every word below is the committed 50 s text."*

**Resolution — the direction the brief names.** `close-block.md` §7.1 **stops prescribing the
film's card**. It gains a one-sentence pointer naming `VO-CLOSE.md` §§2–5 and `ONSCREEN-TEXT.yaml`
`k1`/`k2`/`k3` as the sole film authority, and its six-line block is re-labelled as what it
actually is — **a written/press-kit fallback for a static card, not the film's overlay.** Its line
5 is corrected to the measured state regardless of where it is used, because a false line is false
in a press kit too.

### R-C9 · S1 — RESTORE THE PREDICATE, AND STRENGTHEN THE ROW RATHER THAN WEAKEN THE CLAIM

Both `close-block.md:246` and `feature-census.md:281` take the explicit nine-name `IN` list
preserved at `census/crdb-programmable.md:827`, verbatim, with `ORDER BY 1`. **The published answer
— nine rows, `rolcanlogin` false on all nine — does not change; it becomes true of the command
printed beside it.**

**And the row gains half a clause, because hiding the two logins would be the smaller lie.**
`mainline_judge` is the login this submission publishes to judges, and `mainline_api` is the
Lambda's. The nine are the **duty-separation lattice**, and they are distinct from the two service
logins by design. Saying so converts the audit's sharpest finding into the row's strongest
sentence. **Do not "fix" this by deleting the answer, by softening `nine` to `five`, or by
switching to `rolname LIKE 'agent\_%'`** — I measured that too and it returns **10**, all NOLOGIN,
so "nine" is correct only against the named list.

### R-C10 · S5 AND S6 — SAY THREE, AND PRINT THE COMMAND THAT PRODUCES THE OUTPUT

**S5.** `close-block.md:122-124` — *"All four are exercised in this repository with a committed
transcript"* — becomes **three exercised with a committed transcript, one shipped and not
evidenced**, in the census's own words. `close-block.md:311`'s written cut is corrected in the same
direction: the count of four survives, the state of the fourth is stated. `DEVPOST.md:191`, `:196`,
`:443` and `RULES-MATRIX.md` R6 **already say this correctly** — this is one file catching up with
four, not a new position.

**S6.** `close-block.md:327` takes `--include=*.tf` and prints the exit code: *"returns no output
and exits 1"*. The row's entire premise is one-command falsifiability, so the command must be the
one that was run.

**Also caught by this lead, and assigned:** `SPINE.md:350` still reads *"the close's
words-per-second **does not move** — 1.64 at 50 s, 1.64 at 22 s."* After `D35` the close delivers
**34 words at 1.55 w/s** (`VO-CLOSE.md` §0.2, measured). The direction of the argument is unchanged
and gets *stronger* — the pace moved further **down** — but the number is stale and it is a
close-touching cross-document disagreement of exactly the kind this wave exists to remove.

---

## 3 · WHAT A JUDGE CAN DO AFTER THIS PLAN LANDS, THAT HE CANNOT DO TODAY

**From the frame alone, paused on `k3`:** count four tool names, read three `EXERCISED` and one
`DESIGNED`, and answer *"did they use two or more CockroachDB tools?"* — **yes, three with
transcripts** — without leaving the video.

**From the repository, in under a minute**, using the four paths printed on that same frame:

```
# Managed MCP — prints: 15 / 16 DIVERGED — KNOWN GAP
python -c "import json;d=json.load(open('evidence/mcp/pack-run.json'));print(d['passed'],'/',d['total'],d['verdict'])"

# C-SPANN — prints two lines: REFUSED BY THE SERVER — SQLSTATE 42809
grep -n "REFUSED BY THE SERVER" evidence/aws/ann/explain-unhinted.txt

# ccloud — the transcript, parsed rather than screen-scraped
tail -n +2 evidence/ccloud/cluster-list.txt | python -c "import json,sys;print([c['cockroach_version'] for c in json.load(sys.stdin)])"

# Agent Skills — prints: DESIGNED
python -c "import json;print(json.load(open('evidence/tool-usage/crdb-features.json'))['rows']['crdb_agent_skills']['verdict'])"
```

The fourth prints `DESIGNED` — **and the frame already said so**, which is the entire point of
putting the state on the card. W5 must run all four verbatim and paste the first line each one
prints, so no command reaches a judge that has not been run.

---

## 4 · WHAT DOES NOT CHANGE — the invariants every worker asserts before finishing

| invariant | value |
|---|---|
| film total | **172 s = 2:52** · hard stop 174 s |
| `demo_s` / `close_s` / end card | **148 / 22 / 2** |
| card durations | `k1` **6** · `k2` **10** · `k3` **6** |
| spoken words in the close | **34** delivered · `close_words: 36` budget · **1.55 w/s** |
| `vo_word_budget` | `k1` 10 · `k2` 16 · `k3` 10 — **unchanged** |
| `k2`'s two overlay strings | **byte-identical** |
| `k2` sweep | **four landings**, same order, same times |
| Agent Skills verdict | **DESIGNED**, everywhere, on screen and in prose |
| MCP run verdict | **`DIVERGED — KNOWN GAP`, 15/16, exit 1** |
| suite baseline | 1070 / 1069 / 0 / 0 |

---

## 5 · THE SIX WORKERS — disjoint, literally enumerated paths

**No path appears in two rows. No worker writes to `infra/`, `evidence/`, `skills/`,
`docs/submission/JUDGE-START.md`, `docs/submission/DEVPOST.md` or `docs/submission/RULES-MATRIX.md`.**

| id | worker | owns, literally |
|---|---|---|
| **W1** | the film authority | `docs/demo/film/VO-CLOSE.md` |
| **W2** | the string of record | `docs/demo/film/ONSCREEN-TEXT.yaml` |
| **W3** | timing and structure | `docs/demo/film/BEATS.yaml` · `docs/demo/film/SPINE.md` |
| **W4** | the close block | `docs/submission/census/close-block.md` |
| **W5** | the census | `docs/submission/feature-census.md` · `docs/submission/census/crdb-four-tools.md` |
| **W6** | clearance, hygiene, verification | `docs/demo/film/CLAIMS-CLEARANCE.md` · `docs/demo/film/CLAIMS-CLEARANCE-CR.md` · `docs/demo/ON-SCREEN-CLAIMS.md` |

**Sequence.** W1 first — it is the authority and W2/W3/W6 copy from it. W4 and W5 are independent of
W1 and may run in parallel from the start. W6 runs last and verifies the whole wave.

---

## 6 · THE ONE THING I WOULD ARGUE ABOUT IF THERE WERE ROOM

`k3` goes from **34.2 px to 25.6 px** — a **25 % reduction in glyph size on the card that carries
the film's only concession, the organiser's four criteria in their own words, and both URLs.**
`ONSCREEN-TEXT.yaml` already records that `k3` is *"doing more reading work than `c4` did, in less
time,"* and this plan adds seven lines to it. **That is a real cost and I am not dressing it up.**

Three things are true beside it and none of them cancels it. The card still runs **larger than
either card `k2` replaced was cleared at**. The panel is four rows a judge scans in a second, not
prose he reads. And the alternative — leaving the closing card of a CockroachDB hackathon film
naming seven AWS services and zero CockroachDB tools — is, in the auditor's words, *"the largest
unforced loss in the submission."* **I would rather have a 25.6 px `k3` that answers the
eligibility question than a 34.2 px `k3` that does not.**

The cut ladder's **rank 4** — `k3` 6 s → 4 s — is now a worse step than it was, because the card it
shortens is denser. It stays at rank 4 (it is still the last thing before `b10`), and W3 records
the new cost in its `why` rather than quietly leaving the old one.
