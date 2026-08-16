<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# CLICKS-CR — the pre-flight, the frame rules and the field paths for B9 and B10

**Worker W6** · the film blocks for use case two · cr-gate-route wave · 2026-08-16 ·
**reconciled to the two-block decomposition 2026-08-16**
**Live origin:** `https://ihuuyvm4z6nfuktihnkey77fpy0eyrhj.lambda-url.ap-southeast-1.on.aws`
**Surface filmed:** `<origin>/operator.html#/change` — the **Management of change** screen.
**Voice:** [`VO-DEMO-CR.md`](VO-DEMO-CR.md) §1, which itself inherits its words from
[`VO-DEMO.md`](VO-DEMO.md) §1 · **clearance:** [`CLAIMS-CLEARANCE-CR.md`](CLAIMS-CLEARANCE-CR.md)

> ### WHAT THIS FILE OWNS, AND WHAT IT STOPPED OWNING
>
> **`docs/demo/film/CLICKS.md` §5 is the choreography of record for `B9` and `B10`.** When this
> file was written it declared that it owned the operator actions for `B9`, `B10` and `B11` and
> that `CLICKS.md` owned `B0`…`B8` — **that ownership line went stale the same day**, because
> `CLICKS.md` landed full `B9` and `B10` sections of its own, written against a read chain it
> **measured twice against the live origin** (its M14) and against the two-block spine.
>
> **Two click documents describing one stretch of film is the same defect as two voice documents
> describing it, and it is resolved the same way.** `VO-DEMO-CR.md` §0.3 carries the ruling and the
> reasons. **What this file owns and is worth keeping for:** the frame rule in §3 and the evidence
> trap in §3.1, the field-path tables in §4, the executable pre-flight in §5, and the stop-the-take
> list in §6. **Where the two disagree about a cursor, `CLICKS.md` wins and this file is wrong.**
> §4.2 records the one place they **used to** disagree — where the press lands — together with the
> 2026-08-16 ruling that closed it, rather than quietly conforming and leaving no trace of either
> position.

**`claim_hygiene.py --check` verdict** for this file is recorded once, for the `-CR` files
together, in `CLAIMS-CLEARANCE-CR.md` §6, with its exit code. Re-run it after any edit —
"not scanned" and "passed" are different results.

---

## 0 · WHAT WAS MEASURED BEFORE THIS FILE WAS WRITTEN, AND WHAT WAS NOT

**Nothing in this file was driven.** This worker issued **no `POST`**, no `terraform` anything,
touched no AWS surface, read and wrote no SSM parameter, printed no credential, and created no
scratch database — no database work was required and an empty `w_W6` would have been a write with
no reader.

Everything below was checked against the tree and against measurements other workers took and
recorded. Each row says which.

| # | what was read | what it settled |
|---|---|---|
| M1 | `verticals/mainline/apps/console/src/operator/change/ChangeScreen.ts` | The screen's real structure: header, ribbon, then the five OSHA sections in order, then the action bar, then the raw-payload section. Every control label quoted below is one this module actually constructs. |
| M2 | `.../change/osha-sections.ts:57-67, 264, 291-301` | The five section headings are `29 CFR 1910.119(l)(2)(i)–(v)` verbatim; the clause of record renders under `Clause of record — current text, as returned`; the typed box is `id: moc-proposed-text`, label `Proposed wording`; the compare control is `Compare with clause of record`. |
| M3 | `.../change/absence.ts:408-454` | **The approve control is `Approve change`, and in the shipped bundle it is `disabled`, carries `aria-disabled="true"`, and is given no listener anywhere in that directory.** Its reason line composes from the live `open_blocking`. |
| M4 | `.../change/absence.ts:250-278, 511-579` | The screen already probes for CR check ids over the declared route table, and `renderDefeaterPrompts` is only ever called with options that came back from a live disposition read. Its legend is `Ways this obligation could be answered — each requires a citation`, and there is no `not applicable` option because the vocabulary contains none. |
| M5 | `.../change/absence.ts:322-378` (`renderObligation`) | **Today this panel states in its own words that the obligation's id, precursor, severity, virulence and defeater vocabulary are *not reachable from any declared route*, and shows none of them.** This is the R-5 problem in §5.4, and it is a real one. |
| M6 | `docs/demo/cr-gate-route-plan.md` §0.2 and `docs/demo/film-recut-plan.md` §1.3 — two independent live measurements this session | `POST /v1/change-requests/{cr_id}/merge` → **404**. `GET /v1/change-requests/{cr_id}/blocking-checks` → **404**. `GET /v1/change-requests/{cr_id}` → **200**. `GET /v1/checks/{check_id}/disposition` → **200**. |
| M9 | **`evidence/deploy/cr-gate-live.json`** — W5's transcript, which landed while this file was being written and was read in full | `phase: "baseline"`, `verdict: "UNANSWERABLE"`, `exit_code: 2`, `failures: []`, 14 of 14 assertions holding. `POST /v1/demo/cr-gate-run` → **404**; `cr_blocking_checks_declared` → **false**; `declared_path_count` → **17**. **There is no CR refusal transcript in it, because nothing is deployed that could produce one.** |
| M10 | the same file, `cr_read.body.data` | The values in §4.1 and §4.4 marked **measured** — the state, the counters, the four `cr_*` CHECKs with their predicates, and `blamed_by_refusal: false` on all four. |
| M11 | the same file, `subjects.body.data.clause_uuid` | **The clause the change request targets is the same identifier `B3` shows.** Half of R-5 is secured by measurement; §5.4 is the other half. |
| M7 | `docs/demo/film/CLICKS.md` §1 | The take's fixed settings — 2560×1440 at 30 fps, browser zoom 250 %, DevTools docked right leaving ≥ 760 CSS px, Preserve log ON, taskbar clock and URL bar never cropped. **This file changes none of them.** |
| M8 | `docs/demo/film/CLICKS.md` §1.3 | The change screen renders in its narrow (`max-width: 60rem`) layout at the take's geometry. That is a real responsive layout, expected, and not a window tuned to hide anything. |

