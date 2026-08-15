<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# FIELD-LEDGER.md — every field on both screens, reconciled and classified

**Worker:** W8 · **Date:** 2026-08-15 · **Checked against:** the built screens in
`verticals/mainline/apps/console/src/operator/**` and live responses from
`scripts/deploy/local_furl.py` over the local CockroachDB node (`mainline_demo`), **not**
against `operator-systems-plan.md`.

> **This document exists to make it impossible for a fabricated value to enter unnoticed.**
> Every field on either screen appears below with exactly one classification. **There is no
> unclassified entry.** If a field appears on screen and not in this table, that is a defect in
> this document and it should be reported as one.

---

## 0 · The four classifications

| tag | meaning | the test a reviewer applies |
|---|---|---|
| **REAL** | The value came from the kernel over HTTP in this page load. Carries an endpoint and a JSON pointer below. | Open the raw payload affordance and find it at that pointer. |
| **TYPED** | An operator types it on camera. Empty until they do. **No provenance chip, ever.** | The field is blank on load and no request supplied it. |
| **LABELLED-ABSENT** | The deployment carries no answer, and the screen **says so in words** rather than leaving a gap or inventing a value. | The words `not carried by this deployment` (or a stated reason) are on screen. |
| **OMITTED** | Deliberately not rendered, with the reason printed. | The row is present and marked `omitted — <reason>`. |

**A fifth state is forbidden and is what this ledger hunts:** a plausible value with no source.

### 0.1 The provenance mechanism, verified

Every read response carries a **flat** envelope: `resource`, `schema_id`, `observed_at`,
`server_date`, `staged`, `staged_note`, `statement_refs[]` and `provenance[]`. Each provenance
claim is `{"chip": "db:column", "pointer": "/…"}`.

**Verified this session:** the wire spells the key `chip`; the plan's interface named it `kind`.
`kernel/envelope.ts::parseProvenance` reads `item.chip ?? item.kind`, so both spellings resolve
and **the chips do render**. Had it read only `kind`, every chip on both screens would have
silently vanished and every REAL field would have looked TYPED. Recorded because it was checked,
not assumed.

Measured example — `GET /v1/permits/{permit_id}` returns 21 `db:column` claims including
`/external_ref`, `/ref_name`, `/state`, `/gate_epoch`, `/head_seq`, `/opened_at`,
`/horizon_at`, `/site_code`, `/counters/open_blocking`.

---

## 1 · SCREEN ONE — PERMIT TO WORK vs HSE HSG250 Figure 1

HSG250 Figure 1 enumerates the elements of a permit-to-work form. All thirteen are accounted
for. Endpoints are same-origin; `{permit_id}` etc. come from `GET /v1/demo/subjects` and are
**never literals in source**.

### 1.1 Figure 1, element by element

