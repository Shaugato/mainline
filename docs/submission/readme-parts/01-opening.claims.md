<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->
<!-- prose-hygiene: register -->

# 01-opening.claims.md — the ledger for W1

Every claim, number and citation in the current `README.md` lines 1–50 and in its
one-sentence-version block (`README.md:317–321`), with exactly one disposition each:
**KEPT** (present in `01-opening.md`), **MOVED** (an existing file already carries it — the
grep that proves it is printed), or **DROPPED** (with the reason). Per plan ruling **R2** no
destination file was edited by this worker, and a `MOVED` row without a printed grep would be
a `KEPT`.

**Scope note (plan R17).** Sections C–I of the rebuilt `README.md` are other workers' fragments
and were not written when this ledger was made. Rows below marked `MOVED → readme-plan §2` are
claims that stay in `README.md` but in a section this worker does not own; the grep prints the
assembly-table row that assigns them. They are not dropped from the page.

---

## A · Lines 6–12 — the tagline and the three opening assertions

| # | claim in the current README | disposition | evidence |
|---|---|---|---|
| 1 | `# MAINLINE` (title) | MOVED → W7 | `readme-plan.md:72` `| — | W7 | SPDX comment block, then `# MAINLINE` | 6 |` — the brief forbids this worker a title |
| 2 | L8 "Institutional safety memory as a version-controlled repository whose commits are written by incidents." | MOVED → `docs/submission/DEVPOST.md` | `grep -c "version-controlled repository whose commits are written by incidents" docs/submission/DEVPOST.md` → `1` (line 161). Also `CAMERA-STRINGS.yaml:103` `title_card`. Dropped from the opening because it is four abstractions before the reader has met one concrete thing — the exact failure the founder named. |
| 3 | L10 "Every clause … carries a **blame pointer to the event that wrote it**" | **KEPT** | `01-opening.md` §B ¶1, plain-language: "Every clause of a procedure carries a pointer to the event that caused it to be written. We call that pointer **blame** — who wrote this line, and why." |
| 4 | L10 "The permit-to-work is a **protected branch**." | **KEPT** (reworded) | §B ¶2 "A permit to work is then handled like a change to code, and issuing it is a merge." The `git` term itself is MOVED: `grep -o "the permit-to-work is a protected branch" docs/submission/DEVPOST.md` → `the permit-to-work is a protected branch` (line 161). |
| 5 | L10 "Its merge is *refused by the database* until every recalled precursor carries a signed disposition." | **KEPT** | §B ¶2–3, with `obligation` and `disposition` glossed at first use as R4 requires. |
| 6 | L12 "Recall is not displayed beside the decision. **Recall is a precondition of the decision.**" | **KEPT** | §B ¶4, with `recall` replaced by "the reminder" — `recall` is undefined at that point in the page and R4/Rule One forbid it. |

## B · Lines 14–18 — the two judge pointers

| # | claim | disposition | evidence |
|---|---|---|---|
| 7 | L14–16 `docs/submission/JUDGE-START.md` "is ninety seconds: what to look at, what to run, and what we are not claiming" | MOVED → readme-plan §2 | `readme-plan.md:75` `| C | W2 | `## See it refuse — live, with no account` | 55 |`. Judge navigation is section C by the assembly table. |
| 8 | L16–18 `docs/demo/JUDGE-90-SECONDS.md` "is one row per frame — the exact value, the route or file it came from, and the one command that regenerates it" | MOVED → readme-plan §2 | same grep as row 7. `grep -on "one row per frame" docs/demo/JUDGE-90-SECONDS.md` returned **no match**, so the sentence itself is the README's and this row is an assignment, not a proven external home. Flagged to W2 rather than asserted here. |

## C · Lines 20–28 — the Devpost-required table

Plan **R9** opens section C with these rows. All five are W2's; none is dropped from the page.

