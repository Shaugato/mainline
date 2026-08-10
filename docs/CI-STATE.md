<!--
SPDX-FileCopyrightText: 2026 MAINLINE contributors
SPDX-License-Identifier: CC-BY-4.0
-->

# CI state — what GitHub actually says

**Measured:** 2026-08-10, from `github.com/Shaugato/mainline`, branch `master`, commit
`4d948dd` (`fix(ci): repair the sixteen-workflow pipeline; run it on master at last`).
**Source:** `gh run list` and `gh run view --log-failed` against real runs. Nothing in this
document is inferred from a local run; where a local reproduction is quoted it is labelled as
such and is used only to *explain* a CI result, never to replace one.

This file is written by the CI verifier and is deliberately unflattering. Of 17 workflows, six
are green, ten are red, and one has never run. Two of the reds are **regressions introduced by
the repair wave this commit contains**, and they are named as such in §5. Two more are
pre-existing defects that became visible for the first time today, for the reason given in §1.

Nothing here was inferred from a green local run. Where a workflow is red, it is named and the
cause is quoted from its log.

---

## 0. Re-check it yourself

```bash
# every workflow's real conclusion on the default branch
gh run list --branch master --limit 20

# one workflow's conclusion and its jobs
gh run view <run-id> --json jobs \
  --template '{{range .jobs}}{{.conclusion}} :: {{.name}}{{"\n"}}{{end}}'

# the precise cause of a red (this is the command every claim below rests on)
gh run view <run-id> --log-failed

# the default branch, which is the whole of §1
gh repo view --json defaultBranchRef
```

`jq` is **not** installed on this workstation; the `--template` form above is the substitute
used throughout. Note that `gh --template` renders large run ids in scientific notation — use
`--json databaseId` and read the id from `gh run list`'s plain output instead.

---

## 1. The finding that outranks the table

Before this commit, **every workflow except `submission` was triggered on
`push: branches: [main]`, against a repository whose default branch is `master`.**

```
gh repo view --json defaultBranchRef   ->  master
gh run list --branch main              ->  (empty)
```

The branch `main` does not exist. Fifteen lanes had therefore **never run once on the branch
the Actions tab opens on**. Their green — or their red — was invisible to anyone who landed on
the repository. The single push-triggered lane a visitor could see was `submission`, and it
was red.

This commit retargets them to `master`. The fifteen runs analysed below are, for most of these
lanes, **the first push run in the repository's history**. That is why several reds appear here
that no previous run could have shown: they were always true, and nothing was looking.

Two lanes deliberately have **no** `push:` trigger and were correctly left alone —
`cloud-verify` (holds the only credential, `secrets.CRDB_CLOUD_DSN`; nightly by design) and
`demo-health` (asserts a property of a *deployed* demo, not of a commit). Both still reach
`master`, because GitHub fires `schedule:` from the default branch only.

---

## 2. Every workflow, with its real conclusion

Run ids are from the push of `4d948dd`. URL form:
`https://github.com/Shaugato/mainline/actions/runs/<run-id>`.

| workflow | conclusion | run id | cause of red | intentional? |
|---|---|---|---|---|
| `claims` | **success** | 31386723733 | — | — |
| `console` | **success** | 31386723734 | — | — |
| `judge-pack` | **success** | 31386723727 | — | — |
| `release-proof` | **success** | 31386723657 | — | — |
| `skills` | **success** | 31386723686 | — | — |
| `supply-chain` | **success** | 31386723719 | — | — (verified non-vacuous, §4) |
| `mutation-ratchet` | **failure** | 31386723743 | lane dependency floor: no `pytest-timeout`, no `PyYAML` — §3.9 | **no — still to fix** |
| `nightly-differential` | **failure** | 31386723762 | `uv … --package` passed twice — §3.10 | **no — still to fix** |
| `ci` | **failure** | 31386723652 | 5 of 12 jobs red — §3.1 | partly (2 of 5) |
| `db` | **failure** | 31386723687 | image-pin census ratchet rose — §3.2 | **no — regression** |
| `db-schema` | **failure** | 31386723718 | MI catalogue lag + tier-0 precondition — §3.3 | partly |
| `boundary` | **failure** | 31386723645 | A6 sampling-param grep false positive — §3.4 | **no — instrument defect** |
| `custody-chain` | **failure** | 31386723642 | 7 of 16 custody checks unimplemented — §3.5 | **yes** |
| `schema` | **failure** | 31386723716 | reference vertical missing a producer — §3.6 | **yes** |
| `submission` | **failure** | 31386723640 | licence-spelling ratchet — §3.7 | **yes** (pre-existing) |
| `demo-health` | **failure** | 31386591084 | `DEMO_URL` unset; no demo deployed — §3.8 | **yes** |
| `cloud-verify` | *no runs* | — | schedule-only; has never fired | **yes** |

