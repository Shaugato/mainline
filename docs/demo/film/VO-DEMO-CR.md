<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->
<!-- prose-hygiene: register -->
<!--
§3 and §5 of this file quote forbidden sentences beside the true ones, in the same form
docs/demo/film/VO-DEMO.md, docs/submission/MUST-NOT-CLAIM.md and docs/demo/research/r6-honesty.md
use. It therefore carries the `prose-hygiene: register` marker, and every quoted prohibition sits
on a source line that also carries its own explicit negation marker, because the scanner's
negation exemption is LINE-SCOPED (SPINE.md's own scanner verdict records that trap). If this
path is ever added to a scanner's sweep list, the scanner must PRINT that it skipped this file,
so "not scanned" is never read as "passed".
-->

# VO-DEMO-CR.md — the three spoken blocks for use case two

**Worker W6** · the film blocks for use case two · cr-gate-route wave · 2026-08-16
**Binding plan:** `docs/demo/cr-gate-route-plan.md` §R9 (this file's existence, its block ids, its
budget and its register), and §R3 / §R10 for what the run is allowed to claim.
**Read in full before a line was written:** `docs/demo/film/VO-DEMO.md` (format and register),
`docs/demo/film/SPINE.md` §0 (word counting) and §4 (per-beat prohibitions),
`docs/demo/film-recut-plan.md` §§2, 4, 5 (the seconds these blocks are spending and R-5, R-7, R-10),
`docs/demo/research/r6-honesty.md` A13.5, `docs/submission/MUST-NOT-CLAIM.md`.

**No commit id is written here.** `claim_hygiene.py`'s `HYG-sha-literal` rule refuses one and it is
right to: a commit id cannot be chosen in advance.

**Clearance:** every sentence below is cleared line by line in
[`CLAIMS-CLEARANCE-CR.md`](CLAIMS-CLEARANCE-CR.md), which also carries this wave's
`claim_hygiene.py --check` transcript and its exit code. Screen actions are in
[`CLICKS-CR.md`](CLICKS-CR.md).

**Delivered: 38 spoken words over 24 s = 1.58 w/s across the three blocks.** No block exceeds
1.70 w/s. §2 prices every second of the silence.

**THIS FILE RENUMBERS NOTHING.** `B0`…`B8` keep their ids, their durations and their words. The
film lead splices these three blocks after `B8` and `BEATS.yaml` remains the timing authority
(`SPINE.md` §0: where the two disagree, `BEATS.yaml` wins and the prose file is wrong).

---

## 0 · HOW TO READ THIS FILE

Identical conventions to `VO-DEMO.md` §0, restated so this file can be read on its own.

| mark | meaning |
|---|---|
| `[2:04]` | the block's in-point in the finished cut — **derived, see §0.2** |
| `·hold 0.4·` | the founder **stops talking** for that many seconds. A direction, not a breath. |
| **bold** in the spoken line | a value that must be on screen at that instant |
| `w` / `w/s` | words in the block, and words per second across the block's whole window |

### 0.1 · Word counting, so a later worker gets the same number

`SPINE.md` §0's rule, applied unchanged: **a word is a run of letters between spaces; a hyphenated
compound counts once; dashes, em dashes and punctuation are not words.** `VO-DEMO.md` §0 adds the
case this file needs: **`23514` is one word on the page** and about two and a half words of time in
the mouth, because it is read digit by digit — *two three five one four*. That is why B10 is
written at 1.50 w/s and not at the ceiling; §2 prices it.

`cr_gate_closed_when_merged` is one word on the page and roughly three words of time in the mouth.
It is **not spoken in the primary read** — it is on screen — and §1's B10 note says why, with the
alternate line that speaks it if the film lead pays the second.

### 0.2 · The in-points are DERIVED, and R9's `[2:00]` is a pre-`B0b` figure

`docs/demo/cr-gate-route-plan.md` §R9 sites these blocks "after `B8 · NONE OF IT PERSISTED` at
`[2:00]`". **`[2:00]` was true before `B0b` existed.** `VO-DEMO.md` was edited on 2026-08-16 at
09:37 to insert `B0b · WHY IT MATTERS`, 8 s at `[0:12]`, and every timecode after it moved by 8 s
without any file being told. `film-recut-plan.md` §1.1 measures the same thing independently.

Arithmetic, from `VO-DEMO.md`'s own durations plus `film-recut-plan.md` §2.1's `b8 10 → 6`:

```
B0 12 + B0b 8 + B1 10 + B2 14 + B3 18 + B4 10 + B5 16 + B6 18 + B7 12 + B8 6   = 124 s  → B9  at 2:04
B9 10                                                                          = 134 s  → B10 at 2:14
B10 6                                                                          = 140 s  → B11 at 2:20
B11 8                                                                          = 148 s  → close at 2:28
close 22 + end card 2                                                          = 172 s  = 2:52
```

**172 s is exactly `film-recut-plan.md` §2.1's target** — `172 ≤ 172` target, `< 174` hard stop,
`< 180` ceiling. These three blocks cost **24 s**, which is the middle of R9's `22–26 s` band and
the exact figure the recut budget reserved.

**A consequence worth stating rather than discovering.** If `B8` is **not** cut to 6 s, the film
runs `128 + 24 + 22 + 2 = 176 s`, which is **past the 174 s hard stop.** These blocks and the `B8`
re-time are one decision, not two.

The three candidate in-point sets, so nobody has to redo this at 02:00:

| assumption | B9 | B10 | B11 |
|---|---|---|---|
| `B0b` present, `B8` = 6 s — **the plan of record** | `[2:04]` | `[2:14]` | `[2:20]` |
| `B0b` present, `B8` = 10 s (over the hard stop) | `[2:08]` | `[2:18]` | `[2:24]` |
| pre-`B0b` spine, `B8` = 10 s — R9's `[2:00]` | `[2:00]` | `[2:10]` | `[2:16]` |

**The durations in the headers are mine and they are what this file owns. The in-points are
derived and `BEATS.yaml` is their authority.**

### 0.3 · The block ids, and the collision the film lead must resolve

`docs/demo/cr-gate-route-plan.md` §R9 names these blocks **B9, B10, B11**, and this file obeys it.
`docs/demo/film-recut-plan.md` §4 independently drafts **two** blocks called `b9` and `b10` covering
the same 24 s of the same material. **Two plans, two id schemes, one stretch of film.** Recorded
here rather than left for `BEATS.yaml` to discover: if the film lead adopts the two-block shape,
this file's B9 and B10 fold together and B11 keeps the mirror; if the lead adopts three, the recut
plan's `b9`/`b10` ids are the ones that move. **Nothing before B9 renumbers under either choice**,
which is the property both plans actually require.

---

## 1 · THE SCRIPT

### B9 · THE OTHER WAY IN — `[2:04]` · 10 s · **17 w** · **1.70 w/s**

> "Then change the rule instead." ·hold 0.3· "Same paragraph. Same incident behind it. This
> request asks to edit it."

**This block exists to say the judge's own objection out loud before the judge has to.** The film
has spent two minutes proving a clause under blame cannot be *used*. The obvious next thought —
*fine, so couldn't somebody just rewrite the rule?* — is currently invited and never answered. The
seeded world has answered it since the day it was seeded and nothing has ever surfaced it.

**"Then change the rule instead" is spoken as the objection, not as an instruction.** It is the
sentence a sceptical viewer is already forming. Say it in their voice — flat, slightly impatient —
and then answer it.

**"Same paragraph. Same incident behind it." is the whole axis-one claim and it is two fragments
long.** `film-recut-plan.md` R-5 requires the shared clause and the shared precursor `DEMO-INC-0001`
to be **legible in frame** at this moment, with the same identifiers a judge already read in B3. The
VO does not read the identifiers aloud — it says *same*, and the frame proves *same*. If those two
identifiers are not in frame, R-5 says this whole wave should be abandoned rather than shot, and
these two fragments are the sentence that would be lying.

**"This request asks to edit it" — present tense, and it is a row's content, not a retrieval.**
`mainline.change_request` carries a standing proposal; describing what a row proposes is not
narrating a lookup, and A5's tense rule is about the recall. The recall is still spoken of in the
past tense everywhere in this film. **MUST NOT SAY:** *"the rewritten clause"* — nothing has been
rewritten; somebody has proposed to.

**On screen:** the operator app's **Management of change** screen for `DEMO-MOC-0001` on the
deployed origin — `state checks_materialised`, `counters.open_blocking` from the live read, the
clause of record rendered verbatim with its `SYNTHETIC —` prefix intact and its printed label, and
the clause identifier and `DEMO-INC-0001` both legible (R-5). The founder finishes typing the tail
of the proposed wording on camera, into the screen's own `Proposed wording` box, **carrying no
provenance chip** — the same convention B0 uses for the work description, and the reason a judge
can tell a human's proposal from a database claim in one look. Then the press. `CLICKS-CR.md` B9
has the cursor path.

**Delivery:** flat, and do not let the objection sound like a straw man. A viewer who has thought of
it and hears it dismissed stops believing the next twenty seconds. Say it as if it were a good
point, because it is one.

**The press lands under the last sentence, exactly as B1's does.** *"This request asks to edit it"*
is five words and covers the round trip; if the trip runs long the ·hold absorbs it and B10 starts
late; if it runs short, B10 starts on time and the answer is already there. **The founder says
nothing about how long it took** — the screen's own elapsed labels do that, and they are labelled
whose clock they are.

---

### B10 · REFUSED AGAIN — `[2:14]` · 6 s · **9 w** · **1.50 w/s**

> "Refused. **23514** again — a different CHECK, guarding the change."

**"Again" is the whole word.** A judge who heard `23514` at B2 hears the same SQLSTATE from a
different table, over a different subject kind, refusing a different act. That is the mirror
arriving as a fact before B11 says it as a sentence.

**"A different CHECK" is a claim a judge can check in the frame, and it must be true in the frame.**
The permit's refusal named `gate_closed_when_issued`; this one names `cr_gate_closed_when_merged` —
a different constraint, on a different table, with its own predicate. Both are on screen at the
moment the word *different* is said.

> **THE TRAP THIS BLOCK EXISTS TO NOT FALL INTO, WRITTEN OUT BECAUSE IT IS ONE CHARACTER WIDE.**
> `cr_gate_closed_when_merged` is the **CHECK**
> (`verticals/mainline/db/migrations/0051_change_request.sql:85`).
> `cr_merge_gate` is the **TRIGGER**
> (`verticals/mainline/db/migrations/0131_trg_cr_merge_gate.sql:38`).
> `mainline.fn_cr_merge_gate` is the trigger's **function**
> (`verticals/mainline/db/migrations/0116_fn_cr_merge_gate.sql`),
> and it is what a `P0001` names. They are three different objects. **Putting one where another
> belongs writes a claim the kernel does not make**, and it is the single most likely defect in
> this wave's on-screen text. `CLICKS-CR.md` §3 re-states it against the frame.

**The constraint name is NOT spoken here, and that is a decision with a price.** B2 already did the
*"named by the database"* move for the permit, and doing it twice costs about two seconds that B11
needs more. The name is on screen, in the payload's own field, for the whole block.

**Alternate line, only if the film lead pays 2 s out of the recut plan's 8 s bank** — B10 at 8 s:

> "Refused. **23514** again — a different CHECK, **cr_gate_closed_when_merged**, guarding the change
> itself." (**11 w** · 1.38 w/s)

**MUST NOT SAY:** *"the same constraint refused it"* — it is a different constraint and the frame
shows both names. **MUST NOT SAY:** *"the database refused the edit"* — what was refused is the
merge of the change request; the edit can still be made, by answering the obligation first, and
B11's scope word is what keeps that true.

**On screen:** the refusal band — the SQLSTATE, the constraint name, the constraint source, the
database's own predicate, and `open_blocking` beside it — every value read from the response that
just landed, with the four `cr_*` CHECK constraints the change-request read already returns. The
gate transcript panel beneath renders the beat's own `statement` and `label` verbatim.
`CLICKS-CR.md` B10 fixes the frame; §6 of this file fixes where every one of those values comes
from.

**Delivery: level, and shorter than it wants to be.** The lift belongs to B11 and there is only one
of those left in the film.

---

### B11 · THE MIRROR — `[2:20]` · 8 s · **12 w** · **1.50 w/s**

> "You can't use the clause." ·hold 0.4·
>
> **"You can't quietly edit it away either."**
>
> ·hold 1.3·

**This is the sentence the wave exists for and it is the one line here that can go wrong.**
`film-recut-plan.md` R-7 rules on exactly this failure and the ruling is adopted verbatim:

> **MUST NOT SAY:** *"the clause cannot be changed"* · *"the database won't let anyone edit the rule"* · *"the memory is immutable"* · *"you can't edit it."*

**The scope word `quietly` is doing all the work, and dropping it turns a true sentence into a false
one.** The clause **can** be edited — by disposing of the obligation first, which is exactly what
the three defeater questions on screen are for. Every variant that drops the adverb is filed as a
**REFUSE** row in `CLAIMS-CLEARANCE-CR.md` §4, which is the job R-7 assigns.

**If the adverb reads oddly on the day**, R-7's own sanctioned substitute is *"not without answering
the question first"* — and it **does not fit this window.** Counted the way §0.1 counts:

> **SUBSTITUTE A — 17 w.** "You can't use the clause. ·hold 0.4· You can't edit it away either —
> not without answering the question first."
>
> **17 w in 8 s is 2.13 w/s, which is over every rate ceiling in this kit.** It is shot at
> **11 s** — 1.55 w/s, 8.9 s of speech, the 0.4 hold inside and **1.7 s after the mirror**, which
> is the shape the line needs — and the 3 s comes out of `film-recut-plan.md` §2.1's 8 s bank.
> At 10 s it reads 1.70 w/s and the trailing hold collapses to 0.7 s; at 9 s there is no hold at
> all. **Stated rather than quietly met**, because meeting it at 8 s would break the ceiling.

> **SUBSTITUTE B — 11 w, and it fits the 8 s window as written.** "Use it, or edit it."
> ·hold 0.4· "Not without answering the question first."
>
> 1.38 w/s, 5.8 s of speech, **1.8 s after the mirror** — a wider hold than the primary's. It keeps
> both halves of the mirror, it carries the scope in a clause instead of an adverb, and it costs
> the bank nothing. **This is the substitute to reach for if the adverb has to go and the seconds
> are not there.**

Both are cleared, on the same terms as the primary, in `CLAIMS-CLEARANCE-CR.md` §2 rows 14 and 14b.

**The silence after the line is scripted. Do not fill it.** Same rule as B5, for the same reason: a
viewer who works out the mirror themselves is a viewer who believes it. This is the last spoken
second of the demo and the close card lifts into the hold, not over the line.

**The film has no admission to mirror B7 here, and it does not pretend to have one.**
`film-recut-plan.md` §2.3 COST 3 states the cost plainly and R-4 states the mitigation: the way
through is **shown** — the three live defeater prompts are on screen beside the refusal — and only
the walking through it is not. **MUST NOT SAY:** *"and there is no way through"* — there are three,
they are on screen, and each demands a citation.

**On screen:** the refusal still in frame, and beside it the three defeater prompts as the
disposition read returned them, verbatim, under the screen's own legend
*"Ways this obligation could be answered — each requires a citation"* — each a question, none of
them an escape hatch, and no *"not applicable"* option, because the vocabulary contains none. The
clearance lattice beside them. Shared clause and shared precursor still legible (R-5).

**Delivery:** drop the pace and the volume, once. Then stop.

---

## 2 · THE ARITHMETIC, AND WHAT EVERY SECOND OF SILENCE BUYS

| block | window | delivered | w/s over the window | speech at 1.9 w/s | silence | what the silence buys |
|---|---|---:|---:|---:|---:|---|
| B9 | 10 s | **17 w** | 1.70 | 8.9 s | 1.1 s | the 0.3 hold, and the last words cover the round trip |
| B10 | 6 s | **9 w** | 1.50 | 4.7 s | 1.3 s | pays for saying `23514` digit by digit (≈ 0.8 s) |
| B11 | 8 s | **12 w** | 1.50 | 6.3 s | 1.7 s | the 0.4 hold inside, then 1.3 s after the mirror |
| | **24 s** | **38 w** | **1.58** | **20.0 s** | **4.0 s** | |

The two right-hand columns are rounded to a tenth and the totals are the sums of the **unrounded**
values, which is why the columns add to 19.9 and 4.1 and the totals read 20.0 and 4.0 — the same
convention, for the same reason, as `VO-DEMO.md` §2's slack column.

**1.9 w/s is the speech rate `VO-DEMO.md` §2 measured across the delivered demo** (213 words ÷
112.1 s of speech). Every figure in the two right-hand columns is derived from it, not observed;
they are budgets and are labelled as budgets, per `film-recut-plan.md` §8 rule 8.

**B10's 1.3 s of silence is not 1.3 s of air.** `VO-DEMO.md` §0 prices a spoken SQLSTATE at about
two and a half words of time for one word on the page, so `23514` eats roughly 0.8 s of it and B10
lands with about half a second in hand. That is the whole reason the block is nine words and not
eleven.

**Why these blocks read slower than the demo's 1.78 w/s, stated rather than hidden.** Four things
in 24 seconds buy silence and every one of them is load-bearing: the proposed wording being typed
on camera (B9), a real round trip that must be spoken over and never cut away from (B9 into B10),
a SQLSTATE read digit by digit (B10), and a scripted hold after the mirror (B11). The close runs
at a deliberate 1.64 w/s for the same class of reason; 1.58 across three blocks carrying all four
is in family, not slack.

**The one second worth buying, if the film lead has it.** `film-recut-plan.md` §2.1 banks 8 s of
the 32 recovered. **The single best second in that bank is B11 going 8 s → 9 s**, which takes the
hold after the mirror from 1.3 s to 2.3 s — the duration `VO-DEMO.md` gives B5's hold, which is the
only other line in this film that is allowed to land in silence. Total becomes 173 s, still inside
the 174 s hard stop with 1 s of margin. **This is a recommendation to the film lead and not a
change to this file's budget**, which is 24 s.

**A block that cannot be written at or under 1.95 w/s is not written.** B10 at 6 s could carry 11
words on paper; it carries 9, because two of those words are a SQLSTATE and a beat that reads at
budget on paper and overruns in the mouth steals the second from the beat after it — and the beat
after B10 is the mirror.

---

## 3 · WHAT THESE THREE BLOCKS NEVER DO

Everything in `VO-DEMO.md` §3 still binds. These are the additional ones this material can
actually trip over.

* **Never speaks `blood_major`, and never speaks a severity for this obligation.** Both are on
  screen as column values. `film-recut-plan.md` §4.3 rules it and the reason is the one this
  repository has held to at every turn: saying an injury-shaped word aloud edges toward inventing a
  casualty to move an audience. B3 already spent the film's one spoken *severity four*, on the
  permit's obligation, where the seed-versus-projection pairing is on screen to check it against.
* **Never speaks a date, a site, a job title or an injury.** The seeded precursor describes nobody
  and `demo_world.sql`'s own narrative column says so. `B0b` set the frame with *"years ago"* and
  named no year; these blocks say *"same incident"* and name no more than B3 already did.
* **Never narrates the retrieval in the present tense.** **MUST NOT SAY:** *"watch it remember"* · *"the system just retrieved the incident and blocked the change."* The recall already ran; what is on screen is its record. The only present tense in this film is the re-derivation on a button press, which really executes.
* **Never speaks a timing, a byte count, a digest, a commit id or a uuid.** Not a millisecond, not
  a round trip, not a *"fast"*. `23514` is the **only** kernel-produced value spoken across all
  three blocks. Everything else is on screen with its own label, and §6 says where each comes from.
* **Never calls the second refusal the same constraint as the first**, and never puts the trigger's
  name where the CHECK's belongs. B10's boxed note is the whole rule.
* **Never claims defence in depth.** **MUST NOT SAY:** *"drop the constraint and the trigger still refuses"* — this wave proves one direction on one subject, and the unwelding matrix has never executed in CI.
* **Never says the word tamper-proof.** **MUST NOT SAY:** *"tamper-proof"* in any form — tamper-evident, never proofing, and split-view resistance is not claimed anywhere in this film.
* **Never dresses the second run's fourth beat up as a second peak.** The CR run's projection-drift
  beat is in the payload and on screen in the transcript panel; **it is not narrated.** Speaking a
  second `P0001` twenty seconds after B5 does not double B5, it halves it. `CLICKS-CR.md` B10 keeps
  it visible and unspoken, which is the same treatment B8 gives the beats it does not read out.
* **Never says the product's name inside the demo.** It is earned in the close, as it always was.

---

## 4 · WHAT THESE BLOCKS ASSUME OF WORK THIS WORKER DOES NOT OWN

Recorded, not asserted. **If any of these is not true on the day, the sentence that depends on it
is cut rather than kept**, and `CLICKS-CR.md` §5 carries the executable form of each.

1. **The attempt is reachable and it refuses. TODAY IT IS NOT, AND THAT IS MEASURED, NOT FEARED.**
   `POST /v1/demo/cr-gate-run` answered `404` at `cr_gate_run_probe.status` and
   `POST /v1/change-requests/{cr_id}/merge` is not declared either — three workers now, all
   independent: `cr-gate-route-plan.md` §0.2, `film-recut-plan.md` §1.3, and W5's own transcript at
   `evidence/deploy/cr-gate-live.json`, which closes on `verdict: "UNANSWERABLE"` and `exit_code: 2`
   for exactly this reason. **There is currently no way to attempt the edit and be refused**, which
   is the whole of what this wave builds. Without it, B9–B11 are not shot; `film-recut-plan.md` §6
   is the fully specified NO-GO and it is a legitimate outcome.
2. **The approve control on the Management-of-change screen drives that endpoint.** In the shipped
   bundle the control is hard-disabled and wired to nothing, deliberately and correctly
   (`verticals/mainline/apps/console/src/operator/change/absence.ts:408-454` renders the
   deployment's own 404 route table as its reason). B9's press does not exist until that changes.
3. **`GET /v1/change-requests/{cr_id}/blocking-checks` answers.** `cr_blocking_checks.status` reads
   `404` and `why_unanswerable.cr_blocking_checks_declared` reads `false` — the route is not merely
   unmeasured, it is not declared. The change screen's obligation panel probes it. **Anyone who
   opens that screen on camera right now films a panel rendering an absence**, which is honest and
   is not the shot these blocks are written for.
4. **R-5 holds in frame.** The shared clause identifier **and** the precursor are legible beside
   the change-request refusal. **Half of this is already secured and half is not.** The clause is:
   `subjects.body.data.clause_uuid` is the same identifier `B3` shows, measured (§6.2 M14). The
   precursor is not: the shipped obligation panel states in its own words that the obligation's
   precursor and severity *"are not reachable from any declared route"*, and the read that would
   carry them is the one that `404`s. **If R-5 does not hold, B9's *"Same incident behind it"* is
   cut**, and `film-recut-plan.md` R-5 says the wave should be abandoned rather than shot without
   it.
5. **The three defeater prompts are on screen through B11** (R-4). Without them, B11's mirror is a
   refusal with no way through beside it, which is the reading `film-recut-plan.md` §2.3 COST 3
   warns about. The block is still shot; the delivery note about *showing* the way through comes
   out, because nothing is showing it.
6. **`B8` is cut to 6 s.** §0.2's arithmetic. Without it the film is past the hard stop.
7. **The close lands at 22 s.** These 24 s are the seconds the naming close returns.

---

## 5 · THE SCOPE-CUT LADDER FOR THESE THREE BLOCKS

`film-recut-plan.md` §5 owns the film's ladder; this is only the part of it that reaches this file,
restated so nobody improvises at 02:00.

| # | cut | from → to | saves | the line after |
|---|---|---|---|---|
| **1** | **B9's typing** — arrive on the proposed wording already composed | 10 s → 8 s | 2 s | **11 w** · 1.38 w/s — *"Then change the rule instead. ·hold 0.3· Same paragraph. Same incident behind it."* The last sentence goes; the press moves under *"behind it"* and still covers the trip. |
| **2** | **B11's hold** | 8 s → 7 s | 1 s | unchanged words, **12 w** · 1.71 w/s, **0.3 s** after the mirror. **This is the last second to take and it should be the first one given back.** |

**RULING ADOPTED FROM `film-recut-plan.md` R-10 · USE CASE TWO IS ATOMIC.** **B9 may never be cut
without B11.** A setup with no answer is worse than neither: it spends ten seconds raising the
judge's question and never answers it. If the cut must go further than the two rows above, **drop
B9, B10 and B11 together — all 24 s — and restore `B8` to 10 s**, which is a net −20 s and leaves
the film as one clean use case rather than one and a half.

**B10 is never cut.** It is six seconds and it is the only place the second refusal exists.

**If the live origin is down on the day, none of this applies.** The film is not made against a
mock: it is postponed, or filmed against the local node and **said to be local, on screen**, which
the operator shell's own origin strip does in the page's own words. A staged refusal is a rules
violation under the contest's own Functionality requirement — the project must function as depicted
in the video — and not merely a dishonesty. If a `40001` retry appears, it is pressed again on
camera and the retry is not cut out.

---

## 6 · THE NUMBERS REGISTER — every value, and where it is re-derived from

**RULE, from `docs/demo/cr-gate-route-plan.md` §R10 and `film-recut-plan.md` §8 rule 6.** Every
SQLSTATE, constraint name, count and elapsed time in these three files is re-derived from
**`evidence/deploy/cr-gate-live.json`** — W5's transcript of the run that is actually filmed —
and from nothing else. Not from a plan, not from this brief, not from a memory.

**STATE, RE-DERIVED FROM THE FILE ITSELF, WHICH LANDED WHILE THIS WAS BEING WRITTEN.**
`evidence/deploy/cr-gate-live.json` now exists. It was read in full and it is **`phase: "baseline"`,
`verdict: "UNANSWERABLE"`, `exit_code: 2`, `failures: []`, with 14 of 14 assertions holding.**

> ## THE FILE IS A BASELINE, NOT THE RUN. **THERE IS NO CR REFUSAL TRANSCRIPT IN IT, BECAUSE THERE IS NOTHING DEPLOYED TO PRODUCE ONE.**

W5's own measurements, verbatim from the file:

```
GET  /v1/demo/subjects                              200   subjects.status
GET  /v1/change-requests/{cr_id}                    200   cr_read.status          3,295 B
GET  /v1/change-requests/{cr_id}/blocking-checks    404   cr_blocking_checks.status
POST /v1/demo/cr-gate-run                           404   cr_gate_run_probe.status
                                                          why_unanswerable.declared_path_count = 17
                                                          why_unanswerable.cr_blocking_checks_declared = false
```

and the file's own sentence for what that means, at
`why_unanswerable.this_is_not_a_gate_that_failed_to_refuse`: **a route that has not been deployed is
not a refusal that did not happen**, and exit code 2 keeps the two findings apart.

**So B10's spoken value is still `PENDING`, and it stays `PENDING` until a run exists.** What
changed is that the field paths below are no longer written against an assumed shape — they are
written against a file that is on disk and was read.

### 6.1 · ⛔ THE TRAP IN THIS FILE, AND IT IS THE MOST DANGEROUS ONE IN THE WAVE

`evidence/deploy/cr-gate-live.json` **does** contain a `gate_run_summary` block, and it **does**
contain a `23514`. It is the **PERMIT'S** run:

```
gate_run_summary.merge.sqlstate                  = "23514"
gate_run_summary.merge.constraint                = "gate_closed_when_issued"
gate_run_summary.projection_drift_attack.constraint = "mainline.fn_permit_merge_gate"
gate_run_summary.beat_names                      = ["read","merge","projection_drift_attack","admit"]
```

**Every one of those is `B2`'s and `B5`'s, from `POST /v1/demo/gate-run`, on the permit.** It is in
this file as the control that proves the origin was healthy while the CR probes were 404ing — and
it is **not** the change request's refusal.

> **A worker who reads B10's number out of `gate_run_summary.merge.sqlstate` puts the PERMIT's
> refusal on screen labelled as the CHANGE REQUEST's.** That is the exact fabrication class this
> repository refuses, it would pass every scanner in the kit, and it is one field name away from
> being done by accident at 02:00.

**B10's value comes from the CR run's own merge beat and from nothing else.** Until that run
exists, there is no value.

### 6.2 · MEASURED — values now sourced, with the field path each was read from

Every row here was read from `evidence/deploy/cr-gate-live.json` this session. None is spoken; all
are on screen, per §3.

| # | value | measured | field path |
|---|---|---|---|
| M1 | external ref | `DEMO-MOC-0001` | `cr_read.body.data.external_ref` |
| M2 | state | `checks_materialised` | `cr_read.body.data.state` |
| M3 | the projected counter | `1` | `cr_read.body.data.counters.open_blocking` |
| M4 | the other two counters | `0`, `0` | `cr_read.body.data.counters.open_conflicts`, `.open_residue` |
| M5 | `head_seq`, `gate_epoch` | `1`, `1` | `cr_read.body.data.head_seq`, `.gate_epoch` |
| M6 | `merged_commit` | `null` — the screen renders it as `null — never merged`, which is the page's own string | `cr_read.body.data.merged_commit` |
| M7 | the branch line | `refs/changes/demo-0001  →  refs/heads/main` | `cr_read.body.data.ref_name`, `.target_ref` |
| M8 | **the CHECK's name** | `cr_gate_closed_when_merged` | `cr_read.body.data.constraints[0].constraint` |
| M9 | **its predicate, verbatim** | `CHECK (((state != 'merged'::mainline.subject_state) OR (open_blocking = 0)))` | `cr_read.body.data.constraints[0].predicate` |
| M10 | the counter that CHECK reads | `open_blocking = 1` | `cr_read.body.data.constraints[0].counters[0]` |
| M11 | the other three `cr_*` CHECKs | `cr_merge_evidence`, `cr_conflicts_resolved_when_merged`, `cr_identity_conserved_when_merged`, each with its own predicate | `cr_read_constraints`, `cr_read.body.data.constraints[1..3]` |
| M12 | `blamed_by_refusal` | **`false` on all four** | `cr_read.body.data.constraints[*].blamed_by_refusal` |
| M13 | where the predicates come from | `pg_catalog.pg_constraint`, read at request time | `cr_read.body.statement_refs[1]` |
| M14 | **the shared clause identifier** | the addressing's `clause_uuid` — **and it is the same identifier `B3` shows** | `subjects.body.data.clause_uuid` |
| M15 | the precursor's identifier | the addressing's `lesson_id` | `subjects.body.data.lesson_id` |

**M12 is worth putting on screen and it is worth not over-reading.** `blamed_by_refusal` reads
`false` on all four constraints today because **no attempt has been made**, so no refusal has named
one. It turns true when a refusal blames it. **That field is the cleanest single proof on the
screen that nothing here is pre-baked** — and **MUST NOT SAY** anything about it aloud; it is a
column, it is in frame, and a judge who notices it has found it themselves.

**M9's predicate is the grounds of the refusal, and the grounds are already public.** The
change-request read returns the CHECK, its predicate and the live counter it reads, today, at
`200`. **Only the attempt is missing.** That is what this wave builds and it is the whole of what
it builds.

### 6.3 · PENDING — no run exists, so no value exists

Each row names the beat it will be read from. **`cr-gate-live.json` has no `beats` block at all
today**, which is why every one of these is `PENDING` rather than sourced.

| # | value | block | where it will come from |
|---|---|---|---|
| S1 | **the SQLSTATE — the one value spoken** | **B10** | the CR run's merge beat, **never `gate_run_summary`** (§6.1) |
| P1 | the CHECK's name **as the refusal reports it** | B10, B11 | the same beat's `constraint`, cross-read against M8 |
| P2 | `constraint_source` | B10 | the same beat's refusal. **If it reads `parsed` rather than `reported`, the on-screen label says `parsed`.** A weaker diagnosis stays on screen; `B5` set that precedent and it is why the film is believed. |
| P3 | the refusal's own message | B10, B11 | the same beat |
| P4 | the re-derived open count beside the projected one | B10 | the run's read beat |
| P5 | the projection-drift beat's SQLSTATE and message — **on screen, never narrated** | B10 | that beat. **It will name `mainline.fn_cr_merge_gate`, not `mainline.fn_permit_merge_gate`** — §6.1 again. |
| P6 | the kernel-procedure beat, **if it was shipped at all** | B10 | `cr-gate-route-plan.md` §R3 makes it conditional and drops it if the deployed cluster answers a privilege error rather than a gate refusal. **A privilege error is not a gate refusal and is never presented as one.** |
| P7 | `verdict` | B10 | the run |
| P8 | `persisted`, `self_persisted`, `isolation`, `single_transaction`, the two logical timestamps | B11 tail | the run |
| P9 | per-beat elapsed | B9, B10 | the run — **on screen with its label, never in a sentence** |
| P10 | the obligation's severity, origin and virulence | B9, B11 | the CR blocking-checks read. **`cr_blocking_checks_declared` reads `false` today**, so this is not merely unmeasured — the route does not exist. |
| P11 | the three defeater prompts and the clearance lattice | B11 | the disposition read. **It is not in `cr-gate-live.json` today** — W5 recorded the CR path and the route table, not that read. |
| P12 | the clause's printed label and its canonical text | B9 | the clause-version read. **Also not in `cr-gate-live.json` today.** |

**A row that is still `PENDING` on the day the film is cut is a row whose value does not go on
camera**, and a block whose only spoken value is `PENDING` is a block that is not shot. That is
condition 1 in §4 and it is not a formality.

### 6.4 · Two object identities that are NOT run values, and are cited to the tree

These are not numbers from a run; they are what the objects are called in the repository, read from
the tree this session, and they are the authority for B10's boxed note:

| object | kind | authority |
|---|---|---|
| `cr_gate_closed_when_merged` | **CHECK** on `mainline.change_request` | `verticals/mainline/db/migrations/0051_change_request.sql:85` |
| `cr_merge_gate` | **TRIGGER**, `BEFORE UPDATE`, `WHEN ((NEW).state = 'merged' AND (OLD).state <> 'merged')` | `verticals/mainline/db/migrations/0131_trg_cr_merge_gate.sql:38-41` |
| `mainline.fn_cr_merge_gate` | the trigger's **function**, and what a `P0001` names | `verticals/mainline/db/migrations/0116_fn_cr_merge_gate.sql` |

**What goes on camera is still what the kernel reported on the filmed run.** These three rows exist
so that a mismatch between the tree and the run is caught before the take rather than after it.

---

## 7 · DISSENT, RECORDED AND NOT ACTED ON

**One, and it is about a second I did not spend.** `film-recut-plan.md` R-4 and §2.3 COST 3 both
worry that use case two ends on a refusal with no admission to mirror B7, and that a judge could
read it as *"the system just says no."* I think the mitigation — the three defeater prompts on
screen — is right and sufficient, **and I considered spending two seconds of the bank on a spoken
sentence naming them**, something like *"three questions, each demanding a citation."* I did not
write it, for a reason worth recording rather than leaving as a gap: B6 already spoke that sentence
about the permit's defeaters, in the film's warmest beat, and saying it again twenty seconds later
would trade B11's silence for a repetition. **The silence after the mirror is worth more than a
second explanation of a screen the judge is looking at.** If the film lead disagrees, the two
seconds exist in the bank and the sentence is cleared as a variant in `CLAIMS-CLEARANCE-CR.md` §4.

**Nothing else.** Every ruling that reached this file — R-2, R-4, R-5, R-7, R-10 from the recut
plan, R3, R9 and R10 from the cr-gate route plan — made these blocks shorter and easier to defend.
