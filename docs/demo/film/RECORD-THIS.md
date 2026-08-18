<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# RECORD THIS

**The only sheet you need open while you record.** Everything is printed in full at the moment
you need it: every spoken line, every string you type, every click with its timecode. Nothing
here says "see section five" — if a thing is not on this page, you do not need it to record.

**Film:** 172 s · **2:52** · twelve demo blocks, three close cards, one silent end card.
**Origin:** `https://ihuuyvm4z6nfuktihnkey77fpy0eyrhj.lambda-url.ap-southeast-1.on.aws`
**Page:** `<origin>/operator.html#/permit`

---

## 1 · READ THIS ONCE BEFORE YOU START

**1. The film is 2 minutes 52 seconds and it may not grow.** Every block below has a fixed
duration and a fixed word count. If a take runs long you do not talk faster — you go to section
5 and cut one whole step off the ladder. The contest ceiling is 3:00 and a 3:00 cut is a
disqualified cut.

**2. Order of work: voice first, then screen, then match.** Record the whole voice pass
(section 3) block by block, stopping between blocks. Then record the screen pass (section 4) as
one unbroken take. Then lay them together. A block is where you stop and breathe, and the
blocks in section 3 and section 4 are the same blocks with the same names and the same seconds.

**3. Nothing is ever sped up across a claim.** Not the press, not the wait, not the refusal.
The only thing that may ever be trimmed is typing, and both typed strings on this sheet were
already shortened to 17 characters so they would never need it. A cold start that takes nine
seconds is the shot, not a defect.

**4. Two lines survive any bad night, word for word.** If everything else drifts, these do not:

> An attacker who owns the counter does not own the gate.

> Nobody typed that four.

**5. The one thing that ruins a take is moving the mouse during a hold.** There are five
silences in this film that are scripted elements with durations — 0:12–0:20, 1:23–1:28,
2:14–2:16, 2:16–2:18.5, 2:26–2:28. During those, hands come off the mouse. A cursor that drifts
during a silence reads as nervousness and, worse, tells the viewer to go looking for something
that is not there. Almost everything else is recoverable. That is not.

---

## 2 · THE PRE-ROLL

Everything here happens before the red light. Step 4 is the one people get wrong. Step 11
decides which film you are making, and it is decided here and written down — never inside the
take.

**1 · The machine.** Recording monitor at 100 % display scaling. Capture the **display**, not
the window. 2560 × 1440 at 30 fps. Notifications off. Second monitor cleared and its cursor
parked over there.

**2 · The browser.** Maximised, **not** fullscreen — `F11` hides the taskbar clock and the URL
bar, and those are two of the four things that prove this take is real. One window, one tab,
bookmarks bar off, extensions off, clean profile.

**3 · Zoom 250 %.** A measurement, not a preference: at 200 % the SQLSTATE value, the reason set
and the disclosure line all fall below the legibility floor. Then zoom DevTools itself
(`Ctrl` `+` with DevTools focused) until the Network panel's `Name` / `Status` / `Time` column
text is as tall as the page body text.

**4 · Warm the endpoint from a DIFFERENT tab or a different browser.** Once, within 60 seconds
of the take — `POST /v1/demo/gate-run`, or just `GET /v1/health`, which also opens the pool.
**Never warm it from the tab you are about to film.** A press in the filmed tab reveals the
beats and burns the take. Note how long the warm-up took; if it is over about four seconds,
warm it again.

**5 · Warm the change screen's reads from that same second tab, then close the tab.** Open
`<origin>/operator.html#/change`, let it settle, close it. Those four reads cost about 3.5 s
warm and about 6 s cold, and block B9 has 12 s and cannot pay the cold price. Warming a
read-only chain reveals nothing and burns no beat — it is the one thing in this film that can
be warmed for free.

**6 · Close the warm-up tab. Load the film's page fresh:**

```
<origin>/operator.html#/permit
```

Confirm with your own eyes, on the screen and not in a terminal: the header reads
`DEMO-PTW-0001`, the status chip reads `dispositioned`, the action bar reads
`1 obligation outstanding`, and the origin strip at the bottom names the origin you expect.

**7 · Pre-type two and a half fields.** A page reload clears all of them, so this is the last
step a refresh can undo.

Element 1 · *Permit title* — type in full:

```
Cold work — intrusive work inside the isolation boundary
```

Element 3 · *Location on site* — type in full:

```
Within the isolation boundary declared on this permit
```

Element 5 · *Work to be done and its limitations* — type the head **only** and stop. No
trailing space, no full stop, nothing after `until`:

```
Open the guard and inspect; no work until
```

**8 · Do NOT try to pre-type the proposed wording on the change screen.** It cannot be done.
The router tears the screen down on a hash change, so that textarea is destroyed and re-created
**empty** when block B9 mounts the screen inside the take. It is typed on camera or it is not
on screen at all.

**9 · Open DevTools before the take.** Dock it **right**, at a width that leaves the page at
least 760 CSS px — about 640 physical px of panel at a 2560-wide capture. Select **Network**.
Switch **Preserve log ON**. Leave it open. A Network panel opened after a completed request is
indistinguishable from a screenshot, and that is the whole reason this is a rule.

Then check two things at that geometry: the permit screen has not crossed its 720 px breakpoint
(the form sections stay in their wide layout), and the longest evidence line — the beat-2
`message` row — wraps at most once. If either fails, widen the page by narrowing the dock,
**never** by lowering the zoom.

**10 · Confirm the take is legal before you start it.** `POST /v1/demo/gate-run` answers 200
from the warm-up tab, verdict `PROVEN`, four beats. And fix the number of mutating requests
this take will make: **two** on the GO path, **one** on the NO-GO path. There is no third
value, and the number is decided now, not during the take.

**11 · RUN THE GATE AND WRITE THE ANSWER DOWN. This decides which film you record.**

Six conditions. All six, or NO-GO — five of six is NO-GO. Run this; it takes under a minute:

```
URL=https://ihuuyvm4z6nfuktihnkey77fpy0eyrhj.lambda-url.ap-southeast-1.on.aws
CR=dec0de00-000c-4000-8000-000000000001

curl -sS -X POST -H "content-type: application/json" -d "{}" "$URL/v1/demo/cr-gate-run" | grep -o "persisted[^,]*"
curl -sS -o /dev/null -w "%{http_code}\n" "$URL/v1/change-requests/$CR/blocking-checks"
curl -sS "$URL/v1/change-requests/$CR" | grep -o "open_blocking[^,]*"
```

