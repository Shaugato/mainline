<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# CI completion — the final wave

**Lead:** CI-completion lead. **Measured:** 2026-08-10, against
`github.com/Shaugato/mainline`, branch `master`, commit `ed4a12f`
(`docs(ci): record what GitHub actually says, red by red`).
**Every number below cites the command that produced it.** Nothing here is inferred from a
prose claim in another document, including `docs/CI-STATE.md`, which this wave found to be
accurate in the large and stale in three specific places (§1.4).

---

## 0. The commands this plan rests on

```bash
gh run list --branch master --limit 25 --json databaseId,workflowName,conclusion,event
gh run view <run-id> --json jobs --template '{{range .jobs}}{{.conclusion}} :: {{.name}}{{"\n"}}{{end}}'
gh run view <run-id> --log-failed
.venv/Scripts/python.exe -m ruff format --check .
.venv/Scripts/python.exe scripts/qa/ruff_ratchet.py
.venv/Scripts/python.exe scripts/qa/check_reuse.py
```

`jq` is not installed on this workstation; `gh --json --template` and `gh api --jq` are the
substitutes and are used throughout.

---

## 1. Reality, measured today

### 1.1 The board

`gh run list --branch master` at `ed4a12f`, plus the scheduled runs that have landed since:

| workflow | latest master conclusion | run id |
|---|---|---|
| `claims` | success | 31386723733 |
| `console` | success | 31386723734 |
| `judge-pack` | success | 31386723727 |
| `release-proof` | success | 31386723657 |
| `skills` | success | 31386723686 |
| `supply-chain` | success | 31386723719 |
| `cloud-verify` | **success** (first ever run, scheduled) | 31416080608 |
| `ci` | failure — 5 of 12 jobs | 31388699452 |
| `db` | failure — census; `kernel` **skipped** | 31386723687 |
| `db-schema` | failure — both jobs | 31386723718 |
| `boundary` | failure — 3 of 8 jobs | 31427116607 |
| `custody-chain` | failure — 7 of 16 checks unimplemented | 31386723642 |
| `schema` | failure — reference vertical producer | 31407342624 |
| `submission` | failure — licence-spelling ratchet | 31388699402 |
| `mutation-ratchet` | failure — pytest exit 4 | 31417446264 |
| `nightly-differential` | failure — `--package` twice | 31408959149 |
| `demo-health` | failure ×9 today — `DEMO_URL` unset | 31429290553 |

**Score: 7 green, 10 red, 0 never-run.** `cloud-verify` has now fired and is green — the
"1 never-run" line in the brief is superseded by run `31416080608`.

### 1.2 The finding that reorders the work

`ci.yml` declares `RED_SELECTOR: "g4alpha or pl2_red"` and splits the suite between
`hermetic-tests` (`-m "not (…)"`) and `red-by-design` (`-m "…"`). The design is right. The
selector is **half-connected**:

```
$ grep -rn "pytest.mark.pl2_red" tests packages verticals   ->  (no output)
$ sed -n '95,112p' pyproject.toml | grep pl2_red             ->  (no output)
```

`pl2_red` is **not registered in `pyproject.toml` and not applied to a single test.** The
CI log confirms the consequence: `41 failed, 8224 passed, 833 skipped, 5 deselected`. Five
deselected — the `g4alpha` five, and nothing else. So **eight tests that print
`PL-2 RED, as intended.` are failing inside the general regression lane**, where a reader
cannot tell them from a regression, which is precisely the condition the `red-by-design`
job was built to end. Extracted from run `31388699452`:

```
test_mi_blame.py::test_pl2_red_sev_max_is_never_projected_from_the_closure
test_mi_blame.py::test_mi26_red_the_monotone_guard_accepts_an_unrelated_severity_revision
test_mi_boundary_override.py::test_pl2_red_fn_boundary_project_does_not_exist_yet
test_mi_boundary_override.py::test_pl2_red_the_carried_use_projection_does_not_exist_yet
test_mi_boundary_override.py::test_pl2_red_the_two_new_evidentiary_tables_have_no_append_only_trigger
test_mi_boundary_override.py::test_pl2_red_nothing_yet_requires_a_cited_predicate_to_still_be_holding
test_mi_event_severity.py::test_pl2_red_severity_revision_provenance_is_not_yet_projected
test_mi_ratchet.py::test_red_every_invariant_is_enforced
```

This is the single highest-value change on the board and it is W4.

### 1.3 The 41, classified

`gh run view 31388699452 --log-failed`, every `FAILED` line, sorted into causes:

