<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# CLICKS — every cursor movement, click and keystroke, in one unbroken take

**Worker W4 · story-and-script wave · 2026-08-15**
**Binding on this file:** `docs/demo/story-and-script-plan.md` §2 (the beat sheet) and §4
(R-C, R-D, R-G, R-H, R-I, and every other ruling in that section).
**Live origin:** `https://ihuuyvm4z6nfuktihnkey77fpy0eyrhj.lambda-url.ap-southeast-1.on.aws`
**Operator surface filmed:** `<origin>/operator.html#/permit` and `<origin>/operator.html#/change`

**`claim_hygiene.py --check` verdict**, run this session on this file and pasted verbatim:

```
$ .venv/Scripts/python.exe scripts/demo/claim_hygiene.py --check docs/demo/film/CLICKS.md
  scanned 1 file(s) against 21 rules
  claim hygiene OK
                                                                          (exit 0)
```

Recorded per plan R-B: `docs/demo/film/` is outside every `TARGET_GLOBS` entry, so the scan is
invoked by hand and its result is pasted here rather than assumed. Re-run it after any edit —
"not scanned" and "passed" are different results.

---

## 0 · WHAT THIS FILE IS, AND WHAT WAS MEASURED BEFORE IT WAS WRITTEN

This is the operator's score: for each of the nine beats, the literal window state, the
literal cursor path, the literal click or keystroke, and the render the screen must produce
in answer. It is written to be executed by one person, in one take, without a decision left
to make at 02:00.

**It is not a wish-list against an imaginary UI.** The operator surface exists and has been
captured. Everything below was checked against these, read this session, with no POST issued
and no AWS surface touched:

| # | what I read | what it settled |
|---|---|---|
| M1 | `evidence/demo/operator-capture.json` — W7's capture of the built screens against `scripts/deploy/local_furl.py` over the local node, with the whole rendered DOM at five stages | Every control label, section order and rendered string quoted below is one the built page actually produces. Nothing here is a sketch. |
| M2 | `evidence/deploy/live-gate-run.json` — the recorded four-beat payload | Every SQLSTATE, constraint name, message, statement and field name quoted below is one the kernel returned. |
| M3 | `src/operator/issue/disclosure.ts`, `ActionBar.ts`, `pending.ts`, `route.ts`, `chrome/chrome.css`, `permit/typed-fields.ts` | The reveal mechanics, the pending label, the router's teardown behaviour, and the fact that no element on the page is `position: sticky` or `fixed`. |
| M4 | the capture's `geometry` block | The video's zoom. W7 measured a legibility floor of 2 % of frame height per em and found that at 200 % browser zoom the SQLSTATE value, the reason set and the disclosure line **all fail it**. See §1.2. |
| M5 | the capture's `assertions` block | `one-press-one-request` held; `never-the-merge-route` held; `reveal-3-made-no-request` and `reveal-4-made-no-request` held at 30 ms and 33 ms; **`raw-payload-drawer-is-byte-identical` did NOT hold** (§7 D-3). |

Four things the capture proves that this document then depends on: one press makes exactly
one request; the two reveals make none; the reveals are ~30 ms, not a fake 400 ms wait; and
no request to the merge route occurs in the whole page load.

**Alignment with the spine.** `docs/demo/film/BEATS.yaml` landed while this was being written.
`B0…B8` here are its `b0…b8`, and every in-point, duration and end-point below matches it
exactly (`0 / 12 / 22 / 36 / 54 / 64 / 80 / 98 / 110 / 120`). Its two `never_cut: true` beats —
`b3` and `b5` — are the two beats scored here with no click in them at all, which is not a
coincidence: the beats that may never be cut are the beats where the only correct operator
action is to stop moving.

---

## 1 · THE TAKE — everything fixed before the red light, and never changed inside it

Every setting in this section is chosen **before** recording starts and is not touched again
until the take ends. A dock change, a zoom change or a window resize inside the take reflows
the page underneath a claim, and a viewer cannot tell that from an edit.

### 1.1 Machine and recorder

* Recording monitor at **100 % display scaling**; capture the **display**, not the window.
* **2560×1440, 30 fps.** Notifications off. Second monitor cleared, its cursor parked.
* **Taskbar clock visible.** The browser is **maximised, not fullscreen** — `F11` hides both
  the taskbar clock and the URL bar, which are two of this film's four continuity witnesses.
* Bookmarks bar off, one tab, one window, extensions off, clean profile.

### 1.2 Browser zoom — 250 %, and it is a measurement, not a preference

W7 measured the operator surface at a 1024×576 CSS viewport with device scale factor 2.5 and
recorded the consequence in the capture's own `geometry.note`: at the plan-recommended 200 %,
the legibility floor rises to 14.40 CSS px and **the SQLSTATE value (13.12 px), the reason set
(13.12 px) and the disclosure line (12.80 px) all fall below it.** So:

* **Browser zoom 250 %** for the whole take.
* DevTools zoomed (`Ctrl` `+` with DevTools focused) until the Network panel's
  `Name` / `Status` / `Time` column text is as tall as the page's body text.
* **Run the 480 test at the exact final geometry** — the SQLSTATE frame, the reason-set block
  and the red refusal treatment — before rolling. If the red fails, the fix is zoom, never a
  colour change made for the camera.

### 1.3 The DevTools dock — right, and the width is a trade that must be measured

`r5-craft` §6 requires DevTools **docked and never closed for the whole demo segment**. At
250 % zoom, every physical pixel DevTools takes on the right is 0.4 CSS px taken from the
page. The permit screen's only breakpoint is `max-width: 720px` (`permit/permit.css`), and the
change screen's is `max-width: 60rem` (`change/change.css`).

**Ruling:** dock **right**, at a width that leaves the page **≥ 760 CSS px** — a DevTools
panel of about 640 physical px at a 2560-wide capture. Then, in pre-flight:

