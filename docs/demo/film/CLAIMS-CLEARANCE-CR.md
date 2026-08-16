<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->
<!-- prose-hygiene: register -->
<!--
THIS FILE IS A REGISTER. It quotes forbidden sentences verbatim beside the true ones, which is
what a clearance sheet is for. It therefore carries the `prose-hygiene: register` marker, the same
marker docs/submission/MUST-NOT-CLAIM.md, docs/demo/research/r6-honesty.md,
docs/demo/film/CLAIMS-CLEARANCE.md and docs/demo/film/VO-DEMO.md carry.

EVERY QUOTED PROHIBITION SITS ON A SOURCE LINE THAT ALSO CARRIES ITS OWN NEGATION MARKER, because
the scanner's negation exemption is LINE-SCOPED. SPINE.md's own scanner verdict records that trap:
a `never` that wraps away from the phrase it governs stops exempting it. §6 records this file's
actual scan, its finding count and its exit code. If this path is ever added to a scanner's sweep
list, the scanner must PRINT that it skipped this file, so "not scanned" is never read as "passed".
-->

# CLAIMS CLEARANCE — CR — the line-by-line audit of use case two's two blocks

**Worker W6** · the film blocks for use case two · cr-gate-route wave · audited 2026-08-16 (UTC) ·
**re-headed 2026-08-16 when the block collision closed in favour of TWO blocks**
**Audits, exclusively:** `docs/demo/film/VO-DEMO-CR.md`, `docs/demo/film/CLICKS-CR.md`, and this
file. **`CLAIMS-CLEARANCE.md` is not edited by this worker** and continues to own `B0`…`B8`, the
close, and the other five film documents.

> **`B11` DOES NOT EXIST.** The 24 s of use case two ships as **`B9` 12 s + `B10` 12 s**, which is
> what `BEATS.yaml` always encoded. Rows below that read `B11` audit **the tail of `B10`** — the
> mirror — and are re-labelled where they were touched. The ruling and its reasons are in
> `VO-DEMO-CR.md` §0.3; §8 of this sheet carries the consequences for its own verdict.
>
> **Two rows of this sheet did not survive that re-read, and both were mine.** Row 12 cleared the
> mirror's unscoped first half and row 14 cleared a substitute built on it. **Both are withdrawn**
> — see §2 — because `B7` shows the permit **ISSUED** on that clause thirty seconds earlier, which
> row 12's reasoning never reached. `CLAIMS-CLEARANCE.md` files it as **X5**, the fifth refused
> mirror variant, beside the four R-7 ordered.
**Registers read in full before a row was written:** `docs/demo/research/r6-honesty.md` Part A
(A1–A17), `docs/submission/MUST-NOT-CLAIM.md` (fourteen families plus the three repeated ones),
`docs/demo/film/CLAIMS-CLEARANCE.md` §§1–2 for the method, `docs/demo/film-recut-plan.md` §4.3 and
R-7, and `docs/demo/cr-gate-route-plan.md` §§R3, R9, R10.

---

## THE VERDICT, FIRST

**2 spoken lines and 1 surviving substitute · 50 audited rows · 41 CLEAR · 0 REWORD · 8 REFUSE ·
1 scanner verdict — and THREE of the eight REFUSE rows exist because this sheet cleared a sentence
it should have refused.** (`49` clearance rows + `1` scanner verdict. Counted by verdict marker,
not by memory: §2 carries 25 rows — 23 CLEAR, 2 REFUSE — §4 carries 6 REFUSE, §5 carries 18 CLEAR.)

> ## THE TWO BLOCKS AS WRITTEN MAY BE SHOT. THEY CANNOT BE SHOT YET, AND THAT IS NOT A CLAIMS DEFECT.

Two separate things, and the second is the one that decides whether there is a film:

1. **Nothing in `VO-DEMO-CR.md` or `CLICKS-CR.md` claims more than its evidence carries** — on the
   condition that every value in §5's register is re-derived from the filmed run before the take.
   Five of the eight REFUSE rows are **pre-emptive**: three (`R1`–`R3`) are the variants of the
   mirror that drop the adverb, filed under `film-recut-plan.md` R-7's explicit instruction to file
   a REFUSE against every one of them, and two more (`R4`, `R5`) are sentences that would contradict
   the frame they are spoken over. **None of those five is in the script**; they are here so that
   nobody improvises one at 02:00.

   **The other three are not pre-emptive, and this sheet says so in its own verdict rather than in
   a footnote.** Rows 12 and 14 **cleared a sentence that shipped as a primary line and had to be
   replaced** — *"You can't use the clause"*, unscoped — and `R3b` is the bar that should have been
   filed beside `R1`–`R3` and was not. **R-7 ordered four refusals and four were filed, all against
   the half of the mirror that carries an adverb; the half without one was cleared without being
   walked past `B7`.** The correction is row 12b and `CLAIMS-CLEARANCE.md` **X5** / **D32**. **A
   refusal list is only as good as the half of the sentence it was pointed at.**

   **One finding of my own that survives intact, and it is arithmetic rather than a claim.** R-7's
   sanctioned substitute A is **17 words**, which was `2.13 w/s` in the retired 8 s window — over
   every rate ceiling in this kit — and is **2.17 w/s** behind the refusal sentence in the merged
   12 s block. It is **retired** at §2 row 14 on the claim as well. Substitute B, cleared at row
   14b, fits under either shape and is now the only one. A substitute nobody had counted is a
   substitute that gets read at 02:00 and overruns the beat after it.
