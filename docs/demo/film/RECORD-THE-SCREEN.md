<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# RECORD THE SCREEN — everything, in order

**You have already recorded the voice** from [`READ-THIS-ALOUD.md`](READ-THIS-ALOUD.md). This is
the picture pass. Follow it top to bottom with nothing else open.

Every string you must type is printed here in full, at the moment you type it. Nothing on this
page says "see the other document".

**The stage is already warm.** Measured against the live origin on 2026-08-18: the demo state is
correct for filming, both use cases were driven end to end and answered `PROVEN`, and the state
was unchanged afterwards. **You do not need Docker and you do not need a local database.** The
film shoots against the deployed URL only.

---

# PART 1 · YOUR SETUP

## 1.1 · The recorder

| Setting | Value | Why |
|---|---|---|
| **Resolution** | **2560 × 1440** | The shot list is measured at this size. Smaller, and the refusal text stops being readable in a small player. |
| **Frame rate** | **30 fps** | Enough for cursor motion. 60 doubles the file size for nothing. |
| **Capture area** | The **whole screen**, not a window | A window capture re-crops if anything resizes — and opening DevTools counts as a resize. |
| **Cursor** | **Visible.** Click-highlight effects **off** | The cursor is how a viewer follows you. A coloured ring around clicks reads as a software tutorial. |
| **Audio** | **Off** | You already have the voice. Recording room tone creates a second track you then have to remember to mute. |
| **Format** | MP4, H.264 | Uploads without transcoding surprises. |

**OBS Studio** is free and does all of this:
Sources → **Display Capture** · Settings → Video → set **Base** and **Output** both to
`2560x1440`, FPS `30` · Settings → Output → Recording Quality **Indistinguishable**, format `mp4`.

> **If your screen is not 2560 × 1440**, record at your native resolution and set the output to
> match it. **Do not upscale.** An honest 1920 × 1080 beats a stretched 2560.

## 1.2 · Silence everything

- **Windows** → Settings → System → Notifications → **Off**, then turn on **Focus assist**.
- **Quit** Slack, Teams, Discord, Mail, WhatsApp. Quit, not minimise.
- **Second monitor:** clear it, and park the mouse pointer on the recording screen.
- **Phone:** face down and silent. A vibration is audible on some recorders.

## 1.3 · The browser

Use **Chrome or Edge**, in a **fresh window** with no other tabs.

1. New window.
2. Hide the bookmarks bar — `Ctrl` `Shift` `B`.
3. **Set zoom to 250 %** — `Ctrl` `+` until the indicator reads 250 %.

   > This is a measurement, not taste. At 250 % the refusal banner and the SQLSTATE stay legible
   > in a small embedded player. **If something does not fit later, narrow DevTools — never
   > lower this zoom.**

4. **Do not change zoom, dock width, or window size once you start.** Any of the three reflows
   the page, and every timing on this sheet stops being true.

## 1.4 · DevTools — what it is, and why it is on camera

DevTools is the browser's built-in inspector. You are showing one panel: **Network**, which
lists every request the page sends to the server.

**Why it is in the film:** it is the proof that the refusal came from a real server round trip
and not from a pre-recorded animation. The judge watches the request go out and the answer come
back.

1. Press **`F12`** (or `Ctrl` `Shift` `I`).
2. **Dock it right** — the three-dot menu inside DevTools → *Dock side* → the right-hand icon.
3. Click the **Network** tab.
4. Tick **Preserve log** (a checkbox in the Network toolbar).
5. **Drag the divider** so DevTools takes about a quarter of the width and the permit form still
   has room to breathe without squashing.
6. **Leave it open for the whole take.**

> **Order matters.** DevTools is open **before** the first press, never after. A Network panel
> opened after a request already finished is indistinguishable from a screenshot — and looking
> like a screenshot is the one thing this film cannot afford.

---

# PART 2 · PRE-ROLL — the last two minutes

In order. Step 4 is the one people get wrong.

### 1 · Warm the server from a *different* tab

Open a **second** tab and load this once:

```
https://ihuuyvm4z6nfuktihnkey77fpy0eyrhj.lambda-url.ap-southeast-1.on.aws/v1/health
```

You should see `"ok": true`.

> **Never warm it from the tab you are about to film.** Pressing the demo in the filmed tab
> reveals the answers early and burns the take.

### 2 · In the same second tab, warm the change screen

Load this once and let it finish painting:

```
https://ihuuyvm4z6nfuktihnkey77fpy0eyrhj.lambda-url.ap-southeast-1.on.aws/operator.html#/change
```