| # | what must be true | how you check it | reading on 2026-08-18 |
|---|---|---|---|
| **G1** | `POST /v1/demo/cr-gate-run` answers, and its own payload says `persisted: false` — measured by the endpoint from a fingerprint taken before and after, never a constant | first command prints `persisted: false` | **The route now exists.** It is declared, and answers `405 · allow: POST` to a GET. **Nobody has sent the POST. You must.** |
| **G2** | `…/blocking-checks` answers `200` | second command prints `200` | **200.** It returns the change request's OWN check `dec0de00-000d-…`, carrying `DEMO-INC-0001`, clause `7.3.2(b)`, severity 4 |
| **G3** | the change request still reads `checks_materialised` with `open_blocking = 1` | third command prints `1` | **1** |
| **G4** | an enabled control that calls G1's endpoint | open the screen and look | **the enabled control is labelled `Attempt the merge`.** `Approve change` is still hard-disabled and is never clicked |
| **G5** | the shared clause **and** `DEMO-INC-0001` are both legible **in the same frame as the refusal** | open the screen and look | **read this off the screen yourself.** The data now carries both; whether they compose in one frame is a geometry question nobody has answered |
| **G6** | the change request's three questions render on the refusal frame | open the screen and look | the three exist live and are the right ones. **Whether they render beside the refusal, you must see for yourself** |

**Why this is in bold on the sheet.** The last written reading of this gate, dated 2026-08-17,
was a NO-GO with four legs failing. Measured against the live origin on **2026-08-18**,
`…/blocking-checks` answers 200 and `/v1/demo/cr-gate-run` is declared — **both routes have
landed since that reading.** That moves G2 and G3 to pass and gives G1 something to test. It
does **not** make the gate a GO: G1 needs one POST that nobody has sent, and G4, G5 and G6 are
read off an open screen with your own eyes, never off a status code.

**And one instruction in the older shot list is now stale.** It names the press at 2:14.0 as
`Approve change`. In the bundle serving the origin today, `Approve change` is still built
disabled and wired to nothing; the control that actually sends `POST /v1/demo/cr-gate-run` is
labelled **`Attempt the merge`**. **Press the one that sends the request. Never press the
disabled one** — a disabled control clicked on camera reads as a broken demo, and its reason
text is the exhibit, not the click.

Write one word before you roll:

* **GO** — 172 s. B9 and B10 shoot. Eight acts. Two POSTs.
* **NO-GO** — 152 s. B9 and B10 do not shoot at all. Six acts. One POST. B8 goes back to 10 s
  with its longer line, which is printed in section 5.

**12 · Roll.** The Network list is cleared **on camera**, as the first act of the take. Do not
clear it now.

---

## 3 · THE VOICE PASS

Read the line in the box. Everything under it is direction, not words — do not read it aloud.
`▌` marks a silence with a length: it is a direction, not a breath.

**How the numbers are said.** `23514` is *two three five one four*. `P0001` is *P, oh oh oh
one*. `00000` is *zero zero zero zero zero* — never "OK", because what is on the screen is a
SQLSTATE. The word `SQLSTATE`, which you say once in the whole film, is *ess-cue-ell-state*.

**Say no timing of the system anywhere.** Not a millisecond, not a round trip, not "fast". The
one interval you speak is *ten seconds* in B3, and both ends of it are timestamps on screen.

---

### B0 · 0:00 – 0:12 · 12 s · 19 words · 1.58 w/s

> This is the form a site supervisor signs before a crew opens a live machine — and in a moment,

▌ Stop. 2.0 seconds of silence.

* **The sentence does not finish here.** It finishes at the top of B1, over the click. End on
  *moment,* the way you end on a comma — the voice stays up. If it falls, the join is dead.
* **Stress:** *this is the form* … *signs* … *live machine*. Flat, unhurried, somebody's
  Tuesday. This is the most ordinary thing in the film and it has to sound like it.
* **Do not** dramatise, and do not fill the 2.0 s — that silence is where B0b lands.

---

### B0b · 0:12 – 0:20 · 8 s · 14 words · 1.75 w/s

> Years ago, a machine that should have been isolated wasn't. The lesson lives here.

▌ 0.4 seconds.

* **Slower than B0, and do not dramatise it.** The line works because it is plain. Every second
  you spend reaching for sadness is stolen from B5.
* **Stress:** *isolated* … *wasn't* … then a small lift on *here*.
* **Do not** add a year, a place, a job, a person or an injury. Not here and not anywhere. The
  seeded incident describes nobody, and its own record says so.

---

### B1 · 0:20 – 0:30 · 10 s · 18 words · 1.80 w/s

> a database is going to refuse to let it through.

▌ 0.5 seconds.

> One request — four beats came back inside it.

* **The first line is the back half of B0's sentence.** Pick it up mid-thought — no fresh
  breath before *a database*, no capital letter in the voice.
* **Stress:** *refuse*. That is the word the whole film turns on.
* **The second sentence is said flatly**, as a fact about the panel on screen. It is a
  disclosure, not a boast. If it sounds impressive, it is wrong.
* **Do not** say anything about how long the request took. The screen's own clock does that.

---

### B2 · 0:30 – 0:44 · 14 s · 25 words · 1.79 w/s

> Refused. 23514 — a CHECK constraint, gate_closed_when_issued, named by the database. It also
> says what would fix it.

▌ 0.3 seconds.

> This panel reveals the other beats in order.

* **Say `23514` as *two three five one four*.** Digit by digit, unhurried.
* **Say the constraint name as it is written** — *gate closed when issued* — four words with the
  underscores swallowed, never spelled out.
* **Read this calm, almost bored.** Every database can enforce a CHECK. If you play B2 as the
  climax the film peaks forty seconds early on the least interesting thing you own, and B5 has
  nowhere left to go. The lift in the voice belongs to B5 and only to B5.
* **Stress:** *named by the database*, and *what would fix it*. Those two are the only phrases
  in the beat that the picture cannot say about itself.
* **Do not** rush the digits. A SQLSTATE read fast is a SQLSTATE nobody catches.