2. **The attempt these blocks narrate cannot be made against the deployment today, and that is now
   three independent measurements rather than two.** `cr-gate-route-plan.md` §0.2,
   `film-recut-plan.md` §1.3, and — landing while this sheet was being written —
   **`evidence/deploy/cr-gate-live.json`**, W5's own transcript, which closes on
   `verdict: "UNANSWERABLE"`, `exit_code: 2`, `failures: []`. In it:
   `cr_gate_run_probe.status` = **404**, `cr_blocking_checks.status` = **404**,
   `why_unanswerable.cr_blocking_checks_declared` = **false**,
   `why_unanswerable.declared_path_count` = **17**. The shipped approve control is hard-disabled and
   wired to nothing. **There is currently no way to attempt the edit and be refused.** That is this
   wave's whole build, it belongs to other workers, and it is condition 1 in §7.

   **W5's file keeps the two findings apart in its own words** — a route that has not been deployed
   is not a refusal that did not happen — and this sheet does not soften that sentence to make a
   film possible.

3. **THE MOST DANGEROUS ROW ON THIS SHEET IS A TRUE VALUE IN THE RIGHT FILE UNDER THE WRONG
   LABEL.** `cr-gate-live.json` carries a `gate_run_summary` block with `merge.sqlstate = "23514"`,
   `merge.constraint = "gate_closed_when_issued"` and
   `projection_drift_attack.constraint = "mainline.fn_permit_merge_gate"` — **every one of them the
   PERMIT's**, present as the control that proves the origin was healthy while the CR probes were
   404ing. **A frame or a line built by reading `gate_run_summary.merge.sqlstate` puts `B2`'s
   refusal on screen labelled as the change request's.** It would pass every scanner in the kit.
   §5's second boxed row and `VO-DEMO-CR.md` §6.1 are the guard, and this sheet's verdict depends
   on that guard holding.

**One superseding row is filed and it is the only change this sheet makes to a standing
prohibition** — §3, retiring `r6-honesty.md` A13.5's ban **conditionally**, on the measurement that
retires it and on nothing else. `r6-honesty.md` itself is not edited: a research record is not
rewritten because the world moved; it is cited and superseded.

---

## 1 · WHAT WAS AUDITED, AND HOW

### 1.1 The corpus

| file | owner | audited in | rows |
|---|---|---|---:|
| `docs/demo/film/VO-DEMO-CR.md` | W6 | §2 — every spoken sentence and both cleared substitutes | 25 |
| `docs/demo/film/VO-DEMO-CR.md` | W6 | §4 — the refused variants | 5 |
| `docs/demo/film/CLICKS-CR.md` | W6 | §5 — every on-screen string and every value's provenance | 17 |
| this file | W6 | §6 — its own scan | 1 |
| | | **total** | **48** |

**§3 is a ruling, not a row.** It supersedes a standing prohibition and is counted in neither
column, for the same reason `CLAIMS-CLEARANCE.md` §1.1 counts a shared string once: a sheet that
inflates its own arithmetic is doing the small version of the thing it exists to prevent.

### 1.2 What the three verdicts mean

Identical to `CLAIMS-CLEARANCE.md` §1.2, so the two sheets can be read together.

| verdict | meaning | consequence |
|---|---|---|
| **CLEAR** | the line may be spoken or rendered as written, and every value in it is one this audit traced to a kernel artefact, a migration, a live response, a committed evidence file — or is registered as `PENDING` with the field path it will be read from | shoot it, once §5 is discharged |
| **REWORD** | the substance is supported but the wording claims more than the evidence carries | exact replacement given; the block survives unchanged |
| **REFUSE** | the line asserts something the run, the render or the payload does not support, and no delivery can rescue it | it does not go on camera in this form |

### 1.3 The rule this audit worked under

**Nothing was cleared that could not be traced to a file, a line, a live response, or a registered
`PENDING` field path, and no family was softened to let a sentence through.** Where a line was
defensible only under a condition, the condition is written into its row rather than assumed.

**A `PENDING` row is not a cleared value.** It is a cleared *sentence* with a named source, and
`VO-DEMO-CR.md` §6's rule stands: a row still `PENDING` on the day the film is cut is a row whose
value does not go on camera.

### 1.4 What this worker did and did not do