1. Confirm the permit screen has not crossed the 720 px breakpoint (the Figure 1 sections stay
   in their wide layout).
2. Confirm the longest evidence line wraps **at most once**: the beat-2 `message` is 108
   characters and is the line to test.
3. If either fails, widen the page by narrowing the dock — **never by lowering the zoom**,
   which loses the legibility floor measured in §1.2.

The change screen at B8 will render in its narrow (≤ 60 rem) layout. That is fine and expected;
it is a real responsive layout, not a window tuned to hide anything.

### 1.4 The four things in frame from the first frame to the last

1. **The URL bar**, reading `…lambda-url.ap-southeast-1.on.aws/operator.html#/permit`. Never
   cropped, never scrolled past, never covered by an overlay.
2. **The taskbar clock.**
3. **DevTools**, docked right, Network panel selected, **Preserve log ON**.
4. **The synthetic watermark.** The page's own strip reads
   `SYNTHETIC DEMONSTRATION — no real site, no real permit, no real person` — but it is a
   normal flow element at the top of the shell and **scrolls out of frame** (§7 D-1). Until it
   is made sticky, W5's burned-in strap carries the same words for the beats that are scrolled
   away from the top of the document.

The page's own **origin strip** — `served from <origin>` plus `X-Mainline-Emulator` when one is
present — sits at the very bottom of the document. It is the film's honesty device for plan
R-N: if the take is made against the local emulator, that strip says so **on screen**, in the
page's own words, and the film is not passed off as the deployed one.

### 1.5 Pre-roll, in order — the last ninety seconds before the red light

The order matters, and step 4 is the one people get wrong.

1. **Warm the endpoint from a different tab or a different browser**, once, within 60 s of the
   take (a cold press pays ~6.5 s). **Never warm it from the tab you are about to film**: a
   press in the filmed tab reveals the beats and burns the take.
2. **Close that tab. Load the operator page fresh** at
   `<origin>/operator.html#/permit`. Confirm the header renders `DEMO-PTW-0001`, the status
   chip reads `dispositioned`, the action bar reads `1 obligation outstanding`, and the origin
   strip names the origin you expect.
3. **Pre-type the two fields that are not typed on camera** — element 1 *Permit title* and
   element 3 *Location on site*. Element 5 is pre-typed **except its last few words**, which
   are typed on camera in B0. A page reload clears all three, so this is the last step that
   can be undone by a refresh.
4. **Open DevTools, select Network, switch Preserve log ON — and leave it open.** The panel is
   open **before** the press, not after it. A Network panel opened after a completed request is
   indistinguishable from a screenshot, and that is the whole reason this ordering is a rule.
5. Roll. The Network list is cleared **on camera**, in B1, as the first act of the take.

---

## 2 · THE ONE BUTTON, AND THE ROUTE IT MUST NOT CALL

> ### ⛔ BOXED WARNING — THE ISSUE BUTTON CALLS `POST /v1/demo/gate-run`. IT NEVER CALLS `POST /v1/permits/{id}/merge`.
>
> The seeded demo subject is write-protected. A mutating transition aimed at it answers
> **`423 Locked`** with a body naming `POST /v1/demo/gate-run` as the route to use instead
> (`docs/deploy/gate-run-contract.md` §7; r3-operator §5.5; operator-systems-plan M8/R4).
>
> **A 423 is not a gate refusal.** It is the demonstration protecting itself, and its message
> is about a lock, not about an obligation. Rendering it in a refusal banner would put a
> **fabricated exhibit** in front of a judge — a refusal that looks like the product's and
> came from the demo's own guard rail.
>
> This is the single most likely wrong turn available to anyone touching this surface, and it
> is already guarded in three places: the source comment in `issue/ActionBar.ts` and
> `issue/beats.ts`, the runtime check that renders `THE REQUEST DID NOT COMPLETE` and names
> the path if the button ever posts elsewhere, and W7's capture assertion
> `never-the-merge-route`, which held over the whole page load.
>
> **On camera this means:** there is exactly **one** mutating request in the entire film. If a
> second `POST` row ever appears in the Network panel, the take is dead — stop, and start again
> from §1.5 step 2. Do not narrate over it.

---

## 3 · FIVE MORE BOXED WARNINGS, EACH OF WHICH WOULD FAKE SOMETHING

> ### ⛔ THE PERMIT HEADER'S COUNTER NEVER TICKS 1 → 0. DO NOT WAIT FOR IT AND DO NOT SAY IT DOES.
> The header and the action bar were rendered from `GET /v1/permits/{id}`, which ran before the
> press. `counters.open_blocking` stays **1** for the whole film, because the beat-3 write
> happened inside a transaction that was rolled back and this page never re-reads it. The only
> place a zero legitimately appears is **inside the beat-3 panel**, in the payload's own
> `statement` (`UPDATE mainline.permit SET open_blocking = 0 …`) and its own
> `observed.counter_forced_to`. A UI-side decrement of that header, or a line of narration
> claiming the counter ticked, is a fabricated exhibit (plan R-D; r4-story §5.1 B4).

> ### ⛔ THE PERMIT SCREEN DOES NOT TURN FROM BLOCKED TO ISSUED. IT MUST NOT BE MADE TO.
> The beat sheet's phrase *"the permit screen turns from blocked to issued"* describes something
> the software correctly refuses to do. The admission happened inside the rolled-back
> transaction; on the live row the permit is still `dispositioned`, `head_seq` is still 2 and
> `merged_commit` is still `null`. In the capture, the ISSUE button stays **disabled** and the
> lock note stays on screen through the admission beat. What is true, and is stronger, is on
> screen already: the beat-4 panel's `permit state merged`, the merge record, and then the run
> footer's `this run persisted anything · false`. **That contradiction is B8's whole point, so
> keep it.** The founder must not say "the permit is now issued."