---

### B3 · 0:44 – 1:02 · 18 s · 34 words · 1.89 w/s · **NEVER CUT**

> Stored: a severity-four stored-energy release, 2019 — and the blame it left on this clause.
> Recalled: it already ran; this is its record.

▌ 0.1 seconds — a catch, not a pause.

> Ten seconds later the obligation existed — severity four. Nobody typed that four.

* **This is the fastest beat in the film over the densest picture.** Do not let it accelerate.
  If you are going to under-run any beat, under-run this one.
* **Past tense, always, about the recall.** *It already ran; this is its record.* **Never** say
  "watch it remember", or any present-tense sentence about the retrieval — not once, not as an
  ad-lib. The only thing happening live in this film is the re-derivation on the button press.
* **Stress:** *Stored* … *Recalled* … *already ran* … *Ten seconds*.
* **The last four words are protected and are read alone.** Land *severity four*, take the
  smallest possible beat, then: **Nobody typed that four.** Level, not triumphant. It is a
  measurement, not a punchline.
* **Rising through the beat, and this is the film's one moment of tenderness** — not sympathy
  for a person, there is none in this record, but recognition of a fact that outlived everyone
  who knew it. **Do not reach for sadness.**

---

### B4 · 1:02 – 1:12 · 10 s · 18 words · 1.80 w/s

> Third beat — the shortcut: the projected counter, forced to zero, out of band. Now the CHECK
> is satisfied.

▌ 0.5 seconds.

* **The shrug, not the villainy.** Matter-of-fact, the way you would describe a colleague
  clearing a stuck field. The tension is in the fact, not in your voice.
* **Stress:** *forced to zero*. Then *Now the CHECK is satisfied* said almost as a shrug.
* **Do not** say you are doing this. Nothing is being forged on camera — you are revealing a
  step that already ran inside the transaction. Never "now I'll", never "let me try", never
  "watch me".
* **Only if the payload's own attack string is on screen**, this alternate is cleared —
  its middle clause is the database's own text and may be spoken only while that text is
  visible (18 w · 1.80 w/s):
  *"The counter, forced to zero out of band — what a careless UPDATE leaves behind. The CHECK
  is satisfied."*

---

### B5 · 1:12 – 1:28 · 16 s · 25 words · 1.56 w/s · **NEVER CUT · THE PEAK**

> Refused anyway. P0001 — the gate counted again, from the obligations themselves, and got one.

▌ 1.0 second.

> An attacker who owns the counter does not own the gate.

▌ 1.8 seconds. **The silence is scripted. Do not fill it.**

* **Say `P0001` as *P, oh oh oh one*.**
* **This is the film.** Everything before it is setup and everything after it is proof it was
  not a trick. Drop the pace and drop the volume. This is the only place in 172 seconds where
  you slow down.
* **Say the line once, slowly, and then do not explain it.** No "in other words". No "which
  means". The 1.8 s after it is the beat.
* **Say "the gate", never "the CHECK constraint", for this refusal.** B2 was a declarative
  constraint the database enforces on every path; this is a procedural guard we wrote, running
  inside the database. Collapsing them is the one over-reach available to a person who has been
  saying "the database refused" for ninety seconds.
* **Never say** "tamper-proof", "defence in depth, proven", or "drop the constraint and the
  trigger still refuses". The claim is that an attacker who owns **this counter** does not own
  **this gate**, and nothing wider. Tamper-evident, never tamper-proof.

---

### B6 · 1:28 – 1:46 · 18 s · 34 words · 1.89 w/s

> Not a checkbox — a question: which isolation point was locked, and who verified it at zero?

▌ 0.1 seconds.

> Mechanism-absent costs rank four, a second signer; emergency override dies in twelve hours.
> The engineer answers, and signs.

* **Release.** The film has been refusing for forty seconds and this is a person answering.
  This is the beat where the voice comes back up.
* **Stress:** *Not a checkbox — a question*. Those five words are the clearest thing anybody
  hears in the whole film; give them room. Then let the middle sentence go by at pace — it is a
  list of prices, and the screen carries every one of them. Then slow down again for *The
  engineer answers, and signs.*
* **Never say** "it catches rubber-stamping" or "it proves someone actually read it". Nothing
  in this data model separates a considered disposition from a rubber stamp, and the film says
  so out loud thirty seconds from here.

---

### B7 · 1:46 – 1:58 · 12 s · 15 words · 1.29 w/s

> Admitted. The merge it refused twice now completes.

▌ 0.4 seconds.

> Nothing was overridden — the question was answered.

* **Relief, briefly.** Then straight into B8, which is cool.
* **Stress:** *admitted*, then the whole weight on the last sentence: *Nothing was overridden.*
  That sentence closes the film's argument.
* **⛔ DO NOT SAY "the form turns from blocked to issued", in any wording.** This is not a
  judgement call and there is no option (a). It is a **REFUSE** against the contest Functionality
  rule, filed four times over: `CLAIMS-CLEARANCE.md` D20, D29, O5 and O9, with
  `ONSCREEN-TEXT.yaml`'s `forbidden_on_camera` banning the frame itself. Measured at capture
  stage `04-admitted-and-proven`, **the permit header does not change**: the state chip still
  reads `dispositioned`, `ISSUE` is still disabled, the lock note is still on screen. That is
  correct behaviour — the admission happened inside a transaction that was rolled back — and
  **B8 depends on it.** The only way to make that sentence true on camera is to fake the render.
  The line printed above is the cleared replacement (`CLAIMS-CLEARANCE.md` §7.1, replacement 1).
* **What to do with the cursor.** Keep it on the beat-4 panel rows, which read `permit state
  merged`. The admission and the unmoved lock belong in frame together — that contradiction is
  B8's setup, not a mistake to hide.

*(This block was rewritten 2026-08-18. It previously printed the barred sentence as option (a)
of two and did not print the cleared line at all.)*

---

### B8 · 1:58 – 2:04 · 6 s · 11 words · 1.83 w/s

> Persisted false. One serializable transaction — written, then unwound. Press it yourself.

* **Cool, level and finished — but not final.** The last three words are an invitation and they
  are the most persuasive thing in the beat. Say them to the viewer, not to the screen.
