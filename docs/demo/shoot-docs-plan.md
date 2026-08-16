<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# SHOOT-DOCUMENTS PLAN — FIX 3, S2, and the press placement

**Shooting-documents lead · 2026-08-16 · directs 6 workers · writes no worker's file.**
Authority read before anything was decided: [`docs/submission/AUDIT.md`](../submission/AUDIT.md).
Film authority: [`film/SPINE.md`](film/SPINE.md) and [`film/BEATS.yaml`](film/BEATS.yaml).

**Scope.** FIX 3 (`VIDEO-KIT.md` ↔ `SPINE.md`), S2 (`JUDGE-START.md` Stop 5), the
`CLICKS.md` ↔ `CLICKS-CR.md` press-placement disagreement, and a readback of the ten
documents the founder holds during the shoot.

**Out of scope and not to be touched by any worker below**, because other leads own them this
wave: `docs/demo/film/VO-CLOSE.md`, `docs/submission/census/close-block.md`,
`docs/submission/feature-census.md`, `docs/submission/SUBMISSION.json`,
`docs/submission/RULES-MATRIX.md`, and everything under `verticals/`, `infra/`, `scripts/`.

---

## 0 · WHAT I MEASURED BEFORE I RULED

Nothing below is quoted from a document that asserts it. No AWS call was made, no credential
printed, no Terraform run, nothing committed.

| # | measurement | command / artefact | result |
|---|---|---|---|
| M1 | AWS service census | `evidence/tool-usage/aws-services.json` → `totals` | **12 rows · 6 EXERCISED · 5 DESIGNED · 1 NOT-AVAILABLE** |
| M2 | submission readiness, local, **no `--check-urls`** | `.venv/Scripts/python.exe scripts/submission/check_submission_ready.py` | `tool usage documented` prints **"4 CockroachDB tools, 10 AWS services; 5 AWS service(s) marked as having run (Amazon Bedrock, Amazon CloudWatch, AWS Lambda, AWS IAM, AWS SSM Parameter Store); 35 of 35 cited artefacts present on disk"**. One FAIL row only: `video URL … UNRESOLVED` |
| M3 | `demo_url` in the submission file | `docs/submission/SUBMISSION.json:20` | **RESOLVED** — holds the live Function URL. `video_url` still `UNRESOLVED` |
| M4 | MCP credential | `evidence/deploy/judge-access.json` → `mcp_channel` | `credential_publishable` **false**; `why_not_publishable` names `create_database`, `create_table`, `insert_rows`, `list_clusters` |
| M5 | the wording four documents already use | `docs/deploy/JUDGE-PACK.md:700` | §4 is headed **"Managed MCP — available, working, and deliberately not published"** |
| M6 | B9 / B10 slack | `VO-DEMO.md` §2 table, lines 595–596 | **B9** 20 w / 12 s / 1.67 w/s, slack **1.5 s** = 0.4 s hold + **1.1 s "for the typed proposal to settle"**. **B10** 20 w / 12 s / 1.67 w/s, slack **1.5 s** = 0.6 s mirror hold + 0.5 s spoken `SQLSTATE` → **0.4 s free** |
| M7 | rate ceilings | `BEATS.yaml:142`, `:175` | `wps_assumption: 1.9`; the kit's ceiling is **1.95** |
| M8 | the read chain | `CLICKS.md` M14 | four sequential awaited GETs, **≈ 3.5 s warm**, ≈ 6 s cold — incompressible |
| M9 | the pending state | `CLICKS.md` §5 B10 | **1.5 s** budgeted between press and refusal paint |
| M10 | use case two is NO-GO today | `CLICKS.md` §5 B10 box; `FALLBACKS.md` §6 W6-6/W6-7/W6-8 | `POST /v1/demo/cr-gate-run` **404**, blocking-checks **404**, approve control hard-disabled; `DEMO-INC-0001` occurs **zero** times on the MoC screen (R-5 unsatisfied) |
| M11 | prose gate, baseline | `.venv/Scripts/python.exe scripts/submission/check_submission_prose.py` | `submission prose OK`, **exit 0**, 21 files |
| M12 | hygiene gate, baseline | `.venv/Scripts/python.exe scripts/demo/claim_hygiene.py --check` over `CLICKS.md CLICKS-CR.md VO-DEMO-CR.md SPINE.md BEATS.yaml` | `claim hygiene OK`, **exit 0**, 5 files |

**M2 and M1 disagree and are not to be reconciled by picking a number.** The readiness gate
counts **10 AWS services, 5 run**; the census artefact carries **12 rows, 6 EXERCISED**. They
count different sets (AUDIT §4.3 names the gap: no SNS row, no Budgets row, S3 only as
`aws_s3_object_lock`). Any document restating either **quotes the artefact it read, names it,
and says the two differ.** Averaging them would be the first invented number in this repository.

---

## 1 · THE RULINGS

### R-SD1 · `VIDEO-KIT.md` is demoted from film authority to capture runbook

