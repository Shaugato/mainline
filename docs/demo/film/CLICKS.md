<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# CLICKS — every cursor movement, click and keystroke, in one unbroken take

**Written by W4 · story-and-script wave · 2026-08-15**
**Re-timed and extended by W5 · film-re-cut wave · 2026-08-16**
**Binding on this file:** `docs/demo/film-recut-plan.md` §1.4, §4.1, §4.2 and §6, and rulings
R-2, R-4, R-5, R-9 and R-10 in that document; `docs/demo/film/BEATS.yaml`, which is the
timing authority and wins over this file wherever they disagree; and the surviving rulings of
`docs/demo/story-and-script-plan.md` §4 (R-C, R-D, R-G, R-H, R-I, R-N).
**Live origin:** `https://ihuuyvm4z6nfuktihnkey77fpy0eyrhj.lambda-url.ap-southeast-1.on.aws`
**Operator surface filmed:** `<origin>/operator.html#/permit` and `<origin>/operator.html#/change`

**`claim_hygiene.py --check` verdict**, run this session on this file after the re-cut edit and
pasted verbatim:

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

This is the operator's score: for each of the **twelve** beats, the literal window state, the
literal cursor path, the literal click or keystroke, and the render the screen must produce
in answer. It is written to be executed by one person, in one take, without a decision left
to make at 02:00.

**It is not a wish-list against an imaginary UI.** The operator surface exists and has been
captured. Rows M1–M6 were read by W4 on 2026-08-15; rows **M7–M14 were re-measured by W5
against the live origin on 2026-08-16**, because the brief for this wave described the
change-request surface and a description is not a measurement.

| # | what I read | what it settled |
|---|---|---|
| M1 | `evidence/demo/operator-capture.json` — W7's capture of the built screens against `scripts/deploy/local_furl.py` over the local node, with the whole rendered DOM at five stages | Every control label, section order and rendered string quoted below for the **permit** screen is one the built page actually produces. Nothing there is a sketch. |
| M2 | `evidence/deploy/live-gate-run.json` — the recorded four-beat payload | Every SQLSTATE, constraint name, message, statement and field name quoted below is one the kernel returned. |
| M3 | `src/operator/issue/disclosure.ts`, `ActionBar.ts`, `pending.ts`, `route.ts`, `chrome/chrome.css`, `permit/typed-fields.ts` | The reveal mechanics, the pending label, the router's teardown behaviour, and the fact that no element on the page is `position: sticky` or `fixed`. |
| M4 | the capture's `geometry` block | The video's zoom. W7 measured a legibility floor of 2 % of frame height per em and found that at 200 % browser zoom the SQLSTATE value, the reason set and the disclosure line **all fail it**. See §1.2. |
| M5 | the capture's `assertions` block | `one-press-one-request` held; `never-the-merge-route` held; `reveal-3-made-no-request` and `reveal-4-made-no-request` held at 30 ms and 33 ms; **`raw-payload-drawer-is-byte-identical` did NOT hold** (§7 D-3). |
| **M7** | `GET /operator.html` on the live origin | **200, 5,097 bytes, `<title>Control of Work`.** No longer byte-identical to `GET /` (4,749 bytes) — the two now differ in both length and digest. It loads `assets/operator-<hash>.js` (**96,734 bytes**) and `assets/operator-<hash>.css` (33,043 bytes). **`CLAIMS-CLEARANCE.md` condition 1 — "the film scored in CLICKS.md has no pixels on this origin today" — is CLOSED.** See §7.1. |
| **M8** | the deployed operator bundle, read end to end | The change screen is **complete and shipped**: five OSHA §1910.119(l)(2) sections, the IChemE ribbon, three typed textareas, a clause-of-record quote, an in-browser comparison, a lattice table, a disabled approval bar and four raw-payload drawers. §5 B9/B10 is scored against **that bundle's own construction order**, function by function, not against a description of it. |
| **M9** | the same bundle, at the approval control | **The approve control is hard-disabled in the shipped bytes** and never becomes enabled: it is constructed `disabled`, with `aria-disabled` true, and **there is no change-request merge call anywhere in the bundle.** It renders its own reason — `Cannot approve. 1 blocking obligation is outstanding on this change request.` — then the constraint name, the predicate, the table it came from, and the sentence that the control *"is disabled because no route exists to drive it, and it is wired to nothing."* |
| **M10** | `GET /v1/change-requests/{cr_id}/blocking-checks` on the live origin | **404, 693 bytes** — and the body is a `no_route` envelope that **enumerates all 17 declared routes**. The bundle parses exactly that body and renders the route table from it. **The panel is therefore NOT broken.** It is designed around this 404 and states the absence in its own words. See §7.2 — the 404 is not a cosmetic defect, it is the thing that makes R-4 and R-5 unmeetable. |
| **M11** | `GET /v1/checks/{check_id}/disposition` for **both** check ids | Two different vocabularies under two different `vocab_sha256` values. The change request's own obligation `dec0de00-000d-…` returns `CONTROL_PRESERVED_BY_EDIT` / `EDIT_OUTSIDE_BLAMED_ANCHOR` / `PRECURSOR_ANSWERED_ELSEWHERE`. The permit's check `dec0de00-0007-…` returns the three isolation questions B6 already films. **They are not interchangeable and filming one while speaking of the other would be a fabricated exhibit.** |
| **M12** | the bundle's check-id resolution, traced | Today the change screen reads the disposition of **`dec0de00-0007-…` — the permit's check — not the change request's.** Its own discovery walk finds no declared route that returns a change request's checks, so it falls back to the addressable id **and says so on screen**: *"This change request's own obligation is not addressable from any declared route, so the read above was made against the check that is addressable. Nothing is claimed here about this change request's obligation."* |
| **M13** | `POST /v1/demo/cr-gate-run` on the live origin | **404.** The demo-safe change-request attempt endpoint is named and specified in `scripts/proof/cr_gate_refusal.py` — three beats `read` / `merge` / `projection_drift_attack`, no admission beat, `persisted` false measured from two fingerprints — but **it is not deployed.** Plan §6's decision gate therefore **fails on all three legs today.** |
| **M15** | `app.ROUTES` and `reads.py` in the tree, against the origin's own declared list | **THE TREE AND THE ORIGIN DISAGREE, AND THE ORIGIN IS WHAT THE FILM MEASURES.** Both missing routes — `POST /v1/demo/cr-gate-run` and `GET /v1/change-requests/{cr_id}/blocking-checks` — are **declared and implemented in the tree today**, and the second returns an envelope whose `checks[].check_id` is exactly what the console's own reader parses. They are **built and undeployed**. So the §6 decision gate is a **deploy-and-re-measure**, not a build. **This does not soften anything below:** a route in the tree is not a route on the origin, the film is shot against the origin, and B10 does not shoot until the origin says 200. |
| **M14** | the change screen's read chain, timed twice against the live origin | Four **sequential awaited** GETs — change request, the blocking-checks probe, the clause version, the disposition — total **≈ 3.5 s warm**, painting the page in four visible stages. `GET /v1/demo/subjects` is memoised at module scope and is **not** re-read on the module switch. This is a third of B9's budget and §5 B9 is scored around it. |

Four things the capture proves that this document then depends on: one press makes exactly
one request; the two reveals make none; the reveals are ~30 ms, not a fake 400 ms wait; and
no request to the permit merge route occurs in the whole page load.

**Alignment with the spine.** `BEATS.yaml` was re-cut on 2026-08-16 to twelve beats. `B0`,
`B0b`, `B1`…`B10` here are its `b0`, `b0b`, `b1`…`b10`, and every in-point, duration and
end-point below matches it exactly (`0 / 12 / 20 / 30 / 44 / 62 / 72 / 88 / 106 / 118 / 124 /
136 / 148`). Its two `never_cut: true` beats — `b3` and `b5` — are the two beats scored here
with no click in them at all, which is not a coincidence: the beats that may never be cut are
the beats where the only correct operator action is to stop moving.

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
2. Confirm the longest evidence line wraps **at most once**: the beat-2 `message` is the line
   to test. It measured **111 characters** on the live payload this session — W4's score
   recorded 108 against an earlier run, and the drift is the point: **measure it on the day's
   own payload rather than trusting either number.** §6 rule 5 applies to this document as
   much as to the film.
