<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->
<!-- prose-hygiene: register -->
<!--
§4 and §6 of this file quote forbidden sentences beside the true ones, in the same form
docs/submission/MUST-NOT-CLAIM.md and docs/demo/research/r6-honesty.md use. It therefore
carries the `prose-hygiene: register` marker, and every quoted prohibition sits on a line that
also carries an explicit negation, which claim_hygiene.py's documented negation exemption reads
as STATING the rule. If this path is ever added to a scanner's sweep list, the scanner must
PRINT that it skipped this file, so "not scanned" is never read as "passed".
-->

# VO-DEMO.md — the spoken script for the 148-second demo

**Worker W2** · demo VO · first written 2026-08-15 · **re-cut 2026-08-16** for the two-use-case
film (no commit id is written here — the scanner refuses one and it is right to, because a
commit id cannot be chosen in advance).
**Binding plan:** `docs/demo/film-recut-plan.md` §§1.1, 1.2, 2.4, 4.1, 4.2, 4.3 — and, for
everything the re-cut did not touch, `docs/demo/story-and-script-plan.md` §§1, 2, 4, 5, 6 ·
**research:** `r4-story` §§3–6, `r6-honesty` Part A and Part B.
**Timing authority:** `docs/demo/film/BEATS.yaml`. Every in-point and duration below is
inherited from it. Where this file and that file disagree, **that file wins and this one is
wrong.**

**Claim-hygiene verdict, run by hand under R-B, after the re-cut:**

```
.venv/Scripts/python.exe scripts/demo/claim_hygiene.py --check docs/demo/film/VO-DEMO.md
  scanned 1 file(s) against 21 rules
  claim hygiene OK
exit 0
```

`docs/demo/film/**` is outside `TARGET_GLOBS`, so this verdict is a hand-run reading of this
file and of nothing else. It is not a CI result and this file does not claim one.

**Delivered: 259 spoken words over 148 s = 1.75 w/s across the read, 1.90 w/s across speaking
time.** Every beat is at or under the 1.95 w/s ceiling; the fastest are B3 and B6 at 1.89. That
is twenty-seven words short of the 286-word budget, and §2 says exactly where each of the
twenty-seven went and why. **Every duration and every word budget below is read from
`BEATS.yaml` as W1 landed it**, and §2 checks this file against that one line by line.

> **WHAT CHANGED IN THE RE-CUT, IN FOUR LINES.**
> 1. **Every timecode from B2 down was stale** and is corrected. `B0b` was inserted on
>    2026-08-16 and nothing after it moved: `B1` read `[0:20]`, ran 10 s, and the next header
>    still read `B2 [0:22]`. The chain is rebuilt in §1 and §2.
> 2. **`B0b` could not be spoken in its own window** — 27 words in 8 s is 3.38 w/s, against a
>    1.95 ceiling. Its line is cut to 14 words, which is 1.75 w/s: **the exact rate its own
>    header already claimed.** §2 records the original text and two alternatives.
> 3. **`B8` drops 10 s → 6 s** and its line with it. Its second half — the read-only cut to the
>    change request — is not lost; it becomes B9 and B10, driven instead of told.
> 4. **B9 and B10 are new**, and they are the mirror: you cannot use a clause under blame, and
>    you cannot quietly edit it away either. **R-7 governs that second sentence and W6 refuses
>    any variant that drops the scope word.**

> **THE BLOCK COLLISION IS CLOSED AND THIS FILE'S SHAPE IS THE ONE THAT SHIPPED.**
> `docs/demo/cr-gate-route-plan.md` §R9 named the same 24 s as **three** blocks — `B9` 10 s +
> `B10` 6 s + `B11` 8 s — and `VO-DEMO-CR.md` and `CLICKS-CR.md` were written to it, while this
> file, `BEATS.yaml`, `CLICKS.md`, `ONSCREEN-TEXT.yaml`, `FALLBACKS.md` and `SPINE.md` carried
> **two**. Both totalled 24 s, so 2:52 held either way and the arithmetic never caught it; what
> it broke is the recording, because the founder records **voice first, then picture, then
> matches them** and a block boundary is a place he stops and starts. **Resolved 2026-08-16 in
> favour of two. `B11` does not exist.** The ruling and its three reasons are in
> `VO-DEMO-CR.md` §0.3 and the deciding one is `CLICKS.md`'s measured read chain, not this
> file's seniority. **Nothing in this file changed for it.**
>
> **And a consequence for this file that is stated rather than fixed here:** §1 `B10`'s spoken
> line stands as delivered, and `CLAIMS-CLEARANCE.md` `D31` — a **`~ REWORD`**, *"guards
> **edits**"* naming the merge's object imprecisely, replacement supplied as *"guards the
> change"* — **is still open.** It is not discharged in the reconciliation, because the
> replacement is one word longer on the page and §2 has already priced this beat at 21 words
> running **1.13 s against 0.95 s of slack**. Taking it costs a re-price of `B10`'s hold and
> that is W2's call with W1's seconds, not a tidy-up. **A documented open item beats a quiet
> edit that breaks a beat's own arithmetic.**

---

## 0 · HOW TO READ THIS FILE

| mark | meaning |
|---|---|
| `[0:30]` | the beat's in-point in the finished cut |
| `·hold 2.0·` | the founder **stops talking** for that many seconds. It is a direction, not a pause for breath. |
| **bold** in the spoken line | a value that must be on screen at that instant (R-K) |
| `w` / `w/s` | words in the beat, and words per second across the beat's whole window |

**Word counting.** Whitespace-separated tokens as spoken. `23514`, `P0001`, `00000`,
`gate_closed_when_issued`, `SQLSTATE`, `severity-four` and `Mechanism-absent` each count as one
word. Em dashes, colons and semicolons are punctuation and count as nothing.

**A SQLSTATE is one word on the page and about two and a half words of time in the mouth.** The
plan chose 1.9 w/s rather than a faster rate for exactly this reason — *"several sentences
contain a SQLSTATE"* — and the four beats that carry one (B2, B5, B7, B10) are each held further
under their window to pay for it. §2 prices it, beat by beat.

**Pronunciation.** `23514` is read digit by digit — *two three five one four*. `P0001` is
*P, oh oh oh one*. `00000` is read *zero zero zero zero zero*, never as "OK", because the thing
on screen is the SQLSTATE. `SQLSTATE`, when the word itself is spoken (B10 only), is read
*ess-cue-ell-state* and costs about two words of mouth time for one word on the page. The
numerals stay in the script so the word count means one thing throughout; the mouth does the
expansion.

**Two rules govern every line below and neither is negotiable.**

1. **Nothing spoken is a number or a string the kernel did not produce**, and everything spoken
   is on screen while it is spoken. §4 is the ledger for that claim, sentence by sentence.
2. **No timing of the system is spoken anywhere in this script.** Not a millisecond, not a
   round trip, not a "fast". The one interval that is spoken — *ten seconds*, B3 — is the gap
   between two column timestamps in the seeded world, both of them on screen, and §4 says so.

---

## 1 · THE SCRIPT

**The chain, in one block, so it can be checked in twelve subtractions.** Each beat's in-point
plus its duration is the next beat's in-point; the last one hands off to the close.

```
B0   0:00 +12 → 0:12      B4   1:02 +10 → 1:12      B8   1:58 + 6 → 2:04
B0b  0:12 + 8 → 0:20      B5   1:12 +16 → 1:28      B9   2:04 +12 → 2:16
B1   0:20 +10 → 0:30      B6   1:28 +18 → 1:46      B10  2:16 +12 → 2:28
B2   0:30 +14 → 0:44      B7   1:46 +12 → 1:58      close 2:28
B3   0:44 +18 → 1:02
```

`12+8+10+14+18+10+16+18+12+6+12+12 = 148 s`. The close in-points at `[2:28]`, runs 22 s, and the
end card runs 2 s: `148 + 22 + 2 = 172 s · 2:52`.

---

### B0 · THE ORDINARY MOMENT — `[0:00]` · 12 s · **19 w** · **1.58 w/s**

> "This is the form a site supervisor signs before a crew opens a live machine — and in a
> moment," ·hold 2.0·

**Verbatim and unchanged**, adopted from the plan §1.1 / r4-story §6. The sentence does not
finish here. It finishes in B1, over the click, which is the point of it.

**On screen:** the supervisor's own permit form on the deployed origin — `DEMO-PTW-0001`, the
`dispositioned` chip beside the enum's other six values, the hazard card, the validity line,
`1 obligation outstanding`. The founder finishes typing the tail of the work description on
camera. Watermark on frame from frame one. No title card, no logo, no console.

**Delivery:** flat and unhurried. This is somebody's Tuesday. The 2.0 s of silence is the
cursor settling on **ISSUE** — the suspension before the click, not dead air. **B0b lands inside
that silence**, so the suspension is now filled rather than empty; the cursor does not move.

---

### B0b · WHY IT MATTERS — `[0:12]` · 8 s · **14 w** · **1.75 w/s**

> "Years ago, a machine that should have been isolated wasn't. The lesson lives here." ·hold 0.4·

