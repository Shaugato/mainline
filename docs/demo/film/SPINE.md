<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# SPINE — the prose half of the spine

**W1 · spine and timing · 2026-08-15, revised 2026-08-16**
Machine-readable half: [`BEATS.yaml`](BEATS.yaml). Direction documents:
[`../story-and-script-plan.md`](../story-and-script-plan.md) and, for this revision,
[`../film-recut-plan.md`](../film-recut-plan.md).

**WHAT THE 2026-08-16 REVISION DID, AND WHY IT WAS OWED WHATEVER ELSE HAPPENED.**
`VO-DEMO.md` was edited on 2026-08-16 to insert **`B0b · WHY IT MATTERS`, 8 s at `0:12`**, at
the founder's direction. **The insert propagated to nothing.** This file's §2 table, `BEATS.yaml`,
`CLICKS.md` and `ONSCREEN-TEXT.yaml` all still described the pre-insert film. The film that
actually existed was `128 + 50 + 2 = 180` s — **exactly the number `BEATS.yaml` calls "a
disqualified cut; never approach it".** That is fixed here.

The same revision adds **use case two** (`b9`, `b10`): the change request that proposes to edit
the very clause use case one refuses to issue against, and cannot be quietly merged either. It is
paid for out of close **dwell** (50 s → 22 s, with nothing leaving the screen) and out of `b8`'s
second half, which was **rank 1 on this file's own previous ladder**. `b0`..`b8` keep their ids;
only their in-points shift by 8 s, and only `b8`'s duration changes.

**SCANNER VERDICT (R-B).** `docs/demo/film/` is outside every glob in
`claim_hygiene.py`'s `TARGET_GLOBS`, so the scanner is invoked by hand and its verdict is
recorded here rather than inferred from a green lane. Re-run against **this** revision on
2026-08-16 — the 2026-08-15 verdict this block used to carry described different bytes:

```
.venv/Scripts/python.exe scripts/demo/claim_hygiene.py --check \
    docs/demo/film/BEATS.yaml docs/demo/film/SPINE.md

  scanned 2 file(s) against 21 rules
  claim hygiene OK
  exit 0
```

**VERDICT: PASS — and the 2026-08-15 run is kept in the record because it is the more useful
half.** It went **red three times** on these two files: two `HYG-sha-literal` hits on a tree
reference written into the headers, and one `MNC-17-agentic-memory-lead` hit in §4, where a
forbidden opener was quoted on a source line whose negation marker had wrapped onto the line
above. All three were fixed **in these files, never in the scanner**. Recorded because a hygiene
verdict that has never gone red asserts nothing — and because the third one is a real trap for
the five workers writing behind me: **the negation exemption is line-scoped, so a `never` that
wraps away from the phrase it governs stops exempting it.** Keep the ban and the banned phrase on
one source line.

**The 2026-08-16 green was falsified in both directions before it was recorded**, because a green
whose only evidence is a green proves nothing about a path the scanner is not obliged to walk:

1. A **copy** of this file with a seven-hex commit literal appended was handed to the same
   command. It went **RED** — `HYG-sha-literal`, exit `1`. So the scanner really reaches these
   bytes, and the pass above is a pass rather than a skip. The planted copy lived in a scratch
   directory and is deleted; **nothing in the tree was made non-compliant to run it.**
2. `claim_hygiene.py --self-test` — *planted 4 violation families, scanner fired on 4*, exit `0`.
   So the rule set is not vacuous either.

**Neither file was softened to reach that green.** No rule was edited, no marker was bolted onto a
sentence that was not already a denial, and no phrase was deleted to dodge a rule.

---

## 0 · WHAT THIS FILE IS, AND WHAT IT IS NOT

`BEATS.yaml` owns every **number**. This file owns every **judgement**: the words that open
the film, where the weight sits, what each beat is forbidden to do, and the order things get
cut in when the assembled cut runs long. Where the two files could be read as disagreeing
about a duration, `BEATS.yaml` wins and this file is wrong.

