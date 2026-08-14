<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# DOCS-TRUE-FINAL — make every document true about its own repository, then make submission a form-filling exercise

**Lead:** documents-and-submission · **Date:** 2026-08-14 · **Workers:** exactly 6
**Tree:** `D:/CoackroachDBxAWS/mainline`, HEAD `7535670`, branch `master`, working tree clean,
`HEAD == origin/master`. Public at `github.com/Shaugato/mainline`.
**Interpreter:** `D:/CoackroachDBxAWS/mainline/.venv/Scripts/python.exe`. `uv` is not on PATH;
`uv: command not found` is not a suite result and may not be reported as one.

**This plan applies nothing.** No `terraform apply`. No credential is printed. No password is
rotated. `terraform init/validate/plan/show` and read-only AWS calls only, and no worker in
this wave needs even those.

---

## 0 · WHAT I MEASURED BEFORE DECOMPOSING

Every row is a command this lead ran on this machine today, at HEAD `7535670`, warm. Nothing
below is inherited from the board, from a previous lead's plan, or from a commit message.

### 0.1 The suite baseline — the number every worker must not move

```
$ .venv/Scripts/python.exe -m pytest verticals/mainline/apps/demo-api/tests \
      --crdb=reuse -p no:randomly -q --junitxml=baseline-default.xml
569 passed, 1 skipped in 294.58s (0:04:54)
```

Read from the JUnit XML root element, not from the terminal scroll:

| tests | failures | errors | skipped | time |
|---:|---:|---:|---:|---:|
| **570** | **0** | **0** | **1** | 294.09 s |

The one skip is `test_gate_run.py:1070` — *"jsonschema is not a workspace dependency"*. This
matches the stated baseline of **570 / 569 / 0 / 0** exactly. **It is the BEFORE.** Every
worker reports the same four numbers, from `--junitxml`, AFTER its change. A documents wave
that moves a suite number has broken something it does not own.

### 0.2 The document ratchets — TWO ARE RED, and both reds are mine

```
$ .venv/Scripts/python.exe -m pytest tests/deploy/test_docs_are_true.py \
      tests/release/test_honesty_is_checkable.py tests/deploy/test_cost_model.py \
      --crdb=none -q -p no:randomly
2 failed, 107 passed in 2.60s
```

| # | Ratchet | Verdict | The finding, verbatim |
|---|---|---|---|
| R1 | `test_cost_model.py::test_the_shipping_plan_count_in_the_docs_matches_the_plan_evidence` | **RED** | `docs/submission/JUDGING-AXES.md:122` and `:152` say `'11 to add'`, which no committed plan artefact reports. The artefacts report **24** (`terraform-plan-furl.txt`) and **35** (`terraform-plan-cloudfront.txt`) |
| R2 | `test_cost_model.py::test_line_references_into_the_plan_evidence_point_at_the_plan_line` | **RED** | `docs/submission/JUDGING-AXES.md:152 cites line 339, actual 843` |
| R3 | `test_docs_are_true.py` (whole file) | GREEN | — |
| R4 | `test_honesty_is_checkable.py` (whole file) | GREEN | — |

The R1 assertion message states the tiebreaker itself, and I adopt it verbatim as this wave's
governing sentence: **"Re-read the regenerated plan evidence and correct the documents. Do NOT
edit the evidence file to match the documents."**

### 0.3 The submission checkers

```
$ .venv/Scripts/python.exe scripts/submission/check_submission_ready.py
NOT READY - 2 unresolved rows.   demo_url UNRESOLVED · video_url UNRESOLVED
9 rows checked, 0 NOTRUN.  PASS: remote in sync, repo public, Devpost description,
tool usage (4 CockroachDB tools, 10 AWS services, 21/21 cited artefacts present),
judge access, provenance disclosure, 4d 16h remaining.
```

```
$ .venv/Scripts/python.exe scripts/submission/check_submission_prose.py
submission prose OK  (9 SUB rules, 14 files)
claim_hygiene exited 1 over its own surface:
  FAIL docs/HONESTY.md:724  [HYG-sha-literal]  2dc5c86
  FAIL docs/HONESTY.md:746  [HYG-sha-literal]  2dc5c86
  FAIL docs/HONESTY.md:749  [HYG-sha-literal]  2dc5c86
  ABSENT docs/MECHANISMS.md                      matched no file — not scanned, not passed
  ABSENT verticals/mainline/demo/operator/*.md   matched no file — not scanned, not passed
  ABSENT docs/deck/**/*.{md,html,txt}            matched no file — not scanned, not passed
```