3. If either fails, widen the page by narrowing the dock — **never by lowering the zoom**,
   which loses the legibility floor measured in §1.2.

The change screen at B9/B10 will render in its narrow (≤ 60 rem) layout. That is fine and
expected; it is a real responsive layout, not a window tuned to hide anything.

**And one thing the dock cannot fix, measured this session (M8).** The change screen's DOM
order is fixed by the bundle:

```
header (external_ref · ref_name → target_ref · opened_at, gate_epoch, head_seq,
        merged_commit, counters.open_blocking / open_conflicts / open_residue)
IChemE ribbon + the state chip
§1  The technical basis for the proposed change          ← two typed textareas
§2  Impact of change on safety and health                ← the counter, the CHECK-constraint
                                                            table, and (only if the change
                                                            request's own checks become
                                                            addressable) the three defeater
                                                            prompts
§3  Modifications to operating procedures                ← clause of record, the PROPOSED
                                                            WORDING box, the compare control
§4  Necessary time period for the change
§5  Authorization requirements for the proposed change   ← the lattice table
    the approval bar + "Why there is no approve action here" + the route table + the
    verbatim 404 body
    four raw-payload drawers
```

**§2, §3 and the approval bar are three sections apart.** No zoom setting and no dock width
brings all three into one frame, because the separation is DOM order, not scale. R-5 requires
two identifiers in frame **with the refusal**, and §7.2 is the escalation that follows from
it. Do not attempt to solve this by zooming out; §1.2 is a floor, not a preference.

### 1.4 The four things in frame from the first frame to the last

1. **The URL bar**, reading `…lambda-url.ap-southeast-1.on.aws/operator.html#/permit`, and
   from B9 onward `…#/change`. Never cropped, never scrolled past, never covered by an
   overlay. **The host in frame never changes** — the module switch changes the hash only.
2. **The taskbar clock.**
3. **DevTools**, docked right, Network panel selected, **Preserve log ON**.
4. **The synthetic watermark.** The page's own strip reads
   `SYNTHETIC DEMONSTRATION — no real site, no real permit, no real person` — but it is a
   normal flow element at the top of the shell and **scrolls out of frame** (§7 D-1). Until it
   is made sticky, the burned-in strap carries the same words for the beats that are scrolled
   away from the top of the document. **This matters more from B9 on, not less:** the clause
   of record's own text and the incident title both begin `SYNTHETIC —`, and those prefixes
   are the honesty device at exactly the moment the film is talking about editing a safety
   rule.

The page's own **origin strip** — `served from <origin>` plus `X-Mainline-Emulator` when one is
present — sits at the very bottom of the document. It is the film's honesty device for plan
R-N: if the take is made against the local emulator, that strip says so **on screen**, in the
page's own words, and the film is not passed off as the deployed one.

### 1.5 Pre-roll, in order — the last ninety seconds before the red light

The order matters, step 4 is the one people get wrong, and **step 3 now carries a hard limit
that did not exist before the re-cut**.

1. **Warm the endpoint from a different tab or a different browser**, once, within 60 s of the
   take (a cold press pays ~6.5 s). **Never warm it from the tab you are about to film**: a
   press in the filmed tab reveals the beats and burns the take.
2. **Close that tab. Load the operator page fresh** at
   `<origin>/operator.html#/permit`. Confirm the header renders `DEMO-PTW-0001`, the status
   chip reads `dispositioned`, the action bar reads `1 obligation outstanding`, and the origin
   strip names the origin you expect.
3. **Pre-type the two permit fields that are not typed on camera** — element 1 *Permit title*
   and element 3 *Location on site*. Element 5 is pre-typed **except its last few words**,
   which are typed on camera in B0. A page reload clears all three, so this is the last step
   that can be undone by a refresh.

   > **THE PROPOSED WORDING IN B9 CANNOT BE PRE-TYPED, AND THIS IS A MEASUREMENT, NOT A
   > PREFERENCE.** Pre-typing it would mean visiting `#/change` before the take and returning
   > to `#/permit`. The router **tears the screen down on a hash change** (§3, fifth box), so
   > the textarea is destroyed and re-created empty when B9 mounts the screen again. There is
   > no path by which that box holds text before B9 begins. **It is typed on camera or it is
   > not on screen at all** — which also means the cut ladder's rank-1 saving on `b9` cannot
   > be taken by arriving pre-composed. §7.3 escalates that to W1.
4. **Warm the change screen's read chain from the same second tab** used in step 1, then close
   it. The four reads total ≈ 3.5 s warm and ≈ 6 s cold (M14); B9 has 12 s and cannot pay the
   cold price. Warming a **read-only** chain reveals nothing and burns no beat — this is the
   one thing in the film that may be warmed without cost, because none of it mutates.
5. **Open DevTools, select Network, switch Preserve log ON — and leave it open.** The panel is
   open **before** the press, not after it. A Network panel opened after a completed request is
   indistinguishable from a screenshot, and that is the whole reason this ordering is a rule.
6. **Confirm the two counts that make the take legal before you start it**, because neither can
   be fixed afterwards:
   * `POST /v1/demo/gate-run` answers 200 from the warm-up tab;
   * the number of mutating routes this take will press equals the number §6 rule 9 permits —
     **one** on the path where `POST /v1/demo/cr-gate-run` is absent, **two** where it has
     landed. There is no third value.
7. Roll. The Network list is cleared **on camera**, in B1, as the first act of the take.

---

## 2 · THE BUTTONS, AND THE ROUTES THEY MUST NOT CALL

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

> ### ⛔ BOXED WARNING — THE APPROVE CONTROL ON THE CHANGE SCREEN IS DISABLED, WIRED TO NOTHING, AND MUST NOT BE CLICKED.
>
> Measured in the deployed bundle this session (M9): the control is constructed `disabled`
> with `aria-disabled` true and **never becomes enabled**. There is no change-request merge
> call anywhere in the 96,734 bytes. `POST /v1/change-requests/{cr_id}/merge` answers **404**
> and is not in the deployment's own declared route table (M10).
>
> **Three things follow and none of them is optional.**
>
> 1. **Do not click it.** A disabled control clicked on camera reads as a broken demo, and
>    this one is inert by design. Its reason text is the exhibit; the click is not.
> 2. **Do not point the approve control at the permit's merge route to make something happen.**
>    The bundle's own comment is the ruling and it is better than anything this file could
>    write: *"It is not pointed at the permit's merge route: that route drives a different
>    subject, and a button that refused a different record would be a prop."*
> 3. **Do not narrate the disabled control as a refusal.** It is the console declining to
>    offer an action it has no route for. The kernel has not been asked anything. Saying
>    *"refused"* over it would fake a refusal, which is the one act this whole wave exists to
>    prevent. **B10 as scored requires an actual attempt against an actual endpoint**; where
>    that endpoint does not exist, §7.2 and plan §6 apply and B10 does not shoot.
>
> **On camera this means:** the number of mutating requests in the film is **exactly** the
> number of mutating routes it presses — one today, two if `POST /v1/demo/cr-gate-run` lands.
> §6 rule 9 is the binding form. A `POST` row in the Network panel that nobody narrated, or
> one row more than the path allows, kills the take.

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
>
> **The same rule now binds the change screen.** Its `counters.open_blocking` reads **1** and
> stays 1 for B9 and B10, whatever the attempt returns, for exactly the same reason: the
> attempt is rolled back and the screen holds no re-read.

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

> ### ⛔ DO NOT SELECT A DEFEATER RADIO ON CAMERA — ON EITHER SCREEN — AND DO NOT TYPE A CITATION.
> Selecting one of the three defeater options would say, in pictures, *"I chose this answer and
> then the permit was admitted."* The disposition in beat 4 was composed inside the endpoint's
> own transaction; the payload does not return which `defeater_code` it used, so no selection on
> screen can be shown to be the one that mattered. The three prompts are **read** on camera, not
> answered. The same rule kills any typed rationale or citation: a typed string that is never
> sent, filmed beside an admission, is a claim about causation that nothing supports.
>
> **This extends to the change screen, where the temptation is worse.** Measured this session
> (M8): when the change request's own prompts render, each one carries a **radio** and a
> **`Citation` text field** placeheld `typed by the engineer — this deployment carries no
> answer`. B10 has a refusal on screen and three answerable-looking questions beside it, and
> filling one in would be staging the very act — quietly disposing of the obligation — that
> the beat says the system will not let you do quietly. **Read them. Do not touch them.**

