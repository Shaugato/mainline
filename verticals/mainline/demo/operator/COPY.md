<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# COPY.md — every string on the two operator screens, and where it comes from

**Worker:** W8 · **Date:** 2026-08-15 · **Status:** the deck. A string not in this file has
not been cleared to appear on screen or to be spoken over it.

Read against the built screens, not against the plan: the strings below were taken out of
`verticals/mainline/apps/console/src/operator/**` and the values beside them out of live
responses from `scripts/deploy/local_furl.py` over the local CockroachDB node on 2026-08-15.

---

## 0 · The source column, defined once

Every row in this deck carries one of six sources. The distinction is the whole point of the
document, so it is stated before anything uses it.

| tag | meaning | how a reader checks it |
|---|---|---|
| **DB** | A column value, rendered as the database returned it. | The envelope's `provenance[]` carries a `db:column` claim at that JSON pointer. |
| **DB-TEXT** | Seeded prose rendered **verbatim**, not paraphrased. | Compare with the row. It still carries its `SYNTHETIC —` prefix. |
| **STD** | A verbatim citation of a published standard (HSE HSG250, OSHA 1910.119, IChemE). | The citation is printed next to it on screen. |
| **ED** | Our editorial sentence. Nobody's data; our words, and our responsibility. | It is in this deck with the reason it is allowed. |
| **CLIENT** | Computed in the browser from values already on screen, and **labelled as such** where it appears. | The screen says where it was computed. |
| **TYPED** | An operator types it on camera. Placeholder only; no provenance chip; never echoed back as server data. | The field is empty until somebody types in it. |

**A seventh category exists and is forbidden: a plausible value with no source.** A job
description, a plant name, a crew list or a PPE list presented as data is the same class of act
as reshaping a seed to match a constant, and this repository has reverted a worker for that.

---

## 1 · THE LANGUAGE RULINGS — non-negotiable, and each one has cost somebody something

### 1.1 Two enum values render verbatim, and are never translated

`dispositioned` (the permit) and `checks_materialised` (the change request) are real values of
`mainline.subject_state`. They appear on screen **exactly as spelled**, in a chip, beside the
other six values the enum declares. A gloss is available on demand; the gloss never replaces
the value.

> Why: a screen that prints "Pending approval" where the database says `dispositioned` has
> invented a state machine. The seven-value alphabet is rendered beside the current value so a
> judge can see the chip is a selection from a real domain rather than a label we chose.
> *(Plan R10; `permit/header.ts` `SUBJECT_STATE_ALPHABET`.)*

### 1.2 The recall is described in the PAST TENSE, because it is a seeded row

`mainline_meas.recall_run` is a row that already existed when the page loaded. The page **read**
it. It did not run a retrieval, and the button press does not run one either.

* **Say:** "the recall run that armed this obligation", "recalled", "started 2 August 2026".
* **Do not say:** anything in the present or future tense that implies retrieval is happening
  while the judge watches.

The **present tense is reserved for one thing only**: the re-derivation that happens on the
button press, which really does execute during the demonstration.

### 1.3 Banned phrases — never spoken, never captioned, never written

These are forbidden on screen, in the voice-over, in the script and in the deck:

* "watch it remember"
* "the agent searched the corpus"
* "this is retrieval-augmented"
* any similarity score, vector visualisation, embedding count or candidate-row animation

> Why: there are no embeddings, no cues and no candidate rows in this world. The mechanism is a
> reverse lookup over a blame ancestry, which is a stronger claim than similarity search
> because it is exact. Dressing it as vector search would trade a true strong claim for a false
> weak one. *(Plan R17; r6-honesty A5/A5.1; r2-memory warning 4.)*

### 1.4 Do not claim that every refusal on screen is the database's

Three refusals are visible in this demonstration and they are **not the same kind of thing**.
Saying so is stronger than hiding it, because a judge who notices the difference unaided will
assume we were hiding all of it.