Nothing here is a measurement. **Every duration in this file is a BUDGET this file is setting,
not a length anybody has timed.** The only kernel-produced values quoted anywhere in W1's two
files are the four SQLSTATEs and the four outcomes of the gate run — `00000` read, `23514`
refused, `P0001` refused, `00000` admitted — read from `evidence/deploy/live-gate-run.json`.
Every elapsed time, byte count, digest and field value on screen is re-derived from the run
that is actually filmed (R-K). **No number in this film is typed from memory.**

`b10` carries `23514` as well, from a **different** constraint. That repetition is the whole
point of the beat and it is not a transcription slip.

**How words are counted in this file**, so a later worker gets the same answer: a word is a
run of letters between spaces; a hyphenated compound counts once; dashes, em dashes and
punctuation are not words. The plan's §1.1 records the opener at 30 words and this file counts
29 — the delta is the dash, and it is under a second either way. Where a count matters, the
count in *this* file is the one the budgets in `BEATS.yaml` were built from.

---

## 1 · THE OPENING

### 1.1 The spoken opener — verbatim, and it is not to be paraphrased

Spoken over **B0**, on the supervisor's own screen, cursor already resting on **ISSUE**. Never
over a title card, and never after one — **there is no title card before the demo.**

> ## "This is the form a site supervisor signs before a crew opens a live machine — and in a moment, a database is going to refuse to let it through."

**29 words · 15.3 s at 1.9 w/s.**

**B0b NOW SITS INSIDE THIS SENTENCE, AND THAT IS A CONSEQUENCE THIS FILE MEASURED RATHER THAN
CHOSE.** Before the insert, the opener spanned B0 into B1 and the click landed at `12.0` s
*while the sentence was still finishing*, which was the design. `VO-DEMO.md` splits the opener
after *"and in a moment,"*, so with B0b in place the two halves of one sentence are now **eight
seconds apart**:

| | |
|---|---|
| B0's VO budget | 24 words (`0` → `12` s) — opener's first 19 words |
| **B0b** | **28 words (`12` → `20` s) — a different sentence, inside the opener's suspension** |
| B1 | 16 words (`20` → `30` s) — the opener's remaining 10 words, then B1's own |
| Click lands | `20.0` s — still **while the sentence is unfinished**, but after an 8 s interruption |

**This is W2's to resolve and the spine states the two options rather than inventing a third.**
Either B0's line closes at the em dash and B1 opens a fresh sentence, or the suspension is kept
and the read has to carry an eight-second gap inside one sentence. **`BEATS.yaml` budgets
`12 + 8 + 10` either way**, so nothing in the timing turns on the answer — but a sentence that
has to survive an eight-second interruption is a sentence somebody must actually try aloud
before the shoot, and this file will not pretend the insert was free.

**Fallback if the read runs long** (18 words · 9.5 s), from r4-story §6:

> *"This is what a site supervisor signs before a crew opens a live machine. Watch it get
> refused."*

This fallback is used only if the founder's read is genuinely over budget on the day. It is
weaker: it drops the word *database*, which is the film's whole differentiation, and it drops
*before a crew opens a live machine* into a subordinate clause. Prefer the full opener.

### 1.2 The written strap — the problem and the audience, costing zero seconds

Lower third, one line, **`0:00`–`0:07`**, under the live picture:

> **The lesson a past incident taught is a memo people forget. Here it is a constraint the
> database enforces — for the supervisors and safety engineers who issue permits to work.**

The organiser asks for the problem and the audience "in one sentence up front"; the spoken
opener spends its words on the promise instead. Writing the problem rather than speaking it
satisfies both instructions for free. Together the two sentences also satisfy Devpost's
"explain what your app does in the first few seconds" — **without a title card.** The product
name appears in the close, where it has been earned.

### 1.3 The first thirty seconds, against the organiser's own clock