**Authority: `SPINE.md:197` and `:216`; AUDIT §4.2 S4.** SPINE says in terms that *"any document
still in-pointing the naming block at `2:00` is describing the pre-revision film."* VIDEO-KIT's
§0.1 is a 25-shot table, `s01`–`s25`, 171 s / 2:51, containing `s19-beat5-mcp-connect`, closing
on `s22`/`s23`/`s24`/`s25`. That is not a stale in-point; it is a **different film**.

**The ruling.** VIDEO-KIT keeps what it is genuinely good at — the Devpost sub-rules (§00), the
machine (§A), the cluster pre-flight (§B), export settings, and the film-specific must-not-claim
extract (§0.3) — and **stops describing the film**. §0, §0.1, §0.2, §C, §D and §E are struck as
descriptions of the current cut, preserved struck-through under the repository's own
`~~…~~ SUPERSEDED <date>` convention (`JUDGE-START.md` Stop 6 and `FALLBACKS.md` F-9 are the
precedents), each carrying a pointer to the document that now answers the question.

**`verticals/mainline/demo/script/SHOT-LIST.yaml` is NOT edited and NOT deleted.** It is gated
by `.github/workflows/claims.yml`, it is the committed console cut, and `SPINE.md` §7 leaves that
cut untouched this wave. The correction is that VIDEO-KIT stops presenting it as *this* film.

### R-SD2 · §497 is restated upward, to the measurement, and never past it

**Authority: M1, M2, `evidence/deploy/APPLIED.md`, AUDIT §4.2 S3.** The line *"Lambda, SSM,
CloudWatch are declared in Terraform and not applied … Two of ten, named. Say those two"* has
been false since the 2026-08-14 apply and is **shooting guidance that would understate the
project on camera**. It is struck and replaced with M2's line quoted verbatim, M1's totals beside
it, and the divergence stated.

**And the second half of the ruling, which matters more than the first.** VIDEO-KIT does not get
to prescribe what is said on camera any more. **`VO-CLOSE.md` §4.1 is the authority for the close
card's content** and no worker of mine edits it. VIDEO-KIT names *states* — applied / exercised /
designed — and points at k2. The scopings that make the rest believable stand and are repeated
in the replacement text: **Agent Skills is DESIGNED** (2 authored + 1 de-branded, validator
green, **no run captured under `evidence/`**), **Bedrock is exercised in this repository and is
NOT in the request path**, **the S3 Object Lock row is DESIGNED**.

### R-SD3 · `JUDGE-START.md` Stop 5 has ONE published route to our ledger

**Authority: M4, M5, `SUBMISSION.json` → `judge_access.how`, `MCP-CONFIG.md` §0/§1,
`close-block.md` §7.2 and §8, `RULES-MATRIX.md:536`; AUDIT §2.** Four documents already say this
correctly and one of them records the identical wording being corrected in `SUBMISSION.json` on
2026-08-16. **This is a known-bad sentence that survived in one file, and the fix is to join the
four — not to invent a fifth phrasing.**

The published read path to MAINLINE's ledger is the read-only **`mainline_judge`** SQL login in
`docs/deploy/JUDGE-PACK.md` §2, over pgwire, in the judge's own client. Managed MCP is a
**separate** path that does not reach our data with any credential we publish; `MCP-CONFIG.md` §1
reproduces the *mechanism* on the judge's **own** cluster with the judge's **own** key; the
sessions we ran against ours are committed at `evidence/deploy/judge-run.json` (2026-08-11) and
`evidence/mcp/` (2026-08-16), both at **15 of 16**, verdict **DIVERGED — KNOWN GAP**, the one
FAIL preserved.

**The banned sentence, by name, is the one `close-block.md` §8 already bans:** *"judges can query
our ledger over MCP."* It must not survive in any form, including "either one sufficient".

### R-SD4 · **THE PRESS LANDS AT `2:14.0`, INSIDE B9. `CLICKS.md`'s `2:17` IS STRUCK.**

> **Click 6 — `Approve change` — is at `2:14.0`, which is `+10.0` into `b9`. The request is in
> flight `2:14.0 → 2:15.5`. The refusal paints at `2:15.5`. `B10` opens at `2:16.0` on a refusal
> that has been on screen for half a second.**

**Ruled on the merits, and the merits are the film's own grammar.** `CLICKS.md` §5 `B1` already
solves this exact problem once: the attempt beat carries the press (Click 2 at `0:22.5`, `+2.5`
into a 10 s block), the cursor then does not move, and **the refusal beat's in-point is where the
refusal is on screen** (`B2` at `0:30`). `B9` is the attempt beat of use case two and `B10` is
titled *REFUSED AGAIN*. Choreographing the film's two mutating presses differently is itself the
defect — a judge watches the same act twice and the second one reads as edited.

**Three rules point the same way and none points the other.** R-K: a value is spoken while it is
on screen or it is not spoken — `B10`'s first word is *"Refused."* at `2:16`. R-9: each mutating
request is narrated while it is in flight — under this placement the tail of *"This request asks
to edit it."* runs over the flight. R-10: `b9` and `b10` are atomic, so the boundary between them
is a seam in one act, not a place to park a pending spinner.

**`CLICKS-CR.md` is upheld in substance and struck in its number.** Its intent — the press under
*"This request asks to edit it."* — is correct and is what this ruling implements. Its literal
`+7.4` is struck: it was scored against the retired 10 s `B9`, and `+7.4` in the 12 s block is
`2:11.4`, in the middle of the typing. **Neither sheet's number survives; the placement of one
does.**

