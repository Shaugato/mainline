<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->
<!-- prose-hygiene: register -->
<!--
THIS FILE IS A REGISTER, AND IT IS DELIBERATELY NON-COMPLIANT IN ONE PLACE. It quotes
forbidden sentences verbatim beside true ones, and §8.4 pastes a scanner self-test transcript
that contains four deliberately planted violations. It therefore carries the
`prose-hygiene: register` marker, the same marker docs/submission/MUST-NOT-CLAIM.md (lines
5-13), docs/demo/research/r6-honesty.md and docs/demo/story-and-script-plan.md carry.

SCANNING THIS FILE RETURNS EXIT 1 WITH 6 FINDINGS ON 4 LINES, ALL OF THEM INSIDE THE PASTED
SELF-TEST TRANSCRIPT. That is measured and printed at §8.5, not left for somebody to discover.
The command that scans the film WITHOUT this register is at §8.2 and it is the one to run. If
this path is ever added to a prose scanner's sweep list, the scanner must PRINT that it
skipped this file, so "not scanned" is never read as "passed".
-->

# CLAIMS CLEARANCE — the line-by-line audit of the film

**Worker W7 · claims clearance · story-and-script wave · audited 2026-08-15/16 (UTC)**
**Authorities read in full before a single row was written:** `docs/demo/research/r6-honesty.md`
Part A (A1–A17) and `docs/submission/MUST-NOT-CLAIM.md` (fourteen families). The shortlist in
`docs/demo/story-and-script-plan.md` §5 is a subset of both and was not used as the register.
**Binding plan:** `docs/demo/story-and-script-plan.md`, all of §4's rulings.

---

## THE VERDICT, FIRST, BECAUSE IT IS A NO

**194 CLEAR · 13 REWORD · 6 REFUSE — across 213 rows.**

> ## THE FILM AS WRITTEN MAY NOT BE SHOT — AND TODAY IT COULD NOT BE SHOT ANYWAY.

Two separate blocks, and the second is not a claims problem at all:

1. **Six REFUSE rows, all of them one defect in four places plus one uncovered beat.** A spoken
   and specified claim that *"the permit screen turns from blocked to issued"* survives in
   `VO-DEMO.md` and `BEATS.yaml` — **while `ONSCREEN-TEXT.yaml` now bans that exact frame and
   `CLICKS.md` and `FALLBACKS.md` both document that the software does not do it.** Four of the
   six delivered files are already right; two have not caught up. §7.1 gives the exact
   replacement wording per file and line.
2. ~~**The operator surface is not on the deployed origin.**~~ **CLOSED 2026-08-16 — see §12.2,
   row S2.** The finding below was true on 2026-08-15 and is kept exactly as it was written.
   Re-measured today: `/operator.html` answers `200 · 5,097 B`, titled **`Control of Work`**, no
   longer byte-identical to `/`, and **both screens render on the deployed origin.** Condition 1
   of §11 is discharged. The original finding, unedited:

   > **The operator surface is not on the deployed origin.** Two workers measured this
   > independently today, by `GET` only: `FALLBACKS.md` M2 and `ONSCREEN-TEXT.yaml` finding F-1.
   > `GET /operator.html` answers `200` with **4,655 bytes byte-identical to `GET /`**, titled
   > `MAINLINE console`, and its only script asset contains **zero** occurrences of
   > `CONTROL OF WORK`, `1 obligation outstanding` or `cow-`. **The film scored in `CLICKS.md`
   > has no pixels on this origin today.** That is nobody on this sheet's to fix and it is not a
   > claims defect — but it decides whether there is a film at all, so it is condition 1 in §10.

**A second wave has been audited into this file. See §12.** The film re-cut wave adds two or three
spoken blocks for a second use case and compresses the close from 50 s to 22 s; §12 carries every
new spoken sentence, every new on-screen string, the superseding rows, and **four REFUSE rows on
one sentence**. §§1–11 are the story-and-script wave's audit and are unchanged apart from the two
condition markers, both of which are marked rather than silently edited.

**The thirteen REWORD rows are twelve findings, and most of them are one family.** Seven of the
twelve are a **label that claims more than the thing under it** — the exact failure mode W3's own
three-label discipline was invented to catch — and several land in two files at once, because
`ONSCREEN-TEXT.yaml` mirrors `VO-CLOSE.md`'s overlays verbatim by its own declared rule. §7 has
the wording for each, and **five edits by W3 and W1, mirrored by W5, close nine of the thirteen
rows.**

**The 194 CLEAR rows are clear, and several are stronger than the register requires.** Beat 5 —
the falsified counter, the `P0001`, the system grading its own exhibit down at the loudest
moment of the film — is cleared without a single caveat.

---

## 1 · WHAT WAS AUDITED, AND HOW

### 1.1 The corpus of this audit — all seven documents, all delivered

| file | owner | state | audited in | rows |
|---|---|---|---|---:|
| `docs/demo/film/VO-DEMO.md` | W2 | 499 lines | §3 (spoken), §6.2 O9/O10 (its *On screen* blocks) | 30 |
| `docs/demo/film/VO-CLOSE.md` | W3 | 800 lines | §4 (spoken); its C1–C4 overlays are audited as the `c1`–`c4` rows of §6.1, which reproduce them verbatim | 11 |
| `docs/demo/film/BEATS.yaml` | W1 | 356 lines | §6.2 O4–O8 (`on_screen`, `cut_ladder.why`) | — |
| `docs/demo/film/SPINE.md` | W1 | 317 lines | §3 D24 (fallback opener), §6.2 O1–O3 | — |
| `docs/demo/film/CLICKS.md` | W4 | 689 lines | §6.2 O12–O13; its rendered strings each now carry an `ONSCREEN-TEXT.yaml` id, audited in §6.1 | — |
| `docs/demo/film/FALLBACKS.md` | W6 | 720 lines | §5 (spoken) | 18 |
| `docs/demo/film/ONSCREEN-TEXT.yaml` | W5 | 2,392 lines | §6.1 — **every `id` in the file** | 142 |
| the other five files' on-screen rows | — | — | §6.2 O1–O13 | 12 |
| | | | **total** | **213** |

**Why the row counts are not one-per-file.** A string that appears in two files is audited once, in
the file that owns it, and pointed at from the other — `VO-CLOSE.md` owns the naming-block words and
`ONSCREEN-TEXT.yaml` says so itself. Counting it twice would inflate this sheet's own arithmetic,
which is the failure mode §7.8 exists to catch on somebody else's slide.

W5's and W6's files landed while this audit was in progress. Both were read in full and are
audited here on the same terms as the rest; **the earlier state of this sheet, in which they
were reported ABSENT at scanner exit 2, is superseded and §8.1 records why that matters.**

### 1.2 What the three verdicts mean

| verdict | meaning | consequence |
|---|---|---|
| **CLEAR** | the line may be spoken or rendered as written, and every value in it is one this audit traced to a kernel artefact, a migration, a seed, a live response or a committed evidence file | shoot it |
| **REWORD** | the substance is supported but the wording claims more than the evidence carries — usually a *label* that is stronger than the thing under it | exact replacement in §6; the beat survives unchanged |
| **REFUSE** | the line asserts something the run, the render or the payload does not support, and no delivery can rescue it | it does not go on camera in this form; exact replacement in §6 |

### 1.3 The rule this audit worked under

**Nothing was cleared that could not be traced to a file, a line or a live response, and no
family was softened to let a sentence through.** Where a line was defensible only under a
condition, the condition is written into its row rather than assumed. Where a worker's own
evidence column disagreed with the artefact it cited, the artefact won.

### 1.4 What this worker did and did not do

* **Read-only.** One `GET /v1/health` against the live origin (§8.6), pasted. **No `POST`. No
  `terraform` anything. No AWS surface touched. No SSM parameter read or written. No credential
  printed or handled.** W5's ten `GET`s and W6's three are their own measurements, recorded in
  their files; where this sheet relies on one it says so and names the file.
* **One `POST` did happen in this wave and it is not hidden.** W6 discloses at `FALLBACKS.md`
  M11 that `scripts/qa/regression_guard.py` — the command `r6-honesty` Part D prescribes —
  drives `POST /v1/demo/gate-run` itself as its `LIVE` family. It read `PROVEN`, four beats,
  zero mismatches, and the guard's own `SEED` row counts matched afterwards. **This worker did
  not run it and did not `POST`.** Recording it here as well as there, because a clearance
  sheet that let a disclosed `POST` disappear between two files would be doing the small
  version of the thing it exists to prevent.
* **No database work was required**, so no scratch database was created — an empty `w_W7` would
  have been a write with no reader.
* **The pytest suite was not run, and that is safe rather than lazy:** the only file this worker
  writes is `docs/demo/film/CLAIMS-CLEARANCE.md`, and
  `grep -rln "docs/demo" tests/ scripts/ .github/workflows/` returns two tests and one script,
  every one of which names `docs/demo/memory-visible-*.md` in a docstring and none of which
  globs `docs/demo/film/**`. No workflow triggers on `docs/**`. The 988/987/0/0 baseline cannot
  move for a markdown file nothing reads. **If that ever changes, the number comes from a
  `--junitxml` root element and from nothing else.** (W6's `FALLBACKS.md` §4 note (d) separately
  records `regression_guard.py` reading `997 / 996 / 0 / 0 / 1` over a **different scope**; two
  true readings of two different things, and neither is quoted as the other.)
* **Nothing was committed.** Only this file was written.

---

## 2 · THE FAMILIES NOTHING AUTOMATED ENFORCES — named, because a green scan is not a clearance

`r6-honesty.md` Part E and `MUST-NOT-CLAIM.md:36-42` both state the arithmetic gap and refuse to
hide it: fourteen families, nine submission rules, twenty-one scanner rules, and **no rule at all
behind the families this film is most likely to trip over.**

| family | what it forbids | automated rule |
|---|---|---|
| **A5** | agentic-memory tense — any present-tense sentence about the retrieval | **NONE. No scanner reads a tense.** |
| **A8** | *"every refusal in this demo is the database's"* — the defeater-code refusal is the application's | **NONE. No rule reads a migration for an absent foreign key.** |
| **A9** | *"defence in depth, proven"* — the unwelding matrix has never executed in CI | **NONE. No scanner reads a CI job's reach.** |
| **A13** | the staged screens — propagation, silence, the empty agent view, the change request | **NONE.** |
| **A14** | numbers that move — `clearance_digest`, the MI ratchet, suite totals, the migration chain, console headroom | **NONE. No rule re-derives a number.** |
| **A4** | verdict freshness; the forbidden frame on `docs/submission/SUBMISSION.json` | **NONE. No rule reads a JSON verdict.** |
| MNC 11–14 | MI ratchet · the acceptance verdict · the defeater-vocabulary digest · the defeater FK | **NONE** (`MUST-NOT-CLAIM.md:36-42`) |

**Every REFUSE and every REWORD in §6 was found by a human reading an artefact. Not one was
found by the scanner**, and the scanner is green over all six audited files (§8.2). That is the
whole argument for this sheet existing.

---

## 3 · VO-DEMO.md — EVERY SPOKEN SENTENCE

`✓` CLEAR · `~` REWORD · `✗` REFUSE. **Authority** is the file:line this audit read.

| # | beat | spoken | verdict | family checked | authority |
|---|---|---|---|---|---|
| D1 | B0 `0:00` | *"This is the form a site supervisor signs before a crew opens a live machine — and in a moment,"* | ✓ | A3 · A17.2 · MNC-17 lead | `SPINE.md:65` verbatim; watermark on frame `ONSCREEN-TEXT.yaml` `film.watermark`; leads with the refusal, not the category (`r6-honesty.md:194-195`) |
| D2 | B1 `0:12` | *"a database is going to refuse to let it through."* | ✓ | A4 · A5.2 | `23514` from a declarative CHECK at `0:22`. No model in this path: `r6-honesty.md:162` measured `grep -rn "bedrock\|invoke_model"` over the demo-API source — three comments, no call |
| D3 | B1 | *"One request — four beats came back inside it."* | ✓ | R-C | `evidence/demo/operator-capture.json` → `one-press-one-request` HELD, `four-beats-on-screen` HELD, `reveal-3-made-no-request` and `reveal-4-made-no-request` HELD |
| D4 | B2 `0:22` | *"Refused. 23514 — a CHECK constraint, gate_closed_when_issued, named by the database."* | ✓ | **A8** | Scoped to beat 2 alone. `live-gate-run.json` → `data.beats[1].sqlstate "23514"`, `.constraint "gate_closed_when_issued"`, `.constraint_source "reported"` — the name came off the wire, so *"named by the database"* is literal. `VO-DEMO.md` §6 forbids the generalisation in terms |
| D5 | B2 | *"It also says what would fix it."* | ✓ | over-claiming the diagnosis | `data.beats[1].refusal.naa` = `{kind: dispose_obligations, cardinality: 1, description: "1 obligation(s) remain open on this subject; disposing of exactly those restores admissibility"}`. A claim about **this** refusal; forty seconds later the film shows `naa: null · not_computable` on its best one |
| D6 | B2 | *"This panel reveals the other beats in order."* | ✓ | R-C | Reveals measured at **30 ms** and **33 ms**, each making no request. A reveal labelled as a reveal, at a latency no `setTimeout` produces |
| D7 | B3 `0:36` | *"Stored: a severity-four stored-energy release, 2019 — and the blame it left on this clause."* | ✓ | **A3 · A15.3 · R-E · R-F** | `blocking-checks` body: `occurred_at "2019-03-14T06:20:00Z"`, `severity_gate/actual/potential 4`, `title "SYNTHETIC — Stored energy release during intrusive work"`. A severity, not a person. No `WO-88213`, no 2013, no 2024 anywhere in the film (§9) |
| D8 | B3 | *"Recalled: it already ran; this is its record."* | ✓ | **A5 — no scanner behind it** | Past tense, the only admissible tense. `recall_run.started_at "2026-08-02T03:00:00Z"`, a seeded row (`demo_permit.sql:250`) the page read. The only present tense in the film is the re-derivation on the press |
| D9 | B3 | *"Ten seconds later the obligation existed — severity four."* | ✓ | **A2** | `started_at 03:00:00Z` → `materialised_at "2026-08-02T03:00:10Z"`, both columns, both on screen, interval labelled as subtracted in the browser. `recall_run.latency_ms` is **null** in the live body — there is not even a latency here to misuse |
| D10 | B3 | *"Nobody typed that four."* | ✓ | fabrication / seed reshaping | `demo_permit.sql:318` writes `0, 'routine', 0, -- projected over by fn_check_project (MI25)`; the live row reads `severity 4, virulence blood_major`. The disagreement **is** the projection |
| D11 | B4 `0:54` | *"Third beat — the shortcut: the projected counter, forced to zero, out of band."* | ✓ | **R-D** | The payload's own beat-3 `label` and `statement`, rendered verbatim. No forging control exists (`CLICKS.md:444-448`) |
| D12 | B4 | *"Now the CHECK is satisfied."* | ✓ | **A9** | True and narrow: predicate `((state != 'merged'…) OR (open_blocking = 0…))` with `observed.counter_forced_to = 0`. It is why beat 3 answers `P0001` and not `23514`. No redundancy claim in either direction |
| D13 | B4 alt | *"The counter, forced to zero out of band — what a careless UPDATE leaves behind. The CHECK is satisfied."* | ✓ **(conditional)** | R-D · R-K | The middle clause is `observed.attack` verbatim. **Admissible only while that string is on screen** — `ONSCREEN-TEXT.yaml` `b4.panel.attack_observed` marks it as verbatim payload text, which is what makes it quotable |
| D14 | B5 `1:04` | *"Refused anyway. P0001 — the gate counted again, from the obligations themselves, and got one."* | ✓ | **A8 · A9** | `data.beats[2]`: `P0001`, `mainline.fn_permit_merge_gate`, message *"re-derived open obligation count is 1 while the projected counter reads zero"*. Called **the gate**, never *the CHECK constraint* |
| D15 | B5 | *"An attacker who owns the counter does not own the gate."* | ✓ | **A10 · A9** | Scoped to this counter and this gate, which is what beat 3 measured. Corpus wording at `verticals/mainline/demo/USE-CASES.md:267`. No *tamper-proof*, no *split-view*, no second direction claimed |
| D16 | B6 `1:20` | *"Not a checkbox — a question: which isolation point was locked, and who verified it at zero?"* | ✓ | **A12** | The seeded prompt for `MECHANISM_PRESENT_AND_VERIFIED`, verbatim to the character, from the live `GET /v1/checks/{check_id}/disposition` body |
| D17 | B6 | *"Mechanism-absent costs rank four, a second signer; emergency override dies in twelve hours."* | ✓ | over-claiming the lattice | Same body: `mechanism_absent` → `min_signer_rank 4`, `req_second_signer true`; `emergency_override` → `min_signer_rank 5`, `max_ttl_hours 12`. A true subset; nothing added |
| D18 | B6 | *"The engineer answers, and signs."* | **~** | **A12 · R-K** | **§7.5.** Nothing is answered on camera (`CLICKS.md:207-213`; `ONSCREEN-TEXT.yaml` `b6.do_not_render` records the absence so it cannot be quietly added), and the payload returns **no `defeater_code`** — checked: `data.beats[3].observed` carries `disposition_id`, `disposition_kind`, `merge_record` and nothing else |
| D19 | B7 `1:38` | *"00000 — admitted. State merged, head sequence three;"* | ✓ | A14 | `data.beats[3].sqlstate "00000"`, `.observed.merge_record.permit_state "merged"`, `.permit_head_seq 3` |
| D20 | B7 | *"the form turns from blocked to issued."* | **✗** | **A17.1 · Functionality rule** | **REFUSE — §7.1.** Measured at capture stage `04-admitted-and-proven`: header still `dispositioned`, action bar still `ISSUE is locked: mainline.fn_permit_merge_gate refused this write.`, ISSUE still `disabled`. **`ONSCREEN-TEXT.yaml` `forbidden_on_camera` now bans this exact frame** |
| D21 | B7 | *"Nothing was overridden: the obligation was answered."* | ✓ | **A12** | `observed.disposition_kind "applied"`, beside the `emergency_override` lattice row that was not used. About which constructor was signed, not about anybody's judgement |
| D22 | B8 `1:50` | *"Persisted false. One serializable transaction, rolled back — the disposition it minted was written, and unwound."* | ✓ | A4.2 · Part B4 | `persisted false`; `isolation SERIALIZABLE`, `single_transaction true`, `disposition rolled_back`, opened and closed logical timestamps **identical**; `persistence_check.identical true`, `mainline.disposition` 0 rows before and after. Says `persisted false` and never *"nothing was written"* |
| D23 | B8 | *"Press it again yourself."* | ✓ | A4.2 | Non-mutating by construction, proven per run |
| D24 | fallback opener | *"This is what a site supervisor signs before a crew opens a live machine. Watch it get refused."* | ✓ | A3 · MNC-17 | `SPINE.md:86-87` |
| D25 | cut 2 · B0 | *"This is the form a site supervisor signs before a crew opens a live machine —"* | ✓ | as D1 | `VO-DEMO.md:420-421` |
| D26 | cut 2 · B1 | *"and in a moment, a database is going to refuse to let it through."* | ✓ | as D2 | `VO-DEMO.md:423-424` |
| D27 | cut 2 · B2 | *"Refused. 23514 — a CHECK constraint, gate_closed_when_issued, named by the database. One request; four beats came back inside it, revealed here in order."* | ✓ | A8 · R-C | `VO-DEMO.md:427-428` |
| D28 | cut 3 · B6 | *"Not a checkbox — a question: which isolation point was locked, and who verified it at zero? Mechanism-absent costs rank four and a second signer."* | ✓ | A12 | `VO-DEMO.md:433-434`. Drops the attribution clause D18 fails on |
| D29 | cut 4 · B7 | *"00000 — admitted. State merged, head sequence three; the form turns from blocked to issued."* | **✗** | **A17.1** | **REFUSE — §7.1, second spoken location.** `VO-DEMO.md:438-439` |
| D30 | B6 under **Path B** | the B6 line as written, spoken when the disposition panel has not landed | **✗** | **R-K · A13.4** | **REFUSE — §7.3.** `CLICKS.md:501-511` and `ONSCREEN-TEXT.yaml` `b6.path_note` both measure that under Path B the prompts and the lattice are **not on screen**; `VO-DEMO.md:486-487`'s stated fallback ("the question only") is also unavailable, because the question is one of the absent strings |

**VO-DEMO: 26 CLEAR · 1 REWORD · 3 REFUSE.**

---

## 4 · VO-CLOSE.md — EVERY SPOKEN SENTENCE

| # | block | spoken | verdict | family | authority |
|---|---|---|---|---|---|
| K1 | C1 `2:00` | *"An incident from 2019."* | ✓ | A3 · R-E | `precursor.occurred_at "2019-03-14T06:20:00Z"`, live body. Past tense |
| K2 | C1 | *"A retrieval, and ten seconds later, the obligation."* | ✓ | **A5** · A2 | Two column values ten seconds apart, both on the overlay. A noun, not a verb: nothing is retrieving while this is said |
| K3 | C1 | *"And the refusal you just watched, re-deriving it."* | ✓ | **A5** | The participle attaches to the refusal the judge has already seen execute — the one thing in the film that ran on camera |
| K4 | C2 `2:12` | *"Everything here is either in that request or in the apply that created it."* | **~** | **A6** | **§7.6.** The overlay carries a third group (Bedrock), and §7.7/§7.8 move two more rows out of the first two groups |
| K5 | C2 | *"Bedrock is exercised in this repository — not in this path."* | ✓ | **A6** | `evidence/aws/probe/raw-haiku-converse.json` (live `Converse` in `ap-southeast-2`), `evidence/aws/embeddings/manifest.json` (Titan v2), and `r6-honesty.md:162` measuring no Bedrock call in the demo-API source. The strongest twelve words in the block |
| K6 | C3 `2:28` | *"Two refusals, two SQLSTATEs, one SERIALIZABLE transaction."* | ✓ | A7 | `23514` and `P0001`; `isolation SERIALIZABLE`, `single_transaction true`, three savepoints. Every noun fired in the filmed request |
| K7 | C3 | *"The enum in that predicate is ours."* | ✓ | A7 | `'merged':::mainline.subject_state` is inside `data.beats[1].message`. Declared at `0011_type_subject_state.sql`. The type name is in the error string, not in a caption |
| K8 | C3 | *"One cluster, one region, and no scale claim."* | ✓ | **A7 · A2** | Basic tier, `aws-ap-southeast-1`, confirmed live today (§8.6). The concession spoken rather than buried |
| K9 | C4 `2:42` | *"Nothing here separates a considered disposition from a rubber stamp."* | ✓ | **A12** | `MNC-06`'s own text with the scope word `here` intact. `VO-CLOSE.md:474-484` prices every shorter form and rejects each; dropping `here` turns a limit into a slander |
| K10 | C4 | *"We measure deliberation, never threshold it."* | ✓ | A12 · MNC-16 | The register's TRUE INSTEAD, unparaphrased |
| K11 | C4 alt | *"Deliberation is measured, never thresholded."* | ✓ | A12 | `VO-CLOSE.md:496-497` |

**VO-CLOSE: 10 CLEAR · 1 REWORD · 0 REFUSE.**

---

## 5 · FALLBACKS.md — EVERY SPOKEN SENTENCE THE FOUNDER WILL SAY ON CAMERA

Not named in this worker's brief, and audited anyway: these lines are spoken **on camera, live,
at the moment the take is going wrong**, which is precisely when a register gets broken.