| t | what a judge sees |
|---|---|
| `0:00` | **Live product.** The supervisor's permit form, on the deployed origin, URL bar in frame. |
| `0:12` | Still the live product. **B0b** says why a refusal is the point, over the same frame. |
| `0:20` | A real click, a real in-flight request, a genuine pending state. |
| `0:30` | **The first refusal, inside the supervisor's app** — `23514 · gate_closed_when_issued`. |

> **RULING R-1 — the `first_refusal_at_s` field was wrong and is corrected to `30`.**

`BEATS.yaml` carried `first_refusal_at_s: 22` until 2026-08-16, and `22` was the **pre-`B0b`**
number. With B0b the click lands at `0:20` and the refusal band is on screen at `0:30`.

The organiser's instruction is *"get to the live demo fast (within the first 20 to 30
seconds)"*, and **what that instruction asks for is live product, which is on screen from frame
one.** There is no title card, no logo, no architecture diagram and no terminal in front of it.
The refusal at `0:30` is now the **outer edge** of that window rather than eight seconds inside
it, and this file states that plainly rather than describing the beat sheet as having room it no
longer has. `VO-DEMO.md`'s own B0b note makes the narrower claim — that the **click** is still
inside the window — and that claim is true; the field said *refusal*, and `30` is what a refusal
costs once B0b exists.

**The seconds are not bought back by cutting B0.** The old ladder's rank 2 did exactly that
(12 s → 8 s), and it is **arithmetically unexecutable**: B0 carries 19 fixed, verbatim words, and
19 words in 8 s is 2.4 w/s, over every rate ceiling in the kit. The step cut picture out from
under words that span it. It is removed from §5.

---

## 2 · THE SPINE AT A GLANCE

Durations are authoritative in `BEATS.yaml`; this table exists so the shape can be read in one
look. **b3 and b5 are the two beats no cut may reach.**

| beat | in | dur | what it is | weight |
|---|---|---|---|---|
| **B0** | `0:00` | 12 s | The ordinary moment | low, deliberately |
| **B0b** | `0:12` | 8 s | **Why it matters** — for the audience the rest does not serve | low, plain |
| **B1** | `0:20` | 10 s | The attempt | low |
| **B2** | `0:30` | 14 s | The refusal | medium — **resist inflating it** |
| **B3** | `0:44` | 18 s | **The memory loop** — store, retrieve, act | rising |
| **B4** | `1:02` | 10 s | The human move | tension, played matter-of-fact |
| **B5** | `1:12` | 16 s | **Refused anyway** | **THE PEAK. All of it.** |
| **B6** | `1:28` | 18 s | The answer is a question | release |
| **B7** | `1:46` | 12 s | And then it admits | relief |
| **B8** | `1:58` | 6 s | None of it persisted | cool |
| **B9** | `2:04` | 12 s | **The other way in** — then change the clause | the judge's own question |
| **B10** | `2:16` | 12 s | **Refused again** — the mirror | the answer to it |
| **K1** | `2:28` | 6 s | The loop | — |
| **K2** | `2:34` | 10 s | The stack — AWS ∥ CockroachDB | — |
| **K3** | `2:44` | 6 s | The limit, the rail, the URLs | — |
| **end** | `2:50` | 2 s | End card | — |

`148` s demo · `22` s close · `2` s end card · **`172` s total** · hard stop `174` s ·
ceiling `180` s.

**The two use cases are mirror images and the film's shape is that mirror.** B0–B8: you cannot
**just** use a clause a past incident's blame reaches. B9–B10: you cannot quietly **edit away**
that same clause either. They share a clause version and a precursor, and **R-5 requires both to
be legible in the same frame as the second refusal** — without that, B9 and B10 are merely a second
refusal and the trade this revision makes is a straight loss. See §5.

