<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# Can these four green lanes say no? — `judge-pack`, `release-proof`, `skills`, `console`

**Written 2026-08-12 by W9, against `1d41442` on `master`.** Every run id below was created
and read by me in one sitting; GitHub expires this repository's logs quickly and a claim
whose log I did not read is not in this document.

Method, per promise: plant one violation that should break exactly that promise, dispatch
the lane on a throwaway branch with `gh workflow run <lane>.yml --ref <branch>`, read the
log, confirm the red **names what was planted**, then delete the branch. A lane that goes
red for some other reason has not been falsified. **No plant was ever pushed to `master`;
all sixteen plant branches were deleted** (`git ls-remote origin 'refs/heads/w9/*'` → 0).

Every plant lived on a branch cut from `1d41442`, so every result below describes the
workflow files **as committed at HEAD**, not as they exist in anyone's working tree. That
distinction cost me one experiment and produced one of the two findings — see §2.3.

---

## 0. The board, and the controls

`console`'s conclusion at `1d41442` was unknown when the plan was written. **Measured:
run `31596648619`, conclusion `success`.** All four lanes were green at HEAD.

Reverting is not a separate step here — the plants only ever existed on branches — so the
"green again after revert" control is `master` itself, re-dispatched by me in this sitting
after every plant had been read:

| lane | control run on `master` | conclusion |
|---|---|---|
| `judge-pack` | `31605705752` | **success** |
| `skills` | `31605708672` | **success** |
| `console` | `31605711724` | **success** |
| `release-proof` | `31605714844` | **success** |

Three plant runs also carry an *in-run* control, which is stronger than a same-SHA rerun
because it rules out flake: on `31604861940` the `proofs` job was green while the other two
jobs went red, on `31604901540` the `can-fail` job was green while `prove` went red, and on
`31605910666` three of four jobs were green while the fourth went red. Each of those greens
is the unmutated half of the same run that produced the red.

**26 distinct promises were tested. 21 were falsified with a named red. 5 could not be, and
two of those five are not "untested" but *proved unfalsifiable* — §5.**

---

## 1. `judge-pack`

Four jobs. `green` is gated `needs: [red, anti-vacuity]`, which matters: a defect in the
pack itself is caught by the two red halves and the `green` job never runs, so several of
`green`'s promises can only be reached by a plant that the red halves do not see.

### 1.1 `red` — `cli.py self-test` fires on every planted family

**Plant** (branch `w9/jp-a`): renamed the `str.replace` anchor inside
`judge/selftest.py::_mutate_view_columns` from `"site_id, state,"` to
`"site_id, w9_renamed_away,"` — the exact rot the job's own header warns about, planted
from the mutation side so the pack itself is untouched.

**Run `31604810879` → failure.** The log names it:

```
MISSED view-columns: a prompt selects a column the shipped view does not project
```

**Falsified.** The red named the plant.

### 1.2 `anti-vacuity` — three separate promises, all falsified in one run

Same run `31604810879`, second plant in the same branch: `Q06.defined_in` in the **real**
`QUESTIONS.yaml` was pointed at `0161_w9_absent_from_the_repository.sql`, so the unmutated
pack already fails the `path` check.

The job collects every failure before raising, so one run produced all three annotations:

```
##[error]VACUOUS FAMILY path: the real pack already produces a `fail` for this check
         WITHOUT the planted `dangling authority` violation, so `self-test` would report
         it caught even if the mutation did nothing.
##[error]NO-OP MUTATION view-columns: `renamed column` left the pack byte-identical.
##[error]UNCAUGHT FAMILY view-columns: the planted `renamed column` violation was not
         reported by the validator.
```

**All three falsified**, each naming its plant. This job is the best-instrumented
anti-vacuity construct I tested in any of the four lanes, and it is not decoration.

### 1.3 `not-run-is-not-a-pass` — a run with no cluster must exit 3

**Plant** (branch `w9/jp-b`): `runner.py::RunReport.exit_code` — `if not self.ran: return 3`
changed to `return 0`.

