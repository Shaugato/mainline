<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# README PLAN — the front door, rebuilt in three layers

**Lead: README. Wave of 2026-08-17. Deadline 2026-08-18 17:00 EDT.**

The founder's sentence is the requirement: *"Even after going through your briefing, I'm
finding a very hard time to understand."* The current `README.md` is 475 lines and 33 638
bytes. Almost every claim in it is true and sourced. A stranger arriving from Devpost meets,
in the first forty lines, a blame pointer, a protected branch, a literal `UNRESOLVED` token,
a superseded paragraph with strikethrough, and a disagreement between a JSON file and a web
page — before learning what the product is for.

**The fix is layering, not simplifying.** Nothing gets vaguer. What changes is the order in
which a reader meets things.

* **Layer 1** (sections A–C) — a non-technical reader knows the problem, why it matters, what
  we built and what to click, in sixty seconds. Evidence paths are kept but move to GitHub
  footnotes so they stop interrupting the sentence.
* **Layer 2** (sections D–F) — a technical reader sees the constraint, the trigger, the
  SQLSTATE, the two measured use cases, the platform in its real states, and what we found
  out about CockroachDB along the way.
* **Layer 3** (sections G–I) — a reviewer verifying a claim reaches the file, the line, the
  transcript. **This layer already exists and is not weakened.** It is compressed by moving
  archaeology into one `Corrections` block, not by dropping claims.

---

## 0 · The two rules that go in every worker brief, verbatim

> **THE READABILITY BAR.** A reader who has never heard of a `CHECK` constraint must be able
> to restate the problem in their own words after sixty seconds on this page. No term is used
> before it is defined — `projection`, `blame ancestry`, `obligation`, `disposition`, `epoch`,
> `SQLSTATE`, `minimal unsatisfiable subset` each get a plain-language gloss of twelve words
> or fewer at first use, or do not appear. Concrete before abstract: a person, a situation, a
> consequence — never "a diachronic gate over ancestry" as an opening move.

> **THE NO-OVERCLAIM RULE.** Never claim anything in a better state than it is. Agent Skills
> is **DESIGNED**, not exercised. Bedrock runs **in this repository and not in the demo
> request path**. Use case two has **no admission beat** and says so. Five AWS rows are
> **DESIGNED**, CloudFront is **blocked by an account verification hold**, and the conformance
> suite **has never been demonstrated**. These scopings are why the rest is believable. If a
> sentence cannot be both true and simple, write two sentences — never one softer one. No
> marketing voice: `revolutionary`, `seamless`, `unprecedented`, `cutting-edge`,
> `game-changing`, `powerful`, `robust`, `effortlessly`, `blazing` are banned outright.

---

## 1 · Method — six fragment authors, one assembler

`README.md` is one file, so seven workers cannot own it. Six workers write **fragments** into
literally-enumerated, disjoint paths under `docs/submission/readme-parts/`. The seventh —
and only the seventh — writes `README.md`, by concatenating the fragments in the order fixed
below and then running the mechanical checks.

Every fragment author also writes a **claim ledger** beside its fragment. This is the single
control against the failure mode named in the brief: *deleting a precise claim to make room
for a friendly one*.

---

## 2 · The assembly order and the line budget

`README.md` is assembled in exactly this order. Section letters are planning labels; the
rendered headings are the ones in the third column.

| § | worker | rendered heading | budget |
|---|---|---|---|
| — | W7 | SPDX comment block, then `# MAINLINE` | 6 |
| A | W1 | *(no heading — the opening runs straight from the title)* | 30 |
| B | W1 | `## What this is` | 18 |
| C | W2 | `## See it refuse — live, with no account` | 55 |
| D | W3 | `## How it works` | 55 |
| E | W4 | `## What it is built on` | 45 |
| F | W5 | `## How we got here, and what we found out about CockroachDB` | 40 |
| G | W6 | `## Check us — clone it and reproduce the refusal` | 45 |
| H | W6 | `## What we are not claiming` | 22 |
| I | W6 | `## Repository, licence, status, corrections` | 28 |

**Ceilings: 340 lines and 26 000 bytes for the whole file.** Layer 1 (title through the end
of C) must be **at or under 109 lines**, because that is what sixty seconds buys. A worker
that cannot fit its budget stops and reports rather than overrunning; W7 reconciles.

---

## 3 · Rulings — what the brief left open, decided here

**R1 · Length.** `README.md` ≤ 340 lines and ≤ 26 000 bytes. Per-section budgets in §2 are
binding. Precision is never traded for the budget; the budget is met by moving archaeology
into §I and by ending sentences.

