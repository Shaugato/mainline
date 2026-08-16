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

# VO-DEMO-CR.md — the companion sheet for use case two's TWO spoken blocks

**Worker W6** · the film blocks for use case two · cr-gate-route wave · 2026-08-16 ·
**reconciled to the two-block decomposition 2026-08-16**
**Binding plan:** `docs/demo/cr-gate-route-plan.md` §R9 (this file's existence, its budget and its
register), and §R3 / §R10 for what the run is allowed to claim. **Its three-block id scheme is
superseded** — see §0.3.
**Read in full before a line was written:** `docs/demo/film/VO-DEMO.md` (format and register),
`docs/demo/film/SPINE.md` §0 (word counting) and §4 (per-beat prohibitions),
`docs/demo/film-recut-plan.md` §§2, 4, 5 (the seconds these blocks are spending and R-5, R-7, R-10),
`docs/demo/research/r6-honesty.md` A13.5, `docs/submission/MUST-NOT-CLAIM.md`.

**No commit id is written here.** `claim_hygiene.py`'s `HYG-sha-literal` rule refuses one and it is
right to: a commit id cannot be chosen in advance.

**Clearance:** every sentence below is cleared line by line in
[`CLAIMS-CLEARANCE-CR.md`](CLAIMS-CLEARANCE-CR.md), which also carries this wave's
`claim_hygiene.py --check` transcript and its exit code. Screen actions are in
[`CLICKS.md`](CLICKS.md) §5 `B9`/`B10`; [`CLICKS-CR.md`](CLICKS-CR.md) is the companion pre-flight,
frame-rule and field-path sheet for the same two blocks.

> ### THIS FILE DOES NOT OWN THE WORDS, AND THAT IS THE FIX FOR THE DEFECT IT SHIPPED WITH
>
> **`VO-DEMO.md` §1 is the spoken script of record for `B0`…`B10`.** The lines printed in §1 below
> are **inherited from it, verbatim**, so that the two documents cannot drift word by word the way
> they drifted block by block. **If this file and `VO-DEMO.md` ever disagree about a spoken word,
> `VO-DEMO.md` wins and this file is wrong** — the same precedence `BEATS.yaml` has over both of
> them for timing, applied to the mouth instead of the clock.
>
> **What this file does own, and what it is worth keeping for:** the numbers register in §6 (every
> on-screen value bound to the field path it is re-derived from), the three-object trap in §1's
> boxed note and §6.4, the extra prohibitions in §3, the assumptions in §4 that must hold on the
> day, and the sanctioned alternates — each priced, each cleared, none of them a second primary.

**Delivered: 40 spoken words over 24 s = 1.67 w/s across the two blocks**, inherited from
`VO-DEMO.md` §2. No block exceeds 1.70 w/s. §2 prices every second of the silence.

**THIS FILE RENUMBERS NOTHING.** `B0`…`B8` keep their ids, their durations and their words. The
film lead splices **two** blocks after `B8` and `BEATS.yaml` remains the timing authority
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
the mouth, because it is read digit by digit — *two three five one four*. That is why `B10` is
written well under the ceiling; §2 prices it.

`cr_gate_closed_when_merged` is one word on the page and roughly three words of time in the mouth.
It is **not spoken in the primary read** — it is on screen — and §1's `B10` note says why, with the
alternate line that speaks it if the film lead pays the second.

### 0.2 · The in-points are DERIVED, and R9's `[2:00]` is a pre-`B0b` figure

`docs/demo/cr-gate-route-plan.md` §R9 sites these blocks "after `B8 · NONE OF IT PERSISTED` at
`[2:00]`". **`[2:00]` was true before `B0b` existed.** `VO-DEMO.md` was edited on 2026-08-16 at
09:37 to insert `B0b · WHY IT MATTERS`, 8 s at `[0:12]`, and every timecode after it moved by 8 s
without any file being told. `film-recut-plan.md` §1.1 measures the same thing independently.

Arithmetic, from `BEATS.yaml`'s own durations, which include `film-recut-plan.md` §2.1's `b8 10 → 6`:

```
B0 12 + B0b 8 + B1 10 + B2 14 + B3 18 + B4 10 + B5 16 + B6 18 + B7 12 + B8 6   = 124 s  → B9  at 2:04
B9 12                                                                          = 136 s  → B10 at 2:16
B10 12                                                                         = 148 s  → close at 2:28
close 22 + end card 2                                                          = 172 s  = 2:52
```

**172 s is exactly `film-recut-plan.md` §2.1's target** — `172 ≤ 172` target, `< 174` hard stop,
`< 180` ceiling. These two blocks cost **24 s**, which is the middle of R9's `22–26 s` band and
the exact figure the recut budget reserved. **The 24 s did not change when the decomposition did**
— that is the property that made the collision survivable and it is why nothing downstream moved.