**Score on GitHub: 6 green, 10 red, 1 never-run, of 17 workflows.**

Before this commit the honest score was *1 red and 16 invisible*, because only `submission` ran
on `master` at all. Six green lanes and ten precisely-diagnosed reds is a worse-looking Actions
tab and a far better-understood repository.

---

## 3. Each red, precisely

### 3.1 `ci` — 5 of 12 jobs red

Green now, and worth naming because they were red before: **`actionlint`** (SC2015 in
`custody-chain.yml`, SC2034 in `nightly-differential.yml`), **`mypy · and the target list is
complete`** (the `CandidateRow | None` narrowing and the misplaced `docx` override),
**`import-linter contracts`**, **`the lockfile is authoritative`**, **`the sequence ban`**, and
the new **`RED BY DESIGN, and it must stay red`** job, which passes — meaning the by-design-red
suites really are red and are now asserted to be, rather than being lost in the general lane.

Still red:

| job | cause | class |
|---|---|---|
| `PL-2 — the red run is recorded` | `PL-2: the db lane's red run URL is still UNRECORDED. Open the db workflow run, copy its URL into the ADR's run_url field, and commit.` | bookkeeping — **now newly actionable**, because `db` has only just produced its first `master` run to cite |
| `REUSE — every file names its licence` | `REFUSED [RATCHET] metric=non_spdx_spelling.FSL-1.1-ALv2 baseline=1213 measured=1254` | **pre-existing**, not this wave — see §3.7 |
| `pytest --crdb=none` | `41 failed, 8224 passed, 833 skipped, 5 deselected` (was `47 failed, 8182 passed`) | mixed — includes **2 new regressions**, §5.1 |
| `ruff format · the counted lint ratchet` | `209 files would be reformatted, 1185 files already formatted`; `ruff_ratchet: REFUSED - 4 ratchet regression(s)` | **deliberately deferred** — a mechanical `ruff format .` that must land alone or it hides every other diff in the wave |
| `CI summary` | aggregate of the above | — |

### 3.2 `db` — a regression this wave introduced

```
##[error]floating tag rose from 34 to 37
##[error]restated literal rose from 21 to 24
```

The `db` lane carries a census job — *"one version constant, and it lives in compose.yaml"* —
which counts how many files restate the CockroachDB image instead of reading it from
`compose.yaml`. It is a falling-only ratchet: the count may fall, it may not rise.

Reproduced locally, exactly (`floating=37 ceiling=34  restated=24 ceiling=21`). Counting the
same census at both commits settles authorship beyond argument — **at `HEAD~1` both metrics sat
exactly on their ceilings**, so the lane was passing with zero headroom and any new mention at
all would trip it:

```
HEAD~1  floating=34  restated=21     <- exactly at ceiling, passing
HEAD    floating=37  restated=24     <- +3 and +3
ceilings          34            21
```

The delta is attributable line by line:

| file | metric | before | after |
|---|---|---|---|
| `conftest.py` | floating | 1 | 4 |
| `.github/workflows/custody-chain.yml` | restated | 0 | 2 |
| `tests/integration/recall_schema/_schema_support.py` | restated | 0 | 1 |