**Use case two is TWO blocks and that was a live disagreement until 2026-08-16.**
`docs/demo/cr-gate-route-plan.md` §R9 named the same 24 s as three — `B9` 10 s + `B10` 6 s +
`B11` 8 s — and `VO-DEMO-CR.md` and `CLICKS-CR.md` were written to it. Both shapes totalled 24 s,
so the film's arithmetic held either way and no check in the kit could have caught it; **what it
broke is the recording**, because the founder records voice first and then picture and a block
boundary is a place he stops and starts. **Resolved in favour of two**, on `CLICKS.md`'s measured
read chain. `VO-DEMO-CR.md` §0.3 is the ruling. **This file already carried two and nothing in it
moved for the ruling** — only the B10 prohibition below gained its fifth item.

**One in-point moved that nobody should read past:** the close now begins at `2:28`, not `2:00`.
Any document still in-pointing the naming block at `2:00` is describing the pre-revision film.

---

## 3 · THE EMOTIONAL MAP

This is a direction to the founder reading the VO and to whoever cuts the picture. It is not a
suggestion: it is the difference between a film that peaks at 0:30 on the least differentiated
thing we own, and a film that peaks at 1:12 on the only thing a competitor cannot also show.

| beat | weight | the direction |
|---|---|---|
| **B0–B1** | **low, deliberately** | Familiarity, not tension. The viewer must recognise this as ordinary work software before anything is at stake. Read it flat. Nothing in the frame should suggest a demo is happening. |
| **B0b** | **plain, and slower than B0** | The one beat pitched at somebody with no database background. It works because it is plain, so **do not dramatise it** — no lowered voice, no pause for effect. It makes no technical claim at all, which is why it costs an expert nothing. |
| **B2** | **medium — resist inflating it** | A `CHECK` refusing is table stakes; every database can do this. The refusal is *surprising* here but not yet *interesting* — a stranger cannot yet tell correct from broken. **No music sting. No zoom. No "and there it is."** Filmed calm. |
| **B3** | **rising — the film's only tenderness** | Not sympathy for a person; recognition of a fact that outlived everyone who knew it. Two timestamps ten seconds apart do the work. This is where a viewer decides the product is about something. |
| **B4** | **tension, not weight** | The audience knows this move; many have made it. **The shrug, not the villainy.** Matter-of-fact, almost bored. Any relish here reads as a straw man and costs B5 its credibility. |
| **B5** | **THE PEAK. All of it.** | The counter reads zero and it refuses anyway. Deliver the line, then **hold the frame in silence.** The silence is a scripted element with a duration, not a pause the editor may tighten — it is where the viewer works out what just happened, and a viewer who works it out themselves is a viewer who believes it. |
| **B6** | **release** | The defeaters are questions, not a checkbox. The cost of an excuse is proportional to how much it assumes. Warm, unhurried. |
| **B7** | **relief** | It admits. This beat exists for one reason: to prove B2 was not a bug. |
| **B8** | **cool** | Nothing persisted. Deliberately unemotional, and now six seconds rather than ten. |
| **B9** | **the judge's own question, said out loud** | This is a *concession to an objection*, not a new pitch. The register is somebody granting a fair point: fine — then don't use the clause, change it. **No triumph in the voice.** A second climax here would compete with B5 and lose. |
| **B10** | **quiet, and it must not gloat** | The mirror lands by being obvious, not by being sold. Then stop. **The film ends on competence, not on a swell.** |

**The single most likely way to get this wrong is trying to make B0–B3 sad.** There is nobody
to be sad about — the seed says so in its own column, and the incident is a severity, never an
injury. Every second spent reaching for sentiment is stolen from B5.

**A severity, not a person.** Say *"a severity-four stored-energy release during intrusive
work."* Never *"a worker was hurt"*, never *"someone died"*, nothing about a person at all. The
`SYNTHETIC —` prefix stays visible on screen; it is never cropped out to make a frame prettier.

**The second most likely way is letting B9–B10 become a second peak.** They are 24 seconds
arriving after the film's peak has already landed, and their job is to close a hole a judge
would otherwise walk straight into. Played big, they flatten B5 and the film has two climaxes
and no shape.

---

## 4 · WHAT EACH BEAT MUST NOT DO