**A consequence worth stating rather than discovering.** If `B8` is **not** cut to 6 s, the film
runs `128 + 24 + 22 + 2 = 176 s`, which is **past the 174 s hard stop.** These blocks and the `B8`
re-time are one decision, not two.

The candidate in-point sets, so nobody has to redo this at 02:00:

| assumption | B9 | B10 |
|---|---|---|
| `B0b` present, `B8` = 6 s — **the spine of record** | `[2:04]` | `[2:16]` |
| `B0b` present, `B8` = 10 s (over the hard stop) | `[2:08]` | `[2:20]` |
| pre-`B0b` spine, `B8` = 10 s — R9's `[2:00]` | `[2:00]` | `[2:12]` |

**Neither the durations nor the in-points are this file's any more.** `BEATS.yaml` is the authority
for both and §0.3 is why.

### 0.3 · ⚖ THE BLOCK COLLISION — **RESOLVED, in favour of TWO blocks**

**The defect, stated before the ruling.** `docs/demo/cr-gate-route-plan.md` §R9 named **three**
blocks — `B9` 10 s + `B10` 6 s + `B11` 8 s — and this file and `CLICKS-CR.md` obeyed it.
`docs/demo/film-recut-plan.md` §4 independently drafted **two** — `b9` 12 s + `b10` 12 s — and
`BEATS.yaml`, `VO-DEMO.md`, `CLICKS.md`, `ONSCREEN-TEXT.yaml`, `FALLBACKS.md` and `SPINE.md`
encoded that. Both shapes total 24 s, so **2:52 held either way** and the arithmetic never caught
it. **What it broke is the recording session.** The founder records **voice first, then picture,
then matches them**, so a block boundary is a place he stops, breathes and starts again — and two
documents describing different numbers of stops is a session he cannot run. The earlier text of
this section left the choice open. **Leaving it open was the defect; this is the ruling.**

> ## **RULING · TWO BLOCKS. `B9` = 12 s at `[2:04]`, `B10` = 12 s at `[2:16]`.**
> **`B11` does not exist.** This file's former `B9` becomes `B9`; its former `B10` and `B11`
> become the two halves of one `B10`, which is the shape `BEATS.yaml` already encodes.

**The three reasons, in the order they decided it. The first is a measurement and it is the one
that actually settles it.**