> ### ⛔ THE TWO ADVANCE CONTROLS ARE REVEALS OF A RESPONSE ALREADY IN HAND, AND THEIR LABELS MUST SAY SO.
> Measured in the build today (`src/operator/issue/disclosure.ts` `advanceLabel()`), the labels
> read **`But the counter now reads 0 ▸`** and **`Answer the obligation, then issue again ▸`**.
> Both read as *new actions the operator is about to take*. Plan R-C requires the opposite:
> controls **labelled as reveals**, never as writes. Required strings (§7 D-4 names the owner):
>
> * beat 3 → **`Show what happens if the counter is forced to zero ▸`**
> * beat 4 → **`Show the beat where one signed disposition is admitted ▸`**
>
> Until that lands, the founder narrates them as reveals and **never** says "now I'll…",
> "let me try…", or "watch me". The disclosure strip's own caveat — *"Every beat below came back
> in that one response. Each is revealed on a click"* — is already correct and stays in frame.

> ### ⛔ DO NOT SELECT A DEFEATER RADIO ON CAMERA.
> Selecting one of the three defeater options would say, in pictures, *"I chose this answer and
> then the permit was admitted."* The disposition in beat 4 was composed inside the endpoint's
> own transaction; the payload does not return which `defeater_code` it used, so no selection on
> screen can be shown to be the one that mattered. The three prompts are **read** on camera, not
> answered. The same rule kills any typed rationale or citation: a typed string that is never
> sent, filmed beside an admission, is a claim about causation that nothing supports.

> ### ⛔ NEVER SWITCH MODULES BEFORE B7, AND NEVER SWITCH BACK.
> The router is hash-based and **tears the screen down on a hash change** (`route.ts`,
> `ScreenMount` teardown). Switching to *Management of change* unmounts the permit screen: the
> transcript, the disclosure line and every revealed beat are gone, and returning re-mounts and
> re-fetches. Getting them back would require a **second** `POST /v1/demo/gate-run` — a second
> `run_id`, a second `generated_at`, and a film whose one-request claim is false. The single
> module switch in this film happens at B8 and is never reversed on camera.

---

## 4 · THE CONVENTION A JUDGE CAN CHECK IN TWO SECONDS: TYPED CARRIES NO CHIP

Plan R-H, and the built page already implements it:

* **Every server value carries a provenance chip** — `db:column`, `db:constraint`, `derived`,
  `recomputed` — resolved by JSON pointer from the response's own `provenance[]`.
* **Nothing typed carries one.** The three typed controls are visible `<input>`/`<textarea>`
  elements with a caret and a placeholder, each labelled
  `typed on this device · not carried by this deployment` (`permit/typed-fields.ts`,
  `TYPED_HERE`).
* **Element 8 (PPE) renders empty and labelled** — *"not carried by this deployment"* — and is
  in frame in B0. Do not scroll past it quickly; an empty field that says why it is empty is a
  fidelity signal, not a gap.
* **Element 11 (extension) is omitted**, with a line saying the deployment has no extension
  mechanism. Elements 12 and 13 render **unsigned**.

**What may be typed, and the constraint on it.** W5 owns the literal strings
(`ONSCREEN-TEXT.yaml`); this file owns the rule they must satisfy:

* no invented plant name, asset tag, crew, company or PPE list — a value with no column is
  typed by a human or it is empty, and a plausible-looking invention is the same class of act
  as reshaping a seed to match a constant (r3-operator §5.3);
* nothing that could be mistaken for a column value if screenshotted;
* ≤ 60 characters per field, so no typed line wraps and competes with the evidence lines;
* the on-camera tail in element 5 is **at least three words**, so the human typing rate is
  visible (r5-craft §7 tell 12: an inhuman constant rate reads as fake).

---

## 5 · THE NINE BEATS

Times are the plan's. Each block is: **window/scroll state → cursor path → click or keystroke
→ what must render → in frame → do not.**

---

### B0 · THE ORDINARY MOMENT — `0:00 → 0:12` (12 s)

**Window/scroll state at the in-point.** Scroll position **0** — the top of the document. In
frame, top to bottom: the watermark strip; the `CONTROL OF WORK` app bar with its two module
tabs; the left rail (`Permits`, and `Isolations` / `Certificates` / `Register` each marked
*not carried by this deployment*); the permit-type selector with **Cold work** selected and
labelled `HSG250 Table 2 · selected on this device`; and the header block —
`DEMO-PTW-0001` `[db:column]`, `refs/permits/demo-0001`, the status chip reading
**`dispositioned`** verbatim beside the full enum ladder of `mainline.subject_state`, the site
UUID, `Valid from 02 Aug 2026, 00:00Z`, `Expires 02 Aug 2027, 00:00Z`, `Gate epoch 1`,
`Chain head 2`, `Under hold false`, and the `Display copy ⎙` control.

**Cursor path.**

| t | movement |
|---|---|
| `0:00 – 0:03.5` | Cursor **still**, parked in the header's dead space to the right of the status chip. Nothing moves while the opening sentence runs. |
| `0:03.5 – 0:05` | Wheel scroll **down**, three notches, slowly, into §5 *Description of work to be done and its limitations*. §1 *Permit title* and §3 *Job location* pass through frame carrying their pre-typed text and no chip. |
| `0:05 – 0:05.5` | Cursor travels to the **Work and its limitations** textarea and single-left-clicks into it. Caret appears at the end of the pre-typed text. |
| `0:05.5 – 0:08` | **Keystrokes: the tail of the sentence, typed at a human rate.** No `Enter`, no `Tab`. The caret is left blinking in the field. |
| `0:08 – 0:10.5` | Wheel scroll **down**, four notches, past §6 *Hazard identification* (a pass-through, not a dwell — B3 comes back to it), §7 *Precautions* with the clause and its `LOTO` / `ZERO_ENERGY` anchor chips, §8 *Protective equipment* reading **not carried by this deployment**, and the §9–13 signature block. |
| `0:10.5 – 0:12` | Cursor comes to rest **on the `ISSUE ▸` button** and stops. The action bar reads `1 obligation outstanding`; `Save draft` is beside it, disabled, with its own note. |

