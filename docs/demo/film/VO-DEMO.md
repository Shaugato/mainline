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

# VO-DEMO.md — the spoken script for the 120-second demo

**Worker W2** · story-and-script · 2026-08-15 · written against the tree this wave started from
(no commit id is written here — see the verdict below; the scanner refuses one and it is right
to, because a commit id cannot be chosen in advance).
**Binding plan:** `docs/demo/story-and-script-plan.md` §§1, 2, 4, 5, 6 · **research:**
`r4-story` §§3–6, `r6-honesty` Part A and Part B.

**Claim-hygiene verdict, run by hand under R-B:**

```
.venv/Scripts/python.exe scripts/demo/claim_hygiene.py --check docs/demo/film/VO-DEMO.md
  scanned 1 file(s) against 21 rules
  claim hygiene OK
exit 0
```

`docs/demo/film/**` is outside `TARGET_GLOBS`, so this verdict is a hand-run reading of this
file and of nothing else. It is not a CI result and this file does not claim one.

**Delivered: 213 spoken words over 120 s = 1.78 w/s across the read, 1.90 w/s across speaking
time.** Every beat is at or under the 1.95 w/s ceiling. That is twelve words short of the
225-word budget, and §2 says exactly where each of the twelve went and why; the two largest are
the verbatim opener's split point and the silence the brief requires after B5's line.

---

## 0 · HOW TO READ THIS FILE

| mark | meaning |
|---|---|
| `[0:22]` | the beat's in-point in the finished cut |
| `·hold 2.0·` | the founder **stops talking** for that many seconds. It is a direction, not a pause for breath. |
| **bold** in the spoken line | a value that must be on screen at that instant (R-K) |
| `w` / `w/s` | words in the beat, and words per second across the beat's whole window |

**Word counting.** Whitespace-separated tokens as spoken. `23514`, `P0001`, `00000`,
`gate_closed_when_issued`, `severity-four` and `Mechanism-absent` each count as one word.
Em dashes, colons and semicolons are punctuation and count as nothing.

**A SQLSTATE is one word on the page and about two and a half words of time in the mouth.** The
plan chose 1.9 w/s rather than a faster rate for exactly this reason — *"several sentences
contain a SQLSTATE"* — and the three beats that carry one (B2, B5, B7) are each held further
under their window to pay for it. §2 prices it.

**Pronunciation.** `23514` is read digit by digit — *two three five one four*. `P0001` is
*P, oh oh oh one*. `00000` is read *zero zero zero zero zero*, never as "OK", because the thing
on screen is the SQLSTATE. The numerals stay in the script so the word count means one thing
throughout; the mouth does the expansion.

**Two rules govern every line below and neither is negotiable.**

1. **Nothing spoken is a number or a string the kernel did not produce**, and everything spoken
   is on screen while it is spoken. §4 is the ledger for that claim, sentence by sentence.
2. **No timing of the system is spoken anywhere in this script.** Not a millisecond, not a
   round trip, not a "fast". The one interval that is spoken — *ten seconds*, B3 — is the gap
   between two column timestamps in the seeded world, both of them on screen, and §4 says so.

---

## 1 · THE SCRIPT

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
cursor settling on **ISSUE** — the suspension before the click, not dead air.

---

### B1 · THE ATTEMPT — `[0:12]` · 10 s · **18 w** · **1.80 w/s**

> "a database is going to refuse to let it through." ·hold 0.5· "One request — four beats came
> back inside it."

**The ten words of the opener's tail are the ones that cover the in-flight request.** The click
lands on "a database"; the wait is spoken over, start to finish. **Do not fill the wait with
silence and do not cut away from it.** If the round trip runs longer than the tail, the ·hold
absorbs it and the second sentence starts late; if it runs shorter, the second sentence starts
on time and the answer is already on screen when it does. Either way the founder says nothing
about how long it took — the screen's own elapsed clock is doing that job, and it is labelled
as this browser's measurement.