**The consequence of M3 and M6, stated first because it decides whether there is a shot at all:
today there is no press to film.** The control is disabled by design and the route it would need
does not exist. §5 is the executable pre-flight that settles it on the day, and
`docs/demo/film-recut-plan.md` §6 is the fully specified NO-GO if it does not.

---

## 1 · WHAT DOES NOT CHANGE FROM `CLICKS.md`

These two blocks are shot **inside the same unbroken take** as `B0`…`B8`. Every setting in
`CLICKS.md` §1 was chosen before the red light and is not touched again: a dock change, a zoom
change or a window resize inside the take reflows the page underneath a claim, and a viewer cannot
tell that from an edit.

Four things stay in frame from the first frame to the last, exactly as `CLICKS.md` §1.4 fixes them:

1. **The URL bar** — now reading `…lambda-url.ap-southeast-1.on.aws/operator.html#/change`. Never
   cropped, never covered.
2. **The taskbar clock.**
3. **DevTools**, docked right, Network panel selected, **Preserve log ON** — so the `B1` request
   and the change-request attempt are both in the list, in order, for the whole of these two blocks.
4. **The synthetic watermark**, in the page's own words or in the burned-in strap, per
   `CLICKS.md` §1.4.

The page's **origin strip** at the foot of the document — `served from <origin>`, plus
`X-Mainline-Emulator` when one is present — is the film's honesty device: if the take is made
against the local node, that strip says so on screen, in the page's own words, and the film is not
passed off as the deployed one.

**Two requests in this film, not one.** `docs/demo/film-recut-plan.md` R-9 amends
`FALLBACKS.md` F-11 as a **tightening**: *exactly two mutating requests, each narrated while it is
in flight, each visible in the panel; any third row, or either row appearing without its narration,
stops the take.* That is strictly stronger than a one-request rule at two requests, and it is the
rule this file is scored against. **A third `POST` row in the Network panel stops the take.**

---

## 2 · GETTING TO THE CHANGE SCREEN — the seam out of B8

`B8` ends on the rollback proof. The shipped operator shell routes on the hash, and the change
screen mounts at `#/change`.

**The navigation is a click on the shell's own nav, not a typed URL and not a reload.** A reload
clears the Network panel's continuity, drops the `B1` request out of the story, and re-runs the
page's reads under a fresh clock — three witnesses lost to save nothing.

| t | action | what must happen |
|---|---|---|
| end of `B8` | cursor moves to the shell nav, single left click on the change entry | the URL bar's fragment changes to `#/change`; **no full page load**; DevTools' request list keeps every row already in it |
| — | the screen mounts and its reads fire | the reads appear in the Network panel as they land. **They are `GET`s and they are not narrated.** |

**Nothing is scrolled until the screen has finished rendering.** The change screen renders
absences while its reads are in flight (`Reading the change request…`, `Reading the clause of
record…`, `Reading the disposition lattice…`). Those are honest states and they are allowed on
camera; what is not allowed is scrolling past one so fast it reads as a flicker.

---

## 3 · THE FRAME RULE THIS FILE EXISTS TO ENFORCE

> ### ⛔ BOXED — THREE DIFFERENT OBJECTS, AND THE FRAME MUST NOT MERGE THEM