| el | Figure 1 element | class | endpoint · JSON pointer | measured |
|---|---|---|---|---|
| **1** | Permit title | **TYPED** | — | placeholder `Title of the work this permit authorises` |
| **2** | Permit reference / identification | **REAL** | `GET /v1/permits/{permit_id}` · `/external_ref` | `DEMO-PTW-0001` |
| 2a | branch name | **REAL** | ″ · `/ref_name` | `refs/permits/demo-0001` |
| 2b | status | **REAL** | ″ · `/state` | **`dispositioned`**, verbatim |
| 2c | validity window | **REAL** | ″ · `/opened_at`, `/horizon_at` | 2026-08-02 → 2027-08-02 |
| 2d | gate epoch / chain head / under hold | **REAL** | ″ · `/gate_epoch`, `/head_seq`, `/under_hold` | 1 · 2 · false |
| 2e | **permit type** (cold work etc.) | **TYPED** | — | **No column carries a permit type.** Operator selects it; labelled `HSG250 Table 2 · selected on this device` |
| **3** | Job location | **REAL + TYPED** | ″ · `/site_code` (REAL) | `Site of record` is REAL; `Location on site` is TYPED |
| **4** | Plant identification | **REAL** | ″ · `/boundary_certificate/*` | `demo-asset-graph-1`; declared 1 / resolved 1 / unmodelled 0 / under-declared 0 |
| 4a | boundary certified mark | **CLIENT-DERIVED** (see §4) | ″ · `/counters/unmodelled_asset_count` | 0 → `boundary certified`; rendered beside the counter it was read from |
| 4b | constraint + predicate | **REAL** | ″ · `/constraints/{i}` | `boundary_certified_when_issued` with its real `CHECK` text |
| **5** | Description of work and limitations | **TYPED** | — | placeholder `What is to be done, and what this permit does not authorise` |
| **6** | Hazard identification | **REAL** | §1.2 below | the whole memory-loop card |
| **7** | Precautions / emergency actions | **REAL** | `GET /v1/clauses/{clause_uuid}/versions/{commit_id}` · `/version/canon_text` | the clause, verbatim, `SYNTHETIC —` prefix intact |
| 7a | clause identity | **REAL** | ″ · `/version/printed_label`, `/gen`, `/control_delta`, `/sev_max`, `/canon_sha256`, `/commit_id` | `7.3.2(b)` · 1 · `introduce` · 4 |
| 7b | anchors | **REAL** | ″ · `/version/anchor_set` | `LOTO`, `ZERO_ENERGY` |
| **8** | Protective equipment (PPE) | **LABELLED-ABSENT** | — | renders `not carried by this deployment`. Hard-coding a PPE list is forbidden |
| **9** | Issue / authorisation signature | **REAL (unsigned)** | `GET /v1/permits/{permit_id}` · `/merged_commit` | `null` → row renders **unsigned**; tooltip *"the column, not an inference"* |
| **10** | Acceptance signature | **REAL (signed)** | `GET /v1/receipts/{receipt_id}` · `/actor_sub`, `/issued_at`, `/receipt_digest` | `demo.signer`, labelled **Acceptor** |
| 10a | receipt detail | **REAL** | ″ · `/lines`, `/total_tokens`, `/expires_at`, `/policy_version`, `/corpus_root` | |
| **11** | Extension / shift handover | **OMITTED** | — | `omitted — this deployment has no extension mechanism; no column and no route carry one` |
| **12** | Hand-back | **LABELLED-ABSENT (unsigned row)** | — | rendered as an **unsigned** row — fidelity item 5 |
| **13** | Cancellation | **LABELLED-ABSENT (unsigned row)** | — | rendered as an **unsigned** row |

**Element 8 and elements 12–13 are different absences and are rendered differently.** 8 is a
capability the deployment does not carry. 12–13 are real form rows that nobody has signed yet.
Collapsing them would lose the distinction that makes the signature block credible.

### 1.2 Element 6 in detail — the hazard card

| field | class | endpoint · pointer | measured |
|---|---|---|---|
| precursor ref / kind | **REAL** | `GET /v1/permits/{permit_id}/blocking-checks` · `/checks/0/precursor/external_ref`, `/kind` | `DEMO-INC-0001`, `incident` |
| occurred at | **REAL** | ″ · `/checks/0/precursor/occurred_at` | **`2019-03-14T06:20:00Z`** |
| title | **REAL** | ″ · `/checks/0/precursor/title` | `SYNTHETIC — Stored energy release during intrusive work` |
| severity gate / actual / potential / basis | **REAL** | ″ · `/checks/0/precursor/severity_*` | 4 / 4 / 4 / `human_rated` |
| source document + sha256 | **REAL** | ″ · `/checks/0/precursor/source_object_key`, `/source_sha256` | `demo/incident-0001.pdf` |
| evidence summary | **REAL** | ″ · `/checks/0/evidence_summary` | verbatim, prefix intact |
| severity / virulence / closure_gen on the obligation | **REAL** | ″ · `/checks/0/severity`, `/virulence`, `/closure_gen` | 4 · `blood_major` · 0 |
| origin | **REAL** | ″ · `/checks/0/origin` | `blame_ancestry` |
| blame closure (max severity, virulence, closure_gen, ancestor count) | **REAL** | `GET /v1/clauses/{clause_uuid}/ancestry` · `/closure/*` | compared client-side; see §4 |
| blame edge attribution / basis / state | **REAL** | ″ · `/blame_edges/0` | |
| **RECALLED** row | **REAL** | `GET /v1/recall-runs/{run_id}` · `/run_id`, `/started_at`, `/policy_version`, `/index_generation`, `/counts/*` | past tense on screen — it is a seeded row that was read, not a retrieval that ran |
| **SHOWN TO** row | **REAL** | `GET /v1/receipts/{receipt_id}` · `/actor_sub`, `/issued_at`, `/receipt_digest` | `demo.signer` |
| **STATUS** row — `open` | **REAL, derived server-side and declared as such** | `…/blocking-checks` · `/checks/0/open` | `true` → `OPEN`. **`open` has no column**; the card prints that sentence itself |
| `disposition_id` | **REAL** | ″ · `/checks/0/disposition_id` | `null` |
| interval between recall and materialisation | **CLIENT-DERIVED** | — | labelled *"subtracted in this browser … not a column, and not chipped"* |
| seed citation (`file:line @ commit`) | **REPOSITORY CITATION — not kernel data** | — | see §5, finding F2 |