* **Read-only against anything deployed. No `POST`. No `GET`.** This worker issued no request to the
  live origin at all; every live reading cited here is another worker's, taken this session, and
  each is named where it is used. **No `terraform` anything. No AWS surface touched. No SSM
  parameter read or written. No credential printed or handled.**
* **`evidence/deploy/cr-gate-live.json` was read in full from disk** after it landed mid-audit, and
  every row in §5 marked *measured* names the field path it came from. Its own disclosure —
  `no_apply_was_run.statement`: *the script is an HTTP client*, no terraform, no AWS API, no SSM
  write, no credential, no database connection — is recorded here as well as there, because a
  clearance sheet that let a disclosure disappear between two files would be doing the small
  version of the thing it exists to prevent.
* **No database work**, so no scratch database was created — an empty `w_W6` would have been a write
  with no reader.
* **The pytest suite was not run, and that is safe rather than lazy.** The only files this worker
  writes are three markdown files under `docs/demo/film/`. `CLAIMS-CLEARANCE.md` §1.4 already
  measured the same question for the same directory and found two tests and one script naming
  `docs/demo/**`, none of which globs `docs/demo/film/**`, and no workflow triggering on `docs/**`.
  The **998 collected / 997 passed / 0 failed / 0 errors** baseline cannot move for markdown nothing
  reads. **If that ever changes, the number comes from a `--junitxml` root element and from nothing
  else** — never from a terminal tail, because the suite is silent for minutes and healthy runs have
  been killed for looking hung.
* **Nothing was committed.** Three files were written and no file outside those three was modified.

---

## 2 · EVERY SPOKEN SENTENCE

`✓` CLEAR · `~` REWORD · `✗` REFUSE. **Family** is the register row walked past. **Why it clears**
is the artefact, not an argument.