This screen makes four requests one after another. Warmed, it paints in about **3.5 seconds** on
camera; cold it takes about **6**, and the block it lives in is only 12 seconds long. Warming
costs nothing here — none of those four requests changes anything.

### 3 · Close the second tab

All of it. One tab left.

### 4 · Load the permit screen fresh, in the tab you will film

```
https://ihuuyvm4z6nfuktihnkey77fpy0eyrhj.lambda-url.ap-southeast-1.on.aws/operator.html#/permit
```

**Check all four before continuing. If any is wrong, stop and tell me:**

- header reads **`DEMO-PTW-0001`**
- status chip reads **`dispositioned`**
- action bar reads **`1 obligation outstanding`**
- the address bar shows the URL above

### 5 · Pre-type two fields, completely

**Permit title** — type exactly:

```
Cold work — intrusive work inside the isolation boundary
```

**Location on site** — type exactly:

```
Within the isolation boundary declared on this permit
```

### 6 · Pre-type the *first half only* of the work description

**Work to be done** — type exactly this, then **stop**:

```
Open the guard and inspect; no work until
```

> **Stop after `until`.** No trailing space, no full stop, nothing after it. You type the rest on
> camera in Block B0, and it begins with a space.

### 7 · Do NOT pre-type the proposed wording

The change screen's *Proposed wording* box **cannot** be filled in advance. Navigating there and
back destroys and re-creates it empty. You type it on camera in B9. This is a measured fact about
the page, not a preference.

### 8 · Open DevTools now

`F12` → dock right → **Network** → **Preserve log** ticked. Leave it open.

### 9 · Do not reload the page from here on

A reload wipes everything you typed in steps 5 and 6.

### 10 · Start recording

Let it roll for **three seconds of stillness** before you touch anything — that gives you a clean
handle to trim to.

---

# PART 3 · THE TAKE, BLOCK BY BLOCK

Each block gives you **what is on screen**, **what your hands do and when**, and **what not to
do**. Timecodes run from the start of the film.

> **The most common mistake by far: moving the mouse during a hold.** When this sheet says stop
> moving, take your hand off the mouse completely. A drifting cursor during a silence kills it.

---

## B0 · 0:00 – 0:12 · The permit form

**On screen:** the filled-in permit form, except the end of the work description. Cursor resting
near **ISSUE**.

**Where to be when you start:** scrolled to **section 5, *Description of work to be done and its
limitations***, so the half-typed field is in frame. **Not** the top of the page.

| time | what you do |
|---|---|
| 0:00 – 0:05.5 | Nothing moves. The half-filled field is simply there, being read. |
| 0:05.5 – 0:08 | **Click into *Work and its limitations*** at the end of the existing text and type the tail below, on camera, at a normal pace. |
| 0:08 – 0:12 | **Stop moving.** Caret left blinking in the field. |

**Type this — it begins with a space:**

```
 verified at zero
```

The field then reads `Open the guard and inspect; no work until verified at zero`, which fits on
one line without wrapping.

**Do not:** press Enter or Tab afterwards. Leave the caret blinking in the field.

---

## B0b · 0:12 – 0:20 · Same frame, nothing moves

**This block is one slow scroll, and it is not filler.** The **ISSUE** button lives at the very
foot of a thirteen-section form — it is nowhere near the field you just typed in. You have to
travel, and the journey is the shot.

| time | what you do |
|---|---|
| 0:12 – 0:20 | **One continuous slow scroll down**, from section 5 to the foot of the form. Arrive with **`1 obligation outstanding`** and the **ISSUE** button in frame, and stop. |

**Scroll slowly enough to read.** On the way down you pass section 6, the hazard card carrying
`DEMO-INC-0001 · Stored energy release during intrusive work · 14 March 2019` — which is the exact
thing the voice is describing while you scroll past it. Do not race it.

---

## B1 · 0:20 – 0:30 · The press

| time | what you do |
|---|---|
| 0:20 – 0:21 | **Clear the Network list on camera** — the "no entry" circle at the left of the Network toolbar. Doing this on camera is what proves the row that follows belongs to *this* press. |
| 0:21 – 0:22 | Cursor to **ISSUE**, at the foot of the form beside `1 obligation outstanding`. |
| **0:22** | **Click 1 — press ISSUE.** |
| 0:22 – 0:24.5 | The button shows its pending state. One row appears: `POST /v1/demo/gate-run`. Measured warm at about **2.5 s**. Touch nothing while it flies. |
| 0:24.5 – 0:30 | The answer paints. **Stop moving.** |