**What must render.** Everything above is already on screen from page load; B0 renders nothing
new except the typed characters. The one thing to verify in frame: the typed field carries
**no provenance chip** while `DEMO-PTW-0001` two sections above carries `db:column`.

**In frame.** URL bar · taskbar clock · DevTools (Network, list still holding the page-load
GETs — it is cleared in B1) · the watermark, which is genuinely on screen for this beat because
scroll position starts at 0.

**Do not.** Do not press `Enter` in the textarea. Do not click `Display copy` (it opens a print
view and costs the take). Do not dwell on the hazard card here — B3 is where it earns 18 s.

---

### B1 · THE ATTEMPT — `0:12 → 0:22` (10 s)

**Window/scroll state.** Unchanged: the action bar sits in the lower half of the page area,
the signature block above it.

**Cursor path and the two clicks.**

| t | movement |
|---|---|
| `0:12 – 0:13` | Cursor travels **right, into the DevTools panel**, to the Network toolbar's **Clear** control (⃠). |
| `0:13` | **Click 1 — Clear.** The request list empties on camera. This is the proof that nothing is preloaded, and it is why the panel was opened in pre-flight rather than now. |
| `0:13 – 0:14.5` | Cursor travels **back left**, continuously, to the `ISSUE ▸` button. A cursor that jumps here is a cut (r5-craft §7 tell 6). |
| `0:14.5` | **Click 2 — `ISSUE ▸`.** Single left click. |
| `0:14.5 – 0:22` | Cursor **does not move again** until the response lands. Hands off the wheel. |

**What must render, and it must render with no cut between the press and the render.**

* The button's own label becomes **`Issuing… 0.4 s`** and the tenths **count up on a real
  clock** driven by the real promise (`issue/pending.ts`). There is no `setTimeout` behind it
  and no skeleton.
* Beside it: *"One SERIALIZABLE transaction is open against the database. The clock is this
  browser's measurement of the round trip; each beat below reports the duration the server
  measured."*
* In DevTools: **one row appears**, `gate-run`, method `POST`, and the `Status`, `Size` and
  `Time` columns fill as the response lands.
* Nothing else on the page moves.

**In frame.** The four witnesses, plus the pending clock and the single in-flight row in the
same frame — that pairing is the shot no screenshot and no faked delay can produce.

**Do not.** Do not cut. Do not speed up. Do not talk over the last third of the wait — the
plan's VO stops and lets the beats land. If the round trip is fast, the beat is short, and
that is a better problem than a fake one. If `40001` comes back, press again **on camera**
(plan R-N).

---

### B2 · THE REFUSAL — `0:22 → 0:36` (14 s) · *filmed calm*

**Window/scroll state.** The transcript renders **beneath the action bar** and the page does
not scroll itself, so this beat opens with one small wheel movement.

**Cursor path.**

| t | movement |
|---|---|
| `0:22 – 0:23` | Wheel scroll **down**, two notches, until the lock note, the disclosure strip and the beat-2 banner are in frame together. |
| `0:23 – 0:29` | Cursor **parked and still**, off to the right of the banner. The frame does the work. |
| `0:29 – 0:33` | Cursor travels slowly down the banner as a pointer — `SQLSTATE 23514` → `constraint gate_closed_when_issued` → the `CHECK predicate` row → the `message` row. It **points**; it does not click and does not select text. |
| `0:33 – 0:36` | Cursor moves right and rests beside the DevTools row for ~2 s: `gate-run · 200 · <real bytes> · <real time>`. No tab is clicked. |

**No click and no keystroke occurs in B2.**

**What must render** (all of it from the payload, all of it verbatim):

* the action-bar lock: **`ISSUE is locked: gate_closed_when_issued refused this write.`** with
  `ISSUE ▸` now disabled;
* the permanent disclosure strip:
  **`one request · 4 beats · POST /v1/demo/gate-run · run_id <id> · response received <ISO> · <n> bytes`**
  — carrying that run's own `run_id`, its own received instant and its own byte count, with the
  caveat sentence beneath it. The strip has **no close control** by construction. It says
  `4 beats`, in digits, because that is what the transport composed: **do not "correct" it**;
* beat 1's panel: `SQLSTATE 00000`, `state dispositioned`,
  `open_blocking (projected column) 1`, `open_blocking (re-derived) 1`, `gate_epoch 1`,
  `head_seq 2`, the blocking obligation's id, the server-measured elapsed, and the statement
  `SELECT … FROM mainline.permit JOIN mainline.site …`;
