<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# SPINE — the prose half of the spine

**W1 · story-and-script · 2026-08-15**
Machine-readable half: [`BEATS.yaml`](BEATS.yaml). Direction document:
[`../story-and-script-plan.md`](../story-and-script-plan.md).

**SCANNER VERDICT (R-B).** `docs/demo/film/` is outside every glob in
`claim_hygiene.py`'s `TARGET_GLOBS`, so the scanner is invoked by hand and its verdict is
recorded here rather than inferred from a green lane:

```
.venv/Scripts/python.exe scripts/demo/claim_hygiene.py --check \
    docs/demo/film/BEATS.yaml docs/demo/film/SPINE.md

  scanned 2 file(s) against 21 rules
  claim hygiene OK
  exit 0
```

**VERDICT: PASS — and it is a pass the scanner had to be talked into.** The first run went
**red three times** on these two files: two `HYG-sha-literal` hits on a tree reference written
into the headers, and one `MNC-17-agentic-memory-lead` hit in §4, where a forbidden opener was
quoted on a source line whose negation marker had wrapped onto the line above. All three were
fixed **in these files, never in the scanner**. Recorded because a hygiene verdict that has
never gone red asserts nothing — and because the third one is a real trap for the five workers
writing behind me: **the negation exemption is line-scoped, so a `never` that wraps away from
the phrase it governs stops exempting it.** Keep the ban and the banned phrase on one source
line.

---

## 0 · WHAT THIS FILE IS, AND WHAT IT IS NOT

`BEATS.yaml` owns every **number**. This file owns every **judgement**: the words that open
the film, where the weight sits, what each beat is forbidden to do, and the order things get
cut in when the assembled cut runs long. Where the two files could be read as disagreeing
about a duration, `BEATS.yaml` wins and this file is wrong.

Nothing here is a measurement. The only kernel-produced values quoted anywhere in W1's two
files are the four SQLSTATEs and the four outcomes of the gate run — `00000` read, `23514`
refused, `P0001` refused, `00000` admitted — read from `evidence/deploy/live-gate-run.json`.
Every elapsed time, byte count, digest and field value on screen is re-derived from the run
that is actually filmed (R-K). **No number in this film is typed from memory.**

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

**How it sits across the two beats it spans, which is the ruling W2 needs:**

| | |
|---|---|
| B0's VO budget | 24 words (`0` → `12` s) |
| Opener length | 29 words |
| Overrun into B1 | 5 words ≈ 2.6 s |
| Click lands | `12.0` s — **while the sentence is still finishing**, exactly as intended |
| Words left in B1 after the opener | 16 − 5 = **11** |

The overrun is designed, not tolerated. A sentence that finishes cleanly *before* the click
turns the click into an illustration of a claim; a sentence still running *through* the click
makes the refusal arrive as an event. W2 writes B1's remaining 11 words to land after the
opener's last syllable, not over it.

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
| `0:00` | Live product. The supervisor's permit form, on the deployed origin, URL bar in frame. |
| `0:12` | A real click, a real in-flight request, a genuine pending state. |
| `0:22` | **The first refusal, inside the supervisor's app** — `23514 · gate_closed_when_issued`. |

"Get to the live demo fast (within the first 20 to 30 seconds)." Live product at `0:00`; first
refusal at `0:22`, inside the window with eight seconds to spare and without spending any of
the running-time margin.

---

## 2 · THE SPINE AT A GLANCE

Durations are authoritative in `BEATS.yaml`; this table exists so the shape can be read in one
look. **b3 and b5 are the two beats no cut may reach.**

| beat | in | dur | what it is | weight |
|---|---|---|---|---|
| **B0** | `0:00` | 12 s | The ordinary moment | low, deliberately |
| **B1** | `0:12` | 10 s | The attempt | low |
| **B2** | `0:22` | 14 s | The refusal | medium — **resist inflating it** |
| **B3** | `0:36` | 18 s | **The memory loop** — store, retrieve, act | rising |
| **B4** | `0:54` | 10 s | The human move | tension, played matter-of-fact |
| **B5** | `1:04` | 16 s | **Refused anyway** | **THE PEAK. All of it.** |
| **B6** | `1:20` | 18 s | The answer is a question | release |
| **B7** | `1:38` | 12 s | And then it admits | relief |
| **B8** | `1:50` | 10 s | None of it happened | cool |
| **C1** | `2:00` | 12 s | The loop, named | — |
| **C2** | `2:12` | 16 s | The AWS surfaces | — |
| **C3** | `2:28` | 14 s | The CockroachDB surfaces | — |
| **C4** | `2:42` | 8 s | The honest limit | — |
| **end** | `2:50` | 2 s | End card | — |