| # | block | spoken | v | family | why it clears |
|---|---|---|---|---|---|
| 1 | B9 | *"Then change the rule instead."* | ✓ | A5 tense · fabrication | It is the viewer's objection voiced, not a claim about the system. No tense, no number, no mechanism. `VO-DEMO-CR.md` B9's delivery note requires it be said as a good point rather than a straw man, which is the only way it can go wrong. |
| 2 | B9 | *"Same paragraph."* | ✓ | A3 one world · R-5 | True only if the clause identifier in frame is the one `B3` showed. `CLICKS-CR.md` §5.4 makes that a pre-flight check by eye rather than an assumption, and §4 assumption 4 cuts the sentence if it fails. |
| 3 | B9 | *"Same incident behind it."* | ✓ | A3 corpus · R-F severity-not-injury · R-5 | Names `DEMO-INC-0001` by pointing rather than by speaking it, and adds **nothing** to what `B3` already established. No date, no site, no job title, no injury, no person. The seeded precursor describes nobody and `demo_world.sql`'s own narrative column says so. Cleared **on the same condition as row 2**. |
| 4 | B9 | *"This request asks to edit it."* | ✓ | **A5 tense — the family with no scanner behind it** | Present tense, and it is a **row's standing content**, not a retrieval. `mainline.change_request` carries a proposal; describing what a row proposes is not narrating a lookup. The recall is spoken of in the past tense everywhere in this film, as `B3` fixed. |
| 5 | B9 | — *the word "rewritten" is not spoken* | ✓ | fabrication / seed reshaping | `VO-DEMO.md` §6 already bans *"the rewritten clause"*. **MUST NOT SAY:** *"the rewritten clause"* — nothing has been rewritten; somebody has proposed to, and the script says *asks to edit*. |
| 6 | B10 | *"Refused."* | ✓ | A4 live-demo claims | It is the refusal, not a category. The value it refers to is on screen in the same frame, from the response that landed under B9's last words. |
| 7 | B10 | *"**23514** again"* | ✓ | A4 · A14 numbers that move | **The only kernel-produced value spoken in all three blocks**, registered `PENDING` at `VO-DEMO-CR.md` §6.1 S1 against `data.beats[name="merge"].sqlstate`. **If the filmed run answers anything else, the line changes to match the kernel.** *"Again"* is checkable in one frame: `B2` said the same five digits over a different subject. |
| 8 | B10 | *"a different CHECK"* | ✓ | A8 where the refusal lives | Scoped to this beat, which really is a declarative CHECK on `mainline.change_request` (`verticals/mainline/db/migrations/0051_change_request.sql:85`). Both constraint names are in the frame at the instant *different* is said. **MUST NOT SAY:** *"the same constraint refused it"* — it is a different constraint and the frame shows both names. |
| 9 | B10 | *"guarding the change"* | ✓ | A8 · over-claiming the predicate | The CHECK is on the change-request row and its predicate is in frame. It says what the constraint is attached to, and nothing about what else it can or cannot stop. **MUST NOT SAY:** *"the database refused the edit"* — what was refused is the merge; the edit can still be made by answering the obligation first. |
| 10 | B10 | — *the constraint name is not spoken in the primary read* | ✓ | A14 · delivery | The name is on screen with its field label for the whole block. Speaking it costs about two seconds the mirror needs more. The 8 s alternate that speaks it is cleared as row 11. |
| 11 | B10 alt | *"a different CHECK, **cr_gate_closed_when_merged**, guarding the change itself."* | ✓ | A8 · A14 | Same clearance as rows 8–9, **on the condition that the name spoken is the one `data.beats[name="merge"].constraint` returned on the filmed run** — not the trigger name, not the function name. §5's boxed row is the whole of this condition. |
| 12 | B10 tail | *"You can't use the clause."* | **✗ SUPERSEDED 2026-08-16** | A8 · A9 defence in depth | **This row's ✓ is withdrawn by the worker who filed it.** It cleared the sentence against `B2` — a permit relying on this clause was refused while an obligation was open — and **it did not walk past `B7`, which it should have.** `B7` shows that same permit **ISSUED** on that same clause thirty seconds before the mirror, once its obligation was answered, so the unscoped sentence is contradicted by the film it is spoken in. **MUST NOT SAY:** the unscoped form, in any block or fallback. **TRUE INSTEAD:** *"You can't **just** use the clause."* — `CLAIMS-CLEARANCE.md` **D32** and **X5**. |
| 12b | B10 tail | *"You can't **just** use the clause."* | ✓ | A8 · A12 · R-7 | The replacement, and the line of record. **`just` scopes the first half exactly as `quietly` scopes the second**, so the mirror is scoped on both sides and neither scope is decoration: the clause **is** usable, and the audience watched it become usable — **not** without the obligation being answered. Cleared at `CLAIMS-CLEARANCE.md` D32 as an improvement on the wording this sheet had cleared at row 12. |
| 13 | B10 tail | *"You can't **quietly** edit it away."* | ✓ | **A9 · A10 tamper-evidence · the R-7 family** | **The scope word carries the entire claim.** The clause *can* be edited — by disposing of the obligation first, which is exactly what the three defeater prompts in frame are for. What cannot be done is doing it **without the obligation being answered**, which is what the refusal in the same frame just demonstrated. Cleared **only** with the adverb; every variant without it is REFUSED at §4. **`either` dropped, cleared at `CLAIMS-CLEARANCE.md` D33:** the parallel construction carries the tie, and row 12b's `just` carries it harder. |
| 14 | B10 sub A | *"You can't use the clause. ·hold 0.4· You can't edit it away either — not without answering the question first."* | **✗ RETIRED 2026-08-16** | same | **Retired on the claim, and separately on the arithmetic.** On the claim: **its first half is the unscoped sentence row 12 and `CLAIMS-CLEARANCE.md` X5 refuse**, and the trailing clause does not reach back over it. On the arithmetic: it was priced at 11 s against the retired 8 s `B11`, and in the merged 12 s `B10` it must sit behind the refusal sentence — `9 + 17 = 26 w` = **2.17 w/s**, over every rate ceiling in this kit. **A substitute has to be right in both halves.** |
| 14b | B10 sub B | *"Use it, or edit it. ·hold 0.4· Not without answering the question first."* | ✓ | same | Same scope, carried by a clause. **Re-priced for the two-block shape and it still fits:** behind the refusal sentence in one 12 s block it is `9 + 11 = 20 w` = **1.67 w/s**, identical to the line of record. It keeps both halves of the mirror. Cleared on the same terms as row 13: what it denies is doing either **without the obligation being answered**, which the refusal in the same frame just demonstrated. **It is now the ONLY surviving substitute**, and it is a substitute rather than a co-primary — the line of record's parallel denial cannot be mis-parsed as permission, and an imperative can. |
| 15 | all | — *no timing of the system is spoken* | ✓ | A2 latency · MNC 2 | Not a millisecond, not a round trip, not a *"fast"*. **MUST NOT SAY:** *"it refuses in milliseconds"* — this repository holds no p50, no p99 and no load profile. Per-beat elapsed is on screen with its own label saying whose clock it is. |
| 16 | all | — *no digest, commit id, uuid or byte count is spoken* | ✓ | A14 · `HYG-sha-literal` | None appears in any spoken line. `VO-DEMO-CR.md` §3 states the ban; §6 registers every on-screen value to a field path instead. |
| 17 | all | — *`blood_major` is never spoken, and no severity is spoken for this obligation* | ✓ | A3 · R-F | `film-recut-plan.md` §4.3 rules it. Saying an injury-shaped word aloud edges toward inventing a casualty to move an audience. `B3` already spent the film's one spoken *severity four*, where the seed-versus-projection pairing is on screen to check it. |
| 18 | all | — *the second `P0001` is on screen and never narrated* | ✓ | A9 · delivery | The projection-drift beat is in the transcript panel in payload order where a judge can read it. **MUST NOT SAY:** *"defence in depth, proven"* — this wave proves one direction on one subject, and the unwelding matrix has never executed in CI. |
| 19 | all | — *no present-tense sentence about the retrieval* | ✓ | **A5 — no scanner reads a tense** | **MUST NOT SAY:** *"watch it remember"* · *"the system just retrieved the incident and blocked the change."* The recall already ran; the only present tense in this film is the re-derivation on a button press, which really executes. |
| 20 | all | — *no AWS service, region, model or agent is named* | ✓ | A5.2 · A6 · A7 | No model is in this request path and no agent has called this deployment. The service roll-call belongs to the close, over live picture, where a judge can pause on it. |
| 21 | all | — *the product's name is not spoken* | ✓ | MNC 17 | **MUST NOT SAY:** *"an open-source agentic memory layer"* as a lead — the category belongs in the close, where it is earned. These blocks show the memory reaching a second subject instead of naming it. |
| 22 | all | — *no claim about anybody's judgement, sincerity or diligence* | ✓ | A12 · MNC 6 | **MUST NOT SAY:** *"it catches rubber-stamping"* — nothing in this data model separates a considered disposition from a rubber stamp. These blocks make no claim about a person at all. |
| 23 | all | — *no tamper-proofing claim* | ✓ | A10 · MNC 14 | **MUST NOT SAY:** *"tamper-proof"* in any form, and **MUST NOT SAY:** *"split-view resistant"* — tamper-evidence is the claim, there is one witness and it is ours. |
| 24 | all | — *no claim that this was proven in CI* | ✓ | A11 · A4 | **MUST NOT SAY:** *"we proved it in CI"* — nothing in CI has ever asserted this URL. Every live reading in these files is hand-measured, attributed to the worker who took it, and dated. |