**ADDED 2026-08-16 at the founder's direction, and the reason is an audience the rest of this
script does not serve.** Every other beat is pitched at the judges we know we have — AWS and
CockroachDB engineers, for whom `23514` and `P0001` are unfakeable proof and need no gloss.
This one beat is for everyone else: the video is going to a public channel, and a viewer with
no database background currently hears *"a database is going to refuse to let it through"*
without ever being told **why a refusal is the point**. Eight seconds buys the spine of the
thing — something went wrong, the lesson got written down, and written-down lessons get
forgotten — and it costs an expert nothing, because it makes no technical claim at all.

**THE LINE WAS CUT FROM 27 WORDS TO 14, AND THE ARITHMETIC IS WHY.** As first written it read
*"Years ago, a machine that should have been isolated wasn't. The lesson went into a document.
This is what happens when it lives in the database instead."* — **27 words in an 8 s window,
which is 3.38 w/s against this file's own 1.95 ceiling.** Its own header already declared
**1.75 w/s**, and at 8 s that rate buys exactly 14 words. The line above is the founder's three
moves at the rate the header promised: the incident, the lesson, and the difference. The verb in
*"lives here"* is the founder's own, out of the sentence that was cut. §2 records both
alternatives that would have kept all 27 words, and why neither is affordable.

**IT SAYS "YEARS AGO", NOT A YEAR, AND NAMES NOBODY.** `demo_world.sql`'s own narrative column
records that the seeded precursor **describes nobody** — it is synthetic history built to
exercise the gate. A spoken sentence that gave it a date, a site, a job title or an injury
would be inventing a casualty to move an audience, which is the one thing this repository has
refused at every turn. What is on screen a beat later is `severity 4`, `blood_major`, and an
`event_id` — real rows, generic subject. The sentence is true of the CLASS of incident the
product exists for, and claims nothing about a person. **The same rule binds B9 and B10** (§4.3
of the plan, §6 below).

**"The lesson lives here" is deictic, and that is the scope.** *Here* is the screen the viewer is
looking at. It is not a claim that lessons cannot live elsewhere, and it is not a durability
claim about this system. It is a pointer, and B2 cashes it ten seconds later by refusing.

**On screen:** unchanged — still the permit form, cursor still on **ISSUE**. Nothing is cut to
make room; B0's 2.0 s hold absorbs the beat.

**THE ORGANISER'S WINDOW — the claim this file used to make, corrected.** The old note said the
click *"lands at `[0:20]`, still inside the organiser's 'live demo within the first 20 to 30
seconds'"*. **That is true of the click and false of the refusal, and the refusal is what the
organiser's tip is about.** With `B0b` in place:

* the click lands at **`[0:20]`** — the near edge of the window;
* the refusal is on screen at **`[0:30]`** — **the outer edge, not comfortably inside it**;
* live product is on screen from **`[0:00]`**, which is what the tip actually asks for.

`BEATS.yaml`'s `first_refusal_at_s` must therefore read **30**, not 22 (plan R-1), and this
script has no slack left in front of it. **If a take runs long before `[0:30]`, the fix is the
cut ladder in §5, never a faster read of B0b.** Do **not** buy the seconds back by cutting B0
from 12 s to 8 s: B0 carries 19 fixed, verbatim words, and 19 words in 8 s is 2.38 w/s, over
every rate ceiling in this kit.

**Delivery:** slower than B0, and do not dramatise it. The sentence works because it is plain.

---

### B1 · THE ATTEMPT — `[0:20]` · 10 s · **18 w** · **1.80 w/s**

> "a database is going to refuse to let it through." ·hold 0.5· "One request — four beats came
> back inside it."

**The ten words of the opener's tail are the ones that cover the in-flight request.** The click
lands on "a database"; the wait is spoken over, start to finish. **Do not fill the wait with
silence and do not cut away from it.** If the round trip runs longer than the tail, the ·hold
absorbs it and the second sentence starts late; if it runs shorter, the second sentence starts
on time and the answer is already on screen when it does. Either way the founder says nothing
about how long it took — the screen's own elapsed clock is doing that job, and it is labelled
as this browser's measurement.

**"One request" is true of THIS request and the film now contains two.** Under the re-cut there
are exactly **two** mutating requests in the whole film: this one, and B9's. `BEATS.yaml`'s
`one_post_per_film` becomes `posts_per_film: 2` (plan §4.4), and the disclosure strap becomes
**per-request** — each POST composes its own `one request · four beats · … · … bytes` line, so
the sentence above never has to be re-scoped in the mouth. `FALLBACKS.md` F-11 tightens with it
(plan R-9): **exactly two mutating rows, each narrated while it is in flight; any third row, or
either row appearing without its narration, stops the take.**

**On screen:** the real pending state driven by the real promise. DevTools docked, one
`POST /v1/demo/gate-run` in flight, then `200`. As the answer lands, the disclosure line
composes itself: `one request · four beats · POST /v1/demo/gate-run · run_id … · response
received … · … bytes`.

**Delivery:** the second sentence is said flatly, as a fact about the network panel the judge is
looking at — it is half of the R-C disclosure and it must not sound like a boast.

---

### B2 · THE REFUSAL — `[0:30]` · 14 s · **25 w** · **1.79 w/s** — *filmed and read CALM*

> "Refused. **23514** — a CHECK constraint, **gate_closed_when_issued**, named by the database.
> It also says what would fix it. ·hold 0.3· This panel reveals the other beats in order."

**This beat is table stakes and is filmed as table stakes.** Every database can enforce a
CHECK. If B2 is read as the climax, the film peaks forty seconds early on the least
differentiated thing we own and B5 has nowhere to go (plan §2.1, r4-story §4.2).