### 1.3 The action bar and gate run

| field | class | endpoint · pointer | measured |
|---|---|---|---|
| outstanding count | **REAL** | `GET /v1/permits/{permit_id}` · `/counters/open_blocking` | `1` (the singular/plural word is chosen client-side) |
| `Save draft` | **LABELLED-ABSENT** | — | disabled, `not carried by this deployment` |
| disclosure line | **REAL + CLIENT** | `POST /v1/demo/gate-run` | `run_id` and byte count are real; the received-at instant is the browser clock and says so |
| per-beat name / label / statement | **REAL** | ″ · `/run/beats/{i}/name`, `/label`, `/statement` | four beats; **no beat text is composed by the client** |
| per-beat sqlstate | **REAL** | ″ · `/run/beats/{i}/sqlstate` | `00000` · **`23514`** · **`P0001`** · `00000` |
| per-beat constraint + source | **REAL** | ″ · `/constraint`, `/constraint_source` | `gate_closed_when_issued` (`reported`) · `mainline.fn_permit_merge_gate` (`parsed`) |
| CHECK predicate | **REAL, extracted client-side from the server's message** | ″ · `/run/beats/1/message` | labelled *"Read out of the message below; no field carries it"* |
| per-beat elapsed | **REAL** | ″ · `/elapsed_ms` | 0.011 · 524.153 · 329.951 · 290.828 ms — **server-measured**, labelled *"not a reveal delay"* |
| attack observations | **REAL** | ″ · `/run/beats/2/observed/counter_forced_to`, `/open_blocking_derived`, `/attack` | `0`, `1`, and the attack sentence verbatim |
| admission detail | **REAL** | ″ · `/run/beats/3/observed/*` | disposition `applied`, open_blocking after signature `0`, clearance digest, state `merged` |
| verdict | **REAL** | ″ · `/run/verdict` | **`PROVEN`** |
| transaction facts | **REAL** | ″ · `/run/transaction/*` | `SERIALIZABLE` · `rolled_back` · `single_transaction true` |
| `this run persisted anything` | **REAL** | ″ · `/run/persistence_check/self_persisted` | **`false`** ← the reading the verdict keys on |
| `whole database unchanged` | **REAL** | ″ · `/run/persistence_check/identical` | `true` ← the weaker reading, shown but not quoted |
| persistence note | **REAL** | ″ · `/run/persistence_check/note` | rendered verbatim |
| elapsed clock while in flight | **CLIENT** | — | a real `performance.now()` delta on the real promise. **No `setTimeout` exists on this surface** |

---

## 2 · SCREEN TWO — MANAGEMENT OF CHANGE vs OSHA 1910.119(l)(2)

OSHA 1910.119(l)(2) requires management-of-change procedures to address five matters. All five
are headings on screen, each with its citation printed.