**On screen:** the real pending state driven by the real promise. DevTools docked, one
`POST /v1/demo/gate-run` in flight, then `200`. As the answer lands, the disclosure line
composes itself: `one request · four beats · POST /v1/demo/gate-run · run_id … · response
received … · … bytes`.

**Delivery:** the second sentence is said flatly, as a fact about the network panel the judge is
looking at — it is half of the R-C disclosure and it must not sound like a boast.

---

### B2 · THE REFUSAL — `[0:22]` · 14 s · **25 w** · **1.79 w/s** — *filmed and read CALM*

> "Refused. **23514** — a CHECK constraint, **gate_closed_when_issued**, named by the database.
> It also says what would fix it. ·hold 0.3· This panel reveals the other beats in order."

**This beat is table stakes and is filmed as table stakes.** Every database can enforce a
CHECK. If B2 is read as the climax, the film peaks forty-five seconds early on the least
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

### B3 · WHY — THE MEMORY LOOP — `[0:36]` · 18 s · **34 w** · **1.89 w/s**

> "Stored: a **severity-four** stored-energy release, **2019** — and the blame it left on this
> clause. Recalled: it already ran; this is its record. ·hold 0.1· **Ten seconds** later the
> obligation existed — **severity four**. Nobody typed that four."

**The retrieval is spoken in the past tense, always.** `mainline_meas.recall_run` is a row that
already existed when the page loaded; the page read it. The present tense in this film is
reserved for the one thing that really executes while the judge watches — the re-derivation on
the button press. **MUST NOT SAY:** *"watch it remember"*, or any present-tense sentence about
the recall. Not once, not as an ad-lib.

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

**Delivery:** rising, and this is the film's only tenderness — not sympathy for a person, of
which there is none in this record, but recognition of a fact that outlived everyone who knew
it. **Do not reach for sadness.** There is nobody here to be sad about, the seed says so in its
own column, and every second spent reaching is stolen from B5.

**Never cut this beat.** It is the rules requirement.

---

### B4 · THE HUMAN MOVE — `[0:54]` · 10 s · **18 w** · **1.80 w/s**

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

### B5 · REFUSED ANYWAY — THE PEAK — `[1:04]` · 16 s · **25 w** · **1.56 w/s**

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
said *"the database refused"* for ninety seconds will make.

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

### B6 · THE ANSWER IS A QUESTION — `[1:20]` · 18 s · **34 w** · **1.89 w/s**

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

**Delivery:** release. The film has been refusing for forty seconds; this is a person answering.

---

### B7 · AND THEN IT ADMITS — `[1:38]` · 12 s · **21 w** · **1.75 w/s**

> "**00000** — admitted. State **merged**, head sequence **three**; the form turns from blocked
> to issued. ·hold 0.4· Nothing was overridden: the obligation was answered."

**A gate that always refuses is broken, not safe.** The film does not end on a refusal.

**On screen:** `ADMITTED · 00000`; `state merged`, `open_blocking 0`, `head_seq 3`, the
server-computed clearance digest **captioned as server-computed and never as a constant**, and
the disposition's own kind, `applied`. The permit screen turns from blocked to issued.

**Delivery:** relief, briefly. Then straight into B8, which is cool.

---

### B8 · NONE OF IT PERSISTED — `[1:50]` · 10 s · **19 w** · **1.90 w/s**

> "**Persisted false.** One **serializable** transaction, rolled back — the disposition it
> minted was written, and unwound. Press it again yourself."

**Say `persisted false`. Never say "nothing was written".** Something was written: beat 4 minted
a `disposition_id` no other writer holds, and the payload proves the unwinding with that uuid —
`minted_disposition_rows_after_rollback: 0`. The strong reading is this run's own
(`self_persisted`), not the whole-database one.

**On screen:** `persisted false · single_transaction true · isolation SERIALIZABLE ·
disposition rolled_back`; the minted `disposition_id` beside its zero row count; the opened and
closed logical timestamps, identical. Then the last image: the change request `DEMO-MOC-0001`,
read-only, still carrying `open_blocking 1` from the same 2019 closure, its approve control
rendered disabled with the reason printed beside it.