All six new lines are **prose** — docstrings, error-message text and comments in which workers
recorded *"measured on cockroachdb/cockroach:v26.2.5"* to make their evidence checkable. The
intent was good and the ratchet is still right: a version literal restated in prose is a
version literal that goes stale. The fix is to reword the six lines so they cite the version
without spelling the image coordinate, or to extend the census's existing exemption mechanism
to prose with an argued reason. **Not** to raise the ceiling.

Owners: `conftest.py` (w3), `custody-chain.yml` (w4), `_schema_support.py` (w6). The verifier
does not own these files and has not edited them.

### 3.3 `db-schema` — the original defect is fixed; two lesser ones remain

The failure named in the brief — `0139_trg_candidate_project.sql failed to apply — unknown
function: mainline.fn_candidate_project()` — **no longer occurs.** The cause was real and was
never an environment difference: `RECALL_MIGRATION_NUMBERS` in
`tests/integration/recall_schema/_schema_support.py` hand-declares a subset of the chain and
omitted `0110`, the producer that `0139` welds to. The full local chain always applies `0110`
first, which is why 271/271 passed locally and CI failed. Adding the producer fixed it.

Remaining:

* **`mi-red`** — `REFUSED: MI06 / MI10 / MI21 / MI22 / MI27 is pending but its tests pass —
  promote it in mi_catalogue.yaml`. Down from ten. Seven invariants (MI01, MI02, MI11, MI16,
  MI18, MI19, MI28) were promoted; **five were deliberately held**, with the reasoning written
  into the catalogue: for MI06 and MI21 the object §16 names (`fn_boundary_project`) is absent
  from all 271 migrations, so promoting would be a lie. This red is honest, and it is pointing
  at a real disagreement: the ratchet equates *"the owning test passes"* with *"the invariant
  is enforced"*, and for these five that equation is false. The fix is to strengthen the owning
  tests so they fail — not to promote, and not to weaken the ratchet.
* **tier 0** — `assert 'uv sync --package' not in err`, from
  `packages/trappoint-migrate/tests/test_cli_offline.py::test_delegated_verb_actually_delegates_when_present`.
  The test asserts that `render` reaches the real implementation *when `trappoint-sql` is
  installed*; the job runs `uv run --frozen --package trappoint-migrate`, an environment in
  which `trappoint-sql` is by construction absent. The precondition is unstated. Environment
  defect, still to fix — the repair is to guard the test on the import it silently requires.

### 3.4 `boundary` — the import floor is fixed; the grep is miscalibrated

The `ModuleNotFoundError: No module named 'psycopg'` that failed all seven jobs is **gone** —
`trappoint_testkit/__init__.py` no longer drags the cluster module (and a live database driver)
in for callers who only want the image pin. The lane now actually runs its tests.

What it reports now is a **false positive**:

```
[GREP/GREP-SAMPLING-PARAM] packages/trappoint-recall/.../lexical/units.py:67:
    model request builder sets 'temperature'
[GREP/GREP-SAMPLING-PARAM] verticals/mainline/.../mainline_domain/quantity/units.py:262:
    model request builder sets 'temperature'
```

Both lines were read at source. Neither is a model request builder:

```python
# packages/trappoint-recall/src/trappoint_recall/lexical/units.py:67
DIMENSION_SYMBOL: Final[dict[str, str]] = { ..., "temperature": "k", ... }

# verticals/mainline/packages/mainline-domain/src/mainline_domain/quantity/units.py:262
_LABEL_REPRESENTATIVES: Final[Mapping[str, str]] = { ..., "temperature": "kelvin", ... }
```

They are physical-dimension tables in an industrial-safety domain that also carries `pressure`,
`lel` and `uel`. The A6 guard matches the bare token `temperature` and calls any hit a sampling
parameter. This is a red that is **not** telling the truth, and suppressing it is not the
answer either: the guard must be narrowed so it measures what it claims — a sampling parameter
in a request-builder context — or these two must take the argued exemption the guard already
supports and uses elsewhere. Until then the A6 ban is partly unenforceable, because its
operators have learned that its output contains noise.