**Run `31604833810` → failure**:

```
##[error]run --via sql exited 0 with nothing to talk to.
```

**Falsified**, named. **Caveat:** the step loops `sql` then `mcp` and exits on the first
mismatch, so the `mcp` channel's half of this promise was not separately observed. Both
channels share `exit_code()`, so the plant would have broken both, but I only have a run
id for `sql`.

### 1.4 `green` — `render --check`: the page a judge reads matches the pack

**Plant** (same branch `w9/jp-b`): one line appended to the generated `judge/PACK.md`.

**Run `31604833810` → failure**:

```
PACK.md has DRIFTED from QUESTIONS.yaml. Re-run without --check.
```

**Falsified**, named. `red` and `anti-vacuity` were green in this same run, so `green` was
reached and the drift is attributable to the plant alone.

### 1.5 `green` — `validate --strict`: every prompt legal, every negative refused

Reaching this required a plant outside the nine families the red halves police. The check
names are enumerable from `pack.py`/`drift.py`; `must-fail-because` is not one of the nine.

**Plant** (branch `w9/jp-c`): removed `must_fail_because` from negative `N01` in
`QUESTIONS.yaml`. Verified locally first that `cli.py self-test` still exits 0 — otherwise
the `green` job would have been skipped and the experiment would have measured nothing.

**Run `31605910666` → failure**, with `red`, `anti-vacuity` and `not-run-is-not-a-pass` all
**green in the same run**:

```
FAIL  [must-fail-because] N01: a negative must say why it has to fail
1 failures, 0 warnings, 15 notes
```

**Falsified**, named, with a three-job in-run control.

### 1.6 `green` — the `envelope` step. **NOT FALSIFIABLE, and this is a finding.**

`cli.py envelope` prints three things and its exit code depends on only one of them:

```python
return EXIT_WRONG if cross.disagreements else EXIT_OK
```

A declared-envelope key printed as `DISAGREES (pack says …)` does not affect the exit code.
A bound EXPLAIN printed as `DOES NOT FIT` does not affect the exit code. And a cross-check
that **never ran** has no disagreements, so it exits 0.

No plant was needed. **The control run on `master`, `31605705752`, conclusion `success`,
carries this in the log of the step titled "The limits, the bound EXPLAIN lengths, and the
cross-check":**

```
cross-check: NOT RUN — packages/mainline-mcp is not importable in this environment
(No module named 'mainline_mcp'); the second implementation of the envelope was NOT
consulted. This is not a pass.
```

The step exited 0. The message says *"This is not a pass"* and it was recorded as one.

It gets sharper. The next step, `validate --strict --verbose`, is justified in the
workflow by the comment *"a warn from this validator means AN AUTHORITY WAS ABSENT and a
check did not run"*. In the same run it printed:

```
second implementation of the envelope
  NOT RUN  packages/mainline-mcp is not importable in this environment …
0 failures, 0 warnings, 15 notes
```

**Zero warnings for the one authority that is genuinely absent.** `judge-pack` installs
only PyYAML, so `mainline_mcp` has never been importable in this lane and the second
implementation of the envelope has **never been consulted in CI** — in the lane whose own
header says *"a workflow that tolerates NOT RUN as success is the failure this whole pack
exists to refuse"*, and which carries an entire job (`not-run-is-not-a-pass`) enforcing
exactly that rule for `cli.py run`.

**Mitigation, stated so this is not read as worse than it is:** the two things the
`envelope` step prints but does not gate on — envelope agreement and bound length — *are*
enforced, as `envelope-agreement` and `bound-length` findings inside `validate --strict`
in the same job. What is unenforced is the **cross-check against the second
implementation**, and that one is unenforced everywhere.

*Owner: the `envelope` step and `cmd_envelope`'s exit rule are not mine. Reported, not
edited.*

---

## 2. `release-proof`

The lane whose green tick most directly underwrites the project's headline claim. I gave
it five experiments.