| cite | heading (verbatim) | what fills it | class |
|---|---|---|---|
| `(l)(2)(i)` | The technical basis for the proposed change | `Technical basis` box; `Reference the source of the change` box | **TYPED** — no column carries either |
| `(l)(2)(ii)` | Impact of change on safety and health | the change request itself + its blocking obligation | **REAL** |
| `(l)(2)(iii)` | Modifications to operating procedures | clause of record (REAL) + `Proposed wording` (TYPED) + comparison (CLIENT) | **mixed, each part labelled** |
| `(l)(2)(iv)` | Necessary time period for the change | — | **LABELLED-ABSENT** — no column carries a time period |
| `(l)(2)(v)` | Authorization requirements for the proposed change | the disposition lattice | **REAL**, or LABELLED-ABSENT if no rows return |

### 2.1 Change-request fields

| field | class | endpoint · pointer | measured |
|---|---|---|---|
| reference | **REAL** | `GET /v1/change-requests/{cr_id}` · `/external_ref` | `DEMO-MOC-0001` |
| branch → target | **REAL** | ″ · `/ref_name`, `/target_ref` | `refs/changes/demo-0001` → `refs/heads/main` |
| state | **REAL** | ″ · `/state` | **`checks_materialised`**, verbatim |
| head_seq / gate_epoch | **REAL** | ″ · `/head_seq`, `/gate_epoch` | 1 · 1 |
| opened at | **REAL** | ″ · `/opened_at` | 2026-08-01T03:00:00Z |
| merged commit | **REAL** | ″ · `/merged_commit` | `null` |
| counters | **REAL** | ″ · `/counters/open_blocking`, `/open_conflicts`, `/open_residue` | **1** · 0 · 0 |
| four constraints + predicates | **REAL** | ″ · `/constraints/{0..3}` | `cr_conflicts_resolved_when_merged`, `cr_gate_closed_when_merged`, `cr_identity_conserved_when_merged`, `cr_merge_evidence` |
| IChemE five-step ribbon | **STANDARD, structural** | — | our enum sits in a chip **beside** it, never as a step; screen says the ribbon asserts no position the database carries |
| clause of record (text, label, commit, anchors) | **REAL** | `GET /v1/clauses/{clause_uuid}/versions/{commit_id}` | verbatim |
| proposed wording | **TYPED** | — | **no column carries proposed text**; typed on camera |
| word-level comparison | **CLIENT-DERIVED** | — | labelled *"Computed in this browser, just now … no part of the right-hand side came from the database"* |
| disposition lattice rows | **REAL** *(conditional)* | `GET /v1/checks/{check_id}/disposition` · `/lattice` | renders only if a check id resolves from a live read; otherwise LABELLED-ABSENT with the no-fallback sentence |
| defeater prompts | **REAL** *(conditional)* | ″ · `/defeater_options` | printed verbatim; each citation box is **TYPED** |
| defeater citation | **TYPED** | — | `typed by the engineer — this deployment carries no answer` |
| `Approve change` control | **LABELLED-ABSENT + application-enforced** | — | disabled; reason names the obligation; **the page enforces this, not the database**, and the page says so |
| the 404 route table | **REAL** | `GET /v1/change-requests/{cr_id}/blocking-checks` → **404** | the deployment's own `declared[]` list, with the verbatim body available |

### 2.2 The absence, measured

Both probes were run this session against the local emulator:

```
GET /v1/change-requests/{cr_id}/blocking-checks  -> 404   (body lists the declared routes)
GET /v1/change-requests/{cr_id}/merge            -> 404   (same)
```

`/v1/change-requests/{cr_id}` **is** declared and returns 200. So the screen shows exactly what
it can read and names exactly what it cannot, with the deployment's own 404 as the evidence.
**A hardcoded blocking-check id would be forbidden** and none is present.

---

## 3 · THE CHROME

| field | class | source |
|---|---|---|
| origin | **REAL (browser)** | `location.origin` — no absolute URL is compiled in |
| `X-Mainline-Emulator` | **REAL (response header)** | `local_furl` locally; **absent** on the deployed origin |
| product name `CONTROL OF WORK` | **EDITORIAL** | our name for a generic software category; imitates nobody |
| synthetic watermark | **EDITORIAL** | present in `operator.html` **before any script runs** |
| the four rail registers | **EDITORIAL + LABELLED-ABSENT** | `Permits` carried; the other three say `not carried by this deployment` |
| raw payload / request log | **REAL** | verbatim response bodies, never re-serialised |