`120` s demo · `50` s close · `2` s end card · **`172` s total** · hard stop `174` s ·
ceiling `180` s.

---

## 3 · THE EMOTIONAL MAP

This is a direction to the founder reading the VO and to whoever cuts the picture. It is not a
suggestion: it is the difference between a film that peaks at 0:22 on the least differentiated
thing we own, and a film that peaks at 1:04 on the only thing a competitor cannot also show.

| beat | weight | the direction |
|---|---|---|
| **B0–B1** | **low, deliberately** | Familiarity, not tension. The viewer must recognise this as ordinary work software before anything is at stake. Read it flat. Nothing in the frame should suggest a demo is happening. |
| **B2** | **medium — resist inflating it** | A `CHECK` refusing is table stakes; every database can do this. The refusal is *surprising* here but not yet *interesting* — a stranger cannot yet tell correct from broken. **No music sting. No zoom. No "and there it is."** Filmed calm. |
| **B3** | **rising — the film's only tenderness** | Not sympathy for a person; recognition of a fact that outlived everyone who knew it. Two timestamps ten seconds apart do the work. This is where a viewer decides the product is about something. |
| **B4** | **tension, not weight** | The audience knows this move; many have made it. **The shrug, not the villainy.** Matter-of-fact, almost bored. Any relish here reads as a straw man and costs B5 its credibility. |
| **B5** | **THE PEAK. All of it.** | The counter reads zero and it refuses anyway. Deliver the line, then **hold the frame in silence.** The silence is a scripted element with a duration, not a pause the editor may tighten — it is where the viewer works out what just happened, and a viewer who works it out themselves is a viewer who believes it. |
| **B6** | **release** | The defeaters are questions, not a checkbox. The cost of an excuse is proportional to how much it assumes. Warm, unhurried. |
| **B7** | **relief** | It admits. This beat exists for one reason: to prove B2 was not a bug. |
| **B8** | **cool** | Nothing persisted; the obligation is still there. Deliberately unemotional. **The film ends on competence, not on a swell.** |

**The single most likely way to get this wrong is trying to make B0–B3 sad.** There is nobody
to be sad about — the seed says so in its own column, and the incident is a severity, never an
injury. Every second spent reaching for sentiment is stolen from B5.

**A severity, not a person.** Say *"a severity-four stored-energy release during intrusive
work."* Never *"a worker was hurt"*, never *"someone died"*, nothing about a person at all. The
`SYNTHETIC —` prefix stays visible on screen; it is never cropped out to make a frame prettier.

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
  identifier only this run held. Say `persisted false`. Must not narrate the change request as
  being blocked on camera — it appears once, read-only, with the approve control rendered
  disabled and the obligation named as the reason.
* **C2 / C3** — must name only what fired in this request path or was actually applied. Never
  CloudFront, never a CDN, never "edge", never CMEK, never PrivateLink, never "multi-region",
  never a CloudWatch console window on screen, never "vector search found the precursor", never
  changefeeds. The one AWS service exercised elsewhere in the repository but **not** in this
  request path is named on its own line and labelled as such.
* **C4** — must not point a camera at the submission metadata file while any field in it is
  unresolved. Must not claim a green lane for this URL: nothing in CI has ever asserted it.
* **end** — must not swell. No logo animation, no music resolve, no "thanks for watching".

**Two openings, recorded here so nobody re-proposes them at 02:00:**

* **Never** open on *"In 2019, a worker was hurt…"* — it leads on an injury no column
  supports, and it leads on the cause rather than on the ordinary moment, which is the
  opposite of what works.
* **Never** lead with *"an open-source agentic memory layer"* — it puts the category before
  the demonstration, and it says the hackathon's own word back at the hackathon. B3 shows the
  memory instead of naming it. The category line belongs in the close, where it is earned.

---

