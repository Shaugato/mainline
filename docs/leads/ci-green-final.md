# CI-BOARD LEAD — take the board to its honest floor

**Lead:** CI-BOARD · **Written:** 2026-08-14 · **Tree measured:** `master` @ `7535670`, clean
(`git status --porcelain` empty) · **Cluster:** local CockroachDB CCL v26.2.5 @ `127.0.0.1:26257`

This plan is written **after** measurement, not before it. Every number below was produced by a
command run at the current HEAD in the hour this file was written. Where the brief posed a
question, I RULE on it in §3 and name the authority I ruled from.

---

## 1. MY OWN BASELINE — measured, and it contradicts the handover

### 1.1 The demo-api suite, locally, `--crdb=reuse`, from `--junitxml`

```
.venv/Scripts/python.exe -m pytest verticals/mainline/apps/demo-api/tests \
    --crdb=reuse -q -p no:cacheprovider --junitxml=<report>
```

| | tests | passed | failed | skipped | errors |
|---|---|---|---|---|---|
| **Handover claimed** | 570 | 569 | 0 | 1 | 0 |
| **MEASURED at `7535670`** | **570** | **567** | **2** | **1** | **0** |

`time=303.525s`, `hostname=AetherX`, `timestamp=2026-08-14T14:34:04+10:00`.

The two failures:

1. `tests/test_reads.py::test_health_reads_the_deploy_chain_marker_when_the_database_has_one`
   — `psycopg.errors.InvalidCatalogName: database "w5_deploy_chain_marker" does not exist`.
2. `tests/test_transitions.py::test_sign_disposition_then_merge_commits`
   — `assert 503 == 200`, body `{'error': 'database_unreachable', 'detail': 'restart transaction:
   TransactionRetryWithProtoRefreshError…'}`.

### 1.2 The confirming second measurement — this is the important one

Re-running **only** `test_transitions.py` + `test_reads.py` under `--crdb=reuse`:

```
1 failed, 107 passed in 20.43s
FAILED verticals/mainline/apps/demo-api/tests/test_transitions.py::test_suspending_a_merged_permit_commits
    assert 503 == 200            (verticals/mainline/apps/demo-api/tests/test_transitions.py:808)
```

A **different** node id failed, with the **same** 503 `database_unreachable`, and the `test_reads`
failure did not reproduce. So, measured:

- The `test_transitions.py` 503s are **a real product defect that moves between node ids**: a
  CockroachDB **40001** `TransactionRetryWithProtoRefreshError` is escaping the retry wrapper and
  being rendered to the caller as `database_unreachable` / 503. It is neither a flake nor a
  deterministic per-node-id failure.
- `test_health_reads_the_deploy_chain_marker_when_the_database_has_one` is **state-ordered**: it
  requires a database `w5_deploy_chain_marker` that some earlier test creates, so it passes or
  fails on the composition of the run, not on the code.

**Consequence for the whole board:** the handover's "570/569/0/0" is not reproducible at this HEAD
and may not be quoted again until a worker re-establishes it. Every worker's BEFORE/AFTER must be
stated against **570/567/2/1**, and a worker who reports 569 passed must say which of these two it
fixed.

### 1.3 The board, dispatched at `7535670` and read WARM

Six lanes trigger on push and had already run at HEAD; the five that are `paths:`-filtered I
dispatched by hand (`gh workflow run … --ref master`) so that *every* lane in scope is measured at
this tree, not at a predecessor.

| lane | run | verdict at `7535670` | moved since handover? |
|---|---|---|---|
| `cluster-tests` | 31770005759 | **FAIL** — 570 collected, 569 executed, **1 skipped**, 8 failed | **YES — skips 10 → 1** |
| `cluster-lane-bites` | 31770005766 | **FAIL** — dies before the 2×2, on the frozen-seed guard | yes (new cause) |
| `ci` | 31770005791 | **FAIL** — 4 jobs (`PL-2`, `pytest --crdb=none`, `REUSE`, `ruff`) | yes (new causes) |
| `db` | 31770238265 | **FAIL** — `trappoint_ref.event` missing | no |
| `db-schema` | 31770240275 | **FAIL** — `mi-red`, 7 failed / 460 passed | no |
| `schema` | 31770005764 | **FAIL** — 4 jobs, one root cause: missing producers | no |
| `aws-evidence` | 31770005783 | **FAIL** — 3 jobs, one root cause: `CEN-ANCHORS` | no |
| `submission` | 31770005810 | **FAIL** — 1 job (`REUSE`); 2 of 3 jobs **pass** | improved |
| `custody-chain` | 31770245613 | **FAIL** — 2 jobs; 5 pass | no |
| `boundary` | 31770242329 | **PASS** | no |
| `release-proof` | 31770243984 | **PASS** | no |