**The timeline, which changes no word, no duration and no budget anywhere:**

| t | action | spoken over it |
|---|---|---|
| `2:04.0 – 2:05.5` | cursor travels to the app-bar tab `Management of change` | *"Fine. Then don't use the clause — change it."* |
| `2:05.5` | **Click 5** — module switch | " |
| `2:05.5 – 2:09.0` | the four-read paint, ≈ 3.5 s warm (M8), operator touches nothing | ·hold 0.4· |
| `2:09.0 – 2:10.5` | wheel scroll to §3; **dwell on the clause of record — this dwell is the R-5 evidence and is not shortened** | *"Same paragraph. Same incident behind it."* |
| `2:10.5 – 2:11.0` | click into `Proposed wording`; caret in an empty box | " |
| **`2:11.0 – 2:13.5`** | **keystrokes — 2.5 s, at a human rate, on camera** | *"This request asks to edit it."* begins |
| `2:13.5 – 2:14.0` | cursor travels to `Approve change` | " |
| **`2:14.0`** | **Click 6 — mutating request 2 of 2** | " |
| `2:14.0 – 2:15.0` | in flight; real pending state; **one** `POST cr-gate-run` row | *"…asks to edit it."* finishes — **1.0 s of narration over the flight (R-9)** |
| `2:15.0 – 2:15.5` | still in flight; founder silent | — |
| `2:15.5 – 2:16.0` | the refusal paints and the frame composes | — |
| `2:16.0` | **B10 in-point** | *"Refused."* — **R-K satisfied with 0.5 s to spare** |

**WHAT IT COSTS, PRICED, NOT WAVED THROUGH.** The typing window falls from **5.0 s to 2.5 s**,
and `b9`'s 1.1 s of "settle" slack (M6) is re-purposed from *the typed proposal settling* to *the
answer landing*. **The proposed wording must therefore be a string a human types legibly in
2.5 s.** `CLICKS.md` §5 `B9` owns that string and must state it and its character count. R-2 is
satisfied by the *act* of typing into the console's own input with no provenance chip — it has
never required a character count — so a shorter honest proposal discharges it identically. If
0.5 s more is needed, it comes from the app-bar travel (`1.5 s → 1.0 s`); the travel still proves
no cut. **It never comes from the scroll dwell, which is R-5's evidence, and never from the read
chain, which is incompressible.**

**Why not the other candidate.** `VO-DEMO-CR.md` §1 priced option (b) as *"start `B10`'s line
≈ 2.5 s after its in-point"*. **M6 kills it:** `B10` has 1.5 s of slack of which 0.6 s is the
mirror hold and 0.5 s pays for the spoken `SQLSTATE`, leaving **0.4 s free**. A 2.5 s slip takes
2.1 s that does not exist, and pays for it out of either the hold (`SPINE.md` §4: the hold is a
scripted element, not a pause an editor may tighten) or the words (`SPINE.md` §4: each scope word
does all the work of its own half). 20 w in 9.5 s is **2.11 w/s**, over the kit's 1.95 ceiling
(M7). Option (b) is not expensive; it is unaffordable.

#### R-SD4a · The floored fallback, and the collision it creates

If rehearsal shows that **no honest proposal string types legibly in 2.5 s even after the string
is shortened and the 0.5 s of travel is reclaimed**, `B10`'s first word may slip by **at most
0.4 s** — `B10`'s measured free slack (M6) — putting Click 6 at `2:14.4` and the typing at 2.9 s.

**The cap is 0.4 s and it is a floor, not a preference.** Beyond it the hold or the `SQLSTATE`
pays, and both are protected. **And taking any of it forecloses `CLAIMS-CLEARANCE.md` `D31`** —
the `~ REWORD` of *"guards **edits**"* to *"guards the change"*, which `VO-DEMO.md`'s head note
prices at 21 words running 1.13 s against 0.95 s of slack. **The 0.4 s cannot be spent twice.**
The film lead spends it on the press or on D31, states which, and does not discover the collision
on the day.

#### R-SD4b · The whole ruling is conditional, and every document says so

**`b9` and `b10` are NO-GO on the deployed origin today** (M10). On the no-go path there is no
Click 6 at all: the ledger is **five clicks and one text entry**, §6 rule 9 reverts to **exactly
one** mutating request, `b8` returns to 10 s and the film is 152 s (`SPINE.md` §5.1). **Every
document restating R-SD4 states it as conditional on `FALLBACKS.md` §4.2's R-11 decision gate.**
A ruling written as unconditional would be the second document this wave describing a film that
does not exist.

### R-SD5 · Nothing below lengthens the film, and nothing below changes a spoken word

`total_s` stays **172** (148 + 22 + 2), `hard_stop_s` **174**, ceiling **180**. No beat duration
moves. No `vo_word_budget` moves. No line in `VO-DEMO.md` §1, `VO-DEMO-CR.md` §1 or
`VO-CLOSE.md` §4 is edited by any worker of mine. **R-SD4 was chosen because it is the only
candidate with zero arithmetic ripple**, and a worker who finds themselves editing a duration to
make it fit has misread it and stops.