### 3.5 `custody-chain` — correctly red

`16 checks | 9 passed | 0 failed | 7 not checked`.

Check 14 (`closure_generation_monotone`) and check 13 (`no_sandbox_leaf`) are now
`implemented`, so the brief's `K2.2 NOT MET: … check 14 with status 'deferred'` is **fixed**.
The seven that remain are all `status=deferred, target=implemented, owner=verify-crypto` — the
cryptographic verifier checks genuinely do not exist yet. The lane is red because the product
is incomplete, which is the correct behaviour. See also §5.1: the *way* checks 13/14 were
flipped introduced a regression.

### 3.6 `schema` — correctly red, and deliberately out of scope

```
trappoint migrate: REFUSED: 0058_blocking_check: [42P01] relation "trappoint_ref.event" does not exist
```

The **reference** vertical (`packages/trappoint-sql/refvertical/sql`) has a missing producer —
the same shape of defect as §3.3, in a different tree with a different owner. It was
deliberately not folded into this wave. It is genuine product incompleteness and stays red
until `trappoint_ref.event` has a producer.

### 3.7 `submission` — the path-length gate is fixed; the licence ratchet is not

Two of three jobs are green, including `the submission gate can say no`. The old failure —
`path-length budget EXCEEDED: longest tracked path 218 > budget 214` — is **fixed**; measured
locally now: `budget: max_tracked_path_chars=141 files_unclonable_at_typical_prefix=0
STATUS: OK`. A stranger can clone this repository on Windows.

The remaining red is the licence-spelling ratchet:

```
REFUSED [RATCHET] metric=non_spdx_spelling.FSL-1.1-ALv2 baseline=1213 measured=1254
```

**This is pre-existing and is not attributable to this wave.** `qa/reuse-ratchet.json` was not
touched by this commit; the same `measured=1254` was recorded in the pre-wave runs, and it
reproduces locally at `HEAD`. It entered with `5ddaa3a`. The Functional Source License is not
on the SPDX list, so REUSE 3.3 requires the `LicenseRef-` form; 41 files added by the previous
wave use the bare spelling. The red is telling the truth and the repair is a spelling pass over
those 41 files, followed by regenerating the ratchet.

### 3.8 `demo-health` — correctly red, and loudly so

```
##[error]Set the repository variable DEMO_URL to the CloudFront demo URL … This job fails
rather than skips, because a health check that passes without checking anything is the
failure it exists to prevent.
```

No demo is deployed and `gh variable list` is empty. The job is scheduled every 30 minutes, so
it will keep accumulating red runs on the Actions tab until the demo exists and `DEMO_URL` is
set. That is a configuration truth, not a health truth, and the job says so by name. It is
correct as written; the cost is cosmetic and the cure is to deploy the demo.

### 3.9 `mutation-ratchet` — the cluster now starts; the lane's dependency floor is short

The `error: hostname of listen_addr must be "127.0.0.1" or "localhost"` that stopped this lane
is **gone**. The node came up and the whole chain applied against it in CI:

```
fingerprint b558074c4e01a80ab76e523237443cc9a332390de770da7a9ea348cb688b7c7c
            (grade strong, attestation ordinal 271)
```

That is 271 migrations applied on a real CockroachDB v26.2.5 container inside GitHub Actions —
the central claim now has a CI witness, not only a local one.

The lane then fails at `exit code 4` (pytest usage error) for two dependency reasons:

```
uv run --frozen --package mainline-mutation python -m pytest tests/e2e/mutation tests/unit/domain/novelty -q
ERROR: Unknown config option: timeout
ModuleNotFoundError: No module named 'yaml'   (tests/unit/domain/novelty/test_novelty_manifest.py:45)
```