**The two UNRESOLVED rows are correct and must survive this wave.** `demo_url` and `video_url`
are unresolved because the fact they would assert is not true, and `SUBMISSION.json` says so in
its own `a_field_is_resolved_only_when_it_is_proven` key. Nobody writes a URL into that file in
this wave. Resolving them by invention is the single failure that file exists to prevent.

### 0.4 The evidence that exists, and the evidence that does not

| Claim | Committed artefact | State |
|---|---|---|
| Gate proof, LOCAL, caveat-free | `evidence/gate-refusal/proof-20260814T032418Z.json` | **verdict `PROVEN`**, `caveats: []`, `2026-08-14T03:24:18Z`, database `w_qr_gate_refusal_proof`, CockroachDB CCL v26.2.5 |
| Migration chain applied to Cloud | `evidence/deploy/cloud-chain.json` | **`APPLIED`** against `mainline-dev-31219.j77.aws-ap-southeast-1.cockroachlabs.cloud:26257/defaultdb`, database `mainline_demo` |
| Cloud seeded and refusing | `evidence/deploy/cloud-seed.json` | **`SEEDED AND REFUSABLE`**, `2026-08-14T04:27:30Z`; verification `REFUSED / 23514 / gate_closed_when_issued`, `nothing_persisted: true` |
| HTTP acceptance over the real handler | `evidence/deploy/acceptance.json` | **`NOT PROVEN`**, `2026-08-13T01:47:58Z`, `url http://127.0.0.1:8764`, `target_is_local_emulator: true` |
| **Cloud `defeater_option` 0→6, `ledger_leaf` 0→4, `ledger_node` 0→3, `tree_size` 4** | **NONE** | `cloud-seed.json`'s `row_counts` names 27 tables and **none of those three**; `grep -c defeater_option evidence/deploy/cloud-seed.json` = **0** |
| **`POST /v1/demo/gate-run → 200, verdict PROVEN` against Cloud** | **NONE** | `git show --stat 7535670` changed exactly two files: `cloud-seed.json` and its `.license`. No artefact anywhere in `evidence/` records a Cloud gate-run |

### 0.5 The documents that are false about this tree, found by reading

| Document | The false sentence | What the tree says |
|---|---|---|
| `docs/STATE-OF-THE-BUILD.md:20-30` | *"`mainline.defeater_option` still holds **zero rows**… A judge still cannot sign… **NO-GO for the sixth time**"*, and *"527 passed / 30 failed / 13 errors"* | `defeater_option` is seeded in three places; the suite is **570 / 569 / 0 / 0**; a judge can sign |
| `docs/STATE-OF-THE-BUILD.md:8` | *"against local `HEAD` `eefae1c` plus 37 modified and 13 untracked paths"* | HEAD is `7535670`, two commits later, working tree **clean** |
| `docs/state-of-the-build.html:231,488` | `NO-GO` rendered as the headline verdict | same |
| `docs/HONESTY.md:889` | *"The demo has been driven end to end, **twice**, and the verdict is **NOT PROVEN both times**"* | Still true **of `acceptance.json`**. False as a statement about the build: `proof-20260814T032418Z.json` is `PROVEN` and caveat-free |
| `docs/HONESTY.md:948` | *"Nothing has ever run against CockroachDB Cloud in CI"* | **Still true of CI.** But two Cloud artefacts now exist and this bullet does not name them |
| `docs/HONESTY.md` / `DEMO-HONESTY.md` | — | **Neither declares the 2027 receipt expiry.** `grep -n 2027` over both returns **nothing**, while `demo_permit.sql:416` seeds `expires_at = 2027-01-01` and `:400` says it is chosen *"so that the admission beat keeps working for every judge"*. That is a staged element, undeclared |
| `docs/submission/JUDGING-AXES.md:122,152` | `Plan: 11 to add` · plan line `339` · `acceptance.json generated_at 2026-08-11T05:43:54Z` with `4` failures | **24** to add · line **843** · `2026-08-13T01:47:58Z` |
| `docs/submission/VIDEO-KIT.md:493,541` | `BEAT 4 SKIPS AFTER 2026-08-12T18:37:01Z (1h 59m from now)` | That instant is **two days in the past**. The gate the kit calls *"the quietest way this shoot fails"* is already blown for anyone reading the worked example |
| `docs/submission/VIDEO-KIT.md:809` | *"Beat 1 has neither a main path nor its written fallback today"* | Written before the signature path worked; must be re-measured, not re-typed |