* **Say `persisted false`. Never say "nothing was written".** Something *was* written — a
  disposition id no other writer holds — and then unwound. *Written, then unwound* is not
  optional: without it, "persisted false" can be heard as "nothing happened".
* **On the NO-GO path this block is 10 s and the line is longer.** It is printed in section 5.

---

### B9 · 2:04 – 2:16 · 12 s · 20 words · 1.67 w/s · **GO PATH ONLY**

> Fine. Then don't use the clause — change it.

▌ 0.4 seconds — this is the click landing, not a pause for effect.

> Same paragraph. Same incident behind it. This request asks to edit it.

* **Conversational on *Fine.*** You are taking the objection seriously, not swatting it. That
  one word is the judge's own question, conceded out loud before you answer it.
* Then **flat and quick** through the three short sentences. They are labels, not argument.
* **Never read the proposed wording aloud**, in any form. It is a human's string, typed on
  camera, carrying no provenance chip. The moment you speak it you have made it sound like the
  product's.
* **Past tense about the memory, always.** Never "watch the same debt block the change
  request". Say *Same incident behind it* and let the screen do the rest.
* **Never** say the change request targets the clause. The screen says in writing that no such
  link is asserted, and a narration that contradicts an on-screen caveat is the worst failure
  available in this film.

---

### B10 · 2:16 – 2:28 · 12 s · 20 words · 1.67 w/s · **GO PATH ONLY**

> Refused. Same SQLSTATE — a different constraint guards edits.

▌ 0.6 seconds.

> You can't just use the clause. You can't quietly edit it away.

* **Say `SQLSTATE` as *ess-cue-ell-state*.** This is the only time in the whole film you say the
  word itself, and it costs about two words of mouth time — do not hurry it.
* **First sentence flat and slightly bored.** This is the second time, and the second time
  should sound routine, because routine is the claim.
* **Then the two short sentences slow and level.**
* **Two small words carry this entire beat and dropping either one makes the sentence false:**
  **just** and **quietly**. The clause *can* be edited — by answering the obligation first,
  which is exactly what the three questions on screen are for. And the permit *was* issued on
  that clause thirty seconds ago, in this same film. If either adverb goes missing in a take,
  **the take goes**.
* **Do not lean on "quietly".** It has to be audible, not underlined. Press it and you turn a
  measurement into a boast.
* **Never say** "the same constraint" — it is a different constraint and the same code, and
  that is the whole point.
* **Only if the adverb reads oddly on the day**, this is the single sanctioned substitute
  (19 w · 1.58 w/s). Do not invent a third form:
  *"Refused. Same SQLSTATE, different constraint — this one guards the edit.*
  ▌ 0.6 s
  *Use it or rewrite it — the question comes first."*

---

### k1 · THE LOOP · 2:28 – 2:34 · 6 s · 10 words

> The incident. The retrieval. Ten seconds later, the obligation. Refused.

* **Four fragments landing on three columns.** *The incident* on the left column. *The
  retrieval. Ten seconds later, the obligation* on the middle one — both timestamps are in that
  column, ten seconds apart. *Refused.* on the right, and then stop.
* **The words STORE, RETRIEVE and ACT are on screen in large type and are not spoken.**
* *The retrieval* must stay between *the incident* and *ten seconds later*. Without it, the ten
  seconds attaches to the incident and you have claimed a ten-second response to a years-old
  event.
* **Do not add "…and that's the loop."**

---

### k2 · THE STACK · 2:34 – 2:44 · 10 s · 14 words

> Every line says which. Bedrock is exercised in this repository — not in this path.

* **The dash is a real pause, not a comma.** The last four words are the half a judge does not
  expect and they need the silence in front of them.
* The four words in front of the dash are what make the last four credible. Do not compress the
  sentence into a bare denial.

---

### k3 · THE LIMIT · 2:44 – 2:50 · 6 s · 10 words

> Nothing here separates a considered disposition from a rubber stamp.

* **This is the film's last spoken line and the only one a competitor cannot say.** Level and
  unhurried. It is a concession, and it is the most trustworthy six seconds in the film.
* **The word `here` is not optional.** Without it the sentence is a claim about safety records
  in general, which is not ours to make. A take that drops it is refused.
* **The two URLs on the card are not read aloud.** A judge reads a URL faster than anyone can
  say one.

---

### end card · 2:50 – 2:52 · 2 s · **SILENT**

Two seconds, no voice. Do not record anything for it and do not be tempted to fill it. It is a
held frame with the product name and one sentence, and it is the first and only time the name
appears in the film.

---

## 4 · THE SCREEN PASS

One unbroken take. **Every physical act you perform is numbered 1 to 8 below, and this sheet's
numbering is the only numbering used here** — the older shot lists count them two different
ways, so ignore any "click 6" you remember from elsewhere and use these.

**Four things stay in frame from the first frame to the last:** the URL bar, the taskbar clock,
DevTools docked right with Network selected, and the synthetic watermark strip.

**The rules that bind every second of this pass:** no cut between a press and the render, ever.
The cursor moves continuously — a cursor that jumps is read as a cut. No window is resized, no
zoom is changed, no dock is moved once the take starts. Nothing is rounded and nothing is sped
up.

---

### B0 · 0:00 – 0:12 · act 1

**On screen at the in-point:** scroll position 0, the top of the document — watermark strip,
the `CONTROL OF WORK` app bar, the left rail, the permit-type selector on **Cold work**, then
the header block: `DEMO-PTW-0001`, the status chip reading `dispositioned`, the validity dates,
`Gate epoch 1`, `Chain head 2`.

| time | what you do |
|---|---|
| 0:00 – 0:03.5 | **Cursor completely still**, parked in the header's dead space to the right of the status chip. Nothing moves while the opening sentence runs. |
| 0:03.5 – 0:05 | Wheel scroll **down**, three notches, slowly, into the form's **section 5**, *Description of work to be done and its limitations*. The pre-typed title and location pass through frame. |
| 0:05 – 0:05.5 | **Act 1.** Cursor travels to the *Work and its limitations* textarea and single-left-clicks into it. The caret appears at the end of the pre-typed text. |
| 0:05.5 – 0:08 | **Type this on camera**, at a normal human rate. It begins with a space, because it joins the pre-typed head: |

```
 verified at zero
```