| n | cause | owner |
|---|---|---|
| 8 | declared PL-2 reds running in the wrong job (§1.2) | W4 |
| 8 | `migration 0207 is missing` — `test_0207_shape.py` | W6 |
| 2 | A6 sampling-param grep false positive (`temperature` in two physical-dimension tables) | W3 |
| 2 | `SPEC_STATUS_LAG` regression — `checks.yaml` flipped, code not | W1 |
| 2 | `import conftest` resolves to `packages/trappoint-sql/tests/conftest.py` | W7 |
| 2 | MR-5 suffix: `int('0114a')`; spine band declared list ≠ disk | W5 |
| 2 | `test_mypy_covers_workspace.py` — 3 distributions with no ratchet entry | W9 |
| 2 | novelty manifests cite files nobody wrote (`directrix`, `deltalattice`) | W6 |
| 2 | ratchet self-checks mirroring `ruff`/`REUSE` | W10 |
| 1 | `boto3 was imported during an offline test run` | W7 |
| 1 | injection scanner: `bedrock.py:126 [dict_literal] 'tools'` | W3 |
| 1 | `test_claim_bound_grep.py` — a statement rewrote the sanctioned claim | W9 |
| 1 | `HONESTY.md is behind its own evidence` | W9 |
| 1 | `0084_silence_ledger.sql` declares `COUNSEL-GATED: no` | W5 |
| 1 | `test_mi_ratchet.py::…fixity_unit_test_is_a_mention_not_a_witness` | W4 |
| 1 | `test_mi_spine.py::test_band_is_exactly_the_declared_files` | W5 |
| 1 | `test_k2_exit.py` ×3 — K2.4/K2.5/K2.6 missing artefacts | W6 (declare) |
| 1 | `test_mi_disposition_gated` parametrised case | W5 |

### 1.4 Three claims in the brief and in `CI-STATE.md` that did not survive measurement

* **"`db-schema`: the helper hand-lists a migration subset omitting 0110 … drops 0138a via
  `.isdigit()`."** **Already fixed** at `HEAD`. `tests/integration/recall_schema/_schema_support.py`
  now carries `_MIGRATION_ID = re.compile(r"(\d{1,4})([a-z]*)")`, a `migration_id()` that
  raises rather than skipping, `"0110"` in the band, and
  `_assert_band_is_self_contained`. The lane's two live failures are `mi-red` and the
  catalogue job. **But the same defect class survives in two other files**, which nobody
  looked at: `test_rc00_migration_shape.py` dies on `int('0114a')` and `test_mi_spine.py`'s
  declared band omits `0049b/c/d/y/z` that exist on disk. W5 owns the generalisation.
* **"`ruff format`, 247 files."** Measured on the pinned interpreter, ruff 0.16.1:
  `249 files would be reformatted, 1146 files already formatted`. The ratchet refuses with
  **4 regressions**, one of them a hard gate: `unformatted tree=other/ baseline=0 measured=2`.
* **"MI ratchet at 28/30."** The registry string in `ci.yml` still says *"28 of 30 MI
  invariants are not yet enforced"*. The measured message is **21 of 30 pending** —
  `MI03…MI30`, nine promoted. An intentional red whose message is seven invariants out of
  date is an intentional red losing its precision. W4 corrects it.

### 1.5 The census, reproduced line by line

`db.yml`'s image-pin census, replayed locally with the workflow's own script:

```
floating 37  ceiling 34      restated 24  ceiling 21
```

The six lines are named, and only six:

```
conftest.py:24, :52, :136, :149                              (floating, +3 over HEAD~1's 1)
.github/workflows/custody-chain.yml:538, :572                (restated, +2)
tests/integration/recall_schema/_schema_support.py:757       (restated, +1)
```

All six are prose. Rewording them returns the counts to exactly `34 / 21`, which is *held*,
which is green — **without touching a ceiling.** That is why W1 does not own `db.yml`.

### 1.6 The licence ratchet is not a 41-file problem

`scripts/qa/check_reuse.py` on the tree as committed:

```
LicenseRef-FSL-1.1-ALv2   4820 resolved   394 headers
FSL-1.1-ALv2              1254 resolved  1260 headers
REFUSED [RATCHET] metric=non_spdx_spelling.FSL-1.1-ALv2 baseline=1213 measured=1254
```

`LICENSES/` already contains **both** `FSL-1.1-ALv2.txt` and `LicenseRef-FSL-1.1-ALv2.txt`.
The repository is **mid-migration**, not 41 files short of compliant: 4820 occurrences use
the REUSE 3.3 form and 1254 do not. Restoring `measured=1213` would re-baseline a
half-migration and leave the ratchet pointing at a number with no meaning. The honest
finish is to complete the migration and set the baseline to **0 as a hard gate**. W10.