Per-beat prohibitions. Every one of these has been proposed, in this project or an adjacent
one, by somebody acting in good faith at two in the morning.

**Film-wide, before anything else.** Every refusal on screen came back over HTTP from the
deployed API and carries the SQLSTATE the database produced. No hard-coded refusal text, no
`setTimeout`, no staged screenshot, no mockup, no number typed from memory. A judge who opens
devtools must find exactly what the frame showed. This is not only conscience: the contest's
Functionality requirement says the Project **must function as depicted in the video**, so a
staged refusal is a rules violation and not merely a dishonesty.

* **B0** — must not open on a title card, a logo, an architecture diagram, a terminal or a
  console. Must not put a hard-coded crew, plant name or PPE list on screen to make the form
  look complete: the fields with no column behind them are typed on camera and carry **no**
  provenance chip, and the one with neither renders empty and labelled. The convention that
  makes this checkable is that **every server value carries a provenance chip and nothing typed
  does** — so it must not be broken for the sake of a tidier frame.
* **B0b** — must not name a year, a site, a job title or an injury. The seeded precursor's own
  narrative column records that it **describes nobody**; a spoken sentence giving it a casualty
  would be inventing one to move an audience, which is the one thing this repository has refused
  at every turn. It says *"years ago"* and it names no year. Must not change the picture: nothing
  new appears on screen, because the beat's whole defence is that it makes **no** technical claim.
  Must not be cut to make its 28 words fit — the words are trimmed or the seconds are found; **28
  words in 8 s is 3.5 w/s and nobody speaks at 3.5 w/s.**
* **B1** — must not fake the wait. No `setTimeout`, no synthetic spinner, no cutaway that hides
  the round trip. If the round trip is fast the beat is short, and **that is a better problem
  than a fake one**.
* **B2** — must not be filmed as the climax. No sting, no push-in, no vocal lift. Must not crop
  the network panel out of frame; those two seconds are the cheapest thing in the whole film
  that turns "nice UI" into "real client".
* **B3** — must not say *"vector search"*, must not say *"it just searched its memory"*, and
  must not narrate the retrieval in the **present tense**. The recall already ran; what is on
  screen is its record, and what runs *now* is the third step. Must not claim exhaustion of a
  corpus — what is proven is exhaustion of the retrieval that ran, which is a different and
  weaker thing, and the film does not need the stronger one.
* **B4** — must not re-enact. No fake admin console, no simulated SQL prompt, no client-side
  decrement of the counter, no second press. It is a **reveal** of a beat already in the
  response, and the panel renders that beat's own statement and label strings verbatim.
* **B5** — must not step on the silence, and must not dress the diagnosis up. This beat's own
  evidence grades itself **weaker** than B2's, and that weakening stays on screen: a demo that
  downgrades its own best exhibit is not one anybody believes is faked. Must not offer any
  number here as a product latency.
* **B6** — must not say *"the database refuses a defeater code that was never offered"*; there
  is no foreign key behind that and the refusal is the application's. What is true and better:
  the disposition **pins the digest of the option set the signer was shown**. Must not render a
  global "N/A" escape hatch. Must not claim the model can tell a considered disposition from a
  rubber stamp — **nothing in this data model separates them**, and the honest claim is better:
  it makes the question unavoidable and the worst answer non-representable.
* **B7** — must not caption a run-varying digest as a constant. One digest in this payload is
  stable across runs and may be quoted; the clearance digest is **not**, four runs on
  2026-08-15 produced four different values, and if it were ever stable the rollback proof
  would be broken.
* **B8** — must not say *"nothing was written"*. Something **was** written, and then unwound
  inside one `SERIALIZABLE` transaction, and the payload proves the unwinding with an
  identifier only this run held. Say `persisted false`. **The change-request image is gone from
  this beat** — B9 drives that subject instead of showing it — so B8 must not still be cut to
  include it, and must not run past 6 s waiting for it.
