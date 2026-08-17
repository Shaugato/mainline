<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# 02-demo.claims.md — the claim ledger for section C

Ledger for `docs/submission/readme-parts/02-demo.md`, written under `readme-plan.md` R2. It
accounts for every claim, number and citation in the **submission table** (`README.md:20–46`),
the **live-demo section** (`README.md:48–79`) and the **memory-loop section**
(`README.md:81–104`) of the `README.md` at `HEAD 9e91467`, 475 lines.

Dispositions are `KEPT` (present in the fragment), `MOVED` (a named existing file already
carries it, and the grep that proves it is printed here), or `DROPPED` (with the reason). No
destination file was edited. Section C is 44 lines against a 55-line budget.

---

## 1 · The submission table — `README.md:20–46`

| # | claim in the current README | disposition | where / why |
|---|---|---|---|
| 1 | Demo URL `https://ihuuyvm4z6nfuktihnkey77fpy0eyrhj.lambda-url.ap-southeast-1.on.aws` | **KEPT** | first row of the fragment's table, rendered from `SUBMISSION.json#demo_url` |
| 2 | that URL answers `ok: true`, database `mainline_demo`, deploy chain `271` of `271` | **MOVED** | `docs/demo/LIVE-BEATS.md:35` — `\| target \| ok: true · mainline_demo · deploy chain **271 of 271** · migrations_applied: 0 \|`. The fragment keeps a fresher, weaker form of the same fact: `GET /v1/health` answering `200` with `ok: true` at `server_date 2026-08-17T15:16:05Z`, measured while writing |
| 3 | "`SUBMISSION.json` still holds the sentinel" *(said of `demo_url`)* | **DROPPED — falsified** | `SUBMISSION.json#demo_url` holds the origin, and `notes.demo_url` opens `RESOLVED 2026-08-16`. `docs/submission/DEVPOST.md:259` records the same supersession. Per R9 the fragment renders what the file holds today, so only `video_url` still carries the token |
| 4 | judge access — no account, no login, no credential of ours | **KEPT** | second row of the table, with footnote `[^src-open]` |
| 5 | `docs/demo/JUDGE-90-SECONDS.md` as the ninety-second walk | **MOVED** | `docs/submission/JUDGE-START.md:19` — ``[`docs/demo/JUDGE-90-SECONDS.md`](../demo/JUDGE-90-SECONDS.md) is one row per frame``. Section A links `JUDGE-START.md`; the walk is one hop away rather than two links in a sixty-second table |
| 6 | read-only SQL login is `docs/deploy/JUDGE-PACK.md` §2 | **KEPT** | same table row, named as a *separate* path from the demo origin |
| 7 | video row reads `UNRESOLVED` | **KEPT** | third table row |
| 8 | `docs/TOOL-USAGE.md` carries every tool and service with file, line and verdict | **KEPT** | fourth table row, wording preserved |
| 9 | repository public since 2026-08-11, root `LICENSE` Apache-2.0 | **KEPT** | fifth table row |
| 10 | `UNRESOLVED` is a **literal token**, not a forgotten placeholder | **KEPT** | the paragraph under the table, one sentence |
| 11 | the rows render from `SUBMISSION.json`, the one file where a submission URL may be written, and every field starts life as that string | **KEPT** | same paragraph, plus "this page never edits it" for R9 |
| 12 | ~~"those three fields still hold `UNRESOLVED` because nothing is deployed and no film exists"~~ | **DROPPED — archaeology** | superseded strikethrough. R10 collects self-corrections into the single `Corrections` table at the end of §I, which is W6's file. Not re-asserted anywhere in section C |
| 13 | `verdict PROVEN`, `target_is_local_emulator false`, no credential | **KEPT** | the use-case table's **Artefact** cell for use case one, with `2026-08-15T14:11:35Z` and `base_url` added so the reader can check where it ran |
| 14 | "eleven requests" in that transcript | **MOVED** | `docs/demo/LIVE-BEATS.md:349` — `world read, the gate driven, the rollback re-read, the trap labelled, eleven requests in one` |
| 15 | the twelve-line sentinel-disagreement paragraph — "where they disagree, the wire wins", "this paragraph is the record of the disagreement" | **MOVED** | `docs/submission/JUDGE-START.md:485–502` carries the long form, including `~~...still holds the literal UNRESOLVED for demo_url and for video_url~~` and `SUPERSEDED 2026-08-16 for the demo_url half`. R9 caps section C at three sentences and the fragment uses three |
| 16 | `video_url` is genuinely unresolved; the film has not been recorded | **KEPT** | third sentence of that paragraph, footnoted to `SUBMISSION.json#notes.video_url` |
| 17 | "a submission checklist that looks finished before it is finished is the one failure mode this repository is built to refuse" | **DROPPED — budget, and it is rhetoric** | the fact it decorates is claim 16, which is kept. Nothing checkable is lost |
| 18 | `check_submission_ready.py` prints what is missing and reports `0 rows NOT CHECKED` | **MOVED** | `docs/submission/DEVPOST.md:259` and `:473`, `:479`, and `docs/submission/JUDGING-AXES.md:567` — all four carry `0 NOT CHECKED` with the reading's date. It is a verification command, so §G is its home in the README, not layer 1 |