The complete field then reads `Open the guard and inspect; no work until verified at zero`,
which does not wrap.

| time | what you do |
|---|---|
| 0:08 – 0:10.5 | Wheel scroll **down**, four notches, past the hazard card (a pass-through — B3 comes back to it), past the form's **section 7** with the clause and its `LOTO` / `ZERO_ENERGY` chips, past **section 8** reading *not carried by this deployment*, past the signature block. |
| 0:10.5 – 0:12 | Cursor comes to rest **on the `ISSUE ▸` button** and stops. |

**Do not touch:** `Enter` or `Tab` in the textarea — leave the caret blinking in the field.
`Display copy` — it opens a print view and costs the take. Do not dwell on the hazard card here.

---

### B0b · 0:12 – 0:20 · **NO CLICK, NO KEYSTROKE, NO SCROLL**

**This block has no picture of its own and that is deliberate.** The frame is exactly where B0
left it, and your whole job for eight seconds is to do nothing visible.

| time | what you do |
|---|---|
| 0:12 – 0:20 | **Cursor still, resting on `ISSUE ▸`.** No wheel, no travel, no hovering away and back. The caret blinking in the work field is the only thing moving in the frame, and it is enough. |

**This is the longest continuously static frame in the film**, so it is also where a viewer
actually reads the watermark.

**Do not:** fill the silence with movement. Do not pre-hover the module tab. Do not scroll to
"show" what the words describe — the words describe the world, not the screen. **Do not click
early:** the whole point of these eight seconds is that the press lands at 0:20.

---

### B1 · 0:20 – 0:30 · acts 2 and 3 · **THE FIRST MUTATING REQUEST**

| time | what you do |
|---|---|
| 0:20 – 0:21 | Cursor travels **right, into DevTools**, to the Network toolbar's **Clear** control. |
| 0:21 | **Act 2 — click Clear.** The request list empties on camera. This is the proof that nothing was preloaded. |
| 0:21 – 0:22.5 | Cursor travels **back left, continuously**, to `ISSUE ▸`. A cursor that jumps here is a cut. |
| 0:22.5 | **Act 3 — click `ISSUE ▸`.** Single left click. |
| 0:22.5 – 0:30 | **Cursor does not move again until the answer lands. Hands off the wheel.** |

**A load happens here and a pause is expected.** The button's own label becomes `Issuing… 0.4 s`
and the tenths count up on a real clock driven by the real request. Warm this costs about two
and a half seconds; cold it can cost up to about nine. **Do not cut, do not press again, do not
speed it up.** One row appears in DevTools — `gate-run`, `POST` — and its Status, Size and Time
columns fill as the answer lands.

**Do not:** talk over the last third of the wait. Let it land.

---

### B2 · 0:30 – 0:44 · **NO CLICK, NO KEYSTROKE**

| time | what you do |
|---|---|
| 0:30 – 0:31 | Wheel scroll **down**, two notches, until the lock note, the disclosure strip and the refusal banner are in frame together. |
| 0:31 – 0:37 | **Cursor parked and still**, off to the right of the banner. The frame does the work. |
| 0:37 – 0:41 | Cursor travels slowly down the banner **as a pointer**: `SQLSTATE 23514` → `constraint gate_closed_when_issued` → the CHECK predicate row → the `message` row. It points. It does not click and it does not select text. |
| 0:41 – 0:44 | Cursor moves right and rests beside the DevTools row for about two seconds: `gate-run · 200 · bytes · time`. **No tab is clicked.** |

**Hold the reason set legibly.** It names the clause and the precursor event by id, and those
are the two identifiers a judge is asked to recognise again at 2:16. Someone who is going to
match them later has to see them here first, so the pointer rests on that line rather than
skating past it.

**Do not:** open the Headers or Response tab yet. Do not inflate this beat.

---

### B3 · 0:44 – 1:02 · **NO CLICK · NEVER CUT · this is the most important frame in the film**

| time | what you do |
|---|---|
| 0:44 – 0:46 | Wheel scroll **up**, four notches, to the form's **section 6**, *Hazard identification*. Settle with the card's header at the top of the page area. **Nothing is scrolled again once this frame is composed.** |
| 0:46 – 0:50 | Cursor rests on the precursor block: `DEMO-INC-0001`, `14 March 2019`, the `SYNTHETIC —` title, the severity rows, the source document and its digest. |
| 0:50 – 0:54 | Cursor moves to the projection block — *the severity on this obligation was not chosen by whoever raised it* — and the source citation beneath it. |
| 0:54 – 0:59 | Cursor travels down the three labelled rows in order: **RECALLED** → **SHOWN TO** → **STATUS**. |
| 0:59 – 1:02 | Cursor rests on the interval at the foot of the card: `03:00:00Z` → **10 s** → `03:00:10Z`. |

**Hold `DEMO-INC-0001` legibly.** This is the only place in the film where it appears with its
title and its date, and it is what makes the second refusal the *same* memory rather than an
unrelated one.

**Do not:** crop the `SYNTHETIC —` prefixes to prettify the frame. Do not click — a click here
selects text and adds nothing.

---

### B4 · 1:02 – 1:12 · act 4

| time | what you do |
|---|---|
| 1:02 – 1:04 | Wheel scroll **down**, four notches, back to the transcript, until the reveal control sits in the lower third of the page area with the refusal banner above it. |
| 1:04 | **Act 4 — click the beat-3 reveal.** |
| 1:04 – 1:05 | The panel paints in about 30 ms. **No request is made, and the Network panel proves it** — the list still holds exactly one row. |
| 1:05 – 1:12 | Cursor travels to the panel's `statement` row and rests there, beside the payload's own label for the beat and its observed line. |

**Do not:** wait for the header counter to tick from 1 to 0. It never does, and it is correct
that it never does. Do not describe this as something you are doing. **And nothing else opens:**
no second window, no admin console, no `psql` prompt, no terminal, no SQL typed by anybody. The
forged `UPDATE` appears on camera exactly once, and only as text the server sent back.

---

### B5 · 1:12 – 1:28 · **NO CLICK · NEVER CUT · THE PEAK**

**No scroll during this beat if the panel fits.** If the refusal rows sit below the fold, make
the one wheel notch at 1:12, before the line — never during it.