* **B9** — must not render a proposed clause string that came from anywhere but the founder's
  keyboard. The table carries no such string; a plausible one would have to be hard-coded, and
  hard-coding a plausible string is the same class of act as reshaping a seed to match a
  constant. **The wording is typed on camera, into the console's own input, carrying no
  provenance chip** — visibly a human's proposal and never a database claim. Must not present a
  merge control that is not the product's own. Must not put the propagation payload's title on
  screen: it reuses the precursor's identifier while describing a **different** framing, and the
  two must never share a shot. Must not narrate the recall in the present tense — **never** say
  *"watch the same debt block the change request"*; the blame closure already ran, exactly as B3
  says.
* **B10** — must not say *"the clause cannot be changed"*, must not say *"the database won't let
  anyone edit the rule"*, must not say *"the memory is immutable"*, must not say *"you can't
  edit it"*, and — added 2026-08-16 — must not say *"you can't use the clause"* with no scope
  word. **All five are false.** The clause **can** be edited — by disposing of the
  obligation first, which is exactly what the three defeaters on screen are for; and it **can** be
  used, which is what B7 shows on camera thirty seconds earlier, once the obligation is answered.
  The true sentences are *"you can't **just** use the clause"* and *"you can't **quietly** edit it
  away"*, or, if an adverb reads oddly on the day, the pair as *"Use it, or edit it. Not without
  answering the question first"*. **Each scope word is doing all the work of its own half and
  dropping either converts a true statement into a false one.** Must not speak the virulence value
  — it is a column on screen and never in the mouth, because saying it aloud edges toward
  inventing an injury. Must not end on the refusal alone: **the three live defeater prompts are
  on screen or the beat does not run**, because use case two has no admission to mirror B7 with
  and the way through is the only thing standing in for one.
* **K2** — must name only what fired in this request path or was actually applied. Never
  CloudFront, never a CDN, never "edge", never CMEK, never PrivateLink, never "multi-region",
  never a CloudWatch console window on screen, never "vector search found the precursor", never
  changefeeds. The one AWS service exercised elsewhere in the repository but **not** in this
  request path is named on its own line and labelled as such. **And the CockroachDB half must
  not be a flat list**: `VO-CLOSE.md` §7.1 measured that three of its items — one trigger
  function, the recursive-CTE closure, and the ungranted-pair SQLSTATE — did **not** run in the
  filmed request, and the previous `c3` summary in `BEATS.yaml` read as though all of them did.
  That summary is retired here. The two labelled columns are not a style choice.
* **K1 / K2 / K3** — must not drop a service, a feature, a label, a caveat or a concession to
  reach 22 s. **The saving is dwell, speech, and running two sequential cards in parallel, and
  nothing else.** Devpost asks that these be *"on screen (text overlay or slide) so judges can
  confirm them quickly"* and never asks for them narrated. The proof that this is delivery and
  not content: the close's words-per-second **does not move** — 1.64 at 50 s, 1.64 at 22 s.
* **K3** — must not point a camera at the submission metadata file while any field in it is
  unresolved. Must not claim a green lane for this URL: nothing in CI has ever asserted it.
* **end** — must not swell. No logo animation, no music resolve, no "thanks for watching".

**Two openings, recorded here so nobody re-proposes them at 02:00:**

* **Never** open on *"In 2019, a worker was hurt…"* — it leads on an injury no column
  supports, and it leads on the cause rather than on the ordinary moment, which is the
  opposite of what works. **B0b is not a licence to reopen this**: it earns its emotional beat
  by naming nobody and no year, and it arrives *after* the ordinary moment rather than instead of it.
* **Never** lead with *"an open-source agentic memory layer"* — it puts the category before
  the demonstration, and it says the hackathon's own word back at the hackathon. B3 shows the
  memory instead of naming it. The category line belongs in the close, where it is earned.

---

## 5 · THE SCOPE-CUT LADDER — pre-committed, executed top-down, never improvised