| what refuses | where it is enforced | what may be said |
|---|---|---|
| beat 2 — `23514`, `gate_closed_when_issued` | A **declarative CHECK constraint**. The database refuses it on its own terms, on every code path, including one that never went through our code. | "the database refused this write" |
| beat 3 — `P0001`, `mainline.fn_permit_merge_gate` | A **procedural guard MAINLINE wrote**, executing server-side inside the database. Not a constraint the database enforces by itself. | "the gate re-derived the count and refused" — do not call it a CHECK constraint |
| change screen — `Approve change` disabled | **The page itself.** No route exists to drive a change-request merge, so the control is disabled by the client and the 404 route table is printed beside it as the evidence. | "this control is disabled by this screen, and here is why" |

**The one line that needs W5's attention.** `issue/RefusalBanner.ts` renders the same lead
sentence — *"The database refused this write. Everything below is what it returned."* — above
both beat 2 and beat 3. For beat 2 it is exactly right. For beat 3 it is defensible (the
refusal did come back from the database server) but it flattens the distinction this ruling
exists to preserve. **Recommended:** vary the lead on the beat whose `constraint_source` is
`parsed` and whose `diagnosis` is `none`, to *"The gate refused this write. Everything below is
what it returned."* W5 owns that file; W8 owns the sentence and records the finding here.

### 1.5 "Wrote nothing" is read off `self_persisted`, never off `identical`

The gate-run payload carries both. They answer different questions and the payload says so in
its own `note`:

* `persistence_check.identical` — a whole-database reading. It can go false because **somebody
  else** wrote during the run.
* `persistence_check.self_persisted` — **this run's** own reading: the disposition beat 4
  minted is a uuid4 no other writer holds, it is gone after the rollback, and this subject's
  row counts and permit row are unchanged.

**The verdict keys on `self_persisted`, and so does every sentence we say.** Measured this
session: `self_persisted = false`, `identical = true`, `transaction.disposition = rolled_back`.

* **Say:** "this run wrote nothing."
* **Do not say:** "the database is unchanged" — that is the weaker reading and it is not the
  one the verdict uses.

### 1.6 The incident is 2019-03-14, and nobody was injured in it

The seeded precursor is `DEMO-INC-0001`, `occurred_at 2019-03-14T06:20:00Z`, titled
`SYNTHETIC — Stored energy release during intrusive work`, severity 4.

* **Say:** "a severity-four stored-energy release during intrusive work."
* **Do not say:** "a worker was hurt", "somebody was injured", or any sentence that puts a
  person in the event. The narrative column never says a person was harmed, and the seed's own
  text describes nobody.
* **A script that says 2024 has said the one sentence this repository forbids.** The date is
  **2019-03-14**. It is seven years before the permit, and that gap is the point of the story.

---

## 2 · CHROME — present on both screens

| # | string | source | note |
|---|---|---|---|
| C1 | `CONTROL OF WORK` | ED | The product name. "Control of work" is the industry's own generic name for the software category, so it imitates nobody. No vendor mark, no logo, no employer name, no form number. *(R13)* |
| C2 | `SYNTHETIC DEMONSTRATION — no real site, no real permit, no real person` | ED | Permanent strip, and it is also in `operator.html` **before any script runs**, so it is true even if the bundle never mounts. |
| C3 | `Permit to work` / `Management of change` | ED | Module names in the bar. |
| C4 | `Modules` | ED | `aria-label` on the module nav. |
| C5 | `Registers` | ED | Left rail heading. |
| C6 | `Permits` / `Isolations` / `Certificates` / `Register` | ED | The four registers a control-of-work rail lists. Only `Permits` is carried. |
| C7 | `not carried by this deployment` | ED | Against the three registers that are not built. An absent capability is **named and never populated**. |
| C8 | `This rail is a list, not a menu. The two modules this deployment carries are switched in the bar above.` | ED | Says plainly that the rail is scenery, so nobody films a click that was never going to work. |
| C9 | `served from` + `<origin>` | CLIENT | `location.origin`, rendered live. No absolute URL is compiled into the bundle. |
| C10 | `X-Mainline-Emulator` + value | DB-ADJACENT | The response header, verbatim. `local_furl` locally; **absent** on the deployed origin. This is the mark that separates a rehearsal from the real run. |
| C11 | `no response observed yet in this page load` | ED | Before the first request settles. |
| C12 | `absent — the last response declared no emulator` | ED | What the **deployed** origin produces. |
| C13 | `Module not in this build` / `This is an absent module, not an empty one.` | ED | An unbuilt screen and an empty screen must never look the same. |