> ### ⛔ NEVER SWITCH MODULES BEFORE B9, AND NEVER SWITCH BACK.
> The router is hash-based and **tears the screen down on a hash change** (`route.ts`,
> `ScreenMount` teardown). Switching to *Management of change* unmounts the permit screen: the
> transcript, the disclosure line and every revealed beat are gone, and returning re-mounts and
> re-fetches. Getting them back would require a **second** `POST /v1/demo/gate-run` — a second
> `run_id`, a second `generated_at`, and a film whose one-request-per-case claim is false.
> **The single module switch in this film happens at the top of B9 and is never reversed on
> camera.** It moved there from B8b in the re-cut; B8 now ends on the run footer.

---

## 4 · THE CONVENTION A JUDGE CAN CHECK IN TWO SECONDS: TYPED CARRIES NO CHIP

Plan R-H, and the built page already implements it on **both** screens:

* **Every server value carries a provenance chip** — `db:column`, `db:constraint`, `derived`,
  `recomputed` — resolved by JSON pointer from the response's own `provenance[]`. On the
  change screen the same job is done by a distinct code style applied only to returned values.
* **Nothing typed carries one.** The permit screen's three typed controls are visible
  `<input>`/`<textarea>` elements with a caret and a placeholder, each labelled
  `typed on this device · not carried by this deployment` (`permit/typed-fields.ts`,
  `TYPED_HERE`).
* **The change screen carries three typed textareas and each one states its own absence**,
  measured verbatim in the deployed bundle this session:

  | field | label | placeholder | its note |
  |---|---|---|---|
  | `moc-technical-basis` | *Technical basis* | `type the technical basis for the proposed change` | *"Typed here, now. `mainline.change_request` carries no technical-basis column, so nothing was loaded into this box and nothing will be echoed back as data."* |
  | `moc-source-of-change` | *Reference the source of the change* | `type the incident, assurance action or improvement this change arises from` | the IChemE Initiate-step field — and the note ends *"the obligation below was raised by the database's own reverse lookup, not by anything typed in this box."* |
  | `moc-proposed-text` | *Proposed wording* | `type the proposed wording` | *"Typed here, now. This deployment carries no proposed text: `mainline.change_request` has no column for it, so there is nothing to load into this box and nothing was."* |

* **Element 8 (PPE) renders empty and labelled** — *"not carried by this deployment"* — and is
  in frame in B0. Do not scroll past it quickly; an empty field that says why it is empty is a
  fidelity signal, not a gap.
* **Element 11 (extension) is omitted**, with a line saying the deployment has no extension
  mechanism. Elements 12 and 13 render **unsigned**.

**Why this convention is what makes B9 legal (R-2).** `FALLBACKS.md` F-8 forbids *rendering* a
proposed clause string, because the table carries none and a plausible one would have to be
hard-coded. **Typing it satisfies F-8 rather than waiving it.** The box is the console's own
input, its note says in the deployment's own words that nothing was loaded into it, and it
carries no chip — so the wording is visibly a human's proposal and can never be mistaken for a
database claim. It is the same discipline B0's work-description tail already uses.

**What may be typed, and the constraint on it.** W4 owns the literal strings
(`ONSCREEN-TEXT.yaml`); this file owns the rule they must satisfy:

* no invented plant name, asset tag, crew, company or PPE list — a value with no column is
  typed by a human or it is empty, and a plausible-looking invention is the same class of act
  as reshaping a seed to match a constant (r3-operator §5.3);
* nothing that could be mistaken for a column value if screenshotted;
* ≤ 60 characters per field, so no typed line wraps and competes with the evidence lines;
* the on-camera tail in element 5 is **at least three words**, so the human typing rate is
  visible (r5-craft §7 tell 12: an inhuman constant rate reads as fake);
* **and, for `moc-proposed-text` specifically:** it is a **weakening edit of the clause of
  record**, short enough to type inside B9's budget, and it must be recognisably a *removal or
  softening* of the control the clause carries — because that is what makes the refusal
  intelligible. It must not name a person, a site, a date or a standard. It is typed against a
  clause whose returned text begins `SYNTHETIC —`, and the comparison in §5 B9 will show the
  two side by side, so a judge can read the edit rather than be told about it.

---

## 5 · THE TWELVE BEATS

Times are `BEATS.yaml`'s. Each block is: **window/scroll state → cursor path → click or
keystroke → what must render → in frame → do not.**

`B0b` inserted at `0:12` and everything from `B1` shifted by **+8 s**; `B8` cut from 10 s to
6 s, keeping its first half; `B9` and `B10` appended.

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

### B0b · WHY IT MATTERS — `0:12 → 0:20` (8 s) · *no click, no keystroke, no scroll*

**This beat has no picture of its own and that is deliberate.** It was added to `VO-DEMO.md`
on 2026-08-16 for a public-channel audience who is never told *why* a refusal is the point.
`BEATS.yaml` scores it `on_screen: unchanged from b0`, and the operator's whole job here is to
**do nothing visible for eight seconds** while the founder speaks.

**Window/scroll state.** **Identical to B0's out-point and not touched.** The signature block
above, the action bar with `1 obligation outstanding`, `ISSUE ▸` beneath the cursor.

| t | movement |
|---|---|
| `0:12 – 0:20` | **Cursor still, resting on `ISSUE ▸`.** No wheel, no travel, no hover away and back. The caret left blinking in element 5 at `0:08` is the only thing moving in the frame, and it is enough. |

**What must render.** Nothing. No request is made and no element changes.

**In frame.** The four witnesses. This is the longest continuously static frame in the film, so
it is also the beat where a burned-in watermark strap is most obviously readable — if the
strap is being used (§7 D-1), B0b is where a judge reads it.

**Do not.** **Do not fill the silence with movement.** A cursor that wanders during a spoken
justification reads as nervousness on camera and, worse, invites the viewer to look for
something that is not there. Do not pre-hover the module tab. Do not scroll to "show" anything
the words describe — the words describe the world, not the screen. Do not click early: the
whole point of B0b is that the click lands at `0:20`, and `BEATS.yaml`'s
`first_refusal_at_s: 30` is computed from that.

---

### B1 · THE ATTEMPT — `0:20 → 0:30` (10 s)

**Window/scroll state.** Unchanged: the action bar sits in the lower half of the page area,
the signature block above it.

**Cursor path and the two clicks.**

| t | movement |
|---|---|
| `0:20 – 0:21` | Cursor travels **right, into the DevTools panel**, to the Network toolbar's **Clear** control (⃠). |
| `0:21` | **Click 1 — Clear.** The request list empties on camera. This is the proof that nothing is preloaded, and it is why the panel was opened in pre-flight rather than now. |
| `0:21 – 0:22.5` | Cursor travels **back left**, continuously, to the `ISSUE ▸` button. A cursor that jumps here is a cut (r5-craft §7 tell 6). |
| `0:22.5` | **Click 2 — `ISSUE ▸`.** Single left click. |
| `0:22.5 – 0:30` | Cursor **does not move again** until the response lands. Hands off the wheel. |

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

### B2 · THE REFUSAL — `0:30 → 0:44` (14 s) · *filmed calm*

**Window/scroll state.** The transcript renders **beneath the action bar** and the page does
not scroll itself, so this beat opens with one small wheel movement.

**Cursor path.**