The root `pyproject.toml` sets `--strict-config` and `timeout = 120`, so any environment
without `pytest-timeout` refuses to start; and the minimal `--package mainline-mutation`
environment does not carry `PyYAML`, which the selected tests import. This is the same class of
defect as `release-proof`'s exit-4 — which **was** fixed in this wave — applied to a lane whose
owner fixed only the container. Environment defect, still to fix, and the repair is to add both
to the lane's install line.

### 3.10 `nightly-differential` — a latent authoring bug that only became visible today

```
error: the argument '--package <PACKAGE>' cannot be used multiple times
##[error]Process completed with exit code 2.
```

`uv` accepts `--package` once. `nightly-differential.yml:292` and `:302` pass it twice:

```yaml
run: uv sync --frozen --package trappoint-model --package trappoint-core
     uv run  --frozen --package trappoint-model --package trappoint-core \
```

**This is pre-existing, and it is the clearest single illustration of §1.** The same two lines
are present verbatim at `HEAD~1`; the wave did not touch them. They had simply never been
executed, because the lane was keyed to `push: branches: [main]` and `main` does not exist. The
defect has been sitting in the tree unobserved, and retargeting the trigger is what found it.
Environment defect, still to fix; the repair is `--all-packages`, or one `--package` plus the
other dependency supplied another way.

The `64 parallel merges of one subject` job carries no `continue-on-error` (there is none
anywhere in the file), so its failure fixes the run's conclusion at **failure** regardless of
the two `differential ·` matrix jobs, which allow up to `timeout-minutes: 180` and were still
running when this was written. Their individual outcomes are worth reading when they land, but
they cannot change the lane's verdict.

---

## 4. `supply-chain` is green, and the green is real

The brief flagged this lane as the one whose *earlier pass was vacuous* — the anti-vacuity
guard had reported that `mainline-domain` and `trappoint-core` never appeared in the set being
searched, so the clean result was measured over the wrong thing. That has been verified fixed,
not merely observed green:

```
Witness two — uv tree --frozen --no-dev --package mainline-gate-svc
  mainline-gate-svc v0.1.0
  ├── mainline-domain v0.1.0
  │   ├── numpy v2.5.1
  │   ├── pint v0.25.3
  │   ├── rapidfuzz v3.14.5
  │   └── scipy v1.18.0
  ├── psycopg[binary] v3.3.4
  └── trappoint-core v0.1.0

THE ASSERTION — uv export: 15 distribution(s) … including mainline-domain, trappoint-core
                uv tree:   14 distribution(s) … including mainline-domain, trappoint-core
```

Both witnesses now name the required workspace members, so the anti-vacuity guard is satisfied
**by evidence** rather than bypassed, and the no-model-SDK claim is asserted over a set that
actually contains the gate service's own dependencies. The guard was strengthened, not removed.

The architectural fact this exposes is recorded rather than hidden: `mainline-gate-svc`, a
service whose entire job is one `SERIALIZABLE` transaction and one `CALL mainline.merge_permit`,
reaches **scipy, numpy, pint and rapidfuzz** through `mainline-domain`. No model SDK is present
— the claim holds — but four BLAS/binary-wheel distributions inside a determinism-critical
merge gate is a `mainline-domain` split worth making later.

---

## 5. Regressions introduced by this wave

Two, both caught by guards that were doing their job.

### 5.1 The custody registry was flipped on one side only

`packages/trappoint-verify/tests/test_checks_totality.py` — 2 tests, newly failing:

```
test_the_embedded_registry_matches_the_normative_yaml
  check 1.status: the copy in trappoint_verify.checks says 'deferred';
  spec/custody/checks.yaml says 'implemented'

test_the_declared_status_lag_is_exactly_the_real_one
  checks.SPEC_STATUS_LAG says the registry lags for (1, 2, 3, 9, 10, 13, 14, 15, 16),
  but the real discrepancy is (). Either a check was implemented without declaring the
  lag, or checks.yaml has been flipped and this tuple must shrink in the same commit.
```