---

## 2 · THE SIX WORKERS

Paths are disjoint and literal. Every worker re-runs M11 and M12 over its own files before
reporting and keeps both at exit 0. **No worker runs `scripts/qa/regression_guard.py`** — its
`LIVE` family POSTs to the deployed origin (`FALLBACKS.md` §6 W6-2b) and this wave touches no
AWS. `check_submission_ready.py` may be run **without** `--check-urls`.

| id | title | paths owned |
|---|---|---|
| **W1** | VIDEO-KIT demoted to capture runbook | `docs/submission/VIDEO-KIT.md` |
| **W2** | JUDGE-START Stop 5 joins the four | `docs/submission/JUDGE-START.md` |
| **W3** | CLICKS.md implements the press ruling | `docs/demo/film/CLICKS.md` |
| **W4** | The CR companion sheets retire the open item | `docs/demo/film/CLICKS-CR.md`, `docs/demo/film/VO-DEMO-CR.md` |
| **W5** | The spine and the machine half record the ruling | `docs/demo/film/SPINE.md`, `docs/demo/film/BEATS.yaml`, `docs/demo/film/VO-DEMO.md` |
| **W6** | The readback — ten documents, one story | `docs/demo/film/FALLBACKS.md`, `docs/demo/film/ONSCREEN-TEXT.yaml`, `docs/demo/film/CLAIMS-CLEARANCE.md`, `docs/demo/film/CLAIMS-CLEARANCE-CR.md`, and §R of this file |

**Order.** W1, W2, W3, W4, W5 run in parallel. **W6 runs last**, after all five have reported.

---

## 3 · THE PROHIBITIONS, REPEATED IN EVERY BRIEF

1. **Never `terraform apply`, never redeploy, never touch AWS, never write an SSM parameter,
   never print a credential.** No network call to the origin. Restatements come from committed
   artefacts.
2. **Never claim a tool, service or feature in a state better than it is in.** Agent Skills is
   **DESIGNED**. Bedrock is exercised in this repository and **not** in the request path. The S3
   Object Lock row is **DESIGNED**. The MCP run is **15/16, DIVERGED — KNOWN GAP**. The
   `mainline_qa` divergence stays open. These scopings are why the rest is believable.
3. **Never revoke or widen a grant.** Nothing turns a red suite green.
4. **Never lengthen the film.** 172 s, hard stop 174 s, ceiling 180 s. No duration, no word
   budget and no spoken line moves.
5. **Never regress.** Baseline 1070 collected / 1069 passed / 0 failed / 0 errors; gate proof
   PROVEN caveat-free; `DEFAULT_MAX_RESPONSE_BYTES == 136 * 1024` does not move.
6. **Do not commit.** Leave the tree for the orchestrator.

---

## R · READBACK — filled in by W6

**W6 · the readback · 2026-08-16 (UTC), run after W1–W5 had all landed.** Every cell below was
taken by opening the file and reading the line, not by trusting a worker's report. Commands are
printed where a stranger would want to re-run them; every one takes under a minute.

> ## VERDICT — **THE TEN DOCUMENTS TELL ONE STORY ON ALL FIVE AXES.**
>
> **Shape ✓ · Press ✓ · Words ✓ · States ✓ · Route ✓.** No document still describes 25 shots,
> `171` s, `2:51` or `s19-beat5-mcp-connect` as the film. No document still places the press at
> `2:17` or at `+7.4` except to strike it. **No spoken line, word count or words-per-second figure
> moved anywhere in the wave.** No shoot document tells a judge to read our ledger over MCP — two
> of them ban the sentence by name.
>
> **Six residues remain. None is a disagreement between two shoot documents; four are pointers in
> non-shoot files, one is a stale worker-id label, and one is a rehearsal decision that is
> supposed to stay open.** Each is named below with `file:line` and an owner.

### R.0 · THE TWO GATES, RE-RUN BY THIS WORKER AFTER ITS OWN EDITS

```
$ .venv/Scripts/python.exe scripts/submission/check_submission_prose.py
  claim hygiene OK            (its delegated claim_hygiene sweep, 23 files)
  submission prose OK         (21 files)                                            exit 0

$ .venv/Scripts/python.exe scripts/demo/claim_hygiene.py --check \
      docs/demo/film/BEATS.yaml docs/demo/film/SPINE.md docs/demo/film/VO-DEMO.md \
      docs/demo/film/VO-DEMO-CR.md docs/demo/film/VO-CLOSE.md docs/demo/film/CLICKS.md \
      docs/demo/film/CLICKS-CR.md docs/demo/film/ONSCREEN-TEXT.yaml docs/demo/film/FALLBACKS.md
  scanned 9 file(s) against 21 rules
  claim hygiene OK                                                                  exit 0
```

**The two register sheets are scanned separately and are the reason the sweep above is nine files
and not eleven.** `CLAIMS-CLEARANCE-CR.md` → **exit 0**. `CLAIMS-CLEARANCE.md` → **exit 1 with
exactly 6 findings, all on lines `833`–`836`**, every one of them inside its own pasted `--self-test`
transcript, which §12.10 measures and explains. **That count was 6 before this wave and is 6 after
it; §12.9.2 added no seventh.** `ONSCREEN-TEXT.yaml` also re-parses under `yaml.safe_load` after
its edits — a hygiene scan reads a YAML file as text and would not have caught a broken one.

