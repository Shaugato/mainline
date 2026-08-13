<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# Anti-vacuity: which lane can prove it is able to fail

**Measured 2026-08-10** against `github.com/Shaugato/mainline`, branch `master`. Every
number and every quoted message below came from a command that was run; the commands are
in §4.

A green lane that cannot go red is worse than a red one. It occupies the place a check
would occupy, it reports success for an assertion nobody made, and — on a project whose
entire pitch is that its greens mean something — it is the one defect that cannot be
argued away. This page is the census: **one row per workflow in the repository**,
including the rows that admit no negative control exists.

The shape of a negative control here is fixed, and three lanes had it before this wave
(`claims`, `judge-pack`, `submission`):

> copy the lane's real input into a scratch directory, plant ONE violation per failure
> family the lane claims to catch, run the lane's OWN checker against the mutated copy,
> and assert both that it exits non-zero AND that the message names the planted family.

The last clause is not decoration. **An assertion that a program failed, without checking
why, passes when the program fails to start.** Every control on this page asserts a
substring of the refusal, and every one of them is a standing job rather than a one-off
branch push: a push proves a lane could fail on one day, a job proves it on every run for
as long as the lane exists, and the job is the artefact a judge can read.

---

## 1. The census

| workflow | job that proves it can fail | families it plants | tracked tree mutated? |
|---|---|---|---|
| `claims` | `claim hygiene (red half, then green half)` · **and** `the red half is red for the reason it claims` | scanner `--self-test` plants **4** of 21 rules; the committed fixture `claim-hygiene-red.md` fires all **21**; the meta-job asserts the union covers every declared rule, that each fixture sentence is refused **alone**, and that a copy with the plants removed exits **0** | no — `$RUNNER_TEMP` only, asserted |
| `judge-pack` | `the validator fires on every planted violation` · `a run with no cluster exits 3, never 0` · `the red half is red for the reason it claims` · **and, from 2026-08-13, `the envelope step goes red for each row it prints`** (§7.1) | 9 pack mutations (renamed column, negative gone green, unbounded claim, envelope loosened, index hint dropped, prefix widened, decorative completeness column, dangling `defined_in`, prompt dropped) + claim-hygiene + bound-length; the meta-job asserts each mutation **changes the document**, each is **caught**, and **none** of the nine checks fails on the unmutated pack. The envelope job adds 5 plants — a module constant, a pack constant, a widened EXPLAIN, both judge-side files drifting together, and the second implementation absent — each required to exit 1 **and to name its own row** | no — in-memory copies and temporary copies, both asserted |
| `console` | `RED — pnpm run ci fails on every planted violation family` | `eslint-register-boundary`, `typescript-type-error`, `vitest-failing-case`, `bundle-over-budget`, `lazy-boundary-broken`, `denied-dependency-by-name`, `non-permissive-licence-in-the-runtime-closure` — **each driven through the whole `pnpm run ci` chain**, not through its own sub-command | no — an untracked sibling copy at the same depth (§5.2), removed and asserted gone |
| `release-proof` | `RED — the proof reports NOT PROVEN when the gate is removed` · **and** the `RED — the gate refuses a run where nothing was proved` step inside `the database refuses the merge` | `gate-disabled` (the CHECK weakened to a tautology in a scratch copy of `0050_permit.sql`), `expected-sqlstate` (`fn_permit_merge_gate` raising `22000`, in a copy of `0115`), `nothing-was-proved` (the release suite with no reachable cluster) | no — `$RUNNER_TEMP` migration copies + step-scoped `env:`, asserted |
| `skills` | `spec conformance (red half, then green half)` · **and** the pre-existing `RED BEFORE GREEN` step in `every shipped script proves it can fail` | spec: `missing-required-field`, `malformed-name`, `dangling-link`, `out-of-spec-field`, `empty-body`; marketplace: `dangling-skill-path`, `upstream-staging-shipped`, `plugin-without-source`, `missing-top-level-key`; plus the unwelded-schema gate assertion that must exit 1 | no — `$RUNNER_TEMP` copies, asserted |
| `supply-chain` | `SECURITY CLAIM — mainline-gate-svc's dependency closure contains no model SDK`, step `RED — four planted violations, each refused BY NAME` | `model-sdk-in-the-export` (`boto3`), `model-sdk-in-the-tree` (`anthropic`), `workspace-member-lost` (the anti-vacuity guard), `unreadable-path-entry` | no — `$RUNNER_TEMP` copies of the two witnesses, asserted |
| `cloud-verify` | `is there a Cloud cluster to verify against? (and can it say no?)` · **and** `a real 40001 RETRY_SERIALIZABLE, and the loop that must not swallow it` | credential: no secret → `has-cluster=false` naming `CRDB_CLOUD_DSN`; loopback / `.local` DSN → **exit 1**, never a quiet false; the `verify` gate and its complement are both still declared. retry: `not-exercised`, `wrong-retry-reason`, `retry-never-taken`, `retry-does-not-converge`, `budget-swallows-40001`, `budget-misclassifies-40001` | no |
| `submission` | `the submission gate can say no` | pre-existing; not owned by this wave and not re-examined here | not examined |
| `ci` | **none** | — | — |
| `db` | **none** | — | — |
| `db-schema` | **none** | — | — |
| `boundary` | partial — `test_no_model_in_closure.py` carries planted-reach tests, and the A6 rule gained a positive control (`1e699ba`), but no lane-level planted-violation job | — | — |
| `custody-chain` | **none** | — | — |
| `schema` | **none** | — | — |
| `mutation-ratchet` | **by construction** — the lane IS a mutation harness; its number is the proportion of planted mutants the suite kills. Its one *assertion* was falsified by W10 on the arithmetic half and found **satisfiable three ways without its claim being true** on the survivor half (§7.3) | every mutant the ratchet generates | — |
| `nightly-differential` | **none** | — | — |
| `demo-health` | **none** — and it is red for a true reason (no demo deployed), so a negative control would be measuring a lane that is already reporting its own incompleteness | — | — |