`SPEC_STATUS_LAG` names the checks that are implemented **in code** while `checks.yaml` still
calls them `deferred` — a declared, bounded window. This commit flipped exactly those nine ids
in `spec/custody/checks.yaml` from `deferred` to `implemented`, and did not touch
`packages/trappoint-verify/src/trappoint_verify/checks/__init__.py`, where both the embedded
status copy and `SPEC_STATUS_LAG = (1, 2, 3, 9, 10, 13, 14, 15, 16)` still stand. The window
closed; its declaration did not shrink with it.

Verified by substitution, then restored:

```
HEAD~1 checks.yaml + HEAD code  ->  12 passed
HEAD   checks.yaml + HEAD code  ->  2 failed, 10 passed
```

The remedy is the one the assertion names: in `checks/__init__.py`, set `SPEC_STATUS_LAG = ()`
and flip the embedded status metadata for ids 1, 2, 3, 9, 10, 13, 14, 15, 16 to `implemented`,
in one commit. Owner: w5. The verifier does not own that file.

### 5.2 The image-pin census rose

Six prose lines restating `cockroachdb/cockroach:v26.2.5` and `…:latest-v26.2`. Full accounting
in §3.2.

---

## 6. Honest reds — what stays red, and the truth each one reports

| assertion | truth it reports |
|---|---|
| `custody-chain`, 7 not checked | the cryptographic verifier checks do not exist yet (`owner=verify-crypto`) |
| `schema`, `0058_blocking_check` | the reference vertical has no producer for `trappoint_ref.event` |
| `db-schema` `mi-red`, 5 held | five MI invariants' owning tests pass without the invariant being enforced; the tests are too weak, and saying so is more honest than promoting |
| `ci` `ruff format`, 209 files | the tree is genuinely unformatted; the fix is one mechanical commit that must land alone |
| `ci` REUSE / `submission`, 1254 vs 1213 | 41 files use the bare `FSL-1.1-ALv2` spelling where REUSE 3.3 requires `LicenseRef-` |
| `ci` PL-2 run url | the ADR does not yet cite the `db` red run — newly citable, since `db` only just ran on `master` |
| `demo-health`, `DEMO_URL` unset | no demo is deployed |
| `tests/eval/recall/test_g4alpha_gates.py` and the MI/PL-2 reds | asserted red by the new `RED BY DESIGN` job, which fails loudly if any of them goes green |

The last row is the structural change that makes this table legible rather than embarrassing.
`ci` previously ran the by-design-red suites inside the general `pytest` lane, where a judge —
and a contributor — could not tell a declared red from a regression. They now run in a
dedicated job that **inverts the verdict**: a test in the declared set that fails is the
expected state and the job is green; a test that *passes* fails the job by name. It carries
three anti-vacuity guards, read directly from `.github/workflows/ci.yml`:

* a **floor** (`RED_FLOOR: 5`) on *failures*, so a selector that silently collapses to the
  empty set fails instead of passing;
* a **registry** mapping every permitted file to the truth its red reports, so the marker
  cannot become a place to hide an inconvenient regression;
* a **skip census**, because `--crdb=none` cannot measure a cluster-backed test and an
  unmeasured test may never satisfy the floor.

The job is green in run 31386723652, which means all nine declared reds are still red and
nothing else moved into that set.

No `continue-on-error` was added and no `|| true` was added. **Four real ones were removed**
(non-comment occurrences across the workflow tree fell 19 → 15):

```
-  run: python -m mainline_boundary.cli e1 --json || true          boundary.yml
-  run: python -m mainline_boundary.cli e3 || true                 boundary.yml
-  … && { echo "::error::the verifier pulled in a dependency beyond cryptography"; exit 1; } || true
-  grep -E '^[A-Za-z0-9]' gate-svc.requirements.txt || true        supply-chain.yml
```

The third of those is the `custody-chain.yml` SC2015 that `actionlint` flagged: an
`A && { …; exit 1; } || true` whose trailing `|| true` swallowed the very `exit 1` it had just
raised, so the dependency-floor check could not fail. Removing it is what makes that assertion
real. No assertion was deleted, and `docs/HONESTY.md` was not edited by this wave.
The three `continue-on-error` entries in `submission.yml` are pre-existing and structural: they
capture a step's exit status via `PIPESTATUS` so a later decision step can fail on it.