If the assembled cut exceeds **`174` s**, cut in this order until it is under. Machine form in
`BEATS.yaml` under `cut_ladder`. **Do not reorder this on the day.** The whole point of writing
it now is that at 02:00 on the day before the deadline nobody is competent to weigh a beat
against the rubric, and everybody is confident they are.

**The previous ladder is void and is replaced whole rather than amended.** Its rank 1 (B8's
change-request cut) no longer exists — this revision spent it, which is the point. Its rank 2
(B0 12 s → 8 s) is arithmetically unexecutable, for the reason §1.3 gives. Its rank 5 targeted a
C4 that no longer exists.

| # | cut | from → to | saves | film after |
|---|---|---|---|---|
| **1** | **B9** — the typing of the proposed wording; arrive on it composed | 12 s → 8 s | 4 s | `168` s |
| **2** | **B6** — two defeaters instead of three; **keep the lattice** | 18 s → 14 s | 4 s | `164` s |
| **3** | **B7** — lose the dwell on the post-merge fields | 12 s → 9 s | 3 s | `161` s |
| **4** | **K3** — the spoken limit; the screen keeps all three lines | 6 s → 4 s | 2 s | `159` s |
| **5** | **B10** — the hold after the mirror line | 12 s → 8 s | 4 s | `155` s |

**Total recoverable: 17 s. Floor: 155 s.**

**Never B3. Never B5.**
B3 is a **rules requirement** — the video "must include footage showing the CockroachDB memory
layer at work" — and it is also the first criterion and the tie-break criterion. B5 is the
product. A cut that reaches either of them is a cut that has gone wrong somewhere else, and the
answer is to find that somewhere else.

**Why the order is what it is.** Rank 1 is the only second in the new material that is
*preparation rather than consequence*: the MoC screen, the shared clause and the shared
precursor all survive it, so **R-5 is untouched**. Ranks 2 and 3 are the same trades the old
ladder made and for the same reasons — rank 2 loses redundancy (two questions carry the point
that the answer is a question, and the cost lattice survives), rank 3 loses dwell, which is the
cheapest thing in any film. Rank 4 gives up the film's last *spoken* concession while the screen
keeps every word of it, which is a real loss to a judge who is listening rather than reading, so
it goes fourth and not first. Rank 5 is floored, and §5.1 says why.

### 5.1 · RULING R-10 — USE CASE TWO IS ATOMIC

> **No step may take B10 below 8 s, and B9 may never be cut without B10.**

A setup with no answer is worse than neither. B9 spends 8–12 seconds raising the judge's
question — *couldn't somebody just rewrite the rule?* — and a cut that keeps the question and
loses the answer has spent the film's most expensive seconds making the audience doubt it. B10's
floor of 8 s exists for the same reason: below it the three live defeater prompts stop being
legible, and a refusal with no way through shown is the one reading of use case two that
actively damages the film.

**If the cut must go past rank 5, the escape hatch is not a sixth step — it replaces ranks 1 and
5.** Drop B9 and B10 **together**, at their full durations, and **restore B8 to 10 s** with its
read-only change-request image:

```
172 - 12 (B9) - 12 (B10) + 4 (B8 back to 10 s)  =  152 s
and with ranks 2, 3 and 4 also taken:  152 - 4 - 3 - 2  =  143 s
```

The film is then back to **one clean use case rather than one and a half**, which is a better
film than a mutilated two. **This is the same 152 s the no-go path lands on** if the change-request
attempt endpoint is never built — so there is exactly one fallback film to rehearse, not two.

### 5.2 · The one sanctioned claim on the banked margin

172 leaves 8 s to the ceiling and 2 s to the hard stop. **Eight of the thirty-two seconds this
revision recovered are banked and not spent**, and there is exactly one thing they may be spent
on: if K2's two labelled columns will not fit **legibly** with all three of their labels at 10 s,
K2 takes 12 s and the bank pays. **It does not get flattened into one ungrouped list** — the
grouping is the honesty, because a flat list would let a service that was never in the request
borrow the credibility of one that was.