**Not run, on purpose:** `scripts/qa/regression_guard.py`. Its `LIVE` family `POST`s to the
deployed origin (`FALLBACKS.md` §6 `W6-2b`) and this wave makes no network call. **The 1070 / 1069
/ 0 / 0 baseline cannot move for markdown and YAML nothing collects** — `docs/demo/film/**` is
outside every `TARGET_GLOBS` entry and no workflow filters on `docs/**` — **and if that is ever
wrong, the replacement number comes from a `--junitxml` root element and from nothing else.**

---

### R.1 · THE READBACK TABLE — ten documents, five axes

**Legend.** **✓** = says it, and the line is cited · **—** = silent by design, which is not a
disagreement · **✗** = contradicts another document.

| # | document | **(a) SHAPE** — 148 + 22 + 2 = 172 s = 2:52, `B0`–`B10` then `K1`/`K2`/`K3`, hard stop 174 s | **(b) PRESS** — Click 6 at `2:14.0` inside `b9`, conditional on the R-11 gate | **(c) WORDS** — no spoken line, word count or w/s moved | **(d) STATES** | **(e) ROUTE** — nothing tells a judge to read our ledger over MCP |
|---|---|---|---|---|---|---|
| 1 | `film/SPINE.md` | **✓ AUTHORITY.** `:197` — *"148 s demo · 22 s close · 2 s end card · **172** s total · hard stop **174** s"*; `B0`–`B10`/`K1`–`K3` in the same table; `:392` runs the ladder off `174` | **✓** `:533` — *"`2:14.0`, `+10.0` into B9"*, B10 in-points at `2:16` on a refusal already on screen; **conditional** at `:540` — *"Live only if `FALLBACKS.md` §4.2's R-11 gate passes"* | **✓** two deletions in the whole file, neither a spoken line: the `K3` summary row and the close's stale w/s. `:350` corrects `1.64 at 22 s` → **`1.55`**, which is the *delivered* rate under `D35` and a **fall**, never a rise | **✓** `:366` Agent Skills **DESIGNED**, *"no run committed"*; `:368` bans the panel reading as four exercised tools | **—** silent; carries no route claim |
| 2 | `film/BEATS.yaml` | **✓ MACHINE AUTHORITY.** `:127` `total_s: 172`, `:128` `hard_stop_s: 174`, `:135` *"148 + 22 + 2 = 172"*; sixteen beat ids `b0`…`b10`, `k1`…`k3`, `end` | **✓** `:402` — *"THE PRESS LANDS AT 2:14.0, INSIDE THIS BEAT"*, and `:486` the same from `b10`'s side. **Both are comments**: `:409` — *"NOT ONE `t`, `dur`, `ends` OR `vo_word_budget` IN THIS FILE MOVED FOR IT"* | **✓** `close_words: 36` and every `vo_word_budget` unmoved; `:525`–`:530` correct *"1.64 before, 1.64 after"* to name the delivered **1.55** beside the 1.64 budget | **✓** `:600` the four tools with three EXERCISED / one **DESIGNED**; `:730` the panel may never lose the `DESIGNED` state | **—** silent |
| 3 | `film/VO-DEMO.md` | **✓** `:129` and `:705` — *"148 + 22 + 2 = 172 s · 2:52. Target 172, hard stop 174, ceiling 180"* | **✓** `:595` prices `B9`'s slack as *"1.1 s for the press at `2:14.0` and the answer landing; typing 2.5 s"*; `:616`–`:634` state the ruling, price the rejected candidate, and end *"conditional on `FALLBACKS.md` §4.2's R-11 gate"* | **✓ ONE deletion in the file and it is a slack description, not a word.** `B9` stays `20 w / 12 s / 1.67 w/s`, `B10` stays `20 w / 12 s / 1.67 w/s`, the table still totals `148 s / 259 w / 1.75 w/s` | **—** the demo half names no tool state | **—** silent |
| 4 | `film/VO-DEMO-CR.md` | **✓** `:95` — *"close 22 + end card 2 = 172 s = 2:52"*; `:98` `172 ≤ 172` target, `< 174` hard stop | **✓** `:230` — *"RULED … THE PRESS LANDS AT `2:14.0`"*; `:147` the in-beat timing; `:237` strikes `CLICKS.md`'s `2:17` and `:239` strikes its **own** `+7.4`; `R-SD4b` at `:283` | **✓** its 20 deletions are the retired open-item box and a stale timing recap — **not one spoken line**; the two blocks' words and rates stand | **—** | **—** silent |
| 5 | `film/VO-CLOSE.md` | **✓** `:110` — *"148 + 22 + 2 = 172 s · 2:52"*; `:137`–`:141` reason about the `174` s hard stop explicitly | **— by design.** The close carries no press. **Correct silence, not a gap** | **✓ 339 additions, ZERO deletions.** Not one word of the committed 22 s text was touched | **✓** `:1112` MCP *"15 of 16, DIVERGED, published"*; `:1114` Agent Skills **DESIGNED · NO RUN IS COMMITTED**; `:658` S3 Object Lock is not claimed; Bedrock boxed as exercised-here-not-in-path | **✓ BANS IT BY NAME.** `:1273` and `:1467` — **MUST NOT SAY** *"judges can query our ledger over MCP"*, with `credential_publishable: false` cited |
| 6 | `film/CLICKS.md` | **✓** `:119` — *"no `vo_word_budget` and no spoken line moves; the film is still 172 s"*; the beat headings run `B0` `0:00` → `B10` `2:16 → 2:28` | **✓ CHOREOGRAPHY OF RECORD.** `:89` — *"`2:17` IS STRUCK FROM THIS FILE"*, and `:12` in the header; `:828` the 2.5 s keystroke row; `:830` Click 6 at `2:14.0`; `:1321` the ledger row; `R-SD4b` at the end of §5 `B9` | **✓** its 47 deletions are the retired open-item box, the old `B9`/`B10` cursor tables and a stale header — **no spoken line lives in this file** | **—** | **—** silent |
| 7 | `film/CLICKS-CR.md` | **✓ by beat rather than by total** — `B9` 12 s at `2:04`, `B10` 12 s at `2:16`, `B11` does not exist (`:27` of its sibling sheet records the ruling) | **✓** `:208`–`:210` and the ruled box at `:229`; **both** struck numbers named — its own `+7.4` at `:245` and `CLICKS.md`'s `2:17` at `:248`; `R-SD4b` at `:268` | **✓** its 24 deletions are the retired disagreement box and a recap of `CLICKS.md`'s old table | **—** | **—** silent |
| 8 | `film/ONSCREEN-TEXT.yaml` | **✓** `:200` `film_total_s: 172`; `:231` — *"b10 12 = 148 demo. k1 6 + k2 10 + k3 6 = 22 close. end 2. 148 + 22 + 2 = 172"* | **✓** `b9.press_placement` (`:2121`) carries the ruling, the two struck numbers, an eleven-row in-beat timeline and `R-SD4b`; `b9.devtools.row.when_it_appears` puts the second `POST` row at `2:14.0` | **✓ it holds no spoken line at all** — it holds strings that go **on screen**. Its 8 deletions are the retired head/tail typing model | **✓** `:3351`/`:3353` the panel, 15 of 16 DIVERGED and **DESIGNED · NO RUN IS COMMITTED**; `:3852` bans *"all four exercised"* | **✓** `:3479` — the panel *"does not read as **you can query our ledger over MCP**"* |
| 9 | `film/FALLBACKS.md` | **✓** `:27` — *"172 s total, 174 s hard stop, 180 s ceiling"*; `:1084` the GO/NO-GO table lands `172` with `+2` margin | **✓ IN THREE PLACES, AS THE BRIEF REQUIRED.** **F-1a** (`:176`) prices a cold Click 6; **F-11**'s new table (`:659`) names both mutating rows by clock; **§4.2**'s gate box (`:988`) says what the gate gates. All three carry `R-SD4b` | **✓ 0 deletions.** Every change is additive and no spoken fallback line moved | **—** the fallback half names no tool state | **—** silent |
| 10 | `submission/VIDEO-KIT.md` | **✓ DEMOTED AND HONEST.** `:95` — *"the film is **172 s = 2:52** … `174` s hard stop … `180` s ceiling — `SPINE.md` §2"*; §0, §0.1, §0.2, §C, §D, §E all struck under `R-SD1` with `SPINE.md`/`BEATS.yaml` named as replacements; §0.1a is an explicitly subordinate copy | **— by design, and this is the fix.** It no longer places a click at all; `CLICKS.md`/`CLICKS-CR.md` are named as the choreography | **✓** §0.2 struck **in full** with *"No worker of this wave edited a spoken word anywhere, and this page must not be the second document prescribing one"* | **✓** `:726` the *"two of ten … not applied"* line **struck**; `:741` the re-run gate line **five, not two**; `:764` Agent Skills **DESIGNED**; `:767` Bedrock; `:769` **S3 Object Lock DESIGNED** | **✓ TWO EXPLICIT GUARDS.** `:2088` — a judge *"cannot"* read our ledger over MCP with a credential we supply; `:2204` — the verifiable read-only endpoint is the `mainline_judge` pgwire login, **not** the `claude mcp add` one-liner |