**Boot and `<noscript>` copy** (in `operator.html`, true before any script runs):

* `Control of work — not yet loaded` + the sentence naming `assets/` and `operator.html`. **ED.**
* `JavaScript is required, and here is exactly why` — *"a page that showed you a filled-in
  permit without them would be a picture of a permit rather than a permit."* **ED.** This is
  the thesis of the whole surface and it is worth reading aloud if the script has room.

---

## 3 · SCREEN ONE — PERMIT TO WORK

The subject is addressed from `GET /v1/demo/subjects`. **No UUID is a literal in source.**

### 3.1 Header — HSG250 Figure 1 element 2

| string | source | measured value |
|---|---|---|
| `Permit type` + the eight options | STD (HSG250 Table 2) | **TYPED** selection. No column carries a permit type; "cold work" is an inference from the clause's subject matter, so it is an operator choice on camera, never data. |
| `HSG250 Table 2 · selected on this device` | STD + ED | The disclosure that makes the line above honest. |
| `Permit reference number` / value | DB | `mainline.permit.external_ref` = `DEMO-PTW-0001` |
| branch | DB | `ref_name` = `refs/permits/demo-0001` |
| `Status` + chip | **DB, verbatim** | `state` = **`dispositioned`** — see §1.1 |
| the seven-value alphabet | ED (structure) + DB (current) | `draft, checks_materialised, dispositioned, merged, suspended, closed, abandoned` |
| `mainline.subject_state` | ED | Names the type under the chip. |
| `Site` | DB | `site_code` |
| `Valid from` / `Expires` | DB | `opened_at` = 2026-08-02T00:00:00Z · `horizon_at` = 2027-08-02T00:00:00Z |
| `HSG250 audit item 23 — permits must clearly specify a time limit for expiry` | STD | Tooltip on `Expires`. |
| `Gate epoch` / `Chain head` / `Under hold` | DB | `gate_epoch` = 1 · `head_seq` = 2 · `under_hold` = false |
| `Display copy ⎙` | ED | |
| `Produce a paper copy for display at the work site (HSE HSG250 ¶18, ¶51)` | STD | Fidelity item 7. |

### 3.2 The typed fields — elements 1, 3, 5

Every one is an empty control with a caret and a placeholder, carries **no provenance chip**,
and is **never echoed back as server data**.

| element | label | placeholder (TYPED) |
|---|---|---|
| 1 | `Title` | `Title of the work this permit authorises` |
| 3 | `Location on site` | `Where on the site the work will be done` |
| 5 | `Work and its limitations` | `What is to be done, and what this permit does not authorise` |

Each carries the hint **`typed on this device · not carried by this deployment`**. That hint is
the single most load-bearing piece of editorial copy on the permit screen: it is what stops a
supervisor's typing from being mistaken for the system's knowledge.

### 3.3 Plant identification — element 4

`Plant identification` · *"The boundary this permit was gated against, as the asset graph
resolved it."* (ED). All values **DB**, from `permit.boundary_certificate`:
`asset_graph_version` = `demo-asset-graph-1`; `Tags declared` 1 · `Tags resolved` 1 ·
`Tags unmodelled` 0 · `Under declared` 0; `computed_at` = 2026-08-02T01:00:00Z.

`boundary certified` / `boundary NOT certified` is **CLIENT**, computed from
`counters.unmodelled_asset_count == 0` (measured: 0 → certified), shown beside the counter it
was computed from and beside the constraint `boundary_certified_when_issued` with its real
predicate. The word is a reading of a number that is on screen next to it.

### 3.4 Hazard identification — element 6 · **the STORE → RETRIEVE → ACT loop**

This is the beat the hackathon brief is most likely to fail us on, and it is the one place the
tense rules bite hardest (§1.2).