**That variant puts the film at exactly `174` s, which is `hard_stop_s`.** It does not *exceed*
it, so the ladder is not triggered — but the margin is gone, and if the variant is taken then
nothing else may run long and the assembled cut is measured before anything else is decided.

---

## 6 · THREE THINGS THAT ARE ON SCREEN REGARDLESS OF THE CUT

These are not beats and they have no duration of their own. They are conditions on the film.

**6.1 The mutating-request disclosure (R-C, as tightened by R-9).** The film contains **exactly
two** mutating requests, both to a `/v1/demo/*` rolled-back endpoint. Within use case one, beats
3 and 4 are revealed from the response already in hand, by controls labelled as reveals. From B2
onward, small and permanent:

> *All four beats arrived in one already-rolled-back SERIALIZABLE transaction. This panel
> reveals them in order as a reading aid; every timing shown is the server's.*

— plus **"one request · four beats · response received `<generated_at>`"** in the panel header.
**Without these the progressive reveal is indistinguishable from faked sequencing**, and this
line is therefore not a caption the editor may drop for a cleaner frame. It is the reason the
reveal is honest. B1's *"One request — four beats came back inside it"* stays true of **that**
request; the strap becomes per-request.

> **RULING R-9 — the second POST is admitted as a TIGHTENING of the fake-detection rule, never
> as a loosening of it.** `FALLBACKS.md` F-11 today says a second POST row means *stop the take*.
> Its force must not be reduced to make room for a beat. The new form is **strictly stronger at
> two requests than the old rule was**, because it adds a condition that does not exist today:
>
> **Exactly two mutating requests in the whole cut. Each is narrated while it is in flight. Each
> is visible in the network panel. Any third row, or either row appearing without its narration,
> stops the take.**
>
> Each returns its own `persisted: false` **measured by the endpoint from its own fingerprint**,
> never claimed by a document. **No committing route is added to this film**, and the demo guard
> that answers `423 Locked` on the seeded subjects stays exactly as it is.

**6.2 The watermark.** On frame for the whole film, naming *this* film's world rather than the
corpus world. Exact string and its justification are recorded by W4 in `ONSCREEN-TEXT.yaml`;
the control is preserved either way and only the noun follows the world on screen.

**6.3 The silence receipt is deliberately out of the demo (R-J).** It carries one field that
is reproduced from spec rather than produced by a column, so showing it honestly costs a STAGED
chip and a caveat sentence, and four seconds cannot carry both. **B3 already discharges the
rules requirement without it.** It stays a linked screen, and the fallback document carries the
one-sentence answer if a judge asks.

---

## 7 · WHAT THIS FILE DOES NOT DECIDE

* **The words.** B0–B10's lines are W2's (`VO-DEMO.md`); K1–K3's are W3's (`VO-CLOSE.md`). This
  file fixes their budgets and their weight, never their phrasing — except the opener in §1.1
  and the strap in §1.2, which are verbatim and binding. **The B9 and B10 lines in the re-cut
  plan §4 are drafts, not rulings**; W6 clears the final wording and W6's REFUSE is final.
* **What is on each frame.** W4 owns `ONSCREEN-TEXT.yaml`; the `on_screen` line in
  `BEATS.yaml` is a one-line summary for orientation, not a specification.
* **The clicks and the typed input.** W5 owns `CLICKS.md`, including what the founder types into
  the change request's own field in B9.
* **What happens if the day goes wrong.** W6 owns `FALLBACKS.md`. One thing is settled here
  because it is a timing question: a retry on a serialisation error is **pressed again on
  camera** and costs its own seconds out of the margin above `total_s`, not out of B5.
* **Whether use case two can be shot at all.** That turns on software this file does not own —
  a demo-safe attempt endpoint that rolls back and proves it, and a console control that calls
  it. If those do not exist on the day, §5.1's escape hatch is taken and the film is 152 s. **The
  defect fix in this revision stands either way**, which is why it did not wait for that answer.
* **Which cut is submitted.** The committed console cut stays untouched this wave. The
  orchestrator decides.