`cr_gate_closed_when_merged` is a **CHECK** on `mainline.change_request`
(`verticals/mainline/db/migrations/0051_change_request.sql:85`).
`cr_merge_gate` is a **TRIGGER** on the same table
(`verticals/mainline/db/migrations/0131_trg_cr_merge_gate.sql:38-41`).
`mainline.fn_cr_merge_gate` is that trigger's **function**
(`verticals/mainline/db/migrations/0116_fn_cr_merge_gate.sql`), and it is the object a `P0001`
names.

**Whatever is on screen at B10 is what the kernel put in the response field, rendered under a label
that says which field it came from.** No frame may caption a trigger name as a constraint name, or
the reverse. **This is the single most likely defect in this wave's on-screen text**, it is one
character wide, and it is checked in pre-flight (§5.3) rather than in the edit.

### 3.1 · ⛔ AND THE SECOND TRAP, WHICH IS IN THE EVIDENCE FILE ITSELF

`evidence/deploy/cr-gate-live.json` contains a `gate_run_summary` block carrying
`merge.sqlstate = "23514"`, `merge.constraint = "gate_closed_when_issued"` and
`projection_drift_attack.constraint = "mainline.fn_permit_merge_gate"`.

**Every one of those is the PERMIT'S**, from `POST /v1/demo/gate-run` — they are `B2`'s and `B5`'s
values, present in this file as the control that proves the origin was healthy while the CR probes
were answering `404`.

> **A frame built by reading `gate_run_summary.merge.sqlstate` renders the permit's refusal
> labelled as the change request's.** It would look right, it would pass every scanner in the kit,
> and it is one field name away from happening at 02:00. **B10's values come from the CR run's own
> merge beat and from nothing else.** Until that run exists, there is no value and there is no
> frame.

The film's standing frame rules still apply to both blocks, unchanged:

* **Every value on screen arrived over HTTP in this page load.** No fixture, no seeded constant, no
  fallback object, no default. When a read does not land, the screen renders an **absence** — never
  a placeholder that reads as data. That is the change screen's own rule 1 and it is why it is
  filmable.
* **Every server value carries a provenance chip and nothing typed does.** The convention a judge
  can check in two seconds, from `CLICKS.md` §4.
* **No proposed clause text exists in this deployment, so none is rendered.** The right side of the
  comparison has exactly one possible source and it is the `<textarea>` a human typed into.

---

## 4 · THE TWO BLOCKS

> **`CLICKS.md` §5 `B9` and `B10` carry the cursor path, the click numbers and the keystroke
> timings.** What is below is the **frame** each block must compose and the **field path** every
> value in it is read from — the half of the job that document does not do, and the half a
> pre-flight can actually check.

### B9 · THE OTHER WAY IN — `[2:04]` · 12 s

**Voice:** *"Fine. Then don't use the clause — change it."* ·hold 0.4· *"Same paragraph. Same
incident behind it. This request asks to edit it."* — `VO-DEMO.md` §1 `B9`, inherited.

#### 4.1 · The frame at the top of the block

Composed **before** the block starts, during the seam in §2. Visible, legible at the take's
geometry, and none of it moving:

| what | status | field path in `evidence/deploy/cr-gate-live.json` |
|---|---|---|
| `Management of change` | **measured** — a string the page constructs | `ChangeScreen.ts:249` |
| the external ref, `DEMO-MOC-0001` | **measured** | `cr_read.body.data.external_ref` |
| the state chip, `checks_materialised` | **measured** | `cr_read.body.data.state` |
| the header meta — `counters.open_blocking` `1`, `open_conflicts` `0`, `open_residue` `0`, `head_seq` `1`, `gate_epoch` `1`, `merged_commit` `null` | **measured** | `cr_read.body.data.counters.*`, `.head_seq`, `.gate_epoch`, `.merged_commit` |
| the branch line, `refs/changes/demo-0001  →  refs/heads/main` | **measured** | `cr_read.body.data.ref_name`, `.target_ref` |
| **the clause identifier** | **measured — and it is the identifier `B3` shows** | `subjects.body.data.clause_uuid` |
| the clause of record, verbatim, `SYNTHETIC —` prefix **uncropped**, and its printed label | **PENDING** — the clause-version read is not in the transcript today | the clause-version read |
| **the precursor beside the refusal** | **PENDING, and at risk** — it rides on the CR blocking-checks read, which is **not declared** (`why_unanswerable.cr_blocking_checks_declared` = `false`) | §5.4 is the check |

**RULING R-5, from `docs/demo/film-recut-plan.md` §2.4, is binding on this frame.** The shared
clause **and** the shared precursor `DEMO-INC-0001` must be legible in the same frame as the
change-request refusal, carrying the same identifiers a judge already read at `B3`. Without them
this is a second refusal rather than the same memory reaching a second subject, and the recut plan
says the wave should be abandoned rather than shot. **This is a condition on the shot, checked in
pre-flight, not a thing to notice in the edit.**

