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
2. **The operator surface is not on the deployed origin.** Two workers measured this
   independently today, by `GET` only: `FALLBACKS.md` M2 and `ONSCREEN-TEXT.yaml` finding F-1.
   `GET /operator.html` answers `200` with **4,655 bytes byte-identical to `GET /`**, titled
   `MAINLINE console`, and its only script asset contains **zero** occurrences of
   `CONTROL OF WORK`, `1 obligation outstanding` or `cow-`. **The film scored in `CLICKS.md`
   has no pixels on this origin today.** That is nobody on this sheet's to fix and it is not a
   claims defect — but it decides whether there is a film at all, so it is condition 1 in §10.

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
> 1. **The operator surface is on the deployed origin** — checked by `<title>` **and** by the script
>    asset containing `1 obligation outstanding`, not by a `200` (§8.1). Until then the film scored
>    in `CLICKS.md` cannot be shot at all, and `FALLBACKS.md` F-9 governs — that fallback is cleared
>    and its spoken line is row B9.
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