**The single largest fact on this board: item 1 of the brief is already done.**
`cluster-tests` now runs `./.github/actions/build-demo-package` before the suite, the deployed zip
exists in the lane, and the skip count is **1 against a ceiling of 1** — the `jsonschema` skip and
nothing else. The ceiling was never touched. The nine tree-reading assertions that used to skip now
**execute**, and eight of them **fail**. That is the lane working exactly as designed: it converted
nine invisible skips into eight visible defects. Nobody may undo it.

### 1.4 The eight new `cluster-tests` failures, with their measured numbers

All eight are one finding: **the bundle CI builds is not the bundle the constants were measured
from.**

| measured in CI | declared in the tests |
|---|---|
| `assets/index-DzVoV1YM.js` @ **433,564 B** | `assets/index-BjAGxrVJ.js` @ **433,396 B** |
| deployed-package total **124,177** | **124,127** |
| flood-arithmetic shape **1,274,743** | **1,274,342** |

Failing node ids (all in `verticals/mainline/apps/demo-api/tests/`):
`test_response_contract.py::{test_the_ceiling_refuses_something_it_governs,
test_the_largest_file_in_the_built_web_tree_is_the_one_the_ceiling_refuses,
test_the_built_web_tree_has_not_outgrown_its_declaration,
test_every_identity_object_in_the_deployed_tree_serves_or_is_a_declared_refusal,
test_the_compressed_sibling_has_no_url_of_its_own_and_is_not_a_ceiling_refusal,
test_the_built_web_tree_matches_the_shape_the_flood_arithmetic_assumed}` and
`test_static_site.py::{test_the_deployed_package_is_the_tree_the_ceiling_was_derived_from,
test_serving_the_deployed_package_derives_the_ceiling_end_to_end}`.

### 1.5 `qa/cluster-known-red.json` is stale by an order of magnitude

The file records `445 collected` at HEAD `073dfea` with **64 node ids failing in all three runs**.
At `7535670` the same lane reports **570 collected, 8 failed, and not one of the eight is on the
list** — every failure is annotated `NEW`. The lane additionally emitted:

- `4 declared-unstable test(s) passed this run` — all four `test_transitions.py` entries; and
- a `known-red entry that PASSED` error naming
  `test_reads.py::test_the_disposition_carries_the_lattice_and_the_projected_requirements`
  (a truncated list — the full set must be read from the run, not guessed).

So roughly **64 inventory entries now pass**, and the file's own claim that the `unstable` four fail
"deterministically 17 runs of 17" is **falsified**: they passed in CI at this HEAD, while a fifth
sibling failed locally. §3 rules on what that means.

---

## 2. THE RULE THAT OUTRANKS EVERY TASK — restated, because it applies to five of the six briefs

A worker was once caught editing `demo_world.sql` to enrol a DERIVED credential id, making the SEED
match the CODE. Negative controls caught it; it was reverted.

**When a test and the code disagree, ask which side is AUTHORITATIVE, never which is easier to
move.** The ratified tiebreaker: *the console and the committed JSON schemas are authoritative for
what the demo must carry; the seed and the tests are BOTH checked against them, and either may
lose.*

Never lower a floor. Never raise a skip ceiling. Never add a known-red exemption to obtain a green.
`continue-on-error` and `|| true` are banned. Never `terraform apply`. Never print a credential.
Never weaken `HONESTY.md`, `CI-STATE.md`, a ratchet, or an assertion.

**Re-verification's first check is a `git diff` over every seed, fixture, ceiling and expected
value, asking which side moved and why that one was derived.** Write your commit message so that
diff reads as an answer.

---

## 3. RULINGS

### R1 — The 168 bytes: the console source is authoritative, the byte constants are derived — but only after reproducibility is PROVEN