The Sydney/Singapore split **is** declared, correctly, in both honesty documents
(`HONESTY.md:987-997`, `DEMO-HONESTY.md:72-73`). It needs verification, not repair.

---

## 1 · RULINGS

The brief poses questions. Each is answered here in writing, with the authority named. A
worker that disagrees with a ruling raises it to this lead; it does not quietly decide
otherwise.

### RULING 1 — A commit message is not evidence. The Cloud gate-run may not be printed as PROVEN.

**Question.** The board states as already-true: *"through the REAL handler against Cloud,
`POST /v1/demo/gate-run → 200, verdict PROVEN`"* and *"`defeater_option` 0→6, `ledger_leaf`
0→4, `ledger_node` 0→3, checkpoint `tree_size` now 4"*. May the documents print those?

**Ruling.** **No — not as measurements.** No committed artefact carries any of them (§0.4).
The only place they exist is the body of commit `7535670`, whose diff touched two files, and
neither contains a `defeater_option` count or a gate-run transcript.

**Authority.** `verticals/mainline/demo/DEMO-HONESTY.md`, this repository's own governing
sentence: **"A measurement always outranks a statement about a measurement."** And
`docs/HONESTY.md`'s rule that a transcript *"moves by re-running the prover, never by editing
the file: a recorded transcript edited to agree with a document has stopped being evidence and
started being a forgery."* A commit message is a statement about a measurement. Printing it as
a measurement is the same move as editing the transcript, one indirection out.

**What the documents say instead**, verbatim, so no two workers word it differently:

> **CockroachDB Cloud carries the demo world, and the gate refuses there.** The migration chain
> is `APPLIED` and the seeded world is `SEEDED AND REFUSABLE` against
> `mainline-dev-31219.j77.aws-ap-southeast-1.cockroachlabs.cloud`, database `mainline_demo`,
> CockroachDB CCL v26.2.5 — the refusal observed on Cloud is `23514`
> `gate_closed_when_issued`, with `nothing_persisted: true`
> [src: `evidence/deploy/cloud-chain.json#outcome`, `evidence/deploy/cloud-seed.json#verdict`,
> `#verification`].
>
> **The four-beat run through the HTTP handler has NOT been recorded against Cloud.** The
> operator reports it in the body of commit `7535670`; that commit's diff carries no such
> artefact, and `evidence/` holds none. **OWED:** re-run `scripts/deploy/…` against Cloud with
> `--out evidence/deploy/cloud-gate-run.json`, and only then may a Cloud `PROVEN` appear on
> this page. Until it exists, the only `PROVEN` this repository holds is
> `evidence/gate-refusal/proof-20260814T032418Z.json`, and it is **local**
> (`cluster.database = w_qr_gate_refusal_proof`).

This is not pessimism. It is the product. A judge who checks one claim and finds it
uncorroborated discounts every other claim on the page.

### RULING 2 — `acceptance.json` is not edited, is not deleted, and is not averaged away.

**Question.** `HONESTY.md:889` says the demo is `NOT PROVEN` twice, and the build now has a
`PROVEN`. Which side moves?

**Ruling.** **Neither the artefact nor the finding moves. The framing moves.** `acceptance.json`
still reads `NOT PROVEN` at `2026-08-13T01:47:58Z` against `http://127.0.0.1:8764` with
`target_is_local_emulator: true`, and that is a true fact about the HTTP surface. The section is
**kept**, its verdict is **kept**, and it gains a dated third paragraph that names what has since
landed, what artefact carries it, and which surface each artefact speaks about. The one sentence
that must change is the closing rule *"Until the two agree, only the first may be cited as
proven"* — it is still the right rule, and the SQL-level proof it points at is now
`proof-20260814T032418Z.json` rather than the August-10 one.

**Authority.** `docs/deploy/COST-BOUND.md`'s preservation rule, already enforced by
`tests/deploy/test_docs_are_true.py`: *"Where a sentence has since become false, it is struck
through or annotated in place, never removed. A claim deleted is not a claim corrected, and the
corrections are only checkable against the claims they correct."*