**The VO does not narrate `DEMO-MOC-0001`, and that is deliberate.** There is no merge route for
that subject, there is no diff, and the screen is told rather than driven. **MUST NOT SAY:**
*"watch the same debt block the change request."* The image carries its own on-screen label or
it is cut; it is first on the scope-cut ladder either way.

**Delivery:** cool, level, and finished. The invitation at the end is an invitation — the
endpoint cannot write, and a judge is being told to go and try it.

---

## 2 · THE ARITHMETIC, AND WHERE THE TWELVE WORDS WENT

| beat | window | budget | delivered | Δ | w/s over the window | slack, and what it buys |
|---|---|---|---|---|---|---|
| B0 | 12 s | 24 | **19** | −5 | 1.58 | 2.0 s — the cursor settling on ISSUE |
| B1 | 10 s | 16 | **18** | +2 | 1.80 | 0.5 s — absorbs a slow round trip |
| B2 | 14 s | 26 | **25** | −1 | 1.79 | 0.8 s — pays for saying `23514` |
| B3 | 18 s | 34 | **34** | 0 | 1.89 | 0.1 s |
| B4 | 10 s | 19 | **18** | −1 | 1.80 | 0.5 s — the beat before the peak |
| B5 | 16 s | 30 | **25** | −5 | 1.56 | 2.8 s — `P0001`, then the silence after the line |
| B6 | 18 s | 34 | **34** | 0 | 1.89 | 0.1 s |
| B7 | 12 s | 21 | **21** | −1 | 1.75 | 0.9 s — pays for saying `00000` |
| B8 | 10 s | 20 | **19** | −1 | 1.90 | 0.0 s |
| | **120 s** | **225** | **213** | **−12** | **1.78** | **7.9 s** |

**213 words ÷ 112.1 s of speech = 1.90 w/s delivered.** Every beat is at or under 1.95 w/s. The
slack column is rounded to a tenth and the total is the sum of the unrounded values, which is
why it reads 7.9 and the column adds to 7.7. Of that 7.9 s, roughly 2.4 s is eaten by the three
spoken SQLSTATEs, leaving about 5.5 s of real silence — and 2.0 s of that is the hold after
B5's line, the only one of them that is dramatic rather than mechanical.

**Where each of the twelve went, so nobody has to guess:**

* **B0 −5, B1 +2 (net −3).** The opener is verbatim and its only clean split point is after
  *"and in a moment,"* — 19 words. Its remaining ten are the ones that cover the in-flight
  request in B1, which is what the brief asks those words to do. B0 + B1 = 37 against a budget
  of 40, and the missing three cannot be recovered without either rewriting a sentence that is
  fixed or splitting it somewhere that does not survive being read aloud.
* **B5 −5.** 30 words in 16 s leaves 0.2 s of silence. The brief requires a ·hold after the
  line, and a peak with no silence after it is not a peak. Five words buy 2.8 s.
* **B4 −1, B8 −1.** A 10-second beat cannot carry 20 words at or under 1.95 w/s; 19 is the
  ceiling, and 20 would read at 2.00.
* **B2 −1, B7 −1.** Each of these beats says a SQLSTATE, which costs about a second more than
  its one word suggests. A beat that reads at its budget on paper and overruns in the mouth is
  a beat that steals the second from the beat after it.

**The budgets that exceed the rate ceiling are B0 (24 w / 12 s = 2.00) and B8 (20 w / 10 s =
2.00).** They are stated here rather than quietly met, because meeting them would have broken
the ceiling the same brief sets.

---

## 3 · WHAT THE VO NEVER DOES

* **Never speaks a timing of the system.** No millisecond, no `elapsed_ms`, no round trip, no
  "instantly", no "fast". The per-beat durations are on screen, labelled as the server's own
  measurement, and the screen's clock is labelled as the browser's. Any latency spoken aloud
  becomes a product characteristic in a judge's memory, and this repository has no p50, no p99
  and no load profile to back one.
* **Never rounds.** Every number spoken is an exact column, lattice or SQLSTATE value.
* **Never speaks a digest, a commit id or a hash of any kind.** The clearance digest is
  different on every run — that is what proves the rollback — so it is on screen with a caption
  and never in a sentence.
