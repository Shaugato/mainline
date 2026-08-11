<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# CI state — what GitHub actually says

**Re-measured 2026-08-11 by W10**, after the completion wave (W1–W9) and the mechanical
sweep landed, at commit `47f8aa2` on `master`. Every conclusion below is a run id you can
open. Every cause is quoted from a real log, not inferred from a plan.

This document replaces the version taken at `ed4a12f`. Three of that version's claims did
not survive re-measurement and are corrected in §5.

---

## 0. Re-check it yourself

```bash
# every workflow's real conclusion on the default branch
gh run list --branch master --limit 100 --json databaseId,workflowName,conclusion,headSha,createdAt \
  --jq 'group_by(.workflowName)[] | max_by(.createdAt) | "\(.workflowName)|\(.conclusion)|\(.databaseId)"'

# one workflow's conclusion and its jobs
gh run view <run-id> --json jobs --template '{{range .jobs}}{{.conclusion}} :: {{.name}}{{"\n"}}{{end}}'

# the precise cause of a red — the command every claim below rests on
gh run view <run-id> --log-failed
```

`jq` is not installed on this workstation; `gh --json --jq` is the substitute.

---

## 1. Every workflow, with its real conclusion

Latest run per workflow on `master`. A lane whose `paths:` filter did not match the last
few commits carries an older SHA — that is not staleness in the table, it is the lane
truthfully not having been asked.

| workflow | conclusion | run | at |
|---|---|---|---|
| `claims` | success | 31441300036 | `9d02cee` |
| `cloud-verify` | success | 31441340234 | `9d02cee` |
| `console` | success | 31443340130 | `fd3b0bc` |
| `judge-pack` | success | 31441299981 | `9d02cee` |
| `mutation-ratchet` | **success** | 31462708330 | `998c526` |
| `release-proof` | success | 31441299987 | `9d02cee` |
| `skills` | success | 31444357481 | `c8a3b46` |
| `supply-chain` | success | 31459262572 | `8e8c0b3` |
| `boundary` | failure | 31462708369 | `998c526` |
| `ci` | failure | 31462708400 | `998c526` |
| `custody-chain` | failure | 31462708356 | `998c526` |
| `db` | failure | 31463897045 | `47f8aa2` |
| `db-schema` | failure | 31462708433 | `998c526` |
| `demo-health` | failure | 31462743972 | `998c526` |
| `nightly-differential` | failure | 31435379720 | `834aa59` |
| `schema` | failure | 31463897104 | `47f8aa2` |
| `submission` | failure | 31463897101 | `47f8aa2` |

**Score: 8 green, 9 red, 0 never-run.**

The wave moved two lanes and one job: `mutation-ratchet` is green for the first time,
`cloud-verify` has fired and is green, and `ci`'s `ruff format · the counted lint ratchet`
job is green for the first time. Of the nine reds, **six report a true incompleteness and
are meant to stay red** (§3); **three are untidy** (§4).

---

## 2. `ci`, job by job — 5 of 12 red

Run **31462708400**.

| | job |
|---|---|
| success | every checker this lane invokes exists |
| success | the lockfile is authoritative · workspace membership |
| success | mypy · and the target list is complete |
| success | import-linter contracts · and no package outside them |
| success | **ruff format · the counted lint ratchet** |
| success | the sequence ban, repository-wide |
| success | RED BY DESIGN, and it must stay red |
| failure | actionlint |
| failure | PL-2 — the red run is recorded |
| failure | REUSE — every file names its licence |
| failure | pytest --crdb=none |
| failure | CI summary |

**The regression lane is now readable.** `pytest --crdb=none` reports

```
21 failed, 8280 passed
```

against `41 failed, 8224 passed, 833 skipped, 5 deselected` at run 31388699452 before the
wave. Twenty of those twenty-one were closed by W1–W9; the eight declared PL-2 reds that
used to fail inside this job now run in `RED BY DESIGN`, which is green because they are
red, which is the point.

**`actionlint`** — not a workflow defect of this wave:

```
.github/workflows/console.yml:498:9: shellcheck reported issue in this script: SC2140
```

**`REUSE`** — see §4.1.

---

## 3. The six reds that are meant to be red

Each names the artefact that does not exist and the domain that owes it.

### 3.1 `custody-chain` — 7 of 16 checks unimplemented

Run 31462708356. Three jobs fail and two are skipped behind them. The message names all
seven checks, their artefacts and `owner=verify-crypto` (W-wave commit `dd770c5`). Nothing
here is broken; seven crypto checks have not been written.

### 3.2 `schema` — the reference vertical has no producer

Run 31463897104. `trappoint_ref.event` has no producer. The failure names the object.