| t | movement |
|---|---|
| `0:30 – 0:31` | Wheel scroll **down**, two notches, until the lock note, the disclosure strip and the beat-2 banner are in frame together. |
| `0:31 – 0:37` | Cursor **parked and still**, off to the right of the banner. The frame does the work. |
| `0:37 – 0:41` | Cursor travels slowly down the banner as a pointer — `SQLSTATE 23514` → `constraint gate_closed_when_issued` → the `CHECK predicate` row → the `message` row. It **points**; it does not click and does not select text. |
| `0:41 – 0:44` | Cursor moves right and rests beside the DevTools row for ~2 s: `gate-run · 200 · <real bytes> · <real time>`. No tab is clicked. |

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
truncate it, do not cover it with an overlay; the `SQLSTATE 23514` strap goes **beside** it.

**And one thing to hold deliberately, because B10 depends on it.** The reason set names the
**clause** and the **precursor event** by id. Those are the two identifiers R-5 requires again
in B10's frame. A judge who is going to match them at `2:16` has to have seen them here first,
so the pointer rests on that line rather than skating past it.

**Do not.** Do not inflate this beat — a `CHECK` refusing is table stakes and B5 needs the
weight. Do not open the Headers or Response tab yet; the row's four columns carry B2's claim,
and the deeper inspection belongs to the naming block.

---

### B3 · WHY — THE MEMORY LOOP — `0:44 → 1:02` (18 s) · *never cut*

**Window/scroll state.** Wheel scroll **up**, four notches, back to §6 *Hazard identification*.
The card fills the page area. This is the film's most important frame and nothing may be
scrolled during it once it is composed.

**Cursor path — pointing only, no clicks.**

| t | movement |
|---|---|
| `0:44 – 0:46` | Scroll up; settle with the card's header — *"Hazard identification · raised by recall, not by a checklist"* — at the top of the page area. |
| `0:46 – 0:50` | Cursor rests on the precursor block: `DEMO-INC-0001 · incident · 14 March 2019 06:20 UTC`, the `SYNTHETIC — Stored energy release during intrusive work` title, `severity gate 4 / actual 4 / potential 4`, `basis human_rated`, the source document and its sha256. |
| `0:50 – 0:54` | Cursor moves to the projection block — *"the severity on this obligation was not chosen by whoever raised it"* — with `on the obligation 4 / blood_major / closure_gen 0` beside `in the blame closure 4 / blood_major / closure_gen 0`, and beneath them the **source citation**: `0, 'routine', 0, -- projected over by fn_check_project (MI25)`, attributed to `demo_permit.sql:318` at the tree the capture names. |
| `0:54 – 0:59` | Cursor travels down the three labelled rows in order: **`RECALLED`** (run id · `started 2 August 2026 03:00 UTC` · `policy demo-recall-1.0` · `index generation g1` · `1 candidates · 1 blocking · 0 silenced · 0 deduped`) → **`SHOWN TO`** (`actor demo.signer` · `issued 2 August 2026 03:05 UTC` · the receipt digest) → **`STATUS`** (`● OPEN — unanswered on this permit`, with the `derived` chip and the sentence that `open` has no column). |
| `0:59 – 1:02` | Cursor rests on the delta at the foot of the card: `recall run started 03:00:00Z` → **`10 s`** → `obligation materialised 03:00:10Z`, with the `10 s` labelled as *subtracted in this browser, not a column and not chipped*. |