**R2 · Nothing is deleted without a home.** Every claim, number or citation present in the
current `README.md` and absent from a worker's fragment is recorded in that worker's
`*.claims.md` ledger with exactly one disposition: `KEPT` (present in the fragment),
`MOVED` (a named existing file already contains it, verified by a grep the ledger prints), or
`DROPPED` (with the reason). **A worker may not edit the destination file** — if a claim has
no existing home, it is `KEPT`. A `MOVED` row without a verified grep is a `KEPT`.

**R3 · The opening scenario.** The opening is the compressor alarm setpoint story that
already exists at `README.md:319` — clause written `2013-06-12`, incident `INC-2013-044`,
author left the company in 2017, permit raised today. **It is labelled as authored fiction
inside the first 120 words**, in `docs/submission/MUST-NOT-CLAIM.md` §3's own wording:
*"Kestrel Resources is fictional, Marrindal is fictional, `INC-2013-044` never happened. The
mechanism is real; the inputs are authored."* Do not invent an "eighteen months" or any other
interval — use the corpus's real dates. Do not use the second scenario (the 2019 incident in
`evidence/demo/memory-loop.json`) in the opening; one story, told once.

**R4 · Glossary discipline.** These terms may appear, each glossed at first use in ≤ 12
words: `CHECK constraint`, `projection`, `blame ancestry`, `obligation`, `disposition`,
`epoch`, `SQLSTATE`, `minimal unsatisfiable subset`, `changefeed`, `vector index`.
`diachronic` and `synchronic` may each appear **once**, in layer 2, glossed inline.
**Banned from `README.md` entirely**: `canonicalisation`, `defeater`, `archival bond`,
`fixity`, `MUS` as a bare acronym, `C-SPANN` outside the platform table.

**R5 · Use case two's live status — the sharpest trap in this wave.** The committed artefacts
disagree. `evidence/deploy/cr-gate-live.json` and `qa/cr-gate-live.json`
(`2026-08-16T04:41–04:42Z`) record `POST /v1/demo/cr-gate-run` answering **404** on the live
origin and write `verdict: "UNANSWERABLE"`. `qa/live2.json` (`generated_at
2026-08-16T21:11:57Z`) records `verdict: "PROVEN"` with the CR beats — `00000`,
`23514 cr_gate_closed_when_merged`, `P0001 mainline.fn_cr_merge_gate` — and **the live origin
hostname does not appear in that file**. W2 resolves this from the artefacts plus one
read-only HTTP probe, and writes the sentence the newest evidence actually supports, naming
the artefact and its timestamp. **No orchestrator message, and no sentence in this plan, is
evidence that use case two answers over the public origin.** If it cannot be settled, publish
both readings with their dates and say which is newer — that is a stronger paragraph than a
guess, and it is precisely `MUST-NOT-CLAIM` §12.

**R6 · Network.** Workers may issue **read-only `GET`** requests to the demo origin
(`/v1/health`, and a `GET` against a `POST`-only route to distinguish `404 not deployed` from
`405 method not allowed`). **No `POST`. No `terraform`. No AWS API call. No SSM write. No
redeploy. No credential printed.** Any HTTP observation is transcribed into the worker's own
fragment or ledger — never into `evidence/` or `qa/`.

**R7 · No proof-script runs.** Nobody runs `scripts/proof/*.py`, `seed_demo_state.py` or the
regression guard. They write into `evidence/` and `qa/`, other waves are running concurrently,
and the baseline (`1070 collected / 1069 passed / 0 failed / 0 errors`, gate proof `PROVEN`,
`DEFAULT_MAX_RESPONSE_BYTES == 136 * 1024`) must not move. Numbers are verified by **reading
committed artefacts**, which is what the README asks a judge to do anyway.

**R8 · Mechanical invariants the new file must preserve.** These are enforced by existing
tests and scripts; breaking one is a regression:

1. A copy-paste block containing `git clone -c core.longpaths=true https://github.com/Shaugato/mainline.git` — `scripts/submission/judge_dry_run.py:805` requires the flag.
2. The four documented commands, both columns, present verbatim — `judge_dry_run.py:834,917`.
3. Zero `ARCHITECTURE.md` §11.7 must-not-claim strings — `tests/boundary/test_ci_greps.py::scan_must_not_claim`, which treats a missing README as violation `GREP-CLAIM-NO-README`.
4. `python scripts/submission/check_submission_prose.py` clean on `README.md` (`SUB-01`…`SUB-09`).
5. The SPDX comment block stays as the first four lines.
6. Every relative link resolves to a path that exists.