**Seven lanes have a standing negative control after this wave, against three before it.
Eight of the eighteen workflows still have none, and the rows above say so rather than
omitting them.**

---

## 2. The three findings this census produced

### 2.1 `release-proof` reported the product's central claim as held on a run that proved nothing

`tests/release/test_gate_refusal_proof.py` **skips** when the proof cannot reach a
cluster. That is correct — "there was no database" is not evidence that the gate admitted
anything. But **pytest exits 0 when every test skips**, and the workflow step read:

```yaml
run: python -m pytest tests/release/test_gate_refusal_proof.py -q --no-header -p no:cacheprovider
```

Measured on the pinned interpreter, with every DSN spelling pointed at a closed port:

```
$ MAINLINE_TEST_DSN=…:26299 python -m pytest tests/release/test_gate_refusal_proof.py \
      -q --no-header -p no:cacheprovider --crdb=none -rs
gate_refusal: could not reach the cluster: connection timeout expired
SKIPPED [1] tests/release/test_gate_refusal_proof.py:352: the proof could not reach a cluster (exit 2) …
15 skipped in 21.47s
EXITCODE=0
```

So the step that asserts *the database refuses the merge* would have reported success on a
run in which the database was never asked. It is now gated on a junit report: fewer than
15 assertions, any skip, or any failure is a red step that names itself, and the negative
control drives the same conditions through the same gate and requires it to refuse.

### 2.2 `claim_hygiene.py --self-test` plants 4 of 21 rule families

The step is named *"RED — the scanner fires on every planted violation family"*, and it
does — but `SELF_TEST_EXPECTED` holds four rule ids while `RULES` declares twenty-one:

```
declared: 21 · SELF_TEST_EXPECTED: 4
declared - expected: MNC-02, MNC-03, MNC-04, MNC-05, MNC-06, MNC-07, MNC-08, MNC-09,
                     MNC-10, MNC-11, MNC-12, MNC-13, MNC-14, MNC-16, MNC-17, MNC-18, MNC-19
```

The other seventeen are covered — the committed fixture `claim-hygiene-red.md` fires
**all twenty-one**, measured. So the lane's coverage is complete today, by two mechanisms
rather than one, and neither of them said so. The new job asserts the **union**, and names
any rule that no planted violation reaches. Adding a twenty-second rule without a planted
sentence now turns the lane red.

### 2.3 `supply-chain`'s SECURITY-CLAIM-BROKEN branch had never executed

The job's own header records six runs (`31372088231`, `31372058080`, `31371945797`,
`31371788606`, `31371718663`, `31371705079`) in which it failed on its **anti-vacuity
guard** and the security branch was never taken. The guard was then repaired — correctly —
but the branch the §8.2 claim actually rests on remained untested code. It now runs four
planted violations through the same file on every run of the lane, and the assertion was
moved into a file so the red half and the green half cannot drift into two programs.

---

## 3. What each control refuses to accept as evidence