**Do not:** click twice. Two POST rows contradicts a film that claims one press.

---

## B2 · 0:30 – 0:44 · The refusal

**On screen:** the red refusal band — **REFUSED**, **SQLSTATE 23514**, constraint
**`gate_closed_when_issued`**, and the line saying what would fix it.

| time | what you do |
|---|---|
| 0:30 – 0:34 | **Nothing.** Let the refusal sit. This is the film's first payoff. |
| 0:34 – 0:37 | One slow move to the Network panel, so the `POST` row and its `200` are readable. Rest about 2 seconds. |
| 0:37 – 0:44 | Move back to the refusal band. **Stop.** |

**Do not:** scroll. Everything needed is already in frame.

---

## B3 · 0:44 – 1:02 · The memory loop — **the most important block**

**On screen:** the hazard card in section 6. **The panels are labelled `RECALLED`, `SHOWN TO` and
`STATUS`** — those are the words actually on the page. *Store, retrieve, act* is our vocabulary for
them, not theirs, so do not go hunting for those three words.

This block does not fit in one frame, so it is **one slow continuous scroll** down the card.

| time | what you do |
|---|---|
| 0:44 – 0:50 | Start on the severity comparison — **`ON THE OBLIGATION 4`** above **`IN THE BLAME CLOSURE 4`**, with `ORIGIN blame_ancestry` beneath. This is the *"nobody typed that four"* evidence, so it gets read first. |
| 0:50 – 0:56 | Scroll slowly through **`RECALLED`** (the run that armed it) and **`SHOWN TO`** (`actor demo.signer`). |
| 0:56 – 0:59 | Arrive on **`STATUS ● OPEN — unanswered on this permit — no disposition of it is live`**, with the **`RECALL RUN STARTED · 10 s · OBLIGATION MATERIALISED`** panel below it. Both in frame together. |
| 0:59 – 1:02 | **Stop completely.** The voice says *"Nobody typed that four"* over a still frame. |

**That `10 s` panel is the single most important thing in the film** — two timestamps ten seconds
apart, one from the recall run and one from the obligation it created. Make sure it is legible and
make sure it is still on screen when the block ends.

**The contest rules specifically ask for footage showing the memory layer at work — this is that
footage.** If you get only one block perfect, make it this one.

**Do not:** move quickly between the three panels. A cursor that travels faster than a viewer can
read makes this block worse, not better.

---

## B4 · 1:02 – 1:12 · The attack

**On screen:** the panel showing the counter forced to **zero** from outside.

| time | what you do |
|---|---|
| 1:02 – 1:06 | Cursor to the forced **0**. Rest on it. |
| 1:06 – 1:12 | **Stop.** |

---

## B5 · 1:12 – 1:28 · Refused anyway — **the peak of the film**

**On screen:** the second refusal — **P0001**, from **`mainline.fn_permit_merge_gate`** — with
the message that the re-derived count is 1 while the projected counter reads zero.

| time | what you do |
|---|---|
| 1:12 – 1:17 | Cursor rests on the **P0001** message. |
| 1:17 – 1:18 | One small move to the re-derived count: **1**. |
| **1:18 – 1:28** | **TAKE YOUR HAND OFF THE MOUSE.** Ten seconds. No drift, no hover, no scroll. |

The voice delivers *"An attacker who owns the counter does not own the gate"* into that stillness.
**Any cursor movement here ruins the best ten seconds in the film.**

---

## B6 · 1:28 – 1:46 · The question, and signing it

**On screen:** the three question prompts, and the panel showing what each answer costs.

| time | what you do |
|---|---|
| 1:28 – 1:34 | Cursor rests on the **first prompt** — which isolation point was locked, and who verified it at zero. |
| 1:34 – 1:39 | One slow move down the cost rows — second signer, twelve-hour expiry. |
| 1:39 – 1:42 | Move to the **sign** control. |
| **1:42** | **Click 2 — sign.** |
| 1:42 – 1:46 | Let it answer. **Stop moving.** |

**Do not:** select a radio button on camera, and **do not** type into a citation box — this
deployment carries no answer for one, so anything typed there would be a prop.

---

## B7 · 1:46 – 1:58 · Admitted

**On screen:** **ADMITTED**, **SQLSTATE 00000**, and the post-merge fields.

| time | what you do |
|---|---|
| 1:46 – 1:52 | Cursor rests on the **panel rows** reading `permit state merged`. |
| 1:52 – 1:58 | **Stop.** |