| # | claim | disposition | evidence |
|---|---|---|---|
| 9 | L24 demo URL `https://ihuuyvm4z6nfuktihnkey77fpy0eyrhj.lambda-url.ap-southeast-1.on.aws`, `ok: true`, database `mainline_demo`, deploy chain `271` of `271` [src: evidence/demo/live-beats.json#world.health] | MOVED → `docs/submission/JUDGE-START.md` | `sed -n '13,17p' docs/submission/JUDGE-START.md` → ``**The demo is live and it takes no credential either:**`` / ``` `https://ihuuyvm4z6nfuktihnkey77fpy0eyrhj.lambda-url.ap-southeast-1.on.aws` — ``` / ``` `GET /v1/health` answers `ok: true` on database `mainline_demo` with the deploy chain at ``` / ``` `271` of `271` files … [src: `evidence/demo/live-beats.json`]``` |
| 10 | L24 "`SUBMISSION.json` still holds the sentinel" | MOVED → readme-plan §2 (R9) | `readme-plan.md:75` (row 7 grep). R9 binds W2 to render what `SUBMISSION.json` holds on the day. |
| 11 | L25 judge access "takes no account, no login and no credential of ours" | MOVED → `docs/submission/JUDGE-START.md` | `grep -on "Nothing you need is behind a credential" docs/submission/JUDGE-START.md` → `52:Nothing you need is behind a credential` |
| 12 | L25 `docs/deploy/JUDGE-PACK.md` §2 read-only SQL login | MOVED → `docs/deploy/JUDGE-PACK.md` | `grep -on "mainline_judge" docs/deploy/JUDGE-PACK.md` → `107:mainline_judge`, `118:mainline_judge` |
| 13 | L26 video row `UNRESOLVED` | MOVED → readme-plan §2 (R9) | `readme-plan.md:75` (row 7 grep). R9 requires W2 to state that `UNRESOLVED` is a literal, not a forgotten placeholder. |
| 14 | L27 `docs/TOOL-USAGE.md` — every tool and service with a file, a line number and a verdict | MOVED → `docs/TOOL-USAGE.md` | `ls docs/TOOL-USAGE.md` → `docs/TOOL-USAGE.md` (file present). Section E/F territory by readme-plan §2. |
| 15 | L28 repository `https://github.com/Shaugato/mainline`, **public since 2026-08-11**, root `LICENSE` Apache-2.0 | MOVED → readme-plan §2 (§I, W6) | `readme-plan.md:81` `| I | W6 | `## Repository, licence, status, corrections` | 28 |`. Corroborated by `grep -on "apache-2.0" docs/submission/JUDGING-AXES.md` → `476:apache-2.0`. |

## D · Lines 30–46 — the sentinel-disagreement paragraph and the readiness command

Plan **R9** compresses this twelve-line block to three sentences in section C, and **R10**
collects the strikethrough into one `Corrections` table in §I. Every element survives; the
interruption does not.

| # | claim | disposition | evidence |
|---|---|---|---|
| 16 | L30–31 "`UNRESOLVED` is a **literal token**, not a placeholder somebody forgot to replace" | MOVED → readme-plan §2 (R9) | `readme-plan.md:75` (row 7 grep) |
| 17 | L31–33 `SUBMISSION.json` is "the one file in this repository where a submission URL may be written", every field starts as that string | MOVED → readme-plan §2 (R9) | `readme-plan.md:75` (row 7 grep) |
| 18 | L33–34 the struck sentence "Those three fields still hold `UNRESOLVED` because nothing is deployed and no film exists." | MOVED → readme-plan §2 (R10) | `readme-plan.md:81` (row 15 grep) — R10 sends superseded text to the §I `Corrections` table |
| 19 | L34–36 "SUPERSEDED 2026-08-15 … `verdict: PROVEN`, `target_is_local_emulator: false`, eleven requests, no credential [src: evidence/demo/live-beats.json#verdict]" | MOVED → readme-plan §2 (R5) | `readme-plan.md:75` (row 7 grep). R5 makes W2 settle the live status from artefacts; this worker is forbidden a deployment claim. |
| 20 | L36–39 "`demo_url` … still the sentinel … the two disagree until its owner resolves it. **Where they disagree, the wire wins**" | MOVED → readme-plan §2 (R9) | `readme-plan.md:75` (row 7 grep) |
| 21 | L39–42 "`video_url` is genuinely unresolved: the film has not been uploaded" + "A submission checklist that looks finished before it is finished is the one failure mode this repository is built to refuse" | MOVED → readme-plan §2 (R9) | `readme-plan.md:75` (row 7 grep) |
| 22 | L44–46 `python scripts/submission/check_submission_ready.py` "reports **0 rows NOT CHECKED** — because a question nobody could answer is an unresolved row, never a pass" | MOVED → `docs/submission/DEVPOST.md` | `grep -n "NOT CHECKED" docs/submission/DEVPOST.md` → `473:… \`NOT READY\`, \`3\` unresolved rows out of \`10\`, \`0\` NOT CHECKED`; `479:… \`0\` NOT CHECKED, exit \`1\``; `482:**\`NOTRUN\` means NOT CHECKED and is never a pass**` |

## E · Lines 317–321 — the one-sentence version, which is where the corrections are

This block is the source of section A. **Three of its factual details contradict the corpus
answer key and were not carried forward.** Each is recorded below with the artefact that
falsifies it. This worker did not edit `README.md:319` or `DEVPOST.md:151`, which carry the
same three errors — both are reported to the orchestrator instead.

| # | claim | disposition | evidence |
|---|---|---|---|
| 23 | L319 "An engineer raises a routine, entirely defensible change to a compressor alarm setpoint" | **KEPT** | §A ¶4: "Today someone proposes putting the alarm back to 150 °C. They are not careless." |
| 24 | L319 "The system runs `blame` on the clause." | **KEPT** | §B ¶1–2, with `blame` glossed before use. |
| 25 | L319 setpoint "Lowered 150 to 135" | **KEPT**, corrected to the byte-exact corpus form | §A ¶2 quotes `commit_message_2013` with U+2192 and U+2014: *"Lowered 150 → 135 after seal fire INC-2013-044 — two contractors burned."* `CAMERA-STRINGS.yaml:64` header calls the arrow and em dash "load-bearing … Do not 'fix' the punctuation." |
| 26 | L319 "It was written **2013-06-12**" | **DROPPED — factually wrong** | `2013-06-12` is the **incident** date, not the clause date. `spine.json#dates` → `"incident": "2013-06-12"`, `"strengthen_commit": "2013-08-04"`; `anchors.yaml:68` → `{effective_on: 2013-08-04, driver: incident, author: "kestrel:okonjo.d", driven_by_event: INC-2013-044}`; `CAMERA-STRINGS.yaml:69` → `commit_date_display: "2013-08-04"`. §A uses both real dates instead. |
| 27 | L319 "by an author who **left the company in 2017**" | **DROPPED — factually wrong** | `spine.json:15` → `"author_separated": "2021-07-16"`; `anchors.yaml:57` → `author_separated: 2021-07-16`; `CAMERA-STRINGS.yaml:58` → `author_separated: "2021-07-16"`. §A says "In 2021 the engineer leaves the company." **2017 appears in no corpus artefact.** |
| 28 | L319 "signs a disposition against a **thirteen-year-old death**" | **DROPPED — factually wrong and an overclaim inside the fiction** | Nobody dies. `anchors.yaml` `INC-2013-044` block: `severity_actual: 4`, `severity_potential: 4`, with the file's own comment *"Potential is 4, not 5, and deliberately so"*. `CAMERA-STRINGS.yaml:78` → `incident_summary_line: "gland seal fire · P-4102 · Marrindal · two contractors, partial-thickness burns · severity 4"`, and its `forbidden_on_camera` entry reasons *"a real fatality never appears"*. §A says two contractors are burned and claims no death. |
| 29 | L319 "The permit merge is mechanically refused until a named competent person signs a disposition" | **KEPT** | §B ¶2–3. "competent person" is the repository's existing HSG250 usage (`docs/demo/research/r3-operator.md:87`). |
| 30 | L321 "No shipping permit system can express that" | **KEPT** (narrowed) | §A ¶5 says the market **approves the change**, which is the checkable half. "Can express" is a claim about every product on the market that this repository has not measured, so the stronger verb was not carried. |
| 31 | L321 "every one of them is **synchronic** — it gates on the current state of the world" | **KEPT** in plain language; the term MOVED → `docs/submission/DEVPOST.md` | §A ¶5: "Each checks the world as it is now — isolation in place, gas test valid, signature present." `grep -on "synchronic\|diachronic" docs/submission/DEVPOST.md` → `153:synchronic`, `153:diachronic`, `294:diachronic`, `304:diachronic`. Plan **R4** reserves both terms for layer 2 (W3) and this worker's brief bans them outright. |
| 32 | L321 "MAINLINE is **diachronic**: it gates on *ancestry*." | MOVED → readme-plan §2 (§D, W3) | `readme-plan.md:76` `| D | W3 | `## How it works` | 55 |`. Same DEVPOST grep as row 31. |

---

## Two additions section A makes that the current README opening does not contain

Neither is a claim carried over; both are recorded so the ledger is complete in both directions.

1. **The fiction label, inside the first 120 words** — plan **R3** requires it and the current
   opening has it nowhere. The wording is `MUST-NOT-CLAIM.md` §3's own: *"Kestrel Resources is
   fictional, Marrindal is fictional, `INC-2013-044` never happened. The mechanism is real; the
   inputs are authored."*
2. **The clause's renumbering history** — 7.3 → 5.2.1 (2016-11-21) → 9.2.1 (2019-02-19), across
   `PRO-MEC-014` into `STD-ISO-006`. Transcribed from `spine.json#revisions` and
   `CAMERA-STRINGS.yaml:46–50`. It is the concrete reason the reader in the story cannot see the
   fire, which the abstract version of the sentence never supplied.

## Two claims reported to the orchestrator rather than fixed

This worker owns two files and may not edit either destination.

* `README.md:319` carries rows 26, 27 and 28 above. W7 overwrites this line during assembly, so
  it is fixed by construction.
* `docs/submission/DEVPOST.md:151` carries the **same three errors** — `2013-06-12` as the clause
  date, `2017` as the separation year, and "a thirteen-year-old death" — and is **outside every
  worker's scope in this wave** (plan **R16**). It is judge-facing. Flagged for a follow-up owner.