| banned | why |
|---|---|
| `continue-on-error` | turns every assertion in the job into a comment |
| `\|\| true` | the same, one line at a time. Three occurrences inside the lanes owned by this wave were removed and replaced with explicit status handling (`claims.yml`'s honesty-card ledger, `skills.yml`'s pip listing, `release-proof.yml` and `cloud-verify.yml`'s image-pin greps) |
| a control that asserts only a non-zero exit | a program that fails to **start** also exits non-zero. Every family here asserts a substring of the refusal |
| a control that mutates the tracked tree | seven of the eight jobs end with `git status --porcelain --untracked-files=no` asserted empty |
| a mutation whose anchor may have moved | a `str.replace` against a renamed anchor plants nothing and raises nothing. `release-proof`'s control asserts the anchor exists before replacing it; `judge-pack`'s meta-job asserts each of the nine mutations **changes the document** |
| a copy that is not clean | if the scratch copy is already refused, a refusal after planting is attributable to the copying. `skills`, `supply-chain`, `console` and `claims` all run the unmutated copy first |

---

## 4. The commands, and what they printed

Run on `D:/CoackroachDBxAWS/mainline` with `.venv/Scripts/python.exe` (CPython 3.13),
Node v24.14.0, pnpm 11.5.3, and CockroachDB CCL v26.2.5 at
`postgresql://root@127.0.0.1:26257/defaultdb?sslmode=disable`.

**`release-proof` — the gate removed.** A scratch copy of the 271-file migration tree with
`gate_closed_when_issued` weakened to `CHECK (state <> 'merged' OR open_blocking >= 0)`:

```
chain         271/271 applied, 0 failed, 58.271s
REFUSAL       ADMITTED [00000] None (None)
  ! CF-01: the merge was ADMITTED with an open obligation
VERDICT       NOT PROVEN                                        (exit 1)
```

**`release-proof` — the SQLSTATE changed.** `fn_permit_merge_gate` raising `22000`:

```
REFUSAL       REFUSED [23514] gate_closed_when_issued (reported)
DRIFT         REFUSED [22000] mainline.fn_permit_merge_gate (parsed)
  ! CF-03: expected SQLSTATE P0001, observed 22000
VERDICT       NOT PROVEN                                        (exit 1)
```

The baseline, for comparison, on the unmutated tree: `271/271 applied`, `PROJECTION 10/10
held`, `REFUSAL REFUSED [23514]`, `DRIFT REFUSED [P0001]`, `ADMISSION ADMITTED [00000]`,
`caveats (none)`, `VERDICT PROVEN`, exit 0.

**`cloud-verify` — a real `40001 RETRY_SERIALIZABLE`.** A constructed read-write cycle,
not accidental contention:

```
observed sqlstate : 40001
observed message  : restart transaction: TransactionRetryWithProtoRefreshError:
                    TransactionRetryError: retry txn (RETRY_SERIALIZABLE): "sql txn" …
run_gate attempts : 2  retries recorded: [(0, '40001', 0.01663495554053103)]
max_attempts=1    : RetryBudgetExhausted: 40001 after 1 attempt(s) in 1.013s:
                    the transaction is undecided, not refused
```

This corrects a claim worth stating precisely: `40001` is rare on a single node **by
accident**, and deterministic **by construction**. The lane no longer has to wait for
CockroachDB Cloud to exercise the contract the gate service is built on.

**`console` — three families, driven through the real toolchain:**

```
eslint  : error  'three' import is restricted … EVIDENCE register: no GPU rendering …
          no-restricted-imports                                          (pnpm run lint → 1)
tsc     : src/app/planted_type_error.ts(1,14): error TS2322:
          Type 'string' is not assignable to type 'number'.              (typecheck → 2)
vitest  : FAIL tests/unit/planted_failing.test.ts > planted anti-vacuity
          violation > PLANTED-VITEST-FAILURE                             (test → 1)
licences: • DENIED  gsap@3.13.0                                          (check:licences → 1)
licences: • NOT ALLOWED  axe-core@4.12.1 (runtime) is "MPL-2.0".         (check:licences → 1)
```

A measured detail that changed the design: **pnpm 11.5.3 verifies the installed tree
against `package.json` before running any script.** A package placed by hand under
`node_modules/` is moved to `node_modules/.ignored`, and a package that is only declared is
fetched. Both licence plants therefore name real, resolvable versions — which is also what
a real regression would look like. `axe-core` is MPL-2.0 and already in the tree in the
DEV closure, where that licence is an itemised exception; promoting it to `dependencies`
moves it into the RUNTIME closure, where it is not allowed. That exercises the scope
distinction, which a synthetic package with a made-up licence would not.

**`claims` — the union of the plants covers every rule:**

```
declared rules            : 21
planted by --self-test    : 4
fired by the red fixture  : 21
covered by some plant     : 21
sentences in the fixture  : 17
stripped copy exit        : 0
```

**`judge-pack` — the red half is not vacuous:**

```
baseline fail-findings on the real pack: (none)
  mutation changes the pack: view-columns · negative-refusal · does-not-prove ·
  envelope-agreement · plan-index-hint · plan-prefix · completeness · path · verify-md-drift
9 planted families: each mutation changes the pack, each is caught, and none of them is
reported on the unmutated pack.
```

**`skills` — five spec families and four marketplace families:**

```
unmutated scratch copy exit: 0
  REFUSED  missing-required-field: frontmatter is missing `description`
  REFUSED  malformed-name: must be lowercase words joined by single hyphens
  REFUSED  dangling-link: link target does not exist:
  REFUSED  out-of-spec-field: is not in the spec
  REFUSED  empty-body: the body after the frontmatter is empty
  REFUSED  dangling-skill-path: declared skill path has no SKILL.md
  REFUSED  upstream-staging-shipped: a plugin declares a path under skills/upstream/
  REFUSED  plugin-without-source: plugin entry lacks name or source
  REFUSED  missing-top-level-key: marketplace.json is missing `owner`
```

**`supply-chain` — four planted violations against the resolved-set assertion:**

```
=== model-sdk-in-the-export exit=1
::error title=SECURITY CLAIM BROKEN::… resolves model SDK distribution(s) ['boto3'],
  seen by uv export (the pinned resolution)
=== model-sdk-in-the-tree exit=1
::error title=SECURITY CLAIM BROKEN::… ['anthropic'], seen by uv tree (the workspace graph)
=== workspace-member-lost exit=1
::error title=vacuous assertion::uv export … did not name ['mainline-domain'] …
=== unreadable-path-entry exit=1
::error title=vacuous assertion::the export named a local entry whose pyproject.toml
  could not be read: ['-e ./packages/there-is-no-such-distribution']
```

The two witnesses were synthesised locally because `uv` is not installed on this
workstation (`docs/leads/ci-finish-final.md` §3.4); the fixtures use the real workspace
paths, so `workspace_name()` resolved `-e ./packages/trappoint-core` and
`-e ./verticals/mainline/packages/mainline-domain` against the real `pyproject.toml`
files. The CI job runs the same file against the real `uv export` and `uv tree` output.

---

## 5. Run URLs — the controls, observed in CI

Read with `gh run view <id> --json jobs`, on `master`, at commit `9d02cee`
(`console` re-run at `7e7cd04`).

| workflow | run | the negative-control job | conclusion |
|---|---|---|---|
| `claims` | [31441300036](https://github.com/Shaugato/mainline/actions/runs/31441300036) | `the red half is red for the reason it claims` | **success** |
| `judge-pack` | [31441299981](https://github.com/Shaugato/mainline/actions/runs/31441299981) | `the red half is red for the reason it claims` | **success** |
| `skills` | [31441300043](https://github.com/Shaugato/mainline/actions/runs/31441300043) | `spec conformance (red half, then green half)` | **success** |
| `supply-chain` | [31441300007](https://github.com/Shaugato/mainline/actions/runs/31441300007) | `SECURITY CLAIM …`, step `RED — four planted violations` | **success** |
| `release-proof` | [31441299987](https://github.com/Shaugato/mainline/actions/runs/31441299987) | `RED — the proof reports NOT PROVEN when the gate is removed` | **success** |
| `cloud-verify` | [31441340234](https://github.com/Shaugato/mainline/actions/runs/31441340234) | `a real 40001 RETRY_SERIALIZABLE …` · `is there a Cloud cluster … (and can it say no?)` | **success** |
| `console` | [31443340130](https://github.com/Shaugato/mainline/actions/runs/31443340130) — after [31441299984](https://github.com/Shaugato/mainline/actions/runs/31441299984), [31441667191](https://github.com/Shaugato/mainline/actions/runs/31441667191) and [31442295913](https://github.com/Shaugato/mainline/actions/runs/31442295913), all red and all quoted in §5.2 | `RED — pnpm run ci fails on every planted violation family` | **success** |

### 5.1 What CI added that the workstation could not

* **`supply-chain`** ran the four planted violations against the **real** `uv export` and
  `uv tree` output rather than the synthesised fixtures §4 used, because `uv` is not
  installed on the workstation:

  ```
  unmutated copies exit: 0
    REFUSED  model-sdk-in-the-export: SECURITY CLAIM BROKEN / boto3
    REFUSED  model-sdk-in-the-tree: SECURITY CLAIM BROKEN / anthropic
    REFUSED  workspace-member-lost: vacuous assertion / mainline-domain
    REFUSED  unreadable-path-entry: vacuous assertion / could not be read
  4 planted violations, every one refused by name. The SECURITY-CLAIM-BROKEN branch is now
  executed on every run of this lane, which it had never been before 2026-08-10.
  ```

* **`cloud-verify`** produced a real serialization restart on a GitHub runner:

  ```
  observed sqlstate : 40001
  observed message  : restart transaction: TransactionRetryWithProtoRefreshError:
                      TransactionRetryError: retry txn (RETRY_SERIALIZABLE): "sql txn"
                      meta={id=f8f7c852 key=/Table/106/1/2/0 iso=Serializable …}
  run_gate attempts : 2  retries: [(0, '40001', 0.006704260871989327)]
  max_attempts=1    : RetryBudgetExhausted: 40001 after 1 attempt(s) in 1.007s:
                      the transaction is undecided, not refused
  ```

* **`release-proof`** confirmed §2.1 on a GitHub runner rather than only on the
  workstation, and then confirmed the repair in the same job:

  ```
  the BARE pytest invocation exited 0 with nothing to prove against
  release suite: 15 test(s), 15 skipped, 0 failed
  CONFIRMED: bare pytest exits 0 on an all-skipped run, and the gate refuses it by name.
  …
  release suite: 15 test(s), 0 skipped, 0 failed
  every release assertion ran, none of them skipped
  ```

  and in `can-fail`, against two mutated copies of the 271-file migration tree:

  ```
    REPORTED FAILURE  gate-disabled -> CF-01: the merge was ADMITTED with an open obligation
    REPORTED FAILURE  expected-sqlstate -> CF-03: expected SQLSTATE P0001, observed 22000
  2 planted schema violations, each turning VERDICT PROVEN into VERDICT NOT PROVEN with
  the failing clause named in the report.
  ```

* **A fact the same `cloud-verify` run established, and it belongs on this page rather
  than in a footnote:** `verify` was **skipped** and `SKIPPED — no Cloud cluster secret` **ran**. The
  repository secret `CRDB_CLOUD_DSN` is **not set**, so nothing in this repository has ever
  spoken to CockroachDB Cloud, and `cloud-verify`'s green is the green of a lane that
  correctly reported having asserted nothing. That is the behaviour its header promises,
  and the new preflight job is what now proves the promise is kept rather than merely
  written. The four claims listed in the `skipped-loudly` summary remain unconfirmed
  against Cloud.

### 5.2 `console` — the green control earned its place on the first run

Run `31441299984` failed, and it failed **before any violation had been planted**:

```
GREEN CONTROL — the unmutated copy passes, so every red below is attributable
AssertionError: ../../../../spec/wire/refusal.schema.json must be readable from the
console workspace: expected false to be true
```

`tests/unit/data/_support.ts` sets `REPO_ROOT = '../../../../'`, and `vite.config.ts`
resolves `../../../../evidence/attestations/g1-attestation.json`. Four directories of
relative path reach out of the console and into the repository, so a copy under
`$RUNNER_TEMP` cannot see them — and every red after that point would have been an
artefact of the copying rather than evidence about a plant. The copy is now a **sibling of
`console/` at the same depth**, and the job's last step asserts both that no tracked file
moved and that nothing survived under `verticals/mainline/apps`.

Recorded here rather than quietly fixed, because it is the strongest single argument for
the shape this page describes: **the green control is not ceremony.** It caught a broken
control on its first execution, before the control could report a meaningless success.

Run `31441667191`, with the copy at the right depth, then caught three plants that were
breaking a **different** promise from the one they named — and it caught all three only
because the control asserts the message rather than the exit code:

```
  REFUSED  eslint-register-boundary  (exit 1)  -> EVIDENCE register: no GPU rendering, no-restricted-imports
  REFUSED  typescript-type-error     (exit 2)  -> TS2322, planted_type_error
  REFUSED  vitest-failing-case       (exit 1)  -> PLANTED-VITEST-FAILURE
##[error]PLANTED FAMILY bundle-over-budget: `pnpm run ci` exited 1, but its output never
         names ['[evidentiary-shell]', 'exceeds'].
##[error]PLANTED FAMILY denied-dependency-by-name: … never names ['DENIED'].
##[error]PLANTED FAMILY non-permissive-licence-in-the-runtime-closure: … never names
         ['NOT ALLOWED', 'MPL-2.0', 'runtime'].
```

* The two licence plants died **inside pnpm**, at `runDepsStatusCheck`: on a runner
  `CI=true` makes `--frozen-lockfile` the default, so pnpm's pre-run dependency check
  refused the out-of-date lockfile and the composite never reached `check:licences`.
  Resolving the lockfile is now part of *planting* the violation — a real regression
  arrives with its lockfile updated — and a failure to resolve is reported as a broken
  control, never as an exercised lane. Both refused by name on run `31442295913`:
  `DENIED, gsap` and `NOT ALLOWED, MPL-2.0, runtime`.
* The budget plant died at **`vitest`**, with `budgets.json is authoritative — it is what
  scripts/check-budgets.ts reads after the build. Correct the mirror, not the original.`
  The threshold `225280` lives in four places — `budgets.json`, `src/perf/budgets.ts`,
  `tests/unit/perf/budgets.test.ts` (`'220 KB'`) and `docs/performance-budgets.md`,
  rendered from the mirror — three of which are checks. **A budget cannot be breached by
  lowering it here**; it is breached by a bundle that is too big. The plant is now ~300 KB
  of incompressible base64 assigned onto `globalThis` from `src/main.tsx`, statically
  reachable from the entry: no new file (a dozen suites enumerate `src/**`), no export
  (`react-refresh/only-export-components` is a warning, and `--max-warnings 0` makes a
  warning an error). A sixth family was added for the other half of `check:budgets`, the
  one its own docstring calls out — `react` added to `forbidden_in_entry`, which nothing
  mirrors — and it must produce `[lazy-boundary]`.

Run [31443340130](https://github.com/Shaugato/mainline/actions/runs/31443340130) is the
first green one, and it is green with **seven** families rather than six:

```
  REFUSED  eslint-register-boundary   (exit 1)  -> EVIDENCE register: no GPU rendering, no-restricted-imports
  REFUSED  typescript-type-error      (exit 2)  -> TS2322, planted_type_error
  REFUSED  vitest-failing-case        (exit 1)  -> PLANTED-VITEST-FAILURE
  REFUSED  bundle-over-budget         (exit 1)  -> [evidentiary-shell], exceeds
  REFUSED  lazy-boundary-broken       (exit 1)  -> [lazy-boundary], react
  REFUSED  denied-dependency-by-name  (exit 1)  -> DENIED, gsap
  REFUSED  non-permissive-licence-in-the-runtime-closure (exit 1) -> NOT ALLOWED, MPL-2.0, runtime
7 planted violations, every one of them failing the WHOLE `pnpm run ci` chain and naming
its family in the log.
no tracked file moved, and the scratch copy has been removed
```

**Three red runs to get seven families each breaking the promise it names.** That is the
cost of the rule this page opens with, and not one of the three failures would have been
visible to a control that checked only the exit code: every one of them exited non-zero.
A control that asserted `returncode != 0` would have been green on the first run, on the
second, and on the third — and it would have been measuring the mirror test, pnpm's
lockfile verification, and a broken scratch copy, in a job whose name says it measures
the console's six promises.

## 6. What is still not observed, and where

* `cloud-verify` has **no `push:` trigger by design** — it holds the only credential this
  repository has, and a lane that reaches a live cluster on every commit bills a shared
  resource for every typo. Its jobs are reachable by `workflow_dispatch` and by the 17:00
  UTC schedule; run `31441340234` above is a dispatch.
* `cloud-verify`'s `verify` job has still never executed, because `CRDB_CLOUD_DSN` is not
  set. Its negative control runs regardless, which is the point of putting the control in
  `preflight` rather than in `verify`.
* Eight of the eighteen workflows have no negative control at all. §1 names them.
* `submission`'s `the submission gate can say no` pre-dates this wave and was not
  re-examined; the row says so.

---

## 7. `judge-pack`'s envelope step, and the two mutation families — measured 2026-08-13

**Measured at `9221d0c` on `master`.** Every exit code below came from running the command;
every CI line is quoted from a `gh run view --log` taken while the log was warm. Where a
check could not be made falsifiable it is named as unproven rather than argued around.

### 7.1 `cli.py envelope` — three of its four printed rows were decoration

The step at `judge-pack.yml`'s `green` job runs the command and asserts nothing about it.
`cmd_envelope`'s exit rule was one line:

```python
return EXIT_WRONG if cross.disagreements else EXIT_OK
```

Five mutations, each applied to a **copy** of `verticals/mainline/demo/judge/` in a
temporary directory, run on a bare CPython 3.13 carrying only PyYAML and httpx. The two
columns are the two environments that matter: **without `mainline_mcp` importable is what
CI actually has**, because the `green` job installs PyYAML and nothing else.

| mutation | `envelope`, no mcp | `envelope`, mcp on path | `validate --strict`, no mcp | `validate --strict`, mcp |
|---|---|---|---|---|
| unmutated | 0 | 0 | 0 | 0 |
| `REQUEST_TIMEOUT_SECONDS` 20 → 25 in `envelope.py` | **0** | **0** | 1 | 1 |
| `MAX_RESPONSE_BYTES` 10240 → 10241 in `envelope.py` | **0** | 1 | 1 | 1 |
| `Q10`'s EXPLAIN padded to 16 546 chars (cap 16 384) | **0** | **0** | 1 | 1 |
| `select_page_rows` 25 → 50 in `QUESTIONS.yaml` | **0** | **0** | 1 | 1 |
| **both judge-side files moved to 10241 together** | **0** | 1 | **0** | 1 |

Read the bold column. The command printed `DISAGREES (pack says 20)` and exited 0. It
printed `Q10 … chars= 16546 headroom= -162 DOES NOT FIT` and exited 0. **In the CI
environment it could not fail at all**, because the only condition it gated on was one it
never evaluated. From the warm log of run
[31657327334](https://github.com/Shaugato/mainline/actions/runs/31657327334), step
*The limits, the bound EXPLAIN lengths, and the cross-check*, conclusion `success`:

```
cross-check: NOT RUN — packages/mainline-mcp is not importable in this environment
(No module named 'mainline_mcp'); the second implementation of the envelope was NOT
consulted. This is not a pass.
```

The message says *"This is not a pass"* and the step recorded it as one — in the lane whose
own header calls a workflow that tolerates NOT RUN as success *the failure this whole pack
exists to refuse*.

**The last row is the finding, and it is not covered by "`validate --strict` catches it
anyway".** Move a limit in `envelope.py` and in `QUESTIONS.yaml` together and the two
judge-side files agree with each other; with the second implementation absent there is no
third party left to contradict them, and **both** commands exit 0. A documented
Managed-MCP limit could be redefined in this repository and no lane would notice.

**What changed.** `cmd_envelope` now collects a breach for every row it prints — a
declared limit that disagrees, a limit the pack omits, a limit the pack declares that
`envelope.py` does not model, a bound statement that does not fit, and any cross-check
disagreement — and exits 1 if there is one. `envelope` also grew `--require-cross-check`,
matching `validate`'s flag and exit code, which refuses to call a run where the second
implementation was never consulted a pass.

**Why one job now installs httpx.** `mainline_mcp.limits` is that second implementation,
and `mainline_mcp/__init__.py` reaches `client`, which imports `httpx`. Measured on a bare
venv carrying PyYAML alone: `cross-check: NOT RUN … No module named 'mainline_mcp'`. With
`httpx` installed and `PYTHONPATH=packages/mainline-mcp/src`: `cross-check: ran —
packages/mainline-mcp imported; constants compared`, exit 0. That is a path into a tree the
judge has already cloned, not an install of the workspace package, and it is confined to
the new `envelope-teeth` job — the `green` job still runs `envelope` with `python` and
PyYAML, which is the judge's own environment, and it now gates on every row it can check
from there.

**The negative control**, `envelope-teeth`, follows the shape the lane already uses. It
copies the judge package to a temporary directory, plants one defect, and requires exit 1
**and** the row the plant targets to be named — a plant that goes red for some other reason
is not evidence that its row is gated. It verifies an unmutated copy in the same directory
is green first, refuses a plant whose anchor has been renamed away (a `str.replace` that
matches nothing mutates nothing), and asserts the checkout is clean at the end. Dry-run
against the patched CLI, all six:

```
unmutated copy: exit 0
  plant: envelope.py REQUEST_TIMEOUT_SECONDS 20 -> 25 -> exit 1, names request_timeout_seconds/DISAGREES: True
  plant: envelope.py MAX_RESPONSE_BYTES 10240 -> 10241 -> exit 1, names MAX_RESPONSE_BYTES/DISAGREEMENT: True
  plant: QUESTIONS.yaml Q10 EXPLAIN padded past the 16384 cap -> exit 1, names Q10/DOES NOT FIT: True
  plant: QUESTIONS.yaml select_page_rows 25 -> 50 -> exit 1, names select_page_rows/DISAGREES: True
  plant: both judge-side files move to 10241 together -> exit 1, names MAX_RESPONSE_BYTES/DISAGREEMENT: True
```

and, separately, `envelope --require-cross-check` with `mainline_mcp` off the path exits
**1**, where plain `envelope` exits **0** with the gap stated in its last line.

**The control earned its keep on its first CI run, and that is the most useful thing on
this page.** Run
[31661375603](https://github.com/Shaugato/mainline/actions/runs/31661375603) — `failure`,
with `red`, `anti-vacuity` and `not-run-is-not-a-pass` all green in the same run, and the
job's first two steps green:

```
cross-check: ran — packages/mainline-mcp imported; constants compared
envelope --require-cross-check exited 1 with mainline-mcp absent, as required
```

That first line is the **first time the judge pack's limits have ever been compared against
the second implementation in CI**. Then the plant step:

```
unmutated copy: exit 1
  plant: envelope.py REQUEST_TIMEOUT_SECONDS 20 -> 25 -> exit 1, names request_timeout_seconds/DISAGREES: False
  … all five the same …
BASELINE COPY IS RED: an unmutated copy of the judge package exits 1, so every plant
below would be red for a reason that is not its plant.
RED FOR THE WRONG REASON [envelope.py REQUEST_TIMEOUT_SECONDS 20 -> 25]: exit 1, but the
output never named 'request_timeout_seconds' with a 'DISAGREES' verdict.
```

Every plant exited **1**. A control that asserted `returncode != 0` would have been green
on all five. The cause was in the harness, not the plants: `cli.py` computes
`REPO_ROOT = JUDGE_DIR.parents[3]` at import, the copy sat at `/tmp/<dir>/judge` which has
two parents, and the module raised `IndexError` before argparse ever saw `--root`. **It
reproduces only where the temporary directory is shallow, which is why a Windows
workstation ran the same script green.** The copy now keeps the package at its
repo-relative depth — `<tmp>/verticals/mainline/demo/judge`, whose `parents[3]` is `<tmp>`
itself for any `<tmp>`, `/` included.

Two things follow, and the second is the point of the whole page. The exit-code table above
is a workstation measurement and stands. The *control* is what a shallow `/tmp` falsified,
and it was caught by its own two clauses — the unmutated-copy check and the name-the-row
check — rather than by anyone reading a log.

### 7.2 `aws-evidence`'s mutation family — the harness was already right; the blast radius was not

The brief asked whether each plant fires **its own** invariant or merely some invariant.
**It already asserts its own**, and this is recorded as proven rather than rewritten.
`scripts/aws/verify_evidence.py::self_test` runs `if expected not in fired:` and reports
`What fired instead:`; it verifies the unmutated control first, so no plant's red can be
the sandbox's; and it fails on any declared invariant that has neither a plant nor a
written exemption.

The family was blocked by the `SEC-ACCOUNT-ID` false positive (the lead's §2). Measured on
a clean export of `9221d0c`, the only failure is still that one:

```
[SEC-ACCOUNT-ID] evidence/deploy/verify/aws-quota-and-cost.json:30: a bare 12-digit run
'322122547200' survives UUID/digest/decimal masking and has the shape of an AWS account id
1 failure(s) across 1 invariant(s): SEC-ACCOUNT-ID
```

Against the same evidence with the corrected scanner the baseline is clean —
`880 assertions across 40 of 40 declared invariants. PASS` — and the family runs and
passes: **`control (unmutated copy): 0 failure(s)`, 26 plants, every one `fires`, exit 0.**

What was **not** asserted is how much else each plant breaks. The workflow header carried
that as a comment, and the comment was wrong: it read *"24 of 24 plants … 13 fire it and
NOTHING else … the other 11"*, which is 24 outcomes over a table that holds **26 plants and
24 distinct invariant ids** — `SEC-ACCOUNT-ID` carries three. Re-measured by importing the
verifier and printing the full fired set per plant:

```
26 plants · 24 distinct expected ids · 15 fire their own invariant and nothing else
                                     · 11 additionally fire siblings
```

The 11 are not equal. `DOC-README-COVERS`'s plant writes a file into `evidence/aws/probe/`,
which then fails all seven envelope checks as well — **eight invariants from one plant**,
which makes "its own invariant fired" the weakest evidence in the table. `SEC-ARN-ACCOUNT`
also trips `SEC-ACCOUNT-ID`, because an ARN that keeps its account field contains an
account id.

**What changed.** A second step in `anti-vacuity` pins every plant's **exact** fired set to
a written declaration — an empty list included, because that is the claim most worth
making. It goes red three ways, each exercised locally against the clean baseline:

| perturbation | result |
|---|---|
| a declared sibling deleted from the table | exit 1 · `WIDER THAN DECLARED 'a DSN keeps its password' (SEC-DSN-PASSWORD): also fired ['DOC-README-COVERS']` |
| a sibling declared that does not fire | exit 1 · `NARROWER THAN DECLARED 'the census tally is bent' (CEN-TALLY): ['CEN-ANCHORS'] did NOT fire` |
| a plant with no entry at all | exit 1 · `UNDECLARED PLANT 'a census anchor stops resolving' (CEN-ANCHORS)` |
| unperturbed | exit 0 · `every plant fired exactly the invariants it declares` |

### 7.3 `mutation-ratchet` — the survivor half **could** be satisfied by a class surviving for an unrelated reason

W10 falsified the arithmetic half of this lane's one assertion (run
[31615605021](https://github.com/Shaugato/mainline/actions/runs/31615605021)). The
**survivor** half was `if "deontic_downgrade" not in hurt_text` — a substring search over
the crippled arm's whole stdout, under a failure message claiming the far stronger *"no
`deontic_downgrade` mutant SURVIVED"*. The warm log of run
[31657329516](https://github.com/Shaugato/mainline/actions/runs/31657329516), conclusion
`success`, shows why the gap matters:

```
INTACT    KILL wilson_lower=0.909774  120/125  surviving KILL classes: ['comparator_loosening']
CRIPPLED  KILL wilson_lower=0.802164  109/125  surviving KILL classes: ['comparator_loosening', 'deontic_downgrade']
```

`comparator_loosening` survives in **both** arms. Had the catalogue's deontic class
behaved like that one, the old check would have passed while the crippling did nothing to
it — the ratchet satisfied by a class surviving for a reason that is not `R1_DEONTIC`. It
happens not to be the case today, and nothing asserted it, so nothing would have noticed
the day it changed.

Replayed over six fixtures built from that recorded output, old logic against new:

| fixture | old | new |
|---|---|---|
| the real recorded run | 0 | **0** |
| `deontic_downgrade` survives in BOTH arms | **0** | **1** |
| crippled arm names no `deontic_downgrade` survivor | 1 | 1 |
| crippled arm is not worse | 1 | 1 |
| the harness stops printing `surviving KILL classes:` | **0** | **1** |
| `deontic_downgrade` appears only OUTSIDE the survivors line | **0** | **1** |

Three ways to satisfy the old ratchet without its claim being true. The survivor sets are
now parsed off the `surviving KILL classes:` line of **each** arm; `deontic_downgrade` must
be in the crippled set **and absent from the intact set**; and the classes that survive in
both arms are printed and named as survivors this lane does **not** attribute to
`R1_DEONTIC`. **None of these is a threshold on the figure** — each is a condition under
which the measurement did not measure what it names, which is the category this lane's
header already fails on. It is still never a gate.

The same job's `Tear down` step carried `docker rm -f mutation-crdb || true`, a banned
construct. What it was for is real — `if: always()` means it runs on a job that died before
the container started — so it was replaced by asking whether there is anything to remove,
rather than swallowing the answer. A `docker rm` that fails on a container which **does**
exist is a leaked container on a shared runner and is now visible.

### 7.4 What is still unproven here

* **The `envelope` step's cross-check has never run on `master`.** It runs in
  `envelope-teeth` from this commit onward; before that, every recorded `judge-pack` green
  carries `cross-check: NOT RUN` in its log, including run `31657327334`. Any claim that
  the judge pack's limits have been confirmed against a second implementation **in CI** is
  false for every run before this one.
* **`validate --strict` still tolerates the absent cross-check.** `cmd_validate` prints
  `NOT RUN` and adds no `warn`, so `--strict` does not promote it; only
  `--require-cross-check` fails on it, and the `green` job does not pass that flag.
  `verticals/mainline/demo/judge/pack.py` and `envelope.py` are not this worker's files;
  reported, not edited.
* **`aws-evidence`'s family is proven against a corrected scanner, not against `master`.**
  At `9221d0c` an unmutated `evidence/` still fails `SEC-ACCOUNT-ID`, so the family's job
  is red for the control, not for a plant. The measurement above used a clean export of
  `9221d0c` carrying the working-tree scanner fix; it is not a claim about a CI run until
  that fix is committed.
* **Sixteen `aws-evidence` invariants have no plant** and are carried on a written
  exemption list in `self_test`. That list is named rather than hidden, which is the right
  shape, but a named exemption is still an unexercised check.
* **The blast-radius declaration is a measurement, not a derivation.** It records what each
  plant fires today. It cannot say whether a sibling *should* fire — only that the set
  stopped matching what a reviewer wrote down.