**What must render.** Nothing new — every value above arrived in the four GETs at page load,
and the card prints each one's exchange line (`GET … · 200 · 2,408 B on the wire · observed_at
…`) beneath the values it carries. That is what a judge cross-checks.

**In frame.** The `SYNTHETIC —` prefixes stay visible; do not crop them to prettify the frame
(plan R-F). The disclosure strip is **not** in frame here, because it is not sticky (§7 D-2) —
which is exactly why the card's own per-exchange provenance lines must be legible instead.

**Hold `DEMO-INC-0001` legibly.** It is the identifier R-5 asks a judge to recognise again in
B10, and this is the only beat in the film where it is rendered with its title and its date.

**Do not.** Do not say anything present-tense about the retrieval: the recall already ran and
what is on screen is its **record**. No similarity score, no vector visualisation, no
embedding — this world seeds none. No click: a click here selects text and adds nothing.

---

### B4 · THE HUMAN MOVE — `1:02 → 1:12` (10 s)

**Window/scroll state.** Wheel scroll **down**, four notches, back to the transcript, until the
advance control is in the lower third of the page area with the beat-2 banner above it. This
region **is** the gate transcript of plan R-D: it sits **beneath** the supervisor's own form,
inside the supervisor's own page, and it renders the response's own strings — infrastructure
becoming visible under the product, which is the founder's whole frame.

**Cursor path and the click.**

| t | movement |
|---|---|
| `1:02 – 1:04` | Scroll down; cursor travels to the advance control. |
| `1:04` | **Click 3 — the beat-3 reveal.** Required label: `Show what happens if the counter is forced to zero ▸` (§3, third box). |
| `1:04 – 1:05` | The beat-3 panel paints in ~30 ms — measured, not scheduled. **No request is made**, and the Network panel proves it: the list still holds exactly one row. |
| `1:05 – 1:12` | Cursor travels to the panel's **`statement`** row and rests there: `UPDATE mainline.permit SET open_blocking = 0 WHERE permit_id = %s; CALL mainline.merge_permit(…)`, beside the payload's own label for the beat — *"THE ATTACK: force the projected counter to zero out of band, then merge again"* — and the observed line *"mainline.permit.open_blocking set out of band — what a disarmed projector or a careless UPDATE leaves behind."* |

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

### B5 · REFUSED ANYWAY — `1:12 → 1:28` (16 s) · *the peak · never cut*

**Window/scroll state.** Unchanged from B4 — **no scroll during this beat if the panel fits.**
If the refusal rows sit below the fold, make the one wheel notch at `1:12`, before the line,
never during it.

**Cursor path — no clicks.**

| t | movement |
|---|---|
| `1:12 – 1:16` | Cursor moves up the panel to **`SQLSTATE P0001`** and `constraint mainline.fn_permit_merge_gate`, and rests. |
| `1:16 – 1:20` | Cursor moves to the `message` row and holds on the verbatim string: *"MAINLINE: merge refused by mainline.fn_permit_merge_gate — re-derived open obligation count is 1 while the projected counter reads zero."* |
| `1:20 – 1:23` | Cursor moves to the weakening rows and holds: the `parsed` chip with its note — *"Recovered from the message text rather than reported by the driver — a weakened diagnosis, and it is labelled as one"* — then `diagnosis none · 0 probe calls`, the reason set `capability gap · mainline.fn_permit_merge_gate · …`, and `nearest admissible alternative: NOT COMPUTABLE for this refusal · not_computable`. |
| `1:23 – 1:28` | **Cursor stops. Silence.** Hold the frame with `P0001` and the message both legible. |

**What must render.** Nothing new — the panel is already whole. What matters is that the
**weaker** diagnosis is on screen at the film's loudest moment: `constraint_source: parsed`,
`naa: null`, `naa_reason: not_computable`, MUS `kind: capability_gap`. Leave it there. A demo
that grades its own exhibit down is not one anybody believes is faked.

**In frame.** The single Network row, still one, is the quiet corroboration that this beat
made no request.

**Do not.** Do not add a second overlay here. Do not cut to DevTools mid-line. Do not let the
narration run past the hold — the silence after the sentence is the beat.

---

### B6 · THE ANSWER IS A QUESTION — `1:28 → 1:46` (18 s)

**Dependency, stated first because it changes the clicks.** The three defeater prompts are a
real, declared read — `GET /v1/checks/{check_id}/disposition` → `200`, 3,805 B, carrying
`defeater_options[3]` with their prompts verbatim and `lattice[5]` — but **today they are
rendered only on the change screen**, and the permit screen makes no such read. §7 D-5 names
the owner and the change. Two paths, and the film takes whichever is true on the day.

> **AND ONE THING THAT IS NOW MEASURED AND WAS NOT BEFORE (M11).** The prompts B6 films belong
> to check `dec0de00-0007-…`, the **permit's** obligation. The change request's obligation
> `dec0de00-000d-…` carries a **different vocabulary under a different digest**. B6 and B10
> must never show the same three questions, and neither beat's questions may be spoken over
> the other's screen. If they ever look identical in a take, something is reading the wrong
> check id — stop and start again.

#### Path A — the disposition panel has landed on the permit screen (preferred)

**Window/scroll state.** The panel sits beneath the beat-3 banner, inside the transcript
region, so B6 is a short local scroll and no module switch (§3, fifth box).

| t | movement |
|---|---|
| `1:28 – 1:30` | Wheel scroll **up**, two notches, to the §9–13 signature block. Cursor rests on **row 10 · Acceptance**: `Acceptor` · **`demo.signer`** `[db:column]` · `02 Aug 2026, 03:05Z` · the receipt digest · `Obligations shown 1` · `Tokens 200`. Then one deliberate move up to **row 9 · Issue**, which reads `unsigned — signatory` / `unsigned — date and time`. |
| `1:30 – 1:38` | Wheel scroll **down** to the disposition panel. Cursor travels down the three prompt cards, resting ~2.5 s on each: `MECHANISM_PRESENT_AND_VERIFIED` — *"Which isolation point was locked, and who verified it at zero?"*; `WORK_NOT_INTRUSIVE` — *"Which task in this permit's scope was assessed as non-intrusive, and against which method statement?"*; `ENERGY_SOURCE_ABSENT` — *"Which stored-energy source was surveyed and found absent within this permit's boundary, and by whom?"* |
| `1:38 – 1:46` | Cursor moves to the lattice and rests on two rows: **`mechanism_absent`** (`min rank 4` · second signer ✓ · foreign org ✓ · predicate ✓ · re-assert ✓) and **`emergency_override`** (`min rank 5` · second signer ✓ · foreign org ✓ · `max_ttl_hours 12`). |

**No click and no keystroke occurs in B6** (§3, fourth box).

#### Path B — the panel has not landed

**Window/scroll state.** Identical opening; the second half changes.

| t | movement |
|---|---|
| `1:28 – 1:34` | As Path A: signature block, row 10 Acceptance, then row 9 Issue reading unsigned. |
| `1:34 – 1:46` | Wheel scroll **up** to the hazard card's `STATUS` row — `● OPEN — unanswered on this permit — no disposition of it is live` — with the sentence that `open` has no column and is derived from the absence of a live `mainline.disposition` row. Cursor rests there. |

Under Path B the three questions are **not** filmed and the VO must not describe them; the
cut ladder's B6 trim (18 s → 14 s) applies and the recovered seconds go nowhere else.

**In frame, both paths.** `demo.signer` is on the **acceptance** row and nowhere else. He is
the person the obligation was shown to — `exposure_receipt.actor_sub` — not the issuing
authority (plan R-G). The Issue row stays visibly unsigned.

**Do not.** Do not select a radio. Do not type a rationale. Do not call the three options a
checklist and do not say any of them is inapplicable — there is no global "N/A" in this
vocabulary, and inventing one would destroy the point.

---

### B7 · AND THEN IT ADMITS — `1:46 → 1:58` (12 s)

**Window/scroll state.** Wheel scroll **down** to the foot of the transcript, until the second
advance control is in the middle of the page area.

**Cursor path and the click.**

| t | movement |
|---|---|
| `1:46 – 1:48` | Cursor travels to the advance control. |
| `1:48` | **Click 4 — the beat-4 reveal.** Required label: `Show the beat where one signed disposition is admitted ▸` (§3, third box). |
| `1:48 – 1:49` | The admission panel and the run footer paint together in ~33 ms. **No request is made** — the Network list still holds one row. |
| `1:49 – 1:58` | Cursor travels down the admission rows and rests: **`ISSUE ADMITTED`** · the beat's label *"Sign one disposition against the obligation, then merge again."* · `SQLSTATE 00000` · `disposition <uuid4>` · `disposition kind applied` · `open_blocking after the signature 0` · `clearance digest (server-computed)` · `merged_at` · `permit state merged` · the server-measured elapsed · the `INSERT INTO mainline.disposition (…); CALL mainline.merge_permit(…)` statement. |

**What must render.** The admission panel **plus** the run footer, because the footer paints as
soon as the last beat is revealed. That is why B8 needs no click at all.

**In frame.** The ISSUE button, still disabled, with its lock note — and the header, if the
scroll allows, still reading `dispositioned`. Both are true and both are B8's setup.

**Do not.** Do not say the permit is issued (§3, second box). Do not caption
`clearance_digest` as a constant — four runs on 2026-08-15 produced four different digests, and
if it were ever stable the rollback proof would be broken (plan R-K). `merged_commit` **is**
stable and may be quoted.

---

### B8 · NONE OF IT PERSISTED — `1:58 → 2:04` (6 s) · *one pointer move, no click*

**Cut from 10 s to 6 s in the re-cut. What went is the second half** — the read-only module
switch to the change request, shown rather than driven, which was **rank 1 on the film's own
previous cut ladder** for being *"the weakest-supported second on camera."* B9 and B10 are
precisely the removal of "told rather than driven", so the module switch has not been deleted;
it has **moved into B9**, where it is followed by an attempt instead of a shrug. The rollback
proof is entirely in this half and survives intact.

**Window/scroll state.** Unchanged from B7; the footer is directly beneath the admission panel.

| t | movement |
|---|---|
| `1:58 – 2:04` | Cursor travels down the footer rows: **`VERDICT PROVEN`** · `isolation SERIALIZABLE` · `transaction rolled_back` · `one transaction (equal cluster logical timestamps) · true · <ts> → <ts>` · `savepoints gate_run_beat_2, gate_run_beat_3, gate_run_beat_4` · **`this run persisted anything · false`** · **`minted disposition after rollback · <uuid4> · 0 rows`** · `permit row unchanged · true` · `whole database unchanged · true`. |

**There is no click in B8.** The footer painted with the admission panel at `1:48`.

Say `persisted false`, never *"nothing was written"*. Something **was** written, and unwound
inside one `SERIALIZABLE` transaction, and the proof is a uuid4 only this run held.

**Six seconds is ten rows, so the pointer must not linger.** The two rows that carry the beat
are **`this run persisted anything · false`** and **`minted disposition after rollback · … ·
0 rows`**; the rest are travelled past, legibly, not dwelt on. If the founder's line runs long,
the pointer finishes its travel in silence rather than the beat over-running into B9's module
switch — B9's read chain needs every one of its own 12 seconds (M14).

**Do not.** Do not switch modules inside B8 to "get a head start" on B9. The switch is B9's
first act, on camera, with the URL bar in frame, and moving it earlier steals the shot that
proves the host never changed.

---

### B9 · THE OTHER WAY IN — `2:04 → 2:16` (12 s)

> **THIS BEAT AND B10 ARE ATOMIC (R-10). `b9` MAY NEVER BE SHOT WITHOUT `b10`.** A setup with
> no answer is worse than neither: it spends 12 s raising the judge's question — *"fine, so
> couldn't somebody just rewrite the rule?"* — and never answers it. If B10 cannot shoot for
> any reason in §7.2, **B9 does not shoot either**, and the film reverts to plan §6 with `b8`
> restored to 10 s.

**Window/scroll state at the in-point.** The permit screen's run footer, exactly where B8 left
it. The cursor is at the foot of the footer rows.

**Cursor path, the click, and the keystrokes.**

| t | movement |
|---|---|
| `2:04 – 2:05.5` | Cursor travels **up to the app bar**, continuously, to the tab **`Management of change`**. This is a long travel across the page and it must not jump — the URL bar is in frame the whole way and the travel is what proves no cut. |
| `2:05.5` | **Click 5 — the module switch.** The hash becomes `#/change` **in the URL bar, on the same origin**; the host in frame does not change. |
| `2:05.5 – 2:09` | **The screen paints in four visible stages as its four reads land, and the operator does not touch anything while it does.** Measured warm at ≈ 3.5 s total (M14): the header, the IChemE ribbon and §2's counter and CHECK-constraint table fill together from the change-request read; then the approval bar and its route table, from the blocking-checks probe; then §3's clause of record; then §5's lattice. **The stages do not fill top to bottom** — the approval bar is below §5 and paints second — so let the page settle rather than chasing each one with the cursor. **Four new rows appear in the Network panel** — `change-requests/…` `200`, `…/blocking-checks` **`404`**, the clause version `200`, the disposition `200`. A live client, proven again, for free. **`GET /v1/demo/subjects` is not re-read** — it is memoised at module scope — so there are four rows, not five. |
| `2:09 – 2:10.5` | Wheel scroll **down** to **§3 · Modifications to operating procedures**, until the *Clause of record — current text, as returned* block and the **Proposed wording** box are in frame together. Cursor rests one beat on the clause quote so its returned text and its `SYNTHETIC —` prefix are readable. |
| `2:10.5 – 2:11` | Cursor travels to the **Proposed wording** textarea and single-left-clicks into it. Caret appears in an empty box. |
| `2:11 – 2:16` | **Keystrokes: the proposed wording, typed at a human rate, on camera.** No `Enter`, no `Tab`. The caret is left blinking in the field. |