| # | case | spoken | verdict | family | authority |
|---|---|---|---|---|---|
| B1 | F-1 cold press | *"That's a cold start. Nothing has called this function for a while, so it's building its container and opening its first connection to the database before it can even ask the question. This is the real thing waking up — I'd rather show you that than cut it."* | ✓ | **A2** | Not one number in it. Describes a mechanism, offers no latency, and refuses the cut. `db.py:18-23` is the mechanism it describes |
| B2 | F-2 `40001` | *"Four-oh-oh-oh-one. That's a serialization failure — the database aborted the whole transaction rather than let two writers interleave under SERIALIZABLE. Nothing was written, nothing was decided, and it does not re-send a merge on my behalf. So I press it again."* | ✓ | A7 · B8's *"nothing was written"* rule | True of an **aborted** transaction, which is a different event from beat 4's minted-and-unwound disposition. **Consistency note, not a defect:** the film forbids *"nothing was written"* about B8 (`VO-DEMO.md:290-293`). Two registers ten seconds apart invite a misread; *"nothing persisted, nothing was decided"* costs one word and removes it |
| B3 | F-3 `423` | *"That four-two-three is not the gate refusing. That is the demonstration protecting itself…"* | ✓ | **A17.1 fabricated exhibit** | The `423` body's own substance, quoted from `transitions.py`. Names it as **not** a refusal, which is the whole point |
| B4 | F-4 beat 4 skips | *"Beat four skipped, so this run is NOT PROVEN — and it says so itself, there, with the reason in its own words. I'll run it again. This endpoint persists nothing, so nothing is left half-done."* | ✓ | **A4.4 the PROVEN trap** | The single most valuable line in the fallback document. `verdict` is `PROVEN` only when `failures` is empty; this refuses to round it up on camera |
| B5 | F-5 devtools | *"One request, four beats… That sentence is on the screen the whole time, and you can't dismiss it."* | **~** | **R-C** | **§7.14.** *"you can't dismiss it"* is measured (`disclosure-line-is-not-dismissible` HELD, 0 controls). *"on the screen the whole time"* is contradicted by this file's own F-12 and by `CLICKS.md` D-2: the strip is not sticky and leaves frame at b3 and b6 |
| B6 | F-6 SEAL chip | *"That says NOT VERIFIED, and NOT VERIFIED is not VERIFIED. Every check that ran passed — and eight did not run at all…"* | **~** | **A10 · A14** | **§7.15.** The claim is right and the **number is not this worker's, not W6's and not r6's**: `r6-honesty` marks the chip as the one item nobody opened, and this same block says *"do not carry the numbers from this page onto camera"* — then scripts one |
| B7 | F-7 silence | *"One field on that screen has no column behind it — `bound.statement`… And the bound is on the retrieval that ran — never on the corpus."* | ✓ | **A13.2 · MNC-11** | A13.2's TRUE INSTEAD, extended only by the corpus-exhaustion denial, which is also correct |
| B8 | F-8 change request | *"There's a second subject carrying the same clause's debt… There is no merge route for it yet, so I'm telling you about it rather than driving it."* | ✓ | **A13.5 · R-I** | Told, never driven, and it says so out loud |
| B9 | F-9 operator UI absent | *"What you're looking at is the MAINLINE console and a terminal. The operator screens… are not on this origin yet, so I'm going to show you the kernel directly instead of the software that sits on top of it. Every refusal you see is still the deployed API answering, with the SQLSTATE the database produced."* | ✓ | **A17.1 · R-N** | Names the loss instead of simulating the frame. Given F-1/M2 this is the **likeliest line in the document to be needed** |
| B10 | F-10 local take | *"One thing before I start: this is running against a CockroachDB node on this machine, not against the deployed URL… The database, the migrations, the constraint and the trigger are the same ones; the hop is local."* | ✓ **(conditional)** | **R-N** | The disclosure is right and is first. **Condition:** *"the migrations… are the same ones"* is a parity claim, so it may be said only after the local node's own chain count is read on the day — the same discipline `271/271` gets on the deployed side |
| B11 | F-13 `413` | *"That's the response ceiling refusing rather than truncating…"* | ✓ | Part B12 | `DEFAULT_MAX_RESPONSE_BYTES` is `136 * 1024` = 139,264, and W5's F-5 measured the deployment naming that exact ceiling in its own `413` body |
| B12 | F-13 transport | *"That didn't complete. I'm not going to narrate a refusal over a request that never got an answer — let me press it again."* | ✓ | **A17.1** | A refusal has a SQLSTATE, a constraint and a reason set; this refuses to dress a failure in them |
| B13 | F-14 admission | *"Admitted — zero zero zero zero zero. The disposition applied, open obligations after the signature: zero, permit state merged, and there's the merge record. And three rows below that: this run persisted anything — false. The gate admitted, and the lock is still on the screen beside it, because none of this was allowed to happen."* | ✓ | **A17.1** | Every value checked against `data.beats[3]` and `data.persistence_check`. **This is the correct B7 and it is already written** — see §7.2 |
| B14 | §3 answer 1 | *"I don't know, and nobody who tells you does. Every timing here is a laptop or one Singapore round trip…"* | ✓ | **A2** | `r6-honesty` Part C, verbatim |
| B15 | §3 answer 2 | *"Yes, and we film them doing it. A cluster admin drops the constraint and it succeeds… The claim is tamper-evidence, never tamper-proofing."* | ✓ | **A10** | Part C, verbatim |
| B16 | §3 answer 3 | *"No. Nothing in this data model separates a considered disposition from a rubber stamp…"* | ✓ | **A12** | Part C, verbatim |
| B17 | §3 answer 4 | *"I don't know, and here is the file that would tell us."* | ✓ | Part C | The strongest sentence available to this project |
| B18 | F-11 second `POST` | **says nothing**, stops the take | ✓ | **R-C · A17.1** | An instruction to be silent, correctly scoped: F-2's second press is exempt because the first is on screen failing |

**FALLBACKS: 16 CLEAR · 2 REWORD · 0 REFUSE.**

---

## 6 · EVERY ON-SCREEN STRING

### 6.1 · `ONSCREEN-TEXT.yaml` — all 142 `id`s

**This is the file that decides what a judge actually reads.** Every `id` in it is accounted for
below. Grouped rows list every id they cover; nothing is summarised away.

| ids | verdict | family checked | authority |
|---|---|---|---|
| `film.watermark` | ✓ | **A3 · R-L** | R-L's own string for a `demo_site` world. The deviation from the committed Kestrel string is declared, reasoned and **measured** (`grep -ril kestrel …/console/src/` returns nothing), with a reversion condition if the UI ever renders Kestrel. The control is preserved and only the noun follows the world |
| `film.chip.stack` · `film.ui.origin_strip` · `film.frame.url_bar` | ✓ | **A6 · R-N** | The chip names only what the URL bar in the same frame confirms, and deliberately omits the cluster version because that read is not in frame on the permit screen. The origin strip is the R-N device and renders `X-Mainline-Emulator` in the page's own words |
| `film.strap.disclosure_fallback` | ✓ | **R-C** | Carries **no run-varying value** by explicit design, so a burned strap cannot be wrong about a run. This is the mitigation for §7.2 and it is correctly specified |
| `film.ui.watermark_strip` | ✓ | A3 | The page's own strip, recorded as `b0 only` because it scrolls away — and explicitly **not** offered as a replacement for the film's watermark |
| `b0.lower_third.problem` · `b0.appbar.product` · `b0.appbar.modules` · `b0.rail.items` · `b0.rail.not_carried` · `b0.header.permit_type_note` · `b0.header.state_ladder` · `b0.header.site_source_note` · `b0.header.display_copy` · `b0.el7.sev_max_note` · `b0.el11.extension` · `b0.actionbar.controls` · `b0.actionbar.save_note` · `b0.signatures.block` · `b0.typed.chip_note` | ✓ | A3 · **R-H** | Editorial strings, each marked `chip: editorial` **and** `editorial: true`, which is the convention that makes the authored half greppable. `CONTROL OF WORK` is deliberately not MAINLINE — the refusal lands inside somebody else's software, which is the founder's whole frame |
| `b0.header.external_ref` · `b0.header.ref_name` · `b0.header.state_chip` · `b0.header.site` · `b0.header.validity` · `b0.header.epoch_and_head` | ✓ | A14 · R-E | **Every one re-read from the capture's own permit body by this audit:** `DEMO-PTW-0001`, `refs/permits/demo-0001`, `dispositioned`, `site_code` a uuid, `opened_at 2026-08-02T00:00:00Z` / `horizon_at 2027-08-02T00:00:00Z`, `gate_epoch 1`, `head_seq 2`, `under_hold false`. The `must_not` on the site row — *never a plant name* — is exactly right |
| `b0.header.permit_type` · `b0.el1.title_typed` · `b0.el3.location_typed` · `b0.el5.work_typed_head` · `b0.el5.work_typed_tail` | ✓ | **R-H · A17.2** | The four typed strings carry `chip: typed` and no provenance chip on screen. **Checked against R-H's prohibition one by one: no plant name, no asset tag, no crew, no company, no PPE list, no identifier and no uuid.** The on-camera tail is three words, so the typing rate is visible |
| `b0.el8.ppe` | ✓ | **R-H** | Renders empty and labelled. An invented PPE list would be the seed-reshaping act this repository has already reverted a worker for |
| `b0.el4.plant` | ✓ | A14 | Verified against the capture: `boundary_certificate` = `{asset_graph_version: "demo-asset-graph-1", tags_declared: 1, tags_resolved: 1, tags_unmodelled: 0}` |
| `b0.el7.clause_text` · `b0.evidence`-side `synthetic_prefix` rulings | ✓ | **A3 · R-F · C4** | The clause quoted as the database returned it, `SYNTHETIC —` prefix kept. `raw_text` and `canon_text` byte-identical on that row |
| `b0.el7.clause_facts` | ✓ | **A14 hex literals** | `7.3.2(b) · 1 · introduce · 4 · 9f12114d…9a39 · LOTO · ZERO_ENERGY`. The digest renders **8 + ellipsis + 4**, never 7 and never 40 — checked against the `commit_id` the capture's own permit and clause bodies carry, whose first eight and last four characters are exactly the ones on screen. `HYG-sha-literal` cannot fire on that shape, and the convention is the repository's own *"twelve, never seven"*. **This row is where this sheet broke its own rule on the first pass — see §9.5** |
| `b0.actionbar.standing` | ✓ | **R-D** | `1 obligation outstanding`, with the `must_not` recording that this counter **never ticks to zero in the film** and that a UI-side decrement would be a fabricated exhibit |
| `b1.button.pending` · `b1.button.pending_note` · `b1.devtools.row` | ✓ | **A2 · A17.1** | The two clocks separated on screen, each labelled with whose it is. No `setTimeout`; the capture measured `press_to_first_beat_ms 1146` *"dominated by the real round trip"* |
| `b2.overlay.sqlstate` | ✓ | A7 · C5 | Two lines, both confirmable against the banner in the same frame, placed **beside** the predicate so the `:::` annotation stays legible |
| `b2.lock.note` · `b2.banner.headline` · `b2.banner.register_lead` · `b2.disclosure.caveat` | ✓ | **A8** | *"The database refused this write"* is scoped to **this** write, which is a real declarative CHECK. Nothing generalises to every refusal in the film |
| `b2.disclosure.line` | ✓ | **R-C** | Measured verbatim in the capture with a real 10,446-byte count. The `must_not` — *do not correct `4 beats` to `four beats`* — is the right instinct: a screen that quietly repaired a malformed disclosure would be disclosing something other than what happened |
| `b2.beat1.rows` · `b2.beat1.statement` · `b2.banner.sqlstate` · `b2.banner.constraint` · `b2.banner.statement` · `b2.banner.message` · `b2.banner.diagnosis` · `b2.banner.reason_set` · `b2.banner.naa` | ✓ | **A5 · A14** | Every field checked against `data.beats[0]` and `data.beats[1]`. The `none_claimed` chip is a **declared** vocabulary extension with its reason: the emitter claims a chip for two of the four SQLSTATEs and not the other two, and inventing one for the others *"would be an endpoint change made for the camera"* |
| `b2.banner.check_predicate` **and** `b2.constraint_table.predicate` | ✓ | **A14 · finding F-2** | **Independently re-measured by this audit and both are real.** The gate-run message carries `((state != 'merged':::mainline.subject_state) OR (open_blocking = 0:::INT8))`; the permit body's `constraints[2].predicate` carries `CHECK (((state != 'merged'::mainline.subject_state) OR (open_blocking = 0)))`. Two renderers, one constraint. **Neither may be edited into the other**, and W5's ruling to keep them as separate entries is endorsed |
| `b2.banner.outstanding` | ✓ | A14 | Composed from the beat's observed count or the reason set's size, *"never from a constant"* |
| `b2.banner.precursor_sentence` | **~** | **A5 · provenance chip** | **§7.13.** *"DEMO-INC-0001 has never been answered for this permit."* is chipped `db:column, editorial: false`, but the app composed the sentence and the payload's own derivation is narrower: `open` is derived from the absence of a disposition *"that is neither retracted nor expired"*. *Never answered* and *no live disposition* are different claims |
| `b2.banner.elapsed` | ✓ | **A2 · finding F-3** | A slot, not a string, with the on-screen note *"Measured by the server for this beat — not a reveal delay."* W5's F-3 catches the trap this audit would otherwise have had to raise: the panel prints one decimal above 1 ms while the payload carries more, so **no overlay, strap or spoken line quotes an elapsed figure at all.** That resolution is correct and is why D9 is the only interval in the film |
| `b3.overlay.loop` · `b3.card.heading` · `b3.card.strapline` | ✓ | **A5** | *"raised by recall, not by a checklist"* is past tense and is declared as the card's **one** editorial sentence, in the source's own comment |
| `b3.precursor.identity` · `b3.precursor.title` · `b3.precursor.severity` · `b3.precursor.source_document` · `b3.evidence_summary` · `b3.blame_edge.attribution` | ✓ | **A3 · A7 · R-E · R-F** | All re-read from the live bodies. `SYNTHETIC —` prefixes kept on all three strings that carry them. *"The date is a column value. No AS OF SYSTEM TIME produced it"* — correct, and the GC window is 4500 s |
| `b3.projection.pair` | ✓ | **A14 · chip discipline** | Both operands chipped; **the equality between them carries no chip**, because the comparison is the browser's arithmetic. That is the single most disciplined chip decision in the file |
| `b3.projection.seed_citation` | ✓ | **A14 · finding F-6** | Shown as a **code citation with its file and line**, under a label saying exactly that, and never as a value from a response — because `fn_check_project` overwrote the seeded value before the row was stored. The pinned seven-character tree ref is **not printed**, which is F-6, a red found and fixed **in the file, never in the scanner** |
| `b3.loop.recalled` | ✓ | **A5 — the family with no scanner** | `tense_rule` states it in the file: *"Everything about this row is PAST."* Counts re-verified live: `n_candidates 1 · n_blocking 1 · 0 silenced · 0 deduped · g1 · demo-recall-1.0`. The `must_not` bans a similarity score, a nearest-neighbour plot and an embedding cloud |
| `b3.loop.shown_to` | ✓ | **R-G · A12** | `demo.signer` as the **acceptor**, from `exposure_receipt.actor_sub`; receipt digest at 8 + 4 |
| `b3.loop.status` · `b3.loop.status_note` | ✓ | **A5 · R-H** | *"open has no column"* — the one value in the loop that is not a column says so **on screen, in the same row**, which is why the `derived` chip beside it can be believed |
| `b3.interval.band` · `b3.exchange_lines` | ✓ | **A2** | `10 s` labelled *"subtracted in this browser… not a column, and not chipped"*, with both column names printed as sub-labels. The per-exchange lines are what a judge cross-checks |
| `b4.control.reveal_beat3_required` · `b7.control.reveal_beat4_required` | ✓ | **R-C** | Labelled as reveals, which is what R-C demands |
| `b4.control.reveal_beat3_as_built` · `b7.control.reveal_beat4_as_built` | **~** | **R-C** | **§7.12.** Both strings recorded because W5 *"may not guess which"* will be on screen — correct. The as-built labels read as writes, and the first states a counter value true of no on-screen row at the moment it is read |
| `b4.panel.headline` · `b4.panel.counter_sentence` · `b4.panel.attack_label` · `b4.panel.attack_observed` · `b4.panel.statement` | ✓ | **R-D** | The forged `UPDATE` appears exactly once and only as text the server sent back. `b4.panel.counter_sentence` is chipped `editorial: true` with the note *"The words are ours; the zero is the payload's"* — the correct treatment, and the one `b2.banner.precursor_sentence` should have had |
| `b5.panel.gate_sentence` · `b5.panel.sqlstate` · `b5.panel.constraint` · `b5.panel.message` · `b5.panel.pair` · `b5.panel.refusal_id` | ✓ | **A8 · A9** | Every field against `data.beats[2]`. The `note` carries the A8 discipline in the file itself: *say "the gate" for this refusal, never "the CHECK constraint"* |
| `b5.panel.parsed_note` · `b5.panel.diagnosis` · `b5.panel.reason_set` · `b5.panel.naa` · `b5.weakening.summary` | ✓ | **Part B / anti-fake** | All five carry `weakening: true` and all are on frame at the film's loudest moment, *"not minimised, moved, shrunk or scrolled past."* **This is the strongest anti-fake evidence in the cut and it costs nothing** |
| `b5` `overlays: NONE` | ✓ | plan §2.1 | No overlay is added in the peak. The only thing added to the frame is silence |
| `b6.signatures.acceptance` · `b6.signatures.issue_row` · `b6.signatures.merged_commit_row` | ✓ | **R-G · A17.1** | `demo.signer` on the acceptance row **and nowhere else in the film**. The Issue row stays unsigned *"including after the admission beat"* — W5 states the reason and calls the pairing b8's setup, which is the same conclusion §7.1 reaches from the other end |
| `b6.defeater.mechanism_present` · `b6.defeater.work_not_intrusive` · `b6.defeater.energy_source_absent` · `b6.defeater.no_escape_hatch` | ✓ | **A12 · R-I · MNC-19** | Three prompts verbatim, re-verified against the live disposition body. Not one is a way of saying the obligation does not apply, and `b6.defeater.no_escape_hatch` carries the rule that if the panel lands without that sentence **the founder does not supply it out loud either** — silence over an unrendered claim |
| `b6.lattice.header` · `b6.lattice.mechanism_absent` · `b6.lattice.emergency_override` · `b6.lattice.keyed_by_virulence` | ✓ | A12 | Re-verified: `min_signer_rank 4/5`, `req_second_signer true`, `req_foreign_org true`, `req_predicate`/`req_reassert` true, `max_ttl_hours 12`. `keyed_by_virulence` prevents a per-record authorisation claim the schema does not carry |
| `b6.do_not_render` | ✓ | **A12 · R-I** | An on-screen **absence**, recorded so it cannot be quietly added, with the causation argument stated exactly: the payload does not return which `defeater_code` was used, so no selection on screen can be shown to be the one that mattered |
| `b7.panel.headline` · `b7.panel.label` · `b7.panel.sqlstate` · `b7.panel.rows` · `b7.panel.merged_at` · `b7.panel.statement` | ✓ | A14 | All against `data.beats[3]`. `disposition_id` is a slot, never a string |
| `b7.panel.clearance_digest` | ✓ | **A14 — the one number that must never be a constant** | Slot only, with the `must_not` spelled out: never captioned as a constant, never spoken, never quoted from a previous run, *"and if it were ever stable the rollback proof would be broken"* |
| `b7.optional.merged_commit` | ✓ | **A14 · C5** | R-K permits it; this cut declines it, and **the reason is the frame, not the value** — the admission panel does not render it and the header two sections above reads `Merged commit null`, which is the live row. Permission recorded, decline recorded |
| `b7.frame.still_locked` | ✓ | **A17.1** | **The correct ruling, in the right file:** *"THE PERMIT SCREEN DOES NOT TURN FROM BLOCKED TO ISSUED, and no string in this file says it does."* This is what makes §7.1 a two-file fix rather than a six-file one |
| `b8.footer.verdict` | ✓ | **A4.4** | A slot with the `must_not` naming the trap precisely: beat 4 skips silently when the receipt expires and *"the verdict falls without the screen looking wrong"* |
| `b8.footer.transaction` · `b8.footer.one_transaction` · `b8.footer.minted` · `b8.footer.unchanged` | ✓ | A4.2 · Part B4 | All against `data.transaction` and `data.persistence_check`; the identical logical timestamps are *"shown, not spoken"* |
| `b8.footer.persisted` | ✓ | **B8's own hard case** | `must_say`: *"Say `persisted false`, never 'nothing was written'. Something WAS written… and it was unwound."* Correct, and it is the sentence §7.4 asks C2's rail to stop contradicting |
| `b8b.change.header` · `b8b.change.ribbon` · `b8b.change.counter` · `b8b.change.constraint` · `b8b.change.route_table` | ✓ | **A13.5 · R-I** | The ribbon marks **no** current step because no column maps one, and the screen *"does not silently equate"* the industry model with the record's enum. The 404 route table is the deployment confirming its own absence |
| `b8b.change.approve_disabled` · `b8b.change.proposed_wording` | ✓ | **R-I** | The disabled control is *"wired to nothing"* and explicitly **not** pointed at the permit's merge route — *"a button that refused a different record would be a prop."* The Proposed wording box is empty and says why. A hard-coded proposed clause is forbidden in the file's own words |
| `c1.overlay.columns` · `c1.overlay.strap` · `c1.rail.line1` | ✓ | **A5 · A7 · A13.3** | Reproduced verbatim from `VO-CLOSE.md` §2.2 with the four embedded payload values individually chipped and the `refused at` slot marked *"Never filled from the reference run."* The rail's *"constrains the agent"* is rhetoric about agentic systems and does **not** assert an agent called this deployment — `v_agent_actions` holds 0 rows and zero stays the true answer |
| `c2.overlay.aws` | **~** | **A6** | **§7.7 and §7.8**, mirrored here verbatim from `VO-CLOSE.md` §3.1: `SSM Parameter Store` under `IN THIS REQUEST`, and `Amazon S3` under a heading whose number is `24 created` |
| `c2.rail.line2` | **~** | **A4.2** | **§7.4**, mirrored: `persisted: false — this endpoint cannot write` |
| `c3.overlay.cockroachdb` | **~** | **A7** | **§7.9 and §7.10**, mirrored: the recursive CTE and the `256/256` figure under `IN THIS DATABASE, EARLIER`. The rest of the block — including the `CCL v26.2.5` value read live and the `:::` predicate quoted to the same characters as b2 — is clear |
| `c3.rail.line3` | ✓ | **A2 · A7** | *"— and no scale is claimed"* refuses the question's own premise on screen |
| `c4.overlay.limit` | ✓ | **A12** | `MNC-06`'s TRUE INSTEAD, unparaphrased, all three sentences |
| `c4.overlay.rail_all_four` | **~** | A4.2 · A14 | **§7.4 and §7.10**, mirrored: it carries both *"cannot write"* and the unqualified `256/256` for the film's last eight seconds |
| `c4.overlay.urls` · `end.card` | ✓ | **A4 · R-M · R-L** | Both URLs sourced (`README.md:25`; `evidence/deploy/LIVE.md:8`), neither read aloud, and the `must_not` states R-M in the file: **no camera at `docs/submission/SUBMISSION.json` while `demo_url` reads `UNRESOLVED`.** The end card's last line is the same watermark string that has been on frame since 0:00 |
| `forbidden_on_camera` — all 21 entries | ✓ | **the whole register** | Independently checked against `r6-honesty` Part A: it covers `clearance_digest` as a constant, 7/40-hex literals, bare invariant ids, `SUBMISSION.json`, CloudFront, CDN, *edge*, multi-region, tamper-proof, split-view resistance, any cloud console, CMEK/PrivateLink, vector visualisations, changefeeds, the propagation screen, the 2024/2013/`WO-88213` world, a global "N/A", real people and operators, music, a ticking header counter, **the permit screen turning from blocked to issued**, and a `423` in a refusal banner. **Nothing in Part A that could reach a frame is missing from this list** |
| `todo` T-1 … T-5 · `findings` F-1 … F-6 | ✓ | **A16 / not-built discipline** | Five unsourced strings recorded as gaps with the request that would produce each, **none filled with a plausible placeholder**, and six findings each with an owner. T-1 refuses to write a route into the file that has never answered |

**`ONSCREEN-TEXT.yaml`: 135 CLEAR · 7 REWORD · 0 REFUSE — of 142 ids.**
*(The seven REWORD ids are `b2.banner.precursor_sentence`, `b4.control.reveal_beat3_as_built`,
`b7.control.reveal_beat4_as_built`, `c2.overlay.aws`, `c2.rail.line2`, `c3.overlay.cockroachdb`
and `c4.overlay.rail_all_four` — counted as ids, not as findings, because four of them are one
`VO-CLOSE.md` edit each.)*

### 6.2 · The on-screen strings specified in the other five files

| # | string | verdict | family | authority |
|---|---|---|---|---|
| O1 | `SPINE.md:97-98` lower-third strap | ✓ | A5 · A12 | Mirrored at `ONSCREEN-TEXT.yaml` `b0.lower_third.problem`; states the problem and the audience in writing at zero seconds of voice |
| O2 | `SPINE.md:285-287` R-C disclosure strap | ✓ | **R-C · A2** | Mirrored at `film.strap.disclosure_fallback` **carrying no run-varying value**, which is the correct hardening |
| O3 | `SPINE.md:288` panel header `one request · four beats · response received <generated_at>` | ✓ | R-C | Capture asserts the live strip's shape, its real byte count, and **0** controls inside it |
| O4 | `BEATS.yaml` `b0`–`b6`, `b8` `on_screen` | ✓ | A3 · A5 · R-D · R-I | Read line by line; each is a faithful one-line summary of what W5 then specifies |
| O5 | `BEATS.yaml:203-205` `b7.on_screen` — *"the permit screen turning from blocked to issued"* | **✗** | **A17.1** | **REFUSE — §7.1, third location** |
| O6 | `BEATS.yaml:334-337` `cut_ladder` rank 4 `why` — same clause | **✗** | **A17.1** | **REFUSE — §7.1, fourth location.** It is the rationale a person reads at 02:00 while executing the ladder, which is the worst moment to be told the screen turns |
| O7 | `BEATS.yaml:257-260` `c3.on_screen` — the flat CockroachDB list | **~** | **A7** | **§7.11.** Three of its items did not run in the filmed request and one ran nowhere in this world; `BEATS.yaml` is the file the others inherit from |
| O8 | `BEATS.yaml` `c1`, `c2`, `c4`, `end` `on_screen` | ✓ | A6 · A12 | `c2` names the not-in-path service on its own labelled line |
| O9 | `VO-DEMO.md:279` — *"The permit screen turns from blocked to issued."* | **✗** | **A17.1** | **REFUSE — §7.1, second location.** A stage direction is an instruction to a builder, and this one instructs a render that can only be produced by faking it |
| O10 | `VO-DEMO.md` B0–B8 *"On screen:"* blocks, excluding O9 | ✓ | A5 · A14 · R-D | Each names values now individually sourced in `ONSCREEN-TEXT.yaml`; the B7 block correctly captions the clearance digest as server-computed and never as a constant |
| O11 | `VO-CLOSE.md` C1–C4 overlays and the end card | — | — | **Audited as the `c1`–`c4` and `end` rows in §6.1**, since W5 reproduces them verbatim and declares `VO-CLOSE.md` the owner of the words. Verdicts are carried there and not double-counted here |
| O12 | `CLICKS.md` §5 rendered strings (banners, panels, footer, lock note, typed labels, origin strip, change screen) | ✓ | A17.1 · A14 | Every one now has an individually sourced `ONSCREEN-TEXT.yaml` entry; where the two files describe the same string they agree |
| O13 | `CLICKS.md:196` — the two as-built reveal labels | **~** | **R-C** | **§7.12.** Carried in `ONSCREEN-TEXT.yaml` as `*_as_built` with the same ruling |

**Other files' on-screen strings: 7 CLEAR · 2 REWORD · 3 REFUSE — of 12 verdict rows.**
*(Thirteen rows appear above; O11 is a pointer to §6.1 and carries no verdict of its own, so it is
excluded from every count on this sheet.)*

---

## 7 · THE FINDINGS, WITH EXACT REPLACEMENT WORDING