#### 4.2 · The actions — **`CLICKS.md` §5 `B9` is the version of record**

`CLICKS.md` spends all twelve seconds, and after the press ruling below it spends them as: cursor
to the app bar (`2:04.0–2:05.5`), **Click 5 — the module switch** (`2:05.5`), the four-read paint
it measured at ≈ 3.5 s warm (`2:05.5–2:09.0`), a wheel scroll to the clause of record and the
`Proposed wording` box — **that dwell is R-5's evidence and is not shortened** (`2:09.0–2:10.5`), a
click into the textarea (`2:10.5–2:11.0`), **the proposed wording typed on camera in 2.5 s**
(`2:11.0–2:13.5`), the cursor travelling to `Approve change` (`2:13.5–2:14.0`), and **Click 6 —
mutating request 2 of 2 — at `2:14.0`**, which is `+10.0` into the block. The request is in flight
`2:14.0 → 2:15.5`, the tail of *"…asks to edit it."* runs over that flight (R-9), and **the refusal
paints at `2:15.5`**, half a second before `B10`'s in-point.

**Three notes this file adds and `CLICKS.md` does not contradict:**

* **The typing cannot be pre-typed, and that is a measurement rather than a preference.**
  `CLICKS.md` measured that the textarea is destroyed and re-created empty when `B9` mounts the
  screen, so **the wording is typed on camera or it is not on screen at all.** The pre-typing
  convention `CLICKS.md` §1.5 step 3 uses for `B0`'s other fields **does not reach this box.**
* **No provenance chip appears beside the typed characters**, because nothing typed carries one,
  and the placeholder is gone the instant the first key lands — which is what stops a still frame
  reading the proposal as a stored value.
* **`Compare with clause of record` is not clicked**, and `CLICKS.md` records it as a trade rather
  than a prohibition: it is a real shipped control, it makes no request, and it is the single best
  show-don't-tell asset on that screen — **and there is no room for it**, because `B9`'s last five
  seconds are the typing, the press and the flight. **This file's earlier action table clicked it
  at `+5.5` inside a 10 s block.** That was one of the two documents' disagreements and it is
  resolved against this file.

> ### ✔ RULED, 2026-08-16 — **THE PRESS LANDS AT `2:14.0`, INSIDE `B9`.** This file's open item is closed
>
> **`docs/demo/shoot-docs-plan.md` `R-SD4` is the ruling and it is reproduced here rather than
> pointed at, because a shooting sheet nobody can read on its own at 02:00 is not a shooting
> sheet.** Click 6 — `Approve change` — is at **`2:14.0`**, `+10.0` into `b9`. The request is in
> flight `2:14.0 → 2:15.5`. **The refusal paints at `2:15.5`.** `B10` opens at `2:16.0` on a
> refusal that has already been on screen for half a second.
>
> **This file won on the merits and lost on its number, and both halves are stated.**
>
> * **UPHELD — the placement.** §4.2's position, the press inside `B9` under *"This request asks to
>   edit it."*, is the film's own grammar: `CLICKS.md` §5 `B1` already solves this problem once, with
>   Click 2 at `0:22.5` — `+2.5` into the 10 s attempt beat — and the refusal beat `B2` opening at
>   `0:30` **on a refusal that is already on screen**. `b9` is the attempt beat of use case two and
>   `b10` is titled *REFUSED AGAIN*. Choreographing the film's two mutating presses differently is
>   itself the defect: a judge watches the same act twice and the second one reads as edited.
> * **STRUCK — this file's `+7.4`.** It was scored against the **retired 10 s three-block `B9`**.
>   In the 12 s block `+7.4` is `2:11.4`, which is **in the middle of the typing**. The intent
>   survives; the number does not.
> * **STRUCK — `CLICKS.md`'s `2:17`.** It puts the SQLSTATE on screen **2.5 s after *"Refused."* is
>   spoken** at `2:16`, and R-K is absolute: a value is spoken while it is on screen or it is not
>   spoken. R-9 also requires each mutating request to be narrated **while it is in flight**, which
>   only the `B9` placement gives. **Neither sheet's number survived; the placement of one did.**
>
> **What it costs, and the cost is this file's to carry.** The typing window falls from 5.0 s to
> **2.5 s**, and `b9`'s 1.1 s of slack (`VO-DEMO.md` §2:595) is re-purposed from *the typed
> proposal settling* to *the answer landing*. **R-2 is satisfied by the act of typing into the
> console's own input with no provenance chip — it has never required a character count** — so a
> shorter honest proposal discharges it identically. If 0.5 s more is needed it comes from the
> app-bar travel (`1.5 s → 1.0 s`), which still proves no cut. **It never comes from the scroll
> dwell (R-5's evidence) and never from the read chain (M8/M14, incompressible).** §5.6 is the
> stopwatch check that settles it before the red light, and `R-SD4a`'s floored 0.4 s fallback —
> with the `D31` collision it creates — is priced in `VO-DEMO-CR.md` §1.
>
> **`CLICKS.md` §5 remains the version of record for cursors, click numbers and keystroke
> timings.** This box records a ruling that both files now implement; it does not take that
> ownership back. Where the two still disagree about a cursor, `CLICKS.md` wins and this file is
> wrong.
>
> **`R-SD4b` — and it is not a footnote.** The whole ruling is **conditional on `FALLBACKS.md`
> §4.2's `R-11` gate**, which is a **NO-GO today**: `POST /v1/demo/cr-gate-run` `404`,
> blocking-checks `404`, the approve control hard-disabled, and `DEMO-INC-0001` occurring **zero**
> times on the change screen, so `G5`/R-5 fails. **On the no-go path there is no Click 6 at all** —
> the ledger is five clicks and one text entry, §6 row 1's two-request rule (R-9's tightening of
> `FALLBACKS.md` F-11) reverts to **exactly one** mutating request, `b8` returns to 10 s and the
> film is 152 s (`SPINE.md` §5.1). A press timed to a tenth of a second in a
> block that is not shot is not a plan; it is the second document this wave describing a film that
> does not exist.