**What must render.**

* the header: **`DEMO-MOC-0001`** · `refs/changes/demo-0001  →  refs/heads/main` · `opened_at`
  · `gate_epoch 1` · `head_seq 1` · **`merged_commit null — never merged`** ·
  `counters.open_blocking 1` · `open_conflicts 0` · `open_residue 0`;
* the **IChemE Safety Centre Management of Change** ribbon, five steps, with **no step marked
  current** and the ribbon's own sentence saying why — *no column in this deployment maps a
  change request onto an IChemE step* — beside the `checks_materialised` chip printed from
  `mainline.change_request.state`;
* **§3's clause of record**: the returned `canon_text` in a quote block, then `Printed label`
  **`7.3.2(b)`** at its commit id, `· anchors LOTO, ZERO_ENERGY`;
* **the relation note directly beneath it, and it is not optional** — the deployment's own
  words: *"This is the clause version addressed by `GET /v1/demo/subjects`, and the one the
  live permit's open obligation is anchored to. It is **NOT** a link this change request
  carries: `mainline.change_request` has no target-clause column, so no edge from this record
  to this clause is asserted here."* **The founder must not say the change request targets the
  clause.** The screen refuses that claim in writing while he is looking at it, and a narration
  that contradicts an on-screen caveat is the worst failure available in this film;
* the **Proposed wording** box filling with typed characters, carrying **no provenance chip**,
  under its own note that the deployment carries no proposed text and nothing was loaded into
  it (R-2, §4).

**In frame.** URL bar reading `#/change` on the unchanged host · taskbar clock · DevTools with
the four new rows and the `404` among them, unhidden · `7.3.2(b)` and the typed box in the same
frame at the out-point.

**Do not.**

* **Do not click `Compare with clause of record`, and this is a recorded trade rather than a
  flat prohibition.** It is a real, shipped control; it makes **no request**; it paints a
  word-level diff between the returned clause text and the typed box; and it carries its own
  caveat — *"Computed in this browser, just now … It is not a stored diff, it is not a kernel
  claim, and no part of the right-hand side came from the database."* **It is the single best
  show-don't-tell asset on that screen and the film has no room for it:** B9's last five
  seconds are the typing, and the diff renders in §3 while B10's frame is §2. If `b9` is ever
  given more time, this control is the first thing to spend it on — not a fourth read and not
  a second scroll.
* **Do not touch `moc-technical-basis` or `moc-source-of-change`.** They are empty on purpose
  and their notes are part of the exhibit. Typing into the source-of-change box in particular
  would suggest the obligation came from what was typed there, when the screen's own note says
  it came from *the database's own reverse lookup*.
* Do not scroll past the relation note to reach the box faster.
* Do not narrate the ribbon as a workflow position — no step is current, and the ribbon says so.
* Do not say a year, a site, a job title or an injury. The seeded precursor describes nobody.

---

### B10 · REFUSED AGAIN — `2:16 → 2:28` (12 s) · *the mirror*

> ### ⛔ **THIS BEAT DOES NOT SHOOT TODAY, AND §7.2 IS WHY.** It is scored in full because its
> two route dependencies are **already built in the tree and merely undeployed** (M15) — the
> gate is a deploy away rather than a wave away, and the frame it needs should be on record
> before that deploy, not after it. **Measured against the origin 2026-08-16:
> `POST /v1/demo/cr-gate-run` → 404, `GET /v1/change-requests/{cr_id}/blocking-checks` → 404,
> the approve control hard-disabled.** Plan §6's decision gate fails on all three legs **on the
> origin, which is the only surface this film is shot against.** **Do not substitute the disabled approve
> control's reason text for a refusal** (§2, second box) — the kernel has not been asked
> anything, and narrating an absence of a route as a refusal fakes a refusal.

**Precondition, checked in pre-flight and not on the day of the shoot.** All three must hold,
each measured, none assumed:

1. `POST /v1/demo/cr-gate-run` answers `200` with `persisted` false **measured by the endpoint
   from its own two fingerprints**, three beats named `read` / `merge` /
   `projection_drift_attack`, `admission_beat` null and `admission_absent_reason` populated in
   words — the contract `scripts/proof/cr_gate_refusal.py` asserts;
2. `GET /v1/change-requests/{cr_id}/blocking-checks` answers `200` and returns the change
   request's own `check_id`, so that the screen reads **`dec0de00-000d-…`** and renders **its**
   vocabulary rather than the permit's (M12);
3. the approve control is enabled and calls the endpoint in (1) — and **the refusal renders in
   the same section as the three prompts**, which is the R-5 frame requirement in §7.2.

**Window/scroll state at the in-point.** §2 · *Impact of change on safety and health* composed
in the page area, with the counter line, the CHECK-constraint table and the three prompt cards
in frame. The cursor is coming down from B9's typed box.

**Cursor path and the click.**

| t | movement |
|---|---|
| `2:16 – 2:17` | Cursor travels to the **`Approve change`** control, now enabled. |
| `2:17` | **Click 6 — the attempt.** Single left click. **This is the film's second and last mutating request** and it is narrated while it is in flight (§6 rule 9). |
| `2:17 – 2:18.5` | The control shows its own real pending state; **one row appears** in the Network panel, `cr-gate-run`, method `POST`, its `Status`, `Size` and `Time` columns filling as the response lands. Cursor does not move. |
| `2:18.5 – 2:22` | The refusal paints. Cursor travels down it as a pointer: **`SQLSTATE 23514`** → `constraint cr_gate_closed_when_merged` chipped **`reported`** → the predicate `((state != 'merged':::mainline.subject_state) OR (open_blocking = 0))` → `counters.open_blocking 1`. It **points**; it does not click and does not select text. |
| `2:22 – 2:26` | Cursor moves **left and up, without leaving the frame**, to the three prompt cards and rests across them: `CONTROL_PRESERVED_BY_EDIT`, `EDIT_OUTSIDE_BLAMED_ANCHOR`, `PRECURSOR_ANSWERED_ELSEWHERE`. |
| `2:26 – 2:28` | **Cursor stops. Hold.** The refusal and the three questions both legible, with the mirror line spoken over the still frame. |

**What must render, and the frame that R-5 requires.**

* the refusal itself, from the payload: `23514`, **`cr_gate_closed_when_merged`**, its own
  predicate, `constraint_source reported`, `outcome refused`, the beat's server-measured
  elapsed, and the run's `persisted false` taken from the endpoint's own before-and-after
  fingerprints — **never from a claim** (plan §4.4);
* **the reason set naming the shared clause and the shared precursor.** On the permit side the
  merge beat's refusal carries a minimal-unsatisfiable-set entry with the obligation id, the
  **clause id `dec0de00-0004-…`**, the **precursor event id `dec0de00-0005-…`**, `origin
  blame_ancestry`, `severity 4`, `virulence blood_major`. **The change-request endpoint must
  carry the same shape** — that is the single cleanest way R-5 is satisfied, because it puts
  both identifiers **inside the refusal band itself**, in one frame, as kernel strings, needing
  no scroll and no composite. §7.2 states this as a requirement on whoever builds the endpoint;
* **the three prompts, verbatim, under one `vocab_sha256`** — and note that the third one,
  `PRECURSOR_ANSWERED_ELSEWHERE`, contains **`DEMO-INC-0001` in its own prompt text**: *"Which
  other clause version already carries the control DEMO-INC-0001 called for, and at which
  commit?"* That is the precursor arriving in the frame as a kernel string rather than a
  caption, and it is the reason condition (2) above is load-bearing rather than cosmetic;