### 2.1 The gate itself. **Falsified, caveat-free — the most important result here.**

**Plant** (branch `w9/rp-gate-removed`): one line in the tracked migration
`verticals/mainline/db/migrations/0050_permit.sql` —

```
CONSTRAINT gate_closed_when_issued CHECK (state <> 'merged' OR open_blocking = 0)
                                                            ^^^^^^^^^^^^^^^^^^^^^  becomes  >= 0
```

**Run `31604562363` → failure. Both jobs went red, and each named the plant.**

`prove`:

```
REFUSAL       ADMITTED [00000] None (None)
  ! CF-01: the merge was ADMITTED with an open obligation
  ! CF-03: expected SQLSTATE P0001, observed 23503
  ! CF-03: expected exhibit 'mainline.fn_permit_merge_gate', observed 'legal_edge'
VERDICT       NOT PROVEN
```

`can-fail` — and this is the second half of the answer to the question the brief asked,
*"can its gate be removed without the lane noticing?"*:

```
##[error]PLANTED FAMILY gate-disabled: the anchor "CHECK (state <> 'merged' OR
open_blocking = 0)" is no longer present in 0050_permit.sql, so NOTHING was planted and
this control is vacuous. A no-op mutation is how an anti-vacuity job silently stops being
one.
```

So the answer is **no, twice**: removing the gate turns `VERDICT PROVEN` into
`VERDICT NOT PROVEN` with the failing clause named, *and* the standing negative control
notices that its own anchor has gone and refuses to report a vacuous pass. This is the
strongest result in this document.

Incidental observation worth recording: with the CHECK weakened, the drift refusal came
back as `23503`/`legal_edge` — a foreign key, not the gate. A lane that only asked *"did
something raise?"* would have called that a refusal. `CF-03` compares SQLSTATE **and**
exhibit, and caught it.

### 2.2 The release-suite gate — the 15-assertion floor

**Plant** (branch `w9/rp-suite-shrunk`): deleted `test_the_proof_exits_zero` from
`tests/release/test_gate_refusal_proof.py`, leaving 14.

**Run `31604901540` → failure**, `prove` red, `can-fail` **green in the same run**:

```
release suite: 14 test(s), 14 skipped, 0 failed
##[error]only 14 release assertion(s) ran; this module carried 15 on 2026-08-10, and an
assertion deleted rather than fixed is a claim quietly withdrawn
```

**Falsified**, named. Two things fall out of the same log. First, the standing `RED — the
gate refuses a run where nothing was proved` control **still reaches its state**: `14
skipped` on a closed port confirms the all-skipped condition that step exists to describe
is real, not stale. Second, the step's own message assertion bit correctly — with the count
gate firing first, the gate's message no longer names the skips, and the step said so
rather than accepting a non-zero exit as evidence:

```
##[error]the gate exited 1 but its message does not name the skips.
```

That is a check checking its own check. It works.

### 2.3 The image pin. **NOT FALSIFIABLE in the direction that matters — the second finding.**

I first planted the removal of the `# trappoint:crdb-image-pin` marker from `compose.yaml`
(branch `w9/rp-nopin`). **Run `31604914296` → success.** That surprised me, and the reason
is worth stating because it is a trap for anyone auditing this repository: the
`release-proof.yml` in the working tree carries **uncommitted edits by W1** that rewrite
this step to read the marker. The file *committed at `1d41442`*, which is what CI runs,
still carries the old step:

```bash
pinned="cockroachdb/cockroach:v26.2.5"
found="$(sed -n 's|.*\(cockroachdb/cockroach:v[0-9]\{1,\}\.[0-9]\{1,\}\.[0-9]\{1,\}\).*|\1|p' compose.yaml | head -n1)"
if [ -n "$found" ] && [ "$found" != "$pinned" ]; then … exit 1; fi
```

So I tested the committed logic from both sides.

**Same-shaped tag** (branch `w9/rp-pin-sameshape`, `compose.yaml` → `…:v25.1.0`).
**Run `31605448626` → failure**:

```
##[error]compose.yaml pins cockroachdb/cockroach:v25.1.0 but this workflow pins
cockroachdb/cockroach:v26.2.5.
```

Falsified in that direction. A bonus fell out: the `Upload the evidence` step then errored
with `No files were found with the provided path: …proof-ci-31605448626.json`, which
confirms `if-no-files-found: error` bites rather than silently uploading nothing.

**Differently-shaped tag** (branch `w9/rp-pin-othershape`, `compose.yaml` →
`…:latest-v26.2`, verified on the branch at `compose.yaml:31`).
**Run `31605452346` → SUCCESS. Both jobs green.** The step titled *"Assert the image pin
agrees with compose.yaml"* printed:

```
using cockroachdb/cockroach:v26.2.5
```

`sed` matched nothing, `found` was empty, the `if` was skipped, and the lane started a
`v26.2.5` node, proved the central claim on it, and reported agreement — while
`compose.yaml` named a different tag. **On `master` today, `release-proof` cannot detect a
pin disagreement unless the new tag happens to match `v<N>.<N>.<N>`.** The workflow's own
comment names this exact defect ("`sed` matched `…:vN.N.N` only … the workflow would have
gone on using its own stale literal while reporting agreement") — but that comment is in
W1's **uncommitted** rewrite. The defect is live on `master` and the fix is not.

*This is W1's file. Reported, not edited. If W1's rewrite lands, this promise becomes
falsifiable and run `31604914296` becomes the plant that should then go red.*

### 2.4 The `can-fail` job's second family — `expected-sqlstate`

Not re-planted. Verified to still bite by two independent facts: the anchor
`ERRCODE = 'P0001'` is present in `0115_fn_permit_merge_gate.sql` (3 occurrences), so the
mutation is not a no-op; and the green control `31605714844` requires that mutation to make
`gate_refusal.py` exit non-zero *and* emit both `CF-03: expected SQLSTATE P0001, observed
22000` and `NOT PROVEN`, or the job reds. §2.1 proved the anchor-absence guard on the
sibling family through the identical loop. **Verified still biting; not independently
planted.**

---

## 3. `skills`

Three jobs, seven promises tested, seven falsified.

### 3.1 `proofs` — the unwelding matrix

**Plant** (branch `w9/skills-a`): `assert_gate_refuses.py::REFERENCE_SCHEMA`,
`CHECK (state <> 'closed' OR open_blocking = 0)` → `>= 0`.

**Run `31604638902` → failure**:

```
! the database ADMITTED the illegal history. Nothing refused it: no CHECK, no foreign
  key, no trigger. This is the failure this script exists to find.
[FAIL] welded            close_with_open_obligation  23514 / gate_closed_when_issued → ADMITTED
[PASS] check_dropped     close_with_open_obligation  ADMITTED → ADMITTED
```

**Falsified**, named. Run `31604861940` (a different branch) had this job **green**, which
is the control confirming the red belongs to this plant.

### 3.2 `claims` — we claim the filing, never the merge

**Plant** (same branch): one line appended to `README.md`.
**Run `31604638902` → failure**:

```
##[error]this line claims an upstream merge: W9 PLANT: our contribution was merged into
upstream on 2026-08-13.
```

**Falsified**, named.

### 3.3 `validate` — the "COPY IS NOT CLEAN" guard on the marketplace red half

**Plant** (same branch): `./skills/w9-a-skill-that-does-not-exist` appended to
`marketplace.json`'s `plugins[0].skills`.
**Run `31604638902` → failure**:

```
##[error]COPY IS NOT CLEAN: a byte copy of the marketplace is already refused, so no
refusal below is attributable to a plant:
##[error]declared skill path has no SKILL.md: ./skills/w9-a-skill-that-does-not-exist
```

**Falsified**, named. This is the guard whose absence produced `aws-evidence`'s
red-for-the-wrong-reason. Here it works: the four planted marketplace families all printed
`REFUSED …` *and* the job still went red, because the clean copy was not clean.

### 3.4 `claims` — the upstream tree carries no branded vocabulary

**Plant** (branch `w9/skills-b`): one paragraph mentioning `TRAPPOINT` appended to the
upstream `SKILL.md`.
**Run `31604861940` → failure**:

```
##[error]branded vocabulary 'TRAPPOINT' in a file destined for another repository
```

**Falsified**, named.

### 3.5 `validate` — our validator, warnings promoted to errors

**Plant** (same branch): removed `description:` from
`skills/designing-vector-recall-prefixes/SKILL.md` — a skill the red half does not use, so
the red steps stayed green and the failure is attributable to the green step.
**Run `31604861940` → failure**:

```
##[error]frontmatter is missing `description`
```

**Falsified**, named.

### 3.6 `proofs` — the three "no database required" self-tests

Each plant neuters the **checker**, not the fixture, which is the regression that matters.
Every one was verified locally on `.venv/Scripts/python.exe` before dispatch. In all three
runs the `validate` and `claims` jobs were **green**, isolating the red to the `proofs` job.

| self-test | plant | run | the log |
|---|---|---|---|
| merkle | `verify()` returns an ok `Report` unconditionally | `31605607977` → failure | `[FAIL] 18 rows missing from the END are caught` · `[FAIL] one row altered in the middle is caught` · `[FAIL] two rows swapped are caught` · `self-test: 5 case(s) wrong` |
| vector plan | `assert_index_used()` returns `{"ok": True}` | `31605616658` → failure | `[FAIL] no vector search at all: accepted` · `[FAIL] prefix not constrained: accepted` · `self-test: 3 case(s) wrong` |
| diagnostic parser | the `_SQLSTATE` regex loses its colon | `31605692351` → failure | `[FAIL] check violation names its constraint: None / gate_closed_when_issued` · `parser self-test: 4 case(s) wrong` |

**All three falsified**, each naming its plant.

### 3.7 `validate` — `skills-ref`, the specification's reference implementation

This one needed care. Every violation I could construct — over-long description,
name/directory drift — is *also* caught by `skills/validate-spec.py`, which runs one step
earlier, so a naive plant would prove nothing about `skills-ref`. I probed both validators
locally (`npx --yes skills-ref validate`, node v24.14.0) to establish that.

**Plant** (branch `w9/skills-ref`), two lines, simulating the regression that actually
matters — *our validator stops checking a rule; does the reference implementation still
catch it?*

1. `skills/validate-spec.py:203` → `if False and name != directory.name:`
2. `skills/designing-vector-recall-prefixes/SKILL.md` → `name: designing-vector-recall-prefix`

Verified locally that our validator then reports `3 skill(s), 0 error(s), 0 warning(s)`.

**Run `31606296106` → failure.** Step conclusions confirm the isolation: the two RED steps
and `Our validator, warnings promoted to errors` all **succeeded**; `skills-ref` failed:

```
Validation failed for skills/designing-vector-recall-prefixes:
  - Directory name 'designing-vector-recall-prefixes' must match skill name
    'designing-vector-recall-prefix'
##[error]skills-ref rejected this skill
```

**Falsified**, named. `skills-ref` is a genuinely independent check, not a second opinion
that agrees by construction.

---

## 4. `console`

`console`'s conclusion at `1d41442` is **`success`**, run `31596648619` — the measurement
the plan asked for.

### 4.1 `pnpm run ci` on the tracked tree, and the `can-fail` green control

**Plant** (branch `w9/console-eslint`): `src/app/w9_planted_register_violation.ts`
containing `import 'three';` — the same family the standing `can-fail` job plants into a
scratch copy, planted here into the tracked console instead, so it hits both jobs.

**Run `31604695307` → failure. Both jobs red, each naming the plant.**

`ci`:

```
##[error]  1:1  error  'three' import is restricted from being used by a pattern.
EVIDENCE register: no GPU rendering. Only src/features/ancestry/render3d/** may import a
3D library (ui.md §1.1)  no-restricted-imports
```

`can-fail`, at `GREEN CONTROL — the unmutated copy passes, so every red below is
attributable`, naming the copied plant by path:

```
…/console-mutant/src/app/w9_planted_register_violation.ts
```

**Falsified**, named, twice. The green control is the load-bearing part of the standing
`can-fail` job — it is what makes the seven planted families attributable — and it bites.

### 4.2 `pnpm install --frozen-lockfile`

**Plant** (branch `w9/console-pin`): `gsap: 3.13.0` added to `package.json` `dependencies`
without touching `pnpm-lock.yaml`.
**Run `31605487354` → failure**:

```
[ERR_PNPM_OUTDATED_LOCKFILE] Cannot install with "frozen-lockfile" because pnpm-lock.yaml
is not up to date with <ROOT>/package.json
```

**Falsified**, named.

### 4.3 "The pin that was requested is the pin that arrived". **NOT FALSIFIABLE.**

Same branch and run: `packageManager` was also moved from `pnpm@11.5.3` to `pnpm@11.5.2`.

**The step passed.** From run `31605487354`'s step list —
`The pin that was requested is the pin that arrived → success` — and its log:

```
package.json packageManager : pnpm@11.5.2
pnpm on PATH                : 11.5.2
```

`pnpm/action-setup` is given no `version:` input; it derives the version **from the same
`packageManager` field** the step then compares against. Both operands are one constant
read twice, so moving the pin moves both together and the comparison can never see a drift.
This is precisely the "two copies of the same constant" shape that `release-proof`'s own
image-pin comment condemns, inverted: here there are not two copies, there is one copy
compared with itself.

Stated exactly: the step is **not wholly** vacuous — it would fail if `pnpm/action-setup`
silently failed to honour `packageManager` and a different pnpm shadowed it on `PATH`. But
it cannot detect the thing its name describes, and no plant to `package.json` can make it
red.

*Owner: `console.yml` is W2's. Reported, not edited.*

### 4.4 The seven `can-fail` families

Not individually re-planted; verified to still bite by construction plus the HEAD control
`31605711724` (green). The job requires, for each of the seven, that the **composite**
`pnpm run ci` exits non-zero *and* that its output contains every needle for that family.
A family that stopped failing reports `PLANTED FAMILY … EXITED 0`; a needle that went stale
reports `… never names [...]`. So a green on this job is a positive statement about all
seven, not an absence of evidence — and it is why a sub-command being quietly dropped from
`pnpm run ci` would be caught here (the corresponding family would exit 0). §4.1 separately
proves the green control that makes those seven attributable. **Verified still biting; not
independently planted.**

---

## 5. The promises I could NOT falsify

An honest unproven beats a decorative green. Five entries; the first three are stronger
than "unproven" — they are **proved unfalsifiable**, with a run id showing the lane green
over a real violation.

1. **`release-proof` — "Assert the image pin agrees with compose.yaml", for any tag not
   matching `v<N>.<N>.<N>`.** Run `31605452346`, **success**, with `compose.yaml` pinning
   `cockroachdb/cockroach:latest-v26.2` and the job printing `using
   cockroachdb/cockroach:v26.2.5`. The lane proved the central claim on a node whose
   version `compose.yaml` does not name, and called that agreement. Falsifiable only for
   same-shaped tags (run `31605448626`, failure). W1's uncommitted rewrite of
   `release-proof.yml` fixes this; it is **not on `master`**.

2. **`judge-pack` — the `envelope` step's cross-check, and `--strict`'s promise to flag an
   absent authority.** Run `31605705752`, **success**, printing `cross-check: NOT RUN …
   This is not a pass.` and `0 failures, 0 warnings`. `cmd_envelope` returns non-zero only
   on `cross.disagreements`; a check that never ran has none. `mainline_mcp` is not
   installed by this lane, so the second implementation of the envelope **has never been
   consulted in CI**. Envelope agreement and bound length are still enforced by
   `validate --strict`; the cross-check is enforced by nothing.

3. **`console` — "The pin that was requested is the pin that arrived".** Run `31605487354`,
   step **success** at `packageManager: pnpm@11.5.2` / `pnpm on PATH: 11.5.2`. The check
   compares a field with the pnpm that was installed *from that field*. No edit to
   `package.json` can make it red.

4. **`judge-pack` — `not-run-is-not-a-pass` for the `mcp` channel specifically.** Run
   `31604833810` falsified the promise for `sql`; the step exits on the first mismatch, so
   the `mcp` iteration never executed. Both channels share `RunReport.exit_code()`, so the
   plant would have broken both — but I have no run id for `mcp`, and a shared code path is
   an argument, not a measurement.

5. **Six promises verified to still bite, but not independently planted by me** — each
   guarded by a construct that reds when its own plant stops working, which is why I ranked
   them below the twenty-one above rather than re-planting them:
   `release-proof can-fail`'s `expected-sqlstate` family (§2.4); `console can-fail`'s seven
   families (§4.4); the four `ADMITTED` rows of the skills unwelding matrix (my plant broke
   the `welded` row only); `skills proofs`' "no third-party packages are installed" step;
   the `DISPARAGE` half of the `skills claims` regex (only the `MERGE` half was planted);
   and the three lanes' "the tracked tree was never mutated" steps, which would need a job
   that mutates its own checkout.

---

## 6. Every run in this document

| lane | branch (deleted) | plant | run | conclusion |
|---|---|---|---|---|
| `console` | — | none (HEAD measurement) | `31596648619` | success |
| `release-proof` | `w9/rp-gate-removed` | gate weakened to a tautology | `31604562363` | **failure** |
| `release-proof` | `w9/rp-suite-shrunk` | one release assertion deleted | `31604901540` | **failure** |
| `release-proof` | `w9/rp-nopin` | image-pin marker removed | `31604914296` | success *(HEAD's step does not read the marker)* |
| `release-proof` | `w9/rp-pin-sameshape` | `compose.yaml` → `v25.1.0` | `31605448626` | **failure** |
| `release-proof` | `w9/rp-pin-othershape` | `compose.yaml` → `latest-v26.2` | `31605452346` | success — **vacuity finding** |
| `release-proof` | `master` | none (control) | `31605714844` | success |
| `judge-pack` | `w9/jp-a` | selftest anchor renamed; pack points at an absent migration | `31604810879` | **failure** |
| `judge-pack` | `w9/jp-b` | no-cluster run exits 0; `PACK.md` drift | `31604833810` | **failure** |
| `judge-pack` | `w9/jp-c` | a negative loses `must_fail_because` | `31605910666` | **failure** |
| `judge-pack` | `master` | none (control) | `31605705752` | success — **`envelope` finding** |
| `skills` | `w9/skills-a` | reference gate weakened · merge claim · dangling marketplace path | `31604638902` | **failure** |
| `skills` | `w9/skills-b` | branded vocabulary upstream · skill loses `description` | `31604861940` | **failure** |
| `skills` | `w9/skills-merkle` | merkle verifier accepts every restore | `31605607977` | **failure** |
| `skills` | `w9/skills-vector` | prefix-index assertion accepts every plan | `31605616658` | **failure** |
| `skills` | `w9/skills-parser` | diagnostic parser stops reading SQLSTATE | `31605692351` | **failure** |
| `skills` | `w9/skills-ref` | our validator neutered · shipped skill name drifts | `31606296106` | **failure** |
| `skills` | `master` | none (control) | `31605708672` | success |
| `console` | `w9/console-eslint` | 3D import in the EVIDENCE register | `31604695307` | **failure** |
| `console` | `w9/console-pin` | `packageManager` moved · dependency without lockfile | `31605487354` | **failure** |
| `console` | `master` | none (control) | `31605711724` | success |

Sixteen plant branches created, sixteen deleted, none merged, `master` never touched.
