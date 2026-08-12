<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# CI to its honest floor — wave 2 plan

**Written 2026-08-12 by the CI-COMPLETION LEAD, at `1d41442` on `master`.**

Every number below was measured today, by me, before this file was written. Where a claim
rests on a run, the run id is given and you can open it. Where a claim contradicts
`docs/CI-STATE.md` or the brief that commissioned this wave, the contradiction is stated
plainly rather than smoothed over — **three of the six tasks I was given were already done
by the previous wave**, and a wave that "fixes" them again would be reporting motion as
progress.

---

## 0. What I did to establish reality

`docs/CI-STATE.md` was measured at `47f8aa2`. Two commits have landed since — `ca912eb`
(*"Bedrock executes for real, CI hardening, deploy prep"*) and `1d41442` (the AWS
account-id masking that preceded going public). **Most lanes had never run at `1d41442`**,
and GitHub had already expired the logs of the runs the document cites, so the board it
records could not be re-read — `gh run view <id> --log-failed` answers `log not found` or
`BlobNotFound` for every run before today.

Every workflow in this repository declares `workflow_dispatch`. So I dispatched fourteen
of them at `1d41442` and read the logs while they were still warm. **That is the board
below, and it is the first board measured at HEAD.**

```bash
# what I ran, and what you should run before trusting any row here
gh workflow run <lane>.yml --ref master
gh run view <new-id> --log-failed
```

**Logs expire quickly on this repository. Read them in the same sitting you create them.**
Every worker below is told this because it is the single operational fact that most
changes how this wave has to be worked.

---

## 1. The board at `1d41442`, measured today

| lane | conclusion | run | cause (quoted from the log) |
|---|---|---|---|
| `claims` | **success** | 31596451954 | — *(was recorded red; it is green at HEAD)* |
| `boundary` | **success** | 31596449113 | — *(was recorded red; it is green at HEAD)* |
| `submission` | **success** | 31596458067 | — *(was recorded red; it is green at HEAD)* |
| `judge-pack` | success | 31596651980 | — |
| `release-proof` | success | 31596655296 | — |
| `skills` | success | 31596658833 | — |
| `ci` | failure | 31596249352 | 9 jobs: `connect ECONNREFUSED 54.185.253.63:443` in `setup-workspace`; `actionlint` install exit 7 |
| `supply-chain` | **failure** | 31596446007 | all 3 jobs: same `ECONNREFUSED 54.185.253.63:443` *(was green; it regressed)* |
| `db` | failure | 31596634515 | same `ECONNREFUSED` |
| `aws-evidence` | failure | 31596455267 | `[SEC-ACCOUNT-ID] evidence/deploy/deploy-dry-run.json:409,412` |
| `schema` | failure | 31596641256 | `trappoint_ref.clause`, `trappoint_ref.event` created by no file |
| `custody-chain` | failure | 31596645067 | merkle vectors; exhibit vocabulary; bundle regeneration |
| `db-schema` | failure | 31596638185 | catalogue tier-0; `mi-red` |
| `console`, `mutation-ratchet` | *in flight at writing* | 31596648619, 31596662350 | W2 / W10 re-measure |
| `cloud-verify`, `demo-health`, `nightly-differential` | not dispatched | — | need a secret, a `DEMO_URL`, and a nightly cluster respectively |

**Six green, seven red, three unmeasured.** This is materially different from the 8/9 in
`docs/CI-STATE.md` and different again from the brief. Nobody was lying; the tree moved.

---

## 2. The three things I was asked to do that are already done

I checked each one against the tree instead of against the brief. **Do not redo these.**
Each worker who might touch them is told to verify first and report, not to re-land.

### 2.1 `RED_SELECTOR` / `pl2_red` is fully wired — done 2026-08-10

The brief says *"`pl2_red` is registered nowhere"*. It is registered, in
`pyproject.toml:112`, with `scripts/mi_ratchet.py`'s `PL2_RED_MARKER_DESCRIPTION`
verbatim, and it is **applied to exactly eight tests**:

```
tests/integration/schema/test_mi_ratchet.py:741
tests/integration/schema/test_mi_event_severity.py:617
tests/integration/schema/test_mi_boundary_override.py:655,678,700,728
tests/integration/schema/test_mi_blame.py:747,804
```

`ci.yml:142` reads `RED_SELECTOR: "g4alpha or pl2_red"` and `RED_FLOOR` was raised 5 → 13
to match. The work is done and the file documents its own history.

### 2.2 The MI ratchet already says 21, not 28

`ci.yml:702` reads `"PL-2's red case — 21 of 30 MAINLINE invariants are still pending "`.
The only surviving `28 of 30` strings are in *superseded planning documents* and in
`VIDEO-KIT.md`, which quotes the number **in order to warn the reader off it**. The red
status is untouched, which was the requirement.