**This worker owns one file and has edited no other.** Every replacement is offered to the named
owner at the named line.

### 7.1 · REFUSE — *"the permit screen turns from blocked to issued"* — ONE DEFECT, FOUR PLACES

**What was measured, independently of W4's and W5's escalations.**
`evidence/demo/operator-capture.json`, stage `04-admitted-and-proven`, in that stage's own DOM:

* the action bar reads `ISSUE is locked: mainline.fn_permit_merge_gate refused this write.`
* the ISSUE button carries `disabled`
* the header status chip still reads `dispositioned`
* `Merged commit` still renders `null`

The payload agrees from the other side: `persistence_check.after.permit_row` is
`{state: "dispositioned", head_seq: 2, open_blocking: 1, merged_commit: null}` — **identical to
`before`**. The admission happened inside a transaction that was rolled back. **The screen is
correct and the sentence is wrong**, and the only way to make the sentence true on camera is to
fake the render — the one act this wave exists to prevent, and a **rules violation** under the
contest's own Functionality requirement (*the Project must function as depicted in the video*).

**Four of the six delivered files already say this.** `CLICKS.md` §3 (second box) and §7.1;
`FALLBACKS.md` F-14, which supplies a true replacement line; and `ONSCREEN-TEXT.yaml`, twice —
`b7.frame.still_locked` and a `forbidden_on_camera` entry banning *"the permit screen shown
turning from blocked to issued"*. **Two files have not caught up, and one of them is the
voice-over.**

**Caveat on the measurement, stated rather than buried:** the capture was taken against
`http://127.0.0.1:8741` with `X-Mainline-Emulator: local_furl` and `is_the_deployed_url: false`.
The behaviour is a property of the built client, so it carries to the same bundle anywhere — and
§10 condition 1 means the bundle on the origin is a separate question. It changes nothing about
the refusal: **no payload field supports the sentence either.**

| # | file:line | owner | replace | with |
|---|---|---|---|---|
| 1 | `VO-DEMO.md:272-273` | **W2** | *"**00000** — admitted. State **merged**, head sequence **three**; the form turns from blocked to issued. ·hold 0.4· Nothing was overridden: the obligation was answered."* | **"00000 — admitted. State merged, head sequence three; the merge it refused twice now completes. ·hold 0.4· Nothing was overridden: the obligation was answered."** |
| 2 | `VO-DEMO.md:279` | **W2** | *"The permit screen turns from blocked to issued."* | **"The permit screen does not turn: the header still reads `dispositioned`, `ISSUE` stays disabled with its lock note, and the admission and the lock are in frame together. That contradiction is B8's setup and it is kept."** |
| 3 | `VO-DEMO.md:438-439` (cut 4) | **W2** | *"…head sequence three; the form turns from blocked to issued."* | **"00000 — admitted. State merged, head sequence three; the merge it refused twice now completes."** |
| 4 | `BEATS.yaml:203-205` (`b7.on_screen`) | **W1** | *"…and the permit screen turning from blocked to issued with the subject's post-merge fields beside it."* | **"…with the subject's post-merge fields beside it — while the permit header still reads dispositioned and ISSUE stays disabled, which is B8's setup and is not a defect."** |
| 5 | `BEATS.yaml:334-337` (`cut_ladder` rank 4 `why`) | **W1** | *"ADMITTED and the screen turning from blocked to issued is the whole job of this beat…"* | **"ADMITTED, and the merge completing beside a still-locked ISSUE button, is the whole job of this beat: it proves b2 was not a bug. Three seconds of dwell is not."** |

**Word arithmetic, so W2 does not have to redo it.** Replacement 1 is **21 words** against a
budget of 21 — **1.75 w/s over 12 s, unchanged.** Replacement 3 is **14 words**, exactly the 14
that cut declares. Nothing in `VO-DEMO.md` §2's table moves.

**Why *"the merge it refused twice now completes"* is admissible where the original is not:** it
is a claim about the beat-4 panel, which **is** in frame — `permit state merged`, `merged_at`,
the merge record and `SQLSTATE 00000`, every one a payload value — and not a claim about the form.

### 7.2 · The line that is already written, in the wrong file

`FALLBACKS.md` F-14 carries a B7 that is true, in frame, and stronger than the original:

> *"Admitted — zero zero zero zero zero. The disposition applied, open obligations after the
> signature: zero, permit state merged, and there's the merge record. And three rows below that:
> this run persisted anything — false. The gate admitted, and the lock is still on the screen
> beside it, because none of this was allowed to happen."*

It is too long for a 12 s beat, so it is not the fix; it is the proof that the fix costs nothing.
**W2 may prefer to adapt it rather than take §7.1's wording, and either is cleared.**

### 7.3 · REFUSE — B6 has no admissible voice-over under Path B

`CLICKS.md:482-486`, `:629` and `ONSCREEN-TEXT.yaml` `b6.path_note` all measure the same thing:
the three defeater prompts and the lattice render **on the change screen only**; the permit screen
makes no `GET /v1/checks/{check_id}/disposition`. Under **Path B** those strings are not in frame
and `CLICKS.md:510` states the VO must not describe them. `VO-DEMO.md:486-487`'s fallback — *"the
question only"* — is also unavailable, because the question is one of the absent strings.

**Exact replacement, offered to W2 as a new entry in `VO-DEMO.md` §5:**

> **B6 · PATH B — the disposition panel has not landed** · `[1:20]` · 14 s · **20 w** · 1.43 w/s
>
> **"The obligation is still open — and open is not a column here: it is derived from the absence
> of a live disposition."**

Every value is on screen under Path B: `ONSCREEN-TEXT.yaml` `b3.loop.status` renders
`● OPEN — unanswered on this permit — no disposition of it is live`, `b3.loop.status_note` prints
*"open has no column"* in the same row, and the `derived` chip is beside it. Under Path B the
ladder's rank-3 trim (18 s → 14 s) applies and the recovered seconds go nowhere else.

**The honest consequence:** under Path B the film loses its clearest Impact beat. If the panel can
land before the shoot it is worth more than any other four seconds available — and
`ONSCREEN-TEXT.yaml` T-3 records that the read already answers `200` with all three prompts and
five lattice rows, so **the gap is the panel, not the data.**

### 7.4 · REWORD — *"this endpoint cannot write"* contradicts the film's own B8

**Locations (four, two of them on screen):** `VO-CLOSE.md:264` and `:442`; mirrored at
`ONSCREEN-TEXT.yaml` `c2.rail.line2` and `c4.overlay.rail_all_four`. Spec rows at
`VO-CLOSE.md:115` and `:509`. Owner: **W3**, mirrored by **W5**.

**Why.** The endpoint **does** write. Beat 4 mints a `disposition_id` — `d2da1bd4-…` in the
reference run — and the payload proves the unwinding with that identifier
(`minted_disposition_rows_after_rollback: 0`). B8 says so out loud, and `VO-DEMO.md:290-293` and
`ONSCREEN-TEXT.yaml` `b8.footer.persisted` **both forbid the shorter form in terms**: *never say
"nothing was written."* *"Cannot write"* is that forbidden sentence in three words, on screen
from 2:12 to 2:50 while the founder said the precise version at 1:50.

**Replace** `-> persisted: false — this endpoint cannot write`
**with** `-> persisted: false — this call is non-mutating by construction`

That is A4.2's own sanctioned wording (`PROVEN-STATE.md:257-268`), the same length on screen, and
it survives the follow-up question. Equally good if W3 prefers the mechanism to the term of art:
`-> persisted: false — nothing it writes survives the transaction`.

**Consistency note, not a finding:** the same phrase appears in prose at `VO-DEMO.md:307` and
`CLICKS.md:661`. Neither is on screen or spoken; both would read better with the same fix.

### 7.5 · REWORD — *"The engineer answers, and signs."*

**Location:** `VO-DEMO.md:248`. Owner: **W2**.

Nothing is answered on camera: `CLICKS.md:207-213` forbids selecting a defeater radio, and
`ONSCREEN-TEXT.yaml` `b6.do_not_render` records the absence with the reason — the payload does not
return which `defeater_code` the endpoint's transaction used, so **no selection on screen can be
shown to be the one that mattered.** Speaking the causation is the same claim as clicking it, over
a frame in which nothing is selected and the Issue row is visibly unsigned.

**Replace** *"The engineer answers, and signs."*
**with** **"Answering one is the way through."** — 6 words for 5, B6 at **35 w · 1.94 w/s**, inside
W2's own 1.95 ceiling. It is what the payload's NAA says: *"disposing of exactly those restores
admissibility."*

**Shorter alternative if the beat is retimed:** **"One disposition is signed."** — 4 words, B6 at
33 w · 1.83 w/s, pointing forward at beat 4 rather than at the person on screen.

### 7.6 · REWORD — C2's first spoken sentence, once §7.7 and §7.8 land

**Location:** `VO-CLOSE.md:269-270`. Owner: **W3**.

*"Everything here is either in that request or in the apply that created it"* is already amended
by its own next sentence for Bedrock; after §7.7 and §7.8 it is false about three of the overlay's
rows rather than one. The pair is delivered inside 12.6 s so a listener hears the correction — but
a judge who **pauses** at 2:14, which is the whole design of this block, does not.

**Replace** with **"Every line here says which: in that request, in the apply, or exercised
elsewhere. Bedrock is exercised in this repository — not in this path."** — **24 words, exactly
`BEATS.yaml`'s `c2` budget**, and it states the block's real virtue more directly than the original.

### 7.7 · REWORD — SSM Parameter Store is not in the filmed request

**Locations:** `VO-CLOSE.md:243-244`; mirrored at `ONSCREEN-TEXT.yaml` `c2.overlay.aws`. Owner:
**W3**, mirrored by **W5**.

`verticals/mainline/apps/demo-api/src/mainline_demo_api/db.py:18-23` states it in its own words:
the DSN is *"read here once per cold start by name from `$MAINLINE_DSN_PARAM`"* and *"cached for
the life of the container"* (`_dsn_cache` at `:171`). `CLICKS.md:130-132` then warms the endpoint
**on purpose** within 60 s of the take. **The film's own pre-roll is what makes this label false**:
`IN THIS REQUEST` is defined at `VO-CLOSE.md:137` as *"it executed while the `POST` a judge just
watched was in flight"*, and a warm invocation makes no `GetParameter` call.

**Replace the SSM row in the `IN THIS REQUEST` group with a labelled line of its own**, exactly as
Bedrock gets and for the same reason:

```
  SSM Parameter Store  —  READ ONCE AT COLD START, NOT ON THIS REQUEST
    /mainline/demo/cockroach_dsn — a SecureString the deploy script writes and the handler
    reads by name, cached for the life of the execution environment. This take is warmed on
    purpose, so that call is not in the filmed request.
```

**And amend the IAM row's descriptor**, since its inline policy is that same call:

```
  AWS IAM                     one execution role, assumed on every invocation; its one inline
                              policy is the GetParameter above
```

The parameter **name** on screen is a path, not a value, and stays — nothing here prints or handles
a credential.

### 7.8 · REWORD — the S3 state bucket is not one of the 24

**Locations:** `VO-CLOSE.md:248` under the heading at `:246`; mirrored at `c2.overlay.aws`. Owner:
**W3**, mirrored by **W5**.

`APPLIED.md:14` records `24 created, 0 changed, 0 destroyed`, and `:18-21` accounts for all 24:
*"Eleven resources are the demo API; thirteen are the cost guard."* `APPLIED.md:22-23` then says of
the state bucket: *"Preceding it, and the first mutating action of the whole deploy."* It is the
store the apply wrote its state **into**, not a resource the apply created — and the heading
carries the number two lines above it, inviting a judge to count wrong.

**Replace** the S3 row **with**:

```
  Amazon S3  —  CREATED BEFORE THE APPLY, AS ITS STATE STORE.  NOT ONE OF THE 24.
  Terraform state · versioned · SSE-S3 · public access blocked on all four settings
```

**and annotate the remaining member so the arithmetic closes on screen:**

```
  CloudWatch alarms + SNS     the cost guard — thirteen of the twenty-four: three alarms on
  + AWS Budgets               three timescales into one topic, a responder that sets reserved
                              concurrency to zero, and the budget
```

### 7.9 · REWORD — the recursive CTE did not run in this database for this world

**Locations:** `VO-CLOSE.md:331-337` under the heading at `:322`; mirrored at
`c3.overlay.cockroachdb`. Owner: **W3**, mirrored by **W5**.

**Credit, then the half still open.** W3 found this and wrote it up at `VO-CLOSE.md:579-614`; this
audit re-derived every clause independently. `closure_write.sql:152` is
`WITH RECURSIVE anc (event_id, depth) AS (`; `demo_world.sql:333-341` records that a seed applied
as one text **cannot call** a parameterised top-level statement; and the seeded closure row carries
`computed_by = verticals/mainline/db/seeds/demo/demo_world.sql`, `projector_ver = demo-1` at
`:342-359`. **The half still open is the heading.** The block's body is honest, but it sits under
`IN THIS DATABASE, EARLIER`, defined at `VO-CLOSE.md:138` as *"it ran against this database before
the shoot"* — and the CTE did not run against this database at all for this world. A judge reading
the heading gets a claim the column's own body then denies.

**Replace** the right-column CTE block **with** a self-labelled block, matching Bedrock's treatment:

```
recursive CTE  (WITH RECURSIVE)  —  IN THIS REPOSITORY, NOT IN THIS WORLD
  the sanctioned closure writer, db/queries/closure_write.sql:152.
  THIS world's closure row was written by the seed and says so:
  computed_by = demo_world.sql · projector_ver = demo-1.
  It did not run in this request, and it did not write this row.
```

**Cheaper alternative, equally honest:** drop the CTE from C3 entirely. It is the only feature on
the slide that fired nowhere in this world, and the block loses nothing a judge came for.

### 7.10 · REWORD — `256/256` is not established against this database

**Locations:** `VO-CLOSE.md:339-344` and `:449-450`; mirrored at `c3.overlay.cockroachdb` and
`c4.overlay.rail_all_four` — the latter on screen for the film's last eight seconds. Owner: **W3**,
mirrored by **W5**.

The `42501` block's **first** clause is sound and strong: five privilege gaps were found against
the deployment *"one HTTP request at a time"* (`evidence/deploy/LIVE.md:58-71`). The **second**
clause is `scripts/qa/privilege_conformance.py`'s baseline, and that script's `DEFAULT_DSN` at
`:130` is `postgresql://root@localhost:26257/defaultdb`. `STATE-OF-THE-BUILD.md:181-182` states the
`120/120 · 256/256` baseline and **names no target**; no evidence artefact attributes it to
`mainline_demo` on CockroachDB Cloud, and MUST-NOT-CLAIM family 9 is the standing warning about
exactly that inference. **A real measurement with an unestablished target, under a heading that
establishes one.**

**Replace** the second clause **with** its own labelled block:

```
privilege conformance  —  MEASURED BY SCRIPT.  NOT ESTABLISHED AGAINST THIS DATABASE.
  256/256 ungranted pairs refused with 42501, 0 differences.
  The negative direction is falsifiable and was falsified.
```

**and replace the C4 rail's fourth clause** with *"the refusal itself; 42501 on 256/256 ungranted
pairs in privilege conformance; a ledger that publishes what did not run"* — two words that move
the claim from *this deployment* to *that test*.

**Cheaper alternative:** keep only the live half. `42501` read back off this deployment during the
deploy is already the answer to *access control*, and it needs no qualifier.

**W3's §7.2 remains correct and is endorsed:** `120/120` may never go on screen, because `main()`
applies the matrix before probing and repairs the defect it is meant to detect.

### 7.11 · REWORD — `BEATS.yaml`'s `c3.on_screen` is the flat list W3 warned about

**Location:** `BEATS.yaml:257-260`. Owner: **W1**.

The line reads *"the CHECK constraint; the two trigger functions; the recursive CTE blame closure;
and the SQLSTATEs the client read back — 23514, P0001 and the ungranted-pair 42501"* as one
undifferentiated list. Three of those did not run in the filmed request and one ran nowhere in this
world. `BEATS.yaml` is the file the others inherit from, so a flat list here is how a false line
reaches the screen even after §7.9 and §7.10 are fixed downstream.

**Replace** `c3.on_screen` **with**:

```yaml
    on_screen: >-
      Two labelled columns. Left, what fired inside the request a judge just watched:
      cluster, region and version; the isolation level; the CHECK constraint; the merge-gate
      trigger function; the composite foreign keys; and the two SQLSTATEs the client read
      back, 23514 and P0001. Right, under its own label: fn_check_project, the recursive-CTE
      closure writer and the ungranted-pair 42501 — each carrying the line that says it did
      not run in this request.
```

### 7.12 · REWORD — the two advance controls are labelled as writes

**Location:** the built page, quoted at `CLICKS.md:196` and recorded at
`ONSCREEN-TEXT.yaml` `b4.control.reveal_beat3_as_built` / `b7.control.reveal_beat4_as_built`.
**Owner: the operator wave**, not any worker on this sheet.

The build renders `But the counter now reads 0 ▸` and `Answer the obligation, then issue again ▸`.
Both read as new actions; R-C requires controls labelled as reveals. The first is worse than
imprecise — at the moment it is read, **no on-screen row says the counter is zero** (the header
holds `1` for the whole film by design), so the label promises a state the page is not yet showing.

**This audit endorses W4's replacement strings unchanged** (`CLICKS.md:200-202`), which W5 has
already recorded as `*_required`: `Show what happens if the counter is forced to zero ▸` and
`Show the beat where one signed disposition is admitted ▸`.

**If they do not land**, the labels are still on camera and W5's ruling governs: the built label is
filmed as it is — it is honest and its number is the payload's — and the founder narrates it as a
reveal, never as an act: no *"now I'll"*, no *"let me try"*, no *"watch me"*. **Recorded as a known
weakness of the take rather than fixed in narration and forgotten.**

### 7.13 · REWORD — *"has never been answered"* claims more than `open` carries

**Location:** `ONSCREEN-TEXT.yaml` `b2.banner.precursor_sentence`. Owner: **W5**.

The string *"DEMO-INC-0001 has never been answered for this permit."* is chipped `db:column` with
`editorial: false`, but the app composed the sentence (`RefusalBanner.ts:274`) and only the label
inside it is a column. Two things follow:

1. **The chip over-claims.** Compare `b4.panel.counter_sentence`, which W5 chips `none_claimed` /
   `editorial: true` with the note *"The words are ours; the zero is the payload's."* That is the
   correct treatment and this row should have it.
2. **The wording over-claims.** `open` is derived, and this file prints its derivation two beats
   later at `b3.loop.status_note`: *"the absence of a `mainline.disposition` row for this check
   **that is neither retracted nor expired**."* A retracted disposition would still render *"never
   been answered"*, and *never answered* and *no live disposition* are different claims.

**Replace** *"DEMO-INC-0001 has never been answered for this permit."*
**with** **"DEMO-INC-0001 has no live disposition on this permit."**
**and set** `chip: derived` · `editorial: true`, with the note that the label is the column and the
sentence is ours.

It is the same claim the film makes correctly everywhere else, and it costs one word.

### 7.14 · REWORD — *"on the screen the whole time"* is contradicted by the same file

**Location:** `FALLBACKS.md` F-5 spoken line. Owner: **W6**.

*"You can't dismiss it"* is measured — `disclosure-line-is-not-dismissible` HELD with **0** controls
inside the strip. *"On the screen the whole time"* is contradicted by this file's own **F-12** and
by `CLICKS.md` D-2: the strip is not sticky and leaves frame at b3 and b6. Said to a judge who is
looking at devtools, it is a claim he can falsify by scrolling.

**Replace** *"That sentence is on the screen the whole time, and you can't dismiss it."*
**with** **"That sentence is on the screen with the panel, and it has no close button — you can't
dismiss it."**

If the sticky fix or W5's burned strap lands (§8.2), the original becomes true and may be restored.

### 7.15 · REWORD — the SEAL chip's *"eight"* is a number nobody has read

**Location:** `FALLBACKS.md` F-6 spoken line. Owner: **W6**.

The block's own **DO** says *"read the tally off the screen; do not carry the numbers from this page
onto camera"* — and then the scripted line carries one: *"and eight did not run at all."*
`r6-honesty`'s speculation item 1 marks this chip as the one thing **nobody opened**: the researcher
measured the ledger data, not the browser-computed verdict. W6's own W6-4 records the same gap.
**So the number is scripted, unread, and on a screen whose verdict is computed client-side.**

**Replace** *"Every check that ran passed — and eight did not run at all."*
**with** **"Every check that ran passed — and the ones that did not run are named on the screen,
each with its reason."**

That says the same thing, is stronger (it points at the screen instead of at a memory), and it
cannot be wrong on the day. The CLI figure — `16 checks · 9 passed · 0 failed · 7 not checked,
exit 2` — stays a different subject and is correctly kept separate in that block already.

---

## 8 · CONDITIONS ON THE SHOOT THAT ARE NOT SENTENCES

### 8.1 · **THE OPERATOR SURFACE IS NOT ON THE DEPLOYED ORIGIN** — measured twice today

> **SUPERSEDED 2026-08-16 — it landed. See §12.2, rows S2 and S3.** Everything below was true when
> it was measured and is kept unedited; the pre-flight it prescribes is **corrected** in S3,
> because grepping the script asset for `1 obligation outstanding` fails today on a screen that
> renders it.

This is not a claims defect and it is the largest fact in this wave. Two workers measured it
independently, by `GET` only:

* **`FALLBACKS.md` M2:** `GET /operator.html` and `GET /` both answer `200` with **4,655 bytes that
  are byte-identical**, both titled `MAINLINE console`.
* **`ONSCREEN-TEXT.yaml` F-1:** the served document's only script is `/assets/index-LoN3Sn_L.js`,
  which answers `200` gzipped (138,177 B on the wire, 490,539 B decoded) and contains **zero**
  occurrences of `CONTROL OF WORK`, `1 obligation outstanding`, `not carried by this deployment`,
  `cow-`, `hz-card` or `moc-`.

**Consequence.** The film scored in `CLICKS.md` and specified in `ONSCREEN-TEXT.yaml` has no pixels
on this origin today. Every `ui_label` row in W5's file — and therefore most of §6.1 — describes
*the film the repository can make*, not the film this origin can serve. **`FALLBACKS.md` F-9
governs the shoot until the operator package is deployed**, and its spoken line (B9) is cleared.

**The pre-flight check that catches it**, from F-1, and it is not a `200` check: confirm the served
document's `<title>` is the operator's **and** that the script asset contains the string
`1 obligation outstanding`, before pre-roll step 2. **A pre-flight that only checks for `200` would
pass and the shoot would begin against the console.**

### 8.2 · The watermark and the R-C disclosure line must be in frame

`CLICKS.md` D-1 and D-2 measure both strips as normal flow elements with no sticky positioning: the
watermark leaves frame after b0 and the disclosure strip at b3 and b6. **A3 says the watermark is
not optional and not decoration; R-C requires the disclosure from b2 onward.** Either the strips are
made sticky, or W5's `film.strap.disclosure_fallback` and burned watermark carry the same words —
and the disclosure strap must carry **no run-varying value**, which W5 has already specified.
Until one of those lands, the film violates A3 for roughly 108 of its 120 demo seconds.

### 8.3 · Re-derive on the day, and read the files on the day you say them

* `GET /v1/health` **and** `POST /v1/demo/gate-run` on the recording day **and** the submission day
  (A4.4). Beat 4 **skips silently** when the exposure receipt expires — the first three beats keep
  refusing, the screen looks correct, and the verdict quietly is not `PROVEN`.
* Every `elapsed_ms`, byte count, `run_id`, `refusal_id`, `disposition_id` and `clearance_digest` on
  screen is the **take's own**. The reference values in this sheet exist to be compared against,
  never captioned. `clearance_digest` is never a constant; `merged_commit` is stable and may be.
* **No elapsed figure is spoken or overlaid at all** — W5's finding F-3 (the panel prints one
  decimal above 1 ms while the payload carries more) makes that resolution load-bearing, not merely
  cautious.

### 8.4 · If the origin is down, the film is not made against a mock

Postponed, or filmed against the local node **and said to be local, on screen** — which the page's
own origin strip does by rendering `X-Mainline-Emulator`. A `40001` is pressed again on camera. A
staged refusal is a rules violation, not merely a dishonesty. `FALLBACKS.md` F-10's spoken line is
cleared for this, with the parity condition in row B10.

---

## 9 · THE SCANNER, VERBATIM, WITH EXIT CODES

### 9.1 · Why the exit-2 run is recorded even though it no longer fires

When this audit began, `ONSCREEN-TEXT.yaml` and `FALLBACKS.md` did not exist, and the scanner said
so rather than passing over them:

```
$ .venv/Scripts/python.exe scripts/demo/claim_hygiene.py --check \
    docs/demo/film/BEATS.yaml docs/demo/film/SPINE.md docs/demo/film/VO-DEMO.md \
    docs/demo/film/VO-CLOSE.md docs/demo/film/CLICKS.md \
    docs/demo/film/ONSCREEN-TEXT.yaml docs/demo/film/FALLBACKS.md
  FAIL  D:\CoackroachDBxAWS\mainline\docs\demo\film\ONSCREEN-TEXT.yaml does not exist — nothing was scanned
  FAIL  D:\CoackroachDBxAWS\mainline\docs\demo\film\FALLBACKS.md does not exist — nothing was scanned
exit=2
```

Both files have since landed and are audited in full. **The transcript is kept because it is the
tool refusing to let an absence read as a success**, and because a clearance sheet that quietly
replaced a red with a green would be modelling the exact behaviour it exists to prevent.

### 9.2 · The six delivered film files, scanned together — **exit 0**

```
$ .venv/Scripts/python.exe scripts/demo/claim_hygiene.py --check \
    docs/demo/film/BEATS.yaml docs/demo/film/SPINE.md docs/demo/film/VO-DEMO.md \
    docs/demo/film/VO-CLOSE.md docs/demo/film/CLICKS.md docs/demo/film/FALLBACKS.md
  scanned 6 file(s) against 21 rules
  claim hygiene OK
exit=0
```