**How a stranger re-runs the whole of column (b) in one command:**

```bash
grep -c '2:17' docs/demo/film/*.md docs/demo/film/*.yaml docs/submission/VIDEO-KIT.md
```

**Every surviving hit sits inside a sentence that strikes it** — `CLICKS.md` ×5, `FALLBACKS.md`
×4, `ONSCREEN-TEXT.yaml` ×2, `CLICKS-CR.md` ×1, `VO-DEMO-CR.md` ×1 — and `grep -c '+7\.4'`
behaves identically. **`SPINE.md`, `BEATS.yaml`, `VO-DEMO.md`, `VO-CLOSE.md` and `VIDEO-KIT.md`
return zero.** A number that survives only inside its own strike-through is the shape a corrected
repository is supposed to have; a number that survives silently is the shape this readback exists
to catch.

---

### R.2 · WHAT THE READBACK CLOSED THAT NOBODY HAD ASSIGNED

**One cross-file defect was found by W3 and handed to W6 by name, and W6 closed it.**

| what | where it was | what was wrong | closed how |
|---|---|---|---|
| the typed proposed wording | `ONSCREEN-TEXT.yaml` `b9.proposed.head_typed` / `.tail_typed` | It carried *"Before any intrusive work, stored energy shall be isolated and locked."* — **69 characters** — with its head marked ***"pre-typed in pre-roll, 48 characters."*** **Both halves were wrong and neither was new.** The head could not be pre-typed **at all**: the change screen mounts at Click 5, `2:05.5`, **inside the take**, and the router tears the `moc-proposed-text` textarea down and re-creates it empty on the hash change — the same measurement the file already recorded at `todo.T-7`. And 69 characters in `R-SD4`'s 2.5 s is **27.6 keystrokes per second** | `CLICKS.md` §5 `B9` states the string under `R-SD4` — **`Isolate and lock.`, 17 characters, three words** — and `ONSCREEN-TEXT.yaml` now carries **that** string, with the retired pair kept as a `RETIRED` row so `CLICKS.md:952`'s pointer still resolves. **The rate is calibrated against a shot this film already scored**: `b0.el5.work_typed_tail` types `` verified at zero`` — also **17 keystrokes** — across `0:05.5 – 0:08.0`, also **2.5 s**. Same operator, same window, same rate |

