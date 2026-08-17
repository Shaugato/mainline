<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# Claim ledger — W6, `06-verify.md`

**What this file is.** `docs/submission/readme-parts/06-verify.md` replaces three sections of the
current `README.md`: *Clone it, then four commands* (`README.md:108-253`), *Read this before you
believe any of it* (`README.md:255-313`), *Verifying without trusting us* (`README.md:416-439`),
*Repository layout* (`README.md:400-414`), *Status* (`README.md:441-457`) and *Licence*
(`README.md:459-475`). Every claim, number and citation in those sections is listed below with
exactly one disposition, under readme-plan ruling **R2**:

* **KEPT** — present in the fragment.
* **MOVED** — a named file that already exists carries it, and the grep that proves so is printed.
  No destination file was edited by this worker.
* **DROPPED** — with the reason. Nothing was dropped because it was inconvenient.

Greps below were run from the repository root on 2026-08-17 and their line numbers are that day's.

---

## 1 · Section G — *Check us — clone it and reproduce the refusal*

| # | claim in the current README | disposition | where it is, or why not |
|---|---|---|---|
| 1 | `git clone -c core.longpaths=true …` copy-paste block | **KEPT** | verbatim; `scripts/submission/judge_dry_run.py:805` requires the flag to be in this block |
| 2 | Windows `MAX_PATH` is 260 | **KEPT** | — |
| 3 | longest tracked path is 141 characters, with its citation | **KEPT** | — |
| 4 | the 141-character path spelled out in full (`skills/upstream/…/verify_restore_merkle_root.py.license`) | **MOVED** | `grep -n "verify_restore_merkle_root.py.license" qa/judge-dry-run.json` → `path_lengths.longest_paths[0].path` |
| 5 | the arithmetic `len(dest) + 1 + len(path) <= 259` | **MOVED** | `grep -n "full = len(clone destination)" qa/judge-dry-run.json` → `path_lengths.arithmetic` |
| 6 | safe clone prefix is 117 characters, with its citation | **KEPT** | — |
| 7 | the 214-character archaeology (fixture untracked, artefact still records 214, the old citation named the wrong field) | **KEPT, relocated** | ruling **R10**: it is row 1 of the Corrections table in section I |
| 8 | the three-row clone bracket (111 chars clean · 122 fails · 122 with the flag clean but unreadable) | **KEPT, compressed** | one sentence in the fragment. No artefact holds this 2026-08-12 re-measurement, so it could not be MOVED |
| 9 | the bracket table's `dest + 1 + 141` column and its `7 437 dirty paths` count | **DROPPED** | both are derivable from the two numbers kept (141 and the destination length); the failing-clone transcript itself is in `qa/judge-dry-run.json#clone_attempts[0].output.head` |
| 10 | "the flag fixes `git`, not everything else"; clone somewhere short; no-op on macOS and Linux | **KEPT** | — |
| 11 | both command columns are first-class; `just` and `uv` are not on this machine, with its citation | **KEPT** | — |
| 12 | the four documented commands, both columns | **KEPT** | verbatim; `judge_dry_run.py:834` and `:917` |
| 13 | `doctor` exits 1 on `uv` and `just` only, prints a numbered remedy, does not block the proof | **KEPT** | — |
| 14 | the install step is not optional; a recorded dry run falsified "nothing but the interpreter" | **KEPT** | also row 3 of the Corrections table |
| 15 | the fresh-venv traceback, quoted with its file and line frame | **DROPPED to its last line** | the fragment keeps `ModuleNotFoundError: No module named 'psycopg'`; the frame above it is reproduced by running the command |
| 16 | the install pulls six packages in 19.7 s | **MOVED** | `grep -n "19.7 s, six packages" VERIFY.md` → `VERIFY.md:298` |
| 17 | `just setup` does the fuller job — installs `uv`, then `uv sync --all-packages` | **MOVED** | `grep -n "uv sync --all-packages" justfile qa/judge-dry-run.json` → `justfile:71-77`, and `documented_commands.commands[1].fallback_actually_run` |
| 18 | `crdb-align` pins `gc.ttlseconds` to 4500 to match Cloud Basic | **KEPT** | — |
| 19 | the five-row cost table (2.788 s · 0.472 s · 19.7 s · 70.351 s → 106.2 s · 30.112 s → 13.7 s, 9 324 tests) | **MOVED** | `grep -n "What was executed for this revision" VERIFY.md` → `VERIFY.md:292-304`, which carries every row with its exit code |
| 20 | "every figure is an upper bound rather than a benchmark" | **MOVED** | `grep -n "operator_notes" qa/judge-dry-run.json` → the artefact states the shared-node caveat itself |
| 21 | the recording names the commit it ran against; 106.2 s against 70.351 s | **MOVED** | `grep -n "70.351" docs/submission/JUDGE-START.md qa/judge-dry-run.json` → `JUDGE-START.md:342`, `judge-dry-run.json:1002` |
| 22 | pointer to `docs/submission/FIRST-FIVE-MINUTES.md` | **MOVED** | `grep -n "FIRST-FIVE-MINUTES" docs/submission/JUDGE-START.md` → `JUDGE-START.md:381` |
| 23 | the committed proof transcript, six lines including both SQLSTATEs | **KEPT** | verbatim |
| 24 | the 2026-08-12 re-run: `chain 271/271 applied, 0 failed, 55.611s`, `caveats (none)` | **MOVED** | `grep -n "55.611s" VERIFY.md` → `VERIFY.md:85-95`, the whole block |
| 25 | the three attempts explained (plain `CHECK`, forged projection, admission after one signed disposition) | **KEPT in one clause** | "refused, refused again with the counter forged, then admitted"; the mechanism is section D's, and the `DRIFT` line of the transcript carries the forgery |
| 26 | the `PROJECTION` commentary: 0→1, severity 4 against a client's 0, "a counter a client writes is a client's opinion" | **KEPT as numbers, commentary MOVED** | the numbers stay in the transcript line; `grep -rn "client's opinion" docs/demo/research/r6-honesty.md` → `r6-honesty.md:500` |
| 27 | pointer to `docs/release/QUICKSTART.md` as the long version | **MOVED** | `grep -n "QUICKSTART" docs/submission/FIRST-FIVE-MINUTES.md` → `:225`, "both open with the same four commands"; `qa/judge-dry-run.json#documented_commands` records `in_quickstart: true` for all four |
| 28 | `VERIFY.md`'s three tiers; tier 2 is the four commands | **KEPT** | — |
| 29 | tier 1 returns `16 checks · 8 passed · 1 failed · 7 not checked`, exit 1; seven cryptographic checks unimplemented; one red on real drift; not a verified ledger | **KEPT** | unsoftened, and the word for the failing check is glossed rather than named, per ruling **R4** |
| 30 | `evidence/gate-refusal/` and `qa/test-state.json` as the two artefacts worth opening | **KEPT** | including "predates the producer migrations and has not been retaken" |