**This is the command to re-run after the §7 edits.** It excludes this register by design (§9.5).

### 9.3 · All seven, including `ONSCREEN-TEXT.yaml` — **exit 0**

```
$ .venv/Scripts/python.exe scripts/demo/claim_hygiene.py --check \
    docs/demo/film/BEATS.yaml docs/demo/film/SPINE.md docs/demo/film/VO-DEMO.md \
    docs/demo/film/VO-CLOSE.md docs/demo/film/CLICKS.md docs/demo/film/FALLBACKS.md \
    docs/demo/film/ONSCREEN-TEXT.yaml
  scanned 7 file(s) against 21 rules
  claim hygiene OK
exit=0
```

**What that green means, exactly.** Twenty-one line-scoped regexes found no forbidden phrase in
seven files, several of which carry `prose-hygiene: register` and quote prohibitions on lines that
also carry a negation marker or sit inside a declared `forbidden_on_camera` block, both of which the
scanner's documented exemptions read as *stating* the rule. **It says nothing about A5, A8, A9, A13,
A14 or A4 — see §2 — and not one of the six REFUSE or thirteen REWORD rows in §7 was found by it.**
A green scan was never going to catch a sentence about a render.

### 9.4 · `--self-test` — the scanner can still go red — **exit 0**

```
$ .venv/Scripts/python.exe scripts/demo/claim_hygiene.py --self-test
  planted 4 violation families, scanner fired on 4
    RED   [MNC-01-rls-vs-rogue-admin] Row-level security protects the record from a rogue admin, end to end.
    RED   [MNC-15-upstream-merge] Our contribution was merged into upstream last week.
    RED   [HYG-bare-invariant] I07 in: See I07 for the invariant that governs this.
    RED   [HYG-sha-literal] 7c2e91a in: Reproduce it at commit 7c2e91a on the demo cluster.
  self-test OK — the scanner goes red on every planted family
exit=0
```

Four families planted, four fired. **A hygiene check that has never fired asserts nothing**, and
this one demonstrably can. Three other workers reached the same finding from the other direction and
recorded their own reds: `SPINE.md` and `BEATS.yaml` went red three times, `VO-CLOSE.md` five,
`ONSCREEN-TEXT.yaml` twice. **Every one was fixed in the file and never in the scanner.**

### 9.5 · What pasting §9.4 costs this file — measured, and my first draft was wrong about it

The brief requires the self-test result verbatim, and a verbatim transcript is checkable in a way a
summary is not. W3 measured at `VO-CLOSE.md:701-707` that a verbatim paste **re-commits the
offence**, and chose to elide. This sheet chose the opposite and therefore owes the measurement:

```
$ .venv/Scripts/python.exe scripts/demo/claim_hygiene.py --check docs/demo/film/CLAIMS-CLEARANCE.md
  scanned 1 file(s) against 21 rules
  ... 6 claim-hygiene violation(s)
exit=1
```

**Six findings on four lines — every one of them a line of the §9.4 transcript, and nothing else in
213 audited rows.** The four lines are `MNC-01-rls-vs-rogue-admin`, `MNC-15-upstream-merge`,
`HYG-bare-invariant` and `HYG-sha-literal`; two are reported twice because the rule's own excerpt
repeats its match. **The FAIL lines are named rather than pasted, and that is a measurement, not a
preference** — see §9.5.1.

### 9.5.1 · Three reds this sheet found in itself, and the recursion that made the third

W3 measured at `VO-CLOSE.md:701-707` that a verbatim paste of a hygiene failure **re-commits the
offence**. This file proved it twice more.

| # | what fired | why | fixed how |
|---|---|---|---|
| 1 | `MNC-14` and `MNC-06`, on this sheet's own §10 prose | Two prohibitions began *"No tamper-proof…"* and *"No rubber-stamp detection…"*. **Plain *no* is not one of the scanner's negation markers** — `NEGATION` at `claim_hygiene.py:73-84` lists `never`, `must not`, `nothing` and a dozen more, and not bare `no`. W3 hit the identical trap at `VO-CLOSE.md:720` | Both rewritten to begin with `never`, **in this file, never in the scanner** |
| 2 | `HYG-sha-literal` on `b0.el7.clause_facts`'s row in §6.1 | This sheet quoted a `commit_id` in a form containing a **seven-hex run** — in the row where it was clearing W5 for *avoiding* seven-hex. The rule is right and the sheet was wrong | The row now describes the digest's shape instead of printing a run of it |
| 3 | the paste itself, compounding from 6 findings to **21** | An earlier draft of this section pasted the failing FAIL lines verbatim. Those lines contain the fixture sentences, so the record of the red **became** a red — and the second-order paste tripled it | The FAIL lines are **named, not quoted**. Nothing is elided that a reader cannot reconstruct: the fixtures live in `SELF_TEST_FIXTURE` in `scripts/demo/claim_hygiene.py` and in `scripts/demo/fixtures/claim-hygiene-red.md`, and §9.4 quotes the self-test's own output in full |

**No rule was edited, no exemption marker was bolted onto a sentence that was not already a denial,
and no phrase was deleted to dodge a rule.** Findings 1 and 2 were real defects in this sheet, found
by the scanner this sheet is meant to be a control beyond — which is the argument for keeping both
controls rather than either.

**The consequence, stated plainly.** This register is outside every `TARGET_GLOBS` entry, so **no CI
lane is affected and the 988/987/0/0 baseline cannot move.** The command in §9.2 scans the film
without it. If `docs/demo/film/**` is ever added to a sweep list, **this path must be skipped and
the skip printed** — the same treatment `docs/submission/MUST-NOT-CLAIM.md` and
`docs/demo/research/r6-honesty.md` already get.

### 9.6 · The live origin, read-only, today

```
$ curl -sS "https://ihuuyvm4z6nfuktihnkey77fpy0eyrhj.lambda-url.ap-southeast-1.on.aws/v1/health"
{"applied_by":"scripts/deploy/cloud_chain.py","cluster_version":"CockroachDB CCL v26.2.5 (x86_64-pc-linux-gnu, built 2026/07/28 18:56:00, go1.25.5)","database":"mainline_demo","deploy_chain_applied":271,"deploy_chain_files":271,"migrations_applied":0,"ok":true,"schema_fingerprint":"ec9b1ce70a8df066e5763056c5ad9376800ef5df9362f7d0502b1dc7e7450339","seconds":0.0139,"server_date":"2026-08-15T14:02:54.523866Z"}
```

**One `GET`. No `POST`, no AWS API, no credential.** It confirms `ok: true`, `271/271` and the
`CCL v26.2.5` that C3 puts on screen — all re-derived today rather than inherited. It says nothing
about `POST /v1/demo/gate-run`, which **must be re-run on the recording day** (§8.3); this worker
did not run it, by instruction.

---

## 10 · WHAT THIS AUDIT DID NOT FIND, SAID OUT LOUD

A clearance sheet that lists only faults invites the reading that the rest was skimmed. These were
checked line by line across all seven files and are **clean**:

* **A5 tense.** Not one present-tense sentence about the retrieval, anywhere. Both voice-overs reason
  about it explicitly; `VO-CLOSE.md:200-211` even forbids computing a *"days before"* figure aloud;
  and `ONSCREEN-TEXT.yaml` `b3.loop.recalled` carries a `tense_rule` field of its own. **This is the
  family the whole hackathon theme runs through and the one with no scanner behind it, and four
  writers got it right independently.**
* **A8.** No sentence generalises the refusal to *"every refusal here is the database's"*. The one
  refusal that is the application's is never claimed for the database, and `b5.panel.message` carries
  the *say "the gate", never "the CHECK constraint"* rule in the string file itself.
* **A9.** No *"defence in depth, proven"*, and no claim in the untested direction.
* **A10.** The words *tamper-proof* and *split-view resistant* are never spoken, never captioned and
  never burned on a frame; both sit in `forbidden_on_camera` with their reasons; and no second
  witness is proposed to make a stronger sentence renderable.
* **A12.** Rubber-stamp detection is never claimed, identity verification is never claimed, and
  *"proves someone read it"* is never said. The limit is the film's closing line.
* **A7.** No vector search, no changefeed, no `AS OF SYSTEM TIME`, no multi-region — each refused
  **on the record with its measurement**, not merely omitted.
* **A1.** Residency is stated as a split, on screen, with the denial on the same line.
* **A2.** **No timing of the system is spoken anywhere in the film**, and after W5's F-3 no elapsed
  figure is overlaid either. The two clocks on screen are separately labelled with whose they are.
  `recall_run.latency_ms` is `null` in the live body, so there is not even a number to misuse.
* **A14.** `clearance_digest` is a slot with an explicit never-a-constant rule; the cluster version
  and chain count are read live and labelled as read; every digest renders at 8 + 4 or 64, never at
  7 or 40; no suite total, ratchet figure or headroom number appears in the film.
* **A4 / R-M.** No camera at `docs/submission/SUBMISSION.json`, in any file, and it is in
  `forbidden_on_camera` as well. No claim that CI asserts this URL. The only `PROVEN` on screen is
  the gate-run payload's own, for the run being filmed — never `acceptance.json`'s.
* **A13.** Propagation is never narrated, mentioned or filmed. The change request is told, never
  driven. The empty agent view is not dressed up.
* **R-E.** No `WO-88213`, no 2013, no `INC-2013-044`, **no year 2024 in any spoken or on-screen
  string** — every occurrence across the seven files sits inside a prohibition row or an evidence
  note, verified by grep.
* **R-F.** No injury, no person, no fatality. A severity, and the `SYNTHETIC —` prefixes stay
  uncropped by explicit convention (C4).
* **R-H.** The typed/chipped convention holds on every one of the four typed strings, and the PPE
  field renders empty and labelled rather than filled.
* **MNC-17.** The film does not open with the category. It opens with the form and promises the
  refusal, and the words *agentic memory* are not spoken in the 120 seconds at all.

---

## 11 · THE SIGNED VERDICT

**Rows audited: 213.**
**CLEAR: 194 · REWORD: 13 · REFUSE: 6.**

| source | § | rows | CLEAR | REWORD | REFUSE |
|---|---|---:|---:|---:|---:|
| `VO-DEMO.md` — every spoken sentence | §3 | 30 | 26 | 1 | 3 |
| `VO-CLOSE.md` — every spoken sentence | §4 | 11 | 10 | 1 | 0 |
| `FALLBACKS.md` — every spoken sentence | §5 | 18 | 16 | 2 | 0 |
| `ONSCREEN-TEXT.yaml` — every `id` | §6.1 | 142 | 135 | 7 | 0 |
| on-screen strings in the other five files | §6.2 | 12 | 7 | 2 | 3 |
| **total** | | **213** | **194** | **13** | **6** |

**These six numbers are added from the tables above and from nothing else.** An earlier draft of
this section carried a sixth source row of sixty rows that no table produced — a line written to
make a total close. It is deleted, the total is 213 rather than 273, and the fact that it happened
is recorded here rather than quietly corrected, because a clearance sheet that invented a number to
tidy its own arithmetic would have no standing to refuse anybody else's.

**Six REFUSE rows arise from two findings** (§7.1 in five locations, §7.3 in one).
**Thirteen REWORD rows arise from twelve findings** (§7.4–§7.15); four of the twelve land in two
files at once because `ONSCREEN-TEXT.yaml` mirrors `VO-CLOSE.md` verbatim, so **five edits by W3 and
W1, mirrored by W5, close nine of the thirteen rows.**

**The six REFUSE rows are one defect in four places** — `VO-DEMO.md:272-273`, `:279`, `:438-439`;
`BEATS.yaml:203-205` and `:334-337` — **plus one uncovered beat**, `VO-DEMO.md:244-248` spoken under
Path B. Exact replacement wording for all six is in §7.1 and §7.3.

> ## **THE FILM AS WRITTEN MAY NOT BE SHOT.**
>
> It becomes shootable when, and only when, all five conditions hold:
>
> 1. ~~**The operator surface is on the deployed origin**~~ — **DISCHARGED 2026-08-16, §12.2 row
>    S2.** `/operator.html` serves `Control of Work` and both screens render. **The check as
>    written here is defective and is corrected in §12.2 row S3:** the string
>    `1 obligation outstanding` is **not** in the operator entry asset — it renders from a
>    lazily-loaded chunk — so the check is made against the **rendered screen**, never against the
>    asset. `FALLBACKS.md` F-9 is superseded and kept live only as a regression fallback.
> 2. **The six REFUSE edits in §7.1 and §7.3 are made** by W2 and W1, using the exact replacement
>    wording there or wording this sheet has cleared.
> 3. **The twelve REWORD findings in §7.4–§7.15 are made, or each is declined in writing** in its
>    owner's file with its reason — the dissent mechanism plan §4 already provides. Five of them are
>    W3's and W1's, mirrored by W5, and closing those five closes nine of the thirteen rows.
> 4. **§8.2 is satisfied** — the watermark and the R-C disclosure line are in frame for the beats
>    that require them, by a sticky element or by W5's already-specified burned straps.
> 5. **§8.3's re-derivation is done on the recording day**, `POST /v1/demo/gate-run` included, and
>    every on-screen value is that run's own.
>
> **With those five discharged, and nothing else changed, the 194 CLEAR rows are cleared to shoot.**
> Beat 5 — the falsified counter, the `P0001`, and the system grading its own evidence down while it
> is the loudest thing on screen — is cleared without a single caveat, and it is the strongest thing
> in the cut.

**Signed:** W7 · claims clearance · audited against `r6-honesty.md` Part A (A1–A17) and
`MUST-NOT-CLAIM.md` (fourteen families), both read in full, 2026-08-15/16 (UTC).
**Nothing was cleared that this worker could not source, and no family was softened to let a
sentence pass.** One file written; nothing else in the tree touched; no `POST`, no AWS surface, no
commit.

---

# 12 · THE FILM RE-CUT WAVE — B9, B10, B11, k1, k2, k3, and the superseding rows

**Worker W6 · fallbacks and clearance · film re-cut wave · audited 2026-08-16 (UTC)**
**Binding plan:** `docs/demo/film-recut-plan.md`, §§4.3, 4.4, 6 and 8 — **R-4, R-5, R-7, R-9,
R-10** and the decision gate this wave numbers **R-11**.
**Registers re-read in full before a row was written:** `r6-honesty.md` Part A — **A3, A5, A13.5**
family by family — and `docs/submission/MUST-NOT-CLAIM.md`, **which retains precedence over
everything below.**
**What this section audits:** every new spoken sentence in the second use case and in the
compressed close, and every new on-screen string the plan requires. **§§1–11 are the
story-and-script wave's audit** and are unchanged except for two condition markers, both marked
rather than silently edited.

**A sibling exists and is not superseded.** `CLAIMS-CLEARANCE-CR.md` audits the three-block script
in `VO-DEMO-CR.md` and `CLICKS-CR.md` — 48 rows, 42 CLEAR, 5 REFUSE — and it is a good sheet. This
section does not repeat it and does not overrule it. **Where the two touch the same sentence, the
verdicts agree**, and where this section adds something the sibling could not have had, it is
because the measurements below were taken after it was written.

---

## 12.0 · THE VERDICT OF THIS SECTION, FIRST

> ## THE NEW MATERIAL IS CLEARABLE. IT IS NOT SHOOTABLE TODAY, AND THE REASON IS NOT A CLAIM.

**55 verdict rows · 22 CLEAR · 18 CLEAR-CONDITIONAL · 4 REWORD · 11 REFUSE**, plus **3 superseding
rows** in §12.2 which carry no verdict and are counted separately.

**The arithmetic, added from the tables below and from nothing else.** §12.3 is 28 rows —
`12 · 9 · 2 · 5`, of which §12.3.6's three are this worker's own amended fallback lines, audited
with the conflict declared. §12.4 is 4 rows, all REFUSE. §12.5 is 16 rows — `6 · 9 · 0 · 1`.
§12.9 is 7 rows — `4 · 0 · 2 · 1` — the re-read against the files W2, W3 and W4 landed **while this
section was being written**. `28 + 4 + 16 + 7 = 55`; `22 + 18 + 4 + 11 = 55`. **A first draft of
this line carried a larger total than its own tables produced**, which is the defect §11 confesses
to and refuses to repeat, so the sums are printed rather than asserted.

Three things decide the section, and the second was not in anybody's brief:

1. **Nothing in the drafted blocks claims more than its evidence carries**, on the condition that
   every value is re-derived from the filmed run. **Eleven REFUSE rows: ten of them pre-emptive,
   and one of them live.** The ten are four mirror-line variants R-7 orders filed, two sentences
   the frame would contradict, three compressions of the close that would cost content rather than
   delivery, and one on-screen value **no route that answers returns** — none of the ten is in any
   script, and they are here so nobody improvises one at 02:00. **The eleventh was in the delivered
   `VO-CLOSE.md`:** row D35, `k2`'s only spoken line, which compressed the Bedrock sentence to a
   bare denial and landed on a REFUSE row filed before it existed. Its replacement is two words
   shorter than the line it replaces and was already cleared. **`D35` is DISCHARGED as of
   2026-08-16 — §12.9.1 row C — and a twelfth REFUSE has been filed since this paragraph was
   written: N9 is superseded and the unscoped *"you can't use the clause"* is now barred in its own
   right, which makes five refused mirror variants rather than four.**
2. **`DEMO-INC-0001` is not on the change screen, and R-5 is therefore unsatisfied today.** Counted
   in the rendered DOM of the deployed origin: **zero occurrences.** R-5 is not a preference — its
   own words are that without both identifiers in the frame, use case two is a second refusal, the
   axis-one trade is a straight loss, and **the wave should be abandoned in favour of the NO-GO
   path.** That is condition 7 below and it is the sharpest thing in this section.
3. **The three change-request defeater prompts render nowhere**, so R-4's mitigation — *the way
   through is shown* — is unavailable. The authorisation lattice that **is** on that screen is read
   against the **permit's** check and says so in its own words. **A film that narrated it as the
   change request's would be a fabricated exhibit**, which is why row N14 is a REFUSE and
   `FALLBACKS.md` F-17 exists.

**And one thing that improved, measured rather than assumed:** condition 1 of §11 — *the film
scored in `CLICKS.md` has no pixels on this origin* — **is closed.** The console landed.

---

## 12.1 · WHAT THIS WORKER MEASURED, AND HOW

Everything in this section is a reading taken today against the live origin or against the tree.
`FALLBACKS.md` §1.1 carries the same table with the failure-mode consequences; this is the
clearance-relevant half.

| # | reading | result |
|---|---|---|
| **A** | `GET /operator.html` · `GET /` | `200 · 5,097 B · sha256 37454502…3f2d · <title>Control of Work</title>` against `200 · 4,749 B · sha256 9bd68bcd…1fbb · <title>MAINLINE console</title>`. **Two different documents.** |
| **B** | the rendered `#/permit` screen | `CONTROL OF WORK` · `DEMO-PTW-0001` · `dispositioned` · **`1 obligation outstanding`** · `Save draft` · `ISSUE ▸` · the `SYNTHETIC DEMONSTRATION — no real site, no real permit, no real person` watermark · `DEMO-INC-0001` ×2 · origin strip `X-Mainline-Emulator · absent`. **`Which isolation point` ×0** — the permit screen still issues no disposition read, so §7.3's Path B finding stands, now confirmed against the deployed origin. |
| **C** | the rendered `#/change` screen | Renders, and **does not break on the `404`.** `MANAGEMENT OF CHANGE · DEMO-MOC-0001` · `checks_materialised` · `counters.open_blocking 1` · four `cr_*` constraints with predicates *"read out of `pg_catalog` at request time"* · clause of record with printed label `7.3.2(b)` and its `SYNTHETIC —` prefix · both typed boxes empty and labelled · the disabled approve control with its reason · the `404` body, the seventeen declared routes and the two it needs struck through in place. |
| **D** | the same screen, counted | **`DEMO-INC-0001` ×0 · the three CR defeater prompts ×0 · `dec0de00-000d-…` ×0 · a severity for that obligation ×0.** |
| **E** | `GET`/`POST` on the change-request route family | `{cr_id}` → `200 · 3,295 B`; `…/checks`, `…/blocking-checks`, `…/merge` (`GET` and `POST`), `/v1/demo/cr-gate-run` (`POST`) → **`404`**, each body declaring **17 routes**. |
| **F** | `GET /v1/checks/dec0de00-000d-…/disposition` | `200 · 3,850 B`. Three prompts under one `vocab_sha256`; a five-row `blood_major` lattice; `virulence blood_major`. **No `severity`, no `clause_uuid`, no `event_id`, no origin.** |
| **G** | the seed, read for what the routes do not return | `demo_world.sql:1002-1015` writes that obligation with `clause_uuid dec0de00-0004-…`, `precursor_event_id dec0de00-0005-…`, `origin blame_ancestry`, and the literal `0, 'routine', 0` under its own comment *"projected over by `fn_check_project`"*. The live read returns `blood_major`. **The projection is provable for this obligation from a route that answers; the severity is not.** |

**Two `POST`s were issued by hand and both answered `404 no_route`.** They establish that a route
is **absent**, which is a claim the film makes; a `404` creates nothing and drives nothing.
**`POST /v1/demo/gate-run` was not run by hand** — §8.3's rule stands, and the day's verdict is the
founder's own run. No AWS surface was touched, no SSM parameter read or written, no credential
printed, nothing committed, and no ratchet, floor or expectation moved.

---

## 12.2 · THE SUPERSEDING ROWS — three, and none of them edits a research record

**R-8's ruling, adopted in terms.** `r6-honesty.md` is a **dated research record**; this file is the
film's **live clearance sheet**. A research record is not rewritten because the world moved — it is
cited and superseded, here, with the measurement that retires it. **`docs/demo/research/r6-honesty.md`
is not edited by this worker and must not be edited by anybody for this reason.**

| # | what is superseded | on what measurement | what survives, and this matters |
|---|---|---|---|
| **S1** | **`r6-honesty.md` A13.5's clause *"and no console surface"*, for the change request.** | Readings A, C and D. `/operator.html#/change` renders a complete Management-of-Change surface on the deployed origin: the record, the four `cr_*` predicates, the clause of record, the disabled approve control with its own reason, and the route table. **A13.5's premise that there are no pixels for this subject is retired.** | **A13.5's other half is untouched and is still live.** *"There is no `POST /v1/change-requests/{cr_id}/merge`"* was re-measured today: **`404`, and the `404` body declares the whole route table.** Its **MUST NOT SAY:** *"watch the same debt block the change request"* therefore **stays in force until the attempt endpoint lands and the R-11 gate passes.** A console surface is not a merge route, and retiring half a finding does not retire the half that still holds. Its **TRUE INSTEAD** — *told, never driven* — is unchanged and is `FALLBACKS.md` F-8's NO-GO form. |
| **S2** | **§11 condition 1, and the §THE VERDICT, FIRST finding 2 it came from: *"the film scored in `CLICKS.md` has no pixels on this origin today."*** | Readings A and B. `Control of Work` is served; the permit screen renders every string the film's b0–b8 depend on, including `1 obligation outstanding` and the watermark. | **Closed.** `FALLBACKS.md` F-9 is superseded and is **kept live as a regression fallback**: a deploy can go backwards, and the day's pre-flight decides, not this row. |
| **S3** | **§8.1's pre-flight instruction — *"confirm … that the script asset contains the string `1 obligation outstanding`."*** | The operator entry asset `operator-D24tzVGh.js` is `96,734 B` decoded and contains **zero** occurrences of that string; the **rendered** permit screen contains it. The string lives in a lazily-loaded chunk. | **The check is corrected, not dropped, and it is still not a `200` check.** Open `/operator.html#/permit` and read `1 obligation outstanding` **off the screen**. §8.1's instinct was right — a `200` proves nothing — and its implementation would now fail on a healthy deployment, which is the worse of the two errors: it would send a founder to F-9 on a night when F-9 does not apply. |

---

## 12.3 · EVERY NEW SPOKEN SENTENCE

`✓` CLEAR · `✓⃝` CLEAR-CONDITIONAL, the condition stated in the row and binding · `~` REWORD ·
`✗` REFUSE. **Two block-id schemes are in play and both are audited**, because `VO-DEMO.md` had not
landed its new blocks when this section was written: `film-recut-plan.md` §4 drafts **two** blocks
(`b9`, `b10`), `VO-DEMO-CR.md` writes **three** (`B9`, `B10`, `B11`). A row's verdict attaches to
the **sentence**, not to the id it is filed under, so it survives whichever shape the film lead
picks.

> **THE STANDING RULE OF THIS SECTION, AND IT IS THE ONE THAT MAKES IT A GATE.** A sentence that is
> not on this sheet is **not cleared**, and an uncleared sentence does not go on camera. That
> applies to a rewrite W2 or W3 makes after this section is written, to a substitute reached for at
> 02:00, and to any sentence "obviously equivalent" to a cleared one. **Equivalent is the word that
> drops a scope word.**

### 12.3.1 · The second use case — `b9` / `B9`

| # | line | verdict | family checked | authority, and the condition if there is one |
|---|---|---|---|---|
| N1 | *"Fine. Then don't use the clause — change it."* (plan §4.1) | ✓ | A5 · MNC-17 | It is the **judge's objection spoken in the judge's voice**, not an instruction and not a claim about the system. Nothing in it asserts a retrieval, a capability or an outcome. **Delivery condition, from the plan's own note:** it must not be delivered as a straw man. |
| N2 | *"Then change the rule instead."* (`VO-DEMO-CR.md` B9) | ✓ | as N1 | The same objection, four words shorter. Both forms are cleared; the film lead picks one. |
| N3 | *"Same paragraph. Same incident behind it."* | ✓⃝ | **A3 · R-5** | The whole axis-one claim, and it is **only true if the frame proves *same***. **CONDITION — and it fails today:** the clause is on the change screen (printed label `7.3.2(b)`, the clause uuid in its own read line) and **`DEMO-INC-0001` is not, in any form** (reading D). Until a route renders the precursor on that frame, this sentence is **uncleared for camera**. It is not reworded, because there is no wording that fixes a missing identifier — the frame is the evidence, and the frame is what has to change. |
| N4 | *"This request asks to edit it."* | ✓ | **A5 tense** | Present tense about **a row's standing content**, not about a lookup. `mainline.cr_clause` carries `relation = 'edits'` against the exact `(clause_uuid, commit_id)` pair (`demo_world.sql:984-989`), so *asks to edit* is a column, not a narration. The recall stays past tense everywhere. **MUST NOT SAY:** *"the rewritten clause"* — nothing has been rewritten; somebody has proposed to. |