| string | source | measured value |
|---|---|---|
| `Hazard identification` | STD (HSG250 Figure 1 element 6) | |
| `raised by recall, not by a checklist` | **ED** | The thesis of the card. Nine words. Cleared. |
| `⚠` `DEMO-INC-0001` `incident` | DB | `precursor.external_ref`, `.kind` |
| `14 March 2019 06:20 UTC` | DB | `precursor.occurred_at` = `2019-03-14T06:20:00Z`. **§1.6.** |
| `SYNTHETIC — Stored energy release during intrusive work` | **DB-TEXT** | `precursor.title`, verbatim, prefix intact |
| `severity gate` 4 · `actual` 4 · `potential` 4 · `basis human_rated` | DB | |
| `source document` `demo/incident-0001.pdf` | DB | `precursor.source_object_key` |
| `SYNTHETIC — recalled precursor DEMO-INC-0001 reaches the clause version this permit relies on.` | **DB-TEXT** | `blocking_check.evidence_summary`, verbatim |
| `this obligation is anchored to the clause version this permit relies on` | ED | |
| `the severity on this obligation was not chosen by whoever raised it` | **ED** | Then it prints severity 4 / `blood_major` / `closure_gen 0` on the obligation beside the same three from the blame closure, and says which browser compared them. |
| `origin` `blame_ancestry` | DB | Why the obligation exists at all. |

**The three loop rows** — labels `RECALLED` / `SHOWN TO` / `STATUS`:

| row | gloss (ED) | values (DB) |
|---|---|---|
| `RECALLED` | `the recall run that armed this obligation` — **past tense, §1.2** | `started_at` = 2026-08-02T03:00:00Z · `policy_version` = `demo-recall-1.0` · `index_generation` = `g1` · counts **candidates 1 · blocking 1 · silenced 0 · deduped 0** — from `mainline_meas.recall_run` |
| `SHOWN TO` | `the obligation was put in front of a named human` | `actor_sub` = `demo.signer`, `issued_at`, `receipt_digest` — from `mainline.exposure_receipt` |
| `STATUS` | `whether anything has answered it` | `open` = true → renders **`OPEN`** and `unanswered on this permit — no disposition of it is live`; `disposition_id` = `null` |

**`open` has no column, and the card says so** in its own sentence: *"open has no column: the
read API derived it from the absence of a mainline.disposition row for this check that is
neither retracted nor expired."* **ED.** Keep it. It is the difference between a field and a
claim.

The interval band between `recall run started` and `obligation materialised` carries
**`subtracted in this browser from the two instants either side — not a column, and not
chipped`** (ED). A subtraction that says it is a subtraction.

> **How to narrate this card in one sentence, cleared:**
> *"A severity-four stored-energy release during intrusive work in 2019 is why this obligation
> is on this permit — the system recalled it, showed it to a named person, and it is still
> open."*

**A caution about the counts, because they are small and they are on screen.** The recall run
returns **one** candidate and **one** blocking result. That is the honest shape of a seeded
world with one precursor in it, and it is fine — but it means the card must never be narrated as
a search that sifted many things down to one. It did not sift; it followed a blame ancestry to
the one clause version this permit relies on and found the one event that reaches it. **Say
"found", not "filtered" or "ranked" or "searched".** The strength of the claim is that the
lookup is *exact*, and a number this small only looks weak if we have implied it should be big.

### 3.5 Precautions — element 7

`Precautions necessary and actions in the event of an emergency` (**STD**, HSG250 Figure 1
element 7) · *"The controlling clause version this permit relies on, quoted as the database
returned it."* (ED).

The clause is **DB-TEXT**, verbatim, prefix intact:

> `SYNTHETIC — Before any intrusive work, stored energy shall be isolated, locked and verified
> at zero by a competent person.`

With `Clause` `7.3.2(b)` · `Generation` 1 · `Control delta` `introduce` · `Severity max` 4 ·
`Canonical sha256` · `At commit` — all **DB**. `Anchors`: `LOTO`, `ZERO_ENERGY` — **DB**,
rendered exactly as returned.

`the worst severity anywhere in this version's blame lineage; projected, never chosen` — **ED**,
tooltip on `Severity max`.

### 3.6 Protective equipment — element 8

`Protective equipment (including PPE)` (**STD**) → `not carried by this deployment`
(**LABELLED-ABSENT**). **Hard-coding a plausible PPE list is forbidden.** *(R9.)*

### 3.7 Signature block — elements 9–13

`HSG250 ¶49 — signatures on permit-to-work forms should be dated and timed.` (**STD**.)
Column headings `Element` / `Signatory` / `Date and time` / `Record` (ED).

Roles are HSG250 Table 1 names and **never "approver"**: `Issuing authority`,
`Performing authority`, `Acceptor`.

