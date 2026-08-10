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
| `judge-pack` | `the validator fires on every planted violation` · `a run with no cluster exits 3, never 0` · **and** `the red half is red for the reason it claims` | 9 pack mutations (renamed column, negative gone green, unbounded claim, envelope loosened, index hint dropped, prefix widened, decorative completeness column, dangling `defined_in`, prompt dropped) + claim-hygiene + bound-length; the meta-job asserts each mutation **changes the document**, each is **caught**, and **none** of the nine checks fails on the unmutated pack | no — in-memory copies, asserted |
| `console` | `RED — pnpm run ci fails on every planted violation family` | `eslint-register-boundary`, `typescript-type-error`, `vitest-failing-case`, `bundle-over-budget`, `denied-dependency-by-name`, `non-permissive-licence-in-the-runtime-closure` — **each driven through the whole `pnpm run ci` chain**, not through its own sub-command | no — an untracked sibling copy at the same depth (§5.2), removed and asserted gone |
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
| `mutation-ratchet` | **by construction** — the lane IS a mutation harness; its number is the proportion of planted mutants the suite kills | every mutant the ratchet generates | — |
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
| `console` | [31441299984](https://github.com/Shaugato/mainline/actions/runs/31441299984) → [31441667191](https://github.com/Shaugato/mainline/actions/runs/31441667191) | `RED — pnpm run ci fails on every planted violation family` | see §5.2 |

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