**One claim was added in section G, and it is a correction rather than a decoration.**
`qa/test-state.json#external_checks.custody_bundle_verification` records the same offline tool at
`9 passed · 0 failed · 7 not checked`, **exit 2** — a different result from `VERIFY.md`'s exit 1.
The fragment prints both, dates them, and says which is newer. A reviewer who opens the two files
would find the disagreement; a page that only quoted the newer one would look like it had not.

---

## 2 · Section H — *What we are not claiming*

| # | claim in the current README | disposition | where it is, or why not |
|---|---|---|---|
| 31 | `docs/HONESTY.md` link, and that `tests/release/test_honesty_is_checkable.py` fails the build when a number and its source disagree | **KEPT** | promoted to the first sentence of the section |
| 32 | `docs/submission/MUST-NOT-CLAIM.md` | **KEPT, promoted** | the current README does not link it from this section at all; it is now the second sentence |
| 33 | seven tables had no migration at all; 271 of 271 is a census, not a deployment; the forward-only runner wrote no artefact | **MOVED** | `grep -n "Seven tables had no migration at all" docs/HONESTY.md` → `HONESTY.md:559` |
| 34 | the conformance suite has never been demonstrated; 71 declared, 55 could not run, 6 red, 10 held | **KEPT** | unsoftened, with `qa/conformance-census.json#totals` |
| 35 | "`docs/HONESTY.md` has not absorbed that census yet" | **MOVED** | `grep -n "conformance-census" docs/HONESTY.md` → `:837-846`; that page now cites the census, so the sentence has outlived its subject |
| 36 | authored corpus, recorded cassettes, `NOT-SECRET` keys published on purpose | **KEPT** | — |
| 37 | the test census is per package, taken twice, with every skip reason | **KEPT** | in section G's artefact bullet |
| 38 | lint and types are counted, not clean; the ruff ratchet is red today | **KEPT** | with `qa/ruff-ratchet.json#lint.total` and `qa/mypy-ratchet.json#source_files_checked` |
| 39 | Bedrock in Sydney, database in Singapore, end-to-end Australian residency is false, hop unmeasured, every timing local | **KEPT** | — |
| 40 | "`ap-southeast-2` is Advanced-tier only on CockroachDB Cloud" | **MOVED** | `grep -n "Advanced-tier only" VERIFY.md` → `VERIFY.md:248` |
| 41 | nothing has ever run against CockroachDB Cloud in CI | **KEPT** | the current README does not say this in prose; it is `SUB-09`, and it belongs on the page |
| 42 | ~~Bedrock genuinely executes and nothing else on AWS does~~ | **KEPT, relocated** | row 2 of the Corrections table |
| 43 | the four Bedrock and STS calls with AWS request ids, the Titan v2 embedding, the Haiku `Converse`, `calls_failed: []`, cost under one cent | **MOVED** | `grep -n "sts:GetCallerIdentity" docs/TOOL-USAGE.md` → `TOOL-USAGE.md:1183`, request id and all |
| 44 | CloudFront is blocked by an account verification hold, with the verbatim `AccessDenied` string | **MOVED** | `grep -n "must be verified before you can add new CloudFront" docs/deploy/RUNBOOK.md` → `RUNBOOK.md:1544,1555`. Ruling **R14** puts this in section E, not here |
| 45 | which AWS row is `EXERCISED` is the census's to assert, not this page's | **KEPT** | inside Corrections row 2, naming `evidence/tool-usage/aws-services.json` |
| 46 | `python scripts/submission/capture_tool_evidence.py --check` as the re-derivation command | **DROPPED** | a re-derivation command for an artefact this page only cites; the script is in the tree and `docs/TOOL-USAGE.md` is the page that owns the census |