| time | what you do |
|---|---|
| 1:12 – 1:16 | Cursor moves up the panel to `SQLSTATE P0001` and `mainline.fn_permit_merge_gate`, and rests. |
| 1:16 – 1:20 | Cursor moves to the `message` row and holds on the database's own sentence about the re-derived count. |
| 1:20 – 1:23 | Cursor moves to the weakening rows and holds: the `parsed` chip and its note, `diagnosis none`, the capability-gap reason set, `not computable`. |
| 1:23 – 1:28 | **Cursor stops. Hands off the mouse.** Hold the frame with `P0001` and the message both legible. |

**Leave the weaker diagnosis on screen.** At the film's loudest moment the panel grades its own
evidence down, and a demo that downgrades its own best exhibit is not one anybody believes is
faked.

**Do not:** add an overlay here, cut to DevTools mid-line, or let the pointer run past the hold.

---

### B6 · 1:28 – 1:46 · **NO CLICK, NO KEYSTROKE**

| time | what you do |
|---|---|
| 1:28 – 1:30 | Wheel scroll **up**, two notches, to the signature block. Cursor rests on **row 10 · Acceptance** — `demo.signer`, the timestamp, the receipt digest, `Obligations shown 1`. Then one deliberate move up to **row 9 · Issue**, which reads `unsigned`. |
| 1:30 – 1:38 | Wheel scroll **down** to the three question cards. Cursor rests about 2.5 s on each, in order. |
| 1:38 – 1:46 | Cursor moves to the cost table and rests on two rows: `mechanism_absent` (min rank 4, second signer, foreign org, predicate, re-assert) and `emergency_override` (min rank 5, max TTL 12 h). |

**If the three questions are not on the permit screen on the day**, do not go looking for them:
stay on the signature block through 1:34, then scroll up to the hazard card's `STATUS` row —
`OPEN — unanswered on this permit` — and rest there. In that case the questions are not filmed
and the voice must not describe them, and the block trims to 14 s.

**Do not touch:** the radio buttons. Do not select an option and do not type a rationale.
Selecting one would say in pictures *"I chose this answer and then the permit was admitted"* —
and the payload does not return which option mattered, so nothing on screen could support it.
Do not call the three a checklist, and do not say any of them is inapplicable — there is no
"N/A" in this vocabulary.

---

### B7 · 1:46 – 1:58 · act 5

| time | what you do |
|---|---|
| 1:46 – 1:48 | Wheel scroll **down** to the foot of the transcript, until the second reveal control is in the middle of the page area. |
| 1:48 | **Act 5 — click the beat-4 reveal.** |
| 1:48 – 1:49 | The admission panel **and** the run footer paint together in about 33 ms. No request is made — the Network list still holds one row. This is why the next block needs no click at all. |
| 1:49 – 1:58 | Cursor travels down the admission rows and rests: `ISSUE ADMITTED`, `SQLSTATE 00000`, the disposition uuid, `disposition kind applied`, `open_blocking after the signature 0`, the server-computed clearance digest, `permit state merged`. |

**Keep the cursor on the panel rows for the whole line — never on the permit header.** The header
does not change when the admission lands and is not supposed to: the chip still reads
`dispositioned` and `ISSUE` is still disabled, because the admission happened inside a
transaction that was rolled back. The words you are speaking are true of `permit state merged`
in this panel and false of the header six inches above it.

**Do not:** caption the clearance digest as a constant. It is different on every run, and if it
were ever stable the rollback proof would be broken.

---

### B8 · 1:58 – 2:04 · **ONE POINTER MOVE, NO CLICK**

| time | what you do |
|---|---|
| 1:58 – 2:04 | Cursor travels down the footer rows, legibly, without lingering: `VERDICT PROVEN` · `isolation SERIALIZABLE` · `transaction rolled_back` · the two identical logical timestamps · the savepoints · **`this run persisted anything · false`** · **`minted disposition after rollback · <uuid> · 0 rows`** · `permit row unchanged · true`. |

**Six seconds is ten rows.** Two of them carry the beat — `persisted anything · false` and the
minted disposition with its zero row count. The rest are travelled past, not dwelt on. If the
line runs long, finish the travel in silence rather than over-running into the next block.

**Do not:** switch modules here to get a head start. The switch is the next block's first act,
on camera, with the URL bar in frame — moving it earlier steals the shot that proves the host
never changed.

---

### B9 · 2:04 – 2:16 · acts 6, 7 and 8 · **GO PATH ONLY · THE SECOND AND LAST MUTATING REQUEST**

**If the gate in pre-roll step 11 was a NO-GO, this block and the next do not exist.** Go to
section 5.

| time | what you do |
|---|---|
| 2:04.0 – 2:05.5 | Cursor travels **up to the app bar**, continuously, to the tab `Management of change`. This is a long travel across the page and **it must not jump** — the URL bar is in frame the whole way and the travel is what proves there was no cut. |
| 2:05.5 | **Act 6 — click the module tab.** The hash becomes `#/change` in the URL bar, on the same origin. The host in frame does not change. |
| 2:05.5 – 2:09.0 | **A load happens here and a pause is expected — about 3.5 s warm. Touch nothing while it runs.** The screen paints in four visible stages as its four reads land, and **they do not fill top to bottom** — the approval bar paints second even though it sits near the bottom. Let the page settle instead of chasing it with the cursor. Four new rows appear in DevTools, and one of them may be a `404`. Leave it visible. |
| 2:09.0 – 2:10.5 | Wheel scroll **down** to the change screen's **section 3**, *Modifications to operating procedures*, until the *Clause of record* block and the *Proposed wording* box are in frame **together**. Cursor rests one beat on the clause quote so its returned text and its `SYNTHETIC —` prefix are readable. **This dwell is never shortened, whatever else in the block is under pressure.** |
| 2:10.5 – 2:11.0 | **Act 7.** Cursor travels to the *Proposed wording* textarea and single-left-clicks into it. The caret appears in an **empty** box. |
| 2:11.0 – 2:13.5 | **Type this on camera, in full**, at the same rate you typed in B0 — 17 characters in 2.5 s: |

```
Isolate and lock.
```

No `Enter`, no `Tab`. Leave the caret blinking in the box; it stays there for the rest of the
film.