---

## 2 · The live-demo section — `README.md:48–79`

| # | claim | disposition | where / why |
|---|---|---|---|
| 19 | "this is not a tour of the MAINLINE console"; "MAINLINE is infrastructure; you see it by seeing what it stops" | **MOVED** | `docs/demo/JUDGE-90-SECONDS.md:128` — `The film is not a tour of the MAINLINE console. It is shot inside the software the people in`. The second clause is a claim about the product, which is section B's job, not section C's |
| 20 | screen table — permit to work / site supervisor / `/operator.html#/permit`; management of change / safety engineer / `/operator.html#/change` | **KEPT** | rows one and two of the five-field use-case table, unchanged in substance. "editing a clause" is written as "merging a change to a written procedure", which is what the beats actually do |
| 21 | `operator.html` is a second HTML entry point in the same Vite build; file `verticals/mainline/apps/console/operator.html`, router `src/operator/route.ts`; not a page inside the console; no vendor mark | **MOVED** | `docs/demo/JUDGE-90-SECONDS.md:133–137` carries the same table and the sentence `operator.html` is a **second HTML entry point in the same Vite build**, with both source paths |
| 22 | every refusal on those screens comes back over HTTP and carries the SQLSTATE the database produced; nothing is mocked, staged or timed with a `setTimeout` | **MOVED** | `docs/demo/film/CLICKS.md:525` and `:869`, `docs/demo/film/FALLBACKS.md:160`, `docs/demo/film/CLAIMS-CLEARANCE.md:279` — each states `There is no setTimeout behind it` against a measured latency. The SQLSTATE half is `KEPT`: it is the whole of the fragment's third table row |
| 23 | "those two screens are in this tree and are **not on the deployed origin yet**"; measured 2026-08-15, `GET /operator.html` returns the console shell byte-for-byte identical to `GET /` | **KEPT, and corrected in place** | the fragment states the 2026-08-15 reading *and* the 2026-08-17 re-check. Measured read-only while writing: `GET /operator.html` → `200`, `5097` bytes, sha256 `a7a685e8b69595239a61f435b128f2d0887a23b581223803dd0fa3af68e28110`; `GET /` → `200`, `4749` bytes, sha256 `3178150a43f4976b2fec0324741b38d0fabcd8925ecf37d020dca7f4e56cc1ca`. The first digest equals `verticals/mainline/apps/console/dist/operator.html` in this tree; the second equals `dist/index.html`. `/assets/operator-C7FDTjCb.js` → `200`, `108862` bytes; `/assets/operator-D8s_r_O9.css` → `200`, `33690` bytes |
| 24 | "the screens ship when the orchestrator redeploys" | **DROPPED — falsified** | by claim 23's re-check. The entry point and its assets are served today. The fragment does **not** replace it with a claim that the screens work: it says only that the entry point is served, because a byte-identical document is what was measured and clicking through them was not |
| 25 | three commands, `demo_ready.py` / `live_beats.py` / `memory_loop.py`, with what each answers and its doc link | **KEPT** | the final table, one line each. R7: none of the three was run by this worker |