* the lattice, keyed by `blood_major`, with `emergency_override` at `min_signer_rank 5`, second
  signer ✓, foreign org ✓, `max_ttl_hours 12` — in frame if the composition allows, but it is
  the prompts that are mandatory (R-4), not the lattice.

**In frame, and this list is R-5 and is not negotiable.** The refusal · **clause `7.3.2(b)` /
`dec0de00-0004-…`** · **precursor `DEMO-INC-0001` / `dec0de00-0005-…`** · the three prompts ·
the URL bar · the clock · the Network panel showing **exactly two `POST` rows for the whole
film**. **If they will not compose in one frame, B10 does not shoot** — do not solve it by
zooming out below §1.2's floor, by narrowing the dock past §1.3's 760 CSS px, or by cutting
between two frames and calling it one.

**Do not.**

* **Do not select a defeater radio and do not type a citation** (§3, fourth box). The
  temptation is at its worst here: a refusal on screen, three answerable questions beside it,
  and a text field under each one. Filling one in would stage the exact act — quietly disposing
  of the obligation — that this beat says the system will not let anyone do quietly.
* **Do not say the clause cannot be changed.** It can, by disposing of the obligation first,
  which is what the three prompts are for. The scope word carries the sentence: *you cannot
  **quietly** edit it away.* W6 files a REFUSE against every variant that drops it (plan R-7).
* **Do not speak `blood_major`.** It is a column value and it goes on screen only; saying it
  aloud edges toward inventing an injury.
* **Do not say the permit's SQLSTATE and the change request's are "the same refusal".** They
  are the same SQLSTATE and a **different constraint on a different table**, which is the whole
  point, and flattening it throws away the mirror.
* **Do not claim an admission.** There is no fourth beat here and there is not going to be one:
  the endpoint's contract requires `admission_beat` null and requires the payload to say in
  words why. Use case two ends on the question, and that is honest.
* **Do not switch back to the permit module** (§3, fifth box) — the take ends on this screen.

---

## 6 · THE ANTI-FAKE CRAFT RULES THAT BIND EVERY BEAT ABOVE

Rules 1–8 are unchanged from the story-and-script wave and are not weakened here. Rule 9 is
added by plan R-9 as a **tightening**.

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
9. **EXACTLY TWO MUTATING REQUESTS, EACH NARRATED WHILE IT IS IN FLIGHT, EACH VISIBLE IN THE
   PANEL. Any third row, or either row appearing without its narration, stops the take.**
   This replaces `FALLBACKS.md` F-11's one-request rule and it is **strictly stronger at two
   requests than F-11 was at one**, because it adds a narration condition F-11 never carried:
   a `POST` that lands while the founder is talking about something else is now a dead take
   even though the count is legal. The two are `POST /v1/demo/gate-run` at `0:22.5` and
   `POST /v1/demo/cr-gate-run` at `2:17`, and there is no third mutating route in this film.

   > **On the path where use case two does not shoot, the count reverts to exactly one** and
   > F-11's original form applies unchanged — a second `POST` row kills the take. **The count
   > is never a range and is never decided during the take.** It is fixed at pre-roll step 6,
   > against a measurement, and written on the shot list before the red light.

---

## 7 · DEPENDENCIES AND ESCALATIONS — what this score assumes, and who owns it

Each is a real gap measured this session or the last, not a preference. None is mine to fix:
this file owns no source.

| # | gap | measured where | what the film needs | owner |
|---|---|---|---|---|
| **D-1** | The watermark strip is a normal flow element (`.cw-watermark`, no `position: sticky`) and **scrolls out of frame** for every beat after B0. Plan R-L requires it on frame for the whole film. | `operator/chrome/chrome.css` | Preferred: make the watermark strip sticky. Fallback: a burned-in strap carrying the identical sentence. | operator wave (chrome) |
| **D-2** | The disclosure strip is likewise not sticky, so it leaves frame at B3 and B6. Plan R-C requires it in frame from B2 onward. | `operator/issue/disclosure.ts`, `issue.css` | Preferred: sticky strip. Fallback: a burned strap carrying **no run-varying value** — a generic sentence cannot be wrong about a run, whereas a burned `run_id` typed by hand can be. | operator wave (issue) |
| **D-3** | `raw-payload-drawer-is-byte-identical` **did not hold**: `renderRawPayload()` / `renderRequestLog()` exist and are called by nobody on the permit screen, so the gate-run body has no in-page drawer. | `evidence/demo/operator-capture.json` → `assertions` | Either the drawer lands, or DevTools' Response tab carries the raw payload in the naming block. The film as scored above does **not** depend on it. **Note the asymmetry now visible: the change screen ships four working raw-payload drawers.** | operator wave |
| **D-4** | The two advance controls are labelled as actions, not reveals. | `operator/issue/disclosure.ts` `advanceLabel()` | The two strings in §3, third box. | operator wave (issue) |
| **D-5** | The three permit defeater prompts and the lattice are rendered on the **change** screen only; the permit screen makes no `GET /v1/checks/{check_id}/disposition`. B6 as written in the beat sheet has no pixels on the permit side. | `operator/change/ChangeScreen.ts`, `change/absence.ts`; capture network list | Path A in §5 B6 — a read-only disposition panel on the permit screen, from that one declared GET, with **no submit control**. Otherwise Path B, and B6 trims. | operator wave (permit/issue) |
| **D-6** | ~~`/operator.html` is not on the deployed origin.~~ **CLOSED 2026-08-16 (M7).** It serves 200 at 5,097 bytes with its own title and its own entry bundle. | this session, against the live origin | Nothing. The URL in §1 is confirmed. | — |
| **D-7** | `POST /v1/demo/cr-gate-run` → **404 on the origin**. **But it exists in the tree**: `app.ROUTES` declares it and `cr_gate_run.py` implements it. It is **built and undeployed**, not unbuilt. | this session (M13, M15) | A deploy, then a re-measurement. The contract is already asserted by `scripts/proof/cr_gate_refusal.py`. See §7.2 for the one thing the film needs from its payload that no test asserts. | orchestrator (deploy) |
| **D-8** | `GET /v1/change-requests/{cr_id}/blocking-checks` → **404 on the origin**, so the change screen reads the **permit's** disposition and renders no defeater prompts for the change request. **Also already in the tree**, as `cr_blocking_checks`. | this session (M10, M12, M15) | A deploy. **The console needs no edit** — its reader already parses the exact envelope the tree's implementation returns (§7.2 c). | orchestrator (deploy) |
| **D-9** | The approve control is hard-disabled and wired to nothing; there is no change-request merge call in the bundle. | this session (M9) | An enabled control that calls D-7's endpoint — **and renders its refusal beside the prompts**, §7.2. Subject to the console's 1,325-byte headroom, which is not this file's to spend. | operator wave (change) |

### 7.1 · ESCALATION, UPDATED — the sentence in three files, and the clearance condition that has since closed

**First, the correction this wave owes `CLAIMS-CLEARANCE.md`.** Its condition 1 read *"the film
scored in `CLICKS.md` has no pixels on this origin today."* **That is no longer true and has not
been true for some time.** Measured this session (M7, M8): `GET /operator.html` answers 200 with
its own title and its own 96,734-byte entry bundle, and that bundle contains a complete,
shipped Management-of-Change surface — five OSHA sections, the IChemE ribbon, the clause of
record, an in-browser comparison, a lattice and an approval bar with its own reasoned refusal to
act. `docs/demo/research/r6-honesty.md` §A13.5's *"no console surface"* was correct on the day it
was measured and is now out of date. **Per plan R-8, nobody edits the research record** — a
dated measurement is not rewritten because the world moved. W6 files a **superseding clearance
row** in `CLAIMS-CLEARANCE.md` citing M7 and M8, and condition 1 is recorded **CLOSED**.

**Second, the claim that is still open.** *"The permit screen turns from blocked to issued."* It
appears in `BEATS.yaml` `b7.on_screen`, and — the part that matters, because it is **spoken** —
in `VO-DEMO.md`. The neighbouring version, *"the counter on the permit header ticks 1 → 0"*,
comes from r4-story §5 B4.

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