**MUST NOT DO:** narrate the typing, or say anything that gives the typed words the status of data.
**MUST NOT DO:** press `Approve change` twice. **MUST NOT DO:** open a second tab.

---

### B10 · REFUSED AGAIN — THE MIRROR — `[2:16]` · 12 s

**Voice:** *"Refused. Same **SQLSTATE** — a different constraint guards edits."* ·hold 0.6·
***"You can't just use the clause. You can't quietly edit it away."*** — `VO-DEMO.md` §1 `B10`,
inherited. **The block runs refusal → hold → mirror without a boundary in it**, which is
`VO-DEMO-CR.md` §0.3's ruling and the reason its two frames are described together below.

#### 4.3 · The actions

**`CLICKS.md` §5 `B10` is the version of record.** Its shape, in one line, **re-anchored to the
`R-SD4` ruling above**: the block **contains no press and no pending state** — both are `B9`'s, and
the refusal painted at `2:15.5` — so it opens on a refusal already composed, then the cursor
**points** down the refusal band without clicking or selecting (`2:18.5–2:22`), then travels left
and up to the three prompt cards without leaving the frame (`2:22–2:26`), then **stops** for the
mirror (`2:26–2:28`).

| # | t | action | what must happen on screen |
|---|---|---|---|
| 1 | `+0.0` = `2:16.0` | **nothing.** The founder's hands left the mouse at `2:14.0` and have not come back. | **the answer has already landed.** The Network row went from pending to its status at `2:15.5`; the refusal band composed itself from the response between `2:15.5` and `2:16.0` and is on screen when *"Refused."* is spoken (R-K). Nothing in this block is waiting for a response. |
| 2 | `+2.5` | cursor rests — does not click, does not select text — beside the constraint name | the name is legible and its label says which payload field it is |
| 3 | `+6.0` | **one movement, slow, and it stops** — to the three defeater prompts, **with the refusal band still in frame** | both in one frame. If they will not both fit at the take's geometry, §5.5's ruling applies. |
| 4 | `+10.0` | **nothing.** No cursor movement, no click, no hover, for the rest of the block. | the frame holds through the mirror and through the silence after it |

**There is no click in this block.** The only correct operator action while a refusal is being read
is to stop moving.

**The silence at the tail is a scripted element with a duration, not a pause an editor may
tighten.** It is where a viewer works out what just happened, and a viewer who works it out
themselves is a viewer who believes it. **MUST NOT DO:** cut to the close over the mirror line. The
close card lifts into the hold, after the last word, or the hold is not a hold.

#### 4.4 · The frame, and every value's field path

Per `VO-DEMO-CR.md` §6, and **a value that is still PENDING on the day the film is cut does not go
on camera.**