## 5 · THE SCOPE-CUT LADDER — pre-committed, executed top-down, never improvised

If the assembled cut exceeds **`174` s**, cut in this order until it is under. Machine form in
`BEATS.yaml` under `cut_ladder`. **Do not reorder this on the day.** The whole point of writing
it now is that at 02:00 on the day before the deadline nobody is competent to weigh a beat
against the rubric, and everybody is confident they are.

| # | cut | from → to | saves | film after |
|---|---|---|---|---|
| **1** | **B8's second half** — the change-request cut | 10 s → 6 s | 4 s | `168` s |
| **2** | **B0** — the establishing pan; keep the cursor-on-button frame | 12 s → 8 s | 4 s | `164` s |
| **3** | **B6** — two defeaters instead of three; **keep the lattice** | 18 s → 14 s | 4 s | `160` s |
| **4** | **B7** — lose the dwell on the post-merge fields | 12 s → 9 s | 3 s | `157` s |
| **5** | **C4** — the end card carries the URLs alone | 8 s → 4 s | 4 s | `153` s |

**Total recoverable: 19 s. Floor: 153 s.**

**Never B3. Never B5.**
B3 is a **rules requirement** — the video "must include footage showing the CockroachDB memory
layer at work" — and it is also the first criterion and the tie-break criterion. B5 is the
product. A cut that reaches either of them is a cut that has gone wrong somewhere else, and the
answer is to find that somewhere else.

**Why the order is what it is.** Rank 1 is the beat that is *told rather than driven* — the
only second in the film not backed by something happening on camera. Ranks 2 and 4 are dwell,
which is the cheapest thing to lose. Rank 3 loses redundancy: two questions carry the point
that the answer is a question, and the cost lattice — the half nobody else can show — survives.
Rank 5 is last on purpose: C4 answers the criteria's own **second sentences**, which nothing
else in the film answers, so it goes only when everything above it already has.

---

## 6 · THREE THINGS THAT ARE ON SCREEN REGARDLESS OF THE CUT

These are not beats and they have no duration of their own. They are conditions on the film.

**6.1 The one-transaction disclosure (R-C).** The film contains **one**
`POST /v1/demo/gate-run`. Beats 3 and 4 are revealed from the response already in hand, by
controls labelled as reveals. From B2 onward, small and permanent:

> *All four beats arrived in one already-rolled-back SERIALIZABLE transaction. This panel
> reveals them in order as a reading aid; every timing shown is the server's.*

— plus **"one request · four beats · response received `<generated_at>`"** in the panel header.
**Without these the progressive reveal is indistinguishable from faked sequencing**, and this
line is therefore not a caption the editor may drop for a cleaner frame. It is the reason the
reveal is honest.

**6.2 The watermark.** On frame for the whole film, naming *this* film's world rather than the
corpus world. Exact string and its justification are recorded by W5 in `ONSCREEN-TEXT.yaml`;
the control is preserved either way and only the noun follows the world on screen.

**6.3 The silence receipt is deliberately out of the 120 s (R-J).** It carries one field that
is reproduced from spec rather than produced by a column, so showing it honestly costs a STAGED
chip and a caveat sentence, and four seconds cannot carry both. **B3 already discharges the
rules requirement without it.** It stays a linked screen, and the fallback document carries the
one-sentence answer if a judge asks.

---

## 7 · WHAT THIS FILE DOES NOT DECIDE

* **The words.** B0–B8's lines are W2's (`VO-DEMO.md`); C1–C4's are W3's (`VO-CLOSE.md`). This
  file fixes their budgets and their weight, never their phrasing — except the opener in §1.1
  and the strap in §1.2, which are verbatim and binding.
* **What is on each frame.** W5 owns `ONSCREEN-TEXT.yaml`; the `on_screen` line in
  `BEATS.yaml` is a one-line summary for orientation, not a specification.
* **The clicks and the typed input.** W4 owns `CLICKS.md`.
* **What happens if the day goes wrong.** W6 owns `FALLBACKS.md`. One thing is settled here
  because it is a timing question: a retry on a serialisation error is **pressed again on
  camera** and costs its own seconds out of the margin above `total_s`, not out of B5.
* **Which cut is submitted.** The committed console cut stays untouched this wave. The
  orchestrator decides.