**And the reasoning survived the shortening, which is why the shortening is not a loss.** The
proposal is legible as a *weakening* because it stops at `lock` and drops **`verified at zero`** —
the very phrase `b0`'s supervisor typed into his own permit on camera at `0:05.5`, quoted six
lines above it in the clause of record, with the anchor it walks away from (`ZERO_ENERGY`) printed
in the same panel. **`R-2` never required a character count**: it is discharged by the *act* of
typing into the console's own input with no provenance chip.

---

### R.3 · THE SIX RESIDUES — every one named by `file:line`, with an owner

**Not one of them is two shoot documents disagreeing about the film.** That is the finding.

| # | residue | `file:line` | why it is wrong, checkably | authoritative instead | owner |
|---|---|---|---|---|---|
| **RB-1** | **`MUST-NOT-CLAIM.md` names a watermark string this film does not burn.** Its §3 WHY cell reads *"The film carries the watermark `SYNTHETIC CORPUS · KESTREL RESOURCES IS FICTIONAL` … (`SHOT-LIST.yaml: watermark`)"* | `docs/submission/MUST-NOT-CLAIM.md:90`, pointing at `verticals/mainline/demo/script/SHOT-LIST.yaml:96` | **The film's watermark is a different sentence.** `ONSCREEN-TEXT.yaml:322` burns `SYNTHETIC CORPUS · EVERY SITE, PERMIT, INCIDENT AND PERSON HERE IS AUTHORED`, and `:331`–`:358` carry a full `deviation_from_committed_string` block: the committed string names **Kestrel Resources**, the CORPUS world's cleared fictional operator, and **this film is shot against the demo-api world**, whose site seeds as `demo_site` and renders as a uuid. `grep -ril kestrel verticals/mainline/apps/console/src/` **returns nothing**. A watermark naming an operator the frame never shows would disclaim the wrong fiction and leave the site, the permit, the incident and the person undisclaimed | **`ONSCREEN-TEXT.yaml` `watermark:` is the film's string.** `SHOT-LIST.yaml:96` remains correct **for the console cut**, which is still CI-gated and still committed. The deviation block also carries a **reversion condition**: if the operator UI ever does render Kestrel on the day, the committed string is used verbatim | **submission lead** (`MUST-NOT-CLAIM.md` is read-only to this wave). **Severity: low — the control is not weakened.** The film's string disclaims strictly more than the one the pointer names |
| **RB-2** | **`RULES-MATRIX.md` describes `VIDEO-KIT.md` as carrying two things `R-SD1` has just taken away from it:** *"The kit exists — **VO, timings**, seeded state, the sentences that may not be said on camera"* | `docs/submission/RULES-MATRIX.md:114` (R4's cell) | `VIDEO-KIT.md` §0.2 (**the VO**) and §0.1 (**the timings**) are now struck under `R-SD1`, each carrying *"this page must not be the second document prescribing one."* A reader following R4's cell opens the kit for the two things it has explicitly stopped being authoritative on | **The VO is `VO-DEMO.md` / `VO-DEMO-CR.md` / `VO-CLOSE.md`; the timings are `BEATS.yaml` and `SPINE.md` §2.** The kit is now the Devpost sub-rules, the machine, the pre-flight, the export settings and the must-not-claim extract | **`RULES-MATRIX.md`'s lead** — out of scope for every worker of this wave (§0 out-of-scope list) |
| **RB-3** | **The readiness script prints the same superseded description to the founder's terminal.** Its remedy text lists `docs/submission/VIDEO-KIT.md   the VO and the timings` | `scripts/submission/check_submission_ready.py:1335` (and the same pointer at `:1709`) | Identical to **RB-2**, and worse in one respect: **RULES-MATRIX is read, this is *printed* — on the run a founder makes before recording.** It is the same failure class as `S3`: correct-when-written guidance that has become a direction to the wrong file | same as RB-2 | **submission-tooling owner.** Brief label **`R-SD7`** — **the script is not this wave's to edit**, and no worker touched it. *(Recorded for the reader: §1 of this plan carries `R-SD1`–`R-SD5` only; `R-SD7` exists as a direction in W6's brief and is preserved here under that name rather than invented into §1)* |
| **RB-4** | **`SPINE.md` §7 assigns this wave's files to the PREVIOUS wave's worker ids.** It reads *"W4 owns `ONSCREEN-TEXT.yaml`"* and *"W5 owns `CLICKS.md`"* | `docs/demo/film/SPINE.md:526` and `:528` | In **this** wave `CLICKS.md` is **W3**'s and `ONSCREEN-TEXT.yaml` is **W6**'s (§2 of this plan). The same drift is in `CLAIMS-CLEARANCE.md` §12.9.1, which gives `D31`'s owner as *"W2, with W1 for the seconds"* — film-re-cut-wave ids. **A founder or orchestrator reading either at 02:00 looks for the wrong worker** | **§2 of this plan is the id table for this wave.** The *files* are unambiguous in every case; only the labels drift | **film lead**, at the next spine revision. **Severity: low, and it is a labelling hazard rather than a claim** — no file's content is wrong because of it |
| **RB-5** | **`b10`'s `0.4 s` of free slack is claimed by two things and cannot be spent twice.** `R-SD4a`'s floored press fallback and `CLAIMS-CLEARANCE.md`'s `D31` want the same `0.4 s` | `CLAIMS-CLEARANCE.md` §12.9.2 · `VO-DEMO.md:630` · `CLICKS.md` `R-SD4a` · `FALLBACKS.md` **F-1a** and §6 **W6-10** | `b10`'s 1.5 s of slack is **0.6 s mirror hold + 0.5 s spoken `SQLSTATE` + 0.4 s free**, and `SPINE.md` §4 protects the first two. `D31` is priced at **21 words running `1.13 s` against `0.95 s`** — an `0.18 s` overrun with nowhere else to come from | **This one is SUPPOSED to stay open.** It is a rehearsal trade between a stopwatch and a claim, and `R-SD4a` says the film lead spends it on one, states which, and does not discover it on the day. **`D31` is left OPEN, `~`, un-downgraded** | **film lead** for the `0.4 s`; **W2 with W1** for `D31`'s wording. **Found independently by three workers**, which is the strongest evidence in this wave that it is real |
| **RB-6** | **The typed string is now stated in two files, and one of them must follow the other.** `CLICKS.md` §5 `B9` owns `Isolate and lock.`; `ONSCREEN-TEXT.yaml` `b9.proposed.head_typed` now carries the same 17 characters | `docs/demo/film/CLICKS.md` §5 `B9` (owner) · `docs/demo/film/ONSCREEN-TEXT.yaml` `b9.proposed.head_typed` (copy) | **They agree today** — this worker copied rather than composed, and said so in the row. But this is structurally the **S8** shape the whole wave exists to remove: one string, two files. It is recorded so that a later edit to either is known to require the other | **`CLICKS.md` §5 `B9` is the authority for the string and its character count** (`R-SD4`); `ONSCREEN-TEXT.yaml` records what the frame carries and defers | **W3 / film lead.** **Severity: low today, and it is a standing hazard rather than a defect** — the mitigation is that the copy says in its own row that it is a copy |

---

### R.4 · WHAT THIS READBACK DID NOT DO

* **It did not edit `VO-CLOSE.md`, `close-block.md`, `feature-census.md`, `RULES-MATRIX.md`,
  `MUST-NOT-CLAIM.md` or `SUBMISSION.json`.** All six were **read**; three of them produced
  residues above; none was touched. A worker who repairs another lead's file destroys the only
  evidence that the wave needed repairing.
* **It did not edit `scripts/submission/check_submission_ready.py`**, whose printed remedy text is
  `RB-3`. The script is not this wave's.
* **It did not discharge `D31`, and did not choose the `0.4 s`.** Both stay open with owners.
* **It did not add a second, a word, a budget or a beat.** `172` s, `174` s hard stop, `180` s
  ceiling; every `vo_word_budget` and every `t`/`dur` in `BEATS.yaml` is exactly what it was.
* **It made no network call, ran no `terraform`, touched no AWS surface, read or wrote no SSM
  parameter, printed no credential, created and dropped no database, widened no grant and revoked
  none, and committed nothing.** The `mainline_qa` divergence stays open and the MCP verdict stays
  **`15/16 · DIVERGED — KNOWN GAP`**.

**Signed:** W6 · the readback · shoot-documents wave · 2026-08-16 (UTC).
**Files written: `docs/demo/film/FALLBACKS.md`, `docs/demo/film/ONSCREEN-TEXT.yaml`,
`docs/demo/film/CLAIMS-CLEARANCE.md`, `docs/demo/film/CLAIMS-CLEARANCE-CR.md`, and this section.**