### 3.3 `db-schema` — `mi-red` and the catalogue

Run 31462708433: `the catalogue is committed, current and well-formed` and `mi-red and
mi-green`. `mi-red` holds invariants whose owning tests are too weak to promote. The
**MI ratchet stands at 21 of 30 pending**, not 28 of 30 — see §5.3.

### 3.4 `demo-health` — no demo is deployed

Run 31462743972, and eight more today. `DEMO_URL` is unset because nothing is deployed.
This is the best-worded red in the tree and the model the others were brought up to. The
cure is a deployment, not a workflow edit. It will keep accumulating a red every 30
minutes until then.

### 3.5 `db` — a pin restatement, correctly refused

Run 31463897045, job `one version constant, and it lives in compose.yaml`:

```
##[error].github/workflows/cloud-verify.yml:522: restates the image instead of reading compose.yaml
##[error].github/workflows/cloud-verify.yml:523: restates the image instead of reading compose.yaml
```

This is a HARD check over six OWNED harness files and it is right. It is *listed here*
rather than under §4 because the refusal is correct and precise; it is nonetheless
**fixable, and §4.3 says by whom**. `kernel` is `skipped` behind it, so the lane's
`conform` red required by ADR 0005 has still not been observed on `master`, which is why
`ci`'s `PL-2 — the red run is recorded` job is also red.

### 3.6 `nightly-differential` — the lane refuses to report green on a skip

Run 31435379720:

```
the differential SKIPPED. A cluster is running in this job, so a skip means the suite
could not reach it. This lane asserts nothing when it skips and must not be allowed to
report green.
```

The lane is correct to refuse. It has not re-run since `834aa59`; its next run is the
measurement that matters.

---

## 4. The three untidy reds

Untidy, not intentional: each is fixable and none of them was fixed.

### 4.1 `ci` → `REUSE`, and `submission` with it

```
REFUSED [RATCHET] metric=non_spdx_spelling.FSL-1.1-ALv2 baseline=1213 measured=1254
```

The repository is mid-migration between `FSL-1.1-ALv2` and `LicenseRef-FSL-1.1-ALv2`:
4 821 occurrences already use the REUSE 3.3 form and 1 254 do not.

**W10 built the migration, measured it, and reverted it.** It is not a mechanical sweep:
it rewrites 290 migration `.sql` files whose bytes are recorded in
`verticals/mainline/db/migrations.lock.json` — the artefact behind `chain 271/271
applied` — and it produced **59 new test failures** (5 → 64 across the suites that name the
spelling), because eleven sites *generate* the bare spelling and five *assert* it. The full
measurement, and the ordered plan for doing it properly, are in
[`docs/ci/mechanical-sweeps.md`](ci/mechanical-sweeps.md) §2.

This is the **only** thing keeping `submission` red. `LICENSE` and `LICENSES/` exist and
the path-length gate is fixed.

### 4.2 `boundary` — two lint findings, both older than the wave

Run 31462708369, job `mainline-boundary unit tests`, step `ruff`: `Found 2 errors.`

```
tests/boundary/conftest.py:39:1        E402   Module level import not at top of file
tests/boundary/test_fleet_matrix.py:5  RUF002 Docstring contains ambiguous EN DASH
```

Both pre-date the sweep. Measured on a fresh LF worktree with
`ruff check packages/mainline-boundary tests/boundary`: **7 errors at `8e8c0b3`, 2 at
`47f8aa2`** — the sweep removed four `I001` and one `E501` and introduced nothing. The A6
grep W3 narrowed is fixed and its `RED —` control is green.

### 4.3 `db`'s pin restatement has a known repair

`cloud-verify.yml:522` and `release-proof.yml:380,384` write the image literal in order to
compare it against `compose.yaml`. The repair is to extract it the way
`trappoint_migrate.crdb.pinned_image` already does — find the `trappoint:crdb-image-pin`
marker, take the first `image:` line within the next three — which spells no image literal
at all, satisfies the hard check, and takes the census `restated` count from 25 to 19
without a ceiling moving. Owner: those two lanes.

W10 owns `db.yml` and deliberately did **not** absorb this into the census. An earlier
attempt (`f229c1b`) taught the census to treat those lines as a self-policing guard; it was
reverted whole in `47f8aa2` once the real run showed the hard check refusing first, and
because db.yml's own comment says an exclusion list "is a place to hide a real regression".

---

## 5. Claims in the previous version of this document that did not survive

### 5.1 "`ruff format`, 247 files" — the number is **207**