* beat 2's banner: **`PERMIT NOT ISSUED`** · `1 obligation outstanding` · the precursor line ·
  **`SQLSTATE 23514`** · `constraint gate_closed_when_issued` chipped **`reported`** ·
  the CHECK predicate `((state != 'merged':::mainline.subject_state) OR (open_blocking = 0:::INT8))`
  · the statement `CALL mainline.merge_permit(…)` · the message
  *"failed to satisfy CHECK constraint …"* · `diagnosis declarative · 0 probe calls` · the
  reason set (`obligation … · origin blame_ancestry · severity 4 · virulence blood_major ·
  clause … · precursor event … · open at gate_epoch 1; no live disposition`) · the nearest
  admissible alternative (*"1 obligation(s) remain open on this subject; disposing of exactly
  those restores admissibility"*, `dispose_obligations`) · `refusal_id` · the beat's own
  `elapsed`, labelled *"Measured by the server for this beat — not a reveal delay."*

**In frame.** The `:::mainline.subject_state` type annotation must be legible — it is
CockroachDB's own idiom and the most credible string in the film. Do not paraphrase it, do not
truncate it, do not cover it with an overlay; W5's `SQLSTATE 23514` strap goes **beside** it.

**Do not.** Do not inflate this beat — a `CHECK` refusing is table stakes and B5 needs the
weight. Do not open the Headers or Response tab yet; the row's four columns carry B2's claim,
and the deeper inspection belongs to the naming block.

---

### B3 · WHY — THE MEMORY LOOP — `0:36 → 0:54` (18 s) · *never cut*

**Window/scroll state.** Wheel scroll **up**, four notches, back to §6 *Hazard identification*.
The card fills the page area. This is the film's most important frame and nothing may be
scrolled during it once it is composed.

**Cursor path — pointing only, no clicks.**

| t | movement |
|---|---|
| `0:36 – 0:38` | Scroll up; settle with the card's header — *"Hazard identification · raised by recall, not by a checklist"* — at the top of the page area. |
| `0:38 – 0:42` | Cursor rests on the precursor block: `DEMO-INC-0001 · incident · 14 March 2019 06:20 UTC`, the `SYNTHETIC — Stored energy release during intrusive work` title, `severity gate 4 / actual 4 / potential 4`, `basis human_rated`, the source document and its sha256. |
| `0:42 – 0:46` | Cursor moves to the projection block — *"the severity on this obligation was not chosen by whoever raised it"* — with `on the obligation 4 / blood_major / closure_gen 0` beside `in the blame closure 4 / blood_major / closure_gen 0`, and beneath them the **source citation**: `0, 'routine', 0, -- projected over by fn_check_project (MI25)`, attributed to `demo_permit.sql:318` at the tree the capture names. |
| `0:46 – 0:51` | Cursor travels down the three labelled rows in order: **`RECALLED`** (run id · `started 2 August 2026 03:00 UTC` · `policy demo-recall-1.0` · `index generation g1` · `1 candidates · 1 blocking · 0 silenced · 0 deduped`) → **`SHOWN TO`** (`actor demo.signer` · `issued 2 August 2026 03:05 UTC` · the receipt digest) → **`STATUS`** (`● OPEN — unanswered on this permit`, with the `derived` chip and the sentence that `open` has no column). |
| `0:51 – 0:54` | Cursor rests on the delta at the foot of the card: `recall run started 03:00:00Z` → **`10 s`** → `obligation materialised 03:00:10Z`, with the `10 s` labelled as *subtracted in this browser, not a column and not chipped*. |

**What must render.** Nothing new — every value above arrived in the four GETs at page load,
and the card prints each one's exchange line (`GET … · 200 · 2,408 B on the wire · observed_at
…`) beneath the values it carries. That is what a judge cross-checks.

**In frame.** The `SYNTHETIC —` prefixes stay visible; do not crop them to prettify the frame
(plan R-F). The disclosure strip is **not** in frame here, because it is not sticky (§7 D-2) —
which is exactly why the card's own per-exchange provenance lines must be legible instead.

**Do not.** Do not say anything present-tense about the retrieval: the recall already ran and
what is on screen is its **record**. No similarity score, no vector visualisation, no
embedding — this world seeds none. No click: a click here selects text and adds nothing.

---

### B4 · THE HUMAN MOVE — `0:54 → 1:04` (10 s)

**Window/scroll state.** Wheel scroll **down**, four notches, back to the transcript, until the
advance control is in the lower third of the page area with the beat-2 banner above it. This
region **is** the gate transcript of plan R-D: it sits **beneath** the supervisor's own form,
inside the supervisor's own page, and it renders the response's own strings — infrastructure
becoming visible under the product, which is the founder's whole frame.

**Cursor path and the click.**

| t | movement |
|---|---|
| `0:54 – 0:56` | Scroll down; cursor travels to the advance control. |
| `0:56` | **Click 3 — the beat-3 reveal.** Required label: `Show what happens if the counter is forced to zero ▸` (§3, third box). |
| `0:56 – 0:57` | The beat-3 panel paints in ~30 ms — measured, not scheduled. **No request is made**, and the Network panel proves it: the list still holds exactly one row. |
| `0:57 – 1:04` | Cursor travels to the panel's **`statement`** row and rests there: `UPDATE mainline.permit SET open_blocking = 0 WHERE permit_id = %s; CALL mainline.merge_permit(…)`, beside the payload's own label for the beat — *"THE ATTACK: force the projected counter to zero out of band, then merge again"* — and the observed line *"mainline.permit.open_blocking set out of band — what a disarmed projector or a careless UPDATE leaves behind."* |

**What must render.** The whole beat-3 panel arrives in one paint, headline first. Its order is
the build's: **`PERMIT STILL NOT ISSUED`** → *"The outstanding-obligation counter now reads 0.
The permit was refused anyway."* → *"The gate did not trust the counter. It counted again, from
the obligations themselves, and got 1."* → the attack line → the refusal rows. **B4 is the
cursor and the narration holding on the attack half; B5 is the move to the refusal half.** The
picture is not paced by the software, so it is paced by the pointer.

**In frame.** The disclosure strip, one Network row, the URL bar, the clock.

**Do not.** Do not look for the header counter to change (§3, first box). Do not describe this
as something you are doing — it is a reveal of a beat that already ran inside the rolled-back
transaction. Play it matter-of-fact: the shrug, not the villainy.

**And the prohibition R-D exists for:** no second window, no admin console, no `psql` or
`cockroach sql` prompt, no terminal, no simulated SQL being typed by anybody. A supervisor's
app does not contain a control that forges a counter, and staging one would be a re-enactment
of a beat that already happened in the database. The forged `UPDATE` appears on camera exactly
once and only as **text the server sent back**, in the panel's own `statement` row.

---

### B5 · REFUSED ANYWAY — `1:04 → 1:20` (16 s) · *the peak · never cut*

**Window/scroll state.** Unchanged from B4 — **no scroll during this beat if the panel fits.**
If the refusal rows sit below the fold, make the one wheel notch at `1:04`, before the line,
never during it.

**Cursor path — no clicks.**

| t | movement |
|---|---|
| `1:04 – 1:08` | Cursor moves up the panel to **`SQLSTATE P0001`** and `constraint mainline.fn_permit_merge_gate`, and rests. |
| `1:08 – 1:12` | Cursor moves to the `message` row and holds on the verbatim string: *"MAINLINE: merge refused by mainline.fn_permit_merge_gate — re-derived open obligation count is 1 while the projected counter reads zero."* |
| `1:12 – 1:15` | Cursor moves to the weakening rows and holds: the `parsed` chip with its note — *"Recovered from the message text rather than reported by the driver — a weakened diagnosis, and it is labelled as one"* — then `diagnosis none · 0 probe calls`, the reason set `capability gap · mainline.fn_permit_merge_gate · …`, and `nearest admissible alternative: NOT COMPUTABLE for this refusal · not_computable`. |
| `1:15 – 1:20` | **Cursor stops. Silence.** Hold the frame with `P0001` and the message both legible. |

**What must render.** Nothing new — the panel is already whole. What matters is that the
**weaker** diagnosis is on screen at the film's loudest moment: `constraint_source: parsed`,
`naa: null`, `naa_reason: not_computable`, MUS `kind: capability_gap`. Leave it there. A demo
that grades its own exhibit down is not one anybody believes is faked.

**In frame.** The single Network row, still one, is the quiet corroboration that this beat
made no request.

**Do not.** Do not add a second overlay here. Do not cut to DevTools mid-line. Do not let the
narration run past the hold — the silence after the sentence is the beat.

---

### B6 · THE ANSWER IS A QUESTION — `1:20 → 1:38` (18 s)

**Dependency, stated first because it changes the clicks.** The three defeater prompts are a
real, declared read — `GET /v1/checks/{check_id}/disposition` → `200`, 3,805 B, carrying
`defeater_options[3]` with their prompts verbatim and `lattice[5]` — but **today they are
rendered only on the change screen**, and the permit screen makes no such read. §7 D-5 names
the owner and the change. Two paths, and the film takes whichever is true on the day.

#### Path A — the disposition panel has landed on the permit screen (preferred)

**Window/scroll state.** The panel sits beneath the beat-3 banner, inside the transcript
region, so B6 is a short local scroll and no module switch (§3, fifth box).

| t | movement |
|---|---|
| `1:20 – 1:22` | Wheel scroll **up**, two notches, to the §9–13 signature block. Cursor rests on **row 10 · Acceptance**: `Acceptor` · **`demo.signer`** `[db:column]` · `02 Aug 2026, 03:05Z` · the receipt digest · `Obligations shown 1` · `Tokens 200`. Then one deliberate move up to **row 9 · Issue**, which reads `unsigned — signatory` / `unsigned — date and time`. |
| `1:22 – 1:30` | Wheel scroll **down** to the disposition panel. Cursor travels down the three prompt cards, resting ~2.5 s on each: `MECHANISM_PRESENT_AND_VERIFIED` — *"Which isolation point was locked, and who verified it at zero?"*; `WORK_NOT_INTRUSIVE` — *"Which task in this permit's scope was assessed as non-intrusive, and against which method statement?"*; `ENERGY_SOURCE_ABSENT` — *"Which stored-energy source was surveyed and found absent within this permit's boundary, and by whom?"* |
| `1:30 – 1:38` | Cursor moves to the lattice and rests on two rows: **`mechanism_absent`** (`min rank 4` · second signer ✓ · foreign org ✓ · predicate ✓ · re-assert ✓) and **`emergency_override`** (`min rank 5` · second signer ✓ · foreign org ✓ · `max_ttl_hours 12`). |

**No click and no keystroke occurs in B6** (§3, fourth box).

#### Path B — the panel has not landed

**Window/scroll state.** Identical opening; the second half changes.

| t | movement |
|---|---|
| `1:20 – 1:26` | As Path A: signature block, row 10 Acceptance, then row 9 Issue reading unsigned. |
| `1:26 – 1:38` | Wheel scroll **up** to the hazard card's `STATUS` row — `● OPEN — unanswered on this permit — no disposition of it is live` — with the sentence that `open` has no column and is derived from the absence of a live `mainline.disposition` row. Cursor rests there. |

Under Path B the three questions are **not** filmed and the VO must not describe them; the
scope-cut ladder's B6 trim (18 s → 14 s) applies and the recovered seconds go nowhere else.

**In frame, both paths.** `demo.signer` is on the **acceptance** row and nowhere else. He is
the person the obligation was shown to — `exposure_receipt.actor_sub` — not the issuing
authority (plan R-G). The Issue row stays visibly unsigned.

**Do not.** Do not select a radio. Do not type a rationale. Do not call the three options a
checklist and do not say any of them is inapplicable — there is no global "N/A" in this
vocabulary, and inventing one would destroy the point.

---

### B7 · AND THEN IT ADMITS — `1:38 → 1:50` (12 s)

**Window/scroll state.** Wheel scroll **down** to the foot of the transcript, until the second
advance control is in the middle of the page area.

**Cursor path and the click.**

| t | movement |
|---|---|
| `1:38 – 1:40` | Cursor travels to the advance control. |
| `1:40` | **Click 4 — the beat-4 reveal.** Required label: `Show the beat where one signed disposition is admitted ▸` (§3, third box). |
| `1:40 – 1:41` | The admission panel and the run footer paint together in ~33 ms. **No request is made** — the Network list still holds one row. |
| `1:41 – 1:50` | Cursor travels down the admission rows and rests: **`ISSUE ADMITTED`** · the beat's label *"Sign one disposition against the obligation, then merge again."* · `SQLSTATE 00000` · `disposition <uuid4>` · `disposition kind applied` · `open_blocking after the signature 0` · `clearance digest (server-computed)` · `merged_at` · `permit state merged` · the server-measured elapsed · the `INSERT INTO mainline.disposition (…); CALL mainline.merge_permit(…)` statement. |

**What must render.** The admission panel **plus** the run footer, because the footer paints as
soon as the last beat is revealed. That is why B8's first half needs no click.

**In frame.** The ISSUE button, still disabled, with its lock note — and the header, if the
scroll allows, still reading `dispositioned`. Both are true and both are B8's setup.

**Do not.** Do not say the permit is issued (§3, second box). Do not caption
`clearance_digest` as a constant — four runs on 2026-08-15 produced four different digests, and
if it were ever stable the rollback proof would be broken (plan R-K). `merged_commit` **is**
stable and may be quoted.

---

### B8 · NONE OF IT HAPPENED — `1:50 → 2:00` (10 s)

**Two halves. The first is a pointer move; the second is the film's only navigation.**

#### B8a — the run footer, already on screen (`1:50 – 1:56`)

**Window/scroll state.** Unchanged from B7; the footer is directly beneath the admission panel.

| t | movement |
|---|---|
| `1:50 – 1:56` | Cursor travels down the footer rows: **`VERDICT PROVEN`** · `isolation SERIALIZABLE` · `transaction rolled_back` · `one transaction (equal cluster logical timestamps) · true · <ts> → <ts>` · `savepoints gate_run_beat_2, gate_run_beat_3, gate_run_beat_4` · **`this run persisted anything · false`** · **`minted disposition after rollback · <uuid4> · 0 rows`** · `permit row unchanged · true` · `whole database unchanged · true`. |

Say `persisted false`, never *"nothing was written"*. Something **was** written, and unwound
inside one `SERIALIZABLE` transaction, and the proof is a uuid4 only this run held.

#### B8b — the change request (`1:56 – 2:00`)

| t | movement |
|---|---|
| `1:56 – 1:57.5` | Cursor travels **up to the app bar** and to the tab **`Management of change`**. |
| `1:57.5` | **Click 5 — the module switch.** The hash becomes `#/change` **in the URL bar, on the same origin** — the host in frame does not change. The change screen mounts and issues its reads live: `GET /v1/change-requests/{cr_id}` → `200`, the `…/blocking-checks` probe → **`404`**, the clause version → `200`, the disposition read → `200`. Four new rows appear in the Network panel: a live client, proven again, for free. |
| `1:57.5 – 2:00` | Cursor rests beside the **disabled** `Approve change` control and its reason. |

**What must render.** `DEMO-MOC-0001` · `refs/changes/demo-0001 → refs/heads/main` ·
the `checks_materialised` chip beside the IChemE ribbon (with the ribbon marking **no** current
step, because no column maps one) · `counters.open_blocking 1` · the four CR constraints with
their predicates, `cr_gate_closed_when_merged` reading `open_blocking = 1` · and beside the
disabled control: *"Cannot approve. 1 blocking obligation is outstanding on this change
request."*, the predicate, the sentence that the control is wired to nothing, and the **404
route table the deployment itself returned**, with the two absent routes struck through.

**Do not.** Do not click the disabled control — a disabled control clicked on camera reads as a
broken demo, and this one is inert by design. Do not say *"watch the same debt block the change
request"* (plan R-I): there is no merge route to block, and this screen is **told, not driven**.
Do not switch back to the permit module (§3, fifth box). Do not narrate a proposed clause text —
none exists in this deployment, and the *Proposed wording* box is empty and says why.

**If the scope-cut ladder fires,** B8b is the first thing cut (plan §2.2). Then click 5 never
happens, the film ends on the run footer, and the take is four clicks and one text entry long.

---

## 6 · THE ANTI-FAKE CRAFT RULES THAT BIND EVERY BEAT ABOVE

1. **No cut between the press and the render.** Not once, anywhere. This is the single most
   load-bearing editorial rule in the film.
2. **The cursor moves continuously.** A teleporting cursor **is** a cut, and a viewer reads it
   as one. Every movement in §5 is a travel, not a jump.
3. **No window is sized to hide layout.** Scrollbars stay visible; wrapping stays visible;
   overflow stays visible. A scrollbar is evidence of a real page (r5-craft §7 tell 13). The
   geometry is fixed in §1 and is not adjusted between beats to make a section fit.
4. **Nothing is sped up across a claim.** The press → refusal round trip is never compressed.
   The only thing that may be trimmed at all is typing, and only with a visible marker in the
   picture, and never over a claim — which is why B0's typing is short enough not to need one.
5. **Nothing is rounded.** Per-beat durations are the payload's own `elapsed_ms` to the digits
   it printed. **Re-derive them from the take's own run**; the reference run in
   `evidence/deploy/live-gate-run.json` printed `0.011 / 572.251 / 564.509 / 516.003` ms and the
   capture printed different ones, which is the point. Never a stopwatch, never a reveal delay,
   never offered as a product latency.
6. **Anything spoken is on screen, to the same digits.** Script from the payload, not memory.
7. **If a take fails, re-record the take.** Never patch, never splice, never re-cut picture
   under re-recorded audio.
8. **If the live origin is down, the film is not made against a mock.** It is postponed, or it
   is filmed against the local node **and said to be local, on screen** — which the page's own
   origin strip does automatically by rendering `X-Mainline-Emulator: local_furl` (plan R-N).

---

## 7 · DEPENDENCIES AND ESCALATIONS — what this score assumes, and who owns it

Each is a real gap measured this session, not a preference. None is mine to fix: this file owns
no source.

| # | gap | measured where | what the film needs | owner |
|---|---|---|---|---|
| **D-1** | The watermark strip is a normal flow element (`.cw-watermark`, no `position: sticky`) and **scrolls out of frame** for every beat after B0. Plan R-L requires it on frame for the whole film. | `operator/chrome/chrome.css` | Preferred: make the watermark strip sticky. Fallback: W5 burns in a strap carrying the identical sentence. | operator wave (chrome) / W5 |
| **D-2** | The disclosure strip is likewise not sticky, so it leaves frame at B3 and B6. Plan R-C requires it in frame from B2 onward. | `operator/issue/disclosure.ts`, `issue.css` | Preferred: sticky strip. Fallback: a burned strap carrying **no run-varying value** — a generic sentence cannot be wrong about a run, whereas a burned `run_id` typed by hand can be. | operator wave (issue) / W5 |
| **D-3** | `raw-payload-drawer-is-byte-identical` **did not hold**: `renderRawPayload()` / `renderRequestLog()` exist and are called by nobody on the permit screen, so the 10,446-byte gate-run body has no in-page drawer. | `evidence/demo/operator-capture.json` → `assertions` | Either the drawer lands (and B2 gains an optional click on it), or DevTools' Response tab carries the raw payload in the naming block. The film as scored above does **not** depend on it. | operator wave (W5 with W2) |
| **D-4** | The two advance controls are labelled as actions, not reveals. | `operator/issue/disclosure.ts` `advanceLabel()` | The two strings in §3, third box. | operator wave (issue) |
| **D-5** | The three defeater prompts and the lattice are rendered on the **change** screen only; the permit screen makes no `GET /v1/checks/{check_id}/disposition`. B6 as written in the beat sheet has no pixels on the permit side. | `operator/change/ChangeScreen.ts`, `change/absence.ts`; capture network list | Path A in §5 B6 — a read-only disposition panel on the permit screen, from that one declared GET, with **no submit control**. Otherwise Path B, and B6 trims. | operator wave (permit/issue) |
| **D-6** | `/operator.html` is not on the deployed origin until the orchestrator's next package; the URL in §1 must be confirmed on the day. | operator-systems-plan M5/M6, §3 | Confirm before pre-flight. If it serves the console instead, the shoot follows W6's fallback document, not this one. | orchestrator |

### 7.1 · ESCALATION TO THE STORY LEAD AND TO W7 — one sentence is in three files and the software does not do it

**The claim.** *"The permit screen turns from blocked to issued."* It appears in
`BEATS.yaml:204` and `:336` (`b7.on_screen`), and — the part that matters, because it is
**spoken** — in `VO-DEMO.md:272` (*"the form turns from blocked to issued"*), `:279` and `:422`.
The neighbouring version, *"the counter on the permit header ticks 1 → 0"*, comes from
r4-story §5 B4.

**What was measured.** In W7's capture, across the admission stage
(`04-admitted-and-proven`), the permit screen's diff against the previous stage adds the
admission panel and the run footer **and nothing else**. Specifically:

* the action-bar lock note still reads `ISSUE is locked: mainline.fn_permit_merge_gate refused
  this write.`, and `ISSUE ▸` is still `disabled`;
* the header still reads `dispositioned`, `Chain head 2`, `Merged commit null`;
* `counters.open_blocking` is still `1`;
* the signature block's **Issue** row still reads `unsigned — signatory`.

That is correct behaviour, not a defect: the admission happened inside a transaction that was
rolled back, the page holds no re-read, and a screen that flipped to "issued" would be
asserting a state the database does not hold. **The sentence is therefore a spoken claim about
a render that will not be in the frame it is spoken over** — r5-craft §7 tell 8 — and the only
way to make it true on camera is to fake the render, which is the one act this wave exists to
prevent.

**What is true, and is better, and is already on screen in the same frame:** `ADMITTED · 00000`,
`disposition kind applied`, `open_blocking after the signature 0`, `permit state merged`, the
merge record — **and, three rows below, `this run persisted anything · false`.** The admission
and the lock are in frame together. That contradiction is the product: the gate admits when the
debt is answered, and this endpoint still cannot write. B8 then names it.

**Suggested replacement, offered but not owned** (the words are W2's): *"Zero zero zero zero
zero — admitted. State merged, head sequence three, and the same issue goes through. Nothing
was overridden: the obligation was answered."* It keeps the beat, the digits and the relief, and
drops the one clause the picture cannot support.

**Requested resolution.** Story lead rules; W2 edits `VO-DEMO.md`; W1 edits `b7.on_screen`; W7
records the outcome in `CLAIMS-CLEARANCE.md`. This file is scored against the measured render
either way (§3, first and second boxes) — if the sentence survives unchanged, the founder still
must not point at the screen while saying it, because the screen will be saying otherwise.

---

## 8 · THE CLICK LEDGER — the whole take, in five clicks and one text entry

| # | t | act | request it makes |
|---|---|---|---|
| — | pre-roll | navigate; pre-type elements 1 and 3 and the head of element 5; open DevTools → Network → Preserve log | 8 × `GET` at page load |
| 1 | `0:05.5` | click into the *Work and its limitations* textarea; type the tail | none |
| 2 | `0:13` | click **Clear** in the Network panel | none |
| 3 | `0:14.5` | click **`ISSUE ▸`** | **1 × `POST /v1/demo/gate-run`** — the only mutating call in the film |
| 4 | `0:56` | click the **beat-3 reveal** | **none** (measured 30 ms to paint) |
| 5 | `1:40` | click the **beat-4 reveal** | **none** (measured 33 ms to paint) |
| 6 | `1:57.5` | click the app-bar tab **Management of change** | 4 × `GET`, one of which is the `404` route table |

**Totals a judge can verify in the Network panel: one `POST`, and the reveals make none.**
Everything between the clicks is a wheel scroll and a cursor travel — which is what a real
person does with a form, and is why the take can be unbroken.