| el | row | state | source |
|---|---|---|---|
| 9 | `Issue` · Issuing authority | **unsigned** | `merged_commit` = `null`, with the tooltip *"null while the permit has not been issued — the column, not an inference"* (ED) |
| 10 | `Acceptance` · **Acceptor** | **signed** | `exposure_receipt.actor_sub` = `demo.signer`, `issued_at`, `receipt_digest`, `corpus_root`, `policy_version` — all DB |
| 11 | `Extension / shift handover` | **OMITTED** | `omitted — this deployment has no extension mechanism; no column and no route carry one` (ED) |
| 12 | `Hand-back` | **unsigned** | `certifies: work completed, plant ready for testing and recommissioning` (STD, HSG250) |
| 13 | `Cancellation` | **unsigned** | `certifies: work tested and plant satisfactorily recommissioned` (STD, HSG250) |

**`demo.signer` is labelled the ACCEPTOR and is given no issuing role.** The column is
`exposure_receipt.actor_sub` and it means *who the obligation was shown to* — element 10.
Between two readings of one column we take the one the column's name supports. *(R14.)*

The unsigned rows are not an oversight — **an unsigned hand-back is fidelity item 5**, and a
permit screen with every row pre-signed is the tell of a mock-up.

### 3.8 The action bar and the four beats

| string | source | note |
|---|---|---|
| `1 obligation outstanding` | CLIENT from DB | Singular/plural chosen from `counters.open_blocking` = 1. `obligations outstanding · not read` when null. |
| `Save draft` (disabled) + `Save draft — not carried by this deployment.` | ED | R9's rule for a field with no column, applied to an action. |
| `ISSUE ▸` | ED | **Posts to `/v1/demo/gate-run`. It never calls `POST /v1/permits/{id}/merge`,** which answers `423 Locked` on this subject. A 423 rendered as a gate refusal would be a fake refusal. *(R4, M8.)* |
| `Issuing… 2.3 s` | CLIENT | A **real** elapsed clock driven by the real promise. There is no `setTimeout` anywhere on this surface. |
| `One SERIALIZABLE transaction is open against the database. The clock is this browser's measurement of the round trip; each beat below reports the duration the server measured.` | ED | |

**The disclosure line, which is not optional** (R5). Shape asserted by
`disclosure.ts::DISCLOSURE_SHAPE`; if the composed line does not match, the screen prints it
anyway and says it did not match — it never substitutes or repairs:

```
one request · four beats · POST /v1/demo/gate-run · run_id <id> · response received <ISO> · <n> bytes
```

`Every beat below came back in that one response. Each is revealed on a click, and each shows
the duration the server measured for it. The received-at instant above is this browser's
clock.` (**ED** — the sentence that makes progressive disclosure honest rather than staged.)

**The four beats, measured live 2026-08-15 (`VERDICT PROVEN`, `persisted false`):**

| # | name | label (**DB**, from the payload) | outcome |
|---|---|---|---|
| 1 | `read` | `The permit, and the obligation that is still open on it.` | `00000` |
| 2 | `merge` | `MERGE the permit. One open obligation, no signed disposition.` | **`23514` REFUSED** `gate_closed_when_issued` |
| 3 | `projection_drift_attack` | `THE ATTACK: force the projected counter to zero out of band, then merge again.` | **`P0001` REFUSED** `mainline.fn_permit_merge_gate` |
| 4 | `admit` | `Sign one disposition against the obligation, then merge again.` | `00000` **ADMITTED** |

Every beat label is the payload's own `label` field. **The client composes no beat text.**

**Refusal banner** — two stacked registers, never a modal (R15):

* Operator register: `PERMIT NOT ISSUED` → `PERMIT STILL NOT ISSUED` on the second refusal (ED).
* Database register lead: `The database refused this write. Everything below is what it
  returned.` (ED — **see §1.4 for the beat-3 caveat**.)
* `SQLSTATE` `23514` · `constraint` `gate_closed_when_issued` · `CHECK predicate`
  `((state != 'merged') OR (open_blocking = 0))` with *"Read out of the message below; no field
  carries it."* (ED) · `statement` `CALL mainline.merge_permit(…)` · `elapsed` with *"Measured
  by the server for this beat — not a reveal delay."* (ED). All values **DB**.