### RULING 3 — Live documents are re-derived. Dated records are annotated, never re-typed.

**Question.** `grep -rn "11 to add" docs/` returns hits in ~14 files. Which get corrected?

**Ruling.** Only documents on the **live surface**. `docs/leads/`, `docs/diagnosis/`,
`docs/verify/`, `docs/decisions/`, `docs/adr/` and `docs/upstream/` are **dated records of what
was true on a date**. A worker who re-types a number inside one of them is falsifying history to
obtain a green, and is doing the thing this project sells against.

**Authority.** Already ratified in the tree, in the comment above `LIVE_DOCS` in
`tests/deploy/test_cost_model.py:70-72`: *"`docs/verify/` and `docs/diagnosis/` are deliberately
NOT here — they are records of what was true on a date, and a ratchet that demanded they be
re-typed would be demanding that history be falsified."* I extend the same status to
`docs/leads/`, `docs/decisions/`, `docs/adr/` and `docs/upstream/` on the identical reasoning,
and record the extension here rather than leaving it to be inferred.

**The one exception is `docs/leads/cost-bound-plan.md`**, named by the board as item 5. It is a
dated record, so its M1–M17 digits stay. What it owes is the **ANNOTATED** block it already
carries being *complete* — §0.5's audit of it, not a rewrite. D4 owns that distinction.

### RULING 4 — The aperture is widened, never narrowed. `LIVE_DOCS` gains three entries.

**Question.** `docs/CI-STATE.md`, `docs/submission/VIDEO-KIT.md` and `docs/state-of-the-build.html`
are policed by **no** ratchet. Is that acceptable?

**Ruling.** **No.** All three are added to `LIVE_DOCS` in `tests/deploy/test_cost_model.py`.
This **raises** the aperture; the file's own `test_live_docs_covers_the_documents_this_wave_moved`
already forbids removing an entry, calling removal *"lowering the aperture to obtain a green,
which is the same move as lowering a floor."* Widening is the sanctioned direction. **Expect new
reds**, and expect them to be real: that is the point.

D1 performs the widening as its first act, before any prose is written, and posts the resulting
failure list. No worker may narrow it back to make its own document pass.

### RULING 5 — The three `HYG-sha-literal` reds in `HONESTY.md` are closed with the rule's own escape hatch, and the rule is not touched.

**Question.** `check_submission_prose.py` reports 3 `[HYG-sha-literal]` violations at
`docs/HONESTY.md:724,746,749`, all the literal `2dc5c86`. A previous lead put HONESTY.md *"out of
scope under RULING 8"* (`evidence/deploy/lead/plan-repro-fresh-clone.json`). It is in scope now.

**Ruling.** **Three options exist and two are forbidden.**

* ❌ **Add `docs/HONESTY.md` to `NOT_REAPPLIED` or to any scope list.** That is switching a rule
  off to obtain a green. Forbidden outright.
* ❌ **Delete the SHA.** Lines 746 and 749 are `$ git grep -n "demo-api" 2dc5c86 -- .github/workflows/`
  and `$ git grep -c 'docker run -d' 2dc5c86`. A reader reproduces those commands *only* with the
  SHA in them. Deleting it destroys the reproduction and lowers the document's evidential
  standard — the same failure class, aimed at the document instead of the test.
* ✅ **Use `claim-hygiene: quoting`**, the rule's own escape hatch, defined at
  `scripts/demo/claim_hygiene.py:298-300` as *"The visible escape hatch. A line carrying this
  marker is quoting a banned phrase on purpose"*, and consumed at line 378 by
  `quoting = bool(INLINE_EXEMPT.search(line)) or quoting_indent is not None`.

**Authority.** The rule ships the hatch; using a mechanism the rule provides is not weakening the
rule. The hatch survives in the diff, which is why it was built that way. The rule's stated
rationale — *"The film shows whatever the DAG produced; no SHA is ever spoken or written"* — is
about the **film and the deck**, and `check_submission_prose.py:366-373` says so in its own
comment. `docs/HONESTY.md` is a provenance document, the same species as `DISCLOSURE.md`, which
the checker already scopes out for exactly this reason.