### 2.3 `ruff format` is already at zero — and the Windows number is a lie

On this workstation `ruff format --check .` says **243 files would be reformatted**. On a
worktree checked out with `core.autocrlf=false` it says:

```
1433 files already formatted
```

**Zero.** The 243 is entirely a CRLF artefact of this checkout meeting
`ruff.toml`'s `line-ending = "lf"`. The 249-file format commit the brief asks for **must
not be made** — it would rewrite 243 files to no effect on the runner and destroy the
reviewability of every other diff in this wave.

**Every worker who measures ruff, mypy or anything line-ending sensitive MUST do it on an
LF worktree.** The recipe, which I used:

```bash
git -c core.autocrlf=false worktree add --detach <scratch>/lfwt HEAD
cd <scratch>/lfwt && PATH="<repo>/.venv/Scripts:$PATH" python scripts/qa/ruff_ratchet.py
```

---

## 3. What is actually wrong, in the order it must be fixed

### 3.1 One root cause is holding three lanes down

`ci` (9 jobs), `supply-chain` (3 of 3) and `db` all die in the same place:

```
Run ./.github/actions/setup-workspace
##[error]connect ECONNREFUSED 54.185.253.63:443
```

`supply-chain` was **green** at `b0fe884` with no relevant change since. That is the
signature of an *environmental* break, not a repository one:
`.github/actions/setup-workspace/action.yml` installs uv with `uv-version: latest`, and
`step-security/harden-runner`'s `egress-policy: block` refuses a connection it cannot
match to an allowed hostname. The allowlists already name `astral.sh:443`, so the refusal
is happening at an address the allowlist cannot express.

This is **W1**, and it is the only worker with a hard ordering claim on the others:
until it lands, no `ci` job downstream of `setup-workspace` can be observed at all, so
W3's and W4's ruff work cannot be confirmed in CI and W10 cannot falsify `ci`.

### 3.2 The masking commit made the repo's own secret-scanner fire

`1d41442` replaced the real AWS account id with the literal `999999999999`. The scanner
correctly refuses **any** bare 12-digit run:

```
[SEC-ACCOUNT-ID] evidence/deploy/deploy-dry-run.json:409: a bare 12-digit run
'999999999999' survives UUID/digest/decimal masking and has the shape of an AWS account id
```

The checker is right and must not be weakened. The subtlety — and the reason this is a
whole worker — is that lines 409/412 are a **recorded transcript of a real teardown
dry-run**, where `999999999999` was the deliberately-wrong `--expect-account` value that
provoked the refusal. Editing the transcript to satisfy the scanner would turn real
evidence into a forgery. This must be resolved by **re-running the dry-run with a
non-account-shaped expectation and recording what actually happened**.

The same two lines also poison `aws-evidence`'s anti-vacuity job, which reported
`FAMILY red-for-the-wrong-reason: an unmutated copy of evidence/ already fails`. That job
catching this is the best evidence in the tree that the anti-vacuity discipline works.

### 3.3 The ruff *lint* ratchet is genuinely regressed — 17 rules, 7 hard gates

Measured on the LF worktree. These are real and were introduced by `ca912eb`:

```
BLE001 scripts/     0 -> 2   [HARD]      N803   packages/trappoint-*  0 -> 2  [HARD]
E402   scripts/     0 -> 6   [HARD]      N803   tests/                0 -> 2  [HARD]
PTH123 scripts/     0 -> 2   [HARD]      RUF001 packages/trappoint-*  0 -> 1  [HARD]
PTH202 scripts/     0 -> 1   [HARD]      UP030  scripts/              0 -> 5  [HARD]
PLR0912 scripts/    2 -> 7               PLR0915 scripts/             1 -> 7
D102/D105/D107/D401 packages/trappoint-*  +21    E402 tests/ 1 -> 6   ARG002 tests/ 1 -> 4
```

Two of these must **not** be "fixed" by renaming. `modelId` and `contentType`
(`bedrock_backend.py:502`) are **boto3 API parameter names** — renaming them breaks the
call. The `RUF001` hits in `tests/unit/domain/canon/test_idempotence.py` are **deliberate
Unicode test vectors**; the ambiguity is the thing under test. Both need a `# noqa` that
states the reason. Everything else is a real defect to fix at cause.

**Nobody rebaselines.** `qa/ruff-ratchet.json` is owned by W2 alone and its numbers may
fall, never rise. If a residual survives the wave it is reported to W10 and named in
`docs/CI-STATE.md`, not baselined away.

### 3.4 The reds that must stay red, and must say so better