**Requested resolution.** Story lead rules; W2 edits `VO-DEMO.md`; W1 edits `b7.on_screen`; W6
records the outcome in `CLAIMS-CLEARANCE.md`. This file is scored against the measured render
either way (§3, first and second boxes) — if the sentence survives unchanged, the founder still
must not point at the screen while saying it, because the screen will be saying otherwise.

### 7.2 · ESCALATION — R-4 AND R-5 CANNOT BE SATISFIED ON THE SHIPPED CONSOLE, AND THE REASON IS NOT ZOOM

My brief told me to escalate rather than drop either identifier if the geometry would not hold
them. **The geometry is the second problem, not the first.** Measured this session:

**(a) `DEMO-INC-0001` has no pixels on the change screen at all.** It is not in the
change-request payload, not in the clause-version payload, and not in the disposition payload
the screen currently reads. It appears in exactly **one** place reachable from that screen:
inside the prompt text of `PRECURSOR_ANSWERED_ELSEWHERE`, which belongs to the change request's
**own** obligation `dec0de00-000d-…`. The screen does not read that obligation — it reads the
permit's check `dec0de00-0007-…` instead, and **says so in its own words** (M12). So the
precursor identifier R-5 requires is not merely off-frame; it is not rendered.

**(b) The same absence takes R-4 with it.** The bundle contains a complete prompt renderer —
radios, verbatim prompt text, a citation field each, and the sentence *"There is no 'not
applicable' option because the vocabulary does not contain one"* — but it is called **only**
when the change request's own checks were reached through a declared route. Today it is not
called, and the screen renders instead: *"The ways this obligation could be answered are not
shown, because this deployment declares no route that returns them for a change request. They
are not omitted for space and they are not paraphrased from a document — they are unreachable,
and the route table beside the approve control is the proof."*

**That paragraph is the console being scrupulously honest, and it is why the panel is not
"broken".** The 404 body enumerates all 17 declared routes and the screen renders the route
table from it. Anyone who opens that screen today films an **honest absence**, not a defect.
But an honest absence is not R-4 and it is not R-5, and R-5 says in terms that if those two
identifiers are not in the refusal's frame, the wave should be abandoned in favour of plan §6.

**(c) The one measurement that changes all of it, it costs the console nothing, and it is
already written.** `GET /v1/change-requests/{cr_id}/blocking-checks` must answer `200` —
declared in the route table under that exact template, returning a `checks` array whose entries
carry `check_id`. **The tree's `cr_blocking_checks` returns exactly that envelope and the
bundle's reader parses exactly that field** (M15), so the two halves already fit and neither
was written for the other. When the origin serves it, then with **no edit to the shipped
bundle** the discovery walk finds the route in the declared list, substitutes the `cr_id`,
resolves `dec0de00-000d-…`, reads that obligation's disposition, renders **its** three prompts
with `DEMO-INC-0001` verbatim in the third, and re-labels its raw drawer from *"the addressable
check (NOT this change request's)"* to *"this change request's own check"*. **One route closes
R-4, closes half of R-5, and removes the only paragraph on the screen that reads as an
apology.** It is the highest-value item in this whole dependency table and it is not the
approve button.

**(d) The geometry problem, which survives (c) and is the reason B10 may still not shoot.**
Even with the prompts rendered, the screen's DOM order (§1.3) puts them in §2, the clause of
record in §3, and the approval bar after §5 — **three sections apart.** At 250 % zoom on a
≥ 760 CSS px page they cannot share a frame, and lowering the zoom is forbidden by §1.2.
**Two ways out, and only one of them is available to a film:**

* **Preferred, and it is a requirement on D-7, not on the console:** the endpoint's `merge`
  beat carries a reason set of the same shape the permit's already does — obligation id,
  **clause id**, **precursor event id**, `origin blame_ancestry`, `severity 4`, `virulence
  blood_major`. Then **both identifiers are inside the refusal band itself**, one frame, no
  scroll, as kernel strings. This is exactly how B2 already satisfies the same requirement on
  the permit side, so it is a precedent rather than a request.
* **Otherwise, a requirement on D-9:** the refusal must render **inside §2, beneath the three
  prompts**, so that the prompts and the refusal share a section.

**If neither is done, B10 does not shoot, B9 does not shoot with it (R-10), and the film goes
to plan §6** — which is a legitimate outcome that costs the film nothing: `b8` returns to 10 s
with its read-only change-request cut, the film runs 2:32, and every service and feature is
still named. **What must not happen is B10 being shot against the disabled control** (§2,
second box).

### 7.3 · TWO SMALLER ESCALATIONS TO W1, BOTH ARITHMETIC

* **The cut ladder's rank 1 is not executable as written.** It takes `b9` from 12 s to 8 s by
  removing *"the typing of the proposed wording; arrive on it composed."* **The proposed wording
  cannot be pre-typed** — reaching the box requires a hash change, and a hash change tears the
  screen down and re-creates the textarea empty (§1.5 step 3). At 8 s the choice is a shorter
  string typed faster, not a pre-composed one, and B9's 12 s already contains ≈ 3.5 s of
  read chain it cannot compress (M14). **`b9` at 8 s is tight and should be re-checked against
  a rehearsal, not against arithmetic.**
* **B9's read chain is a measured cost and should be visible in the spine.** Four sequential
  awaited GETs, ≈ 3.5 s warm and ≈ 6 s cold. Pre-roll step 4 exists to keep it warm; if the
  take slips past the warm window, B9 over-runs and there is nowhere for it to go, because B10
  follows immediately and the close is already compressed to the second.

---

## 8 · THE CLICK LEDGER — the whole take

**Six clicks and two text entries** on the path where use case two shoots. Five clicks and one
text entry where it does not (see the tail rows).

| # | t | act | request it makes |
|---|---|---|---|
| — | pre-roll | navigate; pre-type permit elements 1 and 3 and the head of element 5; warm the change screen's reads from a second tab and close it; open DevTools → Network → Preserve log | GETs at page load; the warm-up tab's own reads, which are **not** in the filmed panel because it is closed before the take |
| 1 | `0:05.5` | click into the *Work and its limitations* textarea; **type the tail** | none |
| 2 | `0:21` | click **Clear** in the Network panel | none |
| 3 | `0:22.5` | click **`ISSUE ▸`** | **1 × `POST /v1/demo/gate-run`** — mutating request 1 of 2 |
| 4 | `1:04` | click the **beat-3 reveal** | **none** (measured 30 ms to paint) |
| 5 | `1:48` | click the **beat-4 reveal** | **none** (measured 33 ms to paint) |
| 6 | `2:05.5` | click the app-bar tab **Management of change** | **4 × `GET`** — the change request `200`, `…/blocking-checks` **`404`**, the clause version `200`, the disposition `200`. `GET /v1/demo/subjects` is memoised and is **not** re-read |
| 7 | `2:10.5` | click into **Proposed wording**; **type the proposed wording** | none |
| 8 | `2:17` | click **`Approve change`** | **1 × `POST /v1/demo/cr-gate-run`** — mutating request 2 of 2 |

**B0b contains no click, no keystroke and no scroll.** **B2, B3, B5, B6 and B8 contain no click
either.** Everything between the clicks is a wheel scroll and a cursor travel — which is what a
real person does with a form, and is why the take can be unbroken.

**Totals a judge can verify in the Network panel, and the only totals this film claims:**

* **exactly two `POST` rows**, at `0:22.5` and `2:17`, each narrated while in flight (§6 rule 9);
* **the two reveals make none** — the list holds one `POST` across both of them;
* **the module switch makes four `GET`s and no `POST`**, one of which is a `404` that stays on
  screen unhidden.

**On the path where use case two does not shoot** (§7.2, plan §6): rows 7 and 8 do not happen,
row 6 moves back into `b8`'s second half with `b8` restored to 10 s, the ledger is **five clicks
and one text entry**, and §6 rule 9 reverts to **exactly one** mutating request. The count is
fixed at pre-roll step 6 and never decided inside the take.