1. **`B9` at 10 s is under-budget against something already measured, and the measurement is not
   this worker's.** `CLICKS.md` M14 timed the change screen's read chain **twice against the live
   origin**: four sequential awaited `GET`s, **≈ 3.5 s warm and ≈ 6 s cold**, painting the page in
   four visible stages. `CLICKS.md` §5 also measured that the `moc-proposed-text` textarea is
   **destroyed and re-created empty when the screen mounts**, so the proposed wording **cannot be
   pre-typed** — it is typed on camera or it is not on screen at all. `B9` must therefore hold: the
   module switch, ≈ 3.5 s of read chain nobody may cut away from, a scroll to the clause, and the
   typing. `CLICKS.md`'s own choreography spends all twelve seconds on exactly that — travel and
   module switch `2:04.0–2:05.5`, the four-read paint `2:05.5–2:09.0`, the scroll `2:09.0–2:10.5`,
   the click into the box `2:10.5–2:11.0`, the typing `2:11.0–2:13.5`, the travel to `Approve
   change` `2:13.5–2:14.0`, **Click 6 at `2:14.0`** and the request in flight to `2:15.5`
   (`shoot-docs-plan.md` `R-SD4`, §1's ruling box below) — and its `B8` note says in terms that
   *"B9's read chain needs every one of its own 12 seconds (M14)."* **Ten does not fit**, and the
   same measurement is what voids the cut ladder's rank-1 saving on `b9`. A decomposition that
   starts by over-running its first block is not a decomposition, whatever it totals.
2. **The three-block shape's own sanctioned substitute does not fit its own window, and this file
   said so before the ruling existed.** §1's `SUBSTITUTE A` is **17 w in an 8 s block = 2.13 w/s**,
   over every rate ceiling in the kit, and this file priced it at **11 s** — three seconds that do
   not exist. A block that cannot hold its own cleared alternate is the more fragile of the two
   shapes, and fragility is what a re-take ladder is supposed to remove.
3. **Voice-first costs a join at every boundary, and the last 24 s is where a join is most
   expensive.** The honest case *for* three blocks is real and is recorded rather than waved away:
   **shorter blocks are easier to re-take**, and a fluffed 6 s block costs 6 s to redo instead of
   12. Against that: every boundary is a **sync point matched by hand afterwards**, and the
   three-block shape puts one of those between the refusal sentence and the mirror — which is
   precisely where the `·hold·` lives, and a hold whose two sides come from two takes is a hold
   that will not sound like a hold. **The two-block shape keeps the refusal and the mirror in one
   recorded breath and pays for it with a longer re-take.** The film's last spoken line and its
   scripted silence are worth more than the retake margin, and there is no margin after `B10`
   anyway: the close begins.

**And one reason that is not a merit and is recorded as not being one.** Two blocks is also the
cheaper edit — five documents already carry it against two that do not. **That is not why**; if the
measurement in reason 1 had gone the other way the five would have moved. It is recorded so nobody
later reads convenience into the ruling.

**Nothing before `B9` renumbers**, which was the one property both plans required and the only
reason this collision was recoverable at all.

---

## 1 · THE SCRIPT — TWO BLOCKS, AND THE WORDS ARE `VO-DEMO.md`'s

**Every line printed in this section is inherited verbatim from `VO-DEMO.md` §1.** It is reprinted
here so this sheet can be read on its own at 02:00, **not** so it can be edited here. A word
changed below and not there is a defect of exactly the kind §0.3 exists to close.

### B9 · THE OTHER WAY IN — `[2:04]` · 12 s · **20 w** · **1.67 w/s**

> "Fine. Then don't use the clause — change it. ·hold 0.4· Same paragraph. Same incident behind
> it. This request asks to edit it."

**This block exists to say the judge's own objection out loud before the judge has to.** The film
has spent two minutes proving a clause under blame cannot be *used*. The obvious next thought —
*fine, so couldn't somebody just rewrite the rule?* — is currently invited and never answered. The
seeded world has answered it since the day it was seeded and nothing has ever surfaced it.

**"Fine." is spoken as the objection, not as an instruction.** It is the sentence a sceptical
viewer is already forming. Say it in their voice — flat, slightly impatient — and then answer it.

> **SANCTIONED ALTERNATE, four words shorter, cleared at `CLAIMS-CLEARANCE.md` `N2` and at
> `CLAIMS-CLEARANCE-CR.md` row 1** — *"Then change the rule instead."* in place of *"Fine. Then
> don't use the clause — change it."* It is this file's original opener and the clearance sheet's
> own words are *"the same objection, four words shorter; both forms are cleared, the film lead
> picks one."* **It is an alternate and not a second primary:** taking it takes `B9` to 17 w /
> 12 s = 1.42 w/s, which is more air, not less time.

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
can tell a human's proposal from a database claim in one look. **`CLICKS.md` §5 `B9` is the cursor
path of record**; `CLICKS-CR.md` §4 is its pre-flight and field-path companion.

**Delivery:** flat, and do not let the objection sound like a straw man. A viewer who has thought of
it and hears it dismissed stops believing the next twenty seconds. Say it as if it were a good
point, because it is one.

> ### ✔ **RULED, 2026-08-16 — THE PRESS LANDS AT `2:14.0`, UNDER THIS BLOCK'S LAST SENTENCE.** No word moves
>
> **`docs/demo/shoot-docs-plan.md` `R-SD4` closed the open item this box used to carry, and it
> closed it in favour of candidate (a).** Click 6 — `Approve change` — is at **`2:14.0`**, `+10.0`
> into `b9`. The request is in flight `2:14.0 → 2:15.5`, so the tail of *"This request asks to edit
> it."* runs over the flight and R-9 is satisfied. **The refusal paints at `2:15.5`**, and `B10`
> opens at `2:16.0` on a refusal already on screen, so *"Refused."* names a value the viewer can
> see and R-K is satisfied with 0.5 s to spare. **`CLICKS.md`'s `2:17` is struck** — it put the
> value on screen 2.5 s *after* the word, which R-K does not permit at any price. **This file's
> literal `+7.4` is struck too**: it was scored against the retired 10 s `B9` and in the 12 s block
> lands at `2:11.4`, in the middle of the typing. The placement survived; neither number did.
>
> **What it costs is picture, not words, and that is the whole reason it was chosen.** `B9`'s
> typing window falls 5.0 s → 2.5 s and its 1.1 s of settle slack (§2, from `VO-DEMO.md` §2:595) is
> re-purposed to the answer landing. **No spoken word, no word count, no `w/s` figure and no beat
> duration changes anywhere in this file for it.** `CLICKS-CR.md` §4.2 and §5.6 carry the picture
> half, including the stopwatch check that the proposed wording types legibly in 2.5 s.
>
> #### **WHY CANDIDATE (b) WAS REJECTED — it is not expensive, it is unaffordable**
>
> Candidate (b) was *"start `B10`'s line ≈ 2.5 s after its in-point"*. **`VO-DEMO.md` §2's own beat
> table, line 596, measures `B10`'s slack at 1.5 s** — and that 1.5 s is already spent twice over:
> **0.6 s is the mirror hold** and **≈ 0.5 s pays for the spoken word `SQLSTATE`** (§0.1, §2),
> leaving **0.4 s free**. A 2.5 s slip therefore needs **2.1 s that does not exist**, and it can
> only take them from the hold or from the words:
>
> * **The hold is protected.** `SPINE.md` §4 makes the scripted silence an element with a duration,
>   not a pause an editor may tighten, and §1.1's whole argument is that the mirror is heard in it.
> * **The words are protected, and the arithmetic is the flat refusal.** 20 w in the remaining
>   ≈ 9.5 s is **2.11 w/s**, against `BEATS.yaml:175`'s **1.95** kit ceiling and its 1.9
>   `wps_assumption` (`BEATS.yaml:142`). **§2's closing rule — a block that cannot be written at or
>   under 1.95 w/s is not written — retires (b) exactly as it retired the three-block `B9` and
>   `SUBSTITUTE A`.**
>
> **That is why this box now records a ruling and not a choice.** Candidate (b) does not cost a
> second somebody can find; it costs a second nobody has.
>
> #### **`R-SD4a` — the fallback is floored at 0.4 s, and the 0.4 s cannot be spent twice**
>
> If rehearsal shows that **no honest proposal string types legibly in 2.5 s**, even after the
> string is shortened and the 0.5 s of app-bar travel is reclaimed, `B10`'s first word may slip by
> **at most 0.4 s** — the measured free slack above — putting Click 6 at `2:14.4` and the typing at
> 2.9 s. **0.4 s is a floor, not a preference:** past it the hold or the `SQLSTATE` pays, and both
> are protected.
>
> **And spending it here forecloses `CLAIMS-CLEARANCE.md` `D31`.** That row is the still-open
> `~ REWORD` of `B10`'s *"guards **edits**"* to *"guards the change"* — the more precise naming of
> the object the CHECK refuses, which is the merge — and **`VO-DEMO.md`'s head note prices it at
> 21 words running 1.13 s against 0.95 s of slack**, i.e. it lands only by eating the same free
> tenths. **The 0.4 s buys the press or it buys `D31`. It does not buy both.** The film lead states
> which before the take. **This sheet still does not discharge `D31`** — it is W2's row in W2's
> file — and recording the collision is not the same as resolving it.
>
> #### **`R-SD4b` — all of the above is conditional, and says so**
>
> **`b9` and `b10` are NO-GO on the deployed origin today** and §4's conditions 1–4 are the
> measured reasons: `POST /v1/demo/cr-gate-run` `404`, `GET …/blocking-checks` `404` and **not
> declared**, the approve control hard-disabled and wired to nothing, and `DEMO-INC-0001` occurring
> **zero** times on the change screen, so R-5 is unsatisfied. **`FALLBACKS.md` §4.2's `R-11` gate
> decides it, not this ruling.** On the no-go path there is no Click 6 at all, these two blocks are
> never added, `b8` returns to 10 s and the film is 152 s. A press timed to a tenth in a block that
> is not shot would be a second document describing a film that does not exist.

---

### B10 · REFUSED AGAIN — THE MIRROR — `[2:16]` · 12 s · **20 w** · **1.67 w/s**

> "Refused. Same **SQLSTATE** — a different constraint guards edits. ·hold 0.6· You can't
> **just** use the clause. You can't **quietly** edit it away."

**This one block carries what the three-block shape split across two.** Its first sentence is the
second refusal; its last two are the mirror. §0.3 rules that they belong in one recorded breath,
and the `·hold 0.6·` between them is the seam that a block boundary would have turned into a join.

**"Same" is the whole word, and "again" is its alternate's.** A judge who heard `23514` at B2 hears
the same SQLSTATE from a different table, over a different subject kind, refusing a different act.
**That is the mirror arriving as a fact before §1.1 says it as a sentence** — which is the strongest
argument for the two of them being one block: the fact and the sentence are six seconds apart, and
a boundary between them is a boundary through the middle of one idea.

**"A different constraint" is a claim a judge can check in the frame, and it must be true in the
frame.** The word *constraint* is used and the word *gate* is not: `B5`'s refusal is a procedural
guard MAINLINE wrote, this one is a declarative CHECK the database enforces, and the distinction
`B5` protects is protected here by using the other word. The alternate below says **CHECK** for the
same reason. **MUST NOT SAY:** *"the same constraint"* — it is a different one, and that is the
point.

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
*"named by the database"* move for the permit, and doing it twice costs about two seconds the
mirror needs more. The name is on screen, in the payload's own field, for the whole block.

**One word IS spoken that the three-block draft did not speak: `SQLSTATE` itself.** `VO-DEMO.md` §0
prices it at roughly two words of mouth-time for one word on the page and §2 buys the ≈ 0.5 s out
of `B10`'s slack. It is said while `23514` is on screen, which is the value it names (R-K).

> **SANCTIONED ALTERNATE for this sentence, cleared at `CLAIMS-CLEARANCE.md` `N7`/`N8` and at
> `CLAIMS-CLEARANCE-CR.md` rows 8–11** — *"Refused. **23514** again — a different CHECK,
> guarding the change."* (9 w), and the +2 s form that also speaks
> **`cr_gate_closed_when_merged`** (11 w). **They name the constraint's object more precisely than
> the line of record does**, which is the substance of `CLAIMS-CLEARANCE.md`'s open `~ REWORD`
> `D31` against `VO-DEMO.md`'s *"guards edits"*. **`D31` is not discharged here and this sheet does
> not discharge it by preferring its own wording** — that would put two live primaries back in the
> film, which is the defect §0.3 just closed. It is W2's row, in W2's file, and when it lands these
> two documents converge further rather than diverging.

**MUST NOT SAY:** *"the same constraint refused it"* — it is a different constraint and the frame
shows both names. **MUST NOT SAY:** *"the database refused the edit"* — what was refused is the
merge of the change request; the edit can still be made, by answering the obligation first, and the
mirror's scope words are what keep that true.

**On screen for the first sentence:** the refusal band — the SQLSTATE, the constraint name, the
constraint source, the database's own predicate, and `open_blocking` beside it — every value read
from the response that just landed, with the four `cr_*` CHECK constraints the change-request read
already returns. The gate transcript panel beneath renders the beat's own `statement` and `label`
verbatim. `CLICKS.md` §5 `B10` fixes the frame; §6 of this file fixes where every one of those
values comes from.

#### 1.1 · THE MIRROR — the second half of `B10`, and the one line here that can go wrong

> "You can't **just** use the clause. You can't **quietly** edit it away." ·hold, to the close·

**`film-recut-plan.md` R-7 rules on exactly this failure and the ruling is adopted whole**, with
the fifth bar this file's first draft dropped:

> **MUST NOT SAY:** *"the clause cannot be changed"* · *"the database won't let anyone edit the rule"* · *"the memory is immutable"* · *"you can't edit it"* · **and *"you can't use the clause"* with no scope word.**

##### 1.1.1 · ⚠ THE FIFTH BAR — the one this file itself broke, and the correction

**Before, and it was this block's PRIMARY line:**

> ~~"You can't use the clause." ·hold 0.4· "You can't quietly edit it away either."~~

**After, and it is `VO-DEMO.md` B10's, cleared at `CLAIMS-CLEARANCE.md` `D32` and `D33`:**

> **"You can't just use the clause. You can't quietly edit it away."**

**What was wrong with the old first half, and it is not a matter of taste.** This file transcribed
R-7's bar list as **four** items and **dropped the fifth — the one its own primary line violated.**
**`B7` shows the permit ISSUED on that same clause thirty seconds earlier**, once its obligation
was properly answered, and the film shows it happening rather than asserting it. So the unscoped
sentence is **contradicted by this film, inside this film**, and a judge who noticed would conclude
the narration does not match the product — which is a worse finding than the sentence it came from.
`CLAIMS-CLEARANCE.md` `D32` records the same reasoning and clears the scoped form as an
improvement: *"`just` gives the first half the same scope discipline `quietly` gives the second."*

**Both halves now carry a scope word and neither is decoration.** *Just*: the clause **is** usable —
the audience watched it become usable — but not without the obligation being answered. *Quietly*:
the clause **can** be edited, by disposing of the obligation first, which is exactly what the three
defeater questions on screen are for. **The two scopes point at one fact: the question comes first,
whichever way you come at the clause.** Every variant that drops either is filed as a **REFUSE** row
in `CLAIMS-CLEARANCE.md` §12.4 and `CLAIMS-CLEARANCE-CR.md` §4, which is the job R-7 assigns.

**`either` came out and its loss is priced rather than waved through.** It made the tie between the
two sentences explicit; the parallel *"You can't … You can't …"* carries it, and `D33` clears the
drop on exactly that ground. **The word that came in is `just`, and the arithmetic did not ask for
it — the honesty did.**

##### 1.1.2 · The two substitutes, re-evaluated against a 12 s block rather than an 8 s one

**Both were written for the retired 8 s `B11` and both had to be re-priced when the block changed.
Neither is adopted, and here is why each is not.**

> **SUBSTITUTE A — 17 w, and it is now further out of reach than it was.** "You can't use the
> clause. ·hold 0.4· You can't edit it away either — not without answering the question first."
>
> At 8 s it read **2.13 w/s**, over every rate ceiling in this kit, and this file priced it at 11 s.
> **In the merged 12 s block it is worse, not better:** it must sit behind the refusal sentence, so
> the block would carry `9 + 17 = 26 w` in 12 s = **2.17 w/s**. **REJECTED on arithmetic** — and
> separately, **its first half is the barred unscoped form**, so §1.1.1 refuses it on the claim as
> well. `CLAIMS-CLEARANCE.md` `N11` cleared it as a *claim* under R-7's older reading and
> conditioned it on a timing nobody had counted; the timing is now counted and it does not hold.

> **SUBSTITUTE B — 11 w, cleared at `N12`, and it survives the re-pricing.** "Use it, or edit it.
> ·hold 0.4· Not without answering the question first."
>
> Behind the refusal sentence the block carries `9 + 11 = 20 w` in 12 s = **1.67 w/s**, identical to
> the line of record. It keeps both halves of the mirror, carries the scope in a clause instead of
> two adverbs, and costs the bank nothing. **It remains the substitute to reach for if an adverb
> reads oddly on the day** — and it is a **substitute**, not a co-primary: taking it is a decision
> announced before the take, never a thing discovered in the edit.
>
> **Why the line of record is preferred over it, on the merits and not by seniority.** The parallel
> *"You can't … You can't …"* is the shape that makes the sentence read as a **mirror** rather than
> as advice, and `B9` opened on the objection in the viewer's own voice — so the block that answers
> it wants a denial, not an instruction. *"Use it, or edit it"* is an imperative whose negation
> arrives only in the fragment after it, and a listener who mishears the second fragment has heard
> permission. **The scoped denial cannot be mis-parsed that way.**

`N13` still governs both: **half a mirror is not a mirror.** *"…not without answering the question
first"* used **alone** answers a question the audience has not been asked. **Both halves, in
whichever form is taken.**

**The silence after the line is scripted. Do not fill it.** Same rule as B5, for the same reason: a
viewer who works out the mirror themselves is a viewer who believes it. This is the last spoken
second of the demo and the close card lifts into the hold, not over the line.

**The film has no admission to mirror B7 here, and it does not pretend to have one.**
`film-recut-plan.md` §2.3 COST 3 states the cost plainly and R-4 states the mitigation: the way
through is **shown** — the three live defeater prompts are on screen beside the refusal — and only
the walking through it is not. **MUST NOT SAY:** *"and there is no way through"* — there are three,
they are on screen, and each demands a citation.

**On screen for the mirror:** the refusal still in frame, and beside it the three defeater prompts
as the disposition read returned them, verbatim, under the screen's own legend
*"Ways this obligation could be answered — each requires a citation"* — each a question, none of
them an escape hatch, and **no *"not applicable"* option, because the shipped vocabulary does not
carry one.** The clearance lattice beside them. Shared clause and shared precursor still legible
(R-5).

**Delivery:** the first sentence flat and slightly bored — this is the second time, and the second
time should sound routine, because routine is the claim. Then the hold. Then drop the pace and the
volume, once, through the mirror. Then stop. **Do not lean on `quietly` or on `just`.** Both have to
be audible, not underlined; a founder who presses them turns a measurement into a boast.

---

## 2 · THE ARITHMETIC, AND WHAT EVERY SECOND OF SILENCE BUYS

**Re-derived for the two-block shape, not patched.** The table this replaces read `B9 10 s / B10
6 s / B11 8 s` and `38 w`, and every one of those figures described a decomposition §0.3 retired.
The window and delivered columns are `VO-DEMO.md` §2's, which is `BEATS.yaml`'s.

| block | window | delivered | w/s over the window | speech at 1.9 w/s | silence | what the silence buys |
|---|---|---:|---:|---:|---:|---|
| B9 | 12 s | **20 w** | 1.67 | 10.5 s | 1.5 s | the 0.4 hold on the click, and 1.1 s for the typed proposal to settle |
| B10 | 12 s | **20 w** | 1.67 | 10.5 s | 1.5 s | the 0.6 mirror hold, and ≈ 0.5 s for the spoken `SQLSTATE` |
| | **24 s** | **40 w** | **1.67** | **21.1 s** | **2.9 s** | |

**The two blocks deliver 40 words where the three delivered 38, in the same 24 seconds** — 1.67 w/s
against 1.58. **That is a real cost of the ruling and it is stated rather than buried:** the
two-block shape is 0.09 w/s faster and carries 1.1 s less silence. It is affordable because 1.67 is
well under the kit's 1.95 ceiling and under `BEATS.yaml`'s 1.9 assumption, and because the silence
that went is *distributed* air rather than either of the two named holds, both of which survive at
full length. **What it buys is in §0.3 reason 3: the mirror and its hold are in one recorded take.**

The two right-hand columns are rounded to a tenth and the totals are the sums of the **unrounded**
values — the same convention, for the same reason, as `VO-DEMO.md` §2's slack column.

**One entry in the right-hand column is re-purposed by `R-SD4` and not re-priced by it.** `B9`'s
1.1 s no longer buys *the typed proposal settling* — the typing now ends at `2:13.5` — it buys
**the answer landing**, `2:14.0 → 2:15.5`, so that `B10` opens on a refusal already on screen.
**The seconds are identical and no figure in this table moves**; only what they are spent on
changes, and §1's ruling box is where that is argued. The wording in the cell is `VO-DEMO.md`
§2:595's and is left as inherited rather than edited here, per this file's own precedence rule.

**1.9 w/s is the speech rate `VO-DEMO.md` §2 measured across the delivered demo** (213 words ÷
112.1 s of speech). Every figure in the two right-hand columns is derived from it, not observed;
they are budgets and are labelled as budgets, per `film-recut-plan.md` §8 rule 8.

**B10's 1.5 s of silence is not 1.5 s of air.** `VO-DEMO.md` §0 prices a spoken SQLSTATE at about
two and a half words of time for one word on the page, so the spoken word `SQLSTATE` eats roughly
0.5 s of it and the block lands with about a second in hand — which is what pays the 0.6 s mirror
hold. That is the whole reason `B10` is twenty words and not twenty-two, and `VO-DEMO.md` §2 shows
the working: **at 21 words the hold and the surcharge run 1.13 s against 0.95 s of slack**, and the
hold would have had to shorten to fit.

**Why these blocks read slower than the demo's 1.78 w/s, stated rather than hidden.** Four things
in 24 seconds buy silence and every one of them is load-bearing: the proposed wording being typed
on camera (B9), a real round trip that must be spoken over and never cut away from (B9 into B10),
a SQLSTATE read digit by digit (B10), and a scripted hold before the mirror (B10). The close runs
at a deliberate 1.55 w/s for the same class of reason; 1.67 across two blocks carrying all four is
in family, not slack.

**The one second worth buying, if the film lead has it.** `film-recut-plan.md` §2.1 banks 8 s of
the 32 recovered. **The single best second in that bank is `B10` going 12 s → 13 s**, which takes
the hold after the mirror out toward the 2.3 s `VO-DEMO.md` gives `B5` — the only other line in this
film that is allowed to land in silence. Total becomes 173 s, still inside the 174 s hard stop with
1 s of margin. **This is a recommendation to the film lead and not a change to this file's budget**,
which is 24 s, and `BEATS.yaml` is the only file that may take it.

**A block that cannot be written at or under 1.95 w/s is not written.** That rule is what retired
the three-block shape's `B9` (§0.3 reason 1) and what retires `SUBSTITUTE A` in the merged block
(§1.1.2): a beat that reads at budget on paper and overruns in the mouth steals the second from the
beat after it — and the beat after `B10` is the close, which has no margin at all.

---

## 3 · WHAT THESE TWO BLOCKS NEVER DO

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
  a round trip, not a *"fast"*. `23514` is the **only** kernel-produced value spoken across both
  blocks. Everything else is on screen with its own label, and §6 says where each comes from.
* **Never calls the second refusal the same constraint as the first**, and never puts the trigger's
  name where the CHECK's belongs. B10's boxed note is the whole rule.
* **Never claims defence in depth.** **MUST NOT SAY:** *"drop the constraint and the trigger still refuses"* — this wave proves one direction on one subject, and the unwelding matrix has never executed in CI.
* **Never says the word tamper-proof.** **MUST NOT SAY:** *"tamper-proof"* in any form — tamper-evident, never proofing, and split-view resistance is not claimed anywhere in this film.
* **Never dresses the second run's fourth beat up as a second peak.** The CR run's projection-drift
  beat is in the payload and on screen in the transcript panel; **it is not narrated.** Speaking a
  second `P0001` twenty seconds after B5 does not double B5, it halves it. `CLICKS.md` §5 `B10` and
  `CLICKS-CR.md` §4 both keep it visible and unspoken, which is the same treatment B8 gives the
  beats it does not read out.
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
   is the whole of what this wave builds. Without it, B9 and B10 are not shot; `film-recut-plan.md`
   §6 is the fully specified NO-GO and it is a legitimate outcome.
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
5. **The three defeater prompts are on screen through `B10`'s second half** (R-4). Without them,
   the mirror is a refusal with no way through beside it, which is the reading
   `film-recut-plan.md` §2.3 COST 3 warns about. The block is still shot; the delivery note about
   *showing* the way through comes out, because nothing is showing it.
6. **`B8` is cut to 6 s.** §0.2's arithmetic. Without it the film is past the hard stop.
7. **The close lands at 22 s.** These 24 s are the seconds the naming close returns.

---

## 5 · THE SCOPE-CUT LADDER FOR THESE TWO BLOCKS

**Re-derived for the two-block shape.** The table this replaces cut `B9` `10 → 8` and `B11`'s hold
`8 → 7`; neither block exists in those durations any more. **`BEATS.yaml`'s `cut_ladder` is the
executable form and this is only the part of it that reaches this file** — the film's ladder is
`VO-DEMO.md` §5, which prints the line to read after every step.

| rank in `BEATS.yaml` | cut | from → to | saves | film after | the line after |
|---|---|---|---|---|---|
| **1** | **`B9`'s typing** — arrive on the proposed wording already composed | 12 s → 8 s | 4 s | 168 s | **14 w** · 1.75 w/s — *"Fine. Then don't use the clause — change it. Same paragraph, same incident behind it."* The last sentence goes; `R-2` and `R-5` both still bind. |
| **5** | **`B10`'s hold and its technical sentence** | 12 s → 8 s | 4 s | 155 s | **13 w** · 1.63 w/s — *"Refused. You can't just use the clause. You can't quietly edit it away."* **The mirror does not go and neither scope word goes.** |

**Ranks 2, 3 and 4 do not touch these blocks** (`B6`, `B7`, `k3`) and are in `BEATS.yaml` and
`VO-DEMO.md` §5.

> ### ⚠ RANK 1 IS NOT EXECUTABLE AS WRITTEN, AND THE FINDING IS NOT THIS FILE'S
>
> `CLICKS.md` measured that the `moc-proposed-text` textarea is **destroyed and re-created empty
> when the change screen mounts**, so there is no path by which that box holds text before `B9`
> begins: **the wording is typed on camera or it is not on screen at all.** Rank 1's saving is
> *"arrive on it composed"*, which that measurement forbids. What rank 1 can actually buy is a
> **shorter typed string**, not a pre-composed one — and `B9`'s 12 s already contains ≈ 3.5 s of
> read chain it cannot compress. **`b9` at 8 s is tight and should be re-checked against the
> measurement before anybody executes the step at 02:00.** Recorded here because this file's own
> §0.3 rests on the same measurement; **owner: W1, in `BEATS.yaml`.**
>
> **And `R-SD4` adds a second thing rank 1 must re-site rather than drop.** `b9` now carries
> **Click 6 at `+10.0`** and the flight to `+11.5`; a `12 s → 8 s` cut has to place both inside
> eight seconds, on top of the read chain, or `B10` opens on a request still in flight and R-K
> fails. **The press moves with the block or the step is not executed** — it is never solved by
> letting `B10`'s first word arrive before the refusal, which is the placement `R-SD4` struck.

**RULING ADOPTED FROM `film-recut-plan.md` R-10 · USE CASE TWO IS ATOMIC.** **No step may take
`B10` below 8 s, and `B9` may never be cut without `B10`.** A setup with no answer is worse than
neither: it spends 8–12 seconds raising the judge's question and never answers it. If the cut must
go past rank 5, **drop `B9` and `B10` together — all 24 s — and restore `B8` to 10 s**, which is a
net −20 s and leaves the film as one clean use case rather than one and a half.

**The mirror is never cut, at any rank.** It is the last two sentences of `B10` and it is the only
place the second half of this film's claim is made. **A cut that reaches it is not a cut, it is a
rewrite, and R-7 forbids it.**

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
| P1 | the CHECK's name **as the refusal reports it** | B10, through the mirror | the same beat's `constraint`, cross-read against M8 |
| P2 | `constraint_source` | B10 | the same beat's refusal. **If it reads `parsed` rather than `reported`, the on-screen label says `parsed`.** A weaker diagnosis stays on screen; `B5` set that precedent and it is why the film is believed. |
| P3 | the refusal's own message | B10, through the mirror | the same beat |
| P4 | the re-derived open count beside the projected one | B10 | the run's read beat |
| P5 | the projection-drift beat's SQLSTATE and message — **on screen, never narrated** | B10 | that beat. **It will name `mainline.fn_cr_merge_gate`, not `mainline.fn_permit_merge_gate`** — §6.1 again. |
| P6 | the kernel-procedure beat, **if it was shipped at all** | B10 | `cr-gate-route-plan.md` §R3 makes it conditional and drops it if the deployed cluster answers a privilege error rather than a gate refusal. **A privilege error is not a gate refusal and is never presented as one.** |
| P7 | `verdict` | B10 | the run |
| P8 | `persisted`, `self_persisted`, `isolation`, `single_transaction`, the two logical timestamps | B10 tail | the run |
| P9 | per-beat elapsed | B9, B10 | the run — **on screen with its label, never in a sentence** |
| P10 | the obligation's severity, origin and virulence | B9, B10 | the CR blocking-checks read. **`cr_blocking_checks_declared` reads `false` today**, so this is not merely unmeasured — the route does not exist. |
| P11 | the three defeater prompts and the clearance lattice | B10, from the mirror's frame | the disposition read. **It is not in `cr-gate-live.json` today** — W5 recorded the CR path and the route table, not that read. |
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
would trade the mirror's silence for a repetition. **The silence after the mirror is worth more than
a second explanation of a screen the judge is looking at.** If the film lead disagrees, the two
seconds exist in the bank and the sentence is cleared as a variant in `CLAIMS-CLEARANCE-CR.md` §4.

**And a second, added when this file was reconciled to the two-block shape, because it is a cost
this worker's own ruling imposes.** §0.3 reason 3 grants that shorter blocks are easier to re-take,
and the two-block shape gives that up: a fluffed mirror now costs a twelve-second re-take rather
than an eight-second one, and the block it is inside also contains the film's second SQLSTATE.
**I still think the ruling is right** — the measurement in reason 1 decides it before taste gets a
vote, and a hold assembled from two takes is a worse defect than a long re-take. **But the founder
should know, before the red light, that `B10` is the most expensive block in the film to get
wrong**, and it should be the one he rehearses most and shoots first if he shoots out of order.

**Nothing else.** Every ruling that reached this file — R-2, R-4, R-5, R-7, R-10 from the recut
plan, R3, R9 and R10 from the cr-gate route plan — made these blocks shorter and easier to defend.