`schema` names two missing producers (`trappoint_ref.clause`, `trappoint_ref.event`),
`custody-chain` names three unimplemented checks, `db-schema` names the catalogue and
`mi-red`. These are correct refusals. The work is to make each name **its missing artefact
and its owner**, in the shape `demo-health` already uses — not to make them green.

---

## 4. What matters most: no green lane may be vacuous

Six lanes are green. A green that cannot fail is worth less than an honest red, and the
Actions tab is now public. Three workers (W8, W9, W10) do nothing but **try to break the
green lanes**: plant a violation, dispatch, prove it goes red *for the planted reason*,
revert, prove it goes green again.

Rules that bind all three:

- **Never push a plant to `master`.** Work on a throwaway branch, dispatch with
  `--ref <branch>`, delete the branch.
- A lane that goes red for a *different* reason than the plant has **not** been falsified.
  `aws-evidence` demonstrates exactly this failure mode today.
- A lane you cannot falsify is **named as unproven in `docs/CI-STATE.md`**. That is a
  successful outcome for a worker, not a failed one.
- Deliverable is an evidence document with run ids, not a workflow edit.

---

## 5. Sequencing

```
W1  (setup-workspace / egress)  ─── unblocks ──▶  W2, W10
W3, W4 (ruff)                   ─── verified by ──▶ W2's ratchet job (needs W1)
W5, W6, W7                      ── independent, start immediately
W8, W9                          ── independent, start immediately (green lanes already run)
W10                             ── last: needs every other worker's measured result
```

W5, W6, W7, W8, W9 have no dependency on W1 and must not wait for it.

---

## 6. Standing rules for every worker

1. **Honesty is the moat and the repo is public.** Never weaken `docs/HONESTY.md`,
   `docs/CI-STATE.md`, or any ratchet to gain a green. A red reporting true
   incompleteness stays red with a sharper message.
2. `continue-on-error` and `|| true` are **banned**. Fix causes, not symptoms. No TODOs.
3. **File ownership is absolute.** Touch only your enumerated paths. If your fix requires
   a file you do not own, report it in your result; do not edit it.
4. **No worker may run `terraform apply`.** `init`, `validate`, `plan`, `show` and
   read-only AWS calls only.
5. **Never print any credential** into your output, into files you do not own, or into
   structured results. Do not rotate the `mainline_judge` password; the orchestrator
   handles it.
6. Measure on an **LF worktree** for anything line-ending sensitive (§2.3).
7. Read CI logs **in the same sitting** you create the run (§0).
8. Python is `D:/CoackroachDBxAWS/mainline/.venv/Scripts/python.exe`; Windows `PYTHONPATH`
   separator is `;`.

---

## 7. The ten workers

| id | title | owns |
|---|---|---|
| W1 | the ECONNREFUSED root cause, and the image-pin restatement | `setup-workspace`, `supply-chain.yml`, `db.yml`, `cloud-verify.yml`, `release-proof.yml` |
| W2 | `ci.yml` — actionlint, the ratchet job, the summary | `ci.yml`, `console.yml`, `qa/ruff-ratchet.json` |
| W3 | seven hard-gate lint breaches in `scripts/` | 4 files under `scripts/` |
| W4 | the Bedrock and test-tree lint breaches | 6 files under `packages/` and `tests/` |
| W5 | the mask that trips the repo's own scanner | `deploy-dry-run.json`, `RUNBOOK.md`, `aws-evidence.yml` |
| W6 | `db-schema` — catalogue, `mi-red`, and the ratchet's wording | `db-schema.yml`, `mi_ratchet.py` |
| W7 | `schema` and `custody-chain` — sharper reds, named owners | `schema.yml`, `custody-chain.yml` |
| W8 | falsify `claims`, `boundary`, `submission` | one evidence doc |
| W9 | falsify `judge-pack`, `release-proof`, `skills`, `console` | one evidence doc |
| W10 | falsify `ci`, `supply-chain`, `mutation-ratchet`; write the board | one evidence doc, `docs/CI-STATE.md` |

Full briefs are carried in the structured result that accompanies this file.

---

## 8. What this wave will not achieve

Stated now so that no one has to discover it at the end:

- `demo-health` stays red until something is deployed. It is a deployment, not a workflow
  edit, and the deploy is the orchestrator's to run.
- `schema` and `custody-chain` stay red. Ten checks and two producers do not exist. This
  wave makes them say so more precisely and names their owners.
- `cloud-verify` and `nightly-differential` need a live cluster this wave does not
  provision. W1 fixes their plumbing; their conclusions are next wave's measurement.
- The `g4alpha` gates and the MI ratchet stay red by declaration.

The honest floor for this wave is roughly **eleven green and six red, every red naming its
missing artefact and its owner** — not seventeen green.