| on screen | status | source |
|---|---|---|
| the four `cr_*` CHECK constraints with their predicates and the counters each reads | **measured** | `cr_read.body.data.constraints[]` — `cr_gate_closed_when_merged` with `CHECK (((state != 'merged'::mainline.subject_state) OR (open_blocking = 0)))` and `open_blocking = 1`, plus `cr_merge_evidence`, `cr_conflicts_resolved_when_merged`, `cr_identity_conserved_when_merged` |
| the caption saying the predicates were read out of `pg_catalog` at request time | **measured** | `cr_read.body.statement_refs[1]` names `pg_catalog.pg_constraint` |
| `blamed_by_refusal` | **measured — `false` on all four today** | `cr_read.body.data.constraints[*].blamed_by_refusal`. It turns true when a refusal names one. **Leave it in frame; say nothing about it.** |
| the SQLSTATE — **the one value also spoken** | **PENDING** | the CR run's merge beat — **never `gate_run_summary`, see §3.1** |
| the constraint name **as the refusal reports it** | **PENDING** | the same beat, cross-read against the measured row above |
| `constraint_source` | **PENDING** | the same beat |
| the refusal's own message | **PENDING** | the same beat |
| the re-derived count beside the projected one | **PENDING** | the run's read beat |
| the beat's own `statement` and `label`, verbatim | **PENDING** | the same beat |
| `verdict` | **PENDING** | the run |
| per-beat elapsed, **labelled as the server's** | **PENDING** | the run |

**`constraint_source` goes on screen whatever it says.** If it reads `parsed` rather than
`reported`, the label says `parsed` and the frame is weaker. **Leave the weakening on screen** —
`B5` already set that precedent, and a demo that downgrades its own exhibit is not one anybody
believes is faked.

**The projection-drift beat is on screen and is never narrated.** It is in the transcript panel with
its own statement and label, in payload order, where a judge can read it, pause on it and press the
endpoint themselves. **Speaking a second `P0001` twenty seconds after `B5` does not double `B5`; it
halves it.**

**If a beat is absent from the payload, nothing stands in for it.** `docs/demo/cr-gate-route-plan.md`
§R3 makes the kernel-procedure beat conditional and drops it if the deployed cluster answers a
privilege error rather than a gate refusal. **A privilege error is not a gate refusal and is never
rendered as one.** An absent beat is absent on screen; there is no placeholder, no "skipped" row and
no gap dressed as a pass.

**If `verdict` is not the caveat-free one, it still goes on screen as returned.** A run that
answered something other than what it was written against still returns its verdict, and showing it
is the whole discipline. A beat is never declared successful because it did not raise.

#### 4.5 · ⚠ THE MIRROR'S SPOKEN LINE — the correction this file owed

**This file's `B11` section carried, as its `Voice:` line, a sentence the film's own registers
bar.** The block is gone and so is the line; both are printed here rather than deleted, because a
correction nobody can see is a correction nobody can check.

**Before:**

> ~~**Voice:** *"You can't use the clause."* ·hold 0.4· ***"You can't quietly edit it away
> either."***~~

**After — `VO-DEMO.md` §1 `B10`'s tail, cleared at `CLAIMS-CLEARANCE.md` `D32` and `D33`:**

> **Voice:** *"You can't **just** use the clause. You can't **quietly** edit it away."*

**Why the old first half is barred, and it is a frame problem as much as a claim problem.**
`B7` shows the permit **ISSUED** on that same clause thirty seconds earlier, once its obligation
was answered. The unscoped sentence is therefore contradicted by the film it is spoken in — and
this document is the one that decides what is in the frame, so it is the document with the least
excuse for it. **Both scope words are load-bearing:** *just* says the clause is usable but not
unanswered; *quietly* says it is editable but not unanswered. **MUST NOT DO:** shoot a take in
which either adverb is missing — the take goes, not the line.

#### 4.6 · The frame at the tail of the block

| on screen | field path (**PENDING**) |
|---|---|
| the refusal band, still — SQLSTATE, constraint name, predicate | as §4.4 |
| the three defeater prompts, **verbatim**, under the screen's own legend `Ways this obligation could be answered — each requires a citation` | the disposition read → `data.defeater_options[].prompt` and `.defeater_code` |
| the clearance lattice beside them | the same read → `data.lattice[]` |
| the obligation's severity, origin and virulence | the blocking-checks read — **on screen only; never spoken** (`VO-DEMO-CR.md` §3) |
| the clause identifier and `DEMO-INC-0001`, still legible | R-5, §4.1 |
| `persisted`, `self_persisted`, `isolation`, `single_transaction`, the two logical timestamps | `data.persisted`, `data.persistence_check.self_persisted`, `data.transaction.*` |

**No `not applicable` option is rendered, because none exists in the vocabulary.** Inventing one
would let an engineer dismiss the obligation without answering it, which is the entire failure this
system exists to prevent. The screen's own note says so in its own words and it stays in frame.

**The citation boxes are empty and their placeholder says why** — `typed by the engineer — this
deployment carries no answer`. **MUST NOT DO:** type into one on camera. Nothing in this deployment
carries an answer and a typed citation would be a prop.

**MUST NOT DO:** cut to the close over the mirror line. The close card lifts into the hold, after
the last word, or the hold is not a hold.

---