---

## 4 · EVERY CLIENT-SIDE COMPUTATION ON EITHER SCREEN

A value computed in the browser is not fabricated, but it is **not the kernel's claim either**,
so each one is enumerated here and each one is labelled where it appears.

| # | computation | inputs | how it is labelled on screen |
|---|---|---|---|
| 1 | `boundary certified` / `NOT certified` | `/counters/unmodelled_asset_count` | rendered beside the counter and the constraint it reads |
| 2 | recall → materialisation interval | two REAL instants | *"subtracted in this browser … not a column, and not chipped"* |
| 3 | obligation vs blame-closure comparison | two REAL payloads | *"compared in this browser, from the two payloads above"* |
| 4 | CHECK predicate extraction | the server's `message` | *"Read out of the message below; no field carries it"* |
| 5 | word-level clause comparison | one REAL string + one TYPED string | *"Computed in this browser, just now … no part of the right-hand side came from the database"* |
| 6 | singular/plural of "obligation(s)" | `/counters/open_blocking` | the number itself is REAL |
| 7 | in-flight elapsed clock | `performance.now()` | *"The clock is this browser's measurement of the round trip"* |
| 8 | received-at instant | browser clock | *"The received-at instant above is this browser's clock"* |
| 9 | disclosure-line shape assertion | the composed line | if it does not match, the screen **prints it anyway** and says so; it never substitutes or repairs |
| 10 | contract anomaly detection | the payload vs the contract | `THIS CLIENT READ THE PAYLOAD AGAINST THE CONTRACT AND DISAGREED` |

**Nothing on either screen is computed in the browser and presented as a database value.**
That is the property this section exists to assert, and it is checkable row by row.

---

## 5 · FINDINGS

Two, both recorded rather than fixed, because W8 writes no product code.

**F1 — the beat-3 lead sentence overstates by one word.** `issue/RefusalBanner.ts` prints *"The
database refused this write"* above **both** the `23514` CHECK-constraint refusal and the
`P0001` refusal raised by `mainline.fn_permit_merge_gate`. The second is a procedural guard
MAINLINE wrote executing inside the database, not a constraint the database enforces on its own
terms. Both are server-side and neither is faked, so this is a precision defect and not an
honesty breach — but the distinction is exactly the one a knowledgeable judge will make
unaided. **Suggested:** vary the lead where `constraint_source == 'parsed'` and
`diagnosis == 'none'`. Owner: **W5**. See `COPY.md` §1.4.

**F2 — a hard-coded seven-character git commit is rendered on screen.**
`hazard/HazardCard.ts::SEED_CITATION` carries `{file, line, commit, quoted}` and the card prints
`<file>:<line> @ <commit>`. It is labelled *"source citation — this repository, not this
response"*, which is honest about what it is. Two problems remain: the line number and the
commit are **stale by construction** — both move the moment the seed file or the tree changes,
and nothing fails when they do — and a seven-hex literal on a published surface is the shape
`scripts/demo/claim_hygiene.py::HYG-sha-literal` exists to refuse (it does not fire here only
because the scanner reads `.md`, not `.ts`). **Suggested:** drop the `commit` field, or assert
the quoted line still matches the cited file in a unit test. Owner: **W4**.

---

## 6 · HOW TO FALSIFY THIS DOCUMENT IN FIVE MINUTES

1. Bring the screens up per `RUNBOOK.md`.
2. Open devtools → Network. Every row in the REAL column above corresponds to a request you can
   see, with a status and a byte count.
3. Pick any REAL field. Open the raw payload affordance beside it and find it at the JSON
   pointer this ledger names.
4. Pick any TYPED field. Confirm it is empty on load, and confirm no response carried it.
5. Click ISSUE once. Confirm one `POST /v1/demo/gate-run` — **one**, not four — and that every
   number in the four beats is at a pointer in that single response body.
6. Confirm the change screen's two 404s are real, and that the route table on screen is the one
   the 404 body carried.

If any step fails, this document is wrong and the screens are not shippable until it is
reconciled.