---

## 3 · THE SUPERSEDING ROW — `r6-honesty.md` A13.5, retired CONDITIONALLY

**Filed under `film-recut-plan.md` R-8**, whose authority is precedence: `r6-honesty.md` is a dated
research record and this is the film's live clearance sheet. **Nobody edits `r6-honesty.md`.**

**The standing prohibition, quoted exactly as A13.5 carries it.** **MUST NOT SAY:** *"watch the same debt block the change request."*

**The two grounds A13.5 gives, and their state today:**

| A13.5's ground | measured today | by |
|---|---|---|
| *"There is no `POST /v1/change-requests/{cr_id}/merge`"* — measured 404, and the 404 body declares the whole route table | **still true, and now measured a third time.** The declared-path enumeration in W5's transcript is **17 paths** and contains no committing change-request route and no `/v1/demo/cr-gate-run`. | `cr-gate-route-plan.md` §0.2 · `film-recut-plan.md` §1.3 · `evidence/deploy/cr-gate-live.json` → `why_unanswerable.declared_paths`, `.declared_path_count` |
| *"and no console surface"* | **no longer true.** `GET /operator.html` now serves its own entry bundle containing a complete Management-of-change surface, and it is no longer byte-identical to `GET /`. | `film-recut-plan.md` §1.4 |

**RULING.** A13.5's ban was correct on the day it was measured, its second ground has been closed by
work that landed since, and **its first ground is still standing.** So:

* **The ban is NOT lifted today.** While `POST` answers `404`, the change request can only be
  *told* rather than *driven*, and A13.5's `TRUE INSTEAD` is still the right sentence.
* **The ban is lifted the moment `CLICKS-CR.md` §5.1's three checks all hold**, and not one moment
  earlier. At that point the subject is genuinely driven on camera, which is the only thing A13.5
  was ever objecting to.
* **Even then, the banned sentence itself is not adopted.** *"Watch the same…"* is a present-tense
  imperative about a retrieval and it trips A5 independently of A13.5. The cleared line is the
  mirror at `B10`'s tail, which speaks in no tense about the recall at all.

**This is the only standing prohibition this sheet touches, and it is narrowed rather than
waived.**

---

## 4 · THE REFUSED VARIANTS — filed under R-7, none of them in the script

`film-recut-plan.md` R-7 instructs this worker to *"file a REFUSE row against every variant that
drops the scope word."* Here they are, with what makes each false.