### 12.3.2 · The second use case — `b10` / `B10`

| # | line | verdict | family checked | authority, and the condition if there is one |
|---|---|---|---|---|
| N5 | *"Refused. Same SQLSTATE, a different constraint —"* (plan §4.2) | ✓⃝ | A7 · A8 · **anti-fake** | Both halves are checkable in the frame: the permit's refusal named `gate_closed_when_issued`; this one names `cr_gate_closed_when_merged`, a different constraint on a different table with its own predicate, all four of which the change-request read already returns. **CONDITION:** the SQLSTATE is **read off the take**, never pre-captioned and never predicted from this page. A predicted SQLSTATE on an overlay is a staged exhibit even when the prediction is right. |
| N6 | *"— this one guards the edit."* (plan §4.2) | **~** | **A8 · precision** | **REWORD — §12.6.1.** The constraint's predicate is `((state != 'merged') OR (open_blocking = 0))`: what it refuses is the **merge of the change request**, not the act of editing. `VO-DEMO-CR.md`'s own register already forbids *"the database refused the edit"* for exactly this reason, and *"guards the edit"* is that sentence one word away. **Replace with** *"— this one guards the change."* — the wording the three-block script already uses, one syllable shorter, and true of the object the constraint names. |
| N7 | *"Refused. 23514 again — a different CHECK, guarding the change."* (`VO-DEMO-CR.md` B10) | ✓⃝ | A7 · A8 | Cleared as written, and it is the better of the two forms. **CONDITION as N5.** **The one-character trap, restated because it is the likeliest defect in this wave's on-screen text:** `cr_gate_closed_when_merged` is the **CHECK**; `cr_merge_gate` is the **trigger**; `mainline.fn_cr_merge_gate` is the trigger's **function**, and a `P0001` names the third and never the first. |
| N8 | *"…a different CHECK, `cr_gate_closed_when_merged`, guarding the change itself."* (B10 alternate, +2 s) | ✓⃝ | A7 | Cleared on the same terms. It spends about three words of mouth-time on one word of page, which is what the extra 2 s buys. |

### 12.3.3 · The mirror — `b10` tail / `B11`

| # | line | verdict | family checked | authority |
|---|---|---|---|---|
| N9 | *"You can't use the clause."* | **✗ SUPERSEDED** | A8 · A12 | **This row's ✓ is withdrawn, by the sheet that filed it, at D32.** It cleared the sentence for asserting nothing new — and that reading missed the film: **`b7` shows the permit ISSUED on that same clause thirty seconds later**, once its obligation was answered, so the unscoped form is contradicted by this film inside this film. **The cleared wording is D32's** — *"You can't **just** use the clause."* — and `just` gives the first half the scope discipline `quietly` gives the second. **MUST NOT SAY:** the unscoped form, in any block, in any fallback, as an ad-lib or as a cut-ladder shortening. **This is the fifth bar** and it stands beside §12.4's four. |
| N10 | **"You can't quietly edit it away either."** | ✓ | **R-7 · A5 · MNC-06's scope discipline** | **CLEARED, and cleared only with the adverb.** The scope word carries the entire truth of the sentence, exactly as `here` does in the rubber-stamp limit at row K9. The clause **can** be edited — by disposing of the obligation first — and *quietly* is what makes the sentence a statement about **unanswered** edits rather than about edits. **Every variant that drops it is REFUSED at §12.4, and that refusal is final.** |
| N11 | *"You can't use the clause. You can't edit it away either — not without answering the question first."* (substitute A) | **✗ RETIRED** | R-7 | Cleared, when filed, on the reading that the trailing clause carries the scope the dropped adverb was carrying — **and its FIRST half is the unscoped sentence N9 and D32 refuse**, which this row did not catch and which the trailing clause does not reach. **Retired on the claim.** It is also retired on the arithmetic it was conditioned on: 17 words in the old 8 s `B11` was **2.13 w/s**, and in the two-block shape it must sit behind the refusal sentence in one 12 s block — `9 + 17 = 26 w` = **2.17 w/s**, worse. **Both halves have to be right; this substitute never had a right first half.** Use N12. |
| N12 | *"Use it, or edit it. Not without answering the question first."* (substitute B) | ✓ | R-7 | Cleared, and **re-priced against the two-block shape and still fitting**: behind the refusal sentence in one 12 s `b10` it is `9 + 11 = 20 w` = **1.67 w/s**, identical to the line of record. Keeps both halves of the mirror and carries the scope in a clause rather than an adverb. **This is the substitute to reach for if an adverb has to go**, and it is the **only** surviving one — N11 is retired. **It is a substitute and never a co-primary:** taking it is announced before the take. |
| N13 | *"…not without answering the question first."* used **alone**, without the first half | **~** | R-7 · R-4 | **REWORD — §12.6.2.** On its own it answers a question the audience has not been asked; the mirror is a **pair**, and half a mirror is a claim about editing with no claim about using beside it. Keep both halves in whichever form is taken. |

### 12.3.4 · Two sentences the second use case must never end on

| # | line | verdict | family | authority |
|---|---|---|---|---|
| N14 | **MUST NOT SAY:** *"and there are its defeaters"* — said over the authorisation table on the change screen | **✗** | **A17.1 fabricated exhibit · MNC-19** | **REFUSE.** That table is read from `GET /v1/checks/dec0de00-0007-…/disposition` — **the permit's check** — and the screen prints its own sentence saying so: *"This change request's own obligation is not addressable from any declared route, so the read above was made against the check that is addressable. Nothing is claimed here about this change request's obligation."* The lattice is keyed by **virulence**, so the five rows are identical either way, **and that is exactly what makes the mistake invisible.** The software refuses the claim; the voice-over may not make it. |
| N15 | **MUST NOT SAY:** *"and there is no way through"* | **✗** | **R-4** | **REFUSE.** There are three, each demanding a citation, and showing them is the whole mitigation for use case two having no admission beat. A sentence contradicting the frame spends the mitigation to make a worse point. **TRUE INSTEAD:** *"answering one of those is the way through"* — sayable **only** when the three prompts are actually on screen, which today they are not (reading D). |

### 12.3.5 · The compressed close — `k1`, `k2`, `k3`

**The rule this sub-section runs under.** The close is compressed **from delivery, never from
content** (plan R-6). Every sentence in `k1`–`k3` is therefore either **a cleared C1–C4 sentence
carried forward to the character**, in which case its original row still governs, or **a new
sentence**, in which case it needs a row here. There is no third case, and *"a shorter way of
saying the same thing"* is the second case, not the first.

| # | line | verdict | family checked | authority, and the condition |
|---|---|---|---|---|
| N16 | **`k1` · the compression itself** — C1's 20 spoken words into ~10 | ✓⃝ | **A5 — the family with no scanner** | **CONDITION:** the surviving words are a **subset** of rows K1–K3, never a paraphrase of them. A5 is the one family in this film that a rewrite breaks silently: it has no scanner, and the difference between *"a retrieval"* and *"it retrieves"* is one letter and the whole claim. |
| N17 | **`k1` cleared minimum: *"And the refusal you just watched, re-deriving it."*** (K3 verbatim, 8 w · 1.33 w/s in 6 s) | ✓⃝ | **A5** | K3's clearance carries forward **under NO-GO, unchanged**. **CONDITION under GO — and this is a finding, not a formality:** in the GO cut this sentence lands **6 to 12 seconds after `b10`'s refusal**, and *the refusal you just watched* then most naturally names the change-request refusal — which is a `CHECK` on a counter and **does not re-derive anything**. The referent moved when the blocks were inserted. See §12.6.3. |
| N18 | **`k1` GO-cut replacement: *"And the second refusal, re-deriving it."*** (6 w · 1.00 w/s in 6 s) | ✓ | **A5 · A8** | Names the beat that actually re-derived: `b5`, `P0001`, *"the gate counted again, from the obligations themselves"* — the film's second refusal under either cut, since `b10` is the third. Past-referring, no present tense about the recall, and two words shorter than the sentence it replaces. |
| N19 | **`k1` · *"Stored, recalled — and the refusal you just watched."*** or any form that **speaks** the column words | **✗** | **A5 · W3's own delivery rule** | **REFUSE.** `VO-CLOSE.md` §2.3 rules that `STORE` / `RETRIEVE` / `ACT` are on screen in large type and are **not spoken**, *"because saying them while they are that size is the kind of narration that makes a judge stop reading."* Compression is exactly when a writer reaches for the three words that are already on the card. Every one of them is on screen in `k1`; none is in the mouth. |
| N20 | **`k2` · *"Every line says which."*** (4 w) | ✓⃝ | **A6** | The whole job of `k2`'s voice: tell a judge the list has a rule. **CONDITION:** all three labels must be legible on the card — `IN THIS REQUEST` / `IN THE APPLY` · `EARLIER` / `NOT IN THIS PATH` — because the sentence is a claim **about the card**. If the two columns will not fit legibly with their labels, `k2` takes 12 s from the 8 s bank; **it is never flattened.** **MUST NOT SHOW:** a single ungrouped stack list — *"a flat list would let `S3` borrow the credibility of `Lambda`, and `S3` was never in the request."* |
| N21 | **`k2` · *"Bedrock is exercised in this repository — not in this path."*** (10 w, K5 verbatim) | ✓ | **A6** | K5 carried forward to the character. `raw-haiku-converse.json` (a live `Converse` in `ap-southeast-2`), Titan v2 in `manifest.json`, and `r6-honesty.md:162` measuring no Bedrock call in the demo-API source. **Total spoken `k2` = 14 w in 10 s = 1.40 w/s**, inside the plan's 16-word budget. |
| N22 | **`k2` · any compression of N21 to a bare denial** — *"Bedrock — not in this path."* | **✗** | **A6** | **REFUSE.** The **positive** half is what makes the denial credible and it is the strongest twelve words in the block. A card that only denies reads as a card hiding something; a card that says *we ran it, and not here* reads as the only kind of list a judge can trust. This is a compression that costs content, which R-6 forbids in terms. |
| N23 | **`k3` · *"Nothing here separates a considered disposition from a rubber stamp."*** (10 w · 1.67 w/s in 6 s) | ✓ | **A12 · MNC-06** | K9 carried forward to the character, **with the scope word `here` intact**. `VO-CLOSE.md:474-484` prices every shorter form and rejects each; dropping `here` turns a statement about this deployment into a statement about safety records in general, which is not ours to make. |
| N24 | **`k3` · *"We measure deliberation and never threshold it."*** moved from the mouth to the screen | ✓ | A12 · MNC-16 | It is **already** on the screen, in the limit overlay's third line, verbatim. Moving it out of the mouth removes six spoken words and removes no content — the cleanest trade in the re-cut, and the only reason `k3` fits in 6 s. |
| N25 | **`k3` · the second and third sentences of the limit spoken at speed** | **✗** | **A12 · MNC-06** | **REFUSE.** *"It makes the question unavoidable, the record precise, the worst stamp non-representable"* is the **precise** form and a judge who pauses gets it exactly. Paraphrasing it at pace is how a concession turns back into a boast — `VO-CLOSE.md` §5.3's own words, and compression is when it would happen. |

### 12.3.6 · The amended `FALLBACKS.md` spoken lines — **audited, and the conflict declared**

**This worker wrote these three lines and this worker is clearing them, which is a conflict and is
stated rather than hidden.** §5 of this sheet audits `FALLBACKS.md`'s spoken lines because they are
said **on camera, live, at the moment a take is going wrong**, which is exactly when a register
gets broken; leaving the amended ones unaudited because their author is the auditor would be worse
than the conflict. **Every value below is a reading from §12.1, and any of the three may be struck
by the film lead without argument.**

| # | line | verdict | family | authority |
|---|---|---|---|---|
| B19 | **F-8 NO-GO, amended:** *"…Open blocking: one. The approve control is disabled, and it prints its own reason: one blocking obligation outstanding, and the constraint that holds it closed, with its predicate. There is no merge route for it yet — the screen says so and lists the routes that exist — so I'm telling you about it rather than driving it."* | ✓ | **A13.5 · R-I · A17.1** | Every clause is reading C: the count is `counters.open_blocking 1`; the control is constructed `disabled` with `aria-disabled="true"`; its reason string is measured verbatim; the constraint and predicate render beneath it; and the `404` with its seventeen declared routes is on the same screen. **This row supersedes the quoted form in §5 row B8**, which stays cleared and is now the shorter version of the same true sentence. **A first draft said *"the constraint that will refuse the merge"*; it was changed to *"holds it closed"* before this row was written**, because the first is a claim about a run that has not happened and the second is a claim about a predicate in the frame. |
| B20 | **F-8 GO form:** *"Refused. Twenty-three five one four again — a different CHECK, guarding the change. ·hold· You can't **just** use the clause. You can't **quietly** edit it away."* | ✓⃝ | **R-7 · A7 · A8** | The mirror with **both** scope words (N10 for `quietly`, D32 for `just`), the constraint claim a judge can check in the frame (N7), and the SQLSTATE read off the take. **CONDITION: the R-11 gate passes, all six.** Under NO-GO this line does not exist, because the refusal it narrates cannot be produced. **AMENDED 2026-08-16 — the row as first filed cleared an unscoped first half** (*"you can't use the clause"*, no scope word), which is **refused** at D32: `b7` shows the permit issued on that clause thirty seconds earlier, so the flat form is contradicted by the film it is spoken in. `FALLBACKS.md` F-8's GO form now carries the scoped pair and its `NEVER` list carries the fifth bar. **The clearance is on the amended line only; the wording this row used to quote is not cleared and never was.** |
| B21 | **F-17:** *"That authorisation table is read against the permit's obligation, not the change request's — the screen says so itself, right there. The change request's own obligation isn't reachable from any route this deployment declares, so nothing on this screen claims anything about it."* | ✓ | **A17.1 fabricated exhibit** | A paraphrase of the screen's own two sentences, in the founder's register, pointing at them. It is the answer to the one question that surface invites, and it is stronger than silence: **the software already refuses the claim, and saying so out loud is the disclosure-before-discovery habit §0 is built on.** |

---

## 12.4 · **THE FOUR REFUSED VARIANTS OF THE MIRROR — R-7's instruction, discharged**

`film-recut-plan.md` R-7 instructs this worker to *"file a REFUSE row against every variant that
drops the scope word."* **Here are all four, one row each, each with what makes it false rather than
merely strong.** `CLAIMS-CLEARANCE-CR.md` §4 files three of these against the three-block script and
its rows agree with these; filing them separately is deliberate — **a refusal that lives in one file
is a refusal somebody edits around.**

| # | ✗ **REFUSED** | why it is **false**, not merely strong |
|---|---|---|
| **X1** | **MUST NOT SAY:** *"The clause cannot be changed."* | It **can** be changed — by disposing of the obligation first. The mechanism is not hypothetical: three defeater prompts exist for this obligation under one `vocab_sha256`, live at `GET /v1/checks/dec0de00-000d-…/disposition`. Under R-4 they are meant to be in the same frame, which means the sentence would be **contradicted by the picture it is spoken over.** |
| **X2** | **MUST NOT SAY:** *"The database won't let anyone edit the rule."* | Adds **anyone**, which is a claim about every caller and every code path. A cluster admin drops a constraint and it succeeds — the film shows one doing it. What they cannot do is drop it unobserved. **Tamper-evident, never tamper-proofing**, and §3 answer two is the rehearsed form. |
| **X3** | **MUST NOT SAY:** *"The memory is immutable."* | Nothing here is immutable. `mainline.clause_blame_closure` is append-only and generation-versioned — *superseded, never deleted* — which is a claim about **how** it changes, not about it never changing. What the gate refuses is a **transition** while a counter and a re-derivation disagree; that is a condition on a change, not an absence of change. The word also invites a permanence claim the ledger's own `NOT VERIFIED` chip refuses. |
| **X4** | **MUST NOT SAY:** *"You can't edit it."* | The scope word is the whole sentence. Without it the claim is about editing; with it the claim is about editing **unanswered**, which is what the kernel enforces. This is the same failure `here` prevents in the rubber-stamp limit, and it is the one most likely to happen — because it is the shortest, and 02:00 reaches for the shortest. |
| **X5** — added 2026-08-16 | **MUST NOT SAY:** *"You can't use the clause."* with no scope word — **the mirror's FIRST half, which R-7's list did not cover and which two delivered files shipped** | **This one is refused for a reason the other four are not: the film disproves it on camera.** `b7`, thirty seconds before the mirror, shows the permit **ISSUED** on that same clause once its obligation was answered — so the flat sentence contradicts a frame the viewer has already watched, and a judge who noticed would conclude the narration does not describe the product. That is worse than any of X1–X4, which are merely over-claims. **TRUE INSTEAD:** *"You can't **just** use the clause"* (D32). `just` gives the first half the scope discipline `quietly` gives the second, and the pair then says one thing: **the question comes first, whichever way you come at the clause.** N9's ✓ is withdrawn; N11 is retired for carrying this half. |

> **TRUE INSTEAD, and only these two forms:** **"You can't just use the clause. You can't quietly
> edit it away."** — or, if an adverb reads oddly on the day, the pair as
> **"Use it, or edit it. Not without answering the question first."** (N12), which is the only
> surviving substitute.
>
> **This refusal is final.** Plan §9 states that W2 and W3 draft and **W6 clears**, and that this
> worker's REFUSE is not appealable to a rewrite. A sixth variant invented on the night is refused
> by the standing rule at the head of §12.3 and does not need a row of its own.
>
> **X5 is the row this section owes an admission for.** R-7 instructed four refusals and four were
> filed, correctly and pre-emptively — **against the half of the mirror that had an adverb.** The
> half without one was cleared at N9 on the reasoning that it *"asserts nothing new"*, and that
> reasoning walked past `b7`. **Two delivered files shipped the unscoped sentence as a PRIMARY
> line** before it was caught. **A refusal list is only as good as the half of the sentence it was
> pointed at**, and this one was pointed at one half.

**And two more, refused for a different reason**, endorsing `CLAIMS-CLEARANCE-CR.md` §4 rows R4 and
R5 without restating them: *"and there is no way through"* (N15 above) and *"the same debt blocks
both"* as an unqualified sentence — whether the two obligations are the **same row** is a claim
about the data model that this film does not put on screen. **The cleared claim is the one the frame
carries: same clause, same precursor, two gate families.**

---

## 12.5 · EVERY NEW ON-SCREEN STRING

**What this sub-section can and cannot be, said plainly.** `ONSCREEN-TEXT.yaml` had not landed its
new ids when this section was written, so these rows are filed against **the strings the plan
requires to be on screen**, each sourced against a reading taken today. **A new id that does not
match a row here is uncleared**, and the standing rule at the head of §12.3 governs it. Where a
string already has a row in §6.1, that row still governs and is pointed at rather than re-audited.

| # | string / frame element | verdict | family | authority, and the condition |
|---|---|---|---|---|
| O14 | `DEMO-MOC-0001` · `checks_materialised` · `counters.open_blocking 1` | ✓ | A14 | All three read live today (readings C, E). Composed from the response, never from a constant. |
| O15 | the four `cr_*` CHECK constraints with their predicates and the counters they read | ✓ | **A7 · A14** | Live in the change-request body and rendered on the screen under its own sentence: predicates are *"read out of `pg_catalog` at request time, not stored in this page."* That sentence is the reason the block is quotable. |
| O16 | `cr_gate_closed_when_merged` and `CHECK (((state != 'merged'::mainline.subject_state) OR (open_blocking = 0)))` as **the refusal's** constraint | ✓⃝ | **A8 · anti-fake** | **CONDITION:** on the refusal frame these come from the **response the take produced**, not from the constraint table beside it. Two renderers of one constraint already exist in this film and §6.1 rules that **neither may be edited into the other**; a third — a predicate captioned from this page — would be worse than both. |
| O17 | `23514` on the change-request refusal | ✓⃝ | **A17.1** | **CONDITION: never pre-captioned.** The value is right on the evidence available — the constraint is a `CHECK` — but *right* and *filmed* are different words, and an overlay written before the run is a staged exhibit whatever it says. Read it off the take. |
| O18 | the three defeater prompts, verbatim, under the legend *"Ways this obligation could be answered — each requires a citation"* | ✓⃝ | **A12 · R-4 · MNC-19** | The strings are live and exact (reading F), each a **question**, and never an escape hatch: the shipped vocabulary does not carry `not_applicable` and the three prompts do not offer one, which is the schema's own position. **CONDITION — unmet today:** they render nowhere on the deployed screen (reading D). Until they do, they are cleared as strings and unavailable as pixels. |
| O19 | `severity 4` for the change request's obligation | **✗** | **A14 · A17.1** | **REFUSE.** **No route that answers returns a severity for this obligation** (reading F). The seed writes `0, 'routine', 0` and the projection overwrites it, but the projected severity is not readable from the deployed API — only `virulence` is. Putting `4` on that frame would be a value carried from a seed file to a camera, which is the seed-reshaping act this repository has already reverted a worker for. **TRUE INSTEAD:** show `blood_major`, which **is** returned, and say nothing. |
| O20 | `blood_major` on the change-request frame | ✓ | **A3 · R-F** | A column value, live in the disposition body, and **it is the projection's own output** — the seed literal is `'routine'`. Renders only; **never spoken**, in this block or any other: an injury-shaped word said aloud edges toward inventing a casualty, which is the one thing this repository has refused at every turn. |
| O21 | the proposed wording, **typed by the founder on camera**, into the screen's own box, carrying no provenance chip | ✓ | **R-2 · R-H** | The screen's own field says *"Typed here, now. This deployment carries no proposed text… so there is nothing to load into this box and nothing was."* The typed/chipped convention makes a human's proposal distinguishable from a database claim in one look. **MUST NOT:** pre-fill it, echo it back as data, or let any frame imply the record carries it. |
| O22 | `DEMO-INC-0001` in the `b9`/`b10` frame (R-5) | ✓⃝ | **A3 · R-5** | The identifier itself is cleared — it is a real `external_ref`, it is already on the permit screen, and §6.1's rows govern its treatment. **CONDITION — unmet today:** it must arrive **rendered by a read**, from a route that returns it. **MUST NOT:** supply it by caption, overlay or burned strap on the change screen. An identifier the frame did not fetch is an editorial claim wearing a column's clothes, and it would be the exact defect R-5 exists to prevent, committed in the act of satisfying R-5. |
| O23 | the `404` body, the seventeen declared routes, and the two struck through in place | ✓ | **A13.5 · R-I** | **The deployment confirming its own absence**, now rendered on a real screen rather than described. §6.1's `b8b.change.route_table` row governs and is strengthened by reading C. |
| O24 | the disabled approve control and its reason: *"Cannot approve. 1 blocking obligation is outstanding on this change request."* + the constraint name and predicate + *"← from `mainline.change_request`"* | ✓ | **R-I · A14** | Measured in the rendered DOM and in the shipped bytes: the control is constructed `disabled` with `aria-disabled="true"`, and the count comes from the change-request read's own `counters.open_blocking`. The screen also states *"it is wired to nothing… not pointed at the permit's merge route: a button that refused a different record would be a prop."* **Under GO this string changes** — an enabled control renders something else, and that new string needs its own row before it is filmed. |
| O25 | the authorisation lattice on the change screen | ✓⃝ | **A17.1** | Cleared **only with the screen's own disclosure sentence in the same frame**, naming that the read was made against the addressable check and that nothing is claimed about the change request's obligation. **CONDITION:** W4 may not import this table into a `b10` overlay as *the change request's* lattice. See N14, which refuses the spoken form. |
| O26 | `k2`'s two-column card | ✓⃝ | **A6 · A7** | Inherited from rows `c2.overlay.aws` and `c3.overlay.cockroachdb` — **all four of their REWORDs are still open** (§7.7 SSM, §7.8 the S3 heading, §7.9 the recursive CTE, §7.10 `256/256`). **CONDITION:** merging two cards into one does **not** discharge them; it puts both sets of labels on one card, where a wrong label is harder to spot and stays on screen longer. Condition 3 of §11 covers them and is unchanged. |
| O27 | `k3`'s four-line criterion rail, arriving whole | ✓⃝ | **A4.2 · A14** | R-3's ruling — the rail lifts into the final block complete — is a **layout** change and clears on its own terms. **CONDITION:** rows `c2.rail.line2` and `c4.overlay.rail_all_four` are still REWORD (*"this endpoint cannot write"*, and `256/256`), and the compressed close puts both on screen for the film's last six seconds instead of its last eight. Fewer seconds is not a fix. |
| O28 | the per-request disclosure strap, if a second mutating request lands (plan §4.4) | ✓⃝ | **R-C** | **CONDITION:** each request's strap composes from **its own** payload and carries **its own** measured `persisted: false` — never a figure inherited from the first request, and never a burned constant. `film.strap.disclosure_fallback`'s rule that a burned strap carries **no run-varying value** is what makes the fallback safe, and it applies twice now rather than once. |
| O29 | the film's watermark and the R-C disclosure line, across two more blocks | ✓⃝ | **A3 · R-C** | **CONDITION:** §8.2 is unchanged and now covers 24 more seconds. Both strips are normal-flow elements; the burned straps must carry them through `b9`/`b10` as they do through `b3`/`b6`. |

---

## 12.6 · THE FINDINGS, WITH EXACT REPLACEMENT WORDING

### 12.6.1 · REWORD — *"this one guards the edit"* names the wrong object