---

## 3 · The memory-loop section — `README.md:81–104`

| # | claim | disposition | where / why |
|---|---|---|---|
| 26 | `verdict PROVEN`, 23 of 23 assertions held, 0 failed | **MOVED** | `docs/demo/MEMORY-LOOP.md:12` — `**Verdict:** PROVEN — 40 rows, 23 of 23 assertions held, exit 0.` Confirmed in the artefact: `"assertions_held": 23`, `"verdict": "PROVEN"` in `evidence/demo/memory-loop.json` |
| 27 | run 2026-08-15 with `base_url` set to the demo URL, not a local emulator | **MOVED** | `evidence/demo/memory-loop.json` — `"base_url": "https://ihuuyvm4z6nfuktihnkey77fpy0eyrhj.lambda-url.ap-southeast-1.on.aws"`, `"generated_at": "2026-08-15T14:18:20.623921Z"`. The command row in the fragment tells a judge to pass `--base-url`, which is the actionable half |
| 28 | an incident in **2019** named a clause; seven years later a permit relies on it; **ten seconds** later the finding becomes an obligation | **MOVED** | `docs/demo/MEMORY-LOOP.md:27–28` — `An incident happened in 2019. It named a clause. Seven years later a permit relies on that clause, a retrieval pass finds the incident, ten seconds later the finding becomes an` … R3 also forbids the 2019 scenario in layer 1, one story told once. The fragment keeps the *shape* — STORE → RETRIEVE → ACT, an obligation that blocks the permit — without the second story's numbers |
| 29 | the ten seconds are `mainline.blocking_check.materialised_at` minus `mainline_meas.recall_run.started_at`, off two live routes, with `stated_anywhere_in_this_program: false` | **MOVED** | `docs/demo/MEMORY-LOOP.md:89–90`, `:116`, `:120` name both columns and both routes; `:193` is the section `## 3 · The ten seconds, computed`; `:204` carries `"stated_anywhere_in_this_program": false` |
| 30 | the program audits itself — `values_audited: 79`, `values_found_in_the_source: []`, `uuid_literals_in_the_source: 0`, beside the source's sha256 and byte count | **MOVED** | `evidence/demo/memory-loop.json` — `"values_audited": 79` and `"uuid_literals_in_the_source": 0`, in the `self_audit` block the claim already cited |
| 31 | no endpoint was added to make it filmable — ruling `R7`, *"the loop needs no new endpoint; every word is already a live GET"* | **MOVED** | `docs/demo/MEMORY-LOOP.md:33` — `Each word is already a live GET. **No endpoint was added to make this filmable** — ruling R7`; the same string is in `evidence/demo/memory-loop.json` |

---

## 4 · Claims section C adds that the current README does not make

Recorded because a ledger that only subtracts is not a ledger.