*Authority: the ratified tiebreaker ("the console … is authoritative for what the demo must
carry"), plus the standing finding that the DEPLOYED tree is authoritative because cost is bytes
leaving the origin.*

`_LARGEST_WEB_OBJECT`, `_LARGEST_WEB_OBJECT_BYTES`, `_LARGEST_SERVED_OBJECT*`,
`_REFUSED_BY_THE_CEILING`, and the `124_127` / `1_274_342` totals are **measurements of a build**,
not floors. When the console source moves, re-measuring them is correct and is not "moving a floor".

**But** a content-hashed filename is only a legitimate constant if the build is reproducible. So the
order is non-negotiable:

1. **First** account for the 168 bytes. `verticals/mainline/apps/console/vite.config.ts:76-78`
   inlines `__MAINLINE_BUILD_ID__` from `process.env['MAINLINE_BUILD_ID'] ?? 'dev'` and
   `__MAINLINE_ATTESTATION_SOURCE__` from `MAINLINE_ATTESTATION`; the lane action deliberately
   leaves both **unset**. Rebuild locally with the action's exact environment and pins and see
   whether you reproduce `index-DzVoV1YM.js` @ 433,564 B **byte for byte**.
2. **If you reproduce it** — the build is deterministic, the console source simply grew, and you may
   re-record all derived constants in one commit whose message states old → new for each and names
   the console change that caused it.
3. **If you do not reproduce it** — the build is nondeterministic. That is a **larger** finding than
   the numbers, it makes every one of these assertions decoration, and the fix is to remove the
   nondeterminism, not to re-record a number you cannot re-measure.

**What may NOT move under any branch of this ruling:** `DEFAULT_MAX_RESPONSE_BYTES == 136 * 1024 ==
139_264`; the invariant that **exactly one** identity object is refused; and
`0 < _LARGEST_SERVED_OBJECT_BYTES < ceiling < _LARGEST_WEB_OBJECT_BYTES`. Those are derived from
cost, not from a build.

### R2 — The frozen seeds: this is the STALE-BASELINE case, and it must be PROVEN so before a hash is touched

*Authority: `tests/ci/test_demo_seed_is_frozen.py`'s own module docstring, "HOW TO RE-BASELINE", and
the four-part negative control it makes a precondition.*

`demo_permit.sql` now hashes `ba6c2339…4899` (recorded `df3470cb…2d35`); `demo_world.sql` now hashes
`78158939…5156` (recorded `e2aa9706…87bf`). Commit `898ad55` changed both seeds — seeding
`mainline.defeater_option` at checks `0007` and `000d` — and **did not re-measure the freeze in the
same commit**. That is precisely the omission the guard exists to catch, and the guard is right.

A hash computed FROM a file is never authoritative OVER that file, so a re-baseline is permitted —
**but only after all four controls come back clean, run BEFORE the constants are touched, with their
output pasted into the commit message**:

1. the seed diff carries **no moved credential line**;
2. `test_the_seed_derives_the_demo_credentials_from_their_names` passes;
3. `verticals/mainline/apps/demo-api/tests/test_credentials.py` passes in full under `--crdb=reuse`;
4. `demo_world.sql` still enrols **exactly one** signer as a digest of its NAME.

If any one comes back dirty, the answer is to revert the seed and **not** to edit the recorded hash.
That is the edit that once put `23503` in front of a judge.

### R3 — The four "unstable" entries are neither unstable nor deterministic. They are one product defect, and it does not belong in a category no ceiling polices

*Authority: my own measurement in §1.1–§1.2, which contradicts the file's stated "17 runs of 17".*

Measured: all four passed in CI at this HEAD; a fifth sibling
(`test_suspending_a_merged_permit_commits`, itself one of the four) failed locally in an isolated
re-run; the failure is always the same shape — a **40001** retry error surfacing as a **503
`database_unreachable`**. The node id moves; the defect does not.

Ruling: `unstable` is the wrong category and it must be emptied. Each entry is either
**(a)** deleted because the underlying retry gap is closed, or **(b)** moved into a group a ceiling
polices, with the cause stated as *"a 40001 escapes the retry wrapper on the sign→merge and
merge→suspend paths and is rendered `database_unreachable`"*. What is **not** allowed is leaving
them where nothing counts them. A prior lead measured 40001 six times out of six by racing two
connections against the local single node, so "untestable without Cloud" is false and may not be
claimed here.

### R4 — `collected.txt` is a build output, not a source file; delete it, do not annotate it

*Authority: the REUSE ratchet's own hard gates (`uncovered_total` baseline 0,
`uncovered_by_top_level_directory.<root>` baseline 0) and the file's content.*