---

## 7. Corrections to the triage this repair started from

Three claims in the original problem statement did not survive measurement. They are recorded
because each one would have sent a worker to fix a thing that was not broken.

* **"`custody-chain` → `check_chain_fn_matches_spec.py` **absent**"** — the file is present and
  has been tracked since `904f1b4`:
  `git ls-files --error-unmatch scripts/custody/check_chain_fn_matches_spec.py` resolves. The
  brief's line was the `run:` block's own **echoed source** appearing in the log, not the step's
  output. `gh run view --log-failed` prints both, and they are easy to confuse: every echoed
  source line is prefixed by the runner with the same job/step columns as real output.
* **"`supply-chain` → `SECURITY CLAIM BROKEN: mainline-gate-svc now resolves …`"** — this string
  was never printed as output either; same cause. The finding that *was* printed, in every
  recent run, is the anti-vacuity guard reporting that the resolved set did not contain the
  workspace members — which is a statement about the instrument, not about a broken boundary.
  §4 shows the boundary itself holds.
* **"Sixteen workflows exist"** — there are **17** files in `.github/workflows/`.

The general lesson for reading these logs: `##[error]` lines and lines inside a `##[group]Run …`
header are different kinds of thing, and only the former are results.

---

## 8. What to do next, in the order that changes the Actions tab most

1. **Fix the two regressions this wave introduced** (§5). Both are small, both are guards
   working correctly, and both should land before anything else — a repair wave that leaves
   regressions behind teaches people to distrust the guards.
   `SPEC_STATUS_LAG = ()` plus nine embedded status flips; six prose lines reworded.
2. **`nightly-differential`'s `--package` twice** (§3.10) and **`mutation-ratchet`'s missing
   `pytest-timeout` / `PyYAML`** (§3.9). Both are one-line lane fixes and both currently mask
   whatever those lanes would otherwise measure.
3. **Narrow the A6 sampling-parameter grep** (§3.4) so `boundary` stops reporting two
   physical-unit tables as model request builders. A guard that cries wolf is a guard on its
   way to being ignored.
4. **The `ruff format` commit** (§3.1) — mechanical, 209 files, must land alone.
5. **The `LicenseRef-` spelling pass** over 41 files (§3.7), then regenerate
   `qa/reuse-ratchet.json`.
6. **Record the `db` red run URL in the PL-2 ADR** (§3.1). This is now possible for the first
   time, because `db` has finally run on `master`.

What stays red after all of that, and should: `custody-chain` (7 crypto checks unwritten),
`schema` (reference vertical producer), `db-schema`'s five held MI invariants, and
`demo-health` until a demo exists. Those four are the product being honest about its own
incompleteness, which is the property this pipeline was built to preserve.

---

## 9. Re-checking this document

Every claim above is reproducible with the commands in §0. The fastest full check:

```bash
gh run list --branch master --limit 20
gh run view 31386723652 --json jobs \
  --template '{{range .jobs}}{{.conclusion}} :: {{.name}}{{"\n"}}{{end}}'   # ci
gh run view <any-red-run-id> --log-failed
```

For a job in a run that is still in progress — whose logs `gh run view` will not serve — fetch
the job directly:

```bash
gh api repos/Shaugato/mainline/actions/runs/<run-id>/jobs \
  --jq '.jobs[] | "\(.id) \(.conclusion) \(.name)"'
gh api repos/Shaugato/mainline/actions/jobs/<job-id>/logs
```

`gh api --jq` uses gh's own embedded jq and does not need the `jq` binary, which is not
installed on this workstation. Omit the leading `/` from the endpoint or Git Bash will rewrite
it into a filesystem path.

At the time of writing, `nightly-differential`'s two `differential ·` matrix jobs
(`93448687081`, `93448687143`) were still running. They cannot change that lane's conclusion
(§3.10), but their own results are worth reading when they land.