* When `constraint_source` is `parsed` rather than `reported` — which is **beat 3's real
  value** — the banner adds *"Recovered from the message text rather than reported by the
  driver — a weakened diagnosis, and it is labelled as one."* (ED). Keep it.

**Beat 3 is the strongest thing this project owns and it is easy to under-sell.** Cleared copy:

| string | source |
|---|---|
| `The outstanding-obligation counter now reads 0.` | CLIENT from DB `observed.counter_forced_to` |
| `The permit was refused anyway.` | ED |
| `The gate did not trust the counter. It counted again, from the obligations themselves, and got 1.` | CLIENT from DB `observed.open_blocking_derived` |
| `mainline.permit.open_blocking set out of band — what a disarmed projector or a careless UPDATE leaves behind` | **DB-TEXT**, `observed.attack`, verbatim |

And the database's own sentence, which is better than anything we would write:

> `MAINLINE: merge refused by mainline.fn_permit_merge_gate — re-derived open obligation count
> is 1 while the projected counter reads zero`

**Beat 4 is shown. The film does not end on a refusal** (R16) — *"a gate that always refuses is
broken, not safe."* `ISSUE ADMITTED`, with `disposition kind` `applied`,
`open_blocking after the signature` 0, `clearance digest (server-computed)`, `permit state`
`merged`.

**Run footer:** `VERDICT PROVEN` · `isolation` `SERIALIZABLE` · `transaction` `rolled_back` ·
`one transaction (equal cluster logical timestamps)` `true` · `this run persisted anything`
**`false`** ← **§1.5, this is `self_persisted`** · `whole database unchanged` `true` ←
`identical`, the weaker reading, shown but not the one we quote. Closing note is the payload's
own `persistence_check.note`, **DB-TEXT**.

If the client's own reading disagrees with the contract:
`THIS CLIENT READ THE PAYLOAD AGAINST THE CONTRACT AND DISAGREED` (ED). A screen that can
contradict its own server is a screen a judge can trust.

---

## 4 · SCREEN TWO — MANAGEMENT OF CHANGE

Subject: `change_request` `DEMO-MOC-0001`, `refs/changes/demo-0001 → refs/heads/main`,
state **`checks_materialised`** (verbatim, §1.1), `head_seq` 1, `gate_epoch` 1,
`counters.open_blocking` **1**, four constraints with real predicates.

### 4.1 The IChemE ribbon

`Initiate · Screen · Review · Approve · Implement` — **STD**, the IChemE Safety Centre's
Management of Change model (v1.0). Our enum sits in a chip **beside** the ribbon, never *as* a
step, and the screen says so: the ribbon *"is not asserting a position the database does not
carry"* and the state is rendered *"exactly as it was returned and not translated into process
language."* (ED.)

### 4.2 The OSHA five headings — 1910.119(l)(2)

All **STD**, verbatim, with the citation printed:

| cite | heading |
|---|---|
| `(l)(2)(i)` | The technical basis for the proposed change |
| `(l)(2)(ii)` | Impact of change on safety and health |
| `(l)(2)(iii)` | Modifications to operating procedures |
| `(l)(2)(iv)` | Necessary time period for the change |
| `(l)(2)(v)` | Authorization requirements for the proposed change |

### 4.3 The typed fields, and the diff that is honest about itself

**No proposed clause text is fabricated.** `mainline.change_request` carries no proposed-text
column, so the engineer types it on camera (**TYPED**):

* `Technical basis` — *"Typed here, now. mainline.change_request carries no technical-basis
  column, so nothing was loaded into this box and nothing will be echoed back as data."* (ED)
* `Reference the source of the change` — the IChemE Initiate-step field, with the strongest
  sentence on this screen: *"This deployment carries no column for the citation either — but it
  does not depend on one: the obligation below was raised by the database's own reverse lookup,
  not by anything typed in this box."* (ED)
* `Proposed wording` — **TYPED**, feeding the comparison below.

The comparison is **CLIENT** and labelled at the point of use:

> `Computed in this browser, just now, between the clause text this deployment returned (struck
> through) and the wording typed into the box above (underlined). It is not a stored diff, it
> is not a kernel claim, and no part of the right-hand side came from the database.`