| # | ✗ REFUSED variant | why it is false, not merely strong |
|---|---|---|
| R1 | **MUST NOT SAY:** *"You can't edit the clause."* · *"The clause cannot be changed."* | It **can** be changed — by disposing of the obligation first. The three defeater prompts in the same frame are the mechanism for doing exactly that, so the sentence is contradicted by the picture it is spoken over. |
| R2 | **MUST NOT SAY:** *"The database won't let anyone edit the rule."* | Adds *anyone*, which is a claim about every caller and every code path. A cluster admin can drop a constraint; what they cannot do is do it unobserved. Tamper-evident, never tamper-proof. |
| R3 | **MUST NOT SAY:** *"The memory is immutable."* | Nothing here is immutable. The gate refuses a **transition** while a counter and a re-derivation disagree with the state being written; it is a condition on a change, not an absence of change. |
| **R3b** — added 2026-08-16, **and it is the one this sheet cleared by mistake** | **MUST NOT SAY:** *"You can't use the clause."* with no scope word — the mirror's **first** half | R-7's instruction was to refuse every variant that drops the scope word, and R1–R3 above discharge it **for the second half only**, because that is the half whose scope is an adverb. **The first half's scope is `just`, and this sheet cleared the sentence without it at row 12.** It is false in the plainest possible way: **`B7` shows the permit ISSUED on that clause thirty seconds earlier**, on camera, once the obligation was answered — so the flat sentence is contradicted by a frame the viewer has already watched. **TRUE INSTEAD:** *"You can't **just** use the clause."* (row 12b, `CLAIMS-CLEARANCE.md` D32 / X5). |

**The cleared form is rows 12b and 13 of §2 and it keeps BOTH scope words**: *"You can't **just**
use the clause. You can't **quietly** edit it away."* **The sanctioned substitute is row 14b** —
the only surviving one — if an adverb reads oddly on the day. **Row 14's substitute A is retired**,
because its first half is R3b.

**Two more, refused for a different reason.**

| # | ✗ REFUSED | why |
|---|---|---|
| R4 | **MUST NOT SAY:** *"and there is no way through"* | There are three, they are on screen, and each demands a citation. `film-recut-plan.md` R-4 makes showing them the mitigation for use case two having no admission beat, and a sentence contradicting the frame would spend the mitigation to make a worse point. |
| R5 | **MUST NOT SAY:** *"the same debt blocks both"* — as an unqualified sentence | The two subjects carry obligations raised from the same clause's blame closure; whether they are the *same row* is a claim about the data model that this film does not put on screen and this worker did not verify. The cleared claim is the one the frame carries: same clause, same precursor, two gate families. |

---

## 5 · `CLICKS-CR.md` — EVERY ON-SCREEN VALUE AND ITS PROVENANCE

Seventeen rows. **A frame is cleared when every string in it traces to a payload field or to a
string the shipped page itself constructs.**

> ### ⛔ BOXED ROW ONE — the permit's values are in the change request's evidence file
>
> `evidence/deploy/cr-gate-live.json` → `gate_run_summary.merge.sqlstate` = `"23514"`,
> `.merge.constraint` = `"gate_closed_when_issued"`,
> `.projection_drift_attack.constraint` = `"mainline.fn_permit_merge_gate"`,
> `.beat_names` = `["read","merge","projection_drift_attack","admit"]`.
> **All four are the permit's**, from `POST /v1/demo/gate-run`, recorded as the control that proves
> the origin was healthy while the CR probes answered `404`. **B10's SQLSTATE and B10's constraint
> name come from the CR run's own merge beat and from nothing else.** There is no such beat in this
> file today.

> ### ⛔ BOXED ROW TWO — three objects, one character apart
>
> `cr_gate_closed_when_merged` is a **CHECK** (`verticals/mainline/db/migrations/0051_change_request.sql:85`).
> `cr_merge_gate` is a **TRIGGER** (`verticals/mainline/db/migrations/0131_trg_cr_merge_gate.sql:38-41`).
> `mainline.fn_cr_merge_gate` is that trigger's **function**
> (`verticals/mainline/db/migrations/0116_fn_cr_merge_gate.sql`) and it is what a `P0001` names.
> **A frame that captions one as another writes a claim the kernel does not make.**
> `CLICKS-CR.md` §5.3 makes this a two-person pre-flight check read aloud against the payload.