### 1.7 Anti-vacuity: which greens are already load-bearing

`grep -cE "can say no|planted|RED —|anti-vacuit"` over each workflow:

| lane | already proves it can fail | evidence |
|---|---|---|
| `claims` | **yes** | job `claim hygiene (red half, then green half)`, step `RED — the scanner fires on every planted violation family` |
| `judge-pack` | **yes** | job `the validator fires on every planted violation`; job `a run with no cluster exits 3, never 0` |
| `submission` | **yes** | job `the submission gate can say no` |
| `supply-chain` | partial | an anti-vacuity *guard* (the resolved set must name the workspace members) but no planted violation |
| `console` | **no** | |
| `release-proof` | **no** | |
| `skills` | **no** | |
| `cloud-verify` | **no** | |

Four lanes are green with no demonstration that they can be anything else. W8 closes that,
and closes it **as a standing job inside each lane** rather than as a one-off branch push,
because a one-off proves the lane could fail on 2026-08-10 and a standing job proves it on
every run thereafter.

---

## 2. Strategy

Four rulings govern this wave.

**R1 — The mechanical sweeps land last, alone, and in their own commits.** `ruff format .`
touches 249 files and the `LicenseRef-` rewrite touches 1254 occurrences. Either one landing
mid-wave makes every other worker's diff unreadable and every other worker's merge a
conflict. W10 holds an **exclusive tree lock**: it starts only when W1–W9 have landed, and it
produces exactly two commits, `style(ruff): …` and `chore(licence): …`, each mechanical, each
reviewable by its own summary line.

**R2 — Fix the instrument, never the assertion.** Three reds this wave are guards reporting
something untrue: the A6 grep calling a physical-dimension table a model request builder, a
band selector that drops MR-5 suffixed files, a `SPEC_STATUS_LAG` window that closed without
its declaration shrinking. In every case the repair is upstream of the assertion. No worker
may add `continue-on-error`, `|| true`, an `xfail`, a `skip`, or a raised ceiling to obtain
a green. A ratchet baseline may be re-taken only **downward**, or upward with the argument
written next to it in the same commit.

**R3 — An intentional red must name its missing artefact and its owner, in the log.** Six
lanes stay red on purpose. Each one's failure message must, after this wave, contain the
exact path or object that does not exist and the domain that owes it. `demo-health` already
does this well and is the model. `custody-chain`, `schema`, `db-schema`'s `mi-red`, the
`0207` band and the K2 exit criteria do not yet.

**R4 — Anti-vacuity is a committed property, not an errand.** For every green lane, the
proof that it can fail becomes a job in that lane that plants a violation into a scratch copy
of the input and asserts the checker exits non-zero. It runs forever. Where a real red CI run
is also obtainable cheaply, capture the run URL as corroboration — but the job is the
deliverable.

### 2.1 Sequencing

```
        ┌── W1  regressions closed at the cause ──┐
        ├── W2  lane environment floors            │
        ├── W3  the two noisy instruments          │
        ├── W5  selectors that skip silently       │  all parallel
        ├── W6  missing producers, declared        │
        ├── W7  conftest shadowing + AWS residency │
        ├── W8  anti-vacuity jobs                  │
        └── W9  release self-checks                ┘
                       │
                W4  pl2_red + the PL-2 run URL   (needs W1: `db` must run its
                       │                          kernel job before an ADR URL exists)
                       ▼
                W10 the two sweeps, then CI-STATE.md   (exclusive tree lock)
```

W4 is second-phase for one reason only: `docs/adr/0005-red-before-green.md` needs the URL of
an **observed red `conform` run**, and the `db` lane's `kernel` job is currently `skipped`
because `image-pin` fails ahead of it. W1's six-line rewording unblocks `image-pin`; the next
push produces the red `conform` run; W4 records its URL. Everything else in W4 is
independent and may start immediately.

### 2.2 Expected board after this wave