`collected.txt` is a 530-line `pytest --collect-only -q` dump committed by accident in `eefae1c`. It
reddens **both** `submission` ("a stranger can clone it…") and `ci` ("REUSE — every file names its
licence"). Giving a scratch dump a licence header launders it into a source file. Delete it and add
the pattern to `.gitignore`. Both hard gates return to 0 by removal, which is the only motion that
does not lower a floor.

### R5 — The ruff ratchet baselines are authoritative downward only

*Authority: `qa/ruff-ratchet.json` is a ceiling; a ceiling may fall and may not rise.*

Measured in CI: **16 ratchet regressions**, plus `ruff format --check` dirty.

```
LINT   B905 tests/ 2→3 (+1)          C401 tests/ 0→1 (+1) [HARD]
       C408 tests/ 0→1 (+1) [HARD]   E501 scripts/ 1→4 (+3)
       E501 tests/ 1→6 (+5)          F401 tests/ 0→1 (+1) [HARD]
       ISC004 scripts/ 0→9 (+9) [HARD]   PLR0915 scripts/ 1→2 (+1)
       RUF003 verticals/ 0→1 (+1) [HARD] RUF005 scripts/ 0→1 (+1) [HARD]
       RUF005 tests/ 2→3 (+1)
FORMAT unformatted <repo> 0→14  other/ 0→5 [HARD]  scripts/ 0→1 [HARD]
       tests/ 0→3 [HARD]  verticals/ 0→5 [HARD]
```

**No number in that table may be raised.** Format the files; fix the findings. Improvements the same
run reported (`ARG002 tests/ 1→0`, `E402 tests/ 1→0`, `PLR0912 scripts/ 2→0`, `RUF001 tests/ 9→0`,
`RUF002 tests/ 2→1`, `reuse_toml_patterns_matching_nothing 5→1`) **must be banked by lowering those
baselines in the same commit** — that is the only baseline edit this plan authorises, and it is the
direction a ratchet is for.

### R6 — The evidence citation moved to match the code, never the reverse

*Authority: `infra/modules/demo-api/main.tf` is executable infrastructure;
`evidence/tool-usage/aws-services.json` is a citation of it.*

`CEN-ANCHORS` refuses twice: `main.tf:333` is quoted as
`authorization_type = var.url_authorization_type` but now reads
`handler = "mainline_demo_api.app.handler"`; `main.tf:215` is quoted as
`actions = ["ssm:GetParameter"]` but now reads `#`. The infra wave moved the lines. Re-anchor the
citations to the lines that actually carry the quoted text. **Do not edit `main.tf` to restore a
line number**, and do not weaken `CEN-ANCHORS` — it caught a silent retarget, which is exactly its
job. The third `aws-evidence` job is explicitly collateral ("an unmutated copy of `evidence/`
already fails"), so one fix clears all three.

### R7 — Which reds STAY RED, and are therefore successes of this plan

These report true product incompleteness. Turning them green is forbidden; sharpening them is
required.

- **`schema` and `db`** — `trappoint_ref.clause` and `trappoint_ref.event` have no producer in
  `packages/trappoint-sql/refvertical/sql`; `trappoint migrate` refuses at `0058_blocking_check`
  with `42P01`. Owner: KERNEL domain. `schema` already says all of this beautifully; **`db` says
  only `REFUSED: 0058_blocking_check: [42P01] relation "trappoint_ref.event" does not exist` and
  then exits 1.** Same finding, one lane legible and one not. That gap is W4's.
- **`ci` / `PL-2`** — asks for the URL of a `db` run in which CONFORMANCE itself went red.
  CONFORMANCE has never executed, because `db` stops one step earlier on the same missing producer.
  It stays `UNRECORDED`. Recording any other red run is the laundering the field exists to prevent.
- **`custody-chain`** — checks 4, 5, 6, 7, 8, 11, 12 have no runner bound; owner `verify-crypto`;
  `16 checks | 9 passed | 0 failed | 7 not checked`. Stays red.
- **`demo-health`** — no URL exists. Stays red.
- **`db-schema` / `mi-red`** — 7 failed, 460 passed, every failure captioned *"PL-2 RED, as
  intended"*, and `scripts/mi_ratchet.py red` exited **1 = law broken**. Those two statements cannot
  both be right. Either the lane's polarity is inverted (a CI defect) or an invariant genuinely has
  no failing owning test (an honest red). **W4 must determine which by reading
  `scripts/mi_ratchet.py`, and must not resolve it by flipping an expectation or by making a
  deliberately-red test pass.**

### R8 — A lane whose diagnosis needs `grep` will not be read

*Authority: the brief's item 4, and my own experience today — I could not read `db-schema`'s failure
without stripping ANSI and filtering, and `cluster-tests`' 8 assertions sit under CockroachDB's
event log.*

Every lane in scope must end a failing run with a **bounded, plain-text verdict block** — the node
ids, the numbers, the owner, what turns it green and what does not — emitted **after** any engine
output and **not** interleaved with it, with no ANSI in the `::error::` annotation. This is additive
only: no existing assertion may be removed to make room for it.

---

## 4. THE SIX WORKERS

Paths are **literally enumerated and disjoint**. If your work needs a file another worker owns,
**stop and report it to the lead** — do not edit it.

**Standing rule, and it is repeated verbatim in every brief:** *No shortcuts. Never move an
authoritative value to match a derived one. Never lower a floor, raise a ceiling, or add a known-red
exemption to obtain a green. `continue-on-error` and `|| true` are banned. Never `terraform apply`.
Never print a credential. Report full-suite `--crdb=reuse` numbers from `--junitxml` BEFORE and
AFTER against the measured baseline **570 tests / 567 passed / 2 failed / 1 skipped / 0 errors** —
not the handover's 569. A fix that breaks a neighbour is worse than the defect. The suite is silent
for minutes; healthy runs have been killed for looking hung — do not kill it.*

**Formatting rule, so W5 does not collide with anyone:** every worker leaves the files it owns
`ruff format`-clean and contributing no new `ruff check` finding. W5 owns the ratchet files and
every other `.py` in the tree.

| id | title | owns | depends on |
|---|---|---|---|
| W1 | The deployed tree and the 168 bytes | console build + the two contract test modules | — |
| W2 | The frozen seeds and the 2×2 that has never completed | seed freeze + bites lane | — |
| W3 | Prune the inventory; kill the 40001→503 | known-red + transitions/reads + `retry.py` | — |
| W4 | Make every red legible and correctly attributed | `cluster-tests`/`db`/`db-schema` lanes | — |
| W5 | The licence, lint and format regressions | `collected.txt`, ratchets, all other `.py` | — |
| W6 | Re-anchor the evidence; documents true about their own tree; `CI-STATE.md` | `evidence/`, `docs/` | W1–W5 for `CI-STATE.md` only |

Full briefs are carried in the structured output that accompanies this file. Each is self-contained.

---

## 5. DONE

- `cluster-tests`: builds the package (already true), skips **1** against ceiling **1** (already
  true), and **0 failed** — or the residue is on a policed list with a named owner.
- `cluster-lane-bites`: the 2×2 **completes**, and the discriminating cell —
  *plant-present/hermetic passes the SAME executed count as plant-absent* — is proven with both
  numbers printed.
- `qa/cluster-known-red.json`: pruned to measurement; `unstable` is **empty**.
- `ci`, `submission`, `aws-evidence`: **PASS**.
- `schema`, `db`, `custody-chain`, `demo-health`, `ci/PL-2`: **still RED**, each with a verdict block
  a stranger can read without `grep`.
- `db-schema`: either green, or red for a reason W4 has written down and proven.
- `docs/CI-STATE.md`: rewritten to the measured board, with the honest pass/skip split and the
  distinction between *fixed* and *deliberately red* on its face.
- The demo-api suite: `--junitxml` numbers at or better than **570 / 567 / 2 / 1 / 0**, in DEFAULT
  and RANDOMISED order.