`core.autocrlf` is `true` in this checkout and `ruff.toml` pins `line-ending = "lf"`, so
153 of 1 190 `.py` files counted as unformatted on Windows and did not on the runner.
Measured on a fresh LF worktree: **207**, being 200 `.py` and 7 `.md` (ruff formats python
fences inside Markdown). The tree is now at **0**.

### 5.2 "`db-schema`: the helper hand-lists a migration subset omitting 0110 … drops 0138a"

**Already fixed** before this wave measured it.
`tests/integration/recall_schema/_schema_support.py` carries
`_MIGRATION_ID = re.compile(r"(\d{1,4})([a-z]*)")`, a `migration_id()` that raises rather
than skipping, `"0110"` in the band, and `_assert_band_is_self_contained`. The lane's live
failures are the catalogue job and `mi-red`. W5 generalised the same defect class to
`test_rc00_migration_shape.py` and `test_mi_spine.py`.

### 5.3 "MI ratchet at 28 of 30"

The measured message is **21 of 30 pending** — `MI03…MI30`, nine promoted. An intentional
red whose message is seven invariants out of date is an intentional red losing its
precision; W4 corrected the registry string.

### 5.4 The image-pin census, restated

The previous version recorded `floating 37 / ceiling 34, restated 24 / ceiling 21` and
called it "a regression this wave introduced". W1 closed it exactly as planned:

| commit | floating | restated |
|---|---|---|
| `ed4a12f` | 37 | 24 |
| `90b74df` (W1) | **34** | **21** |
| `8e8c0b3` (before the sweep) | 34 | 25 |
| `998c526` (after the sweep) | 34 | 25 |

The sweep is census-neutral. The four that arrived after W1 are the pin restatements in
§4.3. Measured by extracting `db.yml`'s own heredoc and running it, not by reimplementing
it.

---

## 6. Anti-vacuity — which greens are load-bearing

W8's ruling: a proof that a lane *can* fail belongs in the lane as a standing job, because
a one-off proves it on one day and a standing job proves it on every run. Every green lane
now carries one.

| lane | the job that proves it can say no |
|---|---|
| `claims` | `RED — the scanner fires on every planted violation family`; `RED — the committed non-compliant fixture is refused`; `Every declared rule is reached by a planted violation, and the plants are load-bearing` |
| `cloud-verify` | `RED — with no secret the probe says false, and says why`; `RED — a DSN that is not Cloud is a FAILURE, never a quiet false`; `RED — the gate and its complement are both still declared` |
| `console` | `RED — pnpm run ci fails on every planted violation family`; `RED — one planted violation per promise, and the COMPOSITE must name each` |
| `judge-pack` | `the validator fires on every planted violation`; `RED — one planted violation per family, all of them caught`; `Each planted mutation changes the pack, is caught, and is absent without it` |
| `release-proof` | `RED — the gate refuses a run where nothing was proved`; `RED — the proof reports NOT PROVEN when the gate is removed`; `RED — the proof reports a named FAILURE for every planted family` |
| `skills` | `RED — five planted spec violations, each refused BY NAME`; `RED — four planted marketplace violations, each refused BY NAME` |
| `submission` | `the submission gate can say no`; `RED — every planted failure family fires` |
| `boundary` | `RED — the narrowed A6 rule still fires on a real request builder` |

`supply-chain` carries an anti-vacuity **guard** (the resolved set must name the workspace
members) rather than a planted violation, and is the one green lane whose proof is weaker
than the others'. It is named here rather than left to be discovered.

Two checkers additionally prove themselves outside CI, on a synthetic tree:

```
$ scripts/qa/check_reuse.py --self-test
7 of 7 scenarios behaved as declared: the checker passes a complete tree and refuses
each of the 6 planted violations.
```

and `tests/release/test_ruff_ratchet.py` records, in its own module docstring, the two runs
in which the ratchet was neutered and the exact assertions that went red.

---

## 7. What this leaves for the next wave

1. **Finish the licence migration properly** — `docs/ci/mechanical-sweeps.md` §2.4 has the
   ordered plan. Closes `ci`'s `REUSE` job and all of `submission`.
2. **Make `cloud-verify.yml` and `release-proof.yml` read the pin** (§4.3). Closes `db`'s
   `image-pin`, which unblocks `kernel`, which produces the observed red `conform` run that
   `ci`'s `PL-2` job is waiting for.
3. **Two lint findings in `tests/boundary/`** (§4.2). Closes `boundary`.
4. **`console.yml:498` SC2140** (§2). Closes `ci`'s `actionlint`.
5. Deploy a demo and set `DEMO_URL`. Closes `demo-health` and the submission's Stage One.

Nothing in this list is a ratchet to be raised or a check to be softened. Every one of them
is a thing that does not exist yet, or a line that is written twice and should be written
once.