**Location:** `film-recut-plan.md` §4.2's `b10` draft, and any file that inherits it. **Owner: W2.**

The predicate is `((state != 'merged'::mainline.subject_state) OR (open_blocking = 0))`. It is
evaluated on the change request's **state transition to `merged`**. The edit — the proposed new
wording — is not the object of the constraint and is not refused by it; what is refused is the
merge that would make the edit the clause of record. The three-block script already avoids this and
its own register forbids the neighbouring sentence *"the database refused the edit"* in terms.

**Replace** *"— this one guards the edit."*
**with** **"— this one guards the change."**

Same length in the mouth, true of the object the constraint names, and it keeps `b10` and the
mirror consistent: the mirror's claim is about **editing away quietly**, and the constraint's claim
is about **merging while an obligation is open**. Those are two different sentences and the film is
stronger for saying both.

### 12.6.2 · REWORD — half a mirror is not a mirror

**Location:** any cut that drops *"You can't **just** use the clause."* to save a second.
**Owner: W2.**

The mirror is a **pair**, and the pair is the wave's entire reason for existing: the film has
proved the first half on camera for two minutes, and the second half only lands as a *mirror* if
the first is said beside it. Alone, *"not without answering the question first"* answers a question
the audience has not been asked. **Both halves, in whichever form is taken** — and if the seconds
are not there, take substitute B, which carries both halves in 11 words.

**Amended 2026-08-16.** This location read *"You can't use the clause"* when it was written, which
is the unscoped form **X5** and **D32** refuse. **A cut that restores the sentence must restore the
scoped one** — dropping the beat's last four seconds is a cut, dropping its scope word is a
rewrite, and this section only ever governed the first.

### 12.6.3 · REWORD — `k1`'s referent moves when `b9`/`b10` are inserted

**Location:** `VO-CLOSE.md` C1 / `k1`. **Owner: W3**, and it applies **only under GO.**

*"And the refusal you just watched, re-deriving it"* was cleared at row K3 in a cut where the last
refusal a judge had watched was `b5`'s `P0001` — the beat that **counted again from the obligations
themselves**, which is what *re-deriving* names. Insert `b9`/`b10` and the last refusal watched
becomes the change-request `CHECK`, six to twelve seconds earlier, **which re-derives nothing.**
The sentence does not become false by being rewritten; it becomes false by **something being
inserted in front of it**, which is the kind of defect only a whole-film read catches.

**Replace, under GO only** — *"And the refusal you just watched, re-deriving it."*
**with** **"And the second refusal, re-deriving it."**

Six words for eight, names `b5` unambiguously under either cut, and stays past-referring.
**Under NO-GO, K3 is unchanged and its clearance stands.**

---

## 12.7 · THE FAMILIES RE-CHECKED, ONE BY ONE, FOR THE NEW MATERIAL

Re-read against `r6-honesty.md` Part A and `MUST-NOT-CLAIM.md`, **which retains precedence**.

* **A3 — the corpus and the incident.** The seeded world describes nobody, and the new blocks say
  no more than `b3` already did: **no date, no site, no job title, no injury**, spoken or written.
  `B0b` set the frame with *"years ago"* and named no year. The `SYNTHETIC —` prefixes stay
  uncropped on every string that carries one, including the clause of record on the change screen.
  **The two-incident trap is re-checked and is clean:** `DEMO-INC-0001` is dated 2019 on screen and
  the staged propagation payload reuses that uuid while titling it after a different year — **the
  two must never be in the same shot**, the propagation one is never narrated, and reading D
  confirms the change screen renders **neither**. The answer to *"did that happen?"* remains *"no,
  it is authored"*, and the standing sentence is the one to say: **every clause, procedure,
  incident, permit, operator, site and person in this demo was written for this repository — the
  mechanism is real and the inputs are authored.**
* **A5 — agentic memory, the family with no scanner.** Not one present-tense sentence about the
  retrieval survives into the new material. **MUST NOT SAY:** *"watch it remember"* · *"the system
  just retrieved the incident and blocked the change."* Row N4's present tense is about a **row's
  standing content**, which is not the retrieval; rows N16–N19 exist because compression is exactly
  when a noun becomes a verb; and N19 refuses the compression that speaks the column words off the
  card. **This is the family the whole hackathon theme runs through, a human is the only control,
  and it is the reason this section audits candidate wordings rather than waiting for final ones.**
* **A13.5 — the change request.** Superseded in one half and live in the other; §12.2 row S1 states
  exactly which. Its **MUST NOT SAY:** *"watch the same debt block the change request"* stays in
  force until the R-11 gate passes, because under NO-GO nothing is watched.
* **MUST-NOT-CLAIM, precedence.** Re-checked family by family against the new material, and each
  one is refused rather than merely omitted.
  Tamper-proofing is **never** claimed and split-view resistance is **never** claimed in any form
  (X2's row carries the true version).
  Rubber-stamp detection is **never** claimed — N23 keeps the scope word.
  `not_applicable` **is not** in the shipped vocabulary and **must not** be implied — N14 refuses
  the sentence that would imply one.
  Per-person measurement, time travel, corpus exhaustion and an upstream merge are **never**
  claimed, in any of the new material.
  And the film still **does not** open with the category.
  **Where MNC and any wording below disagree, MNC wins and the wording is wrong.**

---

## 12.8 · WHAT THIS SECTION ADDS TO §11's CONDITIONS

Condition 1 is **discharged** (§12.2 row S2). Conditions 2–5 are **unchanged and still open**.
**Four more are added, and they are conditions on `b9`/`b10` only** — under NO-GO none of them
applies, because the blocks do not exist.

> 6. **The R-11 gate passes on all six of its conditions**, run on the day, from
>    `FALLBACKS.md` §4.2. **Five of six fail today.** A partial pass is a NO-GO: R-10 makes `b9`
>    and `b10` atomic.
> 7. **R-5 is satisfied in the frame** — the shared clause **and** `DEMO-INC-0001`, both legible,
>    both rendered by a read, in the same frame as the change-request refusal. **`DEMO-INC-0001`
>    occurs zero times on that screen today.** Without it, plan R-5's own instruction is to abandon
>    the wave in favour of the NO-GO path, and this sheet holds that instruction to be binding.
> 8. **R-4 is satisfied in the frame** — the three change-request defeater prompts render beside
>    the refusal. They render nowhere today, and **the lattice that is on that screen is not
>    them** (N14, O25).
> 9. **All eleven REFUSE rows in §12.3–§12.5 and §12.9 are honoured, and the findings in §12.6 and
>    §12.9 are made or each is declined in writing** in its owner's file with its reason, under the
>    same dissent mechanism condition 3 provides. **The four in §12.4 are not declinable** — R-7
>    makes this worker's refusal final on that sentence, and plan §9 says so in terms.
>
> **Condition 9 is the only one of the four that binds the NO-GO film as well.** Rows D31–D37 are
> about the close and about `b10`'s wording; **D35 is in `VO-CLOSE.md` and the close is shot under
> either outcome**, so its replacement lands whatever the R-11 gate says.

> ## **THE NEW MATERIAL MAY NOT BE SHOT TODAY — AND THE FILM IS NOT WAITING ON IT.**
>
> The close compression is **not** conditional on any of this. It is a defect fix: the committed
> cut runs **180 s**, which `BEATS.yaml` itself calls a disqualified cut, and rows N16–N25 clear
> the compression that takes it off the ceiling. **Under NO-GO the film is 152 s · 2:32, legal in
> every particular, with every service and feature still named** — and `FALLBACKS.md` §4.3 carries
> that path in full.
>
> **NO-GO is a legitimate outcome and this sheet records it as one.** Nothing in this section is
> an argument for building a committing route, enabling a control in front of nothing, or granting
> `mainline_api` a write it does not hold.

---

## 12.9 · **WHAT THE OWNERS ACTUALLY DELIVERED — re-read against the landed files**

**§§12.3–12.8 were written while `VO-DEMO.md`, `VO-CLOSE.md` and `ONSCREEN-TEXT.yaml` still held
their pre-wave text, so their rows audit the plan's drafts and the sibling script.** The three
files landed at 15:09–15:21 while this section was being written. **This sub-section is the re-read
against what is actually in the tree**, and it is the reason the rows above were written against
candidate wordings rather than waited for: three of the six delivered lines differ from every
wording this sheet had in front of it, and one of them lands **exactly** on a REFUSE row that was
filed before it existed.

| # | delivered line, and where | verdict | authority |
|---|---|---|---|
| D31 | `VO-DEMO.md` B10: *"— a different constraint **guards edits**."* | **~** | **§12.6.1 applies, and now has a real location.** The predicate is evaluated on the transition to `merged`: what it refuses is the **merge**, not the act of editing. **Replace with** *"— a different constraint guards the change."* Same length in the mouth; true of the object the constraint names. The block's own `MUST NOT SAY` already forbids *"the database refused the edit"*, which is this phrase one word away. |
| D32 | `VO-DEMO.md` B10: *"You can't **just** use the clause."* | ✓ | **CLEARED, and it is better than the wording this sheet cleared at N9.** The bare *"You can't use the clause"* is absolute, and the film's own `b7` disproves it on camera — the permit **is** admitted once the obligation is answered. **`just` gives the first half the same scope discipline `quietly` gives the second**, so the mirror is now scoped on both sides. An improvement found by its author, recorded as one. |
| D33 | `VO-DEMO.md` B10: *"You can't **quietly** edit it away."* (without *"either"*) | ✓ | **The adverb survives, which is the only thing §12.4 refuses over.** Dropping *either* costs the explicit tie to the previous sentence; the parallel construction carries it, and D32's *just* now carries it harder. Cleared. **All four §12.4 refusals stand against any future edit of this line.** |
| D34 | `VO-CLOSE.md` `k1`: *"The incident. The retrieval. Ten seconds later, the obligation. Refused."* | ✓ | **A5 clean, and it moots §12.6.3.** Four fragments landing on three columns; *incident* and *retrieval* are **nouns**, so nothing is narrated as happening now; the year is dropped, which A3 can only welcome; and *"Refused."* names what the judge watched under either cut, so the referent problem §12.6.3 raised **cannot arise in this wording.** §12.6.3 is therefore **moot as delivered** and is kept for the case where anybody restores the longer form. |
| D35 | `VO-CLOSE.md` `k2`: *"Everything here is either in that request or in the apply. **Bedrock — not in this path.**"* | **✗ → DISCHARGED 2026-08-16** | **DISCHARGED: `VO-CLOSE.md` §3.4 now reads the replacement below, verbatim and unamended, and §3.4.0 records the finding in the file that carries the line. §12.9.1 row C is the discharge record. The REFUSE stands against the wording quoted in this row, which is no longer in the tree.** · **REFUSE — row N22, filed before this line existed, fires on it exactly.** The Bedrock sentence has been compressed to a **bare denial**: *"is exercised in this repository"* is gone, and that positive half is what makes the denial credible and is the strongest twelve words in the block. A card that only denies reads as a card hiding something. **And the first sentence is §7.6's open REWORD, undischarged** — the overlay carries a third group, and §7.7/§7.8 move two more rows out of the first two, so *"either… or…"* is false about three of the card's rows rather than one. **Replacement, 14 words, inside the 16-word budget:** **"Every line says which. Bedrock is exercised in this repository — not in this path."** That is N20 + N21, both already cleared, and it costs two words fewer than the line it replaces. |
| D36 | `VO-CLOSE.md` `k3`: *"Nothing here separates a considered disposition from a rubber stamp."* | ✓ | **Row N23 exactly, with the scope word `here` intact**, and N24 confirmed: *"We measure deliberation and never threshold it"* has moved to the screen in its sanctioned form. Six spoken words saved, zero content lost. |
| D37 | `ONSCREEN-TEXT.yaml` `b10.lattice.rows` | **~** | **REWORD — one gap in an otherwise exemplary file.** Its `source` reads `GET /v1/checks/{check_id}/disposition`, unbound. **On the deployed screen today that read is made against `dec0de00-0007-…`, the PERMIT's check**, because the change request's own obligation is not addressable — and the deployment prints its own sentence saying so. The five rows are **identical either way**, since the lattice is keyed by virulence, which is exactly what makes the substitution invisible. **Add the deployed screen's own disclosure to this id as a required companion string**, in the form O25 clears and N14 refuses the spoken version of. |

**And the part that is a credit rather than a finding.** ``ONSCREEN-TEXT.yaml``'s 46 new ids reach
four of this section's conclusions independently and in some places further:
`b10.check.row` marks `severity` as a **slot** and names the trap of borrowing the event's
`severity_gate` for it — which is O19's REFUSE, arrived at from the other side;
`b10.obligation.absence_note` records that its own presence and R-5 are **mutually exclusive**;
`b10.do_not_render` records the unselected defeater as an on-screen **absence**; and
`b10.defeater.different_vocabulary` carries `must_not_claim`: **the vocabulary is act-specific, and
it was not generated in this request.** **Four writers reaching the same rulings from four
directions is the strongest evidence in this file that the rulings are right.**

---

## 12.9.1 · **WHAT WAS DISCHARGED, 2026-08-16 — three film defects, and what stayed open**

**Filed by the worker who made the edits, which is the same conflict §12.3.6 declares and it is
declared again here rather than assumed forgiven.** Every row below names the file that changed and
the row that already cleared the wording, so a later reader can check the discharge against a
clearance rather than against this paragraph.

| # | defect | discharged how | authority for the new wording |
|---|---|---|---|
| **A** | **The block collision.** `BEATS.yaml`, `VO-DEMO.md`, `CLICKS.md`, `ONSCREEN-TEXT.yaml`, `FALLBACKS.md` and `SPINE.md` encoded **two** blocks (`b9` 12 s + `b10` 12 s); `VO-DEMO-CR.md` and `CLICKS-CR.md` encoded **three** (`B9` 10 + `B10` 6 + `B11` 8). Both totalled 24 s, so `total_s: 172` held either way and no arithmetic caught it. | **RULED: two blocks. `B11` does not exist.** `VO-DEMO-CR.md` §0.3 carries the ruling and its three reasons; the deciding one is `CLICKS.md`'s **measured** read chain (≈ 3.5 s warm / ≈ 6 s cold) plus its measurement that the proposed-wording box is re-created empty on mount, which makes a 10 s `B9` unshootable. The `-CR` files were reconciled **and made subordinate** — `VO-DEMO.md` §1 owns the words, `CLICKS.md` §5 owns the cursors — so the same pair cannot drift again. | this sheet's own N2/N5–N8 for the `-CR` wordings that survive as alternates; `BEATS.yaml` for every duration |
| **B** | **A barred claim in a primary line.** `VO-DEMO-CR.md` `B11`'s primary opened *"You can't use the clause."*, unscoped — the sentence `b7` disproves on camera thirty seconds earlier. `CLICKS-CR.md` `B11` and `FALLBACKS.md` F-8's GO form carried the same half. | **REPLACED** with `VO-DEMO.md` `B10`'s scoped pair — *"You can't **just** use the clause. You can't **quietly** edit it away."* — in all three files. **N9 is superseded, N11 is retired, N12 survives re-priced**, and the **fifth bar** is added to `VO-DEMO-CR.md`'s R-7 list, to `FALLBACKS.md` F-8's `NEVER`, and to `CLICKS-CR.md` §6 as a stop-the-take condition. | **D32** (`just`) and **D33** / **N10** (`quietly`), both already ✓ on this sheet |
| **C** | **`D35`, undischarged.** `VO-CLOSE.md` `k2` had been compressed to a bare denial — *"Bedrock — not in this path"* — losing *"is exercised in this repository"*, the positive half that makes the denial credible and that the card still carries in full. | **REPLACED** with **"Every line says which. Bedrock is exercised in this repository — not in this path."** — adopted **verbatim** from D35's supplied wording, with no amendment, because a variant invented to hit a word count is an uncleared variant. `VO-CLOSE.md` §3.4.0 is the finding; §0.1, §0.2, §0.4 and §3.5 carry the corrected arithmetic. | **N20** + **N21**, both already ✓, and `r6-honesty.md` **A6**'s `TRUE INSTEAD`, which carries both halves in one clause |

**The one place `D35`'s replacement costs something, stated rather than absorbed.** It is **14
words against a 16-word budget**, so the close delivers **34** rather than 36 and reads at
**1.55 w/s** rather than 1.64. `BEATS.yaml`'s `vo_word_budget: 16` and `close_words: 36` are
**unchanged and still correct** — a budget is a ceiling and under-running one is free. The direction
of the rate is the safe one: a close compressed in *content* would read **faster**, and this one
reads slower than it did and slower than the 50 s cut it replaces.

**Three things were NOT discharged, and each is left as a written open item rather than closed
quietly.**

1. **`D31` — *"a different constraint guards edits"*.** Still **`~ REWORD`**, and **now carrying a
   collision it did not have when it was filed — see §12.9.2.** The supplied replacement *"guards
   the change"* is one word longer on the page, and `VO-DEMO.md` §2 has already priced `b10` at 21
   words running **1.13 s against 0.95 s of slack** — so taking it re-prices the mirror's hold.
   **Owner: W2, with W1 for the seconds.** `VO-DEMO-CR.md`'s own alternate already uses the
   corrected object and is cleared at N7/N8, so the two files converge the moment it lands. **The
   wording was not propagated into a second file in the meantime**, which would have doubled the
   row rather than discharged it. **D31 IS NOT DISCHARGED BY §12.9.2 AND IS NOT DISCHARGED HERE.**
2. **Where the press lands.** ~~`CLICKS.md` §5 puts **Click 6 at `2:17`**, inside `b10`;
   `CLICKS-CR.md` put it inside `b9`. `b10`'s first spoken word is *"Refused."* at `2:16`, so
   under the first placement the value is spoken before it is on screen — which **R-K forbids** —
   and **R-9** requires each mutating request to be narrated while it is in flight. Both fixes
   spend something and both are priced in `VO-DEMO-CR.md` §1. **Owner: the film lead.** **This is
   not a documentation defect and it is not fixed by choosing one quietly.**~~
   **CLOSED 2026-08-16 by `docs/demo/shoot-docs-plan.md` `R-SD4`, which is the film lead's
   ruling this row asked for. §12.9.2 is the closure record, the collision it creates with
   `D31`, and what the ruling costs.**
3. **`cut_ladder` rank 1 is not executable as written.** It buys 4 s by arriving on the proposed
   wording *"already composed"*, and the same `CLICKS.md` measurement that decided defect A says
   the box is empty when the screen mounts. The step can buy a **shorter typed string**, never a
   pre-composed one. Recorded in `BEATS.yaml` and in `VO-DEMO-CR.md` §5. **Owner: W1.
   Re-ordering a pre-committed ladder is a rehearsal decision, never a documentation edit.**

**No assertion was weakened, no floor was lowered, and no register row was softened to let a
sentence through.** Every replacement above is a wording this sheet had **already** cleared before
the defect was found; the work was putting cleared wordings where uncleared ones had been.

---

## 12.9.2 · **OPEN ITEM 2 IS CLOSED — the press lands at `2:14.0`, and it collides with `D31`**

**Added 2026-08-16 by W6 of the shoot-documents wave.** Authority:
[`../shoot-docs-plan.md`](../shoot-docs-plan.md) **`R-SD4`**, `R-SD4a`, `R-SD4b`, and
[`../../submission/AUDIT.md`](../../submission/AUDIT.md). **This sub-section closes §12.9.1's open
item 2 and closes nothing else. `D31` stays open and §12.9.1 item 1 says so on its own line.**

### The ruling, quoted rather than paraphrased

> **Click 6 — `Approve change` — is at `2:14.0`, which is `+10.0` into `b9`. The request is in
> flight `2:14.0 → 2:15.5`. The refusal paints at `2:15.5`. `B10` opens at `2:16.0` on a refusal
> that has been on screen for half a second.**

**Neither sheet's number survived and the placement of one did.** `CLICKS.md` §5's `2:17` is
**struck**: it puts the SQLSTATE on screen after *"Refused."* is spoken at `2:16`, which is exactly
what **R-K** forbids and what this row was filed over. `CLICKS-CR.md`'s literal **`+7.4` is struck
too** — it was scored against the retired 10 s `B9`, and `+7.4` inside the 12 s block is `2:11.4`,
in the middle of the typing. What is upheld is `CLICKS-CR.md`'s *intent*: the press sits under
*"This request asks to edit it."*, inside `b9`, so the mutating request is narrated while it is in
flight (**R-9**) and the value is on screen before it is spoken (**R-K**).

### Why this closes a CLAIMS row and not merely a choreography row

**Because the defect this row named was a claims defect wearing a stopwatch.** Under `2:17` the
founder says *"Refused."* over a frame that does not yet carry a refusal, and then names `23514`
over a frame that has carried it for less than a second — **a spoken value that is not on screen
when it is spoken is an unsourced value**, which is the one thing every row of this sheet exists to
stop. Under `2:14.0` the refusal has been composed for `0.5 s` when the first word lands. **R-K is
satisfied with half a second to spare, and it is satisfied by arithmetic rather than by delivery.**

**It also restores the film's own grammar, and that is a claims argument as well as a craft one.**
`b1` already choreographs the film's *first* mutating press this way — Click 2 at `0:22.5`, `+2.5`
into a 10 s attempt beat, with the refusal beat `B2` opening at `0:30` on an answer already
painted. **A judge watches the same act twice; the second one being cut differently is what makes
it read as edited.**

### What it costs, priced here rather than absorbed

| what moves | from | to | who pays |
|---|---|---|---|
| the typing window in `b9` | `5.0 s` (`2:11 – 2:16`) | **`2.5 s`** (`2:11.0 – 2:13.5`) | the proposed-wording string, which must be one a human types legibly in 2.5 s |
| `b9`'s 1.1 s of "settle" slack | *the typed proposal settling* | *the answer landing* | nobody — it is re-purposed, not spent twice |
| spoken words, word budgets, beat durations, `total_s` | — | — | **nothing.** `R-SD5`: `172 s`, hard stop `174 s`, ceiling `180 s`, and no `vo_word_budget` moves |

**The string is `CLICKS.md` §5 `B9`'s to state, with its character count** (`R-SD4`), and **`R-2`
is discharged by the *act* of typing into the console's own input with no provenance chip** — it
has never required a character count, so a shorter honest proposal discharges it identically.
**If 0.5 s more is needed it comes from the app-bar travel (`1.5 s → 1.0 s`), never from the scroll
dwell — which is R-5's evidence — and never from the read chain, which is incompressible.**

### **THE COLLISION, WHICH IS THE PART A LATER READER MUST NOT LOSE**

> ## `R-SD4a`'s FLOORED `0.4 s` AND `D31` WANT THE SAME `0.4 s`, AND IT CANNOT BE SPENT TWICE.

`R-SD4a` allows `b10`'s first word to slip by **at most `0.4 s`** — `b10`'s entire measured free
slack — if rehearsal shows that no honest proposal string types legibly in 2.5 s even after the
string is shortened and the 0.5 s of travel is reclaimed. That would put Click 6 at `2:14.4` and
the typing at 2.9 s.

**`D31` wants the same `0.4 s`.** §12.9.1 item 1 prices the `~ REWORD` of *"guards **edits**"* to
*"guards the change"* at **21 words running `1.13 s` against `0.95 s` of slack** — an overrun of
`1.13 − 0.95 = 0.18 s`, and `b10`'s free slack is the only place to pay it from. **`VO-DEMO.md`
reaches the same collision from the other side, in its own words, at `:630`** — *"that 0.4 s is the
same 0.4 s `D31` would have to be paid out of … it cannot be spent twice"* — which is two workers
finding one trade independently and is the reason it is recorded rather than resolved.
`b10`'s 1.5 s of slack is
**0.6 s mirror hold + 0.5 s spoken `SQLSTATE` + 0.4 s free**, and both the hold and the `SQLSTATE`
are protected (`SPINE.md` §4: the hold is a scripted element, not a pause an editor may tighten).

| claimant | what it asks for | what it buys | what it forecloses |
|---|---|---|---|
| **`R-SD4a`** | up to `0.4 s` of `b10`'s free slack | 0.4 s more typing, if no honest string fits 2.5 s | **`D31` — the wording stays *"guards edits"*, which this sheet has recorded as **not** true of the object the constraint names** |
| **`D31`** | `0.18 s` of the same slack | *"guards the change"* — true of the object the predicate is evaluated on | the floored press fallback; the string must then fit 2.5 s or the press moves nowhere |

**THE FILM LEAD SPENDS IT ON ONE OR THE OTHER, STATES WHICH, AND DOES NOT DISCOVER THE COLLISION
ON THE DAY.** This sheet does not choose: `D31` is a wording verdict and the press is a
choreography ruling, and **a clearance sheet that quietly resolved a rehearsal trade by picking the
half it owns would be doing the small version of the thing it exists to prevent.**

**`D31` IS THEREFORE LEFT OPEN, WITH ITS COLLISION RECORDED AND ITS `~` UNCHANGED.** It is not
discharged, not downgraded, and not re-priced. Its owner is unchanged — **W2, with W1 for the
seconds** — and the film lead now owns the `0.4 s` that decides whether W2 can spend it.

### `R-SD4b` — the whole of this sub-section is conditional, and it says so on its own line

**`b9` and `b10` are NO-GO on the deployed origin as measured 2026-08-16.** On the no-go path
**there is no Click 6 at all**: the ledger is five clicks and one text entry, `FALLBACKS.md` F-11
reverts to exactly one mutating request, `b8` returns to 10 s and the film is 152 s. **Every
restatement of `R-SD4` in this repository is conditional on `FALLBACKS.md` §4.2's R-11 decision
gate**, and this one is no exception. A row written as unconditional would be a second document
describing a film that does not exist.

---

## 12.10 · THE SCANNER, AFTER THIS SECTION

`docs/demo/film/` is outside every `TARGET_GLOBS` entry, so this scan is invoked by hand and its
result is pasted rather than assumed. **This file's exit code was already `1` before this section
existed** — six findings on four lines, every one of them inside §9.4's pasted self-test transcript,
which §9.5 measures and explains. **The number to watch is therefore whether this section adds a
seventh.**

```
$ .venv/Scripts/python.exe scripts/demo/claim_hygiene.py --check docs/demo/film/CLAIMS-CLEARANCE.md
  scanned 1 file(s) against 21 rules
  ... 6 claim-hygiene violation(s)
exit=1
```

**Six, unchanged, and all four lines are still the transcript's.** Not one finding lands in §12
**in the version you are reading — and four did in the version before it.** Recorded rather than
quietly repaired, because §9.5.1 records the same class of defect and a sheet that hid its own
would have no standing to refuse anybody else's:

| # | what fired, in the first draft of §12 | why | fixed how |
|---|---|---|---|
| 4 | `MNC-14-split-view` and `MNC-06-rubber-stamp` on §12.7's MUST-NOT-CLAIM bullet | The bullet listed the families as *"no tamper-proofing and no split-view resistance… no rubber-stamp detection"*. **Plain *no* is still not one of the scanner's negation markers** — the identical trap §9.5.1 finding 1 records, and the third file in this repository to hit it | The bullet now says each family is **never** claimed, one clause per line, **in this file and never in the scanner** |
| 5 | `MNC-19-not-applicable`, twice — on §12.7's bullet and on row O18 | Both said *"contains no `not_applicable`"*, and both were **clearing** the vocabulary for **not** carrying one. The rule was right and the rows were wrong | Rewritten to *"is not in the shipped vocabulary"* and *"the shipped vocabulary does not carry"* — the same claim, with a marker the scanner reads |

**No rule was edited, no exemption marker was bolted onto a sentence that was not already a denial,
and no phrase was deleted to dodge a rule.** Every prohibition quoted above sits on a line carrying
its own explicit negation marker, because the scanner's exemption is **line-scoped** — a `never`
that wraps away from the phrase it governs stops exempting it. The command that scans the film
**without** this register is §9.2's and is the one to run after the §7 and §12.6 edits.

**One observation about the tool itself, for whoever runs it on the day.** On a Windows console at
the default code page, `claim_hygiene.py` **raises `UnicodeEncodeError` while printing a finding**
whose excerpt contains a character outside `cp1252` — the findings before it print, the traceback
lands after them, and the exit code is still `1`. It is a printing failure, never a scanning
failure, and `PYTHONIOENCODING=utf-8` in front of the command shows the full list. **A green sweep
never hits it, because there is nothing to print.** Recorded here rather than filed as a fix: this
worker owns neither the script nor the right to change a checker.

```
$ .venv/Scripts/python.exe scripts/demo/claim_hygiene.py --check docs/demo/film/FALLBACKS.md
  scanned 1 file(s) against 21 rules
  claim hygiene OK
exit=0
```

The sibling file this worker owns, re-scanned after its own amendment. And §9.2's command, re-run
over the six delivered film files with the amended `FALLBACKS.md` in the set:

```
$ .venv/Scripts/python.exe scripts/demo/claim_hygiene.py --check \
    docs/demo/film/BEATS.yaml docs/demo/film/SPINE.md docs/demo/film/VO-DEMO.md \
    docs/demo/film/VO-CLOSE.md docs/demo/film/CLICKS.md docs/demo/film/FALLBACKS.md
  scanned 6 file(s) against 21 rules
  claim hygiene OK
exit=0
```

**`--self-test` was re-run and is unchanged: `planted 4 violation families, scanner fired on 4`,
exit 0.** A hygiene check that has never fired asserts nothing.

**And the number that must not move, said plainly.** The two files this worker wrote are markdown
under `docs/demo/film/`. Re-verified this session rather than inherited:
`grep -rln "demo/film\|FALLBACKS\|CLAIMS-CLEARANCE" tests/ scripts/ .github/ …/demo-api/tests`
returns **nothing**, no workflow filters on `docs/**`, and `docs/demo/film/**` is outside every
`TARGET_GLOBS` entry. **The 998 / 997 / 0 / 0 baseline cannot move for a markdown file nothing
collects**, so the suite was not run — and **if that verification is ever wrong, the replacement
number comes from a `--junitxml` root element and from nothing else, never from a terminal tail.**
No scratch database was created either: an empty `w_W6` would have been a write with no reader.

---

**Signed:** W6 · fallbacks and clearance · film re-cut wave · 2026-08-16 (UTC), audited against
`r6-honesty.md` Part A — A3, A5 and A13.5 family by family — and `docs/submission/MUST-NOT-CLAIM.md`,
which retains precedence.
**Two files written — `FALLBACKS.md` and this one — and nothing else in the tree touched.**
`docs/demo/research/r6-honesty.md` was **read and not edited**: a dated research record is cited and
superseded, never rewritten. No ratchet, floor, ceiling, assertion or expectation was moved. No
`terraform`, no AWS surface, no SSM parameter, no credential, no commit.
**Nothing was cleared that this worker could not source, no family was softened to let a sentence
through, and the four refusals in §12.4 are final.**

---

# 13 · THE CLOSE-CARD WAVE — `k3.overlay.tools`, the eligibility panel

**Worker W6** · clearance, hygiene and whole-wave verification · close-card wave · **2026-08-16
(UTC)** · authority read first: [`../../submission/AUDIT.md`](../../submission/AUDIT.md) **FIX 1**
and [`../close-card-plan.md`](../close-card-plan.md) §2 (R-C1…R-C10) and §4.

**Why this section exists.** The audit's §5 found that the film's 22 s close named **seven AWS
services and zero of the four contest CockroachDB tools**, on a CockroachDB hackathon — *"the
largest unforced loss in the submission."* The wave's remedy is one new overlay string,
`k3.overlay.tools`, carrying seven lines. **Every one of those lines is a claim a judge reads off
a paused frame, so every one of them gets a row here.**

---

## 13.0 · THE VERDICT OF THIS SECTION, FIRST

> ## THE PANEL CLEARS IN FULL, AND ITS ONE SHOOT-BLOCKING CONDITION WAS DISCHARGED WHILE THIS SHEET WAS BEING WRITTEN.

Two separate things, and the second was the one that decided whether the panel was filmable:

1. **Every string on `k3.overlay.tools` is true in the state it is printed in, and each one was
   re-measured by this worker rather than copied from the plan that specified it.** 8 clearance
   rows — **7 CLEAR, 1 CLEAR-with-condition** — and **0 REWORD**. The panel's numbers (`3 cspann`,
   `4 VECTOR`, `42809`, `15 of 16`), its four verdict words and its four evidence paths all hold
   against the cluster and the committed artefacts. **Nothing on it is stated in a better state
   than it is in**, and the one `DESIGNED` is stated as `DESIGNED` with `NO RUN IS COMMITTED`
   printed beside it in the same capitals.