**R9 · The submission table.** The Devpost-required rows (demo URL, judge access, video,
tool usage, repository and licence) open section C. `docs/submission/SUBMISSION.json` is
**not edited** — the README renders what that file holds today. If `video_url` is still the
literal token `UNRESOLVED`, the row says so in one sentence plus one sentence explaining that
`UNRESOLVED` is a literal, not a forgotten placeholder. The current twelve-line explanation
of the sentinel disagreement compresses to three sentences; the long form is `MOVED` to
`docs/submission/JUDGE-START.md` only if a grep proves it already lives there.

**R10 · Archaeology.** The current README carries superseded paragraphs inline with
strikethrough (the 214-character clone path, the Bedrock-only claim). Self-correction is part
of this project's credibility and is **not** dropped — it is **collected** into one
`Corrections` table at the end of §I: one row each, *what this page used to say* /
*what is true* / *evidence*. Maximum 15 lines. The correction survives; the interruption does
not.

**R11 · Evidence placement.** Layer 1 uses GitHub footnotes (`[^src-health]`) collected at the
end of section C, so no sentence in the first sixty seconds is interrupted by a bracketed
path. Layers 2 and 3 keep inline `[src: path#pointer]` exactly as today. Every factual claim
in layer 1 still carries its evidence path — moved, not removed.

**R12 · Prose limits.** In layers 1 and 2: no sentence over 35 words; mean sentence length in
section A at or under 22 words; no acronym unexpanded at first use; no nested parenthetical.

**R13 · The two use cases are presented identically**, five fields each: the plain-language
name, who is on the screen, what a judge presses, the exact SQLSTATE with its constraint or
function name, and the artefact. Use case two additionally states its **two absent beats** —
`admission_beat: null` and `kernel_procedure_beat: null`, each with the reason the payload
itself declares. Omitting them would be the exact overclaim this project exists to refuse.

**R14 · Platform scoping sentences are mandatory**, not optional garnish: Agent Skills is
DESIGNED with no captured run; Bedrock executes in this repository and **not** in the demo
request path; five AWS rows are DESIGNED; CloudFront is blocked by an account verification
hold with the verbatim `AccessDenied` string cited to `docs/deploy/RUNBOOK.md` Appendix A.

**R15 · The parts directory stays.** W7 leaves `docs/submission/readme-parts/` in the tree and
reports to the orchestrator that it is a build input which may be removed before commit.
**Nobody commits.**

**R16 · Scope fence.** No worker touches any file outside its enumerated paths. Other leads
are rewriting `docs/HONESTY.md`, `docs/TOOL-USAGE.md`, the architecture documents and the
submission materials in this same wave. We **link** to those paths — paths are stable — and we
**never** edit them. `README.md` belongs to this lead and to worker W7 alone.

**R17 · Judgement of taste.** Where a fragment author believes a claim genuinely cannot be
made readable, the resolution is two sentences — a plain one and a precise one — not one
blurred one. Where the author believes the README is the wrong home for a claim, the ledger
records `KEPT` and a note; W7 does not adjudicate content, only budget and invariants.

---

## 4 · The workers

| id | title | owns |
|---|---|---|
| W1 | The sixty seconds | `docs/submission/readme-parts/01-opening.md`, `01-opening.claims.md` |
| W2 | The live demo and the two use cases | `docs/submission/readme-parts/02-demo.md`, `02-demo.claims.md` |
| W3 | The mechanism | `docs/submission/readme-parts/03-mechanism.md`, `03-mechanism.claims.md` |
| W4 | The platform, in its measured states | `docs/submission/readme-parts/04-platform.md`, `04-platform.claims.md` |
| W5 | The story and the critique | `docs/submission/readme-parts/05-findings.md`, `05-findings.claims.md` |
| W6 | Verification, honesty, licence, corrections | `docs/submission/readme-parts/06-verify.md`, `06-verify.claims.md` |
| W7 | Assembly and the readability gate | `README.md`, `scripts/submission/check_readme_readability.py`, `docs/submission/readme-parts/07-assembly-report.md` |

Full briefs are carried in the structured output that accompanies this plan; each is
self-contained and repeats the two rules in §0.

---

## 5 · Definition of done for the wave

1. `README.md` exists, is ≤ 340 lines and ≤ 26 000 bytes, and its layer 1 is ≤ 109 lines.
2. `python scripts/submission/check_submission_prose.py` reports no violation in `README.md`.
3. `python -m pytest tests/boundary/test_ci_greps.py -q` passes.
4. The `core.longpaths` clone line and the four documented commands are present verbatim.
5. Every relative link in `README.md` resolves.
6. Six claim ledgers exist, and every `MOVED` row carries the grep that proves its destination.
7. `scripts/submission/check_readme_readability.py --self-test` plants one violation per family and the checker fires on each; run without the flag it exits 0 on `README.md`.
8. Nothing under `evidence/`, `qa/`, `infra/`, `verticals/`, `spec/` or `packages/` changed.
9. No commit.