| # | on screen | v | provenance | condition |
|---|---|---|---|---|
| 1 | `Management of change`, the five OSHA headings, `Clause of record — current text, as returned`, `Proposed wording`, `Compare with clause of record`, `Approve change` | ✓ | strings the shipped page constructs — `osha-sections.ts:57-67, 264, 291-301`, `absence.ts:413` | none |
| 2 | the external ref `DEMO-MOC-0001`, the state chip `checks_materialised`, and the header counters `1 / 0 / 0` with `head_seq 1`, `gate_epoch 1`, `merged_commit null` | ✓ | **measured** — `cr_read.body.data.external_ref`, `.state`, `.counters.*`, `.head_seq`, `.gate_epoch`, `.merged_commit` | sourced |
| 2b | the four `cr_*` CHECKs with their predicates, and `blamed_by_refusal: false` on all four | ✓ | **measured** — `cr_read.body.data.constraints[]`, read out of `pg_catalog.pg_constraint` at request time (`cr_read.body.statement_refs[1]`) | sourced. **MUST NOT SAY:** anything about `blamed_by_refusal` aloud — it is a column, it reads `false` because no attempt has been made, and a judge who notices it has found it themselves. |
| 3 | the clause of record, verbatim, `SYNTHETIC —` prefix uncropped | ✓ | the clause-version read | `PENDING` — that read is not in the transcript; **never cropped to make a frame prettier** |
| 4 | the clause identifier | ✓ | **measured** — `subjects.body.data.clause_uuid`, **and it is the identifier `B3` shows** | sourced · **half of R-5** |
| 5 | the precursor beside the CR refusal | ✓ | the CR blocking-checks read | **`PENDING` and at risk** — that route is **not declared** (`why_unanswerable.cr_blocking_checks_declared` = `false`), and `renderObligation` states today that the precursor *is not reachable from any declared route*. §7 condition 4, and the other half of R-5. |
| 6 | the typed proposed wording, **no provenance chip** | ✓ | typed on camera into `moc-proposed-text`; no code path in that directory can put a character in it | none — this is the convention, not an exception |
| 7 | the browser-side comparison, labelled as computed in the browser | ✓ | `osha-sections.ts` computes it and labels it | none |
| 8 | the SQLSTATE | ✓ | the CR run's own merge beat | **`PENDING` — no beats block exists in the transcript today.** Boxed row one: **not** `gate_run_summary`. |
| 9 | the constraint name as the refusal reports it | ✓ | the same beat, cross-read against row 2b's measured `cr_gate_closed_when_merged` | `PENDING` · **boxed rows one and two** |
| 10 | `constraint_source` | ✓ | the same beat | `PENDING`. **If it reads `parsed`, the label says `parsed`.** A weaker diagnosis stays on screen; `B5` set that precedent and it is why the film is believed. |
| 11 | the refusal's own message | ✓ | the same beat | `PENDING`. The **grounds** are already public and measured at row 2b — `CHECK (((state != 'merged'::mainline.subject_state) OR (open_blocking = 0)))` beside `open_blocking = 1`. Only the attempt is missing. |
| 12 | the projected counter beside the re-derived count | ✓ | the run's read beat | `PENDING` |
| 13 | the projection-drift beat's SQLSTATE and message — **unspoken** | ✓ | that beat, which will name `mainline.fn_cr_merge_gate` | `PENDING`. **MUST NOT SAY:** anything about this beat aloud — a second `P0001` twenty seconds after `B5` halves `B5`. Boxed row one: the `mainline.fn_permit_merge_gate` in the transcript today is `B5`'s. |
| 14 | the three defeater prompts, verbatim, with no `not applicable` option | ✓ | the disposition read → `data.defeater_options[].prompt`; `absence.ts:529-579` renders only options that arrived on a live read | `PENDING`. **MUST NOT DO:** type into a citation box on camera — nothing in this deployment carries an answer and a typed citation would be a prop. |
| 15 | the clearance lattice | ✓ | the same read → `data.lattice[]` | `PENDING` |
| 16 | `persisted`, `self_persisted`, `isolation`, `single_transaction`, the two logical timestamps | ✓ | `data.persisted`, `data.persistence_check.self_persisted`, `data.transaction.*` | `PENDING`. **MUST NOT SAY:** *"nothing was written"* — the run's own fingerprint is what proves the unwinding, and `persisted false` is the sentence. |

**An absent beat renders as absent.** `cr-gate-route-plan.md` §R3 makes one beat conditional and
drops it if the deployed cluster answers a privilege error rather than a gate refusal. **A privilege
error is not a gate refusal and is never rendered as one**; there is no placeholder, no *skipped*
row, and no gap dressed as a pass.

---

## 6 · THE SCANNER VERDICT — an actual run, pasted, with its exit code

Recorded per the film's standing rule R-B: `docs/demo/film/` is outside every entry in
`claim_hygiene.py`'s `TARGET_GLOBS`, so the scan is invoked **by hand** and its result is pasted
here rather than inferred from a green lane. **"Not scanned" and "passed" are different results.**

```
$ .venv/Scripts/python.exe scripts/demo/claim_hygiene.py --check \
      docs/demo/film/VO-DEMO-CR.md \
      docs/demo/film/CLAIMS-CLEARANCE-CR.md \
      docs/demo/film/CLICKS-CR.md

  scanned 3 file(s) against 21 rules
  claim hygiene OK
                                                                          (exit 0)
```

**VERDICT: PASS — over all three files, in one invocation, at exit 0.** The backslashes above are
line-wrapping for this page; the command was invoked on one line, and the two output lines and the
exit code are verbatim.

**Re-run this after any edit to any of the three.** The trap `SPINE.md`'s own verdict records is
live in this file more than in any other in the kit: **the negation exemption is line-scoped**, so a
`MUST NOT SAY:` that wraps away from the phrase it governs stops exempting it. Every prohibition in
§§2–5 is written with its marker and its banned phrase on **one source line**, which is why several
rows in §2 are longer than they look.