---

## 3 · Section I — *Repository, licence, status, corrections*

| # | claim in the current README | disposition | where it is, or why not |
|---|---|---|---|
| 47 | the nine-row repository layout table with per-directory licences | **KEPT** | unchanged except row 47a |
| 47a | `evidence/` holds "a **signed** reference ledger any stranger can verify offline" | **KEPT, corrected** | now "a reference ledger whose structure a stranger can check offline". `VERIFY.md:28,270` records that tier 1 exits 1 and that the signatures are among the seven checks that do not run, so "signed … verify" overstated it |
| 48 | import boundaries are the layer, licence and liability boundary; `.importlinter` contract 1 | **KEPT** | compressed to one sentence; contract 1's own comment in `.importlinter` states the licence rationale |
| 49 | pre-alpha, under active construction | **KEPT** | as "Pre-alpha" |
| 50 | the design corpus is in a companion repository; 40-agent design operation; 28 adversarial findings; independent feasibility verification | **MOVED** | `grep -n "40-agent" docs/submission/DISCLOSURE.md` → `DISCLOSURE.md:199,207` |
| 51 | the Actions tab is red in places; read `docs/CI-STATE.md` first; seven of sixteen custody checks unwritten | **KEPT** | — |
| 52 | "a reference vertical with no producer" as one of the true reds | **MOVED** | `grep -n "missing two producers" VERIFY.md` → `VERIFY.md:104`; `grep -n "2 with no producer" docs/CI-STATE.md` → `:674` |
| 53 | "21 of 30 invariants pending" as one of the true reds | **MOVED** | `grep -rn "21 of 30" docs/submission/` → `VIDEO-KIT.md:664`, `PUBLIC-FLIP-CHECKLIST.md:357`, `architecture-plan.md:170,226` |
| 54 | ~~no demo to health-check~~, and the parenthetical that `GET /v1/health` now answers `ok: true` | **DROPPED here** | section C owns the live-demo status under ruling **R5**, and the lane itself is `grep -n "demo-health" docs/CI-STATE.md` → `:236`. Asserting a lane's colour from the README is the failure this repository refuses |
| 55 | "nothing here claims what it cannot prove, and the unproven claims are named in `docs/HONESTY.md`" | **KEPT in substance** | section H opens with the two files rather than closing with the sentiment |
| 56 | root `LICENSE` is Apache-2.0; GitHub detects it; the About badge | **KEPT** | — |
| 57 | the `gh repo view` command and its `{"visibility":"PUBLIC","licenseInfo":{"key":"apache-2.0"}}` answer | **MOVED** | `grep -n "licenseInfo" docs/submission/JUDGING-AXES.md` → `:475-476` |
| 58 | multi-licensed by directory; `LICENSES/`; `REUSE.toml`; `LICENSING.md`; `TRADEMARKS.md` | **KEPT** | four sentences, as the brief requires |
| 59 | why `LICENSES/` ships `FSL-1.1-ALv2.txt` and `LicenseRef-FSL-1.1-ALv2.txt` byte-identically; headers use the bare spelling; REUSE requires the prefix; shipping both beat a mass edit | **MOVED** | `grep -n "LicenseRef-FSL-1.1-ALv2.txt" docs/submission/LICENSING.md` → `:114` (ruling L-1) and `:117` (the `sha256sum` of both texts) |

**The Corrections table (ruling R10).** Three rows, six lines, under the fifteen-line ceiling. Seeded
with the two the brief names — the 214-character clone path and *Bedrock genuinely executes and
nothing else on AWS does* — plus *the proof needs nothing but the interpreter*, which this page also
used to say and which a recorded dry run falsified. Row 1 additionally carries a limit the artefact
declares about itself: the 117-character prefix is arithmetic over the tracked paths, and the clone
probe that would observe it has not been re-run
[src: qa/judge-dry-run.json#superseded_observations.still_owed].

---

## 4 · Budget and invariants

| | |
|---|---|
| lines | **95** across the three sections (ceiling 95) |
| bytes | 10 359 |
| clone line with `core.longpaths` | present verbatim, in a `bash` copy-paste block |
| the four documented commands | present verbatim in both columns |
| `python scripts/submission/check_submission_prose.py --check` on this fragment | **exit 0**, 0 submission-prose and 0 claim-hygiene violations |
| relative links | 13, all resolving to paths that exist |
| longest prose sentence | 34 words |
| terms banned by ruling R4 | none present |

**What this worker did not do.** No proof script, seeding script or regression guard was run
(ruling **R7**); every number above was read out of a committed artefact. No network call was made.
No file outside `docs/submission/readme-parts/06-verify.md` and this ledger was written. Nothing was
committed.