2. **`docs/demo/film/VO-CLOSE.md` §5.6 — the section the film authority and the string of record
   both name as the OWNER of these words — did not exist when this sheet's rows were composed at
   `23:31`.** Not stale, not disagreeing: **absent**, while referenced seven times from inside
   `VO-CLOSE.md` itself and twice from `ONSCREEN-TEXT.yaml`. That is the audit's **S8** failure
   mode — two documents from one wave disagreeing about the same 22 seconds — reproduced by the
   wave convened to remove it. **W1 landed §5.6 at `23:43:32`**, and on re-measurement at `23:44`
   the panel text in `VO-CLOSE.md` §5.6.1, in `ONSCREEN-TEXT.yaml` and in `close-card-plan.md`
   R-C4 are **byte-identical, all three** — `sha256[:24] = 9d53228e9442c416acec46d8`. **Condition
   C-13.1 is DISCHARGED (§13.4.2), and both readings are kept (§13.4).**

**Three refusals are filed pre-emptively (§13.3), none of them against anything in the tree.** They
exist so that nobody improvises one at 02:00, which is the same reason X1–X5 exist.

**Two further failures are reported and neither is repaired here, because neither is this worker's
file or this worker's node.** `claim_hygiene.py --check` goes **RED on `feature-census.md`** with
**three** new `HYG-sha-literal` hits (§13.5.4, W5's file — the count was `2` at `23:36` and `3` at
`23:44`, because that file is still being written), and the **regression guard's SUITES family
reports `1070 / 1056 / 1 / 12`** against the `1070 / 1069 / 0 / 0` baseline (§13.5.5). **KERNEL is
`PROVEN` caveat-free and `DEFAULT_MAX_RESPONSE_BYTES == 136 * 1024` is unmoved.** All 13
non-passing tests fail on *setup* with one identical cluster-limit error on a local node carrying
242 databases; §13.5.5.1 gives the three-step argument that no markdown edit could have caused it,
and **declines both available remedies** rather than moving the environment to make a number green.

**And one thing this worker checked and did not do.** The Agent Skills row could be promoted to
`EXERCISED` by running two assertion scripts that finish in seconds and committing the transcript.
**No such run was generated, captured or committed by this worker**, because `close-card-plan.md`
§0 rule 1 and the brief both rule that the tool is stated in the state it is in or not stated at
all. `find evidence -iname "*skill*"` returns nothing, and that is the state the panel prints.

---

## 13.1 · WHAT THIS WORKER MEASURED, AND HOW

**Nothing below is quoted from the plan that specified the panel, or from the census that scores
it.** Each value was taken independently today, and the command is printed so a stranger repeats
it in under a minute.

| # | reading | command, run verbatim by this worker | result |
|---|---|---|---|
| **A** | the four census verdicts | `python -c "import json;d=json.load(open('evidence/tool-usage/crdb-features.json'));[print(k,'=',v['verdict']) for k,v in d['rows'].items() if k in ('crdb_vector_index','crdb_managed_mcp','crdb_cloud_ccloud','crdb_agent_skills')]"` | `crdb_vector_index = EXERCISED` · `crdb_cloud_ccloud = EXERCISED` · `crdb_managed_mcp = EXERCISED` · **`crdb_agent_skills = DESIGNED`** |
| **B** | the MCP run | `python -c "import json;d=json.load(open('evidence/mcp/pack-run.json'));print(d['passed'],'/',d['total'],'exit',d['exit_code'],d['verdict'])"` | `15 / 16 exit 1 DIVERGED — KNOWN GAP` |
| **C** | the C-SPANN server refusal | `grep -c "42809" evidence/aws/ann/explain-unhinted.txt` and `grep -n "REFUSED BY THE SERVER" evidence/aws/ann/explain-unhinted.txt` | `3` occurrences of `42809`; **`:205` and `:220`** both read `REFUSED BY THE SERVER — SQLSTATE 42809` |
| **D** | `cspann` indexes, **live** | `SHOW CREATE TABLE` over the four vector-bearing tables, counting `VECTOR INDEX`, against `postgresql://root@localhost:26257/mainline_demo` | **`3`** — `clause_embedding` 1, `event_cue_coarse` 1, `event_cue_embedding` 1, `event_cue_stage` 0 |
| **E** | `VECTOR` columns, **live** | `SELECT count(*) FROM information_schema.columns WHERE udt_name = 'vector' AND table_schema NOT IN ('pg_catalog','information_schema','crdb_internal')` | **`4`** — `clause_embedding.embedding`, `event_cue_coarse.emb_coarse`, `event_cue_embedding.emb`, `event_cue_stage.emb` |
| **F** | the `ccloud` transcript | `head -c 300 evidence/ccloud/cluster-list.txt` | an `auth whoami` line (`logged in to … (org-3bkz4)`), then a **parsed JSON array** carrying `"cloud_provider": "AWS"` and `"cockroach_version": "v26.2.5"` |
| **G** | the skills tree, and the absence beside it | `ls skills/` then `find evidence -iname "*skill*"` | `README.md`, `designing-diachronic-gates`, `designing-vector-recall-prefixes`, `upstream`, `validate-spec.py` — and **`find` returns nothing**, so `NO RUN IS COMMITTED` is measured, not assumed |
| **H** | the panel as composed | extracted `k3.overlay.tools` from `ONSCREEN-TEXT.yaml` and hashed it against `close-card-plan.md` R-C4's fenced block | **byte-identical**, `sha256[:24] = 9d53228e9442c416acec46d8`; **7 lines**, widest line **99** characters — R-C4's own measurement, reproduced |
| **I** | the four printed paths | `test -d` on each | `evidence/aws/ann/` (4 entries) · `evidence/mcp/` (8) · `evidence/ccloud/` (2) · `skills/` (5) — **all four resolve** |

### 13.1.1 · Reading E is also the answer to the audit's **S7**, and it is worth one sentence

The brief's status table said *"5 live VECTOR columns"*; the census says `4`. **Both numbers come
off the same cluster and the difference is one predicate.** `udt_name ILIKE '%vector%'` returns
**5** — because `mainline.event_cue.tsv` is a **`tsvector`**, a full-text column that is not a
vector column at all. `udt_name = 'vector'` returns **4**. **The panel prints `4` and the panel is
right**, and this is recorded here so nobody "corrects" it upward from a wildcard the way the S1
role predicate was corrupted upward from an `IN` list.

---

## 13.2 · EVERY LINE OF `k3.overlay.tools` — the clearance rows

**The string of record is `ONSCREEN-TEXT.yaml:3228`, id `k3.overlay.tools`, `chip: derived`,
`editorial: false`.** Seven lines. Each row below states the claim, the measured basis, the
artefact or `file:line` that proves it, and the verdict.

| # | the line, exactly as it goes on screen | claim being made | measured basis (§13.1 reading) | verdict |
|---|---|---|---|---|
| **T1** | `------------------------------------------------------------------------------------------------` | **none — decoration.** 96 characters of horizontal rule | No claim to source. R-C4's remedy ladder names this rule as the **second** thing cut if the card lands below a legible floor, precisely because it asserts nothing | **CLEAR** |
| **T2a** | `COCKROACHDB  ·  THE FOUR CONTEST TOOLS.` | **there are four contest-named CockroachDB tools, and this panel enumerates all four** | Reading **A** — the census carries exactly these four rows. `DEVPOST.md:191`: the Technological Implementation criterion names three (*"distributed vector index, MCP Server, ccloud CLI"*) and the submission requirement names Agent Skills separately. **Four is the count of the criterion's own list, not our arithmetic** | **CLEAR** |
| **T2b** | `THE RULES REQUIRE TWO.` | **the eligibility floor is two, and we are naming it out loud on the frame** | `DEVPOST.md:191` — *"Three are EXERCISED against a floor of two"* — and `RULES-MATRIX.md` **R6**, which the audit §3 confirms *"states this correctly and explicitly does not count Agent Skills."* **Printing the floor beside the count is what converts a boast into a check**: a judge can now falsify the eligibility claim from the frame instead of taking it | **CLEAR** |
| **T2c** | `three EXERCISED, one DESIGNED` | **the ratio, before any row is read** | Reading **A**, exactly: three `EXERCISED` and one `DESIGNED` in `crdb-features.json`. **This is the most load-bearing fragment on the panel** and the reason T6 cannot be quietly dropped — the heading has already told the judge to expect a fourth row and to expect it to say `DESIGNED`. R-C5 | **CLEAR** |
| **T3** | `Distributed Vector Indexing (C-SPANN)  EXERCISED  3 cspann, 4 VECTOR, 42809    evidence/aws/ann/` | verdict **EXERCISED**; **3** `cspann` indexes; **4** `VECTOR` columns; SQLSTATE **`42809`**; path `evidence/aws/ann/` | Verdict from reading **A**. `3` and `4` from readings **D** and **E**, taken live on the cluster today, not inherited. `42809` from reading **C** — three occurrences, two of them the committed line `REFUSED BY THE SERVER — SQLSTATE 42809` at `explain-unhinted.txt:205` and `:220`. Path resolves (reading **I**) | **CLEAR** |
| **T4** | `Managed MCP Server                     EXERCISED  15 of 16, DIVERGED, published   evidence/mcp/` | verdict **EXERCISED**; **15 of 16**; the run **DIVERGED**; we **published** it; path `evidence/mcp/` | Verdict from reading **A**. `15 of 16`, `exit 1` and `DIVERGED — KNOWN GAP` from reading **B**, off `pack-run.json` itself. **`DIVERGED, published` is the strongest true form of this row and a weaker-sounding one than the file could have carried**: the one FAIL is `N01`, `mainline_qa.v_disposition_profile` readable by the `managed-mcp` identity when the pack asserted it was not, and it is **still open** — nobody revoked a grant to round `15` to `16`. See §13.3 **X6** for the form this row may never take | **CLEAR** |
| **T5** | `CockroachDB Cloud + ccloud CLI         EXERCISED  cluster list -o json, parsed   evidence/ccloud/` | verdict **EXERCISED**; the transcript is a **parsed** `cluster list -o json`, not a screen-scrape; path `evidence/ccloud/` | Verdict from reading **A**. Reading **F** confirms the file opens on an `auth whoami` line and then carries a **JSON array that parses**, with `cockroach_version v26.2.5` and `cloud_provider AWS` in it. **`parsed` is the honest word and it is doing work**: it says the artefact is machine-readable rather than a pasted terminal, which is the difference between evidence and a screenshot | **CLEAR** |
| **T6** | `CockroachDB Agent Skills               DESIGNED   shipped, validated;  NO RUN IS COMMITTED  skills/` | verdict **DESIGNED**; the skills are **shipped** and **validated**; **no run is committed**; path `skills/` | Verdict from reading **A** — `crdb_agent_skills = DESIGNED`, and it read `DESIGNED` **before this wave**, so the census was already right and only the film was silent. `shipped` from reading **G**: two authored skills, one de-branded upstream contribution and `validate-spec.py` are in the tree. **`NO RUN IS COMMITTED` is measured, not conceded** — `find evidence -iname "*skill*"` returns nothing. Path resolves | **CLEAR — with the standing condition below** |

### 13.2.1 · The condition on **T6**, which is a rendering condition and not a wording one

**`DESIGNED` is cleared on the words and conditioned on the pixels.** R-C5 is adopted here in full
and this sheet enforces it: `DESIGNED` renders in the **same size, same weight and same column** as
`EXERCISED` — no grey, no reduced opacity, no italic, no smaller type, no footnote marker, no
parenthesis — and `NO RUN IS COMMITTED` renders in the **same capitals** as `EXERCISED`.

**Why a clearance sheet is ruling on typography at all.** Every other row on this panel survives a
bad render; this one does not. A greyed `DESIGNED` is read as a footnote, a footnote is read as an
asterisk on a list of four, and a list of four with an asterisk is read as **four tools**. **The
degradation does not change one character of the string, which is exactly why it needs a row here
and not only a note in the layout file.** §13.3 **X7** is the refusal.

### 13.2.2 · What the panel does **not** claim — checked, because the absence is the point

* **No MCP route claim.** The row cites `evidence/mcp/` — **a committed transcript** — and never an
  endpoint. It does not say, and may not be captioned or narrated as saying, that a judge can query
  our ledger over MCP. The credential behind those transcripts is an account-level Cloud
  service-account key carrying `create_database`, `create_table` and `insert_rows`, and
  `evidence/deploy/judge-access.json` records **`credential_publishable: false`**. **A judge reads
  our ledger over pgwire as `mainline_judge`, or not at all.** R-C6 discharged; this worker wrote
  nothing to `docs/submission/JUDGE-START.md`, where the audit's **S2** lives and where it is
  another lead's to close.
* **No scale claim, no latency claim, no `16 of 16`.** The panel prints one number per row and
  every one of them is a count off a committed file.
* **No AWS name.** The panel is the CockroachDB half of the answer and it does not borrow from the
  seven services on `k2`.

---

## 13.3 · THE REFUSALS — three, filed against strings that are **not** in the tree

**All three are pre-emptive.** Nothing in `ONSCREEN-TEXT.yaml`, `VO-CLOSE.md`, `BEATS.yaml` or
`SPINE.md` says any of these today; this worker checked. They are filed because each is shorter,
flatter and more flattering than the true form, and 02:00 reaches for the shortest.

| # | ✗ **REFUSED** | why it is **false**, not merely strong |
|---|---|---|
| **X6** | **MUST NOT SHOW OR SAY:** *"all four exercised"*, *"all four are exercised"*, *"four tools exercised"*, *"four contest tools, all demonstrated"*, or **any variant that puts Agent Skills in the `EXERCISED` column** | **It is false against our own census.** `crdb-features.json` → `rows.crdb_agent_skills.verdict` reads **`DESIGNED`** (reading **A**), and its basis string says the assertion scripts' runs are not captured under `evidence/` — which `find evidence -iname "*skill*"` confirms returns nothing (reading **G**). This is the audit's **S5**, struck in `census/close-block.md` §3 on 2026-08-16; **the film must not re-introduce the sentence the census just removed.** And it may not be made true by capture: **nobody on this wave runs, generates or commits an Agent Skills transcript to promote the row** (`close-card-plan.md` §0 rule 1). **TRUE INSTEAD — and it is already on the frame:** `three EXERCISED, one DESIGNED`. |
| **X7** | **MUST NOT RENDER:** the Agent Skills row **greyed, dimmed, italicised, set smaller, marked with a footnote glyph, parenthesised, folded into the heading, or removed** — and must not render `NO RUN IS COMMITTED` in anything but the capitals `EXERCISED` is set in | **This is how a true panel becomes a false one without a single character changing.** Dropping the row leaves four names' worth of expectation set by the heading and three rows to satisfy it; greying it converts a stated verdict into a visual asterisk. **Either way *"three exercised, one designed"* silently becomes *"four tools"*, and the heading has already promised the judge otherwise.** R-C5 in full. The remedy ladder if the card is illegible is (1) the blank line under the heading, (2) the horizontal rule, (3) re-wrap the Agent Skills row onto two lines — **never a word, never a row, and never the `DESIGNED` state.** |
| **X8** | **MUST NOT SAY:** any word of `k3.overlay.tools`, in any take, in voice-over, in a caption read aloud, or as an ad-lib over the card — **the panel is read by the eye and never by the voice** | **Speaking it breaks the film's arithmetic, and the arithmetic is why the panel was affordable at all.** The whole justification for putting seven lines on `k3` is R-C3: *a card costs layout, not seconds.* `k3` has **0.7 s** of air, which at the file's own 1.9 w/s is **1.3 words** — there is no sentence there. `k2`'s 2.6 s was **priced and refused in writing**: a 19-word line takes that block to `10.0 s` in a 10 s window with zero air and breaks `VO-CLOSE.md` §3.5's landing-4 alignment. **A take that narrates the panel has lengthened the film**, and the film may not be lengthened — 172 s, 174 s hard stop. **The air stays air.** Related and unchanged: §8.2's refusal of any `k1` take exceeding 10 words. |

**A fourth thing, not a row because it is not a string.** R-C7 bans a **fifth highlight sweep
landing** on `k3`. The sweep is capped at four and all four are spent in `k2`. A pointer moving
across this panel during a 6 s card already carrying a three-line limit, a four-stanza rail and two
URLs would be the roving highlight `ONSCREEN-TEXT.yaml` itself calls *"a card nobody reads."*
**The panel is pause material by construction.**

---

## 13.4 · **`VO-CLOSE.md` §5.6 — found missing at `23:31`, landed by W1 at `23:43`, RE-MEASURED AND CLOSED**

> **THIS ROW IS KEPT IN BOTH ITS READINGS RATHER THAN OVERWRITTEN**, which is this repository's
> standing rule for every number on every page. The defect below was real when it was measured;
> **it is not real now.** Deleting the first reading would have been the tidier edit and the
> dishonest one — a clearance sheet that silently drops a finding it raised is a sheet nobody can
> audit, and the whole subject of this section is a wave that published a correction and then
> contradicted it.

### 13.4.1 · What was measured at `23:31`, and why it was filed as shoot-blocking

**This worker runs last, and W1 was still writing.** At the time §13.2's rows were composed:

`docs/demo/film/VO-CLOSE.md` is the film authority — its §4.1 says *"Every word below is the
committed 50 s text"*, and `close-card-plan.md` **R-C8** rules it the sole authority for the close
precisely because two documents prescribing the same 22 seconds is the audit's **S8**.

**Measured, by listing every heading in the file:**

* `VO-CLOSE.md` **references §5.6 seven times** — at `:208`, `:212`, `:320`, `:398`, `:992`, `:997`
  and `:998` — including *"§5.6's **What is NOT on this panel** forbids saying it aloud"* (`:212`),
  *"The panel therefore lives on `k3`, and **§5.6 is it**"* (`:398`), and pointers to **§5.6.1**
  (the ≤ 119 × ≤ 32 geometry budget) and **§5.6.3** (the sweep ban) at `:997`–`:998`.
* **`VO-CLOSE.md` has no §5.6.** Its §5 runs `5.1`, `5.2`, `5.3`, `5.3.1`, `5.4`, `5.5` and then
  §6 begins at `:1099`. There is no `5.6`, no `5.6.1` and no `5.6.3`.
* **The panel string appears zero times in `VO-CLOSE.md`.** `grep -c "THE RULES REQUIRE TWO\|Distributed Vector Indexing\|NO RUN IS COMMITTED\|three EXERCISED, one DESIGNED" docs/demo/film/VO-CLOSE.md` returns **`0`**.
* §5.2 is headed *"Overlay text — **exact**"* and its fenced block carries the limit, the rail and
  both URLs — **and not the panel** — so the authority's own exact-overlay block for `k3` omits a
  string the film renders on that card.
* `ONSCREEN-TEXT.yaml:3276` declares: *"THE WORDS ARE OWNED BY `docs/demo/film/VO-CLOSE.md` §5.6
  and this file reproduces them to the character; **if the two ever disagree, VO-CLOSE.md is right
  and this file is wrong**."* **That tie-break resolves to a section that is not there**, and
  `:3335` cites §5.6.1 for the geometry budget the same way.

**Why this is a blocking condition and not a typo.** The reproduction cannot be checked against its
authority, so the discipline `ONSCREEN-TEXT.yaml` states for itself — *reproduces them to the
character* — is unverifiable, and the one rule that resolves a disagreement points at nothing. **A
panel whose authority is a dangling pointer is exactly the S8 shape the wave was convened to
remove**, committed in the act of removing it.