**Conditions, all three mandatory.** (a) Only the three offending lines are marked, one marker
each, never a file-wide or block-wide sweep. (b) A sentence in `HONESTY.md` itself records that
the marker is there, why, and that the SHA is preserved for reproduction — an exemption nobody
can see is an exemption somebody switched off. (c) `python scripts/demo/claim_hygiene.py --self-test`
is re-run and must still fire on **all four** planted families
(`MNC-01-rls-vs-rogue-admin`, `MNC-15-upstream-merge`, `HYG-bare-invariant`, `HYG-sha-literal`).
If the self-test stops firing on `HYG-sha-literal`, the hatch disarmed the scanner and the change
is reverted on the spot.

### RULING 6 — The three `ABSENT` rows are answered by disclosure, not by creating decoy files.

**Question.** `claim_hygiene` reports `docs/MECHANISMS.md`, `verticals/mainline/demo/operator/*.md`
and `docs/deck/**` as *"matched no file — not scanned, and therefore not passed."*

**Ruling.** **Do not create empty files to satisfy globs.** A file created to make a scanner say
`scanned` instead of `ABSENT` is a vacuous green, and this repository has a workflow lane
(`cluster-lane-bites`) whose entire existence is the argument against those. The correct answer
is a short register entry in `docs/submission/PUBLIC-READINESS.md` naming each absent surface, why
it does not exist (there is no deck and no operator runbook in this project), and that `ABSENT` is
therefore the honest output. D6 owns it.

### RULING 7 — `demo_url` and `video_url` stay `UNRESOLVED`, and the two-hour vs 2027 receipt split is declared, not reconciled.

**Question (a).** May a worker resolve either URL? **No.** Neither fact is true. The `UNRESOLVED`
sentinel is the design.

**Question (b).** `demo_permit.sql:416` seeds `expires_at = 2027-01-01`; `seed_demo_state.py:161`
issues `now() + INTERVAL '2 hours'`. Two expiries. Which is authoritative?

**Ruling.** **Both, for different databases, and the split is the thing that must be written
down.** `VIDEO-KIT.md:663` (§B.9) already establishes that the film and the demo-api world are two
databases on purpose. So: the **2027-01-01** receipt is the demo-api / judge path — a staged
element chosen so *"the admission beat keeps working for every judge"* (`demo_permit.sql:400`),
and it is **undeclared in both honesty documents**, which is a real gap D2 closes. The **two-hour**
receipt is the film path, and `VIDEO-KIT.md`'s worked example prints an instant now two days past,
which D6 re-derives live rather than re-typing. Nobody changes a seed. Nobody changes an expiry.
**The seed is authoritative; the documents are checked against it.**

---

## 2 · THE NO-SHORTCUT RULE — reproduced in every brief below, and binding on all six

> **When a test and the code disagree, ask which side is AUTHORITATIVE, never which is easier to
> move.** The console and the committed JSON schemas are authoritative for what the demo must
> carry; the seed and the tests are BOTH checked against them, and either may lose. Never lower a
> floor, raise a skip ceiling, add a known-red exemption, or delete a claim to obtain a green.
> Never edit an evidence artefact so a document agrees with it — correct the document. Never
> re-type a digit inside a dated record to make history agree with today — annotate it in place.
> `continue-on-error` and `|| true` are banned. Never print a credential. Never weaken
> `HONESTY.md`, `CI-STATE.md`, a ratchet or an assertion. Never run `terraform apply`.
> **The re-verification's first check is a `git diff` over every seed, fixture, ceiling and
> expected value, asking which side moved and why that one was derived.** If your change makes
> the answer "the authoritative side moved", you have failed regardless of the colour of the board.

---

## 3 · THE SIX WORKERS — disjoint, literally enumerated paths

No path appears under two workers. `docs/leads/docs-true-final.md` is this lead's and is written
by nobody else. `docs/leads/`, `docs/diagnosis/`, `docs/verify/`, `docs/decisions/`, `docs/adr/`
and `docs/upstream/` are **read-only for every worker** except D4's single named exception.