| time | what you do |
|---|---|
| 2:13.5 – 2:14.0 | Cursor travels to the control that sends the attempt. **In the deployed bundle today that control is labelled `Attempt the merge`.** A travel, not a scroll, if the geometry allows it. |
| 2:14.0 | **Act 8 — click it.** Single left click. **This is the film's second and last mutating request.** |
| 2:14.0 – 2:15.0 | In flight. The control shows its own real pending state and one row appears in DevTools — `cr-gate-run`, `POST`. **Cursor does not move. Hands off the mouse.** The tail of the spoken line finishes here. |
| 2:15.0 – 2:15.5 | Still in flight. Silence, and nothing on screen is chased. |
| 2:15.5 – 2:16.0 | **The refusal paints and the frame composes itself.** No movement, no scroll, no click. The next block opens on this frame half a second later. |

**Do not touch `Approve change`.** It is disabled, wired to nothing, and clicking it on camera
reads as a broken demo. Its reason text is the exhibit; the click is not.

**Do not press the attempt twice.** A second press is a third mutating row and it kills the
take.

**Do not touch the other two boxes** — *Technical basis* and *Reference the source of the
change*. They are empty on purpose and their notes are part of the exhibit. Typing into the
source box in particular would suggest the obligation came from what you typed, when the
screen's own note says it came from the database's reverse lookup.

**Do not** click *Compare with clause of record*, however tempting. It is a real control and it
makes no request, but there is no room for it in these twelve seconds.

**Do not** scroll past the relation note to reach the box faster, and **do not say the change
request targets the clause** — the screen denies that in writing while you are looking at it.

---

### B10 · 2:16 – 2:28 · **NO CLICK, NO KEYSTROKE · GO PATH ONLY**

**The refusal is already on screen** — it painted at 2:15.5, inside the previous block, and has
been up for half a second when this one starts. The cursor is where you left it, on the control
you pressed, and your hands are off the mouse.

| time | what you do |
|---|---|
| 2:16.0 – 2:18.5 | **Nothing. Hands off the mouse.** Nothing is chased, pointed at or scrolled. The first spoken word names a value that is already in the frame. |
| 2:18.5 – 2:22.0 | Cursor travels down the refusal band **as a pointer**: `SQLSTATE 23514` → `constraint cr_gate_closed_when_merged` → the predicate → `open_blocking 1`. It points; it does not click or select. |
| 2:22.0 – 2:26.0 | Cursor moves **left and up, without leaving the frame**, to the three question cards and rests across them. |
| 2:26.0 – 2:28.0 | **Cursor stops. Hold.** The refusal and the three questions both legible, the mirror line spoken over the still frame. |

**The 2.5 s of stillness that opens this block is not dead air and is not somewhere to reclaim
a second.** Neither is the silence at the tail. Both are scripted elements with durations.

**These must be in frame together, and if they will not compose, this block does not shoot:**
the refusal, the clause `7.3.2(b)`, `DEMO-INC-0001`, the three questions, the URL bar, the
clock, and a Network panel showing exactly two `POST` rows for the whole film. Do not solve a
composition problem by zooming out below the pre-roll's floor, by narrowing the dock past
760 CSS px, or by cutting between two frames and calling it one.

**Do not touch:** the radio buttons or the citation fields. The temptation is at its worst
here — a refusal on screen, three answerable questions beside it, a text field under each.
Filling one in stages the exact act the block says the system will not let anyone do quietly.

**Do not switch back to the permit module.** The take ends on this screen.

---

### The close · 2:28 – 2:52 · **KEEP RECORDING**

The three closing cards and the end card are **text over live picture, never a stock slide** —
the overlays are composed in the edit, but the picture underneath is the picture you are
recording right now. **So do not stop the recording at 2:28.**

| time | what you do |
|---|---|
| 2:28 onwards | **Hands off the mouse. Nothing moves.** Hold the last frame, still and untouched, for at least another thirty seconds so the edit has clean picture to lay all four cards over. Then stop the recorder. |

**Do not** cut to black, do not close DevTools, do not navigate away, and do not tidy anything
up while the recorder is running. Whatever is on screen when you stop is what a judge sees
behind the closing cards.

---

## 5 · IF SOMETHING GOES WRONG

### What is safe to re-take on its own

* **Any voice block.** The voice pass is recorded block by block, so a fluffed line costs you
  that block and nothing else. Re-read it and move on.
* **Nothing in the screen pass.** The screen take is unbroken by design.

### What forces a re-take of the whole screen take

* **Any cut between a press and a render.** There is no exception to this anywhere in the film.
* **A third mutating request** — any `POST` row beyond the ones you planned (two on the GO path,
  one on NO-GO). Also: either planned `POST` landing while you are talking about something else.
* **The cursor jumping** instead of travelling. A viewer reads a teleporting cursor as a cut.
* **Changing zoom, dock width or window size inside the take.** It reflows the page under a
  claim, and nobody watching can tell that from an edit.
* **Clicking the disabled `Approve change` control**, or selecting any radio button, or typing
  into any citation field.
* **A missing scope word in B10** — "just" or "quietly". If either goes, the take goes.

### The press takes seven to nine seconds and nothing seems to be happening

That is a cold start. Nothing is broken: the function has not been called for a while, so it is
building a container and opening its first connection before it can ask the database anything.

> **Say this over the wait, calmly, with no number in it:** "That's a cold start. Nothing has
> called this function for a while, so it's building its container and opening its first
> connection to the database before it can even ask the question. This is the real thing waking
> up — I'd rather show you that than cut it."

**Do not cut. Do not press again** — a second press is a second `POST` row and it kills the
take. Keep the pending clock and the single in-flight row in the same frame. **If the wait
passes about twelve seconds**, stop expecting an answer: the platform cuts the call at fourteen,
and what you are in is the transport failure below, not a cold start.

### `40001` comes back

Not a refusal — the gate never got to say anything. The database aborted the whole transaction
rather than let two writers interleave.

> **Say this, and then press again on camera, in the same unbroken take:** "Four-oh-oh-oh-one.
> That's a serialization failure — the database aborted the whole transaction rather than let
> two writers interleave under SERIALIZABLE. Nothing was written, nothing was decided, and it
> does not re-send a merge on my behalf. So I press it again."

Two `POST` rows are legitimate here **because the first one is on screen failing**. Never call
it a refusal. Never say the system "retried" — at this layer it did not.