**What was NOT wrong even then.** The panel's *content* was correct — §13.2 clears all seven lines
— and the string in `ONSCREEN-TEXT.yaml` was already **byte-identical to `close-card-plan.md`
R-C4** (reading **H**), so there was never a live disagreement about the words. The defect was that
**the authority did not carry them**, which meant the next person to edit either file had no way to
tell which one had moved.

**CONDITION C-13.1, as filed at `23:31`:** *the panel is not filmable until `VO-CLOSE.md` carries a
real §5.6 holding the panel text verbatim, its "What is NOT on this panel" prohibition (the basis
of **X8**), §5.6.1's geometry budget and §5.6.3's sweep ban.*

### 13.4.2 · **C-13.1 IS DISCHARGED.** Re-measured `23:44`, after W1's file changed under this audit

`docs/demo/film/VO-CLOSE.md` was written at **`23:43:32`** — after §13.4.1 was measured and while
this sheet was being written. **Re-read in full, and the section now exists:**

| what C-13.1 required | **measured `23:44`** |
|---|---|
| a real §5.6 | **`:1076` — §5.6 · THE FOUR CONTEST COCKROACHDB TOOLS — the panel on `k3`, read and never spoken** |
| the panel text verbatim | **`:1098` — §5.6.1 · Panel text — exact, and the measured geometry** |
| the geometry budget (§5.6.1) | present, with §5.6.2 added beside it — *"What this costs `k3`, in numbers"* |
| the sweep ban (§5.6.3) | **`:1230` — §5.6.3 · No sweep. The panel is read, never swept.** |
| the *What is NOT on this panel* prohibition — **X8's basis** | **`:1257` — §5.6.5** |
| — | and **`:1239` — §5.6.4 · Evidence — one row per tool**, which C-13.1 did not ask for |

**And the check that actually matters — the authority and its reproduction now agree to the
byte.** The panel extracted from all three files and hashed:

```
VO-CLOSE.md §5.6.1   (AUTHORITY)      sha256[:24] = 9d53228e9442c416acec46d8   7 lines, 99 ch
ONSCREEN-TEXT.yaml   k3.overlay.tools sha256[:24] = 9d53228e9442c416acec46d8   7 lines, 99 ch
close-card-plan.md   R-C4             sha256[:24] = 9d53228e9442c416acec46d8   7 lines, 99 ch
```

**AUTHORITY == REPRODUCTION == PLAN.** `ONSCREEN-TEXT.yaml:3276`'s tie-break — *"if the two ever
disagree, `VO-CLOSE.md` is right and this file is wrong"* — now resolves to a section that exists
and carries the same string. **R-C8 is satisfied and the audit's S8 shape is not reproduced.**

> **C-13.1 — DISCHARGED.** No condition on the panel survives from this sheet. **The three refusals
> in §13.3 are not conditions and do not lift**: they bind every take, in perpetuity.

**One observation, recorded and not raised as a defect.** §5.6 is inserted **between §5.4 and
§5.5**, so §5's headings now read `5.1, 5.2, 5.3, 5.3.1, 5.4, 5.6, 5.5`. §5.5 is the retired
`48 s / 170 s` variant, so putting live material ahead of a retired section is defensible ordering;
it is noted only so that a reader scanning the table of contents is not the one to discover it.
**It changes no string and no verdict, and this worker does not edit another worker's file to
renumber a heading.**

### 13.4.3 · The lesson, which is worth more than the finding

**This worker was specified to run LAST and did not, in fact, run last.** Between the first
verification sweep and the final one, `feature-census.md`'s hygiene violations went from **2 to 3**
and `VO-CLOSE.md` gained six new sub-sections. **Any single-pass verification of a wave still being
written is a photograph, not a proof** — which is why every reading in §13.1 and §13.5 carries the
time it was taken, and why the orchestrator must re-run §13.5's four commands against the tree it
actually commits. **This section is not a substitute for that re-run. It is a record of what was
true when it was read.**

---

## 13.5 · THE WAVE VERIFICATION BLOCK — every invariant `close-card-plan.md` §4 lists

**Run by this worker against the working tree, after W1–W5 landed.** Each row names the command so
a stranger repeats it in under a minute.

### 13.5.1 · The film's arithmetic — `BEATS.yaml`, unchanged

| invariant | required | **measured** | verdict |
|---|---|---|---|
| `total_s` | 172 | **172** | ✓ |
| `hard_stop_s` | 174 | **174** | ✓ |
| `demo_s` | 148 | **148** | ✓ |
| `close_s` | 22 | **22** | ✓ |
| `close_words` | 36 | **36** | ✓ |
| `k1` / `k2` / `k3` `dur` | 6 / 10 / 6 | **6 / 10 / 6** | ✓ |
| `k1` / `k2` / `k3` `vo_word_budget` | 10 / 16 / 10 | **10 / 16 / 10** | ✓ |
| `k1` / `k2` / `k3` in-points | 148 / 154 / 164 | **148 / 154 / 164** | ✓ |

`148 + 22 + 2 = 172 ≤ 174`. **Not one second and not one spoken word was added to put four tool
names on screen**, which was R-C3's whole condition.

### 13.5.2 · `k2` was not touched — byte-identical, proved by hash and not by reading

`k2.overlay.aws_column` and `k2.overlay.cockroachdb_column` extracted from `HEAD` and from the
working tree and hashed:

```
k2.overlay.aws_column           HEAD 748c00dd51fb3029   WORK 748c00dd51fb3029   IDENTICAL  (1067 B)
k2.overlay.cockroachdb_column   HEAD 9f38c578b27917fd   WORK 9f38c578b27917fd   IDENTICAL  (1937 B)
```

**R-C1 holds.** The tightest card in the film was not re-rendered by this wave, and the four
open REWORDs on it (§7.7 SSM, §7.8 the S3 heading, §7.9 the recursive CTE, §7.10 `256/256`) are
neither discharged nor disturbed — §12.5 row **O26** still governs them.

### 13.5.3 · The two greps the brief names, and the third that must exit 1

| # | command | required | **result** | verdict |
|---|---|---|---|---|
| 1 | `grep -rn "LIKE 'mainline" docs/` | nothing | **6 matches in 5 files, exit 0** — and **none is a published check.** `docs/submission/AUDIT.md:147` and `docs/demo/close-card-plan.md:50` **quote the corruption in order to strike it**; `docs/submission/census/crdb-programmable.md:728` is a **different query** (`pg_namespace` / schema ownership, not `pg_roles`); `docs/diagnosis/divergence-census-plan.md:204` is an `information_schema.columns` schema filter; **and 2 are in this sheet, §13.5.3, quoting the command in order to report it** | **PASS on substance, FAIL as literally worded** — see §13.5.3.1 |
| 2 | `grep -rni "all four are exercised" docs/submission/census/` | nothing | **1 match, exit 0** — `census/close-block.md:386`, which reads *"**§3 no longer says** 'all four are exercised … with a committed transcript.'"* It is W4's **correction record**, quoting the struck sentence to record that it was struck | **PASS on substance, FAIL as literally worded** — see §13.5.3.1 |
| 3 | `grep -rn --include=*.tf "aws_cloudwatch_event\|aws_scheduler" infra` | no output, **exit 1** | **no output, exit 1** | **✓ PASS** |

**Row 3 is also the audit's S6 discharged, and it is worth showing both halves**, because the whole
point of that row is that the published command must be the one that was run:

```
$ grep -rn "aws_cloudwatch_event\|aws_scheduler" infra          # as originally published
Binary file infra/envs/demo/.terraform/.../terraform-provider-aws_v6.58.0_x5.exe matches
Binary file infra/modules/cost-guard/.terraform/.../terraform-provider-aws_v6.59.0_x5.exe matches
Binary file infra/modules/demo-api/.terraform/.../terraform-provider-aws_v6.59.0_x5.exe matches
exit 0                                                          # 3 matches, all vendored binaries

$ grep -rn --include=*.tf "aws_cloudwatch_event\|aws_scheduler" infra
exit 1                                                          # no output — the true form
```

**The conclusion was always right and the command was always wrong.** `census/close-block.md:327`
now carries the `--include=*.tf` form.

#### 13.5.3.1 · Both "empty grep" checks return matches, and **the checks are wrong, not the tree**

**This worker is required to report a failure as a failure, so both are reported as returning
matches.** But a clearance sheet that stops at the exit code would be filing two defects that do
not exist, so the substance is stated too:

**Every one of the seven matches is a document quoting a struck string in order to strike it —
including the two this sheet just added by printing the command.** That is not a residual defect —
**it is the repository's standing convention**, the same one that lets `MUST-NOT-CLAIM.md`,
`CLAIMS-CLEARANCE-CR.md` and this file carry banned sentences verbatim under a
`prose-hygiene: register` marker. **A correction record that may not name the thing it corrected is
not a correction record** — and a verification sheet that cannot print the command it ran is the
same defect wearing a different hat. **This is also why an "empty grep" is the wrong shape of check
for a repository that documents its own strikes:** it counts mentions, and a strike is a mention.
The narrow forms below count *predicates*, which is what the claim was ever about.

**The narrow forms that are actually falsifiable**, and which this worker ran:

```
$ grep -rn "rolname LIKE 'mainline" docs/submission/census/ docs/submission/feature-census.md
exit 1                       # the S1 corruption is gone from every PUBLISHED predicate

$ grep -rni "all four are exercised" docs/submission/census/ | grep -v "no longer says"
exit 1                       # the S5 sentence survives only inside its own strike record
```

**S1 and S5 are both closed.** `census/close-block.md:262` now carries the explicit nine-name `IN`
list with `ORDER BY 1` and the answer that did not move — *nine rows, `rolcanlogin` false on all
nine* — plus the half-clause naming `mainline_api` and `mainline_judge` as the two service logins
deliberately outside the lattice. `close-block.md` §3 now reads *"**Three** of the four are
exercised in this repository with a committed transcript … **the fourth, Agent Skills, is
`DESIGNED`**."* **The claim was strengthened rather than weakened to match a broken check**, which
is R-C9's instruction discharged.

### 13.5.4 · `claim_hygiene.py --check` over all six touched files — **RED, and the RED is new**

```
$ .venv/Scripts/python.exe scripts/demo/claim_hygiene.py --check \
    docs/demo/film/VO-CLOSE.md docs/demo/film/ONSCREEN-TEXT.yaml \
    docs/demo/film/BEATS.yaml docs/demo/film/SPINE.md \
    docs/submission/census/close-block.md docs/submission/feature-census.md
  scanned 6 file(s) against 21 rules
  FAIL  docs/submission/feature-census.md:958:  [HYG-sha-literal] 2dc5c8… in: at commit `2dc5c8…`, which `docs/CI-STATE.md` itself calls five commits behind the tip it was
  FAIL  docs/submission/feature-census.md:1617: [HYG-sha-literal] 2dc5c8… in: | U-C4 | `crdb_agent_skills` — **detector only; the verdict stays DESIGNED** | **DESIGNED** | two-part predicate, propos
  2 claim-hygiene violation(s)
exit 1
```

**RE-RUN AT `23:44`, AND THE COUNT HAD MOVED TO `3`.** `feature-census.md:1707` joined the two
above — same rule, same literal, on the `O19` row. **The reading is reported as it moved rather
than as one number**, because W5's file was still being written while this sheet verified it
(§13.4.3). **Four of the six files remain clean; every violation in all three readings is in
`feature-census.md`, and the count may be higher again by the time the orchestrator reads this.**

> **THE OFFENDING LITERAL IS MASKED IN THIS PASTE, TO ITS LAST CHARACTER ONLY, AND THE MASK IS
> DECLARED RATHER THAN SILENT.** The scanner's `HYG-sha-literal` pattern matches a bounded run of
> **exactly 7 or 40 hex characters**, so reproducing W5's literal verbatim here would plant four
> more findings **in this file** — and this register's header commits it to *"exit 1 with 6
> findings on 4 lines, all of them inside the pasted self-test transcript."* **A clearance sheet
> that widens its own sanctioned exception while reporting somebody else's is not a clearance
> sheet.** Every `2dc5c8…` below is the same 7-character literal with its final character elided;
> **run the command and the real one prints.** This is a redaction of one character in a quotation,
> not a softened finding: the file, the two line numbers, the rule id and the exit code are exact.

**Four of the six film/census files are clean. Both failures are in `docs/submission/feature-census.md`,
which is W5's, and both were introduced by this wave.** Proved rather than assumed — the same six
files extracted at `HEAD` into a scratch directory and scanned:

```
$ git show HEAD:<each of the six> > <scratch>/ ; claim_hygiene.py --check <scratch>/*
  scanned 6 file(s) against 21 rules
  claim hygiene OK
exit 0
```

and `git show HEAD:docs/submission/feature-census.md | grep -c <the literal>` returns **`0`** against
**`2`** in the working tree, with both occurrences on `+` lines of `git diff HEAD`.

**THE FIX IS THE TEXT, NEVER THE SCANNER — and this worker did neither.** `feature-census.md` is
W5's file and is not repaired here. For the orchestrator, the remedy is already in the scanner's
own design: `HYG-sha-literal` is exempted on any line carrying the inline marker
`claim-hygiene: quoting` (`scripts/demo/claim_hygiene.py:300`), or inside a `PROHIBITION_KEYS`
block. **Nobody may add `HYG-sha-literal` to an ignore list, relax its pattern, or drop
`feature-census.md` from the sweep** — a hygiene rule that is loosened the first time it fires is
`PL-2` decoration, and this repository's own `--self-test` exists to prevent exactly that.

**The irony is worth one line, because it is the reason this is a small defect and not a
dangerous one.** Every offending line is W5 **refusing to promote `crdb_agent_skills`** — *"the
verdict stays DESIGNED"*, *"Promotion is refused on Part 2's own evidence: the recorded green is at
`2dc5c8…`, five commits behind."* **The content is the most honest paragraph in the file. Only its
citation form is banned.**

#### 13.5.4.1 · This sheet's own scan — the register's declared count, restored exactly

**A verification sheet that reports somebody else's RED without printing its own is not
verification.** Scanned together with the two other files this worker wrote:

```
$ .venv/Scripts/python.exe scripts/demo/claim_hygiene.py --check \
    docs/demo/film/CLAIMS-CLEARANCE.md docs/demo/film/CLAIMS-CLEARANCE-CR.md \
    docs/demo/ON-SCREEN-CLAIMS.md
  scanned 3 file(s) against 21 rules
  6 claim-hygiene violation(s)                    # lines 833, 834, 835 ×2, 836 ×2
exit 1
```

**`CLAIMS-CLEARANCE-CR.md` and `ON-SCREEN-CLAIMS.md` are clean. All 6 findings are in this file, on
4 lines, and every one is inside the pasted `--self-test` transcript at §8.4** — which is exactly
what this register's header commits it to: *"SCANNING THIS FILE RETURNS EXIT 1 WITH 6 FINDINGS ON 4
LINES, ALL OF THEM INSIDE THE PASTED SELF-TEST TRANSCRIPT."* **The declared count is unchanged by
§13, and restoring it took a correction to this worker's own draft**: the first version of §13.5.4
quoted W5's literal verbatim and planted **4 more findings in this file**, taking it to 10 on 8
lines. **That is the same class of defect this section reports in `feature-census.md`, committed in
the act of reporting it**, and it is recorded rather than quietly fixed — a register that widens
its own sanctioned exception while auditing somebody else's has stopped being a register.

**`--self-test` re-run and unchanged: `planted 4 violation families, scanner fired on 4`, exit 0.**
The scanner can still go red, which is the only reason its green means anything.

### 13.5.5 · The regression guard — baseline held

Run as `scripts/qa/regression_guard.py --no-live --no-cloud --only SUITES,KERNEL,BOUNDS` with
`--suite-out` writing a JUnit XML and `--json` writing the full record. **`--live` and `--cloud`
were declined deliberately**: this worker is forbidden to touch AWS, and the deployed origin's
`ok true` / `deploy_chain_applied 271` / `gate_run_verdict PROVEN` are already carried by the
auditor's own run in `AUDIT.md` §1 the same day.

**KERNEL and BOUNDS hold exactly. SUITES does not, and it is reported as a FAIL.**

```
KERNEL  verdict             PASS  expected PROVEN                    observed PROVEN
KERNEL  caveats             PASS  expected (none)                    observed (none)
KERNEL  refusal_sqlstate    PASS  expected 23514                     observed 23514
KERNEL  refusal_exhibit     PASS  expected gate_closed_when_issued   observed gate_closed_when_issued
KERNEL  drift_sqlstate      PASS  expected P0001                     observed P0001
KERNEL  drift_exhibit       PASS  expected mainline.fn_permit_merge_gate  observed mainline.fn_permit_merge_gate
KERNEL  admission_sqlstate  PASS  expected ADMITTED [00000]          observed ADMITTED [00000]

SUITES  collected           PASS  expected 1070                      observed 1070
SUITES  passed              FAIL  expected 1069                      observed 1056
SUITES  failed              FAIL  expected 0                         observed 1
SUITES  errors              FAIL  expected 0                         observed 12
SUITES  skipped             PASS  expected 1                         observed 1

BOUNDS  ceiling_constant    PASS  expected 136 * 1024 == 139264      observed 136 * 1024 == 139264
BOUNDS  straddle            PASS  expected largest_served < 139264 < largest_identity   observed 137939 < 139264 < 490373
BOUNDS  one_refusal         PASS  expected exactly 1 identity object above the ceiling  observed 1: assets/index-HZTFrKeL.js

VERDICT  REGRESSION - 3 of 15 checks FAILED in SUITES (12 PASS, 0 SKIP)
```

**The numbers come from the `--junitxml` root element and from nothing else, never from a terminal
tail** — the rule §12.10 set for this file and which it keeps. The root element, verbatim:

```xml
<testsuite name="pytest" errors="12" failures="1" skipped="1" tests="1070" time="195.344"
           timestamp="2026-08-16T23:36:25.171151+10:00" hostname="AetherX">
```

* **`DEFAULT_MAX_RESPONSE_BYTES` did not move** — `136 * 1024 == 139264`, and the straddle still
  brackets it: `137939 < 139264 < 490373`, with exactly one identity refusal.
* **The gate proof is `PROVEN` and `caveats` is empty** — caveat-free, with all three SQLSTATEs
  and both constraint names intact.
* **`collected` is `1070`, matching the baseline exactly.** No test was added, removed, renamed
  or deselected.

#### 13.5.5.1 · The 13 non-passing tests share ONE cause, and it is the local node, not this wave

**All 13 — the single `failure` and all 12 `errors` — fail on *setup* with the identical error**,
read out of the JUnit XML rather than off a terminal:

```
psycopg.errors.ConfigurationLimitExceeded: error executing StatementPhase stage 1 of 1 with
17 MutationType ops: cannot create new schema object(s): would exceed approximate maximum
(20000); current count: 20270
HINT:  You can increase the limit by adjusting the cluster setting sql.schema.approx_max_object_count
```

**The local CockroachDB node is saturated.** Measured read-only by this worker on
`postgresql://root@localhost:26257`: **242 databases on the node, 54 of them scratch-shaped**,
accumulated across many worker waves — each of which created a scratch database and none of which
dropped it. The fixtures cannot create their schemas, so every test that needs a fresh one errors
before its body runs.

**Why this is not attributable to the close-card wave, stated as an argument a stranger can check
rather than as a reassurance:**

1. **`collected` is `1070`, the baseline exactly.** A wave that changed what the suite runs would
   move the collection count; this one did not move it by one.
2. **The wave touched six files: four `.md` and two `.yaml`, all under `docs/`.** Nothing under
   `docs/**` is collected by pytest, no workflow filters on it, and `docs/demo/film/**` is outside
   every `TARGET_GLOBS` entry. **There is no path by which a markdown edit reaches a fixture.**
3. **The failure mode is a cluster resource limit, not an assertion.** Not one of the 13 records a
   wrong value; every one records `ConfigurationLimitExceeded` on `CREATE`.

> **REPORTED, NOT REPAIRED.** The two available remedies are **raising
> `sql.schema.approx_max_object_count`** and **dropping the 54 accumulated scratch databases**.
> **This worker did neither, and the reason is the same reason `N01` stays FAIL:** both would turn
> a red number green by moving the environment rather than by fixing anything, and one of them
> destroys data on a node the demo world lives on. **Whoever clears it must re-run
> `regression_guard.py` and get `1070 / 1069 / 0 / 0` from a `--junitxml` root element before the
> baseline may be called held.** Until then the honest statement is: **KERNEL caveat-free and
> BOUNDS unmoved, SUITES unverified on a saturated node.**

**Nothing this worker did could have moved it.** The three files written are markdown under
`docs/`. **No database was created or dropped** — an empty scratch database would have been a write
with no reader, and on this node it would also have been one more of the 20,270. No grant moved, no
cluster setting written, no `terraform`, no AWS call, no SSM parameter, no credential printed, no
commit.

### 13.5.6 · The two divergences that stay open, restated so a green is never misread

* **`mainline_qa.v_disposition_profile` / `N01` stays open.** `evidence/mcp/pack-run.json` reads
  `15 / 16`, `exit_code 1`, `verdict DIVERGED — KNOWN GAP` **today**, five days after the
  `2026-08-11` run said the same thing. **No grant was revoked or widened by this wave to change
  it.** If a future capture ever reads `16 of 16`, check what was revoked before believing it.
* **The PRIVILEGES `FAIL` on `mainline.exposure_line` / `mainline.exposure_receipt` INSERT is the
  sanctioned standing gap**, not a regression. Widening the write surface of an unauthenticated
  endpoint is the founder's call and he has not made it.

**A negative suite that has quietly gone green is the worst artefact in a repository, because it
reads as the strongest.**

---

## 13.6 · WHAT THIS SECTION FOUND IN OTHER WORKERS' FILES — reported, not repaired

**`close-card-plan.md` §5 gives each worker literally enumerated paths and this worker's are three
markdown files.** Two defects were found outside them. Both are named with `file:line`; neither was
touched.

| # | file, owner | defect | severity |
|---|---|---|---|
| **D-W1** | `docs/demo/film/VO-CLOSE.md` — **W1** | **§5.6, §5.6.1 and §5.6.3 did not exist** at `23:31`, while referenced 7 times in that file plus twice from `ONSCREEN-TEXT.yaml`; the panel string appeared **0** times in the file the string of record names as owning it | **CLOSED `23:43:32`.** W1 landed §5.6 through §5.6.5; all three copies of the panel are byte-identical. **C-13.1 discharged, §13.4.2.** Kept in the table because a finding that was raised and then met is a record, not an embarrassment |
| **D-W5** | `docs/submission/feature-census.md` — **W5** | `HYG-sha-literal` fires on one 7-character commit literal (`2dc5c8…`, masked per §13.5.4) at `:958`, `:1617` and — from `23:44` — `:1707`. **New this wave** (`0` at `HEAD`; every occurrence on a `+` line). Takes `claim_hygiene.py --check` from **exit 0 to exit 1** across the six touched files | **OPEN — BLOCKING for CI.** `.github/workflows/claims.yml` asserts this scanner. The remedy is the text (`claim-hygiene: quoting`, `:300`), never the rule. **Re-run before committing: the count moved once already** |
| **D-ENV** | the **local CockroachDB node** — nobody's file | `sql.schema.approx_max_object_count` exhausted: **20,270 objects against a 20,000 maximum**, from **242 databases, 54 scratch-shaped**, left behind by earlier waves. 13 tests error/fail on setup; SUITES reads **`1070 / 1056 / 1 / 12`** | **BLOCKING for the baseline claim** — the suite cannot be said to hold until a clean node reproduces `1070 / 1069 / 0 / 0` from a `--junitxml` root. **Not an artefact defect and not caused by this wave** (§13.5.5.1). Remedies declined here on purpose |

**Three things this worker deliberately did not do, each of which would have made a number look
better today.**

1. **Did not run or commit an Agent Skills transcript** to turn `DESIGNED` into `EXERCISED`. The
   scripts finish in seconds. The panel prints the state the tool is in.
2. **Did not touch `mainline_qa`'s grant.** `N01` stays FAIL and the MCP verdict stays
   `DIVERGED — KNOWN GAP`.
3. **Did not soften a clearance verdict, relax the hygiene rule, or edit another worker's file to
   make its check pass.** A REFUSE that is downgraded to let a string through is not a clearance
   system; it is a rubber stamp, which is the exact thing `k3`'s own limit card says this project
   will not dress up.

---

**Signed:** W6 · clearance, hygiene and whole-wave verification · close-card wave · 2026-08-16
(UTC), audited against `docs/submission/AUDIT.md` FIX 1, `docs/demo/close-card-plan.md`
R-C1…R-C10 and §4, `docs/submission/MUST-NOT-CLAIM.md` (which retains precedence) and
`docs/demo/research/r6-honesty.md` Part A.
**Three files written — `CLAIMS-CLEARANCE.md` (this section), `CLAIMS-CLEARANCE-CR.md` (§7, a
scope note only) and `docs/demo/ON-SCREEN-CLAIMS.md` — and nothing else in the tree touched.**
**`VO-CLOSE.md`, `ONSCREEN-TEXT.yaml`, `BEATS.yaml`, `SPINE.md`, `close-block.md` and
`feature-census.md` were READ and NOT EDITED**, including the two files carrying the defects in
§13.6: a worker who repairs another worker's file destroys the only evidence that the wave needed
repairing. No ratchet, floor, ceiling, assertion or expectation was moved. No grant widened, none
revoked. **No cluster setting written and no database created or dropped**, on a node whose
saturation is the subject of D-ENV. No `terraform`, no AWS surface, no SSM parameter, no
credential, no commit.
**8 rows cleared, 0 reworded, 3 refused, 1 shoot-blocking condition raised and discharged,
2 defects still open and handed back — and 2 of the wave's own verification checks reported RED
rather than rounded. Every reading carries the time it was taken, because the wave was still
being written while it was verified, and the orchestrator must re-run §13.5 against the tree it
actually commits.**