## 5 · PRE-FLIGHT — the six things settled before the red light

Every one of these is a `GET`-only check or a look at a rendered screen. **None of them is a
`POST`, and none of them is run from the tab that is about to be filmed** — a press in the filmed
tab reveals the beats and burns the take, exactly as `CLICKS.md` §1.5 step 1 says.

### 5.1 · The route exists and the control drives it

```
POST /v1/demo/cr-gate-run                        → 200, persisted:false measured from a fingerprint
GET  /v1/change-requests/{cr_id}/blocking-checks → 200
GET  /operator.html                              → the approve control is enabled and calls that endpoint
```

**MEASURED TODAY, AND THE FIRST TWO DO NOT HOLD.** `evidence/deploy/cr-gate-live.json`:
`cr_gate_run_probe.status` = **404**; `cr_blocking_checks.status` = **404**;
`why_unanswerable.declared_path_count` = **17**; `why_unanswerable.cr_blocking_checks_declared` =
**false**; the file closes `verdict: "UNANSWERABLE"`, `exit_code: 2`. **These two blocks cannot
be shot today.** W5's own sentence for why that is a different finding from a gate that failed to
refuse is at `why_unanswerable.this_is_not_a_gate_that_failed_to_refuse`, and this file does not
soften it.

**If all three do not hold, use case two is NO-GO** and `docs/demo/film-recut-plan.md` §6 is the
fully specified path — `B9` and `B10` are never added, `B8` is restored to 10 s, and the
film runs `2:32`, comfortably legal, with every service and feature still named. That is a
legitimate outcome and not a failure.

**Under NO-GO nobody builds a committing route, enables the approve control without the demo-safe
endpoint behind it, or grants `mainline_api` a write it does not hold today.** The standing
`transitions.materialise_checks` INSERT-without-privilege finding stays open and is not this wave's
to close. The demo guard's `423 Locked` stays.

### 5.2 · The blocking-checks panel renders clean

`GET /v1/change-requests/{cr_id}/blocking-checks` `404`s today (M6, and M9 confirms it is **not
declared**, not merely unanswered) and the change screen probes it (M4). **Anyone who opens that
screen on camera right now films a panel rendering an absence.** If
the route has not landed, the screen is filmed **only** in the state that renders clean, or not at
all — never scrolled past quickly so the absence does not register.

### 5.3 · The three object names are checked against the response, once, out loud

Open the payload the pre-flight press returned. Read the constraint field. Confirm the frame's
label for it says *constraint*, and that no frame anywhere in the block captions a trigger name as
a constraint name or the reverse (§3). **One person says the three names aloud and a second person
confirms them against the payload.** This costs thirty seconds and it is the only defence against a
one-character claim the kernel does not make.

### 5.4 · R-5 — the shared clause and the shared precursor are actually in the frame

**This is the check most likely to fail, and it will fail silently.** M5 measured that today's
obligation panel states in its own words that the obligation's precursor and severity *are not
reachable from any declared route*, and renders neither. R-5 needs `DEMO-INC-0001` beside the CR
refusal, which means it must arrive on the new blocking-checks read and be rendered.

**Half of R-5 is already secured by measurement.** `subjects.body.data.clause_uuid` in W5's
transcript is the identifier the change request targets and it is the one `B3` shows (M11). The
half that is not secured is the precursor, and it rides on the read that is not declared.

Confirm by eye, on the loaded screen, before rolling:

* the clause identifier is legible, and it is the same one `B3` showed;
* the precursor is legible, and it is the same one `B3` showed;
* both are in the same frame as the refusal band at the take's geometry.

**If they are not:** `VO-DEMO-CR.md` §4 assumption 4 applies — `B9`'s *"Same incident behind it"* is
cut, and `film-recut-plan.md` R-5 says the wave is abandoned rather than shot without it.

**One trap that only bites here.** `r6-honesty.md` A3 records that the staged propagation payload
reuses `DEMO-INC-0001`'s identifier while titling it after a **different** year from the one on
screen at `B3`. **The two must never be in the same shot**, and the staged one is never narrated.
Confirm the change screen does not render that title anywhere in frame.

### 5.5 · The refusal and the defeaters fit in one frame

At the take's geometry the change screen renders in its narrow layout (M8). Confirm in pre-flight
that one slow scroll brings the three prompts into frame **with the refusal band still visible.**

**If they will not both fit, the fix is the dock, never the zoom.** Narrow the DevTools panel to
widen the page, exactly as `CLICKS.md` §1.3 rules — lowering the zoom loses the legibility floor
`CLICKS.md` §1.2 measured, at which the SQLSTATE value itself falls below readable. **If it still
will not fit, `B10` holds the refusal band through its first sentence and the prompts are reached
by a second slow movement inside the 0.6 s hold — and the tail silence moves to the close.** It is
never solved by cropping the refusal out from under a sentence that refers to it. **`CLICKS.md`
§5 `B10` is stricter and it wins: if the refusal and the three prompts will not compose in one
frame, `B10` does not shoot.**