**A green scan is not a clearance.** `CLAIMS-CLEARANCE.md` §2 lists the families with **no automated
rule at all behind them** — A5 tense, A8, A9, A13, A14, A4 — and every family this sheet actually
turned on is one of them. **Every REFUSE in §4 was found by a human reading an artefact. Not one was
found by the scanner.** That is the whole argument for this sheet existing.

---

## 7 · THE CONDITIONS — what has to be true before these blocks are shot

Pre-committed, in order, so nobody weighs one against the rubric at 02:00.
`CLICKS-CR.md` §5 is the executable form of each.

| # | condition | if it fails |
|---|---|---|
| **1** | **The attempt is reachable and it refuses.** `POST /v1/demo/cr-gate-run` answers `200` with `persisted: false` measured from its own fingerprint. **MEASURED TODAY: `404`** (`cr_gate_run_probe.status`). | **NO-GO as things stand.** `film-recut-plan.md` §6 is fully specified: `B9` and `B10` are never added, `B8` is restored to 10 s, the film runs `2:32`, and every service and feature is still named. A legitimate outcome. |
| **2** | **`GET /v1/change-requests/{cr_id}/blocking-checks` answers `200`.** **MEASURED TODAY: `404`, and `cr_blocking_checks_declared` reads `false`** — not declared, not merely unanswered. The change screen probes it. | the screen is filmed **only** in the state that renders clean, or not at all — never scrolled past fast so the absence does not register. |
| **3** | **The approve control drives that endpoint and nothing else.** | the press does not exist. **MUST NOT DO:** point it at the permit's merge route to make the screen work — that route drives a different subject and a button that refused a different record would be a prop. |
| **4** | **R-5 holds in frame:** the shared clause identifier and the precursor are legible beside the refusal. **Half is measured and holds** — `subjects.body.data.clause_uuid` is the identifier `B3` shows. **Half is not** — the precursor rides on the read that is not declared. | B9's *"Same incident behind it"* is cut, and `film-recut-plan.md` R-5 says the wave is abandoned rather than shot without it. |
| **5** | **The three defeater prompts are in frame through `B10`'s mirror.** | `B10` is still shot; the delivery note about showing the way through comes out, because nothing is showing it. |
| **6** | **Every `PENDING` row in §5 has been re-derived from the filmed run.** | that value does not go on camera. |
| **7** | **`B8` is cut to 6 s and the close lands at 22 s.** | the film runs past the 174 s hard stop. `VO-DEMO-CR.md` §0.2 has the arithmetic. |

**Under a NO-GO nobody builds a committing route, enables the approve control without the
demo-safe endpoint behind it, or grants `mainline_api` a write it does not hold today.** The
standing `transitions.materialise_checks` INSERT-without-privilege finding stays open and is not
this wave's to close. The demo guard's `423 Locked` stays.

---

## 8 · THE DISSENT THAT BECAME A RULING, AND WHAT IT COST THIS SHEET

**It was filed here as a dissent about an id scheme and it was not one.** `cr-gate-route-plan.md`
§R9 named these blocks **B9, B10, B11**; `film-recut-plan.md` §4 independently drafted **two**,
`b9` and `b10`, over the same 24 s of the same material. This worker followed the binding plan,
wrote three, recorded the collision, and called it *"a naming decision for the film lead and not a
defect in either plan."*

**That last sentence was wrong and it is the finding of this section.** The founder records
**voice first, then picture, then matches them**, so a block boundary is not a name — **it is a
place he stops recording and starts again.** Two documents disagreeing about how many boundaries
exist is a recording session that cannot be run, whatever the totals are, and both shapes totalled
24 s precisely so that no arithmetic check anywhere in the kit could ever have caught it. **A
collision that only a human reading two documents side by side can find is not a naming decision;
it is a defect that was left open under a label that made it sound optional.**

**RESOLVED 2026-08-16, in favour of TWO blocks.** `VO-DEMO-CR.md` §0.3 carries the ruling and its
three reasons. The deciding one belongs to another worker's measurement rather than to either
plan's seniority: `CLICKS.md` timed the change screen's four sequential reads at **≈ 3.5 s warm and
≈ 6 s cold** and measured that the proposed-wording box is **destroyed and re-created empty when
the screen mounts** — so the wording cannot be pre-typed and `B9` cannot be shot in 10 s. **The
case FOR three blocks is real and is recorded in that section rather than dismissed:** shorter
blocks are cheaper to re-take, and the ruling gives that up deliberately to keep the refusal, the
hold and the mirror inside one recorded breath.

**What it cost this sheet, stated plainly.** Two of its rows did not survive the re-read — row 12
and row 14 — and both had cleared the mirror's **unscoped first half**. **The three-block shape
and the two-block shape were therefore never equal in honesty**, whatever the arithmetic said,
because this file transcribed R-7's bar list as four items and dropped the fifth: the one its own
primary line broke. **That is worth more as a lesson than the ruling is:** a pre-emptive refusal
list is only as good as the half of the sentence it was pointed at.