### The verdict comes back `NOT PROVEN`, or beat 4 skipped

The first three beats will look exactly as correct as ever, which is why this one is dangerous.

> **Say this, reading the payload's own reason off the screen rather than paraphrasing it:**
> "Beat four skipped, so this run is NOT PROVEN — and it says so itself, there, with the reason
> in its own words. I'll run it again. This endpoint persists nothing, so nothing is left
> half-done."

### The request does not complete at all

> **Say this:** "That didn't complete. I'm not going to narrate a refusal over a request that
> never got an answer — let me press it again."

Press again on camera, once. If it fails twice, the shoot moves. **Never** describe a transport
failure as a refusal: a refusal has a SQLSTATE, a constraint and a reason set, and a failed
request has none of the three.

### A `423 Locked` comes back

That is the demonstration protecting itself, not a gate refusal — its message is about a lock,
not about an obligation. **Never render it as a refusal.** Stop and check that the button you
pressed is the one that posts to `/v1/demo/gate-run`.

### The permit header does not change after the admission

It is not supposed to. The chip still reads `dispositioned`, `ISSUE` is still disabled, the
lock note is still there — because the admission happened inside a transaction that was rolled
back, and a screen that flipped to "issued" would be asserting a state the database does not
hold. **That contradiction is the point of B8, so keep it.** Never say "the permit is now issued."

The B7 line *the form turns from blocked to issued* is **barred**, and there is nothing to
settle. It is a REFUSE against the contest Functionality rule in four places —
`CLAIMS-CLEARANCE.md` D20, D29, O5, O9 — and `ONSCREEN-TEXT.yaml`'s `forbidden_on_camera` bans
the frame as well as the sentence. The permit header does not change when the admission lands,
and B8 depends on that. §3's B7 block prints the cleared replacement; read it from there.

### The live origin is down

Two answers, and neither of them is a mock.

**Postpone.** This is the default and it costs less than it feels like it costs.

**Or film against the local node and say so on screen**, in the first fifteen seconds, before
anything else:

> "One thing before I start: this is running against a CockroachDB node on this machine, not
> against the deployed URL — that origin is down right now. The strip at the bottom of the page
> says so, and it says so because the server stamps its own header on every response. The
> database, the migrations, the constraint and the trigger are the same ones; the hop is local."

Never crop the origin strip, never suppress the header, and never let a local take be described
anywhere as the deployed one. If the page header ever reads `TRANSPORT REPLAY`, stop — that is
a stop condition, not a fallback.

### The gate in pre-roll step 11 came back NO-GO

**This is a legitimate film, not a collapse.** It is shorter, legal, and everything that makes
the film good survives.

* B9 and B10 **do not shoot at all**. Not shortened, not merged into B8, not described in
  voice-over over a screen that cannot show them.
* The take is **six acts and one `POST`**. Acts 7 and 8 do not happen and act 6 moves back into
  B8's second half.
* **B8 goes back to 10 s** and gets its longer line (19 w · 1.90 w/s):

  > Persisted false. One serializable transaction, rolled back — the disposition it minted was
  > written, and unwound. Press it again yourself.

  Its second half is a read-only look at the change request, shown and not driven, unnarrated.
* The film runs **152 s · 2:32**. Every AWS service and every CockroachDB feature is still named
  on the closing cards.
* If a judge asks live, the honest answer is already cleared: *"There is no merge route for it
  yet, so I'm telling you about it rather than driving it."*

**What must never happen to turn a NO-GO into a GO:** never build a committing public route to
make the beat work, never enable the approve control ahead of the endpoint, never grant the API
a write it does not have, and never narrate the change request as if it had been driven.

### The whole cut runs long

**Do not talk faster and do not shave holds.** The steps below are pre-committed, in this order,
executed from the top until the cut is under 2:54. Never improvised, never reordered at 02:00.

| step | what goes | saves | film after |
|---|---|---|---|
| 1 | **B9** 12 s → 8 s. The typing of the proposed wording goes; arrive with the box already filled. **Check first** that the box can actually hold text when the screen mounts — it could not on the last measurement. | 4 s | 2:48 |
| 2 | **B6** 18 s → 14 s. One of the three permit questions goes. Two carry the point. The cost table stays — it is the half a competitor cannot show. | 4 s | 2:44 |
| 3 | **B7** 12 s → 9 s. The dwell on the post-merge fields goes. `ADMITTED` is the whole job of the beat; three seconds of dwell is not. | 3 s | 2:41 |
| 4 | **k3** 6 s → 4 s. The **spoken** limit goes; the screen keeps all three of its lines and the whole tools panel. | 2 s | 2:39 |
| 5 | **B10** 12 s → 8 s. The hold after the mirror line goes. The three questions stay on screen — without them the beat ends on a wall. | 4 s | 2:35 |

**B3 and B5 are never cut, at any step, for any reason.** B9 may never be cut without B10 — a
setup with no answer is worse than neither. If the cut has to go past step 5, drop B9 and B10
**together** and restore B8 to 10 s.

### The six sentences you will reach for when a take is going badly

They are banned exactly because that is when the reaching happens.

| never say | true instead |
|---|---|
| "It's PROVEN" over a run that did not print it | Read the verdict off the screen. `PROVEN` only when the failures list is empty. |
| "Watch it remember", or anything present-tense about the retrieval | The recall already ran and you are looking at its record. What runs now is the re-derivation on the press. |
| "Our agent decided to block it" | No model is in this path. It is a CHECK constraint and a procedural gate, and that is the interesting part. |
| "Tamper-proof", or "split-view resistant" in any form | Tamper-evident, never tamper-proof. |
| "It refuses in milliseconds", or any product latency | Say nothing about speed. There is no p50, no p99 and no load profile in this repository. |
| "It catches rubber-stamping" | Nothing here separates a considered disposition from a rubber stamp. It makes the question unavoidable and the record precise. |

**And three more the second use case adds:** never drop the scope word from the mirror line;
never say "and there is no way through" when three ways are on screen; and never point at the
cost table on the change screen and call it the change request's — it is read against the
permit's check and the screen says so.

**And the one that is not a sentence but an act:** never show a recorded refusal as though it
were live. Nothing on this sheet does it, and if anything ever does, it is wrong.