| Worker | Title | Owns | Depends on |
|---|---|---|---|
| **D1** | The verdict page, and the aperture that polices it | `docs/STATE-OF-THE-BUILD.md`, `docs/state-of-the-build.html`, `tests/deploy/test_cost_model.py`, `tests/deploy/test_docs_are_true.py` | — |
| **D2** | The two honesty documents | `docs/HONESTY.md`, `verticals/mainline/demo/DEMO-HONESTY.md` | — |
| **D3** | The board, and the CI narrative | `docs/CI-STATE.md`, `docs/ci/**`, `docs/release/**` | D1 |
| **D4** | Item 5 — cost, latency, and the deploy surface | `docs/deploy/**`, `docs/leads/cost-bound-plan.md` | — |
| **D5** | Submission core, mapped to the five axes | `docs/submission/DEVPOST.md`, `RULES-MATRIX.md`, `JUDGING-AXES.md`, `SUBMISSION.json`, `docs/TOOL-USAGE.md` | D1, D2 |
| **D6** | The video kit, and the rest of `docs/submission/` | `docs/submission/VIDEO-KIT.md`, `JUDGE-START.md`, `FIRST-FIVE-MINUTES.md`, `MUST-NOT-CLAIM.md`, `PUBLIC-READINESS.md`, `RUNBOOK.md`, `DISCLOSURE.md`, `DISCLOSURE-DECISIONS.yaml`, `LICENSING.md`, `LICENCE-CENSUS.md`, `PUBLIC-FLIP-CHECKLIST.md`, `verticals/mainline/demo/script/SHOT-LIST.yaml` | D1, D2 |

Full briefs are carried in this wave's structured output, one per worker, each self-contained and
each repeating §2 verbatim.

---

## 4 · WHAT EVERY WORKER RUNS, AND REPORTS

Before its first edit and after its last, every worker runs and pastes all four:

```bash
V=D:/CoackroachDBxAWS/mainline/.venv/Scripts/python.exe

# 1 — the suite. BEFORE is 570 tests / 569 passed / 1 skipped / 0 failed / 0 errors.
$V -m pytest verticals/mainline/apps/demo-api/tests --crdb=reuse -q \
     --junitxml=out/qa/<worker>-after.xml
# read the four numbers from the XML root element, never from the scroll.
# the suite is silent for minutes. DO NOT KILL IT.

# 2 — the document ratchets. BEFORE is 2 failed, 107 passed.
$V -m pytest tests/deploy/test_docs_are_true.py tests/release/test_honesty_is_checkable.py \
     tests/deploy/test_cost_model.py --crdb=none -q -p no:randomly

# 3 — submission readiness. BEFORE is NOT READY, exactly 2 rows, 0 NOTRUN.
$V scripts/submission/check_submission_ready.py

# 4 — submission prose. BEFORE is: SUB rules clean; claim_hygiene 3 HONESTY.md reds, 3 ABSENT.
$V scripts/submission/check_submission_prose.py
```

**A worker reports the numbers even when they are unflattering, and especially then.** A wave
whose documents are about honesty and whose report is not is the joke this product is about.

---

## 5 · THE DEFINITION OF DONE FOR THE WAVE

1. Suite still **570 / 569 / 1 / 0 / 0** from `--junitxml`, default order **and** randomised.
2. `test_docs_are_true.py` + `test_honesty_is_checkable.py` + `test_cost_model.py`: **0 failed**,
   against a `LIVE_DOCS` that is **three entries longer** than it is today.
3. `check_submission_prose.py`: **0** `[HYG-…]` reds; the 3 `ABSENT` rows still printed, and now
   answered in `PUBLIC-READINESS.md`.
4. `check_submission_ready.py`: **still NOT READY, still exactly 2 rows** — `demo_url` and
   `video_url`. Any other count means someone invented a fact.
5. No `git diff` line anywhere in `evidence/`, `verticals/mainline/db/seeds/`, `qa/`, `infra/`,
   `.github/workflows/`, or any `packages/**/src` — this is a documents wave.
6. The Cloud gate-run is recorded as **OWED**, in RULING 1's exact words, in
   `STATE-OF-THE-BUILD.md`, `HONESTY.md` and `CI-STATE.md`, worded identically in all three.
7. The 2027 receipt expiry and the Sydney/Singapore split are both declared in **both**
   `HONESTY.md` and `DEMO-HONESTY.md`.
8. `VIDEO-KIT.md` is beat-by-beat under **3:00** with timings, exact commands, seeded state, shot
   list and the sentences that may not be said — re-derived against the signature path as it works
   today. **The video is not produced.** Nobody records anything.