| claim | evidence |
|---|---|
| Use case two, management of change: read `00000`; merge refused `23514` on `cr_gate_closed_when_merged`; forged count refused `P0001` from `mainline.fn_cr_merge_gate`; `persisted: false` | `qa/live2.json` — `data.verdict PROVEN`, `data.generated_at 2026-08-16T21:11:57Z`, `resource cr_gate_run`, three beats, `data.persisted false` |
| Use case two has **no** admission beat and **no** kernel-procedure beat, and each absence carries the payload's own reason | `qa/live2.json#data.admission_beat` = `null` with `admission_absent_reason` and `admission_absent_grants` naming `db/GRANTS.yaml:644,647`; `#data.kernel_procedure_beat` = `null` with `kernel_procedure_absent_sqlstate` = `42501` and `kernel_procedure_absent_grants` naming `db/GRANTS.yaml:761` |
| The two artefacts about use case two's live status disagree, and both readings are published with their dates | `evidence/deploy/cr-gate-live.json` — `produced_at_utc 2026-08-16T04:41:54Z`, `verdict UNANSWERABLE`, `cr_gate_run_probe.status 404`, `why_unanswerable.finding` naming the origin, and `this_is_not_a_gate_that_failed_to_refuse`. `qa/cr-gate-live.json#phases[0]` — `generated_utc 2026-08-16T04:41:53Z`, `verdict UNANSWERABLE`, `exit_code 2`. `qa/live2.json` is 16 h 30 min newer and the string `ihuuyvm4z6nfuktihnkey77fpy0eyrhj` does not occur in it — checked by substring over the whole file |
| The route is deployed today, so the `404` reading is superseded — and a `POST` through the public origin was still not driven by us | one read-only probe, R6, made while writing on **2026-08-17**: `GET /v1/demo/cr-gate-run` → `405`, body `{"error":{"allow":["POST"],"detail":"/v1/demo/cr-gate-run exists but not for GET","kind":"method_not_allowed","status":405}}`; control `GET /v1/demo/gate-run` → `405` with the same shape; `GET /v1/health` → `200`, `ok true`, `database mainline_demo`, `deploy_chain_applied 271`, `server_date 2026-08-17T15:16:05Z`. No `POST`, no `terraform`, no AWS API call, no credential |
| Glosses added so no term is used before it is defined: **beat**, **SQLSTATE**, **`CHECK` constraint**, **obligation**, the forged-count attack, and `persisted: false` | R4 and the readability bar. Each gloss is twelve words or fewer at first use |

---

## 5 · Notes for W7

* Section C is **52 lines**, budget 55. Three lines of headroom for the assembler.
* **All layer-1 footnote definitions are collected at the end of section C, per R11 — done, not
  deferred.** Section C defines its own `[^src-open]`, `[^src-video]` and `[^src-cr-absent]`, and
  it now also carries `[^src-fiction]`, `[^src-story]` and `[^src-gate]`, copied **verbatim** out
  of W1's `FOOTNOTES FOR W7` block in `01-opening.md` and placed first, in reference order, with
  labels unrenamed. Checked by string equality against `01-opening.md`: all three match exactly,
  and no label is defined twice. **W7 must delete that block from `01-opening.md` at assembly**,
  or GitHub sees each of the three defined twice. An HTML comment in the fragment says so.
* **One citation inherited from W1 does not verify, and it is left in W1's wording rather than
  silently edited by this worker.** `[^src-story]` ends *"asserted byte-equal across four files
  by `tests/unit/corpus`"*. `tests/unit/corpus` does not exist in this tree, and
  `grep -rln commit_message_2013 tests/` returns nothing at all; the string occurs only in
  `verticals/mainline/demo/honesty/gen_card.py` and
  `verticals/mainline/demo/script/validate_shotlist.py`. It is a backticked token and not a
  Markdown link, so it does not break R8.6, but it is an evidence path a judge cannot follow.
  Flagged to W7 and W1 in the fragment's comment. R16 scope fence: `01-opening.md` was read, not
  written.
* Every relative link in the fragment was checked to resolve against this tree: `docs/deploy/JUDGE-PACK.md`,
  `docs/TOOL-USAGE.md`, `LICENSE`, `docs/submission/SUBMISSION.json`, `evidence/demo/live-beats.json`,
  `qa/live2.json`, `evidence/deploy/cr-gate-live.json`, `qa/cr-gate-live.json`,
  `docs/demo/DEMO-READY.md`, `docs/demo/LIVE-BEATS.md`, `docs/demo/MEMORY-LOOP.md`,
  `docs/submission/JUDGE-START.md`.
* The fragment was scanned against every rule in `scripts/submission/check_submission_prose.py`
  and `scripts/demo/claim_hygiene.py` by importing their `RULES` tuples and matching line by line:
  **0 hits**, and `0` bare-invariant hits. R12 was checked the same way: **0** sentences over 35
  words outside table cells, and no nested parenthetical.
* Two rows in this ledger — 3 and 24 — are **DROPPED because they are falsified**, not because
  they were inconvenient. Both belong in W6's `Corrections` table under R10 if there is room:
  the README said `SUBMISSION.json` still held the sentinel for `demo_url` when it no longer
  did, and it said the operator screens were not on the origin when today they are.
* `docs/submission/SUBMISSION.json` was **read and not edited**, per R9.