### 5.6 · The proposed wording types legibly in **2.5 s** — with a stopwatch, before the red light

**This check exists because of `R-SD4`, and it is the one thing that ruling costs.** Click 6 at
`2:14.0` leaves the typing exactly **`2:11.0 → 2:13.5`**, and a string that overruns it does not
fail gracefully: it either pushes the press past `2:14.0`, which walks the refusal into
*"Refused."*, or it is finished off camera, which R-2 forbids.

**`CLICKS.md` §5 `B9` owns the proposed wording string and states it with its character count.**
This check does not choose the string; it proves the stated one is typeable.

Rehearse it, on the loaded change screen, at the take's own geometry — 2560×1440, browser zoom
250 %, DevTools docked right (`CLICKS.md` §1) — because a string that types in 2.5 s on a bare
desktop can wrap and re-flow in the narrow layout (M8):

1. Caret in the empty `moc-proposed-text` box, as `B9` leaves it at `2:11.0`.
2. **Start the stopwatch, type the string `CLICKS.md` §5 `B9` states, stop the stopwatch.**
   At a human rate, on camera, not at a demo-typist's rate nobody will reproduce under the light.
3. **Read the result back on screen** — the last character legible, no truncation, no wrap that
   hides the tail behind the action bar.
4. Repeat it three times and take the **slowest**, not the best.

| result | what happens |
|---|---|
| **≤ 2.5 s** | shoot it. Nothing moves. |
| **≤ 3.0 s** | reclaim the 0.5 s from the app-bar travel (`1.5 s → 1.0 s`, `R-SD4`). The travel still proves no cut. **Never from the scroll dwell (R-5) and never from the read chain (M8).** |
| **> 3.0 s** | **shorten the string first** — R-2 is satisfied by the act of typing with no provenance chip and has never required a character count. Only if no honest string fits does `R-SD4a`'s floored slip apply: `B10`'s first word may move by **at most 0.4 s**, putting Click 6 at `2:14.4` and the typing at 2.9 s. |

> **`R-SD4a`'s 0.4 s is a floor, not a preference, and it cannot be spent twice.** Beyond it the
> 0.6 s mirror hold or the spoken `SQLSTATE` pays, and both are protected. Spending it here also
> **forecloses `CLAIMS-CLEARANCE.md` `D31`** — the `~ REWORD` of *"guards edits"* to *"guards the
> change"*, priced in `VO-DEMO.md`'s head note at 21 words running **1.13 s against 0.95 s of
> slack**. `VO-DEMO-CR.md` §1 carries the arithmetic. **The film lead spends the 0.4 s on the press
> or on `D31`, says which before the take, and does not discover the collision on the day.**

**And this check is `R-11`-conditional like everything else in §4.2's box.** If the gate in
`FALLBACKS.md` §4.2 is a NO-GO, there is no press, no typing window and nothing here to rehearse —
the change screen is filmed read-only under `FALLBACKS.md` F-17, or not at all.

---

## 6 · WHAT STOPS THE TAKE

Pre-committed, so nobody weighs a beat against the rubric at 02:00.

| # | condition | why |
|---|---|---|
| 1 | **a third `POST` row in the Network panel** | `film-recut-plan.md` R-9's tightening of `FALLBACKS.md` F-11. Two mutating requests, each narrated in flight, each visible. A third row is unaccounted-for work on screen. |
| 2 | **either `POST` row appearing without its narration** | same rule. A request nobody spoke over is indistinguishable from faked sequencing. |
| 3 | **the approve control rendering enabled while pointing at nothing** | a button that refused a different record would be a prop, and the shipped screen says so in its own words. |
| 4 | **the refusal band rendering a value with no field label** | the whole convention is that a judge can trace every string on screen to a payload field. |
| 5 | **a staged, mocked or hard-coded refusal, in any form** | the contest's Functionality requirement says the project must function as depicted in the video. A staged beat is a rules violation, not merely a dishonesty. |
| 6 | **the `SYNTHETIC —` prefix cropped out of the clause text** | it is never cropped to make a frame prettier. |

| 7 | **either mirror adverb missing from the take** — *just*, *quietly* | §4.5. Without them the sentence is contradicted by `B7`, which the same film shows thirty seconds earlier. R-7, and the refusal is final. |

**A `40001` serialisation retry is not on this list.** It is pressed again on camera, the retry is
not cut out, and it costs its own seconds out of the film's margin — never out of `B10`'s mirror.