* **Never names an AWS service, a region, or any capability the film is not showing.** The
  service-and-feature roll-call is the closing block's job (W3), where the names sit over live
  picture and a judge can pause on them. The two mechanism words the VO does say — *CHECK
  constraint* in B2, *serializable* in B8 — are the mechanism on screen at the instant they are
  said, not items from a list.
* **Never says the product's name inside the 120 s.** It appears in the closing block, where it
  has been earned, and on screen in the transcript panel's own function name. The demo shows
  infrastructure by showing what it stops.

---

## 4 · PER-SENTENCE CLEARANCE — every claim that touches a must-not-say family

Read this column by column: what is said, which family it walks past, and what makes it
survivable. Nothing here is a paraphrase of the register's TRUE INSTEAD into something stronger.

| # | spoken | family | why it clears |
|---|---|---|---|
| 1 | B0/B1 *"a database is going to refuse to let it through"* | leading the pitch; A4 live-demo claims | It is the refusal, not the category — `23514` from a declarative CHECK, and the beat sheet delivers it on camera at `0:22`. The film never opens with a category sentence, and the words *"agentic memory"* are not spoken in the 120 s at all. |
| 2 | B0 *"before a crew opens a live machine"* | A3 corpus · R-F injury | Describes the work, not an event, and puts no person in anything. The watermark is on frame throughout and every noun on screen is authored. |
| 3 | B1 *"One request — four beats came back inside it"* / B2 *"This panel reveals the other beats in order"* | R-C progressive disclosure | The disclosure line on screen composes the same fact out of the payload, and the persistent strap carries the third clause. Without this sentence the reveal is indistinguishable from faked sequencing; with it, it is a reading aid and says so. |
| 4 | B2 *"23514 — a CHECK constraint, gate_closed_when_issued, named by the database"* | A8 where the refusal lives | Scoped to beat 2, which really is a declarative CHECK, with `constraint_source: reported` — the name came from the database's own error fields. The VO never generalises this to every refusal on screen; two of the three refusals in this film are a different species and §1 B5 and B8 say which. |
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
| 19 | B8 *"Persisted false … the disposition it minted was written, and unwound"* | A4 / Part B4 | `persisted false`, `self_persisted false`, `transaction.disposition rolled_back`, `minted_disposition_rows_after_rollback 0`. **MUST NOT SAY:** *"nothing was written"* — something was written, and the payload proves it was unwound. |
| 20 | B8 *"Press it again yourself"* | inviting a judge onto a live endpoint | The endpoint is non-mutating by construction and every run mints a fresh uuid4 and destroys it. The invitation is the answer to *"is this a recording?"* and it is checkable in one click. |
| 21 | — *nothing is spoken over `DEMO-MOC-0001`* | R-I told, never driven | No merge route exists for that subject and no diff exists to show. **MUST NOT SAY:** *"watch the same debt block the change request."* |
| 22 | — *no agent, no model, no AWS service and no region is named* | A5.2 · A6 · A7 | No model is in this request path and no MCP agent has called this deployment; the audit view is empty and zero is the true answer. The service roll-call and the residency split belong to the closing block, over live picture, where a judge can pause on them. The only database words the VO speaks — *CHECK constraint*, *serializable* — are the mechanism on screen at that instant. |

---

## 5 · THE SCOPE-CUT LADDER — the lines to read when a beat is trimmed

Pre-committed, in this order, exactly as the plan fixes it. **Never cut B3 or B5.** These
variants exist so nobody improvises a sentence at 02:00.

**Cut 1 — B8's second half (the change-request image), −4 s.** The VO is unchanged: it never
narrated that image. If the beat itself is re-timed to 6 s, drop the last sentence — *"Press it
again yourself."* — leaving **15 w** · 2.50 w/s, which is too fast for a 6 s window, so the
honest form of this cut is that **B8 keeps its 10 s and the change-request image is what
goes**. Either way `persisted false` is said.

**Cut 2 — B0 from 12 s to 8 s.** The opener splits earlier, at the em dash:

> B0 `[0:00]` · 8 s · **15 w** · 1.88 w/s — "This is the form a site supervisor signs before a
> crew opens a live machine —"
>
> B1 `[0:08]` · 10 s · **14 w** · 1.40 w/s — "and in a moment, a database is going to refuse to
> let it through."

B1 then carries the tail only, and **the whole R-C disclosure moves into B2**, which becomes
**22 w** · 1.57 w/s: *"Refused. 23514 — a CHECK constraint, gate_closed_when_issued, named by
the database. One request; four beats came back inside it, revealed here in order."*
The remedy sentence is what is given up. R-C is still discharged out loud.

**Cut 3 — B6 from 18 s to 14 s**, two defeaters instead of three, lattice kept:

> **24 w** · 1.71 w/s — "Not a checkbox — a question: which isolation point was locked, and who
> verified it at zero? Mechanism-absent costs rank four and a second signer."

**Cut 4 — B7 from 12 s to 9 s:**

> **14 w** · 1.56 w/s — "00000 — admitted. State merged, head sequence three; the form turns
> from blocked to issued."

**If the live origin is down on the day, none of these apply.** The film is not made against a
mock. It is postponed, or filmed against the local node and **said to be local, on screen** — a
staged refusal is a rules violation under the hackathon's own Functionality rule, not merely a
dishonesty. If a `40001` retry appears, it is pressed again on camera and the retry is not cut
out.

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
| *"Every refusal in this demo is the database's."* | Two of the three are not, and the film says which is which. |
| *"the 2024 incident"* · *"the rewritten clause"* | 2019-03-14. Nothing was rewritten — somebody has proposed to rewrite it, and that screen is never narrated. |
| *"A worker was hurt."* · any injury, any person in the event | A severity-four stored-energy release during intrusive work. The seed's own last clause is that it describes nobody. |
| *"It refuses in milliseconds."* · any product latency | Say nothing about speed. There is no p50, no p99 and no load profile in this repository. |
| *"We proved it in CI."* | Nothing in CI has ever asserted this URL. The live readings are hand-measured and written down. |
| *"an open-source agentic memory layer"* as an opening | Lead with the refusal. The words *agentic memory* are not spoken in these 120 seconds; B3 shows the loop instead. |

---

## 7 · WHAT THIS SCRIPT ASSUMES OF THE OTHER WORKERS

Recorded, not asserted — if any of these is not true on the day, the sentence that depends on it
is cut rather than kept.

1. **W1/W4/W5 — the disclosure line exists and composes from the payload** (`one request · four
   beats · … · response received …`). B1 and B2 say its content out loud; if the line is not on
   screen, B2's last sentence is still said, because R-C requires the fact spoken, but W7 should
   know the strap is doing none of the work.
2. **W5 — both timestamps and the interval band are on screen through B3.** Without them,
   *"ten seconds"* is a number a viewer cannot check, and the sentence comes out.
3. **W5 — the seed's `severity 0 / routine` is rendered beside the live `4 / blood_major`.**
   Without that pairing, *"nobody typed that four"* comes out.
4. **W5 — the clearance lattice is on screen in B6.** Without it, B6 falls back to the question
   only (cut 3's line, minus its second sentence).
5. **W4 — the ISSUE control posts to `/v1/demo/gate-run` and nothing else.** The merge route
   answers `423` on this subject, and a `423` rendered as a gate refusal would be a fake
   refusal.
6. **W3 — no service or feature name is spoken before `2:00`.** If the closing block moves a
   name earlier, this script does not move with it.

**Dissent, recorded and not acted on (plan §4):** none. Every ruling that reached this file —
R-C, R-D, R-E, R-F, R-G, R-I, R-K — made the script shorter and easier to defend, and the one
place I would have written a bigger sentence, B6's *"the signature pins the exact options the
signer was shown"*, is left out on purpose: the digest that would make it true was wrong until
the day before the deployment on record, the captured bundle still carries the old value, and a
sentence whose evidence needs a re-measurement is not a sentence to hand a founder on the day.