**On screen:** the refusal band inside the operator app — `REFUSED · 23514 ·
gate_closed_when_issued · source: reported`, the database's own predicate, and the payload's
remedy line (*"1 obligation(s) remain open on this subject; disposing of exactly those restores
admissibility"*). DevTools stays in frame about two seconds.

**Delivery:** level, almost bored. The lift in the voice belongs to B5.

**R-C is discharged across B1 and B2** — *one request*, *four beats inside it*, *revealed in
order*. The third clause of the disclosure, *every timing shown is the server's*, is carried by
the persistent on-screen strap and by the per-beat elapsed label; the VO does not say it,
because the VO says no timing at all.

---

### B3 · WHY — THE MEMORY LOOP — `[0:44]` · 18 s · **34 w** · **1.89 w/s**

> "Stored: a **severity-four** stored-energy release, **2019** — and the blame it left on this
> clause. Recalled: it already ran; this is its record. ·hold 0.1· **Ten seconds** later the
> obligation existed — **severity four**. Nobody typed that four."

**The retrieval is spoken in the past tense, always.** `mainline_meas.recall_run` is a row that
already existed when the page loaded; the page read it. The present tense in this film is
reserved for the one thing that really executes while the judge watches — the re-derivation on
the button press. **MUST NOT SAY:** *"watch it remember"*, or any present-tense sentence about
the recall. Not once, not as an ad-lib. **This binds B9 and B10 too**, where the temptation is
strongest, and §6 spells out the two sentences that would break it there.

**Ten seconds is a measurement, not an adjective.** `started_at 2026-08-02T03:00:00Z` →
obligation materialised `2026-08-02T03:00:10Z`. Both instants are on screen, large, with the
interval band between them that says in its own words that it was subtracted in the browser
from the two instants either side.

**Nobody typed that four.** The seed wrote this obligation at `severity 0 / virulence routine`;
the projection overwrote both to `4 / blood_major` out of the clause's own blame closure. Seed
and deployment disagree on purpose and the difference is exactly the projection. *A counter a
client writes is a client's opinion; a counter a trigger writes, on a row the client did not
touch, is the database's.*

**On screen:** `STORE → RETRIEVE → ACT`, three labelled panels; `DEMO-INC-0001` with its
`SYNTHETIC —` prefix intact and `2019-03-14`; the `blame_edge` row naming the clause version;
the recall run's `n_candidates 1 · n_blocking 1 · index g1 · policy demo-recall-1.0`; the
obligation with `origin blame_ancestry`, `severity 4`, `virulence blood_major`, beside the
seed's `0 / routine`.

**The two identifiers this beat puts on screen are the two B9 and B10 must put back.** The
clause version and `DEMO-INC-0001` are what make the second refusal the *same* memory rather
than a second refusal (plan R-5). A judge who cannot match them across the two halves of the
film has been shown two unrelated CHECK constraints.

**Delivery:** rising, and this is the film's only tenderness — not sympathy for a person, of
which there is none in this record, but recognition of a fact that outlived everyone who knew
it. **Do not reach for sadness.** There is nobody here to be sad about, the seed says so in its
own column, and every second spent reaching is stolen from B5.

**Never cut this beat.** It is the rules requirement.

---

### B4 · THE HUMAN MOVE — `[1:02]` · 10 s · **18 w** · **1.80 w/s**

> "Third beat — the shortcut: the projected counter, forced to **zero**, out of band. Now the
> CHECK is satisfied." ·hold 0.5·

**A reveal, never a re-enactment.** Nothing on this screen forges anything. What is revealed is
beat three of the response already in hand, carrying its own `statement` and its own `label`
verbatim. There is no admin console in this film, no simulated SQL prompt, and no UI-side
decrement of the counter.

**On screen:** the MAINLINE gate-transcript panel beneath the operator app — infrastructure
becoming visible under the product — rendering the payload's own label (*"THE ATTACK: force the
projected counter to zero out of band, then merge again"*), its own statement
(`UPDATE mainline.permit SET open_blocking = 0 …; CALL mainline.merge_permit(…)`), and the
counter now reading `open_blocking 0`. The CHECK of beat 2 is genuinely satisfied.

**Delivery: the shrug, not the villainy.** Matter-of-fact, the way you would describe a
colleague clearing a stuck field. No menace in the voice; the tension is in the fact.

**Alternate line, only if the payload's `observed.attack` string is rendered on screen** —
*"The counter, forced to zero out of band — what a careless UPDATE leaves behind. The CHECK is
satisfied."* (18 w · 1.80 w/s). Its middle clause is the database's own text, verbatim, and may
be spoken **only** while that text is on screen.

---

### B5 · REFUSED ANYWAY — THE PEAK — `[1:12]` · 16 s · **25 w** · **1.56 w/s**

> "Refused anyway. **P0001** — the gate counted again, from the obligations themselves, and got
> **one**." ·hold 1.0·
>
> **"An attacker who owns the counter does not own the gate."**
>
> ·hold 1.8·

**This is the film. Everything before it is setup and everything after it is proof it was not a
trick.** The line is the corpus's own sentence (`USE-CASES.md`), and it is said once, slowly,
and then not explained. **The silence after it is scripted. Do not fill it.**

**On screen:** `REFUSED · P0001 · mainline.fn_permit_merge_gate`, the database's own sentence
verbatim — *"re-derived open obligation count is 1 while the projected counter reads zero"* —
beside the pair `open_blocking 0` / `open_blocking_derived 1`. And the diagnosis renders
**weaker** than beat 2's: `constraint_source: parsed`, `naa: null`, `naa_reason:
not_computable`, MUS `kind: capability_gap`. **Leave that weakening on screen.** A demo that
downgrades its own best exhibit is not one anybody believes is faked.

**Say "the gate", never "the CHECK constraint", for this refusal.** Beat 2 is a declarative
constraint the database enforces on every code path. Beat 3 is a procedural guard MAINLINE
wrote, executing inside the database. Collapsing them is the one over-reach a person who has
said *"the database refused"* for ninety seconds will make. **B10's refusal is the other
species again** — a declarative CHECK, `cr_gate_closed_when_merged` — and B10 says *constraint*
for exactly that reason.

**MUST NOT SAY, here or in the Q&A afterwards:** *"defence in depth, proven"*, or *"drop the
constraint and the trigger still refuses"*. This beat proves one direction, live. The other
direction is asserted by an unwelding matrix that has never executed in CI, and we do not claim
it. **MUST NOT SAY** *"tamper-proof"* in any form — the claim is that an attacker who owns
**this counter** does not own **this gate**, and nothing wider. If a judge asks whether an
administrator can get round it, the rehearsed answer is the honest one and it is not in this
film: yes — a cluster admin can drop a constraint, and what they cannot do is do it unobserved.
Tamper-evident, never tamper-proof.

**Delivery:** drop the pace and the volume. This is the only place in the film where the
founder slows down. **Never cut this beat.**

---

### B6 · THE ANSWER IS A QUESTION — `[1:28]` · 18 s · **34 w** · **1.89 w/s**

> "Not a checkbox — a question: **which isolation point was locked, and who verified it at
> zero?** ·hold 0.1· **Mechanism-absent** costs **rank four**, a **second signer**; **emergency
> override** dies in **twelve hours**. The engineer answers, and signs."

The question is the seeded defeater prompt for `MECHANISM_PRESENT_AND_VERIFIED`, spoken word
for word as the row carries it. The costs are the clearance lattice for `blood_major` at
`policy_version cl-1.0`, on screen beside the options.

**On screen:** the safety engineer's disposition screen. Three defeaters rendered as questions,
none of them a global escape hatch. The lattice beside them. The signature binding to
`demo.signer`, who is rendered on the **acceptance** row as the acceptor — the column behind
that name means *who the obligation was shown to*. The **Issue** row stays unsigned until B7.

**MUST NOT SAY:** *"it catches rubber-stamping"* or *"it proves someone actually read it"* —
nothing in this data model separates a considered disposition from a rubber stamp, we do not
pretend otherwise, and the VO never goes near it. What is true and smaller: the question is
unavoidable, the record is precise, and the worst answer is not representable in the lattice at
all. **MUST NOT SAY:** *"the database refuses a defeater code that was never offered"* — that
gap is closed in the application and it is written down.

**This beat is what makes B10 legal.** The change request's own obligation carries **its own
three-option defeater vocabulary**, generated for a different act under a different
`vocab_sha256`. B10 leans on that: the edit is refused *and the way through it is on screen*.
Without B6 having established that a defeater is a question with a price, B10's refusal reads
as a wall.

**Delivery:** release. The film has been refusing for forty seconds; this is a person answering.

---

### B7 · AND THEN IT ADMITS — `[1:46]` · 12 s · **21 w** · **1.75 w/s**

> "**00000** — admitted. State **merged**, head sequence **three**; the form turns from blocked
> to issued. ·hold 0.4· Nothing was overridden: the obligation was answered."

**A gate that always refuses is broken, not safe.** The film does not end on a refusal. **This
beat is also the reason B10's mirror needs a scope word:** thirty seconds after B7, the audience
has watched the permit be issued *on that clause*. A B10 that said *"you can't use the clause"*
flat would be contradicted by the film itself, in the film itself. §4 row 28 and §6 both hold
that line.

**On screen:** `ADMITTED · 00000`; `state merged`, `open_blocking 0`, `head_seq 3`, the
server-computed clearance digest **captioned as server-computed and never as a constant**, and
the disposition's own kind, `applied`. The permit screen turns from blocked to issued.

**Delivery:** relief, briefly. Then straight into B8, which is cool.

---

### B8 · NONE OF IT PERSISTED — `[1:58]` · 6 s · **11 w** · **1.83 w/s**

> "**Persisted false.** One **serializable** transaction — written, then unwound. Press it
> yourself."

**RE-TIMED 10 s → 6 s IN THE RE-CUT, and the four seconds were not taken from the proof.** The
rollback proof is `persisted false`, `SERIALIZABLE`, and the minted disposition id with zero
rows surviving — all of it is in this beat's first half and all of it survives. What went is the
read-only cut to the change request, which was **rank 1 on the old cut ladder** for a stated
reason: *"it is the weakest-supported second on camera: that subject is shown read-only and told
rather than driven."* B9 and B10 are that subject being driven. The four seconds were spent on
the complaint the ladder was making.

**Say `persisted false`. Never say "nothing was written".** Something was written: beat 4 minted
a `disposition_id` no other writer holds, and the payload proves the unwinding with that uuid —
`minted_disposition_rows_after_rollback: 0`. The strong reading is this run's own
(`self_persisted`), not the whole-database one. At 6 s the words *"the disposition it minted"*
come out and **the screen carries them instead** — the minted uuid is beside its zero row count,
large. *"written, then unwound"* is the shortest form of the same fact and it is not optional:
without it, *"persisted false"* alone can be heard as *"nothing happened"*.

**On screen:** `persisted false · single_transaction true · isolation SERIALIZABLE ·
disposition rolled_back`; the minted `disposition_id` beside its zero row count; the opened and
closed logical timestamps, identical. **The change-request image is no longer here** — it is
B9's opening frame, driven.

**Delivery:** cool, level, and finished — but not final. The invitation is an invitation: the
endpoint cannot write, and a judge is being told to go and try it. *"again"* is the word that
came out to fit 6 s, and it costs nothing: the judge has just watched the press.

**Under NO-GO (plan §6), this beat is restored to 10 s and to its full line** —
*"**Persisted false.** One **serializable** transaction, rolled back — the disposition it minted
was written, and unwound. Press it again yourself."* (19 w · 1.90 w/s) — and the read-only
change-request image returns as its second half, unnarrated, exactly as §5 records.

---

### B9 · THE OTHER WAY IN — `[2:04]` · 12 s · **20 w** · **1.67 w/s** — *NEW*

> "Fine. Then don't use the clause — change it. ·hold 0.4· Same paragraph. Same incident behind
> it. This request asks to edit it."

**This beat exists because a judge who is paying attention has already asked the question, and
the seeded world already answers it.** The film's first two minutes show that a permit cannot be
issued while it rests on a clause a past incident's blame reaches. The obvious reply is
*"fine — so couldn't somebody just rewrite the rule?"* **"Fine." is that reply, in the judge's
own words, conceded out loud before it is answered.** Everything after it is the answer.

**Why it is a memory beat and not a second refusal.** Same precursor's blame, same clause
`dec0de00-0004-…`, a **different subject kind** reached through a **different gate family**
(`cr_*`, not `permit`), generating a **different defeater vocabulary** for a different act. That
is a claim about how the memory is *attached* — to the clause, not to the workflow — and it is
the answer to *what makes agentic systems different from traditional apps*: the constraint
follows the knowledge, and it follows it into the process that would erase it (plan §2.4).

**"Same paragraph" is the plain-English form of "same clause version", and it is deliberate.**
The word *clause* is already in the sentence; *paragraph* is what a person outside this industry
hears when they look at `7.3.2(b)` on screen. Nothing is glossed that is not immediately cashed
out by the label beside it.

**R-5 IS BINDING AND THIS BEAT IS WHERE IT IS DISCHARGED.** The clause `dec0de00-0004-…`
(label `7.3.2(b)`) **and** the precursor `DEMO-INC-0001` must be legible **in the same frame**,
with the same identifiers a judge saw in B3. **If both are not in frame, the second and third
sentences come out** — and if they cannot be got into frame at all, B9 and B10 are cut together
(§5, R-10) and the film is one clean use case rather than one and a half.

**On screen:** the console's Management-of-Change screen for `DEMO-MOC-0001` — `state
checks_materialised`, the clause of record at `7.3.2(b)`, the clause version id and
`DEMO-INC-0001` both legible — and the founder **typing the proposed wording on camera** into
the console's own `moc-proposed-text` input, **carrying no provenance chip**. Then the second
and last mutating request of the film, in flight, with the panel in frame.

**R-2: the proposed wording is typed by a human, on camera, and the VO never reads it aloud.**
`CLICKS.md` §4 is the standing convention — *typed carries no chip* — and it is the same
discipline B0 already uses for the work-description tail. Nothing is hard-coded and the product
asserts nothing about that string. **MUST NOT SAY:** the proposed wording, in any form, as
though the database produced it.

**Delivery:** conversational on *"Fine."* — this is the founder taking the objection seriously,
not swatting it. Then flat and quick through the three short sentences; they are labels, not
argument. The 0.4 s hold is the click landing, not a pause for effect.

---

### B10 · REFUSED AGAIN — `[2:16]` · 12 s · **20 w** · **1.67 w/s** — *NEW*

> "Refused. Same **SQLSTATE** — a different constraint guards edits. ·hold 0.6· You can't
> **just** use the clause. You can't **quietly** edit it away."

**The last sentence is the mirror the whole re-cut exists for, and it is the one line in this
film that can go wrong.**

> **R-7 · authority: the plan §4.2, resting on `VO-CLOSE.md` §5.3, which ruled on exactly this
> failure for the word "here".** The clause **can** be edited — by disposing of the obligation
> first, which is what the three defeaters on screen are for.
>
> **MUST NOT SAY:** *"the clause cannot be changed"* · *"the database won't let anyone edit the
> rule"* · *"the memory is immutable"* · *"you can't edit it."*
> **TRUE INSTEAD:** *"you can't **quietly** edit it away"* — the scope word is doing all the
> work, and dropping it converts a true statement into a false one.
> **W6 files a REFUSE row against every variant that drops it.** So does the founder, on the
> day, in the mouth: if the adverb goes missing in a take, the take goes.

**The first half needs a scope word too, and it has one.** B7, thirty seconds earlier, shows the
permit **issued** on that same clause. *"You can't use the clause"* flat is therefore
contradicted by this film, in this film. **"You can't just use the clause"** is the true form:
not without the obligation being answered — which the audience has watched happen. Both halves
of the mirror carry their scope, and both scopes point at the same thing: **the question comes
first, whichever way you come at the clause.**

**"Different constraint" is said, and "gate" is not.** B5's refusal is a procedural guard
MAINLINE wrote; this one is a declarative CHECK the database enforces on every code path —
`cr_gate_closed_when_merged`, predicate `((state != 'merged') OR (open_blocking = 0))`. The
distinction B5 protects is protected here by using the other word.

**"Same SQLSTATE" is a claim about the code and it is checkable in one frame.** Both refusals
are `23514`; the constraint names differ. The word `SQLSTATE` is spoken while `23514` is on
screen, which is the value it names (R-K). **MUST NOT SAY:** *"the same constraint"* — it is
not; that is the whole point.

**On screen:** the refusal — `23514`, `cr_gate_closed_when_merged`, its own predicate
`((state != 'merged') OR (open_blocking = 0))`, and `open_blocking: 1` — **beside the three live
defeater prompts** from the change request's own obligation, with `severity 4` and its lattice.
The clause version and `DEMO-INC-0001` are still in frame (R-5). The disclosure strap for this
second request is composed and visible, and it carries **`persisted: false` measured by the
endpoint from its own fingerprint** — not claimed, and not spoken.

**The three defeaters are on screen because the film must not end on a wall.** Use case one runs
refuse → answer → admit. Use case two runs refuse → *and here is the question that would answer
it* — and stops there, because the merge is not driven and there is no committing route to drive
it with. **The way through is shown; only the walking through it is not.** If the defeater panel
cannot be got on screen, the mirror still runs, but the beat is weaker and W6 should know it.

**Alternate line, if the adverb reads oddly on the day** —
*"Refused. Same SQLSTATE, different constraint — this one guards the edit. ·hold 0.6· Use it or
rewrite it — the question comes first."* (19 w · 1.58 w/s). It carries no scope word because it
needs none: it states the way through instead of scoping the refusal. **It is the only sanctioned
substitute.** Improvising a third form on the day is how R-7 gets broken.

**Delivery:** the first sentence flat and slightly bored — this is the second time, and the
second time should sound routine, because routine is the claim. Then the 0.6 s hold, then the
two short sentences slow and level. **Do not lean on "quietly."** The word has to be audible,
not underlined; a founder who presses it turns a measurement into a boast.

**Never speak `blood_major`.** It is a column value, it is on screen, and saying it aloud edges
toward inventing an injury. **No date, no site, no job title, no injury** in this beat or in B9.

---

## 2 · THE ARITHMETIC, AND WHERE THE TWENTY-SEVEN WORDS WENT

**Rebuilt, not patched.** The table this replaced omitted `B0b` entirely and totalled `120 s /
225 budget / 213 delivered / 112.1 s of speech`. Every one of those four numbers is now false.

**Windows and budgets are read from `BEATS.yaml`, not chosen here.** Checked against W1's landed
file: `b0..b10` `t`/`dur`, `demo_s: 148`, `total_s: 172`, `first_refusal_at_s: 30`,
`posts_per_film: 2`, `demo_words: 286` — **every one agrees with this file.**

| beat | window | budget | delivered | Δ | w/s over the window | slack, and what it buys |
|---|---|---|---|---|---|---|
| B0 | 12 s | 24 | **19** | −5 | 1.58 | 2.0 s — the cursor settling on ISSUE, now filled by B0b |
| B0b | 8 s | 28 | **14** | −14 | 1.75 | 0.6 s — 0.4 s hold before B1 resumes B0's sentence |
| B1 | 10 s | 16 | **18** | +2 | 1.80 | 0.5 s — absorbs a slow round trip |
| B2 | 14 s | 26 | **25** | −1 | 1.79 | 0.8 s — 0.3 s hold, 0.5 s pays for saying `23514` |
| B3 | 18 s | 34 | **34** | 0 | 1.89 | 0.1 s |
| B4 | 10 s | 19 | **18** | −1 | 1.80 | 0.5 s — the beat before the peak |
| B5 | 16 s | 30 | **25** | −5 | 1.56 | 2.8 s — `P0001`, then the silence after the line |
| B6 | 18 s | 34 | **34** | 0 | 1.89 | 0.1 s |
| B7 | 12 s | 22 | **21** | −1 | 1.75 | 0.9 s — 0.4 s hold, 0.5 s pays for saying `00000` |
| B8 | 6 s | 11 | **11** | 0 | 1.83 | 0.2 s |
| B9 | 12 s | 20 | **20** | 0 | 1.67 | 1.5 s — 0.4 s hold, 1.1 s for the press at `2:14.0` and the answer landing; typing 2.5 s |
| B10 | 12 s | 22 | **20** | −2 | 1.67 | 1.5 s — 0.6 s mirror hold, 0.5 s for the spoken `SQLSTATE` |
| | **148 s** | **286** | **259** | **−27** | **1.75** | **11.7 s** |

**259 words ÷ 136.3 s of speech = 1.90 w/s delivered.** Every beat is at or under 1.95 w/s and
the fastest are B3 and B6 at 1.89. The slack column is rounded to a tenth and the total is the
sum of the unrounded values, which is why it reads 11.7 and the column adds to 11.5. Of that
11.7 s, roughly **2.9 s** is eaten by the four spoken SQLSTATE tokens — `23514`, `P0001`,
`00000` and the word `SQLSTATE` itself — leaving about **8.8 s** of real silence, against
**8.1 s** of named holds.

**Every `·hold·` in §1 is under its own beat's slack, beat by beat and not merely in aggregate.**
Where a hold and a SQLSTATE surcharge together run past that beat's slack — **B2 by about
0.25 s, B5 by 0.75 s, B7 by 0.25 s** — all three are inherited unchanged from the pre-re-cut
script, and in all three **the hold is what shortens, never the words.** The `·hold·` figures in
§1 are ceilings for exactly that reason. **The three beats this re-cut wrote or re-timed carry
both without borrowing:** B8 has 0.2 s of slack and no hold at all; B9 spends 0.4 s of hold
inside 1.5 s; B10 spends 0.6 s of hold plus 0.5 s of spoken `SQLSTATE` inside 1.5 s. **No new
beat takes a second from the beat after it**, which matters more here than anywhere else in the
film, because the beat after B10 is the close and the close has no margin left.

**THE PRESS RULING OF 2026-08-16 IS PRICED IN THOSE TWO ROWS AND IN NO OTHER ONE.** Click 6 —
*Approve change* — lands at **`2:14.0`, `+10.0` into B9**, so the request is in flight across the
B9/B10 seam and B10 in-points at `2:16` on a refusal already painted. `CLICKS.md` §5 is the
choreography; `../shoot-docs-plan.md` R-SD4 is the ruling; `BEATS.yaml` records it under `b9` and
`b10` as a comment because **no window, no budget, no delivered count and no w/s figure in the
table above moved for it.** What moved is what B9's 1.1 s *buys*: the keystroke window is now
**2.5 s**, and the 1.1 s pays for the press and for the answer landing rather than for the typed
proposal settling. **The other candidate was priced out of B10's own row, and here is the
measurement that killed it.** B10's 1.5 s is **0.6 s of mirror hold plus 0.5 s for the spoken
`SQLSTATE`, leaving 0.4 s free** — so starting B10's line ≈ 2.5 s after its in-point would have
taken 2.1 s that does not exist, and paid for it out of either the hold (`SPINE.md` §4: a
scripted element, never a pause the editor may tighten) or the words (20 delivered words in 9.5 s
is **2.11 w/s**, over the 1.95 ceiling every other row here clears). **Any slip of B10's first
word is therefore capped at 0.4 s** — and that 0.4 s is the same 0.4 s `D31` would have to be
paid out of, the head note's still-open `~ REWORD` at 21 words running 1.13 s against 0.95 s of
slack. **It cannot be spent twice**, and the film lead states which it is spent on before the
shoot rather than discovering the collision on the day. Both beats stay conditional on
`FALLBACKS.md` §4.2's R-11 gate: on the no-go path neither row is shot at all.

**Where the budgets come from, and the one that cannot be met.** Every figure in the budget
column is `BEATS.yaml`'s own `vo_word_budget`, taken verbatim — including the three the re-cut
added or re-timed (`b0b 28`, `b8 11`, `b9 20`, `b10 22`). **A budget is a ceiling, not a target;
`BEATS.yaml` says so in its own words, and under-running one is free.** That matters here,
because **`b0b`'s budget of 28 words in an 8 s window is 3.50 w/s** — it is not a target this
script declined to hit, it is a number no mouth can reach under a 1.95 ceiling. The 14 words
delivered are 1.75 w/s, and the −14 in that row is the whole finding, not a shortfall.

**Where each of the twenty-seven went, so nobody has to guess:**

* **B0 −5, B1 +2 (net −3).** The opener is verbatim and its only clean split point is after
  *"and in a moment,"* — 19 words. Its remaining ten are the ones that cover the in-flight
  request in B1, which is what the brief asks those words to do. B0 + B1 = 37 against a budget
  of 40, and the missing three cannot be recovered without either rewriting a sentence that is
  fixed or splitting it somewhere that does not survive being read aloud.
* **B0b −14, the largest Δ in the table, and every one of the fourteen is arithmetic rather than
  taste.** The founder's line ran **27 words** (recounted by hand against this file's own
  counting rule; `BEATS.yaml`'s budget, the plan and the brief all record 28, which is off by one
  against the text as written — either way the finding is identical and neither number is
  speakable). 27 words in an 8 s window is **3.38 w/s** and the 28-word budget is **3.50 w/s**,
  both against a 1.95 ceiling, and the beat's own header already declared **1.75 w/s**.
  At 8 s, 1.75 w/s is **14 words**. What went: the middle sentence, *"The lesson went into a
  document"*, and the explicit landing, *"This is what happens when it lives in the database
  instead."* What stayed: all three of its moves — the incident, the lesson, the difference —
  compressed into *"The lesson lives here,"* whose verb is the founder's own out of the sentence
  that was cut, and whose *here* is the deictic that supplies the scope.
  **Two alternatives that would have kept all 27 words, and why neither is taken:**
  1. **B0 12 s → 10 s and B0b 8 s → 10 s.** Timecode-neutral downstream — B1 still lands at
     `[0:20]` and nothing after it moves — and it buys B0b 19 words at 1.90 w/s. **The cost is
     B0's entire 2.0 s hold**, the suspension on the cursor that makes B1's click legible, and
     B0 would then run 19 w / 10 s = 1.90 w/s with no silence at all. **This is a real option
     and it belongs to W1, not to this file.** It is recorded here so the founder can take it.
  2. **B0b 8 s → 14 s**, which is what 27 words at 1.90 w/s actually costs. Film total
     `172 + 6 = 178 s` — past the 174 s hard stop and four seconds from the 180 s ceiling.
     **Not affordable.** The 8 s the re-cut banks is margin to the ceiling, not spendable
     seconds: only 2 s exists below the hard stop.
* **B5 −5.** 30 words in 16 s leaves 0.2 s of silence. The brief requires a ·hold after the
  line, and a peak with no silence after it is not a peak. Five words buy 2.8 s.
* **B4 −1.** A 10-second beat cannot carry 20 words at or under 1.95 w/s; 19 is the ceiling, and
  20 would read at 2.00.
* **B2 −1, B7 −1.** Each of these beats says a SQLSTATE, which costs about a second more than
  its one word suggests. A beat that reads at its budget on paper and overruns in the mouth is
  a beat that steals the second from the beat after it.
* **B8 ±0 on budget, −8 on the line.** The beat lost four seconds, so it lost eight words. What
  went: *"the disposition it"* — the minted uuid is on screen beside its zero row count and says
  it better than the mouth can — *"rolled back"*, folded into *"unwound"*, and *"again"* from
  the invitation. What could not go, at any length: **`persisted false`**, **`serializable`**,
  and *"written, then unwound"*, because *"persisted false"* alone is hearable as *"nothing
  happened"* and §4 row 19 forbids that reading.
* **B9 ±0 — the only beat in the film delivered exactly at its budget.** Twenty words is what
  `BEATS.yaml` allows and what the beat needs; at 1.67 w/s they leave 1.5 s, which pays the 0.4 s
  hold on the click and leaves 1.1 s for the typed proposal to settle on screen before the
  request goes.
* **B10 −2, and four words came out of the plan's draft while one went in.** The mirror is
  twelve of the twenty words and none of the twelve is spare. The plan drafted **23**; twenty is
  what a 12 s window buys once the 0.6 s mirror hold and the surcharge on the spoken word
  `SQLSTATE` are both paid for — at 21 words those two run **1.13 s against 0.95 s of slack**,
  and the hold would have had to shorten to fit. What came **out**: *either*, from the end of the
  mirror, which the parallel *"You can't … You can't …"* carries without it; and *this one … the
  edit*, compressed to *guards edits*, because the constraint being pointed at is the only one on
  screen. What went **in** is the word the arithmetic did not ask for and the honesty did:
  **just**. Row 30 is why — without it, the first half of the mirror is contradicted by B7,
  thirty seconds earlier, in this same film.

**The budgets in `BEATS.yaml` that exceed the 1.95 w/s rate ceiling are B0 (24 w / 12 s = 2.00)
and B0b (28 w / 8 s = 3.50).** B8's old 20 w / 10 s = 2.00 retired with the 10 s beat. They are
stated here rather than quietly met, because meeting them would have broken the ceiling the same
kit sets — and B0b's is not a near miss, it is nearly double.

**The film, checked once more end to end:** demo `148` + close `22` + end card `2` = **172 s ·
2:52**. Target 172, hard stop 174 (2 s margin), ceiling 180 (8 s margin).

---

## 3 · WHAT THE VO NEVER DOES

**These rules bind B9 and B10 exactly as they bind B0 through B8. Nothing in the new material is
an exception to any of them.**

* **Never speaks a timing of the system.** No millisecond, no `elapsed_ms`, no round trip, no
  "instantly", no "fast". The per-beat durations are on screen, labelled as the server's own
  measurement, and the screen's clock is labelled as the browser's. Any latency spoken aloud
  becomes a product characteristic in a judge's memory, and this repository has no p50, no p99
  and no load profile to back one.
* **Never rounds.** Every number spoken is an exact column, lattice or SQLSTATE value.
* **Never speaks a digest, a commit id or a hash of any kind.** The clearance digest is
  different on every run — that is what proves the rollback — so it is on screen with a caption
  and never in a sentence. The change request's `vocab_sha256` is on screen in B10 and is never
  spoken.
* **Never names an AWS service, a region, or any capability the film is not showing.** The
  service-and-feature roll-call is the closing block's job (W3), where the names sit over live
  picture and a judge can pause on them. The three mechanism words the VO says — *CHECK
  constraint* in B2, *serializable* in B8, *constraint* in B10 — are the mechanism on screen at
  the instant they are said, not items from a list.
* **Never says the product's name inside the 148 s.** It appears in the closing block, where it
  has been earned, and on screen in the transcript panel's own function name. The demo shows
  infrastructure by showing what it stops.
* **Never speaks a column value that would read as an injury.** `blood_major` is on screen in B3
  and again in B10 and is never in the mouth.
* **Never reads a string a human typed as though the product produced it.** B0's work-description
  tail and B9's proposed wording are both typed on camera and both carry no provenance chip
  (R-2); neither is spoken.

---

## 4 · PER-SENTENCE CLEARANCE — every claim that touches a must-not-say family

Read this column by column: what is said, which family it walks past, and what makes it
survivable. Nothing here is a paraphrase of the register's TRUE INSTEAD into something stronger.

**Rows 1–22 keep their numbers**, because other documents cite them; the re-cut rewrote rows 19,
20 and 21 in place, where the sentences they cleared actually changed, and appended rows 23–30
for the new material rather than renumbering the sheet.

| # | spoken | family | why it clears |
|---|---|---|---|
| 1 | B0/B1 *"a database is going to refuse to let it through"* | leading the pitch; A4 live-demo claims | It is the refusal, not the category — `23514` from a declarative CHECK, and the beat sheet delivers it on camera at `0:30`. The film never opens with a category sentence, and the words *"agentic memory"* are not spoken in the demo at all. |
| 2 | B0 *"before a crew opens a live machine"* | A3 corpus · R-F injury | Describes the work, not an event, and puts no person in anything. The watermark is on frame throughout and every noun on screen is authored. |
| 3 | B1 *"One request — four beats came back inside it"* / B2 *"This panel reveals the other beats in order"* | R-C progressive disclosure | The disclosure line on screen composes the same fact out of the payload, and the persistent strap carries the third clause. Without this sentence the reveal is indistinguishable from faked sequencing; with it, it is a reading aid and says so. Scoped to **this** request: the film contains two, each with its own strap (row 23). |
| 4 | B2 *"23514 — a CHECK constraint, gate_closed_when_issued, named by the database"* | A8 where the refusal lives | Scoped to beat 2, which really is a declarative CHECK, with `constraint_source: reported` — the name came from the database's own error fields. The VO never generalises this to every refusal on screen; the film's refusals are not all one species and §1 B5 and B10 say which is which. |
| 5 | B2 *"It also says what would fix it"* | over-claiming the diagnosis | The payload's NAA is on screen: `kind dispose_obligations`, `cardinality 1`, with the exact obligation id. It is a claim about **this** refusal; forty seconds later the film shows the system reporting `naa: null · not_computable` on its best refusal and does not hide it. |
| 6 | B3 *"a severity-four stored-energy release, 2019"* | R-E one world · R-F severity not injury | `DEMO-INC-0001`, `occurred_at 2019-03-14T06:20:00Z`, severity gate/actual/potential 4, `SYNTHETIC —` prefix visible and uncropped. No person, no injury, no `WO-88213`, no 2013, and **no 2024 anywhere in this script**. |
| 7 | B3 *"the blame it left on this clause"* | A7 vector search · A5 retrieval story | The blame is a `blame_edge` row closed transitively and read through one view — a foreign key, not a similarity. The demo world seeds no embeddings and runs no vector query, and the VO never says *searched*, *ranked* or *filtered*: the lookup is exact and that is the stronger claim. |
| 8 | B3 *"Recalled: it already ran; this is its record"* | **A5 tense — the family with no scanner behind it** | Past tense, as the record requires: the recall run is a seeded row the page read. The only present tense in the film is the re-derivation on the button press, which really executes. |
| 9 | B3 *"Ten seconds later"* | A2 latency | An interval between two column timestamps in the seeded world — `03:00:00Z` → `03:00:10Z` — both on screen with a band that says it was subtracted in the browser. It is not a system latency, it is not offered as one, and no other interval is spoken in the film. |
| 10 | B3 *"Nobody typed that four"* | fabrication / seed reshaping | Checkable in both directions: the seed file writes `severity 0 / routine`, the live payload reads `4 / blood_major`, and both are on screen together. The disagreement is the projection, and it is the point. |
| 11 | B4 *"the projected counter, forced to zero, out of band"* | R-D reveal not re-enactment | Beat 3's own `statement` and `label` out of the response already in hand, rendered verbatim in the transcript panel. No forging control exists in the operator app and none is implied. |
| 12 | B4 *"Now the CHECK is satisfied"* | A9 defence in depth | States only that the constraint is now satisfied — which it is, `open_blocking` really does read zero. No redundancy claim is made in either direction. |
| 13 | B5 *"P0001 — the gate counted again, from the obligations themselves, and got one"* | A8/A9 · the beat-3 caveat | Called *the gate*, never *the CHECK constraint*: this is a procedural guard MAINLINE wrote, executing inside the database, and the distinction is preserved out loud. One direction, live, and only that one. |
| 14 | B5 *"An attacker who owns the counter does not own the gate"* | A10 tamper-evidence | The claim is scoped to the counter and this gate, and it is what beat 3 measured. **MUST NOT SAY:** *"tamper-proof"* — the claim is tamper-evidence and never proofing; there is one witness, it is ours, and split-view resistance is not claimed anywhere in this film. A cluster admin can drop a constraint and we say so when asked. |
| 15 | B6 *"which isolation point was locked, and who verified it at zero?"* | A12 human judgement | The seeded defeater prompt, spoken as the row carries it. It claims the question was asked — nothing about whether it was answered sincerely. |
| 16 | B6 *"Mechanism-absent costs rank four, a second signer; emergency override dies in twelve hours"* | over-claiming the lattice | Both rows are the `blood_major` lattice at `policy_version cl-1.0`, on screen beside the options. The spoken costs are a true subset of the row; nothing is added to it. |
| 17 | B6 *"The engineer answers, and signs"* | R-G roles · A12 identity | No role is asserted that the columns do not carry, and `demo.signer` is rendered as the acceptor. **MUST NOT SAY:** *"we verify their identity"* — a signature binds to an enrolled credential and whose it is remains an identity provider's assertion, not ours. |
| 18 | B7 *"Nothing was overridden: the obligation was answered"* | A12 rubber-stamping | Reads the disposition's own kind, `applied`, on screen beside the lattice row for `emergency_override` that was not used. It is a statement about which constructor was signed, and nothing about the quality of anybody's judgement. |
| 19 | B8 *"Persisted false … written, then unwound"* | A4 / Part B4 | `persisted false`, `self_persisted false`, `transaction.disposition rolled_back`, `minted_disposition_rows_after_rollback 0`. **MUST NOT SAY:** *"nothing was written"* — something was written, and the payload proves it was unwound. At 6 s the phrase *"the disposition it minted"* moves to the screen, where the uuid sits beside its zero row count; **the clause *"written, then unwound"* may not be dropped with it**, because `persisted false` alone is hearable as the forbidden sentence. |
| 20 | B8 *"Press it yourself"* | inviting a judge onto a live endpoint | The endpoint is non-mutating by construction and every run mints a fresh uuid4 and destroys it. The invitation is the answer to *"is this a recording?"* and it is checkable in one click. *"again"* came out for the 6 s window and nothing turns on it — the judge has just watched the press. |
| 21 | B9/B10 — `DEMO-MOC-0001` is **driven, not told** | R-I · A13.5 | This row previously read *"nothing is spoken over `DEMO-MOC-0001`"*, and it was right on the day it was written: there was no merge route and no diff. **It is superseded by measurement, not by preference** — the demo-safe attempt endpoint answers, the console's approve control calls it, and the subject is pressed on camera. `r6-honesty` A13.5's bar stands as the dated research record it is; **nobody edits it**, and W6 files the superseding clearance row in `CLAIMS-CLEARANCE.md` citing the measurement that retires it (plan R-8). **MUST NOT SAY:** *"watch the same debt block the change request"* — that sentence stays barred on A5 tense grounds, independently of A13.5, and no measurement retires it. **If the three readings in §7.7 do not hold on the day, this row reverts and B9/B10 are cut together.** |
| 22 | — *no agent, no model, no AWS service and no region is named* | A5.2 · A6 · A7 | No model is in this request path and no MCP agent has called this deployment; the audit view is empty and zero is the true answer. The service roll-call and the residency split belong to the closing block, over live picture, where a judge can pause on them. The only database words the VO speaks — *CHECK constraint*, *serializable*, *constraint* — are the mechanism on screen at that instant. |
| 23 | B1 *"One request"*, with two POSTs in the film | R-C · F-11 anti-fake | The sentence is scoped to the request in flight while it is said, and each of the two mutating requests composes **its own** disclosure strap from **its own** payload. `posts_per_film: 2` is a spine amendment (plan §4.4); F-11 tightens rather than loosens (plan R-9): **exactly two mutating rows, each narrated in flight, and any third row — or either row without its narration — stops the take.** |
| 24 | B0b *"Years ago, a machine that should have been isolated wasn't"* | A3 corpus · R-F injury · R-E one world | No year, no site, no job title, no injury, no person. `demo_world.sql`'s own narrative column records that the precursor **describes nobody**. It is true of the class of event the product exists for and asserts nothing about anyone. **MUST NOT SAY:** *"a worker was hurt"* in any form. |
| 25 | B0b *"The lesson lives here"* | over-claiming durability | Deictic, not absolute: *here* is the screen. It is not *"the memory is immutable"*, it is not *"nothing is ever forgotten"*, and it makes no claim about anything off this screen. What cashes it is B2, ten seconds later, refusing. |
| 26 | B9 *"Fine. Then don't use the clause — change it."* | leading the pitch · A4 staging | Claims nothing. It voices the objection a judge has already formed, out loud, before answering it — the same device B4 uses for the shortcut. The attempt that follows is real, driven on camera, against the live origin, and its refusal is the endpoint's own answer on the take that is filmed. |
| 27 | B9 *"Same paragraph. Same incident behind it."* | R-5 · A5 tense · A7 vector search | Both identifiers are on screen in the same frame, and they are the identifiers a judge already read in B3 — the clause version `dec0de00-0004-…` at label `7.3.2(b)`, and `DEMO-INC-0001`. *"behind it"* is stative and past-facing: the `blame_edge` row already existed. Nothing was searched, ranked or filtered; it is a foreign key. **If both identifiers are not in frame, the sentence comes out** (R-5). |
| 28 | B9 *"This request asks to edit it."* | fabrication · R-2 typed-carries-no-chip | The change request is on screen in `state checks_materialised` against that clause of record; *"asks"* is the request's posture and claims nothing about its outcome. The proposed wording is typed by a human on camera and carries no provenance chip. **MUST NOT SAY:** the proposed wording aloud, or anything that presents it as a value the database produced. |
| 29 | B10 *"Refused. Same SQLSTATE — a different constraint guards edits."* | A8 where the refusal lives · anti-fake | Both refusals really are `23514`; the constraint names really do differ, and `cr_gate_closed_when_merged` is named by the database with its own predicate `((state != 'merged') OR (open_blocking = 0))` and `open_blocking: 1` beside it. Called *constraint*, never *gate*, because this one is declarative and B5's is not. **MUST NOT SAY:** *"the same constraint"* — it is a different one, and that is the point. The word `SQLSTATE` is spoken while `23514` is on screen (R-K). |
| 30 | B10 *"You can't **just** use the clause. You can't **quietly** edit it away."* | **R-7 — the line this whole re-cut can fail on** | Both halves are scoped and neither scope is decoration. *Just*: B7 shows the permit **issued** on that clause thirty seconds earlier, so the unscoped form is contradicted by this film in this film. *Quietly*: the clause **can** be edited, by disposing of the obligation first, which is exactly what the three defeaters on screen beside this refusal are for. **MUST NOT SAY:** *"the clause cannot be changed"* · *"the database won't let anyone edit the rule"* · *"the memory is immutable"* · *"you can't edit it"* · *"you can't use the clause"* unscoped. **TRUE INSTEAD:** the line above, or the one sanctioned alternate in §1 B10. **W6 refuses every other variant and the refusal is final.** |

---

## 5 · THE SCOPE-CUT LADDER — the lines to read when a beat is trimmed

**The old ladder is void and this one replaces it.** Its rank 1 was *"B8's second half, the
change-request image"* — that image no longer exists as an image; it is B9 and B10. Its rank 2
was *"B0 from 12 s to 8 s"*, which is arithmetically unexecutable: B0's 19 verbatim words in 8 s
is 2.38 w/s, over every ceiling in this kit. Both are struck.

Pre-committed, in this order, exactly as the plan fixes it. **Never cut B3 or B5.** These
variants exist so nobody improvises a sentence at 02:00.

| rank | beat | from | to | saves | film after | what goes |
|---:|---|---:|---:|---:|---:|---|
| 1 | B9 | 12 | 8 | 4 | 168 | the typing of the proposed wording; arrive on it composed |
| 2 | B6 | 18 | 14 | 4 | 164 | one of the three permit defeaters (two carry the point) |
| 3 | B7 | 12 | 9 | 3 | 161 | the dwell on the post-merge fields |
| 4 | K3 | 6 | 4 | 2 | 159 | the spoken limit in the close — **W3's line, not this file's** |
| 5 | B10 | 12 | 8 | 4 | 155 | the hold after the mirror line, and the SQLSTATE sentence |

**Floor 155 s.** `never_cut: [B3, B5]`.

**Cut 1 — B9 from 12 s to 8 s.** The founder arrives on a composed proposal instead of typing it,
and the beat loses its last sentence and its hold:

> B9 `[2:04]` · 8 s · **14 w** · 1.75 w/s — "Fine. Then don't use the clause — change it. Same
> paragraph, same incident behind it."

*"This request asks to edit it"* is what goes; the screen's own `state checks_materialised` chip
and the proposed-wording field carry it. **R-2 still binds:** if the wording is composed rather
than typed, it is still a human's string, still carries no provenance chip, and is still never
spoken. **R-5 still binds:** both identifiers stay in frame or the second sentence goes too.

**Cut 2 — B6 from 18 s to 14 s**, two defeaters instead of three, lattice kept:

> **24 w** · 1.71 w/s — "Not a checkbox — a question: which isolation point was locked, and who
> verified it at zero? Mechanism-absent costs rank four and a second signer."

**Cut 3 — B7 from 12 s to 9 s:**

> **14 w** · 1.56 w/s — "00000 — admitted. State merged, head sequence three; the form turns
> from blocked to issued."

**Cut 4 — K3, the close's third card, 6 s to 4 s.** Not this file's line. Recorded here only so
the ladder is executable end to end without opening another document.

**Cut 5 — B10 from 12 s to 8 s.** The hold goes and the technical sentence goes. **The mirror
does not, and neither scope word does:**

> B10 `[2:16]` · 8 s · **13 w** · 1.63 w/s — "Refused. You can't just use the clause. You can't
> quietly edit it away."

`23514`, `cr_gate_closed_when_merged` and the predicate are all on screen and lose nothing by
not being said. **A cut that reaches the mirror is not a cut, it is a rewrite, and R-7 forbids
it.**

> **R-10 · USE CASE TWO IS ATOMIC, AND THIS IS THE ONE LADDER RULE THAT IS NOT ABOUT SECONDS.**
> No step may take B10 below 8 s, and **B9 may never be cut without B10.** A setup with no answer
> is worse than neither: it spends 8–12 s raising the judge's question and never answers it. If
> the cut must go past rank 5, **drop B9 and B10 together (24 s) and restore B8 to 10 s** — net
> −20 s, film 152 s — and the film is back to one clean use case rather than one and a half.
> B8's restored line is in §1 B8, written out in full so nobody has to reconstruct it at 02:00.

**If the live origin is down on the day, none of these apply.** The film is not made against a
mock. It is postponed, or filmed against the local node and **said to be local, on screen** — a
staged refusal is a rules violation under the hackathon's own Functionality rule, not merely a
dishonesty. If a `40001` retry appears, it is pressed again on camera and the retry is not cut
out. **The same rule governs B9 and B10:** if the change-request attempt does not refuse on the
take, nothing is re-shot to make it refuse and no refusal is described that did not happen — the
two beats come out together.

---

## 6 · THE SENTENCES THAT MUST NOT BE SAID, INCLUDING AS AN AD-LIB

The full register is `r6-honesty` Part A and `docs/submission/MUST-NOT-CLAIM.md`. These are the
ones this film can actually trip over, and the scanners cannot hear a founder — a human is the
only control here.

| MUST NOT SAY | say this instead, or say nothing |
|---|---|
| *"Watch it remember."* · any present-tense sentence about the retrieval | "Recalled: it already ran; this is its record." The present tense belongs only to the re-derivation on the button press. |
| *"Our agent decided to block it."* | No model is in this path. The decision is a CHECK constraint and a procedural gate, and that is the interesting part. |
| *"The system searched every past incident."* | Nothing was sifted. The lookup followed a blame ancestry to one clause version and found the one event that reaches it. |
| *"Vector search found the precursor."* · *"Changefeeds propagate the lesson."* | This world seeds no embeddings and runs no vector query, and there is no changefeed in any migration. Do not dress an exact lookup as a similarity search. |
| *"Tamper-proof."* · *"split-view resistant"* in any form | Tamper-evident, never tamper-proof; there is one witness, it is ours, and that resistance is not claimed. |
| *"Defence in depth, proven."* | Beat 3 proves one direction, live. The other is asserted by a matrix that has never executed in CI, and we do not claim it. |
| *"It catches rubber-stamping."* | Nothing in this data model separates a considered disposition from a rubber stamp. It makes the question unavoidable and the record precise, and we never accuse. |
| *"Every refusal in this demo is the database's."* | The refusals are not all one species, and the film says which is which: B2 and B10 are declarative CHECK constraints, B5 is a procedural gate MAINLINE wrote. |
| *"the 2024 incident"* · *"the rewritten clause"* | 2019-03-14. **Nothing has been rewritten** — somebody has proposed to rewrite it, and B9 says *"asks to edit it"* for exactly that reason. |
| *"A worker was hurt."* · any injury, any person, any date, any site, any job title in the event — **in B0b, B3, B9 or B10** | A severity-four stored-energy release during intrusive work. The seed's own last clause is that it describes nobody. |
| *"blood_major"*, spoken aloud, anywhere | It is a column value. It is on screen in B3 and again in B10, and it stays there. Saying it edges toward inventing an injury. |
| *"It refuses in milliseconds."* · any product latency | Say nothing about speed. There is no p50, no p99 and no load profile in this repository. |
| *"We proved it in CI."* | Nothing in CI has ever asserted this URL. The live readings are hand-measured and written down. |
| *"an open-source agentic memory layer"* as an opening | Lead with the refusal. The words *agentic memory* are not spoken in these 148 seconds; B3 shows the loop instead. |
| **B9/B10** — *"Watch the same debt block the change request."* · *"The system just retrieved the incident and blocked the change."* | Past tense, always. The blame edge already existed and the obligation was already materialised; what executes on camera is the constraint, on the press. Say *"Same incident behind it"* and let the screen do the rest. |
| **B10** — *"The clause cannot be changed."* · *"The database won't let anyone edit the rule."* · *"The memory is immutable."* · *"You can't edit it."* | *"You can't **quietly** edit it away."* The clause **can** be edited, by disposing of the obligation first — which is what the three defeaters on screen are for. **R-7. W6 refuses every variant that drops the scope word, and the refusal is final.** |
| **B10** — *"You can't use the clause."* with no scope word | *"You can't **just** use the clause."* B7 shows that permit **issued**, on that clause, thirty seconds earlier. The unscoped form is contradicted by this film inside this film. |
| **B10** — *"The same constraint refused it."* | A different constraint, and the same SQLSTATE. `gate_closed_when_issued` and `cr_gate_closed_when_merged` are two rows; the mirror is that they answer to the same obligation, not that they are one thing. |
| **B9** — reading the proposed wording aloud, or in any form that presents it as the product's | It is a human's string, typed on camera, carrying no provenance chip (R-2). The VO never speaks it. |
| **B9/B10** — *"We merged it and rolled it back."* · *"We undid the edit."* | Nothing was merged. The attempt was **refused**, and the endpoint persisted nothing either way — `persisted: false`, measured by the endpoint from its own fingerprint, on screen and never spoken. |
| **B9/B10** — naming the change request's `vocab_sha256`, or any digest | On screen, never in a sentence. §3 holds. |

---

## 7 · WHAT THIS SCRIPT ASSUMES OF THE OTHER WORKERS

Recorded, not asserted — if any of these is not true on the day, the sentence that depends on it
is cut rather than kept.

1. **W1/W4/W5 — the disclosure line exists and composes from the payload** (`one request · four
   beats · … · response received …`), **once per mutating request, and there are now two.** B1
   and B2 say its content out loud; if the line is not on screen, B2's last sentence is still
   said, because R-C requires the fact spoken, but the strap is doing none of the work.
2. **W5 — both timestamps and the interval band are on screen through B3.** Without them,
   *"ten seconds"* is a number a viewer cannot check, and the sentence comes out.
3. **W5 — the seed's `severity 0 / routine` is rendered beside the live `4 / blood_major`.**
   Without that pairing, *"nobody typed that four"* comes out.
4. **W5 — the clearance lattice is on screen in B6.** Without it, B6 falls back to the question
   only (cut 2's line, minus its second sentence).
5. **W4 — the ISSUE control posts to `/v1/demo/gate-run` and nothing else.** The merge route
   answers `423` on this subject, and a `423` rendered as a gate refusal would be a fake
   refusal.
6. **W3 — no service or feature name is spoken before `[2:28]`.** If the closing block moves a
   name earlier, this script does not move with it.
7. **THE GATE ON B9 AND B10 — three readings, measured on the day, not promised.** Before either
   block is recorded, all three must hold (plan §6):
   * a demo-safe change-request attempt endpoint answers `200` with **`persisted: false`
     measured by the endpoint from its own fingerprint**, in the shape `POST /v1/demo/gate-run`
     already proves — one `SERIALIZABLE` transaction, each write beat fenced by its own
     `SAVEPOINT`, the whole transaction rolled back;
   * `GET /v1/change-requests/{cr_id}/blocking-checks` answers `200` — it answered `404` when the
     plan measured it, and the shipped console panel calls it, so a MoC screen filmed today
     films a broken panel;
   * the console's approve control is **enabled and calls that endpoint** — it is hard-disabled
     in the shipped bytes today.

   **If all three do not hold, B9 and B10 are cut together (R-10), B8 is restored to 10 s and to
   the full line in §1 B8, and the film is 152 s.** That is a legitimate outcome and not a
   failure. **Nothing in this file authorises a committing route, an approve control wired to
   anything but a rolled-back endpoint, or any widening of what `mainline_api` may write.**
8. **W4/W5 — R-5, and it is the condition the whole second use case rests on.** The clause
   version `dec0de00-0004-…` at label `7.3.2(b)` **and** `DEMO-INC-0001` legible in the same
   frame as the change-request refusal, with the same identifiers a judge read in B3. Without
   both, B9's second and third sentences come out; without any way to get them in frame, B9 and
   B10 come out together and the axis-1 trade the re-cut makes is a straight loss.
9. **W5 — R-2.** The proposed wording is typed by the founder on camera into the console's own
   input and carries no provenance chip. The VO never reads it.
10. **W4/W5 — the two-incident trap (`r6-honesty` A3).** The staged propagation payload reuses
    `DEMO-INC-0001`'s uuid while titling itself after a 2024 incident. **It must never be in the
    same shot as `DEMO-INC-0001`'s 2019 record, and it is never narrated.** If the MoC screen
    renders that title, B9's *"Same incident behind it"* comes out.
11. **W6 — the superseding clearance row for A13.5 (plan R-8)**, filed in `CLAIMS-CLEARANCE.md`
    and citing the measurement that retires it. **Nobody edits the research record
    `docs/demo/research/r6-honesty.md`** — it is not rewritten because the world moved; it is
    cited and superseded.
12. **W6 — F-11's tightening (plan R-9).** Exactly two mutating requests, each narrated while it
    is in flight; a third row, or either row without its narration, stops the take. This is
    strictly stronger than the rule it replaces, and it is not to be weakened to make room for a
    beat.
13. **W1 — `BEATS.yaml`, and this one is no longer an assumption: it is checked.** Read against
    W1's landed file, `b0`..`b10` `t` and `dur` agree with every in-point and duration in §1;
    `demo_s: 148`, `total_s: 172`, `hard_stop_s: 174`, `ceiling_s: 180`, `wps_assumption: 1.9`,
    **`first_refusal_at_s: 30`** (was 22, corrected under R-1) and **`posts_per_film: 2`** (in
    place of `one_post_per_film: true`, under plan §4.4) all agree with §1, §2 and §4 row 23.
    Every word budget in §2's budget column is that file's `vo_word_budget`, taken verbatim,
    summing to its `demo_words: 286`. **The single disagreement is recorded rather than resolved
    in this file's favour:** `b0b`'s budget of 28 words in an 8 s window is 3.50 w/s, above the
    kit's 1.95 ceiling. A budget is a ceiling and under-running is free, so nothing is broken —
    but if W1 would rather the spine carried a speakable figure, **15** is what 8 s buys at
    `wps_assumption`, and that is W1's line to change, not this one's.

**Dissent, recorded and not acted on:** one, and it is small. The re-cut's most defensible shape
would give `B0b` its full 27 words by taking 2 s from `B0` and 2 s from the hold — §2's
alternative 1 — which is timecode-neutral downstream and costs only atmosphere. **It is not taken
here because `B0`'s duration is `BEATS.yaml`'s, not this file's**, and a script that quietly
re-times a beat it does not own is exactly the failure this wave was called to fix. It is written
down so the founder can take it in one line if he wants it.

Every ruling that reached this file — R-C, R-D, R-E, R-F, R-G, R-I, R-K, and now R-1, R-2, R-5,
R-7, R-8, R-9, R-10 — made the script shorter and easier to defend. The one place I would have
written a bigger sentence, B6's *"the signature pins the exact options the signer was shown"*, is
left out on purpose: the digest that would make it true was wrong until the day before the
deployment on record, the captured bundle still carries the old value, and a sentence whose
evidence needs a re-measurement is not a sentence to hand a founder on the day.