> **Keep the cursor on the panel rows — never on the permit header.**
>
> The header does **not** change. It still reads `dispositioned`, ISSUE is still disabled, the
> lock note is still there. **That is correct** — the admission happened inside a transaction
> that was then rolled back — and the next block depends on it being visible.
>
> Do not go hunting for the form to "turn green". It does not, and making it appear to would be
> faking the shot.

---

## B8 · 1:58 – 2:04 · None of it persisted

**On screen:** `persisted: false`, and the note about one transaction, written then unwound.

| time | what you do |
|---|---|
| 1:58 – 2:01 | Cursor to `persisted: false`. |
| 2:01 – 2:04 | **Stop.** |

This is where B7's unmoved lock pays off: you showed an admission, and the world did not change.

---

## B9 · 2:04 – 2:16 · The other way in — the change screen

| time | what you do |
|---|---|
| 2:04 – 2:05.5 | Cursor to the app's own navigation bar. |
| **2:05.5** | **Click 3 — switch to the change screen.** Use the app's nav — **not** the address bar, **not** a reload. |
| 2:05.5 – 2:09 | The screen paints in four stages, about **3.5 s**, because you warmed it. **Touch nothing.** This pause is expected. |
| 2:09 – 2:10.5 | Scroll down until the **clause of record** and the **Proposed wording** box are in frame together. |
| 2:10.5 – 2:11 | Click into **Proposed wording**. It is empty. |
| 2:11 – 2:13.5 | **Type the string below**, whole, at a human pace. |
| 2:13.5 – 2:14 | Cursor to **Approve change**. |
| **2:14** | **Click 4 — Approve change.** |
| 2:14 – 2:16 | It flies. **Stop moving.** |

**Type this — the whole thing, nothing is pre-filled:**

```
Isolate and lock.
```

**Do not:** click *Compare with clause of record*. It is a real control and it is tempting, but
there is no room in this block, and reaching for it pushes your press past 2:14.

---

## B10 · 2:16 – 2:28 · Refused again

**On screen:** the second refusal — **23514** again, on a **different** constraint:
**`cr_gate_closed_when_merged`**.

| time | what you do |
|---|---|
| 2:16 – 2:22 | Cursor on the constraint name, so a viewer can read that it is a *different* name from B2's. |
| 2:22 – 2:28 | **Stop.** |

---

## k1 · 2:28 – 2:34 · The loop card

**On screen:** the summary — the incident, the lookup, ten seconds later the question, refused.

Nothing moves. Hand off the mouse.

---

## k2 · 2:34 – 2:44 · The stack card

**On screen:** the AWS and CockroachDB list, each row carrying its own verdict.

Nothing moves.

---

## k3 · 2:44 – 2:50 · The limit card

**On screen:** the line naming what this does not do.

Nothing moves.

---

## End card · 2:50 – 2:52

Two seconds, nothing moving. Then let it roll **three extra seconds** before you stop, so you
have a clean handle to trim to.

---

# PART 4 · WHEN SOMETHING GOES WRONG

| what happened | what to do |
|---|---|
| **You clicked twice — two POST rows** | Re-take the block. Two mutating presses contradicts what the film says. |
| **A request was slow and the block overran** | Keep going, re-take that block alone. **Never speed up your movements to catch up.** |
| **You typed the wrong thing** | Re-take that block. Do not fix it off camera and carry on. |
| **You reloaded the page by accident** | Back to pre-roll step 4, then redo steps 5 and 6. Everything typed is gone. |
| **DevTools got closed** | Stop. Reopen, dock right, Network, Preserve log — then re-take the block, because the page reflowed when it closed. |
| **The refusal did not appear** | Stop, and tell me before recording anything else. Do not press again. |
| **You moved the mouse during B5's silence** | Re-take B5. It is the best ten seconds in the film and it is worth the extra take. |

---

# PART 5 · BEFORE YOU CALL IT DONE

- [ ] Recorded at 2560 × 1440 — or your honest native resolution — at 30 fps
- [ ] DevTools open and docked right for the **whole** take
- [ ] Exactly the presses this sheet names, no extras
- [ ] B3 (the memory loop) is unhurried and the cursor never raced
- [ ] B5's ten seconds of stillness are genuinely still
- [ ] B7 never showed the permit header appearing to change
- [ ] Both typed strings exactly as printed here, including B0's **leading space**
- [ ] Cut to the voice, the whole thing runs **under 3:00**