| lane | after | why |
|---|---|---|
| `ci` | **green** | 5 red jobs closed: PL-2 URL recorded, REUSE at 0, hermetic lane holds only true regressions, ruff clean, summary follows |
| `db` | **red, intentionally** | census green; `kernel` runs and `conform` is red by ADR 0005 — the artefact, not a defect |
| `db-schema` | **red, intentionally** | `mi-red` holds five invariants whose owning tests are too weak; message names all five and their owner |
| `boundary` | **green** | A6 measures a request builder instead of a token |
| `mutation-ratchet` | **green** | dependency floor complete; the lane publishes its number |
| `nightly-differential` | **green** | one `--package` |
| `custody-chain` | **red, intentionally** | 7 crypto checks unwritten; message names each and `owner=verify-crypto` |
| `schema` | **red, intentionally** | `trappoint_ref.event` has no producer; message names it |
| `submission` | **green** | licence spelling completed |
| `demo-health` | **red, intentionally** | no demo deployed; already the best-worded red in the tree |
| `claims` `console` `judge-pack` `release-proof` `skills` `supply-chain` `cloud-verify` | **green, and provably non-vacuous** | each carries a planted-violation job |

**Target: 11 green, 6 red, every red naming a missing artefact and its owner.**

---

## 3. Standing rules for every worker

1. Run it. A brief that says "should now pass" and was never executed is not evidence.
   Every worker quotes the command it ran and the output it got, in its commit message.
2. `continue-on-error`, `|| true`, `xfail`, `skip`, and raising a ratchet ceiling to obtain
   green are **banned**. If your fix would need one, the finding is real: sharpen the red's
   message instead and say so.
3. File ownership is absolute. Anything you need outside your list goes in
   `cross_domain_notes`, never in a commit.
4. `uv` and `just` are not installed locally. Use
   `D:/CoackroachDBxAWS/mainline/.venv/Scripts/python.exe`. Windows `PYTHONPATH` separator
   is `;`. CI uses `uv`; when you change an install line you cannot run it locally — assert
   the change by reading the failing CI log that motivated it and by pushing.
5. `CREATE SEQUENCE` / `nextval` / `SERIAL` / `unique_rowid()` are banned repository-wide and
   `ci.yml`'s `sequence ban` job enforces it. `FAMILY` is a reserved keyword.
6. Never run `terraform apply`. `init`, `validate`, `plan` only, and commit the plan output.
7. Do not weaken `docs/HONESTY.md` or `docs/CI-STATE.md`. Bringing `HONESTY.md` *forward* to
   match its evidence is required and is the opposite of weakening it.
8. Push to `master`. `paths:` filters mean an unrelated commit will not trigger your lane —
   check with `gh run list --branch master` that the lane you fixed actually ran.

---

## 4. The ten workers

Full briefs, owned paths and exit criteria are in the structured output that accompanies this
document. Summary:

| id | title | lands |
|---|---|---|
| W1 | The two admitted regressions, closed at the cause | phase 1 |
| W2 | Three lane-environment defects that mask their lanes | phase 1 |
| W3 | Two static instruments that cry wolf | phase 1 |
| W4 | `pl2_red` — the declared reds stop hiding, and PL-2 gets its URL | phase 2 |
| W5 | Selectors and declarations that can skip a file in silence | phase 1 |
| W6 | Missing producers, declared by name and by owner | phase 1 |
| W7 | `conftest` shadowing, and the AWS SDK on the offline path | phase 1 |
| W8 | Every green lane proves it can say no | phase 1 |
| W9 | The release self-checks, and the honesty document's lag | phase 1 |
| W10 | The two mechanical sweeps, then the new truth | phase 3, exclusive |

---

## 5. Cross-domain notes raised by this plan

* **`docs/STATE-OF-THE-BUILD.md` §3.3 is stale.** It records that no AWS service has ever
  executed. The orchestrator measured Bedrock live in `ap-southeast-2` today —
  `amazon.titan-embed-text-v2:0` returned a 1024-dim embedding, `inputTextTokenCount: 6`;
  `au.anthropic.claude-haiku-4-5-20251001-v1:0` replied with 16 in / 8 out. No worker in this
  wave owns that file. It needs a correction with the real evidence attached, and it is on
  the critical path for the hackathon's "≥1 AWS service, and how" requirement.
* **`mainline-gate-svc` reaches scipy, numpy, pint and rapidfuzz** through `mainline-domain`,
  recorded in `CI-STATE.md` §4. Four BLAS/binary-wheel distributions inside a
  determinism-critical merge gate is a `mainline-domain` split worth making, and it is not a
  CI defect.
* **`demo-health` will keep accumulating red runs every 30 minutes** until a demo is
  deployed and the `DEMO_URL` repository variable is set. Nine reds landed today alone. The
  message is correct and the cure is a deployment, not a workflow edit.
* **Submission Stage One still fails on two counts outside CI:** the repository is PRIVATE,
  and `docs/submission/SUBMISSION.json` holds `UNRESOLVED` for `demo_url`, `judge_access` and
  `video_url`.