With nothing typed: *"Nothing has been typed, so there is nothing to compare. The right-hand
side of this comparison has exactly one possible source and it is the box above."* (ED.)

### 4.4 The authorisation matrix — fidelity item 10

The disposition lattice, **DB**, from `GET /v1/checks/{check_id}/disposition`, captioned
`Dispositions legal at virulence <virulence>` with the value in a code chip. Cells read
`required` / `not required` (**DB**).

If no rows come back the screen prints, and **must** print: *"No lattice rows were returned by
this read, so no authorisation matrix is shown. This screen does not carry a fallback table: a
matrix printed from anywhere but the kernel would be a policy this deployment does not
enforce."* (ED.)

There is **no "not applicable" option**, because the vocabulary does not contain one — the
shipped disposition constructor is `mechanism_absent`. The defeater prompts are printed
verbatim as the read returned them, each with a citation box placeholdered
`typed by the engineer — this deployment carries no answer` (**TYPED**).

### 4.5 The absence this screen must NAME — the best-argued thing on either screen

No route in `ROUTES` yields a change request's blocking-check id, and none drives a
change-request merge. **Measured this session, both return 404:**

```
GET /v1/change-requests/{cr_id}/blocking-checks  -> 404
GET /v1/change-requests/{cr_id}/merge            -> 404
```

So the screen renders:

* `Approve change`, **disabled**, with the reason named: `Cannot approve. 1 blocking
  obligation…` (CLIENT from DB `counters.open_blocking`).
* `This control is disabled because no route exists to drive it, and it is wired to nothing.`
  (ED — §1.4: this refusal is the **page's**, and the page says so.)
* `Why there is no approve action here` (ED), and beside it **the 404 route table the
  deployment itself returned**, each undeclared template marked `— not declared`, with the
  `verbatim 404 response body` available. That is evidence for an absence, produced by the
  thing whose absence it evidences.
* `What this deployment does NOT return: the obligation's own row.` (ED.)

**A hardcoded `dec0de00-000d-…` is forbidden.** Taking that id from a document would be exactly
the hardcoded literal the subject index exists to prevent. *(R11, M10.)*

---

## 5 · THE RAW PAYLOAD AFFORDANCE — both screens

| string | source |
|---|---|
| `The bytes below are the response body exactly as it arrived. Nothing has been re-serialised, re-ordered or reformatted.` | ED |
| `GET /v1/… → 200 · 5,691 bytes on the wire · received <ISO> (this browser's clock)` | CLIENT from a real `Exchange` |
| `x-mainline-emulator: local_furl` | header, verbatim — **absent on the deployed origin** |
| `no request has been made from this page yet` | ED |
| `(no bytes arrived)` | ED |

This is what makes the two registers believable, and it is what a judge in devtools will
cross-check. The raw text is the verbatim response body and is **never re-serialised** — a
re-serialised payload is a payload the client has had an opinion about.

---

## 6 · WHAT WOULD MAKE EVERY SENTENCE IN THIS DECK WORTHLESS

Stated plainly so nobody has to infer it.

* A refusal string that did not come back over HTTP in this page load.
* A SQLSTATE, constraint name, digest, count or timestamp typed into a `.ts` file.
* `setTimeout` used to make anything feel like work, anywhere, for any reason.
* A UUID literal in source.
* A "proposed clause text" that no column carries.
* A job description, plant name, crew or PPE list presented as data.
* A `423 Locked` rendered as though it were a gate refusal.
* Saying "the database refused" about the control the **page** disabled.
* Saying the incident was 2024, or that a person was hurt in it.

---

## 7 · OPEN AGAINST THIS DECK

1. **§1.4 — the beat-3 lead sentence.** W5's file, W8's sentence. Recorded above; not yet
   applied, because W8 writes no product code.
2. **`hazard/HazardCard.ts` carries a hard-coded seven-character git commit** in its
   `SEED_CITATION`, rendered on screen as `<file>:<line> @ <commit>`. It is a *source* citation
   rather than a `commit_id`, so it is not the thing `HYG-sha-literal` exists to catch — but it
   is **stale by construction**: it names a commit the tree moves off the moment anything is
   committed, and the screen presents it as a current citation. Flagged for W4 and the
   orchestrator. It is also why no such literal appears anywhere in this deck.
